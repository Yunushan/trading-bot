"""Actual admin BUY recovery validates durable evidence before publication."""
from __future__ import annotations

import copy
from contextlib import contextmanager, redirect_stdout
from decimal import Decimal
from io import StringIO
import json
import os
from types import MethodType, SimpleNamespace
import unittest
from unittest.mock import patch
from uuid import uuid4

import test_spot_buy_generation_faults as buy_fixture

from app.integrations.exchanges.binance.orders import order_intent_admin as admin
from app.integrations.exchanges.binance.orders import order_intent_runtime as ledger
from app.integrations.exchanges.binance.orders import spot_buy_admin_recovery_runtime as publication
from app.integrations.exchanges.binance.orders import spot_fill_recovery_runtime as recovery
from app.integrations.exchanges.binance.orders.order_intent_store import current_ledger_deadline, ledger_transactions
from app.integrations.exchanges.binance.orders import spot_user_data_admin_runtime as admin_transport
from app.integrations.exchanges.binance.orders.spot_inventory_namespace_runtime import namespace_for_current_ledger
from app.integrations.exchanges.binance.orders.spot_execution_owner import owner_administration_lock, owner_marker_path
from app.settings.live_safety import LiveTradingSafetyError


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
        self.inventory_namespace = dict(self.actual.namespace)
        self.initial_allocation_bytes = self.path.read_bytes()
        self.actual.wrapper._spot_execution_owner.close()

    @contextmanager
    def verified_admin_scope(self):
        """Use real signed account serialization and live administration exclusion."""
        transport = admin_transport.SpotUserDataTransport("offline-key", "offline-secret")
        # The actual fixture's patched GET verifies HMAC and returns only its fake UID.
        signed_uid = transport.get_account_uid()
        owner = SimpleNamespace(
            _order_audit_log_path=self.actual.fixture.audit_path, mode="Live", account_type="SPOT",
            api_key="offline-key", api_secret="offline-secret", client=transport,
            _enforce_spot_execution_owner=True, _operator_spot_account_uid=signed_uid,
        )
        owner._verified_spot_account_context = (owner.api_key, owner.api_secret, "live", transport, signed_uid)
        with owner_administration_lock(self.intent_path):
            owner._spot_inventory_administration_path = self.intent_path
            self.assertEqual(self.inventory_namespace, namespace_for_current_ledger(owner))
            yield owner

    def _publish_acquisition(self):
        """Prepare prior durable publication through genuine admin authority."""
        record = self.actual.wrapper._get_order_intent_record(self.client_id)
        fill = recovery.summarize_spot_market_fill(
            record, self.order, [self.trade], base_asset="BTC", quote_asset="USDT",
        )
        with self.verified_admin_scope() as administrator:
            binding = publication.capture_spot_buy_recovery_binding(administrator)
            self.assertTrue(publication.publish_spot_buy_recovery(
                administrator, self.path, fill, expected_record=record,
                expected_store_id=binding["store_id"], expected_binding=binding["binding"],
                expected_intent_path=binding["intent_path"],
            ))

    def _consume_acquisition(self, quantity):
        """Publish synthetic terminal SELL evidence under real admin exclusion."""
        with self.verified_admin_scope() as administrator:
            administrator._mark_order_intent_portfolio_reconciled = MethodType(
                ledger._mark_order_intent_portfolio_reconciled, administrator,
            )
            with patch.object(self.actual, "wrapper", administrator):
                self.actual._sell_under_authority(quantity)

    def _run(self, *, order=None, trade=None, during_trades=None, after_publication=None):
        order = copy.deepcopy(self.order if order is None else order)
        trade = copy.deepcopy(self.trade if trade is None else trade)
        queried = []
        capture_binding = publication.capture_spot_buy_recovery_binding
        publish_fill = publication.publish_spot_buy_recovery

        def captured_owner(owner):
            self.admin_owner = owner
            return capture_binding(owner)

        def published_fill(*args, **kwargs):
            result = publish_fill(*args, **kwargs)
            if after_publication is not None:
                after_publication()
            return result

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

        transport = admin_transport.SpotUserDataTransport("offline-key", "offline-secret")
        transport.get_order = get_order
        transport.get_symbol_assets = lambda **_params: ("BTC", "USDT")
        transport.get_my_trades = get_trades
        with patch.dict(os.environ, {"BUY_RECOVERY_TEST_KEY": "offline-key", "BUY_RECOVERY_TEST_SECRET": "offline-secret"}), \
                patch("app.integrations.exchanges.binance.orders.spot_user_data_admin_runtime.SpotUserDataTransport", return_value=transport), \
                patch.object(publication, "capture_spot_buy_recovery_binding", side_effect=captured_owner), \
                patch.object(publication, "publish_spot_buy_recovery", side_effect=published_fill), \
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
                self.assertEqual(self.initial_allocation_bytes, self.path.read_bytes(), "Conflicting BUY evidence changed the prebound empty source")
                self._assert_unresolved()

    def test_same_signature_changed_quote_total_cannot_publish_or_restore_inventory(self):
        self._publish_acquisition()
        self._consume_acquisition("0.04")
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
        self.assertEqual(self.initial_allocation_bytes, self.path.read_bytes())
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
        self.assertEqual(self.initial_allocation_bytes, self.path.read_bytes())
        self.assertEqual(changed_bytes[-1], self.intent_path.read_bytes())
        self._assert_unresolved()

    def test_replaced_store_after_publication_cannot_confirm_another_store(self):
        published_bytes, replaced_bytes = [], []
        replacement_store_id = str(uuid4())

        def replace_store():
            self.assertTrue(self.path.exists())
            published_bytes.append(self.path.read_bytes())
            current = ledger._read_ledger(self.intent_path, expected_binding=ledger._intent_binding(self.actual.wrapper))
            current["store_id"] = replacement_store_id
            ledger._write_ledger(self.intent_path, current)
            replaced_bytes.append(self.intent_path.read_bytes())

        code, result = self._run(after_publication=replace_store)
        self.assertEqual(1, code, result)
        self.assertFalse(result["ok"])
        self.assertEqual(published_bytes[-1], self.path.read_bytes())
        self.assertEqual(replaced_bytes[-1], self.intent_path.read_bytes())
        self.assertEqual(replacement_store_id, ledger._read_ledger(self.intent_path)["store_id"])
        self._assert_unresolved()

    def test_full_record_change_after_publication_cannot_confirm_newer_record(self):
        published_bytes, replaced_bytes = [], []

        def replace_record():
            published_bytes.append(self.path.read_bytes())
            current = self.actual.wrapper._get_order_intent_record(self.client_id)
            ledger._update_order_intent_by_id(
                self.actual.wrapper, self.client_id, state=current["state"], expected_record=current,
                recovery_test_observation="changed-after-publication",
            )
            replaced_bytes.append(self.intent_path.read_bytes())

        code, result = self._run(after_publication=replace_record)
        self.assertEqual(1, code, result)
        self.assertFalse(result["ok"])
        self.assertEqual(published_bytes[-1], self.path.read_bytes())
        self.assertEqual(replaced_bytes[-1], self.intent_path.read_bytes())
        self._assert_unresolved()

    def test_account_binding_or_path_change_after_publication_preserves_exact_old_work(self):
        for mutation in ("credential", "uid"):
            with self.subTest(mutation=mutation):
                published_bytes, original_bytes = [], []

                def change_account():
                    published_bytes.append(self.path.read_bytes())
                    original_bytes.append(self.intent_path.read_bytes())
                    if mutation == "credential":
                        self.admin_owner.api_key = "other-offline-account-key"
                    else:
                        self.admin_owner._operator_spot_account_uid += 1

                code, result = self._run(after_publication=change_account)
                self.assertEqual(1, code, result)
                self.assertFalse(result["ok"])
                self.assertEqual(published_bytes[-1], self.path.read_bytes())
                self.assertEqual(original_bytes[-1], self.intent_path.read_bytes())
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
                self.assertEqual(self.initial_allocation_bytes, self.path.read_bytes())
                self.assertEqual(changed_bytes[-1], self.intent_path.read_bytes())
                self._assert_unresolved()

    def test_exact_primary_receipt_publishes_once_and_marks_after_storage_locks_release(self):
        original_marker = publication.confirm_spot_buy_recovery

        def unlocked_marker(owner, *args, **kwargs):
            # Actual lock reuse must not make this release assertion vacuous.
            self.assertTrue(self.path.exists())
            with self.assertRaisesRegex(LiveTradingSafetyError, "transaction is required"):
                current_ledger_deadline(self.intent_path, self.path)
            with ledger_transactions(self.intent_path, self.path):
                pass
            return original_marker(owner, *args, **kwargs)

        with patch.object(publication, "confirm_spot_buy_recovery", side_effect=unlocked_marker):
            code, result = self._run()
        self.assertEqual(0, code, result)
        self.assertEqual(1, result["recovered_buy_fill_count"])
        self.assertEqual(0, result["unresolved_after"])
        row = json.loads(self.path.read_text())["entry_allocations"]["BTCUSDT:L"][0]
        self.assertEqual("2000", row["spot_fill_recovery"]["net_quote_cost"])
        self.assertTrue(self.actual.wrapper._get_order_intent_record(self.client_id)["portfolio_reconciled"])

    def test_actual_marker_failure_replays_acquisition_without_restoring_later_consumption(self):
        for consumption in (None, "0.04", "0.1"):
            with self.subTest(consumption=consumption):
                scenario = type(self)()
                scenario.setUp()
                try:
                    with patch.object(publication, "confirm_spot_buy_recovery", side_effect=OSError("offline marker disk failure")):
                        code, result = scenario._run()
                    self.assertEqual(1, code)
                    self.assertEqual(1, result["failed_recovery_count"])
                    self.assertTrue(scenario.path.exists())
                    scenario._assert_unresolved()
                    if consumption is not None:
                        scenario._consume_acquisition(consumption)
                    consumed = scenario.path.read_bytes()
                    code, result = scenario._run()
                    self.assertEqual(0, code, result)
                    self.assertEqual(consumed, scenario.path.read_bytes())
                    payload = json.loads(scenario.path.read_text())
                    if consumption == "0.1":
                        self.assertEqual("Closed", payload["entry_allocations"]["BTCUSDT:L"][0]["status"])
                        self.assertNotIn("BTCUSDT:L", payload["open_position_records"])
                    else:
                        expected_qty = 0.1 - float(consumption or 0)
                        self.assertAlmostEqual(expected_qty, payload["open_position_records"]["BTCUSDT:L"]["data"]["qty"])
                    self.assertTrue(scenario.actual.wrapper._get_order_intent_record(scenario.client_id)["portfolio_reconciled"])
                finally:
                    scenario.doCleanups()

    def test_legacy_accepted_fill_without_primary_receipt_replays_consumed_history_read_only(self):
        self._legacy_accepted_intent()
        self._publish_acquisition()
        self._consume_acquisition("0.04")
        before = self.path.read_bytes()
        code, result = self._run()
        self.assertEqual(0, code, result)
        self.assertEqual(before, self.path.read_bytes())
        self.assertEqual(0, result["unresolved_after"])
        self.assertTrue(self.actual.wrapper._get_order_intent_record(self.client_id)["portfolio_reconciled"])

    def test_legacy_accepted_fill_late_record_change_preserves_both_committed_files(self):
        self._legacy_accepted_intent()
        self._publish_acquisition()
        self._consume_acquisition("0.04")
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

        with self.verified_admin_scope() as administrator:
            binding = publication.capture_spot_buy_recovery_binding(administrator)
            with patch.object(publication, "canonical_spot_buy_metadata", side_effect=mutate_external_argument):
                self.assertTrue(publication.publish_spot_buy_recovery(
                    administrator, self.path, fill, expected_record=record,
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
                    scenario._publish_acquisition()
                    if consumption is not None:
                        scenario._consume_acquisition(consumption)
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

    def test_confirm_complete_primary_conflict_after_publication_preserves_both_files(self):
        record = self.actual.wrapper._get_order_intent_record(self.client_id)
        fill = recovery.summarize_spot_market_fill(record, self.order, [self.trade], base_asset="BTC", quote_asset="USDT")
        with self.verified_admin_scope() as administrator:
            binding = publication.capture_spot_buy_recovery_binding(administrator)
            options = {
                "expected_record": record, "expected_store_id": binding["store_id"],
                "expected_binding": binding["binding"], "expected_intent_path": binding["intent_path"],
            }
            self.assertTrue(publication.publish_spot_buy_recovery(administrator, self.path, fill, **options))
            allocation_bytes, ledger_bytes = self.path.read_bytes(), self.intent_path.read_bytes()
            fill.update(gross_quote_qty="3000", net_quote_cost="3000", average_cost="30000")
            with self.assertRaisesRegex(LiveTradingSafetyError, "complete primary receipt"):
                publication.confirm_spot_buy_recovery(administrator, self.path, fill, **options)
        self.assertEqual(allocation_bytes, self.path.read_bytes())
        self.assertEqual(ledger_bytes, self.intent_path.read_bytes())
        self._assert_unresolved()

    def test_already_confirmed_acquisition_is_read_only_after_partial_and_closed_consumption(self):
        for consumption in ("0.04", "0.1"):
            with self.subTest(consumption=consumption):
                scenario = type(self)()
                scenario.setUp()
                try:
                    code, result = scenario._run()
                    self.assertEqual(0, code, result)
                    scenario._consume_acquisition(consumption)
                    allocation_bytes, ledger_bytes = scenario.path.read_bytes(), scenario.intent_path.read_bytes()
                    record = scenario.actual.wrapper._get_order_intent_record(scenario.client_id)
                    with scenario.verified_admin_scope() as administrator:
                        binding = publication.capture_spot_buy_recovery_binding(administrator)
                        confirmed = publication.confirm_spot_buy_recovery(
                            administrator, scenario.path,
                            {**scenario.primary, "portfolio_qty": scenario.primary["net_qty"]}, expected_record=record,
                            expected_store_id=binding["store_id"], expected_binding=binding["binding"],
                            expected_intent_path=binding["intent_path"],
                        )
                    self.assertTrue(confirmed["already_reconciled"])
                    self.assertEqual(allocation_bytes, scenario.path.read_bytes())
                    self.assertEqual(ledger_bytes, scenario.intent_path.read_bytes())
                finally:
                    scenario.doCleanups()

    def test_legacy_both_phases_keep_the_original_fill_when_publisher_argument_changes(self):
        self._legacy_accepted_intent()
        publisher = publication.publish_spot_buy_recovery

        def mutate_after_publish(owner, path, fill, **kwargs):
            result = publisher(owner, path, fill, **kwargs)
            fill.update(
                net_qty="0.09", portfolio_qty="0.09", base_fee_qty="0.01",
                commissions=[{"asset": "BTC", "amount": "0.01"}],
                average_cost=str(Decimal("2000") / Decimal("0.09")),
            )
            return result

        with patch.object(publication, "publish_spot_buy_recovery", side_effect=mutate_after_publish):
            code, result = self._run()
        self.assertEqual(0, code, result)
        row = json.loads(self.path.read_text())["entry_allocations"]["BTCUSDT:L"][0]
        self.assertEqual("0.1", row["spot_fill_recovery"]["net_qty"])
        self.assertEqual("0.1", self.actual.wrapper._get_order_intent_record(self.client_id)["portfolio_qty"])


if __name__ == "__main__":
    unittest.main()
