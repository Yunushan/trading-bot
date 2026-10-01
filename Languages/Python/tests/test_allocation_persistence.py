from __future__ import annotations

import tempfile
import unittest
import copy
import json
import threading
from types import SimpleNamespace
from pathlib import Path
from unittest.mock import patch

from app.gui.shared import allocation_persistence as persistence
from app.gui.shared.allocation_persistence import (
    AllocationSnapshotSession,
    load_position_allocations,
    save_position_allocations,
)
from app.integrations.exchanges.binance.orders import spot_fill_recovery_runtime as recovery
from app.gui.dashboard import state_runtime


class AllocationPersistenceTests(unittest.TestCase):
    def test_stale_gui_save_cannot_erase_real_owned_sell_recovery(self):
        with tempfile.TemporaryDirectory() as tmp:
            this_file = Path(tmp) / "Languages" / "Python" / "app" / "gui" / "window_shell.py"
            this_file.parent.mkdir(parents=True)
            path = this_file.parents[2] / "data" / ".trading_bot_allocations.json"
            path.parent.mkdir()
            fill = {
                "symbol": "BTCUSDT", "client_order_id": "buy-A", "order_id": 75,
                "trade_ids": [101], "trade_count": 1, "gross_qty": "0.1",
                "net_qty": "0.1", "gross_quote_qty": "2000", "net_quote_cost": "2000",
                "average_cost": "20000", "commissions": [], "base_asset": "BTC",
                "quote_asset": "USDT", "fill_time_ms": 1780000000000, "signature": "a" * 64,
            }
            self.assertTrue(recovery.persist_spot_buy_allocation(path, fill))
            session = AllocationSnapshotSession()
            allocations, records = load_position_allocations(this_file=this_file, mode="Live", session=session)
            baseline = recovery.spot_live_allocation_baseline(path, symbol="BTCUSDT")
            self.assertIsNotNone(baseline)
            assert baseline is not None
            sell = {
                "symbol": "BTCUSDT", "client_order_id": "sell-B", "order_id": 76,
                "side": "SELL", "trade_ids": [201], "gross_qty": "0.04", "portfolio_qty": "0.04",
                "gross_quote_qty": "800", "base_fee_qty": "0", "quote_fee_qty": "0",
                "net_quote_proceeds": "800", "commissions": [], "base_asset": "BTC",
                "quote_asset": "USDT", "fill_time_ms": 1780000001000, "signature": "b" * 64,
                "pre_order_portfolio_signature": baseline["signature"],
                "pre_order_portfolio_qty": baseline["quantity"],
            }
            self.assertTrue(recovery.persist_spot_sell_allocation(path, sell))
            recovered_bytes = path.read_bytes()
            self.assertFalse(save_position_allocations(
                allocations, records, this_file=this_file, mode="Live", session=session,
            ))
            self.assertEqual(recovered_bytes, path.read_bytes())

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.this_file = Path(self.temp.name) / "Languages" / "Python" / "app" / "gui" / "window_shell.py"
        self.this_file.parent.mkdir(parents=True)
        self.path = persistence.get_position_allocations_path(self.this_file)

    def load(self, session, mode="Live"):
        return load_position_allocations(this_file=self.this_file, mode=mode, session=session)

    def save(self, allocations, records, session=None, mode="Live", event_receipt=None):
        return save_position_allocations(
            allocations, records, this_file=self.this_file, mode=mode,
            session=session, event_receipt=event_receipt,
        )

    @staticmethod
    def maps(qty=0.1):
        row = {"symbol": "BTCUSDT", "side_key": "L", "qty": qty, "entry_price": 20000,
               "status": "Active", "client_order_id": "buy-A", "data": {"note": "A"}}
        record = {"symbol": "BTCUSDT", "side_key": "L", "status": "Active",
                  "data": {"symbol": "BTCUSDT", "side_key": "L", "qty": qty}, "allocations": [copy.deepcopy(row)]}
        return {("BTCUSDT", "L"): [row]}, {("BTCUSDT", "L"): record}

    @staticmethod
    def event(token="gui-buy-A", qty="0.1"):
        return {"version": 1, "event_id": token, "kind": "BUY", "symbol": "BTCUSDT",
                "side_key": "L", "quantity": qty, "client_order_id": "buy-A"}

    def test_loaded_absence_and_two_windows_have_independent_receipts(self):
        first, second = AllocationSnapshotSession(), AllocationSnapshotSession()
        self.assertEqual(({}, {}), self.load(first))
        self.assertEqual(({}, {}), self.load(second))
        self.assertEqual("absent", first.state)
        self.assertTrue(self.save(*self.maps(), first))
        original = self.path.read_bytes()
        self.assertFalse(self.save(*self.maps(0.2), second))
        self.assertEqual(original, self.path.read_bytes())
        self.assertEqual("blocked", second.state)
        self.load(second)
        self.assertTrue(self.save(*self.maps(0.2), second))
        second_bytes = self.path.read_bytes()
        self.assertFalse(self.save(*self.maps(), first))
        self.assertEqual(second_bytes, self.path.read_bytes())

    def test_complete_receipt_rejects_same_quantity_changes_and_identical_file_replacement(self):
        self.assertTrue(self.save(*self.maps()))
        for mutate in (
            lambda payload: payload["entry_allocations"]["BTCUSDT:L"][0].update(entry_price=21000),
            lambda payload: payload["entry_allocations"]["BTCUSDT:L"][0]["data"].update(note="B"),
            lambda payload: payload.update(operator_extension={"revision": "B"}),
            lambda payload: payload["entry_allocations"].update({"ETHUSDT:L": [{"qty": 2}]}),
        ):
            with self.subTest(mutate=mutate):
                session = AllocationSnapshotSession()
                maps = self.load(session)
                payload = json.loads(self.path.read_text())
                mutate(payload)
                with persistence.ledger_transaction(self.path):
                    persistence.write_ledger(self.path, payload)
                altered = self.path.read_bytes()
                self.assertFalse(self.save(*maps, session))
                self.assertEqual(altered, self.path.read_bytes())
        session = AllocationSnapshotSession()
        maps = self.load(session)
        same = self.path.read_bytes()
        replace_path = self.path.with_name("replacement.json")
        replace_path.write_bytes(same)
        replace_path.replace(self.path)
        self.assertFalse(self.save(*maps, session))
        self.assertEqual(same, self.path.read_bytes())

    def test_invalid_or_failed_load_never_authorizes_overwrite(self):
        self.path.parent.mkdir()
        valid = {"version": 1, "mode": "Live", "entry_allocations": {}, "open_position_records": {}}
        cases = (
            b'{"version":1,"mode":"Live","entry_allocations":{},"entry_allocations":{},"open_position_records":{}}',
            b"not json", b"[]", b'{"version":true}',
            json.dumps({**valid, "entry_allocations": {"BTCUSDT:L": [42]}}).encode(),
            json.dumps({**valid, "mode": "Demo"}).encode(),
            json.dumps({**valid, "gui_trade_event_receipts": [self.event(), self.event()]}).encode(),
            json.dumps({**valid, "entry_allocations": {"BTCUSDT:L": [{"spot_sell_recoveries": "bad"}]}}).encode(),
        )
        for raw in cases:
            with self.subTest(raw=raw):
                self.path.write_bytes(raw)
                session = AllocationSnapshotSession()
                self.assertEqual(({}, {}), self.load(session))
                self.assertEqual("blocked", session.state)
                self.assertFalse(self.save({}, {}, session))
                self.assertEqual(raw, self.path.read_bytes())
        self.path.write_text(json.dumps(valid))
        session = AllocationSnapshotSession()
        with patch.object(persistence, "_read_receipt", side_effect=PermissionError("denied")):
            self.assertEqual(({}, {}), self.load(session))
        self.assertFalse(session.ready)
        self.assertFalse(self.save({}, {}, session))

    def test_mode_path_unloaded_and_sessionless_existing_state_are_fenced(self):
        session = AllocationSnapshotSession()
        self.assertFalse(self.save(*self.maps(), session))
        self.load(session)
        self.assertTrue(self.save(*self.maps(), session))
        raw = self.path.read_bytes()
        self.assertFalse(self.save(*self.maps(), session, mode="Demo"))
        self.assertFalse(self.save(*self.maps()))
        self.assertFalse(save_position_allocations(
            *self.maps(), this_file=self.this_file.with_name("different_root.py").parent.parent / "different" / "app" / "gui" / "shell.py",
            mode="Live", session=session,
        ))
        session.invalidate("mode_changed")
        self.assertFalse(self.save(*self.maps(), session))
        self.assertEqual(raw, self.path.read_bytes())

    def test_atomic_write_failure_retains_old_receipt_file_and_cleans_temp(self):
        session = AllocationSnapshotSession()
        self.load(session)
        self.assertTrue(self.save(*self.maps(), session))
        receipt = (session._bytes, session._identity, copy.deepcopy(session._snapshot))
        raw = self.path.read_bytes()
        with patch("app.integrations.exchanges.binance.orders.order_intent_store._publish", side_effect=OSError("disk failure")):
            self.assertFalse(self.save(*self.maps(0.2), session, event_receipt=self.event()))
        self.assertEqual(raw, self.path.read_bytes())
        self.assertEqual(receipt, (session._bytes, session._identity, session._snapshot))
        self.assertEqual([], list(self.path.parent.glob("*.tmp")))
        self.assertFalse(session.has_trade_event_receipt(self.event()))
        self.assertFalse(session.ready)
        self.assertFalse(self.save(*self.maps(0.2), session, event_receipt=self.event()))
        self.load(session)
        self.assertTrue(self.save(*self.maps(0.2), session, event_receipt=self.event()))
        self.assertTrue(session.has_trade_event_receipt(self.event()))

    def test_event_receipts_survive_full_close_restart_and_reject_conflict(self):
        session = AllocationSnapshotSession()
        self.load(session)
        receipt = self.event()
        self.assertTrue(self.save(*self.maps(), session, event_receipt=receipt))
        self.assertTrue(self.save({}, {}, session))
        reopened = AllocationSnapshotSession()
        self.assertEqual(({}, {}), self.load(reopened))
        self.assertTrue(reopened.has_trade_event_receipt(receipt))
        raw = self.path.read_bytes()
        conflict = {**receipt, "quantity": "0.2"}
        with self.assertRaisesRegex(ValueError, "conflicts"):
            reopened.has_trade_event_receipt(conflict)
        self.assertFalse(self.save({}, {}, reopened, event_receipt=conflict))
        self.assertEqual(raw, self.path.read_bytes())
        self.load(reopened)
        self.assertTrue(self.save({}, {}, reopened, event_receipt=receipt))
        self.assertEqual([receipt], json.loads(self.path.read_text())["gui_trade_event_receipts"])

    def test_same_committed_event_cannot_publish_another_allocation_mutation(self):
        session = AllocationSnapshotSession()
        self.load(session)
        receipt = self.event()
        self.assertTrue(self.save(*self.maps(), session, event_receipt=receipt))
        raw = self.path.read_bytes()
        self.assertFalse(self.save(*self.maps(0.2), session, event_receipt=receipt))
        self.assertEqual(raw, self.path.read_bytes())
        self.load(session)
        self.assertTrue(self.save(*self.maps(), session, event_receipt=receipt))
        self.assertEqual(raw, self.path.read_bytes())

    def test_same_window_concurrent_receipt_advance_cannot_authorize_stale_candidate(self):
        session = AllocationSnapshotSession()
        self.load(session)
        self.assertTrue(self.save(*self.maps(), session))
        constructing, resume = threading.Event(), threading.Event()
        results = []
        serialize = persistence._serialize_allocation_key
        worker_identity = []

        def delayed_serialize(key):
            if threading.get_ident() == worker_identity[0]:
                constructing.set()
                if not resume.wait(10):
                    raise RuntimeError("publication barrier not released")
            return serialize(key)

        def stale_writer():
            worker_identity.append(threading.get_ident())
            results.append(self.save(*self.maps(0.2), session))

        worker = threading.Thread(target=stale_writer)
        with patch.object(persistence, "_serialize_allocation_key", delayed_serialize):
            worker.start()
            try:
                self.assertTrue(constructing.wait(5))
                self.assertTrue(self.save(*self.maps(0.3), session))
                committed = self.path.read_bytes()
                committed_receipt = session._bytes, session._identity, copy.deepcopy(session._snapshot)
            finally:
                resume.set()
                worker.join(10)
        self.assertFalse(worker.is_alive())
        self.assertEqual([False], results)
        self.assertEqual(committed, self.path.read_bytes())
        self.assertEqual(committed_receipt, (session._bytes, session._identity, session._snapshot))

    def test_invalidation_during_candidate_construction_blocks_unchanged_file(self):
        session = AllocationSnapshotSession()
        self.load(session)
        self.assertTrue(self.save(*self.maps(), session))
        raw = self.path.read_bytes()
        original = persistence._serialize_allocation_key

        def invalidate_at_construction(key):
            session.invalidate("mode_changed")
            return original(key)

        with patch.object(persistence, "_serialize_allocation_key", invalidate_at_construction):
            self.assertFalse(self.save(*self.maps(0.2), session))
        self.assertEqual(raw, self.path.read_bytes())
        self.assertFalse(session.ready)

    def test_late_load_cannot_clear_a_concurrent_mode_invalidation(self):
        self.assertTrue(self.save(*self.maps()))
        session = AllocationSnapshotSession()
        decoding, resume = threading.Event(), threading.Event()
        results = []
        decode = persistence._decode

        def paused_decode(raw, mode):
            decoding.set()
            if not resume.wait(10):
                raise RuntimeError("load barrier not released")
            return decode(raw, mode)

        worker = threading.Thread(target=lambda: results.append(self.load(session)))
        with patch.object(persistence, "_decode", paused_decode):
            worker.start()
            try:
                self.assertTrue(decoding.wait(5))
                session.invalidate("mode_changed")
                fenced_generation = session._generation
            finally:
                resume.set()
                worker.join(10)
        self.assertFalse(worker.is_alive())
        self.assertEqual([({}, {})], results)
        self.assertFalse(session.ready)
        self.assertEqual("mode_changed", session.last_error)
        self.assertEqual(fenced_generation, session._generation)

    def test_parallel_new_load_supersedes_older_result_or_error(self):
        self.assertTrue(self.save(*self.maps()))
        decode = persistence._decode
        for older_error in (False, True):
            with self.subTest(older_error=older_error):
                session = AllocationSnapshotSession()
                decoding, resume, newer_started = threading.Event(), threading.Event(), threading.Event()
                older_identity = []
                results = {}
                begin_load = session._begin_load

                def observed_begin():
                    token = begin_load()
                    if threading.get_ident() != older_identity[0]:
                        newer_started.set()
                    return token

                def paused_decode(raw, mode):
                    if threading.get_ident() == older_identity[0]:
                        decoding.set()
                        if not resume.wait(10):
                            raise RuntimeError("load barrier not released")
                        if older_error:
                            raise ValueError("older load failed")
                    return decode(raw, mode)

                def older_load():
                    older_identity.append(threading.get_ident())
                    results["older"] = self.load(session)

                older = threading.Thread(target=older_load)
                newer = threading.Thread(target=lambda: results.update(newer=self.load(session)))
                with patch.object(session, "_begin_load", observed_begin), patch.object(persistence, "_decode", paused_decode):
                    older.start()
                    try:
                        self.assertTrue(decoding.wait(5))
                        newer.start()
                        self.assertTrue(newer_started.wait(5))
                    finally:
                        resume.set()
                        older.join(10)
                        if newer.ident is not None:
                            newer.join(10)
                self.assertFalse(older.is_alive())
                self.assertFalse(newer.is_alive())
                self.assertEqual(({}, {}), results["older"])
                self.assertEqual(self.maps(), results["newer"])
                self.assertTrue(session.ready)
                self.assertIsNone(session.last_error)

    def test_dashboard_late_load_handoff_cannot_assign_old_maps_against_new_receipt(self):
        self.assertTrue(self.save(*self.maps()))
        session = AllocationSnapshotSession()
        original_maps = self.load(session)
        window = SimpleNamespace(_allocation_snapshot_session=session,
                                 _entry_allocations=original_maps[0], _open_position_records=original_maps[1])
        loaded, resume = threading.Event(), threading.Event()
        results = []

        def delayed_loader(**options):
            result = load_position_allocations(this_file=self.this_file, **options)
            loaded.set()
            if not resume.wait(10):
                raise RuntimeError("dashboard handoff barrier not released")
            return result

        worker = threading.Thread(target=lambda: results.append(state_runtime._reload_position_allocation_snapshot(window, "Live")))
        with patch.object(state_runtime, "_LOAD_POSITION_ALLOCATIONS", delayed_loader):
            worker.start()
            try:
                self.assertTrue(loaded.wait(5))
                writer = AllocationSnapshotSession()
                self.load(writer)
                self.assertTrue(self.save(*self.maps(0.3), writer))
                self.assertEqual(self.maps(0.3), self.load(session))
                fresh_generation = session._generation
            finally:
                resume.set()
                worker.join(10)
        self.assertFalse(worker.is_alive())
        self.assertEqual([False], results)
        self.assertEqual(fresh_generation, session._generation)
        self.assertIs(original_maps[0], window._entry_allocations)
        self.assertIs(original_maps[1], window._open_position_records)
        self.assertEqual(self.maps(0.3)[0], self.load(session)[0])

    def test_ticket_load_keeps_admission_blocked_until_actual_two_map_handoff(self):
        self.assertTrue(self.save(*self.maps()))
        session = AllocationSnapshotSession()
        original_maps = self.load(session)
        window = SimpleNamespace(_allocation_snapshot_session=session,
                                 _entry_allocations=original_maps[0], _open_position_records=original_maps[1])
        writer = AllocationSnapshotSession()
        self.load(writer)
        self.assertTrue(self.save(*self.maps(0.3), writer))
        committed = self.path.read_bytes()
        loaded, resume = threading.Event(), threading.Event()
        results = []

        def delayed_loader(**options):
            result = load_position_allocations(this_file=self.this_file, **options)
            loaded.set()
            if not resume.wait(10):
                raise RuntimeError("dashboard handoff barrier not released")
            return result

        worker = threading.Thread(target=lambda: results.append(state_runtime._reload_position_allocation_snapshot(window, "Live")))
        with patch.object(state_runtime, "_LOAD_POSITION_ALLOCATIONS", delayed_loader):
            worker.start()
            try:
                self.assertTrue(loaded.wait(5))
                self.assertEqual("loaded_pending", session.state)
                self.assertFalse(session.ready)
                self.assertFalse(self.save(window._entry_allocations, window._open_position_records, session))
                self.assertEqual(committed, self.path.read_bytes())
            finally:
                resume.set()
                worker.join(10)
        self.assertEqual([False], results)
        self.assertIs(original_maps[0], window._entry_allocations)
        self.assertIs(original_maps[1], window._open_position_records)
        self.assertFalse(session.ready)

        def loader(**options):
            return load_position_allocations(this_file=self.this_file, **options)

        with patch.object(state_runtime, "_LOAD_POSITION_ALLOCATIONS", loader):
            self.assertTrue(state_runtime._reload_position_allocation_snapshot(window, "Live"))
        self.assertTrue(session.ready)
        self.assertEqual(self.maps(0.3), (window._entry_allocations, window._open_position_records))

    def test_unexpected_storage_or_load_error_propagates_with_admission_fenced(self):
        session = AllocationSnapshotSession()
        self.load(session)
        self.assertTrue(self.save(*self.maps(), session))
        original = self.path.read_bytes()
        with patch.object(persistence, "_write_snapshot", side_effect=RuntimeError("unexpected storage failure")):
            with self.assertRaisesRegex(RuntimeError, "unexpected storage failure"):
                self.save(*self.maps(0.2), session)
        self.assertFalse(session.ready)
        self.assertEqual(original, self.path.read_bytes())
        maps = self.load(session)
        window = SimpleNamespace(_allocation_snapshot_session=session,
                                 _entry_allocations=maps[0], _open_position_records=maps[1])
        with patch.object(state_runtime, "_LOAD_POSITION_ALLOCATIONS", side_effect=RuntimeError("unexpected loader failure")):
            with self.assertRaisesRegex(RuntimeError, "unexpected loader failure"):
                state_runtime._reload_position_allocation_snapshot(window, "Live")
        self.assertFalse(session.ready)
        self.assertIs(maps[0], window._entry_allocations)
        self.assertIs(maps[1], window._open_position_records)
        with patch.object(persistence, "_decode", side_effect=RuntimeError("unexpected decode failure")):
            with self.assertRaisesRegex(RuntimeError, "unexpected decode failure"):
                self.load(session)
        self.assertFalse(session.ready)
        self.assertEqual(original, self.path.read_bytes())

    def test_bad_event_registry_or_nonfinite_candidate_is_not_published(self):
        session = AllocationSnapshotSession()
        self.load(session)
        for descriptor in (
            {**self.event(), "version": True}, {**self.event(), "quantity": "NaN"},
            {**self.event(), "quantity": "0"}, {**self.event(), "raw_response": "secret"},
            {**self.event(), "event_id": "bad\nvalue"}, {**self.event(), "kind": "unknown"},
        ):
            with self.subTest(descriptor=descriptor):
                self.load(session)
                self.assertFalse(self.save({}, {}, session, event_receipt=descriptor))
                self.assertFalse(self.path.exists())
        self.load(session)
        self.assertFalse(self.save(*self.maps(float("nan")), session))
        self.assertFalse(self.path.exists())

    def test_path_resolution_has_no_migration_and_loaded_legacy_uses_transaction(self):
        legacy = self.path.parent.parent / self.path.name
        allocations, records = self.maps()
        payload = {"version": 1, "mode": "Live", "timestamp": 1,
                   "entry_allocations": {"BTCUSDT:L": allocations[("BTCUSDT", "L")]},
                   "open_position_records": {"BTCUSDT:L": records[("BTCUSDT", "L")]}, "preserved": "extension"}
        legacy.write_text(json.dumps(payload))
        self.assertEqual(self.path, persistence.get_position_allocations_path(self.this_file))
        self.assertFalse(self.path.exists())
        self.assertTrue(legacy.exists())
        session = AllocationSnapshotSession()
        self.assertEqual((allocations, records), self.load(session))
        self.assertFalse(legacy.exists())
        self.assertEqual(payload, json.loads(self.path.read_text()))
        self.assertTrue(self.save(allocations, records, session))
        self.assertEqual("extension", json.loads(self.path.read_text())["preserved"])

    def test_symlink_state_and_parent_fail_closed(self):
        self.path.parent.mkdir()
        external = Path(self.temp.name) / "external.json"
        external.write_text("unchanged")
        try:
            self.path.symlink_to(external)
        except OSError as exc:
            self.skipTest(f"symlink privilege unavailable: {exc}")
        session = AllocationSnapshotSession()
        self.assertEqual(({}, {}), self.load(session))
        self.assertFalse(self.save({}, {}, session))
        self.assertEqual("unchanged", external.read_text())

    def seed_real_recovered_row(self):
        fill = {
            "symbol": "BTCUSDT", "client_order_id": "buy-A", "order_id": 75,
            "trade_ids": [101], "trade_count": 1, "gross_qty": "0.1", "net_qty": "0.1",
            "gross_quote_qty": "2000", "net_quote_cost": "2000", "average_cost": "20000",
            "commissions": [], "base_asset": "BTC", "quote_asset": "USDT",
            "fill_time_ms": 1780000000000, "signature": "a" * 64,
        }
        self.assertTrue(recovery.persist_spot_buy_allocation(self.path, fill))
        return fill

    def seed_real_sell_recovery(self, quantity="0.04"):
        baseline = recovery.spot_live_allocation_baseline(self.path, symbol="BTCUSDT")
        self.assertIsNotNone(baseline)
        assert baseline is not None
        sell = {
            "symbol": "BTCUSDT", "client_order_id": "sell-B", "order_id": 76, "side": "SELL",
            "trade_ids": [201], "gross_qty": quantity, "portfolio_qty": quantity,
            "gross_quote_qty": str(float(quantity) * 20000), "base_fee_qty": "0", "quote_fee_qty": "0",
            "net_quote_proceeds": str(float(quantity) * 20000), "commissions": [],
            "base_asset": "BTC", "quote_asset": "USDT", "fill_time_ms": 1780000001000,
            "signature": "b" * 64, "pre_order_portfolio_signature": baseline["signature"],
            "pre_order_portfolio_qty": baseline["quantity"],
        }
        self.assertTrue(recovery.persist_spot_sell_allocation(self.path, sell))

    def test_fresh_loaded_recovered_remaining_row_and_proofs_cannot_be_mutated_or_duplicated(self):
        self.seed_real_recovered_row()
        self.seed_real_sell_recovery()
        session = AllocationSnapshotSession()
        allocations, records = self.load(session)
        raw = self.path.read_bytes()
        key = ("BTCUSDT", "L")
        for mutate in (
            lambda a, r: a[key][0].update(qty=0.1),
            lambda a, r: a[key][0].update(entry_price=25000),
            lambda a, r: a[key][0]["spot_sell_recoveries"][0].update(trade_ids=[999]),
            lambda a, r: a[key][0].pop("spot_sell_recoveries"),
            lambda a, r: a.pop(key),
            lambda a, r: r[key]["data"].update(qty=0.1),
            lambda a, r: r[key]["allocations"][0].update(qty=0.1),
            lambda a, r: r.pop(key),
            lambda a, r: a[key].append({**a[key][0], "qty": 0.2}),
            lambda a, r: a.update({("ETHUSDT", "L"): [{**a[key][0], "symbol": "ETHUSDT"}]}),
            lambda a, r: a.update({("ETHUSDT", "L"): [{**a[key][0], "client_order_id": "different", "symbol": "ETHUSDT"}]}),
            lambda a, r: a.update({("ETHUSDT", "L"): [{**a[key][0], "client_order_id": "different", "trade_id": "different", "order_id": "76", "symbol": "ETHUSDT"}]}),
        ):
            with self.subTest(mutate=mutate):
                self.load(session)
                a, r = copy.deepcopy(allocations), copy.deepcopy(records)
                mutate(a, r)
                self.assertFalse(self.save(a, r, session))
                self.assertEqual(raw, self.path.read_bytes())
        # Annotation of the position and an unrelated symbol do not freeze the GUI.
        self.load(session)
        records[key]["data"]["pnl_value"] = 20.0
        allocations[("ETHUSDT", "L")] = [{"symbol": "ETHUSDT", "side_key": "L", "qty": 1.0,
                                          "client_order_id": "unrelated-ETH", "order_id": "75", "trade_id": "unrelated-ETH"}]
        self.assertTrue(self.save(allocations, records, session))
        self.assertEqual("0.04", self.load(session)[0][key][0]["spot_sell_recoveries"][0]["consumed_qty"])

    def test_closed_owned_proof_cannot_be_removed_or_reactivated_after_reload(self):
        self.seed_real_recovered_row()
        self.seed_real_sell_recovery("0.1")
        session = AllocationSnapshotSession()
        allocations, records = self.load(session)
        self.assertEqual({}, records)
        self.assertEqual("Closed", allocations[("BTCUSDT", "L")][0]["status"])
        raw = self.path.read_bytes()
        self.assertFalse(self.save({}, {}, session))
        self.load(session)
        reopened = copy.deepcopy(allocations)
        reopened[("BTCUSDT", "L")][0]["status"] = "Active"
        self.assertFalse(self.save(reopened, self.maps()[1], session))
        self.load(session)
        self.assertFalse(self.save(allocations, self.maps()[1], session))
        self.assertEqual(raw, self.path.read_bytes())
        self.load(session)
        self.assertTrue(self.save(allocations, records, session))

    def test_actual_recovery_preserves_committed_gui_receipt_registry(self):
        session = AllocationSnapshotSession()
        self.load(session)
        receipt = self.event()
        self.assertTrue(self.save({}, {}, session, event_receipt=receipt))
        self.seed_real_recovered_row()
        self.seed_real_sell_recovery()
        self.load(session)
        self.assertTrue(session.has_trade_event_receipt(receipt))

    def test_dashboard_sessions_load_both_maps_and_failed_mode_reload_preserves_both(self):
        self.assertTrue(self.save(*self.maps()))
        def loader(**kwargs):
            return load_position_allocations(this_file=self.this_file, **kwargs)
        first = SimpleNamespace(config={}, mode_combo=SimpleNamespace(currentText=lambda: "Live"))
        second = SimpleNamespace(config={}, mode_combo=SimpleNamespace(currentText=lambda: "Live"))
        with patch.object(state_runtime, "_LOAD_POSITION_ALLOCATIONS", loader):
            for window in (first, second):
                state_runtime._initialize_dashboard_runtime_state(window, current_max_closed_history=10, gui_max_closed_history=10)
            self.assertIsNot(first._allocation_snapshot_session, second._allocation_snapshot_session)
            first._pending_trade_reconciliation = [{"pending": True}]
            old_maps = first._entry_allocations, first._open_position_records
            self.assertFalse(state_runtime._reload_position_allocation_snapshot(first, "Demo"))
            self.assertIs(old_maps[0], first._entry_allocations)
            self.assertIs(old_maps[1], first._open_position_records)
            self.assertFalse(first._allocation_snapshot_session.ready)
            self.assertEqual([{"pending": True}], first._pending_trade_reconciliation)
            self.assertTrue(state_runtime._reload_position_allocation_snapshot(first, "Live"))
            self.assertTrue(first._allocation_snapshot_session.ready)

    def test_live_allocations_are_not_dropped_after_one_day_offline(self):
        with tempfile.TemporaryDirectory() as tmp:
            this_file = Path(tmp) / "Languages" / "Python" / "app" / "gui" / "window_shell.py"
            this_file.parent.mkdir(parents=True)
            entry = {
                "symbol": "BTCUSDT", "side_key": "L", "qty": 0.1,
                "entry_price": 20000.0, "status": "Active", "client_order_id": "fill-A",
            }
            record = {
                "symbol": "BTCUSDT", "side_key": "L", "status": "Active",
                "data": {"symbol": "BTCUSDT", "side_key": "L"}, "allocations": [entry],
            }
            with patch("app.gui.shared.allocation_persistence.time.time", return_value=1000.0):
                self.assertTrue(save_position_allocations(
                    {("BTCUSDT", "L"): [entry]},
                    {("BTCUSDT", "L"): record},
                    this_file=this_file,
                    mode="Live",
                ))
            with patch("app.gui.shared.allocation_persistence.time.time", return_value=100000.0):
                allocations, records = load_position_allocations(this_file=this_file, mode="Live")

            self.assertEqual("fill-A", allocations[("BTCUSDT", "L")][0]["client_order_id"])
            self.assertEqual("Active", records[("BTCUSDT", "L")]["status"])


if __name__ == "__main__":
    unittest.main()
