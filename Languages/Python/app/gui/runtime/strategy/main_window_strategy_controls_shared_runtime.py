"""Backward-compatible import shim for strategy controls shared helpers."""

from .controls_shared_runtime import (
    _normalize_connector_backend_value,
    _normalize_position_pct_units,
    _normalize_stop_loss,
    configure_main_window_strategy_controls_shared_runtime,
    side_labels,
)

__all__ = [
    "_normalize_connector_backend_value",
    "_normalize_position_pct_units",
    "_normalize_stop_loss",
    "configure_main_window_strategy_controls_shared_runtime",
    "side_labels",
]
