from __future__ import annotations


def _make_engine_key(
    symbol: str,
    interval: str,
    indicators: list[str] | None = None,
    *,
    make_engine_key=None,
) -> str:
    if callable(make_engine_key):
        try:
            return str(make_engine_key(symbol, interval, indicators))
        except Exception:
            pass
    base = f"{symbol}:{interval}"
    if indicators:
        return f"{base}|{','.join(indicators)}"
    return base


def _coerce_bool(value, default=False, *, coerce_bool=None):
    if callable(coerce_bool):
        try:
            return coerce_bool(value, default)
        except Exception:
            pass
    return bool(default)


def _normalize_stop_loss(value, *, normalize_stop_loss_dict=None):
    if callable(normalize_stop_loss_dict):
        try:
            return normalize_stop_loss_dict(value)
        except Exception:
            pass
    return value


def _format_indicator_list(keys, *, format_indicator_list=None) -> str:
    if callable(format_indicator_list):
        try:
            return str(format_indicator_list(keys))
        except Exception:
            pass
    try:
        return ", ".join(str(key).strip() for key in (keys or []) if str(key).strip())
    except Exception:
        return ""


def _normalize_indicator_keys(keys) -> list[str]:
    if keys is None or isinstance(keys, (str, bytes)):
        return []
    try:
        return sorted({str(key).strip() for key in keys if str(key).strip()})
    except Exception:
        return []
