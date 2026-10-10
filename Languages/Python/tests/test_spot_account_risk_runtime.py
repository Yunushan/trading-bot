"""Proposed owned diagnostics with real local owners and isolated protected ports.

All policy/opening/provenance inputs below are synthetic storage fixtures.
No bridge bootstrap, risk append, policy permission or native backend is claimed.
"""
from contextlib import ExitStack, contextmanager
from copy import copy, deepcopy
import inspect
import json
import sqlite3
import sys
from pathlib import Path
import threading
import time
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch
from uuid import uuid4

import test_spot_inventory_namespace_integration as fixtures
from test_spot_account_risk_contract import opening, utc
from test_spot_account_risk_store import FakeProtectedPort
import test_spot_indexed_intent_hot_runtime as indexed_fixtures
from spot_inventory_checkpoint_fixtures import CheckpointFixtureBackend

from app.integrations.exchanges.binance.orders import order_intent_runtime as intents
from app.integrations.exchanges.binance.orders import order_intent_store as locks
from app.integrations.exchanges.binance.orders import spot_account_risk_contract as risk
from app.integrations.exchanges.binance.orders import spot_account_risk_runtime as owned
from app.integrations.exchanges.binance.orders import spot_account_risk_store as store
from app.integrations.exchanges.binance.orders import spot_inventory_checkpoint as inventory
from app.integrations.exchanges.binance.orders import spot_indexed_intent_selective as indexed
from app.integrations.exchanges.binance.orders import spot_indexed_intent_store as indexed_full
from app.gui.shared import allocation_persistence as allocations
from app.settings.live_safety import LiveTradingSafetyError


_UNAVAILABLE_PROVIDER = owned._protected_provider


class OwnedSpotRiskReadTests(unittest.TestCase):
    @contextmanager
    def case(self, *, indexed=False):
        with ExitStack() as stack:
            backend = stack.enter_context(CheckpointFixtureBackend(simulate_windows=True))
            if indexed:
                fixture = indexed_fixtures.SpotIndexedIntentHotRuntimeTests("runTest")
                fixture.setUp()
                stack.callback(fixture.doCleanups)
                account = SimpleNamespace(wrapper=fixture.wrapper, owner=fixture.owner,
                                          home=fixture.root, path=fixture.path)
                allocation_path = fixture.allocation_path
                namespace = {"account_uid": fixture.owner.uid, "store_id": fixture.owner.store_id}
            else:
                fixture = fixtures.SpotInventoryNamespaceIntegrationTests("runTest")
                fixture.setUp()
                stack.callback(fixture.doCleanups)
                account = fixture.account("owned-risk-read", 896101, accepted=False)
                fixture.bootstrap(account)
                fixture.author_accepted(account, fixture.fill)
                allocation_path = fixture.path
                namespace = account.namespace
            port = FakeProtectedPort()
            risk_path = account.path.with_name("account_risk.json")
            raw_opening = opening()
            raw_opening["identity"]["account_uid"] = namespace["account_uid"]
            raw_opening["identity"]["ledger_store_id"] = namespace["store_id"]
            proof = {"version": 1, "basis": "unverified_supplied_claim",
                     "identity": deepcopy(raw_opening["identity"]), "reference": "synthetic-history-only",
                     "record_digest": "1" * 64, "request_digest": "2" * 64, "evidence_digest": "3" * 64}
            # Explicit synthetic initial storage, not an owned bridge capability.
            with store._storage_scope(risk_path, protected=port, guard=lambda: None,
                                      deadline=time.monotonic() + 60.0):
                receipt = store.bootstrap_risk_store(risk_path, raw_opening, proof,
                                                    operation_id="synthetic-owned-read-opening")
                event = risk.parse_event({"event_id": "synthetic-owned-read-kill", "kind": "KILL",
                                          "at": utc(receipt.state.at + 1), "expected_head": receipt.state.head,
                                          "data": {"reason": "synthetic-only", "evidence_ref": "synthetic-test"}})
                receipt = store.append_risk_event(risk_path, receipt, event, proof)
            stack.enter_context(patch.object(owned, "_protected_provider", return_value=port))
            yield SimpleNamespace(f=fixture, account=account, backend=backend, port=port,
                                  allocation_path=allocation_path, risk_path=risk_path,
                                  receipt=receipt, identity=raw_opening["identity"], proof=proof, event=event)

    @contextmanager
    def locked(self, case, paths=None):
        with patch.object(Path, "home", return_value=case.account.home):
            with locks.ledger_transactions(*(paths or (
                    case.account.path, case.allocation_path, case.risk_path))):
                yield

    def image(self, case):
        return (case.account.path.read_bytes(), case.allocation_path.read_bytes(), case.risk_path.read_bytes(),
                deepcopy(case.port.values), deepcopy(case.backend.store), case.port.writes,
                len(case.backend.put_calls))

    def read(self, case):
        with self.locked(case):
            return owned.read_owned_spot_risk_store(case.account.wrapper)

    def test_public_read_accepts_only_wrapper_and_replays_entire_history_without_writes(self):
        self.assertEqual(["wrapper"], list(inspect.signature(owned.read_owned_spot_risk_store).parameters))
        with self.case() as case:
            before = self.image(case)
            signed_reads = list(case.f.account_reads)
            real = risk.replay_events
            with patch.object(risk, "replay_events", wraps=real) as replay:
                receipt = self.read(case)
            self.assertIs(type(receipt), store.RiskReadReceipt)
            self.assertEqual(case.receipt.raw, receipt.raw)
            self.assertEqual(case.receipt.state, receipt.state)
            self.assertEqual(2, receipt.revision)
            self.assertEqual(1, len(replay.call_args.args[1]))
            self.assertEqual(before, self.image(case))
            self.assertEqual(signed_reads, case.f.account_reads)
            self.assertEqual([], case.f.order_calls)
            self.assertIsNone(store._CONTEXT.get())

    def test_no_signed_context_rejects_before_virtual_resolver_or_provider(self):
        with self.case() as case:
            wrapper = case.account.wrapper
            wrapper._verified_spot_account_context = None
            resolver = Mock(side_effect=AssertionError("A diagnostic cannot fetch account identity"))
            with patch.object(wrapper, "_resolve_spot_account_uid", resolver), patch.object(
                    owned, "_protected_provider") as provider:
                with self.locked(case), self.assertRaises(LiveTradingSafetyError):
                    owned.read_owned_spot_risk_store(wrapper)
            resolver.assert_not_called()
            provider.assert_not_called()

    def test_valid_cached_context_never_calls_arbitrary_virtual_resolver(self):
        with self.case() as case:
            before = self.image(case)
            resolver = Mock(side_effect=AssertionError("No virtual resolver"))
            with patch.object(case.account.wrapper, "_resolve_spot_account_uid", resolver):
                self.assertEqual(case.receipt.raw, self.read(case).raw)
            resolver.assert_not_called()
            self.assertEqual(before, self.image(case))

    def test_administration_fallback_cannot_supply_execution_owner(self):
        with self.case() as case:
            before = self.image(case)
            wrapper = case.account.wrapper
            wrapper._spot_execution_owner = None
            wrapper._operator_spot_account_uid = case.account.owner.uid
            wrapper._spot_inventory_administration_path = case.account.path
            with self.locked(case), patch.object(owned, "_protected_provider") as provider:
                with self.assertRaises(LiveTradingSafetyError):
                    owned.read_owned_spot_risk_store(wrapper)
            provider.assert_not_called()
            self.assertEqual(before, self.image(case))

    def test_default_provider_refuses_before_any_inventory_protected_read(self):
        # Restore the genuine default, rather than returning a test provider.
        with self.case() as case:
            before = self.image(case)
            with patch.object(owned, "_protected_provider", new=_UNAVAILABLE_PROVIDER):
                reads = list(case.backend.read_calls)
                with self.assertRaises(LiveTradingSafetyError):
                    self.read(case)
                self.assertEqual(reads, case.backend.read_calls)
            self.assertEqual(before, self.image(case))

    def test_initial_protected_checkpoint_cannot_be_adopted_after_snapshot_verification(self):
        with self.case() as case:
            before = self.image(case)
            risk_reads_before = case.port.reads
            real_verify = allocations.guard_position_allocation_snapshot
            changed = []
            proved = []
            def after_actual_proof(*args, **kwargs):
                snapshot = real_verify(*args, **kwargs)
                if not changed:
                    # The complete original verifier has returned valid A.
                    # Change only the independent fake protected slot BEFORE
                    # the caller can separately capture/post-get its value.
                    proved.append(deepcopy(snapshot))
                    key = next(iter(case.backend.store))
                    original_checkpoint = case.backend.store[key]
                    anchor = json.loads(original_checkpoint)
                    anchor["head"]["revision"] += 1
                    case.backend.store[key] = inventory._compact(anchor)
                    changed.append((original_checkpoint, deepcopy(case.backend.store)))
                return snapshot
            with patch.object(allocations, "guard_position_allocation_snapshot",
                              side_effect=after_actual_proof):
                with patch.object(risk, "replay_events", wraps=risk.replay_events) as replay:
                    with self.assertRaises(LiveTradingSafetyError):
                        self.read(case)
                replay.assert_not_called()
            self.assertEqual(1, len(proved))
            self.assertEqual(json.loads(before[1]), proved[0])
            self.assertEqual(1, len(changed))
            original_checkpoint, changed_store = changed[0]
            self.assertNotEqual(original_checkpoint, next(iter(changed_store.values())))
            self.assertEqual(changed_store, case.backend.store)
            after = self.image(case)
            self.assertEqual(before[:4], after[:4])
            self.assertEqual(before[5:], after[5:])
            self.assertEqual(risk_reads_before, case.port.reads)
    def test_each_missing_caller_lock_fences_without_new_lock_or_provider(self):
        for omitted in range(3):
            with self.subTest(omitted=omitted), self.case() as case:
                paths = (case.account.path, case.allocation_path, case.risk_path)
                before = self.image(case)
                with self.locked(case, tuple(path for i, path in enumerate(paths) if i != omitted)):
                    with patch.object(owned, "_protected_provider") as provider:
                        with self.assertRaises(LiveTradingSafetyError):
                            owned.read_owned_spot_risk_store(case.account.wrapper)
                    provider.assert_not_called()
                self.assertEqual(before, self.image(case))

    def test_busy_actual_owner_mutex_refuses_without_waiting_or_expanding_locks(self):
        with self.case() as case:
            ready, release = threading.Event(), threading.Event()
            def holder():
                with case.account.owner._submission_lock:
                    ready.set()
                    release.wait(3)
            thread = threading.Thread(target=holder)
            thread.start()
            self.assertTrue(ready.wait(2))
            try:
                with self.assertRaises(LiveTradingSafetyError):
                    self.read(case)
            finally:
                release.set()
                thread.join(2)
            self.assertFalse(thread.is_alive())

    def test_original_identity_mutations_before_and_after_actual_full_batch_fence(self):
        variants = ("close", "owner", "key", "secret", "client", "equal_context", "uid",
                    "store", "generation", "owner_path", "mode", "deadline", "transaction")
        for phase in ("before", "after"):
            for variant in variants:
                with self.subTest(phase=phase, variant=variant), self.case() as case:
                    real = risk.replay_events
                    called = []
                    def mutate():
                        wrapper, owner = case.account.wrapper, case.account.owner
                        if variant == "close":
                            owner.close()
                        elif variant == "owner":
                            wrapper._spot_execution_owner = object()
                        elif variant == "key":
                            wrapper.api_key += "-changed"
                        elif variant == "secret":
                            wrapper.api_secret += "-changed"
                        elif variant == "client":
                            wrapper.client = object()
                        elif variant == "equal_context":
                            wrapper._verified_spot_account_context = tuple(list(wrapper._verified_spot_account_context))
                        elif variant == "uid":
                            context = wrapper._verified_spot_account_context
                            wrapper._verified_spot_account_context = (*context[:4], context[4] + 1)
                        elif variant == "store":
                            owner.store_id = str(uuid4())
                        elif variant == "generation":
                            owner.generation += 1
                        elif variant == "owner_path":
                            owner.ledger_path = owner.ledger_path.with_name("other.json")
                        elif variant == "mode":
                            wrapper._mode = "Paper"
                        elif variant == "deadline":
                            locks._ACTIVE_LEDGER_TRANSACTION.get().deadline += 60.0
                        else:
                            locks._ACTIVE_LEDGER_TRANSACTION.set(None)
                    def replay(*args):
                        called.append(phase)
                        if phase == "before":
                            mutate()
                        result = real(*args)
                        if phase == "after":
                            mutate()
                        return result
                    before = self.image(case)
                    with patch.object(risk, "replay_events", side_effect=replay):
                        with self.assertRaises(LiveTradingSafetyError):
                            self.read(case)
                    self.assertEqual([phase], called)
                    self.assertEqual(before, self.image(case))

    def test_full_ledger_change_plain_copy_and_same_bytes_new_inode_cannot_be_adopted(self):
        for variant in ("changed_history", "plain_copy", "new_inode"):
            with self.subTest(variant=variant), self.case() as case:
                real = risk.replay_events
                original_reader = intents._read_ledger
                original = self.image(case)
                after_fault = []
                def replay(*args):
                    result = real(*args)
                    if variant == "changed_history":
                        ledger = original_reader(case.account.path, expected_binding=intents._intent_binding(
                            case.account.wrapper))
                        ledger["intents"][fixtures.CLIENT]["operator_note"] = "changed-complete-history"
                        locks.write_ledger(case.account.path, ledger)
                    elif variant == "new_inode":
                        replacement = case.account.path.with_name("synthetic-replacement")
                        replacement.write_bytes(case.account.path.read_bytes())
                        replacement.replace(case.account.path)
                    after_fault.append(self.image(case))
                    return result
                def copied_reader(*args, **kwargs):
                    payload = original_reader(*args, **kwargs)
                    return dict(payload) if after_fault and variant == "plain_copy" else payload
                with patch.object(risk, "replay_events", side_effect=replay), patch.object(
                        intents, "_read_ledger", side_effect=copied_reader):
                    with self.assertRaises(LiveTradingSafetyError):
                        self.read(case)
                self.assertEqual(after_fault[0], self.image(case))
                self.assertEqual(original[1:], self.image(case)[1:])

    def test_inventory_raw_and_checkpoint_revision_remain_original_after_full_batch(self):
        for variant in ("delete", "strip_namespace", "mode", "protected_revision"):
            with self.subTest(variant=variant), self.case() as case:
                real = risk.replay_events
                original = self.image(case)
                changed = []
                def replay(*args):
                    result = real(*args)
                    if variant == "delete":
                        case.allocation_path.unlink()
                    elif variant in ("strip_namespace", "mode"):
                        snapshot = json.loads(case.allocation_path.read_bytes())
                        if variant == "strip_namespace":
                            del snapshot["spot_account_namespace"]
                        else:
                            snapshot["mode"] = "Paper"
                        case.allocation_path.write_bytes(store._encode(snapshot))
                    else:
                        key = next(iter(case.backend.store))
                        anchor = json.loads(case.backend.store[key])
                        anchor["head"]["revision"] += 1
                        case.backend.store[key] = inventory._compact(anchor)
                    changed.append((case.allocation_path.read_bytes() if case.allocation_path.exists() else None,
                                    deepcopy(case.backend.store)))
                    return result
                with patch.object(risk, "replay_events", side_effect=replay):
                    with self.assertRaises(LiveTradingSafetyError):
                        self.read(case)
                self.assertEqual(changed[0], (
                    case.allocation_path.read_bytes() if case.allocation_path.exists() else None,
                    deepcopy(case.backend.store)))
                self.assertEqual(original[0], case.account.path.read_bytes())
                self.assertEqual(original[2:4], (case.risk_path.read_bytes(), case.port.values))
                self.assertEqual(original[5:], (case.port.writes, len(case.backend.put_calls)))

    def test_pending_wrong_anchor_and_missing_risk_never_recover_or_write(self):
        for variant in ("pending", "wrong_uid", "wrong_store", "missing_slot", "missing_source"):
            with self.subTest(variant=variant), self.case() as case:
                slot = next(iter(case.port.values))
                anchor = store._decode(case.port.values[slot])
                if variant == "pending":
                    with store._storage_scope(case.risk_path, protected=case.port, guard=lambda: None,
                                              deadline=time.monotonic() + 60.0):
                        receipt = store.read_risk_store(case.risk_path, case.identity)
                        event = risk.parse_event({"event_id": "synthetic-prepared-only", "expected_head": receipt.state.head,
                                                  "at": utc(receipt.state.at + 1), "kind": "KILL",
                                                  "data": {"reason": "pending-test", "evidence_ref": "offline"}})
                        with patch.object(store, "_finish", side_effect=OSError("synthetic pending crash")):
                            with self.assertRaises(store.RiskStoreError):
                                store.append_risk_event(case.risk_path, receipt, event, case.proof)
                elif variant in ("wrong_uid", "wrong_store"):
                    field = "account_uid" if variant == "wrong_uid" else "ledger_store_id"
                    anchor["identity"][field] = 896102 if variant == "wrong_uid" else str(uuid4())
                    case.port.values[slot] = store._encode(anchor)
                elif variant == "missing_slot":
                    case.port.values.clear()
                else:
                    case.risk_path.unlink()
                with self.locked(case):
                    before = (case.risk_path.read_bytes() if case.risk_path.exists() else None,
                              deepcopy(case.port.values), case.port.writes, len(case.backend.put_calls),
                              sorted(path.name for path in case.risk_path.parent.iterdir()))
                    with patch.object(store, "recover_risk_store", side_effect=AssertionError("Read cannot recover")):
                        with self.assertRaises(LiveTradingSafetyError):
                            owned.read_owned_spot_risk_store(case.account.wrapper)
                    self.assertEqual(before, (
                        case.risk_path.read_bytes() if case.risk_path.exists() else None,
                        deepcopy(case.port.values), case.port.writes, len(case.backend.put_calls),
                        sorted(path.name for path in case.risk_path.parent.iterdir())))

    def test_diagnostic_receipt_copy_original_and_foreign_scope_do_not_author_append(self):
        with self.case() as case:
            receipt = self.read(case)
            before = self.image(case)
            for candidate in (receipt, copy(receipt)):
                with self.subTest(copy=candidate is not receipt), store._storage_scope(
                        case.risk_path, protected=case.port, guard=lambda: None,
                        deadline=time.monotonic() + 60.0):
                    with self.assertRaises(store.RiskStoreError):
                        store.append_risk_event(case.risk_path, candidate, case.event, case.proof)
            self.assertEqual(before, self.image(case))

    def test_copied_wrapper_and_inherited_process_cannot_reuse_actual_owner(self):
        with self.case() as case:
            before = self.image(case)
            with self.locked(case):
                with self.assertRaises(LiveTradingSafetyError):
                    owned.read_owned_spot_risk_store(copy(case.account.wrapper))
                with patch.object(owned, "_PROCESS_ID", -1):
                    with self.assertRaises(LiveTradingSafetyError):
                        owned.read_owned_spot_risk_store(case.account.wrapper)
            self.assertEqual(before, self.image(case))

    def test_replaced_inventory_path_and_valid_foreign_owner_cannot_redirect_read(self):
        for variant in ("inventory_path", "foreign_owner"):
            with self.subTest(variant=variant), self.case() as case:
                before = self.image(case)
                if variant == "foreign_owner":
                    foreign = case.f.account("foreign-risk-owner", 896102, accepted=False)
                    case.account.wrapper._spot_execution_owner = foreign.owner
                    with self.assertRaises(LiveTradingSafetyError):
                        self.read(case)
                else:
                    real = risk.replay_events
                    replacement = case.allocation_path.with_name("different-valid-allocation.json")
                    replacement.write_bytes(case.allocation_path.read_bytes())
                    def replay(*args):
                        result = real(*args)
                        redirect.start()
                        return result
                    redirect = patch.object(allocations, "get_position_allocations_path", return_value=replacement)
                    try:
                        with patch.object(risk, "replay_events", side_effect=replay):
                            with self.assertRaises(LiveTradingSafetyError):
                                self.read(case)
                    finally:
                        redirect.stop()
                    self.assertEqual(before[1], replacement.read_bytes())
                self.assertEqual(before, self.image(case))

    def test_expiry_after_full_batch_preserves_original_deadline_and_no_receipt(self):
        with self.case() as case:
            real = risk.replay_events
            before = self.image(case)
            with self.locked(case):
                deadline = locks.current_ledger_deadline(case.account.path, case.allocation_path, case.risk_path)
                def replay(*args):
                    result = real(*args)
                    # Shared stdlib time mock forces the genuine original deadline past.
                    expiry.start()
                    return result
                expiry = patch.object(time, "monotonic", return_value=deadline + 1)
                try:
                    with patch.object(risk, "replay_events", side_effect=replay):
                        with self.assertRaises(LiveTradingSafetyError):
                            owned.read_owned_spot_risk_store(case.account.wrapper)
                finally:
                    expiry.stop()
                self.assertEqual(deadline, locks.current_ledger_deadline(*(
                    case.account.path, case.allocation_path, case.risk_path)))
            self.assertEqual(before, self.image(case))

    def test_keyboard_interrupt_and_system_exit_preserve_exact_identity_and_release_mutex(self):
        for cancellation in (KeyboardInterrupt("synthetic-cancel"), SystemExit("synthetic-exit")):
            with self.subTest(type=type(cancellation).__name__), self.case() as case:
                before = self.image(case)
                real = risk.replay_events
                def replay(*args):
                    real(*args)
                    raise cancellation
                with patch.object(risk, "replay_events", side_effect=replay):
                    with self.assertRaises(type(cancellation)) as caught:
                        self.read(case)
                self.assertIs(cancellation, caught.exception)
                self.assertIsNone(store._CONTEXT.get())
                self.assertEqual(before, self.image(case))
                acquired = []
                def probe():
                    held = case.account.owner._submission_lock.acquire(blocking=False)
                    acquired.append(held)
                    if held:
                        case.account.owner._submission_lock.release()
                thread = threading.Thread(target=probe)
                thread.start()
                thread.join(2)
                self.assertEqual([True], acquired)
                self.assertEqual(case.receipt.raw, self.read(case).raw)

    def assert_original_mutex_released(self, original_mutex):
        acquired = []
        def probe():
            held = original_mutex.acquire(blocking=False)
            acquired.append(held)
            if held:
                original_mutex.release()
        thread = threading.Thread(target=probe)
        thread.start()
        thread.join(2)
        self.assertFalse(thread.is_alive())
        self.assertEqual([True], acquired)

    def test_original_mutex_replacement_before_and_after_full_batch_fences_and_releases(self):
        for phase in ("before", "after"):
            with self.subTest(phase=phase), self.case() as case:
                before = self.image(case)
                original_mutex = case.account.owner._submission_lock
                replacement_mutex = threading.RLock()
                real = risk.replay_events
                called = []
                def replay(*args):
                    called.append(phase)
                    if phase == "before":
                        case.account.owner._submission_lock = replacement_mutex
                    result = real(*args)
                    if phase == "after":
                        case.account.owner._submission_lock = replacement_mutex
                    return result
                with patch.object(risk, "replay_events", side_effect=replay):
                    with self.assertRaises(LiveTradingSafetyError):
                        self.read(case)
                self.assertEqual([phase], called)
                self.assertIs(replacement_mutex, case.account.owner._submission_lock)
                self.assertEqual(before, self.image(case))
                self.assert_original_mutex_released(original_mutex)

    def test_mutex_replacement_cannot_mask_primary_cancellation_or_leak_original_lock(self):
        for cancellation in (KeyboardInterrupt("mutex-cancel"), SystemExit("mutex-exit")):
            with self.subTest(type=type(cancellation).__name__), self.case() as case:
                before = self.image(case)
                original_mutex = case.account.owner._submission_lock
                replacement_mutex = threading.RLock()
                real = risk.replay_events
                def replay(*args):
                    real(*args)
                    case.account.owner._submission_lock = replacement_mutex
                    raise cancellation
                with patch.object(risk, "replay_events", side_effect=replay):
                    with self.assertRaises(type(cancellation)) as caught:
                        self.read(case)
                self.assertIs(cancellation, caught.exception)
                self.assertIsNone(store._CONTEXT.get())
                self.assertEqual(before, self.image(case))
                self.assert_original_mutex_released(original_mutex)

    def test_indexed_complete_original_receipt_not_only_current_rows_is_retained(self):
        with self.case(indexed=True) as case:
            before = self.image(case)
            self.assertEqual(case.receipt.raw, self.read(case).raw)
            self.assertEqual(before, self.image(case))
            real = risk.replay_events
            histories = []
            def replay(*args):
                result = real(*args)
                original = intents._read_ledger(case.account.path, expected_binding=intents._intent_binding(
                    case.account.wrapper))
                first_id = next(iter(original["intents"]))
                original_data = json.dumps(dict(original), sort_keys=True)
                original["intents"][first_id]["operator_note"] = "synthetic-history-added"
                locks.write_ledger(case.account.path, original)
                current = intents._read_ledger(case.account.path, expected_binding=intents._intent_binding(
                    case.account.wrapper))
                del current["intents"][first_id]["operator_note"]
                locks.write_ledger(case.account.path, current)
                final = intents._read_ledger(case.account.path, expected_binding=intents._intent_binding(
                    case.account.wrapper))
                self.assertEqual(original_data, json.dumps(dict(final), sort_keys=True))
                histories.append(final.indexed_authority.snapshot.receipt)
                return result
            with patch.object(risk, "replay_events", side_effect=replay):
                with self.assertRaises(LiveTradingSafetyError):
                    self.read(case)
            self.assertEqual(1, len(histories))
            self.assertEqual(before[1:], self.image(case)[1:])

    def native_session(self, case):
        with self.locked(case):
            session = case.f.session()
            if session.native_guarded:
                self.assertEqual("win32", sys.platform)
                return session
            # There is no native claim on another platform. The real legacy
            # fallback is exercised separately; the optimization must refuse.
            self.assertNotEqual("win32", sys.platform)
            self.assertIsNone(owned._native_indexed_guard(
                case.account.owner, case.account.wrapper, case.account.path,
                intents._intent_binding(case.account.wrapper),
                locks.current_ledger_deadline(case.account.path, case.allocation_path, case.risk_path),
                lambda: case.account.owner.assert_held(
                    uid=case.account.owner.uid, environment="live",
                    credential_fingerprint=case.account.owner.credential_fingerprint,
                    owner_wrapper=case.account.wrapper)))
            return None

    def indexed_image(self, case, session):
        # Read through the real guarded pager. Open no foreign native file handle
        # unless a failed existing session has already closed that pager.
        connection = session._connection
        closed = session._closed
        if closed:
            connection = sqlite3.connect(session._receipt.path.as_uri() + "?mode=ro", uri=True)
        try:
            schema = tuple(connection.execute(
                "SELECT name,type,tbl_name,sql FROM sqlite_master ORDER BY name").fetchall())
            rows = tuple((table, tuple(sorted(connection.execute(f"SELECT * FROM {table}").fetchall())))
                         for table in ("store_state", "current_records", "journal_commits", "journal_records",
                                       "reserved_ids", "active_projection", "unresolved_projection"))
            return schema, rows
        finally:
            if closed:
                connection.close()

    def test_native_read_has_two_genuine_complete_sql_boundaries_around_risk_replay(self):
        with self.case(indexed=True) as case:
            session = self.native_session(case)
            if session is None:
                with self.locked(case), patch.object(intents, "_read_ledger", wraps=intents._read_ledger) as full_reads:
                    receipt = owned.read_owned_spot_risk_store(case.account.wrapper)
                self.assertEqual(case.receipt.raw, receipt.raw)
                self.assertGreater(full_reads.call_count, 2)
                return
            before = self.image(case)
            phases = []
            original_reader, original_replay = intents._read_ledger, risk.replay_events
            def reader(*args, **kwargs):
                result = original_reader(*args, **kwargs)
                phases.append(("ledger", result.indexed_authority))
                return result
            def replay(*args):
                result = original_replay(*args)
                phases.append(("risk", result))
                return result
            with patch.object(intents, "_read_ledger", side_effect=reader), patch.object(
                    risk, "replay_events", side_effect=replay), patch.object(
                    indexed_full, "_verified", wraps=indexed_full._verified) as verified:
                receipt = self.read(case)
            self.assertEqual(["ledger", "risk", "ledger"], [kind for kind, _ in phases])
            self.assertEqual(2, verified.call_count)
            self.assertEqual(phases[0][1], phases[-1][1])
            self.assertEqual(case.receipt.raw, receipt.raw)
            self.assertEqual(before, self.image(case))

    def test_legacy_fallback_keeps_complete_proof_at_every_guard(self):
        with self.case() as case:
            original_reader = intents._read_ledger
            before = self.image(case)
            with patch.object(intents, "_read_ledger", wraps=original_reader) as full_reads, patch.object(
                    owned, "_native_indexed_guard", wraps=owned._native_indexed_guard) as native:
                receipt = self.read(case)
            self.assertEqual(case.receipt.raw, receipt.raw)
            self.assertGreater(full_reads.call_count, 2)
            self.assertEqual(1, native.call_count)
            self.assertEqual(before, self.image(case))

    def test_native_original_session_fields_cannot_be_replaced_at_baseline_or_risk_replay(self):
        variants = ("registry", "connection", "receipt", "change", "manifest", "migration", "backup",
                    "rules", "record_receipts", "commit_sequences", "pending", "data_version", "native_guard")
        for phase in ("baseline", "risk"):
            for variant in variants:
                with self.subTest(phase=phase, variant=variant), self.case(indexed=True) as case:
                    session = self.native_session(case)
                    if session is None:
                        self.assertNotEqual("win32", sys.platform)
                        continue
                    before = self.image(case)
                    original_mutex = case.account.owner._submission_lock
                    original_reader, original_replay = intents._read_ledger, risk.replay_events
                    changed = []
                    restore = []
                    def mutate():
                        if variant == "registry":
                            with indexed._session_registry():
                                indexed._SESSIONS[case.account.path] = copy(session)
                            restore.append(lambda: indexed._SESSIONS.__setitem__(case.account.path, session))
                        else:
                            field = "_" + variant
                            old = getattr(session, field)
                            if variant == "connection":
                                new = object()
                            elif variant == "pending":
                                new = (session._receipt, session._receipt)
                            elif variant == "data_version":
                                new = old + 1
                            elif variant == "native_guard":
                                new = False
                            else:
                                new = copy(old)
                            setattr(session, field, new)
                            restore.append(lambda: setattr(session, field, old))
                        changed.append(variant)
                    def reader(*args, **kwargs):
                        result = original_reader(*args, **kwargs)
                        if phase == "baseline" and not changed:
                            mutate()
                        return result
                    def replay(*args):
                        result = original_replay(*args)
                        if phase == "risk":
                            mutate()
                        return result
                    try:
                        with patch.object(intents, "_read_ledger", side_effect=reader), patch.object(
                                risk, "replay_events", side_effect=replay):
                            with self.assertRaises(LiveTradingSafetyError):
                                self.read(case)
                        self.assertEqual([variant], changed)
                    finally:
                        for restore_field in restore:
                            restore_field()
                    self.assertEqual(before, self.image(case))
                    self.assert_original_mutex_released(original_mutex)

    def test_native_rolled_back_write_and_same_connection_pager_substitution_fence(self):
        for variant in ("rollback", "pager"):
            with self.subTest(variant=variant), self.case(indexed=True) as case:
                session = self.native_session(case)
                if session is None:
                    self.assertNotEqual("win32", sys.platform)
                    continue
                original_mutex = case.account.owner._submission_lock
                with self.locked(case):
                    before = self.indexed_image(case, session)
                original_changes = session._connection.total_changes
                original_replay = risk.replay_events
                changed = []
                def replay(*args):
                    result = original_replay(*args)
                    connection = session._connection
                    if variant == "rollback":
                        connection.execute("BEGIN")
                        connection.execute("UPDATE current_records SET commit_seq=commit_seq WHERE client_id=(SELECT MIN(client_id) FROM current_records)")
                        connection.rollback()
                        self.assertGreater(connection.total_changes, original_changes)
                        self.assertFalse(connection.in_transaction)
                    elif hasattr(connection, "serialize") and hasattr(connection, "deserialize"):
                        connection.deserialize(connection.serialize())
                        self.assertEqual(original_changes, connection.total_changes)
                        self.assertNotEqual(str(session._receipt.path), connection.execute(
                            "PRAGMA database_list").fetchone()[2])
                    else:
                        # Older Python has no deserialize API. A real attached
                        # in-memory pager still changes the pinned database list.
                        connection.execute("ATTACH DATABASE ':memory:' AS injected_pager")
                    changed.append(variant)
                    return result
                with patch.object(risk, "replay_events", side_effect=replay):
                    with self.assertRaises(LiveTradingSafetyError):
                        self.read(case)
                self.assertEqual([variant], changed)
                with self.locked(case):
                    self.assertEqual(before, self.indexed_image(case, session))
                self.assert_original_mutex_released(original_mutex)

    def test_native_last_probe_registry_loss_owner_close_and_guard_failure_cannot_return(self):
        for variant in ("registry", "close", "native_failure"):
            with self.subTest(variant=variant), self.case(indexed=True) as case:
                session = self.native_session(case)
                if session is None:
                    self.assertNotEqual("win32", sys.platform)
                    continue
                original_mutex = case.account.owner._submission_lock
                before = self.image(case)
                with self.locked(case):
                    original_sql = self.indexed_image(case, session)
                original_guard, original_replay = session._guard, risk.replay_events
                ready, changed, markers = [], [], []
                def replay(*args):
                    result = original_replay(*args)
                    ready.append(True)
                    return result
                def guard():
                    original_guard()  # Always run the actual native denial probes.
                    if ready and not changed:
                        changed.append(variant)
                        if variant == "registry":
                            with indexed._session_registry():
                                indexed._SESSIONS[case.account.path] = copy(session)
                        elif variant == "close":
                            case.account.owner.close()
                            markers.append(case.account.owner.marker_path.read_bytes())
                        else:
                            raise LiveTradingSafetyError("Synthetic loss after genuine native probes")
                try:
                    with patch.object(risk, "replay_events", side_effect=replay), patch.object(
                            session, "_guard", side_effect=guard):
                        with self.assertRaises(LiveTradingSafetyError):
                            self.read(case)
                finally:
                    if variant == "registry":
                        with indexed._session_registry():
                            indexed._SESSIONS[case.account.path] = session
                self.assertEqual([variant], changed)
                self.assertEqual(before, self.image(case))
                with self.locked(case):
                    self.assertEqual(original_sql, self.indexed_image(case, session))
                if markers:
                    self.assertEqual(markers[0], case.account.owner.marker_path.read_bytes())
                self.assert_original_mutex_released(original_mutex)

    def test_native_historical_aba_is_rejected_even_when_current_records_return_to_original(self):
        with self.case(indexed=True) as case:
            session = self.native_session(case)
            if session is None:
                self.assertNotEqual("win32", sys.platform)
                return
            before = self.image(case)
            original_mutex = case.account.owner._submission_lock
            old_receipt = session._receipt
            original_replay = risk.replay_events
            changed = []
            def replay(*args):
                result = original_replay(*args)
                deadline = locks.current_ledger_deadline(case.account.path)
                key = "syn-list-00000000"
                original = session.read_record(key, deadline=deadline)
                replacement = {**original, "operator_note": "synthetic-history-only"}
                session.cas_record(key, replacement, expected_record=original, deadline=deadline)
                session.cas_record(key, original, expected_record=replacement, deadline=deadline)
                self.assertEqual(original, session.read_record(key, deadline=deadline))
                self.assertGreater(session._receipt.revision, old_receipt.revision)
                changed.append(session._receipt)
                return result
            with patch.object(risk, "replay_events", side_effect=replay):
                with self.assertRaises(LiveTradingSafetyError):
                    self.read(case)
            self.assertEqual(1, len(changed))
            self.assertEqual(before, self.image(case))
            self.assert_original_mutex_released(original_mutex)

    def test_native_foreign_inactive_registry_rejects_before_any_connection_sql(self):
        for variant in ("owner", "pid", "closed", "pending"):
            with self.subTest(variant=variant), self.case(indexed=True) as case:
                session = self.native_session(case)
                if session is None:
                    self.assertNotEqual("win32", sys.platform)
                    continue
                before = self.image(case)
                original_mutex = case.account.owner._submission_lock
                field = "_" + variant
                old = getattr(session, field)
                changed = {"owner": object(), "pid": -1, "closed": True,
                           "pending": (session._receipt, session._receipt)}[variant]
                setattr(session, field, changed)
                try:
                    with patch.object(indexed_full, "_sql", wraps=indexed_full._sql) as sql, patch.object(
                            intents, "_read_ledger", wraps=intents._read_ledger) as full_reads:
                        with self.assertRaises(LiveTradingSafetyError):
                            self.read(case)
                    sql.assert_not_called()
                    full_reads.assert_not_called()
                finally:
                    setattr(session, field, old)
                self.assertEqual(before, self.image(case))
                self.assert_original_mutex_released(original_mutex)

    def test_native_physical_provenance_change_after_final_full_sql_and_native_probe_fences(self):
        for variant in ("manifest", "migration", "backup"):
            with self.subTest(variant=variant), self.case(indexed=True) as case:
                session = self.native_session(case)
                if session is None:
                    self.assertNotEqual("win32", sys.platform)
                    continue
                original_mutex = case.account.owner._submission_lock
                before = self.image(case)
                with self.locked(case):
                    original_sql = self.indexed_image(case, session)
                original_reader, original_guard = intents._read_ledger, session._guard
                real_full_reads, changed = [], []
                artifact = {"manifest": case.account.path,
                            "migration": locks.indexed_migration_fence_path(case.account.path),
                            "backup": session._backup.path}[variant]
                def reader(*args, **kwargs):
                    result = original_reader(*args, **kwargs)
                    real_full_reads.append(result.indexed_authority)
                    return result
                def guard():
                    original_guard()  # The genuine native probes precede the fault.
                    if len(real_full_reads) == 2 and not changed:
                        raw = artifact.read_bytes()
                        replacement = raw + b" " if variant != "backup" else raw[:-1] + b" "
                        self.assertNotEqual(raw, replacement)
                        artifact.write_bytes(replacement)
                        changed.append(replacement)
                with patch.object(intents, "_read_ledger", side_effect=reader), patch.object(
                        session, "_guard", side_effect=guard):
                    with self.assertRaises(LiveTradingSafetyError):
                        self.read(case)
                self.assertEqual(2, len(real_full_reads))
                self.assertEqual(real_full_reads[0], real_full_reads[1])
                self.assertEqual(1, len(changed))
                self.assertEqual(changed[0], artifact.read_bytes())
                after = self.image(case)
                self.assertEqual(before[1:], after[1:])
                if variant != "manifest":
                    self.assertEqual(before[0], after[0])
                with self.locked(case):
                    self.assertEqual(original_sql, self.indexed_image(case, session))
                self.assert_original_mutex_released(original_mutex)

    def test_native_inventory_checkpoint_change_during_final_full_sql_cannot_return_receipt(self):
        with self.case(indexed=True) as case:
            session = self.native_session(case)
            if session is None:
                self.assertNotEqual("win32", sys.platform)
                return
            before = self.image(case)
            original_mutex = case.account.owner._submission_lock
            original_reader = intents._read_ledger
            full_reads, changed = [], []
            def reader(*args, **kwargs):
                result = original_reader(*args, **kwargs)
                full_reads.append(result.indexed_authority)
                if len(full_reads) == 2:
                    key = next(iter(case.backend.store))
                    anchor = json.loads(case.backend.store[key])
                    anchor["head"]["revision"] += 1
                    case.backend.store[key] = inventory._compact(anchor)
                    changed.append(deepcopy(case.backend.store))
                return result
            with patch.object(intents, "_read_ledger", side_effect=reader):
                with self.assertRaises(LiveTradingSafetyError):
                    self.read(case)
            self.assertEqual(2, len(full_reads))
            self.assertEqual(full_reads[0], full_reads[1])
            self.assertEqual(1, len(changed))
            self.assertEqual(changed[0], case.backend.store)
            after = self.image(case)
            self.assertEqual(before[:4], after[:4])
            self.assertEqual(before[5:], after[5:])
            self.assert_original_mutex_released(original_mutex)

    def test_native_empty_temp_schema_and_extra_pager_are_checked_before_and_after_risk_replay(self):
        for phase in ("baseline", "risk"):
            for variant in ("temp_object", "attached"):
                with self.subTest(phase=phase, variant=variant), self.case(indexed=True) as case:
                    session = self.native_session(case)
                    if session is None:
                        self.assertNotEqual("win32", sys.platform)
                        continue
                    original_mutex = case.account.owner._submission_lock
                    before = self.image(case)
                    connection = session._connection
                    with self.locked(case):
                        original_sql = self.indexed_image(case, session)
                        original_version = connection.execute("PRAGMA data_version").fetchone()[0]
                        original_databases = tuple(connection.execute("PRAGMA database_list").fetchall())
                        self.assertEqual((1, "temp", ""), original_databases[1])
                        self.assertEqual(2, len(original_databases))
                        self.assertEqual([], connection.execute("SELECT name FROM sqlite_temp_master").fetchall())
                    original_changes = connection.total_changes
                    changed = []
                    def mutate():
                        if variant == "temp_object":
                            connection.execute("CREATE TEMP TABLE injected_temp(value TEXT)")
                            self.assertEqual(original_databases, tuple(connection.execute(
                                "PRAGMA database_list").fetchall()))
                            self.assertEqual([("injected_temp",)], connection.execute(
                                "SELECT name FROM sqlite_temp_master").fetchall())
                        else:
                            connection.execute("ATTACH DATABASE ':memory:' AS injected_pager")
                            self.assertEqual(original_databases, tuple(connection.execute(
                                "PRAGMA database_list").fetchall())[:2])
                            self.assertEqual(3, len(connection.execute("PRAGMA database_list").fetchall()))
                        self.assertEqual(original_changes, connection.total_changes)
                        self.assertEqual(original_version, connection.execute("PRAGMA data_version").fetchone()[0])
                        self.assertFalse(connection.in_transaction)
                        changed.append((phase, variant))
                    original_replay = risk.replay_events
                    def replay(*args):
                        result = original_replay(*args)
                        if phase == "risk":
                            mutate()
                        return result
                    try:
                        if phase == "baseline":
                            with self.locked(case):
                                mutate()
                        with patch.object(risk, "replay_events", side_effect=replay) as replay_call:
                            with self.assertRaises(LiveTradingSafetyError):
                                self.read(case)
                        self.assertEqual([(phase, variant)], changed)
                        if phase == "baseline":
                            replay_call.assert_not_called()
                        else:
                            replay_call.assert_called_once()
                        self.assertEqual(before, self.image(case))
                        with self.locked(case):
                            self.assertEqual(original_sql, self.indexed_image(case, session))
                        self.assert_original_mutex_released(original_mutex)
                    finally:
                        if variant == "temp_object":
                            connection.execute("DROP TABLE temp.injected_temp")
                        else:
                            connection.execute("DETACH DATABASE injected_pager")

    def test_account_path_uses_one_nofollow_directory_observation_before_and_after_risk_replay(self):
        for phase in ("baseline", "risk"):
            for mode in (0o100600, 0o120777):
                with self.subTest(phase=phase, mode=mode), self.case() as case:
                    target = case.account.path.parent
                    before = self.image(case)
                    original_mutex = case.account.owner._submission_lock
                    real_stat, real_lstat = owned.os.stat, owned.os.lstat
                    self.assertEqual(0o040000, real_stat(target).st_mode & 0o170000)
                    armed = [phase == "baseline"]
                    observations = []
                    def changed_metadata(path, result):
                        if armed[0] and isinstance(path, (str, Path)) and Path(path) == target:
                            observations.append(mode)
                            fields = list(result)
                            fields[0] = mode
                            return owned.os.stat_result(fields)
                        return result
                    def native_lstat(path, *args, **kwargs):
                        return changed_metadata(path, real_lstat(path, *args, **kwargs))
                    def native_stat(path, *args, **kwargs):
                        result = real_stat(path, *args, **kwargs)
                        return changed_metadata(path, result) if kwargs.get("follow_symlinks", True) is False else result
                    real_replay = risk.replay_events
                    def replay(*args):
                        result = real_replay(*args)
                        armed[0] = True
                        return result
                    with self.locked(case), patch.object(owned.os, "lstat", native_lstat), patch.object(
                            owned.os, "stat", native_stat), patch.object(risk, "replay_events", side_effect=replay) as replay_call:
                        if phase == "baseline":
                            # Old is-link plus follow-is-directory accepts a regular
                            # nofollow mode followed by this genuine directory mode.
                            self.assertEqual(mode & 0o170000, target.stat(follow_symlinks=False).st_mode & 0o170000)
                            self.assertEqual(0o040000, target.stat(follow_symlinks=True).st_mode & 0o170000)
                            with self.assertRaises(LiveTradingSafetyError):
                                owned._paths(case.account.wrapper)
                        with self.assertRaises(LiveTradingSafetyError):
                            owned.read_owned_spot_risk_store(case.account.wrapper)
                        self.assertGreater(len(observations), 0)
                        if phase == "baseline":
                            replay_call.assert_not_called()
                        else:
                            replay_call.assert_called_once()
                    self.assertEqual(before, self.image(case))
                    self.assert_original_mutex_released(original_mutex)

    def test_account_path_metadata_errors_and_cancellations_keep_original_failure_and_no_writes(self):
        for phase in ("baseline", "risk"):
            for failure_type in (FileNotFoundError, PermissionError, KeyboardInterrupt, SystemExit):
                with self.subTest(phase=phase, failure=failure_type.__name__), self.case() as case:
                    target = case.account.path.parent
                    before = self.image(case)
                    original_mutex = case.account.owner._submission_lock
                    primary = failure_type("synthetic owned directory metadata failure")
                    armed = [phase == "baseline"]
                    failures = []
                    real_lstat = Path.lstat
                    def fail_metadata(path):
                        if armed[0] and isinstance(path, (str, Path)) and Path(path) == target:
                            failures.append(primary)
                            raise primary
                    def native_lstat(path, *args, **kwargs):
                        fail_metadata(path)
                        return real_lstat(path, *args, **kwargs)
                    real_replay = risk.replay_events
                    def replay(*args):
                        result = real_replay(*args)
                        armed[0] = True
                        return result
                    expected_type = LiveTradingSafetyError if issubclass(failure_type, OSError) else failure_type
                    with self.locked(case), patch.object(Path, "lstat", native_lstat), patch.object(
                            risk, "replay_events", side_effect=replay) as replay_call:
                        with self.assertRaises(expected_type) as raised:
                            owned.read_owned_spot_risk_store(case.account.wrapper)
                        if issubclass(failure_type, OSError):
                            self.assertIs(primary, raised.exception.__cause__)
                        else:
                            self.assertIs(primary, raised.exception)
                        self.assertGreater(len(failures), 0)
                        self.assertTrue(all(value is primary for value in failures))
                        if phase == "baseline":
                            replay_call.assert_not_called()
                        else:
                            replay_call.assert_called_once()
                    self.assertEqual(before, self.image(case))
                    self.assert_original_mutex_released(original_mutex)

    def test_native_any_invalidation_key_fences_before_sql_and_after_actual_risk_replay(self):
        for phase in ("baseline", "risk"):
            for variant in ("none_payload", "fenced_owner"):
                with self.subTest(phase=phase, variant=variant), self.case(indexed=True) as case:
                    session = self.native_session(case)
                    if session is None:
                        self.assertNotEqual("win32", sys.platform)
                        continue
                    before = self.image(case)
                    original_mutex = case.account.owner._submission_lock
                    with self.locked(case):
                        original_sql = self.indexed_image(case, session)
                    path = case.account.path
                    with indexed._session_registry():
                        self.assertNotIn(path, indexed._INVALIDATIONS)
                    value = None if variant == "none_payload" else (
                        indexed.weakref.ref(case.account.owner), case.account.owner.generation,
                        "fenced", session._wrapper)
                    changed, sql_at_fault = [], []
                    real_replay = risk.replay_events
                    def invalidate():
                        with indexed._session_registry():
                            self.assertNotIn(path, indexed._INVALIDATIONS)
                            indexed._INVALIDATIONS[path] = value
                        changed.append(variant)
                        sql_at_fault.append(sql.call_count)
                    def replay(*args):
                        result = real_replay(*args)
                        if phase == "risk":
                            invalidate()
                        return result
                    try:
                        with patch.object(indexed_full, "_sql", wraps=indexed_full._sql) as sql, patch.object(
                                intents, "_read_ledger", wraps=intents._read_ledger) as full_reads, patch.object(
                                risk, "replay_events", side_effect=replay) as replay_call:
                            if phase == "baseline":
                                invalidate()
                            with self.assertRaises(LiveTradingSafetyError):
                                self.read(case)
                            self.assertEqual([variant], changed)
                            self.assertEqual([sql.call_count], sql_at_fault)
                            if phase == "baseline":
                                sql.assert_not_called()
                                full_reads.assert_not_called()
                                replay_call.assert_not_called()
                            else:
                                self.assertEqual(1, full_reads.call_count)
                                replay_call.assert_called_once()
                        with indexed._session_registry():
                            self.assertIn(path, indexed._INVALIDATIONS)
                            self.assertIs(value, indexed._INVALIDATIONS[path])
                            self.assertIs(session, indexed._SESSIONS[path])
                        self.assertFalse(session._closed)
                        self.assertEqual(before, self.image(case))
                        with self.locked(case):
                            self.assertEqual(original_sql, self.indexed_image(case, session))
                        self.assert_original_mutex_released(original_mutex)
                    finally:
                        with indexed._session_registry():
                            indexed._INVALIDATIONS.pop(path, None)
