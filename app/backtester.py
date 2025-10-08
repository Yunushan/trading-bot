from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Callable, Dict, Iterable, List, Optional, Tuple

import pandas as pd

from . import indicators as ind
from .binance_wrapper import _coerce_interval_seconds


@dataclass
class IndicatorDefinition:
    key: str
    params: Dict[str, object]


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
    pair_overrides: Optional[List[Tuple[str, str]]] = None


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

        data_cache: dict[tuple[str, str], pd.DataFrame] = {}

        combos: List[tuple[str, str]]
        pair_override = getattr(request, "pair_overrides", None) or []
        if pair_override:
            combos = []
            seen = set()
            for sym, iv in pair_override:
                sym_norm = str(sym).strip().upper()
                iv_norm = str(iv).strip()
                if not sym_norm or not iv_norm:
                    continue
                key = (sym_norm, iv_norm)
                if key in seen:
                    continue
                seen.add(key)
                combos.append(key)
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
                    combos.append((sym_norm, iv_norm))

        try:
            for symbol, interval in combos:
                if should_stop and should_stop():
                    raise RuntimeError("backtest_cancelled")
                try:
                    cache_key = (symbol, interval)
                    df = data_cache.get(cache_key)
                    if df is None:
                        detail = f" ({source_label})" if source_label else ""
                        progress(f"Fetching {symbol} @ {interval}{detail} data...")
                        df = self._load_klines(symbol, interval, request.start, request.end, active_indicators)
                        if df is not None:
                            data_cache[cache_key] = df
                    if df is None or df.empty:
                        raise RuntimeError("No historical data returned.")
                    if logic == "SEPARATE":
                        for indicator in active_indicators:
                            if should_stop and should_stop():
                                raise RuntimeError("backtest_cancelled")
                            run = self._simulate(df, [indicator], request)
                            if run is not None:
                                run.symbol = symbol
                                run.interval = interval
                                runs.append(run)
                    else:
                        run = self._simulate(df, active_indicators, request)
                        if run is not None:
                            run.symbol = symbol
                            run.interval = interval
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
        warmup_seconds = warmup_bars * _coerce_interval_seconds(interval)
        buffered_start = start - timedelta(seconds=warmup_seconds * 2)
        acct = str(getattr(self.wrapper, "account_type", "") or "").upper()
        limit = 1500 if acct.startswith("FUT") else 1000
        return self.wrapper.get_klines_range(symbol, interval, buffered_start, end, limit=limit)

    @staticmethod
    def _estimate_warmup(indicator: IndicatorDefinition) -> int:
        params = indicator.params or {}
        length_candidates = []
        for key in ("length", "fast", "slow", "signal", "smooth_k", "smooth_d"):
            try:
                val = params.get(key)
                if val is not None:
                    length_candidates.append(int(float(val)))
            except Exception:
                continue
        return max(length_candidates or [50])

    def _simulate(self, df: pd.DataFrame, indicators: List[IndicatorDefinition],
                  request: BacktestRequest) -> Optional[BacktestRunResult]:
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
        leverage = max(1.0, float(request.leverage or 1.0))
        margin_mode = (request.margin_mode or "Isolated").strip().upper()
        side_pref = (request.side or "BOTH").strip().upper()

        indicator_signals: List[Dict[str, pd.Series]] = []
        indicator_keys: List[str] = []
        for indicator in indicators:
            series = self._compute_indicator_series(df, indicator)
            if series is None:
                continue
            series = series.reindex(work_df.index).astype(float)
            buy_val = indicator.params.get("buy_value")
            sell_val = indicator.params.get("sell_value")
            buy_events, sell_events = self._generate_signals(series, buy_val, sell_val)
            if buy_events is None and sell_events is None:
                continue
            indicator_signals.append({"buy": buy_events, "sell": sell_events})
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

        for idx, row in work_df.iterrows():
            if should_stop_cb and callable(should_stop_cb) and should_stop_cb():
                raise RuntimeError('backtest_cancelled')
            price = float(row.get('close', 0.0) or 0.0)
            if price <= 0.0:
                continue
            high_price = float(row.get('high', price) or price)
            low_price = float(row.get('low', price) or price)

            buys = [signals["buy"].get(idx, False) if signals["buy"] is not None else False
                    for signals in indicator_signals]
            sells = [signals["sell"].get(idx, False) if signals["sell"] is not None else False
                     for signals in indicator_signals]

            if logic == "AND":
                aggregated_buy = bool(buys) and all(buys)
            elif logic == "OR":
                aggregated_buy = any(buys)
            else:  # SEPARATE handled earlier
                aggregated_buy = any(buys)
            aggregated_sell = any(sells)

            if position_open:
                effective_leverage = leverage
                if margin_mode == "CROSS":
                    effective_leverage = max(1.0, leverage * pct_fraction)
                if direction == "LONG" and effective_leverage > 1.0:
                    liq_price = entry_price * (1.0 - (1.0 / effective_leverage))
                    if liq_price < 0.0:
                        liq_price = 0.0
                    if low_price <= liq_price:
                        loss = min(equity, position_margin)
                        equity = max(0.0, equity - loss)
                        position_open = False
                        units = 0.0
                        position_margin = 0.0
                        direction = ""
                        continue
                if direction == "SHORT" and effective_leverage > 1.0:
                    liq_price = entry_price * (1.0 + (1.0 / effective_leverage))
                    if high_price >= liq_price:
                        loss = min(equity, position_margin)
                        equity = max(0.0, equity - loss)
                        position_open = False
                        units = 0.0
                        position_margin = 0.0
                        direction = ""
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

        return BacktestRunResult(
            symbol="",
            interval="",
            indicator_keys=indicator_keys,
            trades=trades,
            roi_value=float(roi_value),
            roi_percent=float(roi_percent),
            final_equity=float(equity),
            logic=logic,
        )

    @staticmethod
    def _generate_signals(series: pd.Series, buy_value, sell_value) -> tuple[Optional[pd.Series], Optional[pd.Series]]:
        if series is None or series.empty:
            return None, None

        def _to_bool(ser: pd.Series) -> pd.Series:
            ser = ser.fillna(False)
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
        except Exception:
            return None
        return None
