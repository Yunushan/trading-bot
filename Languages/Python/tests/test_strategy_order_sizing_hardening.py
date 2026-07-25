from __future__ import annotations

import math
import unittest
from types import SimpleNamespace

from app.core.strategy.orders.strategy_signal_order_sizing_runtime import (
    _prepare_futures_signal_order_state,
)


class StrategyOrderSizingHardeningTests(unittest.TestCase):
    def _prepare_with_margin_state(self, margin_state: dict[str, object]):
        logs: list[str] = []
        aborts: list[bool] = []
        position_gate_calls: list[bool] = []
        runtime = SimpleNamespace(
            config={"leverage": 5},
            log=lambda message: logs.append(str(message)),
            _prepare_signal_order_slot_state=lambda **_kwargs: {"aborted": False},
            _prepare_signal_order_margin_state=lambda **_kwargs: dict(margin_state),
            _prepare_signal_order_position_gate=lambda **_kwargs: position_gate_calls.append(True)
            or {"aborted": False},
        )

        result = _prepare_futures_signal_order_state(
            runtime,
            cw={"symbol": "BTCUSDT", "interval": "1m", "leverage": 5},
            side="BUY",
            interval_norm="1m",
            signature=("rsi",),
            trigger_labels=["RSI"],
            context_key="1m:BUY:rsi",
            indicator_key_hint="rsi",
            indicator_tokens_for_order=["rsi"],
            indicator_tokens_for_guard=["rsi"],
            flip_active=False,
            flip_close_qty=0.0,
            qty_tol_slot_guard=0.0,
            free_usdt=1000.0,
            price=100.0,
            pct=0.1,
            futures_balance_snap={"available": 1000.0, "wallet": 1000.0},
            abort_guard=lambda: aborts.append(True),
        )
        return result, logs, aborts, position_gate_calls

    def test_invalid_margin_gate_leverage_aborts_before_position_gate(self):
        for leverage in (None, "invalid", 0, -1, math.inf):
            with self.subTest(leverage=leverage):
                result, logs, aborts, position_gate_calls = self._prepare_with_margin_state(
                    {"aborted": False, "lev": leverage, "qty_est": 1.0}
                )
                self.assertTrue(result["aborted"])
                self.assertEqual([True], aborts)
                self.assertEqual([], position_gate_calls)
                self.assertTrue(any("invalid leverage" in message for message in logs))

    def test_invalid_margin_gate_quantity_aborts_before_position_gate(self):
        for quantity in (None, "invalid", 0.0, -1.0, math.nan, math.inf, -math.inf):
            with self.subTest(quantity=quantity):
                result, logs, aborts, position_gate_calls = self._prepare_with_margin_state(
                    {"aborted": False, "lev": 5, "qty_est": quantity}
                )
                self.assertTrue(result["aborted"])
                self.assertEqual([True], aborts)
                self.assertEqual([], position_gate_calls)
                self.assertTrue(any("invalid quantity" in message for message in logs))


if __name__ == "__main__":
    unittest.main()
