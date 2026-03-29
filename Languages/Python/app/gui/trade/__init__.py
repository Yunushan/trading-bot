"""Trade runtime package for the Python desktop app.

New code should prefer the short helper modules in this package:
`trade_runtime`, `signal_runtime`, and `signal_open_runtime`.

The older `main_window_trade_*` helper modules remain as
compatibility wrappers while callers are migrated.
"""

__all__ = [
    "main_window_trade_runtime",
    "main_window_trade_signal_open_runtime",
    "main_window_trade_signal_runtime",
    "signal_open_runtime",
    "signal_runtime",
    "trade_runtime",
]
