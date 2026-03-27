"""Compatibility shim for the moved window GUI runtime helpers."""

from .window import window_code_tab_suppression_runtime as _impl

for _shim_name in dir(_impl):
    if not _shim_name.startswith("__"):
        globals()[_shim_name] = getattr(_impl, _shim_name)

del _impl
