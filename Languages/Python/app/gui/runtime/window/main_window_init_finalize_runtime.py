"""Backward-compatible import shim for window init-finalize helpers."""

from .init_finalize_runtime import _finalize_init_ui, bind_main_window_init_finalize_runtime

__all__ = ["_finalize_init_ui", "bind_main_window_init_finalize_runtime"]
