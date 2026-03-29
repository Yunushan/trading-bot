"""Dashboard feature package for the Python desktop app.

New code should prefer the short helper modules in this package:
`actions_runtime`, `chart_runtime`, `header_runtime`,
`indicator_runtime`, `log_runtime`, `markets_runtime`,
`state_runtime`, and `strategy_runtime`.

The older `main_window_dashboard_*` helper modules remain as
compatibility wrappers while callers are migrated.
"""

__all__ = [
    "actions_runtime",
    "chart_runtime",
    "header_runtime",
    "indicator_runtime",
    "log_runtime",
    "main_window_dashboard_actions_runtime",
    "main_window_dashboard_chart_runtime",
    "main_window_dashboard_header_runtime",
    "main_window_dashboard_indicator_runtime",
    "main_window_dashboard_log_runtime",
    "main_window_dashboard_markets_runtime",
    "main_window_dashboard_state_runtime",
    "main_window_dashboard_strategy_runtime",
    "markets_runtime",
    "state_runtime",
    "strategy_runtime",
]
