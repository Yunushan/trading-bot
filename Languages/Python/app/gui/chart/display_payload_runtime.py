from __future__ import annotations

import pandas as pd

from app.core.indicators import (
    adx as adx_indicator,
    atr as atr_indicator,
    bollinger_band_width as bbw_indicator,
    bollinger_bands as bollinger_bands_indicator,
    dmi as dmi_indicator,
    donchian_high as donchian_high_indicator,
    donchian_low as donchian_low_indicator,
    ema as ema_indicator,
    ichimoku_cloud as ichimoku_cloud_indicator,
    keltner_channels as keltner_channels_indicator,
    macd as macd_indicator,
    mfi as mfi_indicator,
    natr as natr_indicator,
    obv as obv_indicator,
    ppo as ppo_indicator,
    chaikin_money_flow as cmf_indicator,
    cci as cci_indicator,
    choppiness_index as chop_indicator,
    relative_volume as rvol_indicator,
    roc as roc_indicator,
    trix as trix_indicator,
    awesome_oscillator as ao_indicator,
    kst as kst_indicator,
    aroon as aroon_indicator,
    parabolic_sar as psar_indicator,
    rsi as rsi_indicator,
    sma as sma_indicator,
    stochastic as stochastic_indicator,
    stoch_rsi as stoch_rsi_indicator,
    supertrend as supertrend_indicator,
    ultimate_oscillator as uo_indicator,
    vwap as vwap_indicator,
    williams_r as williams_r_indicator,
)
from app.config import INDICATOR_DISPLAY_NAMES


def _build_lightweight_payload(
    self,
    df: pd.DataFrame,
    times: list[int],
    candles: list[dict],
    indicators_cfg: dict,
    theme_name: str,
) -> dict:
    theme_code = "light" if str(theme_name or "").lower().startswith("light") else "dark"

    def _series_from_values(values) -> list[dict]:
        data = []
        for t_val, v_val in zip(times, values):
            try:
                if v_val is None or pd.isna(v_val):
                    continue
                data.append({"time": int(t_val), "value": float(v_val)})
            except Exception:
                continue
        return data

    def _add_overlay(key: str, label: str, data: list[dict], color: str, line_style: int = 0, line_width: int = 2):
        if not data:
            return
        overlays.append(
            {
                "key": key,
                "label": label,
                "type": "line",
                "data": data,
                "color": color,
                "lineStyle": int(line_style),
                "lineWidth": int(line_width),
            }
        )

    def _add_pane(key: str, label: str, series: list[dict], height: int = 80):
        if not series:
            return
        panes.append(
            {
                "key": key,
                "label": label,
                "height": int(height),
                "series": series,
            }
        )

    overlays: list[dict] = []
    panes: list[dict] = []

    volume_series = []
    try:
        opens = df["open"].tolist()
        closes = df["close"].tolist()
        volumes = df["volume"].tolist()
        for t_val, o_val, c_val, v_val in zip(times, opens, closes, volumes):
            if v_val is None or pd.isna(v_val):
                continue
            color = "#0ebb7a" if float(c_val) >= float(o_val) else "#f75467"
            volume_series.append({"time": int(t_val), "value": float(v_val), "color": color})
    except Exception:
        volume_series = []

    indicators_cfg = indicators_cfg or {}
    enabled_map = {
        str(k).strip().lower(): v
        for k, v in (indicators_cfg or {}).items()
        if isinstance(v, dict) and v.get("enabled")
    }

    if enabled_map.get("volume"):
        _add_pane(
            "volume",
            INDICATOR_DISPLAY_NAMES.get("volume", "Volume"),
            [
                {
                    "type": "histogram",
                    "data": volume_series,
                    "color": "#94a3b8",
                    "priceFormat": {"type": "volume"},
                }
            ],
            height=90,
        )

    if enabled_map.get("obv"):
        series = obv_indicator(df)
        _add_pane(
            "obv",
            INDICATOR_DISPLAY_NAMES.get("obv", "OBV"),
            [{"type": "line", "data": _series_from_values(series.tolist()), "color": "#22c55e"}],
        )

    if enabled_map.get("rvol"):
        cfg = enabled_map.get("rvol", {})
        length = int(cfg.get("length") or 20)
        series = rvol_indicator(df, length=length)
        _add_pane(
            "rvol",
            INDICATOR_DISPLAY_NAMES.get("rvol", "RVOL"),
            [{"type": "line", "data": _series_from_values(series.tolist()), "color": "#84cc16"}],
        )

    if enabled_map.get("cmf"):
        cfg = enabled_map.get("cmf", {})
        length = int(cfg.get("length") or 20)
        series = cmf_indicator(df, length=length)
        _add_pane(
            "cmf",
            INDICATOR_DISPLAY_NAMES.get("cmf", "CMF"),
            [{"type": "line", "data": _series_from_values(series.tolist()), "color": "#06b6d4"}],
        )

    if enabled_map.get("cci"):
        cfg = enabled_map.get("cci", {})
        length = int(cfg.get("length") or 20)
        constant = float(cfg.get("constant") or 0.015)
        series = cci_indicator(df, length=length, constant=constant)
        _add_pane(
            "cci",
            INDICATOR_DISPLAY_NAMES.get("cci", "CCI"),
            [{"type": "line", "data": _series_from_values(series.tolist()), "color": "#f97316"}],
        )

    if enabled_map.get("bbw"):
        cfg = enabled_map.get("bbw", {})
        length = int(cfg.get("length") or 20)
        std = float(cfg.get("std") or 2.0)
        series = bbw_indicator(df, length=length, std=std)
        _add_pane(
            "bbw",
            INDICATOR_DISPLAY_NAMES.get("bbw", "BBW"),
            [{"type": "line", "data": _series_from_values(series.tolist()), "color": "#eab308"}],
        )

    if enabled_map.get("roc"):
        cfg = enabled_map.get("roc", {})
        length = int(cfg.get("length") or 12)
        series = roc_indicator(df["close"], length=length)
        _add_pane(
            "roc",
            INDICATOR_DISPLAY_NAMES.get("roc", "ROC"),
            [{"type": "line", "data": _series_from_values(series.tolist()), "color": "#a855f7"}],
        )

    if enabled_map.get("trix"):
        cfg = enabled_map.get("trix", {})
        length = int(cfg.get("length") or 15)
        series = trix_indicator(df["close"], length=length)
        _add_pane(
            "trix",
            INDICATOR_DISPLAY_NAMES.get("trix", "TRIX"),
            [{"type": "line", "data": _series_from_values(series.tolist()), "color": "#38bdf8"}],
        )

    if enabled_map.get("ppo"):
        cfg = enabled_map.get("ppo", {})
        fast = int(cfg.get("fast") or 12)
        slow = int(cfg.get("slow") or 26)
        signal = int(cfg.get("signal") or 9)
        ppo_line, signal_line, hist = ppo_indicator(df["close"], fast=fast, slow=slow, signal=signal)
        _add_pane(
            "ppo",
            INDICATOR_DISPLAY_NAMES.get("ppo", "PPO"),
            [
                {"type": "line", "data": _series_from_values(ppo_line.tolist()), "color": "#22c55e"},
                {"type": "line", "data": _series_from_values(signal_line.tolist()), "color": "#ef4444"},
                {"type": "histogram", "data": _series_from_values(hist.tolist()), "color": "#94a3b8"},
            ],
        )

    if enabled_map.get("ao"):
        cfg = enabled_map.get("ao", {})
        fast = int(cfg.get("fast") or 5)
        slow = int(cfg.get("slow") or 34)
        series = ao_indicator(df, fast=fast, slow=slow)
        _add_pane(
            "ao",
            INDICATOR_DISPLAY_NAMES.get("ao", "AO"),
            [{"type": "histogram", "data": _series_from_values(series.tolist()), "color": "#f59e0b"}],
        )

    if enabled_map.get("kst"):
        cfg = enabled_map.get("kst", {})
        kst_line, signal_line, spread = kst_indicator(
            df["close"],
            roc1=int(cfg.get("roc1") or 10),
            roc2=int(cfg.get("roc2") or 15),
            roc3=int(cfg.get("roc3") or 20),
            roc4=int(cfg.get("roc4") or 30),
            sma1=int(cfg.get("sma1") or 10),
            sma2=int(cfg.get("sma2") or 10),
            sma3=int(cfg.get("sma3") or 10),
            sma4=int(cfg.get("sma4") or 15),
            signal=int(cfg.get("signal") or 9),
        )
        _add_pane(
            "kst",
            INDICATOR_DISPLAY_NAMES.get("kst", "KST"),
            [
                {"type": "line", "data": _series_from_values(kst_line.tolist()), "color": "#22c55e"},
                {"type": "line", "data": _series_from_values(signal_line.tolist()), "color": "#ef4444"},
                {"type": "histogram", "data": _series_from_values(spread.tolist()), "color": "#94a3b8"},
            ],
        )

    if enabled_map.get("aroon"):
        cfg = enabled_map.get("aroon", {})
        length = int(cfg.get("length") or 25)
        up_series, down_series, oscillator = aroon_indicator(df, length=length)
        _add_pane(
            "aroon",
            INDICATOR_DISPLAY_NAMES.get("aroon", "Aroon"),
            [
                {"type": "line", "data": _series_from_values(up_series.tolist()), "color": "#22c55e"},
                {"type": "line", "data": _series_from_values(down_series.tolist()), "color": "#ef4444"},
                {"type": "line", "data": _series_from_values(oscillator.tolist()), "color": "#f59e0b"},
            ],
        )

    if enabled_map.get("chop"):
        cfg = enabled_map.get("chop", {})
        length = int(cfg.get("length") or 14)
        series = chop_indicator(df, length=length)
        _add_pane(
            "chop",
            INDICATOR_DISPLAY_NAMES.get("chop", "CHOP"),
            [{"type": "line", "data": _series_from_values(series.tolist()), "color": "#f43f5e"}],
        )

    if enabled_map.get("ma"):
        cfg = enabled_map.get("ma", {})
        length = int(cfg.get("length") or 20)
        ma_type = str(cfg.get("type") or "SMA").strip().upper()
        if ma_type == "EMA":
            series = ema_indicator(df["close"], length)
            label = f"EMA({length})"
            color = "#38bdf8"
        else:
            series = sma_indicator(df["close"], length)
            label = f"SMA({length})"
            color = "#f59e0b"
        _add_overlay("ma", label, _series_from_values(series.tolist()), color)

    if enabled_map.get("ema"):
        cfg = enabled_map.get("ema", {})
        length = int(cfg.get("length") or 20)
        series = ema_indicator(df["close"], length)
        _add_overlay("ema", f"EMA({length})", _series_from_values(series.tolist()), "#22c55e")

    if enabled_map.get("vwap"):
        cfg = enabled_map.get("vwap", {})
        length = int(cfg.get("length") or 20)
        series = vwap_indicator(df, length=length)
        _add_overlay("vwap", f"VWAP({length})", _series_from_values(series.tolist()), "#14b8a6", line_width=2)

    if enabled_map.get("bb"):
        cfg = enabled_map.get("bb", {})
        length = int(cfg.get("length") or 20)
        std = float(cfg.get("std") or 2)
        upper, mid, lower = bollinger_bands_indicator(df, length=length, std=std)
        _add_overlay("bb_upper", f"BB Upper({length})", _series_from_values(upper.tolist()), "#60a5fa", line_style=2)
        _add_overlay("bb_mid", f"BB Mid({length})", _series_from_values(mid.tolist()), "#fbbf24")
        _add_overlay("bb_lower", f"BB Lower({length})", _series_from_values(lower.tolist()), "#60a5fa", line_style=2)

    if enabled_map.get("keltner"):
        cfg = enabled_map.get("keltner", {})
        length = int(cfg.get("length") or 20)
        atr_length = int(cfg.get("atr_length") or 10)
        multiplier = float(cfg.get("multiplier") or 2.0)
        upper, mid, lower = keltner_channels_indicator(
            df,
            length=length,
            atr_length=atr_length,
            multiplier=multiplier,
        )
        _add_overlay("keltner_upper", f"KC Upper({length})", _series_from_values(upper.tolist()), "#06b6d4", line_style=2)
        _add_overlay("keltner_mid", f"KC Mid({length})", _series_from_values(mid.tolist()), "#f97316")
        _add_overlay("keltner_lower", f"KC Lower({length})", _series_from_values(lower.tolist()), "#06b6d4", line_style=2)

    if enabled_map.get("ichimoku"):
        cfg = enabled_map.get("ichimoku", {})
        conversion_length = int(cfg.get("conversion_length") or 9)
        base_length = int(cfg.get("base_length") or 26)
        span_b_length = int(cfg.get("span_b_length") or 52)
        displacement = int(cfg.get("displacement") or 26)
        tenkan, kijun, span_a, span_b, chikou = ichimoku_cloud_indicator(
            df,
            conversion_length=conversion_length,
            base_length=base_length,
            span_b_length=span_b_length,
            displacement=displacement,
        )
        _add_overlay("ichimoku_tenkan", f"IC Tenkan({conversion_length})", _series_from_values(tenkan.tolist()), "#38bdf8")
        _add_overlay("ichimoku_kijun", f"IC Kijun({base_length})", _series_from_values(kijun.tolist()), "#f97316")
        _add_overlay("ichimoku_span_a", "IC Span A", _series_from_values(span_a.tolist()), "#22c55e", line_style=2)
        _add_overlay("ichimoku_span_b", "IC Span B", _series_from_values(span_b.tolist()), "#ef4444", line_style=2)
        _add_overlay("ichimoku_chikou", "IC Chikou", _series_from_values(chikou.tolist()), "#a855f7", line_style=1)

    if enabled_map.get("donchian"):
        cfg = enabled_map.get("donchian", {})
        length = int(cfg.get("length") or 20)
        high_series = donchian_high_indicator(df, length)
        low_series = donchian_low_indicator(df, length)
        _add_overlay("donchian_high", f"DC High({length})", _series_from_values(high_series.tolist()), "#f59e0b", line_style=2)
        _add_overlay("donchian_low", f"DC Low({length})", _series_from_values(low_series.tolist()), "#22c55e", line_style=2)

    if enabled_map.get("psar"):
        cfg = enabled_map.get("psar", {})
        af = float(cfg.get("af") or 0.02)
        max_af = float(cfg.get("max_af") or 0.2)
        psar_series = psar_indicator(df, af=af, max_af=max_af)
        _add_overlay("psar", "PSAR", _series_from_values(psar_series.tolist()), "#f472b6", line_style=1)

    if enabled_map.get("supertrend"):
        cfg = enabled_map.get("supertrend", {})
        atr_period = int(cfg.get("atr_period") or 10)
        multiplier = float(cfg.get("multiplier") or 3.0)
        st_delta = supertrend_indicator(df, atr_period=atr_period, multiplier=multiplier)
        try:
            st_line = df["close"] - st_delta
        except Exception:
            st_line = st_delta
        _add_overlay("supertrend", "SuperTrend", _series_from_values(st_line.tolist()), "#a855f7", line_style=2)

    if enabled_map.get("rsi"):
        cfg = enabled_map.get("rsi", {})
        length = int(cfg.get("length") or 14)
        series = rsi_indicator(df["close"], length=length)
        _add_pane(
            "rsi",
            INDICATOR_DISPLAY_NAMES.get("rsi", "RSI"),
            [{"type": "line", "data": _series_from_values(series.tolist()), "color": "#f97316"}],
        )

    if enabled_map.get("stoch_rsi"):
        cfg = enabled_map.get("stoch_rsi", {})
        length = int(cfg.get("length") or 14)
        smooth_k = int(cfg.get("smooth_k") or 3)
        smooth_d = int(cfg.get("smooth_d") or 3)
        k_series, d_series = stoch_rsi_indicator(df["close"], length=length, smooth_k=smooth_k, smooth_d=smooth_d)
        _add_pane(
            "stoch_rsi",
            INDICATOR_DISPLAY_NAMES.get("stoch_rsi", "Stoch RSI"),
            [
                {"type": "line", "data": _series_from_values(k_series.tolist()), "color": "#22c55e"},
                {"type": "line", "data": _series_from_values(d_series.tolist()), "color": "#ef4444"},
            ],
        )

    if enabled_map.get("willr"):
        cfg = enabled_map.get("willr", {})
        length = int(cfg.get("length") or 14)
        series = williams_r_indicator(df, length=length)
        _add_pane(
            "willr",
            INDICATOR_DISPLAY_NAMES.get("willr", "Williams %R"),
            [{"type": "line", "data": _series_from_values(series.tolist()), "color": "#60a5fa"}],
        )

    if enabled_map.get("atr"):
        cfg = enabled_map.get("atr", {})
        length = int(cfg.get("length") or 14)
        series = atr_indicator(df, length=length)
        _add_pane(
            "atr",
            INDICATOR_DISPLAY_NAMES.get("atr", "ATR"),
            [{"type": "line", "data": _series_from_values(series.tolist()), "color": "#14b8a6"}],
        )

    if enabled_map.get("natr"):
        cfg = enabled_map.get("natr", {})
        length = int(cfg.get("length") or 14)
        series = natr_indicator(df, length=length)
        _add_pane(
            "natr",
            INDICATOR_DISPLAY_NAMES.get("natr", "NATR"),
            [{"type": "line", "data": _series_from_values(series.tolist()), "color": "#0ea5e9"}],
        )

    if enabled_map.get("mfi"):
        cfg = enabled_map.get("mfi", {})
        length = int(cfg.get("length") or 14)
        series = mfi_indicator(df, length=length)
        _add_pane(
            "mfi",
            INDICATOR_DISPLAY_NAMES.get("mfi", "MFI"),
            [{"type": "line", "data": _series_from_values(series.tolist()), "color": "#06b6d4"}],
        )

    if enabled_map.get("macd"):
        cfg = enabled_map.get("macd", {})
        fast = int(cfg.get("fast") or 12)
        slow = int(cfg.get("slow") or 26)
        signal = int(cfg.get("signal") or 9)
        macd_line, signal_line, hist = macd_indicator(df["close"], fast=fast, slow=slow, signal=signal)
        _add_pane(
            "macd",
            INDICATOR_DISPLAY_NAMES.get("macd", "MACD"),
            [
                {"type": "line", "data": _series_from_values(macd_line.tolist()), "color": "#22c55e"},
                {"type": "line", "data": _series_from_values(signal_line.tolist()), "color": "#ef4444"},
                {"type": "histogram", "data": _series_from_values(hist.tolist()), "color": "#94a3b8"},
            ],
        )

    if enabled_map.get("uo"):
        cfg = enabled_map.get("uo", {})
        short = int(cfg.get("short") or 7)
        medium = int(cfg.get("medium") or 14)
        long = int(cfg.get("long") or 28)
        series = uo_indicator(df, short=short, medium=medium, long=long)
        _add_pane(
            "uo",
            INDICATOR_DISPLAY_NAMES.get("uo", "Ultimate Oscillator"),
            [{"type": "line", "data": _series_from_values(series.tolist()), "color": "#8b5cf6"}],
        )

    if enabled_map.get("adx"):
        cfg = enabled_map.get("adx", {})
        length = int(cfg.get("length") or 14)
        series = adx_indicator(df, length=length)
        _add_pane(
            "adx",
            INDICATOR_DISPLAY_NAMES.get("adx", "ADX"),
            [{"type": "line", "data": _series_from_values(series.tolist()), "color": "#f59e0b"}],
        )

    if enabled_map.get("dmi"):
        cfg = enabled_map.get("dmi", {})
        length = int(cfg.get("length") or 14)
        plus_di, minus_di, adx_series = dmi_indicator(df, length=length)
        _add_pane(
            "dmi",
            INDICATOR_DISPLAY_NAMES.get("dmi", "DMI"),
            [
                {"type": "line", "data": _series_from_values(plus_di.tolist()), "color": "#22c55e"},
                {"type": "line", "data": _series_from_values(minus_di.tolist()), "color": "#ef4444"},
                {"type": "line", "data": _series_from_values(adx_series.tolist()), "color": "#f59e0b"},
            ],
        )

    if enabled_map.get("stochastic"):
        cfg = enabled_map.get("stochastic", {})
        length = int(cfg.get("length") or 14)
        smooth_k = int(cfg.get("smooth_k") or 3)
        smooth_d = int(cfg.get("smooth_d") or 3)
        k_series, d_series = stochastic_indicator(df, length=length, smooth_k=smooth_k, smooth_d=smooth_d)
        _add_pane(
            "stochastic",
            INDICATOR_DISPLAY_NAMES.get("stochastic", "Stochastic"),
            [
                {"type": "line", "data": _series_from_values(k_series.tolist()), "color": "#22c55e"},
                {"type": "line", "data": _series_from_values(d_series.tolist()), "color": "#ef4444"},
            ],
        )

    return {
        "candles": candles,
        "volume": volume_series if enabled_map.get("volume") else [],
        "overlays": overlays,
        "panes": panes,
        "theme": theme_code,
    }
