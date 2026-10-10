"""Complete ledger routing for an explicitly migrated indexed Spot namespace.

This bridge retains the original manifest, cutover receipt and full verified
snapshot. It provides compatibility for administrative/full-ledger operations;
its full history verification is not a selective-read capacity qualification.
"""
from __future__ import annotations

from collections.abc import Mapping
import hashlib
import os
import stat
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING, cast

from app.settings.live_safety import LiveTradingSafetyError

from .order_intent_store import IndexedLedgerWritePayload, current_ledger_deadline, ledger_file_identity
from .spot_indexed_intent_manifest import IndexedManifestReceipt, read_indexed_manifest
from .spot_indexed_file_identity import IndexedFileChangeReceipt, capture_indexed_file_change
from .spot_indexed_intent_store import (
    IndexedIntentRules, IndexedIntentSnapshot, read_indexed_snapshot, replace_indexed_snapshot,
)

if TYPE_CHECKING:
    from .spot_indexed_intent_migration import IndexedMigrationReceipt


def indexed_intent_rules() -> IndexedIntentRules:
    """Use owned complete-ledger validation and projection rules without copies."""
    from . import order_intent_runtime as runtime
    return IndexedIntentRules(runtime.validate_order_intent_ledger, runtime._is_unresolved,
                              runtime._has_active_spot_protection, runtime.used_spot_client_order_ids)


@dataclass(frozen=True)
class IndexedSourceBackupReceipt:
    path: Path
    identity: tuple[int, int, int, int, int]
    sha256: str
    file_change: IndexedFileChangeReceipt

    def assert_current(self, manifest: IndexedManifestReceipt, logical_path: Path) -> None:
        if manifest.source_backup_path(logical_path) != self.path or ledger_file_identity(self.path) != self.identity:
            raise LiveTradingSafetyError("Indexed intent preserved source backup changed.")
        try:
            self.file_change.assert_current()
        except LiveTradingSafetyError as exc:
            raise LiveTradingSafetyError("Indexed intent preserved source backup changed.") from exc


def _verified_source_backup(manifest: IndexedManifestReceipt, logical_path: Path, *,
                            checkpoint: bool = True) -> IndexedSourceBackupReceipt:
    path = manifest.source_backup_path(logical_path)
    before = ledger_file_identity(path)
    file_change = capture_indexed_file_change(path, checkpoint=checkpoint)
    try:
        descriptor = os.open(path, os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0) | getattr(os, "O_BINARY", 0))
    except OSError as exc:
        raise LiveTradingSafetyError("Indexed intent preserved source backup cannot be read.") from exc
    try:
        opened = os.fstat(descriptor)
        opened_identity = (opened.st_dev, opened.st_ino, opened.st_size, opened.st_mtime_ns, opened.st_ctime_ns)
        if ((opened_identity[:4] != before[:4] if sys.platform == "win32" else opened_identity != before)
                or not stat.S_ISREG(opened.st_mode) or opened.st_nlink != 1):
            raise LiveTradingSafetyError("Indexed intent preserved source backup changed while reading.")
        digest = hashlib.sha256()
        size = 0
        while chunk := os.read(descriptor, 1024 * 1024):
            digest.update(chunk)
            size += len(chunk)
        final = os.fstat(descriptor)
        if (size != opened.st_size
                or (final.st_dev, final.st_ino, final.st_size, final.st_mtime_ns, final.st_ctime_ns) != opened_identity
                or ledger_file_identity(path) != before
                or digest.hexdigest() != manifest.manifest.source_sha256):
            raise LiveTradingSafetyError("Indexed intent preserved source backup no longer matches migration provenance.")
        try:
            file_change.assert_current()
        except LiveTradingSafetyError as exc:
            raise LiveTradingSafetyError("Indexed intent preserved source backup changed while reading.") from exc
    except OSError as exc:
        raise LiveTradingSafetyError("Indexed intent preserved source backup cannot be read.") from exc
    finally:
        os.close(descriptor)
    return IndexedSourceBackupReceipt(path, before, digest.hexdigest(), file_change)


@dataclass(frozen=True)
class IndexedReadAuthority:
    manifest: IndexedManifestReceipt
    migration: IndexedMigrationReceipt
    snapshot: IndexedIntentSnapshot
    binding: tuple[str, str, str]
    source_backup: IndexedSourceBackupReceipt

    def original_binding(self) -> dict[str, str]:
        return dict(zip(("exchange", "environment", "credential_fingerprint"), self.binding))


class FullIndexedLedgerPayload(IndexedLedgerWritePayload):
    """Detached, complete v2-shaped data retaining its original cutover authority."""

    def __init__(self, value: dict[str, object], authority: IndexedReadAuthority) -> None:
        super().__init__(value)
        self._indexed_authority = authority

    @property
    def indexed_authority(self) -> IndexedReadAuthority:
        return self._indexed_authority

    @property
    def indexed_snapshot(self) -> IndexedIntentSnapshot:
        return self._indexed_authority.snapshot


def read_indexed_ledger(path: Path, *, expected_binding: Mapping[str, str] | None = None
                        ) -> FullIndexedLedgerPayload:
    """Verify the actual namespace and complete history under its original lock."""
    from .spot_indexed_intent_migration import assert_indexed_migration_manifest
    deadline = current_ledger_deadline(path)
    manifest = read_indexed_manifest(path)
    migration = assert_indexed_migration_manifest(path, manifest.manifest)
    database_path = manifest.database_path(path)
    from .spot_indexed_intent_selective import read_owned_indexed_snapshot, read_owned_indexed_source_backup
    cached_backup = read_owned_indexed_source_backup(path, deadline=deadline)
    source_backup = _verified_source_backup(manifest, path, checkpoint=cached_backup is None)
    if cached_backup is not None and source_backup != cached_backup:
        raise LiveTradingSafetyError("Indexed intent full read differs from its original sealed source backup.")
    snapshot = read_owned_indexed_snapshot(path, expected_binding=expected_binding, deadline=deadline)
    if snapshot is None:
        snapshot = read_indexed_snapshot(
            database_path, logical_path=manifest.logical_path, rules=indexed_intent_rules(),
            expected_binding=expected_binding, deadline=deadline,
            expected_store_id=manifest.manifest.store_id, expected_backend_id=manifest.manifest.backend_id,
        )
    if (snapshot.receipt.path != database_path or snapshot.receipt.logical_path != manifest.logical_path
            or snapshot.receipt.store_id != manifest.manifest.store_id
            or snapshot.receipt.database_id != manifest.manifest.backend_id):
        raise LiveTradingSafetyError("Indexed intent full read does not match its original namespace.")
    manifest.assert_current(path)
    migration.assert_current(path)
    source_backup.assert_current(manifest, path)
    payload = dict(snapshot.payload)
    binding = cast(dict[str, str], payload["binding"])
    authority = IndexedReadAuthority(manifest, migration, snapshot,
                                     (binding["exchange"], binding["environment"],
                                      binding["credential_fingerprint"]), source_backup)
    return FullIndexedLedgerPayload(payload, authority)


def write_indexed_ledger(path: Path, payload: Mapping[str, object], *,
                         expected_new_binding: Mapping[str, str] | None = None) -> None:
    """CAS the original full snapshot, keeping immutable namespace bytes intact."""
    if not isinstance(payload, FullIndexedLedgerPayload):
        raise LiveTradingSafetyError("Indexed intent write requires its original complete read authority.")
    authority = payload.indexed_authority
    deadline = current_ledger_deadline(path)
    authority.manifest.assert_current(path)
    authority.migration.assert_current(path)
    authority.source_backup.assert_current(authority.manifest, path)
    # Full writers already reconstruct all history. Rehash provenance here as
    # well; an unsealed backup token alone is insufficient write authority.
    if _verified_source_backup(authority.manifest, path, checkpoint=False) != authority.source_backup:
        raise LiveTradingSafetyError("Indexed intent preserved source backup changed before the full write.")
    snapshot = authority.snapshot
    original_binding = authority.original_binding()
    if (snapshot.receipt.logical_path != authority.manifest.logical_path
            or snapshot.receipt.store_id != authority.manifest.manifest.store_id
            or snapshot.receipt.database_id != authority.manifest.manifest.backend_id
            or snapshot.payload["binding"] != original_binding
            or authority.migration.manifest != authority.manifest.manifest):
        raise LiveTradingSafetyError("Indexed intent read authority does not match its original namespace.")
    database_path = authority.manifest.database_path(path)
    from .spot_indexed_intent_selective import replace_owned_indexed_snapshot
    result = replace_owned_indexed_snapshot(
        path, payload, expected=snapshot, expected_binding=original_binding,
        expected_new_binding=expected_new_binding, deadline=deadline,
    )
    if result is None:
        result = replace_indexed_snapshot(
            database_path, payload, expected=snapshot, rules=indexed_intent_rules(),
            expected_binding=original_binding, expected_new_binding=expected_new_binding, deadline=deadline,
        )
    # Cooperating cutover/rotation writers are excluded by the logical lock.
    # An external pointer/receipt replacement still fences this operation.
    from .spot_indexed_intent_selective import notify_indexed_full_commit, reject_indexed_full_commit
    try:
        authority.manifest.assert_current(path)
        authority.migration.assert_current(path)
        authority.source_backup.assert_current(authority.manifest, path)
        notify_indexed_full_commit(path, result, authority)
    except BaseException:
        reject_indexed_full_commit(path)
        raise
