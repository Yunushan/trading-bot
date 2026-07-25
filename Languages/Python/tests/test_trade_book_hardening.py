from __future__ import annotations

import sys
import unittest
from pathlib import Path


PYTHON_ROOT = Path(__file__).resolve().parents[1]
if str(PYTHON_ROOT) not in sys.path:
    sys.path.insert(0, str(PYTHON_ROOT))

from app.config import build_default_config  # noqa: E402
from app.core.strategy import StrategyEngine  # noqa: E402


class _FakeBinance:
    account_type = "FUTURES"

    def get_futures_dual_side(self):
        return False


def _build_engine() -> StrategyEngine:
    config = build_default_config()
    config["symbol"] = "BTCUSDT"
    config["interval"] = "1m"
    return StrategyEngine(_FakeBinance(), config, log_callback=lambda _message: None)


class TradeBookHardeningTests(unittest.TestCase):
    def test_valid_trade_book_quantities_still_aggregate(self):
        engine = _build_engine()
        key = engine._trade_book_key("BTCUSDT", "1m", "rsi", "BUY")
        self.assertIsNotNone(key)
        engine._trade_book[key] = {
            "ledger-1": {"qty": "0.25"},
            "ledger-2": {"qty": 0.75},
        }

        total = engine._trade_book_total_qty("BTCUSDT", "1m", "rsi", "BUY")

        self.assertEqual(1.0, total)

    def test_corrupt_trade_book_quantity_is_not_treated_as_flat(self):
        engine = _build_engine()
        key = engine._trade_book_key("BTCUSDT", "1m", "rsi", "BUY")
        self.assertIsNotNone(key)
        engine._trade_book[key] = {"ledger-1": {"qty": "not-a-number"}}

        with self.assertRaisesRegex(ValueError, "trade-book quantity must be numeric"):
            engine._trade_book_total_qty("BTCUSDT", "1m", "rsi", "BUY")

    def test_nonfinite_trade_book_quantity_is_rejected(self):
        engine = _build_engine()
        key = engine._trade_book_key("BTCUSDT", "1m", "rsi", "BUY")
        self.assertIsNotNone(key)
        engine._trade_book[key] = {"ledger-1": {"qty": float("inf")}}

        with self.assertRaisesRegex(ValueError, "trade-book quantity must be finite"):
            engine._trade_book_has_entries("BTCUSDT", "1m", "rsi", "BUY")

    def test_corrupt_primary_ledger_quantity_is_not_ignored(self):
        engine = _build_engine()
        key = ("BTCUSDT", "5m", "BUY")
        engine._leg_ledger[key] = {
            "entries": [
                {
                    "qty": "invalid",
                    "ledger_id": "ledger-1",
                    "indicator_keys": ["macd"],
                }
            ]
        }

        with self.assertRaisesRegex(ValueError, "ledger entry quantity must be numeric"):
            engine._symbol_side_has_other_positions("BTCUSDT", "1m", "rsi", "BUY")

    def test_exchange_position_mode_failure_propagates(self):
        engine = _build_engine()

        def fail_position_mode():
            raise RuntimeError("position mode unavailable")

        engine.binance.get_futures_dual_side = fail_position_mode

        with self.assertRaisesRegex(RuntimeError, "position mode unavailable"):
            engine._indicator_live_qty_total("BTCUSDT", "1m", "rsi", "BUY")

    def test_exchange_position_quantity_failure_propagates(self):
        engine = _build_engine()

        def fail_position_quantity(*_args, **_kwargs):
            raise RuntimeError("position quantity unavailable")

        engine._current_futures_position_qty = fail_position_quantity

        with self.assertRaisesRegex(RuntimeError, "position quantity unavailable"):
            engine._indicator_live_qty_total("BTCUSDT", "1m", "rsi", "BUY")

    def test_unavailable_exchange_position_quantity_is_not_treated_as_flat(self):
        engine = _build_engine()
        engine._current_futures_position_qty = lambda *_args, **_kwargs: None

        with self.assertRaisesRegex(RuntimeError, "exchange position quantity is unavailable"):
            engine._indicator_live_qty_total("BTCUSDT", "1m", "rsi", "BUY")


if __name__ == "__main__":
    unittest.main()
