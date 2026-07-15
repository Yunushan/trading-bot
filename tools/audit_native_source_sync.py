from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
from dataclasses import dataclass
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
PYTHON_ROOT = REPO_ROOT / "Languages" / "Python"
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))
if str(PYTHON_ROOT) not in sys.path:
    sys.path.insert(0, str(PYTHON_ROOT))

from app.native_parity import native_python_source_contract_hash  # noqa: E402
from app.service.api_contract import SERVICE_API_ROUTE_PATHS  # noqa: E402
from tools.generate_native_parity_contracts import (  # noqa: E402
    CPP_INDICATOR_REFERENCE_OUTPUT,
    CPP_OUTPUT,
    RUST_INDICATOR_REFERENCE_OUTPUT,
    RUST_OUTPUT,
    TAURI_BROWSER_OUTPUT,
    render_cpp_indicator_reference_header,
    render_cpp_header,
    render_rust_indicator_reference_module,
    render_rust_module,
    render_tauri_browser_contract,
)


@dataclass(frozen=True, slots=True)
class GeneratedArtifact:
    name: str
    path: Path
    expected: str


@dataclass(frozen=True, slots=True)
class ConsumerRequirement:
    name: str
    path: Path
    required_text: tuple[str, ...]
    service_route_names: tuple[str, ...] = ()
    route_extractors: tuple[str, ...] = ()
    forbidden_text: tuple[str, ...] = ()


CPP_SERVICE_API_EXTRACTOR = "cpp_service_api"
TAURI_REQUEST_AND_REPORT_EXTRACTOR = "tauri_request_and_report"
CPP_SERVICE_API_ROUTE_RE = re.compile(
    r"TradingBotWindowSupport::serviceApiRequestJson\s*\(\s*"
    r"QStringLiteral\(\"[A-Z]+\"\)\s*,\s*QStringLiteral\(\"([a-z0-9_]+)\"\)",
    re.DOTALL,
)
CPP_ROUTED_ACTION_RE = re.compile(
    r"runLocalModelAction\s*\(\s*"
    r"QStringLiteral\(\"[^\"]+\"\)\s*,\s*QStringLiteral\(\"([a-z0-9_]+)\"\)",
    re.DOTALL,
)
TAURI_REQUEST_AND_REPORT_ROUTE_RE = re.compile(
    r"requestAndReport\s*\(\s*(?:\"[^\"]+\"|[A-Za-z_$][\w$]*)\s*,\s*\"([a-z0-9_]+)\"",
    re.DOTALL,
)
PYTHON_OWNED_OPTION_VALUE_FRAGMENTS = (
    "Provider: OpenAI / ChatGPT",
    "Model: gpt-5.5, gpt-5.4",
    "Connector: Binance SDK Derivatives Trading USD-S Futures",
    "Indicator Source: Binance spot, Binance futures",
    "Default symbols: BTCUSDT, ETHUSDT",
    "Default intervals: 1m, 3m",
    "Default intervals: 1m, 5m",
    "Loop Interval Override: 30 seconds",
    "Symbol Source: Futures, Spot",
    "Signal Logic: AND, OR, SEPARATE",
    "MDD Logic: Per Trade MDD",
    "Side: Buy (Long), Sell (Short)",
    "Template: Enable, First 50 Highest Volume",
)
REQUIRED_GENERATED_ARTIFACT_NAMES = (
    "rust_core_generated_contract",
    "rust_indicator_reference_fixture",
    "cpp_generated_contract",
    "cpp_indicator_reference_fixture",
    "tauri_browser_generated_contract",
)
REQUIRED_CONSUMER_SURFACE_NAMES = (
    "rust_core_consumes_generated_contract",
    "rust_strategy_runtime_uses_python_source_options",
    "rust_config_persistence_uses_python_source_options",
    "python_order_guard_implements_behavior_contract",
    "rust_order_guard_uses_python_behavior_contract",
    "cpp_support_consumes_generated_contract",
    "cpp_support_exposes_generated_contract",
    "cpp_config_persistence_uses_python_source_options",
    "cpp_dashboard_uses_python_source_surface",
    "cpp_backtest_uses_python_source_surface",
    "cpp_backtest_service_api_uses_python_source_routes",
    "cpp_dashboard_llm_service_api_uses_python_source_routes",
    "cpp_config_service_api_uses_python_source_routes",
    "cpp_chart_uses_python_source_surface",
    "cpp_native_chart_heatmap_uses_python_source_surface",
    "cpp_positions_uses_python_source_surface",
    "cpp_account_symbols_use_python_source_fallbacks",
    "cpp_native_exchange_connectors_use_python_source_connectors",
    "cpp_native_strategy_runtime_uses_python_source_options",
    "cpp_native_indicator_runtime_uses_python_reference_fixture",
    "cpp_dashboard_runtime_uses_native_indicator_strategy_pipeline",
    "cpp_order_guard_uses_python_behavior_contract",
    "tauri_browser_consumes_generated_contract",
    "tauri_browser_service_api_uses_python_source_routes",
    "tauri_native_runtime_preview_backend",
    "tauri_native_runtime_preview_browser_bridge",
    "tauri_native_runtime_controller_backend",
    "tauri_native_runtime_controller_browser_bridge",
)


def _rel(path: Path) -> str:
    return path.relative_to(REPO_ROOT).as_posix()


def _read(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def _sha256(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _ordered_unique(values: list[str] | tuple[str, ...]) -> list[str]:
    seen: set[str] = set()
    unique: list[str] = []
    for value in values:
        if value not in seen:
            seen.add(value)
            unique.append(value)
    return unique


def _duplicate_names(values: tuple[str, ...]) -> list[str]:
    seen: set[str] = set()
    duplicates: list[str] = []
    for value in values:
        if value in seen and value not in duplicates:
            duplicates.append(value)
        seen.add(value)
    return duplicates


def _name_contract_issues(label: str, required_names: tuple[str, ...], actual_names: tuple[str, ...]) -> list[str]:
    actual_name_set = set(actual_names)
    required_name_set = set(required_names)
    issues: list[str] = []
    missing = [name for name in required_names if name not in actual_name_set]
    unexpected = [name for name in actual_names if name not in required_name_set]
    duplicates = _duplicate_names(actual_names)
    if missing:
        issues.append(f"missing required {label}(s): {', '.join(missing)}")
    if unexpected:
        issues.append(f"unexpected {label}(s): {', '.join(unexpected)}")
    if duplicates:
        issues.append(f"duplicate {label}(s): {', '.join(duplicates)}")
    return issues


def _surface_contract(
    generated_artifacts: tuple[GeneratedArtifact, ...],
    consumers: tuple[ConsumerRequirement, ...],
) -> dict[str, object]:
    generated_artifact_names = tuple(artifact.name for artifact in generated_artifacts)
    consumer_surface_names = tuple(consumer.name for consumer in consumers)
    issues = [
        *_name_contract_issues(
            "generated artifact",
            REQUIRED_GENERATED_ARTIFACT_NAMES,
            generated_artifact_names,
        ),
        *_name_contract_issues(
            "consumer surface",
            REQUIRED_CONSUMER_SURFACE_NAMES,
            consumer_surface_names,
        ),
    ]
    return {
        "ok": not issues,
        "required_generated_artifact_names": list(REQUIRED_GENERATED_ARTIFACT_NAMES),
        "actual_generated_artifact_names": list(generated_artifact_names),
        "required_consumer_surface_names": list(REQUIRED_CONSUMER_SURFACE_NAMES),
        "actual_consumer_surface_names": list(consumer_surface_names),
        "issues": issues,
    }


def _extract_service_routes(text: str, extractors: tuple[str, ...]) -> tuple[list[str], list[str]]:
    route_names: list[str] = []
    unknown_extractors: list[str] = []
    for extractor in extractors:
        if extractor == CPP_SERVICE_API_EXTRACTOR:
            route_names.extend(CPP_SERVICE_API_ROUTE_RE.findall(text))
            route_names.extend(CPP_ROUTED_ACTION_RE.findall(text))
        elif extractor == TAURI_REQUEST_AND_REPORT_EXTRACTOR:
            route_names.extend(TAURI_REQUEST_AND_REPORT_ROUTE_RE.findall(text))
        else:
            unknown_extractors.append(extractor)
    return _ordered_unique(route_names), unknown_extractors


def _generated_artifacts() -> tuple[GeneratedArtifact, ...]:
    return (
        GeneratedArtifact("rust_core_generated_contract", RUST_OUTPUT, render_rust_module()),
        GeneratedArtifact(
            "rust_indicator_reference_fixture",
            RUST_INDICATOR_REFERENCE_OUTPUT,
            render_rust_indicator_reference_module(),
        ),
        GeneratedArtifact("cpp_generated_contract", CPP_OUTPUT, render_cpp_header()),
        GeneratedArtifact(
            "cpp_indicator_reference_fixture",
            CPP_INDICATOR_REFERENCE_OUTPUT,
            render_cpp_indicator_reference_header(),
        ),
        GeneratedArtifact("tauri_browser_generated_contract", TAURI_BROWSER_OUTPUT, render_tauri_browser_contract()),
    )


def _consumer_requirements() -> tuple[ConsumerRequirement, ...]:
    return (
        ConsumerRequirement(
            "rust_core_consumes_generated_contract",
            REPO_ROOT / "experiments" / "rust-shells" / "crates" / "core" / "src" / "lib.rs",
            (
                "pub mod generated_python_parity",
                "generated_python_parity::PYTHON_SOURCE_CONTRACT_HASH",
                "generated_python_parity::PYTHON_PARITY_DOMAINS",
                "generated_python_parity::PYTHON_SERVICE_ROUTES",
                "generated_python_parity::PYTHON_SERVICE_ROUTE_SCHEMAS",
                "generated_python_parity::PYTHON_INDICATOR_CATALOG",
                "generated_python_parity::PYTHON_LLM_PROVIDERS",
                "generated_python_parity::PYTHON_CONNECTOR_OPTIONS",
                "generated_python_parity::PYTHON_BACKTEST_INTERVALS",
                "python_source_indicator_catalog",
                "python_source_llm_provider_keys",
                "python_source_connector_keys",
                "python_source_backtest_templates",
                "python_source_dashboard_strategy_templates",
                "python_source_chart_view_options",
                "python_source_positions_view_options",
                "python_source_rust_contract_parity_ready",
                "python_source_rust_standalone_runtime_ready",
            ),
            forbidden_text=PYTHON_OWNED_OPTION_VALUE_FRAGMENTS,
        ),
        ConsumerRequirement(
            "rust_strategy_runtime_uses_python_source_options",
            REPO_ROOT / "experiments" / "rust-shells" / "crates" / "core" / "src" / "strategy_runtime.rs",
            (
                "PYTHON_ACCOUNT_MODE_OPTIONS",
                "PYTHON_ASSETS_MODE_OPTIONS",
                "PYTHON_SIDE_OPTIONS",
                "PYTHON_SIGNAL_LOGIC_OPTIONS",
                "PYTHON_STOP_LOSS_MODES",
                "PYTHON_STOP_LOSS_SCOPES",
                "PYTHON_INDICATOR_CATALOG",
                "normalize_python_ui_option_key",
                "normalize_python_ui_option_key_fuzzy",
                "normalize_python_string_option_fuzzy",
                "runtime_output_keys",
                "canonical_side",
                "normalize_account_mode",
                "normalize_assets_mode",
                "normalize_strategy_controls",
                "normalize_stop_loss",
            ),
        ),
        ConsumerRequirement(
            "rust_config_persistence_uses_python_source_options",
            REPO_ROOT / "experiments" / "rust-shells" / "crates" / "core" / "src" / "config_persistence.rs",
            (
                "PYTHON_ACCOUNT_MODE_OPTIONS",
                "PYTHON_ACCOUNT_TYPE_OPTIONS",
                "PYTHON_ASSETS_MODE_OPTIONS",
                "PYTHON_BACKTEST_EXECUTION_BACKEND_OPTIONS",
                "PYTHON_CHART_MARKET_OPTIONS",
                "PYTHON_CHART_VIEW_OPTIONS",
                "PYTHON_CONFIG_MODE_OPTIONS",
                "PYTHON_CONNECTOR_OPTIONS",
                "PYTHON_DESIGN_OPTIONS",
                "PYTHON_EXCHANGE_OPTIONS",
                "PYTHON_INDICATOR_SOURCE_OPTIONS",
                "PYTHON_LLM_PROVIDERS",
                "PYTHON_LLM_USE_FOR_OPTIONS",
                "PYTHON_MARGIN_MODE_OPTIONS",
                "PYTHON_MDD_LOGIC_OPTIONS",
                "PYTHON_OPTIMIZER_METRIC_OPTIONS",
                "PYTHON_OPTIMIZER_MODE_OPTIONS",
                "PYTHON_ORDER_TYPE_OPTIONS",
                "PYTHON_POSITION_MODE_OPTIONS",
                "PYTHON_SCAN_SCOPE_OPTIONS",
                "PYTHON_SIDE_OPTIONS",
                "PYTHON_SIGNAL_LOGIC_OPTIONS",
                "PYTHON_STOP_LOSS_MODES",
                "PYTHON_STOP_LOSS_SCOPES",
                "PYTHON_THEME_OPTIONS",
                "PYTHON_TIME_IN_FORCE_OPTIONS",
                "ChoiceList",
                "choice_value_from_text",
                "validate_choice",
                "validate_optional_choice",
                "normalize_stop_loss_value",
            ),
        ),
        ConsumerRequirement(
            "python_order_guard_implements_behavior_contract",
            REPO_ROOT
            / "Languages"
            / "Python"
            / "app"
            / "integrations"
            / "exchanges"
            / "binance"
            / "orders"
            / "order_submit_guard_runtime.py",
            (
                "ORDER_GUARD_BEHAVIOR",
                "_policy_applies_to_mode",
                "validate_exchange_filters_all_modes",
                "validate_connector_health_all_modes",
                "validate_audit_writable_all_modes",
            ),
        ),
        ConsumerRequirement(
            "rust_order_guard_uses_python_behavior_contract",
            REPO_ROOT / "experiments" / "rust-shells" / "crates" / "core" / "src" / "order_guard.rs",
            (
                "PYTHON_ORDER_GUARD_VALIDATE_EXCHANGE_FILTERS_ALL_MODES",
                "PYTHON_ORDER_GUARD_VALIDATE_CONNECTOR_HEALTH_ALL_MODES",
                "PYTHON_ORDER_GUARD_VALIDATE_AUDIT_WRITABLE_ALL_MODES",
            ),
        ),
        ConsumerRequirement(
            "cpp_support_consumes_generated_contract",
            REPO_ROOT / "experiments" / "native-cpp" / "src" / "TradingBotWindowSupport.cpp",
            (
                '#include "generated/PythonParityContract.h"',
                "PythonParityContract::kPythonSourceContractHash",
                "PythonParityContract::kPythonParityDomains",
                "PythonParityContract::kPythonServiceRoutes",
                "PythonParityContract::kPythonServiceRouteSchemas",
                "PythonParityContract::kPythonIndicatorCatalog",
                "PythonParityContract::kPythonLlmProviders",
                "PythonParityContract::kPythonConnectorOptions",
                "PythonParityContract::kPythonBacktestIntervals",
                "PythonParityContract::kPythonBacktestTemplates",
                "PythonParityContract::kPythonChartViewOptions",
                "PythonParityContract::kPythonPositionsViewOptions",
                "PythonParityContract::kPythonSignalLogicOptions",
                "PythonParityContract::kPythonMddLogicOptions",
                "PythonParityContract::kPythonStopLossModes",
            ),
            forbidden_text=PYTHON_OWNED_OPTION_VALUE_FRAGMENTS,
        ),
        ConsumerRequirement(
            "cpp_support_exposes_generated_contract",
            REPO_ROOT / "experiments" / "native-cpp" / "src" / "TradingBotWindowSupport.h",
            (
                "pythonSourceParityContractHash",
                "pythonSourceParityDomainTitle",
                "pythonSourceServiceRoutePath",
                "pythonSourceServiceRouteMethods",
                "pythonSourceIndicatorKeys",
                "pythonSourceLlmProviderKeys",
                "pythonSourceConnectorKeys",
                "pythonSourceBacktestIntervals",
                "pythonSourceBacktestTemplateKeys",
                "pythonSourceDashboardStrategyTemplateLabels",
                "pythonSourceChartViewOptionLabels",
                "pythonSourcePositionsViewOptionLabels",
                "pythonSourceSignalLogicOptionLabels",
                "pythonSourceMddLogicOptionLabels",
                "pythonSourceStopLossModeLabels",
            ),
        ),
        ConsumerRequirement(
            "cpp_config_persistence_uses_python_source_options",
            REPO_ROOT / "experiments" / "native-cpp" / "src" / "NativeConfigPersistence.cpp",
            (
                '#include "generated/PythonParityContract.h"',
                "PythonParityContract::kPythonAccountModeOptions",
                "PythonParityContract::kPythonAccountTypeOptions",
                "PythonParityContract::kPythonAssetsModeOptions",
                "PythonParityContract::kPythonBacktestExecutionBackendOptions",
                "PythonParityContract::kPythonChartMarketOptions",
                "PythonParityContract::kPythonChartViewOptions",
                "PythonParityContract::kPythonConfigModeOptions",
                "PythonParityContract::kPythonConnectorOptions",
                "PythonParityContract::kPythonDesignOptions",
                "PythonParityContract::kPythonExchangeOptions",
                "PythonParityContract::kPythonIndicatorSourceOptions",
                "PythonParityContract::kPythonLlmProviders",
                "PythonParityContract::kPythonLlmUseForOptions",
                "PythonParityContract::kPythonMarginModeOptions",
                "PythonParityContract::kPythonMddLogicOptions",
                "PythonParityContract::kPythonOptimizerMetricOptions",
                "PythonParityContract::kPythonOptimizerModeOptions",
                "PythonParityContract::kPythonOrderTypeOptions",
                "PythonParityContract::kPythonPositionModeOptions",
                "PythonParityContract::kPythonScanScopeOptions",
                "PythonParityContract::kPythonSideOptions",
                "PythonParityContract::kPythonSignalLogicOptions",
                "PythonParityContract::kPythonStopLossModes",
                "PythonParityContract::kPythonStopLossScopes",
                "PythonParityContract::kPythonThemeOptions",
                "PythonParityContract::kPythonTimeInForceOptions",
                "ChoicePairs",
                "choiceCandidateMatches",
                "validateOptionalChoice",
                "llmReasoningEffortChoicesFromSource",
            ),
            forbidden_text=PYTHON_OWNED_OPTION_VALUE_FRAGMENTS,
        ),
        ConsumerRequirement(
            "cpp_dashboard_uses_python_source_surface",
            REPO_ROOT / "experiments" / "native-cpp" / "src" / "TradingBotWindow.dashboard_ui.cpp",
            (
                "pythonSourceDefaultExecutionSymbols",
                "pythonSourceBacktestIntervals",
                "pythonSourceIndicatorDisplayNames",
                "pythonSourceDefaultEnabledIndicatorKeys",
                "pythonSourceDashboardLoopChoiceLabels",
                "pythonSourceDashboardStrategyTemplateLabels",
            ),
            forbidden_text=PYTHON_OWNED_OPTION_VALUE_FRAGMENTS,
        ),
        ConsumerRequirement(
            "cpp_backtest_uses_python_source_surface",
            REPO_ROOT / "experiments" / "native-cpp" / "src" / "TradingBotWindow.backtest.cpp",
            (
                "pythonSourceDefaultBacktestSymbols",
                "pythonSourceBacktestIntervals",
                "pythonSourceIndicatorDisplayNames",
                "pythonSourceBacktestTemplateLabels",
                "pythonSourceSignalLogicOptionLabels",
                "pythonSourceMddLogicOptionLabels",
                "pythonSourceBacktestIndicatorConfigs",
                "pythonSourceBacktestExecutionBackendOptionKeys",
                "rebuildConnectorComboForAccount",
                "resolveConnectorConfig",
                "NativeBacktestBatchRuntime::runBatch",
                "BinanceRestClient::fetchKlinesRange",
            ),
            forbidden_text=PYTHON_OWNED_OPTION_VALUE_FRAGMENTS,
        ),
        ConsumerRequirement(
            "cpp_backtest_service_api_uses_python_source_routes",
            REPO_ROOT / "experiments" / "native-cpp" / "src" / "TradingBotWindow.backtest.cpp",
            (
                "TradingBotWindowSupport::serviceApiRequestJson",
                'QStringLiteral("backtest_run")',
                'QStringLiteral("backtest")',
                'QStringLiteral("backtest_stop")',
            ),
            ("backtest_run", "backtest", "backtest_stop"),
            (CPP_SERVICE_API_EXTRACTOR,),
        ),
        ConsumerRequirement(
            "cpp_dashboard_llm_service_api_uses_python_source_routes",
            REPO_ROOT / "experiments" / "native-cpp" / "src" / "TradingBotWindow.dashboard_ui.cpp",
            (
                "TradingBotWindowSupport::serviceApiRequestJson",
                'QStringLiteral("llm_config")',
                'QStringLiteral("llm_prompt")',
                'QStringLiteral("llm_local_model_status")',
                'QStringLiteral("llm_local_model_start")',
                'QStringLiteral("llm_local_model_pull")',
                'QStringLiteral("llm_local_model_delete")',
            ),
            (
                "llm_config",
                "llm_prompt",
                "llm_local_model_status",
                "llm_local_model_start",
                "llm_local_model_pull",
                "llm_local_model_delete",
            ),
            (CPP_SERVICE_API_EXTRACTOR,),
        ),
        ConsumerRequirement(
            "cpp_config_service_api_uses_python_source_routes",
            REPO_ROOT / "experiments" / "native-cpp" / "src" / "TradingBotWindow.dashboard_overrides.cpp",
            (
                "TradingBotWindowSupport::serviceApiRequestJson",
                'QStringLiteral("config")',
                'QStringLiteral("config_save")',
                'QStringLiteral("config_load")',
            ),
            ("config", "config_save", "config_load"),
            (CPP_SERVICE_API_EXTRACTOR,),
        ),
        ConsumerRequirement(
            "cpp_chart_uses_python_source_surface",
            REPO_ROOT / "experiments" / "native-cpp" / "src" / "TradingBotWindow.chart.cpp",
            (
                "pythonSourceChartMarketOptions",
                "pythonSourceBacktestIntervals",
                "pythonSourceTradingViewIntervalKeys",
                "pythonSourceTradingViewIntervalCodes",
                "pythonSourceChartViewOptionKeys",
                "pythonSourceDefaultChartSymbols",
            ),
        ),
        ConsumerRequirement(
            "cpp_native_chart_heatmap_uses_python_source_surface",
            REPO_ROOT / "experiments" / "native-cpp" / "src" / "NativeChartHeatmap.cpp",
            (
                '#include "generated/PythonParityContract.h"',
                "PythonParityContract::kPythonTradingViewIntervalMap",
                "PythonParityContract::kPythonDefaultChartSymbols",
                "mapTradingViewInterval",
                "buildChartStatePayload",
            ),
        ),
        ConsumerRequirement(
            "cpp_positions_uses_python_source_surface",
            REPO_ROOT / "experiments" / "native-cpp" / "src" / "TradingBotWindow.positions.cpp",
            (
                "populateComboFromPythonSourceOptions",
                "pythonSourcePositionsViewOptionKeys",
                "pythonSourcePositionsViewOptionLabels",
                "applyPositionsViewMode",
                "positionsCumulativeView_",
            ),
        ),
        ConsumerRequirement(
            "cpp_account_symbols_use_python_source_fallbacks",
            REPO_ROOT / "experiments" / "native-cpp" / "src" / "TradingBotWindow.account.cpp",
            (
                "placeholderSymbolsForExchange",
                "resolveConnectorConfig",
                "fetchUsdtSymbols",
            ),
        ),
        ConsumerRequirement(
            "cpp_native_exchange_connectors_use_python_source_connectors",
            REPO_ROOT / "experiments" / "native-cpp" / "src" / "NativeExchangeConnectors.cpp",
            (
                '#include "generated/PythonParityContract.h"',
                "PythonParityContract::kPythonConnectorOptions",
                "supportedConnectorBackends",
                "buildExchangeSupportPayload",
                "buildConnectorHealthSnapshot",
            ),
        ),
        ConsumerRequirement(
            "cpp_native_strategy_runtime_uses_python_source_options",
            REPO_ROOT / "experiments" / "native-cpp" / "src" / "NativeStrategyRuntime.cpp",
            (
                '#include "generated/PythonParityContract.h"',
                "PythonParityContract::kPythonAccountModeOptions",
                "PythonParityContract::kPythonAssetsModeOptions",
                "PythonParityContract::kPythonSideOptions",
                "PythonParityContract::kPythonSignalLogicOptions",
                "PythonParityContract::kPythonStopLossModes",
                "PythonParityContract::kPythonStopLossScopes",
                "PythonParityContract::kPythonIndicatorCatalog",
                "normalizePythonUiOptionKey",
                "normalizePythonStringOption",
                "pythonUiOptionKeyAt",
                "pythonStringOptionAt",
                "canonicalSide",
                "normalizeAccountMode",
                "normalizeAssetsMode",
                "normalizeSignalLogic",
                "normalizeStopLossMode",
                "normalizeStopLossScope",
                "normalizeStrategyControls",
                "runtimeOutputKeysCsv",
            ),
        ),
        ConsumerRequirement(
            "cpp_native_indicator_runtime_uses_python_reference_fixture",
            REPO_ROOT / "experiments" / "native-cpp" / "tests" / "NativeOrderSafetyTests.cpp",
            (
                '#include "../src/NativeIndicatorRuntime.h"',
                '#include "../src/generated/PythonIndicatorReference.h"',
                "PythonIndicatorReference::kPythonSourceContractHash",
                "PythonIndicatorReference::kReferenceJson",
                "NativeIndicatorRuntime::computeConfiguredSeries",
            ),
        ),
        ConsumerRequirement(
            "cpp_dashboard_runtime_uses_native_indicator_strategy_pipeline",
            REPO_ROOT / "experiments" / "native-cpp" / "src" / "TradingBotWindow.dashboard_runtime.cpp",
            (
                '#include "NativeIndicatorRuntime.h"',
                '#include "NativeStrategyRuntime.h"',
                "NativeIndicatorRuntime::computeConfiguredSeries",
                "NativeStrategyRuntime::buildSignalDecision",
                "nativeIndicatorConfigsForKeys",
                "unsupportedEnabledIndicatorKeys",
            ),
            forbidden_text=(
                "if (!useRsi && !useStochRsi && !useWillr)",
            ),
        ),
        ConsumerRequirement(
            "cpp_order_guard_uses_python_behavior_contract",
            REPO_ROOT / "experiments" / "native-cpp" / "src" / "NativeOrderSafety.cpp",
            (
                "PythonParityContract::kPythonOrderGuardValidateExchangeFiltersAllModes",
                "PythonParityContract::kPythonOrderGuardValidateConnectorHealthAllModes",
                "PythonParityContract::kPythonOrderGuardValidateAuditWritableAllModes",
            ),
        ),
        ConsumerRequirement(
            "tauri_browser_consumes_generated_contract",
            REPO_ROOT / "experiments" / "rust-shells" / "apps" / "tauri-desktop" / "ui" / "index.html",
            (
                'src="generated-python-parity.js"',
                "window.PythonParityContract",
                "pythonParityContract.indicatorCatalog",
                "pythonParityContract.llmProviders",
                "pythonParityContract.connectorOptions",
                "pythonParityContract.backtestIntervals",
                "pythonParityContract.serviceRoutePaths",
                "pythonParityContract.defaultExecution",
                "pythonParityContract.defaultBacktest",
                "pythonParityContract.defaultChartSymbols",
                "pythonParityContract.dashboardLoopChoices",
                "pythonParityContract.dashboardStrategyTemplates",
                "pythonParityContract.backtestTemplates",
                "pythonParityContract.tradingviewIntervalMap",
                "pythonParityContract.chartViewOptions",
                "pythonParityContract.positionsViewOptions",
                "pythonParityContract.signalLogicOptions",
                "pythonParityContract.mddLogicOptions",
                "pythonParityContract.stopLossModes",
            ),
            forbidden_text=PYTHON_OWNED_OPTION_VALUE_FRAGMENTS,
        ),
        ConsumerRequirement(
            "tauri_browser_service_api_uses_python_source_routes",
            REPO_ROOT / "experiments" / "rust-shells" / "apps" / "tauri-desktop" / "ui" / "index.html",
            (
                "requestAndReport",
                "serviceRouteSupportsMethod",
                '"operational_preflight"',
                '"config_persistence"',
                '"connector_order_circuit_breaker"',
                '"connector_order_circuit_incidents"',
                '"account"',
                '"portfolio"',
                '"exchange_connector"',
                '"dashboard"',
                '"logs"',
                '"llm_local_model_status"',
                '"llm_local_model_start"',
                '"llm_local_model_pull"',
                '"llm_local_model_delete"',
                '"llm_config"',
                '"llm_prompt"',
                '"connector_order_circuit_breaker_reset"',
                '"config"',
                '"control_start"',
                '"control_stop"',
                '"config_save"',
                '"config_load"',
                '"backtest_run"',
                '"backtest_stop"',
            ),
            (
                "operational_preflight",
                "config_persistence",
                "connector_order_circuit_breaker",
                "connector_order_circuit_incidents",
                "account",
                "portfolio",
                "exchange_connector",
                "dashboard",
                "logs",
                "llm_local_model_status",
                "llm_local_model_start",
                "llm_local_model_pull",
                "llm_local_model_delete",
                "llm_config",
                "llm_prompt",
                "connector_order_circuit_breaker_reset",
                "config",
                "control_start",
                "control_stop",
                "config_save",
                "config_load",
                "backtest_run",
                "backtest_stop",
            ),
            (TAURI_REQUEST_AND_REPORT_EXTRACTOR,),
        ),
        ConsumerRequirement(
            "tauri_native_runtime_preview_backend",
            REPO_ROOT / "experiments" / "rust-shells" / "apps" / "tauri-desktop" / "src" / "main.rs",
            (
                "fn evaluate_native_runtime_preview",
                "NativeRuntimeReadOnlyMarketCycleInput::from_python_service_config",
                "NativeRuntimeLoop::new",
                "trading_execution_supported",
                "evaluate_native_runtime_preview,",
            ),
        ),
        ConsumerRequirement(
            "tauri_native_runtime_preview_browser_bridge",
            REPO_ROOT / "experiments" / "rust-shells" / "apps" / "tauri-desktop" / "ui" / "index.html",
            (
                'invoke("evaluate_native_runtime_preview"',
                "window.TradingBotNativeRuntime",
                "evaluateReadOnly",
            ),
        ),
        ConsumerRequirement(
            "tauri_native_runtime_controller_backend",
            REPO_ROOT / "experiments" / "rust-shells" / "apps" / "tauri-desktop" / "src" / "main.rs",
            (
                "fn start_native_runtime",
                "fn native_runtime_status",
                "fn set_native_runtime_paused",
                "fn stop_native_runtime",
                ".manage(NativeRuntimeState::default())",
                "start_native_runtime,",
                "native_runtime_status,",
                "set_native_runtime_paused,",
                "stop_native_runtime,",
            ),
        ),
        ConsumerRequirement(
            "tauri_native_runtime_controller_browser_bridge",
            REPO_ROOT / "experiments" / "rust-shells" / "apps" / "tauri-desktop" / "ui" / "index.html",
            (
                'id="runtime-execution-backend"',
                'invoke("start_native_runtime"',
                'invoke("native_runtime_status"',
                'invoke("set_native_runtime_paused"',
                'invoke("stop_native_runtime"',
                "buildNativeRuntimeConfig",
                "delete config.api_key",
                "delete config.api_secret",
            ),
        ),
    )


def _check_generated_artifact(artifact: GeneratedArtifact, contract_hash: str) -> dict[str, object]:
    report: dict[str, object] = {
        "name": artifact.name,
        "path": _rel(artifact.path),
        "ok": True,
        "expected_bytes": len(artifact.expected.encode("utf-8")),
        "expected_sha256": _sha256(artifact.expected),
        "expected_contract_hash": contract_hash,
        "actual_bytes": None,
        "actual_sha256": None,
        "embeds_contract_hash": False,
        "issue": "",
        "issues": [],
    }
    if not artifact.path.exists():
        report["ok"] = False
        report["issue"] = "missing generated artifact"
        report["issues"] = ["missing generated artifact"]
        return report

    actual = _read(artifact.path)
    report["actual_bytes"] = len(actual.encode("utf-8"))
    report["actual_sha256"] = _sha256(actual)
    report["embeds_contract_hash"] = contract_hash in actual
    artifact_issues: list[str] = []
    if actual != artifact.expected:
        artifact_issues.append(
            "generated artifact is stale; run "
            "python Languages/Python/tools/generate_native_parity_contracts.py"
        )
    if not report["embeds_contract_hash"]:
        artifact_issues.append("generated artifact does not embed the current Python contract hash")
    if artifact_issues:
        report["ok"] = False
        report["issue"] = "; ".join(artifact_issues)
        report["issues"] = artifact_issues
    return report


def _check_consumer(requirement: ConsumerRequirement) -> dict[str, object]:
    report: dict[str, object] = {
        "name": requirement.name,
        "path": _rel(requirement.path),
        "ok": True,
        "missing_text": [],
        "forbidden_text": [],
        "declared_service_route_names": list(requirement.service_route_names),
        "extracted_service_route_names": [],
        "service_route_extractors": list(requirement.route_extractors),
        "service_route_names": [],
        "unknown_service_routes": [],
        "unknown_route_extractors": [],
    }
    if not requirement.path.exists():
        report["ok"] = False
        report["missing_text"] = ["consumer file is missing"]
        return report

    text = _read(requirement.path)
    missing = [needle for needle in requirement.required_text if needle not in text]
    forbidden = [needle for needle in requirement.forbidden_text if needle in text]
    extracted_service_routes, unknown_route_extractors = _extract_service_routes(text, requirement.route_extractors)
    service_route_names = _ordered_unique([*requirement.service_route_names, *extracted_service_routes])
    unknown_service_routes = [
        route_name
        for route_name in service_route_names
        if route_name not in SERVICE_API_ROUTE_PATHS
    ]
    report["missing_text"] = missing
    report["forbidden_text"] = forbidden
    report["extracted_service_route_names"] = extracted_service_routes
    report["service_route_names"] = service_route_names
    report["unknown_service_routes"] = unknown_service_routes
    report["unknown_route_extractors"] = unknown_route_extractors
    report["ok"] = not missing and not forbidden and not unknown_service_routes and not unknown_route_extractors
    if forbidden:
        report["issue"] = "consumer contains Python-owned option values instead of generated parity sources"
    if unknown_service_routes or unknown_route_extractors:
        report["issue"] = "consumer references service routes missing from Python Service API contract"
        if unknown_route_extractors:
            report["issue"] = "consumer has unknown service route extractor configuration"
    return report


def audit_native_source_sync() -> dict[str, object]:
    contract_hash = native_python_source_contract_hash()
    generated_artifact_requirements = _generated_artifacts()
    consumer_requirements = _consumer_requirements()
    surface_contract = _surface_contract(generated_artifact_requirements, consumer_requirements)
    generated = [
        _check_generated_artifact(artifact, contract_hash)
        for artifact in generated_artifact_requirements
    ]
    consumers = [_check_consumer(requirement) for requirement in consumer_requirements]
    surface_contract_issues = [str(issue) for issue in surface_contract["issues"]]
    surface_wiring_issues = [
        f"{item['path']}: {item.get('issue') or 'missing consumer wiring'}"
        for item in [*generated, *consumers]
        if not bool(item["ok"])
    ]
    issues = [*surface_contract_issues, *surface_wiring_issues]
    return {
        "ok": not issues,
        "contract_hash": contract_hash,
        "source": "Languages/Python/app/native_parity.py",
        "surface_contract": surface_contract,
        "generated": generated,
        "consumers": consumers,
        "issues": issues,
        "remediation": "python Languages/Python/tools/generate_native_parity_contracts.py",
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Audit Python-owned native C++/Rust source synchronization.")
    parser.add_argument("--json", action="store_true", help="Print machine-readable JSON.")
    parser.add_argument(
        "--output",
        type=Path,
        help="Write the machine-readable audit JSON to this path before returning.",
    )
    args = parser.parse_args(argv)
    report = audit_native_source_sync()
    if args.output is not None:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")

    if args.json:
        print(json.dumps(report, indent=2, sort_keys=True))
    elif report["ok"]:
        print(f"Native source sync ok: Python contract {report['contract_hash']}")
    else:
        print("Native source sync failed:")
        for issue in report["issues"]:
            print(f"- {issue}")
        print(f"remediation: {report['remediation']}")
    return 0 if report["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
