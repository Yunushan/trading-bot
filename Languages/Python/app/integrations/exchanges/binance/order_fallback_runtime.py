"""Compatibility shim for the moved Binance order fallback helpers."""

from .orders.order_fallback_runtime import (
    _futures_create_order_with_fallback,
    _is_testnet_mode,
    _testnet_order_fallback_client,
    bind_binance_order_fallback_runtime,
)
