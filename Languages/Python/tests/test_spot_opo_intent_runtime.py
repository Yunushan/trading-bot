from __future__ import annotations

import json
import tempfile
import unittest
from decimal import Decimal
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from app.integrations.exchanges.binance.orders import order_intent_runtime as ledger
from app.integrations.exchanges.binance.orders.order_intent_provisioning import PROVISION_ACK, provision_order_intent_store
from app.integrations.exchanges.binance.orders.spot_fill_recovery_runtime import (
    persist_spot_opo_residual_stop_allocation,
    persist_spot_opo_stop_sell_allocation,
    persist_spot_opo_strategy_sell_allocation,
    persist_spot_buy_allocation,
    spot_opo_allocation_baseline,
    summarize_spot_opo_residual_stop_sell_fill,
    summarize_spot_opo_stop_sell_fill,
    summarize_spot_opo_strategy_sell_fill,
)
from app.integrations.exchanges.binance.orders.spot_opo_runtime import build_spot_opo_request
from app.integrations.exchanges.binance.orders.spot_opo_execution_runtime import place_spot_opo_entry
from app.integrations.exchanges.binance.orders.order_sizing_runtime import place_spot_market_order, _floor_to_step
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


def _acknowledgement(request: dict[str, str]) -> dict[str, object]:
    return {
        "symbol": request["symbol"],
        "orderListId": 300,
        "contingencyType": "OTO",
        "listStatusType": "EXEC_STARTED",
        "listOrderStatus": "EXECUTING",
        "listClientOrderId": request["listClientOrderId"],
        "orders": [
            {"symbol": request["symbol"], "orderId": 301, "clientOrderId": request["workingClientOrderId"]},
            {"symbol": request["symbol"], "orderId": 302, "clientOrderId": request["pendingClientOrderId"]},
        ],
        "orderReports": [
            {
                "symbol": request["symbol"], "orderId": 301, "orderListId": 300,
                "clientOrderId": request["workingClientOrderId"], "type": "LIMIT", "side": "BUY",
                "timeInForce": "FOK", "status": "FILLED", "origQty": request["workingQuantity"],
                "executedQty": request["workingQuantity"],
            },
            {
                "symbol": request["symbol"], "orderId": 302, "orderListId": 300,
                "clientOrderId": request["pendingClientOrderId"], "type": "STOP_LOSS", "side": "SELL",
                "status": "PENDING_NEW", "executedQty": "0", "stopPrice": request["pendingStopPrice"],
            },
        ],
    }


def _observation(
    request: dict[str, str], *, working_status: str = "FILLED", working_executed: str = "0.1000",
    pending_status: str = "NEW", pending_executed: str = "0", list_status: str = "EXEC_STARTED",
) -> tuple[dict[str, object], dict[str, object], dict[str, object]]:
    list_response = {
        "symbol": request["symbol"], "orderListId": 300, "contingencyType": "OTO",
        "listStatusType": list_status, "listOrderStatus": "EXECUTING" if list_status == "EXEC_STARTED" else "ALL_DONE",
        "listClientOrderId": request["listClientOrderId"],
        "orders": [
            {"symbol": request["symbol"], "orderId": 301, "clientOrderId": request["workingClientOrderId"]},
            {"symbol": request["symbol"], "orderId": 302, "clientOrderId": request["pendingClientOrderId"]},
        ],
    }
    working = {
        "symbol": request["symbol"], "orderId": 301, "orderListId": 300,
        "clientOrderId": request["workingClientOrderId"], "type": "LIMIT", "side": "BUY",
        "timeInForce": "FOK", "status": working_status, "origQty": request["workingQuantity"],
        "executedQty": working_executed,
    }
    pending = {
        "symbol": request["symbol"], "orderId": 302, "orderListId": 300,
        "clientOrderId": request["pendingClientOrderId"], "type": "STOP_LOSS", "side": "SELL",
        "status": pending_status,
        "origQty": "0.0999" if working_status == "FILLED" and pending_status != "PENDING_NEW" else "0",
        "executedQty": pending_executed, "stopPrice": request["pendingStopPrice"],
    }
    return list_response, working, pending


def _cancel_replace_response(
    *, new_client_order_id: str, cancel_result: str = "SUCCESS", new_result: str = "SUCCESS",
) -> dict[str, object]:
    if cancel_result == "FAILURE":
        return {
            "cancelResult": "FAILURE",
            "newOrderResult": "NOT_ATTEMPTED",
            "cancelResponse": {"code": -2011, "msg": "Unknown order sent."},
            "newOrderResponse": None,
        }
    if new_result == "FAILURE":
        new_response = {"code": -1013, "msg": "Rejected"}
    else:
        new_response = {
            "symbol": "BTCUSDT", "clientOrderId": new_client_order_id, "orderId": 401,
            "side": "SELL", "type": "MARKET", "status": "FILLED",
            "origQty": "0.0999", "executedQty": "0.0999",
        }
    return {
        "cancelResult": "SUCCESS",
        "newOrderResult": new_result,
        "cancelResponse": {
            "symbol": "BTCUSDT", "orderId": 302, "origClientOrderId": "op-stop-001",
            "side": "SELL", "status": "CANCELED", "executedQty": "0",
        },
        "newOrderResponse": new_response,
    }


class SpotOpoIntentRuntimeTests(unittest.TestCase):
    def setUp(self):
        self._reset_intent_store()

    def _reset_intent_store(self):
        directory = self.enterContext(tempfile.TemporaryDirectory())
        self.owner = SimpleNamespace(
            _order_audit_log_path=Path(directory) / "audit.jsonl",
            api_key="offline-test-key",
            mode="Demo/Testnet",
        )
        provision_order_intent_store(self.owner, acknowledgement=PROVISION_ACK)
        self.request = _request()
        self.intent = ledger._begin_spot_opo_intent(self.owner, self.request, source="offline-test")

    def _submit(self):
        ledger._mark_spot_opo_submitted(self.owner, self.request["listClientOrderId"], via="test")

    def _install_observation(self, *, working_status="FILLED", working_executed="0.1000", pending_status="NEW",
                             pending_executed="0", list_status="EXEC_STARTED", wrong_pending_id=False):
        list_response, working, pending = _observation(
            self.request,
            working_status=working_status,
            working_executed=working_executed,
            pending_status=pending_status,
            pending_executed=pending_executed,
            list_status=list_status,
        )
        if wrong_pending_id:
            list_response["orders"][1]["clientOrderId"] = "another-stop"
        children = {working["clientOrderId"]: working, pending["clientOrderId"]: pending}
        self.owner.client = SimpleNamespace(
            get_order_list=lambda **_kwargs: list_response,
            get_order=lambda **kwargs: children[kwargs["origClientOrderId"]],
        )

    def _recover_active_entry(self):
        self._submit()
        ledger._mark_spot_opo_unknown(self.owner, self.request["listClientOrderId"], error="restart recovery")
        self._install_observation()
        ledger.reconcile_spot_opo_intent(self.owner, self.request["listClientOrderId"])
        allocation_path = Path(self.owner._order_audit_log_path).with_name("allocations.json")
        fill = {
            "symbol": "BTCUSDT", "client_order_id": self.request["listClientOrderId"],
            "exchange_client_order_id": self.request["workingClientOrderId"], "order_id": 301,
            "trade_ids": [901], "trade_count": 1, "gross_qty": "0.1", "net_qty": "0.0999",
            "pending_order_qty": "0.0999", "gross_quote_qty": "10", "net_quote_cost": "9.99",
            "average_cost": "100", "commissions": [], "base_asset": "BTC", "quote_asset": "USDT",
            "fill_time_ms": 1780000000000, "signature": "c" * 64,
        }
        with patch(
            "app.gui.shared.allocation_persistence.get_position_allocations_path",
            return_value=allocation_path,
        ):
            persist_spot_buy_allocation(allocation_path, fill)
            ledger._mark_spot_opo_entry_reconciled(
                self.owner, self.request["listClientOrderId"],
                portfolio_signature="c" * 64, portfolio_quantity="0.0999",
            )
        self.allocation_path = allocation_path
        return allocation_path

    def _begin_strategy_exit(self, owner, client_order_id: str, new_order_client_id: str):
        baseline = spot_opo_allocation_baseline(
            self.allocation_path,
            symbol="BTCUSDT",
            list_client_order_id=self.request["listClientOrderId"],
            expected_quantity="0.0999",
        )
        return ledger._begin_spot_opo_strategy_exit(
            owner,
            client_order_id,
            new_order_client_id=new_order_client_id,
            pre_order_portfolio_signature=baseline["signature"],
            pre_order_portfolio_quantity=baseline["quantity"],
        )

    def _recover_partial_strategy_exit(self):
        allocation_path = self._recover_active_entry()
        self._begin_strategy_exit(self.owner, self.request["listClientOrderId"], "strategy-exit-partial")
        response = _cancel_replace_response(new_client_order_id="strategy-exit-partial")
        response["newOrderResponse"]["orderId"] = 410
        response["newOrderResponse"]["status"] = "PARTIALLY_FILLED"
        response["newOrderResponse"]["executedQty"] = "0.0600"
        ledger._mark_spot_opo_strategy_exit_response(
            self.owner, self.request["listClientOrderId"], response=response,
        )
        self._install_observation(
            pending_status="CANCELED", pending_executed="0", list_status="ALL_DONE",
        )
        reconciled = ledger.reconcile_spot_opo_intent(
            self.owner, self.request["listClientOrderId"], force=True,
        )
        self.assertEqual("cancelled", reconciled["protection_state"])
        order = {
            "symbol": "BTCUSDT", "clientOrderId": "strategy-exit-partial", "orderId": 410,
            "orderListId": -1, "side": "SELL", "type": "MARKET", "status": "CANCELED",
            "origQty": "0.0999", "executedQty": "0.0600", "cummulativeQuoteQty": "11.4",
            "updateTime": 1780000000030,
        }
        ledger._mark_spot_opo_strategy_exit_order_observed(
            self.owner, self.request["listClientOrderId"], order_response=order,
        )
        intent = ledger._get_order_intent_record(self.owner, self.request["listClientOrderId"])
        trades = [{
            "symbol": "BTCUSDT", "id": 910, "orderId": 410, "price": "190",
            "qty": "0.0600", "quoteQty": "11.4", "commission": "0", "commissionAsset": "BTC",
            "time": 1780000000030, "isBuyer": False,
        }]
        fill = summarize_spot_opo_strategy_sell_fill(
            intent, order, trades, base_asset="BTC", quote_asset="USDT",
        )
        persist_spot_opo_strategy_sell_allocation(allocation_path, fill)
        remaining = Decimal(str(intent["entry_portfolio_quantity"])) - Decimal(str(fill["portfolio_qty"]))
        baseline = spot_opo_allocation_baseline(
            allocation_path,
            symbol="BTCUSDT",
            list_client_order_id=self.request["listClientOrderId"],
            expected_quantity=remaining,
        )
        ledger._mark_spot_opo_strategy_exit_residual_required(
            self.owner,
            self.request["listClientOrderId"],
            allocation_path=allocation_path,
            portfolio_signature=baseline["signature"],
            portfolio_quantity=baseline["quantity"],
            fill_signature=str(fill["signature"]),
            consumed_quantity=fill["portfolio_qty"],
            trade_ids=list(fill["trade_ids"]),
            fill_time_ms=int(fill["fill_time_ms"]),
        )
        return allocation_path, baseline

    def _begin_and_observe_residual_stop(
        self, allocation_path, baseline, client_order_id="residual-stop-001", *, exact_query=True,
    ):
        request = {
            "symbol": "BTCUSDT", "side": "SELL", "type": "STOP_LOSS",
            "quantity": baseline["quantity"], "stopPrice": "95.00",
            "newClientOrderId": client_order_id, "newOrderRespType": "FULL",
        }
        ledger._begin_spot_opo_residual_stop(
            self.owner,
            self.request["listClientOrderId"],
            allocation_path=allocation_path,
            request=request,
            pre_order_portfolio_signature=baseline["signature"],
            pre_order_portfolio_quantity=baseline["quantity"],
        )
        acknowledgement = {
            "symbol": "BTCUSDT", "clientOrderId": client_order_id, "orderId": 510,
            "side": "SELL", "type": "STOP_LOSS", "orderListId": -1, "status": "NEW",
            "origQty": baseline["quantity"], "executedQty": "0", "stopPrice": "95.00",
        }
        ledger._mark_spot_opo_residual_stop_order_observed(
            self.owner, self.request["listClientOrderId"], order_response=acknowledgement,
        )
        if exact_query:
            exact = ledger._mark_spot_opo_residual_stop_order_observed(
                self.owner,
                self.request["listClientOrderId"],
                order_response=acknowledgement,
                exact_query=True,
            )
            self.assertEqual("NEW", exact["status"])
        return request, acknowledgement

    def test_durable_pending_intent_blocks_another_entry(self):
        self.assertEqual("pending", self.intent["state"])
        self.assertTrue(ledger._is_unresolved(self.intent))
        with self.assertRaisesRegex(LiveTradingSafetyError, "Unresolved exchange order intent"):
            ledger._begin_spot_opo_intent(
                self.owner,
                {**self.request, "listClientOrderId": "op-list-002", "workingClientOrderId": "op-buy-002",
                 "pendingClientOrderId": "op-stop-002"},
                source="offline-test",
            )

    def test_uncertain_submission_cannot_be_resubmitted(self):
        self._submit()
        ledger._mark_spot_opo_unknown(
            self.owner, self.request["listClientOrderId"], error="ambiguous response",
        )
        with self.assertRaisesRegex(LiveTradingSafetyError, "not in a submittable state"):
            self._submit()
        record = ledger._get_order_intent_record(self.owner, self.request["listClientOrderId"])
        self.assertEqual("unknown", record["state"])

    def test_acknowledgement_requires_prior_durable_submission_and_persists_fill_proof(self):
        with self.assertRaisesRegex(LiveTradingSafetyError, "durably submitted"):
            ledger._mark_spot_opo_accepted(self.owner, self.request, via="test", result=_acknowledgement(self.request))
        self.assertEqual("pending", ledger._get_order_intent_record(self.owner, self.request["listClientOrderId"])["state"])

        self._submit()
        accepted = ledger._mark_spot_opo_accepted(
            self.owner, self.request, via="test", result=_acknowledgement(self.request),
        )
        self.assertEqual("accepted", accepted["state"])
        self.assertEqual("unverified", accepted["protection_state"])
        self.assertEqual("0.1000", accepted["working_executed_qty"])
        self.assertEqual("0", accepted["pending_executed_qty"])
        self.assertTrue(ledger._is_unresolved(accepted))

    def test_exact_active_stop_is_recorded_but_inventory_stays_unresolved(self):
        self._submit()
        ledger._mark_spot_opo_unknown(self.owner, self.request["listClientOrderId"], error="restart recovery")
        self._install_observation()

        result = ledger.reconcile_spot_opo_intent(self.owner, self.request["listClientOrderId"])

        self.assertFalse(result["reconciled"])
        self.assertEqual("accepted", result["state"])
        self.assertEqual("active", result["protection_state"])
        self.assertEqual("NEW", result["pending_status"])
        self.assertEqual(1, ledger.get_order_intent_status(self.owner)["unresolved_count"])
        audit = ledger.get_spot_open_order_reconciliation_status(self.owner, [{
            "symbol": "BTCUSDT", "clientOrderId": self.request["pendingClientOrderId"],
            "orderId": 302, "status": "NEW",
        }])
        self.assertEqual(1, audit["matched_open_order_count"])
        self.assertEqual(0, audit["local_open_order_status_conflict_count"])
        missing = ledger.get_spot_open_order_reconciliation_status(self.owner, [])
        self.assertEqual(1, missing["local_open_orders_missing_from_exchange_count"])
        changed_id = ledger.get_spot_open_order_reconciliation_status(self.owner, [{
            "symbol": "BTCUSDT", "clientOrderId": self.request["pendingClientOrderId"],
            "orderId": 999, "status": "NEW",
        }])
        self.assertEqual(1, changed_id["local_open_order_status_conflict_count"])

    def test_malformed_acknowledgement_becomes_unknown_and_cannot_be_retried(self):
        self._submit()
        bad_ack = _acknowledgement(self.request)
        bad_ack["orderReports"][1]["clientOrderId"] = self.request["workingClientOrderId"]

        with self.assertRaisesRegex(LiveTradingSafetyError, "reconciliation required"):
            ledger._mark_spot_opo_accepted(self.owner, self.request, via="test", result=bad_ack)

        record = ledger._get_order_intent_record(self.owner, self.request["listClientOrderId"])
        self.assertEqual("unknown", record["state"])
        self.assertEqual("unverified", record["protection_state"])
        with self.assertRaisesRegex(LiveTradingSafetyError, "not in a submittable state"):
            self._submit()

    def test_fok_no_fill_requires_terminal_exact_list_and_zero_execution(self):
        self._submit()
        ledger._mark_spot_opo_unknown(self.owner, self.request["listClientOrderId"], error="restart recovery")
        self._install_observation(
            working_status="EXPIRED", working_executed="0", pending_status="PENDING_NEW",
            pending_executed="0", list_status="ALL_DONE",
        )

        result = ledger.reconcile_spot_opo_intent(self.owner, self.request["listClientOrderId"])

        self.assertTrue(result["reconciled"])
        self.assertEqual("rejected", result["state"])
        self.assertEqual("none", result["protection_state"])
        self.assertEqual(0, ledger.get_order_intent_status(self.owner)["unresolved_count"])

    def test_verified_no_fill_keeps_terminal_evidence_and_blocks_after_failed_refresh(self):
        self._submit()
        ledger._mark_spot_opo_unknown(self.owner, self.request["listClientOrderId"], error="restart recovery")
        self._install_observation(
            working_status="EXPIRED", working_executed="0", pending_status="PENDING_NEW", list_status="ALL_DONE",
        )
        verified = ledger.reconcile_spot_opo_intent(self.owner, self.request["listClientOrderId"])
        self.assertTrue(verified["reconciled"])
        self.assertEqual("none", verified["protection_state"])
        self.owner.client.get_order_list = lambda **_kwargs: (_ for _ in ()).throw(TimeoutError("offline timeout"))

        failed = ledger.reconcile_spot_opo_intent(self.owner, self.request["listClientOrderId"], force=True)

        self.assertFalse(failed["reconciled"])
        self.assertEqual("unknown", failed["state"])
        self.assertEqual("unverified", failed["protection_state"])
        record = ledger._get_order_intent_record(self.owner, self.request["listClientOrderId"])
        self.assertEqual("EXPIRED", record["working_status"])
        self.assertEqual("0", record["working_executed_qty"])
        self.assertEqual("PENDING_NEW", record["pending_status"])
        self.assertEqual("0", record["pending_executed_qty"])
        self.assertEqual("ALL_DONE", record["list_status"])
        self.assertEqual(1, ledger.get_order_intent_status(self.owner)["unresolved_count"])

        self._install_observation(
            working_status="NEW", working_executed="0", pending_status="PENDING_NEW", list_status="ALL_DONE",
        )
        stale = ledger.reconcile_spot_opo_intent(self.owner, self.request["listClientOrderId"], force=True)
        self.assertFalse(stale["reconciled"])
        self.assertIn("terminal child status", stale["error"])
        self.assertEqual("EXPIRED", ledger._get_order_intent_record(
            self.owner, self.request["listClientOrderId"],
        )["working_status"])
        with self.assertRaisesRegex(LiveTradingSafetyError, "Unresolved"):
            ledger._begin_spot_opo_intent(
                self.owner, {**self.request, "listClientOrderId": "another-op-list"}, source="strategy",
            )

    def test_entry_recovery_requires_persisted_fill_and_exact_active_stop_coverage(self):
        self._submit()
        ledger._mark_spot_opo_unknown(self.owner, self.request["listClientOrderId"], error="restart recovery")
        self._install_observation()
        ledger.reconcile_spot_opo_intent(self.owner, self.request["listClientOrderId"])
        allocation_path = Path(self.owner._order_audit_log_path).with_name("allocations.json")
        fill = {
            "symbol": "BTCUSDT", "client_order_id": self.request["listClientOrderId"],
            "exchange_client_order_id": self.request["workingClientOrderId"], "order_id": 301,
            "trade_ids": [901], "trade_count": 1, "gross_qty": "0.1", "net_qty": "0.0999",
            "pending_order_qty": "0.0999", "gross_quote_qty": "10", "net_quote_cost": "9.99",
            "average_cost": "100", "commissions": [], "base_asset": "BTC", "quote_asset": "USDT",
            "fill_time_ms": 1780000000000, "signature": "c" * 64,
        }
        with patch(
            "app.gui.shared.allocation_persistence.get_position_allocations_path",
            return_value=allocation_path,
        ):
            persist_spot_buy_allocation(allocation_path, fill)
            with self.assertRaisesRegex(LiveTradingSafetyError, "stop quantity"):
                ledger._mark_spot_opo_entry_reconciled(
                    self.owner, self.request["listClientOrderId"],
                    portfolio_signature="c" * 64, portfolio_quantity="0.0998",
                )
            marked = ledger._mark_spot_opo_entry_reconciled(
                self.owner, self.request["listClientOrderId"],
                portfolio_signature="c" * 64, portfolio_quantity="0.0999",
            )

        self.assertTrue(marked["entry_reconciled"])
        self.assertEqual(0, ledger.get_order_intent_status(self.owner)["unresolved_count"])

    def test_force_reconciliation_polls_a_resolved_active_stop_for_triggered_exit(self):
        self._submit()
        ledger._mark_spot_opo_unknown(self.owner, self.request["listClientOrderId"], error="restart recovery")
        self._install_observation()
        ledger.reconcile_spot_opo_intent(self.owner, self.request["listClientOrderId"])
        allocation_path = Path(self.owner._order_audit_log_path).with_name("allocations.json")
        fill = {
            "symbol": "BTCUSDT", "client_order_id": self.request["listClientOrderId"],
            "exchange_client_order_id": self.request["workingClientOrderId"], "order_id": 301,
            "trade_ids": [901], "trade_count": 1, "gross_qty": "0.1", "net_qty": "0.0999",
            "pending_order_qty": "0.0999", "gross_quote_qty": "10", "net_quote_cost": "9.99",
            "average_cost": "100", "commissions": [], "base_asset": "BTC", "quote_asset": "USDT",
            "fill_time_ms": 1780000000000, "signature": "c" * 64,
        }
        with patch(
            "app.gui.shared.allocation_persistence.get_position_allocations_path",
            return_value=allocation_path,
        ):
            persist_spot_buy_allocation(allocation_path, fill)
            ledger._mark_spot_opo_entry_reconciled(
                self.owner, self.request["listClientOrderId"],
                portfolio_signature="c" * 64, portfolio_quantity="0.0999",
            )
        self.assertEqual(0, ledger.get_order_intent_status(self.owner)["unresolved_count"])

        self._install_observation(
            pending_status="FILLED", pending_executed="0.0999", list_status="ALL_DONE",
        )
        skipped = ledger.reconcile_spot_opo_intent(self.owner, self.request["listClientOrderId"])
        self.assertEqual("active", skipped["protection_state"])
        self.assertEqual(0, ledger.get_order_intent_status(self.owner)["unresolved_count"])

        polled = ledger.reconcile_spot_opo_intent(
            self.owner, self.request["listClientOrderId"], force=True,
        )
        status = ledger.get_order_intent_status(self.owner)
        self.assertEqual("triggered", polled["protection_state"])
        self.assertEqual(1, status["unresolved_count"])
        self.assertEqual([self.request["listClientOrderId"]], status["spot_opo_client_order_ids"])

    def _assert_original_stop_terminal_status_cannot_regress(self, status, executed="0"):
        self._recover_active_entry()
        self._install_observation(pending_status=status, pending_executed=executed, list_status="ALL_DONE")
        first = ledger.reconcile_spot_opo_intent(self.owner, self.request["listClientOrderId"], force=True)
        self.assertEqual("triggered" if status == "FILLED" else "lost", first["protection_state"])
        self.assertEqual(1, ledger.get_order_intent_status(self.owner)["unresolved_count"])

        # Keep ALL_DONE to exercise child continuity independently of list continuity.
        self._install_observation(list_status="ALL_DONE")
        stale = ledger.reconcile_spot_opo_intent(self.owner, self.request["listClientOrderId"], force=True)
        self.assertFalse(stale["reconciled"])
        self.assertIn("terminal child status", stale["error"])
        record = ledger._get_order_intent_record(self.owner, self.request["listClientOrderId"])
        self.assertEqual(status, record["pending_status"])
        self.assertEqual(executed, record["pending_executed_qty"])
        self.assertEqual("ALL_DONE", record["list_status"])
        self.assertEqual("0.0999", record["pending_original_qty"])
        self.assertTrue(record["entry_reconciled"])
        self.assertTrue(ledger._is_unresolved(record))
        self.assertEqual(1, ledger.get_order_intent_status(self.owner)["unresolved_count"])
        with self.assertRaisesRegex(LiveTradingSafetyError, "Unresolved"):
            ledger._begin_spot_opo_intent(
                self.owner, {**self.request, "listClientOrderId": "another-op-list"}, source="strategy",
            )

    def test_filled_original_stop_cannot_be_reported_active_again(self):
        self._assert_original_stop_terminal_status_cannot_regress("FILLED", "0.0999")

    def test_canceled_original_stop_cannot_be_reported_active_again(self):
        self._assert_original_stop_terminal_status_cannot_regress("CANCELED")

    def test_expired_original_stop_cannot_be_reported_active_again(self):
        self._assert_original_stop_terminal_status_cannot_regress("EXPIRED")

    def test_expired_in_match_original_stop_cannot_be_reported_active_again(self):
        self._assert_original_stop_terminal_status_cannot_regress("EXPIRED_IN_MATCH")

    def test_rejected_original_stop_cannot_be_reported_active_again(self):
        self._assert_original_stop_terminal_status_cannot_regress("REJECTED")

    def test_original_terminal_list_cannot_regress_with_unchanged_children(self):
        self._recover_active_entry()
        self._install_observation(pending_status="CANCELED", list_status="ALL_DONE")
        ledger.reconcile_spot_opo_intent(self.owner, self.request["listClientOrderId"], force=True)
        self._install_observation(pending_status="CANCELED", list_status="EXEC_STARTED")

        stale = ledger.reconcile_spot_opo_intent(self.owner, self.request["listClientOrderId"], force=True)

        self.assertFalse(stale["reconciled"])
        self.assertIn("terminal list status", stale["error"])
        record = ledger._get_order_intent_record(self.owner, self.request["listClientOrderId"])
        self.assertEqual("ALL_DONE", record["list_status"])
        self.assertEqual("CANCELED", record["pending_status"])
        self.assertEqual(1, ledger.get_order_intent_status(self.owner)["unresolved_count"])

    def test_original_stop_partial_execution_cannot_decrease_or_return_to_new(self):
        self._recover_active_entry()
        self._install_observation(pending_status="PARTIALLY_FILLED", pending_executed="0.05")
        ledger.reconcile_spot_opo_intent(self.owner, self.request["listClientOrderId"], force=True)
        for status, executed in (("PARTIALLY_FILLED", "0.04"), ("NEW", "0")):
            with self.subTest(status=status):
                self._install_observation(pending_status=status, pending_executed=executed)
                stale = ledger.reconcile_spot_opo_intent(self.owner, self.request["listClientOrderId"], force=True)
                self.assertFalse(stale["reconciled"])
                self.assertIn("executed quantity decreased", stale["error"])
                record = ledger._get_order_intent_record(self.owner, self.request["listClientOrderId"])
                self.assertEqual("PARTIALLY_FILLED", record["pending_status"])
                self.assertEqual("0.05", record["pending_executed_qty"])
                self.assertEqual(1, ledger.get_order_intent_status(self.owner)["unresolved_count"])

    def test_original_buy_terminal_status_and_execution_cannot_regress(self):
        self._recover_active_entry()
        self._install_observation(working_status="PARTIALLY_FILLED", working_executed="0.01")

        stale = ledger.reconcile_spot_opo_intent(self.owner, self.request["listClientOrderId"], force=True)

        self.assertFalse(stale["reconciled"])
        self.assertIn("terminal child status", stale["error"])
        record = ledger._get_order_intent_record(self.owner, self.request["listClientOrderId"])
        self.assertEqual("FILLED", record["working_status"])
        self.assertEqual("0.1000", record["working_executed_qty"])
        self.assertEqual("0.0999", record["pending_original_qty"])
        self.assertEqual(1, ledger.get_order_intent_status(self.owner)["unresolved_count"])

    def test_original_buy_partial_execution_cannot_decrease(self):
        self._submit()
        ledger._mark_spot_opo_unknown(self.owner, self.request["listClientOrderId"], error="restart recovery")
        self._install_observation(
            working_status="PARTIALLY_FILLED", working_executed="0.0100", pending_status="PENDING_NEW",
        )
        ledger.reconcile_spot_opo_intent(self.owner, self.request["listClientOrderId"])
        self._install_observation(
            working_status="PARTIALLY_FILLED", working_executed="0.0090", pending_status="PENDING_NEW",
        )

        stale = ledger.reconcile_spot_opo_intent(self.owner, self.request["listClientOrderId"], force=True)

        self.assertFalse(stale["reconciled"])
        self.assertIn("executed quantity decreased", stale["error"])
        record = ledger._get_order_intent_record(self.owner, self.request["listClientOrderId"])
        self.assertEqual("PARTIALLY_FILLED", record["working_status"])
        self.assertEqual("0.0100", record["working_executed_qty"])
        self.assertEqual("lost", record["protection_state"])
        self.assertEqual(1, ledger.get_order_intent_status(self.owner)["unresolved_count"])

    def test_original_list_and_children_must_keep_their_durable_exchange_ids(self):
        self._recover_active_entry()
        for field in ("list", "working", "pending"):
            with self.subTest(field=field):
                list_response, working, pending = _observation(self.request)
                if field == "list":
                    list_response["orderListId"] = 600
                    working["orderListId"] = pending["orderListId"] = 600
                else:
                    child = working if field == "working" else pending
                    child["orderId"] = 600
                    list_response["orders"][0 if field == "working" else 1]["orderId"] = 600
                children = {working["clientOrderId"]: working, pending["clientOrderId"]: pending}
                self.owner.client = SimpleNamespace(
                    get_order_list=lambda **_kwargs: list_response,
                    get_order=lambda **kwargs: children[kwargs["origClientOrderId"]],
                )
                stale = ledger.reconcile_spot_opo_intent(self.owner, self.request["listClientOrderId"], force=True)
                self.assertFalse(stale["reconciled"])
                self.assertIn("ID changed", stale["error"])
                record = ledger._get_order_intent_record(self.owner, self.request["listClientOrderId"])
                self.assertEqual(300, record["exchange_order_list_id"])
                self.assertEqual(301, record["working_order_id"])
                self.assertEqual(302, record["pending_order_id"])
                self.assertEqual(1, ledger.get_order_intent_status(self.owner)["unresolved_count"])

    def test_original_stop_quantity_cannot_change_after_entry_recovery(self):
        self._recover_active_entry()
        list_response, working, pending = _observation(self.request)
        pending["origQty"] = "0.1000"
        children = {working["clientOrderId"]: working, pending["clientOrderId"]: pending}
        self.owner.client = SimpleNamespace(
            get_order_list=lambda **_kwargs: list_response,
            get_order=lambda **kwargs: children[kwargs["origClientOrderId"]],
        )

        stale = ledger.reconcile_spot_opo_intent(self.owner, self.request["listClientOrderId"], force=True)

        self.assertFalse(stale["reconciled"])
        self.assertIn("stop quantity changed", stale["error"])
        record = ledger._get_order_intent_record(self.owner, self.request["listClientOrderId"])
        self.assertEqual("0.0999", record["pending_original_qty"])
        self.assertEqual("0.0999", record["entry_portfolio_quantity"])
        self.assertEqual(1, ledger.get_order_intent_status(self.owner)["unresolved_count"])

    def test_original_stop_inconsistent_execution_cannot_become_active(self):
        self._recover_active_entry()
        for status, executed in (("NEW", "0.001"), ("FILLED", "0.0998"), ("PARTIALLY_FILLED", "0.1")):
            with self.subTest(status=status):
                self._install_observation(pending_status=status, pending_executed=executed)
                stale = ledger.reconcile_spot_opo_intent(self.owner, self.request["listClientOrderId"], force=True)
                self.assertFalse(stale["reconciled"])
                self.assertIn("status conflicts", stale["error"])
                record = ledger._get_order_intent_record(self.owner, self.request["listClientOrderId"])
                self.assertEqual("NEW", record["pending_status"])
                self.assertEqual("0", record["pending_executed_qty"])
                self.assertEqual(1, ledger.get_order_intent_status(self.owner)["unresolved_count"])

    def test_confirmed_original_stop_cancellation_survives_stale_and_failed_refresh(self):
        self._recover_active_entry()

        def cancel_order_list(**_kwargs):
            self._install_observation(pending_status="CANCELED", list_status="ALL_DONE")
            return {}

        self.owner.client.cancel_order_list = cancel_order_list
        self.assertTrue(ledger.cancel_spot_opo_intent(self.owner, self.request["listClientOrderId"])["cancel_confirmed"])
        self._install_observation()
        stale = ledger.reconcile_spot_opo_intent(self.owner, self.request["listClientOrderId"], force=True)
        self.assertFalse(stale["reconciled"])
        self.owner.client.get_order_list = lambda **_kwargs: (_ for _ in ()).throw(TimeoutError("offline timeout"))
        failed = ledger.reconcile_spot_opo_intent(self.owner, self.request["listClientOrderId"], force=True)
        self.assertFalse(failed["reconciled"])
        record = ledger._get_order_intent_record(self.owner, self.request["listClientOrderId"])
        self.assertEqual("accepted", record["state"])
        self.assertEqual("cancelled", record["protection_state"])
        self.assertEqual("confirmed", record["cancel_state"])
        self.assertEqual("CANCELED", record["pending_status"])
        self.assertEqual("0", record["pending_executed_qty"])
        self.assertEqual("ALL_DONE", record["list_status"])
        self.assertEqual(1, ledger.get_order_intent_status(self.owner)["unresolved_count"])

    def _assert_late_original_query_cannot_overwrite_newer_stop_fill(self, *, fail):
        self._recover_active_entry()
        stale_client = self.owner.client
        original_getter = stale_client.get_order_list
        newer_records = []

        def late_get_order_list(**kwargs):
            self._install_observation(pending_status="FILLED", pending_executed="0.0999", list_status="ALL_DONE")
            newer = ledger.reconcile_spot_opo_intent(self.owner, self.request["listClientOrderId"], force=True)
            self.assertEqual("triggered", newer["protection_state"])
            newer_records.append(ledger._get_order_intent_record(self.owner, self.request["listClientOrderId"]))
            self.owner.client = stale_client
            if fail:
                raise TimeoutError("late offline timeout")
            return original_getter(**kwargs)

        stale_client.get_order_list = late_get_order_list
        late = ledger.reconcile_spot_opo_intent(self.owner, self.request["listClientOrderId"], force=True)
        self.assertFalse(late["reconciled"])
        self.assertIn("late result was not applied", late["error"])
        record = ledger._get_order_intent_record(self.owner, self.request["listClientOrderId"])
        self.assertEqual(newer_records[0], record)
        self.assertEqual("FILLED", record["pending_status"])
        self.assertEqual("0.0999", record["pending_executed_qty"])
        self.assertEqual(1, ledger.get_order_intent_status(self.owner)["unresolved_count"])

    def test_late_original_query_success_cannot_overwrite_newer_stop_fill(self):
        self._assert_late_original_query_cannot_overwrite_newer_stop_fill(fail=False)

    def test_late_original_query_failure_cannot_overwrite_newer_stop_fill(self):
        self._assert_late_original_query_cannot_overwrite_newer_stop_fill(fail=True)

    def test_original_stop_fill_recovery_still_completes_after_stale_refresh(self):
        allocation_path = self._recover_active_entry()
        self._install_observation(pending_status="FILLED", pending_executed="0.0999", list_status="ALL_DONE")
        ledger.reconcile_spot_opo_intent(self.owner, self.request["listClientOrderId"], force=True)
        self._install_observation()
        self.assertFalse(ledger.reconcile_spot_opo_intent(
            self.owner, self.request["listClientOrderId"], force=True,
        )["reconciled"])
        self._install_observation(pending_status="FILLED", pending_executed="0.0999", list_status="ALL_DONE")
        ledger.reconcile_spot_opo_intent(self.owner, self.request["listClientOrderId"], force=True)
        record = ledger._get_order_intent_record(self.owner, self.request["listClientOrderId"])
        _, _, order = _observation(
            self.request, pending_status="FILLED", pending_executed="0.0999", list_status="ALL_DONE",
        )
        order.update(cummulativeQuoteQty="9.4905", updateTime=1780000000010)
        trades = [{
            "symbol": "BTCUSDT", "id": 902, "orderId": 302, "price": "95",
            "qty": "0.0999", "quoteQty": "9.4905", "commission": "0", "commissionAsset": "BTC",
            "time": 1780000000010, "isBuyer": False,
        }]
        fill = summarize_spot_opo_stop_sell_fill(record, order, trades, base_asset="BTC", quote_asset="USDT")
        with patch(
            "app.gui.shared.allocation_persistence.get_position_allocations_path",
            return_value=allocation_path,
        ):
            self.assertTrue(persist_spot_opo_stop_sell_allocation(allocation_path, fill))
            marked = ledger._mark_spot_opo_exit_reconciled(
                self.owner, self.request["listClientOrderId"],
                portfolio_signature=fill["signature"], portfolio_quantity=fill["portfolio_qty"],
            )
        self.assertTrue(marked["exit_reconciled"])
        self.assertEqual(0, ledger.get_order_intent_status(self.owner)["unresolved_count"])

    def test_duplicate_buy_id_is_rejected_before_any_protection_query(self):
        self._recover_active_entry()
        path = ledger._intent_path(self.owner)
        before = path.read_bytes()
        queried = []
        self.owner.client.get_order_list = lambda **kwargs: queried.append(kwargs)
        for route in ("opo", "market"):
            with self.subTest(route=route):
                with self.assertRaisesRegex(LiveTradingSafetyError, "already has state accepted"):
                    if route == "opo":
                        ledger._begin_spot_opo_intent(self.owner, self.request, source="duplicate")
                    else:
                        ledger._begin_order_intent(
                            self.owner,
                            {"symbol": "ETHUSDT", "side": "BUY", "type": "MARKET", "quantity": "1",
                             "newClientOrderId": self.request["listClientOrderId"]},
                            market="spot", source="duplicate",
                        )
                self.assertEqual([], queried)
                self.assertEqual(before, path.read_bytes())

    def test_new_opo_buy_refreshes_original_stop_before_persisting_exposure(self):
        self._recover_active_entry()
        self.assertEqual(0, ledger.get_order_intent_status(self.owner)["unresolved_count"])
        self._install_observation(pending_status="CANCELED", list_status="ALL_DONE")

        with self.assertRaises(LiveTradingSafetyError):
            ledger._begin_spot_opo_intent(
                self.owner,
                {**self.request, "listClientOrderId": "next-list", "workingClientOrderId": "next-buy",
                 "pendingClientOrderId": "next-stop"},
                source="new-exposure",
            )

        self.assertIsNone(ledger._get_order_intent_record(self.owner, "next-list"))
        self.assertEqual(1, ledger.get_order_intent_status(self.owner)["unresolved_count"])

    def test_new_market_buy_refreshes_residual_stop_before_persisting_exposure(self):
        allocation_path, baseline = self._recover_partial_strategy_exit()
        _, acknowledgement = self._begin_and_observe_residual_stop(allocation_path, baseline)
        self.assertEqual(0, ledger.get_order_intent_status(self.owner)["unresolved_count"])
        self.owner.client.get_order = lambda **_kwargs: {**acknowledgement, "status": "CANCELED"}

        with self.assertRaises(LiveTradingSafetyError):
            ledger._begin_order_intent(
                self.owner,
                {"symbol": "ETHUSDT", "side": "BUY", "type": "MARKET", "quantity": "1",
                 "newClientOrderId": "next-market-buy"},
                market="spot", source="new-exposure",
            )

        self.assertIsNone(ledger._get_order_intent_record(self.owner, "next-market-buy"))
        self.assertEqual(1, ledger.get_order_intent_status(self.owner)["unresolved_count"])

    def _begin_next_spot_buy(self, route):
        if route == "opo":
            request = {
                **self.request, "listClientOrderId": "next-list", "workingClientOrderId": "next-buy",
                "pendingClientOrderId": "next-stop",
            }
            return ledger._begin_spot_opo_intent(self.owner, request, source="new-exposure")
        return ledger._begin_order_intent(
            self.owner,
            {"symbol": "ETHUSDT", "side": "BUY", "type": "MARKET", "quantity": "1",
             "newClientOrderId": "next-market-buy"},
            market="spot", source="new-exposure",
        )

    def _submit_next_spot_buy(self, route):
        if route == "opo":
            ledger._mark_spot_opo_submitted(self.owner, "next-list", via="test")
        else:
            ledger._mark_order_intent_submitted(
                self.owner,
                {"symbol": "ETHUSDT", "side": "BUY", "type": "MARKET", "quantity": "1",
                 "newClientOrderId": "next-market-buy"},
                via="test",
            )

    def _assert_next_spot_buy_absent(self, route):
        self.assertIsNone(ledger._get_order_intent_record(
            self.owner, "next-list" if route == "opo" else "next-market-buy",
        ))

    def test_both_buy_routes_fail_closed_for_changed_original_protection(self):
        for route in ("opo", "market"):
            for change in ("canceled", "filled", "identity", "offline"):
                with self.subTest(route=route, change=change):
                    self._reset_intent_store()
                    self._recover_active_entry()
                    queried = []
                    if change == "canceled":
                        self._install_observation(pending_status="CANCELED", list_status="ALL_DONE")
                    elif change == "filled":
                        self._install_observation(
                            pending_status="FILLED", pending_executed="0.0999", list_status="ALL_DONE",
                        )
                    elif change == "identity":
                        self._install_observation(wrong_pending_id=True)
                    original_getter = self.owner.client.get_order_list

                    def get_order_list(**kwargs):
                        queried.append(kwargs)
                        if change == "offline":
                            raise TimeoutError("offline protection refresh")
                        return original_getter(**kwargs)

                    self.owner.client.get_order_list = get_order_list
                    with self.assertRaisesRegex(LiveTradingSafetyError, "Fresh exact Spot protection"):
                        self._begin_next_spot_buy(route)
                    self.assertEqual([{"origClientOrderId": self.request["listClientOrderId"]}], queried)
                    self._assert_next_spot_buy_absent(route)
                    self.assertEqual(1, ledger.get_order_intent_status(self.owner)["unresolved_count"])
                    record = ledger._get_order_intent_record(self.owner, self.request["listClientOrderId"])
                    self.assertEqual(302, record["pending_order_id"])
                    self.assertEqual("0.0999", record["pending_original_qty"])
                    self.assertTrue(record["entry_reconciled"])

    def test_both_buy_routes_fail_closed_for_changed_residual_protection(self):
        for route in ("opo", "market"):
            for change in ("canceled", "filled", "identity", "offline"):
                with self.subTest(route=route, change=change):
                    self._reset_intent_store()
                    allocation_path, baseline = self._recover_partial_strategy_exit()
                    request, acknowledgement = self._begin_and_observe_residual_stop(allocation_path, baseline)
                    queried = []

                    def get_order(**kwargs):
                        queried.append(kwargs)
                        if change == "offline":
                            raise TimeoutError("offline residual refresh")
                        changed = dict(acknowledgement)
                        if change == "canceled":
                            changed["status"] = "CANCELED"
                        elif change == "filled":
                            changed.update(status="FILLED", executedQty=baseline["quantity"])
                        elif change == "identity":
                            changed["orderId"] = 999
                        return changed

                    self.owner.client = SimpleNamespace(get_order=get_order)
                    with self.assertRaisesRegex(LiveTradingSafetyError, "Fresh exact Spot protection"):
                        self._begin_next_spot_buy(route)
                    self.assertEqual([{
                        "symbol": "BTCUSDT", "origClientOrderId": request["newClientOrderId"],
                    }], queried)
                    self._assert_next_spot_buy_absent(route)
                    self.assertEqual(1, ledger.get_order_intent_status(self.owner)["unresolved_count"])
                    record = ledger._get_order_intent_record(self.owner, self.request["listClientOrderId"])
                    self.assertEqual(510, record["residual_stop_order_id"])
                    self.assertEqual(request, record["residual_stop_request"])
                    self.assertEqual("confirmed", record["cancel_state"])

    def test_both_buy_routes_refresh_original_protection_at_begin_and_submission(self):
        for route in ("opo", "market"):
            with self.subTest(route=route):
                self._reset_intent_store()
                self._recover_active_entry()
                queried = []
                original_list_getter = self.owner.client.get_order_list
                original_order_getter = self.owner.client.get_order

                def get_order_list(**kwargs):
                    queried.append(("list", kwargs["origClientOrderId"]))
                    return original_list_getter(**kwargs)

                def get_order(**kwargs):
                    queried.append(("order", kwargs["origClientOrderId"]))
                    return original_order_getter(**kwargs)

                self.owner.client.get_order_list = get_order_list
                self.owner.client.get_order = get_order
                self._begin_next_spot_buy(route)
                self._submit_next_spot_buy(route)
                expected = [
                    ("list", self.request["listClientOrderId"]),
                    ("order", self.request["workingClientOrderId"]),
                    ("order", self.request["pendingClientOrderId"]),
                ]
                self.assertEqual(expected * 2, queried)
                record = ledger._get_order_intent_record(
                    self.owner, "next-list" if route == "opo" else "next-market-buy",
                )
                self.assertEqual("submitted", record["state"])

    def test_both_buy_routes_refresh_residual_protection_at_begin_and_submission(self):
        for route in ("opo", "market"):
            with self.subTest(route=route):
                self._reset_intent_store()
                allocation_path, baseline = self._recover_partial_strategy_exit()
                request, acknowledgement = self._begin_and_observe_residual_stop(allocation_path, baseline)
                queried = []

                def get_order(**kwargs):
                    queried.append(kwargs)
                    return acknowledgement

                self.owner.client = SimpleNamespace(get_order=get_order)
                self._begin_next_spot_buy(route)
                self._submit_next_spot_buy(route)
                self.assertEqual([{
                    "symbol": "BTCUSDT", "origClientOrderId": request["newClientOrderId"],
                }] * 2, queried)

    def test_protection_changed_after_begin_blocks_both_submitted_transitions(self):
        for route in ("opo", "market"):
            with self.subTest(route=route):
                self._reset_intent_store()
                self._recover_active_entry()
                self._begin_next_spot_buy(route)
                self._install_observation(pending_status="CANCELED", list_status="ALL_DONE")
                with self.assertRaisesRegex(LiveTradingSafetyError, "Fresh exact Spot protection"):
                    self._submit_next_spot_buy(route)
                pending = ledger._get_order_intent_record(
                    self.owner, "next-list" if route == "opo" else "next-market-buy",
                )
                self.assertEqual("pending", pending["state"])
                self.assertEqual(2, ledger.get_order_intent_status(self.owner)["unresolved_count"])

    def test_protection_snapshot_changed_after_query_blocks_begin_and_submission(self):
        for route in ("opo", "market"):
            for boundary in ("begin", "submit"):
                with self.subTest(route=route, boundary=boundary):
                    self._reset_intent_store()
                    self._recover_active_entry()
                    if boundary == "submit":
                        self._begin_next_spot_buy(route)
                    refresh = ledger._refresh_spot_active_protection

                    def raced_refresh(*args, **kwargs):
                        proof = refresh(*args, **kwargs)
                        record = ledger._get_order_intent_record(self.owner, self.request["listClientOrderId"])
                        ledger._update_order_intent_by_id(
                            self.owner, self.request["listClientOrderId"], state="accepted",
                            expected_record=record, source="concurrent protection observation",
                        )
                        return proof

                    with patch.object(ledger, "_refresh_spot_active_protection", side_effect=raced_refresh):
                        with self.assertRaisesRegex(LiveTradingSafetyError, "changed after its exact refresh"):
                            if boundary == "begin":
                                self._begin_next_spot_buy(route)
                            else:
                                self._submit_next_spot_buy(route)
                    if boundary == "begin":
                        self._assert_next_spot_buy_absent(route)
                    else:
                        self.assertEqual("pending", ledger._get_order_intent_record(
                            self.owner, "next-list" if route == "opo" else "next-market-buy",
                        )["state"])

    def test_late_original_refresh_cannot_authorize_new_exposure(self):
        self._recover_active_entry()
        stale_client = self.owner.client
        original_getter = stale_client.get_order_list

        def raced_get_order_list(**kwargs):
            self._install_observation(pending_status="FILLED", pending_executed="0.0999", list_status="ALL_DONE")
            ledger.reconcile_spot_opo_intent(self.owner, self.request["listClientOrderId"], force=True)
            self.owner.client = stale_client
            return original_getter(**kwargs)

        stale_client.get_order_list = raced_get_order_list
        with self.assertRaisesRegex(LiveTradingSafetyError, "Fresh exact Spot protection"):
            self._begin_next_spot_buy("opo")
        self._assert_next_spot_buy_absent("opo")
        self.assertEqual("FILLED", ledger._get_order_intent_record(
            self.owner, self.request["listClientOrderId"],
        )["pending_status"])
        self.assertEqual(1, ledger.get_order_intent_status(self.owner)["unresolved_count"])

    def test_late_residual_refresh_cannot_authorize_new_exposure(self):
        allocation_path, baseline = self._recover_partial_strategy_exit()
        _, acknowledgement = self._begin_and_observe_residual_stop(allocation_path, baseline)

        def raced_get_order(**_kwargs):
            ledger._mark_spot_opo_residual_stop_order_observed(
                self.owner, self.request["listClientOrderId"],
                order_response={**acknowledgement, "status": "CANCELED"}, exact_query=True,
            )
            return acknowledgement

        self.owner.client = SimpleNamespace(get_order=raced_get_order)
        with self.assertRaisesRegex(LiveTradingSafetyError, "Fresh exact Spot protection"):
            self._begin_next_spot_buy("market")
        self._assert_next_spot_buy_absent("market")
        self.assertEqual("CANCELED", ledger._get_order_intent_record(
            self.owner, self.request["listClientOrderId"],
        )["residual_stop_status"])
        self.assertEqual(1, ledger.get_order_intent_status(self.owner)["unresolved_count"])

    def test_batch_and_individual_reconciliation_poll_resolved_original_protection(self):
        for batch in (False, True):
            with self.subTest(batch=batch):
                self._reset_intent_store()
                self._recover_active_entry()
                self._install_observation(pending_status="FILLED", pending_executed="0.0999", list_status="ALL_DONE")
                if batch:
                    results = ledger.reconcile_unresolved_order_intents(self.owner, limit=1)
                    self.assertEqual(1, len(results))
                    result = results[0]
                else:
                    result = ledger.reconcile_order_intent(self.owner, self.request["listClientOrderId"])
                self.assertFalse(result["reconciled"])
                self.assertEqual("triggered", result["protection_state"])
                self.assertEqual(1, ledger.get_order_intent_status(self.owner)["unresolved_count"])

    def test_batch_reconciliation_polls_resolved_residual_protection(self):
        allocation_path, baseline = self._recover_partial_strategy_exit()
        _, acknowledgement = self._begin_and_observe_residual_stop(allocation_path, baseline)
        self.owner.client = SimpleNamespace(get_order=lambda **_kwargs: {**acknowledgement, "status": "CANCELED"})

        results = ledger.reconcile_unresolved_order_intents(self.owner, limit=1)

        self.assertEqual(1, len(results))
        self.assertFalse(results[0]["reconciled"])
        self.assertEqual("triggered", results[0]["residual_stop_state"])
        self.assertEqual(1, ledger.get_order_intent_status(self.owner)["unresolved_count"])

    def test_resolved_no_fill_records_do_not_consume_batch_monitoring_limit(self):
        self._submit()
        self._install_observation(
            working_status="EXPIRED", working_executed="0", pending_status="PENDING_NEW", list_status="ALL_DONE",
        )
        ledger.reconcile_spot_opo_intent(self.owner, self.request["listClientOrderId"])
        queried = []
        self.owner.client.get_order_list = lambda **kwargs: queried.append(kwargs)

        self.assertEqual([], ledger.reconcile_unresolved_order_intents(self.owner, limit=1))
        self.assertEqual([], queried)

    def test_reducing_sell_for_other_symbol_does_not_refresh_active_protection(self):
        self._recover_active_entry()
        queried = []
        self.owner.client.get_order_list = lambda **kwargs: queried.append(kwargs)

        record = ledger._begin_order_intent(
            self.owner,
            {"symbol": "ETHUSDT", "side": "SELL", "type": "MARKET", "quantity": "1",
             "newClientOrderId": "reducing-sell"},
            market="spot", source="reducing-exit",
        )
        ledger._mark_order_intent_submitted(
            self.owner, {"newClientOrderId": "reducing-sell"}, via="test",
        )

        self.assertEqual("SELL", record["side"])
        self.assertEqual([], queried)

    def _add_second_recovered_active_entry(self):
        request = {
            **self.request, "listClientOrderId": "other-list", "workingClientOrderId": "other-buy",
            "pendingClientOrderId": "other-stop",
        }
        ledger._begin_spot_opo_intent(self.owner, request, source="second-protected-entry")
        ledger._mark_spot_opo_submitted(self.owner, request["listClientOrderId"], via="test")
        list_response, working, pending = _observation(request)
        list_response["orderListId"] = 400
        list_response["orders"][0]["orderId"] = working["orderId"] = 401
        list_response["orders"][1]["orderId"] = pending["orderId"] = 402
        working["orderListId"] = pending["orderListId"] = 400
        original_client = self.owner.client
        children = {working["clientOrderId"]: working, pending["clientOrderId"]: pending}
        self.owner.client = SimpleNamespace(
            get_order_list=lambda **kwargs: (
                list_response if kwargs["origClientOrderId"] == request["listClientOrderId"]
                else original_client.get_order_list(**kwargs)
            ),
            get_order=lambda **kwargs: (
                children[kwargs["origClientOrderId"]] if kwargs["origClientOrderId"] in children
                else original_client.get_order(**kwargs)
            ),
        )
        ledger.reconcile_spot_opo_intent(self.owner, request["listClientOrderId"])
        fill = {
            "symbol": "BTCUSDT", "client_order_id": request["listClientOrderId"],
            "exchange_client_order_id": request["workingClientOrderId"], "order_id": 401,
            "trade_ids": [903], "trade_count": 1, "gross_qty": "0.1", "net_qty": "0.0999",
            "pending_order_qty": "0.0999", "gross_quote_qty": "10", "net_quote_cost": "9.99",
            "average_cost": "100", "commissions": [], "base_asset": "BTC", "quote_asset": "USDT",
            "fill_time_ms": 1780000000001, "signature": "d" * 64,
        }
        with patch(
            "app.gui.shared.allocation_persistence.get_position_allocations_path",
            return_value=self.allocation_path,
        ):
            persist_spot_buy_allocation(self.allocation_path, fill)
            ledger._mark_spot_opo_entry_reconciled(
                self.owner, request["listClientOrderId"], portfolio_signature="d" * 64, portfolio_quantity="0.0999",
            )
        return request, list_response, working, pending

    def test_new_exposure_refreshes_every_active_stop_across_symbols(self):
        self._recover_active_entry()
        other_request, _, _, _ = self._add_second_recovered_active_entry()
        self.assertEqual(0, ledger.get_order_intent_status(self.owner)["unresolved_count"])
        original_getter = self.owner.client.get_order_list
        queried = []

        def get_order_list(**kwargs):
            queried.append(kwargs["origClientOrderId"])
            return original_getter(**kwargs)

        self.owner.client.get_order_list = get_order_list
        # The incoming MARKET BUY is ETHUSDT; both existing protections are BTCUSDT.
        self._begin_next_spot_buy("market")
        self._submit_next_spot_buy("market")
        self.assertEqual([
            self.request["listClientOrderId"], other_request["listClientOrderId"],
        ] * 2, queried)

    def test_monitoring_limit_cannot_hide_an_unqueried_stop_from_new_exposure(self):
        self._recover_active_entry()
        other_request, list_response, _, pending = self._add_second_recovered_active_entry()
        result = ledger.reconcile_unresolved_order_intents(self.owner, limit=1)
        self.assertEqual(1, len(result))
        self.assertEqual(self.request["listClientOrderId"], result[0]["client_order_id"])
        list_response.update(listStatusType="ALL_DONE", listOrderStatus="ALL_DONE")
        pending["status"] = "CANCELED"

        with self.assertRaisesRegex(LiveTradingSafetyError, "Fresh exact Spot protection"):
            self._begin_next_spot_buy("opo")

        self._assert_next_spot_buy_absent("opo")
        record = ledger._get_order_intent_record(self.owner, other_request["listClientOrderId"])
        self.assertEqual("CANCELED", record["pending_status"])
        self.assertEqual(1, ledger.get_order_intent_status(self.owner)["unresolved_count"])

    def test_real_entry_functions_do_not_post_when_protection_changes_after_begin(self):
        for route in ("opo", "market"):
            with self.subTest(route=route):
                self._reset_intent_store()
                self._recover_active_entry()
                self.owner.account_type = "SPOT"
                events = []
                posts = []

                def create_order(**kwargs):
                    posts.append(kwargs)
                    return {}

                def cancel_protection():
                    self._install_observation(pending_status="CANCELED", list_status="ALL_DONE")
                    self.owner.client.create_order = create_order
                    self.owner.client.create_order_list_opo = create_order

                def begin_market(params, **kwargs):
                    result = ledger._begin_order_intent(self.owner, params, **kwargs)
                    events.append("begin")
                    cancel_protection()
                    return result

                def begin_opo(request, **kwargs):
                    result = ledger._begin_spot_opo_intent(self.owner, request, **kwargs)
                    events.append("begin")
                    cancel_protection()
                    return result

                self.owner._guard_live_order_submit = lambda **_kwargs: events.append("guard")
                self.owner._begin_order_intent = begin_market
                self.owner._begin_spot_opo_intent = begin_opo
                self.owner._mark_order_intent_submitted = lambda params, **kwargs: ledger._mark_order_intent_submitted(
                    self.owner, params, **kwargs,
                )
                self.owner._mark_spot_opo_submitted = lambda client_id, **kwargs: ledger._mark_spot_opo_submitted(
                    self.owner, client_id, **kwargs,
                )
                self.owner._mark_order_intent_accepted = lambda params, **kwargs: ledger._mark_order_intent_accepted(
                    self.owner, params, **kwargs,
                )
                self.owner._mark_spot_opo_accepted = lambda request, **kwargs: ledger._mark_spot_opo_accepted(
                    self.owner, request, **kwargs,
                )
                self.owner._mark_order_intent_unknown = lambda params, **kwargs: ledger._mark_order_intent_unknown(
                    self.owner, params, **kwargs,
                )
                self.owner._mark_spot_opo_unknown = lambda client_id, **kwargs: ledger._mark_spot_opo_unknown(
                    self.owner, client_id, **kwargs,
                )
                self.owner.reconcile_spot_opo_intent = lambda client_id, **kwargs: ledger.reconcile_spot_opo_intent(
                    self.owner, client_id, **kwargs,
                )
                self.owner.get_spot_symbol_filters = lambda _symbol: {
                    "stepSize": 0.0001, "minQty": 0.0001, "minNotional": 5,
                }
                self.owner._floor_to_step = _floor_to_step
                self.owner.get_symbol_info_spot = lambda _symbol: _symbol_info()
                self.owner.client.create_order = create_order
                self.owner.client.create_order_list_opo = create_order
                if route == "opo":
                    result = place_spot_opo_entry(
                        self.owner, "BTCUSDT", "BUY", "100.00", "0.1000", "95.00",
                        list_client_order_id="next-list", working_client_order_id="next-buy",
                        pending_client_order_id="next-stop",
                    )
                else:
                    result = place_spot_market_order(self.owner, "ETHUSDT", "BUY", quantity=1, price=100)

                self.assertFalse(result["ok"])
                self.assertIn("Fresh exact Spot protection", result["error"])
                self.assertEqual(["guard", "begin"], events)
                self.assertEqual([], posts)
                self.assertEqual("CANCELED", ledger._get_order_intent_record(
                    self.owner, self.request["listClientOrderId"],
                )["pending_status"])

    def test_strategy_market_sell_is_blocked_while_linked_opo_stop_is_active(self):
        self._submit()
        ledger._mark_spot_opo_unknown(self.owner, self.request["listClientOrderId"], error="restart recovery")
        self._install_observation()
        ledger.reconcile_spot_opo_intent(self.owner, self.request["listClientOrderId"])
        allocation_path = Path(self.owner._order_audit_log_path).with_name("allocations.json")
        fill = {
            "symbol": "BTCUSDT", "client_order_id": self.request["listClientOrderId"],
            "exchange_client_order_id": self.request["workingClientOrderId"], "order_id": 301,
            "trade_ids": [901], "trade_count": 1, "gross_qty": "0.1", "net_qty": "0.0999",
            "pending_order_qty": "0.0999", "gross_quote_qty": "10", "net_quote_cost": "9.99",
            "average_cost": "100", "commissions": [], "base_asset": "BTC", "quote_asset": "USDT",
            "fill_time_ms": 1780000000000, "signature": "c" * 64,
        }
        with patch(
            "app.gui.shared.allocation_persistence.get_position_allocations_path",
            return_value=allocation_path,
        ):
            persist_spot_buy_allocation(allocation_path, fill)
            ledger._mark_spot_opo_entry_reconciled(
                self.owner, self.request["listClientOrderId"],
                portfolio_signature="c" * 64, portfolio_quantity="0.0999",
            )

        with self.assertRaisesRegex(LiveTradingSafetyError, "OPO stop reserves inventory"):
            ledger._begin_order_intent(
                self.owner,
                {
                    "newClientOrderId": "strategy-sell-001", "symbol": "BTCUSDT",
                    "side": "SELL", "type": "MARKET", "quantity": "0.0999",
                },
                market="spot", source="offline-strategy-sell-test",
            )
        self.assertIsNone(ledger._get_order_intent_record(self.owner, "strategy-sell-001"))
        self.assertEqual(0, ledger.get_order_intent_status(self.owner)["unresolved_count"])

    def test_linked_sell_intent_is_durable_and_blocks_after_restart(self):
        self._recover_active_entry()
        intent = self._begin_strategy_exit(
            self.owner,
            self.request["listClientOrderId"],
            "strategy-exit-001",
        )
        self.assertEqual("submitted", intent["strategy_exit_state"])
        self.assertEqual("STOP_ON_FAILURE", intent["strategy_exit_request"]["cancelReplaceMode"])
        self.assertEqual("ONLY_NEW", intent["strategy_exit_request"]["cancelRestrictions"])
        self.assertEqual("0.0999", intent["strategy_exit_quantity"])
        self.assertEqual(1, ledger.get_order_intent_status(self.owner)["unresolved_count"])

        restarted_owner = SimpleNamespace(
            _order_audit_log_path=self.owner._order_audit_log_path,
            api_key=self.owner.api_key,
            mode=self.owner.mode,
        )
        restored = ledger._get_order_intent_record(restarted_owner, self.request["listClientOrderId"])
        self.assertEqual("strategy-exit-001", restored["strategy_exit_client_order_id"])
        self.assertTrue(ledger._is_unresolved(restored))
        with self.assertRaisesRegex(LiveTradingSafetyError, "no prior exit attempt"):
            self._begin_strategy_exit(
                restarted_owner,
                self.request["listClientOrderId"],
                "strategy-exit-002",
            )

    def test_rejected_cancel_replace_resolves_only_after_exact_active_stop_requery(self):
        self._recover_active_entry()
        self._begin_strategy_exit(self.owner, self.request["listClientOrderId"], "strategy-exit-003")
        marked = ledger._mark_spot_opo_strategy_exit_response(
            self.owner,
            self.request["listClientOrderId"],
            response=_cancel_replace_response(
                new_client_order_id="strategy-exit-003", cancel_result="FAILURE",
            ),
        )
        self.assertEqual("cancel_failed", marked["strategy_exit_state"])
        self.assertEqual(1, ledger.get_order_intent_status(self.owner)["unresolved_count"])

        self._install_observation()
        reconciled = ledger.reconcile_spot_opo_intent(self.owner, self.request["listClientOrderId"])
        record = ledger._get_order_intent_record(self.owner, self.request["listClientOrderId"])
        self.assertTrue(reconciled["reconciled"])
        self.assertEqual("active", record["protection_state"])
        self.assertEqual("rejected", record["cancel_state"])
        self.assertEqual("no_effect", record["strategy_exit_state"])
        self.assertEqual(0, ledger.get_order_intent_status(self.owner)["unresolved_count"])

        self._install_observation(
            pending_status="FILLED", pending_executed="0.0999", list_status="ALL_DONE",
        )
        later_stop_fill = ledger.reconcile_spot_opo_intent(
            self.owner, self.request["listClientOrderId"], force=True,
        )
        self.assertEqual("triggered", later_stop_fill["protection_state"])
        self.assertEqual(1, ledger.get_order_intent_status(self.owner)["unresolved_count"])

    def test_canceled_stop_with_rejected_sell_remains_blocked_after_exact_requery(self):
        self._recover_active_entry()
        self._begin_strategy_exit(self.owner, self.request["listClientOrderId"], "strategy-exit-004")
        marked = ledger._mark_spot_opo_strategy_exit_response(
            self.owner,
            self.request["listClientOrderId"],
            response=_cancel_replace_response(
                new_client_order_id="strategy-exit-004", new_result="FAILURE",
            ),
        )
        self.assertTrue(marked["requires_stop_rearm"])
        self._install_observation(
            pending_status="CANCELED", pending_executed="0", list_status="ALL_DONE",
        )

        reconciled = ledger.reconcile_spot_opo_intent(self.owner, self.request["listClientOrderId"])
        record = ledger._get_order_intent_record(self.owner, self.request["listClientOrderId"])
        self.assertEqual("cancelled", reconciled["protection_state"])
        self.assertEqual("stop_cancelled", record["strategy_exit_state"])
        self.assertTrue(ledger._is_unresolved(record))
        self.assertEqual(1, ledger.get_order_intent_status(self.owner)["unresolved_count"])

    def test_open_order_audit_tracks_linked_strategy_sell_by_its_exact_client_id(self):
        self._recover_active_entry()
        self._begin_strategy_exit(self.owner, self.request["listClientOrderId"], "strategy-exit-005")
        response = _cancel_replace_response(new_client_order_id="strategy-exit-005")
        response["newOrderResponse"]["status"] = "NEW"
        response["newOrderResponse"]["executedQty"] = "0"
        ledger._mark_spot_opo_strategy_exit_response(
            self.owner, self.request["listClientOrderId"], response=response,
        )
        self._install_observation(
            pending_status="CANCELED", pending_executed="0", list_status="ALL_DONE",
        )
        ledger.reconcile_spot_opo_intent(self.owner, self.request["listClientOrderId"])

        status = ledger.get_spot_open_order_reconciliation_status(self.owner, [{
            "symbol": "BTCUSDT", "clientOrderId": "strategy-exit-005", "orderId": 401, "status": "NEW",
        }])
        self.assertEqual(1, status["matched_open_order_count"])
        self.assertEqual(0, status["unmatched_exchange_open_order_count"])
        self.assertEqual(0, status["local_open_orders_missing_from_exchange_count"])
        self.assertEqual(0, status["local_open_order_status_conflict_count"])

    def test_full_linked_sell_is_reconciled_to_exact_opo_allocation_and_completes_durably(self):
        self._recover_active_entry()
        self._begin_strategy_exit(self.owner, self.request["listClientOrderId"], "strategy-exit-complete")
        ledger._mark_spot_opo_strategy_exit_response(
            self.owner,
            self.request["listClientOrderId"],
            response=_cancel_replace_response(new_client_order_id="strategy-exit-complete"),
        )
        self._install_observation(
            pending_status="CANCELED", pending_executed="0", list_status="ALL_DONE",
        )
        ledger.reconcile_spot_opo_intent(self.owner, self.request["listClientOrderId"], force=True)
        exit_order = {
            "symbol": "BTCUSDT", "clientOrderId": "strategy-exit-complete", "orderId": 401,
            "orderListId": -1, "side": "SELL", "type": "MARKET", "status": "FILLED",
            "origQty": "0.0999", "executedQty": "0.0999", "cummulativeQuoteQty": "1898.1",
            "updateTime": 1780000000010,
        }
        ledger._mark_spot_opo_strategy_exit_order_observed(
            self.owner, self.request["listClientOrderId"], order_response=exit_order,
        )
        intent = ledger._get_order_intent_record(self.owner, self.request["listClientOrderId"])
        self.assertIsNotNone(intent)
        exit_trades = [{
            "symbol": "BTCUSDT", "id": 901, "orderId": 401, "price": "19000",
            "qty": "0.0999", "quoteQty": "1898.1", "commission": "0", "commissionAsset": "BTC",
            "time": 1780000000010, "isBuyer": False,
        }]
        fill = summarize_spot_opo_strategy_sell_fill(
            intent, exit_order, exit_trades, base_asset="BTC", quote_asset="USDT",
        )
        persist_spot_opo_strategy_sell_allocation(self.allocation_path, fill)
        ledger._mark_spot_opo_strategy_exit_reconciled(
            self.owner,
            self.request["listClientOrderId"],
            allocation_path=self.allocation_path,
            portfolio_signature=str(fill["signature"]),
            portfolio_quantity=fill["portfolio_qty"],
            trade_ids=list(fill["trade_ids"]),
            fill_time_ms=int(fill["fill_time_ms"]),
        )

        restarted_owner = SimpleNamespace(
            _order_audit_log_path=self.owner._order_audit_log_path,
            api_key=self.owner.api_key,
            mode=self.owner.mode,
        )
        restored = ledger._get_order_intent_record(restarted_owner, self.request["listClientOrderId"])
        self.assertEqual("completed", restored["strategy_exit_state"])
        self.assertEqual("closed", restored["protection_state"])
        self.assertTrue(restored["strategy_exit_portfolio_reconciled"])
        self.assertFalse(ledger._is_unresolved(restored))
        self.assertEqual(0, ledger.get_order_intent_status(restarted_owner)["unresolved_count"])

    def test_partial_linked_sell_rearm_ack_is_unresolved_until_exact_new_stop_query(self):
        allocation_path, baseline = self._recover_partial_strategy_exit()
        record = ledger._get_order_intent_record(self.owner, self.request["listClientOrderId"])
        self.assertEqual("rearm_required", record["residual_stop_state"])
        self.assertEqual("0.0399", baseline["quantity"])
        self.assertTrue(ledger._is_unresolved(record))

        request, acknowledgement = self._begin_and_observe_residual_stop(
            allocation_path, baseline, exact_query=False,
        )
        acknowledged = ledger._get_order_intent_record(self.owner, self.request["listClientOrderId"])
        self.assertEqual("acknowledged", acknowledged["residual_stop_state"])
        self.assertFalse(acknowledged["residual_stop_query_verified"])
        self.assertTrue(ledger._is_unresolved(acknowledged))

        restarted_owner = SimpleNamespace(
            _order_audit_log_path=self.owner._order_audit_log_path,
            api_key=self.owner.api_key,
            mode=self.owner.mode,
        )
        self.assertEqual(1, ledger.get_order_intent_status(restarted_owner)["unresolved_count"])
        with self.assertRaisesRegex(LiveTradingSafetyError, "exact re-arm-required OPO allocation"):
            ledger._begin_spot_opo_residual_stop(
                restarted_owner,
                self.request["listClientOrderId"],
                allocation_path=allocation_path,
                request=request,
                pre_order_portfolio_signature=baseline["signature"],
                pre_order_portfolio_quantity=baseline["quantity"],
            )

        exact = ledger._mark_spot_opo_residual_stop_order_observed(
            restarted_owner,
            self.request["listClientOrderId"],
            order_response=acknowledgement,
            exact_query=True,
        )
        self.assertEqual("NEW", exact["status"])
        active = ledger._get_order_intent_record(restarted_owner, self.request["listClientOrderId"])
        self.assertEqual("active", active["residual_stop_state"])
        self.assertFalse(ledger._is_unresolved(active))
        self.assertEqual(0, ledger.get_order_intent_status(restarted_owner)["unresolved_count"])

        audit = ledger.get_spot_open_order_reconciliation_status(restarted_owner, [{
            "symbol": "BTCUSDT", "clientOrderId": "residual-stop-001", "orderId": 510, "status": "NEW",
        }])
        self.assertEqual(1, audit["matched_open_order_count"])
        self.assertEqual(0, audit["unmatched_exchange_open_order_count"])
        self.assertEqual(0, audit["local_open_orders_missing_from_exchange_count"])
        with self.assertRaisesRegex(LiveTradingSafetyError, "including a re-armed residual stop"):
            ledger._begin_order_intent(
                restarted_owner,
                {
                    "newClientOrderId": "strategy-sell-after-rearm", "symbol": "BTCUSDT",
                    "side": "SELL", "type": "MARKET", "quantity": baseline["quantity"],
                },
                market="spot", source="offline-residual-stop-sell-test",
            )

    def _recover_partial_residual_stop(self):
        allocation_path, baseline = self._recover_partial_strategy_exit()
        request, acknowledgement = self._begin_and_observe_residual_stop(allocation_path, baseline)
        order = {
            **acknowledgement, "status": "CANCELED", "executedQty": "0.01",
            "cummulativeQuoteQty": "0.95", "updateTime": 1780000000040,
        }
        ledger._mark_spot_opo_residual_stop_order_observed(
            self.owner, self.request["listClientOrderId"], order_response=order, exact_query=True,
        )
        intent = ledger._get_order_intent_record(self.owner, self.request["listClientOrderId"])
        trades = [{
            "symbol": "BTCUSDT", "id": 911, "orderId": 510, "price": "95",
            "qty": "0.01", "quoteQty": "0.95", "commission": "0", "commissionAsset": "BTC",
            "time": 1780000000040, "isBuyer": False,
        }]
        fill = summarize_spot_opo_residual_stop_sell_fill(
            intent, order, trades, base_asset="BTC", quote_asset="USDT",
        )
        self.assertTrue(persist_spot_opo_residual_stop_allocation(allocation_path, fill))
        ledger._mark_spot_opo_residual_stop_reconciled(
            self.owner, self.request["listClientOrderId"], allocation_path=allocation_path,
            fill_signature=str(fill["signature"]), consumed_quantity=fill["portfolio_qty"],
            remaining_quantity=Decimal("0.0299"), trade_ids=list(fill["trade_ids"]),
            fill_time_ms=int(fill["fill_time_ms"]),
        )
        return allocation_path, request, fill

    def test_terminal_partial_residual_stop_can_rearm_after_restart(self):
        allocation_path, request, fill = self._recover_partial_residual_stop()
        self.owner = SimpleNamespace(
            _order_audit_log_path=self.owner._order_audit_log_path,
            api_key=self.owner.api_key, mode=self.owner.mode,
        )
        restored = ledger._get_order_intent_record(self.owner, self.request["listClientOrderId"])
        self.assertEqual("rearm_required", restored["residual_stop_state"])
        self.assertEqual("0.0299", restored["residual_rearm_quantity"])
        self.assertTrue(ledger._is_unresolved(restored))
        next_baseline = spot_opo_allocation_baseline(
            allocation_path, symbol="BTCUSDT", list_client_order_id=self.request["listClientOrderId"],
            expected_quantity="0.0299",
        )
        next_request, _next_ack = self._begin_and_observe_residual_stop(
            allocation_path, next_baseline, client_order_id="residual-stop-002",
        )
        latest = ledger._get_order_intent_record(self.owner, self.request["listClientOrderId"])
        self.assertEqual(next_request, latest["residual_stop_request"])
        self.assertEqual(request, latest["residual_stop_history"][0]["request"])
        self.assertEqual(fill["signature"], latest["residual_stop_history"][0]["recovery_signature"])

    def test_partial_residual_rearm_rejects_incomplete_or_conflicting_prior_proof(self):
        self._recover_partial_residual_stop()
        path = ledger._intent_path(self.owner)
        original = path.read_text(encoding="utf-8")
        for field, value in (
            ("residual_stop_query_verified", False),
            ("residual_stop_request_signature", "a" * 64),
            ("residual_stop_recovery_quantity", "0.02"),
            ("residual_stop_status", "NEW"),
            ("residual_stop_recovery_signature", None),
            ("residual_stop_recovery_trade_ids", []),
            ("residual_stop_recovery_trade_ids", [911, 911]),
            ("residual_stop_recovery_fill_time_ms", None),
            ("residual_stop_executed_qty", "0"),
        ):
            with self.subTest(field=field):
                payload = json.loads(original)
                payload["intents"][self.request["listClientOrderId"]][field] = value
                path.write_text(json.dumps(payload), encoding="utf-8")
                with self.assertRaises(LiveTradingSafetyError):
                    ledger._get_order_intent_record(self.owner, self.request["listClientOrderId"])
        path.write_text(original, encoding="utf-8")

    def test_force_reconciliation_refreshes_exact_active_residual_stop(self):
        allocation_path, baseline = self._recover_partial_strategy_exit()
        request, acknowledgement = self._begin_and_observe_residual_stop(allocation_path, baseline)
        self._install_observation(pending_status="CANCELED", list_status="ALL_DONE")
        original_getter = self.owner.client.get_order
        queried = []

        def get_order(**kwargs):
            queried.append(kwargs["origClientOrderId"])
            if kwargs["origClientOrderId"] == request["newClientOrderId"]:
                return {**acknowledgement, "status": "CANCELED"}
            return original_getter(**kwargs)

        self.owner.client.get_order = get_order
        result = ledger.reconcile_spot_opo_intent(self.owner, self.request["listClientOrderId"], force=True)
        self.assertIn(request["newClientOrderId"], queried)
        self.assertFalse(result["reconciled"])
        restored = ledger._get_order_intent_record(self.owner, self.request["listClientOrderId"])
        self.assertEqual("triggered", restored["residual_stop_state"])
        self.assertEqual("CANCELED", restored["residual_stop_status"])
        self.assertEqual(1, ledger.get_order_intent_status(self.owner)["unresolved_count"])

    def test_failed_residual_stop_refresh_invalidates_old_active_proof_after_restart(self):
        allocation_path, baseline = self._recover_partial_strategy_exit()
        _request, acknowledgement = self._begin_and_observe_residual_stop(allocation_path, baseline)

        def failed_getter(**_kwargs):
            raise TimeoutError("offline query timeout")

        self.owner.client = SimpleNamespace(get_order=failed_getter)
        result = ledger.reconcile_spot_opo_intent(self.owner, self.request["listClientOrderId"], force=True)
        self.assertFalse(result["reconciled"])
        self.owner = SimpleNamespace(
            _order_audit_log_path=self.owner._order_audit_log_path,
            api_key=self.owner.api_key, mode=self.owner.mode,
        )
        record = ledger._get_order_intent_record(self.owner, self.request["listClientOrderId"])
        self.assertEqual("acknowledged", record["residual_stop_state"])
        self.assertFalse(record["residual_stop_query_verified"])
        self.assertEqual(510, record["residual_stop_order_id"])
        self.assertEqual("0", record["residual_stop_executed_qty"])
        self.assertEqual(1, ledger.get_order_intent_status(self.owner)["unresolved_count"])
        with self.assertRaisesRegex(LiveTradingSafetyError, "Unresolved exchange order intent"):
            ledger._begin_spot_opo_intent(
                self.owner, {**self.request, "listClientOrderId": "op-list-002",
                             "workingClientOrderId": "op-buy-002", "pendingClientOrderId": "op-stop-002"},
                source="offline-test",
            )
        self.owner.client = SimpleNamespace(get_order=lambda **_kwargs: acknowledgement)
        recovered = ledger.reconcile_spot_opo_intent(self.owner, self.request["listClientOrderId"])
        self.assertTrue(recovered["reconciled"])
        self.assertEqual(0, ledger.get_order_intent_status(self.owner)["unresolved_count"])

    def test_residual_stop_refresh_rejects_changed_identity(self):
        allocation_path, baseline = self._recover_partial_strategy_exit()
        _request, acknowledgement = self._begin_and_observe_residual_stop(allocation_path, baseline)
        for changes in ({"clientOrderId": "unrelated-order"}, {"orderId": 999}):
            with self.subTest(changes=changes):
                self.owner.client = SimpleNamespace(get_order=lambda **_kwargs: {**acknowledgement, **changes})
                result = ledger.reconcile_spot_opo_intent(self.owner, self.request["listClientOrderId"], force=True)
                self.assertFalse(result["reconciled"])
                record = ledger._get_order_intent_record(self.owner, self.request["listClientOrderId"])
                self.assertEqual(510, record["residual_stop_order_id"])
                self.assertFalse(record["residual_stop_query_verified"])
                self.assertTrue(ledger._is_unresolved(record))

    def _assert_residual_stop_execution_stays_unresolved(self, *, status, executed_quantity):
        allocation_path, baseline = self._recover_partial_strategy_exit()
        _request, acknowledgement = self._begin_and_observe_residual_stop(allocation_path, baseline)
        self.owner.client = SimpleNamespace(get_order=lambda **_kwargs: {
            **acknowledgement, "status": status, "executedQty": executed_quantity,
        })
        result = ledger.reconcile_spot_opo_intent(self.owner, self.request["listClientOrderId"], force=True)
        self.assertFalse(result["reconciled"])
        self.assertEqual("triggered", result["residual_stop_state"])
        self.assertEqual(1, ledger.get_order_intent_status(self.owner)["unresolved_count"])
        self.assertEqual(baseline, spot_opo_allocation_baseline(
            allocation_path, symbol="BTCUSDT", list_client_order_id=self.request["listClientOrderId"],
            expected_quantity=baseline["quantity"],
        ))
        return acknowledgement

    def test_full_residual_stop_execution_requires_trade_and_portfolio_recovery(self):
        self._assert_residual_stop_execution_stays_unresolved(status="FILLED", executed_quantity="0.0399")

    def test_partial_residual_stop_execution_requires_trade_and_portfolio_recovery(self):
        acknowledgement = self._assert_residual_stop_execution_stays_unresolved(
            status="PARTIALLY_FILLED", executed_quantity="0.01",
        )
        self.owner.client = SimpleNamespace(get_order=lambda **_kwargs: acknowledgement)
        result = ledger.reconcile_spot_opo_intent(self.owner, self.request["listClientOrderId"], force=True)
        self.assertFalse(result["reconciled"])
        record = ledger._get_order_intent_record(self.owner, self.request["listClientOrderId"])
        self.assertEqual("0.01", record["residual_stop_executed_qty"])
        self.assertEqual("triggered", record["residual_stop_state"])

    def test_late_residual_query_cannot_overwrite_a_newer_terminal_observation(self):
        allocation_path, baseline = self._recover_partial_strategy_exit()
        _request, acknowledgement = self._begin_and_observe_residual_stop(allocation_path, baseline)

        def raced_getter(**_kwargs):
            ledger._mark_spot_opo_residual_stop_order_observed(
                self.owner, self.request["listClientOrderId"],
                order_response={**acknowledgement, "status": "CANCELED"}, exact_query=True,
            )
            return acknowledgement

        self.owner.client = SimpleNamespace(get_order=raced_getter)
        result = ledger.reconcile_spot_opo_intent(self.owner, self.request["listClientOrderId"], force=True)
        self.assertFalse(result["reconciled"])
        self.assertIn("late result was not applied", result["error"])
        record = ledger._get_order_intent_record(self.owner, self.request["listClientOrderId"])
        self.assertEqual("CANCELED", record["residual_stop_status"])
        self.assertEqual("triggered", record["residual_stop_state"])
        self.assertTrue(ledger._is_unresolved(record))

    def _assert_terminal_residual_stop_cannot_regress(self, status):
        allocation_path, baseline = self._recover_partial_strategy_exit()
        _request, acknowledgement = self._begin_and_observe_residual_stop(allocation_path, baseline)
        terminal = {**acknowledgement, "status": status}
        self.owner.client = SimpleNamespace(get_order=lambda **_kwargs: terminal)
        first = ledger.reconcile_spot_opo_intent(self.owner, self.request["listClientOrderId"], force=True)
        self.assertFalse(first["reconciled"])
        self.owner.client.get_order = lambda **_kwargs: acknowledgement
        stale = ledger.reconcile_spot_opo_intent(self.owner, self.request["listClientOrderId"], force=True)
        self.assertFalse(stale["reconciled"])
        record = ledger._get_order_intent_record(self.owner, self.request["listClientOrderId"])
        self.assertEqual(status, record["residual_stop_status"])
        self.assertEqual("triggered", record["residual_stop_state"])
        self.assertTrue(ledger._is_unresolved(record))

    def test_canceled_empty_residual_stop_cannot_be_reported_active_again(self):
        self._assert_terminal_residual_stop_cannot_regress("CANCELED")

    def test_expired_empty_residual_stop_cannot_be_reported_active_again(self):
        self._assert_terminal_residual_stop_cannot_regress("EXPIRED")

    def test_match_expired_empty_residual_stop_cannot_be_reported_active_again(self):
        self._assert_terminal_residual_stop_cannot_regress("EXPIRED_IN_MATCH")

    def test_triggered_residual_stop_fill_closes_only_the_exact_ledgered_remainder(self):
        allocation_path, baseline = self._recover_partial_strategy_exit()
        request, _acknowledgement = self._begin_and_observe_residual_stop(allocation_path, baseline)
        filled_order = {
            "symbol": "BTCUSDT", "clientOrderId": request["newClientOrderId"], "orderId": 510,
            "orderListId": -1, "side": "SELL", "type": "STOP_LOSS", "status": "FILLED",
            "origQty": baseline["quantity"], "executedQty": baseline["quantity"],
            "stopPrice": "95.00", "cummulativeQuoteQty": "3.7905", "updateTime": 1780000000040,
        }
        ledger._mark_spot_opo_residual_stop_order_observed(
            self.owner,
            self.request["listClientOrderId"],
            order_response=filled_order,
            exact_query=True,
        )
        intent = ledger._get_order_intent_record(self.owner, self.request["listClientOrderId"])
        trades = [{
            "symbol": "BTCUSDT", "id": 911, "orderId": 510, "price": "95",
            "qty": baseline["quantity"], "quoteQty": "3.7905", "commission": "0",
            "commissionAsset": "BTC", "time": 1780000000040, "isBuyer": False,
        }]
        fill = summarize_spot_opo_residual_stop_sell_fill(
            intent, filled_order, trades, base_asset="BTC", quote_asset="USDT",
        )
        self.assertTrue(persist_spot_opo_residual_stop_allocation(allocation_path, fill))
        consumed = Decimal(str(fill["portfolio_qty"]))
        remaining = Decimal(str(baseline["quantity"])) - consumed
        self.assertEqual(Decimal("0"), remaining)
        ledger._mark_spot_opo_residual_stop_reconciled(
            self.owner,
            self.request["listClientOrderId"],
            allocation_path=allocation_path,
            fill_signature=str(fill["signature"]),
            consumed_quantity=consumed,
            remaining_quantity=remaining,
            trade_ids=list(fill["trade_ids"]),
            fill_time_ms=int(fill["fill_time_ms"]),
        )

        restarted_owner = SimpleNamespace(
            _order_audit_log_path=self.owner._order_audit_log_path,
            api_key=self.owner.api_key,
            mode=self.owner.mode,
        )
        restored = ledger._get_order_intent_record(restarted_owner, self.request["listClientOrderId"])
        self.assertEqual("completed", restored["residual_stop_state"])
        self.assertEqual("closed", restored["protection_state"])
        self.assertFalse(ledger._is_unresolved(restored))
        self.assertEqual(0, ledger.get_order_intent_status(restarted_owner)["unresolved_count"])
        saved = json.loads(allocation_path.read_text(encoding="utf-8"))
        row = saved["entry_allocations"]["BTCUSDT:L"][0]
        self.assertEqual("Closed", row["status"])
        self.assertEqual(request["newClientOrderId"], row["spot_sell_recoveries"][-1]["client_order_id"])

    def test_malformed_linked_sell_response_cannot_be_cleared_by_stop_recovery_or_manual_cancel(self):
        self._recover_active_entry()
        self._begin_strategy_exit(self.owner, self.request["listClientOrderId"], "strategy-exit-006")
        malformed = _cancel_replace_response(new_client_order_id="strategy-exit-006")
        malformed["newOrderResponse"]["clientOrderId"] = "crossed-order-id"
        with self.assertRaisesRegex(LiveTradingSafetyError, "exact reconciliation is required"):
            ledger._mark_spot_opo_strategy_exit_response(
                self.owner, self.request["listClientOrderId"], response=malformed,
            )
        with self.assertRaisesRegex(LiveTradingSafetyError, "blocked after a linked SELL attempt"):
            ledger.cancel_spot_opo_intent(self.owner, self.request["listClientOrderId"])

        self._install_observation(
            pending_status="FILLED", pending_executed="0.0999", list_status="ALL_DONE",
        )
        ledger.reconcile_spot_opo_intent(self.owner, self.request["listClientOrderId"])
        record = ledger._get_order_intent_record(self.owner, self.request["listClientOrderId"])
        self.assertEqual("triggered", record["protection_state"])
        self.assertEqual("unknown", record["strategy_exit_state"])
        self.assertTrue(ledger._is_unresolved(record))
        with self.assertRaisesRegex(LiveTradingSafetyError, "triggered stop with durable entry proof"):
            ledger._mark_spot_opo_exit_reconciled(
                self.owner,
                self.request["listClientOrderId"],
                portfolio_signature="d" * 64,
                portfolio_quantity="0.0999",
            )

    def test_cancel_requires_a_recovered_entry_and_confirms_after_exact_child_requery(self):
        self._recover_active_entry()
        cancel_calls = []

        def cancel_order_list(**kwargs):
            cancel_calls.append(kwargs)
            self._install_observation(
                pending_status="CANCELED", pending_executed="0", list_status="ALL_DONE",
            )
            return {"symbol": "BTCUSDT", "listClientOrderId": self.request["listClientOrderId"]}

        self.owner.client.cancel_order_list = cancel_order_list
        result = ledger.cancel_spot_opo_intent(self.owner, self.request["listClientOrderId"])

        self.assertTrue(result["cancel_confirmed"])
        self.assertTrue(result["requires_manual_reconciliation"])
        self.assertEqual([{
            "symbol": "BTCUSDT", "listClientOrderId": self.request["listClientOrderId"],
        }], cancel_calls)
        intent = ledger._get_order_intent_record(self.owner, self.request["listClientOrderId"])
        self.assertEqual("cancelled", intent["protection_state"])
        self.assertEqual("confirmed", intent["cancel_state"])
        self.assertEqual(1, ledger.get_order_intent_status(self.owner)["unresolved_count"])
        self.assertEqual(
            0,
            ledger.get_spot_open_order_reconciliation_status(self.owner, [])[
                "local_open_order_status_conflict_count"
            ],
        )
        self.assertTrue(ledger.cancel_spot_opo_intent(
            self.owner, self.request["listClientOrderId"],
        )["already_cancelled"])
        self.assertEqual(1, len(cancel_calls))

    def test_stop_trigger_during_cancel_is_reported_for_fill_recovery(self):
        self._recover_active_entry()

        def cancel_order_list(**_kwargs):
            self._install_observation(
                pending_status="FILLED", pending_executed="0.0999", list_status="ALL_DONE",
            )
            return {}

        self.owner.client.cancel_order_list = cancel_order_list
        result = ledger.cancel_spot_opo_intent(self.owner, self.request["listClientOrderId"])

        self.assertFalse(result["cancel_confirmed"])
        self.assertTrue(result["requires_stop_fill_recovery"])
        intent = ledger._get_order_intent_record(self.owner, self.request["listClientOrderId"])
        self.assertEqual("triggered", intent["protection_state"])
        self.assertNotEqual("confirmed", intent.get("cancel_state"))
        self.assertEqual(1, ledger.get_order_intent_status(self.owner)["unresolved_count"])

    def test_restart_reconciles_persisted_cancel_before_repeating_the_cancel(self):
        self._recover_active_entry()
        record = ledger._get_order_intent_record(self.owner, self.request["listClientOrderId"])
        ledger._update_order_intent_by_id(
            self.owner,
            self.request["listClientOrderId"],
            state="accepted",
            expected_record=record,
            cancel_state="submitted",
            cancel_submitted_at="2026-09-27T12:00:00+00:00",
        )
        self._install_observation(
            pending_status="CANCELED", pending_executed="0", list_status="ALL_DONE",
        )

        result = ledger.cancel_spot_opo_intent(self.owner, self.request["listClientOrderId"])

        self.assertTrue(result["cancel_confirmed"])
        self.assertTrue(result["already_cancelled"])
        self.assertEqual("confirmed", ledger._get_order_intent_record(
            self.owner, self.request["listClientOrderId"],
        )["cancel_state"])
        self.assertEqual(1, ledger.get_order_intent_status(self.owner)["unresolved_count"])

    def test_ambiguous_cancel_keeps_the_account_blocked_until_retried_or_reconciled(self):
        self._recover_active_entry()
        self.owner.client.cancel_order_list = lambda **_kwargs: (_ for _ in ()).throw(RuntimeError("timeout"))

        result = ledger.cancel_spot_opo_intent(self.owner, self.request["listClientOrderId"])

        self.assertFalse(result["cancel_confirmed"])
        self.assertEqual("active", result["protection_state"])
        self.assertEqual(1, ledger.get_order_intent_status(self.owner)["unresolved_count"])
        intent = ledger._get_order_intent_record(self.owner, self.request["listClientOrderId"])
        self.assertEqual("unknown", intent["cancel_state"])
        self.assertEqual("timeout", intent["last_cancel_error"])

    def test_no_fill_resolution_cannot_be_reconstructed_from_a_tampered_ledger(self):
        self._submit()
        ledger._mark_spot_opo_unknown(self.owner, self.request["listClientOrderId"], error="restart recovery")
        self._install_observation(
            working_status="EXPIRED", working_executed="0", pending_status="PENDING_NEW",
            pending_executed="0", list_status="ALL_DONE",
        )
        ledger.reconcile_spot_opo_intent(self.owner, self.request["listClientOrderId"])
        path = ledger._intent_path(self.owner)
        payload = json.loads(path.read_text(encoding="utf-8"))
        del payload["intents"][self.request["listClientOrderId"]]["working_executed_qty"]
        path.write_text(json.dumps(payload), encoding="utf-8")

        with self.assertRaisesRegex(LiveTradingSafetyError, "missing exact Spot OPO exchange evidence"):
            ledger.get_order_intent_status(self.owner)

    def test_positive_partial_execution_and_wrong_child_identity_stay_blocked(self):
        self._submit()
        ledger._mark_spot_opo_unknown(self.owner, self.request["listClientOrderId"], error="restart recovery")
        self._install_observation(
            working_status="PARTIALLY_FILLED", working_executed="0.0100", pending_status="PENDING_NEW",
        )
        partial_result = ledger.reconcile_spot_opo_intent(self.owner, self.request["listClientOrderId"])
        self.assertFalse(partial_result["reconciled"])
        self.assertEqual("lost", partial_result["protection_state"])
        self.assertEqual(1, ledger.get_order_intent_status(self.owner)["unresolved_count"])

        self._install_observation(wrong_pending_id=True)
        bad_query = ledger.reconcile_spot_opo_intent(self.owner, self.request["listClientOrderId"])
        self.assertFalse(bad_query["reconciled"])
        self.assertEqual("lost", bad_query["protection_state"])
        self.assertEqual(1, ledger.get_order_intent_status(self.owner)["unresolved_count"])


if __name__ == "__main__":
    unittest.main()
