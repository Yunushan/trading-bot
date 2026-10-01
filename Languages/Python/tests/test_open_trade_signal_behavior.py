from __future__ import annotations

import sys
import unittest
import copy
import tempfile
import socket
import hashlib
import hmac
from urllib.parse import urlencode, urlparse
from unittest.mock import patch
from datetime import datetime, timezone
from pathlib import Path
from types import SimpleNamespace


PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from app.gui.trade.signal_open_runtime import handle_non_close_trade_signal  # noqa: E402
from app.gui.trade import signal_common_runtime  # noqa: E402
from app.gui.shared.allocation_persistence import (  # noqa: E402
    AllocationSnapshotSession, load_position_allocations, save_position_allocations,
)
from app.integrations.exchanges.binance.orders.order_intent_store import ledger_transaction  # noqa: E402
from app.integrations.exchanges.binance.orders import spot_fill_recovery_runtime as recovery  # noqa: E402
from app.integrations.exchanges.binance.orders.order_intent_provisioning import (  # noqa: E402
    PROVISION_ACK, provision_order_intent_store,
)
from app.integrations.exchanges.binance.wrapper import BinanceWrapper  # noqa: E402
from app.settings.live_safety import LIVE_TRADING_ACKNOWLEDGEMENT  # noqa: E402
from app.core.strategy.orders.strategy_signal_order_result_runtime import _emit_signal_order_info  # noqa: E402


class _OpenSignalWindowStub:
    def __init__(self) -> None:
        self._entry_allocations: dict[tuple[str, str], list[dict]] = {}
        self._pending_close_times: dict[tuple[str, str], str] = {}
        self._open_position_records: dict[tuple[str, str], dict] = {}
        self._processed_open_events = None
        self._is_stopping_engines = False

    def _parse_any_datetime(self, value):
        if isinstance(value, datetime):
            return value
        if isinstance(value, str):
            try:
                return datetime.fromisoformat(value)
            except Exception:
                return None
        return None

    def _format_display_time(self, value) -> str:
        if isinstance(value, datetime):
            return value.astimezone(timezone.utc).isoformat(timespec="seconds")
        return str(value)


def _normalize_interval(_self, value):
    if value is None:
        return None
    text = str(value).strip()
    return text.lower() or None


def _side_key_from_value(value) -> str:
    return "L" if str(value).upper() in {"BUY", "LONG"} else "S"


def _resolve_trigger_indicators(raw, _desc=None):
    if isinstance(raw, (list, tuple, set)):
        return [str(token).strip().lower() for token in raw if str(token).strip()]
    return []


def _normalize_trigger_actions_map(raw):
    return dict(raw) if isinstance(raw, dict) else {}


def _ctx() -> dict:
    return {
        "sym": "BTCUSDT",
        "interval": "1m",
        "side_for_key": "BUY",
        "side_key": "L",
        "sym_upper": "BTCUSDT",
        "status": "placed",
        "ok_flag": True,
    }


def _dispatch(
    window: _OpenSignalWindowStub,
    order_info: dict,
    *,
    persist_trade_allocations=None,
    sync_open_position_snapshot=None,
    saver=None,
) -> None:
    handle_non_close_trade_signal(
        window,
        order_info,
        _ctx(),
        alloc_map=window._entry_allocations,
        pending_close=window._pending_close_times,
        resolve_trigger_indicators=_resolve_trigger_indicators,
        normalize_trigger_actions_map=_normalize_trigger_actions_map,
        save_position_allocations=saver or (lambda *_args, **_kwargs: True),
        normalize_interval=_normalize_interval,
        side_key_from_value=_side_key_from_value,
        refresh_trade_views=lambda *_args, **_kwargs: None,
        persist_trade_allocations=persist_trade_allocations or (lambda *_args, **_kwargs: True),
        sync_open_position_snapshot=sync_open_position_snapshot or (lambda *_args, **_kwargs: None),
    )


class OpenTradeSignalBehaviorTests(unittest.TestCase):
    def test_interrupted_open_mutation_rolls_back_and_retains_confirmed_event(self):
        window = _OpenSignalWindowStub()
        order = {"side": "BUY", "client_order_id": "interrupted-buy", "qty": 0.25,
                 "avg_price": 100.0, "status": "placed", "ok": True}
        def interrupted_sync(*_args, **_kwargs):
            window._open_position_records[("BTCUSDT", "L")] = {"data": {"qty": 0.25}}
            raise KeyboardInterrupt()
        with self.assertRaises(KeyboardInterrupt):
            _dispatch(window, order, sync_open_position_snapshot=interrupted_sync)
        self.assertEqual({}, window._entry_allocations)
        self.assertEqual({}, window._open_position_records)
        self.assertTrue(window._pending_allocation_reconciliations[("BTCUSDT", "L")])
        self.assertIsNone(window._active_trade_event_receipt)

    def test_real_primary_buy_event_publishes_fee_aware_quantity_then_actual_intent_marker(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp).resolve()
            this_file = root / "Languages" / "Python" / "app" / "gui" / "window_shell.py"
            this_file.parent.mkdir(parents=True)
            allocation_path = this_file.parents[2] / "data" / ".trading_bot_allocations.json"
            audit_path = root / "offline-audit.jsonl"
            uid = 12345678
            sdk = SimpleNamespace(get_symbol_info=lambda symbol: {
                "symbol": symbol, "baseAsset": "BTC", "quoteAsset": "USDT"})
            def account_get(url, *, params, headers, timeout):
                self.assertEqual("/api/v3/account", urlparse(url).path)
                self.assertEqual({"X-MBX-APIKEY": "offline-key"}, headers)
                unsigned = {key: value for key, value in params.items() if key != "signature"}
                signature = hmac.new(b"offline-secret", urlencode(unsigned).encode(), hashlib.sha256).hexdigest()
                self.assertTrue(hmac.compare_digest(signature, params["signature"]))
                self.assertTrue(timeout)
                return SimpleNamespace(status_code=200, json=lambda: {"uid": uid, "accountType": "SPOT"})
            with patch.object(Path, "home", return_value=root), \
                    patch.object(socket.socket, "connect", side_effect=AssertionError("Network forbidden")), \
                    patch.object(socket.socket, "connect_ex", side_effect=AssertionError("Network forbidden")), \
                    patch("app.integrations.exchanges.binance.wrapper.BinanceSDKSpotClient", return_value=sdk), \
                    patch("app.integrations.exchanges.binance.transport.http_request_runtime.requests.get", side_effect=account_get), \
                    patch("app.gui.shared.allocation_persistence.get_position_allocations_path", return_value=allocation_path):
                admin = SimpleNamespace(_order_audit_log_path=audit_path, api_key="offline-key", mode="Live",
                                        account_type="SPOT", _enforce_spot_execution_owner=True, _operator_spot_account_uid=uid)
                provision_order_intent_store(admin, acknowledgement=PROVISION_ACK)
                wrapper = BinanceWrapper("offline-key", "offline-secret", mode="Live", account_type="Spot",
                                         connector_backend="binance-sdk-spot", live_safety_config={
                                             "live_trading_enabled": True, "live_trading_acknowledgement": LIVE_TRADING_ACKNOWLEDGEMENT,
                                             "position_pct": 2.0, "live_trading_max_leverage": 20,
                                             "live_trading_max_position_pct": 10.0, "live_trading_max_session_orders": 10,
                                             "order_audit_enabled": True, "order_audit_log_path": str(audit_path)})
                try:
                    params = {"newClientOrderId": "primary-fee-buy", "symbol": "BTCUSDT", "side": "BUY", "type": "MARKET", "quantity": "0.1"}
                    wrapper._begin_order_intent(params, market="spot", source="offline-gui-proof")
                    wrapper._mark_order_intent_submitted(params, via="offline-gui-proof")
                    response = {"clientOrderId": "primary-fee-buy", "symbol": "BTCUSDT", "side": "BUY", "type": "MARKET",
                                "orderId": 75, "status": "FILLED", "origQty": "0.1", "executedQty": "0.1",
                                "cummulativeQuoteQty": "2000", "updateTime": 1780000000000,
                                "fills": [{"tradeId": 101, "price": "20000", "qty": "0.04", "commission": "0.00004", "commissionAsset": "BTC"},
                                          {"tradeId": 102, "price": "20000", "qty": "0.06", "commission": "0.2", "commissionAsset": "USDT"}]}
                    wrapper._mark_order_intent_accepted(params, via="offline-gui-proof", result=response)
                    events = []
                    strategy = SimpleNamespace(binance=wrapper, trade_cb=events.append, log=lambda _message: None)
                    _emit_signal_order_info(strategy, cw={"symbol": "BTCUSDT", "interval": "1m"}, side="BUY",
                                            order_res={"ok": True, "execution_confirmed": True, "submitted_qty": "0.1", "info": response},
                                            price=20000.0, qty_display=0.1, trigger_labels=[], trigger_desc_for_order=None,
                                            trigger_signature=[], context_key=None, order_event_uid="primary-event",
                                            trigger_actions_for_order={}, origin_timestamp=None, leverage_used=1)
                    self.assertEqual(1, len(events))
                    event = events[0]
                    self.assertFalse(event["reconciliation_required"])
                    self.assertTrue(event["execution_confirmed"])
                    self.assertEqual("0.09996", event["spot_fill_recovery"]["net_qty"])
                    self.assertEqual(0.09996, event["executed_qty"])
                    window = _OpenSignalWindowStub()
                    window.mode_combo = SimpleNamespace(currentText=lambda: "Live")
                    window.shared_binance = wrapper
                    session = window._allocation_snapshot_session = AllocationSnapshotSession()
                    load_position_allocations(this_file=this_file, mode="Live", session=session)
                    def saver(allocations, records, **kwargs):
                        return save_position_allocations(allocations, records, this_file=this_file, **kwargs)
                    _dispatch(window, dict(event, reconciliation_required=True),
                              persist_trade_allocations=signal_common_runtime._persist_trade_allocations,
                              sync_open_position_snapshot=signal_common_runtime._sync_open_position_snapshot, saver=saver)
                    self.assertEqual({}, window._entry_allocations)
                    self.assertFalse(allocation_path.exists())
                    self.assertTrue(window._pending_allocation_reconciliations[("BTCUSDT", "L")])
                    self.assertIsNot(wrapper._get_order_intent_record("primary-fee-buy").get("portfolio_reconciled"), True)
                    _dispatch(window, event, persist_trade_allocations=signal_common_runtime._persist_trade_allocations,
                              sync_open_position_snapshot=signal_common_runtime._sync_open_position_snapshot, saver=saver)
                    self.assertFalse(getattr(window, "_pending_trade_reconciliation", {}))
                    record = wrapper._get_order_intent_record("primary-fee-buy")
                    self.assertTrue(record["portfolio_reconciled"])
                    self.assertEqual("0.09996", record["portfolio_qty"])
                    committed = allocation_path.read_bytes()
                    self.assertEqual("0.09996", session._snapshot["gui_trade_event_receipts"][0]["quantity"])
                    wrapper._mark_order_intent_portfolio_reconciled("primary-fee-buy", portfolio_signature=event["spot_fill_recovery"]["signature"], portfolio_quantity="0.09996")
                    self.assertEqual(committed, allocation_path.read_bytes())
                    self.assertEqual(committed, session._bytes)
                finally:
                    owner = getattr(wrapper, "_spot_execution_owner", None)
                    if owner is not None and owner.fd is not None:
                        owner.close()

    def test_actual_owned_sell_recovery_survives_late_original_buy_after_fresh_load(self):
        for sold_qty in ("0.04", "0.1"):
            with self.subTest(sold_qty=sold_qty), tempfile.TemporaryDirectory() as tmp:
                this_file = Path(tmp) / "Languages" / "Python" / "app" / "gui" / "window_shell.py"
                this_file.parent.mkdir(parents=True)
                allocation_path = this_file.parents[2] / "data" / ".trading_bot_allocations.json"
                allocation_path.parent.mkdir()
                buy = {"symbol": "BTCUSDT", "client_order_id": "owned-buy", "order_id": 75,
                       "trade_ids": [101], "trade_count": 1, "gross_qty": "0.1", "net_qty": "0.1",
                       "gross_quote_qty": "2000", "net_quote_cost": "2000", "average_cost": "20000",
                       "commissions": [], "base_asset": "BTC", "quote_asset": "USDT",
                       "fill_time_ms": 1780000000000, "signature": "a" * 64}
                self.assertTrue(recovery.persist_spot_buy_allocation(allocation_path, buy))
                baseline = recovery.spot_live_allocation_baseline(allocation_path, symbol="BTCUSDT")
                assert baseline is not None
                sell = {"symbol": "BTCUSDT", "client_order_id": "owned-sell", "order_id": 76,
                        "side": "SELL", "trade_ids": [201], "gross_qty": sold_qty, "portfolio_qty": sold_qty,
                        "gross_quote_qty": str(float(sold_qty) * 20000), "base_fee_qty": "0", "quote_fee_qty": "0",
                        "net_quote_proceeds": str(float(sold_qty) * 20000), "commissions": [], "base_asset": "BTC",
                        "quote_asset": "USDT", "fill_time_ms": 1780000001000, "signature": "b" * 64,
                        "pre_order_portfolio_signature": baseline["signature"], "pre_order_portfolio_qty": baseline["quantity"]}
                self.assertTrue(recovery.persist_spot_sell_allocation(allocation_path, sell))
                committed = allocation_path.read_bytes()
                window = _OpenSignalWindowStub()
                window.mode_combo = SimpleNamespace(currentText=lambda: "Live")
                window._allocation_snapshot_session = AllocationSnapshotSession()
                window._entry_allocations, window._open_position_records = load_position_allocations(
                    this_file=this_file, mode="Live", session=window._allocation_snapshot_session)
                loaded = copy.deepcopy((window._entry_allocations, window._open_position_records))
                publications = []
                def saver(allocations, records, **kwargs):
                    publications.append(True)
                    return save_position_allocations(allocations, records, this_file=this_file, **kwargs)
                _dispatch(window, {"side": "BUY", "client_order_id": "owned-buy", "order_id": "75",
                                   "qty": 0.1, "avg_price": 20000.0, "exchange_status": "FILLED"},
                          saver=saver, persist_trade_allocations=signal_common_runtime._persist_trade_allocations,
                          sync_open_position_snapshot=signal_common_runtime._sync_open_position_snapshot)
                self.assertEqual(committed, allocation_path.read_bytes())
                self.assertEqual(loaded, (window._entry_allocations, window._open_position_records))
                self.assertEqual([], publications)
                self.assertTrue(window._pending_allocation_reconciliations[("BTCUSDT", "L")])

    def test_real_publisher_commits_before_ledger_callback_and_restart_buy_replay(self):
        with tempfile.TemporaryDirectory() as tmp:
            this_file = Path(tmp) / "Languages" / "Python" / "app" / "gui" / "window_shell.py"
            this_file.parent.mkdir(parents=True)
            allocation_path = this_file.parents[2] / "data" / ".trading_bot_allocations.json"
            window = _OpenSignalWindowStub()
            window.mode_combo = SimpleNamespace(currentText=lambda: "Live")
            window._allocation_snapshot_session = AllocationSnapshotSession()
            window._entry_allocations, window._open_position_records = load_position_allocations(
                this_file=this_file, mode="Live", session=window._allocation_snapshot_session)
            markers = []
            def mark(*_args, **_kwargs):
                with ledger_transaction(allocation_path):
                    self.assertTrue(allocation_path.is_file())
                    markers.append("marked")
            window.shared_binance = SimpleNamespace(_mark_order_intent_portfolio_reconciled=mark)
            def saver(allocations, records, **kwargs):
                return save_position_allocations(allocations, records, this_file=this_file, **kwargs)
            order = {"side": "BUY", "client_order_id": "real-buy", "order_id": "71",
                     "qty": 0.25, "avg_price": 100.0, "status": "placed", "ok": True,
                     "exchange_status": "FILLED", "spot_fill_recovery": {"signature": "a" * 64, "net_qty": "0.25"}}
            _dispatch(window, order, persist_trade_allocations=signal_common_runtime._persist_trade_allocations,
                      sync_open_position_snapshot=signal_common_runtime._sync_open_position_snapshot, saver=saver)
            self.assertEqual(["marked"], markers)
            committed = allocation_path.read_bytes()
            restarted = _OpenSignalWindowStub()
            restarted.mode_combo = window.mode_combo
            restarted.shared_binance = window.shared_binance
            restarted._allocation_snapshot_session = AllocationSnapshotSession()
            restarted._entry_allocations, restarted._open_position_records = load_position_allocations(
                this_file=this_file, mode="Live", session=restarted._allocation_snapshot_session)
            _dispatch(restarted, order, persist_trade_allocations=signal_common_runtime._persist_trade_allocations,
                      sync_open_position_snapshot=signal_common_runtime._sync_open_position_snapshot, saver=saver)
            self.assertEqual(committed, allocation_path.read_bytes())
            self.assertEqual(1, len(restarted._entry_allocations[("BTCUSDT", "L")]))
            self.assertEqual(["marked", "marked"], markers)
            _dispatch(restarted, dict(order, qty=0.5), persist_trade_allocations=signal_common_runtime._persist_trade_allocations,
                      sync_open_position_snapshot=signal_common_runtime._sync_open_position_snapshot, saver=saver)
            self.assertEqual(committed, allocation_path.read_bytes())
            self.assertEqual(1, len(restarted._pending_trade_reconciliation))
            _dispatch(restarted, order, persist_trade_allocations=signal_common_runtime._persist_trade_allocations,
                      sync_open_position_snapshot=signal_common_runtime._sync_open_position_snapshot, saver=saver)
            self.assertEqual(1, len(restarted._pending_trade_reconciliation))
            self.assertEqual(1, len(restarted._pending_allocation_reconciliations[("BTCUSDT", "L")]))

    def test_distinct_unidentifiable_confirmed_events_are_retained_in_memory(self):
        window = _OpenSignalWindowStub()
        for price in (100.0, 101.0):
            _dispatch(window, {"side": "BUY", "qty": 0.25, "avg_price": price, "status": "placed", "ok": True})
        self.assertEqual({}, window._entry_allocations)
        self.assertEqual(2, len(window._pending_trade_reconciliation))
        self.assertEqual(2, len(window._pending_allocation_reconciliations[("BTCUSDT", "L")]))

    def test_raising_open_publisher_rolls_back_and_does_not_mark_buy_reconciled(self):
        window = _OpenSignalWindowStub()
        markers = []
        window.shared_binance = SimpleNamespace(_mark_order_intent_portfolio_reconciled=lambda *_a, **_kw: markers.append(True))
        order = {"side": "BUY", "client_order_id": "raising-buy", "qty": 0.25,
                 "exchange_status": "FILLED", "spot_fill_recovery": {"signature": "a" * 64, "net_qty": "0.25"}}
        def persist(*_args):
            raise OSError("offline publication failure")
        _dispatch(window, order, persist_trade_allocations=persist)
        self.assertEqual({}, window._entry_allocations)
        self.assertEqual([], markers)
        self.assertTrue(window._pending_allocation_reconciliations[("BTCUSDT", "L")])

    def test_late_original_buy_does_not_reset_consumed_recovery_inventory(self):
        for status, remaining_qty in (("Active", 0.04), ("Closed", 0.0999)):
            with self.subTest(status=status):
                window = _OpenSignalWindowStub()
                original = {
                    "client_order_id": "client-recovered", "order_id": "41",
                    "trade_id": "client-recovered", "status": status, "qty": remaining_qty,
                    "entry_price": 101.0, "margin_usdt": 4.04,
                    "spot_fill_recovery": {"signature": "a" * 64, "net_qty": "0.0999"},
                    "spot_sell_recoveries": [{"consumed_qty": "0.0599", "signature": "b" * 64}],
                }
                window._entry_allocations[("BTCUSDT", "L")] = [copy.deepcopy(original)]
                publications = []
                _dispatch(window, {
                    "side": "BUY", "client_order_id": "client-recovered", "order_id": "41",
                    "qty": 0.0999, "avg_price": 100.0, "status": "placed", "ok": True,
                    "spot_fill_recovery": {"signature": "a" * 64, "net_qty": "0.0999"},
                }, persist_trade_allocations=lambda *_args: publications.append(True) or True)
                self.assertEqual(original, window._entry_allocations[("BTCUSDT", "L")][0])
                self.assertEqual([], publications)

    def test_failed_open_publication_preserves_event_for_explicit_retry(self):
        window = _OpenSignalWindowStub()
        order = {"side": "BUY", "client_order_id": "retry-open", "qty": 0.25,
                 "avg_price": 100.0, "status": "placed", "ok": True}
        _dispatch(window, order, persist_trade_allocations=lambda *_args: False)
        self.assertEqual({}, window._entry_allocations)
        self.assertTrue(getattr(window, "_pending_trade_reconciliation", {}))
        _dispatch(window, order, persist_trade_allocations=lambda *_args: True)
        self.assertEqual(1, len(window._entry_allocations[("BTCUSDT", "L")]))
        self.assertFalse(window._pending_trade_reconciliation)

    def test_filled_spot_buy_is_marked_only_after_snapshot_sync_and_durable_save(self):
        window = _OpenSignalWindowStub()
        events = []

        def mark(client_order_id, *, portfolio_signature, portfolio_quantity):
            events.append(("mark", client_order_id, portfolio_signature, portfolio_quantity))

        window.shared_binance = SimpleNamespace(_mark_order_intent_portfolio_reconciled=mark)

        def sync(*_args, **_kwargs):
            events.append("sync")

        def persist(*_args, **_kwargs):
            events.append("persist")
            return True

        _dispatch(
            window,
            {
                "symbol": "BTCUSDT", "interval": "1m", "side": "BUY",
                "qty": 0.0999, "executed_qty": 0.0999, "avg_price": 20020.02002002,
                "status": "placed", "ok": True, "exchange_status": "FILLED",
                "client_order_id": "client-spot-buy", "reconciliation_required": False,
                "spot_fill_recovery": {"signature": "a" * 64, "net_qty": "0.0999"},
            },
            persist_trade_allocations=persist,
            sync_open_position_snapshot=sync,
        )

        self.assertEqual("sync", events[0])
        self.assertEqual("persist", events[1])
        self.assertEqual(
            ("mark", "client-spot-buy", "a" * 64, "0.0999"),
            events[2],
        )

    def test_distinct_context_slots_without_exchange_ids_preserve_live_allocations(self):
        window = _OpenSignalWindowStub()
        base_order = {
            "symbol": "BTCUSDT",
            "interval": "1m",
            "side": "BUY",
            "qty": 0.25,
            "executed_qty": 0.25,
            "avg_price": 100.0,
            "price": 100.0,
            "leverage": 5,
            "status": "placed",
            "ok": True,
            "time": "2026-04-05T12:30:00+00:00",
            "trigger_indicators": ["rsi"],
            "trigger_signature": ["rsi"],
            "trigger_desc": "rsi",
        }

        first_order = dict(base_order, context_key="1m:BUY:rsi|slot-a", slot_id="slot-a")
        second_order = dict(base_order, context_key="1m:BUY:rsi|slot-b", slot_id="slot-b")

        _dispatch(window, first_order)
        _dispatch(window, second_order)

        allocations = window._entry_allocations[("BTCUSDT", "L")]
        self.assertEqual(2, len(allocations))
        self.assertEqual({"slot-a", "slot-b"}, {entry.get("slot_id") for entry in allocations})
        self.assertEqual(
            {"1m:BUY:rsi|slot-a", "1m:BUY:rsi|slot-b"},
            {entry.get("context_key") for entry in allocations},
        )
        self.assertEqual(2, len({entry.get("trade_id") for entry in allocations}))

    def test_distinct_client_order_ids_preserve_live_allocations(self):
        window = _OpenSignalWindowStub()
        base_order = {
            "symbol": "BTCUSDT",
            "interval": "1m",
            "side": "BUY",
            "qty": 0.25,
            "executed_qty": 0.25,
            "avg_price": 100.0,
            "price": 100.0,
            "leverage": 5,
            "status": "placed",
            "ok": True,
            "time": "2026-04-05T12:31:00+00:00",
            "trigger_indicators": ["rsi"],
            "trigger_signature": ["rsi"],
            "trigger_desc": "rsi",
        }

        _dispatch(window, dict(base_order, client_order_id="client-a"))
        _dispatch(window, dict(base_order, client_order_id="client-b"))

        allocations = window._entry_allocations[("BTCUSDT", "L")]
        self.assertEqual(2, len(allocations))
        self.assertEqual({"client-a", "client-b"}, {entry.get("client_order_id") for entry in allocations})
        self.assertEqual({"client-a", "client-b"}, {entry.get("trade_id") for entry in allocations})


if __name__ == "__main__":
    unittest.main()
