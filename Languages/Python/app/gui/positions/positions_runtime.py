from __future__ import annotations

from . import (
    actions_runtime,
    build_runtime,
    history_runtime,
    positions_context_runtime,
    render_runtime,
    tracking_runtime,
)
from .positions_context_runtime import (
    _closed_history_max,
    _coerce_bool,
    _collect_current_indicator_live_strings,
    _collect_indicator_value_strings,
    _collect_record_indicator_keys,
    _dedupe_indicator_entries_normalized,
    _derive_margin_snapshot,
    _format_indicator_list,
    _normalize_indicator_values,
    _resolve_trigger_indicators_safe,
)
from .positions_cumulative_runtime import _mw_positions_records_cumulative
from .positions_refresh_runtime import (
    _apply_positions_refresh_settings,
    refresh_positions,
    trigger_positions_refresh,
)


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
    positions_context_runtime.configure_positions_runtime_context(
        resolve_trigger_indicators=resolve_trigger_indicators,
        max_closed_history=max_closed_history,
        normalize_indicator_values=normalize_indicator_values,
        derive_margin_snapshot=derive_margin_snapshot,
        coerce_bool=coerce_bool,
        format_indicator_list=format_indicator_list,
        collect_record_indicator_keys=collect_record_indicator_keys,
        collect_indicator_value_strings=collect_indicator_value_strings,
        collect_current_indicator_live_strings=collect_current_indicator_live_strings,
        dedupe_indicator_entries_normalized=dedupe_indicator_entries_normalized,
        numeric_item_cls=numeric_item_cls,
        pos_triggered_value_column=pos_triggered_value_column,
        pos_current_value_column=pos_current_value_column,
        pos_stop_loss_column=pos_stop_loss_column,
        pos_status_column=pos_status_column,
        pos_close_column=pos_close_column,
    )

    build_runtime.configure_main_window_positions_build_runtime(
        resolve_trigger_indicators=resolve_trigger_indicators,
    )
    history_runtime.configure_main_window_positions_history_runtime(
        closed_history_max_fn=_closed_history_max,
        closed_record_states=positions_context_runtime._CLOSED_RECORD_STATES,
        normalize_indicator_values=normalize_indicator_values,
        derive_margin_snapshot=derive_margin_snapshot,
        resolve_trigger_indicators=resolve_trigger_indicators,
    )
    render_runtime.configure_main_window_positions_render_runtime(
        closed_record_states=positions_context_runtime._CLOSED_RECORD_STATES,
        numeric_item_cls=positions_context_runtime._NumericItem,
        collect_current_indicator_live_strings=collect_current_indicator_live_strings,
        collect_indicator_value_strings=collect_indicator_value_strings,
        collect_record_indicator_keys=collect_record_indicator_keys,
        coerce_bool_fn=_coerce_bool,
        dedupe_indicator_entries_normalized=dedupe_indicator_entries_normalized,
        filter_indicator_entries_for_interval=positions_context_runtime._filter_indicator_entries_for_interval,
        format_indicator_list=format_indicator_list,
        indicator_entry_signature=positions_context_runtime._indicator_entry_signature,
        indicator_short_label=positions_context_runtime._indicator_short_label,
        normalize_indicator_values=normalize_indicator_values,
        positions_records_cumulative_fn=_mw_positions_records_cumulative,
        pos_triggered_value_column=positions_context_runtime.POS_TRIGGERED_VALUE_COLUMN,
        pos_current_value_column=positions_context_runtime.POS_CURRENT_VALUE_COLUMN,
        pos_stop_loss_column=positions_context_runtime.POS_STOP_LOSS_COLUMN,
        pos_status_column=positions_context_runtime.POS_STATUS_COLUMN,
        pos_close_column=positions_context_runtime.POS_CLOSE_COLUMN,
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


__all__ = [
    "_apply_interval_metadata_to_row",
    "_apply_positions_refresh_settings",
    "_closed_history_max",
    "_coerce_bool",
    "_collect_current_indicator_live_strings",
    "_collect_indicator_value_strings",
    "_collect_record_indicator_keys",
    "_copy_allocations_for_key",
    "_dedupe_indicator_entries_normalized",
    "_derive_margin_snapshot",
    "_format_indicator_list",
    "_gui_on_positions_ready",
    "_merge_futures_rows_into_positions_map",
    "_mw_positions_records_cumulative",
    "_mw_positions_records_per_trade",
    "_mw_render_positions_table",
    "_mw_update_position_history",
    "_normalize_indicator_values",
    "_resolve_trigger_indicators_safe",
    "_seed_positions_map_from_rows",
    "_update_positions_pnl_summary",
    "bind_main_window_positions",
    "refresh_positions",
    "trigger_positions_refresh",
]
