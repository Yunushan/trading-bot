from __future__ import annotations

_CLOSED_HISTORY_MAX = None
_RESOLVE_TRIGGER_INDICATORS = None


def configure_main_window_positions_history_update_runtime(
    *,
    closed_history_max_fn=None,
    resolve_trigger_indicators=None,
) -> None:
    global _CLOSED_HISTORY_MAX
    global _RESOLVE_TRIGGER_INDICATORS

    _CLOSED_HISTORY_MAX = closed_history_max_fn
    _RESOLVE_TRIGGER_INDICATORS = resolve_trigger_indicators


def _closed_history_max(self) -> int:
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
    return max(200, cfg_val)


def _resolve_trigger_indicators_safe(raw, desc: str | None = None) -> list[str]:
    func = _RESOLVE_TRIGGER_INDICATORS
    if not callable(func):
        return []
    try:
        return list(func(raw, desc))
    except Exception:
        return []
