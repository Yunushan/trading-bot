import json
import sys
import tempfile
import unittest
from pathlib import Path

PYTHON_ROOT = Path(__file__).resolve().parents[1]
if str(PYTHON_ROOT) not in sys.path:
    sys.path.insert(0, str(PYTHON_ROOT))

from app.service.runners.backtest_snapshot_store import (  # noqa: E402
    BACKTEST_SNAPSHOT_FILE_KIND,
    load_backtest_snapshot_file,
    write_backtest_snapshot_file,
)
from app.service.schemas.backtest import build_backtest_snapshot  # noqa: E402


class BacktestSnapshotStoreTests(unittest.TestCase):
    def test_running_snapshot_is_recovered_as_interrupted_without_auto_resume(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "backtest-session.json"
            snapshot = build_backtest_snapshot(
                session_id="session-1",
                state="running",
                status_message="Backtest running.",
                symbols=["BTCUSDT"],
                intervals=["1h"],
                runs=[{"symbol": "BTCUSDT", "interval": "1h", "indicator_keys": ["rsi"]}],
            )
            write_backtest_snapshot_file(snapshot, path=path)

            recovered = load_backtest_snapshot_file(path)
            payload = json.loads(path.read_text(encoding="utf-8"))

            self.assertEqual(BACKTEST_SNAPSHOT_FILE_KIND, payload["kind"])
            self.assertIsNotNone(recovered)
            self.assertEqual("interrupted", recovered.state)
            self.assertEqual("session-1", recovered.session_id)
            self.assertEqual(["BTCUSDT"], list(recovered.symbols))
            self.assertIn("interrupted by a service restart", recovered.errors[-1].error)

    def test_completed_snapshot_is_available_after_restart(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "backtest-session.json"
            snapshot = build_backtest_snapshot(
                session_id="session-2",
                state="completed",
                status_message="Backtest completed.",
                symbols=["ETHUSDT"],
                intervals=["15m"],
                run_count=1,
                runs=[{"symbol": "ETHUSDT", "interval": "15m", "indicator_keys": ["rsi"]}],
            )
            write_backtest_snapshot_file(snapshot, path=path)

            recovered = load_backtest_snapshot_file(path)

            self.assertIsNotNone(recovered)
            self.assertEqual("completed", recovered.state)
            self.assertEqual("session-2", recovered.session_id)
            self.assertEqual(1, recovered.run_count)
