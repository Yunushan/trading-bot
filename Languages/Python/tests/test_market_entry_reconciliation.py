"""Real futures market submission and durable reconciliation, with no network."""
from __future__ import annotations

import socket
import tempfile
import unittest
from types import SimpleNamespace
from unittest.mock import Mock, patch

from app.integrations.exchanges.binance.orders import order_intent_runtime as intents
from app.integrations.exchanges.binance.orders.futures_orders import (
    _market_execution_result, _place_futures_market_order_FLEX, _place_futures_market_order_STRICT,
    place_futures_market_order,
)
from app.integrations.exchanges.binance.orders.order_close_confirmation_runtime import CLOSE_QUERY_ATTEMPTS
from app.settings.live_safety import LiveTradingSafetyError
from test_confirmed_close_execution import OfflineCloseExchange
from test_binance_package_split_smoke import _FlexFuturesOrderWrapper
from test_strategy_order_result_hardening import GUARD_KEY, _build_engine, _result_kwargs


ENTRY = {"symbol": "BTCUSDT", "side": "BUY", "type": "MARKET", "quantity": "1"}


class OfflineTestnetExchange(OfflineCloseExchange):
    mode = "Demo/Testnet"


class MarketEntryReconciliationTests(unittest.TestCase):
    def setUp(self):
        self.enterContext(patch.object(socket.socket, "connect", side_effect=AssertionError("Network forbidden")))
        self.enterContext(patch(
            "app.integrations.exchanges.binance.orders.order_close_confirmation_runtime.CLOSE_QUERY_INTERVAL_SECONDS", 0,
        ))
        directory = self.enterContext(tempfile.TemporaryDirectory())
        self.exchange = OfflineCloseExchange(directory)
        self.exchange.mode = "Live"
        self.exchange._testnet_order_fallback_client = Mock(side_effect=AssertionError("Second POST forbidden"))
        self.queries = []

    def receipt(self, *, status="FILLED", executed="1"):
        params = self.exchange.sent[0]
        return {"symbol": params["symbol"], "side": params["side"], "status": status,
                "clientOrderId": params["newClientOrderId"], "orderId": 1234,
                "origQty": params["quantity"], "executedQty": executed, "avgPrice": "100"}

    def query(self, transform=lambda receipt: receipt):
        def receive(record):
            self.queries.append(dict(record))
            self.assertEqual(self.exchange.sent[0]["newClientOrderId"], record["client_order_id"])
            return transform(self.receipt())
        self.exchange._query_order_intent_exchange = receive

    def test_pending_market_entry_stays_blocked_after_restart(self):
        self.exchange.status = "NEW"
        self.exchange.executed_qty = "0"
        self.query(lambda result: dict(result, status="NEW", executedQty="0"))
        response, _via = self.exchange._futures_create_order_with_fallback(ENTRY)
        self.assertEqual("RESULT", self.exchange.sent[0]["newOrderRespType"])
        self.assertEqual(CLOSE_QUERY_ATTEMPTS, len(self.queries))
        outcome = _market_execution_result(response, "1")
        self.assertFalse(outcome["ok"])
        self.assertEqual(0.0, outcome["executed_qty"])
        restarted = SimpleNamespace(api_key=self.exchange.api_key, mode=self.exchange.mode,
                                    _order_audit_log_path=self.exchange._order_audit_log_path)
        self.assertEqual(1, intents.get_order_intent_status(restarted)["unresolved_count"])
        with self.assertRaisesRegex(LiveTradingSafetyError, "Unresolved"):
            intents._begin_order_intent(restarted, dict(ENTRY, newClientOrderId="another-entry"),
                                       market="futures", source="restart")
        self.assertEqual(1, len(self.exchange.sent))
        self.exchange._testnet_order_fallback_client.assert_not_called()

    def test_partial_market_entry_keeps_executed_quantity_and_unfilled_remainder(self):
        self.exchange.status = "PARTIALLY_FILLED"
        self.exchange.executed_qty = "0.25"
        self.query(lambda result: dict(result, status="PARTIALLY_FILLED", executedQty="0.25"))
        response, _via = self.exchange._futures_create_order_with_fallback(ENTRY)
        outcome = {**_market_execution_result(response, "1"), "info": response}
        engine = _build_engine()
        self.addCleanup(type(engine)._GLOBAL_PAUSE.clear)
        accepted, qty = engine._handle_futures_signal_order_result(**_result_kwargs(outcome))
        self.assertTrue(accepted)
        self.assertFalse(outcome["ok"])
        self.assertEqual(0.25, qty)
        self.assertEqual(0.25, engine._leg_ledger[GUARD_KEY]["entries"][0]["qty"])
        self.assertTrue(type(engine)._GLOBAL_PAUSE.is_set())
        record = intents._get_order_intent_record(self.exchange, response["clientOrderId"])
        self.assertEqual(("unknown", "1", "0.25"), (record["state"], record["quantity"], record["executed_qty"]))

    def test_lost_market_response_is_queried_not_resubmitted(self):
        self.exchange.submit_error = TimeoutError("response lost after exchange fill")
        self.query()
        response, via = self.exchange._futures_create_order_with_fallback(ENTRY)
        self.assertEqual("primary-reconciled", via)
        self.assertTrue(_market_execution_result(response, "1")["ok"])
        self.assertEqual(1, len(self.exchange.sent))
        self.assertEqual(1, len(self.queries))
        self.assertEqual(0, intents.get_order_intent_status(self.exchange)["unresolved_count"])
        self.exchange._testnet_order_fallback_client.assert_not_called()

    def test_wrong_query_identity_cannot_release_pending_entry(self):
        self.exchange.status = "NEW"
        self.exchange.executed_qty = "0"
        self.query(lambda result: dict(result, side="SELL"))
        response, _via = self.exchange._futures_create_order_with_fallback(ENTRY)
        self.assertEqual("NEW", response["status"])
        self.assertEqual(1, intents.get_order_intent_status(self.exchange)["unresolved_count"])

    def test_pre_upgrade_accepted_market_ack_requires_execution_reconciliation(self):
        params = dict(ENTRY, newClientOrderId="legacy-accepted-entry")
        intents._begin_order_intent(self.exchange, params, market="futures", source="legacy")
        intents._update_order_intent(self.exchange, params, state="accepted", exchange_status="FILLED")
        self.assertEqual(1, intents.get_order_intent_status(self.exchange)["unresolved_count"])
        self.exchange.sent.append(params)
        self.query()
        result = intents.reconcile_order_intent(self.exchange, params["newClientOrderId"], include_execution=True)
        self.assertTrue(result["reconciled"])
        self.assertEqual("1", result["order_response"]["executedQty"])
        self.assertEqual(0, intents.get_order_intent_status(self.exchange)["unresolved_count"])

    def test_terminal_partial_execution_is_preserved_without_a_pending_remainder(self):
        self.exchange.status = "EXPIRED"
        self.exchange.executed_qty = "0.25"
        response, _via = self.exchange._futures_create_order_with_fallback(ENTRY)
        result = _market_execution_result(response, "1")
        self.assertFalse(result["ok"])
        self.assertFalse(result["reconciliation_required"])
        self.assertEqual(0.25, result["executed_qty"])
        self.assertEqual(0, intents.get_order_intent_status(self.exchange)["unresolved_count"])

    def test_testnet_lost_response_never_uses_a_second_post(self):
        self.exchange = OfflineTestnetExchange(self.enterContext(tempfile.TemporaryDirectory()))
        self.exchange.submit_error = TimeoutError("response lost after fill")
        self.exchange._testnet_order_fallback_client = Mock(side_effect=AssertionError("Second POST forbidden"))
        self.query(lambda result: {"code": -2013, "msg": "Order does not exist"})
        with self.assertRaisesRegex(LiveTradingSafetyError, "unconfirmed"):
            self.exchange._futures_create_order_with_fallback(ENTRY)
        self.assertEqual(1, len(self.exchange.sent))
        self.assertEqual(CLOSE_QUERY_ATTEMPTS, len(self.queries))
        self.assertEqual(1, intents.get_order_intent_status(self.exchange)["unresolved_count"])
        self.exchange._testnet_order_fallback_client.assert_not_called()

    def test_all_futures_sizers_report_execution_not_order_acceptance(self):
        for place in (place_futures_market_order, _place_futures_market_order_STRICT, _place_futures_market_order_FLEX):
            for status, filled, pending in (("NEW", "0", True), ("PARTIALLY_FILLED", "0.025", True),
                                            ("FILLED", "0.1", False), ("EXPIRED", "0.025", False)):
                with self.subTest(sizer=place.__name__, status=status):
                    wrapper = _FlexFuturesOrderWrapper()
                    wrapper._ensure_symbol_margin = Mock()
                    wrapper.ensure_futures_settings = Mock()
                    wrapper._log = Mock()
                    wrapper._futures_create_order_with_fallback = Mock(return_value=({
                        "orderId": 123, "status": status, "origQty": "0.1", "executedQty": filled,
                    }, "primary"))
                    result = place(wrapper, "BTCUSDT", "BUY", quantity=0.1, price=100.0)
                    self.assertEqual(status == "FILLED", result["ok"], result)
                    self.assertTrue(result["execution_confirmed"], result)
                    self.assertEqual(float(filled), result["executed_qty"])
                    self.assertEqual(pending, result["reconciliation_required"])
                    self.assertEqual("0.100", result["submitted_qty"])
                    wrapper._futures_create_order_with_fallback.assert_called_once()


if __name__ == "__main__":
    unittest.main()
