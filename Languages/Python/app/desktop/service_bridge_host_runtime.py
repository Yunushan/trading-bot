from __future__ import annotations

import os

from ..service.api import ServiceApiBackgroundHost
from .service_bridge_client_runtime import _ensure_service_client, _service_bridge_log


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
