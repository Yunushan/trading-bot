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
from app.gui.shared import allocation_persistence as allocations
from app.integrations.exchanges.binance.orders.spot_inventory_namespace import ACCOUNT_NAMESPACE_KEY
from app.integrations.exchanges.binance.orders.spot_inventory_namespace_runtime import (
    namespace_for_owner, assert_bootstrap_empty_ledger,
)
from app.integrations.exchanges.binance.orders.order_intent_store import ledger_transactions
from app.integrations.exchanges.binance.orders.order_intent_provisioning import (
    PROVISION_ACK,
    migrate_spot_order_intent_store,
    provision_order_intent_store,
    rearm_spot_execution_owner,
    rotate_spot_owner_credentials,
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
        self.allocation_path = self.home / "allocations.json"
        self.enterContext(patch.object(allocations, "get_position_allocations_path", return_value=self.allocation_path))
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

    def initialize_inventory(self, wrapper) -> None:
        owner = wrapper._ensure_spot_execution_owner()
        namespace = namespace_for_owner(wrapper)
        with ledger_transactions(owner.ledger_path, self.allocation_path):
            assert_bootstrap_empty_ledger(wrapper, expected_store_id=owner.store_id)
            self.assertFalse(self.allocation_path.exists())
            allocations._write_snapshot(self.allocation_path, {
                "version": 1, "mode": "Live", "entry_allocations": {}, "open_position_records": {},
                ACCOUNT_NAMESPACE_KEY: namespace,
            })

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
        self.initialize_inventory(first)
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

    def test_offline_credential_rotation_preserves_intents_and_requires_rearm(self):
        self.provision()
        original = _SpotWrapper(self.audit_a)
        self.addCleanup(self.close_owner, original)
        self.initialize_inventory(original)
        result = original.place_spot_market_order("BTCUSDT", "BUY", quantity=0.1, price=100.0)
        self.assertTrue(result["ok"], result)
        self.close_owner(original)

        # Model the explicit GUI checkpoint after its verified allocation is durable.
        intents._update_order_intent_by_id(
            original,
            result["info"]["clientOrderId"],
            state="accepted",
            portfolio_reconciled=True,
            portfolio_qty="0.1",
            portfolio_recovery_signature="f" * 64,
        )

        before = intents._read_ledger(self.path)
        before_intents = json.loads(json.dumps(before["intents"]))
        store_id = before["store_id"]
        previous_fingerprint = before["binding"]["credential_fingerprint"]
        rotated_admin = _offline_admin(self.audit_b, key="new-offline-key")
        rotated = rotate_spot_owner_credentials(
            rotated_admin,
            acknowledgement=PROVISION_ACK,
            reconciliation_reference="change-456",
        )

        self.assertTrue(rotated["rotated"])
        self.assertTrue(rotated["requires_rearm"])
        current = intents._read_ledger(self.path, expected_binding=intents._intent_binding(rotated_admin))
        self.assertEqual(store_id, current["store_id"])
        self.assertEqual(before_intents, current["intents"])
        history = current["credential_rotation_history"]
        self.assertEqual(1, len(history))
        self.assertEqual(previous_fingerprint, history[0]["previous_fingerprint"])
        self.assertEqual(current["binding"]["credential_fingerprint"], history[0]["new_fingerprint"])
        self.assertEqual("change-456", history[0]["reconciliation_reference"])
        marker_path = owner_marker_path(self.path)
        self.assertEqual("recovery_required", json.loads(marker_path.read_text())["state"])

        with self.assertRaisesRegex(LiveTradingSafetyError, "different credentials"):
            intents._ensure_spot_execution_owner(original)
        restarted = _SpotWrapper(self.audit_b, key="new-offline-key")
        with self.assertRaisesRegex(LiveTradingSafetyError, "reconciliation"):
            restarted._ensure_spot_execution_owner()

        rearm_spot_execution_owner(
            rotated_admin, acknowledgement=PROVISION_ACK, reconciliation_reference="change-456-verified",
        )
        restarted._ensure_spot_execution_owner()
        self.addCleanup(self.close_owner, restarted)

    def test_rotation_refuses_unresolved_intents_without_changing_ledger_or_marker(self):
        self.provision()
        wrapper = _SpotWrapper(self.audit_a)
        self.addCleanup(self.close_owner, wrapper)
        self.initialize_inventory(wrapper)
        intents._begin_order_intent(wrapper, PARAMS, market="spot", source="offline-test")
        self.close_owner(wrapper)
        ledger_before = self.path.read_bytes()
        marker_path = owner_marker_path(self.path)
        marker_before = marker_path.read_bytes()

        with self.assertRaisesRegex(LiveTradingSafetyError, "Unresolved order intents"):
            rotate_spot_owner_credentials(
                _offline_admin(self.audit_b, key="new-offline-key"),
                acknowledgement=PROVISION_ACK,
                reconciliation_reference="change-457",
            )
        self.assertEqual(ledger_before, self.path.read_bytes())
        self.assertEqual(marker_before, marker_path.read_bytes())

    def test_rotation_requires_acknowledgement_and_reference_before_disarming(self):
        self.provision()
        ledger_before = self.path.read_bytes()
        marker_path = owner_marker_path(self.path)
        marker_before = marker_path.read_bytes()
        rotated_admin = _offline_admin(self.audit_b, key="new-offline-key")
        for acknowledgement, reference, expected in (
            ("", "change-458", "Stop all executors"),
            (PROVISION_ACK, "", "reference"),
        ):
            with self.subTest(acknowledgement=acknowledgement, reference=reference):
                with self.assertRaisesRegex(LiveTradingSafetyError, expected):
                    rotate_spot_owner_credentials(
                        rotated_admin, acknowledgement=acknowledgement,
                        reconciliation_reference=reference,
                    )
                self.assertEqual(ledger_before, self.path.read_bytes())
                self.assertEqual(marker_before, marker_path.read_bytes())

        running = _SpotWrapper(self.audit_a)
        self.addCleanup(self.close_owner, running)
        running._ensure_spot_execution_owner()
        ledger_before = self.path.read_bytes()
        marker_before = marker_path.read_bytes()
        with self.assertRaisesRegex(LiveTradingSafetyError, "owner is active"):
            rotate_spot_owner_credentials(
                rotated_admin, acknowledgement=PROVISION_ACK,
                reconciliation_reference="change-459",
            )
        self.assertEqual(ledger_before, self.path.read_bytes())
        self.assertEqual(marker_before, marker_path.read_bytes())

    def test_rotation_write_failure_leaves_owner_disarmed_and_old_binding_recoverable(self):
        self.provision()
        ledger_before = self.path.read_bytes()
        with patch(
            "app.integrations.exchanges.binance.orders.order_intent_provisioning.write_ledger",
            side_effect=OSError("disk full"),
        ):
            with self.assertRaisesRegex(LiveTradingSafetyError, "storage failed"):
                rotate_spot_owner_credentials(
                    _offline_admin(self.audit_b, key="new-offline-key"),
                    acknowledgement=PROVISION_ACK,
                    reconciliation_reference="change-460",
                )

        self.assertEqual(ledger_before, self.path.read_bytes())
        marker_path = owner_marker_path(self.path)
        self.assertEqual("recovery_required", json.loads(marker_path.read_text())["state"])
        rearm_spot_execution_owner(
            self.admin, acknowledgement=PROVISION_ACK, reconciliation_reference="change-460-recovered",
        )
        recovered = _SpotWrapper(self.audit_a)
        self.addCleanup(self.close_owner, recovered)
        recovered._ensure_spot_execution_owner()

    def test_spot_history_migration_preserves_legacy_ledger_and_requires_rearm(self):
        legacy_path = intents._legacy_intent_path(self.admin)
        legacy_path.write_text(json.dumps({
            "format_version": 1,
            "intents": {
                "legacy-complete": {
                    "client_order_id": "legacy-complete", "state": "rejected", "market": "spot",
                    "symbol": "BTCUSDT", "operator_metadata": {"retain": ["all", "fields"]},
                },
            },
        }))
        original_bytes = legacy_path.read_bytes()

        migration = migrate_spot_order_intent_store(
            self.admin, acknowledgement=PROVISION_ACK, reconciliation_reference="migration-001",
        )
        self.assertTrue(migration["migrated"])
        self.assertFalse(migration["resumed"])
        self.assertTrue(migration["requires_rearm"])
        self.assertFalse(legacy_path.exists())
        self.assertEqual(original_bytes, Path(migration["backup_path"]).read_bytes())
        current = intents._read_ledger(self.path, expected_binding=intents._intent_binding(self.admin))
        self.assertEqual(2, current["format_version"])
        self.assertEqual("rejected", current["intents"]["legacy-complete"]["state"])
        self.assertEqual({"retain": ["all", "fields"]}, current["intents"]["legacy-complete"]["operator_metadata"])
        marker = json.loads(owner_marker_path(self.path).read_text())
        self.assertEqual("recovery_required", marker["state"])
        self.assertEqual("migration-001", marker["reconciliation_reference"])

        rearm_spot_execution_owner(
            self.admin, acknowledgement=PROVISION_ACK, reconciliation_reference="migration-001-verified",
        )
        runtime = _SpotWrapper(self.audit_b)
        self.addCleanup(self.close_owner, runtime)
        runtime._ensure_spot_execution_owner()

    def test_spot_history_migration_resumes_safely_after_target_write_failure(self):
        legacy_path = intents._legacy_intent_path(self.admin)
        legacy_path.write_text(json.dumps({
            "format_version": 1,
            "intents": {
                "legacy-rejected": {"client_order_id": "legacy-rejected", "state": "rejected"},
            },
        }))
        with patch(
            "app.integrations.exchanges.binance.orders.order_intent_provisioning.write_ledger",
            side_effect=OSError("disk full"),
        ):
            with self.assertRaisesRegex(LiveTradingSafetyError, "storage failed"):
                migrate_spot_order_intent_store(
                    self.admin, acknowledgement=PROVISION_ACK, reconciliation_reference="migration-002",
                )

        self.assertFalse(self.path.exists())
        self.assertFalse(legacy_path.exists())
        marker_path = owner_marker_path(self.path)
        self.assertEqual("recovery_required", json.loads(marker_path.read_text())["state"])
        backup_path = legacy_path.with_name(f"{legacy_path.name}.spot-live-uid-{UID}.backup")
        self.assertTrue(backup_path.exists())

        resumed = migrate_spot_order_intent_store(
            self.admin, acknowledgement=PROVISION_ACK, reconciliation_reference="migration-002",
        )
        self.assertTrue(resumed["resumed"])
        self.assertTrue(self.path.exists())
        self.assertEqual("recovery_required", json.loads(marker_path.read_text())["state"])

    def test_spot_history_migration_preserves_existing_v2_store_identity(self):
        legacy_path = intents._legacy_intent_path(self.admin)
        source = {
            "format_version": 2,
            "binding": intents._intent_binding(self.admin),
            "store_id": "00000000-0000-4000-8000-000000000001",
            "created_at": "2026-09-23T12:00:00+00:00",
            "intents": {"legacy-v2-rejected": {"client_order_id": "legacy-v2-rejected", "state": "rejected"}},
        }
        legacy_path.write_text(json.dumps(source))

        migration = migrate_spot_order_intent_store(
            self.admin, acknowledgement=PROVISION_ACK, reconciliation_reference="migration-v2-001",
        )
        self.assertEqual(source["store_id"], intents._read_ledger(self.path)["store_id"])
        self.assertEqual(source["intents"], intents._read_ledger(self.path)["intents"])
        self.assertEqual("recovery_required", json.loads(owner_marker_path(self.path).read_text())["state"])
        self.assertTrue(Path(migration["backup_path"]).exists())

    def test_spot_history_migration_refuses_unresolved_intent_without_mutation(self):
        legacy_path = intents._legacy_intent_path(self.admin)
        legacy_path.write_text(json.dumps({
            "format_version": 1,
            "intents": {
                "legacy-pending": {"client_order_id": "legacy-pending", "state": "pending"},
            },
        }))
        original_bytes = legacy_path.read_bytes()

        with self.assertRaisesRegex(LiveTradingSafetyError, "Unresolved order intents"):
            migrate_spot_order_intent_store(
                self.admin, acknowledgement=PROVISION_ACK, reconciliation_reference="migration-003",
            )
        self.assertEqual(original_bytes, legacy_path.read_bytes())
        self.assertFalse(self.path.exists())
        self.assertFalse(owner_marker_path(self.path).exists())

    def test_owner_marker_change_and_unresolved_history_block_submission_and_rearm(self):
        self.provision()
        wrapper = _SpotWrapper(self.audit_a)
        self.addCleanup(self.close_owner, wrapper)
        self.initialize_inventory(wrapper)
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
            args[0] = "rotate-credentials"
            args[args.index("--api-key-env") + 1] = "SPOT_KEY_ROTATED_TEST"
            with patch.dict(os.environ, {"SPOT_KEY_ROTATED_TEST": "new-offline-key"}):
                with redirect_stdout(StringIO()) as output:
                    self.assertEqual(0, admin_cli.main(args))
            self.assertTrue(json.loads(output.getvalue())["rotated"])
            self.assertEqual("recovery_required", json.loads(owner_marker_path(self.path).read_text())["state"])

    def test_cli_migrates_existing_spot_history_offline(self):
        legacy_path = intents._legacy_intent_path(self.admin)
        legacy_path.write_text(json.dumps({
            "format_version": 1,
            "intents": {"cli-rejected": {"client_order_id": "cli-rejected", "state": "rejected"}},
        }))
        args = [
            "migrate-spot", "--account-type", "Spot", "--spot-account-uid-env", "SPOT_UID_MIGRATION_TEST",
            "--audit-log-path", str(self.audit_a), "--mode", "Live", "--api-key-env", "SPOT_KEY_MIGRATION_TEST",
            "--acknowledgement", PROVISION_ACK, "--reconciliation-reference", "migration-cli-001",
        ]
        with patch.dict(os.environ, {
            "SPOT_UID_MIGRATION_TEST": str(UID), "SPOT_KEY_MIGRATION_TEST": "offline-key",
        }):
            with redirect_stdout(StringIO()) as output:
                self.assertEqual(0, admin_cli.main(args))
        result = json.loads(output.getvalue())
        self.assertTrue(result["migrated"])
        self.assertTrue(result["requires_rearm"])
        self.assertFalse(legacy_path.exists())
        self.assertTrue(self.path.exists())

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
