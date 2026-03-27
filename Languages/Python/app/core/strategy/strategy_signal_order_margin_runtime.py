"""Compatibility shim for the moved strategy order-margin helpers."""

from .orders import strategy_signal_order_margin_runtime as _impl

for _shim_name in dir(_impl):
    if not _shim_name.startswith("__"):
        globals()[_shim_name] = getattr(_impl, _shim_name)

del _impl
