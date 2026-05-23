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
    from app.gui.runtime.ui import tab_runtime

    PYQT_AVAILABLE = True
    PYQT_UNAVAILABLE_REASON = ""
except Exception as exc:
    PYQT_AVAILABLE = False
    PYQT_UNAVAILABLE_REASON = str(exc)


@unittest.skipIf(not PYQT_AVAILABLE, f"PyQt6 unavailable: {PYQT_UNAVAILABLE_REASON}")
class TabRuntimeExceptionLoggingTests(unittest.TestCase):
    def test_record_tab_runtime_exception_uses_chart_debug_logger(self):
        class _Window:
            def __init__(self):
                self.messages: list[str] = []

            def _chart_debug_log(self, message):
                self.messages.append(str(message))

        window = _Window()
        tab_runtime._record_tab_runtime_exception(window, "unit_context", RuntimeError("first line\nsecond line"))

        self.assertEqual(1, len(window.messages))
        self.assertIn("context=unit_context", window.messages[0])
        self.assertIn("RuntimeError", window.messages[0])
        self.assertIn("first line second line", window.messages[0])

    def test_record_tab_runtime_exception_falls_back_to_temp_debug_log(self):
        with tempfile.TemporaryDirectory() as tmp:
            with mock.patch.dict(os.environ, {"TEMP": tmp}):
                tab_runtime._record_tab_runtime_exception(None, "fallback_context", RuntimeError("fallback failed"))

            log_path = Path(tmp) / "binance_chart_debug.log"
            self.assertTrue(log_path.exists())
            contents = log_path.read_text(encoding="utf-8")
            self.assertIn("context=fallback_context", contents)
            self.assertIn("fallback failed", contents)

    def test_code_tab_suppression_logs_property_and_start_failures(self):
        class _Tabs:
            def __init__(self, widget):
                self._widget = widget

            def widget(self, _index):
                return self._widget

        class _Window:
            def __init__(self):
                self.code_tab = object()
                self.tabs = _Tabs(self.code_tab)
                self.messages: list[str] = []

            def _start_code_tab_window_suppression(self):
                raise RuntimeError("suppression failed")

            def _chart_debug_log(self, message):
                self.messages.append(str(message))

        window = _Window()
        tab_runtime._maybe_start_code_tab_window_suppression(window, 0)

        joined = "\n".join(window.messages)
        self.assertIn("context=code_tab_suppression_lazy_property", joined)
        self.assertIn("context=start_code_tab_window_suppression", joined)

    def test_code_tab_auto_refresh_logs_refresh_failure_and_resets_done_flag(self):
        class _Tabs:
            def __init__(self, widget):
                self._widget = widget

            def currentWidget(self):  # noqa: N802
                return self._widget

        class _Window:
            def __init__(self):
                self.code_tab = object()
                self.tabs = _Tabs(self.code_tab)
                self._dep_version_refresh_inflight = False
                self._dep_version_auto_refresh_done = False
                self._code_tab_auto_refresh_versions_pending = False
                self._code_tab_auto_refresh_versions_token = 0
                self.messages: list[str] = []

            def _refresh_dependency_versions(self):
                raise RuntimeError("refresh failed")

            def _chart_debug_log(self, message):
                self.messages.append(str(message))

        window = _Window()
        with mock.patch.object(tab_runtime.QtCore.QTimer, "singleShot", side_effect=lambda _delay, callback: callback()):
            tab_runtime._schedule_code_tab_auto_refresh_versions(window)

        self.assertFalse(window._dep_version_auto_refresh_done)
        self.assertFalse(window._code_tab_auto_refresh_versions_pending)
        self.assertIn("context=auto_refresh_dependency_versions", "\n".join(window.messages))


if __name__ == "__main__":
    unittest.main()
