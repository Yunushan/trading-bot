from __future__ import annotations

import sys
import unittest
from pathlib import Path
from types import SimpleNamespace


PYTHON_ROOT = Path(__file__).resolve().parents[1]
if str(PYTHON_ROOT) not in sys.path:
    sys.path.insert(0, str(PYTHON_ROOT))

from app.core.strategy.positions.strategy_position_futures_runtime import (  # noqa: E402
    _current_futures_position_qty,
)


class StrategyFuturesSnapshotSafetyTests(unittest.TestCase):
    def test_unknown_futures_snapshot_never_becomes_a_flat_position(self):
        strategy = SimpleNamespace(
            binance=SimpleNamespace(
                list_open_futures_positions=lambda **_kwargs: None,
            )
        )

        result = _current_futures_position_qty(strategy, "BTCUSDT", "BUY", "LONG")

        self.assertIsNone(result)

    def test_explicit_matching_hedge_snapshot_returns_only_the_requested_leg_quantity(self):
        strategy = SimpleNamespace(binance=SimpleNamespace())
        positions = [
            {"symbol": "BTCUSDT", "positionAmt": "0.7", "positionSide": "LONG"},
            {"symbol": "BTCUSDT", "positionAmt": "-0.4", "positionSide": "SHORT"},
        ]

        result = _current_futures_position_qty(strategy, "BTCUSDT", "BUY", "LONG", positions)

        self.assertEqual(0.7, result)


if __name__ == "__main__":
    unittest.main()
