"""Explicit, offline operator actions; never called from order submission."""
from __future__ import annotations

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
from .order_intent_store import ledger_transaction, write_ledger
from .spot_execution_owner import (
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
                write_ledger(backup, payload)
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
        rearm_owner_marker_locked(
            path, uid=_spot_account_uid(self), environment=binding["environment"],
            store_id=str(ledger["store_id"]), acknowledgement=acknowledgement,
            reconciliation_reference=reconciliation_reference,
        )
    return {"path": str(path), "rearmed": True, "reconciliation_reference": reconciliation_reference.strip()}
