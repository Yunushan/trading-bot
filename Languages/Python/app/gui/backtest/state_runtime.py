from __future__ import annotations

from .backtest_state_context_runtime import configure_backtest_state_runtime
from .backtest_state_dates_runtime import (
    backtest_dates_changed,
    coerce_qdate,
    coerce_qdatetime,
)
from .backtest_state_init_runtime import initialize_backtest_ui_defaults
from .backtest_state_lists_runtime import (
    apply_backtest_intervals_to_dashboard,
    apply_backtest_symbol_selection_rule,
    backtest_store_intervals,
    backtest_store_symbols,
    populate_backtest_lists,
    set_backtest_interval_selection,
    set_backtest_symbol_selection,
    update_backtest_symbol_list,
)
from .backtest_state_symbols_runtime import (
    backtest_symbol_source_changed,
    on_backtest_symbols_ready,
    refresh_backtest_symbols,
    update_backtest_futures_controls,
)

_coerce_qdate = coerce_qdate
_coerce_qdatetime = coerce_qdatetime
_initialize_backtest_ui_defaults = initialize_backtest_ui_defaults
_populate_backtest_lists = populate_backtest_lists
_set_backtest_symbol_selection = set_backtest_symbol_selection
_apply_backtest_symbol_selection_rule = apply_backtest_symbol_selection_rule
_set_backtest_interval_selection = set_backtest_interval_selection
_update_backtest_symbol_list = update_backtest_symbol_list
_backtest_store_symbols = backtest_store_symbols
_backtest_store_intervals = backtest_store_intervals
_apply_backtest_intervals_to_dashboard = apply_backtest_intervals_to_dashboard
_update_backtest_futures_controls = update_backtest_futures_controls
_backtest_symbol_source_changed = backtest_symbol_source_changed
_refresh_backtest_symbols = refresh_backtest_symbols
_on_backtest_symbols_ready = on_backtest_symbols_ready
_backtest_dates_changed = backtest_dates_changed


def bind_main_window_backtest_state_runtime(
    main_window_cls,
    *,
    backtest_interval_order,
    side_labels: dict[str, str],
    symbol_fetch_top_n: int,
) -> None:
    configure_backtest_state_runtime(
        backtest_interval_order=backtest_interval_order,
        side_labels=side_labels,
        symbol_fetch_top_n=symbol_fetch_top_n,
    )

    main_window_cls._coerce_qdate = staticmethod(_coerce_qdate)
    main_window_cls._coerce_qdatetime = staticmethod(_coerce_qdatetime)
    main_window_cls._initialize_backtest_ui_defaults = _initialize_backtest_ui_defaults
    main_window_cls._populate_backtest_lists = _populate_backtest_lists
    main_window_cls._set_backtest_symbol_selection = _set_backtest_symbol_selection
    main_window_cls._apply_backtest_symbol_selection_rule = (
        _apply_backtest_symbol_selection_rule
    )
    main_window_cls._set_backtest_interval_selection = _set_backtest_interval_selection
    main_window_cls._update_backtest_symbol_list = _update_backtest_symbol_list
    main_window_cls._backtest_store_symbols = _backtest_store_symbols
    main_window_cls._backtest_store_intervals = _backtest_store_intervals
    main_window_cls._apply_backtest_intervals_to_dashboard = (
        _apply_backtest_intervals_to_dashboard
    )
    main_window_cls._update_backtest_futures_controls = (
        _update_backtest_futures_controls
    )
    main_window_cls._backtest_symbol_source_changed = _backtest_symbol_source_changed
    main_window_cls._refresh_backtest_symbols = _refresh_backtest_symbols
    main_window_cls._on_backtest_symbols_ready = _on_backtest_symbols_ready
    main_window_cls._backtest_dates_changed = _backtest_dates_changed
