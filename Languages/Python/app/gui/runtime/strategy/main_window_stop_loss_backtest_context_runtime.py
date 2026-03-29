"""Backward-compatible import shim for backtest stop-loss handlers."""

from .stop_loss_backtest_context import (
    _backtest_stop_loss_update,
    _on_backtest_stop_loss_enabled,
    _on_backtest_stop_loss_mode_changed,
    _on_backtest_stop_loss_scope_changed,
    _on_backtest_stop_loss_value_changed,
    _update_backtest_stop_loss_widgets,
)

__all__ = [
    "_backtest_stop_loss_update",
    "_on_backtest_stop_loss_enabled",
    "_on_backtest_stop_loss_mode_changed",
    "_on_backtest_stop_loss_scope_changed",
    "_on_backtest_stop_loss_value_changed",
    "_update_backtest_stop_loss_widgets",
]
