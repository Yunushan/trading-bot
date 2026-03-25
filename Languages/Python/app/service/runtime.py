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
    from app.service.runners.local_executor import LocalServiceExecutionAdapter
    from app.service.schemas.account import ServiceAccountSnapshot
    from app.service.schemas.backtest import ServiceBacktestCommandResult, ServiceBacktestSnapshot
    from app.service.schemas.config import ServiceConfigSummary, ServiceEditableConfig
    from app.service.schemas.control import BotControlRequest, BotControlResult
    from app.service.schemas.execution import ServiceExecutionSnapshot
    from app.service.schemas.logs import ServiceLogEvent
    from app.service.schemas.positions import ServicePortfolioSnapshot
    from app.service.schemas.runtime import ServiceRuntimeDescriptor
    from app.service.schemas.status import BotStatusSnapshot
else:
    from .runners.bot_runtime import BotRuntimeCoordinator
    from .runners.local_executor import LocalServiceExecutionAdapter
    from .schemas.account import ServiceAccountSnapshot
    from .schemas.backtest import ServiceBacktestCommandResult, ServiceBacktestSnapshot
    from .schemas.config import ServiceConfigSummary, ServiceEditableConfig
    from .schemas.control import BotControlRequest, BotControlResult
    from .schemas.execution import ServiceExecutionSnapshot
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
        self._local_execution_adapter: LocalServiceExecutionAdapter | None = None
        self._backtest_execution_adapter: ServiceBacktestExecutionAdapter | None = None

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

    def set_execution_snapshot(self, **kwargs) -> ServiceExecutionSnapshot:
        return self._runtime.set_execution_snapshot(**kwargs)

    def get_execution_snapshot(self) -> ServiceExecutionSnapshot:
        return self._runtime.get_execution_snapshot()

    def set_backtest_snapshot(self, snapshot: ServiceBacktestSnapshot) -> ServiceBacktestSnapshot:
        return self._runtime.set_backtest_snapshot(snapshot)

    def get_backtest_snapshot(self) -> ServiceBacktestSnapshot:
        return self._runtime.get_backtest_snapshot()

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

    def set_control_request_handler(self, handler=None, **kwargs) -> None:
        self._runtime.set_control_request_handler(handler, **kwargs)

    def enable_local_executor(self) -> LocalServiceExecutionAdapter:
        adapter = self._local_execution_adapter
        if adapter is None:
            adapter = LocalServiceExecutionAdapter(self._runtime)
            self._local_execution_adapter = adapter
        self._runtime.set_control_request_handler(
            adapter.handle_control_request,
            mode="local-service-executor",
            owner="service-process",
            start_supported=True,
            stop_supported=True,
            notes=(
                "Start and stop are owned by the standalone service process.",
                "This adapter manages service-local runtime transitions until the full bot engine is extracted.",
            ),
        )
        self._runtime.set_execution_snapshot(
            executor_kind="local-service-executor",
            owner="service-process",
            state="idle",
            workload_kind="service-runtime-session",
            session_id="",
            requested_job_count=0,
            active_engine_count=0,
            progress_label="Ready for a standalone service session.",
            progress_percent=None,
            heartbeat_at="",
            tick_count=0,
            last_action="attach",
            last_message="Local service executor attached and ready.",
            started_at="",
            source="service-local-executor",
            notes=(
                "Standalone service process currently owns the execution session.",
                "No active local session is running.",
            ),
        )
        return adapter

    def enable_backtest_executor(
        self,
        *,
        wrapper_factory=None,  # noqa: ANN001
    ) -> ServiceBacktestExecutionAdapter:
        if __package__ in (None, ""):
            from app.service.runners.backtest_executor import ServiceBacktestExecutionAdapter
        else:
            from .runners.backtest_executor import ServiceBacktestExecutionAdapter
        adapter = self._backtest_execution_adapter
        if adapter is None or wrapper_factory is not None:
            adapter = ServiceBacktestExecutionAdapter(self._runtime, wrapper_factory=wrapper_factory)
            self._backtest_execution_adapter = adapter
        return adapter

    def submit_backtest(
        self,
        request_patch: dict | None = None,
        *,
        source: str = "service",
    ) -> ServiceBacktestCommandResult:
        return self.enable_backtest_executor().submit_backtest(request_patch, source=source)

    def stop_backtest(self, *, source: str = "service") -> ServiceBacktestCommandResult:
        return self.enable_backtest_executor().stop_backtest(source=source)

    def describe_runtime(self) -> ServiceRuntimeDescriptor:
        return self._runtime.describe_runtime()

    def get_status(self) -> BotStatusSnapshot:
        return self._runtime.get_status()

    def get_dashboard_snapshot(self, *, log_limit: int = 30) -> dict[str, object]:
        return self._runtime.get_dashboard_snapshot(log_limit=log_limit)
