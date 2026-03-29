from __future__ import annotations

from .strategy_position_conflict_runtime import _resolve_indicator_conflicts
from .strategy_position_futures_runtime import (
    _compute_position_margin_fields,
    _current_futures_position_qty,
    _entry_margin_value,
    _purge_flat_futures_legs,
)
from .strategy_position_ledger_runtime import (
    _append_leg_entry,
    _decrement_leg_entry_qty,
    _remove_leg_entry,
    _sync_leg_entry_totals,
    _update_leg_snapshot,
)


def bind_strategy_position_state(strategy_cls) -> None:
    strategy_cls._update_leg_snapshot = _update_leg_snapshot
    strategy_cls._append_leg_entry = _append_leg_entry
    strategy_cls._resolve_indicator_conflicts = _resolve_indicator_conflicts
    strategy_cls._remove_leg_entry = _remove_leg_entry
    strategy_cls._decrement_leg_entry_qty = _decrement_leg_entry_qty
    strategy_cls._sync_leg_entry_totals = _sync_leg_entry_totals
    strategy_cls._entry_margin_value = staticmethod(_entry_margin_value)
    strategy_cls._current_futures_position_qty = _current_futures_position_qty
    strategy_cls._purge_flat_futures_legs = _purge_flat_futures_legs
    strategy_cls._compute_position_margin_fields = staticmethod(_compute_position_margin_fields)


__all__ = ["bind_strategy_position_state"]
