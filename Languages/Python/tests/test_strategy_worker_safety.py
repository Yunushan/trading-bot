from __future__ import annotations

import sys
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch


PYTHON_ROOT = Path(__file__).resolve().parents[1]
if str(PYTHON_ROOT) not in sys.path:
    sys.path.insert(0, str(PYTHON_ROOT))

from app.gui.runtime.strategy_workers import StartWorker, StopWorker  # noqa: E402
from app.gui.runtime.strategy import start_runtime  # noqa: E402
from app.core.strategy import StrategyEngine  # noqa: E402


class _Guard:
    def __init__(self, reconciliation_result: bool) -> None:
        self.reconciliation_result = reconciliation_result
        self.last_exchange_guard_error = "position snapshot unavailable"
        self.attached_wrapper = None
        self.reset_calls = 0
        self.resume_calls = 0

    def attach_wrapper(self, wrapper) -> None:
        self.attached_wrapper = wrapper

    def reset(self) -> None:
        self.reset_calls += 1

    def resume_new(self) -> None:
        self.resume_calls += 1

    def reconcile_with_exchange(self, wrapper, jobs, *, account_type):  # noqa: ANN001
        del wrapper, jobs, account_type
        return self.reconciliation_result


class _Wrapper:
    account_type = "FUTURES"

    def __init__(self, mode: str) -> None:
        self.mode = mode


class _StopGuard:
    def pause_new(self) -> None:
        raise RuntimeError("guard pause failed")


class _BrokenStrategyLoop:
    def stop(self) -> None:
        raise RuntimeError("stop failed")

    def join(self, timeout: float) -> None:
        del timeout
        raise RuntimeError("join failed")


class _FuturesWrapper:
    account_type = "FUTURES"


class StrategyWorkerSafetyTests(unittest.TestCase):
    def _worker(self, *, mode: str, reconciliation_result: bool) -> tuple[StartWorker, list[dict]]:
        starts: list[dict] = []
        worker = StartWorker(
            _Guard(reconciliation_result),
            _Wrapper(mode),
            [{"symbol": "BTCUSDT", "interval": "1m"}],
            {"account_type": "FUTURES"},
            delay_ms=0,
        )
        worker._start_one = lambda job: starts.append(dict(job)) or True
        return worker, starts

    def test_live_start_is_blocked_when_guard_reconciliation_fails(self):
        worker, starts = self._worker(mode="Live", reconciliation_result=False)

        worker.run()

        self.assertEqual([], starts)

    def test_demo_start_keeps_best_effort_behavior_when_guard_reconciliation_fails(self):
        worker, starts = self._worker(mode="Demo", reconciliation_result=False)

        worker.run()

        self.assertEqual([{"symbol": "BTCUSDT", "interval": "1m"}], starts)

    def test_start_is_blocked_when_global_trading_resume_is_rejected(self):
        worker, starts = self._worker(mode="Live", reconciliation_result=True)
        logs: list[str] = []
        worker.log_signal.connect(logs.append)

        with patch.object(StrategyEngine, "resume_trading", return_value=False):
            worker.run()

        self.assertEqual([], starts)
        self.assertTrue(any("could not be resumed safely" in message for message in logs))

    def test_desktop_start_is_blocked_when_global_trading_resume_is_rejected(self):
        class _Engine:
            @classmethod
            def resume_trading(cls):
                return False

        class _Window:
            _is_stopping_engines = False
            shared_binance = None

            def __init__(self) -> None:
                self.logs: list[str] = []
                self.failures: list[dict] = []
                self.sync_calls = 0

            def log(self, message: str) -> None:
                self.logs.append(message)

            def _service_mark_start_failed(self, **payload) -> None:
                self.failures.append(payload)

            def _sync_runtime_state(self) -> None:
                self.sync_calls += 1

        window = _Window()
        context = SimpleNamespace(
            pair_entries=[object()],
            combos=[object()],
            account_type_text="Futures",
            is_futures_account=True,
            default_loop_override=None,
        )
        with (
            patch.object(start_runtime, "_collect_strategy_start_context", return_value=context),
            patch.object(start_runtime, "_prepare_strategy_runtime_start", return_value=(object(), None)),
            patch.object(start_runtime, "_start_strategy_engines") as start_engines,
        ):
            start_runtime.start_strategy(window, strategy_engine_cls=_Engine)

        start_engines.assert_not_called()
        self.assertEqual(1, window.sync_calls)
        self.assertEqual("desktop-start", window.failures[0]["source"])
        self.assertTrue(any("could not be resumed safely" in message for message in window.logs))

    def test_desktop_start_rejects_unavailable_runtime_and_active_stop(self):
        class _Window:
            def __init__(self, *, stopping: bool = False) -> None:
                self._is_stopping_engines = stopping
                self.shared_binance = None
                self.logs: list[str] = []

            def log(self, message: str) -> None:
                self.logs.append(message)

        unavailable = _Window()
        start_runtime.start_strategy(unavailable)
        self.assertEqual(["Strategy runtime is not available."], unavailable.logs)

        stopping = _Window(stopping=True)
        start_runtime.start_strategy(stopping, strategy_engine_cls=object())
        self.assertEqual(["Stop in progress; cannot start new engines."], stopping.logs)

    def test_desktop_start_rejects_emergency_close_and_invalid_context(self):
        class _Engine:
            @classmethod
            def resume_trading(cls):
                return True

        class _Window:
            _is_stopping_engines = False

            def __init__(self, shared_binance=None) -> None:
                self.shared_binance = shared_binance
                self.logs: list[str] = []
                self.sync_calls = 0

            def log(self, message: str) -> None:
                self.logs.append(message)

            def _sync_runtime_state(self) -> None:
                self.sync_calls += 1

        emergency = _Window(SimpleNamespace(_emergency_close_requested=True))
        start_runtime.start_strategy(emergency, strategy_engine_cls=_Engine)
        self.assertEqual(
            ["Emergency close-all in progress; wait for it to finish before starting."],
            emergency.logs,
        )

        for context, expected in (
            (
                SimpleNamespace(pair_entries=[], combos=[], account_type_text="Futures", is_futures_account=True),
                "No symbol/interval overrides configured. Add entries before starting.",
            ),
            (
                SimpleNamespace(pair_entries=[object()], combos=[], account_type_text="Futures", is_futures_account=True),
                "No valid symbol/interval overrides found.",
            ),
        ):
            window = _Window()
            with patch.object(start_runtime, "_collect_strategy_start_context", return_value=context):
                start_runtime.start_strategy(window, strategy_engine_cls=_Engine)
            self.assertEqual([expected], window.logs)
            self.assertEqual(1, window.sync_calls)

    def test_desktop_start_reports_prepare_and_resume_failures(self):
        class _Engine:
            @classmethod
            def resume_trading(cls):
                raise RuntimeError("resume unavailable")

        class _Window:
            _is_stopping_engines = False
            shared_binance = None

            def __init__(self) -> None:
                self.logs: list[str] = []
                self.failures: list[dict] = []
                self.sync_calls = 0

            def log(self, message: str) -> None:
                self.logs.append(message)

            def _service_mark_start_failed(self, **payload) -> None:
                self.failures.append(payload)

            def _sync_runtime_state(self) -> None:
                self.sync_calls += 1

        context = SimpleNamespace(
            pair_entries=[object()],
            combos=[object()],
            account_type_text="Futures",
            is_futures_account=True,
        )
        window = _Window()
        with (
            patch.object(start_runtime, "_collect_strategy_start_context", return_value=context),
            patch.object(start_runtime, "_prepare_strategy_runtime_start", return_value=(object(), None)),
        ):
            start_runtime.start_strategy(window, strategy_engine_cls=_Engine)

        self.assertEqual(1, window.sync_calls)
        self.assertEqual("desktop-start", window.failures[0]["source"])
        self.assertTrue(any("resume failed" in message for message in window.logs))

    def test_desktop_start_handles_rejection_unexpected_failure_and_zero_starts(self):
        class _Engine:
            @classmethod
            def resume_trading(cls):
                return True

        class _Window:
            _is_stopping_engines = False
            shared_binance = None

            def __init__(self) -> None:
                self.logs: list[str] = []
                self.failures: list[dict] = []
                self.sync_calls = 0

            def log(self, message: str) -> None:
                self.logs.append(message)

            def _service_mark_start_failed(self, **payload) -> None:
                self.failures.append(payload)

            def _sync_runtime_state(self) -> None:
                self.sync_calls += 1

        rejected = _Window()
        with patch.object(
            start_runtime,
            "_collect_strategy_start_context",
            side_effect=start_runtime.ServiceStartRejected("Service rejected the start."),
        ):
            start_runtime.start_strategy(rejected, strategy_engine_cls=_Engine)
        self.assertEqual(["Service rejected the start."], rejected.logs)
        self.assertEqual(0, rejected.sync_calls)

        failed = _Window()
        with patch.object(start_runtime, "_collect_strategy_start_context", side_effect=RuntimeError("bad context")):
            start_runtime.start_strategy(failed, strategy_engine_cls=_Engine)
        self.assertEqual(1, failed.sync_calls)
        self.assertEqual("desktop-start", failed.failures[0]["source"])
        self.assertTrue(any("Start error: bad context" in message for message in failed.logs))

        zero_starts = _Window()
        context = SimpleNamespace(
            pair_entries=[object()],
            combos=[object()],
            account_type_text="Futures",
            is_futures_account=True,
            default_loop_override=None,
        )
        with (
            patch.object(start_runtime, "_collect_strategy_start_context", return_value=context),
            patch.object(start_runtime, "_prepare_strategy_runtime_start", return_value=(object(), None)),
            patch.object(start_runtime, "_start_strategy_engines", return_value=0),
            patch.object(zero_starts, "_reset_service_connector_order_circuit_breaker", side_effect=RuntimeError("reset failed"), create=True),
        ):
            start_runtime.start_strategy(zero_starts, strategy_engine_cls=_Engine)
        self.assertEqual(1, zero_starts.sync_calls)
        self.assertEqual("No new engines started.", zero_starts.failures[0]["reason"])
        self.assertTrue(any("circuit-breaker reset" in message for message in zero_starts.logs))
        self.assertTrue(any("No new engines started" in message for message in zero_starts.logs))

    def test_stop_worker_reports_failed_cleanup_steps(self):
        worker = StopWorker(
            {"BTCUSDT@1m": _BrokenStrategyLoop()},
            None,
            guard=_StopGuard(),
        )
        logs: list[str] = []
        worker.log_signal.connect(logs.append)

        self.assertFalse(worker._stop_threads())

        self.assertTrue(any("Could not pause the order guard" in message for message in logs))
        self.assertTrue(any("Could not stop strategy loop BTCUSDT@1m" in message for message in logs))
        self.assertTrue(any("Could not join strategy loop BTCUSDT@1m" in message for message in logs))

    def test_stop_worker_closes_futures_after_a_cleanup_failure(self):
        worker = StopWorker(
            {"BTCUSDT@1m": _BrokenStrategyLoop()},
            _FuturesWrapper(),
            guard=_StopGuard(),
        )
        close_calls: list[bool] = []
        completion: list[bool] = []
        worker._close_futures = lambda: close_calls.append(True) or True
        worker.finished_ok.connect(completion.append)

        worker.run()

        self.assertEqual([True], close_calls)
        self.assertEqual([False], completion)


if __name__ == "__main__":
    unittest.main()
