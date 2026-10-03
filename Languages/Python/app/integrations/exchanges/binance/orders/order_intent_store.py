"""Local-filesystem transactions for the exchange order-intent ledger."""
from __future__ import annotations

import errno
import json
import os
import stat
import sys
import tempfile
import threading
import time
from collections.abc import Iterator, Mapping
from contextlib import contextmanager
from contextvars import ContextVar
from pathlib import Path

from app.security.redaction import redact_text
from app.settings.live_safety import LiveTradingSafetyError

_THREAD_LOCK = threading.Lock()
LOCK_TIMEOUT_SECONDS = 5.0


class _LedgerTransactionToken:
    """Shared lifetime prevents copied contexts from retaining released lock authority."""

    def __init__(self, deadline: float) -> None:
        self.deadline = deadline
        self.owner_thread = threading.current_thread()
        self.owner_pid = os.getpid()
        self.held_paths: frozenset[Path] = frozenset()
        self.active = False


_ACTIVE_LEDGER_TRANSACTION: ContextVar[_LedgerTransactionToken | None] = ContextVar(
    "order_intent_ledger_transaction", default=None
)


def _logical_lock_path(path: Path) -> Path:
    # Normalize parent aliases (including Windows short paths), preserving the
    # logical final basename even when that file itself is a symbolic link.
    absolute = Path(os.path.abspath(path))
    return absolute.parent.resolve() / absolute.name


def current_ledger_deadline(*required_paths: Path) -> float:
    """Return the original deadline only while this thread holds the required locks."""
    transaction = _ACTIVE_LEDGER_TRANSACTION.get()
    if (
        transaction is None
        or not transaction.active
        or transaction.owner_thread is not threading.current_thread()
        or transaction.owner_pid != os.getpid()
    ):
        raise LiveTradingSafetyError("An order intent transaction is required for this storage operation.")
    if any(_logical_lock_path(path) not in transaction.held_paths for path in required_paths):
        raise LiveTradingSafetyError("The required order intent ledger lock is not held for this storage operation.")
    return transaction.deadline


def _try_lock(fd: int) -> None:
    if sys.platform == "win32":
        import msvcrt

        os.lseek(fd, 0, os.SEEK_SET)
        msvcrt.locking(fd, msvcrt.LK_NBLCK, 1)
    else:
        import fcntl

        fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)


def _unlock(fd: int) -> None:
    if sys.platform == "win32":
        import msvcrt

        os.lseek(fd, 0, os.SEEK_SET)
        msvcrt.locking(fd, msvcrt.LK_UNLCK, 1)
    else:
        import fcntl

        fcntl.flock(fd, fcntl.LOCK_UN)


def _sync_directory(path: Path) -> None:
    if sys.platform != "win32":
        fd = os.open(path, os.O_RDONLY | getattr(os, "O_DIRECTORY", 0))
        try:
            os.fsync(fd)
        finally:
            os.close(fd)


def _ensure_parent(path: Path) -> None:
    missing = []
    parent = path.parent
    while not parent.exists():
        missing.append(parent)
        parent = parent.parent
    for directory in reversed(missing):
        directory.mkdir(mode=0o700, exist_ok=True)
        _sync_directory(directory.parent)


def _already_held_transaction(*paths: Path) -> bool:
    """Borrow only this thread's actual live locks, without expanding paths or deadlines."""
    transaction = _ACTIVE_LEDGER_TRANSACTION.get()
    return bool(transaction is not None and transaction.active
                and transaction.owner_thread is threading.current_thread()
                and transaction.owner_pid == os.getpid()
                and all(_logical_lock_path(path) in transaction.held_paths for path in paths))


@contextmanager
def ledger_transaction(path: Path) -> Iterator[None]:
    if _already_held_transaction(path):
        yield
        return
    deadline = time.monotonic() + LOCK_TIMEOUT_SECONDS
    if not _THREAD_LOCK.acquire(timeout=LOCK_TIMEOUT_SECONDS):
        raise LiveTradingSafetyError("Order intent ledger is busy; submission is blocked.")
    transaction = _LedgerTransactionToken(deadline)
    context_token = _ACTIVE_LEDGER_TRANSACTION.set(transaction)
    try:
        path = _logical_lock_path(path)
        _ensure_parent(path)
        # Never unlink this file: replacing its inode can create independent locks.
        lock_path = path.with_name(f".{path.name}.lock")
        fd = os.open(lock_path, os.O_RDWR | os.O_CREAT | getattr(os, "O_NOFOLLOW", 0), 0o600)
        try:
            if not stat.S_ISREG(os.fstat(fd).st_mode):
                raise LiveTradingSafetyError("Order intent lock must be a regular file.")
            while True:
                try:
                    _try_lock(fd)
                    break
                except OSError as exc:
                    if exc.errno not in (errno.EACCES, errno.EAGAIN):
                        raise
                    remaining = deadline - time.monotonic()
                    if remaining <= 0:
                        raise LiveTradingSafetyError("Order intent ledger is busy; submission is blocked.") from exc
                    time.sleep(min(0.025, remaining))
            try:
                transaction.held_paths = frozenset((path,))
                transaction.active = True
                yield
            finally:
                transaction.active = False
                # An inherited POSIX descriptor shares its parent's lock.
                if transaction.owner_pid == os.getpid():
                    _unlock(fd)
        finally:
            os.close(fd)
    except (OSError, ValueError, TypeError) as exc:
        raise LiveTradingSafetyError(f"Order intent storage failed; submission is blocked: {redact_text(exc)}") from exc
    finally:
        transaction.active = False
        try:
            _ACTIVE_LEDGER_TRANSACTION.reset(context_token)
        finally:
            _THREAD_LOCK.release()


@contextmanager
def ledger_transactions(*paths: Path) -> Iterator[None]:
    """Lock multiple ledgers in stable path order for atomic cross-ledger administration."""
    normalized_paths = sorted({_logical_lock_path(path) for path in paths}, key=os.fspath)
    if not normalized_paths:
        raise ValueError("At least one ledger path is required.")
    if _already_held_transaction(*normalized_paths):
        yield
        return
    deadline = time.monotonic() + LOCK_TIMEOUT_SECONDS
    if not _THREAD_LOCK.acquire(timeout=LOCK_TIMEOUT_SECONDS):
        raise LiveTradingSafetyError("Order intent ledger is busy; submission is blocked.")
    transaction = _LedgerTransactionToken(deadline)
    context_token = _ACTIVE_LEDGER_TRANSACTION.set(transaction)
    locked_fds: list[int] = []
    try:
        for path in normalized_paths:
            _ensure_parent(path)
            lock_path = path.with_name(f".{path.name}.lock")
            fd = os.open(lock_path, os.O_RDWR | os.O_CREAT | getattr(os, "O_NOFOLLOW", 0), 0o600)
            try:
                if not stat.S_ISREG(os.fstat(fd).st_mode):
                    raise LiveTradingSafetyError("Order intent lock must be a regular file.")
                while True:
                    try:
                        _try_lock(fd)
                        locked_fds.append(fd)
                        break
                    except OSError as exc:
                        if exc.errno not in (errno.EACCES, errno.EAGAIN):
                            raise
                        remaining = deadline - time.monotonic()
                        if remaining <= 0:
                            raise LiveTradingSafetyError("Order intent ledger is busy; submission is blocked.") from exc
                        time.sleep(min(0.025, remaining))
            except BaseException:
                if fd not in locked_fds:
                    os.close(fd)
                raise
        transaction.held_paths = frozenset(normalized_paths)
        transaction.active = True
        yield
    except (OSError, ValueError, TypeError) as exc:
        raise LiveTradingSafetyError(f"Order intent storage failed; submission is blocked: {redact_text(exc)}") from exc
    finally:
        transaction.active = False
        try:
            for fd in reversed(locked_fds):
                try:
                    if transaction.owner_pid == os.getpid():
                        _unlock(fd)
                finally:
                    os.close(fd)
        finally:
            try:
                _ACTIVE_LEDGER_TRANSACTION.reset(context_token)
            finally:
                _THREAD_LOCK.release()


def _publish(temp_path: Path, path: Path) -> None:
    if sys.platform == "win32":
        import ctypes
        from ctypes import wintypes

        move = ctypes.WinDLL("kernel32", use_last_error=True).MoveFileExW
        move.argtypes = (wintypes.LPCWSTR, wintypes.LPCWSTR, wintypes.DWORD)
        move.restype = wintypes.BOOL
        # Same-directory rename, replacing the old file, with write-through requested.
        if not move(str(temp_path), str(path), 0x1 | 0x8):
            raise ctypes.WinError(ctypes.get_last_error())
    else:
        os.replace(temp_path, path)
        _sync_directory(path.parent)



class IndexedLedgerWritePayload(dict[str, object]):
    """Inert dispatch marker; the indexed bridge supplies and verifies authority."""


class LegacyLedgerWritePayload(dict[str, object]):
    """Complete JSON read with its original source path and filesystem identity."""

    def __init__(self, value: dict[str, object], *, source_path: Path,
                 source_identity: tuple[int, int, int, int, int]) -> None:
        super().__init__(value)
        self._legacy_source = (_logical_lock_path(source_path), source_identity)

    @property
    def legacy_source(self) -> tuple[Path, tuple[int, int, int, int, int]]:
        return self._legacy_source


def indexed_migration_fence_path(path: Path) -> Path:
    """Immutable cutover receipt fences the logical namespace before any outputs."""
    return path.with_name(f"{path.name}.indexed-migration.json")


def indexed_namespace_exists(path: Path) -> bool:
    # lstat also sees a dangling symbolic link or malformed receipt. Presence is
    # sufficient to fence JSON writes; migration validates contents separately.
    try:
        indexed_migration_fence_path(path).lstat()
    except FileNotFoundError:
        # Use literal names, including logical filenames with glob metacharacters.
        # Losing a cutover receipt must not silently reset a surviving backend.
        try:
            return any(candidate.name.startswith(f"{path.name}.") and candidate.name.endswith(".sqlite3")
                       for candidate in path.parent.iterdir())
        except FileNotFoundError:
            return False
    else:
        return True


def ledger_file_identity(path: Path) -> tuple[int, int, int, int, int]:
    info = path.lstat()
    if not stat.S_ISREG(info.st_mode):
        raise LiveTradingSafetyError("Order intent JSON storage must be a regular file.")
    return info.st_dev, info.st_ino, info.st_size, info.st_mtime_ns, info.st_ctime_ns


def _assert_json_namespace(path: Path) -> None:
    if indexed_namespace_exists(path):
        raise LiveTradingSafetyError(
            "Indexed intent namespace requires its original verified read receipt; JSON replacement is blocked."
        )


def _strict_existing_json_source(path: Path) -> tuple[int, int, int, int, int] | None:
    _assert_json_namespace(path)
    try:
        identity = ledger_file_identity(path)
    except FileNotFoundError:
        return None

    def unique_object(pairs: list[tuple[str, object]]) -> dict[str, object]:
        result: dict[str, object] = {}
        for key, value in pairs:
            if key in result:
                raise ValueError("Duplicate JSON storage field")
            result[key] = value
        return result

    def invalid_constant(value: str) -> object:
        raise ValueError("Nonfinite JSON storage field")

    try:
        decoded = json.loads(path.read_text(encoding="utf-8"), object_pairs_hook=unique_object,
                             parse_constant=invalid_constant)
    except (ValueError, UnicodeError, TypeError, RecursionError) as exc:
        raise LiveTradingSafetyError("Existing JSON storage is malformed; replacement is blocked.") from exc
    if isinstance(decoded, dict) and decoded.get("format_version") == 3:
        raise LiveTradingSafetyError("Indexed intent manifest cannot be replaced by a JSON ledger.")
    _assert_json_source(path, identity)
    return identity


def _assert_json_source(path: Path, identity: tuple[int, int, int, int, int] | None) -> None:
    _assert_json_namespace(path)
    try:
        observed = ledger_file_identity(path)
    except FileNotFoundError:
        observed = None
    if observed != identity:
        raise LiveTradingSafetyError("Order intent JSON source changed before publication; replacement is blocked.")


def write_ledger(path: Path, payload: Mapping[str, object], *,
                 expected_new_binding: Mapping[str, str] | None = None) -> None:
    """Publish JSON or CAS indexed data using the original complete-read authority."""
    if isinstance(payload, IndexedLedgerWritePayload):
        # Keep ordinary JSON/isolated storage imports independent of SDKs and
        # package-relative imports. Only the typed bridge uses this branch.
        from .spot_indexed_intent_bridge import write_indexed_ledger
        write_indexed_ledger(path, payload, expected_new_binding=expected_new_binding)
        return
    if payload.get("format_version") == 3:
        raise LiveTradingSafetyError("Indexed intent manifests require explicit offline migration.")
    identity: tuple[int, int, int, int, int] | None
    if isinstance(payload, LegacyLedgerWritePayload):
        source_path, identity = payload.legacy_source
        if _logical_lock_path(path) != source_path:
            raise LiveTradingSafetyError("Order intent JSON read receipt belongs to a different target path.")
        _assert_json_source(path, identity)
    else:
        identity = _strict_existing_json_source(path)
    serialized = json.dumps(payload, sort_keys=True, indent=2, allow_nan=False) + "\n"
    fd, name = tempfile.mkstemp(prefix=f".{path.name}.", suffix=".tmp", dir=path.parent)
    temp_path = Path(name)
    try:
        with os.fdopen(fd, "w", encoding="utf-8", newline="\n") as handle:
            handle.write(serialized)
            handle.flush()
            os.fsync(handle.fileno())
        _assert_json_source(path, identity)
        _publish(temp_path, path)
    finally:
        temp_path.unlink(missing_ok=True)
