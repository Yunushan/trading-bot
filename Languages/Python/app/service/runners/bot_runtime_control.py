"""Control-plane and execution mixin for the service bot runtime coordinator."""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Callable

if __package__ in (None, ""):
    _PYTHON_ROOT = Path(__file__).resolve().parents[3]
    if str(_PYTHON_ROOT) not in sys.path:
        sys.path.insert(0, str(_PYTHON_ROOT))
    from app.service.runners.bot_runtime_shared import _MISSING, _normalize_control_plane_notes
    from app.service.schemas.control import (
        BotControlRequest,
        BotControlResult,
        make_control_result,
        make_start_request,
        make_stop_request,
    )
    from app.service.schemas.execution import ServiceExecutionSnapshot, build_execution_snapshot
    from app.service.schemas.runtime import ServiceControlPlaneDescriptor, ServiceRuntimeDescriptor
    from app.service.schemas.runtime import build_runtime_descriptor
    from app.service.schemas.status import BotStatusSnapshot, make_initial_status
else:
    from .bot_runtime_shared import _MISSING, _normalize_control_plane_notes
    from ..schemas.control import (
        BotControlRequest,
        BotControlResult,
        make_control_result,
        make_start_request,
        make_stop_request,
    )
    from ..schemas.execution import ServiceExecutionSnapshot, build_execution_snapshot
    from ..schemas.runtime import ServiceControlPlaneDescriptor, ServiceRuntimeDescriptor
    from ..schemas.runtime import build_runtime_descriptor
    from ..schemas.status import BotStatusSnapshot, make_initial_status


class BotRuntimeControlMixin:
    _lock: object
    _control_request_handler: Callable[[BotControlRequest], object] | None

    def set_execution_snapshot(
        self,
        *,
        executor_kind=_MISSING,
        owner=_MISSING,
        state=_MISSING,
        workload_kind=_MISSING,
        session_id=_MISSING,
        requested_job_count=_MISSING,
        active_engine_count=_MISSING,
        progress_label=_MISSING,
        progress_percent=_MISSING,
        heartbeat_at=_MISSING,
        tick_count=_MISSING,
        last_action=_MISSING,
        last_message=_MISSING,
        started_at=_MISSING,
        source=_MISSING,
        notes=_MISSING,
    ) -> ServiceExecutionSnapshot:
        with self._lock:
            if executor_kind is not _MISSING:
                self._execution_executor_kind = str(executor_kind or "unbound")
            if owner is not _MISSING:
                self._execution_owner = str(owner or "service-runtime")
            if state is not _MISSING:
                self._execution_state = str(state or "idle")
            if workload_kind is not _MISSING:
                self._execution_workload_kind = str(workload_kind or "unbound")
            if session_id is not _MISSING:
                self._execution_session_id = str(session_id or "")
            if requested_job_count is not _MISSING:
                self._execution_requested_job_count = max(0, int(requested_job_count or 0))
            if active_engine_count is not _MISSING:
                self._execution_active_engine_count = max(0, int(active_engine_count or 0))
            if progress_label is not _MISSING:
                self._execution_progress_label = str(progress_label or "")
            if progress_percent is not _MISSING:
                self._execution_progress_percent = None if progress_percent is None else float(progress_percent)
            if heartbeat_at is not _MISSING:
                self._execution_heartbeat_at = str(heartbeat_at or "")
            if tick_count is not _MISSING:
                self._execution_tick_count = max(0, int(tick_count or 0))
            if last_action is not _MISSING:
                self._execution_last_action = str(last_action or "")
            if last_message is not _MISSING:
                self._execution_last_message = str(last_message or "")
            if started_at is not _MISSING:
                self._execution_started_at = str(started_at or "")
            if source is not _MISSING:
                self._execution_source = str(source or "service")
            if notes is not _MISSING:
                self._execution_notes = _normalize_control_plane_notes(notes)
            self._execution_snapshot = build_execution_snapshot(
                executor_kind=self._execution_executor_kind,
                owner=self._execution_owner,
                state=self._execution_state,
                workload_kind=self._execution_workload_kind,
                session_id=self._execution_session_id,
                requested_job_count=self._execution_requested_job_count,
                active_engine_count=self._execution_active_engine_count,
                progress_label=self._execution_progress_label,
                progress_percent=self._execution_progress_percent,
                heartbeat_at=self._execution_heartbeat_at,
                tick_count=self._execution_tick_count,
                last_action=self._execution_last_action,
                last_message=self._execution_last_message,
                started_at=self._execution_started_at,
                source=self._execution_source,
                notes=self._execution_notes,
            )
            return self._execution_snapshot

    def get_execution_snapshot(self) -> ServiceExecutionSnapshot:
        with self._lock:
            return self._execution_snapshot

    def set_control_request_handler(
        self,
        handler: Callable[[BotControlRequest], object] | None = None,
        *,
        mode: str | None = None,
        owner: str | None = None,
        start_supported: bool | None = None,
        stop_supported: bool | None = None,
        notes=None,  # noqa: ANN001
    ) -> None:
        with self._lock:
            self._control_request_handler = handler if callable(handler) else None
            if callable(handler):
                self._control_plane_mode = str(mode or "delegated-dispatch").strip() or "delegated-dispatch"
                self._control_plane_owner = str(owner or "external-control-adapter").strip() or "external-control-adapter"
                self._control_plane_start_supported = True if start_supported is None else bool(start_supported)
                self._control_plane_stop_supported = True if stop_supported is None else bool(stop_supported)
                self._control_plane_notes = _normalize_control_plane_notes(notes) or (
                    "Control requests are forwarded to an external execution adapter.",
                )
                self.set_execution_snapshot(
                    executor_kind=self._control_plane_mode,
                    owner=self._control_plane_owner,
                    state="idle",
                    workload_kind="delegated-runtime",
                    session_id="",
                    requested_job_count=0,
                    active_engine_count=0,
                    progress_label="Awaiting delegated runtime updates.",
                    progress_percent=None,
                    heartbeat_at="",
                    tick_count=0,
                    last_action="attach",
                    last_message="Delegated execution adapter attached.",
                    started_at="",
                    source="service-control-plane",
                    notes=(
                        "Execution updates depend on the attached delegated runtime owner.",
                    ),
                )
            else:
                self._control_plane_mode = "intent-only"
                self._control_plane_owner = "service-runtime"
                self._control_plane_start_supported = False
                self._control_plane_stop_supported = False
                self._control_plane_notes = (
                    "Control requests are recorded as service intent until an execution adapter is attached.",
                )
                self.set_execution_snapshot(
                    executor_kind="unbound",
                    owner="service-runtime",
                    state="idle",
                    workload_kind="unbound",
                    session_id="",
                    requested_job_count=0,
                    active_engine_count=0,
                    progress_label="No execution adapter attached.",
                    progress_percent=None,
                    heartbeat_at="",
                    tick_count=0,
                    last_action="detach",
                    last_message="Execution adapter detached; service returned to intent-only mode.",
                    started_at="",
                    source="service-control-plane",
                    notes=("Execution state is idle until a service-owned or delegated executor attaches.",),
                )

    def _dispatch_control_request(self, control_request: BotControlRequest) -> tuple[bool | None, str]:
        with self._lock:
            handler = self._control_request_handler
        if not callable(handler):
            return None, ""
        source_text = str(control_request.source or "").strip().lower()
        if source_text.startswith("desktop"):
            return None, ""
        try:
            response = handler(control_request)
        except Exception as exc:
            return False, f"Control dispatch failed: {exc}"
        if isinstance(response, dict):
            accepted_value = response.get("accepted")
            message = str(response.get("message") or "").strip()
            if accepted_value is None:
                return True, message
            return bool(accepted_value), message
        if isinstance(response, bool):
            return bool(response), ""
        if response is None:
            return True, ""
        return True, str(response).strip()

    def _make_control_result(
        self,
        *,
        action: str,
        requested_job_count: int = 0,
        close_positions_requested: bool | None = None,
        accepted: bool = True,
    ) -> BotControlResult:
        return make_control_result(
            accepted=accepted,
            action=action,
            lifecycle_phase=self._lifecycle_phase,
            runtime_active=self._runtime_active,
            active_engine_count=self._active_engine_count,
            requested_job_count=requested_job_count,
            close_positions_requested=(
                self._close_positions_requested
                if close_positions_requested is None
                else bool(close_positions_requested)
            ),
            source=self._runtime_source,
            status_message=self._status_message,
        )

    def request_start(
        self,
        request: BotControlRequest | None = None,
        *,
        requested_job_count: int = 0,
        source: str = "service",
    ) -> BotControlResult:
        with self._lock:
            control_request = (
                request
                if isinstance(request, BotControlRequest)
                else make_start_request(requested_job_count=requested_job_count, source=source)
            )
            self._runtime_source = control_request.source
            self._lifecycle_phase = "starting"
            self._requested_action = "start"
            self._close_positions_requested = False
            if control_request.requested_job_count > 0:
                self._status_message = (
                    f"Start requested for {control_request.requested_job_count} symbol/interval loop(s)."
                )
            else:
                self._status_message = "Start requested."
            self._last_transition_at = self._now_iso()
        dispatch_accepted, dispatch_message = self._dispatch_control_request(control_request)
        with self._lock:
            accepted = dispatch_accepted is not False
            if dispatch_accepted is False:
                self._lifecycle_phase = "running" if self._runtime_active else "idle"
                self._requested_action = ""
                self._close_positions_requested = False
                self._status_message = dispatch_message or "Start request could not be dispatched."
                self._last_transition_at = self._now_iso()
            elif dispatch_message:
                self._status_message = f"{self._status_message} {dispatch_message}".strip()
            return self._make_control_result(
                action=control_request.action,
                requested_job_count=control_request.requested_job_count,
                close_positions_requested=False,
                accepted=accepted,
            )

    def request_stop(
        self,
        request: BotControlRequest | None = None,
        *,
        close_positions: bool = False,
        source: str = "service",
    ) -> BotControlResult:
        with self._lock:
            control_request = (
                request
                if isinstance(request, BotControlRequest)
                else make_stop_request(close_positions=close_positions, source=source)
            )
            self._runtime_source = control_request.source
            self._lifecycle_phase = "stopping"
            self._requested_action = "stop"
            self._close_positions_requested = bool(control_request.close_positions)
            if self._close_positions_requested:
                self._status_message = "Stop requested with close-all positions."
            else:
                self._status_message = "Stop requested."
            self._last_transition_at = self._now_iso()
        dispatch_accepted, dispatch_message = self._dispatch_control_request(control_request)
        with self._lock:
            accepted = dispatch_accepted is not False
            if dispatch_accepted is False:
                self._lifecycle_phase = "running" if self._runtime_active else "idle"
                self._requested_action = ""
                self._close_positions_requested = False
                self._status_message = dispatch_message or "Stop request could not be dispatched."
                self._last_transition_at = self._now_iso()
            elif dispatch_message:
                self._status_message = f"{self._status_message} {dispatch_message}".strip()
            return self._make_control_result(
                action=control_request.action,
                close_positions_requested=self._close_positions_requested,
                accepted=accepted,
            )

    def mark_start_failed(self, *, reason: str = "", source: str = "service") -> BotControlResult:
        with self._lock:
            self._runtime_source = str(source or "service")
            self._runtime_active = False
            self._active_engine_count = 0
            self._lifecycle_phase = "idle"
            self._requested_action = ""
            self._close_positions_requested = False
            self._status_message = str(reason or "Start request did not launch any engine.")
            self._last_transition_at = self._now_iso()
            return self._make_control_result(action="start", accepted=False)

    def set_runtime_state(
        self,
        *,
        active: bool,
        active_engine_count: int = 0,
        source: str = "service",
    ) -> BotControlResult:
        with self._lock:
            self._runtime_active = bool(active)
            try:
                self._active_engine_count = max(0, int(active_engine_count))
            except Exception:
                self._active_engine_count = 0
            self._runtime_source = str(source or "service")
            if self._runtime_active:
                self._lifecycle_phase = "running"
                self._requested_action = ""
                self._status_message = f"Runtime active with {self._active_engine_count} engine(s)."
            else:
                self._lifecycle_phase = "idle"
                self._requested_action = ""
                if self._close_positions_requested:
                    self._status_message = "Runtime idle after stop request."
                else:
                    self._status_message = "Runtime idle."
                self._close_positions_requested = False
            self._last_transition_at = self._now_iso()
            return self._make_control_result(action="sync")

    def describe_runtime(self) -> ServiceRuntimeDescriptor:
        with self._lock:
            return build_runtime_descriptor(
                control_plane=ServiceControlPlaneDescriptor(
                    mode=self._control_plane_mode,
                    owner=self._control_plane_owner,
                    start_supported=self._control_plane_start_supported,
                    stop_supported=self._control_plane_stop_supported,
                    notes=tuple(self._control_plane_notes),
                )
            )

    def get_status(self) -> BotStatusSnapshot:
        with self._lock:
            return make_initial_status(
                state="running" if self._runtime_active else "idle",
                lifecycle_phase=self._lifecycle_phase,
                requested_action=self._requested_action,
                close_positions_requested=self._close_positions_requested,
                status_message=self._status_message,
                last_transition_at=self._last_transition_at,
                runtime_source=self._runtime_source,
                active_engine_count=self._active_engine_count,
                account_type=str(self._config.get("account_type") or ""),
                mode=str(self._config.get("mode") or ""),
                selected_exchange=str(self._config.get("selected_exchange") or ""),
                connector_backend=str(self._config.get("connector_backend") or ""),
            )
