from __future__ import annotations

import copy
import json
import socket
import tempfile
import unittest
from decimal import Decimal
from pathlib import Path
from unittest.mock import patch

import test_spot_fill_recovery_runtime as fixtures
import test_spot_inventory_namespace_integration as owner_fixtures
from spot_inventory_checkpoint_fixtures import checkpoint_backend_for_case
from app.gui.shared import allocation_persistence
from app.integrations.exchanges.binance.orders import order_intent_runtime as intents
from app.integrations.exchanges.binance.orders.spot_inventory_namespace_runtime import publish_owned_spot_fill
from uuid import uuid4
from app.integrations.exchanges.binance.orders import order_intent_store as storage
from app.integrations.exchanges.binance.orders import spot_fill_recovery_runtime as recovery
from app.integrations.exchanges.binance.orders.spot_inventory_namespace import (
    ACCOUNT_NAMESPACE_KEY,
    is_strictly_empty_live_snapshot,
    make_namespace,
    require_namespace,
    validate_namespace,
)
from app.settings.live_safety import LiveTradingSafetyError


STORE_A = "98e9bb6e-f91c-4a16-8005-935dd75d6a4e"
STORE_B = "f86a5511-0a27-4604-aaba-aa9a9e7e38d9"
UID_A = 820001
UID_B = 820002


def empty_snapshot():
    return {"version": 1, "mode": "Live", "entry_allocations": {}, "open_position_records": {}}


def buy_fill(*, client="recovered-buy-1", order_id=75, trade_offset=0):
    intent = {**fixtures.INTENT, "client_order_id": client, "exchange_order_id": str(order_id)}
    order = {**fixtures.ORDER, "clientOrderId": client, "orderId": order_id}
    trades = [{**item, "orderId": order_id, "id": item["id"] + trade_offset} for item in fixtures.TRADES]
    return recovery.summarize_spot_market_fill(intent, order, trades, base_asset="BTC", quote_asset="USDT")


class _OfflineNamespaceCase(unittest.TestCase):
    def setUp(self):
        # Tests use only local files and synthetic signed-account transports.
        self.socket_guard = patch.object(socket, "socket", side_effect=AssertionError("offline namespace test"))
        self.socket_guard.start()
        self.addCleanup(self.socket_guard.stop)
        self.namespace = make_namespace(UID_A, STORE_A)


class OfflineNamespaceTests(_OfflineNamespaceCase):
    def test_descriptor_exact_shape_types_and_canonical_store_id(self):
        self.assertEqual({
            "version": 1, "exchange": "binance", "market": "spot", "environment": "live",
            "account_uid": UID_A, "store_id": STORE_A,
        }, self.namespace)
        cases = [None, [], {}, {**self.namespace, "credential_fingerprint": "not-identity"}]
        cases += [{key: value for key, value in self.namespace.items() if key != missing} for missing in self.namespace]
        for field, values in {
            "version": [True, 1.0, "1", 0, 2],
            "exchange": [None, "Binance", "other"],
            "market": ["futures", "SPOT"],
            "environment": ["testnet", "Live"],
            "account_uid": [True, False, 0, -1, 1.0, "820001", None],
            "store_id": [None, 1, "", STORE_A.upper(), STORE_A.replace("-", ""), "{" + STORE_A + "}"],
        }.items():
            cases += [{**self.namespace, field: invalid} for invalid in values]
        for value in cases:
            with self.subTest(value=value), self.assertRaises(LiveTradingSafetyError):
                validate_namespace(value)
        # This is the ledger's canonical UUID contract, not a version/authentication claim.
        self.assertEqual("00000000-0000-0000-0000-000000000000", make_namespace(1, "00000000-0000-0000-0000-000000000000")["store_id"])
        for uid, store in [(True, STORE_A), (UID_A, STORE_A.upper())]:
            with self.subTest(uid=uid, store=store), self.assertRaises(LiveTradingSafetyError):
                make_namespace(uid, store)

    def test_returned_metadata_is_detached_and_never_changes_inputs(self):
        original = copy.deepcopy(self.namespace)
        checked = validate_namespace(self.namespace)
        snapshot = {**empty_snapshot(), ACCOUNT_NAMESPACE_KEY: checked}
        required = require_namespace(snapshot, self.namespace)
        self.assertIsNot(checked, self.namespace)
        self.assertIsNot(required, checked)
        self.assertIsNot(required, self.namespace)
        required["account_uid"] = UID_B
        self.assertEqual(original, checked)
        self.assertEqual(original, self.namespace)
        self.assertEqual(original, snapshot[ACCOUNT_NAMESPACE_KEY])

    def test_missing_namespace_needs_explicit_structurally_empty_allowance(self):
        for snapshot in [None, empty_snapshot(), {**empty_snapshot(), "timestamp": 1.5, "gui_trade_event_receipts": []}]:
            with self.subTest(snapshot=snapshot):
                self.assertTrue(is_strictly_empty_live_snapshot(snapshot))
                with self.assertRaises(LiveTradingSafetyError):
                    require_namespace(snapshot, self.namespace)
                self.assertEqual(self.namespace, require_namespace(snapshot, self.namespace, allow_empty=True))
                if snapshot is not None:
                    self.assertNotIn(ACCOUNT_NAMESPACE_KEY, snapshot)
        with self.assertRaises(LiveTradingSafetyError):
            require_namespace(None, self.namespace, allow_empty=1)

    def test_empty_predicate_rejects_unknown_history_and_invalid_headers(self):
        cases = [False, [], {}, {**empty_snapshot(), "version": True}, {**empty_snapshot(), "mode": "Paper"},
                 {**empty_snapshot(), "entry_allocations": []}, {**empty_snapshot(), "open_position_records": []},
                 {**empty_snapshot(), "entry_allocations": {"BTCUSDT:L": []}},
                 {**empty_snapshot(), "entry_allocations": {"BTCUSDT:L": [{"status": "Closed"}]}},
                 {**empty_snapshot(), "open_position_records": {"BTCUSDT:L": {}}},
                 {**empty_snapshot(), "gui_trade_event_receipts": ["prior-event"]},
                 {**empty_snapshot(), "gui_trade_event_receipts": {}}, {**empty_snapshot(), "opaque_history": []},
                 {**empty_snapshot(), ACCOUNT_NAMESPACE_KEY: None}]
        cases += [{**empty_snapshot(), "timestamp": value} for value in [True, None, "0", float("nan"), float("inf"), -float("inf"), 10 ** 1000]]
        for snapshot in cases:
            with self.subTest(snapshot=str(snapshot)[:180]):
                self.assertFalse(is_strictly_empty_live_snapshot(snapshot))
                with self.assertRaises(LiveTradingSafetyError):
                    require_namespace(snapshot, self.namespace, allow_empty=True)

    def test_bound_empty_or_nonempty_sources_cannot_be_relabelled(self):
        for observed in [make_namespace(UID_B, STORE_A), make_namespace(UID_A, STORE_B), None,
                         {**self.namespace, "environment": "testnet"}]:
            for entries in [{}, {"BTCUSDT:L": [{"status": "Closed"}]}]:
                snapshot = {**empty_snapshot(), "entry_allocations": entries, ACCOUNT_NAMESPACE_KEY: observed}
                before = copy.deepcopy(snapshot)
                with self.subTest(observed=observed, entries=entries), self.assertRaises(LiveTradingSafetyError):
                    require_namespace(snapshot, self.namespace, allow_empty=True)
                self.assertEqual(before, snapshot)
        same = {**empty_snapshot(), "entry_allocations": {"BTCUSDT:L": [{"status": "Closed"}]},
                "opaque_history": {"preserved": True}, ACCOUNT_NAMESPACE_KEY: self.namespace}
        # Scope checks do not claim to replace complete row/history validation.
        self.assertEqual(self.namespace, require_namespace(same, self.namespace))

    def test_metadata_contract_does_not_depend_on_credential_or_backend_revision(self):
        before = make_namespace(UID_A, STORE_A)
        after = make_namespace(UID_A, STORE_A)
        self.assertEqual(before, after)
        self.assertEqual({"version", "exchange", "market", "environment", "account_uid", "store_id"}, set(after))


class OfflineFillNamespaceTests(_OfflineNamespaceCase):
    def setUp(self):
        super().setUp()
        self.f = owner_fixtures.SpotInventoryNamespaceIntegrationTests("runTest")
        self.f.setUp()
        self.addCleanup(self.f.doCleanups)
        self.accounts_by_path = {}

    def prepare_owned(self, path):
        """Explicit real-owner bootstrap for this target before any financial record."""
        checkpoint_backend_for_case(self)
        self.f.path = path
        self.enterContext(patch.object(allocation_persistence, "get_position_allocations_path", return_value=path))
        self.enterContext(patch.object(allocation_persistence, "_get_allocations_file_path", return_value=path))
        account = self.f.account("pure-owned-" + str(uuid4()), UID_A, separate_home=True, accepted=False)
        self.f.bootstrap(account)
        self.accounts_by_path[path] = account
        self.namespace = account.namespace
        return account

    def author_record(self, path, record):
        account = self.accounts_by_path[path]
        record = copy.deepcopy(record)
        now = intents._now()
        record.setdefault("created_at", now)
        record.setdefault("updated_at", now)
        record.setdefault("source", "offline-namespace-owned-fixture")
        record.setdefault("quantity", record["request"]["workingQuantity"])
        record.setdefault("entry_reconciled", False)
        if record.get("cancel_state") == "confirmed":
            record.update(cancel_submitted_at=now, cancel_confirmed_at=now)
        if record.get("strategy_exit_state") is not None:
            request = record.get("strategy_exit_request") or {
                "symbol": record["symbol"], "side": "SELL", "type": "MARKET", "cancelReplaceMode": "STOP_ON_FAILURE",
                "cancelOrderId": record["pending_order_id"], "cancelOrigClientOrderId": record["request"]["pendingClientOrderId"],
                "cancelRestrictions": "ONLY_NEW", "quantity": record["entry_portfolio_quantity"],
                "newClientOrderId": "rejected-linked-sell", "newOrderRespType": "FULL",
            }
            record.update(strategy_exit_request=request, strategy_exit_client_order_id=request["newClientOrderId"],
                          strategy_exit_quantity=request["quantity"], strategy_exit_request_signature=intents._request_signature(request),
                          strategy_exit_started_at=now, strategy_exit_response_at=now,
                          strategy_exit_pre_order_quantity=request["quantity"],
                          strategy_exit_requires_exact_reconciliation=True,
                          strategy_exit_requires_stop_rearm=record["strategy_exit_state"] == "stop_cancelled")
            record.setdefault("strategy_exit_pre_order_signature", record.get("residual_stop_pre_order_signature"))
            record.setdefault("strategy_exit_cancel_confirmed", True)
            record.setdefault("strategy_exit_outcome", "exit_sell_accepted")
            if record["strategy_exit_state"] == "sell_accepted":
                record.update(strategy_exit_order_observed_at=now)
        if record.get("residual_stop_state") is not None:
            record.update(residual_rearm_quantity=record["residual_stop_pre_order_quantity"],
                          residual_rearm_signature=record["residual_stop_pre_order_signature"],
                          residual_stop_request_signature=intents._request_signature(record["residual_stop_request"]),
                          residual_stop_started_at=now, residual_stop_observed_at=now,
                          strategy_exit_fill_signature="d" * 64, strategy_exit_fill_quantity="0",
                          strategy_exit_fill_trade_ids=[], strategy_exit_fill_time_ms=1780000000000)
        intents.validate_order_intent_record(record["client_order_id"], record)
        with self.f.account_home(account), storage.ledger_transaction(account.path):
            ledger = intents._read_ledger(account.path, expected_binding=intents._intent_binding(account.wrapper))
            ledger["intents"][record["client_order_id"]] = record
            intents.validate_order_intent_ledger(ledger, expected_binding=intents._intent_binding(account.wrapper))
            storage.write_ledger(account.path, ledger)
        return self.f.ledger(account)["intents"][record["client_order_id"]]

    def publish(self, path, fill, *, record=None, operation=recovery.persist_spot_buy_allocation):
        account = self.accounts_by_path[path]
        if record is not None:
            current = self.f.ledger(account)["intents"].get(record["client_order_id"])
            if current != record:
                current = self.author_record(path, record)
        else:
            current = self.f.ledger(account)["intents"].get(fill["client_order_id"])
            if current is None:
                if fill.get("side", "BUY") == "BUY":
                    current = self.f.author_accepted(account, fill)
                else:
                    self.f.publish_sell(account, fill)
                    return True
        with self.f.account_home(account):
            return publish_owned_spot_fill(account.wrapper, path, fill, expected_record=current, operation=operation)

    def bind_test_fixture(self, path, namespace):
        # Author fixture metadata explicitly; this is not a product migration/bootstrap.
        snapshot = json.loads(path.read_text(encoding="utf-8"))
        snapshot[ACCOUNT_NAMESPACE_KEY] = namespace
        storage.write_ledger(path, snapshot)
        checkpoint_backend_for_case(self).author_snapshot(storage._logical_lock_path(path), namespace=namespace)
        return snapshot

    def test_bound_buy_replay_without_namespace_is_rejected_before_return(self):
        # Also runnable against the old producer: this guard failed on committed source.
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / "allocations.json"
            fill = buy_fill()
            recovery.persist_spot_buy_allocation(path, fill)
            snapshot = self.bind_test_fixture(path, self.namespace)
            before = path.read_bytes()
            with self.assertRaises(LiveTradingSafetyError):
                recovery.persist_spot_buy_allocation(path, fill)
            self.assertEqual(before, path.read_bytes())
            self.assertEqual(snapshot, json.loads(path.read_text(encoding="utf-8")))

    def test_bound_buy_append_without_namespace_is_rejected_before_write(self):
        # Distinct account-local IDs; the old producer silently appended to a bound file.
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / "allocations.json"
            recovery.persist_spot_buy_allocation(path, buy_fill())
            snapshot = self.bind_test_fixture(path, self.namespace)
            before = path.read_bytes()
            fill = buy_fill(client="second-exact-buy", order_id=76, trade_offset=1000)
            with self.assertRaises(LiveTradingSafetyError):
                recovery.persist_spot_buy_allocation(path, fill)
            self.assertEqual(before, path.read_bytes())
            self.assertEqual(snapshot, json.loads(path.read_text(encoding="utf-8")))

    def test_first_buy_publishes_namespace_and_exact_fill_in_one_atomic_replace(self):
        for preexisting in [False, True]:
            with self.subTest(preexisting=preexisting), tempfile.TemporaryDirectory() as temp:
                path = Path(temp) / "allocations.json"
                if preexisting:
                    storage.write_ledger(path, {**empty_snapshot(), "gui_trade_event_receipts": []})
                account = self.prepare_owned(path)
                self.f.author_accepted(account, buy_fill())
                original_publish = storage._publish
                published = []

                def capture(temp_path, target):
                    saved = json.loads(temp_path.read_text(encoding="utf-8"))
                    self.assertEqual(self.namespace, saved[ACCOUNT_NAMESPACE_KEY])
                    self.assertEqual(1, len(saved["entry_allocations"]["BTCUSDT:L"]))
                    self.assertEqual(buy_fill()["signature"], saved["entry_allocations"]["BTCUSDT:L"][0]["spot_fill_recovery"]["signature"])
                    published.append(saved)
                    return original_publish(temp_path, target)

                with patch.object(storage, "_publish", side_effect=capture):
                    self.assertTrue(self.publish(path, buy_fill()))
                self.assertEqual(1, len(published))
                self.assertEqual(published[0], json.loads(path.read_text(encoding="utf-8")))
                before = path.read_bytes()
                self.assertTrue(self.publish(path, buy_fill()))
                self.assertEqual(before, path.read_bytes())

    def test_failed_first_publication_leaves_no_partial_namespace_or_acquisition(self):
        for preexisting in [False, True]:
            with self.subTest(preexisting=preexisting), tempfile.TemporaryDirectory() as temp:
                path = Path(temp) / "allocations.json"
                if preexisting:
                    storage.write_ledger(path, empty_snapshot())
                account = self.prepare_owned(path)
                self.f.author_accepted(account, buy_fill())
                before = path.read_bytes()
                calls = []

                def fail(temp_path, target):
                    value = json.loads(temp_path.read_text(encoding="utf-8"))
                    self.assertEqual(self.namespace, value[ACCOUNT_NAMESPACE_KEY])
                    self.assertEqual(1, len(value["entry_allocations"]["BTCUSDT:L"]))
                    calls.append(value)
                    raise OSError("controlled pre-rename failure")

                with patch.object(storage, "_publish", side_effect=fail), self.assertRaises(LiveTradingSafetyError):
                    self.publish(path, buy_fill())
                self.assertEqual(1, len(calls))
                self.assertEqual(before, path.read_bytes() if path.exists() else None)
                self.assertFalse(list(path.parent.glob(".allocations.json.*.tmp")))

    def test_nonempty_or_opaque_unbound_inventory_is_not_adopted(self):
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / "allocations.json"
            recovery.persist_spot_buy_allocation(path, buy_fill())
            before = path.read_bytes()
            with self.assertRaises(LiveTradingSafetyError):
                recovery.persist_spot_buy_allocation(path, buy_fill(), namespace=self.namespace)
            self.assertEqual(before, path.read_bytes())
        for snapshot in [{**empty_snapshot(), "entry_allocations": {"BTCUSDT:L": []}},
                         {**empty_snapshot(), "gui_trade_event_receipts": ["unconfirmed-event"]},
                         {**empty_snapshot(), "unknown_history": []}]:
            with self.subTest(snapshot=snapshot), tempfile.TemporaryDirectory() as temp:
                path = Path(temp) / "allocations.json"
                storage.write_ledger(path, snapshot)
                before = path.read_bytes()
                with self.assertRaises(LiveTradingSafetyError):
                    recovery.persist_spot_buy_allocation(path, buy_fill(), namespace=self.namespace)
                self.assertEqual(before, path.read_bytes())

    def test_foreign_uid_store_or_malformed_header_blocks_append_and_replay(self):
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / "allocations.json"
            self.prepare_owned(path)
            self.publish(path, buy_fill())
            before = path.read_bytes()
            for namespace in [make_namespace(UID_B, STORE_A), make_namespace(UID_A, STORE_B), {},
                              {**self.namespace, "account_uid": True}]:
                for fill in [buy_fill(), buy_fill(client="new-buy", order_id=76, trade_offset=1000)]:
                    with self.subTest(namespace=namespace, replay=fill["client_order_id"]), self.assertRaises(LiveTradingSafetyError):
                        recovery.persist_spot_buy_allocation(path, fill, namespace=namespace)
                    self.assertEqual(before, path.read_bytes())
            snapshot = json.loads(path.read_text(encoding="utf-8"))
            snapshot[ACCOUNT_NAMESPACE_KEY] = None
            storage.write_ledger(path, snapshot)
            malformed_before = path.read_bytes()
            with self.assertRaises(LiveTradingSafetyError):
                recovery.persist_spot_buy_allocation(path, buy_fill())
            self.assertEqual(malformed_before, path.read_bytes())

    def test_legacy_fact_builder_does_not_mint_reserved_namespace_from_fill(self):
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / "allocations.json"
            fill = {**buy_fill(), ACCOUNT_NAMESPACE_KEY: self.namespace}
            recovery.persist_spot_buy_allocation(path, fill)
            saved = json.loads(path.read_text(encoding="utf-8"))
            self.assertNotIn(ACCOUNT_NAMESPACE_KEY, saved)
            recovery.validate_spot_buy_replay(saved["entry_allocations"]["BTCUSDT:L"][0], fill)
            with self.assertRaises(LiveTradingSafetyError):
                require_namespace(saved, self.namespace)

    def test_bound_sell_replay_and_buy_replay_preserve_consumed_acquisition(self):
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / "allocations.json"
            buy = buy_fill()
            self.prepare_owned(path)
            self.publish(path, buy)
            before_buy = json.loads(path.read_text(encoding="utf-8"))
            acquisition = before_buy["entry_allocations"]["BTCUSDT:L"][0]["spot_fill_recovery"]
            baseline = recovery.spot_live_allocation_baseline(path, symbol="BTCUSDT", namespace=self.namespace)
            fill = fixtures.SpotFillRecoveryTests().summarize_sell()
            fill.update(pre_order_portfolio_signature=baseline["signature"], pre_order_portfolio_qty=baseline["quantity"])
            original = path.read_bytes()
            for namespace in [None, make_namespace(UID_B, STORE_A), make_namespace(UID_A, STORE_B)]:
                with self.subTest(namespace=namespace), self.assertRaises(LiveTradingSafetyError):
                    recovery.persist_spot_sell_allocation(path, fill, namespace=namespace)
                self.assertEqual(original, path.read_bytes())
            self.publish(path, fill, operation=recovery.persist_spot_sell_allocation)
            sold_bytes = path.read_bytes()
            sold = json.loads(sold_bytes)
            row = sold["entry_allocations"]["BTCUSDT:L"][0]
            self.assertEqual(acquisition, row["spot_fill_recovery"])
            self.assertEqual(Decimal("0.01993"), Decimal(str(row["qty"])))
            self.assertEqual("0.08003", row["spot_sell_recoveries"][0]["consumed_qty"])
            self.assertEqual(self.namespace, sold[ACCOUNT_NAMESPACE_KEY])
            self.publish(path, fill, operation=recovery.persist_spot_sell_allocation)
            self.publish(path, buy)
            self.assertEqual(sold_bytes, path.read_bytes())
            with self.assertRaises(LiveTradingSafetyError):
                recovery.persist_spot_sell_allocation(path, fill)
            self.assertEqual(sold_bytes, path.read_bytes())

    def test_bound_opo_stop_and_strategy_sell_forward_exact_namespace(self):
        helper = fixtures.SpotFillRecoveryTests()
        for strategy in [False, True]:
            intent, working, request = helper.opo_buy_inputs()
            buy_trades = [{"symbol": "BTCUSDT", "id": 301, "orderId": 75, "price": "20000", "qty": "0.1",
                           "quoteQty": "2000", "commission": "0.0001", "commissionAsset": "BTC", "time": 1780000000000, "isBuyer": True}]
            buy = recovery.summarize_spot_opo_buy_fill(intent, working, buy_trades, base_asset="BTC", quote_asset="USDT")
            client = "strategy-exit-1" if strategy else request["pendingClientOrderId"]
            order_id = 402 if strategy else 302
            order = {"symbol": "BTCUSDT", "orderId": order_id, "orderListId": -1 if strategy else 300,
                     "clientOrderId": client, "side": "SELL", "type": "MARKET" if strategy else "STOP_LOSS",
                     "status": "FILLED", "origQty": "0.0999", "executedQty": "0.0999", "stopPrice": "19000",
                     "cummulativeQuoteQty": "1898.1", "updateTime": 1780000000010}
            trades = [{"symbol": "BTCUSDT", "id": 403, "orderId": order_id, "price": "19000", "qty": "0.0999",
                       "quoteQty": "1898.1", "commission": "0", "commissionAsset": "BTC", "time": 1780000000010, "isBuyer": False}]
            with self.subTest(strategy=strategy), tempfile.TemporaryDirectory() as temp:
                path = Path(temp) / "allocations.json"
                self.prepare_owned(path)
                self.assertTrue(self.publish(path, buy, record=intent))
                baseline = recovery.spot_opo_allocation_baseline(path, symbol="BTCUSDT",
                    list_client_order_id=request["listClientOrderId"], expected_quantity="0.0999", namespace=self.namespace)
                linked = {**intent, "entry_reconciled": True, "entry_portfolio_quantity": "0.0999",
                          "entry_recovery_signature": buy["signature"], "list_status": "ALL_DONE"}
                if strategy:
                    exit_request = {"symbol": "BTCUSDT", "side": "SELL", "type": "MARKET", "cancelReplaceMode": "STOP_ON_FAILURE",
                                    "cancelOrderId": 302, "cancelOrigClientOrderId": request["pendingClientOrderId"],
                                    "cancelRestrictions": "ONLY_NEW", "quantity": "0.0999", "newClientOrderId": client, "newOrderRespType": "FULL"}
                    linked.update(protection_state="cancelled", cancel_state="confirmed", pending_status="CANCELED",
                                  strategy_exit_state="sell_accepted", strategy_exit_request=exit_request,
                                  strategy_exit_new_order_accepted=True, strategy_exit_order_id=order_id,
                                  strategy_exit_status="FILLED", strategy_exit_executed_qty="0.0999",
                                  strategy_exit_pre_order_signature=baseline["signature"])
                    writer = recovery.persist_spot_opo_strategy_sell_allocation
                    current = self.author_record(path, linked)
                    fill = recovery.summarize_spot_opo_strategy_sell_fill(current, order, trades, base_asset="BTC", quote_asset="USDT")
                else:
                    linked.update(protection_state="triggered", pending_status="FILLED", pending_executed_qty="0.0999")
                    writer = recovery.persist_spot_opo_stop_sell_allocation
                    current = self.author_record(path, linked)
                    fill = recovery.summarize_spot_opo_stop_sell_fill(current, order, trades, base_asset="BTC", quote_asset="USDT")
                before = path.read_bytes()
                for namespace in [None, make_namespace(UID_B, self.namespace["store_id"])]:
                    with self.subTest(namespace=namespace), self.assertRaises(LiveTradingSafetyError):
                        writer(path, fill, namespace=namespace)
                    self.assertEqual(before, path.read_bytes())
                self.assertTrue(self.publish(path, fill, record=current, operation=writer))
                after = path.read_bytes()
                full_after = self.f.ledger(self.accounts_by_path[path])
                self.assertTrue(self.publish(path, fill, record=current, operation=writer))
                self.assertEqual(after, path.read_bytes())
                self.assertEqual(full_after, self.f.ledger(self.accounts_by_path[path]))
                saved = json.loads(after)
                row = saved["entry_allocations"]["BTCUSDT:L"][0]
                self.assertEqual("Closed", row["status"])
                self.assertEqual(buy["signature"], row["spot_fill_recovery"]["signature"])
                self.assertEqual(self.namespace, saved[ACCOUNT_NAMESPACE_KEY])
                self.assertNotIn("BTCUSDT:L", saved["open_position_records"])
                if strategy:
                    proof_intent = {**current, "strategy_exit_trade_ids": [403]}
                    self.assertTrue(recovery.has_durable_spot_opo_strategy_sell(path, proof_intent, signature=str(fill["signature"]), consumed_quantity="0.0999", namespace=self.namespace))
                else:
                    self.assertTrue(recovery.has_durable_spot_opo_stop_exit(current, signature=str(fill["signature"]), portfolio_quantity="0.0999", namespace=self.namespace))

    def test_readers_and_baselines_never_convert_namespace_failure_to_false(self):
        from app.gui.shared import allocation_persistence

        def readers(path):
            return [
                lambda ns: recovery.has_durable_spot_opo_strategy_sell(path, {}, signature="0" * 64, consumed_quantity="1", namespace=ns),
                lambda ns: recovery.has_durable_spot_opo_strategy_sell_recovery(path, {}, signature="0" * 64, consumed_quantity="1", remaining_quantity="1", trade_ids=[1], namespace=ns),
                lambda ns: recovery.has_durable_spot_opo_residual_stop_allocation(path, {}, signature="0" * 64, consumed_quantity="1", remaining_quantity="1", trade_ids=[1], namespace=ns),
                lambda ns: recovery.has_durable_spot_opo_stop_exit({}, signature="0" * 64, portfolio_quantity="1", namespace=ns),
                lambda ns: recovery.spot_live_allocation_baseline(path, symbol="BTCUSDT", namespace=ns),
                lambda ns: recovery.spot_opo_allocation_baseline(path, symbol="BTCUSDT", list_client_order_id="not-the-entry", expected_quantity="1", namespace=ns),
                lambda ns: recovery.spot_opo_allocation_baseline_unlocked(path, symbol="BTCUSDT", list_client_order_id="not-the-entry", expected_quantity="1", namespace=ns),
            ]

        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / "allocations.json"
            recovery.persist_spot_buy_allocation(path, buy_fill())
            before = path.read_bytes()
            with patch.object(allocation_persistence, "get_position_allocations_path", return_value=path):
                for index, reader in enumerate(readers(path)):
                    with self.subTest(reader=index, source="nonempty-unbound"), self.assertRaises(LiveTradingSafetyError):
                        reader(self.namespace)
                    self.assertEqual(before, path.read_bytes())
                snapshot = self.bind_test_fixture(path, self.namespace)
                bound_before = path.read_bytes()
                for index, reader in enumerate(readers(path)):
                    for namespace in [None, make_namespace(UID_B, STORE_A), make_namespace(UID_A, STORE_B)]:
                        with self.subTest(reader=index, namespace=namespace), self.assertRaises(LiveTradingSafetyError):
                            reader(namespace)
                        self.assertEqual(bound_before, path.read_bytes())
                for index, reader in enumerate(readers(path)[:4]):
                    with self.subTest(reader=index, source="correct-namespace-invalid-proof"):
                        self.assertFalse(reader(self.namespace))
                self.assertEqual("0.09996", readers(path)[4](self.namespace)["quantity"])
                snapshot[ACCOUNT_NAMESPACE_KEY] = {**self.namespace, "account_uid": True}
                storage.write_ledger(path, snapshot)
                malformed_before = path.read_bytes()
                for index, reader in enumerate(readers(path)):
                    with self.subTest(reader=index, source="malformed-bound"), self.assertRaises(LiveTradingSafetyError):
                        reader(self.namespace)
                    self.assertEqual(malformed_before, path.read_bytes())

    def test_foreign_bound_empty_source_cannot_be_relabelled_by_first_buy(self):
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / "allocations.json"
            storage.write_ledger(path, {**empty_snapshot(), ACCOUNT_NAMESPACE_KEY: make_namespace(UID_B, STORE_A)})
            before = path.read_bytes()
            for namespace in [None, self.namespace]:
                with self.subTest(namespace=namespace), self.assertRaises(LiveTradingSafetyError):
                    recovery.persist_spot_buy_allocation(path, buy_fill(), namespace=namespace)
                self.assertEqual(before, path.read_bytes())

    def test_caller_locked_buy_writer_keeps_same_namespace_contract(self):
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / "allocations.json"
            account = self.prepare_owned(path)
            with storage.ledger_transactions(account.path, path):
                self.publish(path, buy_fill(), operation=recovery._persist_spot_buy_allocation_unlocked)
                before = path.read_bytes()
                self.publish(path, buy_fill(), operation=recovery._persist_spot_buy_allocation_unlocked)
                with self.assertRaises(LiveTradingSafetyError):
                    recovery._persist_spot_buy_allocation_unlocked(path, buy_fill())
                self.assertEqual(before, path.read_bytes())

    def test_bound_full_size_residual_stop_forwards_namespace_without_restoring_inventory(self):
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / "allocations.json"
            facts = Path(temp) / "unbound-original-facts.json"
            helper = fixtures.SpotFillRecoveryTests()
            intent, order, trades = helper.full_size_residual_stop_inputs(facts)
            initial, working, _request = helper.opo_buy_inputs()
            buy_trades = [{"symbol": "BTCUSDT", "id": 601, "orderId": 75, "price": "20000", "qty": "0.1",
                           "quoteQty": "2000", "commission": "0.0001", "commissionAsset": "BTC", "time": 1780000000000, "isBuyer": True}]
            buy = recovery.summarize_spot_opo_buy_fill(initial, working, buy_trades, base_asset="BTC", quote_asset="USDT")
            self.prepare_owned(path)
            self.assertTrue(self.publish(path, buy, record=initial))
            baseline = recovery.spot_opo_allocation_baseline(path, symbol="BTCUSDT", list_client_order_id=initial["client_order_id"], expected_quantity="0.0999", namespace=self.namespace)
            intent["residual_stop_pre_order_signature"] = baseline["signature"]
            current = self.author_record(path, intent)
            fill = recovery.summarize_spot_opo_residual_stop_sell_fill(current, order, trades, base_asset="BTC", quote_asset="USDT")
            before = path.read_bytes()
            for namespace in [None, make_namespace(UID_A, STORE_B)]:
                with self.subTest(namespace=namespace), self.assertRaises(LiveTradingSafetyError):
                    recovery.persist_spot_opo_residual_stop_allocation(path, fill, namespace=namespace)
                self.assertEqual(before, path.read_bytes())
            writer = recovery.persist_spot_opo_residual_stop_allocation
            account = self.accounts_by_path[path]
            ledger_before = self.f.ledger(account)
            backend = checkpoint_backend_for_case(self)
            protected_before = dict(backend.store)
            normalized = {**fill, "pre_order_portfolio_signature": fill["residual_stop_pre_order_signature"],
                          "pre_order_portfolio_qty": fill["residual_stop_pre_order_quantity"]}
            invalid = [{key: value for key, value in normalized.items() if key != missing}
                       for missing in ("pre_order_portfolio_signature", "pre_order_portfolio_qty")]
            invalid += [{**normalized, **change} for change in (
                {"pre_order_portfolio_signature": "f" * 64}, {"pre_order_portfolio_qty": "0.2"},
                {"pre_order_extra": "foreign"},
            )]
            for changed in invalid:
                with self.subTest(changed=changed), self.assertRaises(LiveTradingSafetyError):
                    self.publish(path, changed, record=current, operation=writer)
                self.assertEqual(before, path.read_bytes())
                self.assertEqual(ledger_before, self.f.ledger(account))
                self.assertEqual(protected_before, backend.store)
            self.assertTrue(self.publish(path, fill, record=current, operation=writer))
            after = path.read_bytes()
            full_after = self.f.ledger(self.accounts_by_path[path])
            self.assertTrue(self.publish(path, fill, record=current, operation=writer))
            self.assertEqual(after, path.read_bytes())
            self.assertEqual(full_after, self.f.ledger(self.accounts_by_path[path]))
            self.assertTrue(recovery.has_durable_spot_opo_residual_stop_allocation(path, current, signature=str(fill["signature"]), consumed_quantity="0.0999", remaining_quantity="0", trade_ids=[603], namespace=self.namespace))
            saved = json.loads(after)
            self.assertEqual("Closed", saved["entry_allocations"]["BTCUSDT:L"][0]["status"])
            self.assertEqual(self.namespace, saved[ACCOUNT_NAMESPACE_KEY])
            self.assertNotIn("BTCUSDT:L", saved["open_position_records"])


if __name__ == "__main__":
    unittest.main()
