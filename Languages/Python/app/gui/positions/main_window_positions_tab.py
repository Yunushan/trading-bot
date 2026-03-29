"""Backward-compatible import shim for the positions-tab binder surface."""

from .tab_runtime import _create_positions_tab, bind_main_window_positions_tab

__all__ = ["_create_positions_tab", "bind_main_window_positions_tab"]
