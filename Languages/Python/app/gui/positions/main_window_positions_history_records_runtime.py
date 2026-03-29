"""Backward-compatible import shim for positions history-record helpers."""

from .history_records_runtime import (
    _mw_positions_records_per_trade,
    configure_main_window_positions_history_records_runtime,
)

__all__ = [
    "_mw_positions_records_per_trade",
    "configure_main_window_positions_history_records_runtime",
]

