"""
Service-facing schemas.

These schemas are intended to become the stable contracts shared by desktop,
headless runtime, web UI, and mobile clients.
"""

from .account import ServiceAccountSnapshot, build_account_snapshot
from .backtest import (
    ServiceBacktestCommandResult,
    ServiceBacktestErrorRecord,
    ServiceBacktestRunRecord,
    ServiceBacktestSnapshot,
    build_backtest_error_record,
    build_backtest_run_record,
    build_backtest_snapshot,
    make_backtest_command_result,
)
from .config import ServiceConfigSummary, build_config_summary
from .control import BotControlRequest, BotControlResult, make_control_result, make_start_request, make_stop_request
from .execution import ServiceExecutionSnapshot, build_execution_snapshot
from .logs import ServiceLogEvent, make_log_event
from .positions import ServicePortfolioSnapshot, ServicePositionSnapshot, build_portfolio_snapshot, build_position_snapshot
from .runtime import ServiceCapabilityFlags, ServiceRuntimeDescriptor, build_runtime_descriptor
from .status import BotStatusSnapshot

__all__ = [
    "BotStatusSnapshot",
    "BotControlRequest",
    "BotControlResult",
    "ServiceAccountSnapshot",
    "ServiceBacktestCommandResult",
    "ServiceBacktestErrorRecord",
    "ServiceBacktestRunRecord",
    "ServiceBacktestSnapshot",
    "ServiceExecutionSnapshot",
    "ServiceLogEvent",
    "ServiceConfigSummary",
    "ServiceCapabilityFlags",
    "ServicePortfolioSnapshot",
    "ServicePositionSnapshot",
    "ServiceRuntimeDescriptor",
    "build_account_snapshot",
    "build_backtest_error_record",
    "build_backtest_run_record",
    "build_backtest_snapshot",
    "build_config_summary",
    "build_execution_snapshot",
    "make_backtest_command_result",
    "make_control_result",
    "make_log_event",
    "build_portfolio_snapshot",
    "build_position_snapshot",
    "build_runtime_descriptor",
    "make_start_request",
    "make_stop_request",
]
