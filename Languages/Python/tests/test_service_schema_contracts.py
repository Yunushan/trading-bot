from __future__ import annotations

from datetime import datetime
import sys
from typing import cast
import unittest
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from app.core.backtest.models import BacktestRunResult  # noqa: E402
from app.service.schemas.backtest import (  # noqa: E402
    build_backtest_error_record,
    build_backtest_run_record,
    build_backtest_snapshot,
    make_backtest_command_result,
)
from app.service.schemas.config import build_config_summary, build_editable_config  # noqa: E402


class ServiceSchemaContractTests(unittest.TestCase):
    def test_backtest_snapshot_normalizes_nested_runs_and_errors(self):
        started_at = datetime(2025, 1, 1, 12, 0, 0)
        completed_at = datetime(2025, 1, 1, 12, 5, 0)
        run = BacktestRunResult(
            symbol="BTCUSDT",
            interval="1h",
            indicator_keys=["rsi", "ema"],
            trades=3,
            roi_value=125.5,
            roi_percent=12.55,
            final_equity=1125.5,
            max_drawdown_value=40.0,
            max_drawdown_percent=4.0,
            logic="AND",
            leverage=5.0,
            mdd_logic="cumulative",
            start=started_at,
            end=completed_at,
        )

        snapshot = build_backtest_snapshot(
            session_id=" session-1 ",
            state=" completed ",
            workload_kind=" backtest-run ",
            status_message=" finished ",
            symbols=["BTCUSDT", "", "ETHUSDT"],
            intervals=["60m", " ", "1H", "2months"],
            indicator_keys=["rsi", "", "ema"],
            logic="AND",
            symbol_source="Futures",
            capital="1000.5",
            run_count="2",
            error_count="-3",
            cancelled=1,
            started_at=started_at,
            completed_at=completed_at,
            updated_at=completed_at,
            source=" service-executor ",
            top_runs=[run],
            errors=[{"symbol": "ETHUSDT", "interval": "60", "error": "No data"}, {}],
        )

        payload = snapshot.to_dict()

        self.assertEqual("session-1", snapshot.session_id)
        self.assertEqual("completed", snapshot.state)
        self.assertEqual(("BTCUSDT", "ETHUSDT"), snapshot.symbols)
        self.assertEqual(("1h", "2mo"), snapshot.intervals)
        self.assertEqual(("rsi", "ema"), snapshot.indicator_keys)
        self.assertEqual(1000.5, snapshot.capital)
        self.assertEqual(2, snapshot.run_count)
        self.assertEqual(0, snapshot.error_count)
        self.assertTrue(snapshot.cancelled)
        self.assertIsNotNone(snapshot.top_run)
        top_run = snapshot.top_run
        assert top_run is not None
        self.assertEqual("BTCUSDT", top_run.symbol)
        self.assertEqual(["BTCUSDT", "ETHUSDT"], payload["symbols"])
        self.assertEqual("2025-01-01T12:00:00", payload["started_at"])
        payload_top_run = cast(dict[str, object], payload["top_run"])
        payload_errors = cast(list[dict[str, object]], payload["errors"])
        self.assertEqual("BTCUSDT", payload_top_run["symbol"])
        self.assertEqual("1h", payload_errors[0]["interval"])
        self.assertEqual("Unknown backtest error.", payload_errors[1]["error"])

    def test_backtest_run_and_command_records_coerce_public_payloads(self):
        run = build_backtest_run_record(
            type(
                "RunRecord",
                (),
                {
                    "symbol": " BTCUSDT ",
                    "interval": " 60 ",
                    "indicator_keys": ["rsi", "", "ema"],
                    "trades": "4",
                    "roi_value": "10.5",
                    "roi_percent": "1.05",
                    "final_equity": "1010.5",
                    "max_drawdown_value": "15",
                    "max_drawdown_percent": "1.5",
                    "leverage": "3",
                    "logic": "AND",
                    "mdd_logic": "per_trade",
                    "start": datetime(2025, 1, 1, 0, 0, 0),
                    "end": datetime(2025, 1, 1, 1, 0, 0),
                },
            )()
        )
        command = make_backtest_command_result(
            accepted=1,
            action=" run ",
            session_id=" abc123 ",
            state=" running ",
            status_message=" queued ",
            source=" api ",
        )
        error = build_backtest_error_record({})

        self.assertEqual("BTCUSDT", run.symbol)
        self.assertEqual("1h", run.interval)
        self.assertEqual(("rsi", "ema"), run.indicator_keys)
        self.assertEqual(4, run.trades)
        self.assertEqual("2025-01-01T00:00:00", run.start)
        self.assertEqual("run", command.action)
        self.assertEqual("abc123", command.session_id)
        self.assertEqual("running", command.state)
        self.assertEqual("Unknown backtest error.", error.error)

    def test_config_schema_builders_count_enabled_indicators_and_mask_secrets(self):
        config = {
            "mode": "Demo/Testnet",
            "account_type": "Futures",
            "margin_mode": "Cross",
            "position_mode": "Hedge",
            "side": "BOTH",
            "leverage": "10",
            "position_pct": "5.5",
            "connector_backend": "binance-sdk-spot",
            "selected_exchange": "Binance",
            "code_language": "Python",
            "theme": "Light",
            "symbols": ["BTCUSDT", "ETHUSDT"],
            "intervals": ["60m", "1H", ""],
            "api_key": "key",
            "api_secret": "",
            "indicators": {
                "rsi": {"enabled": True},
                "ema": {"enabled": "false"},
                "macd": {"enabled": 1},
                "bb": {"enabled": "0"},
            },
            "runtime_symbol_interval_pairs": [{"symbol": "BTCUSDT", "interval": "1m"}],
            "backtest_symbol_interval_pairs": [
                {"symbol": "BTCUSDT", "interval": "1m"},
                {"symbol": "ETHUSDT", "interval": "5m"},
            ],
        }

        editable = build_editable_config(config).to_dict()
        summary = build_config_summary(config).to_dict()

        self.assertEqual(["BTCUSDT", "ETHUSDT"], editable["symbols"])
        self.assertEqual(["1h"], editable["intervals"])
        self.assertFalse(editable["api_credentials_present"])
        self.assertEqual(2, summary["symbol_count"])
        self.assertEqual(1, summary["interval_count"])
        self.assertEqual(2, summary["enabled_indicator_count"])
        self.assertEqual(1, summary["runtime_pair_count"])
        self.assertEqual(2, summary["backtest_pair_count"])
