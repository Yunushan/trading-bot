"""Compatibility shim for the moved strategy GUI runtime helpers."""

from .strategy import main_window_stop_loss_runtime as _impl

for _shim_name in dir(_impl):
    if not _shim_name.startswith("__"):
        globals()[_shim_name] = getattr(_impl, _shim_name)

del _impl
