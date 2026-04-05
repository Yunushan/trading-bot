"""
Backtest-domain helpers shared by desktop and service runtimes.
"""

from .engine import BacktestEngine
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
