from __future__ import annotations

import copy
import json
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock, patch

from app.integrations.exchanges.binance.orders import order_intent_runtime as ledger
from app.integrations.exchanges.binance.orders import spot_fill_recovery_runtime as spot_recovery
from app.integrations.exchanges.binance.orders.order_intent_provisioning import PROVISION_ACK, provision_order_intent_store
from app.settings.live_safety import LiveTradingSafetyError


class OrderIntentReconciliationSafetyTests(unittest.TestCase):
    def setUp(self):
        directory = self.enterContext(tempfile.TemporaryDirectory())
        self.owner = SimpleNamespace(_order_audit_log_path=Path(directory) / "audit.jsonl", api_key="unit-api-key", mode="Live")
        provision_order_intent_store(self.owner, acknowledgement=PROVISION_ACK)
        self.params = {
            "newClientOrderId": "reconcile-A", "symbol": "BTCUSDT", "side": "BUY",
            "type": "MARKET", "quantity": "1",
        }
        ledger._begin_order_intent(self.owner, self.params, market="futures", source="offline-test")
        ledger._mark_order_intent_unknown(self.owner, self.params, error="ambiguous acknowledgement")

    def response(self, **changes):
        return {
            "status": "FILLED", "clientOrderId": "reconcile-A", "symbol": "BTCUSDT",
            "side": "BUY", "origQty": "1", "orderId": 123, "executedQty": "1", **changes,
        }

    def reconcile(self, response):
        self.owner._query_order_intent_exchange = lambda _record: response
        return ledger.reconcile_order_intent(self.owner, "reconcile-A")

    def assert_unresolved(self, response):
        result = self.reconcile(response)
        self.assertFalse(result["reconciled"])
        self.assertEqual("unknown", result["state"])
        self.assertTrue(result["error"])
        self.assertEqual(1, ledger.get_order_intent_status(self.owner)["unresolved_count"])
        with self.assertRaisesRegex(LiveTradingSafetyError, "Unresolved exchange order intent"):
            ledger._begin_order_intent(
                self.owner, {**self.params, "newClientOrderId": "reconcile-B"},
                market="futures", source="offline-test",
            )

    def test_unknown_or_non_string_status_does_not_resolve_an_intent(self):
        for status in ("ERROR", "SUCCESS", "NOT_FOUND", "", None, True, 200, [], {}, "PENDING_NEW"):
            with self.subTest(status=status):
                self.assert_unresolved(self.response(status=status))

    def test_response_identity_must_match_the_persisted_order(self):
        for field, values in {
            "clientOrderId": (None, "", "reconcile-B", "RECONCILE-A", [], 123),
            "symbol": (None, "", "ETHUSDT", {}, 123),
            "orderId": (None, "", False, True, 0, -1, 1.5, "nan", "1e3", [], {}),
        }.items():
            for value in values:
                with self.subTest(field=field, value=value):
                    self.assert_unresolved(self.response(**{field: value}))

    def test_error_envelope_with_plausible_order_fields_is_not_confirmation(self):
        self.assert_unresolved(self.response(code=-2013, msg="Order does not exist"))

    def test_missing_response_or_not_found_query_preserves_block(self):
        for response in (None, [], {}, {"code": -2013, "msg": "Order does not exist"}):
            with self.subTest(response=response):
                self.assert_unresolved(response)
        self.owner._query_order_intent_exchange = lambda _record: (_ for _ in ()).throw(TimeoutError("offline"))
        result = ledger.reconcile_order_intent(self.owner, "reconcile-A")
        self.assertFalse(result["reconciled"])
        self.assertEqual("unknown", result["state"])

    def test_matching_confirmation_resolves_but_keeps_duplicate_id_blocked(self):
        result = self.reconcile(self.response(orderId="123"))
        self.assertTrue(result["reconciled"])
        self.assertEqual("accepted", result["state"])
        self.assertEqual("123", result["exchange_order_id"])
        self.assertEqual(0, ledger.get_order_intent_status(self.owner)["unresolved_count"])
        with self.assertRaisesRegex(LiveTradingSafetyError, "already has state accepted"):
            ledger._begin_order_intent(self.owner, self.params, market="futures", source="offline-test")
        ledger._begin_order_intent(
            self.owner, {**self.params, "newClientOrderId": "reconcile-B"},
            market="futures", source="offline-test",
        )

    def test_canceled_and_expired_orders_cannot_be_retried_under_the_same_id(self):
        for status in ("CANCELED", "EXPIRED", "EXPIRED_IN_MATCH"):
            with self.subTest(status=status):
                ledger._update_order_intent_by_id(self.owner, "reconcile-A", state="unknown")
                result = self.reconcile(self.response(status=status, executedQty="0.5"))
                self.assertTrue(result["reconciled"])
                self.assertEqual("accepted", result["state"])
                self.assertEqual(status, result["exchange_status"])
                with self.assertRaisesRegex(LiveTradingSafetyError, "already has state accepted"):
                    ledger._begin_order_intent(self.owner, self.params, market="futures", source="offline-test")

    def test_spot_market_positive_fill_remains_unresolved_until_portfolio_recovery(self):
        for status, executed in (
            ("CANCELED", "0.5"), ("EXPIRED", "0.5"),
            ("EXPIRED_IN_MATCH", "0.5"), ("FILLED", "1"),
        ):
            with self.subTest(status=status):
                ledger._update_order_intent_by_id(
                    self.owner, "reconcile-A", state="unknown", market="spot", type="MARKET",
                    executed_qty="0",
                )
                result = self.reconcile(self.response(status=status, executedQty=executed))
                self.assertTrue(result["reconciled"])
                self.assertEqual("unknown", result["state"])
                self.assertEqual(status, result["exchange_status"])
                self.assertEqual(1, ledger.get_order_intent_status(self.owner)["unresolved_count"])
                with self.assertRaisesRegex(LiveTradingSafetyError, "Unresolved exchange order intent"):
                    ledger._begin_order_intent(
                        self.owner, {**self.params, "newClientOrderId": "reconcile-B"},
                        market="spot", source="offline-test",
                    )

    def test_primary_spot_filled_ack_remains_unresolved_until_durable_portfolio_proof(self):
        ledger._update_order_intent_by_id(
            self.owner,
            "reconcile-A",
            state="accepted",
            market="spot",
            type="MARKET",
            side="BUY",
            exchange_status="FILLED",
            executed_qty="1",
            portfolio_reconciled=False,
        )

        self.assertEqual(1, ledger.get_order_intent_status(self.owner)["unresolved_count"])
        with self.assertRaisesRegex(LiveTradingSafetyError, "Unresolved exchange order intent"):
            ledger._begin_order_intent(
                self.owner,
                {**self.params, "newClientOrderId": "reconcile-B"},
                market="spot",
                source="offline-test",
            )

    def test_spot_market_terminal_order_with_zero_execution_resolves(self):
        ledger._update_order_intent_by_id(
            self.owner, "reconcile-A", state="unknown", market="spot", type="MARKET",
        )
        result = self.reconcile(self.response(status="CANCELED", executedQty="0"))
        self.assertTrue(result["reconciled"])
        self.assertEqual("accepted", result["state"])
        self.assertEqual(0, ledger.get_order_intent_status(self.owner)["unresolved_count"])
        ledger._begin_order_intent(
            self.owner, {**self.params, "newClientOrderId": "reconcile-B"},
            market="spot", source="offline-test",
        )

    def test_spot_sell_recovery_requires_and_accepts_durable_fee_aware_portfolio_proof(self):
        ledger._update_order_intent_by_id(
            self.owner,
            "reconcile-A",
            state="accepted",
            market="spot",
            type="MARKET",
            side="SELL",
            symbol="BTCUSDT",
            exchange_order_id="76",
            exchange_status="FILLED",
            executed_qty="0.08",
        )
        allocation_path = Path(self.owner._order_audit_log_path).with_name("allocations.json")
        buy_fill = {
            "symbol": "BTCUSDT", "client_order_id": "buy-alloc-1", "order_id": 75,
            "trade_ids": [101], "trade_count": 1, "gross_qty": "0.1", "net_qty": "0.1",
            "gross_quote_qty": "2000", "net_quote_cost": "2000", "average_cost": "20000",
            "commissions": [], "base_asset": "BTC", "quote_asset": "USDT",
            "fill_time_ms": 1780000000000, "signature": "a" * 64,
        }
        sell_fill = {
            "symbol": "BTCUSDT", "client_order_id": "reconcile-A", "side": "SELL",
            "order_id": 76, "trade_ids": [901], "trade_count": 1,
            "gross_qty": "0.08", "net_qty": "0.08003", "portfolio_qty": "0.08003",
            "gross_quote_qty": "1600", "base_fee_qty": "0.00003", "quote_fee_qty": "0.2",
            "net_quote_proceeds": "1599.8",
            "commissions": [
                {"asset": "BTC", "amount": "0.00003"},
                {"asset": "USDT", "amount": "0.2"},
            ],
            "base_asset": "BTC", "quote_asset": "USDT",
            "fill_time_ms": 1780000000010, "signature": "b" * 64,
        }
        with patch(
            "app.gui.shared.allocation_persistence.get_position_allocations_path",
            return_value=allocation_path,
        ):
            spot_recovery.persist_spot_buy_allocation(allocation_path, buy_fill)
            baseline = spot_recovery.spot_live_allocation_baseline(allocation_path, symbol="BTCUSDT")
            self.assertIsNotNone(baseline)
            ledger._update_order_intent_by_id(
                self.owner,
                "reconcile-A",
                state="accepted",
                portfolio_pre_order_signature=baseline["signature"],
                portfolio_pre_order_qty=baseline["quantity"],
            )
            sell_fill["pre_order_portfolio_signature"] = baseline["signature"]
            sell_fill["pre_order_portfolio_qty"] = baseline["quantity"]
            spot_recovery.persist_spot_sell_allocation(allocation_path, sell_fill)
            marked = ledger._mark_order_intent_portfolio_reconciled(
                self.owner, "reconcile-A", portfolio_signature="b" * 64,
                portfolio_quantity="0.08003",
            )
            saved_ledger = ledger._read_ledger(ledger._intent_path(self.owner))

        self.assertTrue(marked["portfolio_reconciled"])
        record = saved_ledger["intents"]["reconcile-A"]
        self.assertEqual("0.08003", record["portfolio_qty"])
        self.assertEqual("b" * 64, record["portfolio_recovery_signature"])
        saved_allocations = json.loads(allocation_path.read_text(encoding="utf-8"))
        self.assertAlmostEqual(
            0.01997,
            saved_allocations["open_position_records"]["BTCUSDT:L"]["data"]["qty"],
        )

    def primary_spot_buy(self):
        ledger._update_order_intent_by_id(
            self.owner, "reconcile-A", state="unknown", market="spot", type="MARKET",
        )
        self.owner.get_base_quote_assets = lambda _symbol: ("BTC", "USDT")
        response = self.response(
            type="MARKET", cummulativeQuoteQty="20000", transactTime=1780000000000,
            fills=[{"tradeId": 901, "price": "20000", "qty": "1",
                    "commission": "0.0004", "commissionAsset": "BTC"}],
        )
        ledger._mark_order_intent_accepted(self.owner, self.params, via="primary", result=response)
        record = ledger._get_order_intent_record(self.owner, "reconcile-A")
        self.assertIn("primary_fill_receipt", record)
        self.assertEqual("0.9996", record["primary_fill_receipt"]["net_qty"])
        return copy.deepcopy(record)

    def reconcile_primary_get(self, **changes):
        response = self.response(
            type="MARKET", cummulativeQuoteQty="20000", time=1779999999990,
            updateTime=1780000000020,
        )
        response.update(changes)
        getter = Mock(return_value=response)
        submitter = Mock(side_effect=AssertionError("Offline reconciliation must not submit orders"))
        self.owner.client = SimpleNamespace(get_order=getter, create_order=submitter)
        self.owner._query_order_intent_exchange = lambda record: ledger._query_order_intent_exchange(self.owner, record)
        with patch("socket.socket.connect", side_effect=AssertionError("Offline sockets forbidden")), patch(
            "socket.socket.connect_ex", side_effect=AssertionError("Offline sockets forbidden"),
        ):
            result = ledger.reconcile_order_intent(self.owner, "reconcile-A", include_execution=True)
        getter.assert_called_once_with(symbol="BTCUSDT", origClientOrderId="reconcile-A")
        submitter.assert_not_called()
        return result

    def test_primary_fill_rejects_contradictory_terminal_get_and_preserves_readable_ledger(self):
        for changes in (
            {"status": "CANCELED"}, {"status": "EXPIRED"}, {"status": "EXPIRED_IN_MATCH"},
            {"status": "PARTIALLY_FILLED"}, {"status": "NEW", "executedQty": "0"},
            {"status": "REJECTED", "executedQty": "0"},
            {"executedQty": "0.9996"}, {"executedQty": "1.0001"},
            {"orderId": 124}, {"clientOrderId": "reconcile-B"}, {"symbol": "ETHUSDT"},
            {"side": "SELL"}, {"type": "LIMIT"},
            {"cummulativeQuoteQty": "20001"}, {"cummulativeQuoteQty": "NaN"},
        ):
            with self.subTest(changes=changes):
                fixture = type(self)()
                fixture.setUp()
                try:
                    original = fixture.primary_spot_buy()
                    result = fixture.reconcile_primary_get(**changes)
                    self.assertFalse(result["reconciled"], result)
                    self.assertTrue(result["error"])
                    current = ledger._get_order_intent_record(fixture.owner, "reconcile-A")
                    for field in (
                        "primary_fill_receipt", "primary_fill_signature", "portfolio_qty",
                        "executed_qty", "exchange_status", "exchange_order_id",
                    ):
                        self.assertEqual(original[field], current[field], field)
                    self.assertIsNot(current.get("portfolio_reconciled"), True)
                    self.assertEqual(1, ledger.get_order_intent_status(fixture.owner)["unresolved_count"])
                    with self.assertRaisesRegex(LiveTradingSafetyError, "Unresolved exchange order intent"):
                        ledger._begin_order_intent(
                            fixture.owner, {**fixture.params, "newClientOrderId": "reconcile-B"},
                            market="spot", source="offline-test",
                        )
                finally:
                    fixture.doCleanups()

    def test_primary_fill_allows_compatible_get_without_replacing_acquisition_time(self):
        original = self.primary_spot_buy()
        result = self.reconcile_primary_get(executedQty="1.00000000", cummulativeQuoteQty="20000.00000000")
        self.assertTrue(result["reconciled"], result)
        self.assertEqual("unknown", result["state"])
        self.assertTrue(result["portfolio_reconciliation_required"])
        self.assertEqual(1780000000020, result["order_response"]["updateTime"])
        current = ledger._get_order_intent_record(self.owner, "reconcile-A")
        self.assertEqual(original["primary_fill_receipt"], current["primary_fill_receipt"])
        self.assertEqual(1780000000000, current["primary_fill_receipt"]["fill_time_ms"])
        self.assertEqual(1, ledger.get_order_intent_status(self.owner)["unresolved_count"])

    def test_rejected_response_requires_explicit_zero_execution(self):
        for executed in (None, "", "nan", "inf", "-1", "0.1", False, 0, 0.0, {}, []):
            with self.subTest(executed=executed):
                self.assert_unresolved(self.response(status="REJECTED", executedQty=executed))
        result = self.reconcile(self.response(status="REJECTED", executedQty="0.000"))
        self.assertTrue(result["reconciled"])
        self.assertEqual("rejected", result["state"])

    def test_documented_spot_pending_states_are_supported_only_for_spot(self):
        for status in ("PENDING_NEW", "PENDING_CANCEL"):
            with self.subTest(status=status):
                ledger._update_order_intent_by_id(
                    self.owner, "reconcile-A", state="unknown", market="spot", type="LIMIT",
                )
                result = self.reconcile(self.response(status=status, executedQty="0"))
                self.assertTrue(result["reconciled"])
                self.assertEqual("accepted", result["state"])

    def test_late_query_cannot_overwrite_a_newer_acceptance(self):
        for response in (None, self.response(status="ERROR"), self.response(status="REJECTED", executedQty="0")):
            with self.subTest(response=response):
                ledger._update_order_intent_by_id(self.owner, "reconcile-A", state="unknown")

                def query(_record):
                    ledger._mark_order_intent_accepted(self.owner, self.params, via="primary", result=self.response(orderId=456))
                    return response

                self.owner._query_order_intent_exchange = query
                result = ledger.reconcile_order_intent(self.owner, "reconcile-A")
                self.assertFalse(result["reconciled"])
                self.assertEqual("accepted", result["state"])
                record = ledger._get_order_intent_record(self.owner, "reconcile-A")
                self.assertEqual("456", record["exchange_order_id"])
                self.assertEqual("primary", record["last_via"])
                self.assertEqual(0, ledger.get_order_intent_status(self.owner)["unresolved_count"])

    def test_late_transport_error_cannot_restore_the_old_pending_state(self):
        def query(_record):
            ledger._mark_order_intent_accepted(self.owner, self.params, via="primary", result=self.response(orderId=456))
            raise TimeoutError("late query")

        self.owner._query_order_intent_exchange = query
        result = ledger.reconcile_order_intent(self.owner, "reconcile-A")
        self.assertFalse(result["reconciled"])
        self.assertEqual("accepted", result["state"])
        self.assertEqual("accepted", ledger._get_order_intent_record(self.owner, "reconcile-A")["state"])

    def test_transport_error_without_a_message_is_not_reported_as_reconciled(self):
        def query(_record):
            raise TimeoutError()

        self.owner._query_order_intent_exchange = query
        result = ledger.reconcile_order_intent(self.owner, "reconcile-A")
        self.assertFalse(result["reconciled"])
        self.assertTrue(result["error"])
        self.assertEqual(1, ledger.get_order_intent_status(self.owner)["unresolved_count"])

    def test_late_success_cannot_resolve_a_replacement_intent(self):
        def query(_record):
            ledger._update_order_intent_by_id(self.owner, "reconcile-A", state="rejected")
            ledger._begin_order_intent(self.owner, self.params, market="futures", source="replacement")
            return self.response()

        self.owner._query_order_intent_exchange = query
        result = ledger.reconcile_order_intent(self.owner, "reconcile-A")
        self.assertFalse(result["reconciled"])
        self.assertEqual("pending", result["state"])
        self.assertEqual(1, ledger.get_order_intent_status(self.owner)["unresolved_count"])
        self.assertEqual("replacement", ledger._get_order_intent_record(self.owner, "reconcile-A")["source"])


if __name__ == "__main__":
    unittest.main()
