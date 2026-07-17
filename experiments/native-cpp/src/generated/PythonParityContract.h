// This file is generated from Languages/Python/app/native_parity.py.
// Do not edit manually; run Languages/Python/tools/generate_native_parity_contracts.py.
#pragma once

#include <array>
#include <string_view>

namespace PythonParityContract {

inline constexpr std::string_view kPythonSource = "Languages/Python";
inline constexpr unsigned kPythonSourceSchemaVersion = 1;
inline constexpr std::string_view kPythonSourceContractHash = "a9e15f87add34bf94b77675f06ed7a879eeb0768a5287c0e0c00a3625d390c83";
inline constexpr bool kCppContractParityReady = true;
inline constexpr bool kRustContractParityReady = true;
inline constexpr bool kCppStandaloneRuntimeReady = false;
inline constexpr bool kRustStandaloneRuntimeReady = false;
inline constexpr bool kCppFullParityReady = false;
inline constexpr bool kRustFullParityReady = false;
inline constexpr std::string_view kPythonOrderGuardBehaviorJson = "{\"live_only_requirements\":[\"credentials\",\"live_acknowledgement\",\"session_order_cap\",\"session_order_count_increment\"],\"validate_audit_enabled_all_modes\":true,\"validate_audit_writable_all_modes\":true,\"validate_connector_health_all_modes\":true,\"validate_exchange_filters_all_modes\":true,\"validate_intent_all_modes\":true}";
inline constexpr bool kPythonOrderGuardValidateIntentAllModes = true;
inline constexpr bool kPythonOrderGuardValidateExchangeFiltersAllModes = true;
inline constexpr bool kPythonOrderGuardValidateConnectorHealthAllModes = true;
inline constexpr bool kPythonOrderGuardValidateAuditEnabledAllModes = true;
inline constexpr bool kPythonOrderGuardValidateAuditWritableAllModes = true;
inline constexpr std::array<std::string_view, 4> kPythonOrderGuardLiveOnlyRequirements = {
    "credentials",
    "live_acknowledgement",
    "session_order_cap",
    "session_order_count_increment",
};

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
    PythonParityDomain{"desktop_shell_and_tabs", "Desktop shell and primary tabs", "Dashboard, Chart, Positions, Backtest, Liquidation Heatmap, Code Languages, startup composition, theme, and live tab wiring.", "Complete", "Complete", "C++: Complete | Rust: Complete", true, true},
    PythonParityDomain{"service_api_contract", "Service API contract", "Canonical /api/v1 routes, methods, schemas, dashboard stream, auth, control-plane state, and desktop bridge contract.", "Complete", "Complete", "C++: Complete | Rust: Complete", true, true},
    PythonParityDomain{"config_persistence", "Config persistence and hydration", "Runtime config, file save/load, dirty state, dashboard hydration, service snapshots, and secret redaction.", "Complete", "Complete", "C++: Complete | Rust: Complete", true, true},
    PythonParityDomain{"strategy_runtime", "Strategy runtime and signal generation", "Indicator computation, strategy cycles, signal generation, live candle options, override tables, and worker lifecycle.", "Complete", "Complete", "C++: Complete | Rust: Complete", true, true},
    PythonParityDomain{"exchange_connectors", "Exchange connectors and market data", "Binance SDK/connector/CCXT/python-binance selection, connector support metadata, transport diagnostics, rate limits, REST market data, and WebSocket paths.", "Complete", "Complete", "C++: Complete | Rust: Complete", true, true},
    PythonParityDomain{"account_portfolio_positions", "Account, portfolio, and positions", "Account snapshots, portfolio summaries, futures position queries, close-all behavior, position history, allocation tracking, and reconciliation.", "Complete", "Complete", "C++: Complete | Rust: Complete", true, true},
    PythonParityDomain{"order_execution_and_risk", "Order execution, audit, and risk", "Order sizing, submit guards, audit logs, position gates, close-opposite logic, stop-loss scopes, live safety preflight, circuit breaker, and shutdown guards.", "Complete", "Complete", "C++: Complete | Rust: Complete", true, true},
    PythonParityDomain{"backtest_engine", "Backtest engine, optimizer, and scanner", "Backtest engine, optimizer limits/results, live parity request shape, scanner polling, dashboard import, indicator selection, and provenance.", "Complete", "Complete", "C++: Complete | Rust: Complete", true, true},
    PythonParityDomain{"charts_and_heatmaps", "Charts and liquidation heatmaps", "TradingView, lightweight chart assets, candlestick fallback, chart state payloads, browser guards, and liquidation provider panels.", "Complete", "Complete", "C++: Complete | Rust: Complete", true, true},
    PythonParityDomain{"logs_terminal_diagnostics", "Logs, terminal, and diagnostics", "Service logs, dashboard logs, terminal command execution, exception diagnostics, secret redaction, and test runner/reporting flows.", "Complete", "Complete", "C++: Complete | Rust: Complete", true, true},
    PythonParityDomain{"llm_advisory", "LLM advisory and local model lifecycle", "Provider catalogs, privacy flags, advisory prompt execution, config persistence, local Ollama status/start/pull/delete, and redacted output.", "Complete", "Complete", "C++: Complete | Rust: Complete", true, true},
    PythonParityDomain{"startup_packaging_platform", "Startup, packaging, and platform integration", "Product entrypoints, startup splash/suppression, Windows taskbar metadata, PyInstaller packaging, service wrappers, and release smoke tests.", "Complete", "Complete", "C++: Complete | Rust: Complete", true, true},
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

inline constexpr std::array<std::string_view, 34> kPythonServiceRouteNames = {
    "runtime",
    "dashboard",
    "status",
    "metrics",
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

inline constexpr std::array<PythonServiceRoute, 34> kPythonServiceRoutes = {
    PythonServiceRoute{"runtime", "/api/v1/runtime", "GET"},
    PythonServiceRoute{"dashboard", "/api/v1/dashboard", "GET"},
    PythonServiceRoute{"status", "/api/v1/status", "GET"},
    PythonServiceRoute{"metrics", "/api/v1/metrics", "GET"},
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

struct PythonServiceRouteSchema {
    std::string_view name;
    std::string_view queryFields;
    std::string_view requestFields;
    std::string_view responseFields;
};

inline constexpr std::array<PythonServiceRouteSchema, 34> kPythonServiceRouteSchemas = {
    PythonServiceRouteSchema{"runtime", "", "", "service_name,phase,python_entrypoint,desktop_entrypoint,repo_root,platform,python_version,capabilities,control_plane,notes"},
    PythonServiceRouteSchema{"dashboard", "log_limit,incident_limit", "", "runtime,status,operational,config,config_summary,execution,backtest,account,portfolio,logs,service_api,connector_order_circuit_incidents"},
    PythonServiceRouteSchema{"status", "", "", "state,lifecycle_phase,requested_action,close_positions_requested,status_message,last_transition_at,service_mode,generated_at,api_enabled,docker_required,runtime_source,active_engine_count,account_type,mode,selected_exchange,connector_backend,connector_health,exchange_connector,operational_health,operational,notes"},
    PythonServiceRouteSchema{"metrics", "", "", "generated_at,operational_health,connector_health,connector_state,runtime_active,active_engine_count,log_warning_count,log_error_count,connector_order_circuit_open,unresolved_order_intent_count"},
    PythonServiceRouteSchema{"execution", "", "", "executor_kind,owner,state,workload_kind,session_id,requested_job_count,active_engine_count,progress_label,progress_percent,heartbeat_at,tick_count,last_action,last_message,started_at,updated_at,source,notes"},
    PythonServiceRouteSchema{"backtest", "", "", "session_id,state,workload_kind,status_message,symbols,intervals,indicator_keys,logic,symbol_source,capital,run_count,error_count,cancelled,started_at,completed_at,updated_at,source,top_run,runs,top_runs,errors"},
    PythonServiceRouteSchema{"config_summary", "", "", "mode,account_type,connector_backend,selected_exchange,code_language,theme,design,api_credentials_present,symbol_count,interval_count,enabled_indicator_count,runtime_pair_count,backtest_pair_count,llm_enabled,llm_provider,llm_mode,llm_api_key_present"},
    PythonServiceRouteSchema{"config", "", "config", "mode,account_type,margin_mode,position_mode,side,leverage,position_pct,connector_backend,selected_exchange,code_language,theme,design,order_audit_max_bytes,order_audit_backup_count,connector_order_circuit_incident_log_max_bytes,connector_order_circuit_incident_log_backup_count,operational_connector_snapshot_stale_seconds,operational_execution_heartbeat_stale_seconds,operational_account_snapshot_stale_seconds,operational_portfolio_snapshot_stale_seconds,operational_live_start_gate_enabled,operational_live_order_gate_enabled,live_allow_auto_bump_to_min_order,symbols,intervals,api_credentials_present,llm,exchange_support"},
    PythonServiceRouteSchema{"config_persistence", "", "", "path,exists,modified_at,kind,format_version,loaded,dirty,last_loaded_at,last_saved_at,migrated_from_format_version"},
    PythonServiceRouteSchema{"config_save", "", "path,source,allow_unsafe_path", "path,exists,modified_at,kind,format_version,loaded,dirty,last_loaded_at,last_saved_at,migrated_from_format_version"},
    PythonServiceRouteSchema{"config_load", "", "path,source,allow_unsafe_path", "config,persistence"},
    PythonServiceRouteSchema{"runtime_state", "", "active,active_engine_count,source", "state,lifecycle_phase,requested_action,close_positions_requested,status_message,last_transition_at,service_mode,generated_at,api_enabled,docker_required,runtime_source,active_engine_count,account_type,mode,selected_exchange,connector_backend,connector_health,exchange_connector,operational_health,operational,notes"},
    PythonServiceRouteSchema{"operational_preflight", "", "", "state,message,mode,live_mode,generated_at,start,orders,freshness,critical_stale,reasons"},
    PythonServiceRouteSchema{"control_start", "", "requested_job_count,source", "accepted,action,lifecycle_phase,runtime_active,active_engine_count,requested_job_count,close_positions_requested,source,status_message,generated_at"},
    PythonServiceRouteSchema{"control_stop", "", "close_positions,source", "accepted,action,lifecycle_phase,runtime_active,active_engine_count,requested_job_count,close_positions_requested,source,status_message,generated_at"},
    PythonServiceRouteSchema{"control_start_failed", "", "reason,source", "accepted,action,lifecycle_phase,runtime_active,active_engine_count,requested_job_count,close_positions_requested,source,status_message,generated_at"},
    PythonServiceRouteSchema{"connector_order_circuit_breaker", "", "snapshot,source,force", "active,state,reason,message,block_count,block_threshold,block_window_seconds,source,generated_at"},
    PythonServiceRouteSchema{"connector_order_circuit_breaker_reset", "", "snapshot,source,force", "active,state,source,generated_at"},
    PythonServiceRouteSchema{"connector_order_circuit_incidents", "limit", "", "path,path_source,configured_path,limit,events,parse_errors"},
    PythonServiceRouteSchema{"backtest_run", "", "request,source", "accepted,action,session_id,state,status_message,source"},
    PythonServiceRouteSchema{"backtest_stop", "", "source", "accepted,action,session_id,state,status_message,source"},
    PythonServiceRouteSchema{"account", "", "total_balance,available_balance,source", "account_type,mode,selected_exchange,connector_backend,balance_currency,total_balance,available_balance,source,generated_at"},
    PythonServiceRouteSchema{"portfolio", "", "open_position_records,closed_position_records,closed_trade_registry,active_pnl,active_margin,closed_pnl,closed_margin,total_balance,available_balance,source", "account_type,open_position_count,closed_position_count,active_pnl,active_margin,closed_pnl,closed_margin,total_balance,available_balance,positions,source,generated_at"},
    PythonServiceRouteSchema{"exchange_connector", "", "snapshot,source", "health,state,generated_at,source,selected_exchange,connector_backend,support,rate_limit,network,last_error,attention"},
    PythonServiceRouteSchema{"logs", "limit", "message,source,level", "sequence_id,level,message,source,generated_at"},
    PythonServiceRouteSchema{"terminal_run", "", "command,source", "command,exit_code,output,source,generated_at"},
    PythonServiceRouteSchema{"llm_providers", "", "", "key,label,mode,protocol,default_base_url,default_model,api_key_env,model_suggestions,reasoning_efforts,default_reasoning_effort"},
    PythonServiceRouteSchema{"llm_config", "", "config", "enabled,provider,provider_label,mode,protocol,model,base_url,api_key_env,api_key_present,allow_public_network,use_for,reasoning_effort"},
    PythonServiceRouteSchema{"llm_prompt", "", "prompt,system_prompt,dry_run,source", "provider,model,dry_run,prompt,system_prompt,response,source"},
    PythonServiceRouteSchema{"llm_local_model_status", "base_url,model", "", "model,base_url,server_kind,installed,can_download,can_start,storage_hint,storage_paths,estimated_size_label"},
    PythonServiceRouteSchema{"llm_local_model_start", "", "base_url,model,source", "started,server_kind,executable,error"},
    PythonServiceRouteSchema{"llm_local_model_pull", "", "base_url,model,source", "ok,action,model,status"},
    PythonServiceRouteSchema{"llm_local_model_delete", "", "base_url,model,source", "ok,action,model,status"},
    PythonServiceRouteSchema{"stream_dashboard", "log_limit,incident_limit,interval_ms,max_events", "", "event,data"},
};

inline constexpr std::array<std::string_view, 34> kPythonBacktestRunRequestFields = {
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
    "optimizer_max_duration_seconds",
    "optimizer_metric",
    "optimizer_min_trades",
    "optimizer_mode",
    "pair_overrides",
    "position_mode",
    "position_pct",
    "position_pct_units",
    "queue_if_busy",
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
    std::string_view runtimeConfigJson;
    std::string_view backtestConfigJson;
    std::string_view runtimeOutputKeysCsv;
};

inline constexpr std::array<PythonIndicator, 33> kPythonIndicatorCatalog = {
    PythonIndicator{"ma", "Moving Average (MA)", false, "{\"buy_value\":null,\"enabled\":false,\"length\":20,\"sell_value\":null,\"type\":\"SMA\"}", "{\"buy_value\":0,\"enabled\":false,\"length\":20,\"sell_value\":0,\"signal_mode\":\"price_cross\",\"type\":\"SMA\"}", "ma"},
    PythonIndicator{"donchian", "Donchian Channels (DC)", false, "{\"buy_value\":null,\"enabled\":false,\"length\":20,\"sell_value\":null}", "{\"buy_value\":0,\"enabled\":false,\"length\":20,\"sell_value\":100,\"signal_mode\":\"band_position\"}", "donchian_high,donchian_low,donchian"},
    PythonIndicator{"psar", "Parabolic SAR (PSAR)", false, "{\"af\":0.02,\"buy_value\":null,\"enabled\":false,\"max_af\":0.2,\"sell_value\":null}", "{\"af\":0.02,\"buy_value\":0,\"enabled\":false,\"max_af\":0.2,\"sell_value\":0,\"signal_mode\":\"price_cross\"}", "psar"},
    PythonIndicator{"bb", "Bollinger Bands (BB)", false, "{\"buy_value\":null,\"enabled\":false,\"length\":20,\"sell_value\":null,\"std\":2}", "{\"buy_value\":0,\"enabled\":false,\"length\":20,\"sell_value\":100,\"signal_mode\":\"band_position\",\"std\":2}", "bb_upper,bb_mid,bb_lower"},
    PythonIndicator{"bbw", "Bollinger Band Width (BBW)", false, "{\"buy_value\":null,\"enabled\":false,\"length\":20,\"sell_value\":null,\"std\":2}", "{\"buy_value\":5.0,\"enabled\":false,\"length\":20,\"sell_value\":2.0,\"std\":2}", "bbw"},
    PythonIndicator{"keltner", "Keltner Channels (KC)", false, "{\"atr_length\":10,\"buy_value\":null,\"enabled\":false,\"length\":20,\"multiplier\":2.0,\"sell_value\":null}", "{\"atr_length\":10,\"buy_value\":0,\"enabled\":false,\"length\":20,\"multiplier\":2.0,\"sell_value\":100,\"signal_mode\":\"band_position\"}", "keltner_upper,keltner_mid,keltner_lower"},
    PythonIndicator{"ichimoku", "Ichimoku Cloud (IC)", false, "{\"base_length\":26,\"buy_value\":null,\"conversion_length\":9,\"displacement\":26,\"enabled\":false,\"sell_value\":null,\"span_b_length\":52}", "{\"base_length\":26,\"buy_value\":0,\"conversion_length\":9,\"displacement\":26,\"enabled\":false,\"sell_value\":0,\"span_b_length\":52}", "ichimoku_tenkan,ichimoku_kijun,ichimoku_span_a,ichimoku_span_b,ichimoku_chikou,ichimoku"},
    PythonIndicator{"rsi", "Relative Strength Index (RSI)", true, "{\"buy_value\":null,\"enabled\":true,\"length\":14,\"sell_value\":null}", "{\"buy_value\":30,\"enabled\":true,\"length\":14,\"sell_value\":70}", "rsi"},
    PythonIndicator{"volume", "Volume", false, "{\"buy_value\":null,\"enabled\":false,\"sell_value\":null}", "{\"buy_value\":1.0,\"enabled\":false,\"filter_operator\":\"gte\",\"length\":20,\"sell_value\":null,\"signal_mode\":\"relative_to_sma\",\"signal_role\":\"filter\"}", "volume"},
    PythonIndicator{"obv", "On-Balance Volume (OBV)", false, "{\"buy_value\":null,\"enabled\":false,\"sell_value\":null}", "{\"buy_value\":0,\"enabled\":false,\"length\":3,\"sell_value\":0,\"signal_mode\":\"slope\"}", "obv"},
    PythonIndicator{"rvol", "Relative Volume (RVOL)", false, "{\"buy_value\":null,\"enabled\":false,\"length\":20,\"sell_value\":null}", "{\"buy_value\":1.5,\"enabled\":false,\"length\":20,\"sell_value\":0.75}", "rvol"},
    PythonIndicator{"cmf", "Chaikin Money Flow (CMF)", false, "{\"buy_value\":null,\"enabled\":false,\"length\":20,\"sell_value\":null}", "{\"buy_value\":0.05,\"enabled\":false,\"length\":20,\"sell_value\":-0.05}", "cmf"},
    PythonIndicator{"cci", "Commodity Channel Index (CCI)", false, "{\"buy_value\":null,\"constant\":0.015,\"enabled\":false,\"length\":20,\"sell_value\":null}", "{\"buy_value\":-100,\"constant\":0.015,\"enabled\":false,\"length\":20,\"sell_value\":100}", "cci"},
    PythonIndicator{"roc", "Rate of Change (ROC)", false, "{\"buy_value\":null,\"enabled\":false,\"length\":12,\"sell_value\":null}", "{\"buy_value\":0,\"enabled\":false,\"length\":12,\"sell_value\":0}", "roc"},
    PythonIndicator{"trix", "Triple Exponential Average (TRIX)", false, "{\"buy_value\":null,\"enabled\":false,\"length\":15,\"sell_value\":null}", "{\"buy_value\":0,\"enabled\":false,\"length\":15,\"sell_value\":0}", "trix"},
    PythonIndicator{"ppo", "Percentage Price Oscillator (PPO)", false, "{\"buy_value\":null,\"enabled\":false,\"fast\":12,\"sell_value\":null,\"signal\":9,\"slow\":26}", "{\"buy_value\":0,\"enabled\":false,\"fast\":12,\"sell_value\":0,\"signal\":9,\"slow\":26}", "ppo,ppo_signal,ppo_hist"},
    PythonIndicator{"ao", "Awesome Oscillator (AO)", false, "{\"buy_value\":null,\"enabled\":false,\"fast\":5,\"sell_value\":null,\"slow\":34}", "{\"buy_value\":0,\"enabled\":false,\"fast\":5,\"sell_value\":0,\"slow\":34}", "ao"},
    PythonIndicator{"kst", "Know Sure Thing (KST)", false, "{\"buy_value\":null,\"enabled\":false,\"roc1\":10,\"roc2\":15,\"roc3\":20,\"roc4\":30,\"sell_value\":null,\"signal\":9,\"sma1\":10,\"sma2\":10,\"sma3\":10,\"sma4\":15}", "{\"buy_value\":0,\"enabled\":false,\"roc1\":10,\"roc2\":15,\"roc3\":20,\"roc4\":30,\"sell_value\":0,\"signal\":9,\"sma1\":10,\"sma2\":10,\"sma3\":10,\"sma4\":15}", "kst,kst_signal,kst_hist"},
    PythonIndicator{"aroon", "Aroon Oscillator (AROON)", false, "{\"buy_value\":null,\"enabled\":false,\"length\":25,\"sell_value\":null}", "{\"buy_value\":50,\"enabled\":false,\"length\":25,\"sell_value\":-50}", "aroon_up,aroon_down,aroon"},
    PythonIndicator{"chop", "Choppiness Index (CHOP)", false, "{\"buy_value\":null,\"enabled\":false,\"length\":14,\"sell_value\":null}", "{\"buy_value\":38.2,\"enabled\":false,\"length\":14,\"sell_value\":61.8}", "chop"},
    PythonIndicator{"atr", "Average True Range (ATR)", false, "{\"buy_value\":null,\"enabled\":false,\"length\":14,\"sell_value\":null}", "{\"buy_value\":1.0,\"enabled\":false,\"filter_operator\":\"gte\",\"length\":14,\"sell_value\":null,\"signal_mode\":\"percent_of_close\",\"signal_role\":\"filter\"}", "atr"},
    PythonIndicator{"natr", "Normalized Average True Range (NATR)", false, "{\"buy_value\":null,\"enabled\":false,\"length\":14,\"sell_value\":null}", "{\"buy_value\":2.0,\"enabled\":false,\"length\":14,\"sell_value\":1.0}", "natr"},
    PythonIndicator{"vwap", "Volume Weighted Average Price (VWAP)", false, "{\"buy_value\":null,\"enabled\":false,\"length\":20,\"sell_value\":null}", "{\"buy_value\":0,\"enabled\":false,\"length\":20,\"sell_value\":0,\"signal_mode\":\"price_cross\"}", "vwap"},
    PythonIndicator{"mfi", "Money Flow Index (MFI)", false, "{\"buy_value\":null,\"enabled\":false,\"length\":14,\"sell_value\":null}", "{\"buy_value\":20,\"enabled\":false,\"length\":14,\"sell_value\":80}", "mfi"},
    PythonIndicator{"stoch_rsi", "Stochastic RSI (SRSI)", false, "{\"buy_value\":null,\"enabled\":false,\"length\":14,\"sell_value\":null,\"smooth_d\":3,\"smooth_k\":3}", "{\"buy_value\":20,\"enabled\":false,\"length\":14,\"sell_value\":80,\"smooth_d\":3,\"smooth_k\":3}", "stoch_rsi,stoch_rsi_k,stoch_rsi_d"},
    PythonIndicator{"willr", "Williams %R", false, "{\"buy_value\":null,\"enabled\":false,\"length\":14,\"sell_value\":null}", "{\"buy_value\":-80,\"enabled\":false,\"length\":14,\"sell_value\":-20}", "willr"},
    PythonIndicator{"macd", "Moving Average Convergence/Divergence (MACD)", false, "{\"buy_value\":null,\"enabled\":false,\"fast\":12,\"sell_value\":null,\"signal\":9,\"slow\":26}", "{\"buy_value\":0,\"enabled\":false,\"fast\":12,\"sell_value\":0,\"signal\":9,\"slow\":26}", "macd_line,macd_signal"},
    PythonIndicator{"uo", "Ultimate Oscillator (UO)", false, "{\"buy_value\":null,\"enabled\":false,\"long\":28,\"medium\":14,\"sell_value\":null,\"short\":7}", "{\"buy_value\":30,\"enabled\":false,\"long\":28,\"medium\":14,\"sell_value\":70,\"short\":7}", "uo"},
    PythonIndicator{"adx", "Average Directional Index (ADX)", false, "{\"buy_value\":null,\"enabled\":false,\"length\":14,\"sell_value\":null}", "{\"buy_value\":20,\"enabled\":false,\"filter_operator\":\"gte\",\"length\":14,\"sell_value\":null,\"signal_role\":\"filter\"}", "adx"},
    PythonIndicator{"dmi", "Directional Movement Index (DMI)", false, "{\"buy_value\":null,\"enabled\":false,\"length\":14,\"sell_value\":null}", "{\"buy_value\":0,\"enabled\":false,\"length\":14,\"sell_value\":0}", "dmi_plus,dmi_minus,dmi"},
    PythonIndicator{"supertrend", "SuperTrend (ST)", false, "{\"atr_period\":10,\"buy_value\":null,\"enabled\":false,\"multiplier\":3.0,\"sell_value\":null}", "{\"atr_period\":10,\"buy_value\":0,\"enabled\":false,\"multiplier\":3.0,\"sell_value\":0,\"signal_mode\":\"price_cross\"}", "supertrend"},
    PythonIndicator{"ema", "Exponential Moving Average (EMA)", false, "{\"buy_value\":null,\"enabled\":false,\"length\":20,\"sell_value\":null}", "{\"buy_value\":0,\"enabled\":false,\"length\":20,\"sell_value\":0,\"signal_mode\":\"price_cross\"}", "ema"},
    PythonIndicator{"stochastic", "Stochastic Oscillator", false, "{\"buy_value\":null,\"enabled\":false,\"length\":14,\"sell_value\":null,\"smooth_d\":3,\"smooth_k\":3}", "{\"buy_value\":20,\"enabled\":false,\"length\":14,\"sell_value\":80,\"smooth_d\":3,\"smooth_k\":3}", "stochastic,stochastic_k,stochastic_d"},
};

inline constexpr std::array<std::string_view, 15> kPythonLlmProviderKeys = {
    "openai",
    "anthropic",
    "gemini",
    "deepseek",
    "mistral",
    "grok",
    "qwen",
    "moonshot",
    "local",
    "ollama",
    "vllm",
    "llamacpp",
    "lmstudio",
    "tgi",
    "open-source",
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

inline constexpr std::array<PythonLlmProvider, 15> kPythonLlmProviders = {
    PythonLlmProvider{"openai", "OpenAI / ChatGPT", "cloud", "openai-chat-completions", "https://api.openai.com/v1", "gpt-5.5", "OPENAI_API_KEY", "gpt-5.6,gpt-5.6-sol,gpt-5.6-terra,gpt-5.6-luna,gpt-5.5,gpt-5.5-2026-04-23,gpt-5.5-pro,gpt-5.5-pro-2026-04-23,gpt-5.4,gpt-5.4-2026-03-05,gpt-5.4-pro,gpt-5.4-pro-2026-03-05,gpt-5.4-mini,gpt-5.4-mini-2026-03-17,gpt-5.4-nano,gpt-5.4-nano-2026-03-17,gpt-5.3-chat-latest,gpt-5.3-codex,gpt-5.2,gpt-5.2-codex,gpt-5.2-chat-latest,gpt-5.2-pro,gpt-5.1,gpt-5-codex,gpt-5-mini,gpt-5-nano,gpt-4.1,gpt-4.1-mini,gpt-4.1-nano", "default,none,minimal,low,medium,high,xhigh,max", "default"},
    PythonLlmProvider{"anthropic", "Anthropic Claude", "cloud", "anthropic-messages", "https://api.anthropic.com", "claude-sonnet-4-5-20250929", "ANTHROPIC_API_KEY", "claude-sonnet-4-5-20250929,claude-haiku-4-5-20251001,claude-opus-4-5-20251101,claude-opus-4-1-20250805,claude-opus-4-20250514,claude-sonnet-4-20250514,claude-sonnet-4-5,claude-haiku-4-5,claude-opus-4-5,claude-opus-4-1,claude-opus-4-0,claude-sonnet-4-0", "default,disabled,enabled,low,medium,high", "default"},
    PythonLlmProvider{"gemini", "Google Gemini", "cloud", "gemini-generate-content", "https://generativelanguage.googleapis.com/v1beta", "gemini-3-flash-preview", "GEMINI_API_KEY", "gemini-3.1-pro-preview,gemini-3.1-pro-preview-customtools,gemini-3-flash-preview,gemini-3.1-flash-lite-preview,gemini-2.5-pro,gemini-2.5-flash,gemini-2.5-flash-preview-09-2025,gemini-2.5-flash-lite,gemini-2.5-flash-lite-preview-09-2025", "default,minimal,low,medium,high", "default"},
    PythonLlmProvider{"deepseek", "DeepSeek", "cloud", "openai-chat-completions", "https://api.deepseek.com", "deepseek-v4-flash", "DEEPSEEK_API_KEY", "deepseek-v4-flash,deepseek-v4-pro,deepseek-chat,deepseek-reasoner", "default,disabled,enabled,high,max", "default"},
    PythonLlmProvider{"mistral", "Mistral AI", "cloud", "openai-chat-completions", "https://api.mistral.ai/v1", "mistral-small-latest", "MISTRAL_API_KEY", "mistral-large-latest,mistral-medium-latest,mistral-small-latest,codestral-latest,open-mistral-nemo", "default,low,medium,high", "default"},
    PythonLlmProvider{"grok", "xAI Grok", "cloud", "openai-chat-completions", "https://api.x.ai/v1", "grok-4.3", "XAI_API_KEY", "grok-4.3,grok-4.3-latest,grok-4.20,grok-4.20-reasoning,grok-4.20-non-reasoning,grok-4-fast-reasoning,grok-4-fast-non-reasoning", "default,low,medium,high", "default"},
    PythonLlmProvider{"qwen", "Alibaba Qwen / DashScope", "cloud", "openai-chat-completions", "https://dashscope-intl.aliyuncs.com/compatible-mode/v1", "qwen3.6-plus", "DASHSCOPE_API_KEY", "qwen3.7-max,qwen3.7-max-2026-06-08,qwen3.7-max-2026-05-20,qwen3.6-max-preview,qwen3.6-plus,qwen3.6-plus-2026-04-02,qwen3.6-flash,qwen3.6-flash-2026-04-16,qwen3-max,qwen3-max-2026-01-23,qwen3-max-2025-09-23,qwen3-max-preview,qwen3.5-plus,qwen3.5-plus-2026-02-15,qwen3.5-flash,qwen3.5-flash-2026-02-23,qwen3-coder-plus,qwen3-coder-flash,qwen-plus-us,qwen-flash-us", "default,disabled,enabled,low,medium,high,max", "default"},
    PythonLlmProvider{"moonshot", "Moonshot AI / Kimi", "cloud", "openai-chat-completions", "https://api.moonshot.ai/v1", "kimi-k3", "MOONSHOT_API_KEY", "kimi-k3,kimi-k2.7-code,kimi-k2.7-code-highspeed,kimi-k2.6,kimi-k2.5", "default,disabled,enabled,max", "default"},
    PythonLlmProvider{"local", "Local / Custom OpenAI-Compatible", "local", "openai-chat-completions", "http://127.0.0.1:11434/v1", "qwen3:8b", "LOCAL_LLM_API_KEY", "qwen3:0.6b,qwen3:1.7b,qwen3:4b,qwen3:8b,qwen3:14b,qwen3:30b-a3b,qwen3:32b,qwen3,qwen3-vl:8b,qwen3-vl:32b,qwen3.5,qwen2.5:0.5b,qwen2.5:1.5b,qwen2.5:3b,qwen2.5:7b,qwen2.5:14b,qwen2.5:32b,qwen2.5:72b,qwen2.5-coder:1.5b,qwen2.5-coder:7b,qwen2.5-coder:14b,qwen2.5-coder:32b,qwq:32b,gpt-oss:20b,gpt-oss:120b,gpt-oss:latest,llama4:maverick,llama4:scout,deepseek-v3,deepseek-v3.1,deepseek-v3.2,deepseek-r1:1.5b,deepseek-r1:7b,deepseek-r1:8b,deepseek-r1:14b,deepseek-r1:32b,deepseek-r1:70b,deepseek-coder-v2,llama3.3,llama3.1:8b,llama3.1:70b,llama3.2:1b,llama3.2:3b,llama3.2-vision:11b,llama3.2-vision:90b,mistral,mistral-nemo,mistral-small3.2,mixtral:8x7b,mixtral:8x22b,codestral,devstral,gemma3:1b,gemma3:4b,gemma3:12b,gemma3:27b,gemma4:27b,gemma2:2b,gemma2:9b,gemma2:27b,phi4,phi4-mini,phi3.5,phi3:mini,falcon3:1b,falcon3:3b,falcon3:7b,falcon3:10b,yi:6b,yi:9b,yi:34b,glm4,glm4.5,glm5,kimi-k2,minimax-m2,step3,mimo-v2,internlm2.5,baichuan2:7b,baichuan2:13b,minicpm-v,smollm2:135m,smollm2:360m,smollm2:1.7b,granite3.3:2b,granite3.3:8b,command-r,command-r-plus,starcoder2:3b,starcoder2:7b,starcoder2:15b,codellama:7b,codellama:13b,codellama:34b,dolphin-mixtral,openchat,neural-chat,orca-mini,zephyr,solar,nous-hermes2,wizardlm2,vicuna,rwkv,pythia,dolly-v2,stablelm,redpajama,openllama,mpt,dbrx,arctic,bloom,bloomz,mamba,custom-model,Qwen/Qwen3-0.6B,Qwen/Qwen3-1.7B,Qwen/Qwen3-4B,Qwen/Qwen3-8B,Qwen/Qwen3-14B,Qwen/Qwen3-32B,Qwen/Qwen3-30B-A3B,Qwen/Qwen2.5-0.5B-Instruct,Qwen/Qwen2.5-1.5B-Instruct,Qwen/Qwen2.5-3B-Instruct,Qwen/Qwen2.5-7B-Instruct,Qwen/Qwen2.5-14B-Instruct,Qwen/Qwen2.5-32B-Instruct,Qwen/Qwen2.5-72B-Instruct,Qwen/Qwen2.5-Coder-1.5B-Instruct,Qwen/Qwen2.5-Coder-7B-Instruct,Qwen/Qwen2.5-Coder-14B-Instruct,Qwen/Qwen2.5-Coder-32B-Instruct,Qwen/QwQ-32B,openai/gpt-oss-20b,openai/gpt-oss-120b,google-t5/t5-small,google-t5/t5-base,google-t5/t5-large,google/flan-t5-small,google/flan-t5-base,google/flan-t5-large,google/flan-t5-xl,google/flan-t5-xxl,RWKV/rwkv-4-world,RWKV/rwkv-5-world,RWKV/rwkv-6-world,BlinkDL/rwkv-7-world,EleutherAI/gpt-neox-20b,EleutherAI/gpt-j-6b,EleutherAI/gpt-neo-2.7B,yandex/yalm-100b,meta-llama/Llama-3.3-70B-Instruct,meta-llama/Llama-3.1-8B-Instruct,meta-llama/Llama-3.1-70B-Instruct,meta-llama/Llama-3.2-1B-Instruct,meta-llama/Llama-3.2-3B-Instruct,mistralai/Mistral-7B-Instruct-v0.3,mistralai/Mistral-Nemo-Instruct-2407,mistralai/Mixtral-8x7B-Instruct-v0.1,mistralai/Mixtral-8x22B-Instruct-v0.1,mistralai/Codestral-22B-v0.1,deepseek-ai/DeepSeek-R1,deepseek-ai/DeepSeek-R1-Distill-Qwen-1.5B,deepseek-ai/DeepSeek-R1-Distill-Qwen-7B,deepseek-ai/DeepSeek-R1-Distill-Qwen-14B,deepseek-ai/DeepSeek-R1-Distill-Qwen-32B,deepseek-ai/deepseek-coder-6.7b-instruct,deepseek-ai/DeepSeek-Coder-V2-Instruct,google/gemma-3-1b-it,google/gemma-3-4b-it,google/gemma-3-12b-it,google/gemma-3-27b-it,google/gemma-2-2b-it,google/gemma-2-9b-it,google/gemma-2-27b-it,microsoft/phi-4,microsoft/Phi-4-mini-instruct,microsoft/Phi-3.5-mini-instruct,tiiuae/Falcon3-1B-Instruct,tiiuae/Falcon3-3B-Instruct,tiiuae/Falcon3-7B-Instruct,tiiuae/Falcon3-10B-Instruct,tiiuae/falcon-180B-chat,01-ai/Yi-6B-Chat,01-ai/Yi-9B-Chat,01-ai/Yi-34B-Chat,THUDM/glm-4-9b-chat,internlm/internlm2_5-7b-chat,internlm/internlm2_5-20b-chat,baichuan-inc/Baichuan2-7B-Chat,baichuan-inc/Baichuan2-13B-Chat,openbmb/MiniCPM3-4B,HuggingFaceTB/SmolLM2-135M-Instruct,HuggingFaceTB/SmolLM2-360M-Instruct,HuggingFaceTB/SmolLM2-1.7B-Instruct,ibm-granite/granite-3.3-2b-instruct,ibm-granite/granite-3.3-8b-instruct,CohereForAI/c4ai-command-r-v01,CohereForAI/c4ai-command-r-plus,CohereForAI/aya-23-8B,CohereForAI/aya-23-35B,bigscience/bloomz-7b1,bigscience/bloom,mosaicml/mpt-7b-instruct,mosaicml/mpt-30b-instruct,databricks/dbrx-instruct,ai21labs/Jamba-v0.1,Nexusflow/Starling-LM-7B-beta,HuggingFaceH4/zephyr-7b-beta,NousResearch/Nous-Hermes-2-Mixtral-8x7B-DPO,openchat/openchat-3.5-0106,WizardLMTeam/WizardLM-2-8x22B,lmsys/vicuna-13b-v1.5,codellama/CodeLlama-7b-Instruct-hf,codellama/CodeLlama-13b-Instruct-hf,codellama/CodeLlama-34b-Instruct-hf,bigcode/starcoder2-3b,bigcode/starcoder2-7b,bigcode/starcoder2-15b,nvidia/Llama-3.1-Nemotron-70B-Instruct-HF,google/flan-ul2,allenai/OLMo-7B-Instruct,allenai/OLMo-2-1124-7B-Instruct,allenai/OLMo-2-1124-13B-Instruct,cerebras/Cerebras-GPT-111M,cerebras/Cerebras-GPT-256M,cerebras/Cerebras-GPT-590M,cerebras/Cerebras-GPT-1.3B,cerebras/Cerebras-GPT-2.7B,cerebras/Cerebras-GPT-6.7B,cerebras/Cerebras-GPT-13B,OpenAssistant/oasst-sft-4-pythia-12b-epoch-3.5,EleutherAI/pythia-70m,EleutherAI/pythia-160m,EleutherAI/pythia-410m,EleutherAI/pythia-1b,EleutherAI/pythia-1.4b,EleutherAI/pythia-2.8b,EleutherAI/pythia-6.9b,EleutherAI/pythia-12b,databricks/dolly-v2-3b,databricks/dolly-v2-7b,databricks/dolly-v2-12b,stabilityai/stablelm-base-alpha-3b,stabilityai/stablelm-base-alpha-7b,stabilityai/stablelm-tuned-alpha-3b,stabilityai/stablelm-tuned-alpha-7b,lmsys/fastchat-t5-3b-v1.0,aisquared/dlite-v2-1_5b,h2oai/h2ogpt-oasst1-512-12b,togethercomputer/RedPajama-INCITE-7B-Instruct,openlm-research/open_llama_3b,openlm-research/open_llama_7b,openlm-research/open_llama_13b,mosaicml/mpt-7b-chat,mosaicml/mpt-7b-storywriter,mosaicml/mpt-30b-chat,nomic-ai/gpt4all-j,Salesforce/xgen-7b-8k-inst,inceptionai/jais-13b-chat,codellama/CodeLlama-70b-Instruct-hf,teknium/OpenHermes-2.5-Mistral-7B,apple/OpenELM-270M-Instruct,apple/OpenELM-450M-Instruct,apple/OpenELM-1_1B-Instruct,apple/OpenELM-3B-Instruct,Deci/DeciLM-7B-instruct,THUDM/chatglm-6b,THUDM/chatglm2-6b,THUDM/chatglm3-6b,Skywork/Skywork-13B-base,LLM360/Amber,Cerebras/FLOR-6.3B,Qwen/Qwen1.5-0.5B-Chat,Qwen/Qwen1.5-1.8B-Chat,Qwen/Qwen1.5-4B-Chat,Qwen/Qwen1.5-7B-Chat,Qwen/Qwen1.5-14B-Chat,Qwen/Qwen1.5-32B-Chat,Qwen/Qwen1.5-72B-Chat,Qwen/Qwen1.5-110B-Chat,Qwen/Qwen1.5-MoE-A2.7B-Chat,LargeWorldModel/LWM-Text-1M,YerevaNN/YerevaNN-Grok-1,state-spaces/mamba-130m,state-spaces/mamba-370m,state-spaces/mamba-790m,state-spaces/mamba-1.4b,state-spaces/mamba-2.8b,Snowflake/snowflake-arctic-instruct,Fugaku-LLM/Fugaku-LLM-13B-instruct,tiiuae/Falcon2-11B,01-ai/Yi-1.5-6B-Chat,01-ai/Yi-1.5-9B-Chat,01-ai/Yi-1.5-34B-Chat,deepseek-ai/DeepSeek-V2-Lite-Chat,deepseek-ai/DeepSeek-V2-Chat,deepseek-ai/DeepSeek-V3,deepseek-ai/DeepSeek-V3-0324,deepseek-ai/DeepSeek-V3.1,deepseek-ai/DeepSeek-V3.2,deepseek-ai/DeepSeek-R1-0528,microsoft/Phi-3-medium-128k-instruct,microsoft/Phi-3-mini-128k-instruct,microsoft/phi-4-reasoning,yulan-team/YuLan-Mini,AtlaAI/Selene-1-Mini-Llama-3.1-8B,bigcode/santacoder,Salesforce/codegen2-1B,Salesforce/codegen2-3_7B,Salesforce/codegen2-7B,HuggingFaceH4/starchat-alpha,replit/replit-code-v1-3b,Salesforce/codet5p-770m,Salesforce/codet5p-2b,Salesforce/codet5p-6b,Salesforce/codegen25-7b-multi,Deci/DeciCoder-1b,meta-llama/Llama-2-7b-chat-hf,meta-llama/Llama-2-13b-chat-hf,meta-llama/Llama-2-70b-chat-hf,meta-llama/Llama-3-8B-Instruct,meta-llama/Llama-3-70B-Instruct,meta-llama/Llama-4-Maverick-17B-128E-Instruct,meta-llama/Llama-4-Scout-17B-16E-Instruct,mistralai/Mistral-7B-Instruct-v0.2,mistralai/Mistral-Large-Instruct-2407,mistralai/Mistral-Large-Instruct-2411,Qwen/Qwen2-72B-Instruct,Qwen/Qwen3-235B-A22B-Instruct-2507,Qwen/Qwen3-235B-A22B-Thinking-2507,Qwen/Qwen3-VL-235B-A22B-Instruct,Qwen/Qwen3.5,Qwen/Qwen3.5-30B-A3B,Qwen/Qwen3.5-Coder,zai-org/GLM-4.5,zai-org/GLM-4.5-Air,zai-org/GLM-4.6,zai-org/GLM-5,moonshotai/Kimi-K2,moonshotai/Kimi-K2-Thinking,moonshotai/Kimi-K2.5,MiniMaxAI/MiniMax-M2.5,stepfun-ai/Step3,stepfun-ai/Step-3.5-Flash,XiaomiMiMo/MiMo-V2-Flash,google/gemma-4-4b-it,google/gemma-4-12b-it,google/gemma-4-27b-it,nvidia/Llama-3.1-Nemotron-Ultra-253B-v1,nvidia/Llama-3.1-Nemotron-Super-49B-v1,nvidia/Llama-3.1-Nemotron-Nano-8B-v1", "default,none,disabled,auto,low,medium,high,xhigh", "default"},
    PythonLlmProvider{"ollama", "Ollama", "local", "openai-chat-completions", "http://127.0.0.1:11434/v1", "qwen3:8b", "OLLAMA_API_KEY", "qwen3:0.6b,qwen3:1.7b,qwen3:4b,qwen3:8b,qwen3:14b,qwen3:30b-a3b,qwen3:32b,qwen3,qwen3-vl:8b,qwen3-vl:32b,qwen3.5,qwen2.5:0.5b,qwen2.5:1.5b,qwen2.5:3b,qwen2.5:7b,qwen2.5:14b,qwen2.5:32b,qwen2.5:72b,qwen2.5-coder:1.5b,qwen2.5-coder:7b,qwen2.5-coder:14b,qwen2.5-coder:32b,qwq:32b,gpt-oss:20b,gpt-oss:120b,gpt-oss:latest,llama4:maverick,llama4:scout,deepseek-v3,deepseek-v3.1,deepseek-v3.2,deepseek-r1:1.5b,deepseek-r1:7b,deepseek-r1:8b,deepseek-r1:14b,deepseek-r1:32b,deepseek-r1:70b,deepseek-coder-v2,llama3.3,llama3.1:8b,llama3.1:70b,llama3.2:1b,llama3.2:3b,llama3.2-vision:11b,llama3.2-vision:90b,mistral,mistral-nemo,mistral-small3.2,mixtral:8x7b,mixtral:8x22b,codestral,devstral,gemma3:1b,gemma3:4b,gemma3:12b,gemma3:27b,gemma4:27b,gemma2:2b,gemma2:9b,gemma2:27b,phi4,phi4-mini,phi3.5,phi3:mini,falcon3:1b,falcon3:3b,falcon3:7b,falcon3:10b,yi:6b,yi:9b,yi:34b,glm4,glm4.5,glm5,kimi-k2,minimax-m2,step3,mimo-v2,internlm2.5,baichuan2:7b,baichuan2:13b,minicpm-v,smollm2:135m,smollm2:360m,smollm2:1.7b,granite3.3:2b,granite3.3:8b,command-r,command-r-plus,starcoder2:3b,starcoder2:7b,starcoder2:15b,codellama:7b,codellama:13b,codellama:34b,dolphin-mixtral,openchat,neural-chat,orca-mini,zephyr,solar,nous-hermes2,wizardlm2,vicuna,rwkv,pythia,dolly-v2,stablelm,redpajama,openllama,mpt,dbrx,arctic,bloom,bloomz,mamba,custom-model", "default,none,disabled,auto,low,medium,high,xhigh", "default"},
    PythonLlmProvider{"vllm", "vLLM / SGLang", "local", "openai-chat-completions", "http://127.0.0.1:8000/v1", "Qwen/Qwen3-8B", "VLLM_API_KEY", "Qwen/Qwen3-0.6B,Qwen/Qwen3-1.7B,Qwen/Qwen3-4B,Qwen/Qwen3-8B,Qwen/Qwen3-14B,Qwen/Qwen3-32B,Qwen/Qwen3-30B-A3B,Qwen/Qwen2.5-0.5B-Instruct,Qwen/Qwen2.5-1.5B-Instruct,Qwen/Qwen2.5-3B-Instruct,Qwen/Qwen2.5-7B-Instruct,Qwen/Qwen2.5-14B-Instruct,Qwen/Qwen2.5-32B-Instruct,Qwen/Qwen2.5-72B-Instruct,Qwen/Qwen2.5-Coder-1.5B-Instruct,Qwen/Qwen2.5-Coder-7B-Instruct,Qwen/Qwen2.5-Coder-14B-Instruct,Qwen/Qwen2.5-Coder-32B-Instruct,Qwen/QwQ-32B,openai/gpt-oss-20b,openai/gpt-oss-120b,google-t5/t5-small,google-t5/t5-base,google-t5/t5-large,google/flan-t5-small,google/flan-t5-base,google/flan-t5-large,google/flan-t5-xl,google/flan-t5-xxl,RWKV/rwkv-4-world,RWKV/rwkv-5-world,RWKV/rwkv-6-world,BlinkDL/rwkv-7-world,EleutherAI/gpt-neox-20b,EleutherAI/gpt-j-6b,EleutherAI/gpt-neo-2.7B,yandex/yalm-100b,meta-llama/Llama-3.3-70B-Instruct,meta-llama/Llama-3.1-8B-Instruct,meta-llama/Llama-3.1-70B-Instruct,meta-llama/Llama-3.2-1B-Instruct,meta-llama/Llama-3.2-3B-Instruct,mistralai/Mistral-7B-Instruct-v0.3,mistralai/Mistral-Nemo-Instruct-2407,mistralai/Mixtral-8x7B-Instruct-v0.1,mistralai/Mixtral-8x22B-Instruct-v0.1,mistralai/Codestral-22B-v0.1,deepseek-ai/DeepSeek-R1,deepseek-ai/DeepSeek-R1-Distill-Qwen-1.5B,deepseek-ai/DeepSeek-R1-Distill-Qwen-7B,deepseek-ai/DeepSeek-R1-Distill-Qwen-14B,deepseek-ai/DeepSeek-R1-Distill-Qwen-32B,deepseek-ai/deepseek-coder-6.7b-instruct,deepseek-ai/DeepSeek-Coder-V2-Instruct,google/gemma-3-1b-it,google/gemma-3-4b-it,google/gemma-3-12b-it,google/gemma-3-27b-it,google/gemma-2-2b-it,google/gemma-2-9b-it,google/gemma-2-27b-it,microsoft/phi-4,microsoft/Phi-4-mini-instruct,microsoft/Phi-3.5-mini-instruct,tiiuae/Falcon3-1B-Instruct,tiiuae/Falcon3-3B-Instruct,tiiuae/Falcon3-7B-Instruct,tiiuae/Falcon3-10B-Instruct,tiiuae/falcon-180B-chat,01-ai/Yi-6B-Chat,01-ai/Yi-9B-Chat,01-ai/Yi-34B-Chat,THUDM/glm-4-9b-chat,internlm/internlm2_5-7b-chat,internlm/internlm2_5-20b-chat,baichuan-inc/Baichuan2-7B-Chat,baichuan-inc/Baichuan2-13B-Chat,openbmb/MiniCPM3-4B,HuggingFaceTB/SmolLM2-135M-Instruct,HuggingFaceTB/SmolLM2-360M-Instruct,HuggingFaceTB/SmolLM2-1.7B-Instruct,ibm-granite/granite-3.3-2b-instruct,ibm-granite/granite-3.3-8b-instruct,CohereForAI/c4ai-command-r-v01,CohereForAI/c4ai-command-r-plus,CohereForAI/aya-23-8B,CohereForAI/aya-23-35B,bigscience/bloomz-7b1,bigscience/bloom,mosaicml/mpt-7b-instruct,mosaicml/mpt-30b-instruct,databricks/dbrx-instruct,ai21labs/Jamba-v0.1,Nexusflow/Starling-LM-7B-beta,HuggingFaceH4/zephyr-7b-beta,NousResearch/Nous-Hermes-2-Mixtral-8x7B-DPO,openchat/openchat-3.5-0106,WizardLMTeam/WizardLM-2-8x22B,lmsys/vicuna-13b-v1.5,codellama/CodeLlama-7b-Instruct-hf,codellama/CodeLlama-13b-Instruct-hf,codellama/CodeLlama-34b-Instruct-hf,bigcode/starcoder2-3b,bigcode/starcoder2-7b,bigcode/starcoder2-15b,nvidia/Llama-3.1-Nemotron-70B-Instruct-HF,google/flan-ul2,allenai/OLMo-7B-Instruct,allenai/OLMo-2-1124-7B-Instruct,allenai/OLMo-2-1124-13B-Instruct,cerebras/Cerebras-GPT-111M,cerebras/Cerebras-GPT-256M,cerebras/Cerebras-GPT-590M,cerebras/Cerebras-GPT-1.3B,cerebras/Cerebras-GPT-2.7B,cerebras/Cerebras-GPT-6.7B,cerebras/Cerebras-GPT-13B,OpenAssistant/oasst-sft-4-pythia-12b-epoch-3.5,EleutherAI/pythia-70m,EleutherAI/pythia-160m,EleutherAI/pythia-410m,EleutherAI/pythia-1b,EleutherAI/pythia-1.4b,EleutherAI/pythia-2.8b,EleutherAI/pythia-6.9b,EleutherAI/pythia-12b,databricks/dolly-v2-3b,databricks/dolly-v2-7b,databricks/dolly-v2-12b,stabilityai/stablelm-base-alpha-3b,stabilityai/stablelm-base-alpha-7b,stabilityai/stablelm-tuned-alpha-3b,stabilityai/stablelm-tuned-alpha-7b,lmsys/fastchat-t5-3b-v1.0,aisquared/dlite-v2-1_5b,h2oai/h2ogpt-oasst1-512-12b,togethercomputer/RedPajama-INCITE-7B-Instruct,openlm-research/open_llama_3b,openlm-research/open_llama_7b,openlm-research/open_llama_13b,mosaicml/mpt-7b-chat,mosaicml/mpt-7b-storywriter,mosaicml/mpt-30b-chat,nomic-ai/gpt4all-j,Salesforce/xgen-7b-8k-inst,inceptionai/jais-13b-chat,codellama/CodeLlama-70b-Instruct-hf,teknium/OpenHermes-2.5-Mistral-7B,apple/OpenELM-270M-Instruct,apple/OpenELM-450M-Instruct,apple/OpenELM-1_1B-Instruct,apple/OpenELM-3B-Instruct,Deci/DeciLM-7B-instruct,THUDM/chatglm-6b,THUDM/chatglm2-6b,THUDM/chatglm3-6b,Skywork/Skywork-13B-base,LLM360/Amber,Cerebras/FLOR-6.3B,Qwen/Qwen1.5-0.5B-Chat,Qwen/Qwen1.5-1.8B-Chat,Qwen/Qwen1.5-4B-Chat,Qwen/Qwen1.5-7B-Chat,Qwen/Qwen1.5-14B-Chat,Qwen/Qwen1.5-32B-Chat,Qwen/Qwen1.5-72B-Chat,Qwen/Qwen1.5-110B-Chat,Qwen/Qwen1.5-MoE-A2.7B-Chat,LargeWorldModel/LWM-Text-1M,YerevaNN/YerevaNN-Grok-1,state-spaces/mamba-130m,state-spaces/mamba-370m,state-spaces/mamba-790m,state-spaces/mamba-1.4b,state-spaces/mamba-2.8b,Snowflake/snowflake-arctic-instruct,Fugaku-LLM/Fugaku-LLM-13B-instruct,tiiuae/Falcon2-11B,01-ai/Yi-1.5-6B-Chat,01-ai/Yi-1.5-9B-Chat,01-ai/Yi-1.5-34B-Chat,deepseek-ai/DeepSeek-V2-Lite-Chat,deepseek-ai/DeepSeek-V2-Chat,deepseek-ai/DeepSeek-V3,deepseek-ai/DeepSeek-V3-0324,deepseek-ai/DeepSeek-V3.1,deepseek-ai/DeepSeek-V3.2,deepseek-ai/DeepSeek-R1-0528,microsoft/Phi-3-medium-128k-instruct,microsoft/Phi-3-mini-128k-instruct,microsoft/phi-4-reasoning,yulan-team/YuLan-Mini,AtlaAI/Selene-1-Mini-Llama-3.1-8B,bigcode/santacoder,Salesforce/codegen2-1B,Salesforce/codegen2-3_7B,Salesforce/codegen2-7B,HuggingFaceH4/starchat-alpha,replit/replit-code-v1-3b,Salesforce/codet5p-770m,Salesforce/codet5p-2b,Salesforce/codet5p-6b,Salesforce/codegen25-7b-multi,Deci/DeciCoder-1b,meta-llama/Llama-2-7b-chat-hf,meta-llama/Llama-2-13b-chat-hf,meta-llama/Llama-2-70b-chat-hf,meta-llama/Llama-3-8B-Instruct,meta-llama/Llama-3-70B-Instruct,meta-llama/Llama-4-Maverick-17B-128E-Instruct,meta-llama/Llama-4-Scout-17B-16E-Instruct,mistralai/Mistral-7B-Instruct-v0.2,mistralai/Mistral-Large-Instruct-2407,mistralai/Mistral-Large-Instruct-2411,Qwen/Qwen2-72B-Instruct,Qwen/Qwen3-235B-A22B-Instruct-2507,Qwen/Qwen3-235B-A22B-Thinking-2507,Qwen/Qwen3-VL-235B-A22B-Instruct,Qwen/Qwen3.5,Qwen/Qwen3.5-30B-A3B,Qwen/Qwen3.5-Coder,zai-org/GLM-4.5,zai-org/GLM-4.5-Air,zai-org/GLM-4.6,zai-org/GLM-5,moonshotai/Kimi-K2,moonshotai/Kimi-K2-Thinking,moonshotai/Kimi-K2.5,MiniMaxAI/MiniMax-M2.5,stepfun-ai/Step3,stepfun-ai/Step-3.5-Flash,XiaomiMiMo/MiMo-V2-Flash,google/gemma-4-4b-it,google/gemma-4-12b-it,google/gemma-4-27b-it,nvidia/Llama-3.1-Nemotron-Ultra-253B-v1,nvidia/Llama-3.1-Nemotron-Super-49B-v1,nvidia/Llama-3.1-Nemotron-Nano-8B-v1", "default,none,disabled,auto,low,medium,high,xhigh", "default"},
    PythonLlmProvider{"llamacpp", "llama.cpp server", "local", "openai-chat-completions", "http://127.0.0.1:8080/v1", "local-model", "LLAMACPP_API_KEY", "local-model,qwen3-8b-q4_k_m.gguf,llama-3.1-8b-instruct-q4_k_m.gguf,mistral-7b-instruct-q4_k_m.gguf,gemma-3-4b-it-q4_k_m.gguf,qwen3:0.6b,qwen3:1.7b,qwen3:4b,qwen3:8b,qwen3:14b,qwen3:30b-a3b,qwen3:32b,qwen3,qwen3-vl:8b,qwen3-vl:32b,qwen3.5,qwen2.5:0.5b,qwen2.5:1.5b,qwen2.5:3b,qwen2.5:7b,qwen2.5:14b,qwen2.5:32b,qwen2.5:72b,qwen2.5-coder:1.5b,qwen2.5-coder:7b,qwen2.5-coder:14b,qwen2.5-coder:32b,qwq:32b,gpt-oss:20b,gpt-oss:120b,gpt-oss:latest,llama4:maverick,llama4:scout,deepseek-v3,deepseek-v3.1,deepseek-v3.2,deepseek-r1:1.5b,deepseek-r1:7b,deepseek-r1:8b,deepseek-r1:14b,deepseek-r1:32b,deepseek-r1:70b,deepseek-coder-v2,llama3.3,llama3.1:8b,llama3.1:70b,llama3.2:1b,llama3.2:3b,llama3.2-vision:11b,llama3.2-vision:90b,mistral,mistral-nemo,mistral-small3.2,mixtral:8x7b,mixtral:8x22b,codestral,devstral,gemma3:1b,gemma3:4b,gemma3:12b,gemma3:27b,gemma4:27b,gemma2:2b,gemma2:9b,gemma2:27b,phi4,phi4-mini,phi3.5,phi3:mini,falcon3:1b,falcon3:3b,falcon3:7b,falcon3:10b,yi:6b,yi:9b,yi:34b,glm4,glm4.5,glm5,kimi-k2,minimax-m2,step3,mimo-v2,internlm2.5,baichuan2:7b,baichuan2:13b,minicpm-v,smollm2:135m,smollm2:360m,smollm2:1.7b,granite3.3:2b,granite3.3:8b,command-r,command-r-plus,starcoder2:3b,starcoder2:7b,starcoder2:15b,codellama:7b,codellama:13b,codellama:34b,dolphin-mixtral,openchat,neural-chat,orca-mini,zephyr,solar,nous-hermes2,wizardlm2,vicuna,rwkv,pythia,dolly-v2,stablelm,redpajama,openllama,mpt,dbrx,arctic,bloom,bloomz,mamba,custom-model,google/flan-ul2,allenai/OLMo-7B-Instruct,allenai/OLMo-2-1124-7B-Instruct,allenai/OLMo-2-1124-13B-Instruct,cerebras/Cerebras-GPT-111M,cerebras/Cerebras-GPT-256M,cerebras/Cerebras-GPT-590M,cerebras/Cerebras-GPT-1.3B,cerebras/Cerebras-GPT-2.7B,cerebras/Cerebras-GPT-6.7B,cerebras/Cerebras-GPT-13B,OpenAssistant/oasst-sft-4-pythia-12b-epoch-3.5,EleutherAI/pythia-70m,EleutherAI/pythia-160m,EleutherAI/pythia-410m,EleutherAI/pythia-1b,EleutherAI/pythia-1.4b,EleutherAI/pythia-2.8b,EleutherAI/pythia-6.9b,EleutherAI/pythia-12b,databricks/dolly-v2-3b,databricks/dolly-v2-7b,databricks/dolly-v2-12b,stabilityai/stablelm-base-alpha-3b,stabilityai/stablelm-base-alpha-7b,stabilityai/stablelm-tuned-alpha-3b,stabilityai/stablelm-tuned-alpha-7b,lmsys/fastchat-t5-3b-v1.0,aisquared/dlite-v2-1_5b,h2oai/h2ogpt-oasst1-512-12b,togethercomputer/RedPajama-INCITE-7B-Instruct,openlm-research/open_llama_3b,openlm-research/open_llama_7b,openlm-research/open_llama_13b,mosaicml/mpt-7b-chat,mosaicml/mpt-7b-storywriter,mosaicml/mpt-30b-chat,nomic-ai/gpt4all-j,Salesforce/xgen-7b-8k-inst,inceptionai/jais-13b-chat,codellama/CodeLlama-70b-Instruct-hf,teknium/OpenHermes-2.5-Mistral-7B,apple/OpenELM-270M-Instruct,apple/OpenELM-450M-Instruct,apple/OpenELM-1_1B-Instruct,apple/OpenELM-3B-Instruct,Deci/DeciLM-7B-instruct,THUDM/chatglm-6b,THUDM/chatglm2-6b,THUDM/chatglm3-6b,THUDM/glm-4-9b-chat,Skywork/Skywork-13B-base,LLM360/Amber,Cerebras/FLOR-6.3B,Qwen/Qwen1.5-0.5B-Chat,Qwen/Qwen1.5-1.8B-Chat,Qwen/Qwen1.5-4B-Chat,Qwen/Qwen1.5-7B-Chat,Qwen/Qwen1.5-14B-Chat,Qwen/Qwen1.5-32B-Chat,Qwen/Qwen1.5-72B-Chat,Qwen/Qwen1.5-110B-Chat,Qwen/Qwen1.5-MoE-A2.7B-Chat,LargeWorldModel/LWM-Text-1M,YerevaNN/YerevaNN-Grok-1,state-spaces/mamba-130m,state-spaces/mamba-370m,state-spaces/mamba-790m,state-spaces/mamba-1.4b,state-spaces/mamba-2.8b,Snowflake/snowflake-arctic-instruct,Fugaku-LLM/Fugaku-LLM-13B-instruct,tiiuae/Falcon2-11B,01-ai/Yi-1.5-6B-Chat,01-ai/Yi-1.5-9B-Chat,01-ai/Yi-1.5-34B-Chat,deepseek-ai/DeepSeek-V2-Lite-Chat,deepseek-ai/DeepSeek-V2-Chat,deepseek-ai/DeepSeek-V3,deepseek-ai/DeepSeek-V3-0324,deepseek-ai/DeepSeek-V3.1,deepseek-ai/DeepSeek-V3.2,deepseek-ai/DeepSeek-R1-0528,microsoft/Phi-3-medium-128k-instruct,microsoft/Phi-3-mini-128k-instruct,microsoft/phi-4-reasoning,yulan-team/YuLan-Mini,AtlaAI/Selene-1-Mini-Llama-3.1-8B,bigcode/santacoder,Salesforce/codegen2-1B,Salesforce/codegen2-3_7B,Salesforce/codegen2-7B,HuggingFaceH4/starchat-alpha,replit/replit-code-v1-3b,Salesforce/codet5p-770m,Salesforce/codet5p-2b,Salesforce/codet5p-6b,Salesforce/codegen25-7b-multi,Deci/DeciCoder-1b,meta-llama/Llama-2-7b-chat-hf,meta-llama/Llama-2-13b-chat-hf,meta-llama/Llama-2-70b-chat-hf,meta-llama/Llama-3-8B-Instruct,meta-llama/Llama-3-70B-Instruct,meta-llama/Llama-4-Maverick-17B-128E-Instruct,meta-llama/Llama-4-Scout-17B-16E-Instruct,mistralai/Mistral-7B-Instruct-v0.2,mistralai/Mistral-Large-Instruct-2407,mistralai/Mistral-Large-Instruct-2411,Qwen/Qwen2-72B-Instruct,Qwen/Qwen3-235B-A22B-Instruct-2507,Qwen/Qwen3-235B-A22B-Thinking-2507,Qwen/Qwen3-VL-235B-A22B-Instruct,Qwen/Qwen3.5,Qwen/Qwen3.5-30B-A3B,Qwen/Qwen3.5-Coder,zai-org/GLM-4.5,zai-org/GLM-4.5-Air,zai-org/GLM-4.6,zai-org/GLM-5,moonshotai/Kimi-K2,moonshotai/Kimi-K2-Thinking,moonshotai/Kimi-K2.5,MiniMaxAI/MiniMax-M2.5,stepfun-ai/Step3,stepfun-ai/Step-3.5-Flash,XiaomiMiMo/MiMo-V2-Flash,google/gemma-4-4b-it,google/gemma-4-12b-it,google/gemma-4-27b-it,nvidia/Llama-3.1-Nemotron-Ultra-253B-v1,nvidia/Llama-3.1-Nemotron-Super-49B-v1,nvidia/Llama-3.1-Nemotron-Nano-8B-v1", "default,none,disabled,auto,low,medium,high,xhigh", "default"},
    PythonLlmProvider{"lmstudio", "LM Studio", "local", "openai-chat-completions", "http://127.0.0.1:1234/v1", "local-model", "LMSTUDIO_API_KEY", "local-model,Qwen/Qwen3-0.6B,Qwen/Qwen3-1.7B,Qwen/Qwen3-4B,Qwen/Qwen3-8B,Qwen/Qwen3-14B,Qwen/Qwen3-32B,Qwen/Qwen3-30B-A3B,Qwen/Qwen2.5-0.5B-Instruct,Qwen/Qwen2.5-1.5B-Instruct,Qwen/Qwen2.5-3B-Instruct,Qwen/Qwen2.5-7B-Instruct,Qwen/Qwen2.5-14B-Instruct,Qwen/Qwen2.5-32B-Instruct,Qwen/Qwen2.5-72B-Instruct,Qwen/Qwen2.5-Coder-1.5B-Instruct,Qwen/Qwen2.5-Coder-7B-Instruct,Qwen/Qwen2.5-Coder-14B-Instruct,Qwen/Qwen2.5-Coder-32B-Instruct,Qwen/QwQ-32B,openai/gpt-oss-20b,openai/gpt-oss-120b,google-t5/t5-small,google-t5/t5-base,google-t5/t5-large,google/flan-t5-small,google/flan-t5-base,google/flan-t5-large,google/flan-t5-xl,google/flan-t5-xxl,RWKV/rwkv-4-world,RWKV/rwkv-5-world,RWKV/rwkv-6-world,BlinkDL/rwkv-7-world,EleutherAI/gpt-neox-20b,EleutherAI/gpt-j-6b,EleutherAI/gpt-neo-2.7B,yandex/yalm-100b,meta-llama/Llama-3.3-70B-Instruct,meta-llama/Llama-3.1-8B-Instruct,meta-llama/Llama-3.1-70B-Instruct,meta-llama/Llama-3.2-1B-Instruct,meta-llama/Llama-3.2-3B-Instruct,mistralai/Mistral-7B-Instruct-v0.3,mistralai/Mistral-Nemo-Instruct-2407,mistralai/Mixtral-8x7B-Instruct-v0.1,mistralai/Mixtral-8x22B-Instruct-v0.1,mistralai/Codestral-22B-v0.1,deepseek-ai/DeepSeek-R1,deepseek-ai/DeepSeek-R1-Distill-Qwen-1.5B,deepseek-ai/DeepSeek-R1-Distill-Qwen-7B,deepseek-ai/DeepSeek-R1-Distill-Qwen-14B,deepseek-ai/DeepSeek-R1-Distill-Qwen-32B,deepseek-ai/deepseek-coder-6.7b-instruct,deepseek-ai/DeepSeek-Coder-V2-Instruct,google/gemma-3-1b-it,google/gemma-3-4b-it,google/gemma-3-12b-it,google/gemma-3-27b-it,google/gemma-2-2b-it,google/gemma-2-9b-it,google/gemma-2-27b-it,microsoft/phi-4,microsoft/Phi-4-mini-instruct,microsoft/Phi-3.5-mini-instruct,tiiuae/Falcon3-1B-Instruct,tiiuae/Falcon3-3B-Instruct,tiiuae/Falcon3-7B-Instruct,tiiuae/Falcon3-10B-Instruct,tiiuae/falcon-180B-chat,01-ai/Yi-6B-Chat,01-ai/Yi-9B-Chat,01-ai/Yi-34B-Chat,THUDM/glm-4-9b-chat,internlm/internlm2_5-7b-chat,internlm/internlm2_5-20b-chat,baichuan-inc/Baichuan2-7B-Chat,baichuan-inc/Baichuan2-13B-Chat,openbmb/MiniCPM3-4B,HuggingFaceTB/SmolLM2-135M-Instruct,HuggingFaceTB/SmolLM2-360M-Instruct,HuggingFaceTB/SmolLM2-1.7B-Instruct,ibm-granite/granite-3.3-2b-instruct,ibm-granite/granite-3.3-8b-instruct,CohereForAI/c4ai-command-r-v01,CohereForAI/c4ai-command-r-plus,CohereForAI/aya-23-8B,CohereForAI/aya-23-35B,bigscience/bloomz-7b1,bigscience/bloom,mosaicml/mpt-7b-instruct,mosaicml/mpt-30b-instruct,databricks/dbrx-instruct,ai21labs/Jamba-v0.1,Nexusflow/Starling-LM-7B-beta,HuggingFaceH4/zephyr-7b-beta,NousResearch/Nous-Hermes-2-Mixtral-8x7B-DPO,openchat/openchat-3.5-0106,WizardLMTeam/WizardLM-2-8x22B,lmsys/vicuna-13b-v1.5,codellama/CodeLlama-7b-Instruct-hf,codellama/CodeLlama-13b-Instruct-hf,codellama/CodeLlama-34b-Instruct-hf,bigcode/starcoder2-3b,bigcode/starcoder2-7b,bigcode/starcoder2-15b,nvidia/Llama-3.1-Nemotron-70B-Instruct-HF,google/flan-ul2,allenai/OLMo-7B-Instruct,allenai/OLMo-2-1124-7B-Instruct,allenai/OLMo-2-1124-13B-Instruct,cerebras/Cerebras-GPT-111M,cerebras/Cerebras-GPT-256M,cerebras/Cerebras-GPT-590M,cerebras/Cerebras-GPT-1.3B,cerebras/Cerebras-GPT-2.7B,cerebras/Cerebras-GPT-6.7B,cerebras/Cerebras-GPT-13B,OpenAssistant/oasst-sft-4-pythia-12b-epoch-3.5,EleutherAI/pythia-70m,EleutherAI/pythia-160m,EleutherAI/pythia-410m,EleutherAI/pythia-1b,EleutherAI/pythia-1.4b,EleutherAI/pythia-2.8b,EleutherAI/pythia-6.9b,EleutherAI/pythia-12b,databricks/dolly-v2-3b,databricks/dolly-v2-7b,databricks/dolly-v2-12b,stabilityai/stablelm-base-alpha-3b,stabilityai/stablelm-base-alpha-7b,stabilityai/stablelm-tuned-alpha-3b,stabilityai/stablelm-tuned-alpha-7b,lmsys/fastchat-t5-3b-v1.0,aisquared/dlite-v2-1_5b,h2oai/h2ogpt-oasst1-512-12b,togethercomputer/RedPajama-INCITE-7B-Instruct,openlm-research/open_llama_3b,openlm-research/open_llama_7b,openlm-research/open_llama_13b,mosaicml/mpt-7b-chat,mosaicml/mpt-7b-storywriter,mosaicml/mpt-30b-chat,nomic-ai/gpt4all-j,Salesforce/xgen-7b-8k-inst,inceptionai/jais-13b-chat,codellama/CodeLlama-70b-Instruct-hf,teknium/OpenHermes-2.5-Mistral-7B,apple/OpenELM-270M-Instruct,apple/OpenELM-450M-Instruct,apple/OpenELM-1_1B-Instruct,apple/OpenELM-3B-Instruct,Deci/DeciLM-7B-instruct,THUDM/chatglm-6b,THUDM/chatglm2-6b,THUDM/chatglm3-6b,Skywork/Skywork-13B-base,LLM360/Amber,Cerebras/FLOR-6.3B,Qwen/Qwen1.5-0.5B-Chat,Qwen/Qwen1.5-1.8B-Chat,Qwen/Qwen1.5-4B-Chat,Qwen/Qwen1.5-7B-Chat,Qwen/Qwen1.5-14B-Chat,Qwen/Qwen1.5-32B-Chat,Qwen/Qwen1.5-72B-Chat,Qwen/Qwen1.5-110B-Chat,Qwen/Qwen1.5-MoE-A2.7B-Chat,LargeWorldModel/LWM-Text-1M,YerevaNN/YerevaNN-Grok-1,state-spaces/mamba-130m,state-spaces/mamba-370m,state-spaces/mamba-790m,state-spaces/mamba-1.4b,state-spaces/mamba-2.8b,Snowflake/snowflake-arctic-instruct,Fugaku-LLM/Fugaku-LLM-13B-instruct,tiiuae/Falcon2-11B,01-ai/Yi-1.5-6B-Chat,01-ai/Yi-1.5-9B-Chat,01-ai/Yi-1.5-34B-Chat,deepseek-ai/DeepSeek-V2-Lite-Chat,deepseek-ai/DeepSeek-V2-Chat,deepseek-ai/DeepSeek-V3,deepseek-ai/DeepSeek-V3-0324,deepseek-ai/DeepSeek-V3.1,deepseek-ai/DeepSeek-V3.2,deepseek-ai/DeepSeek-R1-0528,microsoft/Phi-3-medium-128k-instruct,microsoft/Phi-3-mini-128k-instruct,microsoft/phi-4-reasoning,yulan-team/YuLan-Mini,AtlaAI/Selene-1-Mini-Llama-3.1-8B,bigcode/santacoder,Salesforce/codegen2-1B,Salesforce/codegen2-3_7B,Salesforce/codegen2-7B,HuggingFaceH4/starchat-alpha,replit/replit-code-v1-3b,Salesforce/codet5p-770m,Salesforce/codet5p-2b,Salesforce/codet5p-6b,Salesforce/codegen25-7b-multi,Deci/DeciCoder-1b,meta-llama/Llama-2-7b-chat-hf,meta-llama/Llama-2-13b-chat-hf,meta-llama/Llama-2-70b-chat-hf,meta-llama/Llama-3-8B-Instruct,meta-llama/Llama-3-70B-Instruct,meta-llama/Llama-4-Maverick-17B-128E-Instruct,meta-llama/Llama-4-Scout-17B-16E-Instruct,mistralai/Mistral-7B-Instruct-v0.2,mistralai/Mistral-Large-Instruct-2407,mistralai/Mistral-Large-Instruct-2411,Qwen/Qwen2-72B-Instruct,Qwen/Qwen3-235B-A22B-Instruct-2507,Qwen/Qwen3-235B-A22B-Thinking-2507,Qwen/Qwen3-VL-235B-A22B-Instruct,Qwen/Qwen3.5,Qwen/Qwen3.5-30B-A3B,Qwen/Qwen3.5-Coder,zai-org/GLM-4.5,zai-org/GLM-4.5-Air,zai-org/GLM-4.6,zai-org/GLM-5,moonshotai/Kimi-K2,moonshotai/Kimi-K2-Thinking,moonshotai/Kimi-K2.5,MiniMaxAI/MiniMax-M2.5,stepfun-ai/Step3,stepfun-ai/Step-3.5-Flash,XiaomiMiMo/MiMo-V2-Flash,google/gemma-4-4b-it,google/gemma-4-12b-it,google/gemma-4-27b-it,nvidia/Llama-3.1-Nemotron-Ultra-253B-v1,nvidia/Llama-3.1-Nemotron-Super-49B-v1,nvidia/Llama-3.1-Nemotron-Nano-8B-v1", "default,none,disabled,auto,low,medium,high,xhigh", "default"},
    PythonLlmProvider{"tgi", "Hugging Face TGI", "local", "openai-chat-completions", "http://127.0.0.1:3000/v1", "tgi", "HUGGINGFACE_API_KEY", "tgi,Qwen/Qwen3-0.6B,Qwen/Qwen3-1.7B,Qwen/Qwen3-4B,Qwen/Qwen3-8B,Qwen/Qwen3-14B,Qwen/Qwen3-32B,Qwen/Qwen3-30B-A3B,Qwen/Qwen2.5-0.5B-Instruct,Qwen/Qwen2.5-1.5B-Instruct,Qwen/Qwen2.5-3B-Instruct,Qwen/Qwen2.5-7B-Instruct,Qwen/Qwen2.5-14B-Instruct,Qwen/Qwen2.5-32B-Instruct,Qwen/Qwen2.5-72B-Instruct,Qwen/Qwen2.5-Coder-1.5B-Instruct,Qwen/Qwen2.5-Coder-7B-Instruct,Qwen/Qwen2.5-Coder-14B-Instruct,Qwen/Qwen2.5-Coder-32B-Instruct,Qwen/QwQ-32B,openai/gpt-oss-20b,openai/gpt-oss-120b,google-t5/t5-small,google-t5/t5-base,google-t5/t5-large,google/flan-t5-small,google/flan-t5-base,google/flan-t5-large,google/flan-t5-xl,google/flan-t5-xxl,RWKV/rwkv-4-world,RWKV/rwkv-5-world,RWKV/rwkv-6-world,BlinkDL/rwkv-7-world,EleutherAI/gpt-neox-20b,EleutherAI/gpt-j-6b,EleutherAI/gpt-neo-2.7B,yandex/yalm-100b,meta-llama/Llama-3.3-70B-Instruct,meta-llama/Llama-3.1-8B-Instruct,meta-llama/Llama-3.1-70B-Instruct,meta-llama/Llama-3.2-1B-Instruct,meta-llama/Llama-3.2-3B-Instruct,mistralai/Mistral-7B-Instruct-v0.3,mistralai/Mistral-Nemo-Instruct-2407,mistralai/Mixtral-8x7B-Instruct-v0.1,mistralai/Mixtral-8x22B-Instruct-v0.1,mistralai/Codestral-22B-v0.1,deepseek-ai/DeepSeek-R1,deepseek-ai/DeepSeek-R1-Distill-Qwen-1.5B,deepseek-ai/DeepSeek-R1-Distill-Qwen-7B,deepseek-ai/DeepSeek-R1-Distill-Qwen-14B,deepseek-ai/DeepSeek-R1-Distill-Qwen-32B,deepseek-ai/deepseek-coder-6.7b-instruct,deepseek-ai/DeepSeek-Coder-V2-Instruct,google/gemma-3-1b-it,google/gemma-3-4b-it,google/gemma-3-12b-it,google/gemma-3-27b-it,google/gemma-2-2b-it,google/gemma-2-9b-it,google/gemma-2-27b-it,microsoft/phi-4,microsoft/Phi-4-mini-instruct,microsoft/Phi-3.5-mini-instruct,tiiuae/Falcon3-1B-Instruct,tiiuae/Falcon3-3B-Instruct,tiiuae/Falcon3-7B-Instruct,tiiuae/Falcon3-10B-Instruct,tiiuae/falcon-180B-chat,01-ai/Yi-6B-Chat,01-ai/Yi-9B-Chat,01-ai/Yi-34B-Chat,THUDM/glm-4-9b-chat,internlm/internlm2_5-7b-chat,internlm/internlm2_5-20b-chat,baichuan-inc/Baichuan2-7B-Chat,baichuan-inc/Baichuan2-13B-Chat,openbmb/MiniCPM3-4B,HuggingFaceTB/SmolLM2-135M-Instruct,HuggingFaceTB/SmolLM2-360M-Instruct,HuggingFaceTB/SmolLM2-1.7B-Instruct,ibm-granite/granite-3.3-2b-instruct,ibm-granite/granite-3.3-8b-instruct,CohereForAI/c4ai-command-r-v01,CohereForAI/c4ai-command-r-plus,CohereForAI/aya-23-8B,CohereForAI/aya-23-35B,bigscience/bloomz-7b1,bigscience/bloom,mosaicml/mpt-7b-instruct,mosaicml/mpt-30b-instruct,databricks/dbrx-instruct,ai21labs/Jamba-v0.1,Nexusflow/Starling-LM-7B-beta,HuggingFaceH4/zephyr-7b-beta,NousResearch/Nous-Hermes-2-Mixtral-8x7B-DPO,openchat/openchat-3.5-0106,WizardLMTeam/WizardLM-2-8x22B,lmsys/vicuna-13b-v1.5,codellama/CodeLlama-7b-Instruct-hf,codellama/CodeLlama-13b-Instruct-hf,codellama/CodeLlama-34b-Instruct-hf,bigcode/starcoder2-3b,bigcode/starcoder2-7b,bigcode/starcoder2-15b,nvidia/Llama-3.1-Nemotron-70B-Instruct-HF,google/flan-ul2,allenai/OLMo-7B-Instruct,allenai/OLMo-2-1124-7B-Instruct,allenai/OLMo-2-1124-13B-Instruct,cerebras/Cerebras-GPT-111M,cerebras/Cerebras-GPT-256M,cerebras/Cerebras-GPT-590M,cerebras/Cerebras-GPT-1.3B,cerebras/Cerebras-GPT-2.7B,cerebras/Cerebras-GPT-6.7B,cerebras/Cerebras-GPT-13B,OpenAssistant/oasst-sft-4-pythia-12b-epoch-3.5,EleutherAI/pythia-70m,EleutherAI/pythia-160m,EleutherAI/pythia-410m,EleutherAI/pythia-1b,EleutherAI/pythia-1.4b,EleutherAI/pythia-2.8b,EleutherAI/pythia-6.9b,EleutherAI/pythia-12b,databricks/dolly-v2-3b,databricks/dolly-v2-7b,databricks/dolly-v2-12b,stabilityai/stablelm-base-alpha-3b,stabilityai/stablelm-base-alpha-7b,stabilityai/stablelm-tuned-alpha-3b,stabilityai/stablelm-tuned-alpha-7b,lmsys/fastchat-t5-3b-v1.0,aisquared/dlite-v2-1_5b,h2oai/h2ogpt-oasst1-512-12b,togethercomputer/RedPajama-INCITE-7B-Instruct,openlm-research/open_llama_3b,openlm-research/open_llama_7b,openlm-research/open_llama_13b,mosaicml/mpt-7b-chat,mosaicml/mpt-7b-storywriter,mosaicml/mpt-30b-chat,nomic-ai/gpt4all-j,Salesforce/xgen-7b-8k-inst,inceptionai/jais-13b-chat,codellama/CodeLlama-70b-Instruct-hf,teknium/OpenHermes-2.5-Mistral-7B,apple/OpenELM-270M-Instruct,apple/OpenELM-450M-Instruct,apple/OpenELM-1_1B-Instruct,apple/OpenELM-3B-Instruct,Deci/DeciLM-7B-instruct,THUDM/chatglm-6b,THUDM/chatglm2-6b,THUDM/chatglm3-6b,Skywork/Skywork-13B-base,LLM360/Amber,Cerebras/FLOR-6.3B,Qwen/Qwen1.5-0.5B-Chat,Qwen/Qwen1.5-1.8B-Chat,Qwen/Qwen1.5-4B-Chat,Qwen/Qwen1.5-7B-Chat,Qwen/Qwen1.5-14B-Chat,Qwen/Qwen1.5-32B-Chat,Qwen/Qwen1.5-72B-Chat,Qwen/Qwen1.5-110B-Chat,Qwen/Qwen1.5-MoE-A2.7B-Chat,LargeWorldModel/LWM-Text-1M,YerevaNN/YerevaNN-Grok-1,state-spaces/mamba-130m,state-spaces/mamba-370m,state-spaces/mamba-790m,state-spaces/mamba-1.4b,state-spaces/mamba-2.8b,Snowflake/snowflake-arctic-instruct,Fugaku-LLM/Fugaku-LLM-13B-instruct,tiiuae/Falcon2-11B,01-ai/Yi-1.5-6B-Chat,01-ai/Yi-1.5-9B-Chat,01-ai/Yi-1.5-34B-Chat,deepseek-ai/DeepSeek-V2-Lite-Chat,deepseek-ai/DeepSeek-V2-Chat,deepseek-ai/DeepSeek-V3,deepseek-ai/DeepSeek-V3-0324,deepseek-ai/DeepSeek-V3.1,deepseek-ai/DeepSeek-V3.2,deepseek-ai/DeepSeek-R1-0528,microsoft/Phi-3-medium-128k-instruct,microsoft/Phi-3-mini-128k-instruct,microsoft/phi-4-reasoning,yulan-team/YuLan-Mini,AtlaAI/Selene-1-Mini-Llama-3.1-8B,bigcode/santacoder,Salesforce/codegen2-1B,Salesforce/codegen2-3_7B,Salesforce/codegen2-7B,HuggingFaceH4/starchat-alpha,replit/replit-code-v1-3b,Salesforce/codet5p-770m,Salesforce/codet5p-2b,Salesforce/codet5p-6b,Salesforce/codegen25-7b-multi,Deci/DeciCoder-1b,meta-llama/Llama-2-7b-chat-hf,meta-llama/Llama-2-13b-chat-hf,meta-llama/Llama-2-70b-chat-hf,meta-llama/Llama-3-8B-Instruct,meta-llama/Llama-3-70B-Instruct,meta-llama/Llama-4-Maverick-17B-128E-Instruct,meta-llama/Llama-4-Scout-17B-16E-Instruct,mistralai/Mistral-7B-Instruct-v0.2,mistralai/Mistral-Large-Instruct-2407,mistralai/Mistral-Large-Instruct-2411,Qwen/Qwen2-72B-Instruct,Qwen/Qwen3-235B-A22B-Instruct-2507,Qwen/Qwen3-235B-A22B-Thinking-2507,Qwen/Qwen3-VL-235B-A22B-Instruct,Qwen/Qwen3.5,Qwen/Qwen3.5-30B-A3B,Qwen/Qwen3.5-Coder,zai-org/GLM-4.5,zai-org/GLM-4.5-Air,zai-org/GLM-4.6,zai-org/GLM-5,moonshotai/Kimi-K2,moonshotai/Kimi-K2-Thinking,moonshotai/Kimi-K2.5,MiniMaxAI/MiniMax-M2.5,stepfun-ai/Step3,stepfun-ai/Step-3.5-Flash,XiaomiMiMo/MiMo-V2-Flash,google/gemma-4-4b-it,google/gemma-4-12b-it,google/gemma-4-27b-it,nvidia/Llama-3.1-Nemotron-Ultra-253B-v1,nvidia/Llama-3.1-Nemotron-Super-49B-v1,nvidia/Llama-3.1-Nemotron-Nano-8B-v1", "default,none,disabled,auto,low,medium,high,xhigh", "default"},
    PythonLlmProvider{"open-source", "Generic Open-Source / Remote", "local", "openai-chat-completions", "http://127.0.0.1:8000/v1", "Qwen/Qwen3-8B", "OPEN_SOURCE_LLM_API_KEY", "Qwen/Qwen3-0.6B,Qwen/Qwen3-1.7B,Qwen/Qwen3-4B,Qwen/Qwen3-8B,Qwen/Qwen3-14B,Qwen/Qwen3-32B,Qwen/Qwen3-30B-A3B,Qwen/Qwen2.5-0.5B-Instruct,Qwen/Qwen2.5-1.5B-Instruct,Qwen/Qwen2.5-3B-Instruct,Qwen/Qwen2.5-7B-Instruct,Qwen/Qwen2.5-14B-Instruct,Qwen/Qwen2.5-32B-Instruct,Qwen/Qwen2.5-72B-Instruct,Qwen/Qwen2.5-Coder-1.5B-Instruct,Qwen/Qwen2.5-Coder-7B-Instruct,Qwen/Qwen2.5-Coder-14B-Instruct,Qwen/Qwen2.5-Coder-32B-Instruct,Qwen/QwQ-32B,openai/gpt-oss-20b,openai/gpt-oss-120b,google-t5/t5-small,google-t5/t5-base,google-t5/t5-large,google/flan-t5-small,google/flan-t5-base,google/flan-t5-large,google/flan-t5-xl,google/flan-t5-xxl,RWKV/rwkv-4-world,RWKV/rwkv-5-world,RWKV/rwkv-6-world,BlinkDL/rwkv-7-world,EleutherAI/gpt-neox-20b,EleutherAI/gpt-j-6b,EleutherAI/gpt-neo-2.7B,yandex/yalm-100b,meta-llama/Llama-3.3-70B-Instruct,meta-llama/Llama-3.1-8B-Instruct,meta-llama/Llama-3.1-70B-Instruct,meta-llama/Llama-3.2-1B-Instruct,meta-llama/Llama-3.2-3B-Instruct,mistralai/Mistral-7B-Instruct-v0.3,mistralai/Mistral-Nemo-Instruct-2407,mistralai/Mixtral-8x7B-Instruct-v0.1,mistralai/Mixtral-8x22B-Instruct-v0.1,mistralai/Codestral-22B-v0.1,deepseek-ai/DeepSeek-R1,deepseek-ai/DeepSeek-R1-Distill-Qwen-1.5B,deepseek-ai/DeepSeek-R1-Distill-Qwen-7B,deepseek-ai/DeepSeek-R1-Distill-Qwen-14B,deepseek-ai/DeepSeek-R1-Distill-Qwen-32B,deepseek-ai/deepseek-coder-6.7b-instruct,deepseek-ai/DeepSeek-Coder-V2-Instruct,google/gemma-3-1b-it,google/gemma-3-4b-it,google/gemma-3-12b-it,google/gemma-3-27b-it,google/gemma-2-2b-it,google/gemma-2-9b-it,google/gemma-2-27b-it,microsoft/phi-4,microsoft/Phi-4-mini-instruct,microsoft/Phi-3.5-mini-instruct,tiiuae/Falcon3-1B-Instruct,tiiuae/Falcon3-3B-Instruct,tiiuae/Falcon3-7B-Instruct,tiiuae/Falcon3-10B-Instruct,tiiuae/falcon-180B-chat,01-ai/Yi-6B-Chat,01-ai/Yi-9B-Chat,01-ai/Yi-34B-Chat,THUDM/glm-4-9b-chat,internlm/internlm2_5-7b-chat,internlm/internlm2_5-20b-chat,baichuan-inc/Baichuan2-7B-Chat,baichuan-inc/Baichuan2-13B-Chat,openbmb/MiniCPM3-4B,HuggingFaceTB/SmolLM2-135M-Instruct,HuggingFaceTB/SmolLM2-360M-Instruct,HuggingFaceTB/SmolLM2-1.7B-Instruct,ibm-granite/granite-3.3-2b-instruct,ibm-granite/granite-3.3-8b-instruct,CohereForAI/c4ai-command-r-v01,CohereForAI/c4ai-command-r-plus,CohereForAI/aya-23-8B,CohereForAI/aya-23-35B,bigscience/bloomz-7b1,bigscience/bloom,mosaicml/mpt-7b-instruct,mosaicml/mpt-30b-instruct,databricks/dbrx-instruct,ai21labs/Jamba-v0.1,Nexusflow/Starling-LM-7B-beta,HuggingFaceH4/zephyr-7b-beta,NousResearch/Nous-Hermes-2-Mixtral-8x7B-DPO,openchat/openchat-3.5-0106,WizardLMTeam/WizardLM-2-8x22B,lmsys/vicuna-13b-v1.5,codellama/CodeLlama-7b-Instruct-hf,codellama/CodeLlama-13b-Instruct-hf,codellama/CodeLlama-34b-Instruct-hf,bigcode/starcoder2-3b,bigcode/starcoder2-7b,bigcode/starcoder2-15b,nvidia/Llama-3.1-Nemotron-70B-Instruct-HF,google/flan-ul2,allenai/OLMo-7B-Instruct,allenai/OLMo-2-1124-7B-Instruct,allenai/OLMo-2-1124-13B-Instruct,cerebras/Cerebras-GPT-111M,cerebras/Cerebras-GPT-256M,cerebras/Cerebras-GPT-590M,cerebras/Cerebras-GPT-1.3B,cerebras/Cerebras-GPT-2.7B,cerebras/Cerebras-GPT-6.7B,cerebras/Cerebras-GPT-13B,OpenAssistant/oasst-sft-4-pythia-12b-epoch-3.5,EleutherAI/pythia-70m,EleutherAI/pythia-160m,EleutherAI/pythia-410m,EleutherAI/pythia-1b,EleutherAI/pythia-1.4b,EleutherAI/pythia-2.8b,EleutherAI/pythia-6.9b,EleutherAI/pythia-12b,databricks/dolly-v2-3b,databricks/dolly-v2-7b,databricks/dolly-v2-12b,stabilityai/stablelm-base-alpha-3b,stabilityai/stablelm-base-alpha-7b,stabilityai/stablelm-tuned-alpha-3b,stabilityai/stablelm-tuned-alpha-7b,lmsys/fastchat-t5-3b-v1.0,aisquared/dlite-v2-1_5b,h2oai/h2ogpt-oasst1-512-12b,togethercomputer/RedPajama-INCITE-7B-Instruct,openlm-research/open_llama_3b,openlm-research/open_llama_7b,openlm-research/open_llama_13b,mosaicml/mpt-7b-chat,mosaicml/mpt-7b-storywriter,mosaicml/mpt-30b-chat,nomic-ai/gpt4all-j,Salesforce/xgen-7b-8k-inst,inceptionai/jais-13b-chat,codellama/CodeLlama-70b-Instruct-hf,teknium/OpenHermes-2.5-Mistral-7B,apple/OpenELM-270M-Instruct,apple/OpenELM-450M-Instruct,apple/OpenELM-1_1B-Instruct,apple/OpenELM-3B-Instruct,Deci/DeciLM-7B-instruct,THUDM/chatglm-6b,THUDM/chatglm2-6b,THUDM/chatglm3-6b,Skywork/Skywork-13B-base,LLM360/Amber,Cerebras/FLOR-6.3B,Qwen/Qwen1.5-0.5B-Chat,Qwen/Qwen1.5-1.8B-Chat,Qwen/Qwen1.5-4B-Chat,Qwen/Qwen1.5-7B-Chat,Qwen/Qwen1.5-14B-Chat,Qwen/Qwen1.5-32B-Chat,Qwen/Qwen1.5-72B-Chat,Qwen/Qwen1.5-110B-Chat,Qwen/Qwen1.5-MoE-A2.7B-Chat,LargeWorldModel/LWM-Text-1M,YerevaNN/YerevaNN-Grok-1,state-spaces/mamba-130m,state-spaces/mamba-370m,state-spaces/mamba-790m,state-spaces/mamba-1.4b,state-spaces/mamba-2.8b,Snowflake/snowflake-arctic-instruct,Fugaku-LLM/Fugaku-LLM-13B-instruct,tiiuae/Falcon2-11B,01-ai/Yi-1.5-6B-Chat,01-ai/Yi-1.5-9B-Chat,01-ai/Yi-1.5-34B-Chat,deepseek-ai/DeepSeek-V2-Lite-Chat,deepseek-ai/DeepSeek-V2-Chat,deepseek-ai/DeepSeek-V3,deepseek-ai/DeepSeek-V3-0324,deepseek-ai/DeepSeek-V3.1,deepseek-ai/DeepSeek-V3.2,deepseek-ai/DeepSeek-R1-0528,microsoft/Phi-3-medium-128k-instruct,microsoft/Phi-3-mini-128k-instruct,microsoft/phi-4-reasoning,yulan-team/YuLan-Mini,AtlaAI/Selene-1-Mini-Llama-3.1-8B,bigcode/santacoder,Salesforce/codegen2-1B,Salesforce/codegen2-3_7B,Salesforce/codegen2-7B,HuggingFaceH4/starchat-alpha,replit/replit-code-v1-3b,Salesforce/codet5p-770m,Salesforce/codet5p-2b,Salesforce/codet5p-6b,Salesforce/codegen25-7b-multi,Deci/DeciCoder-1b,meta-llama/Llama-2-7b-chat-hf,meta-llama/Llama-2-13b-chat-hf,meta-llama/Llama-2-70b-chat-hf,meta-llama/Llama-3-8B-Instruct,meta-llama/Llama-3-70B-Instruct,meta-llama/Llama-4-Maverick-17B-128E-Instruct,meta-llama/Llama-4-Scout-17B-16E-Instruct,mistralai/Mistral-7B-Instruct-v0.2,mistralai/Mistral-Large-Instruct-2407,mistralai/Mistral-Large-Instruct-2411,Qwen/Qwen2-72B-Instruct,Qwen/Qwen3-235B-A22B-Instruct-2507,Qwen/Qwen3-235B-A22B-Thinking-2507,Qwen/Qwen3-VL-235B-A22B-Instruct,Qwen/Qwen3.5,Qwen/Qwen3.5-30B-A3B,Qwen/Qwen3.5-Coder,zai-org/GLM-4.5,zai-org/GLM-4.5-Air,zai-org/GLM-4.6,zai-org/GLM-5,moonshotai/Kimi-K2,moonshotai/Kimi-K2-Thinking,moonshotai/Kimi-K2.5,MiniMaxAI/MiniMax-M2.5,stepfun-ai/Step3,stepfun-ai/Step-3.5-Flash,XiaomiMiMo/MiMo-V2-Flash,google/gemma-4-4b-it,google/gemma-4-12b-it,google/gemma-4-27b-it,nvidia/Llama-3.1-Nemotron-Ultra-253B-v1,nvidia/Llama-3.1-Nemotron-Super-49B-v1,nvidia/Llama-3.1-Nemotron-Nano-8B-v1,qwen3:0.6b,qwen3:1.7b,qwen3:4b,qwen3:8b,qwen3:14b,qwen3:30b-a3b,qwen3:32b,qwen3,qwen3-vl:8b,qwen3-vl:32b,qwen3.5,qwen2.5:0.5b,qwen2.5:1.5b,qwen2.5:3b,qwen2.5:7b,qwen2.5:14b,qwen2.5:32b,qwen2.5:72b,qwen2.5-coder:1.5b,qwen2.5-coder:7b,qwen2.5-coder:14b,qwen2.5-coder:32b,qwq:32b,gpt-oss:20b,gpt-oss:120b,gpt-oss:latest,llama4:maverick,llama4:scout,deepseek-v3,deepseek-v3.1,deepseek-v3.2,deepseek-r1:1.5b,deepseek-r1:7b,deepseek-r1:8b,deepseek-r1:14b,deepseek-r1:32b,deepseek-r1:70b,deepseek-coder-v2,llama3.3,llama3.1:8b,llama3.1:70b,llama3.2:1b,llama3.2:3b,llama3.2-vision:11b,llama3.2-vision:90b,mistral,mistral-nemo,mistral-small3.2,mixtral:8x7b,mixtral:8x22b,codestral,devstral,gemma3:1b,gemma3:4b,gemma3:12b,gemma3:27b,gemma4:27b,gemma2:2b,gemma2:9b,gemma2:27b,phi4,phi4-mini,phi3.5,phi3:mini,falcon3:1b,falcon3:3b,falcon3:7b,falcon3:10b,yi:6b,yi:9b,yi:34b,glm4,glm4.5,glm5,kimi-k2,minimax-m2,step3,mimo-v2,internlm2.5,baichuan2:7b,baichuan2:13b,minicpm-v,smollm2:135m,smollm2:360m,smollm2:1.7b,granite3.3:2b,granite3.3:8b,command-r,command-r-plus,starcoder2:3b,starcoder2:7b,starcoder2:15b,codellama:7b,codellama:13b,codellama:34b,dolphin-mixtral,openchat,neural-chat,orca-mini,zephyr,solar,nous-hermes2,wizardlm2,vicuna,rwkv,pythia,dolly-v2,stablelm,redpajama,openllama,mpt,dbrx,arctic,bloom,bloomz,mamba,custom-model", "default,none,disabled,auto,low,medium,high,xhigh", "default"},
};

inline constexpr std::array<std::string_view, 9> kPythonConnectorKeys = {
    "binance-sdk-derivatives-trading-usds-futures",
    "binance-sdk-derivatives-trading-coin-futures",
    "binance-sdk-spot",
    "binance-connector",
    "ccxt",
    "oanda-rest",
    "fxcmpy",
    "ig-rest",
    "python-binance",
};

struct PythonConnectorOption {
    std::string_view key;
    std::string_view label;
};

inline constexpr std::array<PythonConnectorOption, 9> kPythonConnectorOptions = {
    PythonConnectorOption{"binance-sdk-derivatives-trading-usds-futures", "Binance SDK Derivatives Trading USD\u24c8 Futures (Official Recommended)"},
    PythonConnectorOption{"binance-sdk-derivatives-trading-coin-futures", "Binance SDK Derivatives Trading COIN-M Futures"},
    PythonConnectorOption{"binance-sdk-spot", "Binance SDK Spot (Official Recommended)"},
    PythonConnectorOption{"binance-connector", "Binance Connector Python"},
    PythonConnectorOption{"ccxt", "CCXT (Unified)"},
    PythonConnectorOption{"oanda-rest", "OANDA REST-v20"},
    PythonConnectorOption{"fxcmpy", "FXCM fxcmpy"},
    PythonConnectorOption{"ig-rest", "IG REST Trading API"},
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

inline constexpr std::array<PythonUiOption, 11> kPythonExchangeOptions = {
    PythonUiOption{"Binance", "Binance", false},
    PythonUiOption{"Bybit", "Bybit (ccxt order routing)", false},
    PythonUiOption{"OKX", "OKX (ccxt order routing)", false},
    PythonUiOption{"Gate", "Gate (ccxt order routing)", false},
    PythonUiOption{"Bitget", "Bitget (ccxt order routing)", false},
    PythonUiOption{"MEXC", "MEXC (ccxt order routing)", false},
    PythonUiOption{"KuCoin", "KuCoin (ccxt order routing)", false},
    PythonUiOption{"HTX", "HTX (ccxt order routing)", false},
    PythonUiOption{"Crypto.com Exchange", "Crypto.com Exchange (ccxt order routing)", false},
    PythonUiOption{"Kraken", "Kraken (ccxt order routing)", false},
    PythonUiOption{"Bitfinex", "Bitfinex (ccxt order routing)", false},
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
