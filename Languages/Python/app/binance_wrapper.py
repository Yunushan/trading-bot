"""
Backward-compatible import shim for the Binance integration.

New code should import from ``app.integrations.exchanges.binance``.
This module stays in place so older call sites and standalone helpers do not
break while the source tree transitions away from the flat layout.
"""

from app.integrations.exchanges.binance import (
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
