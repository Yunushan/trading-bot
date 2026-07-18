from __future__ import annotations

import sys
import unittest
import warnings
from pathlib import Path
from unittest.mock import patch

try:
    import pandas as pd

    PANDAS_AVAILABLE = True
except Exception:
    pd = None
    PANDAS_AVAILABLE = False


PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from app.core.backtest import (  # noqa: E402
    BacktestDataQualityError,
    BacktestEngine,
    BacktestRequest,
    IndicatorDefinition,
    inspect_backtest_frame,
    validate_backtest_frame,
)
from app.core.backtest.models import PairOverride  # noqa: E402
from app.core.backtest.models import BacktestRunResult  # noqa: E402
from app.core.backtest import engine_run_runtime  # noqa: E402
from app.core.backtest.indicator_runtime import (  # noqa: E402
    compute_indicator_series,
    indicators_missing_signal_rules,
)


class _SyntheticBacktestEngine(BacktestEngine):
    def __init__(self, indicator_series: dict[str, list[float]], frame=None) -> None:  # noqa: ANN001
        super().__init__(wrapper=object())
        self._indicator_series = indicator_series
        self._frame = frame

    def _compute_indicator_series(self, df, indicator):  # noqa: ANN001
        values = self._indicator_series[indicator.key]
        return pd.Series(values, index=df.index, dtype=float)

    def _load_klines(self, *_args, **_kwargs):  # noqa: ANN001
        if self._frame is None:
            return super()._load_klines(*_args, **_kwargs)
        return self._frame.copy()


class _BudgetBacktestEngine(_SyntheticBacktestEngine):
    def _simulate(self, symbol, interval, *_args, leverage_override=1, **_kwargs):  # noqa: ANN001
        return BacktestRunResult(
            symbol=symbol,
            interval=interval,
            indicator_keys=["rsi"],
            trades=1,
            roi_value=10.0,
            roi_percent=1.0,
            final_equity=1010.0,
            max_drawdown_value=5.0,
            max_drawdown_percent=0.5,
            logic="AND",
            leverage=float(leverage_override),
        )


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
        # Individual behavioral tests opt into a frictionless model unless the
        # case is specifically validating execution costs.
        "fee_bps": 0.0,
        "slippage_bps": 0.0,
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
    def test_optimizer_budget_returns_completed_partial_results(self):
        df = _build_frame([100.0, 101.0, 102.0, 103.0, 104.0])
        engine = _BudgetBacktestEngine({"rsi": [50.0] * len(df)}, frame=df)
        request = _build_request(
            df,
            [IndicatorDefinition(key="rsi", params={"length": 14})],
            symbols=["BTCUSDT", "ETHUSDT"],
            optimizer_max_duration_seconds=1,
        )
        request.optimizer_result_limit = 1
        request.optimizer_run_count = 2

        with patch.object(engine_run_runtime.time, "monotonic", side_effect=[0.0, 0.0, 2.0]):
            result = engine.run(request)

        self.assertTrue(result["budget_exhausted"])
        self.assertEqual(1, len(result["runs"]))
        self.assertEqual("BTCUSDT", result["runs"][0].symbol)
        self.assertEqual(
            "backtest_optimizer_time_budget_exhausted",
            result["errors"][0]["error"],
        )

    def test_optimizer_resume_offset_skips_completed_combinations(self):
        df = _build_frame([100.0, 101.0, 102.0, 103.0])
        engine = _BudgetBacktestEngine({"rsi": [50.0] * len(df)}, frame=df)
        request = _build_request(
            df,
            [IndicatorDefinition(key="rsi", params={"length": 14})],
            symbols=["BTCUSDT", "ETHUSDT"],
        )

        result = engine.run(request, resume_combo_offset=1)

        self.assertFalse(result["budget_exhausted"])
        self.assertEqual(1, result["resume_combo_offset"])
        self.assertEqual(2, result["completed_combo_count"])
        self.assertEqual(["ETHUSDT"], [run.symbol for run in result["runs"]])

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

    def test_compute_obv_slope_signal_mode(self):
        df = _build_frame([10.0, 11.0, 10.0, 12.0])
        df["volume"] = [100.0, 200.0, 50.0, 300.0]

        series = compute_indicator_series(
            df,
            IndicatorDefinition(
                key="obv",
                params={"signal_mode": "slope", "length": 2},
            ),
        )

        self.assertIsNotNone(series)
        assert series is not None
        self.assertEqual([0.0, 0.0, 150.0, 250.0], [float(value) for value in series.tolist()])

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

    def test_compute_volume_relative_filter_series(self):
        df = _build_frame([10.0, 11.0, 12.0, 13.0])
        df["volume"] = [100.0, 200.0, 300.0, 600.0]

        series = compute_indicator_series(
            df,
            IndicatorDefinition(
                key="volume",
                params={"length": 3, "signal_mode": "relative_to_sma", "signal_role": "filter"},
            ),
        )

        self.assertIsNotNone(series)
        assert series is not None
        self.assertAlmostEqual(1.636363636, float(series.iloc[-1]), places=6)

    def test_compute_atr_percent_filter_series(self):
        df = _build_frame(
            [10.0, 12.0, 13.0, 12.0],
            highs=[11.0, 13.0, 14.0, 13.0],
            lows=[9.0, 11.0, 12.0, 11.0],
        )

        series = compute_indicator_series(
            df,
            IndicatorDefinition(
                key="atr",
                params={"length": 3, "signal_mode": "percent_of_close", "signal_role": "filter"},
            ),
        )

        self.assertIsNotNone(series)
        assert series is not None
        self.assertAlmostEqual(17.901234568, float(series.iloc[-1]), places=6)

    def test_compute_price_cross_signal_mode_uses_close_minus_baseline(self):
        df = _build_frame([10.0, 12.0, 14.0, 11.0])

        series = compute_indicator_series(
            df,
            IndicatorDefinition(
                key="ma",
                params={
                    "length": 2,
                    "signal_mode": "price_cross",
                    "buy_value": 0,
                    "sell_value": 0,
                },
            ),
        )

        self.assertIsNotNone(series)
        assert series is not None
        self.assertEqual([0.0, 1.0, 1.0, -1.5], [float(value) for value in series.tolist()])

    def test_compute_band_position_signal_mode_uses_lower_upper_position(self):
        df = _build_frame([10.0, 11.0, 12.0, 13.0])

        series = compute_indicator_series(
            df,
            IndicatorDefinition(
                key="bb",
                params={
                    "length": 3,
                    "std": 2,
                    "signal_mode": "band_position",
                    "buy_value": 0,
                    "sell_value": 100,
                },
            ),
        )

        self.assertIsNotNone(series)
        assert series is not None
        self.assertAlmostEqual(75.0, float(series.iloc[-1]), places=6)

    def test_missing_signal_rule_helper_flags_enabled_filter_only_indicators(self):
        indicators = [
            IndicatorDefinition(key="volume", params={"signal_role": "filter"}),
            IndicatorDefinition(key="ema", params={"buy_value": 0, "sell_value": 0}),
        ]

        missing = indicators_missing_signal_rules(indicators)

        self.assertEqual(["volume"], [indicator.key for indicator in missing])

    def test_simulate_rejects_indicator_without_signal_rule(self):
        df = _build_frame([100.0, 110.0, 120.0])
        indicators = [IndicatorDefinition(key="synthetic", params={})]
        engine = _SyntheticBacktestEngine({"synthetic": [20.0, 50.0, 80.0]})
        request = _build_request(df, indicators)

        with self.assertRaisesRegex(ValueError, "signal rules are missing"):
            engine._simulate("BTCUSDT", "1h", df, indicators, request)

    def test_simulate_filter_indicator_gates_entries_not_exits(self):
        df = _build_frame([100.0, 110.0, 90.0, 80.0])
        indicators = [
            IndicatorDefinition(key="entry", params={"buy_value": 30, "sell_value": 70}),
            IndicatorDefinition(
                key="volume_filter",
                params={"signal_role": "filter", "filter_operator": "gte", "buy_value": 1},
            ),
        ]
        engine = _SyntheticBacktestEngine(
            {
                "entry": [50.0, 20.0, 80.0, 80.0],
                "volume_filter": [0.0, 1.0, 0.0, 0.0],
            }
        )
        request = _build_request(
            df,
            indicators,
            position_pct=1.0,
            position_pct_units="ratio",
        )

        result = engine._simulate("BTCUSDT", "1h", df, indicators, request)

        self.assertIsNotNone(result)
        assert result is not None
        self.assertEqual(["entry", "volume_filter"], result.indicator_keys)
        self.assertEqual(1, result.trades)
        self.assertAlmostEqual(818.181818182, result.final_equity, places=6)

    def test_simulate_filter_only_indicators_cannot_open_trades(self):
        df = _build_frame([100.0, 110.0, 120.0])
        indicators = [
            IndicatorDefinition(
                key="volume_filter",
                params={"signal_role": "filter", "filter_operator": "gte", "buy_value": 1},
            )
        ]
        engine = _SyntheticBacktestEngine({"volume_filter": [1.0, 1.0, 1.0]})
        request = _build_request(df, indicators)

        with self.assertRaisesRegex(ValueError, "filter-only indicators cannot open trades"):
            engine._simulate("BTCUSDT", "1h", df, indicators, request)

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
        self.assertEqual("BOTH", result.side)
        self.assertEqual("fraction", result.position_pct_units)
        self.assertAlmostEqual(1000.0, result.capital)
        self.assertFalse(result.stop_loss_enabled)

    def test_run_applies_pair_override_strategy_controls(self):
        df = _build_frame([100.0, 105.0, 110.0])
        indicators = [IndicatorDefinition(key="synthetic", params={"buy_value": 30, "sell_value": 70})]
        engine = _SyntheticBacktestEngine({"synthetic": [20.0, 50.0, 80.0]}, frame=df)
        request = _build_request(
            df,
            indicators,
            side="BUY",
            position_pct=100.0,
            position_pct_units="percent",
            capital=1000.0,
            pair_overrides=[
                PairOverride(
                    symbol="BTCUSDT",
                    interval="1h",
                    indicators=["synthetic"],
                    leverage=4,
                    strategy_controls={
                        "side": "SELL",
                        "capital": 500.0,
                        "position_pct": 0.25,
                        "position_pct_units": "fraction",
                        "stop_loss": {
                            "enabled": True,
                            "mode": "percent",
                            "percent": 2.5,
                            "scope": "per_trade",
                        },
                    },
                )
            ],
        )

        result = engine.run(request)

        runs = result["runs"]
        self.assertEqual(1, len(runs))
        run = runs[0]
        self.assertEqual("SELL", run.side)
        self.assertEqual(4.0, run.leverage)
        self.assertAlmostEqual(500.0, run.capital)
        self.assertAlmostEqual(0.25, run.position_pct)
        self.assertEqual("fraction", run.position_pct_units)
        self.assertTrue(run.stop_loss_enabled)
        self.assertEqual("percent", run.stop_loss_mode)
        self.assertAlmostEqual(2.5, run.stop_loss_percent)
        self.assertIsInstance(run.strategy_controls, dict)
        assert run.strategy_controls is not None
        self.assertEqual("SELL", run.strategy_controls["side"])
        self.assertEqual(4, run.strategy_controls["leverage"])

    def test_data_quality_report_accepts_contiguous_ohlcv_frame(self):
        df = _build_frame([100.0, 101.0, 102.0])

        report = inspect_backtest_frame(df, interval="1h")

        self.assertTrue(report.ok, report.issues())
        self.assertEqual(3, report.row_count)
        self.assertEqual(3600.0, report.expected_interval_seconds)

    def test_data_quality_report_rejects_duplicate_timestamps_and_bad_prices(self):
        df = _build_frame([100.0, 101.0, 102.0])
        df.index = [df.index[0], df.index[0], df.index[2]]
        df.loc[df.index[1], "close"] = 0.0

        report = inspect_backtest_frame(df, interval="1h")

        self.assertFalse(report.ok)
        self.assertEqual(1, report.duplicate_index_count)
        self.assertGreater(report.non_positive_price_counts["close"], 0)
        self.assertIn("duplicate timestamp", report.message())
        self.assertIn("close has", report.message())
        with self.assertRaises(BacktestDataQualityError):
            validate_backtest_frame(df, interval="1h")

    def test_data_quality_report_rejects_candle_gaps(self):
        df = _build_frame([100.0, 101.0, 102.0])
        df = df.drop(df.index[1])

        report = inspect_backtest_frame(df, interval="1h")

        self.assertFalse(report.ok)
        self.assertEqual(1, report.gap_count)
        self.assertGreaterEqual(report.max_gap_seconds, 7200.0)

    def test_run_rejects_bad_historical_data_before_simulation(self):
        df = _build_frame([100.0, 101.0, 102.0])
        df = df.drop(columns=["volume"])
        indicators = [IndicatorDefinition(key="synthetic", params={"buy_value": 30, "sell_value": 70})]
        engine = _SyntheticBacktestEngine({"synthetic": [20.0, 50.0, 80.0]}, frame=df)
        request = _build_request(df, indicators)

        result = engine.run(request)

        self.assertEqual([], result["runs"])
        self.assertEqual(1, len(result["errors"]))
        self.assertIn("Backtest data quality failed", result["errors"][0]["error"])
        self.assertIn("missing columns: volume", result["errors"][0]["error"])

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

    def test_simulate_applies_fee_and_slippage_on_entry_and_exit(self):
        df = _build_frame([100.0, 110.0, 120.0])
        indicators = [IndicatorDefinition(key="synthetic", params={"buy_value": 30, "sell_value": 70})]
        engine = _SyntheticBacktestEngine({"synthetic": [20.0, 50.0, 80.0]})

        frictionless = _run_without_pandas4_warning(
            lambda: engine._simulate("BTCUSDT", "1h", df, indicators, _build_request(df, indicators))
        )
        costed = _run_without_pandas4_warning(
            lambda: engine._simulate(
                "BTCUSDT",
                "1h",
                df,
                indicators,
                _build_request(df, indicators, fee_bps=10.0, slippage_bps=10.0),
            )
        )

        self.assertIsNotNone(frictionless)
        self.assertIsNotNone(costed)
        assert frictionless is not None
        assert costed is not None
        self.assertGreater(costed.fees_paid or 0.0, 0.0)
        self.assertEqual(10.0, costed.fee_bps)
        self.assertEqual(10.0, costed.slippage_bps)
        self.assertLess(costed.final_equity, frictionless.final_equity)
