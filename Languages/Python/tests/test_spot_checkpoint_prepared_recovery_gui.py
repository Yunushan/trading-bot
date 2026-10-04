"""Explicit GUI prepared recovery uses real local protocol and fake protected APIs."""
from copy import deepcopy
from dataclasses import replace
import json
from types import SimpleNamespace
import unittest
from unittest.mock import patch

import test_spot_buy_recovery_gui as gui_fixture
import test_spot_inventory_namespace_integration as account_fixture
from spot_inventory_checkpoint_fixtures import CheckpointFixtureBackend
from app.gui.runtime.account import spot_buy_recovery_runtime as gui
from app.gui.shared import allocation_persistence as allocations
from app.integrations.exchanges.binance.orders import spot_desktop_buy_recovery_runtime as desktop
from app.integrations.exchanges.binance.orders import spot_fill_recovery_runtime as fills
from app.integrations.exchanges.binance.orders import spot_inventory_checkpoint as core
from app.integrations.exchanges.binance.orders import spot_inventory_checkpoint_runtime as runtime
from app.integrations.exchanges.binance.orders.spot_inventory_namespace_runtime import publish_owned_spot_fill
from app.settings.live_safety import LiveTradingSafetyError

_ACTUAL_DISCOVER = gui._discover
_ACTUAL_PREPARED = gui._recover_prepared


class SpotCheckpointPreparedRecoveryGuiTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        gui_fixture.SpotBuyRecoveryGuiTests.setUpClass()

    def setUp(self):
        # Shield initial ordinary GUI scaffolding, then give the actual protocol
        # its own explicit empty protected store before creating account history.
        self.enterContext(CheckpointFixtureBackend(simulate_windows=True))
        self.ui = gui_fixture.SpotBuyRecoveryGuiTests("runTest")
        self.addCleanup(self.ui.doCleanups)
        self.ui.setUp()
        self.f = account_fixture.SpotInventoryNamespaceIntegrationTests("runTest")
        self.addCleanup(self.f.doCleanups)
        self.f.setUp()
        self.backend = self.enterContext(CheckpointFixtureBackend(simulate_windows=True))
        self.account = self.f.account("prepared-gui", 889001, accepted=False)
        self.window = self.ui.window
        self.enterContext(patch.object(gui, "_allocation_path", return_value=self.f.path))
        self.enterContext(patch.object(desktop, "_canonical_path", return_value=self.f.path))
        with self.f.account_home(self.account):
            self.assertTrue(runtime.bootstrap_owned_inventory_checkpoint(self.account.wrapper, allocation_path=self.f.path))
        self.assertTrue(self.window._reload_position_allocation_snapshot("Live"))
        self.old_maps = (self.window._entry_allocations, self.window._open_position_records)
        self.record = self.f.author_accepted(self.account, self.f.fill)
        with self.f.account_home(self.account), patch.object(core, "_finish", side_effect=OSError("Synthetic prepared crash")), \
             self.assertRaises(LiveTradingSafetyError):
            publish_owned_spot_fill(self.account.wrapper, self.f.path, self.f.fill,
                expected_record=self.record, operation=fills._persist_spot_buy_allocation_unlocked)
        self.assertEqual("pending", json.loads(next(iter(self.backend.store.values())))["state"])
        self.account.owner.close()
        self.wrapper = self.f.new_wrapper(self.account.wrapper.api_key, self.account.wrapper.api_secret,
                                          self.account.home, self.account.venue)
        self.window.shared_binance = self.wrapper
        self.window.api_key_edit.setText(self.wrapper.api_key)
        self.window.api_secret_edit.setText(self.wrapper.api_secret)
        self.window.connector_combo.addItem("binance-sdk-spot")
        self.window.connector_combo.setCurrentText("binance-sdk-spot")
        self.window._create_binance_wrapper.return_value = self.wrapper
        self.window._reload_position_allocation_snapshot.reset_mock()
        self.discover = self.enterContext(patch.object(gui, "_discover", wraps=_ACTUAL_DISCOVER))
        self.prepared = self.enterContext(patch.object(gui, "_recover_prepared", wraps=_ACTUAL_PREPARED))
        self.before = self.durable()
        self.dialog = self.ui._dialog()

    def durable(self):
        return self.f.durable_bytes(self.account), deepcopy(self.backend.store)

    def discover_pending(self):
        self.dialog.discover()
        self.assertIsNotNone(self.dialog._worker)
        self.dialog._worker.complete()
        self.assertIsNotNone(self.dialog._discovery, self.dialog.status_label.text())
        self.assertEqual(1, len(self.dialog._discovery.items))
        self.assertIsInstance(self.dialog._discovery.items[0], desktop.SpotDesktopBuyRecoveryWorkItem)
        self.assertTrue(self.dialog._discovery.items[0].checkpoint_pending)
        return self.dialog._discovery.items[0]

    def test_read_only_pending_discovery_blocks_old_maps_without_loading_or_publishing(self):
        self.assertTrue(self.window._allocation_snapshot_session.ready)
        self.discover_pending()
        self.assertFalse(self.window._allocation_snapshot_session.ready)
        self.assertIs(self.old_maps[0], self.window._entry_allocations)
        self.assertIs(self.old_maps[1], self.window._open_position_records)
        self.window._reload_position_allocation_snapshot.assert_not_called()
        self.assertTrue(self.dialog.recover_btn.isEnabled())
        self.assertTrue(self.window._spot_buy_recovery_fence)
        self.assertEqual(self.before, self.durable())
        self.prepared.assert_not_called()
        self.assertEqual([], self.f.order_calls)

    def test_selected_wrapper_session_or_generation_change_fences_before_helper(self):
        self.discover_pending()
        changes = (("shared_binance", object()),
                   ("_allocation_snapshot_session", allocations.AllocationSnapshotSession()),
                   ("_account_observation_generation", 1))
        for name, value in changes:
            with self.subTest(field=name):
                original = getattr(self.window, name, 0)
                setattr(self.window, name, value)
                try:
                    self.dialog.recover_selected()
                    self.assertIsNone(self.dialog._worker)
                    self.prepared.assert_not_called()
                    self.assertEqual(self.before, self.durable())
                finally:
                    setattr(self.window, name, original)
        self.assertTrue(self.window._spot_buy_recovery_fence)
        self.assertEqual([], self.f.order_calls)

    def test_selection_changed_after_worker_queue_is_rejected_before_helper(self):
        self.discover_pending()
        self.dialog.recover_selected()
        worker = self.dialog._worker
        self.assertIsNotNone(worker)
        self.window.shared_binance = object()
        worker.complete()
        self.prepared.assert_not_called()
        self.assertEqual(self.before, self.durable())
        self.window._reload_position_allocation_snapshot.assert_not_called()
        self.assertTrue(self.window._spot_buy_recovery_fence)

    def test_genuine_selected_completion_runs_once_then_actual_reload_and_rediscovery(self):
        item = self.discover_pending()
        self.dialog.recover_selected()
        worker = self.dialog._worker
        self.dialog.recover_selected()
        self.assertIs(worker, self.dialog._worker)
        worker.complete()
        self.prepared.assert_called_once()
        self.assertIs(item, self.prepared.call_args.args[1])
        self.window._reload_position_allocation_snapshot.assert_called_once_with("Live")
        self.assertTrue(self.window._allocation_snapshot_session.ready)
        self.assertIsNot(self.old_maps[0], self.window._entry_allocations)
        self.assertIsNot(self.old_maps[1], self.window._open_position_records)
        self.assertEqual("stable", json.loads(next(iter(self.backend.store.values())))["state"])
        row = self.window._entry_allocations[("BTCUSDT", "L")][0]
        self.assertAlmostEqual(float(self.f.fill["net_qty"]), row["qty"])
        self.assertTrue(self.f.ledger(self.account)["intents"][account_fixture.CLIENT]["portfolio_reconciled"])
        self.assertTrue(self.window._spot_buy_recovery_fence)
        self.assertIsNotNone(self.dialog._worker)
        self.dialog._worker.complete()
        self.assertEqual(2, self.discover.call_count)
        self.assertFalse(self.window._spot_buy_recovery_fence)
        self.assertFalse(self.dialog.recover_btn.isEnabled())
        self.assertEqual([], self.f.order_calls)
        self.window.start_strategy.assert_not_called()

    def test_untyped_pending_flag_never_enables_or_dispatches_recovery(self):
        item = self.discover_pending()
        fake = SimpleNamespace(authority=item.authority, client_order_id=item.client_order_id,
            symbol=item.symbol, order_id=item.order_id, exchange_status=item.exchange_status,
            checkpoint_pending=True)
        self.discover.side_effect = None
        self.discover.return_value = desktop.SpotDesktopBuyRecoveryDiscovery(item.authority, (fake,), 1, 1)
        self.dialog.discover()
        self.dialog._worker.complete()
        self.assertFalse(self.dialog.recover_btn.isEnabled())
        self.dialog.recover_selected()
        self.assertIsNone(self.dialog._worker)
        self.prepared.assert_not_called()
        self.assertEqual(self.before, self.durable())

    def test_typed_nonprepared_item_cannot_bypass_blocked_session(self):
        item = self.discover_pending()
        self.dialog._discovery = replace(self.dialog._discovery, items=(replace(item, checkpoint_pending=False),))
        self.dialog.recover_selected()
        self.assertIsNone(self.dialog._worker)
        self.prepared.assert_not_called()
        self.ui.recover_core.assert_not_called()
        self.assertEqual(self.before, self.durable())

    def test_missing_exact_journal_blocks_discovery_without_source_or_marker_change(self):
        pending = json.loads(next(iter(self.backend.store.values())))
        journal = core._journal(self.f.path, pending)
        self.assertTrue(journal.is_file())
        journal.unlink()
        self.dialog.discover()
        self.dialog._worker.complete()
        self.assertFalse(self.dialog.recover_btn.isEnabled())
        self.assertIsNone(self.dialog._discovery)
        self.assertTrue(self.window._spot_buy_recovery_fence)
        self.prepared.assert_not_called()
        self.assertEqual(self.before, self.durable())
        self.assertFalse(journal.exists())
        self.assertEqual([], self.f.order_calls)


if __name__ == "__main__":
    unittest.main()
