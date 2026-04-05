from __future__ import annotations

import copy
import sys
import unittest
from datetime import datetime
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from app.gui.positions.history_records_emit_runtime import build_raw_history_records  # noqa: E402
from app.gui.positions.history_records_group_runtime import group_history_records  # noqa: E402


class _ActiveHistoryWindowStub:
    def _parse_any_datetime(self, value):
        if isinstance(value, datetime):
            return value
        if isinstance(value, str):
            try:
                return datetime.fromisoformat(value)
            except Exception:
                return None
        return None

    def _canonicalize_interval(self, value):
        if value is None:
            return None
        return str(value).strip() or None


class ActiveHistoryReconciliationTests(unittest.TestCase):
    def test_distinct_active_allocations_with_same_interval_and_indicator_are_preserved(self):
        window = _ActiveHistoryWindowStub()
        open_records = {
            ("BTCUSDT", "L"): {
                "symbol": "BTCUSDT",
                "side_key": "L",
                "entry_tf": "1m",
                "open_time": "2026-04-05T12:20:00+00:00",
                "close_time": "-",
                "status": "Active",
                "data": {
                    "symbol": "BTCUSDT",
                    "side_key": "L",
                    "qty": 0.5,
                    "margin_usdt": 50.0,
                    "size_usdt": 500.0,
                    "entry_price": 100.0,
                    "leverage": 10,
                    "trigger_indicators": ["rsi"],
                },
                "indicators": ["rsi"],
                "stop_loss_enabled": False,
                "allocations": [
                    {
                        "trade_id": "trade-a",
                        "context_key": "1m:BUY:rsi|slot-a",
                        "slot_id": "slot-a",
                        "qty": 0.25,
                        "margin_usdt": 25.0,
                        "notional": 250.0,
                        "entry_price": 100.0,
                        "interval": "1m",
                        "interval_display": "1m",
                        "open_time": "2026-04-05T12:20:00+00:00",
                        "status": "Active",
                        "trigger_indicators": ["rsi"],
                    },
                    {
                        "trade_id": "trade-b",
                        "context_key": "1m:BUY:rsi|slot-b",
                        "slot_id": "slot-b",
                        "qty": 0.25,
                        "margin_usdt": 25.0,
                        "notional": 250.0,
                        "entry_price": 100.0,
                        "interval": "1m",
                        "interval_display": "1m",
                        "open_time": "2026-04-05T12:21:00+00:00",
                        "status": "Active",
                        "trigger_indicators": ["rsi"],
                    },
                ],
            }
        }

        raw_records = build_raw_history_records(
            window,
            open_records,
            [],
            {},
            normalize_indicator_values=lambda values: [
                str(value).strip()
                for value in (values or [])
                if str(value).strip()
            ],
            derive_margin_snapshot=lambda *_args, **_kwargs: (0.0, 0.0, 0.0, 0.0),
        )
        grouped = group_history_records(window, raw_records, {"closed", "liquidated"})
        active_rows = [
            record
            for record in grouped
            if str(record.get("status") or "").lower() == "active"
        ]

        self.assertEqual(2, len(active_rows))
        self.assertEqual(
            {"trade-a", "trade-b"},
            {str((record.get("allocations") or [{}])[0].get("trade_id") or "") for record in active_rows},
        )
        self.assertEqual(
            {
                "trade-a|slot-a|1m:BUY:rsi|slot-a|2026-04-05T12:20:00+00:00|rsi",
                "trade-b|slot-b|1m:BUY:rsi|slot-b|2026-04-05T12:21:00+00:00|rsi",
            },
            {str(record.get("_aggregate_key") or "") for record in active_rows},
        )

    def test_named_active_rows_keep_stable_order_for_reversed_input(self):
        window = _ActiveHistoryWindowStub()

        def _named_entry(*, trade_id: str, slot_id: str, open_time: str) -> dict:
            return {
                "symbol": "BTCUSDT",
                "side_key": "L",
                "entry_tf": "1m",
                "open_time": open_time,
                "close_time": "-",
                "status": "Active",
                "data": {
                    "symbol": "BTCUSDT",
                    "side_key": "L",
                    "qty": 0.25,
                    "margin_usdt": 25.0,
                    "size_usdt": 250.0,
                    "entry_price": 100.0,
                    "leverage": 10,
                    "trigger_desc": trade_id,
                    "trigger_indicators": ["rsi"],
                },
                "indicators": ["rsi"],
                "allocations": [
                    {
                        "trade_id": trade_id,
                        "client_order_id": f"client-{trade_id}",
                        "context_key": f"1m:BUY:rsi|{slot_id}",
                        "slot_id": slot_id,
                        "qty": 0.25,
                        "margin_usdt": 25.0,
                        "notional": 250.0,
                        "entry_price": 100.0,
                        "interval": "1m",
                        "interval_display": "1m",
                        "open_time": open_time,
                        "status": "Active",
                        "trigger_indicators": ["rsi"],
                    }
                ],
                "_aggregate_key": f"{trade_id}|{slot_id}|1m:BUY:rsi|{slot_id}|{open_time}|rsi",
                "_aggregate_is_primary": True,
            }

        first = _named_entry(
            trade_id="trade-a",
            slot_id="slot-a",
            open_time="2026-04-05T12:20:00+00:00",
        )
        second = _named_entry(
            trade_id="trade-b",
            slot_id="slot-b",
            open_time="2026-04-05T12:21:00+00:00",
        )

        forward = group_history_records(
            window,
            [copy.deepcopy(second), copy.deepcopy(first)],
            {"closed", "liquidated"},
        )
        reverse = group_history_records(
            window,
            [copy.deepcopy(first), copy.deepcopy(second)],
            {"closed", "liquidated"},
        )

        self.assertEqual(forward, reverse)
        self.assertEqual(
            ["trade-a", "trade-b"],
            [
                str((record.get("allocations") or [{}])[0].get("trade_id") or "")
                for record in forward
                if str(record.get("status") or "").lower() == "active"
            ],
        )

    def test_unnamed_active_tie_break_is_deterministic(self):
        window = _ActiveHistoryWindowStub()

        def _unnamed_entry(*, open_time: str, trigger_desc: str) -> dict:
            return {
                "symbol": "BTCUSDT",
                "side_key": "L",
                "entry_tf": "1m",
                "open_time": open_time,
                "close_time": "-",
                "status": "Active",
                "data": {
                    "symbol": "BTCUSDT",
                    "side_key": "L",
                    "qty": 0.25,
                    "margin_usdt": 25.0,
                    "size_usdt": 250.0,
                    "entry_price": 100.0,
                    "leverage": 10,
                    "trigger_desc": trigger_desc,
                    "trigger_indicators": ["rsi"],
                },
                "indicators": ["rsi"],
                "allocations": [
                    {
                        "qty": 0.25,
                        "margin_usdt": 25.0,
                        "notional": 250.0,
                        "interval": "1m",
                        "interval_display": "1m",
                        "open_time": open_time,
                        "status": "Active",
                        "trigger_indicators": ["rsi"],
                    }
                ],
            }

        early = _unnamed_entry(
            open_time="2026-04-05T12:20:00+00:00",
            trigger_desc="alpha",
        )
        late = _unnamed_entry(
            open_time="2026-04-05T12:21:00+00:00",
            trigger_desc="beta",
        )

        forward = group_history_records(
            window,
            [copy.deepcopy(late), copy.deepcopy(early)],
            {"closed", "liquidated"},
        )
        reverse = group_history_records(
            window,
            [copy.deepcopy(early), copy.deepcopy(late)],
            {"closed", "liquidated"},
        )

        self.assertEqual(forward, reverse)
        self.assertEqual(1, len(forward))
        self.assertEqual("2026-04-05T12:20:00+00:00", forward[0]["open_time"])
        self.assertEqual("alpha", forward[0]["data"]["trigger_desc"])


if __name__ == "__main__":
    unittest.main()
