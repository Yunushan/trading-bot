from __future__ import annotations

import hashlib
import hmac
import json
import os
import socket
import tempfile
import unittest
from contextlib import contextmanager, redirect_stdout
from decimal import Decimal
from io import StringIO
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch
from urllib.parse import urlencode, urlparse

from app.integrations.exchanges.binance.orders import order_intent_admin as admin_cli
from app.integrations.exchanges.binance.orders import order_intent_runtime as intents
from app.integrations.exchanges.binance.orders import spot_fill_recovery_runtime as spot_recovery
from app.integrations.exchanges.binance.orders import spot_user_data_admin_runtime as spot_admin_runtime
from app.integrations.exchanges.binance.orders.spot_fill_recovery_runtime import spot_opo_allocation_baseline
from app.integrations.exchanges.binance.orders.spot_opo_runtime import build_spot_opo_request
from app.integrations.exchanges.binance.orders.order_intent_provisioning import (
    PROVISION_ACK,
    provision_order_intent_store,
)
from app.integrations.exchanges.binance.orders.spot_execution_owner import owner_administration_lock, owner_marker_path
from app.integrations.exchanges.binance.orders.spot_inventory_namespace_runtime import (
    namespace_for_current_ledger, namespace_for_owner, publish_owned_spot_fill,
)
from app.integrations.exchanges.binance.orders.order_intent_store import ledger_transactions, write_ledger
from app.integrations.exchanges.binance.orders.spot_inventory_checkpoint_runtime import bootstrap_owned_inventory_checkpoint
from app.integrations.exchanges.binance.orders.spot_allocation_generation_runtime import canonical_spot_buy_metadata
from spot_inventory_checkpoint_fixtures import checkpoint_backend_for_case


UID = 12345678
API_KEY = "offline-reconcile-key"
API_SECRET = "offline-reconcile-secret"
PARAMS = {
    "newClientOrderId": "reconcile-intent-A", "symbol": "BTCUSDT", "side": "BUY",
    "type": "MARKET", "quantity": "0.1",
}


class _SpotRuntime:
    _enforce_spot_execution_owner = True

    def __init__(self, audit_path: Path) -> None:
        self.account_type = "SPOT"
        self.mode = "Live"
        self.api_key = API_KEY
        self.api_secret = "offline-runtime-secret"
        self.client = SimpleNamespace()
        self._order_audit_log_path = audit_path

    def _http_signed_spot(self, path: str):
        if path != "/v3/account":
            raise AssertionError(f"Unexpected owner identity path: {path}")
        return {"uid": UID, "accountType": "SPOT"}


intents.bind_binance_order_intent_runtime(_SpotRuntime)


class SpotReconciliationAdminTests(unittest.TestCase):
    def setUp(self) -> None:
        self.home = Path(self.enterContext(tempfile.TemporaryDirectory())).resolve()
        self.enterContext(patch.object(Path, "home", return_value=self.home))
        self.enterContext(patch.object(socket.socket, "connect", side_effect=AssertionError("No network calls")))
        self.audit_path = self.home / "logs" / "audit.jsonl"
        self.audit_path.parent.mkdir(parents=True)
        self.admin_owner = SimpleNamespace(
            _order_audit_log_path=self.audit_path,
            api_key=API_KEY,
            mode="Live",
            account_type="SPOT",
            _enforce_spot_execution_owner=True,
            _operator_spot_account_uid=UID,
        )
        self.path = intents._intent_path(self.admin_owner)
        provision_order_intent_store(self.admin_owner, acknowledgement=PROVISION_ACK)
        self.allocation_path = self.home / "allocations.json"
        self.enterContext(patch(
            "app.gui.shared.allocation_persistence.get_position_allocations_path", return_value=self.allocation_path,
        ))

    def prebind_inventory(self, wrapper):
        """Bootstrap the actual empty canonical source before financial history."""
        from app.gui.shared import allocation_persistence
        checkpoint_backend_for_case(self)
        app_root = Path(intents.__file__).resolve().parents[4]
        allocation_path = allocation_persistence.get_position_allocations_path(app_root / "gui" / "window_shell.py")
        owner = wrapper._ensure_spot_execution_owner()
        self.addCleanup(owner.close)
        if allocation_path.exists():
            with ledger_transactions(owner.ledger_path, allocation_path):
                allocation_persistence.guard_position_allocation_snapshot(
                    allocation_path, allocation_persistence._read_receipt(allocation_path),
                    expected_namespace=namespace_for_owner(wrapper),
                )
            return
        self.assertTrue(bootstrap_owned_inventory_checkpoint(wrapper, allocation_path=allocation_path))

    def publish_fill(self, wrapper, allocation_path, fill, *, record, operation=spot_recovery.persist_spot_buy_allocation):
        self.assertTrue(publish_owned_spot_fill(wrapper, allocation_path, fill, expected_record=record, operation=operation))

    def canonical_opo_buy(self, record, working, *, trade_id):
        working = {**working, "cummulativeQuoteQty": "10", "updateTime": 1780000000000}
        trades = [{"symbol": "BTCUSDT", "id": trade_id, "orderId": working["orderId"],
                   "price": "100", "qty": "0.1", "quoteQty": "10", "commission": "0.0001",
                   "commissionAsset": "BTC", "time": 1780000000000, "isBuyer": True}]
        return spot_recovery.summarize_spot_opo_buy_fill(record, working, trades, base_asset="BTC", quote_asset="USDT")

    def author_tracked_buy(self, wrapper, allocation_path, fill):
        """Publish an explicit synthetic terminal BUY in the original same ledger."""
        params = {**PARAMS, "newClientOrderId": fill["client_order_id"]}
        record = intents._intent_record(params, market="spot", source="offline-tracked-acquisition-fixture")
        metadata = canonical_spot_buy_metadata(fill)
        record.update(state="accepted", exchange_status="FILLED", exchange_order_id=str(fill["order_id"]),
                      executed_qty=metadata["gross_qty"], portfolio_qty=metadata["net_qty"], portfolio_reconciled=False,
                      primary_fill_receipt=metadata, primary_fill_signature=metadata["signature"], accepted_at=intents._now())
        intents.validate_order_intent_record(fill["client_order_id"], record)
        with ledger_transactions(self.path, allocation_path):
            ledger = intents._read_ledger(self.path, expected_binding=intents._intent_binding(wrapper))
            ledger["intents"][fill["client_order_id"]] = record
            intents.validate_order_intent_ledger(ledger, expected_binding=intents._intent_binding(wrapper))
            write_ledger(self.path, ledger)
        self.publish_fill(wrapper, allocation_path, fill, record=record)
        intents._mark_order_intent_portfolio_reconciled(wrapper, fill["client_order_id"],
            portfolio_signature=fill["signature"], portfolio_quantity=fill["net_qty"])

    @contextmanager
    def verified_admin_scope(self):
        """Use the CLI's actual signed UID and administration exclusion for fixture marks."""
        def signed_account(url, *, params, headers, timeout):
            self.assertEqual("/api/v3/account", urlparse(url).path)
            self.assertEqual({"X-MBX-APIKEY": API_KEY}, headers)
            unsigned = {key: value for key, value in params.items() if key != "signature"}
            expected = hmac.new(API_SECRET.encode(), urlencode(unsigned).encode("ascii"), hashlib.sha256).hexdigest()
            self.assertTrue(hmac.compare_digest(expected, params["signature"]))
            self.assertEqual((3, 8), timeout)
            return SimpleNamespace(status_code=200, json=lambda: {"uid": UID, "accountType": "SPOT"})

        transport = spot_admin_runtime.SpotUserDataTransport(API_KEY, API_SECRET)
        with patch.object(spot_admin_runtime.requests, "get", side_effect=signed_account) as request:
            signed_uid = transport.get_account_uid()
        self.assertEqual(1, request.call_count)
        self.assertEqual(self.admin_owner._operator_spot_account_uid, signed_uid)
        attributes = ("api_secret", "client", "_verified_spot_account_context", "_spot_inventory_administration_path")
        missing = object()
        previous = {name: getattr(self.admin_owner, name, missing) for name in attributes}
        with owner_administration_lock(self.path):
            self.admin_owner.api_secret = API_SECRET
            self.admin_owner.client = transport
            self.admin_owner._verified_spot_account_context = (API_KEY, API_SECRET, "live", transport, signed_uid)
            self.admin_owner._spot_inventory_administration_path = self.path
            try:
                yield namespace_for_current_ledger(self.admin_owner)
            finally:
                for name, value in previous.items():
                    if value is missing:
                        delattr(self.admin_owner, name)
                    else:
                        setattr(self.admin_owner, name, value)

    def args(self) -> list[str]:
        return [
            "reconcile-spot", "--account-type", "Spot", "--mode", "Live",
            "--api-key-env", "SPOT_RECONCILE_TEST_KEY",
            "--api-secret-env", "SPOT_RECONCILE_TEST_SECRET",
        ]

    def set_up_pending_after_owner_loss(
        self, *, order_type: str = "MARKET", side: str = "BUY", quantity: str = "0.1", wrapper=None,
    ) -> Path:
        wrapper = wrapper if wrapper is not None else _SpotRuntime(self.audit_path)
        wrapper._ensure_spot_execution_owner()
        self.prebind_inventory(wrapper)
        params = {**PARAMS, "type": order_type, "side": side, "quantity": quantity}
        intents._begin_order_intent(
            wrapper, params, market="spot", source="offline-reconciliation-test",
        )
        owner = wrapper._spot_execution_owner
        owner.close()
        path = owner_marker_path(self.path)
        self.assertEqual("recovery_required", json.loads(path.read_text(encoding="utf-8"))["state"])
        return path

    def set_up_pending_opo_after_owner_loss(self) -> tuple[Path, dict[str, str]]:
        wrapper = _SpotRuntime(self.audit_path)
        self.prebind_inventory(wrapper)
        request = build_spot_opo_request(
            symbol="BTCUSDT",
            symbol_info={
                "symbol": "BTCUSDT", "status": "TRADING", "quoteAsset": "USDT",
                "isSpotTradingAllowed": True, "otoAllowed": True, "opoAllowed": True,
                "filters": [
                    {"filterType": "PRICE_FILTER", "minPrice": "0.01", "maxPrice": "1000000", "tickSize": "0.01"},
                    {"filterType": "LOT_SIZE", "minQty": "0.0001", "maxQty": "9000", "stepSize": "0.0001"},
                    {"filterType": "MIN_NOTIONAL", "minNotional": "5"},
                ],
            },
            working_price="100", working_quantity="0.1", pending_stop_price="95",
            list_client_order_id="recover-op-list", working_client_order_id="recover-op-buy",
            pending_client_order_id="recover-op-stop",
        )
        intents._begin_spot_opo_intent(wrapper, request, source="offline-reconciliation-test")
        intents._mark_spot_opo_submitted(wrapper, request["listClientOrderId"], via="offline-test")
        intents._mark_spot_opo_unknown(wrapper, request["listClientOrderId"], error="lost response")
        owner = wrapper._spot_execution_owner
        owner.close()
        path = owner_marker_path(self.path)
        self.assertEqual("recovery_required", json.loads(path.read_text(encoding="utf-8"))["state"])
        return path, request

    def set_up_active_recovered_opo(self, allocation_path: Path) -> tuple[Path, dict[str, str]]:
        with patch("app.gui.shared.allocation_persistence.get_position_allocations_path", return_value=allocation_path):
            marker_path, request = self.set_up_pending_opo_after_owner_loss()
        record = intents._get_order_intent_record(self.admin_owner, request["listClientOrderId"])
        self.assertIsInstance(record, dict)
        updated = intents._update_order_intent_by_id(
            self.admin_owner,
            request["listClientOrderId"],
            state="accepted",
            expected_record=record,
            protection_state="active",
            exchange_order_list_id=500,
            list_status="EXEC_STARTED",
            working_order_id=501,
            working_status="FILLED",
            working_executed_qty="0.1",
            pending_order_id=502,
            pending_status="NEW",
            pending_executed_qty="0",
            pending_original_qty="0.0999",
        )
        self.assertIsNotNone(updated)
        working = self.opo_list_observation(request, pending_status="NEW", list_status="EXEC_STARTED")[1]
        fill = self.canonical_opo_buy(updated, working, trade_id=601)
        with self.verified_admin_scope(), patch(
            "app.gui.shared.allocation_persistence.get_position_allocations_path",
            return_value=allocation_path,
        ):
            self.publish_fill(self.admin_owner, allocation_path, fill, record=updated)
            intents._mark_spot_opo_entry_reconciled(
                self.admin_owner, request["listClientOrderId"],
                portfolio_signature=fill["signature"], portfolio_quantity="0.0999",
            )
        return marker_path, request

    def set_up_active_opo_with_linked_exit(
        self, allocation_path: Path, *, exit_client_id: str, retry_attempt: bool = False,
    ) -> tuple[Path, dict[str, str]]:
        wrapper = _SpotRuntime(self.audit_path)
        with patch("app.gui.shared.allocation_persistence.get_position_allocations_path", return_value=allocation_path):
            wrapper._ensure_spot_execution_owner()
            self.prebind_inventory(wrapper)
            self.addCleanup(wrapper._spot_execution_owner.close)
            request = build_spot_opo_request(
                symbol="BTCUSDT",
                symbol_info={
                    "symbol": "BTCUSDT", "status": "TRADING", "quoteAsset": "USDT",
                    "isSpotTradingAllowed": True, "otoAllowed": True, "opoAllowed": True,
                    "filters": [
                        {"filterType": "PRICE_FILTER", "minPrice": "0.01", "maxPrice": "1000000", "tickSize": "0.01"},
                        {"filterType": "LOT_SIZE", "minQty": "0.0001", "maxQty": "9000", "stepSize": "0.0001"},
                        {"filterType": "MIN_NOTIONAL", "minNotional": "5"},
                    ],
                },
                working_price="100", working_quantity="0.1", pending_stop_price="95",
                list_client_order_id="recovery-exit-list", working_client_order_id="recovery-exit-buy",
                pending_client_order_id="recovery-exit-stop",
            )
            intents._begin_spot_opo_intent(wrapper, request, source="offline-recovery-test")
            intents._mark_spot_opo_submitted(wrapper, request["listClientOrderId"], via="offline-test")
            current = intents._get_order_intent_record(wrapper, request["listClientOrderId"])
            intents._update_order_intent_by_id(
                wrapper,
                request["listClientOrderId"],
                state="accepted",
                expected_record=current,
                protection_state="active",
                exchange_order_list_id=700,
                list_status="EXEC_STARTED",
                working_order_id=701,
                working_status="FILLED",
                working_executed_qty="0.1",
                pending_order_id=702,
                pending_status="NEW",
                pending_executed_qty="0",
                pending_original_qty="0.0999",
            )
            list_response, working, pending = self.opo_list_observation(
                request, pending_status="NEW", list_status="EXEC_STARTED",
            )
            list_response["orderListId"] = 700
            for child in list_response["orders"]:
                child["orderId"] += 200
            for child in (working, pending):
                child["orderId"] += 200
                child["orderListId"] = 700
            children = {child["clientOrderId"]: child for child in (working, pending)}

            def get_order_list(**kwargs):
                self.assertEqual({"origClientOrderId": request["listClientOrderId"]}, kwargs)
                return list_response

            def get_order(**kwargs):
                self.assertEqual("BTCUSDT", kwargs["symbol"])
                return children[kwargs["origClientOrderId"]]

            wrapper.client.get_order_list = get_order_list
            wrapper.client.get_order = get_order
            current = intents._get_order_intent_record(wrapper, request["listClientOrderId"])
            buy_fill = self.canonical_opo_buy(current, working, trade_id=801)
            with patch(
                "app.gui.shared.allocation_persistence.get_position_allocations_path",
                return_value=allocation_path,
            ):
                self.publish_fill(wrapper, allocation_path, buy_fill, record=current)
                intents._mark_spot_opo_entry_reconciled(
                    wrapper, request["listClientOrderId"],
                    portfolio_signature=buy_fill["signature"], portfolio_quantity="0.0999",
                )
                baseline = spot_opo_allocation_baseline(
                    allocation_path,
                    symbol="BTCUSDT",
                    list_client_order_id=request["listClientOrderId"],
                    expected_quantity="0.0999", namespace=namespace_for_owner(wrapper),
                )
                if retry_attempt:
                    first = intents._begin_spot_opo_strategy_exit(
                        wrapper, request["listClientOrderId"], new_order_client_id="first-no-effect-exit",
                        pre_order_portfolio_signature=baseline["signature"],
                        pre_order_portfolio_quantity=baseline["quantity"], allocation_path=allocation_path,
                    )
                    intents._mark_spot_opo_strategy_exit_response(
                        wrapper, request["listClientOrderId"], expected_record=first,
                        response={
                            "cancelResult": "FAILURE", "newOrderResult": "NOT_ATTEMPTED",
                            "cancelResponse": {"code": -2011, "msg": "Unknown order sent."},
                            "newOrderResponse": None,
                        },
                    )
                    intents.reconcile_spot_opo_intent(wrapper, request["listClientOrderId"], force=True)
                intents._begin_spot_opo_strategy_exit(
                    wrapper,
                    request["listClientOrderId"],
                    new_order_client_id=exit_client_id,
                    pre_order_portfolio_signature=baseline["signature"],
                    pre_order_portfolio_quantity=baseline["quantity"],
                    allocation_path=allocation_path,
                )
            marker_path = owner_marker_path(self.path)
            wrapper._spot_execution_owner.close()
            self.assertEqual("recovery_required", json.loads(marker_path.read_text(encoding="utf-8"))["state"])
            return marker_path, request

    def set_up_rearm_required_opo(self, allocation_path: Path) -> tuple[Path, dict[str, str], dict[str, str]]:
        exit_client_id = "recovery-exit-partial"
        marker_path, request = self.set_up_active_opo_with_linked_exit(
            allocation_path, exit_client_id=exit_client_id,
        )
        with self.verified_admin_scope() as namespace, patch(
            "app.gui.shared.allocation_persistence.get_position_allocations_path", return_value=allocation_path,
        ):
            response = {
                "cancelResult": "SUCCESS", "newOrderResult": "SUCCESS",
                "cancelResponse": {
                    "symbol": "BTCUSDT", "orderId": 702, "origClientOrderId": request["pendingClientOrderId"],
                    "side": "SELL", "status": "CANCELED", "executedQty": "0",
                },
                "newOrderResponse": {
                    "symbol": "BTCUSDT", "clientOrderId": exit_client_id, "orderId": 703,
                    "side": "SELL", "type": "MARKET", "status": "PARTIALLY_FILLED",
                    "origQty": "0.0999", "executedQty": "0.0600",
                },
            }
            intents._mark_spot_opo_strategy_exit_response(
                self.admin_owner, request["listClientOrderId"], response=response,
            )
            current = intents._get_order_intent_record(self.admin_owner, request["listClientOrderId"])
            updated = intents._update_order_intent_by_id(
                self.admin_owner,
                request["listClientOrderId"],
                state="accepted",
                expected_record=current,
                protection_state="cancelled",
                cancel_state="confirmed",
                cancel_confirmed_at="2026-09-27T12:00:00+00:00",
                list_status="ALL_DONE",
                pending_status="CANCELED",
                pending_executed_qty="0",
            )
            self.assertIsNotNone(updated)
            exit_order = {
                "symbol": "BTCUSDT", "clientOrderId": exit_client_id, "orderId": 703,
                "orderListId": -1, "side": "SELL", "type": "MARKET", "status": "CANCELED",
                "origQty": "0.0999", "executedQty": "0.0600", "cummulativeQuoteQty": "5.7",
                "updateTime": 1780000000020,
            }
            intents._mark_spot_opo_strategy_exit_order_observed(
                self.admin_owner, request["listClientOrderId"], order_response=exit_order,
            )
            intent = intents._get_order_intent_record(self.admin_owner, request["listClientOrderId"])
            trades = [{
                "symbol": "BTCUSDT", "id": 704, "orderId": 703, "price": "95",
                "qty": "0.0600", "quoteQty": "5.7", "commission": "0", "commissionAsset": "BTC",
                "time": 1780000000020, "isBuyer": False,
            }]
            fill = spot_recovery.summarize_spot_opo_strategy_sell_fill(
                intent, exit_order, trades, base_asset="BTC", quote_asset="USDT",
            )
            self.publish_fill(self.admin_owner, allocation_path, fill, record=intent,
                              operation=spot_recovery.persist_spot_opo_strategy_sell_allocation)
            remaining = Decimal(str(intent["entry_portfolio_quantity"])) - Decimal(str(fill["portfolio_qty"]))
            baseline = spot_opo_allocation_baseline(
                allocation_path,
                symbol="BTCUSDT",
                list_client_order_id=request["listClientOrderId"],
                expected_quantity=remaining, namespace=namespace,
            )
            intents._mark_spot_opo_strategy_exit_residual_required(
                self.admin_owner,
                request["listClientOrderId"],
                allocation_path=allocation_path,
                portfolio_signature=baseline["signature"],
                portfolio_quantity=baseline["quantity"],
                fill_signature=str(fill["signature"]),
                consumed_quantity=fill["portfolio_qty"],
                trade_ids=list(fill["trade_ids"]),
                fill_time_ms=int(fill["fill_time_ms"]),
            )
            return marker_path, request, baseline

    def run_cli_with_responses(self, responses: list[object]) -> tuple[int, dict[str, object], object]:
        with patch.dict(os.environ, {
            "SPOT_RECONCILE_TEST_KEY": API_KEY,
            "SPOT_RECONCILE_TEST_SECRET": API_SECRET,
        }):
            with patch.object(spot_admin_runtime.requests, "get", side_effect=responses) as request:
                with redirect_stdout(StringIO()) as output:
                    code = admin_cli.main(self.args())
        return code, json.loads(output.getvalue()), request

    def test_exact_filled_order_stays_blocked_pending_portfolio_recovery(self):
        marker_path = self.set_up_pending_after_owner_loss()
        responses = [
            SimpleNamespace(status_code=200, json=lambda: {"uid": UID, "accountType": "SPOT"}),
            SimpleNamespace(status_code=200, json=lambda: {
                "clientOrderId": PARAMS["newClientOrderId"], "symbol": "BTCUSDT", "side": "BUY",
                "orderId": 55, "status": "FILLED", "type": "MARKET", "price": "0",
                "origQty": "0.1", "executedQty": "0.1", "cummulativeQuoteQty": "2000",
            }),
        ]
        code, result, request = self.run_cli_with_responses(responses)
        self.assertEqual(1, code)
        self.assertFalse(result["ok"])
        self.assertEqual(1, result["unresolved_before"])
        self.assertEqual(1, result["result_count"])
        self.assertEqual(1, result["unresolved_after"])
        self.assertEqual("unknown", result["results"][0]["state"])
        self.assertTrue(result["results"][0]["portfolio_reconciliation_required"])
        self.assertEqual("20000", result["results"][0]["order_response"]["gross_average_price"])
        self.assertEqual("2000", result["results"][0]["order_response"]["cummulativeQuoteQty"])
        self.assertEqual(2, request.call_count)
        self.assertTrue(all(
            call.args[0].startswith("https://api.binance.com/api/v3/")
            for call in request.call_args_list
        ))
        order_params = request.call_args_list[1].kwargs["params"]
        self.assertEqual("BTCUSDT", order_params["symbol"])
        self.assertEqual(PARAMS["newClientOrderId"], order_params["origClientOrderId"])
        self.assertEqual("recovery_required", json.loads(marker_path.read_text(encoding="utf-8"))["state"])
        self.assertEqual(1, intents.get_order_intent_status(self.admin_owner)["unresolved_count"])

    def test_terminal_partial_fill_is_visible_but_stays_blocked_for_portfolio_recovery(self):
        marker_path = self.set_up_pending_after_owner_loss()
        responses = [
            SimpleNamespace(status_code=200, json=lambda: {"uid": UID, "accountType": "SPOT"}),
            SimpleNamespace(status_code=200, json=lambda: {
                "clientOrderId": PARAMS["newClientOrderId"], "symbol": "BTCUSDT", "side": "BUY",
                "orderId": 56, "status": "CANCELED", "type": "MARKET", "price": "0",
                "origQty": "0.1", "executedQty": "0.04", "cummulativeQuoteQty": "800",
                "updateTime": 1780000000000,
            }),
        ]

        code, result, _request = self.run_cli_with_responses(responses)

        self.assertEqual(1, code)
        self.assertFalse(result["ok"])
        self.assertEqual(1, result["unresolved_after"])
        observation = result["results"][0]
        self.assertTrue(observation["reconciled"])
        self.assertEqual("unknown", observation["state"])
        self.assertTrue(observation["portfolio_reconciliation_required"])
        self.assertEqual("0.04", observation["order_response"]["executedQty"])
        self.assertEqual("800", observation["order_response"]["cummulativeQuoteQty"])
        self.assertEqual("20000", observation["order_response"]["gross_average_price"])
        self.assertEqual(1, intents.get_order_intent_status(self.admin_owner)["unresolved_count"])
        self.assertEqual("recovery_required", json.loads(marker_path.read_text(encoding="utf-8"))["state"])

    def test_not_found_order_keeps_intent_unresolved_and_returns_failure(self):
        marker_path = self.set_up_pending_after_owner_loss()
        responses = [
            SimpleNamespace(status_code=200, json=lambda: {"uid": UID, "accountType": "SPOT"}),
            SimpleNamespace(status_code=400, json=lambda: {"code": -2013, "msg": "Order does not exist."}),
        ]
        code, result, _request = self.run_cli_with_responses(responses)
        self.assertEqual(1, code)
        self.assertFalse(result["ok"])
        self.assertFalse(result["results"][0]["reconciled"])
        self.assertEqual("pending", result["results"][0]["state"])
        self.assertEqual(1, intents.get_order_intent_status(self.admin_owner)["unresolved_count"])
        self.assertEqual("recovery_required", json.loads(marker_path.read_text(encoding="utf-8"))["state"])

    def test_refuses_order_queries_while_execution_owner_is_active(self):
        wrapper = _SpotRuntime(self.audit_path)
        wrapper._ensure_spot_execution_owner()
        self.addCleanup(wrapper._spot_execution_owner.close)
        responses = [
            SimpleNamespace(status_code=200, json=lambda: {"uid": UID, "accountType": "SPOT"}),
        ]
        code, result, request = self.run_cli_with_responses(responses)
        self.assertEqual(1, code)
        self.assertFalse(result["ok"])
        self.assertIn("owner is active", result["error"])
        self.assertEqual(1, request.call_count)
        self.assertEqual("active", json.loads(owner_marker_path(self.path).read_text(encoding="utf-8"))["state"])

    def account_reconcile_args(self) -> list[str]:
        args = self.args()
        args[0] = "reconcile-spot-account"
        return args

    def run_account_cli_with_responses(self, responses: list[object]) -> tuple[int, dict[str, object], object]:
        with patch.dict(os.environ, {
            "SPOT_RECONCILE_TEST_KEY": API_KEY,
            "SPOT_RECONCILE_TEST_SECRET": API_SECRET,
        }):
            with patch.object(spot_admin_runtime.requests, "get", side_effect=responses) as request:
                with redirect_stdout(StringIO()) as output:
                    code = admin_cli.main(self.account_reconcile_args())
        return code, json.loads(output.getvalue()), request

    @staticmethod
    def account_overview_response() -> object:
        return SimpleNamespace(status_code=200, json=lambda: {
            "uid": UID,
            "accountType": "SPOT",
            "balances": [
                {"asset": "BTC", "free": "0.1", "locked": "0"},
                {"asset": "USDT", "free": "0", "locked": "2"},
            ],
        })

    def test_account_reconciliation_matches_all_open_orders_and_redacts_balances(self):
        self.set_up_pending_after_owner_loss(order_type="LIMIT")
        responses = [
            SimpleNamespace(status_code=200, json=lambda: {"uid": UID, "accountType": "SPOT"}),
            SimpleNamespace(status_code=200, json=lambda: {
                "clientOrderId": PARAMS["newClientOrderId"], "symbol": "BTCUSDT",
                "orderId": 55, "status": "NEW",
            }),
            self.account_overview_response(),
            SimpleNamespace(status_code=200, json=lambda: [{
                "clientOrderId": PARAMS["newClientOrderId"], "symbol": "BTCUSDT",
                "orderId": 55, "status": "NEW",
            }]),
        ]
        code, result, request = self.run_account_cli_with_responses(responses)
        self.assertEqual(0, code)
        self.assertTrue(result["ok"])
        self.assertEqual(2, result["balance_asset_count"])
        self.assertEqual(2, result["nonzero_balance_asset_count"])
        self.assertEqual(1, result["locked_balance_asset_count"])
        self.assertEqual(1, result["matched_open_order_count"])
        self.assertEqual(0, result["unmatched_exchange_open_order_count"])
        self.assertEqual(0, result["unresolved_after"])
        self.assertFalse(result["balances_reconciled_to_strategy_state"])
        self.assertFalse(result["automatic_rearm"])
        rendered = json.dumps(result)
        for secret_or_balance in (
            "offline-reconcile-secret", "0.1", "BTC", PARAMS["newClientOrderId"],
        ):
            self.assertNotIn(secret_or_balance, rendered)
        self.assertEqual(4, request.call_count)
        self.assertEqual("https://api.binance.com/api/v3/openOrders", request.call_args_list[-1].args[0])
        self.assertEqual("recovery_required", json.loads(owner_marker_path(self.path).read_text(encoding="utf-8"))["state"])

    def test_account_reconciliation_fails_on_untracked_exchange_order_without_echoing_id(self):
        external_client_order_id = "operator-or-other-key-order"
        responses = [
            SimpleNamespace(status_code=200, json=lambda: {"uid": UID, "accountType": "SPOT"}),
            self.account_overview_response(),
            SimpleNamespace(status_code=200, json=lambda: [{
                "clientOrderId": external_client_order_id, "symbol": "ETHUSDT",
                "orderId": 77, "status": "PARTIALLY_FILLED",
            }]),
        ]
        code, result, _request = self.run_account_cli_with_responses(responses)
        self.assertEqual(1, code)
        self.assertFalse(result["ok"])
        self.assertEqual(1, result["unmatched_exchange_open_order_count"])
        self.assertNotIn(external_client_order_id, json.dumps(result))
        self.assertEqual(0, intents.get_order_intent_status(self.admin_owner)["unresolved_count"])

    def test_account_audit_reports_full_market_fill_recovery_without_exposing_order_details(self):
        self.set_up_pending_after_owner_loss()
        responses = [
            SimpleNamespace(status_code=200, json=lambda: {"uid": UID, "accountType": "SPOT"}),
            SimpleNamespace(status_code=200, json=lambda: {
                "clientOrderId": PARAMS["newClientOrderId"], "symbol": "BTCUSDT", "side": "BUY",
                "orderId": 55, "status": "FILLED", "type": "MARKET", "price": "0",
                "origQty": "0.1", "executedQty": "0.1", "cummulativeQuoteQty": "2000",
            }),
            self.account_overview_response(),
            SimpleNamespace(status_code=200, json=lambda: []),
        ]

        code, result, _request = self.run_account_cli_with_responses(responses)

        self.assertEqual(1, code)
        self.assertFalse(result["ok"])
        self.assertEqual(1, result["unresolved_after"])
        self.assertEqual(1, result["positive_market_fill_needs_portfolio_reconciliation_count"])
        self.assertFalse(result["automatic_rearm"])
        rendered = json.dumps(result)
        for private_order_detail in (PARAMS["newClientOrderId"], "BTCUSDT", "0.1", "2000"):
            self.assertNotIn(private_order_detail, rendered)

    def test_recover_command_imports_exact_commission_aware_buy_fill_before_resolving_intent(self):
        self.set_up_pending_after_owner_loss()
        args = self.args()
        args[0] = "recover-spot-market-fills"
        responses = [
            SimpleNamespace(status_code=200, json=lambda: {"uid": UID, "accountType": "SPOT"}),
            SimpleNamespace(status_code=200, json=lambda: {
                "clientOrderId": PARAMS["newClientOrderId"], "symbol": "BTCUSDT", "side": "BUY",
                "orderId": 55, "status": "FILLED", "type": "MARKET", "price": "0",
                "origQty": "0.1", "executedQty": "0.1", "cummulativeQuoteQty": "2000",
                "updateTime": 1780000000000,
            }),
            SimpleNamespace(status_code=200, json=lambda: {"symbols": [{
                "symbol": "BTCUSDT", "baseAsset": "BTC", "quoteAsset": "USDT",
            }]}),
            SimpleNamespace(status_code=200, json=lambda: [{
                "symbol": "BTCUSDT", "id": 77, "orderId": 55,
                "price": "20000", "qty": "0.1", "quoteQty": "2000",
                "commission": "0.0001", "commissionAsset": "BTC",
                "time": 1780000000000, "isBuyer": True,
            }]),
            SimpleNamespace(status_code=200, json=lambda: {"uid": UID, "accountType": "SPOT"}),
        ]
        # Use the protected source prepared before this pending financial intent.
        allocation_path = self.allocation_path
        with patch.dict(os.environ, {
            "SPOT_RECONCILE_TEST_KEY": API_KEY,
            "SPOT_RECONCILE_TEST_SECRET": API_SECRET,
        }), patch.object(
            spot_admin_runtime.requests, "get", side_effect=responses,
        ) as request, patch(
            "app.gui.shared.allocation_persistence.get_position_allocations_path",
            return_value=allocation_path,
        ), redirect_stdout(StringIO()) as output:
            code = admin_cli.main(args)
        saved = json.loads(allocation_path.read_text(encoding="utf-8"))
        recovered = saved["entry_allocations"]["BTCUSDT:L"][0]

        result = json.loads(output.getvalue())
        self.assertEqual(0, code)
        self.assertTrue(result["ok"])
        self.assertEqual(1, result["recovered_buy_fill_count"])
        self.assertEqual(1, result["recovered_trade_count"])
        self.assertEqual(0, result["unresolved_after"])
        self.assertFalse(result["automatic_rearm"])
        self.assertFalse(result["exchange_orders_placed"])
        self.assertEqual(5, request.call_count)
        self.assertEqual("recovery_required", json.loads(owner_marker_path(self.path).read_text(encoding="utf-8"))["state"])
        self.assertEqual(0, intents.get_order_intent_status(self.admin_owner)["unresolved_count"])
        self.assertAlmostEqual(0.0999, recovered["qty"])
        self.assertAlmostEqual(20020.02002002, recovered["entry_price"])
        self.assertEqual("0.0001", recovered["spot_fill_recovery"]["commissions"][0]["amount"])

    def test_recover_opo_command_imports_only_exact_filled_entry_with_matching_active_stop(self):
        marker_path, request = self.set_up_pending_opo_after_owner_loss()
        args = self.args()
        args[0] = "recover-spot-opos"
        list_response = {
            "symbol": "BTCUSDT", "orderListId": 500, "contingencyType": "OTO",
            "listStatusType": "EXEC_STARTED", "listOrderStatus": "EXECUTING",
            "listClientOrderId": request["listClientOrderId"],
            "orders": [
                {"symbol": "BTCUSDT", "orderId": 501, "clientOrderId": request["workingClientOrderId"]},
                {"symbol": "BTCUSDT", "orderId": 502, "clientOrderId": request["pendingClientOrderId"]},
            ],
        }
        working_order = {
            "symbol": "BTCUSDT", "orderId": 501, "orderListId": 500,
            "clientOrderId": request["workingClientOrderId"], "side": "BUY", "type": "LIMIT",
            "status": "FILLED", "origQty": "0.1", "executedQty": "0.1", "timeInForce": "FOK",
            "cummulativeQuoteQty": "10", "updateTime": 1780000000000,
        }
        pending_order = {
            "symbol": "BTCUSDT", "orderId": 502, "orderListId": 500,
            "clientOrderId": request["pendingClientOrderId"], "side": "SELL", "type": "STOP_LOSS",
            "status": "NEW", "origQty": "0.0999", "executedQty": "0", "stopPrice": "95",
        }
        responses = [
            SimpleNamespace(status_code=200, json=lambda: {"uid": UID, "accountType": "SPOT"}),
            SimpleNamespace(status_code=200, json=lambda: list_response),
            SimpleNamespace(status_code=200, json=lambda: working_order),
            SimpleNamespace(status_code=200, json=lambda: pending_order),
            SimpleNamespace(status_code=200, json=lambda: working_order),
            SimpleNamespace(status_code=200, json=lambda: {"symbols": [{
                "symbol": "BTCUSDT", "baseAsset": "BTC", "quoteAsset": "USDT",
            }]}),
            SimpleNamespace(status_code=200, json=lambda: [{
                "symbol": "BTCUSDT", "id": 601, "orderId": 501,
                "price": "100", "qty": "0.1", "quoteQty": "10",
                "commission": "0.0001", "commissionAsset": "BTC",
                "time": 1780000000000, "isBuyer": True,
            }]),
            SimpleNamespace(status_code=200, json=lambda: list_response),
            SimpleNamespace(status_code=200, json=lambda: working_order),
            SimpleNamespace(status_code=200, json=lambda: pending_order),
            SimpleNamespace(status_code=200, json=lambda: {"uid": UID, "accountType": "SPOT"}),
        ]
        # Use the protected source prepared before this pending financial intent.
        allocation_path = self.allocation_path
        with patch.dict(os.environ, {
            "SPOT_RECONCILE_TEST_KEY": API_KEY,
            "SPOT_RECONCILE_TEST_SECRET": API_SECRET,
        }), patch.object(
            spot_admin_runtime.requests, "get", side_effect=responses,
        ) as request_calls, patch(
            "app.gui.shared.allocation_persistence.get_position_allocations_path",
            return_value=allocation_path,
        ), redirect_stdout(StringIO()) as output:
            code = admin_cli.main(args)
        saved = json.loads(allocation_path.read_text(encoding="utf-8"))
        recovered = saved["entry_allocations"]["BTCUSDT:L"][0]

        result = json.loads(output.getvalue())
        self.assertEqual(0, code)
        self.assertTrue(result["ok"])
        self.assertEqual(1, result["recovered_entry_count"])
        self.assertEqual(1, result["recovered_trade_count"])
        self.assertEqual(0, result["unresolved_after"])
        self.assertFalse(result["automatic_rearm"])
        self.assertFalse(result["exchange_orders_placed"])
        self.assertEqual(11, request_calls.call_count)
        self.assertEqual(request["listClientOrderId"], recovered["client_order_id"])
        self.assertEqual(request["workingClientOrderId"], recovered["spot_fill_recovery"]["exchange_client_order_id"])
        self.assertEqual("0.0999", recovered["spot_fill_recovery"]["pending_order_qty"])
        recovered_status = intents.get_order_intent_status(self.admin_owner)
        self.assertEqual(0, recovered_status["unresolved_count"])
        self.assertEqual([request["listClientOrderId"]], recovered_status["spot_opo_client_order_ids"])
        self.assertEqual("recovery_required", json.loads(marker_path.read_text(encoding="utf-8"))["state"])

    def test_cancel_opo_command_cancels_one_exact_list_and_leaves_owner_blocked(self):
        with tempfile.TemporaryDirectory() as tmp:
            allocation_path = Path(tmp) / "allocations.json"
            marker_path, request = self.set_up_active_recovered_opo(allocation_path)
            args = self.args()
            args[0] = "cancel-spot-opos"
            args.extend(["--order-list-client-id", request["listClientOrderId"]])
            before_cancel = self.opo_list_observation(request, pending_status="NEW", list_status="EXEC_STARTED")
            after_cancel = self.opo_list_observation(request, pending_status="CANCELED", list_status="ALL_DONE")
            responses = [
                SimpleNamespace(status_code=200, json=lambda: {"uid": UID, "accountType": "SPOT"}),
                *[
                    SimpleNamespace(status_code=200, json=lambda body=body: body)
                    for body in before_cancel
                ],
                *[
                    SimpleNamespace(status_code=200, json=lambda body=body: body)
                    for body in after_cancel
                ],
                SimpleNamespace(status_code=200, json=lambda: {"uid": UID, "accountType": "SPOT"}),
            ]
            cancel_ack = {
                "symbol": "BTCUSDT", "listClientOrderId": request["listClientOrderId"],
                "orderListId": 500, "listStatusType": "ALL_DONE",
            }
            with patch.dict(os.environ, {
                "SPOT_RECONCILE_TEST_KEY": API_KEY,
                "SPOT_RECONCILE_TEST_SECRET": API_SECRET,
            }), patch.object(
                spot_admin_runtime.requests, "get", side_effect=responses,
            ) as get, patch.object(
                spot_admin_runtime.requests, "delete",
                return_value=SimpleNamespace(status_code=200, json=lambda: cancel_ack),
            ) as delete, redirect_stdout(StringIO()) as output:
                code = admin_cli.main(args)

        result = json.loads(output.getvalue())
        self.assertEqual(0, code, output.getvalue())
        self.assertTrue(result["ok"])
        self.assertTrue(result["cancel_confirmed"])
        self.assertEqual("cancelled", result["protection_state"])
        self.assertEqual(1, result["unresolved_after"])
        self.assertFalse(result["strategy_sell_submitted"])
        self.assertFalse(result["automatic_rearm"])
        self.assertEqual(8, get.call_count)
        delete.assert_called_once()
        delete_params = delete.call_args.kwargs["params"]
        self.assertEqual("BTCUSDT", delete_params["symbol"])
        self.assertEqual(request["listClientOrderId"], delete_params["listClientOrderId"])
        self.assertEqual(1, intents.get_order_intent_status(self.admin_owner)["unresolved_count"])
        self.assertEqual("recovery_required", json.loads(marker_path.read_text(encoding="utf-8"))["state"])

    def test_rearm_opo_command_posts_one_exact_residual_stop_and_requires_exact_query(self):
        with tempfile.TemporaryDirectory() as tmp:
            allocation_path = Path(tmp) / "allocations.json"
            marker_path, request, baseline = self.set_up_rearm_required_opo(allocation_path)
            args = self.args()
            args[0] = "rearm-spot-opos"
            args.extend(["--order-list-client-id", request["listClientOrderId"]])
            list_response = {
                "symbol": "BTCUSDT", "orderListId": 700, "contingencyType": "OTO",
                "listStatusType": "ALL_DONE", "listOrderStatus": "ALL_DONE",
                "listClientOrderId": request["listClientOrderId"],
                "orders": [
                    {"symbol": "BTCUSDT", "orderId": 701, "clientOrderId": request["workingClientOrderId"]},
                    {"symbol": "BTCUSDT", "orderId": 702, "clientOrderId": request["pendingClientOrderId"]},
                ],
            }
            working_order = {
                "symbol": "BTCUSDT", "orderId": 701, "orderListId": 700,
                "clientOrderId": request["workingClientOrderId"], "side": "BUY", "type": "LIMIT",
                "status": "FILLED", "origQty": "0.1", "executedQty": "0.1", "timeInForce": "FOK",
            }
            pending_order = {
                "symbol": "BTCUSDT", "orderId": 702, "orderListId": 700,
                "clientOrderId": request["pendingClientOrderId"], "side": "SELL", "type": "STOP_LOSS",
                "status": "CANCELED", "origQty": "0.0999", "executedQty": "0", "stopPrice": "95",
            }
            symbol_info = {"symbols": [{
                "symbol": "BTCUSDT", "status": "TRADING", "isSpotTradingAllowed": True,
                "filters": [
                    {"filterType": "PRICE_FILTER", "minPrice": "0.01", "maxPrice": "1000000", "tickSize": "0.01"},
                    {"filterType": "LOT_SIZE", "minQty": "0.0001", "maxQty": "9000", "stepSize": "0.0001"},
                    {"filterType": "MARKET_LOT_SIZE", "minQty": "0.0001", "maxQty": "9000", "stepSize": "0.0001"},
                    {"filterType": "MIN_NOTIONAL", "minNotional": "5", "applyToMarket": False, "avgPriceMins": 0},
                ],
            }]}
            current = intents._get_order_intent_record(self.admin_owner, request["listClientOrderId"])
            pending_order["clientOrderId"] = current["strategy_exit_request"]["cancelNewClientOrderId"]
            get_responses: list[tuple[str, object]] = [
                ("/account", {"uid": UID, "accountType": "SPOT"}),
                ("/orderList", list_response),
                ("/order", working_order),
                ("/order", pending_order),
                ("/exchangeInfo", symbol_info),
                ("/ticker/price", {"symbol": "BTCUSDT", "price": "100"}),
            ]
            get_endpoints: list[str] = []

            def get_response(url, **kwargs):
                endpoint = str(url).removeprefix("https://api.binance.com/api/v3")
                get_endpoints.append(endpoint)
                if endpoint == "/order" and len(get_responses) == 0:
                    client_id = kwargs["params"].get("origClientOrderId")
                    posted_id = post.call_args.kwargs["params"]["newClientOrderId"]
                    if client_id != posted_id:
                        raise AssertionError("Exact residual-stop query must use the ID from the single POST.")
                    return SimpleNamespace(status_code=200, json=lambda: {
                        "symbol": "BTCUSDT", "clientOrderId": posted_id, "orderId": 811,
                        "orderListId": -1, "side": "SELL", "type": "STOP_LOSS", "status": "NEW",
                        "origQty": baseline["quantity"], "executedQty": "0", "stopPrice": "95",
                    })
                if endpoint == "/account" and len(get_responses) == 0:
                    return SimpleNamespace(status_code=200, json=lambda: {"uid": UID, "accountType": "SPOT"})
                if not get_responses:
                    raise AssertionError(f"Unexpected Binance GET: {endpoint}")
                expected_endpoint, body = get_responses.pop(0)
                if endpoint != expected_endpoint:
                    raise AssertionError(f"Expected {expected_endpoint}, got {endpoint}")
                return SimpleNamespace(status_code=200, json=lambda body=body: body)

            def post_response(url, **kwargs):
                self.assertEqual("https://api.binance.com/api/v3/order", url)
                params = kwargs["params"]
                return SimpleNamespace(status_code=200, json=lambda: {
                    "symbol": "BTCUSDT", "clientOrderId": params["newClientOrderId"], "orderId": 811,
                    "orderListId": -1, "side": "SELL", "type": "STOP_LOSS", "status": "NEW",
                    "origQty": params["quantity"], "executedQty": "0", "stopPrice": params["stopPrice"],
                })

            with patch.dict(os.environ, {
                "SPOT_RECONCILE_TEST_KEY": API_KEY,
                "SPOT_RECONCILE_TEST_SECRET": API_SECRET,
            }), patch.object(
                spot_admin_runtime.requests, "get", side_effect=get_response,
            ) as get, patch.object(
                spot_admin_runtime.requests, "post", side_effect=post_response,
            ) as post, patch(
                "app.gui.shared.allocation_persistence.get_position_allocations_path",
                return_value=allocation_path,
            ), patch(
                "app.settings.live_safety.validate_live_trading_safety",
            ) as live_safety, redirect_stdout(StringIO()) as output:
                code = admin_cli.main(args)

        result = json.loads(output.getvalue())
        self.assertEqual(0, code, output.getvalue())
        self.assertTrue(result["ok"])
        self.assertTrue(result["account_identity_verified_twice"])
        self.assertEqual(811, result["residual_stop_order_id"])
        self.assertEqual("NEW", result["residual_stop_status"])
        self.assertEqual(baseline["quantity"], result["residual_quantity"])
        self.assertEqual(0, result["unresolved_after"])
        self.assertEqual(9, get.call_count)
        self.assertEqual([
            "/account", "/orderList", "/order", "/order", "/exchangeInfo",
            "/ticker/price", "/account", "/order", "/account",
        ], get_endpoints)
        self.assertEqual([], get_responses)
        post.assert_called_once()
        live_safety.assert_called_once()
        post_url, post_kwargs = post.call_args.args[0], post.call_args.kwargs
        self.assertEqual("https://api.binance.com/api/v3/order", post_url)
        post_params = post_kwargs["params"]
        self.assertEqual("BTCUSDT", post_params["symbol"])
        self.assertEqual("SELL", post_params["side"])
        self.assertEqual("STOP_LOSS", post_params["type"])
        self.assertEqual(baseline["quantity"], post_params["quantity"])
        self.assertEqual("95", post_params["stopPrice"])
        self.assertEqual("FULL", post_params["newOrderRespType"])
        self.assertTrue(post_params["newClientOrderId"].startswith("rs"))
        self.assertEqual("recovery_required", json.loads(marker_path.read_text(encoding="utf-8"))["state"])
        self.assertEqual(0, intents.get_order_intent_status(self.admin_owner)["unresolved_count"])

    def opo_list_observation(
        self, request: dict[str, str], *, pending_status: str, list_status: str,
    ) -> list[dict[str, object]]:
        list_response = {
            "symbol": "BTCUSDT", "orderListId": 500, "contingencyType": "OTO",
            "listStatusType": list_status, "listOrderStatus": "EXECUTING" if list_status == "EXEC_STARTED" else "ALL_DONE",
            "listClientOrderId": request["listClientOrderId"],
            "orders": [
                {"symbol": "BTCUSDT", "orderId": 501, "clientOrderId": request["workingClientOrderId"]},
                {"symbol": "BTCUSDT", "orderId": 502, "clientOrderId": request["pendingClientOrderId"]},
            ],
        }
        working_order = {
            "symbol": "BTCUSDT", "orderId": 501, "orderListId": 500,
            "clientOrderId": request["workingClientOrderId"], "side": "BUY", "type": "LIMIT",
            "status": "FILLED", "origQty": "0.1", "executedQty": "0.1", "timeInForce": "FOK",
        }
        pending_order = {
            "symbol": "BTCUSDT", "orderId": 502, "orderListId": 500,
            "clientOrderId": request["pendingClientOrderId"], "side": "SELL", "type": "STOP_LOSS",
            "status": pending_status, "origQty": "0.0999", "executedQty": "0",
            "stopPrice": "95",
        }
        current = intents._get_order_intent_record(self.admin_owner, request["listClientOrderId"])
        exit_request = current.get("strategy_exit_request") if isinstance(current, dict) else None
        if pending_status == "CANCELED" and isinstance(exit_request, dict) and "cancelNewClientOrderId" in exit_request:
            pending_order["clientOrderId"] = exit_request["cancelNewClientOrderId"]
        return [list_response, working_order, pending_order]

    def test_recover_opo_command_imports_entry_and_exact_triggered_stop_sell(self):
        marker_path, request = self.set_up_pending_opo_after_owner_loss()
        args = self.args()
        args[0] = "recover-spot-opos"
        list_response = {
            "symbol": "BTCUSDT", "orderListId": 500, "contingencyType": "OTO",
            "listStatusType": "ALL_DONE", "listOrderStatus": "ALL_DONE",
            "listClientOrderId": request["listClientOrderId"],
            "orders": [
                {"symbol": "BTCUSDT", "orderId": 501, "clientOrderId": request["workingClientOrderId"]},
                {"symbol": "BTCUSDT", "orderId": 502, "clientOrderId": request["pendingClientOrderId"]},
            ],
        }
        working_order = {
            "symbol": "BTCUSDT", "orderId": 501, "orderListId": 500,
            "clientOrderId": request["workingClientOrderId"], "side": "BUY", "type": "LIMIT",
            "status": "FILLED", "origQty": "0.1", "executedQty": "0.1", "timeInForce": "FOK",
            "cummulativeQuoteQty": "10", "updateTime": 1780000000000,
        }
        pending_order = {
            "symbol": "BTCUSDT", "orderId": 502, "orderListId": 500,
            "clientOrderId": request["pendingClientOrderId"], "side": "SELL", "type": "STOP_LOSS",
            "status": "FILLED", "origQty": "0.0999", "executedQty": "0.0999",
            "stopPrice": "95", "cummulativeQuoteQty": "9.4905", "updateTime": 1780000000010,
        }
        symbol_info = {"symbols": [{"symbol": "BTCUSDT", "baseAsset": "BTC", "quoteAsset": "USDT"}]}
        buy_trades = [{
            "symbol": "BTCUSDT", "id": 601, "orderId": 501,
            "price": "100", "qty": "0.1", "quoteQty": "10",
            "commission": "0.0001", "commissionAsset": "BTC",
            "time": 1780000000000, "isBuyer": True,
        }]
        sell_trades = [{
            "symbol": "BTCUSDT", "id": 602, "orderId": 502,
            "price": "95", "qty": "0.0999", "quoteQty": "9.4905",
            "commission": "0", "commissionAsset": "BTC",
            "time": 1780000000010, "isBuyer": False,
        }]
        responses = [
            SimpleNamespace(status_code=200, json=lambda: {"uid": UID, "accountType": "SPOT"}),
            SimpleNamespace(status_code=200, json=lambda: list_response),
            SimpleNamespace(status_code=200, json=lambda: working_order),
            SimpleNamespace(status_code=200, json=lambda: pending_order),
            SimpleNamespace(status_code=200, json=lambda: working_order),
            SimpleNamespace(status_code=200, json=lambda: symbol_info),
            SimpleNamespace(status_code=200, json=lambda: buy_trades),
            SimpleNamespace(status_code=200, json=lambda: list_response),
            SimpleNamespace(status_code=200, json=lambda: working_order),
            SimpleNamespace(status_code=200, json=lambda: pending_order),
            SimpleNamespace(status_code=200, json=lambda: pending_order),
            SimpleNamespace(status_code=200, json=lambda: symbol_info),
            SimpleNamespace(status_code=200, json=lambda: sell_trades),
            SimpleNamespace(status_code=200, json=lambda: list_response),
            SimpleNamespace(status_code=200, json=lambda: working_order),
            SimpleNamespace(status_code=200, json=lambda: pending_order),
            SimpleNamespace(status_code=200, json=lambda: {"uid": UID, "accountType": "SPOT"}),
        ]
        # Use the protected source prepared before this pending financial intent.
        allocation_path = self.allocation_path
        with patch.dict(os.environ, {
            "SPOT_RECONCILE_TEST_KEY": API_KEY,
            "SPOT_RECONCILE_TEST_SECRET": API_SECRET,
        }), patch.object(
            spot_admin_runtime.requests, "get", side_effect=responses,
        ) as request_calls, patch(
            "app.gui.shared.allocation_persistence.get_position_allocations_path",
            return_value=allocation_path,
        ), redirect_stdout(StringIO()) as output:
            code = admin_cli.main(args)
        saved = json.loads(allocation_path.read_text(encoding="utf-8"))
        recovered = saved["entry_allocations"]["BTCUSDT:L"][0]

        result = json.loads(output.getvalue())
        self.assertEqual(0, code, output.getvalue())
        self.assertTrue(result["ok"])
        self.assertEqual(1, result["recovered_entry_count"])
        self.assertEqual(1, result["recovered_exit_count"])
        self.assertEqual(2, result["recovered_trade_count"])
        self.assertEqual(0, result["unresolved_after"])
        self.assertEqual("Closed", recovered["status"])
        self.assertEqual(request["listClientOrderId"], recovered["spot_opo_stop_recovery"]["client_order_id"])
        self.assertEqual(17, request_calls.call_count)
        recovered_status = intents.get_order_intent_status(self.admin_owner)
        self.assertEqual(0, recovered_status["unresolved_count"])
        self.assertEqual([], recovered_status["spot_opo_client_order_ids"])
        self.assertEqual("recovery_required", json.loads(marker_path.read_text(encoding="utf-8"))["state"])

    def test_recover_opos_finishes_lost_ack_full_linked_sell_after_restart(self):
        self._recover_lost_ack_full_linked_sell_after_restart()

    def test_recover_opos_finishes_lost_retry_ack_full_linked_sell_after_restart(self):
        self._recover_lost_ack_full_linked_sell_after_restart(retry_attempt=True)

    def _recover_lost_ack_full_linked_sell_after_restart(self, *, retry_attempt=False):
        args = self.args()
        args[0] = "recover-spot-opos"
        exit_client_id = "recovery-exit-sell"
        with tempfile.TemporaryDirectory() as tmp:
            allocation_path = Path(tmp) / "allocations.json"
            marker_path, request = self.set_up_active_opo_with_linked_exit(
                allocation_path, exit_client_id=exit_client_id, retry_attempt=retry_attempt,
            )
            list_response = {
                "symbol": "BTCUSDT", "orderListId": 700, "contingencyType": "OTO",
                "listStatusType": "ALL_DONE", "listOrderStatus": "ALL_DONE",
                "listClientOrderId": request["listClientOrderId"],
                "orders": [
                    {"symbol": "BTCUSDT", "orderId": 701, "clientOrderId": request["workingClientOrderId"]},
                    {"symbol": "BTCUSDT", "orderId": 702, "clientOrderId": request["pendingClientOrderId"]},
                ],
            }
            working_order = {
                "symbol": "BTCUSDT", "orderId": 701, "orderListId": 700,
                "clientOrderId": request["workingClientOrderId"], "side": "BUY", "type": "LIMIT",
                "status": "FILLED", "origQty": "0.1", "executedQty": "0.1", "timeInForce": "FOK",
            }
            pending_order = {
                "symbol": "BTCUSDT", "orderId": 702, "orderListId": 700,
                "clientOrderId": request["pendingClientOrderId"], "side": "SELL", "type": "STOP_LOSS",
                "status": "CANCELED", "origQty": "0.0999", "executedQty": "0", "stopPrice": "95",
            }
            current = intents._get_order_intent_record(self.admin_owner, request["listClientOrderId"])
            pending_order["clientOrderId"] = current["strategy_exit_request"]["cancelNewClientOrderId"]
            exit_order = {
                "symbol": "BTCUSDT", "clientOrderId": exit_client_id, "orderId": 703,
                "orderListId": -1, "side": "SELL", "type": "MARKET", "status": "FILLED",
                "origQty": "0.0999", "executedQty": "0.0999", "cummulativeQuoteQty": "9.4905",
                "updateTime": 1780000000010,
            }
            symbol_info = {"symbols": [{"symbol": "BTCUSDT", "baseAsset": "BTC", "quoteAsset": "USDT"}]}
            sell_trades = [{
                "symbol": "BTCUSDT", "id": 704, "orderId": 703, "price": "95",
                "qty": "0.0999", "quoteQty": "9.4905", "commission": "0", "commissionAsset": "BTC",
                "time": 1780000000010, "isBuyer": False,
            }]
            bodies = [
                list_response, working_order, pending_order,
                exit_order,
                list_response, working_order, pending_order,
                exit_order, exit_order, sell_trades, symbol_info,
            ]

            def get_response(url, **_kwargs):
                body = {"uid": UID, "accountType": "SPOT"} if url.endswith("/account") else bodies.pop(0)
                return SimpleNamespace(status_code=200, json=lambda body=body: body)
            with patch.dict(os.environ, {
                "SPOT_RECONCILE_TEST_KEY": API_KEY,
                "SPOT_RECONCILE_TEST_SECRET": API_SECRET,
            }), patch.object(
                spot_admin_runtime.requests, "get", side_effect=get_response,
            ) as request_calls, patch(
                "app.gui.shared.allocation_persistence.get_position_allocations_path",
                return_value=allocation_path,
            ), redirect_stdout(StringIO()) as output:
                code = admin_cli.main(args)
            saved = json.loads(allocation_path.read_text(encoding="utf-8"))

        result = json.loads(output.getvalue())
        self.assertEqual(0, code, output.getvalue())
        self.assertTrue(result["ok"])
        self.assertEqual(1, result["recovered_strategy_exit_count"])
        self.assertEqual(1, result["recovered_trade_count"])
        self.assertEqual(0, result["unresolved_after"])
        self.assertFalse(result["exchange_orders_placed"])
        self.assertEqual(13, request_calls.call_count)
        row = saved["entry_allocations"]["BTCUSDT:L"][0]
        self.assertEqual("Closed", row["status"])
        self.assertEqual(exit_client_id, row["spot_sell_recoveries"][0]["client_order_id"])
        record = intents._get_order_intent_record(self.admin_owner, request["listClientOrderId"])
        self.assertEqual("completed", record["strategy_exit_state"])
        self.assertEqual("recovery_required", json.loads(marker_path.read_text(encoding="utf-8"))["state"])

    def test_recover_command_consumes_exact_owned_spot_sell_fill_before_resolving_intent(self):
        args = self.args()
        args[0] = "recover-spot-market-fills"
        responses = [
            SimpleNamespace(status_code=200, json=lambda: {"uid": UID, "accountType": "SPOT"}),
            SimpleNamespace(status_code=200, json=lambda: {
                "clientOrderId": PARAMS["newClientOrderId"], "symbol": "BTCUSDT", "side": "SELL",
                "orderId": 56, "status": "FILLED", "type": "MARKET", "price": "0",
                "origQty": "0.08", "executedQty": "0.08", "cummulativeQuoteQty": "1600",
                "updateTime": 1780000000010,
            }),
            SimpleNamespace(status_code=200, json=lambda: {"symbols": [{
                "symbol": "BTCUSDT", "baseAsset": "BTC", "quoteAsset": "USDT",
            }]}),
            SimpleNamespace(status_code=200, json=lambda: [{
                "symbol": "BTCUSDT", "id": 78, "orderId": 56,
                "price": "20000", "qty": "0.08", "quoteQty": "1600",
                "commission": "0.00003", "commissionAsset": "BTC",
                "time": 1780000000010, "isBuyer": False,
            }]),
            SimpleNamespace(status_code=200, json=lambda: {"uid": UID, "accountType": "SPOT"}),
        ]
        with tempfile.TemporaryDirectory() as tmp:
            allocation_path = Path(tmp) / ".trading_bot_allocations.json"
            buy_fill = {
                "symbol": "BTCUSDT", "client_order_id": "tracked-buy", "order_id": 54,
                "trade_ids": [77], "trade_count": 1, "gross_qty": "0.1", "net_qty": "0.1",
                "gross_quote_qty": "2000", "net_quote_cost": "2000", "average_cost": "20000",
                "commissions": [], "base_asset": "BTC", "quote_asset": "USDT",
                "fill_time_ms": 1780000000000, "signature": "a" * 64,
            }
            with patch(
                "app.gui.shared.allocation_persistence.get_position_allocations_path",
                return_value=allocation_path,
            ):
                wrapper = _SpotRuntime(self.audit_path)
                self.prebind_inventory(wrapper)
                self.author_tracked_buy(wrapper, allocation_path, buy_fill)
                self.set_up_pending_after_owner_loss(side="SELL", quantity="0.08", wrapper=wrapper)
                with patch.dict(os.environ, {
                    "SPOT_RECONCILE_TEST_KEY": API_KEY,
                    "SPOT_RECONCILE_TEST_SECRET": API_SECRET,
                }), patch.object(
                    spot_admin_runtime.requests, "get", side_effect=responses,
                ) as request, redirect_stdout(StringIO()) as output:
                    code = admin_cli.main(args)
            saved = json.loads(allocation_path.read_text(encoding="utf-8"))

        result = json.loads(output.getvalue())
        self.assertEqual(0, code, result)
        self.assertTrue(result["ok"])
        self.assertEqual(0, result["recovered_buy_fill_count"])
        self.assertEqual(1, result["recovered_sell_fill_count"])
        self.assertEqual(1, result["recovered_fill_count"])
        self.assertEqual(0, result["unresolved_after"])
        self.assertEqual(5, request.call_count)
        tracked = saved["entry_allocations"]["BTCUSDT:L"][0]
        self.assertEqual("Active", tracked["status"])
        self.assertAlmostEqual(0.01997, tracked["qty"])
        self.assertEqual("reconcile-intent-A", tracked["spot_sell_recoveries"][0]["client_order_id"])


if __name__ == "__main__":
    unittest.main()
