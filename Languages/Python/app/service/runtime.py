"""
Service facade for the current headless backend boundary.

The facade intentionally stays small. Lifecycle/config state now lives in the
service runner layer so the optional HTTP API and desktop adapters can share
the same backend coordinator.
"""

from __future__ import annotations

import sys
from pathlib import Path

if __package__ in (None, ""):
    _PYTHON_ROOT = Path(__file__).resolve().parents[2]
    if str(_PYTHON_ROOT) not in sys.path:
        sys.path.insert(0, str(_PYTHON_ROOT))
    from app.service.runners.bot_runtime import BotRuntimeCoordinator
    from app.service.schemas.account import ServiceAccountSnapshot
    from app.service.schemas.config import ServiceConfigSummary, ServiceEditableConfig
    from app.service.schemas.control import BotControlRequest, BotControlResult
    from app.service.schemas.logs import ServiceLogEvent
    from app.service.schemas.positions import ServicePortfolioSnapshot
    from app.service.schemas.runtime import ServiceRuntimeDescriptor
    from app.service.schemas.status import BotStatusSnapshot
else:
    from .runners.bot_runtime import BotRuntimeCoordinator
    from .schemas.account import ServiceAccountSnapshot
    from .schemas.config import ServiceConfigSummary, ServiceEditableConfig
    from .schemas.control import BotControlRequest, BotControlResult
    from .schemas.logs import ServiceLogEvent
    from .schemas.positions import ServicePortfolioSnapshot
    from .schemas.runtime import ServiceRuntimeDescriptor
    from .schemas.status import BotStatusSnapshot


class TradingBotService:
    """
    Minimal service facade.

    This class does not start the real bot loop by itself. It exposes a stable
    backend-facing surface for the optional HTTP API and desktop adapters
    without pushing new orchestration into the PyQt window layer.
    """

    def __init__(self, config: dict | None = None) -> None:
        self._runtime = BotRuntimeCoordinator(config=config)

    @property
    def config(self) -> dict:
        return self._runtime.config

    def replace_config(self, config: dict | None) -> None:
        self._runtime.replace_config(config)

    def get_config_summary(self) -> ServiceConfigSummary:
        return self._runtime.get_config_summary()

    def get_config_payload(self) -> ServiceEditableConfig:
        return self._runtime.get_config_payload()

    def update_config(self, config_patch: dict | None) -> ServiceEditableConfig:
        return self._runtime.update_config(config_patch)

    def set_account_snapshot(self, **kwargs) -> ServiceAccountSnapshot:
        return self._runtime.set_account_snapshot(**kwargs)

    def get_account_snapshot(self) -> ServiceAccountSnapshot:
        return self._runtime.get_account_snapshot()

    def set_portfolio_snapshot(self, **kwargs) -> ServicePortfolioSnapshot:
        return self._runtime.set_portfolio_snapshot(**kwargs)

    def get_portfolio_snapshot(self) -> ServicePortfolioSnapshot:
        return self._runtime.get_portfolio_snapshot()

    def record_log_event(
        self,
        message: str,
        *,
        source: str = "service",
        level: str = "info",
    ) -> ServiceLogEvent:
        return self._runtime.record_log_event(message, source=source, level=level)

    def get_recent_logs(self, *, limit: int = 100) -> tuple[ServiceLogEvent, ...]:
        return self._runtime.get_recent_logs(limit=limit)

    def request_start(
        self,
        request: BotControlRequest | None = None,
        *,
        requested_job_count: int = 0,
        source: str = "service",
    ) -> BotControlResult:
        return self._runtime.request_start(
            request,
            requested_job_count=requested_job_count,
            source=source,
        )

    def request_stop(
        self,
        request: BotControlRequest | None = None,
        *,
        close_positions: bool = False,
        source: str = "service",
    ) -> BotControlResult:
        return self._runtime.request_stop(
            request,
            close_positions=close_positions,
            source=source,
        )

    def mark_start_failed(self, *, reason: str = "", source: str = "service") -> BotControlResult:
        return self._runtime.mark_start_failed(reason=reason, source=source)

    def set_runtime_state(
        self,
        *,
        active: bool,
        active_engine_count: int = 0,
        source: str = "service",
    ) -> BotControlResult:
        return self._runtime.set_runtime_state(
            active=active,
            active_engine_count=active_engine_count,
            source=source,
        )

    def set_control_request_handler(self, handler=None) -> None:
        self._runtime.set_control_request_handler(handler)

    def describe_runtime(self) -> ServiceRuntimeDescriptor:
        return self._runtime.describe_runtime()

    def get_status(self) -> BotStatusSnapshot:
        return self._runtime.get_status()

    def get_dashboard_snapshot(self, *, log_limit: int = 30) -> dict[str, object]:
        return self._runtime.get_dashboard_snapshot(log_limit=log_limit)
