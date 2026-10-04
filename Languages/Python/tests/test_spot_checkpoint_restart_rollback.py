"""Independent synthetic owner close/rearm/reclaim and coherent inventory rollback control."""
from copy import deepcopy
import hashlib
import json
from types import SimpleNamespace
import unittest
from unittest.mock import patch

import test_spot_checkpoint_product_integration as product_fixtures
from app.gui.runtime.account import account_runtime
from app.gui.shared import allocation_persistence as allocations
from app.integrations.exchanges.binance.orders import order_intent_runtime as intents
from app.integrations.exchanges.binance.orders import spot_fill_recovery_runtime as fills
from app.integrations.exchanges.binance.orders.order_intent_provisioning import PROVISION_ACK, rearm_spot_execution_owner
from app.integrations.exchanges.binance.orders.order_intent_store import ledger_transaction, ledger_transactions, write_ledger
from app.integrations.exchanges.binance.orders.spot_execution_owner import owner_marker_path
from app.integrations.exchanges.binance.orders.spot_inventory_namespace_runtime import namespace_for_owner, publish_owned_spot_fill
from app.settings.live_safety import LiveTradingSafetyError


class SpotCheckpointRestartRollbackTests(unittest.TestCase):
    def setUp(self):
        self.product = product_fixtures.SpotCheckpointProductIntegrationTests("runTest")
        self.product.setUp()
        self.addCleanup(self.product.doCleanups)
        self.f, self.backend = self.product.f, self.product.backend
        self.observed = {}

    def _artifact(self, name, raw):
        root = getattr(self, "artifact_root", None)
        if root is not None:
            root.mkdir(parents=True, exist_ok=True)
            (root / name).write_bytes(raw)
        return hashlib.sha256(raw).hexdigest()

    def _load_window(self, wrapper, home):
        session = allocations.AllocationSnapshotSession()
        ticket = allocations.AllocationSnapshotLoadTicket()
        maps = allocations.load_position_allocations(this_file=home / "unused.py", mode="Live",
                                                     session=session, load_ticket=ticket)
        window = SimpleNamespace(shared_binance=wrapper, _allocation_snapshot_session=session,
                                 mode_combo=SimpleNamespace(currentText=lambda: "Live"), config={},
                                 _account_observation_generation=0, _entry_allocations={}, _open_position_records={})
        with session.loaded_handoff(ticket) as accepted:
            if accepted:
                window._entry_allocations, window._open_position_records = maps
        with patch.object(account_runtime, "BinanceWrapper", return_value=wrapper):
            actual = account_runtime._create_binance_wrapper(
                window, api_key=wrapper.api_key, api_secret=wrapper.api_secret, mode=wrapper.mode,
                account_type=wrapper.account_type, connector_backend="binance-sdk-spot",
            )
        self.assertIs(wrapper, actual)
        return window, accepted

    def _exercise(self, *, expect_blocked):
        account = self.product.fresh()
        buy = self.product.author_buy(account)
        self.assertTrue(self.product.publish_buy(account, buy))
        with self.f.account_home(account):
            marked = account.wrapper._mark_order_intent_portfolio_reconciled(
                buy["client_order_id"], portfolio_signature=self.product.fill["signature"], portfolio_quantity="0.1",
            )
            self.assertTrue(marked["portfolio_reconciled"])
            old = self.f.path.read_bytes()
            old_payload = json.loads(old)
            baseline = fills.spot_live_allocation_baseline(self.f.path, symbol="BTCUSDT", namespace=account.namespace)
            self.assertEqual("0.1", baseline["quantity"])
            params = {"symbol": "BTCUSDT", "side": "SELL", "type": "MARKET", "quantity": "0.04",
                      "newClientOrderId": "restart-proof-sell"}
            sell = intents._intent_record(params, market="spot", source="offline-restart-checkpoint-fixture")
            sell.update(state="accepted", exchange_status="FILLED", exchange_order_id="707002", executed_qty="0.04",
                        portfolio_qty="0.04", portfolio_pre_order_qty=baseline["quantity"],
                        portfolio_pre_order_signature=baseline["signature"])
            with ledger_transaction(account.path):
                ledger = intents._read_ledger(account.path, expected_binding=intents._intent_binding(account.wrapper))
                ledger["intents"][sell["client_order_id"]] = sell
                intents.validate_order_intent_ledger(ledger, expected_binding=intents._intent_binding(account.wrapper))
                write_ledger(account.path, ledger)
            order = {"symbol": "BTCUSDT", "side": "SELL", "type": "MARKET", "clientOrderId": sell["client_order_id"],
                     "orderId": 707002, "status": "FILLED", "origQty": "0.04", "executedQty": "0.04",
                     "cummulativeQuoteQty": "800", "updateTime": 1780000001000}
            trades = [{"id": 909002, "orderId": 707002, "symbol": "BTCUSDT", "price": "20000", "qty": "0.04",
                       "quoteQty": "800", "commission": "0", "commissionAsset": "BTC", "time": 1780000001000,
                       "isBuyer": False}]
            fill = fills.summarize_spot_market_fill(sell, order, trades, base_asset="BTC", quote_asset="USDT")
            fill.update(pre_order_portfolio_signature=baseline["signature"], pre_order_portfolio_qty=baseline["quantity"])
            self.assertTrue(publish_owned_spot_fill(account.wrapper, self.f.path, fill,
                                                   expected_record=sell, operation=fills.persist_spot_sell_allocation))
            self.assertTrue(account.wrapper._mark_order_intent_portfolio_reconciled(
                sell["client_order_id"], portfolio_signature=fill["signature"], portfolio_quantity="0.04",
            )["portfolio_reconciled"])
            self.assertEqual("0.06", fills.spot_live_allocation_baseline(
                self.f.path, symbol="BTCUSDT", namespace=account.namespace)["quantity"])
            complete = self.f.ledger(account)
            self.assertEqual(2, len(complete["intents"]))
            self.assertTrue(all(record["portfolio_reconciled"] for record in complete["intents"].values()))
            self.assertEqual(0, account.wrapper.get_order_intent_status()["unresolved_count"])
            full_raw = account.path.read_bytes()
            current = self.f.path.read_bytes()
            original_owner = account.owner
            self.assertEqual(1, original_owner.generation)
            protected, puts = deepcopy(self.backend.store), list(self.backend.put_calls)
            original_owner.close()
            marker_path = owner_marker_path(account.path)
            self.assertEqual("recovery_required", json.loads(marker_path.read_bytes())["state"])
            self._artifact("marker-after-owner-close.json", marker_path.read_bytes())
            with ledger_transactions(account.path, self.f.path):
                self.f.path.write_bytes(old)  # Whole old valid snapshot; no fields are forged/relabelled.
            self.assertEqual(full_raw, account.path.read_bytes())
            result = rearm_spot_execution_owner(account.wrapper, acknowledgement=PROVISION_ACK,
                reconciliation_reference="synthetic-offline-rollback-control-not-real-exchange-reconciliation")
            self.assertTrue(result["rearmed"])
            self.assertEqual("armed", json.loads(marker_path.read_bytes())["state"])
            self._artifact("marker-after-explicit-synthetic-rearm.json", marker_path.read_bytes())
            restarted = self.f.new_wrapper(account.wrapper.api_key, account.wrapper.api_secret, account.home, account.venue)
            owner = restarted._ensure_spot_execution_owner()
            self.addCleanup(owner.close)
            self.assertIsNot(owner, original_owner)
            self.assertEqual(2, owner.generation)
            self.assertEqual(account.namespace, namespace_for_owner(restarted))
            self.assertEqual(original_owner.store_id, owner.store_id)
            self.assertEqual(account.path, intents._intent_path(restarted))
            self.assertEqual(full_raw, account.path.read_bytes())
            claimed_marker = marker_path.read_bytes()
            self._artifact("marker-after-fresh-native-owner.json", claimed_marker)
            window, installed = self._load_window(restarted, account.home)
            if expect_blocked:
                self.assertFalse(installed)
                self.assertFalse(window._allocation_snapshot_session.ready)
                self.assertEqual({}, window._entry_allocations)
                self.assertEqual({}, window._open_position_records)
                with self.assertRaises(LiveTradingSafetyError):
                    fills.spot_live_allocation_baseline(self.f.path, symbol="BTCUSDT", namespace=account.namespace)
                with self.assertRaises(LiveTradingSafetyError):
                    restarted._mark_order_intent_portfolio_reconciled(
                        buy["client_order_id"], portfolio_signature=self.product.fill["signature"], portfolio_quantity="0.1",
                    )
            else:
                self.assertTrue(installed)
                self.assertTrue(window._allocation_snapshot_session.ready)
                self.assertEqual(old_payload["entry_allocations"]["BTCUSDT:L"], window._entry_allocations[("BTCUSDT", "L")])
                self.assertEqual(old_payload["open_position_records"]["BTCUSDT:L"], window._open_position_records[("BTCUSDT", "L")])
                self.assertEqual("0.1", fills.spot_live_allocation_baseline(
                    self.f.path, symbol="BTCUSDT", namespace=account.namespace)["quantity"])
            self.assertEqual(full_raw, account.path.read_bytes())
            self.assertEqual(complete, self.f.ledger(account))
            self.assertEqual(claimed_marker, marker_path.read_bytes())
            self.assertEqual(protected, self.backend.store)
            self.assertEqual(puts, self.backend.put_calls)
            self.assertEqual(old, self.f.path.read_bytes())
            self.assertEqual(0, restarted.get_order_intent_status()["unresolved_count"])
            self.assertEqual([], self.f.order_calls)
            self.observed = {
                "source_before_consumption_sha256": self._artifact("inventory-A-before-consumption.json", old),
                "source_after_consumption_sha256": self._artifact("inventory-B-after-consumption.json", current),
                "full_reconciled_history_sha256": self._artifact("full-reconciled-history.json", full_raw),
                "protected_state_sha256": self._artifact("fake-protected-state.json", json.dumps({scope + "/" + account: value for (scope, account), value in protected.items()}, sort_keys=True).encode()),
                "original_generation": original_owner.generation, "fresh_generation": owner.generation,
                "same_uid_store_namespace": account.namespace, "complete_intents": 2, "unresolved_count": 0,
                "source_quantity_before": "0.1", "source_quantity_after_consumption": "0.06",
                "restored_quantity": "0.1", "correlated_maps_installed": installed,
                "correlated_session_ready": window._allocation_snapshot_session.ready,
                "full_history_marker_and_protected_store_unchanged_after_reload": True,
                "order_attempts": 0, "socket_attempts": 0, "native_credential_attempts": 0,
                "rearm_attestation": "Explicit synthetic fixture acknowledgement; not real exchange reconciliation",
                "process_restart": False,
            }

    def test_fresh_same_account_owner_cannot_accept_coherent_consumption_rollback(self):
        self._exercise(expect_blocked=True)


if __name__ == "__main__":
    unittest.main()