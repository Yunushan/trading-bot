from __future__ import annotations

from . import signal_runtime

_MAX_CLOSED_HISTORY = 200
_RESOLVE_TRIGGER_INDICATORS = None
_SAVE_POSITION_ALLOCATIONS = None
_NORMALIZE_TRIGGER_ACTIONS_MAP = None


def _resolve_trigger_indicators_safe(raw, desc: str | None = None) -> list[str]:
    func = _RESOLVE_TRIGGER_INDICATORS
    if not callable(func):
        return []
    try:
        return list(func(raw, desc))
    except Exception:
        return []


def _normalize_trigger_actions_map_safe(raw) -> dict:
    func = _NORMALIZE_TRIGGER_ACTIONS_MAP
    if not callable(func):
        return {}
    try:
        normalized = func(raw) or {}
    except Exception:
        return {}
    return dict(normalized) if isinstance(normalized, dict) else {}


def _save_position_allocations_safe(
    entry_allocations,
    open_position_records,
    *,
    mode=None,
) -> None:
    func = _SAVE_POSITION_ALLOCATIONS
    if not callable(func):
        return
    try:
        func(entry_allocations, open_position_records, mode=mode)
    except Exception:
        pass


def bind_main_window_trade_runtime(
    main_window_cls,
    *,
    resolve_trigger_indicators=None,
    save_position_allocations=None,
    normalize_trigger_actions_map=None,
    max_closed_history: int = 200,
) -> None:
    global _MAX_CLOSED_HISTORY
    global _RESOLVE_TRIGGER_INDICATORS
    global _SAVE_POSITION_ALLOCATIONS
    global _NORMALIZE_TRIGGER_ACTIONS_MAP

    _MAX_CLOSED_HISTORY = max(1, int(max_closed_history))
    _RESOLVE_TRIGGER_INDICATORS = resolve_trigger_indicators
    _SAVE_POSITION_ALLOCATIONS = save_position_allocations
    _NORMALIZE_TRIGGER_ACTIONS_MAP = normalize_trigger_actions_map

    main_window_cls.log = _mw_log
    main_window_cls._trade_mux = _mw_trade_mux
    main_window_cls._on_trade_signal = _mw_on_trade_signal


def _mw_log(self, msg: str):
    try:
        self.log_signal.emit(str(msg))
    except Exception:
        pass


def _mw_trade_mux(self, evt: dict):
    try:
        guard = getattr(self, "guard", None)
        hook = getattr(guard, "trade_hook", None)
        if callable(hook):
            hook(evt)
    except Exception:
        pass
    try:
        self.trade_signal.emit(evt)
    except Exception:
        pass


def _mw_on_trade_signal(self, order_info: dict):
    return signal_runtime.handle_trade_signal(
        self,
        order_info,
        max_closed_history=_MAX_CLOSED_HISTORY,
        resolve_trigger_indicators=_resolve_trigger_indicators_safe,
        normalize_trigger_actions_map=_normalize_trigger_actions_map_safe,
        save_position_allocations=_save_position_allocations_safe,
    )
