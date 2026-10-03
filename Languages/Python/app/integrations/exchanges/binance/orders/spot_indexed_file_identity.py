"""Change receipts for a warm indexed-store validation anchor.

These detect ordinary external file changes, including a restored mtime.
Windows receipts checkpoint the existing per-file USN journal before issuance.
They are consistency evidence, not authenticated storage or rollback authority.
"""
from __future__ import annotations

import os
import stat
import struct
import sys
from dataclasses import dataclass
from pathlib import Path

from app.settings.live_safety import LiveTradingSafetyError


def _fail() -> LiveTradingSafetyError:
    return LiveTradingSafetyError("Indexed database changed or cannot be identified; full verification is required.")


def _identity(value: os.stat_result) -> tuple[int, int, int, int, int]:
    return value.st_dev, value.st_ino, value.st_size, value.st_mtime_ns, value.st_ctime_ns


def _regular(value: os.stat_result) -> None:
    if (not stat.S_ISREG(value.st_mode) or value.st_nlink != 1
            or getattr(value, "st_file_attributes", 0) & getattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT", 0x400)):
        raise _fail()


def _windows_create_file(path: Path, access: int) -> tuple[int | None, int]:
    import ctypes
    from ctypes import wintypes

    create = ctypes.WinDLL("kernel32", use_last_error=True).CreateFileW
    create.argtypes = (wintypes.LPCWSTR, wintypes.DWORD, wintypes.DWORD, ctypes.c_void_p,
                       wintypes.DWORD, wintypes.DWORD, wintypes.HANDLE)
    create.restype = wintypes.HANDLE
    # Metadata-only handles must permit the continuously guarded SQLite handle.
    handle = create(str(path), access, 7, None, 3, 0x200000, None)
    error = ctypes.get_last_error()
    if handle is None or handle == ctypes.c_void_p(-1).value:
        return None, error
    return int(handle), 0


def _windows_close_file(handle: int) -> None:
    import ctypes
    from ctypes import wintypes

    close = ctypes.WinDLL("kernel32", use_last_error=True).CloseHandle
    close.argtypes = (wintypes.HANDLE,)
    close.restype = wintypes.BOOL
    if not close(handle):
        raise _fail()


def _open_metadata_descriptor(path: Path) -> int:
    if sys.platform != "win32":
        return os.open(path, os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0) | getattr(os, "O_BINARY", 0))
    import msvcrt

    handle, _ = _windows_create_file(path, 0)
    if handle is None:
        raise _fail()
    try:
        return msvcrt.open_osfhandle(handle, os.O_RDONLY | os.O_BINARY)
    except OSError as exc:
        _windows_close_file(handle)
        raise _fail() from exc


def assert_indexed_native_guard(path: Path) -> None:
    """Require actual Windows denial of foreign read, write and delete handles.

    SQLite's Windows exclusive=1 URI option holds share mode zero continuously.
    Probe the native behavior rather than trusting an ignored URI or custom VFS.
    Each unexpected successful handle is closed without reading or changing data.
    A pre-existing file mapping also prevents acquisition of this native guard.
    """
    if sys.platform != "win32":
        raise _fail()
    for access in (0x80000000, 0x40000000, 0x00010000):
        handle, error = _windows_create_file(path, access)
        if handle is not None:
            _windows_close_file(handle)
            raise _fail()
        if error != 32:  # ERROR_SHARING_VIOLATION; permission failure is not proof.
            raise _fail()


def _change_time(descriptor: int) -> int:
    if sys.platform != "win32":
        return os.fstat(descriptor).st_ctime_ns
    import ctypes
    import msvcrt
    from ctypes import wintypes

    class FileBasicInfo(ctypes.Structure):
        _fields_ = [("creation", ctypes.c_longlong), ("access", ctypes.c_longlong),
                    ("write", ctypes.c_longlong), ("change", ctypes.c_longlong),
                    ("attributes", wintypes.DWORD)]

    query = ctypes.WinDLL("kernel32", use_last_error=True).GetFileInformationByHandleEx
    query.argtypes = (wintypes.HANDLE, ctypes.c_int, ctypes.c_void_p, wintypes.DWORD)
    query.restype = wintypes.BOOL
    value = FileBasicInfo()
    if not query(msvcrt.get_osfhandle(descriptor), 0, ctypes.byref(value), ctypes.sizeof(value)):
        raise _fail()
    if value.change <= 0 or value.attributes & getattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT", 0x400):
        raise _fail()
    return int(value.change)


def _decode_usn_record(raw: bytes, file_id: int) -> tuple[int, int, int]:
    if len(raw) < 8:
        raise _fail()
    length, major, minor = struct.unpack_from("<IHH", raw)
    layouts = {2: (60, 8, 24, 56), 3: (76, 16, 40, 72)}
    if major not in layouts or minor != 0 or length != len(raw):
        raise _fail()
    minimum, id_bytes, usn_offset, name_offset = layouts[major]
    if length < minimum:
        raise _fail()
    identifier = int.from_bytes(raw[8:8 + id_bytes], "little")
    sequence = struct.unpack_from("<q", raw, usn_offset)[0]
    name_length, name_start = struct.unpack_from("<HH", raw, name_offset)
    if (identifier != file_id or sequence <= 0 or name_length % 2
            or name_start < minimum or name_start + name_length > length):
        raise _fail()
    return major, identifier, sequence


def _windows_journal(descriptor: int, *, checkpoint: bool) -> tuple[int, int, int]:
    """Use only the named file's existing journal; never configure a volume."""
    import ctypes
    import msvcrt
    from ctypes import wintypes

    control = ctypes.WinDLL("kernel32", use_last_error=True).DeviceIoControl
    control.argtypes = (wintypes.HANDLE, wintypes.DWORD, ctypes.c_void_p, wintypes.DWORD,
                        ctypes.c_void_p, wintypes.DWORD, ctypes.POINTER(wintypes.DWORD), ctypes.c_void_p)
    control.restype = wintypes.BOOL
    handle = msvcrt.get_osfhandle(descriptor)
    returned = wintypes.DWORD()
    sealed = None
    if checkpoint:
        sequence = ctypes.c_longlong()
        # SDK winioctl.h: function 59, METHOD_NEITHER, FILE_ANY_ACCESS.
        if (not control(handle, 0x900EF, None, 0, ctypes.byref(sequence), ctypes.sizeof(sequence),
                        ctypes.byref(returned), None) or returned.value != ctypes.sizeof(sequence)
                or sequence.value <= 0):
            raise _fail()
        sealed = int(sequence.value)
    buffer = ctypes.create_string_buffer(4096)
    # SDK winioctl.h: function 58, METHOD_NEITHER, FILE_ANY_ACCESS.
    if (not control(handle, 0x900EB, None, 0, buffer, len(buffer), ctypes.byref(returned), None)
            or not 8 <= returned.value <= len(buffer)):
        raise _fail()
    receipt = _decode_usn_record(buffer.raw[:returned.value], os.fstat(descriptor).st_ino)
    if sealed is not None and receipt[2] != sealed:
        raise _fail()
    return receipt


@dataclass(frozen=True)
class IndexedFileChangeReceipt:
    path: Path
    identity: tuple[int, int, int, int, int]
    change_time: int
    change_journal: tuple[int, int, int] | None

    def assert_current(self) -> None:
        if capture_indexed_file_change(self.path, checkpoint=False) != self:
            raise _fail()


def capture_indexed_file_change(path: Path, *, checkpoint: bool = True) -> IndexedFileChangeReceipt:
    """Pin a unique regular file and its actual metadata-change clock.

    Python Windows ctime is a creation clock on supported older runtimes. The
    handle-based FILE_BASIC_INFO ChangeTime is required on Windows; failures do
    not fall back to mtime. ChangeTime can repeat during rapid writes; Windows
    also requires a per-file USN close checkpoint and sequence. Unsupported USN
    behavior fences storage. Checks do not write another checkpoint. POSIX ctime
    supplies its metadata-change clock. These are not rollback authentication.
    """
    absolute = Path(os.path.abspath(path))
    try:
        for component in (absolute, *absolute.parents):
            value = component.lstat()
            if (stat.S_ISLNK(value.st_mode)
                    or getattr(value, "st_file_attributes", 0) & getattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT", 0x400)):
                raise _fail()
        before = absolute.lstat()
        _regular(before)
        descriptor = _open_metadata_descriptor(absolute)
        try:
            opened = os.fstat(descriptor)
            _regular(opened)
            before_identity, opened_identity = _identity(before), _identity(opened)
            if (before_identity[:4] != opened_identity[:4] if sys.platform == "win32"
                    else before_identity != opened_identity):
                raise _fail()
            journal = _windows_journal(descriptor, checkpoint=checkpoint) if sys.platform == "win32" else None
            changed = _change_time(descriptor)
            if (sys.platform == "win32" and _windows_journal(descriptor, checkpoint=False) != journal):
                raise _fail()
            if _identity(os.fstat(descriptor)) != opened_identity or _change_time(descriptor) != changed:
                raise _fail()
        finally:
            os.close(descriptor)
        after = absolute.lstat()
        _regular(after)
        if _identity(after) != before_identity:
            raise _fail()
        return IndexedFileChangeReceipt(absolute, before_identity, changed, journal)
    except OSError as exc:
        raise _fail() from exc
