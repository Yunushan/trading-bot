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


class RuntimeExceptionDiagnosticHelperTests(unittest.TestCase):
    def test_chart_view_exception_uses_chart_debug_logger(self):
        from app.gui.chart import view_runtime

        class _Window:
            def __init__(self):
                self.messages: list[str] = []

            def _chart_debug_log(self, message):
                self.messages.append(str(message))

        window = _Window()
        view_runtime._record_chart_view_exception(window, "unit_context", RuntimeError("chart failed"))

        self.assertEqual(1, len(window.messages))
        self.assertIn("context=unit_context", window.messages[0])
        self.assertIn("chart failed", window.messages[0])

    def test_startup_helpers_route_to_boot_logger(self):
        from app.bootstrap import (
            startup_icon_runtime,
            startup_lifecycle_runtime,
            startup_post_window_runtime,
        )

        icon_messages: list[str] = []
        post_messages: list[str] = []
        lifecycle_messages: list[str] = []

        with mock.patch.object(startup_icon_runtime, "_boot_log", side_effect=icon_messages.append):
            startup_icon_runtime._record_startup_icon_exception("icon_context", RuntimeError("icon failed"))

        with mock.patch.object(startup_post_window_runtime, "_boot_log", side_effect=post_messages.append):
            startup_post_window_runtime._record_post_window_exception("post_context", RuntimeError("post failed"))

        startup_lifecycle_runtime._record_startup_lifecycle_exception(
            "life_context",
            RuntimeError("life failed"),
            boot_log=lifecycle_messages.append,
        )

        self.assertIn("context=icon_context", icon_messages[0])
        self.assertIn("context=post_context", post_messages[0])
        self.assertIn("context=life_context", lifecycle_messages[0])

    def test_position_and_account_helpers_use_window_logger(self):
        from app.gui.positions import actions_state_runtime
        from app.gui.runtime.account import account_runtime

        class _Window:
            def __init__(self):
                self.messages: list[str] = []

            def _chart_debug_log(self, message):
                self.messages.append(str(message))

        window = _Window()
        actions_state_runtime._record_positions_action_exception(
            window,
            "positions_context",
            RuntimeError("position failed"),
        )
        account_runtime._record_account_runtime_exception(window, "account_context", RuntimeError("account failed"))

        joined = "\n".join(window.messages)
        self.assertIn("context=positions_context", joined)
        self.assertIn("context=account_context", joined)

    def test_chart_widget_helpers_write_to_chart_log(self):
        from app.gui.chart import lightweight_widget_runtime, tradingview_widget_runtime

        with tempfile.TemporaryDirectory() as tmp:
            log_path = Path(tmp) / "chart.log"
            with (
                mock.patch.object(lightweight_widget_runtime, "_LOG_PATH", log_path),
                mock.patch.object(tradingview_widget_runtime, "_LOG_PATH", log_path),
            ):
                lightweight_widget_runtime._log_lightweight_exception("light_context", RuntimeError("light failed"))
                tradingview_widget_runtime._log_tradingview_exception("tv_context", RuntimeError("tv failed"))

            contents = log_path.read_text(encoding="utf-8")
            self.assertIn("context=light_context", contents)
            self.assertIn("context=tv_context", contents)

    def test_binance_runtime_helpers_use_wrapper_logger(self):
        from app.integrations.exchanges.binance.positions import close_all_runtime
        from app.integrations.exchanges.binance.transport import http_diagnostic_runtime

        class _Wrapper:
            def __init__(self):
                self.messages: list[str] = []

            def _log(self, message, lvl="info"):
                self.messages.append(f"{lvl}:{message}")

        wrapper = _Wrapper()
        close_all_runtime._record_close_all_exception(wrapper, "close_context", RuntimeError("close failed"))
        http_diagnostic_runtime._record_http_diagnostic_exception(
            wrapper,
            "http_context",
            RuntimeError("http failed"),
        )

        joined = "\n".join(wrapper.messages)
        self.assertIn("context=close_context", joined)
        self.assertIn("context=http_context", joined)


if __name__ == "__main__":
    unittest.main()
