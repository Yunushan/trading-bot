"""Pure interval timing rules shared by Python runtime and native fixtures."""

from __future__ import annotations


def interval_seconds_value(interval_value: object) -> float:
    """Return Python's indicator and guard interval value semantics."""

    try:
        text = str(interval_value or "1m")
        if text.endswith("s"):
            return float(int(text[:-1]))
        if text.endswith("m"):
            return float(int(text[:-1]) * 60)
        if text.endswith("h"):
            return float(int(text[:-1]) * 3600)
        if text.endswith("d"):
            return float(int(text[:-1]) * 86400)
    except (AttributeError, TypeError, ValueError, OverflowError):
        return 60.0
    return 60.0


def interval_seconds(interval: str) -> int:
    """Return Python's worker-loop interval semantics."""

    try:
        if interval.endswith("s"):
            return int(interval[:-1])
        if interval.endswith("m"):
            return int(interval[:-1]) * 60
        if interval.endswith("h"):
            return int(interval[:-1]) * 3600
        if interval.endswith("d"):
            return int(interval[:-1]) * 86400
        if interval.endswith("w"):
            return int(interval[:-1]) * 7 * 86400
        return int(interval)
    except Exception:
        return 60


def backtest_interval_seconds(interval: str | None) -> float:
    """Return the exact interval coercion used by Python backtest loading."""

    try:
        iv = (interval or "").strip().lower()
        if not iv:
            return 60.0
        unit = iv[-1]
        value_part = iv[:-1] if unit.isalpha() else iv
        value = float(value_part or 0.0)
        if unit == "s":
            return max(value, 1.0)
        if unit == "m":
            return max(value * 60.0, 1.0)
        if unit == "h":
            return max(value * 3600.0, 1.0)
        if unit == "d":
            return max(value * 86400.0, 1.0)
        if unit == "w":
            return max(value * 7 * 86400.0, 1.0)
        return max(float(iv), 1.0)
    except Exception:
        return 60.0
