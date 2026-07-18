import sys
import tempfile
import unittest
from datetime import datetime
from pathlib import Path

PYTHON_ROOT = Path(__file__).resolve().parents[1]
if str(PYTHON_ROOT) not in sys.path:
    sys.path.insert(0, str(PYTHON_ROOT))

from app.core.backtest.models import BacktestRequest, IndicatorDefinition, PairOverride  # noqa: E402
from app.service.runners.backtest_checkpoint_store import (  # noqa: E402
    delete_backtest_checkpoint_file,
    deserialize_backtest_request,
    load_backtest_checkpoint_file,
    resolve_backtest_checkpoint_path,
    write_backtest_checkpoint_file,
)


class BacktestCheckpointStoreTests(unittest.TestCase):
    def test_checkpoint_round_trip_is_credential_free_and_restores_frozen_request(self):
        request = BacktestRequest(
            symbols=["BTCUSDT"],
            intervals=["1h"],
            indicators=[IndicatorDefinition(key="rsi", params={"length": 14})],
            logic="AND",
            symbol_source="Futures",
            start=datetime(2025, 1, 1),
            end=datetime(2025, 1, 2),
            capital=1000.0,
            pair_overrides=[
                PairOverride(
                    symbol="BTCUSDT",
                    interval="1h",
                    indicators=["rsi"],
                    strategy_controls={"leverage": 2},
                )
            ],
            optimizer_max_duration_seconds=60,
        )
        request.optimizer_result_limit = 500
        request.optimizer_metric = "roi_percent"
        request.optimizer_run_count = 5

        with tempfile.TemporaryDirectory() as tmp:
            checkpoint_path = resolve_backtest_checkpoint_path(Path(tmp) / "backtest-session.json")
            write_backtest_checkpoint_file(
                path=checkpoint_path,
                session_id="checkpoint-1",
                request=request,
                wrapper_options={"api_key": "secret-key", "api_secret": "secret-value", "mode": "Demo/Testnet"},
                summary={"symbols": ["BTCUSDT"], "estimated_run_count": 5},
                completed_combo_count=2,
                previous_runs=[{"symbol": "BTCUSDT", "roi_percent": 1.0}],
                previous_errors=[],
            )
            checkpoint = load_backtest_checkpoint_file(checkpoint_path)

            self.assertIsNotNone(checkpoint)
            assert checkpoint is not None
            self.assertEqual(2, checkpoint["completed_combo_count"])
            self.assertEqual({"mode": "Demo/Testnet"}, checkpoint["wrapper_options"])
            self.assertNotIn("secret-key", checkpoint_path.read_text(encoding="utf-8"))
            restored = deserialize_backtest_request(checkpoint["request"])
            self.assertEqual(request.symbols, restored.symbols)
            self.assertEqual(request.start, restored.start)
            self.assertEqual(["rsi"], restored.pair_overrides[0].indicators)

            delete_backtest_checkpoint_file(checkpoint_path)
            self.assertIsNone(load_backtest_checkpoint_file(checkpoint_path))
