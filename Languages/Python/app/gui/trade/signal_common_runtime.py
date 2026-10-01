from __future__ import annotations

import copy
import hashlib
import json
from decimal import Decimal, InvalidOperation

from app.gui.positions.actions_state_runtime import (
    _allocation_is_active,
    sync_local_position_tracking_from_allocations,
)


_TRADE_STATE_FIELDS = (
    "_entry_allocations", "_open_position_records", "_pending_close_times",
    "_entry_intervals", "_entry_times", "_entry_times_by_iv", "_position_missing_counts",
    "_closed_position_records", "_closed_trade_registry", "_processed_close_events",
    "_processed_open_events",
)


def _capture_trade_state(self) -> dict:
    return {name: (hasattr(self, name), copy.deepcopy(getattr(self, name, None)))
            for name in _TRADE_STATE_FIELDS}


def _restore_trade_state(self, snapshot: dict) -> None:
    for name, (present, value) in snapshot.items():
        if not present:
            if hasattr(self, name):
                delattr(self, name)
            continue
        current = getattr(self, name, None)
        if isinstance(current, dict) and isinstance(value, dict):
            current.clear()
            current.update(value)
        elif isinstance(current, list) and isinstance(value, list):
            current[:] = value
        elif isinstance(current, set) and isinstance(value, set):
            current.clear()
            current.update(value)
        else:
            setattr(self, name, value)


def _trade_event_receipt(order_info: dict, ctx: dict, kind: str) -> dict:
    """Keep only stable event identity and quantity in the durable replay receipt."""
    quantity_raw = order_info.get("executed_qty")
    if quantity_raw is None:
        quantity_raw = order_info.get("qty")
    if isinstance(quantity_raw, bool):
        raise ValueError("Trade event quantity is invalid")
    try:
        quantity = abs(Decimal(str(quantity_raw)))
    except (InvalidOperation, TypeError, ValueError):
        raise ValueError("Trade event quantity is invalid") from None
    if not quantity.is_finite() or quantity <= 0:
        raise ValueError("Trade event quantity is invalid")
    if quantity.adjusted() > 78 or int(quantity.as_tuple().exponent) < -78:
        raise ValueError("Trade event quantity is out of bounds")
    fills = order_info.get("fills_meta")
    client_id = str(order_info.get("client_order_id") or order_info.get("clientOrderId") or "").strip()
    order_id = str(order_info.get("order_id") or (fills.get("order_id") if isinstance(fills, dict) else "") or "").strip()
    event_id = str(order_info.get("event_id") or order_info.get("event_uid") or "").strip()
    identity: str | list[str] = client_id or order_id or event_id
    if not identity:
        context = str(order_info.get("context_key") or order_info.get("slot_id") or order_info.get("ledger_id") or "").strip()
        event_time = str(order_info.get("time") or "").strip()
        if not context or not event_time:
            raise ValueError("Trade event has no stable replay identity")
        identity = [context, event_time]
    symbol = str(ctx.get("sym_upper") or "").strip().upper()
    side_key = str(ctx.get("side_key") or "").strip().upper()
    identity_json = json.dumps([kind, symbol, side_key, identity], separators=(",", ":"), ensure_ascii=True)
    quantity_text = format(quantity, "f")
    if "." in quantity_text:
        quantity_text = quantity_text.rstrip("0").rstrip(".")
    if len(quantity_text) > 80:
        raise ValueError("Trade event quantity is out of bounds")
    receipt = {
        "version": 1,
        "event_id": "gui-" + hashlib.sha256(identity_json.encode("utf-8")).hexdigest(),
        "kind": kind, "symbol": symbol, "side_key": side_key,
        "quantity": quantity_text,
    }
    if client_id:
        receipt["client_order_id"] = client_id
    if order_id:
        receipt["order_id"] = order_id
    return receipt


def _has_trade_event_receipt(self, receipt: dict) -> bool:
    session = getattr(self, "_allocation_snapshot_session", None)
    checker = getattr(session, "has_trade_event_receipt", None)
    return checker(receipt) is True if callable(checker) else False


def _retain_pending_trade_event(self, order_info: dict, ctx: dict, receipt: dict | None) -> None:
    pending = getattr(self, "_pending_trade_reconciliation", None)
    if not isinstance(pending, dict):
        pending = {}
        self._pending_trade_reconciliation = pending
    identifier = receipt["event_id"] if receipt else "unclassified"
    memory_payload = json.dumps(order_info, sort_keys=True, default=str, ensure_ascii=True)
    memory_key = identifier + ":" + hashlib.sha256(memory_payload.encode("utf-8")).hexdigest()
    already_pending = memory_key in pending
    pending[memory_key] = {"order_info": copy.deepcopy(order_info), "receipt": copy.deepcopy(receipt),
                           "reason": "local publication or exact reconciliation pending"}
    fences = getattr(self, "_pending_allocation_reconciliations", None)
    if not isinstance(fences, dict):
        fences = {}
        self._pending_allocation_reconciliations = fences
    key = (ctx.get("sym_upper"), ctx.get("side_key"))
    events = fences.setdefault(key, [])
    event = {"event_id": identifier, "order_info": copy.deepcopy(order_info), "receipt": copy.deepcopy(receipt)}
    if event not in events:
        events.append(event)
    if not already_pending:
        log = getattr(self, "log", None)
        if callable(log):
            try:
                log(f"{ctx.get('sym_upper') or 'Trade'} awaits local portfolio reconciliation.")
            except (AttributeError, LookupError, OSError, ReferenceError, RuntimeError, TypeError, ValueError):
                pass


def _clear_pending_trade_event(self, ctx: dict, receipt: dict) -> None:
    pending = getattr(self, "_pending_trade_reconciliation", {})
    for identifier, event in list(pending.items()):
        if event.get("receipt") == receipt:
            pending.pop(identifier, None)
    fences = getattr(self, "_pending_allocation_reconciliations", {})
    key = (ctx.get("sym_upper"), ctx.get("side_key"))
    events = fences.get(key)
    if isinstance(events, list):
        remaining = [event for event in events if event.get("receipt") != receipt]
        if remaining:
            fences[key] = remaining
        else:
            fences.pop(key, None)


def _connector_name(self) -> str:
    try:
        return str(self._connector_label_text(self._runtime_connector_backend(suppress_refresh=True)))
    except Exception:
        return "Unknown"


def _side_key(side_value) -> str:
    return "L" if str(side_value).upper() in ("BUY", "LONG") else "S"


def _ensure_trade_maps(self):
    alloc_map = getattr(self, "_entry_allocations", None)
    if alloc_map is None:
        self._entry_allocations = {}
        alloc_map = self._entry_allocations

    pending_close = getattr(self, "_pending_close_times", None)
    if pending_close is None:
        self._pending_close_times = {}
        pending_close = self._pending_close_times
    return alloc_map, pending_close


def _normalize_interval(self, value):
    try:
        canon = self._canonicalize_interval(value)
    except Exception:
        canon = None
    if canon:
        return canon
    if isinstance(value, str):
        lowered = value.strip().lower()
        return lowered or None
    return None


def _safe_float(value):
    try:
        if value is None:
            return None
        if isinstance(value, str):
            stripped = value.strip()
            if not stripped:
                return None
            return float(stripped)
        return float(value)
    except Exception:
        return None


def _persist_trade_allocations(self, save_position_allocations) -> bool:
    try:
        mode = self.mode_combo.currentText() if hasattr(self, "mode_combo") else None
        result = save_position_allocations(
            getattr(self, "_entry_allocations", {}),
            getattr(self, "_open_position_records", {}),
            mode=mode,
            session=getattr(self, "_allocation_snapshot_session", None),
            event_receipt=getattr(self, "_active_trade_event_receipt", None),
        )
        return result is True
    except Exception:
        return False


def _refresh_trade_views(self, sym, *, mark_traded: bool = True) -> None:
    if mark_traded and sym:
        self.traded_symbols.add(sym)
    self.update_balance_label()
    self.refresh_positions(symbols=[sym] if sym else None)


def _sync_open_position_snapshot(
    self,
    symbol_key: str,
    side_key_local: str,
    alloc_entries: list | None,
    trade_snapshot: dict | None,
    interval_label: str | None,
    normalized_interval: str | None,
    open_time_fmt: str | None,
    *,
    resolve_trigger_indicators,
    normalize_trigger_actions_map,
) -> None:
    if not symbol_key or side_key_local not in ("L", "S"):
        return

    open_records = getattr(self, "_open_position_records", None)
    if not isinstance(open_records, dict):
        open_records = {}
        self._open_position_records = open_records
    active_entries = [entry for entry in alloc_entries or []
                      if isinstance(entry, dict) and _allocation_is_active(entry)]
    if not active_entries:
        open_records.pop((symbol_key, side_key_local), None)
        sync_local_position_tracking_from_allocations(self, symbol_key, side_key_local, [])
        return

    record = open_records.get((symbol_key, side_key_local))
    if not isinstance(record, dict):
        record = {
            "symbol": symbol_key,
            "side_key": side_key_local,
            "entry_tf": interval_label or normalized_interval or "-",
            "open_time": open_time_fmt
            or (trade_snapshot.get("open_time") if isinstance(trade_snapshot, dict) else "-"),
            "close_time": "-",
            "status": "Active",
            "data": {},
            "indicators": [],
            "stop_loss_enabled": False,
        }
        open_records[(symbol_key, side_key_local)] = record

    record["status"] = "Active"
    if interval_label:
        record["entry_tf"] = interval_label
    elif normalized_interval and not record.get("entry_tf"):
        record["entry_tf"] = normalized_interval
    if open_time_fmt:
        record["open_time"] = open_time_fmt
    record["allocations"] = copy.deepcopy(active_entries)
    sync_local_position_tracking_from_allocations(
        self,
        symbol_key,
        side_key_local,
        active_entries,
    )

    base_data = dict(record.get("data") or {})
    base_data.setdefault("symbol", symbol_key)
    base_data.setdefault("side_key", side_key_local)
    if interval_label:
        base_data.setdefault("interval_display", interval_label)
    if normalized_interval:
        base_data.setdefault("interval", normalized_interval)

    if isinstance(trade_snapshot, dict):
        trigger_desc = trade_snapshot.get("trigger_desc")
        if trigger_desc:
            base_data["trigger_desc"] = trigger_desc
        normalized_triggers = resolve_trigger_indicators(
            trade_snapshot.get("trigger_indicators"),
            trigger_desc,
        )
        if normalized_triggers:
            base_data["trigger_indicators"] = normalized_triggers
        normalized_actions = normalize_trigger_actions_map(
            trade_snapshot.get("trigger_actions")
        )
        if normalized_actions:
            base_data["trigger_actions"] = normalized_actions

        value_mappings = (
            ("qty", "qty"),
            ("margin_usdt", "margin_usdt"),
            ("pnl_value", "pnl_value"),
            ("entry_price", "entry_price"),
            ("leverage", "leverage"),
            ("notional", "size_usdt"),
            ("size_usdt", "size_usdt"),
        )
        for src_key, dest_key in value_mappings:
            value = trade_snapshot.get(src_key)
            if value is None or value == "":
                continue
            value_num: object
            if isinstance(value, str):
                try:
                    value_num = float(value)
                except Exception:
                    value_num = value
            else:
                value_num = value
            if dest_key == "leverage":
                try:
                    if isinstance(value_num, (int, float, str, bytes, bytearray)):
                        value_num = int(float(value_num))
                except Exception:
                    pass
            if dest_key not in base_data or base_data.get(dest_key) in (None, "", 0):
                base_data[dest_key] = value_num

    record["data"] = base_data
    for field_name, source_name in (("qty", "qty"), ("margin_usdt", "margin_usdt"), ("size_usdt", "notional")):
        base_data[field_name] = sum(float(entry.get(source_name) or 0.0) for entry in active_entries)
    if base_data["qty"] > 0:
        weighted_price = sum(float(entry.get("qty") or 0.0) * float(entry.get("entry_price") or 0.0)
                             for entry in active_entries)
        base_data["entry_price"] = weighted_price / base_data["qty"]
