from __future__ import annotations

from PyQt6 import QtWidgets

from ..shared import indicator_value_helpers

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


def _collect_indicator_value_strings(
    rec: dict,
    interval_hint: str | None = None,
) -> tuple[list[str], dict[str, list[str]]]:
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


def configure_positions_runtime_context(
    *,
    resolve_trigger_indicators=None,
    max_closed_history: int = 200,
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
    pos_status_column: int = 16,
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


__all__ = [
    "POS_CLOSE_COLUMN",
    "POS_CURRENT_VALUE_COLUMN",
    "POS_STATUS_COLUMN",
    "POS_STOP_LOSS_COLUMN",
    "POS_TRIGGERED_VALUE_COLUMN",
    "_CLOSED_RECORD_STATES",
    "_NumericItem",
    "_closed_history_max",
    "_coerce_bool",
    "_collect_current_indicator_live_strings",
    "_collect_indicator_value_strings",
    "_collect_record_indicator_keys",
    "_dedupe_indicator_entries_normalized",
    "_derive_margin_snapshot",
    "_filter_indicator_entries_for_interval",
    "_format_indicator_list",
    "_indicator_entry_signature",
    "_indicator_short_label",
    "_normalize_indicator_values",
    "_resolve_trigger_indicators_safe",
    "configure_positions_runtime_context",
]
