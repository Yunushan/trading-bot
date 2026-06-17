// This file is generated from Languages/Python/app/native_parity.py.
// Do not edit manually; run Languages/Python/tools/generate_native_parity_contracts.py.

pub const PYTHON_SOURCE: &str = "Languages/Python";
pub const PYTHON_SOURCE_SCHEMA_VERSION: u32 = 1;
pub const PYTHON_SOURCE_CONTRACT_HASH: &str = "5f226cd68f0d40a44af7d611dd68c3b15645d452d6421854b5f31100c5533e08";
pub const CPP_FULL_PARITY_READY: bool = false;
pub const RUST_FULL_PARITY_READY: bool = false;

pub struct PythonParityDomain {
    pub key: &'static str,
    pub title: &'static str,
    pub python_surface: &'static str,
    pub cpp_status: &'static str,
    pub rust_status: &'static str,
    pub required_before_full_parity: &'static str,
    pub cpp_full_parity: bool,
    pub rust_full_parity: bool,
}

pub const PYTHON_PARITY_DOMAINS: &[PythonParityDomain] = &[
    PythonParityDomain {
        key: "desktop_shell_and_tabs",
        title: "Desktop shell and primary tabs",
        python_surface: "Dashboard, Chart, Positions, Backtest, Liquidation Heatmap, Code Languages, startup composition, theme, and live tab wiring.",
        cpp_status: "C++ missing: Production startup and lifecycle parity; Tab behavior parity tests; Release ownership instead of preview ownership",
        rust_status: "Rust missing: Production desktop ownership for the selected Rust shell; Equivalent startup and tab lifecycle behavior; Remove non-operational claims from comparison renderers",
        required_before_full_parity: "C++: Production startup and lifecycle parity; Tab behavior parity tests; Release ownership instead of preview ownership | Rust: Production desktop ownership for the selected Rust shell; Equivalent startup and tab lifecycle behavior; Remove non-operational claims from comparison renderers",
        cpp_full_parity: false,
        rust_full_parity: false,
    },
    PythonParityDomain {
        key: "service_api_contract",
        title: "Service API contract",
        python_surface: "Canonical /api/v1 routes, methods, schemas, dashboard stream, auth, control-plane state, and desktop bridge contract.",
        cpp_status: "C++ missing: Generated schema parity beyond route/method lookup; Operational request/response tests",
        rust_status: "Rust missing: Generated route, method, and schema parity; Tauri client behavior retained or replaced by native equivalent; Explicit non-operational boundaries for other shells",
        required_before_full_parity: "C++: Generated schema parity beyond route/method lookup; Operational request/response tests | Rust: Generated route, method, and schema parity; Tauri client behavior retained or replaced by native equivalent; Explicit non-operational boundaries for other shells",
        cpp_full_parity: false,
        rust_full_parity: false,
    },
    PythonParityDomain {
        key: "config_persistence",
        title: "Config persistence and hydration",
        python_surface: "Runtime config, file save/load, dirty state, dashboard hydration, service snapshots, and secret redaction.",
        cpp_status: "C++ missing: Config schema parity; Save/load and dirty-state semantics; Secret redaction behavior",
        rust_status: "Rust missing: Config schema parity; Persistence status parity; Secret redaction behavior",
        required_before_full_parity: "C++: Config schema parity; Save/load and dirty-state semantics; Secret redaction behavior | Rust: Config schema parity; Persistence status parity; Secret redaction behavior",
        cpp_full_parity: false,
        rust_full_parity: false,
    },
    PythonParityDomain {
        key: "strategy_runtime",
        title: "Strategy runtime and signal generation",
        python_surface: "Indicator computation, strategy cycles, signal generation, live candle options, override tables, and worker lifecycle.",
        cpp_status: "C++ missing: Strategy cycle parity; Indicator value semantics parity; Worker lifecycle and override provenance tests",
        rust_status: "Rust missing: Native strategy runtime or strict Python-service delegation; Signal regression tests; Override provenance tests",
        required_before_full_parity: "C++: Strategy cycle parity; Indicator value semantics parity; Worker lifecycle and override provenance tests | Rust: Native strategy runtime or strict Python-service delegation; Signal regression tests; Override provenance tests",
        cpp_full_parity: false,
        rust_full_parity: false,
    },
    PythonParityDomain {
        key: "exchange_connectors",
        title: "Exchange connectors and market data",
        python_surface: "Binance SDK/connector/CCXT/python-binance selection, connector support metadata, transport diagnostics, rate limits, REST market data, and WebSocket paths.",
        cpp_status: "C++ missing: Connector backend parity; Diagnostics and rate-limit parity; Non-Binance support behavior",
        rust_status: "Rust missing: Connector support metadata; WebSocket parity; Signed account/order clients",
        required_before_full_parity: "C++: Connector backend parity; Diagnostics and rate-limit parity; Non-Binance support behavior | Rust: Connector support metadata; WebSocket parity; Signed account/order clients",
        cpp_full_parity: false,
        rust_full_parity: false,
    },
    PythonParityDomain {
        key: "account_portfolio_positions",
        title: "Account, portfolio, and positions",
        python_surface: "Account snapshots, portfolio summaries, futures position queries, close-all behavior, position history, allocation tracking, and reconciliation.",
        cpp_status: "C++ missing: Portfolio DTO parity; History/allocation ledgers; Manual close reconciliation tests",
        rust_status: "Rust missing: Signed account clients; Balance and position DTOs; Manual close reconciliation tests",
        required_before_full_parity: "C++: Portfolio DTO parity; History/allocation ledgers; Manual close reconciliation tests | Rust: Signed account clients; Balance and position DTOs; Manual close reconciliation tests",
        cpp_full_parity: false,
        rust_full_parity: false,
    },
    PythonParityDomain {
        key: "order_execution_and_risk",
        title: "Order execution, audit, and risk",
        python_surface: "Order sizing, submit guards, audit logs, position gates, close-opposite logic, stop-loss scopes, live safety preflight, circuit breaker, and shutdown guards.",
        cpp_status: "C++ missing: Order audit contract; Live safety preflight parity; Circuit-breaker and shutdown guard parity",
        rust_status: "Rust missing: Order intent validation; Precision and reduce-only rules; Audit and circuit-breaker tests before native execution",
        required_before_full_parity: "C++: Order audit contract; Live safety preflight parity; Circuit-breaker and shutdown guard parity | Rust: Order intent validation; Precision and reduce-only rules; Audit and circuit-breaker tests before native execution",
        cpp_full_parity: false,
        rust_full_parity: false,
    },
    PythonParityDomain {
        key: "backtest_engine",
        title: "Backtest engine, optimizer, and scanner",
        python_surface: "Backtest engine, optimizer limits/results, live parity request shape, scanner polling, dashboard import, indicator selection, and provenance.",
        cpp_status: "C++ missing: Result/provenance parity tests",
        rust_status: "Rust missing: Result/provenance parity tests",
        required_before_full_parity: "C++: Result/provenance parity tests | Rust: Result/provenance parity tests",
        cpp_full_parity: false,
        rust_full_parity: false,
    },
    PythonParityDomain {
        key: "charts_and_heatmaps",
        title: "Charts and liquidation heatmaps",
        python_surface: "TradingView, lightweight chart assets, candlestick fallback, chart state payloads, browser guards, and liquidation provider panels.",
        cpp_status: "C++ missing: Chart state parity; Asset loading and fallback rendering tests; Browser guard logging parity",
        rust_status: "Rust missing: Chart state parity; Heatmap provider parity; Visual smoke coverage",
        required_before_full_parity: "C++: Chart state parity; Asset loading and fallback rendering tests; Browser guard logging parity | Rust: Chart state parity; Heatmap provider parity; Visual smoke coverage",
        cpp_full_parity: false,
        rust_full_parity: false,
    },
    PythonParityDomain {
        key: "logs_terminal_diagnostics",
        title: "Logs, terminal, and diagnostics",
        python_surface: "Service logs, dashboard logs, terminal command execution, exception diagnostics, secret redaction, and test runner/reporting flows.",
        cpp_status: "C++ missing: Service log schema parity; Terminal route behavior; Diagnostic redaction tests",
        rust_status: "Rust missing: Service log schema parity; Terminal route behavior or explicit delegation; Diagnostic redaction tests",
        required_before_full_parity: "C++: Service log schema parity; Terminal route behavior; Diagnostic redaction tests | Rust: Service log schema parity; Terminal route behavior or explicit delegation; Diagnostic redaction tests",
        cpp_full_parity: false,
        rust_full_parity: false,
    },
    PythonParityDomain {
        key: "llm_advisory",
        title: "LLM advisory and local model lifecycle",
        python_surface: "Provider catalogs, privacy flags, advisory prompt execution, config persistence, local Ollama status/start/pull/delete, and redacted output.",
        cpp_status: "C++ missing: Local model progress/cancellation UI; LLM result rendering and redaction tests",
        rust_status: "Rust missing: LLM route parity; Local model lifecycle parity; Prompt/redaction tests",
        required_before_full_parity: "C++: Local model progress/cancellation UI; LLM result rendering and redaction tests | Rust: LLM route parity; Local model lifecycle parity; Prompt/redaction tests",
        cpp_full_parity: false,
        rust_full_parity: false,
    },
    PythonParityDomain {
        key: "startup_packaging_platform",
        title: "Startup, packaging, and platform integration",
        python_surface: "Product entrypoints, startup splash/suppression, Windows taskbar metadata, PyInstaller packaging, service wrappers, and release smoke tests.",
        cpp_status: "C++ missing: Native packaging parity; Startup suppression and platform metadata; Release smoke coverage",
        rust_status: "Rust missing: Native packaging parity; Startup suppression and platform metadata; Release smoke coverage",
        required_before_full_parity: "C++: Native packaging parity; Startup suppression and platform metadata; Release smoke coverage | Rust: Native packaging parity; Startup suppression and platform metadata; Release smoke coverage",
        cpp_full_parity: false,
        rust_full_parity: false,
    },
];

pub const PYTHON_PARITY_DOMAIN_KEYS: &[&str] = &[
    "desktop_shell_and_tabs",
    "service_api_contract",
    "config_persistence",
    "strategy_runtime",
    "exchange_connectors",
    "account_portfolio_positions",
    "order_execution_and_risk",
    "backtest_engine",
    "charts_and_heatmaps",
    "logs_terminal_diagnostics",
    "llm_advisory",
    "startup_packaging_platform",
];

pub const PYTHON_SERVICE_ROUTE_NAMES: &[&str] = &[
    "runtime",
    "dashboard",
    "status",
    "execution",
    "backtest",
    "config_summary",
    "config",
    "config_persistence",
    "config_save",
    "config_load",
    "runtime_state",
    "operational_preflight",
    "control_start",
    "control_stop",
    "control_start_failed",
    "connector_order_circuit_breaker",
    "connector_order_circuit_breaker_reset",
    "connector_order_circuit_incidents",
    "backtest_run",
    "backtest_stop",
    "account",
    "portfolio",
    "exchange_connector",
    "logs",
    "terminal_run",
    "llm_providers",
    "llm_config",
    "llm_prompt",
    "llm_local_model_status",
    "llm_local_model_start",
    "llm_local_model_pull",
    "llm_local_model_delete",
    "stream_dashboard",
];

pub struct PythonServiceRoute {
    pub name: &'static str,
    pub path: &'static str,
    pub methods: &'static [&'static str],
}

pub const PYTHON_SERVICE_ROUTES: &[PythonServiceRoute] = &[
    PythonServiceRoute {
        name: "runtime",
        path: "/api/v1/runtime",
        methods: &["GET"],
    },
    PythonServiceRoute {
        name: "dashboard",
        path: "/api/v1/dashboard",
        methods: &["GET"],
    },
    PythonServiceRoute {
        name: "status",
        path: "/api/v1/status",
        methods: &["GET"],
    },
    PythonServiceRoute {
        name: "execution",
        path: "/api/v1/execution",
        methods: &["GET"],
    },
    PythonServiceRoute {
        name: "backtest",
        path: "/api/v1/backtest",
        methods: &["GET"],
    },
    PythonServiceRoute {
        name: "config_summary",
        path: "/api/v1/config-summary",
        methods: &["GET"],
    },
    PythonServiceRoute {
        name: "config",
        path: "/api/v1/config",
        methods: &["GET", "PUT", "PATCH"],
    },
    PythonServiceRoute {
        name: "config_persistence",
        path: "/api/v1/config/persistence",
        methods: &["GET"],
    },
    PythonServiceRoute {
        name: "config_save",
        path: "/api/v1/config/save",
        methods: &["POST"],
    },
    PythonServiceRoute {
        name: "config_load",
        path: "/api/v1/config/load",
        methods: &["POST"],
    },
    PythonServiceRoute {
        name: "runtime_state",
        path: "/api/v1/runtime/state",
        methods: &["PUT"],
    },
    PythonServiceRoute {
        name: "operational_preflight",
        path: "/api/v1/runtime/operational-preflight",
        methods: &["GET"],
    },
    PythonServiceRoute {
        name: "control_start",
        path: "/api/v1/control/start",
        methods: &["POST"],
    },
    PythonServiceRoute {
        name: "control_stop",
        path: "/api/v1/control/stop",
        methods: &["POST"],
    },
    PythonServiceRoute {
        name: "control_start_failed",
        path: "/api/v1/control/start-failed",
        methods: &["POST"],
    },
    PythonServiceRoute {
        name: "connector_order_circuit_breaker",
        path: "/api/v1/runtime/connector-order-circuit-breaker",
        methods: &["GET", "PUT"],
    },
    PythonServiceRoute {
        name: "connector_order_circuit_breaker_reset",
        path: "/api/v1/runtime/connector-order-circuit-breaker/reset",
        methods: &["POST"],
    },
    PythonServiceRoute {
        name: "connector_order_circuit_incidents",
        path: "/api/v1/runtime/connector-order-circuit-breaker/incidents",
        methods: &["GET"],
    },
    PythonServiceRoute {
        name: "backtest_run",
        path: "/api/v1/backtest/run",
        methods: &["POST"],
    },
    PythonServiceRoute {
        name: "backtest_stop",
        path: "/api/v1/backtest/stop",
        methods: &["POST"],
    },
    PythonServiceRoute {
        name: "account",
        path: "/api/v1/account",
        methods: &["GET", "PUT"],
    },
    PythonServiceRoute {
        name: "portfolio",
        path: "/api/v1/portfolio",
        methods: &["GET", "PUT"],
    },
    PythonServiceRoute {
        name: "exchange_connector",
        path: "/api/v1/exchange/connector",
        methods: &["GET", "PUT"],
    },
    PythonServiceRoute {
        name: "logs",
        path: "/api/v1/logs",
        methods: &["GET", "POST"],
    },
    PythonServiceRoute {
        name: "terminal_run",
        path: "/api/v1/terminal/run",
        methods: &["POST"],
    },
    PythonServiceRoute {
        name: "llm_providers",
        path: "/api/v1/llm/providers",
        methods: &["GET"],
    },
    PythonServiceRoute {
        name: "llm_config",
        path: "/api/v1/llm/config",
        methods: &["GET", "PATCH"],
    },
    PythonServiceRoute {
        name: "llm_prompt",
        path: "/api/v1/llm/prompt",
        methods: &["POST"],
    },
    PythonServiceRoute {
        name: "llm_local_model_status",
        path: "/api/v1/llm/local-model/status",
        methods: &["GET"],
    },
    PythonServiceRoute {
        name: "llm_local_model_start",
        path: "/api/v1/llm/local-model/start",
        methods: &["POST"],
    },
    PythonServiceRoute {
        name: "llm_local_model_pull",
        path: "/api/v1/llm/local-model/pull",
        methods: &["POST"],
    },
    PythonServiceRoute {
        name: "llm_local_model_delete",
        path: "/api/v1/llm/local-model/delete",
        methods: &["POST"],
    },
    PythonServiceRoute {
        name: "stream_dashboard",
        path: "/api/v1/stream/dashboard",
        methods: &["GET"],
    },
];

pub const PYTHON_BACKTEST_RUN_REQUEST_FIELDS: &[&str] = &[
    "account_mode",
    "account_type",
    "api_key",
    "api_secret",
    "assets_mode",
    "backtest",
    "capital",
    "connector_backend",
    "end",
    "indicators",
    "intervals",
    "leverage",
    "logic",
    "margin_mode",
    "mdd_logic",
    "mode",
    "optimizer_combo_size",
    "optimizer_metric",
    "optimizer_min_trades",
    "optimizer_mode",
    "pair_overrides",
    "position_mode",
    "position_pct",
    "position_pct_units",
    "scan_mdd_limit",
    "scan_scope",
    "scan_top_n",
    "side",
    "start",
    "stop_loss",
    "symbol_source",
    "symbols",
];

pub const PYTHON_INDICATOR_KEYS: &[&str] = &[
    "ma",
    "donchian",
    "psar",
    "bb",
    "bbw",
    "keltner",
    "ichimoku",
    "rsi",
    "volume",
    "obv",
    "rvol",
    "cmf",
    "cci",
    "roc",
    "trix",
    "ppo",
    "ao",
    "kst",
    "aroon",
    "chop",
    "atr",
    "natr",
    "vwap",
    "mfi",
    "stoch_rsi",
    "willr",
    "macd",
    "uo",
    "adx",
    "dmi",
    "supertrend",
    "ema",
    "stochastic",
];

pub struct PythonIndicator {
    pub key: &'static str,
    pub display_name: &'static str,
    pub default_enabled: bool,
}

pub const PYTHON_INDICATOR_CATALOG: &[PythonIndicator] = &[
    PythonIndicator {
        key: "ma",
        display_name: "Moving Average (MA)",
        default_enabled: false,
    },
    PythonIndicator {
        key: "donchian",
        display_name: "Donchian Channels (DC)",
        default_enabled: false,
    },
    PythonIndicator {
        key: "psar",
        display_name: "Parabolic SAR (PSAR)",
        default_enabled: false,
    },
    PythonIndicator {
        key: "bb",
        display_name: "Bollinger Bands (BB)",
        default_enabled: false,
    },
    PythonIndicator {
        key: "bbw",
        display_name: "Bollinger Band Width (BBW)",
        default_enabled: false,
    },
    PythonIndicator {
        key: "keltner",
        display_name: "Keltner Channels (KC)",
        default_enabled: false,
    },
    PythonIndicator {
        key: "ichimoku",
        display_name: "Ichimoku Cloud (IC)",
        default_enabled: false,
    },
    PythonIndicator {
        key: "rsi",
        display_name: "Relative Strength Index (RSI)",
        default_enabled: true,
    },
    PythonIndicator {
        key: "volume",
        display_name: "Volume",
        default_enabled: false,
    },
    PythonIndicator {
        key: "obv",
        display_name: "On-Balance Volume (OBV)",
        default_enabled: false,
    },
    PythonIndicator {
        key: "rvol",
        display_name: "Relative Volume (RVOL)",
        default_enabled: false,
    },
    PythonIndicator {
        key: "cmf",
        display_name: "Chaikin Money Flow (CMF)",
        default_enabled: false,
    },
    PythonIndicator {
        key: "cci",
        display_name: "Commodity Channel Index (CCI)",
        default_enabled: false,
    },
    PythonIndicator {
        key: "roc",
        display_name: "Rate of Change (ROC)",
        default_enabled: false,
    },
    PythonIndicator {
        key: "trix",
        display_name: "Triple Exponential Average (TRIX)",
        default_enabled: false,
    },
    PythonIndicator {
        key: "ppo",
        display_name: "Percentage Price Oscillator (PPO)",
        default_enabled: false,
    },
    PythonIndicator {
        key: "ao",
        display_name: "Awesome Oscillator (AO)",
        default_enabled: false,
    },
    PythonIndicator {
        key: "kst",
        display_name: "Know Sure Thing (KST)",
        default_enabled: false,
    },
    PythonIndicator {
        key: "aroon",
        display_name: "Aroon Oscillator (AROON)",
        default_enabled: false,
    },
    PythonIndicator {
        key: "chop",
        display_name: "Choppiness Index (CHOP)",
        default_enabled: false,
    },
    PythonIndicator {
        key: "atr",
        display_name: "Average True Range (ATR)",
        default_enabled: false,
    },
    PythonIndicator {
        key: "natr",
        display_name: "Normalized Average True Range (NATR)",
        default_enabled: false,
    },
    PythonIndicator {
        key: "vwap",
        display_name: "Volume Weighted Average Price (VWAP)",
        default_enabled: false,
    },
    PythonIndicator {
        key: "mfi",
        display_name: "Money Flow Index (MFI)",
        default_enabled: false,
    },
    PythonIndicator {
        key: "stoch_rsi",
        display_name: "Stochastic RSI (SRSI)",
        default_enabled: false,
    },
    PythonIndicator {
        key: "willr",
        display_name: "Williams %R",
        default_enabled: false,
    },
    PythonIndicator {
        key: "macd",
        display_name: "Moving Average Convergence/Divergence (MACD)",
        default_enabled: false,
    },
    PythonIndicator {
        key: "uo",
        display_name: "Ultimate Oscillator (UO)",
        default_enabled: false,
    },
    PythonIndicator {
        key: "adx",
        display_name: "Average Directional Index (ADX)",
        default_enabled: false,
    },
    PythonIndicator {
        key: "dmi",
        display_name: "Directional Movement Index (DMI)",
        default_enabled: false,
    },
    PythonIndicator {
        key: "supertrend",
        display_name: "SuperTrend (ST)",
        default_enabled: false,
    },
    PythonIndicator {
        key: "ema",
        display_name: "Exponential Moving Average (EMA)",
        default_enabled: false,
    },
    PythonIndicator {
        key: "stochastic",
        display_name: "Stochastic Oscillator",
        default_enabled: false,
    },
];

pub const PYTHON_LLM_PROVIDER_KEYS: &[&str] = &[
    "openai",
    "anthropic",
    "gemini",
    "deepseek",
    "mistral",
    "grok",
    "qwen",
    "local",
];

pub struct PythonLlmProvider {
    pub key: &'static str,
    pub label: &'static str,
    pub mode: &'static str,
    pub protocol: &'static str,
    pub default_base_url: &'static str,
    pub default_model: &'static str,
    pub api_key_env: &'static str,
    pub model_suggestions: &'static [&'static str],
    pub reasoning_efforts: &'static [&'static str],
    pub default_reasoning_effort: &'static str,
}

pub const PYTHON_LLM_PROVIDERS: &[PythonLlmProvider] = &[
    PythonLlmProvider {
        key: "openai",
        label: "OpenAI / ChatGPT",
        mode: "cloud",
        protocol: "openai-chat-completions",
        default_base_url: "https://api.openai.com/v1",
        default_model: "gpt-5.5",
        api_key_env: "OPENAI_API_KEY",
        model_suggestions: &["gpt-5.5", "gpt-5.5-2026-04-23", "gpt-5.5-pro", "gpt-5.5-pro-2026-04-23", "gpt-5.4", "gpt-5.4-2026-03-05", "gpt-5.4-pro", "gpt-5.4-pro-2026-03-05", "gpt-5.4-mini", "gpt-5.4-mini-2026-03-17", "gpt-5.4-nano", "gpt-5.4-nano-2026-03-17", "gpt-5.3-chat-latest", "gpt-5.3-codex", "gpt-5.2", "gpt-5.2-codex", "gpt-5.2-chat-latest", "gpt-5.2-pro", "gpt-5.1", "gpt-5-codex", "gpt-5-mini", "gpt-5-nano", "gpt-4.1", "gpt-4.1-mini", "gpt-4.1-nano"],
        reasoning_efforts: &["default", "none", "minimal", "low", "medium", "high", "xhigh"],
        default_reasoning_effort: "default",
    },
    PythonLlmProvider {
        key: "anthropic",
        label: "Anthropic Claude",
        mode: "cloud",
        protocol: "anthropic-messages",
        default_base_url: "https://api.anthropic.com",
        default_model: "claude-sonnet-4-5-20250929",
        api_key_env: "ANTHROPIC_API_KEY",
        model_suggestions: &["claude-sonnet-4-5-20250929", "claude-haiku-4-5-20251001", "claude-opus-4-5-20251101", "claude-opus-4-1-20250805", "claude-opus-4-20250514", "claude-sonnet-4-20250514", "claude-sonnet-4-5", "claude-haiku-4-5", "claude-opus-4-5", "claude-opus-4-1", "claude-opus-4-0", "claude-sonnet-4-0"],
        reasoning_efforts: &["default", "disabled", "enabled", "low", "medium", "high"],
        default_reasoning_effort: "default",
    },
    PythonLlmProvider {
        key: "gemini",
        label: "Google Gemini",
        mode: "cloud",
        protocol: "gemini-generate-content",
        default_base_url: "https://generativelanguage.googleapis.com/v1beta",
        default_model: "gemini-3-flash-preview",
        api_key_env: "GEMINI_API_KEY",
        model_suggestions: &["gemini-3.1-pro-preview", "gemini-3.1-pro-preview-customtools", "gemini-3-flash-preview", "gemini-3.1-flash-lite-preview", "gemini-2.5-pro", "gemini-2.5-flash", "gemini-2.5-flash-preview-09-2025", "gemini-2.5-flash-lite", "gemini-2.5-flash-lite-preview-09-2025"],
        reasoning_efforts: &["default", "minimal", "low", "medium", "high"],
        default_reasoning_effort: "default",
    },
    PythonLlmProvider {
        key: "deepseek",
        label: "DeepSeek",
        mode: "cloud",
        protocol: "openai-chat-completions",
        default_base_url: "https://api.deepseek.com",
        default_model: "deepseek-v4-flash",
        api_key_env: "DEEPSEEK_API_KEY",
        model_suggestions: &["deepseek-v4-flash", "deepseek-v4-pro", "deepseek-chat", "deepseek-reasoner"],
        reasoning_efforts: &["default", "disabled", "enabled", "high", "max"],
        default_reasoning_effort: "default",
    },
    PythonLlmProvider {
        key: "mistral",
        label: "Mistral AI",
        mode: "cloud",
        protocol: "openai-chat-completions",
        default_base_url: "https://api.mistral.ai/v1",
        default_model: "mistral-small-latest",
        api_key_env: "MISTRAL_API_KEY",
        model_suggestions: &["mistral-large-latest", "mistral-medium-latest", "mistral-small-latest", "codestral-latest", "open-mistral-nemo"],
        reasoning_efforts: &["default", "low", "medium", "high"],
        default_reasoning_effort: "default",
    },
    PythonLlmProvider {
        key: "grok",
        label: "xAI Grok",
        mode: "cloud",
        protocol: "openai-chat-completions",
        default_base_url: "https://api.x.ai/v1",
        default_model: "grok-4.3",
        api_key_env: "XAI_API_KEY",
        model_suggestions: &["grok-4.3", "grok-4.3-latest", "grok-4.20", "grok-4.20-reasoning", "grok-4.20-non-reasoning", "grok-4-fast-reasoning", "grok-4-fast-non-reasoning"],
        reasoning_efforts: &["default", "low", "medium", "high"],
        default_reasoning_effort: "default",
    },
    PythonLlmProvider {
        key: "qwen",
        label: "Alibaba Qwen / DashScope",
        mode: "cloud",
        protocol: "openai-chat-completions",
        default_base_url: "https://dashscope-intl.aliyuncs.com/compatible-mode/v1",
        default_model: "qwen3.6-plus",
        api_key_env: "DASHSCOPE_API_KEY",
        model_suggestions: &["qwen3.6-max-preview", "qwen3.6-plus", "qwen3.6-plus-2026-04-02", "qwen3.6-flash", "qwen3.6-flash-2026-04-16", "qwen3-max", "qwen3-max-2026-01-23", "qwen3-max-2025-09-23", "qwen3-max-preview", "qwen3.5-plus", "qwen3.5-plus-2026-02-15", "qwen3.5-flash", "qwen3.5-flash-2026-02-23", "qwen3-coder-plus", "qwen3-coder-flash", "qwen-plus-us", "qwen-flash-us"],
        reasoning_efforts: &["default", "low", "medium", "high"],
        default_reasoning_effort: "default",
    },
    PythonLlmProvider {
        key: "local",
        label: "Local / Custom OpenAI-Compatible",
        mode: "local",
        protocol: "openai-chat-completions",
        default_base_url: "http://127.0.0.1:11434/v1",
        default_model: "qwen3:8b",
        api_key_env: "LOCAL_LLM_API_KEY",
        model_suggestions: &["qwen3:0.6b", "qwen3:1.7b", "qwen3:4b", "qwen3:8b", "qwen3:14b", "qwen3:30b-a3b", "qwen3:32b", "qwen3", "gpt-oss:20b", "gpt-oss:latest", "llama3.3", "llama3.1:8b", "llama3.2:3b", "llama3.2:1b", "mistral-small3.2", "deepseek-r1:8b", "gemma3:4b", "custom-model"],
        reasoning_efforts: &["default", "none", "low", "medium", "high", "xhigh"],
        default_reasoning_effort: "default",
    },
];

pub const PYTHON_CONNECTOR_KEYS: &[&str] = &[
    "binance-sdk-derivatives-trading-usds-futures",
    "binance-sdk-derivatives-trading-coin-futures",
    "binance-sdk-spot",
    "binance-connector",
    "ccxt",
    "python-binance",
];

pub struct PythonConnectorOption {
    pub key: &'static str,
    pub label: &'static str,
}

pub const PYTHON_CONNECTOR_OPTIONS: &[PythonConnectorOption] = &[
    PythonConnectorOption {
        key: "binance-sdk-derivatives-trading-usds-futures",
        label: "Binance SDK Derivatives Trading USD\u{24c8} Futures (Official Recommended)",
    },
    PythonConnectorOption {
        key: "binance-sdk-derivatives-trading-coin-futures",
        label: "Binance SDK Derivatives Trading COIN-M Futures",
    },
    PythonConnectorOption {
        key: "binance-sdk-spot",
        label: "Binance SDK Spot (Official Recommended)",
    },
    PythonConnectorOption {
        key: "binance-connector",
        label: "Binance Connector Python",
    },
    PythonConnectorOption {
        key: "ccxt",
        label: "CCXT (Unified)",
    },
    PythonConnectorOption {
        key: "python-binance",
        label: "python-binance (Community)",
    },
];

pub const PYTHON_BACKTEST_INTERVALS: &[&str] = &[
    "1m",
    "3m",
    "5m",
    "10m",
    "15m",
    "20m",
    "30m",
    "1h",
    "2h",
    "3h",
    "4h",
    "5h",
    "6h",
    "7h",
    "8h",
    "9h",
    "10h",
    "11h",
    "12h",
    "1d",
    "2d",
    "3d",
    "4d",
    "5d",
    "6d",
    "1w",
    "2w",
    "3w",
    "1month",
    "2months",
    "3months",
    "6months",
    "1mo",
    "2mo",
    "3mo",
    "6mo",
    "1y",
    "2y",
];

pub struct PythonTradingViewInterval {
    pub interval: &'static str,
    pub code: &'static str,
}

pub const PYTHON_TRADINGVIEW_INTERVAL_MAP: &[PythonTradingViewInterval] = &[
    PythonTradingViewInterval {
        interval: "1m",
        code: "1",
    },
    PythonTradingViewInterval {
        interval: "3m",
        code: "3",
    },
    PythonTradingViewInterval {
        interval: "5m",
        code: "5",
    },
    PythonTradingViewInterval {
        interval: "10m",
        code: "10",
    },
    PythonTradingViewInterval {
        interval: "15m",
        code: "15",
    },
    PythonTradingViewInterval {
        interval: "20m",
        code: "20",
    },
    PythonTradingViewInterval {
        interval: "30m",
        code: "30",
    },
    PythonTradingViewInterval {
        interval: "45m",
        code: "45",
    },
    PythonTradingViewInterval {
        interval: "1h",
        code: "60",
    },
    PythonTradingViewInterval {
        interval: "2h",
        code: "120",
    },
    PythonTradingViewInterval {
        interval: "3h",
        code: "180",
    },
    PythonTradingViewInterval {
        interval: "4h",
        code: "240",
    },
    PythonTradingViewInterval {
        interval: "5h",
        code: "300",
    },
    PythonTradingViewInterval {
        interval: "6h",
        code: "360",
    },
    PythonTradingViewInterval {
        interval: "7h",
        code: "420",
    },
    PythonTradingViewInterval {
        interval: "8h",
        code: "480",
    },
    PythonTradingViewInterval {
        interval: "9h",
        code: "540",
    },
    PythonTradingViewInterval {
        interval: "10h",
        code: "600",
    },
    PythonTradingViewInterval {
        interval: "11h",
        code: "660",
    },
    PythonTradingViewInterval {
        interval: "12h",
        code: "720",
    },
    PythonTradingViewInterval {
        interval: "1d",
        code: "1D",
    },
    PythonTradingViewInterval {
        interval: "2d",
        code: "2D",
    },
    PythonTradingViewInterval {
        interval: "3d",
        code: "3D",
    },
    PythonTradingViewInterval {
        interval: "4d",
        code: "4D",
    },
    PythonTradingViewInterval {
        interval: "5d",
        code: "5D",
    },
    PythonTradingViewInterval {
        interval: "6d",
        code: "6D",
    },
    PythonTradingViewInterval {
        interval: "1w",
        code: "1W",
    },
    PythonTradingViewInterval {
        interval: "2w",
        code: "2W",
    },
    PythonTradingViewInterval {
        interval: "3w",
        code: "3W",
    },
    PythonTradingViewInterval {
        interval: "1mo",
        code: "1M",
    },
    PythonTradingViewInterval {
        interval: "2mo",
        code: "2M",
    },
    PythonTradingViewInterval {
        interval: "3mo",
        code: "3M",
    },
    PythonTradingViewInterval {
        interval: "6mo",
        code: "6M",
    },
    PythonTradingViewInterval {
        interval: "1month",
        code: "1M",
    },
    PythonTradingViewInterval {
        interval: "2months",
        code: "2M",
    },
    PythonTradingViewInterval {
        interval: "3months",
        code: "3M",
    },
    PythonTradingViewInterval {
        interval: "6months",
        code: "6M",
    },
    PythonTradingViewInterval {
        interval: "1y",
        code: "12M",
    },
    PythonTradingViewInterval {
        interval: "2y",
        code: "24M",
    },
];

pub const PYTHON_DEFAULT_CHART_SYMBOLS: &[&str] = &[
    "BTCUSDT",
    "ETHUSDT",
    "BNBUSDT",
    "SOLUSDT",
    "XRPUSDT",
    "ADAUSDT",
    "DOGEUSDT",
    "AVAXUSDT",
    "LINKUSDT",
    "TRXUSDT",
];

pub const PYTHON_DEFAULT_EXECUTION_SYMBOLS: &[&str] = &[
    "BTCUSDT",
];

pub const PYTHON_DEFAULT_EXECUTION_INTERVALS: &[&str] = &[
    "1m",
];

pub const PYTHON_DEFAULT_BACKTEST_SYMBOLS: &[&str] = &[
    "BTCUSDT",
];

pub const PYTHON_DEFAULT_BACKTEST_INTERVALS: &[&str] = &[
    "1h",
];

pub const PYTHON_CHART_MARKET_OPTIONS: &[&str] = &[
    "Futures",
    "Spot",
];

pub const PYTHON_ACCOUNT_MODE_OPTIONS: &[&str] = &[
    "Classic Trading",
    "Portfolio Margin",
];

pub struct PythonUiOption {
    pub key: &'static str,
    pub label: &'static str,
    pub disabled: bool,
}

pub const PYTHON_DASHBOARD_LOOP_CHOICES: &[PythonUiOption] = &[
    PythonUiOption {
        key: "30s",
        label: "30 seconds",
        disabled: false,
    },
    PythonUiOption {
        key: "45s",
        label: "45 seconds",
        disabled: false,
    },
    PythonUiOption {
        key: "1m",
        label: "1 minute",
        disabled: false,
    },
    PythonUiOption {
        key: "2m",
        label: "2 minutes",
        disabled: false,
    },
    PythonUiOption {
        key: "3m",
        label: "3 minutes",
        disabled: false,
    },
    PythonUiOption {
        key: "5m",
        label: "5 minutes",
        disabled: false,
    },
    PythonUiOption {
        key: "10m",
        label: "10 minutes",
        disabled: false,
    },
    PythonUiOption {
        key: "30m",
        label: "30 minutes",
        disabled: false,
    },
    PythonUiOption {
        key: "1h",
        label: "1 hour",
        disabled: false,
    },
    PythonUiOption {
        key: "2h",
        label: "2 hours",
        disabled: false,
    },
];

pub const PYTHON_LEAD_TRADER_OPTIONS: &[PythonUiOption] = &[
    PythonUiOption {
        key: "futures_public",
        label: "Futures Public Lead Trader",
        disabled: false,
    },
    PythonUiOption {
        key: "futures_private",
        label: "Futures Private Lead Trader",
        disabled: false,
    },
    PythonUiOption {
        key: "spot_public",
        label: "Spot Public Lead Trader",
        disabled: false,
    },
    PythonUiOption {
        key: "spot_private",
        label: "Spot Private Lead Trader",
        disabled: false,
    },
];

pub const PYTHON_LLM_USE_FOR_OPTIONS: &[PythonUiOption] = &[
    PythonUiOption {
        key: "advisory",
        label: "Advisory",
        disabled: false,
    },
    PythonUiOption {
        key: "signal_confirmation",
        label: "Signal confirmation",
        disabled: false,
    },
    PythonUiOption {
        key: "risk_review",
        label: "Risk review",
        disabled: false,
    },
    PythonUiOption {
        key: "backtest_explanation",
        label: "Backtest explanation",
        disabled: false,
    },
];

pub const PYTHON_DASHBOARD_STRATEGY_TEMPLATES: &[PythonUiOption] = &[
    PythonUiOption {
        key: "",
        label: "No Template",
        disabled: false,
    },
    PythonUiOption {
        key: "top10",
        label: "Top 10 %2 per trade 1x Isolated",
        disabled: false,
    },
    PythonUiOption {
        key: "top50",
        label: "Top 50 %2 per trade 1x",
        disabled: false,
    },
    PythonUiOption {
        key: "top100",
        label: "Top 100 %1 per trade 1x",
        disabled: false,
    },
];

pub const PYTHON_BACKTEST_TEMPLATES: &[PythonUiOption] = &[
    PythonUiOption {
        key: "volume_top50",
        label: "First 50 Highest Volume",
        disabled: false,
    },
    PythonUiOption {
        key: "volume_last_week",
        label: "Last 1 week \u{b7} 2% per trade \u{b7} 50 highest volume",
        disabled: false,
    },
    PythonUiOption {
        key: "top100_isolated_1pct_sl",
        label: "Top 100, %2 per trade, isolated, %20 per trade SL",
        disabled: false,
    },
];

pub const PYTHON_SIDE_OPTIONS: &[PythonUiOption] = &[
    PythonUiOption {
        key: "BUY",
        label: "Buy (Long)",
        disabled: false,
    },
    PythonUiOption {
        key: "SELL",
        label: "Sell (Short)",
        disabled: false,
    },
    PythonUiOption {
        key: "BOTH",
        label: "Both (Long/Short)",
        disabled: false,
    },
];

pub const PYTHON_CONFIG_MODE_OPTIONS: &[PythonUiOption] = &[
    PythonUiOption {
        key: "Live",
        label: "Live",
        disabled: false,
    },
    PythonUiOption {
        key: "Demo",
        label: "Demo",
        disabled: false,
    },
    PythonUiOption {
        key: "Testnet",
        label: "Testnet",
        disabled: false,
    },
];

pub const PYTHON_THEME_OPTIONS: &[PythonUiOption] = &[
    PythonUiOption {
        key: "Light",
        label: "Light",
        disabled: false,
    },
    PythonUiOption {
        key: "Dark",
        label: "Dark",
        disabled: false,
    },
    PythonUiOption {
        key: "Blue",
        label: "Blue",
        disabled: false,
    },
    PythonUiOption {
        key: "Yellow",
        label: "Yellow",
        disabled: false,
    },
    PythonUiOption {
        key: "Green",
        label: "Green",
        disabled: false,
    },
    PythonUiOption {
        key: "Red",
        label: "Red",
        disabled: false,
    },
];

pub const PYTHON_DESIGN_OPTIONS: &[PythonUiOption] = &[
    PythonUiOption {
        key: "Classic",
        label: "Classic",
        disabled: false,
    },
    PythonUiOption {
        key: "Workstation",
        label: "Workstation",
        disabled: false,
    },
];

pub const PYTHON_INDICATOR_SOURCE_OPTIONS: &[PythonUiOption] = &[
    PythonUiOption {
        key: "Binance spot",
        label: "Binance spot",
        disabled: false,
    },
    PythonUiOption {
        key: "Binance futures",
        label: "Binance futures",
        disabled: false,
    },
    PythonUiOption {
        key: "TradingView",
        label: "TradingView",
        disabled: false,
    },
    PythonUiOption {
        key: "Bybit",
        label: "Bybit",
        disabled: false,
    },
    PythonUiOption {
        key: "Coinbase",
        label: "Coinbase",
        disabled: false,
    },
    PythonUiOption {
        key: "OKX",
        label: "OKX",
        disabled: false,
    },
    PythonUiOption {
        key: "Gate",
        label: "Gate",
        disabled: false,
    },
    PythonUiOption {
        key: "Bitget",
        label: "Bitget",
        disabled: false,
    },
    PythonUiOption {
        key: "Mexc",
        label: "Mexc",
        disabled: false,
    },
    PythonUiOption {
        key: "Kucoin",
        label: "Kucoin",
        disabled: false,
    },
    PythonUiOption {
        key: "HTX",
        label: "HTX",
        disabled: false,
    },
    PythonUiOption {
        key: "Kraken",
        label: "Kraken",
        disabled: false,
    },
];

pub const PYTHON_EXCHANGE_OPTIONS: &[PythonUiOption] = &[
    PythonUiOption {
        key: "Binance",
        label: "Binance",
        disabled: false,
    },
    PythonUiOption {
        key: "Bybit",
        label: "Bybit (coming soon)",
        disabled: true,
    },
    PythonUiOption {
        key: "OKX",
        label: "OKX (coming soon)",
        disabled: true,
    },
    PythonUiOption {
        key: "Gate",
        label: "Gate (coming soon)",
        disabled: true,
    },
    PythonUiOption {
        key: "Bitget",
        label: "Bitget (coming soon)",
        disabled: true,
    },
    PythonUiOption {
        key: "MEXC",
        label: "MEXC (coming soon)",
        disabled: true,
    },
    PythonUiOption {
        key: "KuCoin",
        label: "KuCoin (coming soon)",
        disabled: true,
    },
];

pub const PYTHON_ACCOUNT_TYPE_OPTIONS: &[PythonUiOption] = &[
    PythonUiOption {
        key: "Spot",
        label: "Spot",
        disabled: false,
    },
    PythonUiOption {
        key: "Futures",
        label: "Futures",
        disabled: false,
    },
];

pub const PYTHON_MARGIN_MODE_OPTIONS: &[PythonUiOption] = &[
    PythonUiOption {
        key: "Isolated",
        label: "Isolated",
        disabled: false,
    },
    PythonUiOption {
        key: "Cross",
        label: "Cross",
        disabled: false,
    },
];

pub const PYTHON_POSITION_MODE_OPTIONS: &[PythonUiOption] = &[
    PythonUiOption {
        key: "Hedge",
        label: "Hedge",
        disabled: false,
    },
    PythonUiOption {
        key: "One-way",
        label: "One-way",
        disabled: false,
    },
];

pub const PYTHON_ASSETS_MODE_OPTIONS: &[PythonUiOption] = &[
    PythonUiOption {
        key: "Single-Asset",
        label: "Single-Asset Mode",
        disabled: false,
    },
    PythonUiOption {
        key: "Multi-Assets",
        label: "Multi-Assets Mode",
        disabled: false,
    },
];

pub const PYTHON_ORDER_TYPE_OPTIONS: &[PythonUiOption] = &[
    PythonUiOption {
        key: "MARKET",
        label: "MARKET",
        disabled: false,
    },
    PythonUiOption {
        key: "LIMIT",
        label: "LIMIT",
        disabled: false,
    },
];

pub const PYTHON_TIME_IN_FORCE_OPTIONS: &[PythonUiOption] = &[
    PythonUiOption {
        key: "GTC",
        label: "GTC",
        disabled: false,
    },
    PythonUiOption {
        key: "IOC",
        label: "IOC",
        disabled: false,
    },
    PythonUiOption {
        key: "FOK",
        label: "FOK",
        disabled: false,
    },
    PythonUiOption {
        key: "GTD",
        label: "GTD",
        disabled: false,
    },
];

pub const PYTHON_SIGNAL_LOGIC_OPTIONS: &[PythonUiOption] = &[
    PythonUiOption {
        key: "AND",
        label: "AND",
        disabled: false,
    },
    PythonUiOption {
        key: "OR",
        label: "OR",
        disabled: false,
    },
    PythonUiOption {
        key: "SEPARATE",
        label: "SEPARATE",
        disabled: false,
    },
];

pub const PYTHON_MDD_LOGIC_OPTIONS: &[PythonUiOption] = &[
    PythonUiOption {
        key: "per_trade",
        label: "Per Trade MDD",
        disabled: false,
    },
    PythonUiOption {
        key: "cumulative",
        label: "Cumulative MDD",
        disabled: false,
    },
    PythonUiOption {
        key: "entire_account",
        label: "Entire Account MDD",
        disabled: false,
    },
];

pub const PYTHON_STOP_LOSS_MODES: &[PythonUiOption] = &[
    PythonUiOption {
        key: "usdt",
        label: "USDT Based Stop Loss",
        disabled: false,
    },
    PythonUiOption {
        key: "percent",
        label: "Percentage Based Stop Loss",
        disabled: false,
    },
    PythonUiOption {
        key: "both",
        label: "Both Stop Loss (USDT & Percentage)",
        disabled: false,
    },
];

pub const PYTHON_STOP_LOSS_SCOPES: &[PythonUiOption] = &[
    PythonUiOption {
        key: "per_trade",
        label: "Per Trade Stop Loss",
        disabled: false,
    },
    PythonUiOption {
        key: "cumulative",
        label: "Cumulative Stop Loss",
        disabled: false,
    },
    PythonUiOption {
        key: "entire_account",
        label: "Entire Account Stop Loss",
        disabled: false,
    },
];

pub const PYTHON_SCAN_SCOPE_OPTIONS: &[PythonUiOption] = &[
    PythonUiOption {
        key: "selected",
        label: "selected",
        disabled: false,
    },
    PythonUiOption {
        key: "top_n",
        label: "top_n",
        disabled: false,
    },
    PythonUiOption {
        key: "all_loaded",
        label: "all_loaded",
        disabled: false,
    },
];

pub const PYTHON_OPTIMIZER_MODE_OPTIONS: &[PythonUiOption] = &[
    PythonUiOption {
        key: "current",
        label: "current",
        disabled: false,
    },
    PythonUiOption {
        key: "single",
        label: "single",
        disabled: false,
    },
    PythonUiOption {
        key: "pairs",
        label: "pairs",
        disabled: false,
    },
    PythonUiOption {
        key: "combinations",
        label: "combinations",
        disabled: false,
    },
];

pub const PYTHON_OPTIMIZER_METRIC_OPTIONS: &[PythonUiOption] = &[
    PythonUiOption {
        key: "roi_percent",
        label: "roi_percent",
        disabled: false,
    },
    PythonUiOption {
        key: "roi_percent_mdd",
        label: "roi_percent_mdd",
        disabled: false,
    },
    PythonUiOption {
        key: "roi_drawdown",
        label: "roi_drawdown",
        disabled: false,
    },
    PythonUiOption {
        key: "roi_value",
        label: "roi_value",
        disabled: false,
    },
];

pub const PYTHON_BACKTEST_EXECUTION_BACKEND_OPTIONS: &[PythonUiOption] = &[
    PythonUiOption {
        key: "local",
        label: "local",
        disabled: false,
    },
    PythonUiOption {
        key: "service",
        label: "service",
        disabled: false,
    },
];

pub const PYTHON_CHART_VIEW_OPTIONS: &[PythonUiOption] = &[
    PythonUiOption {
        key: "tradingview",
        label: "TradingView",
        disabled: false,
    },
    PythonUiOption {
        key: "original",
        label: "Original",
        disabled: false,
    },
    PythonUiOption {
        key: "lightweight",
        label: "TradingView Lightweight",
        disabled: false,
    },
];

pub const PYTHON_POSITIONS_VIEW_OPTIONS: &[PythonUiOption] = &[
    PythonUiOption {
        key: "cumulative",
        label: "Cumulative View",
        disabled: false,
    },
    PythonUiOption {
        key: "per_trade",
        label: "Per Trade View",
        disabled: false,
    },
];
