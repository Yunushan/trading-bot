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
        from PyQt6 import QtWidgets

        from app.gui.chart import lightweight_widget_runtime, tradingview_widget_runtime

        self.assertTrue(issubclass(lightweight_widget_runtime.LightweightChartWidget, QtWidgets.QWidget))
        self.assertTrue(issubclass(tradingview_widget_runtime.TradingViewWidget, QtWidgets.QWidget))

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
        close_all_runtime._record_close_all_exception(
            wrapper,
            "close_context",
            RuntimeError("close failed api_secret=unit-api-secret signature=unit-signature"),
        )
        http_diagnostic_runtime._record_http_diagnostic_exception(
            wrapper,
            "http_context",
            RuntimeError("http failed api_secret=unit-api-secret signature=unit-signature"),
        )

        joined = "\n".join(wrapper.messages)
        self.assertIn("context=close_context", joined)
        self.assertIn("context=http_context", joined)
        self.assertIn("<redacted>", joined)
        self.assertNotIn("unit-api-secret", joined)
        self.assertNotIn("unit-signature", joined)

    def test_strategy_order_logger_redacts_callback_messages(self):
        from app.core.strategy.orders.strategy_order_error_logging import safe_strategy_log

        class _Strategy:
            def __init__(self):
                self.messages: list[str] = []

            def log(self, message, lvl="info"):
                self.messages.append(f"{lvl}:{message}")

        strategy = _Strategy()
        safe_strategy_log(
            strategy,
            "order failed api_secret=unit-api-secret signature=unit-signature authorization=Bearer unit-token",
        )

        self.assertEqual(1, len(strategy.messages))
        self.assertIn("<redacted>", strategy.messages[0])
        self.assertNotIn("unit-api-secret", strategy.messages[0])
        self.assertNotIn("unit-signature", strategy.messages[0])
        self.assertNotIn("unit-token", strategy.messages[0])

    def test_gui_and_wrapper_log_boundaries_redact_messages(self):
        from collections import deque

        from app.gui.runtime.window import log_runtime
        from app.integrations.exchanges.binance.wrapper import BinanceWrapper

        class _Window:
            def __init__(self):
                self._log_buf = deque(maxlen=8)
                self.events: list[str] = []

            def _service_record_log_event(self, message, **_kwargs):
                self.events.append(str(message))

        window = _Window()
        message = "desktop failure api_secret=unit-api-secret authorization=Bearer unit-token"
        log_runtime._gui_buffer_log(window, message)

        self.assertIn("<redacted>", window._log_buf[0])
        self.assertIn("<redacted>", window.events[0])
        self.assertNotIn("unit-api-secret", window._log_buf[0])
        self.assertNotIn("unit-token", window.events[0])

        logger = mock.Mock()
        wrapper = object.__new__(BinanceWrapper)
        wrapper.logger = logger
        wrapper._log(message, lvl="error")

        logged_message = logger.error.call_args.args[0]
        self.assertIn("<redacted>", logged_message)
        self.assertNotIn("unit-api-secret", logged_message)
        self.assertNotIn("unit-token", logged_message)


if __name__ == "__main__":
    unittest.main()
