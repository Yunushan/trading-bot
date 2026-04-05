"""
Desktop-only package.

Phase 2 note:
This package now includes the desktop service client adapters plus the
desktop-bootstrap implementation that sits behind the public
`apps/desktop-pyqt/main.py` launcher, with `app.desktop.product_main` as the
canonical importable entrypoint and `Languages/Python/main.py` kept as a
deprecated compatibility surface. The Qt UI still lives under `app/gui`.
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
