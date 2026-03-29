from __future__ import annotations

from . import history_update_context_runtime
from .history_update_close_runtime import close_confirmed_positions
from .history_update_lookup_runtime import (
    collect_missing_candidates,
    lookup_force_liquidation,
    resolve_live_keys,
)

configure_main_window_positions_history_update_runtime = (
    history_update_context_runtime.configure_main_window_positions_history_update_runtime
)
_closed_history_max = history_update_context_runtime._closed_history_max
_resolve_trigger_indicators_safe = history_update_context_runtime._resolve_trigger_indicators_safe


def _mw_update_position_history(self, positions_map: dict):
    try:
        if not hasattr(self, "_open_position_records"):
            self._open_position_records = {}
        if not hasattr(self, "_closed_position_records"):
            self._closed_position_records = []
        missing_counts = getattr(self, "_position_missing_counts", {})
        if not isinstance(missing_counts, dict):
            missing_counts = {}
        prev_records = getattr(self, "_open_position_records", {}) or {}
        pending_close_map = getattr(self, "_pending_close_times", {})
        closed_history_max = _closed_history_max(self)
        candidates = collect_missing_candidates(
            self,
            positions_map,
            prev_records,
            missing_counts,
            pending_close_map,
        )

        live_keys = resolve_live_keys(self, candidates) if candidates else set()
        allow_missing_autoclose = bool(self.config.get("positions_missing_autoclose", True))

        confirmed_closed: list[tuple[str, str]] = []
        for key in candidates:
            if live_keys is None or key in live_keys:
                if key in prev_records:
                    positions_map.setdefault(key, prev_records[key])
                missing_counts[key] = 0
            else:
                if allow_missing_autoclose:
                    confirmed_closed.append(key)
                else:
                    prev_records.pop(key, None)
                    missing_counts.pop(key, None)

        if confirmed_closed:
            close_confirmed_positions(
                self,
                confirmed_closed,
                prev_records,
                pending_close_map,
                closed_history_max=closed_history_max,
                resolve_trigger_indicators_safe=_resolve_trigger_indicators_safe,
                lookup_force_liquidation=lookup_force_liquidation,
            )
            for key in confirmed_closed:
                missing_counts.pop(key, None)

        self._open_position_records = positions_map
        self._position_missing_counts = missing_counts
    except Exception:
        pass


__all__ = [
    "configure_main_window_positions_history_update_runtime",
    "_closed_history_max",
    "_resolve_trigger_indicators_safe",
    "_mw_update_position_history",
]
