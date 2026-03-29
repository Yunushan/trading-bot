from __future__ import annotations

from . import control_actions_runtime, control_lifecycle_runtime, control_shared_runtime

on_leverage_changed = control_actions_runtime.on_leverage_changed
refresh_symbols = control_actions_runtime.refresh_symbols
apply_futures_modes = control_actions_runtime.apply_futures_modes

start_strategy = control_lifecycle_runtime.start_strategy
_stop_strategy_sync = control_lifecycle_runtime._stop_strategy_sync
stop_strategy_async = control_lifecycle_runtime.stop_strategy_async


def bind_main_window_control_runtime(
    main_window_cls,
    *,
    strategy_engine_cls=None,
    make_engine_key=None,
    coerce_bool=None,
    normalize_stop_loss_dict=None,
    format_indicator_list=None,
    symbol_fetch_top_n: int = 200,
) -> None:
    control_shared_runtime.configure_main_window_control_shared_runtime(
        strategy_engine_cls=strategy_engine_cls,
        make_engine_key=make_engine_key,
        coerce_bool=coerce_bool,
        normalize_stop_loss_dict=normalize_stop_loss_dict,
        format_indicator_list=format_indicator_list,
        symbol_fetch_top_n=symbol_fetch_top_n,
    )

    main_window_cls.on_leverage_changed = on_leverage_changed
    main_window_cls.refresh_symbols = refresh_symbols
    main_window_cls.apply_futures_modes = apply_futures_modes
    main_window_cls.start_strategy = start_strategy
    main_window_cls._stop_strategy_sync = _stop_strategy_sync
    main_window_cls.stop_strategy_async = stop_strategy_async
