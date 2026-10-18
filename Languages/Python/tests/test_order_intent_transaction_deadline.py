"""Lock authority cannot escape its transaction through copied contexts."""
from __future__ import annotations

import errno
import importlib.util
import os
import sys
import tempfile
import threading
import unittest
from contextvars import copy_context
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

SPEC = importlib.util.spec_from_file_location(
    "order_intent_store_deadline",
    ROOT / "app/integrations/exchanges/binance/orders/order_intent_store.py",
)
store = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(store)


class OrderIntentTransactionDeadlineTests(unittest.TestCase):
    def setUp(self):
        self.directory = Path(self.enterContext(tempfile.TemporaryDirectory())).resolve()
        self.paths = (self.directory / "first.json", self.directory / "second.json")

    def transaction(self, paired):
        return store.ledger_transactions(*reversed(self.paths), self.paths[0]) if paired else (
            store.ledger_transaction(self.paths[0])
        )

    def assert_unavailable(self, context=None, *paths):
        with self.assertRaises(store.LiveTradingSafetyError):
            if context is None:
                store.current_ledger_deadline(*paths)
            else:
                context.run(store.current_ledger_deadline, *paths)

    def test_only_the_actual_required_logical_paths_are_authorized(self):
        self.assert_unavailable()
        for paired in (False, True):
            with self.subTest(paired=paired), self.transaction(paired):
                deadline = store.current_ledger_deadline()
                self.assertEqual(deadline, store.current_ledger_deadline(self.paths[0]))
                relative = Path(os.path.relpath(self.paths[0]))
                self.assertEqual(deadline, store.current_ledger_deadline(relative))
                if paired:
                    self.assertEqual(deadline, store.current_ledger_deadline(*self.paths))
                else:
                    self.assert_unavailable(None, self.paths[1])
                self.assert_unavailable(None, self.directory / "unheld.json")

    def test_copied_context_loses_authority_on_normal_exit(self):
        for paired in (False, True):
            with self.subTest(paired=paired):
                with self.transaction(paired):
                    copied = copy_context()
                    self.assertEqual(store.current_ledger_deadline(), copied.run(store.current_ledger_deadline))
                self.assert_unavailable(copied)
                self.assert_unavailable()
                with self.transaction(paired):
                    store.current_ledger_deadline()
                    self.assert_unavailable(copied)

    def test_copied_context_cannot_authorize_another_thread(self):
        for paired in (False, True):
            with self.subTest(paired=paired), self.transaction(paired):
                copied = copy_context()
                results = []

                def check():
                    try:
                        copied.run(store.current_ledger_deadline, self.paths[0])
                    except BaseException as exc:
                        results.append(exc)

                worker = threading.Thread(target=check)
                worker.start()
                worker.join(timeout=2)
                self.assertFalse(worker.is_alive())
                self.assertEqual(1, len(results))
                self.assertIsInstance(results[0], store.LiveTradingSafetyError)
                store.current_ledger_deadline(self.paths[0])

    def test_authority_is_unavailable_until_every_os_lock_is_acquired(self):
        real_lock = store._try_lock
        real_parent = store._ensure_parent
        for paired in (False, True):
            observations = []
            parent_paths = []

            def acquire(fd):
                self.assert_unavailable()
                observations.append(copy_context())
                real_lock(fd)

            def prepare(path):
                self.assert_unavailable()
                parent_paths.append(path)
                real_parent(path)

            with self.subTest(paired=paired), patch.object(store, "_try_lock", side_effect=acquire), patch.object(
                store, "_ensure_parent", side_effect=prepare
            ):
                with self.transaction(paired):
                    store.current_ledger_deadline(*self.paths if paired else self.paths[:1])
                self.assertEqual(2 if paired else 1, len(observations))
                self.assertEqual(list(self.paths if paired else self.paths[:1]), parent_paths)
                for copied in observations:
                    self.assert_unavailable(copied)

    def test_body_exception_invalidates_context_before_unlock_and_releases_locks(self):
        real_unlock = store._unlock
        for paired in (False, True):
            copied = None

            def unlock(fd):
                self.assert_unavailable(copied)
                real_unlock(fd)

            with self.subTest(paired=paired), patch.object(store, "_unlock", side_effect=unlock):
                with self.assertRaisesRegex(RuntimeError, "body failed"):
                    with self.transaction(paired):
                        copied = copy_context()
                        raise RuntimeError("body failed")
                self.assert_unavailable(copied)
            with self.transaction(paired):
                store.current_ledger_deadline()

    def test_partial_acquisition_failure_invalidates_context_and_releases_locks(self):
        real_lock = store._try_lock
        copied = None
        attempts = 0

        def acquire(fd):
            nonlocal attempts, copied
            attempts += 1
            if attempts == 2:
                copied = copy_context()
                raise OSError(errno.EIO, "synthetic acquisition failure")
            real_lock(fd)

        with patch.object(store, "_try_lock", side_effect=acquire):
            with self.assertRaises(store.LiveTradingSafetyError), self.transaction(True):
                self.fail("Partial acquisition must never yield.")
        self.assertIsNotNone(copied)
        self.assert_unavailable(copied)
        self.assert_unavailable()
        with self.transaction(True):
            store.current_ledger_deadline(*self.paths)

    def test_unlock_error_also_invalidates_context(self):
        real_unlock = store._unlock
        copied = None

        def unlock(fd):
            self.assert_unavailable(copied)
            real_unlock(fd)
            raise OSError(errno.EIO, "synthetic unlock failure")

        with patch.object(store, "_unlock", side_effect=unlock):
            with self.assertRaises(store.LiveTradingSafetyError), self.transaction(False):
                copied = copy_context()
        self.assert_unavailable(copied)
        self.assert_unavailable()
        with self.transaction(False):
            store.current_ledger_deadline(self.paths[0])

    def test_original_deadline_is_reused_after_acquisition_and_clock_changes(self):
        for paired in (False, True):
            with self.subTest(paired=paired), patch.object(store.time, "monotonic", return_value=100.0) as clock:
                with self.transaction(paired):
                    self.assertEqual(100.0 + store.LOCK_TIMEOUT_SECONDS, store.current_ledger_deadline())
                    clock.return_value = 104.5
                    self.assertEqual(105.0, store.current_ledger_deadline(self.paths[0]))
                    clock.return_value = 110.0
                    self.assertEqual(105.0, copy_context().run(store.current_ledger_deadline))


if __name__ == "__main__":
    unittest.main()
