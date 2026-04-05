from __future__ import annotations

import re

from app.config import INDICATOR_DISPLAY_NAMES


_FLOAT_RE = re.compile(r"-?\d+(?:\.\d+)?")
_ACTION_RE = re.compile(r"->\s*(BUY|SELL)", re.IGNORECASE)
_INTERVAL_RE = re.compile(r"^\s*(\d+(?:\.\d+)?)\s*([A-Za-z]+)?\s*$")
_INDICATOR_SHORT_LABEL_OVERRIDES = {
    "stoch_rsi": "SRSI",
    "rsi": "RSI",
    "willr": "W%R",
}
_INTERVAL_UNIT_ALIASES = {
    "": "m",
    "s": "s",
    "sec": "s",
    "secs": "s",
    "second": "s",
    "seconds": "s",
    "m": "m",
    "min": "m",
    "mins": "m",
    "minute": "m",
    "minutes": "m",
    "h": "h",
    "hr": "h",
    "hrs": "h",
    "hour": "h",
    "hours": "h",
    "d": "d",
    "day": "d",
    "days": "d",
    "w": "w",
    "wk": "w",
    "wks": "w",
    "week": "w",
    "weeks": "w",
}
_CANONICAL_INTERVAL_BY_SECONDS = {
    60.0: "1m",
    180.0: "3m",
    300.0: "5m",
    900.0: "15m",
    1800.0: "30m",
    3600.0: "1h",
    7200.0: "2h",
    14400.0: "4h",
    21600.0: "6h",
    28800.0: "8h",
    43200.0: "12h",
    86400.0: "1d",
    259200.0: "3d",
    604800.0: "1w",
}

CLOSED_RECORD_STATES = {
    "closed",
    "liquidated",
    "liquidation",
    "error",
    "stopped",
}

CLOSED_ALLOCATION_STATES = {
    "closed",
    "error",
    "cancelled",
    "canceled",
    "liquidated",
    "liquidation",
    "stopped",
    "completed",
    "filled",
}


def indicator_short_label(indicator_key: str) -> str:
    key_norm = str(indicator_key or "").strip().lower()
    if not key_norm:
        return "-"
    if key_norm in _INDICATOR_SHORT_LABEL_OVERRIDES:
        return _INDICATOR_SHORT_LABEL_OVERRIDES[key_norm]
    display = INDICATOR_DISPLAY_NAMES.get(key_norm)
    if display:
        display_text = str(display).strip()
        if "(" in display_text and ")" in display_text:
            candidate = display_text.rsplit("(", 1)[-1].rstrip(")")
            if candidate.strip():
                return candidate.strip()
        first_word = display_text.split()[0]
        if first_word:
            return first_word.upper()
    return key_norm.upper()


def indicator_entry_signature(text: str) -> tuple[str, str]:
    parts = text.split("@", 1)
    label_part = parts[0].strip().lower()
    interval_part = ""
    if len(parts) == 2:
        remainder = parts[1]
        interval_part = normalize_interval_token(remainder.split(None, 1)[0].strip()) or ""
    return label_part, interval_part


def dedupe_indicator_entries(entries: list[str] | None) -> list[str]:
    if not entries:
        return []
    seen: set[tuple[str, str]] = set()
    deduped: list[str] = []
    for entry in entries:
        sig = indicator_entry_signature(entry)
        if sig in seen:
            continue
        seen.add(sig)
        deduped.append(entry)
    return deduped


def dedupe_indicator_entries_normalized(
    entries: list[str] | None,
    *,
    normalize_indicator_token,
) -> list[str]:
    if not entries:
        return []
    seen_idx: dict[tuple[str, str], int] = {}
    deduped: list[str] = []
    for entry in entries:
        label_part, interval_part = indicator_entry_signature(entry)
        label_key = normalize_indicator_token(label_part) or label_part
        interval_key = normalize_indicator_token(interval_part) or interval_part
        sig = (label_key, interval_key)
        prior = seen_idx.get(sig)
        if prior is None:
            seen_idx[sig] = len(deduped)
            deduped.append(entry)
        else:
            deduped[prior] = entry
    return deduped


def normalize_interval_token(value: str | None) -> str | None:
    if not value:
        return None
    try:
        raw = str(value).strip()
    except Exception:
        return None
    if not raw:
        return None
    if raw == "1M":
        return "1mo"
    lower = raw.lower()
    if lower in {"1mo", "1mon", "1month", "1months"}:
        return "1mo"
    match = _INTERVAL_RE.match(raw)
    if not match:
        return lower
    amount_raw, unit_raw = match.groups()
    unit_norm = _INTERVAL_UNIT_ALIASES.get(str(unit_raw or "").strip().lower(), None)
    if unit_norm is None:
        return lower
    try:
        amount = float(amount_raw)
    except Exception:
        return lower
    if unit_norm == "s":
        seconds = amount
    elif unit_norm == "m":
        seconds = amount * 60.0
    elif unit_norm == "h":
        seconds = amount * 3600.0
    elif unit_norm == "d":
        seconds = amount * 86400.0
    elif unit_norm == "w":
        seconds = amount * 604800.0
    else:
        return lower
    canonical = _CANONICAL_INTERVAL_BY_SECONDS.get(seconds)
    if canonical:
        return canonical
    if amount.is_integer():
        amount_token = str(int(amount))
    else:
        amount_token = str(amount).rstrip("0").rstrip(".")
    return f"{amount_token}{unit_norm}"


def format_interval_display_token(value: str | None) -> str:
    normalized = normalize_interval_token(value)
    if not normalized:
        try:
            return str(value or "").strip().upper()
        except Exception:
            return ""
    if normalized == "1mo":
        return "1M"
    return normalized.upper()


def normalize_trigger_actions_map(
    raw_actions,
    *,
    canonicalize_indicator_key,
) -> dict[str, str]:
    if not isinstance(raw_actions, dict):
        return {}
    normalized: dict[str, str] = {}
    for raw_key, raw_action in raw_actions.items():
        key_norm = canonicalize_indicator_key(raw_key)
        action_norm = str(raw_action or "").strip().lower()
        if not key_norm or action_norm not in {"buy", "sell"}:
            continue
        normalized[key_norm] = action_norm.title()
    return normalized


def filter_indicator_entries_for_interval(
    entries: list[str],
    interval_hint: str | None,
    *,
    include_non_matching: bool = True,
) -> list[str]:
    if not entries:
        return []
    interval_targets: list[str] = []
    if interval_hint:
        for part in str(interval_hint).split(","):
            token = normalize_interval_token(part)
            if token and token not in interval_targets:
                interval_targets.append(token)
    seen: set[tuple[str, str]] = set()
    filtered: list[str] = []

    def _interval_token(text: str) -> str | None:
        if "@" not in text:
            return None
        return normalize_interval_token(text.split("@", 1)[1].split(None, 1)[0].strip())

    def _label_token(text: str) -> str:
        return text.split("@", 1)[0].strip().lower()

    matched: list[str] = []
    if interval_targets:
        for target in interval_targets:
            for text in entries:
                token = _interval_token(text)
                if token != target:
                    continue
                label = _label_token(text)
                sig = (label, token)
                if sig in seen:
                    continue
                seen.add(sig)
                matched.append(text)
    if matched:
        return dedupe_indicator_entries(matched)
    any_interval_token = any(_interval_token(text) is not None for text in entries)
    if not any_interval_token:
        return dedupe_indicator_entries(entries)
    if not include_non_matching:
        return []
    for text in entries:
        token = _interval_token(text)
        if token is None:
            continue
        label = _label_token(text)
        sig = (label, token)
        if sig in seen:
            continue
        seen.add(sig)
        filtered.append(text)
    return dedupe_indicator_entries(filtered or entries)
