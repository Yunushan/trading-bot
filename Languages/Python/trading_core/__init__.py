"""
Public reusable trading-domain package.

This package is the stable import surface for strategy, backtest, indicator,
and position helpers that should be shared across desktop, service, tests, and
future clients. The existing ``app.core`` package remains available as the
monolith-facing implementation namespace during the migration.
"""

from importlib import import_module

from .orders import OrderSubmitIntent, order_submit_intent_from_params, validate_order_submit_intent

__all__ = [
    "BacktestEngine",
    "BacktestRequest",
    "BacktestRunResult",
    "IndicatorDefinition",
    "IntervalPositionGuard",
    "OrderSubmitIntent",
    "PairOverride",
    "StrategyEngine",
    "indicators",
    "order_submit_intent_from_params",
    "validate_order_submit_intent",
]


def __getattr__(name: str):
    if name == "indicators":
        return import_module(f"{__name__}.indicators")
    if name in {"BacktestEngine", "BacktestRequest", "BacktestRunResult", "IndicatorDefinition", "PairOverride"}:
        backtest_module = import_module(f"{__name__}.backtest")
        return getattr(backtest_module, name)
    if name == "IntervalPositionGuard":
        from .positions import IntervalPositionGuard

        return IntervalPositionGuard
    if name == "StrategyEngine":
        from .strategy import StrategyEngine

        return StrategyEngine
    raise AttributeError(name)
