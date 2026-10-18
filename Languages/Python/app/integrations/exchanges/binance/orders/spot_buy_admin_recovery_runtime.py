"""Paired local publication of exact operator-recovered Spot BUY acquisitions."""
from __future__ import annotations

from collections.abc import Mapping
from copy import deepcopy
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import cast

from app.settings.live_safety import LiveTradingSafetyError

from .order_intent_runtime import (
    _has_durable_spot_buy_allocation,
    _owned_inventory_confirmation,
    _intent_binding,
    _intent_path,
    _now,
    _read_ledger,
    _write_ledger,
)
from .order_intent_store import ledger_transaction, ledger_transactions
from .spot_allocation_generation_runtime import canonical_spot_buy_metadata
from .spot_fill_recovery_runtime import _persist_spot_buy_allocation_unlocked
from .spot_inventory_namespace_runtime import namespace_for_ledger
from .spot_inventory_checkpoint_runtime import owned_inventory_publication


_TERMINAL = {"FILLED", "CANCELED", "EXPIRED", "EXPIRED_IN_MATCH", "REJECTED"}


def capture_spot_buy_recovery_binding(owner) -> dict:
    """Pin the verified account ledger while the administrator excludes execution."""
    path = _intent_path(owner)
    binding = _intent_binding(owner)
    with ledger_transaction(path):
        ledger = _read_ledger(path, expected_binding=binding)
    return {"intent_path": path, "binding": dict(binding), "store_id": ledger["store_id"],
            "namespace": namespace_for_ledger(owner, ledger)}


def _validate_terminal_fill(record: Mapping, fill: Mapping, metadata: Mapping) -> Decimal:
    try:
        executed = Decimal(str(record.get("executed_qty")))
        quantity = Decimal(str(fill.get("portfolio_qty")))
    except (InvalidOperation, ValueError, TypeError):
        raise LiveTradingSafetyError("Spot BUY recovery quantities are invalid.") from None
    if (
        record.get("market") != "spot" or record.get("type") != "MARKET"
        or record.get("side") != "BUY" or record.get("state") not in {"accepted", "unknown"}
        or record.get("exchange_status") not in _TERMINAL
        or fill.get("symbol") != record.get("symbol")
        or metadata["exchange_client_order_id"] != record.get("client_order_id")
        or str(metadata["order_id"]) != str(record.get("exchange_order_id"))
        or not executed.is_finite() or executed <= 0 or executed != Decimal(metadata["gross_qty"])
        or not quantity.is_finite() or quantity <= 0 or quantity != Decimal(metadata["net_qty"])
        or (record.get("primary_fill_signature") and record["primary_fill_signature"] != metadata["signature"])
    ):
        raise LiveTradingSafetyError("Spot BUY recovery does not match its terminal intent.")
    if "primary_fill_receipt" in record and record["primary_fill_receipt"] != metadata:
        raise LiveTradingSafetyError("Spot BUY recovery conflicts with its complete primary receipt.")
    return quantity


def publish_spot_buy_recovery(
    owner,
    allocation_path: Path,
    fill: Mapping[str, object],
    *,
    expected_record: Mapping[str, object],
    expected_store_id: str,
    expected_binding: Mapping[str, str],
    expected_intent_path: Path,
) -> bool:
    """Validate retained evidence before publishing under both storage locks.

    The caller holds owner administration exclusion. The marker is committed
    after this transaction; a crash between writes remains an immutable replay.
    """
    from app.gui.shared.allocation_persistence import get_position_allocations_path

    fill = deepcopy(dict(fill))
    expected_record = deepcopy(dict(expected_record))
    expected_binding = dict(expected_binding)
    app_root = Path(__file__).resolve().parents[4]
    canonical_path = get_position_allocations_path(app_root / "gui" / "window_shell.py")
    if allocation_path != canonical_path:
        raise LiveTradingSafetyError("Spot BUY recovery allocation path changed.")
    if _intent_path(owner) != expected_intent_path or _intent_binding(owner) != expected_binding:
        raise LiveTradingSafetyError("Spot BUY recovery account binding changed.")
    metadata = canonical_spot_buy_metadata(fill)
    with ledger_transactions(expected_intent_path, allocation_path):
        if _intent_path(owner) != expected_intent_path or _intent_binding(owner) != expected_binding:
            raise LiveTradingSafetyError("Spot BUY recovery account binding changed.")
        ledger = _read_ledger(expected_intent_path, expected_binding=dict(expected_binding))
        intents = ledger["intents"]
        record = intents.get(str(fill.get("client_order_id"))) if isinstance(intents, dict) else None
        if ledger["store_id"] != expected_store_id or not isinstance(record, dict) or record != expected_record:
            raise LiveTradingSafetyError("Spot BUY recovery ledger changed before publication.")
        quantity = _validate_terminal_fill(record, fill, metadata)
        namespace = namespace_for_ledger(owner, ledger)
        with owned_inventory_publication(owner, allocation_path=allocation_path, expected_record=record, fill=fill):
            result = _persist_spot_buy_allocation_unlocked(allocation_path, fill, namespace=namespace)
        if not _has_durable_spot_buy_allocation(
            record, portfolio_signature=metadata["signature"], portfolio_quantity=quantity, namespace=namespace,
        ):
            raise LiveTradingSafetyError("Spot BUY recovery has no matching durable acquisition.")
        return cast(bool, result)


@_owned_inventory_confirmation
def confirm_spot_buy_recovery(
    owner,
    allocation_path: Path,
    fill: Mapping[str, object],
    *,
    expected_record: Mapping[str, object],
    expected_store_id: str,
    expected_binding: Mapping[str, str],
    expected_intent_path: Path,
) -> dict[str, object]:
    """Confirm the pinned acquisition after publication under both storage locks.

    The caller still holds administration exclusion. A changed store, account,
    record or acquisition leaves the durable BUY work unresolved for exact replay.
    """
    from app.gui.shared.allocation_persistence import get_position_allocations_path

    fill = deepcopy(dict(fill))
    expected_record = deepcopy(dict(expected_record))
    expected_binding = dict(expected_binding)
    app_root = Path(__file__).resolve().parents[4]
    canonical_path = get_position_allocations_path(app_root / "gui" / "window_shell.py")
    if allocation_path != canonical_path:
        raise LiveTradingSafetyError("Spot BUY recovery allocation path changed before confirmation.")
    if _intent_path(owner) != expected_intent_path or _intent_binding(owner) != expected_binding:
        raise LiveTradingSafetyError("Spot BUY recovery account binding changed before confirmation.")
    metadata = canonical_spot_buy_metadata(fill)
    with ledger_transactions(expected_intent_path, allocation_path):
        if _intent_path(owner) != expected_intent_path or _intent_binding(owner) != expected_binding:
            raise LiveTradingSafetyError("Spot BUY recovery account binding changed before confirmation.")
        ledger = _read_ledger(expected_intent_path, expected_binding=expected_binding)
        intents = ledger["intents"]
        current = intents.get(str(fill.get("client_order_id"))) if isinstance(intents, dict) else None
        if ledger["store_id"] != expected_store_id or not isinstance(current, dict) or current != expected_record:
            raise LiveTradingSafetyError("Spot BUY recovery ledger changed before acquisition confirmation.")
        quantity = _validate_terminal_fill(current, fill, metadata)
        signature = str(metadata["signature"])
        if not _has_durable_spot_buy_allocation(
            current, portfolio_signature=signature, portfolio_quantity=quantity, namespace=namespace_for_ledger(owner, ledger),
        ):
            raise LiveTradingSafetyError("Spot BUY recovery has no matching durable acquisition for confirmation.")
        already = current.get("portfolio_reconciled") is True
        if already:
            if (current.get("portfolio_recovery_signature") != signature
                    or Decimal(str(current.get("portfolio_qty"))) != quantity):
                raise LiveTradingSafetyError("Spot BUY acquisition receipt conflicts with its intent.")
        else:
            current.update({
                "state": "accepted", "portfolio_reconciled": True, "portfolio_qty": format(quantity, "f"),
                "portfolio_recovery_signature": signature, "portfolio_reconciled_at": _now(), "updated_at": _now(),
            })
            _write_ledger(expected_intent_path, ledger)
    return {"client_order_id": str(current["client_order_id"]), "portfolio_reconciled": True,
            "already_reconciled": already}
