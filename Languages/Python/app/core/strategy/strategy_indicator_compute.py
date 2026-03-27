"""Compatibility shim for the moved strategy indicator-compute helpers."""

from .runtime import strategy_indicator_compute as _impl

for _shim_name in dir(_impl):
    if not _shim_name.startswith("__"):
        globals()[_shim_name] = getattr(_impl, _shim_name)

del _impl
