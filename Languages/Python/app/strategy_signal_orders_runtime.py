from __future__ import annotations

try:
    from . import strategy_signal_order_collect_runtime
    from . import strategy_signal_order_prepare_runtime
    from . import strategy_signal_order_execute_runtime
except ImportError:  # pragma: no cover - standalone execution fallback
    import strategy_signal_order_collect_runtime
    import strategy_signal_order_prepare_runtime
    import strategy_signal_order_execute_runtime


def bind_strategy_signal_orders_runtime(
    strategy_cls,
    *,
    interval_to_seconds_fn,
    canonical_indicator_token_fn,
) -> None:
    strategy_cls._interval_to_seconds = staticmethod(interval_to_seconds_fn)
    strategy_cls._canonical_indicator_token = staticmethod(canonical_indicator_token_fn)
    strategy_signal_order_collect_runtime.bind_strategy_signal_order_collect_runtime(strategy_cls)
    strategy_signal_order_prepare_runtime.bind_strategy_signal_order_prepare_runtime(strategy_cls)
    strategy_signal_order_execute_runtime.bind_strategy_signal_order_execute_runtime(strategy_cls)
