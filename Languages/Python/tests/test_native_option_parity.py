from __future__ import annotations

import json
import math
import sys
import unittest
from pathlib import Path

import pandas as pd


PYTHON_ROOT = Path(__file__).resolve().parents[1]
REPO_ROOT = Path(__file__).resolve().parents[3]

if str(PYTHON_ROOT) not in sys.path:
    sys.path.insert(0, str(PYTHON_ROOT))
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from app.gui.backtest.backtest_templates import BACKTEST_TEMPLATE_DEFINITIONS  # noqa: E402
from app.gui.runtime.composition.module_state_constants import (  # noqa: E402
    BACKTEST_INTERVAL_ORDER,
    DASHBOARD_LOOP_CHOICES,
    DEFAULT_CHART_SYMBOLS,
    _connector_options,
)
from app.settings.indicators import INDICATOR_CATALOG, MOVING_AVERAGE_TYPE_OPTIONS  # noqa: E402
from app.core.strategy.runtime.strategy_runtime_support import (  # noqa: E402
    _indicator_prev_live_signal_values,
)
from app.core.strategy.runtime.strategy_signal_generation import generate_signal  # noqa: E402
from tools import audit_native_source_sync  # noqa: E402


CPP_SRC = REPO_ROOT / "experiments" / "native-cpp" / "src"
CPP_GENERATED_PARITY = CPP_SRC / "generated" / "PythonParityContract.h"
RUST_CORE = REPO_ROOT / "experiments" / "rust-shells" / "crates" / "core" / "src" / "lib.rs"
RUST_CORE_SRC = RUST_CORE.parent
RUST_TAURI_HTML = REPO_ROOT / "experiments" / "rust-shells" / "apps" / "tauri-desktop" / "ui" / "index.html"
RUST_TAURI_GENERATED = (
    REPO_ROOT
    / "experiments"
    / "rust-shells"
    / "apps"
    / "tauri-desktop"
    / "ui"
    / "generated-python-parity.js"
)


def _read(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def _read_cpp_sources() -> str:
    source_paths = [*sorted(CPP_SRC.glob("TradingBotWindow*.cpp")), CPP_GENERATED_PARITY]
    return "\n".join(_read(path) for path in source_paths)


class NativeOptionParityTests(unittest.TestCase):
    maxDiff = None

    def test_python_signal_rejects_non_finite_candle_closes(self):
        strategy = type("FixtureStrategy", (), {})()
        strategy.config = {
            "side": "BUY",
            "indicators": {
                "rsi": {"enabled": True, "buy_value": 30.0, "sell_value": 70.0},
            },
        }
        strategy._indicator_use_live_values = True
        strategy._indicator_prev_live_signal_values = lambda series: _indicator_prev_live_signal_values(
            strategy,
            series,
        )
        frame = pd.DataFrame(
            {
                "close": [100.0, math.nan],
                "open": [100.0, math.nan],
                "high": [101.0, math.nan],
                "low": [99.0, math.nan],
                "volume": [10.0, 10.0],
            }
        )

        self.assertEqual(
            (None, "no data", None, [], {}),
            generate_signal(strategy, frame, {"rsi": pd.Series([50.0, 20.0])}),
        )

    def assert_all_present(self, text: str, values: list[str], context: str) -> None:
        missing = [value for value in values if value not in text]
        self.assertEqual([], missing, f"{context} missing: {missing}")

    def test_cpp_surfaces_expose_python_intervals_symbols_and_indicators(self):
        dashboard_text = _read(CPP_SRC / "TradingBotWindow.dashboard_ui.cpp")
        backtest_text = _read(CPP_SRC / "TradingBotWindow.backtest.cpp")
        chart_text = _read(CPP_SRC / "TradingBotWindow.chart.cpp")

        self.assert_all_present(
            dashboard_text,
            [
                "pythonSourceDefaultExecutionSymbols",
                "pythonSourceBacktestIntervals",
            ],
            "C++ dashboard Python-sourced symbols/intervals",
        )
        self.assert_all_present(
            backtest_text,
            [
                "pythonSourceDefaultBacktestSymbols",
                "pythonSourceBacktestIntervals",
            ],
            "C++ backtest Python-sourced symbols/intervals",
        )
        self.assert_all_present(
            chart_text,
            [
                "pythonSourceChartMarketOptions",
                "pythonSourceBacktestIntervals",
                "pythonSourceChartViewOptionKeys",
            ],
            "C++ chart Python-sourced markets/intervals/views",
        )

        for context, text in {
            "dashboard": dashboard_text,
            "backtest": backtest_text,
        }.items():
            with self.subTest(context=context):
                self.assert_all_present(
                    text,
                    ["pythonSourceIndicatorDisplayNames"],
                    f"C++ {context} indicators",
                )
        self.assertIn("pythonSourceDefaultEnabledIndicatorKeys", dashboard_text)

    def test_cpp_supports_python_option_values_and_llm_catalog(self):
        text = _read_cpp_sources()
        config_persistence_text = _read(CPP_SRC / "NativeConfigPersistence.cpp")
        connector_keys = [value for _, value in _connector_options()]

        self.assert_all_present(
            text,
            [
                "Time-in-Force",
                "GTD minutes",
                "pythonSourceConfigModeOptionLabels",
                "pythonSourceThemeOptionLabels",
                "pythonSourceAccountTypeOptionLabels",
                "pythonSourceAccountModeOptions",
                "pythonSourceMarginModeOptionLabels",
                "pythonSourcePositionModeOptionLabels",
                "pythonSourceAssetsModeOptionLabels",
                "pythonSourceTimeInForceOptionLabels",
                "pythonSourceSignalLogicOptionLabels",
                "pythonSourceMddLogicOptionLabels",
                "pythonSourceStopLossModeLabels",
                "pythonSourceStopLossScopeLabels",
                "pythonSourceBacktestTemplateLabels",
                "pythonSourceDashboardStrategyTemplateLabels",
                "pythonSourceExchangeOptionDisabledLabels",
                "pythonSourceLlmProviderConfigs",
                "pythonSourceLlmUseForOptionLabels",
                "PythonParityContract::kPythonLlmProviders",
                "default_model",
                "default_reasoning",
                "PythonParityContract::kPythonConnectorOptions",
                "pythonConnectorOptions",
                "populateComboFromPythonSourceOptions",
            ],
            "C++ Python-sourced account/order/backtest options",
        )
        self.assert_all_present(text, ["pythonSourceDashboardLoopChoiceLabels"], "C++ loop options")
        self.assert_all_present(text, connector_keys, "C++ connector keys")
        self.assertNotIn('useForCombo->addItem("Advisory"', text)
        self.assertIn(
            "stringOptionChoices(PythonParityContract::kPythonChartMarketOptions)",
            config_persistence_text,
            "C++ chart-market validation must consume Python's chart-market catalog",
        )

    def test_cpp_indicator_runtime_knows_python_indicator_keys(self):
        runtime_text = _read(CPP_SRC / "TradingBotWindow.dashboard_runtime_shared.cpp")
        dialog_text = _read(CPP_SRC / "TradingBotWindow.dashboard_indicator_dialog.cpp")
        indicator_keys = [definition.key for definition in INDICATOR_CATALOG]

        self.assert_all_present(runtime_text, indicator_keys, "C++ indicator normalization keys")
        self.assert_all_present(dialog_text + runtime_text, indicator_keys, "C++ indicator dialog keys")

    def test_cpp_indicator_dialog_uses_python_moving_average_options(self):
        dialog_text = _read(CPP_SRC / "TradingBotWindow.dashboard_indicator_dialog.cpp")
        self.assertIn("PythonParityContract::kPythonIndicatorMaTypeOptions", dialog_text)
        self.assertIn("pythonSourceMovingAverageTypeOptions", dialog_text)
        for option in MOVING_AVERAGE_TYPE_OPTIONS:
            with self.subTest(option=option):
                self.assertIn(option, dialog_text + _read(CPP_GENERATED_PARITY))
        self.assertNotIn('QStringLiteral("WMA")', dialog_text)
        self.assertNotIn('QStringLiteral("VWMA")', dialog_text)

    def test_cpp_does_not_expose_native_only_signal_feed_option(self):
        dashboard_text = _read(CPP_SRC / "TradingBotWindow.dashboard_ui.cpp")
        runtime_text = _read(CPP_SRC / "TradingBotWindow.dashboard_runtime.cpp")
        lifecycle_text = _read(CPP_SRC / "TradingBotWindow.dashboard_runtime_lifecycle.cpp")
        shared_text = _read(CPP_SRC / "TradingBotWindow.dashboard_runtime_shared.cpp")

        self.assertNotIn("Signal Feed:", dashboard_text)
        self.assertNotIn("dashboardSignalFeedCombo_", dashboard_text + runtime_text + lifecycle_text)
        self.assertIn('BINANCE_WS_INDICATORS', shared_text)
        self.assertIn('BINANCE_INDICATOR_LIVE_DATA', shared_text)
        self.assertIn("pythonSourceUseWebSocketFeed", runtime_text + lifecycle_text)

    def test_rust_surfaces_expose_python_intervals_symbols_and_indicators(self):
        indicator_names = [definition.display_name for definition in INDICATOR_CATALOG]
        rust_summary_text = _read(RUST_CORE)
        tauri_text = _read(RUST_TAURI_HTML) + "\n" + _read(RUST_TAURI_GENERATED)

        self.assert_all_present(tauri_text, BACKTEST_INTERVAL_ORDER, "Rust Tauri intervals")
        self.assert_all_present(tauri_text, DEFAULT_CHART_SYMBOLS, "Rust Tauri symbols")
        self.assert_all_present(tauri_text, indicator_names, "Rust Tauri indicators")
        self.assert_all_present(
            rust_summary_text,
            [
                "generated_python_parity::PYTHON_BACKTEST_INTERVALS",
                "generated_python_parity::PYTHON_DEFAULT_CHART_SYMBOLS",
                "generated_python_parity::PYTHON_INDICATOR_CATALOG",
                "python_source_backtest_intervals",
                "python_source_default_chart_symbols",
                "python_source_indicator_catalog",
            ],
            "Rust core generated Python parity accessors",
        )

    def test_rust_surfaces_expose_python_connectors_loops_and_templates(self):
        connector_keys = [value for _, value in _connector_options()]
        connector_json_labels = [json.dumps(label)[1:-1] for label, _ in _connector_options()]
        loop_labels = [label for label, _ in DASHBOARD_LOOP_CHOICES]
        loop_values = [value for _, value in DASHBOARD_LOOP_CHOICES]
        template_keys = list(BACKTEST_TEMPLATE_DEFINITIONS.keys())
        template_labels = [str(template["label"]) for template in BACKTEST_TEMPLATE_DEFINITIONS.values()]
        template_json_labels = [json.dumps(label)[1:-1] for label in template_labels]

        tauri_text = _read(RUST_TAURI_HTML) + "\n" + _read(RUST_TAURI_GENERATED)
        rust_summary_text = _read(RUST_CORE)

        self.assert_all_present(tauri_text, connector_keys, "Rust Tauri connector keys")
        self.assertNotIn("binance-connector-python", tauri_text)
        self.assert_all_present(tauri_text, loop_values, "Rust Tauri loop values")
        self.assert_all_present(tauri_text, template_keys, "Rust Tauri template keys")

        for context, text, connector_labels, template_label_values in (
            ("tauri", tauri_text, connector_json_labels, template_json_labels),
        ):
            with self.subTest(context=context):
                self.assert_all_present(text, connector_labels, f"Rust {context} connector labels")
                self.assert_all_present(text, loop_labels, f"Rust {context} loop labels")
                self.assert_all_present(text, template_label_values, f"Rust {context} template labels")
        self.assert_all_present(
            rust_summary_text,
            [
                "generated_python_parity::PYTHON_CONNECTOR_OPTIONS",
                "generated_python_parity::PYTHON_DASHBOARD_LOOP_CHOICES",
                "generated_python_parity::PYTHON_BACKTEST_TEMPLATES",
                "python_source_connector_options",
                "python_source_dashboard_loop_choices",
                "python_source_backtest_templates",
                "Connector: Python source parity options",
                "Loop Interval Override: Python source parity options",
                "Symbol Source: Python source parity options",
                "Template: Python source parity options",
            ],
            "Rust core generated Python parity option accessors",
        )

    def test_native_source_sync_audit_rejects_handwritten_python_owned_literals(self):
        guarded_consumers = {
            requirement.name: requirement
            for requirement in audit_native_source_sync._consumer_requirements()
            if requirement.forbidden_text
        }
        expected_python_owned_literal_consumers = {
            "rust_core_consumes_generated_contract",
            "cpp_support_consumes_generated_contract",
            "cpp_config_persistence_uses_python_source_options",
            "cpp_dashboard_uses_python_source_surface",
            "cpp_backtest_uses_python_source_surface",
            "tauri_browser_consumes_generated_contract",
        }
        expected_pipeline_guard_consumers = {
            "cpp_dashboard_runtime_uses_native_indicator_strategy_pipeline": (
                "if (!useRsi && !useStochRsi && !useWillr)",
            ),
        }
        expected_guarded_consumers = (
            expected_python_owned_literal_consumers | set(expected_pipeline_guard_consumers)
        )
        report = audit_native_source_sync.audit_native_source_sync()
        consumers_by_name = {item["name"]: item for item in report["consumers"]}

        self.assertEqual(expected_guarded_consumers, set(guarded_consumers))
        for consumer_name in expected_guarded_consumers:
            with self.subTest(consumer=consumer_name):
                expected_forbidden_text = (
                    audit_native_source_sync.PYTHON_OWNED_OPTION_VALUE_FRAGMENTS
                    if consumer_name in expected_python_owned_literal_consumers
                    else expected_pipeline_guard_consumers[consumer_name]
                )
                self.assertEqual(
                    expected_forbidden_text,
                    guarded_consumers[consumer_name].forbidden_text,
                )
                self.assertTrue(consumers_by_name[consumer_name]["ok"], consumers_by_name[consumer_name])
                self.assertEqual([], consumers_by_name[consumer_name]["forbidden_text"])

    def test_native_backtest_runtimes_normalize_python_owned_choices(self):
        cpp_runtime = _read(CPP_SRC / "NativeBacktestRuntime.cpp")
        cpp_batch_runtime = _read(CPP_SRC / "NativeBacktestBatchRuntime.cpp")
        cpp_choice_helper = _read(CPP_SRC / "NativePythonParityChoices.h")
        rust_runtime = _read(RUST_CORE_SRC / "backtest_runtime.rs")
        rust_batch_runtime = _read(RUST_CORE_SRC / "backtest_batch_runtime.rs")
        cpp_strategy_runtime = _read(CPP_SRC / "NativeStrategyRuntime.cpp")
        rust_strategy_runtime = _read(RUST_CORE_SRC / "strategy_runtime.rs")

        self.assertIn('#include "NativePythonParityChoices.h"', cpp_runtime)
        self.assertIn('#include "NativePythonParityChoices.h"', cpp_batch_runtime)
        self.assertIn("canonicalConfigChoice", cpp_choice_helper)
        self.assertIn("normalize_config_choice", rust_runtime)
        self.assertNotIn('QStringLiteral("percentage")', cpp_strategy_runtime)
        self.assertNotIn('"percentage" =>', rust_strategy_runtime)

        native_runtime_text = "\n".join(
            [cpp_runtime, cpp_batch_runtime, rust_runtime, rust_batch_runtime]
        )
        for generated_choice in (
            "LogicConfigChoices",
            "SideConfigChoices",
            "MddLogicConfigChoices",
            "StopLossModeConfigChoices",
            "StopLossScopeConfigChoices",
            "OptimizerModeConfigChoices",
            "OptimizerMetricConfigChoices",
            "ScanScopeConfigChoices",
            "PositionPctUnitsConfigChoices",
        ):
            with self.subTest(generated_choice=generated_choice):
                self.assertIn(
                    f"Python{generated_choice}",
                    native_runtime_text,
                    f"native backtest runtimes must consume generated Python {generated_choice}",
                )


if __name__ == "__main__":
    unittest.main()
