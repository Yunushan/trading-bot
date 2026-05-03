"""
Backtest-domain helpers shared by desktop and service runtimes.
"""

from .intervals import normalize_backtest_interval, normalize_backtest_intervals
from .models import BacktestRequest, BacktestRunResult, IndicatorDefinition, PairOverride

__all__ = [
    "BacktestEngine",
    "BacktestRequest",
    "BacktestRunResult",
    "IndicatorDefinition",
    "PairOverride",
    "normalize_backtest_interval",
    "normalize_backtest_intervals",
]


def __getattr__(name: str):
    if name == "BacktestEngine":
        from .engine import BacktestEngine

        globals()[name] = BacktestEngine
        return BacktestEngine
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
