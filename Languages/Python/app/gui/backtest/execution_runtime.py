from __future__ import annotations

from .backtest_execution_context_runtime import configure_backtest_execution_runtime
from .backtest_execution_run_runtime import run_backtest
from .backtest_execution_scan_runtime import run_backtest_scan

_run_backtest = run_backtest
_run_backtest_scan = run_backtest_scan


def bind_main_window_backtest_execution_runtime(
    main_window_cls,
    *,
    dbg_backtest_run: bool,
    symbol_fetch_top_n: int,
    normalize_stop_loss_dict,
    backtest_worker_cls,
) -> None:
    configure_backtest_execution_runtime(
        dbg_backtest_run=dbg_backtest_run,
        symbol_fetch_top_n=symbol_fetch_top_n,
        normalize_stop_loss_dict=normalize_stop_loss_dict,
        backtest_worker_cls=backtest_worker_cls,
    )

    main_window_cls._run_backtest = _run_backtest
    main_window_cls._run_backtest_scan = _run_backtest_scan
