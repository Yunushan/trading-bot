// This file is generated from Languages/Python/app/native_parity.py.
// Do not edit manually; run Languages/Python/tools/generate_native_parity_contracts.py.
#pragma once

#include <array>
#include <string_view>

namespace PythonParityContract {

inline constexpr std::string_view kPythonSource = "Languages/Python";
inline constexpr unsigned kPythonSourceSchemaVersion = 1;
inline constexpr std::string_view kPythonSourceContractHash = "5f226cd68f0d40a44af7d611dd68c3b15645d452d6421854b5f31100c5533e08";
inline constexpr bool kCppFullParityReady = false;
inline constexpr bool kRustFullParityReady = false;

struct PythonParityDomain {
    std::string_view key;
    std::string_view title;
    std::string_view pythonSurface;
    std::string_view cppStatus;
    std::string_view rustStatus;
    std::string_view requiredBeforeFullParity;
    bool cppFullParity;
    bool rustFullParity;
};

inline constexpr std::array<PythonParityDomain, 12> kPythonParityDomains = {
    PythonParityDomain{"desktop_shell_and_tabs", "Desktop shell and primary tabs", "Dashboard, Chart, Positions, Backtest, Liquidation Heatmap, Code Languages, startup composition, theme, and live tab wiring.", "C++ missing: Production startup and lifecycle parity; Tab behavior parity tests; Release ownership instead of preview ownership", "Rust missing: Production desktop ownership for the selected Rust shell; Equivalent startup and tab lifecycle behavior; Remove non-operational claims from comparison renderers", "C++: Production startup and lifecycle parity; Tab behavior parity tests; Release ownership instead of preview ownership | Rust: Production desktop ownership for the selected Rust shell; Equivalent startup and tab lifecycle behavior; Remove non-operational claims from comparison renderers", false, false},
    PythonParityDomain{"service_api_contract", "Service API contract", "Canonical /api/v1 routes, methods, schemas, dashboard stream, auth, control-plane state, and desktop bridge contract.", "C++ missing: Generated schema parity beyond route/method lookup; Operational request/response tests", "Rust missing: Generated route, method, and schema parity; Tauri client behavior retained or replaced by native equivalent; Explicit non-operational boundaries for other shells", "C++: Generated schema parity beyond route/method lookup; Operational request/response tests | Rust: Generated route, method, and schema parity; Tauri client behavior retained or replaced by native equivalent; Explicit non-operational boundaries for other shells", false, false},
    PythonParityDomain{"config_persistence", "Config persistence and hydration", "Runtime config, file save/load, dirty state, dashboard hydration, service snapshots, and secret redaction.", "C++ missing: Config schema parity; Save/load and dirty-state semantics; Secret redaction behavior", "Rust missing: Config schema parity; Persistence status parity; Secret redaction behavior", "C++: Config schema parity; Save/load and dirty-state semantics; Secret redaction behavior | Rust: Config schema parity; Persistence status parity; Secret redaction behavior", false, false},
    PythonParityDomain{"strategy_runtime", "Strategy runtime and signal generation", "Indicator computation, strategy cycles, signal generation, live candle options, override tables, and worker lifecycle.", "C++ missing: Strategy cycle parity; Indicator value semantics parity; Worker lifecycle and override provenance tests", "Rust missing: Native strategy runtime or strict Python-service delegation; Signal regression tests; Override provenance tests", "C++: Strategy cycle parity; Indicator value semantics parity; Worker lifecycle and override provenance tests | Rust: Native strategy runtime or strict Python-service delegation; Signal regression tests; Override provenance tests", false, false},
    PythonParityDomain{"exchange_connectors", "Exchange connectors and market data", "Binance SDK/connector/CCXT/python-binance selection, connector support metadata, transport diagnostics, rate limits, REST market data, and WebSocket paths.", "C++ missing: Connector backend parity; Diagnostics and rate-limit parity; Non-Binance support behavior", "Rust missing: Connector support metadata; WebSocket parity; Signed account/order clients", "C++: Connector backend parity; Diagnostics and rate-limit parity; Non-Binance support behavior | Rust: Connector support metadata; WebSocket parity; Signed account/order clients", false, false},
    PythonParityDomain{"account_portfolio_positions", "Account, portfolio, and positions", "Account snapshots, portfolio summaries, futures position queries, close-all behavior, position history, allocation tracking, and reconciliation.", "C++ missing: Portfolio DTO parity; History/allocation ledgers; Manual close reconciliation tests", "Rust missing: Signed account clients; Balance and position DTOs; Manual close reconciliation tests", "C++: Portfolio DTO parity; History/allocation ledgers; Manual close reconciliation tests | Rust: Signed account clients; Balance and position DTOs; Manual close reconciliation tests", false, false},
    PythonParityDomain{"order_execution_and_risk", "Order execution, audit, and risk", "Order sizing, submit guards, audit logs, position gates, close-opposite logic, stop-loss scopes, live safety preflight, circuit breaker, and shutdown guards.", "C++ missing: Order audit contract; Live safety preflight parity; Circuit-breaker and shutdown guard parity", "Rust missing: Order intent validation; Precision and reduce-only rules; Audit and circuit-breaker tests before native execution", "C++: Order audit contract; Live safety preflight parity; Circuit-breaker and shutdown guard parity | Rust: Order intent validation; Precision and reduce-only rules; Audit and circuit-breaker tests before native execution", false, false},
    PythonParityDomain{"backtest_engine", "Backtest engine, optimizer, and scanner", "Backtest engine, optimizer limits/results, live parity request shape, scanner polling, dashboard import, indicator selection, and provenance.", "C++ missing: Result/provenance parity tests", "Rust missing: Result/provenance parity tests", "C++: Result/provenance parity tests | Rust: Result/provenance parity tests", false, false},
    PythonParityDomain{"charts_and_heatmaps", "Charts and liquidation heatmaps", "TradingView, lightweight chart assets, candlestick fallback, chart state payloads, browser guards, and liquidation provider panels.", "C++ missing: Chart state parity; Asset loading and fallback rendering tests; Browser guard logging parity", "Rust missing: Chart state parity; Heatmap provider parity; Visual smoke coverage", "C++: Chart state parity; Asset loading and fallback rendering tests; Browser guard logging parity | Rust: Chart state parity; Heatmap provider parity; Visual smoke coverage", false, false},
    PythonParityDomain{"logs_terminal_diagnostics", "Logs, terminal, and diagnostics", "Service logs, dashboard logs, terminal command execution, exception diagnostics, secret redaction, and test runner/reporting flows.", "C++ missing: Service log schema parity; Terminal route behavior; Diagnostic redaction tests", "Rust missing: Service log schema parity; Terminal route behavior or explicit delegation; Diagnostic redaction tests", "C++: Service log schema parity; Terminal route behavior; Diagnostic redaction tests | Rust: Service log schema parity; Terminal route behavior or explicit delegation; Diagnostic redaction tests", false, false},
    PythonParityDomain{"llm_advisory", "LLM advisory and local model lifecycle", "Provider catalogs, privacy flags, advisory prompt execution, config persistence, local Ollama status/start/pull/delete, and redacted output.", "C++ missing: Local model progress/cancellation UI; LLM result rendering and redaction tests", "Rust missing: LLM route parity; Local model lifecycle parity; Prompt/redaction tests", "C++: Local model progress/cancellation UI; LLM result rendering and redaction tests | Rust: LLM route parity; Local model lifecycle parity; Prompt/redaction tests", false, false},
    PythonParityDomain{"startup_packaging_platform", "Startup, packaging, and platform integration", "Product entrypoints, startup splash/suppression, Windows taskbar metadata, PyInstaller packaging, service wrappers, and release smoke tests.", "C++ missing: Native packaging parity; Startup suppression and platform metadata; Release smoke coverage", "Rust missing: Native packaging parity; Startup suppression and platform metadata; Release smoke coverage", "C++: Native packaging parity; Startup suppression and platform metadata; Release smoke coverage | Rust: Native packaging parity; Startup suppression and platform metadata; Release smoke coverage", false, false},
};

inline constexpr std::array<std::string_view, 12> kPythonParityDomainKeys = {
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
};

inline constexpr std::array<std::string_view, 33> kPythonServiceRouteNames = {
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
};

struct PythonServiceRoute {
    std::string_view name;
    std::string_view path;
    std::string_view methods;
};

inline constexpr std::array<PythonServiceRoute, 33> kPythonServiceRoutes = {
    PythonServiceRoute{"runtime", "/api/v1/runtime", "GET"},
    PythonServiceRoute{"dashboard", "/api/v1/dashboard", "GET"},
    PythonServiceRoute{"status", "/api/v1/status", "GET"},
    PythonServiceRoute{"execution", "/api/v1/execution", "GET"},
    PythonServiceRoute{"backtest", "/api/v1/backtest", "GET"},
    PythonServiceRoute{"config_summary", "/api/v1/config-summary", "GET"},
    PythonServiceRoute{"config", "/api/v1/config", "GET,PUT,PATCH"},
    PythonServiceRoute{"config_persistence", "/api/v1/config/persistence", "GET"},
    PythonServiceRoute{"config_save", "/api/v1/config/save", "POST"},
    PythonServiceRoute{"config_load", "/api/v1/config/load", "POST"},
    PythonServiceRoute{"runtime_state", "/api/v1/runtime/state", "PUT"},
    PythonServiceRoute{"operational_preflight", "/api/v1/runtime/operational-preflight", "GET"},
    PythonServiceRoute{"control_start", "/api/v1/control/start", "POST"},
    PythonServiceRoute{"control_stop", "/api/v1/control/stop", "POST"},
    PythonServiceRoute{"control_start_failed", "/api/v1/control/start-failed", "POST"},
    PythonServiceRoute{"connector_order_circuit_breaker", "/api/v1/runtime/connector-order-circuit-breaker", "GET,PUT"},
    PythonServiceRoute{"connector_order_circuit_breaker_reset", "/api/v1/runtime/connector-order-circuit-breaker/reset", "POST"},
    PythonServiceRoute{"connector_order_circuit_incidents", "/api/v1/runtime/connector-order-circuit-breaker/incidents", "GET"},
    PythonServiceRoute{"backtest_run", "/api/v1/backtest/run", "POST"},
    PythonServiceRoute{"backtest_stop", "/api/v1/backtest/stop", "POST"},
    PythonServiceRoute{"account", "/api/v1/account", "GET,PUT"},
    PythonServiceRoute{"portfolio", "/api/v1/portfolio", "GET,PUT"},
    PythonServiceRoute{"exchange_connector", "/api/v1/exchange/connector", "GET,PUT"},
    PythonServiceRoute{"logs", "/api/v1/logs", "GET,POST"},
    PythonServiceRoute{"terminal_run", "/api/v1/terminal/run", "POST"},
    PythonServiceRoute{"llm_providers", "/api/v1/llm/providers", "GET"},
    PythonServiceRoute{"llm_config", "/api/v1/llm/config", "GET,PATCH"},
    PythonServiceRoute{"llm_prompt", "/api/v1/llm/prompt", "POST"},
    PythonServiceRoute{"llm_local_model_status", "/api/v1/llm/local-model/status", "GET"},
    PythonServiceRoute{"llm_local_model_start", "/api/v1/llm/local-model/start", "POST"},
    PythonServiceRoute{"llm_local_model_pull", "/api/v1/llm/local-model/pull", "POST"},
    PythonServiceRoute{"llm_local_model_delete", "/api/v1/llm/local-model/delete", "POST"},
    PythonServiceRoute{"stream_dashboard", "/api/v1/stream/dashboard", "GET"},
};

inline constexpr std::array<std::string_view, 32> kPythonBacktestRunRequestFields = {
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
};

inline constexpr std::array<std::string_view, 33> kPythonIndicatorKeys = {
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
};

struct PythonIndicator {
    std::string_view key;
    std::string_view displayName;
    bool defaultEnabled;
};

inline constexpr std::array<PythonIndicator, 33> kPythonIndicatorCatalog = {
    PythonIndicator{"ma", "Moving Average (MA)", false},
    PythonIndicator{"donchian", "Donchian Channels (DC)", false},
    PythonIndicator{"psar", "Parabolic SAR (PSAR)", false},
    PythonIndicator{"bb", "Bollinger Bands (BB)", false},
    PythonIndicator{"bbw", "Bollinger Band Width (BBW)", false},
    PythonIndicator{"keltner", "Keltner Channels (KC)", false},
    PythonIndicator{"ichimoku", "Ichimoku Cloud (IC)", false},
    PythonIndicator{"rsi", "Relative Strength Index (RSI)", true},
    PythonIndicator{"volume", "Volume", false},
    PythonIndicator{"obv", "On-Balance Volume (OBV)", false},
    PythonIndicator{"rvol", "Relative Volume (RVOL)", false},
    PythonIndicator{"cmf", "Chaikin Money Flow (CMF)", false},
    PythonIndicator{"cci", "Commodity Channel Index (CCI)", false},
    PythonIndicator{"roc", "Rate of Change (ROC)", false},
    PythonIndicator{"trix", "Triple Exponential Average (TRIX)", false},
    PythonIndicator{"ppo", "Percentage Price Oscillator (PPO)", false},
    PythonIndicator{"ao", "Awesome Oscillator (AO)", false},
    PythonIndicator{"kst", "Know Sure Thing (KST)", false},
    PythonIndicator{"aroon", "Aroon Oscillator (AROON)", false},
    PythonIndicator{"chop", "Choppiness Index (CHOP)", false},
    PythonIndicator{"atr", "Average True Range (ATR)", false},
    PythonIndicator{"natr", "Normalized Average True Range (NATR)", false},
    PythonIndicator{"vwap", "Volume Weighted Average Price (VWAP)", false},
    PythonIndicator{"mfi", "Money Flow Index (MFI)", false},
    PythonIndicator{"stoch_rsi", "Stochastic RSI (SRSI)", false},
    PythonIndicator{"willr", "Williams %R", false},
    PythonIndicator{"macd", "Moving Average Convergence/Divergence (MACD)", false},
    PythonIndicator{"uo", "Ultimate Oscillator (UO)", false},
    PythonIndicator{"adx", "Average Directional Index (ADX)", false},
    PythonIndicator{"dmi", "Directional Movement Index (DMI)", false},
    PythonIndicator{"supertrend", "SuperTrend (ST)", false},
    PythonIndicator{"ema", "Exponential Moving Average (EMA)", false},
    PythonIndicator{"stochastic", "Stochastic Oscillator", false},
};

inline constexpr std::array<std::string_view, 8> kPythonLlmProviderKeys = {
    "openai",
    "anthropic",
    "gemini",
    "deepseek",
    "mistral",
    "grok",
    "qwen",
    "local",
};

struct PythonLlmProvider {
    std::string_view key;
    std::string_view label;
    std::string_view mode;
    std::string_view protocol;
    std::string_view defaultBaseUrl;
    std::string_view defaultModel;
    std::string_view apiKeyEnv;
    std::string_view modelSuggestions;
    std::string_view reasoningEfforts;
    std::string_view defaultReasoningEffort;
};

inline constexpr std::array<PythonLlmProvider, 8> kPythonLlmProviders = {
    PythonLlmProvider{"openai", "OpenAI / ChatGPT", "cloud", "openai-chat-completions", "https://api.openai.com/v1", "gpt-5.5", "OPENAI_API_KEY", "gpt-5.5,gpt-5.5-2026-04-23,gpt-5.5-pro,gpt-5.5-pro-2026-04-23,gpt-5.4,gpt-5.4-2026-03-05,gpt-5.4-pro,gpt-5.4-pro-2026-03-05,gpt-5.4-mini,gpt-5.4-mini-2026-03-17,gpt-5.4-nano,gpt-5.4-nano-2026-03-17,gpt-5.3-chat-latest,gpt-5.3-codex,gpt-5.2,gpt-5.2-codex,gpt-5.2-chat-latest,gpt-5.2-pro,gpt-5.1,gpt-5-codex,gpt-5-mini,gpt-5-nano,gpt-4.1,gpt-4.1-mini,gpt-4.1-nano", "default,none,minimal,low,medium,high,xhigh", "default"},
    PythonLlmProvider{"anthropic", "Anthropic Claude", "cloud", "anthropic-messages", "https://api.anthropic.com", "claude-sonnet-4-5-20250929", "ANTHROPIC_API_KEY", "claude-sonnet-4-5-20250929,claude-haiku-4-5-20251001,claude-opus-4-5-20251101,claude-opus-4-1-20250805,claude-opus-4-20250514,claude-sonnet-4-20250514,claude-sonnet-4-5,claude-haiku-4-5,claude-opus-4-5,claude-opus-4-1,claude-opus-4-0,claude-sonnet-4-0", "default,disabled,enabled,low,medium,high", "default"},
    PythonLlmProvider{"gemini", "Google Gemini", "cloud", "gemini-generate-content", "https://generativelanguage.googleapis.com/v1beta", "gemini-3-flash-preview", "GEMINI_API_KEY", "gemini-3.1-pro-preview,gemini-3.1-pro-preview-customtools,gemini-3-flash-preview,gemini-3.1-flash-lite-preview,gemini-2.5-pro,gemini-2.5-flash,gemini-2.5-flash-preview-09-2025,gemini-2.5-flash-lite,gemini-2.5-flash-lite-preview-09-2025", "default,minimal,low,medium,high", "default"},
    PythonLlmProvider{"deepseek", "DeepSeek", "cloud", "openai-chat-completions", "https://api.deepseek.com", "deepseek-v4-flash", "DEEPSEEK_API_KEY", "deepseek-v4-flash,deepseek-v4-pro,deepseek-chat,deepseek-reasoner", "default,disabled,enabled,high,max", "default"},
    PythonLlmProvider{"mistral", "Mistral AI", "cloud", "openai-chat-completions", "https://api.mistral.ai/v1", "mistral-small-latest", "MISTRAL_API_KEY", "mistral-large-latest,mistral-medium-latest,mistral-small-latest,codestral-latest,open-mistral-nemo", "default,low,medium,high", "default"},
    PythonLlmProvider{"grok", "xAI Grok", "cloud", "openai-chat-completions", "https://api.x.ai/v1", "grok-4.3", "XAI_API_KEY", "grok-4.3,grok-4.3-latest,grok-4.20,grok-4.20-reasoning,grok-4.20-non-reasoning,grok-4-fast-reasoning,grok-4-fast-non-reasoning", "default,low,medium,high", "default"},
    PythonLlmProvider{"qwen", "Alibaba Qwen / DashScope", "cloud", "openai-chat-completions", "https://dashscope-intl.aliyuncs.com/compatible-mode/v1", "qwen3.6-plus", "DASHSCOPE_API_KEY", "qwen3.6-max-preview,qwen3.6-plus,qwen3.6-plus-2026-04-02,qwen3.6-flash,qwen3.6-flash-2026-04-16,qwen3-max,qwen3-max-2026-01-23,qwen3-max-2025-09-23,qwen3-max-preview,qwen3.5-plus,qwen3.5-plus-2026-02-15,qwen3.5-flash,qwen3.5-flash-2026-02-23,qwen3-coder-plus,qwen3-coder-flash,qwen-plus-us,qwen-flash-us", "default,low,medium,high", "default"},
    PythonLlmProvider{"local", "Local / Custom OpenAI-Compatible", "local", "openai-chat-completions", "http://127.0.0.1:11434/v1", "qwen3:8b", "LOCAL_LLM_API_KEY", "qwen3:0.6b,qwen3:1.7b,qwen3:4b,qwen3:8b,qwen3:14b,qwen3:30b-a3b,qwen3:32b,qwen3,gpt-oss:20b,gpt-oss:latest,llama3.3,llama3.1:8b,llama3.2:3b,llama3.2:1b,mistral-small3.2,deepseek-r1:8b,gemma3:4b,custom-model", "default,none,low,medium,high,xhigh", "default"},
};

inline constexpr std::array<std::string_view, 6> kPythonConnectorKeys = {
    "binance-sdk-derivatives-trading-usds-futures",
    "binance-sdk-derivatives-trading-coin-futures",
    "binance-sdk-spot",
    "binance-connector",
    "ccxt",
    "python-binance",
};

struct PythonConnectorOption {
    std::string_view key;
    std::string_view label;
};

inline constexpr std::array<PythonConnectorOption, 6> kPythonConnectorOptions = {
    PythonConnectorOption{"binance-sdk-derivatives-trading-usds-futures", "Binance SDK Derivatives Trading USD\u24c8 Futures (Official Recommended)"},
    PythonConnectorOption{"binance-sdk-derivatives-trading-coin-futures", "Binance SDK Derivatives Trading COIN-M Futures"},
    PythonConnectorOption{"binance-sdk-spot", "Binance SDK Spot (Official Recommended)"},
    PythonConnectorOption{"binance-connector", "Binance Connector Python"},
    PythonConnectorOption{"ccxt", "CCXT (Unified)"},
    PythonConnectorOption{"python-binance", "python-binance (Community)"},
};

inline constexpr std::array<std::string_view, 38> kPythonBacktestIntervals = {
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
};

struct PythonTradingViewInterval {
    std::string_view interval;
    std::string_view code;
};

inline constexpr std::array<PythonTradingViewInterval, 39> kPythonTradingViewIntervalMap = {
    PythonTradingViewInterval{"1m", "1"},
    PythonTradingViewInterval{"3m", "3"},
    PythonTradingViewInterval{"5m", "5"},
    PythonTradingViewInterval{"10m", "10"},
    PythonTradingViewInterval{"15m", "15"},
    PythonTradingViewInterval{"20m", "20"},
    PythonTradingViewInterval{"30m", "30"},
    PythonTradingViewInterval{"45m", "45"},
    PythonTradingViewInterval{"1h", "60"},
    PythonTradingViewInterval{"2h", "120"},
    PythonTradingViewInterval{"3h", "180"},
    PythonTradingViewInterval{"4h", "240"},
    PythonTradingViewInterval{"5h", "300"},
    PythonTradingViewInterval{"6h", "360"},
    PythonTradingViewInterval{"7h", "420"},
    PythonTradingViewInterval{"8h", "480"},
    PythonTradingViewInterval{"9h", "540"},
    PythonTradingViewInterval{"10h", "600"},
    PythonTradingViewInterval{"11h", "660"},
    PythonTradingViewInterval{"12h", "720"},
    PythonTradingViewInterval{"1d", "1D"},
    PythonTradingViewInterval{"2d", "2D"},
    PythonTradingViewInterval{"3d", "3D"},
    PythonTradingViewInterval{"4d", "4D"},
    PythonTradingViewInterval{"5d", "5D"},
    PythonTradingViewInterval{"6d", "6D"},
    PythonTradingViewInterval{"1w", "1W"},
    PythonTradingViewInterval{"2w", "2W"},
    PythonTradingViewInterval{"3w", "3W"},
    PythonTradingViewInterval{"1mo", "1M"},
    PythonTradingViewInterval{"2mo", "2M"},
    PythonTradingViewInterval{"3mo", "3M"},
    PythonTradingViewInterval{"6mo", "6M"},
    PythonTradingViewInterval{"1month", "1M"},
    PythonTradingViewInterval{"2months", "2M"},
    PythonTradingViewInterval{"3months", "3M"},
    PythonTradingViewInterval{"6months", "6M"},
    PythonTradingViewInterval{"1y", "12M"},
    PythonTradingViewInterval{"2y", "24M"},
};

inline constexpr std::array<std::string_view, 10> kPythonDefaultChartSymbols = {
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
};

inline constexpr std::array<std::string_view, 1> kPythonDefaultExecutionSymbols = {
    "BTCUSDT",
};

inline constexpr std::array<std::string_view, 1> kPythonDefaultExecutionIntervals = {
    "1m",
};

inline constexpr std::array<std::string_view, 1> kPythonDefaultBacktestSymbols = {
    "BTCUSDT",
};

inline constexpr std::array<std::string_view, 1> kPythonDefaultBacktestIntervals = {
    "1h",
};

inline constexpr std::array<std::string_view, 2> kPythonChartMarketOptions = {
    "Futures",
    "Spot",
};

inline constexpr std::array<std::string_view, 2> kPythonAccountModeOptions = {
    "Classic Trading",
    "Portfolio Margin",
};

struct PythonUiOption {
    std::string_view key;
    std::string_view label;
    bool disabled;
};

inline constexpr std::array<PythonUiOption, 10> kPythonDashboardLoopChoices = {
    PythonUiOption{"30s", "30 seconds", false},
    PythonUiOption{"45s", "45 seconds", false},
    PythonUiOption{"1m", "1 minute", false},
    PythonUiOption{"2m", "2 minutes", false},
    PythonUiOption{"3m", "3 minutes", false},
    PythonUiOption{"5m", "5 minutes", false},
    PythonUiOption{"10m", "10 minutes", false},
    PythonUiOption{"30m", "30 minutes", false},
    PythonUiOption{"1h", "1 hour", false},
    PythonUiOption{"2h", "2 hours", false},
};

inline constexpr std::array<PythonUiOption, 4> kPythonLeadTraderOptions = {
    PythonUiOption{"futures_public", "Futures Public Lead Trader", false},
    PythonUiOption{"futures_private", "Futures Private Lead Trader", false},
    PythonUiOption{"spot_public", "Spot Public Lead Trader", false},
    PythonUiOption{"spot_private", "Spot Private Lead Trader", false},
};

inline constexpr std::array<PythonUiOption, 4> kPythonLlmUseForOptions = {
    PythonUiOption{"advisory", "Advisory", false},
    PythonUiOption{"signal_confirmation", "Signal confirmation", false},
    PythonUiOption{"risk_review", "Risk review", false},
    PythonUiOption{"backtest_explanation", "Backtest explanation", false},
};

inline constexpr std::array<PythonUiOption, 4> kPythonDashboardStrategyTemplates = {
    PythonUiOption{"", "No Template", false},
    PythonUiOption{"top10", "Top 10 %2 per trade 1x Isolated", false},
    PythonUiOption{"top50", "Top 50 %2 per trade 1x", false},
    PythonUiOption{"top100", "Top 100 %1 per trade 1x", false},
};

inline constexpr std::array<PythonUiOption, 3> kPythonBacktestTemplates = {
    PythonUiOption{"volume_top50", "First 50 Highest Volume", false},
    PythonUiOption{"volume_last_week", "Last 1 week \u00b7 2% per trade \u00b7 50 highest volume", false},
    PythonUiOption{"top100_isolated_1pct_sl", "Top 100, %2 per trade, isolated, %20 per trade SL", false},
};

inline constexpr std::array<PythonUiOption, 3> kPythonSideOptions = {
    PythonUiOption{"BUY", "Buy (Long)", false},
    PythonUiOption{"SELL", "Sell (Short)", false},
    PythonUiOption{"BOTH", "Both (Long/Short)", false},
};

inline constexpr std::array<PythonUiOption, 3> kPythonConfigModeOptions = {
    PythonUiOption{"Live", "Live", false},
    PythonUiOption{"Demo", "Demo", false},
    PythonUiOption{"Testnet", "Testnet", false},
};

inline constexpr std::array<PythonUiOption, 6> kPythonThemeOptions = {
    PythonUiOption{"Light", "Light", false},
    PythonUiOption{"Dark", "Dark", false},
    PythonUiOption{"Blue", "Blue", false},
    PythonUiOption{"Yellow", "Yellow", false},
    PythonUiOption{"Green", "Green", false},
    PythonUiOption{"Red", "Red", false},
};

inline constexpr std::array<PythonUiOption, 2> kPythonDesignOptions = {
    PythonUiOption{"Classic", "Classic", false},
    PythonUiOption{"Workstation", "Workstation", false},
};

inline constexpr std::array<PythonUiOption, 12> kPythonIndicatorSourceOptions = {
    PythonUiOption{"Binance spot", "Binance spot", false},
    PythonUiOption{"Binance futures", "Binance futures", false},
    PythonUiOption{"TradingView", "TradingView", false},
    PythonUiOption{"Bybit", "Bybit", false},
    PythonUiOption{"Coinbase", "Coinbase", false},
    PythonUiOption{"OKX", "OKX", false},
    PythonUiOption{"Gate", "Gate", false},
    PythonUiOption{"Bitget", "Bitget", false},
    PythonUiOption{"Mexc", "Mexc", false},
    PythonUiOption{"Kucoin", "Kucoin", false},
    PythonUiOption{"HTX", "HTX", false},
    PythonUiOption{"Kraken", "Kraken", false},
};

inline constexpr std::array<PythonUiOption, 7> kPythonExchangeOptions = {
    PythonUiOption{"Binance", "Binance", false},
    PythonUiOption{"Bybit", "Bybit (coming soon)", true},
    PythonUiOption{"OKX", "OKX (coming soon)", true},
    PythonUiOption{"Gate", "Gate (coming soon)", true},
    PythonUiOption{"Bitget", "Bitget (coming soon)", true},
    PythonUiOption{"MEXC", "MEXC (coming soon)", true},
    PythonUiOption{"KuCoin", "KuCoin (coming soon)", true},
};

inline constexpr std::array<PythonUiOption, 2> kPythonAccountTypeOptions = {
    PythonUiOption{"Spot", "Spot", false},
    PythonUiOption{"Futures", "Futures", false},
};

inline constexpr std::array<PythonUiOption, 2> kPythonMarginModeOptions = {
    PythonUiOption{"Isolated", "Isolated", false},
    PythonUiOption{"Cross", "Cross", false},
};

inline constexpr std::array<PythonUiOption, 2> kPythonPositionModeOptions = {
    PythonUiOption{"Hedge", "Hedge", false},
    PythonUiOption{"One-way", "One-way", false},
};

inline constexpr std::array<PythonUiOption, 2> kPythonAssetsModeOptions = {
    PythonUiOption{"Single-Asset", "Single-Asset Mode", false},
    PythonUiOption{"Multi-Assets", "Multi-Assets Mode", false},
};

inline constexpr std::array<PythonUiOption, 2> kPythonOrderTypeOptions = {
    PythonUiOption{"MARKET", "MARKET", false},
    PythonUiOption{"LIMIT", "LIMIT", false},
};

inline constexpr std::array<PythonUiOption, 4> kPythonTimeInForceOptions = {
    PythonUiOption{"GTC", "GTC", false},
    PythonUiOption{"IOC", "IOC", false},
    PythonUiOption{"FOK", "FOK", false},
    PythonUiOption{"GTD", "GTD", false},
};

inline constexpr std::array<PythonUiOption, 3> kPythonSignalLogicOptions = {
    PythonUiOption{"AND", "AND", false},
    PythonUiOption{"OR", "OR", false},
    PythonUiOption{"SEPARATE", "SEPARATE", false},
};

inline constexpr std::array<PythonUiOption, 3> kPythonMddLogicOptions = {
    PythonUiOption{"per_trade", "Per Trade MDD", false},
    PythonUiOption{"cumulative", "Cumulative MDD", false},
    PythonUiOption{"entire_account", "Entire Account MDD", false},
};

inline constexpr std::array<PythonUiOption, 3> kPythonStopLossModes = {
    PythonUiOption{"usdt", "USDT Based Stop Loss", false},
    PythonUiOption{"percent", "Percentage Based Stop Loss", false},
    PythonUiOption{"both", "Both Stop Loss (USDT & Percentage)", false},
};

inline constexpr std::array<PythonUiOption, 3> kPythonStopLossScopes = {
    PythonUiOption{"per_trade", "Per Trade Stop Loss", false},
    PythonUiOption{"cumulative", "Cumulative Stop Loss", false},
    PythonUiOption{"entire_account", "Entire Account Stop Loss", false},
};

inline constexpr std::array<PythonUiOption, 3> kPythonScanScopeOptions = {
    PythonUiOption{"selected", "selected", false},
    PythonUiOption{"top_n", "top_n", false},
    PythonUiOption{"all_loaded", "all_loaded", false},
};

inline constexpr std::array<PythonUiOption, 4> kPythonOptimizerModeOptions = {
    PythonUiOption{"current", "current", false},
    PythonUiOption{"single", "single", false},
    PythonUiOption{"pairs", "pairs", false},
    PythonUiOption{"combinations", "combinations", false},
};

inline constexpr std::array<PythonUiOption, 4> kPythonOptimizerMetricOptions = {
    PythonUiOption{"roi_percent", "roi_percent", false},
    PythonUiOption{"roi_percent_mdd", "roi_percent_mdd", false},
    PythonUiOption{"roi_drawdown", "roi_drawdown", false},
    PythonUiOption{"roi_value", "roi_value", false},
};

inline constexpr std::array<PythonUiOption, 2> kPythonBacktestExecutionBackendOptions = {
    PythonUiOption{"local", "local", false},
    PythonUiOption{"service", "service", false},
};

inline constexpr std::array<PythonUiOption, 3> kPythonChartViewOptions = {
    PythonUiOption{"tradingview", "TradingView", false},
    PythonUiOption{"original", "Original", false},
    PythonUiOption{"lightweight", "TradingView Lightweight", false},
};

inline constexpr std::array<PythonUiOption, 2> kPythonPositionsViewOptions = {
    PythonUiOption{"cumulative", "Cumulative View", false},
    PythonUiOption{"per_trade", "Per Trade View", false},
};

} // namespace PythonParityContract
