from __future__ import annotations

import copy
from dataclasses import dataclass, field


def _deep_merge_defaults(
    base: dict[str, object],
    overrides: dict[str, object] | None = None,
) -> dict[str, object]:
    payload = copy.deepcopy(base)
    for key, value in (overrides or {}).items():
        payload[key] = copy.deepcopy(value)
    return payload


@dataclass(frozen=True, slots=True)
class IndicatorDefinition:
    key: str
    display_name: str
    defaults: dict[str, object]
    runtime_overrides: dict[str, object] = field(default_factory=dict)
    backtest_overrides: dict[str, object] = field(default_factory=dict)

    def build_available(self) -> dict[str, object]:
        return _deep_merge_defaults(self.defaults)

    def build_runtime(self) -> dict[str, object]:
        return _deep_merge_defaults(self.defaults, self.runtime_overrides)

    def build_backtest(self) -> dict[str, object]:
        return _deep_merge_defaults(self.build_runtime(), self.backtest_overrides)


INDICATOR_CATALOG = (
    IndicatorDefinition(
        key="ma",
        display_name="Moving Average (MA)",
        defaults={"enabled": False, "length": 20, "type": "SMA", "buy_value": None, "sell_value": None},
        backtest_overrides={"signal_mode": "price_cross", "buy_value": 0, "sell_value": 0},
    ),
    IndicatorDefinition(
        key="donchian",
        display_name="Donchian Channels (DC)",
        defaults={"enabled": False, "length": 20, "buy_value": None, "sell_value": None},
        backtest_overrides={"signal_mode": "band_position", "buy_value": 0, "sell_value": 100},
    ),
    IndicatorDefinition(
        key="psar",
        display_name="Parabolic SAR (PSAR)",
        defaults={"enabled": False, "af": 0.02, "max_af": 0.2, "buy_value": None, "sell_value": None},
        backtest_overrides={"signal_mode": "price_cross", "buy_value": 0, "sell_value": 0},
    ),
    IndicatorDefinition(
        key="bb",
        display_name="Bollinger Bands (BB)",
        defaults={"enabled": False, "length": 20, "std": 2, "buy_value": None, "sell_value": None},
        backtest_overrides={"signal_mode": "band_position", "buy_value": 0, "sell_value": 100},
    ),
    IndicatorDefinition(
        key="bbw",
        display_name="Bollinger Band Width (BBW)",
        defaults={"enabled": False, "length": 20, "std": 2, "buy_value": None, "sell_value": None},
        backtest_overrides={"buy_value": 5.0, "sell_value": 2.0},
    ),
    IndicatorDefinition(
        key="keltner",
        display_name="Keltner Channels (KC)",
        defaults={
            "enabled": False,
            "length": 20,
            "atr_length": 10,
            "multiplier": 2.0,
            "buy_value": None,
            "sell_value": None,
        },
        backtest_overrides={"signal_mode": "band_position", "buy_value": 0, "sell_value": 100},
    ),
    IndicatorDefinition(
        key="ichimoku",
        display_name="Ichimoku Cloud (IC)",
        defaults={
            "enabled": False,
            "conversion_length": 9,
            "base_length": 26,
            "span_b_length": 52,
            "displacement": 26,
            "buy_value": None,
            "sell_value": None,
        },
        backtest_overrides={"buy_value": 0, "sell_value": 0},
    ),
    IndicatorDefinition(
        key="rsi",
        display_name="Relative Strength Index (RSI)",
        defaults={"enabled": False, "length": 14, "buy_value": None, "sell_value": None},
        runtime_overrides={"enabled": True},
        backtest_overrides={"buy_value": 30, "sell_value": 70},
    ),
    IndicatorDefinition(
        key="volume",
        display_name="Volume",
        defaults={"enabled": False, "buy_value": None, "sell_value": None},
        backtest_overrides={
            "signal_role": "filter",
            "signal_mode": "relative_to_sma",
            "length": 20,
            "filter_operator": "gte",
            "buy_value": 1.0,
        },
    ),
    IndicatorDefinition(
        key="obv",
        display_name="On-Balance Volume (OBV)",
        defaults={"enabled": False, "buy_value": None, "sell_value": None},
    ),
    IndicatorDefinition(
        key="rvol",
        display_name="Relative Volume (RVOL)",
        defaults={"enabled": False, "length": 20, "buy_value": None, "sell_value": None},
        backtest_overrides={"buy_value": 1.5, "sell_value": 0.75},
    ),
    IndicatorDefinition(
        key="cmf",
        display_name="Chaikin Money Flow (CMF)",
        defaults={"enabled": False, "length": 20, "buy_value": None, "sell_value": None},
        backtest_overrides={"buy_value": 0.05, "sell_value": -0.05},
    ),
    IndicatorDefinition(
        key="cci",
        display_name="Commodity Channel Index (CCI)",
        defaults={"enabled": False, "length": 20, "constant": 0.015, "buy_value": None, "sell_value": None},
        backtest_overrides={"buy_value": -100, "sell_value": 100},
    ),
    IndicatorDefinition(
        key="roc",
        display_name="Rate of Change (ROC)",
        defaults={"enabled": False, "length": 12, "buy_value": None, "sell_value": None},
        backtest_overrides={"buy_value": 0, "sell_value": 0},
    ),
    IndicatorDefinition(
        key="trix",
        display_name="Triple Exponential Average (TRIX)",
        defaults={"enabled": False, "length": 15, "buy_value": None, "sell_value": None},
        backtest_overrides={"buy_value": 0, "sell_value": 0},
    ),
    IndicatorDefinition(
        key="ppo",
        display_name="Percentage Price Oscillator (PPO)",
        defaults={"enabled": False, "fast": 12, "slow": 26, "signal": 9, "buy_value": None, "sell_value": None},
        backtest_overrides={"buy_value": 0, "sell_value": 0},
    ),
    IndicatorDefinition(
        key="ao",
        display_name="Awesome Oscillator (AO)",
        defaults={"enabled": False, "fast": 5, "slow": 34, "buy_value": None, "sell_value": None},
        backtest_overrides={"buy_value": 0, "sell_value": 0},
    ),
    IndicatorDefinition(
        key="kst",
        display_name="Know Sure Thing (KST)",
        defaults={
            "enabled": False,
            "roc1": 10,
            "roc2": 15,
            "roc3": 20,
            "roc4": 30,
            "sma1": 10,
            "sma2": 10,
            "sma3": 10,
            "sma4": 15,
            "signal": 9,
            "buy_value": None,
            "sell_value": None,
        },
        backtest_overrides={"buy_value": 0, "sell_value": 0},
    ),
    IndicatorDefinition(
        key="aroon",
        display_name="Aroon Oscillator (AROON)",
        defaults={"enabled": False, "length": 25, "buy_value": None, "sell_value": None},
        backtest_overrides={"buy_value": 50, "sell_value": -50},
    ),
    IndicatorDefinition(
        key="chop",
        display_name="Choppiness Index (CHOP)",
        defaults={"enabled": False, "length": 14, "buy_value": None, "sell_value": None},
        backtest_overrides={"buy_value": 38.2, "sell_value": 61.8},
    ),
    IndicatorDefinition(
        key="atr",
        display_name="Average True Range (ATR)",
        defaults={"enabled": False, "length": 14, "buy_value": None, "sell_value": None},
        backtest_overrides={
            "signal_role": "filter",
            "signal_mode": "percent_of_close",
            "filter_operator": "gte",
            "buy_value": 1.0,
        },
    ),
    IndicatorDefinition(
        key="natr",
        display_name="Normalized Average True Range (NATR)",
        defaults={"enabled": False, "length": 14, "buy_value": None, "sell_value": None},
        backtest_overrides={"buy_value": 2.0, "sell_value": 1.0},
    ),
    IndicatorDefinition(
        key="vwap",
        display_name="Volume Weighted Average Price (VWAP)",
        defaults={"enabled": False, "length": 20, "buy_value": None, "sell_value": None},
        backtest_overrides={"signal_mode": "price_cross", "buy_value": 0, "sell_value": 0},
    ),
    IndicatorDefinition(
        key="mfi",
        display_name="Money Flow Index (MFI)",
        defaults={"enabled": False, "length": 14, "buy_value": None, "sell_value": None},
        backtest_overrides={"buy_value": 20, "sell_value": 80},
    ),
    IndicatorDefinition(
        key="stoch_rsi",
        display_name="Stochastic RSI (SRSI)",
        defaults={"enabled": False, "length": 14, "smooth_k": 3, "smooth_d": 3, "buy_value": None, "sell_value": None},
        backtest_overrides={"buy_value": 20, "sell_value": 80},
    ),
    IndicatorDefinition(
        key="willr",
        display_name="Williams %R",
        defaults={"enabled": False, "length": 14, "buy_value": None, "sell_value": None},
        backtest_overrides={"buy_value": -80, "sell_value": -20},
    ),
    IndicatorDefinition(
        key="macd",
        display_name="Moving Average Convergence/Divergence (MACD)",
        defaults={"enabled": False, "fast": 12, "slow": 26, "signal": 9, "buy_value": None, "sell_value": None},
        backtest_overrides={"buy_value": 0, "sell_value": 0},
    ),
    IndicatorDefinition(
        key="uo",
        display_name="Ultimate Oscillator (UO)",
        defaults={"enabled": False, "short": 7, "medium": 14, "long": 28, "buy_value": None, "sell_value": None},
        backtest_overrides={"buy_value": 30, "sell_value": 70},
    ),
    IndicatorDefinition(
        key="adx",
        display_name="Average Directional Index (ADX)",
        defaults={"enabled": False, "length": 14, "buy_value": None, "sell_value": None},
        backtest_overrides={
            "signal_role": "filter",
            "filter_operator": "gte",
            "buy_value": 20,
        },
    ),
    IndicatorDefinition(
        key="dmi",
        display_name="Directional Movement Index (DMI)",
        defaults={"enabled": False, "length": 14, "buy_value": None, "sell_value": None},
        backtest_overrides={"buy_value": 0, "sell_value": 0},
    ),
    IndicatorDefinition(
        key="supertrend",
        display_name="SuperTrend (ST)",
        defaults={"enabled": False, "atr_period": 10, "multiplier": 3.0, "buy_value": None, "sell_value": None},
        backtest_overrides={"signal_mode": "price_cross", "buy_value": 0, "sell_value": 0},
    ),
    IndicatorDefinition(
        key="ema",
        display_name="Exponential Moving Average (EMA)",
        defaults={"enabled": False, "length": 20, "buy_value": None, "sell_value": None},
        backtest_overrides={"signal_mode": "price_cross", "buy_value": 0, "sell_value": 0},
    ),
    IndicatorDefinition(
        key="stochastic",
        display_name="Stochastic Oscillator",
        defaults={"enabled": False, "length": 14, "smooth_k": 3, "smooth_d": 3, "buy_value": None, "sell_value": None},
        backtest_overrides={"buy_value": 20, "sell_value": 80},
    ),
)


def build_available_indicators() -> dict[str, dict[str, object]]:
    return {definition.key: definition.build_available() for definition in INDICATOR_CATALOG}


def build_runtime_indicator_defaults() -> dict[str, dict[str, object]]:
    return {definition.key: definition.build_runtime() for definition in INDICATOR_CATALOG}


def build_backtest_indicator_defaults() -> dict[str, dict[str, object]]:
    return {definition.key: definition.build_backtest() for definition in INDICATOR_CATALOG}


AVAILABLE_INDICATORS = build_available_indicators()
INDICATOR_DISPLAY_NAMES = {definition.key: definition.display_name for definition in INDICATOR_CATALOG}
