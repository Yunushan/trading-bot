"""Offline, single-profile Binance Spot ownership regressions."""

from __future__ import annotations

import json
import multiprocessing
import os
import socket
import tempfile
import unittest
from contextlib import redirect_stdout
from io import StringIO
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from app.integrations.exchanges.binance.orders import order_intent_runtime as intents
from app.integrations.exchanges.binance.orders import order_intent_admin as admin_cli
from app.integrations.exchanges.binance.orders.order_intent_provisioning import (
    PROVISION_ACK,
    provision_order_intent_store,
    rearm_spot_execution_owner,
)
from app.integrations.exchanges.binance.orders.order_sizing_runtime import bind_binance_order_sizing_runtime
from app.integrations.exchanges.binance.orders.spot_execution_owner import owner_lock_path, owner_marker_path
from app.settings.live_safety import LiveTradingSafetyError


UID = 12345678
PARAMS = {"newClientOrderId": "owner-intent-A", "symbol": "BTCUSDT", "side": "BUY", "type": "MARKET", "quantity": "0.1"}


class _FakeClient:
    def __init__(self) -> None:
        self.orders: list[dict[str, object]] = []

    def create_order(self, **params):
        self.orders.append(dict(params))
        return {
            "orderId": len(self.orders), "clientOrderId": params["newClientOrderId"],
            "symbol": params["symbol"], "side": params["side"], "status": "FILLED",
            "origQty": params["quantity"], "executedQty": params["quantity"],
        }


class _SpotWrapper:
    _enforce_spot_execution_owner = True

    def __init__(self, audit_path: Path, *, key: str = "offline-key", uid: object = UID, mode: str = "Live") -> None:
        self.account_type = "SPOT"
        self.mode = mode
        self.api_key = key
        self.api_secret = "offline-secret"
        self.client = _FakeClient()
        self._order_audit_log_path = audit_path
        self.account_response: object = {"uid": uid, "accountType": "SPOT"}
        self.account_reads = 0

    def _http_signed_spot(self, path: str):
        assert path == "/v3/account"
        self.account_reads += 1
        return self.account_response

    def get_spot_symbol_filters(self, _symbol: str):
        return {"stepSize": 0.001, "minQty": 0.001, "minNotional": 5.0}

    def get_last_price(self, _symbol: str) -> float:
        return 100.0


intents.bind_binance_order_intent_runtime(_SpotWrapper)
bind_binance_order_sizing_runtime(_SpotWrapper)


def _offline_admin(audit_path: Path, *, key: str = "offline-key", uid: int = UID):
    return SimpleNamespace(
        _order_audit_log_path=audit_path, api_key=key, mode="Live", account_type="SPOT",
        _enforce_spot_execution_owner=True, _operator_spot_account_uid=uid,
    )


def _claim_in_child(home: str, audit_path: str, ready, release) -> None:
    with patch.object(Path, "home", return_value=Path(home)):
        wrapper = _SpotWrapper(Path(audit_path))
        wrapper._ensure_spot_execution_owner()
        ready.set()
        release.wait(timeout=30)


class SpotExecutionOwnerTests(unittest.TestCase):
    def setUp(self) -> None:
        self.home = Path(self.enterContext(tempfile.TemporaryDirectory())).resolve()
        self.enterContext(patch.object(Path, "home", return_value=self.home))
        self.enterContext(patch.object(socket.socket, "connect", side_effect=AssertionError("No network calls")))
        self.audit_a = self.home / "first" / "audit.jsonl"
        self.audit_b = self.home / "second" / "audit.jsonl"
        self.audit_a.parent.mkdir()
        self.audit_b.parent.mkdir()
        self.admin = _offline_admin(self.audit_a)
        self.path = intents._intent_path(self.admin)
        self.assertEqual("uid-12345678", self.path.parent.name)
        self.assertNotEqual(self.path, intents._legacy_intent_path(self.admin))

    def provision(self) -> None:
        provision_order_intent_store(self.admin, acknowledgement=PROVISION_ACK)

    def close_owner(self, wrapper: _SpotWrapper) -> None:
        owner = getattr(wrapper, "_spot_execution_owner", None)
        if owner is not None and owner.fd is not None:
            owner.close()

    def test_two_audit_paths_resolve_one_account_ledger_and_second_wrapper_is_blocked(self):
        self.provision()
        first = _SpotWrapper(self.audit_a)
        second = _SpotWrapper(self.audit_b)
        self.addCleanup(self.close_owner, first)
        self.addCleanup(self.close_owner, second)
        self.assertEqual(self.path, intents._intent_path(first))
        self.assertEqual(self.path, intents._intent_path(second))
        result = first.place_spot_market_order("BTCUSDT", "BUY", quantity=0.1, price=100.0)
        self.assertTrue(result["ok"], result)
        blocked = second.place_spot_market_order("BTCUSDT", "BUY", quantity=0.1, price=100.0)
        self.assertFalse(blocked["ok"])
        self.assertIn("owner", blocked["error"].lower())
        self.assertEqual([], second.client.orders)
        self.assertEqual(1, len(first.client.orders))
        self.assertEqual(1, intents.get_order_intent_status(first)["intent_count"])
        self.assertEqual(1, first.account_reads)

    def test_key_rotation_and_missing_or_invalid_signed_uid_fail_before_post(self):
        self.provision()
        for uid in (None, "12345678", 0, -1, True):
            with self.subTest(uid=uid):
                wrapper = _SpotWrapper(self.audit_a, uid=uid)
                result = wrapper.place_spot_market_order("BTCUSDT", "BUY", quantity=0.1, price=100.0)
                self.assertFalse(result["ok"])
                self.assertEqual([], wrapper.client.orders)
        rotated = _SpotWrapper(self.audit_b, key="new-offline-key")
        result = rotated.place_spot_market_order("BTCUSDT", "BUY", quantity=0.1, price=100.0)
        self.assertFalse(result["ok"])
        self.assertEqual([], rotated.client.orders)
        self.assertEqual(0, intents.get_order_intent_status(self.admin)["intent_count"])

    def test_owner_loss_and_credential_mutation_block_post_and_require_rearm(self):
        self.provision()
        wrapper = _SpotWrapper(self.audit_a)
        wrapper._ensure_spot_execution_owner()
        wrapper.api_key = "mutated-key"
        result = wrapper.place_spot_market_order("BTCUSDT", "BUY", quantity=0.1, price=100.0)
        self.assertFalse(result["ok"])
        self.assertEqual([], wrapper.client.orders)
        wrapper.api_key = "offline-key"
        self.close_owner(wrapper)
        marker = json.loads(owner_marker_path(self.path).read_text(encoding="utf-8"))
        self.assertEqual("recovery_required", marker["state"])
        with self.assertRaisesRegex(LiveTradingSafetyError, "reconciliation"):
            _SpotWrapper(self.audit_b)._ensure_spot_execution_owner()
        with self.assertRaisesRegex(LiveTradingSafetyError, "acknowledgement"):
            rearm_spot_execution_owner(self.admin, acknowledgement="", reconciliation_reference="incident-123")
        with self.assertRaisesRegex(LiveTradingSafetyError, "reference"):
            rearm_spot_execution_owner(self.admin, acknowledgement=PROVISION_ACK, reconciliation_reference="")
        rearm_spot_execution_owner(
            self.admin, acknowledgement=PROVISION_ACK, reconciliation_reference="incident-123",
        )
        restarted = _SpotWrapper(self.audit_b)
        self.addCleanup(self.close_owner, restarted)
        restarted._ensure_spot_execution_owner()
        self.assertEqual("incident-123", json.loads(owner_marker_path(self.path).read_text())["reconciliation_reference"])

    def test_owner_marker_change_and_unresolved_history_block_submission_and_rearm(self):
        self.provision()
        wrapper = _SpotWrapper(self.audit_a)
        self.addCleanup(self.close_owner, wrapper)
        intents._begin_order_intent(wrapper, PARAMS, market="spot", source="offline-test")
        marker_path = owner_marker_path(self.path)
        original = marker_path.read_text(encoding="utf-8")
        marker = json.loads(original)
        marker["state"] = "armed"
        marker_path.write_text(json.dumps(marker), encoding="utf-8")
        try:
            result = wrapper.place_spot_market_order("BTCUSDT", "BUY", quantity=0.1, price=100.0)
            self.assertFalse(result["ok"])
            self.assertEqual([], wrapper.client.orders)
        finally:
            marker_path.write_text(original, encoding="utf-8")
        self.close_owner(wrapper)
        with self.assertRaisesRegex(LiveTradingSafetyError, "Unresolved order intents"):
            rearm_spot_execution_owner(
                self.admin, acknowledgement=PROVISION_ACK, reconciliation_reference="incident-124",
            )

    def test_cli_spot_provision_and_rearm_require_uid_env_and_reference(self):
        args = [
            "initialize", "--account-type", "Spot", "--spot-account-uid-env", "SPOT_UID_TEST",
            "--audit-log-path", str(self.audit_a), "--mode", "Live", "--api-key-env", "SPOT_KEY_TEST",
            "--acknowledgement", PROVISION_ACK,
        ]
        with patch.dict(os.environ, {"SPOT_UID_TEST": str(UID), "SPOT_KEY_TEST": "offline-key"}):
            with redirect_stdout(StringIO()) as output:
                self.assertEqual(0, admin_cli.main(args))
            self.assertTrue(json.loads(output.getvalue())["ok"])
            self.assertTrue(self.path.exists())
            wrapper = _SpotWrapper(self.audit_a)
            wrapper._ensure_spot_execution_owner()
            self.close_owner(wrapper)
            args[0] = "rearm"
            args.extend(["--reconciliation-reference", "INC-1234"])
            with redirect_stdout(StringIO()) as output:
                self.assertEqual(0, admin_cli.main(args))
            self.assertTrue(json.loads(output.getvalue())["rearmed"])
            self.assertEqual("INC-1234", json.loads(owner_marker_path(self.path).read_text())["reconciliation_reference"])

    def test_separate_process_cannot_claim_and_crash_requires_reconciliation(self):
        self.provision()
        context = multiprocessing.get_context("spawn")
        ready, release = context.Event(), context.Event()
        process = context.Process(target=_claim_in_child, args=(str(self.home), str(self.audit_a), ready, release))
        process.start()
        try:
            self.assertTrue(ready.wait(timeout=30))
            competing = _SpotWrapper(self.audit_b)
            with self.assertRaisesRegex(LiveTradingSafetyError, "owner is unavailable"):
                competing._ensure_spot_execution_owner()
            self.assertEqual([], competing.client.orders)
        finally:
            if process.is_alive():
                process.terminate()
            process.join(timeout=15)
        with self.assertRaisesRegex(LiveTradingSafetyError, "reconciliation"):
            _SpotWrapper(self.audit_b)._ensure_spot_execution_owner()
        self.assertTrue(owner_lock_path(self.path).exists())

    def test_demo_spot_keeps_existing_intent_path_and_needs_no_owner_marker(self):
        demo = _SpotWrapper(self.audit_a, mode="Demo/Testnet")
        self.assertEqual(intents._legacy_intent_path(demo), intents._intent_path(demo))
        provision_order_intent_store(demo, acknowledgement=PROVISION_ACK)
        result = demo.place_spot_market_order("BTCUSDT", "BUY", quantity=0.1, price=100.0)
        self.assertTrue(result["ok"], result)
        self.assertFalse(owner_marker_path(intents._intent_path(demo)).exists())


if __name__ == "__main__":
    unittest.main()
