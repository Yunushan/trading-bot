from __future__ import annotations

import copy
import sys
import unittest
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from types import SimpleNamespace
from unittest.mock import patch


PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from app.gui.positions.tracking_runtime import _mw_pos_track_interval_close  # noqa: E402
from app.gui.trade.signal_close_interval_runtime import _handle_close_interval_event  # noqa: E402
from app.gui.shared.allocation_persistence import (  # noqa: E402
    AllocationSnapshotSession, load_position_allocations, save_position_allocations,
)
from app.gui.trade import signal_common_runtime  # noqa: E402


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


def _dispatch(window: _SignalCloseWindowStub, *, ledger_id: str, event_id: str, saver=None) -> None:
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
        save_position_allocations=saver or (lambda *_args, **_kwargs: True),
    )


class SignalCloseReconciliationTests(unittest.TestCase):
    def test_interrupted_close_mutation_rolls_back_and_retains_confirmed_event(self):
        window = _SignalCloseWindowStub([
            _allocation(ledger_id="ledger-a", trade_id="trade-a", slot_id="slot-a", open_time="2026-04-05T12:20:00+00:00"),
            _allocation(ledger_id="ledger-b", trade_id="trade-b", slot_id="slot-b", open_time="2026-04-05T12:21:00+00:00"),
        ])
        baseline = copy.deepcopy((window._entry_allocations, window._open_position_records))
        with patch.object(signal_common_runtime, "_sync_open_position_snapshot", side_effect=KeyboardInterrupt()):
            with self.assertRaises(KeyboardInterrupt):
                _dispatch(window, ledger_id="ledger-a", event_id="interrupted-close")
        self.assertEqual(baseline, (window._entry_allocations, window._open_position_records))
        self.assertEqual([], window._closed_position_records)
        self.assertEqual(set(), window._processed_close_events)
        self.assertTrue(window._pending_allocation_reconciliations[("BTCUSDT", "L")])
        self.assertIsNone(window._active_trade_event_receipt)

    def test_actual_publication_retains_closed_history_without_active_record_or_guard_ghost(self):
        for active_qty in (0.25, 0.5):
            with self.subTest(active_qty=active_qty), tempfile.TemporaryDirectory() as tmp:
                this_file = Path(tmp) / "Languages" / "Python" / "app" / "gui" / "window_shell.py"
                this_file.parent.mkdir(parents=True)
                closed = _allocation(ledger_id="ledger-a", trade_id="trade-a", slot_id="slot-a", open_time="2026-04-05T12:10:00+00:00")
                closed.update(status="Closed", entry_price=999.0, close_time="2026-04-05T12:15:00+00:00")
                active = _allocation(ledger_id="ledger-b", trade_id="trade-b", slot_id="slot-b", open_time="2026-04-05T12:20:00+00:00")
                active["qty"] = active_qty
                closed["context_key"] = active["context_key"]
                window = _SignalCloseWindowStub([closed, active])
                key = ("BTCUSDT", "L")
                record = window._open_position_records[key]
                record["allocations"] = [copy.deepcopy(active)]
                record["data"].update(qty=active_qty, margin_usdt=25.0, size_usdt=250.0, entry_price=100.0)
                closed_before = copy.deepcopy(closed)
                cleared = []
                window.guard = SimpleNamespace(mark_closed=lambda *_args, **kwargs: cleared.append(kwargs))
                session = window._allocation_snapshot_session = AllocationSnapshotSession()
                load_position_allocations(this_file=this_file, mode="Live", session=session)
                self.assertTrue(save_position_allocations(window._entry_allocations, window._open_position_records,
                                                         this_file=this_file, mode="Live", session=session))
                publications = []
                def saver(allocations, records, **kwargs):
                    publications.append(copy.deepcopy((allocations, records)))
                    return save_position_allocations(allocations, records, this_file=this_file, **kwargs)
                _dispatch(window, ledger_id="ledger-b", event_id="mixed-history-close", saver=saver)
                self.assertEqual(1, len(publications))
                self.assertEqual(closed_before, window._entry_allocations[key][0])
                self.assertFalse(getattr(window, "_pending_trade_reconciliation", {}))
                if active_qty == 0.25:
                    self.assertEqual([closed_before], window._entry_allocations[key])
                    self.assertNotIn(key, window._open_position_records)
                    self.assertNotIn("BTCUSDT", window._entry_intervals)
                    self.assertEqual([{"context": active["context_key"]}], cleared)
                else:
                    survivors = window._entry_allocations[key][1:]
                    self.assertEqual(survivors, window._open_position_records[key]["allocations"])
                    self.assertEqual(0.25, window._open_position_records[key]["data"]["qty"])
                    self.assertEqual(100.0, window._open_position_records[key]["data"]["entry_price"])
                    self.assertEqual({"1m"}, window._entry_intervals["BTCUSDT"]["L"])
                    self.assertEqual([], cleared)
                reloaded_allocations, reloaded_records = load_position_allocations(this_file=this_file, mode="Live")
                self.assertEqual(window._entry_allocations, reloaded_allocations)
                self.assertEqual(window._open_position_records, reloaded_records)

    def test_real_snapshot_receipt_prevents_partial_and_full_close_replay_after_restart(self):
        for starting_qty in (0.5, 0.25):
            with self.subTest(starting_qty=starting_qty), tempfile.TemporaryDirectory() as tmp:
                this_file = Path(tmp) / "Languages" / "Python" / "app" / "gui" / "window_shell.py"
                this_file.parent.mkdir(parents=True)
                entry = _allocation(ledger_id="ledger-a", trade_id="trade-a", slot_id="slot-a", open_time="2026-04-05T12:20:00+00:00")
                entry["qty"] = starting_qty
                window = _SignalCloseWindowStub([entry])
                session = window._allocation_snapshot_session = AllocationSnapshotSession()
                load_position_allocations(this_file=this_file, mode="Live", session=session)
                self.assertTrue(save_position_allocations(window._entry_allocations, window._open_position_records,
                                                         this_file=this_file, mode="Live", session=session))
                def saver(allocations, records, **kwargs):
                    return save_position_allocations(allocations, records, this_file=this_file, **kwargs)
                _dispatch(window, ledger_id="ledger-a", event_id="restart-close", saver=saver)
                allocation_path = this_file.parents[2] / "data" / ".trading_bot_allocations.json"
                if starting_qty == 0.25:
                    replacement = copy.deepcopy(entry)
                    replacement.update(client_order_id="new-client", trade_id="new-trade")
                    new_window = _SignalCloseWindowStub([replacement])
                    self.assertTrue(save_position_allocations(new_window._entry_allocations, new_window._open_position_records,
                                                             this_file=this_file, mode="Live", session=session))
                committed = allocation_path.read_bytes()
                restarted = _SignalCloseWindowStub([])
                restarted._allocation_snapshot_session = AllocationSnapshotSession()
                restarted._entry_allocations, restarted._open_position_records = load_position_allocations(
                    this_file=this_file, mode="Live", session=restarted._allocation_snapshot_session)
                original = copy.deepcopy((restarted._entry_allocations, restarted._open_position_records))
                _dispatch(restarted, ledger_id="ledger-a", event_id="restart-close", saver=saver)
                self.assertEqual(committed, allocation_path.read_bytes())
                self.assertEqual(original, (restarted._entry_allocations, restarted._open_position_records))
                self.assertEqual([], restarted._closed_position_records)

    def test_raising_close_publisher_keeps_guard_and_interval_tracking_until_retry(self):
        window = _SignalCloseWindowStub([_allocation(
            ledger_id="ledger-a", trade_id="trade-a", slot_id="slot-a", open_time="2026-04-05T12:20:00+00:00")])
        cleared = []
        window.guard = SimpleNamespace(mark_closed=lambda *_a, **_kw: cleared.append(True))
        def saver(*_args, **_kwargs):
            raise OSError("offline publication failure")
        _dispatch(window, ledger_id="ledger-a", event_id="raising-close", saver=saver)
        self.assertEqual([], cleared)
        self.assertEqual({"1m"}, window._entry_intervals["BTCUSDT"]["L"])
        self.assertEqual(set(), window._processed_close_events)
        self.assertEqual([], window._closed_position_records)
        self.assertTrue(window._pending_allocation_reconciliations[("BTCUSDT", "L")])
        _dispatch(window, ledger_id="ledger-a", event_id="raising-close")
        self.assertEqual([True], cleared)
        self.assertFalse(window._pending_allocation_reconciliations)

    def test_close_target_with_recovery_proof_is_retained_as_pending(self):
        entry = _allocation(ledger_id="ledger-a", trade_id="trade-a", slot_id="slot-a", open_time="2026-04-05T12:20:00+00:00")
        entry["spot_fill_recovery"] = {"signature": "a" * 64, "net_qty": "0.25"}
        window = _SignalCloseWindowStub([entry])
        baseline = copy.deepcopy((window._entry_allocations, window._open_position_records))
        saves = []
        _dispatch(window, ledger_id="ledger-a", event_id="protected-close", saver=lambda *_a, **_kw: saves.append(True) or True)
        self.assertEqual(baseline, (window._entry_allocations, window._open_position_records))
        self.assertEqual([], saves)
        self.assertTrue(window._pending_allocation_reconciliations[("BTCUSDT", "L")])

    def test_partial_close_publishes_coherent_allocation_and_position_record_once(self):
        window = _SignalCloseWindowStub([
            _allocation(ledger_id="ledger-a", trade_id="trade-a", slot_id="slot-a", open_time="2026-04-05T12:20:00+00:00"),
            _allocation(ledger_id="ledger-b", trade_id="trade-b", slot_id="slot-b", open_time="2026-04-05T12:21:00+00:00"),
        ])
        publications = []
        def saver(allocations, records, **_kwargs):
            publications.append(copy.deepcopy((allocations, records)))
            return True
        _dispatch(window, ledger_id="ledger-a", event_id="coherent-close", saver=saver)
        self.assertEqual(1, len(publications))
        allocations, records = publications[0]
        key = ("BTCUSDT", "L")
        self.assertEqual(allocations[key], records[key]["allocations"])
        self.assertEqual(0.25, records[key]["data"]["qty"])

    def test_failed_close_publication_retains_inventory_and_pending_event(self):
        window = _SignalCloseWindowStub([_allocation(
            ledger_id="ledger-a", trade_id="trade-a", slot_id="slot-a", open_time="2026-04-05T12:20:00+00:00")])
        before = copy.deepcopy((window._entry_allocations, window._open_position_records))
        _dispatch(window, ledger_id="ledger-a", event_id="failed-close", saver=lambda *_args, **_kwargs: False)
        self.assertEqual(before, (window._entry_allocations, window._open_position_records))
        self.assertEqual([], window._closed_position_records)
        self.assertEqual(set(), window._processed_close_events)
        self.assertTrue(getattr(window, "_pending_trade_reconciliation", {}))
        _dispatch(window, ledger_id="ledger-a", event_id="failed-close")
        self.assertEqual(1, len(window._closed_position_records))
        self.assertFalse(window._pending_trade_reconciliation)

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
