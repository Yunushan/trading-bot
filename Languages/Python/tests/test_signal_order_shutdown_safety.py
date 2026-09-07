"""Stopping prohibits new submissions, not accounting for in-flight outcomes."""
from __future__ import annotations

import tempfile
import unittest
from types import SimpleNamespace
from unittest.mock import Mock, patch

from app.core.strategy import StrategyEngine
from app.core.strategy.orders import strategy_signal_order_guard_runtime as guards
from app.core.strategy.orders import strategy_signal_order_submit_runtime as submit_runtime
from app.integrations.exchanges.binance.orders import order_intent_runtime as intents
from app.integrations.exchanges.binance.orders.futures_orders import _market_execution_result
from app.settings.live_safety import LiveTradingSafetyError
from test_confirmed_close_execution import OfflineCloseExchange
from test_fake_exchange_integration import _FakeExchangeWrapper, _build_engine, _signal_order_kwargs


KEY = ("BTCUSDT", "1m", "BUY")


class SignalOrderShutdownSafetyTests(unittest.TestCase):
    def setUp(self):
        self.enterContext(patch("socket.socket.connect", side_effect=AssertionError("Network forbidden")))
        self.enterContext(patch.object(StrategyEngine, "_ORDER_MIN_SPACING", 0))
        self.enterContext(patch(
            "app.integrations.exchanges.binance.orders.order_close_confirmation_runtime.CLOSE_QUERY_INTERVAL_SECONDS", 0,
        ))
        self.reset_global_state()
        self.addCleanup(self.reset_global_state)

    @staticmethod
    def reset_global_state():
        StrategyEngine._BAR_GLOBAL_SIGNATURES.clear()
        StrategyEngine._SYMBOL_ORDER_STATE.clear()
        StrategyEngine._GLOBAL_PAUSE.clear()
        StrategyEngine._GLOBAL_SHUTDOWN.clear()
        StrategyEngine._GLOBAL_PAUSE_FALLBACK = False
        StrategyEngine._GLOBAL_SHUTDOWN_FALLBACK = False

    def engine(self):
        self.reset_global_state()
        wrapper = _FakeExchangeWrapper()
        trades = []
        engine = _build_engine(wrapper=wrapper, logs=[], trades=trades)
        engine._handle_futures_signal_order_result = Mock(wraps=engine._handle_futures_signal_order_result)
        return engine, wrapper, trades

    @staticmethod
    def stop(engine, mode):
        if mode == "local":
            engine.stop()
        elif mode == "pause":
            StrategyEngine.pause_trading()
        else:
            StrategyEngine.request_shutdown()

    @staticmethod
    def execute(engine, marker=501):
        engine._execute_signal_order(**_signal_order_kwargs(engine, side="BUY", price=100.0, marker=marker))

    def test_inflight_execution_is_accounted_for_under_every_stop_mode(self):
        for mode in ("local", "pause", "shutdown"):
            for status, fraction in (("FILLED", 1.0), ("PARTIALLY_FILLED", 0.25), ("NEW", 0.0),
                                     ("EXPIRED", 0.25), ("REJECTED", 0.0)):
                with self.subTest(mode=mode, status=status):
                    engine, wrapper, trades = self.engine()
                    original_submit = wrapper.place_futures_market_order

                    def submit(*args, **kwargs):
                        response = original_submit(*args, **kwargs)
                        qty = response["computed"]["qty"]
                        info = dict(response["info"], status=status, executedQty=str(qty * fraction))
                        self.stop(engine, mode)
                        return {**_market_execution_result(info, str(qty)), "info": info}

                    wrapper.place_futures_market_order = Mock(side_effect=submit)
                    engine.guard = Mock()
                    self.execute(engine)
                    wrapper.place_futures_market_order.assert_called_once()
                    engine._handle_futures_signal_order_result.assert_called_once()
                    self.assertTrue(engine.stopped())
                    qty = wrapper.orders[0]["quantity"] * fraction
                    entries = engine._leg_entries(KEY)
                    self.assertEqual(qty, sum(entry["qty"] for entry in entries))
                    self.assertEqual(3 if status == "REJECTED" else 2, len(trades))
                    self.assertTrue(all(event["executed_qty"] == qty for event in trades))
                    pending = status in {"NEW", "PARTIALLY_FILLED"}
                    self.assertEqual(pending, trades[0]["reconciliation_required"])
                    if pending:
                        self.assertTrue(StrategyEngine._GLOBAL_PAUSE.is_set())
                    self.assertEqual(status == "FILLED", engine.guard.end_open.call_args.args[3])
                    self.execute(engine, marker=502)
                    wrapper.place_futures_market_order.assert_called_once()

    def test_lost_response_during_stop_still_pauses_for_reconciliation(self):
        for mode in ("local", "pause", "shutdown"):
            with self.subTest(mode=mode):
                engine, wrapper, trades = self.engine()

                def submit(*args, **kwargs):
                    self.stop(engine, mode)
                    raise TimeoutError("rate limit querying a submitted order")

                wrapper.place_futures_market_order = Mock(side_effect=submit)
                self.execute(engine)
                engine._handle_futures_signal_order_result.assert_called_once()
                self.assertTrue(StrategyEngine._GLOBAL_PAUSE.is_set())
                self.assertEqual([], engine._leg_entries(KEY))
                self.assertEqual(2, len(trades))
                self.assertTrue(all(event["reconciliation_required"] for event in trades))
                self.execute(engine, marker=502)
                wrapper.place_futures_market_order.assert_called_once()

    def test_stop_before_submission_does_not_send_or_account_for_an_order(self):
        for stage in ("already_stopped", "rate_slot", "reservation"):
            with self.subTest(stage=stage):
                engine, wrapper, trades = self.engine()
                wrapper.place_futures_market_order = Mock(wraps=wrapper.place_futures_market_order)
                if stage == "already_stopped":
                    engine.stop()
                    self.execute(engine)
                elif stage == "rate_slot":
                    with patch.object(StrategyEngine, "_reserve_order_slot", side_effect=lambda *a: engine.stop()):
                        self.execute(engine)
                else:
                    mark = guards._mark_signal_order_submission

                    def stop_after_reservation(*args):
                        mark(*args)
                        engine.stop()

                    with patch.object(guards, "_mark_signal_order_submission", side_effect=stop_after_reservation):
                        self.execute(engine)
                wrapper.place_futures_market_order.assert_not_called()
                engine._handle_futures_signal_order_result.assert_not_called()
                self.assertFalse(trades)

    def test_stop_during_retry_backoff_preserves_the_received_rejection(self):
        engine, wrapper, trades = self.engine()
        rejection = {"ok": False, "error": "rate limit rejected before exchange submission"}
        wrapper.place_futures_market_order = Mock(return_value=rejection)
        with patch.object(StrategyEngine, "_reserve_order_slot"), \
             patch.object(submit_runtime.time, "sleep", side_effect=lambda *a: engine.stop()):
            self.execute(engine)
        wrapper.place_futures_market_order.assert_called_once()
        engine._handle_futures_signal_order_result.assert_called_once()
        self.assertEqual(rejection, engine._handle_futures_signal_order_result.call_args.kwargs["order_res"])
        self.assertFalse(StrategyEngine._GLOBAL_PAUSE.is_set())
        self.assertTrue(all(event["executed_qty"] == 0.0 for event in trades))

    def test_stopped_partial_entry_retains_durable_restart_barrier(self):
        engine, wrapper, trades = self.engine()
        exchange = OfflineCloseExchange(self.enterContext(tempfile.TemporaryDirectory()))
        exchange.status = "PARTIALLY_FILLED"
        exchange.executed_qty = "0.25"
        create_order = exchange.client.futures_create_order

        def stop_after_exchange_accepts(**params):
            response = create_order(**params)
            engine.stop()
            return response

        exchange.client.futures_create_order = stop_after_exchange_accepts
        exchange._query_order_intent_exchange = lambda record: {
            "orderId": 1234, "clientOrderId": record["client_order_id"], "symbol": record["symbol"],
            "side": record["side"], "origQty": record["quantity"], "status": "PARTIALLY_FILLED",
            "executedQty": "0.25",
        }

        def submit(symbol, side, **kwargs):
            qty = str(kwargs["quantity"])
            response, _via = exchange._futures_create_order_with_fallback({
                "symbol": symbol, "side": side, "type": "MARKET", "quantity": qty,
            })
            return {**_market_execution_result(response, qty), "info": response}

        wrapper.place_futures_market_order = Mock(side_effect=submit)
        self.execute(engine)
        self.assertEqual(1, len(exchange.sent))
        self.assertEqual(0.25, engine._leg_entries(KEY)[0]["qty"])
        self.assertTrue(all(event["executed_qty"] == 0.25 for event in trades))
        restarted = SimpleNamespace(api_key=exchange.api_key, mode=exchange.mode,
                                    _order_audit_log_path=exchange._order_audit_log_path)
        self.assertEqual(1, intents.get_order_intent_status(restarted)["unresolved_count"])
        with self.assertRaisesRegex(LiveTradingSafetyError, "Unresolved"):
            intents._begin_order_intent(restarted, dict(exchange.sent[0], newClientOrderId="restart-entry"),
                                       market="futures", source="restart")
        self.assertTrue(StrategyEngine._GLOBAL_PAUSE.is_set())


if __name__ == "__main__":
    unittest.main()
