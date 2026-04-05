"""
Public reusable trading-domain package.

This package is the stable import surface for strategy, backtest, indicator,
and position helpers that should be shared across desktop, service, tests, and
future clients. The existing ``app.core`` package remains available as the
monolith-facing implementation namespace during the migration.
"""

from . import indicators
from .backtest import (
    BacktestEngine,
    BacktestRequest,
    BacktestRunResult,
    IndicatorDefinition,
    PairOverride,
)
from .positions import IntervalPositionGuard
from .strategy import StrategyEngine

__all__ = [
    "BacktestEngine",
    "BacktestRequest",
    "BacktestRunResult",
    "IndicatorDefinition",
    "IntervalPositionGuard",
    "PairOverride",
    "StrategyEngine",
    "indicators",
]
