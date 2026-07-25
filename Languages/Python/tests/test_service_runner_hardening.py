from __future__ import annotations

import math
import unittest
from unittest import mock

from app.service.api.host import ServiceApiBackgroundHost
from app.service.runners import backtest_executor_worker_runtime, bot_runtime_state
from app.service.runners.backtest_executor_request_runtime import coerce_datetime


class _StoppedThread:
    def is_alive(self) -> bool:
        return False

    def join(self, _timeout: float) -> None:
        return None


class _BrokenShutdownServer:
    @property
    def should_exit(self) -> bool:
        return False

    @should_exit.setter
    def should_exit(self, _value: bool) -> None:
        raise RuntimeError("should-exit denied")

    @property
    def force_exit(self) -> bool:
        return False

    @force_exit.setter
    def force_exit(self, _value: bool) -> None:
        raise RuntimeError("force-exit denied")


class ServiceRunnerHardeningTests(unittest.TestCase):
    def test_background_host_exposes_shutdown_flag_failures(self):
        host = ServiceApiBackgroundHost()
        host._server = _BrokenShutdownServer()
        host._thread = _StoppedThread()

        self.assertTrue(host.stop())
        self.assertEqual("should-exit denied", host.describe()["shutdown_error"])

    def test_backtest_source_assignment_failure_fails_session(self):
        class _Wrapper:
            @property
            def indicator_source(self) -> str:
                return ""

            @indicator_source.setter
            def indicator_source(self, _value: str) -> None:
                raise RuntimeError("source selection denied")

        runtime = mock.MagicMock()
        adapter = mock.MagicMock()
        adapter._wrapper_factory.return_value = _Wrapper()
        adapter._runtime = runtime
        adapter._start_next_queued_backtest.return_value = None

        with mock.patch.object(backtest_executor_worker_runtime, "finish_snapshots") as finish:
            backtest_executor_worker_runtime.run_backtest_thread(
                adapter,
                "session-1",
                "2026-01-01T00:00:00+00:00",
                object(),
                {},
                {"symbol_source": "Spot"},
            )

        self.assertEqual("failed", finish.call_args.kwargs["state"])
        self.assertIn("source selection denied", finish.call_args.kwargs["message"])
        runtime.record_log_event.assert_called_once()
        self.assertEqual("error", runtime.record_log_event.call_args.kwargs["level"])

    def test_timestamp_parser_rejects_non_finite_and_boolean_values(self):
        parser = bot_runtime_state.BotRuntimeStateMixin._timestamp_epoch
        for value in (True, False, math.nan, math.inf, -math.inf, "nan", "inf", "-inf"):
            with self.subTest(value=value):
                self.assertIsNone(parser(value))

        self.assertEqual(123.5, parser("123.5"))
        self.assertIsNotNone(parser("2026-01-01T00:00:00Z"))

    def test_backtest_datetime_parser_keeps_supported_formats(self):
        date_only = coerce_datetime("2026-01-02")
        date_time = coerce_datetime("2026-01-02 03:04:05")
        self.assertIsNotNone(date_only)
        self.assertIsNotNone(date_time)
        assert date_only is not None
        assert date_time is not None
        self.assertEqual("2026-01-02", date_only.date().isoformat())
        self.assertEqual("2026-01-02T03:04:05", date_time.isoformat())
        self.assertIsNone(coerce_datetime("not-a-date"))


if __name__ == "__main__":
    unittest.main()
