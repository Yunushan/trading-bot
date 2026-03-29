"""Backward-compatible import shim for strategy UI control handlers."""

from .ui_controls_runtime import (
    _apply_backtest_account_mode_constraints,
    _apply_lead_trader_state,
    _apply_runtime_account_mode_constraints,
    _enforce_portfolio_margin_constraints,
    _on_allow_opposite_changed,
    _on_backtest_account_mode_changed,
    _on_backtest_loop_changed,
    _on_lead_trader_option_changed,
    _on_lead_trader_toggled,
    _on_runtime_account_mode_changed,
    _on_runtime_loop_changed,
)

__all__ = [
    "_apply_backtest_account_mode_constraints",
    "_apply_lead_trader_state",
    "_apply_runtime_account_mode_constraints",
    "_enforce_portfolio_margin_constraints",
    "_on_allow_opposite_changed",
    "_on_backtest_account_mode_changed",
    "_on_backtest_loop_changed",
    "_on_lead_trader_option_changed",
    "_on_lead_trader_toggled",
    "_on_runtime_account_mode_changed",
    "_on_runtime_loop_changed",
]
