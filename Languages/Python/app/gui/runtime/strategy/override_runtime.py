from __future__ import annotations

from . import (
    override_actions_runtime,
    override_shared_runtime,
    override_table_runtime,
    override_ui_runtime,
)

_normalize_stop_loss = override_shared_runtime._normalize_stop_loss
_normalize_indicator_values_list = override_shared_runtime._normalize_indicator_values_list
_format_indicator_list_text = override_shared_runtime._format_indicator_list_text
_normalize_connector_backend_value = override_shared_runtime._normalize_connector_backend_value
_override_ctx = override_shared_runtime._override_ctx
_override_config_list = override_shared_runtime._override_config_list
_get_selected_indicator_keys = override_shared_runtime._get_selected_indicator_keys

_refresh_symbol_interval_pairs = override_table_runtime._refresh_symbol_interval_pairs

_add_selected_symbol_interval_pairs = override_actions_runtime._add_selected_symbol_interval_pairs
_remove_selected_symbol_interval_pairs = override_actions_runtime._remove_selected_symbol_interval_pairs
_clear_symbol_interval_pairs = override_actions_runtime._clear_symbol_interval_pairs

_create_override_group = override_ui_runtime._create_override_group


def bind_main_window_override_runtime(
    main_window_cls,
    *,
    format_indicator_list=None,
    normalize_connector_backend=None,
    normalize_indicator_values=None,
    normalize_stop_loss_dict=None,
) -> None:
    override_shared_runtime.configure_main_window_override_shared_runtime(
        format_indicator_list=format_indicator_list,
        normalize_connector_backend=normalize_connector_backend,
        normalize_indicator_values=normalize_indicator_values,
        normalize_stop_loss_dict=normalize_stop_loss_dict,
    )

    main_window_cls._override_ctx = _override_ctx
    main_window_cls._override_config_list = _override_config_list
    main_window_cls._get_selected_indicator_keys = _get_selected_indicator_keys
    main_window_cls._refresh_symbol_interval_pairs = _refresh_symbol_interval_pairs
    main_window_cls._add_selected_symbol_interval_pairs = _add_selected_symbol_interval_pairs
    main_window_cls._remove_selected_symbol_interval_pairs = _remove_selected_symbol_interval_pairs
    main_window_cls._clear_symbol_interval_pairs = _clear_symbol_interval_pairs
    main_window_cls._create_override_group = _create_override_group
