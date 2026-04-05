from __future__ import annotations

import sys
import unittest
from datetime import datetime
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from app.gui.positions.history_records_runtime import _mw_positions_records_per_trade  # noqa: E402
from app.gui.positions.record_build_helpers import _seed_positions_map_from_rows  # noqa: E402


def _allocation(*, trade_id: str, slot_id: str, open_time: str) -> dict:
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


class _RefreshWindowStub:
    def __init__(self) -> None:
        self._pending_close_times: dict[tuple[str, str], str] = {}
        self._engine_indicator_map: dict = {}
        self._entry_times: dict[tuple[str, str], str] = {}
        self._entry_times_by_iv: dict[tuple[str, str, str], str] = {}
        self._entry_intervals: dict[str, dict[str, set[str]]] = {}

    def _position_stop_loss_enabled(self, *_args, **_kwargs) -> bool:
        return False

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

    def _format_display_time(self, value) -> str:
        if isinstance(value, datetime):
            return value.isoformat(timespec="seconds")
        return str(value)


class RefreshIdentityStabilityTests(unittest.TestCase):
    def test_seed_positions_map_sorts_allocations_by_identity(self):
        window = _RefreshWindowStub()
        alloc_map_global = {
            ("BTCUSDT", "L"): [
                _allocation(
                    trade_id="trade-b",
                    slot_id="slot-b",
                    open_time="2026-04-05T12:21:00+00:00",
                ),
                _allocation(
                    trade_id="trade-a",
                    slot_id="slot-a",
                    open_time="2026-04-05T12:20:00+00:00",
                ),
            ]
        }
        base_rows = [
            {
                "symbol": "BTCUSDT",
                "side_key": "L",
                "entry_tf": "1m",
                "open_time": "2026-04-05T12:20:00+00:00",
                "qty": 0.5,
                "margin_usdt": 50.0,
                "size_usdt": 500.0,
                "entry_price": 100.0,
                "trigger_indicators": ["rsi"],
            }
        ]

        positions_map = _seed_positions_map_from_rows(window, base_rows, alloc_map_global, {})

        allocations = positions_map[("BTCUSDT", "L")]["allocations"]
        self.assertEqual(["trade-a", "trade-b"], [entry["trade_id"] for entry in allocations])

    def test_per_trade_rows_keep_stable_order_after_refresh_seed(self):
        window = _RefreshWindowStub()
        alloc_map_global = {
            ("BTCUSDT", "L"): [
                _allocation(
                    trade_id="trade-b",
                    slot_id="slot-b",
                    open_time="2026-04-05T12:21:00+00:00",
                ),
                _allocation(
                    trade_id="trade-a",
                    slot_id="slot-a",
                    open_time="2026-04-05T12:20:00+00:00",
                ),
            ]
        }
        prev_records = {
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
                },
            }
        }

        positions_map = _seed_positions_map_from_rows(window, [], alloc_map_global, prev_records)
        records = _mw_positions_records_per_trade(window, positions_map, [])
        active_rows = [
            record
            for record in records
            if str(record.get("status") or "").lower() == "active"
        ]

        self.assertEqual(["trade-a", "trade-b"], [record["allocations"][0]["trade_id"] for record in active_rows])
        self.assertEqual(
            [
                "2026-04-05T12:20:00+00:00",
                "2026-04-05T12:21:00+00:00",
            ],
            [record["allocations"][0]["open_time"] for record in active_rows],
        )


if __name__ == "__main__":
    unittest.main()
