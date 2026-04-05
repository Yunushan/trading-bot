from __future__ import annotations

import copy
import sys
import unittest
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from app.gui.positions.tracking_runtime import _mw_pos_track_interval_close  # noqa: E402
from app.gui.trade.signal_close_interval_runtime import _handle_close_interval_event  # noqa: E402


class _StaticCombo:
    def __init__(self, value: str) -> None:
        self._value = value

    def currentText(self) -> str:
        return self._value


class _SignalCloseWindowStub:
    def __init__(self, allocations: list[dict]) -> None:
        key = ("BTCUSDT", "L")
        self._entry_allocations: dict[tuple[str, str], list[dict[str, Any]]] = {
            key: copy.deepcopy(allocations)
        }
        self._open_position_records: dict[tuple[str, str], dict[str, Any]] = {
            key: {
                "symbol": "BTCUSDT",
                "side_key": "L",
                "entry_tf": "1m",
                "open_time": allocations[0]["open_time"] if allocations else "-",
                "close_time": "-",
                "status": "Active",
                "data": {
                    "symbol": "BTCUSDT",
                    "side_key": "L",
                    "qty": sum(float(entry.get("qty") or 0.0) for entry in allocations),
                    "margin_usdt": sum(float(entry.get("margin_usdt") or 0.0) for entry in allocations),
                    "size_usdt": sum(float(entry.get("notional") or 0.0) for entry in allocations),
                    "entry_price": 100.0,
                    "leverage": 10,
                    "trigger_indicators": ["rsi"],
                },
                "allocations": copy.deepcopy(allocations),
                "indicators": ["rsi"],
                "stop_loss_enabled": False,
            }
        }
        earliest_open_time = allocations[0]["open_time"] if allocations else ""
        self._entry_intervals = {"BTCUSDT": {"L": {"1m"}, "S": set()}}
        self._entry_times = {key: earliest_open_time}
        self._entry_times_by_iv = {("BTCUSDT", "L", "1m"): earliest_open_time}
        self._pending_close_times: dict[tuple[str, str], str] = {}
        self._position_missing_counts: dict[tuple[str, str], int] = {}
        self._closed_position_records: list[dict] = []
        self._closed_trade_registry: dict[str, dict[str, float | None]] = {}
        self._processed_close_events: set[str] = set()
        self.traded_symbols: set[str] = set()
        self.mode_combo = _StaticCombo("Live")
        self.refreshed_symbols = None

    def _track_interval_close(self, symbol, side_key, interval) -> None:
        _mw_pos_track_interval_close(self, symbol, side_key, interval)

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
            return value.astimezone(timezone.utc).isoformat(timespec="seconds")
        return str(value)

    def update_balance_label(self) -> None:
        return None

    def refresh_positions(self, symbols=None) -> None:
        self.refreshed_symbols = symbols

    def _update_global_pnl_display(self, *_args, **_kwargs) -> None:
        return None

    def _compute_global_pnl_totals(self):
        return (0.0, 0.0)


def _allocation(*, ledger_id: str, trade_id: str, slot_id: str, open_time: str) -> dict:
    return {
        "ledger_id": ledger_id,
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
        "entry_price": 100.0,
        "leverage": 10,
    }


def _ctx() -> dict:
    return {
        "sym": "BTCUSDT",
        "interval": "1m",
        "side_for_key": "BUY",
        "side_key": "L",
        "sym_upper": "BTCUSDT",
        "event_type": "close_interval",
        "status": "closed",
        "ok_flag": True,
    }


def _dispatch(window: _SignalCloseWindowStub, *, ledger_id: str, event_id: str) -> None:
    _handle_close_interval_event(
        window,
        {
            "event": "close_interval",
            "symbol": "BTCUSDT",
            "interval": "1m",
            "side": "BUY",
            "ledger_id": ledger_id,
            "event_id": event_id,
            "qty": 0.25,
            "pnl_value": 5.0,
            "margin_usdt": 25.0,
            "entry_price": 100.0,
            "close_price": 102.0,
            "leverage": 10,
            "time": "2026-04-05T12:40:00+00:00",
            "context_key": f"1m:BUY:rsi|slot-{ledger_id[-1]}",
        },
        _ctx(),
        alloc_map=window._entry_allocations,
        pending_close=window._pending_close_times,
        max_closed_history=100,
        resolve_trigger_indicators=lambda raw, _desc=None: [
            str(value).strip()
            for value in (raw or [])
            if str(value).strip()
        ]
        if isinstance(raw, (list, tuple, set))
        else [],
        normalize_trigger_actions_map=lambda raw: dict(raw) if isinstance(raw, dict) else {},
        save_position_allocations=lambda *_args, **_kwargs: None,
    )


class SignalCloseReconciliationTests(unittest.TestCase):
    def test_partial_signal_close_restores_same_interval_tracking_for_survivor(self):
        window = _SignalCloseWindowStub(
            [
                _allocation(
                    ledger_id="ledger-a",
                    trade_id="trade-a",
                    slot_id="slot-a",
                    open_time="2026-04-05T12:20:00+00:00",
                ),
                _allocation(
                    ledger_id="ledger-b",
                    trade_id="trade-b",
                    slot_id="slot-b",
                    open_time="2026-04-05T12:21:00+00:00",
                ),
            ]
        )

        _dispatch(window, ledger_id="ledger-a", event_id="evt-close-a")

        key = ("BTCUSDT", "L")
        self.assertIn(key, window._entry_allocations)
        self.assertEqual(1, len(window._entry_allocations[key]))
        self.assertEqual("trade-b", window._entry_allocations[key][0]["trade_id"])
        self.assertIn(key, window._open_position_records)
        open_record = window._open_position_records[key]
        open_allocations = open_record.get("allocations")
        assert isinstance(open_allocations, list)
        first_allocation = open_allocations[0]
        assert isinstance(first_allocation, dict)
        self.assertEqual("trade-b", first_allocation["trade_id"])
        self.assertEqual({"1m"}, window._entry_intervals["BTCUSDT"]["L"])
        self.assertEqual("2026-04-05T12:21:00+00:00", window._entry_times[key])
        self.assertEqual(
            "2026-04-05T12:21:00+00:00",
            window._entry_times_by_iv[("BTCUSDT", "L", "1m")],
        )
        self.assertNotIn(key, window._pending_close_times)
        self.assertEqual(["BTCUSDT"], window.refreshed_symbols)

    def test_final_signal_close_clears_tracking_for_last_leg(self):
        window = _SignalCloseWindowStub(
            [
                _allocation(
                    ledger_id="ledger-a",
                    trade_id="trade-a",
                    slot_id="slot-a",
                    open_time="2026-04-05T12:20:00+00:00",
                )
            ]
        )

        _dispatch(window, ledger_id="ledger-a", event_id="evt-close-final")

        key = ("BTCUSDT", "L")
        self.assertNotIn(key, window._entry_allocations)
        self.assertNotIn(key, window._open_position_records)
        self.assertNotIn("BTCUSDT", window._entry_intervals)
        self.assertNotIn(key, window._entry_times)
        self.assertNotIn(("BTCUSDT", "L", "1m"), window._entry_times_by_iv)
        self.assertNotIn(key, window._pending_close_times)
        self.assertEqual(1, len(window._closed_position_records))
        self.assertEqual(["BTCUSDT"], window.refreshed_symbols)


if __name__ == "__main__":
    unittest.main()
