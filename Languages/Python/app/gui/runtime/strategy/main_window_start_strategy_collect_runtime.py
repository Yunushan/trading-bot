"""Backward-compatible import shim for strategy start context helpers."""

from .start_collect_runtime import (
    StrategyStartContext,
    _build_strategy_combos,
    _collect_config_pair_entries,
    _collect_selected_pair_entries,
    _collect_strategy_start_context,
)

__all__ = [
    "StrategyStartContext",
    "_build_strategy_combos",
    "_collect_config_pair_entries",
    "_collect_selected_pair_entries",
    "_collect_strategy_start_context",
]
