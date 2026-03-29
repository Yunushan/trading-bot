"""Backward-compatible import shim for positions render helpers."""

from .render_runtime import (
    _mw_render_positions_table,
    configure_main_window_positions_render_runtime,
)

__all__ = [
    "_mw_render_positions_table",
    "configure_main_window_positions_render_runtime",
]
