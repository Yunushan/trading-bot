from __future__ import annotations

try:
    from ...indicators import (
        sma,
        ema,
        bollinger_bands,
        rsi as rsi_fallback,
        macd as macd_fallback,
        stoch_rsi as stoch_rsi_fallback,
        williams_r as williams_r_fallback,
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
    coerce_enabled = getattr(self, "_strategy_coerce_bool", None)
    if not callable(coerce_enabled):
        def coerce_enabled(value, default=False):
            return bool(default if value is None else value)

    ma_cfg = cfg.get("ma", {})
    if coerce_enabled(ma_cfg.get("enabled"), False):
        if cfg["ma"].get("type", "SMA").upper() == "SMA":
            ind["ma"] = sma(df["close"], int(cfg["ma"]["length"]))
        else:
            ind["ma"] = ema(df["close"], int(cfg["ma"]["length"]))

    ema_cfg = cfg.get("ema", {})
    if coerce_enabled(ema_cfg.get("enabled"), False):
        length = int(ema_cfg.get("length") or 20)
        ind["ema"] = ema(df["close"], length)

    bb_cfg = cfg.get("bb", {})
    if coerce_enabled(bb_cfg.get("enabled"), False):
        upper, mid, lower = bollinger_bands(df, int(cfg["bb"]["length"]), float(cfg["bb"]["std"]))
        ind["bb_upper"], ind["bb_mid"], ind["bb_lower"] = upper, mid, lower

    if coerce_enabled(cfg.get("rsi", {}).get("enabled"), False):
        ind["rsi"] = rsi_fallback(df["close"], length=int(cfg["rsi"]["length"]))

    stoch_rsi_cfg = cfg.get("stoch_rsi", {})
    if coerce_enabled(stoch_rsi_cfg.get("enabled"), False):
        length = int(stoch_rsi_cfg.get("length") or 14)
        smooth_k = int(stoch_rsi_cfg.get("smooth_k") or 3)
        smooth_d = int(stoch_rsi_cfg.get("smooth_d") or 3)
        k_series, d_series = stoch_rsi_fallback(
            df["close"], length=length, smooth_k=smooth_k, smooth_d=smooth_d
        )
        ind["stoch_rsi"] = k_series
        ind["stoch_rsi_k"] = k_series
        ind["stoch_rsi_d"] = d_series

    if coerce_enabled(cfg.get("willr", {}).get("enabled"), False):
        try:
            length = int(cfg["willr"].get("length") or 14)
        except Exception:
            length = 14
        length = max(1, length)
        ind["willr"] = williams_r_fallback(df, length=length)

    if coerce_enabled(cfg.get("macd", {}).get("enabled"), False):
        macdl, macds, _ = macd_fallback(
            df["close"],
            int(cfg["macd"]["fast"]),
            int(cfg["macd"]["slow"]),
            int(cfg["macd"]["signal"]),
        )
        ind["macd_line"], ind["macd_signal"] = macdl, macds

    if coerce_enabled(cfg.get("uo", {}).get("enabled"), False):
        short = int(cfg["uo"].get("short") or 7)
        medium = int(cfg["uo"].get("medium") or 14)
        long = int(cfg["uo"].get("long") or 28)
        ind["uo"] = uo_fallback(df, short=short, medium=medium, long=long)

    if coerce_enabled(cfg.get("adx", {}).get("enabled"), False):
        length = int(cfg["adx"].get("length") or 14)
        ind["adx"] = adx_fallback(df, length=length)

    if coerce_enabled(cfg.get("dmi", {}).get("enabled"), False):
        length = int(cfg["dmi"].get("length") or 14)
        plus_series, minus_series, _ = dmi_fallback(df, length=length)
        ind["dmi_plus"] = plus_series
        ind["dmi_minus"] = minus_series
        ind["dmi"] = plus_series - minus_series

    if coerce_enabled(cfg.get("supertrend", {}).get("enabled"), False):
        atr_period = int(cfg["supertrend"].get("atr_period") or 10)
        multiplier = float(cfg["supertrend"].get("multiplier") or 3.0)
        ind["supertrend"] = supertrend_fallback(df, atr_period=atr_period, multiplier=multiplier)

    if coerce_enabled(cfg.get("stochastic", {}).get("enabled"), False):
        length = int(cfg["stochastic"].get("length") or 14)
        smooth_k = int(cfg["stochastic"].get("smooth_k") or 3)
        smooth_d = int(cfg["stochastic"].get("smooth_d") or 3)
        k_series, d_series = stochastic_fallback(
            df, length=length, smooth_k=smooth_k, smooth_d=smooth_d
        )
        ind["stochastic"] = k_series
        ind["stochastic_k"] = k_series
        ind["stochastic_d"] = d_series

    return ind


def bind_strategy_indicator_compute(strategy_cls) -> None:
    strategy_cls.compute_indicators = compute_indicators
