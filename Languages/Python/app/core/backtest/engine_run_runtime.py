from __future__ import annotations

from collections.abc import Iterator, Mapping
from dataclasses import replace
import time
from typing import Dict, List, Optional, Sequence

import pandas as pd

from ...settings.risk import coerce_bool, normalize_stop_loss_dict
from .data_quality import validate_backtest_frame
from .engine_data_runtime import slice_work_frame
from .optimizer_limits_runtime import BACKTEST_OPTIMIZER_PROGRESS_EVERY, format_optimizer_progress
from .optimizer_result_runtime import OptimizerTopResultCollector
from .engine_signal_runtime import IndicatorCache, SignalCache
from .indicator_runtime import filter_indicators, signal_indicators
from .models import BacktestRequest, BacktestRunResult, IndicatorDefinition, PairOverride


_PAIR_CONTROL_KEYS = (
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
)
_STOP_LOSS_KEYS = (
    "stop_loss_enabled",
    "stop_loss_mode",
    "stop_loss_usdt",
    "stop_loss_percent",
    "stop_loss_scope",
)


def _clean_text(value: object) -> str:
    return str(value or "").strip()


def _optional_float(value: object) -> float | None:
    if isinstance(value, bool) or value in (None, ""):
        return None
    try:
        return float(str(value).strip())
    except Exception:
        return None


def _optional_int(value: object) -> int | None:
    number = _optional_float(value)
    if number is None:
        return None
    try:
        return int(number)
    except Exception:
        return None


def _indicator_key_list(value: object) -> list[str]:
    if not isinstance(value, (list, tuple)):
        return []
    return sorted({str(key).strip() for key in value if str(key).strip()})


def _merge_override_controls(entry: object) -> dict[str, object]:
    controls: dict[str, object] = {}
    if isinstance(entry, PairOverride):
        raw_controls = entry.strategy_controls
        if isinstance(raw_controls, Mapping):
            controls.update(dict(raw_controls))
        for key in _PAIR_CONTROL_KEYS:
            value = getattr(entry, key, None)
            if value is not None:
                controls[key] = value
        return controls
    if not isinstance(entry, Mapping):
        return controls
    raw_controls = entry.get("strategy_controls")
    if isinstance(raw_controls, Mapping):
        controls.update(dict(raw_controls))
    for key in _PAIR_CONTROL_KEYS:
        if key in entry and entry.get(key) is not None:
            controls[key] = entry.get(key)
    if isinstance(entry.get("stop_loss"), Mapping):
        controls["stop_loss"] = dict(entry.get("stop_loss") or {})
    return controls


def _override_leverage(raw_value: object, controls: Mapping[str, object]) -> int | None:
    lev_val = _optional_int(raw_value)
    if lev_val is None:
        lev_val = _optional_int(controls.get("leverage"))
    if lev_val is None:
        return None
    return max(1, lev_val)


def iter_request_combos(
    request: BacktestRequest,
) -> Iterator[tuple[str, str, Optional[Sequence[str]], Optional[int], dict[str, object]]]:
    pair_override = getattr(request, "pair_overrides", None)
    if not pair_override:
        for symbol in request.symbols:
            sym_norm = str(symbol).strip().upper()
            if not sym_norm:
                continue
            for interval in request.intervals:
                iv_norm = str(interval).strip()
                if not iv_norm:
                    continue
                yield (sym_norm, iv_norm, None, None, {})
        return

    seen: set[tuple[str, str, tuple[str, ...]]] = set()
    for entry in pair_override:
        if isinstance(entry, PairOverride):
            sym_raw = entry.symbol
            iv_raw = entry.interval
            ind_raw = entry.indicators
            lev_raw = entry.leverage
            controls = _merge_override_controls(entry)
        elif isinstance(entry, dict):
            sym_raw = entry.get("symbol")
            iv_raw = entry.get("interval")
            ind_raw = entry.get("indicators")
            lev_raw = entry.get("leverage")
            controls = _merge_override_controls(entry)
        elif isinstance(entry, (list, tuple)):
            sym_raw = entry[0] if len(entry) > 0 else None
            iv_raw = entry[1] if len(entry) > 1 else None
            ind_raw = entry[2] if len(entry) > 2 else None
            lev_raw = entry[3] if len(entry) > 3 else None
            controls = {}
        else:
            continue
        sym_norm = str(sym_raw or "").strip().upper()
        iv_norm = str(iv_raw or "").strip()
        if not sym_norm or not iv_norm:
            continue
        indicator_keys = _indicator_key_list(ind_raw)
        key = (sym_norm, iv_norm, tuple(indicator_keys))
        if key in seen:
            continue
        seen.add(key)
        lev_val = _override_leverage(lev_raw, controls)
        yield (sym_norm, iv_norm, indicator_keys or None, lev_val, controls)


def build_request_combos(
    request: BacktestRequest,
) -> list[tuple[str, str, Optional[Sequence[str]], Optional[int], dict[str, object]]]:
    return list(iter_request_combos(request))


def resolve_effective_leverage(
    *,
    wrapper,
    request: BacktestRequest,
    symbol: str,
    source_label_lower: str,
    override_leverage: int | None,
) -> int:
    if isinstance(override_leverage, (int, float)):
        requested_leverage = int(float(override_leverage))
    else:
        requested_leverage = int(request.leverage or 1)
    if requested_leverage < 1:
        requested_leverage = 1
    if source_label_lower.startswith("fut") and hasattr(wrapper, "clamp_futures_leverage"):
        try:
            return int(wrapper.clamp_futures_leverage(symbol, requested_leverage))
        except Exception:
            return requested_leverage
    return requested_leverage


def resolve_indicator_bundle(
    *,
    active_indicators: list[IndicatorDefinition],
    indicator_map: dict[str, IndicatorDefinition],
    override_keys: Sequence[str] | None,
) -> list[IndicatorDefinition]:
    if not override_keys:
        return active_indicators
    override_defs = [indicator_map[key] for key in override_keys if key in indicator_map]
    override_key_set = {indicator.key for indicator in override_defs}
    global_filters = [
        indicator
        for indicator in filter_indicators(active_indicators)
        if indicator.key not in override_key_set
    ]
    return (override_defs + global_filters) or active_indicators


def build_effective_request(
    request: BacktestRequest,
    controls: Mapping[str, object],
    *,
    effective_leverage: int,
) -> BacktestRequest:
    if not controls:
        return replace(request, leverage=float(effective_leverage))
    updates: dict[str, object] = {"leverage": float(effective_leverage)}
    logic = _clean_text(controls.get("logic")).upper()
    if logic in {"AND", "OR", "SEPARATE"}:
        updates["logic"] = logic
    capital = _optional_float(controls.get("capital"))
    if capital is not None and capital > 0.0:
        updates["capital"] = capital
    side = _clean_text(controls.get("side")).upper()
    if side in {"BUY", "SELL", "BOTH"}:
        updates["side"] = side
    position_pct = _optional_float(controls.get("position_pct"))
    if position_pct is not None and position_pct > 0.0:
        updates["position_pct"] = position_pct
    position_pct_units = _clean_text(controls.get("position_pct_units"))
    if position_pct_units:
        updates["position_pct_units"] = position_pct_units
    for key in (
        "margin_mode",
        "position_mode",
        "assets_mode",
        "account_mode",
        "mdd_logic",
    ):
        text = _clean_text(controls.get(key))
        if text:
            updates[key] = text

    stop_loss_cfg = None
    if isinstance(controls.get("stop_loss"), Mapping):
        stop_loss_cfg = normalize_stop_loss_dict(controls.get("stop_loss"))
    if any(key in controls for key in _STOP_LOSS_KEYS):
        base = stop_loss_cfg or {
            "enabled": request.stop_loss_enabled,
            "mode": request.stop_loss_mode,
            "usdt": request.stop_loss_usdt,
            "percent": request.stop_loss_percent,
            "scope": request.stop_loss_scope,
        }
        stop_loss_cfg = dict(base)
        if "stop_loss_enabled" in controls:
            stop_loss_cfg["enabled"] = coerce_bool(controls.get("stop_loss_enabled"), False)
        if "stop_loss_mode" in controls:
            stop_loss_cfg["mode"] = _clean_text(controls.get("stop_loss_mode")) or "usdt"
        if "stop_loss_usdt" in controls:
            stop_loss_cfg["usdt"] = _optional_float(controls.get("stop_loss_usdt")) or 0.0
        if "stop_loss_percent" in controls:
            stop_loss_cfg["percent"] = _optional_float(controls.get("stop_loss_percent")) or 0.0
        if "stop_loss_scope" in controls:
            stop_loss_cfg["scope"] = _clean_text(controls.get("stop_loss_scope")) or "per_trade"
        stop_loss_cfg = normalize_stop_loss_dict(stop_loss_cfg)
    if stop_loss_cfg is not None:
        updates["stop_loss_enabled"] = bool(stop_loss_cfg.get("enabled"))
        updates["stop_loss_mode"] = str(stop_loss_cfg.get("mode") or "usdt")
        updates["stop_loss_usdt"] = _optional_float(stop_loss_cfg.get("usdt", 0.0)) or 0.0
        updates["stop_loss_percent"] = _optional_float(stop_loss_cfg.get("percent", 0.0)) or 0.0
        updates["stop_loss_scope"] = str(stop_loss_cfg.get("scope") or "per_trade")
    return replace(request, **updates)


def strategy_controls_from_request(
    request: BacktestRequest,
    *,
    effective_leverage: int,
) -> dict[str, object]:
    return {
        "logic": request.logic,
        "capital": request.capital,
        "side": request.side,
        "position_pct": request.position_pct,
        "position_pct_units": request.position_pct_units,
        "leverage": int(effective_leverage),
        "margin_mode": request.margin_mode,
        "position_mode": request.position_mode,
        "assets_mode": request.assets_mode,
        "account_mode": request.account_mode,
        "mdd_logic": request.mdd_logic,
        "stop_loss": {
            "enabled": bool(request.stop_loss_enabled),
            "mode": request.stop_loss_mode,
            "usdt": float(request.stop_loss_usdt or 0.0),
            "percent": float(request.stop_loss_percent or 0.0),
            "scope": request.stop_loss_scope,
        },
    }


def run_backtest(
    engine,
    request: BacktestRequest,
    progress=None,
    should_stop=None,
) -> Dict[str, object]:
    progress = progress or (lambda _msg: None)
    source_label = (request.symbol_source or "").strip() if hasattr(request, "symbol_source") else ""
    runs: List[BacktestRunResult] = []
    errors: List[Dict[str, object]] = []

    if not request.indicators:
        raise ValueError("At least one indicator must be selected for backtesting.")

    active_indicators = [ind_def for ind_def in request.indicators if ind_def and ind_def.key]
    if not active_indicators:
        raise ValueError("No indicators available for backtesting.")
    if not signal_indicators(active_indicators):
        raise ValueError("At least one signal indicator is required; filter-only indicators cannot open trades.")

    indicator_map = {ind.key: ind for ind in active_indicators}
    data_cache: dict[tuple[str, str], pd.DataFrame] = {}
    indicator_cache: IndicatorCache = {}
    signal_cache: SignalCache = {}
    result_collector = OptimizerTopResultCollector.from_request(request)
    processed_count = 0
    optimizer_started_at = time.monotonic()

    def _record_run(run: BacktestRunResult) -> None:
        if result_collector is not None:
            result_collector.add(run)
        else:
            runs.append(run)

    engine._should_stop_cb = should_stop
    try:
        source_label_lower = str(request.symbol_source or "").strip().lower()
        for symbol, interval, override_keys, override_leverage, override_controls in iter_request_combos(request):
            if should_stop and should_stop():
                raise RuntimeError("backtest_cancelled")
            try:
                effective_leverage = resolve_effective_leverage(
                    wrapper=engine.wrapper,
                    request=request,
                    symbol=symbol,
                    source_label_lower=source_label_lower,
                    override_leverage=override_leverage,
                )
                effective_request = build_effective_request(
                    request,
                    override_controls,
                    effective_leverage=effective_leverage,
                )
                effective_logic = (effective_request.logic or "AND").strip().upper()
                indicator_bundle = resolve_indicator_bundle(
                    active_indicators=active_indicators,
                    indicator_map=indicator_map,
                    override_keys=override_keys,
                )
                cache_key = (symbol, interval)
                df = data_cache.get(cache_key)
                if df is None:
                    detail = f" ({source_label})" if source_label else ""
                    progress(f"Fetching {symbol} @ {interval}{detail} data...")
                    df = engine._load_klines(symbol, interval, request.start, request.end, active_indicators)
                    if df is not None:
                        data_cache[cache_key] = df
                if df is None or df.empty:
                    raise RuntimeError("No historical data returned.")
                validate_backtest_frame(df, interval=interval)

                work_df, work_start_idx = slice_work_frame(df, effective_request.start)
                if effective_logic == "SEPARATE":
                    separate_signal_indicators = signal_indicators(indicator_bundle)
                    shared_filter_indicators = filter_indicators(indicator_bundle)
                    if not separate_signal_indicators:
                        raise RuntimeError("No signal indicator available for this backtest run.")
                    for indicator in separate_signal_indicators:
                        if should_stop and should_stop():
                            raise RuntimeError("backtest_cancelled")
                        run = engine._simulate(
                            symbol,
                            interval,
                            df,
                            [indicator, *shared_filter_indicators],
                            effective_request,
                            leverage_override=effective_leverage,
                            indicator_cache=indicator_cache,
                            signal_cache=signal_cache,
                            work_df=work_df,
                            work_start_idx=work_start_idx,
                        )
                        if run is not None:
                            run.symbol = symbol
                            run.interval = interval
                            run.leverage = float(effective_leverage)
                            run.strategy_controls = strategy_controls_from_request(
                                effective_request,
                                effective_leverage=effective_leverage,
                            )
                            _record_run(run)
                            processed_count += 1
                            if (
                                result_collector is not None
                                and processed_count % BACKTEST_OPTIMIZER_PROGRESS_EVERY == 0
                            ):
                                progress(
                                    format_optimizer_progress(
                                        processed_count,
                                        result_collector.run_count or processed_count,
                                        elapsed_seconds=time.monotonic() - optimizer_started_at,
                                    )
                                )
                else:
                    run = engine._simulate(
                        symbol,
                        interval,
                        df,
                        indicator_bundle,
                        effective_request,
                        leverage_override=effective_leverage,
                        indicator_cache=indicator_cache,
                        signal_cache=signal_cache,
                        work_df=work_df,
                        work_start_idx=work_start_idx,
                    )
                    if run is not None:
                        run.symbol = symbol
                        run.interval = interval
                        run.leverage = float(effective_leverage)
                        run.strategy_controls = strategy_controls_from_request(
                            effective_request,
                            effective_leverage=effective_leverage,
                        )
                        _record_run(run)
                        processed_count += 1
                        if (
                            result_collector is not None
                            and processed_count % BACKTEST_OPTIMIZER_PROGRESS_EVERY == 0
                        ):
                            progress(
                                format_optimizer_progress(
                                    processed_count,
                                    result_collector.run_count or processed_count,
                                    elapsed_seconds=time.monotonic() - optimizer_started_at,
                                )
                            )
            except Exception as exc:
                if str(exc).lower().startswith("backtest_cancelled"):
                    raise
                errors.append({"symbol": symbol, "interval": interval, "error": str(exc)})
    finally:
        engine._should_stop_cb = None

    if result_collector is not None:
        runs = result_collector.finish()
    return {"runs": runs, "errors": errors}
