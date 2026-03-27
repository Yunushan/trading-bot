"""Compatibility shim for the moved composition GUI runtime helpers."""

from .composition import main_window_module_state_runtime as _impl

for _shim_name in dir(_impl):
    if not _shim_name.startswith("__"):
        globals()[_shim_name] = getattr(_impl, _shim_name)

del _impl
