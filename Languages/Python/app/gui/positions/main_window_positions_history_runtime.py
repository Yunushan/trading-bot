"""Backward-compatible import shim for positions history helpers."""

from .history_runtime import (
    _mw_positions_records_per_trade,
    _mw_update_position_history,
    configure_main_window_positions_history_runtime,
)

__all__ = [
    "_mw_positions_records_per_trade",
    "_mw_update_position_history",
    "configure_main_window_positions_history_runtime",
]
