from __future__ import annotations

import copy
import json
import sys
import tempfile
import unittest
from datetime import datetime
from pathlib import Path
from types import SimpleNamespace
from typing import Any
from unittest.mock import Mock, patch


PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from app.gui.positions.actions_state_runtime import (  # noqa: E402
    _retain_pending_allocation_reconciliation,
    clear_local_position_state,
    reduce_local_position_allocation_state,
)
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
    def setUp(self):
        self.enterContext(patch("app.gui.positions.actions_state_runtime.get_save_position_allocations",
                                return_value=Mock(return_value=True)))

    def test_missing_or_conflicting_target_never_consumes_neighbor(self):
        for target in (
            {"trade_id": "missing"},
            {"trade_id": "missing", "slot_id": "neighbor-slot"},
            {"trade_id": "missing", "client_order_id": "client-neighbor"},
            {"trade_id": "neighbor", "client_order_id": "missing"},
        ):
            with self.subTest(target=target):
                window = _ManualCloseWindowStub()
                neighbor = _active_allocation(trade_id="neighbor", slot_id="neighbor-slot", open_time="2026-09-06")
                window._entry_allocations[("BTCUSDT", "L")] = [copy.deepcopy(neighbor)]
                changed = reduce_local_position_allocation_state(
                    window, "BTCUSDT", "L", interval="1m", qty=0.25, target_identity=target,
                )
                self.assertFalse(changed)
                self.assertEqual([neighbor], window._entry_allocations[("BTCUSDT", "L")])

    def test_ambiguous_identity_or_quantity_preserves_all_allocations(self):
        for copies, qty in ((2, 0.25), (1, 0.5), (1, 0), (1, -0.1), (1, True), (1, "nan"), (1, "inf")):
            with self.subTest(copies=copies, qty=qty):
                window = _ManualCloseWindowStub()
                entry = _active_allocation(trade_id="target", slot_id="slot", open_time="2026-09-06")
                before = [copy.deepcopy(entry) for _ in range(copies)]
                window._entry_allocations[("BTCUSDT", "L")] = copy.deepcopy(before)
                changed = reduce_local_position_allocation_state(
                    window, "BTCUSDT", "L", interval="1m", qty=qty, target_identity={"trade_id": "target"},
                )
                self.assertFalse(changed)
                self.assertEqual(before, window._entry_allocations[("BTCUSDT", "L")])

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
        self.assertEqual(0.25, window._open_position_records[key]["data"]["qty"])

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

    def _publication_window(self):
        window = _ManualCloseWindowStub()
        key = ("BTCUSDT", "L")
        entry = _active_allocation(trade_id="owned", slot_id="slot", open_time="2026-09-06")
        window._entry_allocations[key] = [copy.deepcopy(entry)]
        window._open_position_records[key] = {
            "symbol": "BTCUSDT", "side_key": "L", "status": "Active",
            "data": {"qty": 0.25}, "allocations": [copy.deepcopy(entry)],
        }
        window._entry_intervals = {"BTCUSDT": {"L": {"1m"}, "S": set()}}
        window._entry_times[key] = "2026-09-06"
        window._entry_times_by_iv[("BTCUSDT", "L", "1m")] = "2026-09-06"
        window._pending_close_times = {key: "confirmed-close"}
        window._position_missing_counts = {key: 2}
        window.mode_combo = SimpleNamespace(currentText=lambda: "Testnet")
        window._allocation_snapshot_session = object()
        window.guard = SimpleNamespace(mark_closed=Mock(), clear_symbol_side=Mock())
        window._track_interval_close = Mock()
        window._snapshot_closed_position = Mock(return_value=True)
        window._update_global_pnl_display = Mock()
        window._compute_global_pnl_totals = Mock(return_value=(0, 0))
        window._render_positions_table = Mock()
        window.log = Mock()
        return window

    def test_reduce_failed_publication_preserves_maps_tracking_and_pending_fill(self):
        for failure in (False, OSError("disk unavailable")):
            with self.subTest(failure=failure):
                window = self._publication_window()
                before_allocations = copy.deepcopy(window._entry_allocations)
                before_records = copy.deepcopy(window._open_position_records)
                saver = Mock(return_value=failure if failure is False else None,
                             side_effect=failure if isinstance(failure, BaseException) else None)
                with patch("app.gui.positions.actions_state_runtime.get_save_position_allocations", return_value=saver):
                    changed = reduce_local_position_allocation_state(
                        window, "BTCUSDT", "L", interval="1m", qty=0.1,
                        target_identity={"trade_id": "owned"},
                    )
                self.assertFalse(changed)
                self.assertEqual(before_allocations, window._entry_allocations)
                self.assertEqual(before_records, window._open_position_records)
                self.assertEqual({"1m"}, window._entry_intervals["BTCUSDT"]["L"])
                self.assertIn(("BTCUSDT", "L", "1m"), window._entry_times_by_iv)
                window.guard.clear_symbol_side.assert_not_called()
                pending = window._pending_allocation_reconciliations[("BTCUSDT", "L")]
                self.assertEqual(0.1, pending[-1]["qty"])
                self.assertEqual({"trade_id": "owned"}, pending[-1]["target_identity"])

    def test_clear_failed_publication_retains_guards_and_stale_snapshot(self):
        for failure in (False, OSError("disk unavailable")):
            with self.subTest(failure=failure):
                window = self._publication_window()
                before_allocations = copy.deepcopy(window._entry_allocations)
                before_records = copy.deepcopy(window._open_position_records)
                saver = Mock(return_value=failure if failure is False else None,
                             side_effect=failure if isinstance(failure, BaseException) else None)
                with patch("app.gui.positions.actions_state_runtime.get_save_position_allocations", return_value=saver):
                    changed = clear_local_position_state(window, "BTCUSDT", "L", interval="1m",
                                                         reason="exchange reports no open leg")
                self.assertFalse(changed)
                self.assertEqual(before_allocations, window._entry_allocations)
                self.assertEqual(before_records, window._open_position_records)
                self.assertEqual({"1m"}, window._entry_intervals["BTCUSDT"]["L"])
                self.assertEqual("confirmed-close", window._pending_close_times[("BTCUSDT", "L")])
                self.assertEqual(2, window._position_missing_counts[("BTCUSDT", "L")])
                window.guard.clear_symbol_side.assert_not_called()
                window._track_interval_close.assert_not_called()
                window._snapshot_closed_position.assert_not_called()
                window._render_positions_table.assert_not_called()
                self.assertEqual("clear", window._pending_allocation_reconciliations[("BTCUSDT", "L")][-1]["operation"])

    def test_reduce_publishes_coherent_maps_once_before_guard_or_tracking_changes(self):
        for qty in (0.1, 0.25):
            with self.subTest(qty=qty):
                window = self._publication_window()
                key = ("BTCUSDT", "L")
                before = copy.deepcopy(window._entry_allocations)

                def save(allocations, records, *, mode, session):
                    self.assertEqual(before, window._entry_allocations)
                    self.assertEqual({"1m"}, window._entry_intervals["BTCUSDT"]["L"])
                    window.guard.clear_symbol_side.assert_not_called()
                    self.assertEqual("Testnet", mode)
                    self.assertIs(window._allocation_snapshot_session, session)
                    if qty < 0.25:
                        self.assertAlmostEqual(0.25 - qty, records[key]["data"]["qty"])
                        self.assertEqual(allocations[key], records[key]["allocations"])
                    else:
                        self.assertNotIn(key, allocations)
                        self.assertNotIn(key, records)
                    return True

                saver = Mock(side_effect=save)
                with patch("app.gui.positions.actions_state_runtime.get_save_position_allocations", return_value=saver):
                    self.assertTrue(reduce_local_position_allocation_state(
                        window, "BTCUSDT", "L", interval="1m", qty=qty,
                        target_identity={"trade_id": "owned"},
                    ))
                saver.assert_called_once()
                if qty < 0.25:
                    window.guard.clear_symbol_side.assert_not_called()
                else:
                    window.guard.clear_symbol_side.assert_called_once_with("BTCUSDT", "BUY", intervals=["1m"])
                    self.assertNotIn("BTCUSDT", window._entry_intervals)

    def test_clear_publishes_before_history_callback_and_guard_release(self):
        window = self._publication_window()
        key = ("BTCUSDT", "L")

        def save(allocations, records, **kwargs):
            self.assertIn(key, window._entry_allocations)
            self.assertIn(key, window._open_position_records)
            self.assertNotIn(key, allocations)
            self.assertNotIn(key, records)
            window._snapshot_closed_position.assert_not_called()
            window.guard.clear_symbol_side.assert_not_called()
            return True

        saver = Mock(side_effect=save)
        with patch("app.gui.positions.actions_state_runtime.get_save_position_allocations", return_value=saver):
            self.assertTrue(clear_local_position_state(window, "BTCUSDT", "L", interval="1m"))
        saver.assert_called_once()
        window._snapshot_closed_position.assert_called_once_with("BTCUSDT", "L")
        window.guard.clear_symbol_side.assert_called_once_with("BTCUSDT", "BUY", intervals=["1m"])
        self.assertNotIn("BTCUSDT", window._entry_intervals)

    def test_missing_saver_fails_closed_and_does_not_replay_pending_reduction(self):
        window = self._publication_window()
        before = copy.deepcopy(window._entry_allocations)
        with patch("app.gui.positions.actions_state_runtime.get_save_position_allocations", return_value=None):
            self.assertFalse(reduce_local_position_allocation_state(
                window, "BTCUSDT", "L", qty=0.1, target_identity={"trade_id": "owned"},
            ))
        saver = Mock(return_value=True)
        with patch("app.gui.positions.actions_state_runtime.get_save_position_allocations", return_value=saver):
            self.assertFalse(reduce_local_position_allocation_state(
                window, "BTCUSDT", "L", qty=0.1, target_identity={"trade_id": "owned"},
            ))
        self.assertEqual(before, window._entry_allocations)
        saver.assert_not_called()

    def test_confirmed_close_missing_exact_identity_remains_pending_without_publication(self):
        window = self._publication_window()
        before = copy.deepcopy(window._entry_allocations)
        saver = Mock(return_value=True)
        response = {"execution_confirmed": True, "executed_qty": 0.1, "info": {"status": "FILLED"}}
        with patch("app.gui.positions.actions_state_runtime.get_save_position_allocations", return_value=saver):
            self.assertFalse(reduce_local_position_allocation_state(
                window, "BTCUSDT", "L", qty=0.1, target_identity={"trade_id": "owned"}, close_result=response,
            ))
        self.assertEqual(before, window._entry_allocations)
        saver.assert_not_called()
        self.assertEqual(response, window._pending_allocation_reconciliations[("BTCUSDT", "L")][-1]["venue_result"])

    def test_actual_publication_receipt_blocks_close_replay_after_restart(self):
        from app.gui.shared.allocation_persistence import (
            AllocationSnapshotSession,
            get_position_allocations_path,
            load_position_allocations,
            save_position_allocations,
        )

        for qty in (0.1, 0.25):
            with self.subTest(qty=qty), tempfile.TemporaryDirectory(prefix="manual-close-receipt-") as directory:
                this_file = Path(directory) / "app" / "gui" / "composition.py"
                window = self._publication_window()
                session = AllocationSnapshotSession()
                load_position_allocations(this_file=this_file, mode="Testnet", session=session)
                self.assertTrue(save_position_allocations(
                    window._entry_allocations, window._open_position_records,
                    this_file=this_file, mode="Testnet", session=session,
                ))
                window._allocation_snapshot_session = session
                response = {
                    "execution_confirmed": True, "executed_qty": qty,
                    "info": {"orderId": 913, "clientOrderId": "close-owned", "status": "FILLED"},
                    "private_context": "must-not-be-written",
                }

                def save(allocations, records, **options):
                    return save_position_allocations(allocations, records, this_file=this_file, **options)

                with patch("app.gui.positions.actions_state_runtime.get_save_position_allocations", return_value=save):
                    self.assertTrue(reduce_local_position_allocation_state(
                        window, "BTCUSDT", "L", qty=qty, target_identity={"trade_id": "owned"}, close_result=response,
                    ))
                path = get_position_allocations_path(this_file)
                before_bytes = path.read_bytes()
                payload = json.loads(before_bytes)
                self.assertEqual(1, len(payload["gui_trade_event_receipts"]))
                self.assertNotIn(b"must-not-be-written", before_bytes)
                self.assertEqual(str(qty), payload["gui_trade_event_receipts"][0]["quantity"])
                restarted = self._publication_window()
                restarted._allocation_snapshot_session = AllocationSnapshotSession()
                restarted._entry_allocations, restarted._open_position_records = load_position_allocations(
                    this_file=this_file, mode="Testnet", session=restarted._allocation_snapshot_session,
                )
                before_maps = copy.deepcopy(restarted._entry_allocations)
                saver = Mock(side_effect=AssertionError("Replayed close must not republish"))
                with patch("app.gui.positions.actions_state_runtime.get_save_position_allocations", return_value=saver):
                    self.assertTrue(reduce_local_position_allocation_state(
                        restarted, "BTCUSDT", "L", qty=qty, target_identity={"trade_id": "owned"}, close_result=response,
                    ))
                saver.assert_not_called()
                self.assertEqual(before_maps, restarted._entry_allocations)
                self.assertEqual(before_bytes, path.read_bytes())

    def test_conflicting_confirmed_receipt_cannot_consume_more_inventory(self):
        from app.gui.trade.signal_common_runtime import _trade_event_receipt

        window = self._publication_window()
        response = {"execution_confirmed": True, "executed_qty": 0.1,
                    "info": {"orderId": 913, "clientOrderId": "close-owned"}}
        descriptor = _trade_event_receipt(
            {"qty": 0.25, "order_id": 913, "client_order_id": "close-owned"},
            {"sym_upper": "BTCUSDT", "side_key": "L"}, "SELL",
        )

        def has_receipt(candidate):
            self.assertEqual(descriptor["event_id"], candidate["event_id"])
            raise ValueError("GUI trade event conflicts with committed receipt")

        window._allocation_snapshot_session = SimpleNamespace(has_trade_event_receipt=has_receipt)
        before = copy.deepcopy(window._entry_allocations)
        saver = Mock(return_value=True)
        with patch("app.gui.positions.actions_state_runtime.get_save_position_allocations", return_value=saver):
            self.assertFalse(reduce_local_position_allocation_state(
                window, "BTCUSDT", "L", qty=0.1, target_identity={"trade_id": "owned"}, close_result=response,
            ))
        self.assertEqual(before, window._entry_allocations)
        saver.assert_not_called()
        self.assertEqual(response, window._pending_allocation_reconciliations[("BTCUSDT", "L")][-1]["venue_result"])

    def test_interval_close_cannot_credit_more_than_matching_owned_inventory(self):
        window = self._publication_window()
        before = copy.deepcopy(window._entry_allocations)
        saver = Mock(return_value=True)
        with patch("app.gui.positions.actions_state_runtime.get_save_position_allocations", return_value=saver):
            self.assertFalse(reduce_local_position_allocation_state(
                window, "BTCUSDT", "L", qty=0.5, interval="1m",
            ))
        self.assertEqual(before, window._entry_allocations)
        saver.assert_not_called()

    def test_partial_close_reconstructs_missing_record_in_same_publication(self):
        window = self._publication_window()
        window._open_position_records = {}
        key = ("BTCUSDT", "L")

        def save(allocations, records, **kwargs):
            self.assertEqual({}, window._open_position_records)
            self.assertAlmostEqual(0.15, records[key]["data"]["qty"])
            self.assertEqual(allocations[key], records[key]["allocations"])
            return True

        saver = Mock(side_effect=save)
        with patch("app.gui.positions.actions_state_runtime.get_save_position_allocations", return_value=saver):
            self.assertTrue(reduce_local_position_allocation_state(
                window, "BTCUSDT", "L", qty=0.1, target_identity={"trade_id": "owned"},
            ))
        saver.assert_called_once()
        self.assertEqual("Active", window._open_position_records[key]["status"])

    def test_distinct_confirmed_order_receipts_are_not_overwritten_in_pending_fence(self):
        window = self._publication_window()
        first = {"execution_confirmed": True, "executed_qty": 0.1, "info": {"orderId": 913}}
        second = {"execution_confirmed": True, "executed_qty": 0.1, "info": {"orderId": 914}}
        for result in (first, second, first):
            _retain_pending_allocation_reconciliation(
                window, "BTCUSDT", "L", operation="reduce", qty=0.1,
                target_identity={"trade_id": "owned"}, venue_result=result,
            )
        pending = window._pending_allocation_reconciliations[("BTCUSDT", "L")]
        self.assertEqual([first, second], [item["venue_result"] for item in pending])

    def test_actual_mixed_price_close_recomputes_active_survivor_weighted_cost(self):
        from app.gui.shared.allocation_persistence import (
            AllocationSnapshotSession,
            get_position_allocations_path,
            load_position_allocations,
            save_position_allocations,
        )

        for qty, target, remaining_qty, remaining_price in (
            (0.1, {"trade_id": "buy-A"}, 0.1, 30000.0),
            (0.05, {"trade_id": "buy-A"}, 0.15, 80000.0 / 3),
            (0.15, None, 0.05, 30000.0),
        ):
            with self.subTest(qty=qty, target=target), tempfile.TemporaryDirectory(prefix="manual-cost-") as directory:
                this_file = Path(directory) / "app" / "gui" / "composition.py"
                window = self._publication_window()
                key = ("BTCUSDT", "L")
                rows = [{"trade_id": token, "client_order_id": token, "qty": 0.1, "entry_price": price,
                         "margin_usdt": price * 0.1, "notional": price * 0.1,
                         "status": "Active", "interval": "1m"}
                        for token, price in (("buy-A", 20000.0), ("buy-B", 30000.0))]
                window._entry_allocations[key] = copy.deepcopy(rows)
                window._open_position_records[key] = {
                    "symbol": "BTCUSDT", "side_key": "L", "status": "Active", "allocations": copy.deepcopy(rows),
                    "data": {"qty": 0.2, "entry_price": 25000.0, "margin_usdt": 5000.0, "size_usdt": 5000.0},
                }
                session = AllocationSnapshotSession()
                load_position_allocations(this_file=this_file, mode="Testnet", session=session)
                self.assertTrue(save_position_allocations(window._entry_allocations, window._open_position_records,
                                                         this_file=this_file, mode="Testnet", session=session))
                window._allocation_snapshot_session = session

                def save(allocations, records, **options):
                    return save_position_allocations(allocations, records, this_file=this_file, **options)

                response = {"execution_confirmed": True, "executed_qty": qty,
                            "info": {"orderId": 913, "clientOrderId": "close-mixed-cost"}}
                with patch("app.gui.positions.actions_state_runtime.get_save_position_allocations", return_value=save):
                    self.assertTrue(reduce_local_position_allocation_state(
                        window, "BTCUSDT", "L", interval="1m", qty=qty, target_identity=target, close_result=response,
                    ))
                payload = json.loads(get_position_allocations_path(this_file).read_bytes())
                record = payload["open_position_records"]["BTCUSDT:L"]
                self.assertAlmostEqual(remaining_qty, record["data"]["qty"])
                self.assertAlmostEqual(remaining_price, record["data"]["entry_price"])
                self.assertEqual(payload["entry_allocations"]["BTCUSDT:L"], record["allocations"])

    def test_closed_tombstones_stay_durable_but_never_enter_active_position_amounts(self):
        from app.gui.shared.allocation_persistence import (
            AllocationSnapshotSession,
            get_position_allocations_path,
            load_position_allocations,
            save_position_allocations,
        )

        for qty in (0.04, 0.1):
            with self.subTest(qty=qty), tempfile.TemporaryDirectory(prefix="manual-tombstone-") as directory:
                this_file = Path(directory) / "app" / "gui" / "composition.py"
                window = self._publication_window()
                key = ("BTCUSDT", "L")
                tombstone = {"trade_id": "closed-A", "client_order_id": "closed-A", "qty": 0.2,
                             "entry_price": 20000.0, "margin_usdt": 4000.0, "notional": 4000.0,
                             "status": "Closed", "interval": "5m"}
                active = {"trade_id": "active-B", "client_order_id": "active-B", "qty": 0.1,
                          "entry_price": 30000.0, "margin_usdt": 3000.0, "notional": 3000.0,
                          "status": "Active", "interval": "1m"}
                proof_tombstone = {"trade_id": "closed-proof", "client_order_id": "closed-proof", "qty": 0,
                                   "status": "Closed", "spot_sell_recoveries": [{"signature": "b" * 64}]}
                window._entry_allocations = {key: [copy.deepcopy(tombstone), copy.deepcopy(active)],
                                              ("ETHUSDT", "L"): [copy.deepcopy(proof_tombstone)]}
                window._open_position_records[key] = {
                    "symbol": "BTCUSDT", "side_key": "L", "status": "Active", "allocations": [copy.deepcopy(active)],
                    "data": {"qty": 0.1, "entry_price": 30000.0, "margin_usdt": 3000.0, "size_usdt": 3000.0},
                }
                session = AllocationSnapshotSession()
                load_position_allocations(this_file=this_file, mode="Testnet", session=session)
                self.assertTrue(save_position_allocations(window._entry_allocations, window._open_position_records,
                                                         this_file=this_file, mode="Testnet", session=session))
                window._allocation_snapshot_session = session

                def save(allocations, records, **options):
                    return save_position_allocations(allocations, records, this_file=this_file, **options)

                response = {"execution_confirmed": True, "executed_qty": qty,
                            "info": {"orderId": 913, "clientOrderId": "close-active-B"}}
                with patch("app.gui.positions.actions_state_runtime.get_save_position_allocations", return_value=save):
                    self.assertTrue(reduce_local_position_allocation_state(
                        window, "BTCUSDT", "L", interval="1m", qty=qty,
                        target_identity={"trade_id": "active-B"}, close_result=response,
                    ))
                payload = json.loads(get_position_allocations_path(this_file).read_bytes())
                self.assertEqual(tombstone, payload["entry_allocations"]["BTCUSDT:L"][0])
                self.assertEqual([proof_tombstone], payload["entry_allocations"]["ETHUSDT:L"])
                if qty < 0.1:
                    record = payload["open_position_records"]["BTCUSDT:L"]
                    self.assertAlmostEqual(0.1 - qty, record["data"]["qty"])
                    self.assertEqual(30000.0, record["data"]["entry_price"])
                    self.assertAlmostEqual((0.1 - qty) * 30000.0, record["data"]["margin_usdt"])
                    self.assertEqual(["Active"], [entry["status"] for entry in record["allocations"]])
                else:
                    self.assertNotIn("BTCUSDT:L", payload["open_position_records"])
                    self.assertNotIn("BTCUSDT", window._entry_intervals)


if __name__ == "__main__":
    unittest.main()
