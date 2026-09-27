from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from app.integrations.exchanges.binance.orders import spot_fill_recovery_runtime as recovery
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


class SpotFillRecoveryTests(unittest.TestCase):
    def summarize(self):
        return recovery.summarize_spot_market_fill(
            INTENT, ORDER, TRADES, base_asset="BTC", quote_asset="USDT",
        )

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
