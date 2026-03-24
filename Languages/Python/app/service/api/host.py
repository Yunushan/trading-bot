"""
Background host for serving the service API from an existing service instance.
"""

from __future__ import annotations

import asyncio
import threading
import time

from .app import create_service_api_app
from ..auth import resolve_service_api_token
from ..runtime import TradingBotService


class ServiceApiBackgroundHost:
    def __init__(
        self,
        *,
        service: TradingBotService | None = None,
        host: str = "127.0.0.1",
        port: int = 8000,
        api_token: str | None = None,
    ) -> None:
        self._service = service or TradingBotService()
        self._host = str(host or "127.0.0.1").strip() or "127.0.0.1"
        self._port = max(1, int(port))
        self._api_token = resolve_service_api_token(api_token)
        self._app = None
        self._server = None
        self._thread = None
        self._startup_error: Exception | None = None
        self._lock = threading.RLock()

    @property
    def service(self) -> TradingBotService:
        return self._service

    @property
    def host(self) -> str:
        return self._host

    @property
    def port(self) -> int:
        return self._port

    def is_running(self) -> bool:
        with self._lock:
            thread = self._thread
            server = self._server
            return bool(thread and thread.is_alive() and server and getattr(server, "started", False))

    def describe(self) -> dict[str, object]:
        return {
            "host": self._host,
            "port": self._port,
            "url": f"http://{self._host}:{self._port}",
            "running": self.is_running(),
            "auth_enabled": bool(self._api_token),
            "host_context": "desktop-embedded",
            "host_owner": "desktop-gui",
            "startup_error": str(self._startup_error) if self._startup_error else "",
        }

    def start(self, *, timeout_seconds: float = 5.0) -> bool:
        with self._lock:
            if self.is_running():
                return True
            self._startup_error = None
            self._app = create_service_api_app(
                service=self._service,
                api_token=self._api_token,
                host_context="desktop-embedded",
                host_owner="desktop-gui",
            )
            self._server = None

            def _run() -> None:
                try:
                    import uvicorn

                    config = uvicorn.Config(
                        self._app,
                        host=self._host,
                        port=self._port,
                        log_level="warning",
                        access_log=False,
                        lifespan="off",
                    )
                    server = uvicorn.Server(config)
                    server.install_signal_handlers = lambda: None
                    with self._lock:
                        self._server = server
                    asyncio.run(server.serve())
                except Exception as exc:  # pragma: no cover - exercised through start()
                    with self._lock:
                        self._startup_error = exc

            self._thread = threading.Thread(
                target=_run,
                name=f"TradingBotServiceApiHost:{self._port}",
                daemon=True,
            )
            self._thread.start()

        deadline = time.monotonic() + max(0.5, float(timeout_seconds))
        while time.monotonic() < deadline:
            with self._lock:
                if self._startup_error is not None:
                    raise RuntimeError(f"Embedded service API host failed to start: {self._startup_error}") from self._startup_error
                server = self._server
                thread = self._thread
                started = bool(server and getattr(server, "started", False))
                alive = bool(thread and thread.is_alive())
            if started:
                return True
            if not alive:
                break
            time.sleep(0.05)
        with self._lock:
            if self._startup_error is not None:
                raise RuntimeError(f"Embedded service API host failed to start: {self._startup_error}") from self._startup_error
        raise RuntimeError("Embedded service API host did not become ready before the timeout.")

    def stop(self, *, timeout_seconds: float = 5.0) -> bool:
        with self._lock:
            server = self._server
            thread = self._thread
            if server is None and (thread is None or not thread.is_alive()):
                self._server = None
                self._thread = None
                return True
            if server is not None:
                try:
                    server.should_exit = True
                except Exception:
                    pass
                try:
                    server.force_exit = True
                except Exception:
                    pass
        if thread is not None:
            thread.join(max(0.5, float(timeout_seconds)))
        with self._lock:
            thread = self._thread
            stopped = not (thread and thread.is_alive())
            if stopped:
                self._server = None
                self._thread = None
            return stopped


def start_background_service_api_host(
    *,
    service: TradingBotService | None = None,
    host: str = "127.0.0.1",
    port: int = 8000,
    api_token: str | None = None,
    timeout_seconds: float = 5.0,
) -> ServiceApiBackgroundHost:
    api_host = ServiceApiBackgroundHost(
        service=service,
        host=host,
        port=port,
        api_token=api_token,
    )
    api_host.start(timeout_seconds=timeout_seconds)
    return api_host
