from __future__ import annotations

from dataclasses import asdict, is_dataclass
from itertools import combinations
from typing import Iterable, Sequence

from app.core.backtest.models import PairOverride


MAX_BACKTEST_OPTIMIZER_RUNS = 5000

OPTIMIZER_MODE_OPTIONS = (
    ("Current selection", "current"),
    ("Single indicators", "single"),
    ("Indicator pairs", "pairs"),
    ("Combinations up to N", "combinations"),
)
OPTIMIZER_METRIC_OPTIONS = (
    ("Best ROI %", "roi_percent"),
    ("Best ROI % within Max MDD", "roi_percent_mdd"),
    ("ROI / Drawdown score", "roi_drawdown"),
    ("Best ROI USDT", "roi_value"),
)
SCAN_SCOPE_OPTIONS = (
    ("Selected symbols", "selected"),
    ("Top N loaded symbols", "top_n"),
    ("All loaded symbols", "all_loaded"),
)

_OPTIMIZER_MODE_VALUES = {value for _label, value in OPTIMIZER_MODE_OPTIONS}
_OPTIMIZER_METRIC_VALUES = {value for _label, value in OPTIMIZER_METRIC_OPTIONS}
_SCAN_SCOPE_VALUES = {value for _label, value in SCAN_SCOPE_OPTIONS}


def _normalize_option(value: object, allowed: set[str], default: str) -> str:
    text = str(value or "").strip().lower().replace("-", "_").replace(" ", "_")
    return text if text in allowed else default


def normalize_optimizer_mode(value: object) -> str:
    return _normalize_option(value, _OPTIMIZER_MODE_VALUES, "current")


def normalize_optimizer_metric(value: object) -> str:
    return _normalize_option(value, _OPTIMIZER_METRIC_VALUES, "roi_percent")


def normalize_scan_scope(value: object) -> str:
    return _normalize_option(value, _SCAN_SCOPE_VALUES, "selected")


def option_label(options: Sequence[tuple[str, str]], value: str) -> str:
    normalized = str(value or "").strip()
    for label, option_value in options:
        if option_value == normalized:
            return label
    return normalized.replace("_", " ").title()


def _unique_texts(values: Iterable[object], *, uppercase: bool = False) -> list[str]:
    result: list[str] = []
    seen: set[str] = set()
    for raw in values or []:
        value = str(raw or "").strip()
        if not value:
            continue
        if uppercase:
            value = value.upper()
        if value in seen:
            continue
        seen.add(value)
        result.append(value)
    return result


def resolve_scan_symbols(
    *,
    symbols_all: Iterable[object],
    selected_symbols: Iterable[object],
    scope: str,
    top_n: int,
) -> list[str]:
    normalized_scope = normalize_scan_scope(scope)
    if normalized_scope == "selected":
        return _unique_texts(selected_symbols, uppercase=True)
    loaded_symbols = _unique_texts(symbols_all, uppercase=True)
    if normalized_scope == "all_loaded":
        return loaded_symbols
    return loaded_symbols[: max(0, int(top_n or 0))]


def build_indicator_key_groups(
    indicator_keys: Iterable[object],
    *,
    mode: str,
    combo_size: int,
) -> list[list[str]]:
    keys = _unique_texts(indicator_keys)
    normalized_mode = normalize_optimizer_mode(mode)
    if normalized_mode == "current":
        return []
    if normalized_mode == "single":
        return [[key] for key in keys]
    if normalized_mode == "pairs":
        return [list(group) for group in combinations(keys, 2)]
    max_size = max(1, min(int(combo_size or 1), len(keys)))
    groups: list[list[str]] = []
    for size in range(1, max_size + 1):
        groups.extend(list(group) for group in combinations(keys, size))
    return groups


def estimate_scan_run_count(
    *,
    symbols: Sequence[str],
    intervals: Sequence[str],
    indicator_count: int,
    indicator_groups: Sequence[Sequence[str]],
    mode: str,
    logic: str,
) -> int:
    base_count = len(symbols) * len(intervals)
    if normalize_optimizer_mode(mode) == "current":
        multiplier = max(1, int(indicator_count or 0)) if str(logic or "").upper() == "SEPARATE" else 1
        return base_count * multiplier
    return base_count * len(indicator_groups)


def build_pair_overrides(
    *,
    symbols: Sequence[str],
    intervals: Sequence[str],
    indicator_groups: Sequence[Sequence[str]],
) -> list[PairOverride]:
    overrides: list[PairOverride] = []
    for symbol in symbols:
        for interval in intervals:
            for indicator_keys in indicator_groups:
                overrides.append(
                    PairOverride(
                        symbol=symbol,
                        interval=interval,
                        indicators=list(indicator_keys),
                    )
                )
    return overrides


def run_to_mapping(run) -> dict[str, object]:  # noqa: ANN001
    if is_dataclass(run):
        return asdict(run)
    if isinstance(run, dict):
        return dict(run)
    return {
        "symbol": getattr(run, "symbol", ""),
        "interval": getattr(run, "interval", ""),
        "indicator_keys": getattr(run, "indicator_keys", []),
        "trades": getattr(run, "trades", 0),
        "roi_percent": getattr(run, "roi_percent", 0.0),
        "roi_value": getattr(run, "roi_value", 0.0),
        "max_drawdown_percent": getattr(run, "max_drawdown_percent", 0.0),
        "mdd_logic": getattr(run, "mdd_logic", None),
    }


def optimizer_score(
    run,
    *,
    metric: str,
    mdd_limit: float,
    min_trades: int,
) -> tuple[float, ...] | None:
    data = run_to_mapping(run)
    try:
        trades = int(data.get("trades", 0) or 0)
    except Exception:
        trades = 0
    if trades < max(0, int(min_trades or 0)):
        return None
    try:
        mdd = float(data.get("max_drawdown_percent", 0.0) or 0.0)
    except Exception:
        mdd = 0.0
    try:
        limit = float(mdd_limit or 0.0)
    except Exception:
        limit = 0.0
    if limit > 0.0 and mdd > limit:
        return None
    try:
        roi_pct = float(data.get("roi_percent", 0.0) or 0.0)
    except Exception:
        roi_pct = 0.0
    try:
        roi_val = float(data.get("roi_value", 0.0) or 0.0)
    except Exception:
        roi_val = 0.0
    metric_norm = normalize_optimizer_metric(metric)
    if metric_norm == "roi_value":
        return (roi_val, roi_pct, float(trades), -mdd)
    if metric_norm == "roi_drawdown":
        return (roi_pct / max(abs(mdd), 1.0), roi_pct, roi_val, float(trades), -mdd)
    return (roi_pct, roi_val, float(trades), -mdd)


__all__ = [
    "MAX_BACKTEST_OPTIMIZER_RUNS",
    "OPTIMIZER_METRIC_OPTIONS",
    "OPTIMIZER_MODE_OPTIONS",
    "SCAN_SCOPE_OPTIONS",
    "build_indicator_key_groups",
    "build_pair_overrides",
    "estimate_scan_run_count",
    "normalize_optimizer_metric",
    "normalize_optimizer_mode",
    "normalize_scan_scope",
    "optimizer_score",
    "option_label",
    "resolve_scan_symbols",
    "run_to_mapping",
]
