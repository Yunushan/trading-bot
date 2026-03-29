"""Code and dependency tooling package for the Python desktop app.

New code should prefer the short helper modules `runtime` and
`tab_runtime` for the main code-tab surfaces.

The older `main_window_code*` modules remain as compatibility
wrappers while callers are migrated.
"""

__all__ = [
    "main_window_code",
    "main_window_code_runtime",
    "runtime",
    "tab_runtime",
]
