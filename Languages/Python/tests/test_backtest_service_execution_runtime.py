import sys
import unittest
from pathlib import Path
from unittest import mock

PYTHON_ROOT = Path(__file__).resolve().parents[1]
if str(PYTHON_ROOT) not in sys.path:
    sys.path.insert(0, str(PYTHON_ROOT))

from app.gui.backtest import backtest_service_execution_runtime as runtime  # noqa: E402


class _Label:
    def __init__(self) -> None:
        self.text = ""

    def setText(self, text: str) -> None:  # noqa: N802
        self.text = str(text)


class _Button:
    def __init__(self) -> None:
        self.enabled = True

    def setEnabled(self, enabled: bool) -> None:  # noqa: N802
        self.enabled = bool(enabled)


class _Table:
    def __init__(self) -> None:
        self.rows = 0

    def setRowCount(self, rows: int) -> None:  # noqa: N802
        self.rows = int(rows)


class _Window:
    def __init__(self) -> None:
        self.config = {"backtest": {"execution_backend": "service"}}
        self.backtest_config = self.config["backtest"]
        self.backtest_status_label = _Label()
        self.backtest_run_btn = _Button()
        self.backtest_scan_btn = _Button()
        self.backtest_stop_btn = _Button()
        self.backtest_results_table = _Table()
        self.submitted = None
        self.stopped = False
        self.finished = None
        self.scan_finished = None
        self.snapshot = {
            "state": "completed",
            "status_message": "done",
            "runs": [{"symbol": "BTCUSDT", "interval": "1h"}],
            "errors": [],
        }

    def _get_service_client_descriptor(self):
        return {"client_mode": "embedded"}

    def _service_submit_backtest(self, request, *, source):
        self.submitted = {"request": request, "source": source}
        return {"accepted": True, "session_id": "abc", "state": "running"}

    def _service_stop_backtest(self, *, source):
        self.stopped = source
        return {"accepted": True, "status_message": "stopping"}

    def _get_service_backtest_snapshot(self):
        return dict(self.snapshot)

    def _on_backtest_finished(self, result, error):
        self.finished = (result, error)

    def _on_backtest_scan_finished(self, result, error):
        self.scan_finished = (result, error)


class BacktestServiceExecutionRuntimeTests(unittest.TestCase):
    def test_service_backtest_is_opt_in_or_remote(self):
        window = _Window()

        self.assertTrue(runtime.should_use_service_backtest(window))

        window.backtest_config["execution_backend"] = "local"
        self.assertFalse(runtime.should_use_service_backtest(window))

        window._get_service_client_descriptor = lambda: {"client_mode": "remote"}  # type: ignore[method-assign]
        self.assertTrue(runtime.should_use_service_backtest(window))

    def test_start_service_backtest_submits_and_finishes_from_full_runs_snapshot(self):
        window = _Window()

        with mock.patch.object(runtime.QtCore.QTimer, "singleShot") as single_shot:
            handled = runtime.maybe_start_service_backtest(
                window,
                {"symbols": ["BTCUSDT"]},
                scan=False,
            )

        self.assertTrue(handled)
        self.assertEqual("desktop-backtest-run", window.submitted["source"])
        self.assertFalse(window.backtest_run_btn.enabled)
        self.assertEqual(0, window.backtest_results_table.rows)
        single_shot.assert_called_once()

        runtime.poll_service_backtest(window)

        self.assertFalse(window._backtest_service_session_active)
        result, error = window.finished
        self.assertIsNone(error)
        self.assertEqual("BTCUSDT", result["runs"][0]["symbol"])

    def test_start_service_scan_uses_scan_callback_and_stop_uses_service(self):
        window = _Window()

        with mock.patch.object(runtime.QtCore.QTimer, "singleShot"):
            runtime.maybe_start_service_backtest(
                window,
                {"symbols": ["BTCUSDT"]},
                scan=True,
            )

        self.assertTrue(runtime.stop_service_backtest(window))
        self.assertEqual("desktop-backtest-stop", window.stopped)
        self.assertFalse(window.backtest_stop_btn.enabled)
        runtime.poll_service_backtest(window)

        result, error = window.scan_finished
        self.assertIsNone(error)
        self.assertEqual("BTCUSDT", result["runs"][0]["symbol"])


if __name__ == "__main__":
    unittest.main()
