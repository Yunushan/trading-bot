"""
Desktop-to-service bridge.

This bridge lets the existing PyQt application mirror selected config and
runtime state into the phase-1 desktop service client without changing the
current desktop ownership model.
"""

from __future__ import annotations

import copy
import os
from typing import Callable

from PyQt6 import QtCore

from ..service.api import ServiceApiBackgroundHost

_DESKTOP_SERVICE_CLIENT_FACTORY: Callable | None = None
_MISSING = object()


def bind_main_window_desktop_service_bridge(
    main_window_cls,
    *,
    desktop_service_client_factory,
) -> None:
    global _DESKTOP_SERVICE_CLIENT_FACTORY
    _DESKTOP_SERVICE_CLIENT_FACTORY = desktop_service_client_factory

    main_window_cls._initialize_desktop_service_bridge = _initialize_desktop_service_bridge
    main_window_cls._register_service_control_dispatcher = _register_service_control_dispatcher
    main_window_cls._queue_service_control_request = _queue_service_control_request
    main_window_cls._handle_service_control_request = _handle_service_control_request
    main_window_cls._sync_service_config_snapshot = _sync_service_config_snapshot
    main_window_cls._sync_service_runtime_snapshot = _sync_service_runtime_snapshot
    main_window_cls._sync_service_account_snapshot = _sync_service_account_snapshot
    main_window_cls._sync_service_portfolio_snapshot = _sync_service_portfolio_snapshot
    main_window_cls._service_request_start = _service_request_start
    main_window_cls._service_request_stop = _service_request_stop
    main_window_cls._service_mark_start_failed = _service_mark_start_failed
    main_window_cls._service_record_log_event = _service_record_log_event
    main_window_cls._get_service_client_descriptor = _get_service_client_descriptor
    main_window_cls._get_service_account_snapshot = _get_service_account_snapshot
    main_window_cls._get_service_status_snapshot = _get_service_status_snapshot
    main_window_cls._get_service_config_summary = _get_service_config_summary
    main_window_cls._get_service_portfolio_snapshot = _get_service_portfolio_snapshot
    main_window_cls._get_service_recent_logs = _get_service_recent_logs
    main_window_cls._maybe_start_desktop_service_api_host = _maybe_start_desktop_service_api_host
    main_window_cls._shutdown_desktop_service_api_host = _shutdown_desktop_service_api_host
    main_window_cls._get_desktop_service_api_host_status = _get_desktop_service_api_host_status


def _env_flag(name: str, default: bool = False) -> bool:
    raw = os.environ.get(name)
    if raw is None:
        return bool(default)
    return str(raw).strip().lower() in {"1", "true", "yes", "on"}


def _desktop_service_host_enabled() -> bool:
    return _env_flag("BOT_ENABLE_DESKTOP_SERVICE_API", False)


def _desktop_service_api_host() -> str:
    return str(os.environ.get("BOT_DESKTOP_SERVICE_API_HOST") or "127.0.0.1").strip() or "127.0.0.1"


def _desktop_service_api_port() -> int:
    try:
        return max(1, int(os.environ.get("BOT_DESKTOP_SERVICE_API_PORT") or 8000))
    except Exception:
        return 8000


def _desktop_service_api_token() -> str:
    return str(os.environ.get("BOT_SERVICE_API_TOKEN") or "").strip()


def _resolve_desktop_service_api_settings(
    self,
    *,
    enabled=None,
    host=None,
    port=None,
    api_token=None,
) -> dict[str, object]:
    if enabled is None:
        enabled = getattr(self, "_desktop_service_api_enabled_pref", None)
    if enabled is None:
        enabled = _desktop_service_host_enabled()
    if host in (None, ""):
        host = getattr(self, "_desktop_service_api_host_pref", None)
    if not host:
        host = _desktop_service_api_host()
    if port in (None, ""):
        port = getattr(self, "_desktop_service_api_port_pref", None)
    try:
        port = max(1, int(port))
    except Exception:
        port = _desktop_service_api_port()
    if api_token is None:
        api_token = getattr(self, "_desktop_service_api_token_pref", None)
    if api_token is None:
        api_token = _desktop_service_api_token()
    api_token = str(api_token or "").strip()
    return {
        "enabled": bool(enabled),
        "host": str(host or "127.0.0.1").strip() or "127.0.0.1",
        "port": port,
        "api_token": api_token,
        "url": f"http://{str(host or '127.0.0.1').strip() or '127.0.0.1'}:{port}",
        "auth_enabled": bool(api_token),
    }


def _service_bridge_log(self, message: str) -> None:
    try:
        logger = getattr(self, "log", None)
        if callable(logger):
            logger(message)
    except Exception:
        pass


def _ensure_service_client(self):
    client = getattr(self, "_desktop_service_client", None)
    if client is not None:
        return client
    factory = _DESKTOP_SERVICE_CLIENT_FACTORY
    if not callable(factory):
        return None
    try:
        client = factory(config=getattr(self, "config", None))
    except Exception:
        return None
    try:
        self._desktop_service_client = client
    except Exception:
        pass
    return client


def _initialize_desktop_service_bridge(self) -> None:
    client = _ensure_service_client(self)
    if client is None:
        return
    _register_service_control_dispatcher(self)
    _sync_service_config_snapshot(self)
    _sync_service_runtime_snapshot(self, active=False, source="desktop-bootstrap")
    _sync_service_account_snapshot(self, source="desktop-bootstrap")
    _sync_service_portfolio_snapshot(self, source="desktop-bootstrap")
    try:
        self._desktop_service_api_host_status = None
    except Exception:
        pass


def _sync_service_config_snapshot(self) -> None:
    client = _ensure_service_client(self)
    if client is None:
        return
    try:
        client.replace_config(getattr(self, "config", None))
    except Exception:
        return


def _register_service_control_dispatcher(self) -> None:
    client = _ensure_service_client(self)
    if client is None:
        return
    service = getattr(client, "service", None)
    if service is None:
        return
    setter = getattr(service, "set_control_request_handler", None)
    if not callable(setter):
        return
    try:
        setter(
            lambda request, window=self: _queue_service_control_request(window, request),
            mode="desktop-gui-dispatch",
            owner="desktop-gui",
            start_supported=True,
            stop_supported=True,
            notes=(
                "Control requests are queued onto the live desktop GUI thread.",
                "Desktop runtime state flows back into the service snapshot after actual start/stop transitions.",
            ),
        )
        self._desktop_service_control_dispatcher_registered = True
    except Exception:
        pass


def _coerce_service_control_payload(request) -> dict[str, object]:  # noqa: ANN001
    if isinstance(request, dict):
        return dict(request)
    try:
        to_dict = getattr(request, "to_dict", None)
        if callable(to_dict):
            payload = to_dict()
            if isinstance(payload, dict):
                return dict(payload)
    except Exception:
        pass
    return {}


def _queue_service_control_request(self, request) -> dict[str, object]:  # noqa: ANN001
    payload = _coerce_service_control_payload(request)
    action = str(payload.get("action") or "").strip().lower()
    if action not in {"start", "stop"}:
        return {"accepted": False, "message": f"Unsupported control action: {action or 'unknown'}."}
    if bool(getattr(self, "_force_close", False)) or bool(getattr(self, "_close_in_progress", False)):
        return {"accepted": False, "message": "Desktop window is closing; control request rejected."}
    try:
        QtCore.QMetaObject.invokeMethod(
            self,
            "_handle_service_control_request",
            QtCore.Qt.ConnectionType.QueuedConnection,
            QtCore.Q_ARG(object, payload),
        )
    except Exception as exc:
        return {
            "accepted": False,
            "message": f"Failed to queue the control request on the desktop UI thread: {exc}",
        }
    request_source = str(payload.get("source") or "service-api").strip() or "service-api"
    return {
        "accepted": True,
        "message": f"{action.title()} request forwarded to the desktop GUI from {request_source}.",
    }


@QtCore.pyqtSlot(object)
def _handle_service_control_request(self, payload: dict | None) -> None:
    control_payload = payload if isinstance(payload, dict) else {}
    action = str(control_payload.get("action") or "").strip().lower()
    source = str(control_payload.get("source") or "service-api").strip() or "service-api"

    if action == "start":
        if bool(getattr(self, "_is_stopping_engines", False)):
            _service_bridge_log(self, "Service API start request ignored while stop is in progress.")
            try:
                self._service_mark_start_failed(
                    reason="Service API start ignored while stop is in progress.",
                    source="desktop-api",
                )
            except Exception:
                pass
            try:
                self._sync_runtime_state()
            except Exception:
                pass
            return
        try:
            if self._has_active_engines():
                _service_bridge_log(self, "Service API start request ignored because the bot is already running.")
                self._sync_runtime_state()
                return
        except Exception:
            pass
        _service_bridge_log(self, f"Service API start request accepted ({source}).")
        try:
            self.start_strategy()
        except Exception as exc:
            _service_bridge_log(self, f"Service API start dispatch failed: {exc}")
            try:
                self._service_mark_start_failed(
                    reason=f"Service API start dispatch failed: {exc}",
                    source="desktop-api",
                )
            except Exception:
                pass
            try:
                self._sync_runtime_state()
            except Exception:
                pass
        return

    if action == "stop":
        close_positions = bool(control_payload.get("close_positions"))
        try:
            if not self._has_active_engines():
                _service_bridge_log(self, "Service API stop request received while the bot is already idle.")
                self._sync_runtime_state()
                return
        except Exception:
            pass
        _service_bridge_log(self, f"Service API stop request accepted ({source}).")
        try:
            self.stop_strategy_async(close_positions=close_positions, blocking=False)
        except Exception as exc:
            _service_bridge_log(self, f"Service API stop dispatch failed: {exc}")
            try:
                self._sync_runtime_state()
            except Exception:
                pass
        return

    _service_bridge_log(self, f"Unsupported service control action ignored: {action or 'unknown'}.")
    try:
        self._sync_runtime_state()
    except Exception:
        pass


def _count_active_engines(self) -> int:
    try:
        engines = getattr(self, "strategy_engines", {}) or {}
    except Exception:
        return 0
    count = 0
    for eng in engines.values():
        try:
            if hasattr(eng, "is_alive") and eng.is_alive():
                count += 1
        except Exception:
            continue
    return count


def _sync_service_runtime_snapshot(self, active=None, *, source: str = "desktop") -> None:
    client = _ensure_service_client(self)
    if client is None:
        return
    try:
        current_active = bool(getattr(self, "_bot_active", False)) if active is None else bool(active)
    except Exception:
        current_active = bool(active)
    try:
        active_engine_count = _count_active_engines(self)
    except Exception:
        active_engine_count = 0
    try:
        client.set_runtime_state(
            active=current_active,
            active_engine_count=active_engine_count,
            source=source,
        )
    except Exception:
        pass


def _sync_service_account_snapshot(
    self,
    total_balance=_MISSING,
    available_balance=_MISSING,
    *,
    source: str = "desktop-account",
) -> None:
    client = _ensure_service_client(self)
    if client is None:
        return
    kwargs = {"source": source}
    if total_balance is not _MISSING:
        kwargs["total_balance"] = total_balance
    if available_balance is not _MISSING:
        kwargs["available_balance"] = available_balance
    try:
        set_account_snapshot = getattr(client, "set_account_snapshot", None)
        if callable(set_account_snapshot):
            set_account_snapshot(**kwargs)
    except Exception:
        pass


def _sync_service_portfolio_snapshot(
    self,
    *,
    active_pnl=_MISSING,
    active_margin=_MISSING,
    closed_pnl=_MISSING,
    closed_margin=_MISSING,
    source: str = "desktop-portfolio",
) -> None:
    client = _ensure_service_client(self)
    if client is None:
        return
    try:
        open_position_records = copy.deepcopy(getattr(self, "_open_position_records", {}) or {})
    except Exception:
        open_position_records = {}
    try:
        closed_position_records = copy.deepcopy(getattr(self, "_closed_position_records", []) or [])
    except Exception:
        closed_position_records = []
    try:
        closed_trade_registry = copy.deepcopy(getattr(self, "_closed_trade_registry", {}) or {})
    except Exception:
        closed_trade_registry = {}
    if (
        active_pnl is _MISSING
        or active_margin is _MISSING
        or closed_pnl is _MISSING
        or closed_margin is _MISSING
    ):
        try:
            totals = tuple(self._compute_global_pnl_totals())
        except Exception:
            totals = (None, None, None, None)
        if active_pnl is _MISSING:
            active_pnl = totals[0]
        if active_margin is _MISSING:
            active_margin = totals[1]
        if closed_pnl is _MISSING:
            closed_pnl = totals[2]
        if closed_margin is _MISSING:
            closed_margin = totals[3]
    try:
        balance_snapshot = getattr(self, "_positions_balance_snapshot", None)
    except Exception:
        balance_snapshot = None
    if not isinstance(balance_snapshot, dict):
        balance_snapshot = {}
    try:
        set_portfolio_snapshot = getattr(client, "set_portfolio_snapshot", None)
        if callable(set_portfolio_snapshot):
            set_portfolio_snapshot(
                open_position_records=open_position_records,
                closed_position_records=closed_position_records,
                closed_trade_registry=closed_trade_registry,
                active_pnl=None if active_pnl is _MISSING else active_pnl,
                active_margin=None if active_margin is _MISSING else active_margin,
                closed_pnl=None if closed_pnl is _MISSING else closed_pnl,
                closed_margin=None if closed_margin is _MISSING else closed_margin,
                total_balance=balance_snapshot.get("total"),
                available_balance=balance_snapshot.get("available"),
                source=source,
            )
    except Exception:
        pass


def _service_request_start(self, *, requested_job_count: int = 0, source: str = "desktop-start") -> None:
    client = _ensure_service_client(self)
    if client is None:
        return
    try:
        client.request_start(requested_job_count=requested_job_count, source=source)
    except Exception:
        pass


def _service_request_stop(self, *, close_positions: bool = False, source: str = "desktop-stop") -> None:
    client = _ensure_service_client(self)
    if client is None:
        return
    try:
        client.request_stop(close_positions=close_positions, source=source)
    except Exception:
        pass


def _service_mark_start_failed(self, *, reason: str = "", source: str = "desktop-start") -> None:
    client = _ensure_service_client(self)
    if client is None:
        return
    try:
        client.mark_start_failed(reason=reason, source=source)
    except Exception:
        pass


def _service_record_log_event(
    self,
    message: str,
    *,
    source: str = "desktop-log",
    level: str = "info",
) -> None:
    client = _ensure_service_client(self)
    if client is None:
        return
    try:
        record_log_event = getattr(client, "record_log_event", None)
        if callable(record_log_event):
            record_log_event(message, source=source, level=level)
    except Exception:
        pass


def _get_service_client_descriptor(self) -> dict | None:
    client = _ensure_service_client(self)
    if client is None:
        return None
    try:
        describe = getattr(client, "describe", None)
        if callable(describe):
            result = describe()
            return result if isinstance(result, dict) else None
    except Exception:
        return None
    return None


def _get_service_account_snapshot(self) -> dict | None:
    client = _ensure_service_client(self)
    if client is None:
        return None
    try:
        get_account_snapshot = getattr(client, "get_account_snapshot", None)
        if callable(get_account_snapshot):
            result = get_account_snapshot()
            return result if isinstance(result, dict) else None
    except Exception:
        return None
    return None


def _get_service_status_snapshot(self) -> dict | None:
    client = _ensure_service_client(self)
    if client is None:
        return None
    try:
        get_status_snapshot = getattr(client, "get_status_snapshot", None)
        if callable(get_status_snapshot):
            result = get_status_snapshot()
            return result if isinstance(result, dict) else None
    except Exception:
        return None
    return None


def _get_service_portfolio_snapshot(self) -> dict | None:
    client = _ensure_service_client(self)
    if client is None:
        return None
    try:
        get_portfolio_snapshot = getattr(client, "get_portfolio_snapshot", None)
        if callable(get_portfolio_snapshot):
            result = get_portfolio_snapshot()
            return result if isinstance(result, dict) else None
    except Exception:
        return None
    return None


def _get_service_config_summary(self) -> dict | None:
    client = _ensure_service_client(self)
    if client is None:
        return None
    try:
        get_config_summary = getattr(client, "get_config_summary", None)
        if callable(get_config_summary):
            result = get_config_summary()
            return result if isinstance(result, dict) else None
    except Exception:
        return None
    return None


def _get_service_recent_logs(self, *, limit: int = 100) -> list[dict]:
    client = _ensure_service_client(self)
    if client is None:
        return []
    try:
        get_recent_logs = getattr(client, "get_recent_logs", None)
        if callable(get_recent_logs):
            result = get_recent_logs(limit=limit)
            return list(result) if isinstance(result, (list, tuple)) else []
    except Exception:
        return []
    return []


def _maybe_start_desktop_service_api_host(
    self,
    *,
    enabled=None,
    host=None,
    port=None,
    api_token=None,
) -> dict | None:
    settings = _resolve_desktop_service_api_settings(
        self,
        enabled=enabled,
        host=host,
        port=port,
        api_token=api_token,
    )
    if not settings["enabled"]:
        return None
    existing_host = getattr(self, "_desktop_service_api_host", None)
    existing_config = getattr(self, "_desktop_service_api_host_config", None)
    try:
        if (
            existing_host is not None
            and existing_host.is_running()
            and isinstance(existing_config, dict)
            and existing_config.get("host") == settings["host"]
            and existing_config.get("port") == settings["port"]
            and existing_config.get("api_token") == settings["api_token"]
        ):
            status = existing_host.describe()
            self._desktop_service_api_host_status = status
            return status
    except Exception:
        pass
    if existing_host is not None:
        try:
            _shutdown_desktop_service_api_host(self, log_result=False)
        except Exception:
            pass

    client = _ensure_service_client(self)
    service = getattr(client, "service", None) if client is not None else None
    if service is None:
        status = {
            "running": False,
            "url": "",
            "host": settings["host"],
            "port": settings["port"],
            "auth_enabled": settings["auth_enabled"],
            "startup_error": "Desktop service API host requires embedded desktop service mode.",
        }
        try:
            self._desktop_service_api_host_config = dict(settings)
            self._desktop_service_api_host_status = status
        except Exception:
            pass
        _service_bridge_log(self, status["startup_error"])
        return status

    try:
        api_host = ServiceApiBackgroundHost(
            service=service,
            host=str(settings["host"]),
            port=int(settings["port"]),
            api_token=str(settings["api_token"]),
        )
        api_host.start(timeout_seconds=5.0)
        status = api_host.describe()
        try:
            self._desktop_service_api_host = api_host
            self._desktop_service_api_host_config = dict(settings)
            self._desktop_service_api_host_status = status
        except Exception:
            pass
        _service_bridge_log(
            self,
            f"Desktop service API host listening at {status.get('url')} (auth={'on' if status.get('auth_enabled') else 'off'}).",
        )
        return status
    except Exception as exc:
        status = {
            "running": False,
            "url": str(settings["url"]),
            "host": settings["host"],
            "port": settings["port"],
            "auth_enabled": settings["auth_enabled"],
            "startup_error": str(exc),
        }
        try:
            self._desktop_service_api_host = None
            self._desktop_service_api_host_config = dict(settings)
            self._desktop_service_api_host_status = status
        except Exception:
            pass
        _service_bridge_log(self, f"Desktop service API host failed to start: {exc}")
        return status


def _shutdown_desktop_service_api_host(self, *, log_result: bool = True) -> bool:
    host = getattr(self, "_desktop_service_api_host", None)
    if host is None:
        return True
    try:
        stopped = bool(host.stop(timeout_seconds=3.0))
    except Exception:
        stopped = False
    try:
        status = host.describe()
        self._desktop_service_api_host_status = status
        if stopped:
            self._desktop_service_api_host = None
            self._desktop_service_api_host_config = None
    except Exception:
        pass
    if stopped and log_result:
        _service_bridge_log(self, "Desktop service API host stopped.")
    return stopped


def _get_desktop_service_api_host_status(self) -> dict | None:
    status = getattr(self, "_desktop_service_api_host_status", None)
    if isinstance(status, dict):
        return status
    host = getattr(self, "_desktop_service_api_host", None)
    try:
        if host is not None:
            status = host.describe()
            self._desktop_service_api_host_status = status
            return status
    except Exception:
        return None
    return None
