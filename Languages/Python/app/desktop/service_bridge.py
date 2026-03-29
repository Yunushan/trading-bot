"""
Desktop-to-service bridge.

This bridge lets the existing PyQt application mirror selected config and
runtime state into the phase-1 desktop service client without changing the
current desktop ownership model.
"""

from __future__ import annotations

from . import service_bridge_client_runtime, service_bridge_control_runtime, service_bridge_host_runtime
from . import service_bridge_snapshot_runtime


def bind_main_window_desktop_service_bridge(
    main_window_cls,
    *,
    desktop_service_client_factory,
) -> None:
    service_bridge_client_runtime.set_desktop_service_client_factory(desktop_service_client_factory)

    main_window_cls._initialize_desktop_service_bridge = _initialize_desktop_service_bridge
    main_window_cls._register_service_control_dispatcher = service_bridge_control_runtime._register_service_control_dispatcher
    main_window_cls._queue_service_control_request = service_bridge_control_runtime._queue_service_control_request
    main_window_cls._handle_service_control_request = service_bridge_control_runtime._handle_service_control_request
    main_window_cls._sync_service_config_snapshot = service_bridge_snapshot_runtime._sync_service_config_snapshot
    main_window_cls._sync_service_runtime_snapshot = service_bridge_snapshot_runtime._sync_service_runtime_snapshot
    main_window_cls._sync_service_account_snapshot = service_bridge_snapshot_runtime._sync_service_account_snapshot
    main_window_cls._sync_service_portfolio_snapshot = service_bridge_snapshot_runtime._sync_service_portfolio_snapshot
    main_window_cls._service_request_start = service_bridge_control_runtime._service_request_start
    main_window_cls._service_request_stop = service_bridge_control_runtime._service_request_stop
    main_window_cls._service_mark_start_failed = service_bridge_control_runtime._service_mark_start_failed
    main_window_cls._service_record_log_event = service_bridge_control_runtime._service_record_log_event
    main_window_cls._get_service_client_descriptor = service_bridge_snapshot_runtime._get_service_client_descriptor
    main_window_cls._get_service_account_snapshot = service_bridge_snapshot_runtime._get_service_account_snapshot
    main_window_cls._get_service_status_snapshot = service_bridge_snapshot_runtime._get_service_status_snapshot
    main_window_cls._get_service_config_summary = service_bridge_snapshot_runtime._get_service_config_summary
    main_window_cls._get_service_portfolio_snapshot = service_bridge_snapshot_runtime._get_service_portfolio_snapshot
    main_window_cls._get_service_recent_logs = service_bridge_snapshot_runtime._get_service_recent_logs
    main_window_cls._maybe_start_desktop_service_api_host = service_bridge_host_runtime._maybe_start_desktop_service_api_host
    main_window_cls._shutdown_desktop_service_api_host = service_bridge_host_runtime._shutdown_desktop_service_api_host
    main_window_cls._get_desktop_service_api_host_status = service_bridge_host_runtime._get_desktop_service_api_host_status


def _initialize_desktop_service_bridge(self) -> None:
    client = service_bridge_client_runtime._ensure_service_client(self)
    if client is None:
        return
    service_bridge_control_runtime._register_service_control_dispatcher(self)
    service_bridge_snapshot_runtime._sync_service_config_snapshot(self)
    service_bridge_snapshot_runtime._sync_service_runtime_snapshot(self, active=False, source="desktop-bootstrap")
    service_bridge_snapshot_runtime._sync_service_account_snapshot(self, source="desktop-bootstrap")
    service_bridge_snapshot_runtime._sync_service_portfolio_snapshot(self, source="desktop-bootstrap")
    try:
        self._desktop_service_api_host_status = None
    except Exception:
        pass
