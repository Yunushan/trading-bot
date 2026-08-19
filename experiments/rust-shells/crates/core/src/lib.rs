use std::sync::OnceLock;

use serde_json::Value;
use trading_bot_contracts::AppIdentity;

pub mod account;
pub mod backtest_batch_runtime;
pub mod backtest_runtime;
pub mod chart_heatmap;
pub mod config_persistence;
pub mod desktop_shell;
pub mod diagnostics;
pub mod exchange_connectors;
pub mod generated_python_exchange_support_reference;
pub mod generated_python_indicator_reference;
pub mod generated_python_parity;
pub mod generated_python_portfolio_reference;
pub mod llm_advisory;
pub mod market_data;
pub mod native_indicators;
pub mod native_runtime;
pub mod order_audit;
pub mod order_guard;
pub mod orders;
pub mod portfolio;
pub mod position_close;
pub mod risk;
pub mod runtime_control;
pub mod runtime_order_engine;
pub mod startup_packaging;
pub mod strategy_runtime;
pub mod streams;

mod tls;

pub use generated_python_parity::{
    PythonConnectorOption as NativePythonConnectorOption, PythonIndicator as NativePythonIndicator,
    PythonLlmProvider as NativePythonLlmProvider,
    PythonParityDomain as NativePythonAppParityDomain,
    PythonRustEnvironmentDependency as NativePythonRustEnvironmentDependency,
    PythonServiceRoute as ServiceApiRoute, PythonServiceRouteSchema as ServiceApiRouteSchema,
    PythonStarterOption as NativePythonStarterOption,
    PythonTradingViewInterval as NativePythonTradingViewInterval,
    PythonUiOption as NativePythonUiOption,
};

pub fn app_banner(shell: &str) -> String {
    format!("Trading Bot Rust runtime -> {shell}")
}

pub fn default_identity(shell: &str) -> AppIdentity {
    AppIdentity::new(shell)
}

pub fn supported_frameworks() -> &'static [&'static str] {
    &["Tauri"]
}

pub fn python_source_contract_hash() -> &'static str {
    generated_python_parity::PYTHON_SOURCE_CONTRACT_HASH
}

pub fn python_source_parity_domain_keys() -> &'static [&'static str] {
    generated_python_parity::PYTHON_PARITY_DOMAIN_KEYS
}

pub fn python_source_service_route_names() -> &'static [&'static str] {
    generated_python_parity::PYTHON_SERVICE_ROUTE_NAMES
}

pub fn python_source_service_route_schemas() -> &'static [ServiceApiRouteSchema] {
    generated_python_parity::PYTHON_SERVICE_ROUTE_SCHEMAS
}

pub fn python_source_backtest_run_request_fields() -> &'static [&'static str] {
    generated_python_parity::PYTHON_BACKTEST_RUN_REQUEST_FIELDS
}

pub fn python_source_indicator_keys() -> &'static [&'static str] {
    generated_python_parity::PYTHON_INDICATOR_KEYS
}

pub fn python_source_indicator_catalog() -> &'static [NativePythonIndicator] {
    generated_python_parity::PYTHON_INDICATOR_CATALOG
}

pub fn python_source_llm_provider_keys() -> &'static [&'static str] {
    generated_python_parity::PYTHON_LLM_PROVIDER_KEYS
}

pub fn python_source_llm_providers() -> &'static [NativePythonLlmProvider] {
    generated_python_parity::PYTHON_LLM_PROVIDERS
}

/// Return the Python source-of-truth default model for every LLM provider.
///
/// Keeping this projection in the shared Rust core makes the default-model
/// field part of the native API surface instead of leaving it reachable only
/// through the generated implementation module.
pub fn python_source_llm_provider_default_models() -> Vec<(&'static str, &'static str)> {
    python_source_llm_providers()
        .iter()
        .map(|provider| (provider.key, provider.default_model))
        .collect()
}

pub fn python_source_connector_keys() -> &'static [&'static str] {
    generated_python_parity::PYTHON_CONNECTOR_KEYS
}

pub fn python_source_connector_options() -> &'static [NativePythonConnectorOption] {
    generated_python_parity::PYTHON_CONNECTOR_OPTIONS
}

pub fn python_source_rust_environment_dependencies()
-> &'static [NativePythonRustEnvironmentDependency] {
    generated_python_parity::PYTHON_RUST_ENVIRONMENT_DEPENDENCIES
}

pub fn python_source_backtest_intervals() -> &'static [&'static str] {
    generated_python_parity::PYTHON_BACKTEST_INTERVALS
}

pub fn python_source_tradingview_interval_map() -> &'static [NativePythonTradingViewInterval] {
    generated_python_parity::PYTHON_TRADINGVIEW_INTERVAL_MAP
}

pub fn python_source_default_chart_symbols() -> &'static [&'static str] {
    generated_python_parity::PYTHON_DEFAULT_CHART_SYMBOLS
}

pub fn python_source_default_execution_symbols() -> &'static [&'static str] {
    generated_python_parity::PYTHON_DEFAULT_EXECUTION_SYMBOLS
}

pub fn python_source_default_execution_intervals() -> &'static [&'static str] {
    generated_python_parity::PYTHON_DEFAULT_EXECUTION_INTERVALS
}

pub fn python_source_default_backtest_symbols() -> &'static [&'static str] {
    generated_python_parity::PYTHON_DEFAULT_BACKTEST_SYMBOLS
}

pub fn python_source_default_backtest_intervals() -> &'static [&'static str] {
    generated_python_parity::PYTHON_DEFAULT_BACKTEST_INTERVALS
}

pub fn python_source_default_backtest_config() -> &'static Value {
    static CONFIG: OnceLock<Value> = OnceLock::new();
    CONFIG.get_or_init(|| {
        serde_json::from_str(generated_python_parity::PYTHON_DEFAULT_BACKTEST_JSON)
            .expect("generated Python backtest defaults must be valid JSON")
    })
}

pub fn python_source_default_execution_config() -> &'static Value {
    static CONFIG: OnceLock<Value> = OnceLock::new();
    CONFIG.get_or_init(|| {
        serde_json::from_str(generated_python_parity::PYTHON_DEFAULT_EXECUTION_JSON)
            .expect("generated Python execution defaults must be valid JSON")
    })
}

pub fn python_source_risk_defaults() -> &'static Value {
    static CONFIG: OnceLock<Value> = OnceLock::new();
    CONFIG.get_or_init(|| {
        serde_json::from_str(generated_python_parity::PYTHON_RISK_DEFAULTS_JSON)
            .expect("generated Python risk defaults must be valid JSON")
    })
}

pub fn python_source_ui_defaults() -> &'static Value {
    static CONFIG: OnceLock<Value> = OnceLock::new();
    CONFIG.get_or_init(|| {
        serde_json::from_str(generated_python_parity::PYTHON_UI_DEFAULTS_JSON)
            .expect("generated Python UI defaults must be valid JSON")
    })
}

pub fn python_source_chart_market_options() -> &'static [&'static str] {
    generated_python_parity::PYTHON_CHART_MARKET_OPTIONS
}

pub fn python_source_account_mode_options() -> &'static [&'static str] {
    generated_python_parity::PYTHON_ACCOUNT_MODE_OPTIONS
}

pub fn python_source_dashboard_loop_choices() -> &'static [NativePythonUiOption] {
    generated_python_parity::PYTHON_DASHBOARD_LOOP_CHOICES
}

pub fn python_source_lead_trader_options() -> &'static [NativePythonUiOption] {
    generated_python_parity::PYTHON_LEAD_TRADER_OPTIONS
}

pub fn python_source_llm_use_for_options() -> &'static [NativePythonUiOption] {
    generated_python_parity::PYTHON_LLM_USE_FOR_OPTIONS
}

pub fn python_source_dashboard_strategy_templates() -> &'static [NativePythonUiOption] {
    generated_python_parity::PYTHON_DASHBOARD_STRATEGY_TEMPLATES
}

pub fn python_source_backtest_templates() -> &'static [NativePythonUiOption] {
    generated_python_parity::PYTHON_BACKTEST_TEMPLATES
}

pub fn python_source_side_options() -> &'static [NativePythonUiOption] {
    generated_python_parity::PYTHON_SIDE_OPTIONS
}

pub fn python_source_config_mode_options() -> &'static [NativePythonUiOption] {
    generated_python_parity::PYTHON_CONFIG_MODE_OPTIONS
}

pub fn python_source_theme_options() -> &'static [NativePythonUiOption] {
    generated_python_parity::PYTHON_THEME_OPTIONS
}

pub fn python_source_design_options() -> &'static [NativePythonUiOption] {
    generated_python_parity::PYTHON_DESIGN_OPTIONS
}

pub fn python_source_indicator_source_options() -> &'static [NativePythonUiOption] {
    generated_python_parity::PYTHON_INDICATOR_SOURCE_OPTIONS
}

pub fn python_source_indicator_ma_type_options() -> &'static [NativePythonUiOption] {
    generated_python_parity::PYTHON_INDICATOR_MA_TYPE_OPTIONS
}

pub fn python_source_exchange_options() -> &'static [NativePythonUiOption] {
    generated_python_parity::PYTHON_EXCHANGE_OPTIONS
}

pub fn python_source_code_language_options() -> &'static [NativePythonStarterOption] {
    generated_python_parity::PYTHON_CODE_LANGUAGE_OPTIONS
}

pub fn python_source_rust_framework_options() -> &'static [NativePythonStarterOption] {
    generated_python_parity::PYTHON_RUST_FRAMEWORK_OPTIONS
}

pub fn python_source_starter_market_options() -> &'static [NativePythonStarterOption] {
    generated_python_parity::PYTHON_STARTER_MARKET_OPTIONS
}

pub fn python_source_account_type_options() -> &'static [NativePythonUiOption] {
    generated_python_parity::PYTHON_ACCOUNT_TYPE_OPTIONS
}

pub fn python_source_margin_mode_options() -> &'static [NativePythonUiOption] {
    generated_python_parity::PYTHON_MARGIN_MODE_OPTIONS
}

pub fn python_source_position_mode_options() -> &'static [NativePythonUiOption] {
    generated_python_parity::PYTHON_POSITION_MODE_OPTIONS
}

pub fn python_source_assets_mode_options() -> &'static [NativePythonUiOption] {
    generated_python_parity::PYTHON_ASSETS_MODE_OPTIONS
}

pub fn python_source_order_type_options() -> &'static [NativePythonUiOption] {
    generated_python_parity::PYTHON_ORDER_TYPE_OPTIONS
}

pub fn python_source_time_in_force_options() -> &'static [NativePythonUiOption] {
    generated_python_parity::PYTHON_TIME_IN_FORCE_OPTIONS
}

pub fn python_source_signal_logic_options() -> &'static [NativePythonUiOption] {
    generated_python_parity::PYTHON_SIGNAL_LOGIC_OPTIONS
}

pub fn python_source_mdd_logic_options() -> &'static [NativePythonUiOption] {
    generated_python_parity::PYTHON_MDD_LOGIC_OPTIONS
}

pub fn python_source_stop_loss_modes() -> &'static [NativePythonUiOption] {
    generated_python_parity::PYTHON_STOP_LOSS_MODES
}

pub fn python_source_stop_loss_scopes() -> &'static [NativePythonUiOption] {
    generated_python_parity::PYTHON_STOP_LOSS_SCOPES
}

pub fn python_source_scan_scope_options() -> &'static [NativePythonUiOption] {
    generated_python_parity::PYTHON_SCAN_SCOPE_OPTIONS
}

pub fn python_source_optimizer_mode_options() -> &'static [NativePythonUiOption] {
    generated_python_parity::PYTHON_OPTIMIZER_MODE_OPTIONS
}

pub fn python_source_optimizer_metric_options() -> &'static [NativePythonUiOption] {
    generated_python_parity::PYTHON_OPTIMIZER_METRIC_OPTIONS
}

pub fn python_source_backtest_execution_backend_options() -> &'static [NativePythonUiOption] {
    generated_python_parity::PYTHON_BACKTEST_EXECUTION_BACKEND_OPTIONS
}

pub fn python_source_chart_view_options() -> &'static [NativePythonUiOption] {
    generated_python_parity::PYTHON_CHART_VIEW_OPTIONS
}

pub fn python_source_positions_view_options() -> &'static [NativePythonUiOption] {
    generated_python_parity::PYTHON_POSITIONS_VIEW_OPTIONS
}

pub fn python_source_cpp_contract_parity_ready() -> bool {
    generated_python_parity::CPP_CONTRACT_PARITY_READY
}

pub fn python_source_rust_contract_parity_ready() -> bool {
    generated_python_parity::RUST_CONTRACT_PARITY_READY
}

pub fn python_source_cpp_standalone_runtime_ready() -> bool {
    generated_python_parity::CPP_STANDALONE_RUNTIME_READY
}

pub fn python_source_rust_standalone_runtime_ready() -> bool {
    generated_python_parity::RUST_STANDALONE_RUNTIME_READY
}

pub fn python_source_cpp_full_parity_ready() -> bool {
    generated_python_parity::CPP_FULL_PARITY_READY
}

pub fn python_source_rust_full_parity_ready() -> bool {
    generated_python_parity::RUST_FULL_PARITY_READY
}

pub struct TradingAppTab {
    pub key: &'static str,
    pub title: &'static str,
    pub status: &'static str,
    pub primary_metric: &'static str,
    pub secondary_metric: &'static str,
    pub summary: &'static str,
    pub actions: &'static [&'static str],
    pub sections: &'static [TradingAppSection],
    pub tables: &'static [TradingAppTable],
}

pub struct TradingAppSection {
    pub title: &'static str,
    pub items: &'static [&'static str],
}

pub struct TradingAppTable {
    pub title: &'static str,
    pub columns: &'static [&'static str],
}

pub struct ServiceApiCapability {
    pub title: &'static str,
    pub detail: &'static str,
}

pub struct RustExecutionMode {
    pub key: &'static str,
    pub title: &'static str,
    pub detail: &'static str,
    pub trading_execution_supported: bool,
}

pub struct RustShellFrameworkParity {
    pub framework: &'static str,
    pub status: &'static str,
    pub detail: &'static str,
}

pub struct RustNativeRuntimeCapability {
    pub key: &'static str,
    pub title: &'static str,
    pub cpp_status: &'static str,
    pub rust_status: &'static str,
    pub required_before_enable: &'static str,
    pub trading_execution_supported: bool,
}

pub const SERVICE_API_BASE_PATH: &str = "/api/v1";

pub fn rust_trading_execution_supported() -> bool {
    python_source_rust_full_parity_ready()
}

pub fn rust_native_trading_runtime_ready() -> bool {
    python_source_rust_full_parity_ready()
}

pub fn cpp_entire_python_app_contract_parity_ready() -> bool {
    native_python_app_parity_domains()
        .iter()
        .all(|domain| domain.cpp_full_parity)
}

pub fn rust_entire_python_app_contract_parity_ready() -> bool {
    native_python_app_parity_domains()
        .iter()
        .all(|domain| domain.rust_full_parity)
}

pub fn native_python_app_contract_parity_ready() -> bool {
    cpp_entire_python_app_contract_parity_ready() && rust_entire_python_app_contract_parity_ready()
}

pub fn cpp_entire_python_app_parity_ready() -> bool {
    python_source_cpp_full_parity_ready()
}

pub fn rust_entire_python_app_parity_ready() -> bool {
    python_source_rust_full_parity_ready()
}

pub fn native_full_python_app_parity_ready() -> bool {
    cpp_entire_python_app_parity_ready() && rust_entire_python_app_parity_ready()
}

pub fn rust_execution_modes() -> &'static [RustExecutionMode] {
    &[
        RustExecutionMode {
            key: "service_client",
            title: "Service client",
            detail: "Rust shells read dashboard state and submit lifecycle/config/backtest requests through the canonical Python Service API.",
            trading_execution_supported: false,
        },
        RustExecutionMode {
            key: "tauri_managed_service",
            title: "Tauri managed local service",
            detail: "Tauri may launch apps/service-api/main.py locally, but the Python runtime remains the only active strategy, risk, and exchange execution owner.",
            trading_execution_supported: false,
        },
        RustExecutionMode {
            key: "native_engine_future",
            title: "Native Rust trading engine",
            detail: "Runs the native guarded strategy, account, market-data, exposure, audit, and circuit-breaker path in forced dry-run mode until credentialed and release promotion evidence is complete.",
            trading_execution_supported: false,
        },
    ]
}

pub fn native_python_app_parity_domains() -> &'static [NativePythonAppParityDomain] {
    generated_python_parity::PYTHON_PARITY_DOMAINS
}

pub fn rust_shell_framework_parity() -> &'static [RustShellFrameworkParity] {
    &[RustShellFrameworkParity {
        framework: "Tauri",
        status: "Operational Service API client",
        detail: "Runs the only user-selectable Rust desktop shell with live Python Service API start/stop, authenticated dashboard SSE hydration with reconnect/snapshot fallback, config hydration, backtest scanner, dashboard import, logs, LLM advisory prompts, and local LLM model lifecycle controls; trading execution still belongs to Python.",
    }]
}

pub fn rust_native_runtime_capabilities() -> &'static [RustNativeRuntimeCapability] {
    &[
        RustNativeRuntimeCapability {
            key: "market_data_rest",
            title: "REST market data",
            cpp_status: "C++ has BinanceRestClient fetchUsdtSymbols, fetchKlines, and fetchTickerPrice.",
            rust_status: "Rust core now has BinanceRestMarketDataClient for native exchangeInfo USDT symbols, optional 24h quote-volume ordering, native and custom-aggregated klines, ticker prices, and Binance error payload handling.",
            required_before_enable: "Collect/import live-network market smoke evidence where credentials/network policy allow it, then finish connector support metadata, rate-limit diagnostics, and integration with live runtime network ingestion.",
            trading_execution_supported: false,
        },
        RustNativeRuntimeCapability {
            key: "market_data_websocket",
            title: "WebSocket market stream",
            cpp_status: "C++ has BinanceWsClient connectBookTicker/connectKline plus dashboardRuntimeSignalSockets and candle caches.",
            rust_status: "Rust core now has BinanceWebSocketClient URL construction, tungstenite connection entry points, book ticker/kline message parsing for Binance spot and futures streams, reconnect/backoff decisions, kline cache staleness guards, a deterministic stream supervisor state machine, and a live stream ingestion bridge that feeds WebSocket event/close/error results into the runtime loop coordinator.",
            required_before_enable: "Collect live-network WebSocket smoke evidence before live signal evaluation and standalone native trading.",
            trading_execution_supported: false,
        },
        RustNativeRuntimeCapability {
            key: "account_positions",
            title: "Account, balance, and positions",
            cpp_status: "C++ can fetch USDT/collateral balance, open futures positions, futures settings, force-order history, isolated position-margin cleanup, and Spot trade history, then reconcile positions into the positions table.",
            rust_status: "Rust core now has BinanceSignedRestClient for signed USDT balance snapshots, normalized balance rows, open futures position parsing with account-position overlays, futures position-mode get/change request foundations, futures margin-type/leverage/multi-assets request and parser foundations, signed force-order history, isolated position-margin cleanup, signed Spot trade history, close-position planning foundations, native runtime hedge/one-way close planning, account-mode reconciliation, futures-settings reconciliation snapshots, a native account preflight gate, native operational preflight gate, and portfolio/history/allocation/reconciliation tests.",
            required_before_enable: "Collect/import signed credential-gated live-smoke evidence and broader supervised execution integration before enabling native trading.",
            trading_execution_supported: false,
        },
        RustNativeRuntimeCapability {
            key: "order_submission",
            title: "Order submission",
            cpp_status: "C++ has placeFuturesMarketOrder/placeFuturesLimitOrder and dashboard open/close fallback helpers.",
            rust_status: "Rust core now has Binance futures symbol filters, signed market/limit order request construction, order submit guard and order audit/circuit-breaker foundations, risk/stop-loss close-decision planning, reduce-only hedge-mode rules, close-position and closePosition planning, POST submission hooks, order response parsing, and a runtime-owned order engine for guarded submit, deterministic dry-run audit, redacted audit JSONL, connector circuit incident persistence, and submit reconciliation.",
            required_before_enable: "Collect/import credential-gated smoke evidence, supervised runtime lifecycle tests, and runtime-owned recovery gates before enabling native trading.",
            trading_execution_supported: false,
        },
        RustNativeRuntimeCapability {
            key: "runtime_lifecycle",
            title: "Runtime lifecycle loop",
            cpp_status: "C++ has startDashboardRuntime, runDashboardRuntimeCycle, stopDashboardRuntime, timer state, retry windows, and open-position tracking.",
            rust_status: "Rust core now has Desktop shell/tab lifecycle contracts plus strategy runtime signal/control/provenance helpers, worker lifecycle snapshots, core stop/shutdown guard result builders, a native runtime loop coordinator that owns stream supervisor, pause, stop, shutdown, idle transitions, hedge/one-way close planning snapshots, account-mode reconciliation, futures-settings reconciliation for margin mode, leverage, and assets mode before signal evaluation, a native account preflight gate that combines account mode plus futures settings, and a native operational preflight gate for live/demo start and order readiness, plus a mockable live ingestion bridge in dry-run coordination mode; Tauri may start/stop the Python Service API but standalone Rust trading remains disabled.",
            required_before_enable: "Collect/import credential-gated smoke evidence, live recovery evidence, and release evidence before enabling standalone Rust trading.",
            trading_execution_supported: false,
        },
        RustNativeRuntimeCapability {
            key: "risk_and_shutdown_guards",
            title: "Risk and shutdown guards",
            cpp_status: "C++ tracks stop-loss settings, quantity caps, retry-after windows, close-on-stop behavior, connector warnings, and forced close fallbacks.",
            rust_status: "Rust core now has stop-loss setting normalization plus per-trade, directional, cumulative, entire-account, close-opposite planning foundations, a runtime-owned risk/close execution path for stop-loss and close-opposite reconciliation, Python-compatible shutdown guard result tests, native runtime loop stop/idle wiring, and a portfolio-aware exposure guard for target margin, available balance, side cap, filter headroom, and one-way add-only reduce-only checks.",
            required_before_enable: "Add credential-gated regression tests, live recovery evidence, and release evidence before enabling native trading.",
            trading_execution_supported: false,
        },
    ]
}

pub fn service_api_capabilities() -> &'static [ServiceApiCapability] {
    &[
        ServiceApiCapability {
            title: "Managed Local Service API",
            detail: "Tauri is the only Rust desktop shell that can launch apps/service-api/main.py --serve on 127.0.0.1 and stop only the process it started.",
        },
        ServiceApiCapability {
            title: "Canonical /api/v1 Contract",
            detail: "Rust shells expose the full canonical Python Service API route catalog, including runtime, dashboard, status, stream, config persistence, control, connector circuit, account, portfolio, terminal, LLM, logs, and backtest routes.",
        },
        ServiceApiCapability {
            title: "Logs, Terminal & Diagnostics",
            detail: "trading-bot-core mirrors Python service log and controlled terminal result schemas with diagnostic redaction; Tauri delegates /logs and terminal_run behavior to the Python Service API.",
        },
        ServiceApiCapability {
            title: "Config Hydration",
            detail: "Tauri refreshes dashboard/config snapshots and direct account, portfolio, exchange connector, and service logs snapshots, then hydrates visible runtime, account, config persistence state/path, stop-loss, LLM, symbol, interval, strategy, backtest, and logs controls; trading-bot-core mirrors the Python config persistence envelope/status helpers, path-safety checks, and secret-redaction contract.",
        },
        ServiceApiCapability {
            title: "Operational Preflight Start Gate",
            detail: "Tauri formats the operational_preflight payload, shows start/orders/mode/critical/age details, blocks Start Bot when start.allowed is false, and surfaces connector order circuit breaker state with reset control.",
        },
        ServiceApiCapability {
            title: "Backtest Scanner & Dashboard Import",
            detail: "Tauri can submit scanner backtests, poll until idle, select the best max-drawdown candidate, and import selected or all backtest rows into dashboard symbol/interval overrides.",
        },
        ServiceApiCapability {
            title: "LLM Advisory & Local Lifecycle",
            detail: "Tauri applies LLM settings, prepares dry-run advisory prompt requests, can send confirmed advisory prompts through llm_prompt, and checks/starts/pulls/deletes local Ollama models through llm_local_model_status/start/pull/delete routes after user confirmation.",
        },
        ServiceApiCapability {
            title: "Execution Boundary",
            detail: "Python service/desktop runtime remains the trading execution owner; Rust shells are clients and must not bypass strategy, risk, or exchange guards. trading-bot-core includes strategy runtime signal/control/provenance helpers for parity validation without enabling standalone native trading.",
        },
        ServiceApiCapability {
            title: "Native Runtime Gap",
            detail: "C++ already has Binance REST/WebSocket and dashboard runtime experiments; Rust has Desktop shell/tab lifecycle contracts and strategy runtime parity helpers, while standalone Rust trading remains blocked until rust_native_runtime_capabilities are safe to enable.",
        },
    ]
}

pub fn service_api_routes() -> &'static [ServiceApiRoute] {
    generated_python_parity::PYTHON_SERVICE_ROUTES
}

pub fn service_api_route_path(name: &str) -> Option<&'static str> {
    service_api_routes()
        .iter()
        .find(|route| route.name == name)
        .map(|route| route.path)
}

pub fn service_api_route_methods(name: &str) -> Option<&'static [&'static str]> {
    service_api_routes()
        .iter()
        .find(|route| route.name == name)
        .map(|route| route.methods)
}

pub fn service_api_route_supports_method(name: &str, method: &str) -> bool {
    let normalized = method.trim();
    !normalized.is_empty()
        && service_api_route_methods(name).is_some_and(|methods| {
            methods
                .iter()
                .any(|candidate| candidate.eq_ignore_ascii_case(normalized))
        })
}

pub fn service_api_route_schema(name: &str) -> Option<&'static ServiceApiRouteSchema> {
    python_source_service_route_schemas()
        .iter()
        .find(|schema| schema.name == name)
}

pub fn service_api_route_query_fields(name: &str) -> Option<&'static [&'static str]> {
    service_api_route_schema(name).map(|schema| schema.query_fields)
}

pub fn service_api_route_request_fields(name: &str) -> Option<&'static [&'static str]> {
    service_api_route_schema(name).map(|schema| schema.request_fields)
}

pub fn service_api_route_supports_query_field(name: &str, field: &str) -> bool {
    service_api_route_query_fields(name).is_some_and(|fields| fields.contains(&field))
}

pub fn service_api_route_supports_request_field(name: &str, field: &str) -> bool {
    service_api_route_request_fields(name).is_some_and(|fields| fields.contains(&field))
}

pub fn trading_app_tabs() -> &'static [TradingAppTab] {
    &[
        TradingAppTab {
            key: "dashboard",
            title: "Dashboard",
            status: "Bot Status: OFF",
            primary_metric: "Active PNL: 0.00 USDT",
            secondary_metric: "Closed PNL: 0.00 USDT",
            summary: "Main desktop trading controls mirrored from the Python and C++ dashboards.",
            actions: &["Start", "Stop", "Save Config", "Load Config"],
            sections: &[
                TradingAppSection {
                    title: "Account & Status",
                    items: &[
                        "API Key:",
                        "API Secret Key:",
                        "Mode: Python source parity options",
                        "Theme: Python source parity options",
                        "Account Type: Python source parity options",
                        "Account Mode: Python source parity options",
                        "Connector: Python source parity options",
                        "Total USDT balance: N/A",
                        "Position Mode: N/A",
                        "Refresh Balance",
                        "Leverage (Futures): 1-150",
                        "Margin Mode (Futures): Python source parity options",
                        "Position Mode: Python source parity options",
                        "Assets Mode: Python source parity options",
                        "Time-in-Force: Python source parity options",
                        "GTD minutes: 1-1440",
                        "Indicator Source: Python source parity options",
                    ],
                },
                TradingAppSection {
                    title: "AI / LLM Settings",
                    items: &[
                        "Enable LLM assistance",
                        "Allow public network endpoint",
                        "Provider: Python source parity options",
                        "Model: Python source parity options",
                        "Base URL / IP:",
                        "API key env:",
                        "API token:",
                        "Use for: Python source parity options",
                        "Reasoning / Thinking:",
                        "Apply LLM Settings",
                        "Local model status",
                        "Check / Download Local Model: starts Ollama when confirmed and pulls the selected local model when missing",
                        "Remove Local Model: deletes the selected local model when confirmed",
                        "Advisory Prompt",
                        "System Prompt",
                        "Prepare Advisory Request",
                        "Run Advisory",
                        "LLM advisory result",
                    ],
                },
                TradingAppSection {
                    title: "Exchange",
                    items: &[
                        "Select exchange",
                        "Binance",
                        "Bybit (ccxt order routing)",
                        "OKX (ccxt order routing)",
                        "Gate (ccxt order routing)",
                        "Bitget (ccxt order routing)",
                        "MEXC (ccxt order routing)",
                        "KuCoin (ccxt order routing)",
                        "HTX (ccxt order routing)",
                        "Crypto.com Exchange (ccxt order routing)",
                        "Kraken (ccxt order routing)",
                        "Bitfinex (ccxt order routing)",
                    ],
                },
                TradingAppSection {
                    title: "Markets & Intervals",
                    items: &[
                        "Symbols (select 1 or more):",
                        "Default symbols: Python source parity defaults",
                        "Refresh Symbols",
                        "Intervals (select 1 or more):",
                        "Default intervals: Python source parity defaults",
                        "Custom interval input: e.g., 45s or 7m or 90m, comma-separated",
                        "Add Custom Interval(s)",
                    ],
                },
                TradingAppSection {
                    title: "Strategy Controls",
                    items: &[
                        "Side: Python source parity options",
                        "Position % of Balance:",
                        "Loop Interval Override: Python source parity options",
                        "Enable Lead Trader",
                        "Lead Trader: Futures Public Lead Trader, Futures Private Lead Trader, Spot Public Lead Trader, Spot Private Lead Trader",
                        "Use live candle values for signals (repaints)",
                        "Add-only in current net direction (one-way)",
                        "Allow simultaneous long & short positions (hedge stacking)",
                        "Stop Bot Without Closing Active Positions",
                        "Market Close All Active Positions On Window Close (Working in progress)",
                        "Stop Loss: Enable",
                        "Stop Loss Mode: USDT Based Stop Loss, Percentage Based Stop Loss, Both Stop Loss (USDT & Percentage)",
                        "Stop Loss USDT",
                        "Stop Loss %",
                        "Stop Loss Scope: Per Trade Stop Loss, Cumulative Stop Loss, Entire Account Stop Loss",
                        "Template: No Template, Top 10 %2 per trade 1x Isolated, Top 50 %2 per trade 1x, Top 100 %1 per trade 1x",
                    ],
                },
                TradingAppSection {
                    title: "Indicators",
                    items: &[
                        "Moving Average (MA) + Buy-Sell Values",
                        "Donchian Channels (DC) + Buy-Sell Values",
                        "Parabolic SAR (PSAR) + Buy-Sell Values",
                        "Bollinger Bands (BB) + Buy-Sell Values",
                        "Bollinger Band Width (BBW) + Buy-Sell Values",
                        "Keltner Channels (KC) + Buy-Sell Values",
                        "Ichimoku Cloud (IC) + Buy-Sell Values",
                        "Relative Strength Index (RSI) + Buy-Sell Values",
                        "Volume + Buy-Sell Values",
                        "On-Balance Volume (OBV) + Buy-Sell Values",
                        "Relative Volume (RVOL) + Buy-Sell Values",
                        "Chaikin Money Flow (CMF) + Buy-Sell Values",
                        "Commodity Channel Index (CCI) + Buy-Sell Values",
                        "Rate of Change (ROC) + Buy-Sell Values",
                        "Triple Exponential Average (TRIX) + Buy-Sell Values",
                        "Percentage Price Oscillator (PPO) + Buy-Sell Values",
                        "Awesome Oscillator (AO) + Buy-Sell Values",
                        "Know Sure Thing (KST) + Buy-Sell Values",
                        "Aroon Oscillator (AROON) + Buy-Sell Values",
                        "Choppiness Index (CHOP) + Buy-Sell Values",
                        "Average True Range (ATR) + Buy-Sell Values",
                        "Normalized Average True Range (NATR) + Buy-Sell Values",
                        "Volume Weighted Average Price (VWAP) + Buy-Sell Values",
                        "Money Flow Index (MFI) + Buy-Sell Values",
                        "Stochastic RSI (SRSI) + Buy-Sell Values",
                        "Williams %R + Buy-Sell Values",
                        "Moving Average Convergence/Divergence (MACD) + Buy-Sell Values",
                        "Ultimate Oscillator (UO) + Buy-Sell Values",
                        "Average Directional Index (ADX) + Buy-Sell Values",
                        "Directional Movement Index (DMI) + Buy-Sell Values",
                        "SuperTrend (ST) + Buy-Sell Values",
                        "Exponential Moving Average (EMA) + Buy-Sell Values",
                        "Stochastic Oscillator + Buy-Sell Values",
                    ],
                },
                TradingAppSection {
                    title: "Symbol / Interval Overrides",
                    items: &[
                        "Columns: Symbol, Interval, Indicators, Loop, Leverage, Connector, Strategy Controls, Stop-Loss",
                        "Add Selected",
                        "Remove Selected",
                        "Clear All",
                    ],
                },
                TradingAppSection {
                    title: "Desktop Service API",
                    items: &[
                        "Enable",
                        "Host: 127.0.0.1",
                        "Port: 8000",
                        "Token: Session only; not saved to app state",
                        "Start / Connect API",
                        "Stop API",
                        "Open Dashboard",
                        "Service API: off",
                        "Preflight: unknown",
                        "Recheck Preflight",
                    ],
                },
                TradingAppSection {
                    title: "Logs",
                    items: &[
                        "All Logs",
                        "Position Trigger Logs",
                        "Waiting Positions (Queue)",
                        "Refresh Logs",
                    ],
                },
            ],
            tables: &[
                TradingAppTable {
                    title: "Symbol / Interval Overrides",
                    columns: &[
                        "Symbol",
                        "Interval",
                        "Indicators",
                        "Loop",
                        "Leverage",
                        "Connector",
                        "Strategy Controls",
                        "Stop-Loss",
                    ],
                },
                TradingAppTable {
                    title: "Waiting Positions (Queue)",
                    columns: &["Symbol", "Interval", "Side", "Context", "State", "Age (s)"],
                },
            ],
        },
        TradingAppTab {
            key: "chart",
            title: "Chart",
            status: "Chart ready.",
            primary_metric: "Market: Futures",
            secondary_metric: "View: TradingView",
            summary: "Chart tab controls mirrored from the Python and C++ chart surfaces.",
            actions: &["Refresh", "Open In Browser"],
            sections: &[
                TradingAppSection {
                    title: "Chart Controls",
                    items: &[
                        "Market: Futures, Spot",
                        "Symbol: BTCUSDT, ETHUSDT, BNBUSDT, SOLUSDT, XRPUSDT, ADAUSDT, DOGEUSDT, AVAXUSDT, LINKUSDT, TRXUSDT",
                        "Interval: 1m, 3m, 5m, 10m, 15m, 20m, 30m, 1h, 2h, 3h, 4h, 5h, 6h, 7h, 8h, 9h, 10h, 11h, 12h, 1d, 2d, 3d, 4d, 5d, 6d, 1w, 2w, 3w, 1month, 2months, 3months, 6months, 1mo, 2mo, 3mo, 6mo, 1y, 2y",
                        "View: TradingView, Original, TradingView Lightweight",
                        "Total PNL Active Positions: --",
                        "Total PNL Closed Positions: --",
                        "Bot Status: OFF",
                        "Bot Active Time: --",
                    ],
                },
                TradingAppSection {
                    title: "Chart View Stack",
                    items: &[
                        "TradingView",
                        "Original",
                        "TradingView Lightweight",
                        "Chart ready.",
                        "Open In Browser URL: https://www.tradingview.com/chart/?symbol=BINANCE:BTCUSDT.P&interval=1",
                    ],
                },
            ],
            tables: &[],
        },
        TradingAppTab {
            key: "positions",
            title: "Positions",
            status: "Bot Status: OFF",
            primary_metric: "Total Balance: --",
            secondary_metric: "Available Balance: --",
            summary: "Positions tab controls and table columns mirrored from Python and C++.",
            actions: &[
                "Refresh Positions",
                "Market Close ALL Positions",
                "Clear Selected",
                "Clear All",
            ],
            sections: &[TradingAppSection {
                title: "Position Controls",
                items: &[
                    "Positions View: Cumulative View, Per Trade View",
                    "Auto Row Height",
                    "Auto Column Width",
                    "Total PNL Active Positions: --",
                    "Total PNL Closed Positions: --",
                    "Total Balance: --",
                    "Available Balance: --",
                    "Bot Status: OFF",
                    "Bot Active Time: --",
                ],
            }],
            tables: &[TradingAppTable {
                title: "Positions",
                columns: &[
                    "Symbol",
                    "Size (USDT)",
                    "Last Price (USDT)",
                    "Margin Ratio",
                    "Liq Price (USDT)",
                    "Margin (USDT)",
                    "Quantity (Qty)",
                    "PNL (ROI%)",
                    "Interval",
                    "Indicator",
                    "Triggered Indicator Value",
                    "Current Indicator Value",
                    "Side",
                    "Open Time",
                    "Close Time",
                    "Stop-Loss",
                    "Status",
                    "Close",
                ],
            }],
        },
        TradingAppTab {
            key: "backtest",
            title: "Backtest",
            status: "Backtest idle",
            primary_metric: "Backtest Output",
            secondary_metric: "Max MDD Scanner",
            summary: "Backtest controls, indicators, scanner, and results table mirrored from Python and C++.",
            actions: &[
                "Run Backtest",
                "Stop",
                "Add Selected to Dashboard",
                "Add All to Dashboard",
                "Scan Symbols",
            ],
            sections: &[
                TradingAppSection {
                    title: "Markets",
                    items: &[
                        "Symbol Source: Python source parity options",
                        "Refresh",
                        "Symbols (select 1 or more):",
                        "Default symbols: Python source parity defaults",
                        "Intervals (select 1 or more):",
                        "Default intervals: Python source parity defaults",
                        "Custom interval input: e.g., 45s or 7m or 90m, comma-separated",
                        "Add Custom Interval(s)",
                    ],
                },
                TradingAppSection {
                    title: "Backtest Parameters",
                    items: &[
                        "Start Date/Time:",
                        "End Date/Time:",
                        "Signal Logic: Python source parity options",
                        "MDD Logic: Python source parity options",
                        "Margin Capital:",
                        "Position % of Balance:",
                        "Loop Interval Override: Python source parity options",
                        "Stop Loss: Enable, mode, Scope, USDT, %",
                        "Side: Python source parity options",
                        "Margin Mode (Futures): Python source parity options",
                        "Position Mode: Python source parity options",
                        "Assets Mode: Python source parity options",
                        "Account Mode: Python source parity options",
                        "Connector: Python source parity options",
                        "Leverage (Futures):",
                        "Template: Python source parity options",
                        "Max MDD Scanner Top N:",
                        "Max MDD Scanner Max MDD %:",
                        "Scan Symbols",
                        "Scanner status text",
                        "Scanner best candidate summary",
                        "Pair overrides: symbol, interval, indicators, strategy, connector, leverage, and stop-loss",
                    ],
                },
                TradingAppSection {
                    title: "Indicators",
                    items: &[
                        "Moving Average (MA) + Buy-Sell Values",
                        "Donchian Channels (DC) + Buy-Sell Values",
                        "Parabolic SAR (PSAR) + Buy-Sell Values",
                        "Bollinger Bands (BB) + Buy-Sell Values",
                        "Bollinger Band Width (BBW) + Buy-Sell Values",
                        "Keltner Channels (KC) + Buy-Sell Values",
                        "Ichimoku Cloud (IC) + Buy-Sell Values",
                        "Relative Strength Index (RSI) + Buy-Sell Values",
                        "Volume + Buy-Sell Values",
                        "On-Balance Volume (OBV) + Buy-Sell Values",
                        "Relative Volume (RVOL) + Buy-Sell Values",
                        "Chaikin Money Flow (CMF) + Buy-Sell Values",
                        "Commodity Channel Index (CCI) + Buy-Sell Values",
                        "Rate of Change (ROC) + Buy-Sell Values",
                        "Triple Exponential Average (TRIX) + Buy-Sell Values",
                        "Percentage Price Oscillator (PPO) + Buy-Sell Values",
                        "Awesome Oscillator (AO) + Buy-Sell Values",
                        "Know Sure Thing (KST) + Buy-Sell Values",
                        "Aroon Oscillator (AROON) + Buy-Sell Values",
                        "Choppiness Index (CHOP) + Buy-Sell Values",
                        "Average True Range (ATR) + Buy-Sell Values",
                        "Normalized Average True Range (NATR) + Buy-Sell Values",
                        "Volume Weighted Average Price (VWAP) + Buy-Sell Values",
                        "Money Flow Index (MFI) + Buy-Sell Values",
                        "Stochastic RSI (SRSI) + Buy-Sell Values",
                        "Williams %R + Buy-Sell Values",
                        "Moving Average Convergence/Divergence (MACD) + Buy-Sell Values",
                        "Ultimate Oscillator (UO) + Buy-Sell Values",
                        "Average Directional Index (ADX) + Buy-Sell Values",
                        "Directional Movement Index (DMI) + Buy-Sell Values",
                        "SuperTrend (ST) + Buy-Sell Values",
                        "Exponential Moving Average (EMA) + Buy-Sell Values",
                        "Stochastic Oscillator + Buy-Sell Values",
                    ],
                },
                TradingAppSection {
                    title: "Symbol / Interval Overrides",
                    items: &[
                        "Columns: Symbol, Interval, Indicators, Loop, Leverage, Connector, Strategy Controls, Stop-Loss",
                        "Add Selected",
                        "Remove Selected",
                        "Clear All",
                    ],
                },
                TradingAppSection {
                    title: "Backtest Output",
                    items: &[
                        "Run Backtest",
                        "Stop",
                        "Add Selected to Dashboard",
                        "Add All to Dashboard",
                        "Scanner submits request, polls until backtest idle, renders runs, and selects the best row under Max MDD %",
                        "Dashboard import merges selected or all result rows into dashboard overrides without duplicates",
                        "Total PNL Active Positions: --",
                        "Total PNL Closed Positions: --",
                        "Bot Status: OFF",
                        "Bot Active Time: --",
                    ],
                },
            ],
            tables: &[
                TradingAppTable {
                    title: "Symbol / Interval Overrides",
                    columns: &[
                        "Symbol",
                        "Interval",
                        "Indicators",
                        "Loop",
                        "Leverage",
                        "Connector",
                        "Strategy Controls",
                        "Stop-Loss",
                    ],
                },
                TradingAppTable {
                    title: "Backtest Results",
                    columns: &[
                        "Symbol",
                        "Interval",
                        "Logic",
                        "Indicators",
                        "Trades",
                        "Loop Interval",
                        "Start Date",
                        "End Date",
                        "Position % Of Balance",
                        "Stop-Loss Options",
                        "Margin Mode (Futures)",
                        "Position Mode",
                        "Assets Mode",
                        "Account Mode",
                        "Leverage (Futures)",
                        "ROI (USDT)",
                        "ROI (%)",
                        "Max Drawdown During Position (USDT)",
                        "Max Drawdown During Position (%)",
                        "Max Drawdown Results (USDT)",
                        "Max Drawdown Results (%)",
                    ],
                },
            ],
        },
        TradingAppTab {
            key: "liquidation-heatmap",
            title: "Liquidation Heatmap",
            status: "Web panels",
            primary_metric: "Coinglass Heatmap",
            secondary_metric: "Hyperliquid Map",
            summary: "Liquidation heatmap provider tabs mirrored from the Python and C++ web tab.",
            actions: &["Open in Browser", "Reload", "Go"],
            sections: &[
                TradingAppSection {
                    title: "Coinglass Heatmap",
                    items: &[
                        "Use the on-page controls for Model 1/2/3, pair, symbol, and time selection.",
                        "Coinglass model tabs: Model 1, Model 2, Model 3",
                        "Model 1: https://www.coinglass.com/pro/futures/LiquidationHeatMap",
                        "Model 2: https://www.coinglass.com/pro/futures/LiquidationHeatMapNew",
                        "Model 3: https://www.coinglass.com/pro/futures/LiquidationHeatMapModel3",
                    ],
                },
                TradingAppSection {
                    title: "Providers",
                    items: &[
                        "URL:",
                        "Go",
                        "Reload",
                        "Open in Browser",
                        "Coinank: https://coinank.com/chart/derivatives/liq-heat-map",
                        "Bitcoin Counterflow: https://www.bitcoincounterflow.com/liquidation-heatmap/",
                        "Hyblock Capital: https://hyblockcapital.com/",
                        "Coinglass Map: https://www.coinglass.com/pro/futures/LiquidationMap",
                        "Hyperliquid Map: https://www.coinglass.com/hyperliquid-liquidation-map",
                    ],
                },
            ],
            tables: &[],
        },
        TradingAppTab {
            key: "code-languages",
            title: "Code Languages",
            status: "0 selected",
            primary_metric: "Language: Rust",
            secondary_metric: "Framework: Tauri",
            summary: "Code language, Rust framework, and dependency version controls mirrored from Python/C++.",
            actions: &[
                "Update Selected",
                "Update All",
                "Check Versions",
                "Refresh Env Versions",
            ],
            sections: &[
                TradingAppSection {
                    title: "Choose your language",
                    items: &[
                        "Python - Recommended - Fast to build - Huge ecosystem",
                        "C++ - Experiment - Qt native desktop experiment",
                        "Rust - Experiment - Service API client + guarded runtime (promotion-gated)",
                    ],
                },
                TradingAppSection {
                    title: "Rust desktop framework",
                    items: &[
                        "Tauri - The only user-selectable Rust desktop shell; interactive managed Python Service API behavior",
                    ],
                },
                TradingAppSection {
                    title: "Native Rust Runtime Gap",
                    items: &[
                        "Native Rust trading runtime ready: false",
                        "C++ has BinanceRestClient, BinanceWsClient, dashboard runtime lifecycle, positions sync, futures order submission, and risk/shutdown experiments",
                        "Rust currently has BinanceRestMarketDataClient for native REST market data and custom interval kline aggregation, BinanceWebSocketClient for native stream URL/message foundations, reconnect/backoff and kline cache staleness guards, a native runtime loop coordinator for stream supervision, live ingestion event/close/error handling, pause, stop, shutdown, idle transitions, hedge/one-way close planning, account-mode reconciliation, futures-settings reconciliation, a native account preflight gate, native operational preflight gate, and portfolio-aware exposure guard checks, BinanceSignedRestClient for signed balance/open-position snapshots and futures position-mode, margin-type, leverage, multi-assets, force-order, position-margin, and Spot trade-history request foundations, Binance futures order/filter request foundations, order submit guard and order audit/circuit-breaker foundations, runtime-owned order engine with deterministic dry-run, risk/stop-loss close-decision foundations, runtime-owned risk/close execution path, portfolio/history/allocation/reconciliation tests, LLM advisory/local model parity helpers, close-position planning foundations, Desktop shell/tab lifecycle contracts, strategy runtime signal/control/provenance helpers, plus Service API clients, tab/catalog parity, and desktop shells",
                        "Before enabling Rust native trading: collect/import credential-gated live-smoke artifacts, live recovery evidence, and release evidence",
                    ],
                },
                TradingAppSection {
                    title: "Environment Versions",
                    items: &[
                        "0 selected",
                        "Update Selected",
                        "Update All",
                        "Check Versions",
                        "Refresh Env Versions",
                    ],
                },
            ],
            tables: &[TradingAppTable {
                title: "Environment Versions",
                columns: &[
                    "Select",
                    "Dependency",
                    "Installed",
                    "Latest",
                    "Usage",
                    "Usage Change Counter",
                ],
            }],
        },
    ]
}

/// Compatibility alias for callers of the former hand-maintained catalog.
/// The returned slice is the generated Python source-of-truth catalog.
pub type LlmProviderOption = generated_python_parity::PythonLlmProvider;

pub fn llm_provider_options() -> &'static [LlmProviderOption] {
    python_source_llm_providers()
}

#[cfg(test)]
mod tests {
    use std::collections::{BTreeMap, BTreeSet};

    use super::*;

    #[test]
    fn legacy_llm_provider_view_is_the_generated_python_catalog() {
        assert!(std::ptr::eq(
            llm_provider_options().as_ptr(),
            python_source_llm_providers().as_ptr()
        ));
        assert_eq!(llm_provider_options().len(), 15);
        assert!(
            llm_provider_options()
                .iter()
                .any(|provider| provider.key == "ollama")
        );
    }

    #[test]
    fn llm_default_model_projection_matches_generated_python_catalog() {
        let defaults = python_source_llm_provider_default_models();
        assert_eq!(defaults.len(), python_source_llm_providers().len());
        assert!(defaults.contains(&("local", "qwen3:8b")));
        assert!(defaults.contains(&("open-source", "Qwen/Qwen3-8B")));
    }

    #[test]
    fn starter_catalogs_match_python_shape_and_expected_choices() {
        for option in python_source_code_language_options()
            .iter()
            .chain(python_source_rust_framework_options())
            .chain(python_source_starter_market_options())
        {
            assert!(!option.key.is_empty());
            assert!(!option.title.is_empty());
            assert!(!option.subtitle.is_empty());
        }
        assert_eq!(python_source_code_language_options().len(), 3);
        assert_eq!(
            python_source_rust_framework_options()
                .first()
                .map(|option| option.key),
            Some("Tauri")
        );
        assert_eq!(python_source_starter_market_options().len(), 2);
    }

    #[test]
    fn every_python_ui_catalog_is_non_empty_and_has_unique_keys() {
        let ui_catalog_count = generated_python_parity::PYTHON_UI_OPTION_CATALOGS.len();
        let ui_entry_count = generated_python_parity::PYTHON_UI_OPTION_CATALOGS
            .iter()
            .map(|catalog| catalog.options.len())
            .sum::<usize>();
        assert_eq!(
            generated_python_parity::PYTHON_OPTION_CATALOG_COUNT,
            44,
            "the generated native contract must contain every Python option catalog"
        );
        assert_eq!(
            generated_python_parity::PYTHON_OPTION_CATALOG_ENTRY_COUNT,
            255,
            "the generated native contract must contain every Python option entry"
        );
        assert_eq!(
            generated_python_parity::PYTHON_UI_OPTION_CATALOG_COUNT,
            ui_catalog_count,
            "generated UI catalog count must match the native catalog projection"
        );
        assert_eq!(
            generated_python_parity::PYTHON_UI_OPTION_ENTRY_COUNT,
            ui_entry_count,
            "generated UI entry count must match the native catalog projection"
        );
        for catalog in generated_python_parity::PYTHON_UI_OPTION_CATALOGS {
            let catalog_name = catalog.name;
            let options = catalog.options;
            assert!(
                !options.is_empty(),
                "Python UI catalog should not be empty: {catalog_name}"
            );
            let mut keys = BTreeSet::new();
            for option in options {
                assert!(!option.label.is_empty(), "missing label in {catalog_name}");
                if option.key.is_empty() {
                    assert_eq!(
                        catalog_name, "dashboard strategy templates",
                        "only Python's No Template sentinel may have an empty key"
                    );
                    assert_eq!(
                        option.label, "No Template",
                        "the empty-key Python template must remain the No Template sentinel"
                    );
                }
                assert!(
                    keys.insert(option.key),
                    "duplicate key in {catalog_name}: {}",
                    option.key
                );
            }
        }
    }

    #[test]
    fn every_python_option_catalog_is_manifested_with_source_entry_counts() {
        let manifest = generated_python_parity::PYTHON_OPTION_CATALOG_MANIFEST;
        assert_eq!(
            manifest.len(),
            generated_python_parity::PYTHON_OPTION_CATALOG_COUNT,
            "the generated Rust manifest must contain every Python option catalog"
        );
        assert_eq!(
            manifest
                .iter()
                .map(|entry| entry.entry_count)
                .sum::<usize>(),
            generated_python_parity::PYTHON_OPTION_CATALOG_ENTRY_COUNT,
            "the generated Rust manifest must contain every Python option entry"
        );
        let mut names = BTreeSet::new();
        for entry in manifest {
            assert!(
                !entry.name.is_empty(),
                "Python option catalog names must be present"
            );
            assert!(
                entry.entry_count > 0,
                "Python option catalogs must not be empty: {}",
                entry.name
            );
            assert!(
                names.insert(entry.name),
                "duplicate Python option catalog: {}",
                entry.name
            );
        }
    }

    #[test]
    fn python_option_catalog_json_matches_manifest_shape() {
        let payload: Value =
            serde_json::from_str(generated_python_parity::PYTHON_OPTION_CATALOGS_JSON)
                .expect("generated Python option catalog JSON should be valid");
        let catalogs = payload
            .as_object()
            .expect("generated Python option catalog JSON should be an object");
        assert_eq!(
            catalogs.len(),
            generated_python_parity::PYTHON_OPTION_CATALOG_COUNT
        );
        for entry in generated_python_parity::PYTHON_OPTION_CATALOG_MANIFEST {
            let value = catalogs.get(entry.name).unwrap_or_else(|| {
                panic!("missing Python option catalog JSON entry: {}", entry.name)
            });
            let count = value.as_array().map_or_else(
                || value.as_object().map_or(1, |object| object.len()),
                |array| array.len(),
            );
            assert_eq!(
                count, entry.entry_count,
                "catalog JSON count mismatch: {}",
                entry.name
            );
        }
    }

    #[test]
    fn python_typed_ui_catalog_values_match_python_option_catalog_json() {
        let payload: Value =
            serde_json::from_str(generated_python_parity::PYTHON_OPTION_CATALOGS_JSON)
                .expect("generated Python option catalog JSON should be valid");
        let catalogs = payload
            .as_object()
            .expect("generated Python option catalog JSON should be an object");
        let source_name_for = |name: &str| -> &str {
            match name {
                "dashboard loop" => "dashboard_loop_choices",
                "lead trader" => "lead_trader_options",
                "LLM use-for" => "llm_use_for_options",
                "dashboard strategy templates" => "dashboard_strategy_templates",
                "backtest templates" => "backtest_templates",
                "side" => "side_options",
                "config mode" => "config_mode_options",
                "theme" => "theme_options",
                "design" => "design_options",
                "indicator source" => "indicator_source_options",
                "moving average type" => "indicator_ma_type_options",
                "exchange" => "exchange_options",
                "account type" => "account_type_options",
                "margin mode" => "margin_mode_options",
                "position mode" => "position_mode_options",
                "assets mode" => "assets_mode_options",
                "order type" => "order_type_options",
                "time in force" => "time_in_force_options",
                "signal logic" => "signal_logic_options",
                "MDD logic" => "mdd_logic_options",
                "stop-loss modes" => "stop_loss_modes",
                "stop-loss scopes" => "stop_loss_scopes",
                "scan scope" => "scan_scope_options",
                "optimizer mode" => "optimizer_mode_options",
                "optimizer metric" => "optimizer_metric_options",
                "backtest execution backend" => "backtest_execution_backend_options",
                "chart view" => "chart_view_options",
                "positions view" => "positions_view_options",
                other => panic!("unmapped generated Python UI catalog: {other}"),
            }
        };

        for catalog in generated_python_parity::PYTHON_UI_OPTION_CATALOGS {
            let source_name = source_name_for(catalog.name);
            let source_options = catalogs
                .get(source_name)
                .and_then(Value::as_array)
                .unwrap_or_else(|| {
                    panic!("missing Python option catalog JSON array: {source_name}")
                });
            assert_eq!(
                source_options.len(),
                catalog.options.len(),
                "typed Python UI catalog size mismatch: {}",
                catalog.name
            );
            for (index, option) in catalog.options.iter().enumerate() {
                let source_option = source_options[index].as_object().unwrap_or_else(|| {
                    panic!("Python UI option should be an object: {source_name}[{index}]")
                });
                assert_eq!(
                    source_option.get("key").and_then(Value::as_str),
                    Some(option.key),
                    "typed Python UI option key mismatch: {}[{index}]",
                    catalog.name
                );
                assert_eq!(
                    source_option.get("label").and_then(Value::as_str),
                    Some(option.label),
                    "typed Python UI option label mismatch: {}[{index}]",
                    catalog.name
                );
                assert_eq!(
                    source_option
                        .get("disabled")
                        .and_then(Value::as_bool)
                        .unwrap_or(false),
                    option.disabled,
                    "typed Python UI option disabled mismatch: {}[{index}]",
                    catalog.name
                );
                if let Some(value) = source_option.get("value") {
                    assert_eq!(
                        value.as_str(),
                        Some(option.key),
                        "typed Python UI option value mismatch: {}[{index}]",
                        catalog.name
                    );
                }
            }
        }
    }

    #[test]
    fn python_native_primitive_projections_match_python_option_catalog_json() {
        let payload: Value =
            serde_json::from_str(generated_python_parity::PYTHON_OPTION_CATALOGS_JSON)
                .expect("generated Python option catalog JSON should be valid");
        let catalogs = payload
            .as_object()
            .expect("generated Python option catalog JSON should be an object");
        let source_strings = |name: &str| -> Vec<&str> {
            catalogs
                .get(name)
                .and_then(Value::as_array)
                .unwrap_or_else(|| panic!("missing Python string catalog: {name}"))
                .iter()
                .map(|value| {
                    value.as_str().unwrap_or_else(|| {
                        panic!("Python catalog entry should be a string: {name}")
                    })
                })
                .collect()
        };

        assert_eq!(
            python_source_backtest_intervals(),
            source_strings("intervals").as_slice()
        );
        assert_eq!(
            python_source_default_chart_symbols(),
            source_strings("default_chart_symbols").as_slice()
        );
        assert_eq!(
            python_source_default_execution_symbols(),
            source_strings("default_execution_symbols").as_slice()
        );
        assert_eq!(
            python_source_default_execution_intervals(),
            source_strings("default_execution_intervals").as_slice()
        );
        assert_eq!(
            python_source_default_backtest_symbols(),
            source_strings("default_backtest_symbols").as_slice()
        );
        assert_eq!(
            python_source_default_backtest_intervals(),
            source_strings("default_backtest_intervals").as_slice()
        );
        assert_eq!(
            python_source_chart_market_options(),
            source_strings("chart_market_options").as_slice()
        );
        assert_eq!(
            python_source_account_mode_options(),
            source_strings("account_mode_options").as_slice()
        );

        let expected_tradingview: BTreeMap<&str, &str> = catalogs
            .get("tradingview_interval_map")
            .and_then(Value::as_object)
            .expect("missing Python TradingView interval map")
            .iter()
            .map(|(interval, code)| {
                (
                    interval.as_str(),
                    code.as_str()
                        .expect("TradingView interval code should be a string"),
                )
            })
            .collect();
        let actual_tradingview: BTreeMap<&str, &str> = python_source_tradingview_interval_map()
            .iter()
            .map(|entry| (entry.interval, entry.code))
            .collect();
        assert_eq!(actual_tradingview, expected_tradingview);

        let expected_connectors: Vec<(&str, &str)> = catalogs
            .get("connectors")
            .and_then(Value::as_array)
            .expect("missing Python connector catalog")
            .iter()
            .map(|value| {
                let connector = value.as_object().expect("connector should be an object");
                (
                    connector
                        .get("key")
                        .and_then(Value::as_str)
                        .expect("connector key should be present"),
                    connector
                        .get("label")
                        .and_then(Value::as_str)
                        .expect("connector label should be present"),
                )
            })
            .collect();
        let actual_connectors: Vec<(&str, &str)> = python_source_connector_options()
            .iter()
            .map(|connector| (connector.key, connector.label))
            .collect();
        assert_eq!(actual_connectors, expected_connectors);

        let source_indicators = catalogs
            .get("indicators")
            .and_then(Value::as_array)
            .expect("missing Python indicator catalog");
        assert_eq!(
            python_source_indicator_catalog().len(),
            source_indicators.len()
        );
        for (index, indicator) in python_source_indicator_catalog().iter().enumerate() {
            let source_indicator = source_indicators[index]
                .as_object()
                .expect("Python indicator should be an object");
            assert_eq!(
                source_indicator.get("key").and_then(Value::as_str),
                Some(indicator.key)
            );
            assert_eq!(
                source_indicator.get("display_name").and_then(Value::as_str),
                Some(indicator.display_name)
            );
            assert_eq!(
                source_indicator
                    .get("default_enabled")
                    .and_then(Value::as_bool),
                Some(indicator.default_enabled)
            );
            let runtime_config: Value = serde_json::from_str(indicator.runtime_config_json)
                .expect("generated Python indicator runtime config should be valid JSON");
            let backtest_config: Value = serde_json::from_str(indicator.backtest_config_json)
                .expect("generated Python indicator backtest config should be valid JSON");
            assert_eq!(
                source_indicator.get("runtime_config"),
                Some(&runtime_config)
            );
            assert_eq!(
                source_indicator.get("backtest_config"),
                Some(&backtest_config)
            );
            let expected_output_keys: Vec<&str> = source_indicator
                .get("runtime_output_keys")
                .and_then(Value::as_array)
                .expect("Python indicator output keys should be an array")
                .iter()
                .map(|value| {
                    value
                        .as_str()
                        .expect("Python indicator output key should be a string")
                })
                .collect();
            assert_eq!(
                indicator.runtime_output_keys,
                expected_output_keys.as_slice()
            );
        }
    }

    #[test]
    fn moving_average_options_match_python_source_catalog() {
        assert_eq!(
            python_source_indicator_ma_type_options()
                .iter()
                .map(|option| option.key)
                .collect::<Vec<_>>(),
            vec!["SMA", "EMA"]
        );
    }

    #[test]
    fn service_api_route_schemas_are_generated_from_python_source() {
        assert_eq!(
            python_source_service_route_names().len(),
            python_source_service_route_schemas().len()
        );

        let dashboard = service_api_route_schema("dashboard").expect("dashboard schema");
        assert_eq!(dashboard.query_fields, &["log_limit", "incident_limit"]);
        assert!(dashboard.request_fields.is_empty());
        assert!(dashboard.response_fields.contains(&"runtime"));
        assert!(dashboard.response_fields.contains(&"service_api"));

        let config = service_api_route_schema("config").expect("config schema");
        assert_eq!(config.request_fields, &["config"]);
        assert!(config.response_fields.contains(&"llm"));
        assert!(config.response_fields.contains(&"exchange_support"));

        let control_start =
            service_api_route_schema("control_start").expect("control_start schema");
        assert!(
            control_start
                .request_fields
                .contains(&"requested_job_count")
        );
        assert!(control_start.response_fields.contains(&"accepted"));

        let llm_providers =
            service_api_route_schema("llm_providers").expect("llm_providers schema");
        for field in [
            "model_suggestions",
            "reasoning_efforts",
            "default_reasoning_effort",
            "catalog_revision",
            "catalog_path",
            "custom_models_env",
            "custom_models_path_env",
            "catalog_note",
            "notes",
        ] {
            assert!(
                llm_providers.response_fields.contains(&field),
                "missing llm provider field {field}"
            );
        }

        let llm_config = service_api_route_schema("llm_config").expect("llm_config schema");
        for field in [
            "catalog_revision",
            "catalog_path",
            "custom_models_env",
            "custom_models_path_env",
            "default_reasoning_effort",
            "reasoning_efforts",
            "model_suggestions",
            "notes",
            "execution_policy",
        ] {
            assert!(
                llm_config.response_fields.contains(&field),
                "missing llm config field {field}"
            );
        }

        assert!(service_api_route_schema("unknown").is_none());
    }

    #[test]
    fn service_api_route_helpers_follow_the_generated_python_contract() {
        assert_eq!(
            service_api_route_methods("config"),
            Some(&["GET", "PUT", "PATCH"][..])
        );
        assert!(service_api_route_supports_method("config", "patch"));
        assert!(!service_api_route_supports_method("config", "POST"));
        assert!(service_api_route_supports_query_field(
            "dashboard",
            "log_limit"
        ));
        assert!(!service_api_route_supports_query_field(
            "dashboard",
            "unexpected"
        ));
        assert!(service_api_route_supports_request_field("config", "config"));
        assert!(!service_api_route_supports_request_field("config", "mode"));
    }
}
