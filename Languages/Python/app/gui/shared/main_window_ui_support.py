"""Backward-compatible import shim for shared UI support helpers."""

from . import ui_support as _impl

for _name in dir(_impl):
    if not _name.startswith("__"):
        globals()[_name] = getattr(_impl, _name)

del _impl
del _name
