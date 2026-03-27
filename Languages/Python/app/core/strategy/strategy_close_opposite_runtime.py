"""Compatibility shim for the moved strategy close-opposite helpers."""

from .positions import strategy_close_opposite_runtime as _impl

for _shim_name in dir(_impl):
    if not _shim_name.startswith("__"):
        globals()[_shim_name] = getattr(_impl, _shim_name)

del _impl
