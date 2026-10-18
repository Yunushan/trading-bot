"""Inherited Spot execution state must reject before mutex or SQLite work."""
from __future__ import annotations

from contextlib import contextmanager
import errno
import gc
import json
import os
from pathlib import Path
import select
import signal
import socket
import subprocess
import sys
import tempfile
import threading
import unittest
from unittest.mock import patch
import weakref

from app.integrations.exchanges.binance.orders import order_intent_runtime as runtime
from app.integrations.exchanges.binance.orders import order_intent_store as store
from app.integrations.exchanges.binance.orders import spot_execution_owner as owners
from app.integrations.exchanges.binance.orders import spot_indexed_intent_bridge as bridge
from app.integrations.exchanges.binance.orders import spot_indexed_intent_migration as migration
from app.integrations.exchanges.binance.orders import spot_indexed_intent_selective as selective
from app.integrations.exchanges.binance.orders import spot_indexed_intent_store as full
from app.integrations.exchanges.binance.orders.order_intent_provisioning import PROVISION_ACK
from app.settings.live_safety import LiveTradingSafetyError
from tools import benchmark_spot_intent_history as fixtures


class _Wrapper:
    pass


class _PoisonLock:
    def acquire(self, *args, **kwargs):
        raise AssertionError("Inherited mutex was entered before the process fence")

    def __enter__(self):
        return self.acquire()

    def __exit__(self, *args):
        raise AssertionError("Inherited mutex was exited")


class _PoisonConnection:
    def __init__(self):
        object.__setattr__(self, "accesses", [])

    def __getattribute__(self, name):
        object.__getattribute__(self, "accesses").append(name)
        raise AssertionError("Inherited SQLite connection was accessed")


class _WeakConnection(full.sqlite3.Connection):
    pass


class _ProcessObservedConnection:
    """Delegate real parent SQL; any child-side access is a recorded failure."""
    def __init__(self, actual):
        self._actual, self._pid, self.accesses = actual, os.getpid(), []

    def __getattribute__(self, name):
        if os.getpid() != object.__getattribute__(self, "_pid"):
            object.__getattribute__(self, "accesses").append(name)
            raise AssertionError("Inherited cold SQLite connection was accessed")
        return getattr(object.__getattribute__(self, "_actual"), name)


class SpotForkProcessFenceTests(unittest.TestCase):
    def setUp(self):
        self.home = Path(self.enterContext(tempfile.TemporaryDirectory(prefix="trading-bot-fork-fence-"))).resolve()
        self.enterContext(patch.object(Path, "home", return_value=self.home))
        self.enterContext(patch.object(socket.socket, "connect", side_effect=AssertionError("No network")))
        self.enterContext(patch.object(socket, "create_connection", side_effect=AssertionError("No network")))
        self.wrapper = _Wrapper()
        self.wrapper.__dict__.update(vars(fixtures.synthetic_owner()))
        self.ledger = runtime._intent_path(self.wrapper)
        self.inventory = self.home / "inventory.json"
        self.payload = fixtures.synthetic_payload(1, 1)
        self.payload["intents"]["synthetic-history-00000000"].update(
            state="rejected", exchange_status="EXPIRED", executed_qty="0")
        self.binding = self.payload["binding"]
        self.foreign_pid = os.getpid() + 100000

    def owner(self):
        owners.provision_owner_marker(self.ledger, uid=fixtures.SYNTHETIC_UID,
            environment="live", store_id=self.payload["store_id"])
        owner = owners.claim_execution_owner(self.ledger, uid=fixtures.SYNTHETIC_UID,
            environment="live", store_id=self.payload["store_id"],
            credential_fingerprint=self.binding["credential_fingerprint"], owner_wrapper=self.wrapper)
        self.addCleanup(owner.close)
        return owner

    def indexed(self):
        with owners.owner_administration_lock(self.ledger):
            with store.ledger_transaction(self.ledger):
                store.write_ledger(self.ledger, self.payload)
            owners.provision_owner_marker_locked(self.ledger, uid=fixtures.SYNTHETIC_UID,
                environment="live", store_id=self.payload["store_id"])
        result = migration.migrate_spot_indexed_intent_store(self.wrapper,
            acknowledgement=PROVISION_ACK, reconciliation_reference="synthetic fork migration")
        owners.rearm_owner_marker(self.ledger, uid=fixtures.SYNTHETIC_UID, environment="live",
            store_id=self.payload["store_id"], acknowledgement=PROVISION_ACK,
            reconciliation_reference="synthetic fork rearm")
        owner = owners.claim_execution_owner(self.ledger, uid=fixtures.SYNTHETIC_UID,
            environment="live", store_id=self.payload["store_id"],
            credential_fingerprint=self.binding["credential_fingerprint"], owner_wrapper=self.wrapper)
        self.addCleanup(owner.close)
        with store.ledger_transaction(self.ledger):
            authority = bridge.read_indexed_ledger(self.ledger, expected_binding=self.binding).indexed_authority
            session = selective.open_indexed_session(owner=owner, owner_wrapper=self.wrapper,
                expected_binding=self.binding, expected_authority=authority,
                deadline=store.current_ledger_deadline(self.ledger))
        connection = session._connection

        def dispose():
            # PID injection changes this same graph; actual fork changes only the child copy.
            with selective._SESSIONS_LOCK:
                if selective._SESSIONS.get(self.ledger) is session:
                    selective._SESSIONS.pop(self.ledger)
            session._finalizer.detach()
            connection.close()
        self.addCleanup(dispose)
        return owner, session, Path(result["database_path"])

    def assert_owner_held(self, owner):
        owner.assert_held(uid=fixtures.SYNTHETIC_UID, environment="live",
            credential_fingerprint=self.binding["credential_fingerprint"], owner_wrapper=self.wrapper)
        self.assert_os_lock(owner.lock_path)

    def assert_os_lock(self, path):
        fd = os.open(path, os.O_RDWR)
        try:
            try:
                store._try_lock(fd)
            except OSError as exc:
                self.assertIn(exc.errno, (errno.EACCES, errno.EAGAIN))
            else:
                store._unlock(fd)
                self.fail("The child released its parent's native lock")
        finally:
            os.close(fd)

    def test_process_fence_precedes_single_and_paired_ledger_mutexes(self):
        for paths in ((self.ledger,), (self.ledger, self.inventory)):
            with self.subTest(paths=len(paths)), patch.object(store, "_THREAD_LOCK", _PoisonLock()), \
                    patch.object(os, "getpid", return_value=self.foreign_pid):
                with self.assertRaises(LiveTradingSafetyError):
                    manager = store.ledger_transaction(paths[0]) if len(paths) == 1 else store.ledger_transactions(*paths)
                    with manager:
                        self.fail("Inherited process obtained new storage authority")
        self.assertFalse(self.ledger.parent.exists())

    def test_process_fence_precedes_owner_claim_admin_and_submission_mutexes(self):
        owner = self.owner()
        raw = owner.marker_path.read_bytes()
        calls = (
            lambda: owners.claim_execution_owner(self.ledger, uid=fixtures.SYNTHETIC_UID,
                environment="live", store_id=owner.store_id,
                credential_fingerprint=self.binding["credential_fingerprint"], owner_wrapper=self.wrapper),
            lambda: owners.owner_administration_lock(self.ledger).__enter__(),
            lambda: owner.submission(uid=owner.uid, environment=owner.environment,
                credential_fingerprint=owner.credential_fingerprint, owner_wrapper=self.wrapper).__enter__(),
        )
        for index, call in enumerate(calls):
            with self.subTest(boundary=index), patch.object(owners, "_SESSIONS_LOCK", _PoisonLock()), \
                    patch.object(owner, "_submission_lock", _PoisonLock()), \
                    patch.object(os, "getpid", return_value=self.foreign_pid):
                with self.assertRaises(LiveTradingSafetyError):
                    call()
        self.assertEqual(raw, owner.marker_path.read_bytes())
        self.assert_owner_held(owner)

    def test_process_fence_precedes_indexed_registry_inspection_and_revocation(self):
        owner = self.owner()
        calls = (
            lambda: selective.indexed_namespace_known(self.ledger),
            lambda: selective.indexed_namespace_attribution(owner_wrapper=self.wrapper),
            lambda: selective.indexed_session_refresh_required(owner),
            lambda: selective.close_indexed_session(owner),
        )
        for index, call in enumerate(calls):
            with self.subTest(boundary=index), patch.object(selective, "_SESSIONS_LOCK", _PoisonLock()), \
                    patch.object(os, "getpid", return_value=self.foreign_pid):
                with self.assertRaises(LiveTradingSafetyError):
                    call()
        self.assert_owner_held(owner)

    def test_inherited_indexed_close_and_finalizer_skip_registry_and_sqlite(self):
        owner, session, _database = self.indexed()
        actual_connection = session._connection
        before = actual_connection.serialize(), owner.marker_path.read_bytes()
        connection = _PoisonConnection()
        session._connection = connection
        session._finalizer.detach()
        for finalizer in (False, True):
            # Reattach solely to exercise both cleanup entries under deterministic PID injection.
            session._closed = False
            session._finalizer = weakref.finalize(self.wrapper, session.close)
            with self.subTest(finalizer=finalizer), patch.object(selective, "_SESSIONS_LOCK", _PoisonLock()), \
                    patch.object(os, "getpid", return_value=self.foreign_pid):
                session._finalizer() if finalizer else session.close()
            self.assertTrue(session._closed)
            self.assertFalse(session._finalizer.alive)
            self.assertEqual([], object.__getattribute__(connection, "accesses"))
            self.assertIs(session, selective._SESSIONS[self.ledger])
        self.assertEqual(before, (actual_connection.serialize(), owner.marker_path.read_bytes()))
        self.assert_owner_held(owner)

    def test_foreign_session_transaction_rejects_before_any_sqlite_cleanup_access(self):
        owner, session, _database = self.indexed()
        connection = _PoisonConnection()
        session._connection = connection
        original_pid = session._pid
        session._pid = self.foreign_pid
        try:
            with store.ledger_transaction(self.ledger):
                with self.assertRaises(LiveTradingSafetyError):
                    with session._transaction(store.current_ledger_deadline(self.ledger)):
                        self.fail("A foreign process session obtained SQL authority")
            self.assertEqual([], object.__getattribute__(connection, "accesses"))
            self.assertFalse(session._closed)
            self.assertIs(session, selective._SESSIONS[self.ledger])
        finally:
            session._pid = original_pid
        self.assert_owner_held(owner)

    def entered_transaction_exit(self, interruption=None):
        owner, session, _database = self.indexed()
        connection, original_pid = session._connection, session._pid
        before = connection.serialize(), owner.marker_path.read_bytes()
        with store.ledger_transaction(self.ledger):
            manager = session._transaction(store.current_ledger_deadline(self.ledger))
            manager.__enter__()
            self.assertTrue(connection.in_transaction)
            poison = _PoisonConnection()
            session._connection, session._pid = poison, self.foreign_pid
            try:
                if interruption is None:
                    with self.assertRaises(LiveTradingSafetyError):
                        manager.__exit__(None, None, None)
                else:
                    # contextlib returns False only when the same original exception survives.
                    self.assertFalse(manager.__exit__(type(interruption), interruption, None))
                self.assertEqual([], object.__getattribute__(poison, "accesses"))
                self.assertTrue(session._closed)
                self.assertFalse(session._finalizer.alive)
                self.assertIs(session, selective._SESSIONS[self.ledger])
                self.assertTrue(connection.in_transaction)
                self.assertEqual(before, (connection.serialize(), owner.marker_path.read_bytes()))
                self.assert_owner_held(owner)
            finally:
                # Undo only this in-process simulation of a fork copy; a real child
                # cannot restore or adopt its inherited product session.
                session._connection, session._pid, session._closed = connection, original_pid, False
                session._finalizer = weakref.finalize(self.wrapper, session.close)
                connection.commit()
            self.assertFalse(connection.in_transaction)

    def test_entered_transaction_normal_exit_checks_process_before_sqlite_cleanup(self):
        self.entered_transaction_exit()

    def test_entered_transaction_preserves_body_interruption_without_sqlite_cleanup(self):
        self.entered_transaction_exit(KeyboardInterrupt("synthetic inherited body interruption"))

    @contextmanager
    def worker_holds(self, mutex):
        ready, release = threading.Event(), threading.Event()
        def hold():
            with mutex:
                ready.set()
                release.wait(10)
        thread = threading.Thread(target=hold)
        thread.start()
        try:
            self.assertTrue(ready.wait(2), "Parent worker did not acquire the real mutex")
            yield
        finally:
            release.set()
            thread.join(2)
            self.assertFalse(thread.is_alive(), "Parent fixture worker did not finish")

    def fork_result(self, operation):
        """Kill/reap only this test's child if it traps in an inherited mutex."""
        reader, writer = os.pipe()
        pid = os.fork()
        if pid == 0:
            os.close(reader)
            try:
                operation()
                result = {"ok": True, "pid": os.getpid()}
            except BaseException as exc:
                result = {"ok": False, "error": repr(exc), "pid": os.getpid()}
            try:
                os.write(writer, json.dumps(result).encode("ascii"))
            finally:
                os._exit(0)
        os.close(writer)
        try:
            if not select.select([reader], [], [], 2)[0]:
                os.kill(pid, signal.SIGKILL)
                os.waitpid(pid, 0)
                self.fail("Fork child trapped before reaching the process fence")
            result = json.loads(os.read(reader, 8192))
            self.assertEqual(pid, result["pid"])
            self.assertTrue(result["ok"], result)
        finally:
            os.close(reader)
            # A failed assertion must still reap only our owned child.
            try:
                os.waitpid(pid, 0)
            except ChildProcessError:
                pass

    @unittest.skipUnless(hasattr(os, "fork"), "Requires actual POSIX fork")
    def test_actual_fork_rejects_owner_submission_and_registry_while_worker_holds_mutex(self):
        owner = self.owner()
        before = owner.marker_path.read_bytes()
        def submission():
            with self.assertRaises(LiveTradingSafetyError), owner.submission(uid=owner.uid,
                    environment=owner.environment, credential_fingerprint=owner.credential_fingerprint,
                    owner_wrapper=self.wrapper):
                self.fail("Fork child inherited submission authority")
        def registry():
            with self.assertRaises(LiveTradingSafetyError):
                with owners.owner_administration_lock(self.ledger):
                    self.fail("Fork child inherited administration authority")
        for mutex, operation in ((owner._submission_lock, submission), (owners._SESSIONS_LOCK, registry)):
            with self.subTest(boundary=operation.__name__), self.worker_holds(mutex):
                self.fork_result(operation)
            self.assertEqual(before, owner.marker_path.read_bytes())
            self.assert_owner_held(owner)

    @unittest.skipUnless(hasattr(os, "fork"), "Requires actual POSIX fork")
    def test_actual_fork_rejects_ledger_entry_before_inherited_worker_lock(self):
        for paired in (False, True):
            def enter():
                with self.assertRaises(LiveTradingSafetyError):
                    manager = store.ledger_transactions(self.ledger, self.inventory) if paired else store.ledger_transaction(self.ledger)
                    with manager:
                        self.fail("Fork child obtained ledger authority")
            with self.subTest(paired=paired), self.worker_holds(store._THREAD_LOCK):
                self.fork_result(enter)
        self.assertFalse(self.ledger.parent.exists())

    @unittest.skipUnless(hasattr(os, "fork"), "Requires actual POSIX fork")
    def test_actual_fork_indexed_finalizer_does_not_enter_registry_or_mutate_parent(self):
        owner, session, database = self.indexed()
        before = database.read_bytes(), self.ledger.read_bytes(), owner.marker_path.read_bytes()
        def cleanup():
            session._finalizer()
            self.assertTrue(session._closed)
            self.assertFalse(session._finalizer.alive)
            with self.assertRaises(LiveTradingSafetyError):
                selective.indexed_namespace_known(self.ledger)
        with self.worker_holds(selective._SESSIONS_LOCK):
            self.fork_result(cleanup)
        self.assertEqual(before, (database.read_bytes(), self.ledger.read_bytes(), owner.marker_path.read_bytes()))
        self.assertFalse(session._closed)
        self.assertTrue(session._finalizer.alive)
        self.assertIs(session, selective._SESSIONS[self.ledger])
        self.assert_owner_held(owner)
        with store.ledger_transaction(self.ledger):
            self.assertEqual(self.payload["intents"]["synthetic-history-00000000"],
                session.read_record("synthetic-history-00000000", deadline=store.current_ledger_deadline(self.ledger)))

    @unittest.skipUnless(hasattr(os, "fork"), "Requires actual POSIX fork")
    def test_actual_fork_transaction_cleanup_preserves_parent_locks_and_deadline(self):
        for kind in ("single", "paired", "admin"):
            with self.subTest(kind=kind):
                manager = (owners.owner_administration_lock(self.ledger) if kind == "admin" else
                    store.ledger_transactions(self.ledger, self.inventory) if kind == "paired" else
                    store.ledger_transaction(self.ledger))
                with manager:
                    def cleanup():
                        manager.__exit__(None, None, None)
                    self.fork_result(cleanup)
                    if kind == "admin":
                        owners.assert_owner_administration_held(self.ledger)
                        self.assert_os_lock(owners.owner_lock_path(self.ledger))
                    else:
                        store.current_ledger_deadline(self.ledger)
                        self.assert_os_lock(self.ledger.with_name(f".{self.ledger.name}.lock"))
                        if kind == "paired":
                            self.assert_os_lock(self.inventory.with_name(f".{self.inventory.name}.lock"))

    @unittest.skipUnless(hasattr(os, "fork"), "Requires actual POSIX fork")
    def test_actual_fork_entered_sql_transaction_unwind_leaves_parent_authority_unchanged(self):
        owner, session, database = self.indexed()
        connection = session._connection
        for interrupted in (False, True):
            with self.subTest(interrupted=interrupted), store.ledger_transaction(self.ledger):
                manager = session._transaction(store.current_ledger_deadline(self.ledger))
                manager.__enter__()
                before = database.read_bytes(), self.ledger.read_bytes(), owner.marker_path.read_bytes()
                def unwind():
                    poison = _PoisonConnection()
                    session._connection = poison
                    if interrupted:
                        interruption = KeyboardInterrupt("synthetic actual fork body interruption")
                        self.assertFalse(manager.__exit__(KeyboardInterrupt, interruption, None))
                    else:
                        with self.assertRaises(LiveTradingSafetyError):
                            manager.__exit__(None, None, None)
                    self.assertEqual([], object.__getattribute__(poison, "accesses"))
                    self.assertTrue(session._closed)
                    self.assertFalse(session._finalizer.alive)
                try:
                    self.fork_result(unwind)
                    self.assertTrue(connection.in_transaction)
                    self.assertFalse(session._closed)
                    self.assertTrue(session._finalizer.alive)
                    self.assertIs(session, selective._SESSIONS[self.ledger])
                    self.assertEqual(before, (database.read_bytes(), self.ledger.read_bytes(), owner.marker_path.read_bytes()))
                    self.assert_owner_held(owner)
                finally:
                    # This is the unchanged parent's original generator and real SQL COMMIT.
                    manager.__exit__(None, None, None)
                self.assertFalse(connection.in_transaction)

    def cold_store(self):
        owner, database = self.owner(), self.home / "cold.sqlite3"
        with store.ledger_transaction(self.ledger):
            full.create_indexed_store(database, self.payload, logical_path=self.ledger,
                rules=bridge.indexed_intent_rules(), expected_binding=self.binding,
                deadline=store.current_ledger_deadline(self.ledger))
        return owner, database

    @contextmanager
    def observed_cold_connection(self, database):
        connect = full.sqlite3.connect
        captured = []
        def observing(*args, **kwargs):
            proxy = _ProcessObservedConnection(connect(*args, **kwargs))
            captured.append(proxy)
            return proxy
        with patch.object(full.sqlite3, "connect", side_effect=observing):
            manager = full._connection(database, self.ledger, store.current_ledger_deadline(self.ledger))
            proxy = manager.__enter__()
        try:
            self.assertEqual([proxy], captured)
            yield manager, proxy, object.__getattribute__(proxy, "_actual")
        finally:
            # This fixture owns the parent connection; inherited cleanup must not close it.
            object.__getattribute__(proxy, "_actual").close()

    def cold_connection_exit(self, interruption=None):
        owner, database = self.cold_store()
        with store.ledger_transaction(self.ledger), self.observed_cold_connection(database) as (manager, proxy, actual):
            full._sql(proxy, store.current_ledger_deadline(self.ledger), "BEGIN")
            before = database.read_bytes(), owner.marker_path.read_bytes()
            with patch.object(os, "getpid", return_value=self.foreign_pid):
                if interruption is None:
                    with self.assertRaises(LiveTradingSafetyError):
                        manager.__exit__(None, None, None)
                else:
                    self.assertFalse(manager.__exit__(type(interruption), interruption, None))
            self.assertEqual([], object.__getattribute__(proxy, "accesses"))
            self.assertTrue(actual.in_transaction)
            self.assertEqual(before, (database.read_bytes(), owner.marker_path.read_bytes()))
            self.assert_owner_held(owner)
            full._sql(proxy, store.current_ledger_deadline(self.ledger), "COMMIT")
            self.assertFalse(actual.in_transaction)

    def test_entered_cold_connection_normal_exit_skips_all_foreign_sqlite_access(self):
        self.cold_connection_exit()

    def test_entered_cold_connection_preserves_body_interruption_without_foreign_sqlite_access(self):
        self.cold_connection_exit(KeyboardInterrupt("synthetic cold inherited interruption"))

    @unittest.skipUnless(hasattr(os, "fork"), "Requires actual POSIX fork")
    def test_actual_fork_entered_cold_connection_unwind_preserves_parent_transaction(self):
        owner, database = self.cold_store()
        for interrupted in (False, True):
            with self.subTest(interrupted=interrupted), store.ledger_transaction(self.ledger), \
                    self.observed_cold_connection(database) as (manager, proxy, actual):
                deadline = store.current_ledger_deadline(self.ledger)
                full._sql(proxy, deadline, "BEGIN")
                before = database.read_bytes(), owner.marker_path.read_bytes()
                def unwind():
                    if interrupted:
                        interruption = KeyboardInterrupt("synthetic actual cold fork interruption")
                        self.assertFalse(manager.__exit__(KeyboardInterrupt, interruption, None))
                    else:
                        with self.assertRaises(LiveTradingSafetyError):
                            manager.__exit__(None, None, None)
                    self.assertEqual([], object.__getattribute__(proxy, "accesses"))
                try:
                    self.fork_result(unwind)
                    self.assertTrue(actual.in_transaction)
                    self.assertEqual(before, (database.read_bytes(), owner.marker_path.read_bytes()))
                    self.assert_owner_held(owner)
                    full._sql(proxy, deadline, "COMMIT")
                    self.assertFalse(actual.in_transaction)
                finally:
                    manager.__exit__(None, None, None)

    def weak_cold_manager(self, database):
        connect, refs, finalized = full.sqlite3.connect, [], []
        def observed(*args, **kwargs):
            driver = connect(*args, factory=_WeakConnection, **kwargs)
            proxy = _ProcessObservedConnection(driver)
            refs.extend((weakref.ref(proxy), weakref.ref(driver)))
            weakref.finalize(proxy, finalized.append, "proxy")
            weakref.finalize(driver, finalized.append, "driver")
            return proxy
        with patch.object(full.sqlite3, "connect", side_effect=observed):
            manager = full._connection(database, self.ledger, store.current_ledger_deadline(self.ledger))
            proxy = manager.__enter__()
        # No captured strong proxy/driver list or actual-driver local survives this helper.
        return manager, proxy, refs, finalized

    def test_inherited_cold_connection_survives_gc_without_caller_or_generator_references(self):
        owner, database = self.cold_store()
        with store.ledger_transaction(self.ledger):
            manager, proxy, refs, finalized = self.weak_cold_manager(database)
            full._sql(proxy, store.current_ledger_deadline(self.ledger), "BEGIN")
            before = database.read_bytes(), owner.marker_path.read_bytes()
            with patch.object(os, "getpid", return_value=self.foreign_pid):
                with self.assertRaises(LiveTradingSafetyError):
                    manager.__exit__(None, None, None)
            manager = proxy = None
            gc.collect()
            self.assertTrue(all(ref() is not None for ref in refs))
            self.assertEqual([], finalized)
            self.assertEqual([], object.__getattribute__(refs[0](), "accesses"))
            self.assertTrue(refs[1]().in_transaction)
            self.assertEqual(before, (database.read_bytes(), owner.marker_path.read_bytes()))
            self.assert_owner_held(owner)
            # Dispose the original-PID native test handle after the simulated child proof.
            refs[1]().commit()
            refs[1]().close()
            with self.assertRaises(full.sqlite3.ProgrammingError):
                refs[1]().execute("SELECT 1")

    @unittest.skipUnless(hasattr(os, "fork"), "Requires actual POSIX fork")
    def test_actual_fork_cold_connection_gc_retains_child_and_parent_closes_normally(self):
        owner, database = self.cold_store()
        with store.ledger_transaction(self.ledger):
            manager, proxy, refs, finalized = self.weak_cold_manager(database)
            deadline = store.current_ledger_deadline(self.ledger)
            full._sql(proxy, deadline, "BEGIN")
            before = database.read_bytes(), owner.marker_path.read_bytes()
            def unwind_and_collect():
                nonlocal manager, proxy
                with self.assertRaises(LiveTradingSafetyError):
                    manager.__exit__(None, None, None)
                manager = proxy = None
                gc.collect()
                self.assertTrue(all(ref() is not None for ref in refs))
                self.assertEqual([], finalized)
                self.assertEqual([], object.__getattribute__(refs[0](), "accesses"))
            try:
                self.fork_result(unwind_and_collect)
                self.assertTrue(refs[1]().in_transaction)
                self.assertEqual([], finalized)
                self.assertEqual(before, (database.read_bytes(), owner.marker_path.read_bytes()))
                self.assert_owner_held(owner)
                full._sql(proxy, deadline, "COMMIT")
            finally:
                manager.__exit__(None, None, None)
            manager = proxy = None
            gc.collect()
            self.assertTrue(all(ref() is None for ref in refs))
            self.assertEqual(["driver", "proxy"], sorted(finalized))

    def test_fresh_interpreter_can_claim_and_use_new_process_authority(self):
        script = '''import os, pathlib, sys
from app.integrations.exchanges.binance.orders import order_intent_store as s, spot_execution_owner as o
class W: pass
w=W(); p=pathlib.Path(sys.argv[1]); identity="00000000-0000-4000-8000-000000000029"
o.provision_owner_marker(p,uid=900000029,environment="live",store_id=identity)
owner=o.claim_execution_owner(p,uid=900000029,environment="live",store_id=identity,credential_fingerprint="f"*64,owner_wrapper=w)
with owner.submission(uid=owner.uid,environment=owner.environment,credential_fingerprint=owner.credential_fingerprint,owner_wrapper=w):
    with s.ledger_transaction(p): s.write_ledger(p,{"synthetic_fresh_process":True})
owner.close()
print(os.getpid())
'''
        path = self.home / "fresh-process" / "intents.json"
        result = subprocess.run([sys.executable, "-B", "-c", script, str(path)],
            capture_output=True, text=True, timeout=10, check=False)
        self.assertEqual(0, result.returncode, result.stderr)
        self.assertNotEqual(os.getpid(), int(result.stdout.strip()))
        self.assertEqual({"synthetic_fresh_process": True}, json.loads(path.read_text()))
        self.assertEqual("recovery_required", json.loads(owners.owner_marker_path(path).read_text())["state"])


if __name__ == "__main__":
    unittest.main()
