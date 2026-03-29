from __future__ import annotations

from datetime import datetime
from typing import Callable, Dict, Iterable, List, Optional

import pandas as pd

from .engine_data_runtime import load_klines
from .engine_run_runtime import run_backtest
from .engine_signal_runtime import (
    IndicatorCache,
    SignalCache,
    compute_indicator_series,
    estimate_warmup,
    generate_signals,
)
from .engine_simulation_runtime import simulate_backtest
from .models import BacktestRequest, BacktestRunResult, IndicatorDefinition


class BacktestEngine:
    def __init__(self, wrapper):
        self.wrapper = wrapper
        self._should_stop_cb = None

    def run(
        self,
        request: BacktestRequest,
        progress: Optional[Callable[[str], None]] = None,
        should_stop: Optional[Callable[[], bool]] = None,
    ) -> Dict[str, object]:
        return run_backtest(self, request, progress=progress, should_stop=should_stop)

    def _load_klines(
        self,
        symbol: str,
        interval: str,
        start: datetime,
        end: datetime,
        indicators: Iterable[IndicatorDefinition],
    ) -> pd.DataFrame:
        return load_klines(self.wrapper, symbol, interval, start, end, indicators)

    @staticmethod
    def _estimate_warmup(indicator: IndicatorDefinition) -> int:
        return estimate_warmup(indicator)

    def _simulate(
        self,
        symbol: str,
        interval: str,
        df: pd.DataFrame,
        indicators: List[IndicatorDefinition],
        request: BacktestRequest,
        *,
        leverage_override: float | None = None,
        indicator_cache: Optional[IndicatorCache] = None,
        signal_cache: Optional[SignalCache] = None,
        work_df: Optional[pd.DataFrame] = None,
        work_start_idx: int | None = None,
    ) -> Optional[BacktestRunResult]:
        return simulate_backtest(
            self,
            symbol,
            interval,
            df,
            indicators,
            request,
            leverage_override=leverage_override,
            indicator_cache=indicator_cache,
            signal_cache=signal_cache,
            work_df=work_df,
            work_start_idx=work_start_idx,
        )

    @staticmethod
    def _generate_signals(series: pd.Series, buy_value, sell_value) -> tuple[Optional[pd.Series], Optional[pd.Series]]:
        return generate_signals(series, buy_value, sell_value)

    @staticmethod
    def _compute_indicator_series(df: pd.DataFrame, indicator: IndicatorDefinition) -> Optional[pd.Series]:
        return compute_indicator_series(df, indicator)
