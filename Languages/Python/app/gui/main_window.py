"""Backward-compatible import shim for the main GUI window module."""

from . import window_shell as _impl

for _name in dir(_impl):
    if not (_name.startswith("__") and _name.endswith("__")):
        globals()[_name] = getattr(_impl, _name)

del _impl
del _name
