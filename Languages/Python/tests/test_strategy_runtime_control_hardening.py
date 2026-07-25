from __future__ import annotations

import sys
import unittest
from pathlib import Path
from unittest import mock


PYTHON_ROOT = Path(__file__).resolve().parents[1]
if str(PYTHON_ROOT) not in sys.path:
    sys.path.insert(0, str(PYTHON_ROOT))

from app.config import build_default_config  # noqa: E402
from app.core.strategy import StrategyEngine  # noqa: E402


class _FakeBinance:
    account_type = "FUTURES"


class _ReadFailureEvent:
    def is_set(self):
        raise RuntimeError("event read failed")


class _SetFailureEvent:
    def set(self):
        raise RuntimeError("event set failed")

    def is_set(self):
        return False


class _BrokenLock:
    def __enter__(self):
        raise RuntimeError("lock acquisition failed")

    def __exit__(self, *_args):
        return False


class _BrokenJoinThread:
    def join(self, _timeout):
        raise RuntimeError("join failed")


class _BrokenGate:
    def acquire(self, *, timeout):  # noqa: ARG002
        return True

    def release(self):
        raise RuntimeError("gate release failed")


def _build_engine(*, logs: list[str] | None = None) -> StrategyEngine:
    config = build_default_config()
    config["symbol"] = "BTCUSDT"
    config["interval"] = "1m"
    return StrategyEngine(_FakeBinance(), config, log_callback=(logs if logs is not None else []).append)


class StrategyRuntimeControlHardeningTests(unittest.TestCase):
    def setUp(self):
        StrategyEngine._GLOBAL_SHUTDOWN.clear()
        StrategyEngine._GLOBAL_PAUSE.clear()
        StrategyEngine._GLOBAL_SHUTDOWN_FALLBACK = False
        StrategyEngine._GLOBAL_PAUSE_FALLBACK = False
        with StrategyEngine._CONNECTOR_ORDER_BLOCK_LOCK:
            StrategyEngine._CONNECTOR_ORDER_BLOCK_EVENTS.clear()
            StrategyEngine._CONNECTOR_ORDER_CIRCUIT_OPEN = False

    def tearDown(self):
        StrategyEngine._GLOBAL_SHUTDOWN.clear()
        StrategyEngine._GLOBAL_PAUSE.clear()
        StrategyEngine._GLOBAL_SHUTDOWN_FALLBACK = False
        StrategyEngine._GLOBAL_PAUSE_FALLBACK = False
        with StrategyEngine._CONNECTOR_ORDER_BLOCK_LOCK:
            StrategyEngine._CONNECTOR_ORDER_BLOCK_EVENTS.clear()
            StrategyEngine._CONNECTOR_ORDER_CIRCUIT_OPEN = False

    def test_unreadable_shutdown_event_stops_strategy_fail_closed(self):
        engine = _build_engine()

        with mock.patch.object(StrategyEngine, "_GLOBAL_SHUTDOWN", _ReadFailureEvent()):
            self.assertTrue(engine.stopped())
            self.assertTrue(StrategyEngine._GLOBAL_SHUTDOWN_FALLBACK)

    def test_shutdown_set_failure_uses_persistent_fail_closed_fallback(self):
        engine = _build_engine()

        with mock.patch.object(StrategyEngine, "_GLOBAL_SHUTDOWN", _SetFailureEvent()):
            StrategyEngine.request_shutdown()
            self.assertTrue(StrategyEngine._GLOBAL_SHUTDOWN_FALLBACK)
            self.assertTrue(engine.stopped())

    def test_resume_lock_failure_keeps_pause_and_circuit_state(self):
        StrategyEngine.pause_trading()
        StrategyEngine._CONNECTOR_ORDER_BLOCK_EVENTS.append({"reason": "network"})
        StrategyEngine._CONNECTOR_ORDER_CIRCUIT_OPEN = True

        with mock.patch.object(StrategyEngine, "_CONNECTOR_ORDER_BLOCK_LOCK", _BrokenLock()):
            StrategyEngine.resume_trading()

        self.assertTrue(StrategyEngine._GLOBAL_PAUSE.is_set())
        self.assertTrue(StrategyEngine._GLOBAL_PAUSE_FALLBACK)
        self.assertTrue(StrategyEngine._CONNECTOR_ORDER_CIRCUIT_OPEN)
        self.assertEqual([{"reason": "network"}], StrategyEngine._CONNECTOR_ORDER_BLOCK_EVENTS)

    def test_stop_blocking_forces_local_stop_and_reports_join_failure(self):
        logs: list[str] = []
        engine = _build_engine(logs=logs)

        def fail_stop():
            raise RuntimeError("stop failed")

        engine.stop = fail_stop
        engine._thread = _BrokenJoinThread()

        engine.stop_blocking(timeout=0.0)

        self.assertTrue(engine._stop)
        self.assertIn("forcing local stop", "\n".join(logs))
        self.assertIn("thread join failed", "\n".join(logs))

    def test_run_gate_release_failure_stops_loop_fail_closed(self):
        logs: list[str] = []
        engine = _build_engine(logs=logs)
        engine._phase_seed = 0.0
        engine.run_once = lambda: None

        with mock.patch.object(StrategyEngine, "_RUN_GATE", _BrokenGate()):
            engine.run_loop()

        self.assertTrue(engine._stop)
        self.assertIn("run gate release failed", "\n".join(logs))


if __name__ == "__main__":
    unittest.main()
