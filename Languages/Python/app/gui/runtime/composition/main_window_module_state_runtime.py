"""Backward-compatible import shim for main-window module-state composition."""

from .module_state_runtime import install_main_window_module_state

__all__ = ["install_main_window_module_state"]
