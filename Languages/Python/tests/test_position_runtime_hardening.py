from __future__ import annotations

import sys
import unittest
from pathlib import Path


PYTHON_ROOT = Path(__file__).resolve().parents[1]
if str(PYTHON_ROOT) not in sys.path:
    sys.path.insert(0, str(PYTHON_ROOT))

from app.config import build_default_config  # noqa: E402
from app.core.strategy import StrategyEngine  # noqa: E402
from app.core.strategy.positions.strategy_close_opposite_exchange_runtime import (  # noqa: E402
    _close_symbol_level_positions,
)
from app.core.strategy.positions.strategy_close_opposite_ledger_runtime import (  # noqa: E402
    _close_interval_side_entries,
)


class _FakeBinance:
    account_type = "FUTURES"
    mode = "Live"

    def get_futures_dual_side(self):
        return False

    def list_open_futures_positions(self, **_kwargs):
        return []


def _build_engine(*, logs: list[str] | None = None) -> StrategyEngine:
    config = build_default_config()
    config["symbol"] = "BTCUSDT"
    config["interval"] = "1m"
    config["account_type"] = "FUTURES"
    sink = logs if logs is not None else []
    return StrategyEngine(_FakeBinance(), config, log_callback=sink.append)


class PositionRuntimeHardeningTests(unittest.TestCase):
    def setUp(self):
        StrategyEngine._GLOBAL_PAUSE.clear()
        StrategyEngine._GLOBAL_PAUSE_FALLBACK = False

    def tearDown(self):
        StrategyEngine._GLOBAL_PAUSE.clear()
        StrategyEngine._GLOBAL_PAUSE_FALLBACK = False

    def test_malformed_exchange_position_row_returns_unknown_quantity(self):
        engine = _build_engine()

        quantity = engine._current_futures_position_qty(
            "BTCUSDT",
            "BUY",
            None,
            [{"symbol": "BTCUSDT", "positionAmt": "not-a-number"}],
        )

        self.assertIsNone(quantity)

    def test_flat_leg_purge_retains_ledger_when_exchange_quantity_is_unknown(self):
        engine = _build_engine()
        leg_key = ("BTCUSDT", "1m", "BUY")
        engine._leg_ledger[leg_key] = {
            "qty": 1.0,
            "timestamp": 1.0,
            "entries": [{"qty": 1.0, "timestamp": 1.0}],
        }

        engine._purge_flat_futures_legs(
            "BTCUSDT",
            [{"symbol": "BTCUSDT", "positionAmt": "invalid"}],
            dual_side=False,
        )

        self.assertIn(leg_key, engine._leg_ledger)
        self.assertTrue(StrategyEngine._GLOBAL_PAUSE.is_set())

    def test_invalid_hold_timestamp_blocks_close_and_pauses(self):
        engine = _build_engine()
        engine._indicator_min_hold_seconds = 30.0

        ready = engine._indicator_hold_ready(
            "invalid",
            "BTCUSDT",
            "1m",
            "rsi",
            "BUY",
            60.0,
        )

        self.assertFalse(ready)
        self.assertTrue(engine._ledger_reconciliation_required)
        self.assertTrue(StrategyEngine._GLOBAL_PAUSE.is_set())

    def test_guard_close_failure_pauses_for_reconciliation(self):
        engine = _build_engine()

        class _FailingGuard:
            def mark_closed(self, *_args, **_kwargs):
                raise RuntimeError("guard storage unavailable")

        engine.guard = _FailingGuard()

        engine._mark_guard_closed("BTCUSDT", "1m", "BUY")

        self.assertTrue(engine._ledger_reconciliation_required)
        self.assertTrue(StrategyEngine._GLOBAL_PAUSE.is_set())

    def test_flip_request_is_dropped_when_ownership_lookup_fails(self):
        engine = _build_engine()
        engine.config["require_indicator_flip_signal"] = False
        engine._drain_flip_on_close_requests = lambda _interval: [
            {"indicator_key": "rsi", "side": "BUY", "qty": 1.0}
        ]

        def fail_ownership(*_args, **_kwargs):
            raise RuntimeError("ownership unavailable")

        engine._indicator_live_qty_total = fail_ownership
        requests: list[dict[str, object]] = []

        result = engine._merge_flip_requests_into_indicator_orders(
            cw={"symbol": "BTCUSDT", "interval": "1m"},
            indicator_order_requests=requests,
            qty_tol_indicator=1e-9,
        )

        self.assertEqual([], result)
        self.assertTrue(StrategyEngine._GLOBAL_PAUSE.is_set())

    def test_conflict_resolution_rejects_unknown_position_mode(self):
        engine = _build_engine()
        engine.config["allow_indicator_close_without_signal"] = True

        def fail_position_mode():
            raise RuntimeError("position mode unavailable")

        engine.binance.get_futures_dual_side = fail_position_mode

        with self.assertRaisesRegex(RuntimeError, "could not verify position mode"):
            engine._resolve_indicator_conflicts(
                ("BTCUSDT", "1m", "BUY"),
                ["rsi"],
                {"qty": 1.0},
            )

    def test_confirmed_symbol_close_with_failed_cleanup_pauses(self):
        engine = _build_engine()
        engine._execute_close_with_fallback = lambda *_args, **_kwargs: (True, {"ok": True})
        engine._build_close_event_payload = lambda *_args, **_kwargs: {}
        engine._notify_interval_closed = lambda *_args, **_kwargs: None

        def fail_guard_cleanup(*_args, **_kwargs):
            raise RuntimeError("guard cleanup unavailable")

        engine._mark_guard_closed = fail_guard_cleanup
        state: dict[str, object] = {
            "symbol": "BTCUSDT",
            "interval": "1m",
            "desired": "BUY",
            "dual": False,
            "qty_goal": None,
            "qty_tol": 1e-9,
            "closed_any": False,
            "positions": [{"symbol": "BTCUSDT", "positionAmt": "-1"}],
        }

        result = _close_symbol_level_positions(engine, state)

        self.assertFalse(result)
        self.assertTrue(engine._ledger_reconciliation_required)
        self.assertTrue(StrategyEngine._GLOBAL_PAUSE.is_set())

    def test_invalid_ledger_close_limit_fails_closed(self):
        engine = _build_engine()

        result = _close_interval_side_entries(
            engine,
            symbol="BTCUSDT",
            interval_norm="1m",
            interval_tokens={"1m"},
            interval_has_filter=True,
            interval_norm_guard=None,
            opp="BUY",
            dual=False,
            indicator_filter=None,
            signature_filter=None,
            qty_limit=float("nan"),
        )

        self.assertEqual((0, True, 0.0), result)
        self.assertTrue(StrategyEngine._GLOBAL_PAUSE.is_set())


if __name__ == "__main__":
    unittest.main()
