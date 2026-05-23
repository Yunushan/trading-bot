from __future__ import annotations

import copy
from typing import Iterable

from ...settings.indicators import INDICATOR_DISPLAY_NAMES, build_backtest_indicator_defaults
from .indicator_runtime import indicators_missing_signal_rules, signal_indicators
from .models import IndicatorDefinition


_FALSE_TEXT_VALUES = {"0", "false", "no", "off", "disabled"}


def _enabled(value: object, default: bool = True) -> bool:
    if value is None:
        return default
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        return bool(value)
    text = str(value).strip().lower()
    if text in _FALSE_TEXT_VALUES:
        return False
    if text:
        return True
    return default


def merge_backtest_indicator_params(key: object, params: object) -> dict[str, object]:
    indicator_key = str(key or "").strip()
    defaults = copy.deepcopy(build_backtest_indicator_defaults().get(indicator_key, {}))
    merged = copy.deepcopy(defaults)
    if isinstance(params, dict):
        merged.update(copy.deepcopy(params))
        incoming_has_empty_rule = params.get("buy_value") is None and params.get("sell_value") is None
        default_has_rule = defaults.get("buy_value") is not None or defaults.get("sell_value") is not None
        if incoming_has_empty_rule and default_has_rule:
            merged["buy_value"] = defaults.get("buy_value")
            merged["sell_value"] = defaults.get("sell_value")
            if defaults.get("signal_mode") is not None and merged.get("signal_mode") is None:
                merged["signal_mode"] = defaults.get("signal_mode")
    return merged


def _from_mapping(payload: dict[object, object]) -> list[IndicatorDefinition]:
    indicators: list[IndicatorDefinition] = []
    for key, params in payload.items():
        if not isinstance(params, dict) or not _enabled(params.get("enabled"), default=False):
            continue
        clean_params = merge_backtest_indicator_params(key, params)
        clean_params.pop("enabled", None)
        indicators.append(IndicatorDefinition(key=str(key), params=clean_params))
    return indicators


def _from_items(payload: Iterable[object]) -> list[IndicatorDefinition]:
    indicators: list[IndicatorDefinition] = []
    for item in payload:
        if not isinstance(item, dict):
            continue
        key = str(item.get("key") or "").strip()
        if not key:
            continue
        params = item.get("params") or {}
        if isinstance(params, dict) and "enabled" in params and not _enabled(params.get("enabled")):
            continue
        clean_params = merge_backtest_indicator_params(key, params)
        clean_params.pop("enabled", None)
        indicators.append(IndicatorDefinition(key=key, params=clean_params))
    return indicators


def build_backtest_indicator_definitions(payload: object) -> list[IndicatorDefinition]:
    if isinstance(payload, dict):
        return _from_mapping(payload)
    if isinstance(payload, (list, tuple)):
        return _from_items(payload)
    return []


def format_missing_signal_rule_message(indicators: list[IndicatorDefinition]) -> str:
    missing = indicators_missing_signal_rules(indicators)
    if not missing:
        return ""
    labels = [
        INDICATOR_DISPLAY_NAMES.get(indicator.key, indicator.key)
        for indicator in missing
    ]
    return (
        "Backtest indicator signal rules are missing: "
        f"{', '.join(labels)}. Add buy/sell values or choose signal-ready defaults."
    )


def format_missing_signal_indicator_message(indicators: list[IndicatorDefinition]) -> str:
    if signal_indicators(indicators):
        return ""
    return "At least one signal indicator is required; filter-only indicators cannot open trades."
