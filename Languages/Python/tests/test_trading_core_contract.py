import sys
import tomllib
import unittest
import importlib
from pathlib import Path

PYTHON_ROOT = Path(__file__).resolve().parents[1]
if str(PYTHON_ROOT) not in sys.path:
    sys.path.insert(0, str(PYTHON_ROOT))

import trading_core  # noqa: E402
from app.core import indicators as app_indicators  # noqa: E402
from app.core.backtest import (  # noqa: E402
    BacktestEngine as AppBacktestEngine,
    BacktestRequest as AppBacktestRequest,
    BacktestRunResult as AppBacktestRunResult,
    IndicatorDefinition as AppIndicatorDefinition,
    PairOverride as AppPairOverride,
)
from app.core.positions import IntervalPositionGuard as AppIntervalPositionGuard  # noqa: E402
from app.core.strategy import StrategyEngine as AppStrategyEngine  # noqa: E402
from trading_core import indicators as trading_indicators  # noqa: E402
from trading_core.backtest import (  # noqa: E402
    BacktestEngine,
    BacktestRequest,
    BacktestRunResult,
    IndicatorDefinition,
    PairOverride,
)
from trading_core.positions import IntervalPositionGuard  # noqa: E402
from trading_core.strategy import StrategyEngine  # noqa: E402


class TradingCoreContractTests(unittest.TestCase):
    def test_pyproject_exposes_trading_core_as_packaged_typed_public_surface(self):
        data = tomllib.loads((PYTHON_ROOT / "pyproject.toml").read_text(encoding="utf-8"))
        package_includes = data["tool"]["setuptools"]["packages"]["find"]["include"]
        package_data = data["tool"]["setuptools"]["package-data"]
        ruff_src = data["tool"]["ruff"]["src"]
        pytest_addopts = data["tool"]["pytest"]["ini_options"]["addopts"]

        self.assertIn("trading_core*", package_includes)
        self.assertEqual(package_data["trading_core"], ["py.typed"])
        self.assertIn("trading_core", ruff_src)
        self.assertIn("--cov=trading_core", pytest_addopts)
        self.assertTrue((PYTHON_ROOT / "trading_core" / "py.typed").is_file())

    def test_top_level_trading_core_exports_map_to_existing_domain_implementations(self):
        self.assertIs(trading_core.BacktestEngine, AppBacktestEngine)
        self.assertIs(trading_core.BacktestRequest, AppBacktestRequest)
        self.assertIs(trading_core.BacktestRunResult, AppBacktestRunResult)
        self.assertIs(trading_core.IndicatorDefinition, AppIndicatorDefinition)
        self.assertIs(trading_core.PairOverride, AppPairOverride)
        self.assertIs(trading_core.IntervalPositionGuard, AppIntervalPositionGuard)
        self.assertIs(trading_core.StrategyEngine, AppStrategyEngine)
        self.assertIs(trading_core.indicators.sma, app_indicators.sma)

    def test_domain_modules_reexport_stable_public_contracts(self):
        self.assertIs(BacktestEngine, AppBacktestEngine)
        self.assertIs(BacktestRequest, AppBacktestRequest)
        self.assertIs(BacktestRunResult, AppBacktestRunResult)
        self.assertIs(IndicatorDefinition, AppIndicatorDefinition)
        self.assertIs(PairOverride, AppPairOverride)
        self.assertIs(IntervalPositionGuard, AppIntervalPositionGuard)
        self.assertIs(StrategyEngine, AppStrategyEngine)
        self.assertIs(trading_indicators.rsi, app_indicators.rsi)
        self.assertIs(trading_indicators.supertrend, app_indicators.supertrend)

    def test_removed_flat_domain_shims_stay_gone(self):
        removed_modules = [
            "app.backtester",
            "app.indicators",
            "app.position_guard",
        ]

        for module_name in removed_modules:
            with self.subTest(module_name=module_name):
                with self.assertRaises(ModuleNotFoundError):
                    importlib.import_module(module_name)
