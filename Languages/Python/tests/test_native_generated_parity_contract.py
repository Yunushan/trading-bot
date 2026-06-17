from __future__ import annotations

import json
import sys
import unittest
from pathlib import Path


PYTHON_ROOT = Path(__file__).resolve().parents[1]
REPO_ROOT = PYTHON_ROOT.parents[1]
if str(PYTHON_ROOT) not in sys.path:
    sys.path.insert(0, str(PYTHON_ROOT))

from app.native_parity import (  # noqa: E402
    NATIVE_PARITY_DOMAINS,
    native_python_source_contract_hash,
    native_python_source_contract_summary,
)
from app.service.api_contract import (  # noqa: E402
    SERVICE_API_ROUTE_METHODS,
    SERVICE_API_ROUTE_PATHS,
    SERVICE_API_ROUTE_SUFFIXES,
)
from tools.generate_native_parity_contracts import (  # noqa: E402
    CPP_OUTPUT,
    RUST_OUTPUT,
    TAURI_BROWSER_OUTPUT,
    _rust_string,
    render_cpp_header,
    render_rust_module,
    render_tauri_browser_contract,
)


def _read(path: Path) -> str:
    return path.read_text(encoding="utf-8")


class NativeGeneratedParityContractTests(unittest.TestCase):
    maxDiff = None

    def test_generated_native_contracts_are_in_sync_with_python_source(self):
        self.assertEqual(render_rust_module(), _read(RUST_OUTPUT))
        self.assertEqual(render_cpp_header(), _read(CPP_OUTPUT))
        self.assertEqual(render_tauri_browser_contract(), _read(TAURI_BROWSER_OUTPUT))

    def test_generated_contract_exposes_python_source_boundaries(self):
        summary = native_python_source_contract_summary()
        domain_keys = [domain.key for domain in NATIVE_PARITY_DOMAINS]

        self.assertEqual(domain_keys, summary["domain_keys"])
        self.assertFalse(summary["cpp_full_parity"])
        self.assertFalse(summary["rust_full_parity"])
        self.assertEqual(12, len(summary["domain_keys"]))
        self.assertIn("service_api_contract", summary["domain_keys"])
        self.assertIn("backtest_engine", summary["domain_keys"])
        self.assertIn("order_execution_and_risk", summary["domain_keys"])

    def test_rust_and_cpp_consume_generated_python_contracts(self):
        rust_core = _read(REPO_ROOT / "experiments" / "rust-shells" / "crates" / "core" / "src" / "lib.rs")
        cpp_support_header = _read(REPO_ROOT / "experiments" / "native-cpp" / "src" / "TradingBotWindowSupport.h")
        cpp_support_source = _read(REPO_ROOT / "experiments" / "native-cpp" / "src" / "TradingBotWindowSupport.cpp")
        tauri_html = _read(REPO_ROOT / "experiments" / "rust-shells" / "apps" / "tauri-desktop" / "ui" / "index.html")
        cmake = _read(REPO_ROOT / "experiments" / "native-cpp" / "CMakeLists.txt")

        self.assertIn("pub mod generated_python_parity", rust_core)
        self.assertIn("PythonParityDomain as NativePythonAppParityDomain", rust_core)
        self.assertIn("PythonServiceRoute as ServiceApiRoute", rust_core)
        self.assertIn("python_source_contract_hash", rust_core)
        self.assertIn("generated_python_parity::PYTHON_PARITY_DOMAINS", rust_core)
        self.assertIn("generated_python_parity::PYTHON_SERVICE_ROUTES", rust_core)
        self.assertIn("python_source_backtest_run_request_fields", rust_core)
        self.assertIn("python_source_indicator_keys", rust_core)
        self.assertIn("python_source_indicator_catalog", rust_core)
        self.assertIn("python_source_llm_provider_keys", rust_core)
        self.assertIn("python_source_connector_keys", rust_core)
        self.assertIn("python_source_backtest_intervals", rust_core)
        self.assertIn("python_source_tradingview_interval_map", rust_core)
        self.assertIn("python_source_default_chart_symbols", rust_core)
        self.assertIn("python_source_default_execution_symbols", rust_core)
        self.assertIn("python_source_default_backtest_symbols", rust_core)
        self.assertIn("python_source_dashboard_loop_choices", rust_core)
        self.assertIn("python_source_lead_trader_options", rust_core)
        self.assertIn("python_source_llm_use_for_options", rust_core)
        self.assertIn("python_source_dashboard_strategy_templates", rust_core)
        self.assertIn("python_source_backtest_templates", rust_core)
        self.assertIn("python_source_side_options", rust_core)
        self.assertIn("python_source_config_mode_options", rust_core)
        self.assertIn("python_source_theme_options", rust_core)
        self.assertIn("python_source_design_options", rust_core)
        self.assertIn("python_source_indicator_source_options", rust_core)
        self.assertIn("python_source_exchange_options", rust_core)
        self.assertIn("python_source_account_type_options", rust_core)
        self.assertIn("python_source_margin_mode_options", rust_core)
        self.assertIn("python_source_position_mode_options", rust_core)
        self.assertIn("python_source_assets_mode_options", rust_core)
        self.assertIn("python_source_time_in_force_options", rust_core)
        self.assertIn("python_source_signal_logic_options", rust_core)
        self.assertIn("python_source_mdd_logic_options", rust_core)
        self.assertIn("python_source_stop_loss_modes", rust_core)
        self.assertIn("python_source_chart_view_options", rust_core)
        self.assertIn("python_source_positions_view_options", rust_core)
        self.assertIn('include "generated/PythonParityContract.h"', cpp_support_source)
        self.assertIn("pythonSourceParityContractHash", cpp_support_header)
        self.assertIn("pythonSourceParityDomainTitle", cpp_support_header)
        self.assertIn("pythonSourceParityDomainCppStatus", cpp_support_source)
        self.assertIn("pythonSourceParityDomainRustStatus", cpp_support_source)
        self.assertIn("PythonParityContract::kPythonParityDomains", cpp_support_source)
        self.assertIn("pythonSourceServiceRoutePath", cpp_support_header)
        self.assertIn("pythonSourceServiceRouteMethods", cpp_support_source)
        self.assertIn("pythonSourceBacktestRunRequestFields", cpp_support_header)
        self.assertIn("pythonSourceIndicatorKeys", cpp_support_source)
        self.assertIn("pythonSourceIndicatorDisplayNames", cpp_support_header)
        self.assertIn("pythonSourceDefaultEnabledIndicatorKeys", cpp_support_source)
        self.assertIn("pythonSourceLlmProviderKeys", cpp_support_source)
        self.assertIn("pythonSourceLlmProviderLabels", cpp_support_header)
        self.assertIn("pythonSourceLlmProviderDefaultModels", cpp_support_source)
        self.assertIn("pythonSourceConnectorKeys", cpp_support_source)
        self.assertIn("pythonSourceConnectorLabels", cpp_support_header)
        self.assertIn("pythonSourceBacktestIntervals", cpp_support_source)
        self.assertIn("pythonSourceDefaultChartSymbols", cpp_support_header)
        self.assertIn("pythonSourceDefaultExecutionSymbols", cpp_support_source)
        self.assertIn("pythonSourceDefaultBacktestSymbols", cpp_support_source)
        self.assertIn("pythonSourceDashboardLoopChoiceLabels", cpp_support_header)
        self.assertIn("pythonSourceLeadTraderOptionLabels", cpp_support_source)
        self.assertIn("pythonSourceLlmUseForOptionLabels", cpp_support_source)
        self.assertIn("pythonSourceDashboardStrategyTemplateKeys", cpp_support_source)
        self.assertIn("pythonSourceBacktestTemplateKeys", cpp_support_source)
        self.assertIn("pythonSourceSideOptionLabels", cpp_support_source)
        self.assertIn("pythonSourceConfigModeOptionLabels", cpp_support_source)
        self.assertIn("pythonSourceThemeOptionLabels", cpp_support_source)
        self.assertIn("pythonSourceDesignOptionLabels", cpp_support_source)
        self.assertIn("pythonSourceIndicatorSourceOptionLabels", cpp_support_source)
        self.assertIn("pythonSourceExchangeOptionLabels", cpp_support_source)
        self.assertIn("pythonSourceAccountTypeOptionLabels", cpp_support_source)
        self.assertIn("pythonSourceMarginModeOptionLabels", cpp_support_source)
        self.assertIn("pythonSourcePositionModeOptionLabels", cpp_support_source)
        self.assertIn("pythonSourceAssetsModeOptionLabels", cpp_support_source)
        self.assertIn("pythonSourceTimeInForceOptionLabels", cpp_support_source)
        self.assertIn("pythonSourceSignalLogicOptionLabels", cpp_support_source)
        self.assertIn("pythonSourceMddLogicOptionLabels", cpp_support_source)
        self.assertIn("pythonSourceStopLossModeLabels", cpp_support_source)
        self.assertIn("pythonSourceChartViewOptionLabels", cpp_support_source)
        self.assertIn("pythonSourcePositionsViewOptionLabels", cpp_support_source)
        self.assertIn("PythonParityContract::kPythonServiceRoutes", cpp_support_source)
        self.assertIn("PythonParityContract::kPythonIndicatorCatalog", cpp_support_source)
        self.assertIn("PythonParityContract::kPythonLlmProviders", cpp_support_source)
        self.assertIn("PythonParityContract::kPythonConnectorOptions", cpp_support_source)
        self.assertIn("PythonParityContract::kPythonBacktestTemplates", cpp_support_source)
        self.assertIn('src="generated-python-parity.js"', tauri_html)
        self.assertIn("window.PythonParityContract", _read(TAURI_BROWSER_OUTPUT))
        self.assertIn("pythonParityContract.indicatorCatalog", tauri_html)
        self.assertIn("pythonParityContract.llmProviders", tauri_html)
        self.assertIn("pythonParityContract.connectorOptions", tauri_html)
        self.assertIn("pythonParityContract.defaultExecution", tauri_html)
        self.assertIn("pythonParityContract.defaultBacktest", tauri_html)
        self.assertIn("pythonParityContract.defaultChartSymbols", tauri_html)
        self.assertIn("pythonParityContract.dashboardLoopChoices", tauri_html)
        self.assertIn("pythonParityContract.leadTraderOptions", tauri_html)
        self.assertIn("pythonParityContract.llmUseForOptions", tauri_html)
        self.assertIn("pythonParityContract.dashboardStrategyTemplates", tauri_html)
        self.assertIn("pythonParityContract.backtestTemplates", tauri_html)
        self.assertIn("pythonParityContract.tradingviewIntervalMap", tauri_html)
        self.assertIn("pythonParityContract.configModeOptions", tauri_html)
        self.assertIn("pythonParityContract.themeOptions", tauri_html)
        self.assertIn("pythonParityContract.designOptions", tauri_html)
        self.assertIn("pythonParityContract.indicatorSourceOptions", tauri_html)
        self.assertIn("pythonParityContract.exchangeOptions", tauri_html)
        self.assertIn("pythonParityContract.accountTypeOptions", tauri_html)
        self.assertIn("pythonParityContract.marginModeOptions", tauri_html)
        self.assertIn("pythonParityContract.positionModeOptions", tauri_html)
        self.assertIn("pythonParityContract.assetsModeOptions", tauri_html)
        self.assertIn("pythonParityContract.timeInForceOptions", tauri_html)
        self.assertIn("pythonParityContract.signalLogicOptions", tauri_html)
        self.assertIn("pythonParityContract.chartViewOptions", tauri_html)
        self.assertIn("pythonParityContract.positionsViewOptions", tauri_html)
        self.assertNotIn("const indicatorCatalog = [", tauri_html)
        self.assertNotIn("const chartDefaultSymbols = [", tauri_html)
        self.assertNotIn("const chartIntervalMap = {", tauri_html)
        self.assertNotIn("const modelSuggestions = {", tauri_html)
        self.assertIn("pythonParityContract.serviceRoutePaths", tauri_html)
        self.assertIn("serviceRouteSupportsMethod", tauri_html)
        self.assertIn("src/generated/PythonParityContract.h", cmake)

    def test_contract_hash_is_embedded_in_native_destinations(self):
        contract_hash = native_python_source_contract_hash()

        self.assertIn(contract_hash, _read(RUST_OUTPUT))
        self.assertIn(contract_hash, _read(CPP_OUTPUT))
        self.assertIn(contract_hash, _read(TAURI_BROWSER_OUTPUT))

    def test_generated_parity_domains_match_python_source_contract(self):
        summary = native_python_source_contract_summary()
        source_domains = {
            domain.key: domain
            for domain in NATIVE_PARITY_DOMAINS
        }
        summary_domains = {
            str(domain["key"]): domain
            for domain in summary["domains"]
        }

        self.assertEqual(list(source_domains), list(summary_domains))
        rust_generated = _read(RUST_OUTPUT)
        cpp_generated = _read(CPP_OUTPUT)
        self.assertIn("pub struct PythonParityDomain", rust_generated)
        self.assertIn("pub const PYTHON_PARITY_DOMAINS", rust_generated)
        self.assertIn("struct PythonParityDomain", cpp_generated)
        self.assertIn("kPythonParityDomains", cpp_generated)

        for domain_key, source_domain in source_domains.items():
            summary_domain = summary_domains[domain_key]
            self.assertEqual(source_domain.title, summary_domain["title"])
            self.assertEqual(source_domain.python_surface, summary_domain["python_surface"])
            self.assertEqual(
                list(source_domain.cpp_required_before_full_parity),
                list(summary_domain["cpp_required_before_full_parity"]),
            )
            self.assertEqual(
                list(source_domain.rust_required_before_full_parity),
                list(summary_domain["rust_required_before_full_parity"]),
            )
            self.assertIn(f'key: "{domain_key}"', rust_generated)
            self.assertIn(f'PythonParityDomain{{"{domain_key}",', cpp_generated)

    def test_generated_service_routes_match_python_source_contract(self):
        summary = native_python_source_contract_summary()
        service_routes = {
            str(route["name"]): route
            for route in summary["service_routes"]
        }

        self.assertEqual(list(SERVICE_API_ROUTE_SUFFIXES), list(service_routes))
        for route_name in SERVICE_API_ROUTE_SUFFIXES:
            self.assertEqual(SERVICE_API_ROUTE_PATHS[route_name], service_routes[route_name]["path"])
            self.assertEqual(
                list(SERVICE_API_ROUTE_METHODS[route_name]),
                service_routes[route_name]["methods"],
            )

        rust_generated = _read(RUST_OUTPUT)
        cpp_generated = _read(CPP_OUTPUT)
        tauri_generated = _read(TAURI_BROWSER_OUTPUT)
        self.assertIn("pub struct PythonServiceRoute", rust_generated)
        self.assertIn("pub const PYTHON_SERVICE_ROUTES", rust_generated)
        self.assertIn("struct PythonServiceRoute", cpp_generated)
        self.assertIn("kPythonServiceRoutes", cpp_generated)
        self.assertIn('"serviceRoutePaths"', tauri_generated)
        self.assertIn('"serviceRouteMethods"', tauri_generated)

        for route_name in SERVICE_API_ROUTE_SUFFIXES:
            route_path = SERVICE_API_ROUTE_PATHS[route_name]
            rust_methods = ", ".join(
                f'"{method}"'
                for method in SERVICE_API_ROUTE_METHODS[route_name]
            )
            cpp_methods = ",".join(SERVICE_API_ROUTE_METHODS[route_name])

            self.assertIn(f'name: "{route_name}"', rust_generated)
            self.assertIn(f'path: "{route_path}"', rust_generated)
            self.assertIn(f"methods: &[{rust_methods}]", rust_generated)
            self.assertIn(
                f'PythonServiceRoute{{"{route_name}", "{route_path}", "{cpp_methods}"}}',
                cpp_generated,
            )
            self.assertIn(f'"{route_name}": "{route_path}"', tauri_generated)
            for method in SERVICE_API_ROUTE_METHODS[route_name]:
                self.assertIn(f'"{method}"', tauri_generated)

    def test_generated_indicator_catalog_matches_python_source_contract(self):
        summary = native_python_source_contract_summary()
        indicators = list(summary["indicators"])
        indicator_keys = [str(indicator["key"]) for indicator in indicators]

        self.assertEqual(list(summary["indicator_keys"]), indicator_keys)
        self.assertTrue(any(bool(indicator["default_enabled"]) for indicator in indicators))

        rust_generated = _read(RUST_OUTPUT)
        cpp_generated = _read(CPP_OUTPUT)
        tauri_generated = _read(TAURI_BROWSER_OUTPUT)
        self.assertIn("pub struct PythonIndicator", rust_generated)
        self.assertIn("pub const PYTHON_INDICATOR_CATALOG", rust_generated)
        self.assertIn("struct PythonIndicator", cpp_generated)
        self.assertIn("kPythonIndicatorCatalog", cpp_generated)
        self.assertIn('"indicatorCatalog"', tauri_generated)

        for indicator in indicators:
            key = str(indicator["key"])
            display_name = str(indicator["display_name"])
            rust_enabled = str(bool(indicator["default_enabled"])).lower()
            cpp_enabled = rust_enabled
            js_key = json.dumps(key)
            js_name = json.dumps(display_name)

            self.assertIn(f"key: {js_key}", rust_generated)
            self.assertIn(f"display_name: {js_name}", rust_generated)
            self.assertIn(f"default_enabled: {rust_enabled}", rust_generated)
            self.assertIn(
                f"PythonIndicator{{{js_key}, {js_name}, {cpp_enabled}}}",
                cpp_generated,
            )
            self.assertIn(f'"key": {js_key}', tauri_generated)
            self.assertIn(f'"name": {js_name}', tauri_generated)

    def test_generated_connector_and_llm_catalogs_match_python_source_contract(self):
        summary = native_python_source_contract_summary()
        rust_generated = _read(RUST_OUTPUT)
        cpp_generated = _read(CPP_OUTPUT)
        tauri_generated = _read(TAURI_BROWSER_OUTPUT)

        self.assertIn("pub struct PythonConnectorOption", rust_generated)
        self.assertIn("pub const PYTHON_CONNECTOR_OPTIONS", rust_generated)
        self.assertIn("struct PythonConnectorOption", cpp_generated)
        self.assertIn("kPythonConnectorOptions", cpp_generated)
        self.assertIn('"connectorOptions"', tauri_generated)
        self.assertIn("pub struct PythonLlmProvider", rust_generated)
        self.assertIn("pub const PYTHON_LLM_PROVIDERS", rust_generated)
        self.assertIn("struct PythonLlmProvider", cpp_generated)
        self.assertIn("kPythonLlmProviders", cpp_generated)
        self.assertIn('"llmProviders"', tauri_generated)

        for connector in summary["connectors"]:
            key = json.dumps(str(connector["key"]))
            label = json.dumps(str(connector["label"]))
            rust_label = _rust_string(str(connector["label"]))
            self.assertIn(f"key: {key}", rust_generated)
            self.assertIn(f"label: {rust_label}", rust_generated)
            self.assertIn(f"PythonConnectorOption{{{key}, {label}}}", cpp_generated)
            self.assertIn(f'"key": {key}', tauri_generated)
            self.assertIn(f'"label": {label}', tauri_generated)

        for provider in summary["llm_providers"]:
            key = json.dumps(str(provider["key"]))
            label = json.dumps(str(provider["label"]))
            default_model = json.dumps(str(provider["default_model"]))
            api_key_env = json.dumps(str(provider["api_key_env"]))
            self.assertIn(f"key: {key}", rust_generated)
            self.assertIn(f"label: {label}", rust_generated)
            self.assertIn(f"default_model: {default_model}", rust_generated)
            self.assertIn(f"api_key_env: {api_key_env}", rust_generated)
            self.assertIn(f'"key": {key}', tauri_generated)
            self.assertIn(f'"label": {label}', tauri_generated)
            self.assertIn(f'"default_model": {default_model}', tauri_generated)
            self.assertIn(f'"api_key_env": {api_key_env}', tauri_generated)

    def test_generated_runtime_option_catalogs_match_python_source_contract(self):
        summary = native_python_source_contract_summary()
        rust_generated = _read(RUST_OUTPUT)
        cpp_generated = _read(CPP_OUTPUT)
        tauri_generated = _read(TAURI_BROWSER_OUTPUT)

        simple_arrays = {
            "default_chart_symbols": (
                "PYTHON_DEFAULT_CHART_SYMBOLS",
                "kPythonDefaultChartSymbols",
                "defaultChartSymbols",
            ),
            "default_execution_symbols": (
                "PYTHON_DEFAULT_EXECUTION_SYMBOLS",
                "kPythonDefaultExecutionSymbols",
                "defaultExecutionSymbols",
            ),
            "default_execution_intervals": (
                "PYTHON_DEFAULT_EXECUTION_INTERVALS",
                "kPythonDefaultExecutionIntervals",
                "defaultExecutionIntervals",
            ),
            "default_backtest_symbols": (
                "PYTHON_DEFAULT_BACKTEST_SYMBOLS",
                "kPythonDefaultBacktestSymbols",
                "defaultBacktestSymbols",
            ),
            "default_backtest_intervals": (
                "PYTHON_DEFAULT_BACKTEST_INTERVALS",
                "kPythonDefaultBacktestIntervals",
                "defaultBacktestIntervals",
            ),
            "chart_market_options": (
                "PYTHON_CHART_MARKET_OPTIONS",
                "kPythonChartMarketOptions",
                "chartMarketOptions",
            ),
            "account_mode_options": (
                "PYTHON_ACCOUNT_MODE_OPTIONS",
                "kPythonAccountModeOptions",
                "accountModeOptions",
            ),
        }
        for summary_key, (rust_name, cpp_name, js_name) in simple_arrays.items():
            with self.subTest(summary_key=summary_key):
                self.assertIn(rust_name, rust_generated)
                self.assertIn(cpp_name, cpp_generated)
                self.assertIn(f'"{js_name}"', tauri_generated)
                for value in summary[summary_key]:
                    encoded = json.dumps(str(value))
                    self.assertIn(encoded, rust_generated)
                    self.assertIn(encoded, cpp_generated)
                    self.assertIn(encoded, tauri_generated)

        option_groups = {
            "dashboard_loop_choices": (
                "PYTHON_DASHBOARD_LOOP_CHOICES",
                "kPythonDashboardLoopChoices",
                "dashboardLoopChoices",
            ),
            "lead_trader_options": (
                "PYTHON_LEAD_TRADER_OPTIONS",
                "kPythonLeadTraderOptions",
                "leadTraderOptions",
            ),
            "llm_use_for_options": (
                "PYTHON_LLM_USE_FOR_OPTIONS",
                "kPythonLlmUseForOptions",
                "llmUseForOptions",
            ),
            "dashboard_strategy_templates": (
                "PYTHON_DASHBOARD_STRATEGY_TEMPLATES",
                "kPythonDashboardStrategyTemplates",
                "dashboardStrategyTemplates",
            ),
            "backtest_templates": (
                "PYTHON_BACKTEST_TEMPLATES",
                "kPythonBacktestTemplates",
                "backtestTemplates",
            ),
            "side_options": (
                "PYTHON_SIDE_OPTIONS",
                "kPythonSideOptions",
                "sideOptions",
            ),
            "config_mode_options": (
                "PYTHON_CONFIG_MODE_OPTIONS",
                "kPythonConfigModeOptions",
                "configModeOptions",
            ),
            "theme_options": (
                "PYTHON_THEME_OPTIONS",
                "kPythonThemeOptions",
                "themeOptions",
            ),
            "design_options": (
                "PYTHON_DESIGN_OPTIONS",
                "kPythonDesignOptions",
                "designOptions",
            ),
            "indicator_source_options": (
                "PYTHON_INDICATOR_SOURCE_OPTIONS",
                "kPythonIndicatorSourceOptions",
                "indicatorSourceOptions",
            ),
            "exchange_options": (
                "PYTHON_EXCHANGE_OPTIONS",
                "kPythonExchangeOptions",
                "exchangeOptions",
            ),
            "account_type_options": (
                "PYTHON_ACCOUNT_TYPE_OPTIONS",
                "kPythonAccountTypeOptions",
                "accountTypeOptions",
            ),
            "margin_mode_options": (
                "PYTHON_MARGIN_MODE_OPTIONS",
                "kPythonMarginModeOptions",
                "marginModeOptions",
            ),
            "position_mode_options": (
                "PYTHON_POSITION_MODE_OPTIONS",
                "kPythonPositionModeOptions",
                "positionModeOptions",
            ),
            "assets_mode_options": (
                "PYTHON_ASSETS_MODE_OPTIONS",
                "kPythonAssetsModeOptions",
                "assetsModeOptions",
            ),
            "order_type_options": (
                "PYTHON_ORDER_TYPE_OPTIONS",
                "kPythonOrderTypeOptions",
                "orderTypeOptions",
            ),
            "time_in_force_options": (
                "PYTHON_TIME_IN_FORCE_OPTIONS",
                "kPythonTimeInForceOptions",
                "timeInForceOptions",
            ),
            "signal_logic_options": (
                "PYTHON_SIGNAL_LOGIC_OPTIONS",
                "kPythonSignalLogicOptions",
                "signalLogicOptions",
            ),
            "mdd_logic_options": (
                "PYTHON_MDD_LOGIC_OPTIONS",
                "kPythonMddLogicOptions",
                "mddLogicOptions",
            ),
            "stop_loss_modes": (
                "PYTHON_STOP_LOSS_MODES",
                "kPythonStopLossModes",
                "stopLossModes",
            ),
            "stop_loss_scopes": (
                "PYTHON_STOP_LOSS_SCOPES",
                "kPythonStopLossScopes",
                "stopLossScopes",
            ),
            "scan_scope_options": (
                "PYTHON_SCAN_SCOPE_OPTIONS",
                "kPythonScanScopeOptions",
                "scanScopeOptions",
            ),
            "optimizer_mode_options": (
                "PYTHON_OPTIMIZER_MODE_OPTIONS",
                "kPythonOptimizerModeOptions",
                "optimizerModeOptions",
            ),
            "optimizer_metric_options": (
                "PYTHON_OPTIMIZER_METRIC_OPTIONS",
                "kPythonOptimizerMetricOptions",
                "optimizerMetricOptions",
            ),
            "backtest_execution_backend_options": (
                "PYTHON_BACKTEST_EXECUTION_BACKEND_OPTIONS",
                "kPythonBacktestExecutionBackendOptions",
                "backtestExecutionBackendOptions",
            ),
            "chart_view_options": (
                "PYTHON_CHART_VIEW_OPTIONS",
                "kPythonChartViewOptions",
                "chartViewOptions",
            ),
            "positions_view_options": (
                "PYTHON_POSITIONS_VIEW_OPTIONS",
                "kPythonPositionsViewOptions",
                "positionsViewOptions",
            ),
        }
        self.assertIn("pub struct PythonUiOption", rust_generated)
        self.assertIn("struct PythonUiOption", cpp_generated)
        self.assertIn("disabled: bool", rust_generated)
        self.assertIn("bool disabled", cpp_generated)
        for summary_key, (rust_name, cpp_name, js_name) in option_groups.items():
            with self.subTest(summary_key=summary_key):
                self.assertIn(rust_name, rust_generated)
                self.assertIn(cpp_name, cpp_generated)
                self.assertIn(f'"{js_name}"', tauri_generated)
                for option in summary[summary_key]:
                    raw_key = option["key"] if "key" in option else option.get("value", "")
                    key = json.dumps(str(raw_key))
                    label = json.dumps(str(option["label"]))
                    disabled = str(bool(option.get("disabled", False))).lower()
                    rust_label = _rust_string(str(option["label"]))
                    self.assertIn(f"key: {key}", rust_generated)
                    self.assertIn(f"label: {rust_label}", rust_generated)
                    self.assertIn(f"disabled: {disabled}", rust_generated)
                    self.assertIn(f"PythonUiOption{{{key}, {label}, {disabled}}}", cpp_generated)
                    self.assertIn(f'"key": {key}', tauri_generated)
                    self.assertIn(f'"label": {label}', tauri_generated)
                    if "disabled" in option:
                        self.assertIn(f'"disabled": {disabled}', tauri_generated)

        self.assertIn("pub struct PythonTradingViewInterval", rust_generated)
        self.assertIn("kPythonTradingViewIntervalMap", cpp_generated)
        self.assertIn('"tradingviewIntervalMap"', tauri_generated)
        for interval, code in summary["tradingview_interval_map"].items():
            interval_json = json.dumps(str(interval))
            code_json = json.dumps(str(code))
            self.assertIn(f"interval: {interval_json}", rust_generated)
            self.assertIn(f"code: {code_json}", rust_generated)
            self.assertIn(f"PythonTradingViewInterval{{{interval_json}, {code_json}}}", cpp_generated)
            self.assertIn(f'{interval_json}: {code_json}', tauri_generated)

        self.assertIn('"defaultExecution"', tauri_generated)
        self.assertIn('"defaultBacktest"', tauri_generated)
        for key, value in summary["default_execution"].items():
            if isinstance(value, str):
                self.assertIn(f'"{key}": {json.dumps(value)}', tauri_generated)
        for key, value in summary["default_backtest"].items():
            if isinstance(value, str):
                self.assertIn(f'"{key}": {json.dumps(value)}', tauri_generated)


if __name__ == "__main__":
    unittest.main()
