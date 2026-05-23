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
    from app.gui.runtime.window import window_webengine_guard_runtime

    PYQT_AVAILABLE = True
    PYQT_UNAVAILABLE_REASON = ""
except Exception as exc:
    PYQT_AVAILABLE = False
    PYQT_UNAVAILABLE_REASON = str(exc)


@unittest.skipIf(not PYQT_AVAILABLE, f"PyQt6 unavailable: {PYQT_UNAVAILABLE_REASON}")
class WindowWebEngineGuardLoggingTests(unittest.TestCase):
    def test_record_webengine_guard_exception_uses_window_debug_logger(self):
        class _Window:
            def __init__(self):
                self.messages: list[str] = []

            def _chart_debug_log(self, message):
                self.messages.append(str(message))

        window = _Window()
        window_webengine_guard_runtime._record_webengine_guard_exception(
            window,
            "unit_context",
            RuntimeError("first line\nsecond line"),
        )

        self.assertEqual(1, len(window.messages))
        self.assertIn("context=unit_context", window.messages[0])
        self.assertIn("RuntimeError", window.messages[0])
        self.assertIn("first line second line", window.messages[0])

    def test_record_webengine_guard_exception_falls_back_to_temp_debug_log(self):
        with tempfile.TemporaryDirectory() as tmp:
            with mock.patch.dict(os.environ, {"TEMP": tmp}):
                window_webengine_guard_runtime._record_webengine_guard_exception(
                    None,
                    "fallback_context",
                    RuntimeError("fallback failed"),
                )

            log_path = Path(tmp) / "binance_chart_debug.log"
            self.assertTrue(log_path.exists())
            contents = log_path.read_text(encoding="utf-8")
            self.assertIn("context=fallback_context", contents)
            self.assertIn("fallback failed", contents)

    def test_stop_webengine_visibility_watchdog_logs_timer_failures_and_clears_refs(self):
        class _Timer:
            def stop(self):
                raise RuntimeError("stop failed")

            def deleteLater(self):
                raise RuntimeError("delete failed")

        class _Window:
            def __init__(self):
                self._webengine_visibility_watchdog_timer = _Timer()
                self._webengine_visibility_watchdog_active = True
                self.messages: list[str] = []

            def _chart_debug_log(self, message):
                self.messages.append(str(message))

        window = _Window()
        window_webengine_guard_runtime.stop_webengine_visibility_watchdog(window)

        self.assertIsNone(window._webengine_visibility_watchdog_timer)
        self.assertFalse(window._webengine_visibility_watchdog_active)
        joined = "\n".join(window.messages)
        self.assertIn("context=webengine_watchdog_timer_stop", joined)
        self.assertIn("context=webengine_watchdog_timer_delete", joined)

    def test_restore_window_after_guard_logs_restore_failures(self):
        qtcore = window_webengine_guard_runtime.QtCore

        class _Window:
            def __init__(self):
                self.messages: list[str] = []

            def windowState(self):
                return qtcore.Qt.WindowState.WindowMinimized

            def isVisible(self):
                return True

            def showMaximized(self):
                raise RuntimeError("show failed")

            def raise_(self):
                raise RuntimeError("raise failed")

            def activateWindow(self):
                raise AssertionError("activate should not run after raise fails")

            def _chart_debug_log(self, message):
                self.messages.append(str(message))

        window = _Window()
        with mock.patch.object(qtcore.QTimer, "singleShot", return_value=None):
            window_webengine_guard_runtime.restore_window_after_guard(window)

        joined = "\n".join(window.messages)
        self.assertIn("context=restore_minimized_show", joined)
        self.assertIn("context=restore_raise_activate", joined)


if __name__ == "__main__":
    unittest.main()
