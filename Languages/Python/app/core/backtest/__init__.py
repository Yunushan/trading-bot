"""
Backtest-domain helpers shared by desktop and service runtimes.
"""

from .intervals import normalize_backtest_interval, normalize_backtest_intervals
from .models import BacktestRequest, BacktestRunResult, IndicatorDefinition, PairOverride

__all__ = [
    "BacktestEngine",
    "BacktestDataQualityError",
    "BacktestDataQualityReport",
    "BacktestRequest",
    "BacktestRunResult",
    "IndicatorDefinition",
    "PairOverride",
    "inspect_backtest_frame",
    "normalize_backtest_interval",
    "normalize_backtest_intervals",
    "validate_backtest_frame",
]


_LAZY_DATA_QUALITY_EXPORTS = {
    "BacktestDataQualityError",
    "BacktestDataQualityReport",
    "inspect_backtest_frame",
    "validate_backtest_frame",
}


def __getattr__(name: str):
    if name == "BacktestEngine":
        from .engine import BacktestEngine

        globals()[name] = BacktestEngine
        return BacktestEngine
    if name in _LAZY_DATA_QUALITY_EXPORTS:
        from . import data_quality

        value = getattr(data_quality, name)
        globals()[name] = value
        return value
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
