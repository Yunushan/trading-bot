from __future__ import annotations

import re
from datetime import datetime

from app.config import INDICATOR_DISPLAY_NAMES

_DEFAULT_CONNECTOR_BACKEND = "binance-sdk-derivatives-trading-usds-futures"

RECOMMENDED_CONNECTOR_BY_ACCOUNT = {
    "FUTURES": "binance-sdk-derivatives-trading-usds-futures",
    "SPOT": "binance-sdk-spot",
}


def bind_main_window_helper_runtime(*, default_connector_backend: str | None = None) -> None:
    global _DEFAULT_CONNECTOR_BACKEND
    if default_connector_backend:
        _DEFAULT_CONNECTOR_BACKEND = str(default_connector_backend)


def _normalize_connector_backend(value) -> str:
    text_raw = str(value or "").strip()
    if not text_raw:
        return _DEFAULT_CONNECTOR_BACKEND
    text = text_raw.lower()
    if text in {
        "binance-sdk-derivatives-trading-usds-futures",
        "binance_sdk_derivatives_trading_usds_futures",
    } or ("sdk" in text and "future" in text and ("usd" in text or "usds" in text)):
        return "binance-sdk-derivatives-trading-usds-futures"
    if text in {
        "binance-sdk-derivatives-trading-coin-futures",
        "binance_sdk_derivatives_trading_coin_futures",
    } or ("sdk" in text and "coin" in text and "future" in text):
        return "binance-sdk-derivatives-trading-coin-futures"
    if text in {"binance-sdk-spot", "binance_sdk_spot"} or ("sdk" in text and "spot" in text):
        return "binance-sdk-spot"
    if text == "ccxt" or "ccxt" in text:
        return "ccxt"
    if "connector" in text or "official" in text or text == "binance-connector":
        return "binance-connector"
    if "python" in text and "binance" in text:
        return "python-binance"
    return _DEFAULT_CONNECTOR_BACKEND


def _recommended_connector_for_key(account_key: str) -> str:
    key = (account_key or "").strip().upper()
    return RECOMMENDED_CONNECTOR_BY_ACCOUNT.get(key, _DEFAULT_CONNECTOR_BACKEND)


def _format_indicator_list(keys):
    if not keys:
        return "-"
    rendered = []
    for key in keys:
        rendered.append(INDICATOR_DISPLAY_NAMES.get(key, key))
    return ", ".join(rendered) if rendered else "-"


def _safe_float(value, default=0.0):
    try:
        if isinstance(value, str):
            value = value.replace("%", "").strip()
            if value == "":
                return float(default)
        return float(value)
    except Exception:
        return float(default)


def _safe_int(value, default=0):
    try:
        return int(float(value))
    except Exception:
        return int(default)


def _normalize_indicator_token(text: str) -> str:
    return re.sub(r"[^a-z0-9]", "", str(text or "").lower())


_INDICATOR_TOKEN_TO_KEY: dict[str, str] = {}
for _ind_key, _display_name in INDICATOR_DISPLAY_NAMES.items():
    _key_norm = str(_ind_key or "").strip().lower()
    _key_token = _normalize_indicator_token(_key_norm)
    if _key_token:
        _INDICATOR_TOKEN_TO_KEY.setdefault(_key_token, _key_norm)
    if isinstance(_display_name, str) and _display_name.strip():
        _display_token = _normalize_indicator_token(_display_name)
        if _display_token:
            _INDICATOR_TOKEN_TO_KEY.setdefault(_display_token, _key_norm)

_INDICATOR_TOKEN_ALIASES = {
    "stochrsi": "stoch_rsi",
    "stochasticrsi": "stoch_rsi",
    "srsi": "stoch_rsi",
    "williamsr": "willr",
    "williamspercentr": "willr",
    "wr": "willr",
    "wpr": "willr",
    "relativestrengthindex": "rsi",
}


def _canonicalize_indicator_key(value: str | None) -> str | None:
    if value is None:
        return None
    try:
        text = str(value).strip()
    except Exception:
        return None
    if not text:
        return None
    base = text.split("@", 1)[0].strip()
    low = base.lower()
    if not low:
        return None
    if low in INDICATOR_DISPLAY_NAMES:
        return low
    token = _normalize_indicator_token(low)
    if not token:
        return low
    alias = _INDICATOR_TOKEN_ALIASES.get(token)
    if alias:
        return alias
    mapped = _INDICATOR_TOKEN_TO_KEY.get(token)
    if mapped:
        return mapped
    return low


def _normalize_indicator_values(raw) -> list[str]:
    items: list[str] = []
    if isinstance(raw, (list, tuple, set)):
        iterable = raw
    elif raw in (None, "", False, True):
        iterable = []
    else:
        iterable = [raw]
    for item in iterable:
        canonical = _canonicalize_indicator_key(item)
        if canonical:
            items.append(canonical)
    if not items:
        return []
    return sorted(dict.fromkeys(items))


_INDICATOR_DESC_TOKENS = {
    key: _normalize_indicator_token(name)
    for key, name in INDICATOR_DISPLAY_NAMES.items()
    if isinstance(name, str) and name
}

_INDICATOR_DESC_HINTS = {
    "stoch_rsi": {"stochrsi", "stochasticrsi", "srsi"},
    "willr": {"williamsr", "williamspercentr", "wr", "wpr"},
    "rsi": {"rsi", "relativestrengthindex"},
}


def _infer_indicators_from_desc(desc: str | None) -> list[str]:
    if not desc:
        return []
    inferred: set[str] = set()
    segments = [seg.strip() for seg in str(desc).split("|") if "->" in seg]
    for segment in segments:
        norm_segment = _normalize_indicator_token(segment)
        if not norm_segment:
            continue
        for key, token in _INDICATOR_DESC_TOKENS.items():
            if token and token in norm_segment:
                inferred.add(key)
        for key, hints in _INDICATOR_DESC_HINTS.items():
            if any(hint in norm_segment for hint in hints):
                if key == "rsi" and (
                    "stochrsi" in norm_segment or "stochasticrsi" in norm_segment
                ):
                    continue
                inferred.add(key)
    return sorted(inferred)


def _resolve_trigger_indicators(raw, desc: str | None = None) -> list[str]:
    indicators = _normalize_indicator_values(raw)
    if not indicators and desc:
        indicators = _infer_indicators_from_desc(desc)
    if not indicators:
        return []
    return sorted(dict.fromkeys(indicators))


def _normalize_datetime_pair(value) -> tuple[str, str]:
    dt_obj = None
    text_value = ""
    if isinstance(value, datetime):
        dt_obj = value
    elif isinstance(value, (int, float)):
        try:
            dt_obj = datetime.fromtimestamp(float(value))
        except Exception:
            dt_obj = None
    elif isinstance(value, str):
        text_value = value.strip()
        if text_value:
            try:
                dt_obj = datetime.fromisoformat(text_value)
            except Exception:
                try:
                    dt_obj = datetime.strptime(text_value, "%Y-%m-%d %H:%M")
                except Exception:
                    dt_obj = None
    if dt_obj is not None:
        iso = dt_obj.isoformat()
        display = dt_obj.strftime("%Y-%m-%d %H:%M")
        return iso, display
    return text_value, text_value or ""


def _make_engine_key(symbol: str, interval: str, indicators: list[str] | None) -> str:
    base = f"{symbol}@{interval}"
    if indicators:
        base += "#" + ",".join(indicators)
    return base
