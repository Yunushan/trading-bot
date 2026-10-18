"""Explicit restart bookkeeping through actual Spot wrappers and loaded sessions."""
from __future__ import annotations

from contextlib import contextmanager
from copy import deepcopy
import hashlib
import json
import unittest
from unittest.mock import patch
from uuid import uuid4

import test_spot_buy_generation_faults as buy_fixture

from app.gui.shared import allocation_persistence as allocations
from app.integrations.exchanges.binance.orders import order_intent_runtime as intents
from app.integrations.exchanges.binance.orders import spot_desktop_buy_recovery_runtime as recovery
from app.integrations.exchanges.binance.orders import spot_fill_recovery_runtime as fills
from app.integrations.exchanges.binance.orders.order_intent_store import ledger_transaction, ledger_transactions, write_ledger
from app.integrations.exchanges.binance.orders.spot_execution_owner import owner_marker_path, owner_administration_lock
from app.settings.live_safety import LiveTradingSafetyError
from app.integrations.exchanges.binance.orders.spot_inventory_namespace_runtime import publish_owned_spot_fill


class SpotDesktopBuyRecoveryTests(unittest.TestCase):
    def setUp(self):
        self.actual = buy_fixture.SpotBuyGenerationFaultsTests()
        self.actual.setUp()
        self.addCleanup(self.actual.doCleanups)
        old_window = self.actual._load_window()
        event, self.fill = self.actual._buy(base_fee="0.00004")
        self.initial_bytes = self.actual.fixture.allocation_path.read_bytes()
        self.namespace = deepcopy(self.actual.namespace)
        self.actual._dispatch(old_window, event, saver=lambda *_args, **_kwargs: False)
        self.client_id = self.fill["client_order_id"]
        self.path = self.actual.fixture.allocation_path
        self.intent_path = intents._intent_path(self.actual.wrapper)
        self.assertEqual(self.initial_bytes, self.path.read_bytes())
        self.actual.wrapper._spot_execution_owner.close()
        self.actual.wrapper = self.actual.fixture.wrapper()
        self.wrapper = self.actual.wrapper
        self.window = self.actual._load_window()
        self.assertFalse(getattr(self.wrapper, "_desktop_spot_entry_origins", None))
        self.assertEqual(1, self.wrapper.get_order_intent_status()["unresolved_count"])

    def publish_existing_buy(self):
        # Actual signed administration exclusion after this restart fixture.
        self.wrapper._resolve_spot_account_uid()
        record = intents._get_order_intent_record(self.wrapper, self.fill["client_order_id"])
        with owner_administration_lock(self.intent_path), recovery._desktop_inventory_administration(self.wrapper, self.intent_path):
            return publish_owned_spot_fill(
                self.wrapper, self.path, self.fill, expected_record=record, operation=fills.persist_spot_buy_allocation,
            )

    def prepare(self):
        discovery = recovery.discover_spot_desktop_buy_recoveries(self.wrapper, allocation_path=self.path)
        self.assertEqual(1, len(discovery.items))
        source = recovery.capture_spot_desktop_buy_recovery_source(
            self.window._allocation_snapshot_session, self.window._entry_allocations,
            self.window._open_position_records, allocation_path=self.path,
        )
        return discovery.items[0], source

    @contextmanager
    def handoff(self):
        session = self.window._allocation_snapshot_session
        with session._mutex:
            if (self.window.shared_binance is not self.wrapper
                    or not session.matches_loaded_maps(self.window._entry_allocations, self.window._open_position_records)):
                raise LiveTradingSafetyError("Fresh window account/maps changed")
            yield

    def recover(self, item=None, source=None, *, handoff=None):
        if item is None:
            item, source = self.prepare()
        return recovery.recover_spot_desktop_buy(
            self.wrapper, item, allocation_path=self.path, expected_loaded_receipt=source,
            publication_handoff=handoff or self.handoff,
        )

    def reload(self, *, expect_accepted=True):
        session = self.window._allocation_snapshot_session
        ticket = allocations.AllocationSnapshotLoadTicket()
        entries, records = allocations.load_position_allocations(
            this_file=self.actual.fixture.home / "unused.py", mode="Live", session=session, load_ticket=ticket,
        )
        original_maps = self.window._entry_allocations, self.window._open_position_records
        with session.loaded_handoff(ticket) as accepted:
            self.assertEqual(expect_accepted, accepted)
            if accepted:
                self.window._entry_allocations, self.window._open_position_records = entries, records
        if expect_accepted:
            self.assertTrue(session.matches_loaded_maps(entries, records))
        else:
            self.assertFalse(session.ready)
            self.assertIs(original_maps[0], self.window._entry_allocations)
            self.assertIs(original_maps[1], self.window._open_position_records)
        return session

    def assert_fenced_without_publication(self):
        self.assertEqual(self.initial_bytes, self.path.read_bytes())
        current = self.wrapper._get_order_intent_record(self.client_id)
        self.assertEqual(self.fill["signature"], current["primary_fill_signature"])
        self.assertIsNot(current.get("portfolio_reconciled"), True)
        self.assertEqual(1, len(self.actual.market_posts))
        self.assertEqual("recovery_required", json.loads(owner_marker_path(self.intent_path).read_text())["state"])

    def test_restart_recovers_primary_receipt_and_requires_fresh_loaded_handoff(self):
        item, source = self.prepare()
        self.assertEqual("0.09996", item.expected_record["primary_fill_receipt"]["net_qty"])
        self.window._pending_allocation_reconciliations = {("ETHUSDT", "L"): [{"operation": "unrelated"}]}
        result = self.recover(item, source)
        self.assertTrue(result["allocation_published"])
        self.assertTrue(result["portfolio_reconciled"])
        self.assertFalse(result["already_present"])
        self.assertTrue(result["recovery_required"])
        self.assertFalse(source.session.ready)
        self.assertEqual({}, self.window._entry_allocations)
        self.assertEqual(0, self.wrapper.get_order_intent_status()["unresolved_count"])
        session = self.reload()
        self.assertEqual(result["allocation_receipt"], (session._bytes, session._identity))
        row = self.window._entry_allocations[("BTCUSDT", "L")][0]
        self.assertAlmostEqual(0.09996, row["qty"])
        self.assertEqual("RECOVERY", row["interval"])
        self.assertEqual("Recovered Spot fill", row["interval_display"])
        self.assertIn(("ETHUSDT", "L"), self.window._pending_allocation_reconciliations)
        self.assertEqual(1, len(self.actual.market_posts))
        self.assertEqual("recovery_required", json.loads(owner_marker_path(self.intent_path).read_text())["state"])
        with self.assertRaisesRegex(LiveTradingSafetyError, "rearm"):
            self.wrapper._ensure_spot_execution_owner()

    def test_existing_partial_and_closed_acquisition_replay_never_restores_inventory(self):
        for consumed in ("0.04", "0.09996"):
            with self.subTest(consumed=consumed):
                scenario = type(self)()
                scenario.setUp()
                try:
                    scenario.publish_existing_buy()
                    scenario.actual._sell(consumed)
                    before = scenario.path.read_bytes()
                    scenario.reload()
                    item, source = scenario.prepare()
                    self.assertNotEqual(item.expected_record["desktop_entry_source"]["snapshot_signature"],
                                        hashlib.sha256(source.raw).hexdigest())
                    result = scenario.recover(item, source)
                    self.assertTrue(result["already_present"])
                    self.assertTrue(result["portfolio_reconciled"])
                    self.assertEqual(before, scenario.path.read_bytes())
                    payload = json.loads(before)
                    row = payload["entry_allocations"]["BTCUSDT:L"][0]
                    if consumed == "0.09996":
                        self.assertEqual("Closed", row["status"])
                        self.assertNotIn("BTCUSDT:L", payload["open_position_records"])
                    else:
                        self.assertAlmostEqual(0.09996 - float(consumed), row["qty"])
                    self.assertEqual(1, len(scenario.actual.market_posts))
                finally:
                    scenario.doCleanups()

    def test_marker_failure_is_durable_restart_replay_and_marker_runs_outside_storage_locks(self):
        item, source = self.prepare()
        with patch.object(recovery, "_mark_exact_acquisition", side_effect=OSError("Synthetic disk fault")):
            result = self.recover(item, source)
        self.assertTrue(result["allocation_published"])
        self.assertFalse(result["portfolio_reconciled"])
        self.assertTrue(result["error"])
        self.assertEqual(1, self.wrapper.get_order_intent_status()["unresolved_count"])
        committed = self.path.read_bytes()
        self.actual.wrapper = self.actual.fixture.wrapper()
        self.wrapper = self.actual.wrapper
        self.window = self.actual._load_window()
        original_marker = recovery._mark_exact_acquisition
        def marker(*args, **kwargs):
            with ledger_transactions(self.intent_path, self.path):
                pass
            self.assertFalse(self.window._allocation_snapshot_session.ready)
            return original_marker(*args, **kwargs)
        with patch.object(recovery, "_mark_exact_acquisition", side_effect=marker):
            retried = self.recover()
        self.assertTrue(retried["portfolio_reconciled"], retried)
        self.assertTrue(retried["already_present"])
        self.assertEqual(committed, self.path.read_bytes())
        self.assertEqual(1, len(self.actual.market_posts))

    def test_changed_store_or_full_intent_blocks_before_allocation_publication(self):
        for change in ("store", "record"):
            with self.subTest(change=change):
                scenario = type(self)()
                scenario.setUp()
                try:
                    item, source = scenario.prepare()
                    with ledger_transaction(scenario.intent_path):
                        ledger = intents._read_ledger(scenario.intent_path)
                        if change == "store":
                            ledger["store_id"] = str(uuid4())
                        else:
                            ledger["intents"][scenario.client_id]["source"] = "changed-record"
                        write_ledger(scenario.intent_path, ledger)
                    with self.assertRaisesRegex(LiveTradingSafetyError, "intent or store changed"):
                        scenario.recover(item, source)
                    scenario.assert_fenced_without_publication()
                finally:
                    scenario.doCleanups()

    def test_changed_wrapper_credentials_or_signed_uid_cannot_redirect_recovery(self):
        item, source = self.prepare()
        other = self.actual.fixture.wrapper()
        with self.assertRaisesRegex(LiveTradingSafetyError, "context changed"):
            recovery.recover_spot_desktop_buy(other, item, allocation_path=self.path,
                expected_loaded_receipt=source, publication_handoff=self.handoff)
        original_secret = self.wrapper.api_secret
        self.wrapper.api_secret = "changed-offline-secret"
        with self.assertRaises(LiveTradingSafetyError):
            self.recover(item, source)
        self.wrapper.api_secret = original_secret
        self.actual.fixture.venue.uid += 1
        with self.assertRaisesRegex(LiveTradingSafetyError, "signed account identity changed"):
            self.recover(item, source)
        self.actual.fixture.venue.uid -= 1
        self.assert_fenced_without_publication()

    def test_changed_file_session_or_actual_maps_blocks_before_publication(self):
        for change in ("file", "session", "maps", "map_replacement"):
            with self.subTest(change=change):
                scenario = type(self)()
                scenario.setUp()
                try:
                    item, source = scenario.prepare()
                    if change == "file":
                        write_ledger(scenario.path, {"version": 1, "mode": "Live", "entry_allocations": {},
                                                     "open_position_records": {}, "timestamp": 1,
                                                     "spot_account_namespace": deepcopy(scenario.namespace)})
                    elif change == "session":
                        source.session.invalidate("Changed session")
                    elif change == "maps":
                        scenario.window._entry_allocations[("ETHUSDT", "L")] = []
                    else:
                        scenario.window._entry_allocations = {("ETHUSDT", "L"): []}
                    before = scenario.path.read_bytes() if scenario.path.exists() else None
                    with self.assertRaises(LiveTradingSafetyError):
                        scenario.recover(item, source)
                    self.assertEqual(before, scenario.path.read_bytes() if scenario.path.exists() else None)
                    self.assertEqual(1, scenario.wrapper.get_order_intent_status()["unresolved_count"])
                    self.assertEqual(1, len(scenario.actual.market_posts))
                finally:
                    scenario.doCleanups()

    def test_missing_acquisition_changed_original_baseline_or_missing_descriptor_fails_closed(self):
        for descriptor in (None, "changed_digest"):
            with self.subTest(descriptor=descriptor):
                scenario = type(self)()
                scenario.setUp()
                try:
                    with ledger_transaction(scenario.intent_path):
                        ledger = intents._read_ledger(scenario.intent_path)
                        record = ledger["intents"][scenario.client_id]
                        if descriptor is None:
                            record.pop("desktop_entry_source")
                        else:
                            record["desktop_entry_source"]["snapshot_signature"] = "0" * 64
                        write_ledger(scenario.intent_path, ledger)
                    with self.assertRaisesRegex(LiveTradingSafetyError, "original source baseline"):
                        scenario.recover()
                    scenario.assert_fenced_without_publication()
                finally:
                    scenario.doCleanups()

    def test_mutated_work_item_cannot_replace_its_durable_receipt(self):
        item, source = self.prepare()
        item.expected_record["primary_fill_receipt"]["net_quote_cost"] = "3000"
        with self.assertRaisesRegex(LiveTradingSafetyError, "work item changed"):
            self.recover(item, source)
        self.assert_fenced_without_publication()

    def test_writer_false_error_and_unexpected_failure_preserve_fence_and_durable_intent(self):
        for outcome in (False, OSError("Synthetic write failed"), AssertionError("Unexpected write failure")):
            with self.subTest(outcome=outcome):
                scenario = type(self)()
                scenario.setUp()
                try:
                    item, source = scenario.prepare()
                    with patch.object(recovery, "_persist_spot_buy_allocation_unlocked",
                                      return_value=outcome if outcome is False else None,
                                      side_effect=outcome if isinstance(outcome, BaseException) else None):
                        with self.assertRaises((LiveTradingSafetyError, OSError, AssertionError)):
                            scenario.recover(item, source)
                    self.assertFalse(source.session.ready)
                    scenario.assert_fenced_without_publication()
                    scenario.reload()
                    self.assertTrue(scenario.recover()["portfolio_reconciled"])
                finally:
                    scenario.doCleanups()

    def test_active_execution_owner_blocks_discovery_without_closing_or_rearming_it(self):
        active = buy_fixture.SpotBuyGenerationFaultsTests()
        active.setUp()
        try:
            active._load_window()
            active._buy()
            owner = active.wrapper._spot_execution_owner
            with self.assertRaisesRegex(LiveTradingSafetyError, "owner is active"):
                recovery.discover_spot_desktop_buy_recoveries(active.wrapper, allocation_path=active.fixture.allocation_path)
            self.assertIsNotNone(owner.fd)
            self.assertEqual(1, len(active.market_posts))
        finally:
            active.doCleanups()

    def test_changed_loaded_record_snapshot_identity_or_wrong_source_type_fails_closed(self):
        for change in ("record_qty", "annotation", "snapshot", "identity", "wrong_type"):
            with self.subTest(change=change):
                scenario = type(self)()
                scenario.setUp()
                try:
                    scenario.publish_existing_buy()
                    scenario.reload()
                    item, source = scenario.prepare()
                    before = scenario.path.read_bytes()
                    if change == "record_qty":
                        scenario.window._open_position_records[("BTCUSDT", "L")]["data"]["qty"] = 2
                    elif change == "annotation":
                        scenario.window._entry_allocations[("BTCUSDT", "L")][0]["interval_display"] = "Changed"
                    elif change == "snapshot":
                        source.snapshot["entry_allocations"]["BTCUSDT:L"][0]["qty"] = 2
                    elif change == "identity":
                        import os
                        os.utime(scenario.path, ns=(source.identity[2] + 1000000, source.identity[2] + 1000000))
                    else:
                        source = None
                    with self.assertRaises(LiveTradingSafetyError):
                        scenario.recover(item, source)
                    self.assertEqual(before, scenario.path.read_bytes())
                    self.assertEqual(1, scenario.wrapper.get_order_intent_status()["unresolved_count"])
                    self.assertEqual(1, len(scenario.actual.market_posts))
                finally:
                    scenario.doCleanups()

    def test_client_or_owner_revocation_race_in_handoff_blocks_publication(self):
        for change in ("client", "revoked"):
            with self.subTest(change=change):
                scenario = type(self)()
                scenario.setUp()
                try:
                    item, source = scenario.prepare()
                    @contextmanager
                    def changed_handoff():
                        if change == "client":
                            scenario.wrapper.client = object()
                        else:
                            scenario.wrapper._revoke_spot_execution_owner()
                        yield
                    with self.assertRaisesRegex(LiveTradingSafetyError, "context changed"):
                        scenario.recover(item, source, handoff=changed_handoff)
                    self.assertEqual(scenario.initial_bytes, scenario.path.read_bytes())
                    self.assertEqual(1, len(scenario.actual.market_posts))
                finally:
                    scenario.doCleanups()

    def test_crash_after_exact_marker_does_not_require_old_origin_or_restore_inventory(self):
        item, source = self.prepare()
        result = self.recover(item, source)
        self.assertTrue(result["portfolio_reconciled"])
        before = self.path.read_bytes()
        self.actual.wrapper = self.actual.fixture.wrapper()
        self.wrapper = self.actual.wrapper
        self.window = self.actual._load_window()
        discovery = recovery.discover_spot_desktop_buy_recoveries(self.wrapper, allocation_path=self.path)
        self.assertEqual(0, discovery.unresolved_count)
        self.assertEqual((), discovery.items)
        self.assertEqual(before, self.path.read_bytes())
        self.assertAlmostEqual(0.09996, self.window._entry_allocations[("BTCUSDT", "L")][0]["qty"])
        self.assertFalse(getattr(self.wrapper, "_desktop_spot_entry_origins", None))
        self.assertEqual("recovery_required", json.loads(owner_marker_path(self.intent_path).read_text())["state"])
        self.assertEqual(1, len(self.actual.market_posts))

    def test_conflicting_existing_primary_or_consumption_proof_cannot_be_rewritten(self):
        for change in ("primary_trade", "consumption"):
            with self.subTest(change=change):
                scenario = type(self)()
                scenario.setUp()
                try:
                    scenario.publish_existing_buy()
                    if change == "consumption":
                        scenario.actual._sell("0.04")
                    payload = json.loads(scenario.path.read_text())
                    row = payload["entry_allocations"]["BTCUSDT:L"][0]
                    if change == "primary_trade":
                        row["spot_fill_recovery"]["trade_ids"][0] += 1
                    else:
                        row["spot_sell_recoveries"][0]["consumed_qty"] = "0.03"
                    write_ledger(scenario.path, payload)
                    scenario.reload(expect_accepted=False)
                    before = scenario.path.read_bytes()
                    with self.assertRaises(LiveTradingSafetyError):
                        scenario.recover()
                    self.assertEqual(before, scenario.path.read_bytes())
                    self.assertEqual(1, scenario.wrapper.get_order_intent_status()["unresolved_count"])
                    self.assertEqual(1, len(scenario.actual.market_posts))
                finally:
                    scenario.doCleanups()

    def test_same_record_store_replacement_before_marker_cannot_confirm_new_store(self):
        item, source = self.prepare()
        original_marker = recovery._mark_exact_acquisition
        def replaced_store(*args, **kwargs):
            with ledger_transaction(self.intent_path):
                ledger = intents._read_ledger(self.intent_path)
                ledger["store_id"] = str(uuid4())
                write_ledger(self.intent_path, ledger)
            return original_marker(*args, **kwargs)
        with patch.object(recovery, "_mark_exact_acquisition", side_effect=replaced_store):
            result = self.recover(item, source)
        self.assertTrue(result["allocation_published"])
        self.assertFalse(result["portfolio_reconciled"])
        self.assertIn("store or work item changed", result["error"])
        self.assertIsNot(self.wrapper._get_order_intent_record(self.client_id).get("portfolio_reconciled"), True)
        self.assertFalse(source.session.ready)
        self.assertEqual(1, len(self.actual.market_posts))

    def test_second_missing_acquisition_rechecks_original_baseline_after_first_publication(self):
        second_client = "restart-second-buy"
        order = deepcopy(self.actual.fixture.venue.orders[self.client_id])
        order.update(clientOrderId=second_client, orderId=10002)
        order["fills"][0]["tradeId"] += 1
        second_fill = fills.summarize_primary_spot_buy(order, symbol="BTCUSDT", client_order_id=second_client,
                                                      base_asset="BTC", quote_asset="USDT")
        with ledger_transaction(self.intent_path):
            ledger = intents._read_ledger(self.intent_path)
            second = deepcopy(ledger["intents"][self.client_id])
            second.update(client_order_id=second_client, exchange_order_id="10002",
                          primary_fill_signature=second_fill["signature"],
                          primary_fill_receipt=recovery.canonical_spot_buy_metadata(second_fill))
            second["desktop_entry_source"]["client_order_ids"] = [second_client]
            ledger["intents"][second_client] = second
            write_ledger(self.intent_path, ledger)
        discovery = recovery.discover_spot_desktop_buy_recoveries(self.wrapper, allocation_path=self.path)
        self.assertEqual(2, len(discovery.items))
        first, source = self.prepare_without_count()
        self.assertTrue(self.recover(first, source)["portfolio_reconciled"])
        self.reload()
        second, source = self.prepare()
        self.assertEqual(second_client, second.client_order_id)
        before = self.path.read_bytes()
        with self.assertRaisesRegex(LiveTradingSafetyError, "original source baseline"):
            self.recover(second, source)
        self.assertEqual(before, self.path.read_bytes())
        self.assertEqual(1, self.wrapper.get_order_intent_status()["unresolved_count"])
        self.assertEqual(1, len(self.actual.market_posts))

    def prepare_without_count(self):
        discovery = recovery.discover_spot_desktop_buy_recoveries(self.wrapper, allocation_path=self.path)
        item = next(item for item in discovery.items if item.client_order_id == self.client_id)
        source = recovery.capture_spot_desktop_buy_recovery_source(
            self.window._allocation_snapshot_session, self.window._entry_allocations,
            self.window._open_position_records, allocation_path=self.path,
        )
        return item, source

    def test_current_target_coherence_faults_never_confirm_historical_acquisition(self):
        changes = [("data", field, value) for field, value in (
            ("qty", 0.5), ("entry_price", 30000), ("margin_usdt", 9999), ("size_usdt", 9999),
            ("symbol", "ETHUSDT"), ("side_key", "S"), ("status", "Closed"), ("entry_price", None),
        )] + [("record", field, value) for field, value in (
            ("symbol", "ETHUSDT"), ("side_key", "S"), ("status", "Closed"), ("status", None),
            ("allocations", []),
        )]
        for layer, field, value in changes:
            with self.subTest(layer=layer, field=field, value=value):
                scenario = type(self)()
                scenario.setUp()
                try:
                    scenario.publish_existing_buy()
                    scenario.actual._sell("0.04")
                    payload = json.loads(scenario.path.read_text())
                    record = payload["open_position_records"]["BTCUSDT:L"]
                    target = record["data"] if layer == "data" else record
                    if value is None:
                        target.pop(field)
                    else:
                        target[field] = value
                    write_ledger(scenario.path, payload)
                    scenario.reload(expect_accepted=False)
                    before = scenario.path.read_bytes()
                    with self.assertRaises(LiveTradingSafetyError):
                        scenario.recover()
                    self.assertEqual(before, scenario.path.read_bytes())
                    self.assertEqual(1, scenario.wrapper.get_order_intent_status()["unresolved_count"])
                    self.assertEqual(1, len(scenario.actual.market_posts))
                finally:
                    scenario.doCleanups()

    def test_position_financial_drift_after_publication_blocks_final_marker(self):
        item, source = self.prepare()
        original_marker = recovery._mark_exact_acquisition
        def changed_position(*args, **kwargs):
            with ledger_transaction(self.path):
                payload = json.loads(self.path.read_text())
                payload["open_position_records"]["BTCUSDT:L"]["data"]["entry_price"] = 30000
                write_ledger(self.path, payload)
            return original_marker(*args, **kwargs)
        with patch.object(recovery, "_mark_exact_acquisition", side_effect=changed_position):
            result = self.recover(item, source)
        self.assertTrue(result["allocation_published"])
        self.assertFalse(result["portfolio_reconciled"])
        self.assertIn("protected inventory", result["error"].lower())
        self.assertEqual(1, self.wrapper.get_order_intent_status()["unresolved_count"])
        self.assertFalse(source.session.ready)
        self.assertEqual(1, len(self.actual.market_posts))

    def test_current_projection_validation_preserves_original_strategy_annotations(self):
        self.publish_existing_buy()
        self.actual._sell("0.04")
        payload = json.loads(self.path.read_text())
        row = payload["entry_allocations"]["BTCUSDT:L"][0]
        row.update(interval="5m", interval_display="Strategy timeframe", trigger_desc="Original strategy context")
        record = payload["open_position_records"]["BTCUSDT:L"]
        record["allocations"] = [deepcopy(row)]
        record["data"].update(interval="5m", interval_display="Strategy timeframe")
        record["entry_tf"] = "Original timeframe"
        write_ledger(self.path, payload)
        # Explicitly authored historical strategy annotations precede the initial
        # checkpoint in this isolated synthetic world; no product re-sealing.
        from spot_inventory_checkpoint_fixtures import CheckpointFixtureBackend
        historical = self.enterContext(CheckpointFixtureBackend(simulate_windows=True))
        historical.author_snapshot(self.path, namespace=self.namespace)
        self.reload()
        before = self.path.read_bytes()
        self.assertTrue(self.recover()["portfolio_reconciled"])
        self.assertEqual(before, self.path.read_bytes())

    def test_unknown_primary_receipts_remain_unsupported_without_normalizing_a_prior_marker(self):
        for already_marked in (False, True):
            with self.subTest(already_marked=already_marked):
                scenario = type(self)()
                scenario.setUp()
                try:
                    if already_marked:
                        self.assertTrue(scenario.recover()["portfolio_reconciled"])
                        scenario.reload()
                    current = scenario.wrapper._get_order_intent_record(scenario.client_id)
                    intents._update_order_intent_by_id(scenario.wrapper, scenario.client_id,
                                                      state="unknown", expected_record=current)
                    before_intent = scenario.intent_path.read_bytes()
                    before_allocations = scenario.path.read_bytes() if scenario.path.exists() else None
                    discovery = recovery.discover_spot_desktop_buy_recoveries(
                        scenario.wrapper, allocation_path=scenario.path,
                    )
                    self.assertEqual(1, discovery.unresolved_count)
                    self.assertEqual(1, discovery.unsupported_count)
                    self.assertEqual((), discovery.items)
                    current = scenario.wrapper._get_order_intent_record(scenario.client_id)
                    item = recovery.SpotDesktopBuyRecoveryWorkItem(
                        discovery.authority, scenario.client_id, "BTCUSDT", int(current["exchange_order_id"]),
                        "FILLED", current, recovery._signature(current),
                    )
                    source = recovery.capture_spot_desktop_buy_recovery_source(
                        scenario.window._allocation_snapshot_session, scenario.window._entry_allocations,
                        scenario.window._open_position_records, allocation_path=scenario.path,
                    )
                    with self.assertRaisesRegex(LiveTradingSafetyError, "unmarked accepted terminal primary"):
                        scenario.recover(item, source)
                    self.assertEqual(before_intent, scenario.intent_path.read_bytes())
                    self.assertEqual(before_allocations, scenario.path.read_bytes() if scenario.path.exists() else None)
                    self.assertEqual("unknown", scenario.wrapper._get_order_intent_record(scenario.client_id)["state"])
                    self.assertEqual(1, scenario.wrapper.get_order_intent_status()["unresolved_count"])
                    self.assertEqual(1, len(scenario.actual.market_posts))
                finally:
                    scenario.doCleanups()

    def test_nonprimary_unresolved_work_is_reported_but_not_accepted_as_recoverable(self):
        with ledger_transaction(self.intent_path):
            ledger = intents._read_ledger(self.intent_path)
            record = ledger["intents"][self.client_id]
            for field in ("primary_fill_receipt", "primary_fill_signature", "portfolio_qty"):
                record.pop(field)
            write_ledger(self.intent_path, ledger)
        discovery = recovery.discover_spot_desktop_buy_recoveries(self.wrapper, allocation_path=self.path)
        self.assertEqual(1, discovery.unresolved_count)
        self.assertEqual(1, discovery.unsupported_count)
        self.assertEqual((), discovery.items)
        self.assertEqual(self.initial_bytes, self.path.read_bytes())
        self.assertIsNot(self.wrapper._get_order_intent_record(self.client_id).get("portfolio_reconciled"), True)
        self.assertEqual(1, len(self.actual.market_posts))
