"""Offline tests: all protected-store calls use one isolated fake backend."""
from __future__ import annotations

import copy
import hashlib
import json
import os
import tempfile
import time
import threading
from contextvars import copy_context
import unittest
from pathlib import Path
from unittest.mock import patch
from uuid import uuid4

from app.integrations.exchanges.binance.orders import spot_inventory_checkpoint as core
from app.integrations.exchanges.binance.orders.order_intent_store import ledger_transaction
from app.integrations.exchanges.binance.orders.spot_inventory_namespace import ACCOUNT_NAMESPACE_KEY, make_namespace
from app.settings.live_safety import LiveTradingSafetyError


class SpotInventoryCheckpointTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="spot-checkpoint-test-")
        self.addCleanup(self.temp.cleanup)
        self.path = Path(self.temp.name) / "inventory.json"
        self.namespace = make_namespace(101, str(uuid4()))
        self.values, self.calls = {}, []
        adapter = patch.object(core, "_windows_read_adapter", return_value=True)
        adapter.start()
        self.addCleanup(adapter.stop)
        for name, kwargs in (
            ("credential_store_backend", {"return_value": "windows-credential-manager"}),
            ("get_secret", {"side_effect": self.get}), ("put_secret", {"side_effect": self.put}),
            ("delete_secret", {"side_effect": AssertionError("No reset API permitted")}),
        ):
            patcher = patch.object(core.credential_store, name, **kwargs)
            patcher.start()
            self.addCleanup(patcher.stop)
        self.empty = {"version": 1, "mode": "Live", "entry_allocations": {}, "open_position_records": {}}
        self.bound = {**copy.deepcopy(self.empty), ACCOUNT_NAMESPACE_KEY: self.namespace}

    def get(self, *, scope, account):
        self.calls.append(("get", scope, account))
        return self.values.get((scope, account), "")

    def put(self, *, scope, account, value):
        self.calls.append(("put", scope, account))
        self.values[scope, account] = value

    def protected(self):
        self.assertEqual(1, len(self.values))
        return json.loads(next(iter(self.values.values())))

    def raw(self):
        return self.path.read_bytes() if self.path.exists() else None

    def snapshot(self):
        return json.loads(self.raw()) if self.raw() is not None else None

    def bootstrap(self, previous=None):
        if previous is not None:
            self.path.write_bytes(core._encode(previous))
        with ledger_transaction(self.path):
            self.assertTrue(core._bootstrap_inventory_checkpoint(
                self.path, self.raw(), self.snapshot(), self.bound, self.namespace, "bootstrap"))
        return self.raw()

    def candidate(self):
        result = copy.deepcopy(self.snapshot())
        result["entry_allocations"] = {"BTCUSDT:L": [{"client_order_id": "owned-buy", "qty": "0.1", "status": "Active"}]}
        result["open_position_records"] = {"BTCUSDT:L": {"status": "Active", "data": {"qty": "0.1"}, "allocations": copy.deepcopy(result["entry_allocations"]["BTCUSDT:L"])}}
        result["timestamp"] = 123.25
        return result

    def publish(self, candidate=None):
        with ledger_transaction(self.path):
            return core._publish_inventory_checkpoint(self.path, self.raw(), self.snapshot(),
                self.candidate() if candidate is None else candidate, self.namespace, "buy")

    def verify(self, namespace=None):
        with ledger_transaction(self.path):
            return core.verify_inventory_checkpoint(self.path, self.raw(), self.snapshot(), namespace)

    def recover(self, operation="buy", namespace=None):
        with ledger_transaction(self.path):
            return core._recover_inventory_checkpoint(self.path, self.namespace if namespace is None else namespace, operation)

    def pending(self, published=False):
        before = self.raw()
        actual = core.write_ledger
        def fail(path, payload):
            if published:
                actual(path, payload)
            raise OSError("source publication failure")
        with patch.object(core, "write_ledger", side_effect=fail), self.assertRaises(LiveTradingSafetyError):
            self.publish()
        self.assertEqual("pending", self.protected()["state"])
        self.assertEqual(not published, self.raw() == before)
        return self.protected()

    def test_non_windows_only_ordinary_unbound_reads_keep_legacy_compatibility(self):
        with patch.object(core, "_windows_read_adapter", return_value=False):
            with patch.object(core.credential_store, "get_secret", side_effect=AssertionError("No native protected read")):
                with patch.object(core.credential_store, "put_secret", side_effect=AssertionError("No native protected write")):
                    self.assertFalse(self.verify())
                    for mode in ("Paper", "Testnet", "Live"):
                        self.path.write_bytes(core._encode({**self.empty, "mode": mode}))
                        self.assertFalse(self.verify())
                    with self.assertRaises(LiveTradingSafetyError):
                        self.verify(self.namespace)
                    self.path.write_bytes(core._encode(self.bound))
                    with self.assertRaises(LiveTradingSafetyError):
                        self.verify()
                    self.path.write_bytes(b"{invalid")
                    with ledger_transaction(self.path), self.assertRaises(LiveTradingSafetyError):
                        core.verify_inventory_checkpoint(self.path, self.raw(), {})
                    self.path.unlink()
                    with ledger_transaction(self.path):
                        with patch.object(core.os, "getpid", return_value=os.getpid() + 1), self.assertRaises(LiveTradingSafetyError):
                            core.verify_inventory_checkpoint(self.path, None, None)
                        with patch.object(core.time, "monotonic", return_value=time.monotonic() + 100), self.assertRaises(LiveTradingSafetyError):
                            core.verify_inventory_checkpoint(self.path, None, None)
        self.assertFalse(self.values)

    def test_non_windows_private_writers_and_recovery_reject_before_protected_io(self):
        with patch.object(core, "_windows_read_adapter", return_value=False):
            with ledger_transaction(self.path):
                for operation, args in (
                    (core._bootstrap_inventory_checkpoint, (self.path, None, None, self.bound, self.namespace, "bootstrap")),
                    (core._publish_inventory_checkpoint, (self.path, None, None, self.bound, self.namespace, "buy")),
                    (core._recover_inventory_checkpoint, (self.path, self.namespace, "buy")),
                ):
                    with self.subTest(operation=operation.__name__), self.assertRaises(LiveTradingSafetyError):
                        operation(*args)
        self.assertFalse(self.calls)
        self.assertFalse(self.values)
        self.assertFalse(self.path.exists())

    def test_windows_queries_path_slot_even_missing_unbound_or_changed_mode(self):
        self.bootstrap()
        protected = dict(self.values)
        for snapshot in (None, self.empty, {**self.empty, "mode": "Paper"}):
            with self.subTest(snapshot=snapshot):
                self.path.unlink(missing_ok=True)
                if snapshot is not None:
                    self.path.write_bytes(core._encode(snapshot))
                self.calls.clear()
                with patch.object(core, "_windows_read_adapter", return_value=True), self.assertRaises(LiveTradingSafetyError):
                    self.verify()
                self.assertEqual("get", self.calls[0][0])
                self.assertEqual(protected, self.values)

    def test_actual_native_moved_journal_read_and_in_read_change(self):
        self.bootstrap()
        candidate = core._encode(self.candidate())
        with ledger_transaction(self.path):
            deadline = core.current_ledger_deadline(self.path)
            journal = self.path.parent / "native-journal.json"
            core._write_journal(self.path, deadline, journal, candidate)
            for _ in range(3):
                self.assertEqual(candidate, core._read(journal, deadline))
            actual_fstat, count = core.os.fstat, 0
            def change(fd):
                nonlocal count
                count += 1
                if count == 2:
                    journal.write_bytes(candidate + b" ")
                return actual_fstat(fd)
            with patch.object(core.os, "fstat", side_effect=change), self.assertRaises(ValueError):
                core._read(journal, deadline)

    def test_missing_unbound_verification_never_mints(self):
        self.assertFalse(self.verify())
        for mode in ("Live", "Paper", "Testnet"):
            self.path.write_bytes(core._encode({**self.empty, "mode": mode}))
            self.assertFalse(self.verify())
        self.assertFalse(self.values)
        self.assertFalse(any(c[0] == "put" for c in self.calls))

    def test_bootstrap_publish_exact_encoding_detachment_and_noop_recovery(self):
        for previous in (None, self.empty):
            with self.subTest(previous=previous):
                self.values.clear()
                self.path.unlink(missing_ok=True)
                self.bootstrap(previous)
                self.assertTrue(self.verify(self.namespace))
                candidate = self.candidate()
                copied = copy.deepcopy(candidate)
                self.assertTrue(self.publish(candidate))
                self.assertEqual(copied, candidate)
                self.assertEqual(core._encode(candidate), self.raw())
                self.assertEqual({"revision": 2, "digest": hashlib.sha256(self.raw()).hexdigest()}, self.protected()["head"])
                self.assertFalse(list(self.path.parent.glob(".spot-inventory-*.json")))
                self.assertTrue(self.verify())
                self.assertFalse(self.recover())

    def test_bootstrap_cannot_seal_bound_empty_nonempty_or_existing_authority(self):
        for previous in (self.bound, {**self.empty, "entry_allocations": {"BTCUSDT:L": [{}]}}):
            with self.subTest(previous=previous):
                self.path.write_bytes(core._encode(previous))
                before = self.raw()
                with ledger_transaction(self.path), self.assertRaises(LiveTradingSafetyError):
                    core._bootstrap_inventory_checkpoint(self.path, before, previous, self.bound, self.namespace, "bootstrap")
                self.assertEqual(before, self.raw())
                self.assertFalse(self.values)
        self.path.unlink()
        self.bootstrap()
        protected = dict(self.values)
        with ledger_transaction(self.path), self.assertRaises(LiveTradingSafetyError):
            core._bootstrap_inventory_checkpoint(self.path, self.raw(), self.snapshot(), self.bound, self.namespace, "bootstrap")
        self.assertEqual(protected, self.values)

    def test_bound_without_authority_cannot_be_verified_or_reseeded(self):
        self.path.write_bytes(core._encode(self.bound))
        with self.assertRaises(LiveTradingSafetyError):
            self.verify()
        with self.assertRaises(LiveTradingSafetyError):
            self.publish()
        self.assertFalse(self.values)

    def test_coherent_rollback_deletion_and_namespace_stripping_fence(self):
        initial = self.bootstrap()
        self.publish()
        latest, protected = self.raw(), dict(self.values)
        for old in (initial, None, core._encode(self.empty)):
            with self.subTest(old=old):
                self.path.unlink(missing_ok=True)
                if old is not None:
                    self.path.write_bytes(old)
                with self.assertRaises(LiveTradingSafetyError):
                    self.verify()
                with self.assertRaises(LiveTradingSafetyError):
                    self.recover()
                self.assertEqual(protected, self.values)
        self.path.write_bytes(latest)
        self.assertTrue(self.verify())

    def test_same_namespace_copy_and_changed_uid_store(self):
        self.bootstrap()
        self.assertTrue(self.verify(copy.deepcopy(self.namespace)))
        for other in (make_namespace(102, self.namespace["store_id"]), make_namespace(101, str(uuid4()))):
            with self.subTest(other=other), self.assertRaises(LiveTradingSafetyError):
                self.verify(other)
        self.assertEqual(1, len(self.values))

    def test_pending_old_and_target_only_recover_exact_prepared_candidate(self):
        for published in (False, True):
            with self.subTest(published=published):
                self.values.clear()
                self.path.unlink(missing_ok=True)
                self.bootstrap()
                pending = self.pending(published)
                target = (self.path.parent / pending["journal"]).read_bytes()
                with self.assertRaises(LiveTradingSafetyError):
                    self.verify()
                self.assertTrue(self.recover())
                self.assertEqual(target, self.raw())
                self.assertEqual(pending["target"], self.protected()["head"])
                self.assertTrue(self.verify())
                self.assertFalse(self.recover())

    def test_pending_changed_operation_namespace_or_third_source_never_adopts(self):
        self.bootstrap()
        self.pending()
        protected = dict(self.values)
        for operation, namespace in (("other", self.namespace), ("buy", make_namespace(102, str(uuid4())))):
            with self.subTest(operation=operation), self.assertRaises(LiveTradingSafetyError):
                self.recover(operation, namespace)
        self.path.write_bytes(core._encode({**self.bound, "timestamp": 999}))
        with self.assertRaises(LiveTradingSafetyError):
            self.recover()
        self.assertEqual(protected, self.values)

    def test_pending_missing_corrupt_hardlink_and_symlink_journal_fence(self):
        for damage in ("missing", "corrupt", "hardlink", "symlink"):
            with self.subTest(damage=damage):
                self.values.clear()
                self.path.unlink(missing_ok=True)
                self.bootstrap()
                pending = self.pending()
                journal = self.path.parent / pending["journal"]
                other = self.path.parent / "other.json"
                other.write_bytes(journal.read_bytes())
                journal.unlink()
                if damage == "corrupt":
                    journal.write_bytes(b"{}")
                elif damage == "hardlink":
                    os.link(other, journal)
                elif damage == "symlink":
                    try:
                        journal.symlink_to(other)
                    except OSError:
                        continue  # Symlink privilege unavailable; hardlink assertion still executes.
                protected = dict(self.values)
                with self.assertRaises(LiveTradingSafetyError):
                    self.recover()
                self.assertEqual(protected, self.values)
                journal.unlink(missing_ok=True)
                other.unlink()

    def test_protected_write_persisted_then_raised_retains_known_uncertainty(self):
        self.bootstrap()
        for state in ("pending", "stable"):
            with self.subTest(state=state):
                candidate = self.candidate()
                candidate["timestamp"] += 1
                def fail(**kwargs):
                    self.put(**kwargs)
                    if json.loads(kwargs["value"])["state"] == state:
                        raise OSError("protected write persisted before error")
                with patch.object(core.credential_store, "put_secret", side_effect=fail), self.assertRaises(LiveTradingSafetyError):
                    self.publish(candidate)
                self.assertTrue(list(self.path.parent.glob(".spot-inventory-*.json")))
                if state == "pending":
                    with self.assertRaises(LiveTradingSafetyError):
                        self.verify()
                    self.assertTrue(self.recover())
                else:
                    self.assertTrue(self.verify())
                    self.assertFalse(self.recover())

    def test_stale_protected_readback_leaves_source_old_and_pending_recoverable(self):
        old = self.bootstrap()
        def stale(**kwargs):
            value = self.get(**kwargs)
            return "" if value and json.loads(value)["state"] == "pending" else value
        with patch.object(core.credential_store, "get_secret", side_effect=stale), self.assertRaises(LiveTradingSafetyError):
            self.publish()
        self.assertEqual(old, self.raw())
        self.assertEqual("pending", self.protected()["state"])
        self.assertTrue(self.recover())

    def test_primary_cancellations_preserve_identity_without_resetting_authority(self):
        self.bootstrap()
        for place, kind in (("put", KeyboardInterrupt), ("write", SystemExit)):
            with self.subTest(place=place):
                interruption = kind("explicit interruption")
                target, name = (core.credential_store, "put_secret") if place == "put" else (core, "write_ledger")
                with patch.object(target, name, side_effect=interruption), self.assertRaises(kind) as caught:
                    self.publish()
                self.assertIs(interruption, caught.exception)
                if place == "write":
                    self.assertEqual("pending", self.protected()["state"])
                    self.assertTrue(self.recover())

    def test_primary_cancellation_survives_candidate_cleanup_failure(self):
        self.bootstrap()
        protected, old = dict(self.values), self.raw()
        for kind in (KeyboardInterrupt, SystemExit):
            with self.subTest(kind=kind):
                interruption, cleanup = kind("journal interrupted"), OSError("temp cleanup failed")
                actual_unlink = Path.unlink
                def fail_temp(path, *args, **kwargs):
                    if path.name.startswith(".inventory-candidate-"):
                        raise cleanup
                    return actual_unlink(path, *args, **kwargs)
                with patch.object(core.os, "fsync", side_effect=interruption):
                    with patch.object(Path, "unlink", fail_temp), self.assertRaises(kind) as caught:
                        self.publish()
                self.assertIs(interruption, caught.exception)
                self.assertIs(cleanup, caught.exception.__cause__)
                self.assertEqual(protected, self.values)
                self.assertEqual(old, self.raw())

    def test_scoped_authority_revocation_before_pending_and_after_pending_put(self):
        self.bootstrap()
        for phase in ("journal", "pending"):
            with self.subTest(phase=phase):
                old, protected = self.raw(), dict(self.values)
                valid = True
                def guard():
                    if not valid:
                        raise LiveTradingSafetyError("Original caller pin lost")
                actual_journal = core._write_journal
                def after_journal(*args):
                    nonlocal valid
                    actual_journal(*args)
                    if phase == "journal":
                        valid = False
                def after_put(**kwargs):
                    nonlocal valid
                    self.put(**kwargs)
                    if phase == "pending" and json.loads(kwargs["value"])["state"] == "pending":
                        valid = False
                with core._checkpoint_authority(guard):
                    with patch.object(core, "_write_journal", side_effect=after_journal):
                        with patch.object(core.credential_store, "put_secret", side_effect=after_put):
                            with self.assertRaisesRegex(LiveTradingSafetyError, "pin lost"):
                                self.publish()
                    valid = True
                self.assertEqual(old, self.raw())
                if phase == "journal":
                    self.assertEqual(protected, self.values)
                else:
                    self.assertEqual("pending", self.protected()["state"])
                    with self.assertRaises(LiveTradingSafetyError):
                        self.verify()
                    self.assertTrue(self.recover())

    def test_scoped_authority_is_revoked_in_copied_context_and_other_thread(self):
        self.bootstrap()
        self.calls.clear()
        def inspection():
            try:
                self.verify()
            except LiveTradingSafetyError as error:
                return error
            return None
        with core._checkpoint_authority(lambda: None):
            retained = copy_context()
            result = []
            worker = threading.Thread(target=lambda: result.append(copy_context_value.run(inspection)))
            copy_context_value = copy_context()
            worker.start()
            worker.join(2)
            self.assertFalse(worker.is_alive())
            self.assertIsInstance(result[0], LiveTradingSafetyError)
        self.assertIsInstance(retained.run(inspection), LiveTradingSafetyError)
        self.assertFalse(self.calls)
        self.assertTrue(self.verify())

    def test_cleared_context_during_pending_put_cannot_drop_required_authority_guard(self):
        old = self.bootstrap()
        def clear_context(**kwargs):
            self.put(**kwargs)
            core._AUTHORITY.set(None)
        with self.assertRaisesRegex(LiveTradingSafetyError, "authority is unavailable"):
            with core._checkpoint_authority(lambda: None):
                with patch.object(core.credential_store, "put_secret", side_effect=clear_context):
                    self.publish()
        self.assertEqual(old, self.raw())
        self.assertEqual("pending", self.protected()["state"])
        self.assertTrue(self.recover())

    def test_guard_originated_cancellation_preserves_pending_fence_and_exact_object(self):
        old = self.bootstrap()
        valid, interruption = True, KeyboardInterrupt("owner canceled during protected I/O")
        def guard():
            if not valid:
                raise interruption
        def after_put(**kwargs):
            nonlocal valid
            self.put(**kwargs)
            valid = False
        with self.assertRaises(KeyboardInterrupt) as caught:
            with core._checkpoint_authority(guard), patch.object(core.credential_store, "put_secret", side_effect=after_put):
                self.publish()
        self.assertIs(interruption, caught.exception)
        self.assertEqual(old, self.raw())
        self.assertEqual("pending", self.protected()["state"])
        self.assertTrue(self.recover())

    def test_reader_primary_cancellation_survives_actual_handle_close_failure(self):
        self.bootstrap()
        before, protected = self.raw(), dict(self.values)
        for phase in ("read", "reopened-metadata"):
            for kind in (KeyboardInterrupt, SystemExit):
                with self.subTest(phase=phase, kind=kind):
                    interruption, cleanup = kind("interrupted native read"), OSError("closed before error")
                    actual_fdopen, actual_close, actual_change = core.os.fdopen, core.os.close, core._change_time
                    captured, change_calls = [], 0
                    class InterruptedReader:
                        def __init__(reader, handle):
                            reader.handle = handle
                            captured.append(handle.fileno())
                        def fileno(reader):
                            return reader.handle.fileno()
                        def read(reader):
                            raise interruption
                        def close(reader):
                            reader.handle.close()
                            raise cleanup
                    def interrupt_metadata(fd):
                        nonlocal change_calls
                        change_calls += 1
                        if change_calls == 3:
                            captured.append(fd)
                            raise interruption
                        return actual_change(fd)
                    def closed_then_error(fd):
                        actual_close(fd)
                        if fd in captured:
                            raise cleanup
                    if phase == "read":
                        fault = patch.object(core.os, "fdopen", side_effect=lambda fd, mode: InterruptedReader(actual_fdopen(fd, mode)))
                        close = patch.object(core.os, "close", wraps=actual_close)
                    else:
                        fault = patch.object(core, "_change_time", side_effect=interrupt_metadata)
                        close = patch.object(core.os, "close", side_effect=closed_then_error)
                    with fault, close, self.assertRaises(kind) as caught:
                        self.verify()
                    self.assertIs(interruption, caught.exception)
                    self.assertIs(cleanup, caught.exception.__cause__)
                    self.assertEqual(before, self.raw())
                    self.assertEqual(protected, self.values)
                    self.assertEqual(1, len(captured))
                    with self.assertRaises(OSError):
                        os.fstat(captured[0])

    def test_journal_primary_cancellation_survives_actual_writer_close_failure(self):
        self.bootstrap()
        before, protected = self.raw(), dict(self.values)
        for kind in (KeyboardInterrupt, SystemExit):
            with self.subTest(kind=kind):
                interruption, cleanup = kind("journal fsync interrupted"), OSError("writer closed before error")
                actual_fdopen, captured = core.os.fdopen, []
                class ClosingWriter:
                    def __init__(writer, handle):
                        writer.handle = handle
                        captured.append(handle.fileno())
                    def write(writer, raw):
                        return writer.handle.write(raw)
                    def flush(writer):
                        return writer.handle.flush()
                    def fileno(writer):
                        return writer.handle.fileno()
                    def close(writer):
                        writer.handle.close()
                        raise cleanup
                def fdopen(fd, mode):
                    handle = actual_fdopen(fd, mode)
                    return ClosingWriter(handle) if mode == "wb" else handle
                with patch.object(core.os, "fdopen", side_effect=fdopen):
                    with patch.object(core.os, "fsync", side_effect=interruption), self.assertRaises(kind) as caught:
                        self.publish()
                self.assertIs(interruption, caught.exception)
                self.assertIs(cleanup, caught.exception.__cause__)
                self.assertEqual(before, self.raw())
                self.assertEqual(protected, self.values)
                self.assertFalse(list(self.path.parent.glob(".inventory-candidate-*.tmp")))
                self.assertEqual(1, len(captured))
                with self.assertRaises(OSError):
                    os.fstat(captured[0])

    def test_journal_preparation_failure_never_changes_authority_or_source(self):
        old, protected = self.bootstrap(), dict(self.values)
        with patch.object(core, "_write_journal", side_effect=OSError("journal failure")), self.assertRaises(LiveTradingSafetyError):
            self.publish()
        self.assertEqual(old, self.raw())
        self.assertEqual(protected, self.values)

    def test_source_or_protected_change_after_journal_fences_before_pending(self):
        self.bootstrap()
        actual = core._write_journal
        for changed in ("source", "protected"):
            with self.subTest(changed=changed):
                old, protected = self.raw(), dict(self.values)
                def change(*args):
                    actual(*args)
                    if changed == "source":
                        self.path.write_bytes(core._encode({**self.bound, "timestamp": 321}))
                    else:
                        self.values[next(iter(self.values))] = "corrupt"
                with patch.object(core, "_write_journal", side_effect=change), self.assertRaises(LiveTradingSafetyError):
                    self.publish()
                self.assertFalse(any(json.loads(v).get("state") == "pending" for v in self.values.values() if v != "corrupt"))
                self.path.write_bytes(old)
                self.values.clear()
                self.values.update(protected)

    def test_cleanup_failure_preserves_stable_and_never_deletes_unknown_journal(self):
        self.bootstrap()
        actual = Path.unlink
        def fail_journal(path, *args, **kwargs):
            if path.name.startswith(".spot-inventory-"):
                raise OSError("cleanup failure")
            return actual(path, *args, **kwargs)
        with patch.object(Path, "unlink", fail_journal), self.assertRaises(LiveTradingSafetyError):
            self.publish()
        protected = dict(self.values)
        self.assertTrue(self.verify())
        self.assertFalse(self.recover())
        self.assertEqual(protected, self.values)
        self.assertTrue(list(self.path.parent.glob(".spot-inventory-*.json")))

    def test_strict_schema_duplicate_unknown_bool_digest_path_and_nonfinite(self):
        self.bootstrap()
        valid = next(iter(self.values.values()))
        mutations = []
        for name, value in (("version", True), ("unexpected", 1), ("source", "wrong")):
            obj = json.loads(valid)
            obj[name] = value
            mutations.append(json.dumps(obj, sort_keys=True, separators=(",", ":")))
        for head in ({"revision": True, "digest": "0" * 64}, {"revision": 1, "digest": "A" * 64}):
            obj = json.loads(valid)
            obj["head"] = head
            mutations.append(json.dumps(obj, sort_keys=True, separators=(",", ":")))
        mutations.extend(['{"version":1,"version":1}', valid + " ", '{"value":NaN}', '{"value":1e309}', "x" * 2561])
        for value in mutations:
            with self.subTest(value=value[:25]):
                self.values[next(iter(self.values))] = value
                with self.assertRaises(LiveTradingSafetyError):
                    self.verify()
        self.values[next(iter(self.values))] = valid
        self.pending()
        obj = self.protected()
        obj["journal"] = "../outside.json"
        self.values[next(iter(self.values))] = json.dumps(obj, sort_keys=True, separators=(",", ":"))
        with self.assertRaises(LiveTradingSafetyError):
            self.recover()

    def test_actual_lock_pid_backend_and_original_deadline_before_credential_io(self):
        with self.assertRaises(LiveTradingSafetyError):
            core.verify_inventory_checkpoint(self.path, None, None)
        with ledger_transaction(self.path):
            with patch.object(core.os, "getpid", return_value=os.getpid() + 1), self.assertRaises(LiveTradingSafetyError):
                core.verify_inventory_checkpoint(self.path, None, None)
            with patch.object(core.credential_store, "credential_store_backend", return_value="linux-secret-service"), self.assertRaises(LiveTradingSafetyError):
                core.verify_inventory_checkpoint(self.path, None, None)
            with patch.object(core.time, "monotonic", return_value=time.monotonic() + 100), self.assertRaises(LiveTradingSafetyError):
                core.verify_inventory_checkpoint(self.path, None, None)
        self.assertFalse(self.calls)

    def test_expired_after_prepare_retains_pending_old_source_and_original_deadline(self):
        old = self.bootstrap()
        actual, original_clock = core._put, time.monotonic
        def expire(*args, **kwargs):
            value = actual(*args, **kwargs)
            clock.return_value = original_clock() + 100
            return value
        with patch.object(core.time, "monotonic", wraps=original_clock) as clock:
            with patch.object(core, "_put", side_effect=expire), self.assertRaises(LiveTradingSafetyError):
                self.publish()
        self.assertEqual(old, self.raw())
        self.assertEqual("pending", self.protected()["state"])
        self.assertTrue(self.recover())

    def test_parent_alias_same_slot_and_wrong_lock_rejects(self):
        self.bootstrap()
        alias = self.path.parent / ".." / self.path.parent.name / self.path.name
        with ledger_transaction(self.path):
            self.assertTrue(core.verify_inventory_checkpoint(alias, self.raw(), self.snapshot()))
            with self.assertRaises(LiveTradingSafetyError):
                core.verify_inventory_checkpoint(self.path.parent / "other.json", self.raw(), self.snapshot())
        self.assertEqual(1, len(self.values))


if __name__ == "__main__":
    unittest.main()
