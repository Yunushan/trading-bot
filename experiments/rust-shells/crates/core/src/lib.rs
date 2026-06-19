use trading_bot_contracts::AppIdentity;

pub mod account;
pub mod chart_heatmap;
pub mod config_persistence;
pub mod diagnostics;
pub mod desktop_shell;
pub mod exchange_connectors;
pub mod generated_python_parity;
pub mod llm_advisory;
pub mod market_data;
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

pub use generated_python_parity::{
    PythonConnectorOption as NativePythonConnectorOption, PythonIndicator as NativePythonIndicator,
    PythonLlmProvider as NativePythonLlmProvider,
    PythonParityDomain as NativePythonAppParityDomain, PythonServiceRoute as ServiceApiRoute,
    PythonServiceRouteSchema as ServiceApiRouteSchema,
    PythonTradingViewInterval as NativePythonTradingViewInterval,
    PythonUiOption as NativePythonUiOption,
};

pub fn app_banner(shell: &str) -> String {
    format!("Trading Bot Rust UI scaffold -> {shell}")
}

pub fn default_identity(shell: &str) -> AppIdentity {
    AppIdentity::new(shell)
}

pub fn supported_frameworks() -> &'static [&'static str] {
    &["Tauri", "Slint", "egui", "Iced", "Dioxus Desktop"]
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

pub fn python_source_connector_keys() -> &'static [&'static str] {
    generated_python_parity::PYTHON_CONNECTOR_KEYS
}

pub fn python_source_connector_options() -> &'static [NativePythonConnectorOption] {
    generated_python_parity::PYTHON_CONNECTOR_OPTIONS
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

pub fn python_source_exchange_options() -> &'static [NativePythonUiOption] {
    generated_python_parity::PYTHON_EXCHANGE_OPTIONS
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
    false
}

pub fn rust_native_trading_runtime_ready() -> bool {
    false
}

pub fn cpp_entire_python_app_parity_ready() -> bool {
    native_python_app_parity_domains()
        .iter()
        .all(|domain| domain.cpp_full_parity)
}

pub fn rust_entire_python_app_parity_ready() -> bool {
    native_python_app_parity_domains()
        .iter()
        .all(|domain| domain.rust_full_parity)
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
            detail: "Reserved until a Rust engine reaches feature parity with Python strategy controls, order audit, risk gates, and connector safeguards.",
            trading_execution_supported: false,
        },
    ]
}

pub fn native_python_app_parity_domains() -> &'static [NativePythonAppParityDomain] {
    generated_python_parity::PYTHON_PARITY_DOMAINS
}

pub fn rust_shell_framework_parity() -> &'static [RustShellFrameworkParity] {
    &[
        RustShellFrameworkParity {
            framework: "Tauri",
            status: "Operational Service API client",
            detail: "Runs the operational HTML shell with live Python Service API start/stop, dashboard/config hydration, backtest scanner, dashboard import, logs, LLM advisory prompts, and local LLM model lifecycle controls; trading execution still belongs to Python.",
        },
        RustShellFrameworkParity {
            framework: "Slint",
            status: "Non-operational native UI evaluation",
            detail: "Mirrors the Python/C++ tab, control, table, route, framework, and execution-boundary map for native UI evaluation, but does not manage the Service API or control the bot.",
        },
        RustShellFrameworkParity {
            framework: "egui",
            status: "Non-operational comparison renderer",
            detail: "Renders trading_app_tabs, service_api_capabilities, service_api_routes, rust_execution_modes, and this framework parity contract directly from trading-bot-core for renderer comparison only; it does not manage the Service API or control the bot.",
        },
        RustShellFrameworkParity {
            framework: "Iced",
            status: "Non-operational comparison renderer",
            detail: "Renders trading_app_tabs, service_api_capabilities, service_api_routes, rust_execution_modes, and this framework parity contract directly from trading-bot-core for renderer comparison only; it does not manage the Service API or control the bot.",
        },
        RustShellFrameworkParity {
            framework: "Dioxus Desktop",
            status: "Non-operational comparison renderer",
            detail: "Renders trading_app_tabs, service_api_capabilities, service_api_routes, rust_execution_modes, and this framework parity contract directly from trading-bot-core for renderer comparison only; it does not manage the Service API or control the bot.",
        },
    ]
}

pub fn rust_native_runtime_capabilities() -> &'static [RustNativeRuntimeCapability] {
    &[
        RustNativeRuntimeCapability {
            key: "market_data_rest",
            title: "REST market data",
            cpp_status: "C++ has BinanceRestClient fetchUsdtSymbols, fetchKlines, and fetchTickerPrice.",
            rust_status: "Rust core now has BinanceRestMarketDataClient for native exchangeInfo USDT symbols, optional 24h quote-volume ordering, klines, ticker prices, and Binance error payload handling.",
            required_before_enable: "Add live-network smoke coverage where credentials/network policy allow it, custom interval aggregation, connector support metadata, rate-limit diagnostics, and integration into a supervised Rust runtime loop.",
            trading_execution_supported: false,
        },
        RustNativeRuntimeCapability {
            key: "market_data_websocket",
            title: "WebSocket market stream",
            cpp_status: "C++ has BinanceWsClient connectBookTicker/connectKline plus dashboardRuntimeSignalSockets and candle caches.",
            rust_status: "Rust core now has BinanceWebSocketClient URL construction, tungstenite connection entry points, and book ticker/kline message parsing for Binance spot and futures streams.",
            required_before_enable: "Add supervised reconnect/backoff, candle cache reconciliation, stale-feed guards, stream lifecycle ownership, and live-network smoke coverage before live signal evaluation.",
            trading_execution_supported: false,
        },
        RustNativeRuntimeCapability {
            key: "account_positions",
            title: "Account, balance, and positions",
            cpp_status: "C++ can fetch USDT balance and open futures positions and reconcile them into the positions table.",
            rust_status: "Rust core now has BinanceSignedRestClient for signed USDT balance snapshots, normalized balance rows, open futures position parsing with account-position overlays, close-position planning foundations, and portfolio/history/allocation/reconciliation tests.",
            required_before_enable: "Add live credential-gated smoke coverage, hedge/one-way runtime coverage, and broader supervised runtime integration after the remaining parity domains complete.",
            trading_execution_supported: false,
        },
        RustNativeRuntimeCapability {
            key: "order_submission",
            title: "Order submission",
            cpp_status: "C++ has placeFuturesMarketOrder/placeFuturesLimitOrder and dashboard open/close fallback helpers.",
            rust_status: "Rust core now has Binance futures symbol filters, signed market/limit order request construction, order submit guard and order audit/circuit-breaker foundations, risk/stop-loss close-decision planning, reduce-only hedge-mode rules, close-position and closePosition planning, POST submission hooks, order response parsing, and a runtime-owned order engine for guarded submit, redacted audit JSONL, connector circuit incident persistence, and submit reconciliation.",
            required_before_enable: "Add dry-run controls, live credential-gated smoke coverage, supervised runtime lifecycle tests, and runtime-owned recovery gates before enabling native trading.",
            trading_execution_supported: false,
        },
        RustNativeRuntimeCapability {
            key: "runtime_lifecycle",
            title: "Runtime lifecycle loop",
            cpp_status: "C++ has startDashboardRuntime, runDashboardRuntimeCycle, stopDashboardRuntime, timer state, retry windows, and open-position tracking.",
            rust_status: "Rust core now has Desktop shell/tab lifecycle contracts plus strategy runtime signal/control/provenance helpers, worker lifecycle snapshots, and core stop/shutdown guard result builders; Tauri may start/stop the Python Service API but standalone Rust trading remains disabled.",
            required_before_enable: "Add supervised native loop ownership, live credential-gated smoke coverage, and recovery tests before enabling standalone Rust trading.",
            trading_execution_supported: false,
        },
        RustNativeRuntimeCapability {
            key: "risk_and_shutdown_guards",
            title: "Risk and shutdown guards",
            cpp_status: "C++ tracks stop-loss settings, quantity caps, retry-after windows, close-on-stop behavior, connector warnings, and forced close fallbacks.",
            rust_status: "Rust core now has stop-loss setting normalization plus per-trade, directional, cumulative, entire-account, close-opposite planning foundations, a runtime-owned risk/close execution path for stop-loss and close-opposite reconciliation, and Python-compatible shutdown guard result tests.",
            required_before_enable: "Add max exposure checks, shutdown guard wiring into a supervised runtime, and credential-gated regression tests before enabling native trading.",
            trading_execution_supported: false,
        },
    ]
}

pub fn service_api_capabilities() -> &'static [ServiceApiCapability] {
    &[
        ServiceApiCapability {
            title: "Managed Local Service API",
            detail: "Only Tauri can launch apps/service-api/main.py --serve on 127.0.0.1 and stop only the process it started; the other Rust shells are non-operational evaluation renderers.",
        },
        ServiceApiCapability {
            title: "Canonical /api/v1 Contract",
            detail: "Rust shells expose the full canonical Python Service API route catalog, including runtime, dashboard, status, stream, config persistence, control, connector circuit, account, portfolio, terminal, LLM, logs, and backtest routes.",
        },
        ServiceApiCapability {
            title: "Logs, Terminal & Diagnostics",
            detail: "trading-bot-core mirrors Python service log and controlled terminal result schemas with diagnostic redaction; Tauri delegates /logs and terminal_run behavior to the Python Service API, while other Rust shells are non-operational renderers.",
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

pub fn service_api_route_schema(name: &str) -> Option<&'static ServiceApiRouteSchema> {
    python_source_service_route_schemas()
        .iter()
        .find(|schema| schema.name == name)
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
                        "Mode: Live, Demo, Testnet",
                        "Theme: Light, Dark, Blue, Yellow, Green, Red",
                        "Account Type: Spot, Futures",
                        "Account Mode: Classic Trading, Portfolio Margin",
                        "Connector: Binance SDK Derivatives Trading USD-S Futures, Binance SDK Derivatives Trading COIN-M Futures, Binance SDK Spot, Binance Connector Python, CCXT, python-binance",
                        "Total USDT balance: N/A",
                        "Position Mode: N/A",
                        "Refresh Balance",
                        "Leverage (Futures): 1-150",
                        "Margin Mode (Futures): Cross, Isolated",
                        "Position Mode: One-way, Hedge",
                        "Assets Mode: Single-Asset Mode, Multi-Assets Mode",
                        "Time-in-Force: GTC, IOC, FOK, GTD",
                        "GTD minutes: 1-1440",
                        "Indicator Source: Binance spot, Binance futures, TradingView, Bybit, Coinbase, OKX, Gate, Bitget, Mexc, Kucoin, HTX, Kraken",
                    ],
                },
                TradingAppSection {
                    title: "AI / LLM Settings",
                    items: &[
                        "Enable LLM assistance",
                        "Allow public network endpoint",
                        "Provider: OpenAI / ChatGPT, Anthropic Claude, Google Gemini, xAI Grok, Mistral AI, DeepSeek, Alibaba Qwen / DashScope, Local / Custom OpenAI-Compatible",
                        "Model: gpt-5.5, gpt-5.4, claude-sonnet, gemini, grok, mistral, deepseek, qwen3:8b, llama3.3, gemma3:4b",
                        "Base URL / IP:",
                        "API key env:",
                        "API token:",
                        "Use for: Advisory, Signal confirmation, Risk review, Backtest explanation",
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
                        "Default symbols: BTCUSDT, ETHUSDT, BNBUSDT, SOLUSDT, XRPUSDT",
                        "Refresh Symbols",
                        "Intervals (select 1 or more):",
                        "Default intervals: 1m, 3m, 5m, 10m, 15m, 30m, 1h, 4h, 1d",
                        "Custom interval input: e.g., 45s or 7m or 90m, comma-separated",
                        "Add Custom Interval(s)",
                    ],
                },
                TradingAppSection {
                    title: "Strategy Controls",
                    items: &[
                        "Side: Buy (Long), Sell (Short), Both (Long/Short)",
                        "Position % of Balance:",
                        "Loop Interval Override: 30 seconds, 45 seconds, 1 minute, 2 minutes, 3 minutes, 5 minutes, 10 minutes, 30 minutes, 1 hour, 2 hours",
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
                        "Symbol Source: Futures, Spot",
                        "Refresh",
                        "Symbols (select 1 or more):",
                        "Default symbols: BTCUSDT, ETHUSDT, BNBUSDT",
                        "Intervals (select 1 or more):",
                        "Default intervals: 1m, 5m, 15m, 1h",
                        "Custom interval input: e.g., 45s or 7m or 90m, comma-separated",
                        "Add Custom Interval(s)",
                    ],
                },
                TradingAppSection {
                    title: "Backtest Parameters",
                    items: &[
                        "Start Date/Time:",
                        "End Date/Time:",
                        "Signal Logic: AND, OR, SEPARATE",
                        "MDD Logic: Per Trade MDD, Cumulative MDD, Entire Account MDD",
                        "Margin Capital:",
                        "Position % of Balance:",
                        "Loop Interval Override: 30 seconds, 45 seconds, 1 minute, 2 minutes, 3 minutes, 5 minutes, 10 minutes, 30 minutes, 1 hour, 2 hours",
                        "Stop Loss: Enable, mode, Scope, USDT, %",
                        "Side: Buy (Long), Sell (Short), Both (Long/Short)",
                        "Margin Mode (Futures): Isolated, Cross",
                        "Position Mode: Hedge, One-way",
                        "Assets Mode: Single-Asset Mode, Multi-Assets Mode",
                        "Account Mode: Classic Trading, Portfolio Margin",
                        "Connector: Binance SDK Derivatives Trading USD-S Futures, Binance SDK Derivatives Trading COIN-M Futures, Binance SDK Spot, Binance Connector Python, CCXT, python-binance",
                        "Leverage (Futures):",
                        "Template: Enable, First 50 Highest Volume, Last 1 week · 2% per trade · 50 highest volume, Top 100, %2 per trade, isolated, %20 per trade SL",
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
                        "Rust - Experiment - Service API client and UI scaffold",
                    ],
                },
                TradingAppSection {
                    title: "Choose your Rust framework",
                    items: &[
                        "Tauri - Operational Service API client with interactive managed Python Service API behavior",
                        "Slint - Non-operational native UI evaluation for the same tab/control/route map",
                        "egui - Non-operational comparison renderer from trading-bot-core",
                        "Iced - Non-operational comparison renderer from trading-bot-core",
                        "Dioxus Desktop - Non-operational comparison renderer from trading-bot-core",
                    ],
                },
                TradingAppSection {
                    title: "Native Rust Runtime Gap",
                    items: &[
                        "Native Rust trading runtime ready: false",
                        "C++ has BinanceRestClient, BinanceWsClient, dashboard runtime lifecycle, positions sync, futures order submission, and risk/shutdown experiments",
                        "Rust currently has BinanceRestMarketDataClient for native REST market data, BinanceWebSocketClient for native stream URL/message foundations, BinanceSignedRestClient for signed balance/open-position snapshots, Binance futures order/filter request foundations, order submit guard and order audit/circuit-breaker foundations, runtime-owned order engine, risk/stop-loss close-decision foundations, runtime-owned risk/close execution path, portfolio/history/allocation/reconciliation tests, LLM advisory/local model parity helpers, close-position planning foundations, Desktop shell/tab lifecycle contracts, strategy runtime signal/control/provenance helpers, plus Service API clients, tab/catalog parity, and desktop shells",
                        "Before enabling Rust native trading: add supervised stream reconnect/cache guards, dry-run controls, live credential-gated smoke coverage, hedge/one-way runtime coverage, and shutdown guard wiring",
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

pub struct LlmProviderOption {
    pub key: &'static str,
    pub label: &'static str,
    pub mode: &'static str,
    pub default_base_url: &'static str,
    pub default_model: &'static str,
    pub api_key_env: &'static str,
    pub model_suggestions: &'static [&'static str],
    pub reasoning_efforts: &'static [&'static str],
}

pub fn llm_provider_options() -> &'static [LlmProviderOption] {
    &[
        LlmProviderOption {
            key: "openai",
            label: "OpenAI / ChatGPT",
            mode: "cloud",
            default_base_url: "https://api.openai.com/v1",
            default_model: "gpt-5.5",
            api_key_env: "OPENAI_API_KEY",
            model_suggestions: &[
                "gpt-5.5",
                "gpt-5.5-2026-04-23",
                "gpt-5.5-pro",
                "gpt-5.5-pro-2026-04-23",
                "gpt-5.4",
                "gpt-5.4-2026-03-05",
                "gpt-5.4-pro",
                "gpt-5.4-pro-2026-03-05",
                "gpt-5.4-mini",
                "gpt-5.4-mini-2026-03-17",
                "gpt-5.4-nano",
                "gpt-5.4-nano-2026-03-17",
                "gpt-5.3-chat-latest",
                "gpt-5.3-codex",
                "gpt-5.2",
                "gpt-5.2-codex",
                "gpt-5.2-chat-latest",
                "gpt-5.2-pro",
                "gpt-5.1",
                "gpt-5-codex",
                "gpt-5-mini",
                "gpt-5-nano",
                "gpt-4.1",
                "gpt-4.1-mini",
                "gpt-4.1-nano",
            ],
            reasoning_efforts: &[
                "default", "none", "minimal", "low", "medium", "high", "xhigh",
            ],
        },
        LlmProviderOption {
            key: "anthropic",
            label: "Anthropic Claude",
            mode: "cloud",
            default_base_url: "https://api.anthropic.com",
            default_model: "claude-sonnet-4-5-20250929",
            api_key_env: "ANTHROPIC_API_KEY",
            model_suggestions: &[
                "claude-sonnet-4-5-20250929",
                "claude-haiku-4-5-20251001",
                "claude-opus-4-5-20251101",
                "claude-opus-4-1-20250805",
                "claude-opus-4-20250514",
                "claude-sonnet-4-20250514",
                "claude-sonnet-4-5",
                "claude-haiku-4-5",
                "claude-opus-4-5",
                "claude-opus-4-1",
                "claude-opus-4-0",
                "claude-sonnet-4-0",
            ],
            reasoning_efforts: &["default", "disabled", "enabled", "low", "medium", "high"],
        },
        LlmProviderOption {
            key: "gemini",
            label: "Google Gemini",
            mode: "cloud",
            default_base_url: "https://generativelanguage.googleapis.com/v1beta",
            default_model: "gemini-3-flash-preview",
            api_key_env: "GEMINI_API_KEY",
            model_suggestions: &[
                "gemini-3.1-pro-preview",
                "gemini-3.1-pro-preview-customtools",
                "gemini-3-flash-preview",
                "gemini-3.1-flash-lite-preview",
                "gemini-2.5-pro",
                "gemini-2.5-flash",
                "gemini-2.5-flash-preview-09-2025",
                "gemini-2.5-flash-lite",
                "gemini-2.5-flash-lite-preview-09-2025",
            ],
            reasoning_efforts: &["default", "minimal", "low", "medium", "high"],
        },
        LlmProviderOption {
            key: "deepseek",
            label: "DeepSeek",
            mode: "cloud",
            default_base_url: "https://api.deepseek.com",
            default_model: "deepseek-v4-flash",
            api_key_env: "DEEPSEEK_API_KEY",
            model_suggestions: &[
                "deepseek-v4-flash",
                "deepseek-v4-pro",
                "deepseek-chat",
                "deepseek-reasoner",
            ],
            reasoning_efforts: &["default", "disabled", "enabled", "high", "max"],
        },
        LlmProviderOption {
            key: "mistral",
            label: "Mistral AI",
            mode: "cloud",
            default_base_url: "https://api.mistral.ai/v1",
            default_model: "mistral-small-latest",
            api_key_env: "MISTRAL_API_KEY",
            model_suggestions: &[
                "mistral-large-latest",
                "mistral-medium-latest",
                "mistral-small-latest",
                "codestral-latest",
                "open-mistral-nemo",
            ],
            reasoning_efforts: &["default", "low", "medium", "high"],
        },
        LlmProviderOption {
            key: "grok",
            label: "xAI Grok",
            mode: "cloud",
            default_base_url: "https://api.x.ai/v1",
            default_model: "grok-4.3",
            api_key_env: "XAI_API_KEY",
            model_suggestions: &[
                "grok-4.3",
                "grok-4.3-latest",
                "grok-4.20",
                "grok-4.20-reasoning",
                "grok-4.20-non-reasoning",
                "grok-4-fast-reasoning",
                "grok-4-fast-non-reasoning",
            ],
            reasoning_efforts: &["default", "low", "medium", "high"],
        },
        LlmProviderOption {
            key: "qwen",
            label: "Alibaba Qwen / DashScope",
            mode: "cloud",
            default_base_url: "https://dashscope-intl.aliyuncs.com/compatible-mode/v1",
            default_model: "qwen3.6-plus",
            api_key_env: "DASHSCOPE_API_KEY",
            model_suggestions: &[
                "qwen3.6-max-preview",
                "qwen3.6-plus",
                "qwen3.6-plus-2026-04-02",
                "qwen3.6-flash",
                "qwen3.6-flash-2026-04-16",
                "qwen3-max",
                "qwen3-max-2026-01-23",
                "qwen3-max-2025-09-23",
                "qwen3-max-preview",
                "qwen3.5-plus",
                "qwen3.5-plus-2026-02-15",
                "qwen3.5-flash",
                "qwen3.5-flash-2026-02-23",
                "qwen3-coder-plus",
                "qwen3-coder-flash",
                "qwen-plus-us",
                "qwen-flash-us",
            ],
            reasoning_efforts: &["default", "low", "medium", "high"],
        },
        LlmProviderOption {
            key: "local",
            label: "Local / Custom OpenAI-Compatible",
            mode: "local",
            default_base_url: "http://127.0.0.1:11434/v1",
            default_model: "qwen3:8b",
            api_key_env: "LOCAL_LLM_API_KEY",
            model_suggestions: &[
                "qwen3:0.6b",
                "qwen3:1.7b",
                "qwen3:4b",
                "qwen3:8b",
                "qwen3:14b",
                "qwen3:30b-a3b",
                "qwen3:32b",
                "qwen3",
                "gpt-oss:20b",
                "gpt-oss:latest",
                "llama3.3",
                "llama3.1:8b",
                "llama3.2:3b",
                "llama3.2:1b",
                "mistral-small3.2",
                "deepseek-r1:8b",
                "gemma3:4b",
                "custom-model",
            ],
            reasoning_efforts: &["default", "none", "low", "medium", "high", "xhigh"],
        },
    ]
}

#[cfg(test)]
mod tests {
    use super::*;

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

        assert!(service_api_route_schema("unknown").is_none());
    }
}
