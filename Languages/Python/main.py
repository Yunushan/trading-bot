"""
Public desktop launcher.

This file intentionally stays at the workspace root so existing IDE
configurations, user shortcuts, README instructions, and relaunch metadata keep
working while the desktop bootstrap implementation lives under ``app.desktop``.
"""

from app.desktop.bootstrap import _run_entrypoint


if __name__ == "__main__":
    raise SystemExit(_run_entrypoint())
