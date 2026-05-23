import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock


PYTHON_ROOT = Path(__file__).resolve().parents[1]
if str(PYTHON_ROOT) not in sys.path:
    sys.path.insert(0, str(PYTHON_ROOT))

from app.bootstrap.startup_presentation_runtime import (  # noqa: E402
    _StartupPresentationController,
    _record_startup_presentation_exception,
)


class StartupPresentationLoggingTests(unittest.TestCase):
    def _controller_with_log(self, messages: list[str]) -> _StartupPresentationController:
        controller = _StartupPresentationController.__new__(_StartupPresentationController)
        controller._boot_log = messages.append
        return controller

    def test_record_startup_presentation_exception_uses_boot_log(self):
        messages: list[str] = []

        _record_startup_presentation_exception(
            messages.append,
            "unit_context",
            RuntimeError("first line\nsecond line"),
        )

        self.assertEqual(1, len(messages))
        self.assertIn("context=unit_context", messages[0])
        self.assertIn("RuntimeError", messages[0])
        self.assertIn("first line second line", messages[0])

    def test_record_startup_presentation_exception_falls_back_to_temp_log(self):
        def _broken_log(_message: str) -> None:
            raise RuntimeError("boot log unavailable")

        with tempfile.TemporaryDirectory() as tmp:
            with mock.patch.dict(os.environ, {"TEMP": tmp}):
                _record_startup_presentation_exception(
                    _broken_log,
                    "fallback_context",
                    RuntimeError("fallback failed"),
                )

            log_path = Path(tmp) / "binance_startup_debug.log"
            self.assertTrue(log_path.exists())
            contents = log_path.read_text(encoding="utf-8")
            self.assertIn("context=fallback_context", contents)
            self.assertIn("fallback failed", contents)

    def test_set_status_logs_splash_status_failures(self):
        class _Splash:
            def set_status(self, _text: str) -> None:
                raise RuntimeError("status failed")

        messages: list[str] = []
        controller = self._controller_with_log(messages)
        controller._splash = _Splash()

        controller.set_status("Loading")

        self.assertEqual(1, len(messages))
        self.assertIn("context=set_splash_status", messages[0])
        self.assertIn("status failed", messages[0])

    def test_stop_startup_overlay_raise_timer_logs_timer_failures_and_clears_timer(self):
        class _Timer:
            def stop(self) -> None:
                raise RuntimeError("stop failed")

            def deleteLater(self) -> None:  # noqa: N802
                raise RuntimeError("delete failed")

        messages: list[str] = []
        controller = self._controller_with_log(messages)
        controller._startup_overlay_raise_timer = _Timer()

        controller._stop_startup_overlay_raise_timer()

        self.assertIsNone(controller._startup_overlay_raise_timer)
        joined = "\n".join(messages)
        self.assertIn("context=startup_overlay_timer_stop", joined)
        self.assertIn("context=startup_overlay_timer_delete", joined)


if __name__ == "__main__":
    unittest.main()
