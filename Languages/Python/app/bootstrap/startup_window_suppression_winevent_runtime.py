from __future__ import annotations

import os
import sys
from pathlib import Path

from .startup_window_suppression_shared_runtime import _env_flag

_STARTUP_WINDOW_HOOK = None
_STARTUP_WINDOW_PROC = None
_STARTUP_WINDOW_POLL_STOP = None
_STARTUP_WINDOW_POLL_THREAD = None


def _install_startup_window_suppression() -> None:
    global _STARTUP_WINDOW_HOOK, _STARTUP_WINDOW_PROC, _STARTUP_WINDOW_POLL_STOP, _STARTUP_WINDOW_POLL_THREAD
    if sys.platform != "win32":
        return
    if _STARTUP_WINDOW_HOOK is not None or _STARTUP_WINDOW_POLL_THREAD is not None:
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

    def _get_hwnd_pid(hwnd_obj) -> int:  # noqa: ANN001
        try:
            out_pid = wintypes.DWORD()
            user32.GetWindowThreadProcessId(hwnd_obj, ctypes.byref(out_pid))
            return int(out_pid.value)
        except Exception:
            return 0

    def _enum_descendant_pids(root_pid: int) -> set[int]:
        pids: set[int] = {int(root_pid)}
        if not root_pid:
            return pids
        try:
            TH32CS_SNAPPROCESS = 0x00000002
            snapshot = kernel32.CreateToolhelp32Snapshot(TH32CS_SNAPPROCESS, 0)
            if snapshot in (0, ctypes.c_void_p(-1).value):
                return pids

            class PROCESSENTRY32(ctypes.Structure):
                _fields_ = [
                    ("dwSize", wintypes.DWORD),
                    ("cntUsage", wintypes.DWORD),
                    ("th32ProcessID", wintypes.DWORD),
                    ("th32DefaultHeapID", ctypes.c_void_p),
                    ("th32ModuleID", wintypes.DWORD),
                    ("cntThreads", wintypes.DWORD),
                    ("th32ParentProcessID", wintypes.DWORD),
                    ("pcPriClassBase", wintypes.LONG),
                    ("dwFlags", wintypes.DWORD),
                    ("szExeFile", wintypes.WCHAR * 260),
                ]

            parent_to_children: dict[int, list[int]] = {}
            entry = PROCESSENTRY32()
            entry.dwSize = ctypes.sizeof(entry)
            try:
                if kernel32.Process32FirstW(snapshot, ctypes.byref(entry)):
                    while True:
                        child_pid = int(entry.th32ProcessID)
                        parent_pid = int(entry.th32ParentProcessID)
                        parent_to_children.setdefault(parent_pid, []).append(child_pid)
                        if not kernel32.Process32NextW(snapshot, ctypes.byref(entry)):
                            break
            finally:
                try:
                    kernel32.CloseHandle(snapshot)
                except Exception:
                    pass

            queue = [int(root_pid)]
            while queue:
                current = queue.pop()
                for child in parent_to_children.get(current, []):
                    if child not in pids:
                        pids.add(child)
                        queue.append(child)
        except Exception:
            return pids
        return pids

    tracked_lock = threading.Lock()
    tracked_pids: set[int] = {int(pid)}
    tracked_state = {"ts": 0.0}

    def _refresh_descendant_pids(force: bool = False) -> set[int]:
        now = time.monotonic()
        with tracked_lock:
            last_ts = float(tracked_state["ts"])
            if not force and (now - last_ts) < 0.2:
                return set(tracked_pids)
        refreshed = _enum_descendant_pids(pid)
        with tracked_lock:
            tracked_pids.clear()
            tracked_pids.update(refreshed)
            tracked_state["ts"] = now
            return set(tracked_pids)

    def _pid_is_tracked(pid_val: int) -> bool:
        if not pid_val:
            return False
        with tracked_lock:
            if pid_val in tracked_pids:
                return True
        return pid_val in _refresh_descendant_pids(force=False)

    def _log_window(hwnd_obj, reason: str) -> None:  # noqa: ANN001
        if not debug_window_events:
            return
        try:
            class_buf = ctypes.create_unicode_buffer(256)
            user32.GetClassNameW(hwnd_obj, class_buf, 256)
            try:
                vis = int(bool(user32.IsWindowVisible(hwnd_obj)))
            except Exception:
                vis = 0
            try:
                get_style = getattr(user32, "GetWindowLongPtrW", None) or user32.GetWindowLongW
                style_val = int(get_style(hwnd_obj, -16))
            except Exception:
                style_val = 0
            try:
                get_exstyle = getattr(user32, "GetWindowLongPtrW", None) or user32.GetWindowLongW
                exstyle_val = int(get_exstyle(hwnd_obj, -20))
            except Exception:
                exstyle_val = 0
            rect = wintypes.RECT()
            user32.GetWindowRect(hwnd_obj, ctypes.byref(rect))
            width = int(rect.right - rect.left)
            height = int(rect.bottom - rect.top)
            pid_val = _get_hwnd_pid(hwnd_obj)
            with open(debug_log_path, "a", encoding="utf-8", errors="ignore") as fh:
                fh.write(
                    f"{reason} hwnd={int(hwnd_obj)} pid={pid_val} "
                    f"class={class_buf.value!r} size={width}x{height} "
                    f"vis={vis} style=0x{style_val:08X} exstyle=0x{exstyle_val:08X}\n"
                )
        except Exception:
            return

    def _is_transient_startup_window(hwnd_obj) -> bool:  # noqa: ANN001
        try:
            rect = wintypes.RECT()
            if not user32.GetWindowRect(hwnd_obj, ctypes.byref(rect)):
                return False
            width = int(rect.right - rect.left)
            height = int(rect.bottom - rect.top)
            if width <= 0 or height <= 0:
                return False

            class_buf = ctypes.create_unicode_buffer(256)
            user32.GetClassNameW(hwnd_obj, class_buf, 256)
            class_name = (class_buf.value or "").strip()
            title_buf = ctypes.create_unicode_buffer(256)
            user32.GetWindowTextW(hwnd_obj, title_buf, 256)
            title = (title_buf.value or "").strip()

            try:
                GWL_STYLE = -16
                WS_CHILD = 0x40000000
                get_style = getattr(user32, "GetWindowLongPtrW", None) or user32.GetWindowLongW
                style = int(get_style(hwnd_obj, GWL_STYLE))
                if style & WS_CHILD:
                    return False
            except Exception:
                pass

            if class_name.startswith("Qt") and any(
                class_name.endswith(suffix)
                for suffix in (
                    "PowerDummyWindow",
                    "ClipboardView",
                    "ScreenChangeObserverWindow",
                    "ThemeChangeObserverWindow",
                )
            ):
                return True
            if class_name.startswith("QEventDispatcherWin32_"):
                return True
            if title.startswith("QEventDispatcherWin32_"):
                return True
            if class_name in {"ConsoleWindowClass", "PseudoConsoleWindow"}:
                return True
            if class_name.startswith("_q_"):
                return height <= 260 and width <= 3200
            if title.startswith("_q_"):
                return height <= 260 and width <= 3200
            if class_name == "Intermediate D3D Window":
                return height <= 500 and width <= 4000
            if class_name.startswith("Chrome_WidgetWin_"):
                return height <= 400 and width <= 4000
            if title.startswith("Qt") and any(
                title.endswith(suffix)
                for suffix in (
                    "PowerDummyWindow",
                    "ClipboardView",
                    "ScreenChangeObserverWindow",
                    "ThemeChangeObserverWindow",
                )
            ):
                return True
            if width >= 500 and height >= 300:
                return False

            return height <= 800 and width <= 4000
        except Exception:
            return False

    def _hide_hwnd(hwnd_obj) -> None:  # noqa: ANN001
        try:
            SWP_NOSIZE = 0x0001
            SWP_NOZORDER = 0x0004
            SWP_NOACTIVATE = 0x0010
            SWP_HIDEWINDOW = 0x0080
            SWP_ASYNCWINDOWPOS = 0x4000
            user32.SetWindowPos(
                hwnd_obj,
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
                user32.ShowWindowAsync(hwnd_obj, SW_HIDE)
            else:
                user32.ShowWindow(hwnd_obj, SW_HIDE)
        except Exception:
            pass

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
            if id_object != OBJID_WINDOW or not hwnd_obj:
                return
            is_create_event = int(event) == EVENT_OBJECT_CREATE
            hwnd_pid = _get_hwnd_pid(hwnd_obj)
            if not _pid_is_tracked(hwnd_pid):
                return
            if not is_create_event:
                try:
                    if not user32.IsWindowVisible(hwnd_obj):
                        return
                except Exception:
                    return
            if not _is_transient_startup_window(hwnd_obj):
                return
            reason = "hide-startup-create" if is_create_event else "hide-startup-show"
            _log_window(hwnd_obj, reason)
            _hide_hwnd(hwnd_obj)
        except Exception:
            return

    _refresh_descendant_pids(force=True)

    _STARTUP_WINDOW_PROC = WinEventProc(_win_event_proc)
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
            _STARTUP_WINDOW_PROC,
            hook_pid,
            0,
            WINEVENT_OUTOFCONTEXT,
        )
    _STARTUP_WINDOW_HOOK = hook if hook else None
    if _STARTUP_WINDOW_HOOK is None:
        _STARTUP_WINDOW_PROC = None

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
    _STARTUP_WINDOW_POLL_STOP = stop_event

    EnumWindowsProc = ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)

    def _poll_once() -> None:
        def _enum_cb(hwnd_obj, _lparam):  # noqa: ANN001
            try:
                hwnd_pid = _get_hwnd_pid(hwnd_obj)
                if not _pid_is_tracked(hwnd_pid):
                    return True
                try:
                    if not user32.IsWindowVisible(hwnd_obj):
                        return True
                except Exception:
                    return True
                if _is_transient_startup_window(hwnd_obj):
                    _hide_hwnd(hwnd_obj)
            except Exception:
                return True
            return True

        cb = EnumWindowsProc(_enum_cb)
        try:
            user32.EnumWindows(cb, 0)
        except Exception:
            pass

    def _poll_loop() -> None:
        start = time.monotonic()
        deadline = start + (max(200, poll_ms) / 1000.0)
        fast_deadline = start + (max(0, fast_ms) / 1000.0)
        next_pid_refresh = start
        while time.monotonic() < deadline and not stop_event.is_set():
            now = time.monotonic()
            if now >= next_pid_refresh:
                _refresh_descendant_pids(force=True)
                next_pid_refresh = now + 0.05
            _poll_once()
            sleep_s = (fast_interval_ms if now < fast_deadline else interval_ms) / 1000.0
            time.sleep(max(0.002, sleep_s))

    thread = threading.Thread(target=_poll_loop, name="startup-window-poll", daemon=True)
    _STARTUP_WINDOW_POLL_THREAD = thread
    thread.start()


def _uninstall_startup_window_suppression() -> None:
    global _STARTUP_WINDOW_HOOK, _STARTUP_WINDOW_PROC, _STARTUP_WINDOW_POLL_STOP, _STARTUP_WINDOW_POLL_THREAD
    if sys.platform != "win32":
        return
    if _STARTUP_WINDOW_HOOK is None and _STARTUP_WINDOW_POLL_STOP is None and _STARTUP_WINDOW_POLL_THREAD is None:
        return
    try:
        stop_event = _STARTUP_WINDOW_POLL_STOP
        if stop_event is not None:
            stop_event.set()
    except Exception:
        pass
    try:
        thread = _STARTUP_WINDOW_POLL_THREAD
        if thread is not None and getattr(thread, "is_alive", lambda: False)():
            try:
                thread.join(timeout=0.5)
            except Exception:
                pass
    except Exception:
        pass
    if _STARTUP_WINDOW_HOOK is not None:
        try:  # pragma: no cover - Windows only
            import ctypes

            ctypes.windll.user32.UnhookWinEvent(_STARTUP_WINDOW_HOOK)
        except Exception:
            pass
    _STARTUP_WINDOW_HOOK = None
    _STARTUP_WINDOW_PROC = None
    _STARTUP_WINDOW_POLL_STOP = None
    _STARTUP_WINDOW_POLL_THREAD = None
