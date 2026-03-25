"""
Binance integration package.

This package contains the primary live/demo exchange connector path used by the
desktop app, service backtest runner, and related tools.
"""

from .wrapper import (
    BinanceWrapper,
    DEFAULT_CONNECTOR_BACKEND,
    MAX_FUTURES_LEVERAGE,
    NetworkConnectivityError,
    _coerce_interval_seconds,
    _normalize_connector_choice,
    normalize_margin_ratio,
)

__all__ = [
    "BinanceWrapper",
    "DEFAULT_CONNECTOR_BACKEND",
    "MAX_FUTURES_LEVERAGE",
    "NetworkConnectivityError",
    "_coerce_interval_seconds",
    "_normalize_connector_choice",
    "normalize_margin_ratio",
]
