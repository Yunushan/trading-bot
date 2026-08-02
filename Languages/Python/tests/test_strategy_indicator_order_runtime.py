from __future__ import annotations

import sys
import unittest
from pathlib import Path
from unittest.mock import patch


PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from app.config import build_default_config  # noqa: E402
from app.core.strategy import StrategyEngine  # noqa: E402
from app.core.strategy.orders.strategy_indicator_order_context_runtime import (  # noqa: E402
    _prepare_indicator_signal_request_context,
)
from app.core.strategy.orders.strategy_indicator_order_directional_runtime import (  # noqa: E402
    _build_directional_indicator_order_request,
)
from app.core.strategy.orders.strategy_indicator_order_fallback_runtime import (  # noqa: E402
    _build_fallback_indicator_order_request,
)
from app.core.strategy.orders.strategy_indicator_order_hedge_runtime import (  # noqa: E402
    _build_hedge_indicator_order_request,
)
from app.core.strategy.orders import strategy_signal_order_collect_runtime  # noqa: E402


class _IndicatorOrderBinance:
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
    return StrategyEngine(_IndicatorOrderBinance(), config, log_callback=logs.append)


def _context_kwargs(*, action: str = "buy") -> dict[str, object]:
    return {
        "cw": {"symbol": "BTCUSDT", "interval": "1m"},
        "indicator_label": "RSI@5m",
        "indicator_action": action,
        "account_type": "FUTURES",
        "dual_side": False,
        "qty_tol_indicator": 1e-9,
        "now_ts": 100.0,
        "now_indicator_ts": 100.0,
    }


class StrategyIndicatorOrderRuntimeTests(unittest.TestCase):
    def setUp(self) -> None:
        StrategyEngine._GLOBAL_PAUSE.clear()

    def tearDown(self) -> None:
        StrategyEngine._GLOBAL_PAUSE.clear()

    def _patch_ready_context(self, engine: StrategyEngine) -> None:
        engine._indicator_live_qty_total = lambda *_args, **_kwargs: 0.0
        engine._recent_indicator_close = lambda *_args, **_kwargs: None
        engine._indicator_signal_confirmation_ready = lambda *_args, **_kwargs: True
        engine._indicator_cooldown_remaining = lambda *_args, **_kwargs: 0.0
        engine._reentry_block_remaining = lambda *_args, **_kwargs: 0.0
        engine._indicator_reentry_requires_reset = False

    def test_context_builds_normalized_request_context_with_label_interval_alias(self):
        engine = _build_engine([])
        self._patch_ready_context(engine)

        result = _prepare_indicator_signal_request_context(engine, **_context_kwargs())

        self.assertIsNotNone(result)
        assert result is not None
        self.assertEqual("rsi@5m", result["indicator_key"])
        self.assertEqual("BUY", result["action_side_label"])
        self.assertEqual("SELL", result["opp_side_label"])
        self.assertEqual({"1m", "5m"}, result["indicator_interval_tokens"])
        self.assertEqual("rsi@5m_buy_signal", result["reason_signal"])

    def test_context_suppresses_signal_during_cooldown_without_flip_evidence(self):
        logs: list[str] = []
        engine = _build_engine(logs)
        self._patch_ready_context(engine)
        engine._indicator_cooldown_remaining = lambda *_args, **_kwargs: 30.0

        result = _prepare_indicator_signal_request_context(engine, **_context_kwargs())

        self.assertIsNone(result)
        self.assertTrue(any("cooldown" in message for message in logs))

    def test_context_clears_stale_futures_guard_only_when_exchange_is_flat(self):
        engine = _build_engine([])
        engine._recent_indicator_close = lambda *_args, **_kwargs: None
        engine._indicator_live_qty_total = lambda _s, _i, _k, side, **_kwargs: 1.0 if side == "BUY" else 0.0
        engine._current_futures_position_qty = lambda *_args, **_kwargs: 0.0
        engine._indicator_signal_confirmation_ready = lambda *_args, **_kwargs: True
        engine._indicator_cooldown_remaining = lambda *_args, **_kwargs: 0.0
        engine._reentry_block_remaining = lambda *_args, **_kwargs: 0.0
        purged: list[tuple[object, ...]] = []
        engine._purge_indicator_tracking = lambda *args, **_kwargs: purged.append(args)
        engine._indicator_reentry_requires_reset = False

        result = _prepare_indicator_signal_request_context(engine, **_context_kwargs())

        self.assertIsNotNone(result)
        self.assertEqual([("BTCUSDT", "1m", "rsi@5m", "BUY")], purged)

    def _patch_flat_indicator_state(self, engine: StrategyEngine) -> None:
        engine._indicator_open_qty = lambda *_args, **_kwargs: 0.0
        engine._indicator_trade_book_qty = lambda *_args, **_kwargs: 0.0
        engine._current_futures_position_qty = lambda *_args, **_kwargs: 0.0
        engine._symbol_side_has_other_positions = lambda *_args, **_kwargs: False
        engine._reentry_block_remaining = lambda *_args, **_kwargs: 0.0

    def test_directional_builder_returns_order_when_both_indicator_legs_are_flat(self):
        engine = _build_engine([])
        self._patch_flat_indicator_state(engine)

        result = _build_directional_indicator_order_request(
            engine,
            cw={"symbol": "BTCUSDT", "interval": "1m"},
            interval_current="1m",
            indicator_key="rsi",
            indicator_label="RSI",
            target_side="BUY",
            desired_ps_target=None,
            desired_ps_opposite=None,
            indicator_interval_tokens={"1m"},
            qty_tol_indicator=1e-9,
            reason_signal="rsi_buy_signal",
            recent_close=None,
            now_indicator_ts=100.0,
        )

        self.assertEqual(
            {
                "side": "BUY",
                "labels": ["RSI"],
                "signature": ("rsi",),
                "indicator_key": "rsi",
                "flip_from": None,
                "flip_qty": 0.0,
                "flip_qty_target": 0.0,
            },
            result,
        )

    def test_directional_builder_records_flip_after_opposite_indicator_close(self):
        engine = _build_engine([])
        engine._indicator_open_qty = lambda _s, _i, _k, side, **_kwargs: 2.5 if side == "SELL" else 0.0
        engine._indicator_trade_book_qty = lambda *_args, **_kwargs: 0.0
        engine._close_indicator_positions = lambda *_args, **_kwargs: (1, 2.5)

        result = _build_directional_indicator_order_request(
            engine,
            cw={"symbol": "BTCUSDT", "interval": "1m"},
            interval_current="1m",
            indicator_key="rsi",
            indicator_label="RSI",
            target_side="BUY",
            desired_ps_target=None,
            desired_ps_opposite=None,
            indicator_interval_tokens={"1m"},
            qty_tol_indicator=1e-9,
            reason_signal="rsi_buy_signal",
            recent_close=None,
            now_indicator_ts=100.0,
        )

        self.assertIsNotNone(result)
        assert result is not None
        self.assertEqual("SELL", result["flip_from"])
        self.assertEqual(2.5, result["flip_qty"])
        self.assertEqual(2.5, result["flip_qty_target"])

    def test_directional_builder_fails_closed_when_opposite_leg_survives_failed_close(self):
        engine = _build_engine([])
        engine._indicator_open_qty = lambda _s, _i, _k, side, **_kwargs: 1.0 if side == "SELL" else 0.0
        engine._indicator_trade_book_qty = lambda *_args, **_kwargs: 0.0
        engine._close_indicator_positions = lambda *_args, **_kwargs: (0, 0.0)
        engine._indicator_has_open = lambda *_args, **_kwargs: True
        engine._close_opposite_position = lambda *_args, **_kwargs: False

        result = _build_directional_indicator_order_request(
            engine,
            cw={"symbol": "BTCUSDT", "interval": "1m"},
            interval_current="1m",
            indicator_key="rsi",
            indicator_label="RSI",
            target_side="BUY",
            desired_ps_target=None,
            desired_ps_opposite=None,
            indicator_interval_tokens={"1m"},
            qty_tol_indicator=1e-9,
            reason_signal="rsi_buy_signal",
            recent_close=None,
            now_indicator_ts=100.0,
        )

        self.assertIsNone(result)

    def test_fallback_builder_returns_order_when_exchange_is_flat(self):
        engine = _build_engine([])
        engine._indicator_live_qty_total = lambda *_args, **_kwargs: 0.0
        engine._symbol_side_has_other_positions = lambda *_args, **_kwargs: False
        engine._current_futures_position_qty = lambda *_args, **_kwargs: 0.0
        engine._reentry_block_remaining = lambda *_args, **_kwargs: 0.0

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

        self.assertEqual(
            {
                "side": "BUY",
                "labels": ["RSI"],
                "signature": ("rsi",),
                "indicator_key": "rsi",
            },
            result,
        )

    def test_fallback_builder_blocks_exchange_overlap_when_hedge_is_disabled(self):
        engine = _build_engine([])
        engine._indicator_live_qty_total = lambda *_args, **_kwargs: 0.0
        engine._symbol_side_has_other_positions = lambda *_args, **_kwargs: False
        engine._current_futures_position_qty = lambda *_args, **_kwargs: 1.0

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

    def test_hedge_builder_closes_opposite_indicator_and_returns_flip(self):
        engine = _build_engine([])
        state = {"opposite_qty": 2.0}
        engine._indicator_open_qty = (
            lambda _s, _i, _k, side, **_kwargs: state["opposite_qty"] if side == "SELL" else 0.0
        )
        engine._indicator_trade_book_qty = lambda *_args, **_kwargs: 0.0
        engine._symbol_side_has_other_positions = lambda *_args, **_kwargs: False

        def close_indicator(*_args, **_kwargs):
            state["opposite_qty"] = 0.0
            return 1, 2.0

        engine._close_indicator_positions = close_indicator
        engine._current_futures_position_qty = lambda *_args, **_kwargs: 0.0

        handled, result = _build_hedge_indicator_order_request(
            engine,
            cw={"symbol": "BTCUSDT", "interval": "1m"},
            interval_current="1m",
            indicator_key="rsi",
            indicator_label="RSI",
            target_side="BUY",
            desired_ps_opposite=None,
            indicator_interval_tokens={"1m"},
            qty_tol_indicator=1e-9,
            reason_signal="rsi_buy_signal",
        )

        self.assertTrue(handled)
        self.assertIsNotNone(result)
        assert result is not None
        self.assertEqual("BUY", result["side"])
        self.assertEqual("SELL", result["flip_from"])
        self.assertEqual(2.0, result["flip_qty"])

    def test_hedge_builder_defers_when_close_does_not_remove_opposite_leg(self):
        engine = _build_engine([])
        engine._indicator_open_qty = lambda *_args, **_kwargs: 1.0
        engine._indicator_trade_book_qty = lambda *_args, **_kwargs: 0.0
        engine._symbol_side_has_other_positions = lambda *_args, **_kwargs: False
        engine._close_indicator_positions = lambda *_args, **_kwargs: (0, 0.0)
        engine._close_opposite_position = lambda *_args, **_kwargs: False

        handled, result = _build_hedge_indicator_order_request(
            engine,
            cw={"symbol": "BTCUSDT", "interval": "1m"},
            interval_current="1m",
            indicator_key="rsi",
            indicator_label="RSI",
            target_side="BUY",
            desired_ps_opposite=None,
            indicator_interval_tokens={"1m"},
            qty_tol_indicator=1e-9,
            reason_signal="rsi_buy_signal",
        )

        self.assertTrue(handled)
        self.assertIsNone(result)

    def test_collector_dispatches_normal_indicator_order(self):
        engine = _build_engine([])
        self._patch_ready_context(engine)
        self._patch_flat_indicator_state(engine)

        requests, tolerance = engine._collect_indicator_order_requests(
            cw={"symbol": "BTCUSDT", "interval": "1m"},
            trigger_actions={"RSI": "buy"},
            dual_side=False,
            account_type="FUTURES",
            allow_opposite_enabled=False,
            hedge_overlap_allowed=False,
            now_ts=100.0,
        )

        self.assertEqual(1e-9, tolerance)
        self.assertEqual(["BUY"], [request["side"] for request in requests])
        self.assertEqual(("rsi",), requests[0]["signature"])

    def test_collector_uses_fallback_when_normal_builder_returns_no_request(self):
        engine = _build_engine([])
        self._patch_ready_context(engine)
        self._patch_flat_indicator_state(engine)

        with patch.object(
            strategy_signal_order_collect_runtime,
            "_build_directional_indicator_order_request",
            return_value=None,
        ):
            requests, _tolerance = engine._collect_indicator_order_requests(
                cw={"symbol": "BTCUSDT", "interval": "1m"},
                trigger_actions={"RSI": "buy"},
                dual_side=False,
                account_type="FUTURES",
                allow_opposite_enabled=False,
                hedge_overlap_allowed=False,
                now_ts=100.0,
            )

        self.assertEqual(["BUY"], [request["side"] for request in requests])
        self.assertEqual(("rsi",), requests[0]["signature"])

    def test_collector_rejects_nonfinite_quantity_tolerance(self):
        engine = _build_engine([])

        requests, tolerance = engine._collect_indicator_order_requests(
            cw={"symbol": "BTCUSDT", "interval": "1m", "indicator_qty_tolerance": "nan"},
            trigger_actions={"RSI": "buy"},
            dual_side=False,
            account_type="FUTURES",
            allow_opposite_enabled=False,
            hedge_overlap_allowed=False,
            now_ts=100.0,
        )

        self.assertEqual([], requests)
        self.assertEqual(1e-9, tolerance)
        self.assertTrue(engine._ledger_reconciliation_required or StrategyEngine._GLOBAL_PAUSE.is_set())


if __name__ == "__main__":
    unittest.main()
