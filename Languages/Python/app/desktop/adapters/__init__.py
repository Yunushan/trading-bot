"""
Desktop adapters.

These adapters are the stable client-side boundary for the Qt desktop app.
They currently use an embedded in-process service client, and can later grow a
remote HTTP-backed client without forcing another round of GUI call-site edits.
"""

from .service_client import (
    EmbeddedDesktopServiceClient,
    RemoteDesktopServiceClient,
    create_desktop_service_client,
)

__all__ = [
    "EmbeddedDesktopServiceClient",
    "RemoteDesktopServiceClient",
    "create_desktop_service_client",
]
