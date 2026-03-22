from __future__ import annotations

import time

_LOAD_POSITION_ALLOCATIONS = None


def _initialize_dashboard_runtime_state(
    self,
    *,
    current_max_closed_history,
    gui_max_closed_history,
):
    self._entry_intervals = {}
    self._entry_times = {}  # (sym, 'L'/'S') -> last trade time string
    self._entry_times_by_iv = {}

    persisted_mode = None
    try:
        mode_text = self.mode_combo.currentText() if hasattr(self, "mode_combo") else None
        persisted_mode = mode_text
    except Exception:
        pass

    load_allocations = _LOAD_POSITION_ALLOCATIONS
    if callable(load_allocations):
        loaded_allocations, loaded_records = load_allocations(mode=persisted_mode)
    else:
        loaded_allocations, loaded_records = ({}, {})

    self._entry_allocations = loaded_allocations or {}
    self._pending_close_times = {}
    self._open_position_records = loaded_records or {}
    self._closed_position_records = []
    self._engine_indicator_map = {}
    self._live_indicator_cache = {}
    try:
        ttl_value = float(
            self.config.get("positions_live_indicator_refresh_seconds", 8.0) or 8.0
        )
        self._live_indicator_cache_ttl = max(2.0, ttl_value)
    except Exception:
        self._live_indicator_cache_ttl = 8.0
    self._live_indicator_cache_last_cleanup = time.monotonic()
    self._positions_view_mode = "cumulative"

    try:
        cfg_max_hist = int(self.config.get("positions_closed_history_max", 500) or 500)
        resolved_max_closed_history = max(gui_max_closed_history, cfg_max_hist)
    except Exception:
        try:
            resolved_max_closed_history = max(current_max_closed_history, 500)
        except Exception:
            resolved_max_closed_history = 500

    try:
        self._pos_refresh_interval_ms = int(
            self.config.get("positions_refresh_interval_ms", 5000) or 5000
        )
    except Exception:
        self._pos_refresh_interval_ms = 5000

    return int(resolved_max_closed_history)


def bind_main_window_dashboard_state_runtime(
    MainWindow,
    *,
    load_position_allocations,
):
    global _LOAD_POSITION_ALLOCATIONS

    _LOAD_POSITION_ALLOCATIONS = load_position_allocations

    MainWindow._initialize_dashboard_runtime_state = _initialize_dashboard_runtime_state
