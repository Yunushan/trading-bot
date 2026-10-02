"""Actual admin BUY recovery validates durable evidence before publication."""
from __future__ import annotations

import copy
from contextlib import redirect_stdout
from decimal import Decimal
from io import StringIO
import json
import os
from types import SimpleNamespace
import unittest
from unittest.mock import patch
from uuid import uuid4

import test_spot_buy_generation_faults as buy_fixture

from app.integrations.exchanges.binance.orders import order_intent_admin as admin
from app.integrations.exchanges.binance.orders import order_intent_runtime as ledger
from app.integrations.exchanges.binance.orders import spot_buy_admin_recovery_runtime as publication
from app.integrations.exchanges.binance.orders import spot_fill_recovery_runtime as recovery
from app.integrations.exchanges.binance.orders.spot_execution_owner import owner_administration_lock, owner_marker_path


class SpotBuyAdminPublicationTests(unittest.TestCase):
    def setUp(self):
        self.actual = buy_fixture.SpotBuyGenerationFaultsTests()
        self.actual.setUp()
        self.addCleanup(self.actual.doCleanups)
        _event, self.primary = self.actual._buy()
        self.client_id = self.primary["client_order_id"]
        self.path = self.actual.fixture.allocation_path
        self.intent_path = ledger._intent_path(self.actual.wrapper)
        self.order = copy.deepcopy(self.actual.fixture.venue.orders[self.client_id])
        self.trade = {
            "symbol": "BTCUSDT", "orderId": self.order["orderId"], "id": self.primary["trade_ids"][0],
            "isBuyer": True, "price": "20000", "qty": "0.1", "quoteQty": "2000",
            "commission": "0", "commissionAsset": "BTC", "time": self.primary["fill_time_ms"],
        }
        self.actual.wrapper._spot_execution_owner.close()

    def _run(self, *, order=None, trade=None, during_trades=None):
        order = copy.deepcopy(self.order if order is None else order)
        trade = copy.deepcopy(self.trade if trade is None else trade)
        queried = []
        capture_binding = publication.capture_spot_buy_recovery_binding

        def captured_owner(owner):
            self.admin_owner = owner
            return capture_binding(owner)

        def get_order(**params):
            self.assertEqual({"symbol": "BTCUSDT", "origClientOrderId": self.client_id}, params)
            queried.append("order")
            return copy.deepcopy(order)

        def get_trades(**params):
            self.assertEqual("BTCUSDT", params["symbol"])
            self.assertEqual(self.order["orderId"], params["order_id"])
            queried.append("trades")
            if during_trades is not None:
                during_trades()
            return [copy.deepcopy(trade)]

        transport = SimpleNamespace(
            get_account_uid=lambda: self.actual.fixture.venue.uid,
            get_order=get_order, get_symbol_assets=lambda **_params: ("BTC", "USDT"),
            get_my_trades=get_trades,
        )
        with patch.dict(os.environ, {"BUY_RECOVERY_TEST_KEY": "offline-key", "BUY_RECOVERY_TEST_SECRET": "offline-secret"}), \
                patch("app.integrations.exchanges.binance.orders.spot_user_data_admin_runtime.SpotUserDataTransport", return_value=transport), \
                patch.object(publication, "capture_spot_buy_recovery_binding", side_effect=captured_owner), \
                redirect_stdout(StringIO()) as output:
            code = admin.main([
                "recover-spot-market-fills", "--mode", "Live", "--account-type", "Spot",
                "--api-key-env", "BUY_RECOVERY_TEST_KEY", "--api-secret-env", "BUY_RECOVERY_TEST_SECRET",
            ])
        self.assertIn(queried, [["order"], ["order", "trades"]])
        self.assertEqual(1, len(self.actual.market_posts))
        self.assertEqual("recovery_required", json.loads(owner_marker_path(self.intent_path).read_text())["state"])
        return code, json.loads(output.getvalue())

    def _assert_unresolved(self):
        record = self.actual.wrapper._get_order_intent_record(self.client_id)
        if "primary_fill_signature" in record:
            self.assertEqual(self.primary["signature"], record["primary_fill_signature"])
        self.assertIsNot(record.get("portfolio_reconciled"), True)
        self.assertEqual(1, self.actual.wrapper.get_order_intent_status()["unresolved_count"])

    def _legacy_accepted_intent(self):
        current = ledger._read_ledger(self.intent_path, expected_binding=ledger._intent_binding(self.actual.wrapper))
        record = current["intents"][self.client_id]
        for field in ("primary_fill_receipt", "primary_fill_signature", "portfolio_qty"):
            record.pop(field, None)
        ledger._write_ledger(self.intent_path, current)
        self.assertEqual("accepted", self.actual.wrapper._get_order_intent_record(self.client_id)["state"])

    def test_conflicting_complete_primary_receipt_cannot_publish_missing_acquisition(self):
        variants = [
            ({"cummulativeQuoteQty": "3000"}, {"price": "30000", "quoteQty": "3000"}),
            ({"updateTime": self.trade["time"] + 1}, {"time": self.trade["time"] + 1}),
            ({}, {"commission": "0.0001"}),
            ({}, {"id": self.trade["id"] + 1}),
        ]
        for order_change, trade_change in variants:
            with self.subTest(order=order_change, trade=trade_change):
                code, result = self._run(order={**self.order, **order_change}, trade={**self.trade, **trade_change})
                self.assertEqual(1, code)
                self.assertFalse(result["ok"])
                self.assertFalse(self.path.exists(), "Conflicting BUY evidence was published before rejection")
                self._assert_unresolved()

    def test_same_signature_changed_quote_total_cannot_publish_or_restore_inventory(self):
        recovery.persist_spot_buy_allocation(self.path, self.primary)
        self.actual._sell("0.04")
        before = self.path.read_bytes()
        code, result = self._run(
            order={**self.order, "cummulativeQuoteQty": "3000"},
            trade={**self.trade, "quoteQty": "3000"},
        )
        self.assertEqual(1, code)
        self.assertFalse(result["ok"])
        self.assertEqual(before, self.path.read_bytes())
        self._assert_unresolved()

    def test_full_record_change_during_trade_query_blocks_first_publication(self):
        changed_bytes = []

        def replace_record():
            current = self.actual.wrapper._get_order_intent_record(self.client_id)
            ledger._update_order_intent_by_id(
                self.actual.wrapper, self.client_id, state=current["state"],
                expected_record=current, recovery_test_observation="newer-record",
            )
            changed_bytes.append(self.intent_path.read_bytes())

        code, result = self._run(during_trades=replace_record)
        self.assertEqual(1, code)
        self.assertFalse(result["ok"])
        self.assertFalse(self.path.exists())
        self.assertEqual(changed_bytes[-1], self.intent_path.read_bytes())
        self._assert_unresolved()

    def test_replaced_store_during_trade_query_blocks_first_publication(self):
        changed_bytes = []

        def replace_store():
            current = ledger._read_ledger(self.intent_path, expected_binding=ledger._intent_binding(self.actual.wrapper))
            current["store_id"] = str(uuid4())
            ledger._write_ledger(self.intent_path, current)
            changed_bytes.append(self.intent_path.read_bytes())

        code, result = self._run(during_trades=replace_store)
        self.assertEqual(1, code)
        self.assertFalse(result["ok"])
        self.assertFalse(self.path.exists())
        self.assertEqual(changed_bytes[-1], self.intent_path.read_bytes())
        self._assert_unresolved()

    def test_changed_account_binding_or_uid_during_trade_query_cannot_publish(self):
        for mutation in ("credential", "uid"):
            with self.subTest(mutation=mutation):
                changed_bytes = []

                def change_account():
                    if mutation == "credential":
                        self.admin_owner.api_key = "other-offline-account-key"
                    else:
                        self.admin_owner._operator_spot_account_uid += 1
                    changed_bytes.append(self.intent_path.read_bytes())

                code, result = self._run(during_trades=change_account)
                self.assertEqual(1, code)
                self.assertFalse(result["ok"])
                self.assertFalse(self.path.exists())
                self.assertEqual(changed_bytes[-1], self.intent_path.read_bytes())
                self._assert_unresolved()

    def test_exact_primary_receipt_publishes_once_and_marks_after_storage_locks_release(self):
        original_marker = ledger._mark_order_intent_portfolio_reconciled

        def unlocked_marker(owner, *args, **kwargs):
            # The actual marker acquires paired transactions itself. Nested locks
            # would fail the unchanged busy bound before this recovery completed.
            self.assertTrue(self.path.exists())
            return original_marker(owner, *args, **kwargs)

        with patch.object(ledger, "_mark_order_intent_portfolio_reconciled", side_effect=unlocked_marker):
            code, result = self._run()
        self.assertEqual(0, code, result)
        self.assertEqual(1, result["recovered_buy_fill_count"])
        self.assertEqual(0, result["unresolved_after"])
        row = json.loads(self.path.read_text())["entry_allocations"]["BTCUSDT:L"][0]
        self.assertEqual("2000", row["spot_fill_recovery"]["net_quote_cost"])
        self.assertTrue(self.actual.wrapper._get_order_intent_record(self.client_id)["portfolio_reconciled"])

    def test_actual_marker_failure_replays_acquisition_without_restoring_later_consumption(self):
        with patch.object(ledger, "_mark_order_intent_portfolio_reconciled", side_effect=OSError("offline marker disk failure")):
            code, result = self._run()
        self.assertEqual(1, code)
        self.assertEqual(1, result["failed_recovery_count"])
        self.assertTrue(self.path.exists())
        self._assert_unresolved()
        self.actual._sell("0.04")
        consumed = self.path.read_bytes()
        code, result = self._run()
        self.assertEqual(0, code, result)
        self.assertEqual(consumed, self.path.read_bytes())
        payload = json.loads(self.path.read_text())
        self.assertEqual(0.06, payload["open_position_records"]["BTCUSDT:L"]["data"]["qty"])
        self.assertTrue(self.actual.wrapper._get_order_intent_record(self.client_id)["portfolio_reconciled"])

    def test_legacy_accepted_fill_without_primary_receipt_replays_consumed_history_read_only(self):
        self._legacy_accepted_intent()
        recovery.persist_spot_buy_allocation(self.path, self.primary)
        self.actual._sell("0.04")
        before = self.path.read_bytes()
        code, result = self._run()
        self.assertEqual(0, code, result)
        self.assertEqual(before, self.path.read_bytes())
        self.assertEqual(0, result["unresolved_after"])
        self.assertTrue(self.actual.wrapper._get_order_intent_record(self.client_id)["portfolio_reconciled"])

    def test_legacy_accepted_fill_late_record_change_preserves_both_committed_files(self):
        self._legacy_accepted_intent()
        recovery.persist_spot_buy_allocation(self.path, self.primary)
        self.actual._sell("0.04")
        before = self.path.read_bytes()
        changed_bytes = []

        def replace_record():
            current = self.actual.wrapper._get_order_intent_record(self.client_id)
            ledger._update_order_intent_by_id(
                self.actual.wrapper, self.client_id, state=current["state"],
                expected_record=current, recovery_test_observation="newer-legacy-record",
            )
            changed_bytes.append(self.intent_path.read_bytes())

        code, result = self._run(during_trades=replace_record)
        self.assertEqual(1, code)
        self.assertFalse(result["ok"])
        self.assertEqual(before, self.path.read_bytes())
        self.assertEqual(changed_bytes[-1], self.intent_path.read_bytes())
        self._assert_unresolved()

    def test_paired_helper_detaches_caller_fill_before_canonical_validation(self):
        record = self.actual.wrapper._get_order_intent_record(self.client_id)
        fill = recovery.summarize_spot_market_fill(
            record, self.order, [self.trade], base_asset="BTC", quote_asset="USDT",
        )
        before = self.intent_path.read_bytes()
        canonical = publication.canonical_spot_buy_metadata

        def mutate_external_argument(argument):
            metadata = canonical(argument)
            # Simulate another owner of the caller's dictionary mutating it
            # after validation. The helper must use its detached proof throughout.
            fill.update(
                net_qty="0.09", base_fee_qty="0.01",
                commissions=[{"asset": "BTC", "amount": "0.01"}],
                average_cost=str(Decimal("2000") / Decimal("0.09")),
            )
            return metadata

        with owner_administration_lock(self.intent_path):
            binding = publication.capture_spot_buy_recovery_binding(self.actual.wrapper)
            with patch.object(publication, "canonical_spot_buy_metadata", side_effect=mutate_external_argument):
                self.assertTrue(publication.publish_spot_buy_recovery(
                    self.actual.wrapper, self.path, fill, expected_record=record,
                    expected_store_id=binding["store_id"], expected_binding=binding["binding"],
                    expected_intent_path=binding["intent_path"],
                ))
        self.assertEqual("0.09", fill["net_qty"])
        row = json.loads(self.path.read_text())["entry_allocations"]["BTCUSDT:L"][0]
        self.assertEqual(0.1, row["qty"])
        self.assertEqual(record["primary_fill_receipt"], row["spot_fill_recovery"])
        self.assertEqual(before, self.intent_path.read_bytes())
        self.assertEqual(1, len(self.actual.market_posts))
        self._assert_unresolved()

    def test_publication_written_marker_failed_replay_preserves_consumed_acquisition(self):
        for consumption in (None, "0.04", "0.1"):
            with self.subTest(consumption=consumption):
                scenario = type(self)()
                scenario.setUp()
                try:
                    recovery.persist_spot_buy_allocation(scenario.path, scenario.primary)
                    if consumption is not None:
                        scenario.actual._sell(consumption)
                    before = scenario.path.read_bytes()
                    code, result = scenario._run()
                    self.assertEqual(0, code, result)
                    self.assertEqual(before, scenario.path.read_bytes())
                    self.assertTrue(scenario.actual.wrapper._get_order_intent_record(scenario.client_id)["portfolio_reconciled"])
                    if consumption == "0.1":
                        payload = json.loads(scenario.path.read_text())
                        self.assertEqual("Closed", payload["entry_allocations"]["BTCUSDT:L"][0]["status"])
                        self.assertNotIn("BTCUSDT:L", payload["open_position_records"])
                finally:
                    scenario.doCleanups()


if __name__ == "__main__":
    unittest.main()
