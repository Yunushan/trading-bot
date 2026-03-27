"""Compatibility shim for the moved strategy trade-book helpers."""

from .positions import strategy_trade_book as _impl

for _shim_name in dir(_impl):
    if not _shim_name.startswith("__"):
        globals()[_shim_name] = getattr(_impl, _shim_name)

del _impl
