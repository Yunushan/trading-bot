"""Backward-compatible import shim for Binance futures close-all helpers."""

from app.integrations.exchanges.binance.positions import close_all_runtime as _close_all_runtime


def close_all_futures_positions(*args, **kwargs):
    return _close_all_runtime.close_all_futures_positions(*args, **kwargs)


__all__ = ["close_all_futures_positions"]
