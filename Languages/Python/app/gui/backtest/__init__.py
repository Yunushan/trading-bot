"""Backtest feature package for the Python desktop app.

New code should prefer the short helper modules in this package:
`bridge_runtime`, `execution_runtime`, `results_runtime`,
`state_runtime`, `tab_runtime`, `template_runtime`, and
`worker_runtime`.

The older `main_window_backtest_*` helper modules remain as
compatibility wrappers while callers are migrated.
"""

__all__ = [
    "bridge_runtime",
    "execution_runtime",
    "main_window_backtest_bridge_runtime",
    "main_window_backtest_execution_runtime",
    "main_window_backtest_results_runtime",
    "main_window_backtest_runtime",
    "main_window_backtest_state_runtime",
    "main_window_backtest_tab",
    "main_window_backtest_template_runtime",
    "results_runtime",
    "state_runtime",
    "tab_runtime",
    "template_runtime",
    "worker_runtime",
]
