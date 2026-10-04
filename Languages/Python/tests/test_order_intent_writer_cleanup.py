"""Native temporary I/O and cancellation precedence for the shared JSON writer."""
from __future__ import annotations

from contextlib import contextmanager
import errno
import importlib.util
import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from app.settings.live_safety import LiveTradingSafetyError


ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location(
    "order_intent_writer_cleanup_fixture",
    ROOT / "app/integrations/exchanges/binance/orders/order_intent_store.py",
)
store = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(store)


class _CloseFaultHandle:
    def __init__(self, handle, error, observations):
        self.handle, self.error, self.observations = handle, error, observations

    def __getattr__(self, name):
        return getattr(self.handle, name)

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        self.close()

    def close(self):
        self.handle.close()
        self.observations.append(self.handle.closed)
        raise self.error


class OrderIntentWriterCleanupTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory(prefix="writer-cleanup-")
        self.addCleanup(temporary.cleanup)
        self.directory = temporary.name

    @contextmanager
    def case(self):
        with tempfile.TemporaryDirectory(dir=self.directory) as directory:
            path = Path(directory).resolve() / "unbound-paper.json"
            original = {"version": 1, "mode": "Paper", "count": 0}
            candidate = {**original, "count": 1, "note": "synthetic unicode \u015f"}
            def encode(value):
                return (json.dumps(value, sort_keys=True, indent=2, allow_nan=False) + "\n").encode()
            before, target = encode(original), encode(candidate)
            path.write_bytes(before)
            yield path, candidate, before, target

    def captured(self, path, action):
        try:
            with store.ledger_transaction(path):
                deadline = store.current_ledger_deadline(path)
                action(deadline)
        except BaseException as outcome:
            return outcome
        self.fail("Injected writer failure disappeared")

    def assert_state(self, path, expected):
        self.assertEqual(expected, path.read_bytes())
        self.assertEqual([], [p for p in path.parent.iterdir() if p.name.endswith(".tmp")])
        with self.assertRaisesRegex(LiveTradingSafetyError, "transaction is required"):
            store.current_ledger_deadline(path)
        # The actual module mutex and original native file lock must be released.
        with store.ledger_transaction(path):
            self.assertGreater(store.current_ledger_deadline(path), 0)

    def unlink_fault(self, path, error, observations):
        real_unlink = Path.unlink

        def remove(temp, *args, **kwargs):
            if temp.parent == path.parent and temp.name.startswith(f".{path.name}.") and temp.name.endswith(".tmp"):
                real_unlink(temp, *args, **kwargs)
                observations.append(not temp.exists())
                raise error
            return real_unlink(temp, *args, **kwargs)
        return patch.object(Path, "unlink", new=remove)

    def publish_cancellation(self, primary, *, after_publish, unlink_error=None):
        with self.case() as (path, candidate, before, target):
            real_publish, real_fsync = store._publish, os.fsync
            publish_calls, fsync_calls, unlink_calls = [], [], []

            def action(deadline):
                def sync(fd):
                    real_fsync(fd)
                    fsync_calls.append(fd)
                    self.assertEqual(deadline, store.current_ledger_deadline(path))

                def publish(temp, destination):
                    self.assertEqual(target, temp.read_bytes())
                    self.assertTrue(fsync_calls)
                    self.assertEqual(deadline, store.current_ledger_deadline(path))
                    publish_calls.append(temp)
                    if after_publish:
                        real_publish(temp, destination)
                    raise primary

                with patch.object(store.os, "fsync", side_effect=sync), patch.object(store, "_publish", side_effect=publish):
                    if unlink_error is None:
                        store.write_ledger(path, candidate)
                    else:
                        with self.unlink_fault(path, unlink_error, unlink_calls):
                            store.write_ledger(path, candidate)

            outcome = self.captured(path, action)
            self.assert_state(path, target if after_publish else before)
            self.assertEqual(1, len(publish_calls))
            self.assertTrue(fsync_calls)
            if unlink_error is not None:
                self.assertEqual([True], unlink_calls)
            return outcome

    def test_native_publication_cancellation_without_cleanup_fault_keeps_identity(self):
        for kind in (KeyboardInterrupt, SystemExit):
            for after_publish in (False, True):
                with self.subTest(kind=kind.__name__, after_publish=after_publish):
                    primary = kind("original cancellation")
                    self.assertIs(primary, self.publish_cancellation(primary, after_publish=after_publish))

    def test_final_unlink_fault_keeps_original_cancellation_before_and_after_native_publish(self):
        for kind in (KeyboardInterrupt, SystemExit):
            for after_publish in (False, True):
                with self.subTest(kind=kind.__name__, after_publish=after_publish):
                    primary, cleanup = kind("original cancellation"), OSError("after actual temp unlink")
                    outcome = self.publish_cancellation(primary, after_publish=after_publish, unlink_error=cleanup)
                    self.assertIs(primary, outcome)
                    self.assertIs(cleanup, outcome.__cause__)

    def test_cleanup_cancellation_takes_precedence_over_ordinary_publication_error(self):
        for kind in (KeyboardInterrupt, SystemExit):
            with self.subTest(kind=kind.__name__):
                primary, cleanup = OSError("publication failure"), kind("cleanup cancellation")
                outcome = self.publish_cancellation(primary, after_publish=False, unlink_error=cleanup)
                self.assertIs(cleanup, outcome)
                self.assertIs(primary, outcome.__cause__)

    def test_final_unlink_error_without_primary_retains_storage_error_framing(self):
        with self.case() as (path, candidate, _before, target):
            cleanup, unlinks = OSError("after successful native publication"), []
            def action(_deadline):
                with self.unlink_fault(path, cleanup, unlinks):
                    store.write_ledger(path, candidate)
            outcome = self.captured(path, action)
            self.assert_state(path, target)
            self.assertIsInstance(outcome, LiveTradingSafetyError)
            self.assertIn("Order intent storage failed", str(outcome))
            self.assertIs(cleanup, outcome.__cause__)
            self.assertEqual([True], unlinks)

    def test_ordinary_publication_failure_retains_storage_error_framing(self):
        primary = OSError("publication unavailable")
        outcome = self.publish_cancellation(primary, after_publish=False)
        self.assertIsInstance(outcome, LiveTradingSafetyError)
        self.assertIn("Order intent storage failed", str(outcome))
        self.assertIs(primary, outcome.__cause__)

    def handle_fault(self, primary, *, unlink_error=None, close_error=None):
        with self.case() as (path, candidate, before, _target):
            real_fdopen, real_fsync = os.fdopen, os.fsync
            cleanup = close_error if close_error is not None else OSError("after actual handle close")
            closed, fsynced, unlinks = [], [], []

            def fdopen(*args, **kwargs):
                return _CloseFaultHandle(real_fdopen(*args, **kwargs), cleanup, closed)

            def action(deadline):
                def sync(fd):
                    real_fsync(fd)
                    fsynced.append(fd)
                    self.assertEqual(deadline, store.current_ledger_deadline(path))
                    if primary is not None:
                        raise primary
                with patch.object(store.os, "fdopen", side_effect=fdopen), patch.object(store.os, "fsync", side_effect=sync):
                    if unlink_error is None:
                        store.write_ledger(path, candidate)
                    else:
                        with self.unlink_fault(path, unlink_error, unlinks):
                            store.write_ledger(path, candidate)

            outcome = self.captured(path, action)
            self.assert_state(path, before)
            self.assertEqual([True], closed)
            self.assertEqual(1, len(fsynced))
            if unlink_error is not None:
                self.assertEqual([True], unlinks)
            return outcome, cleanup

    def test_actual_fsync_cancellation_survives_actual_close_error(self):
        for kind in (KeyboardInterrupt, SystemExit):
            with self.subTest(kind=kind.__name__):
                primary = kind("after actual fsync")
                outcome, cleanup = self.handle_fault(primary)
                self.assertIs(primary, outcome)
                self.assertIs(cleanup, outcome.__cause__)

    def test_close_error_without_primary_is_an_owned_storage_error(self):
        outcome, cleanup = self.handle_fault(None)
        self.assertIsInstance(outcome, LiveTradingSafetyError)
        self.assertIn("Order intent storage failed", str(outcome))
        self.assertIs(cleanup, outcome.__cause__)

    def test_primary_and_both_cleanup_errors_keep_all_diagnostic_causes(self):
        primary, unlink_error = KeyboardInterrupt("after actual fsync"), OSError("after real unlink")
        outcome, close_error = self.handle_fault(primary, unlink_error=unlink_error)
        self.assertIs(primary, outcome)
        self.assertIs(unlink_error, outcome.__cause__)
        self.assertIs(close_error, unlink_error.__cause__)

    def test_repeated_cleanup_exception_does_not_create_a_cause_cycle(self):
        primary, cleanup = KeyboardInterrupt("after actual fsync"), OSError("repeated native cleanup fault")
        outcome, close_error = self.handle_fault(primary, unlink_error=cleanup, close_error=cleanup)
        self.assertIs(primary, outcome)
        self.assertIs(cleanup, close_error)
        self.assertIs(cleanup, primary.__cause__)
        self.assertIsNone(cleanup.__cause__)
        self.assertIsNone(cleanup.__context__)

    def construction_fault(self, primary, *, close_error=None):
        with self.case() as (path, candidate, before, _target):
            real_close = os.close
            fds, closed = [], []

            def fdopen(fd, *_args, **_kwargs):
                fds.append(fd)
                raise primary

            def close(fd):
                real_close(fd)
                if fds and fd == fds[-1]:
                    closed.append(fd)
                    if close_error is not None:
                        raise close_error

            def action(_deadline):
                with patch.object(store.os, "fdopen", side_effect=fdopen), patch.object(store.os, "close", side_effect=close):
                    store.write_ledger(path, candidate)

            outcome = self.captured(path, action)
            self.assertEqual(1, len(fds))
            try:
                os.fstat(fds[0])
            except OSError as exc:
                descriptor_closed = exc.errno == errno.EBADF
            else:
                descriptor_closed = False
                # Release the old source's leaked handle before failing its control.
                real_close(fds[0])
            self.assertTrue(descriptor_closed, "Writer leaked its descriptor after fdopen failed")
            self.assertEqual(fds, closed)
            self.assert_state(path, before)
            return outcome

    def test_failed_fdopen_closes_descriptor_and_retains_original_cancellation(self):
        for kind in (KeyboardInterrupt, SystemExit):
            for cleanup_fault in (False, True):
                with self.subTest(kind=kind.__name__, cleanup_fault=cleanup_fault):
                    primary = kind("fdopen cancellation")
                    cleanup = OSError("after actual descriptor close") if cleanup_fault else None
                    outcome = self.construction_fault(primary, close_error=cleanup)
                    self.assertIs(primary, outcome)
                    self.assertIs(cleanup, outcome.__cause__)

    def test_failed_fdopen_ordinary_error_preserves_both_causes_and_storage_framing(self):
        primary, cleanup = OSError("fdopen unavailable"), OSError("after actual descriptor close")
        outcome = self.construction_fault(primary, close_error=cleanup)
        self.assertIsInstance(outcome, LiveTradingSafetyError)
        self.assertIs(primary, outcome.__cause__)
        self.assertIs(cleanup, primary.__cause__)

    def test_unrelated_handled_exception_is_not_a_writer_primary(self):
        for kind in (OSError, KeyboardInterrupt, SystemExit):
            with self.subTest(kind=kind.__name__), self.case() as (path, candidate, _before, target):
                prior, cleanup, unlinks = kind("already handled caller exception"), OSError("after native publish"), []
                def action(_deadline):
                    with self.unlink_fault(path, cleanup, unlinks):
                        store.write_ledger(path, candidate)
                try:
                    raise prior
                except BaseException:
                    outcome = self.captured(path, action)
                self.assert_state(path, target)
                self.assertEqual([True], unlinks)
                self.assertIsInstance(outcome, LiveTradingSafetyError)
                self.assertIs(cleanup, outcome.__cause__)

    def test_healthy_writer_keeps_exact_utf8_lf_atomic_publication(self):
        with self.case() as (path, candidate, _before, target):
            with store.ledger_transaction(path):
                deadline = store.current_ledger_deadline(path)
                store.write_ledger(path, candidate)
                self.assertEqual(deadline, store.current_ledger_deadline(path))
            self.assert_state(path, target)


if __name__ == "__main__":
    unittest.main()
