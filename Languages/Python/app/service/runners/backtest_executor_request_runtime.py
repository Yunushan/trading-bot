from __future__ import annotations

import copy
from datetime import datetime, timedelta, timezone

from ...config import coerce_bool, normalize_stop_loss_dict
from ...core.backtest import (
    BacktestRequest,
    IndicatorDefinition,
    PairOverride,
    normalize_backtest_interval,
    normalize_backtest_intervals,
)


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
    indicators: list[IndicatorDefinition] = []
    if isinstance(indicators_payload, dict):
        for key, params in indicators_payload.items():
            if not isinstance(params, dict) or not coerce_bool(params.get("enabled"), False):
                continue
            clean_params = copy.deepcopy(params)
            clean_params.pop("enabled", None)
            indicators.append(IndicatorDefinition(key=str(key), params=clean_params))
        return indicators
    if isinstance(indicators_payload, (list, tuple)):
        for item in indicators_payload:
            if not isinstance(item, dict):
                continue
            key = clean_text(item.get("key"))
            if not key:
                continue
            params = copy.deepcopy(item.get("params") or {})
            indicators.append(IndicatorDefinition(key=key, params=params if isinstance(params, dict) else {}))
    return indicators


def build_pair_overrides(overrides_payload) -> list[PairOverride] | None:  # noqa: ANN001
    if not isinstance(overrides_payload, (list, tuple)):
        return None
    overrides: list[PairOverride] = []
    seen: set[tuple[str, str]] = set()
    for item in overrides_payload:
        if not isinstance(item, dict):
            continue
        symbol = clean_text(item.get("symbol")).upper()
        interval = normalize_backtest_interval(item.get("interval"))
        if not symbol or not interval:
            continue
        key = (symbol, interval)
        if key in seen:
            continue
        seen.add(key)
        indicators = string_list(item.get("indicators"))
        leverage = None
        try:
            raw_leverage = item.get("leverage")
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
            )
        )
    return overrides or None


def estimate_run_count(
    symbols: list[str],
    intervals: list[str],
    indicator_count: int,
    logic: str,
    pair_overrides: list[PairOverride] | None,
) -> int:
    combos = len(pair_overrides) if pair_overrides else (len(symbols) * len(intervals))
    if combos <= 0:
        return 0
    if str(logic or "").upper() == "SEPARATE":
        return combos * max(1, indicator_count)
    return combos


def sort_runs(records: list) -> list:  # noqa: ANN001
    return sorted(
        records,
        key=lambda item: (
            float(getattr(item, "roi_percent", 0.0) or 0.0),
            float(getattr(item, "roi_value", 0.0) or 0.0),
            -float(getattr(item, "max_drawdown_percent", 0.0) or 0.0),
            int(getattr(item, "trades", 0) or 0),
        ),
        reverse=True,
    )


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

    logic = clean_text(patch.get("logic", backtest_cfg.get("logic", "AND")), "AND").upper()
    symbol_source = clean_text(patch.get("symbol_source", backtest_cfg.get("symbol_source", "Futures")), "Futures")
    capital = max(0.0, coerce_number(patch.get("capital", backtest_cfg.get("capital", 0.0)), 0.0))
    if capital <= 0.0:
        raise ValueError("Backtest capital must be positive.")

    pair_overrides = build_pair_overrides(
        patch.get("pair_overrides", config.get("backtest_symbol_interval_pairs"))
    )
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

    stop_loss_cfg = normalize_stop_loss_dict(patch.get("stop_loss", backtest_cfg.get("stop_loss")))
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

    mode = clean_text(patch.get("mode", config.get("mode", "Live")), "Live")
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
        "estimated_run_count": estimate_run_count(symbols, intervals, len(indicators), logic, pair_overrides),
    }
    return request, wrapper_kwargs, summary
