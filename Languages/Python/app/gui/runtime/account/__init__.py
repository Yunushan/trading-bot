"""Account-oriented GUI runtime helpers.

New code should prefer the short helper modules in this package:
`account_runtime`, `balance_runtime`, and `margin_runtime`.

The older `main_window_*` account modules remain as compatibility
wrappers while callers are migrated.
"""

__all__ = [
    "account_runtime",
    "balance_runtime",
    "main_window_account_runtime",
    "main_window_balance_runtime",
    "main_window_margin_runtime",
    "margin_runtime",
]
