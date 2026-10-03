"""Offline complete-history, CAS and projection integrity for the indexed foundation."""
from __future__ import annotations

from contextlib import closing
from copy import deepcopy
import multiprocessing
from pathlib import Path
import socket
import sqlite3
import tempfile
import time
import unittest
from unittest.mock import patch
from uuid import uuid4

from app.integrations.exchanges.binance.orders import order_intent_runtime as runtime
from app.integrations.exchanges.binance.orders import order_intent_store as locks
from app.integrations.exchanges.binance.orders import spot_indexed_intent_store as indexed
from app.settings.live_safety import LiveTradingSafetyError
from tools import benchmark_spot_intent_history as fixtures
from tools import spot_intent_capacity_profiles as profiles


_DEFAULT = object()

RULES = indexed.IndexedIntentRules(runtime.validate_order_intent_ledger, runtime._is_unresolved,
                                  runtime._has_active_spot_protection, runtime.used_spot_client_order_ids)


def _interrupted_commit(path_text, logical_text, ready, release):
    path, logical = Path(path_text), Path(logical_text)
    binding = fixtures.synthetic_payload(6, 2)['binding']
    original = indexed._sql
    def pause_commit(connection, deadline, query, parameters=()):
        if query == 'COMMIT':
            ready.set()
            if not release.wait(timeout=20):
                raise RuntimeError('Offline crash barrier was not released')
        return original(connection, deadline, query, parameters)
    with locks.ledger_transaction(logical):
        snapshot = indexed.read_indexed_snapshot(path, logical_path=logical, rules=RULES,
                                                 expected_binding=binding, deadline=locks.current_ledger_deadline())
        payload = snapshot.payload
        payload['crash_candidate'] = 'must never commit'
        with patch.object(indexed, '_sql', side_effect=pause_commit):
            indexed.replace_indexed_snapshot(path, payload, expected=snapshot, rules=RULES,
                                             expected_binding=binding, deadline=locks.current_ledger_deadline())


class SpotIndexedIntentStoreTests(unittest.TestCase):
    def setUp(self):
        self.temporary = self.enterContext(tempfile.TemporaryDirectory(prefix='trading-bot-indexed-foundation-'))
        self.root = Path(self.temporary)
        self.logical = self.root / 'order_intents.json'
        self.path = self.root / 'store.sqlite3'
        self.payload = fixtures.synthetic_payload(6, 2)
        self.binding = deepcopy(self.payload['binding'])
        self.enterContext(patch.object(socket.socket, 'connect', side_effect=AssertionError('No network')))
        self.enterContext(patch.object(socket, 'create_connection', side_effect=AssertionError('No network')))

    def create(self, payload=_DEFAULT, path=None, backend_id=None):
        with locks.ledger_transaction(self.logical):
            return indexed.create_indexed_store(path or self.path, self.payload if payload is _DEFAULT else payload, logical_path=self.logical,
                                                rules=RULES, expected_binding=self.binding,
                                                deadline=locks.current_ledger_deadline(), backend_id=backend_id)

    def read(self, **kwargs):
        with locks.ledger_transaction(self.logical):
            return indexed.read_indexed_snapshot(self.path, logical_path=self.logical, rules=RULES,
                                                 expected_binding=self.binding,
                                                 deadline=locks.current_ledger_deadline(), **kwargs)

    def replace(self, payload, expected, **kwargs):
        with locks.ledger_transaction(self.logical):
            return indexed.replace_indexed_snapshot(self.path, payload, expected=expected, rules=RULES,
                                                    expected_binding=self.binding,
                                                    deadline=locks.current_ledger_deadline(), **kwargs)

    def test_exact_metadata_roundtrip_and_detached_complete_payload_receipt(self):
        self.payload['preserved_metadata'] = {'reference': 'synthetic-only', 'generation': 7}
        snapshot = self.create()
        self.assertEqual(self.payload, snapshot.payload)
        self.assertEqual(snapshot, self.read(expected_store_id=self.payload['store_id'],
                                             expected_backend_id=snapshot.receipt.database_id))
        mutable = snapshot.payload
        self.assertIs(mutable.indexed_snapshot, snapshot)
        mutable['intents'].clear()
        self.assertEqual(self.payload, snapshot.payload)
        key = next(iter(self.payload['intents']))
        snapshot.record(key)['state'] = 'unknown'
        self.assertEqual(self.payload['intents'][key], snapshot.record(key))
        self.assertEqual((key,), snapshot.owners(key))
        self.assertEqual(2, len(snapshot.unresolved_ids))
        self.assertEqual(6, len(snapshot.record_receipts))

    def test_actual_opo_active_unresolved_and_full_nested_id_projections(self):
        self.payload['intents'], _ = profiles.synthetic_opo_records(
            6, original_stops=1, residual_stops=1, attempt_depth=2, residual_depth=2)
        snapshot = self.create()
        records = self.payload['intents']
        expected_active = tuple(sorted(key for key, row in records.items() if runtime._has_active_spot_protection(row)))
        expected_unresolved = tuple(sorted(key for key, row in records.items() if runtime._is_unresolved(row)))
        expected_relations = {(identifier, key) for key, row in records.items()
                              for identifier in runtime.used_spot_client_order_ids({key: row}) | {key}}
        self.assertEqual(expected_active, snapshot.active_ids)
        self.assertEqual(expected_unresolved, snapshot.unresolved_ids)
        self.assertEqual(expected_relations, set(snapshot.reserved_owners))
        self.assertEqual(2, len(snapshot.active_ids))
        self.assertIn('syn-rearm-00000001-000', {identifier for identifier, _ in snapshot.reserved_owners})
        self.assertEqual(snapshot, self.read())

    def test_insert_expected_missing_and_atomic_multi_record_update(self):
        snapshot = self.create()
        new = runtime._intent_record({'newClientOrderId': 'new-distinct', 'symbol': 'BTCUSDT', 'side': 'BUY',
                                      'type': 'MARKET', 'quantity': '0.1'}, market='spot', source='offline-foundation')
        key = next(iter(self.payload['intents']))
        updated = deepcopy(snapshot.record(key))
        updated['updated_at'] = '2026-02-01T00:00:00+00:00'
        with locks.ledger_transaction(self.logical):
            result = indexed.compare_and_swap_indexed_records(
                self.path, {key: updated, 'new-distinct': new}, expected=snapshot,
                expected_records={key: snapshot.record_receipt(key), 'new-distinct': None},
                rules=RULES, expected_binding=self.binding, deadline=locks.current_ledger_deadline())
        self.assertEqual(2, result.receipt.revision)
        self.assertEqual(2, result.record_receipt(key).revision)
        self.assertEqual(1, result.record_receipt('new-distinct').revision)
        self.assertEqual(7, len(result.record_receipts))
        self.assertEqual(result, self.read())
        with locks.ledger_transaction(self.logical), self.assertRaises(LiveTradingSafetyError):
            indexed.compare_and_swap_indexed_records(
                self.path, {key: updated}, expected=result, expected_records={key: None},
                rules=RULES, expected_binding=self.binding, deadline=locks.current_ledger_deadline())

    def test_stale_head_record_and_replacement_database_receipts_reject(self):
        original = self.create()
        candidate = original.payload
        candidate['operator_annotation'] = 'offline'
        current = self.replace(candidate, original)
        with self.assertRaisesRegex(LiveTradingSafetyError, 'source changed'):
            self.replace(candidate, original)
        self.assertEqual(current, self.read())
        self.path.unlink()
        replacement = self.create(current.payload)
        self.assertNotEqual(current.receipt.database_id, replacement.receipt.database_id)
        with self.assertRaisesRegex(LiveTradingSafetyError, 'source changed'):
            self.replace(candidate, current)
        self.assertEqual(replacement, self.read())

    def test_noop_write_keeps_head_and_database_bytes(self):
        snapshot = self.create()
        before = self.path.read_bytes()
        self.assertEqual(snapshot, self.replace(snapshot.payload, snapshot))
        self.assertEqual(before, self.path.read_bytes())

    def test_valid_full_snapshot_cannot_delete_terminal_record_or_history(self):
        self.payload['intents'], _ = profiles.synthetic_opo_records(
            6, original_stops=1, residual_stops=1, attempt_depth=2, residual_depth=2)
        snapshot = self.create()
        for fault in ('terminal-record', 'exit-history', 'stop-history', 'original-request'):
            with self.subTest(fault=fault):
                candidate = snapshot.payload
                if fault == 'terminal-record':
                    del candidate['intents']['syn-list-00000005']
                elif fault == 'exit-history':
                    candidate['intents']['syn-list-00000000']['strategy_exit_history'] = []
                elif fault == 'stop-history':
                    candidate['intents']['syn-list-00000001']['residual_stop_history'] = []
                else:
                    row = candidate['intents']['syn-list-00000005']
                    row['request']['workingPrice'] = '101'
                # These are coherent standalone snapshots; full validity cannot prove preservation.
                runtime.validate_order_intent_ledger(candidate, expected_binding=self.binding)
                before = self.path.read_bytes()
                with self.assertRaises(LiveTradingSafetyError):
                    self.replace(candidate, snapshot)
                self.assertEqual(before, self.path.read_bytes())
                self.assertEqual(snapshot, self.read())

    def test_history_reservations_survive_current_alias_removal_and_block_other_owner(self):
        first = next(iter(self.payload['intents']))
        self.payload['intents'][first]['strategy_exit_client_order_id'] = 'historical-reserved-only'
        snapshot = self.create()
        candidate = snapshot.payload
        del candidate['intents'][first]['strategy_exit_client_order_id']
        current = self.replace(candidate, snapshot)
        self.assertEqual((first,), current.owners('historical-reserved-only'))
        new = runtime._intent_record({'newClientOrderId': 'historical-reserved-only', 'symbol': 'BTCUSDT',
                                      'side': 'BUY', 'type': 'MARKET', 'quantity': '0.1'},
                                     market='spot', source='offline-foundation')
        candidate = current.payload
        candidate['intents']['historical-reserved-only'] = new
        runtime.validate_order_intent_ledger(candidate)
        with self.assertRaisesRegex(LiveTradingSafetyError, 'historical client identifier'):
            self.replace(candidate, current)
        self.assertEqual(current, self.read())

    def test_legitimate_legacy_shared_relations_remain_complete_without_overwriting_owners(self):
        keys = list(self.payload['intents'])[:2]
        for key in keys:
            self.payload['intents'][key]['strategy_exit_client_order_id'] = 'shared-legacy-alias'
        runtime.validate_order_intent_ledger(self.payload)
        snapshot = self.create()
        self.assertEqual(tuple(keys), snapshot.owners('shared-legacy-alias'))
        candidate = snapshot.payload
        candidate['synthetic_annotation'] = 'preserved'
        result = self.replace(candidate, snapshot)
        self.assertEqual(tuple(keys), result.owners('shared-legacy-alias'))
        self.assertEqual(result, self.read())

    def test_metadata_rotation_exact_binding_and_history_prefix(self):
        snapshot = self.create()
        metadata = {key: value for key, value in snapshot.payload.items() if key != 'intents'}
        new_binding = {**self.binding, 'credential_fingerprint': 'd' * 64}
        metadata['binding'] = new_binding
        metadata['credential_rotation_history'] = [{'previous_fingerprint': self.binding['credential_fingerprint'],
            'new_fingerprint': 'd' * 64, 'rotated_at': fixtures.FIXED_TIME,
            'reconciliation_reference': 'synthetic offline rotation'}]
        with locks.ledger_transaction(self.logical):
            result = indexed.compare_and_swap_indexed_metadata(
                self.path, metadata, expected=snapshot, rules=RULES, expected_binding=self.binding,
                expected_new_binding=new_binding, deadline=locks.current_ledger_deadline())
        self.binding = new_binding
        self.assertEqual(result, self.read())
        for fault in ('store', 'created', 'history', 'metadata-remove'):
            with self.subTest(fault=fault):
                candidate = result.payload
                if fault == 'store':
                    candidate['store_id'] = str(uuid4())
                elif fault == 'created':
                    candidate['created_at'] = '2026-02-01T00:00:00+00:00'
                elif fault == 'history':
                    candidate['credential_rotation_history'] = []
                else:
                    del candidate['credential_rotation_history']
                with self.assertRaises(LiveTradingSafetyError):
                    self.replace(candidate, result)
                self.assertEqual(result, self.read())

    def test_projection_omission_addition_and_wrong_owner_fail_closed(self):
        self.payload['intents'], _ = profiles.synthetic_opo_records(
            6, original_stops=1, residual_stops=1, attempt_depth=1, residual_depth=1)
        snapshot = self.create()
        saved = self.path.read_bytes()
        faults = ('active-omit', 'active-add', 'unresolved-add', 'reserved-omit', 'reserved-owner')
        for fault in faults:
            with self.subTest(fault=fault):
                self.path.write_bytes(saved)
                with closing(sqlite3.connect(self.path)) as connection, connection:
                    if fault == 'active-omit':
                        connection.execute('DELETE FROM active_projection WHERE client_id=?', (snapshot.active_ids[0],))
                    elif fault == 'active-add':
                        connection.execute('INSERT INTO active_projection VALUES (?)', ('syn-list-00000005',))
                    elif fault == 'unresolved-add':
                        connection.execute('INSERT INTO unresolved_projection VALUES (?)', ('syn-list-00000005',))
                    else:
                        action = 'delete' if fault == 'reserved-omit' else 'update'
                        trigger = 'immutable_reserved_ids_' + action
                        connection.execute('DROP TRIGGER ' + trigger)
                        if fault == 'reserved-omit':
                            connection.execute('DELETE FROM reserved_ids WHERE reserved_id=?',
                                               ('syn-rearm-00000001-000',))
                        else:
                            connection.execute('UPDATE reserved_ids SET owner_id=? WHERE reserved_id=?',
                                               ('syn-list-00000005', 'syn-rearm-00000001-000'))
                        connection.execute(indexed._DDL[trigger])
                with self.assertRaisesRegex(LiveTradingSafetyError, 'complete projections changed'):
                    self.read()
        self.path.write_bytes(saved)
        self.assertEqual(snapshot, self.read())

    def test_missing_unresolved_membership_and_current_journal_metadata_drift_reject(self):
        snapshot = self.create()
        saved = self.path.read_bytes()
        for fault in ('unresolved', 'row', 'row-digest', 'header', 'head', 'schema'):
            with self.subTest(fault=fault):
                self.path.write_bytes(saved)
                with closing(sqlite3.connect(self.path)) as connection, connection:
                    if fault == 'unresolved':
                        connection.execute('DELETE FROM unresolved_projection WHERE client_id=?', (snapshot.unresolved_ids[0],))
                    elif fault == 'row':
                        key = snapshot.record_receipts[0].client_id
                        row = snapshot.record(key)
                        row['updated_at'] = '2026-02-01T00:00:00+00:00'
                        connection.execute('UPDATE current_records SET record=? WHERE client_id=?',
                                           (indexed._canonical(row), key))
                    elif fault == 'row-digest':
                        connection.execute("UPDATE current_records SET digest='wrong'")
                    elif fault == 'header':
                        connection.execute("UPDATE store_state SET metadata='{}'")
                    elif fault == 'head':
                        connection.execute("UPDATE store_state SET head='wrong'")
                    else:
                        connection.execute('DROP TRIGGER immutable_journal_records_delete')
                with self.assertRaises(LiveTradingSafetyError):
                    self.read()
        self.path.write_bytes(saved)
        self.assertEqual(snapshot, self.read())

    def test_immutable_journal_trigger_and_recomputed_chain_detect_corruption(self):
        snapshot = self.create()
        candidate = snapshot.payload
        candidate['offline_step'] = 2
        current = self.replace(candidate, snapshot)
        with closing(sqlite3.connect(self.path)) as connection, connection:
            for table in ('journal_records', 'journal_commits', 'reserved_ids'):
                with self.subTest(table=table), self.assertRaises(sqlite3.IntegrityError):
                    connection.execute('DELETE FROM ' + table)
            connection.execute('DROP TRIGGER immutable_journal_commits_update')
            connection.execute("UPDATE journal_commits SET previous='forged' WHERE seq=2")
            connection.execute(indexed._DDL['immutable_journal_commits_update'])
        with self.assertRaisesRegex(LiveTradingSafetyError, 'journal sequence changed'):
            self.read()
        self.assertEqual(2, current.receipt.revision)

    def test_mid_write_failure_rolls_back_rows_journal_and_all_projections(self):
        snapshot = self.create()
        candidate = snapshot.payload
        row = next(iter(candidate['intents'].values()))
        row['updated_at'] = '2026-03-01T00:00:00+00:00'
        original = indexed._sql
        calls = []
        def fail_after_journal(connection, deadline, query, parameters=()):
            calls.append(query)
            if query.startswith('DELETE FROM active_projection'):
                raise OSError('synthetic interrupted storage')
            return original(connection, deadline, query, parameters)
        with patch.object(indexed, '_sql', side_effect=fail_after_journal), self.assertRaises(LiveTradingSafetyError):
            self.replace(candidate, snapshot)
        self.assertTrue(any(query.startswith('INSERT INTO journal_records') for query in calls))
        self.assertEqual(snapshot, self.read())

    def test_new_file_failure_cleans_only_new_target_and_never_overwrites_existing(self):
        with patch.object(indexed, '_append', side_effect=OSError('synthetic failure')):
            with self.assertRaises(LiveTradingSafetyError):
                self.create()
        self.assertFalse(self.path.exists())
        snapshot = self.create()
        before = self.path.read_bytes()
        with self.assertRaises(LiveTradingSafetyError):
            self.create()
        self.assertEqual(before, self.path.read_bytes())
        self.assertEqual(snapshot, self.read())

    def test_binding_backend_store_and_logical_path_mismatch_reject(self):
        snapshot = self.create()
        for kwargs in ({'expected_store_id': str(uuid4())}, {'expected_backend_id': str(uuid4())}):
            with self.subTest(kwargs=kwargs), self.assertRaises(LiveTradingSafetyError):
                self.read(**kwargs)
        with locks.ledger_transaction(self.logical):
            for logical, binding in ((self.logical.with_name('wrong.json'), self.binding),
                                     (self.logical, {**self.binding, 'environment': 'testnet'})):
                with self.subTest(logical=logical, binding=binding), self.assertRaises(LiveTradingSafetyError):
                    indexed.read_indexed_snapshot(self.path, logical_path=logical, rules=RULES,
                                                  expected_binding=binding, deadline=locks.current_ledger_deadline())
        self.assertEqual(snapshot, self.read())

    def test_requires_actual_transaction_and_cannot_extend_acquisition_deadline(self):
        snapshot = self.create()
        with self.assertRaisesRegex(LiveTradingSafetyError, 'transaction is required'):
            indexed.read_indexed_snapshot(self.path, logical_path=self.logical, rules=RULES,
                                          expected_binding=self.binding, deadline=time.monotonic()+5)
        with locks.ledger_transaction(self.logical):
            for value in (locks.current_ledger_deadline()+0.01, float('inf'), float('nan'), True):
                with self.subTest(value=value), self.assertRaises(LiveTradingSafetyError):
                    indexed.read_indexed_snapshot(self.path, logical_path=self.logical, rules=RULES,
                                                  expected_binding=self.binding, deadline=value)
            # CPU-only offline work may consume deadline: subsequent SQL gets zero waiting allowance.
            self.assertEqual(snapshot, indexed.read_indexed_snapshot(
                self.path, logical_path=self.logical, rules=RULES, expected_binding=self.binding,
                deadline=time.monotonic()-1))

    def test_database_busy_wait_consumes_original_remaining_deadline(self):
        self.create()
        blocker = sqlite3.connect(self.path, isolation_level=None)
        self.addCleanup(blocker.close)
        blocker.execute('BEGIN EXCLUSIVE')
        with locks.ledger_transaction(self.logical):
            deadline = locks.current_ledger_deadline()
            time.sleep(max(0, deadline-time.monotonic()-0.16))
            started = time.monotonic()
            with self.assertRaisesRegex(LiveTradingSafetyError, 'busy'):
                indexed.read_indexed_snapshot(self.path, logical_path=self.logical, rules=RULES,
                                              expected_binding=self.binding, deadline=deadline)
            waited = time.monotonic()-started
        blocker.execute('ROLLBACK')
        self.assertLess(waited, 0.75, 'SQLite must not receive a fresh five-second wait')
        self.assertGreater(waited, 0.04)
        self.read()

    def test_delete_extra_profile_and_wal_mode_rejection(self):
        self.create()
        with locks.ledger_transaction(self.logical), indexed._connection(self.path, self.logical, locks.current_ledger_deadline()) as connection:
            self.assertEqual('delete', connection.execute('PRAGMA journal_mode').fetchone()[0])
            self.assertEqual(3, connection.execute('PRAGMA synchronous').fetchone()[0])
        with closing(sqlite3.connect(self.path)) as connection, connection:
            self.assertEqual('wal', connection.execute('PRAGMA journal_mode=WAL').fetchone()[0])
        with self.assertRaisesRegex(LiveTradingSafetyError, 'DELETE|WAL'):
            self.read()

    def test_unsupported_payload_and_failed_import_have_no_published_database(self):
        for value in ({'format_version': 1, 'intents': {}}, None,
                      {**self.payload, 'unsafe': float('nan')}, {**self.payload, 'unsafe': object()}):
            with self.subTest(value=type(value).__name__), self.assertRaises(LiveTradingSafetyError):
                self.create(value)
            self.assertFalse(self.path.exists())


    def test_unrelated_logical_lock_cannot_authorize_database_access(self):
        self.create()
        with locks.ledger_transaction(self.root / 'unrelated.json'):
            with self.assertRaisesRegex(LiveTradingSafetyError, 'transaction|lock'):
                indexed.read_indexed_snapshot(self.path, logical_path=self.logical, rules=RULES,
                                              expected_binding=self.binding, deadline=locks.current_ledger_deadline())

    def test_actual_process_loss_before_commit_rolls_back_and_releases_logical_lock(self):
        snapshot = self.create()
        context = multiprocessing.get_context('spawn')
        ready, release = context.Event(), context.Event()
        process = context.Process(target=_interrupted_commit,
                                  args=(str(self.path), str(self.logical), ready, release))
        process.start()
        try:
            self.assertTrue(ready.wait(timeout=15), 'Actual child never reached pre-COMMIT barrier')
            process.terminate()
            process.join(timeout=10)
            self.assertFalse(process.is_alive())
            self.assertNotEqual(0, process.exitcode)
        finally:
            # A killed child may own the Event condition mutex; never reuse that IPC lock.
            if process.is_alive():
                process.terminate()
                process.join(timeout=10)
            process.close()
        self.assertEqual(snapshot, self.read())
        with closing(sqlite3.connect(self.path)) as connection:
            self.assertEqual(1, connection.execute('SELECT COUNT(*) FROM journal_commits').fetchone()[0])
            self.assertNotIn('crash_candidate', self.read().payload)

    def test_missing_tail_and_malformed_journal_json_fail_closed(self):
        snapshot = self.create()
        candidate = snapshot.payload
        candidate['second_commit'] = True
        self.replace(candidate, snapshot)
        saved = self.path.read_bytes()
        for fault in ('tail', 'duplicate', 'nonfinite', 'noncanonical'):
            with self.subTest(fault=fault):
                self.path.write_bytes(saved)
                with closing(sqlite3.connect(self.path)) as connection, connection:
                    if fault == 'tail':
                        connection.execute('DROP TRIGGER immutable_journal_commits_delete')
                        connection.execute('DELETE FROM journal_commits WHERE seq=2')
                        connection.execute(indexed._DDL['immutable_journal_commits_delete'])
                    else:
                        trigger = 'immutable_journal_records_update'
                        connection.execute('DROP TRIGGER ' + trigger)
                        raw = {'duplicate': '{"state":"pending","state":"unknown"}',
                               'nonfinite': '{"state":NaN}', 'noncanonical': '{ "state": "pending" }'}[fault]
                        connection.execute('UPDATE journal_records SET record=? WHERE client_id=?',
                                           (raw, snapshot.record_receipts[0].client_id))
                        connection.execute(indexed._DDL[trigger])
                with self.assertRaises(LiveTradingSafetyError):
                    self.read()

    def test_missing_directory_and_hardlinked_database_are_not_opened_or_created(self):
        self.create()
        missing = self.root / 'missing.sqlite3'
        with locks.ledger_transaction(self.logical), self.assertRaises(LiveTradingSafetyError):
            indexed.read_indexed_snapshot(missing, logical_path=self.logical, rules=RULES,
                                          expected_binding=self.binding, deadline=locks.current_ledger_deadline())
        self.assertFalse(missing.exists())
        with locks.ledger_transaction(self.logical), self.assertRaises(LiveTradingSafetyError):
            indexed.read_indexed_snapshot(self.root, logical_path=self.logical, rules=RULES,
                                          expected_binding=self.binding, deadline=locks.current_ledger_deadline())
        import os
        alias = self.root / 'hardlinked.sqlite3'
        os.link(self.path, alias)
        with self.assertRaisesRegex(LiveTradingSafetyError, 'unique regular'):
            self.read()
        alias.unlink()
        self.read()


    def test_nested_opaque_history_containers_cannot_disappear_or_change_type(self):
        key = next(iter(self.payload['intents']))
        nested = {'container': {'audit_history': [{'version': 1, 'synthetic': True}]}}
        self.payload['opaque_metadata'] = deepcopy(nested)
        self.payload['intents'][key]['opaque_record'] = deepcopy(nested)
        snapshot = self.create()
        for location in ('metadata', 'record'):
            for mutation in ('remove', 'none', 'list', 'rewrite-typed-value'):
                with self.subTest(location=location, mutation=mutation):
                    candidate = snapshot.payload
                    target = candidate if location == 'metadata' else candidate['intents'][key]
                    name = 'opaque_metadata' if location == 'metadata' else 'opaque_record'
                    if mutation == 'remove':
                        del target[name]['container']
                    elif mutation == 'none':
                        target[name]['container'] = None
                    elif mutation == 'list':
                        target[name]['container'] = []
                    else:
                        target[name]['container']['audit_history'][0]['synthetic'] = 1
                    runtime.validate_order_intent_ledger(candidate, expected_binding=self.binding)
                    with self.assertRaisesRegex(LiveTradingSafetyError, 'history'):
                        self.replace(candidate, snapshot)
                    self.assertEqual(snapshot, self.read())

    def test_binding_transition_requires_explicit_authority_and_anchored_rotation(self):
        snapshot = self.create()
        for fault in ('no-history', 'wrong-origin', 'environment', 'exchange'):
            with self.subTest(fault=fault):
                candidate = snapshot.payload
                next_binding = {**self.binding, 'credential_fingerprint': 'e' * 64}
                history = [{'previous_fingerprint': self.binding['credential_fingerprint'],
                    'new_fingerprint': 'e' * 64, 'rotated_at': fixtures.FIXED_TIME,
                    'reconciliation_reference': 'synthetic transition'}]
                if fault == 'wrong-origin':
                    history[0]['previous_fingerprint'] = 'f' * 64
                elif fault == 'environment':
                    next_binding['environment'] = 'testnet'
                elif fault == 'exchange':
                    next_binding['exchange'] = 'other'
                candidate['binding'] = next_binding
                if fault != 'no-history':
                    candidate['credential_rotation_history'] = history
                # Valid current headers alone do not prove transition authority/continuity.
                if fault != 'exchange':
                    runtime.validate_order_intent_ledger(candidate, expected_binding=next_binding)
                with self.assertRaises(LiveTradingSafetyError):
                    self.replace(candidate, snapshot, expected_new_binding=next_binding)
                self.assertEqual(snapshot, self.read())
        candidate = snapshot.payload
        candidate['binding'] = {**self.binding, 'credential_fingerprint': 'e' * 64}
        candidate['credential_rotation_history'] = [{'previous_fingerprint': self.binding['credential_fingerprint'],
            'new_fingerprint': 'e' * 64, 'rotated_at': fixtures.FIXED_TIME,
            'reconciliation_reference': 'synthetic transition'}]
        with self.assertRaises(LiveTradingSafetyError):
            self.replace(candidate, snapshot)
        self.assertEqual(snapshot, self.read())


    def test_history_paths_inside_nonhistory_lists_and_opaque_scalars_are_preserved(self):
        key = next(iter(self.payload['intents']))
        nested = [{'container': {'audit_history': [{'synthetic': True}]}}, {'ordinary_values': [1, 2]}]
        self.payload['opaque_metadata'] = deepcopy(nested)
        self.payload['intents'][key]['opaque_record'] = deepcopy(nested)
        self.payload['opaque_history'] = 'synthetic reference'
        snapshot = self.create()
        for location in ('metadata', 'record'):
            for mutation in ('remove', 'container-none', 'typed-rewrite'):
                with self.subTest(location=location, mutation=mutation):
                    candidate = snapshot.payload
                    target = candidate if location == 'metadata' else candidate['intents'][key]
                    name = 'opaque_metadata' if location == 'metadata' else 'opaque_record'
                    if mutation == 'remove':
                        target[name].pop(0)
                    elif mutation == 'container-none':
                        target[name][0] = None
                    else:
                        target[name][0]['container']['audit_history'][0]['synthetic'] = 1
                    runtime.validate_order_intent_ledger(candidate, expected_binding=self.binding)
                    with self.assertRaisesRegex(LiveTradingSafetyError, 'history'):
                        self.replace(candidate, snapshot)
                    self.assertEqual(snapshot, self.read())
        candidate = snapshot.payload
        candidate['operator_annotation'] = 'unchanged opaque history remains accepted'
        candidate['opaque_metadata'][1]['ordinary_values'] = []
        current = self.replace(candidate, snapshot)
        self.assertEqual('synthetic reference', current.payload['opaque_history'])
        candidate = current.payload
        candidate['opaque_history'] = 'rewritten reference'
        runtime.validate_order_intent_ledger(candidate)
        with self.assertRaisesRegex(LiveTradingSafetyError, 'opaque history'):
            self.replace(candidate, current)
        self.assertEqual(current, self.read())


if __name__ == '__main__':
    unittest.main()
