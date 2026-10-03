"""Full-verified SQLite foundation for an explicitly migrated intent ledger.

Callers hold the original logical ledger lock (and allocation lock when needed).
This module neither migrates nor routes trading operations. Every operation verifies
complete journal history and projections; it is not a selective-read capacity claim.
"""
from __future__ import annotations

import hashlib
import json
import math
import os
import sqlite3
import stat
import time
from collections.abc import Callable, Mapping
from contextlib import contextmanager
from dataclasses import dataclass, field
from pathlib import Path
from typing import Iterator, Protocol, cast
from uuid import UUID, uuid4

from app.settings.live_safety import LiveTradingSafetyError

from .order_intent_store import current_ledger_deadline, _sync_directory

_SCHEMA_VERSION = 1
_APPLICATION_ID = 0x54424933
_IMMUTABLE_RECORD_FIELDS = (
    "client_order_id", "market", "type", "side", "symbol", "quantity", "request", "request_signature",
    "created_at", "desktop_entry_source", "primary_fill_receipt", "primary_fill_signature",
)
_DDL = {
    "store_state": "CREATE TABLE store_state (singleton INTEGER PRIMARY KEY CHECK(singleton=1), database_id TEXT NOT NULL, logical_path TEXT NOT NULL, revision INTEGER NOT NULL, metadata TEXT NOT NULL, head TEXT NOT NULL, state_digest TEXT NOT NULL, projection_digest TEXT NOT NULL) STRICT",
    "current_records": "CREATE TABLE current_records (client_id TEXT PRIMARY KEY, revision INTEGER NOT NULL, record TEXT NOT NULL, digest TEXT NOT NULL, commit_seq INTEGER NOT NULL, FOREIGN KEY(commit_seq,client_id) REFERENCES journal_records(seq,client_id)) STRICT",
    "journal_commits": "CREATE TABLE journal_commits (seq INTEGER PRIMARY KEY, previous TEXT NOT NULL, metadata TEXT NOT NULL, metadata_digest TEXT NOT NULL, state_digest TEXT NOT NULL, projection_digest TEXT NOT NULL, active_count INTEGER NOT NULL, unresolved_count INTEGER NOT NULL, reserved_count INTEGER NOT NULL, changed_digest TEXT NOT NULL, head TEXT NOT NULL) STRICT",
    "journal_records": "CREATE TABLE journal_records (seq INTEGER NOT NULL REFERENCES journal_commits(seq), client_id TEXT NOT NULL, revision INTEGER NOT NULL, record TEXT NOT NULL, digest TEXT NOT NULL, PRIMARY KEY(seq,client_id), UNIQUE(client_id,revision)) STRICT",
    "active_projection": "CREATE TABLE active_projection (client_id TEXT PRIMARY KEY REFERENCES current_records(client_id)) STRICT",
    "unresolved_projection": "CREATE TABLE unresolved_projection (client_id TEXT PRIMARY KEY REFERENCES current_records(client_id)) STRICT",
    "reserved_ids": "CREATE TABLE reserved_ids (reserved_id TEXT NOT NULL, owner_id TEXT NOT NULL REFERENCES current_records(client_id), PRIMARY KEY(reserved_id,owner_id)) STRICT",
}
for _table in ("journal_commits", "journal_records", "reserved_ids"):
    for _action in ("UPDATE", "DELETE"):
        _name = f"immutable_{_table}_{_action.lower()}"
        _DDL[_name] = f"CREATE TRIGGER {_name} BEFORE {_action} ON {_table} BEGIN SELECT RAISE(ABORT,'immutable intent history'); END"


class LedgerValidator(Protocol):
    def __call__(self, payload: object, *, expected_binding: Mapping[str, str] | None = None) -> dict[str, object]: ...


@dataclass(frozen=True)
class IndexedIntentRules:
    """Owned complete-ledger validator and projectors; never isolated-row validators."""
    validate_ledger: LedgerValidator
    is_unresolved: Callable[[Mapping[str, object]], bool]
    has_active_protection: Callable[[Mapping[str, object]], bool]
    used_client_ids: Callable[[Mapping[str, object]], set[str]]


@dataclass(frozen=True)
class IndexedStoreReceipt:
    path: Path
    logical_path: Path
    file_identity: tuple[int, int]
    database_id: str
    store_id: str
    revision: int
    metadata_digest: str
    state_digest: str
    projection_digest: str
    head: str


@dataclass(frozen=True)
class IndexedRecordReceipt:
    client_id: str
    revision: int
    digest: str


@dataclass(frozen=True)
class IndexedIntentSnapshot:
    """A verified complete view; callers only receive detached mutable payloads."""
    receipt: IndexedStoreReceipt
    record_receipts: tuple[IndexedRecordReceipt, ...]
    active_ids: tuple[str, ...]
    unresolved_ids: tuple[str, ...]
    reserved_owners: tuple[tuple[str, str], ...]
    _payload_json: str = field(repr=False)

    @property
    def payload(self) -> IndexedLedgerPayload:
        return IndexedLedgerPayload(_decode(self._payload_json), self)

    def record_receipt(self, client_id: str) -> IndexedRecordReceipt | None:
        return next((item for item in self.record_receipts if item.client_id == client_id), None)

    def record(self, client_id: str) -> dict[str, object] | None:
        intents = cast(dict[str, dict[str, object]], self.payload["intents"])
        return intents.get(client_id)

    def owners(self, reserved_id: str) -> tuple[str, ...]:
        return tuple(owner for identifier, owner in self.reserved_owners if identifier == reserved_id)


class IndexedLedgerPayload(dict[str, object]):
    """Legacy-shaped mutable copy carrying its immutable full-read CAS authority."""
    def __init__(self, value: dict[str, object], snapshot: IndexedIntentSnapshot) -> None:
        super().__init__(value)
        self._indexed_snapshot = snapshot

    @property
    def indexed_snapshot(self) -> IndexedIntentSnapshot:
        return self._indexed_snapshot


def _fail(reason: str = "integrity check failed") -> LiveTradingSafetyError:
    return LiveTradingSafetyError(f"Indexed intent storage {reason}; restore and reconcile without resetting history.")


def _canonical(value: object) -> str:
    try:
        return json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False)
    except (ValueError, TypeError, OverflowError) as exc:
        raise _fail("contains unsupported data") from exc


def _digest(value: object) -> str:
    return hashlib.sha256(_canonical(value).encode("utf-8")).hexdigest()


def _parse_json_dict(raw: str) -> dict[str, object]:
    """Parse strict JSON syntax and shape; callers establish canonical bytes."""
    def unique(pairs: list[tuple[str, object]]) -> dict[str, object]:
        result: dict[str, object] = {}
        for key, value in pairs:
            if key in result:
                raise _fail("contains duplicate JSON keys")
            result[key] = value
        return result

    def invalid_constant(value: str) -> object:
        raise _fail("contains nonfinite JSON")

    try:
        value = json.loads(raw, object_pairs_hook=unique, parse_constant=invalid_constant)
    except (ValueError, TypeError, UnicodeError, RecursionError) as exc:
        raise _fail("contains malformed JSON") from exc
    if not isinstance(value, dict):
        raise _fail("contains noncanonical JSON")
    return cast(dict[str, object], value)


def _decode(raw: str) -> dict[str, object]:
    value = _parse_json_dict(raw)
    if _canonical(value) != raw:
        raise _fail("contains noncanonical JSON")
    return value


def _validated_canonical(payload: object, rules: IndexedIntentRules,
                         expected_binding: Mapping[str, str] | None) -> str:
    """Retain the complete validation proof without creating an unused copy."""
    original = _canonical(payload)
    detached = _decode(original)
    checked = rules.validate_ledger(detached, expected_binding=expected_binding)
    if (_canonical(checked) != original or _canonical(detached) != original
            or checked.get("format_version") != 2):
        raise _fail("requires unchanged validated v2 data")
    return original


def _validate(payload: object, rules: IndexedIntentRules,
              expected_binding: Mapping[str, str] | None) -> dict[str, object]:
    # The core proved immutable canonical bytes. Detach the result from every
    # container retained by the callback whenever the caller needs a payload.
    return _parse_json_dict(_validated_canonical(payload, rules, expected_binding))


def _parts(payload: dict[str, object]) -> tuple[dict[str, object], dict[str, dict[str, object]]]:
    intents = payload.get("intents")
    if not isinstance(intents, dict) or any(not isinstance(key, str) or not isinstance(row, dict)
                                          for key, row in intents.items()):
        raise _fail()
    return ({key: value for key, value in payload.items() if key != "intents"},
            cast(dict[str, dict[str, object]], intents))


def _history_prefix(old: object, new: object) -> None:
    """Preserve old history paths, including paths inside otherwise mutable lists."""
    if isinstance(old, list):
        candidate_list = new if isinstance(new, list) else []
        for index, item in enumerate(old):
            _history_prefix(item, candidate_list[index] if index < len(candidate_list) else None)
        return
    if not isinstance(old, dict):
        return
    if not isinstance(new, dict):
        new = {}
    for name, value in old.items():
        if name == "history" or name.endswith("_history"):
            candidate = new.get(name)
            if isinstance(value, list):
                if not isinstance(candidate, list) or _canonical(candidate[:len(value)]) != _canonical(value):
                    raise _fail("cannot truncate or rewrite history")
            elif name not in new or _canonical(value) != _canonical(candidate):
                # Accepted opaque non-list extensions gain no invented list schema.
                raise _fail("cannot rewrite opaque history metadata")
        elif isinstance(value, (dict, list)):
            _history_prefix(value, new.get(name))


def _preserve_record(old: dict[str, object], new: dict[str, object]) -> None:
    for name in _IMMUTABLE_RECORD_FIELDS:
        if name in old and (name not in new or _canonical(old[name]) != _canonical(new[name])):
            raise _fail("cannot rewrite original intent identity or acquisition")
    _history_prefix(old, new)


def _preserve_metadata(old: dict[str, object], new: dict[str, object]) -> None:
    if not set(old).issubset(new):
        raise _fail("cannot remove ledger metadata")
    for name in ("format_version", "store_id", "created_at"):
        if name in old and old[name] != new.get(name):
            raise _fail("cannot replace ledger identity")
    _history_prefix(old, new)
    old_binding, new_binding = old.get("binding"), new.get("binding")
    if old_binding != new_binding:
        old_history = old.get("credential_rotation_history", [])
        new_history = new.get("credential_rotation_history")
        if (not isinstance(old_binding, dict) or not isinstance(new_binding, dict)
                or any(old_binding.get(name) != new_binding.get(name) for name in ("exchange", "environment"))
                or not isinstance(old_history, list) or not isinstance(new_history, list)
                or len(new_history) <= len(old_history)
                or not isinstance(new_history[len(old_history)], dict)
                or new_history[len(old_history)].get("previous_fingerprint") != old_binding.get("credential_fingerprint")
                or not isinstance(new_history[-1], dict)
                or new_history[-1].get("new_fingerprint") != new_binding.get("credential_fingerprint")):
            raise _fail("binding transition requires continuous credential rotation history")


def _projections(records: dict[str, dict[str, object]], rules: IndexedIntentRules
                 ) -> tuple[set[str], set[str], set[tuple[str, str]]]:
    active: set[str] = set()
    unresolved: set[str] = set()
    reservations: set[tuple[str, str]] = set()
    for key, row in records.items():
        active_value = rules.has_active_protection(row)
        unresolved_value = rules.is_unresolved(row)
        identifiers = rules.used_client_ids({key: row})
        if (type(active_value) is not bool or type(unresolved_value) is not bool or not isinstance(identifiers, set)
                or any(not isinstance(value, str) or not value for value in identifiers)):
            raise _fail("has invalid owned projections")
        if active_value:
            active.add(key)
        if unresolved_value:
            unresolved.add(key)
        reservations.update((identifier, key) for identifier in identifiers | {key})
    return active, unresolved, reservations


def _projection_receipt(active: set[str], unresolved: set[str], reserved: set[tuple[str, str]]) -> tuple[str, int, int, int]:
    return (_digest([sorted(active), sorted(unresolved), sorted(reserved)]),
            len(active), len(unresolved), len(reserved))


def _state_digest(metadata: dict[str, object], receipts: dict[str, IndexedRecordReceipt]) -> str:
    return _digest([metadata, [[key, item.revision, item.digest] for key, item in sorted(receipts.items())]])


def _commit_hash(database_id: str, values: tuple[object, ...]) -> str:
    return _digest([database_id, *values])


def _path(path: Path) -> Path:
    value = Path(os.path.abspath(path))
    for component in (value, *value.parents):
        try:
            info = component.lstat()
        except FileNotFoundError:
            continue
        if (stat.S_ISLNK(info.st_mode)
                or getattr(info, "st_file_attributes", 0) & getattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT", 0x400)):
            raise _fail("cannot use linked paths")
    return value


def _identity(path: Path) -> tuple[int, int]:
    info = path.lstat()
    if not stat.S_ISREG(info.st_mode) or info.st_nlink != 1:
        raise _fail("requires a unique regular database file")
    return info.st_dev, info.st_ino


def _deadline(value: float, logical_path: Path) -> float:
    held = current_ledger_deadline(logical_path)
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value) or value > held:
        raise _fail("cannot extend the held lock deadline")
    return float(value)


def _sql(connection: sqlite3.Connection, deadline: float, query: str,
         parameters: tuple[object, ...] = ()) -> sqlite3.Cursor:
    remaining_ms = max(0, int((deadline - time.monotonic()) * 1000))
    connection.execute(f"PRAGMA busy_timeout={remaining_ms}")
    return connection.execute(query, parameters)


@contextmanager
def _connection(path: Path, logical_path: Path, deadline: float) -> Iterator[sqlite3.Connection]:
    deadline = _deadline(deadline, logical_path)
    try:
        identity = _identity(path)
        if path.with_name(path.name + "-wal").exists() or path.with_name(path.name + "-shm").exists():
            raise _fail("cannot use WAL storage")
        connection = sqlite3.connect(path.as_uri() + "?mode=rw", uri=True, timeout=0, isolation_level=None)
        primary: BaseException | None = None
        try:
            mode = _sql(connection, deadline, "PRAGMA journal_mode").fetchone()[0]
            if mode not in ("delete",):
                raise _fail("requires DELETE journaling")
            _sql(connection, deadline, "PRAGMA synchronous=EXTRA")
            _sql(connection, deadline, "PRAGMA foreign_keys=ON")
            _sql(connection, deadline, "PRAGMA trusted_schema=OFF")
            yield connection
            if _identity(path) != identity:
                raise _fail("database file changed")
        except BaseException as exc:
            primary = exc
            raise
        finally:
            cleanup_errors: list[BaseException] = []
            try:
                if connection.in_transaction:
                    remaining_ms = max(0, int((deadline - time.monotonic()) * 1000))
                    connection.execute(f"PRAGMA busy_timeout={remaining_ms}")
                    connection.rollback()
            except BaseException as cleanup_error:
                cleanup_errors.append(cleanup_error)
            finally:
                try:
                    connection.close()
                except BaseException as cleanup_error:
                    cleanup_errors.append(cleanup_error)
            if cleanup_errors:
                for earlier, later in zip(cleanup_errors, cleanup_errors[1:]):
                    later.__cause__ = earlier
                cleanup = cleanup_errors[-1]
                if primary is not None and not isinstance(primary, Exception):
                    raise primary from cleanup
                for interruption in cleanup_errors:
                    if not isinstance(interruption, Exception):
                        if cleanup is not interruption:
                            cleanup.__cause__ = primary
                            raise interruption from cleanup
                        raise interruption from (interruption.__cause__ or primary)
                if (isinstance(primary, (sqlite3.Error, OSError))
                        or any(isinstance(error, (sqlite3.Error, OSError)) for error in cleanup_errors)):
                    raise _fail("is unavailable or busy") from cleanup
                raise cleanup from primary
    except (sqlite3.Error, OSError) as exc:
        raise _fail("is unavailable or busy") from exc


def _check_schema(connection: sqlite3.Connection, deadline: float) -> None:
    if (_sql(connection, deadline, "PRAGMA application_id").fetchone()[0] != _APPLICATION_ID
            or _sql(connection, deadline, "PRAGMA user_version").fetchone()[0] != _SCHEMA_VERSION):
        raise _fail("schema is unsupported")
    observed = {name: sql for name, sql in _sql(connection, deadline,
                "SELECT name,sql FROM sqlite_master WHERE sql IS NOT NULL").fetchall()}
    def normalized(value: str) -> str:
        return " ".join(value.rstrip(";").split())
    if (set(observed) != set(_DDL)
            or any(normalized(observed[name]) != normalized(sql) for name, sql in _DDL.items())):
        raise _fail("schema changed")
    if (_sql(connection, deadline, "PRAGMA integrity_check").fetchall() != [("ok",)]
            or _sql(connection, deadline, "PRAGMA foreign_key_check").fetchall()):
        raise _fail()


def _verified(connection: sqlite3.Connection, path: Path, logical_path: Path, deadline: float,
              rules: IndexedIntentRules, expected_binding: Mapping[str, str] | None) -> IndexedIntentSnapshot:
    _check_schema(connection, deadline)
    states = _sql(connection, deadline, "SELECT * FROM store_state").fetchall()
    if len(states) != 1:
        raise _fail()
    _, database_id, logical, revision, metadata_raw, head, state_hash, projection_hash = states[0]
    try:
        if str(UUID(database_id)) != database_id or logical != str(logical_path):
            raise _fail("identity changed")
    except (ValueError, TypeError, AttributeError) as exc:
        raise _fail() from exc
    records: dict[str, dict[str, object]] = {}
    receipts: dict[str, IndexedRecordReceipt] = {}
    last_seq: dict[str, int] = {}
    reserved: set[tuple[str, str]] = set()
    previous = ""
    metadata: dict[str, object] = {}
    active: set[str] = set()
    unresolved: set[str] = set()
    commits = _sql(connection, deadline, "SELECT * FROM journal_commits ORDER BY seq").fetchall()
    if not commits:
        raise _fail("history is missing")
    all_versions = _sql(connection, deadline, "SELECT * FROM journal_records ORDER BY seq,client_id").fetchall()
    versions: dict[int, list[tuple[object, ...]]] = {}
    for row in all_versions:
        versions.setdefault(row[0], []).append(row)
    for expected_seq, commit in enumerate(commits, 1):
        (seq, predecessor, raw, metadata_hash, current_hash, projections_hash,
         active_count, unresolved_count, reserved_count, changed_hash, commit_head) = commit
        if seq != expected_seq or predecessor != previous:
            raise _fail("journal sequence changed")
        next_metadata = _decode(raw)
        if "intents" in next_metadata or metadata_hash != _digest(next_metadata):
            raise _fail()
        if expected_seq > 1:
            _preserve_metadata(metadata, next_metadata)
        changed: list[list[object]] = []
        before_reserved = reserved.copy()
        for _, key, row_revision, row_raw, row_hash in versions.get(seq, []):
            record = _decode(cast(str, row_raw))
            expected_revision = receipts[cast(str, key)].revision + 1 if key in receipts else 1
            if row_revision != expected_revision or row_hash != _digest(record):
                raise _fail("record history changed")
            if key in records:
                _preserve_record(records[cast(str, key)], record)
            records[cast(str, key)] = record
            receipts[cast(str, key)] = IndexedRecordReceipt(cast(str, key), cast(int, row_revision), cast(str, row_hash))
            last_seq[cast(str, key)] = seq
            changed.append([key, row_revision, row_hash])
        metadata = next_metadata
        _validated_canonical({**metadata, "intents": records}, rules, None)
        active, unresolved, current_reserved = _projections(records, rules)
        if expected_seq > 1:
            _reject_new_alias_owners(before_reserved, current_reserved)
        reserved.update(current_reserved)
        checked_projection = _projection_receipt(active, unresolved, reserved)
        if (checked_projection != (projections_hash, active_count, unresolved_count, reserved_count)
                or current_hash != _state_digest(metadata, receipts) or changed_hash != _digest(changed)):
            raise _fail("journal commitments changed")
        values = (seq, predecessor, metadata_hash, current_hash, projections_hash,
                  active_count, unresolved_count, reserved_count, changed_hash)
        if commit_head != _commit_hash(database_id, values):
            raise _fail("journal chain changed")
        previous = commit_head
    if set(versions) - {commit[0] for commit in commits}:
        raise _fail("contains orphaned history")
    actual_rows = _sql(connection, deadline, "SELECT * FROM current_records ORDER BY client_id").fetchall()
    expected_rows = [(key, item.revision, _canonical(records[key]), item.digest, last_seq[key])
                     for key, item in sorted(receipts.items())]
    actual_active = {row[0] for row in _sql(connection, deadline, "SELECT client_id FROM active_projection").fetchall()}
    actual_unresolved = {row[0] for row in _sql(connection, deadline, "SELECT client_id FROM unresolved_projection").fetchall()}
    actual_reserved = set(_sql(connection, deadline, "SELECT reserved_id,owner_id FROM reserved_ids").fetchall())
    if (actual_rows != expected_rows or actual_active != active or actual_unresolved != unresolved
            or actual_reserved != reserved or revision != len(commits) or head != previous
            or metadata_raw != _canonical(metadata) or state_hash != commits[-1][4]
            or projection_hash != commits[-1][5]):
        raise _fail("current state or complete projections changed")
    payload = _validate({**metadata, "intents": records}, rules, expected_binding)
    store_id = metadata.get("store_id")
    if not isinstance(store_id, str):
        raise _fail()
    receipt = IndexedStoreReceipt(path, logical_path, _identity(path), database_id, store_id, revision,
                                  _digest(metadata), state_hash, projection_hash, head)
    return IndexedIntentSnapshot(receipt, tuple(receipts[key] for key in sorted(receipts)),
                                 tuple(sorted(active)), tuple(sorted(unresolved)), tuple(sorted(reserved)),
                                 _canonical(payload))


def _reject_new_alias_owners(old: set[tuple[str, str]], new: set[tuple[str, str]]) -> None:
    owners: dict[str, set[str]] = {}
    for identifier, owner in old:
        owners.setdefault(identifier, set()).add(owner)
    for identifier, owner in new - old:
        if identifier in owners and owner not in owners[identifier]:
            raise _fail("cannot reuse a historical client identifier")
    new_owners: dict[str, set[str]] = {}
    for identifier, owner in new - old:
        new_owners.setdefault(identifier, set()).add(owner)
    if any(len(value) > 1 for value in new_owners.values()):
        raise _fail("cannot introduce shared client identifiers")


def _append(connection: sqlite3.Connection, deadline: float, database_id: str, logical_path: Path,
            payload: dict[str, object], rules: IndexedIntentRules,
            old: IndexedIntentSnapshot | None) -> None:
    metadata, records = _parts(payload)
    old_records = _parts(old.payload)[1] if old is not None else {}
    old_receipts = {item.client_id: item for item in old.record_receipts} if old is not None else {}
    if not set(old_records).issubset(records):
        raise _fail("cannot remove intent records")
    if old is not None:
        _preserve_metadata(_parts(old.payload)[0], metadata)
    changes: list[tuple[str, IndexedRecordReceipt]] = []
    for key, row in sorted(records.items()):
        if key in old_records:
            _preserve_record(old_records[key], row)
            if _canonical(row) == _canonical(old_records[key]):
                continue
        item = IndexedRecordReceipt(key, old_receipts[key].revision + 1 if key in old_receipts else 1, _digest(row))
        changes.append((key, item))
    seq = old.receipt.revision + 1 if old is not None else 1
    previous = old.receipt.head if old is not None else ""
    receipts = {**old_receipts, **{key: item for key, item in changes}}
    active, unresolved, current_reserved = _projections(records, rules)
    reserved = set(old.reserved_owners) if old is not None else set()
    if old is not None:
        _reject_new_alias_owners(reserved, current_reserved)
    reserved.update(current_reserved)
    projections_hash, active_count, unresolved_count, reserved_count = _projection_receipt(active, unresolved, reserved)
    state_hash = _state_digest(metadata, receipts)
    changed_hash = _digest([[key, item.revision, item.digest] for key, item in changes])
    metadata_hash = _digest(metadata)
    values = (seq, previous, metadata_hash, state_hash, projections_hash,
              active_count, unresolved_count, reserved_count, changed_hash)
    head = _commit_hash(database_id, values)
    _sql(connection, deadline, "INSERT INTO journal_commits VALUES (?,?,?,?,?,?,?,?,?,?,?)",
         (seq, previous, _canonical(metadata), metadata_hash, state_hash, projections_hash,
          active_count, unresolved_count, reserved_count, changed_hash, head))
    for key, item in changes:
        raw = _canonical(records[key])
        _sql(connection, deadline, "INSERT INTO journal_records VALUES (?,?,?,?,?)", (seq, key, item.revision, raw, item.digest))
        _sql(connection, deadline, "INSERT INTO current_records VALUES (?,?,?,?,?) ON CONFLICT(client_id) DO UPDATE SET revision=excluded.revision,record=excluded.record,digest=excluded.digest,commit_seq=excluded.commit_seq",
             (key, item.revision, raw, item.digest, seq))
    for table, values_set in (("active_projection", active), ("unresolved_projection", unresolved)):
        _sql(connection, deadline, f"DELETE FROM {table}")
        for key in sorted(values_set):
            _sql(connection, deadline, f"INSERT INTO {table} VALUES (?)", (key,))
    for identifier, owner in sorted(reserved - (set(old.reserved_owners) if old is not None else set())):
        _sql(connection, deadline, "INSERT INTO reserved_ids VALUES (?,?)", (identifier, owner))
    _sql(connection, deadline, "INSERT INTO store_state VALUES (1,?,?,?,?,?,?,?) ON CONFLICT(singleton) DO UPDATE SET revision=excluded.revision,metadata=excluded.metadata,head=excluded.head,state_digest=excluded.state_digest,projection_digest=excluded.projection_digest",
         (database_id, str(logical_path), seq, _canonical(metadata), head, state_hash, projections_hash))


def create_indexed_store(path: Path, payload: object, *, logical_path: Path, rules: IndexedIntentRules,
                         expected_binding: Mapping[str, str], deadline: float,
                         backend_id: str | None = None) -> IndexedIntentSnapshot:
    """Create an unpublished store exclusively; caller controls manifest activation."""
    path, logical_path = _path(path), _path(logical_path)
    deadline = _deadline(deadline, logical_path)
    detached = _validate(payload, rules, expected_binding)
    database_id = str(uuid4()) if backend_id is None else backend_id
    try:
        if str(UUID(database_id)) != database_id:
            raise _fail("backend identity is invalid")
    except (ValueError, TypeError, AttributeError) as exc:
        raise _fail("backend identity is invalid") from exc
    descriptor = os.open(path, os.O_RDWR | os.O_CREAT | os.O_EXCL | getattr(os, "O_NOFOLLOW", 0), 0o600)
    identity = os.fstat(descriptor).st_dev, os.fstat(descriptor).st_ino
    os.close(descriptor)
    success = False
    try:
        with _connection(path, logical_path, deadline) as connection:
            _sql(connection, deadline, "BEGIN IMMEDIATE")
            _sql(connection, deadline, f"PRAGMA application_id={_APPLICATION_ID}")
            _sql(connection, deadline, f"PRAGMA user_version={_SCHEMA_VERSION}")
            for query in _DDL.values():
                _sql(connection, deadline, query)
            _append(connection, deadline, database_id, logical_path, detached, rules, None)
            snapshot = _verified(connection, path, logical_path, deadline, rules, expected_binding)
            _sql(connection, deadline, "COMMIT")
        _sync_directory(path.parent)
        success = True
        return snapshot
    finally:
        if not success and path.exists() and _identity(path) == identity:
            path.unlink()


def _read_indexed_snapshot_in_transaction(
    connection: sqlite3.Connection, path: Path, *, logical_path: Path,
    rules: IndexedIntentRules, expected_binding: Mapping[str, str] | None, deadline: float,
    expected_store_id: str | None = None, expected_backend_id: str | None = None,
) -> IndexedIntentSnapshot:
    """Complete read core for an already guarded connection and transaction."""
    _deadline(deadline, logical_path)
    if not connection.in_transaction:
        raise _fail("complete read requires its guarded transaction")
    snapshot = _verified(connection, path, logical_path, deadline, rules, expected_binding)
    if ((expected_store_id is not None and snapshot.receipt.store_id != expected_store_id)
            or (expected_backend_id is not None and snapshot.receipt.database_id != expected_backend_id)):
        raise _fail("store identity changed")
    return snapshot


def read_indexed_snapshot(path: Path, *, logical_path: Path, rules: IndexedIntentRules,
                          expected_binding: Mapping[str, str] | None, deadline: float,
                          expected_store_id: str | None = None, expected_backend_id: str | None = None
                          ) -> IndexedIntentSnapshot:
    path, logical_path = _path(path), _path(logical_path)
    with _connection(path, logical_path, deadline) as connection:
        _sql(connection, deadline, "BEGIN")
        snapshot = _read_indexed_snapshot_in_transaction(
            connection, path, logical_path=logical_path, rules=rules,
            expected_binding=expected_binding, deadline=deadline,
            expected_store_id=expected_store_id, expected_backend_id=expected_backend_id,
        )
        _sql(connection, deadline, "COMMIT")
    return snapshot


def _replace_indexed_snapshot_in_transaction(
    connection: sqlite3.Connection, path: Path, detached: dict[str, object], *,
    expected: IndexedIntentSnapshot, rules: IndexedIntentRules,
    expected_binding: Mapping[str, str], deadline: float,
    expected_new_binding: Mapping[str, str] | None = None,
) -> IndexedIntentSnapshot:
    """Whole-snapshot CAS core; caller validates payload before its transaction."""
    _deadline(deadline, expected.receipt.logical_path)
    if not connection.in_transaction:
        raise _fail("complete write requires its guarded transaction")
    if path != expected.receipt.path:
        raise _fail("source path changed")
    observed = _verified(connection, path, expected.receipt.logical_path, deadline, rules, expected_binding)
    if observed.receipt != expected.receipt or observed._payload_json != expected._payload_json:
        raise _fail("compare-and-swap source changed")
    if detached.get("binding") != observed.payload.get("binding") and expected_new_binding is None:
        raise _fail("binding transition requires explicit new binding authority")
    if _canonical(detached) == observed._payload_json:
        return observed
    _append(connection, deadline, observed.receipt.database_id, observed.receipt.logical_path, detached, rules, observed)
    return _verified(connection, path, observed.receipt.logical_path, deadline, rules,
                     expected_new_binding or expected_binding)


def replace_indexed_snapshot(path: Path, payload: object, *, expected: IndexedIntentSnapshot,
                             rules: IndexedIntentRules, expected_binding: Mapping[str, str], deadline: float,
                             expected_new_binding: Mapping[str, str] | None = None) -> IndexedIntentSnapshot:
    """Whole-read CAS for legacy-shaped writers; never delete rows/history/reservations."""
    path = _path(path)
    if path != expected.receipt.path:
        raise _fail("source path changed")
    detached = _validate(payload, rules, expected_new_binding or expected_binding)
    with _connection(path, expected.receipt.logical_path, deadline) as connection:
        _sql(connection, deadline, "BEGIN IMMEDIATE")
        result = _replace_indexed_snapshot_in_transaction(
            connection, path, detached, expected=expected, rules=rules,
            expected_binding=expected_binding, deadline=deadline,
            expected_new_binding=expected_new_binding,
        )
        _sql(connection, deadline, "COMMIT")
    return result


def compare_and_swap_indexed_records(path: Path, replacements: Mapping[str, Mapping[str, object]], *,
                                     expected: IndexedIntentSnapshot,
                                     expected_records: Mapping[str, IndexedRecordReceipt | None],
                                     rules: IndexedIntentRules, expected_binding: Mapping[str, str],
                                     deadline: float) -> IndexedIntentSnapshot:
    """Atomic inserts/updates; None explicitly requires the record to be absent."""
    if not replacements or set(replacements) != set(expected_records):
        raise _fail("record CAS set is invalid")
    payload = expected.payload
    intents = cast(dict[str, dict[str, object]], payload["intents"])
    for key, record in replacements.items():
        if expected.record_receipt(key) != expected_records[key]:
            raise _fail("record CAS receipt changed")
        intents[key] = _decode(_canonical(dict(record)))
    return replace_indexed_snapshot(path, payload, expected=expected, rules=rules,
                                    expected_binding=expected_binding, deadline=deadline)


def compare_and_swap_indexed_metadata(path: Path, metadata: Mapping[str, object], *,
                                      expected: IndexedIntentSnapshot, rules: IndexedIntentRules,
                                      expected_binding: Mapping[str, str], deadline: float,
                                      expected_new_binding: Mapping[str, str] | None = None) -> IndexedIntentSnapshot:
    if "intents" in metadata:
        raise _fail("metadata cannot contain records")
    payload = {**dict(metadata), "intents": expected.payload["intents"]}
    return replace_indexed_snapshot(path, payload, expected=expected, rules=rules,
                                    expected_binding=expected_binding, deadline=deadline,
                                    expected_new_binding=expected_new_binding)
