"""Real submission/intent/bulk-close integration with an offline exchange."""
from __future__ import annotations

import copy
import socket
import threading
import unittest
from unittest.mock import Mock, patch

from app.integrations.exchanges.binance.orders import order_intent_runtime as intents
from app.integrations.exchanges.binance.orders.order_close_confirmation_runtime import CLOSE_QUERY_ATTEMPTS
from app.integrations.exchanges.binance.positions.close_all_runtime import close_all_futures_positions
from app.settings.live_safety import LiveTradingSafetyError
from test_binance_package_split_smoke import _GuardedFuturesAuditWrapper, _live_ack_config


CLOSE = {"symbol": "ETHUSDT", "side": "SELL", "type": "MARKET", "quantity": "0.1", "positionSide": "LONG"}


class MarketCloseReconciliationTests(unittest.TestCase):
    def setUp(self):
        self.enterContext(patch.object(socket.socket, "connect", side_effect=AssertionError("Network forbidden")))
        self.enterContext(patch.dict("os.environ", {}, clear=True))
        self.enterContext(patch(
            "app.integrations.exchanges.binance.orders.order_close_confirmation_runtime.CLOSE_QUERY_INTERVAL_SECONDS", 0,
        ))

    def exchange(self, *, initial="ack", query_change=None, mode="Live"):
        wrapper = _GuardedFuturesAuditWrapper(mode=mode, live_safety_config=_live_ack_config(live_trading_max_session_orders=1))
        self.addCleanup(wrapper.close)
        wrapper._testnet_order_fallback_client = Mock(side_effect=AssertionError("Uncertain close resubmitted"))
        positions = [
            {"symbol": "ETHUSDT", "positionSide": "LONG", "positionAmt": "0.1"},
            {"symbol": "ETHUSDT", "positionSide": "SHORT", "positionAmt": "-0.1"},
        ]
        receipts = {}
        queries = []
        lock = threading.Lock()

        def position_snapshot(**kwargs):
            with lock:
                return copy.deepcopy(positions)

        def apply_execution(receipt):
            for position in list(positions):
                if position["positionSide"] != receipt["positionSide"]:
                    continue
                remaining = float(receipt["origQty"]) - float(receipt["executedQty"])
                if remaining <= 0:
                    positions.remove(position)
                else:
                    position["positionAmt"] = str(remaining if position["positionSide"] == "LONG" else -remaining)

        def submit(**params):
            with lock:
                self.assertEqual("RESULT", params["newOrderRespType"])
                wrapper.client.orders.append(dict(params))
                receipt = {**params, "clientOrderId": params["newClientOrderId"],
                           "orderId": len(wrapper.client.orders), "origQty": params["quantity"],
                           "executedQty": params["quantity"], "status": "FILLED"}
                receipts[params["newClientOrderId"]] = receipt
                if initial == "filled":
                    apply_execution(receipt)
                    return dict(receipt)
                if initial == "timeout":
                    raise TimeoutError("response lost after submission")
                if initial == "malformed":
                    return {"orderId": receipt["orderId"], "status": "FILLED"}
                if initial == "partial":
                    partial = dict(receipt, status="PARTIALLY_FILLED", executedQty="0.05")
                    apply_execution(partial)
                    return partial
                return dict(receipt, status="NEW", executedQty="0")

        def query(method, path, params, **kwargs):
            with lock:
                self.assertEqual(("GET", "/v1/order"), (method, path))
                client_id = params["origClientOrderId"]
                self.assertIn(client_id, receipts)
                queries.append(client_id)
                receipt = dict(receipts[client_id])
                if query_change:
                    receipt = query_change(receipt, len(queries))
                if receipt.get("status") == "FILLED" and receipt.get("side") == receipts[client_id]["side"]:
                    apply_execution(receipts[client_id])
                return receipt

        wrapper.client.futures_create_order = submit
        wrapper.client.futures_get_position_mode = lambda: {"dualSidePosition": True}
        wrapper.client.futures_position_information = position_snapshot
        wrapper.client.futures_cancel_all_open_orders = lambda **kwargs: {"code": 200}
        wrapper._futures_api_prefix = lambda: "fapi"
        wrapper._http_signed_futures_request = query
        return wrapper, positions, queries

    def test_bulk_close_confirms_both_hedge_legs_even_with_exhausted_entry_budget(self):
        for initial in ("filled", "ack", "partial", "timeout", "malformed"):
            for fast in (False, True):
                with self.subTest(initial=initial, fast=fast):
                    wrapper, positions, queries = self.exchange(initial=initial)
                    wrapper._live_order_submit_attempt_count = 1
                    results = close_all_futures_positions(wrapper, fast=fast, max_workers=2)
                    self.assertEqual([], positions)
                    self.assertEqual(2, len(wrapper.client.orders))
                    self.assertTrue(results)
                    self.assertTrue(all(result["ok"] for result in results), results)
                    self.assertEqual(1, wrapper._live_order_submit_attempt_count)
                    self.assertEqual(0, wrapper.get_order_intent_status()["unresolved_count"])
                    self.assertEqual(0 if initial == "filled" else 2, len(queries))
                    wrapper._testnet_order_fallback_client.assert_not_called()

    def test_ack_query_is_bounded_and_preserves_submission_barrier(self):
        wrapper, _positions, queries = self.exchange(query_change=lambda response, _: dict(response, status="NEW", executedQty="0"))
        result, _via = wrapper._futures_create_order_with_fallback(CLOSE)
        self.assertEqual("NEW", result["status"])
        self.assertEqual(CLOSE_QUERY_ATTEMPTS, len(queries))
        self.assertEqual(1, len(wrapper.client.orders))
        self.assertEqual(1, wrapper.get_order_intent_status()["unresolved_count"])
        with self.assertRaisesRegex(LiveTradingSafetyError, "Unresolved exchange order intent"):
            wrapper._futures_create_order_with_fallback(dict(CLOSE, side="BUY", positionSide="SHORT"))
        self.assertEqual(1, len(wrapper.client.orders))

    def test_wrong_query_identity_never_releases_a_close(self):
        for field, value in (("clientOrderId", "wrong"), ("symbol", "BTCUSDT"), ("side", "BUY"),
                             ("positionSide", "SHORT"), ("positionSide", None), ("orderId", 999), ("origQty", "2")):
            with self.subTest(field=field):
                wrapper, _positions, queries = self.exchange(query_change=lambda response, _: dict(response, **{field: value}))
                result, _via = wrapper._futures_create_order_with_fallback(CLOSE)
                self.assertEqual("NEW", result["status"])
                self.assertEqual(1, wrapper.get_order_intent_status()["unresolved_count"])
                self.assertEqual(CLOSE_QUERY_ATTEMPTS, len(queries))
                self.assertEqual(1, len(wrapper.client.orders))

    def test_partial_fill_never_regresses_on_late_or_malformed_queries(self):
        for status, qty in (("PARTIALLY_FILLED", "0.01"), ("NEW", "0"), ("FILLED", "nan"), ("REJECTED", "0")):
            with self.subTest(status=status, qty=qty):
                wrapper, _positions, _queries = self.exchange(
                    initial="partial", query_change=lambda response, _: dict(response, status=status, executedQty=qty),
                )
                result, _via = wrapper._futures_create_order_with_fallback(CLOSE)
                self.assertEqual("0.05", result["executedQty"])
                record = intents._get_order_intent_record(wrapper, result["clientOrderId"])
                self.assertEqual("0.05", record["executed_qty"])
                self.assertEqual("unknown", record["state"])

    def test_transport_failure_never_falls_back_to_another_post_on_testnet(self):
        def fail_query(response, count):
            raise TimeoutError("query unavailable")

        wrapper, _positions, queries = self.exchange(initial="timeout", query_change=fail_query, mode="Testnet")
        with self.assertRaisesRegex(RuntimeError, "remains unconfirmed"):
            wrapper._futures_create_order_with_fallback(CLOSE)
        self.assertEqual(1, len(wrapper.client.orders))
        self.assertEqual(CLOSE_QUERY_ATTEMPTS, len(queries))
        self.assertEqual(1, wrapper.get_order_intent_status()["unresolved_count"])
        wrapper._testnet_order_fallback_client.assert_not_called()

    def test_query_terminal_partial_fill_keeps_confirmed_quantity_and_duplicate_barrier(self):
        wrapper, _positions, _queries = self.exchange(
            initial="partial", query_change=lambda response, _: dict(response, status="CANCELED", executedQty="0.05"),
        )
        result, via = wrapper._futures_create_order_with_fallback(CLOSE)
        self.assertEqual("primary-reconciled", via)
        self.assertEqual(("CANCELED", "0.05"), (result["status"], result["executedQty"]))
        self.assertEqual(0, wrapper.get_order_intent_status()["unresolved_count"])
        with self.assertRaisesRegex(LiveTradingSafetyError, "already has state accepted"):
            wrapper._futures_create_order_with_fallback(dict(CLOSE, newClientOrderId=result["clientOrderId"]))
        self.assertEqual(1, len(wrapper.client.orders))

    def test_late_fill_after_an_unfinished_query_is_applied_without_a_second_submission(self):
        wrapper, _positions, queries = self.exchange(
            query_change=lambda response, count: dict(response, status="NEW", executedQty="0") if count == 1 else response,
        )
        result, via = wrapper._futures_create_order_with_fallback(CLOSE)
        self.assertEqual("FILLED", result["status"])
        self.assertEqual("primary-reconciled", via)
        self.assertEqual(2, len(queries))
        self.assertEqual(1, len(wrapper.client.orders))

    def test_late_primary_response_cannot_overwrite_a_newer_ledger_observation(self):
        wrapper, _positions, _queries = self.exchange(initial="filled")
        params = dict(CLOSE, newClientOrderId="late-primary")
        intents._begin_order_intent(wrapper, params, market="futures", source="offline-test")
        response = dict(params, clientOrderId="late-primary", orderId=1, status="NEW", executedQty="0")
        validate = intents._validate_reconciliation_response

        def observe_fill_during_validation(record, result):
            validated = validate(record, result)
            intents._update_order_intent_by_id(
                wrapper, "late-primary", state="accepted", exchange_order_id="1",
                exchange_status="FILLED", executed_qty="0.1",
            )
            return validated

        with patch.object(intents, "_validate_reconciliation_response", side_effect=observe_fill_during_validation):
            with self.assertRaisesRegex(LiveTradingSafetyError, "changed during confirmation"):
                intents._mark_order_intent_accepted(wrapper, params, via="primary", result=response)
        record = intents._get_order_intent_record(wrapper, "late-primary")
        self.assertEqual(("accepted", "FILLED", "0.1"),
                         (record["state"], record["exchange_status"], record["executed_qty"]))
        self.assertEqual([], wrapper.client.orders)


if __name__ == "__main__":
    unittest.main()
