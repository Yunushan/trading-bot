from __future__ import annotations

from typing import Dict, List, Optional, Sequence

import pandas as pd

from .engine_data_runtime import slice_work_frame
from .engine_signal_runtime import IndicatorCache, SignalCache
from .models import BacktestRequest, BacktestRunResult, IndicatorDefinition, PairOverride


def build_request_combos(
    request: BacktestRequest,
) -> list[tuple[str, str, Optional[Sequence[str]], Optional[int]]]:
    pair_override = getattr(request, "pair_overrides", None)
    if not pair_override:
        combos: list[tuple[str, str, Optional[Sequence[str]], Optional[int]]] = []
        for symbol in request.symbols:
            sym_norm = str(symbol).strip().upper()
            if not sym_norm:
                continue
            for interval in request.intervals:
                iv_norm = str(interval).strip()
                if not iv_norm:
                    continue
                combos.append((sym_norm, iv_norm, None, None))
        return combos

    combos = []
    seen: set[tuple[str, str, tuple[str, ...]]] = set()
    for entry in pair_override:
        if isinstance(entry, PairOverride):
            sym_raw = entry.symbol
            iv_raw = entry.interval
            ind_raw = entry.indicators
            lev_raw = entry.leverage
        elif isinstance(entry, dict):
            sym_raw = entry.get("symbol")
            iv_raw = entry.get("interval")
            ind_raw = entry.get("indicators")
            lev_raw = entry.get("leverage")
        elif isinstance(entry, (list, tuple)):
            sym_raw = entry[0] if len(entry) > 0 else None
            iv_raw = entry[1] if len(entry) > 1 else None
            ind_raw = entry[2] if len(entry) > 2 else None
            lev_raw = entry[3] if len(entry) > 3 else None
        else:
            continue
        sym_norm = str(sym_raw or "").strip().upper()
        iv_norm = str(iv_raw or "").strip()
        if not sym_norm or not iv_norm:
            continue
        if isinstance(ind_raw, (list, tuple)):
            indicator_keys = sorted({str(key).strip() for key in ind_raw if str(key).strip()})
        else:
            indicator_keys = []
        key = (sym_norm, iv_norm, tuple(indicator_keys))
        if key in seen:
            continue
        seen.add(key)
        lev_val = None
        try:
            if lev_raw is not None:
                lev_val = int(float(lev_raw))
        except Exception:
            lev_val = None
        combos.append((sym_norm, iv_norm, indicator_keys or None, lev_val))
    return combos


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
    return override_defs or active_indicators


def run_backtest(
    engine,
    request: BacktestRequest,
    progress=None,
    should_stop=None,
) -> Dict[str, object]:
    progress = progress or (lambda _msg: None)
    logic = (request.logic or "AND").strip().upper()
    source_label = (request.symbol_source or "").strip() if hasattr(request, "symbol_source") else ""
    runs: List[BacktestRunResult] = []
    errors: List[Dict[str, object]] = []

    if not request.indicators:
        raise ValueError("At least one indicator must be selected for backtesting.")

    active_indicators = [ind_def for ind_def in request.indicators if ind_def and ind_def.key]
    if not active_indicators:
        raise ValueError("No indicators available for backtesting.")

    indicator_map = {ind.key: ind for ind in active_indicators}
    data_cache: dict[tuple[str, str], pd.DataFrame] = {}
    indicator_cache: IndicatorCache = {}
    signal_cache: SignalCache = {}
    combos = build_request_combos(request)

    engine._should_stop_cb = should_stop
    try:
        source_label_lower = str(request.symbol_source or "").strip().lower()
        for symbol, interval, override_keys, override_leverage in combos:
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
                    df = engine._load_klines(symbol, interval, request.start, request.end, indicator_bundle)
                    if df is not None:
                        data_cache[cache_key] = df
                if df is None or df.empty:
                    raise RuntimeError("No historical data returned.")

                work_df, work_start_idx = slice_work_frame(df, request.start)
                if logic == "SEPARATE":
                    for indicator in indicator_bundle:
                        if should_stop and should_stop():
                            raise RuntimeError("backtest_cancelled")
                        run = engine._simulate(
                            symbol,
                            interval,
                            df,
                            [indicator],
                            request,
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
                            runs.append(run)
                else:
                    run = engine._simulate(
                        symbol,
                        interval,
                        df,
                        indicator_bundle,
                        request,
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
                        runs.append(run)
            except Exception as exc:
                if str(exc).lower().startswith("backtest_cancelled"):
                    raise
                errors.append({"symbol": symbol, "interval": interval, "error": str(exc)})
    finally:
        engine._should_stop_cb = None

    return {"runs": runs, "errors": errors}
