"""Actual desktop namespace capture, reload and pre-transport publication fences."""
from __future__ import annotations

from copy import deepcopy
import json
from types import MethodType, SimpleNamespace
import unittest
from unittest.mock import Mock, patch

import test_spot_opo_fault_integration as fixture_module
from spot_inventory_checkpoint_fixtures import CheckpointFixtureBackend

from app.gui.runtime.account import account_runtime
from app.gui.shared import allocation_persistence as allocations
from app.gui.shared.trade_callback_origin import capture_trade_callback_origin, check_trade_callback_origin
from app.integrations.exchanges.binance.orders import order_intent_runtime as intents
from app.integrations.exchanges.binance.orders.order_intent_store import ledger_transaction, write_ledger
from app.integrations.exchanges.binance.orders.order_submit_guard_runtime import _guard_live_order_submit
from app.integrations.exchanges.binance.orders.order_fallback_runtime import _futures_create_order_with_fallback
from app.integrations.exchanges.binance.orders.spot_inventory_namespace import ACCOUNT_NAMESPACE_KEY, make_namespace
from app.settings.live_safety import LiveTradingSafetyError


class SpotInventoryNamespaceGuiTests(unittest.TestCase):
    def setUp(self):
        self.checkpoint_backend = self.enterContext(CheckpointFixtureBackend(simulate_windows=True))
        self.fixture = fixture_module.SpotOpoFaultIntegrationTests()
        self.fixture.setUp()
        self.addCleanup(self.fixture.doCleanups)
        self.path = self.fixture.allocation_path
        self.enterContext(patch.object(allocations, "_get_allocations_file_path", return_value=self.path))
        self.wrapper = self.fixture.wrapper(bootstrap=False)
        self.owner = self.wrapper._ensure_spot_execution_owner()
        self.expected = make_namespace(self.owner.uid, self.owner.store_id)
        self.params = {"symbol": "BTCUSDT", "side": "BUY", "type": "MARKET",
                       "quantity": "0.1", "newClientOrderId": "namespace-gui-buy"}
        self.window = self.load_window(self.wrapper)

    def load_window(self, wrapper):
        session = allocations.AllocationSnapshotSession()
        ticket = allocations.AllocationSnapshotLoadTicket()
        maps = allocations.load_position_allocations(this_file=self.fixture.home / "unused.py", mode="Live",
                                                     session=session, load_ticket=ticket)
        window = SimpleNamespace(shared_binance=wrapper, _allocation_snapshot_session=session,
                                 mode_combo=SimpleNamespace(currentText=lambda: "Live"), config={},
                                 _account_observation_generation=0)
        with session.loaded_handoff(ticket) as accepted:
            self.assertTrue(accepted)
            window._entry_allocations, window._open_position_records = maps
        with patch.object(account_runtime, "BinanceWrapper", return_value=wrapper):
            account_runtime._create_binance_wrapper(window, api_key=wrapper.api_key, api_secret=wrapper.api_secret,
                                                    mode=wrapper.mode, account_type=wrapper.account_type,
                                                    connector_backend="binance-sdk-spot")
        return window

    def bootstrap(self):
        origin = capture_trade_callback_origin(self.window, self.wrapper, self.params)
        self.assertEqual(self.expected, json.loads(self.path.read_bytes())[ACCOUNT_NAMESPACE_KEY])
        self.assertEqual([], self.fixture.venue.posts)
        return origin

    def ledger(self):
        with ledger_transaction(self.owner.ledger_path):
            return deepcopy(dict(intents._read_ledger(self.owner.ledger_path)))

    def test_absent_bootstrap_reloads_actual_bytes_and_both_maps_before_descriptor(self):
        session = self.window._allocation_snapshot_session
        original_maps = (self.window._entry_allocations, self.window._open_position_records)
        old_receipt = session._capture()
        real_load = allocations.load_position_allocations
        observed = []

        def actual_load(**kwargs):
            self.assertFalse(session.ready)
            self.assertIs(original_maps[0], self.window._entry_allocations)
            self.assertIs(original_maps[1], self.window._open_position_records)
            self.assertEqual(self.expected, json.loads(self.path.read_bytes())[ACCOUNT_NAMESPACE_KEY])
            observed.append(self.path.read_bytes())
            return real_load(**kwargs)

        with patch.object(allocations, "load_position_allocations", side_effect=actual_load):
            origin = self.bootstrap()
        self.assertEqual(1, len(observed))
        self.assertIsNot(original_maps[0], self.window._entry_allocations)
        self.assertIsNot(original_maps[1], self.window._open_position_records)
        self.assertTrue(session.ready)
        self.assertNotEqual(old_receipt, session._capture())
        self.assertEqual(observed[0], origin.admission_receipt.raw)
        self.assertEqual(self.path.stat().st_size, len(origin.admission_receipt.raw))
        self.assertEqual({}, self.ledger()["intents"])
        self.assertTrue(check_trade_callback_origin(self.window, origin, self.params))
        with patch.object(allocations, "load_position_allocations", side_effect=AssertionError("No redundant reload")):
            self.assertFalse(allocations.initialize_spot_allocation_namespace(self.window, self.wrapper))

    def test_unscoped_nonempty_or_unknown_extension_is_not_adopted(self):
        for extension in ({"unknown_history": []}, {"gui_trade_event_receipts": [
                {"version": 1, "event_id": "prior-event", "kind": "BUY", "symbol": "BTCUSDT",
                 "side_key": "L", "quantity": "0.1"}]}):
            with self.subTest(extension=extension):
                payload = {"version": 1, "mode": "Live", "entry_allocations": {},
                           "open_position_records": {}, **extension}
                write_ledger(self.path, payload)
                self.window = self.load_window(self.wrapper)
                before = self.path.read_bytes()
                with self.assertRaisesRegex(LiveTradingSafetyError, "explicit reconciliation"):
                    capture_trade_callback_origin(self.window, self.wrapper, self.params)
                self.assertEqual(before, self.path.read_bytes())
                self.assertEqual({}, self.ledger()["intents"])
                self.assertEqual([], self.fixture.venue.posts)

    def test_any_retained_ledger_history_prevents_empty_namespace_bootstrap(self):
        record = intents._intent_record(self.params, market="spot", source="namespace-history-control")
        record["state"] = "rejected"
        with ledger_transaction(self.owner.ledger_path):
            payload = intents._read_ledger(self.owner.ledger_path)
            payload["intents"][record["client_order_id"]] = record
            write_ledger(self.owner.ledger_path, payload)
        before = self.ledger()
        with self.assertRaises(LiveTradingSafetyError):
            self.bootstrap()
        self.assertFalse(self.path.exists())
        self.assertEqual(before, self.ledger())
        self.assertEqual([], self.fixture.venue.posts)

    def test_bootstrap_never_freshens_mutated_old_maps_and_reload_failure_stays_fenced(self):
        original = self.window._allocation_snapshot_session._capture()
        self.window._entry_allocations[("BTCUSDT", "L")] = []
        with self.assertRaisesRegex(LiveTradingSafetyError, "maps differ"):
            capture_trade_callback_origin(self.window, self.wrapper, self.params)
        self.assertEqual(original, self.window._allocation_snapshot_session._capture())
        self.assertFalse(self.path.exists())
        self.window._entry_allocations.clear()
        with patch.object(allocations, "load_position_allocations", side_effect=OSError("Confined reload failure")):
            with self.assertRaises(OSError):
                self.bootstrap()
        self.assertEqual(self.expected, json.loads(self.path.read_bytes())[ACCOUNT_NAMESPACE_KEY])
        self.assertFalse(self.window._allocation_snapshot_session.ready)
        self.assertEqual({}, self.window._entry_allocations)
        self.assertEqual({}, self.ledger()["intents"])
        self.assertEqual([], self.fixture.venue.posts)

    def test_namespace_drift_between_begin_and_submitted_keeps_original_intent_pending(self):
        self.bootstrap()
        self.wrapper._begin_order_intent(self.params, market="spot", source="namespace-begin-control")
        before = self.ledger()
        payload = json.loads(self.path.read_bytes())
        payload[ACCOUNT_NAMESPACE_KEY] = make_namespace(self.owner.uid + 1, self.owner.store_id)
        self.path.write_text(json.dumps(payload), encoding="utf-8")
        altered = self.path.read_bytes()
        with self.assertRaises(LiveTradingSafetyError):
            self.wrapper._mark_order_intent_submitted(self.params, via="namespace-submitted-control")
        self.assertEqual(altered, self.path.read_bytes())
        self.assertEqual(before, self.ledger())
        self.assertEqual("pending", self.ledger()["intents"][self.params["newClientOrderId"]]["state"])
        self.assertEqual([], self.fixture.venue.posts)

    def test_pure_handoff_and_check_reject_namespace_drift_without_accepting_a_fresh_origin(self):
        origin = self.bootstrap()
        session = self.window._allocation_snapshot_session
        session._snapshot[ACCOUNT_NAMESPACE_KEY] = make_namespace(self.owner.uid + 1, self.owner.store_id)
        self.assertFalse(check_trade_callback_origin(self.window, origin, self.params))
        with self.assertRaises(LiveTradingSafetyError):
            with origin.admission_handoff(self.params):
                self.fail("Foreign parsed namespace must not reach admission")
        self.assertEqual(self.expected, json.loads(self.path.read_bytes())[ACCOUNT_NAMESPACE_KEY])
        self.assertEqual({}, self.ledger()["intents"])

    def test_generic_shared_save_cannot_mutate_or_mint_bound_namespace(self):
        self.bootstrap()
        before = self.path.read_bytes()
        self.assertFalse(allocations.save_position_allocations(
            {}, {}, this_file=self.fixture.home / "unused.py", mode="Live",
            session=self.window._allocation_snapshot_session))
        self.assertEqual(before, self.path.read_bytes())
        self.assertFalse(self.window._allocation_snapshot_session.ready)
        self.path.unlink()
        forged = allocations.AllocationSnapshotSession()
        forged._accept(self.path, "Live", (None, None), {"version": 1, "mode": "Live",
            "entry_allocations": {}, "open_position_records": {}, ACCOUNT_NAMESPACE_KEY: self.expected})
        self.assertFalse(allocations.save_position_allocations(
            {}, {}, this_file=self.fixture.home / "unused.py", mode="Live", session=forged))
        self.assertFalse(self.path.exists())
        self.assertFalse(forged.ready)

    def test_factory_guard_blocks_foreign_exposure_before_transport_but_retains_risk_reduction(self):
        self.bootstrap()
        transport = Mock()
        foreign = SimpleNamespace(api_key="offline-key", api_secret="offline-secret", mode="Live",
            account_type="FUTURES", client=transport, _live_safety_config=dict(self.wrapper._live_safety_config),
            _guard_live_order_submit=None, _audit_order_event=Mock(),
            get_connector_health_snapshot=lambda: {"state": "ready", "health": "ok"},
            get_futures_symbol_filters=lambda _symbol: {"stepSize": "0.001", "minQty": "0.001",
                                                       "maxQty": "100", "minNotional": "0"})
        foreign._guard_live_order_submit = MethodType(_guard_live_order_submit, foreign)
        self.window = self.load_window(foreign)
        params = {"symbol": "BTCUSDT", "side": "BUY", "type": "MARKET", "quantity": "0.1"}
        with self.assertRaisesRegex(LiveTradingSafetyError, "desktop allocation publication"):
            _futures_create_order_with_fallback(foreign, params)
        transport.futures_create_order.assert_not_called()
        foreign._guard_live_order_submit(market="futures", params={**params, "reduceOnly": True})
        self.assertTrue(foreign._desktop_allocation_admission_check() is False)
        self.path.unlink()
        self.assertFalse(foreign._desktop_allocation_admission_check())
        transport.futures_create_order.assert_not_called()


if __name__ == "__main__":
    unittest.main()
