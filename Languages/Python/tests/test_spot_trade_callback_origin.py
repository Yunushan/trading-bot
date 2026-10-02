from __future__ import annotations

from contextlib import ExitStack
import copy
import hashlib
import hmac
import json
from pathlib import Path
import socket
import sys
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch
from urllib.parse import urlencode, urlparse

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from app.core.strategy.orders.strategy_signal_order_result_runtime import _emit_signal_order_info  # noqa: E402
from app.gui.runtime.account.account_runtime import _create_binance_wrapper, _invalidate_shared_binance  # noqa: E402
from app.gui.shared.allocation_persistence import AllocationSnapshotSession, load_position_allocations, save_position_allocations  # noqa: E402
from app.gui.shared.trade_callback_origin import check_trade_callback_origin  # noqa: E402
from app.gui.trade import signal_common_runtime  # noqa: E402
from app.integrations.exchanges.binance.orders.order_intent_provisioning import PROVISION_ACK, provision_order_intent_store  # noqa: E402
from app.settings.live_safety import LIVE_TRADING_ACKNOWLEDGEMENT, LiveTradingSafetyError  # noqa: E402
from test_open_trade_signal_behavior import _OpenSignalWindowStub, _dispatch  # noqa: E402


class SpotTradeCallbackOriginTests(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory(prefix="spot-callback-origin-")
        self.addCleanup(tmp.cleanup)
        self.root = Path(tmp.name).resolve()
        self.this_file = self.root / "Languages" / "Python" / "app" / "gui" / "window_shell.py"
        self.this_file.parent.mkdir(parents=True)
        self.allocation_path = self.this_file.parents[2] / "data" / ".trading_bot_allocations.json"
        stack = ExitStack()
        self.addCleanup(stack.close)
        stack.enter_context(patch.object(Path, "home", return_value=self.root))
        stack.enter_context(patch.object(socket.socket, "connect", side_effect=AssertionError("Network forbidden")))
        stack.enter_context(patch.object(socket.socket, "connect_ex", side_effect=AssertionError("Network forbidden")))
        stack.enter_context(patch("app.integrations.exchanges.binance.transport.http_request_runtime.requests.post",
                                 side_effect=AssertionError("Orders forbidden")))
        stack.enter_context(patch("app.integrations.exchanges.binance.transport.http_request_runtime.requests.get",
                                 side_effect=self._account_get))
        sdk = SimpleNamespace(get_symbol_info=lambda symbol: {
            "symbol": symbol, "baseAsset": "BTC", "quoteAsset": "USDT"})
        stack.enter_context(patch("app.integrations.exchanges.binance.wrapper.BinanceSDKSpotClient", return_value=sdk))
        stack.enter_context(patch("app.gui.shared.allocation_persistence.get_position_allocations_path",
                                 return_value=self.allocation_path))
        self.window = self._window()
        self.wrapper = self._wrapper(self.window, "offline-key-a", 12345678)
        self.assertIsNone(getattr(self.wrapper, "_spot_execution_owner", None))
        self.origin = self.wrapper._desktop_trade_origin_capture()
        self.assertIsNotNone(self.wrapper._spot_execution_owner)
        self.params = {"newClientOrderId": "callback-fee-buy", "symbol": "BTCUSDT", "side": "BUY",
                       "type": "MARKET", "quantity": "0.1"}
        self.wrapper._begin_order_intent(self.params, market="spot", source="offline-callback-test")
        self.wrapper._mark_order_intent_submitted(self.params, via="offline-callback-test")
        self.response = {"clientOrderId": "callback-fee-buy", "symbol": "BTCUSDT", "side": "BUY", "type": "MARKET",
                         "orderId": 75, "status": "FILLED", "origQty": "0.1", "executedQty": "0.1",
                         "cummulativeQuoteQty": "2000", "updateTime": 1780000000000,
                         "fills": [{"tradeId": 101, "price": "20000", "qty": "0.04", "commission": "0.00004", "commissionAsset": "BTC"},
                                   {"tradeId": 102, "price": "20000", "qty": "0.06", "commission": "0.2", "commissionAsset": "USDT"}]}
        self.wrapper._mark_order_intent_accepted(self.params, via="offline-callback-test", result=self.response)
        self.intent_path = self.origin.owner.ledger_path
        self.event = self._emit()

    def _account_get(self, url, *, params, headers, timeout):
        self.assertEqual("/api/v3/account", urlparse(url).path)
        unsigned = {key: value for key, value in params.items() if key != "signature"}
        expected = hmac.new(b"offline-secret", urlencode(unsigned).encode(), hashlib.sha256).hexdigest()
        self.assertTrue(hmac.compare_digest(expected, params["signature"]))
        self.assertTrue(timeout)
        uid = {"offline-key-a": 12345678, "offline-key-b": 87654321}[headers["X-MBX-APIKEY"]]
        return SimpleNamespace(status_code=200, json=lambda: {"uid": uid, "accountType": "SPOT"})

    def _window(self):
        window = _OpenSignalWindowStub()
        window.mode_combo = SimpleNamespace(currentText=lambda: "Live")
        window.config = {"mode": "Live", "live_trading_enabled": True,
                         "live_trading_acknowledgement": LIVE_TRADING_ACKNOWLEDGEMENT, "position_pct": 2.0,
                         "live_trading_max_leverage": 20, "live_trading_max_position_pct": 10.0,
                         "live_trading_max_session_orders": 10, "order_audit_enabled": True,
                         "order_audit_log_path": str(self.root / "audit.jsonl")}
        window._allocation_snapshot_session = AllocationSnapshotSession()
        window._entry_allocations, window._open_position_records = load_position_allocations(
            this_file=self.this_file, mode="Live", session=window._allocation_snapshot_session)
        return window

    def _wrapper(self, window, key, uid):
        admin = SimpleNamespace(api_key=key, mode="Live", account_type="SPOT", _enforce_spot_execution_owner=True,
                                _operator_spot_account_uid=uid, _order_audit_log_path=self.root / "audit.jsonl")
        provision_order_intent_store(admin, acknowledgement=PROVISION_ACK)
        wrapper = _create_binance_wrapper(window, api_key=key, api_secret="offline-secret", mode="Live",
                                         account_type="Spot", connector_backend="binance-sdk-spot")
        window.shared_binance = wrapper
        def close():
            owner = getattr(wrapper, "_spot_execution_owner", None)
            if owner is not None and owner.fd is not None:
                owner.close()
        self.addCleanup(close)
        return wrapper

    def _emit(self, *, current_wrapper=None):
        events = []
        strategy = SimpleNamespace(binance=current_wrapper or self.wrapper, trade_cb=events.append, log=lambda _: None)
        _emit_signal_order_info(strategy, cw={"symbol": "BTCUSDT", "interval": "1m"}, side="BUY",
                                order_res={"ok": True, "execution_confirmed": True, "submitted_qty": "0.1", "info": self.response},
                                price=20000.0, qty_display=0.1, trigger_labels=[], trigger_desc_for_order=None,
                                trigger_signature=[], context_key="offline-context", order_event_uid="offline-event",
                                trigger_actions_for_order={}, origin_timestamp=None, leverage_used=1,
                                callback_origin=self.origin, callback_wrapper=self.wrapper)
        return events[0]

    def _dispatch(self, event):
        _dispatch(self.window, event, persist_trade_allocations=signal_common_runtime._persist_trade_allocations,
                  sync_open_position_snapshot=signal_common_runtime._sync_open_position_snapshot,
                  saver=lambda a, r, **kw: save_position_allocations(a, r, this_file=self.this_file, **kw))

    def _assert_rejected(self):
        self.assertFalse(self.allocation_path.exists())
        self.assertEqual({}, self.window._entry_allocations)
        self.assertEqual({}, self.window._open_position_records)
        self.assertTrue(self.window._pending_allocation_reconciliations[("BTCUSDT", "L")])
        intent = json.loads(self.intent_path.read_text())["intents"]["callback-fee-buy"]
        self.assertFalse(intent["portfolio_reconciled"])
        self.assertEqual("FILLED", intent["exchange_status"])

    def test_original_unchanged_callback_publishes_canonical_fee_aware_inventory(self):
        self._dispatch(self.event)
        row = self.window._entry_allocations[("BTCUSDT", "L")][0]
        self.assertEqual(0.09996, row["qty"])
        self.assertEqual(1, row["spot_fill_recovery"]["version"])
        self.assertEqual(2000.2, row["notional"])
        self.assertFalse(getattr(self.window, "_pending_allocation_reconciliations", {}))
        self.assertTrue(self.wrapper._get_order_intent_record("callback-fee-buy")["portfolio_reconciled"])

    def test_result_uses_original_wrapper_when_engine_wrapper_changes(self):
        event = self._emit(current_wrapper=SimpleNamespace(account_type="FUTURES"))
        self.assertEqual("0.09996", event["spot_fill_recovery"]["net_qty"])
        self.assertIs(self.origin, event["_trade_callback_origin"])
        self._dispatch(event)
        self.assertEqual(0.09996, self.window._entry_allocations[("BTCUSDT", "L")][0]["qty"])

    def test_committed_same_account_replay_after_reload_is_read_only_and_clears_pending(self):
        self._dispatch(self.event)
        committed = self.allocation_path.read_bytes()
        self.window = self._window()
        self.window.shared_binance = self.wrapper
        before = copy.deepcopy((self.window._entry_allocations, self.window._open_position_records))
        self._dispatch(self.event)
        self.assertEqual(committed, self.allocation_path.read_bytes())
        self.assertEqual(before, (self.window._entry_allocations, self.window._open_position_records))
        self.assertFalse(getattr(self.window, "_pending_allocation_reconciliations", {}))
        self.assertTrue(self.window._allocation_snapshot_session.ready)

    def test_committed_replay_rejects_changed_account_and_changed_full_proof(self):
        self._dispatch(self.event)
        committed = self.allocation_path.read_bytes()
        self.window = self._window()
        self.window.shared_binance = self.wrapper
        bad = copy.deepcopy(self.event)
        bad["spot_fill_recovery"]["trade_ids"] = [501, 502]
        self._dispatch(bad)
        self.assertEqual(committed, self.allocation_path.read_bytes())
        self.assertTrue(self.window._pending_allocation_reconciliations[("BTCUSDT", "L")])
        self._wrapper(self.window, "offline-key-b", 87654321)
        self._dispatch(self.event)
        self.assertEqual(committed, self.allocation_path.read_bytes())
        self.assertTrue(self.window._pending_allocation_reconciliations[("BTCUSDT", "L")])

    def test_committed_replay_requires_actual_file_receipt_and_confirmed_execution(self):
        self._dispatch(self.event)
        self.window = self._window()
        self.window.shared_binance = self.wrapper
        self.allocation_path.write_bytes(self.allocation_path.read_bytes() + b" ")
        changed = self.allocation_path.read_bytes()
        self._dispatch(self.event)
        self.assertEqual(changed, self.allocation_path.read_bytes())
        self.assertTrue(self.window._pending_allocation_reconciliations[("BTCUSDT", "L")])
        self.window = self._window()
        self.window.shared_binance = self.wrapper
        self._dispatch(dict(self.event, execution_confirmed=False))
        self.assertEqual(changed, self.allocation_path.read_bytes())
        self.assertTrue(self.window._pending_allocation_reconciliations[("BTCUSDT", "L")])

    def test_missing_origin_or_publication_context_cannot_mutate_inventory(self):
        for name in ("_trade_callback_origin", "_spot_buy_submission_origin", "_spot_buy_publication"):
            with self.subTest(name=name):
                event = dict(self.event)
                event.pop(name)
                self._dispatch(event)
                self._assert_rejected()

    def test_fresh_session_and_same_session_reload_reject_original_callback(self):
        original_session = self.window._allocation_snapshot_session
        self.window._allocation_snapshot_session = AllocationSnapshotSession()
        load_position_allocations(this_file=self.this_file, mode="Live", session=self.window._allocation_snapshot_session)
        self._dispatch(self.event)
        self._assert_rejected()
        self.window._allocation_snapshot_session = original_session
        load_position_allocations(this_file=self.this_file, mode="Live", session=original_session)
        self._dispatch(self.event)
        self._assert_rejected()

    def test_changed_account_callback_cannot_publish_and_original_intent_stays_unresolved(self):
        self.wrapper._revoke_spot_execution_owner()
        second = self._wrapper(self.window, "offline-key-b", 87654321)
        self.assertEqual(0, second.get_order_intent_status()["unresolved_count"])
        self._dispatch(self.event)
        self._assert_rejected()
        restarted = self._window()
        self.assertEqual({}, restarted._entry_allocations)
        self.assertEqual({}, restarted._open_position_records)

    def test_account_invalidation_fences_session_before_revoking_wrapper(self):
        self.window._invalidate_balance_observation = lambda **kw: None
        with patch.object(self.wrapper, "_revoke_spot_execution_owner", wraps=self.wrapper._revoke_spot_execution_owner) as revoke:
            def checked_revoke():
                self.assertFalse(self.window._allocation_snapshot_session.ready)
                self.wrapper._spot_execution_owner.close()
            revoke.side_effect = checked_revoke
            _invalidate_shared_binance(self.window, "credentials_changed")
        self._dispatch(self.event)
        self._assert_rejected()

    def test_admission_handoff_is_pure_and_rejects_late_generation_change(self):
        source = self.event["_spot_buy_submission_origin"]
        self.assertTrue(check_trade_callback_origin(self.window, source, self.params))
        with patch.object(self.wrapper, "_resolve_spot_account_uid", side_effect=AssertionError("No account callback under mutex")), \
                patch.object(self.wrapper._spot_execution_owner, "assert_held", side_effect=AssertionError("No owner I/O under mutex")), \
                patch.object(self.window.mode_combo, "currentText", side_effect=AssertionError("No widget callback under mutex")):
            with source.admission_handoff(self.params):
                pass
        self.window._allocation_snapshot_session.invalidate("offline late change")
        with self.assertRaises(LiveTradingSafetyError), source.admission_handoff(self.params):
            self.fail("Changed origin was admitted")

    def test_origin_deepcopy_retains_identity_without_exposing_account_context(self):
        self.assertIs(self.origin, copy.deepcopy(self.origin))
        self.assertEqual("<TradeCallbackOrigin>", repr(self.origin))
        self.assertNotIn("offline-key", repr(self.origin))


if __name__ == "__main__":
    unittest.main()
