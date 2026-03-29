from __future__ import annotations

from typing import Callable

_DESKTOP_SERVICE_CLIENT_FACTORY: Callable | None = None


def set_desktop_service_client_factory(factory: Callable | None) -> None:
    global _DESKTOP_SERVICE_CLIENT_FACTORY
    _DESKTOP_SERVICE_CLIENT_FACTORY = factory


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
