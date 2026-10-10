"""Actual lock lifetime controls for nested account/inventory transactions."""
from __future__ import annotations

from contextvars import copy_context
import ctypes
import errno
import os
from pathlib import Path
import tempfile
import threading
import sys
import unittest
from unittest.mock import patch
from uuid import uuid4

from app.integrations.exchanges.binance.orders import order_intent_store as store
from app.integrations.exchanges.binance.orders import spot_execution_owner as owner_runtime
from app.settings.live_safety import LiveTradingSafetyError


class SpotInventoryTransactionReuseTests(unittest.TestCase):
    def setUp(self):
        self.home = Path(self.enterContext(tempfile.TemporaryDirectory())).resolve()
        self.ledger = self.home / "account-intents.json"
        self.inventory = self.home / "shared-live-allocations.json"
        self.other = self.home / "not-held" / "foreign.json"
        self.enterContext(patch.object(store, "LOCK_TIMEOUT_SECONDS", 0.04))

    def assert_os_lock_held(self, path):
        lock_path = path.with_name(f".{path.name}.lock")
        fd = os.open(lock_path, os.O_RDWR)
        try:
            try:
                store._try_lock(fd)
            except OSError as exc:
                self.assertIn(exc.errno, (errno.EACCES, errno.EAGAIN))
            else:
                store._unlock(fd)
                self.fail("A nested exit released the original operating-system lock")
        finally:
            os.close(fd)

    def test_same_thread_nested_subsets_keep_original_deadline_token_and_os_locks(self):
        with store.ledger_transactions(self.ledger, self.inventory):
            original = store._ACTIVE_LEDGER_TRANSACTION.get()
            deadline = store.current_ledger_deadline(self.ledger, self.inventory)
            # Reuse must not mint a fresh budget even if the original SQL busy budget has expired.
            with patch.object(store.time, "monotonic", return_value=deadline + 100):
                with store.ledger_transaction(self.ledger):
                    self.assertIs(original, store._ACTIVE_LEDGER_TRANSACTION.get())
                    self.assertEqual(deadline, store.current_ledger_deadline(self.ledger, self.inventory))
                    with store.ledger_transactions(self.inventory, self.ledger, self.inventory):
                        self.assertIs(original, store._ACTIVE_LEDGER_TRANSACTION.get())
                        self.assertEqual(deadline, store.current_ledger_deadline(self.ledger, self.inventory))
            self.assertTrue(original.active)
            self.assertEqual(frozenset((self.ledger, self.inventory)), original.held_paths)
            self.assert_os_lock_held(self.ledger)
            self.assert_os_lock_held(self.inventory)
        self.assertFalse(original.active)
        with self.assertRaises(LiveTradingSafetyError):
            store.current_ledger_deadline(self.ledger)

    def test_single_outer_can_reuse_multi_api_without_lock_expansion(self):
        with store.ledger_transaction(self.ledger):
            original = store._ACTIVE_LEDGER_TRANSACTION.get()
            with store.ledger_transactions(self.ledger, self.ledger):
                self.assertIs(original, store._ACTIVE_LEDGER_TRANSACTION.get())
                self.assertEqual(original.deadline, store.current_ledger_deadline(self.ledger))
            self.assertTrue(original.active)
            self.assert_os_lock_held(self.ledger)
        with store.ledger_transaction(self.ledger):
            self.assertIsNot(original, store._ACTIVE_LEDGER_TRANSACTION.get())

    def test_nested_body_exception_does_not_release_outer_authority(self):
        for failure in (RuntimeError("nested diagnostic"), KeyboardInterrupt("nested cancellation")):
            with self.subTest(failure=type(failure).__name__):
                with store.ledger_transactions(self.ledger, self.inventory):
                    original = store._ACTIVE_LEDGER_TRANSACTION.get()
                    with self.assertRaises(type(failure)) as caught:
                        with store.ledger_transaction(self.inventory):
                            raise failure
                    self.assertIs(failure, caught.exception)
                    self.assertIs(original, store._ACTIVE_LEDGER_TRANSACTION.get())
                    self.assertTrue(original.active)
                    self.assertEqual(original.deadline, store.current_ledger_deadline(self.ledger, self.inventory))
                    self.assert_os_lock_held(self.ledger)
                    self.assert_os_lock_held(self.inventory)

    def test_nested_new_path_is_busy_and_never_expands_or_creates_storage(self):
        for acquire in (store.ledger_transaction, lambda path: store.ledger_transactions(self.ledger, path)):
            with self.subTest(api=getattr(acquire, "__name__", "paired")):
                with store.ledger_transaction(self.ledger):
                    original = store._ACTIVE_LEDGER_TRANSACTION.get()
                    with self.assertRaises(LiveTradingSafetyError):
                        with acquire(self.other):
                            self.fail("Nested transaction acquired a path outside the original held set")
                    self.assertFalse(self.other.parent.exists())
                    self.assertEqual(frozenset((self.ledger,)), original.held_paths)
                    self.assertIs(original, store._ACTIVE_LEDGER_TRANSACTION.get())
                    self.assertTrue(original.active)
                    self.assert_os_lock_held(self.ledger)

    def test_copied_context_on_foreign_thread_cannot_reuse_active_authority(self):
        for acquire in (store.ledger_transaction, store.ledger_transactions):
            with self.subTest(api=acquire.__name__):
                outcomes = []
                with store.ledger_transactions(self.ledger, self.inventory):
                    original = store._ACTIVE_LEDGER_TRANSACTION.get()
                    copied = copy_context()

                    def contender():
                        try:
                            store.current_ledger_deadline(self.ledger)
                        except LiveTradingSafetyError:
                            outcomes.append("deadline-rejected")
                        try:
                            with acquire(self.ledger):
                                outcomes.append("incorrectly-reused")
                        except LiveTradingSafetyError:
                            outcomes.append("lock-busy")

                    thread = threading.Thread(target=lambda: copied.run(contender))
                    thread.start()
                    thread.join(timeout=2)
                    self.assertFalse(thread.is_alive(), "Foreign context failed to return within the bounded lock wait")
                    self.assertEqual(["deadline-rejected", "lock-busy"], outcomes)
                    self.assertIs(original, store._ACTIVE_LEDGER_TRANSACTION.get())
                    self.assertTrue(original.active)
                    self.assert_os_lock_held(self.ledger)
                self.assertFalse(original.active)

    def test_released_copied_context_requires_fresh_actual_locks_and_token(self):
        with store.ledger_transaction(self.ledger):
            original = store._ACTIVE_LEDGER_TRANSACTION.get()
            copied = copy_context()
        self.assertFalse(original.active)

        def reacquire():
            with self.assertRaises(LiveTradingSafetyError):
                store.current_ledger_deadline(self.ledger)
            with store.ledger_transaction(self.ledger):
                replacement = store._ACTIVE_LEDGER_TRANSACTION.get()
                self.assertIsNot(original, replacement)
                self.assertTrue(replacement.active)
                self.assertEqual(frozenset((self.ledger,)), replacement.held_paths)
                self.assert_os_lock_held(self.ledger)
            self.assertFalse(original.active)
            self.assertFalse(replacement.active)
            with self.assertRaises(LiveTradingSafetyError):
                store.current_ledger_deadline(self.ledger)

        copied.run(reacquire)

    def test_injected_process_mismatch_cannot_reuse_deadline_or_actual_transaction(self):
        """Deterministic process-context injection; this is not an actual POSIX fork test."""
        actual_pid = os.getpid()
        for boundary in ("deadline", "single", "paired"):
            with self.subTest(boundary=boundary):
                with store.ledger_transactions(self.ledger, self.inventory):
                    original = store._ACTIVE_LEDGER_TRANSACTION.get()
                    deadline = store.current_ledger_deadline(self.ledger, self.inventory)
                    with patch.object(store.os, "getpid", return_value=actual_pid + 100000):
                        with self.assertRaises(LiveTradingSafetyError):
                            if boundary == "deadline":
                                store.current_ledger_deadline(self.ledger, self.inventory)
                            elif boundary == "single":
                                with store.ledger_transaction(self.ledger):
                                    self.fail("A different process borrowed the original single-path authority")
                            else:
                                with store.ledger_transactions(self.ledger, self.inventory):
                                    self.fail("A different process borrowed the original paired authority")
                    self.assertIs(original, store._ACTIVE_LEDGER_TRANSACTION.get())
                    self.assertTrue(original.active)
                    self.assertEqual(deadline, store.current_ledger_deadline(self.ledger, self.inventory))
                    self.assert_os_lock_held(self.ledger)
                    self.assert_os_lock_held(self.inventory)
                    self.assertFalse(self.ledger.exists())
                    self.assertFalse(self.inventory.exists())

    def test_injected_process_mismatch_cannot_adopt_actual_administration_exclusion(self):
        """An inherited-thread simulation must not authorize another process's admin FD."""
        actual_pid = os.getpid()
        with owner_runtime.owner_administration_lock(self.ledger):
            original = owner_runtime._ADMINISTRATION.get()
            owner_runtime.assert_owner_administration_held(self.ledger)
            with patch.object(owner_runtime.os, "getpid", return_value=actual_pid + 100000):
                with self.assertRaises(LiveTradingSafetyError):
                    owner_runtime.assert_owner_administration_held(self.ledger)
            self.assertIs(original, owner_runtime._ADMINISTRATION.get())
            self.assertTrue(original.active)
            owner_runtime.assert_owner_administration_held(self.ledger)
        self.assertFalse(original.active)
        with self.assertRaises(LiveTradingSafetyError):
            owner_runtime.assert_owner_administration_held(self.ledger)

    def cleanup_cases(self):
        return (
            ("single", store, lambda: store.ledger_transaction(self.ledger)),
            ("paired", store, lambda: store.ledger_transactions(self.ledger, self.inventory)),
            ("admin", owner_runtime, lambda: owner_runtime.owner_administration_lock(self.ledger)),
        )

    def test_injected_process_cleanup_closes_duplicates_without_unlocking_parent(self):
        """Observe cleanup calls under PID injection; no physical fork retention is claimed."""
        actual_pid = os.getpid()
        for name, module, acquire in self.cleanup_cases():
            with self.subTest(api=name), patch.object(module, "_try_lock", wraps=module._try_lock) as locked, \
                    patch.object(module, "_unlock", wraps=module._unlock) as unlocked, \
                    patch.object(module.os, "close", wraps=module.os.close) as closed:
                manager = acquire()
                manager.__enter__()
                fds = [call.args[0] for call in locked.call_args_list]
                self.assertEqual(2 if name == "paired" else 1, len(fds))
                with patch.object(module.os, "getpid", return_value=actual_pid + 100000):
                    manager.__exit__(None, None, None)
                unlocked.assert_not_called()
                self.assertEqual(sorted(fds), sorted(call.args[0] for call in closed.call_args_list))
                self.assertIsNone(store._ACTIVE_LEDGER_TRANSACTION.get())
                self.assertIsNone(owner_runtime._ADMINISTRATION.get())
                self.assertFalse(store._THREAD_LOCK.locked())

    def test_origin_process_cleanup_unlocks_and_closes_each_actual_fd_once(self):
        for name, module, acquire in self.cleanup_cases():
            with self.subTest(api=name), patch.object(module, "_try_lock", wraps=module._try_lock) as locked, \
                    patch.object(module, "_unlock", wraps=module._unlock) as unlocked, \
                    patch.object(module.os, "close", wraps=module.os.close) as closed:
                with acquire():
                    fds = [call.args[0] for call in locked.call_args_list]
                self.assertEqual(2 if name == "paired" else 1, len(fds))
                self.assertEqual(sorted(fds), sorted(call.args[0] for call in unlocked.call_args_list))
                self.assertEqual(sorted(fds), sorted(call.args[0] for call in closed.call_args_list))

    def synthetic_owner(self, name):
        class OfflineWrapperReference:
            pass
        path = self.home / name / "intents.json"
        path.parent.mkdir()
        store_id = str(uuid4())
        owner_runtime.provision_owner_marker(path, uid=900000029, environment="live", store_id=store_id)
        wrapper = OfflineWrapperReference()
        owner = owner_runtime.claim_execution_owner(
            path, uid=900000029, environment="live", store_id=store_id,
            credential_fingerprint="f" * 64, owner_wrapper=wrapper,
        )
        original_fd, original_stat = owner.fd, owner._file_stat

        def dispose():
            if owner.fd is not None:
                owner.close()
            # The old-control unlock-failure path loses owner.fd before closing
            # it. Close only this fixture's still-open original inode, if any.
            try:
                held = os.fstat(original_fd)
            except OSError:
                held = None
            if held is not None and (held.st_dev, held.st_ino) == (original_stat.st_dev, original_stat.st_ino):
                try:
                    owner_runtime._unlock(original_fd)
                finally:
                    os.close(original_fd)
            if owner_runtime._SESSIONS.get(owner.lock_path) is owner:
                owner_runtime._SESSIONS.pop(owner.lock_path)
        self.addCleanup(dispose)
        return owner, wrapper

    def test_injected_owner_close_and_finalizer_cannot_touch_parent_marker_mutex_or_unlock(self):
        actual_pid = os.getpid()
        for operation in ("close", "finalizer"):
            with self.subTest(operation=operation):
                owner, wrapper = self.synthetic_owner(operation)
                raw, fd = owner.marker_path.read_bytes(), owner.fd
                with patch.object(owner, "_submission_lock") as submission_mutex, \
                        patch.object(owner_runtime, "_SESSIONS_LOCK") as registry_mutex, \
                        patch.object(owner_runtime, "_write_marker", wraps=owner_runtime._write_marker) as marker_write, \
                        patch.object(owner_runtime, "_unlock", wraps=owner_runtime._unlock) as unlocked, \
                        patch.object(owner_runtime.os, "close", wraps=owner_runtime.os.close) as closed:
                    with patch.object(owner_runtime.os, "getpid", return_value=actual_pid + 100000):
                        owner.close() if operation == "close" else owner._finalizer()
                    self.assertEqual(raw, owner.marker_path.read_bytes())
                    marker_write.assert_not_called()
                    unlocked.assert_not_called()
                    submission_mutex.__enter__.assert_not_called()
                    registry_mutex.__enter__.assert_not_called()
                    closed.assert_called_once_with(fd)
                    self.assertIsNone(owner.fd)
                    self.assertFalse(owner._finalizer.alive)
                    self.assertIs(owner_runtime._SESSIONS[owner.lock_path], owner)
                self.assertIsNotNone(wrapper)

    def test_origin_owner_close_disarms_and_closes_fd_even_when_unlock_fails(self):
        for unlock_failure in (False, True):
            with self.subTest(unlock_failure=unlock_failure):
                owner, wrapper = self.synthetic_owner("normal-" + str(unlock_failure))
                fd = owner.fd
                failure = OSError("synthetic owner unlock diagnostic")
                options = {"side_effect": failure} if unlock_failure else {"wraps": owner_runtime._unlock}
                with patch.object(owner_runtime, "_unlock", **options) as unlocked, \
                        patch.object(owner_runtime.os, "close", wraps=owner_runtime.os.close) as closed:
                    if unlock_failure:
                        with self.assertRaises(OSError) as caught:
                            owner.close()
                        self.assertIs(failure, caught.exception)
                    else:
                        owner.close()
                    unlocked.assert_called_once_with(fd)
                    self.assertEqual(1, sum(call.args == (fd,) for call in closed.call_args_list))
                marker = owner_runtime._read_marker(
                    owner.marker_path, uid=owner.uid, environment=owner.environment, store_id=owner.store_id,
                )
                self.assertEqual("recovery_required", marker["state"])
                self.assertIsNone(owner.fd)
                self.assertNotIn(owner.lock_path, owner_runtime._SESSIONS)
                self.assertFalse(owner._finalizer.alive)
                self.assertIsNotNone(wrapper)

    @unittest.skipUnless(sys.platform == "win32", "Windows filesystem short-parent alias control")
    def test_actual_windows_short_and_long_parent_share_original_nested_authority(self):
        get_short = ctypes.WinDLL("kernel32", use_last_error=True).GetShortPathNameW
        get_short.argtypes = (ctypes.c_wchar_p, ctypes.c_wchar_p, ctypes.c_uint32)
        get_short.restype = ctypes.c_uint32
        required = get_short(str(self.home), None, 0)
        if not required:
            self.skipTest("Filesystem does not expose a Windows short parent alias")
        buffer = ctypes.create_unicode_buffer(required + 1)
        written = get_short(str(self.home), buffer, len(buffer))
        self.assertGreater(written, 0)
        self.assertLess(written, len(buffer))
        short_parent = Path(buffer.value)
        if str(short_parent).casefold() == str(self.home).casefold():
            self.skipTest("Filesystem has no distinct Windows short parent alias")
        self.assertEqual(self.home, short_parent.resolve())
        short_ledger = short_parent / self.ledger.name
        short_inventory = short_parent / self.inventory.name
        self.assertEqual(store._logical_lock_path(self.ledger), store._logical_lock_path(short_ledger))
        with store.ledger_transactions(self.ledger, self.inventory):
            original = store._ACTIVE_LEDGER_TRANSACTION.get()
            deadline = store.current_ledger_deadline(short_ledger, short_inventory)
            with store.ledger_transaction(short_ledger):
                self.assertIs(original, store._ACTIVE_LEDGER_TRANSACTION.get())
                self.assertEqual(deadline, store.current_ledger_deadline(self.ledger, short_inventory))
                with store.ledger_transactions(short_inventory, self.ledger, short_ledger):
                    self.assertIs(original, store._ACTIVE_LEDGER_TRANSACTION.get())
                    self.assertEqual(deadline, store.current_ledger_deadline(short_ledger, self.inventory))
            self.assert_os_lock_held(self.ledger)
            self.assert_os_lock_held(self.inventory)

    def test_final_symlink_basename_does_not_expand_to_target_lock_authority(self):
        target = self.home / "target.json"
        alias = self.home / "final-alias.json"
        target.write_text("{}", encoding="utf-8")
        try:
            alias.symlink_to(target)
        except (OSError, NotImplementedError):
            self.skipTest("Filesystem cannot create the final-symlink lock control")
        self.assertEqual(alias, store._logical_lock_path(alias))
        with store.ledger_transactions(alias):
            original = store._ACTIVE_LEDGER_TRANSACTION.get()
            self.assertEqual(frozenset((alias,)), original.held_paths)
            self.assertEqual(original.deadline, store.current_ledger_deadline(alias))
            with self.assertRaises(LiveTradingSafetyError):
                store.current_ledger_deadline(target)
            with store.ledger_transaction(alias):
                self.assertIs(original, store._ACTIVE_LEDGER_TRANSACTION.get())
            with self.assertRaises(LiveTradingSafetyError):
                with store.ledger_transaction(target):
                    self.fail("A final symlink basename silently acquired the target namespace")
            self.assertFalse(target.with_name(f".{target.name}.lock").exists())
            self.assert_os_lock_held(alias)
        with store.ledger_transaction(target):
            self.assert_os_lock_held(target)


if __name__ == "__main__":
    unittest.main()
