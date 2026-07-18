// This file is generated from Languages/Python/app/native_parity.py.
// Do not edit manually; run Languages/Python/tools/generate_native_parity_contracts.py.

#[rustfmt::skip]
mod generated {
    pub const PYTHON_SOURCE: &str = "Languages/Python";
    pub const PYTHON_SOURCE_SCHEMA_VERSION: u32 = 1;
    pub const PYTHON_SOURCE_CONTRACT_HASH: &str = "a7f05cb9c417a23449dc0b3c2bd392912fdb36ceebf77d1a697bdde6220c48d3";
    pub const CPP_CONTRACT_PARITY_READY: bool = true;
    pub const RUST_CONTRACT_PARITY_READY: bool = true;
    pub const CPP_STANDALONE_RUNTIME_READY: bool = false;
    pub const RUST_STANDALONE_RUNTIME_READY: bool = false;
    pub const CPP_FULL_PARITY_READY: bool = false;
    pub const RUST_FULL_PARITY_READY: bool = false;
    pub const PYTHON_ORDER_GUARD_BEHAVIOR_JSON: &str = "{\"live_only_requirements\":[\"credentials\",\"live_acknowledgement\",\"session_order_cap\",\"session_order_count_increment\"],\"validate_audit_enabled_all_modes\":true,\"validate_audit_writable_all_modes\":true,\"validate_connector_health_all_modes\":true,\"validate_exchange_filters_all_modes\":true,\"validate_intent_all_modes\":true}";
    pub const PYTHON_ORDER_GUARD_VALIDATE_INTENT_ALL_MODES: bool = true;
    pub const PYTHON_ORDER_GUARD_VALIDATE_EXCHANGE_FILTERS_ALL_MODES: bool = true;
    pub const PYTHON_ORDER_GUARD_VALIDATE_CONNECTOR_HEALTH_ALL_MODES: bool = true;
    pub const PYTHON_ORDER_GUARD_VALIDATE_AUDIT_ENABLED_ALL_MODES: bool = true;
    pub const PYTHON_ORDER_GUARD_VALIDATE_AUDIT_WRITABLE_ALL_MODES: bool = true;
    pub const PYTHON_ORDER_GUARD_LIVE_ONLY_REQUIREMENTS: &[&str] = &[
    "credentials",
    "live_acknowledgement",
    "session_order_cap",
    "session_order_count_increment",
];

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
        cpp_status: "Complete",
        rust_status: "Complete",
        required_before_full_parity: "C++: Complete | Rust: Complete",
        cpp_full_parity: true,
        rust_full_parity: true,
    },
    PythonParityDomain {
        key: "service_api_contract",
        title: "Service API contract",
        python_surface: "Canonical /api/v1 routes, methods, schemas, dashboard stream, auth, control-plane state, and desktop bridge contract.",
        cpp_status: "Complete",
        rust_status: "Complete",
        required_before_full_parity: "C++: Complete | Rust: Complete",
        cpp_full_parity: true,
        rust_full_parity: true,
    },
    PythonParityDomain {
        key: "config_persistence",
        title: "Config persistence and hydration",
        python_surface: "Runtime config, file save/load, dirty state, dashboard hydration, service snapshots, and secret redaction.",
        cpp_status: "Complete",
        rust_status: "Complete",
        required_before_full_parity: "C++: Complete | Rust: Complete",
        cpp_full_parity: true,
        rust_full_parity: true,
    },
    PythonParityDomain {
        key: "strategy_runtime",
        title: "Strategy runtime and signal generation",
        python_surface: "Indicator computation, strategy cycles, signal generation, live candle options, override tables, and worker lifecycle.",
        cpp_status: "Complete",
        rust_status: "Complete",
        required_before_full_parity: "C++: Complete | Rust: Complete",
        cpp_full_parity: true,
        rust_full_parity: true,
    },
    PythonParityDomain {
        key: "exchange_connectors",
        title: "Exchange connectors and market data",
        python_surface: "Binance SDK/connector/CCXT/python-binance selection, connector support metadata, transport diagnostics, rate limits, REST market data, and WebSocket paths.",
        cpp_status: "Complete",
        rust_status: "Complete",
        required_before_full_parity: "C++: Complete | Rust: Complete",
        cpp_full_parity: true,
        rust_full_parity: true,
    },
    PythonParityDomain {
        key: "account_portfolio_positions",
        title: "Account, portfolio, and positions",
        python_surface: "Account snapshots, portfolio summaries, futures position queries, close-all behavior, position history, allocation tracking, and reconciliation.",
        cpp_status: "Complete",
        rust_status: "Complete",
        required_before_full_parity: "C++: Complete | Rust: Complete",
        cpp_full_parity: true,
        rust_full_parity: true,
    },
    PythonParityDomain {
        key: "order_execution_and_risk",
        title: "Order execution, audit, and risk",
        python_surface: "Order sizing, submit guards, audit logs, position gates, close-opposite logic, stop-loss scopes, live safety preflight, circuit breaker, and shutdown guards.",
        cpp_status: "Complete",
        rust_status: "Complete",
        required_before_full_parity: "C++: Complete | Rust: Complete",
        cpp_full_parity: true,
        rust_full_parity: true,
    },
    PythonParityDomain {
        key: "backtest_engine",
        title: "Backtest engine, optimizer, and scanner",
        python_surface: "Backtest engine, optimizer limits/results, live parity request shape, scanner polling, dashboard import, indicator selection, and provenance.",
        cpp_status: "Complete",
        rust_status: "Complete",
        required_before_full_parity: "C++: Complete | Rust: Complete",
        cpp_full_parity: true,
        rust_full_parity: true,
    },
    PythonParityDomain {
        key: "charts_and_heatmaps",
        title: "Charts and liquidation heatmaps",
        python_surface: "TradingView, lightweight chart assets, candlestick fallback, chart state payloads, browser guards, and liquidation provider panels.",
        cpp_status: "Complete",
        rust_status: "Complete",
        required_before_full_parity: "C++: Complete | Rust: Complete",
        cpp_full_parity: true,
        rust_full_parity: true,
    },
    PythonParityDomain {
        key: "logs_terminal_diagnostics",
        title: "Logs, terminal, and diagnostics",
        python_surface: "Service logs, dashboard logs, terminal command execution, exception diagnostics, secret redaction, and test runner/reporting flows.",
        cpp_status: "Complete",
        rust_status: "Complete",
        required_before_full_parity: "C++: Complete | Rust: Complete",
        cpp_full_parity: true,
        rust_full_parity: true,
    },
    PythonParityDomain {
        key: "llm_advisory",
        title: "LLM advisory and local model lifecycle",
        python_surface: "Provider catalogs, privacy flags, advisory prompt execution, config persistence, local Ollama status/start/pull/delete, and redacted output.",
        cpp_status: "Complete",
        rust_status: "Complete",
        required_before_full_parity: "C++: Complete | Rust: Complete",
        cpp_full_parity: true,
        rust_full_parity: true,
    },
    PythonParityDomain {
        key: "startup_packaging_platform",
        title: "Startup, packaging, and platform integration",
        python_surface: "Product entrypoints, startup splash/suppression, Windows taskbar metadata, PyInstaller packaging, service wrappers, and release smoke tests.",
        cpp_status: "Complete",
        rust_status: "Complete",
        required_before_full_parity: "C++: Complete | Rust: Complete",
        cpp_full_parity: true,
        rust_full_parity: true,
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
        name: "metrics",
        path: "/api/v1/metrics",
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

    pub struct PythonServiceRouteSchema {
    pub name: &'static str,
    pub query_fields: &'static [&'static str],
    pub request_fields: &'static [&'static str],
    pub response_fields: &'static [&'static str],
}

pub const PYTHON_SERVICE_ROUTE_SCHEMAS: &[PythonServiceRouteSchema] = &[
    PythonServiceRouteSchema {
        name: "runtime",
        query_fields: &[],
        request_fields: &[],
        response_fields: &["service_name", "phase", "python_entrypoint", "desktop_entrypoint", "repo_root", "platform", "python_version", "capabilities", "control_plane", "notes"],
    },
    PythonServiceRouteSchema {
        name: "dashboard",
        query_fields: &["log_limit", "incident_limit"],
        request_fields: &[],
        response_fields: &["runtime", "status", "operational", "config", "config_summary", "execution", "backtest", "account", "portfolio", "logs", "service_api", "connector_order_circuit_incidents"],
    },
    PythonServiceRouteSchema {
        name: "status",
        query_fields: &[],
        request_fields: &[],
        response_fields: &["state", "lifecycle_phase", "requested_action", "close_positions_requested", "status_message", "last_transition_at", "service_mode", "generated_at", "api_enabled", "docker_required", "runtime_source", "active_engine_count", "account_type", "mode", "selected_exchange", "connector_backend", "connector_health", "exchange_connector", "operational_health", "operational", "notes"],
    },
    PythonServiceRouteSchema {
        name: "metrics",
        query_fields: &[],
        request_fields: &[],
        response_fields: &["generated_at", "operational_health", "connector_health", "connector_state", "runtime_active", "active_engine_count", "log_warning_count", "log_error_count", "connector_order_circuit_open", "unresolved_order_intent_count"],
    },
    PythonServiceRouteSchema {
        name: "execution",
        query_fields: &[],
        request_fields: &[],
        response_fields: &["executor_kind", "owner", "state", "workload_kind", "session_id", "requested_job_count", "active_engine_count", "progress_label", "progress_percent", "heartbeat_at", "tick_count", "last_action", "last_message", "started_at", "updated_at", "source", "notes"],
    },
    PythonServiceRouteSchema {
        name: "backtest",
        query_fields: &[],
        request_fields: &[],
        response_fields: &["session_id", "state", "workload_kind", "status_message", "symbols", "intervals", "indicator_keys", "logic", "symbol_source", "capital", "run_count", "error_count", "cancelled", "started_at", "completed_at", "updated_at", "source", "top_run", "runs", "top_runs", "errors"],
    },
    PythonServiceRouteSchema {
        name: "config_summary",
        query_fields: &[],
        request_fields: &[],
        response_fields: &["mode", "account_type", "connector_backend", "selected_exchange", "code_language", "theme", "design", "api_credentials_present", "symbol_count", "interval_count", "enabled_indicator_count", "runtime_pair_count", "backtest_pair_count", "llm_enabled", "llm_provider", "llm_mode", "llm_api_key_present"],
    },
    PythonServiceRouteSchema {
        name: "config",
        query_fields: &[],
        request_fields: &["config"],
        response_fields: &["mode", "account_type", "margin_mode", "position_mode", "side", "leverage", "position_pct", "connector_backend", "selected_exchange", "code_language", "theme", "design", "order_audit_max_bytes", "order_audit_backup_count", "connector_order_circuit_incident_log_max_bytes", "connector_order_circuit_incident_log_backup_count", "operational_connector_snapshot_stale_seconds", "operational_execution_heartbeat_stale_seconds", "operational_account_snapshot_stale_seconds", "operational_portfolio_snapshot_stale_seconds", "operational_live_start_gate_enabled", "operational_live_order_gate_enabled", "live_allow_auto_bump_to_min_order", "symbols", "intervals", "api_credentials_present", "llm", "exchange_support"],
    },
    PythonServiceRouteSchema {
        name: "config_persistence",
        query_fields: &[],
        request_fields: &[],
        response_fields: &["path", "exists", "modified_at", "kind", "format_version", "loaded", "dirty", "last_loaded_at", "last_saved_at", "migrated_from_format_version"],
    },
    PythonServiceRouteSchema {
        name: "config_save",
        query_fields: &[],
        request_fields: &["path", "source", "allow_unsafe_path"],
        response_fields: &["path", "exists", "modified_at", "kind", "format_version", "loaded", "dirty", "last_loaded_at", "last_saved_at", "migrated_from_format_version"],
    },
    PythonServiceRouteSchema {
        name: "config_load",
        query_fields: &[],
        request_fields: &["path", "source", "allow_unsafe_path"],
        response_fields: &["config", "persistence"],
    },
    PythonServiceRouteSchema {
        name: "runtime_state",
        query_fields: &[],
        request_fields: &["active", "active_engine_count", "source"],
        response_fields: &["state", "lifecycle_phase", "requested_action", "close_positions_requested", "status_message", "last_transition_at", "service_mode", "generated_at", "api_enabled", "docker_required", "runtime_source", "active_engine_count", "account_type", "mode", "selected_exchange", "connector_backend", "connector_health", "exchange_connector", "operational_health", "operational", "notes"],
    },
    PythonServiceRouteSchema {
        name: "operational_preflight",
        query_fields: &[],
        request_fields: &[],
        response_fields: &["state", "message", "mode", "live_mode", "generated_at", "start", "orders", "freshness", "critical_stale", "reasons"],
    },
    PythonServiceRouteSchema {
        name: "control_start",
        query_fields: &[],
        request_fields: &["requested_job_count", "source"],
        response_fields: &["accepted", "action", "lifecycle_phase", "runtime_active", "active_engine_count", "requested_job_count", "close_positions_requested", "source", "status_message", "generated_at"],
    },
    PythonServiceRouteSchema {
        name: "control_stop",
        query_fields: &[],
        request_fields: &["close_positions", "source"],
        response_fields: &["accepted", "action", "lifecycle_phase", "runtime_active", "active_engine_count", "requested_job_count", "close_positions_requested", "source", "status_message", "generated_at"],
    },
    PythonServiceRouteSchema {
        name: "control_start_failed",
        query_fields: &[],
        request_fields: &["reason", "source"],
        response_fields: &["accepted", "action", "lifecycle_phase", "runtime_active", "active_engine_count", "requested_job_count", "close_positions_requested", "source", "status_message", "generated_at"],
    },
    PythonServiceRouteSchema {
        name: "connector_order_circuit_breaker",
        query_fields: &[],
        request_fields: &["snapshot", "source", "force"],
        response_fields: &["active", "state", "reason", "message", "block_count", "block_threshold", "block_window_seconds", "source", "generated_at"],
    },
    PythonServiceRouteSchema {
        name: "connector_order_circuit_breaker_reset",
        query_fields: &[],
        request_fields: &["snapshot", "source", "force"],
        response_fields: &["active", "state", "source", "generated_at"],
    },
    PythonServiceRouteSchema {
        name: "connector_order_circuit_incidents",
        query_fields: &["limit"],
        request_fields: &[],
        response_fields: &["path", "path_source", "configured_path", "limit", "events", "parse_errors"],
    },
    PythonServiceRouteSchema {
        name: "backtest_run",
        query_fields: &[],
        request_fields: &["request", "source"],
        response_fields: &["accepted", "action", "session_id", "state", "status_message", "source"],
    },
    PythonServiceRouteSchema {
        name: "backtest_stop",
        query_fields: &[],
        request_fields: &["source"],
        response_fields: &["accepted", "action", "session_id", "state", "status_message", "source"],
    },
    PythonServiceRouteSchema {
        name: "account",
        query_fields: &[],
        request_fields: &["total_balance", "available_balance", "source"],
        response_fields: &["account_type", "mode", "selected_exchange", "connector_backend", "balance_currency", "total_balance", "available_balance", "source", "generated_at"],
    },
    PythonServiceRouteSchema {
        name: "portfolio",
        query_fields: &[],
        request_fields: &["open_position_records", "closed_position_records", "closed_trade_registry", "active_pnl", "active_margin", "closed_pnl", "closed_margin", "total_balance", "available_balance", "source"],
        response_fields: &["account_type", "open_position_count", "closed_position_count", "active_pnl", "active_margin", "closed_pnl", "closed_margin", "total_balance", "available_balance", "positions", "source", "generated_at"],
    },
    PythonServiceRouteSchema {
        name: "exchange_connector",
        query_fields: &[],
        request_fields: &["snapshot", "source"],
        response_fields: &["health", "state", "generated_at", "source", "selected_exchange", "connector_backend", "support", "rate_limit", "network", "last_error", "attention"],
    },
    PythonServiceRouteSchema {
        name: "logs",
        query_fields: &["limit"],
        request_fields: &["message", "source", "level"],
        response_fields: &["sequence_id", "level", "message", "source", "generated_at"],
    },
    PythonServiceRouteSchema {
        name: "terminal_run",
        query_fields: &[],
        request_fields: &["command", "source"],
        response_fields: &["command", "exit_code", "output", "source", "generated_at"],
    },
    PythonServiceRouteSchema {
        name: "llm_providers",
        query_fields: &[],
        request_fields: &[],
        response_fields: &["key", "label", "mode", "protocol", "default_base_url", "default_model", "api_key_env", "model_suggestions", "reasoning_efforts", "default_reasoning_effort"],
    },
    PythonServiceRouteSchema {
        name: "llm_config",
        query_fields: &[],
        request_fields: &["config"],
        response_fields: &["enabled", "provider", "provider_label", "mode", "protocol", "model", "base_url", "api_key_env", "api_key_present", "allow_public_network", "use_for", "reasoning_effort"],
    },
    PythonServiceRouteSchema {
        name: "llm_prompt",
        query_fields: &[],
        request_fields: &["prompt", "system_prompt", "dry_run", "source"],
        response_fields: &["provider", "model", "dry_run", "prompt", "system_prompt", "response", "source"],
    },
    PythonServiceRouteSchema {
        name: "llm_local_model_status",
        query_fields: &["base_url", "model"],
        request_fields: &[],
        response_fields: &["model", "base_url", "server_kind", "installed", "can_download", "can_start", "storage_hint", "storage_paths", "estimated_size_label"],
    },
    PythonServiceRouteSchema {
        name: "llm_local_model_start",
        query_fields: &[],
        request_fields: &["base_url", "model", "source"],
        response_fields: &["started", "server_kind", "executable", "error"],
    },
    PythonServiceRouteSchema {
        name: "llm_local_model_pull",
        query_fields: &[],
        request_fields: &["base_url", "model", "source"],
        response_fields: &["ok", "action", "model", "status"],
    },
    PythonServiceRouteSchema {
        name: "llm_local_model_delete",
        query_fields: &[],
        request_fields: &["base_url", "model", "source"],
        response_fields: &["ok", "action", "model", "status"],
    },
    PythonServiceRouteSchema {
        name: "stream_dashboard",
        query_fields: &["log_limit", "incident_limit", "interval_ms", "max_events"],
        request_fields: &[],
        response_fields: &["event", "data"],
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
    "optimizer_max_duration_seconds",
    "optimizer_metric",
    "optimizer_min_trades",
    "optimizer_mode",
    "pair_overrides",
    "position_mode",
    "position_pct",
    "position_pct_units",
    "queue_if_busy",
    "resume_checkpoint",
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
    pub runtime_config_json: &'static str,
    pub backtest_config_json: &'static str,
    pub runtime_output_keys: &'static [&'static str],
}

pub const PYTHON_INDICATOR_CATALOG: &[PythonIndicator] = &[
    PythonIndicator {
        key: "ma",
        display_name: "Moving Average (MA)",
        default_enabled: false,
        runtime_config_json: "{\"buy_value\":null,\"enabled\":false,\"length\":20,\"sell_value\":null,\"type\":\"SMA\"}",
        backtest_config_json: "{\"buy_value\":0,\"enabled\":false,\"length\":20,\"sell_value\":0,\"signal_mode\":\"price_cross\",\"type\":\"SMA\"}",
        runtime_output_keys: &["ma"],
    },
    PythonIndicator {
        key: "donchian",
        display_name: "Donchian Channels (DC)",
        default_enabled: false,
        runtime_config_json: "{\"buy_value\":null,\"enabled\":false,\"length\":20,\"sell_value\":null}",
        backtest_config_json: "{\"buy_value\":0,\"enabled\":false,\"length\":20,\"sell_value\":100,\"signal_mode\":\"band_position\"}",
        runtime_output_keys: &["donchian_high", "donchian_low", "donchian"],
    },
    PythonIndicator {
        key: "psar",
        display_name: "Parabolic SAR (PSAR)",
        default_enabled: false,
        runtime_config_json: "{\"af\":0.02,\"buy_value\":null,\"enabled\":false,\"max_af\":0.2,\"sell_value\":null}",
        backtest_config_json: "{\"af\":0.02,\"buy_value\":0,\"enabled\":false,\"max_af\":0.2,\"sell_value\":0,\"signal_mode\":\"price_cross\"}",
        runtime_output_keys: &["psar"],
    },
    PythonIndicator {
        key: "bb",
        display_name: "Bollinger Bands (BB)",
        default_enabled: false,
        runtime_config_json: "{\"buy_value\":null,\"enabled\":false,\"length\":20,\"sell_value\":null,\"std\":2}",
        backtest_config_json: "{\"buy_value\":0,\"enabled\":false,\"length\":20,\"sell_value\":100,\"signal_mode\":\"band_position\",\"std\":2}",
        runtime_output_keys: &["bb_upper", "bb_mid", "bb_lower"],
    },
    PythonIndicator {
        key: "bbw",
        display_name: "Bollinger Band Width (BBW)",
        default_enabled: false,
        runtime_config_json: "{\"buy_value\":null,\"enabled\":false,\"length\":20,\"sell_value\":null,\"std\":2}",
        backtest_config_json: "{\"buy_value\":5.0,\"enabled\":false,\"length\":20,\"sell_value\":2.0,\"std\":2}",
        runtime_output_keys: &["bbw"],
    },
    PythonIndicator {
        key: "keltner",
        display_name: "Keltner Channels (KC)",
        default_enabled: false,
        runtime_config_json: "{\"atr_length\":10,\"buy_value\":null,\"enabled\":false,\"length\":20,\"multiplier\":2.0,\"sell_value\":null}",
        backtest_config_json: "{\"atr_length\":10,\"buy_value\":0,\"enabled\":false,\"length\":20,\"multiplier\":2.0,\"sell_value\":100,\"signal_mode\":\"band_position\"}",
        runtime_output_keys: &["keltner_upper", "keltner_mid", "keltner_lower"],
    },
    PythonIndicator {
        key: "ichimoku",
        display_name: "Ichimoku Cloud (IC)",
        default_enabled: false,
        runtime_config_json: "{\"base_length\":26,\"buy_value\":null,\"conversion_length\":9,\"displacement\":26,\"enabled\":false,\"sell_value\":null,\"span_b_length\":52}",
        backtest_config_json: "{\"base_length\":26,\"buy_value\":0,\"conversion_length\":9,\"displacement\":26,\"enabled\":false,\"sell_value\":0,\"span_b_length\":52}",
        runtime_output_keys: &["ichimoku_tenkan", "ichimoku_kijun", "ichimoku_span_a", "ichimoku_span_b", "ichimoku_chikou", "ichimoku"],
    },
    PythonIndicator {
        key: "rsi",
        display_name: "Relative Strength Index (RSI)",
        default_enabled: true,
        runtime_config_json: "{\"buy_value\":null,\"enabled\":true,\"length\":14,\"sell_value\":null}",
        backtest_config_json: "{\"buy_value\":30,\"enabled\":true,\"length\":14,\"sell_value\":70}",
        runtime_output_keys: &["rsi"],
    },
    PythonIndicator {
        key: "volume",
        display_name: "Volume",
        default_enabled: false,
        runtime_config_json: "{\"buy_value\":null,\"enabled\":false,\"sell_value\":null}",
        backtest_config_json: "{\"buy_value\":1.0,\"enabled\":false,\"filter_operator\":\"gte\",\"length\":20,\"sell_value\":null,\"signal_mode\":\"relative_to_sma\",\"signal_role\":\"filter\"}",
        runtime_output_keys: &["volume"],
    },
    PythonIndicator {
        key: "obv",
        display_name: "On-Balance Volume (OBV)",
        default_enabled: false,
        runtime_config_json: "{\"buy_value\":null,\"enabled\":false,\"sell_value\":null}",
        backtest_config_json: "{\"buy_value\":0,\"enabled\":false,\"length\":3,\"sell_value\":0,\"signal_mode\":\"slope\"}",
        runtime_output_keys: &["obv"],
    },
    PythonIndicator {
        key: "rvol",
        display_name: "Relative Volume (RVOL)",
        default_enabled: false,
        runtime_config_json: "{\"buy_value\":null,\"enabled\":false,\"length\":20,\"sell_value\":null}",
        backtest_config_json: "{\"buy_value\":1.5,\"enabled\":false,\"length\":20,\"sell_value\":0.75}",
        runtime_output_keys: &["rvol"],
    },
    PythonIndicator {
        key: "cmf",
        display_name: "Chaikin Money Flow (CMF)",
        default_enabled: false,
        runtime_config_json: "{\"buy_value\":null,\"enabled\":false,\"length\":20,\"sell_value\":null}",
        backtest_config_json: "{\"buy_value\":0.05,\"enabled\":false,\"length\":20,\"sell_value\":-0.05}",
        runtime_output_keys: &["cmf"],
    },
    PythonIndicator {
        key: "cci",
        display_name: "Commodity Channel Index (CCI)",
        default_enabled: false,
        runtime_config_json: "{\"buy_value\":null,\"constant\":0.015,\"enabled\":false,\"length\":20,\"sell_value\":null}",
        backtest_config_json: "{\"buy_value\":-100,\"constant\":0.015,\"enabled\":false,\"length\":20,\"sell_value\":100}",
        runtime_output_keys: &["cci"],
    },
    PythonIndicator {
        key: "roc",
        display_name: "Rate of Change (ROC)",
        default_enabled: false,
        runtime_config_json: "{\"buy_value\":null,\"enabled\":false,\"length\":12,\"sell_value\":null}",
        backtest_config_json: "{\"buy_value\":0,\"enabled\":false,\"length\":12,\"sell_value\":0}",
        runtime_output_keys: &["roc"],
    },
    PythonIndicator {
        key: "trix",
        display_name: "Triple Exponential Average (TRIX)",
        default_enabled: false,
        runtime_config_json: "{\"buy_value\":null,\"enabled\":false,\"length\":15,\"sell_value\":null}",
        backtest_config_json: "{\"buy_value\":0,\"enabled\":false,\"length\":15,\"sell_value\":0}",
        runtime_output_keys: &["trix"],
    },
    PythonIndicator {
        key: "ppo",
        display_name: "Percentage Price Oscillator (PPO)",
        default_enabled: false,
        runtime_config_json: "{\"buy_value\":null,\"enabled\":false,\"fast\":12,\"sell_value\":null,\"signal\":9,\"slow\":26}",
        backtest_config_json: "{\"buy_value\":0,\"enabled\":false,\"fast\":12,\"sell_value\":0,\"signal\":9,\"slow\":26}",
        runtime_output_keys: &["ppo", "ppo_signal", "ppo_hist"],
    },
    PythonIndicator {
        key: "ao",
        display_name: "Awesome Oscillator (AO)",
        default_enabled: false,
        runtime_config_json: "{\"buy_value\":null,\"enabled\":false,\"fast\":5,\"sell_value\":null,\"slow\":34}",
        backtest_config_json: "{\"buy_value\":0,\"enabled\":false,\"fast\":5,\"sell_value\":0,\"slow\":34}",
        runtime_output_keys: &["ao"],
    },
    PythonIndicator {
        key: "kst",
        display_name: "Know Sure Thing (KST)",
        default_enabled: false,
        runtime_config_json: "{\"buy_value\":null,\"enabled\":false,\"roc1\":10,\"roc2\":15,\"roc3\":20,\"roc4\":30,\"sell_value\":null,\"signal\":9,\"sma1\":10,\"sma2\":10,\"sma3\":10,\"sma4\":15}",
        backtest_config_json: "{\"buy_value\":0,\"enabled\":false,\"roc1\":10,\"roc2\":15,\"roc3\":20,\"roc4\":30,\"sell_value\":0,\"signal\":9,\"sma1\":10,\"sma2\":10,\"sma3\":10,\"sma4\":15}",
        runtime_output_keys: &["kst", "kst_signal", "kst_hist"],
    },
    PythonIndicator {
        key: "aroon",
        display_name: "Aroon Oscillator (AROON)",
        default_enabled: false,
        runtime_config_json: "{\"buy_value\":null,\"enabled\":false,\"length\":25,\"sell_value\":null}",
        backtest_config_json: "{\"buy_value\":50,\"enabled\":false,\"length\":25,\"sell_value\":-50}",
        runtime_output_keys: &["aroon_up", "aroon_down", "aroon"],
    },
    PythonIndicator {
        key: "chop",
        display_name: "Choppiness Index (CHOP)",
        default_enabled: false,
        runtime_config_json: "{\"buy_value\":null,\"enabled\":false,\"length\":14,\"sell_value\":null}",
        backtest_config_json: "{\"buy_value\":38.2,\"enabled\":false,\"length\":14,\"sell_value\":61.8}",
        runtime_output_keys: &["chop"],
    },
    PythonIndicator {
        key: "atr",
        display_name: "Average True Range (ATR)",
        default_enabled: false,
        runtime_config_json: "{\"buy_value\":null,\"enabled\":false,\"length\":14,\"sell_value\":null}",
        backtest_config_json: "{\"buy_value\":1.0,\"enabled\":false,\"filter_operator\":\"gte\",\"length\":14,\"sell_value\":null,\"signal_mode\":\"percent_of_close\",\"signal_role\":\"filter\"}",
        runtime_output_keys: &["atr"],
    },
    PythonIndicator {
        key: "natr",
        display_name: "Normalized Average True Range (NATR)",
        default_enabled: false,
        runtime_config_json: "{\"buy_value\":null,\"enabled\":false,\"length\":14,\"sell_value\":null}",
        backtest_config_json: "{\"buy_value\":2.0,\"enabled\":false,\"length\":14,\"sell_value\":1.0}",
        runtime_output_keys: &["natr"],
    },
    PythonIndicator {
        key: "vwap",
        display_name: "Volume Weighted Average Price (VWAP)",
        default_enabled: false,
        runtime_config_json: "{\"buy_value\":null,\"enabled\":false,\"length\":20,\"sell_value\":null}",
        backtest_config_json: "{\"buy_value\":0,\"enabled\":false,\"length\":20,\"sell_value\":0,\"signal_mode\":\"price_cross\"}",
        runtime_output_keys: &["vwap"],
    },
    PythonIndicator {
        key: "mfi",
        display_name: "Money Flow Index (MFI)",
        default_enabled: false,
        runtime_config_json: "{\"buy_value\":null,\"enabled\":false,\"length\":14,\"sell_value\":null}",
        backtest_config_json: "{\"buy_value\":20,\"enabled\":false,\"length\":14,\"sell_value\":80}",
        runtime_output_keys: &["mfi"],
    },
    PythonIndicator {
        key: "stoch_rsi",
        display_name: "Stochastic RSI (SRSI)",
        default_enabled: false,
        runtime_config_json: "{\"buy_value\":null,\"enabled\":false,\"length\":14,\"sell_value\":null,\"smooth_d\":3,\"smooth_k\":3}",
        backtest_config_json: "{\"buy_value\":20,\"enabled\":false,\"length\":14,\"sell_value\":80,\"smooth_d\":3,\"smooth_k\":3}",
        runtime_output_keys: &["stoch_rsi", "stoch_rsi_k", "stoch_rsi_d"],
    },
    PythonIndicator {
        key: "willr",
        display_name: "Williams %R",
        default_enabled: false,
        runtime_config_json: "{\"buy_value\":null,\"enabled\":false,\"length\":14,\"sell_value\":null}",
        backtest_config_json: "{\"buy_value\":-80,\"enabled\":false,\"length\":14,\"sell_value\":-20}",
        runtime_output_keys: &["willr"],
    },
    PythonIndicator {
        key: "macd",
        display_name: "Moving Average Convergence/Divergence (MACD)",
        default_enabled: false,
        runtime_config_json: "{\"buy_value\":null,\"enabled\":false,\"fast\":12,\"sell_value\":null,\"signal\":9,\"slow\":26}",
        backtest_config_json: "{\"buy_value\":0,\"enabled\":false,\"fast\":12,\"sell_value\":0,\"signal\":9,\"slow\":26}",
        runtime_output_keys: &["macd_line", "macd_signal"],
    },
    PythonIndicator {
        key: "uo",
        display_name: "Ultimate Oscillator (UO)",
        default_enabled: false,
        runtime_config_json: "{\"buy_value\":null,\"enabled\":false,\"long\":28,\"medium\":14,\"sell_value\":null,\"short\":7}",
        backtest_config_json: "{\"buy_value\":30,\"enabled\":false,\"long\":28,\"medium\":14,\"sell_value\":70,\"short\":7}",
        runtime_output_keys: &["uo"],
    },
    PythonIndicator {
        key: "adx",
        display_name: "Average Directional Index (ADX)",
        default_enabled: false,
        runtime_config_json: "{\"buy_value\":null,\"enabled\":false,\"length\":14,\"sell_value\":null}",
        backtest_config_json: "{\"buy_value\":20,\"enabled\":false,\"filter_operator\":\"gte\",\"length\":14,\"sell_value\":null,\"signal_role\":\"filter\"}",
        runtime_output_keys: &["adx"],
    },
    PythonIndicator {
        key: "dmi",
        display_name: "Directional Movement Index (DMI)",
        default_enabled: false,
        runtime_config_json: "{\"buy_value\":null,\"enabled\":false,\"length\":14,\"sell_value\":null}",
        backtest_config_json: "{\"buy_value\":0,\"enabled\":false,\"length\":14,\"sell_value\":0}",
        runtime_output_keys: &["dmi_plus", "dmi_minus", "dmi"],
    },
    PythonIndicator {
        key: "supertrend",
        display_name: "SuperTrend (ST)",
        default_enabled: false,
        runtime_config_json: "{\"atr_period\":10,\"buy_value\":null,\"enabled\":false,\"multiplier\":3.0,\"sell_value\":null}",
        backtest_config_json: "{\"atr_period\":10,\"buy_value\":0,\"enabled\":false,\"multiplier\":3.0,\"sell_value\":0,\"signal_mode\":\"price_cross\"}",
        runtime_output_keys: &["supertrend"],
    },
    PythonIndicator {
        key: "ema",
        display_name: "Exponential Moving Average (EMA)",
        default_enabled: false,
        runtime_config_json: "{\"buy_value\":null,\"enabled\":false,\"length\":20,\"sell_value\":null}",
        backtest_config_json: "{\"buy_value\":0,\"enabled\":false,\"length\":20,\"sell_value\":0,\"signal_mode\":\"price_cross\"}",
        runtime_output_keys: &["ema"],
    },
    PythonIndicator {
        key: "stochastic",
        display_name: "Stochastic Oscillator",
        default_enabled: false,
        runtime_config_json: "{\"buy_value\":null,\"enabled\":false,\"length\":14,\"sell_value\":null,\"smooth_d\":3,\"smooth_k\":3}",
        backtest_config_json: "{\"buy_value\":20,\"enabled\":false,\"length\":14,\"sell_value\":80,\"smooth_d\":3,\"smooth_k\":3}",
        runtime_output_keys: &["stochastic", "stochastic_k", "stochastic_d"],
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
    "moonshot",
    "local",
    "ollama",
    "vllm",
    "llamacpp",
    "lmstudio",
    "tgi",
    "open-source",
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
        model_suggestions: &["gpt-5.6", "gpt-5.6-sol", "gpt-5.6-terra", "gpt-5.6-luna", "gpt-5.5", "gpt-5.5-2026-04-23", "gpt-5.5-pro", "gpt-5.5-pro-2026-04-23", "gpt-5.4", "gpt-5.4-2026-03-05", "gpt-5.4-pro", "gpt-5.4-pro-2026-03-05", "gpt-5.4-mini", "gpt-5.4-mini-2026-03-17", "gpt-5.4-nano", "gpt-5.4-nano-2026-03-17", "gpt-5.3-chat-latest", "gpt-5.3-codex", "gpt-5.2", "gpt-5.2-codex", "gpt-5.2-chat-latest", "gpt-5.2-pro", "gpt-5.1", "gpt-5-codex", "gpt-5-mini", "gpt-5-nano", "gpt-4.1", "gpt-4.1-mini", "gpt-4.1-nano"],
        reasoning_efforts: &["default", "none", "minimal", "low", "medium", "high", "xhigh", "max"],
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
        model_suggestions: &["qwen3.7-max", "qwen3.7-max-2026-06-08", "qwen3.7-max-2026-05-20", "qwen3.6-max-preview", "qwen3.6-plus", "qwen3.6-plus-2026-04-02", "qwen3.6-flash", "qwen3.6-flash-2026-04-16", "qwen3-max", "qwen3-max-2026-01-23", "qwen3-max-2025-09-23", "qwen3-max-preview", "qwen3.5-plus", "qwen3.5-plus-2026-02-15", "qwen3.5-flash", "qwen3.5-flash-2026-02-23", "qwen3-coder-plus", "qwen3-coder-flash", "qwen-plus-us", "qwen-flash-us"],
        reasoning_efforts: &["default", "disabled", "enabled", "low", "medium", "high", "max"],
        default_reasoning_effort: "default",
    },
    PythonLlmProvider {
        key: "moonshot",
        label: "Moonshot AI / Kimi",
        mode: "cloud",
        protocol: "openai-chat-completions",
        default_base_url: "https://api.moonshot.ai/v1",
        default_model: "kimi-k3",
        api_key_env: "MOONSHOT_API_KEY",
        model_suggestions: &["kimi-k3", "kimi-k2.7-code", "kimi-k2.7-code-highspeed", "kimi-k2.6", "kimi-k2.5"],
        reasoning_efforts: &["default", "disabled", "enabled", "max"],
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
        model_suggestions: &["qwen3:0.6b", "qwen3:1.7b", "qwen3:4b", "qwen3:8b", "qwen3:14b", "qwen3:30b-a3b", "qwen3:32b", "qwen3", "qwen3-vl:8b", "qwen3-vl:32b", "qwen3.5", "qwen2.5:0.5b", "qwen2.5:1.5b", "qwen2.5:3b", "qwen2.5:7b", "qwen2.5:14b", "qwen2.5:32b", "qwen2.5:72b", "qwen2.5-coder:1.5b", "qwen2.5-coder:7b", "qwen2.5-coder:14b", "qwen2.5-coder:32b", "qwq:32b", "gpt-oss:20b", "gpt-oss:120b", "gpt-oss:latest", "llama4:maverick", "llama4:scout", "deepseek-v3", "deepseek-v3.1", "deepseek-v3.2", "deepseek-r1:1.5b", "deepseek-r1:7b", "deepseek-r1:8b", "deepseek-r1:14b", "deepseek-r1:32b", "deepseek-r1:70b", "deepseek-coder-v2", "llama3.3", "llama3.1:8b", "llama3.1:70b", "llama3.2:1b", "llama3.2:3b", "llama3.2-vision:11b", "llama3.2-vision:90b", "mistral", "mistral-nemo", "mistral-small3.2", "mixtral:8x7b", "mixtral:8x22b", "codestral", "devstral", "gemma3:1b", "gemma3:4b", "gemma3:12b", "gemma3:27b", "gemma4:27b", "gemma2:2b", "gemma2:9b", "gemma2:27b", "phi4", "phi4-mini", "phi3.5", "phi3:mini", "falcon3:1b", "falcon3:3b", "falcon3:7b", "falcon3:10b", "yi:6b", "yi:9b", "yi:34b", "glm4", "glm4.5", "glm5", "kimi-k2", "minimax-m2", "step3", "mimo-v2", "internlm2.5", "baichuan2:7b", "baichuan2:13b", "minicpm-v", "smollm2:135m", "smollm2:360m", "smollm2:1.7b", "granite3.3:2b", "granite3.3:8b", "command-r", "command-r-plus", "starcoder2:3b", "starcoder2:7b", "starcoder2:15b", "codellama:7b", "codellama:13b", "codellama:34b", "dolphin-mixtral", "openchat", "neural-chat", "orca-mini", "zephyr", "solar", "nous-hermes2", "wizardlm2", "vicuna", "rwkv", "pythia", "dolly-v2", "stablelm", "redpajama", "openllama", "mpt", "dbrx", "arctic", "bloom", "bloomz", "mamba", "custom-model", "Qwen/Qwen3-0.6B", "Qwen/Qwen3-1.7B", "Qwen/Qwen3-4B", "Qwen/Qwen3-8B", "Qwen/Qwen3-14B", "Qwen/Qwen3-32B", "Qwen/Qwen3-30B-A3B", "Qwen/Qwen2.5-0.5B-Instruct", "Qwen/Qwen2.5-1.5B-Instruct", "Qwen/Qwen2.5-3B-Instruct", "Qwen/Qwen2.5-7B-Instruct", "Qwen/Qwen2.5-14B-Instruct", "Qwen/Qwen2.5-32B-Instruct", "Qwen/Qwen2.5-72B-Instruct", "Qwen/Qwen2.5-Coder-1.5B-Instruct", "Qwen/Qwen2.5-Coder-7B-Instruct", "Qwen/Qwen2.5-Coder-14B-Instruct", "Qwen/Qwen2.5-Coder-32B-Instruct", "Qwen/QwQ-32B", "openai/gpt-oss-20b", "openai/gpt-oss-120b", "google-t5/t5-small", "google-t5/t5-base", "google-t5/t5-large", "google/flan-t5-small", "google/flan-t5-base", "google/flan-t5-large", "google/flan-t5-xl", "google/flan-t5-xxl", "RWKV/rwkv-4-world", "RWKV/rwkv-5-world", "RWKV/rwkv-6-world", "BlinkDL/rwkv-7-world", "EleutherAI/gpt-neox-20b", "EleutherAI/gpt-j-6b", "EleutherAI/gpt-neo-2.7B", "yandex/yalm-100b", "meta-llama/Llama-3.3-70B-Instruct", "meta-llama/Llama-3.1-8B-Instruct", "meta-llama/Llama-3.1-70B-Instruct", "meta-llama/Llama-3.2-1B-Instruct", "meta-llama/Llama-3.2-3B-Instruct", "mistralai/Mistral-7B-Instruct-v0.3", "mistralai/Mistral-Nemo-Instruct-2407", "mistralai/Mixtral-8x7B-Instruct-v0.1", "mistralai/Mixtral-8x22B-Instruct-v0.1", "mistralai/Codestral-22B-v0.1", "deepseek-ai/DeepSeek-R1", "deepseek-ai/DeepSeek-R1-Distill-Qwen-1.5B", "deepseek-ai/DeepSeek-R1-Distill-Qwen-7B", "deepseek-ai/DeepSeek-R1-Distill-Qwen-14B", "deepseek-ai/DeepSeek-R1-Distill-Qwen-32B", "deepseek-ai/deepseek-coder-6.7b-instruct", "deepseek-ai/DeepSeek-Coder-V2-Instruct", "google/gemma-3-1b-it", "google/gemma-3-4b-it", "google/gemma-3-12b-it", "google/gemma-3-27b-it", "google/gemma-2-2b-it", "google/gemma-2-9b-it", "google/gemma-2-27b-it", "microsoft/phi-4", "microsoft/Phi-4-mini-instruct", "microsoft/Phi-3.5-mini-instruct", "tiiuae/Falcon3-1B-Instruct", "tiiuae/Falcon3-3B-Instruct", "tiiuae/Falcon3-7B-Instruct", "tiiuae/Falcon3-10B-Instruct", "tiiuae/falcon-180B-chat", "01-ai/Yi-6B-Chat", "01-ai/Yi-9B-Chat", "01-ai/Yi-34B-Chat", "THUDM/glm-4-9b-chat", "internlm/internlm2_5-7b-chat", "internlm/internlm2_5-20b-chat", "baichuan-inc/Baichuan2-7B-Chat", "baichuan-inc/Baichuan2-13B-Chat", "openbmb/MiniCPM3-4B", "HuggingFaceTB/SmolLM2-135M-Instruct", "HuggingFaceTB/SmolLM2-360M-Instruct", "HuggingFaceTB/SmolLM2-1.7B-Instruct", "ibm-granite/granite-3.3-2b-instruct", "ibm-granite/granite-3.3-8b-instruct", "CohereForAI/c4ai-command-r-v01", "CohereForAI/c4ai-command-r-plus", "CohereForAI/aya-23-8B", "CohereForAI/aya-23-35B", "bigscience/bloomz-7b1", "bigscience/bloom", "mosaicml/mpt-7b-instruct", "mosaicml/mpt-30b-instruct", "databricks/dbrx-instruct", "ai21labs/Jamba-v0.1", "Nexusflow/Starling-LM-7B-beta", "HuggingFaceH4/zephyr-7b-beta", "NousResearch/Nous-Hermes-2-Mixtral-8x7B-DPO", "openchat/openchat-3.5-0106", "WizardLMTeam/WizardLM-2-8x22B", "lmsys/vicuna-13b-v1.5", "codellama/CodeLlama-7b-Instruct-hf", "codellama/CodeLlama-13b-Instruct-hf", "codellama/CodeLlama-34b-Instruct-hf", "bigcode/starcoder2-3b", "bigcode/starcoder2-7b", "bigcode/starcoder2-15b", "nvidia/Llama-3.1-Nemotron-70B-Instruct-HF", "google/flan-ul2", "allenai/OLMo-7B-Instruct", "allenai/OLMo-2-1124-7B-Instruct", "allenai/OLMo-2-1124-13B-Instruct", "cerebras/Cerebras-GPT-111M", "cerebras/Cerebras-GPT-256M", "cerebras/Cerebras-GPT-590M", "cerebras/Cerebras-GPT-1.3B", "cerebras/Cerebras-GPT-2.7B", "cerebras/Cerebras-GPT-6.7B", "cerebras/Cerebras-GPT-13B", "OpenAssistant/oasst-sft-4-pythia-12b-epoch-3.5", "EleutherAI/pythia-70m", "EleutherAI/pythia-160m", "EleutherAI/pythia-410m", "EleutherAI/pythia-1b", "EleutherAI/pythia-1.4b", "EleutherAI/pythia-2.8b", "EleutherAI/pythia-6.9b", "EleutherAI/pythia-12b", "databricks/dolly-v2-3b", "databricks/dolly-v2-7b", "databricks/dolly-v2-12b", "stabilityai/stablelm-base-alpha-3b", "stabilityai/stablelm-base-alpha-7b", "stabilityai/stablelm-tuned-alpha-3b", "stabilityai/stablelm-tuned-alpha-7b", "lmsys/fastchat-t5-3b-v1.0", "aisquared/dlite-v2-1_5b", "h2oai/h2ogpt-oasst1-512-12b", "togethercomputer/RedPajama-INCITE-7B-Instruct", "openlm-research/open_llama_3b", "openlm-research/open_llama_7b", "openlm-research/open_llama_13b", "mosaicml/mpt-7b-chat", "mosaicml/mpt-7b-storywriter", "mosaicml/mpt-30b-chat", "nomic-ai/gpt4all-j", "Salesforce/xgen-7b-8k-inst", "inceptionai/jais-13b-chat", "codellama/CodeLlama-70b-Instruct-hf", "teknium/OpenHermes-2.5-Mistral-7B", "apple/OpenELM-270M-Instruct", "apple/OpenELM-450M-Instruct", "apple/OpenELM-1_1B-Instruct", "apple/OpenELM-3B-Instruct", "Deci/DeciLM-7B-instruct", "THUDM/chatglm-6b", "THUDM/chatglm2-6b", "THUDM/chatglm3-6b", "Skywork/Skywork-13B-base", "LLM360/Amber", "Cerebras/FLOR-6.3B", "Qwen/Qwen1.5-0.5B-Chat", "Qwen/Qwen1.5-1.8B-Chat", "Qwen/Qwen1.5-4B-Chat", "Qwen/Qwen1.5-7B-Chat", "Qwen/Qwen1.5-14B-Chat", "Qwen/Qwen1.5-32B-Chat", "Qwen/Qwen1.5-72B-Chat", "Qwen/Qwen1.5-110B-Chat", "Qwen/Qwen1.5-MoE-A2.7B-Chat", "LargeWorldModel/LWM-Text-1M", "YerevaNN/YerevaNN-Grok-1", "state-spaces/mamba-130m", "state-spaces/mamba-370m", "state-spaces/mamba-790m", "state-spaces/mamba-1.4b", "state-spaces/mamba-2.8b", "Snowflake/snowflake-arctic-instruct", "Fugaku-LLM/Fugaku-LLM-13B-instruct", "tiiuae/Falcon2-11B", "01-ai/Yi-1.5-6B-Chat", "01-ai/Yi-1.5-9B-Chat", "01-ai/Yi-1.5-34B-Chat", "deepseek-ai/DeepSeek-V2-Lite-Chat", "deepseek-ai/DeepSeek-V2-Chat", "deepseek-ai/DeepSeek-V3", "deepseek-ai/DeepSeek-V3-0324", "deepseek-ai/DeepSeek-V3.1", "deepseek-ai/DeepSeek-V3.2", "deepseek-ai/DeepSeek-R1-0528", "microsoft/Phi-3-medium-128k-instruct", "microsoft/Phi-3-mini-128k-instruct", "microsoft/phi-4-reasoning", "yulan-team/YuLan-Mini", "AtlaAI/Selene-1-Mini-Llama-3.1-8B", "bigcode/santacoder", "Salesforce/codegen2-1B", "Salesforce/codegen2-3_7B", "Salesforce/codegen2-7B", "HuggingFaceH4/starchat-alpha", "replit/replit-code-v1-3b", "Salesforce/codet5p-770m", "Salesforce/codet5p-2b", "Salesforce/codet5p-6b", "Salesforce/codegen25-7b-multi", "Deci/DeciCoder-1b", "meta-llama/Llama-2-7b-chat-hf", "meta-llama/Llama-2-13b-chat-hf", "meta-llama/Llama-2-70b-chat-hf", "meta-llama/Llama-3-8B-Instruct", "meta-llama/Llama-3-70B-Instruct", "meta-llama/Llama-4-Maverick-17B-128E-Instruct", "meta-llama/Llama-4-Scout-17B-16E-Instruct", "mistralai/Mistral-7B-Instruct-v0.2", "mistralai/Mistral-Large-Instruct-2407", "mistralai/Mistral-Large-Instruct-2411", "Qwen/Qwen2-72B-Instruct", "Qwen/Qwen3-235B-A22B-Instruct-2507", "Qwen/Qwen3-235B-A22B-Thinking-2507", "Qwen/Qwen3-VL-235B-A22B-Instruct", "Qwen/Qwen3.5", "Qwen/Qwen3.5-30B-A3B", "Qwen/Qwen3.5-Coder", "zai-org/GLM-4.5", "zai-org/GLM-4.5-Air", "zai-org/GLM-4.6", "zai-org/GLM-5", "moonshotai/Kimi-K2", "moonshotai/Kimi-K2-Thinking", "moonshotai/Kimi-K2.5", "MiniMaxAI/MiniMax-M2.5", "stepfun-ai/Step3", "stepfun-ai/Step-3.5-Flash", "XiaomiMiMo/MiMo-V2-Flash", "google/gemma-4-4b-it", "google/gemma-4-12b-it", "google/gemma-4-27b-it", "nvidia/Llama-3.1-Nemotron-Ultra-253B-v1", "nvidia/Llama-3.1-Nemotron-Super-49B-v1", "nvidia/Llama-3.1-Nemotron-Nano-8B-v1"],
        reasoning_efforts: &["default", "none", "disabled", "auto", "low", "medium", "high", "xhigh"],
        default_reasoning_effort: "default",
    },
    PythonLlmProvider {
        key: "ollama",
        label: "Ollama",
        mode: "local",
        protocol: "openai-chat-completions",
        default_base_url: "http://127.0.0.1:11434/v1",
        default_model: "qwen3:8b",
        api_key_env: "OLLAMA_API_KEY",
        model_suggestions: &["qwen3:0.6b", "qwen3:1.7b", "qwen3:4b", "qwen3:8b", "qwen3:14b", "qwen3:30b-a3b", "qwen3:32b", "qwen3", "qwen3-vl:8b", "qwen3-vl:32b", "qwen3.5", "qwen2.5:0.5b", "qwen2.5:1.5b", "qwen2.5:3b", "qwen2.5:7b", "qwen2.5:14b", "qwen2.5:32b", "qwen2.5:72b", "qwen2.5-coder:1.5b", "qwen2.5-coder:7b", "qwen2.5-coder:14b", "qwen2.5-coder:32b", "qwq:32b", "gpt-oss:20b", "gpt-oss:120b", "gpt-oss:latest", "llama4:maverick", "llama4:scout", "deepseek-v3", "deepseek-v3.1", "deepseek-v3.2", "deepseek-r1:1.5b", "deepseek-r1:7b", "deepseek-r1:8b", "deepseek-r1:14b", "deepseek-r1:32b", "deepseek-r1:70b", "deepseek-coder-v2", "llama3.3", "llama3.1:8b", "llama3.1:70b", "llama3.2:1b", "llama3.2:3b", "llama3.2-vision:11b", "llama3.2-vision:90b", "mistral", "mistral-nemo", "mistral-small3.2", "mixtral:8x7b", "mixtral:8x22b", "codestral", "devstral", "gemma3:1b", "gemma3:4b", "gemma3:12b", "gemma3:27b", "gemma4:27b", "gemma2:2b", "gemma2:9b", "gemma2:27b", "phi4", "phi4-mini", "phi3.5", "phi3:mini", "falcon3:1b", "falcon3:3b", "falcon3:7b", "falcon3:10b", "yi:6b", "yi:9b", "yi:34b", "glm4", "glm4.5", "glm5", "kimi-k2", "minimax-m2", "step3", "mimo-v2", "internlm2.5", "baichuan2:7b", "baichuan2:13b", "minicpm-v", "smollm2:135m", "smollm2:360m", "smollm2:1.7b", "granite3.3:2b", "granite3.3:8b", "command-r", "command-r-plus", "starcoder2:3b", "starcoder2:7b", "starcoder2:15b", "codellama:7b", "codellama:13b", "codellama:34b", "dolphin-mixtral", "openchat", "neural-chat", "orca-mini", "zephyr", "solar", "nous-hermes2", "wizardlm2", "vicuna", "rwkv", "pythia", "dolly-v2", "stablelm", "redpajama", "openllama", "mpt", "dbrx", "arctic", "bloom", "bloomz", "mamba", "custom-model"],
        reasoning_efforts: &["default", "none", "disabled", "auto", "low", "medium", "high", "xhigh"],
        default_reasoning_effort: "default",
    },
    PythonLlmProvider {
        key: "vllm",
        label: "vLLM / SGLang",
        mode: "local",
        protocol: "openai-chat-completions",
        default_base_url: "http://127.0.0.1:8000/v1",
        default_model: "Qwen/Qwen3-8B",
        api_key_env: "VLLM_API_KEY",
        model_suggestions: &["Qwen/Qwen3-0.6B", "Qwen/Qwen3-1.7B", "Qwen/Qwen3-4B", "Qwen/Qwen3-8B", "Qwen/Qwen3-14B", "Qwen/Qwen3-32B", "Qwen/Qwen3-30B-A3B", "Qwen/Qwen2.5-0.5B-Instruct", "Qwen/Qwen2.5-1.5B-Instruct", "Qwen/Qwen2.5-3B-Instruct", "Qwen/Qwen2.5-7B-Instruct", "Qwen/Qwen2.5-14B-Instruct", "Qwen/Qwen2.5-32B-Instruct", "Qwen/Qwen2.5-72B-Instruct", "Qwen/Qwen2.5-Coder-1.5B-Instruct", "Qwen/Qwen2.5-Coder-7B-Instruct", "Qwen/Qwen2.5-Coder-14B-Instruct", "Qwen/Qwen2.5-Coder-32B-Instruct", "Qwen/QwQ-32B", "openai/gpt-oss-20b", "openai/gpt-oss-120b", "google-t5/t5-small", "google-t5/t5-base", "google-t5/t5-large", "google/flan-t5-small", "google/flan-t5-base", "google/flan-t5-large", "google/flan-t5-xl", "google/flan-t5-xxl", "RWKV/rwkv-4-world", "RWKV/rwkv-5-world", "RWKV/rwkv-6-world", "BlinkDL/rwkv-7-world", "EleutherAI/gpt-neox-20b", "EleutherAI/gpt-j-6b", "EleutherAI/gpt-neo-2.7B", "yandex/yalm-100b", "meta-llama/Llama-3.3-70B-Instruct", "meta-llama/Llama-3.1-8B-Instruct", "meta-llama/Llama-3.1-70B-Instruct", "meta-llama/Llama-3.2-1B-Instruct", "meta-llama/Llama-3.2-3B-Instruct", "mistralai/Mistral-7B-Instruct-v0.3", "mistralai/Mistral-Nemo-Instruct-2407", "mistralai/Mixtral-8x7B-Instruct-v0.1", "mistralai/Mixtral-8x22B-Instruct-v0.1", "mistralai/Codestral-22B-v0.1", "deepseek-ai/DeepSeek-R1", "deepseek-ai/DeepSeek-R1-Distill-Qwen-1.5B", "deepseek-ai/DeepSeek-R1-Distill-Qwen-7B", "deepseek-ai/DeepSeek-R1-Distill-Qwen-14B", "deepseek-ai/DeepSeek-R1-Distill-Qwen-32B", "deepseek-ai/deepseek-coder-6.7b-instruct", "deepseek-ai/DeepSeek-Coder-V2-Instruct", "google/gemma-3-1b-it", "google/gemma-3-4b-it", "google/gemma-3-12b-it", "google/gemma-3-27b-it", "google/gemma-2-2b-it", "google/gemma-2-9b-it", "google/gemma-2-27b-it", "microsoft/phi-4", "microsoft/Phi-4-mini-instruct", "microsoft/Phi-3.5-mini-instruct", "tiiuae/Falcon3-1B-Instruct", "tiiuae/Falcon3-3B-Instruct", "tiiuae/Falcon3-7B-Instruct", "tiiuae/Falcon3-10B-Instruct", "tiiuae/falcon-180B-chat", "01-ai/Yi-6B-Chat", "01-ai/Yi-9B-Chat", "01-ai/Yi-34B-Chat", "THUDM/glm-4-9b-chat", "internlm/internlm2_5-7b-chat", "internlm/internlm2_5-20b-chat", "baichuan-inc/Baichuan2-7B-Chat", "baichuan-inc/Baichuan2-13B-Chat", "openbmb/MiniCPM3-4B", "HuggingFaceTB/SmolLM2-135M-Instruct", "HuggingFaceTB/SmolLM2-360M-Instruct", "HuggingFaceTB/SmolLM2-1.7B-Instruct", "ibm-granite/granite-3.3-2b-instruct", "ibm-granite/granite-3.3-8b-instruct", "CohereForAI/c4ai-command-r-v01", "CohereForAI/c4ai-command-r-plus", "CohereForAI/aya-23-8B", "CohereForAI/aya-23-35B", "bigscience/bloomz-7b1", "bigscience/bloom", "mosaicml/mpt-7b-instruct", "mosaicml/mpt-30b-instruct", "databricks/dbrx-instruct", "ai21labs/Jamba-v0.1", "Nexusflow/Starling-LM-7B-beta", "HuggingFaceH4/zephyr-7b-beta", "NousResearch/Nous-Hermes-2-Mixtral-8x7B-DPO", "openchat/openchat-3.5-0106", "WizardLMTeam/WizardLM-2-8x22B", "lmsys/vicuna-13b-v1.5", "codellama/CodeLlama-7b-Instruct-hf", "codellama/CodeLlama-13b-Instruct-hf", "codellama/CodeLlama-34b-Instruct-hf", "bigcode/starcoder2-3b", "bigcode/starcoder2-7b", "bigcode/starcoder2-15b", "nvidia/Llama-3.1-Nemotron-70B-Instruct-HF", "google/flan-ul2", "allenai/OLMo-7B-Instruct", "allenai/OLMo-2-1124-7B-Instruct", "allenai/OLMo-2-1124-13B-Instruct", "cerebras/Cerebras-GPT-111M", "cerebras/Cerebras-GPT-256M", "cerebras/Cerebras-GPT-590M", "cerebras/Cerebras-GPT-1.3B", "cerebras/Cerebras-GPT-2.7B", "cerebras/Cerebras-GPT-6.7B", "cerebras/Cerebras-GPT-13B", "OpenAssistant/oasst-sft-4-pythia-12b-epoch-3.5", "EleutherAI/pythia-70m", "EleutherAI/pythia-160m", "EleutherAI/pythia-410m", "EleutherAI/pythia-1b", "EleutherAI/pythia-1.4b", "EleutherAI/pythia-2.8b", "EleutherAI/pythia-6.9b", "EleutherAI/pythia-12b", "databricks/dolly-v2-3b", "databricks/dolly-v2-7b", "databricks/dolly-v2-12b", "stabilityai/stablelm-base-alpha-3b", "stabilityai/stablelm-base-alpha-7b", "stabilityai/stablelm-tuned-alpha-3b", "stabilityai/stablelm-tuned-alpha-7b", "lmsys/fastchat-t5-3b-v1.0", "aisquared/dlite-v2-1_5b", "h2oai/h2ogpt-oasst1-512-12b", "togethercomputer/RedPajama-INCITE-7B-Instruct", "openlm-research/open_llama_3b", "openlm-research/open_llama_7b", "openlm-research/open_llama_13b", "mosaicml/mpt-7b-chat", "mosaicml/mpt-7b-storywriter", "mosaicml/mpt-30b-chat", "nomic-ai/gpt4all-j", "Salesforce/xgen-7b-8k-inst", "inceptionai/jais-13b-chat", "codellama/CodeLlama-70b-Instruct-hf", "teknium/OpenHermes-2.5-Mistral-7B", "apple/OpenELM-270M-Instruct", "apple/OpenELM-450M-Instruct", "apple/OpenELM-1_1B-Instruct", "apple/OpenELM-3B-Instruct", "Deci/DeciLM-7B-instruct", "THUDM/chatglm-6b", "THUDM/chatglm2-6b", "THUDM/chatglm3-6b", "Skywork/Skywork-13B-base", "LLM360/Amber", "Cerebras/FLOR-6.3B", "Qwen/Qwen1.5-0.5B-Chat", "Qwen/Qwen1.5-1.8B-Chat", "Qwen/Qwen1.5-4B-Chat", "Qwen/Qwen1.5-7B-Chat", "Qwen/Qwen1.5-14B-Chat", "Qwen/Qwen1.5-32B-Chat", "Qwen/Qwen1.5-72B-Chat", "Qwen/Qwen1.5-110B-Chat", "Qwen/Qwen1.5-MoE-A2.7B-Chat", "LargeWorldModel/LWM-Text-1M", "YerevaNN/YerevaNN-Grok-1", "state-spaces/mamba-130m", "state-spaces/mamba-370m", "state-spaces/mamba-790m", "state-spaces/mamba-1.4b", "state-spaces/mamba-2.8b", "Snowflake/snowflake-arctic-instruct", "Fugaku-LLM/Fugaku-LLM-13B-instruct", "tiiuae/Falcon2-11B", "01-ai/Yi-1.5-6B-Chat", "01-ai/Yi-1.5-9B-Chat", "01-ai/Yi-1.5-34B-Chat", "deepseek-ai/DeepSeek-V2-Lite-Chat", "deepseek-ai/DeepSeek-V2-Chat", "deepseek-ai/DeepSeek-V3", "deepseek-ai/DeepSeek-V3-0324", "deepseek-ai/DeepSeek-V3.1", "deepseek-ai/DeepSeek-V3.2", "deepseek-ai/DeepSeek-R1-0528", "microsoft/Phi-3-medium-128k-instruct", "microsoft/Phi-3-mini-128k-instruct", "microsoft/phi-4-reasoning", "yulan-team/YuLan-Mini", "AtlaAI/Selene-1-Mini-Llama-3.1-8B", "bigcode/santacoder", "Salesforce/codegen2-1B", "Salesforce/codegen2-3_7B", "Salesforce/codegen2-7B", "HuggingFaceH4/starchat-alpha", "replit/replit-code-v1-3b", "Salesforce/codet5p-770m", "Salesforce/codet5p-2b", "Salesforce/codet5p-6b", "Salesforce/codegen25-7b-multi", "Deci/DeciCoder-1b", "meta-llama/Llama-2-7b-chat-hf", "meta-llama/Llama-2-13b-chat-hf", "meta-llama/Llama-2-70b-chat-hf", "meta-llama/Llama-3-8B-Instruct", "meta-llama/Llama-3-70B-Instruct", "meta-llama/Llama-4-Maverick-17B-128E-Instruct", "meta-llama/Llama-4-Scout-17B-16E-Instruct", "mistralai/Mistral-7B-Instruct-v0.2", "mistralai/Mistral-Large-Instruct-2407", "mistralai/Mistral-Large-Instruct-2411", "Qwen/Qwen2-72B-Instruct", "Qwen/Qwen3-235B-A22B-Instruct-2507", "Qwen/Qwen3-235B-A22B-Thinking-2507", "Qwen/Qwen3-VL-235B-A22B-Instruct", "Qwen/Qwen3.5", "Qwen/Qwen3.5-30B-A3B", "Qwen/Qwen3.5-Coder", "zai-org/GLM-4.5", "zai-org/GLM-4.5-Air", "zai-org/GLM-4.6", "zai-org/GLM-5", "moonshotai/Kimi-K2", "moonshotai/Kimi-K2-Thinking", "moonshotai/Kimi-K2.5", "MiniMaxAI/MiniMax-M2.5", "stepfun-ai/Step3", "stepfun-ai/Step-3.5-Flash", "XiaomiMiMo/MiMo-V2-Flash", "google/gemma-4-4b-it", "google/gemma-4-12b-it", "google/gemma-4-27b-it", "nvidia/Llama-3.1-Nemotron-Ultra-253B-v1", "nvidia/Llama-3.1-Nemotron-Super-49B-v1", "nvidia/Llama-3.1-Nemotron-Nano-8B-v1"],
        reasoning_efforts: &["default", "none", "disabled", "auto", "low", "medium", "high", "xhigh"],
        default_reasoning_effort: "default",
    },
    PythonLlmProvider {
        key: "llamacpp",
        label: "llama.cpp server",
        mode: "local",
        protocol: "openai-chat-completions",
        default_base_url: "http://127.0.0.1:8080/v1",
        default_model: "local-model",
        api_key_env: "LLAMACPP_API_KEY",
        model_suggestions: &["local-model", "qwen3-8b-q4_k_m.gguf", "llama-3.1-8b-instruct-q4_k_m.gguf", "mistral-7b-instruct-q4_k_m.gguf", "gemma-3-4b-it-q4_k_m.gguf", "qwen3:0.6b", "qwen3:1.7b", "qwen3:4b", "qwen3:8b", "qwen3:14b", "qwen3:30b-a3b", "qwen3:32b", "qwen3", "qwen3-vl:8b", "qwen3-vl:32b", "qwen3.5", "qwen2.5:0.5b", "qwen2.5:1.5b", "qwen2.5:3b", "qwen2.5:7b", "qwen2.5:14b", "qwen2.5:32b", "qwen2.5:72b", "qwen2.5-coder:1.5b", "qwen2.5-coder:7b", "qwen2.5-coder:14b", "qwen2.5-coder:32b", "qwq:32b", "gpt-oss:20b", "gpt-oss:120b", "gpt-oss:latest", "llama4:maverick", "llama4:scout", "deepseek-v3", "deepseek-v3.1", "deepseek-v3.2", "deepseek-r1:1.5b", "deepseek-r1:7b", "deepseek-r1:8b", "deepseek-r1:14b", "deepseek-r1:32b", "deepseek-r1:70b", "deepseek-coder-v2", "llama3.3", "llama3.1:8b", "llama3.1:70b", "llama3.2:1b", "llama3.2:3b", "llama3.2-vision:11b", "llama3.2-vision:90b", "mistral", "mistral-nemo", "mistral-small3.2", "mixtral:8x7b", "mixtral:8x22b", "codestral", "devstral", "gemma3:1b", "gemma3:4b", "gemma3:12b", "gemma3:27b", "gemma4:27b", "gemma2:2b", "gemma2:9b", "gemma2:27b", "phi4", "phi4-mini", "phi3.5", "phi3:mini", "falcon3:1b", "falcon3:3b", "falcon3:7b", "falcon3:10b", "yi:6b", "yi:9b", "yi:34b", "glm4", "glm4.5", "glm5", "kimi-k2", "minimax-m2", "step3", "mimo-v2", "internlm2.5", "baichuan2:7b", "baichuan2:13b", "minicpm-v", "smollm2:135m", "smollm2:360m", "smollm2:1.7b", "granite3.3:2b", "granite3.3:8b", "command-r", "command-r-plus", "starcoder2:3b", "starcoder2:7b", "starcoder2:15b", "codellama:7b", "codellama:13b", "codellama:34b", "dolphin-mixtral", "openchat", "neural-chat", "orca-mini", "zephyr", "solar", "nous-hermes2", "wizardlm2", "vicuna", "rwkv", "pythia", "dolly-v2", "stablelm", "redpajama", "openllama", "mpt", "dbrx", "arctic", "bloom", "bloomz", "mamba", "custom-model", "google/flan-ul2", "allenai/OLMo-7B-Instruct", "allenai/OLMo-2-1124-7B-Instruct", "allenai/OLMo-2-1124-13B-Instruct", "cerebras/Cerebras-GPT-111M", "cerebras/Cerebras-GPT-256M", "cerebras/Cerebras-GPT-590M", "cerebras/Cerebras-GPT-1.3B", "cerebras/Cerebras-GPT-2.7B", "cerebras/Cerebras-GPT-6.7B", "cerebras/Cerebras-GPT-13B", "OpenAssistant/oasst-sft-4-pythia-12b-epoch-3.5", "EleutherAI/pythia-70m", "EleutherAI/pythia-160m", "EleutherAI/pythia-410m", "EleutherAI/pythia-1b", "EleutherAI/pythia-1.4b", "EleutherAI/pythia-2.8b", "EleutherAI/pythia-6.9b", "EleutherAI/pythia-12b", "databricks/dolly-v2-3b", "databricks/dolly-v2-7b", "databricks/dolly-v2-12b", "stabilityai/stablelm-base-alpha-3b", "stabilityai/stablelm-base-alpha-7b", "stabilityai/stablelm-tuned-alpha-3b", "stabilityai/stablelm-tuned-alpha-7b", "lmsys/fastchat-t5-3b-v1.0", "aisquared/dlite-v2-1_5b", "h2oai/h2ogpt-oasst1-512-12b", "togethercomputer/RedPajama-INCITE-7B-Instruct", "openlm-research/open_llama_3b", "openlm-research/open_llama_7b", "openlm-research/open_llama_13b", "mosaicml/mpt-7b-chat", "mosaicml/mpt-7b-storywriter", "mosaicml/mpt-30b-chat", "nomic-ai/gpt4all-j", "Salesforce/xgen-7b-8k-inst", "inceptionai/jais-13b-chat", "codellama/CodeLlama-70b-Instruct-hf", "teknium/OpenHermes-2.5-Mistral-7B", "apple/OpenELM-270M-Instruct", "apple/OpenELM-450M-Instruct", "apple/OpenELM-1_1B-Instruct", "apple/OpenELM-3B-Instruct", "Deci/DeciLM-7B-instruct", "THUDM/chatglm-6b", "THUDM/chatglm2-6b", "THUDM/chatglm3-6b", "THUDM/glm-4-9b-chat", "Skywork/Skywork-13B-base", "LLM360/Amber", "Cerebras/FLOR-6.3B", "Qwen/Qwen1.5-0.5B-Chat", "Qwen/Qwen1.5-1.8B-Chat", "Qwen/Qwen1.5-4B-Chat", "Qwen/Qwen1.5-7B-Chat", "Qwen/Qwen1.5-14B-Chat", "Qwen/Qwen1.5-32B-Chat", "Qwen/Qwen1.5-72B-Chat", "Qwen/Qwen1.5-110B-Chat", "Qwen/Qwen1.5-MoE-A2.7B-Chat", "LargeWorldModel/LWM-Text-1M", "YerevaNN/YerevaNN-Grok-1", "state-spaces/mamba-130m", "state-spaces/mamba-370m", "state-spaces/mamba-790m", "state-spaces/mamba-1.4b", "state-spaces/mamba-2.8b", "Snowflake/snowflake-arctic-instruct", "Fugaku-LLM/Fugaku-LLM-13B-instruct", "tiiuae/Falcon2-11B", "01-ai/Yi-1.5-6B-Chat", "01-ai/Yi-1.5-9B-Chat", "01-ai/Yi-1.5-34B-Chat", "deepseek-ai/DeepSeek-V2-Lite-Chat", "deepseek-ai/DeepSeek-V2-Chat", "deepseek-ai/DeepSeek-V3", "deepseek-ai/DeepSeek-V3-0324", "deepseek-ai/DeepSeek-V3.1", "deepseek-ai/DeepSeek-V3.2", "deepseek-ai/DeepSeek-R1-0528", "microsoft/Phi-3-medium-128k-instruct", "microsoft/Phi-3-mini-128k-instruct", "microsoft/phi-4-reasoning", "yulan-team/YuLan-Mini", "AtlaAI/Selene-1-Mini-Llama-3.1-8B", "bigcode/santacoder", "Salesforce/codegen2-1B", "Salesforce/codegen2-3_7B", "Salesforce/codegen2-7B", "HuggingFaceH4/starchat-alpha", "replit/replit-code-v1-3b", "Salesforce/codet5p-770m", "Salesforce/codet5p-2b", "Salesforce/codet5p-6b", "Salesforce/codegen25-7b-multi", "Deci/DeciCoder-1b", "meta-llama/Llama-2-7b-chat-hf", "meta-llama/Llama-2-13b-chat-hf", "meta-llama/Llama-2-70b-chat-hf", "meta-llama/Llama-3-8B-Instruct", "meta-llama/Llama-3-70B-Instruct", "meta-llama/Llama-4-Maverick-17B-128E-Instruct", "meta-llama/Llama-4-Scout-17B-16E-Instruct", "mistralai/Mistral-7B-Instruct-v0.2", "mistralai/Mistral-Large-Instruct-2407", "mistralai/Mistral-Large-Instruct-2411", "Qwen/Qwen2-72B-Instruct", "Qwen/Qwen3-235B-A22B-Instruct-2507", "Qwen/Qwen3-235B-A22B-Thinking-2507", "Qwen/Qwen3-VL-235B-A22B-Instruct", "Qwen/Qwen3.5", "Qwen/Qwen3.5-30B-A3B", "Qwen/Qwen3.5-Coder", "zai-org/GLM-4.5", "zai-org/GLM-4.5-Air", "zai-org/GLM-4.6", "zai-org/GLM-5", "moonshotai/Kimi-K2", "moonshotai/Kimi-K2-Thinking", "moonshotai/Kimi-K2.5", "MiniMaxAI/MiniMax-M2.5", "stepfun-ai/Step3", "stepfun-ai/Step-3.5-Flash", "XiaomiMiMo/MiMo-V2-Flash", "google/gemma-4-4b-it", "google/gemma-4-12b-it", "google/gemma-4-27b-it", "nvidia/Llama-3.1-Nemotron-Ultra-253B-v1", "nvidia/Llama-3.1-Nemotron-Super-49B-v1", "nvidia/Llama-3.1-Nemotron-Nano-8B-v1"],
        reasoning_efforts: &["default", "none", "disabled", "auto", "low", "medium", "high", "xhigh"],
        default_reasoning_effort: "default",
    },
    PythonLlmProvider {
        key: "lmstudio",
        label: "LM Studio",
        mode: "local",
        protocol: "openai-chat-completions",
        default_base_url: "http://127.0.0.1:1234/v1",
        default_model: "local-model",
        api_key_env: "LMSTUDIO_API_KEY",
        model_suggestions: &["local-model", "Qwen/Qwen3-0.6B", "Qwen/Qwen3-1.7B", "Qwen/Qwen3-4B", "Qwen/Qwen3-8B", "Qwen/Qwen3-14B", "Qwen/Qwen3-32B", "Qwen/Qwen3-30B-A3B", "Qwen/Qwen2.5-0.5B-Instruct", "Qwen/Qwen2.5-1.5B-Instruct", "Qwen/Qwen2.5-3B-Instruct", "Qwen/Qwen2.5-7B-Instruct", "Qwen/Qwen2.5-14B-Instruct", "Qwen/Qwen2.5-32B-Instruct", "Qwen/Qwen2.5-72B-Instruct", "Qwen/Qwen2.5-Coder-1.5B-Instruct", "Qwen/Qwen2.5-Coder-7B-Instruct", "Qwen/Qwen2.5-Coder-14B-Instruct", "Qwen/Qwen2.5-Coder-32B-Instruct", "Qwen/QwQ-32B", "openai/gpt-oss-20b", "openai/gpt-oss-120b", "google-t5/t5-small", "google-t5/t5-base", "google-t5/t5-large", "google/flan-t5-small", "google/flan-t5-base", "google/flan-t5-large", "google/flan-t5-xl", "google/flan-t5-xxl", "RWKV/rwkv-4-world", "RWKV/rwkv-5-world", "RWKV/rwkv-6-world", "BlinkDL/rwkv-7-world", "EleutherAI/gpt-neox-20b", "EleutherAI/gpt-j-6b", "EleutherAI/gpt-neo-2.7B", "yandex/yalm-100b", "meta-llama/Llama-3.3-70B-Instruct", "meta-llama/Llama-3.1-8B-Instruct", "meta-llama/Llama-3.1-70B-Instruct", "meta-llama/Llama-3.2-1B-Instruct", "meta-llama/Llama-3.2-3B-Instruct", "mistralai/Mistral-7B-Instruct-v0.3", "mistralai/Mistral-Nemo-Instruct-2407", "mistralai/Mixtral-8x7B-Instruct-v0.1", "mistralai/Mixtral-8x22B-Instruct-v0.1", "mistralai/Codestral-22B-v0.1", "deepseek-ai/DeepSeek-R1", "deepseek-ai/DeepSeek-R1-Distill-Qwen-1.5B", "deepseek-ai/DeepSeek-R1-Distill-Qwen-7B", "deepseek-ai/DeepSeek-R1-Distill-Qwen-14B", "deepseek-ai/DeepSeek-R1-Distill-Qwen-32B", "deepseek-ai/deepseek-coder-6.7b-instruct", "deepseek-ai/DeepSeek-Coder-V2-Instruct", "google/gemma-3-1b-it", "google/gemma-3-4b-it", "google/gemma-3-12b-it", "google/gemma-3-27b-it", "google/gemma-2-2b-it", "google/gemma-2-9b-it", "google/gemma-2-27b-it", "microsoft/phi-4", "microsoft/Phi-4-mini-instruct", "microsoft/Phi-3.5-mini-instruct", "tiiuae/Falcon3-1B-Instruct", "tiiuae/Falcon3-3B-Instruct", "tiiuae/Falcon3-7B-Instruct", "tiiuae/Falcon3-10B-Instruct", "tiiuae/falcon-180B-chat", "01-ai/Yi-6B-Chat", "01-ai/Yi-9B-Chat", "01-ai/Yi-34B-Chat", "THUDM/glm-4-9b-chat", "internlm/internlm2_5-7b-chat", "internlm/internlm2_5-20b-chat", "baichuan-inc/Baichuan2-7B-Chat", "baichuan-inc/Baichuan2-13B-Chat", "openbmb/MiniCPM3-4B", "HuggingFaceTB/SmolLM2-135M-Instruct", "HuggingFaceTB/SmolLM2-360M-Instruct", "HuggingFaceTB/SmolLM2-1.7B-Instruct", "ibm-granite/granite-3.3-2b-instruct", "ibm-granite/granite-3.3-8b-instruct", "CohereForAI/c4ai-command-r-v01", "CohereForAI/c4ai-command-r-plus", "CohereForAI/aya-23-8B", "CohereForAI/aya-23-35B", "bigscience/bloomz-7b1", "bigscience/bloom", "mosaicml/mpt-7b-instruct", "mosaicml/mpt-30b-instruct", "databricks/dbrx-instruct", "ai21labs/Jamba-v0.1", "Nexusflow/Starling-LM-7B-beta", "HuggingFaceH4/zephyr-7b-beta", "NousResearch/Nous-Hermes-2-Mixtral-8x7B-DPO", "openchat/openchat-3.5-0106", "WizardLMTeam/WizardLM-2-8x22B", "lmsys/vicuna-13b-v1.5", "codellama/CodeLlama-7b-Instruct-hf", "codellama/CodeLlama-13b-Instruct-hf", "codellama/CodeLlama-34b-Instruct-hf", "bigcode/starcoder2-3b", "bigcode/starcoder2-7b", "bigcode/starcoder2-15b", "nvidia/Llama-3.1-Nemotron-70B-Instruct-HF", "google/flan-ul2", "allenai/OLMo-7B-Instruct", "allenai/OLMo-2-1124-7B-Instruct", "allenai/OLMo-2-1124-13B-Instruct", "cerebras/Cerebras-GPT-111M", "cerebras/Cerebras-GPT-256M", "cerebras/Cerebras-GPT-590M", "cerebras/Cerebras-GPT-1.3B", "cerebras/Cerebras-GPT-2.7B", "cerebras/Cerebras-GPT-6.7B", "cerebras/Cerebras-GPT-13B", "OpenAssistant/oasst-sft-4-pythia-12b-epoch-3.5", "EleutherAI/pythia-70m", "EleutherAI/pythia-160m", "EleutherAI/pythia-410m", "EleutherAI/pythia-1b", "EleutherAI/pythia-1.4b", "EleutherAI/pythia-2.8b", "EleutherAI/pythia-6.9b", "EleutherAI/pythia-12b", "databricks/dolly-v2-3b", "databricks/dolly-v2-7b", "databricks/dolly-v2-12b", "stabilityai/stablelm-base-alpha-3b", "stabilityai/stablelm-base-alpha-7b", "stabilityai/stablelm-tuned-alpha-3b", "stabilityai/stablelm-tuned-alpha-7b", "lmsys/fastchat-t5-3b-v1.0", "aisquared/dlite-v2-1_5b", "h2oai/h2ogpt-oasst1-512-12b", "togethercomputer/RedPajama-INCITE-7B-Instruct", "openlm-research/open_llama_3b", "openlm-research/open_llama_7b", "openlm-research/open_llama_13b", "mosaicml/mpt-7b-chat", "mosaicml/mpt-7b-storywriter", "mosaicml/mpt-30b-chat", "nomic-ai/gpt4all-j", "Salesforce/xgen-7b-8k-inst", "inceptionai/jais-13b-chat", "codellama/CodeLlama-70b-Instruct-hf", "teknium/OpenHermes-2.5-Mistral-7B", "apple/OpenELM-270M-Instruct", "apple/OpenELM-450M-Instruct", "apple/OpenELM-1_1B-Instruct", "apple/OpenELM-3B-Instruct", "Deci/DeciLM-7B-instruct", "THUDM/chatglm-6b", "THUDM/chatglm2-6b", "THUDM/chatglm3-6b", "Skywork/Skywork-13B-base", "LLM360/Amber", "Cerebras/FLOR-6.3B", "Qwen/Qwen1.5-0.5B-Chat", "Qwen/Qwen1.5-1.8B-Chat", "Qwen/Qwen1.5-4B-Chat", "Qwen/Qwen1.5-7B-Chat", "Qwen/Qwen1.5-14B-Chat", "Qwen/Qwen1.5-32B-Chat", "Qwen/Qwen1.5-72B-Chat", "Qwen/Qwen1.5-110B-Chat", "Qwen/Qwen1.5-MoE-A2.7B-Chat", "LargeWorldModel/LWM-Text-1M", "YerevaNN/YerevaNN-Grok-1", "state-spaces/mamba-130m", "state-spaces/mamba-370m", "state-spaces/mamba-790m", "state-spaces/mamba-1.4b", "state-spaces/mamba-2.8b", "Snowflake/snowflake-arctic-instruct", "Fugaku-LLM/Fugaku-LLM-13B-instruct", "tiiuae/Falcon2-11B", "01-ai/Yi-1.5-6B-Chat", "01-ai/Yi-1.5-9B-Chat", "01-ai/Yi-1.5-34B-Chat", "deepseek-ai/DeepSeek-V2-Lite-Chat", "deepseek-ai/DeepSeek-V2-Chat", "deepseek-ai/DeepSeek-V3", "deepseek-ai/DeepSeek-V3-0324", "deepseek-ai/DeepSeek-V3.1", "deepseek-ai/DeepSeek-V3.2", "deepseek-ai/DeepSeek-R1-0528", "microsoft/Phi-3-medium-128k-instruct", "microsoft/Phi-3-mini-128k-instruct", "microsoft/phi-4-reasoning", "yulan-team/YuLan-Mini", "AtlaAI/Selene-1-Mini-Llama-3.1-8B", "bigcode/santacoder", "Salesforce/codegen2-1B", "Salesforce/codegen2-3_7B", "Salesforce/codegen2-7B", "HuggingFaceH4/starchat-alpha", "replit/replit-code-v1-3b", "Salesforce/codet5p-770m", "Salesforce/codet5p-2b", "Salesforce/codet5p-6b", "Salesforce/codegen25-7b-multi", "Deci/DeciCoder-1b", "meta-llama/Llama-2-7b-chat-hf", "meta-llama/Llama-2-13b-chat-hf", "meta-llama/Llama-2-70b-chat-hf", "meta-llama/Llama-3-8B-Instruct", "meta-llama/Llama-3-70B-Instruct", "meta-llama/Llama-4-Maverick-17B-128E-Instruct", "meta-llama/Llama-4-Scout-17B-16E-Instruct", "mistralai/Mistral-7B-Instruct-v0.2", "mistralai/Mistral-Large-Instruct-2407", "mistralai/Mistral-Large-Instruct-2411", "Qwen/Qwen2-72B-Instruct", "Qwen/Qwen3-235B-A22B-Instruct-2507", "Qwen/Qwen3-235B-A22B-Thinking-2507", "Qwen/Qwen3-VL-235B-A22B-Instruct", "Qwen/Qwen3.5", "Qwen/Qwen3.5-30B-A3B", "Qwen/Qwen3.5-Coder", "zai-org/GLM-4.5", "zai-org/GLM-4.5-Air", "zai-org/GLM-4.6", "zai-org/GLM-5", "moonshotai/Kimi-K2", "moonshotai/Kimi-K2-Thinking", "moonshotai/Kimi-K2.5", "MiniMaxAI/MiniMax-M2.5", "stepfun-ai/Step3", "stepfun-ai/Step-3.5-Flash", "XiaomiMiMo/MiMo-V2-Flash", "google/gemma-4-4b-it", "google/gemma-4-12b-it", "google/gemma-4-27b-it", "nvidia/Llama-3.1-Nemotron-Ultra-253B-v1", "nvidia/Llama-3.1-Nemotron-Super-49B-v1", "nvidia/Llama-3.1-Nemotron-Nano-8B-v1"],
        reasoning_efforts: &["default", "none", "disabled", "auto", "low", "medium", "high", "xhigh"],
        default_reasoning_effort: "default",
    },
    PythonLlmProvider {
        key: "tgi",
        label: "Hugging Face TGI",
        mode: "local",
        protocol: "openai-chat-completions",
        default_base_url: "http://127.0.0.1:3000/v1",
        default_model: "tgi",
        api_key_env: "HUGGINGFACE_API_KEY",
        model_suggestions: &["tgi", "Qwen/Qwen3-0.6B", "Qwen/Qwen3-1.7B", "Qwen/Qwen3-4B", "Qwen/Qwen3-8B", "Qwen/Qwen3-14B", "Qwen/Qwen3-32B", "Qwen/Qwen3-30B-A3B", "Qwen/Qwen2.5-0.5B-Instruct", "Qwen/Qwen2.5-1.5B-Instruct", "Qwen/Qwen2.5-3B-Instruct", "Qwen/Qwen2.5-7B-Instruct", "Qwen/Qwen2.5-14B-Instruct", "Qwen/Qwen2.5-32B-Instruct", "Qwen/Qwen2.5-72B-Instruct", "Qwen/Qwen2.5-Coder-1.5B-Instruct", "Qwen/Qwen2.5-Coder-7B-Instruct", "Qwen/Qwen2.5-Coder-14B-Instruct", "Qwen/Qwen2.5-Coder-32B-Instruct", "Qwen/QwQ-32B", "openai/gpt-oss-20b", "openai/gpt-oss-120b", "google-t5/t5-small", "google-t5/t5-base", "google-t5/t5-large", "google/flan-t5-small", "google/flan-t5-base", "google/flan-t5-large", "google/flan-t5-xl", "google/flan-t5-xxl", "RWKV/rwkv-4-world", "RWKV/rwkv-5-world", "RWKV/rwkv-6-world", "BlinkDL/rwkv-7-world", "EleutherAI/gpt-neox-20b", "EleutherAI/gpt-j-6b", "EleutherAI/gpt-neo-2.7B", "yandex/yalm-100b", "meta-llama/Llama-3.3-70B-Instruct", "meta-llama/Llama-3.1-8B-Instruct", "meta-llama/Llama-3.1-70B-Instruct", "meta-llama/Llama-3.2-1B-Instruct", "meta-llama/Llama-3.2-3B-Instruct", "mistralai/Mistral-7B-Instruct-v0.3", "mistralai/Mistral-Nemo-Instruct-2407", "mistralai/Mixtral-8x7B-Instruct-v0.1", "mistralai/Mixtral-8x22B-Instruct-v0.1", "mistralai/Codestral-22B-v0.1", "deepseek-ai/DeepSeek-R1", "deepseek-ai/DeepSeek-R1-Distill-Qwen-1.5B", "deepseek-ai/DeepSeek-R1-Distill-Qwen-7B", "deepseek-ai/DeepSeek-R1-Distill-Qwen-14B", "deepseek-ai/DeepSeek-R1-Distill-Qwen-32B", "deepseek-ai/deepseek-coder-6.7b-instruct", "deepseek-ai/DeepSeek-Coder-V2-Instruct", "google/gemma-3-1b-it", "google/gemma-3-4b-it", "google/gemma-3-12b-it", "google/gemma-3-27b-it", "google/gemma-2-2b-it", "google/gemma-2-9b-it", "google/gemma-2-27b-it", "microsoft/phi-4", "microsoft/Phi-4-mini-instruct", "microsoft/Phi-3.5-mini-instruct", "tiiuae/Falcon3-1B-Instruct", "tiiuae/Falcon3-3B-Instruct", "tiiuae/Falcon3-7B-Instruct", "tiiuae/Falcon3-10B-Instruct", "tiiuae/falcon-180B-chat", "01-ai/Yi-6B-Chat", "01-ai/Yi-9B-Chat", "01-ai/Yi-34B-Chat", "THUDM/glm-4-9b-chat", "internlm/internlm2_5-7b-chat", "internlm/internlm2_5-20b-chat", "baichuan-inc/Baichuan2-7B-Chat", "baichuan-inc/Baichuan2-13B-Chat", "openbmb/MiniCPM3-4B", "HuggingFaceTB/SmolLM2-135M-Instruct", "HuggingFaceTB/SmolLM2-360M-Instruct", "HuggingFaceTB/SmolLM2-1.7B-Instruct", "ibm-granite/granite-3.3-2b-instruct", "ibm-granite/granite-3.3-8b-instruct", "CohereForAI/c4ai-command-r-v01", "CohereForAI/c4ai-command-r-plus", "CohereForAI/aya-23-8B", "CohereForAI/aya-23-35B", "bigscience/bloomz-7b1", "bigscience/bloom", "mosaicml/mpt-7b-instruct", "mosaicml/mpt-30b-instruct", "databricks/dbrx-instruct", "ai21labs/Jamba-v0.1", "Nexusflow/Starling-LM-7B-beta", "HuggingFaceH4/zephyr-7b-beta", "NousResearch/Nous-Hermes-2-Mixtral-8x7B-DPO", "openchat/openchat-3.5-0106", "WizardLMTeam/WizardLM-2-8x22B", "lmsys/vicuna-13b-v1.5", "codellama/CodeLlama-7b-Instruct-hf", "codellama/CodeLlama-13b-Instruct-hf", "codellama/CodeLlama-34b-Instruct-hf", "bigcode/starcoder2-3b", "bigcode/starcoder2-7b", "bigcode/starcoder2-15b", "nvidia/Llama-3.1-Nemotron-70B-Instruct-HF", "google/flan-ul2", "allenai/OLMo-7B-Instruct", "allenai/OLMo-2-1124-7B-Instruct", "allenai/OLMo-2-1124-13B-Instruct", "cerebras/Cerebras-GPT-111M", "cerebras/Cerebras-GPT-256M", "cerebras/Cerebras-GPT-590M", "cerebras/Cerebras-GPT-1.3B", "cerebras/Cerebras-GPT-2.7B", "cerebras/Cerebras-GPT-6.7B", "cerebras/Cerebras-GPT-13B", "OpenAssistant/oasst-sft-4-pythia-12b-epoch-3.5", "EleutherAI/pythia-70m", "EleutherAI/pythia-160m", "EleutherAI/pythia-410m", "EleutherAI/pythia-1b", "EleutherAI/pythia-1.4b", "EleutherAI/pythia-2.8b", "EleutherAI/pythia-6.9b", "EleutherAI/pythia-12b", "databricks/dolly-v2-3b", "databricks/dolly-v2-7b", "databricks/dolly-v2-12b", "stabilityai/stablelm-base-alpha-3b", "stabilityai/stablelm-base-alpha-7b", "stabilityai/stablelm-tuned-alpha-3b", "stabilityai/stablelm-tuned-alpha-7b", "lmsys/fastchat-t5-3b-v1.0", "aisquared/dlite-v2-1_5b", "h2oai/h2ogpt-oasst1-512-12b", "togethercomputer/RedPajama-INCITE-7B-Instruct", "openlm-research/open_llama_3b", "openlm-research/open_llama_7b", "openlm-research/open_llama_13b", "mosaicml/mpt-7b-chat", "mosaicml/mpt-7b-storywriter", "mosaicml/mpt-30b-chat", "nomic-ai/gpt4all-j", "Salesforce/xgen-7b-8k-inst", "inceptionai/jais-13b-chat", "codellama/CodeLlama-70b-Instruct-hf", "teknium/OpenHermes-2.5-Mistral-7B", "apple/OpenELM-270M-Instruct", "apple/OpenELM-450M-Instruct", "apple/OpenELM-1_1B-Instruct", "apple/OpenELM-3B-Instruct", "Deci/DeciLM-7B-instruct", "THUDM/chatglm-6b", "THUDM/chatglm2-6b", "THUDM/chatglm3-6b", "Skywork/Skywork-13B-base", "LLM360/Amber", "Cerebras/FLOR-6.3B", "Qwen/Qwen1.5-0.5B-Chat", "Qwen/Qwen1.5-1.8B-Chat", "Qwen/Qwen1.5-4B-Chat", "Qwen/Qwen1.5-7B-Chat", "Qwen/Qwen1.5-14B-Chat", "Qwen/Qwen1.5-32B-Chat", "Qwen/Qwen1.5-72B-Chat", "Qwen/Qwen1.5-110B-Chat", "Qwen/Qwen1.5-MoE-A2.7B-Chat", "LargeWorldModel/LWM-Text-1M", "YerevaNN/YerevaNN-Grok-1", "state-spaces/mamba-130m", "state-spaces/mamba-370m", "state-spaces/mamba-790m", "state-spaces/mamba-1.4b", "state-spaces/mamba-2.8b", "Snowflake/snowflake-arctic-instruct", "Fugaku-LLM/Fugaku-LLM-13B-instruct", "tiiuae/Falcon2-11B", "01-ai/Yi-1.5-6B-Chat", "01-ai/Yi-1.5-9B-Chat", "01-ai/Yi-1.5-34B-Chat", "deepseek-ai/DeepSeek-V2-Lite-Chat", "deepseek-ai/DeepSeek-V2-Chat", "deepseek-ai/DeepSeek-V3", "deepseek-ai/DeepSeek-V3-0324", "deepseek-ai/DeepSeek-V3.1", "deepseek-ai/DeepSeek-V3.2", "deepseek-ai/DeepSeek-R1-0528", "microsoft/Phi-3-medium-128k-instruct", "microsoft/Phi-3-mini-128k-instruct", "microsoft/phi-4-reasoning", "yulan-team/YuLan-Mini", "AtlaAI/Selene-1-Mini-Llama-3.1-8B", "bigcode/santacoder", "Salesforce/codegen2-1B", "Salesforce/codegen2-3_7B", "Salesforce/codegen2-7B", "HuggingFaceH4/starchat-alpha", "replit/replit-code-v1-3b", "Salesforce/codet5p-770m", "Salesforce/codet5p-2b", "Salesforce/codet5p-6b", "Salesforce/codegen25-7b-multi", "Deci/DeciCoder-1b", "meta-llama/Llama-2-7b-chat-hf", "meta-llama/Llama-2-13b-chat-hf", "meta-llama/Llama-2-70b-chat-hf", "meta-llama/Llama-3-8B-Instruct", "meta-llama/Llama-3-70B-Instruct", "meta-llama/Llama-4-Maverick-17B-128E-Instruct", "meta-llama/Llama-4-Scout-17B-16E-Instruct", "mistralai/Mistral-7B-Instruct-v0.2", "mistralai/Mistral-Large-Instruct-2407", "mistralai/Mistral-Large-Instruct-2411", "Qwen/Qwen2-72B-Instruct", "Qwen/Qwen3-235B-A22B-Instruct-2507", "Qwen/Qwen3-235B-A22B-Thinking-2507", "Qwen/Qwen3-VL-235B-A22B-Instruct", "Qwen/Qwen3.5", "Qwen/Qwen3.5-30B-A3B", "Qwen/Qwen3.5-Coder", "zai-org/GLM-4.5", "zai-org/GLM-4.5-Air", "zai-org/GLM-4.6", "zai-org/GLM-5", "moonshotai/Kimi-K2", "moonshotai/Kimi-K2-Thinking", "moonshotai/Kimi-K2.5", "MiniMaxAI/MiniMax-M2.5", "stepfun-ai/Step3", "stepfun-ai/Step-3.5-Flash", "XiaomiMiMo/MiMo-V2-Flash", "google/gemma-4-4b-it", "google/gemma-4-12b-it", "google/gemma-4-27b-it", "nvidia/Llama-3.1-Nemotron-Ultra-253B-v1", "nvidia/Llama-3.1-Nemotron-Super-49B-v1", "nvidia/Llama-3.1-Nemotron-Nano-8B-v1"],
        reasoning_efforts: &["default", "none", "disabled", "auto", "low", "medium", "high", "xhigh"],
        default_reasoning_effort: "default",
    },
    PythonLlmProvider {
        key: "open-source",
        label: "Generic Open-Source / Remote",
        mode: "local",
        protocol: "openai-chat-completions",
        default_base_url: "http://127.0.0.1:8000/v1",
        default_model: "Qwen/Qwen3-8B",
        api_key_env: "OPEN_SOURCE_LLM_API_KEY",
        model_suggestions: &["Qwen/Qwen3-0.6B", "Qwen/Qwen3-1.7B", "Qwen/Qwen3-4B", "Qwen/Qwen3-8B", "Qwen/Qwen3-14B", "Qwen/Qwen3-32B", "Qwen/Qwen3-30B-A3B", "Qwen/Qwen2.5-0.5B-Instruct", "Qwen/Qwen2.5-1.5B-Instruct", "Qwen/Qwen2.5-3B-Instruct", "Qwen/Qwen2.5-7B-Instruct", "Qwen/Qwen2.5-14B-Instruct", "Qwen/Qwen2.5-32B-Instruct", "Qwen/Qwen2.5-72B-Instruct", "Qwen/Qwen2.5-Coder-1.5B-Instruct", "Qwen/Qwen2.5-Coder-7B-Instruct", "Qwen/Qwen2.5-Coder-14B-Instruct", "Qwen/Qwen2.5-Coder-32B-Instruct", "Qwen/QwQ-32B", "openai/gpt-oss-20b", "openai/gpt-oss-120b", "google-t5/t5-small", "google-t5/t5-base", "google-t5/t5-large", "google/flan-t5-small", "google/flan-t5-base", "google/flan-t5-large", "google/flan-t5-xl", "google/flan-t5-xxl", "RWKV/rwkv-4-world", "RWKV/rwkv-5-world", "RWKV/rwkv-6-world", "BlinkDL/rwkv-7-world", "EleutherAI/gpt-neox-20b", "EleutherAI/gpt-j-6b", "EleutherAI/gpt-neo-2.7B", "yandex/yalm-100b", "meta-llama/Llama-3.3-70B-Instruct", "meta-llama/Llama-3.1-8B-Instruct", "meta-llama/Llama-3.1-70B-Instruct", "meta-llama/Llama-3.2-1B-Instruct", "meta-llama/Llama-3.2-3B-Instruct", "mistralai/Mistral-7B-Instruct-v0.3", "mistralai/Mistral-Nemo-Instruct-2407", "mistralai/Mixtral-8x7B-Instruct-v0.1", "mistralai/Mixtral-8x22B-Instruct-v0.1", "mistralai/Codestral-22B-v0.1", "deepseek-ai/DeepSeek-R1", "deepseek-ai/DeepSeek-R1-Distill-Qwen-1.5B", "deepseek-ai/DeepSeek-R1-Distill-Qwen-7B", "deepseek-ai/DeepSeek-R1-Distill-Qwen-14B", "deepseek-ai/DeepSeek-R1-Distill-Qwen-32B", "deepseek-ai/deepseek-coder-6.7b-instruct", "deepseek-ai/DeepSeek-Coder-V2-Instruct", "google/gemma-3-1b-it", "google/gemma-3-4b-it", "google/gemma-3-12b-it", "google/gemma-3-27b-it", "google/gemma-2-2b-it", "google/gemma-2-9b-it", "google/gemma-2-27b-it", "microsoft/phi-4", "microsoft/Phi-4-mini-instruct", "microsoft/Phi-3.5-mini-instruct", "tiiuae/Falcon3-1B-Instruct", "tiiuae/Falcon3-3B-Instruct", "tiiuae/Falcon3-7B-Instruct", "tiiuae/Falcon3-10B-Instruct", "tiiuae/falcon-180B-chat", "01-ai/Yi-6B-Chat", "01-ai/Yi-9B-Chat", "01-ai/Yi-34B-Chat", "THUDM/glm-4-9b-chat", "internlm/internlm2_5-7b-chat", "internlm/internlm2_5-20b-chat", "baichuan-inc/Baichuan2-7B-Chat", "baichuan-inc/Baichuan2-13B-Chat", "openbmb/MiniCPM3-4B", "HuggingFaceTB/SmolLM2-135M-Instruct", "HuggingFaceTB/SmolLM2-360M-Instruct", "HuggingFaceTB/SmolLM2-1.7B-Instruct", "ibm-granite/granite-3.3-2b-instruct", "ibm-granite/granite-3.3-8b-instruct", "CohereForAI/c4ai-command-r-v01", "CohereForAI/c4ai-command-r-plus", "CohereForAI/aya-23-8B", "CohereForAI/aya-23-35B", "bigscience/bloomz-7b1", "bigscience/bloom", "mosaicml/mpt-7b-instruct", "mosaicml/mpt-30b-instruct", "databricks/dbrx-instruct", "ai21labs/Jamba-v0.1", "Nexusflow/Starling-LM-7B-beta", "HuggingFaceH4/zephyr-7b-beta", "NousResearch/Nous-Hermes-2-Mixtral-8x7B-DPO", "openchat/openchat-3.5-0106", "WizardLMTeam/WizardLM-2-8x22B", "lmsys/vicuna-13b-v1.5", "codellama/CodeLlama-7b-Instruct-hf", "codellama/CodeLlama-13b-Instruct-hf", "codellama/CodeLlama-34b-Instruct-hf", "bigcode/starcoder2-3b", "bigcode/starcoder2-7b", "bigcode/starcoder2-15b", "nvidia/Llama-3.1-Nemotron-70B-Instruct-HF", "google/flan-ul2", "allenai/OLMo-7B-Instruct", "allenai/OLMo-2-1124-7B-Instruct", "allenai/OLMo-2-1124-13B-Instruct", "cerebras/Cerebras-GPT-111M", "cerebras/Cerebras-GPT-256M", "cerebras/Cerebras-GPT-590M", "cerebras/Cerebras-GPT-1.3B", "cerebras/Cerebras-GPT-2.7B", "cerebras/Cerebras-GPT-6.7B", "cerebras/Cerebras-GPT-13B", "OpenAssistant/oasst-sft-4-pythia-12b-epoch-3.5", "EleutherAI/pythia-70m", "EleutherAI/pythia-160m", "EleutherAI/pythia-410m", "EleutherAI/pythia-1b", "EleutherAI/pythia-1.4b", "EleutherAI/pythia-2.8b", "EleutherAI/pythia-6.9b", "EleutherAI/pythia-12b", "databricks/dolly-v2-3b", "databricks/dolly-v2-7b", "databricks/dolly-v2-12b", "stabilityai/stablelm-base-alpha-3b", "stabilityai/stablelm-base-alpha-7b", "stabilityai/stablelm-tuned-alpha-3b", "stabilityai/stablelm-tuned-alpha-7b", "lmsys/fastchat-t5-3b-v1.0", "aisquared/dlite-v2-1_5b", "h2oai/h2ogpt-oasst1-512-12b", "togethercomputer/RedPajama-INCITE-7B-Instruct", "openlm-research/open_llama_3b", "openlm-research/open_llama_7b", "openlm-research/open_llama_13b", "mosaicml/mpt-7b-chat", "mosaicml/mpt-7b-storywriter", "mosaicml/mpt-30b-chat", "nomic-ai/gpt4all-j", "Salesforce/xgen-7b-8k-inst", "inceptionai/jais-13b-chat", "codellama/CodeLlama-70b-Instruct-hf", "teknium/OpenHermes-2.5-Mistral-7B", "apple/OpenELM-270M-Instruct", "apple/OpenELM-450M-Instruct", "apple/OpenELM-1_1B-Instruct", "apple/OpenELM-3B-Instruct", "Deci/DeciLM-7B-instruct", "THUDM/chatglm-6b", "THUDM/chatglm2-6b", "THUDM/chatglm3-6b", "Skywork/Skywork-13B-base", "LLM360/Amber", "Cerebras/FLOR-6.3B", "Qwen/Qwen1.5-0.5B-Chat", "Qwen/Qwen1.5-1.8B-Chat", "Qwen/Qwen1.5-4B-Chat", "Qwen/Qwen1.5-7B-Chat", "Qwen/Qwen1.5-14B-Chat", "Qwen/Qwen1.5-32B-Chat", "Qwen/Qwen1.5-72B-Chat", "Qwen/Qwen1.5-110B-Chat", "Qwen/Qwen1.5-MoE-A2.7B-Chat", "LargeWorldModel/LWM-Text-1M", "YerevaNN/YerevaNN-Grok-1", "state-spaces/mamba-130m", "state-spaces/mamba-370m", "state-spaces/mamba-790m", "state-spaces/mamba-1.4b", "state-spaces/mamba-2.8b", "Snowflake/snowflake-arctic-instruct", "Fugaku-LLM/Fugaku-LLM-13B-instruct", "tiiuae/Falcon2-11B", "01-ai/Yi-1.5-6B-Chat", "01-ai/Yi-1.5-9B-Chat", "01-ai/Yi-1.5-34B-Chat", "deepseek-ai/DeepSeek-V2-Lite-Chat", "deepseek-ai/DeepSeek-V2-Chat", "deepseek-ai/DeepSeek-V3", "deepseek-ai/DeepSeek-V3-0324", "deepseek-ai/DeepSeek-V3.1", "deepseek-ai/DeepSeek-V3.2", "deepseek-ai/DeepSeek-R1-0528", "microsoft/Phi-3-medium-128k-instruct", "microsoft/Phi-3-mini-128k-instruct", "microsoft/phi-4-reasoning", "yulan-team/YuLan-Mini", "AtlaAI/Selene-1-Mini-Llama-3.1-8B", "bigcode/santacoder", "Salesforce/codegen2-1B", "Salesforce/codegen2-3_7B", "Salesforce/codegen2-7B", "HuggingFaceH4/starchat-alpha", "replit/replit-code-v1-3b", "Salesforce/codet5p-770m", "Salesforce/codet5p-2b", "Salesforce/codet5p-6b", "Salesforce/codegen25-7b-multi", "Deci/DeciCoder-1b", "meta-llama/Llama-2-7b-chat-hf", "meta-llama/Llama-2-13b-chat-hf", "meta-llama/Llama-2-70b-chat-hf", "meta-llama/Llama-3-8B-Instruct", "meta-llama/Llama-3-70B-Instruct", "meta-llama/Llama-4-Maverick-17B-128E-Instruct", "meta-llama/Llama-4-Scout-17B-16E-Instruct", "mistralai/Mistral-7B-Instruct-v0.2", "mistralai/Mistral-Large-Instruct-2407", "mistralai/Mistral-Large-Instruct-2411", "Qwen/Qwen2-72B-Instruct", "Qwen/Qwen3-235B-A22B-Instruct-2507", "Qwen/Qwen3-235B-A22B-Thinking-2507", "Qwen/Qwen3-VL-235B-A22B-Instruct", "Qwen/Qwen3.5", "Qwen/Qwen3.5-30B-A3B", "Qwen/Qwen3.5-Coder", "zai-org/GLM-4.5", "zai-org/GLM-4.5-Air", "zai-org/GLM-4.6", "zai-org/GLM-5", "moonshotai/Kimi-K2", "moonshotai/Kimi-K2-Thinking", "moonshotai/Kimi-K2.5", "MiniMaxAI/MiniMax-M2.5", "stepfun-ai/Step3", "stepfun-ai/Step-3.5-Flash", "XiaomiMiMo/MiMo-V2-Flash", "google/gemma-4-4b-it", "google/gemma-4-12b-it", "google/gemma-4-27b-it", "nvidia/Llama-3.1-Nemotron-Ultra-253B-v1", "nvidia/Llama-3.1-Nemotron-Super-49B-v1", "nvidia/Llama-3.1-Nemotron-Nano-8B-v1", "qwen3:0.6b", "qwen3:1.7b", "qwen3:4b", "qwen3:8b", "qwen3:14b", "qwen3:30b-a3b", "qwen3:32b", "qwen3", "qwen3-vl:8b", "qwen3-vl:32b", "qwen3.5", "qwen2.5:0.5b", "qwen2.5:1.5b", "qwen2.5:3b", "qwen2.5:7b", "qwen2.5:14b", "qwen2.5:32b", "qwen2.5:72b", "qwen2.5-coder:1.5b", "qwen2.5-coder:7b", "qwen2.5-coder:14b", "qwen2.5-coder:32b", "qwq:32b", "gpt-oss:20b", "gpt-oss:120b", "gpt-oss:latest", "llama4:maverick", "llama4:scout", "deepseek-v3", "deepseek-v3.1", "deepseek-v3.2", "deepseek-r1:1.5b", "deepseek-r1:7b", "deepseek-r1:8b", "deepseek-r1:14b", "deepseek-r1:32b", "deepseek-r1:70b", "deepseek-coder-v2", "llama3.3", "llama3.1:8b", "llama3.1:70b", "llama3.2:1b", "llama3.2:3b", "llama3.2-vision:11b", "llama3.2-vision:90b", "mistral", "mistral-nemo", "mistral-small3.2", "mixtral:8x7b", "mixtral:8x22b", "codestral", "devstral", "gemma3:1b", "gemma3:4b", "gemma3:12b", "gemma3:27b", "gemma4:27b", "gemma2:2b", "gemma2:9b", "gemma2:27b", "phi4", "phi4-mini", "phi3.5", "phi3:mini", "falcon3:1b", "falcon3:3b", "falcon3:7b", "falcon3:10b", "yi:6b", "yi:9b", "yi:34b", "glm4", "glm4.5", "glm5", "kimi-k2", "minimax-m2", "step3", "mimo-v2", "internlm2.5", "baichuan2:7b", "baichuan2:13b", "minicpm-v", "smollm2:135m", "smollm2:360m", "smollm2:1.7b", "granite3.3:2b", "granite3.3:8b", "command-r", "command-r-plus", "starcoder2:3b", "starcoder2:7b", "starcoder2:15b", "codellama:7b", "codellama:13b", "codellama:34b", "dolphin-mixtral", "openchat", "neural-chat", "orca-mini", "zephyr", "solar", "nous-hermes2", "wizardlm2", "vicuna", "rwkv", "pythia", "dolly-v2", "stablelm", "redpajama", "openllama", "mpt", "dbrx", "arctic", "bloom", "bloomz", "mamba", "custom-model"],
        reasoning_efforts: &["default", "none", "disabled", "auto", "low", "medium", "high", "xhigh"],
        default_reasoning_effort: "default",
    },
];

    pub const PYTHON_CONNECTOR_KEYS: &[&str] = &[
    "binance-sdk-derivatives-trading-usds-futures",
    "binance-sdk-derivatives-trading-coin-futures",
    "binance-sdk-spot",
    "binance-connector",
    "ccxt",
    "oanda-rest",
    "fxcmpy",
    "ig-rest",
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
        key: "oanda-rest",
        label: "OANDA REST-v20",
    },
    PythonConnectorOption {
        key: "fxcmpy",
        label: "FXCM fxcmpy",
    },
    PythonConnectorOption {
        key: "ig-rest",
        label: "IG REST Trading API",
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
        label: "Bybit (ccxt order routing)",
        disabled: false,
    },
    PythonUiOption {
        key: "OKX",
        label: "OKX (ccxt order routing)",
        disabled: false,
    },
    PythonUiOption {
        key: "Gate",
        label: "Gate (ccxt order routing)",
        disabled: false,
    },
    PythonUiOption {
        key: "Bitget",
        label: "Bitget (ccxt order routing)",
        disabled: false,
    },
    PythonUiOption {
        key: "MEXC",
        label: "MEXC (ccxt order routing)",
        disabled: false,
    },
    PythonUiOption {
        key: "KuCoin",
        label: "KuCoin (ccxt order routing)",
        disabled: false,
    },
    PythonUiOption {
        key: "HTX",
        label: "HTX (ccxt order routing)",
        disabled: false,
    },
    PythonUiOption {
        key: "Crypto.com Exchange",
        label: "Crypto.com Exchange (ccxt order routing)",
        disabled: false,
    },
    PythonUiOption {
        key: "Kraken",
        label: "Kraken (ccxt order routing)",
        disabled: false,
    },
    PythonUiOption {
        key: "Bitfinex",
        label: "Bitfinex (ccxt order routing)",
        disabled: false,
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

}

pub use generated::*;
