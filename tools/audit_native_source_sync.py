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

from app.native_parity import (  # noqa: E402
    native_python_source_contract_hash,
    native_python_source_contract_payload,
)
from app.service.api_contract import SERVICE_API_ROUTE_PATHS  # noqa: E402
from app.settings.validation import (  # noqa: E402
    _ALLOWED_BACKTEST_CONFIG_KEYS,
    _ALLOWED_CHART_CONFIG_KEYS,
    _ALLOWED_RUNTIME_CONFIG_KEYS,
)
from tools.generate_native_parity_contracts import (  # noqa: E402
    _cpp_string,
    _cpp_string_chunks,
    _python_option_catalog_manifest,
    _python_option_catalog_json,
    _rust_string,
    CPP_INDICATOR_REFERENCE_OUTPUT,
    CPP_EXCHANGE_SUPPORT_REFERENCE_OUTPUT,
    CPP_PORTFOLIO_REFERENCE_OUTPUT,
    CPP_OUTPUT,
    RUST_EXCHANGE_SUPPORT_REFERENCE_OUTPUT,
    RUST_INDICATOR_REFERENCE_OUTPUT,
    RUST_PORTFOLIO_REFERENCE_OUTPUT,
    RUST_OUTPUT,
    TAURI_BROWSER_OUTPUT,
    render_cpp_exchange_support_reference_header,
    render_cpp_indicator_reference_header,
    render_cpp_portfolio_reference_header,
    render_cpp_header,
    render_rust_exchange_support_reference_module,
    render_rust_indicator_reference_module,
    render_rust_portfolio_reference_module,
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
    "rust_exchange_support_reference_fixture",
    "rust_portfolio_reference_fixture",
    "cpp_generated_contract",
    "cpp_indicator_reference_fixture",
    "cpp_exchange_support_reference_fixture",
    "cpp_portfolio_reference_fixture",
    "tauri_browser_generated_contract",
)
REQUIRED_CONSUMER_SURFACE_NAMES = (
    "rust_startup_packaging_contract",
    "rust_core_consumes_generated_contract",
    "rust_native_account_runtime_is_present",
    "rust_native_portfolio_reconciliation_uses_python_missing_options",
    "rust_native_portfolio_reconciliation_uses_python_reference_fixture",
    "rust_strategy_runtime_uses_python_source_options",
    "rust_native_strategy_runtime_uses_python_live_signal_fixture",
    "rust_native_strategy_runtime_uses_python_interval_timing_fixture",
    "rust_native_indicator_runtime_uses_python_enabled_fixtures",
    "rust_native_backtest_runtime_uses_python_reference_fixture",
    "rust_native_backtest_batch_runtime_uses_python_reference_fixture",
    "rust_native_backtest_interval_timing_uses_python_reference_fixture",
    "rust_config_persistence_uses_python_source_options",
    "rust_native_exchange_connectors_use_python_source_connectors",
    "rust_native_exchange_connectors_use_python_reference_fixture",
    "rust_native_runtime_ownership_uses_python_source_policy",
    "rust_native_runtime_ownership_uses_python_reference_fixture",
    "rust_native_runtime_routing_uses_python_reference_fixture",
    "rust_native_runtime_mode_uses_python_source_policy",
    "rust_native_runtime_mode_uses_python_reference_fixture",
    "python_order_guard_implements_behavior_contract",
    "rust_order_guard_uses_python_behavior_contract",
    "rust_order_guard_uses_python_live_safety_environment",
    "rust_order_guard_uses_python_order_intent_fixture",
    "rust_order_guard_uses_python_live_safety_fixture",
    "rust_native_stop_intent_uses_python_reference_fixture",
    "rust_order_guard_uses_python_connector_health_fixture",
    "rust_llm_output_policy_uses_python_reference_fixture",
    "rust_llm_chat_request_uses_python_reference_fixture",
    "rust_llm_dynamic_catalog_uses_python_sources",
    "cpp_startup_packaging_contract",
    "cpp_support_consumes_generated_contract",
    "cpp_support_exposes_generated_contract",
    "cpp_config_persistence_uses_python_source_options",
    "cpp_dashboard_uses_python_source_surface",
    "cpp_indicator_dialog_uses_python_ma_options",
    "cpp_backtest_uses_python_source_surface",
    "cpp_native_backtest_pair_overrides_match_python",
    "cpp_backtest_service_api_uses_python_source_routes",
    "cpp_dashboard_llm_service_api_uses_python_source_routes",
    "cpp_llm_catalog_payload_fields_follow_python",
    "cpp_llm_dynamic_catalog_uses_python_sources",
    "cpp_config_service_api_uses_python_source_routes",
    "cpp_code_terminal_uses_python_service_api",
    "cpp_chart_uses_python_source_surface",
    "cpp_native_chart_heatmap_uses_python_source_surface",
    "cpp_positions_uses_python_source_surface",
    "cpp_native_portfolio_reconciliation_uses_python_missing_options",
    "cpp_native_portfolio_reconciliation_policy_uses_python_keys",
    "cpp_native_portfolio_reconciliation_uses_python_reference_fixture",
    "cpp_account_uses_python_service_api",
    "cpp_native_exchange_connectors_use_python_source_connectors",
    "cpp_native_exchange_connectors_use_python_reference_fixture",
    "cpp_native_runtime_ownership_uses_python_source_policy",
    "cpp_native_runtime_ownership_uses_python_reference_fixture",
    "cpp_native_runtime_routing_uses_python_reference_fixture",
    "cpp_native_runtime_mode_uses_python_source_policy",
    "cpp_native_runtime_mode_uses_python_reference_fixture",
    "cpp_native_indicator_source_uses_python_source_policy",
    "cpp_native_indicator_runtime_uses_python_source_policy",
    "cpp_native_strategy_runtime_uses_python_source_options",
    "cpp_native_strategy_runtime_uses_python_live_signal_fixture",
    "cpp_native_strategy_runtime_uses_python_behavior_fixtures",
    "cpp_native_strategy_runtime_uses_python_interval_timing_fixture",
    "cpp_native_indicator_runtime_uses_python_reference_fixture",
    "cpp_native_backtest_runtime_uses_python_reference_fixture",
    "cpp_native_backtest_interval_timing_uses_python_reference_fixture",
    "cpp_dashboard_runtime_uses_native_indicator_strategy_pipeline",
    "cpp_order_guard_uses_python_behavior_contract",
    "cpp_order_guard_uses_python_live_safety_environment",
    "cpp_native_order_guard_uses_python_order_intent_fixture",
    "cpp_native_order_guard_uses_python_live_safety_fixture",
    "cpp_native_stop_intent_uses_python_reference_fixture",
    "cpp_dashboard_runtime_uses_python_stop_intent",
    "cpp_native_order_guard_uses_python_connector_health_fixture",
    "cpp_llm_output_policy_uses_python_reference_fixture",
    "cpp_llm_chat_request_uses_python_reference_fixture",
    "cpp_dashboard_runtime_enforces_live_order_safety",
    "tauri_browser_consumes_generated_contract",
    "tauri_native_runtime_ownership_uses_python_reference_fixture",
    "tauri_native_runtime_mode_uses_python_reference_fixture",
    "tauri_native_runtime_routing_uses_python_reference_fixture",
    "tauri_browser_consumes_generated_starter_catalogs",
    "tauri_browser_service_api_uses_python_source_routes",
    "tauri_llm_catalog_uses_python_source_route",
    "tauri_dashboard_stream_backend_uses_python_source_route",
    "tauri_dashboard_stream_browser_bridge",
    "tauri_environment_versions_backend_uses_python_source_catalog",
    "tauri_environment_versions_browser_bridge",
    "tauri_native_runtime_preview_backend",
    "tauri_native_runtime_preview_browser_bridge",
    "tauri_native_runtime_controller_backend",
    "tauri_native_runtime_controller_browser_bridge",
    "tauri_native_runtime_poll_timing_uses_python_reference_fixture",
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


def _consumer_target(requirement: ConsumerRequirement) -> str:
    relative = requirement.path.relative_to(REPO_ROOT).as_posix()
    if relative.startswith("experiments/native-cpp/"):
        return "cpp"
    if relative.startswith("experiments/rust-shells/"):
        return "rust"
    return "shared"


def _consumer_surface_groups(
    consumers: tuple[ConsumerRequirement, ...],
    consumer_reports: list[dict[str, object]] | tuple[dict[str, object], ...] | None = None,
) -> dict[str, dict[str, object]]:
    reports_by_name = {
        str(report.get("name")): report
        for report in (consumer_reports or [])
        if report.get("name")
    }
    required_by_target: dict[str, list[str]] = {"cpp": [], "rust": []}
    actual_by_target: dict[str, list[str]] = {"cpp": [], "rust": []}
    for consumer in consumers:
        target = _consumer_target(consumer)
        targets = ("cpp", "rust") if target == "shared" else (target,)
        report = reports_by_name.get(consumer.name)
        report_ok = True if consumer_reports is None else bool(report and report.get("ok"))
        for destination in targets:
            required_by_target[destination].append(consumer.name)
            if report_ok:
                actual_by_target[destination].append(consumer.name)
    return {
        target: {
            "required": required_by_target[target],
            "actual": actual_by_target[target],
            "missing": [
                name for name in required_by_target[target] if name not in actual_by_target[target]
            ],
            "extra": [
                name for name in actual_by_target[target] if name not in required_by_target[target]
            ],
        }
        for target in ("cpp", "rust")
    }


def _surface_contract(
    generated_artifacts: tuple[GeneratedArtifact, ...],
    consumers: tuple[ConsumerRequirement, ...],
    consumer_reports: list[dict[str, object]] | tuple[dict[str, object], ...] | None = None,
) -> dict[str, object]:
    generated_artifact_names = tuple(artifact.name for artifact in generated_artifacts)
    consumer_surface_names = tuple(
        str(report.get("name"))
        for report in (consumer_reports or [])
        if report.get("name") and bool(report.get("ok"))
    )
    if consumer_reports is None:
        consumer_surface_names = tuple(consumer.name for consumer in consumers)
    consumer_surface_groups = _consumer_surface_groups(consumers, consumer_reports)
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
        "consumer_surfaces_by_target": consumer_surface_groups,
        "issues": issues,
    }


def _percentage(matched: int, total: int) -> float:
    if total <= 0:
        return 100.0
    return round((max(0, min(matched, total)) / total) * 100.0, 2)


def _set_contract_percentage(expected: object, actual: object) -> float:
    expected_set = {str(value) for value in expected} if isinstance(expected, (list, tuple, set)) else set()
    actual_set = {str(value) for value in actual} if isinstance(actual, (list, tuple, set)) else set()
    union = expected_set | actual_set
    return _percentage(len(expected_set & actual_set), len(union))


def _config_contract_percentages(config_key_contract: dict[str, object]) -> dict[str, float]:
    surfaces = config_key_contract.get("surfaces", {})
    if not isinstance(surfaces, dict):
        return {"cpp": 0.0, "rust": 0.0}
    percentages: dict[str, float] = {}
    for target in ("cpp", "rust"):
        target_surface = surfaces.get(target, {})
        if not isinstance(target_surface, dict):
            percentages[target] = 0.0
            continue
        matched = 0
        total = 0
        for section in target_surface.values():
            if not isinstance(section, dict):
                continue
            expected = section.get("expected", [])
            actual = section.get("actual", [])
            expected_set = {str(value) for value in expected} if isinstance(expected, list) else set()
            actual_set = {str(value) for value in actual} if isinstance(actual, list) else set()
            total += len(expected_set | actual_set)
            matched += len(expected_set & actual_set)
        percentages[target] = _percentage(matched, total)
    return percentages


def _domain_evidence_contract(
    payload: dict[str, object],
    consumers: list[dict[str, object]],
) -> dict[str, object]:
    """Require every declared parity domain to have passing native evidence surfaces."""

    available = {
        str(item.get("name"))
        for item in consumers
        if isinstance(item, dict) and item.get("name")
    }
    passed = {
        str(item.get("name"))
        for item in consumers
        if isinstance(item, dict) and item.get("name") and bool(item.get("ok"))
    }
    domain_reports: list[dict[str, object]] = []
    issues: list[str] = []
    domains = payload.get("domains", [])
    if not isinstance(domains, list):
        return {
            "ok": False,
            "domains": [],
            "available_consumer_surface_names": sorted(available),
            "issues": ["Python parity domains are not a list"],
        }

    for domain in domains:
        if not isinstance(domain, dict):
            issues.append("Python parity domain entry is not an object")
            continue
        key = str(domain.get("key") or "")
        domain_report: dict[str, object] = {"key": key}
        for target in ("cpp", "rust"):
            requirement_key = f"{target}_required_before_full_parity"
            required = [str(item) for item in domain.get(requirement_key, []) or []]
            missing = sorted(set(required) - passed)
            unknown = sorted(set(required) - available)
            declared_complete = bool(domain.get(f"{target}_full_parity"))
            target_ok = declared_complete and not missing and not unknown
            domain_report[target] = {
                "required": required,
                "missing": missing,
                "unknown": unknown,
                "declared_complete": declared_complete,
                "ok": target_ok,
            }
            if not target_ok:
                issues.append(
                    f"{key} {target} parity evidence incomplete"
                    f" (missing={missing or '-'}; unknown={unknown or '-'};"
                    f" declared_complete={declared_complete})"
                )
        domain_reports.append(domain_report)

    return {
        "ok": not issues,
        "domains": domain_reports,
        "available_consumer_surface_names": sorted(available),
        "passed_consumer_surface_names": sorted(passed),
        "issues": issues,
    }


def _native_contract_percentages(
    payload: dict[str, object],
    feature_option_contract: dict[str, object],
    config_key_contract: dict[str, object],
    surface_contract: dict[str, object],
    generated: list[dict[str, object]],
    domain_evidence: dict[str, object],
) -> dict[str, object]:
    domains = payload.get("domains", [])
    domain_count = len(domains) if isinstance(domains, list) else 0
    domain_reports = domain_evidence.get("domains", [])
    domain_percentages = {
        target: _percentage(
            sum(
                1
                for domain in domain_reports
                if isinstance(domain, dict)
                and isinstance(domain.get(target), dict)
                and bool(domain[target].get("ok"))
            ),
            domain_count,
        )
        for target in ("cpp", "rust")
    }

    option_catalog_count = int(feature_option_contract.get("option_catalog_count", 0))
    option_entry_count = int(feature_option_contract.get("option_catalog_entry_count", 0))
    generated_matches = feature_option_contract.get("generated_native_contracts_match_python", {})
    generated_match_percentages = {
        target: _percentage(
            1 if isinstance(generated_matches, dict) and bool(generated_matches.get(target)) else 0,
            1,
        )
        for target in ("cpp", "rust")
    }
    config_percentages = _config_contract_percentages(config_key_contract)
    manifest_contract = feature_option_contract.get("option_catalog_manifest", {})
    manifest_targets = manifest_contract.get("targets", {}) if isinstance(manifest_contract, dict) else {}
    manifest_percentages = {
        target: _percentage(
            1 if isinstance(manifest_targets, dict) and bool(
                isinstance(manifest_targets.get(target), dict)
                and manifest_targets[target].get("ok")
            ) else 0,
            1,
        )
        for target in ("cpp", "rust")
    }
    manifest_value_percentages = {
        target: _percentage(
            1 if isinstance(manifest_targets, dict) and bool(
                isinstance(manifest_targets.get(target), dict)
                and manifest_targets[target].get("catalog_values_exact")
            ) else 0,
            1,
        )
        for target in ("cpp", "rust")
    }
    catalog_consumer_contract = feature_option_contract.get("option_catalog_consumers", {})
    catalog_consumer_targets = (
        catalog_consumer_contract.get("targets", {})
        if isinstance(catalog_consumer_contract, dict)
        else {}
    )
    catalog_consumer_percentages = {
        target: _percentage(
            1 if isinstance(catalog_consumer_targets, dict) and bool(
                isinstance(catalog_consumer_targets.get(target), dict)
                and catalog_consumer_targets[target].get("ok")
            ) else 0,
            1,
        )
        for target in ("cpp", "rust")
    }

    required_artifacts = surface_contract.get("required_generated_artifact_names", [])
    actual_artifacts = surface_contract.get("actual_generated_artifact_names", [])
    artifact_percentages: dict[str, float] = {}
    for target, prefix in (("cpp", "cpp_"), ("rust", ("rust_", "tauri_"))):
        expected = [
            name
            for name in required_artifacts
            if isinstance(name, str)
            and (name.startswith(prefix) if isinstance(prefix, str) else name.startswith(prefix))
        ]
        actual = [
            name
            for name in actual_artifacts
            if isinstance(name, str)
            and (name.startswith(prefix) if isinstance(prefix, str) else name.startswith(prefix))
        ]
        artifact_percentages[target] = _set_contract_percentage(expected, actual)

    consumer_surfaces_by_target = surface_contract.get("consumer_surfaces_by_target", {})
    consumer_percentages: dict[str, float] = {}
    for target in ("cpp", "rust"):
        target_surface = (
            consumer_surfaces_by_target.get(target, {})
            if isinstance(consumer_surfaces_by_target, dict)
            else {}
        )
        if isinstance(target_surface, dict) and "required" in target_surface:
            consumer_percentages[target] = _set_contract_percentage(
                target_surface.get("required", []),
                target_surface.get("actual", []),
            )
        else:
            consumer_percentages[target] = _set_contract_percentage(
                surface_contract.get("required_consumer_surface_names", []),
                surface_contract.get("actual_consumer_surface_names", []),
            )
    contract_percentages: dict[str, dict[str, float]] = {}
    for target in ("cpp", "rust"):
        components = {
            "feature_domains": domain_percentages[target],
            "option_catalogs": generated_match_percentages[target],
            "option_entries": generated_match_percentages[target],
            "option_catalog_manifest": manifest_percentages[target],
            "option_catalog_values": manifest_value_percentages[target],
            "option_catalog_consumers": catalog_consumer_percentages[target],
            "config_keys": config_percentages[target],
            "generated_artifacts": artifact_percentages[target],
            "consumer_surfaces": consumer_percentages[target],
        }
        components["contract_surface_total"] = round(sum(components.values()) / len(components), 2)
        contract_percentages[target] = components

    standalone = payload.get("standalone_runtime_ready", {})
    full = payload.get("full_parity", {})
    return {
        "scope": "Feature, option, config, generated-contract, and consumer-surface equality; runtime promotion is separate.",
        "cpp": contract_percentages["cpp"],
        "rust": contract_percentages["rust"],
        "standalone_runtime": {
            "cpp": _percentage(1 if isinstance(standalone, dict) and bool(standalone.get("cpp")) else 0, 1),
            "rust": _percentage(1 if isinstance(standalone, dict) and bool(standalone.get("rust")) else 0, 1),
        },
        "full_parity": {
            "cpp": _percentage(1 if isinstance(full, dict) and bool(full.get("cpp")) else 0, 1),
            "rust": _percentage(1 if isinstance(full, dict) and bool(full.get("rust")) else 0, 1),
        },
        "generated_artifact_checks": {
            str(item.get("name")): bool(item.get("ok"))
            for item in generated
            if isinstance(item, dict) and item.get("name")
        },
        "option_catalog_count": option_catalog_count,
        "option_catalog_entry_count": option_entry_count,
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
        GeneratedArtifact(
            "rust_exchange_support_reference_fixture",
            RUST_EXCHANGE_SUPPORT_REFERENCE_OUTPUT,
            render_rust_exchange_support_reference_module(),
        ),
        GeneratedArtifact(
            "rust_portfolio_reference_fixture",
            RUST_PORTFOLIO_REFERENCE_OUTPUT,
            render_rust_portfolio_reference_module(),
        ),
        GeneratedArtifact("cpp_generated_contract", CPP_OUTPUT, render_cpp_header()),
        GeneratedArtifact(
            "cpp_indicator_reference_fixture",
            CPP_INDICATOR_REFERENCE_OUTPUT,
            render_cpp_indicator_reference_header(),
        ),
        GeneratedArtifact(
            "cpp_exchange_support_reference_fixture",
            CPP_EXCHANGE_SUPPORT_REFERENCE_OUTPUT,
            render_cpp_exchange_support_reference_header(),
        ),
        GeneratedArtifact(
            "cpp_portfolio_reference_fixture",
            CPP_PORTFOLIO_REFERENCE_OUTPUT,
            render_cpp_portfolio_reference_header(),
        ),
        GeneratedArtifact("tauri_browser_generated_contract", TAURI_BROWSER_OUTPUT, render_tauri_browser_contract()),
    )


def _consumer_requirements() -> tuple[ConsumerRequirement, ...]:
    return (
        ConsumerRequirement(
            "rust_startup_packaging_contract",
            REPO_ROOT / "experiments" / "rust-shells" / "src" / "main.rs",
            (
                "fn run_packaged_smoke()",
                "supported_frameworks()",
                "native_python_app_contract_parity_ready()",
                "rust_native_trading_runtime_ready()",
                "--smoke",
            ),
        ),
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
                "generated_python_parity::PYTHON_INDICATOR_MA_TYPE_OPTIONS",
                "generated_python_parity::PYTHON_LLM_PROVIDERS",
                "generated_python_parity::PYTHON_CONNECTOR_OPTIONS",
                "generated_python_parity::PYTHON_CODE_LANGUAGE_OPTIONS",
                "generated_python_parity::PYTHON_RUST_FRAMEWORK_OPTIONS",
                "generated_python_parity::PYTHON_STARTER_MARKET_OPTIONS",
                "generated_python_parity::PYTHON_BACKTEST_INTERVALS",
                "python_source_indicator_catalog",
                "python_source_indicator_ma_type_options",
                "python_source_llm_provider_keys",
                "python_source_connector_keys",
                "python_source_code_language_options",
                "python_source_rust_framework_options",
                "python_source_starter_market_options",
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
            "rust_native_portfolio_reconciliation_uses_python_missing_options",
            REPO_ROOT / "experiments" / "rust-shells" / "crates" / "core" / "src" / "portfolio.rs",
            (
                "pub struct MissingPositionPolicy",
                "pub struct MissingPositionReconciliationSummary",
                "pub fn reconcile_missing_position_state",
                "state.missing_counts",
                "state.pending_close_times",
                "state.pending_close_times.remove(&key)",
                "record.allocations = previous.allocations.clone()",
                "record.stop_loss_enabled = previous.stop_loss_enabled",
                "policy.autoclose",
                "parse_epoch_seconds",
            ),
        ),
        ConsumerRequirement(
            "rust_native_portfolio_reconciliation_uses_python_reference_fixture",
            REPO_ROOT / "experiments" / "rust-shells" / "crates" / "core" / "src" / "portfolio.rs",
            (
                "generated_python_portfolio_reference::PYTHON_PORTFOLIO_REFERENCE_JSON",
                "missing_position_reconciliation_matches_every_python_generated_reference_case",
                "fixture_state_value",
                "fixture_summary_value",
                "generated Python portfolio reference should be valid JSON",
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
                "PYTHON_STRATEGY_CONTROLS_REFERENCE_CASES",
                "PYTHON_STRATEGY_RISK_REFERENCE_CASES",
                "PYTHON_STRATEGY_RISK_LOOSE_REFERENCE_CASES",
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
            "rust_native_strategy_runtime_uses_python_interval_timing_fixture",
            REPO_ROOT / "experiments" / "rust-shells" / "crates" / "core" / "src" / "native_runtime.rs",
            (
                "PYTHON_INTERVAL_SECONDS_REFERENCE_JSON",
                "python_indicator_interval_seconds",
                "interval_seconds_value",
                "native_interval_timing_matches_python_reference_cases",
                "generated Python interval timing reference",
            ),
        ),
        ConsumerRequirement(
            "rust_native_indicator_runtime_uses_python_enabled_fixtures",
            REPO_ROOT / "experiments" / "rust-shells" / "crates" / "core" / "src" / "native_indicators.rs",
            (
                "PYTHON_INDICATOR_ENABLED_REFERENCE_JSON",
                "PYTHON_BACKTEST_INDICATOR_ENABLED_REFERENCE_JSON",
                "IndicatorEnableSemantics",
                "indicator_enabled",
                "compute_configured_indicator_series_with_semantics",
                "indicator_enabled_semantics_match_python_generated_reference",
            ),
        ),
        ConsumerRequirement(
            "rust_native_backtest_runtime_uses_python_reference_fixture",
            REPO_ROOT / "experiments" / "rust-shells" / "crates" / "core" / "src" / "backtest_runtime.rs",
            (
                "PYTHON_INDICATOR_REFERENCE_JSON",
                "compute_configured_indicator_series_with_semantics",
                "unsupported_enabled_indicator_keys_with_semantics",
                "IndicatorEnableSemantics::Backtest",
                "indicator_enabled",
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
                "indicator_enabled",
                "IndicatorEnableSemantics::Backtest",
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
            "rust_native_backtest_interval_timing_uses_python_reference_fixture",
            REPO_ROOT
            / "experiments"
            / "rust-shells"
            / "crates"
            / "core"
            / "src"
            / "market_data.rs",
            (
                "PYTHON_BACKTEST_INTERVAL_SECONDS_REFERENCE_JSON",
                "pub fn python_backtest_interval_seconds",
                "backtest_interval_seconds_match_python_generated_reference_cases",
                "generated Python backtest interval reference",
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
                "PYTHON_SUPPORTED_CONNECTOR_BACKENDS",
                "PYTHON_CCXT_DIAGNOSTIC_EXCHANGES",
                "PYTHON_CCXT_ORDER_ROUTING_EXCHANGES",
                "PYTHON_ORDER_EXECUTION_EXCHANGES",
                "PYTHON_CCXT_EXCHANGE_IDS",
                "canonical_broker_name",
                "build_exchange_support_payload",
            ),
        ),
        ConsumerRequirement(
            "rust_native_exchange_connectors_use_python_reference_fixture",
            REPO_ROOT / "experiments" / "rust-shells" / "crates" / "core" / "src" / "exchange_connectors.rs",
            (
                "crate::generated_python_exchange_support_reference::PYTHON_EXCHANGE_SUPPORT_REFERENCE_JSON",
                "exchange_support_cases",
                "support_payload_matches_every_generated_python_reference_case",
                "Rust exchange support payload diverged from Python case",
            ),
        ),
        ConsumerRequirement(
            "rust_native_runtime_ownership_uses_python_source_policy",
            REPO_ROOT / "experiments" / "rust-shells" / "apps" / "tauri-desktop" / "src" / "main.rs",
            (
                "PYTHON_NATIVE_RUNTIME_EXCHANGES",
                "PYTHON_NATIVE_RUNTIME_CONNECTOR_BACKENDS",
                "PYTHON_NATIVE_RUNTIME_CONNECTOR_MARKET_FAMILIES",
                "PYTHON_NATIVE_RUNTIME_INDICATOR_SOURCE_MARKET_FAMILIES",
                "PYTHON_NATIVE_RUNTIME_DELEGATED_OWNER",
                "native_runtime_ownership_error",
                "native_runtime_indicator_source_market_family",
                "native_runtime_market_poll_spec_for_config",
            ),
        ),
        ConsumerRequirement(
            "rust_native_runtime_ownership_uses_python_reference_fixture",
            REPO_ROOT / "experiments" / "rust-shells" / "apps" / "tauri-desktop" / "src" / "main.rs",
            (
                "PYTHON_NATIVE_RUNTIME_CONNECTOR_OWNERSHIP_REFERENCE_CASES",
                "native_runtime_connector_ownership_matches_python_reference_cases",
                "native_runtime_connector_input_is_owned",
            ),
        ),
        ConsumerRequirement(
            "rust_native_runtime_routing_uses_python_reference_fixture",
            REPO_ROOT / "experiments" / "rust-shells" / "apps" / "tauri-desktop" / "src" / "main.rs",
            (
                "PYTHON_NATIVE_RUNTIME_ROUTING_REFERENCE_CASES",
                "native_runtime_routing_matches_python_reference_cases",
                "native_runtime_routing_is_owned",
            ),
        ),
        ConsumerRequirement(
            "rust_native_runtime_mode_uses_python_source_policy",
            REPO_ROOT / "experiments" / "rust-shells" / "apps" / "tauri-desktop" / "src" / "main.rs",
            (
                "PYTHON_NATIVE_RUNTIME_TESTNET_MODE_MARKERS",
                "python_mode_uses_testnet",
            ),
        ),
        ConsumerRequirement(
            "rust_native_runtime_mode_uses_python_reference_fixture",
            REPO_ROOT / "experiments" / "rust-shells" / "apps" / "tauri-desktop" / "src" / "main.rs",
            (
                "PYTHON_NATIVE_RUNTIME_MODE_REFERENCE_CASES",
                "native_runtime_mode_mapping_matches_python_reference_cases",
                "python_mode_uses_testnet",
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
            "rust_order_guard_uses_python_live_safety_environment",
            REPO_ROOT / "experiments" / "rust-shells" / "crates" / "core" / "src" / "order_guard.rs",
            (
                "PYTHON_LIVE_TRADING_ENABLED_ENV",
                "PYTHON_LIVE_TRADING_ACK_ENV",
                "PYTHON_LIVE_TRADING_ACK_ENV_LEGACY",
                "PYTHON_LIVE_TRADING_MAX_LEVERAGE_ENV",
                "PYTHON_LIVE_TRADING_MAX_POSITION_PCT_ENV",
                "PYTHON_LIVE_TRADING_MAX_SESSION_ORDERS_ENV",
                "PYTHON_LIVE_SAFETY_ENV_TRUE_VALUES",
                "process_live_trading_environment",
                "validate_live_trading_safety_with_environment",
            ),
        ),
        ConsumerRequirement(
            "rust_order_guard_uses_python_order_intent_fixture",
            REPO_ROOT / "experiments" / "rust-shells" / "crates" / "core" / "src" / "order_guard.rs",
            (
                "PYTHON_ORDER_INTENT_REFERENCE_JSON",
                "order_intent_and_filter_validation_match_every_python_reference_case",
                "intent_bool_param",
                "filter_truthy_param",
                "validate_order_filter_constraints_with_raw_params",
            ),
        ),
        ConsumerRequirement(
            "rust_order_guard_uses_python_live_safety_fixture",
            REPO_ROOT / "experiments" / "rust-shells" / "crates" / "core" / "src" / "order_guard.rs",
            (
                "PYTHON_LIVE_SAFETY_REFERENCE_JSON",
                "live_safety_validation_matches_every_python_reference_case",
                "LiveTradingSafetyInput",
                "validate_live_trading_safety_with_environment",
            ),
        ),
        ConsumerRequirement(
            "rust_native_stop_intent_uses_python_reference_fixture",
            REPO_ROOT / "experiments" / "rust-shells" / "crates" / "core" / "src" / "runtime_control.rs",
            (
                "PYTHON_STOP_INTENT_REFERENCE_JSON",
                "PYTHON_STOP_INTENT_LOOSE_REFERENCE_JSON",
                "stop_intent_mapping_matches_python_reference_cases",
                "close_positions_from_python_config",
                "build_runtime_stop_guard_result",
            ),
        ),
        ConsumerRequirement(
            "rust_order_guard_uses_python_connector_health_fixture",
            REPO_ROOT / "experiments" / "rust-shells" / "crates" / "core" / "src" / "order_guard.rs",
            (
                "PYTHON_CONNECTOR_HEALTH_REFERENCE_JSON",
                "connector_health_validation_matches_every_python_reference_case",
                "validate_connector_health_errors",
            ),
        ),
        ConsumerRequirement(
            "rust_llm_output_policy_uses_python_reference_fixture",
            REPO_ROOT / "experiments" / "rust-shells" / "crates" / "core" / "src" / "llm_advisory.rs",
            (
                "PYTHON_LLM_OUTPUT_POLICY_REFERENCE_JSON",
                "output_policy_blocks_order_claims_and_risk_overrides",
                "llm_output_policy_violations",
            ),
        ),
        ConsumerRequirement(
            "rust_llm_chat_request_uses_python_reference_fixture",
            REPO_ROOT / "experiments" / "rust-shells" / "crates" / "core" / "src" / "llm_advisory.rs",
            (
                "PYTHON_LLM_CHAT_REQUEST_REFERENCE_JSON",
                "chat_request_serialization_matches_python_reference_cases",
                "build_llm_chat_request",
                "serde_json::to_value(request)",
            ),
        ),
        ConsumerRequirement(
            "rust_llm_dynamic_catalog_uses_python_sources",
            REPO_ROOT / "experiments" / "rust-shells" / "crates" / "core" / "src" / "llm_advisory.rs",
            (
                "model_suggestions_for_provider",
                "model_suggestions_for_provider_with_sources",
                "PYTHON_LLM_MODEL_CATALOG_PATH_ENV",
                "custom_models_env",
                "dynamic_catalog_environment_and_file_overrides_merge_like_python",
            ),
        ),
        ConsumerRequirement(
            "cpp_startup_packaging_contract",
            REPO_ROOT / "experiments" / "native-cpp" / "src" / "main.cpp",
            (
                "bool verifyBoundedSmokeWindow(TradingBotWindow &window)",
                "app.setApplicationName(\"Trading Bot\")",
                "TradingBotWindow window;",
                "window.showMaximized();",
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
                "PythonParityContract::kPythonCodeLanguageOptions",
                "PythonParityContract::kPythonRustFrameworkOptions",
                "PythonParityContract::kPythonStarterMarketOptions",
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
                "pythonSourceCodeLanguageOptionKeys",
                "pythonSourceRustFrameworkOptionKeys",
                "pythonSourceStarterMarketOptionKeys",
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
            "cpp_indicator_dialog_uses_python_ma_options",
            REPO_ROOT / "experiments" / "native-cpp" / "src" / "TradingBotWindow.dashboard_indicator_dialog.cpp",
            (
                '#include "generated/PythonParityContract.h"',
                "PythonParityContract::kPythonIndicatorMaTypeOptions",
                "pythonSourceMovingAverageTypeOptions",
            ),
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
                'QStringLiteral("llm_providers")',
                'QStringLiteral("llm_config")',
                'QStringLiteral("llm_prompt")',
                'QStringLiteral("llm_local_model_status")',
                'QStringLiteral("llm_local_model_start")',
                'QStringLiteral("llm_local_model_pull")',
                'QStringLiteral("llm_local_model_delete")',
            ),
            (
                "llm_providers",
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
            "cpp_llm_catalog_payload_fields_follow_python",
            REPO_ROOT / "experiments" / "native-cpp" / "src" / "TradingBotWindowSupport.cpp",
            (
                "mergePythonLlmProviderSpec",
                'QStringLiteral(\"default_base_url\")',
                'QStringLiteral(\"default_reasoning_effort\")',
                'QStringLiteral(\"model_suggestions\")',
                'QStringLiteral(\"reasoning_efforts\")',
                'QStringLiteral(\"custom_models_path_env\")',
                'QStringLiteral(\"catalog_note\")',
            ),
        ),
        ConsumerRequirement(
            "cpp_llm_dynamic_catalog_uses_python_sources",
            REPO_ROOT / "experiments" / "native-cpp" / "src" / "TradingBotWindowSupport.cpp",
            (
                "llmModelSuggestions",
                "appendLlmCatalogModels",
                "customModelsEnv",
                "customModelsPathEnv",
                "providers",
            ),
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
            "cpp_native_portfolio_reconciliation_uses_python_missing_options",
            REPO_ROOT / "experiments" / "native-cpp" / "src" / "TradingBotWindow.positions.cpp",
            (
                '#include "NativePortfolio.h"',
                "NativePortfolio::reconcileMissingPositionState",
                "positionsOpenRecords_",
                "positionsEntryAllocations_",
                "positionsMissingCounts_",
                "positionsPendingCloseTimes_",
                "positionsClosedHistory_",
                "NativePortfolio::applyCloseAllToPositionState",
                "serviceOpenRecords",
                "positionsOpenRecords_ = serviceOpenRecords",
                "positionsPendingCloseTimes_.insert(stateKey, closeTime)",
                "buildDashboardServiceConfigPatch",
            ),
        ),
        ConsumerRequirement(
            "cpp_native_portfolio_reconciliation_policy_uses_python_keys",
            REPO_ROOT / "experiments" / "native-cpp" / "src" / "NativePortfolio.cpp",
            (
                "reconcileMissingPositionState",
                "positions_missing_threshold",
                "positions_missing_grace_seconds",
                "positions_missing_autoclose",
                "pendingCloseTimes",
                "missingCounts",
            ),
        ),
        ConsumerRequirement(
            "cpp_native_portfolio_reconciliation_uses_python_reference_fixture",
            REPO_ROOT / "experiments" / "native-cpp" / "tests" / "NativeOrderSafetyTests.cpp",
            (
                '#include "../src/generated/PythonPortfolioReference.h"',
                "PythonPortfolioReference::kPythonSourceContractHash",
                "PythonPortfolioReference::kReferenceJson",
                "position_reconciliation_cases",
                "native C++ portfolio summary diverged from Python",
                "native C++ open portfolio state diverged from Python",
            ),
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
                "PythonParityContract::kPythonSupportedConnectorBackends",
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
            "cpp_native_exchange_connectors_use_python_reference_fixture",
            REPO_ROOT / "experiments" / "native-cpp" / "tests" / "NativeOrderSafetyTests.cpp",
            (
                '#include "../src/generated/PythonExchangeSupportReference.h"',
                "PythonExchangeSupportReference::kPythonSourceContractHash",
                "PythonExchangeSupportReference::kReferenceJson",
                "exchange_support_cases",
                "native C++ exchange support payload should exactly match Python case",
            ),
        ),
        ConsumerRequirement(
            "cpp_native_runtime_ownership_uses_python_source_policy",
            REPO_ROOT / "experiments" / "native-cpp" / "src" / "TradingBotWindowSupport.cpp",
            (
                "PythonParityContract::kPythonNativeRuntimeExchanges",
                "PythonParityContract::kPythonNativeRuntimeConnectorBackends",
                "PythonParityContract::kPythonNativeRuntimeConnectorMarketFamilies",
                "exchangeUsesBinanceApi",
                "connectorAllowedForAccount",
                "nativeRuntimeOwnsBinanceFuturesConnector",
            ),
        ),
        ConsumerRequirement(
            "cpp_native_runtime_ownership_uses_python_reference_fixture",
            REPO_ROOT / "experiments" / "native-cpp" / "tests" / "NativeServiceApiContractTests.cpp",
            (
                "PythonParityContract::kPythonNativeRuntimeConnectorOwnershipReferenceCases",
                "C++ native connector ownership should match Python",
                "nativeRuntimeOwnsBinanceFuturesConnector",
            ),
        ),
        ConsumerRequirement(
            "cpp_native_runtime_routing_uses_python_reference_fixture",
            REPO_ROOT / "experiments" / "native-cpp" / "tests" / "NativeServiceApiContractTests.cpp",
            (
                "PythonParityContract::kPythonNativeRuntimeRoutingReferenceCases",
                "C++ native runtime routing should match Python",
                "nativeRuntimeRoutingIsOwned",
            ),
        ),
        ConsumerRequirement(
            "cpp_native_runtime_mode_uses_python_source_policy",
            REPO_ROOT / "experiments" / "native-cpp" / "src" / "TradingBotWindowSupport.cpp",
            (
                "PythonParityContract::kPythonNativeRuntimeTestnetModeMarkers",
                "isTestnetModeLabel",
            ),
        ),
        ConsumerRequirement(
            "cpp_native_runtime_mode_uses_python_reference_fixture",
            REPO_ROOT / "experiments" / "native-cpp" / "tests" / "NativeServiceApiContractTests.cpp",
            (
                "PythonParityContract::kPythonNativeRuntimeModeReferenceCases",
                "C++ mode mapping should match Python",
                "isTestnetModeLabel",
            ),
        ),
        ConsumerRequirement(
            "cpp_native_indicator_source_uses_python_source_policy",
            REPO_ROOT
            / "experiments"
            / "native-cpp"
            / "src"
            / "TradingBotWindow.dashboard_runtime_internal.cpp",
            (
                "PythonParityContract::kPythonNativeRuntimeIndicatorSourceMarketFamilies",
                "nativeIndicatorMarketFamily",
                "normalizedIndicatorSourceKey",
            ),
        ),
        ConsumerRequirement(
            "cpp_native_indicator_runtime_uses_python_source_policy",
            REPO_ROOT / "experiments" / "native-cpp" / "src" / "TradingBotWindow.dashboard_runtime.cpp",
            (
                "nativeIndicatorMarketFamily",
                "indicatorUsesBinanceFutures",
                "indicatorUsesBinanceSpot",
                "indicatorMarketFamily",
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
            "cpp_native_strategy_runtime_uses_python_behavior_fixtures",
            REPO_ROOT / "experiments" / "native-cpp" / "tests" / "NativeOrderSafetyTests.cpp",
            (
                "PythonParityContract::kPythonStrategyControlsReferenceCases",
                "PythonParityContract::kPythonStrategyRiskReferenceCases",
                "PythonParityContract::kPythonStrategyRiskLooseReferenceCases",
                "NativeStrategyRuntime::normalizeStrategyControls",
                "NativeStrategyRuntime::normalizeStrategyRiskControls",
                "C++ strategy-control normalization should match Python",
                "C++ strategy-risk normalization should match Python",
            ),
        ),
        ConsumerRequirement(
            "cpp_native_strategy_runtime_uses_python_interval_timing_fixture",
            REPO_ROOT / "experiments" / "native-cpp" / "tests" / "NativeOrderSafetyTests.cpp",
            (
                "PythonParityContract::kPythonIntervalSecondsReferenceJson",
                "NativeStrategyRuntime::pythonIndicatorIntervalSeconds",
                "NativeStrategyRuntime::pythonLoopIntervalSeconds",
                "C++ indicator interval timing should match Python",
                "C++ loop interval timing should match Python",
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
                "PythonParityContract::kPythonIndicatorEnabledReferenceJson",
                "PythonParityContract::kPythonBacktestIndicatorEnabledReferenceJson",
                "NativeIndicatorRuntime::IndicatorEnableSemantics",
                "NativeIndicatorRuntime::isIndicatorEnabled",
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
            "cpp_native_backtest_interval_timing_uses_python_reference_fixture",
            REPO_ROOT / "experiments" / "native-cpp" / "tests" / "NativeOrderSafetyTests.cpp",
            (
                "PythonParityContract::kPythonBacktestIntervalSecondsReferenceJson",
                "NativeBacktestBatchRuntime::bufferedStartTimeMs",
                "C++ backtest interval timing should match Python",
                "generated Python backtest interval timing reference",
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
            "cpp_order_guard_uses_python_live_safety_environment",
            REPO_ROOT / "experiments" / "native-cpp" / "src" / "NativeOrderSafety.cpp",
            (
                "PythonParityContract::kPythonLiveTradingEnabledEnv",
                "PythonParityContract::kPythonLiveTradingAckEnv",
                "PythonParityContract::kPythonLiveTradingAckEnvLegacy",
                "PythonParityContract::kPythonLiveTradingMaxLeverageEnv",
                "PythonParityContract::kPythonLiveTradingMaxPositionPctEnv",
                "PythonParityContract::kPythonLiveTradingMaxSessionOrdersEnv",
                "PythonParityContract::kPythonLiveSafetyEnvironmentTrueValues",
                "generatedEnvValue",
                "liveTradingConfirmationPresent",
            ),
        ),
        ConsumerRequirement(
            "cpp_native_order_guard_uses_python_order_intent_fixture",
            REPO_ROOT / "experiments" / "native-cpp" / "tests" / "NativeOrderSafetyTests.cpp",
            (
                "PythonParityContract::kPythonOrderIntentReferenceJson",
                "C++ order-intent normalization should match Python",
                "C++ order-filter validation should match Python",
                "validateOrderFilterConstraintsWithRawParams",
            ),
        ),
        ConsumerRequirement(
            "cpp_native_order_guard_uses_python_live_safety_fixture",
            REPO_ROOT / "experiments" / "native-cpp" / "tests" / "NativeOrderSafetyTests.cpp",
            (
                "PythonParityContract::kPythonLiveSafetyReferenceJson",
                "C++ live-safety validation should match Python",
                "liveSafetyInputFromJson",
                "validateLiveTradingSafety",
            ),
        ),
        ConsumerRequirement(
            "cpp_native_stop_intent_uses_python_reference_fixture",
            REPO_ROOT / "experiments" / "native-cpp" / "tests" / "NativeOrderSafetyTests.cpp",
            (
                "PythonParityContract::kPythonStopIntentReferenceJson",
                "PythonParityContract::kPythonStopIntentLooseReferenceJson",
                "stop-intent mapping should match Python",
                "NativeOrderSafety::closePositionsFromPythonConfig",
                "buildRuntimeStopGuardResult",
            ),
        ),
        ConsumerRequirement(
            "cpp_dashboard_runtime_uses_python_stop_intent",
            REPO_ROOT / "experiments" / "native-cpp" / "src" / "TradingBotWindow.dashboard_runtime_lifecycle.cpp",
            (
                "NativeOrderSafety::closePositionsFromPythonConfig",
                "buildDashboardServiceConfigPatch",
                "stopRequest",
            ),
        ),
        ConsumerRequirement(
            "cpp_native_order_guard_uses_python_connector_health_fixture",
            REPO_ROOT / "experiments" / "native-cpp" / "tests" / "NativeOrderSafetyTests.cpp",
            (
                "PythonParityContract::kPythonConnectorHealthReferenceJson",
                "C++ connector-health validation should match Python",
                "validateConnectorHealthErrors",
            ),
        ),
        ConsumerRequirement(
            "cpp_llm_output_policy_uses_python_reference_fixture",
            REPO_ROOT / "experiments" / "native-cpp" / "tests" / "NativeOrderSafetyTests.cpp",
            (
                "PythonParityContract::kPythonLlmOutputPolicyReferenceJson",
                "C++ LLM output policy should match Python case",
                "NativeLlmAdvisory::outputPolicyViolations",
            ),
        ),
        ConsumerRequirement(
            "cpp_llm_chat_request_uses_python_reference_fixture",
            REPO_ROOT / "experiments" / "native-cpp" / "tests" / "NativeOrderSafetyTests.cpp",
            (
                "PythonParityContract::kPythonLlmChatRequestReferenceJson",
                "NativeLlmAdvisory::buildChatRequest",
                "C++ LLM request should match Python case",
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
            "tauri_native_runtime_ownership_uses_python_reference_fixture",
            REPO_ROOT
            / "experiments"
            / "rust-shells"
            / "apps"
            / "tauri-desktop"
            / "ui"
            / "tauri-ui-behavior.test.cjs",
            (
                "nativeRuntimeConnectorOwnershipReference",
                "connector ownership drifted for",
                "nativeRuntimeDelegationRequired",
            ),
        ),
        ConsumerRequirement(
            "tauri_native_runtime_mode_uses_python_reference_fixture",
            REPO_ROOT
            / "experiments"
            / "rust-shells"
            / "apps"
            / "tauri-desktop"
            / "ui"
            / "tauri-ui-behavior.test.cjs",
            (
                "nativeRuntimeModePolicy",
                "nativeRuntimeModeReference",
                "nativeRuntimeModeUsesTestnet",
                "mode mapping drifted for",
            ),
        ),
        ConsumerRequirement(
            "tauri_native_runtime_routing_uses_python_reference_fixture",
            REPO_ROOT
            / "experiments"
            / "rust-shells"
            / "apps"
            / "tauri-desktop"
            / "ui"
            / "tauri-ui-behavior.test.cjs",
            (
                "nativeRuntimeRoutingReference",
                "combined native routing drifted for",
                "nativeRuntimeDelegationRequired",
            ),
        ),
        ConsumerRequirement(
            "tauri_browser_consumes_generated_starter_catalogs",
            REPO_ROOT / "experiments" / "rust-shells" / "apps" / "tauri-desktop" / "ui" / "index.html",
            (
                "pythonParityContract.codeLanguageOptions",
                "pythonParityContract.rustFrameworkOptions",
                "pythonParityContract.starterMarketOptions",
                "normalizeStarterOption",
                "renderCodeLanguageCatalog",
                "appendStarterCard",
                "rustCodeLanguageKey",
            ),
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
            "tauri_llm_catalog_uses_python_source_route",
            REPO_ROOT / "experiments" / "rust-shells" / "apps" / "tauri-desktop" / "ui" / "index.html",
            (
                'id="refresh-llm-catalog-btn"',
                "const refreshLlmProviderCatalog",
                'serviceRequest("llm_providers", "GET")',
                "mergeLlmProviderSpec",
                "customModelsPathEnv",
                "defaultReasoningEffort",
            ),
            service_route_names=("llm_providers",),
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
                "margin_over_target_tolerance: config_f64(",
                'python_execution_default_f64("margin_over_target_tolerance", 0.05)',
                "margin_filter_slippage: config_f64(",
                'python_execution_default_f64("margin_filter_slippage", 0.1)',
                "engine.api_key.clear()",
                "engine.api_secret.clear()",
                "NativeRuntimeStreamWorker",
                "read_next_event_with_timeout",
                "native_runtime_stream_requested",
                "consume_native_runtime_stream",
                "merge_native_runtime_stream_candle",
                "stream_worker",
                "latest_stream_event",
                "stream_error",
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
            "tauri_native_runtime_poll_timing_uses_python_reference_fixture",
            REPO_ROOT / "experiments" / "rust-shells" / "apps" / "tauri-desktop" / "ui" / "index.html",
            (
                "pythonParityContract.intervalSecondsReference",
                "tauriUiBehavior.pythonLoopIntervalSeconds",
                "nativeRuntimeMarketPollIntervalMs",
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


def _option_catalog_manifest_contract() -> dict[str, object]:
    """Verify that every Python catalog is explicitly represented in each target."""
    manifest = _python_option_catalog_manifest()
    option_catalog_json = _python_option_catalog_json()
    expected_rust = [
        "PythonOptionCatalogManifestEntry {"
        f" name: {_rust_string(name)}, entry_count: {entry_count} }},"
        for name, entry_count in manifest
    ]
    expected_cpp = [
        "PythonOptionCatalogManifestEntry{"
        f"{_cpp_string(name)}, {entry_count} }},"
        for name, entry_count in manifest
    ]
    expected_browser = [
        f'"entryCount": {entry_count},\n      "name": {json.dumps(name)}'
        for name, entry_count in manifest
    ]
    expected_catalog_json = {
        "cpp": (
            "inline constexpr std::string_view kPythonOptionCatalogsJson = "
            f"{_cpp_string_chunks(option_catalog_json)};"
        ),
        "rust": (
            "pub const PYTHON_OPTION_CATALOGS_JSON: &str = "
            f"{_rust_string(option_catalog_json)};"
        ),
        "browser": f'"optionCatalogsJson": {json.dumps(option_catalog_json)}',
    }
    target_specs = {
        "cpp": (CPP_OUTPUT, expected_cpp),
        "rust": (RUST_OUTPUT, expected_rust),
        "browser": (TAURI_BROWSER_OUTPUT, expected_browser),
    }
    targets: dict[str, dict[str, object]] = {}
    issues: list[str] = []
    for target, (path, expected_lines) in target_specs.items():
        text = _read(path)
        missing = [line for line in expected_lines if line not in text]
        catalog_json_missing = expected_catalog_json[target] not in text
        report = {
            "path": str(path.relative_to(REPO_ROOT)),
            "expected_count": len(expected_lines),
            "missing": missing,
            "catalog_values_exact": not catalog_json_missing,
            "ok": not missing and not catalog_json_missing,
        }
        targets[target] = report
        issues.extend(f"{target}: missing option catalog manifest entry {line}" for line in missing)
        if catalog_json_missing:
            issues.append(f"{target}: missing exact serialized Python option catalog payload")
    return {
        "expected_count": len(manifest),
        "expected_entry_count": sum(entry_count for _, entry_count in manifest),
        "catalog_values_json": option_catalog_json,
        "catalog_names": [name for name, _ in manifest],
        "targets": targets,
        "ok": not issues,
        "issues": issues,
    }


def _catalog_suffix(name: str) -> str:
    return "".join(part[:1].upper() + part[1:] for part in name.split("_"))


OPTION_CATALOG_SUFFIX_OVERRIDES = {
    "intervals": "BacktestIntervals",
    "tradingview_interval_map": "TradingViewIntervalMap",
    "connectors": "ConnectorOptions",
    "indicators": "IndicatorCatalog",
    # Native code consumes the typed option entries; the Python key projection
    # remains a browser-only surface.
    "chart_view_keys": "ChartViewOptions",
}


OPTION_CATALOG_RUST_SUFFIX_OVERRIDES = {
    "intervals": "BACKTEST_INTERVALS",
    "tradingview_interval_map": "TRADINGVIEW_INTERVAL_MAP",
    "connectors": "CONNECTOR_OPTIONS",
    "indicators": "INDICATOR_CATALOG",
}


OPTION_CATALOG_BROWSER_PROPERTY_OVERRIDES = {
    "intervals": "backtestIntervals",
    "connectors": "connectorOptions",
    "indicators": "indicatorCatalog",
}


def _catalog_browser_property(name: str) -> str:
    override = OPTION_CATALOG_BROWSER_PROPERTY_OVERRIDES.get(name)
    if override:
        return override
    suffix = _catalog_suffix(name)
    return suffix[:1].lower() + suffix[1:]


def _catalog_consumer_text(paths: tuple[Path, ...], suffixes: tuple[str, ...]) -> str:
    chunks: list[str] = []
    for root in paths:
        candidates = [root] if root.is_file() else root.rglob("*")
        for path in candidates:
            if not path.is_file() or path.suffix not in suffixes:
                continue
            if "generated" in path.parts or path.name in {
                "generated_python_parity.rs",
                "generated-python-parity.js",
            }:
                continue
            chunks.append(_read(path))
    return "\n".join(chunks)


def _option_catalog_consumer_contract() -> dict[str, object]:
    """Require every applicable generated catalog to have a real consumer."""
    manifest = _python_option_catalog_manifest()
    catalog_names = [name for name, _ in manifest]
    target_specs = {
        "cpp": {
            "generated_path": CPP_OUTPUT,
            "consumer_text": _catalog_consumer_text(
                (REPO_ROOT / "experiments" / "native-cpp" / "src",),
                (".cpp", ".h"),
            ),
            "symbol": lambda name: f"kPython{OPTION_CATALOG_SUFFIX_OVERRIDES.get(name, _catalog_suffix(name))}",
            "consumer": lambda symbol: symbol,
            "not_applicable": {
                "rust_environment_dependencies": "Rust environment metadata is not a C++ runtime input.",
            },
        },
        "rust": {
            "generated_path": RUST_OUTPUT,
            "consumer_text": _catalog_consumer_text(
                (
                    REPO_ROOT / "experiments" / "rust-shells" / "crates" / "core" / "src",
                    REPO_ROOT / "experiments" / "rust-shells" / "apps" / "tauri-desktop" / "src",
                ),
                (".rs",),
            ),
            "symbol": lambda name: "PYTHON_" + OPTION_CATALOG_RUST_SUFFIX_OVERRIDES.get(
                name,
                name.upper(),
            ),
            "consumer": lambda symbol: symbol,
            "not_applicable": {
                "chart_view_keys": "Chart-view key filtering is owned by the Tauri browser bridge.",
            },
        },
        "browser": {
            "generated_path": TAURI_BROWSER_OUTPUT,
            "consumer_text": _catalog_consumer_text(
                (REPO_ROOT / "experiments" / "rust-shells" / "apps" / "tauri-desktop" / "ui",),
                (".html", ".js", ".cjs"),
            ),
            "symbol": lambda name: f'"{_catalog_browser_property(name)}"',
            "consumer": lambda symbol: f"pythonParityContract.{symbol[1:-1]}",
            "not_applicable": {},
        },
    }

    targets: dict[str, dict[str, object]] = {}
    issues: list[str] = []
    for target, spec in target_specs.items():
        generated_text = _read(spec["generated_path"])
        consumer_text = str(spec["consumer_text"])
        symbol_for = spec["symbol"]
        consumer_for = spec["consumer"]
        not_applicable = dict(spec["not_applicable"])
        catalog_reports: list[dict[str, object]] = []
        applicable_count = 0
        matched_count = 0
        for name in catalog_names:
            if name in not_applicable:
                catalog_reports.append(
                    {
                        "name": name,
                        "status": "not_applicable",
                        "reason": not_applicable[name],
                        "ok": True,
                    }
                )
                continue

            symbol = str(symbol_for(name))
            consumer_symbol = str(consumer_for(symbol))
            generated_present = symbol in generated_text
            consumer_references = consumer_text.count(consumer_symbol)
            catalog_ok = generated_present and consumer_references > 0
            applicable_count += 1
            if catalog_ok:
                matched_count += 1
            catalog_reports.append(
                {
                    "name": name,
                    "status": "covered" if catalog_ok else "missing_consumer",
                    "symbol": symbol,
                    "consumer_symbol": consumer_symbol,
                    "generated_present": generated_present,
                    "consumer_references": consumer_references,
                    "ok": catalog_ok,
                }
            )
            if not generated_present:
                issues.append(f"{target}: {name} is missing generated symbol {symbol}")
            if consumer_references <= 0:
                issues.append(f"{target}: {name} has no consumer reference for {consumer_symbol}")

        targets[target] = {
            "generated_path": _rel(spec["generated_path"]),
            "catalog_count": len(catalog_names),
            "applicable_count": applicable_count,
            "not_applicable_count": len(catalog_names) - applicable_count,
            "covered_count": matched_count,
            "coverage_percent": _percentage(matched_count, applicable_count),
            "catalogs": catalog_reports,
            "ok": matched_count == applicable_count,
        }

    return {
        "scope": "Every Python option catalog must have a generated target representation and an applicable consumer.",
        "catalog_count": len(catalog_names),
        "catalog_names": catalog_names,
        "targets": targets,
        "ok": not issues,
        "issues": issues,
    }


def _feature_option_contract() -> dict[str, object]:
    """Report the Python-owned feature and option surface independently of runtime promotion."""
    payload = native_python_source_contract_payload()
    domains = list(payload["domains"])
    option_catalogs = dict(payload["ui_options"])
    option_catalog_entry_counts = {
        name: len(value) if isinstance(value, (dict, list, tuple)) else 1
        for name, value in option_catalogs.items()
    }
    domain_contract_parity = {
        "cpp": all(bool(domain["cpp_full_parity"]) for domain in domains),
        "rust": all(bool(domain["rust_full_parity"]) for domain in domains),
    }
    generated_artifact_reports = {
        artifact.name: _check_generated_artifact(
            artifact,
            native_python_source_contract_hash(),
        )
        for artifact in _generated_artifacts()
    }
    native_generated_artifact_names = {
        "cpp": tuple(
            name
            for name in generated_artifact_reports
            if name.startswith("cpp_")
        ),
        "rust": tuple(
            name
            for name in generated_artifact_reports
            if name.startswith("rust_") or name.startswith("tauri_")
        ),
    }
    generated_native_contracts_match_python = {
        side: all(
            bool(generated_artifact_reports[name]["ok"])
            for name in artifact_names
        )
        for side, artifact_names in native_generated_artifact_names.items()
    }
    option_catalog_manifest = _option_catalog_manifest_contract()
    option_catalog_consumers = _option_catalog_consumer_contract()
    return {
        "scope": "Python feature and option contract/catalog equality plus applicable generated-catalog consumer coverage; standalone runtime promotion is reported separately.",
        "feature_domain_count": len(domains),
        "feature_domain_contract_parity": domain_contract_parity,
        "option_catalog_count": len(option_catalogs),
        "option_catalog_entry_count": sum(option_catalog_entry_counts.values()),
        "option_catalog_entry_counts": option_catalog_entry_counts,
        "option_catalog_names": sorted(option_catalogs),
        "option_catalog_manifest": option_catalog_manifest,
        "option_catalog_consumers": option_catalog_consumers,
        "generated_native_contracts_match_python": generated_native_contracts_match_python,
        "generated_native_contract_artifacts": {
            side: list(artifact_names)
            for side, artifact_names in native_generated_artifact_names.items()
        },
        "ok": all(domain_contract_parity.values())
        and all(generated_native_contracts_match_python.values())
        and bool(option_catalog_manifest["ok"])
        and bool(option_catalog_consumers["ok"]),
    }


def audit_native_source_sync() -> dict[str, object]:
    contract_hash = native_python_source_contract_hash()
    generated_artifact_requirements = _generated_artifacts()
    consumer_requirements = _consumer_requirements()
    consumers = [_check_consumer(requirement) for requirement in consumer_requirements]
    surface_contract = _surface_contract(
        generated_artifact_requirements,
        consumer_requirements,
        consumers,
    )
    config_key_contract = _config_key_contract()
    feature_option_contract = _feature_option_contract()
    payload = native_python_source_contract_payload()
    domain_evidence = _domain_evidence_contract(payload, consumers)
    feature_option_contract["domain_evidence_contract"] = domain_evidence
    feature_option_contract["ok"] = bool(feature_option_contract["ok"]) and bool(domain_evidence["ok"])
    generated = [
        _check_generated_artifact(artifact, contract_hash)
        for artifact in generated_artifact_requirements
    ]
    parity_percentages = _native_contract_percentages(
        native_python_source_contract_payload(),
        feature_option_contract,
        config_key_contract,
        surface_contract,
        generated,
        domain_evidence,
    )
    surface_contract_issues = [str(issue) for issue in surface_contract["issues"]]
    surface_wiring_issues = [
        f"{item['path']}: {item.get('issue') or 'missing consumer wiring'}"
        for item in [*generated, *consumers]
        if not bool(item["ok"])
    ]
    issues = [*surface_contract_issues, *surface_wiring_issues]
    issues.extend(str(issue) for issue in config_key_contract["issues"])
    if not bool(feature_option_contract["ok"]):
        issues.append("Python feature or option contract/catalog parity failed")
    option_catalog_manifest = feature_option_contract.get("option_catalog_manifest", {})
    if isinstance(option_catalog_manifest, dict) and not bool(option_catalog_manifest.get("ok")):
        issues.extend(str(issue) for issue in option_catalog_manifest.get("issues", []))
    option_catalog_consumers = feature_option_contract.get("option_catalog_consumers", {})
    if isinstance(option_catalog_consumers, dict) and not bool(option_catalog_consumers.get("ok")):
        issues.extend(str(issue) for issue in option_catalog_consumers.get("issues", []))
    if not bool(domain_evidence["ok"]):
        issues.extend(str(issue) for issue in domain_evidence["issues"])
    return {
        "ok": not issues,
        "contract_hash": contract_hash,
        "source": "Languages/Python/app/native_parity.py",
        "surface_contract": surface_contract,
        "config_key_contract": config_key_contract,
        "feature_option_contract": feature_option_contract,
        "domain_evidence_contract": domain_evidence,
        "parity_percentages": parity_percentages,
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
