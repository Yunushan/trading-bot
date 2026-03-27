"""Compatibility shim for the moved Binance market-data helpers."""

from .market.market_data import (
    _fetch_futures_klines_rest,
    _get_klines_range_custom,
    _get_klines_range_native,
    _interval_seconds_to_freq,
    _klines_raw_to_df,
    bind_binance_market_data,
    get_klines,
    get_klines_range,
)
