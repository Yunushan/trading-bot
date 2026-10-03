"""Explicit desktop recovery uses fresh selected-account authority."""
from __future__ import annotations

import os
import socket
import tempfile
import threading
import time
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock, patch

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PyQt6 import QtCore, QtWidgets  # noqa: E402
from app.gui.dashboard import actions_runtime, state_runtime  # noqa: E402
from app.gui.runtime.account import spot_buy_recovery_runtime as recovery  # noqa: E402
from app.gui.runtime.background_workers import CallWorker  # noqa: E402
from app.gui.shared import allocation_persistence as allocations  # noqa: E402
from app.gui.shared.allocation_reconciliation import allocation_publication_pending  # noqa: E402
from app.integrations.exchanges.binance.orders import spot_desktop_buy_recovery_runtime as core  # noqa: E402

_ACTUAL_DISCOVER = recovery._discover
_ACTUAL_RECOVER = recovery._recover


class ManualWorker(QtCore.QObject):
    done = QtCore.pyqtSignal(object, object)
    finished = QtCore.pyqtSignal()

    def __init__(self, fn, *, parent):
        super().__init__(parent)
        self.fn = fn

    def start(self):
        pass

    def complete(self):
        try:
            result = self.fn()
        except Exception as exc:
            self.done.emit(None, exc)
        else:
            self.done.emit(result, None)
        self.finished.emit()


class SpotBuyRecoveryGuiTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.application = QtWidgets.QApplication.instance() or QtWidgets.QApplication([])

    def setUp(self):
        self.enterContext(patch.object(socket.socket, "connect", side_effect=AssertionError("No network in GUI fixture")))
        self.window = QtWidgets.QWidget()
        self.addCleanup(self.window.close)
        self.window.config = {}
        self.window._llm_settings_panels = []
        self.window._indicator_runtime_controls = []
        for name in (
            "start_strategy", "stop_strategy_async", "save_config", "load_config",
            "_on_desktop_service_api_enabled_toggled", "_apply_desktop_service_api_ui_settings",
            "_open_desktop_service_api_dashboard", "_recheck_desktop_service_preflight",
            "_refresh_desktop_service_api_ui", "_set_runtime_controls_enabled",
        ):
            setattr(self.window, name, Mock())
        for name in (
            "api_key_edit", "api_secret_edit", "mode_combo", "theme_combo", "design_combo", "account_combo",
            "account_mode_combo", "connector_combo", "leverage_spin", "margin_mode_combo", "position_mode_combo",
            "assets_mode_combo", "tif_combo", "gtd_minutes_spin", "ind_source_combo", "symbol_list",
            "refresh_symbols_btn", "interval_list", "custom_interval_edit", "add_interval_btn", "side_combo",
            "pospct_spin", "loop_combo", "lead_trader_enable_cb", "lead_trader_combo", "cb_live_indicator_values",
            "cb_add_only", "allow_opposite_checkbox", "cb_stop_without_close", "cb_close_on_exit",
            "stop_loss_enable_cb", "stop_loss_mode_combo", "stop_loss_usdt_spin", "stop_loss_percent_spin",
            "stop_loss_scope_combo", "template_combo",
        ):
            setattr(self.window, name, QtWidgets.QWidget(self.window))
        self.window.api_key_edit = QtWidgets.QLineEdit("synthetic-key", self.window)
        self.window.api_secret_edit = QtWidgets.QLineEdit("synthetic-secret", self.window)
        for name, value in (("mode_combo", "Live"), ("account_combo", "Spot"), ("connector_combo", "python-binance")):
            combo = QtWidgets.QComboBox(self.window)
            combo.addItems([value, "Other"])
            setattr(self.window, name, combo)
        self.window._snapshot_auth_state = lambda: {
            "api_key": self.window.api_key_edit.text(), "api_secret": self.window.api_secret_edit.text(),
            "mode": self.window.mode_combo.currentText(), "account_type": self.window.account_combo.currentText(),
        }
        self.window._runtime_connector_backend = lambda **kwargs: self.window.connector_combo.currentText()
        self.wrapper = SimpleNamespace(
            api_key="synthetic-key", api_secret="synthetic-secret", mode="Live", account_type="SPOT",
            _ensure_spot_execution_owner=Mock(side_effect=AssertionError("No owner arm")),
            place_order=Mock(side_effect=AssertionError("No exchange orders")),
        )
        self.window.shared_binance = self.wrapper
        self.window.strategy_engines = {}
        self.window._create_binance_wrapper = Mock(return_value=self.wrapper)
        directory = Path(self.enterContext(tempfile.TemporaryDirectory()))
        source_file = directory / "Python" / "app" / "gui" / "window_shell.py"
        source_file.parent.mkdir(parents=True)
        self.path = allocations.get_position_allocations_path(source_file)
        self.enterContext(patch.object(core, "_canonical_path", return_value=self.path))
        self.enterContext(patch.object(recovery, "_allocation_path", return_value=self.path))
        self.enterContext(patch.object(recovery, "CallWorker", ManualWorker))
        self.window._allocation_snapshot_session = allocations.AllocationSnapshotSession()
        self.window._entry_allocations = {}
        self.window._open_position_records = {}
        def loader(**kwargs):
            return allocations.load_position_allocations(this_file=source_file, **kwargs)
        self.enterContext(patch.object(state_runtime, "_LOAD_POSITION_ALLOCATIONS", loader))
        self.window._reload_position_allocation_snapshot = Mock(
            side_effect=lambda mode: state_runtime._reload_position_allocation_snapshot(self.window, mode)
        )
        self.assertTrue(self.window._reload_position_allocation_snapshot("Live"))
        self.window._reload_position_allocation_snapshot.reset_mock()
        self.authority = core.SpotDesktopBuyRecoveryAuthority(
            self.wrapper, 123, "live", directory / "intent.json", {"environment": "live"}, "synthetic-store",
            self.path, (),
        )
        self.item = core.SpotDesktopBuyRecoveryWorkItem(
            self.authority, "durable-buy-1", "BTCUSDT", 101, "FILLED", {}, "synthetic-proof",
        )
        self.discovery = core.SpotDesktopBuyRecoveryDiscovery(self.authority, (self.item,), 1, 0)
        self.discover_core = self.enterContext(patch.object(recovery, "_discover", return_value=self.discovery))
        self.recover_core = self.enterContext(patch.object(recovery, "_recover", side_effect=self._publish))

    def _publish(self, wrapper, item, *, allocation_path, receipt, handoff):
        with handoff():
            receipt.session.invalidate("synthetic core publication")
            payload = {"version": 1, "mode": "Live", "entry_allocations": {}, "open_position_records": {}}
            allocation_path.parent.mkdir(parents=True, exist_ok=True)
            allocations._write_snapshot(allocation_path, payload)
            committed = allocations._read_receipt(allocation_path)
            generation = receipt.session._generation
        return {
            "portfolio_reconciled": True, "allocation_published": True, "client_order_id": item.client_order_id,
            "account_uid": 123, "environment": "live", "store_id": "synthetic-store",
            "allocation_receipt": committed, "session_generation": generation,
        }

    def _dialog(self):
        dialog = recovery.open_spot_buy_recovery(self.window)
        self.addCleanup(dialog.close)
        return dialog

    def _discovered_dialog(self):
        dialog = self._dialog()
        dialog.discover()
        dialog._worker.complete()
        return dialog

    def test_dashboard_exposes_explicit_spot_buy_recovery_action(self):
        layout = QtWidgets.QVBoxLayout(self.window)
        actions_runtime._create_dashboard_action_section(self.window, layout)
        button = getattr(self.window, "spot_buy_recovery_btn", None)
        self.assertIsInstance(button, QtWidgets.QPushButton)
        self.assertEqual("Spot BUY Recovery", button.text())
        self.window.start_strategy.assert_not_called()

    def test_action_opens_one_dialog_without_automatic_discovery_or_owner_arm(self):
        actions_runtime._create_dashboard_action_section(self.window, QtWidgets.QVBoxLayout(self.window))
        self.window.spot_buy_recovery_btn.click()
        dialog = self.window._spot_buy_recovery_dialog
        self.addCleanup(dialog.close)
        self.window.spot_buy_recovery_btn.click()
        self.assertIs(dialog, self.window._spot_buy_recovery_dialog)
        self.discover_core.assert_not_called()
        self.wrapper._ensure_spot_execution_owner.assert_not_called()
        self.wrapper.place_order.assert_not_called()
        self.window.start_strategy.assert_not_called()

    def test_discovery_verifies_before_actual_two_map_reload_and_lists_exact_work(self):
        dialog = self._dialog()
        dialog.discover()
        self.window._reload_position_allocation_snapshot.assert_not_called()
        self.assertTrue(allocation_publication_pending(self.window))
        worker = dialog._worker
        dialog.discover()
        self.assertIs(worker, dialog._worker)
        worker.complete()
        self.discover_core.assert_called_once_with(self.wrapper, self.path)
        self.window._reload_position_allocation_snapshot.assert_called_once_with("Live")
        self.assertTrue(self.window._allocation_snapshot_session.ready)
        self.assertIn("eligible BUY fills: 1", dialog.count_label.text())
        self.assertEqual(["durable-buy-1", "BTCUSDT", "101", "FILLED", ""],
                         [dialog.table.item(0, col).text() for col in range(5)])
        self.assertTrue(dialog.recover_btn.isEnabled())
        self.assertTrue(allocation_publication_pending(self.window))

    def test_wrong_mode_or_running_engine_fences_without_discovery(self):
        dialog = self._dialog()
        self.window.mode_combo.setCurrentText("Other")
        dialog.discover()
        self.assertIn("Live Spot", dialog.status_label.text())
        self.window.mode_combo.setCurrentText("Live")
        self.window.strategy_engines = {"one": object()}
        dialog.discover()
        self.assertIn("Stop the strategy", dialog.status_label.text())
        self.discover_core.assert_not_called()
        self.assertTrue(allocation_publication_pending(self.window))

    def test_signed_discovery_error_and_busy_owner_remain_blocked(self):
        dialog = self._dialog()
        self.discover_core.side_effect = RuntimeError("execution owner is active")
        dialog.discover()
        dialog._worker.complete()
        self.assertIn("execution owner is active", dialog.status_label.text())
        self.window._reload_position_allocation_snapshot.assert_not_called()
        self.assertFalse(dialog.recover_btn.isEnabled())
        self.assertTrue(allocation_publication_pending(self.window))

    def test_discovery_errors_never_expose_selected_raw_credentials(self):
        dialog = self._dialog()
        self.discover_core.side_effect = RuntimeError("synthetic-key and synthetic-secret failed")
        dialog.discover()
        dialog._worker.complete()
        self.assertNotIn("synthetic-key", dialog.status_label.text())
        self.assertNotIn("synthetic-secret", dialog.status_label.text())
        self.assertIn("<redacted>", dialog.status_label.text())

    def test_changed_credentials_reject_stale_discovery_before_reload(self):
        dialog = self._dialog()
        dialog.discover()
        self.window.api_secret_edit.setText("new-synthetic-secret")
        dialog._worker.complete()
        self.window._reload_position_allocation_snapshot.assert_not_called()
        self.assertFalse(dialog.recover_btn.isEnabled())
        self.assertIn("changed", dialog.status_label.text())
        self.assertTrue(allocation_publication_pending(self.window))

    def test_unsupported_unresolved_work_keeps_fence_and_unrelated_pending(self):
        self.discover_core.return_value = core.SpotDesktopBuyRecoveryDiscovery(self.authority, (), 2, 2)
        self.window._pending_allocation_reconciliations = {("ETHUSDT", "L"): [{"event": "unrelated"}]}
        dialog = self._discovered_dialog()
        self.assertIn("operator recovery required: 2", dialog.count_label.text())
        self.assertTrue(self.window._spot_buy_recovery_fence)
        self.assertEqual({("ETHUSDT", "L"): [{"event": "unrelated"}]}, self.window._pending_allocation_reconciliations)

    def test_changed_complete_maps_block_before_recovery_worker(self):
        dialog = self._discovered_dialog()
        self.window._entry_allocations[("BTCUSDT", "L")] = [{"tampered": True}]
        dialog.recover_selected()
        self.recover_core.assert_not_called()
        self.assertIsNone(dialog._worker)
        self.assertIn("maps differ", dialog.status_label.text())
        self.assertTrue(allocation_publication_pending(self.window))

    def test_account_change_after_capture_rejects_handoff_before_any_write(self):
        dialog = self._discovered_dialog()
        dialog.recover_selected()
        worker = dialog._worker
        self.window.api_key_edit.setText("different-key")
        worker.complete()
        self.assertFalse(self.path.exists())
        self.assertIn("changed before recovery", dialog.status_label.text())
        self.assertTrue(allocation_publication_pending(self.window))

    def test_replaced_equal_maps_reject_handoff(self):
        dialog = self._discovered_dialog()
        dialog.recover_selected()
        self.window._open_position_records = dict(self.window._open_position_records)
        dialog._worker.complete()
        self.assertFalse(self.path.exists())
        self.assertIn("changed before recovery", dialog.status_label.text())

    def test_marker_failure_keeps_item_error_and_requires_fresh_discovery(self):
        dialog = self._discovered_dialog()
        self.window._reload_position_allocation_snapshot.reset_mock()

        def failure(*args, **kwargs):
            result = self._publish(*args, **kwargs)
            return {**result, "portfolio_reconciled": False, "error": "durable marker failed"}

        self.recover_core.side_effect = failure
        dialog.recover_selected()
        dialog._worker.complete()
        self.assertTrue(self.path.exists())
        self.assertFalse(self.window._allocation_snapshot_session.ready)
        self.window._reload_position_allocation_snapshot.assert_not_called()
        self.assertIn("durable marker failed", dialog.table.item(0, 4).text())
        self.assertFalse(dialog.recover_btn.isEnabled())
        self.assertTrue(allocation_publication_pending(self.window))
        dialog.discover()
        dialog._worker.complete()
        self.assertTrue(self.window._allocation_snapshot_session.ready)
        self.assertTrue(dialog.recover_btn.isEnabled())

    def test_success_requires_actual_reload_and_signed_rediscovery_before_fence_clear(self):
        dialog = self._discovered_dialog()
        self.window._reload_position_allocation_snapshot.reset_mock()
        self.discover_core.return_value = core.SpotDesktopBuyRecoveryDiscovery(self.authority, (), 0, 0)
        dialog.recover_selected()
        worker = dialog._worker
        dialog.recover_selected()
        self.assertIs(worker, dialog._worker)
        worker.complete()
        self.window._reload_position_allocation_snapshot.assert_called_once_with("Live")
        self.assertTrue(self.window._spot_buy_recovery_fence)
        self.assertIsNotNone(dialog._worker)
        dialog._worker.complete()
        self.assertFalse(self.window._spot_buy_recovery_fence)
        self.assertFalse(allocation_publication_pending(self.window))
        self.assertIn("No durable unresolved work", dialog.status_label.text())
        self.wrapper.place_order.assert_not_called()
        self.wrapper._ensure_spot_execution_owner.assert_not_called()

    def test_account_switch_after_publication_never_assigns_old_account_maps(self):
        dialog = self._discovered_dialog()
        self.window._reload_position_allocation_snapshot.reset_mock()

        def change_after_publication(*args, **kwargs):
            result = self._publish(*args, **kwargs)
            self.window._account_observation_generation = 1
            self.window.shared_binance = object()
            return result

        self.recover_core.side_effect = change_after_publication
        dialog.recover_selected()
        dialog._worker.complete()
        self.assertTrue(self.path.exists())
        self.window._reload_position_allocation_snapshot.assert_not_called()
        self.assertIn("changed after recovery", dialog.status_label.text())
        self.assertTrue(allocation_publication_pending(self.window))

    def test_failed_recovery_reload_keeps_fence_after_durable_marker(self):
        dialog = self._discovered_dialog()
        self.window._reload_position_allocation_snapshot.side_effect = lambda mode: False
        dialog.recover_selected()
        dialog._worker.complete()
        self.assertIn("reload failed", dialog.status_label.text())
        self.assertTrue(self.window._spot_buy_recovery_fence)
        self.assertFalse(self.window._allocation_snapshot_session.ready)

    def test_changed_allocation_after_publication_rejects_fresh_reload_authority(self):
        dialog = self._discovered_dialog()

        def changed_storage(*args, **kwargs):
            result = self._publish(*args, **kwargs)
            payload = {"version": 1, "mode": "Live", "entry_allocations": {}, "open_position_records": {}, "changed": True}
            allocations._write_snapshot(self.path, payload)
            return result

        self.recover_core.side_effect = changed_storage
        dialog.recover_selected()
        dialog._worker.complete()
        self.assertIn("storage changed after recovery", dialog.status_label.text())
        self.assertFalse(self.window._allocation_snapshot_session.ready)
        self.assertTrue(self.window._spot_buy_recovery_fence)

    def test_window_close_invalidates_pending_recovery_token(self):
        dialog = self._discovered_dialog()
        dialog.recover_selected()
        self.window.close()
        dialog._worker.complete()
        self.assertFalse(self.path.exists())
        self.assertTrue(self.window._spot_buy_recovery_fence)

    def test_real_worker_is_retained_until_finished_and_window_destruction_is_blocked(self):
        entered, release = threading.Event(), threading.Event()

        def wait_for_release(wrapper, allocation_path):
            entered.set()
            if not release.wait(3):
                raise RuntimeError("test release timed out")
            return self.discovery

        self.discover_core.side_effect = wait_for_release
        self.window.setAttribute(QtCore.Qt.WidgetAttribute.WA_DeleteOnClose, True)
        self.window.show()
        dialog = self._dialog()
        with patch.object(recovery, "CallWorker", CallWorker):
            dialog.discover()
        worker = dialog._worker
        try:
            self.assertTrue(entered.wait(2))
            self.assertTrue(worker.isRunning())
            self.assertFalse(self.window.close())
            self.assertIs(worker, dialog._worker)
            self.assertTrue(worker.isRunning())
            self.assertTrue(self.window.isVisible())
            self.assertIn("after it finishes", dialog.status_label.text())
        finally:
            release.set()
            self.assertTrue(worker.wait(3000))
            deadline = time.monotonic() + 3
            while dialog._worker is not None and time.monotonic() < deadline:
                self.application.processEvents()
        self.assertIsNone(dialog._worker)
        self.window._reload_position_allocation_snapshot.assert_not_called()
        self.assertTrue(self.window._spot_buy_recovery_fence)
        # Fixture cleanup must keep Python's window references valid.
        self.window.setAttribute(QtCore.Qt.WidgetAttribute.WA_DeleteOnClose, False)

    def test_recovery_reload_preserves_unrelated_in_memory_fence(self):
        self.window._pending_allocation_reconciliations = {("ETHUSDT", "L"): ["unrelated"]}
        self.discover_core.return_value = core.SpotDesktopBuyRecoveryDiscovery(self.authority, (), 0, 0)
        self._discovered_dialog()
        self.assertFalse(self.window._spot_buy_recovery_fence)
        self.assertTrue(allocation_publication_pending(self.window))
        self.assertEqual(["unrelated"], self.window._pending_allocation_reconciliations[("ETHUSDT", "L")])

    def test_actual_restart_receipt_recovers_through_dialog_action_and_reload_without_orders(self):
        from test_spot_desktop_buy_recovery_runtime import SpotDesktopBuyRecoveryTests

        scenario = SpotDesktopBuyRecoveryTests()
        scenario.setUp()
        self.addCleanup(scenario.doCleanups)
        self.wrapper = scenario.wrapper
        self.window.shared_binance = self.wrapper
        self.window.api_key_edit.setText(self.wrapper.api_key)
        self.window.api_secret_edit.setText(self.wrapper.api_secret)
        self.window._allocation_snapshot_session = scenario.window._allocation_snapshot_session
        self.window._entry_allocations = scenario.window._entry_allocations
        self.window._open_position_records = scenario.window._open_position_records
        actual_scope = recovery._selected_scope

        def ui_scope(window):
            self.assertIs(self.application.thread(), QtCore.QThread.currentThread(), "Qt controls read from a worker")
            return actual_scope(window)

        def drain_workers(dialog):
            deadline = time.monotonic() + 5
            while dialog._worker is not None and time.monotonic() < deadline:
                self.application.processEvents()
                time.sleep(0.001)
            self.assertIsNone(dialog._worker, dialog.status_label.text())

        with (
            patch.object(recovery, "_allocation_path", return_value=scenario.path),
            patch.object(core, "_canonical_path", return_value=scenario.path),
            patch.object(recovery, "_discover", _ACTUAL_DISCOVER),
            patch.object(recovery, "_recover", _ACTUAL_RECOVER),
            patch.object(recovery, "CallWorker", CallWorker),
            patch.object(recovery, "_selected_scope", ui_scope),
        ):
            actions_runtime._create_dashboard_action_section(self.window, QtWidgets.QVBoxLayout(self.window))
            self.window.spot_buy_recovery_btn.click()
            dialog = self.window._spot_buy_recovery_dialog
            self.addCleanup(dialog.close)
            self.assertIsNone(dialog._worker)
            dialog.discover_btn.click()
            drain_workers(dialog)
            self.assertEqual(1, dialog.table.rowCount(), dialog.status_label.text())
            self.assertEqual(scenario.client_id, dialog.table.item(0, 0).text())
            self.assertTrue(allocation_publication_pending(self.window))
            dialog.recover_btn.click()
            drain_workers(dialog)
            self.assertTrue(self.window._allocation_snapshot_session.ready)
            self.assertFalse(allocation_publication_pending(self.window))
            row = self.window._entry_allocations[("BTCUSDT", "L")][0]
            self.assertAlmostEqual(0.09996, row["qty"])
            self.assertEqual("RECOVERY", row["interval"])
            self.assertEqual(0, self.wrapper.get_order_intent_status()["unresolved_count"])
            self.assertEqual(1, len(scenario.actual.market_posts))
            self.assertIsNone(getattr(self.wrapper, "_spot_execution_owner", None))
            self.window.start_strategy.assert_not_called()


if __name__ == "__main__":
    unittest.main()
