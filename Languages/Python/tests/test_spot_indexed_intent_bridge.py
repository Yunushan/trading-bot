"""Real full-ledger routing preserves immutable cutover receipts and CAS sources."""
from __future__ import annotations

from copy import deepcopy
import json
import os
from pathlib import Path
import socket
import tempfile
import unittest
from unittest.mock import patch

from app.integrations.exchanges.binance.orders import order_intent_runtime as runtime
from app.integrations.exchanges.binance.orders import order_intent_store as locks
from app.integrations.exchanges.binance.orders import order_intent_provisioning as provisioning
from app.integrations.exchanges.binance.orders import spot_execution_owner as owners
from app.integrations.exchanges.binance.orders import spot_indexed_intent_bridge as bridge
from app.integrations.exchanges.binance.orders import spot_indexed_intent_migration as migration
from app.integrations.exchanges.binance.orders import spot_indexed_intent_store as backend
from app.settings.live_safety import LiveTradingSafetyError
from tools import benchmark_spot_intent_history as fixtures


class SpotIndexedIntentBridgeTests(unittest.TestCase):
    def setUp(self):
        self.temporary = self.enterContext(tempfile.TemporaryDirectory(prefix='trading-bot-indexed-bridge-'))
        self.root = Path(self.temporary)
        self.enterContext(patch.object(Path, 'home', return_value=self.root))
        self.enterContext(patch.object(socket.socket, 'connect', side_effect=AssertionError('No network')))
        self.enterContext(patch.object(socket, 'create_connection', side_effect=AssertionError('No network')))
        self.owner = fixtures.synthetic_owner()
        self.path = runtime._intent_path(self.owner)
        self.payload = fixtures.synthetic_payload(6, 2)
        self.binding = deepcopy(self.payload['binding'])
        self.key = next(iter(self.payload['intents']))
        with owners.owner_administration_lock(self.path):
            with locks.ledger_transaction(self.path):
                locks.write_ledger(self.path, self.payload)
            owners.provision_owner_marker_locked(
                self.path, uid=fixtures.SYNTHETIC_UID, environment='live', store_id=self.payload['store_id'])
        result = migration.migrate_spot_indexed_intent_store(
            self.owner, acknowledgement=provisioning.PROVISION_ACK,
            reconciliation_reference='synthetic-bridge-migration')
        self.database = Path(result['database_path'])
        self.backup = Path(result['backup_path'])
        self.fence = locks.indexed_migration_fence_path(self.path)
        self.manifest_bytes = self.path.read_bytes()
        self.fence_bytes = self.fence.read_bytes()
        self.backup_bytes = self.backup.read_bytes()

    def read(self, **kwargs):
        with locks.ledger_transaction(self.path):
            return runtime._read_ledger(self.path, **kwargs)

    def write(self, payload, **kwargs):
        with locks.ledger_transaction(self.path):
            locks.write_ledger(self.path, payload, **kwargs)

    def replace_same_bytes(self, path):
        replacement = path.with_name(path.name + '.test-replacement')
        replacement.write_bytes(path.read_bytes())
        os.replace(replacement, path)

    def assert_namespace_unchanged(self):
        self.assertEqual(self.manifest_bytes, self.path.read_bytes())
        self.assertEqual(self.fence_bytes, self.fence.read_bytes())
        self.assertEqual(self.backup_bytes, self.backup.read_bytes())

    def test_real_read_returns_complete_detached_payload_and_original_frozen_authority(self):
        ledger = self.read(expected_binding=self.binding)
        self.assertIsInstance(ledger, bridge.FullIndexedLedgerPayload)
        self.assertEqual(self.payload, ledger)
        self.assertIs(ledger.indexed_snapshot, ledger.indexed_authority.snapshot)
        self.assertEqual(6, len(ledger['intents']))
        self.assertEqual(self.binding, ledger.indexed_authority.original_binding())
        with self.assertRaises(AttributeError):
            ledger.indexed_authority.binding = ('binance', 'live', 'f' * 64)
        ledger['intents'].clear()
        self.assertEqual(self.payload, ledger.indexed_snapshot.payload)
        self.assertEqual(self.payload, self.read())
        self.assert_namespace_unchanged()

    def test_runtime_record_get_update_and_full_record_cas_execute_indexed_storage(self):
        observed = runtime._get_order_intent_record(self.owner, self.key)
        self.assertEqual(self.payload['intents'][self.key], observed)
        updated = runtime._update_order_intent_by_id(
            self.owner, self.key, state='unknown', expected_record=observed,
            operator_annotation='synthetic complete record update')
        self.assertEqual('unknown', updated['state'])
        self.assertEqual(updated, runtime._get_order_intent_record(self.owner, self.key))
        before = self.database.read_bytes()
        self.assertIsNone(runtime._update_order_intent_by_id(
            self.owner, self.key, state='submitted', expected_record=observed))
        self.assertEqual(before, self.database.read_bytes())
        current = self.read()
        self.assertEqual(2, current.indexed_snapshot.receipt.revision)
        self.assertEqual(2, current.indexed_snapshot.record_receipt(self.key).revision)
        self.assert_namespace_unchanged()

    def test_generic_writer_routes_full_receipt_and_never_publishes_json_pointer(self):
        ledger = self.read()
        ledger['operator_annotation'] = {'reference': 'synthetic complete bridge'}
        with patch.object(locks, '_publish', side_effect=AssertionError('Must not publish pointer')):
            self.write(ledger)
        self.assertEqual(ledger, self.read(expected_binding=self.binding))
        self.assert_namespace_unchanged()

    def test_noop_preserves_database_and_namespace_bytes(self):
        ledger = self.read()
        before = self.database.read_bytes()
        self.write(ledger)
        self.assertEqual(before, self.database.read_bytes())
        self.assert_namespace_unchanged()

    def test_stale_full_head_cannot_overwrite_later_record_or_metadata(self):
        stale = self.read()
        # Both detached candidates retain the same actual verified read. A new
        # cold read seals a new backup checkpoint and tests that earlier fence.
        current = bridge.FullIndexedLedgerPayload(dict(stale), stale.indexed_authority)
        current['operator_annotation'] = 'first writer'
        self.write(current)
        with locks.ledger_transaction(self.path):
            committed = backend.read_indexed_snapshot(
                self.database, logical_path=self.path, rules=bridge.indexed_intent_rules(),
                expected_binding=self.binding, deadline=locks.current_ledger_deadline(self.path))
        self.assertEqual(stale.indexed_snapshot.receipt.revision + 1, committed.receipt.revision)
        self.assertNotEqual(stale.indexed_snapshot.receipt.head, committed.receipt.head)
        self.assertEqual('first writer', committed.payload['operator_annotation'])
        before = self.database.read_bytes()
        stale['operator_annotation'] = 'stale writer'
        with self.assertRaisesRegex(LiveTradingSafetyError, 'source changed'):
            self.write(stale)
        self.assertEqual(before, self.database.read_bytes())
        self.assertEqual('first writer', self.read()['operator_annotation'])
        self.assert_namespace_unchanged()

    def test_lost_manifest_authority_rejects_dict_json_and_backend_only_copies(self):
        ledger = self.read()
        for copied in (dict(ledger), json.loads(json.dumps(ledger)), ledger.indexed_snapshot.payload,
                       locks.IndexedLedgerWritePayload(ledger)):
            with self.subTest(copy_type=type(copied).__name__):
                before = self.database.read_bytes()
                with self.assertRaises(LiveTradingSafetyError):
                    self.write(copied)
                self.assertEqual(before, self.database.read_bytes())
                self.assert_namespace_unchanged()

    def test_both_reader_and_writer_require_actual_logical_lock(self):
        ledger = self.read()
        unrelated = self.root / 'unrelated.json'
        for operation in (lambda: runtime._read_ledger(self.path),
                          lambda: locks.write_ledger(self.path, ledger)):
            with self.subTest(operation=operation):
                with self.assertRaisesRegex(LiveTradingSafetyError, 'transaction is required'):
                    operation()
                with locks.ledger_transaction(unrelated):
                    with self.assertRaisesRegex(LiveTradingSafetyError, 'required.*lock'):
                        operation()
        self.assert_namespace_unchanged()

    def test_wrong_target_path_cannot_reuse_original_full_receipt(self):
        ledger = self.read()
        other = self.root / 'different.json'
        with locks.ledger_transaction(other), self.assertRaisesRegex(LiveTradingSafetyError, 'source path changed'):
            locks.write_ledger(other, ledger)
        self.assertFalse(other.exists())
        self.assert_namespace_unchanged()

    def test_manifest_same_bytes_replacement_rejects_original_authority(self):
        ledger = self.read()
        self.replace_same_bytes(self.path)
        before = self.database.read_bytes()
        with self.assertRaisesRegex(LiveTradingSafetyError, 'manifest changed'):
            self.write(ledger)
        self.assertEqual(before, self.database.read_bytes())

    def test_cutover_receipt_same_bytes_replacement_rejects_original_authority(self):
        ledger = self.read()
        self.replace_same_bytes(self.fence)
        before = self.database.read_bytes()
        with self.assertRaisesRegex(LiveTradingSafetyError, 'receipt changed'):
            self.write(ledger)
        self.assertEqual(before, self.database.read_bytes())

    def test_missing_manifest_or_database_fences_typed_and_plain_writes(self):
        for missing in ('manifest', 'database', 'receipt', 'backup'):
            with self.subTest(missing=missing):
                ledger = self.read()
                path = {'manifest': self.path, 'database': self.database, 'receipt': self.fence, 'backup': self.backup}[missing]
                raw = path.read_bytes()
                path.unlink()
                try:
                    with self.assertRaises(LiveTradingSafetyError):
                        self.read()
                    with self.assertRaises(LiveTradingSafetyError):
                        self.write(ledger)
                    with self.assertRaises(LiveTradingSafetyError):
                        self.write(dict(ledger))
                    self.assertFalse(path.exists())
                finally:
                    path.write_bytes(raw)

    def test_corrupt_duplicate_and_oversized_manifests_fail_closed(self):
        for corrupt in (b'{broken', b'{"format_version":3,"format_version":3}',
                        self.manifest_bytes + b' ' * 16384):
            with self.subTest(corrupt_size=len(corrupt)):
                ledger = self.read()
                before = self.database.read_bytes()
                self.path.write_bytes(corrupt)
                try:
                    with self.assertRaises(LiveTradingSafetyError):
                        self.read()
                    for candidate in (ledger, dict(ledger)):
                        with self.assertRaises(LiveTradingSafetyError):
                            self.write(candidate)
                    self.assertEqual(corrupt, self.path.read_bytes())
                    self.assertEqual(before, self.database.read_bytes())
                finally:
                    self.path.write_bytes(self.manifest_bytes)

    def test_corrupt_receipt_or_database_never_creates_fallback_or_resets_history(self):
        for target in (self.fence, self.database):
            with self.subTest(target=target.name):
                ledger = self.read()
                original = target.read_bytes()
                target.write_bytes(b'corrupt synthetic storage')
                try:
                    with self.assertRaises(LiveTradingSafetyError):
                        self.read()
                    for candidate in (ledger, dict(ledger)):
                        with self.assertRaises(LiveTradingSafetyError):
                            self.write(candidate)
                    self.assertEqual(b'corrupt synthetic storage', target.read_bytes())
                    self.assertEqual(self.manifest_bytes, self.path.read_bytes())
                finally:
                    target.write_bytes(original)

    def test_backup_digest_and_original_identity_are_required(self):
        ledger = self.read()
        self.backup.write_bytes(self.backup_bytes + b' ')
        before = self.database.read_bytes()
        with self.assertRaisesRegex(LiveTradingSafetyError, 'backup'):
            self.read()
        with self.assertRaisesRegex(LiveTradingSafetyError, 'backup'):
            self.write(ledger)
        self.assertEqual(before, self.database.read_bytes())
        self.backup.write_bytes(self.backup_bytes)
        fresh = self.read()
        self.replace_same_bytes(self.backup)
        with self.assertRaisesRegex(LiveTradingSafetyError, 'backup'):
            self.write(fresh)
        self.assertEqual(before, self.database.read_bytes())

    def test_cold_backup_read_rejects_coalesced_raw_edit_after_hashing(self):
        changed = self.backup_bytes.replace(b'synthetic-capacity-benchmark', b'synthetic-capacity-benchmarX', 1)
        self.assertNotEqual(self.backup_bytes, changed)
        self.assertEqual(len(self.backup_bytes), len(changed))
        original_stat = self.backup.stat()
        descriptor = os.open(self.backup, os.O_RDWR | getattr(os, 'O_BINARY', 0))
        original_read = os.read
        edited = False
        try:
            # Keep the raw writer open with an existing OVERWRITE reason. Cold
            # receipt issuance must seal that reason before the source is hashed.
            os.write(descriptor, self.backup_bytes)
            os.fsync(descriptor)
            os.utime(self.backup, ns=(original_stat.st_atime_ns, original_stat.st_mtime_ns))
            def read_then_edit(fd, size):
                nonlocal edited
                chunk = original_read(fd, size)
                info = os.fstat(fd)
                if (not chunk and not edited and fd != descriptor
                        and (info.st_dev, info.st_ino) == (original_stat.st_dev, original_stat.st_ino)):
                    edited = True
                    os.lseek(descriptor, 0, os.SEEK_SET)
                    os.write(descriptor, changed)
                    os.fsync(descriptor)
                    os.utime(self.backup, ns=(original_stat.st_atime_ns, original_stat.st_mtime_ns))
                return chunk
            with patch.object(bridge.os, 'read', side_effect=read_then_edit):
                with self.assertRaisesRegex(LiveTradingSafetyError, 'backup'):
                    self.read()
            self.assertTrue(edited)
            self.assertEqual(original_stat.st_mtime_ns, self.backup.stat().st_mtime_ns)
        finally:
            os.close(descriptor)

    def test_backup_same_length_change_with_restored_mtime_rejects_original_write(self):
        ledger = self.read()
        original_stat = self.backup.stat()
        changed = self.backup_bytes.replace(b'synthetic-capacity-benchmark', b'synthetic-capacity-benchmarX', 1)
        self.assertNotEqual(self.backup_bytes, changed)
        self.assertEqual(len(self.backup_bytes), len(changed))
        self.backup.write_bytes(changed)
        os.utime(self.backup, ns=(original_stat.st_atime_ns, original_stat.st_mtime_ns))
        self.assertEqual(original_stat.st_mtime_ns, self.backup.stat().st_mtime_ns)
        before = self.database.read_bytes()
        with self.assertRaisesRegex(LiveTradingSafetyError, 'backup'):
            self.write(ledger)
        with self.assertRaisesRegex(LiveTradingSafetyError, 'backup'):
            self.read()
        self.assertEqual(before, self.database.read_bytes())

    def test_complete_validator_and_history_preservation_still_reject_invalid_writes(self):
        for invalid in ('state', 'delete-record', 'binding', 'request'):
            with self.subTest(invalid=invalid):
                ledger = self.read()
                if invalid == 'state':
                    ledger['intents'][self.key]['state'] = 'invented'
                elif invalid == 'delete-record':
                    del ledger['intents'][self.key]
                elif invalid == 'binding':
                    ledger['binding']['credential_fingerprint'] = 'b' * 64
                else:
                    ledger['intents'][self.key]['symbol'] = 'ETHUSDT'
                before = self.database.read_bytes()
                with self.assertRaises(LiveTradingSafetyError):
                    self.write(ledger)
                self.assertEqual(before, self.database.read_bytes())
                self.assert_namespace_unchanged()

    def test_explicit_generic_metadata_rotation_preserves_full_intents_and_namespace(self):
        ledger = self.read()
        new_binding = {**self.binding, 'credential_fingerprint': 'b' * 64}
        ledger['binding'] = new_binding
        ledger['credential_rotation_history'] = [{
            'previous_fingerprint': self.binding['credential_fingerprint'],
            'new_fingerprint': new_binding['credential_fingerprint'],
            'rotated_at': fixtures.FIXED_TIME, 'reconciliation_reference': 'synthetic explicit rotation',
        }]
        before = self.database.read_bytes()
        with self.assertRaisesRegex(LiveTradingSafetyError, 'different credentials'):
            self.write(ledger)
        self.assertEqual(before, self.database.read_bytes())
        self.write(ledger, expected_new_binding=new_binding)
        current = self.read(expected_binding=new_binding)
        self.assertEqual(self.payload['intents'], current['intents'])
        self.assertEqual(2, current.indexed_snapshot.receipt.revision)
        with self.assertRaisesRegex(LiveTradingSafetyError, 'different credentials'):
            self.read(expected_binding=self.binding)
        self.assert_namespace_unchanged()

    def test_actual_offline_rotation_uses_generic_indexed_writer_and_remains_disarmed(self):
        # Settle the synthetic unresolved records using their owned complete schema.
        ledger = self.read()
        for row in ledger['intents'].values():
            if runtime._is_unresolved(row):
                row.update(state='rejected', exchange_status='EXPIRED', executed_qty='0')
        self.write(ledger)
        previous_records = deepcopy(ledger['intents'])
        self.owner.api_key = 'synthetic-rotated-bridge-key'
        new_binding = runtime._intent_binding(self.owner)
        result = provisioning.rotate_spot_owner_credentials(
            self.owner, acknowledgement=provisioning.PROVISION_ACK,
            reconciliation_reference='synthetic bridge credential rotation')
        self.assertTrue(result['rotated'])
        self.assertTrue(result['requires_rearm'])
        current = self.read(expected_binding=new_binding)
        self.assertEqual(previous_records, current['intents'])
        self.assertEqual(3, current.indexed_snapshot.receipt.revision)
        self.assertEqual('recovery_required', json.loads(owners.owner_marker_path(self.path).read_text())['state'])
        self.assert_namespace_unchanged()


class JsonIntentNamespaceGuardTests(unittest.TestCase):
    def setUp(self):
        self.temporary = self.enterContext(tempfile.TemporaryDirectory(prefix='trading-bot-json-namespace-'))
        self.path = Path(self.temporary) / 'order_intents.json'
        self.payload = fixtures.synthetic_payload(6, 2)
        with locks.ledger_transaction(self.path):
            locks.write_ledger(self.path, self.payload)

    def test_legacy_read_receipt_avoids_second_json_decode_and_cas_checks_source(self):
        with locks.ledger_transaction(self.path):
            ledger = runtime._read_ledger(self.path)
            self.assertIsInstance(ledger, locks.LegacyLedgerWritePayload)
            ledger['operator_annotation'] = 'synthetic legacy update'
            with patch.object(locks.json, 'loads', side_effect=AssertionError('No second legacy parse')):
                locks.write_ledger(self.path, ledger)
        self.assertEqual(ledger, runtime._read_ledger(self.path))
        with locks.ledger_transaction(self.path), self.assertRaisesRegex(LiveTradingSafetyError, 'source changed'):
            locks.write_ledger(self.path, ledger)

    def test_original_legacy_receipt_cannot_authorize_other_path_but_explicit_copy_can(self):
        ledger = runtime._read_ledger(self.path)
        backup = self.path.with_name('explicit-v2.backup')
        with locks.ledger_transaction(self.path):
            with self.assertRaisesRegex(LiveTradingSafetyError, 'different target path'):
                locks.write_ledger(backup, ledger)
            locks.write_ledger(backup, dict(ledger))
        self.assertEqual(self.payload, json.loads(backup.read_text()))

    def test_receipt_or_backend_presence_fences_v2_reads_and_all_json_writes(self):
        for fence in (locks.indexed_migration_fence_path(self.path),
                      self.path.with_name(self.path.name + '.orphaned.sqlite3')):
            with self.subTest(fence=fence.name):
                ledger = runtime._read_ledger(self.path)
                before = self.path.read_bytes()
                fence.write_bytes(b'presence alone fences namespace')
                try:
                    with self.assertRaisesRegex(LiveTradingSafetyError, 'migration has fenced'):
                        runtime._read_ledger(self.path)
                    for candidate in (ledger, dict(ledger)):
                        with locks.ledger_transaction(self.path), self.assertRaisesRegex(
                                LiveTradingSafetyError, 'namespace requires'):
                            locks.write_ledger(self.path, candidate)
                    self.assertEqual(before, self.path.read_bytes())
                finally:
                    fence.unlink()

    def test_plain_json_writer_rejects_corrupt_duplicate_nonfinite_and_indexed_sources(self):
        original = self.path.read_bytes()
        for corrupt in (b'{bad', b'{"a":1,"a":2}', b'{"value":NaN}', b'{"format_version":3}'):
            with self.subTest(corrupt=corrupt):
                self.path.write_bytes(corrupt)
                with locks.ledger_transaction(self.path), self.assertRaises(LiveTradingSafetyError):
                    locks.write_ledger(self.path, self.payload)
                self.assertEqual(corrupt, self.path.read_bytes())
        self.path.write_bytes(original)

    def test_missing_pointer_with_surviving_backend_or_receipt_cannot_first_use_reset(self):
        for kind in ('backend', 'receipt'):
            with self.subTest(kind=kind):
                self.path.unlink()
                fence = (self.path.with_name(self.path.name + '.surviving.sqlite3') if kind == 'backend'
                         else locks.indexed_migration_fence_path(self.path))
                fence.write_bytes(b'unreadable but retained')
                try:
                    with locks.ledger_transaction(self.path), self.assertRaises(LiveTradingSafetyError):
                        locks.write_ledger(self.path, self.payload)
                    self.assertFalse(self.path.exists())
                finally:
                    fence.unlink()
                    self.path.write_text(json.dumps(self.payload))

    def test_backend_namespace_detection_treats_logical_basename_literally(self):
        path = self.path.with_name('intent[one].json')
        backend = path.with_name(path.name + '.retained.sqlite3')
        with locks.ledger_transaction(path):
            locks.write_ledger(path, self.payload)
        backend.write_bytes(b'synthetic literal namespace')
        with locks.ledger_transaction(path), self.assertRaises(LiveTradingSafetyError):
            locks.write_ledger(path, self.payload)
        unrelated = self.path.with_name('intento.json.unrelated.sqlite3')
        backend.unlink()
        unrelated.write_bytes(b'unrelated source')
        with locks.ledger_transaction(path):
            locks.write_ledger(path, self.payload)

    def test_marker_allocation_and_plain_storage_remain_legitimate_json(self):
        for basename, payload in (('owner.json', {'generation': 1, 'state': 'recovery_required'}),
                                  ('allocation.json', {'generation': 2, 'intents': {}}),
                                  ('plain.json', {'count': 0})):
            with self.subTest(basename=basename):
                path = self.path.with_name(basename)
                with locks.ledger_transaction(path):
                    locks.write_ledger(path, payload)
                    payload['synthetic_update'] = True
                    locks.write_ledger(path, payload)
                self.assertEqual(payload, json.loads(path.read_text()))

    def test_namespace_change_during_flush_blocks_publication(self):
        original = self.path.read_bytes()
        fence = locks.indexed_migration_fence_path(self.path)
        sync = locks.os.fsync
        def introduce_fence(fd):
            sync(fd)
            fence.write_bytes(b'interrupted cutover')
        with locks.ledger_transaction(self.path), patch.object(locks.os, 'fsync', side_effect=introduce_fence):
            with self.assertRaisesRegex(LiveTradingSafetyError, 'namespace requires'):
                locks.write_ledger(self.path, self.payload)
        self.assertEqual(original, self.path.read_bytes())
        self.assertFalse(list(self.path.parent.glob('*.tmp')))


if __name__ == '__main__':
    unittest.main()
