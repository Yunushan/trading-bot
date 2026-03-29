"""Backward-compatible import shim for window log runtime helpers."""

from .log_runtime import (
    _gui_buffer_log,
    _gui_flush_log_buffer,
    _gui_setup_log_buffer,
    _is_trigger_log_line,
    _mw_format_display_time,
    _mw_interval_sort_key,
    _mw_parse_any_datetime,
)

__all__ = [
    "_gui_buffer_log",
    "_gui_flush_log_buffer",
    "_gui_setup_log_buffer",
    "_is_trigger_log_line",
    "_mw_format_display_time",
    "_mw_interval_sort_key",
    "_mw_parse_any_datetime",
]
