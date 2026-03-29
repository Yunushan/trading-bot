"""Backward-compatible import shim for strategy control shared helpers."""

from .control_shared_runtime import (
    _coerce_bool_safe,
    _format_indicator_list_safe,
    _get_strategy_engine_cls,
    _get_symbol_fetch_top_n,
    _make_engine_key_safe,
    _normalize_stop_loss_dict_safe,
    configure_main_window_control_shared_runtime,
)

__all__ = [
    "_coerce_bool_safe",
    "_format_indicator_list_safe",
    "_get_strategy_engine_cls",
    "_get_symbol_fetch_top_n",
    "_make_engine_key_safe",
    "_normalize_stop_loss_dict_safe",
    "configure_main_window_control_shared_runtime",
]
