from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch

from app.gui.positions.actions_close_runtime import close_position_single
from app.gui.positions.actions_state_runtime import reduce_local_position_allocation_state


class InlineWorker:
    def __init__(self, operation, parent=None):
        self.operation = operation
        self.done = SimpleNamespace(connect=lambda callback: setattr(self, "callback", callback))
        self.progress = Mock()
        self.finished = Mock()
        self.deleteLater = Mock()

    def start(self):
        self.callback(self.operation(), None)


class ControlledWorker(InlineWorker):
    instances = []

    def __init__(self, operation, parent=None):
        super().__init__(operation, parent)
        self.instances.append(self)

    def start(self):
        self.response = self.operation()

    def complete(self, *, error=None):
        self.callback(self.response, error)


class QueuedWorker(ControlledWorker):
    def start(self):
        self.response = None

    def execute(self):
        self.response = self.operation()


class ManualCloseSubmissionTests(unittest.TestCase):
    def window(self, response):
        return SimpleNamespace(
            shared_binance=SimpleNamespace(
                account_type="FUTURES", get_futures_dual_side=lambda: False,
                close_futures_leg_exact=Mock(return_value=response),
                close_futures_position=Mock(side_effect=AssertionError("Targeted close widened")),
            ),
            account_combo=SimpleNamespace(currentText=lambda: "FUTURES"),
            log=Mock(), refresh_positions=Mock(),
            _reduce_local_position_allocation_state=Mock(return_value=True),
            _track_interval_close=Mock(), _clear_local_position_state=Mock(),
        )

    def close(self, window):
        with patch("app.gui.runtime.background_workers.CallWorker", InlineWorker):
            close_position_single(window, "BTCUSDT", "L", "1m", 1.0, {"trade_id": "owned"})

    def test_unfinished_or_rejected_target_never_falls_back_to_whole_symbol(self):
        for response in (
            {"ok": False, "reconciliation_required": True, "executed_qty": 0.25, "execution_confirmed": True},
            {"ok": False, "submission_attempted": True, "error": "timeout"},
            {"ok": False, "error": "preflight rejected"},
        ):
            with self.subTest(response=response):
                window = self.window(response)
                self.close(window)
                window.shared_binance.close_futures_position.assert_not_called()
                if response.get("execution_confirmed"):
                    window._reduce_local_position_allocation_state.assert_called_once_with(
                        "BTCUSDT", "L", interval="1m", qty=0.25, target_identity={"trade_id": "owned"},
                        close_result=response,
                    )
                else:
                    window._reduce_local_position_allocation_state.assert_not_called()
                window._track_interval_close.assert_not_called()
                window._clear_local_position_state.assert_not_called()
                window.refresh_positions.assert_called_once()

    def test_confirmed_capped_close_updates_only_executed_allocation(self):
        response = {"ok": True, "execution_confirmed": True, "executed_qty": 0.25, "sent_qty": 0.25}
        window = self.window(response)
        self.close(window)
        window._reduce_local_position_allocation_state.assert_called_once_with(
            "BTCUSDT", "L", interval="1m", qty=0.25, target_identity={"trade_id": "owned"},
            close_result=response,
        )
        window._track_interval_close.assert_not_called()

    def test_ack_or_already_flat_result_does_not_credit_a_fill(self):
        for response in ({"ok": True, "sent_qty": 1.0}, {"ok": True, "skipped": True}):
            with self.subTest(response=response):
                window = self.window(response)
                self.close(window)
                window._reduce_local_position_allocation_state.assert_not_called()
                window._track_interval_close.assert_not_called()

    def test_failed_target_reconciliation_retains_interval_and_reports_uncertainty(self):
        from app.gui.positions.tracking_runtime import _mw_pos_track_interval_close

        window = self.window({"ok": True, "execution_confirmed": True, "executed_qty": 1.0})
        window._reduce_local_position_allocation_state.return_value = False
        window._entry_intervals = {"BTCUSDT": {"L": {"1m"}, "S": set()}}
        window._entry_times_by_iv = {("BTCUSDT", "L", "1m"): "2026-09-06T00:00:00+00:00"}
        window._canonicalize_interval = lambda value: value
        window._track_interval_close = lambda *args: _mw_pos_track_interval_close(window, *args)
        self.close(window)
        self.assertEqual({"1m"}, window._entry_intervals["BTCUSDT"]["L"])
        self.assertIn(("BTCUSDT", "L", "1m"), window._entry_times_by_iv)
        self.assertTrue(any("tracking retained pending reconciliation" in str(call) for call in window.log.call_args_list))

    def test_reconciliation_exception_preserves_tracking_and_refreshes(self):
        window = self.window({"ok": True, "execution_confirmed": True, "executed_qty": 1.0})
        window._reduce_local_position_allocation_state.side_effect = RuntimeError("cannot attribute fill")
        self.close(window)
        window._track_interval_close.assert_not_called()
        window.refresh_positions.assert_called_once()
        self.assertTrue(any("manual_close_reconciliation" in str(call) for call in window.log.call_args_list))

    def test_failed_local_publication_retains_exact_venue_event_and_blocks_another_post(self):
        response = {
            "ok": True, "execution_confirmed": True, "executed_qty": 0.25,
            "info": {"orderId": 913, "clientOrderId": "close-owned", "status": "FILLED"},
        }
        for failure in (False, OSError("disk unavailable")):
            with self.subTest(failure=failure):
                window = self.window(response)
                if isinstance(failure, BaseException):
                    window._reduce_local_position_allocation_state.side_effect = failure
                else:
                    window._reduce_local_position_allocation_state.return_value = False
                self.close(window)
                pending = window._pending_allocation_reconciliations[("BTCUSDT", "L")]
                self.assertEqual(0.25, pending[-1]["qty"])
                self.assertEqual(response, pending[-1]["venue_result"])
                self.assertIsNot(response, pending[-1]["venue_result"])
                self.close(window)
                window.shared_binance.close_futures_leg_exact.assert_called_once()
                window._reduce_local_position_allocation_state.assert_called_once()
                window._track_interval_close.assert_not_called()

    def test_uncertain_submitted_close_is_retained_and_cannot_be_posted_again(self):
        response = {"ok": False, "submission_attempted": True,
                    "reconciliation_required": True, "error": "response lost"}
        window = self.window(response)
        self.close(window)
        pending = window._pending_allocation_reconciliations[("BTCUSDT", "L")][-1]
        self.assertEqual("uncertain_close", pending["operation"])
        self.assertEqual(response, pending["venue_result"])
        self.close(window)
        window.shared_binance.close_futures_leg_exact.assert_called_once()
        window._reduce_local_position_allocation_state.assert_not_called()

    def test_logging_exception_does_not_discard_a_confirmed_fill(self):
        response = {"ok": True, "execution_confirmed": True, "executed_qty": 0.25}
        window = self.window(response)
        window.log.side_effect = RuntimeError("UI logging unavailable")
        window._reduce_local_position_allocation_state.return_value = False
        self.close(window)
        window._reduce_local_position_allocation_state.assert_called_once()
        self.assertTrue(any(event.get("venue_result") == response
                            for event in window._pending_allocation_reconciliations[("BTCUSDT", "L")]))

    def test_actual_callback_and_reducer_propagate_failed_snapshot_publication(self):
        response = {
            "ok": True, "execution_confirmed": True, "executed_qty": 0.25,
            "info": {"orderId": 913, "clientOrderId": "close-owned", "status": "FILLED"},
        }
        window = self.window(response)
        entry = {"trade_id": "owned", "client_order_id": "entry-owned", "qty": 1.0,
                 "interval": "1m", "status": "Active"}
        key = ("BTCUSDT", "L")
        window._entry_allocations = {key: [entry.copy()]}
        window._open_position_records = {key: {"symbol": "BTCUSDT", "side_key": "L", "status": "Active",
                                               "data": {"qty": 1.0}, "allocations": [entry.copy()]}}
        window._entry_intervals = {"BTCUSDT": {"L": {"1m"}, "S": set()}}
        window._canonicalize_interval = lambda value: value
        window._reduce_local_position_allocation_state = lambda *args, **kwargs: reduce_local_position_allocation_state(
            window, *args, **kwargs,
        )
        saver = Mock(return_value=False)
        with patch("app.gui.positions.actions_state_runtime.get_save_position_allocations", return_value=saver):
            self.close(window)
        saver.assert_called_once()
        self.assertEqual(1.0, window._entry_allocations[key][0]["qty"])
        self.assertEqual(1.0, window._open_position_records[key]["data"]["qty"])
        self.assertEqual({"1m"}, window._entry_intervals["BTCUSDT"]["L"])
        pending = window._pending_allocation_reconciliations[key]
        self.assertEqual(1, len(pending))
        self.assertEqual(response, pending[0]["venue_result"])
        self.close(window)
        window.shared_binance.close_futures_leg_exact.assert_called_once()

    def test_failed_flat_snapshot_publication_retains_query_result_and_blocks_another_close(self):
        response = {"ok": False, "no_live_position": True, "error": "exchange reports no open leg"}
        window = self.window(response)
        window._clear_local_position_state.return_value = False
        self.close(window)
        pending = window._pending_allocation_reconciliations[("BTCUSDT", "L")][-1]
        self.assertEqual("clear", pending["operation"])
        self.assertEqual(response, pending["venue_result"])
        window._track_interval_close.assert_not_called()
        self.close(window)
        window.shared_binance.close_futures_leg_exact.assert_called_once()

    def test_inflight_manual_close_blocks_second_post_before_first_callback(self):
        response = {"ok": True, "execution_confirmed": True, "executed_qty": 0.25}
        window = self.window(response)
        ControlledWorker.instances = []
        with patch("app.gui.runtime.background_workers.CallWorker", ControlledWorker):
            close_position_single(window, "BTCUSDT", "L", "1m", 1.0, {"trade_id": "owned"})
            self.assertEqual(1, len(ControlledWorker.instances))
            window.shared_binance.close_futures_leg_exact.assert_called_once()
            window._reduce_local_position_allocation_state.assert_not_called()
            close_position_single(window, "BTCUSDT", "L", "1m", 1.0, {"trade_id": "owned"})
            self.assertEqual(1, len(ControlledWorker.instances))
            window.shared_binance.close_futures_leg_exact.assert_called_once()
            ControlledWorker.instances[0].complete()
            self.assertNotIn(("BTCUSDT", "L"), window._manual_close_inflight)
            close_position_single(window, "BTCUSDT", "L", "1m", 1.0, {"trade_id": "owned"})
            self.assertEqual(2, len(ControlledWorker.instances))
            self.assertEqual(2, window.shared_binance.close_futures_leg_exact.call_count)

    def test_partial_or_failed_publication_keeps_inflight_and_pending_fences(self):
        for response, reconciled in (
            ({"ok": False, "execution_confirmed": True, "executed_qty": 0.25,
              "submission_attempted": True, "reconciliation_required": True}, True),
            ({"ok": True, "execution_confirmed": True, "executed_qty": 0.25}, False),
        ):
            with self.subTest(response=response, reconciled=reconciled):
                window = self.window(response)
                window._reduce_local_position_allocation_state.return_value = reconciled
                ControlledWorker.instances = []
                with patch("app.gui.runtime.background_workers.CallWorker", ControlledWorker):
                    close_position_single(window, "BTCUSDT", "L", "1m", 1.0, {"trade_id": "owned"})
                    worker = ControlledWorker.instances[0]
                    worker.complete()
                    worker.finished.connect.call_args_list[-1].args[0]()
                    self.assertIn(("BTCUSDT", "L"), window._manual_close_inflight)
                    self.assertTrue(window._pending_allocation_reconciliations[("BTCUSDT", "L")])
                    close_position_single(window, "BTCUSDT", "L", "1m", 1.0, {"trade_id": "owned"})
                window.shared_binance.close_futures_leg_exact.assert_called_once()

    def test_finished_without_done_cannot_release_inflight_fence(self):
        window = self.window({"ok": True, "execution_confirmed": True, "executed_qty": 0.25})
        ControlledWorker.instances = []
        with patch("app.gui.runtime.background_workers.CallWorker", ControlledWorker):
            close_position_single(window, "BTCUSDT", "L", "1m", 1.0, {"trade_id": "owned"})
            worker = ControlledWorker.instances[0]
            worker.finished.connect.call_args_list[-1].args[0]()
            self.assertIn(("BTCUSDT", "L"), window._manual_close_inflight)
            self.assertEqual("uncertain_close", window._pending_allocation_reconciliations[("BTCUSDT", "L")][-1]["operation"])
            close_position_single(window, "BTCUSDT", "L", "1m", 1.0, {"trade_id": "owned"})
        window.shared_binance.close_futures_leg_exact.assert_called_once()

    def test_late_finished_signal_cannot_clear_newer_worker_fence(self):
        window = self.window({"ok": True, "execution_confirmed": True, "executed_qty": 0.25})
        ControlledWorker.instances = []
        with patch("app.gui.runtime.background_workers.CallWorker", ControlledWorker):
            close_position_single(window, "BTCUSDT", "L", "1m", 1.0, {"trade_id": "owned"})
            first = ControlledWorker.instances[0]
            first.complete()
            close_position_single(window, "BTCUSDT", "L", "1m", 1.0, {"trade_id": "owned"})
            current_token = window._manual_close_inflight[("BTCUSDT", "L")]
            first.finished.connect.call_args_list[-1].args[0]()
            self.assertIs(current_token, window._manual_close_inflight[("BTCUSDT", "L")])
            close_position_single(window, "BTCUSDT", "L", "1m", 1.0, {"trade_id": "owned"})
        self.assertEqual(2, window.shared_binance.close_futures_leg_exact.call_count)

    def test_preflight_rejection_releases_completed_nonpending_worker_fence(self):
        window = self.window({"ok": False, "error": "quantity preflight rejected"})
        ControlledWorker.instances = []
        with patch("app.gui.runtime.background_workers.CallWorker", ControlledWorker):
            close_position_single(window, "BTCUSDT", "L", "1m", 1.0, {"trade_id": "owned"})
            ControlledWorker.instances[0].complete()
            self.assertNotIn(("BTCUSDT", "L"), window._manual_close_inflight)
            close_position_single(window, "BTCUSDT", "L", "1m", 1.0, {"trade_id": "owned"})
        self.assertEqual(2, len(ControlledWorker.instances))

    def test_worker_start_failure_retains_uncertain_fence(self):
        class LostStartWorker(ControlledWorker):
            def start(self):
                super().start()
                raise RuntimeError("start outcome lost")

        window = self.window({"ok": True, "execution_confirmed": True, "executed_qty": 0.25})
        ControlledWorker.instances = []
        with patch("app.gui.runtime.background_workers.CallWorker", LostStartWorker):
            close_position_single(window, "BTCUSDT", "L", "1m", 1.0, {"trade_id": "owned"})
            self.assertIn(("BTCUSDT", "L"), window._manual_close_inflight)
            self.assertEqual("uncertain_close", window._pending_allocation_reconciliations[("BTCUSDT", "L")][-1]["operation"])
            close_position_single(window, "BTCUSDT", "L", "1m", 1.0, {"trade_id": "owned"})
        window.shared_binance.close_futures_leg_exact.assert_called_once()

    def test_invalid_targeted_quantity_never_submits_or_expands_to_whole_symbol(self):
        for quantity in (float("nan"), float("inf"), float("-inf"), 0, -0.25, False, True, "invalid", None):
            for interval, target in (("1m", {"trade_id": "owned"}), ("1m", None), (None, {"trade_id": "owned"})):
                with self.subTest(quantity=quantity, interval=interval, target=target):
                    window = self.window({"ok": True, "execution_confirmed": True, "executed_qty": 0.25})
                    ControlledWorker.instances = []
                    with patch("app.gui.runtime.background_workers.CallWorker", ControlledWorker):
                        close_position_single(window, "BTCUSDT", "L", interval, quantity, target)
                    window.shared_binance.close_futures_leg_exact.assert_not_called()
                    window.shared_binance.close_futures_position.assert_not_called()
                    self.assertEqual([], ControlledWorker.instances)

    def test_only_untargeted_none_quantity_can_request_whole_symbol_close(self):
        window = self.window({"ok": True})
        window.shared_binance.close_futures_position = Mock(return_value={"ok": True, "skipped": True})
        with patch("app.gui.runtime.background_workers.CallWorker", InlineWorker):
            close_position_single(window, "BTCUSDT", "L", None, None, None)
        window.shared_binance.close_futures_position.assert_called_once_with("BTCUSDT")
        window.shared_binance.close_futures_leg_exact.assert_not_called()

    def test_queued_close_uses_original_wrapper_and_defers_changed_account_publication(self):
        original_result = {"ok": True, "execution_confirmed": True, "executed_qty": 0.25,
                           "info": {"orderId": 913, "clientOrderId": "close-original"}}
        window = self.window(original_result)
        original_wrapper = window.shared_binance
        replacement = self.window({"ok": True, "execution_confirmed": True, "executed_qty": 1.0}).shared_binance
        ControlledWorker.instances = []
        with patch("app.gui.runtime.background_workers.CallWorker", QueuedWorker):
            close_position_single(window, "BTCUSDT", "L", "1m", 1.0, {"trade_id": "owned"})
            worker = ControlledWorker.instances[0]
            window.shared_binance = replacement
            worker.execute()
            original_wrapper.close_futures_leg_exact.assert_called_once()
            replacement.close_futures_leg_exact.assert_not_called()
            worker.complete()
        window._reduce_local_position_allocation_state.assert_not_called()
        pending = window._pending_allocation_reconciliations[("BTCUSDT", "L")]
        self.assertTrue(any(event.get("venue_result") == original_result for event in pending))
        self.assertIn(("BTCUSDT", "L"), window._manual_close_inflight)

    def test_changed_mode_or_snapshot_generation_defers_original_close_callback(self):
        result = {"ok": True, "execution_confirmed": True, "executed_qty": 0.25,
                  "info": {"orderId": 913, "clientOrderId": "close-original"}}
        for changed_field in ("mode", "snapshot"):
            with self.subTest(changed_field=changed_field):
                window = self.window(result)
                selected_mode = ["Testnet"]
                window.mode_combo = SimpleNamespace(currentText=lambda: selected_mode[0])
                window._allocation_snapshot_session = SimpleNamespace(_generation=1)
                ControlledWorker.instances = []
                with patch("app.gui.runtime.background_workers.CallWorker", QueuedWorker):
                    close_position_single(window, "BTCUSDT", "L", "1m", 1.0, {"trade_id": "owned"})
                    worker = ControlledWorker.instances[0]
                    worker.execute()
                    if changed_field == "mode":
                        selected_mode[0] = "Live"
                    else:
                        window._allocation_snapshot_session._generation = 2
                    worker.complete()
                window._reduce_local_position_allocation_state.assert_not_called()
                self.assertTrue(any(event.get("venue_result") == result
                                    for event in window._pending_allocation_reconciliations[("BTCUSDT", "L")]))
                self.assertIn(("BTCUSDT", "L"), window._manual_close_inflight)

    def test_unexpected_callback_fault_retains_confirmed_receipt_and_token(self):
        class UnexpectedCallbackFault(Exception):
            pass

        result = {"ok": True, "execution_confirmed": True, "executed_qty": 0.25,
                  "info": {"orderId": 913, "clientOrderId": "close-original"}}
        window = self.window(result)
        window._reduce_local_position_allocation_state.side_effect = UnexpectedCallbackFault("unexpected callback bug")
        with self.assertRaises(UnexpectedCallbackFault):
            self.close(window)
        self.assertTrue(any(event.get("venue_result") == result
                            for event in window._pending_allocation_reconciliations[("BTCUSDT", "L")]))
        self.assertIn(("BTCUSDT", "L"), window._manual_close_inflight)
        window.shared_binance.close_futures_leg_exact.assert_called_once()
