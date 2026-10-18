"""Recovery product controls using confined files and explicit fake protected storage."""
from copy import deepcopy
import json
from decimal import Decimal
import unittest
from unittest.mock import patch

import test_spot_inventory_namespace_integration as fixtures
from app.integrations.exchanges.binance.orders import order_intent_runtime as intents
from app.integrations.exchanges.binance.orders import spot_fill_recovery_runtime as fills
from app.integrations.exchanges.binance.orders import spot_inventory_checkpoint as core
from app.integrations.exchanges.binance.orders import spot_inventory_checkpoint_runtime as owned
from app.integrations.exchanges.binance.orders import spot_inventory_namespace_runtime as namespaces
from app.integrations.exchanges.binance.orders.order_intent_store import ledger_transaction, write_ledger
from app.settings.live_safety import LiveTradingSafetyError


class SpotFillCheckpointIntegrationTests(unittest.TestCase):
    def setUp(self):
        self.f = fixtures.SpotInventoryNamespaceIntegrationTests("runTest")
        self.addCleanup(self.f.doCleanups)
        self.f.setUp()
        self.store, self.puts, self.gets = {}, [], []
        self.fail_stable = False
        self.enterContext(patch.object(core, "_windows_read_adapter", return_value=True))
        self.enterContext(patch.object(core.credential_store, "credential_store_backend",
                                       return_value="windows-credential-manager"))
        self.enterContext(patch.object(core.credential_store, "get_secret", side_effect=self.get))
        self.enterContext(patch.object(core.credential_store, "put_secret", side_effect=self.put))
        self.enterContext(patch.object(core.credential_store, "delete_secret",
                                       side_effect=AssertionError("No native credential deletion")))

    def get(self, *, scope, account):
        self.assertEqual("spot-inventory-checkpoint-v1", scope)
        self.gets.append((scope, account))
        return self.store.get((scope, account), "")

    def put(self, *, scope, account, value):
        self.assertEqual("spot-inventory-checkpoint-v1", scope)
        if self.fail_stable and json.loads(value)["state"] == "stable":
            self.fail_stable = False
            raise OSError("Isolated protected stable publication failure")
        self.store[scope, account] = value
        self.puts.append(value)

    def fresh(self):
        account = self.f.account("protected-recovery", 881001, accepted=False)
        with self.f.account_home(account):
            self.assertTrue(owned.bootstrap_owned_inventory_checkpoint(account.wrapper, allocation_path=self.f.path))
        record = self.f.author_accepted(account, self.f.fill)
        return account, record

    def publish(self, account, record, fill=None, operation=None):
        with self.f.account_home(account):
            return namespaces.publish_owned_spot_fill(
                account.wrapper, self.f.path, fill or self.f.fill, expected_record=record,
                operation=operation or fills.persist_spot_buy_allocation,
            )

    def before(self, account):
        return self.f.durable_bytes(account), self.f.ledger(account), deepcopy(self.store), list(self.puts)

    def baseline(self, account):
        return fills.spot_live_allocation_baseline(self.f.path, symbol="BTCUSDT", namespace=account.namespace)

    def author_sell(self, account, baseline):
        params = {"symbol": "BTCUSDT", "side": "SELL", "type": "MARKET", "quantity": "0.04",
                  "newClientOrderId": "checkpoint-owned-sell"}
        record = intents._intent_record(params, market="spot", source="offline-checkpoint-fixture")
        record.update(state="accepted", exchange_status="FILLED", exchange_order_id="707002", executed_qty="0.04",
                      portfolio_qty="0.04", portfolio_reconciled=False, accepted_at=intents._now(),
                      portfolio_pre_order_signature=baseline["signature"], portfolio_pre_order_qty=baseline["quantity"])
        intents.validate_order_intent_record(record["client_order_id"], record)
        order = {"clientOrderId": record["client_order_id"], "symbol": "BTCUSDT", "side": "SELL", "type": "MARKET",
                 "orderId": 707002, "status": "FILLED", "origQty": "0.04", "executedQty": "0.04",
                 "cummulativeQuoteQty": "800", "updateTime": 1780000001000}
        trades = [{"symbol": "BTCUSDT", "id": 909002, "orderId": 707002, "price": "20000", "qty": "0.04",
                   "quoteQty": "800", "commission": "0", "commissionAsset": "BTC", "time": 1780000001000,
                   "isBuyer": False}]
        fill = fills.summarize_spot_market_fill(record, order, trades, base_asset="BTC", quote_asset="USDT")
        fill.update(pre_order_portfolio_signature=baseline["signature"], pre_order_portfolio_qty=baseline["quantity"])
        with self.f.account_home(account), ledger_transaction(account.path):
            ledger = intents._read_ledger(account.path, expected_binding=intents._intent_binding(account.wrapper))
            ledger["intents"][record["client_order_id"]] = record
            intents.validate_order_intent_ledger(ledger, expected_binding=intents._intent_binding(account.wrapper))
            write_ledger(account.path, ledger)
        return record, fill

    def test_owned_buy_replay_is_read_only_and_preserves_complete_history(self):
        account, record = self.fresh()
        full = self.f.ledger(account)
        self.assertTrue(self.publish(account, record))
        before = self.before(account)
        self.assertEqual(self.f.fill["net_qty"], self.baseline(account)["quantity"])
        self.assertTrue(self.publish(account, record))
        self.assertEqual(before, self.before(account))
        self.assertEqual(full, self.f.ledger(account))
        self.assertEqual([], self.f.order_calls)

    def test_direct_bound_buy_write_and_matching_replay_require_actual_context(self):
        account, record = self.fresh()
        before = self.before(account)
        with self.assertRaises(LiveTradingSafetyError):
            fills.persist_spot_buy_allocation(self.f.path, self.f.fill, namespace=account.namespace)
        self.assertEqual(before, self.before(account))
        self.assertTrue(self.publish(account, record))
        before = self.before(account)
        with self.assertRaises(LiveTradingSafetyError):
            fills.persist_spot_buy_allocation(self.f.path, self.f.fill, namespace=account.namespace)
        self.assertEqual(before, self.before(account))

    def test_valid_different_fill_cannot_consume_original_record_publication_context(self):
        account, record = self.fresh()
        response = deepcopy(fixtures.RESPONSE)
        response.update(clientOrderId="different-unrecorded-buy", orderId=707099)
        response["fills"][0]["tradeId"] = 909099
        other = fills.summarize_primary_spot_buy(response, symbol="BTCUSDT",
            client_order_id=response["clientOrderId"], base_asset="BTC", quote_asset="USDT")
        before = self.before(account)
        with self.f.account_home(account), self.assertRaises(LiveTradingSafetyError):
            with owned.owned_inventory_publication(account.wrapper, allocation_path=self.f.path,
                                                   expected_record=record, fill=self.f.fill):
                fills.persist_spot_buy_allocation(self.f.path, other, namespace=account.namespace)
        self.assertEqual(before, self.before(account))

    def test_owned_sell_conservation_and_buy_replay_do_not_restore_consumed_inventory(self):
        account, buy = self.fresh()
        self.assertTrue(self.publish(account, buy))
        sell, fill = self.author_sell(account, self.baseline(account))
        full = self.f.ledger(account)
        self.assertTrue(self.publish(account, sell, fill, fills.persist_spot_sell_allocation))
        expected = str(Decimal(self.f.fill["net_qty"]) - Decimal("0.04"))
        self.assertEqual(expected, self.baseline(account)["quantity"])
        before = self.before(account)
        self.assertTrue(self.publish(account, buy))
        self.assertTrue(self.publish(account, sell, fill, fills.persist_spot_sell_allocation))
        self.assertEqual(before, self.before(account))
        self.assertEqual(full, self.f.ledger(account))
        self.assertEqual([], self.f.order_calls)

    def test_coherent_consumption_rollback_fences_baseline_and_matching_buy_replay(self):
        account, buy = self.fresh()
        self.assertTrue(self.publish(account, buy))
        old = self.f.path.read_bytes()
        sell, fill = self.author_sell(account, self.baseline(account))
        self.assertTrue(self.publish(account, sell, fill, fills.persist_spot_sell_allocation))
        self.f.path.write_bytes(old)
        before = self.before(account)
        for call in (lambda: self.baseline(account), lambda: self.publish(account, buy),
                     lambda: fills.spot_live_allocation_baseline(self.f.path, symbol="BTCUSDT")):
            with self.subTest(call=call), self.assertRaises(LiveTradingSafetyError):
                call()
            self.assertEqual(before, self.before(account))

    def test_path_slot_checked_after_deletion_namespace_stripping_and_mode_change(self):
        account, record = self.fresh()
        self.assertTrue(self.publish(account, record))
        original = self.f.path.read_bytes()
        changed = json.loads(original)
        stripped = deepcopy(changed)
        del stripped["spot_account_namespace"]
        for payload in (None, stripped, {**changed, "mode": "Paper"}):
            with self.subTest(payload=payload):
                if payload is None:
                    self.f.path.unlink()
                else:
                    self.f.path.write_text(json.dumps(payload), encoding="utf-8")
                before = self.before(account)
                with self.assertRaises(LiveTradingSafetyError):
                    fills.spot_live_allocation_baseline(self.f.path, symbol="BTCUSDT")
                with self.assertRaises(LiveTradingSafetyError):
                    fills.persist_spot_buy_allocation(self.f.path, self.f.fill)
                self.assertEqual(before, self.before(account))
                self.f.path.write_bytes(original)

    def test_bound_empty_snapshot_without_protected_slot_cannot_be_adopted(self):
        account, record = self.fresh()
        self.store.clear()  # Explicit synthetic protected-store loss, never a product reset.
        before = self.before(account)
        with self.assertRaises(LiveTradingSafetyError):
            self.publish(account, record)
        with self.assertRaises(LiveTradingSafetyError):
            self.baseline(account)
        self.assertEqual(before, self.before(account))

    def test_sole_unpublished_history_cannot_seal_missing_source(self):
        account = self.f.account("legacy-sole", 881002)
        record = self.f.ledger(account)["intents"][self.f.fill["client_order_id"]]
        before = self.before(account)
        with self.assertRaises(LiveTradingSafetyError):
            self.publish(account, record)
        self.assertEqual(before, self.before(account))
        self.assertFalse(self.f.path.exists())
        self.assertEqual({}, self.store)

    def test_pending_fences_every_durable_reader_then_exact_owned_recovery_finishes(self):
        account, record = self.fresh()
        self.fail_stable = True
        with self.assertRaises(LiveTradingSafetyError):
            self.publish(account, record)
        self.assertEqual({"pending"}, {json.loads(value)["state"] for value in self.store.values()})
        before = self.before(account)
        signature = "0" * 64
        calls = (
            lambda: self.baseline(account),
            lambda: fills.spot_opo_allocation_baseline(self.f.path, symbol="BTCUSDT",
                list_client_order_id="not-authority", expected_quantity="0.1", namespace=account.namespace),
            lambda: fills.has_durable_spot_opo_strategy_sell(self.f.path, {}, signature=signature,
                consumed_quantity="0.1", namespace=account.namespace),
            lambda: fills.has_durable_spot_opo_strategy_sell_recovery(self.f.path, {}, signature=signature,
                consumed_quantity="0.1", remaining_quantity="0.01", trade_ids=[1], namespace=account.namespace),
            lambda: fills.has_durable_spot_opo_residual_stop_allocation(self.f.path, {}, signature=signature,
                consumed_quantity="0.1", remaining_quantity="0.01", trade_ids=[1], namespace=account.namespace),
            lambda: fills.has_durable_spot_opo_stop_exit({}, signature=signature, portfolio_quantity="0.1",
                namespace=account.namespace),
        )
        for index, call in enumerate(calls):
            with self.subTest(reader=index), self.assertRaises(LiveTradingSafetyError):
                call()
            self.assertEqual(before, self.before(account))
        target = self.f.path.read_bytes()
        self.assertTrue(self.publish(account, record))
        self.assertEqual(target, self.f.path.read_bytes())
        self.assertEqual({"stable"}, {json.loads(value)["state"] for value in self.store.values()})
        self.assertEqual(before[0][1:], self.f.durable_bytes(account)[1:])
        self.assertEqual(before[1], self.f.ledger(account))

    def test_changed_complete_record_rejects_before_operation_callback(self):
        account, record = self.fresh()
        changed = {**record, "updated_at": "different"}
        before = self.before(account)
        with self.assertRaises(LiveTradingSafetyError):
            self.publish(account, changed, operation=lambda *_args, **_kwargs: self.fail("Detached callback reached"))
        self.assertEqual(before, self.before(account))

    def test_ordinary_unbound_fixture_without_slot_remains_compatible(self):
        path = self.f.home / "ordinary-unbound.json"
        self.assertTrue(fills.persist_spot_buy_allocation(path, self.f.fill))
        before = path.read_bytes(), deepcopy(self.store), list(self.puts)
        self.assertIsNotNone(fills.spot_live_allocation_baseline(path, symbol="BTCUSDT"))
        self.assertTrue(fills.persist_spot_buy_allocation(path, self.f.fill))
        self.assertEqual(before, (path.read_bytes(), self.store, self.puts))
        self.assertEqual([], self.f.order_calls)


if __name__ == "__main__":
    unittest.main()