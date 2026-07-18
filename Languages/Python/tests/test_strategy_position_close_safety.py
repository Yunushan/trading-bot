from __future__ import annotations

import sys
import unittest
from pathlib import Path
from types import SimpleNamespace


PYTHON_ROOT = Path(__file__).resolve().parents[1]
if str(PYTHON_ROOT) not in sys.path:
    sys.path.insert(0, str(PYTHON_ROOT))

from app.core.strategy.positions.strategy_position_close_runtime import (  # noqa: E402
    _close_indicator_positions,
)


class _CloseStrategy:
    def __init__(self, *, require_signal: bool = False, guard_available: bool = True, fail_close: bool = False):
        self.config = {
            "allow_opposite_positions": False,
            "require_indicator_flip_signal": require_signal,
            "strict_indicator_flip_enforcement": require_signal,
            "allow_indicator_close_without_signal": False,
        }
        self.binance = SimpleNamespace(get_futures_dual_side=lambda: False)
        self.leg_key = ("BTCUSDT", "1h", "BUY")
        self.entry = {
            "ledger_id": "ledger-1",
            "timestamp": 0.0,
            "qty": 1.0,
            "trigger_indicators": ["rsi"],
        }
        self._ledger_index = {"ledger-1": self.leg_key}
        self._leg_ledger = {self.leg_key: {}}
        self.guard_available = guard_available
        self.fail_close = fail_close
        self.close_calls: list[dict[str, object]] = []
        self.logs: list[str] = []
        self.guard_exits: list[tuple[str, str]] = []

    @staticmethod
    def _canonical_indicator_token(value: object) -> str:
        return str(value or "").strip().lower()

    @staticmethod
    def _strategy_coerce_bool(value: object, default: bool) -> bool:
        if value is None:
            return default
        if isinstance(value, bool):
            return value
        return str(value).strip().lower() in {"1", "true", "yes", "on"}

    @staticmethod
    def _tokenize_interval_label(value: object) -> set[str]:
        return {str(value or "-").strip().lower() or "-"}

    def _trade_book_entries(self, *_args):
        return [self.entry]

    @staticmethod
    def _indicator_entry_matches_close(_entry, _indicator, **_kwargs) -> bool:
        return True

    @staticmethod
    def _indicator_get_ledger_ids(*_args) -> list[str]:
        return []

    def _enter_close_guard(self, *_args) -> bool:
        return self.guard_available

    @staticmethod
    def _describe_close_guard(_symbol: str) -> dict[str, str]:
        return {"side": "BUY", "label": "existing-close"}

    def _exit_close_guard(self, symbol: str, side: str) -> None:
        self.guard_exits.append((symbol, side))

    def _leg_entries(self, leg_key):
        return [self.entry] if leg_key == self.leg_key else []

    @staticmethod
    def _interval_seconds_value(_interval: str) -> float:
        return 3600.0

    @staticmethod
    def _indicator_hold_ready(*_args, **_kwargs) -> bool:
        return True

    @staticmethod
    def _current_futures_position_qty(*_args) -> float:
        return 1.0

    def _close_leg_entry(self, _cw, _leg_key, _entry, side, close_side, position_side, **kwargs) -> float:
        self.close_calls.append(
            {
                "side": side,
                "close_side": close_side,
                "position_side": position_side,
                "qty_limit": kwargs.get("qty_limit"),
            }
        )
        if self.fail_close:
            raise RuntimeError("simulated close transport failure")
        qty_limit = kwargs.get("qty_limit")
        return float(qty_limit) if qty_limit is not None else 1.0

    def log(self, message: str) -> None:
        self.logs.append(message)


class StrategyPositionCloseSafetyTests(unittest.TestCase):
    def _close(self, strategy: _CloseStrategy, **kwargs):
        return _close_indicator_positions(
            strategy,
            {"symbol": "BTCUSDT", "interval": "1h"},
            "1h",
            "rsi",
            "BUY",
            "LONG",
            **kwargs,
        )

    def test_signal_requirement_blocks_close_before_any_guard_or_order_attempt(self):
        strategy = _CloseStrategy(require_signal=True)

        result = self._close(strategy)

        self.assertEqual((0, 0.0), result)
        self.assertEqual([], strategy.close_calls)
        self.assertEqual([], strategy.guard_exits)

    def test_active_close_guard_blocks_a_second_close_attempt(self):
        strategy = _CloseStrategy(guard_available=False)

        result = self._close(strategy)

        self.assertEqual((0, 0.0), result)
        self.assertEqual([], strategy.close_calls)
        self.assertTrue(any("close skipped" in message for message in strategy.logs))

    def test_ledger_close_preserves_requested_quantity_cap_and_side(self):
        strategy = _CloseStrategy()

        result = self._close(strategy, signature_hint=("rsi",), qty_limit=0.25, reason="indicator_flip")

        self.assertEqual((1, 0.25), result)
        self.assertEqual(1, len(strategy.close_calls))
        self.assertEqual("BUY", strategy.close_calls[0]["side"])
        self.assertEqual("SELL", strategy.close_calls[0]["close_side"])
        self.assertEqual("LONG", strategy.close_calls[0]["position_side"])
        self.assertEqual(0.25, strategy.close_calls[0]["qty_limit"])
        self.assertEqual([("BTCUSDT", "BUY")], strategy.guard_exits)

    def test_fallback_close_entry_failure_is_logged_and_never_escapes_strategy_cycle(self):
        strategy = _CloseStrategy(fail_close=True)

        result = self._close(strategy, signature_hint=("rsi",))

        self.assertEqual((0, 0.0), result)
        self.assertGreaterEqual(len(strategy.close_calls), 2)
        self.assertTrue(any("fallback close skipped" in message for message in strategy.logs))
        self.assertEqual([("BTCUSDT", "BUY")], strategy.guard_exits)


if __name__ == "__main__":
    unittest.main()
