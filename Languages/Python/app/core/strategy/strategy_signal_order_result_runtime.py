"""Compatibility shim for the moved strategy order-result helpers."""

from .orders import strategy_signal_order_result_runtime as _impl

for _shim_name in dir(_impl):
    if not _shim_name.startswith("__"):
        globals()[_shim_name] = getattr(_impl, _shim_name)

del _impl
