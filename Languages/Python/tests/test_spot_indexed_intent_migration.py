"""Offline cutover, source conservation and interruption proof for indexed migration."""
from __future__ import annotations

import hashlib
import json
import multiprocessing
import os
import socket
import tempfile
import unittest
from contextlib import redirect_stdout
from copy import deepcopy
from io import StringIO
from pathlib import Path
from unittest.mock import patch

from app.integrations.exchanges.binance.orders import order_intent_admin as admin_cli
from app.integrations.exchanges.binance.orders import order_intent_runtime as runtime
from app.integrations.exchanges.binance.orders import order_intent_store as locks
from app.integrations.exchanges.binance.orders import spot_execution_owner as ownership
from app.integrations.exchanges.binance.orders import spot_indexed_intent_migration as migration
from app.integrations.exchanges.binance.orders import spot_indexed_intent_store as indexed
from app.integrations.exchanges.binance.orders.spot_indexed_intent_bridge import indexed_intent_rules
from app.integrations.exchanges.binance.orders.order_intent_provisioning import (
    PROVISION_ACK, provision_order_intent_store, rotate_spot_owner_credentials,
)
from app.settings.live_safety import LiveTradingSafetyError
from tools import benchmark_spot_intent_history as fixtures
from tools import spot_intent_capacity_profiles as profiles

REFERENCE = "synthetic-indexed-migration-proof"


def _killable_migration(home, ready, release):
    original = migration._publish
    def pause_publication(temp, path):
        ready.set()
        if not release.wait(timeout=30):
            raise RuntimeError("Synthetic cutover barrier timed out")
        return original(temp, path)
    with patch.object(Path, "home", return_value=Path(home)), patch.object(migration, "_publish", side_effect=pause_publication):
        migration.migrate_spot_indexed_intent_store(
            fixtures.synthetic_owner(), acknowledgement=PROVISION_ACK, reconciliation_reference=REFERENCE,
        )


class SpotIndexedIntentMigrationTests(unittest.TestCase):
    def setUp(self):
        self.home = Path(self.enterContext(tempfile.TemporaryDirectory(prefix="trading-bot-indexed-migration-"))).resolve()
        self.enterContext(patch.object(Path, "home", return_value=self.home))
        self.enterContext(patch.object(socket.socket, "connect", side_effect=AssertionError("No network")))
        self.enterContext(patch.object(socket, "create_connection", side_effect=AssertionError("No network")))
        self.owner = fixtures.synthetic_owner()
        self.path = runtime._intent_path(self.owner)
        provision_order_intent_store(self.owner, acknowledgement=PROVISION_ACK)
        self.payload = fixtures.synthetic_payload(6, 2)
        self.payload["store_id"] = json.loads(self.path.read_bytes())["store_id"]
        self.payload["intents"], _ = profiles.synthetic_opo_records(
            6, original_stops=1, residual_stops=1, attempt_depth=3, residual_depth=3,
        )
        self.payload["preserved_extension"] = {"history": ["synthetic-original", {"count": 2}]}
        self.path.write_bytes((json.dumps(self.payload, separators=(", ", ": "), ensure_ascii=False) + "\r\n").encode())
        self.source = self.path.read_bytes()
        self.marker_before = json.loads(ownership.owner_marker_path(self.path).read_bytes())
        self.fence = locks.indexed_migration_fence_path(self.path)

    def migrate(self, owner=None, **kwargs):
        return migration.migrate_spot_indexed_intent_store(
            owner or self.owner, acknowledgement=kwargs.pop("acknowledgement", PROVISION_ACK),
            reconciliation_reference=kwargs.pop("reconciliation_reference", REFERENCE), **kwargs,
        )

    def marker(self):
        return ownership._read_marker(
            ownership.owner_marker_path(self.path), uid=fixtures.SYNTHETIC_UID,
            environment="live", store_id=self.payload["store_id"],
        )

    def read(self):
        with locks.ledger_transaction(self.path):
            return runtime._read_ledger(self.path, expected_binding=self.payload["binding"])

    def interrupt_after_database(self):
        original = migration._prepare_database
        def interrupted(*args, **kwargs):
            original(*args, **kwargs)
            raise RuntimeError("Synthetic interrupted import")
        with patch.object(migration, "_prepare_database", side_effect=interrupted), self.assertRaisesRegex(RuntimeError, "Synthetic"):
            self.migrate()
        return migration.read_indexed_migration_receipt(self.path)

    def assert_disarmed(self):
        marker = self.marker()
        self.assertEqual("recovery_required", marker["state"])
        self.assertEqual(self.marker_before["generation"] + 1, marker["generation"])
        self.assertEqual(REFERENCE, marker["reconciliation_reference"])

    def test_byte_exact_backup_full_history_binding_store_and_projection_conservation(self):
        result = self.migrate()
        receipt = migration.read_indexed_migration_receipt(self.path)
        self.assertEqual(3, result["format_version"])
        self.assertFalse(result["resumed"])
        self.assertTrue(result["requires_rearm"])
        self.assertEqual(self.source, Path(result["backup_path"]).read_bytes())
        self.assertEqual(hashlib.sha256(self.source).hexdigest(), receipt.manifest.source_sha256)
        self.assertEqual(self.payload, self.read())
        snapshot = self.read().indexed_snapshot
        expected = {(identifier, key) for key, row in self.payload["intents"].items()
                    for identifier in runtime.used_spot_client_order_ids({key: row}) | {key}}
        self.assertEqual(expected, set(snapshot.reserved_owners))
        self.assertEqual(tuple(sorted(key for key, row in self.payload["intents"].items()
                                      if runtime._has_active_spot_protection(row))), snapshot.active_ids)
        self.assertEqual(tuple(sorted(key for key, row in self.payload["intents"].items()
                                      if runtime._is_unresolved(row))), snapshot.unresolved_ids)
        self.assert_disarmed()
        self.assertNotEqual(self.source, self.path.read_bytes())

    def test_completed_retry_is_read_only_and_does_not_increment_generation(self):
        result = self.migrate()
        outputs = (self.path, self.fence, Path(result["backup_path"]), Path(result["database_path"]),
                   ownership.owner_marker_path(self.path))
        before = {path: path.read_bytes() for path in outputs}
        retry = self.migrate()
        self.assertTrue(retry["resumed"])
        self.assertEqual(before, {path: path.read_bytes() for path in outputs})
        self.assert_disarmed()

    def test_interruption_boundaries_preserve_source_and_resume_exactly_once(self):
        for boundary in ("before-backup", "after-backup", "after-database", "before-disarm", "after-disarm",
                         "before-pointer", "after-pointer"):
            with self.subTest(boundary=boundary):
                # Each case starts from a complete isolated synthetic account.
                with tempfile.TemporaryDirectory(prefix="trading-bot-indexed-migration-boundary-") as folder:
                    with patch.object(Path, "home", return_value=Path(folder)):
                        owner = fixtures.synthetic_owner()
                        path = runtime._intent_path(owner)
                        provision_order_intent_store(owner, acknowledgement=PROVISION_ACK)
                        path.write_bytes(self.source)
                        marker_path = ownership.owner_marker_path(path)
                        marker = json.loads(marker_path.read_bytes())
                        marker["store_id"] = self.payload["store_id"]
                        marker_path.write_text(json.dumps(marker))
                        original_write, original_db = migration._write_exclusive, migration._prepare_database
                        original_disarm, original_publish = migration.mark_owner_recovery_required_locked, migration._publish
                        def fail_write(target, raw):
                            if target.suffix == ".backup" and boundary == "before-backup":
                                raise RuntimeError("Synthetic boundary")
                            original_write(target, raw)
                            if target.suffix == ".backup" and boundary == "after-backup":
                                raise RuntimeError("Synthetic boundary")
                        def fail_db(*args, **kwargs):
                            value = original_db(*args, **kwargs)
                            if boundary == "after-database":
                                raise RuntimeError("Synthetic boundary")
                            return value
                        def fail_disarm(*args, **kwargs):
                            if boundary == "before-disarm":
                                raise RuntimeError("Synthetic boundary")
                            value = original_disarm(*args, **kwargs)
                            if boundary == "after-disarm":
                                raise RuntimeError("Synthetic boundary")
                            return value
                        def fail_publish(*args):
                            if boundary == "before-pointer":
                                raise RuntimeError("Synthetic boundary")
                            value = original_publish(*args)
                            if boundary == "after-pointer":
                                raise RuntimeError("Synthetic boundary")
                            return value
                        with patch.object(migration, "_write_exclusive", side_effect=fail_write), \
                                patch.object(migration, "_prepare_database", side_effect=fail_db), \
                                patch.object(migration, "mark_owner_recovery_required_locked", side_effect=fail_disarm), \
                                patch.object(migration, "_publish", side_effect=fail_publish), self.assertRaisesRegex(RuntimeError, "Synthetic"):
                            self.migrate(owner)
                        if boundary != "after-pointer":
                            self.assertEqual(self.source, path.read_bytes())
                            with locks.ledger_transaction(path), self.assertRaises(LiveTradingSafetyError):
                                runtime._read_ledger(path)
                            with locks.ledger_transaction(path), self.assertRaises(LiveTradingSafetyError):
                                locks.write_ledger(path, deepcopy(self.payload))
                        retry = self.migrate(owner)
                        self.assertTrue(retry["resumed"])
                        marker = ownership._read_marker(ownership.owner_marker_path(path), uid=fixtures.SYNTHETIC_UID,
                                                        environment="live", store_id=self.payload["store_id"])
                        self.assertEqual(1, marker["generation"])
                        self.assertEqual("recovery_required", marker["state"])

    def test_killed_process_before_pointer_keeps_source_and_resumes_verified_import(self):
        context = multiprocessing.get_context("spawn")
        ready, release = context.Event(), context.Event()
        process = context.Process(target=_killable_migration, args=(str(self.home), ready, release))
        process.start()
        try:
            self.assertTrue(ready.wait(timeout=15), "Synthetic migration did not reach the durable prepublication barrier")
            self.assertEqual(self.source, self.path.read_bytes())
            self.assert_disarmed()
            process.terminate()
            process.join(timeout=10)
            self.assertFalse(process.is_alive())
            self.assertNotEqual(0, process.exitcode)
            result = self.migrate()
            self.assertTrue(result["resumed"])
            self.assertEqual(self.payload, self.read())
            self.assert_disarmed()
        finally:
            # A process killed during Event.wait may abandon its condition lock.
            # Do not reacquire that synchronization object after termination.
            if process.is_alive():
                process.terminate()
                process.join(timeout=10)

    def test_active_owner_is_excluded_before_any_migration_output(self):
        class WeakOwner:
            pass
        weak_owner = WeakOwner()
        execution_owner = ownership.claim_execution_owner(
            self.path, uid=fixtures.SYNTHETIC_UID, environment="live", store_id=self.payload["store_id"],
            credential_fingerprint=self.payload["binding"]["credential_fingerprint"], owner_wrapper=weak_owner,
        )
        try:
            with self.assertRaisesRegex(LiveTradingSafetyError, "active"):
                self.migrate()
            self.assertFalse(self.fence.exists())
            self.assertEqual(self.source, self.path.read_bytes())
        finally:
            execution_owner.close()

    def test_wrong_scope_binding_acknowledgement_or_missing_owner_creates_no_receipt(self):
        for fault in ("futures", "testnet", "different-key", "bad-ack", "no-owner"):
            with self.subTest(fault=fault):
                owner = deepcopy(self.owner)
                args = {}
                marker = ownership.owner_marker_path(self.path)
                saved = marker.read_bytes()
                if fault == "futures":
                    owner.account_type = "FUTURES"
                elif fault == "testnet":
                    owner.mode = "Demo/Testnet"
                elif fault == "different-key":
                    owner.api_key = "different-synthetic-key"
                elif fault == "bad-ack":
                    args["acknowledgement"] = "unattested"
                else:
                    marker.unlink()
                try:
                    with self.assertRaises(LiveTradingSafetyError):
                        self.migrate(owner, **args)
                    self.assertFalse(self.fence.exists())
                    self.assertEqual(self.source, self.path.read_bytes())
                finally:
                    marker.write_bytes(saved)

    def test_resume_rejects_changed_source_even_when_rewritten_bytes_are_identical(self):
        receipt = self.interrupt_after_database()
        replacement = self.path.with_name("rewritten-source.json")
        replacement.write_bytes(self.source)
        os.replace(replacement, self.path)
        before = self.path.read_bytes()
        with self.assertRaisesRegex(LiveTradingSafetyError, "source differs"):
            self.migrate()
        self.assertEqual(before, self.path.read_bytes())
        self.assertEqual(self.marker_before, self.marker())
        self.assertEqual(receipt, migration.read_indexed_migration_receipt(self.path))

    def test_resume_rejects_changed_backup_and_never_overwrites_it(self):
        receipt = self.interrupt_after_database()
        backup = self.path.parent / receipt.manifest.source_backup
        backup.write_bytes(self.source + b" ")
        with self.assertRaisesRegex(LiveTradingSafetyError, "backup changed"):
            self.migrate()
        self.assertEqual(self.source + b" ", backup.read_bytes())
        self.assertEqual(self.source, self.path.read_bytes())

    def test_resume_rejects_corrupt_existing_database_and_never_resets_it(self):
        receipt = self.interrupt_after_database()
        database = self.path.parent / receipt.manifest.database
        database.write_bytes(b"synthetic-incomplete-database")
        with self.assertRaises(LiveTradingSafetyError):
            self.migrate()
        self.assertEqual(b"synthetic-incomplete-database", database.read_bytes())
        self.assertEqual(self.source, self.path.read_bytes())

    def test_resume_rejects_valid_but_different_imported_payload(self):
        receipt = self.interrupt_after_database()
        database = self.path.parent / receipt.manifest.database
        with locks.ledger_transaction(self.path):
            snapshot = indexed.read_indexed_snapshot(
                database, logical_path=self.path, rules=indexed_intent_rules(), expected_binding=self.payload["binding"],
                deadline=locks.current_ledger_deadline(self.path),
            )
            candidate = snapshot.payload
            candidate["unexpected_import_annotation"] = "synthetic mutation"
            indexed.replace_indexed_snapshot(
                database, candidate, expected=snapshot, rules=indexed_intent_rules(),
                expected_binding=self.payload["binding"], deadline=locks.current_ledger_deadline(self.path),
            )
        before = database.read_bytes()
        with self.assertRaises(LiveTradingSafetyError):
            self.migrate()
        self.assertEqual(before, database.read_bytes())
        self.assertEqual(self.source, self.path.read_bytes())

    def test_resume_rejects_changed_reference_or_owner_generation(self):
        self.interrupt_after_database()
        with self.assertRaisesRegex(LiveTradingSafetyError, "reference changed"):
            self.migrate(reconciliation_reference="different-reference")
        marker_path = ownership.owner_marker_path(self.path)
        saved = marker_path.read_bytes()
        for change in ({"generation": 9}, {"state": "recovery_required", "generation": 1,
                                          "reconciliation_reference": "different-reference"},
                       {"state": "armed", "generation": 1}):
            with self.subTest(change=change):
                marker = json.loads(saved)
                marker.update(change)
                marker_path.write_text(json.dumps(marker))
                with self.assertRaisesRegex(LiveTradingSafetyError, "owner changed"):
                    self.migrate()
                self.assertEqual(self.source, self.path.read_bytes())
        marker_path.write_bytes(saved)

    def test_completed_retry_rejects_later_database_update_or_rearm(self):
        self.migrate()
        ledger = self.read()
        ledger["post_migration_annotation"] = "retained"
        with locks.ledger_transaction(self.path):
            locks.write_ledger(self.path, ledger)
        with self.assertRaisesRegex(LiveTradingSafetyError, "history differs"):
            self.migrate()
        self.assertEqual("retained", self.read()["post_migration_annotation"])

    def test_completed_retry_never_recreates_a_missing_established_database(self):
        result = self.migrate()
        database = Path(result["database_path"])
        database.unlink()
        pointer, backup, fence = self.path.read_bytes(), Path(result["backup_path"]).read_bytes(), self.fence.read_bytes()
        with patch.object(migration, "create_indexed_store") as create, \
                self.assertRaisesRegex(LiveTradingSafetyError, "published database is missing"):
            self.migrate()
        create.assert_not_called()
        self.assertFalse(database.exists())
        self.assertEqual(pointer, self.path.read_bytes())
        self.assertEqual(backup, Path(result["backup_path"]).read_bytes())
        self.assertEqual(fence, self.fence.read_bytes())
        self.assert_disarmed()

    def test_completed_retry_rejects_later_owner_rearm(self):
        self.migrate()
        ownership.rearm_owner_marker(
            self.path, uid=fixtures.SYNTHETIC_UID, environment="live", store_id=self.payload["store_id"],
            acknowledgement=PROVISION_ACK, reconciliation_reference="synthetic-later-rearm",
        )
        before = self.path.read_bytes()
        with self.assertRaisesRegex(LiveTradingSafetyError, "owner changed"):
            self.migrate()
        self.assertEqual(before, self.path.read_bytes())
        self.assertEqual("armed", self.marker()["state"])

    def test_source_identity_is_rechecked_after_owner_invalidation_before_pointer(self):
        original = migration.mark_owner_recovery_required_locked
        def mutate_after_disarm(*args, **kwargs):
            result = original(*args, **kwargs)
            replacement = self.path.with_name("synthetic-source-replacement")
            replacement.write_bytes(self.source)
            os.replace(replacement, self.path)
            return result
        with patch.object(migration, "mark_owner_recovery_required_locked", side_effect=mutate_after_disarm), \
                patch.object(migration, "_publish") as publish, self.assertRaisesRegex(LiveTradingSafetyError, "source changed"):
            self.migrate()
        publish.assert_not_called()
        self.assertEqual(self.source, self.path.read_bytes())
        self.assert_disarmed()
        with locks.ledger_transaction(self.path), self.assertRaises(LiveTradingSafetyError):
            runtime._read_ledger(self.path)

    def test_receipt_is_strict_immutable_confined_and_pins_original_stat(self):
        self.migrate()
        receipt = migration.read_indexed_migration_receipt(self.path)
        self.assertEqual(receipt, migration.assert_indexed_migration_manifest(self.path, receipt.manifest))
        original = self.fence.read_bytes()
        for fault in ("duplicate", "extra", "bad-identity", "bad-generation", "bad-binding", "bad-path", "bad-state"):
            with self.subTest(fault=fault):
                value = json.loads(original)
                if fault == "duplicate":
                    raw = original.replace(b'{', b'{"format_version":1,', 1)
                else:
                    if fault == "extra":
                        value["extra"] = True
                    elif fault == "bad-identity":
                        value["source_identity"][0] = True
                    elif fault == "bad-generation":
                        value["target_generation"] = True
                    elif fault == "bad-binding":
                        value["binding"]["credential_fingerprint"] = "invalid"
                    elif fault == "bad-path":
                        value["logical_path"] = str(self.path.with_name("other.json"))
                    else:
                        value["owner_before"]["state"] = []
                    raw = json.dumps(value).encode()
                self.fence.write_bytes(raw)
                with self.assertRaises(LiveTradingSafetyError):
                    migration.read_indexed_migration_receipt(self.path)
                self.fence.write_bytes(original)
        with self.assertRaisesRegex(LiveTradingSafetyError, "receipt changed"):
            receipt.assert_current(self.path)

    def test_migration_requires_original_utf8_decoder_contract_before_any_receipt(self):
        text = self.source.decode("utf-8")
        for raw in (text.encode("utf-16"), text.encode("utf-32"), b"\xef\xbb\xbf" + self.source,
                    b'{"format_version":2,"format_version":2}'):
            with self.subTest(prefix=raw[:4]):
                self.path.write_bytes(raw)
                with self.assertRaises(LiveTradingSafetyError):
                    self.migrate()
                self.assertFalse(self.fence.exists())
                self.assertEqual(raw, self.path.read_bytes())
        self.path.write_bytes(self.source)

    def test_hardlinked_source_and_unrecorded_database_outputs_fail_before_receipt(self):
        link = self.path.with_name("source-hardlink")
        os.link(self.path, link)
        try:
            with self.assertRaises(LiveTradingSafetyError):
                self.migrate()
            self.assertFalse(self.fence.exists())
        finally:
            link.unlink()
        orphan = self.path.with_name(self.path.name + ".orphan.sqlite3")
        orphan.write_bytes(b"unrecorded")
        with self.assertRaisesRegex(LiveTradingSafetyError, "unrecorded"):
            self.migrate()
        self.assertFalse(self.fence.exists())
        self.assertEqual(b"unrecorded", orphan.read_bytes())

    def test_actual_cli_migrates_selected_live_spot_without_secret_or_transport(self):
        output = StringIO()
        with patch.dict(os.environ, {"SYNTHETIC_KEY": fixtures.SYNTHETIC_KEY, "SYNTHETIC_UID": str(fixtures.SYNTHETIC_UID)}), redirect_stdout(output):
            result = admin_cli.main([
                "migrate-spot-indexed", "--mode", "Live", "--account-type", "Spot",
                "--api-key-env", "SYNTHETIC_KEY", "--spot-account-uid-env", "SYNTHETIC_UID",
                "--acknowledgement", PROVISION_ACK, "--reconciliation-reference", REFERENCE,
            ])
        self.assertEqual(0, result)
        self.assertTrue(json.loads(output.getvalue())["requires_rearm"])
        self.assertEqual(self.payload, self.read())

    def test_cli_rejects_futures_indexed_migration(self):
        with redirect_stdout(StringIO()), self.assertRaises(SystemExit) as error:
            admin_cli.main(["migrate-spot-indexed", "--mode", "Live", "--account-type", "Futures",
                            "--api-key-env", "SYNTHETIC_KEY", "--default-intent-path"])
        self.assertEqual(2, error.exception.code)
        self.assertFalse(self.fence.exists())

    def test_direct_credential_rotation_preserves_manifest_and_all_prior_database_history(self):
        self.payload["intents"] = {}
        self.path.write_text(json.dumps(self.payload))
        self.source = self.path.read_bytes()
        result = self.migrate()
        pointer, fence = self.path.read_bytes(), self.fence.read_bytes()
        owner = deepcopy(self.owner)
        owner.api_key = "distinct-synthetic-rotation-key"
        rotated = rotate_spot_owner_credentials(
            owner, acknowledgement=PROVISION_ACK, reconciliation_reference="synthetic-key-rotation",
        )
        self.assertTrue(rotated["requires_rearm"])
        self.assertEqual(pointer, self.path.read_bytes())
        self.assertEqual(fence, self.fence.read_bytes())
        self.assertEqual(self.source, Path(result["backup_path"]).read_bytes())
        with locks.ledger_transaction(self.path):
            ledger = runtime._read_ledger(self.path, expected_binding=runtime._intent_binding(owner))
        self.assertEqual(2, ledger.indexed_snapshot.receipt.revision)
        self.assertEqual(self.payload["store_id"], ledger["store_id"])
        self.assertEqual(self.payload["binding"]["credential_fingerprint"],
                         ledger["credential_rotation_history"][0]["previous_fingerprint"])
        self.assertEqual(2, self.marker()["generation"])


if __name__ == "__main__":
    unittest.main()
