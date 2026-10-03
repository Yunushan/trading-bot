"""Explicit, offline operator actions; never called from order submission."""
from __future__ import annotations

import os
from contextlib import nullcontext
from pathlib import Path
from uuid import uuid4

from app.settings.live_safety import LiveTradingSafetyError

from .order_intent_runtime import (
    _INTENT_FORMAT_VERSION,
    _intent_binding,
    _intent_path,
    _is_unresolved,
    _legacy_intent_path,
    _now,
    _read_ledger,
    _spot_account_uid,
    _spot_owner_scope,
)
from .order_intent_store import ledger_transaction, ledger_transactions, write_ledger
from .spot_execution_owner import (
    _read_marker,
    _validated_reconciliation_reference,
    mark_owner_recovery_required_locked,
    owner_administration_lock,
    owner_marker_path,
    provision_owner_marker_locked,
    rearm_owner_marker_locked,
)


PROVISION_ACK = "I_HAVE_STOPPED_EXECUTORS_AND_RECONCILED_EXCHANGE_STATE"


def _audit_history_exists(path: Path) -> bool:
    path = path.expanduser()
    prefix = f"{path.name}."
    for candidate in path.parent.iterdir():
        suffix = candidate.name[len(prefix):] if candidate.name.startswith(prefix) else ""
        if candidate.name == path.name or (suffix.isascii() and suffix.isdigit()):
            if candidate.is_symlink() or not candidate.is_file() or candidate.stat().st_size:
                return True
    return False


def provision_order_intent_store(self, *, acknowledgement: str, migrate: bool = False) -> dict[str, object]:
    """Create first-use storage or preserve a legacy ledger while binding it.

    This acknowledgement records an operator prerequisite, not machine-verified
    exchange evidence. Missing established history must be restored, not reset.
    """
    if acknowledgement != PROVISION_ACK:
        raise LiveTradingSafetyError("Stop all executors and reconcile exchange state before provisioning storage.")
    binding = _intent_binding(self)
    path = _intent_path(self)
    spot_scope = _spot_owner_scope(self)
    if spot_scope:
        legacy_path = _legacy_intent_path(self)
        if legacy_path != path and (legacy_path.exists() or legacy_path.is_symlink()):
            raise LiveTradingSafetyError(
                "Existing Spot intent history must be explicitly migrated; first-use storage cannot replace it."
            )
    backup = None
    with owner_administration_lock(path) if spot_scope else nullcontext():
        if spot_scope and (owner_marker_path(path).exists() or owner_marker_path(path).is_symlink()):
            raise LiveTradingSafetyError("Spot execution owner state already exists; restore its ledger instead.")
        with ledger_transaction(path):
            if migrate:
                payload = _read_ledger(path, allow_legacy=True)
                if payload["format_version"] != 1:
                    raise LiveTradingSafetyError("Only a legacy version-one ledger can be migrated; existing stores are not reset.")
                backup = path.with_name(f"{path.name}.v1-{uuid4().hex}.backup")
                write_ledger(backup, dict(payload))
            else:
                if path.exists() or path.is_symlink():
                    raise LiveTradingSafetyError("Order intent storage already exists; it will not be overwritten.")
                audit = getattr(self, "_order_audit_log_path", None)
                if audit and _audit_history_exists(Path(audit)):
                    raise LiveTradingSafetyError("Audit history exists; restore the missing intent ledger instead of creating an empty store.")
                payload = {"intents": {}}
            payload.update(format_version=_INTENT_FORMAT_VERSION, binding=binding, store_id=str(uuid4()), created_at=_now())
            write_ledger(path, payload)
        if spot_scope:
            provision_owner_marker_locked(
                path, uid=_spot_account_uid(self), environment=binding["environment"],
                store_id=str(payload["store_id"]),
            )
    intents = payload["intents"]
    assert isinstance(intents, dict)
    return {
        "path": str(path), "format_version": _INTENT_FORMAT_VERSION,
        "intent_count": len(intents), "backup_path": str(backup) if backup else None,
    }


def rearm_spot_execution_owner(
    self, *, acknowledgement: str, reconciliation_reference: str,
) -> dict[str, object]:
    """Offline operator attestation after exchange reconciliation, never an automatic restart."""
    if not _spot_owner_scope(self):
        raise LiveTradingSafetyError("Spot execution owner rearm requires a Spot account scope.")
    path = _intent_path(self)
    binding = _intent_binding(self)
    with owner_administration_lock(path):
        with ledger_transaction(path):
            ledger = _read_ledger(path, expected_binding=binding)
            intents = ledger["intents"]
            if not isinstance(intents, dict) or any(_is_unresolved(record) for record in intents.values()):
                raise LiveTradingSafetyError("Unresolved order intents require reconciliation before owner rearm.")
        reference = rearm_owner_marker_locked(
            path, uid=_spot_account_uid(self), environment=binding["environment"],
            store_id=str(ledger["store_id"]), acknowledgement=acknowledgement,
            reconciliation_reference=reconciliation_reference,
        )
    return {"path": str(path), "rearmed": True, "reconciliation_reference": reference}


def migrate_spot_order_intent_store(
    self, *, acknowledgement: str, reconciliation_reference: str,
) -> dict[str, object]:
    """Move resolved legacy Spot history into the UID-scoped ledger, disarmed until rearm."""
    if not _spot_owner_scope(self):
        raise LiveTradingSafetyError("Spot history migration requires a Spot account scope.")
    if acknowledgement != PROVISION_ACK:
        raise LiveTradingSafetyError("Stop all executors and reconcile exchange state before migrating Spot history.")

    reference = _validated_reconciliation_reference(reconciliation_reference)
    path = _intent_path(self)
    legacy_path = _legacy_intent_path(self)
    if legacy_path == path:
        raise LiveTradingSafetyError("Spot history migration requires distinct legacy and UID-scoped ledger paths.")
    binding = _intent_binding(self)
    uid = _spot_account_uid(self)
    backup_path = legacy_path.with_name(
        f"{legacy_path.name}.spot-{binding['environment']}-uid-{uid}.backup"
    )
    marker_path = owner_marker_path(path)

    with owner_administration_lock(path):
        with ledger_transactions(path, legacy_path, backup_path):
            for candidate in (path, legacy_path, backup_path, marker_path):
                if candidate.is_symlink():
                    raise LiveTradingSafetyError("Spot migration paths and owner state must not be symbolic links.")

            marker: dict[str, object] | None = None
            if marker_path.exists():
                marker = _read_marker(
                    marker_path, uid=uid, environment=binding["environment"], store_id=None,
                )
                if (
                    marker["state"] != "recovery_required"
                    or marker["generation"] != 0
                    or marker["reconciliation_reference"] != reference
                ):
                    raise LiveTradingSafetyError(
                        "Spot owner state already exists; only the matching interrupted migration can be resumed."
                    )
                store_id = str(marker["store_id"])
                resumed = True
            else:
                if path.exists() or backup_path.exists():
                    raise LiveTradingSafetyError("Spot migration target or backup already exists; it will not be overwritten.")
                store_id = ""
                resumed = False

            if legacy_path.exists():
                source_path = legacy_path
            elif resumed and backup_path.exists():
                source_path = backup_path
            else:
                raise LiveTradingSafetyError("Legacy Spot intent history is missing; restore it before migration.")

            source = _read_ledger(source_path, allow_legacy=True)
            source_intents = source["intents"]
            if not isinstance(source_intents, dict):
                raise LiveTradingSafetyError("Legacy Spot intent history is malformed; reconcile it before migration.")
            if any(_is_unresolved(record) for record in source_intents.values()):
                raise LiveTradingSafetyError("Unresolved order intents require reconciliation before Spot history migration.")

            if source["format_version"] == _INTENT_FORMAT_VERSION:
                if source.get("binding") != binding:
                    raise LiveTradingSafetyError("Legacy Spot ledger belongs to different credentials or environment.")
                source_store_id = source.get("store_id")
                if not isinstance(source_store_id, str):
                    raise LiveTradingSafetyError("Legacy Spot ledger has invalid store identity.")
                if store_id and source_store_id != store_id:
                    raise LiveTradingSafetyError("Interrupted Spot migration store identity does not match its source.")
                store_id = source_store_id
            else:
                if "credential_rotation_history" in source:
                    raise LiveTradingSafetyError("Legacy Spot ledger has unsupported rotation history; reconcile it before migration.")
                if not store_id:
                    store_id = str(uuid4())

            if legacy_path.exists() and backup_path.exists():
                backup = _read_ledger(backup_path, allow_legacy=True)
                if backup != source:
                    raise LiveTradingSafetyError("Legacy Spot ledger changed during an interrupted migration; manual reconciliation is required.")
            elif backup_path.exists() and not resumed:
                raise LiveTradingSafetyError("Spot migration backup already exists; it will not be overwritten.")

            if marker is None:
                if path.exists():
                    raise LiveTradingSafetyError("Spot migration target already exists; it will not be overwritten.")
                provision_owner_marker_locked(
                    path, uid=uid, environment=binding["environment"], store_id=store_id,
                    state="recovery_required", reconciliation_reference=reference,
                )

            if not backup_path.exists():
                if not legacy_path.exists():
                    raise LiveTradingSafetyError("Legacy Spot intent history disappeared during migration.")
                os.replace(legacy_path, backup_path)

            current: dict[str, object] | None = None
            if path.exists():
                current = _read_ledger(path, expected_binding=binding)
                if current.get("store_id") != store_id:
                    raise LiveTradingSafetyError("Interrupted Spot migration target has a different store identity.")

            migrated = dict(source)
            if source["format_version"] == 1:
                migrated.update(
                    format_version=_INTENT_FORMAT_VERSION,
                    binding=binding,
                    store_id=store_id,
                    created_at=current.get("created_at") if current is not None else _now(),
                )
            if current is not None:
                if current != migrated:
                    raise LiveTradingSafetyError("Interrupted Spot migration target differs from its preserved source history.")
            else:
                write_ledger(path, migrated)

            if legacy_path.exists():
                legacy_path.unlink()

    return {
        "path": str(path),
        "backup_path": str(backup_path),
        "format_version": _INTENT_FORMAT_VERSION,
        "intent_count": len(source_intents),
        "migrated": True,
        "resumed": resumed,
        "requires_rearm": True,
        "reconciliation_reference": reference,
    }


def rotate_spot_owner_credentials(
    self, *, acknowledgement: str, reconciliation_reference: str,
) -> dict[str, object]:
    """Rebind an offline Spot ledger without discarding intents, then require explicit rearm."""
    if not _spot_owner_scope(self):
        raise LiveTradingSafetyError("Spot credential rotation requires a Spot account scope.")
    if acknowledgement != PROVISION_ACK:
        raise LiveTradingSafetyError("Stop all executors and reconcile exchange state before rotating credentials.")

    path = _intent_path(self)
    binding = _intent_binding(self)
    with owner_administration_lock(path):
        with ledger_transaction(path):
            ledger = _read_ledger(path)
            current_binding = ledger.get("binding")
            if not isinstance(current_binding, dict):
                raise LiveTradingSafetyError("Spot intent ledger has no credential binding to rotate.")
            if (
                current_binding.get("exchange") != binding["exchange"]
                or current_binding.get("environment") != binding["environment"]
            ):
                raise LiveTradingSafetyError("Credential rotation cannot change the exchange or environment.")
            previous_fingerprint = current_binding.get("credential_fingerprint")
            next_fingerprint = binding["credential_fingerprint"]
            if not isinstance(previous_fingerprint, str):
                raise LiveTradingSafetyError("Spot intent ledger has no valid credential fingerprint to rotate.")
            if previous_fingerprint == next_fingerprint:
                raise LiveTradingSafetyError("Credential rotation requires a different API key.")

            intents = ledger.get("intents")
            if not isinstance(intents, dict) or any(_is_unresolved(record) for record in intents.values()):
                raise LiveTradingSafetyError("Unresolved order intents require reconciliation before credential rotation.")
            history = ledger.get("credential_rotation_history", [])
            if not isinstance(history, list):
                raise LiveTradingSafetyError("Credential rotation history is malformed; reconcile the ledger first.")

            reference = mark_owner_recovery_required_locked(
                path, uid=_spot_account_uid(self), environment=binding["environment"],
                store_id=str(ledger["store_id"]), reconciliation_reference=reconciliation_reference,
            )
            ledger["credential_rotation_history"] = [
                *history,
                {
                    "previous_fingerprint": previous_fingerprint,
                    "new_fingerprint": next_fingerprint,
                    "rotated_at": _now(),
                    "reconciliation_reference": reference,
                },
            ]
            ledger["binding"] = binding
            write_ledger(path, ledger, expected_new_binding=binding)

    return {
        "path": str(path),
        "intent_count": len(intents),
        "rotated": True,
        "requires_rearm": True,
        "reconciliation_reference": reference,
    }
