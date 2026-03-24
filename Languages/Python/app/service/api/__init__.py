"""
HTTP API for the headless service layer.

This package exposes the service facade over HTTP so the desktop, the thin
browser dashboard, and future web/mobile clients can consume the same backend
contract.
"""

from .app import FASTAPI_AVAILABLE, create_service_api_app, run_service_api_server
from .host import ServiceApiBackgroundHost, start_background_service_api_host

__all__ = [
    "FASTAPI_AVAILABLE",
    "ServiceApiBackgroundHost",
    "create_service_api_app",
    "run_service_api_server",
    "start_background_service_api_host",
]
