"""Independent offline account/store inventory and admission controls."""
from __future__ import annotations

from contextlib import contextmanager
from copy import deepcopy
from decimal import Decimal
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
from uuid import uuid4

from test_open_trade_signal_behavior import _OpenSignalWindowStub
from test_spot_opo_fault_integration import _Venue

from app.gui.runtime.account import account_runtime
from app.gui.shared import allocation_persistence as allocations
from app.integrations.exchanges.binance.orders import order_intent_runtime as intents
from app.integrations.exchanges.binance.orders import spot_allocation_generation_runtime as generations
from app.integrations.exchanges.binance.orders import spot_desktop_buy_recovery_runtime as recovery
from app.integrations.exchanges.binance.orders import spot_fill_recovery_runtime as fills
from app.integrations.exchanges.binance.orders import spot_indexed_intent_migration as migration
from app.integrations.exchanges.binance.orders import spot_inventory_namespace as namespaces
from app.integrations.exchanges.binance.orders import spot_inventory_namespace_runtime as namespace_runtime
from app.integrations.exchanges.binance.orders.order_intent_provisioning import (
    PROVISION_ACK, provision_order_intent_store, rotate_spot_owner_credentials,
)
from app.integrations.exchanges.binance.orders.order_intent_store import (
    ledger_transaction, ledger_transactions, write_ledger,
)
from app.integrations.exchanges.binance.orders.spot_execution_owner import owner_administration_lock, owner_marker_path
from app.integrations.exchanges.binance.orders.spot_opo_runtime import build_spot_opo_request
from app.integrations.exchanges.binance.wrapper import BinanceWrapper
from app.settings.live_safety import LIVE_TRADING_ACKNOWLEDGEMENT, LiveTradingSafetyError


CLIENT = "coincident-buy-provenance"
PARAMS = {"symbol": "BTCUSDT", "side": "BUY", "type": "MARKET",
          "quantity": "0.1", "newClientOrderId": CLIENT}
RESPONSE = {
    "symbol": "BTCUSDT", "side": "BUY", "type": "MARKET", "clientOrderId": CLIENT,
    "orderId": 707001, "status": "FILLED", "origQty": "0.1", "executedQty": "0.1",
    "cummulativeQuoteQty": "2000", "updateTime": 1780000000001,
    "fills": [{"tradeId": 909001, "price": "20000", "qty": "0.1",
               "commission": "0.00004", "commissionAsset": "BTC"}],
}


class SpotInventoryNamespaceIntegrationTests(unittest.TestCase):
    def setUp(self):
        self.home = Path(self.enterContext(tempfile.TemporaryDirectory())).resolve()
        self.path = self.home / "shared-live-allocations.json"
        self.accounts = {}
        self.order_calls = []
        self.account_reads = []
        self.enterContext(patch.dict("os.environ", {}, clear=True))
        self.enterContext(patch.object(Path, "home", return_value=self.home))
        self.enterContext(patch.object(socket.socket, "connect", side_effect=AssertionError("No network")))
        self.enterContext(patch.object(socket.socket, "connect_ex", side_effect=AssertionError("No network")))
        self.enterContext(patch.object(socket, "create_connection", side_effect=AssertionError("No network")))
        self.enterContext(patch.object(allocations, "get_position_allocations_path", return_value=self.path))
        self.enterContext(patch.object(allocations, "_get_allocations_file_path", return_value=self.path))
        self.enterContext(patch(
            "app.integrations.exchanges.binance.transport.http_request_runtime.requests.get",
            side_effect=self.signed_get,
        ))
        self.enterContext(patch("requests.post", side_effect=self.forbidden_order))
        self.fill = fills.summarize_primary_spot_buy(
            RESPONSE, symbol="BTCUSDT", client_order_id=CLIENT, base_asset="BTC", quote_asset="USDT",
        )

    def forbidden_order(self, *_args, **_kwargs):
        self.order_calls.append("unexpected_order")
        raise AssertionError("Accepted fixtures are authored offline; no order transport is allowed")

    def signed_get(self, url, *, params, headers, timeout):
        self.assertEqual("/api/v3/account", urlparse(url).path)
        uid, secret = self.accounts[headers["X-MBX-APIKEY"]]
        unsigned = {key: value for key, value in params.items() if key != "signature"}
        expected = hmac.new(secret.encode(), urlencode(unsigned).encode(), hashlib.sha256).hexdigest()
        self.assertTrue(hmac.compare_digest(expected, params["signature"]))
        self.assertTrue(timeout)
        self.account_reads.append(uid)
        return SimpleNamespace(status_code=200, json=lambda: {"uid": uid, "accountType": "SPOT"})

    @contextmanager
    def account_home(self, account):
        with patch.object(Path, "home", return_value=account.home):
            yield

    def new_wrapper(self, key, secret, home, venue):
        with patch.object(Path, "home", return_value=home), patch(
            "app.integrations.exchanges.binance.wrapper.BinanceSDKSpotClient", return_value=venue,
        ):
            return BinanceWrapper(
                key, secret, mode="Live", account_type="Spot", connector_backend="binance-sdk-spot",
                live_safety_config={
                    "live_trading_enabled": True, "live_trading_acknowledgement": LIVE_TRADING_ACKNOWLEDGEMENT,
                    "position_pct": 2.0, "live_trading_max_leverage": 20,
                    "live_trading_max_position_pct": 10.0, "live_trading_max_session_orders": 10,
                    "order_audit_enabled": True, "order_audit_log_path": str(home / "audit.jsonl"),
                },
            )

    def account(self, label, uid, *, separate_home=False, accepted=True):
        home = self.home / label if separate_home else self.home
        home.mkdir(exist_ok=True)
        key, secret = "offline-provenance-key-" + label, "offline-provenance-secret-" + label
        self.accounts[key] = uid, secret
        venue = _Venue()
        venue.uid = uid
        venue.create_order = self.forbidden_order
        venue.create_order_list_opo = self.forbidden_order
        venue.cancel_replace_order = self.forbidden_order
        with patch.object(Path, "home", return_value=home), patch(
            "app.integrations.exchanges.binance.wrapper.BinanceSDKSpotClient", return_value=venue,
        ):
            admin = SimpleNamespace(api_key=key, mode="Live", account_type="SPOT",
                                    _enforce_spot_execution_owner=True, _operator_spot_account_uid=uid,
                                    _order_audit_log_path=home / "audit.jsonl")
            provision_order_intent_store(admin, acknowledgement=PROVISION_ACK)
            wrapper = self.new_wrapper(key, secret, home, venue)
            owner = wrapper._ensure_spot_execution_owner()
            self.addCleanup(owner.close)
            account = SimpleNamespace(wrapper=wrapper, uid=uid, home=home,
                                      path=intents._intent_path(wrapper), owner=owner, venue=venue)
            if accepted:
                self.author_accepted(account, self.fill)
            account.namespace = namespaces.make_namespace(uid, self.ledger(account)["store_id"])
            return account

    def ledger(self, account):
        with self.account_home(account), ledger_transaction(account.path):
            payload = intents._read_ledger(account.path, expected_binding=intents._intent_binding(account.wrapper))
            intents.validate_order_intent_ledger(payload, expected_binding=intents._intent_binding(account.wrapper))
            return deepcopy(dict(payload))

    def author_accepted(self, account, fill):
        """Retain the exact original canonical fill without invoking a placement method."""
        params = {**PARAMS, "newClientOrderId": fill["client_order_id"]}
        record = intents._intent_record(params, market="spot", source="offline-provenance-fixture")
        metadata = generations.canonical_spot_buy_metadata(fill)
        record.update(state="accepted", exchange_status="FILLED", exchange_order_id=str(fill["order_id"]),
                      executed_qty=metadata["gross_qty"], portfolio_qty=metadata["net_qty"],
                      portfolio_reconciled=False, primary_fill_receipt=deepcopy(metadata),
                      primary_fill_signature=metadata["signature"], accepted_at=intents._now())
        intents.validate_order_intent_record(fill["client_order_id"], record)
        with self.account_home(account), ledger_transaction(account.path):
            payload = intents._read_ledger(account.path, expected_binding=intents._intent_binding(account.wrapper))
            payload["intents"][fill["client_order_id"]] = record
            intents.validate_order_intent_ledger(payload, expected_binding=intents._intent_binding(account.wrapper))
            write_ledger(account.path, payload)
        return record

    def durable_bytes(self, account):
        return (self.path.read_bytes() if self.path.exists() else None,
                account.path.read_bytes(), owner_marker_path(account.path).read_bytes())

    def loaded(self, account):
        session = allocations.AllocationSnapshotSession()
        ticket = allocations.AllocationSnapshotLoadTicket()
        entries, records = allocations.load_position_allocations(
            this_file=account.home / "unused.py", mode="Live", session=session, load_ticket=ticket,
        )
        with session.loaded_handoff(ticket) as accepted:
            self.assertTrue(accepted)
            window = SimpleNamespace(shared_binance=account.wrapper, _allocation_snapshot_session=session,
                                     _entry_allocations=entries, _open_position_records=records)
        self.assertTrue(session.matches_loaded_maps(entries, records))
        return window

    def recover(self, account):
        with self.account_home(account):
            discovery = recovery.discover_spot_desktop_buy_recoveries(account.wrapper, allocation_path=self.path)
            item = next(item for item in discovery.items if item.client_order_id == CLIENT)
            window = self.loaded(account)
            source = recovery.capture_spot_desktop_buy_recovery_source(
                window._allocation_snapshot_session, window._entry_allocations,
                window._open_position_records, allocation_path=self.path,
            )

            @contextmanager
            def handoff():
                with source.session._mutex:
                    self.assertIs(window.shared_binance, account.wrapper)
                    self.assertTrue(source.session.matches_loaded_maps(
                        window._entry_allocations, window._open_position_records,
                    ))
                    yield

            return recovery.recover_spot_desktop_buy(
                account.wrapper, item, allocation_path=self.path, expected_loaded_receipt=source,
                publication_handoff=handoff,
            )

    def assert_recovery_rejected_without_writes(self, account):
        before = self.durable_bytes(account)
        full_before = self.ledger(account)
        with self.assertRaises(LiveTradingSafetyError):
            self.recover(account)
        self.assertEqual(before, self.durable_bytes(account))
        self.assertEqual(full_before, self.ledger(account))
        self.assertIsNot(full_before["intents"][CLIENT].get("portfolio_reconciled"), True)
        self.assertEqual("recovery_required", json.loads(before[2])["state"])
        self.assertEqual([], self.order_calls)

    def test_foreign_uid_matching_fill_cannot_mark_selected_store(self):
        a = self.account("A", 810001)
        self.assertTrue(fills.persist_spot_buy_allocation(self.path, self.fill, namespace=a.namespace))
        a.owner.close()
        a_bytes = self.durable_bytes(a)
        b = self.account("B", 810002)
        self.assertNotEqual(a.namespace, b.namespace)
        self.assertEqual(self.ledger(a)["intents"][CLIENT]["primary_fill_receipt"],
                         self.ledger(b)["intents"][CLIENT]["primary_fill_receipt"])
        b.owner.close()
        self.assert_recovery_rejected_without_writes(b)
        self.assertEqual(a_bytes, self.durable_bytes(a))

    def test_same_uid_restored_inventory_new_store_cannot_mark_selected_store(self):
        a = self.account("old-home", 810003, separate_home=True)
        self.assertTrue(fills.persist_spot_buy_allocation(self.path, self.fill, namespace=a.namespace))
        a.owner.close()
        b = self.account("new-home", 810003, separate_home=True)
        self.assertEqual(a.uid, b.uid)
        self.assertNotEqual(a.namespace["store_id"], b.namespace["store_id"])
        b.owner.close()
        self.assert_recovery_rejected_without_writes(b)

    def test_nonempty_legacy_acquisition_is_not_implicitly_adopted(self):
        account = self.account("legacy", 810004)
        self.assertTrue(fills.persist_spot_buy_allocation(self.path, self.fill, namespace=account.namespace))
        raw = json.loads(self.path.read_bytes())
        raw.pop(namespaces.ACCOUNT_NAMESPACE_KEY)
        self.path.write_text(json.dumps(raw), encoding="utf-8")
        account.owner.close()
        self.assert_recovery_rejected_without_writes(account)

    def test_malformed_namespace_fences_without_losing_complete_history(self):
        account = self.account("malformed", 810005)
        self.assertTrue(fills.persist_spot_buy_allocation(self.path, self.fill, namespace=account.namespace))
        payload = json.loads(self.path.read_bytes())
        payload["preserved_extension"] = {"history": ["original", {"count": 3}]}
        for malformed in (None, {}, {**account.namespace, "account_uid": True},
                          {**account.namespace, "store_id": "not-a-store"},
                          {**account.namespace, "environment": "testnet"}):
            with self.subTest(namespace=malformed):
                changed = deepcopy(payload)
                changed[namespaces.ACCOUNT_NAMESPACE_KEY] = malformed
                self.path.write_text(json.dumps(changed), encoding="utf-8")
                account.owner.close()
                self.assert_recovery_rejected_without_writes(account)

    def test_owned_recovery_keeps_full_history_and_marker_callback_lock_order(self):
        account = self.account("positive", 810006)
        self.assertTrue(fills.persist_spot_buy_allocation(self.path, self.fill, namespace=account.namespace))
        payload = json.loads(self.path.read_bytes())
        payload["preserved_extension"] = {"history": ["original", {"count": 3}]}
        self.path.write_text(json.dumps(payload), encoding="utf-8")
        account.owner.close()
        before = self.path.read_bytes()
        original = recovery._mark_exact_acquisition
        calls = []

        def marker(*args, **kwargs):
            # This fails if publication invokes the marker while retaining storage locks.
            with ledger_transactions(account.path, self.path):
                calls.append("unlocked")
            return original(*args, **kwargs)

        with patch.object(recovery, "_mark_exact_acquisition", side_effect=marker):
            result = self.recover(account)
        self.assertTrue(result["already_present"])
        self.assertTrue(result["portfolio_reconciled"])
        self.assertEqual(["unlocked"], calls)
        self.assertEqual(before, self.path.read_bytes())
        self.assertEqual(payload, json.loads(before))
        self.assertEqual([], self.order_calls)

    def test_partial_and_closed_acquisition_recovery_never_restores_inventory(self):
        for quantity in ("0.04", "0.09996"):
            with self.subTest(quantity=quantity):
                scenario = type(self)()
                scenario.setUp()
                try:
                    account = scenario.account("consumed", 810011)
                    self.assertTrue(fills.persist_spot_buy_allocation(
                        scenario.path, scenario.fill, namespace=account.namespace,
                    ))
                    baseline = fills.spot_live_allocation_baseline(
                        scenario.path, symbol="BTCUSDT", namespace=account.namespace,
                    )
                    self.assertIsNotNone(baseline)
                    quote = str(Decimal(quantity) * 20000)
                    intent = {"market": "spot", "type": "MARKET", "side": "SELL", "symbol": "BTCUSDT",
                              "client_order_id": "consumed-owned-acquisition", "exchange_order_id": "707002"}
                    order = {"clientOrderId": intent["client_order_id"], "symbol": "BTCUSDT", "side": "SELL",
                             "type": "MARKET", "orderId": 707002, "status": "FILLED", "origQty": quantity,
                             "executedQty": quantity, "cummulativeQuoteQty": quote, "updateTime": 1780000001000}
                    trades = [{"symbol": "BTCUSDT", "id": 909002, "orderId": 707002, "price": "20000",
                               "qty": quantity, "quoteQty": quote, "commission": "0", "commissionAsset": "BTC",
                               "time": 1780000001000, "isBuyer": False}]
                    sold = fills.summarize_spot_market_fill(
                        intent, order, trades, base_asset="BTC", quote_asset="USDT",
                    )
                    sold.update(pre_order_portfolio_signature=baseline["signature"],
                                pre_order_portfolio_qty=baseline["quantity"])
                    self.assertTrue(fills.persist_spot_sell_allocation(
                        scenario.path, sold, namespace=account.namespace,
                    ))
                    account.owner.close()
                    before = scenario.path.read_bytes()
                    result = scenario.recover(account)
                    self.assertTrue(result["already_present"])
                    self.assertTrue(result["portfolio_reconciled"])
                    self.assertEqual(before, scenario.path.read_bytes())
                    payload = json.loads(before)
                    row = payload["entry_allocations"]["BTCUSDT:L"][0]
                    receipt = generations.spot_buy_generation_receipt(row)
                    self.assertEqual(quantity == "0.09996", receipt.terminal)
                    self.assertEqual(account.namespace, payload[namespaces.ACCOUNT_NAMESPACE_KEY])
                    self.assertEqual([], scenario.order_calls)
                finally:
                    scenario.doCleanups()

    def gui_window(self, account):
        window = _OpenSignalWindowStub()
        window.mode_combo = SimpleNamespace(currentText=lambda: "Live")
        window.shared_binance = account.wrapper
        window.config = {}
        window.log = lambda _message: None
        window._allocation_snapshot_session = allocations.AllocationSnapshotSession()
        window._entry_allocations, window._open_position_records = allocations.load_position_allocations(
            this_file=account.home / "unused.py", mode="Live", session=window._allocation_snapshot_session,
        )
        self.assertTrue(window._allocation_snapshot_session.ready)
        with patch.object(account_runtime, "BinanceWrapper", return_value=account.wrapper):
            self.assertIs(account.wrapper, account_runtime._create_binance_wrapper(
                window, api_key=account.wrapper.api_key, api_secret=account.wrapper.api_secret,
                mode="Live", account_type="Spot", connector_backend="binance-sdk-spot",
            ))
        return window

    def test_first_descriptor_requires_owned_empty_header_and_correlated_reload(self):
        account = self.account("fresh", 810007, accepted=False)
        self.assertFalse(self.path.exists())
        window = self.gui_window(account)
        original_handoff = allocations.AllocationSnapshotSession.loaded_handoff
        loaded_tickets = []

        def loaded_handoff(session, ticket):
            self.assertIsNotNone(ticket._completion)
            loaded_tickets.append(ticket)
            return original_handoff(session, ticket)

        with patch.object(allocations.AllocationSnapshotSession, "loaded_handoff", autospec=True,
                          side_effect=loaded_handoff):
            record = account.wrapper._begin_order_intent(PARAMS, market="spot", source="offline-admission")
        self.assertEqual(1, len(loaded_tickets))
        payload = json.loads(self.path.read_bytes())
        self.assertEqual(account.namespace, payload[namespaces.ACCOUNT_NAMESPACE_KEY])
        self.assertEqual({}, payload["entry_allocations"])
        self.assertEqual({}, payload["open_position_records"])
        session = window._allocation_snapshot_session
        self.assertTrue(session.matches_loaded_maps(window._entry_allocations, window._open_position_records))
        self.assertEqual(self.path.read_bytes(), session._bytes)
        self.assertFalse(record["desktop_entry_source"]["absent"])
        self.assertEqual(hashlib.sha256(session._bytes).hexdigest(),
                         record["desktop_entry_source"]["snapshot_signature"])
        self.assertEqual([], self.order_calls)

    def test_second_uid_cannot_capture_same_global_empty_source_as_new_exposure(self):
        a = self.account("first-claim", 810008, accepted=False)
        self.gui_window(a)
        a.wrapper._begin_order_intent(PARAMS, market="spot", source="offline-admission")
        first = self.durable_bytes(a)
        b = self.account("second-claim", 810009, accepted=False)
        before = self.durable_bytes(b)
        ledger_before = self.ledger(b)
        with self.assertRaises(LiveTradingSafetyError):
            self.gui_window(b)
            b.wrapper._begin_order_intent(PARAMS, market="spot", source="offline-admission")
        self.assertEqual(before, self.durable_bytes(b))
        self.assertEqual(ledger_before, self.ledger(b))
        self.assertEqual(first, self.durable_bytes(a))
        self.assertEqual([], self.order_calls)

    def test_existing_financial_ledger_cannot_claim_absent_inventory_as_fresh(self):
        account = self.account("not-fresh", 810014)
        window = self.gui_window(account)
        self.assertFalse(self.path.exists())
        before = self.durable_bytes(account)
        ledger_before = self.ledger(account)
        with self.assertRaises(LiveTradingSafetyError):
            allocations.initialize_spot_allocation_namespace(window, account.wrapper)
        self.assertEqual(before, self.durable_bytes(account))
        self.assertEqual(ledger_before, self.ledger(account))
        self.assertEqual([], self.order_calls)

    def test_submitted_transition_cannot_adopt_new_store_header_after_reload(self):
        account = self.account("submitted", 810012, accepted=False)
        window = self.gui_window(account)
        account.wrapper._begin_order_intent(PARAMS, market="spot", source="offline-admission")
        payload = json.loads(self.path.read_bytes())
        payload[namespaces.ACCOUNT_NAMESPACE_KEY]["store_id"] = str(uuid4())
        self.path.write_text(json.dumps(payload), encoding="utf-8")
        ticket = allocations.AllocationSnapshotLoadTicket()
        session = window._allocation_snapshot_session
        entries, records = allocations.load_position_allocations(
            this_file=self.home / "unused.py", mode="Live", session=session, load_ticket=ticket,
        )
        with session.loaded_handoff(ticket) as accepted:
            self.assertTrue(accepted)
            window._entry_allocations, window._open_position_records = entries, records
        before = self.durable_bytes(account)
        ledger_before = self.ledger(account)
        with self.assertRaises(LiveTradingSafetyError):
            account.wrapper._mark_order_intent_submitted(PARAMS, via="offline-synthetic-boundary")
        self.assertEqual(before, self.durable_bytes(account))
        self.assertEqual(ledger_before, self.ledger(account))
        self.assertEqual([], self.order_calls)

    def test_direct_owned_buy_without_desktop_hooks_cannot_bypass_inventory_namespace(self):
        for source in ("foreign-uid", "foreign-store", "legacy-unscoped", "missing"):
            with self.subTest(source=source):
                scenario = type(self)()
                scenario.setUp()
                try:
                    account = scenario.account("direct-owned", 810015, accepted=False)
                    self.assertIsNone(getattr(account.wrapper, "_desktop_spot_entry_capture", None))
                    if source != "missing":
                        namespace = deepcopy(account.namespace)
                        if source == "foreign-uid":
                            namespace["account_uid"] += 1
                        elif source == "foreign-store":
                            namespace["store_id"] = str(uuid4())
                        self.assertTrue(fills.persist_spot_buy_allocation(
                            scenario.path, scenario.fill,
                            namespace=None if source == "legacy-unscoped" else namespace,
                        ))
                    before = scenario.durable_bytes(account)
                    ledger_before = scenario.ledger(account)
                    with self.assertRaises(LiveTradingSafetyError):
                        account.wrapper._begin_order_intent(PARAMS, market="spot", source="offline-direct")
                    self.assertEqual(before, scenario.durable_bytes(account))
                    self.assertEqual(ledger_before, scenario.ledger(account))
                    # A complete persisted prepared intent cannot bypass the second boundary either.
                    prepared = intents._intent_record(PARAMS, market="spot", source="offline-direct-fixture")
                    intents.validate_order_intent_record(CLIENT, prepared)
                    with ledger_transaction(account.path):
                        ledger = intents._read_ledger(
                            account.path, expected_binding=intents._intent_binding(account.wrapper),
                        )
                        ledger["intents"][CLIENT] = prepared
                        intents.validate_order_intent_ledger(
                            ledger, expected_binding=intents._intent_binding(account.wrapper),
                        )
                        write_ledger(account.path, ledger)
                    before_submitted = scenario.durable_bytes(account)
                    prepared_ledger = scenario.ledger(account)
                    with self.assertRaises(LiveTradingSafetyError):
                        account.wrapper._mark_order_intent_submitted(PARAMS, via="offline-direct-boundary")
                    self.assertEqual(before_submitted, scenario.durable_bytes(account))
                    self.assertEqual(prepared_ledger, scenario.ledger(account))
                    self.assertEqual([], scenario.order_calls)
                finally:
                    scenario.doCleanups()

    def test_direct_owned_opo_without_top_level_side_cannot_bypass_namespace(self):
        for source in ("foreign-uid", "foreign-store", "legacy-unscoped", "missing"):
            with self.subTest(source=source):
                scenario = type(self)()
                scenario.setUp()
                try:
                    account = scenario.account("direct-opo", 810016, accepted=False)
                    self.assertIsNone(getattr(account.wrapper, "_desktop_spot_entry_capture", None))
                    request = build_spot_opo_request(
                        symbol="BTCUSDT", symbol_info=account.venue.get_symbol_info("BTCUSDT"),
                        working_price="20000", working_quantity="0.1", pending_stop_price="19000",
                        list_client_order_id="direct-opo-list", working_client_order_id="direct-opo-buy",
                        pending_client_order_id="direct-opo-stop",
                    )
                    self.assertNotIn("side", request)
                    if source != "missing":
                        namespace = deepcopy(account.namespace)
                        if source == "foreign-uid":
                            namespace["account_uid"] += 1
                        elif source == "foreign-store":
                            namespace["store_id"] = str(uuid4())
                        self.assertTrue(fills.persist_spot_buy_allocation(
                            scenario.path, scenario.fill,
                            namespace=None if source == "legacy-unscoped" else namespace,
                        ))
                    before, ledger_before = scenario.durable_bytes(account), scenario.ledger(account)
                    with self.assertRaises(LiveTradingSafetyError):
                        account.wrapper._begin_spot_opo_intent(request, source="offline-direct-opo")
                    self.assertEqual(before, scenario.durable_bytes(account))
                    self.assertEqual(ledger_before, scenario.ledger(account))
                    now = intents._now()
                    prepared = {
                        "client_order_id": request["listClientOrderId"], "market": "spot",
                        "source": "offline-direct-opo-fixture", "symbol": request["symbol"],
                        "side": "BUY", "type": "OPO", "quantity": request["workingQuantity"],
                        "state": "pending", "created_at": now, "updated_at": now,
                        "request": request, "entry_reconciled": False, "protection_state": "unverified",
                    }
                    intents.validate_order_intent_record(request["listClientOrderId"], prepared)
                    with ledger_transaction(account.path):
                        ledger = intents._read_ledger(
                            account.path, expected_binding=intents._intent_binding(account.wrapper),
                        )
                        ledger["intents"][request["listClientOrderId"]] = prepared
                        intents.validate_order_intent_ledger(
                            ledger, expected_binding=intents._intent_binding(account.wrapper),
                        )
                        write_ledger(account.path, ledger)
                    before_submitted, prepared_ledger = scenario.durable_bytes(account), scenario.ledger(account)
                    with self.assertRaises(LiveTradingSafetyError):
                        account.wrapper._mark_spot_opo_submitted(
                            request["listClientOrderId"], via="offline-direct-opo-boundary",
                        )
                    self.assertEqual(before_submitted, scenario.durable_bytes(account))
                    self.assertEqual(prepared_ledger, scenario.ledger(account))
                    self.assertEqual([], scenario.order_calls)
                finally:
                    scenario.doCleanups()

    def test_generic_bootstrap_cannot_mint_authoritative_spot_acquisition(self):
        row = generations.build_spot_buy_allocation_row(self.fill)
        before = self.path.read_bytes() if self.path.exists() else None
        self.assertFalse(allocations.save_position_allocations(
            {("BTCUSDT", "L"): [row]}, {}, this_file=self.home / "unused.py", mode="Live",
        ))
        self.assertEqual(before, self.path.read_bytes() if self.path.exists() else None)
        self.assertEqual([], self.order_calls)

    def test_owned_market_confirmation_and_replay_require_same_inventory_namespace(self):
        account = self.account("confirmation", 810017)
        self.assertTrue(fills.persist_spot_buy_allocation(self.path, self.fill, namespace=account.namespace))
        before = self.durable_bytes(account)
        full_before = self.ledger(account)
        result = account.wrapper._mark_order_intent_portfolio_reconciled(
            CLIENT, portfolio_signature=self.fill["signature"], portfolio_quantity=self.fill["net_qty"],
        )
        self.assertTrue(result["portfolio_reconciled"])
        self.assertFalse(result["already_reconciled"])
        marked = self.ledger(account)
        self.assertEqual(set(full_before), set(marked))
        self.assertEqual(set(full_before["intents"]), set(marked["intents"]))
        for key, value in full_before.items():
            if key != "intents":
                self.assertEqual(value, marked[key])
        for key, value in full_before["intents"][CLIENT].items():
            if key not in {"portfolio_reconciled", "updated_at"}:
                self.assertEqual(value, marked["intents"][CLIENT][key])
        self.assertEqual((before[0], before[2]), (self.durable_bytes(account)[0], self.durable_bytes(account)[2]))
        replay_before = self.durable_bytes(account)
        self.assertTrue(account.wrapper._mark_order_intent_portfolio_reconciled(
            CLIENT, portfolio_signature=self.fill["signature"], portfolio_quantity=self.fill["net_qty"],
        )["already_reconciled"])
        self.assertEqual(replay_before, self.durable_bytes(account))
        foreign = json.loads(self.path.read_bytes())
        foreign[namespaces.ACCOUNT_NAMESPACE_KEY]["account_uid"] += 1
        self.path.write_text(json.dumps(foreign), encoding="utf-8")
        rejected_before = self.durable_bytes(account)
        with self.assertRaises(LiveTradingSafetyError):
            account.wrapper._mark_order_intent_portfolio_reconciled(
                CLIENT, portfolio_signature=self.fill["signature"], portfolio_quantity=self.fill["net_qty"],
            )
        self.assertEqual(rejected_before, self.durable_bytes(account))
        self.assertEqual(marked, self.ledger(account))
        self.assertEqual([], self.order_calls)

    def test_retained_administration_metadata_cannot_replace_actual_live_exclusion(self):
        account = self.account("admin-exclusion", 810018)
        account.owner.close()
        wrapper = account.wrapper
        admin = SimpleNamespace(
            api_key=wrapper.api_key, api_secret=wrapper.api_secret, client=wrapper.client,
            mode="Live", account_type="Spot", _enforce_spot_execution_owner=True,
            _operator_spot_account_uid=account.uid,
            _verified_spot_account_context=wrapper._verified_spot_account_context,
            _spot_inventory_administration_path=account.path,
        )
        before = self.durable_bytes(account)
        with self.assertRaises(LiveTradingSafetyError):
            namespace_runtime.namespace_for_current_ledger(admin)
        with owner_administration_lock(account.path):
            self.assertEqual(account.namespace, namespace_runtime.namespace_for_current_ledger(admin))
        with self.assertRaises(LiveTradingSafetyError):
            namespace_runtime.namespace_for_current_ledger(admin)
        self.assertEqual(before, self.durable_bytes(account))
        self.assertEqual([], self.order_calls)

    def test_non_spot_exposure_is_fenced_by_bound_or_legacy_protected_inventory(self):
        account = self.account("non-spot", 810013)
        self.assertTrue(fills.persist_spot_buy_allocation(self.path, self.fill, namespace=account.namespace))
        original = json.loads(self.path.read_bytes())
        for scope in ("bound", "legacy-unscoped"):
            with self.subTest(scope=scope):
                payload = deepcopy(original)
                if scope == "legacy-unscoped":
                    payload.pop(namespaces.ACCOUNT_NAMESPACE_KEY)
                self.path.write_text(json.dumps(payload), encoding="utf-8")
                before = self.durable_bytes(account)
                window = SimpleNamespace()
                other = SimpleNamespace(mode="Live", account_type="Futures")
                self.assertFalse(allocations.non_spot_desktop_exposure_allowed(window, other))
                self.assertEqual(before, self.durable_bytes(account))
        self.assertEqual([], self.order_calls)

    def test_plain_paper_bootstrap_remains_unowned_and_compatible(self):
        self.assertTrue(allocations.save_position_allocations(
            {}, {}, this_file=self.home / "unused.py", mode="Paper",
        ))
        payload = json.loads(self.path.read_bytes())
        self.assertNotIn(namespaces.ACCOUNT_NAMESPACE_KEY, payload)
        self.assertEqual("Paper", payload["mode"])
        self.assertTrue(allocations.non_spot_desktop_exposure_allowed(
            SimpleNamespace(), SimpleNamespace(mode="Paper", account_type="Futures"),
        ))
        self.assertEqual([], self.order_calls)

    def test_credential_rotation_and_indexed_migration_preserve_inventory_identity(self):
        account = self.account("rotation", 810010)
        self.assertTrue(fills.persist_spot_buy_allocation(self.path, self.fill, namespace=account.namespace))
        account.owner.close()
        self.assertTrue(self.recover(account)["portfolio_reconciled"])
        inventory_before = self.path.read_bytes()
        original = self.ledger(account)
        next_key, next_secret = "offline-rotation-key", "offline-rotation-secret"
        self.accounts[next_key] = account.uid, next_secret
        account.wrapper = self.new_wrapper(next_key, next_secret, account.home, account.venue)
        with self.account_home(account):
            rotate_spot_owner_credentials(
                account.wrapper, acknowledgement=PROVISION_ACK, reconciliation_reference="synthetic-rotation",
            )
            rotated = self.ledger(account)
            self.assertEqual(original["store_id"], rotated["store_id"])
            self.assertEqual(original["intents"], rotated["intents"])
            self.assertNotEqual(original["binding"], rotated["binding"])
            self.assertEqual(account.namespace, namespaces.make_namespace(account.uid, rotated["store_id"]))
            result = migration.migrate_spot_indexed_intent_store(
                account.wrapper, acknowledgement=PROVISION_ACK, reconciliation_reference="synthetic-migration",
            )
            migrated = self.ledger(account)
        self.assertEqual(rotated, migrated)
        self.assertEqual(inventory_before, self.path.read_bytes())
        self.assertEqual(account.namespace, json.loads(inventory_before)[namespaces.ACCOUNT_NAMESPACE_KEY])
        self.assertEqual(3, result["format_version"])
        self.assertEqual([], self.order_calls)


if __name__ == "__main__":
    unittest.main()
