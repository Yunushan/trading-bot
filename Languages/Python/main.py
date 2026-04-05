"""
Deprecated compatibility desktop launcher.

This file intentionally stays at the workspace root so existing IDE
configurations, user shortcuts, and existing local workflows keep working while
the canonical product launcher now lives at ``apps/desktop-pyqt/main.py``.
"""

from app.entrypoint_contract import DESKTOP_ENTRYPOINT_CONTRACT

IS_DEPRECATED_COMPATIBILITY_ENTRYPOINT = True
COMPATIBILITY_NOTICE = DESKTOP_ENTRYPOINT_CONTRACT.compatibility_notice()


def main() -> int:
    from app.desktop.product_main import main as desktop_main

    return int(desktop_main())


if __name__ == "__main__":
    raise SystemExit(main())
