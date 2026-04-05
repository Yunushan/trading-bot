from __future__ import annotations

import sys
import unittest
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from app.config import build_default_config  # noqa: E402
from app.core.positions import IntervalPositionGuard  # noqa: E402
from app.core.strategy import StrategyEngine  # noqa: E402


class _FakeStrategyBinance:
    account_type = "FUTURES"

    def get_total_usdt_value(self):
        return 1000.0

    def get_futures_balance_snapshot(self, force_refresh=False):  # noqa: ARG002
        return {"total": "1000", "wallet": "1000", "available": "1000"}

    def get_futures_balance_usdt(self):
        return 1000.0

    def get_total_wallet_balance(self):
        return 1000.0

    def get_futures_symbol_filters(self, _symbol):
        return {"minNotional": 0.0, "minQty": 0.0}

    def adjust_qty_to_filters_futures(self, _symbol, qty, _price):
        return float(qty), None

    def get_futures_dual_side(self):
        return False

    def get_net_futures_position_amt(self, _symbol):
        return 0.0


class _AbortGuardBinance(_FakeStrategyBinance):
    def __init__(self) -> None:
        super().__init__()
        self.positions = [
            {"symbol": "BTCUSDT", "positionAmt": "-1", "positionSide": "BOTH"},
        ]
        self.place_calls = 0

    def list_open_futures_positions(self, max_age=0.0, force_refresh=False):  # noqa: ARG002
        return list(self.positions)

    def place_futures_market_order(self, *args, **kwargs):  # noqa: ARG002
        self.place_calls += 1
        return {"ok": True}


def _build_engine(*, wrapper=None, can_open_callback=None):
    config = build_default_config()
    config["symbol"] = "BTCUSDT"
    config["interval"] = "1m"
    config["account_type"] = "FUTURES"
    config["side"] = "BOTH"
    config["leverage"] = 5
    config["position_pct"] = 25
    config["position_pct_units"] = "percent"
    return StrategyEngine(
        wrapper or _FakeStrategyBinance(),
        config,
        log_callback=lambda *_args, **_kwargs: None,
        can_open_callback=can_open_callback,
    )


class PositionGuardBehaviorTests(unittest.TestCase):
    def test_mark_closed_with_context_preserves_other_contexts(self):
        guard = IntervalPositionGuard()
        first_context = "1m:BUY:rsi|slot0"
        second_context = "1m:BUY:ema|slot0"

        guard.end_open("BTCUSDT", "1m", "BUY", True, context=first_context)
        guard.end_open("BTCUSDT", "1m", "BUY", True, context=second_context)

        bucket = guard.ledger.get(("BTCUSDT", "1m", "BUY"), {})
        self.assertIn(first_context, bucket)
        self.assertIn(second_context, bucket)

        guard.mark_closed("BTCUSDT", "1m", "BUY", context=first_context)

        bucket = guard.ledger.get(("BTCUSDT", "1m", "BUY"), {})
        self.assertNotIn(first_context, bucket)
        self.assertIn(second_context, bucket)
        self.assertTrue(guard.can_open("BTCUSDT", "1m", "BUY", first_context))
        self.assertFalse(guard.can_open("BTCUSDT", "1m", "BUY", second_context))

    def test_context_key_from_entry_prefers_explicit_context(self):
        guard = IntervalPositionGuard()

        explicit = guard.context_key_from_entry(
            "1m",
            "BUY",
            {
                "context_key": "1m:BUY:rsi|slot0",
                "trigger_signature": ["ema", "slot0"],
            },
        )
        derived = guard.context_key_from_entry(
            "1m",
            "BUY",
            {
                "interval_display": "5m",
                "side_key": "S",
                "trigger_signature": ["ema", "slot0"],
            },
        )

        self.assertEqual("1m:BUY:rsi|slot0", explicit)
        self.assertEqual("5m:SELL:ema|slot0", derived)

    def test_close_leg_entry_partial_close_keeps_guard_context_until_flat(self):
        engine = _build_engine()
        engine.guard = IntervalPositionGuard()

        context_key = "1m:BUY:rsi|slot0"
        leg_key = ("BTCUSDT", "1m", "BUY")
        entry = {
            "qty": 1.0,
            "timestamp": 1_735_689_600.0,
            "entry_price": 100.0,
            "leverage": 5,
            "margin_usdt": 20.0,
            "ledger_id": "btc-1m-buy-rsi",
            "trigger_signature": ["rsi", "slot0"],
            "trigger_indicators": ["rsi"],
            "indicator_keys": ["rsi"],
            "context_key": context_key,
        }
        engine._append_leg_entry(leg_key, entry)
        engine.guard.end_open("BTCUSDT", "1m", "BUY", True, context=context_key)

        close_events: list[dict] = []

        def _close_stub(_symbol, _close_side, qty, _preferred_ps):
            return True, {"ok": True, "sent_qty": qty}

        engine._current_futures_position_qty = lambda *_args, **_kwargs: 1.0
        engine._execute_close_with_fallback = _close_stub
        engine._notify_interval_closed = lambda *_args, **kwargs: close_events.append(dict(kwargs))
        engine._log_latency_metric = lambda *_args, **_kwargs: None
        engine._queue_flip_on_close = lambda *_args, **_kwargs: None

        closed_qty = engine._close_leg_entry(
            {"symbol": "BTCUSDT", "interval": "1m"},
            leg_key,
            engine._leg_entries(leg_key)[0],
            "BUY",
            "SELL",
            None,
            loss_usdt=4.0,
            price_pct=4.0,
            margin_pct=20.0,
            qty_limit=0.4,
            queue_flip=False,
            reason="test_partial_close",
        )

        self.assertAlmostEqual(0.4, closed_qty)
        self.assertEqual(1, len(close_events))
        self.assertFalse(close_events[-1]["fully_closed"])
        self.assertAlmostEqual(0.6, close_events[-1]["remaining_qty"])
        self.assertFalse(engine.guard.can_open("BTCUSDT", "1m", "BUY", context_key))
        remaining_entry = engine._leg_entries(leg_key)[0]
        self.assertAlmostEqual(0.6, remaining_entry["qty"])
        self.assertIn(context_key, engine.guard.ledger.get(("BTCUSDT", "1m", "BUY"), {}))

        engine._current_futures_position_qty = lambda *_args, **_kwargs: 0.6
        closed_qty = engine._close_leg_entry(
            {"symbol": "BTCUSDT", "interval": "1m"},
            leg_key,
            remaining_entry,
            "BUY",
            "SELL",
            None,
            loss_usdt=6.0,
            price_pct=6.0,
            margin_pct=30.0,
            queue_flip=False,
            reason="test_full_close",
        )

        self.assertAlmostEqual(0.6, closed_qty)
        self.assertNotIn(leg_key, engine._leg_ledger)
        self.assertNotIn(context_key, engine.guard.ledger.get(("BTCUSDT", "1m", "BUY"), {}))
        self.assertTrue(engine.guard.can_open("BTCUSDT", "1m", "BUY", context_key))

    def test_clear_symbol_side_removes_all_intervals_and_pending_attempts(self):
        guard = IntervalPositionGuard()
        first_context = "1m:BUY:rsi|slot0"
        second_context = "5m:BUY:ema|slot0"

        guard.end_open("BTCUSDT", "1m", "BUY", True, context=first_context)
        guard.end_open("BTCUSDT", "5m", "BUY", True, context=second_context)
        guard.begin_open("BTCUSDT", "1m", "BUY", context=first_context)
        guard.begin_open("BTCUSDT", "5m", "BUY", context=second_context)

        self.assertTrue(guard.ledger)
        self.assertTrue(guard.snapshot_pending_attempts())

        guard.clear_symbol_side("BTCUSDT", "BUY")

        self.assertFalse(guard.ledger)
        self.assertEqual([], guard.snapshot_pending_attempts())
        self.assertEqual({}, guard.active)

    def test_submit_order_releases_pending_guard_claim_on_exchange_abort(self):
        wrapper = _AbortGuardBinance()
        guard = IntervalPositionGuard()
        guard.attach_wrapper(wrapper)
        engine = StrategyEngine(
            wrapper,
            {
                **build_default_config(),
                "symbol": "BTCUSDT",
                "interval": "1m",
                "account_type": "FUTURES",
                "side": "BOTH",
                "leverage": 5,
                "position_pct": 25,
                "position_pct_units": "percent",
                "allow_opposite_positions": False,
            },
            log_callback=lambda *_args, **_kwargs: None,
            can_open_callback=guard.can_open,
        )
        engine.set_guard(guard)

        _order_res, order_success, submit_aborted = engine._submit_futures_signal_order(
            cw={"symbol": "BTCUSDT", "interval": "1m"},
            side="BUY",
            flip_active=False,
            context_key="1m:BUY:rsi|slot0",
            signature=("rsi", "slot0"),
            key_bar=("BTCUSDT", "1m", "BUY"),
            key_dup=("BTCUSDT", "1m", "BUY"),
            current_batch_index=0,
            order_batch_total=1,
            desired_ps=None,
            qty_est=1.0,
            reduce_only=False,
            last_price=100.0,
            lev=5,
            abort_guard=lambda: None,
        )

        self.assertTrue(submit_aborted)
        self.assertFalse(order_success)
        self.assertEqual(0, wrapper.place_calls)
        self.assertEqual([], guard.snapshot_pending_attempts())

        wrapper.positions = []
        self.assertTrue(guard.can_open("BTCUSDT", "1m", "BUY", "1m:BUY:rsi|slot0"))
