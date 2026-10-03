"""Offline warm-session integrity, exact admission and committed-history probes."""
from __future__ import annotations

from contextlib import closing
from contextvars import copy_context
from copy import deepcopy
import os
from pathlib import Path
import socket
import sqlite3
import tempfile
import threading
import time
from types import SimpleNamespace
import unittest
from unittest.mock import patch

from app.integrations.exchanges.binance.orders import order_intent_runtime as runtime
from app.integrations.exchanges.binance.orders import order_intent_store as locks
from app.integrations.exchanges.binance.orders import spot_execution_owner as owners
from app.integrations.exchanges.binance.orders import spot_indexed_intent_bridge as bridge
from app.integrations.exchanges.binance.orders import spot_indexed_intent_migration as migration
from app.integrations.exchanges.binance.orders import spot_indexed_intent_selective as selective
from app.integrations.exchanges.binance.orders import spot_indexed_intent_store as full
from app.integrations.exchanges.binance.orders.order_intent_provisioning import PROVISION_ACK
from app.integrations.exchanges.binance.orders.spot_indexed_file_identity import capture_indexed_file_change
from app.settings.live_safety import LiveTradingSafetyError
from tools import benchmark_spot_intent_history as fixtures
from tools import spot_intent_capacity_profiles as profiles


class _Wrapper:
    pass


class SpotIndexedIntentSelectiveTests(unittest.TestCase):
    def setUp(self):
        self.home = Path(self.enterContext(tempfile.TemporaryDirectory(prefix='trading-bot-indexed-selective-'))).resolve()
        self.enterContext(patch.object(Path, 'home', return_value=self.home))
        self.enterContext(patch.object(socket.socket, 'connect', side_effect=AssertionError('No network')))
        self.enterContext(patch.object(socket, 'create_connection', side_effect=AssertionError('No network')))
        self.wrapper = _Wrapper()
        self.wrapper.__dict__.update(vars(fixtures.synthetic_owner()))
        self.path = runtime._intent_path(self.wrapper)
        self.payload = fixtures.synthetic_payload(6, 2)
        self.payload['intents'], _ = profiles.synthetic_opo_records(
            6, original_stops=1, residual_stops=1, attempt_depth=3, residual_depth=3)
        legacy = fixtures.synthetic_payload(2, 1)['intents']
        for row in legacy.values():
            row.update(state='rejected', exchange_status='EXPIRED', executed_qty='0',
                       strategy_exit_client_order_id='shared-legacy-alias')
        self.payload['intents'].update(legacy)
        self.binding = deepcopy(self.payload['binding'])
        with owners.owner_administration_lock(self.path):
            with locks.ledger_transaction(self.path):
                locks.write_ledger(self.path, self.payload)
            owners.provision_owner_marker_locked(self.path, uid=fixtures.SYNTHETIC_UID,
                environment='live', store_id=self.payload['store_id'])
        result = migration.migrate_spot_indexed_intent_store(self.wrapper,
            acknowledgement=PROVISION_ACK, reconciliation_reference='synthetic selective migration')
        self.database, self.backup = Path(result['database_path']), Path(result['backup_path'])
        self.fence = locks.indexed_migration_fence_path(self.path)
        self.start_owner()

    def start_owner(self):
        owners.rearm_owner_marker(self.path, uid=fixtures.SYNTHETIC_UID, environment='live',
            store_id=self.payload['store_id'], acknowledgement=PROVISION_ACK,
            reconciliation_reference='synthetic selective rearm')
        self.owner = owners.claim_execution_owner(self.path, uid=fixtures.SYNTHETIC_UID,
            environment='live', store_id=self.payload['store_id'],
            credential_fingerprint=self.binding['credential_fingerprint'], owner_wrapper=self.wrapper)
        self.addCleanup(self.owner.close)
        self.session = self.open()
        self.addCleanup(self.session.close)

    def open(self, **kwargs):
        with locks.ledger_transaction(self.path):
            authority = bridge.read_indexed_ledger(self.path, expected_binding=self.binding).indexed_authority
            return selective.open_indexed_session(owner=self.owner, owner_wrapper=self.wrapper,
                expected_binding=self.binding, expected_authority=kwargs.pop('expected_authority', authority),
                deadline=locks.current_ledger_deadline(self.path), **kwargs)

    def call(self, method, *args, **kwargs):
        with locks.ledger_transaction(self.path):
            return getattr(self.session, method)(*args, deadline=locks.current_ledger_deadline(self.path), **kwargs)

    def read_full(self):
        with locks.ledger_transaction(self.path):
            if self.session._closed and selective._invalidation_for(self.owner) == 'fenced':
                # Diagnostic complete reader after fencing; no runtime authority.
                return full.read_indexed_snapshot(self.database, logical_path=self.path,
                    rules=bridge.indexed_intent_rules(), expected_binding=self.binding,
                    deadline=locks.current_ledger_deadline(self.path)).payload
            return bridge.read_indexed_ledger(self.path, expected_binding=self.binding)

    def database_bytes(self):
        if self.session._closed:
            return self.database.read_bytes()
        with locks.ledger_transaction(self.path):
            return self.session._connection.serialize()

    def blocked_foreign_sql(self, query, parameters=()):
        if not self.session.native_guarded:
            return False
        with self.assertRaises(sqlite3.OperationalError):
            self.foreign_sql(query, parameters)
        self.assertFalse(self.session._closed)
        self.assertEqual((), self.call('admission_view').unresolved_ids)
        return True

    def proof(self):
        view = self.call('admission_view')
        return view.receipt.store_id, view.active_records

    def new_record(self, identifier='new-selective-buy'):
        return runtime._intent_record({'newClientOrderId': identifier, 'symbol': 'BTCUSDT',
            'side': 'BUY', 'type': 'MARKET', 'quantity': '0.1'}, market='spot', source='synthetic selective')

    def foreign_sql(self, query, parameters=()):
        stamp = self.database.stat()
        with closing(sqlite3.connect(self.database)) as connection, connection:
            connection.execute(query, parameters)
        os.utime(self.database, ns=(stamp.st_atime_ns, stamp.st_mtime_ns))

    def test_startup_and_warm_views_are_exact_detached_and_do_not_reread_full_history(self):
        queried = ('shared-legacy-alias', 'never-used', 'syn-rearm-00000001-000')
        with patch.object(full, '_verified', side_effect=AssertionError('Warm path must not replay history')):
            view = self.call('admission_view', probe_client_ids=queried)
            expected = {key: row for key, row in self.payload['intents'].items() if runtime._has_active_spot_protection(row)}
            self.assertEqual(expected, view.active_records)
            self.assertEqual((), view.unresolved_ids)
            self.assertEqual(tuple(sorted(fixtures.synthetic_payload(2, 1)['intents'])), view.owners('shared-legacy-alias'))
            self.assertEqual((), view.owners('never-used'))
            self.assertEqual(('syn-list-00000001',), view.owners('syn-rearm-00000001-000'))
            with self.assertRaisesRegex(LiveTradingSafetyError, 'not queried'):
                view.owners('unqueried-is-not-unused')
            view.active_records.clear()
            view.metadata['binding'].clear()
            self.assertEqual(expected, view.active_records)
            self.assertEqual(self.binding, view.metadata['binding'])
            record = self.call('read_record', 'syn-list-00000001')
            record['residual_stop_history'].clear()
            self.assertEqual(self.payload['intents']['syn-list-00000001'], self.call('read_record', 'syn-list-00000001'))
            self.assertIsNone(self.call('read_record', 'absent-record'))

    def test_actual_row_update_and_insert_are_full_reader_compatible(self):
        key = 'syn-list-00000001'
        old = self.call('read_record', key)
        replacement = {**old, 'operator_note': 'synthetic whole record CAS'}
        with patch.object(full, '_verified', wraps=full._verified) as complete_checks:
            applied = self.call('cas_record', key, replacement, expected_record=old)
            self.assertEqual(replacement, applied)
            record = self.new_record()
            proof = self.proof()
            self.assertEqual(record, self.call('insert_record', record, protection_proof=proof))
            # Guarded writes preserve the startup anchor; portable writes reverify.
            self.assertEqual(0 if self.session.native_guarded else 2, complete_checks.call_count)
        checked = self.read_full()
        self.assertEqual(3, checked.indexed_snapshot.receipt.revision)
        self.assertEqual(2, checked.indexed_snapshot.record_receipt(key).revision)
        self.assertEqual(replacement, checked['intents'][key])
        self.assertEqual(old['residual_stop_history'], checked['intents'][key]['residual_stop_history'])
        self.assertEqual(record, checked['intents']['new-selective-buy'])
        view = self.call('admission_view', probe_client_ids=('new-selective-buy',))
        self.assertIn('new-selective-buy', view.unresolved_ids)
        self.assertEqual(('new-selective-buy',), view.owners('new-selective-buy'))

    def test_late_whole_record_result_returns_none_without_overwriting_committed_observation(self):
        key = 'syn-list-00000000'
        old = self.call('read_record', key)
        current = {**old, 'operator_note': 'newer exact observation'}
        self.call('cas_record', key, current, expected_record=old)
        before, receipt = self.database_bytes(), self.session.receipt
        self.assertIsNone(self.call('cas_record', key, {**old, 'operator_note': 'late'}, expected_record=old))
        self.assertEqual(before, self.database_bytes())
        self.assertEqual(receipt, self.session.receipt)
        self.assertEqual(current, self.call('read_record', key))

    def test_noop_preserves_head_database_and_session(self):
        key = 'syn-list-00000001'
        old = self.call('read_record', key)
        before, receipt = self.database_bytes(), self.session.receipt
        self.assertEqual(old, self.call('cas_record', key, old, expected_record=old))
        self.assertEqual(before, self.database_bytes())
        self.assertEqual(receipt, self.session.receipt)
        self.assertEqual(old, self.call('read_record', key))

    def test_shared_legacy_ownership_remains_complete_but_new_foreign_owner_rejects(self):
        key = 'synthetic-history-00000000'
        old = self.call('read_record', key)
        self.call('cas_record', key, {**old, 'operator_note': 'allowed existing relation'}, expected_record=old)
        self.assertEqual(2, len(self.call('admission_view', probe_client_ids=('shared-legacy-alias',)).owners('shared-legacy-alias')))
        before = self.database_bytes()
        with self.assertRaisesRegex(LiveTradingSafetyError, 'historical client'):
            self.call('insert_record', self.new_record('shared-legacy-alias'), protection_proof=self.proof())
        self.assertEqual(before, self.database_bytes())
        self.assertEqual(2, len(self.read_full().indexed_snapshot.owners('shared-legacy-alias')))

    def test_history_cannot_be_truncated_or_original_request_changed(self):
        old = self.call('read_record', 'syn-list-00000001')
        candidate = deepcopy(old)
        candidate['residual_stop_history'] = []
        before = self.database_bytes()
        with self.assertRaises(LiveTradingSafetyError):
            self.call('cas_record', 'syn-list-00000001', candidate, expected_record=old)
        self.assertEqual(before, self.database_bytes())
        self.assertEqual(old, self.read_full()['intents']['syn-list-00000001'])

    def test_complete_final_protection_comparison_rejects_changed_residual_identity(self):
        proof = self.proof()
        old = self.call('read_record', 'syn-list-00000001')
        current = {**old, 'residual_stop_order_id': old['residual_stop_order_id'] + 1}
        self.call('cas_record', 'syn-list-00000001', current, expected_record=old)
        before = self.database_bytes()
        with self.assertRaisesRegex(LiveTradingSafetyError, 'protection changed'):
            self.call('insert_record', self.new_record(), protection_proof=proof)
        self.assertEqual(before, self.database_bytes())
        self.assertNotIn('new-selective-buy', self.read_full()['intents'])

    def test_complete_final_submitted_guard_excludes_only_its_own_pending_record(self):
        record = self.new_record()
        self.call('insert_record', record, protection_proof=self.proof())
        proof = self.proof()
        applied = self.call('cas_record', record['client_order_id'], {**record, 'state': 'submitted'},
            expected_record=record, protection_proof=proof, exclude_client_order_id=record['client_order_id'])
        self.assertEqual('submitted', applied['state'])
        current = self.read_full()['intents'][record['client_order_id']]
        self.assertEqual(applied, current)

    def test_external_sql_same_head_and_restored_mtime_fences_and_cannot_reopen_same_owner(self):
        if self.blocked_foreign_sql('UPDATE current_records SET record=? WHERE client_id=?', ('{}', 'syn-list-00000005')):
            return
        self.foreign_sql('UPDATE current_records SET record=? WHERE client_id=?', ('{}', 'syn-list-00000005'))
        with self.assertRaises(LiveTradingSafetyError):
            self.call('admission_view')
        self.assertFalse(selective.indexed_session_refresh_required(self.owner))
        with locks.ledger_transaction(self.path), self.assertRaisesRegex(LiveTradingSafetyError, 'fenced'):
            selective.open_indexed_session(owner=self.owner, owner_wrapper=self.wrapper,
                expected_binding=self.binding, deadline=locks.current_ledger_deadline(self.path))

    def test_persistent_data_version_independently_detects_foreign_sql_commit(self):
        if self.blocked_foreign_sql('UPDATE current_records SET revision=revision+1 WHERE client_id=?', ('syn-list-00000005',)):
            return
        self.foreign_sql('UPDATE current_records SET revision=revision+1 WHERE client_id=?', ('syn-list-00000005',))
        # A refreshed file token cannot stand in for the persistent SQL observer.
        self.session._change = capture_indexed_file_change(self.database)
        with self.assertRaisesRegex(LiveTradingSafetyError, 'external SQL'):
            self.call('read_record', 'syn-list-00000001')

    def test_raw_dormant_corruption_restoring_mtime_fences_before_admission(self):
        raw, stamp = self.database_bytes(), self.database.stat()
        marker = b'"syn-list-00000005"'
        position = raw.index(marker)
        if self.session.native_guarded:
            with self.assertRaises(PermissionError):
                self.database.open('r+b')
            self.assertEqual(raw, self.database_bytes())
            self.assertEqual((), self.call('admission_view').unresolved_ids)
            return
        with self.database.open('r+b') as stream:
            stream.seek(position)
            stream.write(marker.replace(b'00000005', b'00000009'))
        os.utime(self.database, ns=(stamp.st_atime_ns, stamp.st_mtime_ns))
        with self.assertRaises(LiveTradingSafetyError):
            self.call('admission_view')

    def test_projection_omission_fences_even_when_other_active_record_is_queried(self):
        if self.blocked_foreign_sql('DELETE FROM active_projection WHERE client_id=?', ('syn-list-00000000',)):
            return
        self.foreign_sql('DELETE FROM active_projection WHERE client_id=?', ('syn-list-00000000',))
        with self.assertRaises(LiveTradingSafetyError):
            self.call('read_record', 'syn-list-00000001')

    def test_schema_change_fences(self):
        if self.blocked_foreign_sql('CREATE TABLE unauthorized_table (value TEXT)'):
            return
        self.foreign_sql('CREATE TABLE unauthorized_table (value TEXT)')
        with self.assertRaises(LiveTradingSafetyError):
            self.call('admission_view')

    def test_original_manifest_migration_and_backup_receipts_are_preserved(self):
        for path in (self.path, self.fence, self.backup):
            with self.subTest(path=path.name):
                self.session.close()
                self.session = self.open()
                self.addCleanup(self.session.close)
                saved = path.read_bytes()
                stamp = path.stat()
                path.write_bytes(saved + b' ')
                os.utime(path, ns=(stamp.st_atime_ns, stamp.st_mtime_ns))
                with self.assertRaises(LiveTradingSafetyError):
                    self.call('admission_view')
                path.write_bytes(saved)
                self.owner.close()
                self.start_owner()

    def test_actual_owner_and_original_lock_context_required_without_destroying_valid_session(self):
        key = 'syn-list-00000000'
        with self.assertRaises(LiveTradingSafetyError):
            self.session.read_record(key, deadline=time.monotonic() + 1)
        with locks.ledger_transaction(self.path):
            deadline, context = locks.current_ledger_deadline(self.path), copy_context()
        with self.assertRaises(LiveTradingSafetyError):
            context.run(self.session.read_record, key, deadline=deadline)
        self.assertEqual(self.payload['intents'][key], self.call('read_record', key))
        with locks.ledger_transaction(self.path), self.assertRaises(LiveTradingSafetyError):
            selective.open_indexed_session(owner=object(), owner_wrapper=self.wrapper,
                expected_binding=self.binding, deadline=locks.current_ledger_deadline(self.path))

    def test_valid_worker_thread_serializes_the_persistent_connection_with_its_own_lock(self):
        results = []
        def worker():
            try:
                results.append(self.call('read_record', 'syn-list-00000001'))
            except BaseException as exc:
                results.append(exc)
        thread = threading.Thread(target=worker)
        thread.start()
        thread.join(timeout=5)
        self.assertFalse(thread.is_alive())
        self.assertEqual([self.payload['intents']['syn-list-00000001']], results)

    def test_direct_session_rejects_changed_wrapper_configuration(self):
        self.wrapper.api_key = 'different-synthetic-key'
        with self.assertRaises(LiveTradingSafetyError):
            self.call('admission_view')
        self.assertTrue(self.session._closed)

    def test_changed_owner_generation_fences_and_releases_registered_connection(self):
        self.owner.generation += 1
        with self.assertRaises(LiveTradingSafetyError):
            self.call('admission_view')
        self.assertTrue(self.session._closed)
        with self.assertRaises(sqlite3.ProgrammingError):
            self.session._connection.execute('SELECT 1')
        self.owner.generation -= 1

    def test_startup_rechecks_source_after_the_prior_full_read(self):
        self.session.close()
        updated = self.read_full()
        old = updated.indexed_authority
        updated['operator_note'] = 'synthetic source changed before owner/session handoff'
        with locks.ledger_transaction(self.path):
            bridge.write_indexed_ledger(self.path, updated)
        with locks.ledger_transaction(self.path), self.assertRaisesRegex(LiveTradingSafetyError, 'prior complete read'):
            selective.open_indexed_session(owner=self.owner, owner_wrapper=self.wrapper,
                expected_binding=self.binding, expected_authority=old,
                deadline=locks.current_ledger_deadline(self.path))

    def test_busy_writer_gets_only_remaining_original_deadline_and_invalidates(self):
        old = self.call('read_record', 'syn-list-00000001')
        if self.session.native_guarded:
            with self.assertRaises(sqlite3.OperationalError):
                sqlite3.connect(self.database, isolation_level=None)
            self.assertEqual(old, self.call('read_record', 'syn-list-00000001'))
            return
        blocker = sqlite3.connect(self.database, isolation_level=None)
        self.addCleanup(blocker.close)
        blocker.execute('BEGIN IMMEDIATE')
        started = time.monotonic()
        with locks.ledger_transaction(self.path), self.assertRaises(LiveTradingSafetyError):
            deadline = min(locks.current_ledger_deadline(self.path), time.monotonic() + 0.12)
            self.session.cas_record('syn-list-00000001', {**old, 'operator_note': 'must not commit'},
                                    expected_record=old, deadline=deadline)
        self.assertLess(time.monotonic() - started, 1)
        blocker.rollback()
        self.assertEqual(old, self.read_full()['intents']['syn-list-00000001'])

    def test_partial_sql_failure_rolls_back_all_tables_and_invalidates_anchor(self):
        old = self.call('read_record', 'syn-list-00000001')
        original = full._sql
        def interrupted(connection, deadline, query, parameters=()):
            if query.startswith('UPDATE store_state'):
                raise sqlite3.OperationalError('synthetic disk full')
            return original(connection, deadline, query, parameters)
        with patch.object(full, '_sql', side_effect=interrupted), self.assertRaises(LiveTradingSafetyError):
            self.call('cas_record', 'syn-list-00000001', {**old, 'operator_note': 'rollback'}, expected_record=old)
        checked = self.read_full()
        self.assertEqual(1, checked.indexed_snapshot.receipt.revision)
        self.assertEqual(old, checked['intents']['syn-list-00000001'])
        self.assertTrue(self.session._closed)

    def test_commit_return_uncertainty_never_reuses_the_old_anchor(self):
        old = self.call('read_record', 'syn-list-00000001')
        original = full._sql
        def uncertain(connection, deadline, query, parameters=()):
            cursor = original(connection, deadline, query, parameters)
            if query == 'COMMIT':
                raise sqlite3.OperationalError('synthetic uncertain COMMIT return')
            return cursor
        with patch.object(full, '_sql', side_effect=uncertain), self.assertRaises(LiveTradingSafetyError):
            self.call('cas_record', 'syn-list-00000001', {**old, 'operator_note': 'committed but uncertain'}, expected_record=old)
        checked = self.read_full()
        self.assertEqual(2, checked.indexed_snapshot.receipt.revision)
        self.assertEqual('committed but uncertain', checked['intents']['syn-list-00000001']['operator_note'])
        self.assertTrue(self.session._closed)

    def test_full_writer_trusted_hook_allows_only_explicit_reverification(self):
        ledger = self.read_full()
        ledger['operator_note'] = 'synthetic recognized full writer'
        guarded = self.session.native_guarded
        with locks.ledger_transaction(self.path):
            bridge.write_indexed_ledger(self.path, ledger)
        self.assertFalse(self.session._closed)
        self.assertIsNone(self.session._pending)
        self.assertEqual(guarded, self.session.native_guarded)
        self.assertFalse(selective.indexed_session_refresh_required(self.owner))
        self.assertEqual('synthetic recognized full writer', self.call('admission_view').metadata['operator_note'])

    def test_full_writer_noop_hook_preserves_warm_session(self):
        ledger = self.read_full()
        with locks.ledger_transaction(self.path):
            selective.notify_indexed_full_commit(self.path, ledger.indexed_snapshot, ledger.indexed_authority)
            found = selective.get_indexed_session(owner=self.owner, owner_wrapper=self.wrapper,
                expected_binding=self.binding, deadline=locks.current_ledger_deadline(self.path))
        self.assertIs(self.session, found)
        self.assertFalse(selective.indexed_session_refresh_required(self.owner))


    def test_historical_ownership_survives_current_field_removal_and_rejects_reuse(self):
        key = 'synthetic-history-00000000'
        old = self.call('read_record', key)
        own_only = {**old, 'strategy_exit_client_order_id': 'retained-historical-only'}
        self.call('cas_record', key, own_only, expected_record=old)
        without = deepcopy(own_only)
        del without['strategy_exit_client_order_id']
        self.call('cas_record', key, without, expected_record=own_only)
        view = self.call('admission_view', probe_client_ids=('retained-historical-only',))
        self.assertEqual((key,), view.owners('retained-historical-only'))
        checked = self.read_full()
        self.assertEqual((key,), checked.indexed_snapshot.owners('retained-historical-only'))
        before = self.database_bytes()
        with self.assertRaisesRegex(LiveTradingSafetyError, 'historical client'):
            self.call('insert_record', self.new_record('retained-historical-only'), protection_proof=self.proof())
        self.assertEqual(before, self.database_bytes())

    def test_foreign_valid_commit_in_postcommit_gap_is_not_adopted(self):
        old = self.call('read_record', 'syn-list-00000001')
        original, crossed, denied = full._sql, [], []
        guarded = self.session.native_guarded
        def crossing(connection, deadline, query, parameters=()):
            cursor = original(connection, deadline, query, parameters)
            if query == 'COMMIT' and not crossed:
                crossed.append(True)
                try:
                    foreign = full.read_indexed_snapshot(self.database, logical_path=self.path,
                        rules=bridge.indexed_intent_rules(), expected_binding=self.binding, deadline=deadline)
                except LiveTradingSafetyError:
                    if not guarded:
                        raise
                    denied.append(True)
                    return cursor
                candidate = foreign.payload
                candidate['foreign_commit_probe'] = 'synthetic gap writer'
                full.replace_indexed_snapshot(self.database, candidate, expected=foreign,
                    rules=bridge.indexed_intent_rules(), expected_binding=self.binding, deadline=deadline)
            return cursor
        with patch.object(full, '_sql', side_effect=crossing):
            if guarded:
                self.call('cas_record', 'syn-list-00000001', {**old, 'operator_note': 'own committed update'}, expected_record=old)
            else:
                with self.assertRaisesRegex(LiveTradingSafetyError, 'crossed publication'):
                    self.call('cas_record', 'syn-list-00000001', {**old, 'operator_note': 'own committed update'}, expected_record=old)
        checked = self.read_full()
        self.assertTrue(crossed)
        self.assertEqual('own committed update', checked['intents']['syn-list-00000001']['operator_note'])
        if guarded:
            self.assertTrue(denied)
            self.assertEqual(2, checked.indexed_snapshot.receipt.revision)
            self.assertNotIn('foreign_commit_probe', checked)
            self.assertFalse(self.session._closed)
        else:
            self.assertEqual(3, checked.indexed_snapshot.receipt.revision)
            self.assertEqual('synthetic gap writer', checked['foreign_commit_probe'])
            self.assertTrue(self.session._closed)
        self.assertFalse(selective.indexed_session_refresh_required(self.owner))

    def test_cancellation_after_journal_append_rolls_back_and_invalidates(self):
        old = self.call('read_record', 'syn-list-00000001')
        original = full._sql
        def cancelled(connection, deadline, query, parameters=()):
            cursor = original(connection, deadline, query, parameters)
            if query.startswith('INSERT INTO current_records'):
                raise KeyboardInterrupt('synthetic cancelled worker')
            return cursor
        with patch.object(full, '_sql', side_effect=cancelled), self.assertRaises(KeyboardInterrupt):
            self.call('cas_record', 'syn-list-00000001', {**old, 'operator_note': 'cancelled'}, expected_record=old)
        checked = self.read_full()
        self.assertEqual(1, checked.indexed_snapshot.receipt.revision)
        self.assertEqual(old, checked['intents']['syn-list-00000001'])
        self.assertTrue(self.session._closed)


    def test_explicit_old_owner_close_allows_new_owner_without_a_stale_sql_connection(self):
        old_session, old_owner = self.session, self.owner
        old_owner.close()
        self.assertIsNotNone(self.wrapper)
        self.start_owner()
        self.assertIsNot(old_owner, self.owner)
        self.assertTrue(old_session._closed)
        with self.assertRaises(sqlite3.ProgrammingError):
            old_session._connection.execute('SELECT 1')
        self.assertEqual(self.payload['intents']['syn-list-00000001'], self.call('read_record', 'syn-list-00000001'))

    def test_owner_lost_after_row_append_fences_before_commit(self):
        old = self.call('read_record', 'syn-list-00000001')
        original = full._sql
        def lost(connection, deadline, query, parameters=()):
            cursor = original(connection, deadline, query, parameters)
            if query.startswith('UPDATE store_state'):
                self.owner.generation += 1
            return cursor
        with patch.object(full, '_sql', side_effect=lost), self.assertRaises(LiveTradingSafetyError):
            self.call('cas_record', 'syn-list-00000001', {**old, 'operator_note': 'must not persist'}, expected_record=old)
        self.owner.generation -= 1
        checked = self.read_full()
        self.assertEqual(1, checked.indexed_snapshot.receipt.revision)
        self.assertEqual(old, checked['intents']['syn-list-00000001'])


    def test_raw_dormant_edit_in_postcommit_receipt_gap_must_fence_next_admission(self):
        old = self.call('read_record', 'syn-list-00000001')
        original, crossed, denied = full._sql, [], []
        guarded = self.session.native_guarded
        needle = b'"syn-list-00000005"'
        position = self.database_bytes().index(needle)
        def crossing(connection, deadline, query, parameters=()):
            cursor = original(connection, deadline, query, parameters)
            if query == 'COMMIT' and not crossed:
                crossed.append(True)
                stamp = self.database.stat()
                try:
                    with self.database.open('r+b') as stream:
                        stream.seek(position)
                        stream.write(needle.replace(b'00000005', b'00000009'))
                except PermissionError:
                    if not guarded:
                        raise
                    denied.append(True)
                    return cursor
                os.utime(self.database, ns=(stamp.st_atime_ns, stamp.st_mtime_ns))
            return cursor
        try:
            with patch.object(full, '_sql', side_effect=crossing):
                self.call('cas_record', 'syn-list-00000001', {**old, 'operator_note': 'raw gap probe'}, expected_record=old)
        except LiveTradingSafetyError:
            if guarded:
                raise
        self.assertTrue(crossed)
        if guarded:
            self.assertTrue(denied)
            self.assertEqual('raw gap probe', self.read_full()['intents']['syn-list-00000001']['operator_note'])
            self.assertEqual((), self.call('admission_view').unresolved_ids)
        else:
            # Real mutation must fail both full validation and warm admission.
            with self.assertRaises(LiveTradingSafetyError):
                self.read_full()
            with self.assertRaises(LiveTradingSafetyError):
                self.call('admission_view')

    def test_borrowed_complete_result_cannot_run_until_final_publication(self):
        if not self.session.native_guarded:
            self.skipTest('Continuously guarded borrow is a Windows route')
        ledger = self.read_full()
        ledger['operator_note'] = 'synthetic unacknowledged full writer'
        with locks.ledger_transaction(self.path):
            result = selective.replace_owned_indexed_snapshot(self.path, ledger,
                expected=ledger.indexed_snapshot, expected_binding=self.binding,
                deadline=locks.current_ledger_deadline(self.path))
            self.assertEqual(result.receipt, self.session._pending[1])
            with self.assertRaisesRegex(LiveTradingSafetyError, 'pending'):
                selective.read_owned_indexed_snapshot(self.path, expected_binding=self.binding,
                    deadline=locks.current_ledger_deadline(self.path))
            with self.assertRaisesRegex(LiveTradingSafetyError, 'fenced'):
                bridge.read_indexed_ledger(self.path, expected_binding=self.binding)
        self.assertTrue(self.session._closed)

    def reopen_portable(self):
        self.session.close()
        # Exercise the conservative route on this host without modifying the
        # real file-identity helper's native platform or its corruption checks.
        with patch.object(selective, 'sys', SimpleNamespace(platform='portable-test')):
            self.session = self.open()
        self.addCleanup(self.session.close)
        self.assertFalse(self.session.native_guarded)

    def test_portable_fresh_pager_proof_fences_actual_raw_postcommit_gap(self):
        self.reopen_portable()
        self.test_raw_dormant_edit_in_postcommit_receipt_gap_must_fence_next_admission()

    def test_portable_fresh_pager_writes_retain_complete_reader_compatibility(self):
        self.reopen_portable()
        self.test_actual_row_update_and_insert_are_full_reader_compatible()

    def test_portable_external_full_commit_is_not_adopted_during_publication(self):
        self.reopen_portable()
        self.test_foreign_valid_commit_in_postcommit_gap_is_not_adopted()

    def test_portable_full_writer_rejects_changed_actual_wrapper_before_commit(self):
        self.reopen_portable()
        ledger = self.read_full()
        ledger['operator_note'] = 'must not persist under changed wrapper'
        before = self.database_bytes()
        self.wrapper.api_key = 'changed-synthetic-key'
        with locks.ledger_transaction(self.path), self.assertRaises(LiveTradingSafetyError):
            bridge.write_indexed_ledger(self.path, ledger)
        self.assertTrue(self.session._closed)
        self.assertEqual(before, self.database_bytes())
        self.assertEqual(1, self.read_full().indexed_snapshot.receipt.revision)

    def test_portable_full_writer_rejects_lost_registered_owner_before_commit(self):
        self.reopen_portable()
        ledger = self.read_full()
        ledger['operator_note'] = 'must not persist without the original owner'
        before = self.database_bytes()
        self.owner.close()
        with locks.ledger_transaction(self.path), self.assertRaises(LiveTradingSafetyError):
            bridge.write_indexed_ledger(self.path, ledger)
        self.assertTrue(self.session._closed)
        self.assertEqual(before, self.database_bytes())
        self.assertEqual(1, self.read_full().indexed_snapshot.receipt.revision)

    def test_portable_full_writer_rechecks_owner_after_append_before_commit(self):
        self.reopen_portable()
        ledger = self.read_full()
        ledger['operator_note'] = 'must rollback after lost owner'
        before, original = self.database_bytes(), full._append
        def lost(*args, **kwargs):
            result = original(*args, **kwargs)
            self.owner.generation += 1
            return result
        try:
            with locks.ledger_transaction(self.path), patch.object(full, '_append', side_effect=lost):
                with self.assertRaises(LiveTradingSafetyError):
                    bridge.write_indexed_ledger(self.path, ledger)
        finally:
            self.owner.generation -= 1
        self.assertTrue(self.session._closed)
        self.assertEqual(before, self.database_bytes())
        self.assertEqual(1, self.read_full().indexed_snapshot.receipt.revision)

    def test_portable_borrowed_full_writer_has_fresh_complete_postcommit_proof(self):
        self.reopen_portable()
        ledger = self.read_full()
        ledger['operator_note'] = 'portable full CAS'
        with patch.object(full, '_verified', wraps=full._verified) as checked:
            with locks.ledger_transaction(self.path):
                bridge.write_indexed_ledger(self.path, ledger)
            self.assertEqual(3, checked.call_count)
        self.assertFalse(self.session._closed)
        self.assertIsNone(self.session._pending)
        self.assertEqual('portable full CAS', self.call('admission_view').metadata['operator_note'])

    def test_portable_borrowed_full_postcommit_raw_edit_is_never_adopted(self):
        self.reopen_portable()
        ledger = self.read_full()
        ledger['operator_note'] = 'portable raw gap full CAS'
        needle = b'"syn-list-00000005"'
        position = self.database_bytes().index(needle)
        original, crossed = full._sql, []
        def corrupt(connection, deadline, query, parameters=()):
            cursor = original(connection, deadline, query, parameters)
            if query == 'COMMIT' and not crossed:
                crossed.append(True)
                stamp = self.database.stat()
                with self.database.open('r+b') as stream:
                    stream.seek(position)
                    stream.write(needle.replace(b'00000005', b'00000009'))
                os.utime(self.database, ns=(stamp.st_atime_ns, stamp.st_mtime_ns))
            return cursor
        with locks.ledger_transaction(self.path), patch.object(full, '_sql', side_effect=corrupt):
            with self.assertRaises(LiveTradingSafetyError):
                bridge.write_indexed_ledger(self.path, ledger)
        self.assertTrue(crossed)
        self.assertTrue(self.session._closed)
        with self.assertRaises(LiveTradingSafetyError):
            self.read_full()
        with self.assertRaises(LiveTradingSafetyError):
            self.call('admission_view')

    def test_optional_binding_full_read_keeps_actual_owner_authority(self):
        with locks.ledger_transaction(self.path):
            ledger = bridge.read_indexed_ledger(self.path)
        self.assertEqual(self.payload, ledger)
        self.assertEqual(self.session.receipt, ledger.indexed_snapshot.receipt)

    def test_expired_connect_acquisition_releases_the_guard_without_authority(self):
        self.session.close()
        with locks.ledger_transaction(self.path):
            authority = bridge.read_indexed_ledger(self.path, expected_binding=self.binding).indexed_authority
            deadline = locks.current_ledger_deadline(self.path)
            with patch.object(selective.time, 'monotonic', return_value=deadline + 1):
                with self.assertRaisesRegex(LiveTradingSafetyError, 'acquisition exceeded'):
                    selective.open_indexed_session(owner=self.owner, owner_wrapper=self.wrapper,
                        expected_binding=self.binding, expected_authority=authority, deadline=deadline)
            with closing(sqlite3.connect(self.database)) as connection:
                self.assertEqual((1,), connection.execute('SELECT revision FROM store_state').fetchone())

    def test_guard_is_required_instead_of_platform_announcement(self):
        if not self.session.native_guarded:
            self.skipTest('Actual Windows native guard qualification')
        with patch.object(selective, 'assert_indexed_native_guard', side_effect=LiveTradingSafetyError('guard lost')):
            with self.assertRaisesRegex(LiveTradingSafetyError, 'guard lost'):
                self.call('admission_view')
        self.assertTrue(self.session._closed)


if __name__ == '__main__':
    unittest.main()
