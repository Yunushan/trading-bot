from __future__ import annotations

from PyQt6 import QtWidgets

_CLOSED_RECORD_STATES: set[str] = set()
_NUMERIC_ITEM_CLS = QtWidgets.QTableWidgetItem
_COLLECT_CURRENT_INDICATOR_LIVE_STRINGS = None
_COLLECT_INDICATOR_VALUE_STRINGS = None
_COLLECT_RECORD_INDICATOR_KEYS = None
_COERCE_BOOL = None
_DEDUPE_INDICATOR_ENTRIES_NORMALIZED = None
_FILTER_INDICATOR_ENTRIES_FOR_INTERVAL = None
_FORMAT_INDICATOR_LIST = None
_INDICATOR_ENTRY_SIGNATURE = None
_INDICATOR_SHORT_LABEL = None
_NORMALIZE_INDICATOR_VALUES = None
_POSITIONS_RECORDS_CUMULATIVE = None
POS_TRIGGERED_VALUE_COLUMN = 10
POS_CURRENT_VALUE_COLUMN = 11
POS_STOP_LOSS_COLUMN = 15
POS_STATUS_COLUMN = 16
POS_CLOSE_COLUMN = 17


def configure_main_window_positions_render_runtime(
    *,
    closed_record_states=None,
    numeric_item_cls=None,
    collect_current_indicator_live_strings=None,
    collect_indicator_value_strings=None,
    collect_record_indicator_keys=None,
    coerce_bool_fn=None,
    dedupe_indicator_entries_normalized=None,
    filter_indicator_entries_for_interval=None,
    format_indicator_list=None,
    indicator_entry_signature=None,
    indicator_short_label=None,
    normalize_indicator_values=None,
    positions_records_cumulative_fn=None,
    pos_triggered_value_column: int = 10,
    pos_current_value_column: int = 11,
    pos_stop_loss_column: int = 15,
    pos_status_column: int = 16,
    pos_close_column: int = 17,
) -> None:
    global _CLOSED_RECORD_STATES
    global _NUMERIC_ITEM_CLS
    global _COLLECT_CURRENT_INDICATOR_LIVE_STRINGS
    global _COLLECT_INDICATOR_VALUE_STRINGS
    global _COLLECT_RECORD_INDICATOR_KEYS
    global _COERCE_BOOL
    global _DEDUPE_INDICATOR_ENTRIES_NORMALIZED
    global _FILTER_INDICATOR_ENTRIES_FOR_INTERVAL
    global _FORMAT_INDICATOR_LIST
    global _INDICATOR_ENTRY_SIGNATURE
    global _INDICATOR_SHORT_LABEL
    global _NORMALIZE_INDICATOR_VALUES
    global _POSITIONS_RECORDS_CUMULATIVE
    global POS_TRIGGERED_VALUE_COLUMN
    global POS_CURRENT_VALUE_COLUMN
    global POS_STOP_LOSS_COLUMN
    global POS_STATUS_COLUMN
    global POS_CLOSE_COLUMN

    _CLOSED_RECORD_STATES = set(closed_record_states or ())
    if numeric_item_cls is not None:
        _NUMERIC_ITEM_CLS = numeric_item_cls
    _COLLECT_CURRENT_INDICATOR_LIVE_STRINGS = collect_current_indicator_live_strings
    _COLLECT_INDICATOR_VALUE_STRINGS = collect_indicator_value_strings
    _COLLECT_RECORD_INDICATOR_KEYS = collect_record_indicator_keys
    _COERCE_BOOL = coerce_bool_fn
    _DEDUPE_INDICATOR_ENTRIES_NORMALIZED = dedupe_indicator_entries_normalized
    _FILTER_INDICATOR_ENTRIES_FOR_INTERVAL = filter_indicator_entries_for_interval
    _FORMAT_INDICATOR_LIST = format_indicator_list
    _INDICATOR_ENTRY_SIGNATURE = indicator_entry_signature
    _INDICATOR_SHORT_LABEL = indicator_short_label
    _NORMALIZE_INDICATOR_VALUES = normalize_indicator_values
    _POSITIONS_RECORDS_CUMULATIVE = positions_records_cumulative_fn
    POS_TRIGGERED_VALUE_COLUMN = int(pos_triggered_value_column)
    POS_CURRENT_VALUE_COLUMN = int(pos_current_value_column)
    POS_STOP_LOSS_COLUMN = int(pos_stop_loss_column)
    POS_STATUS_COLUMN = int(pos_status_column)
    POS_CLOSE_COLUMN = int(pos_close_column)


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


def _filter_indicator_entries(
    entries: list[str] | None,
    interval_hint: str | None,
    *,
    include_non_matching: bool = True,
) -> list[str]:
    func = _FILTER_INDICATOR_ENTRIES_FOR_INTERVAL
    if not callable(func):
        return list(entries or [])
    try:
        return list(
            func(
                entries,
                interval_hint,
                include_non_matching=include_non_matching,
            )
            or []
        )
    except Exception:
        return list(entries or [])


def _indicator_entry_signature(entry: str) -> tuple[str, str]:
    func = _INDICATOR_ENTRY_SIGNATURE
    if not callable(func):
        text = str(entry or "").strip().lower()
        return (text, "")
    try:
        label_part, interval_part = func(entry)
        return str(label_part or ""), str(interval_part or "")
    except Exception:
        text = str(entry or "").strip().lower()
        return (text, "")


def _indicator_short_label(key) -> str:
    func = _INDICATOR_SHORT_LABEL
    if not callable(func):
        return str(key or "")
    try:
        return str(func(key) or "")
    except Exception:
        return str(key or "")


def _normalize_indicator_values(raw) -> list[str]:
    func = _NORMALIZE_INDICATOR_VALUES
    if not callable(func):
        return []
    try:
        return list(func(raw))
    except Exception:
        return []


def _positions_records_cumulative(self, entries: list[dict], closed_entries: list[dict] | None = None) -> list[dict]:
    func = _POSITIONS_RECORDS_CUMULATIVE
    if not callable(func):
        return list(entries or [])
    try:
        return list(func(self, entries, closed_entries) or [])
    except Exception:
        return list(entries or [])


__all__ = [
    "POS_CLOSE_COLUMN",
    "POS_CURRENT_VALUE_COLUMN",
    "POS_STATUS_COLUMN",
    "POS_STOP_LOSS_COLUMN",
    "POS_TRIGGERED_VALUE_COLUMN",
    "_CLOSED_RECORD_STATES",
    "_NUMERIC_ITEM_CLS",
    "_coerce_bool",
    "_collect_current_indicator_live_strings",
    "_collect_indicator_value_strings",
    "_collect_record_indicator_keys",
    "_dedupe_indicator_entries_normalized",
    "_filter_indicator_entries",
    "_format_indicator_list",
    "_indicator_entry_signature",
    "_indicator_short_label",
    "_normalize_indicator_values",
    "_positions_records_cumulative",
    "configure_main_window_positions_render_runtime",
]
