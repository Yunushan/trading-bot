"""Offline regressions for desktop cleanup of exact recovered inventory."""
from __future__ import annotations

import copy
import json
import socket
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock, patch

from app.gui.dashboard import state_runtime as dashboard_state
from app.gui.shared.allocation_persistence import (
    AllocationSnapshotSession, get_position_allocations_path, load_position_allocations,
    save_position_allocations,
)
from app.gui.runtime.account import account_runtime
from app.gui.positions.history_update_close_runtime import close_confirmed_positions
from app.gui.positions.history_update_runtime import _mw_update_position_history
from app.gui.positions.tracking_runtime import _apply_close_all_to_positions_cache
from app.gui.runtime.strategy import start_runtime
from app.integrations.exchanges.binance.orders.spot_fill_recovery_runtime import (
    persist_spot_buy_allocation,
)


KEY = ("BTCUSDT", "L")
FILL = {
    "symbol": "BTCUSDT", "client_order_id": "offline-owned-buy",
    "order_id": "51", "signature": "a" * 64,
    "net_qty": "0.1", "net_quote_cost": "2000", "average_cost": "20000",
    "gross_qty": "0.1", "gross_quote_qty": "2000",
    "fill_time_ms": 1780000000000, "trade_ids": [61], "trade_count": 1,
    "commissions": [], "base_asset": "BTC", "quote_asset": "USDT",
}


class RecoveryOwnedGuiCleanupTests(unittest.TestCase):
    def setUp(self):
        self.enterContext(patch.object(socket.socket, "connect", side_effect=AssertionError("network forbidden")))
        self.temp = self.enterContext(tempfile.TemporaryDirectory(prefix="gui-owned-cleanup-"))
        self.path = Path(self.temp) / "allocations.json"
        self.assertTrue(persist_spot_buy_allocation(self.path, FILL))
        self.original_bytes = self.path.read_bytes()
        data = json.loads(self.original_bytes)
        self.allocations = {KEY: copy.deepcopy(data["entry_allocations"]["BTCUSDT:L"])}
        self.records = {KEY: copy.deepcopy(data["open_position_records"]["BTCUSDT:L"])}

    def window(self):
        return SimpleNamespace(
            config={"positions_missing_autoclose": True, "positions_missing_threshold": 1,
                    "positions_missing_grace_seconds": 0, "positions_closed_history_max": 200},
            _entry_allocations=copy.deepcopy(self.allocations),
            _open_position_records=copy.deepcopy(self.records),
            _closed_position_records=[], _closed_trade_registry={},
            _pending_close_times={KEY: "2026-10-01T12:00:00+00:00"},
            _position_missing_counts={}, _entry_intervals={"BTCUSDT": {"L": {"RECOVERY"}}},
            _entry_times={KEY: "open"}, _entry_times_by_iv={("BTCUSDT", "L", "RECOVERY"): "open"},
            guard=SimpleNamespace(clear_symbol_side=Mock(), mark_closed=Mock()),
            shared_binance=SimpleNamespace(get_balances=Mock(return_value=[])),
            account_combo=SimpleNamespace(currentText=lambda: "Spot"),
            _format_display_time=lambda value: str(value), _parse_any_datetime=lambda _value: None,
            _canonicalize_interval=lambda value: value, _track_interval_close=Mock(),
            _compute_global_pnl_totals=lambda: (0, 0), _update_global_pnl_display=Mock(),
            _render_positions_table=Mock(), log=Mock(), _chart_debug_log=Mock(),
        )

    def assert_preserved(self, window):
        self.assertEqual(self.allocations, window._entry_allocations)
        self.assertEqual(self.records, window._open_position_records)
        self.assertEqual([], window._closed_position_records)
        window.guard.clear_symbol_side.assert_not_called()
        window.guard.mark_closed.assert_not_called()
        self.assertEqual(self.original_bytes, self.path.read_bytes())
        self.assertIn(KEY, window._pending_allocation_reconciliations)

    def test_history_close_retains_actual_recovery_inventory_and_guard(self):
        window = self.window()
        close_confirmed_positions(
            window, [KEY], window._open_position_records, window._pending_close_times,
            closed_history_max=200, resolve_trigger_indicators_safe=lambda *_args: [],
            lookup_force_liquidation=lambda *_args: None,
        )
        self.assert_preserved(window)

    def test_missing_balance_retains_actual_recovery_even_with_autoclose_disabled(self):
        for autoclose in (True, False):
            with self.subTest(autoclose=autoclose):
                window = self.window()
                window.config["positions_missing_autoclose"] = autoclose
                _mw_update_position_history(window, {})
                self.assert_preserved(window)
                _mw_update_position_history(window, {})
                self.assert_preserved(window)
                self.assertEqual(1, len(window._pending_allocation_reconciliations[KEY]))

    def test_close_all_flat_receipt_retains_actual_recovery_for_exact_fill_path(self):
        window = self.window()
        _apply_close_all_to_positions_cache(window, [{
            "symbol": "BTCUSDT", "side_key": "L", "ok": True, "position_closed": True,
        }])
        self.assert_preserved(window)
        window._track_interval_close.assert_not_called()

    def test_start_rejects_pending_publication_before_service_or_owner_start(self):
        for pending, ready in (({KEY: [{"operation": "close"}]}, True), ({}, False)):
            with self.subTest(pending=pending, ready=ready):
                window = self.window()
                window.shared_binance = None
                window._pending_allocation_reconciliations = pending
                window._allocation_snapshot_session = SimpleNamespace(ready=ready)
                with patch.object(start_runtime, "_collect_strategy_start_context",
                                  return_value=SimpleNamespace(pair_entries=[])) as collect:
                    start_runtime.start_strategy(window, strategy_engine_cls=object)
                collect.assert_not_called()
                self.assertIn("allocation", str(window.log.call_args).lower())


    def test_mode_change_invalidates_before_owner_revoke_and_reloads_both_real_maps(self):
        this_file = Path(self.temp) / "pkg" / "gui" / "window.py"
        path = get_position_allocations_path(this_file)
        self.assertTrue(persist_spot_buy_allocation(path, FILL))
        window = self.window()
        window.config["mode"] = "Live"
        window._allocation_snapshot_session = AllocationSnapshotSession()
        window._reconfigure_positions_worker = Mock()
        window._reload_position_allocation_snapshot = lambda mode: dashboard_state._reload_position_allocation_snapshot(window, mode)
        observations = []

        def invalidate(_reason):
            observations.append(window._allocation_snapshot_session.ready)
            window.shared_binance = None

        window._invalidate_shared_binance = invalidate
        def loader(**kwargs):
            return load_position_allocations(this_file=this_file, **kwargs)
        with patch.object(dashboard_state, "_LOAD_POSITION_ALLOCATIONS", loader):
            self.assertTrue(window._reload_position_allocation_snapshot("Live"))
            window._entry_allocations = {("STALE", "L"): []}
            window._open_position_records = {("STALE", "L"): {}}
            account_runtime._on_mode_changed(window, "Live")
        self.assertEqual([False], observations)
        self.assertEqual(self.allocations, window._entry_allocations)
        self.assertEqual(self.records, window._open_position_records)
        self.assertTrue(window._allocation_snapshot_session.ready)
        window._reconfigure_positions_worker.assert_called_once_with()

    def test_mode_mismatch_keeps_old_maps_and_fences_publication_and_start(self):
        this_file = Path(self.temp) / "pkg" / "gui" / "window.py"
        path = get_position_allocations_path(this_file)
        self.assertTrue(persist_spot_buy_allocation(path, FILL))
        before = path.read_bytes()
        window = self.window()
        window.config["mode"] = "Live"
        window._allocation_snapshot_session = AllocationSnapshotSession()
        window._reconfigure_positions_worker = Mock()
        window._invalidate_shared_binance = Mock()
        window._reload_position_allocation_snapshot = lambda mode: dashboard_state._reload_position_allocation_snapshot(window, mode)
        def loader(**kwargs):
            return load_position_allocations(this_file=this_file, **kwargs)
        with patch.object(dashboard_state, "_LOAD_POSITION_ALLOCATIONS", loader):
            self.assertTrue(window._reload_position_allocation_snapshot("Live"))
            account_runtime._on_mode_changed(window, "Demo")
        self.assertEqual(self.allocations, window._entry_allocations)
        self.assertEqual(self.records, window._open_position_records)
        self.assertFalse(window._allocation_snapshot_session.ready)
        self.assertFalse(save_position_allocations(
            {}, {}, this_file=this_file, mode="Demo", session=window._allocation_snapshot_session,
        ))
        self.assertEqual(before, path.read_bytes())
        with patch.object(start_runtime, "_collect_strategy_start_context") as collect:
            start_runtime.start_strategy(window, strategy_engine_cls=object)
        collect.assert_not_called()
        window._reconfigure_positions_worker.assert_called_once_with()


if __name__ == "__main__":
    unittest.main()
