from __future__ import annotations

import copy
import sys
import unittest
from datetime import datetime
from pathlib import Path
from typing import Any


PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from app.gui.positions.actions_state_runtime import reduce_local_position_allocation_state  # noqa: E402
from app.gui.positions.table_render_prepare_runtime import _prepare_record_snapshot  # noqa: E402


class _ManualCloseWindowStub:
    def __init__(self) -> None:
        self._entry_allocations: dict[tuple[str, str], list[dict]] = {}
        self._open_position_records: dict[tuple[str, str], dict] = {}
        self._entry_intervals: dict[str, dict[str, set[str]]] = {}
        self._entry_times: dict[tuple[str, str], str] = {}
        self._entry_times_by_iv: dict[tuple[str, str, str], str] = {}

    def _canonicalize_interval(self, value):
        if value is None:
            return None
        return str(value).strip() or None

    def _parse_any_datetime(self, value):
        if isinstance(value, datetime):
            return value
        if isinstance(value, str):
            try:
                return datetime.fromisoformat(value)
            except Exception:
                return None
        return None


def _active_allocation(*, trade_id: str, slot_id: str, open_time: str) -> dict:
    return {
        "trade_id": trade_id,
        "client_order_id": f"client-{trade_id}",
        "context_key": f"1m:BUY:rsi|{slot_id}",
        "slot_id": slot_id,
        "qty": 0.25,
        "margin_usdt": 25.0,
        "notional": 250.0,
        "interval": "1m",
        "interval_display": "1m",
        "open_time": open_time,
        "status": "Active",
        "trigger_indicators": ["rsi"],
    }


class ManualCloseReconciliationTests(unittest.TestCase):
    def test_manual_close_reduces_targeted_same_interval_allocation_only(self):
        window = _ManualCloseWindowStub()
        first = _active_allocation(
            trade_id="trade-a",
            slot_id="slot-a",
            open_time="2026-04-05T12:20:00+00:00",
        )
        second = _active_allocation(
            trade_id="trade-b",
            slot_id="slot-b",
            open_time="2026-04-05T12:21:00+00:00",
        )
        key = ("BTCUSDT", "L")
        window._entry_allocations[key] = [copy.deepcopy(first), copy.deepcopy(second)]
        window._open_position_records[key] = {
            "symbol": "BTCUSDT",
            "side_key": "L",
            "entry_tf": "1m",
            "open_time": "2026-04-05T12:20:00+00:00",
            "status": "Active",
            "data": {"qty": 0.5},
            "allocations": [copy.deepcopy(first), copy.deepcopy(second)],
        }
        window._entry_intervals = {"BTCUSDT": {"L": {"1m"}, "S": set()}}
        window._entry_times[key] = "2026-04-05T12:20:00+00:00"
        window._entry_times_by_iv[("BTCUSDT", "L", "1m")] = "2026-04-05T12:20:00+00:00"

        changed = reduce_local_position_allocation_state(
            window,
            "BTCUSDT",
            "L",
            interval="1m",
            qty=0.25,
            target_identity={
                "trade_id": "trade-a",
                "context_key": "1m:BUY:rsi|slot-a",
                "slot_id": "slot-a",
                "open_time": "2026-04-05T12:20:00+00:00",
            },
        )

        self.assertTrue(changed)
        survivors = window._entry_allocations[key]
        self.assertEqual(1, len(survivors))
        self.assertEqual("trade-b", survivors[0]["trade_id"])
        self.assertEqual({"1m"}, window._entry_intervals["BTCUSDT"]["L"])
        self.assertEqual(
            "2026-04-05T12:21:00+00:00",
            window._entry_times[key],
        )
        self.assertEqual(
            "2026-04-05T12:21:00+00:00",
            window._entry_times_by_iv[("BTCUSDT", "L", "1m")],
        )
        open_record_allocs = window._open_position_records[key]["allocations"]
        self.assertEqual(1, len(open_record_allocs))
        self.assertEqual("trade-b", open_record_allocs[0]["trade_id"])

    def test_manual_close_clears_interval_tracking_when_last_leg_closes(self):
        window = _ManualCloseWindowStub()
        only_entry = _active_allocation(
            trade_id="trade-a",
            slot_id="slot-a",
            open_time="2026-04-05T12:20:00+00:00",
        )
        key = ("BTCUSDT", "L")
        window._entry_allocations[key] = [copy.deepcopy(only_entry)]
        window._open_position_records[key] = {
            "symbol": "BTCUSDT",
            "side_key": "L",
            "entry_tf": "1m",
            "open_time": "2026-04-05T12:20:00+00:00",
            "status": "Active",
            "data": {"qty": 0.25},
            "allocations": [copy.deepcopy(only_entry)],
        }
        window._entry_intervals = {"BTCUSDT": {"L": {"1m"}, "S": set()}}
        window._entry_times[key] = "2026-04-05T12:20:00+00:00"
        window._entry_times_by_iv[("BTCUSDT", "L", "1m")] = "2026-04-05T12:20:00+00:00"

        changed = reduce_local_position_allocation_state(
            window,
            "BTCUSDT",
            "L",
            interval="1m",
            qty=0.25,
            target_identity={"trade_id": "trade-a", "slot_id": "slot-a"},
        )

        self.assertTrue(changed)
        self.assertNotIn(key, window._entry_allocations)
        self.assertNotIn(key, window._open_position_records)
        self.assertNotIn("BTCUSDT", window._entry_intervals)
        self.assertNotIn(key, window._entry_times)
        self.assertNotIn(("BTCUSDT", "L", "1m"), window._entry_times_by_iv)

    def test_render_snapshot_changes_when_only_trade_identity_changes(self):
        class _SnapshotWindow:
            pass

        base_record: dict[str, Any] = {
            "symbol": "BTCUSDT",
            "side_key": "L",
            "entry_tf": "1m",
            "status": "Active",
            "data": {
                "qty": 0.25,
                "margin_usdt": 25.0,
                "pnl_value": 0.0,
            },
            "allocations": [
                {
                    "trade_id": "trade-a",
                    "context_key": "1m:BUY:rsi|slot-a",
                    "slot_id": "slot-a",
                    "open_time": "2026-04-05T12:20:00+00:00",
                    "qty": 0.25,
                    "interval": "1m",
                    "interval_display": "1m",
                    "status": "Active",
                }
            ],
        }
        other_record: dict[str, Any] = copy.deepcopy(base_record)
        other_allocations = other_record.get("allocations")
        assert isinstance(other_allocations, list)
        first_allocation = other_allocations[0]
        assert isinstance(first_allocation, dict)
        first_allocation["trade_id"] = "trade-b"
        first_allocation["context_key"] = "1m:BUY:rsi|slot-b"
        first_allocation["slot_id"] = "slot-b"
        first_allocation["open_time"] = "2026-04-05T12:21:00+00:00"

        first_snapshot = _prepare_record_snapshot(
            _SnapshotWindow(),
            base_record,
            view_mode="per_trade",
            live_value_cache={},
        )
        second_snapshot = _prepare_record_snapshot(
            _SnapshotWindow(),
            other_record,
            view_mode="per_trade",
            live_value_cache={},
        )

        self.assertNotEqual(first_snapshot, second_snapshot)


if __name__ == "__main__":
    unittest.main()
