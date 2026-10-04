"""Selective indexed operations within one fully verified local owner session.

The complete historical receipt/ownership index is cached, never a sparse ledger.
Warm reads reuse that compact index. Windows keeps a proved native share-denial
handle throughout the session; other platforms verify complete history through
a fresh connection after each write. Compact commitment hashing remains linear
in history. This consistency proof is not anti-rollback authentication.
"""
from __future__ import annotations

from collections.abc import Iterator, Mapping
from contextlib import contextmanager
from dataclasses import dataclass, field
import os
from pathlib import Path
import sqlite3
import sys
import threading
import time
from typing import TYPE_CHECKING, cast
import weakref

from app.settings.live_safety import LiveTradingSafetyError
from .spot_execution_owner import SpotExecutionOwner
from .order_intent_store import current_ledger_deadline
from .spot_indexed_file_identity import (
    IndexedFileChangeReceipt, assert_indexed_native_guard, capture_indexed_file_change,
)
from .spot_indexed_intent_manifest import IndexedManifestReceipt
from . import spot_indexed_intent_store as full

if TYPE_CHECKING:
    from .spot_indexed_intent_bridge import IndexedReadAuthority, IndexedSourceBackupReceipt
    from .spot_indexed_intent_migration import IndexedMigrationReceipt

_INDEXED_PROCESS_ID = os.getpid()
_SESSIONS_LOCK = threading.RLock()
_SESSIONS: dict[Path, IndexedIntentSession] = {}
_INVALIDATIONS: dict[Path, tuple[weakref.ReferenceType[SpotExecutionOwner], int | None, str, weakref.ReferenceType[object]]] = {}
ProtectionProof = tuple[str, dict[str, dict[str, object]]]


def _fail(reason: str = "changed") -> LiveTradingSafetyError:
    return LiveTradingSafetyError(f"Indexed session {reason}; full verification and reconciliation are required.")


@contextmanager
def _session_registry() -> Iterator[None]:
    if _INDEXED_PROCESS_ID != os.getpid():
        raise _fail("was inherited by another process; start a fresh execution process")
    with _SESSIONS_LOCK:
        yield


@dataclass(frozen=True)
class IndexedAdmissionView:
    """Actual complete protection/unresolved sets, without an invented intents map."""
    receipt: full.IndexedStoreReceipt
    unresolved_ids: tuple[str, ...]
    _metadata: str = field(repr=False)
    _active: str = field(repr=False)
    _answers: tuple[tuple[str, tuple[str, ...]], ...] = field(repr=False)

    @property
    def metadata(self) -> dict[str, object]:
        return full._decode(self._metadata)

    @property
    def active_records(self) -> dict[str, dict[str, object]]:
        return cast(dict[str, dict[str, object]], full._decode(self._active))

    def owners(self, identifier: str) -> tuple[str, ...]:
        for key, owners in self._answers:
            if key == identifier:
                return owners
        raise _fail("ownership identifier was not queried")

    def assert_fresh(self, proof: ProtectionProof, *, exclude_client_order_id: str | None = None) -> None:
        unresolved = [key for key in self.unresolved_ids if key != exclude_client_order_id]
        if unresolved:
            raise LiveTradingSafetyError("Unresolved exchange order intent(s) block new live submissions; "
                                         f"reconcile {', '.join(unresolved[:3])} before continuing.")
        if self.receipt.store_id != proof[0] or self.active_records != proof[1]:
            raise LiveTradingSafetyError("Spot protection changed after its exact refresh; new exposure is blocked. Query it again.")


def _wrapper_context(wrapper: object) -> tuple[object, ...]:
    # Pure equality evidence only; credentials are never serialized or exposed.
    return (getattr(wrapper, "api_key", None), getattr(wrapper, "api_secret", None),
            getattr(wrapper, "mode", None), getattr(wrapper, "account_type", None),
            id(getattr(wrapper, "client", None)), getattr(wrapper, "_operator_spot_account_uid", None),
            id(getattr(wrapper, "_verified_spot_account_context", None)),
            bool(getattr(wrapper, "_spot_execution_revoked", False)))


def _rules() -> full.IndexedIntentRules:
    from . import order_intent_runtime as owned
    return full.IndexedIntentRules(owned.validate_order_intent_ledger, owned._is_unresolved,
                                  owned._has_active_spot_protection, owned.used_spot_client_order_ids)


def _fast_schema(connection: sqlite3.Connection, deadline: float) -> None:
    if (full._sql(connection, deadline, "PRAGMA application_id").fetchone()[0] != full._APPLICATION_ID
            or full._sql(connection, deadline, "PRAGMA user_version").fetchone()[0] != full._SCHEMA_VERSION
            or full._sql(connection, deadline, "PRAGMA journal_mode").fetchone()[0] != "delete"):
        raise _fail("schema or journal mode changed")
    observed = dict(full._sql(connection, deadline, "SELECT name,sql FROM sqlite_master WHERE sql IS NOT NULL").fetchall())
    def normalized(value: str) -> str:
        return " ".join(value.rstrip(";").split())
    if (set(observed) != set(full._DDL)
            or any(normalized(observed[key]) != normalized(value) for key, value in full._DDL.items())):
        raise _fail("schema changed")


class IndexedIntentSession:
    """Registry-owned authority; created only by open_indexed_session."""

    def __init__(self, *, owner: SpotExecutionOwner, owner_wrapper: object,
                 manifest: IndexedManifestReceipt, backup: IndexedSourceBackupReceipt,
                 migration: IndexedMigrationReceipt,
                 connection: sqlite3.Connection, snapshot: full.IndexedIntentSnapshot,
                 change: IndexedFileChangeReceipt, data_version: int,
                 commit_sequences: dict[str, int], rules: full.IndexedIntentRules, native_guard: bool) -> None:
        self._owner, self._wrapper = owner, weakref.ref(owner_wrapper)
        self._wrapper_context = _wrapper_context(owner_wrapper)
        self._manifest, self._backup, self._connection = manifest, backup, connection
        self._migration = migration
        self._receipt, self._change, self._data_version = snapshot.receipt, change, data_version
        self._pid, self._generation = os.getpid(), owner.generation
        self._metadata = full._canonical(full._parts(snapshot.payload)[0])
        self._record_receipts = {item.client_id: item for item in snapshot.record_receipts}
        self._commit_sequences = commit_sequences
        self._active, self._unresolved = set(snapshot.active_ids), set(snapshot.unresolved_ids)
        self._reserved = set(snapshot.reserved_owners)
        self._owners: dict[str, set[str]] = {}
        for identifier, key in self._reserved:
            self._owners.setdefault(identifier, set()).add(key)
        self._rules, self._closed = rules, False
        self._native_guard = native_guard
        self._pending: tuple[full.IndexedStoreReceipt, full.IndexedStoreReceipt] | None = None
        self._invalidation: str | None = None
        self._finalizer = weakref.finalize(owner_wrapper, self.close)

    @property
    def receipt(self) -> full.IndexedStoreReceipt:
        return self._receipt

    @property
    def native_guarded(self) -> bool:
        if self._closed or not self._native_guard:
            return False
        self._guard()
        return True

    def _guard(self) -> None:
        if self._native_guard:
            assert_indexed_native_guard(self._receipt.path)

    def close(self) -> None:
        if self._pid != os.getpid():
            # Do not enter inherited Python or SQLite mutexes, rollback, or
            # change the registry. Keep the connection untouched until OS exit.
            self._closed = True
            self._finalizer.detach()
            return
        with _session_registry():
            if self._closed:
                return
            self._closed = True
            if self._invalidation is not None:
                _INVALIDATIONS[self._receipt.logical_path] = (weakref.ref(self._owner), self._generation, self._invalidation, self._wrapper)
            if _SESSIONS.get(self._receipt.logical_path) is self:
                del _SESSIONS[self._receipt.logical_path]
            self._finalizer.detach()
            self._connection.close()

    def _assert_process(self) -> None:
        if self._pid != os.getpid():
            raise _fail("was inherited by another process; start a fresh execution process")

    def _authority(self, deadline: float, *, allow_pending: bool = False) -> float:
        self._assert_process()
        full._deadline(deadline, self._receipt.logical_path)
        with _session_registry():
            if self._closed or _SESSIONS.get(self._receipt.logical_path) is not self:
                raise _fail("is unavailable")
        if self._pending is not None and not allow_pending:
            raise _fail("complete writer publication is pending")
        wrapper = self._wrapper()
        if (wrapper is None or _wrapper_context(wrapper) != self._wrapper_context
                or self._pid != os.getpid() or self._owner.generation != self._generation):
            raise _fail("owner generation changed")
        binding = cast(dict[str, str], full._decode(self._metadata)["binding"])
        self._owner.assert_held(uid=self._owner.uid, environment=binding["environment"],
                                credential_fingerprint=binding["credential_fingerprint"], owner_wrapper=wrapper)
        self._manifest.assert_current(self._receipt.logical_path)
        self._backup.assert_current(self._manifest, self._receipt.logical_path)
        self._migration.assert_current(self._receipt.logical_path)
        return deadline

    def _files(self) -> None:
        self._guard()
        path = self._receipt.path
        if any(path.with_name(path.name + suffix).exists() for suffix in ("-wal", "-shm", "-journal")):
            raise _fail("unexpected journal files appeared")
        self._change.assert_current()

    def _header(self, deadline: float, receipt: full.IndexedStoreReceipt | None = None) -> None:
        expected = receipt or self._receipt
        state = full._sql(self._connection, deadline, "SELECT * FROM store_state").fetchall()
        if state != [(1, expected.database_id, str(expected.logical_path), expected.revision,
                      self._metadata, expected.head, expected.state_digest, expected.projection_digest)]:
            raise _fail("head or metadata changed")
        last = full._sql(self._connection, deadline, "SELECT seq,head FROM journal_commits ORDER BY seq DESC LIMIT 1").fetchone()
        if last != (expected.revision, expected.head):
            raise _fail("journal head changed")

    def _projections(self, deadline: float, *, active: set[str] | None = None,
                     unresolved: set[str] | None = None) -> None:
        actual_active = {row[0] for row in full._sql(self._connection, deadline, "SELECT client_id FROM active_projection").fetchall()}
        actual_unresolved = {row[0] for row in full._sql(self._connection, deadline, "SELECT client_id FROM unresolved_projection").fetchall()}
        if actual_active != (self._active if active is None else active) or actual_unresolved != (self._unresolved if unresolved is None else unresolved):
            raise _fail("complete projections changed")

    @contextmanager
    def _transaction(self, deadline: float, *, write: bool = False) -> Iterator[None]:
        # Reject before the try/cleanup path can touch an inherited connection.
        self._assert_process()
        # Invalid thread/context callers cannot rollback another held transaction.
        full._deadline(deadline, self._receipt.logical_path)
        try:
            deadline = self._authority(deadline)
            self._files()
            if full._sql(self._connection, deadline, "PRAGMA data_version").fetchone()[0] != self._data_version:
                raise _fail("external SQL transaction changed")
            full._sql(self._connection, deadline, "BEGIN IMMEDIATE" if write else "BEGIN")
            self._files()
            _fast_schema(self._connection, deadline)
            self._header(deadline)
            self._projections(deadline)
            yield
            self._assert_process()
            if not write:
                self._files()
                full._sql(self._connection, deadline, "COMMIT")
                self._files()
        except BaseException as exc:
            if self._pid != os.getpid():
                self.close()
                raise
            cleanup_errors: list[BaseException] = []
            try:
                if not self._closed and self._connection.in_transaction:
                    remaining_ms = max(0, int((deadline - time.monotonic()) * 1000))
                    self._connection.execute(f"PRAGMA busy_timeout={remaining_ms}")
                    self._connection.rollback()
            except BaseException as cleanup_error:
                cleanup_errors.append(cleanup_error)
            finally:
                self._invalidation = "fenced"
                try:
                    self.close()
                except BaseException as cleanup_error:
                    cleanup_errors.append(cleanup_error)
            for earlier, later in zip(cleanup_errors, cleanup_errors[1:]):
                later.__cause__ = earlier
            cleanup = cleanup_errors[-1] if cleanup_errors else None
            if not isinstance(exc, Exception):
                if cleanup is not None:
                    raise exc from cleanup
                raise
            for interruption in cleanup_errors:
                if not isinstance(interruption, Exception):
                    if cleanup is not None and cleanup is not interruption:
                        cleanup.__cause__ = exc
                        raise interruption from cleanup
                    raise interruption from (interruption.__cause__ or exc)
            if (isinstance(exc, (sqlite3.Error, OSError))
                    or any(isinstance(error, (sqlite3.Error, OSError)) for error in cleanup_errors)):
                raise _fail("storage is unavailable or busy") from (cleanup or exc)
            if cleanup is not None:
                raise cleanup from exc
            raise

    def _row(self, client_id: str, deadline: float) -> dict[str, object] | None:
        item = self._record_receipts.get(client_id)
        rows = full._sql(self._connection, deadline, "SELECT revision,record,digest,commit_seq FROM current_records WHERE client_id=?", (client_id,)).fetchall()
        if item is None:
            if rows:
                raise _fail("record membership changed")
            return None
        if len(rows) != 1:
            raise _fail("record is missing")
        revision, raw, digest, seq = rows[0]
        record = full._decode(raw)
        if (revision != item.revision or digest != item.digest or full._digest(record) != item.digest
                or seq != self._commit_sequences[client_id]):
            raise _fail("whole record changed")
        from .order_intent_runtime import validate_order_intent_record
        validate_order_intent_record(client_id, record)
        return record

    def read_record(self, client_id: str, *, deadline: float) -> dict[str, object] | None:
        with self._transaction(deadline):
            return self._row(client_id, deadline)

    def _view(self, probe_client_ids: tuple[str, ...], deadline: float) -> IndexedAdmissionView:
        if any(not isinstance(identifier, str) or not identifier for identifier in probe_client_ids):
            raise _fail("ownership query is invalid")
        active: dict[str, dict[str, object]] = {}
        for key in sorted(self._active):
            row = self._row(key, deadline)
            if row is None or not self._rules.has_active_protection(row):
                raise _fail("active record changed")
            active[key] = row
        answers = tuple((identifier, tuple(sorted(self._owners.get(identifier, set()))))
                        for identifier in sorted(set(probe_client_ids)))
        return IndexedAdmissionView(self._receipt, tuple(sorted(self._unresolved)), self._metadata,
                                    full._canonical(active), answers)

    def admission_view(self, *, probe_client_ids: tuple[str, ...] = (), deadline: float) -> IndexedAdmissionView:
        with self._transaction(deadline):
            return self._view(probe_client_ids, deadline)

    def cas_record(self, client_id: str, replacement: Mapping[str, object], *,
                   expected_record: Mapping[str, object] | None, deadline: float,
                   protection_proof: ProtectionProof | None = None,
                   exclude_client_order_id: str | None = None) -> dict[str, object] | None:
        with self._transaction(deadline, write=True):
            old = self._row(client_id, deadline)
            if old is None:
                raise _fail("record is missing")
            if expected_record is not None and full._canonical(old) != full._canonical(dict(expected_record)):
                full._sql(self._connection, deadline, "COMMIT")
                self._files()
                return None
            if protection_proof is not None:
                self._view((), deadline).assert_fresh(protection_proof, exclude_client_order_id=exclude_client_order_id)
            candidate = full._decode(full._canonical(dict(replacement)))
            if candidate == old:
                full._sql(self._connection, deadline, "COMMIT")
                self._files()
                return old
            return self._append_record(client_id, old, candidate, deadline)

    def insert_record(self, record: Mapping[str, object], *, protection_proof: ProtectionProof,
                      deadline: float) -> dict[str, object]:
        full._deadline(deadline, self._receipt.logical_path)
        candidate = full._decode(full._canonical(dict(record)))
        key = candidate.get("client_order_id")
        if not isinstance(key, str) or candidate.get("market") != "spot" or candidate.get("side") != "BUY":
            raise _fail("selective insertion requires a Spot BUY")
        with self._transaction(deadline, write=True):
            if self._row(key, deadline) is not None:
                raise _fail("intent already exists")
            self._view((), deadline).assert_fresh(protection_proof)
            return self._append_record(key, None, candidate, deadline)

    def _append_record(self, key: str, old: dict[str, object] | None, record: dict[str, object],
                       deadline: float) -> dict[str, object]:
        from .order_intent_runtime import _assert_spot_opo_cancel_alias, validate_order_intent_record
        validate_order_intent_record(key, record)
        if old is not None:
            full._preserve_record(old, record)
        projected_active, projected_unresolved, additions = full._projections({key: record}, self._rules)
        new_reservations = additions - self._reserved
        previous = self._receipt
        unchanged_projection = (
            old is not None and not new_reservations
            and (key in self._active) == (key in projected_active)
            and (key in self._unresolved) == (key in projected_unresolved)
        )
        if unchanged_projection:
            # Reservations only grow, and this existing row changes neither
            # complete membership set. Their previous commitment is identical.
            active, unresolved, reserved, next_owners = (
                self._active, self._unresolved, self._reserved, self._owners,
            )
            projection_hash = previous.projection_digest
            active_count, unresolved_count, reserved_count = len(active), len(unresolved), len(reserved)
        else:
            full._reject_new_alias_owners(self._reserved, additions)
            next_owners = {identifier: owners.copy() for identifier, owners in self._owners.items()}
            for identifier, owner in additions:
                next_owners.setdefault(identifier, set()).add(owner)
            active, unresolved = self._active - {key} | projected_active, self._unresolved - {key} | projected_unresolved
            reserved = self._reserved | additions
            projection_hash, active_count, unresolved_count, reserved_count = full._projection_receipt(active, unresolved, reserved)
        alias = record.get("pending_observed_client_order_id")
        if isinstance(alias, str):
            # The owned per-record helper consumes COMPLETE owners. Its first
            # argument is unused when owners are supplied; no ledger is invented.
            _assert_spot_opo_cancel_alias({}, key, record, alias, owners=next_owners)
        seq = previous.revision + 1
        old_item = self._record_receipts.get(key)
        item = full.IndexedRecordReceipt(key, old_item.revision + 1 if old_item is not None else 1, full._digest(record))
        receipts = {**self._record_receipts, key: item}
        metadata = full._decode(self._metadata)
        state_hash = full._state_digest(metadata, receipts)
        changed_hash = full._digest([[key, item.revision, item.digest]])
        values = (seq, previous.head, previous.metadata_digest, state_hash, projection_hash,
                  active_count, unresolved_count, reserved_count, changed_hash)
        head = full._commit_hash(previous.database_id, values)
        def sql(query: str, parameters: tuple[object, ...] = ()) -> sqlite3.Cursor:
            return full._sql(self._connection, deadline, query, parameters)
        sql("INSERT INTO journal_commits VALUES (?,?,?,?,?,?,?,?,?,?,?)",
            (seq, previous.head, self._metadata, previous.metadata_digest, state_hash, projection_hash,
             active_count, unresolved_count, reserved_count, changed_hash, head))
        sql("INSERT INTO journal_records VALUES (?,?,?,?,?)", (seq, key, item.revision, full._canonical(record), item.digest))
        sql("INSERT INTO current_records VALUES (?,?,?,?,?) ON CONFLICT(client_id) DO UPDATE SET revision=excluded.revision,record=excluded.record,digest=excluded.digest,commit_seq=excluded.commit_seq", (key, item.revision, full._canonical(record), item.digest, seq))
        for table, expected in (("active_projection", active), ("unresolved_projection", unresolved)):
            sql(f"DELETE FROM {table} WHERE client_id=?", (key,))
            if key in expected:
                sql(f"INSERT INTO {table} VALUES (?)", (key,))
        for identifier, owner in sorted(new_reservations):
            sql("INSERT INTO reserved_ids VALUES (?,?)", (identifier, owner))
        sql("UPDATE store_state SET revision=?,head=?,state_digest=?,projection_digest=? WHERE singleton=1", (seq, head, state_hash, projection_hash))
        next_receipt = full.IndexedStoreReceipt(previous.path, previous.logical_path, previous.file_identity,
                                               previous.database_id, previous.store_id, seq,
                                               previous.metadata_digest, state_hash, projection_hash, head)
        self._projections(deadline, active=active, unresolved=unresolved)
        # No persisted transition may outlive its actual owner or namespace.
        self._authority(deadline)
        self._guard()
        sql("COMMIT")
        # Pin a fresh read snapshot before adopting the post-COMMIT file token.
        # A foreign commit in this gap changes persistent data_version and fences.
        sql("BEGIN")
        if sql("PRAGMA data_version").fetchone()[0] != self._data_version:
            raise _fail("external SQL commit crossed publication")
        self._header(deadline, next_receipt)
        self._projections(deadline, active=active, unresolved=unresolved)
        _fast_schema(self._connection, deadline)
        self._authority(deadline)
        self._guard()
        change = capture_indexed_file_change(previous.path)
        # The known SQL commit changed the file token. A raw edit in that gap
        # can share its new token without changing SQLite data_version/head.
        # Verify ALL resulting state through a FRESH pager, pinned by this token;
        # the persistent connection may still cache pages predating raw edits.
        if not self._native_guard:
            checked = full.read_indexed_snapshot(
                previous.path, logical_path=previous.logical_path, rules=self._rules,
                expected_binding=cast(dict[str, str], metadata["binding"]), deadline=deadline,
                expected_store_id=previous.store_id, expected_backend_id=previous.database_id,
            )
            if (checked.receipt != next_receipt
                    or checked.record_receipts != tuple(receipts[name] for name in sorted(receipts))
                    or checked.active_ids != tuple(sorted(active))
                    or checked.unresolved_ids != tuple(sorted(unresolved))
                    or checked.reserved_owners != tuple(sorted(reserved))):
                raise _fail("complete post-COMMIT state differs from the owned transition")
        change.assert_current()
        self._authority(deadline)
        if sql("PRAGMA data_version").fetchone()[0] != self._data_version:
            raise _fail("external SQL changed during complete publication verification")
        if change.identity[:2] != previous.file_identity:
            raise _fail("database identity changed")
        if any(previous.path.with_name(previous.path.name + suffix).exists() for suffix in ("-wal", "-shm", "-journal")):
            raise _fail("unexpected journal appeared after commit")
        sql("COMMIT")
        change.assert_current()
        self._guard()
        self._receipt, self._change = next_receipt, change
        self._record_receipts, self._active, self._unresolved = receipts, active, unresolved
        self._reserved, self._owners = reserved, next_owners
        self._commit_sequences[key] = seq
        return record


def open_indexed_session(*, owner: SpotExecutionOwner, owner_wrapper: object,
                         expected_binding: Mapping[str, str], deadline: float,
                         manifest_receipt: IndexedManifestReceipt | None = None,
                         expected_authority: IndexedReadAuthority | None = None,
                         expected_snapshot: full.IndexedIntentSnapshot | None = None,
                         rules: full.IndexedIntentRules | None = None) -> IndexedIntentSession:
    """Full verification under the actual owner and original logical lock."""
    if not isinstance(owner, SpotExecutionOwner):
        raise _fail("requires the actual Spot execution owner")
    logical = owner.ledger_path
    full._deadline(deadline, logical)
    if _invalidation_for(owner) == "fenced":
        raise _fail("was fenced for this execution owner")
    owner.assert_held(uid=owner.uid, environment=expected_binding["environment"],
                      credential_fingerprint=expected_binding["credential_fingerprint"], owner_wrapper=owner_wrapper)
    with _session_registry():
        previous_session = _SESSIONS.get(logical)
        if previous_session is not None and previous_session._owner.fd is None:
            previous_session.close()
    from .spot_indexed_intent_bridge import IndexedReadAuthority, read_indexed_ledger
    authority = expected_authority or read_indexed_ledger(logical, expected_binding=expected_binding).indexed_authority
    if not isinstance(authority, IndexedReadAuthority):
        raise _fail("requires original complete read authority")
    if manifest_receipt is not None and manifest_receipt != authority.manifest:
        raise _fail("manifest differs from original complete read")
    manifest_receipt = authority.manifest
    if authority.original_binding() != dict(expected_binding):
        raise _fail("binding differs from original complete read")
    authority.migration.assert_current(logical)
    authority.source_backup.assert_current(manifest_receipt, logical)
    if expected_snapshot is not None and expected_snapshot != authority.snapshot:
        raise _fail("snapshot differs from original complete read")
    expected_snapshot = authority.snapshot
    owner.assert_held(uid=owner.uid, environment=expected_binding["environment"],
                      credential_fingerprint=expected_binding["credential_fingerprint"], owner_wrapper=owner_wrapper)
    if owner.ledger_path != logical:
        raise _fail("owner logical path differs")
    with _session_registry():
        existing = _SESSIONS.get(logical)
        if existing is not None and existing._owner.fd is None:
            existing.close()
            existing = None
        if existing is not None:
            raise _fail("already has a registered session")
    path = manifest_receipt.database_path(logical)
    # Issuing a new backup change receipt seals coalesced Windows USN reasons.
    # This intentionally replaces only the already-checked backup token.
    from .spot_indexed_intent_bridge import _verified_source_backup
    backup = _verified_source_backup(manifest_receipt, logical, checkpoint=True)
    change = capture_indexed_file_change(path)
    native_guard = sys.platform == "win32"
    uri = path.as_uri() + ("?mode=rw&exclusive=1&vfs=win32" if native_guard else "?mode=rw")
    try:
        connection = sqlite3.connect(uri, uri=True, timeout=0, isolation_level=None, check_same_thread=False)
    except (sqlite3.Error, OSError) as exc:
        raise _fail("startup database is unavailable") from exc
    try:
        # VFS file-acquisition retries do not obey SQLite busy_timeout.
        if time.monotonic() >= deadline:
            raise _fail("startup acquisition exceeded the original lock deadline")
        if native_guard:
            assert_indexed_native_guard(path)
        full._sql(connection, deadline, "PRAGMA synchronous=EXTRA")
        full._sql(connection, deadline, "PRAGMA foreign_keys=ON")
        full._sql(connection, deadline, "PRAGMA trusted_schema=OFF")
        full._sql(connection, deadline, "BEGIN")
        checked_rules = rules or _rules()
        snapshot = full._verified(connection, path, logical, deadline, checked_rules, expected_binding)
        if (snapshot.receipt.store_id != owner.store_id
                or snapshot.receipt.store_id != manifest_receipt.manifest.store_id
                or snapshot.receipt.database_id != manifest_receipt.manifest.backend_id):
            raise _fail("store/backend identity changed")
        if expected_snapshot is not None and snapshot != expected_snapshot:
            raise _fail("source changed since the prior complete read")
        sequences = {key: seq for key, seq in full._sql(connection, deadline, "SELECT client_id,commit_seq FROM current_records").fetchall()}
        version = full._sql(connection, deadline, "PRAGMA data_version").fetchone()[0]
        manifest_receipt.assert_current(logical)
        backup.assert_current(manifest_receipt, logical)
        authority.migration.assert_current(logical)
        change.assert_current()
        owner.assert_held(uid=owner.uid, environment=expected_binding["environment"],
                          credential_fingerprint=expected_binding["credential_fingerprint"], owner_wrapper=owner_wrapper)
        full._sql(connection, deadline, "COMMIT")
        change.assert_current()
        if native_guard:
            assert_indexed_native_guard(path)
        session = IndexedIntentSession(owner=owner, owner_wrapper=owner_wrapper, manifest=manifest_receipt,
                                       backup=backup, migration=authority.migration, connection=connection, snapshot=snapshot, change=change,
                                       data_version=version, commit_sequences=sequences, rules=checked_rules, native_guard=native_guard)
        with _session_registry():
            if logical in _SESSIONS:
                session.close()
                raise _fail("session registration changed")
            _SESSIONS[logical] = session
            _INVALIDATIONS.pop(logical, None)
        return session
    except BaseException as exc:
        connection.close()
        if isinstance(exc, (sqlite3.Error, OSError)):
            raise _fail("startup storage is unavailable") from exc
        raise


def _invalidation_for(owner: SpotExecutionOwner) -> str | None:
    with _session_registry():
        state = _INVALIDATIONS.get(owner.ledger_path)
        if state is None:
            return None
        registered_owner = state[0]()
        if registered_owner is None or state[1] != owner.generation or registered_owner is not owner:
            return None
        return state[2]


def indexed_namespace_known(path: Path) -> bool:
    """Classify an original indexed namespace without granting read authority."""
    logical = Path(os.path.abspath(path))
    with _session_registry():
        if logical in _SESSIONS:
            return True
        state = _INVALIDATIONS.get(logical)
    owner = None if state is None else state[0]()
    # A mutable generation field cannot erase a held owner's original fence.
    return owner is not None and owner.fd is not None


def indexed_namespace_attribution(
    path: Path | None = None, *, owner_wrapper: object | None = None,
) -> tuple[SpotExecutionOwner, Path] | None:
    """Classify the actual held original owner/path without granting authority."""
    logical = None if path is None else Path(os.path.abspath(path))
    with _session_registry():
        candidates: list[tuple[SpotExecutionOwner, Path]] = []
        for original_path, session in _SESSIONS.items():
            if (session._owner.fd is not None
                    and (logical is None or logical == original_path)
                    and (owner_wrapper is None or session._wrapper() is owner_wrapper)):
                candidates.append((session._owner, original_path))
        for original_path, state in _INVALIDATIONS.items():
            owner = state[0]()
            if (owner is not None and owner.fd is not None
                    and (logical is None or logical == original_path)
                    and (owner_wrapper is None or state[3]() is owner_wrapper)):
                candidates.append((owner, original_path))
        attribution: tuple[SpotExecutionOwner, Path] | None = None
        for owner, original_path in candidates:
            if attribution is None:
                attribution = owner, original_path
            elif owner is not attribution[0] or original_path != attribution[1]:
                raise _fail("wrapper or path has conflicting held indexed owner contexts")
        return attribution


def indexed_session_refresh_required(owner: SpotExecutionOwner) -> bool:
    """Only an explicitly recognized complete writer allows automatic rebuilding."""
    return _invalidation_for(owner) == "trusted_refresh"


def get_indexed_session(*, owner: SpotExecutionOwner, owner_wrapper: object,
                        expected_binding: Mapping[str, str], deadline: float) -> IndexedIntentSession | None:
    full._deadline(deadline, owner.ledger_path)
    if _invalidation_for(owner) == "fenced":
        raise _fail("was fenced for this execution owner")
    with _session_registry():
        session = _SESSIONS.get(owner.ledger_path)
    if session is None:
        return None
    if (session._owner is not owner or session._wrapper() is not owner_wrapper
            or full._decode(session._metadata)["binding"] != dict(expected_binding)):
        raise _fail("registry owner or binding differs")
    with session._transaction(deadline):
        return session


def _borrow_session(path: Path, expected_binding: Mapping[str, str] | None, deadline: float, *,
                    write: bool = False) -> IndexedIntentSession | None:
    logical = Path(os.path.abspath(path))
    full._deadline(deadline, logical)
    with _session_registry():
        session = _SESSIONS.get(logical)
        invalidation = _INVALIDATIONS.get(logical)
    if session is None:
        if invalidation is not None:
            owner = invalidation[0]()
            if owner is not None and owner.fd is not None and invalidation[2] == "fenced":
                raise _fail("was fenced for the held execution owner")
        return None
    if session._owner.fd is None and not write:
        session.close()
        return None
    if expected_binding is not None and full._decode(session._metadata)["binding"] != dict(expected_binding):
        raise _fail("borrowed binding differs")
    return session


def read_owned_indexed_source_backup(path: Path, *, deadline: float) -> IndexedSourceBackupReceipt | None:
    """Return the retained sealed backup only through actual session authority."""
    logical = Path(os.path.abspath(path))
    full._deadline(deadline, logical)
    # Reuse registry invalidation handling, including the portable healthy case.
    _borrow_session(logical, None, deadline)
    with _session_registry():
        session = _SESSIONS.get(logical)
    if session is None:
        return None
    with session._transaction(deadline):
        return session._backup


def _matches_compact(session: IndexedIntentSession, snapshot: full.IndexedIntentSnapshot) -> bool:
    return (snapshot.receipt == session._receipt
            and snapshot.record_receipts == tuple(session._record_receipts[key] for key in sorted(session._record_receipts))
            and snapshot.active_ids == tuple(sorted(session._active))
            and snapshot.unresolved_ids == tuple(sorted(session._unresolved))
            and snapshot.reserved_owners == tuple(sorted(session._reserved))
            and full._canonical(full._parts(snapshot.payload)[0]) == session._metadata)


def read_owned_indexed_snapshot(path: Path, *, expected_binding: Mapping[str, str] | None,
                                deadline: float) -> full.IndexedIntentSnapshot | None:
    """Complete bridge read through the actual registered owner connection."""
    session = _borrow_session(path, expected_binding, deadline)
    if session is None:
        return None
    with session._transaction(deadline):
        snapshot = full._read_indexed_snapshot_in_transaction(
            session._connection, session._receipt.path, logical_path=session._receipt.logical_path,
            rules=session._rules, expected_binding=expected_binding, deadline=deadline,
            expected_store_id=session._receipt.store_id, expected_backend_id=session._receipt.database_id)
        if not _matches_compact(session, snapshot):
            raise _fail("complete borrowed read differs from its original anchor")
        return snapshot


def replace_owned_indexed_snapshot(path: Path, payload: object, *, expected: full.IndexedIntentSnapshot,
                                   expected_binding: Mapping[str, str], deadline: float,
                                   expected_new_binding: Mapping[str, str] | None = None) -> full.IndexedIntentSnapshot | None:
    """Complete CAS with a pending result until the bridge finishes publication."""
    session = _borrow_session(path, expected_binding, deadline, write=True)
    if session is None:
        return None
    if expected_new_binding is not None and dict(expected_new_binding) != dict(expected_binding):
        raise _fail("binding cannot rotate within a held execution owner")
    detached = full._validate(payload, session._rules, expected_binding)
    with session._transaction(deadline, write=True):
        if not _matches_compact(session, expected):
            raise _fail("complete borrowed writer authority differs")
        previous = session._receipt
        result = full._replace_indexed_snapshot_in_transaction(
            session._connection, previous.path, detached, expected=expected, rules=session._rules,
            expected_binding=expected_binding, deadline=deadline, expected_new_binding=expected_new_binding)
        sequences = dict(full._sql(session._connection, deadline, "SELECT client_id,commit_seq FROM current_records").fetchall())
        session._authority(deadline)
        session._guard()
        full._sql(session._connection, deadline, "COMMIT")
        if result.receipt == previous:
            session._files()
            return result
        # Native guard never closes; portable writes also require a fresh pager
        # to prove every post-COMMIT byte under the newly pinned token. Bridge
        # pointer/source checks still have to finish before accepting this result.
        session._pending = (previous, result.receipt)
        session._receipt = result.receipt
        session._metadata = full._canonical(full._parts(result.payload)[0])
        session._record_receipts = {item.client_id: item for item in result.record_receipts}
        session._commit_sequences = sequences
        session._active, session._unresolved = set(result.active_ids), set(result.unresolved_ids)
        session._reserved = set(result.reserved_owners)
        session._owners = {}
        for identifier, key in session._reserved:
            session._owners.setdefault(identifier, set()).add(key)
        full._sql(session._connection, deadline, "BEGIN")
        if full._sql(session._connection, deadline, "PRAGMA data_version").fetchone()[0] != session._data_version:
            raise _fail("external SQL crossed complete publication")
        session._guard()
        session._header(deadline)
        session._projections(deadline)
        _fast_schema(session._connection, deadline)
        session._authority(deadline, allow_pending=True)
        change = capture_indexed_file_change(result.receipt.path)
        if not session._native_guard:
            checked = full.read_indexed_snapshot(
                result.receipt.path, logical_path=result.receipt.logical_path,
                rules=session._rules, expected_binding=expected_binding, deadline=deadline,
                expected_store_id=result.receipt.store_id, expected_backend_id=result.receipt.database_id)
            if checked != result:
                raise _fail("complete post-COMMIT borrowed state differs from its owned transition")
        change.assert_current()
        session._authority(deadline, allow_pending=True)
        if full._sql(session._connection, deadline, "PRAGMA data_version").fetchone()[0] != session._data_version:
            raise _fail("external SQL changed during complete borrowed verification")
        if change.identity[:2] != previous.file_identity:
            raise _fail("complete writer database identity changed")
        full._sql(session._connection, deadline, "COMMIT")
        change.assert_current()
        session._guard()
        session._change = change
        return result


def notify_indexed_full_commit(path: Path, snapshot: full.IndexedIntentSnapshot,
                               authority: IndexedReadAuthority) -> None:
    """Recognize a completed full-writer CAS, after its namespace checks passed."""
    deadline = current_ledger_deadline(path)
    logical = authority.manifest.logical_path
    if Path(os.path.abspath(path)) != logical:
        raise _fail("full writer logical source differs")
    with _session_registry():
        session = _SESSIONS.get(logical)
    if session is None:
        return
    try:
        old = session._pending[0] if session._pending is not None else session._receipt
        if (authority.snapshot.receipt != old or authority.manifest != session._manifest
                or authority.migration != session._migration or authority.source_backup != session._backup
                or snapshot.receipt.path != old.path or snapshot.receipt.logical_path != logical
                or snapshot.receipt.file_identity != old.file_identity
                or snapshot.receipt.database_id != old.database_id or snapshot.receipt.store_id != old.store_id
                or snapshot.receipt.revision not in (old.revision, old.revision + 1)):
            raise _fail("complete-writer authority differs")
        session._authority(deadline, allow_pending=True)
        if session._pending is not None:
            if session._pending != (old, snapshot.receipt) or not _matches_compact(session, snapshot):
                raise _fail("pending complete-writer result differs")
            session._files()
            session._pending = None
            return
        if snapshot.receipt == old:
            session._files()
            return
        session._invalidation = "trusted_refresh"
        session.close()
    except BaseException:
        session._invalidation = "fenced"
        session.close()
        raise


def reject_indexed_full_commit(path: Path) -> None:
    """Fence a borrowed committed result whose bridge publication failed."""
    current_ledger_deadline(path)
    logical = Path(os.path.abspath(path))
    with _session_registry():
        session = _SESSIONS.get(logical)
    if session is not None and session._pending is not None:
        session._invalidation = "fenced"
        session.close()


def close_indexed_session(owner: SpotExecutionOwner) -> None:
    """Release this actual owner's persistent connection when it is revoked."""
    with _session_registry():
        session = _SESSIONS.get(owner.ledger_path)
    if session is not None and session._owner is owner:
        session.close()
