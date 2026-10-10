"""Protected publication protocol; callers separately prove account/ledger authority.

Private writers require genuine held owner or signed administration, the complete
same-store ledger and both inventory/intent locks. Namespace metadata alone grants
no authorship. This module proves an independent Windows protected path checkpoint,
not exchange holdings, protected-store rollback or same-user compromise resistance.
"""
from __future__ import annotations

import hashlib
import json
import os
import stat
import sys
import tempfile
import time
import threading
from collections.abc import Callable, Iterator, Mapping
from contextlib import contextmanager
from contextvars import ContextVar
from dataclasses import dataclass
from pathlib import Path
from typing import Any, BinaryIO, Literal

from app.security import credential_store
from app.settings.live_safety import LiveTradingSafetyError
from .order_intent_store import _logical_lock_path, _sync_directory, current_ledger_deadline, write_ledger
from .spot_indexed_file_identity import _change_time
from .spot_inventory_namespace import (
    ACCOUNT_NAMESPACE_KEY, is_strictly_empty_live_snapshot, require_namespace, validate_namespace,
)

_ORIGIN_PID = os.getpid()
_SCOPE = "spot-inventory-checkpoint-v1"
_LIMIT = 2560


@dataclass
class _Authority:
    guard: Callable[[], None]
    pid: int
    thread: int
    active: bool = True


_AUTHORITY: ContextVar[_Authority | None] = ContextVar("spot_inventory_checkpoint_authority", default=None)
_EXPECTED_AUTHORITY = threading.local()


def _assert_authority() -> None:
    value: _Authority | None = _AUTHORITY.get()
    expected: object = getattr(_EXPECTED_AUTHORITY, "token", None)
    if value is None:
        if expected is None:
            return
        raise LiveTradingSafetyError("Inventory checkpoint original publication authority is unavailable.")
    if (expected is not value or not value.active
            or value.pid != os.getpid() or value.thread != threading.get_ident()):
        raise LiveTradingSafetyError("Inventory checkpoint original publication authority is unavailable.")
    value.guard()
    current: _Authority | None = _AUTHORITY.get()
    current_expected: object = getattr(_EXPECTED_AUTHORITY, "token", None)
    if (current is not value or current_expected is not value
            or not value.active or value.pid != os.getpid() or value.thread != threading.get_ident()):
        raise LiveTradingSafetyError("Inventory checkpoint publication authority changed during its guard.")


@contextmanager
def _checkpoint_authority(guard: Callable[[], None]) -> Iterator[None]:
    """Retain a pure caller-owned pin guard; this private scope grants no authorship.

    The caller holds genuine owner/admin lifetime and paired storage exclusion.
    The callback may check the original full record under already held locks;
    it must not recurse into this core or acquire additional storage locks.
    """
    previous = getattr(_EXPECTED_AUTHORITY, "token", None)
    if os.getpid() != _ORIGIN_PID or not callable(guard) or _AUTHORITY.get() is not None or previous is not None:
        raise LiveTradingSafetyError("Inventory checkpoint authority scope is invalid.")
    value = _Authority(guard, os.getpid(), threading.get_ident())
    token = _AUTHORITY.set(value)
    _EXPECTED_AUTHORITY.token = value
    try:
        _assert_authority()
        yield
        _assert_authority()
    finally:
        value.active = False
        try:
            _AUTHORITY.reset(token)
        finally:
            _EXPECTED_AUTHORITY.token = previous


def _hash(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def _source(path: Path) -> str:
    return os.path.normcase(str(path))


def _guard(path: Path, deadline: float) -> None:
    if os.getpid() != _ORIGIN_PID:
        raise LiveTradingSafetyError("Inherited inventory checkpoint authority is unavailable.")
    if current_ledger_deadline(path) != deadline or time.monotonic() >= deadline:
        raise LiveTradingSafetyError("Inventory checkpoint transaction deadline expired.")
    _assert_authority()
    if current_ledger_deadline(path) != deadline or time.monotonic() >= deadline:
        raise LiveTradingSafetyError("Inventory checkpoint transaction deadline expired after authority validation.")


def _context(path: Path, *, require_backend: bool = True) -> tuple[Path, float]:
    if os.getpid() != _ORIGIN_PID:
        raise LiveTradingSafetyError("Inherited inventory checkpoint authority is unavailable.")
    path = _logical_lock_path(Path(path))
    deadline = current_ledger_deadline(path)
    _guard(path, deadline)
    if require_backend:
        _require_backend(path, deadline)
    return path, deadline


def _require_backend(path: Path, deadline: float) -> None:
    _guard(path, deadline)
    if not _windows_read_adapter() or credential_store.credential_store_backend() != "windows-credential-manager":
        raise LiveTradingSafetyError("Inventory checkpoint requires Windows Credential Manager.")
    _guard(path, deadline)


def _windows_read_adapter() -> bool:
    return sys.platform == "win32"


@contextmanager
def _errors():
    try:
        yield
    except LiveTradingSafetyError:
        raise
    except (OSError, ValueError, TypeError, RuntimeError, OverflowError, RecursionError) as exc:
        raise LiveTradingSafetyError("Protected inventory publication failed; reconciliation is required.") from exc


def _cleanup(action: Callable[[], object], primary: BaseException | None) -> None:
    """Attempt cleanup once while retaining this scope's cancellation and causes."""
    try:
        action()
    except BaseException as cleanup:
        if primary is None or cleanup is primary:
            raise
        if isinstance(cleanup, (KeyboardInterrupt, SystemExit)) and not isinstance(primary, (KeyboardInterrupt, SystemExit)):
            raise cleanup from primary
        cleanup.__context__ = None
        if primary.__cause__ is not None and primary.__cause__ is not cleanup:
            cleanup.__cause__ = primary.__cause__
        raise primary from cleanup


@contextmanager
def _binary_handle(fd: int, mode: Literal["rb", "wb"]) -> Iterator[BinaryIO]:
    try:
        handle = os.fdopen(fd, mode)
    except BaseException as exc:
        _cleanup(lambda: os.close(fd), exc)
        raise
    primary: BaseException | None = None
    try:
        yield handle
    except BaseException as exc:
        primary = exc
        raise
    finally:
        _cleanup(handle.close, primary)


def _unique(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("Duplicate inventory checkpoint field")
        result[key] = value
    return result


def _invalid(value):
    raise ValueError("Nonfinite inventory checkpoint value")


def _decode(raw: bytes) -> dict[str, Any]:
    value = json.loads(raw.decode("utf-8"), object_pairs_hook=_unique, parse_constant=_invalid)
    if not isinstance(value, dict):
        raise ValueError("Inventory checkpoint object required")
    json.dumps(value, allow_nan=False)
    return value


def _encode(candidate: Mapping[str, object]) -> bytes:
    raw = (json.dumps(candidate, sort_keys=True, indent=2, allow_nan=False) + "\n").encode("utf-8")
    if _decode(raw) != candidate:
        raise ValueError("Inventory JSON keys must be strings")
    return raw


def _snapshot(raw: bytes | None, snapshot: object) -> dict[str, Any] | None:
    if raw is None:
        if snapshot is not None:
            raise ValueError("Absent inventory has a nonempty receipt")
        return None
    if type(raw) is not bytes:
        raise ValueError("Inventory receipt bytes required")
    decoded = _decode(raw)
    if decoded != snapshot:
        raise ValueError("Inventory receipt does not match its snapshot")
    if (type(decoded.get("version")) is not int or decoded["version"] != 1
            or type(decoded.get("mode")) is not str or not decoded["mode"]
            or not isinstance(decoded.get("entry_allocations"), dict)
            or not isinstance(decoded.get("open_position_records"), dict)):
        raise ValueError("Inventory snapshot required")
    return decoded


def _identity(info):
    if (not stat.S_ISREG(info.st_mode) or info.st_nlink != 1
            or getattr(info, "st_file_attributes", 0) & getattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT", 1024)):
        raise ValueError("Inventory checkpoint file must be a unique regular file")
    # Windows path/fd ctime APIs disagree after rename. Require native handle
    # ChangeTime separately below; never use a creation clock as that proof.
    epoch = None if sys.platform == "win32" else info.st_ctime_ns
    return info.st_dev, info.st_ino, info.st_size, info.st_mtime_ns, epoch


def _read(path: Path, deadline: float, *, missing: bool = False) -> bytes | None:
    # Journal I/O uses the original logical source's deadline, passed by callers.
    if os.getpid() != _ORIGIN_PID:
        raise LiveTradingSafetyError("Inherited inventory checkpoint authority is unavailable.")
    _assert_authority()
    if time.monotonic() >= deadline:
        raise LiveTradingSafetyError("Inventory checkpoint transaction deadline expired.")
    if path.is_symlink():
        raise ValueError("Inventory checkpoint file must not be a symbolic link")
    try:
        before = _identity(path.lstat())
        fd = os.open(path, os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0) | getattr(os, "O_BINARY", 0))
    except FileNotFoundError:
        if missing:
            return None
        raise
    with _binary_handle(fd, "rb") as handle:
        opened_stat = os.fstat(handle.fileno())
        opened = _identity(opened_stat)
        opened_change = _change_time(handle.fileno())
        raw = handle.read()
        after_stat = os.fstat(handle.fileno())
        after = _identity(after_stat)
        after_change = _change_time(handle.fileno())
    check_fd = os.open(path, os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0) | getattr(os, "O_BINARY", 0))
    primary: BaseException | None = None
    try:
        current_stat = os.fstat(check_fd)
        current_change = _change_time(check_fd)
    except BaseException as exc:
        primary = exc
        raise
    finally:
        _cleanup(lambda: os.close(check_fd), primary)
    if (before != opened or opened != after or after != _identity(current_stat)
            or after != _identity(path.lstat())
            or opened_change != after_change or after_change != current_change):
        raise ValueError("Inventory checkpoint file changed while reading")
    _assert_authority()
    if time.monotonic() >= deadline:
        raise LiveTradingSafetyError("Inventory checkpoint transaction deadline expired.")
    return raw


def _get(path: Path, deadline: float) -> str:
    _guard(path, deadline)
    value = credential_store.get_secret(scope=_SCOPE, account=_hash(_source(path).encode("utf-8")))
    _guard(path, deadline)
    if type(value) is not str or len(value.encode("utf-8")) > _LIMIT:
        raise ValueError("Protected inventory checkpoint value is invalid")
    return value


def _compact(record: dict[str, Any]) -> str:
    value = json.dumps(record, sort_keys=True, separators=(",", ":"), allow_nan=False)
    if len(value.encode("utf-8")) > _LIMIT:
        raise ValueError("Protected inventory checkpoint exceeds its size limit")
    return value


def _digest(value: object, *, absent: bool = False) -> None:
    if absent and value is None:
        return
    if type(value) is not str or len(value) != 64 or any(c not in "0123456789abcdef" for c in value):
        raise ValueError("Inventory checkpoint digest is invalid")


def _head(value: object, *, previous: bool = False) -> None:
    if not isinstance(value, dict) or set(value) != {"revision", "digest"}:
        raise ValueError("Inventory checkpoint head is invalid")
    revision = value["revision"]
    if type(revision) is not int or revision < (0 if previous else 1):
        raise ValueError("Inventory checkpoint revision is invalid")
    _digest(value["digest"], absent=previous and revision == 0)


def _journal(path: Path, record: dict[str, Any]) -> Path:
    target = record["target"]
    name = f".spot-inventory-{_hash(_source(path).encode('utf-8'))[:16]}-{target['revision']}-{target['digest']}-{record['operation_hash'][:16]}.json"
    return path.parent / name


def _record(path: Path, value: str) -> dict[str, Any]:
    record = _decode(value.encode("utf-8"))
    state = record.get("state")
    common = {"version", "state", "namespace", "source"}
    fields = common | ({"head"} if state == "stable" else {"previous", "target", "operation_hash", "journal"})
    if (set(record) != fields or type(record.get("version")) is not int or record["version"] != 1
            or state not in {"stable", "pending"} or record["source"] != _source(path)
            or _compact(record) != value):
        raise ValueError("Protected inventory checkpoint is malformed")
    validate_namespace(record["namespace"])
    if state == "stable":
        _head(record["head"])
    else:
        _head(record["previous"], previous=True)
        _head(record["target"])
        _digest(record["operation_hash"])
        if (record["target"]["revision"] != record["previous"]["revision"] + 1
                or record["journal"] != _journal(path, record).name):
            raise ValueError("Pending inventory checkpoint transition is invalid")
    return record


def _put(path: Path, deadline: float, record: dict[str, Any], *, expected: str) -> str:
    value = _compact(record)
    _record(path, value)
    if _get(path, deadline) != expected:
        raise ValueError("Protected inventory checkpoint changed before publication")
    _guard(path, deadline)
    credential_store.put_secret(scope=_SCOPE, account=_hash(_source(path).encode("utf-8")), value=value)
    _guard(path, deadline)
    if _get(path, deadline) != value:
        raise ValueError("Protected inventory checkpoint readback does not match publication")
    return value


def _assert_source(path: Path, deadline: float, raw: bytes | None) -> None:
    _guard(path, deadline)
    if _read(path, deadline, missing=True) != raw:
        raise ValueError("Inventory source changed from its original receipt")
    _guard(path, deadline)


def _stable(path: Path, record: dict[str, Any], raw: bytes | None, snapshot: object, expected: object = None) -> None:
    if record["state"] != "stable":
        raise LiveTradingSafetyError("Inventory publication is pending; explicit recovery is required.")
    checked = _snapshot(raw, snapshot)
    require_namespace(checked, record["namespace"])
    if expected is not None and validate_namespace(expected) != record["namespace"]:
        raise ValueError("Inventory checkpoint belongs to another account or intent store")
    if raw is None or _hash(raw) != record["head"]["digest"]:
        raise ValueError("Inventory source does not match its protected checkpoint")


def verify_inventory_checkpoint(path: Path, raw: bytes | None, snapshot: object, expected_namespace: object = None) -> bool:
    """Inspect the protected path slot before Windows missing/unbound decisions.

    On other platforms False permits only ordinary unbound legacy inspection,
    without protected authority. Any owned expected namespace is unsupported.
    """
    with _errors():
        path, deadline = _context(path, require_backend=False)
        if not _windows_read_adapter():
            checked = _snapshot(raw, snapshot)
            _assert_source(path, deadline, raw)
            if expected_namespace is not None or checked is not None and ACCOUNT_NAMESPACE_KEY in checked:
                raise LiveTradingSafetyError("Protected Spot inventory reads require Windows Credential Manager.")
            return False
        _require_backend(path, deadline)
        value = _get(path, deadline)
        checked = _snapshot(raw, snapshot)
        _assert_source(path, deadline, raw)
        if not value:
            if checked is not None and ACCOUNT_NAMESPACE_KEY in checked:
                raise ValueError("Bound inventory has no protected checkpoint")
            if expected_namespace is not None:
                validate_namespace(expected_namespace)
            return False
        _stable(path, _record(path, value), raw, checked, expected_namespace)
        if _get(path, deadline) != value:
            raise ValueError("Protected inventory checkpoint changed while verifying")
        return True


def _write_journal(path: Path, deadline: float, journal: Path, raw: bytes) -> None:
    _guard(path, deadline)
    if journal.exists() or journal.is_symlink():
        if _read(journal, deadline) != raw:
            raise ValueError("Inventory candidate journal conflicts with publication")
        return
    fd, name = tempfile.mkstemp(prefix=".inventory-candidate-", suffix=".tmp", dir=path.parent)
    temp = Path(name)
    primary: BaseException | None = None
    try:
        with _binary_handle(fd, "wb") as handle:
            handle.write(raw)
            handle.flush()
            os.fsync(handle.fileno())
        _guard(path, deadline)
        if sys.platform == "win32":
            import ctypes
            from ctypes import wintypes
            move = ctypes.WinDLL("kernel32", use_last_error=True).MoveFileExW
            move.argtypes = (wintypes.LPCWSTR, wintypes.LPCWSTR, wintypes.DWORD)
            move.restype = wintypes.BOOL
            if not move(str(temp), str(journal), 0x8):  # Write-through; never replace an existing journal.
                raise ctypes.WinError(ctypes.get_last_error())
        else:
            os.link(temp, journal)
            temp.unlink()
            _sync_directory(journal.parent)
        _guard(path, deadline)
        if _read(journal, deadline) != raw:
            raise ValueError("Inventory candidate journal changed after publication")
    except BaseException as exc:
        primary = exc
        raise
    finally:
        _cleanup(lambda: temp.unlink(missing_ok=True), primary)


def _finish(path: Path, deadline: float, pending: dict[str, Any], protected: str, target: bytes) -> bool:
    journal = _journal(path, pending)
    if _get(path, deadline) != protected or _read(journal, deadline) != target:
        raise ValueError("Pending inventory publication authority changed")
    current = _read(path, deadline, missing=True)
    digest = _hash(current) if current is not None else None
    if digest not in {pending["previous"]["digest"], pending["target"]["digest"]}:
        raise ValueError("Inventory publication source is neither its original nor target")
    candidate = _snapshot(target, _decode(target))
    assert candidate is not None
    require_namespace(candidate, pending["namespace"])
    if _hash(target) != pending["target"]["digest"]:
        raise ValueError("Inventory candidate journal digest changed")
    if current != target:
        _guard(path, deadline)
        write_ledger(path, candidate)
        _guard(path, deadline)
    _assert_source(path, deadline, target)
    stable = {"version": 1, "state": "stable", "namespace": pending["namespace"],
              "source": _source(path), "head": pending["target"]}
    stable_value = _put(path, deadline, stable, expected=protected)
    _assert_source(path, deadline, target)
    if _get(path, deadline) != stable_value:
        raise ValueError("Protected inventory checkpoint changed after finalization")
    if _read(journal, deadline) != target:
        raise ValueError("Committed inventory candidate journal changed before cleanup")
    _guard(path, deadline)
    journal.unlink()
    _sync_directory(journal.parent)
    _guard(path, deadline)
    return True


def _operation(operation_id: str) -> str:
    if type(operation_id) is not str or not operation_id or len(operation_id.encode("utf-8")) > 1024:
        raise ValueError("Inventory publication operation identity is invalid")
    return _hash(operation_id.encode("utf-8"))


def _publish(path: Path, raw_before: bytes | None, snapshot_before: object,
             candidate: Mapping[str, object], namespace: object, operation_id: str, *, bootstrap: bool) -> bool:
    path, deadline = _context(path)
    namespace = validate_namespace(namespace)
    operation = _operation(operation_id)
    before = _snapshot(raw_before, snapshot_before)
    target = _encode(candidate)
    detached = _snapshot(target, _decode(target))
    require_namespace(detached, namespace)
    protected = _get(path, deadline)
    if bootstrap:
        if (protected or before is not None and ACCOUNT_NAMESPACE_KEY in before
                or not is_strictly_empty_live_snapshot(before)
                or not is_strictly_empty_live_snapshot(detached)):
            raise ValueError("Inventory bootstrap requires missing authority and genuinely unbound empty state")
        previous: dict[str, Any] = {"revision": 0, "digest": _hash(raw_before) if raw_before is not None else None}
    else:
        if not protected:
            raise ValueError("Inventory publication requires its existing protected checkpoint")
        old = _record(path, protected)
        _stable(path, old, raw_before, before, namespace)
        previous = old["head"]
    _assert_source(path, deadline, raw_before)
    pending = {"version": 1, "state": "pending", "namespace": namespace, "source": _source(path),
               "previous": previous, "target": {"revision": previous["revision"] + 1, "digest": _hash(target)},
               "operation_hash": operation}
    pending["journal"] = _journal(path, pending).name
    _compact(pending)
    _write_journal(path, deadline, _journal(path, pending), target)
    _assert_source(path, deadline, raw_before)
    protected = _put(path, deadline, pending, expected=protected)
    _assert_source(path, deadline, raw_before)
    return _finish(path, deadline, pending, protected, target)


def _bootstrap_inventory_checkpoint(path: Path, raw_before: bytes | None, snapshot_before: object,
                                    candidate: Mapping[str, object], namespace: object, operation_id: str) -> bool:
    """Caller additionally proves genuinely empty complete ledger under both locks."""
    with _errors():
        return _publish(path, raw_before, snapshot_before, candidate, namespace, operation_id, bootstrap=True)


def _publish_inventory_checkpoint(path: Path, raw_before: bytes | None, snapshot_before: object,
                                  candidate: Mapping[str, object], namespace: object, operation_id: str) -> bool:
    """Caller pins genuine same-account/full-record publication authority under both locks."""
    with _errors():
        return _publish(path, raw_before, snapshot_before, candidate, namespace, operation_id, bootstrap=False)


def _recover_inventory_checkpoint(path: Path, namespace: object, operation_id: str) -> bool:
    """Only the exact authored operation can advance pending old/new bytes to its target."""
    with _errors():
        path, deadline = _context(path)
        namespace = validate_namespace(namespace)
        protected = _get(path, deadline)
        if not protected:
            raise ValueError("Inventory recovery has no protected checkpoint")
        record = _record(path, protected)
        raw = _read(path, deadline, missing=True)
        snapshot = _decode(raw) if raw is not None else None
        if record["state"] == "stable":
            _stable(path, record, raw, snapshot, namespace)
            if _get(path, deadline) != protected:
                raise ValueError("Protected inventory checkpoint changed during recovery")
            return False
        if record["namespace"] != namespace or record["operation_hash"] != _operation(operation_id):
            raise ValueError("Pending inventory recovery belongs to another namespace or operation")
        target = _read(_journal(path, record), deadline)
        assert target is not None
        return _finish(path, deadline, record, protected, target)
