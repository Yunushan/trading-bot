from __future__ import annotations

import copy

from ..runtime.window import main_window_runtime

_RESOLVE_TRIGGER_INDICATORS = None


def configure_main_window_positions_record_helpers(
    *,
    resolve_trigger_indicators=None,
) -> None:
    global _RESOLVE_TRIGGER_INDICATORS

    _RESOLVE_TRIGGER_INDICATORS = resolve_trigger_indicators


def _resolve_trigger_indicators_safe(raw, desc: str | None = None) -> list[str]:
    func = _RESOLVE_TRIGGER_INDICATORS
    if not callable(func):
        return []
    try:
        return list(func(raw, desc))
    except Exception:
        return []


def _copy_allocations_for_key(alloc_map_global: dict, symbol: str, side_key: str) -> list[dict]:
    try:
        entries = alloc_map_global.get((symbol, side_key), [])
        if isinstance(entries, dict):
            entries = list(entries.values())
        if not isinstance(entries, list):
            return []
        return [copy.deepcopy(entry) for entry in entries if isinstance(entry, dict)]
    except Exception:
        return []


def _seed_positions_map_from_rows(self, base_rows: list, alloc_map_global: dict, prev_records: dict) -> dict[tuple, dict]:
    positions_map: dict[tuple, dict] = {}

    for row in base_rows:
        try:
            sym = str(row.get("symbol") or "").strip().upper()
            side_key = str(row.get("side_key") or "SPOT").upper()
            if not sym:
                continue
            stop_loss_enabled = False
            if side_key in ("L", "S"):
                stop_loss_enabled = self._position_stop_loss_enabled(sym, side_key)
            data_entry = dict(row)
            data_entry["symbol"] = sym
            data_entry["side_key"] = side_key
            positions_map[(sym, side_key)] = {
                "symbol": sym,
                "side_key": side_key,
                "entry_tf": row.get("entry_tf"),
                "open_time": row.get("open_time"),
                "close_time": "-",
                "status": "Active",
                "data": data_entry,
                "indicators": [],
                "stop_loss_enabled": stop_loss_enabled,
                "leverage": data_entry.get("leverage"),
                "liquidation_price": data_entry.get("liquidation_price") or data_entry.get("liquidationPrice"),
            }
            allocations_seed = _copy_allocations_for_key(alloc_map_global, sym, side_key)
            intervals_from_alloc: set[str] = set()
            interval_trigger_map: dict[str, set[str]] = {}
            trigger_union: set[str] = set()
            normalized_entry_triggers = _resolve_trigger_indicators_safe(
                data_entry.get("trigger_indicators"),
                data_entry.get("trigger_desc"),
            )
            if normalized_entry_triggers:
                trigger_union.update(normalized_entry_triggers)
                data_entry["trigger_indicators"] = normalized_entry_triggers
            elif data_entry.get("trigger_indicators"):
                data_entry.pop("trigger_indicators", None)
            if allocations_seed:
                positions_map[(sym, side_key)]["allocations"] = allocations_seed
                if not data_entry.get("trigger_desc"):
                    for alloc in allocations_seed:
                        if not isinstance(alloc, dict):
                            continue
                        desc = alloc.get("trigger_desc")
                        if desc:
                            data_entry["trigger_desc"] = desc
                            break
                for alloc in allocations_seed:
                    status_flag = str(alloc.get("status") or "").strip().lower()
                    try:
                        qty_val = abs(float(alloc.get("qty") or 0.0))
                    except Exception:
                        qty_val = None
                    is_active_allocation = status_flag not in {"closed", "error"}
                    if qty_val is not None and qty_val <= 0.0:
                        qty_val = 0.0
                    if qty_val and status_flag not in {"closed", "error"}:
                        is_active_allocation = True
                    interval_val = alloc.get("interval_display") or alloc.get("interval")
                    interval_normalized = ""
                    interval_key = None
                    if interval_val:
                        try:
                            canon_iv = self._canonicalize_interval(interval_val)
                        except Exception:
                            canon_iv = None
                        if canon_iv:
                            interval_normalized = canon_iv.strip()
                        else:
                            interval_normalized = str(interval_val).strip()
                        if interval_normalized:
                            interval_key = interval_normalized.lower()
                            if is_active_allocation:
                                intervals_from_alloc.add(interval_normalized)
                                interval_trigger_map.setdefault(interval_key, set())
                    normalized_triggers = _resolve_trigger_indicators_safe(
                        alloc.get("trigger_indicators"),
                        alloc.get("trigger_desc"),
                    )
                    if normalized_triggers:
                        alloc["trigger_indicators"] = normalized_triggers
                    elif alloc.get("trigger_indicators"):
                        alloc.pop("trigger_indicators", None)
                    if is_active_allocation and normalized_triggers:
                        trigger_union.update(normalized_triggers)
                        target_key = interval_key or (interval_normalized.strip().lower() if interval_normalized else None) or "-"
                        interval_trigger_map.setdefault(target_key, set()).update(normalized_triggers)
                if trigger_union:
                    data_entry["trigger_indicators"] = sorted(dict.fromkeys(trigger_union))
            elif normalized_entry_triggers:
                data_entry["trigger_indicators"] = normalized_entry_triggers
            try:
                getattr(self, "_pending_close_times", {}).pop((sym, side_key), None)
            except Exception:
                pass
        except Exception:
            continue

    tracked_keys = set(positions_map.keys())
    try:
        for (alloc_sym, alloc_side_key), allocations in alloc_map_global.items():
            if not isinstance(alloc_sym, str):
                continue
            sym = alloc_sym.strip().upper()
            side_key = str(alloc_side_key or "").strip().upper()
            if not sym or side_key not in ("L", "S"):
                continue
            key = (sym, side_key)
            if key in tracked_keys:
                continue
            if not isinstance(allocations, list) or not allocations:
                continue
            active_any = False
            for alloc in allocations:
                if not isinstance(alloc, dict):
                    continue
                status_flag = str(alloc.get("status") or "").strip().lower()
                if status_flag in {"closed", "error"}:
                    continue
                try:
                    qty_val_chk = abs(float(alloc.get("qty") or 0.0))
                except Exception:
                    qty_val_chk = 0.0
                margin_val_chk = 0.0
                notional_val_chk = 0.0
                try:
                    margin_val_chk = abs(float(alloc.get("margin_usdt") or alloc.get("margin") or 0.0))
                except Exception:
                    margin_val_chk = 0.0
                try:
                    notional_val_chk = abs(float(alloc.get("notional") or alloc.get("size_usdt") or 0.0))
                except Exception:
                    notional_val_chk = 0.0
                if qty_val_chk > 0.0 or margin_val_chk > 0.0 or notional_val_chk > 0.0:
                    active_any = True
                    break
            if not active_any:
                continue
            try:
                prev_rec = copy.deepcopy(prev_records.get(key) or {})
            except Exception:
                prev_rec = {}
            if isinstance(prev_rec, dict) and prev_rec:
                prev_rec["status"] = "Active"
                prev_rec["close_time"] = "-"
                try:
                    prev_rec["allocations"] = copy.deepcopy(
                        [entry for entry in allocations if isinstance(entry, dict)]
                    )
                except Exception:
                    pass
                positions_map[key] = prev_rec
                tracked_keys.add(key)
                try:
                    pending_close_map = getattr(self, "_pending_close_times", {})
                    if isinstance(pending_close_map, dict):
                        pending_close_map.pop(key, None)
                except Exception:
                    pass
    except Exception:
        pass

    return positions_map


def _apply_interval_metadata_to_row(
    self,
    *,
    sym: str,
    side_key: str,
    rec: dict,
    data: dict,
    allocations_existing: list[dict],
    intervals_from_alloc: set[str],
    interval_display: dict[str, str],
    interval_lookup: dict[str, str],
    interval_trigger_map: dict[str, set[str]],
    trigger_union: set[str],
) -> None:
    symbol_variants = [sym]
    sym_lower = sym.lower()
    if sym_lower and sym_lower != sym:
        symbol_variants.append(sym_lower)
    entry_times_map = getattr(self, "_entry_times_by_iv", {}) or {}
    entry_intervals_map = getattr(self, "_entry_intervals", {}) or {}
    intervals_tracked = set()
    try:
        for (sym_key, side_key_key, iv_key), ts in entry_times_map.items():
            if sym_key not in symbol_variants or side_key_key != side_key or not ts or not iv_key:
                continue
            iv_text = str(iv_key).strip()
            if not iv_text:
                continue
            try:
                canon_iv = self._canonicalize_interval(iv_text)
            except Exception:
                canon_iv = None
            interval_norm = canon_iv or iv_text
            if intervals_from_alloc and interval_norm not in intervals_from_alloc:
                continue
            key_iv = interval_norm.strip().lower()
            if key_iv:
                interval_display.setdefault(key_iv, interval_norm)
                interval_lookup.setdefault(key_iv, iv_text)
    except Exception:
        pass
    for sym_variant in symbol_variants:
        side_map = entry_intervals_map.get(sym_variant)
        if not isinstance(side_map, dict):
            continue
        bucket = side_map.get(side_key)
        if not isinstance(bucket, set):
            continue
        for iv in bucket:
            iv_text = str(iv).strip()
            if not iv_text:
                continue
            try:
                canon_iv = self._canonicalize_interval(iv_text)
            except Exception:
                canon_iv = None
            interval_norm = canon_iv or iv_text
            if intervals_from_alloc and interval_norm not in intervals_from_alloc:
                continue
            key_iv = interval_norm.strip().lower()
            if key_iv:
                interval_display.setdefault(key_iv, interval_norm)
                interval_lookup.setdefault(key_iv, iv_text)
                intervals_tracked.add(interval_norm)
    metadata = getattr(self, "_engine_indicator_map", {}) or {}
    for meta in metadata.values():
        if not isinstance(meta, dict):
            continue
        if str(meta.get("symbol") or "").strip().upper() != sym:
            continue
        allowed_side = str(meta.get("side") or "BOTH").upper()
        if side_key == "L" and allowed_side == "SELL":
            continue
        if side_key == "S" and allowed_side == "BUY":
            continue
        iv_text = str(meta.get("interval") or "").strip()
        if not iv_text:
            continue
        try:
            canon_iv = self._canonicalize_interval(iv_text)
        except Exception:
            canon_iv = None
        interval_norm = canon_iv or iv_text
        if intervals_from_alloc and interval_norm not in intervals_from_alloc:
            continue
        key_iv = interval_norm.strip().lower()
        if key_iv:
            interval_display.setdefault(key_iv, interval_norm)
            interval_lookup.setdefault(key_iv, iv_text)
    if not interval_display and intervals_from_alloc:
        for iv_norm in intervals_from_alloc:
            if not iv_norm:
                continue
            key_iv = str(iv_norm).strip().lower()
            if not key_iv:
                continue
            try:
                canon_iv = self._canonicalize_interval(iv_norm)
            except Exception:
                canon_iv = None
            interval_display.setdefault(key_iv, canon_iv or str(iv_norm))
            interval_lookup.setdefault(key_iv, str(iv_norm))
    ordered_keys: list[str] = []
    primary_interval_key = None
    if interval_display:
        ordered_keys = sorted(interval_display.keys(), key=main_window_runtime._mw_interval_sort_key)
        rec["entry_tf"] = ", ".join(interval_display[key] for key in ordered_keys if interval_display[key])
        if ordered_keys:
            primary_interval_key = ordered_keys[0]
    else:
        rec["entry_tf"] = "-"
    if primary_interval_key:
        data["interval_display"] = interval_display.get(primary_interval_key)
        data["interval"] = interval_lookup.get(primary_interval_key) or interval_display.get(primary_interval_key)
    elif not data.get("interval_display") and rec.get("entry_tf") and rec.get("entry_tf") != "-":
        data["interval_display"] = rec.get("entry_tf")
        data["interval"] = rec.get("entry_tf")

    if (not rec.get("entry_tf") or rec["entry_tf"] == "-") and intervals_tracked:
        try:
            intervals_active = sorted(
                {self._canonicalize_interval(iv) or str(iv).strip() for iv in intervals_tracked if str(iv).strip()},
                key=main_window_runtime._mw_interval_sort_key,
            )
            if intervals_active:
                rec["entry_tf"] = ", ".join(intervals_active)
                if not data.get("interval_display"):
                    data["interval_display"] = intervals_active[0]
                    data["interval"] = intervals_active[0]
        except Exception:
            pass
    if not data.get("interval_display") and rec.get("entry_tf") and rec["entry_tf"] != "-":
        first_iv = rec["entry_tf"].split(",")[0].strip()
        if first_iv:
            data["interval_display"] = first_iv
            data["interval"] = first_iv

    open_times = []
    ordered_lookup = [
        interval_lookup.get(key) or interval_display.get(key)
        for key in (ordered_keys if interval_display else [])
    ]
    for alloc in allocations_existing or []:
        if not isinstance(alloc, dict):
            continue
        alloc_open = alloc.get("open_time")
        if not alloc_open:
            continue
        dt_obj = self._parse_any_datetime(alloc_open)
        if dt_obj:
            try:
                epoch = dt_obj.timestamp()
            except Exception:
                epoch = None
            if epoch is not None:
                open_times.append((epoch, dt_obj))
    for iv in ordered_lookup:
        if not iv:
            continue
        ts = entry_times_map.get((sym, side_key, iv))
        dt_obj = self._parse_any_datetime(ts)
        if dt_obj:
            try:
                epoch = dt_obj.timestamp()
            except Exception:
                epoch = None
            if epoch is not None:
                open_times.append((epoch, dt_obj))
    if not open_times:
        entry_time_map = getattr(self, "_entry_times", {}) if hasattr(self, "_entry_times") else {}
        base_ts = None
        for sym_variant in symbol_variants:
            base_ts = entry_time_map.get((sym_variant, side_key))
            if base_ts is not None:
                break
        dt_obj = self._parse_any_datetime(base_ts)
        if dt_obj:
            try:
                epoch = dt_obj.timestamp()
            except Exception:
                epoch = None
            if epoch is not None:
                open_times.append((epoch, dt_obj))
    if not open_times and data.get("update_time"):
        dt_obj = self._parse_any_datetime(data.get("update_time"))
        if dt_obj:
            try:
                epoch = dt_obj.timestamp()
            except Exception:
                epoch = None
            if epoch is not None:
                open_times.append((epoch, dt_obj))
    if not open_times and allocations_existing:
        for alloc in allocations_existing:
            if not isinstance(alloc, dict):
                continue
            alloc_open = alloc.get("open_time")
            if not alloc_open:
                continue
            dt_obj = self._parse_any_datetime(alloc_open)
            if dt_obj:
                try:
                    epoch = dt_obj.timestamp()
                except Exception:
                    epoch = None
                if epoch is not None:
                    open_times.append((epoch, dt_obj))
        if open_times:
            open_times.sort(key=lambda item: item[0])
    if open_times:
        open_times.sort(key=lambda item: item[0])
        rec["open_time"] = self._format_display_time(open_times[0][1])
        data["open_time"] = rec["open_time"]
    else:
        entry_time_map = getattr(self, "_entry_times", {}) if hasattr(self, "_entry_times") else {}
        base_open = None
        for sym_variant in symbol_variants:
            base_open = entry_time_map.get((sym_variant, side_key))
            if base_open is not None:
                break
        dt_obj = self._parse_any_datetime(base_open)
        if dt_obj:
            formatted = self._format_display_time(dt_obj)
            rec["open_time"] = formatted
            data["open_time"] = formatted
    if ordered_keys:
        primary_interval_key = ordered_keys[0]
    indicators_selected: list[str] = []
    if trigger_union:
        if primary_interval_key:
            indicators_selected = sorted(dict.fromkeys(interval_trigger_map.get(primary_interval_key, [])))
        if not indicators_selected:
            indicators_selected = sorted(dict.fromkeys(trigger_union))
    if indicators_selected:
        rec["indicators"] = indicators_selected
        if rec.get("data"):
            rec["data"]["trigger_indicators"] = indicators_selected
    elif rec.get("data", {}).get("trigger_indicators"):
        rec["indicators"] = list(rec["data"]["trigger_indicators"])
    elif not rec.get("indicators"):
        rec["indicators"] = []
