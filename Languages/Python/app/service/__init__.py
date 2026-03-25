"""
Headless service package.

Keep the package root intentionally small. Import detailed schemas, auth, and
runner types from their own submodules so the backend boundary stays explicit.
"""

from .api import (
    FASTAPI_AVAILABLE,
    ServiceApiBackgroundHost,
    create_service_api_app,
    run_service_api_server,
    start_background_service_api_host,
)
from .runtime import TradingBotService

__all__ = [
    "FASTAPI_AVAILABLE",
    "ServiceApiBackgroundHost",
    "TradingBotService",
    "create_service_api_app",
    "run_service_api_server",
    "start_background_service_api_host",
]
