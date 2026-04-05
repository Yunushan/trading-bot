from __future__ import annotations

import sys
import unittest
from datetime import datetime, timezone
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from app.gui.positions.history_records_emit_runtime import build_raw_history_records  # noqa: E402
from app.gui.positions.history_records_group_runtime import group_history_records  # noqa: E402
from app.gui.trade.signal_close_records_runtime import _record_closed_position  # noqa: E402


class _CloseHistoryWindowStub:
    def __init__(self) -> None:
        self._closed_position_records: list[dict] = []
        self._closed_trade_registry: dict[str, dict[str, float | None]] = {}
        self._processed_close_events: set[str] = set()
        self._open_position_records = {
            ("BTCUSDT", "L"): {
                "symbol": "BTCUSDT",
                "side_key": "L",
                "entry_tf": "1m",
                "open_time": "2026-04-05T11:55:00+00:00",
                "close_time": "-",
                "status": "Active",
                "data": {
                    "symbol": "BTCUSDT",
                    "side_key": "L",
                    "qty": 1.0,
                    "margin_usdt": 100.0,
                    "size_usdt": 1000.0,
                    "entry_price": 100.0,
                    "leverage": 10,
                    "trigger_indicators": ["rsi"],
                },
                "indicators": ["rsi"],
                "stop_loss_enabled": False,
            }
        }

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
            return value.astimezone(timezone.utc).isoformat(timespec="seconds")
        return str(value)

    def _update_global_pnl_display(self, *_args, **_kwargs) -> None:
        return None

    def _compute_global_pnl_totals(self):
        return (0.0, 0.0)

    def _canonicalize_interval(self, value):
        if value is None:
            return None
        return str(value).strip() or None


def _close_payload(*, event_id: str, qty: float, pnl_value: float, close_time: datetime) -> tuple[dict, list[dict]]:
    order_info = {
        "event_id": event_id,
        "ledger_id": "ledger-1",
        "symbol": "BTCUSDT",
        "qty": qty,
        "pnl_value": pnl_value,
        "margin_usdt": qty * 100.0,
        "roi_percent": pnl_value / (qty * 100.0) * 100.0,
        "entry_price": 100.0,
        "close_price": 102.0,
        "leverage": 10,
        "time": close_time,
    }
    closed_snapshots = [
        {
            "ledger_id": "ledger-1",
            "qty": qty,
            "margin_usdt": qty * 100.0,
            "pnl_value": pnl_value,
            "notional": qty * 1000.0,
            "interval": "1m",
            "interval_display": "1m",
            "trigger_indicators": ["rsi"],
            "open_time": "2026-04-05T11:55:00+00:00",
        }
    ]
    return order_info, closed_snapshots


class CloseHistoryReconciliationTests(unittest.TestCase):
    def test_partial_close_events_on_same_ledger_are_preserved(self):
        window = _CloseHistoryWindowStub()
        close_time = datetime(2026, 4, 5, 12, 0, tzinfo=timezone.utc)

        first_info, first_snapshots = _close_payload(
            event_id="evt-1",
            qty=0.5,
            pnl_value=12.0,
            close_time=close_time,
        )
        second_info, second_snapshots = _close_payload(
            event_id="evt-2",
            qty=0.5,
            pnl_value=18.0,
            close_time=close_time,
        )

        first_recorded = _record_closed_position(
            window,
            first_info,
            {"sym_upper": "BTCUSDT", "side_key": "L"},
            closed_snapshots=first_snapshots,
            max_closed_history=100,
        )
        second_recorded = _record_closed_position(
            window,
            second_info,
            {"sym_upper": "BTCUSDT", "side_key": "L"},
            closed_snapshots=second_snapshots,
            max_closed_history=100,
        )

        self.assertTrue(first_recorded)
        self.assertTrue(second_recorded)
        self.assertEqual(2, len(window._closed_position_records))
        self.assertEqual(
            ["evt-2", "evt-1"],
            [record.get("close_event_id") for record in window._closed_position_records],
        )
        self.assertEqual(
            {"evt-1", "evt-2"},
            set(window._closed_trade_registry.keys()),
        )

    def test_history_grouping_keeps_distinct_close_events_for_same_ledger(self):
        window = _CloseHistoryWindowStub()
        close_time = datetime(2026, 4, 5, 12, 0, tzinfo=timezone.utc)

        for event_id, pnl_value in (("evt-1", 12.0), ("evt-2", 18.0)):
            order_info, closed_snapshots = _close_payload(
                event_id=event_id,
                qty=0.5,
                pnl_value=pnl_value,
                close_time=close_time,
            )
            _record_closed_position(
                window,
                order_info,
                {"sym_upper": "BTCUSDT", "side_key": "L"},
                closed_snapshots=closed_snapshots,
                max_closed_history=100,
            )

        raw_records = build_raw_history_records(
            window,
            {},
            window._closed_position_records,
            {},
            normalize_indicator_values=lambda values: [
                str(value).strip()
                for value in (values or [])
                if str(value).strip()
            ],
            derive_margin_snapshot=lambda *_args, **_kwargs: (0.0, 0.0, 0.0, 0.0),
        )

        grouped = group_history_records(window, raw_records, {"closed", "liquidated"})

        close_event_ids = [record.get("close_event_id") for record in grouped if record.get("status") == "Closed"]
        self.assertEqual(2, len(close_event_ids))
        self.assertEqual(["evt-2", "evt-1"], close_event_ids)

    def test_close_record_reconciles_fill_summary_totals_into_history(self):
        window = _CloseHistoryWindowStub()
        close_time = datetime(2026, 4, 5, 12, 0, tzinfo=timezone.utc)
        order_info = {
            "event_id": "evt-fill-1",
            "ledger_id": "ledger-1",
            "symbol": "BTCUSDT",
            "qty": 1.0,
            "pnl_value": 14.0,
            "margin_usdt": 100.0,
            "roi_percent": 14.0,
            "entry_price": 100.0,
            "close_price": 102.0,
            "leverage": 10,
            "time": close_time,
            "entry_fee_usdt": 1.0,
            "close_fee_usdt": 2.5,
            "realized_pnl_usdt": 17.5,
            "net_realized_usdt": 15.0,
            "fills_meta": {"order_id": "close-order-1", "trade_count": 2},
        }
        closed_snapshots = [
            {
                "ledger_id": "ledger-1",
                "qty": 0.4,
                "margin_usdt": 40.0,
                "notional": 400.0,
                "interval": "1m",
                "interval_display": "1m",
                "trigger_indicators": ["rsi"],
                "open_time": "2026-04-05T11:55:00+00:00",
            },
            {
                "ledger_id": "ledger-1",
                "qty": 0.6,
                "margin_usdt": 60.0,
                "notional": 600.0,
                "interval": "5m",
                "interval_display": "5m",
                "trigger_indicators": ["macd"],
                "open_time": "2026-04-05T11:56:00+00:00",
            },
        ]

        recorded = _record_closed_position(
            window,
            order_info,
            {"sym_upper": "BTCUSDT", "side_key": "L"},
            closed_snapshots=closed_snapshots,
            max_closed_history=100,
        )

        self.assertTrue(recorded)
        record = window._closed_position_records[0]
        data = record["data"]
        self.assertAlmostEqual(1.0, data["entry_fee_usdt"])
        self.assertAlmostEqual(2.5, data["close_fee_usdt"])
        self.assertAlmostEqual(17.5, data["realized_pnl_usdt"])
        self.assertAlmostEqual(15.0, data["net_realized_usdt"])
        self.assertAlmostEqual(14.0, data["pnl_value"])
        self.assertEqual("close-order-1", data["fills_meta"]["order_id"])
        self.assertEqual(2, data["fills_meta"]["trade_count"])

        allocations = record["allocations"]
        self.assertEqual(2, len(allocations))
        self.assertAlmostEqual(0.4, allocations[0]["entry_fee_usdt"])
        self.assertAlmostEqual(0.6, allocations[1]["entry_fee_usdt"])
        self.assertAlmostEqual(1.0, allocations[0]["close_fee_usdt"])
        self.assertAlmostEqual(1.5, allocations[1]["close_fee_usdt"])
        self.assertAlmostEqual(7.0, allocations[0]["realized_pnl_usdt"])
        self.assertAlmostEqual(10.5, allocations[1]["realized_pnl_usdt"])
        self.assertAlmostEqual(6.0, allocations[0]["net_realized_usdt"])
        self.assertAlmostEqual(9.0, allocations[1]["net_realized_usdt"])
        self.assertEqual("close-order-1", allocations[0]["fills_meta"]["order_id"])
        self.assertEqual("close-order-1", allocations[1]["fills_meta"]["order_id"])

        raw_records = build_raw_history_records(
            window,
            {},
            window._closed_position_records,
            {},
            normalize_indicator_values=lambda values: [
                str(value).strip()
                for value in (values or [])
                if str(value).strip()
            ],
            derive_margin_snapshot=lambda *_args, **_kwargs: (0.0, 0.0, 0.0, 0.0),
        )
        closed_rows = {
            record.get("entry_tf"): record
            for record in raw_records
            if record.get("status") == "Closed"
        }
        self.assertAlmostEqual(0.4, closed_rows["1m"]["data"]["entry_fee_usdt"])
        self.assertAlmostEqual(1.5, closed_rows["5m"]["data"]["close_fee_usdt"])
        self.assertAlmostEqual(10.5, closed_rows["5m"]["data"]["realized_pnl_usdt"])
        self.assertAlmostEqual(9.0, closed_rows["5m"]["data"]["net_realized_usdt"])

    def test_close_record_derives_missing_fill_fields_from_quick_summary(self):
        window = _CloseHistoryWindowStub()
        close_time = datetime(2026, 4, 5, 12, 5, tzinfo=timezone.utc)
        order_info = {
            "event_id": "evt-fill-2",
            "ledger_id": "ledger-1",
            "symbol": "BTCUSDT",
            "qty": 1.0,
            "pnl_value": 7.75,
            "margin_usdt": 100.0,
            "roi_percent": 7.75,
            "entry_price": 100.0,
            "close_price": 101.0,
            "leverage": 10,
            "time": close_time,
            "entry_fee_usdt": 0.5,
            "commission_usdt": 1.75,
            "net_realized_usdt": 8.25,
            "fills_meta": {"order_id": "close-order-2", "trade_count": 1},
        }
        closed_snapshots = [
            {
                "ledger_id": "ledger-1",
                "qty": 1.0,
                "margin_usdt": 100.0,
                "notional": 1000.0,
                "interval": "1m",
                "interval_display": "1m",
                "trigger_indicators": ["rsi"],
                "open_time": "2026-04-05T11:55:00+00:00",
            }
        ]

        recorded = _record_closed_position(
            window,
            order_info,
            {"sym_upper": "BTCUSDT", "side_key": "L"},
            closed_snapshots=closed_snapshots,
            max_closed_history=100,
        )

        self.assertTrue(recorded)
        data = window._closed_position_records[0]["data"]
        allocation = window._closed_position_records[0]["allocations"][0]
        registry_entry = window._closed_trade_registry["evt-fill-2"]
        close_fee_registry = registry_entry["close_fee_usdt"]
        realized_pnl_registry = registry_entry["realized_pnl_usdt"]
        self.assertAlmostEqual(0.5, data["entry_fee_usdt"])
        self.assertAlmostEqual(1.75, data["close_fee_usdt"])
        self.assertAlmostEqual(8.25, data["net_realized_usdt"])
        self.assertAlmostEqual(10.0, data["realized_pnl_usdt"])
        self.assertAlmostEqual(10.0, allocation["realized_pnl_usdt"])
        assert close_fee_registry is not None
        assert realized_pnl_registry is not None
        self.assertAlmostEqual(1.75, close_fee_registry)
        self.assertAlmostEqual(10.0, realized_pnl_registry)

    def test_same_interval_partial_close_allocations_keep_distinct_history_rows(self):
        window = _CloseHistoryWindowStub()
        close_time = datetime(2026, 4, 5, 12, 10, tzinfo=timezone.utc)
        order_info = {
            "event_id": "evt-same-interval",
            "ledger_id": "ledger-1",
            "symbol": "BTCUSDT",
            "qty": 0.5,
            "pnl_value": 11.0,
            "margin_usdt": 50.0,
            "roi_percent": 22.0,
            "entry_price": 100.0,
            "close_price": 102.0,
            "leverage": 10,
            "time": close_time,
        }
        closed_snapshots = [
            {
                "ledger_id": "ledger-1",
                "trade_id": "trade-a",
                "order_id": "order-a",
                "qty": 0.25,
                "margin_usdt": 25.0,
                "pnl_value": 5.0,
                "notional": 250.0,
                "interval": "1m",
                "interval_display": "1m",
                "trigger_indicators": ["rsi"],
                "open_time": "2026-04-05T11:50:00+00:00",
            },
            {
                "ledger_id": "ledger-1",
                "trade_id": "trade-b",
                "order_id": "order-b",
                "qty": 0.25,
                "margin_usdt": 25.0,
                "pnl_value": 6.0,
                "notional": 250.0,
                "interval": "1m",
                "interval_display": "1m",
                "trigger_indicators": ["rsi"],
                "open_time": "2026-04-05T11:51:00+00:00",
            },
        ]

        recorded = _record_closed_position(
            window,
            order_info,
            {"sym_upper": "BTCUSDT", "side_key": "L"},
            closed_snapshots=closed_snapshots,
            max_closed_history=100,
        )

        self.assertTrue(recorded)
        raw_records = build_raw_history_records(
            window,
            {},
            window._closed_position_records,
            {},
            normalize_indicator_values=lambda values: [
                str(value).strip()
                for value in (values or [])
                if str(value).strip()
            ],
            derive_margin_snapshot=lambda *_args, **_kwargs: (0.0, 0.0, 0.0, 0.0),
        )
        grouped = group_history_records(window, raw_records, {"closed", "liquidated"})
        closed_rows = [
            record
            for record in grouped
            if record.get("status") == "Closed" and record.get("entry_tf") == "1m"
        ]

        self.assertEqual(2, len(closed_rows))
        aggregate_keys = {str(record.get("_aggregate_key") or "") for record in closed_rows}
        self.assertEqual(2, len(aggregate_keys))
        self.assertTrue(
            any(key.startswith("evt-same-interval|trade-a|order-a|2026-04-05T11:50:00+00:00") for key in aggregate_keys)
        )
        self.assertTrue(
            any(key.startswith("evt-same-interval|trade-b|order-b|2026-04-05T11:51:00+00:00") for key in aggregate_keys)
        )
        self.assertEqual(
            {"trade-a", "trade-b"},
            {str((record.get("allocations") or [{}])[0].get("trade_id") or "") for record in closed_rows},
        )
        self.assertEqual(
            {5.0, 6.0},
            {float(record.get("data", {}).get("pnl_value") or 0.0) for record in closed_rows},
        )


if __name__ == "__main__":
    unittest.main()
