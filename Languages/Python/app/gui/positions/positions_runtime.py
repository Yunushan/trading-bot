from __future__ import annotations

import copy
from datetime import datetime

from PyQt6 import QtWidgets

from app.integrations.exchanges.binance import normalize_margin_ratio
from ..shared import indicator_value_helpers
from . import (
    actions_runtime,
    build_runtime,
    history_runtime,
    render_runtime,
    tracking_runtime,
)

_RESOLVE_TRIGGER_INDICATORS = None
_MAX_CLOSED_HISTORY = 200
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
    return build_runtime._copy_allocations_for_key(
        alloc_map_global,
        symbol,
        side_key,
    )


def _seed_positions_map_from_rows(self, base_rows: list, alloc_map_global: dict, prev_records: dict) -> dict[tuple, dict]:
    return build_runtime._seed_positions_map_from_rows(
        self,
        base_rows,
        alloc_map_global,
        prev_records,
    )


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
    return build_runtime._apply_interval_metadata_to_row(
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


def _merge_futures_rows_into_positions_map(self, base_rows: list, positions_map: dict, alloc_map_global: dict) -> None:
    return build_runtime._merge_futures_rows_into_positions_map(
        self,
        base_rows,
        positions_map,
        alloc_map_global,
    )

def _mw_render_positions_table(self):
    return render_runtime._mw_render_positions_table(self)




def _gui_on_positions_ready(self, rows: list, acct: str):
    return build_runtime._gui_on_positions_ready(self, rows, acct)

def _mw_positions_records_per_trade(self, open_records: dict, closed_records: list) -> list:
    return history_runtime._mw_positions_records_per_trade(
        self,
        open_records,
        closed_records,
    )




def _mw_update_position_history(self, positions_map: dict):
    return history_runtime._mw_update_position_history(
        self,
        positions_map,
    )


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

    build_runtime.configure_main_window_positions_build_runtime(
        resolve_trigger_indicators=resolve_trigger_indicators,
    )
    history_runtime.configure_main_window_positions_history_runtime(
        closed_history_max_fn=_closed_history_max,
        closed_record_states=_CLOSED_RECORD_STATES,
        normalize_indicator_values=normalize_indicator_values,
        derive_margin_snapshot=derive_margin_snapshot,
        resolve_trigger_indicators=resolve_trigger_indicators,
    )
    render_runtime.configure_main_window_positions_render_runtime(
        closed_record_states=_CLOSED_RECORD_STATES,
        numeric_item_cls=_NumericItem,
        collect_current_indicator_live_strings=collect_current_indicator_live_strings,
        collect_indicator_value_strings=collect_indicator_value_strings,
        collect_record_indicator_keys=collect_record_indicator_keys,
        coerce_bool_fn=_coerce_bool,
        dedupe_indicator_entries_normalized=dedupe_indicator_entries_normalized,
        filter_indicator_entries_for_interval=_filter_indicator_entries_for_interval,
        format_indicator_list=format_indicator_list,
        indicator_entry_signature=_indicator_entry_signature,
        indicator_short_label=_indicator_short_label,
        normalize_indicator_values=normalize_indicator_values,
        positions_records_cumulative_fn=_mw_positions_records_cumulative,
        pos_triggered_value_column=POS_TRIGGERED_VALUE_COLUMN,
        pos_current_value_column=POS_CURRENT_VALUE_COLUMN,
        pos_stop_loss_column=POS_STOP_LOSS_COLUMN,
        pos_status_column=POS_STATUS_COLUMN,
        pos_close_column=POS_CLOSE_COLUMN,
    )

    main_window_cls._update_positions_pnl_summary = _update_positions_pnl_summary
    main_window_cls._on_positions_ready = _gui_on_positions_ready
    main_window_cls._positions_records_per_trade = _mw_positions_records_per_trade
    main_window_cls._render_positions_table = _mw_render_positions_table
    main_window_cls._update_position_history = _mw_update_position_history
    main_window_cls.refresh_positions = refresh_positions
    main_window_cls._apply_positions_refresh_settings = _apply_positions_refresh_settings
    main_window_cls.trigger_positions_refresh = trigger_positions_refresh
    actions_runtime.bind_main_window_positions_actions_runtime(
        main_window_cls,
        save_position_allocations=save_position_allocations,
        closed_history_max_fn=_closed_history_max,
        pos_status_column=pos_status_column,
    )
    tracking_runtime.bind_main_window_positions_tracking_runtime(
        main_window_cls,
        resolve_trigger_indicators=resolve_trigger_indicators,
        closed_history_max_fn=_closed_history_max,
        stop_strategy_sync=stop_strategy_sync,
    )
