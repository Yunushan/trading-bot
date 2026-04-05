import sys
import unittest
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from trading_core.strategy import StrategyEngine  # noqa: E402


class _FakeFuturesBinance:
    account_type = "FUTURES"

    def __init__(self):
        self.snapshot_calls = 0

    def get_futures_balance_snapshot(self, force_refresh=False):
        self.snapshot_calls += 1
        return {"total": "123.5", "wallet": "120.0", "available": "90.0"}

    def get_total_usdt_value(self):
        return 0.0


class _FakeSpotBinance:
    account_type = "SPOT"

    def get_total_usdt_value(self):
        return 77.25


def _build_engine(binance_wrapper, *, config=None):
    base_config = {
        "symbol": "BTCUSDT",
        "interval": "1m",
        "stop_loss": {},
    }
    if config:
        base_config.update(config)
    return StrategyEngine(
        binance_wrapper,
        base_config,
        log_callback=lambda *args, **kwargs: None,
    )


class StrategySplitSmokeTests(unittest.TestCase):
    def test_strategy_engine_has_split_runtime_methods(self):
        expected_methods = [
            "_build_cycle_context",
            "_fetch_cycle_market_state",
            "_log_cycle_signal_summary",
            "_apply_entire_account_stop_loss",
            "_collect_indicator_order_requests",
            "_merge_flip_requests_into_indicator_orders",
            "_prepare_signal_orders",
            "_execute_signal_order",
            "_prepare_signal_order_guard",
            "_submit_futures_signal_order",
            "_handle_futures_signal_order_result",
            "_resolve_signal_order_account_state",
            "_prepare_futures_signal_order_state",
            "_prepare_signal_order_slot_state",
            "_prepare_signal_order_margin_state",
            "_prepare_signal_order_position_gate",
        ]

        for method_name in expected_methods:
            with self.subTest(method_name=method_name):
                self.assertTrue(hasattr(StrategyEngine, method_name))
                self.assertTrue(callable(getattr(StrategyEngine, method_name)))

    def test_strategy_engine_instance_exposes_bound_runtime_helpers(self):
        engine = _build_engine(_FakeFuturesBinance())

        self.assertEqual(engine._interval_to_seconds("5m"), 300)
        self.assertTrue(callable(engine._build_cycle_context))
        self.assertTrue(callable(engine._fetch_cycle_market_state))
        self.assertTrue(callable(engine._log_cycle_signal_summary))
        self.assertTrue(callable(engine._apply_entire_account_stop_loss))
        self.assertTrue(callable(engine._collect_indicator_order_requests))
        self.assertTrue(callable(engine._merge_flip_requests_into_indicator_orders))
        self.assertTrue(callable(engine._prepare_signal_orders))
        self.assertTrue(callable(engine._execute_signal_order))
        self.assertTrue(callable(engine._prepare_signal_order_slot_state))
        self.assertTrue(callable(engine._prepare_signal_order_margin_state))
        self.assertTrue(callable(engine._prepare_signal_order_position_gate))

    def test_resolve_account_state_uses_futures_snapshot(self):
        wrapper = _FakeFuturesBinance()
        engine = _build_engine(
            wrapper,
            config={
                "account_type": "FUTURES",
                "position_pct": 25,
                "position_pct_units": "percent",
            },
        )

        state = engine._resolve_signal_order_account_state(
            cw={"position_pct": 25, "position_pct_units": "percent"},
            last_price=101.5,
        )

        self.assertEqual(state["account_type"], "FUTURES")
        self.assertAlmostEqual(state["free_usdt"], 123.5)
        self.assertAlmostEqual(state["pct"], 0.25)
        self.assertAlmostEqual(state["price"], 101.5)
        self.assertEqual(wrapper.snapshot_calls, 1)

    def test_resolve_account_state_uses_total_balance_for_non_futures(self):
        engine = _build_engine(
            _FakeSpotBinance(),
            config={
                "account_type": "SPOT",
                "position_pct": 0.4,
                "position_pct_units": "ratio",
            },
        )

        state = engine._resolve_signal_order_account_state(
            cw={"position_pct": 0.4, "position_pct_units": "ratio"},
            last_price=55.0,
        )

        self.assertEqual(state["account_type"], "SPOT")
        self.assertAlmostEqual(state["free_usdt"], 77.25)
        self.assertAlmostEqual(state["pct"], 0.4)
        self.assertAlmostEqual(state["price"], 55.0)


if __name__ == "__main__":
    unittest.main()
