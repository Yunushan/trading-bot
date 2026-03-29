from __future__ import annotations


def refresh_positions(self, symbols=None, *args, **kwargs):
    """Manual refresh of positions: reconfigure worker and trigger an immediate tick."""
    try:
        try:
            self._reconfigure_positions_worker(symbols=symbols)
        except Exception:
            pass
        try:
            self.trigger_positions_refresh()
        except Exception:
            pass
        self.log("Positions refresh requested.")
    except Exception as e:
        try:
            self.log(f"Refresh positions error: {e}")
        except Exception:
            pass


def _apply_positions_refresh_settings(self):
    try:
        raw_val = self.config.get("positions_refresh_interval_ms", getattr(self, "_pos_refresh_interval_ms", 5000))
        try:
            interval = int(raw_val)
        except Exception:
            interval = getattr(self, "_pos_refresh_interval_ms", 5000)
        interval = max(2000, min(interval, 60000))
        self._pos_refresh_interval_ms = interval
        self.config["positions_refresh_interval_ms"] = interval
        self.req_pos_start.emit(interval)
    except Exception:
        pass


def trigger_positions_refresh(self, interval_ms: int | None = None):
    try:
        if interval_ms is None:
            interval = getattr(self, "_pos_refresh_interval_ms", 5000)
        else:
            interval = int(interval_ms)
    except Exception:
        interval = getattr(self, "_pos_refresh_interval_ms", 5000)
    if interval <= 0:
        interval = 5000
    self._pos_refresh_interval_ms = interval
    try:
        self.req_pos_start.emit(interval)
    except Exception:
        pass


__all__ = [
    "_apply_positions_refresh_settings",
    "refresh_positions",
    "trigger_positions_refresh",
]
