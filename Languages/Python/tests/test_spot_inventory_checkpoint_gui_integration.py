"""Actual GUI boundary controls with a fake protected store and no transport."""
from copy import deepcopy
from dataclasses import replace
import json
from types import SimpleNamespace
import unittest
from unittest.mock import patch

import test_spot_inventory_namespace_integration as fixtures
from spot_inventory_checkpoint_fixtures import CheckpointFixtureBackend
from app.gui.shared import allocation_persistence as allocations
from app.gui.shared.trade_callback_origin import capture_trade_callback_origin, check_trade_callback_origin
from app.integrations.exchanges.binance.orders import order_intent_runtime as intents
from app.integrations.exchanges.binance.orders import spot_allocation_generation_runtime as generations
from app.integrations.exchanges.binance.orders import spot_inventory_checkpoint_runtime as checkpoint_runtime
from app.integrations.exchanges.binance.orders.order_intent_store import ledger_transaction, write_ledger
from app.integrations.exchanges.binance.orders.spot_buy_publication_runtime import desktop_source_descriptor
from app.settings.live_safety import LiveTradingSafetyError


class SpotInventoryCheckpointGuiIntegrationTests(unittest.TestCase):
    def setUp(self):
        self.f = fixtures.SpotInventoryNamespaceIntegrationTests("runTest")
        self.addCleanup(self.f.doCleanups)
        self.f.setUp()
        self.backend = self.enterContext(CheckpointFixtureBackend(simulate_windows=True))
        self.account = self.f.account("gui-checkpoint", 887001, accepted=False)
        self.window = self.loaded()
        self.params = deepcopy(fixtures.PARAMS)
        self.event = {"version": 1, "event_id": "gui-checkpoint-event", "kind": "BUY",
                      "symbol": "BTCUSDT", "side_key": "L", "quantity": str(self.f.fill["net_qty"]),
                      "order_id": str(self.f.fill["order_id"]), "client_order_id": fixtures.CLIENT}

    def loaded(self, *, mode="Live", require_ready=True):
        session = allocations.AllocationSnapshotSession()
        ticket = allocations.AllocationSnapshotLoadTicket()
        maps = allocations.load_position_allocations(this_file=self.f.home / "unused.py", mode=mode,
                                                      session=session, load_ticket=ticket)
        window = SimpleNamespace(shared_binance=self.account.wrapper, _allocation_snapshot_session=session,
            _account_observation_generation=0, mode_combo=SimpleNamespace(currentText=lambda: mode),
            _entry_allocations=maps[0], _open_position_records=maps[1])
        with session.loaded_handoff(ticket) as accepted:
            self.assertEqual(require_ready, accepted)
        self.assertEqual(require_ready, session.ready)
        return window

    def bootstrap(self):
        return capture_trade_callback_origin(self.window, self.account.wrapper, self.params)

    def prepared(self):
        origin = self.bootstrap()
        empty = self.f.path.read_bytes()
        record = self.f.author_accepted(self.account, self.f.fill)
        record["desktop_entry_source"] = desktop_source_descriptor(origin.admission_receipt)
        with ledger_transaction(self.account.path):
            ledger = intents._read_ledger(self.account.path)
            ledger["intents"][fixtures.CLIENT] = record
            intents.validate_order_intent_ledger(ledger)
            write_ledger(self.account.path, ledger)
        row = generations.build_spot_buy_allocation_row(self.f.fill)
        quantity = float(row["qty"])
        position = {"symbol": "BTCUSDT", "side_key": "L", "status": "Active", "allocations": [deepcopy(row)],
                    "data": {"symbol": "BTCUSDT", "side_key": "L", "qty": quantity,
                             "entry_price": quantity * row["entry_price"] / quantity,
                             "margin_usdt": float(row["margin_usdt"]), "size_usdt": float(row["notional"])}}
        entries, records = {("BTCUSDT", "L"): [row]}, {("BTCUSDT", "L"): position}
        ledger = self.f.ledger(self.account)
        context = generations.SpotBuyPublicationContext(allocation_path=self.f.path, intent_path=self.account.path,
            expected_binding=ledger["binding"], expected_intent=record, fill=self.f.fill,
            entry_source_receipt=origin.admission_receipt, expected_store_id=ledger["store_id"],
            namespace=self.account.namespace, origin=origin)
        return origin, context, entries, records, empty

    def publish(self, context, entries, records):
        self.window._entry_allocations, self.window._open_position_records = entries, records
        return allocations.save_position_allocations(entries, records, this_file=self.f.home / "unused.py",
            mode="Live", session=self.window._allocation_snapshot_session,
            event_receipt=self.event, owned_spot_buy=context)

    def test_fresh_bootstrap_commits_protected_head_and_actually_reloads_both_maps(self):
        session = self.window._allocation_snapshot_session
        before = session._capture()
        old_maps = (self.window._entry_allocations, self.window._open_position_records)
        real_load, observations = allocations.load_position_allocations, []
        def load(**kwargs):
            self.assertFalse(session.ready)
            self.assertIs(old_maps[0], self.window._entry_allocations)
            self.assertIs(old_maps[1], self.window._open_position_records)
            observations.append((self.f.path.read_bytes(), deepcopy(self.backend.store)))
            return real_load(**kwargs)
        with patch.object(allocations, "load_position_allocations", side_effect=load):
            origin = self.bootstrap()
        self.assertEqual(1, len(observations))
        self.assertTrue(observations[0][1])
        self.assertEqual("stable", json.loads(next(iter(self.backend.store.values())))["state"])
        self.assertEqual(observations[0][0], origin.admission_receipt.raw)
        self.assertIsNot(old_maps[0], self.window._entry_allocations)
        self.assertIsNot(old_maps[1], self.window._open_position_records)
        self.assertNotEqual(before, session._capture())
        self.assertEqual({}, self.f.ledger(self.account)["intents"])
        self.assertTrue(check_trade_callback_origin(self.window, origin, self.params))
        self.assertEqual([], self.f.order_calls)

    def test_actual_gui_buy_advances_checkpoint_and_retains_complete_intent(self):
        _origin, context, entries, records, empty = self.prepared()
        ledger = self.f.ledger(self.account)
        self.assertTrue(self.publish(context, entries, records))
        self.assertNotEqual(empty, self.f.path.read_bytes())
        self.assertEqual(2, json.loads(next(iter(self.backend.store.values())))["head"]["revision"])
        self.assertEqual(ledger, self.f.ledger(self.account))
        window = self.loaded()
        self.assertTrue(window._allocation_snapshot_session.has_trade_event_receipt(self.event))
        self.assertEqual(entries, window._entry_allocations)
        self.assertEqual(records, window._open_position_records)
        self.assertEqual([], self.f.order_calls)

    def test_coherent_old_same_account_source_cannot_reload_after_new_gui_publication(self):
        _origin, context, entries, records, empty = self.prepared()
        self.assertTrue(self.publish(context, entries, records))
        ledger, protected = self.f.ledger(self.account), deepcopy(self.backend.store)
        self.f.path.write_bytes(empty)
        window = self.loaded(require_ready=False)
        self.assertEqual({}, window._entry_allocations)
        self.assertEqual({}, window._open_position_records)
        self.assertEqual(empty, self.f.path.read_bytes())
        self.assertEqual(protected, self.backend.store)
        self.assertEqual(ledger, self.f.ledger(self.account))
        self.assertEqual([], self.f.order_calls)

    def test_namespace_removal_deletion_and_mode_change_fence_loader_and_foreign_exposure(self):
        self.bootstrap()
        stable, protected = self.f.path.read_bytes(), deepcopy(self.backend.store)
        snapshot = json.loads(stable)
        stripped = deepcopy(snapshot)
        stripped.pop("spot_account_namespace")
        changed_mode = {**stripped, "mode": "Paper"}
        for raw in (json.dumps(stripped).encode(), None, json.dumps(changed_mode).encode()):
            with self.subTest(missing=raw is None, paper=raw is not None and b"Paper" in raw):
                if raw is None:
                    self.f.path.unlink()
                else:
                    self.f.path.write_bytes(raw)
                self.loaded(mode=None, require_ready=False)
                foreign = SimpleNamespace(mode="Paper", account_type="FUTURES")
                self.assertFalse(allocations.non_spot_desktop_exposure_allowed(self.window, foreign))
                self.assertFalse(allocations.save_position_allocations({}, {}, this_file=self.f.home / "unused.py", mode="Paper"))
                self.assertEqual(raw, self.f.path.read_bytes() if self.f.path.exists() else None)
                self.assertEqual(protected, self.backend.store)
                self.f.path.write_bytes(stable)

    def test_bound_snapshot_missing_protected_authority_never_autoseals(self):
        data = {"version": 1, "mode": "Live", "entry_allocations": {}, "open_position_records": {},
                "spot_account_namespace": self.account.namespace}
        with ledger_transaction(self.f.path):
            write_ledger(self.f.path, data)
        before = self.f.path.read_bytes()
        self.loaded(require_ready=False)
        with self.assertRaises(LiveTradingSafetyError):
            allocations.initialize_spot_allocation_namespace(self.window, self.account.wrapper)
        self.assertEqual(before, self.f.path.read_bytes())
        self.assertEqual({}, self.backend.store)
        self.assertEqual([], self.backend.put_calls)
        self.assertEqual({}, self.f.ledger(self.account)["intents"])

    def test_legacy_path_protection_is_checked_before_copy_or_unlink(self):
        # Keep both the canonical and legacy source inside the fixture root.
        legacy = self.f.home / allocations._ALLOCATIONS_FILE_NAME
        canonical = self.f.home / "data" / allocations._ALLOCATIONS_FILE_NAME
        canonical.parent.mkdir()
        data = {"version": 1, "mode": "Live", "entry_allocations": {}, "open_position_records": {},
                "spot_account_namespace": self.account.namespace}
        with ledger_transaction(legacy):
            write_ledger(legacy, data)
        self.backend.author_snapshot(legacy, namespace=self.account.namespace)
        before, protected = legacy.read_bytes(), deepcopy(self.backend.store)
        with patch.object(allocations, "_get_allocations_file_path", return_value=canonical):
            session = allocations.AllocationSnapshotSession()
            self.assertEqual(({}, {}), allocations.load_position_allocations(this_file=self.f.home / "unused.py",
                                                                            mode="Live", session=session))
            self.assertFalse(session.ready)
        self.assertFalse(canonical.exists())
        self.assertEqual(before, legacy.read_bytes())
        self.assertEqual(protected, self.backend.store)

    def test_origin_check_detects_rollback_but_pure_handoff_performs_no_io(self):
        origin = self.bootstrap()
        stable = self.f.path.read_bytes()
        stripped = json.loads(stable)
        stripped.pop("spot_account_namespace")
        self.f.path.write_text(json.dumps(stripped), encoding="utf-8")
        self.assertFalse(check_trade_callback_origin(self.window, origin, self.params))
        self.f.path.write_bytes(stable)
        with patch.object(allocations, "_read_receipt", side_effect=AssertionError("Pure handoff must not read")), \
             patch.object(allocations, "guard_position_allocation_snapshot", side_effect=AssertionError("No protected I/O")):
            with origin.admission_handoff(self.params):
                pass
        self.assertEqual([], self.f.order_calls)

    def test_duplicate_receipt_is_not_authority_after_source_deletion(self):
        _origin, context, entries, records, _empty = self.prepared()
        self.assertTrue(self.publish(context, entries, records))
        session = self.window._allocation_snapshot_session
        self.assertTrue(session.has_trade_event_receipt(self.event))
        self.f.path.unlink()
        protected = deepcopy(self.backend.store)
        with self.assertRaises(LiveTradingSafetyError):
            session.has_trade_event_receipt(self.event)
        self.assertEqual(protected, self.backend.store)
        self.assertFalse(self.f.path.exists())

    def test_detached_publication_context_cannot_write_even_matching_candidate(self):
        _origin, context, entries, records, _empty = self.prepared()
        before = self.f.durable_bytes(self.account), deepcopy(self.backend.store)
        self.assertFalse(self.publish(replace(context, origin=None), entries, records))
        self.assertEqual(before, (self.f.durable_bytes(self.account), self.backend.store))
        self.assertFalse(self.window._allocation_snapshot_session.ready)
        with ledger_transaction(self.f.path), self.assertRaises(LiveTradingSafetyError):
            checkpoint_runtime.write_owned_inventory_checkpoint(self.f.path, {})


if __name__ == "__main__":
    unittest.main()
