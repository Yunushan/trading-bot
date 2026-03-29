"""Chart feature package for the Python desktop app.

New code should prefer the short helper modules in this package:
`display_runtime`, `host_runtime`, `selection_runtime`,
`tab_runtime`, and `view_runtime`.

The older `main_window_chart_*` helper modules remain as
compatibility wrappers while callers are migrated.
"""

__all__ = [
    "display_runtime",
    "host_runtime",
    "main_window_chart_display_runtime",
    "main_window_chart_host_runtime",
    "main_window_chart_selection_runtime",
    "main_window_chart_tab",
    "main_window_chart_view_runtime",
    "selection_runtime",
    "tab_runtime",
    "view_runtime",
]
