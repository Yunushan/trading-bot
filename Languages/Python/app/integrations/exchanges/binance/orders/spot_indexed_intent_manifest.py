"""Confined, immutable pointer receipts for explicitly migrated Spot intent stores."""
from __future__ import annotations

import json
import os
import re
import stat
import sys
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from uuid import UUID

from app.settings.live_safety import LiveTradingSafetyError

INDEXED_MANIFEST_VERSION = 3
INDEXED_SCHEMA_VERSION = 1
INDEXED_STORAGE_KIND = "sqlite-spot-intents"
_MAX_MANIFEST_BYTES = 16384
_FIELDS = {"format_version", "storage_kind", "schema_version", "store_id", "backend_id", "database",
           "migration_id", "source_backup", "source_sha256", "created_at"}


def _fail() -> LiveTradingSafetyError:
    return LiveTradingSafetyError("Indexed Spot intent manifest is invalid; restore and reconcile storage.")


def _uuid(value: object) -> str:
    if not isinstance(value, str):
        raise _fail()
    try:
        parsed = UUID(value)
    except (ValueError, AttributeError) as exc:
        raise _fail() from exc
    if str(parsed) != value:
        raise _fail()
    return value


def _identity(value: os.stat_result) -> tuple[int, int, int, int, int]:
    return value.st_dev, value.st_ino, value.st_size, value.st_mtime_ns, value.st_ctime_ns


def _confined_path(path: Path) -> Path:
    absolute = Path(os.path.abspath(path))
    for component in (absolute, *absolute.parents):
        try:
            info = component.lstat()
        except FileNotFoundError:
            continue
        except OSError as exc:
            raise _fail() from exc
        if (stat.S_ISLNK(info.st_mode)
                or getattr(info, "st_file_attributes", 0) & getattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT", 0x400)):
            raise _fail()
    return absolute


@dataclass(frozen=True)
class IndexedIntentManifest:
    store_id: str
    backend_id: str
    database: str
    migration_id: str
    source_backup: str
    source_sha256: str
    created_at: str

    def payload(self) -> dict[str, object]:
        return {"format_version": INDEXED_MANIFEST_VERSION, "storage_kind": INDEXED_STORAGE_KIND,
                "schema_version": INDEXED_SCHEMA_VERSION, **vars(self)}

@dataclass(frozen=True)
class IndexedManifestReceipt:
    logical_path: Path
    manifest: IndexedIntentManifest
    raw: bytes
    identity: tuple[int, int, int, int, int]

    def database_path(self, logical_path: Path) -> Path:
        self.assert_current(logical_path)
        return _existing_regular(self.logical_path.parent / self.manifest.database)

    def source_backup_path(self, logical_path: Path) -> Path:
        self.assert_current(logical_path)
        return _existing_regular(self.logical_path.parent / self.manifest.source_backup)

    def assert_current(self, logical_path: Path) -> None:
        logical_path = _confined_path(logical_path)
        if logical_path != self.logical_path:
            raise LiveTradingSafetyError("Indexed Spot intent source path changed.")
        current = read_indexed_manifest(logical_path)
        if current.raw != self.raw or current.identity != self.identity:
            raise LiveTradingSafetyError("Indexed Spot intent manifest changed during the storage operation.")


def _existing_regular(path: Path) -> Path:
    path = _confined_path(path)
    try:
        info = path.lstat()
        if not stat.S_ISREG(info.st_mode) or info.st_nlink != 1:
            raise _fail()
    except OSError as exc:
        raise LiveTradingSafetyError("Indexed Spot intent storage is missing; restore it without resetting history.") from exc
    return path


def validate_indexed_manifest(payload: object, *, logical_path: Path) -> IndexedIntentManifest:
    if (not isinstance(payload, dict) or set(payload) != _FIELDS
            or type(payload.get("format_version")) is not int
            or payload["format_version"] != INDEXED_MANIFEST_VERSION
            or type(payload.get("schema_version")) is not int
            or payload["schema_version"] != INDEXED_SCHEMA_VERSION
            or payload.get("storage_kind") != INDEXED_STORAGE_KIND):
        raise _fail()
    store_id = _uuid(payload["store_id"])
    backend_id = _uuid(payload["backend_id"])
    migration_id = _uuid(payload["migration_id"])
    database = f"{logical_path.name}.{backend_id}.sqlite3"
    backup = f"{logical_path.name}.v2-{migration_id}.backup"
    if (payload["database"] != database or payload["source_backup"] != backup
            or not isinstance(payload["source_sha256"], str)
            or re.fullmatch(r"[0-9a-f]{64}", payload["source_sha256"]) is None
            or not isinstance(payload["created_at"], str)):
        raise _fail()
    try:
        created = datetime.fromisoformat(payload["created_at"].replace("Z", "+00:00"))
        if created.tzinfo is None:
            raise ValueError("missing timezone")
    except (ValueError, TypeError) as exc:
        raise _fail() from exc
    return IndexedIntentManifest(store_id, backend_id, database, migration_id, backup,
                                 payload["source_sha256"], payload["created_at"])


def decode_indexed_manifest(raw: bytes, *, logical_path: Path) -> IndexedIntentManifest:
    if len(raw) > _MAX_MANIFEST_BYTES:
        raise _fail()

    def unique(pairs):
        result = {}
        for key, value in pairs:
            if key in result:
                raise _fail()
            result[key] = value
        return result

    try:
        payload = json.loads(raw, object_pairs_hook=unique)
    except (ValueError, UnicodeError, RecursionError) as exc:
        raise _fail() from exc
    return validate_indexed_manifest(payload, logical_path=logical_path)


def read_indexed_manifest(logical_path: Path) -> IndexedManifestReceipt:
    logical_path = _confined_path(logical_path)
    try:
        before = logical_path.lstat()
        if not stat.S_ISREG(before.st_mode) or before.st_nlink != 1 or before.st_size > _MAX_MANIFEST_BYTES:
            raise _fail()
        descriptor = os.open(logical_path, os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0))
        try:
            opened = os.fstat(descriptor)
            # Windows path/descriptor stat disagree about ctime on some fresh
            # files. Compare the same inode/content fields across APIs, while
            # retaining ctime in each API's before/after and receipt checks.
            opened_identity = _identity(opened)
            before_identity = _identity(before)
            if ((opened_identity[:4] != before_identity[:4] if sys.platform == "win32"
                 else opened_identity != before_identity) or opened.st_nlink != 1):
                raise _fail()
            raw = os.read(descriptor, _MAX_MANIFEST_BYTES + 1)
            if len(raw) != opened.st_size or _identity(os.fstat(descriptor)) != _identity(opened):
                raise _fail()
        finally:
            os.close(descriptor)
        after = logical_path.lstat()
        if _identity(after) != _identity(before):
            raise _fail()
    except OSError as exc:
        raise LiveTradingSafetyError("Indexed Spot intent manifest cannot be read; storage remains fenced.") from exc
    return IndexedManifestReceipt(logical_path, decode_indexed_manifest(raw, logical_path=logical_path),
                                  raw, _identity(before))
