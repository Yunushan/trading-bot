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
    from app.gui.runtime.account.balance_runtime import (
        _record_balance_runtime_exception,
        update_balance_label,
    )

    PYQT_AVAILABLE = True
    PYQT_UNAVAILABLE_REASON = ""
except Exception as exc:
    PYQT_AVAILABLE = False
    PYQT_UNAVAILABLE_REASON = str(exc)


@unittest.skipIf(not PYQT_AVAILABLE, f"PyQt6 unavailable: {PYQT_UNAVAILABLE_REASON}")
class BalanceRuntimeExceptionLoggingTests(unittest.TestCase):
    def test_record_balance_runtime_exception_uses_chart_debug_logger(self):
        class _Window:
            def __init__(self):
                self.messages: list[str] = []

            def _chart_debug_log(self, message):
                self.messages.append(str(message))

        window = _Window()
        _record_balance_runtime_exception(window, "unit_context", RuntimeError("first line\nsecond line"))

        self.assertEqual(1, len(window.messages))
        self.assertIn("context=unit_context", window.messages[0])
        self.assertIn("RuntimeError", window.messages[0])
        self.assertIn("first line second line", window.messages[0])

    def test_record_balance_runtime_exception_falls_back_to_temp_debug_log(self):
        with tempfile.TemporaryDirectory() as tmp:
            with mock.patch.dict(os.environ, {"TEMP": tmp}):
                _record_balance_runtime_exception(None, "fallback_context", RuntimeError("fallback failed"))

            log_path = Path(tmp) / "binance_chart_debug.log"
            self.assertTrue(log_path.exists())
            contents = log_path.read_text(encoding="utf-8")
            self.assertIn("context=fallback_context", contents)
            self.assertIn("fallback failed", contents)

    def test_missing_credentials_logs_button_restore_failures(self):
        class _TextField:
            def text(self):
                return ""

        class _Button:
            def text(self):
                return "Refresh Balance"

            def setEnabled(self, _enabled):  # noqa: N802
                raise RuntimeError("button enable failed")

            def setText(self, _text):  # noqa: N802
                raise AssertionError("setText should not run after setEnabled fails")

        class _Label:
            def __init__(self):
                self.texts: list[str] = []

            def setText(self, text):  # noqa: N802
                self.texts.append(str(text))

        class _Window:
            def __init__(self):
                self.refresh_balance_btn = _Button()
                self.balance_label = _Label()
                self.api_key_edit = _TextField()
                self.api_secret_edit = _TextField()
                self.positions_updates: list[tuple[object, object]] = []
                self.messages: list[str] = []

            def _update_positions_balance_labels(self, total, available):
                self.positions_updates.append((total, available))

            def _chart_debug_log(self, message):
                self.messages.append(str(message))

        window = _Window()
        update_balance_label(window)

        self.assertIsNone(getattr(window, "_balance_refresh_token", None))
        self.assertEqual(["Refreshing...", "API credentials missing"], window.balance_label.texts)
        self.assertEqual([(None, None)], window.positions_updates)
        joined = "\n".join(window.messages)
        self.assertIn("context=balance_refresh_button_start", joined)
        self.assertIn("context=missing_credentials_button_restore", joined)


if __name__ == "__main__":
    unittest.main()
