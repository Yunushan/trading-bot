from __future__ import annotations

try:
    from .indicators import (
        sma,
        ema,
        bollinger_bands,
        rsi as rsi_fallback,
        macd as macd_fallback,
        stoch_rsi as stoch_rsi_fallback,
        williams_r as williams_r_fallback,
        parabolic_sar as psar_fallback,
        ultimate_oscillator as uo_fallback,
        dmi as dmi_fallback,
        adx as adx_fallback,
        supertrend as supertrend_fallback,
        stochastic as stochastic_fallback,
    )
except ImportError:  # pragma: no cover - standalone execution fallback
    from indicators import (
        sma,
        ema,
        bollinger_bands,
        rsi as rsi_fallback,
        macd as macd_fallback,
        stoch_rsi as stoch_rsi_fallback,
        williams_r as williams_r_fallback,
        parabolic_sar as psar_fallback,
        ultimate_oscillator as uo_fallback,
        dmi as dmi_fallback,
        adx as adx_fallback,
        supertrend as supertrend_fallback,
        stochastic as stochastic_fallback,
    )


def compute_indicators(self, df):
    cfg = self.config["indicators"]
    ind = {}
    if df.empty:
        return ind
    try:
        import pandas_ta as ta  # optional
        has_accessor = hasattr(df["close"], "ta")
    except Exception:
        ta = None
        has_accessor = False

    ma_cfg = cfg.get("ma", {})
    if ma_cfg.get("enabled"):
        if has_accessor and cfg["ma"].get("type", "SMA").upper() == "SMA":
            ind["ma"] = df["close"].ta.sma(length=int(cfg["ma"]["length"]))
        elif has_accessor:
            ind["ma"] = df["close"].ta.ema(length=int(cfg["ma"]["length"]))
        else:
            if cfg["ma"].get("type", "SMA").upper() == "SMA":
                ind["ma"] = sma(df["close"], int(cfg["ma"]["length"]))
            else:
                ind["ma"] = ema(df["close"], int(cfg["ma"]["length"]))

    ema_cfg = cfg.get("ema", {})
    if ema_cfg.get("enabled"):
        length = int(ema_cfg.get("length") or 20)
        if has_accessor:
            try:
                ind["ema"] = df["close"].ta.ema(length=length)
            except Exception:
                ind["ema"] = ema(df["close"], length)
        else:
            ind["ema"] = ema(df["close"], length)

    bb_cfg = cfg.get("bb", {})
    if bb_cfg.get("enabled"):
        if has_accessor:
            try:
                bb = df["close"].ta.bbands(length=int(cfg["bb"]["length"]), std=float(cfg["bb"]["std"]))
                ind["bb_upper"] = bb.iloc[:, 0]
                ind["bb_mid"] = bb.iloc[:, 1]
                ind["bb_lower"] = bb.iloc[:, 2]
            except Exception:
                upper, mid, lower = bollinger_bands(df, int(cfg["bb"]["length"]), float(cfg["bb"]["std"]))
                ind["bb_upper"], ind["bb_mid"], ind["bb_lower"] = upper, mid, lower
        else:
            upper, mid, lower = bollinger_bands(df, int(cfg["bb"]["length"]), float(cfg["bb"]["std"]))
            ind["bb_upper"], ind["bb_mid"], ind["bb_lower"] = upper, mid, lower

    if cfg.get("rsi", {}).get("enabled"):
        if has_accessor:
            ind["rsi"] = df["close"].ta.rsi(length=int(cfg["rsi"]["length"]))
        else:
            ind["rsi"] = rsi_fallback(df["close"], length=int(cfg["rsi"]["length"]))

    stoch_rsi_cfg = cfg.get("stoch_rsi", {})
    if stoch_rsi_cfg.get("enabled"):
        length = int(stoch_rsi_cfg.get("length") or 14)
        smooth_k = int(stoch_rsi_cfg.get("smooth_k") or 3)
        smooth_d = int(stoch_rsi_cfg.get("smooth_d") or 3)
        k_series = None
        d_series = None
        if has_accessor:
            try:
                srsi_df = df["close"].ta.stochrsi(length=length, rsi_length=length, k=smooth_k, d=smooth_d)
                cols = list(srsi_df.columns) if srsi_df is not None else []
                if cols:
                    k_series = srsi_df[cols[0]]
                    if len(cols) > 1:
                        d_series = srsi_df[cols[1]]
            except Exception:
                k_series = None
                d_series = None
        if k_series is None or d_series is None:
            k_series, d_series = stoch_rsi_fallback(
                df["close"], length=length, smooth_k=smooth_k, smooth_d=smooth_d
            )
        ind["stoch_rsi"] = k_series
        ind["stoch_rsi_k"] = k_series
        ind["stoch_rsi_d"] = d_series

    if cfg.get("willr", {}).get("enabled"):
        try:
            length = int(cfg["willr"].get("length") or 14)
        except Exception:
            length = 14
        length = max(1, length)
        if has_accessor:
            try:
                ind["willr"] = df.ta.willr(length=length)
            except Exception:
                ind["willr"] = williams_r_fallback(df, length=length)
        else:
            ind["willr"] = williams_r_fallback(df, length=length)

    if cfg.get("macd", {}).get("enabled"):
        if has_accessor:
            macd_df = df["close"].ta.macd(
                fast=int(cfg["macd"]["fast"]),
                slow=int(cfg["macd"]["slow"]),
                signal=int(cfg["macd"]["signal"]),
            )
            ind["macd_line"] = macd_df.iloc[:, 0]
            ind["macd_signal"] = macd_df.iloc[:, 1]
        else:
            macdl, macds, _ = macd_fallback(
                df["close"],
                int(cfg["macd"]["fast"]),
                int(cfg["macd"]["slow"]),
                int(cfg["macd"]["signal"]),
            )
            ind["macd_line"], ind["macd_signal"] = macdl, macds

    if cfg.get("uo", {}).get("enabled"):
        short = int(cfg["uo"].get("short") or 7)
        medium = int(cfg["uo"].get("medium") or 14)
        long = int(cfg["uo"].get("long") or 28)
        ind["uo"] = uo_fallback(df, short=short, medium=medium, long=long)

    if cfg.get("adx", {}).get("enabled"):
        length = int(cfg["adx"].get("length") or 14)
        if has_accessor:
            try:
                adx_df = df.ta.adx(length=length)
                adx_cols = [c for c in adx_df.columns if "ADX" in c.upper()]
                ind["adx"] = adx_df[adx_cols[0]] if adx_cols else adx_fallback(df, length=length)
            except Exception:
                ind["adx"] = adx_fallback(df, length=length)
        else:
            ind["adx"] = adx_fallback(df, length=length)

    if cfg.get("dmi", {}).get("enabled"):
        length = int(cfg["dmi"].get("length") or 14)
        plus_series = minus_series = None
        if has_accessor:
            try:
                dmi_df = df.ta.dmi(length=length)
                cols = list(dmi_df.columns)
                if len(cols) >= 2:
                    plus_series = dmi_df[cols[0]]
                    minus_series = dmi_df[cols[1]]
            except Exception:
                plus_series = minus_series = None
        if plus_series is None or minus_series is None:
            plus_series, minus_series, _ = dmi_fallback(df, length=length)
        ind["dmi_plus"] = plus_series
        ind["dmi_minus"] = minus_series
        ind["dmi"] = plus_series - minus_series

    if cfg.get("supertrend", {}).get("enabled"):
        atr_period = int(cfg["supertrend"].get("atr_period") or 10)
        multiplier = float(cfg["supertrend"].get("multiplier") or 3.0)
        ind["supertrend"] = supertrend_fallback(df, atr_period=atr_period, multiplier=multiplier)

    if cfg.get("stochastic", {}).get("enabled"):
        length = int(cfg["stochastic"].get("length") or 14)
        smooth_k = int(cfg["stochastic"].get("smooth_k") or 3)
        smooth_d = int(cfg["stochastic"].get("smooth_d") or 3)
        k_series = None
        d_series = None
        if has_accessor:
            try:
                stoch_df = df.ta.stoch(k=length, d=smooth_d, smooth_k=smooth_k)
                cols = list(stoch_df.columns)
                if cols:
                    k_series = stoch_df[cols[0]]
                    if len(cols) > 1:
                        d_series = stoch_df[cols[1]]
            except Exception:
                k_series = None
                d_series = None
        if k_series is None or d_series is None:
            k_series, d_series = stochastic_fallback(df, length=length, smooth_k=smooth_k, smooth_d=smooth_d)
        ind["stochastic"] = k_series
        ind["stochastic_k"] = k_series
        ind["stochastic_d"] = d_series

    return ind


def bind_strategy_indicator_compute(strategy_cls) -> None:
    strategy_cls.compute_indicators = compute_indicators
