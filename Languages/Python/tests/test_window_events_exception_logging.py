import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock


PYTHON_ROOT = Path(__file__).resolve().parents[1]
if str(PYTHON_ROOT) not in sys.path:
    sys.path.insert(0, str(PYTHON_ROOT))

if sys.platform.startswith("linux") and not os.environ.get("DISPLAY"):
    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

try:
    from app.gui.runtime.window.window_events_runtime import (
        _record_suppressed_exception,
        teardown_positions_thread,
    )

    PYQT_AVAILABLE = True
    PYQT_UNAVAILABLE_REASON = ""
except Exception as exc:
    PYQT_AVAILABLE = False
    PYQT_UNAVAILABLE_REASON = str(exc)


@unittest.skipIf(not PYQT_AVAILABLE, f"PyQt6 unavailable: {PYQT_UNAVAILABLE_REASON}")
class WindowEventsExceptionLoggingTests(unittest.TestCase):
    def test_record_suppressed_exception_uses_window_debug_logger(self):
        class _Window:
            def __init__(self):
                self.messages: list[str] = []

            def _chart_debug_log(self, message):
                self.messages.append(str(message))

        window = _Window()
        _record_suppressed_exception(window, "unit_context", RuntimeError("first line\nsecond line"))

        self.assertEqual(1, len(window.messages))
        self.assertIn("context=unit_context", window.messages[0])
        self.assertIn("RuntimeError", window.messages[0])
        self.assertIn("first line second line", window.messages[0])

    def test_record_suppressed_exception_falls_back_to_temp_debug_log(self):
        with tempfile.TemporaryDirectory() as tmp:
            with mock.patch.dict(os.environ, {"TEMP": tmp}):
                _record_suppressed_exception(None, "strategy_shutdown", RuntimeError("shutdown failed"))

            log_path = Path(tmp) / "binance_chart_debug.log"
            self.assertTrue(log_path.exists())
            contents = log_path.read_text(encoding="utf-8")
            self.assertIn("context=strategy_shutdown", contents)
            self.assertIn("shutdown failed", contents)

    def test_teardown_positions_thread_logs_cleanup_failures_and_clears_refs(self):
        class _StopSignal:
            def emit(self):
                raise RuntimeError("stop signal failed")

        class _Thread:
            def quit(self):
                raise RuntimeError("thread quit failed")

            def wait(self, _timeout):
                raise AssertionError("wait should not run after quit fails")

        class _Window:
            def __init__(self):
                self._pos_worker = object()
                self._pos_thread = _Thread()
                self.req_pos_stop = _StopSignal()
                self.messages: list[str] = []

            def _chart_debug_log(self, message):
                self.messages.append(str(message))

        window = _Window()
        teardown_positions_thread(window)

        self.assertIsNone(window._pos_worker)
        self.assertIsNone(window._pos_thread)
        joined = "\n".join(window.messages)
        self.assertIn("context=positions_stop_signal", joined)
        self.assertIn("context=positions_thread_shutdown", joined)


if __name__ == "__main__":
    unittest.main()
