from __future__ import annotations

from datetime import datetime, timedelta
from typing import Iterable

import pandas as pd

from ...integrations.exchanges.binance import _coerce_interval_seconds
from .engine_signal_runtime import estimate_warmup
from .models import IndicatorDefinition


def load_klines(
    wrapper,
    symbol: str,
    interval: str,
    start: datetime,
    end: datetime,
    indicators: Iterable[IndicatorDefinition],
) -> pd.DataFrame:
    warmup_bars = max((estimate_warmup(indicator) for indicator in indicators), default=100) or 100
    try:
        interval_seconds = _coerce_interval_seconds(interval)
    except Exception as exc:
        raise ValueError(f"Invalid backtest interval: {interval}") from exc
    warmup_seconds = warmup_bars * interval_seconds
    buffered_start = start - timedelta(seconds=warmup_seconds * 2)
    acct = str(getattr(wrapper, "account_type", "") or "").upper()
    limit = 1500 if acct.startswith("FUT") else 1000
    return wrapper.get_klines_range(symbol, interval, buffered_start, end, limit=limit)


def slice_work_frame(df: pd.DataFrame, start: datetime) -> tuple[pd.DataFrame, int | None]:
    work_df = None
    work_start_idx = None
    try:
        df_index = df.index
        if getattr(df_index, "is_monotonic_increasing", False):
            work_start_idx = int(df_index.searchsorted(start))
            if work_start_idx < 0:
                work_start_idx = 0
            work_df = df.iloc[work_start_idx:]
    except Exception:
        work_df = None
        work_start_idx = None
    if work_df is None:
        work_df = df.loc[df.index >= start]
    return work_df, work_start_idx
