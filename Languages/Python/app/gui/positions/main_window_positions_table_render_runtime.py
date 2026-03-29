"""Backward-compatible import shim for positions table-render helpers."""

from .table_render_runtime import (
    _mw_render_positions_table,
    configure_main_window_positions_render_runtime,
)

__all__ = [
    "_mw_render_positions_table",
    "configure_main_window_positions_render_runtime",
]
