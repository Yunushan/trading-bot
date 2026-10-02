"""Paired local publication of exact operator-recovered Spot BUY acquisitions."""
from __future__ import annotations

from collections.abc import Mapping
from copy import deepcopy
from decimal import Decimal, InvalidOperation
from pathlib import Path

from app.settings.live_safety import LiveTradingSafetyError

from .order_intent_runtime import (
    _has_durable_spot_buy_allocation,
    _intent_binding,
    _intent_path,
    _read_ledger,
)
from .order_intent_store import ledger_transaction, ledger_transactions
from .spot_allocation_generation_runtime import canonical_spot_buy_metadata
from .spot_fill_recovery_runtime import _persist_spot_buy_allocation_unlocked


_TERMINAL = {"FILLED", "CANCELED", "EXPIRED", "EXPIRED_IN_MATCH", "REJECTED"}


def capture_spot_buy_recovery_binding(owner) -> dict:
    """Pin the verified account ledger while the administrator excludes execution."""
    path = _intent_path(owner)
    binding = _intent_binding(owner)
    with ledger_transaction(path):
        ledger = _read_ledger(path, expected_binding=binding)
    return {"intent_path": path, "binding": dict(binding), "store_id": ledger["store_id"]}


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
        result = _persist_spot_buy_allocation_unlocked(allocation_path, fill)
        if not _has_durable_spot_buy_allocation(
            record, portfolio_signature=metadata["signature"], portfolio_quantity=quantity,
        ):
            raise LiveTradingSafetyError("Spot BUY recovery has no matching durable acquisition.")
        return result
