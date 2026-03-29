"""Backward-compatible import shim for UI secondary-tab helpers."""

from . import secondary_tabs_runtime as _impl

for _name in dir(_impl):
    if not _name.startswith("__"):
        globals()[_name] = getattr(_impl, _name)

del _impl
del _name
