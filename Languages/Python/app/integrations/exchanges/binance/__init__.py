"""
Binance integration package.

This package contains the primary live/demo exchange connector path used by the
desktop app, service backtest runner, and related tools.

Keep the connector exports lazy so offline administration modules can use the
package without importing the exchange SDK and its asynchronous networking
runtime. The public exports remain available on first access.
"""

from importlib import import_module

__all__ = [
    "BinanceWrapper",
    "DEFAULT_CONNECTOR_BACKEND",
    "MAX_FUTURES_LEVERAGE",
    "NetworkConnectivityError",
    "_coerce_interval_seconds",
    "_normalize_connector_choice",
    "normalize_margin_ratio",
]


def __getattr__(name: str):
    if name not in __all__:
        raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
    wrapper = import_module(".wrapper", __name__)
    value = getattr(wrapper, name)
    globals()[name] = value
    return value


def __dir__() -> list[str]:
    return sorted(set(globals()) | set(__all__))
