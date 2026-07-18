"""
Python-owned native parity contract for C++ and Rust destinations.

This module is intentionally data-oriented.  It defines the Python source
surface that native destinations must track before they can honestly claim
contract parity with the Python application. Standalone product/runtime parity
is stricter and remains false until native runtimes have matching execution
ownership plus external evidence.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
from hashlib import sha256
import json
from typing import Any

from .gui.code.code_language_catalog import EXCHANGE_PATHS, STARTER_CRYPTO_EXCHANGES
from .gui.backtest.backtest_templates import BACKTEST_TEMPLATE_DEFINITIONS
from .gui.runtime.composition.module_state_constants import (
    ACCOUNT_MODE_OPTIONS,
    BACKTEST_INTERVAL_ORDER,
    CHART_MARKET_OPTIONS,
    DASHBOARD_LOOP_CHOICES,
    DEFAULT_CHART_SYMBOLS,
    LEAD_TRADER_OPTIONS,
    MDD_LOGIC_LABELS,
    SIDE_LABELS,
    STOP_LOSS_MODE_LABELS,
    STOP_LOSS_SCOPE_LABELS,
    TRADINGVIEW_INTERVAL_MAP,
    _connector_options,
)
from .gui.runtime.ui.theme_styles import DESIGN_OPTIONS
from .integrations.llm.providers import _PROVIDER_SPECS
from .service.api_contract import (
    SERVICE_API_ROUTE_METHODS,
    SERVICE_API_ROUTE_PATHS,
    SERVICE_API_ROUTE_SUFFIXES,
    SERVICE_BACKTEST_RUN_REQUEST_FIELDS,
    service_api_contract_payload,
)
from .settings.backtest import BacktestSettings
from .settings.execution import ExecutionSettings
from .settings.indicators import (
    INDICATOR_CATALOG,
    build_backtest_indicator_defaults,
    build_runtime_indicator_defaults,
)
from .settings.validation import (
    _ACCOUNT_TYPE_CHOICES,
    _BACKTEST_EXECUTION_BACKEND_CHOICES,
    _CHART_VIEW_MODE_CHOICES,
    _LOGIC_CHOICES,
    _MARGIN_MODE_CHOICES,
    _OPTIMIZER_METRIC_CHOICES,
    _OPTIMIZER_MODE_CHOICES,
    _ORDER_TYPE_CHOICES,
    _POSITION_MODE_CHOICES,
    _SCAN_SCOPE_CHOICES,
    _TIF_CHOICES,
)


NATIVE_PARITY_SCHEMA_VERSION = 1
NATIVE_PARITY_SOURCE = "Languages/Python"
CPP_STANDALONE_RUNTIME_READY = False
RUST_STANDALONE_RUNTIME_READY = False

CONFIG_MODE_OPTIONS = ("Live", "Demo", "Testnet")
THEME_OPTIONS = ("Light", "Dark", "Blue", "Yellow", "Green", "Red")
INDICATOR_SOURCE_OPTIONS = (
    "Binance spot",
    "Binance futures",
    "Bybit",
)
LLM_USE_FOR_OPTIONS = (
    ("Advisory", "advisory"),
    ("Signal confirmation", "signal_confirmation"),
    ("Risk review", "risk_review"),
    ("Backtest explanation", "backtest_explanation"),
)
DASHBOARD_STRATEGY_TEMPLATE_DEFINITIONS = {
    "": {"label": "No Template"},
    "top10": {"label": "Top 10 %2 per trade 1x Isolated"},
    "top50": {"label": "Top 50 %2 per trade 1x"},
    "top100": {"label": "Top 100 %1 per trade 1x"},
}

# Exchange order requests must be structurally safe in every mode. Live mode
# adds credential acknowledgement and session budget gates; it does not own the
# basic request, filter, connector, or audit validation contract.
ORDER_GUARD_BEHAVIOR = {
    "validate_intent_all_modes": True,
    "validate_exchange_filters_all_modes": True,
    "validate_connector_health_all_modes": True,
    "validate_audit_enabled_all_modes": True,
    "validate_audit_writable_all_modes": True,
    "live_only_requirements": (
        "credentials",
        "live_acknowledgement",
        "session_order_cap",
        "session_order_count_increment",
    ),
}

# Canonical runtime-series keys for every user-selectable indicator.  Python's
# chart, backtest, and native destinations consume these names, so emit them
# with the catalog instead of maintaining separate C++ and Rust switch lists.
INDICATOR_RUNTIME_OUTPUT_KEYS: dict[str, tuple[str, ...]] = {
    "ma": ("ma",),
    "donchian": ("donchian_high", "donchian_low", "donchian"),
    "psar": ("psar",),
    "bb": ("bb_upper", "bb_mid", "bb_lower"),
    "bbw": ("bbw",),
    "keltner": ("keltner_upper", "keltner_mid", "keltner_lower"),
    "ichimoku": (
        "ichimoku_tenkan", "ichimoku_kijun", "ichimoku_span_a",
        "ichimoku_span_b", "ichimoku_chikou", "ichimoku",
    ),
    "rsi": ("rsi",),
    "volume": ("volume",),
    "obv": ("obv",),
    "rvol": ("rvol",),
    "cmf": ("cmf",),
    "cci": ("cci",),
    "roc": ("roc",),
    "trix": ("trix",),
    "ppo": ("ppo", "ppo_signal", "ppo_hist"),
    "ao": ("ao",),
    "kst": ("kst", "kst_signal", "kst_hist"),
    "aroon": ("aroon_up", "aroon_down", "aroon"),
    "chop": ("chop",),
    "atr": ("atr",),
    "natr": ("natr",),
    "vwap": ("vwap",),
    "mfi": ("mfi",),
    "stoch_rsi": ("stoch_rsi", "stoch_rsi_k", "stoch_rsi_d"),
    "willr": ("willr",),
    "macd": ("macd_line", "macd_signal"),
    "uo": ("uo",),
    "adx": ("adx",),
    "dmi": ("dmi_plus", "dmi_minus", "dmi"),
    "supertrend": ("supertrend",),
    "ema": ("ema",),
    "stochastic": ("stochastic", "stochastic_k", "stochastic_d"),
}


@dataclass(frozen=True, slots=True)
class NativeParityDomain:
    key: str
    title: str
    python_surface: str
    cpp_required_before_full_parity: tuple[str, ...]
    rust_required_before_full_parity: tuple[str, ...]
    cpp_full_parity: bool = False
    rust_full_parity: bool = False


NATIVE_PARITY_DOMAINS: tuple[NativeParityDomain, ...] = (
    NativeParityDomain(
        key="desktop_shell_and_tabs",
        title="Desktop shell and primary tabs",
        python_surface="Dashboard, Chart, Positions, Backtest, Liquidation Heatmap, Code Languages, startup composition, theme, and live tab wiring.",
        cpp_required_before_full_parity=(
        ),
        rust_required_before_full_parity=(
        ),
        cpp_full_parity=True,
        rust_full_parity=True,
    ),
    NativeParityDomain(
        key="service_api_contract",
        title="Service API contract",
        python_surface="Canonical /api/v1 routes, methods, schemas, dashboard stream, auth, control-plane state, and desktop bridge contract.",
        cpp_required_before_full_parity=(),
        rust_required_before_full_parity=(),
        cpp_full_parity=True,
        rust_full_parity=True,
    ),
    NativeParityDomain(
        key="config_persistence",
        title="Config persistence and hydration",
        python_surface="Runtime config, file save/load, dirty state, dashboard hydration, service snapshots, and secret redaction.",
        cpp_required_before_full_parity=(),
        rust_required_before_full_parity=(),
        cpp_full_parity=True,
        rust_full_parity=True,
    ),
    NativeParityDomain(
        key="strategy_runtime",
        title="Strategy runtime and signal generation",
        python_surface="Indicator computation, strategy cycles, signal generation, live candle options, override tables, and worker lifecycle.",
        cpp_required_before_full_parity=(
        ),
        rust_required_before_full_parity=(
        ),
        cpp_full_parity=True,
        rust_full_parity=True,
    ),
    NativeParityDomain(
        key="exchange_connectors",
        title="Exchange connectors and market data",
        python_surface="Binance SDK/connector/CCXT/python-binance selection, connector support metadata, transport diagnostics, rate limits, REST market data, and WebSocket paths.",
        cpp_required_before_full_parity=(),
        rust_required_before_full_parity=(),
        cpp_full_parity=True,
        rust_full_parity=True,
    ),
    NativeParityDomain(
        key="account_portfolio_positions",
        title="Account, portfolio, and positions",
        python_surface="Account snapshots, portfolio summaries, futures position queries, close-all behavior, position history, allocation tracking, and reconciliation.",
        cpp_required_before_full_parity=(),
        rust_required_before_full_parity=(),
        cpp_full_parity=True,
        rust_full_parity=True,
    ),
    NativeParityDomain(
        key="order_execution_and_risk",
        title="Order execution, audit, and risk",
        python_surface="Order sizing, submit guards, audit logs, position gates, close-opposite logic, stop-loss scopes, live safety preflight, circuit breaker, and shutdown guards.",
        cpp_required_before_full_parity=(),
        rust_required_before_full_parity=(),
        cpp_full_parity=True,
        rust_full_parity=True,
    ),
    NativeParityDomain(
        key="backtest_engine",
        title="Backtest engine, optimizer, and scanner",
        python_surface="Backtest engine, optimizer limits/results, live parity request shape, scanner polling, dashboard import, indicator selection, and provenance.",
        cpp_required_before_full_parity=(),
        rust_required_before_full_parity=(),
        cpp_full_parity=True,
        rust_full_parity=True,
    ),
    NativeParityDomain(
        key="charts_and_heatmaps",
        title="Charts and liquidation heatmaps",
        python_surface="TradingView, lightweight chart assets, candlestick fallback, chart state payloads, browser guards, and liquidation provider panels.",
        cpp_required_before_full_parity=(),
        rust_required_before_full_parity=(),
        cpp_full_parity=True,
        rust_full_parity=True,
    ),
    NativeParityDomain(
        key="logs_terminal_diagnostics",
        title="Logs, terminal, and diagnostics",
        python_surface="Service logs, dashboard logs, terminal command execution, exception diagnostics, secret redaction, and test runner/reporting flows.",
        cpp_required_before_full_parity=(),
        rust_required_before_full_parity=(),
        cpp_full_parity=True,
        rust_full_parity=True,
    ),
    NativeParityDomain(
        key="llm_advisory",
        title="LLM advisory and local model lifecycle",
        python_surface="Provider catalogs, privacy flags, advisory prompt execution, config persistence, local Ollama status/start/pull/delete, and redacted output.",
        cpp_required_before_full_parity=(),
        rust_required_before_full_parity=(),
        cpp_full_parity=True,
        rust_full_parity=True,
    ),
    NativeParityDomain(
        key="startup_packaging_platform",
        title="Startup, packaging, and platform integration",
        python_surface="Product entrypoints, startup splash/suppression, Windows taskbar metadata, PyInstaller packaging, service wrappers, and release smoke tests.",
        cpp_required_before_full_parity=(),
        rust_required_before_full_parity=(),
        cpp_full_parity=True,
        rust_full_parity=True,
    ),
)


def _domain_payload(domain: NativeParityDomain) -> dict[str, Any]:
    return asdict(domain)


def _indicator_payload() -> list[dict[str, object]]:
    runtime_defaults = build_runtime_indicator_defaults()
    backtest_defaults = build_backtest_indicator_defaults()
    catalog_keys = {definition.key for definition in INDICATOR_CATALOG}
    output_keys = set(INDICATOR_RUNTIME_OUTPUT_KEYS)
    if catalog_keys != output_keys:
        missing = ", ".join(sorted(catalog_keys - output_keys))
        unexpected = ", ".join(sorted(output_keys - catalog_keys))
        raise RuntimeError(
            "INDICATOR_RUNTIME_OUTPUT_KEYS must exactly match INDICATOR_CATALOG "
            f"(missing: {missing or '-'}; unexpected: {unexpected or '-'})"
        )
    return [
        {
            "key": definition.key,
            "display_name": definition.display_name,
            "default_enabled": bool(runtime_defaults.get(definition.key, {}).get("enabled")),
            # Native destinations need the canonical runtime parameters as well as the
            # display catalog. Keep this JSON-shaped so new Python-only parameters do
            # not require a parallel destination schema migration.
            "runtime_config": runtime_defaults.get(definition.key, {}),
            # Backtest thresholds and signal/filter modes intentionally differ from
            # live runtime defaults. Native engines must consume these values rather
            # than silently inventing destination-specific behavior.
            "backtest_config": backtest_defaults.get(definition.key, {}),
            "runtime_output_keys": list(INDICATOR_RUNTIME_OUTPUT_KEYS[definition.key]),
        }
        for definition in INDICATOR_CATALOG
    ]


def _llm_provider_payload() -> list[dict[str, object]]:
    return [
        {
            "key": provider.key,
            "label": provider.label,
            "mode": provider.mode,
            "protocol": provider.protocol,
            "default_base_url": provider.default_base_url,
            "default_model": provider.default_model,
            "api_key_env": provider.api_key_env,
            "model_suggestions": list(provider.model_suggestions),
            "reasoning_efforts": list(provider.reasoning_efforts),
            "default_reasoning_effort": provider.default_reasoning_effort,
        }
        for provider in _PROVIDER_SPECS
    ]


def _label_map_payload(values: dict[str, str]) -> list[dict[str, str]]:
    return [
        {"key": str(key), "label": str(label)}
        for key, label in values.items()
    ]


def _choice_payload(values: list[tuple[str, str]] | tuple[tuple[str, str], ...]) -> list[dict[str, str]]:
    return [
        {"label": str(label), "key": str(key), "value": str(key)}
        for label, key in values
    ]


def _canonical_choice_payload(values: dict[str, str]) -> list[dict[str, str]]:
    seen = set()
    result = []
    for value in values.values():
        if value in seen:
            continue
        seen.add(value)
        result.append({"key": str(value), "value": str(value), "label": str(value)})
    return result


def _fixed_choice_payload(values: list[tuple[str, str]] | tuple[tuple[str, str], ...]) -> list[dict[str, str]]:
    return [
        {"key": str(key), "value": str(key), "label": str(label)}
        for key, label in values
    ]


def _value_option_payload(values: tuple[str, ...] | list[str]) -> list[dict[str, str]]:
    return [
        {"key": str(value), "value": str(value), "label": str(value)}
        for value in values
    ]


def _exchange_payload() -> list[dict[str, object]]:
    return [
        {
            "key": str(option["key"]),
            "label": (
                f"{option['title']} ({option['badge']})"
                if option.get("badge")
                else str(option["title"])
            ),
            "title": str(option["title"]),
            "badge": str(option.get("badge") or ""),
            "disabled": bool(option.get("disabled", False)),
        }
        for option in STARTER_CRYPTO_EXCHANGES
        if option["key"] in EXCHANGE_PATHS
    ]


def native_python_source_contract_payload() -> dict[str, Any]:
    route_methods = {
        name: list(methods)
        for name, methods in SERVICE_API_ROUTE_METHODS.items()
    }
    connector_options = [
        {"label": label, "key": key}
        for label, key in _connector_options()
    ]
    execution_defaults = ExecutionSettings()
    backtest_defaults = BacktestSettings()
    cpp_contract_parity = all(domain.cpp_full_parity for domain in NATIVE_PARITY_DOMAINS)
    rust_contract_parity = all(domain.rust_full_parity for domain in NATIVE_PARITY_DOMAINS)
    return {
        "schema_version": NATIVE_PARITY_SCHEMA_VERSION,
        "source": NATIVE_PARITY_SOURCE,
        "contract_parity": {
            "cpp": cpp_contract_parity,
            "rust": rust_contract_parity,
        },
        "standalone_runtime_ready": {
            "cpp": CPP_STANDALONE_RUNTIME_READY,
            "rust": RUST_STANDALONE_RUNTIME_READY,
        },
        "full_parity": {
            "cpp": cpp_contract_parity and CPP_STANDALONE_RUNTIME_READY,
            "rust": rust_contract_parity and RUST_STANDALONE_RUNTIME_READY,
        },
        "order_guard_behavior": {
            **ORDER_GUARD_BEHAVIOR,
            "live_only_requirements": list(ORDER_GUARD_BEHAVIOR["live_only_requirements"]),
        },
        "domains": [_domain_payload(domain) for domain in NATIVE_PARITY_DOMAINS],
        "service_api": {
            **service_api_contract_payload(),
            "route_suffixes": dict(SERVICE_API_ROUTE_SUFFIXES),
            "route_methods": route_methods,
            "backtest_run_request_fields": list(SERVICE_BACKTEST_RUN_REQUEST_FIELDS),
        },
        "ui_options": {
            "intervals": list(BACKTEST_INTERVAL_ORDER),
            "tradingview_interval_map": dict(TRADINGVIEW_INTERVAL_MAP),
            "default_chart_symbols": list(DEFAULT_CHART_SYMBOLS),
            "default_execution_symbols": list(execution_defaults.symbols),
            "default_execution_intervals": list(execution_defaults.intervals),
            "default_backtest_symbols": list(backtest_defaults.symbols),
            "default_backtest_intervals": list(backtest_defaults.intervals),
            "chart_market_options": list(CHART_MARKET_OPTIONS),
            "account_mode_options": list(ACCOUNT_MODE_OPTIONS),
            "config_mode_options": _value_option_payload(list(CONFIG_MODE_OPTIONS)),
            "theme_options": _value_option_payload(list(THEME_OPTIONS)),
            "design_options": _value_option_payload(list(DESIGN_OPTIONS)),
            "indicator_source_options": _value_option_payload(list(INDICATOR_SOURCE_OPTIONS)),
            "exchange_options": _exchange_payload(),
            "dashboard_loop_choices": _choice_payload(DASHBOARD_LOOP_CHOICES),
            "lead_trader_options": _choice_payload(LEAD_TRADER_OPTIONS),
            "llm_use_for_options": _choice_payload(LLM_USE_FOR_OPTIONS),
            "dashboard_strategy_templates": [
                {"key": key, "label": str(definition.get("label", key))}
                for key, definition in DASHBOARD_STRATEGY_TEMPLATE_DEFINITIONS.items()
            ],
            "side_options": _label_map_payload(SIDE_LABELS),
            "account_type_options": _canonical_choice_payload(_ACCOUNT_TYPE_CHOICES),
            "margin_mode_options": _canonical_choice_payload(_MARGIN_MODE_CHOICES),
            "position_mode_options": _canonical_choice_payload(_POSITION_MODE_CHOICES),
            "assets_mode_options": [
                {"key": "Single-Asset", "value": "Single-Asset", "label": "Single-Asset Mode"},
                {"key": "Multi-Assets", "value": "Multi-Assets", "label": "Multi-Assets Mode"},
            ],
            "order_type_options": _canonical_choice_payload(_ORDER_TYPE_CHOICES),
            "time_in_force_options": _canonical_choice_payload(_TIF_CHOICES),
            "signal_logic_options": _canonical_choice_payload(_LOGIC_CHOICES),
            "mdd_logic_options": _label_map_payload(MDD_LOGIC_LABELS),
            "stop_loss_modes": _label_map_payload(STOP_LOSS_MODE_LABELS),
            "stop_loss_scopes": _label_map_payload(STOP_LOSS_SCOPE_LABELS),
            "scan_scope_options": _canonical_choice_payload(_SCAN_SCOPE_CHOICES),
            "optimizer_mode_options": _canonical_choice_payload(_OPTIMIZER_MODE_CHOICES),
            "optimizer_metric_options": _canonical_choice_payload(_OPTIMIZER_METRIC_CHOICES),
            "backtest_execution_backend_options": _canonical_choice_payload(
                _BACKTEST_EXECUTION_BACKEND_CHOICES
            ),
            "chart_view_options": _fixed_choice_payload(
                (
                    ("tradingview", "TradingView"),
                    ("original", "Original"),
                    ("lightweight", "TradingView Lightweight"),
                )
            ),
            "positions_view_options": _fixed_choice_payload(
                (
                    ("cumulative", "Cumulative View"),
                    ("per_trade", "Per Trade View"),
                )
            ),
            "chart_view_keys": list(dict.fromkeys(_CHART_VIEW_MODE_CHOICES.values())),
            "connectors": connector_options,
            "backtest_templates": [
                {"key": key, "label": str(definition.get("label", key))}
                for key, definition in BACKTEST_TEMPLATE_DEFINITIONS.items()
            ],
            "indicators": _indicator_payload(),
        },
        "default_execution": execution_defaults.to_config_dict(),
        "default_backtest": backtest_defaults.to_config_dict(),
        "llm_providers": _llm_provider_payload(),
    }


def native_python_source_contract_json() -> str:
    return json.dumps(
        native_python_source_contract_payload(),
        ensure_ascii=True,
        sort_keys=True,
        separators=(",", ":"),
    )


def native_python_source_contract_hash() -> str:
    return sha256(native_python_source_contract_json().encode("utf-8")).hexdigest()


def native_python_source_contract_summary() -> dict[str, object]:
    payload = native_python_source_contract_payload()
    service_routes = [
        {
            "name": name,
            "path": SERVICE_API_ROUTE_PATHS[name],
            "methods": list(SERVICE_API_ROUTE_METHODS[name]),
        }
        for name in SERVICE_API_ROUTE_SUFFIXES
    ]
    route_schemas = payload["service_api"]["route_schemas"]
    service_route_schemas = [
        {
            "name": name,
            "query_fields": list(route_schemas[name]["query_fields"]),
            "request_fields": list(route_schemas[name]["request_fields"]),
            "response_fields": list(route_schemas[name]["response_fields"]),
        }
        for name in SERVICE_API_ROUTE_SUFFIXES
    ]
    return {
        "schema_version": payload["schema_version"],
        "source": payload["source"],
        "contract_hash": native_python_source_contract_hash(),
        "order_guard_behavior": dict(payload["order_guard_behavior"]),
        "domains": list(payload["domains"]),
        "domain_keys": [domain["key"] for domain in payload["domains"]],
        "route_names": list(SERVICE_API_ROUTE_SUFFIXES),
        "service_routes": service_routes,
        "service_route_schemas": service_route_schemas,
        "backtest_run_request_fields": list(SERVICE_BACKTEST_RUN_REQUEST_FIELDS),
        "indicators": list(payload["ui_options"]["indicators"]),
        "indicator_keys": [definition.key for definition in INDICATOR_CATALOG],
        "connectors": list(payload["ui_options"]["connectors"]),
        "llm_providers": list(payload["llm_providers"]),
        "llm_provider_keys": [provider.key for provider in _PROVIDER_SPECS],
        "connector_keys": [key for _label, key in _connector_options()],
        "intervals": list(BACKTEST_INTERVAL_ORDER),
        "tradingview_interval_map": dict(payload["ui_options"]["tradingview_interval_map"]),
        "default_chart_symbols": list(payload["ui_options"]["default_chart_symbols"]),
        "default_execution_symbols": list(payload["ui_options"]["default_execution_symbols"]),
        "default_execution_intervals": list(payload["ui_options"]["default_execution_intervals"]),
        "default_backtest_symbols": list(payload["ui_options"]["default_backtest_symbols"]),
        "default_backtest_intervals": list(payload["ui_options"]["default_backtest_intervals"]),
        "chart_market_options": list(payload["ui_options"]["chart_market_options"]),
        "account_mode_options": list(payload["ui_options"]["account_mode_options"]),
        "config_mode_options": list(payload["ui_options"]["config_mode_options"]),
        "theme_options": list(payload["ui_options"]["theme_options"]),
        "design_options": list(payload["ui_options"]["design_options"]),
        "indicator_source_options": list(payload["ui_options"]["indicator_source_options"]),
        "exchange_options": list(payload["ui_options"]["exchange_options"]),
        "dashboard_loop_choices": list(payload["ui_options"]["dashboard_loop_choices"]),
        "lead_trader_options": list(payload["ui_options"]["lead_trader_options"]),
        "llm_use_for_options": list(payload["ui_options"]["llm_use_for_options"]),
        "dashboard_strategy_templates": list(payload["ui_options"]["dashboard_strategy_templates"]),
        "side_options": list(payload["ui_options"]["side_options"]),
        "account_type_options": list(payload["ui_options"]["account_type_options"]),
        "margin_mode_options": list(payload["ui_options"]["margin_mode_options"]),
        "position_mode_options": list(payload["ui_options"]["position_mode_options"]),
        "assets_mode_options": list(payload["ui_options"]["assets_mode_options"]),
        "order_type_options": list(payload["ui_options"]["order_type_options"]),
        "time_in_force_options": list(payload["ui_options"]["time_in_force_options"]),
        "signal_logic_options": list(payload["ui_options"]["signal_logic_options"]),
        "mdd_logic_options": list(payload["ui_options"]["mdd_logic_options"]),
        "stop_loss_modes": list(payload["ui_options"]["stop_loss_modes"]),
        "stop_loss_scopes": list(payload["ui_options"]["stop_loss_scopes"]),
        "scan_scope_options": list(payload["ui_options"]["scan_scope_options"]),
        "optimizer_mode_options": list(payload["ui_options"]["optimizer_mode_options"]),
        "optimizer_metric_options": list(payload["ui_options"]["optimizer_metric_options"]),
        "backtest_execution_backend_options": list(
            payload["ui_options"]["backtest_execution_backend_options"]
        ),
        "chart_view_options": list(payload["ui_options"]["chart_view_options"]),
        "positions_view_options": list(payload["ui_options"]["positions_view_options"]),
        "chart_view_keys": list(payload["ui_options"]["chart_view_keys"]),
        "backtest_templates": list(payload["ui_options"]["backtest_templates"]),
        "default_execution": dict(payload["default_execution"]),
        "default_backtest": dict(payload["default_backtest"]),
        "cpp_contract_parity": payload["contract_parity"]["cpp"],
        "rust_contract_parity": payload["contract_parity"]["rust"],
        "cpp_standalone_runtime_ready": payload["standalone_runtime_ready"]["cpp"],
        "rust_standalone_runtime_ready": payload["standalone_runtime_ready"]["rust"],
        "cpp_full_parity": payload["full_parity"]["cpp"],
        "rust_full_parity": payload["full_parity"]["rust"],
    }
