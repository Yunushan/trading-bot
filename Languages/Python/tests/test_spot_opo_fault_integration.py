"""Offline venue faults through the real Spot wrapper, owner, guard and ledger."""

from __future__ import annotations

from copy import deepcopy
import hashlib
import hmac
import json
from pathlib import Path
import socket
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch
from urllib.parse import urlencode, urlparse

from app.integrations.exchanges.binance.orders import order_intent_runtime as ledger
from app.integrations.exchanges.binance.orders.order_intent_provisioning import (
    PROVISION_ACK,
    provision_order_intent_store,
)
from app.integrations.exchanges.binance.orders.spot_fill_recovery_runtime import (
    persist_spot_buy_allocation,
    summarize_spot_opo_buy_fill,
)
from app.integrations.exchanges.binance.wrapper import BinanceWrapper
from app.settings.live_safety import LIVE_TRADING_ACKNOWLEDGEMENT


class _Venue:
    """Stateful adapter boundary; it retains accepted orders after a lost reply."""

    def __init__(self):
        self.posts = []
        self.orders = {}
        self.lists = {}
        self.reads = []
        self.exits = []
        self.lose_ack = False
        self.uid = 12345678

    def get_symbol_info(self, symbol):
        return {
            "symbol": symbol, "status": "TRADING", "baseAsset": "BTC", "quoteAsset": "USDT",
            "isSpotTradingAllowed": True, "otoAllowed": True, "opoAllowed": True,
            "filters": [
                {"filterType": "PRICE_FILTER", "minPrice": "0.01", "maxPrice": "1000000", "tickSize": "0.01"},
                {"filterType": "LOT_SIZE", "minQty": "0.0001", "maxQty": "9000", "stepSize": "0.0001"},
                {"filterType": "MIN_NOTIONAL", "minNotional": "5"},
            ],
        }

    def create_order_list_opo(self, **request):
        if request["listClientOrderId"] in self.lists:
            raise AssertionError("Duplicate synthetic venue submission")
        self.posts.append(deepcopy(request))
        list_id = 300 + 10 * len(self.posts)
        working = {
            "symbol": request["symbol"], "orderId": list_id + 1, "orderListId": list_id,
            "clientOrderId": request["workingClientOrderId"], "type": "LIMIT", "side": "BUY",
            "timeInForce": "FOK", "status": "FILLED", "origQty": request["workingQuantity"],
            "executedQty": request["workingQuantity"], "cummulativeQuoteQty": "10.00",
        }
        pending = {
            "symbol": request["symbol"], "orderId": list_id + 2, "orderListId": list_id,
            "clientOrderId": request["pendingClientOrderId"], "type": "STOP_LOSS", "side": "SELL",
            "status": "NEW", "origQty": request["workingQuantity"], "executedQty": "0",
            "stopPrice": request["pendingStopPrice"],
        }
        for order in (working, pending):
            self.orders[order["clientOrderId"]] = order
        response = {
            "symbol": request["symbol"], "orderListId": list_id, "contingencyType": "OTO",
            "listStatusType": "EXEC_STARTED", "listOrderStatus": "EXECUTING",
            "listClientOrderId": request["listClientOrderId"],
            "orders": [{key: row[key] for key in ("symbol", "orderId", "clientOrderId")} for row in (working, pending)],
        }
        self.lists[request["listClientOrderId"]] = response
        if self.lose_ack:
            raise TimeoutError("Synthetic reply lost after venue acceptance")
        return {**deepcopy(response), "orderReports": deepcopy([working, pending])}

    def get_order_list(self, *, origClientOrderId):
        self.reads.append(("list", origClientOrderId))
        return deepcopy(self.lists[origClientOrderId])

    def get_order(self, *, symbol, origClientOrderId):
        self.reads.append(("order", origClientOrderId))
        result = deepcopy(self.orders[origClientOrderId])
        assert result["symbol"] == symbol
        return result

    def get_symbol_ticker(self, *, symbol):
        return {"symbol": symbol, "price": "100"}

    def cancel_replace_order(self, **request):
        self.exits.append(deepcopy(request))
        stop = self.orders[request["cancelOrigClientOrderId"]]
        assert stop["orderId"] == request["cancelOrderId"]
        stop["status"] = "CANCELED"
        for order_list in self.lists.values():
            if order_list["orderListId"] == stop["orderListId"]:
                order_list.update(listStatusType="ALL_DONE", listOrderStatus="ALL_DONE")
        sell = {
            "symbol": request["symbol"], "orderId": 1001, "orderListId": -1,
            "clientOrderId": request["newClientOrderId"], "side": "SELL", "type": "MARKET",
            "status": "FILLED", "origQty": request["quantity"], "executedQty": request["quantity"],
        }
        self.orders[sell["clientOrderId"]] = sell
        return {
            "cancelResult": "SUCCESS", "newOrderResult": "SUCCESS",
            "cancelResponse": {**deepcopy(stop), "origClientOrderId": stop["clientOrderId"]},
            "newOrderResponse": deepcopy(sell),
        }

    def signed_account_get(self, url, *, params, headers, timeout):
        assert urlparse(url).path == "/api/v3/account"
        assert headers == {"X-MBX-APIKEY": "offline-key"}
        unsigned = {key: value for key, value in params.items() if key != "signature"}
        expected = hmac.new(b"offline-secret", urlencode(unsigned).encode(), hashlib.sha256).hexdigest()
        assert hmac.compare_digest(expected, params["signature"])
        assert timeout
        return SimpleNamespace(status_code=200, json=lambda: {"uid": self.uid, "accountType": "SPOT"})


class SpotOpoFaultIntegrationTests(unittest.TestCase):
    def setUp(self):
        self.home = Path(self.enterContext(tempfile.TemporaryDirectory())).resolve()
        self.audit_path = self.home / "audit.jsonl"
        self.allocation_path = self.home / "allocations.json"
        self.enterContext(patch.dict("os.environ", {}, clear=True))
        self.enterContext(patch.object(Path, "home", return_value=self.home))
        self.enterContext(patch.object(socket.socket, "connect", side_effect=AssertionError("Network forbidden")))
        self.enterContext(patch.object(socket.socket, "connect_ex", side_effect=AssertionError("Network forbidden")))
        self.enterContext(patch(
            "app.gui.shared.allocation_persistence.get_position_allocations_path", return_value=self.allocation_path,
        ))
        self.venue = _Venue()
        self.enterContext(patch(
            "app.integrations.exchanges.binance.wrapper.BinanceSDKSpotClient", return_value=self.venue,
        ))
        self.enterContext(patch(
            "app.integrations.exchanges.binance.transport.http_request_runtime.requests.get",
            side_effect=self.venue.signed_account_get,
        ))
        admin = SimpleNamespace(
            _order_audit_log_path=self.audit_path, api_key="offline-key", mode="Live", account_type="SPOT",
            _enforce_spot_execution_owner=True, _operator_spot_account_uid=self.venue.uid,
        )
        provision_order_intent_store(admin, acknowledgement=PROVISION_ACK)

    def wrapper(self, *, cap=10):
        wrapper = BinanceWrapper(
            "offline-key", "offline-secret", mode="Live", account_type="Spot", connector_backend="binance-sdk-spot",
            live_safety_config={
                "live_trading_enabled": True, "live_trading_acknowledgement": LIVE_TRADING_ACKNOWLEDGEMENT,
                "position_pct": 2.0, "live_trading_max_leverage": 20, "live_trading_max_position_pct": 10.0,
                "live_trading_max_session_orders": cap, "order_audit_enabled": True,
                "order_audit_log_path": str(self.audit_path),
            },
        )
        self.addCleanup(self.close_owner, wrapper)
        return wrapper

    @staticmethod
    def close_owner(wrapper):
        owner = getattr(wrapper, "_spot_execution_owner", None)
        if owner is not None and owner.fd is not None:
            owner.close()

    @staticmethod
    def entry(wrapper, suffix="first"):
        return wrapper.place_spot_opo_entry(
            "BTCUSDT", "BUY", "100.00", "0.1000", "95.00",
            list_client_order_id=f"list-{suffix}", working_client_order_id=f"buy-{suffix}",
            pending_client_order_id=f"stop-{suffix}",
        )

    def recover_buy(self, wrapper, suffix="first"):
        record = ledger._get_order_intent_record(wrapper, f"list-{suffix}")
        order = self.venue.get_order(symbol="BTCUSDT", origClientOrderId=f"buy-{suffix}")
        trades = [{
            "symbol": "BTCUSDT", "orderId": order["orderId"], "id": order["orderId"] + 1000,
            "isBuyer": True, "price": "100", "qty": "0.1", "quoteQty": "10",
            "commission": "0", "commissionAsset": "BTC", "time": 1750000000000,
        }]
        fill = summarize_spot_opo_buy_fill(record, order, trades, base_asset="BTC", quote_asset="USDT")
        persist_spot_buy_allocation(self.allocation_path, fill)
        wrapper._mark_spot_opo_entry_reconciled(
            f"list-{suffix}", portfolio_signature=fill["signature"], portfolio_quantity=fill["net_qty"],
        )
        self.assertEqual(0, wrapper.get_order_intent_status()["unresolved_count"])

    def test_lost_ack_is_exactly_queried_and_recovered_without_second_post(self):
        wrapper = self.wrapper()
        self.venue.lose_ack = True
        result = self.entry(wrapper)
        self.assertFalse(result["ok"], result)
        self.assertEqual("unknown", ledger._get_order_intent_record(wrapper, "list-first")["state"])
        self.assertFalse(self.entry(wrapper, "second")["ok"])
        self.assertEqual(1, len(self.venue.posts))
        observed = wrapper.reconcile_spot_opo_intent("list-first", force=True)
        self.assertEqual("active", observed["protection_state"])
        self.assertEqual([("list", "list-first"), ("order", "buy-first"), ("order", "stop-first")], self.venue.reads)
        self.recover_buy(wrapper)
        self.assertEqual(1, len(self.venue.posts))

    def test_local_publication_failure_after_acceptance_keeps_submitted_intent_blocking(self):
        wrapper = self.wrapper()
        publish = ledger._write_ledger

        def fail_after_post(path, payload):
            if self.venue.posts:
                raise OSError("Synthetic full disk after venue acceptance")
            return publish(path, payload)

        with patch.object(ledger, "_write_ledger", side_effect=fail_after_post):
            result = self.entry(wrapper)
        self.assertFalse(result["ok"], result)
        self.assertTrue(result["exchange_response_received"])
        self.assertEqual("submitted", ledger._get_order_intent_record(wrapper, "list-first")["state"])
        self.assertFalse(self.entry(wrapper, "second")["ok"])
        self.assertEqual(1, len(self.venue.posts))
        self.assertEqual("active", wrapper.reconcile_spot_opo_intent("list-first", force=True)["protection_state"])
        self.recover_buy(wrapper)

    def test_restart_owner_fence_survives_exchange_recovery(self):
        first = self.wrapper()
        self.assertTrue(self.entry(first)["ok"])
        self.recover_buy(first)
        self.close_owner(first)
        second = self.wrapper()
        result = self.entry(second, "second")
        self.assertFalse(result["ok"], result)
        self.assertIn("reconciliation", result["error"].lower())
        self.assertEqual(1, len(self.venue.posts))

    def test_real_guard_blocks_exhausted_cap_before_second_post(self):
        wrapper = self.wrapper(cap=1)
        self.assertTrue(self.entry(wrapper)["ok"])
        self.recover_buy(wrapper)
        result = self.entry(wrapper, "second")
        self.assertFalse(result["ok"], result)
        self.assertIn("session order cap 1", result["error"])
        self.assertEqual(1, wrapper._live_order_submit_attempt_count)
        self.assertEqual(1, len(self.venue.posts))
        events = [json.loads(line)["event"] for line in self.audit_path.read_text(encoding="utf-8").splitlines()]
        self.assertIn("live_order_blocked", events)

    def test_signed_account_identity_mismatch_blocks_before_post(self):
        wrapper = self.wrapper()
        self.venue.uid += 1
        result = self.entry(wrapper)
        self.assertFalse(result["ok"], result)
        self.assertEqual([], self.venue.posts)

    def test_real_wrapper_linked_exit_is_bound_and_uses_durable_exact_request(self):
        wrapper = self.wrapper()
        self.assertTrue(self.entry(wrapper)["ok"])
        self.recover_buy(wrapper)
        result = wrapper.place_spot_opo_strategy_exit("list-first", new_order_client_id="exit-first")
        self.assertTrue(result["ok"], result)
        self.assertEqual(1, len(self.venue.exits))
        record = ledger._get_order_intent_record(wrapper, "list-first")
        self.assertEqual(record["strategy_exit_request"], self.venue.exits[0])
        self.assertEqual("FILLED", record["strategy_exit_status"])
        self.assertEqual(1, wrapper.get_order_intent_status()["unresolved_count"])


if __name__ == "__main__":
    unittest.main()
