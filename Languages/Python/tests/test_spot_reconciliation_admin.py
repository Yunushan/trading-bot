from __future__ import annotations

import json
import os
import socket
import tempfile
import unittest
from contextlib import redirect_stdout
from io import StringIO
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from app.integrations.exchanges.binance.orders import order_intent_admin as admin_cli
from app.integrations.exchanges.binance.orders import order_intent_runtime as intents
from app.integrations.exchanges.binance.orders import spot_user_data_admin_runtime as spot_admin_runtime
from app.integrations.exchanges.binance.orders.order_intent_provisioning import (
    PROVISION_ACK,
    provision_order_intent_store,
)
from app.integrations.exchanges.binance.orders.spot_execution_owner import owner_marker_path


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

    def args(self) -> list[str]:
        return [
            "reconcile-spot", "--account-type", "Spot", "--mode", "Live",
            "--api-key-env", "SPOT_RECONCILE_TEST_KEY",
            "--api-secret-env", "SPOT_RECONCILE_TEST_SECRET",
        ]

    def set_up_pending_after_owner_loss(self) -> Path:
        wrapper = _SpotRuntime(self.audit_path)
        wrapper._ensure_spot_execution_owner()
        intents._begin_order_intent(
            wrapper, PARAMS, market="spot", source="offline-reconciliation-test",
        )
        owner = wrapper._spot_execution_owner
        owner.close()
        path = owner_marker_path(self.path)
        self.assertEqual("recovery_required", json.loads(path.read_text(encoding="utf-8"))["state"])
        return path

    def run_cli_with_responses(self, responses: list[object]) -> tuple[int, dict[str, object], object]:
        with patch.dict(os.environ, {
            "SPOT_RECONCILE_TEST_KEY": API_KEY,
            "SPOT_RECONCILE_TEST_SECRET": API_SECRET,
        }):
            with patch.object(spot_admin_runtime.requests, "get", side_effect=responses) as request:
                with redirect_stdout(StringIO()) as output:
                    code = admin_cli.main(self.args())
        return code, json.loads(output.getvalue()), request

    def test_exact_order_status_reconciles_without_rearming(self):
        marker_path = self.set_up_pending_after_owner_loss()
        responses = [
            SimpleNamespace(status_code=200, json=lambda: {"uid": UID, "accountType": "SPOT"}),
            SimpleNamespace(status_code=200, json=lambda: {
                "clientOrderId": PARAMS["newClientOrderId"], "symbol": "BTCUSDT",
                "orderId": 55, "status": "FILLED",
            }),
        ]
        code, result, request = self.run_cli_with_responses(responses)
        self.assertEqual(0, code)
        self.assertTrue(result["ok"])
        self.assertEqual(1, result["unresolved_before"])
        self.assertEqual(1, result["result_count"])
        self.assertEqual(0, result["unresolved_after"])
        self.assertEqual("accepted", result["results"][0]["state"])
        self.assertEqual(2, request.call_count)
        self.assertTrue(all(
            call.args[0].startswith("https://api.binance.com/api/v3/")
            for call in request.call_args_list
        ))
        order_params = request.call_args_list[1].kwargs["params"]
        self.assertEqual("BTCUSDT", order_params["symbol"])
        self.assertEqual(PARAMS["newClientOrderId"], order_params["origClientOrderId"])
        self.assertEqual("recovery_required", json.loads(marker_path.read_text(encoding="utf-8"))["state"])
        self.assertEqual(0, intents.get_order_intent_status(self.admin_owner)["unresolved_count"])

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
        self.set_up_pending_after_owner_loss()
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


if __name__ == "__main__":
    unittest.main()
