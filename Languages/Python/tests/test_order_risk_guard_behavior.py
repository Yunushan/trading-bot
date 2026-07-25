from __future__ import annotations

import sys
import unittest
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from app.config import build_default_config  # noqa: E402
from app.core.strategy import StrategyEngine  # noqa: E402
from app.core.strategy.orders.strategy_indicator_order_common_runtime import (  # noqa: E402
    _indicator_exchange_qty,
)
from app.core.strategy.orders.strategy_indicator_order_fallback_runtime import (  # noqa: E402
    _build_fallback_indicator_order_request,
)


class _RiskGuardBinance:
    account_type = "FUTURES"

    def get_total_usdt_value(self) -> float:
        return 1000.0

    def get_futures_balance_snapshot(self, force_refresh=False):  # noqa: ARG002
        return {"total": "1000", "wallet": "1000", "available": "1000"}

    def get_futures_dual_side(self) -> bool:
        return False


def _build_engine(logs: list[str]) -> StrategyEngine:
    config = build_default_config()
    config.update(
        {
            "symbol": "BTCUSDT",
            "interval": "1m",
            "account_type": "FUTURES",
            "side": "BOTH",
            "allow_opposite_positions": False,
        }
    )
    engine = StrategyEngine(_RiskGuardBinance(), config, log_callback=logs.append)
    setattr(engine, "_indicator_has_open", lambda *_args, **_kwargs: False)
    setattr(engine, "_symbol_signature_active", lambda *_args, **_kwargs: False)
    return engine


def _signal_guard_kwargs(*, marker: int | None = None) -> dict[str, object]:
    signature = ("rsi", "slot0")
    return {
        "cw": {"symbol": "BTCUSDT", "interval": "1m"},
        "side": "BUY",
        "interval_norm": "1m",
        "interval_key": "1m",
        "trigger_labels": ["rsi", "slot0"],
        "signature": signature,
        "sig_sorted": signature,
        "signature_guard_key": signature,
        "signature_label": "rsi|slot0",
        "indicator_key_hint": "rsi",
        "indicator_tokens_for_order": ["rsi"],
        "current_bar_marker": marker,
        "bar_sig_key": ("BTCUSDT", "1m", "BUY"),
        "flip_active": False,
    }


class OrderRiskGuardBehaviorTests(unittest.TestCase):
    def setUp(self) -> None:
        StrategyEngine._BAR_GLOBAL_SIGNATURES.clear()
        StrategyEngine._SYMBOL_ORDER_STATE.clear()
        StrategyEngine._GLOBAL_PAUSE.clear()
        StrategyEngine._GLOBAL_PAUSE_FALLBACK = False

    def tearDown(self) -> None:
        StrategyEngine._BAR_GLOBAL_SIGNATURES.clear()
        StrategyEngine._SYMBOL_ORDER_STATE.clear()
        StrategyEngine._GLOBAL_PAUSE.clear()
        StrategyEngine._GLOBAL_PAUSE_FALLBACK = False

    def test_symbol_guard_blocks_duplicate_pending_signal_order(self):
        logs: list[str] = []
        engine = _build_engine(logs)

        first = engine._prepare_signal_order_guard(**_signal_guard_kwargs())
        duplicate = engine._prepare_signal_order_guard(**_signal_guard_kwargs())

        self.assertFalse(first["aborted"])
        self.assertTrue(first["guard_claimed"])
        state = StrategyEngine._SYMBOL_ORDER_STATE[("BTCUSDT", "1m", "BUY")]
        self.assertIn(("rsi", "slot0"), state["pending_map"])
        self.assertTrue(duplicate["aborted"])
        self.assertFalse(duplicate["guard_claimed"])
        self.assertTrue(any("previous order still pending" in item for item in logs))

    def test_symbol_guard_resets_stale_state_only_when_no_live_qty_remains(self):
        logs: list[str] = []
        engine = _build_engine(logs)
        StrategyEngine._SYMBOL_ORDER_STATE[("BTCUSDT", "1m", "BUY")] = {
            "last": 1.0,
            "window": 8.0,
            "pending_map": {("rsi", "slot0"): 1.0},
            "signatures": {("rsi", "slot0"): 1.0},
        }

        engine._reset_stale_signal_order_guard(
            symbol="BTCUSDT",
            interval_key="1m",
            side="BUY",
            guard_window=8.0,
        )

        state = StrategyEngine._SYMBOL_ORDER_STATE[("BTCUSDT", "1m", "BUY")]
        self.assertEqual({}, state["pending_map"])
        self.assertEqual({}, state["signatures"])
        self.assertEqual(0.0, state["last"])
        self.assertTrue(any("symbol guard reset" in item for item in logs))

    def test_same_bar_signature_is_suppressed_before_second_order_claim(self):
        logs: list[str] = []
        engine = _build_engine(logs)

        first = engine._prepare_signal_order_guard(**_signal_guard_kwargs(marker=123))
        duplicate = engine._prepare_signal_order_guard(**_signal_guard_kwargs(marker=123))

        self.assertFalse(first["aborted"])
        self.assertTrue(duplicate["aborted"])
        self.assertFalse(duplicate["guard_claimed"])
        self.assertTrue(any("global duplicate" in item for item in logs))

    def test_stale_guard_is_retained_when_live_ledger_quantity_is_invalid(self):
        logs: list[str] = []
        engine = _build_engine(logs)
        engine._leg_ledger[("BTCUSDT", "1m", "BUY")] = {"qty": "nan"}
        signature = ("rsi", "slot0")
        StrategyEngine._SYMBOL_ORDER_STATE[("BTCUSDT", "1m", "BUY")] = {
            "last": 1.0,
            "pending_map": {signature: 1.0},
            "signatures": {signature: 1.0},
        }

        engine._reset_stale_signal_order_guard(
            symbol="BTCUSDT",
            interval_key="1m",
            side="BUY",
            guard_window=8.0,
        )

        state = StrategyEngine._SYMBOL_ORDER_STATE[("BTCUSDT", "1m", "BUY")]
        self.assertEqual({signature: 1.0}, state["pending_map"])
        self.assertEqual({signature: 1.0}, state["signatures"])
        self.assertTrue(any("stale-state safety could not be proven" in item for item in logs))

    def test_invalid_pending_timestamp_blocks_duplicate_fail_closed(self):
        logs: list[str] = []
        engine = _build_engine(logs)
        signature = ("rsi", "slot0")
        StrategyEngine._SYMBOL_ORDER_STATE[("BTCUSDT", "1m", "BUY")] = {
            "last": "nan",
            "pending_map": {signature: "nan"},
            "signatures": {},
        }

        result = engine._prepare_signal_order_guard(**_signal_guard_kwargs())

        self.assertTrue(result["aborted"])
        self.assertFalse(result["guard_claimed"])
        self.assertTrue(any("retained fail-closed" in item for item in logs))
        self.assertTrue(any("previous order still pending" in item for item in logs))

    def test_log_callback_failure_does_not_allow_duplicate_order(self):
        engine = _build_engine([])

        def fail_log(_message):
            raise RuntimeError("log callback failed")

        engine.log = fail_log
        first = engine._prepare_signal_order_guard(**_signal_guard_kwargs())
        with self.assertLogs(
            "app.core.strategy.orders.strategy_signal_order_guard_runtime",
            level="ERROR",
        ):
            duplicate = engine._prepare_signal_order_guard(**_signal_guard_kwargs())

        self.assertFalse(first["aborted"])
        self.assertTrue(duplicate["aborted"])
        self.assertFalse(duplicate["guard_claimed"])

    def test_position_gate_aborts_when_opposite_indicator_exposure_remains(self):
        logs: list[str] = []
        engine = _build_engine(logs)
        abort_calls: list[bool] = []

        setattr(engine, "_close_opposite_position", lambda *_args, **_kwargs: True)
        setattr(engine, "_indicator_live_qty_total", lambda *_args, **_kwargs: 0.25)
        setattr(engine, "_symbol_side_has_other_positions", lambda *_args, **_kwargs: False)
        setattr(engine, "_current_futures_position_qty", lambda *_args, **_kwargs: 0.0)

        result = engine._prepare_signal_order_position_gate(
            cw={"symbol": "BTCUSDT", "interval": "1m"},
            side="BUY",
            interval_norm="1m",
            signature=("rsi",),
            indicator_key_hint="rsi",
            indicator_tokens_for_order=["rsi"],
            indicator_tokens_for_guard=["rsi"],
            flip_close_qty=0.0,
            qty_tol_slot_guard=1e-9,
            abort_guard=lambda: abort_calls.append(True),
        )

        self.assertTrue(result["aborted"])
        self.assertEqual([True], abort_calls)
        self.assertTrue(any("opposite SELL still open" in item for item in logs))

    def test_position_snapshot_with_non_finite_amount_is_treated_as_active(self):
        engine = _build_engine([])

        active = engine._is_futures_position_active_for_order(
            "BTCUSDT",
            "BUY",
            False,
            [{"symbol": "BTCUSDT", "positionAmt": "nan"}],
        )

        self.assertTrue(active)

    def test_candidate_filter_blocks_duplicate_order_when_live_position_amount_is_non_finite(self):
        logs: list[str] = []
        engine = _build_engine(logs)
        leg_key = ("BTCUSDT", "1m", "BUY")
        engine._leg_ledger[leg_key] = {
            "qty": 1.0,
            "timestamp": 0.0,
            "entries": [{"qty": 1.0, "trigger_signature": ["rsi"]}],
        }

        filtered, _cache, aborted = engine._filter_signal_order_candidates(
            cw={"symbol": "BTCUSDT", "interval": "1m"},
            orders_to_execute=[
                {
                    "side": "BUY",
                    "labels": ["rsi"],
                    "signature": ("rsi",),
                    "indicator_key": "rsi",
                }
            ],
            dual_side=False,
            positions_cache=[{"symbol": "BTCUSDT", "positionAmt": "nan"}],
        )

        self.assertFalse(aborted)
        self.assertEqual([], filtered)
        self.assertTrue(any("position still active" in item for item in logs))

    def test_unknown_exchange_quantity_raises_and_pauses(self):
        engine = _build_engine([])
        engine._current_futures_position_qty = lambda *_args, **_kwargs: None

        with self.assertRaisesRegex(RuntimeError, "quantity is unavailable"):
            _indicator_exchange_qty(engine, "BTCUSDT", "BUY", None)

        self.assertTrue(StrategyEngine._GLOBAL_PAUSE.is_set())

    def test_position_gate_aborts_when_ownership_lookup_fails(self):
        engine = _build_engine([])
        abort_calls: list[bool] = []
        engine._close_opposite_position = lambda *_args, **_kwargs: True
        engine._indicator_live_qty_total = lambda *_args, **_kwargs: 0.0

        def fail_ownership(*_args, **_kwargs):
            raise RuntimeError("ownership unavailable")

        engine._symbol_side_has_other_positions = fail_ownership

        result = engine._prepare_signal_order_position_gate(
            cw={"symbol": "BTCUSDT", "interval": "1m"},
            side="BUY",
            interval_norm="1m",
            signature=("rsi",),
            indicator_key_hint="rsi",
            indicator_tokens_for_order=["rsi"],
            indicator_tokens_for_guard=["rsi"],
            flip_close_qty=0.0,
            qty_tol_slot_guard=1e-9,
            abort_guard=lambda: abort_calls.append(True),
        )

        self.assertTrue(result["aborted"])
        self.assertEqual([True], abort_calls)
        self.assertTrue(engine._ledger_reconciliation_required)
        self.assertTrue(StrategyEngine._GLOBAL_PAUSE.is_set())

    def test_candidate_filter_aborts_for_invalid_timestamp_after_stop(self):
        engine = _build_engine([])
        engine._stop_time = 100.0

        filtered, _cache, aborted = engine._filter_signal_order_candidates(
            cw={"symbol": "BTCUSDT", "interval": "1m"},
            orders_to_execute=[
                {
                    "side": "BUY",
                    "labels": ["rsi"],
                    "signature": ("rsi",),
                    "timestamp": "invalid",
                }
            ],
            dual_side=False,
        )

        self.assertTrue(aborted)
        self.assertEqual([], filtered)
        self.assertTrue(StrategyEngine._GLOBAL_PAUSE.is_set())

    def test_slot_cleanup_failure_aborts_flip_order(self):
        engine = _build_engine([])
        leg_key = ("BTCUSDT", "1m", "BUY")
        engine._leg_ledger[leg_key] = {
            "qty": 1.0,
            "entries": [
                {
                    "qty": 1.0,
                    "margin_usdt": 10.0,
                    "indicator_keys": ["rsi"],
                    "trigger_signature": ["rsi"],
                }
            ],
        }
        engine._indicator_open_qty = lambda *_args, **_kwargs: 0.0
        engine._indicator_trade_book_qty = lambda *_args, **_kwargs: 0.0
        engine._current_futures_position_qty = lambda *_args, **_kwargs: 0.0

        def fail_purge(*_args, **_kwargs):
            raise RuntimeError("tracking storage unavailable")

        engine._purge_indicator_tracking = fail_purge
        abort_calls: list[bool] = []

        result = engine._prepare_signal_order_slot_state(
            cw={"symbol": "BTCUSDT", "interval": "1m"},
            side="BUY",
            lev=5,
            signature=("rsi",),
            trigger_labels=["rsi"],
            context_key="1m:BUY:rsi",
            indicator_key_hint="rsi",
            indicator_tokens_for_order=["rsi"],
            flip_active=True,
            abort_guard=lambda: abort_calls.append(True),
        )

        self.assertTrue(result["aborted"])
        self.assertEqual([True], abort_calls)
        self.assertTrue(engine._ledger_reconciliation_required)
        self.assertTrue(StrategyEngine._GLOBAL_PAUSE.is_set())

    def test_fallback_indicator_order_blocks_on_ownership_failure(self):
        engine = _build_engine([])

        def fail_ownership(*_args, **_kwargs):
            raise RuntimeError("ownership unavailable")

        engine._indicator_live_qty_total = fail_ownership

        result = _build_fallback_indicator_order_request(
            engine,
            cw={"symbol": "BTCUSDT", "interval": "1m"},
            interval_current="1m",
            indicator_key="rsi",
            indicator_label="RSI",
            target_side="BUY",
            desired_ps_opposite=None,
            indicator_interval_tokens={"1m"},
            qty_tol_indicator=1e-9,
            hedge_overlap_allowed=False,
            now_indicator_ts=100.0,
        )

        self.assertIsNone(result)
        self.assertTrue(engine._ledger_reconciliation_required)
        self.assertTrue(StrategyEngine._GLOBAL_PAUSE.is_set())

    def test_execute_signal_order_rejects_nonfinite_flip_quantity(self):
        engine = _build_engine([])

        engine._execute_signal_order(
            cw={"symbol": "BTCUSDT", "interval": "1m"},
            order_side="BUY",
            indicator_labels=["rsi"],
            order_signature=("rsi",),
            origin_timestamp=100.0,
            flip_from_side="SELL",
            flip_qty=float("nan"),
        )

        self.assertTrue(engine._ledger_reconciliation_required)
        self.assertTrue(StrategyEngine._GLOBAL_PAUSE.is_set())


if __name__ == "__main__":
    unittest.main()
