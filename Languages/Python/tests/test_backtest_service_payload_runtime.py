import sys
import unittest
from datetime import datetime
from pathlib import Path

PYTHON_ROOT = Path(__file__).resolve().parents[1]
if str(PYTHON_ROOT) not in sys.path:
    sys.path.insert(0, str(PYTHON_ROOT))

from app.core.backtest import BacktestRequest, IndicatorDefinition, PairOverride  # noqa: E402
from app.gui.backtest.backtest_service_payload_runtime import (  # noqa: E402
    build_service_backtest_request_payload,
)


class BacktestServicePayloadRuntimeTests(unittest.TestCase):
    def test_build_service_backtest_request_payload_preserves_live_execution_controls(self):
        request = BacktestRequest(
            symbols=["BTCUSDT"],
            intervals=["1h"],
            indicators=[
                IndicatorDefinition(
                    key="RSI",
                    params={
                        "length": 14,
                        "buy_value": 30,
                        "sell_value": 70,
                        "enabled": True,
                        "signal_role": "entry",
                    },
                )
            ],
            logic="AND",
            symbol_source="Futures",
            start=datetime(2025, 1, 1, 0, 0),
            end=datetime(2025, 1, 2, 0, 0),
            capital=1000.0,
            side="BUY",
            position_pct=2.5,
            position_pct_units="percent",
            leverage=5,
            margin_mode="Cross",
            position_mode="Hedge",
            assets_mode="Single-Asset",
            account_mode="Classic Trading",
            mdd_logic="per_trade",
            stop_loss_enabled=True,
            stop_loss_mode="percent",
            stop_loss_usdt=0.0,
            stop_loss_percent=1.5,
            stop_loss_scope="per_trade",
        )

        payload = build_service_backtest_request_payload(
            request,
            api_key="key",
            api_secret="secret",
            mode="Demo/Testnet",
            account_type="Futures",
            connector_backend="binance-sdk-usds-futures",
        )

        self.assertEqual(["BTCUSDT"], payload["symbols"])
        self.assertEqual(["1h"], payload["intervals"])
        self.assertEqual("rsi", payload["indicators"][0]["key"])
        self.assertEqual(14, payload["indicators"][0]["params"]["length"])
        self.assertEqual("2025-01-01T00:00:00", payload["start"])
        self.assertEqual("2025-01-02T00:00:00", payload["end"])
        self.assertEqual("BUY", payload["side"])
        self.assertEqual(2.5, payload["position_pct"])
        self.assertEqual(5.0, payload["leverage"])
        self.assertEqual("Cross", payload["margin_mode"])
        self.assertEqual("Demo/Testnet", payload["mode"])
        self.assertEqual("Futures", payload["account_type"])
        self.assertEqual("binance-sdk-usds-futures", payload["connector_backend"])
        self.assertEqual(
            {
                "enabled": True,
                "mode": "percent",
                "usdt": 0.0,
                "percent": 1.5,
                "scope": "per_trade",
            },
            payload["stop_loss"],
        )

    def test_build_service_backtest_request_payload_preserves_optimizer_overrides(self):
        request = BacktestRequest(
            symbols=["BTCUSDT", "ETHUSDT"],
            intervals=["1h"],
            indicators=[
                IndicatorDefinition(key="rsi", params={"enabled": True, "signal_role": "entry"}),
                IndicatorDefinition(key="ema", params={"enabled": True, "signal_role": "entry"}),
                IndicatorDefinition(key="volume", params={"enabled": True, "signal_role": "filter"}),
            ],
            logic="AND",
            symbol_source="Futures",
            start=datetime(2025, 1, 1, 0, 0),
            end=datetime(2025, 1, 3, 0, 0),
            capital=1000.0,
            pair_overrides=[
                PairOverride(
                    symbol="BTCUSDT",
                    interval="1h",
                    indicators=["RSI", "VOLUME"],
                    leverage=3,
                    strategy_controls={
                        "side": "SELL",
                        "stop_loss": {"enabled": False, "mode": "usdt"},
                    },
                    logic="OR",
                ),
                {
                    "symbol": "ETHUSDT",
                    "interval": "1h",
                    "indicators": ["ema", "volume"],
                    "strategy_controls": {"side": "BUY"},
                    "position_pct": 1.25,
                },
            ],
        )

        payload = build_service_backtest_request_payload(
            request,
            optimizer_mode="pairs",
            optimizer_metric="roi_drawdown",
            optimizer_combo_size=2,
            optimizer_min_trades=3,
            scan_scope="top_n",
            scan_top_n=50,
            scan_mdd_limit=7.5,
        )

        self.assertEqual("pairs", payload["optimizer_mode"])
        self.assertEqual("roi_drawdown", payload["optimizer_metric"])
        self.assertEqual(2, payload["optimizer_combo_size"])
        self.assertEqual(3, payload["optimizer_min_trades"])
        self.assertEqual("top_n", payload["scan_scope"])
        self.assertEqual(50, payload["scan_top_n"])
        self.assertEqual(7.5, payload["scan_mdd_limit"])
        self.assertEqual(2, len(payload["pair_overrides"]))
        first_override = payload["pair_overrides"][0]
        second_override = payload["pair_overrides"][1]
        self.assertEqual(["rsi", "volume"], first_override["indicators"])
        self.assertEqual(3, first_override["leverage"])
        self.assertEqual("OR", first_override["logic"])
        self.assertEqual("SELL", first_override["strategy_controls"]["side"])
        self.assertEqual(["ema", "volume"], second_override["indicators"])
        self.assertEqual(1.25, second_override["position_pct"])

    def test_build_service_backtest_request_payload_can_omit_pair_overrides(self):
        request = BacktestRequest(
            symbols=["BTCUSDT"],
            intervals=["1h"],
            indicators=[IndicatorDefinition(key="rsi", params={"enabled": True})],
            logic="AND",
            symbol_source="Futures",
            start=datetime(2025, 1, 1, 0, 0),
            end=datetime(2025, 1, 2, 0, 0),
            capital=1000.0,
            pair_overrides=[
                PairOverride(symbol="BTCUSDT", interval="1h", indicators=["rsi"])
            ],
        )

        payload = build_service_backtest_request_payload(
            request,
            optimizer_mode="single",
            include_pair_overrides=False,
        )

        self.assertEqual("single", payload["optimizer_mode"])
        self.assertNotIn("pair_overrides", payload)

    def test_build_service_backtest_request_payload_rejects_wrong_request_type(self):
        with self.assertRaises(TypeError):
            build_service_backtest_request_payload({})  # type: ignore[arg-type]


if __name__ == "__main__":
    unittest.main()
