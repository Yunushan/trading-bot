from __future__ import annotations

import sys
import unittest
from pathlib import Path
from types import SimpleNamespace


PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from app.config import build_default_config  # noqa: E402
from app.service.runners.backtest_executor_request_runtime import (  # noqa: E402
    MAX_BACKTEST_OPTIMIZER_RUNS,
    build_indicator_definitions,
    build_request,
    rank_optimizer_runs,
    sort_runs,
)


def _build_runtime():
    config = build_default_config()
    config["symbols"] = ["BTCUSDT"]
    config["intervals"] = ["1h"]
    config["capital"] = 1000.0
    config["backtest"]["symbols"] = ["BTCUSDT"]
    config["backtest"]["intervals"] = ["1h"]
    config["backtest"]["capital"] = 1000.0
    return SimpleNamespace(config=config)


class BacktestRequestBehaviorTests(unittest.TestCase):
    def test_build_indicator_definitions_coerces_string_enabled_flags(self):
        indicators = build_indicator_definitions(
            {
                "rsi": {"enabled": "false", "length": 14},
                "ema": {"enabled": "true", "length": 20, "buy_value": None, "sell_value": None},
                "macd": {"enabled": "1", "fast": 12},
                "bb": {"enabled": "0", "length": 20},
            }
        )

        self.assertEqual(["ema", "macd"], [indicator.key for indicator in indicators])
        self.assertEqual(
            {
                "length": 20,
                "buy_value": 0,
                "sell_value": 0,
                "signal_mode": "price_cross",
            },
            indicators[0].params,
        )
        self.assertEqual(
            {
                "fast": 12,
                "slow": 26,
                "signal": 9,
                "buy_value": 0,
                "sell_value": 0,
            },
            indicators[1].params,
        )

    def test_build_request_ignores_false_string_indicator_flags(self):
        runtime = _build_runtime()

        request, _wrapper_kwargs, summary = build_request(
            runtime,
            {
                "symbols": ["BTCUSDT"],
                "intervals": ["1h"],
                "capital": 1000.0,
                "start": "2025-01-01T00:00:00",
                "end": "2025-01-02T00:00:00",
                "indicators": {
                    "rsi": {"enabled": "false", "length": 14, "buy_value": 30, "sell_value": 70},
                    "ema": {"enabled": "true", "length": 20},
                    "stoch_rsi": {"enabled": "0", "length": 14},
                },
                "stop_loss": {"enabled": "false", "mode": "percent", "percent": 5},
            },
        )

        self.assertEqual(["ema"], [indicator.key for indicator in request.indicators])
        self.assertEqual(("ema",), summary["indicator_keys"])
        self.assertFalse(request.stop_loss_enabled)

    def test_build_request_rejects_enabled_indicators_without_signal_rules(self):
        runtime = _build_runtime()

        with self.assertRaisesRegex(ValueError, "signal rules are missing"):
            build_request(
                runtime,
                {
                    "symbols": ["BTCUSDT"],
                    "intervals": ["1h"],
                    "capital": 1000.0,
                    "start": "2025-01-01T00:00:00",
                    "end": "2025-01-02T00:00:00",
                    "indicators": {
                        "obv": {"enabled": True},
                    },
                },
            )

    def test_build_request_rejects_filter_only_indicator_sets(self):
        runtime = _build_runtime()

        with self.assertRaisesRegex(ValueError, "filter-only indicators cannot open trades"):
            build_request(
                runtime,
                {
                    "symbols": ["BTCUSDT"],
                    "intervals": ["1h"],
                    "capital": 1000.0,
                    "start": "2025-01-01T00:00:00",
                    "end": "2025-01-02T00:00:00",
                    "indicators": {
                        "volume": {"enabled": True},
                    },
                },
            )

    def test_build_request_accepts_filters_alongside_signal_indicators(self):
        runtime = _build_runtime()

        request, _wrapper_kwargs, summary = build_request(
            runtime,
            {
                "symbols": ["BTCUSDT"],
                "intervals": ["1h"],
                "capital": 1000.0,
                "start": "2025-01-01T00:00:00",
                "end": "2025-01-02T00:00:00",
                "indicators": {
                    "rsi": {"enabled": True},
                    "volume": {"enabled": True},
                },
            },
        )

        self.assertEqual(["rsi", "volume"], [indicator.key for indicator in request.indicators])
        self.assertEqual(("rsi", "volume"), summary["indicator_keys"])
        volume_params = request.indicators[1].params
        self.assertEqual("filter", volume_params["signal_role"])
        self.assertEqual("relative_to_sma", volume_params["signal_mode"])
        self.assertEqual(1.0, volume_params["buy_value"])

    def test_build_request_defaults_missing_mode_to_demo(self):
        runtime = _build_runtime()
        runtime.config.pop("mode", None)

        _request, wrapper_kwargs, _summary = build_request(
            runtime,
            {
                "symbols": ["BTCUSDT"],
                "intervals": ["1h"],
                "capital": 1000.0,
                "start": "2025-01-01T00:00:00",
                "end": "2025-01-02T00:00:00",
                "indicators": {
                    "ema": {"enabled": True, "length": 20},
                },
            },
        )

        self.assertEqual("Demo/Testnet", wrapper_kwargs["mode"])

    def test_build_request_inherits_runtime_risk_settings_for_live_parity(self):
        runtime = _build_runtime()
        runtime.config["leverage"] = 7
        runtime.config["margin_mode"] = "Cross"
        runtime.config["position_mode"] = "One-Way"
        runtime.config["position_pct"] = 3.5
        runtime.config["stop_loss"] = {
            "enabled": True,
            "mode": "percent",
            "percent": 2.5,
            "scope": "per_trade",
        }
        for key in ("leverage", "margin_mode", "position_mode", "position_pct", "stop_loss"):
            runtime.config["backtest"].pop(key, None)

        request, wrapper_kwargs, summary = build_request(
            runtime,
            {
                "symbols": ["BTCUSDT"],
                "intervals": ["1h"],
                "capital": 1000.0,
                "start": "2025-01-01T00:00:00",
                "end": "2025-01-02T00:00:00",
                "indicators": {
                    "ema": {"enabled": True, "length": 20},
                },
            },
        )

        self.assertEqual(7.0, request.leverage)
        self.assertEqual("Cross", request.margin_mode)
        self.assertEqual("One-Way", request.position_mode)
        self.assertEqual(3.5, request.position_pct)
        self.assertTrue(request.stop_loss_enabled)
        self.assertEqual("percent", request.stop_loss_mode)
        self.assertEqual(2.5, request.stop_loss_percent)
        self.assertEqual("per_trade", request.stop_loss_scope)
        self.assertEqual(7, wrapper_kwargs["default_leverage"])
        self.assertEqual("Cross", wrapper_kwargs["default_margin_mode"])
        self.assertEqual(7.0, summary["live_parity"]["leverage"])
        self.assertTrue(summary["live_parity"]["stop_loss_enabled"])
        self.assertTrue(summary["live_parity"]["exchange_support"]["trading_supported"])

    def test_build_request_canonicalizes_interval_aliases_and_pair_overrides(self):
        runtime = _build_runtime()
        runtime.config["backtest_symbol_interval_pairs"] = [
            {"symbol": "BTCUSDT", "interval": "60m"},
            {"symbol": "BTCUSDT", "interval": "1H"},
            {"symbol": "ETHUSDT", "interval": "2months"},
        ]

        request, _wrapper_kwargs, summary = build_request(
            runtime,
            {
                "symbols": ["BTCUSDT", "ETHUSDT"],
                "intervals": ["60", "1H", "2M"],
                "capital": 1000.0,
                "start": "2025-01-01T00:00:00",
                "end": "2025-01-02T00:00:00",
                "indicators": {
                    "ema": {"enabled": True, "length": 20},
                },
                "pair_overrides": runtime.config["backtest_symbol_interval_pairs"],
            },
        )

        self.assertEqual(["BTCUSDT", "ETHUSDT"], request.symbols)
        self.assertEqual(["1h", "2mo"], request.intervals)
        self.assertEqual([("BTCUSDT", "1h"), ("ETHUSDT", "2mo")], [(item.symbol, item.interval) for item in request.pair_overrides or []])
        self.assertEqual(("1h", "2mo"), summary["intervals"])

    def test_build_request_preserves_pair_override_strategy_controls(self):
        runtime = _build_runtime()
        runtime.config["backtest_symbol_interval_pairs"] = [
            {
                "symbol": "BTCUSDT",
                "interval": "60m",
                "indicators": ["ema"],
                "strategy_controls": {
                    "side": "SELL",
                    "leverage": 4,
                    "position_pct": 0.25,
                    "position_pct_units": "fraction",
                    "stop_loss": {
                        "enabled": True,
                        "mode": "percent",
                        "percent": 2.5,
                        "scope": "per_trade",
                    },
                },
            }
        ]

        request, _wrapper_kwargs, summary = build_request(
            runtime,
            {
                "capital": 1000.0,
                "start": "2025-01-01T00:00:00",
                "end": "2025-01-02T00:00:00",
                "indicators": {
                    "ema": {"enabled": True, "length": 20},
                },
            },
        )

        self.assertEqual(("BTCUSDT",), summary["symbols"])
        self.assertEqual(("1h",), summary["intervals"])
        overrides = request.pair_overrides or []
        self.assertEqual(1, len(overrides))
        override = overrides[0]
        self.assertEqual(["ema"], override.indicators)
        self.assertEqual(4, override.leverage)
        self.assertIsNotNone(override.strategy_controls)
        controls = override.strategy_controls or {}
        self.assertEqual("SELL", controls["side"])
        self.assertEqual(0.25, controls["position_pct"])
        self.assertEqual("fraction", controls["position_pct_units"])
        self.assertTrue(controls["stop_loss"]["enabled"])
        self.assertEqual("percent", controls["stop_loss"]["mode"])

    def test_build_request_keeps_same_pair_with_distinct_indicator_overrides(self):
        runtime = _build_runtime()
        runtime.config["backtest_symbol_interval_pairs"] = [
            {"symbol": "BTCUSDT", "interval": "1h", "indicators": ["ema"]},
            {"symbol": "BTCUSDT", "interval": "60m", "indicators": ["rsi"]},
        ]

        request, _wrapper_kwargs, summary = build_request(
            runtime,
            {
                "capital": 1000.0,
                "start": "2025-01-01T00:00:00",
                "end": "2025-01-02T00:00:00",
                "indicators": {
                    "ema": {"enabled": True, "length": 20},
                    "rsi": {"enabled": True, "length": 14},
                },
            },
        )

        overrides = request.pair_overrides or []
        self.assertEqual(2, len(overrides))
        self.assertEqual([["ema"], ["rsi"]], [override.indicators for override in overrides])
        self.assertEqual(("1h",), summary["intervals"])
        self.assertEqual(2, summary["estimated_run_count"])

    def test_build_request_expands_service_optimizer_pairs_with_filters(self):
        runtime = _build_runtime()

        request, _wrapper_kwargs, summary = build_request(
            runtime,
            {
                "symbols": ["BTCUSDT", "ETHUSDT"],
                "intervals": ["1h"],
                "capital": 1000.0,
                "start": "2025-01-01T00:00:00",
                "end": "2025-01-02T00:00:00",
                "logic": "SEPARATE",
                "optimizer_mode": "pairs",
                "optimizer_metric": "roi-drawdown",
                "optimizer_min_trades": "2",
                "scan_mdd_limit": "5.5",
                "indicators": {
                    "ema": {"enabled": True, "length": 20},
                    "rsi": {"enabled": True, "length": 14},
                    "volume": {"enabled": True},
                },
            },
        )

        overrides = request.pair_overrides or []
        self.assertEqual(2, len(overrides))
        self.assertEqual("AND", request.logic)
        self.assertEqual(["ema", "rsi", "volume"], overrides[0].indicators)
        self.assertEqual(("BTCUSDT", "ETHUSDT"), summary["symbols"])
        self.assertEqual(("1h",), summary["intervals"])
        self.assertTrue(summary["optimizer_enabled"])
        self.assertEqual("pairs", summary["optimizer_mode"])
        self.assertEqual("roi_drawdown", summary["optimizer_metric"])
        self.assertEqual(2, summary["optimizer_min_trades"])
        self.assertEqual(5.5, summary["optimizer_mdd_limit"])
        self.assertEqual(2, summary["estimated_run_count"])
        self.assertEqual(2, summary["optimizer_signal_indicator_count"])
        self.assertEqual(1, summary["optimizer_indicator_group_count"])

    def test_build_request_rejects_service_optimizer_runs_over_limit(self):
        runtime = _build_runtime()
        signal_indicator_keys = [
            "ma",
            "donchian",
            "psar",
            "bb",
            "bbw",
            "keltner",
            "ichimoku",
            "rsi",
            "rvol",
            "cmf",
            "cci",
            "roc",
            "trix",
            "ppo",
            "ao",
            "kst",
            "aroon",
            "chop",
            "natr",
            "vwap",
            "mfi",
            "stoch_rsi",
            "willr",
            "macd",
            "uo",
            "dmi",
            "supertrend",
            "ema",
            "stochastic",
        ]

        with self.assertRaisesRegex(ValueError, str(MAX_BACKTEST_OPTIMIZER_RUNS)):
            build_request(
                runtime,
                {
                    "symbols": [f"SYM{i}USDT" for i in range(35_000)],
                    "intervals": [f"{i + 1}h" for i in range(20)],
                    "capital": 1000.0,
                    "start": "2025-01-01T00:00:00",
                    "end": "2025-01-02T00:00:00",
                    "optimizer_mode": "combinations",
                    "optimizer_combo_size": 5,
                    "indicators": {key: {"enabled": True} for key in signal_indicator_keys},
                },
            )

    def test_rank_optimizer_runs_adds_service_optimizer_metadata(self):
        ranked = rank_optimizer_runs(
            [
                {
                    "symbol": "BTCUSDT",
                    "trades": 1,
                    "roi_percent": 4.0,
                    "roi_value": 40.0,
                    "max_drawdown_percent": 2.0,
                },
                {
                    "symbol": "ETHUSDT",
                    "trades": 2,
                    "roi_percent": 8.0,
                    "roi_value": 80.0,
                    "max_drawdown_percent": 7.0,
                },
            ],
            metric="roi_percent",
            mdd_limit=5.0,
            min_trades=1,
            mode="pairs",
            scope="selected",
            run_count=2,
        )

        self.assertEqual("BTCUSDT", ranked[0]["symbol"])
        self.assertEqual(1, ranked[0]["optimizer_rank"])
        self.assertTrue(ranked[0]["optimizer_eligible"])
        self.assertEqual("pairs", ranked[0]["optimizer_mode"])
        self.assertEqual("selected", ranked[0]["optimizer_scope"])
        self.assertEqual(2, ranked[0]["optimizer_run_count"])
        self.assertEqual(2, ranked[0]["optimizer_candidate_count"])
        self.assertEqual(1, ranked[0]["optimizer_eligible_count"])
        self.assertEqual(1, ranked[0]["optimizer_filtered_count"])
        self.assertFalse(ranked[1]["optimizer_eligible"])
        self.assertIn("MDD 7.00% > 5.00%", ranked[1]["optimizer_rejection_reason"])

    def test_sort_runs_prefers_optimizer_rank_when_available(self):
        ranked = sort_runs(
            [
                {
                    "symbol": "BTCUSDT",
                    "roi_percent": 50.0,
                    "roi_value": 500.0,
                    "max_drawdown_percent": 20.0,
                    "trades": 5,
                },
                {
                    "symbol": "ETHUSDT",
                    "roi_percent": 5.0,
                    "roi_value": 50.0,
                    "max_drawdown_percent": 1.0,
                    "trades": 2,
                    "optimizer_rank": 1,
                },
                {
                    "symbol": "SOLUSDT",
                    "roi_percent": 8.0,
                    "roi_value": 80.0,
                    "max_drawdown_percent": 2.0,
                    "trades": 3,
                    "optimizer_rank": 2,
                },
            ]
        )

        self.assertEqual(["ETHUSDT", "SOLUSDT", "BTCUSDT"], [run["symbol"] for run in ranked])
