"""Strategy-oriented GUI runtime helpers.

New code should import the short module names in this package:
`control_runtime`, `start_runtime`, `stop_runtime`, `override_runtime`,
`controls_runtime`, `ui_runtime`, `stop_loss_runtime`, `indicator_runtime`,
and `context_runtime`.

The legacy `main_window_*` modules remain as compatibility shims while older
imports are migrated off the wrapper surface.
"""

__all__ = [
    "context_runtime",
    "control_actions_runtime",
    "control_lifecycle_runtime",
    "control_runtime",
    "control_shared_runtime",
    "controls_collect_runtime",
    "controls_format_runtime",
    "controls_runtime",
    "controls_shared_runtime",
    "indicator_runtime",
    "override_actions_runtime",
    "override_runtime",
    "override_shared_runtime",
    "override_table_runtime",
    "override_ui_runtime",
    "start_collect_runtime",
    "start_engine_runtime",
    "start_runtime",
    "start_shared_runtime",
    "stop_loss_backtest_context",
    "stop_loss_runtime",
    "stop_loss_runtime_context",
    "stop_loss_shared_runtime",
    "stop_runtime",
    "ui_controls_runtime",
    "ui_dashboard_runtime",
    "ui_runtime",
    "ui_shared_runtime",
]
