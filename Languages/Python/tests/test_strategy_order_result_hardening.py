from __future__ import annotations

import sys
import time
import unittest
from pathlib import Path


PYTHON_ROOT = Path(__file__).resolve().parents[1]
if str(PYTHON_ROOT) not in sys.path:
    sys.path.insert(0, str(PYTHON_ROOT))

from app.config import build_default_config  # noqa: E402
from app.core.strategy import StrategyEngine  # noqa: E402


class _FakeBinance:
    account_type = "FUTURES"


SIGNATURE = ("rsi", "slot0")
GUARD_KEY = ("BTCUSDT", "1m", "BUY")


def _build_engine(*, logs: list[str] | None = None, trade_callback=None) -> StrategyEngine:
    config = build_default_config()
    config["symbol"] = "BTCUSDT"
    config["interval"] = "1m"
    sink = logs if logs is not None else []
    return StrategyEngine(
        _FakeBinance(),
        config,
        log_callback=sink.append,
        trade_callback=trade_callback,
    )


def _result_kwargs(order_res) -> dict[str, object]:
    return {
        "cw": {"symbol": "BTCUSDT", "interval": "1m", "price": 100.0, "leverage": 5},
        "side": "BUY",
        "order_res": order_res,
        "trigger_labels": ["rsi"],
        "trigger_desc_for_order": "rsi",
        "order_event_uid": "event-1",
        "trigger_actions_for_order": {"rsi": "buy"},
        "current_bar_marker": 123,
        "bar_sig_key": GUARD_KEY,
        "sig_sorted": SIGNATURE,
        "guard_claimed": True,
        "guard_key_symbol": GUARD_KEY,
        "signature_guard_key": SIGNATURE,
        "guard_window": 8.0,
        "signature": SIGNATURE,
        "context_key": "rsi",
        "slot_key_tuple": ("slot0",),
        "price": 100.0,
        "qty_est": 1.0,
        "lev": 5,
    }


def _successful_order_result() -> dict[str, object]:
    return {
        "ok": True,
        "info": {
            "origQty": "1",
            "executedQty": "1",
            "avgPrice": "100",
            "leverage": "5",
            "orderId": 42,
        },
        "computed": {"qty": 1.0, "px": 100.0, "lev": 5},
        "fills": {"filled_qty": 1.0, "avg_price": 100.0, "commission_usdt": 0.01},
    }


class StrategyOrderResultHardeningTests(unittest.TestCase):
    def setUp(self):
        StrategyEngine._GLOBAL_PAUSE.clear()
        StrategyEngine._GLOBAL_PAUSE_FALLBACK = False
        StrategyEngine._SYMBOL_ORDER_STATE.clear()
        StrategyEngine._BAR_GLOBAL_SIGNATURES.clear()
        StrategyEngine._SYMBOL_ORDER_STATE[GUARD_KEY] = {
            "pending_map": {SIGNATURE: time.time()},
            "signatures": {},
            "last": 0.0,
        }

    def tearDown(self):
        StrategyEngine._GLOBAL_PAUSE.clear()
        StrategyEngine._GLOBAL_PAUSE_FALLBACK = False
        StrategyEngine._SYMBOL_ORDER_STATE.clear()
        StrategyEngine._BAR_GLOBAL_SIGNATURES.clear()

    def test_trade_callback_failure_does_not_erase_successful_order_state(self):
        def fail_trade_callback(_payload):
            raise RuntimeError("trade callback failed")

        engine = _build_engine(trade_callback=fail_trade_callback)

        with self.assertLogs(
            "app.core.strategy.orders.strategy_signal_order_result_runtime",
            level="ERROR",
        ):
            order_ok, qty_display = engine._handle_futures_signal_order_result(
                **_result_kwargs(_successful_order_result())
            )

        self.assertTrue(order_ok)
        self.assertEqual(1.0, float(qty_display))
        self.assertFalse(StrategyEngine._GLOBAL_PAUSE.is_set())
        state = StrategyEngine._SYMBOL_ORDER_STATE[GUARD_KEY]
        self.assertNotIn(SIGNATURE, state["pending_map"])
        self.assertIn(SIGNATURE, state["signatures"])
        entries = engine._leg_ledger[GUARD_KEY]["entries"]
        self.assertEqual(1, len(entries))
        self.assertEqual(1.0, entries[0]["qty"])

    def test_ledger_write_failure_pauses_after_known_success_and_retains_guard(self):
        logs: list[str] = []
        engine = _build_engine(logs=logs)

        def fail_append(*_args, **_kwargs):
            raise RuntimeError("ledger write failed")

        engine._append_leg_entry = fail_append

        order_ok, _qty_display = engine._handle_futures_signal_order_result(
            **_result_kwargs(_successful_order_result())
        )

        self.assertTrue(order_ok)
        self.assertTrue(StrategyEngine._GLOBAL_PAUSE.is_set())
        state = StrategyEngine._SYMBOL_ORDER_STATE[GUARD_KEY]
        self.assertNotIn(SIGNATURE, state["pending_map"])
        self.assertIn(SIGNATURE, state["signatures"])
        self.assertIn("could not be recorded locally", "\n".join(logs))

    def test_success_without_positive_quantity_pauses_for_reconciliation(self):
        logs: list[str] = []
        engine = _build_engine(logs=logs)
        result = {"ok": True, "info": {}, "computed": {}, "fills": {}}
        kwargs = _result_kwargs(result)
        kwargs["qty_est"] = 0.0

        order_ok, _qty_display = engine._handle_futures_signal_order_result(**kwargs)

        self.assertTrue(order_ok)
        self.assertTrue(StrategyEngine._GLOBAL_PAUSE.is_set())
        self.assertIn("no positive executed quantity", "\n".join(logs))

    def test_malformed_result_is_failed_and_releases_pending_guard(self):
        logs: list[str] = []
        engine = _build_engine(logs=logs)

        order_ok, qty_display = engine._handle_futures_signal_order_result(
            **_result_kwargs(["not", "a", "mapping"])
        )

        self.assertFalse(order_ok)
        self.assertEqual(1.0, qty_display)
        state = StrategyEngine._SYMBOL_ORDER_STATE[GUARD_KEY]
        self.assertNotIn(SIGNATURE, state["pending_map"])
        self.assertIn("expected an object", "\n".join(logs))


if __name__ == "__main__":
    unittest.main()
