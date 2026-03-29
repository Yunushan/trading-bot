"""Backward-compatible import shim for strategy UI dashboard handlers."""

from .ui_dashboard_runtime import _on_dashboard_template_changed

__all__ = ["_on_dashboard_template_changed"]
