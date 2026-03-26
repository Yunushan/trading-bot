from __future__ import annotations

from . import (
    main_window_positions_history_records_runtime,
    main_window_positions_history_update_runtime,
)


def configure_main_window_positions_history_runtime(
    *,
    closed_history_max_fn=None,
    closed_record_states=None,
    normalize_indicator_values=None,
    derive_margin_snapshot=None,
    resolve_trigger_indicators=None,
) -> None:
    main_window_positions_history_records_runtime.configure_main_window_positions_history_records_runtime(
        closed_history_max_fn=closed_history_max_fn,
        closed_record_states=closed_record_states,
        normalize_indicator_values=normalize_indicator_values,
        derive_margin_snapshot=derive_margin_snapshot,
        resolve_trigger_indicators=resolve_trigger_indicators,
    )
    main_window_positions_history_update_runtime.configure_main_window_positions_history_update_runtime(
        closed_history_max_fn=closed_history_max_fn,
        resolve_trigger_indicators=resolve_trigger_indicators,
    )


def _mw_positions_records_per_trade(self, open_records: dict, closed_records: list) -> list:
    return main_window_positions_history_records_runtime._mw_positions_records_per_trade(
        self,
        open_records,
        closed_records,
    )


def _mw_update_position_history(self, positions_map: dict):
    return main_window_positions_history_update_runtime._mw_update_position_history(
        self,
        positions_map,
    )
