from __future__ import annotations

import copy
import sys
import unittest
from datetime import datetime
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from app.gui.positions.positions_cumulative_runtime import _mw_positions_records_cumulative  # noqa: E402


class _CumulativeWindowStub:
    def _parse_any_datetime(self, value):
        if isinstance(value, datetime):
            return value
        if isinstance(value, str):
            try:
                return datetime.fromisoformat(value)
            except Exception:
                return None
        return None

    def _format_display_time(self, value) -> str:
        if isinstance(value, datetime):
            return value.isoformat(timespec="seconds")
        return str(value)


def _entry(
    *,
    interval: str,
    open_time: str,
    trade_id: str,
    slot_id: str,
    trigger_desc: str,
    liquidation_price: float,
) -> dict:
    return {
        "symbol": "BTCUSDT",
        "side_key": "L",
        "entry_tf": interval,
        "open_time": open_time,
        "close_time": "-",
        "status": "Active",
        "liquidation_price": liquidation_price,
        "data": {
            "symbol": "BTCUSDT",
            "side_key": "L",
            "interval_display": interval,
            "interval": interval,
            "open_time": open_time,
            "qty": 0.25,
            "margin_usdt": 25.0,
            "size_usdt": 250.0,
            "pnl_value": 5.0,
            "entry_price": 100.0,
            "leverage": 10,
            "trigger_desc": trigger_desc,
            "trigger_indicators": ["rsi"],
        },
        "allocations": [
            {
                "trade_id": trade_id,
                "client_order_id": f"client-{trade_id}",
                "context_key": f"{interval}:BUY:rsi|{slot_id}",
                "slot_id": slot_id,
                "qty": 0.25,
                "margin_usdt": 25.0,
                "notional": 250.0,
                "interval": interval,
                "interval_display": interval,
                "open_time": open_time,
                "status": "Active",
                "trigger_indicators": ["rsi"],
            }
        ],
    }


class CumulativeViewStabilityTests(unittest.TestCase):
    def test_equal_metric_entries_aggregate_deterministically(self):
        window = _CumulativeWindowStub()
        first = _entry(
            interval="1m",
            open_time="2026-04-05T12:20:00+00:00",
            trade_id="trade-a",
            slot_id="slot-a",
            trigger_desc="alpha",
            liquidation_price=90.0,
        )
        second = _entry(
            interval="5m",
            open_time="2026-04-05T12:21:00+00:00",
            trade_id="trade-b",
            slot_id="slot-b",
            trigger_desc="beta",
            liquidation_price=91.0,
        )

        forward = _mw_positions_records_cumulative(window, [copy.deepcopy(second), copy.deepcopy(first)], [])
        reverse = _mw_positions_records_cumulative(window, [copy.deepcopy(first), copy.deepcopy(second)], [])

        self.assertEqual(forward, reverse)
        self.assertEqual(1, len(forward))
        record = forward[0]
        self.assertEqual("1m, 5m", record["entry_tf"])
        self.assertEqual("1m", record["data"]["interval_display"])
        self.assertEqual("1m", record["data"]["interval"])
        self.assertEqual("2026-04-05T12:20:00+00:00", record["open_time"])
        self.assertEqual("2026-04-05T12:20:00+00:00", record["data"]["open_time"])
        self.assertEqual("alpha", record["data"]["trigger_desc"])
        self.assertEqual(90.0, record["liquidation_price"])
        self.assertEqual(
            ["trade-a", "trade-b"],
            [
                aggregated_entry["allocations"][0]["trade_id"]
                for aggregated_entry in record["_aggregated_entries"]
            ],
        )

    def test_summary_interval_metadata_uses_canonical_first_interval(self):
        window = _CumulativeWindowStub()
        first = _entry(
            interval="15m",
            open_time="2026-04-05T12:40:00+00:00",
            trade_id="trade-c",
            slot_id="slot-c",
            trigger_desc="gamma",
            liquidation_price=88.0,
        )
        second = _entry(
            interval="1m",
            open_time="2026-04-05T12:10:00+00:00",
            trade_id="trade-a",
            slot_id="slot-a",
            trigger_desc="alpha",
            liquidation_price=89.0,
        )
        third = _entry(
            interval="5m",
            open_time="2026-04-05T12:20:00+00:00",
            trade_id="trade-b",
            slot_id="slot-b",
            trigger_desc="beta",
            liquidation_price=87.0,
        )

        records = _mw_positions_records_cumulative(
            window,
            [copy.deepcopy(first), copy.deepcopy(second), copy.deepcopy(third)],
            [],
        )

        self.assertEqual(1, len(records))
        record = records[0]
        self.assertEqual("1m, 5m, 15m", record["entry_tf"])
        self.assertEqual("1m", record["data"]["interval_display"])
        self.assertEqual("1m", record["data"]["interval"])
        self.assertEqual("2026-04-05T12:10:00+00:00", record["open_time"])
        self.assertEqual(
            ["trade-a", "trade-b", "trade-c"],
            [
                aggregated_entry["allocations"][0]["trade_id"]
                for aggregated_entry in record["_aggregated_entries"]
            ],
        )


if __name__ == "__main__":
    unittest.main()
