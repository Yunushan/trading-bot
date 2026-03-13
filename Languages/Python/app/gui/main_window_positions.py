from __future__ import annotations

import copy
import os
import time
from datetime import datetime

from PyQt6 import QtCore, QtWidgets

from ..binance_wrapper import normalize_margin_ratio
from . import indicator_value_helpers, main_window_runtime

_RESOLVE_TRIGGER_INDICATORS = None
_MAX_CLOSED_HISTORY = 200
_STOP_STRATEGY_SYNC = None
_SAVE_POSITION_ALLOCATIONS = None
_NORMALIZE_INDICATOR_VALUES = None
_DERIVE_MARGIN_SNAPSHOT = None
_COERCE_BOOL = None
_FORMAT_INDICATOR_LIST = None
_COLLECT_RECORD_INDICATOR_KEYS = None
_COLLECT_INDICATOR_VALUE_STRINGS = None
_COLLECT_CURRENT_INDICATOR_LIVE_STRINGS = None
_DEDUPE_INDICATOR_ENTRIES_NORMALIZED = None
_NUMERIC_ITEM_CLS = QtWidgets.QTableWidgetItem
_NumericItem = QtWidgets.QTableWidgetItem
POS_TRIGGERED_VALUE_COLUMN = 10
POS_CURRENT_VALUE_COLUMN = 11
POS_STOP_LOSS_COLUMN = 15
POS_STATUS_COLUMN = 16
POS_CLOSE_COLUMN = 17
_CLOSED_RECORD_STATES = indicator_value_helpers.CLOSED_RECORD_STATES
_indicator_short_label = indicator_value_helpers.indicator_short_label
_indicator_entry_signature = indicator_value_helpers.indicator_entry_signature
_filter_indicator_entries_for_interval = indicator_value_helpers.filter_indicator_entries_for_interval


def _resolve_trigger_indicators_safe(raw, desc: str | None = None) -> list[str]:
    func = _RESOLVE_TRIGGER_INDICATORS
    if not callable(func):
        return []
    try:
        return list(func(raw, desc))
    except Exception:
        return []


def _normalize_indicator_values(raw) -> list[str]:
    func = _NORMALIZE_INDICATOR_VALUES
    if not callable(func):
        return []
    try:
        return list(func(raw))
    except Exception:
        return []


def _derive_margin_snapshot(
    position: dict | None,
    qty_hint: float = 0.0,
    entry_price_hint: float = 0.0,
) -> tuple[float, float, float, float]:
    func = _DERIVE_MARGIN_SNAPSHOT
    if not callable(func):
        return (0.0, 0.0, 0.0, 0.0)
    try:
        return func(position, qty_hint=qty_hint, entry_price_hint=entry_price_hint)
    except Exception:
        return (0.0, 0.0, 0.0, 0.0)


def _coerce_bool(value, default=False):
    func = _COERCE_BOOL
    if not callable(func):
        return bool(default)
    try:
        return func(value, default)
    except Exception:
        return bool(default)


def _format_indicator_list(keys) -> str:
    func = _FORMAT_INDICATOR_LIST
    if not callable(func):
        try:
            return ", ".join(str(key).strip() for key in (keys or []) if str(key).strip())
        except Exception:
            return ""
    try:
        return str(func(keys))
    except Exception:
        return ""


def _collect_record_indicator_keys(
    rec: dict,
    *,
    include_inactive_allocs: bool = False,
    include_allocation_scope: bool = True,
) -> list[str]:
    func = _COLLECT_RECORD_INDICATOR_KEYS
    if not callable(func):
        return []
    try:
        return list(
            func(
                rec,
                include_inactive_allocs=include_inactive_allocs,
                include_allocation_scope=include_allocation_scope,
            )
        )
    except Exception:
        return []


def _collect_indicator_value_strings(rec: dict, interval_hint: str | None = None) -> tuple[list[str], dict[str, list[str]]]:
    func = _COLLECT_INDICATOR_VALUE_STRINGS
    if not callable(func):
        return ([], {})
    try:
        values, interval_map = func(rec, interval_hint)
        return list(values or []), dict(interval_map or {})
    except Exception:
        return ([], {})


def _collect_current_indicator_live_strings(
    window,
    symbol,
    indicator_keys,
    cache,
    interval_map: dict[str, list[str]] | None = None,
    default_interval_hint: str | None = None,
):
    func = _COLLECT_CURRENT_INDICATOR_LIVE_STRINGS
    if not callable(func):
        return []
    try:
        return list(
            func(
                window,
                symbol,
                indicator_keys,
                cache,
                interval_map,
                default_interval_hint,
            )
            or []
        )
    except Exception:
        return []


def _dedupe_indicator_entries_normalized(entries: list[str] | None) -> list[str]:
    func = _DEDUPE_INDICATOR_ENTRIES_NORMALIZED
    if not callable(func):
        return list(entries or [])
    try:
        return list(func(entries) or [])
    except Exception:
        return list(entries or [])


def _closed_history_max(self) -> int:
    try:
        cfg_val = int(self.config.get("positions_closed_history_max", 500) or 500)
    except Exception:
        cfg_val = 500
    return max(int(_MAX_CLOSED_HISTORY), cfg_val)


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


def _mw_positions_records_cumulative(self, entries: list[dict], closed_entries: list[dict] | None = None) -> list[dict]:
    grouped: dict[tuple[str, str], list[dict]] = {}
    for rec in entries or []:
        if not isinstance(rec, dict):
            continue
        sym = str(rec.get("symbol") or "").strip().upper()
        if not sym:
            continue
        side_key = str(rec.get("side_key") or "").strip().upper()
        if not side_key:
            continue
        grouped.setdefault((sym, side_key), []).append(rec)
    aggregated: list[dict] = []
    for (_sym, _side_key), bucket in grouped.items():
        if not bucket:
            continue
        primary = max(
            bucket,
            key=lambda r: float((r.get("data") or {}).get("qty") or (r.get("data") or {}).get("margin_usdt") or 0.0),
        )
        clone = copy.deepcopy(primary)
        open_time_candidates: list[datetime] = []

        def _clean_interval_label(value: object) -> str:
            try:
                text = str(value or "").strip()
            except Exception:
                return ""
            return text if text and text not in {"-"} else ""

        intervals: list[str] = []
        total_qty = 0.0
        total_margin = 0.0
        total_pnl = 0.0
        leverage_values: set[int] = set()

        def _collect_leverage(value: object) -> None:
            try:
                if value is None or value == "":
                    return
                lev_val = int(float(value))
                if lev_val > 0:
                    leverage_values.add(lev_val)
            except Exception:
                return

        for entry in bucket:
            label = _clean_interval_label(entry.get("entry_tf")) or _clean_interval_label(
                (entry.get("data") or {}).get("interval_display")
            )
            if label and label not in intervals:
                intervals.append(label)
            data = entry.get("data") or {}
            _collect_leverage(data.get("leverage"))
            _collect_leverage(entry.get("leverage"))
            raw_entry = data.get("raw_position")
            if not isinstance(raw_entry, dict):
                raw_entry = entry.get("raw_position") if isinstance(entry.get("raw_position"), dict) else None
            if isinstance(raw_entry, dict):
                _collect_leverage(raw_entry.get("leverage"))
            allocations = entry.get("allocations") or []
            if isinstance(allocations, dict):
                allocations = list(allocations.values())
            if isinstance(allocations, list):
                for alloc in allocations:
                    if not isinstance(alloc, dict):
                        continue
                    _collect_leverage(alloc.get("leverage"))
            for ts_key in ("open_time",):
                ts_val = entry.get(ts_key) or data.get(ts_key)
                dt_obj = self._parse_any_datetime(ts_val) if hasattr(self, "_parse_any_datetime") else None
                if dt_obj:
                    open_time_candidates.append(dt_obj)
            try:
                total_qty += max(0.0, float(data.get("qty") or 0.0))
            except Exception:
                pass
            try:
                total_margin += max(0.0, float(data.get("margin_usdt") or 0.0))
            except Exception:
                pass
            try:
                total_pnl += float(data.get("pnl_value") or 0.0)
            except Exception:
                pass
        if intervals:
            clone["entry_tf"] = ", ".join(intervals)
            clone.setdefault("data", {}).setdefault("interval_display", intervals[0])
        else:
            allocations = clone.get("allocations") or []
            if isinstance(allocations, list):
                for alloc in allocations:
                    if not isinstance(alloc, dict):
                        continue
                    label = _clean_interval_label(alloc.get("interval_display")) or _clean_interval_label(
                        alloc.get("interval")
                    )
                    if label and label not in intervals:
                        intervals.append(label)
                if intervals:
                    clone["entry_tf"] = ", ".join(intervals)
                    clone.setdefault("data", {}).setdefault("interval_display", intervals[0])
        agg_data = dict(clone.get("data") or {})
        if total_qty > 0.0:
            agg_data["qty"] = total_qty
        if total_margin > 0.0:
            agg_data["margin_usdt"] = total_margin
        if total_pnl or total_pnl == 0.0:
            agg_data["pnl_value"] = total_pnl
        if total_margin > 0.0:
            try:
                agg_data["roi_percent"] = (total_pnl / total_margin) * 100.0
            except Exception:
                pass
        leverage_final = None
        if leverage_values:
            leverage_final = max(leverage_values)
        try:
            existing_lev = agg_data.get("leverage")
            if existing_lev is not None:
                existing_lev = int(float(existing_lev))
            if existing_lev and existing_lev > 0:
                leverage_final = existing_lev
        except Exception:
            pass
        if leverage_final:
            agg_data["leverage"] = leverage_final
            clone["leverage"] = leverage_final
        if open_time_candidates:
            try:
                earliest = min(open_time_candidates)
                open_fmt = (
                    self._format_display_time(earliest)
                    if hasattr(self, "_format_display_time")
                    else earliest.isoformat()
                )
                clone["open_time"] = open_fmt
                agg_data.setdefault("open_time", open_fmt)
            except Exception:
                pass
        clone["data"] = agg_data
        clone["_aggregated_entries"] = bucket
        aggregated.append(clone)
    closed_entries = list(closed_entries or [])

    def _close_dt(entry: dict):
        try:
            dt_val = entry.get("close_time") or (entry.get("data") or {}).get("close_time")
            return self._parse_any_datetime(dt_val)
        except Exception:
            return None

    closed_entries.sort(key=lambda e: (_close_dt(e) or datetime.min), reverse=True)
    aggregated.extend(closed_entries)
    aggregated.sort(
        key=lambda item: (item.get("symbol"), item.get("side_key"), item.get("entry_tf") or "", item.get("status") or "")
    )
    return aggregated


def _update_positions_pnl_summary(self, total_pnl: float | None, total_margin: float | None) -> None:
    label = getattr(self, "positions_pnl_label", None)
    if label is None:
        return
    if total_pnl is None:
        label.setText("Total PNL: --")
        return
    text = f"Total PNL: {total_pnl:+.2f} USDT"
    if total_margin is not None and total_margin > 0.0:
        try:
            roi = (total_pnl / total_margin) * 100.0
        except Exception:
            roi = 0.0
        text += f" ({roi:+.2f}%)"
    label.setText(text)


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


def _merge_futures_rows_into_positions_map(self, base_rows: list, positions_map: dict, alloc_map_global: dict) -> None:
    try:
        raw_entries = []
        for row in base_rows:
            try:
                raw_entry = dict(row.get("raw_position") or {})
            except Exception:
                raw_entry = {}
            sym_val = str(raw_entry.get("symbol") or row.get("symbol") or "").strip().upper()
            if not sym_val:
                continue
            if not raw_entry:
                try:
                    qty_val = float(row.get("qty") or 0.0)
                except Exception:
                    qty_val = 0.0
                side_key = str(row.get("side_key") or "").upper()
                qty_signed = -abs(qty_val) if side_key == "S" else abs(qty_val)
                try:
                    margin_balance_fallback = float(row.get("margin_balance") or 0.0)
                except Exception:
                    margin_balance_fallback = 0.0
                if margin_balance_fallback <= 0.0:
                    try:
                        margin_balance_fallback = float(row.get("margin_usdt") or 0.0) + float(row.get("pnl_value") or 0.0)
                    except Exception:
                        margin_balance_fallback = float(row.get("margin_usdt") or 0.0)
                raw_entry = {
                    "symbol": sym_val,
                    "positionAmt": qty_signed,
                    "markPrice": row.get("mark"),
                    "isolatedWallet": margin_balance_fallback if margin_balance_fallback > 0.0 else row.get("margin_usdt"),
                    "initialMargin": row.get("margin_usdt"),
                    "marginBalance": margin_balance_fallback,
                    "maintMargin": row.get("maint_margin"),
                    "marginRatio": row.get("margin_ratio"),
                    "unRealizedProfit": row.get("pnl_value"),
                    "updateTime": row.get("update_time"),
                    "leverage": row.get("leverage"),
                    "notional": row.get("size_usdt"),
                }
            else:
                raw_entry["symbol"] = sym_val
            raw_entries.append(raw_entry)

        for p in raw_entries:
            try:
                sym = str(p.get("symbol") or "").strip().upper()
                if not sym:
                    continue
                amt = float(p.get("positionAmt") or 0.0)
                if abs(amt) <= 0.0:
                    continue
                mark = float(p.get("markPrice") or 0.0)
                value = abs(amt) * mark if mark else 0.0
                side_key = "L" if amt > 0 else "S"
                entry_price = float(p.get("entryPrice") or 0.0)
                iso_wallet = float(p.get("isolatedWallet") or 0.0)
                margin_usdt = float(p.get("initialMargin") or 0.0)
                try:
                    position_initial = float(p.get("positionInitialMargin") or 0.0)
                except Exception:
                    position_initial = 0.0
                try:
                    open_order_margin = float(p.get("openOrderMargin") or p.get("openOrderInitialMargin") or 0.0)
                except Exception:
                    open_order_margin = 0.0
                pnl = float(p.get("unRealizedProfit") or 0.0)
                lev_val_raw = float(p.get("leverage") or 0.0)
                leverage = int(lev_val_raw) if lev_val_raw else None
                if margin_usdt <= 0.0 and iso_wallet > 0.0:
                    try:
                        margin_usdt = iso_wallet - pnl
                    except Exception:
                        margin_usdt = iso_wallet
                    if margin_usdt <= 0.0:
                        margin_usdt = iso_wallet
                if margin_usdt <= 0.0 and entry_price > 0.0 and leverage:
                    margin_usdt = abs(amt) * entry_price / max(leverage, 1)
                if margin_usdt <= 0.0 and leverage and leverage > 0 and value > 0.0:
                    margin_usdt = value / max(leverage, 1)
                margin_usdt = max(margin_usdt, 0.0)
                if position_initial > 0.0 or open_order_margin > 0.0:
                    margin_usdt = max(0.0, position_initial) + max(0.0, open_order_margin)
                try:
                    maint = float(p.get("maintMargin") or p.get("maintenanceMargin") or 0.0)
                except Exception:
                    maint = 0.0
                try:
                    initial_margin_val = float(p.get("initialMargin") or 0.0)
                except Exception:
                    initial_margin_val = 0.0
                try:
                    maint_rate_val = float(p.get("maintMarginRate") or p.get("maintenanceMarginRate") or 0.0)
                except Exception:
                    maint_rate_val = 0.0
                if maint <= 0.0 and maint_rate_val > 0.0 and value > 0.0:
                    maint = abs(value) * maint_rate_val
                baseline_margin = maint if maint > 0.0 else initial_margin_val
                if baseline_margin <= 0.0 and margin_usdt > 0.0 and leverage:
                    baseline_margin = margin_usdt / max(leverage, 1)
                if baseline_margin <= 0.0:
                    baseline_margin = margin_usdt
                if position_initial > 0.0:
                    baseline_margin = position_initial
                try:
                    margin_balance_val = float(p.get("marginBalance") or 0.0)
                except Exception:
                    margin_balance_val = 0.0
                if margin_balance_val <= 0.0 and iso_wallet > 0.0:
                    margin_balance_val = iso_wallet
                if margin_balance_val <= 0.0:
                    margin_balance_val = margin_usdt + pnl
                if margin_balance_val <= 0.0:
                    margin_balance_val = margin_usdt
                margin_balance_val = max(margin_balance_val, 0.0)
                try:
                    wallet_balance_val = float(p.get("walletBalance") or 0.0)
                except Exception:
                    wallet_balance_val = 0.0
                if wallet_balance_val <= 0.0:
                    wallet_balance_val = margin_balance_val if margin_balance_val > 0.0 else margin_usdt + pnl
                if wallet_balance_val <= 0.0 and iso_wallet > 0.0:
                    wallet_balance_val = iso_wallet
                wallet_balance_val = max(wallet_balance_val, 0.0)
                raw_margin_ratio_val = None
                for ratio_key in ("marginRatioRaw", "marginRatio", "margin_ratio"):
                    val = p.get(ratio_key)
                    if val in (None, "", 0, 0.0):
                        continue
                    try:
                        raw_margin_ratio_val = float(val)
                        break
                    except Exception:
                        continue
                calc_ratio = normalize_margin_ratio(p.get("marginRatioCalc")) if p.get("marginRatioCalc") is not None else 0.0
                margin_ratio = normalize_margin_ratio(raw_margin_ratio_val)
                if margin_ratio <= 0.0:
                    margin_ratio = calc_ratio
                if (margin_ratio <= 0.0 or not margin_ratio) and wallet_balance_val > 0:
                    unrealized_loss = abs(pnl) if pnl < 0 else 0.0
                    margin_ratio = ((baseline_margin + open_order_margin + unrealized_loss) / wallet_balance_val) * 100.0
                roi_pct = 0.0
                if margin_usdt > 0:
                    try:
                        roi_pct = (pnl / margin_usdt) * 100.0
                    except Exception:
                        roi_pct = 0.0
                    pnl_roi = f"{pnl:+.2f} USDT ({roi_pct:+.2f}%)"
                else:
                    pnl_roi = f"{pnl:+.2f} USDT"
                try:
                    update_time = int(float(p.get("updateTime") or p.get("update_time") or 0))
                except Exception:
                    update_time = 0
                prev_data_entry = {}
                rec_existing = positions_map.get((sym, side_key))
                if isinstance(rec_existing, dict):
                    try:
                        prev_data_entry = dict(rec_existing.get("data") or {})
                    except Exception:
                        prev_data_entry = {}
                try:
                    liquidation_price = float(
                        p.get("liquidationPrice")
                        or p.get("liqPrice")
                        or prev_data_entry.get("liquidation_price")
                        or 0.0
                    )
                except Exception:
                    liquidation_price = 0.0
                stop_loss_enabled = False
                if side_key in ("L", "S"):
                    try:
                        stop_loss_enabled = self._position_stop_loss_enabled(sym, side_key)
                    except Exception:
                        stop_loss_enabled = False
                data = {
                    "symbol": sym,
                    "qty": abs(amt),
                    "mark": mark,
                    "size_usdt": value,
                    "margin_usdt": margin_usdt,
                    "margin_balance": margin_balance_val,
                    "wallet_balance": wallet_balance_val,
                    "maint_margin": maint,
                    "open_order_margin": open_order_margin,
                    "margin_ratio": margin_ratio,
                    "margin_ratio_raw": normalize_margin_ratio(raw_margin_ratio_val),
                    "margin_ratio_calc": calc_ratio,
                    "pnl_roi": pnl_roi,
                    "pnl_value": pnl,
                    "roi_percent": roi_pct,
                    "side_key": side_key,
                    "update_time": update_time,
                    "entry_price": entry_price if entry_price > 0 else None,
                    "leverage": leverage,
                    "liquidation_price": liquidation_price if liquidation_price > 0 else None,
                    "interval": None,
                    "interval_display": None,
                    "open_time": None,
                }
                rec = positions_map.get((sym, side_key))
                prev_data_entry = {}
                prev_indicators: list[str] = []
                if rec and isinstance(rec, dict):
                    try:
                        prev_data_entry = dict(rec.get("data") or {})
                    except Exception:
                        prev_data_entry = {}
                    try:
                        prev_indicators = list(rec.get("indicators") or [])
                    except Exception:
                        prev_indicators = []
                row_triggers = _resolve_trigger_indicators_safe(
                    prev_data_entry.get("trigger_indicators"),
                    prev_data_entry.get("trigger_desc"),
                )
                if not row_triggers and prev_indicators:
                    cleaned = [str(t).strip() for t in prev_indicators if str(t).strip()]
                    if cleaned:
                        row_triggers = sorted(dict.fromkeys(cleaned))
                if rec is None:
                    rec = {
                        "symbol": sym,
                        "side_key": side_key,
                        "entry_tf": "-",
                        "open_time": "-",
                        "close_time": "-",
                        "status": "Active",
                    }
                else:
                    rec = dict(rec)
                rec["data"] = data
                rec["leverage"] = data.get("leverage")
                rec["liquidation_price"] = data.get("liquidation_price")
                rec["status"] = "Active"
                rec["close_time"] = "-"
                if (not rec.get("entry_tf") or rec["entry_tf"] == "-") and data.get("interval_display"):
                    rec["entry_tf"] = data["interval_display"]
                allocations_existing = _copy_allocations_for_key(alloc_map_global, sym, side_key)
                interval_display: dict[str, str] = {}
                interval_lookup: dict[str, str] = {}
                entry_times_map = getattr(self, "_entry_times_by_iv", {}) or {}
                intervals_from_alloc: set[str] = set()
                interval_trigger_map: dict[str, set[str]] = {}
                trigger_union: set[str] = set()
                if allocations_existing:
                    rec["allocations"] = allocations_existing
                    for alloc in allocations_existing:
                        if not isinstance(alloc, dict):
                            continue
                        iv_disp = alloc.get("interval_display") or alloc.get("interval")
                        iv_raw = alloc.get("interval")
                        status_flag = str(alloc.get("status") or "Active").strip().lower()
                        try:
                            qty_val = abs(float(alloc.get("qty") or 0.0))
                        except Exception:
                            qty_val = None
                        is_active = status_flag not in {"closed", "error"}
                        if qty_val is not None and qty_val <= 0.0:
                            qty_val = 0.0
                        if qty_val:
                            is_active = True
                        normalized_iv = ""
                        key_iv = "-"
                        if iv_disp:
                            iv_text = str(iv_disp).strip()
                            if iv_text:
                                try:
                                    canon_iv = self._canonicalize_interval(iv_text)
                                except Exception:
                                    canon_iv = None
                                normalized_iv = (canon_iv or iv_text).strip()
                                if normalized_iv:
                                    key_iv = normalized_iv.lower()
                                    if is_active:
                                        intervals_from_alloc.add(normalized_iv)
                                    if key_iv and (canon_iv or iv_text):
                                        interval_display.setdefault(key_iv, canon_iv or iv_text)
                                        lookup_val = str(iv_raw or iv_text).strip()
                                        if lookup_val:
                                            interval_lookup.setdefault(key_iv, lookup_val)
                        normalized_triggers = _resolve_trigger_indicators_safe(
                            alloc.get("trigger_indicators"),
                            alloc.get("trigger_desc"),
                        )
                        if normalized_triggers:
                            alloc["trigger_indicators"] = normalized_triggers
                        elif alloc.get("trigger_indicators"):
                            alloc.pop("trigger_indicators", None)
                        if is_active and normalized_triggers:
                            trigger_union.update(normalized_triggers)
                            interval_trigger_map.setdefault(key_iv, set()).update(normalized_triggers)
                    if not data.get("trigger_desc"):
                        for alloc in allocations_existing:
                            if not isinstance(alloc, dict):
                                continue
                            desc = alloc.get("trigger_desc")
                            if desc:
                                data["trigger_desc"] = desc
                                break
                    if trigger_union:
                        indicators_union = sorted(dict.fromkeys(trigger_union))
                        rec["indicators"] = indicators_union
                        data["trigger_indicators"] = indicators_union
                    elif row_triggers:
                        rec["indicators"] = row_triggers
                        data["trigger_indicators"] = row_triggers
                elif row_triggers:
                    rec["indicators"] = row_triggers
                    data["trigger_indicators"] = row_triggers
                if not data.get("trigger_desc") and prev_data_entry.get("trigger_desc"):
                    data["trigger_desc"] = prev_data_entry.get("trigger_desc")
                try:
                    getattr(self, "_pending_close_times", {}).pop((sym, side_key), None)
                except Exception:
                    pass
                _apply_interval_metadata_to_row(
                    self,
                    sym=sym,
                    side_key=side_key,
                    rec=rec,
                    data=data,
                    allocations_existing=allocations_existing,
                    intervals_from_alloc=intervals_from_alloc,
                    interval_display=interval_display,
                    interval_lookup=interval_lookup,
                    interval_trigger_map=interval_trigger_map,
                    trigger_union=trigger_union,
                )
                rec["stop_loss_enabled"] = stop_loss_enabled
                positions_map[(sym, side_key)] = rec
            except Exception:
                continue
    except Exception:
        pass

def _mw_render_positions_table(self):
    try:
        table = self.pos_table
        updates_prev = None
        signals_prev = None
        try:
            updates_prev = table.updatesEnabled()
            table.setUpdatesEnabled(False)
        except Exception:
            pass
        try:
            if hasattr(table, "blockSignals"):
                signals_prev = table.blockSignals(True)
        except Exception:
            pass
        open_records = getattr(self, "_open_position_records", {}) or {}
        closed_records = getattr(self, "_closed_position_records", []) or []
        view_mode = getattr(self, "_positions_view_mode", "cumulative")
        try:
            vbar = self.pos_table.verticalScrollBar()
            vbar_val = vbar.value()
        except Exception:
            vbar = None
            vbar_val = None
        try:
            hbar = self.pos_table.horizontalScrollBar()
            hbar_val = hbar.value()
        except Exception:
            hbar = None
            hbar_val = None
        prev_snapshot = getattr(self, "_last_positions_table_snapshot", None)
        if view_mode == "per_trade":
            display_records = self._positions_records_per_trade(open_records, closed_records)
        else:
            display_records = _mw_positions_records_cumulative(
                self,
                sorted(
                    open_records.values(),
                    key=lambda d: (d['symbol'], d.get('side_key'), d.get('entry_tf')),
                ),
                closed_records,
            )
        display_records = [rec for rec in (display_records or []) if isinstance(rec, dict)]
        snapshot_digest: list[tuple] = []
        acct_type = str(getattr(self, "_positions_account_type", "") or "").upper()
        acct_is_futures = getattr(self, "_positions_account_is_futures", None)
        if acct_is_futures is None:
            acct_is_futures = "FUT" in acct_type
        live_value_cache = getattr(self, "_live_indicator_cache", None)
        if not isinstance(live_value_cache, dict):
            live_value_cache = {}
            self._live_indicator_cache = live_value_cache
        now_ts = time.monotonic()
        ttl = float(getattr(self, "_live_indicator_cache_ttl", 8.0) or 8.0)
        cleanup_interval = max(ttl * 3.0, 30.0)
        last_cleanup = float(getattr(self, "_live_indicator_cache_last_cleanup", 0.0) or 0.0)
        if now_ts - last_cleanup >= cleanup_interval:
            cutoff = now_ts - max(ttl * 6.0, 60.0)
            stale_keys: list[tuple[str, str]] = []
            for key, entry in list(live_value_cache.items()):
                try:
                    entry_ts = float(entry.get("df_ts") or entry.get("ts") or 0.0)
                except Exception:
                    entry_ts = 0.0
                if entry_ts and entry_ts < cutoff:
                    stale_keys.append(key)
            for key in stale_keys:
                live_value_cache.pop(key, None)
            self._live_indicator_cache_last_cleanup = now_ts
        for rec in display_records:
            data = rec.get('data') or {}
            status_flag = str(rec.get('status') or data.get('status') or "").strip().lower()
            record_is_closed = status_flag in _CLOSED_RECORD_STATES
            indicators_list = tuple(
                _collect_record_indicator_keys(
                    rec,
                    include_inactive_allocs=record_is_closed,
                    include_allocation_scope=view_mode != "per_trade",
                )
            )
            interval_hint = (
                rec.get('entry_tf')
                or data.get('interval_display')
                or data.get('interval')
                or "-"
            )
            indicator_value_entries, interval_map = _collect_indicator_value_strings(rec, interval_hint)
            rec["_indicator_value_entries"] = indicator_value_entries
            rec["_indicator_interval_map"] = interval_map
            sym_digest = str(rec.get('symbol') or data.get('symbol') or "").strip().upper()
            if record_is_closed:
                current_live_entries = list(rec.get("_current_indicator_values") or [])
            else:
                current_live_entries = _collect_current_indicator_live_strings(
                    self,
                    sym_digest,
                    indicators_list,
                    live_value_cache,
                    interval_map,
                    interval_hint,
                )
            if view_mode == "per_trade":
                filtered_values = _filter_indicator_entries_for_interval(
                    indicator_value_entries,
                    interval_hint,
                    include_non_matching=False,
                )
                if filtered_values:
                    allowed = {_indicator_entry_signature(entry) for entry in filtered_values}
                    current_live_entries = [
                        entry
                        for entry in (current_live_entries or [])
                        if _indicator_entry_signature(entry) in allowed
                    ]
            if current_live_entries:
                current_live_entries = _dedupe_indicator_entries_normalized(current_live_entries)
            rec["_current_indicator_values"] = current_live_entries
            indicator_snapshot = tuple(indicator_value_entries or [])
            interval_snapshot = tuple(
                (key, tuple(values))
                for key, values in (interval_map or {}).items()
            )
            current_live_tuple = tuple(current_live_entries or [])
            snapshot_digest.append(
                (
                    str(rec.get('symbol') or "").upper(),
                    str(rec.get('side_key') or "").upper(),
                    str(rec.get('entry_tf') or ""),
                    indicators_list,
                    indicator_snapshot,
                    interval_snapshot,
                    current_live_tuple,
                    float(data.get('qty') or 0.0),
                    float(data.get('margin_usdt') or 0.0),
                    float(data.get('pnl_value') or 0.0),
                    str(rec.get('status') or ""),
                )
            )
        snapshot_key = (view_mode, tuple(snapshot_digest))
        if prev_snapshot == snapshot_key and view_mode == "per_trade":
            totals = getattr(self, "_last_positions_table_totals", None)
            if isinstance(totals, tuple) and len(totals) == 2:
                self._update_positions_pnl_summary(*totals)
                self._update_global_pnl_display(*self._compute_global_pnl_totals())
            return
        header = self.pos_table.horizontalHeader()
        try:
            sort_column = header.sortIndicatorSection()
            sort_order = header.sortIndicatorOrder()
            if sort_column is None or sort_column < 0:
                sort_column = 0
                sort_order = QtCore.Qt.SortOrder.AscendingOrder
        except Exception:
            sort_column = 0
            sort_order = QtCore.Qt.SortOrder.AscendingOrder
        self.pos_table.setSortingEnabled(False)
        self.pos_table.setRowCount(0)
        total_pnl = 0.0
        total_margin = 0.0
        pnl_has_value = False
        aggregated_keys: set[tuple[str, tuple[str, ...]] | str] = set()
        for rec in display_records:
            try:
                data = rec.get('data', {}) or {}
                sym = str(rec.get('symbol') or data.get('symbol') or "").strip().upper()
                if not sym:
                    sym = "-"
                side_key = str(rec.get('side_key') or data.get('side_key') or "").upper()
                interval = rec.get('entry_tf') or data.get('interval_display') or "-"
                row = self.pos_table.rowCount()
                self.pos_table.insertRow(row)

                qty_show = float(data.get('qty') or 0.0)
                mark = float(data.get('mark') or 0.0)
                size_usdt = float(data.get('size_usdt') or (qty_show * mark))
                mr = normalize_margin_ratio(data.get('margin_ratio'))
                margin_usdt = float(data.get('margin_usdt') or 0.0)
                pnl_roi = data.get('pnl_roi')
                pnl_raw_value = data.get('pnl_value')
                try:
                    pnl_value = float(pnl_raw_value or 0.0)
                except Exception:
                    pnl_value = 0.0
                side_text = 'Long' if side_key == 'L' else ('Short' if side_key == 'S' else 'Spot')
                open_time = data.get('open_time') or rec.get('open_time') or '-'
                status_txt = rec.get('status', 'Active')
                status_lower = str(status_txt).strip().lower()
                is_closed_like = status_lower in _CLOSED_RECORD_STATES
                close_time = rec.get('close_time') if is_closed_like else '-'
                stop_loss_enabled = bool(rec.get('stop_loss_enabled'))
                stop_loss_text = "Yes" if stop_loss_enabled else "No"

                aggregate_key = str(rec.get("_aggregate_key") or rec.get("ledger_id") or "")
                aggregate_primary = bool(rec.get("_aggregate_is_primary", True))
                should_aggregate = True
                if aggregate_key:
                    indicator_signature = tuple(_normalize_indicator_values(rec.get("indicators")))
                    interval_signature = str(rec.get("entry_tf") or "").strip().lower()
                    if indicator_signature:
                        key_entry = (aggregate_key, interval_signature, indicator_signature)
                    else:
                        key_entry = (aggregate_key, interval_signature)
                    if aggregate_primary:
                        if key_entry in aggregated_keys:
                            should_aggregate = False
                        else:
                            aggregated_keys.add(key_entry)
                    else:
                        should_aggregate = False

                raw_position = data.get("raw_position")
                if not isinstance(raw_position, dict):
                    raw_position = rec.get("raw_position") if isinstance(rec.get("raw_position"), dict) else None
                leverage_val = 0
                leverage_candidates = [
                    data.get("leverage"),
                    rec.get("leverage"),
                    (raw_position or {}).get("leverage"),
                ]
                for candidate in leverage_candidates:
                    try:
                        if candidate is None:
                            continue
                        val = int(round(float(candidate)))
                        if val > 0:
                            leverage_val = val
                            break
                    except Exception:
                        continue
                contract_label_raw = (
                    data.get("contract_type")
                    or data.get("contractType")
                    or data.get("instrument_type")
                    or data.get("instrumentType")
                    or (raw_position or {}).get("contractType")
                    or (raw_position or {}).get("contract_type")
                    or ""
                )
                contract_label = str(contract_label_raw).strip()
                if not contract_label:
                    if side_key in ("L", "S") and acct_is_futures:
                        contract_label = "Perp"
                    elif side_key == "SPOT":
                        contract_label = "Spot"
                elif side_key == "SPOT":
                    contract_label = "Spot"
                contract_display = ""
                if contract_label:
                    if contract_label.upper().startswith("PERP"):
                        contract_display = "Perp"
                    else:
                        contract_display = contract_label.title()
                info_parts: list[str] = []
                if contract_display:
                    info_parts.append(contract_display)
                if leverage_val > 0:
                    info_parts.append(f"{leverage_val}x")
                if info_parts:
                    sym_display = f"{sym}\n{'    '.join(info_parts)}"
                else:
                    sym_display = sym
                self.pos_table.setItem(row, 0, QtWidgets.QTableWidgetItem(sym_display))

                size_item = _NumericItem(f"{size_usdt:.8f}", size_usdt)
                self.pos_table.setItem(row, 1, size_item)

                mark_item = _NumericItem(f"{mark:.8f}" if mark else "-", mark)
                self.pos_table.setItem(row, 2, mark_item)

                mr_display = f"{mr:.2f}%" if mr > 0 else "-"
                mr_item = _NumericItem(mr_display, mr)
                self.pos_table.setItem(row, 3, mr_item)

                liq_price = 0.0
                liq_candidates = [
                    data.get("liquidation_price"),
                    data.get("liquidationPrice"),
                    data.get("liq_price"),
                    data.get("liqPrice"),
                    rec.get("liquidation_price"),
                    rec.get("liquidationPrice"),
                    (raw_position or {}).get("liquidationPrice"),
                    (raw_position or {}).get("liqPrice"),
                ]
                for candidate in liq_candidates:
                    try:
                        if candidate is None or candidate == "":
                            continue
                        value = float(candidate)
                        if value > 0.0:
                            liq_price = value
                            break
                    except Exception:
                        continue
                liq_text = f"{liq_price:.6f}" if liq_price > 0 else "-"
                liq_item = _NumericItem(liq_text if liq_price > 0 else "-", liq_price)
                self.pos_table.setItem(row, 4, liq_item)

                margin_item = _NumericItem(f"{margin_usdt:.2f} USDT" if margin_usdt else "-", margin_usdt)
                self.pos_table.setItem(row, 5, margin_item)
                if margin_usdt > 0.0 and should_aggregate:
                    total_margin += margin_usdt

                qty_margin_item = _NumericItem(f"{qty_show:.6f}", qty_show)
                self.pos_table.setItem(row, 6, qty_margin_item)

                pnl_item = _NumericItem(str(pnl_roi or "-"), pnl_value)
                self.pos_table.setItem(row, 7, pnl_item)
                added_to_total = False
                if pnl_raw_value is not None and should_aggregate:
                    total_pnl += pnl_value
                    pnl_has_value = True
                    added_to_total = True
                pnl_valid = (pnl_raw_value is not None) or (abs(pnl_value) > 0.0)
                if not pnl_valid and status_lower == "closed":
                    pnl_valid = True
                if status_lower == "closed" and not added_to_total and pnl_valid and should_aggregate:
                    total_pnl += pnl_value
                    pnl_has_value = True

                self.pos_table.setItem(row, 8, QtWidgets.QTableWidgetItem(interval or '-'))
                source_entries = rec.get("_aggregated_entries") or [rec]
                indicators_list: list[str] = []
                indicator_values_entries: list[str] = []
                interval_map: dict[str, list[str]] = {}
                for entry in source_entries:
                    entry_inds = _collect_record_indicator_keys(
                        entry,
                        include_inactive_allocs=is_closed_like,
                        include_allocation_scope=view_mode != "per_trade",
                    )
                    for token in entry_inds:
                        if token and token not in indicators_list:
                            indicators_list.append(token)
                    cached_values = entry.get("_indicator_value_entries")
                    cached_map = entry.get("_indicator_interval_map")
                    interval_hint_entry = (
                        entry.get("entry_tf")
                        or (entry.get("data") or {}).get("interval_display")
                        or interval
                    )
                    if cached_values is None or cached_map is None:
                        cached_values, cached_map = _collect_indicator_value_strings(entry, interval_hint_entry)
                        entry["_indicator_value_entries"] = cached_values
                        entry["_indicator_interval_map"] = cached_map
                    for value_entry in cached_values or []:
                        if value_entry not in indicator_values_entries:
                            indicator_values_entries.append(value_entry)
                    for key, slots in (cached_map or {}).items():
                        bucket = interval_map.setdefault(key, [])
                        for slot in slots:
                            if slot not in bucket:
                                bucket.append(slot)
                rec["_indicator_value_entries"] = indicator_values_entries
                rec["_indicator_interval_map"] = interval_map
                active_indicator_keys_ordered = list((interval_map or {}).keys())
                display_list: list[str] = list(indicators_list or [])
                if active_indicator_keys_ordered:
                    filtered = [ind for ind in display_list if ind.lower() in active_indicator_keys_ordered]
                    display_list = filtered if filtered else active_indicator_keys_ordered
                indicators_list = display_list
                indicators_display = _format_indicator_list(display_list) if display_list else '-'
                self.pos_table.setItem(row, 9, QtWidgets.QTableWidgetItem(indicators_display))
                interval_for_display = interval
                strict_interval_values = getattr(self, "_positions_view_mode", "cumulative") == "per_trade"
                filtered_indicator_values = _filter_indicator_entries_for_interval(
                    indicator_values_entries,
                    interval_for_display,
                    include_non_matching=not strict_interval_values,
                )
                if filtered_indicator_values:
                    filtered_indicator_values = list(dict.fromkeys(filtered_indicator_values))
                indicator_values_display = "\n".join(filtered_indicator_values) if filtered_indicator_values else "-"
                self.pos_table.setItem(row, POS_TRIGGERED_VALUE_COLUMN, QtWidgets.QTableWidgetItem(indicator_values_display))
                live_values_entries = rec.get("_current_indicator_values")
                if live_values_entries is None:
                    if not is_closed_like:
                        live_indicator_keys = indicators_list
                        live_interval_map = interval_map
                        if strict_interval_values and filtered_indicator_values:
                            label_map = {
                                _indicator_short_label(key).strip().lower(): key
                                for key in indicators_list
                            }
                            restricted_keys: list[str] = []
                            restricted_map: dict[str, list[str]] = {}
                            for entry in filtered_indicator_values:
                                label_part, interval_part = _indicator_entry_signature(entry)
                                mapped_key = label_map.get(label_part)
                                if not mapped_key:
                                    continue
                                if mapped_key not in restricted_keys:
                                    restricted_keys.append(mapped_key)
                                if interval_part:
                                    slots = restricted_map.setdefault(mapped_key.lower(), [])
                                    interval_clean = interval_part.strip().upper()
                                    if interval_clean and interval_clean not in slots:
                                        slots.append(interval_clean)
                            if restricted_keys:
                                live_indicator_keys = restricted_keys
                                live_interval_map = restricted_map
                        live_values_entries = _collect_current_indicator_live_strings(
                            self,
                            sym,
                            live_indicator_keys,
                            live_value_cache,
                            live_interval_map,
                            interval,
                        )
                        rec["_current_indicator_values"] = live_values_entries
                    else:
                        live_values_entries = []
                if live_values_entries:
                    live_values_entries = _dedupe_indicator_entries_normalized(live_values_entries)
                    rec["_current_indicator_values"] = live_values_entries
                current_values_display = "\n".join(live_values_entries) if live_values_entries else "-"
                self.pos_table.setItem(row, POS_CURRENT_VALUE_COLUMN, QtWidgets.QTableWidgetItem(current_values_display))
                # Keep "Triggered Indicator Value" strictly historical: never backfill from live values.
                self.pos_table.setItem(row, 12, QtWidgets.QTableWidgetItem(side_text))
                self.pos_table.setItem(row, 13, QtWidgets.QTableWidgetItem(str(open_time or '-')))
                self.pos_table.setItem(row, 14, QtWidgets.QTableWidgetItem(str(close_time or '-')))
                self.pos_table.setItem(row, POS_STOP_LOSS_COLUMN, QtWidgets.QTableWidgetItem(stop_loss_text))
                self.pos_table.setItem(row, POS_STATUS_COLUMN, QtWidgets.QTableWidgetItem(status_txt))
                btn_interval = interval if interval != "-" else None
                btn = self._make_close_btn(sym, side_key, btn_interval, qty_show)
                if str(status_txt).strip().lower() != 'active':
                    btn.setEnabled(False)
                self.pos_table.setCellWidget(row, POS_CLOSE_COLUMN, btn)
            except Exception:
                pass
        try:
            if coerce_bool(self.config.get("positions_auto_resize_rows", True), True):
                self.pos_table.resizeRowsToContents()
        except Exception:
            pass
        try:
            if coerce_bool(self.config.get("positions_auto_resize_columns", True), True):
                self.pos_table.resizeColumnsToContents()
        except Exception:
            pass
        summary_margin = total_margin if total_margin > 0.0 else None
        self._update_positions_pnl_summary(total_pnl if pnl_has_value else None, summary_margin)
        self._update_global_pnl_display(*self._compute_global_pnl_totals())
        try:
            if (
                getattr(self, "chart_enabled", False)
                and getattr(self, "chart_auto_follow", False)
                and not getattr(self, "_chart_manual_override", False)
                and self._is_chart_visible()
            ):
                self._sync_chart_to_active_positions()
        except Exception:
            pass
    except Exception as exc:
        try:
            self.log(f"Positions table update failed: {exc}")
        except Exception:
            pass
    finally:
        def _restore_scrollbar(bar, value):
            try:
                if bar is None or value is None:
                    return
                value_clamped = max(bar.minimum(), min(value, bar.maximum()))
                bar.setValue(value_clamped)
            except Exception:
                pass
        try:
            self.pos_table.setSortingEnabled(True)
            if sort_column is not None and sort_column >= 0:
                self.pos_table.sortItems(sort_column, sort_order)
        except Exception:
            pass
        try:
            if vbar is not None and vbar_val is not None:
                QtCore.QTimer.singleShot(0, lambda: _restore_scrollbar(vbar, vbar_val))
        except Exception:
            pass
        try:
            if hbar is not None and hbar_val is not None:
                QtCore.QTimer.singleShot(0, lambda: _restore_scrollbar(hbar, hbar_val))
        except Exception:
            pass
        try:
            self._last_positions_table_snapshot = snapshot_key
            self._last_positions_table_totals = (total_pnl if pnl_has_value else None, summary_margin)
        except Exception:
            pass
        try:
            if hasattr(self.pos_table, "blockSignals"):
                self.pos_table.blockSignals(signals_prev if signals_prev is not None else False)
        except Exception:
            pass
        try:
            if updates_prev is not None:
                self.pos_table.setUpdatesEnabled(updates_prev)
        except Exception:
            pass




def _gui_on_positions_ready(self, rows: list, acct: str):
    try:
        try:
            rows = sorted(rows, key=lambda r: (str(r.get("symbol") or ""), str(r.get("side_key") or "")))
        except Exception:
            rows = rows or []
        base_rows = rows or []
        alloc_map_global = getattr(self, "_entry_allocations", {}) or {}
        prev_records = getattr(self, "_open_position_records", {}) or {}
        if not isinstance(prev_records, dict):
            prev_records = {}
        positions_map = _seed_positions_map_from_rows(self, base_rows, alloc_map_global, prev_records)
        acct_upper = str(acct or "").upper()
        self._positions_account_type = acct_upper
        self._positions_account_is_futures = acct_upper.startswith("FUT")
        if acct_upper.startswith("FUT"):
            _merge_futures_rows_into_positions_map(self, base_rows, positions_map, alloc_map_global)
        self._update_position_history(positions_map)
        self._render_positions_table()
    except Exception as e:
        self.log(f"Positions render failed: {e}")

def _mw_positions_records_per_trade(self, open_records: dict, closed_records: list) -> list:
    raw_records: list[dict] = []
    metadata = getattr(self, "_engine_indicator_map", {}) or {}
    meta_map: dict[tuple[str, str], list[dict]] = {}
    for meta in metadata.values():
        if not isinstance(meta, dict):
            continue
        sym = str(meta.get("symbol") or "").strip().upper()
        if not sym:
            continue
        interval = str(meta.get("interval") or "").strip()
        side_cfg = str(meta.get("side") or "BOTH").upper()
        stop_enabled = bool(meta.get("stop_loss_enabled"))
        indicators = list(meta.get("indicators") or [])
        sides = []
        if side_cfg == "BUY":
            sides = ["L"]
        elif side_cfg == "SELL":
            sides = ["S"]
        else:
            sides = ["L", "S"]
        for side in sides:
            meta_map.setdefault((sym, side), []).append(
                {
                    "interval": interval,
                    "indicators": indicators,
                    "stop_loss_enabled": stop_enabled,
                }
            )

    def _normalize_interval(value):
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

    def _collect_allocations(rec: dict) -> list[dict]:
        allocs = rec.get("allocations") or []
        if isinstance(allocs, dict):
            allocs = list(allocs.values())
        if not isinstance(allocs, list):
            return []
        out: list[dict] = []
        for payload in allocs:
            if not isinstance(payload, dict):
                continue
            entry = copy.deepcopy(payload)
            interval = entry.get("interval")
            if interval is None and entry.get("interval_display"):
                interval = entry.get("interval_display")
            entry["interval"] = interval
            triggers_any = entry.get("trigger_indicators")
            if isinstance(triggers_any, dict):
                merged = []
                for value in triggers_any.values():
                    if isinstance(value, (list, tuple, set)):
                        merged.extend([str(v).strip() for v in value if str(v).strip()])
                    elif isinstance(value, str) and value.strip():
                        merged.append(value.strip())
                entry["trigger_indicators"] = merged or None
            out.append(entry)
        unique: list[dict] = []
        seen: dict[tuple, dict] = {}
        for entry in out:
            indicators_tuple = tuple(sorted(str(v).strip().lower() for v in (entry.get("trigger_indicators") or []) if str(v).strip()))
            key = (
                str(entry.get("ledger_id") or ""),
                str(entry.get("interval") or "").strip().lower(),
                indicators_tuple,
            )
            existing = seen.get(key)
            if existing:
                try:
                    existing["margin_usdt"] = max(float(existing.get("margin_usdt") or 0.0), float(entry.get("margin_usdt") or 0.0))
                    existing["qty"] = max(float(existing.get("qty") or 0.0), float(entry.get("qty") or 0.0))
                    existing["notional"] = max(float(existing.get("notional") or 0.0), float(entry.get("notional") or 0.0))
                except Exception:
                    pass
                continue
            if indicators_tuple:
                entry["trigger_indicators"] = list(indicators_tuple)
            seen[key] = entry
            unique.append(entry)
        return unique

    def _compute_trade_data(base_data: dict, allocation: dict | None, side_key: str, status: str) -> dict:
        data = dict(base_data)
        base_qty = float(base_data.get("qty") or 0.0)
        base_margin = float(base_data.get("margin_usdt") or 0.0)
        base_pnl = float(base_data.get("pnl_value") or 0.0)
        base_roi = float(base_data.get("roi_percent") or 0.0)
        base_size = float(base_data.get("size_usdt") or 0.0)
        mark = float(base_data.get("mark") or 0.0)
        entry_price = float(base_data.get("entry_price") or 0.0)
        leverage = int(base_data.get("leverage") or 0) if base_data.get("leverage") else 0
        base_margin_ratio = normalize_margin_ratio(base_data.get("margin_ratio"))
        base_margin_balance = float(base_data.get("margin_balance") or 0.0)
        base_maint_margin = float(base_data.get("maint_margin") or 0.0)

        qty = base_qty
        margin = base_margin
        notional = base_size
        status_lower = str(status or "").strip().lower()
        pnl = base_pnl
        margin_ratio = 0.0
        margin_balance_val = 0.0
        maint_margin_val = 0.0
        base_liq_price = None

        def _extract_liq_value(candidate):
            try:
                if candidate is None or candidate == "":
                    return None
                value = float(candidate)
                return value if value > 0.0 else None
            except Exception:
                return None

        for cand in (
            base_data.get("liquidation_price"),
            base_data.get("liquidationPrice"),
            base_data.get("liq_price"),
            base_data.get("liqPrice"),
        ):
            found = _extract_liq_value(cand)
            if found:
                base_liq_price = found
                break
        if not base_liq_price:
            raw_base = base_data.get("raw_position") if isinstance(base_data.get("raw_position"), dict) else None
            if raw_base:
                for cand in (
                    raw_base.get("liquidationPrice"),
                    raw_base.get("liqPrice"),
                ):
                    found = _extract_liq_value(cand)
                    if found:
                        base_liq_price = found
                        break

        if allocation:
            try:
                qty = abs(float(allocation.get("qty") or 0.0))
            except Exception:
                qty = max(base_qty, 0.0)
            try:
                entry_price_alloc = float(allocation.get("entry_price") or 0.0)
                if entry_price_alloc > 0:
                    entry_price = entry_price_alloc
            except Exception:
                pass
            try:
                leverage_alloc = int(allocation.get("leverage") or 0)
                if leverage_alloc:
                    leverage = leverage_alloc
            except Exception:
                pass
            try:
                margin = float(allocation.get("margin_usdt") or 0.0)
            except Exception:
                margin = 0.0
            try:
                notional = float(allocation.get("notional") or 0.0)
            except Exception:
                notional = 0.0
            if base_liq_price is None:
                for cand in (
                    allocation.get("liquidation_price"),
                    allocation.get("liquidationPrice"),
                    allocation.get("liq_price"),
                    allocation.get("liqPrice"),
                ):
                    found = _extract_liq_value(cand)
                    if found:
                        base_liq_price = found
                        break
            alloc_pnl = allocation.get("pnl_value")
            if alloc_pnl is not None:
                try:
                    pnl = float(alloc_pnl)
                except Exception:
                    pnl = base_pnl
            if allocation.get("status"):
                status_lower = str(allocation.get("status")).strip().lower()
        allocation_data = allocation if isinstance(allocation, dict) else {}
        margin_ratio = normalize_margin_ratio(allocation_data.get("margin_ratio"))
        try:
            margin_balance_val = float(allocation_data.get("margin_balance") or 0.0)
        except Exception:
            margin_balance_val = 0.0
        try:
            maint_margin_val = float(allocation_data.get("maint_margin") or 0.0)
        except Exception:
            maint_margin_val = 0.0

        qty = max(qty, 0.0)
        if notional <= 0:
            if entry_price > 0 and qty > 0:
                notional = entry_price * qty
            elif mark > 0 and qty > 0:
                notional = mark * qty
            elif base_size > 0 and base_qty > 0:
                notional = base_size * (qty / base_qty)
            else:
                notional = 0.0

        if margin <= 0:
            if leverage and leverage > 0 and entry_price > 0 and qty > 0:
                margin = (entry_price * qty) / leverage
            elif base_margin > 0 and base_qty > 0:
                margin = base_margin * (qty / base_qty)
            else:
                margin = 0.0
        margin = max(margin, 0.0)

        if status_lower == "active":
            if allocation is None or allocation.get("pnl_value") is None:
                direction = 1.0 if side_key == "L" else -1.0 if side_key == "S" else 0.0
                if direction != 0.0 and entry_price > 0 and mark > 0 and qty > 0:
                    pnl = direction * (mark - entry_price) * qty
                elif base_pnl and base_qty > 0:
                    pnl = base_pnl * (qty / base_qty)
        else:
            if allocation is None or allocation.get("pnl_value") is None:
                if base_pnl and base_qty > 0:
                    pnl = base_pnl * (qty / base_qty)
                else:
                    pnl = base_pnl

        roi_percent = (pnl / margin * 100.0) if margin > 0 else base_roi
        pnl_roi = f"{pnl:+.2f} USDT ({roi_percent:+.2f}%)" if margin > 0 else f"{pnl:+.2f} USDT"

        raw_position = base_data.get("raw_position") if isinstance(base_data.get("raw_position"), dict) else None
        if margin_ratio <= 0.0:
            margin_ratio = base_margin_ratio
        if margin_balance_val <= 0.0:
            margin_balance_val = base_margin_balance
        if maint_margin_val <= 0.0:
            maint_margin_val = base_maint_margin
        if margin_ratio <= 0.0 and raw_position is not None:
            snap_margin, snap_balance, snap_maint, snap_unreal_loss = _derive_margin_snapshot(
                raw_position,
                qty_hint=qty if qty > 0 else base_qty,
                entry_price_hint=entry_price if entry_price > 0 else base_data.get("entry_price") or 0.0,
            )
            if margin <= 0.0 and snap_margin > 0.0:
                margin = snap_margin
            if margin_balance_val <= 0.0 and snap_balance > 0.0:
                margin_balance_val = snap_balance
            if maint_margin_val <= 0.0 and snap_maint > 0.0:
                maint_margin_val = snap_maint
            if margin_ratio <= 0.0 and snap_balance > 0.0 and snap_maint > 0.0:
                margin_ratio = ((snap_maint + snap_unreal_loss) / snap_balance) * 100.0
        if margin_balance_val <= 0.0:
            margin_balance_val = margin + max(pnl, 0.0)
        margin_balance_val = max(margin_balance_val, 0.0)
        if margin_ratio <= 0.0 and margin_balance_val > 0 and maint_margin_val > 0.0:
            unrealized_loss = max(0.0, -pnl) if status_lower == "active" else 0.0
            margin_ratio = ((maint_margin_val + unrealized_loss) / margin_balance_val) * 100.0

        data.update({
            "qty": qty,
            "margin_usdt": margin,
            "pnl_value": pnl,
            "roi_percent": roi_percent,
            "pnl_roi": pnl_roi,
            "size_usdt": max(notional, 0.0),
            "margin_balance": max(margin_balance_val, 0.0),
            "maint_margin": max(0.0, maint_margin_val),
            "margin_ratio": max(margin_ratio, 0.0),
        })
        trigger_inds = []
        if allocation and isinstance(allocation.get("trigger_indicators"), (list, tuple, set)):
            trigger_inds = [str(ind).strip() for ind in allocation.get("trigger_indicators") if str(ind).strip()]
        elif isinstance(base_data.get("trigger_indicators"), (list, tuple, set)):
            trigger_inds = [str(ind).strip() for ind in base_data.get("trigger_indicators") if str(ind).strip()]
        if trigger_inds:
            trigger_inds = list(dict.fromkeys(trigger_inds))
            data["trigger_indicators"] = trigger_inds
        if entry_price > 0:
            data["entry_price"] = entry_price
        if leverage:
            data["leverage"] = leverage
        if base_liq_price:
            data["liquidation_price"] = base_liq_price
        if allocation and isinstance(allocation, dict) and allocation.get("trigger_desc"):
            data["trigger_desc"] = allocation.get("trigger_desc")
        elif base_data.get("trigger_desc") and not data.get("trigger_desc"):
            data["trigger_desc"] = base_data.get("trigger_desc")
        return data

    def _emit_entries(base_rec: dict, sym: str, side_key: str, meta_items: list[dict | None]) -> None:
        allocations = _collect_allocations(base_rec)
        base_data = dict(base_rec.get("data") or {})
        status_text = str(base_rec.get("status") or "Active")
        stop_loss_flag = bool(base_rec.get("stop_loss_enabled"))
        default_open = base_rec.get("open_time") or "-"
        default_close = base_rec.get("close_time") or "-"
        meta_items = meta_items or [None]

        def _interval_from_meta(meta: dict | None, fallback: str | None = None) -> str:
            if isinstance(meta, dict):
                label = meta.get("interval") or meta.get("interval_display")
                if label:
                    return str(label)
            if fallback:
                return str(fallback)
            return "-"

        def _build_entry(allocation: dict | None, interval_hint: str | None, meta: dict | None = None) -> None:
            entry = copy.deepcopy(base_rec)
            interval_label = interval_hint or entry.get("entry_tf") or "-"
            entry["entry_tf"] = interval_label or "-"
            if isinstance(allocation, dict):
                try:
                    entry["allocations"] = [copy.deepcopy(allocation)]
                except Exception:
                    entry["allocations"] = [dict(allocation)]
            else:
                entry["allocations"] = []
            alloc_status = str((allocation or {}).get("status") or status_text)
            entry["status"] = alloc_status
            if isinstance(meta, dict) and meta.get("stop_loss_enabled") is not None:
                entry["stop_loss_enabled"] = bool(meta.get("stop_loss_enabled"))
            else:
                entry["stop_loss_enabled"] = bool((allocation or {}).get("stop_loss_enabled", stop_loss_flag))
            alloc_data = _compute_trade_data(base_data, allocation, side_key, alloc_status)
            entry["data"] = alloc_data
            entry["leverage"] = alloc_data.get("leverage")
            entry["liquidation_price"] = alloc_data.get("liquidation_price")
            indicators = allocation.get("trigger_indicators") if isinstance(allocation, dict) else None
            if isinstance(indicators, (list, tuple, set)):
                entry["indicators"] = list(dict.fromkeys(str(t).strip() for t in indicators if str(t).strip()))
            elif isinstance(meta, dict):
                meta_inds = meta.get("indicators")
                if meta_inds:
                    entry["indicators"] = list(meta_inds)
            trig_inds = alloc_data.get("trigger_indicators")
            if trig_inds:
                entry["indicators"] = list(dict.fromkeys(trig_inds))
            open_hint = None
            close_hint = None
            if isinstance(allocation, dict):
                open_hint = allocation.get("open_time")
                close_hint = allocation.get("close_time")
            entry["open_time"] = open_hint or default_open
            entry["close_time"] = close_hint or default_close
            entry["stop_loss_enabled"] = bool(entry.get("stop_loss_enabled"))
            normalized_inds = _normalize_indicator_values(
                entry.get("indicators") or alloc_data.get("trigger_indicators")
            )
            if normalized_inds:
                entry["indicators"] = normalized_inds
                alloc_data["trigger_indicators"] = normalized_inds
            else:
                entry.pop("indicators", None)
                alloc_data.pop("trigger_indicators", None)

            aggregate_key = None
            if isinstance(allocation, dict):
                aggregate_key = (
                    allocation.get("trade_id")
                    or allocation.get("client_order_id")
                    or allocation.get("order_id")
                    or allocation.get("ledger_id")
                )
            if not aggregate_key:
                aggregate_key = (
                    entry.get("trade_id")
                    or entry.get("client_order_id")
                    or entry.get("order_id")
                    or entry.get("ledger_id")
                    or base_rec.get("ledger_id")
                )
            if not aggregate_key:
                aggregate_key = f"{sym}|{side_key}|{interval_label}|{entry.get('open_time')}"

            indicator_source = (
                alloc_data.get("trigger_indicators")
                or entry.get("indicators")
                or base_data.get("trigger_indicators")
            )
            indicator_values = _normalize_indicator_values(indicator_source)
            if indicator_values:
                for idx, indicator_name in enumerate(indicator_values):
                    clone = copy.deepcopy(entry)
                    clone_indicators = [indicator_name]
                    clone["indicators"] = clone_indicators
                    clone_data = dict(clone.get("data") or {})
                    clone_data["trigger_indicators"] = clone_indicators
                    clone["data"] = clone_data
                    clone_allocs: list[dict] = []
                    for alloc_payload in (clone.get("allocations") or []):
                        if not isinstance(alloc_payload, dict):
                            continue
                        alloc_clone = dict(alloc_payload)
                        alloc_clone["trigger_indicators"] = clone_indicators
                        clone_allocs.append(alloc_clone)
                    clone["allocations"] = clone_allocs
                    clone["_aggregate_key"] = f"{aggregate_key}|{indicator_name.lower()}"
                    clone["_aggregate_is_primary"] = True
                    raw_records.append(clone)
                return
            entry["indicators"] = []
            entry_data = dict(entry.get("data") or {})
            entry_data["trigger_indicators"] = []
            entry["data"] = entry_data
            entry["_aggregate_key"] = aggregate_key
            entry["_aggregate_is_primary"] = True
            raw_records.append(entry)

        if allocations:
            for alloc in allocations:
                interval_label = alloc.get("interval_display") or alloc.get("interval")
                norm_iv = _normalize_interval(interval_label)
                matching_meta = None
                if norm_iv is not None:
                    for meta in meta_items:
                        if isinstance(meta, dict) and _normalize_interval(meta.get("interval")) == norm_iv:
                            matching_meta = meta
                            break
                if matching_meta is None:
                    for meta in meta_items:
                        if meta is None:
                            matching_meta = None
                            break
                _build_entry(alloc, interval_label or norm_iv, matching_meta)
        else:
            # Fallback: synthesise entries based on metadata or the base record itself.
            fallback_intervals: list[str] = []
            for meta in meta_items:
                if isinstance(meta, dict) and meta.get("interval"):
                    fallback_intervals.append(_interval_from_meta(meta))
            if not fallback_intervals:
                entry_tf = base_rec.get("entry_tf")
                if isinstance(entry_tf, str) and entry_tf.strip():
                    fallback_intervals = [part.strip() for part in entry_tf.split(",") if part.strip()]
            if not fallback_intervals:
                fallback_intervals = ["-"]
            for idx, interval_label in enumerate(fallback_intervals):
                meta = None
                if idx < len(meta_items) and isinstance(meta_items[idx], dict):
                    meta = meta_items[idx]
                _build_entry(None, interval_label, meta)

    for (sym, side_key), rec in open_records.items():
        meta_items = meta_map.get((sym, side_key)) or [None]
        _emit_entries(rec, sym, side_key, meta_items)

    for rec in closed_records:
        sym = str(rec.get("symbol") or "").strip().upper()
        side_key = str(rec.get("side_key") or "").strip().upper()
        entry_tf = rec.get("entry_tf")
        meta_items: list[dict | None] = []
        if isinstance(entry_tf, str) and entry_tf.strip():
            parts = [part.strip() for part in entry_tf.split(",") if part.strip()]
            if parts:
                meta_items = [{"interval": part} for part in parts]
        if not meta_items:
            meta_items = [None]
        _emit_entries(rec, sym, side_key, meta_items)

    grouped: dict[tuple[str, str, str, tuple[str, ...]], dict[str, list[dict]]] = {}
    dedupe_tracker: dict[tuple[str, str, str, tuple[str, ...]], set[tuple]] = {}
    for entry in raw_records:
        try:
            symbol_key = str(entry.get("symbol") or "").strip().upper()
            side_key = str(entry.get("side_key") or "").strip().upper()
            interval_key = str(entry.get("entry_tf") or "").strip().lower()
            indicators_tuple = tuple(
                sorted(
                    str(ind or "").strip().lower()
                    for ind in (entry.get("indicators") or [])
                    if str(ind or "").strip()
                )
            )
            status_key = str(entry.get("status") or "").strip().lower() or "active"
            group_key = (symbol_key, side_key, interval_key, indicators_tuple)
            bucket = grouped.setdefault(group_key, {})
            status_bucket = bucket.setdefault(status_key, [])
            aggregate_key = entry.get("_aggregate_key")

            # Stronger duplicate guard: collapse identical slot records even when aggregate_key differs.
            data = entry.get("data") or {}
            dedupe_key = (
                status_key,
                str(entry.get("open_time") or data.get("open_time") or "").strip(),
                str(entry.get("close_time") or data.get("close_time") or "").strip(),
                round(float(data.get("qty") or 0.0), 10),
            )
            seen = dedupe_tracker.setdefault(group_key, set())
            if dedupe_key in seen:
                continue
            seen.add(dedupe_key)

            if aggregate_key and any(existing.get("_aggregate_key") == aggregate_key for existing in status_bucket):
                continue
            status_bucket.append(entry)
        except Exception:
            continue

    def _qty_key(entry: dict) -> float:
        try:
            return abs(float((entry.get("data") or {}).get("qty") or 0.0))
        except Exception:
            return 0.0

    def _close_time_key(entry: dict) -> datetime:
        data = entry.get("data") or {}
        close_val = data.get("close_time") or entry.get("close_time") or ""
        dt = None
        try:
            dt = self._parse_any_datetime(close_val)
        except Exception:
            dt = None
        if dt is None:
            try:
                dt = datetime.min.replace(tzinfo=datetime.now().astimezone().tzinfo)
            except Exception:
                dt = datetime.min
        return dt

    records = []
    for (_sym, _side, _interval, _indicators), status_map in grouped.items():
        if not isinstance(status_map, dict):
            continue
        active_entries = status_map.get("active") or status_map.get("open") or []
        if active_entries:
            chosen_active = max(active_entries, key=_qty_key)
            records.append(chosen_active)
        closed_entries = (status_map.get("closed") or [])[:]
        closed_entries.sort(key=_close_time_key, reverse=True)
        records.extend(closed_entries)
        for status_name, entries in status_map.items():
            if status_name in {"active", "open", "closed"}:
                continue
            records.extend(entries or [])

    records.sort(key=lambda item: (
        str(item.get("symbol") or ""),
        str(item.get("side_key") or ""),
        str(item.get("entry_tf") or ""),
        -float(item.get("data", {}).get("qty") or item.get("data", {}).get("margin_usdt") or 0.0),
    ))

    def _merge_interval_labels(primary: dict, candidate: dict) -> None:
        labels: list[str] = []
        for rec in (primary, candidate):
            if not isinstance(rec, dict):
                continue
            for key in ("entry_tf",):
                value = rec.get(key)
                if isinstance(value, str) and value.strip():
                    labels.extend([part.strip() for part in value.split(",") if part.strip()])
            data = rec.get("data") or {}
            if isinstance(data, dict):
                value = data.get("interval_display")
                if isinstance(value, str) and value.strip():
                    labels.extend([part.strip() for part in value.split(",") if part.strip()])
        merged = ", ".join(dict.fromkeys(labels))
        if merged:
            primary["entry_tf"] = merged
            data = dict(primary.get("data") or {})
            data["interval_display"] = merged
            primary["data"] = data

    def _close_key(entry: dict) -> str:
        data = entry.get("data") or {}
        aggregate = str(entry.get("_aggregate_key") or data.get("_aggregate_key") or "").strip()
        ledger = str(entry.get("ledger_id") or data.get("ledger_id") or "").strip()
        close_time = entry.get("close_time") or data.get("close_time") or ""
        symbol_key = str(entry.get("symbol") or data.get("symbol") or "").strip().upper()
        side_key = str(entry.get("side_key") or data.get("side_key") or "").strip().upper()
        try:
            qty_key = f"{float(data.get('qty') or 0.0):.8f}"
        except Exception:
            qty_key = "0.0"
        if aggregate:
            return aggregate
        if ledger:
            return ledger
        return f"{symbol_key}|{side_key}|{close_time}|{qty_key}"

    deduped: list[dict] = []
    seen_closed: dict[str, dict] = {}
    for entry in records:
        data = entry.get("data") or {}
        status_flag = str(entry.get("status") or data.get("status") or "").strip().lower()
        is_closed = status_flag in _CLOSED_RECORD_STATES
        if is_closed:
            key = _close_key(entry)
            existing = seen_closed.get(key)
            if existing:
                _merge_interval_labels(existing, entry)
                continue
            seen_closed[key] = entry
        deduped.append(entry)
    records = deduped

    # Show every record (open and closed) without aggressive de-duplication, so per-trade view reflects all legs.
    for entry in records:
        entry["_aggregated_entries"] = [entry]
    return records




def _mw_update_position_history(self, positions_map: dict):
    try:
        if not hasattr(self, "_open_position_records"):
            self._open_position_records = {}
        if not hasattr(self, "_closed_position_records"):
            self._closed_position_records = []
        missing_counts = getattr(self, "_position_missing_counts", {})
        if not isinstance(missing_counts, dict):
            missing_counts = {}
        prev_records = getattr(self, "_open_position_records", {}) or {}
        candidates: list[tuple[str, str]] = []
        pending_close_map = getattr(self, "_pending_close_times", {})
        closed_history_max = _closed_history_max(self)
        try:
            missing_grace_seconds = float(self.config.get("positions_missing_grace_seconds", 30) or 0.0)
        except Exception:
            missing_grace_seconds = 0.0
        missing_grace_seconds = max(0.0, missing_grace_seconds)
        for key, prev in prev_records.items():
            if key in positions_map:
                missing_counts.pop(key, None)
                continue
            count = missing_counts.get(key, 0) + 1
            missing_counts[key] = count
            try:
                threshold = int(self.config.get("positions_missing_threshold", 2) or 2)
            except Exception:
                threshold = 2
            threshold = max(1, threshold)
            try:
                if isinstance(pending_close_map, dict) and key in pending_close_map:
                    threshold = 1
            except Exception:
                try:
                    threshold = int(self.config.get("positions_missing_threshold", 2) or 2)
                except Exception:
                    threshold = 2
            if count >= threshold:
                if missing_grace_seconds > 0 and not (isinstance(pending_close_map, dict) and key in pending_close_map):
                    open_val = None
                    if isinstance(prev, dict):
                        open_val = prev.get("open_time")
                        if not open_val:
                            open_val = (prev.get("data") or {}).get("open_time")
                        if not open_val:
                            open_val = (prev.get("data") or {}).get("update_time")
                    dt_obj = self._parse_any_datetime(open_val)
                    if dt_obj is not None:
                        try:
                            age_seconds = time.time() - dt_obj.timestamp()
                        except Exception:
                            age_seconds = None
                        if age_seconds is not None and 0 <= age_seconds < missing_grace_seconds:
                            continue
                candidates.append(key)

        def _resolve_live_keys() -> set[tuple[str, str]] | None:
            if not candidates:
                return set()
            try:
                bw = getattr(self, "shared_binance", None)
                if bw is None:
                    api_key = ""
                    api_secret = ""
                    try:
                        api_key = (self.api_key_edit.text() or "").strip()
                        api_secret = (self.api_secret_edit.text() or "").strip()
                    except Exception:
                        pass
                    if api_key and api_secret:
                        try:
                            bw = self._create_binance_wrapper(
                                api_key=api_key,
                                api_secret=api_secret,
                                mode=self.mode_combo.currentText(),
                                account_type=self.account_combo.currentText(),
                                default_leverage=int(self.leverage_spin.value() or 1),
                                default_margin_mode=self.margin_mode_combo.currentText() or "Isolated",
                            )
                            self.shared_binance = bw
                        except Exception:
                            bw = None
                if bw is None:
                    return None
                live = set()
                try:
                    acct_text = self.account_combo.currentText()
                except Exception:
                    acct_text = str(self.config.get("account_type") or "")
                acct_upper = str(acct_text or "").upper()
                acct_is_futures = acct_upper.startswith("FUT")
                acct_is_spot = acct_upper.startswith("SPOT")

                need_futures = acct_is_futures and any(side in ("L", "S") for _, side in candidates)
                need_spot = acct_is_spot and any(side in ("L", "S", "SPOT") for _, side in candidates)
                if need_futures:
                    try:
                        for pos in bw.list_open_futures_positions() or []:
                            sym = str(pos.get("symbol") or "").strip().upper()
                            if not sym:
                                continue
                            amt = float(pos.get("positionAmt") or 0.0)
                            if abs(amt) <= 0.0:
                                continue
                            side_key = "L" if amt > 0 else "S"
                            live.add((sym, side_key))
                    except Exception:
                        return None
                if need_spot:
                    try:
                        balances = bw.get_balances() or []
                        for bal in balances:
                            asset = bal.get("asset")
                            free = float(bal.get("free") or 0.0)
                            locked = float(bal.get("locked") or 0.0)
                            total = free + locked
                            if not asset or total <= 0:
                                continue
                            sym = f"{asset}USDT"
                            sym_upper = sym.strip().upper()
                            live.add((sym_upper, "SPOT"))
                            live.add((sym_upper, "L"))
                    except Exception:
                        pass
                return live
            except Exception:
                return None

        live_keys = _resolve_live_keys() if candidates else set()
        allow_missing_autoclose = bool(self.config.get("positions_missing_autoclose", True))

        def _lookup_force_liquidation(symbol: str, side_key: str, update_hint_ms: int | None = None) -> dict | None:
            try:
                bw = getattr(self, "shared_binance", None)
                if bw is None or not hasattr(bw, "get_recent_force_orders"):
                    return None
                params: dict[str, object] = {"symbol": symbol, "limit": 20}
                if update_hint_ms:
                    try:
                        params["start_time"] = max(0, int(update_hint_ms) - 900_000)
                    except Exception:
                        pass
                orders = bw.get_recent_force_orders(**params) or []
                if not orders:
                    return None
                expected_side = "SELL" if side_key == "L" else "BUY"
                now_ms = int(time.time() * 1000)
                for order in reversed(orders):
                    if not isinstance(order, dict):
                        continue
                    order_side = str(order.get("side") or "").upper()
                    if order_side != expected_side:
                        continue
                    try:
                        order_time = int(float(order.get("updateTime") or order.get("time") or 0))
                    except Exception:
                        order_time = 0
                    if order_time and abs(now_ms - order_time) > 900_000:
                        continue
                    qty_val = 0.0
                    for qty_key in ("executedQty", "origQty"):
                        val = order.get(qty_key)
                        if val in (None, "", 0, 0.0):
                            continue
                        try:
                            qty_val = abs(float(val))
                        except Exception:
                            qty_val = 0.0
                        if qty_val > 0:
                            break
                    if qty_val <= 0.0:
                        continue
                    price_val = 0.0
                    for price_key in ("avgPrice", "price"):
                        val = order.get(price_key)
                        if val in (None, "", 0, 0.0):
                            continue
                        try:
                            price_val = float(val)
                        except Exception:
                            price_val = 0.0
                        if price_val > 0.0:
                            break
                    if price_val <= 0.0:
                        continue
                    return {
                        "close_price": price_val,
                        "qty": qty_val,
                        "time": order_time or now_ms,
                        "raw": order,
                    }
            except Exception:
                return None
            return None

        confirmed_closed: list[tuple[str, str]] = []
        for key in candidates:
            if live_keys is None or key in live_keys:
                if key in prev_records:
                    positions_map.setdefault(key, prev_records[key])
                missing_counts[key] = 0
            else:
                if allow_missing_autoclose:
                    confirmed_closed.append(key)
                else:
                    prev_records.pop(key, None)
                    missing_counts.pop(key, None)

        if confirmed_closed:
            from datetime import datetime as _dt

            close_time_map = getattr(self, "_pending_close_times", {})
            for key in confirmed_closed:
                rec = prev_records.get(key)
                if not rec:
                    continue
                sym, side_key = key
                snap = copy.deepcopy(rec)
                data_prev = dict(rec.get("data") or {})
                close_status = "Closed"
                qty_reported = None
                margin_reported = None
                pnl_reported = None
                roi_reported = None
                close_price_reported = None
                entry_price_reported = None
                leverage_reported = None
                close_fmt = None
                close_raw = close_time_map.pop(key, None) if isinstance(close_time_map, dict) else None
                if close_raw:
                    dt_obj = self._parse_any_datetime(close_raw)
                    if dt_obj:
                        close_fmt = self._format_display_time(dt_obj)
                if close_fmt is None:
                    close_fmt = self._format_display_time(_dt.now().astimezone())
                if "stop_loss_enabled" not in snap:
                    snap["stop_loss_enabled"] = bool(rec.get("stop_loss_enabled"))
                try:
                    alloc_entries = copy.deepcopy(getattr(self, "_entry_allocations", {}).get(key, [])) or []
                except Exception:
                    alloc_entries = []
                entry_price_val = 0.0
                margin_prev = float(data_prev.get("margin_usdt") or 0.0)
                size_prev = float(data_prev.get("size_usdt") or 0.0)
                leverage_prev = data_prev.get("leverage")
                if isinstance(leverage_prev, (int, float)) and leverage_prev > 0:
                    leverage_reported = int(float(leverage_prev))
                else:
                    leverage_reported = None
                if alloc_entries:
                    num = 0.0
                    den = 0.0
                    for entry in alloc_entries:
                        if not isinstance(entry, dict):
                            continue
                        try:
                            qty_val = abs(float(entry.get("qty") or 0.0))
                            price_val = float(entry.get("entry_price") or data_prev.get("entry_price") or 0.0)
                        except Exception:
                            qty_val = 0.0
                            price_val = 0.0
                        if qty_val > 0 and price_val > 0:
                            num += price_val * qty_val
                            den += qty_val
                        try:
                            margin_prev = max(margin_prev, float(entry.get("margin_usdt") or 0.0))
                        except Exception:
                            pass
                        try:
                            size_prev = max(size_prev, float(entry.get("notional") or entry.get("size_usdt") or size_prev or 0.0))
                        except Exception:
                            pass
                    if den > 0:
                        entry_price_val = num / den
                if entry_price_val <= 0:
                    try:
                        entry_price_val = float(data_prev.get("entry_price") or 0.0)
                    except Exception:
                        entry_price_val = 0.0
                update_hint = None
                try:
                    update_hint = int(float(data_prev.get("update_time") or 0))
                except Exception:
                    update_hint = None
                liquidation_meta = None
                if side_key in ("L", "S"):
                    liquidation_meta = _lookup_force_liquidation(sym, side_key, update_hint)
                if liquidation_meta:
                    close_status = "Liquidated"
                    snap["close_reason"] = "Liquidation"
                    liquidation_time = liquidation_meta.get("time")
                    if liquidation_time:
                        try:
                            close_fmt = self._format_display_time(_dt.fromtimestamp(int(liquidation_time) / 1000.0).astimezone())
                        except Exception:
                            pass
                    close_price_reported = float(liquidation_meta.get("close_price") or 0.0)
                    qty_reported = float(liquidation_meta.get("qty") or 0.0)
                    if entry_price_val > 0:
                        entry_price_reported = entry_price_val
                    side_mult = 1.0 if side_key == "L" else -1.0
                    if entry_price_reported and qty_reported:
                        pnl_calc = (close_price_reported - entry_price_reported) * qty_reported * side_mult
                        pnl_reported = pnl_calc
                    if margin_prev <= 0.0 and size_prev > 0.0 and leverage_prev:
                        try:
                            lev_val = float(leverage_prev)
                            if lev_val > 0:
                                margin_prev = size_prev / lev_val
                        except Exception:
                            pass
                    if margin_prev > 0.0:
                        margin_reported = margin_prev
                    if pnl_reported is not None and margin_reported:
                        try:
                            roi_reported = (pnl_reported / margin_reported) * 100.0
                        except Exception:
                            roi_reported = None
                snap["status"] = close_status
                snap["close_time"] = close_fmt
                snap_data = snap.setdefault("data", {})
                if not snap_data and data_prev:
                    snap_data.update(data_prev)
                if qty_reported is None:
                    try:
                        qty_prev = float(data_prev.get("qty") or 0.0)
                        if abs(qty_prev) > 0.0:
                            qty_reported = abs(qty_prev)
                    except Exception:
                        qty_reported = None
                if margin_reported is None:
                    try:
                        margin_val_prev = float(data_prev.get("margin_usdt") or 0.0)
                        if margin_val_prev > 0.0:
                            margin_reported = margin_val_prev
                    except Exception:
                        margin_reported = None
                if pnl_reported is None:
                    try:
                        pnl_prev = float(data_prev.get("pnl_value") or 0.0)
                        pnl_reported = pnl_prev
                    except Exception:
                        pnl_reported = None
                if roi_reported is None:
                    try:
                        roi_prev = float(data_prev.get("roi_percent") or 0.0)
                        roi_reported = roi_prev if roi_prev != 0.0 else None
                    except Exception:
                        roi_reported = None
                if close_price_reported is None:
                    try:
                        close_price_prev = float(data_prev.get("close_price") or 0.0)
                        if close_price_prev > 0.0:
                            close_price_reported = close_price_prev
                    except Exception:
                        close_price_reported = None
                if entry_price_reported is None and entry_price_val > 0:
                    entry_price_reported = entry_price_val
                if leverage_reported is None and leverage_prev:
                    try:
                        lev_int = int(float(leverage_prev))
                        if lev_int > 0:
                            leverage_reported = lev_int
                    except Exception:
                        leverage_reported = None
                if qty_reported is not None and qty_reported > 0:
                    snap_data["qty"] = qty_reported
                if margin_reported is not None and margin_reported > 0:
                    snap_data["margin_usdt"] = margin_reported
                if pnl_reported is not None:
                    snap_data["pnl_value"] = pnl_reported
                    if margin_reported and margin_reported > 0:
                        roi_calc = roi_reported if roi_reported is not None else (pnl_reported / margin_reported) * 100.0
                        roi_reported = roi_calc
                        snap_data["roi_percent"] = roi_calc
                        snap_data["pnl_roi"] = f"{pnl_reported:+.2f} USDT ({roi_calc:+.2f}%)"
                    else:
                        snap_data["pnl_roi"] = f"{pnl_reported:+.2f} USDT"
                if roi_reported is not None and "roi_percent" not in snap_data:
                    snap_data["roi_percent"] = roi_reported
                if close_price_reported is not None and close_price_reported > 0:
                    snap_data["close_price"] = close_price_reported
                if entry_price_reported is not None and entry_price_reported > 0:
                    snap_data.setdefault("entry_price", entry_price_reported)
                if leverage_reported:
                    snap_data["leverage"] = leverage_reported
                if alloc_entries:
                    for entry in alloc_entries:
                        if isinstance(entry, dict):
                            normalized_triggers = _resolve_trigger_indicators_safe(entry.get("trigger_indicators"), entry.get("trigger_desc"))
                            if normalized_triggers:
                                entry["trigger_indicators"] = normalized_triggers
                            elif entry.get("trigger_indicators"):
                                entry.pop("trigger_indicators", None)
                    base_data = rec.get("data", {}) or {}
                    base_qty = float(base_data.get("qty") or 0.0)
                    base_margin = float(base_data.get("margin_usdt") or 0.0)
                    base_pnl = float(base_data.get("pnl_value") or 0.0)
                    base_size = float(base_data.get("size_usdt") or 0.0)
                    total_qty = 0.0
                    for entry in alloc_entries:
                        try:
                            total_qty += abs(float(entry.get("qty") or 0.0))
                        except Exception:
                            continue
                    if total_qty <= 0 and base_qty > 0:
                        total_qty = base_qty
                    count_entries = len([entry for entry in alloc_entries if isinstance(entry, dict)])
                    for entry in alloc_entries:
                        if not isinstance(entry, dict):
                            continue
                        entry["status"] = close_status
                        entry["close_time"] = close_fmt
                        try:
                            qty_val = abs(float(entry.get("qty") or 0.0))
                        except Exception:
                            qty_val = 0.0
                        ratio = (qty_val / total_qty) if total_qty > 0 else (1.0 / count_entries if count_entries else 0.0)
                        if ratio <= 0 and count_entries:
                            ratio = 1.0 / count_entries
                        if float(entry.get("margin_usdt") or 0.0) <= 0 and base_margin > 0:
                            entry["margin_usdt"] = base_margin * ratio
                        if float(entry.get("notional") or 0.0) <= 0 and base_size > 0:
                            entry["notional"] = base_size * ratio
                        if entry.get("pnl_value") is None:
                            if base_pnl and base_qty > 0 and qty_val > 0:
                                entry["pnl_value"] = base_pnl * (qty_val / base_qty)
                            elif base_pnl and ratio > 0:
                                entry["pnl_value"] = base_pnl * ratio
                            else:
                                entry["pnl_value"] = base_pnl
                    qty_dist_sum = 0.0
                    try:
                        qty_dist_sum = sum(abs(float(e.get("qty") or 0.0)) for e in alloc_entries if isinstance(e, dict))
                    except Exception:
                        qty_dist_sum = 0.0
                    if qty_dist_sum <= 0.0 and qty_reported is not None and qty_reported > 0:
                        qty_dist_sum = qty_reported
                    entries_count = len([entry for entry in alloc_entries if isinstance(entry, dict)])
                    for entry in alloc_entries:
                        if not isinstance(entry, dict):
                            continue
                        share = 0.0
                        try:
                            if qty_dist_sum and qty_dist_sum > 0:
                                share = abs(float(entry.get("qty") or 0.0)) / qty_dist_sum
                        except Exception:
                            share = 0.0
                        if share <= 0.0 and entries_count:
                            share = 1.0 / entries_count
                        if qty_reported is not None and qty_reported > 0 and share > 0:
                            entry["qty"] = qty_reported * share
                        if margin_reported is not None and margin_reported > 0 and share > 0:
                            entry["margin_usdt"] = margin_reported * share
                        if pnl_reported is not None and share > 0:
                            entry["pnl_value"] = pnl_reported * share
                        if close_price_reported is not None and close_price_reported > 0:
                            entry["close_price"] = close_price_reported
                        if entry_price_reported is not None and entry_price_reported > 0:
                            entry.setdefault("entry_price", entry_price_reported)
                        if leverage_reported:
                            entry["leverage"] = leverage_reported
                else:
                    alloc_entries = []
                if alloc_entries:
                    snap["allocations"] = alloc_entries
                self._closed_position_records.insert(0, snap)
                try:
                    registry = getattr(self, "_closed_trade_registry", None)
                    if registry is None:
                        registry = {}
                        self._closed_trade_registry = registry
                    registry_key = snap.get("ledger_id") or f"auto:{sym}:{side_key}:{close_fmt}"

                    def _safe_float_report(value):
                        try:
                            return float(value) if value is not None else None
                        except Exception:
                            return None

                    registry[registry_key] = {
                        "pnl_value": _safe_float_report(pnl_reported),
                        "margin_usdt": _safe_float_report(margin_reported),
                        "roi_percent": _safe_float_report(roi_reported),
                    }
                    if len(registry) > closed_history_max:
                        excess = len(registry) - closed_history_max
                        if excess > 0:
                            for old_key in list(registry.keys())[:excess]:
                                registry.pop(old_key, None)
                    try:
                        self._update_global_pnl_display(*self._compute_global_pnl_totals())
                    except Exception:
                        pass
                except Exception:
                    pass
                missing_counts.pop(key, None)
                try:
                    getattr(self, "_entry_allocations", {}).pop(key, None)
                except Exception:
                    pass
            if len(self._closed_position_records) > closed_history_max:
                self._closed_position_records = self._closed_position_records[:closed_history_max]

        self._open_position_records = positions_map
        self._position_missing_counts = missing_counts
    except Exception:
        pass


def refresh_positions(self, symbols=None, *args, **kwargs):
    """Manual refresh of positions: reconfigure worker and trigger an immediate tick."""
    try:
        try:
            self._reconfigure_positions_worker(symbols=symbols)
        except Exception:
            pass
        try:
            self.trigger_positions_refresh()
        except Exception:
            pass
        self.log("Positions refresh requested.")
    except Exception as e:
        try:
            self.log(f"Refresh positions error: {e}")
        except Exception:
            pass


def _apply_positions_refresh_settings(self):
    try:
        raw_val = self.config.get("positions_refresh_interval_ms", getattr(self, "_pos_refresh_interval_ms", 5000))
        try:
            interval = int(raw_val)
        except Exception:
            interval = getattr(self, "_pos_refresh_interval_ms", 5000)
        interval = max(2000, min(interval, 60000))
        self._pos_refresh_interval_ms = interval
        self.config["positions_refresh_interval_ms"] = interval
        self.req_pos_start.emit(interval)
    except Exception:
        pass


def trigger_positions_refresh(self, interval_ms: int | None = None):
    try:
        if interval_ms is None:
            interval = getattr(self, "_pos_refresh_interval_ms", 5000)
        else:
            interval = int(interval_ms)
    except Exception:
        interval = getattr(self, "_pos_refresh_interval_ms", 5000)
    if interval <= 0:
        interval = 5000
    self._pos_refresh_interval_ms = interval
    try:
        self.req_pos_start.emit(interval)
    except Exception:
        pass


def _mw_clear_positions_selected(self):
    try:
        table = getattr(self, "pos_table", None)
        if table is None:
            return
        sel_model = table.selectionModel()
        if sel_model is None:
            return
        rows = sorted({index.row() for index in sel_model.selectedRows()}, reverse=True)
        if not rows:
            return
        closed_records = list(getattr(self, "_closed_position_records", []) or [])
        changed = False
        skipped_active = False
        for row in rows:
            status_item = table.item(row, POS_STATUS_COLUMN)
            status = (status_item.text().strip().upper() if status_item else "")
            if status != "CLOSED":
                skipped_active = True
                continue
            symbol_item = table.item(row, 0)
            side_item = table.item(row, 9)
            symbol = (symbol_item.text().strip().upper() if symbol_item else "")
            side_txt = (side_item.text().strip().upper() if side_item else "")
            side_key = None
            if "LONG" in side_txt or side_txt == "BUY":
                side_key = "L"
            elif "SHORT" in side_txt or side_txt == "SELL":
                side_key = "S"
            remove_idx = None
            for idx, rec in enumerate(closed_records):
                rec_sym = str(rec.get("symbol") or "").strip().upper()
                rec_side = str(rec.get("side_key") or "").strip().upper()
                if rec_sym == symbol and (side_key is None or not rec_side or rec_side == side_key):
                    remove_idx = idx
                    break
            if remove_idx is not None:
                closed_records.pop(remove_idx)
                changed = True
        if changed:
            self._closed_position_records = closed_records
            self._render_positions_table()
        if skipped_active:
            try:
                self.log("Positions: only closed history rows can be cleared.")
            except Exception:
                pass
    except Exception:
        pass


def _mw_clear_positions_all(self):
    try:
        if QtWidgets.QMessageBox.question(
            self,
            "Clear Closed History",
            "Clear ALL closed position history? (Active positions remain untouched.)",
            QtWidgets.QMessageBox.StandardButton.Yes | QtWidgets.QMessageBox.StandardButton.No,
        ) != QtWidgets.QMessageBox.StandardButton.Yes:
            return
        self._closed_position_records = []
        self._closed_trade_registry = {}
        self._render_positions_table()
    except Exception:
        pass


def _mw_snapshot_closed_position(self, symbol: str, side_key: str) -> bool:
    try:
        if not symbol or side_key not in ("L", "S"):
            return False
        if not hasattr(self, "_closed_position_records"):
            self._closed_position_records = []
        open_records = getattr(self, "_open_position_records", {}) or {}
        rec = open_records.get((symbol, side_key))
        if not rec:
            return False
        snap = copy.deepcopy(rec)
        snap["status"] = "Closed"
        snap["close_time"] = self._format_display_time(datetime.now().astimezone())
        self._closed_position_records.insert(0, snap)
        max_history = _closed_history_max(self)
        if len(self._closed_position_records) > max_history:
            self._closed_position_records = self._closed_position_records[:max_history]
        try:
            registry = getattr(self, "_closed_trade_registry", None)
            if registry is None:
                registry = {}
                self._closed_trade_registry = registry
            key = f"{symbol}-{side_key}-{int(time.time() * 1000)}"
            data = snap.get("data") if isinstance(snap, dict) else {}

            def _safe_float_local(value):
                try:
                    return float(value)
                except Exception:
                    return None

            registry[key] = {
                "pnl_value": _safe_float_local((data or {}).get("pnl_value")),
                "margin_usdt": _safe_float_local((data or {}).get("margin_usdt")),
                "roi_percent": _safe_float_local((data or {}).get("roi_percent")),
            }
            if len(registry) > max_history:
                excess = len(registry) - max_history
                if excess > 0:
                    for old_key in list(registry.keys())[:excess]:
                        registry.pop(old_key, None)
        except Exception:
            pass
        try:
            open_records.pop((symbol, side_key), None)
        except Exception:
            pass
        try:
            self._update_global_pnl_display(*self._compute_global_pnl_totals())
        except Exception:
            pass
        return True
    except Exception:
        return False


def _mw_clear_local_position_state(
    self,
    symbol: str,
    side_key: str,
    *,
    interval: str | None = None,
    reason: str | None = None,
) -> bool:
    """Remove a stale local position/allocations snapshot for a single futures side."""
    try:
        sym_upper = str(symbol or "").strip().upper()
        side_norm = str(side_key or "").strip().upper()
        if not sym_upper or side_norm not in ("L", "S"):
            return False
        key = (sym_upper, side_norm)
        changed = False

        try:
            changed = bool(self._snapshot_closed_position(sym_upper, side_norm)) or changed
        except Exception:
            pass

        try:
            open_records = getattr(self, "_open_position_records", None)
            if isinstance(open_records, dict) and key in open_records:
                open_records.pop(key, None)
                changed = True
        except Exception:
            pass

        try:
            alloc_map = getattr(self, "_entry_allocations", None)
            if isinstance(alloc_map, dict) and key in alloc_map:
                alloc_map.pop(key, None)
                changed = True
        except Exception:
            pass

        try:
            pending_close = getattr(self, "_pending_close_times", None)
            if isinstance(pending_close, dict):
                pending_close.pop(key, None)
        except Exception:
            pass

        try:
            missing_counts = getattr(self, "_position_missing_counts", None)
            if isinstance(missing_counts, dict):
                missing_counts.pop(key, None)
        except Exception:
            pass

        try:
            entry_times = getattr(self, "_entry_times", None)
            if isinstance(entry_times, dict):
                entry_times.pop(key, None)
        except Exception:
            pass

        intervals_to_close: list[str] = []
        try:
            entry_intervals = getattr(self, "_entry_intervals", None)
            if isinstance(entry_intervals, dict):
                side_map = entry_intervals.get(sym_upper)
                if isinstance(side_map, dict):
                    bucket = side_map.get(side_norm)
                    if isinstance(bucket, set):
                        intervals_to_close.extend([str(iv).strip() for iv in bucket if str(iv).strip()])
        except Exception:
            pass
        if interval:
            iv = str(interval).strip()
            if iv and iv not in intervals_to_close:
                intervals_to_close.append(iv)
        if intervals_to_close and hasattr(self, "_track_interval_close"):
            for iv in intervals_to_close:
                try:
                    self._track_interval_close(sym_upper, side_norm, iv)
                except Exception:
                    continue

        try:
            iv_times = getattr(self, "_entry_times_by_iv", None)
            if isinstance(iv_times, dict):
                for iv_key in list(iv_times.keys()):
                    try:
                        sym_key, side_key_key, _iv = iv_key
                    except Exception:
                        continue
                    if str(sym_key or "").strip().upper() == sym_upper and str(side_key_key or "").strip().upper() == side_norm:
                        iv_times.pop(iv_key, None)
        except Exception:
            pass

        try:
            guard_obj = getattr(self, "guard", None)
            if guard_obj and hasattr(guard_obj, "mark_closed"):
                guard_side = "BUY" if side_norm == "L" else "SELL"
                guard_obj.mark_closed(sym_upper, interval, guard_side)
        except Exception:
            pass

        if changed:
            saver = _SAVE_POSITION_ALLOCATIONS
            if callable(saver):
                try:
                    mode_value = self.mode_combo.currentText() if hasattr(self, "mode_combo") else None
                    saver(
                        getattr(self, "_entry_allocations", {}),
                        getattr(self, "_open_position_records", {}),
                        mode=mode_value,
                    )
                except Exception:
                    pass
            try:
                self._update_global_pnl_display(*self._compute_global_pnl_totals())
            except Exception:
                pass
            try:
                self._render_positions_table()
            except Exception:
                pass
            if reason:
                try:
                    self.log(f"{sym_upper} {side_norm}: cleared stale local position ({reason}).")
                except Exception:
                    pass
        return changed
    except Exception:
        return False


def _mw_sync_chart_to_active_positions(self):
    try:
        if not getattr(self, "chart_enabled", False):
            return
        open_records = getattr(self, "_open_position_records", {}) or {}
        if not open_records:
            return
        active_syms = []
        for rec in open_records.values():
            try:
                if str(rec.get("status", "Active")).upper() != "ACTIVE":
                    continue
                sym = str(rec.get("symbol") or "").strip().upper()
                if sym:
                    active_syms.append(sym)
            except Exception:
                continue
        if not active_syms:
            return
        target_sym = active_syms[0]
        market_combo = getattr(self, "chart_market_combo", None)
        if market_combo is None:
            return
        current_market = self._normalize_chart_market(market_combo.currentText())
        if current_market != "Futures":
            try:
                idx = market_combo.findText("Futures", QtCore.Qt.MatchFlag.MatchFixedString)
                if idx >= 0:
                    market_combo.setCurrentIndex(idx)
                else:
                    market_combo.addItem("Futures")
                    market_combo.setCurrentIndex(market_combo.count() - 1)
            except Exception:
                try:
                    market_combo.setCurrentText("Futures")
                except Exception:
                    pass
            return
        display_sym = self._futures_display_symbol(target_sym)
        cache = self.chart_symbol_cache.setdefault("Futures", [])
        if target_sym not in cache:
            cache.append(target_sym)
        alias_map = getattr(self, "_chart_symbol_alias_map", None)
        if not isinstance(alias_map, dict):
            alias_map = {}
            self._chart_symbol_alias_map = alias_map
        futures_alias = alias_map.setdefault("Futures", {})
        futures_alias[display_sym] = target_sym
        self._update_chart_symbol_options(cache)
        changed = self._set_chart_symbol(display_sym, ensure_option=True, from_follow=True)
        if changed or self._chart_needs_render or self._is_chart_visible():
            self.load_chart(auto=True)
    except Exception:
        pass


def _mw_make_close_btn(self, symbol: str, side_key: str | None = None, interval: str | None = None, qty: float | None = None):
    label = "Close"
    if side_key == "L":
        label = "Close Long"
    elif side_key == "S":
        label = "Close Short"
    btn = QtWidgets.QPushButton(label)
    tooltip_bits = []
    if side_key == "L":
        tooltip_bits.append("Closes the long leg")
    elif side_key == "S":
        tooltip_bits.append("Closes the short leg")
    if interval and interval not in ("-", "SPOT"):
        tooltip_bits.append(f"Interval {interval}")
    if qty and qty > 0:
        try:
            tooltip_bits.append(f"Qty ~= {qty:.6f}")
        except Exception:
            pass
    if tooltip_bits:
        btn.setToolTip(" | ".join(tooltip_bits))
    btn.setEnabled(side_key in ("L", "S"))
    interval_key = interval if interval not in ("-", "SPOT") else None
    btn.clicked.connect(lambda _, s=symbol, sk=side_key, iv=interval_key, q=qty: self._close_position_single(s, sk, iv, q))
    return btn


def _mw_close_position_single(self, symbol: str, side_key: str | None, interval: str | None, qty: float | None):
    if not symbol:
        return
    try:
        from ..workers import CallWorker as _CallWorker
    except Exception as exc:
        try:
            self.log(f"Close {symbol} setup error: {exc}")
        except Exception:
            pass
        return
    if side_key not in ("L", "S"):
        try:
            self.log(f"{symbol}: manual close is only available for futures legs.")
        except Exception:
            pass
        return
    account_text = (self.account_combo.currentText() or "").upper()
    force_futures = side_key in ("L", "S")
    needs_wrapper = getattr(self, "shared_binance", None) is None
    if force_futures and not needs_wrapper:
        try:
            current_wrapper_acct = str(getattr(self.shared_binance, "account_type", "") or "").upper()
        except Exception:
            current_wrapper_acct = ""
        if not current_wrapper_acct.startswith("FUT"):
            needs_wrapper = True
    if needs_wrapper:
        try:
            self.shared_binance = self._create_binance_wrapper(
                api_key=self.api_key_edit.text().strip(),
                api_secret=self.api_secret_edit.text().strip(),
                mode=self.mode_combo.currentText(),
                account_type=("Futures" if force_futures else self.account_combo.currentText()),
                default_leverage=int(self.leverage_spin.value() or 1),
                default_margin_mode=self.margin_mode_combo.currentText() or "Isolated",
            )
        except Exception as exc:
            try:
                self.log(f"Close {symbol} setup error: {exc}")
            except Exception:
                pass
            return
    account = account_text
    try:
        qty_val = float(qty or 0.0)
    except Exception:
        qty_val = 0.0

    def _do():
        bw = self.shared_binance
        symbol_upper = str(symbol or "").strip().upper()

        def _annotate_no_live_leg(result_payload):
            if isinstance(result_payload, dict) and result_payload.get("ok"):
                return result_payload
            try:
                rows = bw.list_open_futures_positions(max_age=0.0, force_refresh=True) or []
            except Exception as exc:
                if isinstance(result_payload, dict):
                    enriched = dict(result_payload)
                    enriched.setdefault("lookup_error", str(exc))
                    return enriched
                return {"ok": False, "error": f"{result_payload!r}", "lookup_error": str(exc)}
            has_target_leg = False
            for row in rows:
                try:
                    row_sym = str(row.get("symbol") or "").strip().upper()
                    if row_sym != symbol_upper:
                        continue
                    amt = float(row.get("positionAmt") or 0.0)
                    if abs(amt) <= 0.0:
                        continue
                    row_side = str(row.get("positionSide") or row.get("positionside") or "BOTH").upper().strip()
                    if side_key == "L":
                        if row_side == "LONG" or (row_side in ("", "BOTH") and amt > 0.0):
                            has_target_leg = True
                            break
                    elif side_key == "S":
                        if row_side == "SHORT" or (row_side in ("", "BOTH") and amt < 0.0):
                            has_target_leg = True
                            break
                except Exception:
                    continue
            if not has_target_leg:
                if isinstance(result_payload, dict):
                    enriched = dict(result_payload)
                else:
                    enriched = {"ok": False, "error": f"{result_payload!r}"}
                enriched["no_live_position"] = True
                return enriched
            return result_payload

        if force_futures or account.startswith("FUT"):
            if side_key in ("L", "S") and qty_val > 0:
                try:
                    dual = bool(bw.get_futures_dual_side())
                except Exception:
                    dual = False
                order_side = "SELL" if side_key == "L" else "BUY"
                pos_side = None
                if dual:
                    pos_side = "LONG" if side_key == "L" else "SHORT"
                primary_res = bw.close_futures_leg_exact(symbol, qty_val, side=order_side, position_side=pos_side)
                if isinstance(primary_res, dict) and primary_res.get("ok"):
                    return primary_res
                try:
                    fallback_res = bw.close_futures_position(symbol)
                except Exception as exc:
                    fallback_res = {"ok": False, "error": str(exc)}
                if isinstance(fallback_res, dict) and fallback_res.get("ok"):
                    fallback_res.setdefault("fallback_from", "close_futures_leg_exact")
                    if isinstance(primary_res, dict) and primary_res.get("error"):
                        fallback_res.setdefault("primary_error", primary_res.get("error"))
                    return fallback_res
                if isinstance(primary_res, dict):
                    primary_res["fallback"] = fallback_res
                    return _annotate_no_live_leg(primary_res)
                return _annotate_no_live_leg(
                    {"ok": False, "error": f"close leg failed: {primary_res!r}", "fallback": fallback_res}
                )
            return _annotate_no_live_leg(bw.close_futures_position(symbol))
        return {"ok": False, "error": "Spot manual close via UI is not available yet"}

    def _done(res, err):
        succeeded = False
        try:
            if err:
                self.log(f"Close {symbol} error: {err}")
            else:
                self.log(f"Close {symbol} result: {res}")
                succeeded = isinstance(res, dict) and res.get("ok")
                if (
                    not succeeded
                    and isinstance(res, dict)
                    and bool(res.get("no_live_position"))
                    and side_key in ("L", "S")
                ):
                    try:
                        if hasattr(self, "_clear_local_position_state"):
                            cleared = bool(
                                self._clear_local_position_state(
                                    symbol,
                                    side_key,
                                    interval=interval,
                                    reason="exchange reports no open leg",
                                )
                            )
                    except Exception:
                        cleared = False
                    if cleared:
                        succeeded = True
            if succeeded and interval and side_key in ("L", "S"):
                try:
                    if hasattr(self, "_track_interval_close"):
                        self._track_interval_close(symbol, side_key, interval)
                except Exception:
                    pass
        except Exception:
            pass
        try:
            self.refresh_positions(symbols=[symbol])
        except Exception:
            pass

    worker = _CallWorker(_do, parent=self)
    try:
        worker.progress.connect(self.log)
    except Exception:
        pass
    worker.done.connect(_done)
    worker.finished.connect(worker.deleteLater)

    def _cleanup():
        try:
            self._bg_workers.remove(worker)
        except Exception:
            pass

    if not hasattr(self, "_bg_workers"):
        self._bg_workers = []
    self._bg_workers.append(worker)
    worker.finished.connect(_cleanup)
    worker.start()


def _mw_pos_symbol_keys(self, symbol) -> tuple:
    sym_raw = str(symbol or "").strip()
    if not sym_raw:
        return tuple()
    sym_upper = sym_raw.upper()
    if sym_upper == sym_raw:
        return (sym_upper,)
    return tuple(dict.fromkeys([sym_upper, sym_raw]))


def _mw_pos_interval_keys(self, interval) -> tuple:
    iv_raw = str(interval or "").strip()
    if not iv_raw:
        return tuple()
    try:
        canon = self._canonicalize_interval(iv_raw)
    except Exception:
        canon = None
    keys = []
    if canon:
        keys.append(canon)
    if iv_raw and iv_raw != canon:
        keys.append(iv_raw)
    return tuple(dict.fromkeys(keys))


def _mw_pos_track_interval_open(self, symbol, side_key, interval, timestamp) -> None:
    if side_key not in ("L", "S"):
        return
    symbol_keys = _mw_pos_symbol_keys(self, symbol)
    if not symbol_keys:
        sym_raw = str(symbol or "").strip()
        if not sym_raw:
            return
        symbol_keys = _mw_pos_symbol_keys(self, sym_raw)
        if not symbol_keys:
            return
    primary_symbol = symbol_keys[0]
    interval_keys = _mw_pos_interval_keys(self, interval)
    primary_interval = interval_keys[0] if interval_keys else None
    entry_map = self._entry_intervals.setdefault(primary_symbol, {"L": set(), "S": set()})
    entry_map.setdefault("L", set())
    entry_map.setdefault("S", set())
    if primary_interval:
        entry_map[side_key].add(primary_interval)
    if timestamp:
        self._entry_times[(primary_symbol, side_key)] = timestamp
        if primary_interval:
            self._entry_times_by_iv[(primary_symbol, side_key, primary_interval)] = timestamp
    for alt_symbol in symbol_keys[1:]:
        if not alt_symbol:
            continue
        legacy = self._entry_intervals.pop(alt_symbol, None)
        if isinstance(legacy, dict):
            for leg_side, iv_set in legacy.items():
                if leg_side not in ("L", "S") or not isinstance(iv_set, set):
                    continue
                target = entry_map.setdefault(leg_side, set())
                for iv in iv_set:
                    normalized = _mw_pos_interval_keys(self, iv)
                    if normalized:
                        target.add(normalized[0])
        for side_variant in ("L", "S"):
            ts_val = self._entry_times.pop((alt_symbol, side_variant), None)
            if ts_val and (primary_symbol, side_variant) not in self._entry_times:
                self._entry_times[(primary_symbol, side_variant)] = ts_val
        for (sym_key, side_variant, iv_key), ts_val in list(self._entry_times_by_iv.items()):
            if sym_key == alt_symbol:
                normalized = _mw_pos_interval_keys(self, iv_key)
                self._entry_times_by_iv.pop((sym_key, side_variant, iv_key), None)
                if normalized:
                    self._entry_times_by_iv[(primary_symbol, side_variant, normalized[0])] = ts_val


def _mw_pos_track_interval_close(self, symbol, side_key, interval) -> None:
    if side_key not in ("L", "S"):
        return
    symbol_keys = _mw_pos_symbol_keys(self, symbol)
    if not symbol_keys:
        sym_raw = str(symbol or "").strip()
        candidates = [sym_raw.upper(), sym_raw]
        symbol_keys = tuple(dict.fromkeys([c for c in candidates if c]))
    interval_keys = _mw_pos_interval_keys(self, interval)
    if not interval_keys and interval:
        iv_raw = str(interval).strip()
        if iv_raw:
            interval_keys = (iv_raw,)
    for sym_key in symbol_keys:
        if not sym_key:
            continue
        side_map = self._entry_intervals.get(sym_key)
        if not isinstance(side_map, dict):
            continue
        bucket = side_map.get(side_key)
        if not isinstance(bucket, set):
            bucket = side_map[side_key] = set()
        for iv_key in interval_keys:
            bucket.discard(iv_key)
            self._entry_times_by_iv.pop((sym_key, side_key, iv_key), None)


def _handle_close_all_result(self, res):
    try:
        details = res or []
        for r in details:
            sym = r.get("symbol") or "?"
            if not r.get("ok"):
                self.log(f"Close-all {sym}: error -> {r.get('error')}")
            elif r.get("skipped"):
                self.log(f"Close-all {sym}: skipped ({r.get('reason')})")
            else:
                self.log(f"Close-all {sym}: ok")
        n_ok = sum(1 for r in details if r.get("ok"))
        n_all = len(details)
        self.log(f"Close-all completed: {n_ok}/{n_all} ok.")
    except Exception:
        self.log(f"Close-all result: {res}")
    try:
        self._apply_close_all_to_positions_cache(res)
    except Exception:
        pass
    try:
        self.refresh_positions()
    except Exception:
        pass
    try:
        self.trigger_positions_refresh()
    except Exception:
        pass


def _apply_close_all_to_positions_cache(self, res) -> None:
    """Mark local position state as closed when a close-all command succeeds."""
    details = res or []
    if isinstance(details, dict):
        details = [details]
    elif not isinstance(details, (list, tuple, set)):
        details = [details]

    symbols_to_mark: set[str] = set()
    had_error = False
    for item in details:
        if not isinstance(item, dict):
            continue
        sym_raw = str(item.get("symbol") or "").strip().upper()
        if not sym_raw:
            continue
        ok_flag = bool(item.get("ok"))
        skipped_flag = bool(item.get("skipped"))
        if ok_flag or skipped_flag:
            symbols_to_mark.add(sym_raw)
        else:
            had_error = True

    open_records = getattr(self, "_open_position_records", {}) or {}
    if not symbols_to_mark and not had_error and open_records:
        symbols_to_mark = {sym for sym, _ in open_records.keys()}
    if not symbols_to_mark:
        return

    pending_close = getattr(self, "_pending_close_times", None)
    if not isinstance(pending_close, dict):
        pending_close = {}
        self._pending_close_times = pending_close
    missing_counts = getattr(self, "_position_missing_counts", None)
    if not isinstance(missing_counts, dict):
        missing_counts = {}
        self._position_missing_counts = missing_counts

    close_time_fmt = self._format_display_time(datetime.now().astimezone())
    alloc_map = getattr(self, "_entry_allocations", {})
    closed_records = getattr(self, "_closed_position_records", None)
    if not isinstance(closed_records, list):
        closed_records = []
        self._closed_position_records = closed_records
    max_history = _closed_history_max(self)

    for key in list(open_records.keys()):
        sym_key, side_key = key
        record = open_records.get(key)
        if sym_key not in symbols_to_mark:
            continue
        if key not in pending_close:
            pending_close[key] = close_time_fmt
        missing_counts[key] = 0
        try:
            intervals_map = getattr(self, "_entry_intervals", {})
            side_bucket = intervals_map.get(sym_key, {}).get(side_key)
            if hasattr(self, "_track_interval_close") and isinstance(side_bucket, set):
                for interval in list(side_bucket):
                    self._track_interval_close(sym_key, side_key, interval)
        except Exception:
            pass

        snap = copy.deepcopy(record) if isinstance(record, dict) else {
            "symbol": sym_key,
            "side_key": side_key,
            "status": "Closed",
            "open_time": "-",
            "close_time": close_time_fmt,
            "data": {},
            "indicators": [],
            "stop_loss_enabled": False,
        }
        snap["status"] = "Closed"
        snap["close_time"] = close_time_fmt
        if "stop_loss_enabled" not in snap:
            snap["stop_loss_enabled"] = bool((record or {}).get("stop_loss_enabled"))

        base_data = dict((record or {}).get("data") or {})
        snap["data"] = base_data
        try:
            alloc_entries = copy.deepcopy(alloc_map.get(key, [])) or []
            for alloc_entry in alloc_entries:
                if isinstance(alloc_entry, dict):
                    normalized_triggers = _resolve_trigger_indicators_safe(
                        alloc_entry.get("trigger_indicators"),
                        alloc_entry.get("trigger_desc"),
                    )
                    if normalized_triggers:
                        alloc_entry["trigger_indicators"] = normalized_triggers
                    elif alloc_entry.get("trigger_indicators"):
                        alloc_entry.pop("trigger_indicators", None)
        except Exception:
            alloc_entries = []
        if alloc_entries:
            snap["allocations"] = alloc_entries
        closed_records.insert(0, snap)
        if len(closed_records) > max_history:
            del closed_records[max_history:]
        alloc_map.pop(key, None)
        open_records.pop(key, None)
        try:
            getattr(self, "_entry_times", {}).pop(key, None)
        except Exception:
            pass
        try:
            iv_times = getattr(self, "_entry_times_by_iv", {})
            if isinstance(iv_times, dict):
                for (sym, side, interval) in list(iv_times.keys()):
                    if sym == sym_key and side == side_key:
                        iv_times.pop((sym, side, interval), None)
        except Exception:
            pass

    try:
        self._open_position_records = dict(open_records)
    except Exception:
        self._open_position_records = open_records
    try:
        self._update_global_pnl_display(*self._compute_global_pnl_totals())
    except Exception:
        pass
    try:
        self._render_positions_table()
    except Exception:
        pass


def _close_all_positions_blocking(self, auth: dict | None = None, *, fast: bool = False):
    return self._close_all_positions_sync(auth=auth, fast=fast)


def _close_all_positions_sync(self, auth: dict | None = None, *, fast: bool = False):
    from ..close_all import close_all_futures_positions as _close_all_futures

    # Rebuild wrapper each time so close-all uses latest mode/credentials even if launch-time wrapper was different.
    if auth is None:
        auth = self._snapshot_auth_state()
    timeout_override = None
    if fast:
        timeout_override = {
            "BINANCE_HTTP_CONNECT_TIMEOUT": os.environ.get("BINANCE_HTTP_CONNECT_TIMEOUT"),
            "BINANCE_HTTP_READ_TIMEOUT": os.environ.get("BINANCE_HTTP_READ_TIMEOUT"),
        }
        os.environ["BINANCE_HTTP_CONNECT_TIMEOUT"] = "2"
        os.environ["BINANCE_HTTP_READ_TIMEOUT"] = "6"
    try:
        self.shared_binance = self._build_wrapper_from_values(auth)
        acct_text = str(auth.get("account_type") or "").upper() or (
            self.account_combo.currentText().upper() if hasattr(self, "account_combo") else ""
        )
        if acct_text.startswith("FUT"):
            results = _close_all_futures(self.shared_binance, fast=fast) or []
            if not fast:
                # Verification loop: re-run close-all if any positions remain.
                try:
                    for _ in range(3):
                        try:
                            remaining = self.shared_binance.list_open_futures_positions(force_refresh=True) or []
                        except Exception:
                            remaining = []
                        open_left = [p for p in remaining if abs(float(p.get("positionAmt") or 0.0)) > 0.0]
                        if not open_left:
                            break
                        more = _close_all_futures(self.shared_binance) or []
                        results.extend(more)
                except Exception:
                    pass
            return results
        return self.shared_binance.close_all_spot_positions()
    finally:
        if timeout_override is not None:
            for key, old_val in timeout_override.items():
                if old_val is None:
                    try:
                        os.environ.pop(key, None)
                    except Exception:
                        pass
                else:
                    os.environ[key] = old_val


def close_all_positions_async(self):
    """Close all open futures positions using reduce-only market orders in a worker."""
    try:
        from ..workers import CallWorker as _CallWorker

        auth_snapshot = self._snapshot_auth_state()
        fast_close = False
        try:
            mode_txt = str(auth_snapshot.get("mode") or "").lower()
            fast_close = any(tag in mode_txt for tag in ("demo", "test", "sandbox"))
        except Exception:
            fast_close = False

        def _do():
            return self._close_all_positions_sync(auth=auth_snapshot, fast=fast_close)

        def _done(res, err):
            if err:
                self.log(f"Close-all error: {err}")
                return
            self._handle_close_all_result(res)

        worker = _CallWorker(_do, parent=self)
        try:
            worker.progress.connect(self.log)
        except Exception:
            pass
        worker.done.connect(_done)
        if not hasattr(self, "_bg_workers"):
            self._bg_workers = []
        self._bg_workers.append(worker)

        def _cleanup():
            try:
                self._bg_workers.remove(worker)
            except Exception:
                pass

        try:
            worker.finished.connect(_cleanup)
        except Exception:
            pass
        worker.start()
    except Exception as e:
        try:
            self.log(f"Close-all setup error: {e}")
        except Exception:
            pass


def _begin_close_on_exit_sequence(self):
    if getattr(self, "_close_in_progress", False):
        return
    self._close_in_progress = True
    auth_snapshot = self._snapshot_auth_state()
    if not hasattr(self, "_bg_workers"):
        self._bg_workers = []
    try:
        from PyQt6 import QtWidgets

        message = QtWidgets.QMessageBox(self)
        message.setWindowTitle("Closing Positions")
        message.setText("Closing open positions before exit. Please wait.")
        try:
            message.setIcon(QtWidgets.QMessageBox.Icon.Information)
        except Exception:
            pass
        message.setStandardButtons(QtWidgets.QMessageBox.StandardButton.NoButton)
        message.setModal(False)
        message.show()
        self._close_progress_dialog = message
    except Exception:
        self._close_progress_dialog = None

    def _do():
        stop_strategy_sync = _STOP_STRATEGY_SYNC
        if callable(stop_strategy_sync):
            return stop_strategy_sync(self, close_positions=True, auth=auth_snapshot)
        return {"ok": False, "error": "_stop_strategy_sync is not configured"}

    def _done(res, err):
        try:
            if getattr(self, "_close_progress_dialog", None):
                self._close_progress_dialog.close()
        except Exception:
            pass
        self._close_progress_dialog = None
        self._close_in_progress = False

        def _positions_remaining() -> list:
            try:
                acct_text = str(auth_snapshot.get("account_type") or "").upper()
                if acct_text.startswith("FUT"):
                    return [
                        p
                        for p in (self.shared_binance.list_open_futures_positions(force_refresh=True) or [])
                        if abs(float(p.get("positionAmt") or 0.0)) > 0.0
                    ]
            except Exception:
                return []
            return []

        try:
            from PyQt6 import QtWidgets
        except Exception:
            QtWidgets = None

        if err:
            try:
                self.log(f"Stop error during exit: {err}")
            except Exception:
                pass
            remaining = _positions_remaining()
            if remaining and QtWidgets is not None:
                QtWidgets.QMessageBox.warning(
                    self,
                    "Close-all failed",
                    "Some positions are still open. Please try closing them manually.",
                )
            return
        try:
            if isinstance(res, dict) and res.get("close_all_result"):
                self._handle_close_all_result(res.get("close_all_result"))
        except Exception:
            pass
        remaining = _positions_remaining()
        if remaining:
            try:
                symbols_left = ", ".join(sorted({str(p.get("symbol") or "").upper() for p in remaining}))
            except Exception:
                symbols_left = "some positions"
            if QtWidgets is not None:
                QtWidgets.QMessageBox.warning(
                    self,
                    "Positions still open",
                    f"Could not close all positions automatically. Remaining: {symbols_left}. Please close manually.",
                )
            return
        self._force_close = True
        if QtWidgets is not None:
            QtWidgets.QWidget.close(self)
            return
        try:
            self.close()
        except Exception:
            pass

    try:
        from ..workers import CallWorker as _CallWorker

        worker = _CallWorker(_do, parent=self)
        try:
            worker.progress.connect(self.log)
        except Exception:
            pass
        worker.done.connect(_done)

        def _cleanup():
            try:
                self._bg_workers.remove(worker)
            except Exception:
                pass

        worker.finished.connect(_cleanup)
        worker.finished.connect(worker.deleteLater)
        self._bg_workers.append(worker)
        worker.start()
    except Exception as e:
        self._close_in_progress = False
        try:
            if getattr(self, "_close_progress_dialog", None):
                self._close_progress_dialog.close()
        except Exception:
            pass
        self._close_progress_dialog = None
        try:
            self.log(f"Exit close setup error: {e}")
        except Exception:
            pass


def bind_main_window_positions(
    main_window_cls,
    *,
    resolve_trigger_indicators=None,
    max_closed_history: int = 200,
    stop_strategy_sync=None,
    pos_status_column: int = 16,
    save_position_allocations=None,
    normalize_indicator_values=None,
    derive_margin_snapshot=None,
    coerce_bool=None,
    format_indicator_list=None,
    collect_record_indicator_keys=None,
    collect_indicator_value_strings=None,
    collect_current_indicator_live_strings=None,
    dedupe_indicator_entries_normalized=None,
    numeric_item_cls=None,
    pos_triggered_value_column: int = 10,
    pos_current_value_column: int = 11,
    pos_stop_loss_column: int = 15,
    pos_close_column: int = 17,
) -> None:
    global _RESOLVE_TRIGGER_INDICATORS
    global _MAX_CLOSED_HISTORY
    global _STOP_STRATEGY_SYNC
    global _SAVE_POSITION_ALLOCATIONS
    global _NORMALIZE_INDICATOR_VALUES
    global _DERIVE_MARGIN_SNAPSHOT
    global _COERCE_BOOL
    global _FORMAT_INDICATOR_LIST
    global _COLLECT_RECORD_INDICATOR_KEYS
    global _COLLECT_INDICATOR_VALUE_STRINGS
    global _COLLECT_CURRENT_INDICATOR_LIVE_STRINGS
    global _DEDUPE_INDICATOR_ENTRIES_NORMALIZED
    global _NUMERIC_ITEM_CLS
    global _NumericItem
    global POS_TRIGGERED_VALUE_COLUMN
    global POS_CURRENT_VALUE_COLUMN
    global POS_STOP_LOSS_COLUMN
    global POS_STATUS_COLUMN
    global POS_CLOSE_COLUMN

    _RESOLVE_TRIGGER_INDICATORS = resolve_trigger_indicators
    _MAX_CLOSED_HISTORY = int(max_closed_history)
    _STOP_STRATEGY_SYNC = stop_strategy_sync
    _SAVE_POSITION_ALLOCATIONS = save_position_allocations
    _NORMALIZE_INDICATOR_VALUES = normalize_indicator_values
    _DERIVE_MARGIN_SNAPSHOT = derive_margin_snapshot
    _COERCE_BOOL = coerce_bool
    _FORMAT_INDICATOR_LIST = format_indicator_list
    _COLLECT_RECORD_INDICATOR_KEYS = collect_record_indicator_keys
    _COLLECT_INDICATOR_VALUE_STRINGS = collect_indicator_value_strings
    _COLLECT_CURRENT_INDICATOR_LIVE_STRINGS = collect_current_indicator_live_strings
    _DEDUPE_INDICATOR_ENTRIES_NORMALIZED = dedupe_indicator_entries_normalized
    if numeric_item_cls is not None:
        _NUMERIC_ITEM_CLS = numeric_item_cls
        _NumericItem = numeric_item_cls
    POS_TRIGGERED_VALUE_COLUMN = int(pos_triggered_value_column)
    POS_CURRENT_VALUE_COLUMN = int(pos_current_value_column)
    POS_STOP_LOSS_COLUMN = int(pos_stop_loss_column)
    POS_STATUS_COLUMN = int(pos_status_column)
    POS_CLOSE_COLUMN = int(pos_close_column)

    main_window_cls._update_positions_pnl_summary = _update_positions_pnl_summary
    main_window_cls._on_positions_ready = _gui_on_positions_ready
    main_window_cls._positions_records_per_trade = _mw_positions_records_per_trade
    main_window_cls._render_positions_table = _mw_render_positions_table
    main_window_cls._update_position_history = _mw_update_position_history
    main_window_cls.refresh_positions = refresh_positions
    main_window_cls._apply_positions_refresh_settings = _apply_positions_refresh_settings
    main_window_cls.trigger_positions_refresh = trigger_positions_refresh
    main_window_cls._clear_positions_selected = _mw_clear_positions_selected
    main_window_cls._clear_positions_all = _mw_clear_positions_all
    main_window_cls._snapshot_closed_position = _mw_snapshot_closed_position
    main_window_cls._clear_local_position_state = _mw_clear_local_position_state
    main_window_cls._sync_chart_to_active_positions = _mw_sync_chart_to_active_positions
    main_window_cls._make_close_btn = _mw_make_close_btn
    main_window_cls._close_position_single = _mw_close_position_single
    main_window_cls._pos_symbol_keys = _mw_pos_symbol_keys
    main_window_cls._pos_interval_keys = _mw_pos_interval_keys
    main_window_cls._track_interval_open = _mw_pos_track_interval_open
    main_window_cls._track_interval_close = _mw_pos_track_interval_close
    main_window_cls._handle_close_all_result = _handle_close_all_result
    main_window_cls._apply_close_all_to_positions_cache = _apply_close_all_to_positions_cache
    main_window_cls._close_all_positions_sync = _close_all_positions_sync
    main_window_cls._close_all_positions_blocking = _close_all_positions_blocking
    main_window_cls.close_all_positions_async = close_all_positions_async
    main_window_cls._begin_close_on_exit_sequence = _begin_close_on_exit_sequence
