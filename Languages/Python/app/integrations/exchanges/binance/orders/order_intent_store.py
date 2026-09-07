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
from pathlib import Path

from app.security.redaction import redact_text
from app.settings.live_safety import LiveTradingSafetyError

_THREAD_LOCK = threading.Lock()
LOCK_TIMEOUT_SECONDS = 5.0


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


@contextmanager
def ledger_transaction(path: Path) -> Iterator[None]:
    deadline = time.monotonic() + LOCK_TIMEOUT_SECONDS
    if not _THREAD_LOCK.acquire(timeout=LOCK_TIMEOUT_SECONDS):
        raise LiveTradingSafetyError("Order intent ledger is busy; submission is blocked.")
    try:
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
                yield
            finally:
                _unlock(fd)
        finally:
            os.close(fd)
    except (OSError, ValueError, TypeError) as exc:
        raise LiveTradingSafetyError(f"Order intent storage failed; submission is blocked: {redact_text(exc)}") from exc
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


def write_ledger(path: Path, payload: Mapping[str, object]) -> None:
    """Publish only flushed data; callers must hold ledger_transaction throughout."""
    serialized = json.dumps(payload, sort_keys=True, indent=2, allow_nan=False) + "\n"
    fd, name = tempfile.mkstemp(prefix=f".{path.name}.", suffix=".tmp", dir=path.parent)
    temp_path = Path(name)
    try:
        with os.fdopen(fd, "w", encoding="utf-8", newline="\n") as handle:
            handle.write(serialized)
            handle.flush()
            os.fsync(handle.fileno())
        _publish(temp_path, path)
    finally:
        temp_path.unlink(missing_ok=True)
