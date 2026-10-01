from __future__ import annotations

import unittest
from contextlib import contextmanager
from pathlib import Path
from unittest.mock import patch

from app.integrations.exchanges.binance.orders import bind_binance_spot_opo_execution_runtime
from app.integrations.exchanges.binance.orders.spot_opo_execution_runtime import (
    place_spot_opo_entry,
    place_spot_opo_strategy_exit,
)
from app.integrations.exchanges.binance.orders.spot_opo_exit_retry_runtime import spot_opo_cancel_client_id
from app.integrations.exchanges.binance.orders.spot_opo_runtime import (
    validate_spot_opo_acknowledgement,
    validate_spot_opo_request_payload,
    validate_spot_opo_cancel_replace_response,
    validate_spot_opo_strategy_exit_order,
    build_spot_opo_cancel_replace_request,
    build_spot_opo_request,
)


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


def _response(request: dict[str, str]) -> dict[str, object]:
    return {
        "symbol": "BTCUSDT",
        "orderListId": 10,
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
                "symbol": "BTCUSDT", "orderId": 201, "orderListId": 10,
                "clientOrderId": request["workingClientOrderId"], "type": "LIMIT",
                "side": "BUY", "timeInForce": "FOK", "status": "FILLED",
                "origQty": request["workingQuantity"], "executedQty": request["workingQuantity"],
            },
            {
                "symbol": "BTCUSDT", "orderId": 202, "orderListId": 10,
                "clientOrderId": request["pendingClientOrderId"], "type": "STOP_LOSS",
                "side": "SELL", "status": "PENDING_NEW", "executedQty": "0",
                "stopPrice": request["pendingStopPrice"],
            },
        ],
    }


class _Client:
    def __init__(self, events: list[tuple], *, fail: bool = False):
        self.events = events
        self.fail = fail
        self.calls = 0

    def create_order_list_opo(self, **request):
        self.calls += 1
        self.events.append(("create", request))
        if self.fail:
            raise TimeoutError("response timed out")
        return _response(request)


class _Wrapper:
    account_type = "SPOT"
    mode = "live"

    def __init__(self, *, owner: bool = True, fail: bool = False):
        self.events: list[tuple] = []
        self.client = _Client(self.events, fail=fail)
        if owner:
            self._spot_execution_submission = self._owner_submission

    def get_symbol_info_spot(self, symbol: str) -> dict[str, object]:
        self.events.append(("metadata", symbol))
        return _symbol_info()

    def _guard_live_order_submit(self, **kwargs):
        self.events.append(("guard", kwargs))

    def _begin_spot_opo_intent(self, request, *, source):
        validate_spot_opo_request_payload(request)
        self.events.append(("begin", request, source))

    def _mark_spot_opo_submitted(self, client_id, *, via):
        self.events.append(("submitted", client_id, via))

    def _mark_spot_opo_accepted(self, request, *, via, result):
        validate_spot_opo_acknowledgement(result, request)
        self.events.append(("accepted", request["listClientOrderId"], via))

    def _mark_spot_opo_unknown(self, client_id, *, error):
        self.events.append(("unknown", client_id, type(error).__name__))

    def reconcile_spot_opo_intent(self, client_id, *, force):
        self.events.append(("reconcile", client_id, force))
        return {"state": "accepted", "reconciled": False, "protection_state": "active"}

    @contextmanager
    def _owner_submission(self):
        self.events.append(("owner_enter",))
        try:
            yield
        finally:
            self.events.append(("owner_exit",))


class SpotOpoExecutionRuntimeTests(unittest.TestCase):
    def test_live_submit_is_guarded_durable_fenced_and_reconciled(self):
        bind_binance_spot_opo_execution_runtime(_Wrapper)
        wrapper = _Wrapper()

        result = wrapper.place_spot_opo_entry(
            "BTCUSDT",
            "BUY",
            "100.00",
            "0.1000",
            "95.00",
            list_client_order_id="op-list-001",
            working_client_order_id="op-buy-001",
            pending_client_order_id="op-stop-001",
        )

        self.assertTrue(result["ok"])
        self.assertTrue(result["accepted"])
        self.assertEqual("active", result["protection_state"])
        self.assertTrue(result["exchange_reconciled"])
        self.assertTrue(result["active_child_observed"])
        self.assertFalse(result["entry_reconciled"])
        self.assertFalse(result["strategy_ready"])
        self.assertTrue(result["requires_portfolio_recovery"])
        kinds = [event[0] for event in wrapper.events]
        self.assertLess(kinds.index("guard"), kinds.index("begin"))
        self.assertLess(kinds.index("begin"), kinds.index("submitted"))
        self.assertLess(kinds.index("submitted"), kinds.index("owner_enter"))
        self.assertLess(kinds.index("owner_enter"), kinds.index("create"))
        self.assertLess(kinds.index("create"), kinds.index("accepted"))
        self.assertLess(kinds.index("accepted"), kinds.index("reconcile"))
        request = next(event[1] for event in wrapper.events if event[0] == "create")
        self.assertEqual("LIMIT", request["workingType"])
        self.assertEqual("FOK", request["workingTimeInForce"])
        self.assertEqual("STOP_LOSS", request["pendingType"])

    def test_live_submit_fails_closed_without_owner_or_guard(self):
        wrapper = _Wrapper(owner=False)
        wrapper._guard_live_order_submit = None

        result = place_spot_opo_entry(wrapper, "BTCUSDT", "BUY", "100", "0.1", "95")

        self.assertFalse(result["ok"])
        self.assertEqual(0, wrapper.client.calls)
        self.assertNotIn("begin", [event[0] for event in wrapper.events])

    def test_transport_timeout_is_persisted_unknown_and_never_retried(self):
        wrapper = _Wrapper(fail=True)

        result = place_spot_opo_entry(
            wrapper,
            "BTCUSDT",
            "BUY",
            "100",
            "0.1",
            "95",
            list_client_order_id="op-list-timeout",
            working_client_order_id="op-buy-timeout",
            pending_client_order_id="op-stop-timeout",
        )

        self.assertFalse(result["ok"])
        self.assertFalse(result["accepted"])
        self.assertEqual("op-list-timeout", result["order_list_client_id"])
        self.assertEqual(1, wrapper.client.calls)
        kinds = [event[0] for event in wrapper.events]
        self.assertLess(kinds.index("submitted"), kinds.index("create"))
        self.assertLess(kinds.index("create"), kinds.index("unknown"))
        self.assertNotIn("reconcile", kinds)

    def test_invalid_side_is_rejected_before_metadata_or_submission(self):
        wrapper = _Wrapper()

        result = place_spot_opo_entry(wrapper, "BTCUSDT", "SELL", "100", "0.1", "95")

        self.assertFalse(result["ok"])
        self.assertEqual(0, wrapper.client.calls)
        self.assertEqual([], wrapper.events)

    def test_linked_exit_persists_baseline_before_fenced_cancel_replace_and_queries_sell(self):
        class ExitClient:
            def __init__(self, events):
                self.events = events
                self.cancel_called = False
                self.request = None

            def cancel_replace_order(self, **request):
                self.events.append(("cancel_replace", request))
                self.cancel_called = True
                self.request = request
                return {
                    "cancelResult": "SUCCESS",
                    "newOrderResult": "SUCCESS",
                    "cancelResponse": {
                        "symbol": "BTCUSDT", "orderId": 202,
                        "origClientOrderId": "op-stop-001", "side": "SELL",
                        "status": "CANCELED", "executedQty": "0",
                    },
                    "newOrderResponse": {
                        "symbol": "BTCUSDT", "clientOrderId": request["newClientOrderId"],
                        "orderId": 303, "side": "SELL", "type": "MARKET", "status": "FILLED",
                        "origQty": request["quantity"], "executedQty": request["quantity"],
                    },
                }

            def get_order(self, **query):
                self.events.append(("get_order", query))
                return {
                    "symbol": "BTCUSDT", "clientOrderId": query["origClientOrderId"],
                    "orderId": 303, "orderListId": -1, "side": "SELL", "type": "MARKET",
                    "status": "FILLED", "origQty": "0.1000", "executedQty": "0.1000",
                }

        class ExitWrapper:
            account_type = "SPOT"
            mode = "Live"

            def __init__(self):
                self.events = []
                self.client = ExitClient(self.events)
                self.record = {
                    "market": "spot", "type": "OPO", "side": "BUY", "symbol": "BTCUSDT",
                    "client_order_id": "op-list-001", "state": "accepted", "protection_state": "active",
                    "entry_reconciled": True, "entry_portfolio_quantity": "0.1000",
                    "list_status": "EXEC_STARTED", "working_status": "FILLED", "pending_status": "NEW",
                    "pending_order_id": 202, "pending_original_qty": "0.1000", "pending_executed_qty": "0",
                    "request": build_spot_opo_request(
                        symbol="BTCUSDT", symbol_info=_symbol_info(), working_price="100",
                        working_quantity="0.1000", pending_stop_price="95",
                        list_client_order_id="op-list-001", working_client_order_id="op-buy-001",
                        pending_client_order_id="op-stop-001",
                    ),
                }
                self._spot_execution_submission = self.owner_submission

            @contextmanager
            def owner_submission(self):
                self.events.append(("owner_enter",))
                try:
                    yield
                finally:
                    self.events.append(("owner_exit",))

            def _guard_live_order_submit(self, **kwargs):
                self.events.append(("guard", kwargs))

            def reconcile_spot_opo_intent(self, list_id, *, force):
                self.events.append(("reconcile", list_id, force))
                if self.client.cancel_called:
                    self.record.update({"protection_state": "cancelled", "cancel_state": "confirmed"})
                    return {"state": "accepted", "protection_state": "cancelled", "reconciled": False}
                return {"state": "accepted", "protection_state": "active", "reconciled": True}

            def _get_order_intent_record(self, _list_id):
                return dict(self.record)

            def _check_spot_opo_strategy_exit_client_id(self, list_id, *, new_order_client_id):
                build_spot_opo_cancel_replace_request(self.record, new_order_client_id=new_order_client_id)

            def _begin_spot_opo_strategy_exit(self, list_id, *, new_order_client_id,
                                               pre_order_portfolio_signature, pre_order_portfolio_quantity,
                                               allocation_path=None, expected_record=None):
                self.events.append(("begin", pre_order_portfolio_signature, pre_order_portfolio_quantity))
                request = build_spot_opo_cancel_replace_request(
                    self.record, new_order_client_id=new_order_client_id,
                    cancel_new_client_order_id=spot_opo_cancel_client_id(new_order_client_id),
                )
                self.record.update({
                    "strategy_exit_state": "submitted",
                    "strategy_exit_request": request,
                    "strategy_exit_client_order_id": new_order_client_id,
                    "strategy_exit_quantity": request["quantity"],
                    "strategy_exit_pre_order_signature": pre_order_portfolio_signature,
                    "strategy_exit_pre_order_quantity": pre_order_portfolio_quantity,
                })
                return {"strategy_exit_request": request}

            def _mark_spot_opo_strategy_exit_response(self, list_id, *, response, expected_record=None):
                evidence = validate_spot_opo_cancel_replace_response(
                    response, self.record["strategy_exit_request"],
                )
                self.events.append(("response", evidence["outcome"]))
                self.record.update({
                    "strategy_exit_state": "sell_accepted",
                    "strategy_exit_outcome": evidence["outcome"],
                    "strategy_exit_order_id": evidence["new_order_id"],
                    "strategy_exit_status": evidence["new_order_status"],
                    "strategy_exit_executed_qty": evidence["executed_qty"],
                    "strategy_exit_cancel_confirmed": True,
                    "strategy_exit_new_order_accepted": True,
                    "strategy_exit_requires_stop_rearm": False,
                })
                return evidence

            def _mark_spot_opo_strategy_exit_unknown(self, list_id, *, error, expected_record=None):
                self.events.append(("unknown", type(error).__name__))

            def _mark_spot_opo_strategy_exit_order_observed(self, list_id, *, order_response, expected_record=None):
                evidence = validate_spot_opo_strategy_exit_order(
                    order_response, self.record["strategy_exit_request"],
                )
                self.events.append(("observed", evidence["status"]))
                return evidence

        wrapper = ExitWrapper()
        with patch(
            "app.integrations.exchanges.binance.orders.spot_opo_execution_runtime._live_allocation_path",
            return_value=Path("allocations.json"),
        ), patch(
            "app.integrations.exchanges.binance.orders.spot_opo_execution_runtime.spot_opo_allocation_baseline",
            return_value={"signature": "a" * 64, "quantity": "0.1000"},
        ):
            result = place_spot_opo_strategy_exit(
                wrapper, "op-list-001", new_order_client_id="strategy-exit-001",
            )

        self.assertTrue(result["ok"])
        self.assertTrue(result["accepted"])
        self.assertTrue(result["exchange_reconciled"])
        self.assertFalse(result["strategy_ready"])
        self.assertTrue(result["requires_portfolio_recovery"])
        kinds = [event[0] for event in wrapper.events]
        self.assertLess(kinds.index("guard"), kinds.index("begin"))
        self.assertLess(kinds.index("guard"), kinds.index("owner_enter"))
        self.assertLess(kinds.index("owner_enter"), kinds.index("cancel_replace"))
        self.assertLess(kinds.index("cancel_replace"), kinds.index("response"))
        reconcile_after_response = kinds.index("reconcile", kinds.index("response"))
        self.assertLess(kinds.index("response"), reconcile_after_response)
        self.assertLess(reconcile_after_response, kinds.index("get_order"))


if __name__ == "__main__":
    unittest.main()
