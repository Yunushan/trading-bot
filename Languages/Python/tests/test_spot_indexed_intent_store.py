"""Offline complete-history, CAS and projection integrity for the indexed foundation."""
from __future__ import annotations

from contextlib import closing
from copy import deepcopy
import math
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


class _CleanupFaultConnection(sqlite3.Connection):
    """Real pager; rollback/close faults occur after the real cleanup call."""

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.cleanup_calls = []
        self.cleanup_failures = {}
        self.busy_timeouts = []

    def execute(self, query, parameters=()):
        if query.startswith('PRAGMA busy_timeout='):
            self.busy_timeouts.append(int(query.split('=', 1)[1]))
            failure = self.cleanup_failures.get('busy_timeout')
            if failure is not None:
                raise failure
        return super().execute(query, parameters)

    def rollback(self):
        self.cleanup_calls.append('rollback')
        super().rollback()
        failure = self.cleanup_failures.get('rollback')
        if failure is not None:
            raise failure

    def close(self):
        self.cleanup_calls.append('close')
        super().close()
        failure = self.cleanup_failures.get('close')
        if failure is not None:
            raise failure


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

    def assert_cleanup_failure(self, *, primary=None, rollback=True, close=True,
                               rollback_interruption=None, expire_on_error=False, fail_busy_allowance=False):
        snapshot = self.create()
        before = self.path.read_bytes()
        candidate = snapshot.payload
        key = next(iter(candidate['intents']))
        candidate['intents'][key]['operator_note'] = 'must rollback complete history and projections'
        candidate['cleanup_candidate'] = 'must not return an adopted result'
        primary = RuntimeError('synthetic primary ordinary failure') if primary is None else primary
        failures = {}
        if rollback:
            failures['rollback'] = (rollback_interruption if rollback_interruption is not None
                                    else sqlite3.OperationalError('synthetic rollback I/O failure'))
        if close:
            failures['close'] = OSError('synthetic close I/O failure')
        connect, original_sql, monotonic = sqlite3.connect, indexed._sql, time.monotonic
        connections, failed, deadline_seen = [], [], []
        def real_connection(*args, **kwargs):
            kwargs['factory'] = _CleanupFaultConnection
            connection = connect(*args, **kwargs)
            connection.cleanup_failures = failures
            connections.append(connection)
            return connection
        def interrupted(connection, deadline, query, parameters=()):
            if query.startswith('INSERT INTO store_state'):
                deadline_seen.append(deadline)
                failed.append(True)
                if fail_busy_allowance:
                    failures['busy_timeout'] = sqlite3.OperationalError('synthetic cleanup busy allowance failure')
                raise primary
            return original_sql(connection, deadline, query, parameters)
        def cleanup_clock():
            return deadline_seen[0] + 1 if expire_on_error and failed else monotonic()
        interruption = primary if not isinstance(primary, Exception) else rollback_interruption
        expected_type = type(interruption) if interruption is not None else LiveTradingSafetyError
        with patch.object(indexed.sqlite3, 'connect', side_effect=real_connection), \
                patch.object(indexed, '_sql', side_effect=interrupted), \
                patch.object(indexed.time, 'monotonic', side_effect=cleanup_clock):
            with self.assertRaises(expected_type) as caught:
                self.replace(candidate, snapshot)
        self.assertEqual(1, len(connections))
        connection = connections[0]
        if interruption is not None:
            self.assertIs(interruption, caught.exception)
        else:
            self.assertTrue(str(caught.exception).startswith('Indexed intent storage is unavailable or busy;'))
        cause = (failures.get('close') or primary) if rollback_interruption is not None else (
            failures.get('close') or failures.get('rollback') or failures.get('busy_timeout') or primary)
        self.assertIs(cause, caught.exception.__cause__)
        if rollback and close:
            self.assertIs(primary if rollback_interruption is not None else failures['rollback'], cause.__cause__)
        if fail_busy_allowance:
            self.assertIs(primary, cause.__context__)
        expected_cleanup = ['close'] if fail_busy_allowance else ['rollback', 'close']
        self.assertEqual(expected_cleanup, connection.cleanup_calls)
        if expire_on_error:
            self.assertEqual(0, connection.busy_timeouts[-1], 'Cleanup cannot reuse an expired busy allowance')
        with self.assertRaises(sqlite3.ProgrammingError):
            connection.execute('SELECT 1')
        self.assertEqual(before, self.path.read_bytes())
        self.assertEqual(snapshot, self.read(), 'Every complete record, head and projection must remain unchanged')
        self.assertEqual(expected_cleanup, connection.cleanup_calls)

    def cold_replay_history(self):
        self.payload['intents'], _ = profiles.synthetic_opo_records(
            6, original_stops=1, residual_stops=1, attempt_depth=2, residual_depth=2)
        self.payload['cold_metadata_revision'] = 0
        snapshots = [self.create()]
        for revision in (1, 2):
            candidate = snapshots[-1].payload
            candidate['cold_metadata_revision'] = revision
            snapshots.append(self.replace(candidate, snapshots[-1]))
        candidate = snapshots[-1].payload
        candidate['intents']['syn-list-00000001']['operator_note'] = 'a later complete record revision'
        snapshots.append(self.replace(candidate, snapshots[-1]))
        return snapshots

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

    def test_primary_keyboard_interrupt_survives_full_store_cleanup_failures(self):
        self.assert_cleanup_failure(primary=KeyboardInterrupt('synthetic full-store cancellation'))

    def test_primary_system_exit_survives_full_store_cleanup_failures(self):
        self.assert_cleanup_failure(primary=SystemExit(73))

    def test_rollback_cancellation_survives_full_store_close_failure_with_all_causes(self):
        self.assert_cleanup_failure(rollback_interruption=KeyboardInterrupt('synthetic rollback cancellation'))

    def test_full_store_expired_cleanup_uses_zero_remaining_busy_wait(self):
        self.assert_cleanup_failure(close=False, expire_on_error=True)

    def test_full_store_cleanup_busy_allowance_failure_skips_rollback_and_closes_once(self):
        self.assert_cleanup_failure(rollback=False, close=False, fail_busy_allowance=True)

    def test_full_store_ordinary_cleanup_failures_keep_primary_and_both_cleanup_causes(self):
        self.assert_cleanup_failure()

    def test_cold_replay_checks_every_complete_revision_without_discarded_output_parses(self):
        snapshots = self.cold_replay_history()
        expected = [snapshot.payload for snapshot in snapshots]
        observed, retained, full_parses = [], [], []
        parse = indexed._parse_json_dict
        def inspected(payload, *, expected_binding=None):
            observed.append((deepcopy(payload), deepcopy(expected_binding)))
            retained.append(payload)
            return runtime.validate_order_intent_ledger(payload, expected_binding=expected_binding)
        def counted(raw):
            # This fixture has no intents key inside an individual record.
            if '"intents":{' in raw:
                full_parses.append(len(raw))
            return parse(raw)
        rules = indexed.IndexedIntentRules(inspected, RULES.is_unresolved,
                                          RULES.has_active_protection, RULES.used_client_ids)
        with locks.ledger_transaction(self.logical), patch.object(indexed, '_parse_json_dict', side_effect=counted):
            actual = indexed.read_indexed_snapshot(
                self.path, logical_path=self.logical, rules=rules, expected_binding=self.binding,
                deadline=locks.current_ledger_deadline())
        self.assertEqual(snapshots[-1], actual)
        self.assertEqual(expected + [expected[-1]], [payload for payload, _ in observed])
        self.assertEqual([None] * len(snapshots) + [self.binding], [binding for _, binding in observed])
        self.assertEqual(len(snapshots) + 2, len(full_parses),
                         'One strict input parse per historical revision; final validation still detaches its output')
        self.assertTrue(all(len(payload['intents']) == 6 for payload, _ in observed))
        retained_before = deepcopy(retained)
        result = actual.payload
        result['binding'].clear()
        result['intents'].clear()
        self.assertEqual(retained_before, retained)
        retained[0]['binding'].clear()
        retained[-1]['intents']['syn-list-00000001']['strategy_exit_history'].clear()
        self.assertEqual(expected[-1], actual.payload)
        self.assertEqual(expected[1:], retained[1:-1])
        self.assertEqual(actual, self.read())

    def test_cold_replay_rejects_earlier_callback_mutation_with_a_valid_final_revision(self):
        snapshots = self.cold_replay_history()
        before = self.path.read_bytes()
        for fault in ('changed-input-pristine-output', 'changed-output', 'callback-exception'):
            with self.subTest(fault=fault):
                calls = []
                failure = RuntimeError('synthetic earlier full-validator failure')
                def inspected(payload, *, expected_binding=None):
                    checked = runtime.validate_order_intent_ledger(payload, expected_binding=expected_binding)
                    calls.append(deepcopy(payload))
                    if len(calls) != 2:
                        return checked
                    pristine = deepcopy(payload)
                    if fault == 'callback-exception':
                        raise failure
                    if fault == 'changed-input-pristine-output':
                        payload['intents']['syn-list-00000001']['operator_note'] = 'mutated detached history'
                        return pristine
                    pristine['operator_note'] = 'changed validator result'
                    return pristine
                rules = indexed.IndexedIntentRules(inspected, RULES.is_unresolved,
                                                  RULES.has_active_protection, RULES.used_client_ids)
                expected_error = RuntimeError if fault == 'callback-exception' else LiveTradingSafetyError
                with locks.ledger_transaction(self.logical), self.assertRaises(expected_error) as caught:
                    indexed.read_indexed_snapshot(
                        self.path, logical_path=self.logical, rules=rules, expected_binding=self.binding,
                        deadline=locks.current_ledger_deadline())
                if fault == 'callback-exception':
                    self.assertIs(failure, caught.exception)
                else:
                    self.assertIn('requires unchanged validated v2 data', str(caught.exception))
                self.assertEqual(2, len(calls), 'A later valid state cannot replace earlier complete validation')
                self.assertEqual(snapshots[1].payload, calls[1])
                self.assertEqual(before, self.path.read_bytes())
                self.assertEqual(snapshots[-1], self.read())

    def test_cold_replay_rejects_semantically_invalid_earlier_history_with_a_valid_tail(self):
        bad = deepcopy(self.payload)
        key = next(iter(bad['intents']))
        bad['intents'][key]['requires_close_confirmation'] = 1
        def author_injected_fault(payload, *, expected_binding=None):
            # Fault authoring only: keep every other owned rule and store commitment.
            repaired = deepcopy(payload)
            for record in repaired['intents'].values():
                if type(record.get('requires_close_confirmation')) is int:
                    record['requires_close_confirmation'] = True
            runtime.validate_order_intent_ledger(repaired, expected_binding=expected_binding)
            return payload
        authoring = indexed.IndexedIntentRules(author_injected_fault, RULES.is_unresolved,
                                              RULES.has_active_protection, RULES.used_client_ids)
        with locks.ledger_transaction(self.logical):
            first = indexed.create_indexed_store(
                self.path, bad, logical_path=self.logical, rules=authoring, expected_binding=self.binding,
                deadline=locks.current_ledger_deadline())
            valid_tail = first.payload
            valid_tail['intents'][key]['requires_close_confirmation'] = True
            latest = indexed.replace_indexed_snapshot(
                self.path, valid_tail, expected=first, rules=authoring, expected_binding=self.binding,
                deadline=locks.current_ledger_deadline())
        runtime.validate_order_intent_ledger(latest.payload, expected_binding=self.binding)
        before = self.path.read_bytes()
        with self.assertRaisesRegex(LiveTradingSafetyError, 'contains an invalid record'):
            self.read()
        self.assertEqual(before, self.path.read_bytes())

    def test_cold_replay_keeps_strict_json_for_an_earlier_row_with_a_valid_tail(self):
        snapshot = self.cold_replay_history()[-1]
        key = 'syn-list-00000001'
        with closing(sqlite3.connect(self.path)) as connection, connection:
            raw = connection.execute('SELECT record FROM journal_records WHERE seq=1 AND client_id=?', (key,)).fetchone()[0]
            connection.execute('DROP TRIGGER immutable_journal_records_update')
            connection.execute('UPDATE journal_records SET record=? WHERE seq=1 AND client_id=?', (' ' + raw, key))
            connection.execute(indexed._DDL['immutable_journal_records_update'])
            current = connection.execute('SELECT record FROM current_records WHERE client_id=?', (key,)).fetchone()[0]
        self.assertEqual(snapshot.record(key), indexed._decode(current))
        runtime.validate_order_intent_ledger(snapshot.payload, expected_binding=self.binding)
        before = self.path.read_bytes()
        with self.assertRaisesRegex(LiveTradingSafetyError, 'contains noncanonical JSON'):
            self.read()
        self.assertEqual(before, self.path.read_bytes())


    def test_cold_replay_preserves_canonical_stored_metadata_and_record_extensions(self):
        extension = {'unicode': {'İ': '雪\u0000', 'surrogate': '\ud800'},
                     'negative_zero': -0.0, 'typed_scalars': [1, True, None, 0.25]}
        self.payload['canonical_extension'] = deepcopy(extension)
        key = next(iter(self.payload['intents']))
        self.payload['intents'][key]['canonical_extension'] = deepcopy(extension)
        first = self.create()
        candidate = first.payload
        candidate['canonical_step'] = 1
        candidate['intents'][key]['operator_note'] = 'a complete later record revision'
        latest = self.replace(candidate, first)
        observed = []
        def complete_validation(payload, *, expected_binding=None):
            observed.append((deepcopy(payload), deepcopy(expected_binding)))
            return runtime.validate_order_intent_ledger(payload, expected_binding=expected_binding)
        rules = indexed.IndexedIntentRules(complete_validation, RULES.is_unresolved,
                                          RULES.has_active_protection, RULES.used_client_ids)
        before = self.path.read_bytes()
        with locks.ledger_transaction(self.logical):
            actual = indexed.read_indexed_snapshot(
                self.path, logical_path=self.logical, rules=rules, expected_binding=self.binding,
                deadline=locks.current_ledger_deadline())
        self.assertEqual(latest, actual)
        self.assertEqual([first.payload, latest.payload, latest.payload], [value for value, _ in observed])
        self.assertEqual([None, None, self.binding], [binding for _, binding in observed])
        self.assertTrue(all(len(value['intents']) == 6 for value, _ in observed))
        self.assertEqual(before, self.path.read_bytes())
        with closing(sqlite3.connect(self.path)) as connection:
            metadata_rows = connection.execute('SELECT metadata,metadata_digest FROM journal_commits ORDER BY seq').fetchall()
            record_rows = connection.execute('SELECT record,digest FROM journal_records WHERE client_id=? ORDER BY seq', (key,)).fetchall()
        self.assertEqual(2, len(metadata_rows))
        self.assertEqual(2, len(record_rows))
        for label, rows in (('metadata', metadata_rows), ('record', record_rows)):
            for revision, (raw, commitment) in enumerate(rows, 1):
                with self.subTest(stored=label, revision=revision):
                    decoded = indexed._decode(raw)
                    self.assertEqual(indexed._digest(decoded), commitment)
                    self.assertEqual(indexed._canonical(extension), indexed._canonical(decoded['canonical_extension']))
                    self.assertEqual(-1.0, math.copysign(1.0, decoded['canonical_extension']['negative_zero']))
                    self.assertIn(r'\u96ea', raw)
                    self.assertIn(r'\ud800', raw)
                    self.assertEqual(int, type(decoded['canonical_extension']['typed_scalars'][0]))
                    self.assertEqual(bool, type(decoded['canonical_extension']['typed_scalars'][1]))

    def test_cold_replay_rejects_strict_earlier_metadata_with_a_valid_final_tail(self):
        latest = self.cold_replay_history()[-1]
        runtime.validate_order_intent_ledger(latest.payload, expected_binding=self.binding)
        saved = self.path.read_bytes()
        with closing(sqlite3.connect(self.path)) as connection:
            original = connection.execute('SELECT metadata FROM journal_commits WHERE seq=1').fetchone()[0]
        unicode_raw = indexed._canonical({**indexed._decode(original), 'unicode_extension': '雪'})
        faults = (
            ('duplicate', original.replace('"format_version":2', '"format_version":2,"format_version":2', 1), 'duplicate JSON keys'),
            ('nonfinite', original[:-1] + ',"fault":NaN}', 'nonfinite JSON'),
            ('overflow', original[:-1] + ',"fault":1e400}', 'unsupported data'),
            ('whitespace', ' ' + original, 'noncanonical JSON'),
            ('escaped-key', original.replace('"binding"', r'"\u0062inding"', 1), 'noncanonical JSON'),
            ('literal-unicode', unicode_raw.replace(r'\u96ea', '雪'), 'noncanonical JSON'),
        )
        for fault, raw, reason in faults:
            with self.subTest(fault=fault):
                self.path.write_bytes(saved)
                with closing(sqlite3.connect(self.path)) as connection, connection:
                    connection.execute('DROP TRIGGER immutable_journal_commits_update')
                    connection.execute('UPDATE journal_commits SET metadata=? WHERE seq=1', (raw,))
                    connection.execute(indexed._DDL['immutable_journal_commits_update'])
                    current = connection.execute('SELECT metadata FROM store_state').fetchone()[0]
                expected_metadata = {name: value for name, value in latest.payload.items() if name != 'intents'}
                self.assertEqual(indexed._canonical(expected_metadata), current)
                before = self.path.read_bytes()
                calls = []
                def must_not_validate(payload, *, expected_binding=None):
                    calls.append(payload)
                    return runtime.validate_order_intent_ledger(payload, expected_binding=expected_binding)
                rules = indexed.IndexedIntentRules(must_not_validate, RULES.is_unresolved,
                                                  RULES.has_active_protection, RULES.used_client_ids)
                with locks.ledger_transaction(self.logical), self.assertRaisesRegex(LiveTradingSafetyError, reason):
                    indexed.read_indexed_snapshot(
                        self.path, logical_path=self.logical, rules=rules, expected_binding=self.binding,
                        deadline=locks.current_ledger_deadline())
                self.assertEqual([], calls, 'Strict first-revision metadata must reject before any full callback')
                self.assertEqual(before, self.path.read_bytes())
        self.path.write_bytes(saved)
        self.assertEqual(latest.payload, self.read().payload)

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


class IndexedValidatorSerializationTests(unittest.TestCase):
    def setUp(self):
        self.payload = fixtures.synthetic_payload(6, 2)
        self.binding = deepcopy(self.payload['binding'])
        self.enterContext(patch.object(socket.socket, 'connect', side_effect=AssertionError('No network')))
        self.enterContext(patch.object(socket, 'create_connection', side_effect=AssertionError('No network')))

    @staticmethod
    def original_validate(payload, rules, expected_binding):
        # Frozen six-serialization behavior before the constant-factor change.
        detached = indexed._decode(indexed._canonical(payload))
        original = indexed._canonical(detached)
        checked = rules.validate_ledger(detached, expected_binding=expected_binding)
        if (indexed._canonical(checked) != original or indexed._canonical(detached) != original
                or checked.get('format_version') != 2):
            raise indexed._fail('requires unchanged validated v2 data')
        return indexed._decode(original)

    @staticmethod
    def rules(callback):
        return indexed.IndexedIntentRules(callback, RULES.is_unresolved,
                                          RULES.has_active_protection, RULES.used_client_ids)

    @staticmethod
    def outcome(implementation, payload, rules, binding):
        try:
            value = implementation(payload, rules, binding)
            return 'accepted', indexed._canonical(value)
        except (ValueError, TypeError, RuntimeError, AttributeError) as exc:
            chain = []
            while exc is not None:
                chain.append((type(exc).__name__, str(exc)))
                exc = exc.__cause__
            return 'rejected', chain

    def test_owned_validator_matches_original_for_complete_input_matrix(self):
        cases = [('ordinary', self.payload)]
        for label, value in (
            ('opaque', {'nested': [{'history': [None, True, 7, 2.5]}]}),
            ('numeric-single-key', {7: 'numeric keys become strings'}),
            ('numeric-noncanonical-order', {2: 'two', 10: 'ten'}),
            ('float-noncanonical-order', {2.0: 'two', 10.0: 'ten'}),
            ('unicode', {'İ': '雪\u0000', 'surrogate': '\ud800'}),
            ('negative-zero', -0.0),
            ('tuple', (1, {'nested': ('kept', False)})),
            ('large-int', 1 << 200),
            ('nan', float('nan')),
            ('positive-infinity', float('inf')),
            ('negative-infinity', float('-inf')),
            ('unsupported', object()),
        ):
            candidate = deepcopy(self.payload)
            candidate['opaque_extension'] = value
            cases.append((label, candidate))
        for label, field, value in (
            ('legacy', 'format_version', 1),
            ('float-format', 'format_version', 2.0),
            ('malformed-intents', 'intents', []),
            ('wrong-binding', 'binding', {**self.binding, 'credential_fingerprint': 'e' * 64}),
        ):
            candidate = deepcopy(self.payload)
            candidate[field] = value
            cases.append((label, candidate))
        candidate = deepcopy(self.payload)
        candidate['intents'][next(iter(candidate['intents']))]['state'] = 'invalid'
        cases.extend([('bad-record', candidate), ('top-list', []), ('top-scalar', 2)])
        for label, payload in cases:
            with self.subTest(case=label):
                observations = []
                for implementation in (self.original_validate, indexed._validate):
                    calls = []
                    def owned(detached, *, expected_binding=None):
                        calls.append(expected_binding is self.binding)
                        return runtime.validate_order_intent_ledger(detached, expected_binding=expected_binding)
                    result = self.outcome(implementation, deepcopy(payload), self.rules(owned), self.binding)
                    observations.append((result, calls))
                self.assertEqual(observations[0], observations[1])

    def test_callback_mutations_returns_and_exceptions_match_original(self):
        for mode in ('same', 'equal-copy', 'mutated-input-pristine-output',
                     'changed-output', 'mutated-input-and-output', 'raises', 'wrong-format'):
            with self.subTest(mode=mode):
                observations = []
                for implementation in (self.original_validate, indexed._validate):
                    payload = deepcopy(self.payload)
                    before = indexed._canonical(payload)
                    calls = []
                    def callback(detached, *, expected_binding=None):
                        calls.append(expected_binding is self.binding)
                        pristine = deepcopy(detached)
                        if mode == 'raises':
                            raise ValueError('synthetic callback failure')
                        if mode in ('mutated-input-pristine-output', 'mutated-input-and-output'):
                            detached['operator_annotation'] = 'callback changed its input'
                        if mode in ('changed-output', 'mutated-input-and-output'):
                            pristine['operator_annotation'] = 'callback changed its output'
                        if mode == 'wrong-format':
                            pristine['format_version'] = 1
                        if mode == 'same':
                            return detached
                        return pristine
                    result = self.outcome(implementation, payload, self.rules(callback), self.binding)
                    self.assertEqual(before, indexed._canonical(payload))
                    observations.append((result, calls))
                self.assertEqual(observations[0], observations[1])
                self.assertEqual([True], observations[1][1])
                expected = 'accepted' if mode in ('same', 'equal-copy') else 'rejected'
                self.assertEqual(expected, observations[1][0][0])

    def test_numeric_key_order_rejects_before_a_restoring_callback(self):
        for implementation in (self.original_validate, indexed._validate):
            with self.subTest(implementation=implementation.__name__):
                payload = deepcopy(self.payload)
                payload['opaque_extension'] = {2: 'two', 10: 'ten'}
                calls = []
                def restore_keys(detached, *, expected_binding=None):
                    calls.append(True)
                    detached['opaque_extension'] = {
                        int(key): value for key, value in detached['opaque_extension'].items()
                    }
                    return detached
                with self.assertRaisesRegex(LiveTradingSafetyError, 'noncanonical JSON'):
                    implementation(payload, self.rules(restore_keys), self.binding)
                self.assertEqual([], calls)

    def test_mapping_hooks_preserve_mutation_checks_and_error_precedence(self):
        for mode in ('checked-mutates-input', 'same-object-nested-hook', 'checked-hook-raises'):
            with self.subTest(mode=mode):
                observations = []
                for implementation in (self.original_validate, indexed._validate):
                    payload = deepcopy(self.payload)
                    payload['opaque_extension'] = {'value': 'original'}
                    before = indexed._canonical(payload)
                    events = []
                    def callback(detached, *, expected_binding=None):
                        events.append('callback')
                        self.assertIs(expected_binding, self.binding)
                        if mode == 'same-object-nested-hook':
                            class Nested(dict):
                                def items(self):
                                    events.append('nested-items')
                                    pairs = list(super().items())
                                    detached['late_mutation'] = 'after parent items were captured'
                                    return pairs
                            detached['opaque_extension'] = Nested(detached['opaque_extension'])
                            return detached
                        class Checked(dict):
                            def items(self):
                                events.append('checked-items')
                                if mode == 'checked-hook-raises':
                                    raise ValueError('synthetic checked serialization precedence')
                                detached['late_mutation'] = 'checked encoding changed input'
                                return super().items()
                            def get(self, key, default=None):
                                events.append('checked-get')
                                return super().get(key, default)
                        checked = Checked(deepcopy(detached))
                        if mode == 'checked-hook-raises':
                            detached['late_mutation'] = 'input already differs'
                        return checked
                    result = self.outcome(implementation, payload, self.rules(callback), self.binding)
                    self.assertEqual(before, indexed._canonical(payload))
                    observations.append((result, events))
                self.assertEqual(observations[0], observations[1])
                self.assertEqual('rejected', observations[1][0][0])
                if mode == 'same-object-nested-hook':
                    self.assertEqual(['callback', 'nested-items', 'nested-items'], observations[1][1])
                else:
                    self.assertEqual(['callback', 'checked-items'], observations[1][1])
                if mode == 'checked-hook-raises':
                    self.assertIn('contains unsupported data', observations[1][0][1][0][1])
                    self.assertEqual(('ValueError', 'synthetic checked serialization precedence'),
                                     observations[1][0][1][1])

    def test_caller_retained_callback_and_result_graphs_are_isolated(self):
        for implementation in (self.original_validate, indexed._validate):
            for separate in (False, True):
                with self.subTest(implementation=implementation.__name__, separate=separate):
                    caller = deepcopy(self.payload)
                    caller['opaque_extension'] = {'levels': [{'leaves': ['original']}]}
                    retained = {}
                    def callback(detached, *, expected_binding=None):
                        self.assertIs(expected_binding, self.binding)
                        retained['input'] = detached
                        retained['checked'] = deepcopy(detached) if separate else detached
                        return retained['checked']
                    result = implementation(caller, self.rules(callback), self.binding)
                    def leaves(value):
                        return value['opaque_extension']['levels'][0]['leaves']
                    self.assertIsNot(result, caller)
                    self.assertIsNot(result, retained['input'])
                    self.assertIsNot(result, retained['checked'])
                    leaves(result).append('result')
                    self.assertEqual(['original'], leaves(caller))
                    self.assertEqual(['original'], leaves(retained['input']))
                    self.assertEqual(['original'], leaves(retained['checked']))
                    leaves(retained['input']).append('input')
                    self.assertEqual(['original', 'result'], leaves(result))
                    self.assertEqual(['original'], leaves(caller))
                    if separate:
                        leaves(retained['checked']).append('checked')
                        self.assertEqual(['original', 'input'], leaves(retained['input']))
                    leaves(caller).append('caller')
                    self.assertEqual(['original', 'result'], leaves(result))
                    self.assertNotIn('caller', leaves(retained['input']))
                    self.assertNotIn('caller', leaves(retained['checked']))

    def test_owned_validation_uses_four_serializations_instead_of_six(self):
        for implementation, count in ((self.original_validate, 6), (indexed._validate, 4)):
            with self.subTest(implementation=implementation.__name__):
                with patch.object(indexed, '_canonical', wraps=indexed._canonical) as encoded:
                    result = implementation(deepcopy(self.payload), RULES, self.binding)
                    self.assertEqual(count, encoded.call_count)
                self.assertEqual(self.payload, result)

    def test_external_decode_keeps_strict_json_contract(self):
        for raw, reason in (
            ('{"a":1,"a":2}', 'duplicate JSON keys'),
            ('{"a":NaN}', 'nonfinite JSON'),
            ('{"a":Infinity}', 'nonfinite JSON'),
            ('{"a":-Infinity}', 'nonfinite JSON'),
            ('{ "a":1}', 'noncanonical JSON'),
            ('{"b":2,"a":1}', 'noncanonical JSON'),
            ('[]', 'noncanonical JSON'),
            ('2', 'noncanonical JSON'),
            ('{"a":}', 'malformed JSON'),
        ):
            with self.subTest(raw=raw), self.assertRaisesRegex(LiveTradingSafetyError, reason):
                indexed._decode(raw)
        raw = r'{"a":"\ud800","b":-0.0}'
        value = indexed._decode(raw)
        self.assertEqual(raw, indexed._canonical(value))
        self.assertEqual(-1.0, math.copysign(1.0, value['b']))


if __name__ == '__main__':
    unittest.main()
