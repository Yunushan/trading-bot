import importlib
import sys
import unittest
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from trading_core.strategy import StrategyEngine as PublicStrategyEngine  # noqa: E402
from app.core.strategy import StrategyEngine  # noqa: E402
from app.core.strategy.orders.strategy_indicator_order_build_runtime import (  # noqa: E402
    _build_directional_indicator_order_request as new_build_directional_indicator_order_request,
)
from app.core.strategy.orders.strategy_signal_orders_runtime import (  # noqa: E402
    bind_strategy_signal_orders_runtime as new_bind_signal_orders,
)
from app.core.strategy.positions.strategy_close_opposite_runtime import (  # noqa: E402
    _close_opposite_position as new_close_opposite_position,
)
from app.core.strategy.positions.strategy_indicator_guard import (  # noqa: E402
    bind_strategy_indicator_guard as new_bind_indicator_guard,
)
from app.core.strategy.positions.strategy_position_close_runtime import (  # noqa: E402
    bind_strategy_position_close_runtime as new_bind_position_close,
)
from app.core.strategy.positions.strategy_position_flip_runtime import (  # noqa: E402
    bind_strategy_position_flip_runtime as new_bind_position_flip,
)
from app.core.strategy.positions.strategy_position_state import (  # noqa: E402
    bind_strategy_position_state as new_bind_position_state,
)
from app.core.strategy.positions.strategy_trade_book import (  # noqa: E402
    bind_strategy_trade_book as new_bind_trade_book,
)
from app.core.strategy.runtime.strategy_cycle_risk_runtime import (  # noqa: E402
    _apply_cycle_risk_management as new_apply_cycle_risk_management,
)
from app.core.strategy.runtime.strategy_cycle_risk_stop_context_runtime import (  # noqa: E402
    build_futures_stop_state as new_build_futures_stop_state,
)
from app.core.strategy.runtime.strategy_cycle_risk_stop_cumulative_runtime import (  # noqa: E402
    apply_cumulative_futures_stop_management as new_apply_cumulative_futures_stop_management,
)
from app.core.strategy.runtime.strategy_cycle_risk_stop_directional_runtime import (  # noqa: E402
    apply_directional_futures_stop_management as new_apply_directional_futures_stop_management,
)
from app.core.strategy.runtime.strategy_cycle_runtime import (  # noqa: E402
    run_once as new_run_once,
)
from app.core.strategy.runtime.strategy_indicator_compute import (  # noqa: E402
    bind_strategy_indicator_compute as new_bind_indicator_compute,
)
from app.core.strategy.runtime.strategy_indicator_tracking import (  # noqa: E402
    bind_strategy_indicator_tracking as new_bind_indicator_tracking,
)
from app.core.strategy.runtime.strategy_runtime import (  # noqa: E402
    bind_strategy_runtime as new_bind_runtime,
)
from app.core.strategy.runtime.strategy_runtime_support import (  # noqa: E402
    bind_strategy_runtime_support as new_bind_runtime_support,
)
from app.core.strategy.runtime.strategy_signal_generation import (  # noqa: E402
    bind_strategy_signal_generation as new_bind_signal_generation,
)


class StrategyPackageSplitSmokeTests(unittest.TestCase):
    def test_canonical_strategy_engine_surface_resolves_to_same_object(self):
        self.assertIs(PublicStrategyEngine, StrategyEngine)

    def test_final_strategy_subpackages_keep_private_helpers_available(self):
        self.assertTrue(callable(new_build_directional_indicator_order_request))
        self.assertTrue(callable(new_close_opposite_position))
        self.assertTrue(callable(new_apply_cycle_risk_management))
        self.assertTrue(callable(new_build_futures_stop_state))
        self.assertTrue(callable(new_apply_cumulative_futures_stop_management))
        self.assertTrue(callable(new_apply_directional_futures_stop_management))

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

    def test_removed_flat_strategy_root_shims_raise_import_error(self):
        removed_modules = [
            "app.strategy",
            "app.strategy_cycle_runtime",
            "app.strategy_indicator_compute",
            "app.strategy_indicator_guard",
            "app.strategy_indicator_tracking",
            "app.strategy_position_close_runtime",
            "app.strategy_position_flip_runtime",
            "app.strategy_position_state",
            "app.strategy_runtime",
            "app.strategy_runtime_support",
            "app.strategy_signal_generation",
            "app.strategy_signal_order_collect_runtime",
            "app.strategy_signal_order_execute_runtime",
            "app.strategy_signal_order_guard_runtime",
            "app.strategy_signal_order_margin_runtime",
            "app.strategy_signal_order_position_gate_runtime",
            "app.strategy_signal_order_prepare_runtime",
            "app.strategy_signal_order_result_runtime",
            "app.strategy_signal_order_sizing_runtime",
            "app.strategy_signal_order_slot_runtime",
            "app.strategy_signal_order_submit_runtime",
            "app.strategy_signal_orders_runtime",
            "app.strategy_trade_book",
        ]

        for module_name in removed_modules:
            with self.subTest(module_name=module_name):
                with self.assertRaises(ModuleNotFoundError):
                    importlib.import_module(module_name)

    def test_canonical_strategy_runtime_bindings_stay_available(self):
        self.assertTrue(callable(new_bind_signal_orders))
        self.assertTrue(callable(new_bind_trade_book))
        self.assertTrue(callable(new_bind_indicator_guard))
        self.assertTrue(callable(new_bind_position_state))
        self.assertTrue(callable(new_bind_position_close))
        self.assertTrue(callable(new_bind_position_flip))
        self.assertTrue(callable(new_bind_runtime))
        self.assertTrue(callable(new_bind_runtime_support))
        self.assertTrue(callable(new_bind_indicator_compute))
        self.assertTrue(callable(new_bind_signal_generation))
        self.assertTrue(callable(new_bind_indicator_tracking))
        self.assertTrue(callable(new_run_once))

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
