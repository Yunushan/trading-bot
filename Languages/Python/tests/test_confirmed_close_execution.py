"""Exercise close accounting with real runtime code and an offline exchange."""
from __future__ import annotations

import socket
import tempfile
import time
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from app.config import build_default_config
from app.core.strategy import StrategyEngine
from app.core.strategy.positions.close_execution import _close_leg_entry
from app.integrations.exchanges.binance.orders import order_intent_runtime as intents
from app.integrations.exchanges.binance.orders.order_intent_provisioning import PROVISION_ACK, provision_order_intent_store
from app.integrations.exchanges.binance.orders.order_fallback_runtime import _futures_create_order_with_fallback
from app.integrations.exchanges.binance.positions.futures_position_close_runtime import close_futures_leg_exact
from app.settings.live_safety import LiveTradingSafetyError
from trading_core.orders import confirmed_close_quantity, order_execution_from_response


class OfflineCloseExchange:
    account_type = "FUTURES"
    mode = "Live"
    _futures_create_order_with_fallback = _futures_create_order_with_fallback
    close_futures_leg_exact = close_futures_leg_exact
    _begin_order_intent = intents._begin_order_intent
    _mark_order_intent_submitted = intents._mark_order_intent_submitted
    _mark_order_intent_accepted = intents._mark_order_intent_accepted
    _mark_order_intent_unknown = intents._mark_order_intent_unknown

    def __init__(self, directory):
        self._order_audit_log_path = Path(directory) / "synthetic-audit.jsonl"
        self.api_key = "unit-api-key"
        provision_order_intent_store(self, acknowledgement=PROVISION_ACK)
        self.status = "FILLED"
        self.executed_qty = None
        self.submit_error = None
        self.sent = []
        self.client = SimpleNamespace(
            futures_create_order=self.create_order,
            futures_cancel_all_open_orders=lambda **kw: {"code": 200},
        )

    def create_order(self, **params):
        self.sent.append(params)
        if self.submit_error:
            raise self.submit_error
        return {
            "orderId": 1234, "status": self.status, "symbol": params["symbol"],
            "side": params["side"], "clientOrderId": params["newClientOrderId"],
            "origQty": params["quantity"],
            "executedQty": str(self.executed_qty if self.executed_qty is not None else params["quantity"]),
        }

    def get_futures_dual_side(self):
        return False

    def get_futures_symbol_filters(self, symbol):
        return {"stepSize": 0.001}

    def list_open_futures_positions(self, **kwargs):
        return [{"symbol": "BTCUSDT", "positionAmt": "3", "positionSide": "BOTH"}]

    def _format_quantity_for_order(self, quantity, step):
        return str(quantity)

    def _summarize_futures_order_fills(self, symbol, order_id):
        return {}

    def _invalidate_futures_positions_cache(self):
        pass

    def _testnet_order_fallback_client(self):
        return None


class ConfirmedCloseExecutionTests(unittest.TestCase):
    def setUp(self):
        network = patch.object(socket.socket, "connect", side_effect=AssertionError("Network forbidden"))
        network.start()
        self.addCleanup(network.stop)
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.exchange = OfflineCloseExchange(temporary.name)
        StrategyEngine._GLOBAL_PAUSE.clear()
        StrategyEngine._GLOBAL_PAUSE_FALLBACK = False
        self.addCleanup(StrategyEngine._GLOBAL_PAUSE.clear)
        config = build_default_config()
        config.update(symbol="BTCUSDT", interval="1m", account_type="FUTURES")
        self.engine = StrategyEngine(self.exchange, config, log_callback=lambda message: None)
        self.key = ("BTCUSDT", "1m", "BUY")
        self.engine._build_close_event_payload = lambda *a, **kw: {}
        self.engine._notify_interval_closed = lambda *a, **kw: None
        self.flips = []
        self.engine._queue_flip_on_close = lambda *a, **kw: self.flips.append(a)

    def append(self, ledger_id="target", qty=1.0):
        entry = {
            "ledger_id": ledger_id, "qty": qty, "entry_price": 100.0,
            "margin_usdt": qty * 10.0, "timestamp": time.time(),
            "trigger_signature": ("rsi", "macd"),
        }
        self.engine._append_leg_entry(self.key, entry)
        return entry

    def close(self, entry, limit=None):
        return _close_leg_entry(
            self.engine, {"symbol": "BTCUSDT", "interval": "1m"}, self.key,
            entry, "BUY", "SELL", None,
            loss_usdt=0.0, price_pct=0.0, margin_pct=0.0,
            qty_limit=limit, queue_flip=True,
        )

    def test_filled_close_positive_control(self):
        self.assertEqual(1.0, self.close(self.append()))
        self.assertEqual(1, len(self.exchange.sent))
        self.assertNotIn(self.key, self.engine._leg_ledger)
        self.assertEqual(1, len(self.flips))
        self.assertEqual("RESULT", self.exchange.sent[0]["newOrderRespType"])

    def test_new_ack_keeps_all_exposure_and_requires_reconciliation(self):
        self.exchange.status = "NEW"
        self.exchange.executed_qty = 0.0
        self.assertEqual(0.0, self.close(self.append()))
        self.assertEqual(1.0, self.engine._leg_entries(self.key)[0]["qty"])
        self.assertTrue(self.engine._ledger_reconciliation_required)
        self.assertEqual([], self.flips)
        self.assertEqual(1, len(self.exchange.sent))

    def test_partial_fill_accounts_only_confirmed_execution(self):
        self.exchange.status = "PARTIALLY_FILLED"
        self.exchange.executed_qty = 0.25
        self.assertEqual(0.25, self.close(self.append()))
        self.assertEqual(0.75, self.engine._leg_entries(self.key)[0]["qty"])
        self.assertTrue(self.engine._ledger_reconciliation_required)
        self.assertEqual([], self.flips)
        self.assertEqual(1, len(self.exchange.sent))

    def test_pending_close_blocks_other_intents_and_cannot_be_retried(self):
        self.exchange.status = "PARTIALLY_FILLED"
        self.exchange.executed_qty = 0.25
        self.close(self.append())
        current = self.engine._leg_entries(self.key)[0]
        self.assertEqual(0.0, self.close(current))
        self.assertEqual(1, len(self.exchange.sent))
        status = intents.get_order_intent_status(self.exchange)
        self.assertEqual(1, status["unresolved_count"])
        with self.assertRaises(LiveTradingSafetyError):
            intents._begin_order_intent(
                self.exchange, dict(self.exchange.sent[0], newClientOrderId="another-close"),
                market="futures", source="test",
            )

    def test_reconciliation_keeps_unfinished_close_blocked_until_terminal(self):
        self.exchange.status = "NEW"
        self.exchange.executed_qty = 0.0
        self.close(self.append())
        client_id = self.exchange.sent[0]["newClientOrderId"]
        response = {"clientOrderId": client_id, "symbol": "BTCUSDT", "side": "SELL", "orderId": 1234,
                    "status": "PARTIALLY_FILLED", "executedQty": "0.25", "origQty": "1.0"}
        self.exchange._query_order_intent_exchange = lambda record: response
        result = intents.reconcile_order_intent(self.exchange, client_id)
        self.assertEqual("unknown", result["state"])
        self.assertEqual(1, intents.get_order_intent_status(self.exchange)["unresolved_count"])
        response.update(status="FILLED", executedQty="1.0")
        result = intents.reconcile_order_intent(self.exchange, client_id)
        self.assertEqual("accepted", result["state"])
        self.assertEqual(0, intents.get_order_intent_status(self.exchange)["unresolved_count"])
        self.assertTrue(self.engine._ledger_reconciliation_required)

    def test_transport_uncertainty_does_not_retry_or_clear_exposure(self):
        self.exchange.submit_error = TimeoutError("response lost after submission")
        entry = self.append()
        self.assertEqual(0.0, self.close(entry))
        self.assertEqual(1, len(self.exchange.sent))
        self.assertEqual(1.0, self.engine._leg_entries(self.key)[0]["qty"])
        self.assertEqual(1, intents.get_order_intent_status(self.exchange)["unresolved_count"])
        self.assertTrue(self.engine._ledger_reconciliation_required)

    def test_malformed_fill_cannot_release_the_persistent_intent(self):
        self.exchange.executed_qty = "nan"
        self.assertEqual(0.0, self.close(self.append()))
        self.assertEqual(1.0, self.engine._leg_entries(self.key)[0]["qty"])
        self.assertEqual(1, intents.get_order_intent_status(self.exchange)["unresolved_count"])
        self.assertEqual([], self.flips)

    def test_partial_close_updates_margin_for_every_owner(self):
        self.assertAlmostEqual(0.4, self.close(self.append(), 0.4))
        entry = self.engine._leg_entries(self.key)[0]
        self.assertAlmostEqual(6.0, entry["margin_usdt"])
        for indicator in ("rsi", "macd"):
            owner = self.engine._trade_book[("BTCUSDT", "1m", indicator, "BUY")]["target"]
            self.assertAlmostEqual(0.6, owner["qty"])
            self.assertAlmostEqual(entry["margin_usdt"], owner["margin_usdt"])

    def test_missing_identity_blocks_submission_and_preserves_neighbors(self):
        unidentified = self.append(None)
        neighbor = self.append("neighbor", 2.0)
        self.assertEqual(0.0, self.close(unidentified, 0.4))
        self.assertEqual([], self.exchange.sent)
        self.assertIn(neighbor, self.engine._leg_entries(self.key))
        self.assertIn(unidentified, self.engine._leg_entries(self.key))
        self.assertTrue(self.engine._ledger_reconciliation_required)

    def test_duplicate_identity_blocks_submission(self):
        entry = self.append()
        self.append()
        self.assertEqual(0.0, self.close(entry))
        self.assertEqual([], self.exchange.sent)
        self.assertEqual(2, len(self.engine._leg_entries(self.key)))

    def test_stale_entry_quantity_blocks_submission(self):
        entry = self.append()
        stale = dict(entry, qty=2.0)
        self.assertEqual(0.0, self.close(stale))
        self.assertEqual([], self.exchange.sent)
        self.assertEqual(1.0, self.engine._leg_entries(self.key)[0]["qty"])


class OrderExecutionResponseTests(unittest.TestCase):
    def test_status_and_quantity_are_independent_of_submission_amount(self):
        for status, qty, complete in (
            ("NEW", "0", False), ("PARTIALLY_FILLED", "0.25", False),
            ("CANCELED", "0.25", False), ("EXPIRED", "0", False), ("FILLED", "1", True),
        ):
            with self.subTest(status=status):
                result = order_execution_from_response({"status": status, "executedQty": qty}, "1")
                self.assertEqual(float(qty), result.executed_qty)
                self.assertEqual(complete, result.complete)

    def test_malformed_or_contradictory_execution_is_rejected(self):
        for response in (
            {}, {"status": "FILLED"}, {"status": []},
            {"status": "UNKNOWN", "executedQty": "1"},
            *({"status": "FILLED", "executedQty": value}
              for value in (True, None, "", "nan", "inf", "-1", "2", "0", "0.25", "1e9999", "1e-9999")),
            {"status": "NEW", "executedQty": "0.25"},
            {"status": "FILLED", "executedQty": "1", "origQty": "2"},
        ):
            with self.subTest(response=response), self.assertRaises(ValueError):
                order_execution_from_response(response, "1")

    def test_close_consumers_never_infer_fills_from_sent_or_original_quantity(self):
        for response in ({"ok": True}, {"ok": True, "sent_qty": 1}, {"origQty": "1"},
                         {"execution_confirmed": False, "executed_qty": 1}):
            with self.subTest(response=response):
                self.assertEqual(0.0, confirmed_close_quantity(response, 1))
        for qty in (True, None, "nan", "-1", "2"):
            with self.subTest(qty=qty), self.assertRaises(ValueError):
                confirmed_close_quantity({"execution_confirmed": True, "executed_qty": qty}, 1)


if __name__ == "__main__":
    unittest.main()
