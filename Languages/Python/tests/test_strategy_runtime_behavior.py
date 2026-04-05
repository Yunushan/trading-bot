from __future__ import annotations

import sys
import unittest
from pathlib import Path

try:
    import pandas as pd

    PANDAS_AVAILABLE = True
except Exception:
    pd = None
    PANDAS_AVAILABLE = False


PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from app.config import build_default_config  # noqa: E402
from app.core.strategy import StrategyEngine  # noqa: E402


class _FakeStrategyBinance:
    account_type = "FUTURES"

    def __init__(self) -> None:
        self.net_amt = 0.0

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
        return self.net_amt


def _build_engine(*, wrapper=None, logs=None):
    config = build_default_config()
    config["symbol"] = "BTCUSDT"
    config["interval"] = "1m"
    config["account_type"] = "FUTURES"
    config["side"] = "BOTH"
    config["leverage"] = 5
    config["position_pct"] = 25
    config["position_pct_units"] = "percent"
    sink = logs if logs is not None else []
    return StrategyEngine(
        wrapper or _FakeStrategyBinance(),
        config,
        log_callback=sink.append,
    )


class StrategyRuntimeBehaviorTests(unittest.TestCase):
    def test_engine_coerces_string_boolean_runtime_flags(self):
        wrapper = _FakeStrategyBinance()
        config = build_default_config()
        config["symbol"] = "BTCUSDT"
        config["interval"] = "1m"
        config["indicator_use_live_values"] = "false"
        config["indicator_reentry_requires_signal_reset"] = "0"

        engine = StrategyEngine(wrapper, config, log_callback=lambda *_args, **_kwargs: None)

        self.assertFalse(engine._indicator_use_live_values)
        self.assertFalse(engine._indicator_reentry_requires_reset)

    @unittest.skipUnless(PANDAS_AVAILABLE, "pandas is required for strategy signal behavior tests")
    def test_generate_signal_respects_string_indicator_enabled_flags(self):
        engine = _build_engine()
        engine.config["side"] = "BUY"
        engine.config["indicators"]["rsi"]["buy_value"] = 30
        engine.config["indicators"]["rsi"]["sell_value"] = 70

        df = pd.DataFrame({"close": [100.0, 101.0, 102.0]})
        ind = {"rsi": pd.Series([50.0, 25.0, 20.0])}

        engine.config["indicators"]["rsi"]["enabled"] = "false"
        signal, _desc, _price, sources, actions = engine.generate_signal(df, ind)
        self.assertIsNone(signal)
        self.assertEqual([], sources)
        self.assertEqual({}, actions)

        engine.config["indicators"]["rsi"]["enabled"] = "true"
        signal, _desc, _price, sources, actions = engine.generate_signal(df, ind)
        self.assertEqual("BUY", signal)
        self.assertEqual(["rsi"], sources)
        self.assertEqual({"rsi": "buy"}, actions)

    @unittest.skipUnless(PANDAS_AVAILABLE, "pandas is required for strategy indicator behavior tests")
    def test_compute_indicators_respects_string_indicator_enabled_flags(self):
        engine = _build_engine()
        engine.config["indicators"]["rsi"]["enabled"] = "false"
        engine.config["indicators"]["ema"]["enabled"] = "true"
        engine.config["indicators"]["ema"]["length"] = 2

        df = pd.DataFrame(
            {
                "open": [100.0, 101.0, 102.0],
                "high": [101.0, 102.0, 103.0],
                "low": [99.0, 100.0, 101.0],
                "close": [100.0, 101.0, 102.0],
                "volume": [1000.0, 1000.0, 1000.0],
            }
        )

        indicators = engine.compute_indicators(df)

        self.assertNotIn("rsi", indicators)
        self.assertIn("ema", indicators)

    def test_queue_flip_on_close_respects_string_trade_and_indicator_flags(self):
        engine = _build_engine()
        entry = {"qty": 1.0, "indicator_keys": ["rsi"]}
        payload = {"qty": 1.0, "reason": "per_trade_stop_loss"}

        engine.config["auto_flip_on_close"] = "true"
        engine.config["trade_on_signal"] = "false"
        engine.config["indicators"]["rsi"]["enabled"] = True
        engine._queue_flip_on_close("1m", "BUY", entry, payload)
        self.assertEqual({}, engine._flip_on_close_requests)

        engine.config["trade_on_signal"] = "true"
        engine.config["indicators"]["rsi"]["enabled"] = "false"
        engine._queue_flip_on_close("1m", "BUY", entry, payload)
        self.assertEqual({}, engine._flip_on_close_requests)

        engine.config["indicators"]["rsi"]["enabled"] = "true"
        engine._queue_flip_on_close("1m", "BUY", entry, payload)
        self.assertEqual(1, len(engine._flip_on_close_requests))

    def test_resolve_signal_order_account_state_falls_back_from_invalid_position_pct(self):
        engine = _build_engine()

        state = engine._resolve_signal_order_account_state(
            cw={"position_pct": "not-a-number", "position_pct_units": "percent"},
            last_price=123.45,
        )

        self.assertEqual("FUTURES", state["account_type"])
        self.assertAlmostEqual(1000.0, state["free_usdt"])
        self.assertAlmostEqual(0.25, state["pct"])
        self.assertAlmostEqual(123.45, state["price"])

    def test_prepare_signal_order_margin_state_ignores_false_string_add_only(self):
        wrapper = _FakeStrategyBinance()
        wrapper.net_amt = 2.0
        engine = _build_engine(wrapper=wrapper)
        engine.config["add_only"] = "false"

        state = engine._prepare_signal_order_margin_state(
            cw={"symbol": "BTCUSDT", "interval": "1m"},
            side="SELL",
            pct=0.1,
            free_usdt=1000.0,
            price=100.0,
            futures_balance_snap={"available": 1000.0, "wallet": 1000.0},
            flip_close_qty=0.0,
            entries_side_all=[],
            active_slot_tokens_all=set(),
            existing_margin_indicator_total=0.0,
            slot_label="rsi",
            slot_token_for_order="rsi",
            lev=5,
            abort_guard=lambda: None,
        )

        self.assertFalse(state["aborted"])
        self.assertFalse(state["reduce_only"])
        self.assertAlmostEqual(5.0, state["qty_est"])

        engine.config["add_only"] = "true"
        state = engine._prepare_signal_order_margin_state(
            cw={"symbol": "BTCUSDT", "interval": "1m"},
            side="SELL",
            pct=0.1,
            free_usdt=1000.0,
            price=100.0,
            futures_balance_snap={"available": 1000.0, "wallet": 1000.0},
            flip_close_qty=0.0,
            entries_side_all=[],
            active_slot_tokens_all=set(),
            existing_margin_indicator_total=0.0,
            slot_label="rsi",
            slot_token_for_order="rsi",
            lev=5,
            abort_guard=lambda: None,
        )

        self.assertFalse(state["aborted"])
        self.assertTrue(state["reduce_only"])
        self.assertAlmostEqual(2.0, state["qty_est"])
