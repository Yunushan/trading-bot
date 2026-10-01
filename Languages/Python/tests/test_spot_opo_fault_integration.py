"""Offline venue faults through the real Spot wrapper, owner, guard and ledger."""

from __future__ import annotations

from contextlib import redirect_stdout
from copy import deepcopy
import hashlib
import hmac
from io import StringIO
import json
import os
from pathlib import Path
import socket
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch
from urllib.parse import urlencode, urlparse

from app.integrations.exchanges.binance.orders import order_intent_admin as admin_cli
from app.integrations.exchanges.binance.orders import order_intent_runtime as ledger
from app.integrations.exchanges.binance.orders import spot_user_data_admin_runtime as admin_transport
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
from app.gui.shared.allocation_reconciliation import allocation_publication_pending
from app.gui.runtime.account import account_runtime


class _Venue:
    """Stateful adapter boundary; it retains accepted orders after a lost reply."""

    def __init__(self):
        self.posts = []
        self.orders = {}
        self.lists = {}
        self.reads = []
        self.exits = []
        self.lose_ack = False
        self.cancel_no_effect = False
        self.lose_exit_ack = False
        self.list_retains_original_client_id = False
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

    def get_order(self, *, symbol, origClientOrderId=None, orderId=None):
        assert (origClientOrderId is None) != (orderId is None)
        if orderId is not None:
            self.reads.append(("order_id", orderId))
            matches = [row for row in self.orders.values() if row["orderId"] == orderId]
            assert len(matches) == 1
            result = deepcopy(matches[0])
        else:
            self.reads.append(("order", origClientOrderId))
            result = deepcopy(self.orders[origClientOrderId])
        assert result["symbol"] == symbol
        return result

    def get_account_uid(self):
        return self.uid

    def get_symbol_assets(self, symbol):
        assert symbol == "BTCUSDT"
        return "BTC", "USDT"

    def get_my_trades(self, *, symbol, order_id, from_id=None, limit=1000):
        assert symbol == "BTCUSDT" and limit == 1000
        order = self.get_order(symbol=symbol, orderId=order_id)
        if order["executedQty"] == "0":
            return []
        trade_id = order_id + 1000
        if from_id is not None and from_id > trade_id:
            return []
        return [{
            "symbol": symbol, "orderId": order_id, "id": trade_id, "isBuyer": False,
            "price": "100", "qty": order["executedQty"],
            "quoteQty": order["cummulativeQuoteQty"], "commission": "0.01",
            "commissionAsset": "USDT", "time": 1750000001000,
        }]

    def get_symbol_ticker(self, *, symbol):
        return {"symbol": symbol, "price": "100"}

    def cancel_replace_order(self, **request):
        self.exits.append(deepcopy(request))
        stop = self.orders[request["cancelOrigClientOrderId"]]
        assert stop["orderId"] == request["cancelOrderId"]
        if self.cancel_no_effect:
            return {
                "cancelResult": "FAILURE", "newOrderResult": "NOT_ATTEMPTED",
                "cancelResponse": {"code": -2011, "msg": "Synthetic cancellation had no effect"},
                "newOrderResponse": None,
            }
        original_stop_client_id = stop["clientOrderId"]
        stop["status"] = "CANCELED"
        stop["clientOrderId"] = request.get("cancelNewClientOrderId", "venue-cancelled-stop")
        del self.orders[original_stop_client_id]
        self.orders[stop["clientOrderId"]] = stop
        for order_list in self.lists.values():
            if order_list["orderListId"] == stop["orderListId"]:
                order_list.update(listStatusType="ALL_DONE", listOrderStatus="ALL_DONE")
                if not self.list_retains_original_client_id:
                    for child in order_list["orders"]:
                        if child["orderId"] == stop["orderId"]:
                            child["clientOrderId"] = stop["clientOrderId"]
        sell = {
            "symbol": request["symbol"], "orderId": 1001, "orderListId": -1,
            "clientOrderId": request["newClientOrderId"], "side": "SELL", "type": "MARKET",
            "status": "FILLED", "origQty": request["quantity"], "executedQty": request["quantity"],
            "cummulativeQuoteQty": "10.00", "updateTime": 1750000001000,
        }
        self.orders[sell["clientOrderId"]] = sell
        if self.lose_exit_ack:
            raise TimeoutError("Synthetic linked SELL reply lost after venue acceptance")
        return {
            "cancelResult": "SUCCESS", "newOrderResult": "SUCCESS",
            "cancelResponse": {**deepcopy(stop), "origClientOrderId": original_stop_client_id},
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

    def recover_cli(self):
        with patch.dict(os.environ, {
            "OFFLINE_ADMIN_KEY": "offline-key", "OFFLINE_ADMIN_SECRET": "offline-secret",
        }), patch.object(
            admin_transport, "SpotUserDataTransport", return_value=self.venue,
        ), redirect_stdout(StringIO()) as output:
            code = admin_cli.main([
                "recover-spot-opos", "--mode", "Live", "--account-type", "Spot",
                "--api-key-env", "OFFLINE_ADMIN_KEY", "--api-secret-env", "OFFLINE_ADMIN_SECRET",
            ])
        return code, json.loads(output.getvalue())

    def lost_exit(self, *, retry=False, list_retains_original=False):
        wrapper = self.wrapper()
        self.assertTrue(self.entry(wrapper)["ok"])
        self.recover_buy(wrapper)
        if retry:
            self.venue.cancel_no_effect = True
            self.assertTrue(wrapper.place_spot_opo_strategy_exit(
                "list-first", new_order_client_id="exit-no-effect",
            )["ok"])
            self.venue.cancel_no_effect = False
        self.venue.list_retains_original_client_id = list_retains_original
        self.venue.lose_exit_ack = True
        self.assertFalse(wrapper.place_spot_opo_strategy_exit(
            "list-first", new_order_client_id="exit-lost",
        )["ok"])
        self.close_owner(wrapper)
        return wrapper

    def test_gui_factory_fences_pending_publication_before_opo_intent_and_post(self):
        wrapper = self.wrapper()
        window = SimpleNamespace(
            config={}, _runtime_connector_backend=lambda **_kwargs: "binance-sdk-spot",
            _allocation_snapshot_session=SimpleNamespace(ready=True),
            _pending_allocation_reconciliations={("BTCUSDT", "L"): [{"operation": "close"}]},
        )
        with patch.object(account_runtime, "BinanceWrapper", return_value=wrapper):
            created = account_runtime._create_binance_wrapper(
                window, api_key="offline-key", api_secret="offline-secret", mode="Live", account_type="Spot",
            )
        self.assertIs(wrapper, created)
        result = self.entry(wrapper)
        self.assertFalse(result["ok"], result)
        self.assertIn("allocation publication", result["error"])
        self.assertEqual([], self.venue.posts)
        self.assertEqual(0, wrapper.get_order_intent_status()["intent_count"])
        self.assertEqual(0, getattr(wrapper, "_live_order_submit_attempt_count", 0))

    def test_gui_admission_callback_error_fails_closed_without_secret_in_error(self):
        wrapper = self.wrapper()
        def broken_check():
            raise RuntimeError("api_secret=private-callback-unit")
        wrapper._desktop_allocation_admission_check = broken_check
        result = self.entry(wrapper)
        self.assertFalse(result["ok"], result)
        self.assertIn("allocation publication", result["error"])
        self.assertNotIn("private-callback-unit", str(result))
        self.assertEqual([], self.venue.posts)
        self.assertEqual(0, wrapper.get_order_intent_status()["intent_count"])

    def test_gui_pending_publication_retains_linked_risk_reducing_exit(self):
        wrapper = self.wrapper()
        self.assertTrue(self.entry(wrapper)["ok"])
        self.recover_buy(wrapper)
        window = SimpleNamespace(_pending_allocation_reconciliations={
            ("ETHUSDT", "L"): [{"operation": "close"}],
        })
        wrapper._desktop_allocation_admission_check = lambda: not allocation_publication_pending(window)
        self.assertTrue(wrapper.place_spot_opo_strategy_exit(
            "list-first", new_order_client_id="exit-pending-gui",
        )["ok"])
        self.assertEqual(1, len(self.venue.exits))
        self.assertEqual("sell_accepted", ledger._get_order_intent_record(wrapper, "list-first")["strategy_exit_state"])

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

    def test_proven_no_effect_exit_retries_once_with_new_durable_request(self):
        wrapper = self.wrapper()
        self.assertTrue(self.entry(wrapper)["ok"])
        self.recover_buy(wrapper)
        allocation_before = self.allocation_path.read_bytes()
        self.venue.cancel_no_effect = True
        first = wrapper.place_spot_opo_strategy_exit("list-first", new_order_client_id="exit-no-effect")
        self.assertTrue(first["ok"], first)
        self.assertFalse(first["accepted"])
        record_before = ledger._get_order_intent_record(wrapper, "list-first")
        self.assertEqual("no_effect", record_before["strategy_exit_state"])
        self.assertEqual("active", record_before["protection_state"])
        self.assertNotIn("exit-no-effect", self.venue.orders)
        self.assertEqual(allocation_before, self.allocation_path.read_bytes())
        self.venue.cancel_no_effect = False
        second = wrapper.place_spot_opo_strategy_exit("list-first", new_order_client_id="exit-retry")
        self.assertTrue(second["ok"], second)
        self.assertTrue(second["accepted"])
        self.assertEqual(["exit-no-effect", "exit-retry"], [row["newClientOrderId"] for row in self.venue.exits])
        current = ledger._get_order_intent_record(wrapper, "list-first")
        self.assertEqual("exit-retry", current["strategy_exit_client_order_id"])
        self.assertEqual(current["strategy_exit_request"], self.venue.exits[1])
        history = current["strategy_exit_history"]
        self.assertEqual(1, len(history))
        self.assertEqual("exit-no-effect", history[0]["strategy_exit_client_order_id"])
        self.assertEqual(record_before["strategy_exit_request"], history[0]["strategy_exit_request"])
        self.assertEqual("no_effect", history[0]["strategy_exit_state"])
        self.assertEqual("FILLED", current["strategy_exit_status"])
        self.assertEqual(allocation_before, self.allocation_path.read_bytes())
        self.assertEqual(1, wrapper.get_order_intent_status()["unresolved_count"])

    def test_uncertain_linked_exit_cannot_submit_a_second_replacement(self):
        wrapper = self.wrapper()
        self.assertTrue(self.entry(wrapper)["ok"])
        self.recover_buy(wrapper)
        self.venue.lose_exit_ack = True
        first = wrapper.place_spot_opo_strategy_exit("list-first", new_order_client_id="exit-lost")
        self.assertFalse(first["ok"], first)
        self.assertEqual("unknown", ledger._get_order_intent_record(wrapper, "list-first")["strategy_exit_state"])
        self.assertIn("exit-lost", self.venue.orders)
        second = wrapper.place_spot_opo_strategy_exit("list-first", new_order_client_id="exit-retry")
        self.assertFalse(second["ok"], second)
        self.assertEqual(["exit-lost"], [row["newClientOrderId"] for row in self.venue.exits])

    def test_proven_no_effect_exit_cannot_reuse_its_old_client_id(self):
        wrapper = self.wrapper()
        self.assertTrue(self.entry(wrapper)["ok"])
        self.recover_buy(wrapper)
        self.venue.cancel_no_effect = True
        first = wrapper.place_spot_opo_strategy_exit("list-first", new_order_client_id="exit-no-effect")
        self.assertTrue(first["ok"], first)
        path = ledger._intent_path(wrapper)
        before = path.read_bytes()
        second = wrapper.place_spot_opo_strategy_exit("list-first", new_order_client_id="exit-no-effect")
        self.assertFalse(second["ok"], second)
        self.assertEqual(["exit-no-effect"], [row["newClientOrderId"] for row in self.venue.exits])
        self.assertEqual(before, path.read_bytes())

    def test_triggered_stop_blocks_retry_after_prior_no_effect_cancellation(self):
        wrapper = self.wrapper()
        self.assertTrue(self.entry(wrapper)["ok"])
        self.recover_buy(wrapper)
        self.venue.cancel_no_effect = True
        self.assertTrue(wrapper.place_spot_opo_strategy_exit("list-first", new_order_client_id="exit-no-effect")["ok"])
        stop = self.venue.orders["stop-first"]
        stop.update(status="FILLED", executedQty=stop["origQty"])
        self.venue.lists["list-first"].update(listStatusType="ALL_DONE", listOrderStatus="ALL_DONE")
        result = wrapper.place_spot_opo_strategy_exit("list-first", new_order_client_id="exit-retry")
        self.assertFalse(result["ok"], result)
        self.assertEqual(["exit-no-effect"], [row["newClientOrderId"] for row in self.venue.exits])
        self.assertEqual(1, wrapper.get_order_intent_status()["unresolved_count"])

    def test_changed_allocation_blocks_retry_after_prior_no_effect_cancellation(self):
        wrapper = self.wrapper()
        self.assertTrue(self.entry(wrapper)["ok"])
        self.recover_buy(wrapper)
        self.venue.cancel_no_effect = True
        self.assertTrue(wrapper.place_spot_opo_strategy_exit("list-first", new_order_client_id="exit-no-effect")["ok"])
        snapshot = json.loads(self.allocation_path.read_text(encoding="utf-8"))
        snapshot["entry_allocations"]["BTCUSDT:L"][0]["entry_price"] = 101.0
        self.allocation_path.write_text(json.dumps(snapshot), encoding="utf-8")
        changed_allocation = self.allocation_path.read_bytes()
        result = wrapper.place_spot_opo_strategy_exit("list-first", new_order_client_id="exit-retry")
        self.assertFalse(result["ok"], result)
        self.assertEqual(["exit-no-effect"], [row["newClientOrderId"] for row in self.venue.exits])
        self.assertEqual(changed_allocation, self.allocation_path.read_bytes())

    def test_external_cancel_after_prior_no_effect_keeps_exact_state_loadable_and_blocking(self):
        wrapper = self.wrapper()
        self.assertTrue(self.entry(wrapper)["ok"])
        self.recover_buy(wrapper)
        self.venue.cancel_no_effect = True
        self.assertTrue(wrapper.place_spot_opo_strategy_exit("list-first", new_order_client_id="exit-no-effect")["ok"])
        self.venue.orders["stop-first"].update(status="CANCELED", executedQty="0")
        self.venue.lists["list-first"].update(listStatusType="ALL_DONE", listOrderStatus="ALL_DONE")
        result = wrapper.place_spot_opo_strategy_exit("list-first", new_order_client_id="exit-retry")
        self.assertFalse(result["ok"], result)
        self.assertEqual(["exit-no-effect"], [row["newClientOrderId"] for row in self.venue.exits])
        self.assertEqual(1, wrapper.get_order_intent_status()["unresolved_count"])
        current = ledger._get_order_intent_record(wrapper, "list-first")
        self.assertEqual("CANCELED", current["pending_status"])
        self.assertEqual("lost", current["protection_state"])
        self.assertEqual("unknown", current["state"])
        self.assertEqual("rejected", current["cancel_state"])
        self.assertNotIn("cancel_confirmed_at", current)
        self.assertEqual("cancel_failed", current["strategy_exit_outcome"])
        self.assertIs(False, current["strategy_exit_new_order_accepted"])

    def test_exhausted_guard_blocks_retry_after_prior_no_effect_cancellation(self):
        wrapper = self.wrapper(cap=2)
        self.assertTrue(self.entry(wrapper)["ok"])
        self.recover_buy(wrapper)
        self.venue.cancel_no_effect = True
        self.assertTrue(wrapper.place_spot_opo_strategy_exit("list-first", new_order_client_id="exit-no-effect")["ok"])
        record_before = ledger._get_order_intent_record(wrapper, "list-first")
        result = wrapper.place_spot_opo_strategy_exit("list-first", new_order_client_id="exit-retry")
        self.assertFalse(result["ok"], result)
        self.assertIn("session order cap 2", result["error"])
        self.assertEqual(2, wrapper._live_order_submit_attempt_count)
        self.assertEqual(["exit-no-effect"], [row["newClientOrderId"] for row in self.venue.exits])
        current = ledger._get_order_intent_record(wrapper, "list-first")
        for field in ("strategy_exit_client_order_id", "strategy_exit_request", "strategy_exit_history"):
            self.assertEqual(record_before.get(field), current.get(field))


    def test_cli_lost_retry_reply_recovers_renamed_stop_and_fee_aware_fill(self):
        self._assert_cli_lost_reply_recovered(retry=True, list_retains_original=False)

    def test_cli_lost_retry_reply_accepts_list_retaining_original_stop_id(self):
        self._assert_cli_lost_reply_recovered(retry=True, list_retains_original=True)

    def test_cli_lost_first_reply_recovers_renamed_stop_without_extra_submission(self):
        self._assert_cli_lost_reply_recovered(retry=False, list_retains_original=False)

    def _assert_cli_lost_reply_recovered(self, *, retry, list_retains_original):
        wrapper = self.lost_exit(retry=retry, list_retains_original=list_retains_original)
        before = ledger._get_order_intent_record(wrapper, "list-first")
        history = deepcopy(before.get("strategy_exit_history", []))
        submitted = deepcopy(self.venue.exits)
        code, result = self.recover_cli()
        self.assertEqual(0, code, result)
        self.assertEqual(1, result["recovered_strategy_exit_count"])
        self.assertEqual(0, result["unresolved_after"])
        self.assertFalse(result["exchange_orders_placed"])
        self.assertFalse(result["automatic_rearm"])
        self.assertEqual(submitted, self.venue.exits)
        current = ledger._get_order_intent_record(wrapper, "list-first")
        self.assertEqual("completed", current["strategy_exit_state"])
        self.assertEqual(history, current.get("strategy_exit_history", []))
        self.assertEqual(
            before["strategy_exit_request"]["cancelNewClientOrderId"],
            current["pending_observed_client_order_id"],
        )
        self.assertEqual("stop-first", current["request"]["pendingClientOrderId"])
        allocation = json.loads(self.allocation_path.read_text(encoding="utf-8"))
        row = allocation["entry_allocations"]["BTCUSDT:L"][0]
        self.assertEqual("Closed", row["status"])
        self.assertEqual("exit-lost", row["spot_sell_recoveries"][0]["client_order_id"])
        self.assertEqual("0.01", str(row["spot_sell_recoveries"][0]["quote_fee_qty"]))
        restarted = self.wrapper()
        self.assertFalse(self.entry(restarted, "second")["ok"])
        self.assertEqual(1, len(self.venue.posts))

    def test_cli_new_replacement_is_classified_but_inventory_remains_unresolved(self):
        self._assert_open_replacement_unresolved("NEW", "0", "0")

    def test_cli_partial_replacement_is_classified_but_inventory_remains_unresolved(self):
        self._assert_open_replacement_unresolved("PARTIALLY_FILLED", "0.04", "4")

    def _assert_open_replacement_unresolved(self, status, executed, quote):
        wrapper = self.lost_exit(retry=True)
        self.venue.orders["exit-lost"].update(
            status=status, executedQty=executed, cummulativeQuoteQty=quote,
        )
        allocation = self.allocation_path.read_bytes()
        submitted = deepcopy(self.venue.exits)
        code, result = self.recover_cli()
        self.assertEqual(1, code, result)
        self.assertEqual(0, result["failed_recovery_count"])
        self.assertEqual(1, result["unresolved_after"])
        self.assertEqual(0, result["recovered_strategy_exit_count"])
        self.assertEqual(submitted, self.venue.exits)
        self.assertEqual(allocation, self.allocation_path.read_bytes())
        current = ledger._get_order_intent_record(wrapper, "list-first")
        self.assertEqual("sell_accepted", current["strategy_exit_state"])
        self.assertEqual(status, current["strategy_exit_status"])

    def test_cli_changed_allocation_during_queries_rejects_exit_classification(self):
        wrapper = self.lost_exit(retry=True)
        original_get = self.venue.get_order
        changed = []

        def mutate_allocation(**selector):
            order = original_get(**selector)
            if selector.get("origClientOrderId") == "exit-lost" and not changed:
                snapshot = json.loads(self.allocation_path.read_text(encoding="utf-8"))
                snapshot["entry_allocations"]["BTCUSDT:L"][0]["entry_price"] = 101.0
                self.allocation_path.write_text(json.dumps(snapshot), encoding="utf-8")
                changed.append(self.allocation_path.read_bytes())
            return order

        with patch.object(self.venue, "get_order", side_effect=mutate_allocation):
            code, result = self.recover_cli()
        self.assertEqual(1, code, result)
        self.assertEqual(1, result["failed_recovery_count"])
        self.assertEqual(changed[0], self.allocation_path.read_bytes())
        current = ledger._get_order_intent_record(wrapper, "list-first")
        self.assertEqual("unknown", current["strategy_exit_state"])
        self.assertEqual(2, len(self.venue.exits))

    def test_cli_rejects_wrong_cancel_alias_without_consuming_inventory(self):
        wrapper = self.lost_exit(retry=True, list_retains_original=True)
        alias = self.venue.exits[-1]["cancelNewClientOrderId"]
        self.venue.orders[alias]["clientOrderId"] = "unrelated-cancel-alias"
        allocation = self.allocation_path.read_bytes()
        code, result = self.recover_cli()
        self.assertEqual(1, code, result)
        self.assertEqual(1, result["failed_recovery_count"])
        self.assertEqual(1, result["unresolved_after"])
        self.assertEqual(allocation, self.allocation_path.read_bytes())
        self.assertEqual("unknown", ledger._get_order_intent_record(wrapper, "list-first")["strategy_exit_state"])
        self.assertEqual(2, len(self.venue.exits))

    def test_cli_failed_acceptance_publication_remains_blocking_and_replays_queries(self):
        wrapper = self.lost_exit(retry=True)
        allocation = self.allocation_path.read_bytes()
        publish = ledger._write_ledger

        def fail_acceptance(path, payload):
            record = payload["intents"]["list-first"]
            if record.get("strategy_exit_state") == "sell_accepted":
                raise OSError("Synthetic full disk at query-proof publication")
            return publish(path, payload)

        with patch.object(ledger, "_write_ledger", side_effect=fail_acceptance):
            code, result = self.recover_cli()
        self.assertEqual(1, code, result)
        self.assertEqual(1, result["unresolved_after"])
        self.assertEqual(allocation, self.allocation_path.read_bytes())
        self.assertEqual("unknown", ledger._get_order_intent_record(wrapper, "list-first")["strategy_exit_state"])
        code, result = self.recover_cli()
        self.assertEqual(0, code, result)
        self.assertEqual(1, result["recovered_strategy_exit_count"])
        self.assertEqual(2, len(self.venue.exits))


if __name__ == "__main__":
    unittest.main()
