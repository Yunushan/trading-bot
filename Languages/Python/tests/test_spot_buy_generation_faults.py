"""Offline acquisition generations through the real Spot wrapper and publisher."""
from __future__ import annotations

import copy
from contextlib import contextmanager
from dataclasses import replace
import json
import os
from decimal import Decimal
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch
from uuid import uuid4

import test_spot_opo_fault_integration as opo_fixture
from test_open_trade_signal_behavior import _OpenSignalWindowStub, _dispatch

from app.core.strategy.orders.strategy_signal_order_result_runtime import _emit_signal_order_info
from app.gui.shared import allocation_persistence as publication
from app.gui.shared.allocation_reconciliation import allocation_publication_pending
from app.gui.runtime.account import account_runtime
from app.gui.trade import signal_common_runtime
from app.integrations.exchanges.binance.orders import order_intent_runtime as ledger
from app.integrations.exchanges.binance.orders import spot_fill_recovery_runtime as recovery
from app.integrations.exchanges.binance.orders import spot_buy_publication_runtime as buy_publication
from app.integrations.exchanges.binance.orders.order_intent_store import ledger_transaction, write_ledger
from app.settings.live_safety import LiveTradingSafetyError


class SpotBuyGenerationFaultsTests(unittest.TestCase):
    def setUp(self):
        self.fixture = opo_fixture.SpotOpoFaultIntegrationTests()
        self.fixture.setUp()
        self.addCleanup(self.fixture.doCleanups)
        self.enterContext(patch.object(
            publication, "_get_allocations_file_path", return_value=self.fixture.allocation_path,
        ))
        self.wrapper = self.fixture.wrapper()
        self.market_posts = []
        self.base_fee = Decimal(0)
        self.venue_price = Decimal("20000")
        self.fixture.venue.create_order = self._create_order

    def _create_order(self, **params):
        self.market_posts.append(copy.deepcopy(params))
        order_id = 10000 + len(self.market_posts)
        qty = Decimal(params["quantity"])
        response = {
            "clientOrderId": params["newClientOrderId"], "symbol": "BTCUSDT", "side": params["side"],
            "type": "MARKET", "orderId": order_id, "status": "FILLED", "origQty": str(qty),
            "executedQty": str(qty), "cummulativeQuoteQty": str(qty * self.venue_price),
            "updateTime": 1780000000000 + len(self.market_posts),
            "fills": [{"tradeId": order_id + 20000, "price": str(self.venue_price), "qty": str(qty),
                       "commission": str(self.base_fee), "commissionAsset": "BTC"}],
        }
        self.fixture.venue.orders[response["clientOrderId"]] = copy.deepcopy(response)
        return response

    def _buy(self, *, base_fee="0", price="20000"):
        self.base_fee = Decimal(base_fee)
        self.venue_price = Decimal(price)
        capture_origin = getattr(self.wrapper, "_desktop_trade_origin_capture", None)
        callback_origin = capture_origin() if callable(capture_origin) else None
        result = self.wrapper.place_spot_market_order("BTCUSDT", "BUY", quantity=0.1, price=float(self.venue_price))
        self.assertTrue(result["ok"], result)
        response = result["info"]
        events = []
        strategy = SimpleNamespace(binance=self.wrapper, trade_cb=events.append, log=lambda _message: None)
        _emit_signal_order_info(
            strategy, cw={"symbol": "BTCUSDT", "interval": "1m"}, side="BUY", order_res=result,
            price=float(self.venue_price), qty_display=0.1, trigger_labels=[], trigger_desc_for_order=None,
            trigger_signature=[], context_key=None, order_event_uid=f"buy-event-{response['orderId']}",
            trigger_actions_for_order={}, origin_timestamp=None, leverage_used=1,
            callback_wrapper=self.wrapper, callback_origin=callback_origin,
        )
        self.assertEqual(1, len(events))
        event = events[0]
        if callback_origin is not None:
            self.assertFalse(event["reconciliation_required"])
        self.assertTrue(event["execution_confirmed"])
        fill = recovery.summarize_primary_spot_buy(
            response, symbol="BTCUSDT", client_order_id=response["clientOrderId"],
            base_asset="BTC", quote_asset="USDT",
        )
        self.assertEqual(fill["signature"], event["spot_fill_recovery"]["signature"])
        return event, fill

    def _persist_buy(self, fill):
        self.assertTrue(recovery.persist_spot_buy_allocation(self.fixture.allocation_path, fill))
        marker = self.wrapper._mark_order_intent_portfolio_reconciled(
            fill["client_order_id"], portfolio_signature=fill["signature"], portfolio_quantity=fill["net_qty"],
        )
        self.assertTrue(marker["portfolio_reconciled"])

    def _sell(self, consumed, *, base_fee="0"):
        consumed = Decimal(consumed)
        base_fee = Decimal(base_fee)
        gross = consumed - base_fee
        baseline = recovery.spot_live_allocation_baseline(self.fixture.allocation_path, symbol="BTCUSDT")
        self.assertIsNotNone(baseline)
        intent = {"market": "spot", "type": "MARKET", "side": "SELL", "symbol": "BTCUSDT",
                  "client_order_id": "sell-generation-one", "exchange_order_id": "11000"}
        order = {"clientOrderId": intent["client_order_id"], "symbol": "BTCUSDT", "side": "SELL",
                 "type": "MARKET", "orderId": 11000, "status": "FILLED", "origQty": str(gross),
                 "executedQty": str(gross), "cummulativeQuoteQty": str(gross * Decimal("20000")),
                 "updateTime": 1780000001000}
        trades = [{"symbol": "BTCUSDT", "id": 31000, "orderId": 11000, "price": "20000", "qty": str(gross),
                   "quoteQty": str(gross * Decimal("20000")), "commission": str(base_fee), "commissionAsset": "BTC",
                   "time": 1780000001000, "isBuyer": False}]
        fill = recovery.summarize_spot_market_fill(intent, order, trades, base_asset="BTC", quote_asset="USDT")
        self.assertEqual(consumed, Decimal(fill["portfolio_qty"]))
        fill.update(pre_order_portfolio_signature=baseline["signature"], pre_order_portfolio_qty=baseline["quantity"])
        self.assertTrue(recovery.persist_spot_sell_allocation(self.fixture.allocation_path, fill))
        return fill

    def _load_window(self):
        window = _OpenSignalWindowStub()
        window.mode_combo = SimpleNamespace(currentText=lambda: "Live")
        window.shared_binance = self.wrapper
        window.config = {}
        window.log = lambda _message: None
        window._allocation_snapshot_session = publication.AllocationSnapshotSession()
        window._entry_allocations, window._open_position_records = publication.load_position_allocations(
            this_file=self.fixture.home / "unused.py", mode="Live", session=window._allocation_snapshot_session,
        )
        self.assertTrue(window._allocation_snapshot_session.ready)
        with patch.object(account_runtime, "BinanceWrapper", return_value=self.wrapper):
            self.assertIs(self.wrapper, account_runtime._create_binance_wrapper(
                window, api_key="offline-key", api_secret="offline-secret", mode="Live", account_type="Spot",
                connector_backend="binance-sdk-spot",
            ))
        self.assertFalse(allocation_publication_pending(window))
        return window

    def _dispatch(self, window, event, *, saver=None):
        def actual_saver(allocations, records, **kwargs):
            return publication.save_position_allocations(
                allocations, records, this_file=self.fixture.home / "unused.py", **kwargs,
            )
        _dispatch(
            window, event, persist_trade_allocations=signal_common_runtime._persist_trade_allocations,
            sync_open_position_snapshot=signal_common_runtime._sync_open_position_snapshot,
            saver=saver or actual_saver,
        )

    def _payload(self):
        return json.loads(self.fixture.allocation_path.read_text(encoding="utf-8"))

    def test_exact_buy_writer_replay_preserves_partial_and_closed_inventory(self):
        for consumed in ("0.04", "0.1"):
            with self.subTest(consumed=consumed):
                # Each generation gets its own real wrapper owner and confined ledger.
                fixture = type(self)()
                fixture.setUp()
                try:
                    _event, buy = fixture._buy()
                    fixture._persist_buy(buy)
                    fixture._sell(consumed)
                    committed = fixture.fixture.allocation_path.read_bytes()
                    payload = fixture._payload()
                    self.assertTrue(recovery.persist_spot_buy_allocation(fixture.fixture.allocation_path, buy))
                    self.assertEqual(committed, fixture.fixture.allocation_path.read_bytes())
                    current = fixture.wrapper._get_order_intent_record(buy["client_order_id"])
                    self.assertTrue(ledger._has_durable_spot_buy_allocation(
                        current, portfolio_signature=buy["signature"], portfolio_quantity=buy["net_qty"],
                    ))
                    marker = fixture.wrapper._mark_order_intent_portfolio_reconciled(
                        buy["client_order_id"], portfolio_signature=buy["signature"], portfolio_quantity=buy["net_qty"],
                    )
                    self.assertTrue(marker["already_reconciled"])
                    self.assertEqual(committed, fixture.fixture.allocation_path.read_bytes())
                    self.assertEqual(payload, fixture._payload())
                    self.assertEqual(1, len(fixture.market_posts))
                finally:
                    fixture.doCleanups()

    def test_new_owned_entry_preserves_closed_proof_and_old_buy_replay_after_reload(self):
        _first_event, first = self._buy(base_fee="0.00004")
        self._persist_buy(first)
        self._sell("0.09996", base_fee="0.00006")
        old_row = copy.deepcopy(self._payload()["entry_allocations"]["BTCUSDT:L"][0])
        self.assertEqual("Closed", old_row["status"])
        _second_event, second = self._buy(price="30000")
        self._persist_buy(second)
        committed = self.fixture.allocation_path.read_bytes()
        payload = self._payload()
        rows = payload["entry_allocations"]["BTCUSDT:L"]
        self.assertEqual(old_row, rows[0])
        self.assertEqual(["Closed", "Active"], [row["status"] for row in rows])
        record = payload["open_position_records"]["BTCUSDT:L"]
        self.assertEqual([rows[1]], record["allocations"])
        self.assertEqual(0.1, record["data"]["qty"])
        self.assertEqual(30000.0, record["data"]["entry_price"])
        reloaded = self._load_window()
        loaded = copy.deepcopy((reloaded._entry_allocations, reloaded._open_position_records))
        self.assertTrue(recovery.persist_spot_buy_allocation(self.fixture.allocation_path, first))
        self.assertEqual(committed, self.fixture.allocation_path.read_bytes())
        self.assertEqual(loaded, (reloaded._entry_allocations, reloaded._open_position_records))
        self.assertEqual(2, len(self.market_posts))

    def test_new_gui_entry_commits_canonical_generation_and_old_replay_is_harmless(self):
        first_event, first = self._buy()
        self._persist_buy(first)
        self._sell("0.1")
        old_row = copy.deepcopy(self._payload()["entry_allocations"]["BTCUSDT:L"][0])
        window = self._load_window()
        second_event, second = self._buy(price="30000")
        self._dispatch(window, second_event)
        self.assertFalse(getattr(window, "_pending_trade_reconciliation", {}))
        intent = self.wrapper._get_order_intent_record(second["client_order_id"])
        self.assertTrue(intent["portfolio_reconciled"])
        committed = self.fixture.allocation_path.read_bytes()
        rows = self._payload()["entry_allocations"]["BTCUSDT:L"]
        self.assertEqual(old_row, rows[0])
        self.assertEqual(2, len(rows))
        self.assertEqual(second["signature"], rows[1]["spot_fill_recovery"]["signature"])
        self.assertEqual([rows[1]], self._payload()["open_position_records"]["BTCUSDT:L"]["allocations"])
        self.assertEqual(0.1, self._payload()["open_position_records"]["BTCUSDT:L"]["data"]["qty"])
        self.assertEqual(30000.0, self._payload()["open_position_records"]["BTCUSDT:L"]["data"]["entry_price"])
        reloaded = self._load_window()
        maps = copy.deepcopy((reloaded._entry_allocations, reloaded._open_position_records))
        self._dispatch(reloaded, second_event)
        self.assertFalse(getattr(reloaded, "_pending_trade_reconciliation", {}))
        self.assertFalse(allocation_publication_pending(reloaded))
        self.assertEqual(committed, self.fixture.allocation_path.read_bytes())
        self.assertEqual(maps, (reloaded._entry_allocations, reloaded._open_position_records))
        self._dispatch(reloaded, first_event)
        self.assertEqual(committed, self.fixture.allocation_path.read_bytes())
        self.assertEqual(maps, (reloaded._entry_allocations, reloaded._open_position_records))
        # A CLI event has no committed GUI receipt to authorize a read-only replay.
        self.assertTrue(reloaded._pending_trade_reconciliation)
        self.assertTrue(recovery.persist_spot_buy_allocation(self.fixture.allocation_path, first))
        self.assertEqual(committed, self.fixture.allocation_path.read_bytes())
        self.assertEqual(2, len(self.market_posts))

    def test_first_gui_fee_aware_entry_is_canonical_before_real_intent_marker(self):
        window = self._load_window()
        event, fill = self._buy(base_fee="0.00004")
        self.assertEqual("0.09996", fill["net_qty"])
        self._dispatch(window, event)
        self.assertFalse(getattr(window, "_pending_trade_reconciliation", {}))
        payload = self._payload()
        row = payload["entry_allocations"]["BTCUSDT:L"][0]
        self.assertEqual(0.09996, row["qty"])
        self.assertEqual("0.09996", row["spot_fill_recovery"]["net_qty"])
        self.assertEqual(fill["signature"], row["spot_fill_recovery"]["signature"])
        self.assertEqual(1, row["spot_fill_recovery"]["version"])
        self.assertEqual([row], payload["open_position_records"]["BTCUSDT:L"]["allocations"])
        self.assertEqual(0.09996, payload["open_position_records"]["BTCUSDT:L"]["data"]["qty"])
        self.assertEqual("0.09996", payload["gui_trade_event_receipts"][0]["quantity"])
        intent = self.wrapper._get_order_intent_record(fill["client_order_id"])
        self.assertTrue(intent["portfolio_reconciled"])
        self.assertEqual("0.09996", intent["portfolio_qty"])
        self.assertEqual(self.fixture.allocation_path.read_bytes(), window._allocation_snapshot_session._bytes)
        self.assertEqual(1, len(self.market_posts))

    def test_failed_new_generation_publication_preserves_confirmed_fill_and_closed_inventory(self):
        _first_event, first = self._buy()
        self._persist_buy(first)
        self._sell("0.1")
        window = self._load_window()
        old_maps = copy.deepcopy((window._entry_allocations, window._open_position_records))
        old_bytes = self.fixture.allocation_path.read_bytes()
        event, second = self._buy()
        with patch.object(publication, "_write_snapshot", side_effect=OSError("offline allocation disk failure")):
            self._dispatch(window, event)
        self.assertEqual(old_bytes, self.fixture.allocation_path.read_bytes())
        self.assertEqual(old_maps, (window._entry_allocations, window._open_position_records))
        self.assertFalse(window._allocation_snapshot_session.ready)
        intent = self.wrapper._get_order_intent_record(second["client_order_id"])
        self.assertIsNot(intent.get("portfolio_reconciled"), True)
        pending = list(window._pending_trade_reconciliation.values())
        self.assertEqual(1, len(pending))
        self.assertEqual(event, pending[0]["order_info"])
        self.assertEqual(2, len(self.market_posts))
        before_status = self.wrapper.get_order_intent_status()
        before_attempts = self.wrapper._live_order_submit_attempt_count
        blocked = self.wrapper.place_spot_market_order("BTCUSDT", "BUY", quantity=0.1, price=20000)
        self.assertFalse(blocked["ok"])
        self.assertEqual(2, len(self.market_posts))
        self.assertEqual(before_status["intent_count"], self.wrapper.get_order_intent_status()["intent_count"])
        self.assertEqual(before_attempts, self.wrapper._live_order_submit_attempt_count)

    def test_changed_account_or_mode_rejects_original_accepted_generation_callback(self):
        for mutation in ("wrapper", "mode"):
            with self.subTest(mutation=mutation):
                fixture = type(self)()
                fixture.setUp()
                try:
                    _first_event, first = fixture._buy()
                    fixture._persist_buy(first)
                    fixture._sell("0.1")
                    window = fixture._load_window()
                    event, second = fixture._buy()
                    old_bytes = fixture.fixture.allocation_path.read_bytes()
                    old_maps = copy.deepcopy((window._entry_allocations, window._open_position_records))
                    replacement_marker = Mock()
                    if mutation == "wrapper":
                        window.shared_binance = SimpleNamespace(_mark_order_intent_portfolio_reconciled=replacement_marker)
                    else:
                        window.mode_combo = SimpleNamespace(currentText=lambda: "Demo/Testnet")
                    fixture._dispatch(window, event)
                    self.assertEqual(old_bytes, fixture.fixture.allocation_path.read_bytes())
                    self.assertEqual(old_maps, (window._entry_allocations, window._open_position_records))
                    self.assertTrue(window._pending_trade_reconciliation)
                    replacement_marker.assert_not_called()
                    self.assertIsNot(fixture.wrapper._get_order_intent_record(second["client_order_id"]).get("portfolio_reconciled"), True)
                    self.assertEqual(2, len(fixture.market_posts))
                finally:
                    fixture.doCleanups()

    def test_changed_acquisition_amounts_cannot_reuse_accepted_fill_signature(self):
        for mutation in ("net_quantity", "quote_cost", "quote_fee"):
            with self.subTest(mutation=mutation):
                fixture = type(self)()
                fixture.setUp()
                try:
                    window = fixture._load_window()
                    event, fill = fixture._buy()
                    changed = copy.deepcopy(fill)
                    if mutation == "net_quantity":
                        changed.update(net_qty="0.09", commissions=[{"asset": "BTC", "amount": "0.01"}],
                                       average_cost=str(Decimal("2000") / Decimal("0.09")))
                    elif mutation == "quote_cost":
                        changed.update(gross_quote_qty="3000", net_quote_cost="3000", average_cost="30000")
                    else:
                        changed.update(net_quote_cost="2001", average_cost="20010",
                                       commissions=[{"asset": "USDT", "amount": "1"}])
                    self.assertEqual(fill["signature"], changed["signature"])
                    event.update(qty=float(changed["net_qty"]), executed_qty=float(changed["net_qty"]),
                                 avg_price=float(changed["average_cost"]), spot_fill_recovery=changed)
                    event["_spot_buy_publication"] = replace(event["_spot_buy_publication"], fill=changed)
                    fixture._dispatch(window, event)
                    self.assertFalse(fixture.fixture.allocation_path.exists())
                    self.assertEqual({}, window._entry_allocations)
                    self.assertEqual({}, window._open_position_records)
                    self.assertTrue(window._pending_trade_reconciliation)
                    self.assertIsNot(fixture.wrapper._get_order_intent_record(fill["client_order_id"]).get("portfolio_reconciled"), True)
                    self.assertEqual(1, len(fixture.market_posts))
                finally:
                    fixture.doCleanups()

    def test_account_switch_after_publication_cannot_mark_replacement_account(self):
        window = self._load_window()
        event, fill = self._buy()
        replacement_marker = Mock(return_value={"portfolio_reconciled": True})

        def switch_after_durable_save(allocations, records, **kwargs):
            published = publication.save_position_allocations(
                allocations, records, this_file=self.fixture.home / "unused.py", **kwargs,
            )
            self.assertTrue(published)
            window.shared_binance = SimpleNamespace(_mark_order_intent_portfolio_reconciled=replacement_marker)
            return published

        self._dispatch(window, event, saver=switch_after_durable_save)
        replacement_marker.assert_not_called()
        self.assertEqual(0.1, self._payload()["open_position_records"]["BTCUSDT:L"]["data"]["qty"])
        # Durable proof may finish its original ledger; changed GUI ownership remains fenced.
        self.assertTrue(self.wrapper._get_order_intent_record(fill["client_order_id"])["portfolio_reconciled"])
        pending = list(window._pending_trade_reconciliation.values())
        self.assertEqual(1, len(pending))
        self.assertEqual(event, pending[0]["order_info"])
        self.assertEqual(1, len(self.market_posts))

    def test_actual_wrapper_blocks_changed_allocation_bytes_or_stat_before_post(self):
        for mutation in ("bytes", "identity"):
            with self.subTest(mutation=mutation):
                fixture = type(self)()
                fixture.setUp()
                try:
                    window = fixture._load_window()
                    self.assertTrue(publication.save_position_allocations(
                        {}, {}, this_file=fixture.fixture.home / "unused.py", mode="Live",
                        session=window._allocation_snapshot_session,
                    ))
                    original_submit = fixture.wrapper._mark_order_intent_submitted
                    prepared_ids = []

                    def change_before_submission(params, *, via):
                        prepared_ids.append(params["newClientOrderId"])
                        self.assertEqual("pending", fixture.wrapper._get_order_intent_record(prepared_ids[-1])["state"])
                        path = fixture.fixture.allocation_path
                        if mutation == "bytes":
                            path.write_bytes(path.read_bytes() + b"\n")
                        else:
                            stat = path.stat()
                            os.utime(path, ns=(stat.st_atime_ns, stat.st_mtime_ns + 1000000000))
                        return original_submit(params, via=via)

                    with patch.object(fixture.wrapper, "_mark_order_intent_submitted", side_effect=change_before_submission):
                        result = fixture.wrapper.place_spot_market_order("BTCUSDT", "BUY", quantity=0.1, price=20000)
                    self.assertFalse(result["ok"], result)
                    self.assertEqual(1, len(prepared_ids))
                    prepared = fixture.wrapper._get_order_intent_record(prepared_ids[0])
                    self.assertEqual("pending", prepared["state"])
                    self.assertTrue(ledger._is_unresolved(prepared))
                    self.assertEqual(1, fixture.wrapper.get_order_intent_status()["unresolved_count"])
                    self.assertEqual([], fixture.market_posts)
                finally:
                    fixture.doCleanups()

    def test_session_invalidation_after_outside_check_blocks_paired_submission_transaction(self):
        window = self._load_window()
        original_submit = self.wrapper._mark_order_intent_submitted
        original_check = self.wrapper._desktop_spot_entry_check
        original_transactions = buy_publication.ledger_transactions
        observed = {"outside_ok": False, "pairs": 0}
        prepared_ids = []

        def record_outside_check(origin, params):
            accepted = original_check(origin, params)
            observed["outside_ok"] |= accepted is True
            return accepted

        @contextmanager
        def invalidate_before_paired_lock(*paths):
            self.assertTrue(observed["outside_ok"])
            observed["pairs"] += 1
            window._allocation_snapshot_session.invalidate("offline invalidation before paired write")
            with original_transactions(*paths):
                yield

        def interrupt_submission(params, *, via):
            prepared_ids.append(params["newClientOrderId"])
            self.assertEqual("pending", self.wrapper._get_order_intent_record(prepared_ids[-1])["state"])
            with patch.object(self.wrapper, "_desktop_spot_entry_check", side_effect=record_outside_check), \
                    patch.object(buy_publication, "ledger_transactions", side_effect=invalidate_before_paired_lock):
                return original_submit(params, via=via)

        with patch.object(self.wrapper, "_mark_order_intent_submitted", side_effect=interrupt_submission):
            result = self.wrapper.place_spot_market_order("BTCUSDT", "BUY", quantity=0.1, price=20000)
        self.assertFalse(result["ok"], result)
        self.assertTrue(observed["outside_ok"])
        self.assertEqual(1, observed["pairs"])
        self.assertEqual(1, len(prepared_ids))
        prepared = self.wrapper._get_order_intent_record(prepared_ids[0])
        self.assertEqual("pending", prepared["state"])
        self.assertTrue(ledger._is_unresolved(prepared))
        self.assertEqual([], self.market_posts)
        self.assertFalse(self.fixture.allocation_path.exists())

    def test_actual_wrapper_blocks_replaced_execution_store_before_begin_or_submission(self):
        for phase in ("capture", "submitted"):
            with self.subTest(phase=phase):
                fixture = type(self)()
                fixture.setUp()
                try:
                    fixture._load_window()
                    old_store_id = fixture.wrapper._ensure_spot_execution_owner().store_id
                    path = ledger._intent_path(fixture.wrapper)
                    captured_intents = []

                    def replace_store():
                        with ledger_transaction(path):
                            payload = json.loads(path.read_text(encoding="utf-8"))
                            self.assertEqual(old_store_id, payload["store_id"])
                            captured_intents.append(copy.deepcopy(payload["intents"]))
                            payload["store_id"] = str(uuid4())
                            write_ledger(path, payload)

                    if phase == "capture":
                        original = fixture.wrapper._desktop_spot_entry_capture

                        def change_after_capture(params):
                            origin = original(params)
                            replace_store()
                            return origin

                        boundary = "_desktop_spot_entry_capture"
                        callback = change_after_capture
                    else:
                        original = fixture.wrapper._mark_order_intent_submitted

                        def change_before_submission(params, *, via):
                            self.assertEqual("pending", fixture.wrapper._get_order_intent_record(params["newClientOrderId"])["state"])
                            replace_store()
                            return original(params, via=via)

                        boundary = "_mark_order_intent_submitted"
                        callback = change_before_submission

                    with patch.object(fixture.wrapper, boundary, side_effect=callback):
                        result = fixture.wrapper.place_spot_market_order("BTCUSDT", "BUY", quantity=0.1, price=20000)
                    self.assertFalse(result["ok"], result)
                    self.assertEqual(1, len(captured_intents))
                    intents = json.loads(path.read_text(encoding="utf-8"))["intents"]
                    self.assertEqual(captured_intents[0], intents)
                    if phase == "capture":
                        self.assertEqual({}, intents)
                    else:
                        self.assertEqual(1, len(intents))
                        prepared = next(iter(intents.values()))
                        self.assertEqual("pending", prepared["state"])
                        self.assertTrue(ledger._is_unresolved(prepared))
                        self.assertIsNot(prepared.get("portfolio_reconciled"), True)
                    self.assertEqual([], fixture.market_posts)
                    self.assertFalse(fixture.fixture.allocation_path.exists())
                finally:
                    fixture.doCleanups()

    def test_actual_window_maps_must_match_loaded_source_before_capture_and_submission(self):
        for phase in ("capture", "submitted"):
            for mutation in ("extra_allocation", "extra_record", "allocation_quantity", "record_quantity"):
                with self.subTest(phase=phase, mutation=mutation):
                    fixture = type(self)()
                    fixture.setUp()
                    try:
                        window = fixture._load_window()
                        if mutation in {"allocation_quantity", "record_quantity"}:
                            row = {"symbol": "ETHUSDT", "side_key": "L", "qty": 0.2, "entry_price": 1000.0,
                                   "status": "Active", "trade_id": "legacy-eth", "interval": "5m",
                                   "margin_usdt": 200.0, "margin_balance": 200.0, "notional": 200.0}
                            window._entry_allocations[("ETHUSDT", "L")] = [row]
                            window._open_position_records[("ETHUSDT", "L")] = {
                                "data": {"qty": 0.2, "entry_price": 1000.0, "margin_usdt": 200.0, "size_usdt": 200.0},
                                "allocations": [copy.deepcopy(row)],
                            }
                            self.assertTrue(publication.save_position_allocations(
                                window._entry_allocations, window._open_position_records,
                                this_file=fixture.fixture.home / "unused.py", mode="Live",
                                session=window._allocation_snapshot_session,
                            ))
                            window = fixture._load_window()
                        source = fixture.fixture.allocation_path.read_bytes() if fixture.fixture.allocation_path.exists() else None
                        captured_intents = []

                        def change_window_maps():
                            if mutation == "extra_allocation":
                                window._entry_allocations[("ETHUSDT", "L")] = [{
                                    "symbol": "ETHUSDT", "side_key": "L", "qty": 0.2, "entry_price": 1000.0,
                                    "status": "Active", "trade_id": "stale-local-eth",
                                }]
                            elif mutation == "extra_record":
                                window._open_position_records[("ETHUSDT", "L")] = {"data": {"qty": 0.2}, "allocations": []}
                            elif mutation == "allocation_quantity":
                                window._entry_allocations[("ETHUSDT", "L")][0]["qty"] = 0.3
                            else:
                                window._open_position_records[("ETHUSDT", "L")]["data"]["qty"] = 0.3

                        if phase == "capture":
                            change_window_maps()
                            result = fixture.wrapper.place_spot_market_order("BTCUSDT", "BUY", quantity=0.1, price=20000)
                        else:
                            original_submit = fixture.wrapper._mark_order_intent_submitted

                            def change_before_submission(params, *, via):
                                path = ledger._intent_path(fixture.wrapper)
                                intents = json.loads(path.read_text(encoding="utf-8"))["intents"]
                                self.assertEqual("pending", intents[params["newClientOrderId"]]["state"])
                                captured_intents.append(copy.deepcopy(intents))
                                change_window_maps()
                                return original_submit(params, via=via)

                            with patch.object(fixture.wrapper, "_mark_order_intent_submitted", side_effect=change_before_submission):
                                result = fixture.wrapper.place_spot_market_order("BTCUSDT", "BUY", quantity=0.1, price=20000)
                        self.assertFalse(result["ok"], result)
                        self.assertEqual([], fixture.market_posts)
                        path = ledger._intent_path(fixture.wrapper)
                        intents = json.loads(path.read_text(encoding="utf-8"))["intents"]
                        if phase == "capture":
                            self.assertEqual([], captured_intents)
                            self.assertEqual({}, intents)
                        else:
                            self.assertEqual([intents], captured_intents)
                            prepared = next(iter(intents.values()))
                            self.assertEqual("pending", prepared["state"])
                            self.assertTrue(ledger._is_unresolved(prepared))
                        observed = fixture.fixture.allocation_path.read_bytes() if fixture.fixture.allocation_path.exists() else None
                        self.assertEqual(source, observed)
                    finally:
                        fixture.doCleanups()

    def test_unsupported_desktop_opo_is_rejected_before_intent_and_post(self):
        self._load_window()
        result = self.fixture.entry(self.wrapper, "desktop")
        self.assertFalse(result["ok"], result)
        self.assertEqual([], self.fixture.venue.posts)
        self.assertEqual(0, self.wrapper.get_order_intent_status()["intent_count"])
        self.assertEqual([], self.market_posts)

    def test_generic_exact_opo_recovery_remains_supported_without_desktop_origin(self):
        result = self.fixture.entry(self.wrapper, "operator")
        self.assertTrue(result["ok"], result)
        self.assertEqual(1, len(self.fixture.venue.posts))
        self.fixture.recover_buy(self.wrapper, "operator")
        record = self.wrapper._get_order_intent_record("list-operator")
        self.assertTrue(record["entry_reconciled"])
        self.assertEqual(0, self.wrapper.get_order_intent_status()["unresolved_count"])

    def test_original_marker_rejects_changed_cost_reusing_original_fill_signature(self):
        for previously_marked in (False, True):
            with self.subTest(previously_marked=previously_marked):
                fixture = type(self)()
                fixture.setUp()
                try:
                    _event, fill = fixture._buy()
                    self.assertTrue(recovery.persist_spot_buy_allocation(fixture.fixture.allocation_path, fill))
                    if previously_marked:
                        fixture.wrapper._mark_order_intent_portfolio_reconciled(
                            fill["client_order_id"], portfolio_signature=fill["signature"], portfolio_quantity=fill["net_qty"],
                        )
                    payload = fixture._payload()
                    row = payload["entry_allocations"]["BTCUSDT:L"][0]
                    row["spot_fill_recovery"].update(gross_quote_qty="3000", net_quote_cost="3000")
                    row.update(entry_price=30000.0, margin_usdt=3000.0, margin_balance=3000.0, notional=3000.0)
                    record = payload["open_position_records"]["BTCUSDT:L"]
                    record["allocations"] = [copy.deepcopy(row)]
                    record["data"].update(entry_price=30000.0, margin_usdt=3000.0, size_usdt=3000.0)
                    path = fixture.fixture.allocation_path
                    path.write_text(json.dumps(payload), encoding="utf-8")
                    committed = path.read_bytes()
                    with self.assertRaises(LiveTradingSafetyError):
                        fixture.wrapper._mark_order_intent_portfolio_reconciled(
                            fill["client_order_id"], portfolio_signature=fill["signature"], portfolio_quantity=fill["net_qty"],
                        )
                    self.assertEqual(committed, path.read_bytes())
                    self.assertEqual(1, len(fixture.market_posts))
                finally:
                    fixture.doCleanups()

    def test_exact_opo_stop_close_retains_acquisition_receipt_across_next_operator_generation(self):
        self.assertTrue(self.fixture.entry(self.wrapper)["ok"])
        self.fixture.recover_buy(self.wrapper)
        first_intent = self.wrapper._get_order_intent_record("list-first")
        first_order = self.fixture.venue.get_order(symbol="BTCUSDT", origClientOrderId="buy-first")
        buy_trades = [{
            "symbol": "BTCUSDT", "orderId": first_order["orderId"], "id": first_order["orderId"] + 1000,
            "isBuyer": True, "price": "100", "qty": "0.1", "quoteQty": "10",
            "commission": "0", "commissionAsset": "BTC", "time": 1750000000000,
        }]
        first_fill = recovery.summarize_spot_opo_buy_fill(
            first_intent, first_order, buy_trades, base_asset="BTC", quote_asset="USDT",
        )
        stop = self.fixture.venue.orders["stop-first"]
        stop.update(status="FILLED", executedQty="0.1", cummulativeQuoteQty="10", updateTime=1750000001000)
        self.fixture.venue.lists["list-first"].update(listStatusType="ALL_DONE", listOrderStatus="ALL_DONE")
        self.assertEqual("triggered", self.wrapper.reconcile_spot_opo_intent("list-first", force=True)["protection_state"])
        observed = self.wrapper._get_order_intent_record("list-first")
        stop_trades = self.fixture.venue.get_my_trades(symbol="BTCUSDT", order_id=stop["orderId"])
        stop_fill = recovery.summarize_spot_opo_stop_sell_fill(
            observed, copy.deepcopy(stop), stop_trades, base_asset="BTC", quote_asset="USDT",
        )
        self.assertTrue(recovery.persist_spot_opo_stop_sell_allocation(self.fixture.allocation_path, stop_fill))
        self.wrapper._mark_spot_opo_exit_reconciled(
            "list-first", portfolio_signature=stop_fill["signature"], portfolio_quantity=stop_fill["portfolio_qty"],
        )
        closed_bytes = self.fixture.allocation_path.read_bytes()
        old_row = copy.deepcopy(self._payload()["entry_allocations"]["BTCUSDT:L"][0])
        self.assertEqual("Closed", old_row["status"])
        self.assertNotIn("BTCUSDT:L", self._payload()["open_position_records"])
        self.assertTrue(recovery.persist_spot_buy_allocation(self.fixture.allocation_path, first_fill))
        self.assertEqual(closed_bytes, self.fixture.allocation_path.read_bytes())
        marker = self.wrapper._mark_spot_opo_entry_reconciled(
            "list-first", portfolio_signature=first_fill["signature"], portfolio_quantity=first_fill["net_qty"],
        )
        self.assertTrue(marker["already_reconciled"])
        self.assertEqual(closed_bytes, self.fixture.allocation_path.read_bytes())
        with self.assertRaises(LiveTradingSafetyError):
            recovery.spot_opo_allocation_baseline(
                self.fixture.allocation_path, symbol="BTCUSDT", list_client_order_id="list-first", expected_quantity="0.1",
            )
        self.assertTrue(self.fixture.entry(self.wrapper, "second")["ok"])
        self.fixture.recover_buy(self.wrapper, "second")
        second_bytes = self.fixture.allocation_path.read_bytes()
        rows = self._payload()["entry_allocations"]["BTCUSDT:L"]
        self.assertEqual(old_row, rows[0])
        self.assertEqual(["Closed", "Active"], [row["status"] for row in rows])
        self.assertEqual([rows[1]], self._payload()["open_position_records"]["BTCUSDT:L"]["allocations"])
        self.assertTrue(recovery.persist_spot_buy_allocation(self.fixture.allocation_path, first_fill))
        self.assertTrue(self.wrapper._mark_spot_opo_entry_reconciled(
            "list-first", portfolio_signature=first_fill["signature"], portfolio_quantity=first_fill["net_qty"],
        )["already_reconciled"])
        self.assertEqual(second_bytes, self.fixture.allocation_path.read_bytes())
        self.assertEqual(0.1, self._payload()["open_position_records"]["BTCUSDT:L"]["data"]["qty"])
        self.assertEqual(2, len(self.fixture.venue.posts))
        self.assertEqual([], self.market_posts)


if __name__ == "__main__":
    unittest.main()
