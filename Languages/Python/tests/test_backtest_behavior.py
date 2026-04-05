from __future__ import annotations

import sys
import unittest
import warnings
from pathlib import Path

try:
    import pandas as pd

    PANDAS_AVAILABLE = True
except Exception:
    pd = None
    PANDAS_AVAILABLE = False


PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from app.core.backtest import BacktestEngine, BacktestRequest, IndicatorDefinition  # noqa: E402


class _SyntheticBacktestEngine(BacktestEngine):
    def __init__(self, indicator_series: dict[str, list[float]]) -> None:
        super().__init__(wrapper=object())
        self._indicator_series = indicator_series

    def _compute_indicator_series(self, df, indicator):  # noqa: ANN001
        values = self._indicator_series[indicator.key]
        return pd.Series(values, index=df.index, dtype=float)


def _build_frame(
    closes: list[float],
    *,
    highs: list[float] | None = None,
    lows: list[float] | None = None,
):
    if pd is None:
        raise RuntimeError("pandas is required for backtest behavior tests")
    index = pd.date_range(start="2025-01-01T00:00:00", periods=len(closes), freq="1h")
    high_values = highs or closes
    low_values = lows or closes
    return pd.DataFrame(
        {
            "open": closes,
            "high": high_values,
            "low": low_values,
            "close": closes,
            "volume": [1000.0] * len(closes),
        },
        index=index,
    )


def _build_request(
    df,
    indicators: list[IndicatorDefinition],
    **overrides,
) -> BacktestRequest:
    payload = {
        "symbols": ["BTCUSDT"],
        "intervals": ["1h"],
        "indicators": indicators,
        "logic": "AND",
        "symbol_source": "Futures",
        "start": df.index[0].to_pydatetime(),
        "end": df.index[-1].to_pydatetime(),
        "capital": 1000.0,
        "position_pct": 1.0,
        "position_pct_units": "ratio",
        "leverage": 1.0,
    }
    payload.update(overrides)
    return BacktestRequest(**payload)


def _run_without_pandas4_warning(callback):
    if pd is None:
        return callback()

    pandas4_warning = getattr(pd.errors, "Pandas4Warning", None)
    if pandas4_warning is None:
        return callback()

    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("always", pandas4_warning)
        result = callback()

    relevant = [warning for warning in caught if isinstance(warning.message, pandas4_warning)]
    if relevant:
        details = ", ".join(str(warning.message) for warning in relevant)
        raise AssertionError(f"unexpected Pandas4Warning emitted: {details}")
    return result


@unittest.skipUnless(PANDAS_AVAILABLE, "pandas is required for backtest behavior tests")
class BacktestBehaviorTests(unittest.TestCase):
    def test_simulate_signal_reversal_closes_and_reopens_on_same_bar(self):
        df = _build_frame([100.0, 110.0, 120.0])
        indicators = [IndicatorDefinition(key="synthetic", params={"buy_value": 30, "sell_value": 70})]
        engine = _SyntheticBacktestEngine({"synthetic": [20.0, 50.0, 80.0]})
        request = _build_request(
            df,
            indicators,
            position_pct=0.5,
            position_pct_units="ratio",
        )

        result = _run_without_pandas4_warning(
            lambda: engine._simulate("BTCUSDT", "1h", df, indicators, request)
        )

        self.assertIsNotNone(result)
        assert result is not None
        self.assertEqual(["synthetic"], result.indicator_keys)
        self.assertEqual(2, result.trades)
        self.assertAlmostEqual(1100.0, result.final_equity)
        self.assertAlmostEqual(100.0, result.roi_value)
        self.assertAlmostEqual(10.0, result.roi_percent)
        self.assertAlmostEqual(0.5, result.position_pct)
        self.assertFalse(result.stop_loss_enabled)

    def test_simulate_stop_loss_exits_on_intrabar_extreme(self):
        df = _build_frame(
            [100.0, 96.0, 96.0],
            highs=[100.0, 97.0, 97.0],
            lows=[100.0, 94.0, 96.0],
        )
        indicators = [IndicatorDefinition(key="synthetic", params={"buy_value": 30, "sell_value": 200})]
        engine = _SyntheticBacktestEngine({"synthetic": [20.0, 20.0, 20.0]})
        request = _build_request(
            df,
            indicators,
            stop_loss_enabled=True,
            stop_loss_mode="usdt",
            stop_loss_usdt=50.0,
            stop_loss_scope="per_trade",
        )

        result = _run_without_pandas4_warning(
            lambda: engine._simulate("BTCUSDT", "1h", df, indicators, request)
        )

        self.assertIsNotNone(result)
        assert result is not None
        self.assertAlmostEqual(940.0, result.final_equity)
        self.assertAlmostEqual(-60.0, result.roi_value)
        self.assertAlmostEqual(-6.0, result.roi_percent)
        self.assertTrue(result.stop_loss_enabled)
        self.assertEqual("usdt", result.stop_loss_mode)
        self.assertEqual("per_trade", result.stop_loss_scope)
        self.assertAlmostEqual(50.0, result.stop_loss_usdt)
        self.assertAlmostEqual(60.0, result.max_drawdown_during_value)
        self.assertAlmostEqual(60.0, result.max_drawdown_result_value)
        self.assertAlmostEqual(6.0, result.max_drawdown_result_percent)
