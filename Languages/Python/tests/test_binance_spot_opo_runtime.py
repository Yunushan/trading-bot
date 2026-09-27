from __future__ import annotations

import unittest

from app.integrations.exchanges.binance.orders.spot_opo_runtime import (
    build_spot_opo_cancel_replace_request,
    build_spot_opo_request,
    build_spot_opo_residual_stop_request,
    validate_spot_opo_acknowledgement,
    validate_spot_opo_cancel_replace_request,
    validate_spot_opo_cancel_replace_response,
    validate_spot_opo_strategy_exit_order,
    validate_spot_opo_residual_stop_order,
)
from app.settings.live_safety import LiveTradingSafetyError


def _symbol_info() -> dict[str, object]:
    return {
        "symbol": "BTCUSDT",
        "status": "TRADING",
        "quoteAsset": "USDT",
        "isSpotTradingAllowed": True,
        "otoAllowed": True,
        "opoAllowed": True,
        "filters": [
            {"filterType": "PRICE_FILTER", "minPrice": "0.01", "maxPrice": "1000000", "tickSize": "0.01"},
            {"filterType": "LOT_SIZE", "minQty": "0.0001", "maxQty": "9000", "stepSize": "0.0001"},
            {"filterType": "MIN_NOTIONAL", "minNotional": "5"},
        ],
    }


def _request() -> dict[str, str]:
    return build_spot_opo_request(
        symbol="BTCUSDT",
        symbol_info=_symbol_info(),
        working_price="100.00",
        working_quantity="0.1000",
        pending_stop_price="95.00",
        list_client_order_id="op-list-001",
        working_client_order_id="op-buy-001",
        pending_client_order_id="op-stop-001",
    )


def _response(request: dict[str, str]) -> dict[str, object]:
    return {
        "symbol": "BTCUSDT",
        "orderListId": 0,
        "contingencyType": "OTO",
        "listStatusType": "EXEC_STARTED",
        "listOrderStatus": "EXECUTING",
        "listClientOrderId": request["listClientOrderId"],
        "orders": [
            {"symbol": "BTCUSDT", "orderId": 201, "clientOrderId": request["workingClientOrderId"]},
            {"symbol": "BTCUSDT", "orderId": 202, "clientOrderId": request["pendingClientOrderId"]},
        ],
        "orderReports": [
            {
                "symbol": "BTCUSDT", "orderId": 201, "orderListId": 0,
                "clientOrderId": request["workingClientOrderId"], "type": "LIMIT",
                "side": "BUY", "timeInForce": "FOK", "status": "FILLED",
                "origQty": request["workingQuantity"], "executedQty": request["workingQuantity"],
            },
            {
                "symbol": "BTCUSDT", "orderId": 202, "orderListId": 0,
                "clientOrderId": request["pendingClientOrderId"], "type": "STOP_LOSS",
                "side": "SELL", "status": "PENDING_NEW", "executedQty": "0",
                "stopPrice": request["pendingStopPrice"],
            },
        ],
    }


def _active_intent() -> dict[str, object]:
    request = _request()
    return {
        "market": "spot",
        "type": "OPO",
        "symbol": "BTCUSDT",
        "request": request,
        "state": "accepted",
        "protection_state": "active",
        "entry_reconciled": True,
        "cancel_state": None,
        "list_status": "EXEC_STARTED",
        "working_status": "FILLED",
        "pending_status": "NEW",
        "pending_order_id": 202,
        "entry_portfolio_quantity": "0.1000",
        "pending_original_qty": "0.1000",
        "pending_executed_qty": "0",
    }


def _cancel_replace_response(
    request: dict[str, object],
    *,
    cancel_result: str = "SUCCESS",
    new_result: str = "SUCCESS",
    status: str = "FILLED",
    executed_qty: str = "0.1000",
) -> dict[str, object]:
    return {
        "cancelResult": cancel_result,
        "newOrderResult": new_result,
        "cancelResponse": {
            "symbol": "BTCUSDT",
            "orderId": 202,
            "origClientOrderId": "op-stop-001",
            "side": "SELL",
            "status": "CANCELED",
            "executedQty": "0",
        },
        "newOrderResponse": {
            "symbol": "BTCUSDT",
            "clientOrderId": request["newClientOrderId"],
            "orderId": 303,
            "side": "SELL",
            "type": "MARKET",
            "status": status,
            "origQty": request["quantity"],
            "executedQty": executed_qty,
        } if new_result == "SUCCESS" else {"code": -1013, "msg": "Rejected"},
    }


class BinanceSpotOpoRuntimeTests(unittest.TestCase):
    def test_request_uses_fok_limit_buy_and_fee_adjusted_stop_market_sell(self):
        request = _request()
        self.assertEqual("LIMIT", request["workingType"])
        self.assertEqual("BUY", request["workingSide"])
        self.assertEqual("FOK", request["workingTimeInForce"])
        self.assertEqual("STOP_LOSS", request["pendingType"])
        self.assertEqual("SELL", request["pendingSide"])
        self.assertEqual("95.00", request["pendingStopPrice"])
        self.assertNotIn("pendingQuantity", request)
        self.assertEqual("FULL", request["newOrderRespType"])

    def test_request_rejects_ineligible_symbols_and_unprotected_partial_entry(self):
        for field, value in (("opoAllowed", False), ("otoAllowed", False), ("isSpotTradingAllowed", False)):
            info = _symbol_info()
            info[field] = value
            with self.subTest(field=field), self.assertRaises(LiveTradingSafetyError):
                build_spot_opo_request(
                    symbol="BTCUSDT", symbol_info=info,
                    working_price="100", working_quantity="0.1", pending_stop_price="95",
                    list_client_order_id="l1", working_client_order_id="w1", pending_client_order_id="p1",
                )

    def test_request_rejects_bad_prices_quantity_notional_and_duplicate_ids(self):
        cases = (
            {"working_price": "100.001"},
            {"working_quantity": "0.10001"},
            {"pending_stop_price": "100"},
            {"working_quantity": "0.01"},
            {"pending_client_order_id": "op-buy-001"},
        )
        for changes in cases:
            args = {
                "symbol": "BTCUSDT", "symbol_info": _symbol_info(),
                "working_price": "100.00", "working_quantity": "0.1000", "pending_stop_price": "95.00",
                "list_client_order_id": "op-list-001", "working_client_order_id": "op-buy-001",
                "pending_client_order_id": "op-stop-001",
            }
            args.update(changes)
            with self.subTest(changes=changes), self.assertRaises(LiveTradingSafetyError):
                build_spot_opo_request(**args)

    def test_acknowledgement_binds_both_order_ids_and_pending_protection(self):
        request = _request()
        result = validate_spot_opo_acknowledgement(_response(request), request)
        self.assertEqual(0, result["order_list_id"])
        self.assertEqual(201, result["working_order_id"])
        self.assertEqual(202, result["pending_order_id"])
        self.assertEqual("FILLED", result["working_status"])
        self.assertEqual("PENDING_NEW", result["pending_status"])

    def test_acknowledgement_rejects_missing_or_crossed_stop_child(self):
        request = _request()
        bad_response = _response(request)
        bad_response["orderReports"][1]["clientOrderId"] = request["workingClientOrderId"]
        with self.assertRaises(LiveTradingSafetyError):
            validate_spot_opo_acknowledgement(bad_response, request)

        bad_response = _response(request)
        bad_response["orderReports"][1]["status"] = "CANCELED"
        with self.assertRaises(LiveTradingSafetyError):
            validate_spot_opo_acknowledgement(bad_response, request)

        bad_response = _response(request)
        bad_response["orderReports"][0]["executedQty"] = "0.0999"
        with self.assertRaises(LiveTradingSafetyError):
            validate_spot_opo_acknowledgement(bad_response, request)

        bad_response = _response(request)
        bad_response["orderReports"][1]["stopPrice"] = "94.99"
        with self.assertRaises(LiveTradingSafetyError):
            validate_spot_opo_acknowledgement(bad_response, request)

    def test_strategy_exit_request_replaces_only_an_exact_active_recovered_stop(self):
        request = build_spot_opo_cancel_replace_request(_active_intent(), new_order_client_id="exit-001")
        self.assertEqual({
            "symbol": "BTCUSDT",
            "side": "SELL",
            "type": "MARKET",
            "cancelReplaceMode": "STOP_ON_FAILURE",
            "cancelOrderId": 202,
            "cancelOrigClientOrderId": "op-stop-001",
            "cancelRestrictions": "ONLY_NEW",
            "quantity": "0.1000",
            "newClientOrderId": "exit-001",
            "newOrderRespType": "FULL",
        }, request)
        self.assertEqual(request, validate_spot_opo_cancel_replace_request(request))

    def test_strategy_exit_request_fails_closed_without_exact_active_stop(self):
        cases = []
        not_reconciled = _active_intent()
        not_reconciled["entry_reconciled"] = False
        cases.append(not_reconciled)
        triggered = _active_intent()
        triggered["pending_status"] = "PENDING_NEW"
        cases.append(triggered)
        cancelled = _active_intent()
        cancelled["cancel_state"] = "pending"
        cases.append(cancelled)
        wrong_entry_quantity = _active_intent()
        wrong_entry_quantity["entry_portfolio_quantity"] = "0.099"
        cases.append(wrong_entry_quantity)
        wrong_stop_quantity = _active_intent()
        wrong_stop_quantity["pending_original_qty"] = "0.099"
        cases.append(wrong_stop_quantity)
        for intent in cases:
            with self.subTest(intent=intent), self.assertRaises(LiveTradingSafetyError):
                build_spot_opo_cancel_replace_request(intent, new_order_client_id="exit-001")
        with self.assertRaises(LiveTradingSafetyError):
            build_spot_opo_cancel_replace_request(_active_intent(), new_order_client_id="op-stop-001")

    def test_cancel_replace_response_classifies_cancel_failure_and_requires_rearm(self):
        request = build_spot_opo_cancel_replace_request(_active_intent(), new_order_client_id="exit-001")
        canceled_stop = _cancel_replace_response(request, new_result="FAILURE")
        canceled_stop["newOrderResult"] = "FAILURE"
        outcome = validate_spot_opo_cancel_replace_response(canceled_stop, request)
        self.assertEqual("stop_canceled_exit_rejected", outcome["outcome"])
        self.assertTrue(outcome["requires_stop_rearm"])

        canceled_stop["cancelResult"] = "FAILURE"
        canceled_stop["newOrderResult"] = "NOT_ATTEMPTED"
        canceled_stop["cancelResponse"] = {"code": -2011, "msg": "Unknown order sent."}
        canceled_stop["newOrderResponse"] = None
        outcome = validate_spot_opo_cancel_replace_response(canceled_stop, request)
        self.assertEqual("cancel_failed", outcome["outcome"])
        self.assertFalse(outcome["requires_stop_rearm"])
        self.assertTrue(outcome["requires_exact_reconciliation"])

    def test_cancel_replace_response_requires_exact_sell_and_marks_residual_for_rearm(self):
        request = build_spot_opo_cancel_replace_request(_active_intent(), new_order_client_id="exit-001")
        full = validate_spot_opo_cancel_replace_response(_cancel_replace_response(request), request)
        self.assertEqual("exit_sell_accepted", full["outcome"])
        self.assertFalse(full["requires_stop_rearm"])
        self.assertEqual("0.1000", full["executed_qty"])

        partial_response = _cancel_replace_response(
            request, status="PARTIALLY_FILLED", executed_qty="0.0600",
        )
        partial = validate_spot_opo_cancel_replace_response(partial_response, request)
        self.assertTrue(partial["requires_stop_rearm"])
        self.assertEqual("0.0600", partial["executed_qty"])

        crossed = _cancel_replace_response(request)
        crossed["newOrderResponse"]["clientOrderId"] = "other-exit"
        with self.assertRaises(LiveTradingSafetyError):
            validate_spot_opo_cancel_replace_response(crossed, request)

        short_fill = _cancel_replace_response(request, executed_qty="0.0900")
        with self.assertRaises(LiveTradingSafetyError):
            validate_spot_opo_cancel_replace_response(short_fill, request)

    def test_exact_strategy_exit_order_query_requires_unlinked_matching_market_sell(self):
        request = build_spot_opo_cancel_replace_request(_active_intent(), new_order_client_id="exit-001")
        order = {
            "symbol": "BTCUSDT", "clientOrderId": "exit-001", "orderId": 303, "orderListId": -1,
            "side": "SELL", "type": "MARKET", "status": "FILLED",
            "origQty": "0.1000", "executedQty": "0.1000",
        }
        evidence = validate_spot_opo_strategy_exit_order(order, request)
        self.assertEqual(303, evidence["order_id"])
        self.assertEqual("FILLED", evidence["status"])
        self.assertTrue(evidence["terminal"])

        for changed in (
            {**order, "clientOrderId": "other-exit"},
            {**order, "orderListId": 202},
            {**order, "side": "BUY"},
            {**order, "origQty": "0.0999"},
            {**order, "status": "FILLED", "executedQty": "0.0999"},
            {**order, "status": "PARTIALLY_FILLED", "executedQty": "0"},
        ):
            with self.subTest(changed=changed), self.assertRaises(LiveTradingSafetyError):
                validate_spot_opo_strategy_exit_order(changed, request)

    @staticmethod
    def _residual_intent() -> dict[str, object]:
        intent = _active_intent()
        intent.update({
            "protection_state": "cancelled",
            "cancel_state": "confirmed",
            "strategy_exit_state": "sell_accepted",
            "residual_stop_state": "rearm_required",
        })
        return intent

    @staticmethod
    def _residual_symbol_info() -> dict[str, object]:
        info = _symbol_info()
        info["filters"] = [
            {"filterType": "PRICE_FILTER", "minPrice": "0.01", "maxPrice": "1000000", "tickSize": "0.01"},
            {"filterType": "LOT_SIZE", "minQty": "0.0001", "maxQty": "9000", "stepSize": "0.0001"},
            {"filterType": "MARKET_LOT_SIZE", "minQty": "0.0001", "maxQty": "9000", "stepSize": "0.0001"},
            {"filterType": "MIN_NOTIONAL", "minNotional": "1", "applyToMarket": True, "avgPriceMins": 0},
        ]
        return info

    def _residual_request(self, **overrides) -> dict[str, str]:
        arguments = {
            "intent": self._residual_intent(),
            "symbol_info": self._residual_symbol_info(),
            "quantity": "0.0399",
            "last_price": "100",
            "average_price": None,
            "average_price_mins": None,
            "new_client_order_id": "residual-stop-001",
        }
        arguments.update(overrides)
        return build_spot_opo_residual_stop_request(**arguments)

    def test_residual_stop_reuses_original_stop_and_exact_remaining_allocation(self):
        request = self._residual_request()
        self.assertEqual({
            "symbol": "BTCUSDT",
            "side": "SELL",
            "type": "STOP_LOSS",
            "quantity": "0.0399",
            "stopPrice": "95.00",
            "newClientOrderId": "residual-stop-001",
            "newOrderRespType": "FULL",
        }, request)

    def test_residual_stop_requires_current_market_quantity_price_and_notional_filters(self):
        invalid_quantity_info = self._residual_symbol_info()
        invalid_quantity_info["filters"][2]["stepSize"] = "0.001"
        invalid_market_lot_info = self._residual_symbol_info()
        invalid_market_lot_info["filters"][2]["minQty"] = "0.04"
        invalid_notional_info = self._residual_symbol_info()
        invalid_notional_info["filters"][3]["minNotional"] = "4"
        needs_average_info = self._residual_symbol_info()
        needs_average_info["filters"][3]["avgPriceMins"] = 5
        cases = (
            {"quantity": "0.03995"},
            {"last_price": "95"},
            {"last_price": "94"},
            {"symbol_info": invalid_quantity_info},
            {"symbol_info": invalid_market_lot_info},
            {"symbol_info": invalid_notional_info},
            {"symbol_info": needs_average_info, "average_price": "100", "average_price_mins": 4},
        )
        for changes in cases:
            with self.subTest(changes=changes), self.assertRaises(LiveTradingSafetyError):
                self._residual_request(**changes)

    def test_residual_stop_acknowledgement_and_triggered_fill_are_exact(self):
        request = self._residual_request()
        order = {
            "symbol": "BTCUSDT", "clientOrderId": "residual-stop-001", "orderId": 502,
            "orderListId": -1, "side": "SELL", "type": "STOP_LOSS", "status": "NEW",
            "origQty": "0.0399", "executedQty": "0", "stopPrice": "95",
        }
        active = validate_spot_opo_residual_stop_order(order, request)
        self.assertTrue(active["active"])
        self.assertFalse(active["terminal"])
        filled = {**order, "status": "FILLED", "executedQty": "0.0399"}
        evidence = validate_spot_opo_residual_stop_order(filled, request)
        self.assertEqual("FILLED", evidence["status"])
        self.assertTrue(evidence["terminal"])
        for changed in (
            {**order, "clientOrderId": "other-stop"},
            {**order, "stopPrice": "94.99"},
            {**order, "origQty": "0.04"},
            {**order, "status": "FILLED", "executedQty": "0.0398"},
        ):
            with self.subTest(changed=changed), self.assertRaises(LiveTradingSafetyError):
                validate_spot_opo_residual_stop_order(changed, request)


if __name__ == "__main__":
    unittest.main()
