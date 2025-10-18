from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Callable, Dict, Iterable, List, Optional, Sequence, Tuple

import numpy as np
import pandas as pd

from . import indicators as ind
from .binance_wrapper import _coerce_interval_seconds
from .config import STOP_LOSS_MODE_ORDER, STOP_LOSS_SCOPE_OPTIONS


@dataclass
class IndicatorDefinition:
    key: str
    params: Dict[str, object]


@dataclass
class PairOverride:
    symbol: str
    interval: str
    indicators: Optional[List[str]] = None
    leverage: Optional[int] = None


@dataclass
class BacktestRequest:
    symbols: List[str]
    intervals: List[str]
    indicators: List[IndicatorDefinition]
    logic: str
    symbol_source: str
    start: datetime
    end: datetime
    capital: float
    side: str = "BOTH"
    position_pct: float = 1.0
    leverage: float = 1.0
    margin_mode: str = "Isolated"
    position_mode: str = "Hedge"
    assets_mode: str = "Single-Asset"
    account_mode: str = "Classic Trading"
    stop_loss_enabled: bool = False
    stop_loss_mode: str = "usdt"
    stop_loss_usdt: float = 0.0
    stop_loss_percent: float = 0.0
    stop_loss_scope: str = "per_trade"
    pair_overrides: Optional[List[PairOverride]] = None


@dataclass
class BacktestRunResult:
    symbol: str
    interval: str
    indicator_keys: List[str]
    trades: int
    roi_value: float
    roi_percent: float
    final_equity: float
    logic: str
    leverage: float
    start: datetime | None = None
    end: datetime | None = None
    position_pct: float | None = None
    stop_loss_enabled: bool | None = None
    stop_loss_mode: str | None = None
    stop_loss_usdt: float | None = None
    stop_loss_percent: float | None = None
    stop_loss_scope: str | None = None
    margin_mode: str | None = None
    position_mode: str | None = None
    assets_mode: str | None = None
    account_mode: str | None = None


class BacktestEngine:
    def __init__(self, wrapper):
        self.wrapper = wrapper
        self._should_stop_cb = None

    def run(self, request: BacktestRequest, progress: Optional[Callable[[str], None]] = None,
            should_stop: Optional[Callable[[], bool]] = None) -> Dict[str, object]:
        progress = progress or (lambda _msg: None)
        self._should_stop_cb = should_stop
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
        indicator_cache: dict[tuple[str, str, str, Tuple[Tuple[str, object], ...]], pd.Series] = {}

        combos: List[tuple[str, str, Optional[Sequence[str]], Optional[int]]]
        pair_override = getattr(request, "pair_overrides", None)
        if pair_override:
            combos = []
            seen: set[tuple[str, str, Tuple[str, ...]]] = set()
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
                    indicator_keys = sorted({str(k).strip() for k in ind_raw if str(k).strip()})
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
        else:
            combos = []
            for symbol in request.symbols:
                sym_norm = str(symbol).strip().upper()
                if not sym_norm:
                    continue
                for interval in request.intervals:
                    iv_norm = str(interval).strip()
                    if not iv_norm:
                        continue
                    combos.append((sym_norm, iv_norm, None, None))

        try:
            source_label_lower = str(request.symbol_source or "").strip().lower()
            for symbol, interval, override_keys, override_leverage in combos:
                if should_stop and should_stop():
                    raise RuntimeError("backtest_cancelled")
                try:
                    if isinstance(override_leverage, (int, float)):
                        requested_leverage = int(float(override_leverage))
                    else:
                        requested_leverage = int(request.leverage or 1)
                    if requested_leverage < 1:
                        requested_leverage = 1
                    if source_label_lower.startswith("fut") and hasattr(self.wrapper, "clamp_futures_leverage"):
                        try:
                            effective_leverage = int(self.wrapper.clamp_futures_leverage(symbol, requested_leverage))
                        except Exception:
                            effective_leverage = requested_leverage
                    else:
                        effective_leverage = requested_leverage
                    if override_keys:
                        override_defs = [indicator_map[k] for k in override_keys if k in indicator_map]
                        if override_defs:
                            indicator_bundle = override_defs
                        else:
                            indicator_bundle = active_indicators
                    else:
                        indicator_bundle = active_indicators
                    cache_key = (symbol, interval)
                    df = data_cache.get(cache_key)
                    if df is None:
                        detail = f" ({source_label})" if source_label else ""
                        progress(f"Fetching {symbol} @ {interval}{detail} data...")
                        df = self._load_klines(symbol, interval, request.start, request.end, indicator_bundle)
                        if df is not None:
                            data_cache[cache_key] = df
                    if df is None or df.empty:
                        raise RuntimeError("No historical data returned.")
                    if logic == "SEPARATE":
                        for indicator in indicator_bundle:
                            if should_stop and should_stop():
                                raise RuntimeError("backtest_cancelled")
                            run = self._simulate(
                                symbol,
                                interval,
                                df,
                                [indicator],
                                request,
                                leverage_override=effective_leverage,
                                indicator_cache=indicator_cache,
                            )
                            if run is not None:
                                run.symbol = symbol
                                run.interval = interval
                                run.leverage = float(effective_leverage)
                                runs.append(run)
                    else:
                        run = self._simulate(
                            symbol,
                            interval,
                            df,
                            indicator_bundle,
                            request,
                            leverage_override=effective_leverage,
                            indicator_cache=indicator_cache,
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
            self._should_stop_cb = None
        return {"runs": runs, "errors": errors}

    def _load_klines(self, symbol: str, interval: str, start: datetime, end: datetime,
                     indicators: Iterable[IndicatorDefinition]) -> pd.DataFrame:
        warmup_bars = max(self._estimate_warmup(indicator) for indicator in indicators) or 100
        try:
            interval_seconds = _coerce_interval_seconds(interval)
        except Exception:
            raise ValueError(f"Invalid backtest interval: {interval}")
        warmup_seconds = warmup_bars * interval_seconds
        buffered_start = start - timedelta(seconds=warmup_seconds * 2)
        acct = str(getattr(self.wrapper, "account_type", "") or "").upper()
        limit = 1500 if acct.startswith("FUT") else 1000
        return self.wrapper.get_klines_range(symbol, interval, buffered_start, end, limit=limit)

    @staticmethod
    def _estimate_warmup(indicator: IndicatorDefinition) -> int:
        params = indicator.params or {}
        length_candidates = []
        for key in ("length", "fast", "slow", "signal", "smooth_k", "smooth_d", "short", "medium", "long", "atr_period"):
            try:
                val = params.get(key)
                if val is not None:
                    length_candidates.append(int(float(val)))
            except Exception:
                continue
        return max(length_candidates or [50])

    def _simulate(
        self,
        symbol: str,
        interval: str,
        df: pd.DataFrame,
        indicators: List[IndicatorDefinition],
        request: BacktestRequest,
        *,
        leverage_override: float | None = None,
        indicator_cache: Optional[dict[tuple[str, str, str, Tuple[Tuple[str, object], ...]], pd.Series]] = None,
    ) -> Optional[BacktestRunResult]:
        logic = (request.logic or "AND").upper()
        work_df = df.loc[df.index >= request.start]
        if work_df.empty:
            return None

        capital = float(request.capital or 0.0)
        if capital <= 0.0:
            return None

        pct_raw = float(request.position_pct or 0.0)
        pct_fraction = pct_raw / 100.0 if pct_raw > 1.0 else pct_raw
        pct_fraction = max(0.0001, min(1.0, pct_fraction))
        leverage = max(1.0, float(leverage_override if leverage_override is not None else (request.leverage or 1.0)))
        margin_mode = (request.margin_mode or "Isolated").strip().upper()
        side_pref = (request.side or "BOTH").strip().upper()

        indicator_signals: List[Dict[str, Optional[np.ndarray]]] = []
        indicator_keys: List[str] = []
        work_index = work_df.index
        for indicator in indicators:
            cache_key = (
                symbol,
                interval,
                indicator.key,
                tuple(
                    sorted(
                        (key, (value if isinstance(value, (int, float, str, bool, type(None))) else repr(value)))
                        for key, value in (indicator.params or {}).items()
                    )
                ),
            )
            series_full = None
            if indicator_cache is not None:
                series_full = indicator_cache.get(cache_key)
            if series_full is None:
                series_full = self._compute_indicator_series(df, indicator)
                if series_full is not None:
                    series_full = series_full.astype(float, copy=False)
                    if indicator_cache is not None:
                        indicator_cache[cache_key] = series_full
            if series_full is None:
                continue

            series = series_full.reindex(work_index)
            if series is None:
                continue
            buy_val = indicator.params.get("buy_value")
            sell_val = indicator.params.get("sell_value")
            buy_events, sell_events = self._generate_signals(series, buy_val, sell_val)
            if buy_events is None and sell_events is None:
                continue

            buy_array = (
                buy_events.reindex(work_index, fill_value=False).to_numpy(dtype=bool, copy=False)
                if buy_events is not None else None
            )
            sell_array = (
                sell_events.reindex(work_index, fill_value=False).to_numpy(dtype=bool, copy=False)
                if sell_events is not None else None
            )
            indicator_signals.append({"buy": buy_array, "sell": sell_array})
            indicator_keys.append(indicator.key)

        if not indicator_signals:
            return None

        should_stop_cb = getattr(self, '_should_stop_cb', None)
        position_open = False
        entry_price = 0.0
        units = 0.0
        position_margin = 0.0
        direction = ""
        equity = float(capital)
        trades = 0

        can_long = side_pref in ("BUY", "BOTH")
        can_short = side_pref in ("SELL", "BOTH")
        stop_enabled = bool(getattr(request, "stop_loss_enabled", False))
        stop_mode = str(getattr(request, "stop_loss_mode", "usdt")).lower()
        if stop_mode not in STOP_LOSS_MODE_ORDER:
            stop_mode = STOP_LOSS_MODE_ORDER[0]
        stop_usdt = max(0.0, float(getattr(request, "stop_loss_usdt", 0.0) or 0.0))
        stop_percent = max(0.0, float(getattr(request, "stop_loss_percent", 0.0) or 0.0))
        scope = str(getattr(request, "stop_loss_scope", "per_trade") or "per_trade").lower()
        if scope not in STOP_LOSS_SCOPE_OPTIONS:
            scope = STOP_LOSS_SCOPE_OPTIONS[0]
        is_cumulative = stop_enabled and scope == "cumulative"

        n_rows = len(work_df)
        if n_rows == 0:
            return None

        close_values = work_df["close"].to_numpy(dtype=float, copy=False)
        high_values = work_df["high"].to_numpy(dtype=float, copy=False) if "high" in work_df else close_values
        low_values = work_df["low"].to_numpy(dtype=float, copy=False) if "low" in work_df else close_values

        buy_arrays = [signals["buy"] for signals in indicator_signals if signals["buy"] is not None]
        sell_arrays = [signals["sell"] for signals in indicator_signals if signals["sell"] is not None]

        if buy_arrays:
            buy_stack = np.vstack(buy_arrays)
            if logic == "AND":
                aggregated_buy_array = np.all(buy_stack, axis=0)
            else:
                aggregated_buy_array = np.any(buy_stack, axis=0)
        else:
            aggregated_buy_array = np.zeros(n_rows, dtype=bool)

        if sell_arrays:
            sell_stack = np.vstack(sell_arrays)
            aggregated_sell_array = np.any(sell_stack, axis=0)
        else:
            aggregated_sell_array = np.zeros(n_rows, dtype=bool)

        for idx in range(n_rows):
            if should_stop_cb and callable(should_stop_cb) and should_stop_cb():
                raise RuntimeError('backtest_cancelled')
            price = float(close_values[idx] if np.isfinite(close_values[idx]) else 0.0)
            if price <= 0.0:
                continue
            high_price_val = float(high_values[idx] if np.isfinite(high_values[idx]) else price)
            if high_price_val <= 0.0:
                high_price_val = price
            low_price_val = float(low_values[idx] if np.isfinite(low_values[idx]) else price)
            if low_price_val <= 0.0:
                low_price_val = price

            aggregated_buy = bool(aggregated_buy_array[idx])
            aggregated_sell = bool(aggregated_sell_array[idx])

            if position_open:
                effective_leverage = leverage
                if margin_mode == "CROSS":
                    effective_leverage = max(1.0, leverage * pct_fraction)
                if direction == "LONG" and effective_leverage > 1.0:
                    liq_price = entry_price * (1.0 - (1.0 / effective_leverage))
                    if liq_price < 0.0:
                        liq_price = 0.0
                    if low_price_val <= liq_price:
                        loss = min(equity, position_margin)
                        equity = max(0.0, equity - loss)
                        position_open = False
                        units = 0.0
                        position_margin = 0.0
                        direction = ""
                        continue
                if direction == "SHORT" and effective_leverage > 1.0:
                    liq_price = entry_price * (1.0 + (1.0 / effective_leverage))
                    if high_price_val >= liq_price:
                        loss = min(equity, position_margin)
                        equity = max(0.0, equity - loss)
                        position_open = False
                        units = 0.0
                        position_margin = 0.0
                        direction = ""
                        continue

                if stop_enabled and units > 0.0 and entry_price > 0.0:
                    if direction == "LONG":
                        worst_price = min(price, low_price_val)
                        loss_usdt = max(0.0, (entry_price - worst_price) * units)
                    else:
                        worst_price = max(price, high_price_val)
                        loss_usdt = max(0.0, (worst_price - entry_price) * units)
                    denom = entry_price * units
                    loss_pct = (loss_usdt / denom * 100.0) if denom > 0 else 0.0
                    triggered = False
                    if stop_mode in ("usdt", "both") and stop_usdt > 0.0 and loss_usdt >= stop_usdt:
                        triggered = True
                    if not triggered and stop_mode in ("percent", "both") and stop_percent > 0.0 and loss_pct >= stop_percent:
                        triggered = True
                    if triggered:
                        exit_price = worst_price
                        pnl = (exit_price - entry_price) * units if direction == "LONG" else (entry_price - exit_price) * units
                        equity = max(0.0, equity + pnl)
                        position_open = False
                        units = 0.0
                        position_margin = 0.0
                        direction = ""
                        trades += 1
                        continue

                if direction == "LONG" and aggregated_sell:
                    pnl = (price - entry_price) * units
                    equity = max(0.0, equity + pnl)
                    position_open = False
                    units = 0.0
                    position_margin = 0.0
                    direction = ""
                    if can_short and aggregated_sell and equity > 0.0:
                        # allow immediate flip to short if permitted
                        aggregated_sell = True
                    else:
                        aggregated_sell = False
                elif direction == "SHORT" and aggregated_buy:
                    pnl = (entry_price - price) * units
                    equity = max(0.0, equity + pnl)
                    position_open = False
                    units = 0.0
                    position_margin = 0.0
                    direction = ""
                    if can_long and aggregated_buy and equity > 0.0:
                        aggregated_buy = True
                    else:
                        aggregated_buy = False

            if not position_open and equity > 0.0:
                if aggregated_buy and can_long:
                    entry_price = price
                    position_margin = equity * pct_fraction
                    units = (position_margin * leverage) / entry_price if entry_price > 0.0 else 0.0
                    if units <= 0.0:
                        position_margin = 0.0
                        continue
                    position_open = True
                    direction = "LONG"
                    trades += 1
                elif aggregated_sell and can_short:
                    entry_price = price
                    position_margin = equity * pct_fraction
                    units = (position_margin * leverage) / entry_price if entry_price > 0.0 else 0.0
                    if units <= 0.0:
                        position_margin = 0.0
                        continue
                    position_open = True
                    direction = "SHORT"
                    trades += 1

        if position_open and units > 0.0:
            last_price = float(work_df['close'].iloc[-1] or 0.0)
            if direction == "LONG":
                pnl = (last_price - entry_price) * units
            else:
                pnl = (entry_price - last_price) * units
            equity = max(0.0, equity + pnl)
            position_open = False
            units = 0.0
            position_margin = 0.0
            direction = ""

        roi_value = equity - capital
        roi_percent = (roi_value / capital * 100.0) if capital else 0.0

        position_mode_val = (request.position_mode or "").strip() if hasattr(request, "position_mode") else ""
        assets_mode_val = (request.assets_mode or "").strip() if hasattr(request, "assets_mode") else ""
        account_mode_val = (request.account_mode or "").strip() if hasattr(request, "account_mode") else ""

        return BacktestRunResult(
            symbol="",
            interval="",
            indicator_keys=indicator_keys,
            trades=trades,
            roi_value=float(roi_value),
            roi_percent=float(roi_percent),
            final_equity=float(equity),
            logic=logic,
            leverage=float(leverage),
            start=request.start,
            end=request.end,
            position_pct=pct_fraction,
            stop_loss_enabled=stop_enabled,
            stop_loss_mode=stop_mode,
            stop_loss_usdt=stop_usdt,
            stop_loss_percent=stop_percent,
            stop_loss_scope=scope,
            margin_mode=margin_mode,
            position_mode=position_mode_val,
            assets_mode=assets_mode_val,
            account_mode=account_mode_val,
        )

    @staticmethod
    def _generate_signals(series: pd.Series, buy_value, sell_value) -> tuple[Optional[pd.Series], Optional[pd.Series]]:
        if series is None or series.empty:
            return None, None

        def _to_bool(ser: pd.Series) -> pd.Series:
            if not pd.api.types.is_bool_dtype(ser):
                ser = ser.where(ser.notna(), False)
                try:
                    ser = ser.infer_objects(copy=False)
                except AttributeError:
                    pass
            return ser.astype(bool, copy=False)

        buy_events = None
        sell_events = None
        if buy_value is not None:
            if sell_value is not None and float(buy_value) < float(sell_value):
                buy_condition = series <= float(buy_value)
            else:
                buy_condition = series >= float(buy_value)
        if buy_value is not None:
            buy_condition = _to_bool(buy_condition)
            prev_buy = _to_bool(buy_condition.shift(1))
            buy_events = buy_condition & (~prev_buy)
        if sell_value is not None:
            if buy_value is not None and float(buy_value) < float(sell_value):
                sell_condition = series >= float(sell_value)
            else:
                sell_condition = series <= float(sell_value)
            sell_condition = _to_bool(sell_condition)
            prev_sell = _to_bool(sell_condition.shift(1))
            sell_events = sell_condition & (~prev_sell)
        return buy_events, sell_events

    @staticmethod
    def _compute_indicator_series(df: pd.DataFrame, indicator: IndicatorDefinition) -> Optional[pd.Series]:
        key = indicator.key
        params = indicator.params or {}

        try:
            if key == "rsi":
                length = int(params.get("length") or 14)
                return ind.rsi(df['close'], length=length)
            if key == "ma":
                length = int(params.get("length") or 20)
                ma_type = str(params.get("type") or "SMA").upper()
                if ma_type == "EMA":
                    return ind.ema(df['close'], length)
                return ind.sma(df['close'], length)
            if key == "donchian":
                length = int(params.get("length") or 20)
                high = ind.donchian_high(df, length)
                low = ind.donchian_low(df, length)
                return (high + low) / 2.0
            if key == "bb":
                length = int(params.get("length") or 20)
                std = float(params.get("std") or 2.0)
                _upper, mid, _lower = ind.bollinger_bands(df, length=length, std=std)
                return mid
            if key == "psar":
                af = float(params.get("af") or 0.02)
                max_af = float(params.get("max_af") or 0.2)
                return ind.parabolic_sar(df, af=af, max_af=max_af)
            if key == "stoch_rsi":
                length = int(params.get("length") or 14)
                smooth_k = int(params.get("smooth_k") or 3)
                smooth_d = int(params.get("smooth_d") or 3)
                k, _d = ind.stoch_rsi(df['close'], length=length, smooth_k=smooth_k, smooth_d=smooth_d)
                return k
            if key == "willr":
                length = int(params.get("length") or 14)
                return ind.williams_r(df, length=length)
            if key == "macd":
                fast = int(params.get("fast") or 12)
                slow = int(params.get("slow") or 26)
                signal = int(params.get("signal") or 9)
                _macd, _signal, hist = ind.macd(df['close'], fast=fast, slow=slow, signal=signal)
                return hist
            if key == "volume":
                return df['volume']
            if key == "uo":
                short = int(params.get("short") or 7)
                medium = int(params.get("medium") or 14)
                long = int(params.get("long") or 28)
                return ind.ultimate_oscillator(df, short=short, medium=medium, long=long)
            if key == "ema":
                length = int(params.get("length") or 20)
                return ind.ema(df['close'], length)
            if key == "adx":
                length = int(params.get("length") or 14)
                return ind.adx(df, length=length)
            if key == "dmi":
                length = int(params.get("length") or 14)
                plus_di, minus_di, _ = ind.dmi(df, length=length)
                return (plus_di - minus_di)
            if key == "supertrend":
                atr_period = int(params.get("atr_period") or 10)
                multiplier = float(params.get("multiplier") or 3.0)
                return ind.supertrend(df, atr_period=atr_period, multiplier=multiplier)
            if key == "stochastic":
                length = int(params.get("length") or 14)
                smooth_k = int(params.get("smooth_k") or 3)
                smooth_d = int(params.get("smooth_d") or 3)
                k, _d = ind.stochastic(df, length=length, smooth_k=smooth_k, smooth_d=smooth_d)
                return k
        except Exception:
            return None
        return None
