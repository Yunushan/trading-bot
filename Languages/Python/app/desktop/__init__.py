"""
Desktop-only package.

Phase 2 note:
This package now includes the desktop service client adapters plus the
desktop-bootstrap implementation that sits behind the public
`Languages/Python/main.py` launcher. The Qt UI still lives under `app/gui`.
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
