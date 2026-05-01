from __future__ import annotations

import sys
import unittest
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from app.config import build_default_config  # noqa: E402
from app.core.strategy import StrategyEngine  # noqa: E402


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

    def tearDown(self) -> None:
        StrategyEngine._BAR_GLOBAL_SIGNATURES.clear()
        StrategyEngine._SYMBOL_ORDER_STATE.clear()

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


if __name__ == "__main__":
    unittest.main()
