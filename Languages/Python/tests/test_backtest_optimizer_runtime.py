from __future__ import annotations

import sys
import unittest
from pathlib import Path


PYTHON_ROOT = Path(__file__).resolve().parents[1]
if str(PYTHON_ROOT) not in sys.path:
    sys.path.insert(0, str(PYTHON_ROOT))

from app.gui.backtest import backtest_optimizer_runtime  # noqa: E402
from app.core.backtest.optimizer_result_runtime import OptimizerTopResultCollector  # noqa: E402


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

    def test_estimate_scan_plan_reports_counts_and_limit_state(self):
        plan = backtest_optimizer_runtime.estimate_scan_plan(
            symbols_all=["BTCUSDT", "ETHUSDT", "XRPUSDT"],
            selected_symbols=["btcusdt", "ethusdt"],
            intervals=["1h", "4h"],
            indicator_keys=["rsi", "macd", "ema"],
            scope="selected",
            top_n=2,
            mode="pairs",
            combo_size=2,
            logic="AND",
        )

        self.assertEqual(2, plan["symbol_count"])
        self.assertEqual(2, plan["interval_count"])
        self.assertEqual(3, plan["signal_indicator_count"])
        self.assertEqual(3, plan["indicator_group_count"])
        self.assertEqual(12, plan["run_count"])
        self.assertFalse(plan["over_limit"])
        self.assertIn(
            "Estimated optimizer runs: 12",
            backtest_optimizer_runtime.format_scan_plan_estimate(plan),
        )

        over_limit_plan = backtest_optimizer_runtime.estimate_scan_plan(
            symbols_all=[f"SYM{i}USDT" for i in range(40_000)],
            selected_symbols=[],
            intervals=[f"{i}h" for i in range(20)],
            indicator_keys=[f"indicator_{i}" for i in range(100)],
            scope="all_loaded",
            top_n=100,
            mode="combinations",
            combo_size=3,
            logic="AND",
        )

        self.assertGreater(
            int(over_limit_plan["run_count"]),
            backtest_optimizer_runtime.MAX_BACKTEST_OPTIMIZER_RUNS,
        )
        self.assertTrue(over_limit_plan["over_limit"])
        self.assertIn(
            "exceeds research limit",
            backtest_optimizer_runtime.format_scan_plan_estimate(over_limit_plan),
        )

        large_allowed_plan = backtest_optimizer_runtime.estimate_scan_plan(
            symbols_all=[f"SYM{i}USDT" for i in range(200)],
            selected_symbols=[],
            intervals=[f"{i}h" for i in range(20)],
            indicator_keys=[f"indicator_{i}" for i in range(30)],
            scope="top_n",
            top_n=200,
            mode="pairs",
            combo_size=2,
            logic="AND",
        )

        self.assertEqual(1_740_000, large_allowed_plan["run_count"])
        self.assertFalse(large_allowed_plan["over_limit"])
        self.assertTrue(large_allowed_plan["large_warning"])
        self.assertIn(
            "large research batch",
            backtest_optimizer_runtime.format_scan_plan_estimate(large_allowed_plan),
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

    def test_rank_optimizer_runs_sorts_eligible_rows_and_marks_filtered_rows(self):
        runs = [
            {"symbol": "BTCUSDT", "interval": "1h", "trades": 1, "roi_percent": 5.0, "roi_value": 50.0, "max_drawdown_percent": 2.0},
            {"symbol": "ETHUSDT", "interval": "1h", "trades": 3, "roi_percent": 12.0, "roi_value": 120.0, "max_drawdown_percent": 4.0},
            {"symbol": "XRPUSDT", "interval": "1h", "trades": 0, "roi_percent": 20.0, "roi_value": 200.0, "max_drawdown_percent": 1.0},
            {"symbol": "SOLUSDT", "interval": "1h", "trades": 2, "roi_percent": 15.0, "roi_value": 150.0, "max_drawdown_percent": 8.0},
        ]

        ranked = backtest_optimizer_runtime.rank_optimizer_runs(
            runs,
            metric="roi_percent",
            mdd_limit=5.0,
            min_trades=1,
            mode="pairs",
            scope="top_n",
            run_count=4,
        )

        self.assertEqual(["ETHUSDT", "BTCUSDT", "XRPUSDT", "SOLUSDT"], [row["symbol"] for row in ranked])
        self.assertEqual([1, 2, None, None], [row["optimizer_rank"] for row in ranked])
        self.assertEqual([True, True, False, False], [row["optimizer_eligible"] for row in ranked])
        self.assertEqual(12.0, ranked[0]["optimizer_primary_score"])
        self.assertEqual("pairs", ranked[0]["optimizer_mode"])
        self.assertEqual("top_n", ranked[0]["optimizer_scope"])
        self.assertEqual(5.0, ranked[0]["optimizer_mdd_limit"])
        self.assertEqual(1, ranked[0]["optimizer_min_trades"])
        self.assertEqual(4, ranked[0]["optimizer_candidate_count"])
        self.assertEqual(2, ranked[0]["optimizer_eligible_count"])
        self.assertEqual(2, ranked[0]["optimizer_filtered_count"])
        self.assertEqual(4, ranked[0]["optimizer_run_count"])
        self.assertIn("trades 0 < 1", str(ranked[2]["optimizer_rejection_reason"]))
        self.assertIn("MDD 8.00% > 5.00%", str(ranked[3]["optimizer_rejection_reason"]))

    def test_optimizer_top_result_collector_keeps_best_rows_only(self):
        collector = OptimizerTopResultCollector(
            limit=2,
            metric="roi_percent",
            mdd_limit=5.0,
            min_trades=1,
            mode="pairs",
            scope="top_n",
            run_count=4,
        )
        runs = [
            {"symbol": "BTCUSDT", "trades": 1, "roi_percent": 5.0, "roi_value": 50.0, "max_drawdown_percent": 2.0},
            {"symbol": "ETHUSDT", "trades": 2, "roi_percent": 12.0, "roi_value": 120.0, "max_drawdown_percent": 4.0},
            {"symbol": "SOLUSDT", "trades": 2, "roi_percent": 9.0, "roi_value": 90.0, "max_drawdown_percent": 3.0},
            {"symbol": "XRPUSDT", "trades": 0, "roi_percent": 50.0, "roi_value": 500.0, "max_drawdown_percent": 1.0},
        ]
        for run in runs:
            collector.add(run)

        top_rows = collector.finish()

        self.assertEqual(["ETHUSDT", "SOLUSDT"], [row["symbol"] for row in top_rows])
        self.assertEqual([1, 2], [row["optimizer_rank"] for row in top_rows])
        self.assertEqual([4, 4], [row["optimizer_candidate_count"] for row in top_rows])
        self.assertEqual([3, 3], [row["optimizer_eligible_count"] for row in top_rows])
        self.assertEqual([1, 1], [row["optimizer_filtered_count"] for row in top_rows])


if __name__ == "__main__":
    unittest.main()
