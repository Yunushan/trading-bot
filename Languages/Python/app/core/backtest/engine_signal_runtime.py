from __future__ import annotations

from typing import Callable, Iterable, Optional

import numpy as np
import pandas as pd

from . import indicator_runtime
from .models import IndicatorDefinition

IndicatorCache = dict[tuple[str, str, str, tuple[tuple[str, object], ...]], pd.Series]
SignalCache = dict[
    tuple[str, str, str, tuple[tuple[str, object], ...], int | None, int],
    tuple[Optional[np.ndarray], Optional[np.ndarray]],
]
IndicatorSignal = dict[str, Optional[np.ndarray]]


def estimate_warmup(indicator: IndicatorDefinition) -> int:
    return indicator_runtime.estimate_warmup(indicator)


def generate_signals(
    series: pd.Series,
    buy_value,
    sell_value,
) -> tuple[Optional[pd.Series], Optional[pd.Series]]:
    return indicator_runtime.generate_signals(series, buy_value, sell_value)


def compute_indicator_series(
    df: pd.DataFrame,
    indicator: IndicatorDefinition,
) -> Optional[pd.Series]:
    return indicator_runtime.compute_indicator_series(df, indicator)


def collect_indicator_signals(
    *,
    symbol: str,
    interval: str,
    df: pd.DataFrame,
    indicators: Iterable[IndicatorDefinition],
    work_df: pd.DataFrame,
    work_start_idx: int | None,
    compute_indicator_series_fn: Callable[[pd.DataFrame, IndicatorDefinition], Optional[pd.Series]],
    generate_signals_fn: Callable[[pd.Series, object, object], tuple[Optional[pd.Series], Optional[pd.Series]]],
    indicator_cache: IndicatorCache | None = None,
    signal_cache: SignalCache | None = None,
) -> tuple[list[IndicatorSignal], list[str]]:
    indicator_signals: list[IndicatorSignal] = []
    indicator_keys: list[str] = []
    work_index = work_df.index
    df_len = len(df)

    for indicator in indicators:
        params = indicator.params or {}
        params_key = tuple(
            sorted(
                (key, (value if isinstance(value, (int, float, str, bool, type(None))) else repr(value)))
                for key, value in params.items()
            )
        )
        cache_key = (symbol, interval, indicator.key, params_key)
        signal_key = None
        if signal_cache is not None:
            signal_key = (symbol, interval, indicator.key, params_key, work_start_idx, df_len)
            cached = signal_cache.get(signal_key)
            if cached is not None:
                buy_array, sell_array = cached
                if buy_array is None and sell_array is None:
                    continue
                indicator_signals.append({"buy": buy_array, "sell": sell_array})
                indicator_keys.append(indicator.key)
                continue

        series_full = None
        if indicator_cache is not None:
            series_full = indicator_cache.get(cache_key)
        if series_full is None:
            series_full = compute_indicator_series_fn(df, indicator)
            if series_full is not None:
                series_full = series_full.astype(float, copy=False)
                if indicator_cache is not None:
                    indicator_cache[cache_key] = series_full
        if series_full is None:
            if signal_cache is not None and signal_key is not None:
                signal_cache[signal_key] = (None, None)
            continue

        if work_start_idx is not None:
            if work_start_idx >= len(series_full):
                if signal_cache is not None and signal_key is not None:
                    signal_cache[signal_key] = (None, None)
                continue
            series = series_full.iloc[work_start_idx:]
        else:
            series = series_full.reindex(work_index)
        if series is None:
            if signal_cache is not None and signal_key is not None:
                signal_cache[signal_key] = (None, None)
            continue

        buy_events, sell_events = generate_signals_fn(
            series,
            params.get("buy_value"),
            params.get("sell_value"),
        )
        if buy_events is None and sell_events is None:
            if signal_cache is not None and signal_key is not None:
                signal_cache[signal_key] = (None, None)
            continue

        buy_array = buy_events.to_numpy(dtype=bool, copy=False) if buy_events is not None else None
        sell_array = sell_events.to_numpy(dtype=bool, copy=False) if sell_events is not None else None
        if signal_cache is not None and signal_key is not None:
            signal_cache[signal_key] = (buy_array, sell_array)
        indicator_signals.append({"buy": buy_array, "sell": sell_array})
        indicator_keys.append(indicator.key)

    return indicator_signals, indicator_keys
