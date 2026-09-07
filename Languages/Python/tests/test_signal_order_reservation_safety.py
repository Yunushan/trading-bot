from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from threading import Barrier
import unittest
from unittest.mock import Mock, patch

from app.core.strategy import StrategyEngine
from app.core.strategy.orders import strategy_signal_order_guard_runtime as guards
from app.core.strategy.orders import strategy_signal_order_result_runtime as results
from test_order_risk_guard_behavior import _build_engine, _signal_guard_kwargs
from test_fake_exchange_integration import _FakeExchangeWrapper, _build_engine as execution_engine, _signal_order_kwargs


class SignalOrderReservationSafetyTests(unittest.TestCase):
    def setUp(self):
        StrategyEngine._BAR_GLOBAL_SIGNATURES.clear()
        StrategyEngine._SYMBOL_ORDER_STATE.clear()
        StrategyEngine._GLOBAL_PAUSE.clear()
        StrategyEngine._GLOBAL_SHUTDOWN.clear()
        StrategyEngine._GLOBAL_PAUSE_FALLBACK = False
        self.network = patch("socket.socket.connect", side_effect=AssertionError("Network forbidden"))
        self.network.start()

    def tearDown(self):
        self.network.stop()
        StrategyEngine._BAR_GLOBAL_SIGNATURES.clear()
        StrategyEngine._SYMBOL_ORDER_STATE.clear()
        StrategyEngine._GLOBAL_PAUSE.clear()
        StrategyEngine._GLOBAL_SHUTDOWN.clear()
        StrategyEngine._GLOBAL_PAUSE_FALLBACK = False

    def abort(self, engine, state):
        engine._abort_signal_order_guard(
            state["guard_key_symbol"], ("rsi", "slot0"),
            reservation_token=state["reservation_token"], bar_reservation=state["bar_reservation"],
        )

    def submit(self, engine, state):
        guards._mark_signal_order_submission(
            engine, state["guard_key_symbol"], ("rsi", "slot0"),
            state["reservation_token"], state["bar_reservation"],
        )

    def test_abort_releases_only_its_own_reservation(self):
        engine = _build_engine([])
        kwargs = _signal_guard_kwargs(marker=123)
        first = engine._prepare_signal_order_guard(**kwargs)
        self.abort(engine, first)
        second = engine._prepare_signal_order_guard(**kwargs)
        self.assertFalse(second["aborted"])
        self.abort(engine, first)
        self.assertTrue(engine._prepare_signal_order_guard(**kwargs)["aborted"])
        with self.assertRaisesRegex(RuntimeError, "ownership was lost"):
            self.submit(engine, first)
        self.submit(engine, second)
        self.abort(engine, second)
        self.assertTrue(engine._prepare_signal_order_guard(**kwargs)["aborted"])

    def test_rejected_symbol_claim_does_not_poison_bar(self):
        engine = _build_engine([])
        first = engine._prepare_signal_order_guard(**_signal_guard_kwargs())
        self.assertTrue(engine._prepare_signal_order_guard(**_signal_guard_kwargs(marker=123))["aborted"])
        self.abort(engine, first)
        self.assertFalse(engine._prepare_signal_order_guard(**_signal_guard_kwargs(marker=123))["aborted"])

    def test_concurrent_engines_reserve_once_even_during_flip(self):
        for flip in (False, True):
            with self.subTest(flip=flip):
                StrategyEngine._BAR_GLOBAL_SIGNATURES.clear()
                StrategyEngine._SYMBOL_ORDER_STATE.clear()
                engines = [_build_engine([]), _build_engine([])]
                barrier = Barrier(2)
                for engine in engines:
                    engine._symbol_signature_active = lambda *args: (barrier.wait(timeout=5), False)[1]
                kwargs = dict(_signal_guard_kwargs(marker=123), flip_active=flip)
                with ThreadPoolExecutor(max_workers=2) as pool:
                    states = list(pool.map(lambda engine: engine._prepare_signal_order_guard(**kwargs), engines))
                self.assertEqual(1, sum(not state["aborted"] for state in states))

    def test_failed_flip_cannot_erase_previous_submission(self):
        engine = _build_engine([])
        kwargs = _signal_guard_kwargs(marker=123)
        first = engine._prepare_signal_order_guard(**kwargs)
        self.submit(engine, first)
        self.abort(engine, first)
        flip = engine._prepare_signal_order_guard(**dict(kwargs, flip_active=True))
        self.assertFalse(flip["aborted"])
        self.abort(engine, flip)
        self.assertTrue(engine._prepare_signal_order_guard(**kwargs)["aborted"])

    def test_old_claim_and_late_result_cannot_replace_current_bar(self):
        engine = _build_engine([])
        with patch.object(guards.time, "time", return_value=1000):
            first = engine._prepare_signal_order_guard(**_signal_guard_kwargs(marker=123))
        with patch.object(guards.time, "time", return_value=2000):
            second = engine._prepare_signal_order_guard(**_signal_guard_kwargs(marker=124))
        self.assertFalse(second["aborted"])
        with self.assertRaises(RuntimeError):
            self.submit(engine, first)
        self.abort(engine, first)
        results._record_order_bar_signature(
            engine, current_bar_marker=123, bar_sig_key=("BTCUSDT", "1m", "BUY"), sig_sorted=("rsi", "slot0"),
        )
        self.assertEqual(124, StrategyEngine._BAR_GLOBAL_SIGNATURES[("BTCUSDT", "1m", "BUY")]["bar"])
        self.submit(engine, second)

    def test_ambiguous_submission_retains_duplicate_protection(self):
        wrapper = _FakeExchangeWrapper()
        wrapper.place_futures_market_order = Mock(side_effect=TimeoutError("response lost"))
        engine = execution_engine(wrapper=wrapper, logs=[], trades=[])
        kwargs = _signal_order_kwargs(engine, side="BUY", price=100, marker=123)
        with patch.object(StrategyEngine, "_ORDER_MIN_SPACING", 0):
            engine._execute_signal_order(**kwargs)
            engine._execute_signal_order(**kwargs)
        wrapper.place_futures_market_order.assert_called_once()

    def test_post_submit_logging_exception_does_not_reopen_bar(self):
        wrapper = _FakeExchangeWrapper()
        wrapper.place_futures_market_order = Mock(wraps=wrapper.place_futures_market_order)
        engine = execution_engine(wrapper=wrapper, logs=[], trades=[])
        kwargs = _signal_order_kwargs(engine, side="BUY", price=100, marker=124)
        with patch.object(engine, "_emit_signal_order_info", side_effect=RuntimeError("log failed")), \
             patch.object(StrategyEngine, "_ORDER_MIN_SPACING", 0):
            engine._execute_signal_order(**kwargs)
        engine._leg_ledger.clear()
        engine._symbol_signature_active = lambda *args: False
        engine._indicator_live_qty_total = lambda *args, **kw: 0
        engine._indicator_trade_book_qty = lambda *args, **kw: 0
        engine._execute_signal_order(**kwargs)
        wrapper.place_futures_market_order.assert_called_once()

    def test_uncertain_rate_limit_result_does_not_trigger_strategy_resubmission(self):
        wrapper = _FakeExchangeWrapper()
        wrapper.place_futures_market_order = Mock(return_value={
            "ok": False, "reconciliation_required": True,
            "error": "rate limit while querying an already submitted order",
        })
        engine = execution_engine(wrapper=wrapper, logs=[], trades=[])
        with patch.object(StrategyEngine, "_ORDER_MIN_SPACING", 0):
            engine._execute_signal_order(**_signal_order_kwargs(engine, side="BUY", price=100, marker=125))
        wrapper.place_futures_market_order.assert_called_once()
        self.assertTrue(StrategyEngine._GLOBAL_PAUSE.is_set())
        self.assertFalse(engine._leg_ledger)


if __name__ == "__main__":
    unittest.main()
