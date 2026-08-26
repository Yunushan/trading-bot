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
from copy import deepcopy
from datetime import datetime, timezone
from hashlib import sha256
import json
import re
from typing import Any

from .gui.code.code_language_catalog import (
    EXCHANGE_PATHS,
    RUST_FRAMEWORK_OPTIONS,
    STARTER_CRYPTO_EXCHANGES,
    STARTER_LANGUAGE_OPTIONS,
    STARTER_MARKET_OPTIONS,
    _rust_dependency_targets_for_config,
)
from .core.backtest.indicator_selection_runtime import _enabled as backtest_indicator_enabled
from .gui.backtest.backtest_templates import BACKTEST_TEMPLATE_DEFINITIONS
from .native_interval_semantics import (
    backtest_interval_seconds,
    interval_seconds,
    interval_seconds_value,
)
from .gui.runtime.composition.module_state_constants import (
    ACCOUNT_MODE_OPTIONS,
    BACKTEST_INTERVAL_ORDER,
    CHART_MARKET_OPTIONS,
    DASHBOARD_LOOP_CHOICES,
    DEFAULT_CHART_SYMBOLS,
    FUTURES_CONNECTOR_KEYS,
    LEAD_TRADER_OPTIONS,
    MDD_LOGIC_LABELS,
    SIDE_LABELS,
    SPOT_CONNECTOR_KEYS,
    STOP_LOSS_MODE_LABELS,
    STOP_LOSS_SCOPE_LABELS,
    TRADINGVIEW_INTERVAL_MAP,
    _connector_options,
)
from .gui.runtime.strategy import controls_format_runtime, controls_shared_runtime
from .gui.runtime.ui.theme_styles import DESIGN_OPTIONS
from .integrations.llm.clients import build_llm_chat_request, llm_output_policy_violations
from .integrations.llm.providers import (
    LLM_API_STYLE_OPTIONS,
    LLM_MODEL_CATALOG_PATH_ENV,
    LLM_PROVIDER_CATALOG_REVISION,
    LLM_SPEED_OPTIONS,
    _PROVIDER_SPECS,
    llm_provider_choices,
)
from .integrations.llm.local_models import ollama_model_size_catalog
from .service.api_contract import (
    SERVICE_API_ROUTE_METHODS,
    SERVICE_API_ROUTE_PATHS,
    SERVICE_API_ROUTE_SUFFIXES,
    SERVICE_BACKTEST_RUN_REQUEST_FIELDS,
    service_api_contract_payload,
)
from .service.config_store import REMOTE_SERVICE_CONFIG_PROTECTED_FIELDS
from .settings.backtest import BacktestSettings, MDD_LOGIC_OPTIONS
from .settings.connectors import DEFAULT_INDICATOR_SOURCE
from .settings.execution import ExecutionSettings
from .settings.exchange_support import (
    BROKER_INTEGRATION_DISPOSITIONS,
    BROKER_MARKET_SCOPES,
    BROKER_ORDER_ROUTING_BACKENDS,
    CCXT_DIAGNOSTIC_EXCHANGES,
    CCXT_EXCHANGE_IDS,
    CCXT_ORDER_ROUTING_EXCHANGES,
    METATRADER5_BROKER_ALIASES,
    ORDER_EXECUTION_EXCHANGES,
    REQUESTED_BROKER_TARGETS,
    SUPPORTED_CONNECTOR_BACKENDS,
    SUPPORTED_EXCHANGES,
    SUPPORTED_BROKERS,
    SUPPORTED_FOREX_BROKERS,
    canonical_broker_name,
)
from .settings.indicators import (
    INDICATOR_CATALOG,
    MOVING_AVERAGE_TYPE_OPTIONS,
    build_backtest_indicator_defaults,
    build_runtime_indicator_defaults,
)
from .settings.live_safety import (
    BINANCE_MAX_FUTURES_LEVERAGE,
    LIVE_TRADING_ACK_ENV,
    LIVE_TRADING_ACK_ENV_LEGACY,
    LIVE_TRADING_ACKNOWLEDGEMENT,
    LIVE_TRADING_ENABLED_ENV,
    LIVE_TRADING_MAX_LEVERAGE_ENV,
    LIVE_TRADING_MAX_POSITION_PCT_ENV,
    LIVE_TRADING_MAX_SESSION_ORDERS_ENV,
    LiveTradingSafetyError,
    validate_live_trading_safety,
)
from .settings.risk import (
    RiskManagementSettings,
    STOP_LOSS_MODE_ORDER,
    STOP_LOSS_SCOPE_OPTIONS,
    coerce_bool,
    normalize_stop_loss_dict,
)
from .gui.shared.helper_runtime import _normalize_connector_backend
from .settings.ui import DEFAULT_DESIGN, DEFAULT_SELECTED_EXCHANGE, DEFAULT_THEME
from .settings.validation import (
    _ACCOUNT_MODE_CHOICES,
    _ACCOUNT_TYPE_CHOICES,
    _ASSETS_MODE_CHOICES,
    _BACKTEST_EXECUTION_BACKEND_CHOICES,
    _CHART_VIEW_MODE_CHOICES,
    _LLM_REASONING_EFFORT_CHOICES,
    _LLM_USE_FOR_CHOICES,
    _LOGIC_CHOICES,
    _MARGIN_MODE_CHOICES,
    _OPTIMIZER_METRIC_CHOICES,
    _OPTIMIZER_MODE_CHOICES,
    _ORDER_TYPE_CHOICES,
    _POSITION_MODE_CHOICES,
    _SCAN_SCOPE_CHOICES,
    _SIDE_CHOICES,
    _TIF_CHOICES,
    ConfigValidationError,
    validate_runtime_config,
)


NATIVE_PARITY_SCHEMA_VERSION = 1
NATIVE_PARITY_SOURCE = "Languages/Python"
CPP_STANDALONE_RUNTIME_READY = False
RUST_STANDALONE_RUNTIME_READY = False
NATIVE_POSITION_RECONCILIATION_REFERENCE_SCHEMA_VERSION = 1

CONFIG_MODE_OPTIONS = ("Live", "Demo", "Testnet")
THEME_OPTIONS = ("Light", "Dark", "Blue", "Yellow", "Green", "Red")
INDICATOR_SOURCE_OPTIONS = (
    "Binance spot",
    "Binance futures",
)
_COERCE_BOOL_PROBE_VALUES = ("1", "true", "yes", "on", "y")
PYTHON_COERCE_BOOL_TRUE_VALUES = tuple(
    value for value in _COERCE_BOOL_PROBE_VALUES if coerce_bool(value, False)
)

# Native shells must derive their direct-execution boundary from Python as well
# as their option catalogs. Anything outside this deliberately small surface is
# coordinated by the Python Service API/provider connector until native runtime
# promotion has matching implementation and external evidence.
_NATIVE_RUNTIME_CONNECTOR_BACKEND_ORDER = (
    "binance-sdk-derivatives-trading-usds-futures",
    "binance-sdk-derivatives-trading-coin-futures",
    "binance-sdk-spot",
    "binance-connector",
    "ccxt",
    "python-binance",
)


def _native_runtime_connector_market_families() -> tuple[tuple[str, str], ...]:
    """Project Python's account connector filters into native market families."""

    mappings: list[tuple[str, str]] = []
    for backend in _NATIVE_RUNTIME_CONNECTOR_BACKEND_ORDER:
        if backend == "binance-sdk-derivatives-trading-coin-futures":
            mappings.append((backend, "coin-m-futures"))
        elif backend in FUTURES_CONNECTOR_KEYS:
            mappings.append((backend, "usd-m-futures"))
        if backend in SPOT_CONNECTOR_KEYS:
            mappings.append((backend, "spot"))
    return tuple(mappings)


_NATIVE_RUNTIME_CONNECTOR_BACKENDS = tuple(
    backend
    for backend in _NATIVE_RUNTIME_CONNECTOR_BACKEND_ORDER
    if backend in FUTURES_CONNECTOR_KEYS or backend in SPOT_CONNECTOR_KEYS
)


NATIVE_RUNTIME_OWNERSHIP = {
    "direct_exchanges": ("Binance",),
    "direct_connector_backends": _NATIVE_RUNTIME_CONNECTOR_BACKENDS,
    "direct_market_families": (
        "usd-m-futures",
        "coin-m-futures",
        "spot",
    ),
    "native_execution_scope": "binance-spot-usds-and-coin-futures",
    "native_execution_capability": True,
    "direct_connector_market_families": _native_runtime_connector_market_families(),
    "indicator_source_market_families": (
        ("binance_spot", "spot"),
        ("binance_futures", "usd-m-futures"),
        ("spot", "spot"),
        ("futures", "usd-m-futures"),
    ),
    "delegated_owner": "Python Service API/provider connector",
}

NATIVE_RUNTIME_TESTNET_MODE_MARKERS = ("demo", "test", "sandbox")


def native_runtime_mode_is_testnet(value: object) -> bool:
    """Mirror Python's Binance mode-to-testnet URL selection policy."""

    text = str(value or "").lower()
    return any(marker in text for marker in NATIVE_RUNTIME_TESTNET_MODE_MARKERS)


def native_runtime_mode_reference_cases() -> list[dict[str, object]]:
    """Expose representative and adversarial mode strings to native targets."""

    raw_cases = (
        ("empty-live", ""),
        ("live", "Live"),
        ("production", "Production"),
        ("demo", "Demo"),
        ("demo-testnet", "Demo/Testnet"),
        ("testnet", "Testnet"),
        ("sandbox", "Sandbox"),
        ("embedded-test-marker", "contest"),
        ("embedded-demo-marker", "my-demo-mode"),
        ("paper-local", "Paper Local"),
        ("trimmed-testnet", "  Testnet  "),
    )
    return [
        {
            "name": name,
            "input": input_value,
            "expected_testnet": native_runtime_mode_is_testnet(input_value),
        }
        for name, input_value in raw_cases
    ]


def native_runtime_connector_input_is_owned(value: object) -> bool:
    """Return whether native code may handle a connector input directly.

    Connector normalization is intentionally permissive for configuration
    persistence, but runtime ownership is fail-closed. Unknown text must not
    silently become a Binance REST request just because normalization falls
    back to the USD-M default.
    """

    raw = str(value or "").strip()
    if not raw:
        return True

    normalized = _normalize_connector_backend(raw)
    direct_backends = set(NATIVE_RUNTIME_OWNERSHIP["direct_connector_backends"])
    if normalized not in direct_backends:
        return False

    raw_folded = raw.casefold()
    for label, key in _connector_options():
        if str(key).casefold() != raw_folded and str(label).casefold() != raw_folded:
            continue
        return key in direct_backends

    # Non-default normalized aliases are explicit native identities. The
    # default backend needs an additional identity check to reject unknown
    # providers that Python's configuration normalizer maps to USD-M.
    default_backend = str(NATIVE_RUNTIME_OWNERSHIP["direct_connector_backends"][0])
    if normalized != default_backend:
        return True

    text = raw.casefold()
    return text == "binance_sdk_derivatives_trading_usds_futures" or (
        "sdk" in text
        and "future" in text
        and ("usd" in text or "usds" in text)
    )


def native_runtime_connector_ownership_reference_cases() -> list[dict[str, object]]:
    """Expose Python's native connector ownership boundary to native targets."""

    labels_by_key = {key: label for label, key in _connector_options()}
    raw_cases = (
        ("empty-default", ""),
        ("usds-key", "binance-sdk-derivatives-trading-usds-futures"),
        ("usds-underscore-alias", "binance_sdk_derivatives_trading_usds_futures"),
        ("usds-label", labels_by_key["binance-sdk-derivatives-trading-usds-futures"]),
        ("usds-readable-alias", "Binance SDK USD-M Futures"),
        ("coin-key", "binance-sdk-derivatives-trading-coin-futures"),
        ("spot-key", "binance-sdk-spot"),
        ("binance-connector-key", "binance-connector"),
        ("ccxt-label", labels_by_key["ccxt"]),
        ("python-binance-label", labels_by_key["python-binance"]),
        ("oanda-provider-option", labels_by_key["oanda-rest"]),
        ("custom-provider", "custom"),
        ("unknown-provider", "unknown backend"),
        ("connector-url-alias", "https://connector.example.test/api"),
    )
    return [
        {
            "name": name,
            "input": input_value,
            "expected_owned": native_runtime_connector_input_is_owned(input_value),
        }
        for name, input_value in raw_cases
    ]


def _native_runtime_indicator_source_key(value: object) -> str:
    """Normalize indicator-source labels and keys for the native routing gate."""

    normalized = re.sub(r"[^a-z0-9]+", "_", str(value or "").strip().casefold())
    return normalized.strip("_")


def native_runtime_routing_is_owned(config: object) -> bool:
    """Return whether Python allows native handling for one runtime config."""

    source = config if isinstance(config, dict) else {}
    selected_exchange = str(
        source.get("selected_exchange") or NATIVE_RUNTIME_OWNERSHIP["direct_exchanges"][0]
    ).strip()
    direct_exchanges = {
        str(exchange).casefold() for exchange in NATIVE_RUNTIME_OWNERSHIP["direct_exchanges"]
    }
    if selected_exchange.casefold() not in direct_exchanges:
        return False
    if not native_runtime_connector_input_is_owned(source.get("connector_backend", "")):
        return False

    indicator_source = source.get("indicator_source")
    if isinstance(indicator_source, (list, tuple)):
        indicator_source = indicator_source[0] if indicator_source else None
    if indicator_source is None or not str(indicator_source).strip():
        return True

    direct_sources = {
        _native_runtime_indicator_source_key(key)
        for key, _market_family in NATIVE_RUNTIME_OWNERSHIP["indicator_source_market_families"]
    }
    direct_sources.update(
        _native_runtime_indicator_source_key(label) for label in INDICATOR_SOURCE_OPTIONS
    )
    return _native_runtime_indicator_source_key(indicator_source) in direct_sources


def native_runtime_routing_reference_cases() -> list[dict[str, object]]:
    """Expose combined exchange/connector/indicator routing decisions to native targets."""

    raw_cases = (
        ("binance-default", "Binance", "", ""),
        (
            "binance-usds-canonical",
            "Binance",
            "binance-sdk-derivatives-trading-usds-futures",
            "binance_futures",
        ),
        (
            "binance-usds-label",
            "Binance",
            "Binance SDK Derivatives Trading USD-M Futures (Official Recommended)",
            "Binance futures",
        ),
        (
            "binance-coin-futures",
            "Binance",
            "binance-sdk-derivatives-trading-coin-futures",
            "",
        ),
        ("binance-spot", "Binance", "binance-sdk-spot", "Binance spot"),
        ("non-native-exchange", "Bybit", "binance-sdk-spot", "Binance spot"),
        ("non-native-connector", "Binance", "OANDA REST-v20", "Binance spot"),
        ("unknown-connector", "Binance", "unknown backend", "Binance spot"),
        ("non-native-indicator", "Binance", "binance-sdk-spot", "TradingView"),
        ("indicator-key-alias", "Binance", "binance-sdk-spot", "spot"),
        ("indicator-punctuation-alias", "Binance", "binance-sdk-spot", "Binance/futures"),
        ("empty-indicator", "Binance", "binance-sdk-spot", ""),
        ("empty-exchange-default", "", "binance-sdk-spot", "Binance spot"),
        ("whitespace-exchange-rejected", "   ", "binance-sdk-spot", "Binance spot"),
        ("exchange-display-badge-rejected", "Binance (official)", "binance-sdk-spot", "Binance spot"),
    )
    return [
        {
            "name": name,
            "selected_exchange": selected_exchange,
            "connector_backend": connector_backend,
            "indicator_source": indicator_source,
            "expected_owned": native_runtime_routing_is_owned(
                {
                    "selected_exchange": selected_exchange,
                    "connector_backend": connector_backend,
                    "indicator_source": indicator_source,
                }
            ),
        }
        for name, selected_exchange, connector_backend, indicator_source in raw_cases
    ]


def native_runtime_routing_json_coercion_reference_cases() -> list[dict[str, object]]:
    """Expose Python JSON truthiness/string coercion at the native routing boundary."""

    raw_cases = (
        (
            "numeric-connector",
            {
                "selected_exchange": "Binance",
                "connector_backend": 1,
                "indicator_source": "Binance spot",
            },
            False,
        ),
        (
            "empty-connector-list",
            {
                "selected_exchange": "Binance",
                "connector_backend": [],
                "indicator_source": "Binance spot",
            },
            True,
        ),
        (
            "nonempty-connector-list",
            {
                "selected_exchange": "Binance",
                "connector_backend": ["binance-sdk-spot"],
                "indicator_source": "Binance spot",
            },
            True,
        ),
        (
            "numeric-exchange",
            {"selected_exchange": 1, "connector_backend": "binance-sdk-spot"},
            False,
        ),
        (
            "empty-exchange-list-default",
            {"selected_exchange": [], "connector_backend": "binance-sdk-spot"},
            True,
        ),
        (
            "nonempty-exchange-list",
            {"selected_exchange": ["Binance"], "connector_backend": "binance-sdk-spot"},
            False,
        ),
        (
            "numeric-indicator",
            {
                "selected_exchange": "Binance",
                "connector_backend": "binance-sdk-spot",
                "indicator_source": 1,
            },
            False,
        ),
        (
            "false-indicator",
            {
                "selected_exchange": "Binance",
                "connector_backend": "binance-sdk-spot",
                "indicator_source": False,
            },
            False,
        ),
        (
            "null-indicator",
            {
                "selected_exchange": "Binance",
                "connector_backend": "binance-sdk-spot",
                "indicator_source": None,
            },
            True,
        ),
        (
            "empty-indicator-list",
            {
                "selected_exchange": "Binance",
                "connector_backend": "binance-sdk-spot",
                "indicator_source": [],
            },
            True,
        ),
        (
            "numeric-first-indicator-list",
            {
                "selected_exchange": "Binance",
                "connector_backend": "binance-sdk-spot",
                "indicator_source": [0],
            },
            False,
        ),
        (
            "false-exchange-default",
            {"selected_exchange": False, "connector_backend": "binance-sdk-spot"},
            True,
        ),
    )
    cases: list[dict[str, object]] = []
    for name, config, expected in raw_cases:
        actual = native_runtime_routing_is_owned(config)
        if actual != expected:
            raise AssertionError(
                f"Python routing JSON coercion fixture is inconsistent for {name}: "
                f"expected {expected!r}, got {actual!r}"
            )
        cases.append(
            {
                "name": name,
                "config": config,
                "expected_owned": actual,
            }
        )
    return cases


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
    "live_safety_environment": {
        "enabled": LIVE_TRADING_ENABLED_ENV,
        "acknowledgement": LIVE_TRADING_ACK_ENV,
        "legacy_acknowledgement": LIVE_TRADING_ACK_ENV_LEGACY,
        "max_leverage": LIVE_TRADING_MAX_LEVERAGE_ENV,
        "max_position_pct": LIVE_TRADING_MAX_POSITION_PCT_ENV,
        "max_session_orders": LIVE_TRADING_MAX_SESSION_ORDERS_ENV,
    },
    "environment_bool_true_values": PYTHON_COERCE_BOOL_TRUE_VALUES,
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
        "ichimoku_tenkan",
        "ichimoku_kijun",
        "ichimoku_span_a",
        "ichimoku_span_b",
        "ichimoku_chikou",
        "ichimoku",
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
            "cpp_support_consumes_generated_contract",
            "cpp_support_exposes_generated_contract",
            "cpp_dashboard_uses_python_source_surface",
            "cpp_indicator_dialog_uses_python_ma_options",
            "cpp_chart_uses_python_source_surface",
            "cpp_native_chart_heatmap_uses_python_source_surface",
            "cpp_positions_uses_python_source_surface",
        ),
        rust_required_before_full_parity=(
            "rust_core_consumes_generated_contract",
            "tauri_browser_consumes_generated_contract",
            "tauri_browser_consumes_generated_starter_catalogs",
            "tauri_environment_versions_browser_bridge",
        ),
        cpp_full_parity=True,
        rust_full_parity=True,
    ),
    NativeParityDomain(
        key="service_api_contract",
        title="Service API contract",
        python_surface="Canonical /api/v1 routes, methods, schemas, dashboard stream, auth, control-plane state, and desktop bridge contract.",
        cpp_required_before_full_parity=(
            "cpp_support_consumes_generated_contract",
            "cpp_support_exposes_generated_contract",
            "cpp_backtest_service_api_uses_python_source_routes",
            "cpp_dashboard_llm_service_api_uses_python_source_routes",
            "cpp_config_service_api_uses_python_source_routes",
            "cpp_code_terminal_uses_python_service_api",
            "cpp_account_uses_python_service_api",
        ),
        rust_required_before_full_parity=(
            "rust_core_consumes_generated_contract",
            "tauri_browser_service_api_uses_python_source_routes",
            "tauri_llm_catalog_uses_python_source_route",
            "tauri_dashboard_stream_backend_uses_python_source_route",
            "tauri_dashboard_stream_browser_bridge",
        ),
        cpp_full_parity=True,
        rust_full_parity=True,
    ),
    NativeParityDomain(
        key="config_persistence",
        title="Config persistence and hydration",
        python_surface="Runtime config, file save/load, dirty state, dashboard hydration, service snapshots, and secret redaction.",
        cpp_required_before_full_parity=(
            "cpp_config_persistence_uses_python_source_options",
            "cpp_config_service_api_uses_python_source_routes",
        ),
        rust_required_before_full_parity=(
            "rust_config_persistence_uses_python_source_options",
        ),
        cpp_full_parity=True,
        rust_full_parity=True,
    ),
    NativeParityDomain(
        key="strategy_runtime",
        title="Strategy runtime and signal generation",
        python_surface="Indicator computation, strategy cycles, signal generation, live candle options, override tables, and worker lifecycle.",
        cpp_required_before_full_parity=(
            "cpp_native_indicator_source_uses_python_source_policy",
            "cpp_native_indicator_runtime_uses_python_source_policy",
            "cpp_native_indicator_runtime_uses_python_reference_fixture",
            "cpp_native_strategy_runtime_uses_python_source_options",
            "cpp_native_strategy_runtime_uses_python_live_signal_fixture",
            "cpp_native_strategy_runtime_uses_python_behavior_fixtures",
            "cpp_native_strategy_runtime_uses_python_interval_timing_fixture",
            "cpp_dashboard_runtime_uses_native_indicator_strategy_pipeline",
        ),
        rust_required_before_full_parity=(
            "rust_core_consumes_generated_contract",
            "rust_strategy_runtime_uses_python_source_options",
            "rust_native_strategy_runtime_uses_python_live_signal_fixture",
            "rust_native_strategy_runtime_uses_python_interval_timing_fixture",
            "tauri_native_runtime_poll_timing_uses_python_reference_fixture",
        ),
        cpp_full_parity=True,
        rust_full_parity=True,
    ),
    NativeParityDomain(
        key="exchange_connectors",
        title="Exchange connectors and market data",
        python_surface="Binance SDK/connector/CCXT/python-binance selection, connector support metadata, transport diagnostics, rate limits, REST market data, and WebSocket paths.",
        cpp_required_before_full_parity=(
            "cpp_native_exchange_connectors_use_python_source_connectors",
            "cpp_native_exchange_connectors_use_python_reference_fixture",
            "cpp_native_runtime_ownership_uses_python_source_policy",
        ),
        rust_required_before_full_parity=(
            "rust_native_exchange_connectors_use_python_source_connectors",
            "rust_native_exchange_connectors_use_python_reference_fixture",
            "rust_native_runtime_ownership_uses_python_source_policy",
        ),
        cpp_full_parity=True,
        rust_full_parity=True,
    ),
    NativeParityDomain(
        key="account_portfolio_positions",
        title="Account, portfolio, and positions",
        python_surface="Account snapshots, portfolio summaries, futures position queries, close-all behavior, position history, allocation tracking, and reconciliation.",
        cpp_required_before_full_parity=(
            "cpp_account_uses_python_service_api",
            "cpp_native_portfolio_reconciliation_uses_python_missing_options",
            "cpp_native_portfolio_reconciliation_policy_uses_python_keys",
            "cpp_native_portfolio_reconciliation_uses_python_reference_fixture",
        ),
        rust_required_before_full_parity=(
            "rust_native_account_runtime_is_present",
            "rust_native_portfolio_reconciliation_uses_python_missing_options",
            "rust_native_portfolio_reconciliation_uses_python_reference_fixture",
        ),
        cpp_full_parity=True,
        rust_full_parity=True,
    ),
    NativeParityDomain(
        key="order_execution_and_risk",
        title="Order execution, audit, and risk",
        python_surface="Order sizing, submit guards, audit logs, position gates, close-opposite logic, stop-loss scopes, live safety preflight, circuit breaker, and shutdown guards.",
        cpp_required_before_full_parity=(
            "python_order_guard_implements_behavior_contract",
            "cpp_order_guard_uses_python_behavior_contract",
            "cpp_order_guard_uses_python_live_safety_environment",
            "cpp_native_order_guard_uses_python_order_intent_fixture",
            "cpp_native_order_guard_uses_python_connector_health_fixture",
            "cpp_native_stop_intent_uses_python_reference_fixture",
            "cpp_dashboard_runtime_uses_python_stop_intent",
            "cpp_dashboard_runtime_enforces_live_order_safety",
        ),
        rust_required_before_full_parity=(
            "python_order_guard_implements_behavior_contract",
            "rust_order_guard_uses_python_behavior_contract",
            "rust_order_guard_uses_python_live_safety_environment",
            "rust_order_guard_uses_python_order_intent_fixture",
            "rust_order_guard_uses_python_connector_health_fixture",
            "rust_native_stop_intent_uses_python_reference_fixture",
        ),
        cpp_full_parity=True,
        rust_full_parity=True,
    ),
    NativeParityDomain(
        key="backtest_engine",
        title="Backtest engine, optimizer, and scanner",
        python_surface="Backtest engine, optimizer limits/results, live parity request shape, scanner polling, dashboard import, indicator selection, and provenance.",
        cpp_required_before_full_parity=(
            "cpp_backtest_uses_python_source_surface",
            "cpp_native_backtest_pair_overrides_match_python",
            "cpp_native_backtest_runtime_uses_python_reference_fixture",
            "cpp_native_backtest_interval_timing_uses_python_reference_fixture",
            "cpp_backtest_service_api_uses_python_source_routes",
        ),
        rust_required_before_full_parity=(
            "rust_native_backtest_runtime_uses_python_reference_fixture",
            "rust_native_backtest_batch_runtime_uses_python_reference_fixture",
            "rust_native_backtest_interval_timing_uses_python_reference_fixture",
            "tauri_native_backtest_bridge",
            "tauri_native_backtest_commands_registered",
            "tauri_native_backtest_browser_bridge",
        ),
        cpp_full_parity=True,
        rust_full_parity=True,
    ),
    NativeParityDomain(
        key="charts_and_heatmaps",
        title="Charts and liquidation heatmaps",
        python_surface="TradingView, lightweight chart assets, candlestick fallback, chart state payloads, browser guards, and liquidation provider panels.",
        cpp_required_before_full_parity=(
            "cpp_chart_uses_python_source_surface",
            "cpp_native_chart_heatmap_uses_python_source_surface",
            "cpp_support_consumes_generated_contract",
        ),
        rust_required_before_full_parity=(
            "rust_core_consumes_generated_contract",
            "tauri_dashboard_stream_backend_uses_python_source_route",
            "tauri_dashboard_stream_browser_bridge",
            "tauri_browser_consumes_generated_contract",
        ),
        cpp_full_parity=True,
        rust_full_parity=True,
    ),
    NativeParityDomain(
        key="logs_terminal_diagnostics",
        title="Logs, terminal, and diagnostics",
        python_surface="Service logs, dashboard logs, terminal command execution, exception diagnostics, secret redaction, and test runner/reporting flows.",
        cpp_required_before_full_parity=(
            "cpp_code_terminal_uses_python_service_api",
            "cpp_support_consumes_generated_contract",
        ),
        rust_required_before_full_parity=(
            "rust_core_consumes_generated_contract",
            "tauri_browser_service_api_uses_python_source_routes",
            "tauri_dashboard_stream_browser_bridge",
        ),
        cpp_full_parity=True,
        rust_full_parity=True,
    ),
    NativeParityDomain(
        key="llm_advisory",
        title="LLM advisory and local model lifecycle",
        python_surface="Provider catalogs, privacy flags, advisory prompt execution, config persistence, local Ollama status/start/pull/delete, and redacted output.",
        cpp_required_before_full_parity=(
            "cpp_dashboard_llm_service_api_uses_python_source_routes",
            "cpp_llm_catalog_payload_fields_follow_python",
            "cpp_llm_dynamic_catalog_uses_python_sources",
            "cpp_llm_output_policy_uses_python_reference_fixture",
            "cpp_llm_chat_request_uses_python_reference_fixture",
        ),
        rust_required_before_full_parity=(
            "rust_llm_output_policy_uses_python_reference_fixture",
            "rust_llm_chat_request_uses_python_reference_fixture",
            "rust_llm_dynamic_catalog_uses_python_sources",
            "tauri_llm_catalog_uses_python_source_route",
            "tauri_browser_service_api_uses_python_source_routes",
        ),
        cpp_full_parity=True,
        rust_full_parity=True,
    ),
    NativeParityDomain(
        key="startup_packaging_platform",
        title="Startup, packaging, and platform integration",
        python_surface="Product entrypoints, startup splash/suppression, Windows taskbar metadata, PyInstaller packaging, service wrappers, and release smoke tests.",
        cpp_required_before_full_parity=(
            "cpp_startup_packaging_contract",
        ),
        rust_required_before_full_parity=(
            "rust_startup_packaging_contract",
            "tauri_environment_versions_backend_uses_python_source_catalog",
            "tauri_environment_versions_browser_bridge",
        ),
        cpp_full_parity=True,
        rust_full_parity=True,
    ),
)


def _native_position_reference_allocation(
    ledger_id: str,
    interval: str,
    *,
    qty: float = 1.0,
) -> dict[str, object]:
    return {
        "ledger_id": ledger_id,
        "interval": interval,
        "interval_display": interval,
        "trigger_indicators": ["rsi"],
        "trade_id": f"trade-{ledger_id}",
        "client_order_id": f"client-{ledger_id}",
        "order_id": f"order-{ledger_id}",
        "event_uid": f"event-{ledger_id}",
        "slot_id": f"slot-{ledger_id}",
        "context_key": f"context-{ledger_id}",
        "open_time": "2026-01-01T00:00:00Z",
        "close_time": "",
        "qty": qty,
        "margin_usdt": 100.0,
        "notional": 100.0,
        "pnl_value": None,
        "status": "Open",
        "close_price": None,
        "entry_price": 100.0,
        "leverage": 1,
    }


def _native_position_reference_record(
    symbol: str,
    side_key: str,
    interval: str,
    *,
    open_time: str = "",
    stop_loss_enabled: bool = False,
    allocations: list[dict[str, object]] | None = None,
    quantity: float | None = None,
) -> dict[str, object]:
    return {
        "symbol": symbol,
        "side_key": side_key,
        "interval": interval,
        "quantity": quantity,
        "mark_price": 100.0 if quantity is not None else None,
        "size_usdt": 100.0 if quantity is not None else None,
        "margin_usdt": 100.0 if quantity is not None else None,
        "pnl_value": 0.0 if quantity is not None else None,
        "roi_percent": 0.0 if quantity is not None else None,
        "leverage": 1 if quantity is not None else None,
        "liquidation_price": None,
        "status": "Active",
        "stop_loss_enabled": stop_loss_enabled,
        "open_time": open_time,
        "close_time": "",
        "allocations": deepcopy(allocations or []),
    }


def _native_position_reference_state(
    *,
    open_position_records: dict[str, dict[str, object]],
    entry_allocations: dict[str, list[dict[str, object]]] | None = None,
    closed_position_records: list[dict[str, object]] | None = None,
    missing_counts: dict[str, int] | None = None,
    pending_close_times: dict[str, str] | None = None,
) -> dict[str, object]:
    return {
        "entry_allocations": deepcopy(entry_allocations or {}),
        "open_position_records": deepcopy(open_position_records),
        "closed_position_records": deepcopy(closed_position_records or []),
        "missing_counts": deepcopy(missing_counts or {}),
        "pending_close_times": deepcopy(pending_close_times or {}),
    }


def _native_position_reference_epoch(value: object) -> float | None:
    text = str(value or "").strip()
    if not text:
        return None
    try:
        parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=timezone.utc)
        return parsed.timestamp()
    except (TypeError, ValueError, OverflowError):
        return None


def _native_position_reference_reconcile_step(
    state: dict[str, object],
    live_position_records: dict[str, dict[str, object]],
    policy: dict[str, object],
    *,
    now_epoch_seconds: float,
    close_time: str,
    max_history: int,
) -> tuple[dict[str, object], dict[str, list[str]]]:
    """Apply the deterministic portion of Python's missing-position policy.

    The GUI still performs the exchange freshness lookup and liquidation lookup
    around this state transition. This pure case runner is the Python oracle for
    the same state transition that native runtimes execute after those lookups.
    """

    next_state = deepcopy(state)
    open_records = next_state["open_position_records"]
    entry_allocations = next_state["entry_allocations"]
    closed_records = next_state["closed_position_records"]
    missing_counts = next_state["missing_counts"]
    pending_close_times = next_state["pending_close_times"]
    assert isinstance(open_records, dict)
    assert isinstance(entry_allocations, dict)
    assert isinstance(closed_records, list)
    assert isinstance(missing_counts, dict)
    assert isinstance(pending_close_times, dict)

    live_keys: list[str] = []
    for key in sorted(live_position_records):
        live_keys.append(key)
        record = deepcopy(live_position_records[key])
        previous = open_records.get(key)
        if not isinstance(previous, dict):
            previous = {}
        if not str(record.get("open_time") or "").strip():
            previous_open = str(previous.get("open_time") or "").strip()
            if previous_open:
                record["open_time"] = previous_open
        if not str(record.get("interval") or "").strip():
            previous_interval = str(previous.get("interval") or "").strip()
            if previous_interval:
                record["interval"] = previous_interval
        if not record.get("allocations"):
            previous_allocations = previous.get("allocations")
            if previous_allocations:
                record["allocations"] = deepcopy(previous_allocations)
        if not bool(record.get("stop_loss_enabled")) and bool(previous.get("stop_loss_enabled")):
            record["stop_loss_enabled"] = True
        if not str(record.get("status") or "").strip():
            record["status"] = "Active"
        missing_counts.pop(key, None)
        pending_close_times.pop(key, None)
        open_records[key] = record

    try:
        threshold = int(policy.get("positions_missing_threshold") or 2)
    except (TypeError, ValueError):
        threshold = 2
    threshold = max(1, threshold)
    try:
        grace_seconds = float(policy.get("positions_missing_grace_seconds") or 30.0)
    except (TypeError, ValueError):
        grace_seconds = 0.0
    if grace_seconds != grace_seconds or grace_seconds < 0.0:
        grace_seconds = 0.0
    allow_autoclose = bool(policy.get("positions_missing_autoclose", True))
    summary = {
        "closed_keys": [],
        "dropped_keys": [],
        "waiting_keys": [],
        "live_keys": live_keys,
    }

    for key in sorted(open_records):
        if key in live_position_records:
            continue
        count = int(missing_counts.get(key, 0) or 0) + 1
        missing_counts[key] = count
        required = 1 if key in pending_close_times else threshold
        if count < required:
            summary["waiting_keys"].append(key)
            continue

        within_grace = False
        if grace_seconds > 0.0 and key not in pending_close_times:
            record = open_records.get(key)
            open_value = record.get("open_time") if isinstance(record, dict) else None
            opened = _native_position_reference_epoch(open_value)
            if opened is not None:
                age_seconds = now_epoch_seconds - opened
                within_grace = 0.0 <= age_seconds < grace_seconds
        if within_grace:
            summary["waiting_keys"].append(key)
            continue

        if allow_autoclose:
            record = deepcopy(open_records.pop(key))
            record["status"] = "Closed"
            record["close_time"] = close_time.strip() or str(record.get("close_time") or "")
            allocations = entry_allocations.get(key)
            if allocations:
                record["allocations"] = deepcopy(allocations)
            closed_records.insert(0, record)
            del closed_records[max(1, int(max_history)) :]
            summary["closed_keys"].append(key)
        else:
            open_records.pop(key, None)
            entry_allocations.pop(key, None)
            summary["dropped_keys"].append(key)
        missing_counts.pop(key, None)
        pending_close_times.pop(key, None)

    for key in summary:
        summary[key].sort()
    return next_state, summary


def native_position_reconciliation_reference_cases() -> list[dict[str, object]]:
    allocation = _native_position_reference_allocation("ledger-btc", "5m")
    cases: list[dict[str, object]] = [
        {
            "name": "live-recovery-preserves-python-metadata",
            "initial_state": _native_position_reference_state(
                open_position_records={
                    "BTCUSDT:L": _native_position_reference_record(
                        "BTCUSDT",
                        "L",
                        "5m",
                        open_time="2026-01-01T00:00:00Z",
                        stop_loss_enabled=True,
                        allocations=[allocation],
                    )
                },
                entry_allocations={"BTCUSDT:L": [allocation]},
                missing_counts={"BTCUSDT:L": 2},
                pending_close_times={"BTCUSDT:L": "2026-01-01T00:00:01Z"},
            ),
            "steps": [
                {
                    "live_position_records": {
                        "BTCUSDT:L": _native_position_reference_record(
                            "BTCUSDT", "L", "", quantity=1.0
                        )
                    },
                    "policy": {
                        "positions_missing_threshold": 2,
                        "positions_missing_grace_seconds": 30.0,
                        "positions_missing_autoclose": True,
                    },
                    "now_epoch_seconds": 1_767_225_602.0,
                    "close_time": "2026-01-01T00:00:02Z",
                    "max_history": 10,
                }
            ],
        },
        {
            "name": "threshold-autoclose-after-two-misses",
            "initial_state": _native_position_reference_state(
                open_position_records={
                    "ETHUSDT:S": _native_position_reference_record("ETHUSDT", "S", "1m")
                }
            ),
            "steps": [
                {
                    "live_position_records": {},
                    "policy": {
                        "positions_missing_threshold": 2,
                        "positions_missing_grace_seconds": 0.0,
                        "positions_missing_autoclose": True,
                    },
                    "now_epoch_seconds": 1_767_225_660.0,
                    "close_time": "2026-01-01T00:01:00Z",
                    "max_history": 10,
                },
                {
                    "live_position_records": {},
                    "policy": {
                        "positions_missing_threshold": 2,
                        "positions_missing_grace_seconds": 0.0,
                        "positions_missing_autoclose": True,
                    },
                    "now_epoch_seconds": 1_767_225_661.0,
                    "close_time": "2026-01-01T00:01:01Z",
                    "max_history": 10,
                },
            ],
        },
        {
            "name": "grace-period-waits-before-close",
            "initial_state": _native_position_reference_state(
                open_position_records={
                    "XRPUSDT:L": _native_position_reference_record(
                        "XRPUSDT", "L", "5m", open_time="2026-01-01T00:00:00Z"
                    )
                }
            ),
            "steps": [
                {
                    "live_position_records": {},
                    "policy": {
                        "positions_missing_threshold": 1,
                        "positions_missing_grace_seconds": 120.0,
                        "positions_missing_autoclose": True,
                    },
                    "now_epoch_seconds": 1_767_225_660.0,
                    "close_time": "2026-01-01T00:01:00Z",
                    "max_history": 10,
                }
            ],
        },
        {
            "name": "autoclose-disabled-drops-record",
            "initial_state": _native_position_reference_state(
                open_position_records={
                    "SOLUSDT:S": _native_position_reference_record("SOLUSDT", "S", "1m")
                }
            ),
            "steps": [
                {
                    "live_position_records": {},
                    "policy": {
                        "positions_missing_threshold": 1,
                        "positions_missing_grace_seconds": 0.0,
                        "positions_missing_autoclose": False,
                    },
                    "now_epoch_seconds": 1_767_225_660.0,
                    "close_time": "2026-01-01T00:01:00Z",
                    "max_history": 10,
                }
            ],
        },
        {
            "name": "pending-close-bypasses-threshold-and-grace",
            "initial_state": _native_position_reference_state(
                open_position_records={
                    "ADAUSDT:L": _native_position_reference_record(
                        "ADAUSDT", "L", "1m", open_time="2026-01-01T00:00:00Z"
                    )
                },
                pending_close_times={"ADAUSDT:L": "2026-01-01T00:00:10Z"},
            ),
            "steps": [
                {
                    "live_position_records": {},
                    "policy": {
                        "positions_missing_threshold": 2,
                        "positions_missing_grace_seconds": 120.0,
                        "positions_missing_autoclose": True,
                    },
                    "now_epoch_seconds": 1_767_225_660.0,
                    "close_time": "2026-01-01T00:01:00Z",
                    "max_history": 10,
                }
            ],
        },
    ]

    for case in cases:
        state = deepcopy(case["initial_state"])
        expected_steps: list[dict[str, object]] = []
        for step in case["steps"]:
            state, summary = _native_position_reference_reconcile_step(
                state,
                step["live_position_records"],
                step["policy"],
                now_epoch_seconds=float(step["now_epoch_seconds"]),
                close_time=str(step["close_time"]),
                max_history=int(step["max_history"]),
            )
            expected_steps.append({"summary": summary, "state": deepcopy(state)})
        case["expected_steps"] = expected_steps
    return cases


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
            "api_styles": list(provider.api_styles or (provider.protocol,)),
            "speed_options": list(provider.speed_options),
            "default_speed": provider.default_speed,
            "supports_model_discovery": provider.supports_model_discovery,
            "model_discovery_path": provider.model_discovery_path,
            "catalog_revision": LLM_PROVIDER_CATALOG_REVISION,
            "custom_models_env": f"BOT_LLM_EXTRA_MODELS_{provider.key.upper().replace('-', '_')}",
            "custom_models_path_env": LLM_MODEL_CATALOG_PATH_ENV,
            "notes": list(provider.notes),
        }
        for provider in _PROVIDER_SPECS
    ]


def _config_choice_maps() -> dict[str, dict[str, str]]:
    return {
        "account_type": dict(_ACCOUNT_TYPE_CHOICES),
        "margin_mode": dict(_MARGIN_MODE_CHOICES),
        "position_mode": dict(_POSITION_MODE_CHOICES),
        "assets_mode": dict(_ASSETS_MODE_CHOICES),
        "account_mode": dict(_ACCOUNT_MODE_CHOICES),
        "side": dict(_SIDE_CHOICES),
        "order_type": dict(_ORDER_TYPE_CHOICES),
        "tif": dict(_TIF_CHOICES),
        "logic": dict(_LOGIC_CHOICES),
        "mdd_logic": {item: item for item in MDD_LOGIC_OPTIONS},
        "stop_loss_mode": {item: item for item in STOP_LOSS_MODE_ORDER},
        "stop_loss_scope": {item: item for item in STOP_LOSS_SCOPE_OPTIONS},
        "scan_scope": dict(_SCAN_SCOPE_CHOICES),
        "optimizer_mode": dict(_OPTIMIZER_MODE_CHOICES),
        "optimizer_metric": dict(_OPTIMIZER_METRIC_CHOICES),
        "backtest_execution_backend": dict(_BACKTEST_EXECUTION_BACKEND_CHOICES),
        "chart_view_mode": dict(_CHART_VIEW_MODE_CHOICES),
        "llm_use_for": dict(_LLM_USE_FOR_CHOICES),
        "llm_reasoning_effort": dict(_LLM_REASONING_EFFORT_CHOICES),
        "position_pct_units": dict(controls_shared_runtime.POSITION_PCT_UNITS_CHOICES),
    }


def native_runtime_config_choice_reference() -> list[dict[str, object]]:
    """Return Python-normalized cases for every accepted config choice alias."""

    choice_paths: dict[str, tuple[tuple[str, ...], str]] = {
        "account_type": ((), "account_type"),
        "margin_mode": ((), "margin_mode"),
        "position_mode": ((), "position_mode"),
        "assets_mode": ((), "assets_mode"),
        "account_mode": ((), "account_mode"),
        "side": ((), "side"),
        "order_type": ((), "order_type"),
        "tif": ((), "tif"),
        "chart_view_mode": (("chart",), "view_mode"),
        "logic": (("backtest",), "logic"),
        "backtest_execution_backend": (("backtest",), "execution_backend"),
        "mdd_logic": (("backtest",), "mdd_logic"),
        "scan_scope": (("backtest",), "scan_scope"),
        "optimizer_mode": (("backtest",), "optimizer_mode"),
        "optimizer_metric": (("backtest",), "optimizer_metric"),
        "stop_loss_mode": (("stop_loss",), "mode"),
        "stop_loss_scope": (("stop_loss",), "scope"),
        "llm_use_for": ((), "llm_use_for"),
        "llm_reasoning_effort": ((), "llm_reasoning_effort"),
    }
    cases: list[dict[str, object]] = []
    choice_maps = _config_choice_maps()
    for choice_name, (path, field) in choice_paths.items():
        for alias in choice_maps.get(choice_name, {}):
            config: dict[str, object] = {}
            target = config
            for part in path:
                child: dict[str, object] = {}
                target[part] = child
                target = child
            target[field] = alias
            cases.append(
                {
                    "name": f"choice-{choice_name}-{alias}",
                    "input": config,
                    "valid": True,
                    "expected": validate_runtime_config(config),
                    "expected_error": "",
                }
            )

    # Position units belong to strategy controls nested under a symbol/interval
    # override, rather than to the top-level runtime configuration schema.
    for alias in choice_maps.get("position_pct_units", {}):
        config = {
            "runtime_symbol_interval_pairs": [
                {
                    "symbol": "BTCUSDT",
                    "interval": "1m",
                    "strategy_controls": {"position_pct_units": alias},
                }
            ]
        }
        cases.append(
            {
                "name": f"choice-position_pct_units-{alias}",
                "input": config,
                "valid": True,
                "expected": validate_runtime_config(config),
                "expected_error": "",
            }
        )

    for alias in llm_provider_choices():
        if alias:
            config = {"llm_provider": alias}
            cases.append(
                {
                    "name": f"choice-llm_provider-{alias}",
                    "input": config,
                    "valid": True,
                    "expected": validate_runtime_config(config),
                    "expected_error": "",
                }
            )
    for key in ("stop_without_close",):
        for alias in ("true", "false"):
            config = {key: alias}
            cases.append(
                {
                    "name": f"bool-{key}-{alias}",
                    "input": config,
                    "valid": True,
                    "expected": validate_runtime_config(config),
                    "expected_error": "",
                }
            )
    return cases


def native_runtime_config_invalid_reference_cases() -> list[dict[str, object]]:
    """Return Python-owned rejection outcomes for native config validators."""

    invalid_cases: tuple[tuple[str, dict[str, object]], ...] = (
        ("invalid-unknown-key", {"unknown_key": True}),
        ("invalid-mode-empty", {"mode": ""}),
        ("invalid-account-type", {"account_type": "margin"}),
        ("invalid-symbol-type", {"symbols": 42}),
        ("invalid-symbol-content", {"symbols": ["BTC USDT"]}),
        ("invalid-interval-type", {"intervals": 42}),
        ("invalid-interval-content", {"intervals": ["0m"]}),
        ("invalid-lookback-type", {"lookback": "bars"}),
        ("invalid-lookback-range", {"lookback": 0}),
        ("invalid-position-pct-exclusive", {"position_pct": 0}),
        ("invalid-position-pct-range", {"position_pct": 101}),
        ("invalid-bool", {"live_trading_enabled": "maybe"}),
        ("invalid-loop-interval", {"loop_interval_override": "fast"}),
        ("invalid-pair-type", {"runtime_symbol_interval_pairs": {}}),
        (
            "invalid-pair-entry",
            {"runtime_symbol_interval_pairs": [{"symbol": "BTC USDT", "interval": "1m"}]},
        ),
        (
            "invalid-pair-controls",
            {
                "runtime_symbol_interval_pairs": [
                    {
                        "symbol": "BTCUSDT",
                        "interval": "1m",
                        "strategy_controls": {"leverage": 0},
                    }
                ]
            },
        ),
        ("invalid-stop-loss-type", {"stop_loss": "no"}),
        ("invalid-chart-type", {"chart": "no"}),
        ("invalid-chart-key", {"chart": {"unknown": True}}),
        ("invalid-chart-market", {"chart": {"market": "margin"}}),
        ("invalid-chart-view", {"chart": {"view_mode": "external"}}),
        ("invalid-chart-symbol", {"chart": {"symbol": "BTC USDT"}}),
        ("invalid-chart-interval", {"chart": {"interval": "0m"}}),
        ("invalid-backtest-type", {"backtest": "no"}),
        ("invalid-backtest-key", {"backtest": {"unknown": True}}),
        ("invalid-backtest-capital", {"backtest": {"capital": 0}}),
        ("invalid-backtest-date", {"backtest": {"start_date": "not-date"}}),
        ("invalid-backtest-choice", {"backtest": {"logic": "xor"}}),
        ("invalid-backtest-mapping", {"backtest": {"template": []}}),
        ("invalid-backtest-stop-loss", {"backtest": {"stop_loss": "bad"}}),
        ("invalid-risk-int", {"indicator_flip_confirmation_bars": 0}),
        ("invalid-risk-float", {"max_auto_bump_percent": 101}),
        ("invalid-llm-provider", {"llm_provider": "ghost-ai"}),
        ("invalid-text-control", {"connector_backend": "ok\u0001"}),
    )
    cases: list[dict[str, object]] = []
    for name, config in invalid_cases:
        try:
            validate_runtime_config(config)
        except ConfigValidationError as error:
            cases.append(
                {
                    "name": name,
                    "input": config,
                    "valid": False,
                    "expected": {},
                    "expected_error": str(error),
                }
            )
        else:
            raise AssertionError(f"Python invalid parity fixture unexpectedly validated: {name}")
    return cases


class _NativeStrategyControlsReferenceAdapter:
    """Bind the real Python control formatter without importing a GUI window."""

    config: dict[str, object] = {}

    @staticmethod
    def _normalize_position_pct_units(value) -> str:
        return controls_shared_runtime._normalize_position_pct_units(value)

    @staticmethod
    def _normalize_loop_override(value) -> str | None:
        text = str(value or "").strip()
        if not text:
            return None
        cleaned = re.sub(r"\s+", "", text.lower())
        if re.match(r"^\d+(s|m|h|d|w)?$", cleaned):
            return cleaned
        return None

    @staticmethod
    def _normalize_account_mode(value) -> str:
        text = str(value or "").strip().lower()
        if "portfolio" in text:
            return "Portfolio Margin"
        return "Classic Trading"

    @staticmethod
    def _normalize_assets_mode(value) -> str:
        text = str(value or "").strip().lower()
        if "multi" in text:
            return "Multi-Assets"
        return "Single-Asset"

    @staticmethod
    def _canonical_side_from_text(value: str) -> str:
        raw = str(value or "").strip()
        if not raw:
            return "BOTH"
        lower = raw.lower()
        side_lookup = {str(label).lower(): str(code) for code, label in SIDE_LABELS.items()}
        if lower in side_lookup:
            return side_lookup[lower]
        if lower.startswith("buy"):
            return "BUY"
        if lower.startswith("sell"):
            return "SELL"
        return "BOTH"


def native_strategy_controls_reference_cases() -> list[dict[str, object]]:
    """Return exact Python strategy-control normalization outcomes."""

    controls_shared_runtime.configure_main_window_strategy_controls_shared_runtime(
        side_labels=SIDE_LABELS,
        normalize_stop_loss_dict=normalize_stop_loss_dict,
        normalize_connector_backend=_normalize_connector_backend,
    )
    adapter = _NativeStrategyControlsReferenceAdapter()
    raw_cases: tuple[tuple[str, str, dict[str, object]], ...] = (
        (
            "runtime-canonical",
            "runtime",
            {
                "side": "buy",
                "position_pct": "12.5",
                "position_pct_units": "percentage",
                "leverage": "3",
                "loop_interval_override": " 5 M ",
                "add_only": "false",
                "account_mode": "portfolio margin",
                "connector_backend": "CCXT",
                "stop_loss": {
                    "enabled": "true",
                    "mode": "both",
                    "scope": "bad",
                    "usdt": "50",
                    "percent": "2.5",
                },
            },
        ),
        (
            "runtime-python-truthiness-boundaries",
            "runtime",
            {
                "side": " buy ",
                "position_pct": True,
                "position_pct_units": "",
                "_position_pct_units": "percentage",
                "leverage": 2.5,
                "loop_interval_override": " 5 M ",
                "add_only": None,
                "account_mode": False,
                "connector_backend": False,
            },
        ),
        (
            "runtime-kind-is-case-sensitive",
            "Runtime",
            {
                "side": "buy",
                "stop_loss": {"enabled": True},
                "connector_backend": "ccxt",
            },
        ),
        (
            "backtest-canonical",
            "backtest",
            {
                "logic": "separate",
                "capital": "1000",
                "position_pct": "0.4",
                "position_pct_units": "fraction",
                "side": "sell short",
                "margin_mode": " Isolated ",
                "position_mode": " Hedge ",
                "assets_mode": "multi assets",
                "account_mode": "classic",
                "loop_interval_override": " 1 h ",
                "leverage": 0,
                "fee_bps": "5",
                "slippage_bps": "2",
                "stop_loss": {
                    "enabled": "true",
                    "mode": "both",
                    "scope": "entire_account",
                    "percent": "2.5",
                },
                "connector_backend": "ccxt",
            },
        ),
        (
            "backtest-exact-logic-and-fuzzy-side",
            "backtest",
            {
                "logic": " OR ",
                "side": " buy ",
                "leverage": "3.5",
                "margin_mode": "",
                "position_mode": "Hedge",
                "assets_mode": "single asset",
                "account_mode": "portfolio",
            },
        ),
    )
    return [
        {
            "name": name,
            "kind": kind,
            "input": controls,
            "expected": controls_format_runtime._normalize_strategy_controls(adapter, kind, controls),
        }
        for name, kind, controls in raw_cases
    ]


def native_strategy_risk_reference_cases() -> list[dict[str, object]]:
    """Return Python-validated effective risk-control outputs for native runtimes."""

    raw_cases: tuple[tuple[str, dict[str, object]], ...] = (
        (
            "risk-defaults",
            {},
        ),
        (
            "risk-canonical-all-controls",
            {
                "indicator_flip_cooldown_bars": "4",
                "indicator_flip_cooldown_seconds": "12.5",
                "indicator_use_live_values": "false",
                "indicator_min_position_hold_seconds": "7.25",
                "indicator_min_position_hold_bars": "3",
                "require_indicator_flip_signal": "yes",
                "strict_indicator_flip_enforcement": "no",
                "indicator_reentry_cooldown_seconds": "9.5",
                "indicator_reentry_cooldown_bars": "2",
                "indicator_reentry_requires_signal_reset": "true",
                "auto_flip_on_close": "false",
                "allow_close_ignoring_hold": "true",
                "allow_multi_indicator_close": "true",
                "allow_indicator_close_without_signal": "false",
                "indicator_flip_confirmation_bars": "2",
                "close_on_exit": "true",
                "positions_missing_threshold": "3",
                "positions_missing_autoclose": "false",
                "positions_missing_grace_seconds": "45",
                "futures_flat_purge_miss_threshold": "4",
                "futures_flat_purge_grace_seconds": "18.5",
                "allow_opposite_positions": "false",
                "hedge_preserve_opposites": "true",
                "max_auto_bump_percent": "7.5",
                "auto_bump_percent_multiplier": "20",
                "stop_loss": {
                    "enabled": "true",
                    "mode": "percent",
                    "scope": "entire_account",
                    "usdt": "25",
                    "percent": "2.5",
                },
            },
        ),
        (
            "risk-valid-lower-and-upper-bounds",
            {
                "indicator_flip_cooldown_bars": 0,
                "indicator_flip_cooldown_seconds": 0,
                "indicator_min_position_hold_seconds": 0,
                "indicator_min_position_hold_bars": 0,
                "indicator_reentry_cooldown_seconds": 0,
                "indicator_reentry_cooldown_bars": 0,
                "indicator_flip_confirmation_bars": 1,
                "positions_missing_threshold": 1,
                "positions_missing_grace_seconds": 604800,
                "futures_flat_purge_miss_threshold": 1,
                "futures_flat_purge_grace_seconds": 604800,
                "max_auto_bump_percent": 100,
                "auto_bump_percent_multiplier": 1000,
                "stop_loss": {
                    "enabled": False,
                    "mode": "both",
                    "scope": "cumulative",
                    "usdt": 0,
                    "percent": 0,
                },
            },
        ),
    )
    cases: list[dict[str, object]] = []
    for name, config in raw_cases:
        normalized = validate_runtime_config(config)
        expected = native_python_risk_defaults()
        expected.update(normalized)
        cases.append(
            {
                "name": name,
                "input": config,
                "expected": expected,
            }
        )
    return cases


def native_strategy_risk_loose_reference_cases() -> list[dict[str, object]]:
    """Return Python's loose bool-coercion cases for strategy risk controls."""

    bool_keys = (
        "indicator_use_live_values",
        "require_indicator_flip_signal",
        "strict_indicator_flip_enforcement",
        "indicator_reentry_requires_signal_reset",
        "auto_flip_on_close",
        "allow_close_ignoring_hold",
        "allow_multi_indicator_close",
        "allow_indicator_close_without_signal",
        "close_on_exit",
        "positions_missing_autoclose",
        "allow_opposite_positions",
        "hedge_preserve_opposites",
    )
    raw_cases: tuple[tuple[str, object], ...] = (
        ("risk-loose-string-y", "y"),
        ("risk-loose-unknown-string", "maybe"),
        ("risk-loose-string-n", "n"),
        ("risk-loose-fractional-zero", 0.5),
        ("risk-loose-fractional-one", 1.5),
        ("risk-loose-negative-fractional-zero", -0.5),
        ("risk-loose-negative-fractional-one", -1.5),
        ("risk-loose-empty-list", []),
        ("risk-loose-nonempty-list", [0]),
        ("risk-loose-empty-object", {}),
        ("risk-loose-nonempty-object", {"enabled": True}),
    )
    cases: list[dict[str, object]] = []
    for name, value in raw_cases:
        config = {key: value for key in bool_keys}
        expected = native_python_risk_defaults()
        for key in bool_keys:
            expected[key] = coerce_bool(value, bool(expected[key]))
        cases.append(
            {
                "name": name,
                "input": config,
                "expected": expected,
            }
        )
    return cases


def native_indicator_enabled_reference_cases() -> list[dict[str, object]]:
    """Return strategy indicator enabled coercion from Python's canonical bool helper."""

    raw_cases: tuple[tuple[str, object], ...] = (
        ("indicator-enabled-bool-true", True),
        ("indicator-enabled-bool-false", False),
        ("indicator-enabled-string-true", "true"),
        ("indicator-enabled-string-false", "false"),
        ("indicator-enabled-string-yes", "yes"),
        ("indicator-enabled-string-no", "no"),
        ("indicator-enabled-string-on", "on"),
        ("indicator-enabled-string-off", "off"),
        ("indicator-enabled-string-disabled", "disabled"),
        ("indicator-enabled-string-none", "none"),
        ("indicator-enabled-string-null", "null"),
        ("indicator-enabled-string-numeric", "0.5"),
        ("indicator-enabled-string-y", "y"),
        ("indicator-enabled-unknown-string", "maybe"),
        ("indicator-enabled-empty-string", ""),
        ("indicator-enabled-null", None),
        ("indicator-enabled-zero", 0),
        ("indicator-enabled-one", 1),
        ("indicator-enabled-fractional-zero", 0.5),
        ("indicator-enabled-fractional-one", 1.5),
        ("indicator-enabled-negative-fractional-zero", -0.5),
        ("indicator-enabled-negative-fractional-one", -1.5),
        ("indicator-enabled-empty-list", []),
        ("indicator-enabled-nonempty-list", [0]),
        ("indicator-enabled-empty-object", {}),
        ("indicator-enabled-nonempty-object", {"enabled": True}),
    )
    cases: list[dict[str, object]] = [
        {
            "name": "indicator-enabled-missing",
            "input": {},
            "expected": coerce_bool(None, False),
        }
    ]
    for name, value in raw_cases:
        cases.append(
            {
                "name": name,
                "input": {"enabled": value},
                "expected": coerce_bool(value, False),
            }
        )
    return cases


def native_backtest_indicator_enabled_reference_cases() -> list[dict[str, object]]:
    """Return backtest/optimizer indicator selection coercion from Python."""

    raw_cases = native_indicator_enabled_reference_cases()
    cases: list[dict[str, object]] = []
    for case in raw_cases:
        input_config = dict(case["input"])
        value = input_config.get("enabled")
        cases.append(
            {
                "name": str(case["name"]).replace("indicator-enabled", "backtest-indicator-enabled", 1),
                "input": input_config,
                "expected": backtest_indicator_enabled(value, default=False),
            }
        )
    return cases


def native_interval_seconds_reference_cases() -> list[dict[str, object]]:
    """Return interval timing behavior used by Python strategy runtime paths."""

    values = (
        "1s",
        "5m",
        "1.5m",
        "0.5h",
        "1h",
        "1d",
        "1w",
        "1mo",
        "1y",
        "5",
        "0m",
        "-1m",
        "1M",
        " 5m ",
        "5m ",
        "",
    )
    cases: list[dict[str, object]] = []
    for value in values:
        cases.append(
            {
                "input": value,
                "indicator_seconds": interval_seconds_value(value),
                "loop_seconds": max(1, interval_seconds(value)),
            }
        )
    return cases


def native_backtest_interval_seconds_reference_cases() -> list[dict[str, object]]:
    """Return the exact interval coercion used by Python backtest data loading."""

    values = (
        "1s",
        "5m",
        "1.5m",
        "0.5h",
        "1h",
        "1d",
        "1w",
        "1mo",
        "1y",
        "5",
        "0m",
        "-1m",
        "1M",
        " 5m ",
        "5m ",
        "",
        "abc",
        "5x",
    )
    return [
        {
            "input": value,
        "seconds": backtest_interval_seconds(value),
        }
        for value in values
    ]


def native_stop_intent_reference_cases() -> dict[str, object]:
    """Return Python-normalized stop-without-close intent cases for native runtimes."""

    raw_cases: tuple[tuple[str, dict[str, object]], ...] = (
        ("default-close-all", {}),
        ("explicit-close-all", {"stop_without_close": False}),
        ("explicit-keep-open", {"stop_without_close": True}),
        ("string-keep-open", {"stop_without_close": "true"}),
        ("string-close-all", {"stop_without_close": "false"}),
    )
    cases: list[dict[str, object]] = []
    for name, config in raw_cases:
        normalized = validate_runtime_config(config)
        stop_without_close = bool(normalized.get("stop_without_close", False))
        cases.append(
            {
                "name": name,
                "input": dict(config),
                "expected": {
                    "stop_without_close": stop_without_close,
                    "close_positions": not stop_without_close,
                },
            }
        )
    return {"schema_version": 1, "cases": cases}


def native_stop_intent_loose_reference_cases() -> dict[str, object]:
    """Return Python's loose bool-coercion cases used before config validation."""

    raw_cases: tuple[tuple[str, dict[str, object]], ...] = (
        ("missing", {}),
        ("null", {"stop_without_close": None}),
        ("empty-string", {"stop_without_close": ""}),
        ("string-y-is-false", {"stop_without_close": "y"}),
        ("unknown-string-is-false", {"stop_without_close": "maybe"}),
        ("fractional-zero-is-false", {"stop_without_close": 0.5}),
        ("fractional-one-is-true", {"stop_without_close": 1.5}),
        ("negative-fraction-is-true", {"stop_without_close": -1.5}),
    )
    cases: list[dict[str, object]] = []
    for name, config in raw_cases:
        stop_without_close = coerce_bool(config.get("stop_without_close"), False)
        cases.append(
            {
                "name": name,
                "input": dict(config),
                "expected": {
                    "stop_without_close": stop_without_close,
                    "close_positions": not stop_without_close,
                },
            }
        )
    return {"schema_version": 1, "cases": cases}


def native_order_intent_reference_cases() -> dict[str, object]:
    """Return Python order-intent and raw-filter truthiness reference cases."""

    from trading_core.orders import (
        order_submit_intent_from_params,
        validate_order_submit_intent,
    )

    from .integrations.exchanges.binance.orders.order_submit_guard_runtime import (
        _order_filter_errors,
    )

    class _FixtureWrapper:
        def __init__(self, filters: dict[str, object], last_price: object) -> None:
            self._filters = dict(filters)
            self._last_price = last_price

        def get_spot_symbol_filters(self, _symbol: str) -> dict[str, object]:
            return dict(self._filters)

        def get_futures_symbol_filters(self, _symbol: str) -> dict[str, object]:
            return dict(self._filters)

        def get_last_price(self, _symbol: str) -> object:
            return self._last_price

    raw_cases: tuple[tuple[str, str, dict[str, object], dict[str, object], object], ...] = (
        (
            "canonical-close-position",
            "futures",
            {
                "symbol": "BTCUSDT",
                "side": "SELL",
                "type": "MARKET",
                "closePosition": "true",
            },
            {"stepSize": 0.001, "tickSize": 0.1, "minQty": 0.01, "minNotional": 5.0},
            100.0,
        ),
        (
            "python-intent-y-is-false-filter-y-is-true",
            "futures",
            {
                "symbol": "BTCUSDT",
                "side": "SELL",
                "type": "MARKET",
                "quantity": "0.001",
                "closePosition": "y",
            },
            {"stepSize": 0.001, "tickSize": 0.1, "minQty": 0.01, "minNotional": 5.0},
            100.0,
        ),
        (
            "canonical-aliases-and-conflicting-flags",
            "futures",
            {
                "symbol": "ETHUSDT",
                "side": "BUY",
                "type": "LIMIT",
                "quantity": "1",
                "price": "2000",
                "position_side": "long",
                "close_position": "yes",
                "reduce_only": "on",
            },
            {"stepSize": 0.001, "tickSize": 0.1, "minQty": 0.01, "minNotional": 5.0},
            2000.0,
        ),
        (
            "spot-rejects-futures-flags",
            "spot",
            {
                "symbol": "ETHUSDT",
                "side": "BUY",
                "type": "MARKET",
                "positionSide": "LONG",
                "closePosition": "true",
                "reduceOnly": "true",
            },
            {"stepSize": 0.001, "tickSize": 0.1, "minQty": 0.01, "minNotional": 5.0},
            2000.0,
        ),
    )
    cases: list[dict[str, object]] = []
    for name, market, params, filters, last_price in raw_cases:
        intent = order_submit_intent_from_params(market, params)
        wrapper = _FixtureWrapper(filters, last_price)
        cases.append(
            {
                "name": name,
                "market": market,
                "params": dict(params),
                "filters": dict(filters),
                "last_price": last_price,
                "expected": {
                    "intent": asdict(intent),
                    "intent_errors": list(validate_order_submit_intent(intent)),
                    "filter_errors": list(_order_filter_errors(wrapper, market, params)),
                },
            }
        )
    return {"schema_version": 1, "cases": cases}


def native_live_safety_reference_cases() -> dict[str, object]:
    """Return Python-owned live safety outcomes for native guard consumers."""

    safe_config = {
        "live_trading_enabled": True,
        "live_trading_acknowledgement": LIVE_TRADING_ACKNOWLEDGEMENT,
        "live_trading_max_leverage": 5,
        "live_trading_max_position_pct": 3.0,
        "live_trading_max_session_orders": 7,
    }
    raw_cases: tuple[tuple[str, dict[str, object]], ...] = (
        (
            "demo-mode-bypasses-live-gates",
            {
                "mode": "Demo/Testnet",
                "api_key": "",
                "api_secret": "",
                "account_type": "Futures",
                "leverage": 0,
                "margin_mode": "invalid",
                "position_pct": 0.0,
                "config": {},
            },
        ),
        (
            "live-requires-confirmation",
            {
                "mode": "Live",
                "api_key": "live-api-key",
                "api_secret": "live-api-secret",
                "account_type": "Futures",
                "leverage": 1,
                "margin_mode": "",
                "position_pct": 2.0,
                "config": {},
            },
        ),
        (
            "live-safe-futures",
            {
                "mode": "Live",
                "api_key": "live-api-key",
                "api_secret": "live-api-secret",
                "account_type": "Futures",
                "leverage": 3,
                "margin_mode": "Isolated",
                "position_pct": 2.0,
                "config": dict(safe_config),
            },
        ),
        (
            "live-spot-position-cap",
            {
                "mode": "Live",
                "api_key": "live-api-key",
                "api_secret": "live-api-secret",
                "account_type": "Spot",
                "leverage": 0,
                "margin_mode": "invalid-is-ignored-for-spot",
                "position_pct": 4.0,
                "config": dict(safe_config),
            },
        ),
        (
            "live-invalid-caps-and-futures-controls",
            {
                "mode": "Production",
                "api_key": "live-api-key",
                "api_secret": "live-api-secret",
                "account_type": "Futures",
                "leverage": 130,
                "margin_mode": "Portfolio",
                "position_pct": 0.0,
                "config": {
                    "live_trading_enabled": True,
                    "live_trading_acknowledgement": LIVE_TRADING_ACKNOWLEDGEMENT,
                    "live_trading_max_leverage": BINANCE_MAX_FUTURES_LEVERAGE + 1,
                    "live_trading_max_position_pct": 0.0,
                    "live_trading_max_session_orders": 0,
                },
            },
        ),
        (
            "live-rejects-placeholder-credentials",
            {
                "mode": "Live",
                "api_key": "your_api_key",
                "api_secret": "testnet",
                "account_type": "Futures",
                "leverage": 1,
                "margin_mode": "Cross",
                "position_pct": 2.0,
                "config": dict(safe_config),
            },
        ),
    )

    cases: list[dict[str, object]] = []
    for name, input_case in raw_cases:
        try:
            validate_live_trading_safety(**input_case, env={})
        except LiveTradingSafetyError as exc:
            mode = input_case["mode"]
            prefix = f"Live trading safety check failed for mode {mode!r}: "
            message = str(exc)
            if not message.startswith(prefix) or not message.endswith("."):
                raise AssertionError(f"Unexpected Python live-safety error format: {message}") from exc
            detail = message[len(prefix) : -1]
            expected_errors = detail.split("; ") if detail else []
        else:
            expected_errors = []
        cases.append(
            {
                "name": name,
                "input": input_case,
                "expected_errors": expected_errors,
            }
        )
    return {"schema_version": 1, "cases": cases}


def native_connector_health_reference_cases() -> dict[str, object]:
    """Return Python connector-health order-guard cases for native consumers."""

    from .integrations.exchanges.binance.orders.order_submit_guard_runtime import (
        _order_health_errors,
    )

    class _FixtureWrapper:
        def __init__(self, snapshot: dict[str, object]) -> None:
            self._snapshot = dict(snapshot)

        def get_connector_health_snapshot(self) -> dict[str, object]:
            return dict(self._snapshot)

    raw_cases: tuple[tuple[str, dict[str, object]], ...] = (
        ("missing-state", {"state": "", "health": "ok"}),
        ("missing-health", {"state": "ready", "health": ""}),
        ("not-ready", {"state": "paused", "health": "degraded"}),
        ("degraded-health", {"state": "ready", "health": "degraded"}),
        ("ready-ok", {"state": "ready", "health": "ok"}),
        ("ready-unknown", {"state": "ready", "health": "unknown"}),
    )
    return {
        "schema_version": 1,
        "cases": [
            {
                "name": name,
                "snapshot": dict(snapshot),
                "expected_errors": list(_order_health_errors(_FixtureWrapper(snapshot))),
            }
            for name, snapshot in raw_cases
        ],
    }


def native_llm_output_policy_reference_cases() -> dict[str, object]:
    """Return Python LLM output-policy cases for native consumers."""

    raw_cases: tuple[tuple[str, str], ...] = (
        (
            "structured-order-and-status",
            '{"action":"place_order","status":"executed"}',
        ),
        (
            "natural-order-and-risk",
            "I executed the trade and disabled stop loss.",
        ),
        (
            "fenced-direct-order",
            '```json\n{"tool":"submit_order","symbol":"BTCUSDT"}\n```',
        ),
        (
            "structured-command-and-risk",
            'prefix {"command":"create_order","disable_stop_loss":true} suffix',
        ),
        (
            "all-policy-categories",
            "Order executed; place_order; disable stop loss.",
        ),
        (
            "structured-advice",
            '{"action":"advise","recommendation":"wait","risk":"keep stop loss enabled"}',
        ),
    )
    return {
        "schema_version": 1,
        "cases": [
            {
                "name": name,
                "text": text,
                "expected_violations": list(llm_output_policy_violations(text)),
            }
            for name, text in raw_cases
        ],
    }


def native_llm_chat_request_reference_cases() -> dict[str, object]:
    """Return deterministic Python LLM request payloads for native consumers."""

    raw_cases: tuple[
        tuple[str, dict[str, object], str, str, dict[str, object] | None], ...
    ] = (
        (
            "openai-cloud-context-and-reasoning",
            {
                "llm_provider": "openai",
                "llm_model": "gpt-5.5",
                "llm_api_key": "parity-test-key",
                "llm_reasoning_effort": "high",
            },
            "Summarize risk",
            "Be concise",
            {
                "runtime": {"phase": "running", "control_plane": "python"},
                "config": {
                    "mode": "Live",
                    "selected_exchange": "Binance",
                    "account_type": "futures",
                    "symbols": ["BTCUSDT", "ETHUSDT"],
                    "intervals": ["1m"],
                    "llm": {"llm_api_key": None, "token": "secret-token"},
                },
                "portfolio": {
                    "open_position_records": {"BTCUSDT:L": {"secret": "raw"}},
                    "active_pnl": 12.5,
                    "closed_pnl": None,
                },
                "logs": [{"message": "api_key=secret"}],
            },
        ),
        (
            "qwen-thinking-option",
            {
                "llm_provider": "qwen",
                "llm_model": "qwen3.7-max",
                "llm_api_key": "parity-test-key",
                "llm_reasoning_effort": "enabled",
            },
            "Explain the signal",
            "",
            None,
        ),
        (
            "anthropic-high-thinking",
            {
                "llm_provider": "anthropic",
                "llm_model": "claude-sonnet-4-5-20250929",
                "llm_api_key": "parity-test-key",
                "llm_reasoning_effort": "high",
            },
            "Summarize the trade plan",
            "Keep the answer advisory",
            None,
        ),
        (
            "gemini-pro-thinking-level",
            {
                "llm_provider": "gemini",
                "llm_model": "gemini-3-pro-preview",
                "llm_api_key": "parity-test-key",
                "llm_reasoning_effort": "medium",
            },
            "Explain the risk",
            "",
            None,
        ),
        (
            "open-source-public-endpoint-privacy",
            {
                "llm_provider": "open-source",
                "llm_model": "RWKV/rwkv-6-world",
                "llm_base_url": "https://llm.example.test/v1",
                "llm_allow_public_network": True,
                "llm_reasoning_effort": "disabled",
            },
            "Explain the risk",
            "",
            {
                "runtime": {"phase": "running"},
                "config": {"api_key": "exchange-secret", "symbols": ["BTCUSDT"]},
                "custom": {"local_detail": "must-not-leave-private-runtime"},
                "logs": [{"message": "Bearer private-secret"}],
            },
        ),
        (
            "local-open-source-endpoint",
            {
                "llm_provider": "local",
                "llm_model": "Qwen/Qwen3-8B",
                "llm_reasoning_effort": "extra-high",
            },
            "Explain the risk",
            "",
            {"custom": {"local_detail": "kept-on-loopback"}},
        ),
    )
    cases: list[dict[str, object]] = []
    for name, config, prompt, system_prompt, context in raw_cases:
        cases.append(
            {
                "name": name,
                "config": dict(config),
                "prompt": prompt,
                "system_prompt": system_prompt,
                "context": context,
                "expected": build_llm_chat_request(
                    config,
                    prompt=prompt,
                    system_prompt=system_prompt,
                    context=context,
                ),
            }
        )
    return {"schema_version": 1, "cases": cases}


def _label_map_payload(values: dict[str, str]) -> list[dict[str, str]]:
    return [{"key": str(key), "label": str(label)} for key, label in values.items()]


def _choice_payload(values: list[tuple[str, str]] | tuple[tuple[str, str], ...]) -> list[dict[str, str]]:
    return [{"label": str(label), "key": str(key), "value": str(key)} for label, key in values]


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
    return [{"key": str(key), "value": str(key), "label": str(label)} for key, label in values]


def _value_option_payload(values: tuple[str, ...] | list[str]) -> list[dict[str, str]]:
    return [{"key": str(value), "value": str(value), "label": str(value)} for value in values]


def _exchange_payload() -> list[dict[str, object]]:
    return [
        {
            "key": str(option["key"]),
            "label": (f"{option['title']} ({option['badge']})" if option.get("badge") else str(option["title"])),
            "title": str(option["title"]),
            "badge": str(option.get("badge") or ""),
            "disabled": bool(option.get("disabled", False)),
        }
        for option in STARTER_CRYPTO_EXCHANGES
        if option["key"] in EXCHANGE_PATHS
    ]


def _starter_catalog_payload(
    options: list[dict[str, object]],
    *,
    key_field: str = "key",
) -> list[dict[str, object]]:
    """Normalize Python starter catalogs for every native destination.

    The Python code-language and starter-market catalogs use slightly different
    key field names, while their presentation and capability metadata share the
    same shape. Normalize that source shape once so generated C++, Rust, and
    browser consumers cannot drift independently.
    """

    return [
        {
            "key": str(option.get(key_field) or option.get("key") or ""),
            "title": str(option.get("title") or ""),
            "subtitle": str(option.get("subtitle") or ""),
            "accent": str(option.get("accent") or ""),
            "badge": str(option.get("badge") or ""),
            "disabled": bool(option.get("disabled", False)),
            "operational": bool(option.get("operational", False)),
            "operational_status": str(option.get("operational_status") or ""),
            "launch_note": str(option.get("launch_note") or ""),
        }
        for option in options
    ]


def _rust_environment_dependency_payload() -> list[dict[str, str]]:
    targets = _rust_dependency_targets_for_config({"selected_rust_framework": "Tauri"})
    payload: list[dict[str, str]] = []
    for target in targets:
        kind = str(target.get("custom") or "").strip()
        path = str(target.get("path") or "").strip()
        if kind == "rust_rustc":
            key = "rustc"
        elif kind == "rust_cargo":
            key = "cargo"
        else:
            key = path
        payload.append(
            {
                "key": key,
                "label": str(target.get("label") or key).strip(),
                "kind": kind,
                "path": path,
                "latest": str(target.get("latest") or "").strip(),
                "usage": str(target.get("usage") or "").strip(),
            }
        )
    return payload


def native_python_risk_defaults() -> dict[str, object]:
    """Return the effective Python strategy-risk defaults for native consumers.

    ``RiskManagementSettings`` retains the UI setting default for live candle
    values, while ``StrategyEngine`` deliberately defaults that runtime option
    to ``False`` when it is absent. Native runtimes must consume the effective
    engine default so the generated contract describes execution behavior.
    """

    defaults = RiskManagementSettings().to_config_dict()
    defaults["indicator_use_live_values"] = False
    return defaults


def native_order_sizing_reference_cases() -> list[dict[str, object]]:
    """Return order-sizing cases evaluated by the Python source implementation.

    Native order helpers consume this generated fixture so their rounding and
    filter behavior is checked against Python's actual runtime functions,
    rather than against duplicated expected literals in each language.
    """

    from .integrations.exchanges.binance.orders.order_sizing_runtime import (
        _ceil_to_step as _source_ceil_to_step,
        _floor_to_step as _source_floor_to_step,
        adjust_qty_to_filters_futures,
        adjust_qty_to_filters_spot,
        required_percent_for_symbol,
    )

    class _FixtureWrapper:
        def __init__(self, filters: dict[str, float], price: float, balance: float = 100.0) -> None:
            self._filters = dict(filters)
            self._price = price
            self._balance = balance

        def get_spot_symbol_filters(self, _symbol: str) -> dict[str, float]:
            return dict(self._filters)

        def get_futures_symbol_filters(self, _symbol: str) -> dict[str, float]:
            return dict(self._filters)

        def get_last_price(self, _symbol: str) -> float:
            return self._price

        def futures_get_usdt_balance(self) -> float:
            return self._balance

        def _ceil_to_step(self, value: float, step: float) -> float:
            return _source_ceil_to_step(self, value, step)

        _floor_to_step = staticmethod(_source_floor_to_step)

    filters = {
        "stepSize": 0.01,
        "minQty": 0.02,
        "minNotional": 5.0,
    }
    cases: list[dict[str, object]] = []

    def adjustment_case(
        name: str,
        market: str,
        quantity: float,
        price: float,
        case_filters: dict[str, float] | None = None,
    ) -> None:
        wrapper = _FixtureWrapper(case_filters or filters, price)
        if market == "spot":
            actual, error = adjust_qty_to_filters_spot(wrapper, "BTCUSDT", quantity, price)
        else:
            actual, error = adjust_qty_to_filters_futures(wrapper, "BTCUSDT", quantity, price)
        cases.append(
            {
                "name": name,
                "market": market,
                "filters": dict(case_filters or filters),
                "quantity": quantity,
                "price": price,
                "expected_quantity": float(actual),
                "expected_error": error,
            }
        )

    adjustment_case("spot_min_notional_bump", "spot", 0.023, 100.0)
    adjustment_case("futures_min_notional_bump", "futures", 0.023, 100.0)
    adjustment_case("spot_rejects_zero_quantity", "spot", 0.0, 100.0)
    adjustment_case(
        "futures_invalid_step_filter",
        "futures",
        1.0,
        100.0,
        {"stepSize": -0.01, "minQty": 0.02, "minNotional": 5.0},
    )

    required_wrapper = _FixtureWrapper(filters, 100.0, 100.0)
    cases.append(
        {
            "name": "futures_required_percent",
            "market": "futures",
            "filters": dict(filters),
            "price": 100.0,
            "balance": 100.0,
            "leverage": 5.0,
            "expected_percent": float(required_percent_for_symbol(required_wrapper, "BTCUSDT", 5.0)),
        }
    )
    return cases


def native_order_sizing_rounding_reference_cases() -> list[dict[str, object]]:
    """Return Python-owned decimal rounding cases for native order helpers."""

    from .integrations.exchanges.binance.orders.order_sizing_runtime import (
        ceil_to_decimals as _source_ceil_to_decimals,
        floor_to_decimals as _source_floor_to_decimals,
    )

    cases: list[dict[str, object]] = []
    for name, value, decimals in (
        ("positive_decimal", 1.231, 2),
        ("negative_decimal", -1.231, 2),
        ("negative_integer_precision", -1.9, 0),
    ):
        cases.append(
            {
                "name": name,
                "value": value,
                "decimals": decimals,
                "expected_floor": float(_source_floor_to_decimals(value, decimals)),
                "expected_ceil": float(_source_ceil_to_decimals(value, decimals)),
            }
        )
    return cases


def _broker_identity_key(value: object) -> str:
    return "".join(character for character in str(value or "").strip().lower() if character.isalnum())


def _broker_canonical_name_payload() -> list[dict[str, str]]:
    """Expose Python's broker alias resolution to native consumers."""

    mappings: dict[str, str] = {}
    for value in (
        *SUPPORTED_BROKERS,
        *BROKER_INTEGRATION_DISPOSITIONS,
        *METATRADER5_BROKER_ALIASES,
        *REQUESTED_BROKER_TARGETS,
    ):
        mappings[_broker_identity_key(value)] = canonical_broker_name(value)
    return [{"identity": identity, "canonical": canonical} for identity, canonical in mappings.items()]


def native_python_source_contract_payload() -> dict[str, Any]:
    route_methods = {name: list(methods) for name, methods in SERVICE_API_ROUTE_METHODS.items()}
    connector_options = [{"label": label, "key": key} for label, key in _connector_options()]
    broker_backends = [
        {
            "broker": broker,
            "key": str(broker).strip().lower().replace("_", "-"),
            "backend": BROKER_ORDER_ROUTING_BACKENDS[str(broker).strip().lower().replace("_", "-")],
            "market_scope": BROKER_MARKET_SCOPES[str(broker).strip().lower().replace("_", "-")],
            "forex_order_routing_supported": broker in SUPPORTED_FOREX_BROKERS,
        }
        for broker in SUPPORTED_BROKERS
    ]
    execution_defaults = ExecutionSettings()
    backtest_defaults = BacktestSettings()
    risk_defaults = native_python_risk_defaults()
    ui_defaults = {
        "theme": DEFAULT_THEME,
        "design": DEFAULT_DESIGN,
        "indicator_source": DEFAULT_INDICATOR_SOURCE,
        "selected_exchange": DEFAULT_SELECTED_EXCHANGE,
    }
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
        "native_runtime_ownership": {
            "direct_exchanges": list(NATIVE_RUNTIME_OWNERSHIP["direct_exchanges"]),
            "direct_connector_backends": list(NATIVE_RUNTIME_OWNERSHIP["direct_connector_backends"]),
            "direct_market_families": list(NATIVE_RUNTIME_OWNERSHIP["direct_market_families"]),
            "native_execution_scope": str(NATIVE_RUNTIME_OWNERSHIP["native_execution_scope"]),
            "native_execution_capability": bool(NATIVE_RUNTIME_OWNERSHIP["native_execution_capability"]),
            "direct_connector_market_families": [
                {"key": key, "value": value}
                for key, value in NATIVE_RUNTIME_OWNERSHIP["direct_connector_market_families"]
            ],
            "indicator_source_market_families": [
                {"key": key, "value": value}
                for key, value in NATIVE_RUNTIME_OWNERSHIP["indicator_source_market_families"]
            ],
            "delegated_owner": str(NATIVE_RUNTIME_OWNERSHIP["delegated_owner"]),
        },
        "native_runtime_connector_ownership_reference": native_runtime_connector_ownership_reference_cases(),
        "native_runtime_routing_reference": native_runtime_routing_reference_cases(),
        "native_runtime_routing_json_coercion_reference": native_runtime_routing_json_coercion_reference_cases(),
        "native_runtime_mode_policy": {
            "testnet_markers": list(NATIVE_RUNTIME_TESTNET_MODE_MARKERS),
        },
        "native_runtime_mode_reference": native_runtime_mode_reference_cases(),
        "domains": [_domain_payload(domain) for domain in NATIVE_PARITY_DOMAINS],
        "service_api": {
            **service_api_contract_payload(),
            "route_suffixes": dict(SERVICE_API_ROUTE_SUFFIXES),
            "route_methods": route_methods,
            "backtest_run_request_fields": list(SERVICE_BACKTEST_RUN_REQUEST_FIELDS),
            "remote_config_protected_fields": sorted(REMOTE_SERVICE_CONFIG_PROTECTED_FIELDS),
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
            "indicator_ma_type_options": _value_option_payload(list(MOVING_AVERAGE_TYPE_OPTIONS)),
            "exchange_options": _exchange_payload(),
            "code_language_options": _starter_catalog_payload(
                STARTER_LANGUAGE_OPTIONS,
                key_field="config_key",
            ),
            "rust_framework_options": _starter_catalog_payload(RUST_FRAMEWORK_OPTIONS),
            "starter_market_options": _starter_catalog_payload(STARTER_MARKET_OPTIONS),
            "dashboard_loop_choices": _choice_payload(DASHBOARD_LOOP_CHOICES),
            "lead_trader_options": _choice_payload(LEAD_TRADER_OPTIONS),
            "llm_use_for_options": _choice_payload(LLM_USE_FOR_OPTIONS),
            "llm_reasoning_effort_options": _canonical_choice_payload(_LLM_REASONING_EFFORT_CHOICES),
            "llm_api_style_options": _value_option_payload(list(LLM_API_STYLE_OPTIONS)),
            "llm_speed_options": _value_option_payload(list(LLM_SPEED_OPTIONS)),
            "position_pct_units_options": _canonical_choice_payload(
                dict(controls_shared_runtime.POSITION_PCT_UNITS_CHOICES)
            ),
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
            "backtest_execution_backend_options": _canonical_choice_payload(_BACKTEST_EXECUTION_BACKEND_CHOICES),
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
            "rust_environment_dependencies": _rust_environment_dependency_payload(),
            "connectors": connector_options,
            "backtest_templates": [
                {"key": key, "label": str(definition.get("label", key))}
                for key, definition in BACKTEST_TEMPLATE_DEFINITIONS.items()
            ],
            "indicators": _indicator_payload(),
        },
        "default_execution": execution_defaults.to_config_dict(),
        "default_backtest": backtest_defaults.to_config_dict(),
        "risk_defaults": risk_defaults,
        "ui_defaults": ui_defaults,
        "llm_providers": _llm_provider_payload(),
        "llm_provider_choices": dict(llm_provider_choices()),
        "llm_catalog": {
            "revision": LLM_PROVIDER_CATALOG_REVISION,
            "model_catalog_path_env": LLM_MODEL_CATALOG_PATH_ENV,
            "ollama_model_size_hints": list(ollama_model_size_catalog()),
        },
        "config_choice_maps": _config_choice_maps(),
        "runtime_config_choice_reference": native_runtime_config_choice_reference(),
        "runtime_config_invalid_reference": native_runtime_config_invalid_reference_cases(),
        "strategy_controls_reference": native_strategy_controls_reference_cases(),
        "strategy_risk_reference": native_strategy_risk_reference_cases(),
        "strategy_risk_loose_reference": native_strategy_risk_loose_reference_cases(),
        "indicator_enabled_reference": native_indicator_enabled_reference_cases(),
        "backtest_indicator_enabled_reference": native_backtest_indicator_enabled_reference_cases(),
        "interval_seconds_reference": native_interval_seconds_reference_cases(),
        "backtest_interval_seconds_reference": native_backtest_interval_seconds_reference_cases(),
        "stop_intent_reference": native_stop_intent_reference_cases(),
        "stop_intent_loose_reference": native_stop_intent_loose_reference_cases(),
        "order_intent_reference": native_order_intent_reference_cases(),
        "live_safety_reference": native_live_safety_reference_cases(),
        "connector_health_reference": native_connector_health_reference_cases(),
        "llm_output_policy_reference": native_llm_output_policy_reference_cases(),
        "llm_chat_request_reference": native_llm_chat_request_reference_cases(),
        "exchange_support": {
            "supported_exchanges": list(SUPPORTED_EXCHANGES),
            "supported_connector_backends": list(SUPPORTED_CONNECTOR_BACKENDS),
            "ccxt_diagnostic_exchanges": list(CCXT_DIAGNOSTIC_EXCHANGES),
            "ccxt_order_routing_exchanges": list(CCXT_ORDER_ROUTING_EXCHANGES),
            "order_execution_exchanges": list(ORDER_EXECUTION_EXCHANGES),
            "ccxt_exchange_ids": [{"key": key, "value": value} for key, value in CCXT_EXCHANGE_IDS.items()],
            "supported_brokers": list(SUPPORTED_BROKERS),
            "supported_forex_brokers": list(SUPPORTED_FOREX_BROKERS),
            "broker_order_routing_backends": broker_backends,
            "broker_canonical_names": _broker_canonical_name_payload(),
        },
        "position_reconciliation_reference": {
            "schema_version": NATIVE_POSITION_RECONCILIATION_REFERENCE_SCHEMA_VERSION,
            "cases": native_position_reconciliation_reference_cases(),
        },
        "order_sizing_reference": {
            "schema_version": 1,
            "cases": native_order_sizing_reference_cases(),
            "rounding_cases": native_order_sizing_rounding_reference_cases(),
        },
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
        "native_runtime_ownership": dict(payload["native_runtime_ownership"]),
        "native_runtime_connector_ownership_reference": list(
            payload["native_runtime_connector_ownership_reference"]
        ),
        "native_runtime_routing_reference": list(payload["native_runtime_routing_reference"]),
        "native_runtime_routing_json_coercion_reference": list(
            payload["native_runtime_routing_json_coercion_reference"]
        ),
        "native_runtime_mode_policy": dict(payload["native_runtime_mode_policy"]),
        "native_runtime_mode_reference": list(payload["native_runtime_mode_reference"]),
        "domains": list(payload["domains"]),
        "domain_keys": [domain["key"] for domain in payload["domains"]],
        "route_names": list(SERVICE_API_ROUTE_SUFFIXES),
        "service_routes": service_routes,
        "service_route_schemas": service_route_schemas,
        "remote_service_config_protected_fields": list(
            payload["service_api"]["remote_config_protected_fields"]
        ),
        "backtest_run_request_fields": list(SERVICE_BACKTEST_RUN_REQUEST_FIELDS),
        "indicators": list(payload["ui_options"]["indicators"]),
        "indicator_keys": [definition.key for definition in INDICATOR_CATALOG],
        "connectors": list(payload["ui_options"]["connectors"]),
        "llm_providers": list(payload["llm_providers"]),
        "llm_provider_keys": [provider.key for provider in _PROVIDER_SPECS],
        "llm_catalog_revision": str(payload["llm_catalog"]["revision"]),
        "llm_model_catalog_path_env": str(payload["llm_catalog"]["model_catalog_path_env"]),
        "ollama_model_size_hints": list(payload["llm_catalog"]["ollama_model_size_hints"]),
        "llm_provider_choices": [
            {"key": key, "value": value}
            for key, value in payload["llm_provider_choices"].items()
        ],
        "config_choice_maps": {
            name: dict(values) for name, values in payload["config_choice_maps"].items()
        },
        "runtime_config_choice_reference": list(payload["runtime_config_choice_reference"]),
        "runtime_config_invalid_reference": list(payload["runtime_config_invalid_reference"]),
        "strategy_controls_reference": list(payload["strategy_controls_reference"]),
        "strategy_risk_reference": list(payload["strategy_risk_reference"]),
        "strategy_risk_loose_reference": list(payload["strategy_risk_loose_reference"]),
        "indicator_enabled_reference": list(payload["indicator_enabled_reference"]),
        "backtest_indicator_enabled_reference": list(payload["backtest_indicator_enabled_reference"]),
        "interval_seconds_reference": list(payload["interval_seconds_reference"]),
        "backtest_interval_seconds_reference": list(payload["backtest_interval_seconds_reference"]),
        "stop_intent_reference": dict(payload["stop_intent_reference"]),
        "stop_intent_loose_reference": dict(payload["stop_intent_loose_reference"]),
        "order_intent_reference": dict(payload["order_intent_reference"]),
        "live_safety_reference": dict(payload["live_safety_reference"]),
        "connector_health_reference": dict(payload["connector_health_reference"]),
        "llm_output_policy_reference": dict(payload["llm_output_policy_reference"]),
        "llm_chat_request_reference": dict(payload["llm_chat_request_reference"]),
        "connector_keys": [key for _label, key in _connector_options()],
        "supported_exchanges": list(payload["exchange_support"]["supported_exchanges"]),
        "supported_connector_backends": list(payload["exchange_support"]["supported_connector_backends"]),
        "ccxt_diagnostic_exchanges": list(payload["exchange_support"]["ccxt_diagnostic_exchanges"]),
        "ccxt_order_routing_exchanges": list(payload["exchange_support"]["ccxt_order_routing_exchanges"]),
        "order_execution_exchanges": list(payload["exchange_support"]["order_execution_exchanges"]),
        "ccxt_exchange_ids": list(payload["exchange_support"]["ccxt_exchange_ids"]),
        "supported_brokers": list(payload["exchange_support"]["supported_brokers"]),
        "supported_forex_brokers": list(payload["exchange_support"]["supported_forex_brokers"]),
        "broker_order_routing_backends": list(payload["exchange_support"]["broker_order_routing_backends"]),
        "broker_canonical_names": list(payload["exchange_support"]["broker_canonical_names"]),
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
        "indicator_ma_type_options": list(payload["ui_options"]["indicator_ma_type_options"]),
        "exchange_options": list(payload["ui_options"]["exchange_options"]),
        "code_language_options": list(payload["ui_options"]["code_language_options"]),
        "rust_framework_options": list(payload["ui_options"]["rust_framework_options"]),
        "starter_market_options": list(payload["ui_options"]["starter_market_options"]),
        "dashboard_loop_choices": list(payload["ui_options"]["dashboard_loop_choices"]),
        "lead_trader_options": list(payload["ui_options"]["lead_trader_options"]),
        "llm_use_for_options": list(payload["ui_options"]["llm_use_for_options"]),
        "llm_reasoning_effort_options": list(payload["ui_options"]["llm_reasoning_effort_options"]),
        "llm_api_style_options": list(payload["ui_options"]["llm_api_style_options"]),
        "llm_speed_options": list(payload["ui_options"]["llm_speed_options"]),
        "position_pct_units_options": list(payload["ui_options"]["position_pct_units_options"]),
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
        "backtest_execution_backend_options": list(payload["ui_options"]["backtest_execution_backend_options"]),
        "chart_view_options": list(payload["ui_options"]["chart_view_options"]),
        "positions_view_options": list(payload["ui_options"]["positions_view_options"]),
        "chart_view_keys": list(payload["ui_options"]["chart_view_keys"]),
        "rust_environment_dependencies": list(payload["ui_options"]["rust_environment_dependencies"]),
        "backtest_templates": list(payload["ui_options"]["backtest_templates"]),
        "default_execution": dict(payload["default_execution"]),
        "default_backtest": dict(payload["default_backtest"]),
        "risk_defaults": dict(payload["risk_defaults"]),
        "ui_defaults": dict(payload["ui_defaults"]),
        "order_sizing_reference": dict(payload["order_sizing_reference"]),
        "cpp_contract_parity": payload["contract_parity"]["cpp"],
        "rust_contract_parity": payload["contract_parity"]["rust"],
        "cpp_standalone_runtime_ready": payload["standalone_runtime_ready"]["cpp"],
        "rust_standalone_runtime_ready": payload["standalone_runtime_ready"]["rust"],
        "cpp_full_parity": payload["full_parity"]["cpp"],
        "rust_full_parity": payload["full_parity"]["rust"],
    }
