"""Validate service snapshot freshness before strategy order submission."""

from __future__ import annotations

import math
from collections.abc import Mapping
from datetime import datetime

from app.settings.execution import ExecutionSettings


_DEFAULTS = ExecutionSettings()
_MAX_FUTURE_SKEW_SECONDS = 5.0
_CRITICAL_COMPONENTS = (
    ("exchange_connector", "exchange connector", "operational_connector_snapshot_stale_seconds"),
    ("account", "account", "operational_account_snapshot_stale_seconds"),
    ("portfolio", "portfolio", "operational_portfolio_snapshot_stale_seconds"),
)


def _nonnegative_number(value: object) -> float | None:
    if isinstance(value, bool) or not isinstance(value, (str, int, float)):
        return None
    try:
        number = float(value)
    except (TypeError, ValueError, OverflowError):
        return None
    return number if math.isfinite(number) and number >= 0.0 else None


def _timestamp_epoch(value: object) -> float | None:
    numeric = _nonnegative_number(value)
    if numeric is not None:
        return numeric
    if not isinstance(value, str):
        return None
    try:
        timestamp = datetime.fromisoformat(value.strip().replace("Z", "+00:00"))
        if timestamp.tzinfo is None:
            return None
        return _nonnegative_number(timestamp.timestamp())
    except (OSError, OverflowError, ValueError):
        return None


def operational_snapshot_issues(
    snapshot: object, config: Mapping[str, object], *, now_epoch: float,
) -> list[str]:
    if not isinstance(snapshot, dict) or not snapshot:
        return ["operational safety snapshot is unavailable or invalid"]
    if _nonnegative_number(now_epoch) is None:
        return ["operational safety clock is invalid"]

    issues: list[str] = []
    if snapshot.get("health") not in ("ok", "warning"):
        issues.append("operational health is error, missing, or invalid")
    snapshot_epoch = _timestamp_epoch(snapshot.get("generated_at"))
    if snapshot_epoch is None:
        issues.append("operational snapshot timestamp is missing or invalid")
    elif snapshot_epoch - now_epoch > _MAX_FUTURE_SKEW_SECONDS:
        issues.append("operational snapshot timestamp is in the future")

    freshness = snapshot.get("freshness")
    if not isinstance(freshness, dict):
        return issues + ["critical snapshot freshness is missing or invalid"]

    for key, label, config_key in _CRITICAL_COMPONENTS:
        item = freshness.get(key)
        if not isinstance(item, dict):
            issues.append(f"{label} freshness is missing or invalid")
            continue
        stale = item.get("stale")
        if not isinstance(stale, bool):
            issues.append(f"{label} freshness stale flag is missing or invalid")
        elif stale:
            issues.append(f"{label} snapshot is stale")

        age = _nonnegative_number(item.get("age_seconds"))
        epoch = _timestamp_epoch(item.get("generated_at"))
        reported_limit = _nonnegative_number(item.get("max_age_seconds"))
        configured_limit = _nonnegative_number(config.get(config_key, getattr(_DEFAULTS, config_key)))
        if age is None or epoch is None:
            issues.append(f"{label} freshness age or timestamp is missing or invalid")
        if reported_limit is None or configured_limit is None or reported_limit == 0.0 or configured_limit == 0.0:
            issues.append(f"{label} freshness limit is missing or invalid")
            continue
        if age is None or epoch is None:
            continue
        if epoch - now_epoch > _MAX_FUTURE_SKEW_SECONDS:
            issues.append(f"{label} freshness timestamp is in the future")
            continue

        # Re-age cached snapshots and never let remote metadata relax the local limit.
        limit = min(reported_limit, configured_limit)
        if max(age, now_epoch - epoch) > limit:
            issues.append(f"{label} snapshot is stale")
        if snapshot_epoch is not None and now_epoch - snapshot_epoch > limit:
            issues.append(f"operational snapshot is stale for {label}")
    return issues
