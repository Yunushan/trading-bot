from __future__ import annotations

from typing import Optional

import pandas as pd

from .. import indicators as ind
from .models import IndicatorDefinition


def estimate_warmup(indicator: IndicatorDefinition) -> int:
    params = indicator.params or {}
    length_candidates = []
    for key in (
        "length",
        "fast",
        "slow",
        "signal",
        "smooth_k",
        "smooth_d",
        "short",
        "medium",
        "long",
        "atr_period",
        "atr_length",
        "conversion_length",
        "base_length",
        "span_b_length",
        "displacement",
        "roc1",
        "roc2",
        "roc3",
        "roc4",
        "sma1",
        "sma2",
        "sma3",
        "sma4",
    ):
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
        if key == "bbw":
            length = int(params.get("length") or 20)
            std = float(params.get("std") or 2.0)
            return ind.bollinger_band_width(df, length=length, std=std)
        if key == "keltner":
            length = int(params.get("length") or 20)
            atr_length = int(params.get("atr_length") or 10)
            multiplier = float(params.get("multiplier") or 2.0)
            _upper, mid, _lower = ind.keltner_channels(
                df,
                length=length,
                atr_length=atr_length,
                multiplier=multiplier,
            )
            return mid
        if key == "ichimoku":
            conversion_length = int(params.get("conversion_length") or 9)
            base_length = int(params.get("base_length") or 26)
            span_b_length = int(params.get("span_b_length") or 52)
            displacement = int(params.get("displacement") or 26)
            tenkan, kijun, _span_a, _span_b, _chikou = ind.ichimoku_cloud(
                df,
                conversion_length=conversion_length,
                base_length=base_length,
                span_b_length=span_b_length,
                displacement=displacement,
            )
            return tenkan - kijun
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
        if key == "obv":
            return ind.obv(df)
        if key == "rvol":
            length = int(params.get("length") or 20)
            return ind.relative_volume(df, length=length)
        if key == "cmf":
            length = int(params.get("length") or 20)
            return ind.chaikin_money_flow(df, length=length)
        if key == "cci":
            length = int(params.get("length") or 20)
            constant = float(params.get("constant") or 0.015)
            return ind.cci(df, length=length, constant=constant)
        if key == "roc":
            length = int(params.get("length") or 12)
            return ind.roc(df["close"], length=length)
        if key == "trix":
            length = int(params.get("length") or 15)
            return ind.trix(df["close"], length=length)
        if key == "ppo":
            fast = int(params.get("fast") or 12)
            slow = int(params.get("slow") or 26)
            signal = int(params.get("signal") or 9)
            _ppo, _signal, hist = ind.ppo(df["close"], fast=fast, slow=slow, signal=signal)
            return hist
        if key == "ao":
            fast = int(params.get("fast") or 5)
            slow = int(params.get("slow") or 34)
            return ind.awesome_oscillator(df, fast=fast, slow=slow)
        if key == "kst":
            kst_line, signal_line, spread = ind.kst(
                df["close"],
                roc1=int(params.get("roc1") or 10),
                roc2=int(params.get("roc2") or 15),
                roc3=int(params.get("roc3") or 20),
                roc4=int(params.get("roc4") or 30),
                sma1=int(params.get("sma1") or 10),
                sma2=int(params.get("sma2") or 10),
                sma3=int(params.get("sma3") or 10),
                sma4=int(params.get("sma4") or 15),
                signal=int(params.get("signal") or 9),
            )
            return spread
        if key == "aroon":
            length = int(params.get("length") or 25)
            _up, _down, oscillator = ind.aroon(df, length=length)
            return oscillator
        if key == "chop":
            length = int(params.get("length") or 14)
            return ind.choppiness_index(df, length=length)
        if key == "atr":
            length = int(params.get("length") or 14)
            return ind.atr(df, length=length)
        if key == "natr":
            length = int(params.get("length") or 14)
            return ind.natr(df, length=length)
        if key == "vwap":
            length = int(params.get("length") or 20)
            return ind.vwap(df, length=length)
        if key == "mfi":
            length = int(params.get("length") or 14)
            return ind.mfi(df, length=length)
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
