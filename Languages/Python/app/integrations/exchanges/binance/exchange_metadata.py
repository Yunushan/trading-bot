"""Compatibility shim for the moved Binance exchange metadata helpers."""

from .metadata.exchange_metadata import (
    bind_binance_exchange_metadata,
    clamp_futures_leverage,
    fetch_symbols,
    get_base_quote_assets,
    get_futures_exchange_info,
    get_futures_max_leverage,
    get_futures_symbol_filters,
    get_futures_symbol_info,
    get_recent_force_orders,
    get_spot_symbol_filters,
    get_symbol_info_spot,
    get_symbol_quote_precision_spot,
)
