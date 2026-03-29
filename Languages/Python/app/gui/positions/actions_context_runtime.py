from __future__ import annotations

_SAVE_POSITION_ALLOCATIONS = None
_CLOSED_HISTORY_MAX = None
_POS_STATUS_COLUMN = 16
_DEFAULT_MAX_CLOSED_HISTORY = 200


def configure_positions_actions_runtime(
    *,
    save_position_allocations=None,
    closed_history_max_fn=None,
    pos_status_column: int = 16,
) -> None:
    global _SAVE_POSITION_ALLOCATIONS
    global _CLOSED_HISTORY_MAX
    global _POS_STATUS_COLUMN

    _SAVE_POSITION_ALLOCATIONS = save_position_allocations
    _CLOSED_HISTORY_MAX = closed_history_max_fn
    _POS_STATUS_COLUMN = int(pos_status_column)


def get_save_position_allocations():
    return _SAVE_POSITION_ALLOCATIONS


def get_pos_status_column() -> int:
    return int(_POS_STATUS_COLUMN)


def closed_history_max(self) -> int:
    func = _CLOSED_HISTORY_MAX
    if callable(func):
        try:
            return int(func(self))
        except Exception:
            pass
    try:
        cfg_val = int(self.config.get("positions_closed_history_max", 500) or 500)
    except Exception:
        cfg_val = 500
    return max(_DEFAULT_MAX_CLOSED_HISTORY, cfg_val)
