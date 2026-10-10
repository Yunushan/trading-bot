"""Offline genuine-owner boundary controls; product caller integration is separate."""
from contextvars import copy_context
from copy import deepcopy
import json
import threading
from types import SimpleNamespace
import unittest
from unittest.mock import patch
import test_spot_inventory_namespace_integration as fixtures
from app.integrations.exchanges.binance.orders import spot_inventory_checkpoint as core
from app.integrations.exchanges.binance.orders import spot_inventory_checkpoint_runtime as runtime
from app.integrations.exchanges.binance.orders import spot_fill_recovery_runtime as fills
from app.integrations.exchanges.binance.orders.order_intent_store import ledger_transaction, ledger_transactions, write_ledger
from app.integrations.exchanges.binance.orders.spot_execution_owner import owner_administration_lock
from app.settings.live_safety import LiveTradingSafetyError


class SpotInventoryCheckpointRuntimeTests(unittest.TestCase):
    def setUp(self):
        self.f = fixtures.SpotInventoryNamespaceIntegrationTests("runTest")
        self.addCleanup(self.f.doCleanups)
        self.f.setUp()
        self.store, self.puts = {}, []
        self.enterContext(patch.object(core, "_windows_read_adapter", return_value=True))
        self.enterContext(patch.object(core.credential_store, "credential_store_backend", return_value="windows-credential-manager"))
        self.enterContext(patch.object(core.credential_store, "get_secret", side_effect=self.get))
        self.enterContext(patch.object(core.credential_store, "put_secret", side_effect=self.put))
        self.enterContext(patch.object(core.credential_store, "delete_secret", side_effect=AssertionError("No OS store deletion")))

    def get(self, *, scope, account):
        self.assertEqual("spot-inventory-checkpoint-v1", scope)
        return self.store.get((scope, account), "")

    def put(self, *, scope, account, value):
        self.assertEqual("spot-inventory-checkpoint-v1", scope)
        self.store[scope, account] = value
        self.puts.append(value)

    def account(self, accepted=False):
        return self.f.account("checkpoint", 880001, accepted=accepted)

    def prepared(self):
        account = self.account()
        with self.f.account_home(account):
            self.assertTrue(runtime.bootstrap_owned_inventory_checkpoint(account.wrapper, allocation_path=self.f.path))
        record = self.f.author_accepted(account, self.f.fill)
        prepared = self.f.home / "prepared.json"
        fills.persist_spot_buy_allocation(prepared, self.f.fill)
        candidate = json.loads(prepared.read_text(encoding="utf-8"))
        candidate["spot_account_namespace"] = deepcopy(account.namespace)
        return account, record, candidate

    def publication(self, account, record):
        return runtime.owned_inventory_publication(account.wrapper, allocation_path=self.f.path,
                                                   expected_record=record, fill=self.f.fill)

    def before(self, account):
        return self.f.durable_bytes(account), deepcopy(self.store), list(self.puts)

    def test_empty_bootstrap_repeat_is_read_only(self):
        account = self.account()
        before = self.f.ledger(account)
        with self.f.account_home(account):
            self.assertTrue(runtime.bootstrap_owned_inventory_checkpoint(account.wrapper, allocation_path=self.f.path))
            stable = self.before(account)
            self.assertFalse(runtime.bootstrap_owned_inventory_checkpoint(account.wrapper, allocation_path=self.f.path))
            self.assertEqual(stable, self.before(account))
        self.assertEqual(before, self.f.ledger(account))
        self.assertEqual([], self.f.order_calls)

    def test_nonempty_history_cannot_bootstrap_absent_source(self):
        account = self.account(True)
        before = self.before(account)
        with self.f.account_home(account), self.assertRaises(LiveTradingSafetyError):
            runtime.bootstrap_owned_inventory_checkpoint(account.wrapper, allocation_path=self.f.path)
        self.assertEqual(before, self.before(account))

    def test_bound_empty_source_without_checkpoint_is_not_resealed(self):
        account = self.account()
        with ledger_transaction(self.f.path):
            write_ledger(self.f.path, {"version": 1, "mode": "Live", "entry_allocations": {},
                                      "open_position_records": {}, "spot_account_namespace": account.namespace})
        before = self.before(account)
        with self.f.account_home(account), self.assertRaises(LiveTradingSafetyError):
            runtime.bootstrap_owned_inventory_checkpoint(account.wrapper, allocation_path=self.f.path)
        self.assertEqual(before, self.before(account))

    def test_matching_metadata_and_detached_writer_grant_nothing(self):
        account, record, candidate = self.prepared()
        before = self.before(account)
        with self.assertRaises(LiveTradingSafetyError):
            runtime.write_owned_inventory_checkpoint(self.f.path, candidate)
        self.assertEqual(before, self.before(account))
        self.assertEqual(record, self.f.ledger(account)["intents"][record["client_order_id"]])

    def test_changed_record_or_fill_never_issues_context(self):
        account, record, candidate = self.prepared()
        before = self.before(account)
        cases = (({**record, "updated_at": "changed"}, self.f.fill),
                 (record, {**self.f.fill, "client_order_id": "foreign"}))
        for changed, fill in cases:
            with self.subTest(changed_record=changed != record), self.f.account_home(account), self.assertRaises(LiveTradingSafetyError):
                with runtime.owned_inventory_publication(account.wrapper, allocation_path=self.f.path,
                                                         expected_record=changed, fill=fill):
                    self.fail("Detached context admitted")
        self.assertEqual(before, self.before(account))

    def test_canonical_candidate_advances_once_without_marker(self):
        account, record, candidate = self.prepared()
        before = self.f.durable_bytes(account)[1:]
        with self.f.account_home(account), self.publication(account, record):
            runtime.write_owned_inventory_checkpoint(self.f.path, candidate)
            with self.assertRaises(LiveTradingSafetyError):
                runtime.write_owned_inventory_checkpoint(self.f.path, candidate)
        self.assertEqual(candidate, json.loads(self.f.path.read_text(encoding="utf-8")))
        self.assertEqual(before, self.f.durable_bytes(account)[1:])
        self.assertEqual([], self.f.order_calls)

    def test_replaced_owner_or_client_fences_original_context(self):
        account, record, candidate = self.prepared()
        for field in ("client", "_spot_execution_owner"):
            before, original = self.before(account), getattr(account.wrapper, field)
            with self.subTest(field=field), self.f.account_home(account), self.assertRaises(LiveTradingSafetyError):
                with self.publication(account, record):
                    setattr(account.wrapper, field, object())
                    try:
                        runtime.write_owned_inventory_checkpoint(self.f.path, candidate)
                    finally:
                        setattr(account.wrapper, field, original)
            self.assertEqual(before, self.before(account))

    def test_foreign_thread_and_expired_copied_context_cannot_write(self):
        account, record, candidate = self.prepared()
        before, outcomes = self.before(account), []
        with self.f.account_home(account), self.publication(account, record):
            copied = copy_context()
            def call():
                try:
                    copied.run(runtime.write_owned_inventory_checkpoint, self.f.path, candidate)
                except BaseException as exc:
                    outcomes.append(exc)
            worker = threading.Thread(target=call)
            worker.start()
            worker.join(timeout=2)
            self.assertFalse(worker.is_alive())
            self.assertEqual(1, len(outcomes))
            self.assertIsInstance(outcomes[0], LiveTradingSafetyError)
        with self.assertRaises(LiveTradingSafetyError):
            copied.run(runtime.write_owned_inventory_checkpoint, self.f.path, candidate)
        self.assertEqual(before, self.before(account))

    def test_body_cancellation_retains_identity_and_revokes_context(self):
        account, record, candidate = self.prepared()
        before, error = self.before(account), KeyboardInterrupt("fixture cancellation")
        with self.f.account_home(account), self.assertRaises(KeyboardInterrupt) as caught:
            with self.publication(account, record):
                copied = copy_context()
                raise error
        self.assertIs(error, caught.exception)
        with self.assertRaises(LiveTradingSafetyError):
            copied.run(runtime.write_owned_inventory_checkpoint, self.f.path, candidate)
        self.assertEqual(before, self.before(account))

    def test_noncanonical_path_never_reads_or_writes_protected_slot(self):
        account = self.account()
        before = self.before(account)
        with self.f.account_home(account), self.assertRaises(LiveTradingSafetyError):
            runtime.bootstrap_owned_inventory_checkpoint(account.wrapper, allocation_path=self.f.home / "other.json")
        self.assertEqual(before, self.before(account))

    def test_pending_failure_consumes_attempt_and_fresh_context_recovers_exact_target(self):
        account, record, candidate = self.prepared()
        old_source, ledger, marker = self.f.durable_bytes(account)
        puts = len(self.puts)
        with self.f.account_home(account), self.assertRaises(LiveTradingSafetyError):
            with self.publication(account, record):
                with patch.object(core, "_finish", side_effect=OSError("offline prepared crash")):
                    with self.assertRaises(LiveTradingSafetyError):
                        runtime.write_owned_inventory_checkpoint(self.f.path, candidate)
                with self.assertRaises(LiveTradingSafetyError):
                    runtime.write_owned_inventory_checkpoint(self.f.path, candidate)
                self.assertEqual(puts + 1, len(self.puts))
        self.assertEqual(old_source, self.f.path.read_bytes())
        self.assertEqual("pending", json.loads(self.puts[-1])["state"])
        with self.f.account_home(account), self.publication(account, record):
            self.assertEqual(candidate, json.loads(self.f.path.read_bytes()))
            self.assertEqual("stable", json.loads(self.puts[-1])["state"])
        self.assertEqual((ledger, marker), self.f.durable_bytes(account)[1:])
        self.assertEqual([], self.f.order_calls)

    def test_ambiguous_stable_failure_cannot_repeat_in_original_context(self):
        account, record, candidate = self.prepared()
        ledger_and_marker = self.f.durable_bytes(account)[1:]
        original = core._put
        def put_then_fail(path, deadline, protected, *, expected):
            result = original(path, deadline, protected, expected=expected)
            if protected["state"] == "stable":
                raise OSError("offline lost completion after protected commit")
            return result
        with self.f.account_home(account), self.publication(account, record):
            with patch.object(core, "_put", side_effect=put_then_fail), self.assertRaises(LiveTradingSafetyError):
                runtime.write_owned_inventory_checkpoint(self.f.path, candidate)
            committed = self.before(account)
            with self.assertRaises(LiveTradingSafetyError):
                runtime.write_owned_inventory_checkpoint(self.f.path, candidate)
            self.assertEqual(committed, self.before(account))
        with self.f.account_home(account), self.publication(account, record):
            self.assertEqual(candidate, json.loads(self.f.path.read_bytes()))
        self.assertEqual(ledger_and_marker, self.f.durable_bytes(account)[1:])

    def administrator(self, account):
        account.owner.close()
        wrapper = account.wrapper
        administrator = SimpleNamespace(api_key=wrapper.api_key, api_secret=wrapper.api_secret,
            client=wrapper.client, mode="Live", account_type="SPOT", _enforce_spot_execution_owner=True,
            _operator_spot_account_uid=account.uid, _order_audit_log_path=account.home / "audit.jsonl",
            _spot_inventory_administration_path=account.path,
            _verified_spot_account_context=wrapper._verified_spot_account_context)
        return administrator

    def test_held_signed_administrator_can_publish_full_current_record(self):
        account, record, candidate = self.prepared()
        admin = self.administrator(account)
        ledger_and_marker = self.f.durable_bytes(account)[1:]
        with self.f.account_home(account), owner_administration_lock(account.path):
            with runtime.owned_inventory_publication(admin, allocation_path=self.f.path,
                    expected_record=record, fill=self.f.fill):
                runtime.write_owned_inventory_checkpoint(self.f.path, candidate)
        self.assertEqual(candidate, json.loads(self.f.path.read_bytes()))
        self.assertEqual(ledger_and_marker, self.f.durable_bytes(account)[1:])
        self.assertEqual([], self.f.order_calls)

    def test_replacement_administration_cannot_reuse_original_context(self):
        account, record, candidate = self.prepared()
        admin = self.administrator(account)
        before = self.before(account)
        with self.f.account_home(account):
            original = owner_administration_lock(account.path)
            original.__enter__()
            with self.assertRaises(LiveTradingSafetyError):
                with runtime.owned_inventory_publication(admin, allocation_path=self.f.path,
                        expected_record=record, fill=self.f.fill):
                    original.__exit__(None, None, None)
                    with owner_administration_lock(account.path):
                        runtime.write_owned_inventory_checkpoint(self.f.path, candidate)
        self.assertEqual(before, self.before(account))

    def test_administrator_metadata_without_actual_exclusion_grants_nothing(self):
        account, record, _candidate = self.prepared()
        admin = self.administrator(account)
        before = self.before(account)
        with self.f.account_home(account), self.assertRaises(LiveTradingSafetyError):
            with runtime.owned_inventory_publication(admin, allocation_path=self.f.path,
                    expected_record=record, fill=self.f.fill):
                self.fail("Detached administrator was admitted")
        self.assertEqual(before, self.before(account))

    def test_concurrent_close_waits_for_original_publication_lifetime(self):
        account, record, candidate = self.prepared()
        before_ledger = self.f.durable_bytes(account)[1]
        attempted, closed, outcomes = threading.Event(), threading.Event(), []
        original = account.owner._submission_lock
        class ObservedLock:
            def acquire(self, *args, **kwargs):
                return original.acquire(*args, **kwargs)
            def release(self):
                original.release()
            def __enter__(self):
                attempted.set()
                original.acquire()
                return self
            def __exit__(self, *_args):
                original.release()
        def close():
            try:
                account.owner.close()
                closed.set()
            except BaseException as exc:
                outcomes.append(exc)
        worker = threading.Thread(target=close)
        with patch.object(account.owner, "_submission_lock", ObservedLock()):
            with self.f.account_home(account), self.publication(account, record):
                worker.start()
                self.assertTrue(attempted.wait(timeout=2))
                self.assertFalse(closed.is_set())
                runtime.write_owned_inventory_checkpoint(self.f.path, candidate)
                self.assertFalse(closed.is_set())
            worker.join(timeout=2)
            self.assertFalse(worker.is_alive())
        self.assertEqual([], outcomes)
        self.assertTrue(closed.is_set())
        self.assertEqual(candidate, json.loads(self.f.path.read_bytes()))
        self.assertEqual(before_ledger, self.f.durable_bytes(account)[1])

    def test_busy_owner_fails_without_storage_lock_inversion(self):
        account, record, _candidate = self.prepared()
        before = self.before(account)
        held, release, outcomes = threading.Event(), threading.Event(), []
        def hold():
            try:
                with account.owner._submission_lock:
                    held.set()
                    if not release.wait(timeout=2):
                        raise AssertionError("Bounded owner control was not released")
            except BaseException as exc:
                outcomes.append(exc)
        worker = threading.Thread(target=hold)
        worker.start()
        try:
            self.assertTrue(held.wait(timeout=2))
            with self.f.account_home(account), ledger_transactions(account.path, self.f.path):
                with self.assertRaises(LiveTradingSafetyError):
                    with self.publication(account, record):
                        self.fail("Busy owner was admitted under storage locks")
        finally:
            release.set()
            worker.join(timeout=2)
        self.assertFalse(worker.is_alive())
        self.assertEqual([], outcomes)
        self.assertEqual(before, self.before(account))

    def test_reentrant_close_during_protected_put_fences_before_inventory_write(self):
        account, record, candidate = self.prepared()
        source, ledger, _marker = self.f.durable_bytes(account)
        def close_after_put(**kwargs):
            self.put(**kwargs)
            account.owner.close()
        with self.f.account_home(account), self.assertRaises(LiveTradingSafetyError):
            with self.publication(account, record):
                with patch.object(core.credential_store, "put_secret", side_effect=close_after_put):
                    runtime.write_owned_inventory_checkpoint(self.f.path, candidate)
        self.assertEqual(source, self.f.path.read_bytes())
        self.assertEqual(ledger, self.f.durable_bytes(account)[1])
        self.assertEqual("pending", json.loads(self.puts[-1])["state"])
        self.assertEqual([], self.f.order_calls)

    def test_record_change_during_protected_put_fences_before_inventory_write(self):
        account, record, candidate = self.prepared()
        source = self.f.path.read_bytes()
        def change_after_put(**kwargs):
            self.put(**kwargs)
            payload = self.f.ledger(account)
            payload["intents"][record["client_order_id"]]["updated_at"] = "2026-10-04T01:00:00+00:00"
            with ledger_transaction(account.path):
                write_ledger(account.path, payload)
        with self.f.account_home(account), self.assertRaises(LiveTradingSafetyError):
            with self.publication(account, record):
                with patch.object(core.credential_store, "put_secret", side_effect=change_after_put):
                    runtime.write_owned_inventory_checkpoint(self.f.path, candidate)
        self.assertEqual(source, self.f.path.read_bytes())
        self.assertEqual("pending", json.loads(self.puts[-1])["state"])
        self.assertNotEqual(record, self.f.ledger(account)["intents"][record["client_order_id"]])
        self.assertEqual([], self.f.order_calls)

    def test_explicit_empty_bootstrap_recovery_finishes_pinned_first_write(self):
        account = self.account()
        before_ledger_and_marker = self.f.durable_bytes(account)[1:]
        with self.f.account_home(account):
            with patch.object(core, "_finish", side_effect=OSError("offline empty bootstrap crash")):
                with self.assertRaises(LiveTradingSafetyError):
                    runtime.bootstrap_owned_inventory_checkpoint(account.wrapper, allocation_path=self.f.path)
            self.assertFalse(self.f.path.exists())
            pending = json.loads(self.puts[-1])
            target = json.loads((self.f.path.parent / pending["journal"]).read_bytes())
            with self.assertRaises(LiveTradingSafetyError):
                runtime.bootstrap_owned_inventory_checkpoint(account.wrapper, allocation_path=self.f.path)
            self.assertTrue(runtime.recover_owned_inventory_bootstrap(account.wrapper, allocation_path=self.f.path))
            self.assertFalse(runtime.recover_owned_inventory_bootstrap(account.wrapper, allocation_path=self.f.path))
        self.assertEqual(target, json.loads(self.f.path.read_bytes()))
        self.assertEqual(before_ledger_and_marker, self.f.durable_bytes(account)[1:])
        self.assertEqual([], self.f.order_calls)

    def test_pending_bootstrap_cannot_finish_after_history_becomes_nonempty(self):
        account = self.account()
        with self.f.account_home(account), patch.object(core, "_finish", side_effect=OSError("offline bootstrap crash")):
            with self.assertRaises(LiveTradingSafetyError):
                runtime.bootstrap_owned_inventory_checkpoint(account.wrapper, allocation_path=self.f.path)
        self.f.author_accepted(account, self.f.fill)
        before = self.before(account)
        with self.f.account_home(account), self.assertRaises(LiveTradingSafetyError):
            runtime.recover_owned_inventory_bootstrap(account.wrapper, allocation_path=self.f.path)
        self.assertEqual(before, self.before(account))
        self.assertFalse(self.f.path.exists())

    def test_pending_inspection_is_read_only_and_explicit_exact_recovery_precedes_reload(self):
        account, record, candidate = self.prepared()
        ledger_marker = self.f.durable_bytes(account)[1:]
        with self.f.account_home(account), self.assertRaises(LiveTradingSafetyError):
            with self.publication(account, record), patch.object(core, "_finish", side_effect=OSError("prepared crash")):
                runtime.write_owned_inventory_checkpoint(self.f.path, candidate)
        before = self.before(account)
        with self.f.account_home(account):
            operation = runtime.inspect_owned_pending_inventory_operation(account.wrapper, self.f.path)
            self.assertEqual(runtime.inventory_publication_operation_hash(account.namespace, record, self.f.fill), operation)
            self.assertEqual(before, self.before(account))
            with ledger_transaction(self.f.path), self.assertRaises(LiveTradingSafetyError):
                raw = self.f.path.read_bytes()
                core.verify_inventory_checkpoint(self.f.path, raw, json.loads(raw), expected_namespace=account.namespace)
            runtime.recover_owned_inventory_publication(account.wrapper, self.f.path, expected_record=record, fill=self.f.fill)
            self.assertIsNone(runtime.inspect_owned_pending_inventory_operation(account.wrapper, self.f.path))
        self.assertEqual(candidate, json.loads(self.f.path.read_text(encoding="utf-8")))
        self.assertEqual(ledger_marker, self.f.durable_bytes(account)[1:])
        self.assertEqual([], self.f.order_calls)

    def test_pending_wrong_event_or_missing_exact_journal_never_adopts_or_resets(self):
        account, record, candidate = self.prepared()
        with self.f.account_home(account), self.assertRaises(LiveTradingSafetyError):
            with self.publication(account, record), patch.object(core, "_finish", side_effect=OSError("prepared crash")):
                runtime.write_owned_inventory_checkpoint(self.f.path, candidate)
        before = self.before(account)
        with self.f.account_home(account), self.assertRaises(LiveTradingSafetyError):
            runtime.recover_owned_inventory_publication(account.wrapper, self.f.path, expected_record=record,
                                                         fill={**self.f.fill, "signature": "f" * 64})
        self.assertEqual(before, self.before(account))
        protected = core._record(self.f.path, next(iter(self.store.values())))
        journal = core._journal(self.f.path, protected)
        journal.unlink()
        before = self.before(account)
        with self.f.account_home(account), self.assertRaises(LiveTradingSafetyError):
            runtime.inspect_owned_pending_inventory_operation(account.wrapper, self.f.path)
        self.assertEqual(before, self.before(account))

    def test_producer_assertion_requires_original_active_event_before_replay(self):
        account, record, _candidate = self.prepared()
        before = self.before(account)
        with self.assertRaises(LiveTradingSafetyError):
            runtime.assert_owned_inventory_publication(self.f.path, fill=self.f.fill)
        with self.f.account_home(account), self.publication(account, record):
            runtime.assert_owned_inventory_publication(self.f.path, fill=self.f.fill)
            with self.assertRaises(LiveTradingSafetyError):
                runtime.assert_owned_inventory_publication(self.f.path, fill={**self.f.fill, "client_order_id": "other-event"})
        self.assertEqual(before, self.before(account))
