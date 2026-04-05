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
    ),
    IndicatorDefinition(
        key="donchian",
        display_name="Donchian Channels (DC)",
        defaults={"enabled": False, "length": 20, "buy_value": None, "sell_value": None},
    ),
    IndicatorDefinition(
        key="psar",
        display_name="Parabolic SAR (PSAR)",
        defaults={"enabled": False, "af": 0.02, "max_af": 0.2, "buy_value": None, "sell_value": None},
    ),
    IndicatorDefinition(
        key="bb",
        display_name="Bollinger Bands (BB)",
        defaults={"enabled": False, "length": 20, "std": 2, "buy_value": None, "sell_value": None},
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
    ),
    IndicatorDefinition(
        key="stoch_rsi",
        display_name="Stochastic RSI (SRSI)",
        defaults={"enabled": False, "length": 14, "smooth_k": 3, "smooth_d": 3, "buy_value": None, "sell_value": None},
    ),
    IndicatorDefinition(
        key="willr",
        display_name="Williams %R",
        defaults={"enabled": False, "length": 14, "buy_value": None, "sell_value": None},
    ),
    IndicatorDefinition(
        key="macd",
        display_name="Moving Average Convergence/Divergence (MACD)",
        defaults={"enabled": False, "fast": 12, "slow": 26, "signal": 9, "buy_value": None, "sell_value": None},
    ),
    IndicatorDefinition(
        key="uo",
        display_name="Ultimate Oscillator (UO)",
        defaults={"enabled": False, "short": 7, "medium": 14, "long": 28, "buy_value": None, "sell_value": None},
    ),
    IndicatorDefinition(
        key="adx",
        display_name="Average Directional Index (ADX)",
        defaults={"enabled": False, "length": 14, "buy_value": None, "sell_value": None},
    ),
    IndicatorDefinition(
        key="dmi",
        display_name="Directional Movement Index (DMI)",
        defaults={"enabled": False, "length": 14, "buy_value": None, "sell_value": None},
    ),
    IndicatorDefinition(
        key="supertrend",
        display_name="SuperTrend (ST)",
        defaults={"enabled": False, "atr_period": 10, "multiplier": 3.0, "buy_value": None, "sell_value": None},
    ),
    IndicatorDefinition(
        key="ema",
        display_name="Exponential Moving Average (EMA)",
        defaults={"enabled": False, "length": 20, "buy_value": None, "sell_value": None},
    ),
    IndicatorDefinition(
        key="stochastic",
        display_name="Stochastic Oscillator",
        defaults={"enabled": False, "length": 14, "smooth_k": 3, "smooth_d": 3, "buy_value": None, "sell_value": None},
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
