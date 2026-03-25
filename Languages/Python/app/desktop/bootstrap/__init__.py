"""
Desktop bootstrap package.

The public launcher remains ``Languages/Python/main.py``. This package holds
the internal desktop startup implementation so desktop-only bootstrap logic can
move behind the ``app.desktop`` boundary without breaking existing entrypoints.
"""

from .main import _run_entrypoint, main

__all__ = ["_run_entrypoint", "main"]
