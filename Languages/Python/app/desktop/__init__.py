"""
Desktop-only package.

Phase 2 note:
This package now includes the desktop service client adapters that let the Qt
app talk to either the embedded backend or the optional HTTP service API.
The current app still lives under `app/gui` and `main.py`.
"""

from .adapters import (
    EmbeddedDesktopServiceClient,
    RemoteDesktopServiceClient,
    create_desktop_service_client,
)

__all__ = [
    "EmbeddedDesktopServiceClient",
    "RemoteDesktopServiceClient",
    "create_desktop_service_client",
]
