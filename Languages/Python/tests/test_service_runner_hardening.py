from __future__ import annotations

import math
import unittest
from unittest import mock

from app.service.api.host import ServiceApiBackgroundHost
from app.service.runtime import TradingBotService
from app.service.runners import backtest_executor_worker_runtime, bot_runtime_state
from app.service.runners.backtest_executor_snapshot_runtime import finish_snapshots
from app.service.runners.backtest_executor_request_runtime import coerce_datetime, coerce_int, coerce_number


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


class _BrokenNumericValue:
    def __float__(self) -> float:
        raise RuntimeError("unexpected numeric conversion failure")

    def __int__(self) -> int:
        raise RuntimeError("unexpected numeric conversion failure")


class ServiceRunnerHardeningTests(unittest.TestCase):
    def test_terminal_backtest_snapshot_is_persisted_before_publication(self):
        events: list[tuple[str, object]] = []
        runtime = mock.MagicMock()
        runtime.set_backtest_snapshot.side_effect = lambda snapshot: events.append(("publish", snapshot))
        adapter = mock.MagicMock()
        adapter._runtime = runtime
        adapter._progress_tick_count = 4
        adapter._persist_backtest_snapshot.side_effect = lambda snapshot: events.append(("persist", snapshot))

        finish_snapshots(
            adapter,
            session_id="session-1",
            started_at="2026-01-01T00:00:00+00:00",
            summary={
                "estimated_run_count": 1,
                "symbols": ["BTCUSDT"],
                "intervals": ["1h"],
                "indicator_keys": ["rsi"],
                "logic": "AND",
                "symbol_source": "Binance futures",
                "capital": 1000.0,
            },
            state="completed",
            message="Backtest session completed.",
            cancelled=False,
            run_records=[],
            error_records=[],
            progress_percent=100.0,
        )

        self.assertEqual(["persist", "publish"], [event[0] for event in events])
        self.assertIs(events[0][1], events[1][1])
        self.assertEqual("completed", events[0][1].state)

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

    def test_backtest_numeric_coercion_only_defaults_expected_input_errors(self):
        for value in (None, "", "not-a-number", object()):
            with self.subTest(value=value):
                self.assertEqual(3.5, coerce_number(value, 3.5))
                self.assertEqual(4, coerce_int(value, 4))

        with self.assertRaisesRegex(RuntimeError, "unexpected numeric conversion failure"):
            coerce_number(_BrokenNumericValue(), 3.5)
        with self.assertRaisesRegex(RuntimeError, "unexpected numeric conversion failure"):
            coerce_int(_BrokenNumericValue(), 4)

    def test_service_snapshot_numeric_parsing_does_not_hide_programming_errors(self):
        service = TradingBotService()

        account = service.set_account_snapshot(
            total_balance="not-a-number",
            available_balance="also-not-a-number",
            source="unit-test",
        )
        self.assertIsNone(account.total_balance)
        self.assertIsNone(account.available_balance)

        with self.assertRaisesRegex(RuntimeError, "unexpected numeric conversion failure"):
            service.set_account_snapshot(total_balance=_BrokenNumericValue(), source="unit-test")
        with self.assertRaisesRegex(RuntimeError, "unexpected numeric conversion failure"):
            service.set_portfolio_snapshot(active_pnl=_BrokenNumericValue(), source="unit-test")
        with self.assertRaisesRegex(RuntimeError, "unexpected numeric conversion failure"):
            service.set_runtime_state(
                active=True,
                active_engine_count=_BrokenNumericValue(),
                source="unit-test",
            )


if __name__ == "__main__":
    unittest.main()
