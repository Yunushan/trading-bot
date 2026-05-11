from __future__ import annotations

import sys
import unittest
from pathlib import Path

PYTHON_ROOT = Path(__file__).resolve().parents[1]
if str(PYTHON_ROOT) not in sys.path:
    sys.path.insert(0, str(PYTHON_ROOT))

from trading_core.orders import order_submit_intent_from_params, validate_order_submit_intent  # noqa: E402


class TradingCoreOrderIntentTests(unittest.TestCase):
    def test_order_intent_validation_allows_futures_close_position_without_quantity(self):
        intent = order_submit_intent_from_params(
            "futures",
            {"symbol": "BTCUSDT", "side": "SELL", "type": "MARKET", "closePosition": True},
        )

        self.assertEqual((), validate_order_submit_intent(intent))

    def test_order_intent_validation_rejects_missing_required_fields(self):
        intent = order_submit_intent_from_params("spot", {"symbol": "", "side": "HOLD", "type": "MARKET"})

        errors = validate_order_submit_intent(intent)

        self.assertIn("order symbol is required", errors)
        self.assertIn("order side must be BUY or SELL", errors)
        self.assertIn("order quantity must be > 0", errors)

    def test_order_intent_validation_rejects_spot_close_position_and_reduce_only(self):
        intent = order_submit_intent_from_params(
            "spot",
            {"symbol": "BTCUSDT", "side": "SELL", "type": "MARKET", "closePosition": True, "reduceOnly": True},
        )

        errors = validate_order_submit_intent(intent)

        self.assertIn("closePosition orders are only supported for futures", errors)
        self.assertIn("reduceOnly orders are only supported for futures", errors)
        self.assertIn("closePosition and reduceOnly cannot be used together", errors)

    def test_order_intent_validation_requires_limit_price(self):
        intent = order_submit_intent_from_params(
            "futures",
            {"symbol": "BTCUSDT", "side": "BUY", "type": "LIMIT", "quantity": "0.1"},
        )

        self.assertIn("limit order price must be > 0", validate_order_submit_intent(intent))


if __name__ == "__main__":
    unittest.main()
