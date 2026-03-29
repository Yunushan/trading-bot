from __future__ import annotations

from .futures_fill_summary_runtime import (
    _convert_asset_to_usdt,
    _summarize_futures_order_fills,
)
from .futures_position_close_runtime import (
    cancel_all_open_futures_orders,
    close_all_futures_positions,
    close_futures_leg_exact,
    close_futures_position,
)
from .futures_position_query_runtime import (
    get_futures_dual_side,
    get_net_futures_position_amt,
    list_open_futures_positions,
)
from .futures_positions_cache_runtime import (
    _format_quantity_for_order,
    _get_cached_futures_positions,
    _invalidate_futures_positions_cache,
    _store_futures_positions_cache,
)


def bind_binance_futures_positions(wrapper_cls):
    wrapper_cls._get_cached_futures_positions = _get_cached_futures_positions
    wrapper_cls._store_futures_positions_cache = _store_futures_positions_cache
    wrapper_cls._invalidate_futures_positions_cache = _invalidate_futures_positions_cache
    wrapper_cls._format_quantity_for_order = staticmethod(_format_quantity_for_order)
    wrapper_cls._convert_asset_to_usdt = _convert_asset_to_usdt
    wrapper_cls._summarize_futures_order_fills = _summarize_futures_order_fills
    wrapper_cls.get_futures_dual_side = get_futures_dual_side
    wrapper_cls.close_futures_leg_exact = close_futures_leg_exact
    wrapper_cls.close_futures_position = close_futures_position
    wrapper_cls.cancel_all_open_futures_orders = cancel_all_open_futures_orders
    wrapper_cls.close_all_futures_positions = close_all_futures_positions
    wrapper_cls.list_open_futures_positions = list_open_futures_positions
    wrapper_cls.get_net_futures_position_amt = get_net_futures_position_amt
