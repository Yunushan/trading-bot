from __future__ import annotations

import copy
from dataclasses import asdict, is_dataclass
from datetime import datetime, timedelta, timezone
from itertools import combinations

from ...config import coerce_bool, normalize_stop_loss_dict
from ...core.backtest.indicator_selection_runtime import (
    build_backtest_indicator_definitions,
    format_missing_signal_indicator_message,
    format_missing_signal_rule_message,
)
from ...core.backtest.indicator_runtime import filter_indicators, signal_indicators
from ...core.backtest.intervals import normalize_backtest_interval, normalize_backtest_intervals
from ...core.backtest.models import BacktestRequest, IndicatorDefinition, PairOverride
from ...settings.exchange_support import build_exchange_support_payload

MAX_BACKTEST_OPTIMIZER_RUNS = 5000
OPTIMIZER_MODE_VALUES = {"current", "single", "pairs", "combinations"}
OPTIMIZER_METRIC_VALUES = {
    "roi_percent",
    "roi_percent_mdd",
    "roi_drawdown",
    "roi_value",
}
SCAN_SCOPE_VALUES = {"selected", "top_n", "all_loaded"}


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def clean_text(value, default: str = "") -> str:  # noqa: ANN001
    text = str(value or "").strip()
    return text or default


def string_list(value) -> list[str]:  # noqa: ANN001
    if not isinstance(value, (list, tuple)):
        return []
    items: list[str] = []
    for item in value:
        text = clean_text(item)
        if text:
            items.append(text)
    return items


def interval_list(value) -> list[str]:  # noqa: ANN001
    return normalize_backtest_intervals(value)


def deep_merge(base: dict, patch: dict) -> dict:
    merged = copy.deepcopy(base)
    for key, value in patch.items():
        if isinstance(value, dict) and isinstance(merged.get(key), dict):
            merged[key] = deep_merge(merged.get(key) or {}, value)
        else:
            merged[key] = copy.deepcopy(value)
    return merged


def coerce_number(value, default: float = 0.0) -> float:  # noqa: ANN001
    try:
        return float(value)
    except Exception:
        return float(default)


def coerce_int(value, default: int = 0) -> int:  # noqa: ANN001
    try:
        return int(float(value))
    except Exception:
        return int(default)


def normalize_choice(value, allowed: set[str], default: str) -> str:  # noqa: ANN001
    text = str(value or "").strip().lower().replace("-", "_").replace(" ", "_")
    return text if text in allowed else default


def normalize_optimizer_mode(value) -> str:  # noqa: ANN001
    return normalize_choice(value, OPTIMIZER_MODE_VALUES, "current")


def normalize_optimizer_metric(value) -> str:  # noqa: ANN001
    return normalize_choice(value, OPTIMIZER_METRIC_VALUES, "roi_percent")


def normalize_scan_scope(value) -> str:  # noqa: ANN001
    return normalize_choice(value, SCAN_SCOPE_VALUES, "selected")


def coerce_datetime(value) -> datetime | None:  # noqa: ANN001
    if isinstance(value, datetime):
        parsed = value
    else:
        text = clean_text(value)
        if not text:
            return None
        if text.endswith("Z"):
            text = f"{text[:-1]}+00:00"
        parsed = None
        try:
            parsed = datetime.fromisoformat(text)
        except Exception:
            for fmt in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%d"):
                try:
                    parsed = datetime.strptime(text, fmt)
                    break
                except Exception:
                    continue
        if parsed is None:
            return None
    if parsed is None:
        return None
    if parsed.tzinfo is not None:
        parsed = parsed.astimezone(timezone.utc).replace(tzinfo=None)
    return parsed


def build_indicator_definitions(indicators_payload) -> list[IndicatorDefinition]:  # noqa: ANN001
    return build_backtest_indicator_definitions(indicators_payload)


def build_pair_overrides(overrides_payload) -> list[PairOverride] | None:  # noqa: ANN001
    if not isinstance(overrides_payload, (list, tuple)):
        return None
    overrides: list[PairOverride] = []
    seen: set[tuple[str, str, tuple[str, ...]]] = set()
    for item in overrides_payload:
        if not isinstance(item, dict):
            continue
        symbol = clean_text(item.get("symbol")).upper()
        interval = normalize_backtest_interval(item.get("interval"))
        if not symbol or not interval:
            continue
        indicators = string_list(item.get("indicators"))
        key = (symbol, interval, tuple(sorted(indicators)))
        if key in seen:
            continue
        seen.add(key)
        strategy_controls = (
            copy.deepcopy(item.get("strategy_controls"))
            if isinstance(item.get("strategy_controls"), dict)
            else {}
        )
        for control_key in (
            "logic",
            "capital",
            "side",
            "position_pct",
            "position_pct_units",
            "margin_mode",
            "position_mode",
            "assets_mode",
            "account_mode",
            "mdd_logic",
            "leverage",
            "stop_loss_enabled",
            "stop_loss_mode",
            "stop_loss_usdt",
            "stop_loss_percent",
            "stop_loss_scope",
        ):
            if control_key in item and item.get(control_key) is not None:
                strategy_controls[control_key] = copy.deepcopy(item.get(control_key))
        if isinstance(item.get("stop_loss"), dict):
            strategy_controls["stop_loss"] = copy.deepcopy(item.get("stop_loss"))
        leverage = None
        try:
            raw_leverage = item.get("leverage")
            if raw_leverage is None:
                raw_leverage = strategy_controls.get("leverage")
            if raw_leverage is not None:
                leverage = int(float(raw_leverage))
        except Exception:
            leverage = None
        overrides.append(
            PairOverride(
                symbol=symbol,
                interval=interval,
                indicators=indicators or None,
                leverage=leverage,
                strategy_controls=strategy_controls or None,
            )
        )
    return overrides or None


def unique_texts(values, *, uppercase: bool = False) -> list[str]:  # noqa: ANN001
    result: list[str] = []
    seen: set[str] = set()
    for raw in values or []:
        value = clean_text(raw)
        if not value:
            continue
        if uppercase:
            value = value.upper()
        if value in seen:
            continue
        seen.add(value)
        result.append(value)
    return result


def build_indicator_key_groups(
    indicator_keys,
    *,
    mode: str,
    combo_size: int,
) -> list[list[str]]:  # noqa: ANN001
    keys = unique_texts(indicator_keys)
    mode_norm = normalize_optimizer_mode(mode)
    if mode_norm == "current":
        return []
    if mode_norm == "single":
        return [[key] for key in keys]
    if mode_norm == "pairs":
        return [list(group) for group in combinations(keys, 2)]
    max_size = max(1, min(int(combo_size or 1), len(keys)))
    groups: list[list[str]] = []
    for size in range(1, max_size + 1):
        groups.extend(list(group) for group in combinations(keys, size))
    return groups


def build_optimizer_pair_overrides(
    *,
    symbols: list[str],
    intervals: list[str],
    indicators: list[IndicatorDefinition],
    mode: str,
    combo_size: int,
    logic: str,
) -> tuple[list[PairOverride], str, int, int]:
    signal_defs = signal_indicators(indicators)
    signal_keys = [indicator.key for indicator in signal_defs]
    filter_keys = [indicator.key for indicator in filter_indicators(indicators)]
    indicator_groups = build_indicator_key_groups(
        signal_keys,
        mode=mode,
        combo_size=combo_size,
    )
    if normalize_optimizer_mode(mode) != "current" and not indicator_groups:
        raise ValueError(
            "Optimizer mode needs more enabled signal indicators for the selected "
            "combination type."
        )
    if filter_keys:
        indicator_groups = [
            list(dict.fromkeys([*group, *filter_keys]))
            for group in indicator_groups
        ]

    request_logic = str(logic or "AND").strip().upper()
    if request_logic == "SEPARATE" and any(len(group) > 1 for group in indicator_groups):
        request_logic = "AND"

    overrides: list[PairOverride] = []
    for symbol in symbols:
        for interval in intervals:
            for indicator_group in indicator_groups:
                overrides.append(
                    PairOverride(
                        symbol=symbol,
                        interval=interval,
                        indicators=list(indicator_group),
                    )
                )
    return overrides, request_logic, len(signal_keys), len(indicator_groups)


def estimate_run_count(
    symbols: list[str],
    intervals: list[str],
    indicator_count: int,
    logic: str,
    pair_overrides: list[PairOverride] | None,
    *,
    optimizer_generated: bool = False,
) -> int:
    combos = len(pair_overrides) if pair_overrides else (len(symbols) * len(intervals))
    if combos <= 0:
        return 0
    if optimizer_generated:
        return combos
    if str(logic or "").upper() == "SEPARATE":
        return combos * max(1, indicator_count)
    return combos


def sort_runs(records: list) -> list:  # noqa: ANN001
    def _field(item, key: str, default=0.0):  # noqa: ANN001
        if isinstance(item, dict):
            return item.get(key, default)
        return getattr(item, key, default)

    def _optimizer_rank_sort(item) -> int:  # noqa: ANN001
        try:
            rank = int(_field(item, "optimizer_rank", 0) or 0)
        except Exception:
            rank = 0
        return rank if rank > 0 else 1_000_000

    return sorted(
        records,
        key=lambda item: (
            -_optimizer_rank_sort(item),
            float(_field(item, "roi_percent", 0.0) or 0.0),
            float(_field(item, "roi_value", 0.0) or 0.0),
            -float(_field(item, "max_drawdown_percent", 0.0) or 0.0),
            int(_field(item, "trades", 0) or 0),
        ),
        reverse=True,
    )


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
    trades = coerce_int(data.get("trades", 0), 0)
    if trades < max(0, int(min_trades or 0)):
        return None
    mdd = coerce_number(data.get("max_drawdown_percent", 0.0), 0.0)
    limit = coerce_number(mdd_limit, 0.0)
    if limit > 0.0 and mdd > limit:
        return None
    roi_pct = coerce_number(data.get("roi_percent", 0.0), 0.0)
    roi_val = coerce_number(data.get("roi_value", 0.0), 0.0)
    metric_norm = normalize_optimizer_metric(metric)
    if metric_norm == "roi_value":
        return (roi_val, roi_pct, float(trades), -mdd)
    if metric_norm == "roi_drawdown":
        return (roi_pct / max(abs(mdd), 1.0), roi_pct, roi_val, float(trades), -mdd)
    return (roi_pct, roi_val, float(trades), -mdd)


def optimizer_rejection_reasons(
    run,
    *,
    mdd_limit: float,
    min_trades: int,
) -> list[str]:
    data = run_to_mapping(run)
    trades = coerce_int(data.get("trades", 0), 0)
    mdd = coerce_number(data.get("max_drawdown_percent", 0.0), 0.0)
    trade_floor = max(0, int(min_trades or 0))
    limit = coerce_number(mdd_limit, 0.0)
    reasons: list[str] = []
    if trades < trade_floor:
        reasons.append(f"trades {trades} < {trade_floor}")
    if limit > 0.0 and mdd > limit:
        reasons.append(f"MDD {mdd:.2f}% > {limit:.2f}%")
    return reasons


def rank_optimizer_runs(
    runs,
    *,
    metric: str,
    mdd_limit: float,
    min_trades: int,
    mode: str = "",
    scope: str = "",
    run_count: int | None = None,
) -> list[dict[str, object]]:
    metric_norm = normalize_optimizer_metric(metric)
    mode_norm = normalize_optimizer_mode(mode) if clean_text(mode) else ""
    scope_norm = normalize_scan_scope(scope) if clean_text(scope) else ""
    mdd_limit_value = max(0.0, coerce_number(mdd_limit, 0.0))
    min_trades_value = max(0, coerce_int(min_trades, 0))
    run_count_value = coerce_int(run_count, 0) if run_count is not None else None
    ranked_rows: list[dict[str, object]] = []
    for original_index, run in enumerate(runs or []):
        data = run_to_mapping(run)
        score = optimizer_score(
            data,
            metric=metric_norm,
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
        row["optimizer_rejection_reason"] = "; ".join(
            optimizer_rejection_reasons(
                data,
                mdd_limit=mdd_limit_value,
                min_trades=min_trades_value,
            )
        )
        ranked_rows.append(row)

    eligible_rows = [row for row in ranked_rows if row.get("optimizer_eligible")]
    eligible_rows.sort(
        key=lambda row: (
            tuple(row.get("optimizer_score") or ()),
            -int(row.get("_optimizer_original_index", 0) or 0),
        ),
        reverse=True,
    )
    for rank, row in enumerate(eligible_rows, start=1):
        row["optimizer_rank"] = rank
    rejected_rows = [row for row in ranked_rows if not row.get("optimizer_eligible")]
    rejected_rows.sort(key=lambda row: int(row.get("_optimizer_original_index", 0) or 0))
    for row in rejected_rows:
        row["optimizer_rank"] = None

    candidate_count = len(ranked_rows)
    eligible_count = len(eligible_rows)
    filtered_count = len(rejected_rows)
    for row in ranked_rows:
        row["optimizer_candidate_count"] = candidate_count
        row["optimizer_eligible_count"] = eligible_count
        row["optimizer_filtered_count"] = filtered_count
    return eligible_rows + rejected_rows


def build_request(runtime, request_patch: dict | None) -> tuple[BacktestRequest, dict[str, object], dict[str, object]]:
    config = runtime.config
    patch = copy.deepcopy(request_patch) if isinstance(request_patch, dict) else {}
    backtest_cfg = copy.deepcopy(config.get("backtest") or {}) if isinstance(config.get("backtest"), dict) else {}
    if isinstance(patch.get("backtest"), dict):
        backtest_cfg = deep_merge(backtest_cfg, patch.pop("backtest"))

    symbols = string_list(patch.get("symbols", backtest_cfg.get("symbols", config.get("symbols"))))
    intervals = interval_list(patch.get("intervals", backtest_cfg.get("intervals", config.get("intervals"))))
    indicators = build_indicator_definitions(
        patch.get("indicators", backtest_cfg.get("indicators", config.get("indicators")))
    )
    if not indicators:
        raise ValueError("At least one enabled indicator is required for backtesting.")
    signal_rule_message = format_missing_signal_rule_message(indicators)
    if signal_rule_message:
        raise ValueError(signal_rule_message)
    signal_indicator_message = format_missing_signal_indicator_message(indicators)
    if signal_indicator_message:
        raise ValueError(signal_indicator_message)

    logic = clean_text(patch.get("logic", backtest_cfg.get("logic", "AND")), "AND").upper()
    optimizer_mode = normalize_optimizer_mode(
        patch.get("optimizer_mode", backtest_cfg.get("optimizer_mode", "current"))
    )
    optimizer_metric = normalize_optimizer_metric(
        patch.get("optimizer_metric", backtest_cfg.get("optimizer_metric", "roi_percent"))
    )
    optimizer_combo_size = max(
        1,
        min(
            5,
            coerce_int(
                patch.get(
                    "optimizer_combo_size",
                    backtest_cfg.get("optimizer_combo_size", 2),
                ),
                2,
            ),
        ),
    )
    optimizer_min_trades = max(
        0,
        coerce_int(
            patch.get("optimizer_min_trades", backtest_cfg.get("optimizer_min_trades", 1)),
            1,
        ),
    )
    optimizer_mdd_limit = max(
        0.0,
        coerce_number(
            patch.get("scan_mdd_limit", backtest_cfg.get("scan_mdd_limit", 10.0)),
            10.0,
        ),
    )
    scan_scope = normalize_scan_scope(
        patch.get("scan_scope", backtest_cfg.get("scan_scope", "selected"))
    )
    scan_top_n = max(
        1,
        coerce_int(patch.get("scan_top_n", backtest_cfg.get("scan_top_n", 200)), 200),
    )
    if optimizer_mode != "current" and scan_scope == "top_n":
        symbols = symbols[:scan_top_n]
    symbol_source = clean_text(patch.get("symbol_source", backtest_cfg.get("symbol_source", "Futures")), "Futures")
    capital = max(0.0, coerce_number(patch.get("capital", backtest_cfg.get("capital", 0.0)), 0.0))
    if capital <= 0.0:
        raise ValueError("Backtest capital must be positive.")

    optimizer_generated_overrides = False
    optimizer_signal_indicator_count = len(signal_indicators(indicators))
    optimizer_indicator_group_count = 0
    if "pair_overrides" in patch:
        pair_overrides = build_pair_overrides(patch.get("pair_overrides"))
    elif optimizer_mode != "current":
        (
            pair_overrides,
            logic,
            optimizer_signal_indicator_count,
            optimizer_indicator_group_count,
        ) = build_optimizer_pair_overrides(
            symbols=symbols,
            intervals=intervals,
            indicators=indicators,
            mode=optimizer_mode,
            combo_size=optimizer_combo_size,
            logic=logic,
        )
        optimizer_generated_overrides = True
    else:
        pair_overrides = build_pair_overrides(config.get("backtest_symbol_interval_pairs"))
    if pair_overrides:
        symbols = list(dict.fromkeys(item.symbol for item in pair_overrides))
        intervals = list(dict.fromkeys(item.interval for item in pair_overrides))

    if not symbols:
        raise ValueError("At least one symbol is required for backtesting.")
    if not intervals:
        raise ValueError("At least one interval is required for backtesting.")

    start_dt = coerce_datetime(patch.get("start", backtest_cfg.get("start_date")))
    end_dt = coerce_datetime(patch.get("end", backtest_cfg.get("end_date")))
    if end_dt is None:
        end_dt = datetime.now(timezone.utc).replace(tzinfo=None)
    if start_dt is None:
        start_dt = end_dt - timedelta(days=30)
    if start_dt >= end_dt:
        raise ValueError("Backtest start must be earlier than backtest end.")

    estimated_run_count = estimate_run_count(
        symbols,
        intervals,
        optimizer_signal_indicator_count,
        logic,
        pair_overrides,
        optimizer_generated=optimizer_generated_overrides,
    )
    if optimizer_generated_overrides and estimated_run_count > MAX_BACKTEST_OPTIMIZER_RUNS:
        raise ValueError(
            f"Optimizer would create {estimated_run_count} runs; reduce symbols, "
            f"intervals, or combination size (limit {MAX_BACKTEST_OPTIMIZER_RUNS})."
        )

    stop_loss_cfg = normalize_stop_loss_dict(
        patch.get("stop_loss", backtest_cfg.get("stop_loss", config.get("stop_loss")))
    )
    leverage = max(1.0, coerce_number(patch.get("leverage", backtest_cfg.get("leverage", config.get("leverage", 1))), 1.0))
    margin_mode = clean_text(
        patch.get("margin_mode", backtest_cfg.get("margin_mode", config.get("margin_mode", "Isolated"))),
        "Isolated",
    )
    position_mode = clean_text(
        patch.get("position_mode", backtest_cfg.get("position_mode", config.get("position_mode", "Hedge"))),
        "Hedge",
    )
    assets_mode = clean_text(
        patch.get("assets_mode", backtest_cfg.get("assets_mode", config.get("assets_mode", "Single-Asset"))),
        "Single-Asset",
    )
    account_mode = clean_text(
        patch.get("account_mode", backtest_cfg.get("account_mode", config.get("account_mode", "Classic Trading"))),
        "Classic Trading",
    )
    side = clean_text(patch.get("side", backtest_cfg.get("side", config.get("side", "BOTH"))), "BOTH")
    position_pct = max(
        0.0001,
        coerce_number(patch.get("position_pct", backtest_cfg.get("position_pct", config.get("position_pct", 1.0))), 1.0),
    )
    position_pct_units = clean_text(
        patch.get("position_pct_units", backtest_cfg.get("position_pct_units", "percent")),
        "percent",
    )
    mdd_logic = clean_text(patch.get("mdd_logic", backtest_cfg.get("mdd_logic", "per_trade")), "per_trade")

    request = BacktestRequest(
        symbols=symbols,
        intervals=intervals,
        indicators=indicators,
        logic=logic,
        symbol_source=symbol_source,
        start=start_dt,
        end=end_dt,
        capital=capital,
        side=side,
        position_pct=position_pct,
        position_pct_units=position_pct_units,
        leverage=leverage,
        margin_mode=margin_mode,
        position_mode=position_mode,
        assets_mode=assets_mode,
        account_mode=account_mode,
        mdd_logic=mdd_logic,
        stop_loss_enabled=coerce_bool(stop_loss_cfg.get("enabled"), False),
        stop_loss_mode=clean_text(stop_loss_cfg.get("mode"), "usdt"),
        stop_loss_usdt=coerce_number(stop_loss_cfg.get("usdt"), 0.0),
        stop_loss_percent=coerce_number(stop_loss_cfg.get("percent"), 0.0),
        stop_loss_scope=clean_text(stop_loss_cfg.get("scope"), "per_trade"),
        pair_overrides=pair_overrides,
    )

    mode = clean_text(patch.get("mode", config.get("mode", "Demo/Testnet")), "Demo/Testnet")
    account_type = clean_text(
        patch.get(
            "account_type",
            "Spot" if symbol_source.lower().startswith("spot") else config.get("account_type", "Futures"),
        ),
        "Futures",
    )
    connector_backend = clean_text(
        patch.get("connector_backend", backtest_cfg.get("connector_backend", config.get("connector_backend"))),
    )
    wrapper_kwargs = {
        "api_key": clean_text(patch.get("api_key", config.get("api_key"))),
        "api_secret": clean_text(patch.get("api_secret", config.get("api_secret"))),
        "mode": mode,
        "account_type": account_type,
        "default_leverage": int(max(1, round(leverage))),
        "default_margin_mode": margin_mode,
        "connector_backend": connector_backend or None,
    }
    summary = {
        "symbols": tuple(symbols),
        "intervals": tuple(intervals),
        "indicator_keys": tuple(ind.key for ind in indicators),
        "logic": logic,
        "symbol_source": symbol_source,
        "capital": capital,
        "estimated_run_count": estimated_run_count,
        "optimizer_enabled": optimizer_generated_overrides,
        "optimizer_mode": optimizer_mode,
        "optimizer_metric": optimizer_metric,
        "optimizer_combo_size": optimizer_combo_size,
        "optimizer_min_trades": optimizer_min_trades,
        "optimizer_mdd_limit": optimizer_mdd_limit,
        "optimizer_scope": scan_scope,
        "optimizer_scan_top_n": scan_top_n,
        "optimizer_signal_indicator_count": optimizer_signal_indicator_count,
        "optimizer_indicator_group_count": optimizer_indicator_group_count,
        "live_parity": {
            "mode": mode,
            "account_type": account_type,
            "margin_mode": margin_mode,
            "position_mode": position_mode,
            "side": side,
            "leverage": leverage,
            "position_pct": position_pct,
            "stop_loss_enabled": bool(request.stop_loss_enabled),
            "exchange_support": build_exchange_support_payload(
                config={
                    **config,
                    "connector_backend": connector_backend or config.get("connector_backend"),
                    "account_type": account_type,
                    "mode": mode,
                }
            ),
        },
    }
    return request, wrapper_kwargs, summary
