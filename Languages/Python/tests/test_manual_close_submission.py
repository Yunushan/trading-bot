from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch

from app.gui.positions.actions_close_runtime import close_position_single


class InlineWorker:
    def __init__(self, operation, parent=None):
        self.operation = operation
        self.done = SimpleNamespace(connect=lambda callback: setattr(self, "callback", callback))
        self.progress = Mock()
        self.finished = Mock()
        self.deleteLater = Mock()

    def start(self):
        self.callback(self.operation(), None)


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
                    )
                else:
                    window._reduce_local_position_allocation_state.assert_not_called()
                window._track_interval_close.assert_not_called()
                window._clear_local_position_state.assert_not_called()
                window.refresh_positions.assert_called_once()

    def test_confirmed_capped_close_updates_only_executed_allocation(self):
        window = self.window({"ok": True, "execution_confirmed": True, "executed_qty": 0.25, "sent_qty": 0.25})
        self.close(window)
        window._reduce_local_position_allocation_state.assert_called_once_with(
            "BTCUSDT", "L", interval="1m", qty=0.25, target_identity={"trade_id": "owned"},
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
