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
