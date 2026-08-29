"""Keep frozen PyQt6 builds from loading an incompatible external ICU DLL."""

from __future__ import annotations

import os
import sys
from pathlib import Path


def _read_u16(payload: bytes, offset: int) -> int | None:
    end = offset + 2
    if offset < 0 or end > len(payload):
        return None
    return int.from_bytes(payload[offset:end], "little")


def _read_u32(payload: bytes, offset: int) -> int | None:
    end = offset + 4
    if offset < 0 or end > len(payload):
        return None
    return int.from_bytes(payload[offset:end], "little")


def _rva_to_file_offset(payload: bytes, rva: int) -> int | None:
    if len(payload) < 0x40 or payload[:2] != b"MZ":
        return None
    pe_offset = _read_u32(payload, 0x3C)
    if pe_offset is None or payload[pe_offset : pe_offset + 4] != b"PE\x00\x00":
        return None

    coff_offset = pe_offset + 4
    section_count = _read_u16(payload, coff_offset + 2)
    optional_size = _read_u16(payload, coff_offset + 16)
    if section_count is None or optional_size is None:
        return None
    optional_offset = coff_offset + 20
    magic = _read_u16(payload, optional_offset)
    data_directory_offset = optional_offset + (112 if magic == 0x20B else 96)
    export_rva = _read_u32(payload, data_directory_offset)
    if export_rva is None:
        return None

    section_offset = optional_offset + optional_size
    for index in range(section_count):
        current = section_offset + index * 40
        virtual_size = _read_u32(payload, current + 8)
        virtual_address = _read_u32(payload, current + 12)
        raw_size = _read_u32(payload, current + 16)
        raw_offset = _read_u32(payload, current + 20)
        if None in (virtual_size, virtual_address, raw_size, raw_offset):
            continue
        section_size = max(virtual_size or 0, raw_size or 0)
        if virtual_address <= rva < virtual_address + section_size:
            return raw_offset + rva - virtual_address
    return None


def _pe_export_names(payload: bytes) -> set[bytes]:
    pe_offset = _read_u32(payload, 0x3C)
    if pe_offset is None:
        return set()
    coff_offset = pe_offset + 4
    optional_size = _read_u16(payload, coff_offset + 16)
    if optional_size is None:
        return set()
    optional_offset = coff_offset + 20
    magic = _read_u16(payload, optional_offset)
    data_directory_offset = optional_offset + (112 if magic == 0x20B else 96)
    export_rva = _read_u32(payload, data_directory_offset)
    if not export_rva:
        return set()
    export_offset = _rva_to_file_offset(payload, export_rva)
    if export_offset is None:
        return set()
    name_count = _read_u32(payload, export_offset + 24)
    names_rva = _read_u32(payload, export_offset + 32)
    if not name_count or names_rva is None:
        return set()
    names_offset = _rva_to_file_offset(payload, names_rva)
    if names_offset is None:
        return set()

    names: set[bytes] = set()
    for index in range(name_count):
        name_rva = _read_u32(payload, names_offset + index * 4)
        if name_rva is None:
            continue
        name_offset = _rva_to_file_offset(payload, name_rva)
        if name_offset is None:
            continue
        end = payload.find(b"\x00", name_offset)
        if end > name_offset:
            names.add(payload[name_offset:end])
    return names


def _has_unsuffixed_icu_exports(path: Path) -> bool:
    try:
        payload = path.read_bytes()
    except OSError:
        return False
    exports = _pe_export_names(payload)
    return b"ucnv_open" in exports and b"ucnv_close" in exports


def _hide_incompatible_bundled_icu() -> None:
    if sys.platform != "win32":
        return

    bundle_root_raw = getattr(sys, "_MEIPASS", "")
    if not bundle_root_raw:
        return

    bundled_icu = Path(bundle_root_raw) / "icuuc.dll"
    if not bundled_icu.is_file():
        return

    # PyInstaller can discover ICU from an unrelated dependency such as
    # Poppler. That DLL exports version-suffixed ICU 78 symbols, while the
    # PyQt6 Qt wheel imports the unsuffixed symbols provided by Windows ICU.
    # Leave a valid unsuffixed ICU untouched and hide only the incompatible
    # binary so Qt can resolve its normal system dependency.
    if _has_unsuffixed_icu_exports(bundled_icu):
        return

    try:
        os.replace(bundled_icu, bundled_icu.with_name("icuuc.dll.trading-bot-disabled"))
    except OSError:
        # The application will report the normal Qt import error if the
        # bundle directory is not writable; do not mask the original failure.
        return


_hide_incompatible_bundled_icu()
