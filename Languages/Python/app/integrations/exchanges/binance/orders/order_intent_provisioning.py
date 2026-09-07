"""Explicit, offline operator actions; never called from order submission."""
from __future__ import annotations

from pathlib import Path
from uuid import uuid4

from app.settings.live_safety import LiveTradingSafetyError

from .order_intent_runtime import _INTENT_FORMAT_VERSION, _intent_binding, _intent_path, _now, _read_ledger
from .order_intent_store import ledger_transaction, write_ledger


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
    backup = None
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
    intents = payload["intents"]
    assert isinstance(intents, dict)
    return {
        "path": str(path), "format_version": _INTENT_FORMAT_VERSION,
        "intent_count": len(intents), "backup_path": str(backup) if backup else None,
    }
