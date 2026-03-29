"""Backward-compatible import shim for window portfolio helpers."""

from .portfolio_runtime import _compute_global_pnl_totals, _update_positions_balance_labels

__all__ = ["_compute_global_pnl_totals", "_update_positions_balance_labels"]
