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
from app.core.backtest.indicator_runtime import compute_indicator_series  # noqa: E402


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
    def test_compute_atr_indicator_series(self):
        df = _build_frame(
            [10.0, 12.0, 13.0, 12.0],
            highs=[11.0, 13.0, 14.0, 13.0],
            lows=[9.0, 11.0, 12.0, 11.0],
        )

        series = compute_indicator_series(df, IndicatorDefinition(key="atr", params={"length": 3}))

        self.assertIsNotNone(series)
        assert series is not None
        self.assertAlmostEqual(2.148148148, float(series.iloc[-1]), places=6)

    def test_compute_vwap_indicator_series(self):
        df = _build_frame(
            [10.0, 12.0, 13.0, 12.0],
            highs=[11.0, 13.0, 14.0, 13.0],
            lows=[9.0, 11.0, 12.0, 11.0],
        )

        series = compute_indicator_series(df, IndicatorDefinition(key="vwap", params={"length": 3}))

        self.assertIsNotNone(series)
        assert series is not None
        self.assertAlmostEqual(12.333333333, float(series.iloc[-1]), places=6)

    def test_compute_keltner_indicator_series(self):
        df = _build_frame(
            [10.0, 12.0, 13.0, 12.0],
            highs=[11.0, 13.0, 14.0, 13.0],
            lows=[9.0, 11.0, 12.0, 11.0],
        )

        series = compute_indicator_series(
            df,
            IndicatorDefinition(key="keltner", params={"length": 3, "atr_length": 3, "multiplier": 2.0}),
        )

        self.assertIsNotNone(series)
        assert series is not None
        self.assertAlmostEqual(12.0, float(series.iloc[-1]), places=6)

    def test_compute_ichimoku_indicator_series(self):
        df = _build_frame(
            [10.0, 12.0, 13.0, 16.0],
            highs=[11.0, 13.0, 14.0, 17.0],
            lows=[9.0, 11.0, 12.0, 15.0],
        )

        series = compute_indicator_series(
            df,
            IndicatorDefinition(
                key="ichimoku",
                params={
                    "conversion_length": 2,
                    "base_length": 3,
                    "span_b_length": 4,
                    "displacement": 1,
                },
            ),
        )

        self.assertIsNotNone(series)
        assert series is not None
        self.assertAlmostEqual(0.5, float(series.iloc[-1]), places=6)

    def test_compute_mfi_indicator_series(self):
        df = _build_frame(
            [10.0, 11.0, 12.0, 11.0],
            highs=[10.0, 11.0, 12.0, 11.0],
            lows=[10.0, 11.0, 12.0, 11.0],
        )

        series = compute_indicator_series(df, IndicatorDefinition(key="mfi", params={"length": 3}))

        self.assertIsNotNone(series)
        assert series is not None
        self.assertAlmostEqual(67.647058824, float(series.iloc[-1]), places=6)

    def test_compute_obv_indicator_series(self):
        df = _build_frame([10.0, 11.0, 10.0, 12.0])
        df["volume"] = [100.0, 200.0, 50.0, 300.0]

        series = compute_indicator_series(df, IndicatorDefinition(key="obv", params={}))

        self.assertIsNotNone(series)
        assert series is not None
        self.assertEqual([0.0, 200.0, 150.0, 450.0], [float(value) for value in series.tolist()])

    def test_compute_cmf_indicator_series(self):
        df = _build_frame(
            [11.0, 11.5, 8.5, 12.5],
            highs=[12.0, 12.0, 10.0, 13.0],
            lows=[8.0, 10.0, 8.0, 11.0],
        )
        df["volume"] = [100.0, 200.0, 50.0, 300.0]

        series = compute_indicator_series(df, IndicatorDefinition(key="cmf", params={"length": 3}))

        self.assertIsNotNone(series)
        assert series is not None
        self.assertAlmostEqual(0.409090909, float(series.iloc[-1]), places=6)

    def test_compute_rvol_indicator_series(self):
        df = _build_frame([10.0, 11.0, 12.0, 13.0])
        df["volume"] = [100.0, 200.0, 300.0, 600.0]

        series = compute_indicator_series(df, IndicatorDefinition(key="rvol", params={"length": 3}))

        self.assertIsNotNone(series)
        assert series is not None
        self.assertAlmostEqual(1.636363636, float(series.iloc[-1]), places=6)

    def test_compute_cci_indicator_series(self):
        df = _build_frame(
            [10.0, 11.0, 12.0, 13.0],
            highs=[10.0, 11.0, 12.0, 13.0],
            lows=[10.0, 11.0, 12.0, 13.0],
        )

        series = compute_indicator_series(
            df,
            IndicatorDefinition(key="cci", params={"length": 3, "constant": 0.015}),
        )

        self.assertIsNotNone(series)
        assert series is not None
        self.assertAlmostEqual(100.0, float(series.iloc[-1]), places=6)

    def test_compute_bbw_indicator_series(self):
        df = _build_frame([10.0, 11.0, 12.0, 13.0])

        series = compute_indicator_series(
            df,
            IndicatorDefinition(key="bbw", params={"length": 3, "std": 2}),
        )

        self.assertIsNotNone(series)
        assert series is not None
        self.assertAlmostEqual(33.333333333, float(series.iloc[-1]), places=6)

    def test_compute_roc_indicator_series(self):
        df = _build_frame([10.0, 11.0, 12.0, 9.0])

        series = compute_indicator_series(df, IndicatorDefinition(key="roc", params={"length": 2}))

        self.assertIsNotNone(series)
        assert series is not None
        self.assertAlmostEqual(-18.181818182, float(series.iloc[-1]), places=6)

    def test_compute_trix_indicator_series(self):
        df = _build_frame([10.0, 11.0, 12.0, 13.0])

        series = compute_indicator_series(df, IndicatorDefinition(key="trix", params={"length": 2}))

        self.assertIsNotNone(series)
        assert series is not None
        self.assertAlmostEqual(7.256235828, float(series.iloc[-1]), places=6)

    def test_compute_ppo_indicator_series(self):
        df = _build_frame([10.0, 11.0, 12.0, 13.0])

        series = compute_indicator_series(
            df,
            IndicatorDefinition(key="ppo", params={"fast": 2, "slow": 3, "signal": 2}),
        )

        self.assertIsNotNone(series)
        assert series is not None
        self.assertAlmostEqual(0.360693309, float(series.iloc[-1]), places=6)

    def test_compute_ao_indicator_series(self):
        df = _build_frame(
            [10.0, 11.0, 12.0, 13.0],
            highs=[10.0, 11.0, 12.0, 13.0],
            lows=[10.0, 11.0, 12.0, 13.0],
        )

        series = compute_indicator_series(df, IndicatorDefinition(key="ao", params={"fast": 2, "slow": 3}))

        self.assertIsNotNone(series)
        assert series is not None
        self.assertAlmostEqual(0.5, float(series.iloc[-1]), places=6)

    def test_compute_kst_indicator_series(self):
        df = _build_frame([10.0, 11.0, 12.0, 13.0, 14.0])

        series = compute_indicator_series(
            df,
            IndicatorDefinition(
                key="kst",
                params={
                    "roc1": 1,
                    "roc2": 2,
                    "roc3": 3,
                    "roc4": 4,
                    "sma1": 1,
                    "sma2": 1,
                    "sma3": 1,
                    "sma4": 1,
                    "signal": 2,
                },
            ),
        )

        self.assertIsNotNone(series)
        assert series is not None
        self.assertAlmostEqual(74.073426573, float(series.iloc[-1]), places=6)

    def test_compute_aroon_indicator_series(self):
        df = _build_frame(
            [10.0, 11.0, 12.0, 13.0],
            highs=[10.0, 11.0, 12.0, 13.0],
            lows=[10.0, 9.0, 8.0, 9.0],
        )

        series = compute_indicator_series(df, IndicatorDefinition(key="aroon", params={"length": 3}))

        self.assertIsNotNone(series)
        assert series is not None
        self.assertAlmostEqual(50.0, float(series.iloc[-1]), places=6)

    def test_compute_chop_indicator_series(self):
        df = _build_frame([10.0, 11.0, 12.0, 13.0])

        series = compute_indicator_series(df, IndicatorDefinition(key="chop", params={"length": 3}))

        self.assertIsNotNone(series)
        assert series is not None
        self.assertAlmostEqual(36.907024643, float(series.iloc[-1]), places=6)

    def test_compute_natr_indicator_series(self):
        df = _build_frame([10.0, 11.0, 12.0, 13.0])

        series = compute_indicator_series(df, IndicatorDefinition(key="natr", params={"length": 3}))

        self.assertIsNotNone(series)
        assert series is not None
        self.assertAlmostEqual(5.413105413, float(series.iloc[-1]), places=6)

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
