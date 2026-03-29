from __future__ import annotations

_DBG_BACKTEST_RUN = False
_SYMBOL_FETCH_TOP_N = 200
_normalize_stop_loss_dict = lambda value: value  # type: ignore
_BacktestWorker = None


def configure_backtest_execution_runtime(
    *,
    dbg_backtest_run: bool,
    symbol_fetch_top_n: int,
    normalize_stop_loss_dict,
    backtest_worker_cls,
) -> None:
    global _DBG_BACKTEST_RUN
    global _SYMBOL_FETCH_TOP_N
    global _normalize_stop_loss_dict
    global _BacktestWorker

    _DBG_BACKTEST_RUN = bool(dbg_backtest_run)
    _SYMBOL_FETCH_TOP_N = max(1, int(symbol_fetch_top_n))
    if callable(normalize_stop_loss_dict):
        _normalize_stop_loss_dict = normalize_stop_loss_dict
    _BacktestWorker = backtest_worker_cls


def backtest_debug_enabled() -> bool:
    return bool(_DBG_BACKTEST_RUN)


def get_symbol_fetch_top_n() -> int:
    return int(_SYMBOL_FETCH_TOP_N)


def normalize_backtest_stop_loss_dict(value):
    return _normalize_stop_loss_dict(value)


def get_backtest_worker_cls():
    return _BacktestWorker


__all__ = [
    "backtest_debug_enabled",
    "configure_backtest_execution_runtime",
    "get_backtest_worker_cls",
    "get_symbol_fetch_top_n",
    "normalize_backtest_stop_loss_dict",
]
