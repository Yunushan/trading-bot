"""Shared helper package for the Python desktop app.

New code should prefer the short helper modules in this package:
`config_runtime`, `helper_runtime`, `ui_support`, and
`web_embed`.

The older `main_window_*` helper modules remain as compatibility
wrappers while callers are migrated.
"""

__all__ = [
    "config_runtime",
    "helper_runtime",
    "main_window_config",
    "main_window_helper_runtime",
    "main_window_ui_support",
    "main_window_web_embed",
    "ui_support",
    "web_embed",
]
