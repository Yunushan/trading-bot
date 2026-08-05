from __future__ import annotations

_UNIT_ALIASES = {
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
    "y": "y",
    "yr": "y",
    "yrs": "y",
    "year": "y",
    "years": "y",
}
_CANONICAL_INTERVAL_BY_SECONDS = {
    30.0: "30s",
    45.0: "45s",
    60.0: "1m",
    180.0: "3m",
    300.0: "5m",
    600.0: "10m",
    900.0: "15m",
    1200.0: "20m",
    1800.0: "30m",
    2700.0: "45m",
    3600.0: "1h",
    7200.0: "2h",
    10800.0: "3h",
    14400.0: "4h",
    18000.0: "5h",
    21600.0: "6h",
    25200.0: "7h",
    28800.0: "8h",
    32400.0: "9h",
    36000.0: "10h",
    39600.0: "11h",
    43200.0: "12h",
    86400.0: "1d",
    172800.0: "2d",
    259200.0: "3d",
    345600.0: "4d",
    432000.0: "5d",
    518400.0: "6d",
    604800.0: "1w",
    1209600.0: "2w",
    1814400.0: "3w",
}


def _format_amount(amount: float) -> str:
    if amount.is_integer():
        return str(int(amount))
    return str(amount).rstrip("0").rstrip(".")


def _split_numeric_unit(raw: str) -> tuple[str, str] | None:
    """Parse a bounded numeric interval without backtracking regexes."""
    text = raw.strip()
    index = 0
    while index < len(text) and text[index].isdigit():
        index += 1
    if index == 0:
        return None
    if index < len(text) and text[index] == ".":
        index += 1
        fraction_start = index
        while index < len(text) and text[index].isdigit():
            index += 1
        if index == fraction_start:
            return None
    amount_raw = text[:index]
    unit_raw = text[index:].strip()
    if unit_raw and not unit_raw.isalpha():
        return None
    return amount_raw, unit_raw


def normalize_backtest_interval(value: str | None) -> str:
    if value is None:
        return ""
    raw = str(value).strip()
    if not raw:
        return ""
    numeric_unit = _split_numeric_unit(raw)
    if numeric_unit is None:
        return raw.lower()
    amount_raw, unit_raw = numeric_unit
    if unit_raw == "M" and amount_raw.isdigit():
        return f"{int(amount_raw)}mo"
    if unit_raw.strip().lower() in {"mo", "mon", "mons", "month", "months"}:
        try:
            amount = float(amount_raw)
        except Exception:
            return raw.lower()
        return f"{_format_amount(amount)}mo"
    unit_norm = _UNIT_ALIASES.get(str(unit_raw or "").strip().lower())
    if unit_norm is None:
        return raw.lower()
    try:
        amount = float(amount_raw)
    except Exception:
        return raw.lower()
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
        seconds = None
    if seconds is not None:
        canonical = _CANONICAL_INTERVAL_BY_SECONDS.get(seconds)
        if canonical:
            return canonical
    return f"{_format_amount(amount)}{unit_norm}"


def normalize_backtest_intervals(values) -> list[str]:  # noqa: ANN001
    if not isinstance(values, (list, tuple, set)):
        return []
    items: list[str] = []
    seen: set[str] = set()
    for value in values:
        normalized = normalize_backtest_interval(value)
        if not normalized or normalized in seen:
            continue
        seen.add(normalized)
        items.append(normalized)
    return items


__all__ = [
    "normalize_backtest_interval",
    "normalize_backtest_intervals",
]
