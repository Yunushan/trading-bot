from __future__ import annotations

import json
import tempfile
import unittest
from decimal import Decimal
from pathlib import Path
from unittest.mock import patch

from app.integrations.exchanges.binance.orders import spot_fill_recovery_runtime as recovery
from app.integrations.exchanges.binance.orders.spot_opo_runtime import build_spot_opo_request
from app.settings.live_safety import LiveTradingSafetyError


INTENT = {
    "client_order_id": "recovered-buy-1",
    "exchange_order_id": "75",
    "market": "spot",
    "type": "MARKET",
    "side": "BUY",
    "symbol": "BTCUSDT",
}
ORDER = {
    "clientOrderId": "recovered-buy-1",
    "symbol": "BTCUSDT",
    "side": "BUY",
    "type": "MARKET",
    "orderId": 75,
    "status": "FILLED",
    "executedQty": "0.10000000",
    "cummulativeQuoteQty": "2000.00000000",
    "updateTime": 1780000000000,
}
TRADES = [
    {
        "symbol": "BTCUSDT", "id": 101, "orderId": 75,
        "price": "20000.00000000", "qty": "0.04000000", "quoteQty": "800.00000000",
        "commission": "0.00004000", "commissionAsset": "BTC", "time": 1780000000000,
        "isBuyer": True,
    },
    {
        "symbol": "BTCUSDT", "id": 102, "orderId": 75,
        "price": "20000.00000000", "qty": "0.06000000", "quoteQty": "1200.00000000",
        "commission": "0.20000000", "commissionAsset": "USDT", "time": 1780000000001,
        "isBuyer": True,
    },
]
PRIMARY_ORDER = {
    **ORDER,
    "fills": [
        {
            "tradeId": 101, "price": "20000.00000000", "qty": "0.04000000",
            "commission": "0.00004000", "commissionAsset": "BTC",
        },
        {
            "tradeId": 102, "price": "20000.00000000", "qty": "0.06000000",
            "commission": "0.20000000", "commissionAsset": "USDT",
        },
    ],
}
SELL_INTENT = {
    "client_order_id": "recovered-sell-1",
    "exchange_order_id": "76",
    "market": "spot",
    "type": "MARKET",
    "side": "SELL",
    "symbol": "BTCUSDT",
}
SELL_ORDER = {
    "clientOrderId": "recovered-sell-1",
    "symbol": "BTCUSDT",
    "side": "SELL",
    "type": "MARKET",
    "orderId": 76,
    "status": "FILLED",
    "executedQty": "0.08000000",
    "cummulativeQuoteQty": "1600.00000000",
    "updateTime": 1780000000010,
}
SELL_TRADES = [
    {
        "symbol": "BTCUSDT", "id": 201, "orderId": 76,
        "price": "20000.00000000", "qty": "0.03000000", "quoteQty": "600.00000000",
        "commission": "0.00003000", "commissionAsset": "BTC", "time": 1780000000010,
        "isBuyer": False,
    },
    {
        "symbol": "BTCUSDT", "id": 202, "orderId": 76,
        "price": "20000.00000000", "qty": "0.05000000", "quoteQty": "1000.00000000",
        "commission": "0.20000000", "commissionAsset": "USDT", "time": 1780000000011,
        "isBuyer": False,
    },
]


class SpotFillRecoveryTests(unittest.TestCase):
    def summarize(self):
        return recovery.summarize_spot_market_fill(
            INTENT, ORDER, TRADES, base_asset="BTC", quote_asset="USDT",
        )

    def summarize_sell(self, *, intent=SELL_INTENT, order=SELL_ORDER, trades=SELL_TRADES):
        return recovery.summarize_spot_market_fill(
            intent, order, trades, base_asset="BTC", quote_asset="USDT",
        )

    def opo_buy_inputs(self):
        request = build_spot_opo_request(
            symbol="BTCUSDT",
            symbol_info={
                "symbol": "BTCUSDT", "status": "TRADING", "quoteAsset": "USDT",
                "isSpotTradingAllowed": True, "otoAllowed": True, "opoAllowed": True,
                "filters": [
                    {"filterType": "PRICE_FILTER", "minPrice": "0.01", "maxPrice": "1000000", "tickSize": "0.01"},
                    {"filterType": "LOT_SIZE", "minQty": "0.0001", "maxQty": "9000", "stepSize": "0.0001"},
                    {"filterType": "MIN_NOTIONAL", "minNotional": "5"},
                ],
            },
            working_price="20000", working_quantity="0.1", pending_stop_price="19000",
            list_client_order_id="opo-list-1", working_client_order_id="opo-buy-1",
            pending_client_order_id="opo-stop-1",
        )
        intent = {
            "market": "spot", "type": "OPO", "side": "BUY", "symbol": "BTCUSDT",
            "client_order_id": request["listClientOrderId"], "request": request,
            "state": "accepted", "protection_state": "active", "list_status": "EXEC_STARTED",
            "working_status": "FILLED", "pending_status": "NEW", "exchange_order_list_id": 300,
            "working_order_id": 75, "pending_order_id": 302,
            "working_executed_qty": "0.1", "pending_executed_qty": "0",
            "pending_original_qty": "0.0999",
        }
        order = {
            **ORDER, "clientOrderId": request["workingClientOrderId"], "type": "LIMIT",
            "orderListId": 300, "timeInForce": "FOK", "origQty": "0.1",
        }
        return intent, order, request

    @staticmethod
    def buy_fill(client_order_id, order_id, qty, quote):
        return {
            "symbol": "BTCUSDT",
            "client_order_id": client_order_id,
            "order_id": order_id,
            "trade_ids": [order_id],
            "trade_count": 1,
            "gross_qty": qty,
            "net_qty": qty,
            "gross_quote_qty": quote,
            "net_quote_cost": quote,
            "average_cost": str(float(quote) / float(qty)),
            "commissions": [],
            "base_asset": "BTC",
            "quote_asset": "USDT",
            "fill_time_ms": 1780000000000 + order_id,
            "signature": f"{order_id:064x}",
        }

    def test_primary_ack_and_my_trades_produce_the_same_fee_aware_proof(self):
        recovered = self.summarize()
        primary = recovery.summarize_primary_spot_buy(
            PRIMARY_ORDER,
            symbol="BTCUSDT",
            client_order_id="recovered-buy-1",
            base_asset="BTC",
            quote_asset="USDT",
        )

        self.assertEqual("0.09996", recovered["net_qty"])
        self.assertEqual("2000.2", recovered["net_quote_cost"])
        self.assertEqual(recovered["signature"], primary["signature"])
        self.assertEqual(recovered["commissions"], primary["commissions"])

    def test_exact_order_totals_and_trade_identity_are_required(self):
        bad_order = {**ORDER, "executedQty": "0.09"}
        with self.assertRaisesRegex(LiveTradingSafetyError, "totals do not match"):
            recovery.summarize_spot_market_fill(
                INTENT, bad_order, TRADES, base_asset="BTC", quote_asset="USDT",
            )

        bad_trade = [dict(row) for row in TRADES]
        bad_trade[0]["orderId"] = 76
        with self.assertRaisesRegex(LiveTradingSafetyError, "does not belong"):
            recovery.summarize_spot_market_fill(
                INTENT, ORDER, bad_trade, base_asset="BTC", quote_asset="USDT",
            )

    def test_unvalued_third_asset_fees_and_non_usdt_quotes_stay_blocked(self):
        third_asset_fee = [dict(row) for row in TRADES]
        third_asset_fee[0]["commissionAsset"] = "BNB"
        with self.assertRaisesRegex(LiveTradingSafetyError, "third-asset"):
            recovery.summarize_spot_market_fill(
                INTENT, ORDER, third_asset_fee, base_asset="BTC", quote_asset="USDT",
            )
        with self.assertRaisesRegex(LiveTradingSafetyError, "USDT-quoted"):
            recovery.summarize_spot_market_fill(
                INTENT, ORDER, TRADES, base_asset="BTC", quote_asset="BUSD",
            )

    def test_sell_summary_counts_base_fee_as_inventory_and_quote_fee_against_proceeds(self):
        fill = self.summarize_sell()
        self.assertEqual("SELL", fill["side"])
        self.assertEqual("0.08003", fill["portfolio_qty"])
        self.assertEqual("1599.8", fill["net_quote_proceeds"])
        self.assertNotEqual(self.summarize()["signature"], fill["signature"])

        wrong_side_trade = [dict(row) for row in SELL_TRADES]
        wrong_side_trade[0]["isBuyer"] = True
        with self.assertRaisesRegex(LiveTradingSafetyError, "does not belong"):
            self.summarize_sell(trades=wrong_side_trade)

    def test_opo_buy_recovery_binds_list_and_working_child_and_records_linked_stop_quantity(self):
        intent, order, request = self.opo_buy_inputs()

        fill = recovery.summarize_spot_opo_buy_fill(
            intent, order, TRADES, base_asset="BTC", quote_asset="USDT",
        )

        self.assertEqual(request["listClientOrderId"], fill["client_order_id"])
        self.assertEqual(request["workingClientOrderId"], fill["exchange_client_order_id"])
        self.assertEqual("0.09996", fill["net_qty"])
        self.assertEqual("0.0999", fill["pending_order_qty"])
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "allocations.json"
            recovery.persist_spot_buy_allocation(path, fill)
            entry = json.loads(path.read_text(encoding="utf-8"))["entry_allocations"]["BTCUSDT:L"][0]
        self.assertEqual(request["listClientOrderId"], entry["client_order_id"])
        self.assertEqual(request["workingClientOrderId"], entry["spot_fill_recovery"]["exchange_client_order_id"])
        self.assertEqual("0.0999", entry["spot_fill_recovery"]["pending_order_qty"])

    def test_opo_buy_recovery_proves_inventory_independently_of_stop_state(self):
        intent, order, _request = self.opo_buy_inputs()
        triggered = {
            **intent, "state": "accepted", "protection_state": "triggered",
            "list_status": "ALL_DONE", "pending_status": "FILLED", "pending_executed_qty": "0.0999",
        }
        fill = recovery.summarize_spot_opo_buy_fill(
            triggered, order, TRADES, base_asset="BTC", quote_asset="USDT",
        )
        self.assertEqual("0.09996", fill["net_qty"])
        with self.assertRaisesRegex(LiveTradingSafetyError, "exact filled working child"):
            recovery.summarize_spot_opo_buy_fill(
                {**intent, "working_status": "PARTIALLY_FILLED"}, order, TRADES,
                base_asset="BTC", quote_asset="USDT",
            )
        with self.assertRaisesRegex(LiveTradingSafetyError, "conflicts with its reconciled list fill"):
            recovery.summarize_spot_opo_buy_fill(
                intent, {**order, "orderListId": 301}, TRADES,
                base_asset="BTC", quote_asset="USDT",
            )

    def test_opo_stop_sell_recovery_requires_full_exact_linked_exit(self):
        intent, _working_order, request = self.opo_buy_inputs()
        intent.update({
            "state": "accepted", "protection_state": "triggered", "list_status": "ALL_DONE",
            "pending_status": "FILLED", "pending_executed_qty": "0.0999",
            "entry_reconciled": True, "entry_portfolio_quantity": "0.0999",
            "entry_recovery_signature": "a" * 64,
        })
        order = {
            "symbol": "BTCUSDT", "orderId": 302, "orderListId": 300,
            "clientOrderId": request["pendingClientOrderId"], "side": "SELL", "type": "STOP_LOSS",
            "status": "FILLED", "origQty": "0.0999", "executedQty": "0.0999",
            "stopPrice": "19000", "cummulativeQuoteQty": "1898.1", "updateTime": 1780000000010,
        }
        trades = [{
            "symbol": "BTCUSDT", "id": 303, "orderId": 302, "price": "19000",
            "qty": "0.0999", "quoteQty": "1898.1", "commission": "0", "commissionAsset": "BTC",
            "time": 1780000000010, "isBuyer": False,
        }]
        fill = recovery.summarize_spot_opo_stop_sell_fill(
            intent, order, trades, base_asset="BTC", quote_asset="USDT",
        )
        self.assertEqual(request["listClientOrderId"], fill["opo_list_client_order_id"])
        self.assertEqual("0.0999", fill["portfolio_qty"])

        with self.assertRaisesRegex(LiveTradingSafetyError, "exact linked entry proof"):
            recovery.summarize_spot_opo_stop_sell_fill(
                intent, {**order, "executedQty": "0.0998"}, trades,
                base_asset="BTC", quote_asset="USDT",
            )
        charged_base_fee = [{**trades[0], "commission": "0.0001", "commissionAsset": "BTC"}]
        with self.assertRaisesRegex(LiveTradingSafetyError, "consumed quantity differs"):
            recovery.summarize_spot_opo_stop_sell_fill(
                intent, order, charged_base_fee, base_asset="BTC", quote_asset="USDT",
            )

    def test_opo_stop_sell_closes_only_its_exact_entry_allocation_and_is_idempotent(self):
        intent, working_order, request = self.opo_buy_inputs()
        buy_trades = [{
            "symbol": "BTCUSDT", "id": 301, "orderId": 75, "price": "20000",
            "qty": "0.1", "quoteQty": "2000", "commission": "0.0001", "commissionAsset": "BTC",
            "time": 1780000000000, "isBuyer": True,
        }]
        buy_fill = recovery.summarize_spot_opo_buy_fill(
            intent, working_order, buy_trades, base_asset="BTC", quote_asset="USDT",
        )
        triggered = {
            **intent, "state": "accepted", "protection_state": "triggered", "list_status": "ALL_DONE",
            "pending_status": "FILLED", "pending_executed_qty": "0.0999",
            "entry_reconciled": True, "entry_portfolio_quantity": "0.0999",
            "entry_recovery_signature": buy_fill["signature"],
        }
        stop_order = {
            "symbol": "BTCUSDT", "orderId": 302, "orderListId": 300,
            "clientOrderId": request["pendingClientOrderId"], "side": "SELL", "type": "STOP_LOSS",
            "status": "FILLED", "origQty": "0.0999", "executedQty": "0.0999",
            "stopPrice": "19000", "cummulativeQuoteQty": "1898.1", "updateTime": 1780000000010,
        }
        stop_trades = [{
            "symbol": "BTCUSDT", "id": 303, "orderId": 302, "price": "19000",
            "qty": "0.0999", "quoteQty": "1898.1", "commission": "0", "commissionAsset": "BTC",
            "time": 1780000000010, "isBuyer": False,
        }]
        stop_fill = recovery.summarize_spot_opo_stop_sell_fill(
            triggered, stop_order, stop_trades, base_asset="BTC", quote_asset="USDT",
        )
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "allocations.json"
            recovery.persist_spot_buy_allocation(path, buy_fill)
            recovery.persist_spot_opo_stop_sell_allocation(path, stop_fill)
            first = json.loads(path.read_text(encoding="utf-8"))
            recovery.persist_spot_opo_stop_sell_allocation(path, stop_fill)
            second = json.loads(path.read_text(encoding="utf-8"))
        row = second["entry_allocations"]["BTCUSDT:L"][0]
        self.assertEqual("Closed", row["status"])
        self.assertEqual(stop_fill["signature"], row["spot_opo_stop_recovery"]["signature"])
        self.assertNotIn("BTCUSDT:L", second["open_position_records"])
        self.assertEqual(first["entry_allocations"], second["entry_allocations"])

    def test_strategy_sell_consumes_only_the_sole_exact_opo_allocation(self):
        intent, working_order, request = self.opo_buy_inputs()
        buy_trades = [{
            "symbol": "BTCUSDT", "id": 401, "orderId": 75, "price": "20000",
            "qty": "0.1", "quoteQty": "2000", "commission": "0.0001", "commissionAsset": "BTC",
            "time": 1780000000000, "isBuyer": True,
        }]
        buy_fill = recovery.summarize_spot_opo_buy_fill(
            intent, working_order, buy_trades, base_asset="BTC", quote_asset="USDT",
        )
        exit_order = {
            "symbol": "BTCUSDT", "clientOrderId": "strategy-exit-1", "orderId": 402,
            "orderListId": -1, "side": "SELL", "type": "MARKET", "status": "FILLED",
            "origQty": "0.0999", "executedQty": "0.0999", "cummulativeQuoteQty": "1898.1",
            "updateTime": 1780000000010,
        }
        exit_trades = [{
            "symbol": "BTCUSDT", "id": 403, "orderId": 402, "price": "19000",
            "qty": "0.0999", "quoteQty": "1898.1", "commission": "0", "commissionAsset": "BTC",
            "time": 1780000000010, "isBuyer": False,
        }]
        sell_intent = {
            "market": "spot", "type": "MARKET", "side": "SELL", "symbol": "BTCUSDT",
            "client_order_id": "strategy-exit-1", "exchange_client_order_id": "strategy-exit-1",
            "exchange_order_id": 402,
        }
        fill = recovery.summarize_spot_market_fill(
            sell_intent, exit_order, exit_trades, base_asset="BTC", quote_asset="USDT",
        )
        fill["type"] = "MARKET"
        fill["opo_list_client_order_id"] = request["listClientOrderId"]
        fill["opo_entry_portfolio_quantity"] = "0.0999"
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "allocations.json"
            recovery.persist_spot_buy_allocation(path, buy_fill)
            baseline = recovery.spot_opo_allocation_baseline(
                path,
                symbol="BTCUSDT",
                list_client_order_id=request["listClientOrderId"],
                expected_quantity="0.0999",
            )
            fill["pre_order_portfolio_signature"] = baseline["signature"]
            fill["pre_order_portfolio_qty"] = baseline["quantity"]
            self.assertTrue(recovery.persist_spot_opo_strategy_sell_allocation(path, fill))
            self.assertTrue(recovery.persist_spot_opo_strategy_sell_allocation(path, fill))
            proof_intent = {
                "client_order_id": request["listClientOrderId"],
                "strategy_exit_client_order_id": "strategy-exit-1",
                "strategy_exit_order_id": 402,
                "strategy_exit_trade_ids": [403],
                "strategy_exit_pre_order_signature": baseline["signature"],
                "strategy_exit_pre_order_quantity": baseline["quantity"],
            }
            self.assertTrue(recovery.has_durable_spot_opo_strategy_sell(
                path, proof_intent, signature=str(fill["signature"]), consumed_quantity="0.0999",
            ))
            saved = json.loads(path.read_text(encoding="utf-8"))

        row = saved["entry_allocations"]["BTCUSDT:L"][0]
        self.assertEqual("Closed", row["status"])
        self.assertEqual("strategy-exit-1", row["spot_sell_recoveries"][0]["client_order_id"])
        self.assertNotIn("BTCUSDT:L", saved["open_position_records"])

    def full_size_residual_stop_inputs(self, path):
        intent, working_order, request = self.opo_buy_inputs()
        buy_trades = [{
            "symbol": "BTCUSDT", "id": 601, "orderId": 75, "price": "20000",
            "qty": "0.1", "quoteQty": "2000", "commission": "0.0001", "commissionAsset": "BTC",
            "time": 1780000000000, "isBuyer": True,
        }]
        buy_fill = recovery.summarize_spot_opo_buy_fill(
            intent, working_order, buy_trades, base_asset="BTC", quote_asset="USDT",
        )
        recovery.persist_spot_buy_allocation(path, buy_fill)
        baseline = recovery.spot_opo_allocation_baseline(
            path, symbol="BTCUSDT", list_client_order_id=request["listClientOrderId"],
            expected_quantity="0.0999",
        )
        residual_request = {
            "symbol": "BTCUSDT", "side": "SELL", "type": "STOP_LOSS",
            "quantity": baseline["quantity"], "stopPrice": "19000",
            "newClientOrderId": "residual-full-stop-1", "newOrderRespType": "FULL",
        }
        intent.update({
            "protection_state": "cancelled", "cancel_state": "confirmed",
            "list_status": "ALL_DONE", "pending_status": "CANCELED",
            "entry_reconciled": True, "entry_portfolio_quantity": baseline["quantity"],
            "entry_recovery_signature": buy_fill["signature"],
            "strategy_exit_state": "stop_cancelled",
            "strategy_exit_outcome": "stop_canceled_exit_rejected",
            "strategy_exit_new_order_accepted": False,
            "residual_rearm_no_fill": True,
            "residual_stop_state": "triggered", "residual_stop_query_verified": True,
            "residual_stop_request": residual_request, "residual_stop_order_id": 602,
            "residual_stop_status": "FILLED", "residual_stop_executed_qty": baseline["quantity"],
            "residual_stop_pre_order_quantity": baseline["quantity"],
            "residual_stop_pre_order_signature": baseline["signature"],
        })
        order = {
            "symbol": "BTCUSDT", "clientOrderId": residual_request["newClientOrderId"],
            "orderId": 602, "orderListId": -1, "side": "SELL", "type": "STOP_LOSS",
            "status": "FILLED", "origQty": baseline["quantity"], "executedQty": baseline["quantity"],
            "stopPrice": "19000", "cummulativeQuoteQty": "1898.1", "updateTime": 1780000000010,
        }
        trades = [{
            "symbol": "BTCUSDT", "id": 603, "orderId": 602, "price": "19000",
            "qty": baseline["quantity"], "quoteQty": "1898.1", "commission": "0", "commissionAsset": "BTC",
            "time": 1780000000010, "isBuyer": False,
        }]
        return intent, order, trades

    def test_full_size_rearmed_stop_after_rejected_linked_sell_closes_exact_allocation(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "allocations.json"
            intent, order, trades = self.full_size_residual_stop_inputs(path)
            fill = recovery.summarize_spot_opo_residual_stop_sell_fill(
                intent, order, trades, base_asset="BTC", quote_asset="USDT",
            )
            self.assertEqual("0.0999", fill["portfolio_qty"])
            self.assertTrue(recovery.persist_spot_opo_residual_stop_allocation(path, fill))
            first = path.read_bytes()
            # Reopening the durable snapshot must recognize the same stop fill.
            self.assertTrue(recovery.persist_spot_opo_residual_stop_allocation(path, fill))
            self.assertEqual(first, path.read_bytes())
            self.assertTrue(recovery.has_durable_spot_opo_residual_stop_allocation(
                path, intent, signature=str(fill["signature"]), consumed_quantity="0.0999",
                remaining_quantity="0", trade_ids=[603],
            ))
            saved = json.loads(path.read_text(encoding="utf-8"))
        row = saved["entry_allocations"]["BTCUSDT:L"][0]
        self.assertEqual("Closed", row["status"])
        self.assertEqual("residual-full-stop-1", row["spot_sell_recoveries"][0]["client_order_id"])
        self.assertNotIn("BTCUSDT:L", saved["open_position_records"])

    def test_rearmed_stop_baseline_above_entry_is_rejected_before_allocation_changes(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "allocations.json"
            intent, order, trades = self.full_size_residual_stop_inputs(path)
            original = path.read_bytes()
            with self.assertRaisesRegex(LiveTradingSafetyError, "exact terminal protected remainder"):
                recovery.summarize_spot_opo_residual_stop_sell_fill(
                    {**intent, "entry_portfolio_quantity": "0.0998"}, order, trades,
                    base_asset="BTC", quote_asset="USDT",
                )
            fill = recovery.summarize_spot_opo_residual_stop_sell_fill(
                intent, order, trades, base_asset="BTC", quote_asset="USDT",
            )
            with self.assertRaisesRegex(LiveTradingSafetyError, "exceeds its exact OPO remainder"):
                recovery.persist_spot_opo_residual_stop_allocation(
                    path, {**fill, "opo_entry_portfolio_quantity": "0.0998"},
                )
            self.assertEqual(original, path.read_bytes())

    def test_strategy_sell_baseline_rejects_other_active_same_symbol_allocation(self):
        intent, working_order, request = self.opo_buy_inputs()
        buy_trades = [{
            "symbol": "BTCUSDT", "id": 501, "orderId": 75, "price": "20000",
            "qty": "0.1", "quoteQty": "2000", "commission": "0.0001", "commissionAsset": "BTC",
            "time": 1780000000000, "isBuyer": True,
        }]
        buy_fill = recovery.summarize_spot_opo_buy_fill(
            intent, working_order, buy_trades, base_asset="BTC", quote_asset="USDT",
        )
        other = self.buy_fill("other-spot-allocation", 502, "0.01", "200")
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "allocations.json"
            recovery.persist_spot_buy_allocation(path, buy_fill)
            recovery.persist_spot_buy_allocation(path, other)
            with self.assertRaisesRegex(LiveTradingSafetyError, "only active allocation"):
                recovery.spot_opo_allocation_baseline(
                    path,
                    symbol="BTCUSDT",
                    list_client_order_id=request["listClientOrderId"],
                    expected_quantity="0.0999",
                )

    def test_sell_recovery_consumes_fifo_allocations_and_is_idempotent(self):
        first = self.buy_fill("recovered-buy-a", 501, "0.06", "1200")
        second = self.buy_fill("recovered-buy-b", 502, "0.04", "800")
        fill = self.summarize_sell()
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / ".trading_bot_allocations.json"
            self.assertTrue(recovery.persist_spot_buy_allocation(path, first))
            self.assertTrue(recovery.persist_spot_buy_allocation(path, second))
            baseline = recovery.spot_live_allocation_baseline(path, symbol="BTCUSDT")
            self.assertIsNotNone(baseline)
            fill = {
                **fill,
                "pre_order_portfolio_signature": baseline["signature"],
                "pre_order_portfolio_qty": baseline["quantity"],
            }

            self.assertTrue(recovery.persist_spot_sell_allocation(path, fill))
            after_first = json.loads(path.read_text(encoding="utf-8"))
            self.assertTrue(recovery.persist_spot_sell_allocation(path, fill))
            after_retry = json.loads(path.read_text(encoding="utf-8"))

        rows = after_retry["entry_allocations"]["BTCUSDT:L"]
        self.assertEqual(["Closed", "Active"], [row["status"] for row in rows])
        self.assertAlmostEqual(0.01997, rows[1]["qty"])
        self.assertEqual("0.08003", sum(
            (Decimal(proof["consumed_qty"]) for row in rows for proof in row.get("spot_sell_recoveries", [])),
            start=Decimal(0),
        ).__str__())
        self.assertAlmostEqual(0.01997, after_retry["open_position_records"]["BTCUSDT:L"]["data"]["qty"])
        self.assertEqual(after_first["entry_allocations"], after_retry["entry_allocations"])

    def test_original_buy_replays_do_not_restore_consumed_or_closed_generations(self):
        first = self.buy_fill("recovered-buy-a", 501, "0.06", "1200")
        second = self.buy_fill("recovered-buy-b", 502, "0.04", "800")
        first["fill_time_ms"] = second["fill_time_ms"] = 1780000000000
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "allocations.json"
            recovery.persist_spot_buy_allocation(path, first)
            recovery.persist_spot_buy_allocation(path, second)
            baseline = recovery.spot_live_allocation_baseline(path, symbol="BTCUSDT")
            sell = {**self.summarize_sell(), "pre_order_portfolio_signature": baseline["signature"],
                    "pre_order_portfolio_qty": baseline["quantity"]}
            recovery.persist_spot_sell_allocation(path, sell)
            consumed = path.read_bytes()
            for original in (first, second):
                self.assertTrue(recovery.persist_spot_buy_allocation(path, original))
                self.assertEqual(consumed, path.read_bytes())
            next_fill = self.buy_fill("recovered-buy-c", 503, "0.01", "200")
            recovery.persist_spot_buy_allocation(path, next_fill)
            generation_two = path.read_bytes()
            for original in (first, second):
                self.assertTrue(recovery.persist_spot_buy_allocation(path, original))
                self.assertEqual(generation_two, path.read_bytes())
            data = json.loads(generation_two)
            self.assertEqual(["Closed", "Active", "Active"], [row["status"] for row in data["entry_allocations"]["BTCUSDT:L"]])
            self.assertEqual(["recovered-buy-b", "recovered-buy-c"],
                             [row["client_order_id"] for row in data["open_position_records"]["BTCUSDT:L"]["allocations"]])

    def test_buy_replay_rejects_corrupted_consumption_without_rewriting(self):
        first = self.buy_fill("recovered-buy-a", 501, "0.1", "2000")
        first["fill_time_ms"] = 1780000000000
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "allocations.json"
            recovery.persist_spot_buy_allocation(path, first)
            baseline = recovery.spot_live_allocation_baseline(path, symbol="BTCUSDT")
            sell = {**self.summarize_sell(), "pre_order_portfolio_signature": baseline["signature"],
                    "pre_order_portfolio_qty": baseline["quantity"]}
            recovery.persist_spot_sell_allocation(path, sell)
            data = json.loads(path.read_text())
            data["entry_allocations"]["BTCUSDT:L"][0]["qty"] = 0.1
            path.write_text(json.dumps(data))
            corrupt = path.read_bytes()
            with self.assertRaisesRegex(LiveTradingSafetyError, "does not conserve"):
                recovery.persist_spot_buy_allocation(path, first)
            self.assertEqual(corrupt, path.read_bytes())

    def test_sell_recovery_rejects_inventory_exceeding_durable_owned_allocations(self):
        fill = self.summarize_sell(
            order={**SELL_ORDER, "executedQty": "0.10000000", "cummulativeQuoteQty": "2000.00000000"},
            trades=[{
                **SELL_TRADES[0], "id": 203, "qty": "0.10000000", "quoteQty": "2000.00000000",
                "commission": "0.00010000", "time": 1780000000012,
            }],
        )
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / ".trading_bot_allocations.json"
            self.assertTrue(recovery.persist_spot_buy_allocation(
                path, self.buy_fill("recovered-buy-a", 501, "0.1", "2000"),
            ))
            baseline = recovery.spot_live_allocation_baseline(path, symbol="BTCUSDT")
            self.assertIsNotNone(baseline)
            fill["pre_order_portfolio_signature"] = baseline["signature"]
            fill["pre_order_portfolio_qty"] = baseline["quantity"]
            with self.assertRaisesRegex(LiveTradingSafetyError, "exceeds durable owned allocation"):
                recovery.persist_spot_sell_allocation(path, fill)

    def test_sell_recovery_blocks_when_portfolio_changed_after_intent_baseline(self):
        first = self.buy_fill("recovered-buy-a", 501, "0.1", "2000")
        second = self.buy_fill("recovered-buy-b", 502, "0.01", "200")
        fill = self.summarize_sell()
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / ".trading_bot_allocations.json"
            recovery.persist_spot_buy_allocation(path, first)
            baseline = recovery.spot_live_allocation_baseline(path, symbol="BTCUSDT")
            self.assertIsNotNone(baseline)
            fill["pre_order_portfolio_signature"] = baseline["signature"]
            fill["pre_order_portfolio_qty"] = baseline["quantity"]
            recovery.persist_spot_buy_allocation(path, second)

            with self.assertRaisesRegex(LiveTradingSafetyError, "changed after intent creation"):
                recovery.persist_spot_sell_allocation(path, fill)

    def test_recovery_is_idempotent_and_updates_a_live_desktop_snapshot(self):
        fill = self.summarize()
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / ".trading_bot_allocations.json"
            path.write_text(json.dumps({
                "version": 1,
                "mode": "Live",
                "timestamp": 1780000000,
                "entry_allocations": {},
                "open_position_records": {},
            }), encoding="utf-8")

            self.assertTrue(recovery.persist_spot_buy_allocation(path, fill))
            first = json.loads(path.read_text(encoding="utf-8"))
            self.assertTrue(recovery.persist_spot_buy_allocation(path, fill))
            second = json.loads(path.read_text(encoding="utf-8"))

            entries = second["entry_allocations"]["BTCUSDT:L"]
            self.assertEqual(1, len(entries))
            self.assertEqual("0.09996", entries[0]["spot_fill_recovery"]["net_qty"])
            self.assertEqual(first["entry_allocations"], second["entry_allocations"])
            record = second["open_position_records"]["BTCUSDT:L"]
            self.assertEqual("Active", record["status"])
            self.assertEqual(0.09996, record["data"]["qty"])

    def test_recovery_rejects_wrong_mode_and_conflicting_order_proof(self):
        fill = self.summarize()
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "allocations.json"
            path.write_text(json.dumps({
                "version": 1, "mode": "Demo/Testnet", "timestamp": 1,
                "entry_allocations": {}, "open_position_records": {},
            }), encoding="utf-8")
            with self.assertRaisesRegex(LiveTradingSafetyError, "not a valid Live"):
                recovery.persist_spot_buy_allocation(path, fill)

            path.write_text(json.dumps({
                "version": 1, "mode": "Live", "timestamp": 1,
                "entry_allocations": {"BTCUSDT:L": [{
                    "client_order_id": INTENT["client_order_id"],
                    "symbol": "BTCUSDT", "side_key": "L", "qty": 0.1,
                    "entry_price": 20000, "status": "Active",
                    "spot_fill_recovery": {"signature": "0" * 64},
                }]},
                "open_position_records": {},
            }), encoding="utf-8")
            with self.assertRaisesRegex(LiveTradingSafetyError, "conflicts"):
                recovery.persist_spot_buy_allocation(path, fill)

    def test_trade_history_pagination_is_bounded_and_advances_by_trade_id(self):
        class FakeTransport:
            calls = []

            def get_my_trades(self, *, symbol, order_id, from_id, limit):
                self.calls.append((symbol, order_id, from_id, limit))
                return [[{"id": 1}, {"id": 2}], [{"id": 3}]][len(self.calls) - 1]

        transport = FakeTransport()
        with patch.object(recovery, "_TRADE_PAGE_SIZE", 2), patch.object(recovery, "_MAX_TRADE_PAGES", 3):
            trades = recovery.collect_spot_order_trades(transport, symbol="BTCUSDT", order_id=75)
        self.assertEqual([1, 2, 3], [row["id"] for row in trades])
        self.assertEqual([None, 3], [call[2] for call in transport.calls])


if __name__ == "__main__":
    unittest.main()
