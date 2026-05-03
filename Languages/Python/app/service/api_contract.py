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
    "stream_dashboard": "/stream/dashboard",
}

SERVICE_API_ROUTE_METHODS: dict[str, tuple[str, ...]] = {
    "runtime": ("GET",),
    "dashboard": ("GET",),
    "status": ("GET",),
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
    "stream_dashboard": ("GET",),
}

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
        "dashboard_required_routes": list(SERVICE_API_DASHBOARD_ROUTE_NAMES),
        "mobile_required_routes": list(SERVICE_API_MOBILE_ROUTE_NAMES),
    }
