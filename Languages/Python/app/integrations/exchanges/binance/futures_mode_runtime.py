"""Compatibility shim for the moved Binance futures mode helpers."""

from .runtime.futures_mode_runtime import (
    _ensure_symbol_margin,
    bind_binance_futures_mode_runtime,
    set_multi_assets_mode,
    set_position_mode,
)
