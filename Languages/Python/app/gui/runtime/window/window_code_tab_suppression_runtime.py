from __future__ import annotations

import os
import sys

from PyQt6 import QtCore

from . import (
    window_code_tab_cbt_runtime,
    window_code_tab_transient_runtime,
)

start_windows_thread_cbt_window_suppression = (
    window_code_tab_cbt_runtime.start_windows_thread_cbt_window_suppression
)
start_windows_transient_window_suppression = (
    window_code_tab_transient_runtime.start_windows_transient_window_suppression
)


def start_code_tab_window_suppression(self) -> None:
    start_windows_thread_cbt_window_suppression(
        self,
        hook_attr="_code_tab_window_cbt_hook",
        proc_attr="_code_tab_window_cbt_proc",
        timer_attr="_code_tab_window_cbt_timer",
        enabled_env="BOT_CODE_TAB_CBT_WINDOW_SUPPRESS",
        default_enabled=True,
        duration_env="BOT_CODE_TAB_CBT_WINDOW_SUPPRESS_MS",
        default_duration_ms=2800,
        debug_env="BOT_DEBUG_CODE_TAB_WINDOWS",
        debug_log_name="binance_code_tab_windows.log",
    )
    start_windows_transient_window_suppression(
        self,
        active_attr="_code_tab_window_suppress_active",
        timer_attr="_code_tab_window_suppress_timer",
        enabled_env="BOT_CODE_TAB_WINDOW_SUPPRESS",
        default_enabled=True,
        duration_env="BOT_CODE_TAB_WINDOW_SUPPRESS_MS",
        default_duration_ms=2200,
        interval_env="BOT_CODE_TAB_WINDOW_SUPPRESS_INTERVAL_MS",
        default_interval_ms=5,
        debug_env="BOT_DEBUG_CODE_TAB_WINDOWS",
        debug_log_name="binance_code_tab_windows.log",
        fallback_height_limit=260,
    )
    if sys.platform != "win32":
        return
    if getattr(self, "_code_tab_winevent_suppressor", None) is not None:
        return
    try:
        from ....bootstrap.startup_pre_qt_window_suppression_runtime import _PreQtWinEventSuppressor
    except Exception:
        return
    try:
        suppressor = _PreQtWinEventSuppressor()
        try:
            suppressor.add_known_ok_hwnd(int(self.winId()))
        except Exception:
            pass
        suppressor.start(ready_timeout_s=0.2)
        self._code_tab_winevent_suppressor = suppressor
    except Exception:
        return

    try:
        duration_ms = int(os.environ.get("BOT_CODE_TAB_WINEVENT_SUPPRESS_MS") or 3200)
    except Exception:
        duration_ms = 3200
    duration_ms = max(500, min(duration_ms, 5000))

    def _stop() -> None:
        current = getattr(self, "_code_tab_winevent_suppressor", None)
        if current is not suppressor:
            return
        try:
            current.stop()
        except Exception:
            pass
        self._code_tab_winevent_suppressor = None

    QtCore.QTimer.singleShot(duration_ms, _stop)


def stop_code_tab_window_suppression(self) -> None:
    if sys.platform != "win32":
        return
    timer = getattr(self, "_code_tab_window_suppress_timer", None)
    if timer is not None:
        try:
            timer.stop()
        except Exception:
            pass
        try:
            timer.deleteLater()
        except Exception:
            pass
    self._code_tab_window_suppress_timer = None
    self._code_tab_window_suppress_active = False

    cbt_timer = getattr(self, "_code_tab_window_cbt_timer", None)
    if cbt_timer is not None:
        try:
            cbt_timer.stop()
        except Exception:
            pass
    hook_value = getattr(self, "_code_tab_window_cbt_hook", None)
    if hook_value:
        try:
            import ctypes

            ctypes.windll.user32.UnhookWindowsHookEx(hook_value)
        except Exception:
            pass
    self._code_tab_window_cbt_hook = None
    self._code_tab_window_cbt_proc = None
    if cbt_timer is not None:
        try:
            cbt_timer.deleteLater()
        except Exception:
            pass
    self._code_tab_window_cbt_timer = None

    suppressor = getattr(self, "_code_tab_winevent_suppressor", None)
    if suppressor is not None:
        try:
            suppressor.stop()
        except Exception:
            pass
    self._code_tab_winevent_suppressor = None
