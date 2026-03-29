"""Backward-compatible import shim for strategy context helpers."""

from .context_runtime import (
    _canonical_side_from_text,
    _canonicalize_interval,
    _collect_strategy_indicators,
    _position_stop_loss_enabled,
    _resolve_dashboard_side,
    bind_main_window_strategy_context_runtime,
)

__all__ = [
    "_canonical_side_from_text",
    "_canonicalize_interval",
    "_collect_strategy_indicators",
    "_position_stop_loss_enabled",
    "_resolve_dashboard_side",
    "bind_main_window_strategy_context_runtime",
]
