"""Close/reversal contracts with real strategy code and an offline exchange boundary."""
from __future__ import annotations

import copy
import socket
import time
import unittest
from unittest.mock import patch

from app.core.strategy import StrategyEngine
from app.core.strategy.positions.strategy_close_opposite_common_runtime import _finalize_close_cleanup
from app.core.strategy.positions.strategy_close_opposite_indicator_runtime import _indicator_scope_is_already_flat
from tests.test_fake_exchange_integration import _FakeExchangeWrapper, _build_engine, _signal_order_kwargs
from trading_core.orders import order_execution_from_response


class ScriptedCloseExchange(_FakeExchangeWrapper):
    def __init__(self, *, dual=False):
        super().__init__()
        self.dual = dual
        self.reads = 0
        self.read_faults = {}
        self.close_attempts = []
        self.closes = []
        self.close_status = "FILLED"
        self.executed_qty = None
        self.close_error = None
        self.keep_exposure = False

    def get_futures_dual_side(self):
        if isinstance(self.dual, Exception):
            raise self.dual
        return self.dual

    def list_open_futures_positions(self, **kwargs):
        self.reads += 1
        result = self.read_faults.get(self.reads, self.positions)
        if isinstance(result, Exception):
            raise result
        return copy.deepcopy(result)

    def close_futures_leg_exact(self, symbol, quantity, *, side, position_side):
        attempt = {"symbol": symbol, "qty": quantity, "side": side, "position_side": position_side}
        self.close_attempts.append(attempt)
        if not self.dual and position_side is not None:
            return {"ok": False, "error": "position side does not match", "submission_attempted": False}
        self.closes.append(attempt)
        if self.close_error:
            raise self.close_error
        executed = self.executed_qty
        if executed is None:
            executed = quantity if self.close_status == "FILLED" else 0.0
        if not self.keep_exposure:
            for pos in self.positions:
                if pos["symbol"] != symbol or (self.dual and pos["positionSide"] != position_side):
                    continue
                amount = float(pos["positionAmt"])
                if (side == "BUY" and amount < 0) or (side == "SELL" and amount > 0):
                    remaining = max(0.0, abs(amount) - float(executed))
                    pos["positionAmt"] = str(remaining if amount > 0 else -remaining)
        response = {
            "ok": True, "status": self.close_status, "symbol": symbol, "side": side,
            "orderId": len(self.closes), "origQty": str(quantity),
            "executedQty": str(executed), "avgPrice": "100",
        }
        execution = order_execution_from_response(response, quantity)
        return {"ok": execution.complete, "info": response, "requested_qty": quantity,
                "sent_qty": quantity, "submission_attempted": True,
                "execution_confirmed": True, "executed_qty": execution.executed_qty,
                "reconciliation_required": not execution.complete}

    def expose(self, side, qty=1.0, *, symbol="BTCUSDT"):
        self.positions.append({
            "symbol": symbol, "positionAmt": str(qty if side == "BUY" else -qty),
            "positionSide": ("LONG" if side == "BUY" else "SHORT") if self.dual else "BOTH",
        })


class CloseReversalContractTests(unittest.TestCase):
    def setUp(self):
        for target in ((socket.socket, "connect"), (socket, "create_connection")):
            blocker = patch.object(*target, side_effect=AssertionError("Network forbidden"))
            blocker.start()
            self.addCleanup(blocker.stop)
        spacing = patch.object(StrategyEngine, "_ORDER_MIN_SPACING", 0.0)
        spacing.start()
        self.addCleanup(spacing.stop)
        self.reset_globals()
        self.addCleanup(self.reset_globals)

    @staticmethod
    def reset_globals():
        StrategyEngine._GLOBAL_PAUSE.clear()
        StrategyEngine._GLOBAL_PAUSE_FALLBACK = False
        StrategyEngine._GLOBAL_SHUTDOWN.clear()
        StrategyEngine._GLOBAL_SHUTDOWN_FALLBACK = False
        StrategyEngine._ORDER_LAST_TS = 0.0
        StrategyEngine._BAR_GLOBAL_SIGNATURES.clear()
        StrategyEngine._SYMBOL_ORDER_STATE.clear()
        StrategyEngine._CONNECTOR_ORDER_BLOCK_EVENTS.clear()
        StrategyEngine._CONNECTOR_ORDER_CIRCUIT_OPEN = False

    def engine(self, *, dual=False, allow_opposite=False, live=True):
        self.reset_globals()
        self.exchange = ScriptedCloseExchange(dual=dual)
        self.exchange.mode = "Live" if live else "Demo/Testnet"
        self.logs, self.trades = [], []
        engine = _build_engine(wrapper=self.exchange, logs=self.logs, trades=self.trades)
        engine.config.update(allow_opposite_positions=allow_opposite, allow_close_ignoring_hold=True,
                             mode=self.exchange.mode)
        engine.operational_snapshot_callback = self.fresh_operational_snapshot
        return engine

    @staticmethod
    def fresh_operational_snapshot():
        now = time.time()
        return {"health": "ok", "generated_at": now, "freshness": {
            key: {"stale": False, "generated_at": now, "age_seconds": 0.0, "max_age_seconds": 120.0}
            for key in ("exchange_connector", "account", "portfolio")
        }}

    def append(self, engine, *, side="SELL", qty=1.0, indicator="rsi", interval="1m", symbol="BTCUSDT"):
        key = (symbol, interval, side)
        entry = {
            "ledger_id": f"{symbol}-{interval}-{indicator}-{side}", "qty": qty,
            "entry_price": 100.0, "margin_usdt": qty * 20.0,
            "timestamp": time.time() - 600, "trigger_signature": (indicator,),
        }
        engine._append_leg_entry(key, entry)
        return key, entry

    @staticmethod
    def close(engine, *, desired="BUY", scoped=True, target=None, indicators=("rsi",)):
        return engine._close_opposite_position(
            "BTCUSDT", "1m", desired,
            trigger_signature=indicators if scoped else None,
            indicator_key=indicators if scoped else None,
            target_qty=target,
        )

    def assert_blocked(self, engine):
        self.assertTrue(engine.stopped(), self.logs)
        self.assertEqual([], self.exchange.orders)

    def test_unknown_snapshots_block_both_directions_before_any_submission(self):
        invalid = [None, {}, [None], [{"symbol": "BTCUSDT"}],
                   [{"symbol": "BTCUSDT", "positionAmt": False}],
                   [{"symbol": "BTCUSDT", "positionAmt": ""}],
                   [{"symbol": "BTCUSDT", "positionAmt": "NaN"}],
                   [{"symbol": "BTCUSDT", "positionAmt": "Infinity"}],
                   [{"positionAmt": "0"}],
                   [{"symbol": "BTCUSDT", "positionAmt": "0", "positionSide": "invalid"}],
                   [{"symbol": "BTCUSDT", "positionAmt": "-1", "positionSide": "LONG"}],
                   TimeoutError("offline snapshot timeout")]
        for desired in ("BUY", "SELL"):
            for dual in (False, True):
                for read in (1, 2):
                    for snapshot in invalid:
                        with self.subTest(desired=desired, dual=dual, read=read, snapshot=snapshot):
                            engine = self.engine(dual=dual)
                            self.exchange.read_faults[read] = snapshot
                            self.assertIs(False, self.close(engine, desired=desired))
                            self.assert_blocked(engine)
                            self.assertEqual([], self.exchange.close_attempts)

    def test_known_opposite_then_unknown_refresh_does_not_authorize_reversal(self):
        for desired in ("BUY", "SELL"):
            for dual in (False, True):
                with self.subTest(desired=desired, dual=dual):
                    engine = self.engine(dual=dual)
                    self.exchange.expose("SELL" if desired == "BUY" else "BUY")
                    self.exchange.read_faults[2] = TimeoutError("offline refresh timeout")
                    self.assertIs(False, self.close(engine, desired=desired))
                    self.assert_blocked(engine)
                    self.assertEqual([], self.exchange.close_attempts)

    def test_verified_flat_controls_succeed_without_submitting(self):
        for desired in ("BUY", "SELL"):
            for dual, scoped in ((False, False), (False, True), (True, True)):
                with self.subTest(desired=desired, dual=dual, scoped=scoped):
                    engine = self.engine(dual=dual)
                    self.assertIs(True, self.close(engine, desired=desired, scoped=scoped))
                    self.assertFalse(engine.stopped(), self.logs)
                    self.assertEqual([], self.exchange.close_attempts)

    def test_unknown_position_mode_blocks(self):
        for mode in (None, "false", 0, RuntimeError("mode unavailable")):
            with self.subTest(mode=mode):
                engine = self.engine(dual=mode)
                self.assertIs(False, self.close(engine))
                self.assert_blocked(engine)
                self.assertEqual([], self.exchange.close_attempts)

    def test_paused_engine_does_not_begin_a_reversal(self):
        engine = self.engine()
        StrategyEngine._GLOBAL_PAUSE.set()
        self.assertIs(False, self.close(engine))
        self.assertEqual(0, self.exchange.reads)
        self.assertEqual([], self.exchange.close_attempts)

    def test_invalid_target_cannot_become_an_executable_close_quantity(self):
        for target in (True, False, "bad", -1.0, float("nan"), float("inf")):
            with self.subTest(target=target):
                engine = self.engine()
                self.append(engine)
                self.exchange.expose("SELL")
                self.assertIs(False, self.close(engine, target=target))
                self.assert_blocked(engine)
                self.assertEqual([], self.exchange.close_attempts)

    def test_quantity_failure_aborts_before_indicator_close(self):
        for method in ("_indicator_open_qty", "_indicator_trade_book_qty"):
            for quantity in (None, False, -1, float("nan"), float("inf")):
                with self.subTest(method=method, quantity=quantity):
                    engine = self.engine()
                    with patch.object(engine, method, return_value=quantity), \
                         patch.object(engine, "_close_indicator_positions", wraps=engine._close_indicator_positions) as close:
                        self.assertIs(False, self.close(engine))
                        close.assert_not_called()
                    self.assert_blocked(engine)

    def test_all_indicator_tokens_are_considered_before_declaring_flat(self):
        engine = self.engine()
        self.append(engine, indicator="macd")
        state = {"symbol": "BTCUSDT", "interval_norm": "1m", "interval_tokens": {"1m"},
                 "indicator_tokens": ("rsi", "macd"), "opp": "SELL", "qty_goal": None, "qty_tol": 1e-9}
        self.assertIs(False, _indicator_scope_is_already_flat(engine, state))
        self.assertEqual(0, self.exchange.reads)
        self.assertFalse(engine.stopped(), self.logs)

    def test_confirmed_indicator_close_removes_only_owned_leg(self):
        for desired in ("BUY", "SELL"):
            for dual in (False, True):
                with self.subTest(desired=desired, dual=dual):
                    engine = self.engine(dual=dual, allow_opposite=True)
                    opposite = "SELL" if desired == "BUY" else "BUY"
                    key, entry = self.append(engine, side=opposite)
                    other_key, other = self.append(engine, side=opposite, interval="5m", indicator="macd")
                    self.exchange.expose(opposite, 2.0)
                    self.assertIs(True, self.close(engine, desired=desired, target=1.0))
                    self.assertFalse(engine.stopped(), self.logs)
                    self.assertNotIn(key, engine._leg_ledger)
                    self.assertEqual([other], engine._leg_entries(other_key))
                    self.assertEqual(1, len(self.exchange.closes))
                    self.assertEqual(1.0, self.exchange.closes[0]["qty"])
                    self.assertEqual(desired, self.exchange.closes[0]["side"])
                    self.assertNotIn(entry["ledger_id"], engine._ledger_index)

    def test_full_unscoped_symbol_close_requires_confirmed_flat_cleanup(self):
        for desired in ("BUY", "SELL"):
            with self.subTest(desired=desired):
                engine = self.engine()
                self.exchange.expose("SELL" if desired == "BUY" else "BUY")
                self.exchange.expose("SELL", symbol="ETHUSDT")
                self.assertIs(True, self.close(engine, desired=desired, scoped=False))
                self.assertFalse(engine.stopped(), self.logs)
                self.assertEqual(1, len(self.exchange.closes))
                self.assertEqual(desired, self.exchange.closes[0]["side"])
                self.assertEqual("-1.0", self.exchange.positions[1]["positionAmt"])
                self.assertGreaterEqual(self.exchange.reads, 3)

    def test_unconfirmed_indicator_close_never_allows_reopening(self):
        for status, executed in (("NEW", 0.0), ("PARTIALLY_FILLED", 0.25)):
            with self.subTest(status=status):
                engine = self.engine(allow_opposite=True)
                key, _ = self.append(engine)
                self.exchange.expose("SELL")
                self.exchange.close_status, self.exchange.executed_qty = status, executed
                self.assertIs(False, self.close(engine))
                self.assert_blocked(engine)
                self.assertTrue(engine._ledger_reconciliation_required)
                self.assertAlmostEqual(1.0 - executed, engine._leg_entries(key)[0]["qty"])
                self.assertEqual(1, len(self.exchange.closes))

    def test_confirmed_unscoped_ledger_close_and_quantity_limited_close(self):
        for desired in ("BUY", "SELL"):
            for limit in (None, 0.4):
                with self.subTest(desired=desired, limit=limit):
                    engine = self.engine()
                    opposite = "SELL" if desired == "BUY" else "BUY"
                    key, _ = self.append(engine, side=opposite)
                    neighbor_key, neighbor = self.append(engine, symbol="ETHUSDT")
                    self.exchange.expose(opposite)
                    self.assertIs(True, self.close(engine, desired=desired, scoped=False, target=limit))
                    self.assertFalse(engine.stopped(), self.logs)
                    self.assertEqual(1, len(self.exchange.closes))
                    self.assertAlmostEqual(limit or 1.0, self.exchange.closes[0]["qty"])
                    if limit is None:
                        self.assertNotIn(key, engine._leg_ledger)
                    else:
                        self.assertAlmostEqual(1.0 - limit, engine._leg_entries(key)[0]["qty"])
                    self.assertEqual([neighbor], engine._leg_entries(neighbor_key))

    def test_unscoped_ledger_refresh_failure_blocks_after_confirmed_execution(self):
        engine = self.engine()
        self.append(engine)
        self.exchange.expose("SELL")
        self.exchange.read_faults[3] = TimeoutError("read after fill failed")
        self.assertIs(False, self.close(engine, scoped=False))
        self.assert_blocked(engine)
        self.assertEqual(1, len(self.exchange.closes))

    def test_close_transport_uncertainty_cannot_be_retried_or_reopened(self):
        for scoped in (True, False):
            with self.subTest(scoped=scoped):
                engine = self.engine()
                key, entry = self.append(engine)
                self.exchange.expose("SELL")
                self.exchange.close_error = TimeoutError("reply lost after submission")
                self.assertIs(False, self.close(engine, scoped=scoped))
                self.assertIs(False, self.close(engine, scoped=scoped))
                self.assertEqual(1, len(self.exchange.closes))
                self.assertEqual([entry], engine._leg_entries(key))
                self.assert_blocked(engine)
                self.assertTrue(engine._ledger_reconciliation_required)

    def test_malformed_indicator_close_result_blocks_and_retains_ownership(self):
        outcomes = [(True, 1.0), (-1, 1.0), (1, 0.0), (0, 1.0), (0, None),
                    (1, float("nan")), RuntimeError("local close bookkeeping failed")]
        for outcome in outcomes:
            with self.subTest(outcome=outcome):
                engine = self.engine()
                key, entry = self.append(engine)
                self.exchange.expose("SELL")
                kwargs = {"side_effect": outcome} if isinstance(outcome, Exception) else {"return_value": outcome}
                with patch.object(engine, "_close_indicator_positions", **kwargs):
                    self.assertIs(False, self.close(engine))
                self.assertEqual([entry], engine._leg_entries(key))
                self.assert_blocked(engine)
                self.assertTrue(engine._ledger_reconciliation_required)
                self.assertEqual([], self.exchange.close_attempts)

    def test_unknown_indicator_residual_state_blocks_caller(self):
        for state in (None, "false", TimeoutError("ownership unavailable")):
            with self.subTest(state=state):
                engine = self.engine()
                self.append(engine)
                self.exchange.expose("SELL")
                kwargs = {"side_effect": state} if isinstance(state, Exception) else {"return_value": state}
                with patch.object(engine, "_close_indicator_positions", return_value=(0, 0.0)), \
                     patch.object(engine, "_indicator_has_open", **kwargs):
                    self.assertIs(False, self.close(engine))
                self.assert_blocked(engine)

    def test_cleanup_still_open_blocks_without_deleting_ledger(self):
        engine = self.engine()
        key, entry = self.append(engine)
        self.exchange.expose("SELL")
        with patch("app.core.strategy.positions.strategy_close_opposite_common_runtime.time.sleep"):
            self.assertIs(False, _finalize_close_cleanup(engine, "BTCUSDT", "SELL", 1e-9, True))
        self.assertEqual(6, self.exchange.reads)
        self.assertEqual([entry], engine._leg_entries(key))
        self.assert_blocked(engine)

    def test_cleanup_propagates_internal_guard_reconciliation_failure(self):
        engine = self.engine()
        self.append(engine)
        with patch.object(engine, "_mark_guard_closed", side_effect=RuntimeError("guard write failed")):
            self.assertIs(False, _finalize_close_cleanup(engine, "BTCUSDT", "SELL", 1e-9, True))
        self.assert_blocked(engine)
        self.assertTrue(engine._ledger_reconciliation_required)

    def test_symbol_close_metadata_failure_blocks_reopen_after_one_submission(self):
        for desired in ("BUY", "SELL"):
            with self.subTest(desired=desired):
                engine = self.engine()
                self.exchange.expose("SELL" if desired == "BUY" else "BUY")
                with patch.object(engine, "_build_close_event_payload", side_effect=RuntimeError("metadata failed")):
                    self.assertIs(False, self.close(engine, desired=desired, scoped=False))
                self.assert_blocked(engine)
                self.assertEqual(1, len(self.exchange.closes))
                self.assertTrue(engine._ledger_reconciliation_required)

    def test_ledger_close_guard_lookup_failure_prevents_submission(self):
        for desired in ("BUY", "SELL"):
            with self.subTest(desired=desired):
                engine = self.engine()
                opposite = "SELL" if desired == "BUY" else "BUY"
                key, entry = self.append(engine, side=opposite)
                self.exchange.expose(opposite)
                engine._close_leg_guard = None
                self.assertIs(False, self.close(engine, desired=desired, scoped=False))
                self.assert_blocked(engine)
                self.assertTrue(engine._ledger_reconciliation_required)
                self.assertEqual([entry], engine._leg_entries(key))
                self.assertEqual([], self.exchange.close_attempts)

    def test_ledger_close_guard_update_failure_blocks_after_confirmed_fill(self):
        class UnwritableGuard(set):
            def add(self, item):
                raise RuntimeError("close guard update failed")

        for desired in ("BUY", "SELL"):
            with self.subTest(desired=desired):
                engine = self.engine()
                opposite = "SELL" if desired == "BUY" else "BUY"
                self.append(engine, side=opposite)
                other_key, other_entry = self.append(engine, symbol="ETHUSDT")
                self.exchange.expose(opposite)
                engine._close_leg_guard = UnwritableGuard()
                self.assertIs(False, self.close(engine, desired=desired, scoped=False))
                self.assertIs(False, self.close(engine, desired=desired, scoped=False))
                self.assert_blocked(engine)
                self.assertTrue(engine._ledger_reconciliation_required)
                self.assertEqual([other_entry], engine._leg_entries(other_key))
                self.assertEqual(1, len(self.exchange.closes))
                self.assertEqual(0.0, float(self.exchange.positions[0]["positionAmt"]))

    def test_unconfirmed_symbol_close_blocks_without_a_ledger(self):
        for desired in ("BUY", "SELL"):
            for status, executed in (("NEW", 0.0), ("PARTIALLY_FILLED", 0.25)):
                with self.subTest(desired=desired, status=status):
                    engine = self.engine()
                    self.exchange.expose("SELL" if desired == "BUY" else "BUY")
                    self.exchange.close_status, self.exchange.executed_qty = status, executed
                    self.assertIs(False, self.close(engine, desired=desired, scoped=False))
                    self.assertIs(False, self.close(engine, desired=desired, scoped=False))
                    self.assert_blocked(engine)
                    self.assertTrue(engine._ledger_reconciliation_required)
                    self.assertEqual(1, len(self.exchange.closes))
                    self.assertAlmostEqual(1.0 - executed, abs(float(self.exchange.positions[0]["positionAmt"])))

    def test_quantity_limited_symbol_close_does_not_authorize_reversal_with_residual_exposure(self):
        for desired in ("BUY", "SELL"):
            with self.subTest(desired=desired):
                engine = self.engine()
                self.exchange.expose("SELL" if desired == "BUY" else "BUY")
                with patch("app.core.strategy.positions.strategy_close_opposite_common_runtime.time.sleep"):
                    self.assertIs(False, self.close(engine, desired=desired, scoped=False, target=0.4))
                self.assert_blocked(engine)
                self.assertTrue(engine._ledger_reconciliation_required)
                self.assertEqual(1, len(self.exchange.closes))
                self.assertAlmostEqual(0.4, self.exchange.closes[0]["qty"])
                self.assertAlmostEqual(0.6, abs(float(self.exchange.positions[0]["positionAmt"])))

    def test_invalid_next_side_never_closes_existing_exposure(self):
        for desired in ("", "HOLD", "LONG", "SHORT"):
            with self.subTest(desired=desired):
                engine = self.engine()
                key, entry = self.append(engine)
                self.exchange.expose("SELL")
                self.assertIs(False, self.close(engine, desired=desired))
                self.assertEqual([entry], engine._leg_entries(key))
                self.assertEqual([], self.exchange.close_attempts)
                self.assertEqual([], self.exchange.orders)

    def test_direct_indicator_close_rejects_unknown_ownership_and_quantity_limit(self):
        for method in ("_indicator_open_qty", "_indicator_trade_book_qty", "_current_futures_position_qty"):
            for invalid in (None, False, float("nan"), -1.0):
                with self.subTest(method=method, invalid=invalid):
                    engine = self.engine(allow_opposite=True)
                    self.append(engine)
                    with patch.object(engine, method, return_value=invalid):
                        result = engine._close_indicator_positions(
                            {"symbol": "BTCUSDT"}, "1m", "rsi", "SELL", None,
                            signature_hint=("rsi",), allow_hedge_close=True,
                        )
                    self.assertEqual((0, 0.0), result)
                    self.assertEqual([], self.exchange.close_attempts)
                    self.assert_blocked(engine)
        engine = self.engine(allow_opposite=True)
        result = engine._close_indicator_positions(
            {"symbol": "BTCUSDT"}, "1m", "rsi", "SELL", None,
            signature_hint=("rsi",), allow_hedge_close=True, qty_limit=float("nan"),
        )
        self.assertEqual((0, 0.0), result)
        self.assert_blocked(engine)

    def test_cleanup_retains_ledger_on_missing_or_reappearing_final_exposure(self):
        for fault in (None, TimeoutError("last read failed"),
                      [{"symbol": "BTCUSDT", "positionAmt": "-1"}]):
            with self.subTest(fault=fault):
                engine = self.engine()
                key, entry = self.append(engine)
                self.exchange.read_faults[2] = fault
                self.assertIs(False, _finalize_close_cleanup(engine, "BTCUSDT", "SELL", 1e-9, True))
                self.assertEqual([entry], engine._leg_entries(key))
                self.assert_blocked(engine)
                self.assertTrue(engine._ledger_reconciliation_required)

    def test_cleanup_removes_only_opposite_side_when_other_hedge_side_remains(self):
        engine = self.engine(dual=True)
        closed_key, _ = self.append(engine)
        live_key, live_entry = self.append(engine, side="BUY", indicator="macd")
        neighbor_key, neighbor = self.append(engine, symbol="ETHUSDT")
        self.exchange.expose("BUY")
        self.assertIs(True, _finalize_close_cleanup(engine, "BTCUSDT", "SELL", 1e-9, True))
        self.assertNotIn(closed_key, engine._leg_ledger)
        self.assertEqual([live_entry], engine._leg_entries(live_key))
        self.assertEqual([neighbor], engine._leg_entries(neighbor_key))
        self.assertFalse(engine.stopped(), self.logs)

    def test_unscoped_cleanup_failure_propagates_to_close_caller(self):
        engine = self.engine()
        self.exchange.read_faults[2] = None
        self.assertIs(False, self.close(engine, scoped=False))
        self.assert_blocked(engine)
        self.assertTrue(engine._ledger_reconciliation_required)

    def test_full_signal_order_cannot_submit_after_uncertain_close_gate(self):
        for desired in ("BUY", "SELL"):
            with self.subTest(desired=desired):
                engine = self.engine()
                original_close = engine._close_opposite_position

                def fail_refresh(*args, **kwargs):
                    self.exchange.read_faults[self.exchange.reads + 2] = None
                    return original_close(*args, **kwargs)

                with patch.object(engine, "_close_opposite_position", side_effect=fail_refresh) as gate:
                    engine._execute_signal_order(**_signal_order_kwargs(engine, side=desired, price=100.0, marker=123))
                    gate.assert_called_once()
                self.assert_blocked(engine)
                self.assertEqual([], self.exchange.close_attempts)
                self.assertEqual([], self.trades)

    def test_full_signal_order_flat_positive_control_reaches_submission(self):
        for desired in ("BUY", "SELL"):
            with self.subTest(desired=desired):
                engine = self.engine()
                with patch.object(engine, "_close_opposite_position", wraps=engine._close_opposite_position) as gate:
                    engine._execute_signal_order(**_signal_order_kwargs(engine, side=desired, price=100.0, marker=124))
                    gate.assert_called_once()
                self.assertEqual(1, len(self.exchange.orders), self.logs)
                self.assertEqual(desired, self.exchange.orders[0]["side"])
                self.assertFalse(engine.stopped(), self.logs)

    def test_full_signal_reversal_closes_before_opening_and_preserves_ordering(self):
        for desired in ("BUY", "SELL"):
            for retain_exposure in (False, True):
                with self.subTest(desired=desired, retain_exposure=retain_exposure):
                    engine = self.engine()
                    opposite = "SELL" if desired == "BUY" else "BUY"
                    self.append(engine, side=opposite)
                    self.exchange.expose(opposite)
                    self.exchange.keep_exposure = retain_exposure
                    engine._execute_signal_order(**_signal_order_kwargs(engine, side=desired, price=100.0, marker=125))
                    self.assertEqual(1, len(self.exchange.closes), self.logs)
                    self.assertEqual(0 if retain_exposure else 1, len(self.exchange.orders), self.logs)
                    if not retain_exposure:
                        closed_event = next(i for i, event in enumerate(self.trades) if event.get("status") == "closed")
                        opened_event = next(i for i, event in enumerate(self.trades) if event.get("status") == "placed")
                        self.assertLess(closed_event, opened_event)


if __name__ == "__main__":
    unittest.main()
