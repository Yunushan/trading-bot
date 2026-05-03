"""
Service facade for the current headless backend boundary.

The facade intentionally stays small. Lifecycle/config state now lives in the
service runner layer so the optional HTTP API and desktop adapters can share
the same backend coordinator.
"""

from __future__ import annotations

import sys
from pathlib import Path
from typing import TYPE_CHECKING

if __package__ in (None, ""):
    _PYTHON_ROOT = Path(__file__).resolve().parents[2]
    if str(_PYTHON_ROOT) not in sys.path:
        sys.path.insert(0, str(_PYTHON_ROOT))
    from app.service.runners.bot_runtime import BotRuntimeCoordinator
    from app.service.runners.local_executor import LocalServiceExecutionAdapter
    from app.service.config_store import (
        load_service_config_file,
        merge_service_config,
        resolve_service_config_path,
        service_config_file_status,
        write_service_config_file,
    )
    from app.service.schemas.account import ServiceAccountSnapshot
    from app.service.schemas.backtest import ServiceBacktestCommandResult, ServiceBacktestSnapshot
    from app.service.schemas.config import ServiceConfigSummary, ServiceEditableConfig
    from app.service.schemas.control import BotControlRequest, BotControlResult
    from app.service.schemas.execution import ServiceExecutionSnapshot
    from app.service.schemas.logs import ServiceLogEvent
    from app.service.schemas.positions import ServicePortfolioSnapshot
    from app.service.schemas.runtime import ServiceRuntimeDescriptor
    from app.service.schemas.status import BotStatusSnapshot
    from app.service.terminal import ServiceTerminalCommandResult, run_service_terminal_command
    from app.integrations.llm import (
        build_llm_config_payload,
        list_llm_provider_specs,
        update_llm_config,
    )
else:
    from .runners.bot_runtime import BotRuntimeCoordinator
    from .runners.local_executor import LocalServiceExecutionAdapter
    from .config_store import (
        load_service_config_file,
        merge_service_config,
        resolve_service_config_path,
        service_config_file_status,
        write_service_config_file,
    )
    from .schemas.account import ServiceAccountSnapshot
    from .schemas.backtest import ServiceBacktestCommandResult, ServiceBacktestSnapshot
    from .schemas.config import ServiceConfigSummary, ServiceEditableConfig
    from .schemas.control import BotControlRequest, BotControlResult
    from .schemas.execution import ServiceExecutionSnapshot
    from .schemas.logs import ServiceLogEvent
    from .schemas.positions import ServicePortfolioSnapshot
    from .schemas.runtime import ServiceRuntimeDescriptor
    from .schemas.status import BotStatusSnapshot
    from .terminal import ServiceTerminalCommandResult, run_service_terminal_command
    from ..integrations.llm import (
        build_llm_config_payload,
        list_llm_provider_specs,
        update_llm_config,
    )

if TYPE_CHECKING:
    if __package__ in (None, ""):
        from app.service.runners.backtest_executor import ServiceBacktestExecutionAdapter
    else:
        from .runners.backtest_executor import ServiceBacktestExecutionAdapter


class TradingBotService:
    """
    Minimal service facade.

    This class does not start the real bot loop by itself. It exposes a stable
    backend-facing surface for the optional HTTP API and desktop adapters
    without pushing new orchestration into the PyQt window layer.
    """

    def __init__(
        self,
        config: dict | None = None,
        *,
        config_path: str | Path | None = None,
        load_persisted_config: bool = False,
    ) -> None:
        self._config_persistence_path = resolve_service_config_path(config_path)
        self._config_persistence_loaded_at = ""
        self._config_persistence_saved_at = ""
        self._config_persistence_dirty = bool(config)
        runtime_config = config
        if load_persisted_config:
            loaded_config, metadata = load_service_config_file(self._config_persistence_path)
            self._config_persistence_loaded_at = str(metadata.get("loaded_at") or "")
            self._config_persistence_saved_at = str(metadata.get("saved_at") or "")
            runtime_config = loaded_config
            if isinstance(config, dict):
                runtime_config = merge_service_config(loaded_config, config)
                self._config_persistence_dirty = True
            else:
                self._config_persistence_dirty = False
        self._runtime = BotRuntimeCoordinator(config=runtime_config)
        self._local_execution_adapter: LocalServiceExecutionAdapter | None = None
        self._backtest_execution_adapter: ServiceBacktestExecutionAdapter | None = None

    @property
    def config(self) -> dict:
        return self._runtime.config

    def replace_config(self, config: dict | None) -> None:
        self._runtime.replace_config(config)
        self._config_persistence_dirty = True

    def get_config_summary(self) -> ServiceConfigSummary:
        return self._runtime.get_config_summary()

    def get_config_payload(self) -> ServiceEditableConfig:
        return self._runtime.get_config_payload()

    def update_config(self, config_patch: dict | None) -> ServiceEditableConfig:
        payload = self._runtime.update_config(config_patch)
        if isinstance(config_patch, dict) and config_patch:
            self._config_persistence_dirty = True
        return payload

    def get_config_persistence_status(self) -> dict[str, object]:
        status = service_config_file_status(self._config_persistence_path)
        status.update(
            {
                "loaded": bool(self._config_persistence_loaded_at),
                "dirty": bool(self._config_persistence_dirty),
                "last_loaded_at": self._config_persistence_loaded_at,
                "last_saved_at": self._config_persistence_saved_at,
            }
        )
        return status

    def save_config(
        self,
        path: str | Path | None = None,
        *,
        source: str = "service",
    ) -> dict[str, object]:
        metadata = write_service_config_file(self.config, path or self._config_persistence_path)
        self._config_persistence_path = resolve_service_config_path(metadata["path"])
        self._config_persistence_saved_at = str(metadata.get("saved_at") or "")
        self._config_persistence_dirty = False
        self.record_log_event(
            f"Service config persisted to {self._config_persistence_path}.",
            source=source,
            level="info",
        )
        status = self.get_config_persistence_status()
        status.update(metadata)
        return status

    def load_config(
        self,
        path: str | Path | None = None,
        *,
        source: str = "service",
    ) -> dict[str, object]:
        config, metadata = load_service_config_file(path or self._config_persistence_path)
        self._runtime.replace_config(config)
        self._config_persistence_path = resolve_service_config_path(metadata["path"])
        self._config_persistence_loaded_at = str(metadata.get("loaded_at") or "")
        self._config_persistence_saved_at = str(metadata.get("saved_at") or "")
        self._config_persistence_dirty = False
        self.record_log_event(
            f"Service config loaded from {self._config_persistence_path}.",
            source=source,
            level="info",
        )
        return {
            "config": self.get_config_payload().to_dict(),
            "persistence": self.get_config_persistence_status(),
        }

    def get_llm_provider_catalog(self) -> list[dict[str, object]]:
        return list_llm_provider_specs()

    def get_llm_config_payload(self) -> dict[str, object]:
        return build_llm_config_payload(self.config)

    def update_llm_config(self, config_patch: dict | None) -> dict[str, object]:
        updated_config = update_llm_config(self.config, config_patch)
        self.replace_config(updated_config)
        return self.get_llm_config_payload()

    def call_llm(
        self,
        *,
        prompt: str,
        system_prompt: str = "",
        dry_run: bool = True,
        source: str = "service",
    ) -> dict[str, object]:
        if __package__ in (None, ""):
            from app.integrations.llm.clients import call_llm as _call_llm
        else:
            from ..integrations.llm.clients import call_llm as _call_llm

        result = _call_llm(
            self.config,
            prompt=prompt,
            system_prompt=system_prompt
            or "You are an advisory trading assistant. Do not place orders or claim that orders were executed.",
            context=self.get_dashboard_snapshot(log_limit=10),
            dry_run=dry_run,
        )
        self.record_log_event(
            f"LLM prompt {'prepared' if dry_run else 'sent'} via {self.get_llm_config_payload()['provider']}.",
            source=source,
            level="info" if result.get("ok") else "warning",
        )
        return result

    def run_terminal_command(
        self,
        command: str,
        *,
        source: str = "service-terminal",
    ) -> ServiceTerminalCommandResult:
        return run_service_terminal_command(self, command, source=source)

    def set_account_snapshot(self, **kwargs) -> ServiceAccountSnapshot:
        return self._runtime.set_account_snapshot(**kwargs)

    def get_account_snapshot(self) -> ServiceAccountSnapshot:
        return self._runtime.get_account_snapshot()

    def set_portfolio_snapshot(self, **kwargs) -> ServicePortfolioSnapshot:
        return self._runtime.set_portfolio_snapshot(**kwargs)

    def get_portfolio_snapshot(self) -> ServicePortfolioSnapshot:
        return self._runtime.get_portfolio_snapshot()

    def set_exchange_connector_snapshot(self, snapshot: dict | None = None, **kwargs) -> dict[str, object]:
        return self._runtime.set_exchange_connector_snapshot(snapshot, **kwargs)

    def get_exchange_connector_snapshot(self) -> dict[str, object]:
        return self._runtime.get_exchange_connector_snapshot()

    def set_connector_order_circuit_breaker_snapshot(
        self,
        snapshot: dict | None = None,
        **kwargs,
    ) -> dict[str, object]:
        return self._runtime.set_connector_order_circuit_breaker_snapshot(snapshot, **kwargs)

    def reset_connector_order_circuit_breaker(
        self,
        *,
        source: str = "service",
        force: bool = False,
    ) -> dict[str, object]:
        return self._runtime.reset_connector_order_circuit_breaker(source=source, force=force)

    def get_connector_order_circuit_breaker_snapshot(self) -> dict[str, object]:
        return self._runtime.get_connector_order_circuit_breaker_snapshot()

    def get_connector_order_circuit_incidents(self, *, limit: int = 20) -> dict[str, object]:
        return self._runtime.get_connector_order_circuit_incidents(limit=limit)

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
        status_message: str = "",
    ) -> BotControlResult:
        return self._runtime.set_runtime_state(
            active=active,
            active_engine_count=active_engine_count,
            source=source,
            status_message=status_message,
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
            execution_scope="service-lifecycle-heartbeat",
            trading_execution_supported=False,
            notes=(
                "Start and stop are owned by the standalone service process as lifecycle transitions.",
                "This adapter only maintains a service lifecycle heartbeat.",
                "It does not run trading strategies, market-data loops, or exchange order execution.",
                "Use desktop-hosted API mode for desktop-owned live/demo trading runtime state.",
            ),
        )
        self._runtime.set_execution_snapshot(
            executor_kind="local-service-executor",
            owner="service-process",
            state="idle",
            workload_kind="service-lifecycle-heartbeat",
            session_id="",
            requested_job_count=0,
            active_engine_count=0,
            progress_label="Ready for a standalone lifecycle heartbeat session.",
            progress_percent=None,
            heartbeat_at="",
            tick_count=0,
            last_action="attach",
            last_message="Local service lifecycle executor attached; no trading engines are running.",
            started_at="",
            source="service-local-executor",
            notes=(
                "Standalone service process currently owns lifecycle heartbeat state only.",
                "No strategy loop, market-data loop, or exchange order executor is attached.",
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

    def get_operational_snapshot(self) -> dict[str, object]:
        return self._runtime.get_operational_snapshot()

    def get_operational_preflight(self) -> dict[str, object]:
        snapshot = self.get_operational_snapshot()
        preflight = snapshot.get("preflight") if isinstance(snapshot, dict) else None
        return dict(preflight) if isinstance(preflight, dict) else {}

    def get_dashboard_snapshot(self, *, log_limit: int = 30) -> dict[str, object]:
        payload = self._runtime.get_dashboard_snapshot(log_limit=log_limit)
        payload["config_persistence"] = self.get_config_persistence_status()
        return payload
