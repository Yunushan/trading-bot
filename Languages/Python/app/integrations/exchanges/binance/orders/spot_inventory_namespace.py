"""Consistent Live Spot inventory metadata, not authenticated account authority.

The caller must obtain the UID/store from the owned verified execution or
administration boundary. These pure checks do not authenticate stored files,
prove exchange holdings, or detect restoration of an earlier matching snapshot.
"""
from __future__ import annotations

import math
from uuid import UUID

from app.settings.live_safety import LiveTradingSafetyError

ACCOUNT_NAMESPACE_KEY = "spot_account_namespace"
_NAMESPACE_FIELDS = {"version", "exchange", "market", "environment", "account_uid", "store_id"}
_EMPTY_FIELDS = {"version", "mode", "timestamp", "entry_allocations", "open_position_records",
                 "gui_trade_event_receipts", ACCOUNT_NAMESPACE_KEY}


def validate_namespace(value: object) -> dict[str, object]:
    """Validate the exact metadata contract and return a detached plain dictionary."""
    if (
        not isinstance(value, dict) or set(value) != _NAMESPACE_FIELDS
        or type(value.get("version")) is not int or value["version"] != 1
        or type(value.get("exchange")) is not str or value["exchange"] != "binance"
        or type(value.get("market")) is not str or value["market"] != "spot"
        or type(value.get("environment")) is not str or value["environment"] != "live"
        or type(value.get("account_uid")) is not int or value["account_uid"] <= 0
        or type(value.get("store_id")) is not str
    ):
        raise LiveTradingSafetyError("Live Spot inventory account namespace is malformed.")
    store_id = value["store_id"]
    try:
        if str(UUID(store_id)) != store_id:
            raise ValueError("noncanonical store ID")
    except (ValueError, TypeError, AttributeError) as exc:
        raise LiveTradingSafetyError("Live Spot inventory account namespace store ID is invalid.") from exc
    return {name: value[name] for name in ("version", "exchange", "market", "environment", "account_uid", "store_id")}


def make_namespace(uid: int, store_id: str) -> dict[str, object]:
    """Construct checked metadata; the UID/store must already be independently verified."""
    return validate_namespace({"version": 1, "exchange": "binance", "market": "spot", "environment": "live",
                               "account_uid": uid, "store_id": store_id})


def _is_live_snapshot(snapshot: object) -> bool:
    return (
        isinstance(snapshot, dict)
        and type(snapshot.get("version")) is int and snapshot["version"] == 1
        and type(snapshot.get("mode")) is str and snapshot["mode"] == "Live"
        and isinstance(snapshot.get("entry_allocations"), dict)
        and isinstance(snapshot.get("open_position_records"), dict)
    )


def is_strictly_empty_live_snapshot(snapshot: object) -> bool:
    """Recognize only absence or a strict Live header with no inventory/event history.

    Structural emptiness is not permission to bootstrap. The caller must also
    prove its complete same-store ledger has no earlier inventory obligations.
    A present namespace remains subject to exact matching in require_namespace.
    """
    if snapshot is None:
        return True
    if not _is_live_snapshot(snapshot):
        return False
    assert isinstance(snapshot, dict)
    if set(snapshot) - _EMPTY_FIELDS or snapshot["entry_allocations"] or snapshot["open_position_records"]:
        return False
    if "gui_trade_event_receipts" in snapshot and (
        not isinstance(snapshot["gui_trade_event_receipts"], list) or snapshot["gui_trade_event_receipts"]
    ):
        return False
    if "timestamp" in snapshot:
        timestamp = snapshot["timestamp"]
        if type(timestamp) not in (int, float):
            return False
        try:
            if not math.isfinite(timestamp):
                return False
        except (OverflowError, TypeError, ValueError):
            return False
    if ACCOUNT_NAMESPACE_KEY in snapshot:
        try:
            validate_namespace(snapshot[ACCOUNT_NAMESPACE_KEY])
        except LiveTradingSafetyError:
            return False
    return True


def require_namespace(
    snapshot: object, expected: object, *, allow_empty: bool = False,
) -> dict[str, object]:
    """Require account/store consistency; explicit empty allowance never relabels a source."""
    checked = validate_namespace(expected)
    if type(allow_empty) is not bool:
        raise LiveTradingSafetyError("Live Spot inventory empty-source allowance is invalid.")
    if snapshot is None:
        if allow_empty:
            return checked
        raise LiveTradingSafetyError("Live Spot inventory account namespace is missing.")
    if not _is_live_snapshot(snapshot):
        raise LiveTradingSafetyError("Live Spot inventory source is not a valid Live snapshot.")
    assert isinstance(snapshot, dict)
    if ACCOUNT_NAMESPACE_KEY in snapshot:
        observed = validate_namespace(snapshot[ACCOUNT_NAMESPACE_KEY])
        if observed != checked:
            raise LiveTradingSafetyError("Live Spot inventory belongs to another account or intent store.")
        return checked
    if allow_empty and is_strictly_empty_live_snapshot(snapshot):
        return checked
    raise LiveTradingSafetyError("Live Spot inventory account namespace is missing; unscoped history requires explicit reconciliation.")
