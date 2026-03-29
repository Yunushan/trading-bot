from __future__ import annotations

import os

from . import (
    log_runtime as main_window_log_runtime,
    positions_runtime as main_window_positions_runtime,
    window_events_runtime as main_window_window_events_runtime,
)

_STRATEGY_ENGINE_CLS = None

_gui_setup_log_buffer = main_window_log_runtime._gui_setup_log_buffer
_gui_buffer_log = main_window_log_runtime._gui_buffer_log
_mw_parse_any_datetime = main_window_log_runtime._mw_parse_any_datetime
_mw_format_display_time = main_window_log_runtime._mw_format_display_time
_mw_interval_sort_key = main_window_log_runtime._mw_interval_sort_key
_is_trigger_log_line = main_window_log_runtime._is_trigger_log_line
_gui_flush_log_buffer = main_window_log_runtime._gui_flush_log_buffer

_mw_reconfigure_positions_worker = main_window_positions_runtime._mw_reconfigure_positions_worker
_mw_collect_strategy_intervals = main_window_positions_runtime._mw_collect_strategy_intervals
_mw_refresh_waiting_positions_tab = main_window_positions_runtime._mw_refresh_waiting_positions_tab


def _request_strategy_shutdown() -> None:
    return main_window_window_events_runtime.request_strategy_shutdown(_STRATEGY_ENGINE_CLS)


def _teardown_positions_thread(self):
    return main_window_window_events_runtime.teardown_positions_thread(self)


def _log_window_event(self, name: str, event=None) -> None:
    return main_window_window_events_runtime.log_window_event(self, name, event=event)


def _allow_guard_bypass(self) -> bool:
    return main_window_window_events_runtime.allow_guard_bypass(self)


def _mark_user_close_command(self) -> None:
    return main_window_window_events_runtime.mark_user_close_command(self)


def _is_recent_user_close_command(self) -> bool:
    return main_window_window_events_runtime.is_recent_user_close_command(self)


def _event_is_spontaneous(event) -> bool:  # noqa: ANN001
    return main_window_window_events_runtime.event_is_spontaneous(event)


def _active_spontaneous_close_block_until(self) -> float:
    return main_window_window_events_runtime.active_spontaneous_close_block_until(self)


def _extend_spontaneous_close_block(self, duration_ms: int = 5000) -> float:
    return main_window_window_events_runtime.extend_spontaneous_close_block(self, duration_ms=duration_ms)


def _restore_window_after_guard(self) -> None:
    return main_window_window_events_runtime.restore_window_after_guard(self)


def _active_close_protection_until(self) -> float:
    return main_window_window_events_runtime.active_close_protection_until(self)


def _should_block_spontaneous_close(self, event) -> bool:  # noqa: ANN001
    return main_window_window_events_runtime.should_block_spontaneous_close(self, event)


def _should_block_programmatic_hide(self) -> bool:
    return main_window_window_events_runtime.should_block_programmatic_hide(self)


def setVisible(self, visible):  # noqa: N802, ANN001
    return main_window_window_events_runtime.set_visible(self, visible)


def hide(self):  # noqa: ANN001
    return main_window_window_events_runtime.hide_window(self)


def nativeEvent(self, eventType, message):  # noqa: N802, ANN001
    return main_window_window_events_runtime.native_event(self, eventType, message)


def closeEvent(self, event):
    return main_window_window_events_runtime.close_event(
        self,
        event,
        strategy_engine_cls=_STRATEGY_ENGINE_CLS,
    )


def hideEvent(self, event):  # noqa: N802
    return main_window_window_events_runtime.hide_event(self, event)


def bind_main_window_runtime(
    main_window_cls,
    *,
    strategy_engine_cls,
    numeric_item_cls=None,
    waiting_position_late_threshold: float = 45.0,
) -> None:
    global _STRATEGY_ENGINE_CLS

    _STRATEGY_ENGINE_CLS = strategy_engine_cls
    main_window_positions_runtime.configure_main_window_positions_runtime(
        numeric_item_cls=numeric_item_cls,
        waiting_position_late_threshold=waiting_position_late_threshold,
    )

    _bind_window_event_methods(main_window_cls)
    _bind_log_runtime_methods(main_window_cls)
    _bind_position_runtime_methods(main_window_cls)


def _bind_window_event_methods(main_window_cls) -> None:
    main_window_cls._teardown_positions_thread = _teardown_positions_thread
    main_window_cls._log_window_event = _log_window_event
    main_window_cls._allow_guard_bypass = _allow_guard_bypass
    main_window_cls._mark_user_close_command = _mark_user_close_command
    main_window_cls._is_recent_user_close_command = _is_recent_user_close_command
    main_window_cls._event_is_spontaneous = _event_is_spontaneous
    main_window_cls._active_spontaneous_close_block_until = _active_spontaneous_close_block_until
    main_window_cls._extend_spontaneous_close_block = _extend_spontaneous_close_block
    main_window_cls._should_block_spontaneous_close = _should_block_spontaneous_close
    main_window_cls._restore_window_after_guard = _restore_window_after_guard
    main_window_cls._active_close_protection_until = _active_close_protection_until
    main_window_cls._should_block_programmatic_hide = _should_block_programmatic_hide
    main_window_cls.setVisible = setVisible
    main_window_cls.hide = hide
    if _native_close_detect_enabled():
        main_window_cls.nativeEvent = nativeEvent
    main_window_cls.closeEvent = closeEvent
    main_window_cls.hideEvent = hideEvent


def _bind_log_runtime_methods(main_window_cls) -> None:
    main_window_cls._setup_log_buffer = _gui_setup_log_buffer
    main_window_cls._buffer_log = _gui_buffer_log
    main_window_cls._parse_any_datetime = _mw_parse_any_datetime
    main_window_cls._format_display_time = _mw_format_display_time
    main_window_cls._flush_log_buffer = _gui_flush_log_buffer


def _bind_position_runtime_methods(main_window_cls) -> None:
    main_window_cls._reconfigure_positions_worker = _mw_reconfigure_positions_worker
    main_window_cls._collect_strategy_intervals = _mw_collect_strategy_intervals
    main_window_cls._refresh_waiting_positions_tab = _mw_refresh_waiting_positions_tab


def _native_close_detect_enabled() -> bool:
    return str(os.environ.get("BOT_ENABLE_NATIVE_CLOSE_DETECT", "")).strip().lower() in {
        "1",
        "true",
        "yes",
        "on",
    }
