from __future__ import annotations

from typing import Optional

import pandas as pd

from .. import indicators as ind
from .models import IndicatorDefinition


def estimate_warmup(indicator: IndicatorDefinition) -> int:
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


def generate_signals(series: pd.Series, buy_value, sell_value) -> tuple[Optional[pd.Series], Optional[pd.Series]]:
    if series is None or series.empty:
        return None, None

    def _to_bool(ser: pd.Series) -> pd.Series:
        if not pd.api.types.is_bool_dtype(ser):
            ser = ser.where(ser.notna(), False)
            try:
                ser = ser.infer_objects()
            except AttributeError:
                pass
        return ser.astype(bool)

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


def compute_indicator_series(df: pd.DataFrame, indicator: IndicatorDefinition) -> Optional[pd.Series]:
    key = indicator.key
    params = indicator.params or {}

    try:
        if key == "rsi":
            length = int(params.get("length") or 14)
            return ind.rsi(df["close"], length=length)
        if key == "ma":
            length = int(params.get("length") or 20)
            ma_type = str(params.get("type") or "SMA").upper()
            if ma_type == "EMA":
                return ind.ema(df["close"], length)
            return ind.sma(df["close"], length)
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
            k, _d = ind.stoch_rsi(df["close"], length=length, smooth_k=smooth_k, smooth_d=smooth_d)
            return k
        if key == "willr":
            length = int(params.get("length") or 14)
            return ind.williams_r(df, length=length)
        if key == "macd":
            fast = int(params.get("fast") or 12)
            slow = int(params.get("slow") or 26)
            signal = int(params.get("signal") or 9)
            _macd, _signal, hist = ind.macd(df["close"], fast=fast, slow=slow, signal=signal)
            return hist
        if key == "volume":
            return df["volume"]
        if key == "uo":
            short = int(params.get("short") or 7)
            medium = int(params.get("medium") or 14)
            long = int(params.get("long") or 28)
            return ind.ultimate_oscillator(df, short=short, medium=medium, long=long)
        if key == "ema":
            length = int(params.get("length") or 20)
            return ind.ema(df["close"], length)
        if key == "adx":
            length = int(params.get("length") or 14)
            return ind.adx(df, length=length)
        if key == "dmi":
            length = int(params.get("length") or 14)
            plus_di, minus_di, _ = ind.dmi(df, length=length)
            return plus_di - minus_di
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
