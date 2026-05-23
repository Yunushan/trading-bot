import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock


PYTHON_ROOT = Path(__file__).resolve().parents[1]
if str(PYTHON_ROOT) not in sys.path:
    sys.path.insert(0, str(PYTHON_ROOT))

from app.gui.positions.tracking_runtime import (  # noqa: E402
    _apply_close_all_to_positions_cache,
    _handle_close_all_result,
    _record_positions_tracking_exception,
)


class PositionsTrackingExceptionLoggingTests(unittest.TestCase):
    def test_record_positions_tracking_exception_uses_chart_debug_logger(self):
        class _Window:
            def __init__(self):
                self.messages: list[str] = []

            def _chart_debug_log(self, message):
                self.messages.append(str(message))

        window = _Window()
        _record_positions_tracking_exception(window, "unit_context", RuntimeError("first line\nsecond line"))

        self.assertEqual(1, len(window.messages))
        self.assertIn("context=unit_context", window.messages[0])
        self.assertIn("RuntimeError", window.messages[0])
        self.assertIn("first line second line", window.messages[0])

    def test_record_positions_tracking_exception_falls_back_to_temp_debug_log(self):
        with tempfile.TemporaryDirectory() as tmp:
            with mock.patch.dict(os.environ, {"TEMP": tmp}):
                _record_positions_tracking_exception(None, "fallback_context", RuntimeError("fallback failed"))

            log_path = Path(tmp) / "binance_chart_debug.log"
            self.assertTrue(log_path.exists())
            contents = log_path.read_text(encoding="utf-8")
            self.assertIn("context=fallback_context", contents)
            self.assertIn("fallback failed", contents)

    def test_handle_close_all_result_logs_cache_and_refresh_failures(self):
        class _Window:
            def __init__(self):
                self.messages: list[str] = []
                self.logs: list[str] = []

            def log(self, message):
                self.logs.append(str(message))

            def _chart_debug_log(self, message):
                self.messages.append(str(message))

            def _apply_close_all_to_positions_cache(self, _res):
                raise RuntimeError("cache failed")

            def refresh_positions(self):
                raise RuntimeError("refresh failed")

            def trigger_positions_refresh(self):
                raise RuntimeError("trigger failed")

        window = _Window()
        _handle_close_all_result(window, [{"symbol": "BTCUSDT", "ok": True}])

        self.assertIn("Close-all BTCUSDT: ok", "\n".join(window.logs))
        joined = "\n".join(window.messages)
        self.assertIn("context=apply_close_all_to_positions_cache", joined)
        self.assertIn("context=refresh_positions_after_close_all", joined)
        self.assertIn("context=trigger_positions_refresh_after_close_all", joined)

    def test_apply_close_all_cache_logs_reconciliation_failures_and_still_closes_record(self):
        class _Guard:
            def clear_symbol_side(self, _symbol, _side):
                raise RuntimeError("guard failed")

        class _Window:
            def __init__(self):
                self.config = {"positions_closed_history_max": 200}
                self.guard = _Guard()
                self.messages: list[str] = []
                self._open_position_records = {
                    ("BTCUSDT", "L"): {
                        "symbol": "BTCUSDT",
                        "side_key": "L",
                        "status": "Open",
                        "data": {},
                    }
                }
                self._entry_intervals = {"BTCUSDT": {"L": {"1m"}, "S": set()}}
                self._entry_times = {("BTCUSDT", "L"): "open-time"}
                self._entry_times_by_iv = {("BTCUSDT", "L", "1m"): "open-time"}
                self._entry_allocations = {}
                self._closed_position_records = []

            def _chart_debug_log(self, message):
                self.messages.append(str(message))

            def _format_display_time(self, _dt):
                return "close-time"

            def _track_interval_close(self, _symbol, _side, _interval):
                raise RuntimeError("track close failed")

            def _compute_global_pnl_totals(self):
                return (0.0, 0.0)

            def _update_global_pnl_display(self, *_args):
                raise RuntimeError("pnl failed")

            def _render_positions_table(self):
                raise RuntimeError("render failed")

        window = _Window()
        _apply_close_all_to_positions_cache(window, [{"symbol": "BTCUSDT", "ok": True}])

        self.assertEqual({}, window._open_position_records)
        self.assertEqual("Closed", window._closed_position_records[0]["status"])
        joined = "\n".join(window.messages)
        self.assertIn("context=track_interval_close_cache_reconcile", joined)
        self.assertIn("context=clear_position_guard_symbol_side", joined)
        self.assertIn("context=update_global_pnl_after_close_all", joined)
        self.assertIn("context=render_positions_after_close_all", joined)


if __name__ == "__main__":
    unittest.main()
