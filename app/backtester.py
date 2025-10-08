from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Callable, Dict, Iterable, List, Optional

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

    def run(self, request: BacktestRequest, progress: Optional[Callable[[str], None]] = None) -> Dict[str, object]:
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

        for symbol in request.symbols:
            symbol = symbol.strip().upper()
            if not symbol:
                continue
            for interval in request.intervals:
                interval = interval.strip()
                if not interval:
                    continue
                try:
                    detail = f" ({source_label})" if source_label else ""
                    progress(f"Fetching {symbol} @ {interval}{detail} data...")
                    df = self._load_klines(symbol, interval, request.start, request.end, active_indicators)
                    if df is None or df.empty:
                        raise RuntimeError("No historical data returned.")
                    if logic == "SEPARATE":
                        for indicator in active_indicators:
                            run = self._simulate(df, [indicator], request.start, logic, request.capital)
                            if run is not None:
                                run.symbol = symbol
                                run.interval = interval
                                runs.append(run)
                    else:
                        run = self._simulate(df, active_indicators, request.start, logic, request.capital)
                        if run is not None:
                            run.symbol = symbol
                            run.interval = interval
                            runs.append(run)
                except Exception as exc:
                    errors.append({"symbol": symbol, "interval": interval, "error": str(exc)})
        return {"runs": runs, "errors": errors}

    def _load_klines(self, symbol: str, interval: str, start: datetime, end: datetime,
                     indicators: Iterable[IndicatorDefinition]) -> pd.DataFrame:
        warmup_bars = max(self._estimate_warmup(indicator) for indicator in indicators) or 100
        warmup_seconds = warmup_bars * _coerce_interval_seconds(interval)
        buffered_start = start - timedelta(seconds=warmup_seconds * 2)
        return self.wrapper.get_klines_range(symbol, interval, buffered_start, end)

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
                  start: datetime, logic: str, capital: float) -> Optional[BacktestRunResult]:
        logic = (logic or "AND").upper()
        work_df = df.loc[df.index >= start].copy()
        if work_df.empty:
            return None

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

        position_open = False
        entry_price = 0.0
        units = 0.0
        equity = float(capital)
        trades = 0

        for idx, price in work_df['close'].items():
            price = float(price or 0.0)
            if price <= 0:
                continue

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

            if not position_open and aggregated_buy:
                position_open = True
                entry_price = price
                units = equity / price
                trades += 1
            elif position_open and aggregated_sell:
                equity = units * price
                position_open = False
                units = 0.0

        if position_open and units > 0.0:
            equity = units * work_df['close'].iloc[-1]
            position_open = False
            units = 0.0

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

        buy_events = None
        sell_events = None
        if buy_value is not None:
            if sell_value is not None and float(buy_value) < float(sell_value):
                buy_condition = series <= float(buy_value)
            else:
                buy_condition = series >= float(buy_value)
        if buy_value is not None:
            buy_condition = buy_condition.fillna(False).astype(bool, copy=False)
            prev_buy = buy_condition.shift(1).fillna(False).astype(bool, copy=False)
            buy_events = buy_condition & (~prev_buy)
        if sell_value is not None:
            if buy_value is not None and float(buy_value) < float(sell_value):
                sell_condition = series >= float(sell_value)
            else:
                sell_condition = series <= float(sell_value)
            sell_condition = sell_condition.fillna(False).astype(bool, copy=False)
            prev_sell = sell_condition.shift(1).fillna(False).astype(bool, copy=False)
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
