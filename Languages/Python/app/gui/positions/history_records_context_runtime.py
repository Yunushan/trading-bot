from __future__ import annotations

_CLOSED_HISTORY_MAX = None
_CLOSED_RECORD_STATES: set[str] = set()
_NORMALIZE_INDICATOR_VALUES = None
_DERIVE_MARGIN_SNAPSHOT = None
_RESOLVE_TRIGGER_INDICATORS = None


def configure_main_window_positions_history_records_runtime(
    *,
    closed_history_max_fn=None,
    closed_record_states=None,
    normalize_indicator_values=None,
    derive_margin_snapshot=None,
    resolve_trigger_indicators=None,
) -> None:
    global _CLOSED_HISTORY_MAX
    global _CLOSED_RECORD_STATES
    global _NORMALIZE_INDICATOR_VALUES
    global _DERIVE_MARGIN_SNAPSHOT
    global _RESOLVE_TRIGGER_INDICATORS

    _CLOSED_HISTORY_MAX = closed_history_max_fn
    _CLOSED_RECORD_STATES = set(closed_record_states or ())
    _NORMALIZE_INDICATOR_VALUES = normalize_indicator_values
    _DERIVE_MARGIN_SNAPSHOT = derive_margin_snapshot
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


def _normalize_indicator_values(raw) -> list[str]:
    func = _NORMALIZE_INDICATOR_VALUES
    if not callable(func):
        return []
    try:
        return list(func(raw))
    except Exception:
        return []


def _derive_margin_snapshot(
    position: dict | None,
    qty_hint: float = 0.0,
    entry_price_hint: float = 0.0,
) -> tuple[float, float, float, float]:
    func = _DERIVE_MARGIN_SNAPSHOT
    if not callable(func):
        return (0.0, 0.0, 0.0, 0.0)
    try:
        return func(position, qty_hint=qty_hint, entry_price_hint=entry_price_hint)
    except Exception:
        return (0.0, 0.0, 0.0, 0.0)


def _resolve_trigger_indicators_safe(raw, desc: str | None = None) -> list[str]:
    func = _RESOLVE_TRIGGER_INDICATORS
    if not callable(func):
        return []
    try:
        return list(func(raw, desc))
    except Exception:
        return []
