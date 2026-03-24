"""
Bot runtime coordinator for the service layer.

This owns config snapshots and lifecycle intent so future HTTP/web/mobile
clients can call a stable backend contract without depending on PyQt.
"""

from __future__ import annotations

import copy
import sys
import threading
from collections import deque
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable

if __package__ in (None, ""):
    _PYTHON_ROOT = Path(__file__).resolve().parents[3]
    if str(_PYTHON_ROOT) not in sys.path:
        sys.path.insert(0, str(_PYTHON_ROOT))
    from app.config import DEFAULT_CONFIG
    from app.service.schemas.account import ServiceAccountSnapshot, build_account_snapshot
    from app.service.schemas.config import (
        ServiceConfigSummary,
        ServiceEditableConfig,
        build_config_summary,
        build_editable_config,
    )
    from app.service.schemas.control import (
        BotControlRequest,
        BotControlResult,
        make_control_result,
        make_start_request,
        make_stop_request,
    )
    from app.service.schemas.logs import ServiceLogEvent, make_log_event
    from app.service.schemas.positions import ServicePortfolioSnapshot, build_portfolio_snapshot
    from app.service.schemas.runtime import ServiceRuntimeDescriptor, build_runtime_descriptor
    from app.service.schemas.status import BotStatusSnapshot, make_initial_status
else:
    from ...config import DEFAULT_CONFIG
    from ..schemas.account import ServiceAccountSnapshot, build_account_snapshot
    from ..schemas.config import (
        ServiceConfigSummary,
        ServiceEditableConfig,
        build_config_summary,
        build_editable_config,
    )
    from ..schemas.control import (
        BotControlRequest,
        BotControlResult,
        make_control_result,
        make_start_request,
        make_stop_request,
    )
    from ..schemas.logs import ServiceLogEvent, make_log_event
    from ..schemas.positions import ServicePortfolioSnapshot, build_portfolio_snapshot
    from ..schemas.runtime import ServiceRuntimeDescriptor, build_runtime_descriptor
    from ..schemas.status import BotStatusSnapshot, make_initial_status

_MISSING = object()


def _deep_merge_mappings(base: dict, patch: dict) -> dict:
    merged = copy.deepcopy(base)
    for key, value in patch.items():
        if isinstance(value, dict) and isinstance(merged.get(key), dict):
            merged[key] = _deep_merge_mappings(merged.get(key) or {}, value)
        else:
            merged[key] = copy.deepcopy(value)
    return merged


class BotRuntimeCoordinator:
    def __init__(self, config: dict | None = None) -> None:
        self._lock = threading.RLock()
        self._config = copy.deepcopy(DEFAULT_CONFIG)
        if isinstance(config, dict):
            self._config.update(copy.deepcopy(config))
        self._runtime_active = False
        self._active_engine_count = 0
        self._runtime_source = "service"
        self._lifecycle_phase = "idle"
        self._requested_action = ""
        self._close_positions_requested = False
        self._status_message = "Service initialized."
        self._last_transition_at = self._now_iso()
        self._log_sequence = 0
        self._recent_logs: deque[ServiceLogEvent] = deque(maxlen=250)
        self._account_total_balance = None
        self._account_available_balance = None
        self._open_position_records: dict = {}
        self._closed_position_records: list[dict] = []
        self._closed_trade_registry: dict = {}
        self._active_pnl = None
        self._active_margin = None
        self._closed_pnl = None
        self._closed_margin = None
        self._account_snapshot = build_account_snapshot(config=self._config, source="service-bootstrap")
        self._portfolio_snapshot = build_portfolio_snapshot(config=self._config, source="service-bootstrap")
        self._control_request_handler: Callable[[BotControlRequest], object] | None = None

    @staticmethod
    def _now_iso() -> str:
        return datetime.now(timezone.utc).isoformat()

    @property
    def config(self) -> dict:
        with self._lock:
            return copy.deepcopy(self._config)

    def replace_config(self, config: dict | None) -> None:
        with self._lock:
            self._config = copy.deepcopy(DEFAULT_CONFIG)
            if isinstance(config, dict):
                self._config.update(copy.deepcopy(config))
            self._account_snapshot = build_account_snapshot(
                config=self._config,
                total_balance=self._account_total_balance,
                available_balance=self._account_available_balance,
                source="service-config",
            )
            self._portfolio_snapshot = build_portfolio_snapshot(
                config=self._config,
                open_position_records=self._open_position_records,
                closed_position_records=self._closed_position_records,
                closed_trade_registry=self._closed_trade_registry,
                active_pnl=self._active_pnl,
                active_margin=self._active_margin,
                closed_pnl=self._closed_pnl,
                closed_margin=self._closed_margin,
                total_balance=self._account_total_balance,
                available_balance=self._account_available_balance,
                source="service-config",
            )

    def get_config_summary(self) -> ServiceConfigSummary:
        with self._lock:
            return build_config_summary(self._config)

    def get_config_payload(self) -> ServiceEditableConfig:
        with self._lock:
            return build_editable_config(self._config)

    def update_config(self, config_patch: dict | None) -> ServiceEditableConfig:
        with self._lock:
            if isinstance(config_patch, dict) and config_patch:
                merged_config = _deep_merge_mappings(self._config, config_patch)
                self.replace_config(merged_config)
            return self.get_config_payload()

    def set_account_snapshot(
        self,
        *,
        total_balance=_MISSING,
        available_balance=_MISSING,
        source: str = "service",
    ) -> ServiceAccountSnapshot:
        with self._lock:
            if total_balance is not _MISSING:
                try:
                    self._account_total_balance = None if total_balance is None else float(total_balance)
                except Exception:
                    self._account_total_balance = None
            if available_balance is not _MISSING:
                try:
                    self._account_available_balance = None if available_balance is None else float(available_balance)
                except Exception:
                    self._account_available_balance = None
            self._account_snapshot = build_account_snapshot(
                config=self._config,
                total_balance=self._account_total_balance,
                available_balance=self._account_available_balance,
                source=source,
            )
            return self._account_snapshot

    def get_account_snapshot(self) -> ServiceAccountSnapshot:
        with self._lock:
            return self._account_snapshot

    def set_portfolio_snapshot(
        self,
        *,
        open_position_records=_MISSING,
        closed_position_records=_MISSING,
        closed_trade_registry=_MISSING,
        active_pnl=_MISSING,
        active_margin=_MISSING,
        closed_pnl=_MISSING,
        closed_margin=_MISSING,
        total_balance=_MISSING,
        available_balance=_MISSING,
        source: str = "service",
    ) -> ServicePortfolioSnapshot:
        with self._lock:
            if open_position_records is not _MISSING:
                self._open_position_records = (
                    copy.deepcopy(open_position_records) if isinstance(open_position_records, dict) else {}
                )
            if closed_position_records is not _MISSING:
                self._closed_position_records = (
                    copy.deepcopy(list(closed_position_records))
                    if isinstance(closed_position_records, (list, tuple))
                    else []
                )
            if closed_trade_registry is not _MISSING:
                self._closed_trade_registry = (
                    copy.deepcopy(closed_trade_registry) if isinstance(closed_trade_registry, dict) else {}
                )
            if active_pnl is not _MISSING:
                try:
                    self._active_pnl = None if active_pnl is None else float(active_pnl)
                except Exception:
                    self._active_pnl = None
            if active_margin is not _MISSING:
                try:
                    self._active_margin = None if active_margin is None else float(active_margin)
                except Exception:
                    self._active_margin = None
            if closed_pnl is not _MISSING:
                try:
                    self._closed_pnl = None if closed_pnl is None else float(closed_pnl)
                except Exception:
                    self._closed_pnl = None
            if closed_margin is not _MISSING:
                try:
                    self._closed_margin = None if closed_margin is None else float(closed_margin)
                except Exception:
                    self._closed_margin = None
            if total_balance is not _MISSING:
                try:
                    self._account_total_balance = None if total_balance is None else float(total_balance)
                except Exception:
                    self._account_total_balance = None
            if available_balance is not _MISSING:
                try:
                    self._account_available_balance = None if available_balance is None else float(available_balance)
                except Exception:
                    self._account_available_balance = None
            self._portfolio_snapshot = build_portfolio_snapshot(
                config=self._config,
                open_position_records=self._open_position_records,
                closed_position_records=self._closed_position_records,
                closed_trade_registry=self._closed_trade_registry,
                active_pnl=self._active_pnl,
                active_margin=self._active_margin,
                closed_pnl=self._closed_pnl,
                closed_margin=self._closed_margin,
                total_balance=self._account_total_balance,
                available_balance=self._account_available_balance,
                source=source,
            )
            return self._portfolio_snapshot

    def get_portfolio_snapshot(self) -> ServicePortfolioSnapshot:
        with self._lock:
            return self._portfolio_snapshot

    def record_log_event(
        self,
        message: str,
        *,
        source: str = "service",
        level: str = "info",
    ) -> ServiceLogEvent:
        with self._lock:
            self._log_sequence += 1
            event = make_log_event(
                message=message,
                source=source,
                level=level,
                sequence_id=self._log_sequence,
            )
            self._recent_logs.append(event)
            return event

    def get_recent_logs(self, *, limit: int = 100) -> tuple[ServiceLogEvent, ...]:
        with self._lock:
            try:
                max_items = max(1, int(limit))
            except Exception:
                max_items = 100
            items = list(self._recent_logs)
            return tuple(items[-max_items:])

    def get_dashboard_snapshot(self, *, log_limit: int = 30) -> dict[str, object]:
        with self._lock:
            return {
                "runtime": self.describe_runtime().to_dict(),
                "status": self.get_status().to_dict(),
                "config": self.get_config_payload().to_dict(),
                "config_summary": self.get_config_summary().to_dict(),
                "account": self.get_account_snapshot().to_dict(),
                "portfolio": self.get_portfolio_snapshot().to_dict(),
                "logs": [item.to_dict() for item in self.get_recent_logs(limit=log_limit)],
            }

    def set_control_request_handler(
        self,
        handler: Callable[[BotControlRequest], object] | None = None,
    ) -> None:
        with self._lock:
            self._control_request_handler = handler if callable(handler) else None

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
            return build_runtime_descriptor()

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
