from __future__ import annotations

import sys
import unittest
from pathlib import Path


PYTHON_ROOT = Path(__file__).resolve().parents[1]
if str(PYTHON_ROOT) not in sys.path:
    sys.path.insert(0, str(PYTHON_ROOT))

from app.gui.runtime.strategy_workers import StartWorker  # noqa: E402


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


if __name__ == "__main__":
    unittest.main()
