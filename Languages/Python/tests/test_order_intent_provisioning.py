"""Exercise explicit store administration without any real exchange or credentials."""
from __future__ import annotations

import contextlib
import copy
import errno
import io
import json
import multiprocessing
import os
from pathlib import Path
import socket
import subprocess
import sys
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch

from app.integrations.exchanges.binance.orders import order_intent_admin as admin
from app.integrations.exchanges.binance.orders import order_intent_provisioning as provisioning
from app.integrations.exchanges.binance.orders import order_intent_runtime as ledger
from app.integrations.exchanges.binance.orders import order_intent_store as store
from app.integrations.exchanges.binance.transport.http_diagnostic_runtime import get_connector_health_snapshot
from app.service.schemas.status import build_exchange_connector_snapshot
from app.settings.live_safety import LiveTradingSafetyError

PYTHON_ROOT = Path(__file__).resolve().parents[1]
ROOT = PYTHON_ROOT.parents[1]
ACK = provisioning.PROVISION_ACK
KEY = "offline-unit-api-key"
PARAMS = {"newClientOrderId": "intent-A", "symbol": "BTCUSDT", "side": "BUY", "type": "MARKET", "quantity": "1"}


def _owner(directory, *, mode="Live", key=KEY):
    return SimpleNamespace(_order_audit_log_path=Path(directory) / "audit.jsonl", mode=mode, api_key=key)


def _initialize_race(directory, barrier, results):
    barrier.wait(timeout=30)
    try:
        provisioning.provision_order_intent_store(_owner(directory), acknowledgement=ACK)
        results.put("initialized")
    except LiveTradingSafetyError as exc:
        results.put(str(exc))


class OrderIntentProvisioningTests(unittest.TestCase):
    def setUp(self):
        self.directory = Path(self.enterContext(tempfile.TemporaryDirectory())).resolve()
        self.owner = _owner(self.directory)
        self.path = ledger._intent_path(self.owner)
        self.enterContext(patch.object(socket.socket, "connect", side_effect=AssertionError("Network forbidden")))
        self.enterContext(patch.dict(os.environ, {
            "USERPROFILE": str(self.directory), "HOME": str(self.directory),
            "TEMP": str(self.directory), "TMP": str(self.directory),
        }, clear=True))

    def initialize(self, **kwargs):
        return provisioning.provision_order_intent_store(self.owner, acknowledgement=ACK, **kwargs)

    def begin(self, owner=None, identifier="intent-A"):
        return ledger._begin_order_intent(owner or self.owner, dict(PARAMS, newClientOrderId=identifier),
                                          market="futures", source="offline-test")

    def assert_storage_blocked(self, owner=None, message=""):
        owner = owner or self.owner
        owner._query_order_intent_exchange = Mock(side_effect=AssertionError("No exchange query without trusted history"))
        for operation in (
            lambda: self.begin(owner), lambda: ledger.get_order_intent_status(owner),
            lambda: ledger._mark_order_intent_submitted(owner, PARAMS, via="test"),
            lambda: ledger.reconcile_order_intent(owner, "intent-A"),
        ):
            with self.assertRaisesRegex(LiveTradingSafetyError, message):
                operation()
        owner._query_order_intent_exchange.assert_not_called()

    def test_missing_store_is_not_implicitly_initialized_by_any_runtime_operation(self):
        self.assert_storage_blocked(message="ledger is missing")
        self.assertFalse(self.path.exists())

    def test_first_use_requires_explicit_acknowledgement_and_credential_environment_identity(self):
        for acknowledgement in (None, "", "yes", ACK.lower()):
            with self.subTest(acknowledgement=acknowledgement), self.assertRaises(LiveTradingSafetyError):
                provisioning.provision_order_intent_store(self.owner, acknowledgement=acknowledgement)
        for key, mode in ((None, "Live"), ("", "Live"), ([], "Live"), (KEY, None), (KEY, "Paper")):
            with self.subTest(key=key, mode=mode), self.assertRaises(LiveTradingSafetyError):
                provisioning.provision_order_intent_store(_owner(self.directory, key=key, mode=mode), acknowledgement=ACK)
        self.assertFalse(self.path.exists())

    def test_provisioned_store_is_private_bound_and_survives_restart(self):
        result = self.initialize()
        payload = ledger._read_ledger(self.path, expected_binding=ledger._intent_binding(self.owner))
        self.assertEqual(2, payload["format_version"])
        self.assertEqual({}, payload["intents"])
        self.assertEqual(0, result["intent_count"])
        self.assertIsNone(result["backup_path"])
        self.assertNotIn(KEY, self.path.read_text())
        if os.name != "nt":
            self.assertEqual(0o600, self.path.stat().st_mode & 0o777)
        self.begin()
        restarted = _owner(self.directory)
        with self.assertRaisesRegex(LiveTradingSafetyError, "already has state pending"):
            self.begin(restarted)
        self.assertEqual(1, ledger.get_order_intent_status(restarted)["unresolved_count"])

    def test_different_keys_or_environment_cannot_read_submit_update_or_reconcile(self):
        self.initialize()
        self.begin()
        before = self.path.read_bytes()
        for key, mode in (("different-key", "Live"), (KEY, "Demo/Testnet")):
            with self.subTest(key=key, mode=mode):
                self.assert_storage_blocked(_owner(self.directory, key=key, mode=mode), "different credentials or environment")
        self.assertEqual(before, self.path.read_bytes())

    def test_same_environment_alias_does_not_change_identity(self):
        self.owner.mode = "Demo/Testnet"
        self.initialize()
        status = ledger.get_order_intent_status(_owner(self.directory, mode="Testnet"))
        self.assertTrue(status["storage_ready"])
        self.assertEqual(0, status["intent_count"])

    def test_deletion_after_any_submission_state_blocks_restart_and_restoration_preserves_records(self):
        for state in ("pending", "submitted", "unknown", "accepted"):
            with self.subTest(state=state), tempfile.TemporaryDirectory() as directory:
                owner = _owner(directory)
                provisioning.provision_order_intent_store(owner, acknowledgement=ACK)
                self.begin(owner)
                ledger._update_order_intent(owner, PARAMS, state=state)
                path = ledger._intent_path(owner)
                previous = path.read_bytes()
                self.assertEqual(Path(directory).resolve(), path.parent)
                path.unlink()
                restarted = _owner(directory)
                self.assert_storage_blocked(restarted, "ledger is missing")
                self.assertFalse(path.exists())
                path.write_bytes(previous)
                self.assertEqual(state, ledger._get_order_intent_record(restarted, "intent-A")["state"])
                with self.assertRaisesRegex(LiveTradingSafetyError, "already has state"):
                    self.begin(restarted)

    def test_missing_or_mismatched_storage_never_reaches_primary_or_fallback_post(self):
        from test_binance_package_split_smoke import _FuturesAuditWrapper

        wrapper = _FuturesAuditWrapper()
        self.addCleanup(wrapper.close)
        wrapper._configure_order_audit(path=self.owner._order_audit_log_path)
        wrapper.client.futures_create_order = Mock(side_effect=AssertionError("No primary POST"))
        wrapper._testnet_order_fallback_client = Mock(side_effect=AssertionError("No fallback POST"))
        with patch.object(provisioning, "provision_order_intent_store") as automatic:
            with self.assertRaisesRegex(LiveTradingSafetyError, "ledger is missing"):
                wrapper._futures_create_order_with_fallback(dict(PARAMS))
            automatic.assert_not_called()
        self.assertFalse(self.path.exists())
        wrapper.client.futures_create_order.assert_not_called()
        wrapper._testnet_order_fallback_client.assert_not_called()

    def test_initialize_never_overwrites_existing_legacy_current_corrupt_or_directory_store(self):
        for contents in ('{"format_version":1,"intents":{}}', 'invalid', '{"format_version":2}'):
            with self.subTest(contents=contents):
                self.path.write_text(contents)
                with self.assertRaisesRegex(LiveTradingSafetyError, "already exists"):
                    self.initialize()
                self.assertEqual(contents, self.path.read_text())
        self.path.unlink()
        self.path.mkdir()
        with self.assertRaisesRegex(LiveTradingSafetyError, "already exists"):
            self.initialize()

    def test_nonempty_current_or_rotated_audit_prevents_empty_history_initialization(self):
        for name in ("audit.jsonl", "audit.jsonl.1", "audit.jsonl.100"):
            with self.subTest(name=name):
                audit = self.directory / name
                audit.write_text('{"event":"exchange_order_request"}\n')
                with self.assertRaisesRegex(LiveTradingSafetyError, "Audit history exists"):
                    self.initialize()
                self.assertFalse(self.path.exists())
                audit.unlink()

    def test_home_expansion_also_applies_to_audit_history_check(self):
        self.owner._order_audit_log_path = "~/audit.jsonl"
        (self.directory / "audit.jsonl.1").write_text("previous history")
        with patch.object(Path, "home", return_value=self.directory), patch.dict(os.environ, {
            "USERPROFILE": str(self.directory), "HOME": str(self.directory),
        }):
            with self.assertRaisesRegex(LiveTradingSafetyError, "Audit history exists"):
                self.initialize()
        self.assertFalse(self.path.exists())

    def test_unrelated_siblings_and_empty_audit_do_not_prevent_first_use(self):
        (self.directory / "audit.jsonl").touch()
        (self.directory / "audit.jsonl.note").write_text("unrelated operator note")
        self.initialize()
        self.assertTrue(ledger.get_order_intent_status(self.owner)["storage_ready"])

    def test_missing_identity_metadata_is_not_silently_recreated(self):
        self.initialize()
        original = json.loads(self.path.read_text())
        changes = [
            ("store_id", None), ("store_id", "not-a-uuid"), ("created_at", ""),
            ("created_at", "2026-09-06T12:00:00"), ("binding", None), ("binding", {}),
            ("binding", {**original["binding"], "environment": "paper"}),
            ("binding", {**original["binding"], "exchange": "other"}),
            ("binding", {**original["binding"], "credential_fingerprint": "bad"}),
            ("binding", {**original["binding"], "unrecognized": True}),
        ]
        for field, value in changes:
            with self.subTest(field=field, value=value):
                payload = copy.deepcopy(original)
                payload[field] = value
                self.path.write_text(json.dumps(payload))
                before = self.path.read_bytes()
                self.assert_storage_blocked()
                self.assertEqual(before, self.path.read_bytes())

    def legacy_payload(self):
        records = {state: {"client_order_id": state, "state": state, "symbol": "BTCUSDT", "custom": {"preserve": True}}
                   for state in ("pending", "submitted", "unknown", "accepted", "rejected")}
        payload = {"format_version": 1, "intents": records}
        self.path.write_text(json.dumps(payload))
        return payload

    def test_legacy_migration_requires_explicit_action_preserves_backup_and_never_resolves_orders(self):
        old = self.legacy_payload()
        self.assert_storage_blocked(message="explicit migration")
        with self.assertRaises(LiveTradingSafetyError):
            provisioning.provision_order_intent_store(self.owner, acknowledgement="", migrate=True)
        result = self.initialize(migrate=True)
        current = ledger._read_ledger(self.path, expected_binding=ledger._intent_binding(self.owner))
        self.assertEqual(old["intents"], current["intents"])
        self.assertEqual(old, json.loads(Path(result["backup_path"]).read_text()))
        self.assertEqual(3, ledger.get_order_intent_status(self.owner)["unresolved_count"])
        with self.assertRaisesRegex(LiveTradingSafetyError, "Unresolved exchange order intent"):
            self.begin()
        with self.assertRaisesRegex(LiveTradingSafetyError, "already has state accepted"):
            self.begin(identifier="accepted")

    def test_migration_refuses_missing_corrupt_or_already_bound_store(self):
        with self.assertRaisesRegex(LiveTradingSafetyError, "ledger is missing"):
            self.initialize(migrate=True)
        self.path.write_text('{"format_version":1,"intents":{"bad":{"state":"unknown"}}}')
        before = self.path.read_bytes()
        with self.assertRaisesRegex(LiveTradingSafetyError, "invalid record"):
            self.initialize(migrate=True)
        self.assertEqual(before, self.path.read_bytes())
        self.path.unlink()
        self.initialize()
        before = self.path.read_bytes()
        with self.assertRaisesRegex(LiveTradingSafetyError, "Only a legacy"):
            self.initialize(migrate=True)
        self.assertEqual(before, self.path.read_bytes())

    def test_backup_or_migration_write_failure_does_not_erase_legacy_history(self):
        for failing_write in (1, 2):
            with self.subTest(failing_write=failing_write):
                old = self.legacy_payload()
                publish = store._publish
                writes = []

                def fail_selected(*args):
                    writes.append(args)
                    if len(writes) == failing_write:
                        raise OSError(errno.ENOSPC, "simulated disk full")
                    publish(*args)

                with patch.object(store, "_publish", side_effect=fail_selected):
                    with self.assertRaises(LiveTradingSafetyError):
                        self.initialize(migrate=True)
                self.assertEqual(old, json.loads(self.path.read_text()))
                self.assert_storage_blocked(message="explicit migration")
                self.assertEqual([], list(self.directory.glob("*.tmp")))

    def test_uncertain_migration_publish_preserves_history_and_block_on_restart(self):
        old = self.legacy_payload()
        publish = store._publish

        def uncertain(temp_path, path):
            publish(temp_path, path)
            if path == self.path:
                raise OSError(errno.EIO, "publication completion unknown")

        with patch.object(store, "_publish", side_effect=uncertain):
            with self.assertRaises(LiveTradingSafetyError):
                self.initialize(migrate=True)
        restarted = _owner(self.directory)
        self.assertEqual(old["intents"], ledger._read_ledger(self.path)["intents"])
        self.assertEqual(3, ledger.get_order_intent_status(restarted)["unresolved_count"])
        with self.assertRaisesRegex(LiveTradingSafetyError, "Unresolved exchange order intent"):
            self.begin(restarted)

    def test_initialize_write_failure_leaves_no_usable_empty_store(self):
        with patch.object(store, "_publish", side_effect=OSError(errno.ENOSPC, "simulated disk full")):
            with self.assertRaises(LiveTradingSafetyError):
                self.initialize()
        self.assertFalse(self.path.exists())
        self.assert_storage_blocked(message="ledger is missing")

    def test_symlink_store_is_never_followed_or_overwritten(self):
        target = self.directory / "target.json"
        target.write_text("unrelated contents")
        try:
            self.path.symlink_to(target)
        except OSError as exc:
            self.skipTest(f"Symlink creation unavailable: {exc}")
        for action in (lambda: self.initialize(), lambda: self.initialize(migrate=True), lambda: self.begin()):
            with self.assertRaisesRegex(LiveTradingSafetyError, "symbolic link"):
                action()
        self.assertEqual("unrelated contents", target.read_text())

    def test_symlink_detection_blocks_before_storage_access_on_all_hosts(self):
        with patch.object(Path, "is_symlink", return_value=True), patch.object(ledger, "ledger_transaction") as transaction:
            for operation in (lambda: self.initialize(), lambda: self.initialize(migrate=True), lambda: self.begin()):
                with self.assertRaisesRegex(LiveTradingSafetyError, "symbolic link"):
                    operation()
            transaction.assert_not_called()
        self.assertFalse(self.path.exists())

    def test_only_one_process_can_initialize_the_same_store(self):
        context = multiprocessing.get_context("spawn")
        barrier, results = context.Barrier(2), context.Queue()
        processes = [context.Process(target=_initialize_race, args=(str(self.directory), barrier, results)) for _ in range(2)]
        try:
            for process in processes:
                process.start()
            outcomes = [results.get(timeout=40) for _ in processes]
            for process in processes:
                process.join(timeout=10)
                self.assertEqual(0, process.exitcode)
            self.assertEqual(1, outcomes.count("initialized"), outcomes)
            self.assertTrue(any("already exists" in outcome for outcome in outcomes), outcomes)
            self.assertTrue(ledger.get_order_intent_status(self.owner)["storage_ready"])
        finally:
            for process in processes:
                if process.is_alive():
                    process.terminate()
                if process.pid:
                    process.join(timeout=10)
            results.close()

    def test_connector_and_service_health_expose_storage_failure_and_redact_error(self):
        self.owner.api_secret = "offline-secret"
        self.owner.get_order_intent_status = lambda: ledger.get_order_intent_status(self.owner)
        snapshot = get_connector_health_snapshot(self.owner)
        self.assertEqual("error", snapshot["health"])
        self.assertEqual("order_intent_storage_unavailable", snapshot["state"])
        self.assertFalse(snapshot["order_intents"]["storage_ready"])
        self.owner.get_order_intent_status = Mock(side_effect=LiveTradingSafetyError("api_secret=private-value"))
        snapshot = get_connector_health_snapshot(self.owner)
        self.assertNotIn("private-value", repr(snapshot))
        snapshot.update(health="ok", state="ready")
        canonical = build_exchange_connector_snapshot(
            config={"selected_exchange": "Binance", "connector_backend": "sdk"}, snapshot=snapshot, source="unit-test",
        )
        self.assertEqual("error", canonical["health"])
        self.assertEqual("order_intent_storage_unavailable", canonical["state"])
        self.assertTrue(canonical["attention"])
        self.assertNotIn("private-value", repr(canonical))

    def cli(self, action, *extras, default_path=False):
        paths = ["--default-intent-path"] if default_path else ["--audit-log-path", str(self.owner._order_audit_log_path)]
        args = [action, *paths, "--mode", "Live", "--api-key-env", "UNIT_STORE_API_KEY", *extras]
        with patch.dict(os.environ, {"UNIT_STORE_API_KEY": KEY}), contextlib.redirect_stdout(io.StringIO()) as output:
            code = admin.main(args)
        self.assertNotIn(KEY, output.getvalue())
        return code, json.loads(output.getvalue())

    def test_admin_cli_requires_operator_ack_and_reports_machine_readable_status(self):
        self.assertEqual(1, self.cli("status")[0])
        self.assertEqual(1, self.cli("initialize")[0])
        self.assertFalse(self.path.exists())
        self.assertEqual(0, self.cli("initialize", "--acknowledgement", ACK)[0])
        code, status = self.cli("status")
        self.assertEqual(0, code)
        self.assertTrue(status["storage_ready"])
        self.assertEqual(str(self.path), status["path"])
        self.assertEqual(1, self.cli("initialize", "--acknowledgement", ACK)[0])

    def test_admin_cli_supports_legacy_migration_and_explicit_default_path(self):
        self.legacy_payload()
        code, result = self.cli("migrate", "--acknowledgement", ACK)
        self.assertEqual(0, code)
        self.assertTrue(Path(result["backup_path"]).exists())
        with patch.object(Path, "home", return_value=self.directory):
            code, result = self.cli("initialize", "--acknowledgement", ACK, default_path=True)
        self.assertEqual(0, code)
        self.assertEqual(self.directory / ".trading-bot" / "order_intents.json", Path(result["path"]))

    def test_admin_cli_missing_credential_env_fails_without_writing_storage(self):
        with contextlib.redirect_stdout(io.StringIO()) as output:
            code = admin.main(["initialize", "--audit-log-path", str(self.owner._order_audit_log_path),
                               "--mode", "Live", "--api-key-env", "ABSENT_UNIT_KEY", "--acknowledgement", ACK])
        self.assertEqual(1, code)
        self.assertFalse(json.loads(output.getvalue())["ok"])
        self.assertFalse(self.path.exists())

    def test_admin_is_packaged_and_module_and_source_entrypoints_share_behavior(self):
        try:
            import tomllib
        except ModuleNotFoundError:
            import tomli as tomllib

        metadata = tomllib.loads((PYTHON_ROOT / "pyproject.toml").read_text())
        self.assertEqual("app.integrations.exchanges.binance.orders.order_intent_admin:main",
                         metadata["project"]["scripts"]["trading-bot-order-store"])
        self.assertEqual(0, self.cli("initialize", "--acknowledgement", ACK)[0])
        args = ["status", "--audit-log-path", str(self.owner._order_audit_log_path),
                "--mode", "Live", "--api-key-env", "UNIT_STORE_API_KEY"]
        for entry in (["-m", admin.__name__], [str(ROOT / "tools" / "manage_order_intent_store.py")]):
            with self.subTest(entry=entry):
                result = subprocess.run([sys.executable, *entry, *args], cwd=PYTHON_ROOT,
                                        env={**os.environ, "UNIT_STORE_API_KEY": KEY},
                                        text=True, capture_output=True, timeout=30)
                self.assertEqual(0, result.returncode, result.stderr)
                self.assertTrue(json.loads(result.stdout)["storage_ready"])
                self.assertNotIn(KEY, result.stdout + result.stderr)


if __name__ == "__main__":
    unittest.main()
