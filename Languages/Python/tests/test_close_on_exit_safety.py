import unittest
from types import SimpleNamespace
from unittest.mock import Mock, patch

import PyQt6

from app.gui.positions import tracking_runtime
from app.gui.runtime.strategy.stop_runtime import stop_strategy_sync
from app.gui.runtime.window import window_events_runtime


class Signal:
    def __init__(self):
        self.callbacks = []

    def connect(self, callback):
        self.callbacks.append(callback)

    def emit(self, *args):
        for callback in list(self.callbacks):
            callback(*args)


class OfflineWorker:
    def __init__(self, fn, **_kwargs):
        self.fn = fn
        self.done = Signal()
        self.progress = Signal()
        self.finished = Signal()
        self.start = Mock()
        self.deleteLater = Mock()

    def complete(self):
        try:
            result = self.fn()
        except Exception as exc:
            self.done.emit(None, exc)
        else:
            self.done.emit(result, None)
        self.finished.emit()


def stopped_result():
    return {
        "ok": True, "engines_stopped": True, "close_all_result": [],
        "cancel_open_orders_after_close": {"ok": True},
    }


class CloseOnExitSafetyTests(unittest.TestCase):
    def setUp(self):
        self.auth = {"mode": "Testnet", "account_type": "Futures", "api_key": "offline-fixture"}
        self.client = SimpleNamespace(
            futures_position_information=Mock(return_value=[]),
            futures_account=Mock(side_effect=OSError("offline fallback unavailable")),
            futures_get_open_orders=Mock(return_value=[]),
            get_account=Mock(return_value={"balances": [{"asset": "USDT", "free": "5", "locked": "0"}]}),
            get_open_orders=Mock(return_value=[]),
        )
        self.wrapper = SimpleNamespace(
            client=self.client,
            list_open_futures_positions=self.client.futures_position_information,
            get_order_intent_status=Mock(return_value={"storage_ready": True, "unresolved_count": 0}),
            _chart_debug_log=Mock(),
        )
        self.window = SimpleNamespace(
            _close_in_progress=False, _force_close=False,
            _snapshot_auth_state=lambda: dict(self.auth),
            _build_wrapper_from_values=Mock(return_value=self.wrapper),
            shared_binance=self.wrapper,
            _handle_close_all_result=Mock(),
            _chart_debug_log=Mock(), log=Mock(), close=Mock(),
        )
        self.app = SimpleNamespace(_exiting=False, _bot_arm_hard_exit=Mock(), quit=Mock())
        self.qt = SimpleNamespace(
            QMessageBox=Mock(), QWidget=SimpleNamespace(close=Mock()),
            QApplication=SimpleNamespace(instance=lambda: self.app),
        )
        self.stop = Mock(return_value=stopped_result())
        self.addCleanup(patch.stopall)
        patch.object(PyQt6, "QtWidgets", self.qt).start()
        patch.object(window_events_runtime, "QtWidgets", self.qt).start()
        patch.object(tracking_runtime, "_STOP_STRATEGY_SYNC", self.stop).start()
        patch("app.gui.runtime.background_workers.CallWorker", OfflineWorker).start()

    def begin(self):
        tracking_runtime._begin_close_on_exit_sequence(self.window)
        return self.window._bg_workers[-1]

    def assert_held_open(self):
        self.assertFalse(self.window._force_close)
        self.qt.QWidget.close.assert_not_called()
        self.assertTrue(self.qt.QMessageBox.warning.called)
        self.assertFalse(self.window._close_in_progress)

    def test_snapshot_failure_holds_exit_and_cleans_worker(self):
        self.client.futures_position_information.side_effect = OSError("offline snapshot unavailable")
        worker = self.begin()
        worker.complete()
        self.assert_held_open()
        self.assertEqual([], self.window._bg_workers)
        worker.deleteLater.assert_called_once()

    def test_malformed_snapshots_cannot_authorize_exit(self):
        for snapshot in (None, {}, [None], [{}], [{"symbol": "BTCUSDT", "positionAmt": "NaN"}],
                         [{"symbol": "BTCUSDT", "positionAmt": False}],
                         [{"symbol": "BTCUSDT", "positionAmt": "1e-999"}]):
            with self.subTest(snapshot=snapshot):
                self.client.futures_position_information.return_value = snapshot
                self.begin().complete()
                self.assert_held_open()

    def test_remaining_hedge_side_prevents_exit(self):
        self.client.futures_position_information.return_value = [
            {"symbol": "BTCUSDT", "positionAmt": "0", "positionSide": "LONG"},
            {"symbol": "BTCUSDT", "positionAmt": "-1", "positionSide": "SHORT"},
        ]
        self.begin().complete()
        self.assert_held_open()

    def test_verified_flat_exit_uses_captured_auth_in_worker_not_shared_cache(self):
        wrong_wrapper = SimpleNamespace(list_open_futures_positions=Mock(return_value=[]))
        self.window.shared_binance = wrong_wrapper
        worker = self.begin()
        result = worker.fn()
        self.window._build_wrapper_from_values.assert_called_once_with(self.auth)
        self.client.futures_position_information.assert_called_once()
        self.wrapper.get_order_intent_status.assert_called_once()
        worker.done.emit(result, None)
        self.client.futures_position_information.assert_called_once()
        wrong_wrapper.list_open_futures_positions.assert_not_called()
        self.assertTrue(self.window._force_close)
        self.qt.QWidget.close.assert_called_once_with(self.window)

    def test_invalid_or_failed_stop_results_hold_exit_even_when_flat(self):
        bad_results = (None, {}, {"ok": False}, {"ok": "true"},
                       {**stopped_result(), "engines_stopped": False},
                       {**stopped_result(), "warnings": ["engine could not be paused"]},
                       {**stopped_result(), "close_all_result": None},
                       {**stopped_result(), "close_all_result": [None]},
                       {**stopped_result(), "close_all_result": [{"ok": False}]},
                       {**stopped_result(), "close_all_result": [{"ok": True, "skipped": True}]},
                       {**stopped_result(), "cancel_open_orders_after_close": {"ok": False}})
        for result in bad_results:
            with self.subTest(result=result):
                self.stop.return_value = result
                self.begin().complete()
                self.assert_held_open()

    def test_unavailable_worker_or_worker_exception_holds_exit(self):
        for stop in (None, Mock(side_effect=RuntimeError("offline stop failed"))):
            with self.subTest(stop=stop), patch.object(tracking_runtime, "_STOP_STRATEGY_SYNC", stop):
                self.begin().complete()
                self.assert_held_open()

    def test_unverified_open_orders_hold_exit(self):
        for orders in (None, {}, [{"symbol": "BTCUSDT", "orderId": 1}]):
            with self.subTest(orders=orders):
                self.client.futures_get_open_orders.return_value = orders
                self.begin().complete()
                self.assert_held_open()

    def test_unresolved_or_unavailable_intent_state_holds_exit(self):
        for status in (None, {}, {"storage_ready": True, "unresolved_count": 1},
                       {"storage_ready": True, "unresolved_count": False},
                       {"storage_ready": False, "unresolved_count": 0}):
            with self.subTest(status=status):
                self.wrapper.get_order_intent_status.return_value = status
                self.begin().complete()
                self.assert_held_open()

    def test_account_change_during_worker_does_not_apply_old_results_or_exit(self):
        worker = self.begin()
        result = worker.fn()
        self.auth["api_key"] = "other-offline-account"
        worker.done.emit(result, None)
        self.assert_held_open()
        self.window._handle_close_all_result.assert_not_called()

    def test_duplicate_close_request_does_not_start_second_worker(self):
        worker = self.begin()
        tracking_runtime._begin_close_on_exit_sequence(self.window)
        self.assertEqual([worker], self.window._bg_workers)

    def test_auth_capture_failure_clears_close_guard(self):
        self.window._snapshot_auth_state = Mock(side_effect=RuntimeError("offline auth unavailable"))
        tracking_runtime._begin_close_on_exit_sequence(self.window)
        self.assert_held_open()

    def test_spot_remaining_free_or_locked_balance_prevents_exit(self):
        self.auth["account_type"] = "Spot"
        for free, locked in (("1", "0"), ("0", "1"), ("0.000000001", "0")):
            with self.subTest(free=free, locked=locked):
                self.client.get_account.return_value = {"balances": [{"asset": "BTC", "free": free, "locked": locked}]}
                self.begin().complete()
                self.assert_held_open()

    def test_spot_malformed_balance_snapshot_prevents_exit(self):
        self.auth["account_type"] = "Spot"
        for account in (None, {}, {"balances": [None]}, {"balances": [{"asset": "BTC"}]},
                        {"balances": [{"asset": "BTC", "free": "NaN", "locked": "0"}]},
                        {"balances": [{"asset": "BTC", "free": "-1", "locked": "0"}]},
                        {"balances": [{"asset": "BTC", "free": False, "locked": "0"}]}):
            with self.subTest(account=account):
                self.client.get_account.return_value = account
                self.begin().complete()
                self.assert_held_open()

    def test_spot_verified_cash_only_account_can_exit(self):
        self.auth["account_type"] = "Spot"
        self.begin().complete()
        self.client.get_account.assert_called_once()
        self.client.get_open_orders.assert_called_once()
        self.assertTrue(self.window._force_close)

    def test_close_event_does_not_arm_hard_exit_while_verification_is_pending(self):
        self.window.cb_close_on_exit = SimpleNamespace(isChecked=lambda: True)
        self.window._begin_close_on_exit_sequence = Mock()
        event = Mock()
        with patch.object(window_events_runtime, "log_window_event"), \
             patch.object(window_events_runtime, "should_block_spontaneous_close", return_value=False), \
             patch.object(window_events_runtime, "allow_guard_bypass", return_value=True):
            window_events_runtime.close_event(self.window, event)
        event.ignore.assert_called_once()
        self.window._begin_close_on_exit_sequence.assert_called_once()
        self.assertFalse(self.app._exiting)
        self.app._bot_arm_hard_exit.assert_not_called()

    def test_real_stop_helper_retains_live_engine_then_allows_verified_retry(self):
        engine = SimpleNamespace(stop=Mock(), join=Mock(), is_alive=Mock(return_value=True))
        self.window.strategy_engines = {"BTCUSDT|1m": engine}
        self.window._engine_indicator_map = {"BTCUSDT|1m": {"rsi": True}}
        self.window._service_request_stop = Mock()
        self.window._close_all_positions_blocking = Mock(return_value=[])
        self.wrapper.cancel_all_open_futures_orders = Mock(return_value={"ok": True})
        with patch.object(tracking_runtime, "_STOP_STRATEGY_SYNC", stop_strategy_sync):
            self.begin().complete()
            self.assert_held_open()
            self.assertIs(engine, self.window.strategy_engines["BTCUSDT|1m"])
            engine.is_alive.return_value = False
            self.begin().complete()
        self.assertEqual({}, self.window.strategy_engines)
        self.assertTrue(self.window._force_close)
        self.qt.QWidget.close.assert_called_once()
        self.assertEqual(2, engine.stop.call_count)

    def test_new_engine_between_verification_and_callback_prevents_exit(self):
        worker = self.begin()
        result = worker.fn()
        self.window.strategy_engines = {"ETHUSDT|5m": object()}
        worker.done.emit(result, None)
        self.assert_held_open()

    def test_callback_rejects_unverified_or_invalid_worker_envelopes(self):
        for result in (None, {}, {"verified_flat": "true"},
                       {"verified_flat": True, "stop_result": {"ok": False}}):
            with self.subTest(result=result):
                worker = self.begin()
                worker.done.emit(result, None)
                self.assert_held_open()

    def test_recheck_or_result_application_error_keeps_exit_blocked(self):
        for failing_method in ("_snapshot_auth_state", "_handle_close_all_result"):
            with self.subTest(method=failing_method):
                worker = self.begin()
                result = worker.fn()
                with patch.object(self.window, failing_method, side_effect=RuntimeError("offline callback failure")):
                    worker.done.emit(result, None)
                self.assert_held_open()

    def test_final_close_exception_clears_force_close_flag(self):
        self.qt.QWidget.close.side_effect = RuntimeError("offline QWidget failure")
        self.begin().complete()
        self.assertFalse(self.window._force_close)
        self.assertFalse(self.window._close_in_progress)
        self.qt.QMessageBox.warning.assert_called_once()

    def test_worker_start_failure_cleans_guard_and_worker_reference(self):
        class FailingWorker(OfflineWorker):
            def __init__(self, *args, **kwargs):
                super().__init__(*args, **kwargs)
                self.start.side_effect = RuntimeError("offline start failure")

        with patch("app.gui.runtime.background_workers.CallWorker", FailingWorker):
            tracking_runtime._begin_close_on_exit_sequence(self.window)
        self.assert_held_open()
        self.assertEqual([], self.window._bg_workers)

    def test_unknown_account_type_cannot_be_verified(self):
        self.auth["account_type"] = "Unknown"
        self.begin().complete()
        self.assert_held_open()

    def test_final_intent_read_failure_cannot_be_replaced_by_flat_positions(self):
        self.wrapper.get_order_intent_status.side_effect = OSError("offline ledger unavailable")
        self.begin().complete()
        self.assert_held_open()


if __name__ == "__main__":
    unittest.main()
