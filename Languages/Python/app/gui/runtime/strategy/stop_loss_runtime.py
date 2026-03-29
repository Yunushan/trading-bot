from __future__ import annotations

from . import (
    stop_loss_backtest_context,
    stop_loss_runtime_context,
    stop_loss_shared_runtime,
)

_runtime_stop_loss_update = stop_loss_runtime_context._runtime_stop_loss_update
_update_runtime_stop_loss_widgets = stop_loss_runtime_context._update_runtime_stop_loss_widgets
_on_runtime_stop_loss_enabled = stop_loss_runtime_context._on_runtime_stop_loss_enabled
_on_runtime_stop_loss_mode_changed = stop_loss_runtime_context._on_runtime_stop_loss_mode_changed
_on_runtime_stop_loss_scope_changed = stop_loss_runtime_context._on_runtime_stop_loss_scope_changed
_on_runtime_stop_loss_value_changed = stop_loss_runtime_context._on_runtime_stop_loss_value_changed

_backtest_stop_loss_update = stop_loss_backtest_context._backtest_stop_loss_update
_update_backtest_stop_loss_widgets = stop_loss_backtest_context._update_backtest_stop_loss_widgets
_on_backtest_stop_loss_enabled = stop_loss_backtest_context._on_backtest_stop_loss_enabled
_on_backtest_stop_loss_mode_changed = stop_loss_backtest_context._on_backtest_stop_loss_mode_changed
_on_backtest_stop_loss_scope_changed = stop_loss_backtest_context._on_backtest_stop_loss_scope_changed
_on_backtest_stop_loss_value_changed = stop_loss_backtest_context._on_backtest_stop_loss_value_changed


def bind_main_window_stop_loss_runtime(
    main_window_cls,
    *,
    normalize_stop_loss_dict=None,
    stop_loss_mode_order=None,
    stop_loss_scope_options=None,
) -> None:
    stop_loss_shared_runtime.configure_main_window_stop_loss_shared_runtime(
        normalize_stop_loss_dict=normalize_stop_loss_dict,
        stop_loss_mode_order=stop_loss_mode_order,
        stop_loss_scope_options=stop_loss_scope_options,
    )

    main_window_cls._runtime_stop_loss_update = _runtime_stop_loss_update
    main_window_cls._update_runtime_stop_loss_widgets = _update_runtime_stop_loss_widgets
    main_window_cls._on_runtime_stop_loss_enabled = _on_runtime_stop_loss_enabled
    main_window_cls._on_runtime_stop_loss_mode_changed = _on_runtime_stop_loss_mode_changed
    main_window_cls._on_runtime_stop_loss_scope_changed = _on_runtime_stop_loss_scope_changed
    main_window_cls._on_runtime_stop_loss_value_changed = _on_runtime_stop_loss_value_changed
    main_window_cls._backtest_stop_loss_update = _backtest_stop_loss_update
    main_window_cls._update_backtest_stop_loss_widgets = _update_backtest_stop_loss_widgets
    main_window_cls._on_backtest_stop_loss_enabled = _on_backtest_stop_loss_enabled
    main_window_cls._on_backtest_stop_loss_mode_changed = _on_backtest_stop_loss_mode_changed
    main_window_cls._on_backtest_stop_loss_scope_changed = _on_backtest_stop_loss_scope_changed
    main_window_cls._on_backtest_stop_loss_value_changed = _on_backtest_stop_loss_value_changed
