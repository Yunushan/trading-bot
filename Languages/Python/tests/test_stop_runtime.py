from __future__ import annotations

import sys
import unittest
from pathlib import Path


PYTHON_ROOT = Path(__file__).resolve().parents[1]
if str(PYTHON_ROOT) not in sys.path:
    sys.path.insert(0, str(PYTHON_ROOT))

from app.gui.runtime.strategy.stop_runtime import stop_strategy_async, stop_strategy_sync  # noqa: E402


class _FailingStrategyEngine:
    @staticmethod
    def pause_trading() -> None:
        raise RuntimeError("strategy pause failure")


class _FailingGuard:
    def pause_new(self) -> None:
        raise RuntimeError("guard pause failure")


class _Runtime:
    def __init__(self) -> None:
        self.guard = _FailingGuard()
        self.logged: list[str] = []

    def _service_request_stop(self, **_kwargs) -> None:
        raise RuntimeError("service stop failure")

    def log(self, message: str) -> None:
        self.logged.append(message)


class _Engine:
    def __init__(self, *, alive: bool = False) -> None:
        self.alive = alive
        self.stop_calls = 0
        self.join_timeouts: list[float] = []

    def stop(self) -> None:
        self.stop_calls += 1

    def join(self, timeout: float) -> None:
        self.join_timeouts.append(timeout)

    def is_alive(self) -> bool:
        return self.alive


class _FuturesWrapper:
    def __init__(self) -> None:
        self.cancel_calls = 0

    def cancel_all_open_futures_orders(self) -> dict:
        self.cancel_calls += 1
        return {"ok": True, "call": self.cancel_calls}


class _CloseRuntime:
    def __init__(self) -> None:
        self.guard = None
        self.logged: list[str] = []
        self.strategy_engines = {"BTCUSDT@1m": _Engine(alive=True)}
        self._engine_indicator_map = {"BTCUSDT@1m": {"indicators": ["rsi"]}}
        self.shared_binance = None
        self.close_calls: list[dict] = []

    def log(self, message: str) -> None:
        self.logged.append(message)

    def _service_request_stop(self, **_kwargs) -> None:
        return None

    def _build_wrapper_from_values(self, auth: dict):
        del auth
        return _FuturesWrapper()

    def _close_all_positions_blocking(self, **kwargs) -> dict:
        self.close_calls.append(dict(kwargs))
        return {"ok": True, "closed": 1}


class _AsyncRuntime:
    def __init__(self) -> None:
        self.logged: list[str] = []
        self.close_results: list[object] = []
        self.sync_calls = 0

    def log(self, message: str) -> None:
        self.logged.append(message)

    def _snapshot_auth_state(self) -> dict:
        return {"mode": "Testnet"}

    def _handle_close_all_result(self, result) -> None:
        self.close_results.append(result)

    def _sync_runtime_state(self) -> None:
        self.sync_calls += 1


class StopRuntimeTests(unittest.TestCase):
    def test_stop_strategy_retains_critical_stop_warnings(self) -> None:
        runtime = _Runtime()

        result = stop_strategy_sync(
            runtime,
            close_positions=False,
            strategy_engine_cls=_FailingStrategyEngine,
        )

        self.assertTrue(result["ok"])
        self.assertEqual(
            result["warnings"],
            [
                "Service stop request failed: service stop failure",
                "Could not pause new strategy entries: strategy pause failure",
                "Could not pause the order guard: guard pause failure",
            ],
        )
        self.assertEqual(runtime.logged[:3], result["warnings"])
        self.assertIn("No engines to stop.", runtime.logged)

    def test_stop_strategy_closes_futures_and_retains_live_engine_notice(self) -> None:
        runtime = _CloseRuntime()

        result = stop_strategy_sync(
            runtime,
            auth={"mode": "Testnet", "account_type": "Futures"},
        )

        engine = runtime.strategy_engines
        self.assertEqual({}, engine)
        self.assertEqual({}, runtime._engine_indicator_map)
        self.assertFalse(runtime._is_stopping_engines)
        self.assertEqual({"ok": True, "call": 1}, result["cancel_open_orders_result"])
        self.assertEqual({"ok": True, "call": 2}, result["cancel_open_orders_after_close"])
        self.assertEqual({"ok": True, "closed": 1}, result["close_all_result"])
        self.assertEqual([{"auth": {"mode": "Testnet", "account_type": "Futures"}, "fast": True}], runtime.close_calls)
        self.assertTrue(any("still shutting down" in message for message in runtime.logged))

    def test_stop_strategy_reports_close_setup_failure(self) -> None:
        class _BrokenCloseRuntime(_CloseRuntime):
            def _build_wrapper_from_values(self, auth: dict):
                del auth
                raise RuntimeError("wrapper unavailable")

        runtime = _BrokenCloseRuntime()
        result = stop_strategy_sync(runtime, auth={"account_type": "Futures"})

        self.assertFalse(result["ok"])
        self.assertEqual("wrapper unavailable", result["error"])
        self.assertIsNone(result["close_all_result"])
        self.assertTrue(any("Failed to trigger close-all" in message for message in runtime.logged))

    def test_blocking_async_stop_processes_warnings_close_result_and_state_sync(self) -> None:
        runtime = _AsyncRuntime()

        result = stop_strategy_async(
            runtime,
            close_positions=True,
            blocking=True,
            stop_strategy_sync_fn=lambda **kwargs: {
                "ok": True,
                "warnings": [f"cleanup used {kwargs['auth']['mode']}"],
                "close_all_result": {"ok": True},
                "_sync_runtime_state": True,
            },
        )

        self.assertTrue(result["ok"])
        self.assertEqual([{"ok": True}], runtime.close_results)
        self.assertEqual(1, runtime.sync_calls)
        self.assertTrue(any("cleanup used Testnet" in message for message in runtime.logged))

    def test_async_stop_without_a_helper_returns_visible_failure(self) -> None:
        runtime = _AsyncRuntime()

        result = stop_strategy_async(runtime, blocking=True)

        self.assertFalse(result["ok"])
        self.assertTrue(any("Stop strategy helper is not configured" in message for message in runtime.logged))


if __name__ == "__main__":
    unittest.main()
