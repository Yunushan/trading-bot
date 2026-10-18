"""Owned-runtime access to typed indexed admission and detached records.

Callers retain the original logical ledger lock. An unavailable owner session
cannot silently fall back to a reconstructed JSON-shaped write authority.
"""
from __future__ import annotations

from collections.abc import Mapping
from pathlib import Path

from app.settings.live_safety import LiveTradingSafetyError
from .order_intent_store import current_ledger_deadline, indexed_namespace_exists
from .spot_execution_owner import SpotExecutionOwner
from .spot_indexed_intent_bridge import read_indexed_ledger
from .spot_indexed_intent_selective import (
    IndexedAdmissionView, IndexedIntentSession, get_indexed_session,
    indexed_namespace_attribution, indexed_namespace_known, indexed_session_refresh_required, open_indexed_session,
)


def indexed_session_for(self, path: Path) -> IndexedIntentSession | None:
    """Return only this wrapper's registered, current, verified owner session."""
    owner = getattr(self, "_spot_execution_owner", None)
    original = indexed_namespace_attribution(owner_wrapper=self)
    if original is not None:
        original_owner, original_path = original
        if not isinstance(owner, SpotExecutionOwner) or owner is not original_owner:
            raise LiveTradingSafetyError("Indexed Spot execution wrapper lost its original owner.")
        if path != original_path or owner.ledger_path != original_path:
            raise LiveTradingSafetyError("Indexed Spot execution owner logical path changed.")
    current = original or indexed_namespace_attribution(path)
    if current is not None and not isinstance(owner, SpotExecutionOwner):
        raise LiveTradingSafetyError("Indexed Spot namespace requires its actual held execution owner.")
    retained_owner_namespace = (
        isinstance(owner, SpotExecutionOwner) and owner.fd is not None
        and (indexed_namespace_known(owner.ledger_path) or indexed_namespace_exists(owner.ledger_path))
    )
    # True legacy inspection keeps its original JSON path. Indexed attribution
    # is independent of mutable wrapper owner/path fields and disk destruction.
    if (original is None and current is None and not retained_owner_namespace
            and not indexed_namespace_known(path) and not indexed_namespace_exists(path)):
        return None
    if not isinstance(owner, SpotExecutionOwner):
        # Ownerless offline inspection still uses the complete indexed reader.
        return None
    from .order_intent_runtime import _intent_binding, _spot_account_uid, _spot_owner_scope
    if not _spot_owner_scope(self):
        raise LiveTradingSafetyError("Indexed Spot execution owner scope changed.")
    deadline = current_ledger_deadline(path)
    binding = _intent_binding(self)
    owner.assert_held(uid=_spot_account_uid(self), environment=binding["environment"],
                      credential_fingerprint=binding["credential_fingerprint"], owner_wrapper=self)
    if owner.ledger_path != path:
        raise LiveTradingSafetyError("Indexed Spot execution owner logical path changed.")
    session = get_indexed_session(owner=owner, owner_wrapper=self, expected_binding=binding, deadline=deadline)
    if session is not None:
        return session
    if indexed_session_refresh_required(owner):
        # Only a successful same-process full commit creates this permission.
        # Unknown external changes remain fenced by the registry tombstone.
        authority = read_indexed_ledger(path, expected_binding=binding).indexed_authority
        return open_indexed_session(owner=owner, owner_wrapper=self, expected_binding=binding,
                                    deadline=deadline, expected_authority=authority)
    if indexed_namespace_exists(path):
        raise LiveTradingSafetyError("Indexed Spot owner lacks its original verified session; reconcile storage.")
    return None


def indexed_admission_view(self, path: Path, *, probe_client_ids: tuple[str, ...] = ()
                            ) -> IndexedAdmissionView | None:
    session = indexed_session_for(self, path)
    return None if session is None else session.admission_view(
        probe_client_ids=probe_client_ids, deadline=current_ledger_deadline(path))


def assert_view_unresolved(view: IndexedAdmissionView, *, exclude_client_order_id: str | None = None) -> None:
    unresolved = [key for key in view.unresolved_ids if key != exclude_client_order_id]
    if unresolved:
        raise LiveTradingSafetyError("Unresolved exchange order intent(s) block new live submissions; "
                                     f"reconcile {', '.join(unresolved[:3])} before continuing.")


def assert_view_unused_ids(view: IndexedAdmissionView, client_ids: tuple[str, ...]) -> None:
    if any(view.owners(identifier) for identifier in client_ids):
        raise LiveTradingSafetyError("Spot client order ID was already used in this ledger.")


def update_indexed_record(self, path: Path, client_id: str, *, state: str,
                           expected_record: Mapping[str, object] | None,
                           updates: Mapping[str, object]) -> tuple[bool, dict[str, object] | None]:
    session = indexed_session_for(self, path)
    if session is None:
        return False, None
    from .order_intent_runtime import _assert_spot_opo_cancel_alias, _now
    deadline = current_ledger_deadline(path)
    record = session.read_record(client_id, deadline=deadline)
    if record is None:
        raise LiveTradingSafetyError("Order intent record is missing; reconciliation cannot update it.")
    if expected_record is not None and record != expected_record:
        return True, None
    alias = updates.get("pending_observed_client_order_id")
    if isinstance(alias, str):
        view = session.admission_view(probe_client_ids=(alias,), deadline=deadline)
        # This owned helper uses the complete queried alias owners. Its intents
        # parameter is unused with owners; no partial ledger is validated.
        _assert_spot_opo_cancel_alias({}, client_id, record, alias,
                                     owners={alias: set(view.owners(alias))})
    record.update(state=state, updated_at=_now())
    record.update({key: value for key, value in updates.items() if value not in (None, "")})
    return True, session.cas_record(client_id, record, expected_record=expected_record, deadline=deadline)
