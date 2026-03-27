"""Compatibility shim for the moved strategy signal-generation helpers."""

from .runtime import strategy_signal_generation as _impl

for _shim_name in dir(_impl):
    if not _shim_name.startswith("__"):
        globals()[_shim_name] = getattr(_impl, _shim_name)

del _impl
