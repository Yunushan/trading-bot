from __future__ import annotations

import sys
import unittest
from pathlib import Path


PYTHON_ROOT = Path(__file__).resolve().parents[1]
if str(PYTHON_ROOT) not in sys.path:
    sys.path.insert(0, str(PYTHON_ROOT))

from app.core.strategy.positions.strategy_close_opposite_common_runtime import (  # noqa: E402
    _finalize_close_cleanup,
    _refresh_positions_snapshot,
)


class _UnknownSnapshotBinance:
    def list_open_futures_positions(self, **_kwargs):
        return None


class _CloseCleanupEngine:
    def __init__(self):
        self.binance = _UnknownSnapshotBinance()
        self._leg_ledger = {("BTCUSDT", "1h", "SELL"): {"qty": 1.0}}
        self.removed = []
        self.guarded = []
        self.logs = []

    def _remove_leg_entry(self, key, _order):
        self.removed.append(key)

    def _guard_mark_leg_closed(self, key):
        self.guarded.append(key)

    def log(self, message):
        self.logs.append(message)


class StrategyCloseOppositeSnapshotSafetyTests(unittest.TestCase):
    def test_refresh_rejects_an_explicitly_unknown_snapshot(self):
        engine = _CloseCleanupEngine()

        result = _refresh_positions_snapshot(engine, "BTCUSDT", "1h")

        self.assertIsNone(result)
        self.assertTrue(any("snapshot unavailable" in message for message in engine.logs))

    def test_cleanup_keeps_ledger_when_post_close_snapshot_is_unknown(self):
        engine = _CloseCleanupEngine()

        _finalize_close_cleanup(engine, "BTCUSDT", "SELL", 1e-9, True)

        self.assertEqual([], engine.removed)
        self.assertEqual([], engine.guarded)

