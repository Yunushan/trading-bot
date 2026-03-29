"""Backward-compatible facade for split startup UI/bootstrap helpers."""

from .startup_cover_runtime import _NativeStartupCover, _show_native_startup_cover
from .startup_icon_runtime import (
    _apply_qt_icon,
    _format_shortcut_args,
    _get_hwnd,
    _persist_icon_for_taskbar,
    _resolve_native_icon_path,
    _resolve_taskbar_icon_path,
    _schedule_icon_enforcer,
    _set_native_window_icon,
    _stable_icon_cache_path,
)
from .startup_splash_ui import (
    _SplashScreen,
    _make_splash_widget_class,
    _resolve_splash_logo_pixmap,
)
from .startup_ui_shared import APP_DISPLAY_NAME, _boot_log, _env_flag

__all__ = [
    "APP_DISPLAY_NAME",
    "_NativeStartupCover",
    "_SplashScreen",
    "_apply_qt_icon",
    "_boot_log",
    "_env_flag",
    "_format_shortcut_args",
    "_get_hwnd",
    "_make_splash_widget_class",
    "_persist_icon_for_taskbar",
    "_resolve_native_icon_path",
    "_resolve_splash_logo_pixmap",
    "_resolve_taskbar_icon_path",
    "_schedule_icon_enforcer",
    "_set_native_window_icon",
    "_show_native_startup_cover",
    "_stable_icon_cache_path",
]


def __getattr__(name: str):
    if name == "_SplashWidget":
        from . import startup_splash_ui

        return startup_splash_ui._SplashWidget
    raise AttributeError(name)
