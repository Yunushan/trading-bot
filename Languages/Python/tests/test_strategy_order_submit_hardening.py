from __future__ import annotations

import threading
import unittest

from app.core.strategy.orders.strategy_signal_order_submit_runtime import (
    _record_connector_order_block,
)


class _BrokenPauseEvent:
    def set(self) -> None:
        raise RuntimeError("pause event unavailable")


def _strategy_type(pause_event):
    class _Strategy:
        _CONNECTOR_ORDER_BLOCK_LOCK = threading.Lock()
        _CONNECTOR_ORDER_BLOCK_EVENTS: list[dict[str, object]] = []
        _CONNECTOR_ORDER_CIRCUIT_OPEN = False
        _GLOBAL_PAUSE = pause_event

        def __init__(self) -> None:
            self.config = {
                "connector_order_block_circuit_breaker_enabled": True,
                "connector_order_block_pause_threshold": 1,
                "connector_order_block_window_seconds": 30.0,
            }
            self.logs: list[str] = []

        def log(self, message: str, *, lvl: str = "info") -> None:
            self.logs.append(f"{lvl}:{message}")

    return _Strategy


def _record(strategy) -> bool:
    return _record_connector_order_block(
        strategy,
        cw={"symbol": "BTCUSDT", "interval": "1m"},
        side="BUY",
        account_type="FUTURES",
        connector_message="network offline",
        connector_snapshot={"health": "error", "state": "network_offline"},
        context_key="1m:BUY:rsi",
        signature=("rsi",),
    )


class StrategyOrderSubmitHardeningTests(unittest.TestCase):
    def test_circuit_remains_retryable_when_global_pause_event_fails(self):
        strategy_class = _strategy_type(_BrokenPauseEvent())
        strategy = strategy_class()

        self.assertFalse(_record(strategy))
        self.assertFalse(strategy_class._CONNECTOR_ORDER_CIRCUIT_OPEN)
        self.assertTrue(any("failed to pause trading" in message for message in strategy.logs))
        self.assertTrue(any("pause event unavailable" in message for message in strategy.logs))

    def test_circuit_callback_failure_is_structured_and_does_not_undo_pause(self):
        pause_event = threading.Event()
        strategy_class = _strategy_type(pause_event)
        strategy = strategy_class()

        def fail_callback(_payload) -> None:
            raise RuntimeError("callback unavailable")

        strategy.connector_order_circuit_breaker_callback = fail_callback

        self.assertTrue(_record(strategy))
        self.assertTrue(pause_event.is_set())
        self.assertTrue(strategy_class._CONNECTOR_ORDER_CIRCUIT_OPEN)
        self.assertTrue(any("circuit callback failed" in message for message in strategy.logs))
        self.assertTrue(any("callback unavailable" in message for message in strategy.logs))


if __name__ == "__main__":
    unittest.main()
