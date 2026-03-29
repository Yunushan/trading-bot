"""Backward-compatible import shim for strategy control binding."""

from .control_runtime import (
    _stop_strategy_sync,
    apply_futures_modes,
    bind_main_window_control_runtime,
    on_leverage_changed,
    refresh_symbols,
    start_strategy,
    stop_strategy_async,
)

__all__ = [
    "_stop_strategy_sync",
    "apply_futures_modes",
    "bind_main_window_control_runtime",
    "on_leverage_changed",
    "refresh_symbols",
    "start_strategy",
    "stop_strategy_async",
]

