from __future__ import annotations

try:
    from ...indicators import (
        sma,
        ema,
        bollinger_bands,
        bollinger_band_width as bbw_fallback,
        keltner_channels as keltner_channels_fallback,
        ichimoku_cloud as ichimoku_cloud_fallback,
        atr as atr_fallback,
        natr as natr_fallback,
        rsi as rsi_fallback,
        macd as macd_fallback,
        ppo as ppo_fallback,
        mfi as mfi_fallback,
        obv as obv_fallback,
        relative_volume as rvol_fallback,
        chaikin_money_flow as cmf_fallback,
        cci as cci_fallback,
        roc as roc_fallback,
        trix as trix_fallback,
        awesome_oscillator as ao_fallback,
        kst as kst_fallback,
        aroon as aroon_fallback,
        choppiness_index as chop_fallback,
        stoch_rsi as stoch_rsi_fallback,
        williams_r as williams_r_fallback,
        ultimate_oscillator as uo_fallback,
        dmi as dmi_fallback,
        adx as adx_fallback,
        supertrend as supertrend_fallback,
        stochastic as stochastic_fallback,
        vwap as vwap_fallback,
    )
except ImportError:  # pragma: no cover - standalone execution fallback
    from indicators import (
        sma,
        ema,
        bollinger_bands,
        bollinger_band_width as bbw_fallback,
        keltner_channels as keltner_channels_fallback,
        ichimoku_cloud as ichimoku_cloud_fallback,
        atr as atr_fallback,
        natr as natr_fallback,
        rsi as rsi_fallback,
        macd as macd_fallback,
        ppo as ppo_fallback,
        mfi as mfi_fallback,
        obv as obv_fallback,
        relative_volume as rvol_fallback,
        chaikin_money_flow as cmf_fallback,
        cci as cci_fallback,
        roc as roc_fallback,
        trix as trix_fallback,
        awesome_oscillator as ao_fallback,
        kst as kst_fallback,
        aroon as aroon_fallback,
        choppiness_index as chop_fallback,
        stoch_rsi as stoch_rsi_fallback,
        williams_r as williams_r_fallback,
        ultimate_oscillator as uo_fallback,
        dmi as dmi_fallback,
        adx as adx_fallback,
        supertrend as supertrend_fallback,
        stochastic as stochastic_fallback,
        vwap as vwap_fallback,
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

    bbw_cfg = cfg.get("bbw", {})
    if coerce_enabled(bbw_cfg.get("enabled"), False):
        length = int(bbw_cfg.get("length") or 20)
        std = float(bbw_cfg.get("std") or 2.0)
        ind["bbw"] = bbw_fallback(df, length=length, std=std)

    keltner_cfg = cfg.get("keltner", {})
    if coerce_enabled(keltner_cfg.get("enabled"), False):
        length = int(keltner_cfg.get("length") or 20)
        atr_length = int(keltner_cfg.get("atr_length") or 10)
        multiplier = float(keltner_cfg.get("multiplier") or 2.0)
        upper, mid, lower = keltner_channels_fallback(
            df,
            length=length,
            atr_length=atr_length,
            multiplier=multiplier,
        )
        ind["keltner_upper"], ind["keltner_mid"], ind["keltner_lower"] = upper, mid, lower

    ichimoku_cfg = cfg.get("ichimoku", {})
    if coerce_enabled(ichimoku_cfg.get("enabled"), False):
        conversion_length = int(ichimoku_cfg.get("conversion_length") or 9)
        base_length = int(ichimoku_cfg.get("base_length") or 26)
        span_b_length = int(ichimoku_cfg.get("span_b_length") or 52)
        displacement = int(ichimoku_cfg.get("displacement") or 26)
        tenkan, kijun, span_a, span_b, chikou = ichimoku_cloud_fallback(
            df,
            conversion_length=conversion_length,
            base_length=base_length,
            span_b_length=span_b_length,
            displacement=displacement,
        )
        ind["ichimoku_tenkan"] = tenkan
        ind["ichimoku_kijun"] = kijun
        ind["ichimoku_span_a"] = span_a
        ind["ichimoku_span_b"] = span_b
        ind["ichimoku_chikou"] = chikou
        ind["ichimoku"] = tenkan - kijun

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

    if coerce_enabled(cfg.get("atr", {}).get("enabled"), False):
        length = int(cfg["atr"].get("length") or 14)
        ind["atr"] = atr_fallback(df, length=length)

    if coerce_enabled(cfg.get("natr", {}).get("enabled"), False):
        length = int(cfg["natr"].get("length") or 14)
        ind["natr"] = natr_fallback(df, length=length)

    if coerce_enabled(cfg.get("vwap", {}).get("enabled"), False):
        length = int(cfg["vwap"].get("length") or 20)
        ind["vwap"] = vwap_fallback(df, length=length)

    if coerce_enabled(cfg.get("mfi", {}).get("enabled"), False):
        length = int(cfg["mfi"].get("length") or 14)
        ind["mfi"] = mfi_fallback(df, length=length)

    if coerce_enabled(cfg.get("obv", {}).get("enabled"), False):
        ind["obv"] = obv_fallback(df)

    if coerce_enabled(cfg.get("rvol", {}).get("enabled"), False):
        length = int(cfg["rvol"].get("length") or 20)
        ind["rvol"] = rvol_fallback(df, length=length)

    if coerce_enabled(cfg.get("cmf", {}).get("enabled"), False):
        length = int(cfg["cmf"].get("length") or 20)
        ind["cmf"] = cmf_fallback(df, length=length)

    if coerce_enabled(cfg.get("cci", {}).get("enabled"), False):
        length = int(cfg["cci"].get("length") or 20)
        constant = float(cfg["cci"].get("constant") or 0.015)
        ind["cci"] = cci_fallback(df, length=length, constant=constant)

    if coerce_enabled(cfg.get("roc", {}).get("enabled"), False):
        length = int(cfg["roc"].get("length") or 12)
        ind["roc"] = roc_fallback(df["close"], length=length)

    if coerce_enabled(cfg.get("trix", {}).get("enabled"), False):
        length = int(cfg["trix"].get("length") or 15)
        ind["trix"] = trix_fallback(df["close"], length=length)

    if coerce_enabled(cfg.get("ppo", {}).get("enabled"), False):
        ppo_cfg = cfg["ppo"]
        ppo_line, ppo_signal, ppo_hist = ppo_fallback(
            df["close"],
            int(ppo_cfg.get("fast") or 12),
            int(ppo_cfg.get("slow") or 26),
            int(ppo_cfg.get("signal") or 9),
        )
        ind["ppo"] = ppo_line
        ind["ppo_signal"] = ppo_signal
        ind["ppo_hist"] = ppo_hist

    if coerce_enabled(cfg.get("ao", {}).get("enabled"), False):
        fast = int(cfg["ao"].get("fast") or 5)
        slow = int(cfg["ao"].get("slow") or 34)
        ind["ao"] = ao_fallback(df, fast=fast, slow=slow)

    if coerce_enabled(cfg.get("kst", {}).get("enabled"), False):
        kst_cfg = cfg["kst"]
        kst_line, signal_line, spread = kst_fallback(
            df["close"],
            roc1=int(kst_cfg.get("roc1") or 10),
            roc2=int(kst_cfg.get("roc2") or 15),
            roc3=int(kst_cfg.get("roc3") or 20),
            roc4=int(kst_cfg.get("roc4") or 30),
            sma1=int(kst_cfg.get("sma1") or 10),
            sma2=int(kst_cfg.get("sma2") or 10),
            sma3=int(kst_cfg.get("sma3") or 10),
            sma4=int(kst_cfg.get("sma4") or 15),
            signal=int(kst_cfg.get("signal") or 9),
        )
        ind["kst"] = kst_line
        ind["kst_signal"] = signal_line
        ind["kst_hist"] = spread

    if coerce_enabled(cfg.get("aroon", {}).get("enabled"), False):
        length = int(cfg["aroon"].get("length") or 25)
        up_series, down_series, oscillator = aroon_fallback(df, length=length)
        ind["aroon_up"] = up_series
        ind["aroon_down"] = down_series
        ind["aroon"] = oscillator

    if coerce_enabled(cfg.get("chop", {}).get("enabled"), False):
        length = int(cfg["chop"].get("length") or 14)
        ind["chop"] = chop_fallback(df, length=length)

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
