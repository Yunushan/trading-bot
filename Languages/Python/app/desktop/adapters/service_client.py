"""
Desktop service client adapters.

Phase 1 keeps the desktop on an embedded in-process service client. The point
of this module is to give the GUI a desktop-facing client contract now, so the
same bridge can later target a remote API client with minimal churn.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

if __package__ in (None, ""):
    _PYTHON_ROOT = Path(__file__).resolve().parents[3]
    if str(_PYTHON_ROOT) not in sys.path:
        sys.path.insert(0, str(_PYTHON_ROOT))
    from app.service.runtime import TradingBotService
else:
    from ...service.runtime import TradingBotService

try:
    import requests
except Exception:
    requests = None


def _maybe_to_dict(value):
    if value is None:
        return None
    to_dict = getattr(value, "to_dict", None)
    if callable(to_dict):
        try:
            return to_dict()
        except Exception:
            return None
    return value if isinstance(value, dict) else None


class EmbeddedDesktopServiceClient:
    """
    In-process desktop client for the service facade.

    The desktop still runs the bot locally today. This client isolates the GUI
    from the service implementation details so future remote mode can slot in
    behind the same client-facing methods.
    """

    def __init__(self, config: dict | None = None, *, service_cls=TradingBotService) -> None:
        self._service = service_cls(config=config) if callable(service_cls) else None
        self._client_mode = "embedded"
        self._transport = "in-process"

    @property
    def service(self):
        return self._service

    def is_available(self) -> bool:
        return self._service is not None

    def describe(self) -> dict[str, object]:
        return {
            "client_mode": self._client_mode,
            "transport": self._transport,
            "available": self.is_available(),
            "remote_capable": False,
            "notes": [
                "Desktop currently uses an embedded service client.",
                "Remote HTTP desktop mode is available as an opt-in integration path.",
            ],
        }

    def replace_config(self, config: dict | None) -> dict | None:
        if self._service is None:
            return None
        self._service.replace_config(config)
        return self.get_config_summary()

    def set_runtime_state(
        self,
        *,
        active: bool,
        active_engine_count: int = 0,
        source: str = "desktop",
    ) -> dict | None:
        if self._service is None:
            return None
        return _maybe_to_dict(
            self._service.set_runtime_state(
                active=active,
                active_engine_count=active_engine_count,
                source=source,
            )
        )

    def request_start(self, *, requested_job_count: int = 0, source: str = "desktop-start") -> dict | None:
        if self._service is None:
            return None
        return _maybe_to_dict(
            self._service.request_start(
                requested_job_count=requested_job_count,
                source=source,
            )
        )

    def request_stop(self, *, close_positions: bool = False, source: str = "desktop-stop") -> dict | None:
        if self._service is None:
            return None
        return _maybe_to_dict(
            self._service.request_stop(
                close_positions=close_positions,
                source=source,
            )
        )

    def mark_start_failed(self, *, reason: str = "", source: str = "desktop-start") -> dict | None:
        if self._service is None:
            return None
        return _maybe_to_dict(
            self._service.mark_start_failed(
                reason=reason,
                source=source,
            )
        )

    def get_status_snapshot(self) -> dict | None:
        if self._service is None:
            return None
        return _maybe_to_dict(self._service.get_status())

    def get_config_summary(self) -> dict | None:
        if self._service is None:
            return None
        return _maybe_to_dict(self._service.get_config_summary())

    def set_account_snapshot(self, **kwargs) -> dict | None:
        if self._service is None:
            return None
        return _maybe_to_dict(self._service.set_account_snapshot(**kwargs))

    def get_account_snapshot(self) -> dict | None:
        if self._service is None:
            return None
        return _maybe_to_dict(self._service.get_account_snapshot())

    def set_portfolio_snapshot(self, **kwargs) -> dict | None:
        if self._service is None:
            return None
        return _maybe_to_dict(self._service.set_portfolio_snapshot(**kwargs))

    def get_portfolio_snapshot(self) -> dict | None:
        if self._service is None:
            return None
        return _maybe_to_dict(self._service.get_portfolio_snapshot())

    def record_log_event(
        self,
        message: str,
        *,
        source: str = "desktop-log",
        level: str = "info",
    ) -> dict | None:
        if self._service is None:
            return None
        return _maybe_to_dict(
            self._service.record_log_event(
                message,
                source=source,
                level=level,
            )
        )

    def get_recent_logs(self, *, limit: int = 100) -> list[dict]:
        if self._service is None:
            return []
        try:
            items = self._service.get_recent_logs(limit=limit)
        except Exception:
            return []
        out: list[dict] = []
        for item in items or ():
            converted = _maybe_to_dict(item)
            if isinstance(converted, dict):
                out.append(converted)
        return out


class RemoteDesktopServiceClient:
    """
    HTTP-backed desktop client for the service API.

    This is opt-in and is meant for the future desktop-remote mode. The current
    desktop keeps using the embedded client unless explicitly configured.
    """

    def __init__(self, *, base_url: str, api_token: str | None = None, timeout_seconds: float = 3.0) -> None:
        self._base_url = str(base_url or "").rstrip("/")
        self._api_token = str(api_token or os.environ.get("BOT_SERVICE_API_TOKEN") or "").strip()
        self._timeout_seconds = max(0.5, float(timeout_seconds))
        self._client_mode = "remote"
        self._transport = "http"

    def _request(self, method: str, path: str, *, payload: dict | None = None, timeout: float | None = None):
        if requests is None:
            raise RuntimeError("requests is not installed for remote desktop service mode.")
        url = f"{self._base_url}{path}"
        headers = {}
        if self._api_token:
            headers["Authorization"] = f"Bearer {self._api_token}"
        response = requests.request(
            method=method.upper(),
            url=url,
            json=payload,
            headers=headers or None,
            timeout=timeout if timeout is not None else self._timeout_seconds,
        )
        response.raise_for_status()
        if not response.content:
            return None
        try:
            return response.json()
        except Exception:
            return None

    def is_available(self) -> bool:
        try:
            payload = self._request("GET", "/health", timeout=min(self._timeout_seconds, 1.5))
            return isinstance(payload, dict) and payload.get("status") == "ok"
        except Exception:
            return False

    def describe(self) -> dict[str, object]:
        return {
            "client_mode": self._client_mode,
            "transport": self._transport,
            "available": self.is_available(),
            "remote_capable": True,
            "base_url": self._base_url,
            "auth_enabled": bool(self._api_token),
            "notes": [
                "Desktop is configured to use the HTTP service API.",
                "Remote mode is opt-in and depends on the service API being reachable.",
            ],
        }

    def replace_config(self, config: dict | None) -> dict | None:
        return self._request("PUT", "/api/config", payload={"config": config})

    def set_runtime_state(
        self,
        *,
        active: bool,
        active_engine_count: int = 0,
        source: str = "desktop",
    ) -> dict | None:
        return self._request(
            "PUT",
            "/api/runtime/state",
            payload={
                "active": bool(active),
                "active_engine_count": max(0, int(active_engine_count)),
                "source": source,
            },
        )

    def request_start(self, *, requested_job_count: int = 0, source: str = "desktop-start") -> dict | None:
        return self._request(
            "POST",
            "/api/control/start",
            payload={
                "requested_job_count": max(0, int(requested_job_count)),
                "source": source,
            },
        )

    def request_stop(self, *, close_positions: bool = False, source: str = "desktop-stop") -> dict | None:
        return self._request(
            "POST",
            "/api/control/stop",
            payload={
                "close_positions": bool(close_positions),
                "source": source,
            },
        )

    def mark_start_failed(self, *, reason: str = "", source: str = "desktop-start") -> dict | None:
        return self._request(
            "POST",
            "/api/control/start-failed",
            payload={
                "reason": str(reason or ""),
                "source": source,
            },
        )

    def get_status_snapshot(self) -> dict | None:
        return self._request("GET", "/api/status")

    def get_config_summary(self) -> dict | None:
        return self._request("GET", "/api/config-summary")

    def set_account_snapshot(self, **kwargs) -> dict | None:
        return self._request("PUT", "/api/account", payload=dict(kwargs))

    def get_account_snapshot(self) -> dict | None:
        return self._request("GET", "/api/account")

    def set_portfolio_snapshot(self, **kwargs) -> dict | None:
        return self._request("PUT", "/api/portfolio", payload=dict(kwargs))

    def get_portfolio_snapshot(self) -> dict | None:
        return self._request("GET", "/api/portfolio")

    def record_log_event(
        self,
        message: str,
        *,
        source: str = "desktop-log",
        level: str = "info",
    ) -> dict | None:
        return self._request(
            "POST",
            "/api/logs",
            payload={
                "message": str(message or ""),
                "source": source,
                "level": level,
            },
        )

    def get_recent_logs(self, *, limit: int = 100) -> list[dict]:
        payload = self._request("GET", f"/api/logs?limit={max(1, int(limit))}")
        return payload if isinstance(payload, list) else []


def create_desktop_service_client(
    *,
    config: dict | None = None,
    client_mode: str | None = None,
    base_url: str | None = None,
    api_token: str | None = None,
    service_cls=TradingBotService,
) -> EmbeddedDesktopServiceClient | RemoteDesktopServiceClient:
    mode = str(client_mode or os.environ.get("BOT_DESKTOP_SERVICE_MODE") or "embedded").strip().lower()
    resolved_base_url = str(base_url or os.environ.get("BOT_SERVICE_BASE_URL") or "http://127.0.0.1:8000").strip()
    resolved_api_token = str(api_token or os.environ.get("BOT_SERVICE_API_TOKEN") or "").strip()
    if mode == "remote":
        return RemoteDesktopServiceClient(base_url=resolved_base_url, api_token=resolved_api_token)
    return EmbeddedDesktopServiceClient(config=config, service_cls=service_cls)
