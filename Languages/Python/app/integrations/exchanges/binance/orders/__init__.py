"""Order helpers for the Binance integration."""

from importlib import import_module

_EXPORT_MODULES = {
    "bind_binance_futures_orders": ".futures_orders",
    "bind_binance_order_audit_runtime": ".order_audit_runtime",
    "bind_binance_order_fallback_runtime": ".order_fallback_runtime",
    "bind_binance_order_intent_runtime": ".order_intent_runtime",
    "bind_binance_order_sizing_runtime": ".order_sizing_runtime",
    "bind_binance_order_submit_guard_runtime": ".order_submit_guard_runtime",
}
__all__ = list(_EXPORT_MODULES)


def __getattr__(name: str):
    module_name = _EXPORT_MODULES.get(name)
    if module_name is None:
        raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
    value = getattr(import_module(module_name, __name__), name)
    globals()[name] = value
    return value


def __dir__() -> list[str]:
    return sorted(set(globals()) | set(__all__))
