from __future__ import annotations

from .actions_close_runtime import close_position_single, make_close_btn
from .actions_context_runtime import closed_history_max, configure_positions_actions_runtime
from .actions_history_runtime import clear_positions_all, clear_positions_selected, snapshot_closed_position
from .actions_state_runtime import (
    clear_local_position_state,
    reduce_local_position_allocation_state,
    sync_local_position_tracking_from_allocations,
    sync_chart_to_active_positions,
)

_closed_history_max = closed_history_max
_mw_clear_positions_selected = clear_positions_selected
_mw_clear_positions_all = clear_positions_all
_mw_snapshot_closed_position = snapshot_closed_position
_mw_clear_local_position_state = clear_local_position_state
_mw_reduce_local_position_allocation_state = reduce_local_position_allocation_state
_mw_sync_local_position_tracking_from_allocations = sync_local_position_tracking_from_allocations
_mw_sync_chart_to_active_positions = sync_chart_to_active_positions
_mw_make_close_btn = make_close_btn
_mw_close_position_single = close_position_single


def bind_main_window_positions_actions_runtime(
    main_window_cls,
    *,
    save_position_allocations=None,
    closed_history_max_fn=None,
    pos_status_column: int = 16,
) -> None:
    configure_positions_actions_runtime(
        save_position_allocations=save_position_allocations,
        closed_history_max_fn=closed_history_max_fn,
        pos_status_column=pos_status_column,
    )

    main_window_cls._clear_positions_selected = _mw_clear_positions_selected
    main_window_cls._clear_positions_all = _mw_clear_positions_all
    main_window_cls._snapshot_closed_position = _mw_snapshot_closed_position
    main_window_cls._clear_local_position_state = _mw_clear_local_position_state
    main_window_cls._reduce_local_position_allocation_state = _mw_reduce_local_position_allocation_state
    main_window_cls._sync_local_position_tracking_from_allocations = _mw_sync_local_position_tracking_from_allocations
    main_window_cls._sync_chart_to_active_positions = _mw_sync_chart_to_active_positions
    main_window_cls._make_close_btn = _mw_make_close_btn
    main_window_cls._close_position_single = _mw_close_position_single
