from __future__ import annotations

import sys
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch


PYTHON_ROOT = Path(__file__).resolve().parents[1]
if str(PYTHON_ROOT) not in sys.path:
    sys.path.insert(0, str(PYTHON_ROOT))

from app.core.strategy.runtime import strategy_cycle_runtime  # noqa: E402


def _cycle_context() -> dict[str, object]:
    return {
        "cw": {"symbol": "BTCUSDT", "interval": "1m"},
        "now_ts": 1_700_000_000.0,
        "allow_opposite_enabled": False,
        "stop_enabled": True,
        "apply_usdt_limit": True,
        "apply_percent_limit": False,
        "stop_usdt_limit": 10.0,
        "stop_percent_limit": 1.0,
        "scope": "per_trade",
        "account_type": "FUTURES",
        "is_cumulative": False,
        "hedge_overlap_allowed": False,
    }


def _market_state() -> dict[str, object]:
    return {
        "df": object(),
        "signal": "BUY",
        "signal_timestamp": 1_700_000_001.0,
        "trigger_desc": "RSI crossed above the entry threshold",
        "trigger_sources": ["rsi"],
        "trigger_actions": ["BUY"],
        "trigger_segments": ["rsi"],
        "current_bar_marker": "bar-1",
        "last_rsi": 55.0,
    }


class _Cycle:
    def __init__(self, *, context: dict[str, object] | None = None):
        self.context = context
        self.apply_stop = False
        self.market_state: dict[str, object] | None = _market_state()
        self.indicator_orders: list[dict[str, object]] = []
        self.prepared_orders: list[dict[str, object]] = []
        self.prepare_stop = False
        self._leg_ledger: dict[tuple[str, str, str], dict[str, object]] = {}
        self.binance = SimpleNamespace(get_futures_dual_side=lambda: False)
        self.calls: list[tuple[str, object]] = []

    def _build_cycle_context(self):
        return self.context

    def _apply_entire_account_stop_loss(self, *, ctx):
        self.calls.append(("account-stop", ctx))
        return self.apply_stop

    def _fetch_cycle_market_state(self, *, ctx):
        self.calls.append(("market-state", ctx))
        return self.market_state

    def _collect_indicator_order_requests(self, **kwargs):
        self.calls.append(("collect-orders", kwargs))
        return self.indicator_orders, 0.001

    def _merge_flip_requests_into_indicator_orders(self, **kwargs):
        self.calls.append(("merge-orders", kwargs))
        return kwargs["indicator_order_requests"]

    def _log_cycle_signal_summary(self, **kwargs):
        self.calls.append(("signal-summary", kwargs))

    def _prepare_signal_orders(self, **kwargs):
        self.calls.append(("prepare-orders", kwargs))
        return self.prepared_orders, {"loaded": True}, self.prepare_stop

    def _execute_signal_order(self, **kwargs):
        self.calls.append(("execute-order", kwargs))


class StrategyCycleRuntimeTests(unittest.TestCase):
    def test_missing_context_returns_without_touching_runtime_state(self):
        strategy = _Cycle(context=None)

        result = strategy_cycle_runtime.run_once(strategy)

        self.assertIsNone(result)
        self.assertEqual([], strategy.calls)

    def test_account_stop_loss_short_circuits_before_market_fetch(self):
        strategy = _Cycle(context=_cycle_context())
        strategy.apply_stop = True

        strategy_cycle_runtime.run_once(strategy)

        self.assertEqual(["account-stop"], [name for name, _ in strategy.calls])

    def test_missing_market_state_short_circuits_before_risk_management(self):
        strategy = _Cycle(context=_cycle_context())
        strategy.market_state = None

        with patch.object(
            strategy_cycle_runtime.strategy_cycle_risk_runtime,
            "_apply_cycle_risk_management",
        ) as risk_management:
            strategy_cycle_runtime.run_once(strategy)

        self.assertEqual(["account-stop", "market-state"], [name for name, _ in strategy.calls])
        risk_management.assert_not_called()

    def test_dual_side_futures_mode_propagates_position_side_guards(self):
        strategy = _Cycle(context=_cycle_context())
        strategy.binance.get_futures_dual_side = lambda: True
        risk_state = {
            "last_price": 100.0,
            "positions_cache": {},
            "load_positions_cache": lambda: {},
            "long_open": False,
            "short_open": False,
        }

        with patch.object(
            strategy_cycle_runtime.strategy_cycle_risk_runtime,
            "_apply_cycle_risk_management",
            return_value=risk_state,
        ) as risk_management:
            strategy_cycle_runtime.run_once(strategy)

        risk_kwargs = risk_management.call_args.kwargs
        self.assertTrue(risk_kwargs["dual_side"])
        self.assertEqual("LONG", risk_kwargs["desired_ps_long_guard"])
        self.assertEqual("SHORT", risk_kwargs["desired_ps_short_guard"])
        collect_payloads = [payload for name, payload in strategy.calls if name == "collect-orders"]
        self.assertEqual(1, len(collect_payloads))
        self.assertTrue(collect_payloads[0]["dual_side"])

    def test_dual_side_lookup_failure_falls_back_to_one_way_guards(self):
        strategy = _Cycle(context=_cycle_context())

        def raise_lookup_error():
            raise RuntimeError("exchange metadata unavailable")

        strategy.binance.get_futures_dual_side = raise_lookup_error
        risk_state = {
            "last_price": 100.0,
            "positions_cache": {},
            "load_positions_cache": lambda: {},
            "long_open": False,
            "short_open": False,
        }

        with patch.object(
            strategy_cycle_runtime.strategy_cycle_risk_runtime,
            "_apply_cycle_risk_management",
            return_value=risk_state,
        ) as risk_management:
            strategy_cycle_runtime.run_once(strategy)

        risk_kwargs = risk_management.call_args.kwargs
        self.assertFalse(risk_kwargs["dual_side"])
        self.assertIsNone(risk_kwargs["desired_ps_long_guard"])
        self.assertIsNone(risk_kwargs["desired_ps_short_guard"])

    def test_internal_ledger_state_is_forwarded_to_risk_management(self):
        strategy = _Cycle(context=_cycle_context())
        strategy._leg_ledger = {
            ("BTCUSDT", "1m", "BUY"): {"qty": 1.0},
            ("BTCUSDT", "1m", "SELL"): {"qty": 2.0},
        }
        risk_state = {
            "last_price": 100.0,
            "positions_cache": {},
            "load_positions_cache": lambda: {},
            "long_open": True,
            "short_open": True,
        }

        with patch.object(
            strategy_cycle_runtime.strategy_cycle_risk_runtime,
            "_apply_cycle_risk_management",
            return_value=risk_state,
        ) as risk_management:
            strategy_cycle_runtime.run_once(strategy)

        risk_kwargs = risk_management.call_args.kwargs
        self.assertTrue(risk_kwargs["long_open"])
        self.assertTrue(risk_kwargs["short_open"])
        self.assertEqual(("BTCUSDT", "1m", "BUY"), risk_kwargs["key_long"])
        self.assertEqual(("BTCUSDT", "1m", "SELL"), risk_kwargs["key_short"])

    def test_full_cycle_executes_prepared_order_and_normalizes_bad_timestamp(self):
        strategy = _Cycle(context=_cycle_context())
        strategy.indicator_orders = [{"side": "BUY", "labels": ["rsi"]}]
        strategy.prepared_orders = [
            {
                "side": "BUY",
                "labels": ["rsi"],
                "signature": ("rsi", "BUY"),
                "timestamp": "not-a-number",
                "flip_from": None,
                "flip_qty": None,
                "flip_qty_target": None,
                "trigger_desc": "rsi entry",
                "trigger_actions": ["BUY"],
            }
        ]
        risk_state = {
            "last_price": 100.0,
            "positions_cache": {"BTCUSDT": []},
            "load_positions_cache": lambda: {"BTCUSDT": []},
            "long_open": False,
            "short_open": False,
        }

        with patch.object(
            strategy_cycle_runtime.strategy_cycle_risk_runtime,
            "_apply_cycle_risk_management",
            return_value=risk_state,
        ) as risk_management:
            strategy_cycle_runtime.run_once(strategy)

        risk_management.assert_called_once()
        executions = [payload for name, payload in strategy.calls if name == "execute-order"]
        self.assertEqual(1, len(executions))
        self.assertIsNone(executions[0]["origin_timestamp"])
        self.assertEqual("BUY", executions[0]["order_side"])
        self.assertEqual("bar-1", executions[0]["current_bar_marker"])

    def test_prepare_stop_prevents_order_execution_after_signal_preparation(self):
        strategy = _Cycle(context=_cycle_context())
        strategy.prepare_stop = True
        strategy.prepared_orders = [{"side": "BUY", "timestamp": 1.0}]
        risk_state = {
            "last_price": 100.0,
            "positions_cache": {},
            "load_positions_cache": lambda: {},
            "long_open": False,
            "short_open": False,
        }

        with patch.object(
            strategy_cycle_runtime.strategy_cycle_risk_runtime,
            "_apply_cycle_risk_management",
            return_value=risk_state,
        ):
            strategy_cycle_runtime.run_once(strategy)

        self.assertFalse(any(name == "execute-order" for name, _ in strategy.calls))


if __name__ == "__main__":
    unittest.main()
