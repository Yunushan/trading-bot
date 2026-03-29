"""UI composition GUI runtime helpers.

New code should prefer the short helper modules in this package:
`secondary_tabs_runtime`, `tab_runtime`, `theme_runtime`,
`theme_styles`, and `ui_misc_runtime`.

The older `main_window_*` UI helper modules remain as compatibility
wrappers while callers are migrated.
"""

__all__ = [
    "main_window_secondary_tabs_runtime",
    "main_window_tab_runtime",
    "main_window_theme_runtime",
    "main_window_theme_styles",
    "main_window_ui_misc_runtime",
    "secondary_tabs_runtime",
    "tab_runtime",
    "theme_runtime",
    "theme_styles",
    "ui_misc_runtime",
]
