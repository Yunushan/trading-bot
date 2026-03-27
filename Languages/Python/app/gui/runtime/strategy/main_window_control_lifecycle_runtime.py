from __future__ import annotations

from . import (
    main_window_control_shared_runtime,
    main_window_start_strategy_runtime,
    main_window_stop_strategy_runtime,
)


def start_strategy(self):
    return main_window_start_strategy_runtime.start_strategy(
        self,
        strategy_engine_cls=main_window_control_shared_runtime._get_strategy_engine_cls(),
        make_engine_key=main_window_control_shared_runtime._make_engine_key_safe,
        coerce_bool=main_window_control_shared_runtime._coerce_bool_safe,
        normalize_stop_loss_dict=main_window_control_shared_runtime._normalize_stop_loss_dict_safe,
        format_indicator_list=main_window_control_shared_runtime._format_indicator_list_safe,
    )


def _stop_strategy_sync(self, close_positions: bool = True, auth: dict | None = None) -> dict:
    return main_window_stop_strategy_runtime.stop_strategy_sync(
        self,
        close_positions=close_positions,
        auth=auth,
        strategy_engine_cls=main_window_control_shared_runtime._get_strategy_engine_cls(),
    )


def stop_strategy_async(self, close_positions: bool = False, blocking: bool = False):
    return main_window_stop_strategy_runtime.stop_strategy_async(
        self,
        close_positions=close_positions,
        blocking=blocking,
        stop_strategy_sync_fn=lambda **kwargs: _stop_strategy_sync(self, **kwargs),
    )
