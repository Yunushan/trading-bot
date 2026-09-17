"""Validation and freshness diagnostics for live OHLCV market data.

Historical backtests intentionally use a separate retrieval path.  The helpers in
this module are for data that may drive a live signal or an exposure-increasing
order and therefore keep the exchange event time and transport receipt time
separate.  A cached frame must never become fresh merely because it was read from
the local cache.
"""

from __future__ import annotations

from collections.abc import Mapping
import math
import time

import pandas as pd

from ..transport.helpers import _coerce_interval_seconds


OHLCV_COLUMNS = ("open", "high", "low", "close", "volume")
_MAX_FUTURE_SKEW_SECONDS = 5.0
_GAP_TOLERANCE_MS = 1_000


def _finite_number(value: object) -> float | None:
    if isinstance(value, bool) or not isinstance(value, (str, int, float)):
        return None
    try:
        number = float(value)
    except (TypeError, ValueError, OverflowError):
        return None
    return number if math.isfinite(number) else None


def _timestamp_ms(value: object) -> int | None:
    number = _finite_number(value)
    if number is None or number < 0.0:
        return None
    try:
        return int(number)
    except (TypeError, ValueError, OverflowError):
        return None


def _index_epoch_ms(frame: object) -> list[int] | None:
    if not isinstance(frame, pd.DataFrame):
        return None
    try:
        if pd.api.types.is_numeric_dtype(frame.index.dtype):
            parsed_index = pd.to_datetime(frame.index, unit="ms", utc=True)
        else:
            parsed_index = pd.to_datetime(frame.index, utc=True)
        index = pd.DatetimeIndex(parsed_index)
        if index.tz is not None:
            index = index.tz_convert("UTC").tz_localize(None)
        if index.isna().any():
            return None
        values = index.asi8
        unit = str(getattr(index, "unit", "ns") or "ns")
        scale_to_ms = {"s": 1_000.0, "ms": 1.0, "us": 0.001, "ns": 0.000001}
        scale = scale_to_ms.get(unit, 0.000001)
        return [int(float(value) * scale) for value in values]
    except (TypeError, ValueError, OverflowError):
        return None


def _unique_reasons(reasons: list[str]) -> list[str]:
    return list(dict.fromkeys(str(reason) for reason in reasons if str(reason).strip()))


def build_live_market_data_quality(
    frame: object,
    interval: object,
    *,
    metadata: Mapping[str, object] | None = None,
    now_epoch: float | None = None,
    source: str | None = None,
) -> dict[str, object]:
    """Return a serializable quality result for a live OHLCV frame.

    ``metadata`` is transport-owned and may contain ``event_time_ms`` (exchange
    event time), ``receipt_time_ms`` (local receipt time), ``closed`` for the
    latest bar, and pre-sort ``index_monotonic``/``index_unique`` observations.
    The result is deliberately a plain dictionary so it can be carried through
    strategy state, operational snapshots, logs, and native parity boundaries.
    """

    metadata = metadata if isinstance(metadata, Mapping) else {}
    try:
        interval_seconds = float(_coerce_interval_seconds(interval))
    except (TypeError, ValueError, OverflowError):
        interval_seconds = 0.0
    interval_ms = int(interval_seconds * 1_000) if interval_seconds > 0.0 else 0

    current_epoch = _finite_number(now_epoch)
    if current_epoch is None:
        current_epoch = time.time()
    receipt_ms = _timestamp_ms(metadata.get("receipt_time_ms"))
    event_ms = _timestamp_ms(metadata.get("event_time_ms"))
    if event_ms is None:
        event_ms = _timestamp_ms(metadata.get("exchange_event_time_ms"))
    source_text = str(source if source is not None else metadata.get("source") or "").strip()

    reasons: list[str] = []
    if not source_text:
        reasons.append("market-data source is missing or invalid")
    if interval_ms <= 0:
        reasons.append("market-data interval is missing or invalid")
    if receipt_ms is None:
        reasons.append("market-data receipt timestamp is missing or invalid")
    if event_ms is None:
        reasons.append("market-data source event timestamp is missing or invalid")

    frame_ok = isinstance(frame, pd.DataFrame)
    if not frame_ok:
        reasons.append("market-data frame is missing or invalid")
        index_ms = None
    else:
        index_ms = _index_epoch_ms(frame)
        if index_ms is None:
            reasons.append("market-data index contains an invalid timestamp")
        elif not index_ms:
            reasons.append("market-data frame is empty")

    if isinstance(metadata.get("index_monotonic"), bool):
        index_monotonic = bool(metadata["index_monotonic"])
    else:
        index_monotonic = bool(index_ms is not None and all(a < b for a, b in zip(index_ms, index_ms[1:])))
    if isinstance(metadata.get("index_unique"), bool):
        index_unique = bool(metadata["index_unique"])
    else:
        index_unique = bool(index_ms is not None and len(index_ms) == len(set(index_ms)))
    if not index_monotonic:
        reasons.append("market-data index is not monotonic")
    if not index_unique:
        reasons.append("market-data index contains duplicates")

    gap_free = True
    if index_ms is not None and interval_ms > 0 and len(index_ms) > 1:
        differences = [right - left for left, right in zip(index_ms, index_ms[1:])]
        gap_free = all(
            difference > 0 and abs(difference - interval_ms) <= _GAP_TOLERANCE_MS
            for difference in differences
        )
        if not gap_free:
            reasons.append("market-data candle gap or cadence violation detected")
    if isinstance(metadata.get("gap_free"), bool):
        gap_free = bool(metadata["gap_free"])
        if not gap_free and "market-data candle gap or cadence violation detected" not in reasons:
            reasons.append("market-data candle gap or cadence violation detected")

    finite_ohlcv = True
    price_valid = True
    volume_valid = True
    relationships_valid = True
    if frame_ok:
        missing_columns = [column for column in OHLCV_COLUMNS if column not in frame.columns]
        if missing_columns:
            finite_ohlcv = price_valid = volume_valid = relationships_valid = False
            reasons.append(f"market-data OHLCV columns are missing: {','.join(missing_columns)}")
        else:
            for row in frame.loc[:, list(OHLCV_COLUMNS)].itertuples(index=False, name=None):
                try:
                    open_value, high_value, low_value, close_value, volume_value = (
                        float(value) for value in row
                    )
                except (TypeError, ValueError, OverflowError):
                    finite_ohlcv = False
                    continue
                if not all(math.isfinite(value) for value in (open_value, high_value, low_value, close_value, volume_value)):
                    finite_ohlcv = False
                    continue
                if min(open_value, high_value, low_value, close_value) <= 0.0:
                    price_valid = False
                if volume_value < 0.0:
                    volume_valid = False
                if high_value < max(open_value, close_value, low_value) or low_value > min(open_value, close_value, high_value):
                    relationships_valid = False
    if not finite_ohlcv:
        reasons.append("market-data OHLCV contains non-finite or non-numeric values")
    if not price_valid:
        reasons.append("market-data OHLC prices must be finite and positive")
    if not volume_valid:
        reasons.append("market-data volume must be finite and non-negative")
    if not relationships_valid:
        reasons.append("market-data OHLC relationships are invalid")

    closed_value = metadata.get("closed")
    if isinstance(closed_value, bool):
        closed = closed_value
    elif index_ms and interval_ms > 0 and receipt_ms is not None:
        closed = index_ms[-1] + interval_ms <= receipt_ms + _GAP_TOLERANCE_MS
    else:
        closed = False
    if not closed:
        reasons.append("market-data latest candle is still open")

    sequence_ok = metadata.get("sequence_ok")
    if isinstance(sequence_ok, bool) and not sequence_ok:
        reasons.append("market-data stream sequence is invalid or has a reconnect gap")

    max_age_seconds = max(interval_seconds * 2.0, 30.0) if interval_seconds > 0.0 else 30.0
    age_seconds: float | None = None
    receipt_age_seconds: float | None = None
    clock_skew_seconds: float | None = None
    if event_ms is not None:
        event_epoch = event_ms / 1_000.0
        age_seconds = current_epoch - event_epoch
        clock_skew_seconds = event_epoch - (receipt_ms / 1_000.0) if receipt_ms is not None else None
        if event_epoch - current_epoch > _MAX_FUTURE_SKEW_SECONDS:
            reasons.append("market-data source event timestamp is in the future")
        if age_seconds > max_age_seconds:
            reasons.append(
                f"market-data is stale (event age {age_seconds:.1f}s exceeds {max_age_seconds:.1f}s)"
            )
    if receipt_ms is not None:
        receipt_age_seconds = current_epoch - (receipt_ms / 1_000.0)
        if receipt_age_seconds < -_MAX_FUTURE_SKEW_SECONDS:
            reasons.append("market-data receipt timestamp is in the future")

    reasons = _unique_reasons(reasons)
    return {
        "ok": not reasons,
        "source": source_text,
        "interval": str(interval or "").strip(),
        "interval_seconds": interval_seconds,
        "event_time_ms": event_ms,
        "exchange_event_time_ms": event_ms,
        "receipt_time_ms": receipt_ms,
        "age_seconds": age_seconds,
        "receipt_age_seconds": receipt_age_seconds,
        "clock_skew_seconds": clock_skew_seconds,
        "max_age_seconds": max_age_seconds,
        "closed": closed,
        "open_bar": not closed,
        "index_monotonic": index_monotonic,
        "index_unique": index_unique,
        "gap_free": gap_free,
        "finite_ohlcv": finite_ohlcv,
        "price_valid": price_valid,
        "volume_valid": volume_valid,
        "relationships_valid": relationships_valid,
        "sequence_ok": sequence_ok if isinstance(sequence_ok, bool) else True,
        "last_open_time_ms": index_ms[-1] if index_ms else None,
        "rows": len(index_ms or []),
        "reasons": reasons,
        "reason": reasons[0] if reasons else "",
    }


def market_data_quality_issues(
    quality: object,
    *,
    now_epoch: float,
    require_closed: bool = True,
) -> list[str]:
    """Re-age a previously-produced quality result at the order boundary."""

    if not isinstance(quality, Mapping) or not quality:
        return ["market-data quality result is unavailable or invalid"]
    now_value = _finite_number(now_epoch)
    if now_value is None:
        return ["market-data safety clock is invalid"]

    issues: list[str] = []
    raw_reasons = quality.get("reasons")
    if isinstance(raw_reasons, (list, tuple)):
        issues.extend(str(reason) for reason in raw_reasons if str(reason).strip())
    elif quality.get("ok") is False:
        reason = str(quality.get("reason") or "market-data quality validation failed").strip()
        issues.append(reason)

    event_ms = _timestamp_ms(quality.get("event_time_ms"))
    receipt_ms = _timestamp_ms(quality.get("receipt_time_ms"))
    max_age = _finite_number(quality.get("max_age_seconds"))
    if event_ms is None:
        issues.append("market-data source event timestamp is missing or invalid")
    else:
        event_epoch = event_ms / 1_000.0
        age_seconds = now_value - event_epoch
        if event_epoch - now_value > _MAX_FUTURE_SKEW_SECONDS:
            issues.append("market-data source event timestamp is in the future")
        if max_age is None or max_age <= 0.0:
            issues.append("market-data freshness limit is missing or invalid")
        elif age_seconds > max_age:
            issues.append(f"market-data is stale (event age {age_seconds:.1f}s exceeds {max_age:.1f}s)")
    if receipt_ms is None:
        issues.append("market-data receipt timestamp is missing or invalid")
    elif now_value - (receipt_ms / 1_000.0) < -_MAX_FUTURE_SKEW_SECONDS:
        issues.append("market-data receipt timestamp is in the future")

    for field, label in (
        ("index_monotonic", "market-data index is not monotonic"),
        ("index_unique", "market-data index contains duplicates"),
        ("gap_free", "market-data candle gap or cadence violation detected"),
        ("finite_ohlcv", "market-data OHLCV contains non-finite or non-numeric values"),
        ("price_valid", "market-data OHLC prices must be finite and positive"),
        ("volume_valid", "market-data volume must be finite and non-negative"),
        ("relationships_valid", "market-data OHLC relationships are invalid"),
        ("sequence_ok", "market-data stream sequence is invalid or has a reconnect gap"),
    ):
        value = quality.get(field)
        if value is not True:
            issues.append(label)
    if require_closed and quality.get("closed") is not True:
        issues.append("market-data latest candle is still open")

    return _unique_reasons(issues)


__all__ = ["build_live_market_data_quality", "market_data_quality_issues"]
