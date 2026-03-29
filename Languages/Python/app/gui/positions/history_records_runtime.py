from __future__ import annotations

from . import history_records_context_runtime
from .history_records_entries_runtime import build_meta_map, build_raw_history_records
from .history_records_group_runtime import group_history_records

configure_main_window_positions_history_records_runtime = (
    history_records_context_runtime.configure_main_window_positions_history_records_runtime
)
_closed_history_max = history_records_context_runtime._closed_history_max
_normalize_indicator_values = history_records_context_runtime._normalize_indicator_values
_derive_margin_snapshot = history_records_context_runtime._derive_margin_snapshot
_resolve_trigger_indicators_safe = history_records_context_runtime._resolve_trigger_indicators_safe


def _mw_positions_records_per_trade(self, open_records: dict, closed_records: list) -> list:
    metadata = getattr(self, "_engine_indicator_map", {}) or {}
    meta_map = build_meta_map(metadata)
    raw_records = build_raw_history_records(
        self,
        open_records,
        closed_records,
        meta_map,
        normalize_indicator_values=_normalize_indicator_values,
        derive_margin_snapshot=_derive_margin_snapshot,
    )
    records = group_history_records(
        self,
        raw_records,
        history_records_context_runtime._CLOSED_RECORD_STATES,
    )
    for entry in records:
        entry["_aggregated_entries"] = [entry]
    return records


__all__ = [
    "configure_main_window_positions_history_records_runtime",
    "_closed_history_max",
    "_normalize_indicator_values",
    "_derive_margin_snapshot",
    "_resolve_trigger_indicators_safe",
    "_mw_positions_records_per_trade",
]
