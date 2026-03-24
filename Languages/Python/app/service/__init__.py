"""
Headless service package.

Phase 2 note:
This package establishes the backend boundary used by the desktop client,
the optional FastAPI service process, and the first thin web dashboard.
It does not change the current desktop launch behavior.
"""

from .api import (
    FASTAPI_AVAILABLE,
    ServiceApiBackgroundHost,
    create_service_api_app,
    run_service_api_server,
    start_background_service_api_host,
)
from .runtime import TradingBotService
from .schemas.account import ServiceAccountSnapshot, build_account_snapshot
from .schemas.config import (
    ServiceConfigSummary,
    ServiceEditableConfig,
    build_config_summary,
    build_editable_config,
)
from .schemas.control import (
    BotControlRequest,
    BotControlResult,
    make_control_result,
    make_start_request,
    make_stop_request,
)
from .schemas.logs import ServiceLogEvent, make_log_event
from .schemas.positions import (
    ServicePortfolioSnapshot,
    ServicePositionSnapshot,
    build_portfolio_snapshot,
    build_position_snapshot,
)
from .schemas.runtime import ServiceRuntimeDescriptor, build_runtime_descriptor
from .schemas.status import BotStatusSnapshot
from .runners import BotRuntimeCoordinator

__all__ = [
    "BotStatusSnapshot",
    "BotControlRequest",
    "BotControlResult",
    "BotRuntimeCoordinator",
    "FASTAPI_AVAILABLE",
    "ServiceApiBackgroundHost",
    "ServiceAccountSnapshot",
    "ServiceLogEvent",
    "ServiceConfigSummary",
    "ServiceEditableConfig",
    "ServicePortfolioSnapshot",
    "ServicePositionSnapshot",
    "ServiceRuntimeDescriptor",
    "TradingBotService",
    "build_account_snapshot",
    "build_config_summary",
    "build_editable_config",
    "create_service_api_app",
    "make_control_result",
    "make_log_event",
    "build_portfolio_snapshot",
    "build_position_snapshot",
    "build_runtime_descriptor",
    "make_start_request",
    "make_stop_request",
    "run_service_api_server",
    "start_background_service_api_host",
]
