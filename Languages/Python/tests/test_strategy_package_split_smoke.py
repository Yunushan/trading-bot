import importlib
import sys
import unittest
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from app import strategy
from app.core.strategy import StrategyEngine
from app.core.strategy.orders.strategy_indicator_order_build_runtime import (
    _build_directional_indicator_order_request as new_build_directional_indicator_order_request,
)
from app.core.strategy.orders.strategy_signal_orders_runtime import (
    bind_strategy_signal_orders_runtime as new_bind_signal_orders,
)
from app.core.strategy.positions.strategy_close_opposite_runtime import (
    _close_opposite_position as new_close_opposite_position,
)
from app.core.strategy.positions.strategy_indicator_guard import (
    bind_strategy_indicator_guard as new_bind_indicator_guard,
)
from app.core.strategy.positions.strategy_position_close_runtime import (
    bind_strategy_position_close_runtime as new_bind_position_close,
)
from app.core.strategy.positions.strategy_position_flip_runtime import (
    bind_strategy_position_flip_runtime as new_bind_position_flip,
)
from app.core.strategy.positions.strategy_position_state import (
    bind_strategy_position_state as new_bind_position_state,
)
from app.core.strategy.positions.strategy_trade_book import (
    bind_strategy_trade_book as new_bind_trade_book,
)
from app.core.strategy.runtime.strategy_cycle_risk_runtime import (
    _apply_cycle_risk_management as new_apply_cycle_risk_management,
)
from app.core.strategy.runtime.strategy_cycle_runtime import (
    run_once as new_run_once,
)
from app.core.strategy.runtime.strategy_indicator_compute import (
    bind_strategy_indicator_compute as new_bind_indicator_compute,
)
from app.core.strategy.runtime.strategy_indicator_tracking import (
    bind_strategy_indicator_tracking as new_bind_indicator_tracking,
)
from app.core.strategy.runtime.strategy_runtime import (
    bind_strategy_runtime as new_bind_runtime,
)
from app.core.strategy.runtime.strategy_runtime_support import (
    bind_strategy_runtime_support as new_bind_runtime_support,
)
from app.core.strategy.runtime.strategy_signal_generation import (
    bind_strategy_signal_generation as new_bind_signal_generation,
)
from app.strategy_cycle_runtime import run_once as root_run_once
from app.strategy_indicator_compute import bind_strategy_indicator_compute as root_bind_indicator_compute
from app.strategy_indicator_guard import bind_strategy_indicator_guard as root_bind_indicator_guard
from app.strategy_indicator_tracking import bind_strategy_indicator_tracking as root_bind_indicator_tracking
from app.strategy_position_close_runtime import (
    bind_strategy_position_close_runtime as root_bind_position_close,
)
from app.strategy_position_flip_runtime import (
    bind_strategy_position_flip_runtime as root_bind_position_flip,
)
from app.strategy_position_state import bind_strategy_position_state as root_bind_position_state
from app.strategy_runtime import bind_strategy_runtime as root_bind_runtime
from app.strategy_runtime_support import (
    bind_strategy_runtime_support as root_bind_runtime_support,
)
from app.strategy_signal_generation import bind_strategy_signal_generation as root_bind_signal_generation
from app.strategy_signal_orders_runtime import (
    bind_strategy_signal_orders_runtime as root_bind_signal_orders,
)
from app.strategy_trade_book import bind_strategy_trade_book as root_bind_trade_book


class StrategyPackageSplitSmokeTests(unittest.TestCase):
    def test_root_shims_resolve_to_same_objects(self):
        self.assertIs(strategy.StrategyEngine, StrategyEngine)
        self.assertIs(root_bind_signal_orders, new_bind_signal_orders)
        self.assertIs(root_bind_trade_book, new_bind_trade_book)
        self.assertIs(root_bind_indicator_guard, new_bind_indicator_guard)
        self.assertIs(root_bind_position_state, new_bind_position_state)
        self.assertIs(root_bind_position_close, new_bind_position_close)
        self.assertIs(root_bind_position_flip, new_bind_position_flip)
        self.assertIs(root_bind_runtime, new_bind_runtime)
        self.assertIs(root_bind_runtime_support, new_bind_runtime_support)
        self.assertIs(root_bind_indicator_compute, new_bind_indicator_compute)
        self.assertIs(root_bind_signal_generation, new_bind_signal_generation)
        self.assertIs(root_bind_indicator_tracking, new_bind_indicator_tracking)
        self.assertIs(root_run_once, new_run_once)

    def test_final_strategy_subpackages_keep_private_helpers_available(self):
        self.assertTrue(callable(new_build_directional_indicator_order_request))
        self.assertTrue(callable(new_close_opposite_position))
        self.assertTrue(callable(new_apply_cycle_risk_management))

    def test_removed_intermediate_strategy_modules_raise_import_error(self):
        removed_modules = [
            "app.core.strategy.strategy_close_opposite_runtime",
            "app.core.strategy.strategy_cycle_risk_runtime",
            "app.core.strategy.strategy_cycle_runtime",
            "app.core.strategy.strategy_indicator_compute",
            "app.core.strategy.strategy_indicator_guard",
            "app.core.strategy.strategy_indicator_order_build_runtime",
            "app.core.strategy.strategy_indicator_order_context_runtime",
            "app.core.strategy.strategy_indicator_tracking",
            "app.core.strategy.strategy_position_close_runtime",
            "app.core.strategy.strategy_position_flip_runtime",
            "app.core.strategy.strategy_position_state",
            "app.core.strategy.strategy_runtime",
            "app.core.strategy.strategy_runtime_support",
            "app.core.strategy.strategy_signal_generation",
            "app.core.strategy.strategy_signal_order_collect_runtime",
            "app.core.strategy.strategy_signal_order_execute_runtime",
            "app.core.strategy.strategy_signal_order_guard_runtime",
            "app.core.strategy.strategy_signal_order_margin_runtime",
            "app.core.strategy.strategy_signal_order_position_gate_runtime",
            "app.core.strategy.strategy_signal_order_prepare_runtime",
            "app.core.strategy.strategy_signal_order_result_runtime",
            "app.core.strategy.strategy_signal_order_sizing_runtime",
            "app.core.strategy.strategy_signal_order_slot_runtime",
            "app.core.strategy.strategy_signal_order_submit_runtime",
            "app.core.strategy.strategy_signal_orders_runtime",
            "app.core.strategy.strategy_trade_book",
        ]

        for module_name in removed_modules:
            with self.subTest(module_name=module_name):
                with self.assertRaises(ModuleNotFoundError):
                    importlib.import_module(module_name)

    def test_strategy_engine_still_exposes_runtime_order_and_position_helpers(self):
        expected_methods = [
            "compute_indicators",
            "generate_signal",
            "run_loop",
            "stop",
            "start",
            "_build_cycle_context",
            "_fetch_cycle_market_state",
            "_log_cycle_signal_summary",
            "_notify_interval_closed",
            "_indicator_register_entry",
            "_collect_indicator_order_requests",
            "_prepare_signal_orders",
            "_execute_signal_order",
            "_prepare_signal_order_guard",
            "_prepare_signal_order_margin_state",
            "_prepare_signal_order_position_gate",
            "_prepare_signal_order_slot_state",
            "_merge_flip_requests_into_indicator_orders",
            "_close_opposite_position",
            "_apply_entire_account_stop_loss",
            "_trade_book_add_entry",
            "_append_leg_entry",
            "_indicator_hold_ready",
        ]
        for method_name in expected_methods:
            with self.subTest(method_name=method_name):
                self.assertTrue(hasattr(StrategyEngine, method_name))
                self.assertTrue(callable(getattr(StrategyEngine, method_name)))


if __name__ == "__main__":
    unittest.main()
