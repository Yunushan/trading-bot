from __future__ import annotations

import sys
import unittest
from pathlib import Path
from unittest import mock


PYTHON_ROOT = Path(__file__).resolve().parents[1]
if str(PYTHON_ROOT) not in sys.path:
    sys.path.insert(0, str(PYTHON_ROOT))

from app.config import build_default_config  # noqa: E402
from app.core.strategy import StrategyEngine  # noqa: E402
from app.core.strategy.positions.strategy_close_opposite_common_runtime import (  # noqa: E402
    _finalize_close_cleanup,
)
from app.core.strategy.positions.strategy_close_opposite_indicator_runtime import (  # noqa: E402
    _indicator_scope_is_already_flat,
    _resolve_indicator_residuals,
)


class _FakeBinance:
    account_type = "FUTURES"

    def list_open_futures_positions(self, **_kwargs):
        return []

    def get_futures_dual_side(self):
        return False


def _build_engine(*, logs: list[str] | None = None) -> StrategyEngine:
    config = build_default_config()
    config["symbol"] = "BTCUSDT"
    config["interval"] = "1m"
    config["allow_close_ignoring_hold"] = True
    sink = logs if logs is not None else []
    engine = StrategyEngine(_FakeBinance(), config, log_callback=sink.append)
    engine._symbol_side_has_other_positions = lambda *_args, **_kwargs: False
    engine._mark_guard_closed = lambda *_args, **_kwargs: None
    engine._purge_indicator_tracking = lambda *_args, **_kwargs: None
    return engine


def _state(*, opposite_side: str, qty_goal: float | None = 1.0) -> dict[str, object]:
    return {
        "symbol": "BTCUSDT",
        "interval": "1m",
        "interval_norm": "1m",
        "interval_tokens": {"1m"},
        "indicator_tokens": ("rsi",),
        "signature_hint_tokens": ("rsi",),
        "allow_opposite_requested": False,
        "positions": [],
        "desired": "SELL" if opposite_side == "BUY" else "BUY",
        "opp": opposite_side,
        "dual": True,
        "qty_goal": qty_goal,
        "qty_tol": 1e-9,
        "closed_any": False,
        "indicator_target_cleared": False,
    }


class CloseOppositeHardeningTests(unittest.TestCase):
    def setUp(self):
        StrategyEngine._GLOBAL_PAUSE.clear()
        StrategyEngine._GLOBAL_PAUSE_FALLBACK = False

    def tearDown(self):
        StrategyEngine._GLOBAL_PAUSE.clear()
        StrategyEngine._GLOBAL_PAUSE_FALLBACK = False

    def test_residual_close_uses_order_side_opposite_to_position_side(self):
        cases = (("BUY", "LONG", "SELL"), ("SELL", "SHORT", "BUY"))

        for opposite_side, position_side, expected_close_side in cases:
            with self.subTest(opposite_side=opposite_side):
                engine = _build_engine()
                engine._indicator_live_qty_total = lambda *_args, **_kwargs: 1.0
                close_calls: list[tuple[object, ...]] = []

                def execute_close(*args):
                    close_calls.append(args)
                    return True, {"ok": True, "executedQty": "1"}

                engine._execute_close_with_fallback = execute_close

                result = _resolve_indicator_residuals(
                    engine,
                    _state(opposite_side=opposite_side),
                    position_side,
                )

                self.assertTrue(result)
                self.assertEqual(1, len(close_calls))
                self.assertEqual(expected_close_side, close_calls[0][1])
                self.assertEqual(position_side, close_calls[0][3])
                self.assertFalse(StrategyEngine._GLOBAL_PAUSE.is_set())

    def test_residual_quantity_failure_blocks_flip_and_pauses(self):
        logs: list[str] = []
        engine = _build_engine(logs=logs)

        def fail_quantity(*_args, **_kwargs):
            raise RuntimeError("quantity unavailable")

        engine._indicator_live_qty_total = fail_quantity
        engine._execute_close_with_fallback = lambda *_args, **_kwargs: self.fail(
            "close must not run with unknown quantity"
        )

        result = _resolve_indicator_residuals(engine, _state(opposite_side="BUY"), "LONG")

        self.assertFalse(result)
        self.assertTrue(StrategyEngine._GLOBAL_PAUSE.is_set())
        self.assertIn("live quantity lookup failed", "\n".join(logs))

    def test_flat_scope_query_failure_is_not_treated_as_flat(self):
        logs: list[str] = []
        engine = _build_engine(logs=logs)

        def fail_open_quantity(*_args, **_kwargs):
            raise RuntimeError("ownership unavailable")

        engine._indicator_open_qty = fail_open_quantity

        flat = _indicator_scope_is_already_flat(engine, _state(opposite_side="BUY", qty_goal=None))

        self.assertFalse(flat)
        self.assertTrue(StrategyEngine._GLOBAL_PAUSE.is_set())
        self.assertIn("open-quantity lookup failed", "\n".join(logs))

    def test_strict_flip_without_signature_blocks_new_order(self):
        logs: list[str] = []
        engine = _build_engine(logs=logs)
        engine.config["allow_opposite_positions"] = False
        engine.config["strict_indicator_flip_enforcement"] = True

        result = engine._close_opposite_position(
            "BTCUSDT",
            "1m",
            "BUY",
            trigger_signature=None,
            indicator_key="rsi",
        )

        self.assertFalse(result)
        self.assertIn("missing opposite signature", "\n".join(logs))

    def test_position_mode_lookup_failure_blocks_and_pauses(self):
        logs: list[str] = []
        engine = _build_engine(logs=logs)

        def fail_position_mode():
            raise RuntimeError("position mode unavailable")

        engine.binance.get_futures_dual_side = fail_position_mode

        result = engine._close_opposite_position("BTCUSDT", "1m", "BUY")

        self.assertFalse(result)
        self.assertTrue(StrategyEngine._GLOBAL_PAUSE.is_set())
        self.assertIn("position mode lookup failed", "\n".join(logs))

    def test_non_finite_target_quantity_blocks_and_pauses(self):
        logs: list[str] = []
        engine = _build_engine(logs=logs)
        engine.config["allow_opposite_positions"] = False

        result = engine._close_opposite_position(
            "BTCUSDT",
            "1m",
            "BUY",
            trigger_signature=("rsi",),
            indicator_key="rsi",
            target_qty=float("nan"),
        )

        self.assertFalse(result)
        self.assertTrue(StrategyEngine._GLOBAL_PAUSE.is_set())
        self.assertIn("target quantity is invalid", "\n".join(logs))

    def test_cleanup_retains_ledger_until_exchange_proves_position_flat(self):
        logs: list[str] = []
        engine = _build_engine(logs=logs)
        key = ("BTCUSDT", "1m", "BUY")
        engine._leg_ledger[key] = {"entries": [{"qty": 1.0}]}
        engine.binance.list_open_futures_positions = lambda **_kwargs: [
            {"symbol": "BTCUSDT", "positionAmt": "1"}
        ]
        removed: list[object] = []
        engine._remove_leg_entry = lambda *args, **_kwargs: removed.append(args)
        engine._guard_mark_leg_closed = lambda *_args, **_kwargs: None

        with mock.patch(
            "app.core.strategy.positions.strategy_close_opposite_common_runtime.time.sleep",
            return_value=None,
        ):
            _finalize_close_cleanup(engine, "BTCUSDT", "BUY", 1e-9, True)

        self.assertEqual([], removed)
        self.assertIn(key, engine._leg_ledger)
        self.assertTrue(StrategyEngine._GLOBAL_PAUSE.is_set())
        self.assertIn("exposure is still open", "\n".join(logs))


if __name__ == "__main__":
    unittest.main()
