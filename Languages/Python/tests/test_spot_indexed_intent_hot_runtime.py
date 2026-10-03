"""Owned runtime keeps native exclusion or complete post-write integrity proof."""
from __future__ import annotations

from contextlib import nullcontext
from copy import deepcopy
import json
import os
from pathlib import Path
import socket
import tempfile
import unittest
import weakref
from unittest.mock import patch
from uuid import uuid4

from app.integrations.exchanges.binance.orders import order_intent_runtime as runtime
from app.integrations.exchanges.binance.orders import order_intent_store as locks
from app.integrations.exchanges.binance.orders import order_intent_provisioning as provision
from app.integrations.exchanges.binance.orders import spot_execution_owner as owners
from app.integrations.exchanges.binance.orders import spot_indexed_intent_hot_runtime as hot
from app.integrations.exchanges.binance.orders import spot_indexed_intent_migration as migration
from app.integrations.exchanges.binance.orders import spot_indexed_intent_selective as selective
from app.integrations.exchanges.binance.orders import spot_indexed_intent_store as full
from app.integrations.exchanges.binance.orders.spot_opo_execution_runtime import place_spot_opo_entry
from app.settings.live_safety import LiveTradingSafetyError
from tools import benchmark_spot_intent_history as fixtures
from tools import spot_intent_capacity_profiles as profiles


class _OwnedWrapper:
    def __init__(self, records):
        self.__dict__.update(vars(fixtures.synthetic_owner()))
        self.api_secret = 'synthetic-hot-secret'
        self.client = profiles.SyntheticOpoVenue(records)

    def get_symbol_info_spot(self, symbol):
        return {'symbol': symbol, 'status': 'TRADING', 'quoteAsset': 'USDT',
                'isSpotTradingAllowed': True, 'otoAllowed': True, 'opoAllowed': True,
                'filters': [
                    {'filterType': 'PRICE_FILTER', 'minPrice': '0.01', 'maxPrice': '1000000', 'tickSize': '0.01'},
                    {'filterType': 'LOT_SIZE', 'minQty': '0.0001', 'maxQty': '9000', 'stepSize': '0.0001'},
                    {'filterType': 'MIN_NOTIONAL', 'minNotional': '5'}]}

    def _guard_live_order_submit(self, **_kwargs):
        # This fixture has only an in-memory transport; product guard unchanged.
        return None

    def _http_signed_spot(self, path):
        if path != '/v3/account':
            raise AssertionError('Only the in-memory synthetic account GET is available')
        return {'uid': fixtures.SYNTHETIC_UID, 'accountType': 'SPOT'}


runtime.bind_binance_order_intent_runtime(_OwnedWrapper)


class SpotIndexedIntentHotRuntimeTests(unittest.TestCase):
    def setUp(self):
        self.temporary = self.enterContext(tempfile.TemporaryDirectory(prefix='trading-bot-indexed-hot-'))
        self.root = Path(self.temporary)
        self.enterContext(patch.object(Path, 'home', return_value=self.root))
        self.enterContext(patch.object(socket.socket, 'connect', side_effect=AssertionError('No network')))
        self.enterContext(patch.object(socket, 'create_connection', side_effect=AssertionError('No network')))
        records, self.profile = profiles.synthetic_opo_records(
            12, original_stops=2, residual_stops=2, attempt_depth=2, residual_depth=2)
        self.wrapper = _OwnedWrapper(records)
        self.path = runtime._intent_path(self.wrapper)
        self.binding = runtime._intent_binding(self.wrapper)
        self.payload = fixtures.synthetic_payload(12, 2)
        self.payload['intents'] = records
        with owners.owner_administration_lock(self.path):
            with locks.ledger_transaction(self.path):
                locks.write_ledger(self.path, self.payload)
            owners.provision_owner_marker_locked(
                self.path, uid=fixtures.SYNTHETIC_UID, environment='live', store_id=self.payload['store_id'])
        migration.migrate_spot_indexed_intent_store(
            self.wrapper, acknowledgement=provision.PROVISION_ACK, reconciliation_reference='synthetic hot migration')
        provision.rearm_spot_execution_owner(
            self.wrapper, acknowledgement=provision.PROVISION_ACK, reconciliation_reference='synthetic hot rearm')
        self.owner = self.wrapper._ensure_spot_execution_owner()
        self.addCleanup(self.close_owner)
        self.manifest = self.path.read_bytes()
        self.request = profiles.request_for(700)

    def close_owner(self):
        selective.close_indexed_session(self.owner)
        self.owner.close()

    def session(self):
        return hot.indexed_session_for(self.wrapper, self.path)

    def read_full(self):
        with locks.ledger_transaction(self.path):
            return runtime._read_ledger(self.path, expected_binding=self.binding)

    def warm_only(self):
        self.enterContext(patch.object(runtime, '_read_ledger', side_effect=AssertionError('Warm path reread full ledger')))
        self.enterContext(patch.object(full, '_verified', side_effect=AssertionError('Warm path reverified full history')))

    def observe_owned_writes(self):
        with locks.ledger_transaction(self.path):
            session = self.session()
            self.initial_revision = session.receipt.revision
            self.full_checks_per_commit = 0 if session.native_guarded else 1
        self.enterContext(patch.object(runtime, '_read_ledger', side_effect=AssertionError('Warm path reread full ledger')))
        self.full_verifications = self.enterContext(patch.object(full, '_verified', wraps=full._verified))

    def assert_owned_writes_protected(self):
        with locks.ledger_transaction(self.path):
            committed_revisions = self.session().receipt.revision - self.initial_revision
        self.assertGreater(committed_revisions, 0)
        self.assertEqual(committed_revisions * self.full_checks_per_commit, self.full_verifications.call_count)

    def settle_pending(self, client_id):
        record = self.wrapper._get_order_intent_record(client_id)
        return runtime._update_order_intent_by_id(
            self.wrapper, client_id, state='rejected', expected_record=record,
            protection_state='none', exchange_order_list_id=71000, list_status='ALL_DONE',
            working_order_id=71001, pending_order_id=71002, working_status='EXPIRED', pending_status='CANCELED',
            working_executed_qty='0', pending_executed_qty='0', pending_original_qty='0')

    def test_actual_runtime_reads_are_selective_and_commits_retain_integrity_proof(self):
        self.observe_owned_writes()
        original_owner = self.wrapper._ensure_spot_execution_owner()
        self.assertIs(self.owner, original_owner)
        row = self.wrapper._get_order_intent_record('syn-list-00000000')
        with locks.ledger_transaction(self.path):
            view = hot.indexed_admission_view(self.wrapper, self.path)
            self.assertEqual(self.payload['store_id'], view.receipt.store_id)
            self.assertEqual(4, len(view.active_records))
        self.assertEqual(0, self.full_verifications.call_count)
        changed = runtime._update_order_intent_by_id(
            self.wrapper, row['client_order_id'], state='accepted', expected_record=row,
            operator_annotation='synthetic warm record change')
        self.assertEqual('synthetic warm record change', changed['operator_annotation'])
        self.assertIsNone(runtime._update_order_intent_by_id(
            self.wrapper, row['client_order_id'], state='accepted', expected_record=row,
            operator_annotation='stale update must not apply'))
        proof = runtime._refresh_spot_active_protection(self.wrapper)
        with locks.ledger_transaction(self.path):
            hot.indexed_admission_view(self.wrapper, self.path).assert_fresh(proof)
        self.assertEqual(self.profile['expected_gets_per_refresh'], self.wrapper.client.calls)
        record = self.wrapper._begin_spot_opo_intent(self.request, source='synthetic warm admission')
        self.assertEqual('pending', record['state'])
        self.wrapper._mark_spot_opo_submitted(record['client_order_id'], via='synthetic')
        self.assertEqual('submitted', self.wrapper._get_order_intent_record(record['client_order_id'])['state'])
        settled = self.settle_pending(record['client_order_id'])
        self.assertEqual('rejected', settled['state'])
        self.assertEqual({key: value * 3 for key, value in self.profile['expected_gets_per_refresh'].items()},
                         self.wrapper.client.calls)
        self.assertEqual(self.manifest, self.path.read_bytes())
        self.assert_owned_writes_protected()

    def test_market_buy_uses_selective_admission_and_guarded_generic_update(self):
        self.observe_owned_writes()
        params = {'symbol': 'BTCUSDT', 'side': 'BUY', 'type': 'MARKET', 'quantity': '0.1',
                  'newClientOrderId': 'synthetic-new-market-buy'}
        record = self.wrapper._begin_order_intent(params, market='spot', source='synthetic warm market')
        self.wrapper._mark_order_intent_submitted(params, via='synthetic')
        self.assertEqual('submitted', self.wrapper._get_order_intent_record(record['client_order_id'])['state'])
        runtime._update_order_intent(self.wrapper, params, state='unknown', last_error='synthetic uncertain outcome')
        self.assertEqual('unknown', self.wrapper._get_order_intent_record(record['client_order_id'])['state'])
        self.assertEqual({key: value * 2 for key, value in self.profile['expected_gets_per_refresh'].items()},
                         self.wrapper.client.calls)
        self.assert_owned_writes_protected()

    def test_every_refresh_queries_original_and_residual_stops_again(self):
        self.observe_owned_writes()
        proofs = [runtime._refresh_spot_active_protection(self.wrapper) for _ in range(2)]
        self.assertEqual(set(proofs[0][1]), set(proofs[1][1]))
        self.assertEqual(4, len(proofs[0][1]))
        self.assertNotEqual(proofs[0][1], proofs[1][1])
        self.assertEqual({key: value * 2 for key, value in self.profile['expected_gets_per_refresh'].items()},
                         self.wrapper.client.calls)
        self.assert_owned_writes_protected()

    def test_archived_historical_ids_and_duplicate_pending_block_before_new_intent(self):
        self.observe_owned_writes()
        original = self.wrapper._get_order_intent_record('syn-list-00000000')
        used = runtime.used_spot_client_order_ids({'syn-list-00000000': original})
        archived_id = next(identifier for identifier in used if 'exit' in identifier and identifier not in
                           {original.get('strategy_exit_client_order_id')})
        request = dict(self.request)
        request['pendingClientOrderId'] = archived_id
        with self.assertRaisesRegex(LiveTradingSafetyError, 'already used'):
            self.wrapper._begin_spot_opo_intent(request, source='synthetic archived collision')
        self.assertIsNone(self.wrapper._get_order_intent_record(request['listClientOrderId']))
        record = self.wrapper._begin_spot_opo_intent(self.request, source='synthetic new pending')
        with self.assertRaisesRegex(LiveTradingSafetyError, 'already has state'):
            self.wrapper._begin_spot_opo_intent(self.request, source='synthetic duplicate')
        with self.assertRaisesRegex(LiveTradingSafetyError, 'Unresolved'):
            self.wrapper._begin_spot_opo_intent(profiles.request_for(701), source='synthetic unresolved')
        self.assertEqual('pending', self.wrapper._get_order_intent_record(record['client_order_id'])['state'])
        self.assert_owned_writes_protected()

    def test_complete_bridge_write_retains_owner_guard_and_verified_anchor(self):
        with locks.ledger_transaction(self.path):
            old_session = self.session()
            native_guarded = old_session.native_guarded
            context = (patch.object(full, '_connection', side_effect=AssertionError('Complete bridge released native guard'))
                       if native_guarded else nullcontext())
            with context:
                ledger = runtime._read_ledger(self.path, expected_binding=self.binding)
                ledger['operator_annotation'] = 'synthetic authorized full write'
                locks.write_ledger(self.path, ledger)
            self.assertFalse(selective.indexed_session_refresh_required(self.owner))
        self.assertIsNotNone(self.wrapper._get_order_intent_record('syn-list-00000000'))
        with locks.ledger_transaction(self.path):
            current_session = self.session()
            self.assertIs(old_session, current_session)
            self.assertFalse(selective.indexed_session_refresh_required(self.owner))
            self.assertEqual('synthetic authorized full write', current_session.admission_view(
                deadline=locks.current_ledger_deadline(self.path)).metadata['operator_annotation'])
        self.warm_only()
        self.assertIsNotNone(self.wrapper._get_order_intent_record('syn-list-00000000'))

    def test_unknown_external_writer_is_blocked_or_fenced_without_automatic_reverification(self):
        with locks.ledger_transaction(self.path):
            native_guarded = self.session().native_guarded
            ledger = runtime._read_ledger(self.path, expected_binding=self.binding)
            candidate = dict(ledger)
            candidate['operator_annotation'] = 'synthetic unrecognized external writer'
            context = self.assertRaises(LiveTradingSafetyError) if native_guarded else nullcontext()
            with context:
                full.replace_indexed_snapshot(
                    ledger.indexed_snapshot.receipt.path, candidate, expected=ledger.indexed_snapshot,
                    rules=selective._rules(), expected_binding=self.binding,
                    deadline=locks.current_ledger_deadline(self.path))
        self.warm_only()
        for operation in (lambda: self.wrapper._get_order_intent_record('syn-list-00000000'),
                          self.wrapper._ensure_spot_execution_owner):
            with self.subTest(operation=operation):
                if native_guarded:
                    self.assertIsNotNone(operation())
                else:
                    with self.assertRaises(LiveTradingSafetyError):
                        operation()

    def test_current_wrapper_identity_and_owner_generation_are_required(self):
        self.warm_only()
        self.wrapper.api_key = 'synthetic other key'
        with self.assertRaisesRegex(LiveTradingSafetyError, 'credential'):
            self.wrapper._get_order_intent_record('syn-list-00000000')
        self.wrapper.api_key = fixtures.SYNTHETIC_KEY
        marker = owners.owner_marker_path(self.path)
        value = json.loads(marker.read_text())
        value['generation'] += 1
        marker.write_text(json.dumps(value))
        with self.assertRaisesRegex(LiveTradingSafetyError, 'owner state changed'):
            self.wrapper._get_order_intent_record('syn-list-00000000')

    def test_missing_indexed_pointer_or_receipt_never_uses_legacy_fallback(self):
        for removed in ('pointer', 'receipt'):
            with self.subTest(removed=removed):
                self.close_owner()
                self.setUp()
                target = self.path if removed == 'pointer' else locks.indexed_migration_fence_path(self.path)
                target.unlink()
                self.assertTrue(locks.indexed_namespace_exists(self.path))
                with patch.object(runtime, '_read_ledger', side_effect=AssertionError('Indexed source became legacy')):
                    with self.assertRaises(LiveTradingSafetyError):
                        self.wrapper._get_order_intent_record('syn-list-00000000')
                    with self.assertRaises(LiveTradingSafetyError):
                        runtime._update_order_intent_by_id(
                            self.wrapper, 'syn-list-00000000', state='accepted', operator_annotation='must not publish')
                self.assertFalse(target.exists())

    def test_destroyed_fenced_indexed_namespace_cannot_become_plain_json(self):
        database = self.read_full().indexed_snapshot.receipt.path
        replacement = self.path.with_name(self.path.name + '.synthetic-source-replacement')
        replacement.write_bytes(self.path.read_bytes())
        os.replace(replacement, self.path)
        # An actual source-identity failure closes the protected connection and
        # creates the held owner's fenced tombstone before namespace destruction.
        with self.assertRaises(LiveTradingSafetyError):
            self.wrapper._get_order_intent_record('syn-list-00000000')
        self.assertIsNotNone(self.owner.fd)
        database.unlink()
        locks.indexed_migration_fence_path(self.path).unlink()
        self.path.write_text(json.dumps(self.payload), encoding='utf-8')
        before = self.path.read_bytes()
        self.assertFalse(locks.indexed_namespace_exists(self.path))
        self.assertTrue(selective.indexed_namespace_known(self.path))
        generation = self.owner.generation
        try:
            for changed_generation in (False, True):
                with self.subTest(changed_generation=changed_generation):
                    self.owner.generation = generation + int(changed_generation)
                    self.assertTrue(selective.indexed_namespace_known(self.path))
                    with patch.object(runtime, '_read_ledger', side_effect=AssertionError('Known indexed source became legacy')):
                        with self.assertRaises(LiveTradingSafetyError):
                            self.wrapper._get_order_intent_record('syn-list-00000000')
                        with self.assertRaises(LiveTradingSafetyError):
                            runtime._update_order_intent_by_id(
                                self.wrapper, 'syn-list-00000000', state='accepted', operator_annotation='must not publish')
                        observed = self.install_transport_counter()
                        result = self.execute_entry()
                        self.assertFalse(result['ok'])
                        self.assertEqual(0, observed['post'])
                    self.assertEqual(before, self.path.read_bytes())
        finally:
            self.owner.generation = generation

    def assert_original_indexed_routing_blocks(self, target):
        before = target.read_bytes()
        with self.assertRaises(LiveTradingSafetyError):
            self.wrapper._get_order_intent_record('syn-list-00000000')
        with self.assertRaises(LiveTradingSafetyError):
            runtime._update_order_intent_by_id(
                self.wrapper, 'syn-list-00000000', state='accepted', operator_annotation='must not publish')
        observed = self.install_transport_counter()
        result = self.execute_entry()
        self.assertFalse(result['ok'])
        self.assertEqual(0, observed['post'])
        self.assertEqual(before, target.read_bytes())

    def new_legacy_target(self):
        target = self.root / 'separate-legacy.json'
        payload = deepcopy(self.payload)
        payload['store_id'] = str(uuid4())
        with locks.ledger_transaction(target):
            locks.write_ledger(target, payload)
        runtime.validate_order_intent_ledger(payload, expected_binding=self.binding)
        return target, payload

    def test_missing_or_replaced_owner_cannot_downgrade_destroyed_indexed_namespace(self):
        database = self.read_full().indexed_snapshot.receipt.path
        replacement = self.path.with_name(self.path.name + '.synthetic-source-replacement')
        replacement.write_bytes(self.path.read_bytes())
        os.replace(replacement, self.path)
        with self.assertRaises(LiveTradingSafetyError):
            self.wrapper._get_order_intent_record('syn-list-00000000')
        database.unlink()
        locks.indexed_migration_fence_path(self.path).unlink()
        self.path.write_text(json.dumps(self.payload), encoding='utf-8')
        self.assertFalse(locks.indexed_namespace_exists(self.path))
        try:
            for replacement_owner in (None, object()):
                with self.subTest(replacement_owner=type(replacement_owner).__name__):
                    self.wrapper._spot_execution_owner = replacement_owner
                    self.assert_original_indexed_routing_blocks(self.path)
        finally:
            self.wrapper._spot_execution_owner = self.owner

    def test_original_held_indexed_owner_rejects_new_legacy_path_and_valid_other_owner(self):
        target, payload = self.new_legacy_target()
        self.assertNotEqual(self.payload['store_id'], payload['store_id'])
        other_wrapper = _OwnedWrapper(payload['intents'])
        with owners.owner_administration_lock(target):
            owners.provision_owner_marker_locked(
                target, uid=fixtures.SYNTHETIC_UID, environment='live', store_id=payload['store_id'])
        other_owner = owners.claim_execution_owner(
            target, uid=fixtures.SYNTHETIC_UID, environment='live', store_id=payload['store_id'],
            credential_fingerprint=self.binding['credential_fingerprint'], owner_wrapper=other_wrapper)
        try:
            other_owner.assert_held(
                uid=fixtures.SYNTHETIC_UID, environment='live',
                credential_fingerprint=self.binding['credential_fingerprint'], owner_wrapper=other_wrapper)
            with patch.object(runtime, '_intent_path', return_value=target):
                for replacement_owner in (self.owner, other_owner):
                    with self.subTest(original_owner=replacement_owner is self.owner):
                        self.wrapper._spot_execution_owner = replacement_owner
                        self.assert_original_indexed_routing_blocks(target)
        finally:
            self.wrapper._spot_execution_owner = self.owner
            other_owner.close()
        # Retiring the original owner releases its wrapper attribution. A
        # subsequent true legacy inspection retains the existing JSON behavior.
        self.close_owner()
        with patch.object(runtime, '_intent_path', return_value=target):
            self.assertEqual(payload['intents']['syn-list-00000000'],
                             self.wrapper._get_order_intent_record('syn-list-00000000'))

    def test_original_wrapper_attribution_survives_combined_owner_and_path_changes(self):
        for fenced in (False, True):
            for replacement_owner in (None, object()):
                with self.subTest(fenced=fenced, replacement_owner=type(replacement_owner).__name__):
                    self.close_owner()
                    self.setUp()
                    target, _payload = self.new_legacy_target()
                    if fenced:
                        replacement = self.path.with_name(self.path.name + '.synthetic-source-replacement')
                        replacement.write_bytes(self.path.read_bytes())
                        os.replace(replacement, self.path)
                        with self.assertRaises(LiveTradingSafetyError):
                            self.wrapper._get_order_intent_record('syn-list-00000000')
                    original_ref = self.owner._owner_ref
                    decoy_wrapper = _OwnedWrapper(self.payload['intents'])
                    try:
                        if fenced:
                            # Tombstone attribution retains the session's original
                            # wrapper reference, independent of this mutable field.
                            self.owner._owner_ref = weakref.ref(decoy_wrapper)
                        self.wrapper._spot_execution_owner = replacement_owner
                        with patch.object(runtime, '_intent_path', return_value=target):
                            self.assert_original_indexed_routing_blocks(target)
                    finally:
                        self.owner._owner_ref = original_ref
                        self.wrapper._spot_execution_owner = self.owner

    def test_live_session_cannot_mask_original_held_wrapper_tombstone(self):
        replacement = self.path.with_name(self.path.name + '.synthetic-source-replacement')
        replacement.write_bytes(self.path.read_bytes())
        os.replace(replacement, self.path)
        with self.assertRaises(LiveTradingSafetyError):
            self.wrapper._get_order_intent_record('syn-list-00000000')
        self.assertIsNotNone(self.owner.fd)
        other_uid = fixtures.SYNTHETIC_UID + 1
        self.wrapper._spot_execution_owner = None
        original_context = self.wrapper._verified_spot_account_context
        # Mutating the actual wrapper's cached synthetic UID opens a distinct
        # account namespace without releasing its original held owner.
        self.wrapper._verified_spot_account_context = (*original_context[:4], other_uid)
        other_owner = None
        try:
            target = runtime._intent_path(self.wrapper)
            payload = deepcopy(self.payload)
            payload['store_id'] = str(uuid4())
            with owners.owner_administration_lock(target):
                with locks.ledger_transaction(target):
                    locks.write_ledger(target, payload)
                owners.provision_owner_marker_locked(
                    target, uid=other_uid, environment='live', store_id=payload['store_id'])
            migration.migrate_spot_indexed_intent_store(
                self.wrapper, acknowledgement=provision.PROVISION_ACK,
                reconciliation_reference='synthetic conflicting context migration')
            provision.rearm_spot_execution_owner(
                self.wrapper, acknowledgement=provision.PROVISION_ACK,
                reconciliation_reference='synthetic conflicting context rearm')
            other_owner = self.wrapper._ensure_spot_execution_owner()
            self.assertIsNot(self.owner, other_owner)
            self.assertIsNotNone(other_owner.fd)
            # The actual second live session and first held fenced tombstone
            # belong to this same original wrapper. Lookup order grants neither.
            with self.assertRaisesRegex(LiveTradingSafetyError, 'conflicting held'):
                selective.indexed_namespace_attribution(owner_wrapper=self.wrapper)
            self.assert_original_indexed_routing_blocks(target)
        finally:
            if other_owner is not None:
                selective.close_indexed_session(other_owner)
                other_owner.close()
            self.wrapper._verified_spot_account_context = original_context
            self.wrapper._spot_execution_owner = self.owner

    def test_revocation_closes_indexed_connection_and_prevents_admission(self):
        with locks.ledger_transaction(self.path):
            session = self.session()
        self.wrapper._revoke_spot_execution_owner()
        self.assertIsNone(self.owner.fd)
        with locks.ledger_transaction(self.path), self.assertRaises(LiveTradingSafetyError):
            session.read_record('syn-list-00000000', deadline=locks.current_ledger_deadline(self.path))
        with self.assertRaises(LiveTradingSafetyError):
            self.wrapper._ensure_spot_execution_owner()

    def test_initial_owner_source_gap_closes_new_owner_after_releasing_ledger_lock(self):
        self.close_owner()
        provision.rearm_spot_execution_owner(
            self.wrapper, acknowledgement=provision.PROVISION_ACK, reconciliation_reference='synthetic gap rearm')
        restarted = _OwnedWrapper(self.payload['intents'])
        original_claim = runtime.claim_execution_owner
        observed = {}
        def claim_then_replace(*args, **kwargs):
            owner = original_claim(*args, **kwargs)
            observed['owner'] = owner
            close = owner.close
            def record_close():
                try:
                    locks.current_ledger_deadline(self.path)
                except LiveTradingSafetyError:
                    observed['closed_after_unlock'] = True
                else:
                    raise AssertionError('Owner close must occur after the ledger lock is released')
                close()
            owner.close = record_close
            replacement = self.path.with_name(self.path.name + '.synthetic-gap')
            replacement.write_bytes(self.path.read_bytes())
            os.replace(replacement, self.path)
            return owner
        with patch.object(runtime, 'claim_execution_owner', side_effect=claim_then_replace):
            with self.assertRaisesRegex(LiveTradingSafetyError, 'manifest changed'):
                restarted._ensure_spot_execution_owner()
        self.assertTrue(observed['closed_after_unlock'])
        self.assertIsNone(observed['owner'].fd)
        self.assertEqual('recovery_required', json.loads(owners.owner_marker_path(self.path).read_text())['state'])

    def install_transport_counter(self):
        observed = {'post': 0}
        def synthetic_post(**_kwargs):
            observed['post'] += 1
            raise RuntimeError('Synthetic in-memory POST boundary reached')
        self.wrapper.client.create_order_list_opo = synthetic_post
        return observed

    def execute_entry(self):
        return place_spot_opo_entry(
            self.wrapper, self.request['symbol'], 'BUY', self.request['workingPrice'],
            self.request['workingQuantity'], self.request['pendingStopPrice'],
            list_client_order_id=self.request['listClientOrderId'],
            working_client_order_id=self.request['workingClientOrderId'],
            pending_client_order_id=self.request['pendingClientOrderId'])

    def test_actual_submission_boundary_has_one_synthetic_post_positive_control(self):
        self.observe_owned_writes()
        observed = self.install_transport_counter()
        result = self.execute_entry()
        self.assertFalse(result['ok'])
        self.assertEqual(1, observed['post'])
        self.assertIn('POST boundary reached', result['error'])
        self.assertEqual('unknown', self.wrapper._get_order_intent_record(self.request['listClientOrderId'])['state'])
        self.assert_owned_writes_protected()

    def test_actual_wrapper_rejects_six_complete_protection_races_before_transport(self):
        for boundary in ('begin', 'submitted'):
            for mutation in ('residual-numeric-id', 'new-active', 'settle-original'):
                with self.subTest(boundary=boundary, mutation=mutation):
                    self.close_owner()
                    self.setUp()
                    observed = self.install_transport_counter()
                    refresh = runtime._refresh_spot_active_protection
                    refresh_count = 0
                    def refresh_then_change(*args, **kwargs):
                        nonlocal refresh_count
                        proof = refresh(*args, **kwargs)
                        refresh_count += 1
                        if refresh_count == (1 if boundary == 'begin' else 2):
                            with patch.object(runtime, '_refresh_spot_active_protection', side_effect=refresh):
                                self.mutate_protection(mutation)
                        return proof
                    with patch.object(runtime, '_refresh_spot_active_protection', side_effect=refresh_then_change):
                        result = self.execute_entry()
                    self.assertFalse(result['ok'])
                    self.assertEqual(0, observed['post'])
                    self.assertIn('protection changed', result['error'])
                    record = self.wrapper._get_order_intent_record(self.request['listClientOrderId'])
                    if boundary == 'begin':
                        self.assertIsNone(record)
                    else:
                        self.assertEqual('unknown', record['state'])
                        self.assertTrue(runtime._is_unresolved(record))
                    self.assertEqual(self.manifest, self.path.read_bytes())

    def mutate_protection(self, kind):
        if kind == 'residual-numeric-id':
            record = self.wrapper._get_order_intent_record('syn-list-00000002')
            runtime._update_order_intent_by_id(
                self.wrapper, record['client_order_id'], state='accepted', expected_record=record,
                residual_stop_order_id=record['residual_stop_order_id'] + 1)
        elif kind == 'new-active':
            # A schema-valid full writer may import another accepted observation;
            # the actual complete map check must still reject its stale proof.
            with locks.ledger_transaction(self.path):
                ledger = runtime._read_ledger(self.path, expected_binding=self.binding)
                active = profiles._active_original(702, 0)
                ledger['intents'][active['client_order_id']] = active
                locks.write_ledger(self.path, ledger)
        else:
            record = self.wrapper._get_order_intent_record('syn-list-00000001')
            runtime._update_order_intent_by_id(
                self.wrapper, record['client_order_id'], state='accepted', expected_record=record,
                protection_state='triggered', list_status='ALL_DONE', pending_status='FILLED',
                pending_executed_qty='0.0999', exit_reconciled=True, exit_portfolio_quantity='0.0999',
                exit_recovery_signature='d' * 64, exit_order_id=record['pending_order_id'])

    def test_begin_and_submitted_reject_all_three_valid_complete_protection_races(self):
        # Fresh setup per race keeps every failed admission's authority isolated.
        for boundary in ('begin', 'submitted'):
            for mutation in ('residual-numeric-id', 'new-active', 'settle-original'):
                with self.subTest(boundary=boundary, mutation=mutation):
                    self.close_owner()
                    self.setUp()
                    if boundary == 'submitted':
                        pending = self.wrapper._begin_spot_opo_intent(self.request, source='synthetic race pending')
                    refresh = runtime._refresh_spot_active_protection
                    fired = False
                    def refresh_then_change(*args, **kwargs):
                        nonlocal fired
                        proof = refresh(*args, **kwargs)
                        if not fired:
                            fired = True
                            # Do the synthetic mutation after all fresh GETs, using
                            # the same registered writer and full local validators.
                            with patch.object(runtime, '_refresh_spot_active_protection', side_effect=refresh):
                                self.mutate_protection(mutation)
                        return proof
                    with patch.object(runtime, '_refresh_spot_active_protection', side_effect=refresh_then_change):
                        with self.assertRaisesRegex(LiveTradingSafetyError, 'protection changed'):
                            if boundary == 'begin':
                                self.wrapper._begin_spot_opo_intent(self.request, source='synthetic race rejected')
                            else:
                                self.wrapper._mark_spot_opo_submitted(pending['client_order_id'], via='synthetic')
                    record = self.wrapper._get_order_intent_record(self.request['listClientOrderId'])
                    self.assertIsNone(record) if boundary == 'begin' else self.assertEqual('pending', record['state'])
                    self.assertEqual(self.manifest, self.path.read_bytes())


if __name__ == '__main__':
    unittest.main()
