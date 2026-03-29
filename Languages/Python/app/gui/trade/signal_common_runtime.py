from __future__ import annotations

import copy


def _connector_name(self) -> str:
    try:
        return self._connector_label_text(self._runtime_connector_backend(suppress_refresh=True))
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


def _persist_trade_allocations(self, save_position_allocations) -> None:
    try:
        mode = self.mode_combo.currentText() if hasattr(self, "mode_combo") else None
        save_position_allocations(
            getattr(self, "_entry_allocations", {}),
            getattr(self, "_open_position_records", {}),
            mode=mode,
        )
    except Exception:
        pass


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
    record["allocations"] = copy.deepcopy(alloc_entries or [])

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
            if isinstance(value, str):
                try:
                    value_num = float(value)
                except Exception:
                    value_num = value
            else:
                value_num = value
            if dest_key == "leverage":
                try:
                    value_num = int(value_num)
                except Exception:
                    pass
            if dest_key not in base_data or base_data.get(dest_key) in (None, "", 0):
                base_data[dest_key] = value_num

    record["data"] = base_data
