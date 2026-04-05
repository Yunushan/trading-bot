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
    build_indicator_definitions,
    build_request,
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
                "ema": {"enabled": "true", "length": 20},
                "macd": {"enabled": "1", "fast": 12},
                "bb": {"enabled": "0", "length": 20},
            }
        )

        self.assertEqual(["ema", "macd"], [indicator.key for indicator in indicators])
        self.assertEqual({"length": 20}, indicators[0].params)
        self.assertEqual({"fast": 12}, indicators[1].params)

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
