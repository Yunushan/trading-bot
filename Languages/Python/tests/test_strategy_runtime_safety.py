from __future__ import annotations

import sys
import unittest
from pathlib import Path
from types import SimpleNamespace


PYTHON_ROOT = Path(__file__).resolve().parents[1]
if str(PYTHON_ROOT) not in sys.path:
    sys.path.insert(0, str(PYTHON_ROOT))

from app.core.strategy.runtime.strategy_runtime import _fetch_cycle_market_state  # noqa: E402
from app.core.strategy.positions.strategy_position_flip_runtime import (  # noqa: E402
    _reconcile_liquidations,
)


class _LiveReconciliationFailureStrategy:
    def __init__(self) -> None:
        self.config = {"symbol": "BTCUSDT", "interval": "1m", "lookback": 200}
        self.binance = SimpleNamespace(mode="Live")
        self.logs: list[str] = []
        self.market_reads = 0

    def stopped(self) -> bool:
        return False

    def _reconcile_liquidations(self, _symbol: str) -> None:
        raise RuntimeError("exchange unavailable")

    def log(self, message: str) -> None:
        self.logs.append(message)

    def get_klines(self, *_args, **_kwargs):
        self.market_reads += 1
        raise AssertionError("live cycle must not fetch market data after reconciliation failure")


class _LiveSnapshotFailureStrategy:
    def __init__(self, snapshot) -> None:
        self.binance = SimpleNamespace(
            mode="Live",
            list_open_futures_positions=lambda **_kwargs: snapshot,
            get_futures_dual_side=lambda: False,
        )
        self._reconcile_miss_counts: dict[str, int] = {}
        self._leg_ledger: dict[object, object] = {}


class StrategyRuntimeSafetyTests(unittest.TestCase):
    def test_live_cycle_blocks_before_market_read_when_liquidation_reconciliation_fails(self):
        strategy = _LiveReconciliationFailureStrategy()

        result = _fetch_cycle_market_state(strategy, ctx={"cw": strategy.config})

        self.assertIsNone(result)
        self.assertEqual(0, strategy.market_reads)
        self.assertTrue(any("live cycle blocked" in message for message in strategy.logs))

    def test_liquidation_reconciliation_rejects_unavailable_live_position_snapshot(self):
        strategy = _LiveSnapshotFailureStrategy(None)

        with self.assertRaisesRegex(RuntimeError, "snapshot was unavailable"):
            _reconcile_liquidations(strategy, "BTCUSDT")

    def test_liquidation_reconciliation_rejects_malformed_live_position_amount(self):
        strategy = _LiveSnapshotFailureStrategy(
            [{"symbol": "BTCUSDT", "positionAmt": "not-a-number"}]
        )

        with self.assertRaisesRegex(RuntimeError, "invalid amount"):
            _reconcile_liquidations(strategy, "BTCUSDT")


if __name__ == "__main__":
    unittest.main()
