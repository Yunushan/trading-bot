import importlib
import runpy
import unittest
from pathlib import Path

import pandas as pd


PYTHON_ROOT = Path(__file__).resolve().parents[1]


class PackageImportCompatibilityTests(unittest.TestCase):
    def test_backtest_package_lazy_exports_resolve_and_unknown_names_fail(self):
        backtest = importlib.reload(importlib.import_module("app.core.backtest"))

        self.assertEqual("BacktestEngine", backtest.BacktestEngine.__name__)
        self.assertTrue(callable(backtest.inspect_backtest_frame))
        self.assertEqual("BacktestDataQualityError", backtest.BacktestDataQualityError.__name__)
        self.assertEqual("BacktestDataQualityReport", backtest.BacktestDataQualityReport.__name__)
        self.assertTrue(callable(backtest.validate_backtest_frame))

        with self.assertRaises(AttributeError):
            getattr(backtest, "not_a_backtest_export")

    def test_config_module_supports_direct_script_import_mode(self):
        namespace = runpy.run_path(str(PYTHON_ROOT / "app" / "config.py"))

        self.assertTrue(callable(namespace["build_default_config"]))
        self.assertIn("AppSettings", namespace["__all__"])

    def test_public_domain_reexports_resolve_to_the_canonical_implementations(self):
        positions = importlib.import_module("app.core.positions")
        strategy = importlib.import_module("app.core.strategy")
        trading_backtest = importlib.import_module("trading_core.backtest")
        trading_indicators = importlib.import_module("trading_core.indicators")
        trading_positions = importlib.import_module("trading_core.positions")
        trading_strategy = importlib.import_module("trading_core.strategy")

        self.assertIs(positions.IntervalPositionGuard, trading_positions.IntervalPositionGuard)
        self.assertIs(strategy.StrategyEngine, trading_strategy.StrategyEngine)
        self.assertIs(trading_backtest.BacktestRequest, importlib.import_module("app.core.backtest").BacktestRequest)
        self.assertTrue(callable(trading_indicators.rsi))

    def test_backtest_data_quality_reports_edge_case_diagnostics(self):
        data_quality = importlib.import_module("app.core.backtest.data_quality")
        report = data_quality.BacktestDataQualityReport(
            row_count=0,
            missing_columns=("close",),
            null_counts={"close": 1},
            negative_volume_count=2,
            non_datetime_index=True,
            non_monotonic_index=True,
        )

        self.assertEqual(
            [
                "no rows",
                "missing columns: close",
                "index must be a DatetimeIndex",
                "timestamps are not monotonic increasing",
                "close has 1 null/non-finite value(s)",
                "volume has 2 negative value(s)",
            ],
            report.issues(),
        )
        self.assertEqual("Backtest data quality check passed.", data_quality.BacktestDataQualityReport(row_count=1).message())
        self.assertEqual((0, 0.0, 60.0), data_quality._gap_summary(pd.DatetimeIndex([pd.Timestamp("2026-01-01")]), "1m"))
        self.assertEqual((0, 0.0, 60.0), data_quality._gap_summary(pd.DatetimeIndex([pd.NaT, pd.NaT]), "1m"))

        invalid_input = data_quality.inspect_backtest_frame(object(), interval="1m")
        self.assertEqual(data_quality.REQUIRED_BACKTEST_COLUMNS, invalid_input.missing_columns)


if __name__ == "__main__":
    unittest.main()
