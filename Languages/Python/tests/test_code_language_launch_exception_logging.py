import os
import sys
import tempfile
import time
import unittest
from pathlib import Path
from unittest import mock


PYTHON_ROOT = Path(__file__).resolve().parents[1]
if str(PYTHON_ROOT) not in sys.path:
    sys.path.insert(0, str(PYTHON_ROOT))

if sys.platform.startswith("linux") and not os.environ.get("DISPLAY"):
    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

try:
    from app.gui.code import code_language_launch

    PYQT_AVAILABLE = True
    PYQT_UNAVAILABLE_REASON = ""
except Exception as exc:
    PYQT_AVAILABLE = False
    PYQT_UNAVAILABLE_REASON = str(exc)


@unittest.skipIf(not PYQT_AVAILABLE, f"PyQt6 unavailable: {PYQT_UNAVAILABLE_REASON}")
class CodeLanguageLaunchExceptionLoggingTests(unittest.TestCase):
    def test_record_code_launch_exception_uses_window_debug_logger(self):
        class _Window:
            def __init__(self):
                self.messages: list[str] = []

            def _chart_debug_log(self, message):
                self.messages.append(str(message))

        window = _Window()
        code_language_launch._record_code_launch_exception(
            "unit_context",
            RuntimeError("first line\nsecond line"),
            window,
        )

        self.assertEqual(1, len(window.messages))
        self.assertIn("context=unit_context", window.messages[0])
        self.assertIn("RuntimeError", window.messages[0])
        self.assertIn("first line second line", window.messages[0])

    def test_record_code_launch_exception_falls_back_to_temp_debug_log(self):
        with tempfile.TemporaryDirectory() as tmp:
            with mock.patch.dict(os.environ, {"TEMP": tmp}):
                code_language_launch._record_code_launch_exception(
                    "fallback_context",
                    RuntimeError("fallback failed"),
                )

            log_path = Path(tmp) / "binance_chart_debug.log"
            self.assertTrue(log_path.exists())
            contents = log_path.read_text(encoding="utf-8")
            self.assertIn("context=fallback_context", contents)
            self.assertIn("fallback failed", contents)

    def test_hide_window_for_handoff_logs_cleanup_failures(self):
        class _Window:
            def __init__(self):
                object.__setattr__(self, "visible", True)
                object.__setattr__(self, "messages", [])

            def __setattr__(self, name, value):
                if name == "handoff_active" and value is False:
                    raise RuntimeError("active reset failed")
                if name == "hidden_for_handoff":
                    raise RuntimeError("hidden store failed")
                object.__setattr__(self, name, value)

            def hide(self):
                self.visible = False

            def isVisible(self):  # noqa: N802
                return self.visible

            def _chart_debug_log(self, message):
                self.messages.append(str(message))

        window = _Window()
        hidden = code_language_launch.hide_window_for_handoff(
            window,
            None,
            active_attr="handoff_active",
            hidden_attr="hidden_for_handoff",
        )

        self.assertTrue(hidden)
        joined = "\n".join(window.messages)
        self.assertIn("context=hide_window_for_handoff_active_reset", joined)
        self.assertIn("context=hide_window_for_handoff_hidden_attr_store", joined)

    def test_run_callable_with_ui_pump_logs_process_event_failures(self):
        def _slow_result():
            time.sleep(0.03)
            return "ok"

        with tempfile.TemporaryDirectory() as tmp:
            with (
                mock.patch.dict(os.environ, {"TEMP": tmp}),
                mock.patch.object(
                    code_language_launch.QtWidgets.QApplication,
                    "processEvents",
                    side_effect=RuntimeError("pump failed"),
                ),
            ):
                result = code_language_launch.run_callable_with_ui_pump(_slow_result, poll_interval_s=0.01)

            self.assertEqual("ok", result)
            contents = (Path(tmp) / "binance_chart_debug.log").read_text(encoding="utf-8")
            self.assertIn("context=run_callable_with_ui_pump_process_events", contents)
            self.assertIn("pump failed", contents)


if __name__ == "__main__":
    unittest.main()
