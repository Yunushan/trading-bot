import sys
import unittest
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))


from app.core.strategy.orders import strategy_indicator_order_build_runtime as build_runtime
from app.core.strategy.orders import strategy_indicator_order_common_runtime as common_runtime
from app.core.strategy.orders import strategy_indicator_order_directional_runtime as directional_runtime
from app.core.strategy.orders import strategy_indicator_order_fallback_runtime as fallback_runtime
from app.core.strategy.orders import strategy_indicator_order_hedge_runtime as hedge_runtime


class StrategyIndicatorOrderBuildSplitSmokeTests(unittest.TestCase):
    def test_build_facade_matches_split_helpers(self):
        self.assertIs(build_runtime._indicator_exchange_qty, common_runtime._indicator_exchange_qty)
        self.assertIs(
            build_runtime._purge_indicator_side_if_exchange_flat,
            common_runtime._purge_indicator_side_if_exchange_flat,
        )
        self.assertIs(
            build_runtime._build_directional_indicator_order_request,
            directional_runtime._build_directional_indicator_order_request,
        )
        self.assertIs(
            build_runtime._build_fallback_indicator_order_request,
            fallback_runtime._build_fallback_indicator_order_request,
        )
        self.assertIs(
            build_runtime._build_hedge_indicator_order_request,
            hedge_runtime._build_hedge_indicator_order_request,
        )


if __name__ == "__main__":
    unittest.main()
