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
from app.settings.validation import (  # noqa: E402
    _ALLOWED_BACKTEST_CONFIG_KEYS,
    _ALLOWED_CHART_CONFIG_KEYS,
    _ALLOWED_RUNTIME_CONFIG_KEYS,
)
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
    required_patterns: tuple[str, ...] = ()


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
    "rust_native_account_runtime_is_present",
    "rust_strategy_runtime_uses_python_source_options",
    "rust_native_strategy_runtime_uses_python_live_signal_fixture",
    "rust_native_backtest_runtime_uses_python_reference_fixture",
    "rust_native_backtest_batch_runtime_uses_python_reference_fixture",
    "rust_config_persistence_uses_python_source_options",
    "rust_native_exchange_connectors_use_python_source_connectors",
    "python_order_guard_implements_behavior_contract",
    "rust_order_guard_uses_python_behavior_contract",
    "cpp_support_consumes_generated_contract",
    "cpp_support_exposes_generated_contract",
    "cpp_config_persistence_uses_python_source_options",
    "cpp_dashboard_uses_python_source_surface",
    "cpp_backtest_uses_python_source_surface",
    "cpp_native_backtest_pair_overrides_match_python",
    "cpp_backtest_service_api_uses_python_source_routes",
    "cpp_dashboard_llm_service_api_uses_python_source_routes",
    "cpp_config_service_api_uses_python_source_routes",
    "cpp_code_terminal_uses_python_service_api",
    "cpp_chart_uses_python_source_surface",
    "cpp_native_chart_heatmap_uses_python_source_surface",
    "cpp_positions_uses_python_source_surface",
    "cpp_account_uses_python_service_api",
    "cpp_native_exchange_connectors_use_python_source_connectors",
    "cpp_native_strategy_runtime_uses_python_source_options",
    "cpp_native_strategy_runtime_uses_python_live_signal_fixture",
    "cpp_native_indicator_runtime_uses_python_reference_fixture",
    "cpp_native_backtest_runtime_uses_python_reference_fixture",
    "cpp_dashboard_runtime_uses_native_indicator_strategy_pipeline",
    "cpp_order_guard_uses_python_behavior_contract",
    "cpp_dashboard_runtime_enforces_live_order_safety",
    "tauri_browser_consumes_generated_contract",
    "tauri_browser_service_api_uses_python_source_routes",
    "tauri_dashboard_stream_backend_uses_python_source_route",
    "tauri_dashboard_stream_browser_bridge",
    "tauri_environment_versions_backend_uses_python_source_catalog",
    "tauri_environment_versions_browser_bridge",
    "tauri_native_runtime_preview_backend",
    "tauri_native_runtime_preview_browser_bridge",
    "tauri_native_runtime_controller_backend",
    "tauri_native_runtime_controller_browser_bridge",
    "tauri_native_backtest_bridge",
    "tauri_native_backtest_commands_registered",
    "tauri_native_backtest_browser_bridge",
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


def _section(text: str, start: str, end: str) -> str:
    start_index = text.index(start)
    end_index = text.index(end, start_index + len(start))
    return text[start_index:end_index]


def _quoted_keys(text: str) -> set[str]:
    return {
        left or right
        for left, right in re.findall(r'QStringLiteral\("([^"]+)"\)|"([^"]+)"', text)
    }


def _config_key_contract() -> dict[str, object]:
    expected = {
        "runtime": set(_ALLOWED_RUNTIME_CONFIG_KEYS),
        "chart": set(_ALLOWED_CHART_CONFIG_KEYS),
        "backtest": set(_ALLOWED_BACKTEST_CONFIG_KEYS),
    }
    source_definitions = {
        "cpp": (
            REPO_ROOT / "experiments" / "native-cpp" / "src" / "NativeConfigPersistence.cpp",
            {
                "runtime": ("const QStringList &runtimeAllowedKeys()", "const QStringList &chartAllowedKeys()"),
                "chart": ("const QStringList &chartAllowedKeys()", "const QStringList &backtestAllowedKeys()"),
                "backtest": ("const QStringList &backtestAllowedKeys()", "void validateAllowedKeys("),
            },
        ),
        "rust": (
            REPO_ROOT / "experiments" / "rust-shells" / "crates" / "core" / "src" / "config_persistence.rs",
            {
                "runtime": ("const RUNTIME_ALLOWED_KEYS", "const CHART_ALLOWED_KEYS"),
                "chart": ("const CHART_ALLOWED_KEYS", "const BACKTEST_ALLOWED_KEYS"),
                "backtest": ("const BACKTEST_ALLOWED_KEYS", "#[derive(Clone, Copy)]"),
            },
        ),
    }
    surfaces: dict[str, object] = {}
    issues: list[str] = []
    for target, (path, section_definitions) in source_definitions.items():
        target_report: dict[str, object] = {}
        if not path.exists():
            issue = f"{_rel(path)}: config allow-list source is missing"
            issues.append(issue)
            for section_name, _ in section_definitions.items():
                target_report[section_name] = {
                    "ok": False,
                    "expected": sorted(expected[section_name]),
                    "actual": [],
                    "missing": sorted(expected[section_name]),
                    "extra": [],
                    "issue": issue,
                }
            surfaces[target] = target_report
            continue

        text = _read(path)
        for section_name, (start, end) in section_definitions.items():
            try:
                actual = _quoted_keys(_section(text, start, end))
            except ValueError as exc:
                issue = f"{_rel(path)}: unable to extract {section_name} config allow-list: {exc}"
                issues.append(issue)
                target_report[section_name] = {
                    "ok": False,
                    "expected": sorted(expected[section_name]),
                    "actual": [],
                    "missing": sorted(expected[section_name]),
                    "extra": [],
                    "issue": issue,
                }
                continue

            missing = sorted(expected[section_name] - actual)
            extra = sorted(actual - expected[section_name])
            section_issues: list[str] = []
            if missing:
                section_issues.append(f"missing keys: {', '.join(missing)}")
            if extra:
                section_issues.append(f"unexpected keys: {', '.join(extra)}")
            if section_issues:
                issues.append(f"{_rel(path)} {section_name}: {'; '.join(section_issues)}")
            target_report[section_name] = {
                "ok": not section_issues,
                "expected": sorted(expected[section_name]),
                "actual": sorted(actual),
                "missing": missing,
                "extra": extra,
                "issues": section_issues,
            }
        surfaces[target] = target_report

    return {
        "ok": not issues,
        "expected": {name: sorted(values) for name, values in expected.items()},
        "surfaces": surfaces,
        "issues": issues,
    }


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
                "python_source_rust_environment_dependencies",
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
            "rust_native_account_runtime_is_present",
            REPO_ROOT / "experiments" / "rust-shells" / "crates" / "core" / "src" / "account.rs",
            (
                "pub struct BinanceSignedRestClient",
                "pub fn fetch_usdt_balance(",
                "pub fn fetch_open_futures_positions(",
                "pub fn fetch_futures_account_read_snapshot(",
                "pub fn parse_futures_symbol_settings(",
                "pub(crate) fn futures_v1_path",
                "PREFERRED_FUTURES_COLLATERAL_ASSETS",
                "parsed.is_finite().then_some(parsed)",
            ),
        ),
        ConsumerRequirement(
            "rust_strategy_runtime_uses_python_source_options",
            REPO_ROOT / "experiments" / "rust-shells" / "crates" / "core" / "src" / "strategy_runtime.rs",
            (
                "PYTHON_ACCOUNT_MODE_OPTIONS",
                "PYTHON_ASSETS_MODE_OPTIONS",
                "PYTHON_SIDE_OPTIONS",
                "PYTHON_SIGNAL_LOGIC_OPTIONS",
                "PYTHON_STOP_LOSS_MODE_CONFIG_CHOICES",
                "PYTHON_STOP_LOSS_SCOPE_CONFIG_CHOICES",
                "PYTHON_INDICATOR_CATALOG",
                "normalize_python_ui_option_key",
                "normalize_python_ui_option_key_fuzzy",
                "normalize_python_string_option_fuzzy",
                "normalize_python_config_choice_or_default",
                "runtime_output_keys",
                "canonical_side",
                "normalize_account_mode",
                "normalize_assets_mode",
                "normalize_strategy_controls",
                "normalize_stop_loss",
            ),
        ),
        ConsumerRequirement(
            "rust_native_strategy_runtime_uses_python_live_signal_fixture",
            REPO_ROOT / "experiments" / "rust-shells" / "crates" / "core" / "src" / "strategy_runtime.rs",
            (
                "PYTHON_INDICATOR_REFERENCE_JSON",
                "live_signal_cases",
                "StrategySignalInput",
                "build_signal_decision",
                "live_signal_generation_matches_python_reference_cases",
            ),
        ),
        ConsumerRequirement(
            "rust_native_backtest_runtime_uses_python_reference_fixture",
            REPO_ROOT / "experiments" / "rust-shells" / "crates" / "core" / "src" / "backtest_runtime.rs",
            (
                "PYTHON_INDICATOR_REFERENCE_JSON",
                "compute_configured_indicator_series",
                "unsupported_enabled_indicator_keys",
                "pub fn run_native_backtest(",
                "pub fn run_native_backtest_with_cancel",
                'combine_signals(&sell_arrays, size, "OR")',
                "realized_pnl - trade.entry_fee",
                "native_backtest_matches_every_generated_python_reference_case",
            ),
        ),
        ConsumerRequirement(
            "rust_native_backtest_batch_runtime_uses_python_reference_fixture",
            REPO_ROOT
            / "experiments"
            / "rust-shells"
            / "crates"
            / "core"
            / "src"
            / "backtest_batch_runtime.rs",
            (
                "PYTHON_INDICATOR_REFERENCE_JSON",
                "pub fn build_indicator_groups",
                "pub fn estimate_run_count",
                "pub fn run_native_backtest_batch",
                "run_native_backtest_with_cancel",
                "build_override_plans",
                "optimizer_score",
                "optimizer_score_from_row",
                "optimizer_max_duration_seconds",
                "resume_combo_offset",
                "completed_combo_count",
                "native_batch_budget_and_resume_preserve_python_checkpoint_semantics",
                "native_batch_matches_python_reference_result_and_reuses_candles",
            ),
        ),
        ConsumerRequirement(
            "rust_config_persistence_uses_python_source_options",
            REPO_ROOT / "experiments" / "rust-shells" / "crates" / "core" / "src" / "config_persistence.rs",
            (
                "PYTHON_LLM_PROVIDER_CHOICES",
                "PYTHON_ACCOUNT_MODE_CONFIG_CHOICES",
                "PYTHON_ACCOUNT_TYPE_CONFIG_CHOICES",
                "PYTHON_ASSETS_MODE_CONFIG_CHOICES",
                "PYTHON_BACKTEST_EXECUTION_BACKEND_CONFIG_CHOICES",
                "PYTHON_CHART_VIEW_MODE_CONFIG_CHOICES",
                "PYTHON_LLM_REASONING_EFFORT_CONFIG_CHOICES",
                "PYTHON_LLM_USE_FOR_CONFIG_CHOICES",
                "PYTHON_LOGIC_CONFIG_CHOICES",
                "PYTHON_MARGIN_MODE_CONFIG_CHOICES",
                "PYTHON_MDD_LOGIC_CONFIG_CHOICES",
                "PYTHON_OPTIMIZER_METRIC_CONFIG_CHOICES",
                "PYTHON_OPTIMIZER_MODE_CONFIG_CHOICES",
                "PYTHON_ORDER_TYPE_CONFIG_CHOICES",
                "PYTHON_POSITION_MODE_CONFIG_CHOICES",
                "PYTHON_SCAN_SCOPE_CONFIG_CHOICES",
                "PYTHON_SIDE_CONFIG_CHOICES",
                "PYTHON_STOP_LOSS_MODE_CONFIG_CHOICES",
                "PYTHON_STOP_LOSS_SCOPE_CONFIG_CHOICES",
                "PYTHON_TIF_CONFIG_CHOICES",
                "BACKTEST_ALLOWED_KEYS",
                "optimizer_max_duration_seconds",
                "604_800",
                "cfg.insert(key.to_owned(), Value::Array(Vec::new()))",
                'validate_text(&mut backtest, "symbol_source", issues, "backtest", false)',
                'validate_text(&mut cfg, "mode", &mut issues, "", false)',
                'validate_text(&mut cfg, "connector_backend", &mut issues, "", false)',
                'validate_text(&mut cfg, "indicator_source", &mut issues, "", false)',
                'validate_text(&mut cfg, "theme", &mut issues, "", true)',
                'validate_text(&mut cfg, "design", &mut issues, "", true)',
                'validate_text(&mut cfg, "selected_exchange", &mut issues, "", false)',
                "ChoiceList",
                "choice_value_from_text",
                "validate_choice",
                "normalize_stop_loss_value",
            ),
            required_patterns=(
                r'validate_text\s*\(\s*&mut backtest,\s*"connector_backend",\s*issues,\s*"backtest",\s*false\s*,?\s*\)',
            ),
        ),
        ConsumerRequirement(
            "rust_native_exchange_connectors_use_python_source_connectors",
            REPO_ROOT / "experiments" / "rust-shells" / "crates" / "core" / "src" / "exchange_connectors.rs",
            (
                "PYTHON_CONNECTOR_OPTIONS",
                "PYTHON_BROKER_ORDER_ROUTING_BACKENDS",
                "PYTHON_BROKER_CANONICAL_NAMES",
                "PYTHON_SUPPORTED_EXCHANGES",
                "PYTHON_CCXT_DIAGNOSTIC_EXCHANGES",
                "PYTHON_CCXT_ORDER_ROUTING_EXCHANGES",
                "PYTHON_ORDER_EXECUTION_EXCHANGES",
                "PYTHON_CCXT_EXCHANGE_IDS",
                "canonical_broker_name",
                "build_exchange_support_payload",
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
                "PythonParityContract::kPythonDefaultExecutionJson",
                "PythonParityContract::kPythonDefaultBacktestJson",
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
                "pythonSourceDefaultExecutionConfig",
                "pythonSourceDefaultBacktestConfig",
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
                "PythonParityContract::kPythonLlmProviderChoices",
                "PythonParityContract::kPythonAccountModeConfigChoices",
                "PythonParityContract::kPythonAccountTypeConfigChoices",
                "PythonParityContract::kPythonAssetsModeConfigChoices",
                "PythonParityContract::kPythonBacktestExecutionBackendConfigChoices",
                "PythonParityContract::kPythonChartViewModeConfigChoices",
                "PythonParityContract::kPythonLlmReasoningEffortConfigChoices",
                "PythonParityContract::kPythonLlmUseForConfigChoices",
                "PythonParityContract::kPythonLogicConfigChoices",
                "PythonParityContract::kPythonMarginModeConfigChoices",
                "PythonParityContract::kPythonMddLogicConfigChoices",
                "PythonParityContract::kPythonOptimizerMetricConfigChoices",
                "PythonParityContract::kPythonOptimizerModeConfigChoices",
                "PythonParityContract::kPythonOrderTypeConfigChoices",
                "PythonParityContract::kPythonPositionModeConfigChoices",
                "PythonParityContract::kPythonScanScopeConfigChoices",
                "PythonParityContract::kPythonSideConfigChoices",
                "PythonParityContract::kPythonStopLossModeConfigChoices",
                "PythonParityContract::kPythonStopLossScopeConfigChoices",
                "PythonParityContract::kPythonTifConfigChoices",
                "backtestAllowedKeys",
                "fee_bps",
                "slippage_bps",
                "optimizer_max_duration_seconds",
                "604'800",
                'validateText(&backtest, QStringLiteral("symbol_source"), issues, QStringLiteral("backtest"))',
                'validateText(&cfg, QStringLiteral("mode"), &issues)',
                'validateText(&cfg, QStringLiteral("connector_backend"), &issues)',
                'validateText(&cfg, QStringLiteral("indicator_source"), &issues)',
                'validateText(&cfg, QStringLiteral("theme"), &issues, {}, true)',
                'validateText(&cfg, QStringLiteral("design"), &issues, {}, true)',
                'validateText(&cfg, QStringLiteral("selected_exchange"), &issues)',
                'validateText(&backtest, QStringLiteral("connector_backend"), issues, QStringLiteral("backtest"))',
                "ChoicePairs",
                "choiceCandidateMatches",
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
                "dashboardOrderAuditEnabledCheck_",
                "dashboardConnectorOrderCircuitEnabledCheck_",
                "dashboardConnectorOrderCircuitResetBtn_",
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
                "pythonSourceDefaultBacktestConfig",
                "buildBacktestServiceConfig",
                "buildBacktestSymbolIntervalPairs",
                "backtestFeeBpsSpin_",
                "backtestSlippageBpsSpin_",
                "rebuildConnectorComboForAccount",
                "resolveConnectorConfig",
                "NativeBacktestBatchRuntime::runBatch",
                "BinanceRestClient::fetchKlinesRange",
            ),
            forbidden_text=PYTHON_OWNED_OPTION_VALUE_FRAGMENTS,
        ),
        ConsumerRequirement(
            "cpp_native_backtest_pair_overrides_match_python",
            REPO_ROOT / "experiments" / "native-cpp" / "src" / "NativeBacktestBatchRuntime.cpp",
            (
                "buildOverridePlans",
                "mergedPairControls",
                "resolveIndicatorBundle",
                "applyPairControls",
                "strategyControls(runTemplate)",
                "candleCache",
                "request.pairOverrides",
            ),
        ),
        ConsumerRequirement(
            "cpp_backtest_service_api_uses_python_source_routes",
            REPO_ROOT / "experiments" / "native-cpp" / "src" / "TradingBotWindow.backtest.cpp",
            (
                "TradingBotWindowSupport::serviceApiRequestJson",
                'QStringLiteral("config")',
                'QStringLiteral("backtest_run")',
                'QStringLiteral("backtest")',
                'QStringLiteral("backtest_stop")',
            ),
            ("config", "backtest_run", "backtest", "backtest_stop"),
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
                'QStringLiteral("order_audit_enabled")',
                'QStringLiteral("connector_order_block_circuit_breaker_enabled")',
                'QStringLiteral("connector_order_circuit_incident_log_path")',
                'QStringLiteral("lookback")',
                'QStringLiteral("order_type")',
                'QStringLiteral("operational_connector_snapshot_stale_seconds")',
                'QStringLiteral("operational_live_start_gate_enabled")',
                'QStringLiteral("operational_live_order_gate_enabled")',
                "buildBacktestServiceConfig",
                "hydrateBacktestServiceConfig",
                "hydrateBacktestSymbolIntervalPairs",
                'params.remove(QStringLiteral("enabled"))',
            ),
            ("config", "config_save", "config_load"),
            (CPP_SERVICE_API_EXTRACTOR,),
        ),
        ConsumerRequirement(
            "cpp_code_terminal_uses_python_service_api",
            REPO_ROOT / "experiments" / "native-cpp" / "src" / "TradingBotWindow.cpp",
            (
                "Controlled Terminal",
                "TradingBotWindowSupport::serviceApiRequestJson",
                'QStringLiteral("terminal_run")',
                'QStringLiteral("cpp-desktop-terminal")',
            ),
            ("terminal_run",),
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
                "TradingBotWindowSupport::serviceApiRequestJson",
                'QStringLiteral("position_close")',
            ),
            ("position_close",),
            (CPP_SERVICE_API_EXTRACTOR,),
        ),
        ConsumerRequirement(
            "cpp_account_uses_python_service_api",
            REPO_ROOT / "experiments" / "native-cpp" / "src" / "TradingBotWindow.account.cpp",
            (
                "serviceApiRequestJson",
                'QStringLiteral("account")',
                'QStringLiteral("config")',
                "exchangeUsesBinanceApi",
                "resolveConnectorConfig",
                "fetchUsdtSymbols",
            ),
            ("account", "config"),
            (CPP_SERVICE_API_EXTRACTOR,),
        ),
        ConsumerRequirement(
            "cpp_native_exchange_connectors_use_python_source_connectors",
            REPO_ROOT / "experiments" / "native-cpp" / "src" / "NativeExchangeConnectors.cpp",
            (
                '#include "generated/PythonParityContract.h"',
                "PythonParityContract::kPythonConnectorOptions",
                "PythonParityContract::kPythonBrokerCanonicalNames",
                "PythonParityContract::kPythonSupportedExchanges",
                "PythonParityContract::kPythonCcxtDiagnosticExchanges",
                "PythonParityContract::kPythonCcxtOrderRoutingExchanges",
                "PythonParityContract::kPythonOrderExecutionExchanges",
                "PythonParityContract::kPythonCcxtExchangeIds",
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
                "PythonParityContract::kPythonStopLossModeConfigChoices",
                "PythonParityContract::kPythonStopLossScopeConfigChoices",
                "PythonParityContract::kPythonIndicatorCatalog",
                "normalizePythonUiOptionKey",
                "normalizePythonStringOption",
                "normalizePythonConfigChoice",
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
            "cpp_native_strategy_runtime_uses_python_live_signal_fixture",
            REPO_ROOT / "experiments" / "native-cpp" / "tests" / "NativeOrderSafetyTests.cpp",
            (
                '#include "../src/NativeStrategyRuntime.h"',
                "live_signal_cases",
                "NativeStrategyRuntime::StrategySignalInput",
                "NativeStrategyRuntime::buildSignalDecision",
                "native C++ live signal description should match Python",
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
            "cpp_native_backtest_runtime_uses_python_reference_fixture",
            REPO_ROOT / "experiments" / "native-cpp" / "tests" / "NativeOrderSafetyTests.cpp",
            (
                '#include "../src/NativeBacktestRuntime.h"',
                '#include "../src/generated/PythonIndicatorReference.h"',
                "PythonIndicatorReference::kReferenceJson",
                "NativeBacktestRuntime::run",
                'QStringLiteral("max_drawdown_result_value")',
                'QStringLiteral("fees_paid")',
                'QStringLiteral("indicator_keys")',
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
            "cpp_dashboard_runtime_enforces_live_order_safety",
            REPO_ROOT / "experiments" / "native-cpp" / "src" / "TradingBotWindow.dashboard_runtime.cpp",
            (
                '#include "NativeOrderSafety.h"',
                "NativeOrderSafety::guardFuturesMinimumOrderAutoBump",
                "NativeOrderSafety::guardLiveOrderSubmit",
                "liveAllowAutoBumpToMinOrder",
                "dashboardRuntimeLiveSubmitAttemptCount_",
                "dashboardRuntimeConnectorOrderCircuit_",
                "NativeOrderSafety::buildConnectorOrderCircuitIncident",
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
                "pythonParityContract.chartViewKeys",
                "pythonParityContract.chartViewOptions",
                "pythonParityContract.positionsViewOptions",
                "pythonParityContract.orderTypeOptions",
                "pythonParityContract.backtestExecutionBackendOptions",
                "pythonParityContract.signalLogicOptions",
                "pythonParityContract.mddLogicOptions",
                "pythonParityContract.stopLossModes",
                "pythonParityContract.rustEnvironmentDependencies",
                "const buildBacktestConfigPatch",
                "backtest: buildBacktestConfigPatch()",
                'hydrateBacktestControls(result.config?.backtest)',
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
                '"position_close"',
                '"terminal_run"',
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
                "position_close",
                "terminal_run",
            ),
            (TAURI_REQUEST_AND_REPORT_EXTRACTOR,),
        ),
        ConsumerRequirement(
            "tauri_dashboard_stream_backend_uses_python_source_route",
            REPO_ROOT / "experiments" / "rust-shells" / "apps" / "tauri-desktop" / "src" / "main.rs",
            (
                'const ROUTE_NAME: &str = "stream_dashboard"',
                "fn run_service_dashboard_stream",
                "fn start_service_dashboard_stream",
                "fn stop_service_dashboard_stream",
                'header("Accept", "text/event-stream")',
                "bearer_auth(api_token.trim())",
                '"service-dashboard"',
                '"service-dashboard-stream-status"',
                ".manage(ServiceDashboardStreamState::default())",
                "start_service_dashboard_stream,",
                "stop_service_dashboard_stream,",
            ),
            ("stream_dashboard",),
        ),
        ConsumerRequirement(
            "tauri_dashboard_stream_browser_bridge",
            REPO_ROOT / "experiments" / "rust-shells" / "apps" / "tauri-desktop" / "ui" / "index.html",
            (
                'id="service-stream-status-text"',
                'listen("service-dashboard"',
                'listen("service-dashboard-stream-status"',
                'invoke("start_service_dashboard_stream"',
                'invoke("stop_service_dashboard_stream"',
                "dashboardPayloadFromStreamEvent",
                "dashboardStreamReconnectDelay",
                "applyDashboardPayload",
                "hydrateControls: false",
            ),
            ("stream_dashboard",),
        ),
        ConsumerRequirement(
            "tauri_environment_versions_backend_uses_python_source_catalog",
            REPO_ROOT / "experiments" / "rust-shells" / "apps" / "tauri-desktop" / "src" / "main.rs",
            (
                "python_source_rust_environment_dependencies",
                "fn environment_dependency_rows",
                "fn environment_versions",
                "fn update_rust_environment",
                "fn generated_manifest_path",
                "validate_rust_environment_update_scope",
                "environment_versions,",
                "update_rust_environment,",
            ),
        ),
        ConsumerRequirement(
            "tauri_environment_versions_browser_bridge",
            REPO_ROOT / "experiments" / "rust-shells" / "apps" / "tauri-desktop" / "ui" / "index.html",
            (
                "pythonParityContract.rustEnvironmentDependencies",
                'id="environment-versions-table"',
                'id="environment-update-selected-btn"',
                'id="environment-update-all-btn"',
                'invoke("environment_versions"',
                'invoke("update_rust_environment"',
                "normalizeEnvironmentVersionRows",
                "environmentUpdateScope",
            ),
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
                "fn execute_native_runtime_cycle",
                "fn native_runtime_status",
                "fn set_native_runtime_paused",
                "fn stop_native_runtime",
                "fn save_native_runtime_config",
                "fn load_native_runtime_config",
                "write_service_config_file(&config, None, false, false",
                "load_service_config_file(None)",
                "run_guarded_execution_cycle",
                "place_futures_market_order",
                "engine.api_key.clear()",
                "engine.api_secret.clear()",
                ".manage(NativeRuntimeState::default())",
                "start_native_runtime,",
                "execute_native_runtime_cycle,",
                "native_runtime_status,",
                "set_native_runtime_paused,",
                "stop_native_runtime,",
                "save_native_runtime_config,",
                "load_native_runtime_config,",
            ),
        ),
        ConsumerRequirement(
            "tauri_native_runtime_controller_browser_bridge",
            REPO_ROOT / "experiments" / "rust-shells" / "apps" / "tauri-desktop" / "ui" / "index.html",
            (
                'id="runtime-execution-backend"',
                'invoke("start_native_runtime"',
                'invoke("execute_native_runtime_cycle"',
                'invoke("native_runtime_status"',
                'invoke("set_native_runtime_paused"',
                'invoke("stop_native_runtime"',
                'invoke("save_native_runtime_config"',
                'invoke("load_native_runtime_config"',
                "buildNativeRuntimeConfig",
                "buildNativePersistedConfig",
                "Inline secrets were excluded.",
                "execute: executeNativeRuntimeCycle",
                'id="live-trading-enabled"',
                'id="live-trading-acknowledgement"',
                'id="live-trading-max-leverage"',
                'id="live-trading-max-position-pct"',
                'id="live-trading-max-session-orders"',
                'id="live-allow-auto-bump-to-min-order"',
                'id="max-auto-bump-percent"',
                'id="auto-bump-percent-multiplier"',
                'id="order-audit-enabled"',
                'id="order-audit-log-path"',
                'id="order-audit-max-bytes"',
                'id="order-audit-backup-count"',
                'id="connector-order-circuit-enabled"',
                'id="connector-order-circuit-threshold"',
                'id="connector-order-circuit-window-seconds"',
                'id="connector-order-incident-log-path"',
                'id="connector-order-incident-max-bytes"',
                'id="connector-order-incident-backup-count"',
                "live_trading_enabled:",
                "live_trading_acknowledgement:",
                "live_trading_max_leverage:",
                "live_trading_max_position_pct:",
                "live_trading_max_session_orders:",
                "live_allow_auto_bump_to_min_order:",
                "max_auto_bump_percent:",
                "auto_bump_percent_multiplier:",
                "order_audit_enabled:",
                "order_audit_log_path:",
                "order_audit_max_bytes:",
                "order_audit_backup_count:",
                "connector_order_block_circuit_breaker_enabled:",
                "connector_order_block_pause_threshold:",
                "connector_order_block_window_seconds:",
                "connector_order_circuit_incident_log_path:",
                "connector_order_circuit_incident_log_max_bytes:",
                "connector_order_circuit_incident_log_backup_count:",
                "delete config.api_key",
                "delete config.api_secret",
            ),
        ),
        ConsumerRequirement(
            "tauri_native_backtest_bridge",
            REPO_ROOT / "experiments" / "rust-shells" / "apps" / "tauri-desktop" / "src" / "native_backtest.rs",
            (
                "NativeBacktestBatchRequest::from_python_request",
                "run_native_backtest_batch",
                "fetch_klines_range",
                "request.start_ms",
                "request.end_ms",
                "request.warmup_bars",
                "NativeBacktestCheckpoint",
                "resume_requested",
                "managed.checkpoint",
                'state == "budget_exhausted"',
                "native_market_data_supported",
                "pub fn start_native_backtest",
                "pub fn native_backtest_status",
                "pub fn stop_native_backtest",
            ),
        ),
        ConsumerRequirement(
            "tauri_native_backtest_commands_registered",
            REPO_ROOT / "experiments" / "rust-shells" / "apps" / "tauri-desktop" / "src" / "main.rs",
            (
                "use native_backtest::NativeBacktestState",
                ".manage(NativeBacktestState::default())",
                "native_backtest::start_native_backtest",
                "native_backtest::native_backtest_status",
                "native_backtest::stop_native_backtest",
            ),
        ),
        ConsumerRequirement(
            "tauri_native_backtest_browser_bridge",
            REPO_ROOT / "experiments" / "rust-shells" / "apps" / "tauri-desktop" / "ui" / "index.html",
            (
                "const submitBacktest",
                "usesLocalBacktestBackend",
                'invoke("start_native_backtest"',
                'invoke("native_backtest_status"',
                'invoke("stop_native_backtest"',
                "syncBacktestResumeAvailability",
                'runNativeBacktest("Resume optimizer"',
                "Native Rust backtest",
                "nativeBacktestResult",
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
        "missing_patterns": [],
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
    missing_patterns = [
        pattern
        for pattern in requirement.required_patterns
        if re.search(pattern, text, re.DOTALL) is None
    ]
    forbidden = [needle for needle in requirement.forbidden_text if needle in text]
    extracted_service_routes, unknown_route_extractors = _extract_service_routes(text, requirement.route_extractors)
    service_route_names = _ordered_unique([*requirement.service_route_names, *extracted_service_routes])
    unknown_service_routes = [
        route_name
        for route_name in service_route_names
        if route_name not in SERVICE_API_ROUTE_PATHS
    ]
    report["missing_text"] = missing
    report["missing_patterns"] = missing_patterns
    report["forbidden_text"] = forbidden
    report["extracted_service_route_names"] = extracted_service_routes
    report["service_route_names"] = service_route_names
    report["unknown_service_routes"] = unknown_service_routes
    report["unknown_route_extractors"] = unknown_route_extractors
    report["ok"] = (
        not missing
        and not missing_patterns
        and not forbidden
        and not unknown_service_routes
        and not unknown_route_extractors
    )
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
    config_key_contract = _config_key_contract()
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
    issues.extend(str(issue) for issue in config_key_contract["issues"])
    return {
        "ok": not issues,
        "contract_hash": contract_hash,
        "source": "Languages/Python/app/native_parity.py",
        "surface_contract": surface_contract,
        "config_key_contract": config_key_contract,
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
