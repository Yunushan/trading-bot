"""Window lifecycle GUI runtime helpers.

New code should prefer the short helper modules in this package,
including `runtime.py` for the main orchestration surface.

The older `main_window_*` window helper modules remain as
compatibility wrappers while callers are migrated.
"""

__all__ = [
    "main_window_runtime",
    "runtime",
]
