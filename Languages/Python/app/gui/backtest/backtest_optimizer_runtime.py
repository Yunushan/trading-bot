from __future__ import annotations

from dataclasses import asdict, is_dataclass
from itertools import combinations
from typing import Any, Iterable, Sequence, cast

from app.core.backtest.models import PairOverride
from app.core.backtest.optimizer_limits_runtime import (
    BACKTEST_OPTIMIZER_INTERACTIVE_RUN_WARNING,
    BACKTEST_OPTIMIZER_LARGE_RUN_WARNING,
    MAX_BACKTEST_EXPECTED_RUN_TRACKING,
    MAX_BACKTEST_OPTIMIZER_RUNS,
    MAX_BACKTEST_OPTIMIZER_TABLE_ROWS,
    estimate_optimizer_duration_seconds,
    format_optimizer_duration,
)
from app.core.backtest.optimizer_pair_plan_runtime import (
    build_optimizer_pair_override_collection,
)

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


def _coerce_float(value: object, default: float = 0.0) -> float:
    if isinstance(value, bool) or value in (None, ""):
        return float(default)
    try:
        return float(str(value).strip() if isinstance(value, str) else str(value))
    except (TypeError, ValueError):
        return float(default)


def _coerce_int(value: object, default: int = 0) -> int:
    try:
        return int(_coerce_float(value, float(default)))
    except (TypeError, ValueError, OverflowError):
        return int(default)


def _coerce_score_tuple(value: object) -> tuple[float, ...]:
    if isinstance(value, tuple):
        return tuple(_coerce_float(item) for item in value)
    if isinstance(value, list):
        return tuple(_coerce_float(item) for item in value)
    return ()


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


def estimate_scan_plan(
    *,
    symbols_all: Iterable[object],
    selected_symbols: Iterable[object],
    intervals: Iterable[object],
    indicator_keys: Iterable[object],
    scope: str,
    top_n: int,
    mode: str,
    combo_size: int,
    logic: str,
) -> dict[str, object]:
    normalized_scope = normalize_scan_scope(scope)
    normalized_mode = normalize_optimizer_mode(mode)
    symbols = resolve_scan_symbols(
        symbols_all=symbols_all,
        selected_symbols=selected_symbols,
        scope=normalized_scope,
        top_n=top_n,
    )
    interval_values = _unique_texts(intervals)
    signal_keys = _unique_texts(indicator_keys)
    indicator_groups = build_indicator_key_groups(
        signal_keys,
        mode=normalized_mode,
        combo_size=combo_size,
    )
    has_groups = bool(indicator_groups) if normalized_mode != "current" else True
    run_count = (
        estimate_scan_run_count(
            symbols=symbols,
            intervals=interval_values,
            indicator_count=len(signal_keys),
            indicator_groups=indicator_groups,
            mode=normalized_mode,
            logic=logic,
        )
        if has_groups
        else 0
    )
    return {
        "scope": normalized_scope,
        "mode": normalized_mode,
        "symbols": symbols,
        "symbol_count": len(symbols),
        "interval_count": len(interval_values),
        "signal_indicator_count": len(signal_keys),
        "indicator_group_count": len(indicator_groups) if normalized_mode != "current" else 0,
        "run_count": run_count,
        "over_limit": run_count > MAX_BACKTEST_OPTIMIZER_RUNS,
        "large_warning": run_count > BACKTEST_OPTIMIZER_LARGE_RUN_WARNING,
        "interactive_warning": run_count > BACKTEST_OPTIMIZER_INTERACTIVE_RUN_WARNING,
        "limit": MAX_BACKTEST_OPTIMIZER_RUNS,
        "display_limit": MAX_BACKTEST_OPTIMIZER_TABLE_ROWS,
        "estimated_seconds": estimate_optimizer_duration_seconds(run_count),
        "estimated_duration": format_optimizer_duration(estimate_optimizer_duration_seconds(run_count)),
    }


def format_scan_plan_estimate(plan: dict[str, object]) -> str:
    run_count = _coerce_int(plan.get("run_count", 0), 0)
    limit = _coerce_int(plan.get("limit", MAX_BACKTEST_OPTIMIZER_RUNS), MAX_BACKTEST_OPTIMIZER_RUNS)
    symbol_count = _coerce_int(plan.get("symbol_count", 0), 0)
    interval_count = _coerce_int(plan.get("interval_count", 0), 0)
    signal_count = _coerce_int(plan.get("signal_indicator_count", 0), 0)
    group_count = _coerce_int(plan.get("indicator_group_count", 0), 0)
    display_limit = _coerce_int(plan.get("display_limit", MAX_BACKTEST_OPTIMIZER_TABLE_ROWS), MAX_BACKTEST_OPTIMIZER_TABLE_ROWS)
    estimated_duration = str(plan.get("estimated_duration") or "").strip()

    mode = normalize_optimizer_mode(plan.get("mode"))
    over_limit = bool(plan.get("over_limit"))
    large_warning = bool(plan.get("large_warning"))
    interactive_warning = bool(plan.get("interactive_warning"))
    if mode == "current":
        group_text = f"{signal_count} signal indicator(s)"
    else:
        group_text = f"{group_count} indicator group(s)"
    text = (
        f"Estimated optimizer runs: {run_count} "
        f"({symbol_count} symbol(s) x {interval_count} interval(s), {group_text})"
    )
    if estimated_duration:
        text += f" - rough runtime estimate {estimated_duration}"
    if over_limit:
        text += f" - exceeds research limit {limit}; reduce selection."
    elif large_warning:
        text += f" - large research batch; leaderboard keeps top {display_limit} row(s)."
    elif interactive_warning:
        text += f" - large interactive batch; top {display_limit} row(s) are displayed."
    return text


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


def build_pair_overrides_or_plan(
    *,
    symbols: Sequence[str],
    intervals: Sequence[str],
    indicator_groups: Sequence[Sequence[str]],
):
    return build_optimizer_pair_override_collection(
        symbols=symbols,
        intervals=intervals,
        indicator_groups=indicator_groups,
        lazy_threshold=MAX_BACKTEST_EXPECTED_RUN_TRACKING,
    )


def run_to_mapping(run) -> dict[str, object]:  # noqa: ANN001
    if not isinstance(run, type) and is_dataclass(run):
        return cast(dict[str, object], asdict(cast(Any, run)))
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
    trades = _coerce_int(data.get("trades", 0), 0)
    if trades < max(0, int(min_trades or 0)):
        return None
    mdd = _coerce_float(data.get("max_drawdown_percent", 0.0), 0.0)
    try:
        limit = float(mdd_limit or 0.0)
    except Exception:
        limit = 0.0
    if limit > 0.0 and mdd > limit:
        return None
    roi_pct = _coerce_float(data.get("roi_percent", 0.0), 0.0)
    roi_val = _coerce_float(data.get("roi_value", 0.0), 0.0)
    metric_norm = normalize_optimizer_metric(metric)
    if metric_norm == "roi_value":
        return (roi_val, roi_pct, float(trades), -mdd)
    if metric_norm == "roi_drawdown":
        return (roi_pct / max(abs(mdd), 1.0), roi_pct, roi_val, float(trades), -mdd)
    return (roi_pct, roi_val, float(trades), -mdd)


def _optimizer_threshold_state(
    run,
    *,
    mdd_limit: float,
    min_trades: int,
) -> tuple[int, float, list[str]]:
    data = run_to_mapping(run)
    trades = _coerce_int(data.get("trades", 0), 0)
    mdd = _coerce_float(data.get("max_drawdown_percent", 0.0), 0.0)
    try:
        limit = float(mdd_limit or 0.0)
    except Exception:
        limit = 0.0
    trade_floor = max(0, int(min_trades or 0))
    reasons: list[str] = []
    if trades < trade_floor:
        reasons.append(f"trades {trades} < {trade_floor}")
    if limit > 0.0 and mdd > limit:
        reasons.append(f"MDD {mdd:.2f}% > {limit:.2f}%")
    return trades, mdd, reasons


def rank_optimizer_runs(
    runs,
    *,
    metric: str,
    mdd_limit: float,
    min_trades: int,
    mode: str = "",
    scope: str = "",
    run_count: int | None = None,
    max_rows: int | None = None,
) -> list[dict[str, object]]:
    metric_norm = normalize_optimizer_metric(metric)
    mode_norm = normalize_optimizer_mode(mode) if str(mode or "").strip() else ""
    scope_norm = normalize_scan_scope(scope) if str(scope or "").strip() else ""
    try:
        mdd_limit_value = max(0.0, float(mdd_limit or 0.0))
    except Exception:
        mdd_limit_value = 0.0
    try:
        min_trades_value = max(0, int(min_trades or 0))
    except Exception:
        min_trades_value = 0
    try:
        run_count_value = int(run_count) if run_count is not None else None
    except Exception:
        run_count_value = None
    row_limit = None
    try:
        if max_rows is not None:
            row_limit = max(1, int(max_rows))
    except Exception:
        row_limit = None
    ranked_rows: list[dict[str, object]] = []
    for original_index, run in enumerate(runs or []):
        data = run_to_mapping(run)
        score = optimizer_score(
            data,
            metric=metric_norm,
            mdd_limit=mdd_limit_value,
            min_trades=min_trades_value,
        )
        _trades, _mdd, reasons = _optimizer_threshold_state(
            data,
            mdd_limit=mdd_limit_value,
            min_trades=min_trades_value,
        )
        row = dict(data)
        row["_optimizer_original_index"] = original_index
        row["optimizer_metric"] = metric_norm
        row["optimizer_mdd_limit"] = mdd_limit_value
        row["optimizer_min_trades"] = min_trades_value
        if mode_norm:
            row["optimizer_mode"] = mode_norm
        if scope_norm:
            row["optimizer_scope"] = scope_norm
        if run_count_value is not None:
            row["optimizer_run_count"] = run_count_value
        row["optimizer_eligible"] = score is not None
        row["optimizer_score"] = tuple(score or ())
        row["optimizer_primary_score"] = float(score[0]) if score else None
        row["optimizer_rejection_reason"] = "; ".join(reasons)
        ranked_rows.append(row)

    eligible_rows = [row for row in ranked_rows if row.get("optimizer_eligible")]
    eligible_rows.sort(
        key=lambda row: (
            _coerce_score_tuple(row.get("optimizer_score")),
            -_coerce_int(row.get("_optimizer_original_index", 0), 0),
        ),
        reverse=True,
    )
    for rank, row in enumerate(eligible_rows, start=1):
        row["optimizer_rank"] = rank

    rejected_rows = [row for row in ranked_rows if not row.get("optimizer_eligible")]
    rejected_rows.sort(key=lambda row: _coerce_int(row.get("_optimizer_original_index", 0), 0))
    for row in rejected_rows:
        row["optimizer_rank"] = None
    candidate_count = len(ranked_rows)
    eligible_count = len(eligible_rows)
    filtered_count = len(rejected_rows)
    for row in ranked_rows:
        row["optimizer_candidate_count"] = candidate_count
        row["optimizer_eligible_count"] = eligible_count
        row["optimizer_filtered_count"] = filtered_count
    ranked_result = eligible_rows + rejected_rows
    if row_limit is not None and len(ranked_result) > row_limit:
        return ranked_result[:row_limit]
    return ranked_result


__all__ = [
    "MAX_BACKTEST_OPTIMIZER_RUNS",
    "MAX_BACKTEST_OPTIMIZER_TABLE_ROWS",
    "OPTIMIZER_METRIC_OPTIONS",
    "OPTIMIZER_MODE_OPTIONS",
    "SCAN_SCOPE_OPTIONS",
    "build_indicator_key_groups",
    "build_pair_overrides",
    "build_pair_overrides_or_plan",
    "estimate_scan_plan",
    "estimate_scan_run_count",
    "format_scan_plan_estimate",
    "normalize_optimizer_metric",
    "normalize_optimizer_mode",
    "normalize_scan_scope",
    "optimizer_score",
    "option_label",
    "rank_optimizer_runs",
    "resolve_scan_symbols",
    "run_to_mapping",
]
