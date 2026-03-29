from __future__ import annotations

from . import (
    backtest_results_normalize_runtime,
    backtest_results_selection_runtime,
    backtest_results_table_runtime,
)

_select_backtest_scan_best = backtest_results_selection_runtime._select_backtest_scan_best
_select_backtest_scan_row = backtest_results_selection_runtime._select_backtest_scan_row
_apply_backtest_scan_best = backtest_results_selection_runtime._apply_backtest_scan_best
_on_backtest_scan_finished = backtest_results_selection_runtime._on_backtest_scan_finished
_stop_backtest = backtest_results_selection_runtime._stop_backtest
_on_backtest_progress = backtest_results_selection_runtime._on_backtest_progress
_normalize_backtest_run = backtest_results_normalize_runtime._normalize_backtest_run
_on_backtest_finished = backtest_results_table_runtime._on_backtest_finished
_populate_backtest_results_table = backtest_results_table_runtime._populate_backtest_results_table


def bind_main_window_backtest_results_runtime(
    main_window_cls,
    *,
    mdd_logic_labels: dict[str, str],
    normalize_loop_override,
) -> None:
    backtest_results_normalize_runtime.configure_backtest_results_normalize_runtime(
        mdd_logic_labels=mdd_logic_labels,
        normalize_loop_override=normalize_loop_override,
    )

    main_window_cls._select_backtest_scan_best = _select_backtest_scan_best
    main_window_cls._select_backtest_scan_row = _select_backtest_scan_row
    main_window_cls._apply_backtest_scan_best = _apply_backtest_scan_best
    main_window_cls._on_backtest_scan_finished = _on_backtest_scan_finished
    main_window_cls._stop_backtest = _stop_backtest
    main_window_cls._on_backtest_progress = _on_backtest_progress
    main_window_cls._normalize_backtest_run = staticmethod(_normalize_backtest_run)
    main_window_cls._on_backtest_finished = _on_backtest_finished
    main_window_cls._populate_backtest_results_table = _populate_backtest_results_table
