"""Actual protected product paths with synthetic signed venue and isolated OS store."""
from contextlib import contextmanager
from copy import deepcopy
from decimal import Decimal
import json
import unittest
from unittest.mock import patch

import test_spot_inventory_namespace_integration as fixtures
from spot_inventory_checkpoint_fixtures import CheckpointFixtureBackend
from app.gui.shared import allocation_persistence as allocations
from app.integrations.exchanges.binance.orders import order_intent_runtime as intents
from app.integrations.exchanges.binance.orders import spot_buy_admin_recovery_runtime as admin
from app.integrations.exchanges.binance.orders import spot_desktop_buy_recovery_runtime as desktop
from app.integrations.exchanges.binance.orders import spot_fill_recovery_runtime as fills
from app.integrations.exchanges.binance.orders import spot_inventory_checkpoint as core
from app.integrations.exchanges.binance.orders import spot_inventory_checkpoint_runtime as checkpoint
from app.integrations.exchanges.binance.orders.spot_inventory_namespace_runtime import publish_owned_spot_fill
from app.integrations.exchanges.binance.orders.spot_buy_publication_runtime import desktop_entry_transaction
from app.integrations.exchanges.binance.orders.order_intent_store import ledger_transaction, write_ledger
from app.integrations.exchanges.binance.orders.spot_execution_owner import owner_administration_lock
from app.settings.live_safety import LiveTradingSafetyError


class SpotCheckpointProductIntegrationTests(unittest.TestCase):
    def setUp(self):
        self.backend = self.enterContext(CheckpointFixtureBackend(simulate_windows=True))
        self.f = fixtures.SpotInventoryNamespaceIntegrationTests("runTest")
        self.f.setUp()
        self.addCleanup(self.f.doCleanups)
        response = deepcopy(fixtures.RESPONSE)
        response["fills"][0]["commission"] = "0"
        self.fill = fills.summarize_primary_spot_buy(
            response, symbol="BTCUSDT", client_order_id=fixtures.CLIENT, base_asset="BTC", quote_asset="USDT",
        )

    def fresh(self):
        account = self.f.account("protected-product", 895001, accepted=False)
        with self.f.account_home(account):
            self.assertTrue(checkpoint.bootstrap_owned_inventory_checkpoint(account.wrapper, allocation_path=self.f.path))
        return account

    def author_buy(self, account):
        return self.f.author_accepted(account, self.fill)

    def publish_buy(self, account, record):
        with self.f.account_home(account):
            return publish_owned_spot_fill(account.wrapper, self.f.path, self.fill,
                                           expected_record=record, operation=fills._persist_spot_buy_allocation_unlocked)

    def read_only_wrapper(self, account):
        account.owner.close()
        wrapper = self.f.new_wrapper(account.wrapper.api_key, account.wrapper.api_secret, account.home, account.venue)
        return wrapper

    def test_actual_consumption_rollback_fences_load_admission_proof_and_confirmation(self):
        account = self.fresh()
        buy = self.author_buy(account)
        self.assertTrue(self.publish_buy(account, buy))
        old = self.f.path.read_bytes()
        with self.f.account_home(account):
            baseline = fills.spot_live_allocation_baseline(self.f.path, symbol="BTCUSDT", namespace=account.namespace)
            params = {"symbol": "BTCUSDT", "side": "SELL", "type": "MARKET", "quantity": "0.04",
                      "newClientOrderId": "protected-product-sell"}
            sell = intents._intent_record(params, market="spot", source="offline-checkpoint-fixture")
            sell.update(state="accepted", exchange_status="FILLED", exchange_order_id="707002", executed_qty="0.04",
                        portfolio_qty="0.04", portfolio_pre_order_qty=baseline["quantity"],
                        portfolio_pre_order_signature=baseline["signature"])
            with ledger_transaction(account.path):
                ledger = intents._read_ledger(account.path, expected_binding=intents._intent_binding(account.wrapper))
                ledger["intents"][params["newClientOrderId"]] = sell
                intents.validate_order_intent_ledger(ledger, expected_binding=intents._intent_binding(account.wrapper))
                write_ledger(account.path, ledger)
            response = {"symbol": "BTCUSDT", "side": "SELL", "type": "MARKET", "clientOrderId": params["newClientOrderId"],
                        "orderId": 707002, "status": "FILLED", "origQty": "0.04", "executedQty": "0.04",
                        "cummulativeQuoteQty": "800", "updateTime": 1780000000002}
            trades = [{"id": 909002, "orderId": 707002, "symbol": "BTCUSDT", "price": "20000", "qty": "0.04",
                       "quoteQty": "800", "commission": "0", "commissionAsset": "USDT", "time": 1780000000002,
                       "isBuyer": False}]
            fill = fills.summarize_spot_market_fill(sell, response, trades, base_asset="BTC", quote_asset="USDT")
            fill.update(pre_order_portfolio_signature=baseline["signature"],
                        pre_order_portfolio_qty=baseline["quantity"])
            self.assertTrue(publish_owned_spot_fill(account.wrapper, self.f.path, fill,
                                                   expected_record=sell, operation=fills.persist_spot_sell_allocation))
            current = json.loads(self.f.path.read_bytes())
            self.assertEqual(Decimal("0.06"), Decimal(str(current["entry_allocations"]["BTCUSDT:L"][0]["qty"])))
            durable_before = self.f.durable_bytes(account)[1:]
            protected_before = deepcopy(self.backend.store)
            self.f.path.write_bytes(old)
            self.assertEqual(Decimal("0.1"), Decimal(str(json.loads(old)["entry_allocations"]["BTCUSDT:L"][0]["qty"])))
            operations = (
                lambda: fills.spot_live_allocation_baseline(self.f.path, symbol="BTCUSDT", namespace=account.namespace),
                lambda: intents._has_durable_spot_buy_allocation(buy, portfolio_signature=self.fill["signature"],
                                                                 portfolio_quantity="0.1", namespace=account.namespace),
                lambda: intents._has_durable_spot_buy_allocation(buy, portfolio_signature=self.fill["signature"],
                                                                 portfolio_quantity="0.1"),
                lambda: checkpoint.bootstrap_owned_inventory_checkpoint(account.wrapper, allocation_path=self.f.path),
            )
            for operation in operations:
                with self.subTest(operation=operation), self.assertRaises(LiveTradingSafetyError):
                    operation()
            with self.assertRaises(LiveTradingSafetyError):
                with desktop_entry_transaction(account.wrapper, account.path, fixtures.PARAMS, None):
                    self.fail("Restored inventory admitted a new BUY")
            with self.assertRaises(LiveTradingSafetyError):
                account.wrapper._mark_order_intent_portfolio_reconciled(
                    fixtures.CLIENT, portfolio_signature=self.fill["signature"], portfolio_quantity="0.1",
                )
            session = allocations.AllocationSnapshotSession()
            self.assertEqual(({}, {}), allocations.load_position_allocations(
                this_file=account.home / "unused.py", mode="Live", session=session,
            ))
            self.assertFalse(session.ready)
            self.assertEqual(durable_before, self.f.durable_bytes(account)[1:])
            self.assertEqual(protected_before, self.backend.store)
            self.assertEqual([], self.f.order_calls)

    def test_explicit_desktop_pending_recovery_finishes_exact_target_then_reloads(self):
        account = self.fresh()
        record = self.author_buy(account)
        before = self.f.durable_bytes(account)
        with patch.object(core, "_finish", side_effect=OSError("synthetic pending crash")), self.assertRaises(LiveTradingSafetyError):
            self.publish_buy(account, record)
        self.assertEqual(before, self.f.durable_bytes(account))
        self.assertEqual("pending", json.loads(next(iter(self.backend.store.values())))["state"])
        wrapper = self.read_only_wrapper(account)
        discovery_before = (self.f.path.read_bytes(), account.path.read_bytes(), deepcopy(self.backend.store))
        with self.f.account_home(account):
            discovery = desktop.discover_spot_desktop_buy_recoveries(wrapper, allocation_path=self.f.path)
            self.assertEqual(1, len(discovery.items))
            item = discovery.items[0]
            self.assertTrue(item.checkpoint_pending)
            self.assertEqual(discovery_before, (self.f.path.read_bytes(), account.path.read_bytes(), deepcopy(self.backend.store)))
            session = allocations.AllocationSnapshotSession()
            allocations.load_position_allocations(this_file=account.home / "unused.py", mode="Live", session=session)
            self.assertFalse(session.ready)
            @contextmanager
            def handoff():
                with session._mutex:
                    self.assertIs(wrapper, item.authority.wrapper)
                    yield
            result = desktop.recover_spot_desktop_prepared_buy(wrapper, item, allocation_path=self.f.path,
                                                              session=session, publication_handoff=handoff)
            self.assertTrue(result["checkpoint_recovered"])
            self.assertTrue(result["portfolio_reconciled"])
            self.assertFalse(session.ready)
            entries, records = allocations.load_position_allocations(this_file=account.home / "unused.py", mode="Live", session=session)
            self.assertTrue(session.ready)
            self.assertEqual(Decimal("0.1"), Decimal(str(entries[("BTCUSDT", "L")][0]["qty"])))
            self.assertIn(("BTCUSDT", "L"), records)
            self.assertEqual("stable", json.loads(next(iter(self.backend.store.values())))["state"])
            self.assertEqual([], self.f.order_calls)

    def test_unknown_terminal_admin_recovery_retains_real_admin_and_original_receipt(self):
        account = self.fresh()
        record = self.author_buy(account)
        with self.f.account_home(account), ledger_transaction(account.path):
            ledger = intents._read_ledger(account.path, expected_binding=intents._intent_binding(account.wrapper))
            ledger["intents"][fixtures.CLIENT]["state"] = "unknown"
            record = deepcopy(ledger["intents"][fixtures.CLIENT])
            intents.validate_order_intent_ledger(ledger, expected_binding=intents._intent_binding(account.wrapper))
            write_ledger(account.path, ledger)
        wrapper = self.read_only_wrapper(account)
        with self.f.account_home(account):
            wrapper._resolve_spot_account_uid()
            with owner_administration_lock(account.path), desktop._desktop_inventory_administration(wrapper, account.path):
                arguments = dict(expected_record=record, expected_intent_path=account.path,
                                 expected_binding=intents._intent_binding(wrapper), expected_store_id=account.namespace["store_id"])
                normalized = {**self.fill, "portfolio_qty": self.fill["net_qty"]}
                self.assertTrue(admin.publish_spot_buy_recovery(wrapper, self.f.path, normalized, **arguments))
                result = admin.confirm_spot_buy_recovery(wrapper, self.f.path, normalized, **arguments)
                self.assertTrue(result["portfolio_reconciled"])
            self.assertEqual([], self.f.order_calls)


if __name__ == "__main__":
    unittest.main()
