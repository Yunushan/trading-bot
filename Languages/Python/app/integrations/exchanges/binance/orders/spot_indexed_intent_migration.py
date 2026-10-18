"""Explicit offline import and immutable cutover proof for indexed Spot ledgers."""
from __future__ import annotations

import hashlib
import json
import os
import re
import stat
import sys
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import cast
from uuid import uuid4

from app.settings.live_safety import LiveTradingSafetyError

from .order_intent_runtime import (
    _intent_binding, _intent_path, _now, _spot_account_uid, _spot_owner_scope,
    validate_order_intent_ledger,
)
from .order_intent_store import (
    _publish, _sync_directory, current_ledger_deadline, indexed_migration_fence_path,
    indexed_namespace_exists, ledger_transaction,
)
from .spot_execution_owner import (
    _read_marker, _validated_reconciliation_reference,
    mark_owner_recovery_required_locked, owner_administration_lock, owner_marker_path,
)
from .spot_indexed_intent_manifest import (
    IndexedIntentManifest, _confined_path, validate_indexed_manifest,
)
from .spot_indexed_intent_store import create_indexed_store, read_indexed_snapshot

_RECEIPT_VERSION = 1
_RECEIPT_LIMIT = 16384
_FIELDS = {"format_version", "logical_path", "manifest", "source_identity", "binding",
           "owner_before", "target_generation", "reconciliation_reference"}


def _fail(reason: str) -> LiveTradingSafetyError:
    return LiveTradingSafetyError(f"Indexed Spot migration {reason}; preserve outputs and reconcile storage.")


def _identity(value: os.stat_result) -> tuple[int, int, int, int, int]:
    return value.st_dev, value.st_ino, value.st_size, value.st_mtime_ns, value.st_ctime_ns


def _read_regular(path: Path, *, limit: int | None = None) -> tuple[bytes, tuple[int, int, int, int, int]]:
    path = _confined_path(path)
    try:
        before = path.lstat()
        if not stat.S_ISREG(before.st_mode) or before.st_nlink != 1 or (limit is not None and before.st_size > limit):
            raise _fail("requires confined regular files")
        fd = os.open(path, os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0) | getattr(os, "O_BINARY", 0))
        try:
            opened = os.fstat(fd)
            if ((_identity(opened)[:4] != _identity(before)[:4] if sys.platform == "win32"
                 else _identity(opened) != _identity(before)) or opened.st_nlink != 1):
                raise _fail("source file changed")
            chunks = []
            while chunk := os.read(fd, 1024 * 1024):
                chunks.append(chunk)
                if limit is not None and sum(map(len, chunks)) > limit:
                    raise _fail("receipt is too large")
            raw = b"".join(chunks)
            if len(raw) != opened.st_size or _identity(os.fstat(fd)) != _identity(opened):
                raise _fail("source file changed")
        finally:
            os.close(fd)
        if _identity(path.lstat()) != _identity(before):
            raise _fail("source file changed")
        return raw, _identity(before)
    except OSError as exc:
        raise _fail("cannot read retained storage") from exc


def _decode(raw: bytes) -> dict[str, object]:
    def unique(pairs):
        result = {}
        for name, value in pairs:
            if name in result:
                raise _fail("contains duplicate fields")
            result[name] = value
        return result

    def nonfinite(value):
        raise _fail("contains nonfinite data")

    try:
        value = json.loads(raw.decode("utf-8"), object_pairs_hook=unique, parse_constant=nonfinite)
    except (ValueError, UnicodeError, RecursionError) as exc:
        raise _fail("contains unreadable data") from exc
    if not isinstance(value, dict):
        raise _fail("requires an object")
    return value


def _serialized(value: object) -> bytes:
    return (json.dumps(value, sort_keys=True, indent=2, allow_nan=False) + "\n").encode("utf-8")


@dataclass(frozen=True)
class IndexedMigrationReceipt:
    logical_path: Path
    raw: bytes
    identity: tuple[int, int, int, int, int]
    manifest: IndexedIntentManifest
    source_identity: tuple[int, int, int, int, int]
    binding_json: str
    owner_before_json: str
    target_generation: int
    reconciliation_reference: str

    @property
    def binding(self) -> dict[str, str]:
        return cast(dict[str, str], json.loads(self.binding_json))

    @property
    def owner_before(self) -> dict[str, object]:
        return cast(dict[str, object], json.loads(self.owner_before_json))

    def assert_current(self, logical_path: Path) -> None:
        if _confined_path(logical_path) != self.logical_path:
            raise _fail("receipt source path changed")
        current = read_indexed_migration_receipt(logical_path)
        if current.raw != self.raw or current.identity != self.identity:
            raise _fail("receipt changed")


def read_indexed_migration_receipt(logical_path: Path) -> IndexedMigrationReceipt:
    logical_path = _confined_path(logical_path)
    raw, identity = _read_regular(indexed_migration_fence_path(logical_path), limit=_RECEIPT_LIMIT)
    value = _decode(raw)
    if (set(value) != _FIELDS or type(value["format_version"]) is not int
            or value["format_version"] != _RECEIPT_VERSION or value["logical_path"] != str(logical_path)):
        raise _fail("receipt fields do not match")
    manifest = validate_indexed_manifest(value["manifest"], logical_path=logical_path)
    binding = value["binding"]
    if (not isinstance(binding, dict) or set(binding) != {"exchange", "environment", "credential_fingerprint"}
            or binding["exchange"] != "binance" or binding["environment"] != "live"
            or not isinstance(binding["credential_fingerprint"], str)
            or re.fullmatch(r"[0-9a-f]{64}", binding["credential_fingerprint"]) is None):
        raise _fail("receipt binding does not match")
    source_identity = value["source_identity"]
    if (not isinstance(source_identity, list) or len(source_identity) != 5
            or any(type(item) is not int for item in source_identity)
            or any(item < 0 for item in source_identity[:3])):
        raise _fail("receipt source identity does not match")
    before = value["owner_before"]
    reference = _validated_reconciliation_reference(value["reconciliation_reference"])
    target = value["target_generation"]
    if (not isinstance(before, dict) or set(before) != {
            "format_version", "account_uid", "environment", "store_id", "state", "generation",
            "updated_at", "reconciliation_reference"}
            or type(before["format_version"]) is not int or before["format_version"] != 1
            or type(before["account_uid"]) is not int or before["account_uid"] <= 0
            or before["environment"] != binding["environment"] or before["store_id"] != manifest.store_id
            or not isinstance(before["state"], str) or before["state"] not in {"armed", "active", "recovery_required"}
            or type(before["generation"]) is not int or before["generation"] < 0
            or not isinstance(before["updated_at"], str)
            or not isinstance(before["reconciliation_reference"], str) or not before["reconciliation_reference"].strip()
            or type(target) is not int or target != before["generation"] + 1
            or reference != value["reconciliation_reference"]):
        raise _fail("receipt owner proof does not match")
    return IndexedMigrationReceipt(logical_path, raw, identity, manifest, tuple(source_identity),
                                   json.dumps(binding, sort_keys=True), json.dumps(before, sort_keys=True),
                                   target, reference)


def assert_indexed_migration_manifest(
    logical_path: Path, manifest: IndexedIntentManifest,
) -> IndexedMigrationReceipt:
    receipt = read_indexed_migration_receipt(logical_path)
    if receipt.manifest != manifest:
        raise _fail("manifest differs from its original receipt")
    return receipt


def _publish_exclusive(temp: Path, final: Path) -> None:
    """Publish new flushed files with durable parent/name semantics; never replace outputs."""
    _confined_path(final)
    if sys.platform == "win32":
        import ctypes
        from ctypes import wintypes

        move = ctypes.WinDLL("kernel32", use_last_error=True).MoveFileExW
        move.argtypes = (wintypes.LPCWSTR, wintypes.LPCWSTR, wintypes.DWORD)
        move.restype = wintypes.BOOL
        if not move(str(temp), str(final), 0x8):
            raise ctypes.WinError(ctypes.get_last_error())
    else:
        os.link(temp, final, follow_symlinks=False)
        temp.unlink()
        _sync_directory(final.parent)


def _write_exclusive(path: Path, raw: bytes) -> None:
    _confined_path(path)
    fd, name = tempfile.mkstemp(prefix=f".{path.name}.", suffix=".tmp", dir=path.parent)
    temp = Path(name)
    try:
        with os.fdopen(fd, "wb") as handle:
            handle.write(raw)
            handle.flush()
            os.fsync(handle.fileno())
        _publish_exclusive(temp, path)
    finally:
        temp.unlink(missing_ok=True)


def _assert_source(path: Path, raw: bytes, identity: tuple[int, int, int, int, int]) -> None:
    current, current_identity = _read_regular(path)
    if current != raw or current_identity != identity:
        raise _fail("original source changed before cutover")


def _assert_target_owner(path: Path, receipt: IndexedMigrationReceipt, *, uid: int) -> dict[str, object]:
    marker = cast(dict[str, object], _read_marker(
        owner_marker_path(path), uid=uid, environment="live", store_id=receipt.manifest.store_id,
    ))
    if marker == receipt.owner_before:
        return marker
    if (marker["state"] != "recovery_required" or marker["generation"] != receipt.target_generation
            or marker["reconciliation_reference"] != receipt.reconciliation_reference):
        raise _fail("owner changed during the interrupted import")
    return marker


def _verify_import(path: Path, receipt: IndexedMigrationReceipt, payload: dict[str, object]) -> None:
    from .spot_indexed_intent_bridge import indexed_intent_rules

    snapshot = read_indexed_snapshot(
        path, logical_path=receipt.logical_path, rules=indexed_intent_rules(), expected_binding=receipt.binding,
        deadline=current_ledger_deadline(receipt.logical_path), expected_store_id=receipt.manifest.store_id,
        expected_backend_id=receipt.manifest.backend_id,
    )
    if snapshot.receipt.revision != 1 or snapshot.payload != payload:
        raise _fail("imported history differs from the original source")


def _prepare_database(
    receipt: IndexedMigrationReceipt, payload: dict[str, object], *, allow_create: bool = True,
) -> Path:
    from .spot_indexed_intent_bridge import indexed_intent_rules

    path = cast(Path, _confined_path(receipt.logical_path.parent / receipt.manifest.database))
    staging = _confined_path(path.with_name(f".{path.name}.import"))
    if path.exists():
        if staging.exists() or staging.is_symlink():
            raise _fail("contains conflicting database outputs")
        _verify_import(path, receipt, payload)
        return path
    if not allow_create:
        raise _fail("published database is missing; restore its established history")
    if not staging.exists():
        create_indexed_store(
            staging, payload, logical_path=receipt.logical_path, rules=indexed_intent_rules(),
            expected_binding=receipt.binding, deadline=current_ledger_deadline(receipt.logical_path),
            backend_id=receipt.manifest.backend_id,
        )
    _verify_import(staging, receipt, payload)
    descriptor = os.open(staging, os.O_RDWR | getattr(os, "O_NOFOLLOW", 0))
    try:
        os.fsync(descriptor)
    finally:
        os.close(descriptor)
    _publish_exclusive(staging, path)
    _verify_import(path, receipt, payload)
    return path


def migrate_spot_indexed_intent_store(
    self, *, acknowledgement: str, reconciliation_reference: str,
) -> dict[str, object]:
    """Preserve a bound v2 ledger, exclude its owner, and cut over disarmed."""
    from .order_intent_provisioning import PROVISION_ACK

    if not _spot_owner_scope(self) or getattr(self, "mode", None) != "Live":
        raise _fail("requires the selected Live Spot owner scope")
    if acknowledgement != PROVISION_ACK:
        raise _fail("requires stopped executors and the reconciliation acknowledgement")
    reference = _validated_reconciliation_reference(reconciliation_reference)
    path = _confined_path(_intent_path(self))
    binding = _intent_binding(self)
    uid = _spot_account_uid(self)
    with owner_administration_lock(path), ledger_transaction(path):
        fence = indexed_migration_fence_path(path)
        source_raw, source_identity = _read_regular(path)
        source = _decode(source_raw)
        resumed = fence.exists() or fence.is_symlink()
        if resumed:
            receipt = read_indexed_migration_receipt(path)
            if receipt.binding != binding or receipt.reconciliation_reference != reference:
                raise _fail("retry binding or reconciliation reference changed")
            marker = _assert_target_owner(path, receipt, uid=uid)
        else:
            if indexed_namespace_exists(path):
                raise _fail("contains unrecorded indexed outputs")
            source = validate_order_intent_ledger(source, expected_binding=binding)
            if source["format_version"] != 2:
                raise _fail("requires an existing bound version-two ledger")
            marker = _read_marker(owner_marker_path(path), uid=uid, environment="live", store_id=str(source["store_id"]))
            migration_id, backend_id = str(uuid4()), str(uuid4())
            manifest = IndexedIntentManifest(
                str(source["store_id"]), backend_id, f"{path.name}.{backend_id}.sqlite3", migration_id,
                f"{path.name}.v2-{migration_id}.backup", hashlib.sha256(source_raw).hexdigest(), _now(),
            )
            _write_exclusive(fence, _serialized({
                "format_version": _RECEIPT_VERSION, "logical_path": str(path), "manifest": manifest.payload(),
                "source_identity": list(source_identity), "binding": binding, "owner_before": marker,
                "target_generation": int(marker["generation"]) + 1, "reconciliation_reference": reference,
            }))
            receipt = read_indexed_migration_receipt(path)
        backup = _confined_path(path.parent / receipt.manifest.source_backup)
        complete = source.get("format_version") == 3
        if complete:
            if validate_indexed_manifest(source, logical_path=path) != receipt.manifest:
                raise _fail("published pointer differs from the original import")
            source_raw, _ = _read_regular(backup)
        else:
            if source_identity != receipt.source_identity or hashlib.sha256(source_raw).hexdigest() != receipt.manifest.source_sha256:
                raise _fail("original source differs from its recorded receipt")
            _assert_source(path, source_raw, receipt.source_identity)
            if not backup.exists():
                _write_exclusive(backup, source_raw)
        backup_raw, _ = _read_regular(backup)
        if backup_raw != source_raw or hashlib.sha256(backup_raw).hexdigest() != receipt.manifest.source_sha256:
            raise _fail("preserved source backup changed")
        payload = validate_order_intent_ledger(_decode(backup_raw), expected_binding=binding)
        if payload["format_version"] != 2 or payload["store_id"] != receipt.manifest.store_id:
            raise _fail("preserved ledger identity changed")
        _prepare_database(receipt, payload, allow_create=not complete)
        receipt.assert_current(path)
        marker = _assert_target_owner(path, receipt, uid=uid)
        if complete:
            if marker == receipt.owner_before:
                raise _fail("pointer was published without owner invalidation")
        else:
            _assert_source(path, source_raw, receipt.source_identity)
            if marker == receipt.owner_before:
                mark_owner_recovery_required_locked(
                    path, uid=uid, environment="live", store_id=receipt.manifest.store_id,
                    reconciliation_reference=reference,
                )
            marker = _assert_target_owner(path, receipt, uid=uid)
            if marker["generation"] != receipt.target_generation or marker["state"] != "recovery_required":
                raise _fail("owner invalidation was not persisted")
            _assert_source(path, source_raw, receipt.source_identity)
            receipt.assert_current(path)
            fd, name = tempfile.mkstemp(prefix=f".{path.name}.", suffix=".tmp", dir=path.parent)
            temporary = Path(name)
            try:
                with os.fdopen(fd, "wb") as handle:
                    handle.write(_serialized(receipt.manifest.payload()))
                    handle.flush()
                    os.fsync(handle.fileno())
                _assert_source(path, source_raw, receipt.source_identity)
                _publish(temporary, path)
            finally:
                temporary.unlink(missing_ok=True)
    return {"path": str(path), "backup_path": str(backup), "database_path": str(path.parent / receipt.manifest.database),
            "format_version": 3, "intent_count": len(cast(dict[str, object], payload["intents"])), "migrated": True,
            "resumed": resumed, "requires_rearm": True, "reconciliation_reference": reference}
