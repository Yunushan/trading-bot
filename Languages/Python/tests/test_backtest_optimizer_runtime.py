from __future__ import annotations

import sys
import unittest
from pathlib import Path


PYTHON_ROOT = Path(__file__).resolve().parents[1]
if str(PYTHON_ROOT) not in sys.path:
    sys.path.insert(0, str(PYTHON_ROOT))

from app.gui.backtest import backtest_optimizer_runtime  # noqa: E402


class BacktestOptimizerRuntimeTests(unittest.TestCase):
    def test_resolve_scan_symbols_respects_selected_top_n_and_all_loaded_scopes(self):
        loaded = ["btcusdt", "ETHUSDT", "BTCUSDT", ""]
        selected = ["xrpusdt", " XRPUSDT ", "solusdt"]

        self.assertEqual(
            ["XRPUSDT", "SOLUSDT"],
            backtest_optimizer_runtime.resolve_scan_symbols(
                symbols_all=loaded,
                selected_symbols=selected,
                scope="selected",
                top_n=1,
            ),
        )
        self.assertEqual(
            ["BTCUSDT"],
            backtest_optimizer_runtime.resolve_scan_symbols(
                symbols_all=loaded,
                selected_symbols=selected,
                scope="top_n",
                top_n=1,
            ),
        )
        self.assertEqual(
            ["BTCUSDT", "ETHUSDT"],
            backtest_optimizer_runtime.resolve_scan_symbols(
                symbols_all=loaded,
                selected_symbols=selected,
                scope="all-loaded",
                top_n=1,
            ),
        )

    def test_build_indicator_key_groups_matches_optimizer_modes(self):
        indicators = ["rsi", "macd", "ema", "rsi"]

        self.assertEqual(
            [],
            backtest_optimizer_runtime.build_indicator_key_groups(
                indicators,
                mode="current",
                combo_size=3,
            ),
        )
        self.assertEqual(
            [["rsi"], ["macd"], ["ema"]],
            backtest_optimizer_runtime.build_indicator_key_groups(
                indicators,
                mode="single",
                combo_size=3,
            ),
        )
        self.assertEqual(
            [["rsi", "macd"], ["rsi", "ema"], ["macd", "ema"]],
            backtest_optimizer_runtime.build_indicator_key_groups(
                indicators,
                mode="pairs",
                combo_size=3,
            ),
        )
        self.assertEqual(
            [["rsi"], ["macd"], ["ema"], ["rsi", "macd"], ["rsi", "ema"], ["macd", "ema"]],
            backtest_optimizer_runtime.build_indicator_key_groups(
                indicators,
                mode="combinations",
                combo_size=2,
            ),
        )

    def test_build_pair_overrides_expands_symbols_intervals_and_indicator_groups(self):
        overrides = backtest_optimizer_runtime.build_pair_overrides(
            symbols=["BTCUSDT", "ETHUSDT"],
            intervals=["1h", "4h"],
            indicator_groups=[["rsi"], ["rsi", "macd"]],
        )

        self.assertEqual(8, len(overrides))
        self.assertEqual(("BTCUSDT", "1h", ["rsi"]), (overrides[0].symbol, overrides[0].interval, overrides[0].indicators))
        self.assertEqual(("ETHUSDT", "4h", ["rsi", "macd"]), (overrides[-1].symbol, overrides[-1].interval, overrides[-1].indicators))

    def test_estimate_scan_run_count_accounts_for_separate_logic(self):
        self.assertEqual(
            6,
            backtest_optimizer_runtime.estimate_scan_run_count(
                symbols=["BTCUSDT"],
                intervals=["1h", "4h"],
                indicator_count=3,
                indicator_groups=[],
                mode="current",
                logic="SEPARATE",
            ),
        )
        self.assertEqual(
            4,
            backtest_optimizer_runtime.estimate_scan_run_count(
                symbols=["BTCUSDT", "ETHUSDT"],
                intervals=["1h"],
                indicator_count=3,
                indicator_groups=[["rsi"], ["macd"]],
                mode="single",
                logic="AND",
            ),
        )

    def test_optimizer_score_filters_mdd_and_min_trades_and_ranks_metrics(self):
        run = {"trades": 3, "roi_percent": 12.0, "roi_value": 120.0, "max_drawdown_percent": 4.0}

        self.assertIsNone(
            backtest_optimizer_runtime.optimizer_score(
                run,
                metric="roi_percent",
                mdd_limit=3.0,
                min_trades=1,
            )
        )
        self.assertIsNone(
            backtest_optimizer_runtime.optimizer_score(
                run,
                metric="roi_percent",
                mdd_limit=0.0,
                min_trades=4,
            )
        )
        self.assertEqual(
            (120.0, 12.0, 3.0, -4.0),
            backtest_optimizer_runtime.optimizer_score(
                run,
                metric="roi_value",
                mdd_limit=5.0,
                min_trades=1,
            ),
        )
        self.assertEqual(
            (3.0, 12.0, 120.0, 3.0, -4.0),
            backtest_optimizer_runtime.optimizer_score(
                run,
                metric="roi_drawdown",
                mdd_limit=5.0,
                min_trades=1,
            ),
        )


if __name__ == "__main__":
    unittest.main()
