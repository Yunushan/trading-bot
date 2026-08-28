"""
HTTP API for the headless service layer.

This package exposes the service facade over HTTP so the desktop, the thin
browser dashboard, and future web/mobile clients can consume the same backend
contract.
"""

from .app import (
    FASTAPI_AVAILABLE,
    SERVICE_API_DEFAULT_DASHBOARD_INCIDENT_LIMIT,
    SERVICE_API_DEFAULT_DASHBOARD_LOG_LIMIT,
    SERVICE_API_MAX_INCIDENT_LIMIT,
    SERVICE_API_MAX_RECENT_LOG_LIMIT,
    SERVICE_API_MAX_STREAM_CONNECTIONS,
    SERVICE_API_MAX_STREAM_EVENTS,
    SERVICE_API_MAX_STREAM_INTERVAL_MS,
    SERVICE_API_MIN_STREAM_INTERVAL_MS,
    create_service_api_app,
    run_service_api_server,
)
from .host import ServiceApiBackgroundHost, start_background_service_api_host

__all__ = [
    "FASTAPI_AVAILABLE",
    "SERVICE_API_DEFAULT_DASHBOARD_INCIDENT_LIMIT",
    "SERVICE_API_DEFAULT_DASHBOARD_LOG_LIMIT",
    "SERVICE_API_MAX_INCIDENT_LIMIT",
    "SERVICE_API_MAX_RECENT_LOG_LIMIT",
    "SERVICE_API_MAX_STREAM_CONNECTIONS",
    "SERVICE_API_MAX_STREAM_EVENTS",
    "SERVICE_API_MAX_STREAM_INTERVAL_MS",
    "SERVICE_API_MIN_STREAM_INTERVAL_MS",
    "ServiceApiBackgroundHost",
    "create_service_api_app",
    "run_service_api_server",
    "start_background_service_api_host",
]
