"""Resolve inventory metadata from verified runtime authority without venue callbacks."""
from __future__ import annotations

from collections.abc import Callable, Mapping
from pathlib import Path

from app.settings.execution_mode import execution_environment
from app.settings.live_safety import LiveTradingSafetyError

from .spot_inventory_namespace import make_namespace


def _verified_uid(wrapper) -> int:
    from .order_intent_runtime import _spot_owner_scope
    context = getattr(wrapper, "_verified_spot_account_context", None)
    if (not _spot_owner_scope(wrapper) or getattr(wrapper, "_spot_execution_revoked", False)
            or not isinstance(context, tuple) or len(context) != 5
            or context[:3] != (getattr(wrapper, "api_key", None), getattr(wrapper, "api_secret", None),
                               execution_environment(getattr(wrapper, "mode", None)))
            or context[3] is not getattr(wrapper, "client", None)
            or type(context[4]) is not int or context[4] <= 0 or context[2] != "live"):
        raise LiveTradingSafetyError("Spot inventory requires the unchanged signed account context.")
    # An administrator's selected storage UID alone is never verified authority.
    if not callable(getattr(wrapper, "_resolve_spot_account_uid", None)) and (
            getattr(wrapper, "_operator_spot_account_uid", None) != context[4]):
        raise LiveTradingSafetyError("Spot inventory administration account context changed.")
    return context[4]


def namespace_for_owner(wrapper) -> dict[str, object]:
    """Use only the actual held owner and previously signed immutable account context."""
    from .order_intent_runtime import _intent_binding, _intent_path
    from .spot_execution_owner import SpotExecutionOwner, owner_lock_path, owner_marker_path
    uid = _verified_uid(wrapper)
    owner = getattr(wrapper, "_spot_execution_owner", None)
    binding = _intent_binding(wrapper)
    if (not isinstance(owner, SpotExecutionOwner) or owner.ledger_path != _intent_path(wrapper)
            or owner.lock_path != owner_lock_path(owner.ledger_path)
            or owner.marker_path != owner_marker_path(owner.ledger_path)):
        raise LiveTradingSafetyError("Spot inventory execution ownership or storage path changed.")
    owner.assert_held(uid=uid, environment=binding["environment"],
                      credential_fingerprint=binding["credential_fingerprint"], owner_wrapper=wrapper)
    return make_namespace(uid, owner.store_id)


def namespace_for_ledger(wrapper, ledger: Mapping) -> dict[str, object] | None:
    """Bind an already fully validated complete ledger to runtime or signed administration."""
    from .order_intent_runtime import _intent_binding, _intent_path, _spot_owner_scope
    if not _spot_owner_scope(wrapper):
        return None
    uid = _verified_uid(wrapper)
    binding = _intent_binding(wrapper)
    store_id = ledger.get("store_id")
    if not isinstance(store_id, str):
        raise LiveTradingSafetyError("Spot inventory logical store identity is invalid.")
    expected = make_namespace(uid, store_id)
    if ledger.get("binding") != binding:
        raise LiveTradingSafetyError("Spot inventory account ledger binding changed.")
    if getattr(wrapper, "_spot_execution_owner", None) is not None:
        if namespace_for_owner(wrapper) != expected:
            raise LiveTradingSafetyError("Spot inventory logical store changed under its owner.")
    else:
        from .spot_execution_owner import _read_marker, owner_marker_path, assert_owner_administration_held
        path = _intent_path(wrapper)
        if getattr(wrapper, "_spot_inventory_administration_path", None) != path:
            raise LiveTradingSafetyError("Spot inventory requires held execution or administration exclusion.")
        assert_owner_administration_held(path)
        _read_marker(owner_marker_path(path), uid=uid, environment="live", store_id=str(expected["store_id"]))
    return expected


def namespace_for_current_ledger(wrapper) -> dict[str, object] | None:
    """Resolve canonical inventory authority before an inventory read or publication."""
    from .order_intent_runtime import _intent_binding, _intent_path, _read_ledger, _spot_owner_scope
    from .order_intent_store import ledger_transaction
    if not _spot_owner_scope(wrapper):
        return None
    _verified_uid(wrapper)
    path = _intent_path(wrapper)
    with ledger_transaction(path):
        return namespace_for_ledger(wrapper, _read_ledger(path, expected_binding=_intent_binding(wrapper)))


def assert_bootstrap_empty_ledger(wrapper, *, expected_store_id: str) -> None:
    """Caller holds both storage locks; first-use binding requires genuinely empty history."""
    from .order_intent_runtime import _intent_binding, _read_ledger
    from .order_intent_store import current_ledger_deadline
    expected = namespace_for_owner(wrapper)
    if expected["store_id"] != expected_store_id:
        raise LiveTradingSafetyError("Spot inventory first-use store changed.")
    owner = wrapper._spot_execution_owner
    from app.gui.shared.allocation_persistence import get_position_allocations_path
    app_root = Path(__file__).resolve().parents[4]
    allocation_path = get_position_allocations_path(app_root / "gui" / "window_shell.py")
    current_ledger_deadline(owner.ledger_path, allocation_path)
    ledger = _read_ledger(owner.ledger_path, expected_binding=_intent_binding(wrapper))
    if namespace_for_ledger(wrapper, ledger) != expected or ledger.get("intents") != {}:
        raise LiveTradingSafetyError("Spot inventory first-use binding requires an empty complete intent history.")


def assert_single_unpublished_acquisition(ledger: Mapping, record: Mapping) -> None:
    """Missing unbound inventory can be recovered only for the sole first acquisition.

    This conservative legacy allowance never reconstructs discarded inventory,
    consumed quantities or earlier records. The desktop additionally checks the
    original immutable absent/empty source descriptor before this atomic write.
    """
    records = ledger.get("intents")
    if (not isinstance(records, dict) or records != {record.get("client_order_id"): record}
            or record.get("market") != "spot" or record.get("side") != "BUY"
            or record.get("portfolio_reconciled") is True or record.get("entry_reconciled") is True):
        raise LiveTradingSafetyError("Unbound Spot inventory requires explicit history reconciliation.")


def publish_owned_spot_fill(wrapper, allocation_path, fill, *, expected_record: Mapping, operation: Callable[..., bool]) -> bool:
    """Keep the original complete record alive through canonical protected publication."""
    from copy import deepcopy
    from .spot_inventory_checkpoint_runtime import owned_inventory_publication
    record, original_fill = deepcopy(dict(expected_record)), deepcopy(dict(fill))
    with owned_inventory_publication(wrapper, allocation_path=allocation_path,
                                     expected_record=record, fill=original_fill):
        namespace = namespace_for_current_ledger(wrapper)
        if namespace is None:
            raise LiveTradingSafetyError("Spot fill publication requires actual owned account authority.")
        return operation(allocation_path, original_fill, namespace=namespace)
