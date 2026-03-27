from __future__ import annotations

_STRATEGY_ENGINE_CLS = None
_MAKE_ENGINE_KEY = None
_COERCE_BOOL = None
_NORMALIZE_STOP_LOSS_DICT = None
_FORMAT_INDICATOR_LIST = None
_SYMBOL_FETCH_TOP_N = 200


def configure_main_window_control_shared_runtime(
    *,
    strategy_engine_cls=None,
    make_engine_key=None,
    coerce_bool=None,
    normalize_stop_loss_dict=None,
    format_indicator_list=None,
    symbol_fetch_top_n: int = 200,
) -> None:
    global _STRATEGY_ENGINE_CLS
    global _MAKE_ENGINE_KEY
    global _COERCE_BOOL
    global _NORMALIZE_STOP_LOSS_DICT
    global _FORMAT_INDICATOR_LIST
    global _SYMBOL_FETCH_TOP_N

    _STRATEGY_ENGINE_CLS = strategy_engine_cls
    _MAKE_ENGINE_KEY = make_engine_key
    _COERCE_BOOL = coerce_bool
    _NORMALIZE_STOP_LOSS_DICT = normalize_stop_loss_dict
    _FORMAT_INDICATOR_LIST = format_indicator_list
    _SYMBOL_FETCH_TOP_N = max(1, int(symbol_fetch_top_n))


def _make_engine_key_safe(symbol: str, interval: str, indicators: list[str] | None = None) -> str:
    func = _MAKE_ENGINE_KEY
    if not callable(func):
        base = f"{symbol}:{interval}"
        if indicators:
            return f"{base}|{','.join(indicators)}"
        return base
    try:
        return str(func(symbol, interval, indicators))
    except Exception:
        base = f"{symbol}:{interval}"
        if indicators:
            return f"{base}|{','.join(indicators)}"
        return base


def _coerce_bool_safe(value, default=False):
    func = _COERCE_BOOL
    if not callable(func):
        return bool(default)
    try:
        return func(value, default)
    except Exception:
        return bool(default)


def _normalize_stop_loss_dict_safe(value):
    func = _NORMALIZE_STOP_LOSS_DICT
    if not callable(func):
        return value
    try:
        return func(value)
    except Exception:
        return value


def _format_indicator_list_safe(keys) -> str:
    func = _FORMAT_INDICATOR_LIST
    if not callable(func):
        try:
            return ", ".join(str(key).strip() for key in (keys or []) if str(key).strip())
        except Exception:
            return ""
    try:
        return str(func(keys))
    except Exception:
        return ""


def _get_strategy_engine_cls():
    return _STRATEGY_ENGINE_CLS


def _get_symbol_fetch_top_n() -> int:
    return max(1, int(_SYMBOL_FETCH_TOP_N or 1))
