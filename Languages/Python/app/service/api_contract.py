"""
Canonical HTTP contract metadata for the service API.
"""

from __future__ import annotations

SERVICE_API_TITLE = "Trading Bot Service API"
SERVICE_API_DESCRIPTION = "Headless API surface for the Trading Bot service layer."
SERVICE_API_VERSION = "1.0.0"
SERVICE_API_MAJOR_LABEL = "v1"

SERVICE_ROOT_PATH = "/"
SERVICE_HEALTH_PATH = "/health"
SERVICE_UI_PATH = "/ui"
SERVICE_API_ROOT_PATH = SERVICE_ROOT_PATH
SERVICE_API_HEALTH_PATH = SERVICE_HEALTH_PATH
SERVICE_API_UI_PATH = SERVICE_UI_PATH

SERVICE_API_LEGACY_BASE_PATH = "/api"
SERVICE_API_BASE_PATH = f"{SERVICE_API_LEGACY_BASE_PATH}/{SERVICE_API_MAJOR_LABEL}"

SERVICE_API_ROUTE_SUFFIXES: dict[str, str] = {
    "runtime": "/runtime",
    "dashboard": "/dashboard",
    "status": "/status",
    "metrics": "/metrics",
    "execution": "/execution",
    "backtest": "/backtest",
    "config_summary": "/config-summary",
    "config": "/config",
    "config_persistence": "/config/persistence",
    "config_save": "/config/save",
    "config_load": "/config/load",
    "runtime_state": "/runtime/state",
    "operational_preflight": "/runtime/operational-preflight",
    "control_start": "/control/start",
    "control_stop": "/control/stop",
    "control_start_failed": "/control/start-failed",
    "connector_order_circuit_breaker": "/runtime/connector-order-circuit-breaker",
    "connector_order_circuit_breaker_reset": "/runtime/connector-order-circuit-breaker/reset",
    "connector_order_circuit_incidents": "/runtime/connector-order-circuit-breaker/incidents",
    "backtest_run": "/backtest/run",
    "backtest_stop": "/backtest/stop",
    "account": "/account",
    "portfolio": "/portfolio",
    "exchange_connector": "/exchange/connector",
    "logs": "/logs",
    "terminal_run": "/terminal/run",
    "llm_providers": "/llm/providers",
    "llm_config": "/llm/config",
    "llm_prompt": "/llm/prompt",
    "llm_local_model_status": "/llm/local-model/status",
    "llm_local_model_start": "/llm/local-model/start",
    "llm_local_model_pull": "/llm/local-model/pull",
    "llm_local_model_delete": "/llm/local-model/delete",
    "stream_dashboard": "/stream/dashboard",
}

SERVICE_API_ROUTE_METHODS: dict[str, tuple[str, ...]] = {
    "runtime": ("GET",),
    "dashboard": ("GET",),
    "status": ("GET",),
    "metrics": ("GET",),
    "execution": ("GET",),
    "backtest": ("GET",),
    "config_summary": ("GET",),
    "config": ("GET", "PUT", "PATCH"),
    "config_persistence": ("GET",),
    "config_save": ("POST",),
    "config_load": ("POST",),
    "runtime_state": ("PUT",),
    "operational_preflight": ("GET",),
    "control_start": ("POST",),
    "control_stop": ("POST",),
    "control_start_failed": ("POST",),
    "connector_order_circuit_breaker": ("GET", "PUT"),
    "connector_order_circuit_breaker_reset": ("POST",),
    "connector_order_circuit_incidents": ("GET",),
    "backtest_run": ("POST",),
    "backtest_stop": ("POST",),
    "account": ("GET", "PUT"),
    "portfolio": ("GET", "PUT"),
    "exchange_connector": ("GET", "PUT"),
    "logs": ("GET", "POST"),
    "terminal_run": ("POST",),
    "llm_providers": ("GET",),
    "llm_config": ("GET", "PATCH"),
    "llm_prompt": ("POST",),
    "llm_local_model_status": ("GET",),
    "llm_local_model_start": ("POST",),
    "llm_local_model_pull": ("POST",),
    "llm_local_model_delete": ("POST",),
    "stream_dashboard": ("GET",),
}

SERVICE_RUNTIME_RESPONSE_FIELDS: tuple[str, ...] = (
    "service_name",
    "phase",
    "python_entrypoint",
    "desktop_entrypoint",
    "repo_root",
    "platform",
    "python_version",
    "capabilities",
    "control_plane",
    "notes",
)

SERVICE_DASHBOARD_RESPONSE_FIELDS: tuple[str, ...] = (
    "runtime",
    "status",
    "operational",
    "config",
    "config_summary",
    "execution",
    "backtest",
    "account",
    "portfolio",
    "logs",
    "service_api",
    "connector_order_circuit_incidents",
)

SERVICE_STATUS_RESPONSE_FIELDS: tuple[str, ...] = (
    "state",
    "lifecycle_phase",
    "requested_action",
    "close_positions_requested",
    "status_message",
    "last_transition_at",
    "service_mode",
    "generated_at",
    "api_enabled",
    "docker_required",
    "runtime_source",
    "active_engine_count",
    "account_type",
    "mode",
    "selected_exchange",
    "connector_backend",
    "connector_health",
    "exchange_connector",
    "operational_health",
    "operational",
    "notes",
)

SERVICE_METRICS_RESPONSE_FIELDS: tuple[str, ...] = (
    "generated_at",
    "operational_health",
    "connector_health",
    "connector_state",
    "runtime_active",
    "active_engine_count",
    "log_warning_count",
    "log_error_count",
    "connector_order_circuit_open",
    "unresolved_order_intent_count",
)

SERVICE_EXECUTION_RESPONSE_FIELDS: tuple[str, ...] = (
    "executor_kind",
    "owner",
    "state",
    "workload_kind",
    "session_id",
    "requested_job_count",
    "active_engine_count",
    "progress_label",
    "progress_percent",
    "heartbeat_at",
    "tick_count",
    "last_action",
    "last_message",
    "started_at",
    "updated_at",
    "source",
    "notes",
)

SERVICE_BACKTEST_RESPONSE_FIELDS: tuple[str, ...] = (
    "session_id",
    "state",
    "workload_kind",
    "status_message",
    "symbols",
    "intervals",
    "indicator_keys",
    "logic",
    "symbol_source",
    "capital",
    "run_count",
    "error_count",
    "cancelled",
    "started_at",
    "completed_at",
    "updated_at",
    "source",
    "top_run",
    "runs",
    "top_runs",
    "errors",
)

SERVICE_CONFIG_RESPONSE_FIELDS: tuple[str, ...] = (
    "mode",
    "account_type",
    "margin_mode",
    "position_mode",
    "side",
    "leverage",
    "position_pct",
    "connector_backend",
    "selected_exchange",
    "code_language",
    "theme",
    "design",
    "order_audit_max_bytes",
    "order_audit_backup_count",
    "connector_order_circuit_incident_log_max_bytes",
    "connector_order_circuit_incident_log_backup_count",
    "operational_connector_snapshot_stale_seconds",
    "operational_execution_heartbeat_stale_seconds",
    "operational_account_snapshot_stale_seconds",
    "operational_portfolio_snapshot_stale_seconds",
    "operational_live_start_gate_enabled",
    "operational_live_order_gate_enabled",
    "live_allow_auto_bump_to_min_order",
    "symbols",
    "intervals",
    "api_credentials_present",
    "llm",
    "exchange_support",
)

SERVICE_CONFIG_SUMMARY_RESPONSE_FIELDS: tuple[str, ...] = (
    "mode",
    "account_type",
    "connector_backend",
    "selected_exchange",
    "code_language",
    "theme",
    "design",
    "api_credentials_present",
    "symbol_count",
    "interval_count",
    "enabled_indicator_count",
    "runtime_pair_count",
    "backtest_pair_count",
    "llm_enabled",
    "llm_provider",
    "llm_mode",
    "llm_api_key_present",
)

SERVICE_CONFIG_PERSISTENCE_RESPONSE_FIELDS: tuple[str, ...] = (
    "path",
    "exists",
    "modified_at",
    "kind",
    "format_version",
    "loaded",
    "dirty",
    "last_loaded_at",
    "last_saved_at",
    "migrated_from_format_version",
)

SERVICE_CONTROL_RESULT_RESPONSE_FIELDS: tuple[str, ...] = (
    "accepted",
    "action",
    "lifecycle_phase",
    "runtime_active",
    "active_engine_count",
    "requested_job_count",
    "close_positions_requested",
    "source",
    "status_message",
    "generated_at",
)

SERVICE_ACCOUNT_RESPONSE_FIELDS: tuple[str, ...] = (
    "account_type",
    "mode",
    "selected_exchange",
    "connector_backend",
    "balance_currency",
    "total_balance",
    "available_balance",
    "source",
    "generated_at",
)

SERVICE_PORTFOLIO_RESPONSE_FIELDS: tuple[str, ...] = (
    "account_type",
    "open_position_count",
    "closed_position_count",
    "active_pnl",
    "active_margin",
    "closed_pnl",
    "closed_margin",
    "total_balance",
    "available_balance",
    "positions",
    "source",
    "generated_at",
)

SERVICE_LOG_EVENT_RESPONSE_FIELDS: tuple[str, ...] = (
    "sequence_id",
    "level",
    "message",
    "source",
    "generated_at",
)

SERVICE_TERMINAL_RESPONSE_FIELDS: tuple[str, ...] = (
    "command",
    "exit_code",
    "output",
    "source",
    "generated_at",
)

SERVICE_LLM_LOCAL_MODEL_RESPONSE_FIELDS: tuple[str, ...] = (
    "model",
    "base_url",
    "server_kind",
    "installed",
    "can_download",
    "can_start",
    "storage_hint",
    "storage_paths",
    "estimated_size_label",
)

SERVICE_API_ROUTE_SCHEMAS: dict[str, dict[str, tuple[str, ...]]] = {
    "runtime": {
        "query_fields": (),
        "request_fields": (),
        "response_fields": SERVICE_RUNTIME_RESPONSE_FIELDS,
    },
    "dashboard": {
        "query_fields": ("log_limit", "incident_limit"),
        "request_fields": (),
        "response_fields": SERVICE_DASHBOARD_RESPONSE_FIELDS,
    },
    "status": {"query_fields": (), "request_fields": (), "response_fields": SERVICE_STATUS_RESPONSE_FIELDS},
    "metrics": {"query_fields": (), "request_fields": (), "response_fields": SERVICE_METRICS_RESPONSE_FIELDS},
    "execution": {"query_fields": (), "request_fields": (), "response_fields": SERVICE_EXECUTION_RESPONSE_FIELDS},
    "backtest": {"query_fields": (), "request_fields": (), "response_fields": SERVICE_BACKTEST_RESPONSE_FIELDS},
    "config_summary": {"query_fields": (), "request_fields": (), "response_fields": SERVICE_CONFIG_SUMMARY_RESPONSE_FIELDS},
    "config": {
        "query_fields": (),
        "request_fields": ("config",),
        "response_fields": SERVICE_CONFIG_RESPONSE_FIELDS,
    },
    "config_persistence": {
        "query_fields": (),
        "request_fields": (),
        "response_fields": SERVICE_CONFIG_PERSISTENCE_RESPONSE_FIELDS,
    },
    "config_save": {
        "query_fields": (),
        "request_fields": ("path", "source", "allow_unsafe_path"),
        "response_fields": SERVICE_CONFIG_PERSISTENCE_RESPONSE_FIELDS,
    },
    "config_load": {
        "query_fields": (),
        "request_fields": ("path", "source", "allow_unsafe_path"),
        "response_fields": ("config", "persistence"),
    },
    "runtime_state": {
        "query_fields": (),
        "request_fields": ("active", "active_engine_count", "source"),
        "response_fields": SERVICE_STATUS_RESPONSE_FIELDS,
    },
    "operational_preflight": {"query_fields": (), "request_fields": (), "response_fields": ("state", "message", "mode", "live_mode", "generated_at", "start", "orders", "freshness", "critical_stale", "reasons")},
    "control_start": {
        "query_fields": (),
        "request_fields": ("requested_job_count", "source"),
        "response_fields": SERVICE_CONTROL_RESULT_RESPONSE_FIELDS,
    },
    "control_stop": {
        "query_fields": (),
        "request_fields": ("close_positions", "source"),
        "response_fields": SERVICE_CONTROL_RESULT_RESPONSE_FIELDS,
    },
    "control_start_failed": {
        "query_fields": (),
        "request_fields": ("reason", "source"),
        "response_fields": SERVICE_CONTROL_RESULT_RESPONSE_FIELDS,
    },
    "connector_order_circuit_breaker": {
        "query_fields": (),
        "request_fields": ("snapshot", "source", "force"),
        "response_fields": ("active", "state", "reason", "message", "block_count", "block_threshold", "block_window_seconds", "source", "generated_at"),
    },
    "connector_order_circuit_breaker_reset": {
        "query_fields": (),
        "request_fields": ("snapshot", "source", "force"),
        "response_fields": ("active", "state", "source", "generated_at"),
    },
    "connector_order_circuit_incidents": {
        "query_fields": ("limit",),
        "request_fields": (),
        "response_fields": ("path", "path_source", "configured_path", "limit", "events", "parse_errors"),
    },
    "backtest_run": {
        "query_fields": (),
        "request_fields": ("request", "source"),
        "response_fields": ("accepted", "action", "session_id", "state", "status_message", "source"),
    },
    "backtest_stop": {
        "query_fields": (),
        "request_fields": ("source",),
        "response_fields": ("accepted", "action", "session_id", "state", "status_message", "source"),
    },
    "account": {
        "query_fields": (),
        "request_fields": ("total_balance", "available_balance", "source"),
        "response_fields": SERVICE_ACCOUNT_RESPONSE_FIELDS,
    },
    "portfolio": {
        "query_fields": (),
        "request_fields": (
            "open_position_records",
            "closed_position_records",
            "closed_trade_registry",
            "active_pnl",
            "active_margin",
            "closed_pnl",
            "closed_margin",
            "total_balance",
            "available_balance",
            "source",
        ),
        "response_fields": SERVICE_PORTFOLIO_RESPONSE_FIELDS,
    },
    "exchange_connector": {
        "query_fields": (),
        "request_fields": ("snapshot", "source"),
        "response_fields": ("health", "state", "generated_at", "source", "selected_exchange", "connector_backend", "support", "rate_limit", "network", "last_error", "attention"),
    },
    "logs": {
        "query_fields": ("limit",),
        "request_fields": ("message", "source", "level"),
        "response_fields": SERVICE_LOG_EVENT_RESPONSE_FIELDS,
    },
    "terminal_run": {
        "query_fields": (),
        "request_fields": ("command", "source"),
        "response_fields": SERVICE_TERMINAL_RESPONSE_FIELDS,
    },
    "llm_providers": {"query_fields": (), "request_fields": (), "response_fields": ("key", "label", "mode", "protocol", "default_base_url", "default_model", "api_key_env", "model_suggestions", "reasoning_efforts", "default_reasoning_effort")},
    "llm_config": {
        "query_fields": (),
        "request_fields": ("config",),
        "response_fields": ("enabled", "provider", "provider_label", "mode", "protocol", "model", "base_url", "api_key_env", "api_key_present", "allow_public_network", "use_for", "reasoning_effort"),
    },
    "llm_prompt": {
        "query_fields": (),
        "request_fields": ("prompt", "system_prompt", "dry_run", "source"),
        "response_fields": ("provider", "model", "dry_run", "prompt", "system_prompt", "response", "source"),
    },
    "llm_local_model_status": {
        "query_fields": ("base_url", "model"),
        "request_fields": (),
        "response_fields": SERVICE_LLM_LOCAL_MODEL_RESPONSE_FIELDS,
    },
    "llm_local_model_start": {
        "query_fields": (),
        "request_fields": ("base_url", "model", "source"),
        "response_fields": ("started", "server_kind", "executable", "error"),
    },
    "llm_local_model_pull": {
        "query_fields": (),
        "request_fields": ("base_url", "model", "source"),
        "response_fields": ("ok", "action", "model", "status"),
    },
    "llm_local_model_delete": {
        "query_fields": (),
        "request_fields": ("base_url", "model", "source"),
        "response_fields": ("ok", "action", "model", "status"),
    },
    "stream_dashboard": {
        "query_fields": ("log_limit", "incident_limit", "interval_ms", "max_events"),
        "request_fields": (),
        "response_fields": ("event", "data"),
    },
}

SERVICE_BACKTEST_RUN_REQUEST_FIELDS: tuple[str, ...] = (
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
)

SERVICE_API_DASHBOARD_ROUTE_NAMES: tuple[str, ...] = (
    "dashboard",
    "status",
    "stream_dashboard",
    "control_start",
    "control_stop",
    "runtime_state",
    "operational_preflight",
    "connector_order_circuit_breaker_reset",
    "config",
    "config_persistence",
    "config_save",
    "config_load",
    "backtest_run",
    "backtest_stop",
)

SERVICE_API_MOBILE_ROUTE_NAMES: tuple[str, ...] = (
    "dashboard",
    "llm_providers",
    "llm_config",
    "config_persistence",
    "config_save",
    "config_load",
    "operational_preflight",
    "control_start",
    "control_stop",
    "backtest_run",
    "terminal_run",
    "llm_prompt",
)


def _normalize_route_suffix(path: str) -> str:
    return "/" + str(path or "").strip().lstrip("/")


def service_api_path(path: str, *, versioned: bool = True) -> str:
    base_path = SERVICE_API_BASE_PATH if versioned else SERVICE_API_LEGACY_BASE_PATH
    return f"{base_path}{_normalize_route_suffix(path)}"


SERVICE_API_ROUTE_PATHS: dict[str, str] = {
    name: service_api_path(path, versioned=True)
    for name, path in SERVICE_API_ROUTE_SUFFIXES.items()
}

SERVICE_API_LEGACY_ROUTE_PATHS: dict[str, str] = {
    name: service_api_path(path, versioned=False)
    for name, path in SERVICE_API_ROUTE_SUFFIXES.items()
}


def service_api_route(name: str, *, versioned: bool = True) -> str:
    routes = SERVICE_API_ROUTE_PATHS if versioned else SERVICE_API_LEGACY_ROUTE_PATHS
    return routes[name]


SERVICE_API_STREAM_DASHBOARD_PATH = SERVICE_API_ROUTE_PATHS["stream_dashboard"]


def service_api_contract_payload() -> dict[str, object]:
    return {
        "title": SERVICE_API_TITLE,
        "description": SERVICE_API_DESCRIPTION,
        "version": SERVICE_API_VERSION,
        "major_label": SERVICE_API_MAJOR_LABEL,
        "root_path": SERVICE_ROOT_PATH,
        "health_path": SERVICE_HEALTH_PATH,
        "ui_path": SERVICE_UI_PATH,
        "legacy_base_path": SERVICE_API_LEGACY_BASE_PATH,
        "base_path": SERVICE_API_BASE_PATH,
        "stream_dashboard_path": SERVICE_API_STREAM_DASHBOARD_PATH,
        "route_suffixes": dict(SERVICE_API_ROUTE_SUFFIXES),
        "route_paths": dict(SERVICE_API_ROUTE_PATHS),
        "legacy_route_paths": dict(SERVICE_API_LEGACY_ROUTE_PATHS),
        "route_methods": {
            name: list(methods)
            for name, methods in SERVICE_API_ROUTE_METHODS.items()
        },
        "route_schemas": {
            name: {
                "query_fields": list(schema["query_fields"]),
                "request_fields": list(schema["request_fields"]),
                "response_fields": list(schema["response_fields"]),
            }
            for name, schema in SERVICE_API_ROUTE_SCHEMAS.items()
        },
        "dashboard_required_routes": list(SERVICE_API_DASHBOARD_ROUTE_NAMES),
        "mobile_required_routes": list(SERVICE_API_MOBILE_ROUTE_NAMES),
    }
