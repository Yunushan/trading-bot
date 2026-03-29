from __future__ import annotations

import os
import sys
from pathlib import Path
from types import SimpleNamespace

from .startup_window_suppression_shared_runtime import _env_flag
from . import startup_window_suppression_winevent_poll_runtime as poll_runtime
from . import startup_window_suppression_winevent_state_runtime as winevent_state
from . import startup_window_suppression_winevent_window_runtime as window_runtime
from .startup_window_suppression_winevent_pid_runtime import TrackedPidRegistry


def _install_startup_window_suppression() -> None:
    if sys.platform != "win32":
        return
    if winevent_state._STARTUP_WINDOW_HOOK is not None or winevent_state._STARTUP_WINDOW_POLL_THREAD is not None:
        return
    if _env_flag("BOT_NO_STARTUP_WINDOW_SUPPRESS"):
        return
    disable_winevent_hook = _env_flag("BOT_NO_WINEVENT_STARTUP_WINDOW_SUPPRESS")

    try:  # pragma: no cover - Windows only
        import ctypes
        import ctypes.wintypes as wintypes
        import threading
        import time
    except Exception:
        return

    user32 = ctypes.windll.user32
    kernel32 = ctypes.windll.kernel32
    pid = int(kernel32.GetCurrentProcessId())

    debug_window_events = _env_flag("BOT_DEBUG_WINDOW_EVENTS")
    debug_log_path = Path(os.getenv("TEMP") or ".").resolve() / "binance_window_events.log"

    EVENT_OBJECT_CREATE = 0x8000
    EVENT_OBJECT_SHOW = 0x8002
    WINEVENT_OUTOFCONTEXT = 0x0000
    OBJID_WINDOW = 0
    SW_HIDE = 0

    try:
        user32.ShowWindowAsync.argtypes = [wintypes.HWND, ctypes.c_int]
        user32.ShowWindowAsync.restype = wintypes.BOOL
    except Exception:
        pass

    try:
        user32.SetWinEventHook.argtypes = [
            wintypes.DWORD,
            wintypes.DWORD,
            wintypes.HMODULE,
            ctypes.c_void_p,
            wintypes.DWORD,
            wintypes.DWORD,
            wintypes.DWORD,
        ]
        user32.SetWinEventHook.restype = wintypes.HANDLE
        user32.UnhookWinEvent.argtypes = [wintypes.HANDLE]
        user32.UnhookWinEvent.restype = wintypes.BOOL
    except Exception:
        pass

    try:
        user32.EnumWindows.argtypes = [ctypes.c_void_p, wintypes.LPARAM]
        user32.EnumWindows.restype = wintypes.BOOL
    except Exception:
        pass

    api = SimpleNamespace(
        ctypes=ctypes,
        wintypes=wintypes,
        user32=user32,
        kernel32=kernel32,
        threading=threading,
        time=time,
        debug_window_events=debug_window_events,
        debug_log_path=debug_log_path,
        EVENT_OBJECT_CREATE=EVENT_OBJECT_CREATE,
        EVENT_OBJECT_SHOW=EVENT_OBJECT_SHOW,
        WINEVENT_OUTOFCONTEXT=WINEVENT_OUTOFCONTEXT,
        OBJID_WINDOW=OBJID_WINDOW,
        SW_HIDE=SW_HIDE,
    )

    pid_registry = TrackedPidRegistry(api, pid)

    WinEventProc = ctypes.WINFUNCTYPE(
        None,
        wintypes.HANDLE,
        wintypes.DWORD,
        wintypes.HWND,
        wintypes.LONG,
        wintypes.LONG,
        wintypes.DWORD,
        wintypes.DWORD,
    )

    def _win_event_proc(_hook, event, hwnd_obj, id_object, _id_child, _thread, _time):  # noqa: ANN001
        try:
            if id_object != api.OBJID_WINDOW or not hwnd_obj:
                return
            is_create_event = int(event) == api.EVENT_OBJECT_CREATE
            hwnd_pid = window_runtime._get_hwnd_pid(api, hwnd_obj)
            if not pid_registry.contains(hwnd_pid):
                return
            if not is_create_event:
                try:
                    if not api.user32.IsWindowVisible(hwnd_obj):
                        return
                except Exception:
                    return
            if not window_runtime._is_transient_startup_window(api, hwnd_obj):
                return
            reason = "hide-startup-create" if is_create_event else "hide-startup-show"
            window_runtime._log_window(api, hwnd_obj, reason)
            window_runtime._hide_hwnd(api, hwnd_obj)
        except Exception:
            return

    pid_registry.refresh(force=True)

    winevent_state._STARTUP_WINDOW_PROC = WinEventProc(_win_event_proc)
    hook = 0
    if not disable_winevent_hook:
        use_global_hook = str(os.environ.get("BOT_STARTUP_WINDOW_SUPPRESS_GLOBAL_HOOK", "")).strip().lower() not in {
            "0",
            "false",
            "no",
            "off",
        }
        hook_pid = 0 if use_global_hook else pid
        hook = user32.SetWinEventHook(
            EVENT_OBJECT_CREATE,
            EVENT_OBJECT_SHOW,
            0,
            winevent_state._STARTUP_WINDOW_PROC,
            hook_pid,
            0,
            WINEVENT_OUTOFCONTEXT,
        )
    winevent_state._STARTUP_WINDOW_HOOK = hook if hook else None
    if winevent_state._STARTUP_WINDOW_HOOK is None:
        winevent_state._STARTUP_WINDOW_PROC = None

    try:
        suppress_ms = int(os.environ.get("BOT_STARTUP_WINDOW_SUPPRESS_DURATION_MS") or 8000)
    except Exception:
        suppress_ms = 8000
    suppress_ms = max(500, min(suppress_ms, 30000))
    try:
        poll_ms = int(os.environ.get("BOT_STARTUP_WINDOW_POLL_MS") or suppress_ms)
    except Exception:
        poll_ms = suppress_ms
    try:
        interval_ms = int(os.environ.get("BOT_STARTUP_WINDOW_POLL_INTERVAL_MS") or 30)
    except Exception:
        interval_ms = 30
    poll_ms = max(200, min(poll_ms, suppress_ms))
    interval_ms = max(20, min(interval_ms, 200))
    try:
        fast_ms = int(os.environ.get("BOT_STARTUP_WINDOW_POLL_FAST_MS") or 1200)
    except Exception:
        fast_ms = 1200
    fast_ms = max(0, min(fast_ms, poll_ms))
    try:
        fast_interval_ms = int(os.environ.get("BOT_STARTUP_WINDOW_POLL_FAST_INTERVAL_MS") or 10)
    except Exception:
        fast_interval_ms = 10
    fast_interval_ms = max(5, min(fast_interval_ms, interval_ms))

    stop_event = threading.Event()
    winevent_state._STARTUP_WINDOW_POLL_STOP = stop_event
    winevent_state._STARTUP_WINDOW_POLL_THREAD = poll_runtime.start_poll_thread(
        api,
        pid_registry,
        poll_ms=poll_ms,
        interval_ms=interval_ms,
        fast_ms=fast_ms,
        fast_interval_ms=fast_interval_ms,
        stop_event=stop_event,
    )


def _uninstall_startup_window_suppression() -> None:
    if sys.platform != "win32":
        return
    if (
        winevent_state._STARTUP_WINDOW_HOOK is None
        and winevent_state._STARTUP_WINDOW_POLL_STOP is None
        and winevent_state._STARTUP_WINDOW_POLL_THREAD is None
    ):
        return
    try:
        stop_event = winevent_state._STARTUP_WINDOW_POLL_STOP
        if stop_event is not None:
            stop_event.set()
    except Exception:
        pass
    try:
        thread = winevent_state._STARTUP_WINDOW_POLL_THREAD
        if thread is not None and getattr(thread, "is_alive", lambda: False)():
            try:
                thread.join(timeout=0.5)
            except Exception:
                pass
    except Exception:
        pass
    if winevent_state._STARTUP_WINDOW_HOOK is not None:
        try:  # pragma: no cover - Windows only
            import ctypes

            ctypes.windll.user32.UnhookWinEvent(winevent_state._STARTUP_WINDOW_HOOK)
        except Exception:
            pass
    winevent_state._STARTUP_WINDOW_HOOK = None
    winevent_state._STARTUP_WINDOW_PROC = None
    winevent_state._STARTUP_WINDOW_POLL_STOP = None
    winevent_state._STARTUP_WINDOW_POLL_THREAD = None
