"""
Stable backtest API for reusable trading-domain consumers.
"""

from app.core.backtest import (
    BacktestDataQualityError,
    BacktestDataQualityReport,
    BacktestEngine,
    BacktestRequest,
    BacktestRunResult,
    IndicatorDefinition,
    PairOverride,
    inspect_backtest_frame,
    validate_backtest_frame,
)

__all__ = [
    "BacktestEngine",
    "BacktestDataQualityError",
    "BacktestDataQualityReport",
    "BacktestRequest",
    "BacktestRunResult",
    "IndicatorDefinition",
    "PairOverride",
    "inspect_backtest_frame",
    "validate_backtest_frame",
]
