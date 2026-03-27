from __future__ import annotations

from . import (
    main_window_strategy_controls_collect_runtime,
    main_window_strategy_controls_format_runtime,
    main_window_strategy_controls_shared_runtime,
)

_normalize_stop_loss = main_window_strategy_controls_shared_runtime._normalize_stop_loss
_normalize_connector_backend_value = (
    main_window_strategy_controls_shared_runtime._normalize_connector_backend_value
)
_normalize_position_pct_units = (
    main_window_strategy_controls_shared_runtime._normalize_position_pct_units
)

_collect_strategy_controls = main_window_strategy_controls_collect_runtime._collect_strategy_controls
_prepare_controls_snapshot = main_window_strategy_controls_collect_runtime._prepare_controls_snapshot

_override_debug_enabled = main_window_strategy_controls_format_runtime._override_debug_enabled
_log_override_debug = main_window_strategy_controls_format_runtime._log_override_debug
_normalize_strategy_controls = main_window_strategy_controls_format_runtime._normalize_strategy_controls
_format_strategy_controls_summary = (
    main_window_strategy_controls_format_runtime._format_strategy_controls_summary
)


def bind_main_window_strategy_controls_runtime(
    main_window_cls,
    *,
    side_labels=None,
    normalize_stop_loss_dict=None,
    normalize_connector_backend=None,
) -> None:
    main_window_strategy_controls_shared_runtime.configure_main_window_strategy_controls_shared_runtime(
        side_labels=side_labels,
        normalize_stop_loss_dict=normalize_stop_loss_dict,
        normalize_connector_backend=normalize_connector_backend,
    )

    main_window_cls._collect_strategy_controls = _collect_strategy_controls
    main_window_cls._prepare_controls_snapshot = _prepare_controls_snapshot
    main_window_cls._override_debug_enabled = _override_debug_enabled
    main_window_cls._log_override_debug = _log_override_debug
    main_window_cls._normalize_strategy_controls = _normalize_strategy_controls
    main_window_cls._format_strategy_controls_summary = _format_strategy_controls_summary
    main_window_cls._normalize_position_pct_units = staticmethod(_normalize_position_pct_units)
