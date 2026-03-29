from __future__ import annotations

import sys

from . import startup_window_suppression_cbt_state_runtime as cbt_state


def uninstall_cbt_startup_window_suppression() -> None:
    if sys.platform != "win32" or cbt_state._CBT_STARTUP_WINDOW_PROC is None:
        return
    try:
        stop_event = cbt_state._CBT_STARTUP_WINDOW_SCAN_STOP
        if stop_event is not None:
            stop_event.set()
    except Exception:
        pass
    try:
        thread = cbt_state._CBT_STARTUP_WINDOW_SCAN_THREAD
        if thread is not None and getattr(thread, "is_alive", lambda: False)():
            try:
                thread.join(timeout=0.5)
            except Exception:
                pass
    except Exception:
        pass
    try:
        stop_event = cbt_state._CBT_STARTUP_HELPER_COVER_STOP
        if stop_event is not None:
            stop_event.set()
    except Exception:
        pass
    try:
        thread = cbt_state._CBT_STARTUP_HELPER_COVER_THREAD
        if thread is not None and getattr(thread, "is_alive", lambda: False)():
            try:
                thread.join(timeout=0.5)
            except Exception:
                pass
    except Exception:
        pass
    try:  # pragma: no cover - Windows only
        import ctypes

        user32 = ctypes.windll.user32
        hooks = list(cbt_state._CBT_STARTUP_WINDOW_HOOKS.values())
        if cbt_state._CBT_STARTUP_WINDOW_LOCK is not None:
            try:
                with cbt_state._CBT_STARTUP_WINDOW_LOCK:
                    cbt_state._CBT_STARTUP_WINDOW_HOOKS.clear()
            except Exception:
                pass
        for hook in hooks:
            try:
                user32.UnhookWindowsHookEx(hook)
            except Exception:
                pass
        helper_covers = list(cbt_state._CBT_STARTUP_HELPER_COVERS.items())
        for (_left, _top, _width, _height), info in helper_covers:
            hwnd = int(info.get("hwnd") or 0)
            if not hwnd:
                continue
            try:
                SWP_NOSIZE = 0x0001
                SWP_NOZORDER = 0x0004
                SWP_NOACTIVATE = 0x0010
                SWP_HIDEWINDOW = 0x0080
                SWP_ASYNCWINDOWPOS = 0x4000
                user32.SetWindowPos(
                    hwnd,
                    0,
                    -32000,
                    -32000,
                    0,
                    0,
                    SWP_NOSIZE | SWP_NOZORDER | SWP_NOACTIVATE | SWP_HIDEWINDOW | SWP_ASYNCWINDOWPOS,
                )
            except Exception:
                pass
            try:
                if getattr(user32, "ShowWindowAsync", None):
                    user32.ShowWindowAsync(hwnd, 0)
                else:
                    user32.ShowWindow(hwnd, 0)
            except Exception:
                pass
    except Exception:
        pass
    cbt_state._CBT_STARTUP_WINDOW_HOOKS.clear()
    cbt_state._CBT_STARTUP_HELPER_COVERS.clear()
    cbt_state._CBT_STARTUP_WINDOW_PROC = None
    cbt_state._CBT_STARTUP_WINDOW_SCAN_STOP = None
    cbt_state._CBT_STARTUP_WINDOW_SCAN_THREAD = None
    cbt_state._CBT_STARTUP_WINDOW_LOCK = None
    cbt_state._CBT_STARTUP_HELPER_COVER_LOCK = None
    cbt_state._CBT_STARTUP_HELPER_COVER_STOP = None
    cbt_state._CBT_STARTUP_HELPER_COVER_THREAD = None
