"""Offline closed-event classifier controls using actual canonical raw-fill summarizers.

These partial records exercise pure classification only; the owned adapter separately
requires the original fully validated ledger, signed context and held native owner.
"""
from copy import deepcopy
import socket
import unittest
from unittest.mock import patch

import test_spot_fill_recovery_runtime as fixtures
from app.integrations.exchanges.binance.orders import spot_fill_recovery_runtime as fills
from app.integrations.exchanges.binance.orders import spot_inventory_checkpoint_runtime as runtime
from app.integrations.exchanges.binance.orders.spot_allocation_generation_runtime import canonical_spot_buy_metadata
from app.integrations.exchanges.binance.orders.spot_inventory_namespace import make_namespace
from app.settings.live_safety import LiveTradingSafetyError


class SpotInventoryCheckpointEventTests(unittest.TestCase):
    def setUp(self):
        self.enterContext(patch.object(socket, "socket", side_effect=AssertionError("No network in event controls")))
        for name in ("get_secret", "put_secret", "delete_secret"):
            self.enterContext(patch.object(runtime.checkpoints.credential_store, name,
                                          side_effect=AssertionError("No OS credentials in event controls")))
        self.namespace = make_namespace(880001, "11111111-1111-1111-1111-111111111111")
        self.f = fixtures.SpotFillRecoveryTests("runTest")

    def events(self):
        buy = fills.summarize_primary_spot_buy(
            fixtures.PRIMARY_ORDER, symbol="BTCUSDT", client_order_id=fixtures.INTENT["client_order_id"],
            base_asset="BTC", quote_asset="USDT",
        )
        buy_record = {**fixtures.INTENT, "state": "accepted", "exchange_status": "FILLED", "executed_qty": "0.1",
                      "primary_fill_receipt": canonical_spot_buy_metadata(buy)}
        sell = self.f.summarize_sell()
        sell.update(pre_order_portfolio_signature="a" * 64, pre_order_portfolio_qty="1")
        sell_record = {**fixtures.SELL_INTENT, "state": "accepted", "exchange_status": "FILLED", "executed_qty": "0.08",
                       "portfolio_pre_order_signature": "a" * 64, "portfolio_pre_order_qty": "1"}
        record, working, request = self.f.opo_buy_inputs()
        buy_trades = [{"symbol": "BTCUSDT", "id": 601, "orderId": 75, "price": "20000", "qty": "0.1",
                       "quoteQty": "2000", "commission": "0.0001", "commissionAsset": "BTC",
                       "time": 1780000000000, "isBuyer": True}]
        opo_buy = fills.summarize_spot_opo_buy_fill(record, working, buy_trades, base_asset="BTC", quote_asset="USDT")
        stop_record = {**record, "protection_state": "triggered", "list_status": "ALL_DONE", "pending_status": "FILLED",
                       "pending_executed_qty": "0.0999", "entry_reconciled": True, "entry_portfolio_quantity": "0.0999",
                       "entry_recovery_signature": opo_buy["signature"]}
        stop_order = {"symbol": "BTCUSDT", "clientOrderId": request["pendingClientOrderId"], "orderId": 302,
                      "orderListId": 300, "side": "SELL", "type": "STOP_LOSS", "status": "FILLED", "origQty": "0.0999",
                      "executedQty": "0.0999", "stopPrice": "19000", "cummulativeQuoteQty": "1898.1", "updateTime": 1780000000010}
        def trades(order_id, trade_id):
            return [{"symbol": "BTCUSDT", "id": trade_id, "orderId": order_id, "price": "19000", "qty": "0.0999",
                     "quoteQty": "1898.1", "commission": "0", "commissionAsset": "BTC", "time": 1780000000010, "isBuyer": False}]
        stop = fills.summarize_spot_opo_stop_sell_fill(stop_record, stop_order, trades(302, 602), base_asset="BTC", quote_asset="USDT")
        exit_request = {"symbol": "BTCUSDT", "side": "SELL", "type": "MARKET", "cancelReplaceMode": "STOP_ON_FAILURE",
                        "cancelOrderId": 302, "cancelOrigClientOrderId": request["pendingClientOrderId"],
                        "cancelRestrictions": "ONLY_NEW", "quantity": "0.0999", "newClientOrderId": "current-strategy-child",
                        "newOrderRespType": "FULL"}
        exit_record = {**stop_record, "protection_state": "cancelled", "cancel_state": "confirmed", "pending_status": "CANCELED",
                       "strategy_exit_request": exit_request, "strategy_exit_client_order_id": exit_request["newClientOrderId"],
                       "strategy_exit_order_id": 603, "strategy_exit_status": "FILLED", "strategy_exit_executed_qty": "0.0999",
                       "strategy_exit_state": "sell_accepted", "strategy_exit_new_order_accepted": True,
                       "strategy_exit_cancel_confirmed": True, "strategy_exit_pre_order_signature": "b" * 64,
                       "strategy_exit_pre_order_quantity": "0.0999"}
        exit_order = {**stop_order, "clientOrderId": exit_request["newClientOrderId"], "orderId": 603, "orderListId": -1, "type": "MARKET"}
        exit_fill = fills.summarize_spot_opo_strategy_sell_fill(exit_record, exit_order, trades(603, 604), base_asset="BTC", quote_asset="USDT")
        residual_request = {"symbol": "BTCUSDT", "side": "SELL", "type": "STOP_LOSS", "quantity": "0.0999", "stopPrice": "19000",
                            "newClientOrderId": "current-residual-child", "newOrderRespType": "FULL"}
        residual_record = {**exit_record, "residual_stop_request": residual_request, "residual_stop_order_id": 605,
                           "residual_stop_state": "triggered", "residual_stop_query_verified": True, "residual_stop_status": "FILLED",
                           "residual_stop_executed_qty": "0.0999", "residual_stop_pre_order_signature": "c" * 64,
                           "residual_stop_pre_order_quantity": "0.0999"}
        residual_order = {**stop_order, "clientOrderId": residual_request["newClientOrderId"], "orderId": 605, "orderListId": -1}
        residual = fills.summarize_spot_opo_residual_stop_sell_fill(residual_record, residual_order, trades(605, 606), base_asset="BTC", quote_asset="USDT")
        return {"market-buy": (buy_record, buy), "market-sell": (sell_record, sell), "opo-working-buy": (record, opo_buy),
                "opo-original-stop": (stop_record, stop), "opo-strategy-sell": (exit_record, exit_fill),
                "opo-residual-stop": (residual_record, residual)}

    def reject(self, record, fill):
        with self.assertRaises(LiveTradingSafetyError):
            runtime._event_operation(self.namespace, record, fill)

    def test_six_real_summaries_have_distinct_closed_operations_without_mutation(self):
        events = self.events()
        original = deepcopy(events)
        operations = []
        for kind, (record, fill) in events.items():
            with self.subTest(kind=kind):
                self.assertEqual(kind, runtime._event_identity(record, fill)[0])
                operations.append(runtime._event_operation(self.namespace, record, fill))
        self.assertEqual(6, len(set(operations)))
        self.assertEqual(original, events)

    def test_market_sell_requires_exact_original_baseline_even_for_replay(self):
        record, fill = self.events()["market-sell"]
        for changed in ({**fill, "pre_order_portfolio_signature": "d" * 64}, {**fill, "pre_order_portfolio_qty": "2"},
                        {key: value for key, value in fill.items() if key != "pre_order_portfolio_qty"},
                        {**fill, "pre_order_extra": "foreign"}):
            with self.subTest(changed=changed):
                self.reject(record, changed)

    def test_residual_normalized_alias_pair_preserves_original_operation(self):
        record, fill = self.events()["opo-residual-stop"]
        original = deepcopy((record, fill))
        normalized = {**fill, "pre_order_portfolio_signature": fill["residual_stop_pre_order_signature"],
                      "pre_order_portfolio_qty": fill["residual_stop_pre_order_quantity"]}
        operation = runtime._event_operation(self.namespace, record, fill)
        self.assertEqual(operation, runtime._event_operation(self.namespace, record, normalized))
        self.assertEqual(runtime.inventory_publication_operation_hash(self.namespace, record, fill),
                         runtime.inventory_publication_operation_hash(self.namespace, record, normalized))
        self.assertEqual(original, (record, fill))

    def test_residual_normalized_aliases_require_complete_exact_original_baseline(self):
        record, fill = self.events()["opo-residual-stop"]
        normalized = {**fill, "pre_order_portfolio_signature": fill["residual_stop_pre_order_signature"],
                      "pre_order_portfolio_qty": fill["residual_stop_pre_order_quantity"]}
        invalid = [{key: value for key, value in normalized.items() if key != missing}
                   for missing in ("pre_order_portfolio_signature", "pre_order_portfolio_qty")]
        invalid += [{**normalized, **change} for change in (
            {"pre_order_portfolio_signature": "d" * 64}, {"pre_order_portfolio_qty": "0.2"},
            {"pre_order_portfolio_qty": True}, {"pre_order_extra": "foreign"},
            {"residual_stop_pre_order_signature": "d" * 64}, {"residual_stop_pre_order_quantity": "0.2"},
        )]
        original = deepcopy((record, fill))
        for changed in invalid:
            with self.subTest(changed=changed):
                self.reject(record, changed)
                self.assertEqual(original, (record, fill))
        self.reject({**record, "residual_stop_pre_order_signature": "d" * 64}, normalized)
        self.reject({**record, "residual_stop_pre_order_quantity": "0.2"}, normalized)

    def test_historical_child_membership_never_replaces_current_child_or_order(self):
        for kind, (record, fill) in self.events().items():
            with self.subTest(kind=kind):
                self.reject({**record, "historical_reserved_ids": ["historical-child"]}, {**fill, "exchange_client_order_id": "historical-child"})
                self.reject(record, {**fill, "order_id": 999999})
                self.reject(record, {**fill, "opo_list_client_order_id": "foreign-parent"})

    def test_unknown_requires_existing_explicit_positive_terminal_contract(self):
        for kind, (record, fill) in self.events().items():
            with self.subTest(kind=kind):
                changed = {**record, "state": "unknown"}
                if kind == "opo-residual-stop":
                    self.reject(changed, fill)
                else:
                    self.assertEqual(kind, runtime._event_identity(changed, fill)[0])
                self.reject({**record, "state": "prepared"}, fill)
        record, fill = self.events()["market-sell"]
        self.reject({**record, "state": "unknown", "exchange_status": "NEW"}, fill)
        self.reject({**record, "state": "unknown", "executed_qty": "0"}, fill)
        record, fill = self.events()["opo-strategy-sell"]
        self.reject({**record, "state": "unknown", "strategy_exit_new_order_accepted": False}, fill)
        self.reject({**record, "strategy_exit_status": "NEW", "strategy_exit_executed_qty": "0"}, fill)
        record, fill = self.events()["opo-residual-stop"]
        self.reject({**record, "residual_stop_query_verified": False}, fill)
        self.reject({**record, "residual_stop_status": "NEW", "residual_stop_executed_qty": "0"}, fill)

    def test_child_requests_remain_linked_to_original_cancel_and_stop(self):
        record, fill = self.events()["opo-strategy-sell"]
        for fields in ({"cancelOrderId": 999}, {"cancelOrigClientOrderId": "foreign-stop"}, {"quantity": "0.2"}):
            with self.subTest(fields=fields):
                self.reject({**record, "strategy_exit_request": {**record["strategy_exit_request"], **fields}}, fill)
        record, fill = self.events()["opo-residual-stop"]
        self.reject({**record, "residual_stop_request": {**record["residual_stop_request"], "stopPrice": "18000"}}, fill)

    def test_cross_kind_provenance_and_invalid_fees_trade_ids_or_side_are_rejected(self):
        for kind, (record, fill) in self.events().items():
            for change in ({"side": "SELL" if fill.get("side", "BUY") == "BUY" else "BUY"}, {"trade_ids": [True]},
                           {"commissions": [{"asset": "BNB", "amount": "0.1"}]}, {"net_qty": "9"},
                           {"entry_unrecognized_proof": "foreign"}):
                with self.subTest(kind=kind, change=change):
                    self.reject(record, {**fill, **change})
        record, fill = self.events()["opo-original-stop"]
        self.reject({**record, "entry_recovery_signature": None}, {**fill, "entry_recovery_signature": None})
        self.reject({**record, "exchange_order_list_id": 1}, {**fill, "opo_order_list_id": True})
        self.reject({**record, "working_order_id": 1}, {**fill, "entry_working_order_id": True})

    def test_hash_ignores_mutable_record_clocks_and_credential_generation_but_binds_execution(self):
        for kind, (record, fill) in self.events().items():
            with self.subTest(kind=kind):
                operation = runtime._event_operation(self.namespace, record, fill)
                changed = {**record, "updated_at": "later", "reconciled_at": "later", "credential_fingerprint": "rotated",
                           "owner_generation": 9, "backend_generation": 2, "operator_note": "presentation"}
                self.assertEqual(operation, runtime._event_operation(self.namespace, changed, fill))
                if kind == "market-buy":
                    self.reject(record, {**fill, "signature": "f" * 64})
                else:
                    self.assertNotEqual(operation, runtime._event_operation(self.namespace, record, {**fill, "signature": "f" * 64}))
        record, fill = self.events()["market-sell"]
        self.assertEqual(runtime._event_operation(self.namespace, record, fill),
                         runtime._event_operation(self.namespace, record, {**fill, "fill_time_ms": fill["fill_time_ms"] + 100}))
        record, fill = self.events()["market-buy"]
        self.reject(record, {**fill, "fill_time_ms": fill["fill_time_ms"] + 100})

    def test_namespace_and_exact_protected_hash_are_bound(self):
        record, fill = self.events()["market-sell"]
        operation = runtime._event_operation(self.namespace, record, fill)
        self.assertEqual(runtime.checkpoints._operation(operation), runtime.inventory_publication_operation_hash(self.namespace, record, fill))
        self.assertNotEqual(operation, runtime._event_operation(make_namespace(880002, "11111111-1111-1111-1111-111111111111"), record, fill))
        self.assertNotEqual(operation, runtime._event_operation(make_namespace(880001, "22222222-2222-2222-2222-222222222222"), record, fill))
