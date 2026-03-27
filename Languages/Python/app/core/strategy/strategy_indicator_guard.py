"""Compatibility shim for the moved strategy indicator-guard helpers."""

from .positions import strategy_indicator_guard as _impl

for _shim_name in dir(_impl):
    if not _shim_name.startswith("__"):
        globals()[_shim_name] = getattr(_impl, _shim_name)

del _impl
