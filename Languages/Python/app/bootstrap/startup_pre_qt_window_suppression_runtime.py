from __future__ import annotations

import os
import sys
import threading
import time
from pathlib import Path


def _env_flag(name: str) -> bool:
    return str(os.environ.get(name, "")).strip().lower() in {"1", "true", "yes", "on"}


class _PreQtWinEventSuppressor:
    def __init__(self) -> None:
        self._known_ok: set[int] = set()
        self._ready = None
        self._stop = False
        self._thread = None

    def add_known_ok_hwnd(self, hwnd_value: int) -> None:
        try:
            hwnd_int = int(hwnd_value)
        except Exception:
            return
        if hwnd_int:
            self._known_ok.add(hwnd_int)

    def start(self, *, ready_timeout_s: float = 0.5) -> None:
        if sys.platform != "win32" or self._thread is not None:
            return
        self._ready = threading.Event()
        self._thread = threading.Thread(
            target=self._run,
            name="pre-qt-winevent-suppress",
            daemon=True,
        )
        self._thread.start()
        try:
            self._ready.wait(timeout=max(0.0, float(ready_timeout_s)))
        except Exception:
            pass

    def stop(self) -> None:
        self._stop = True

    def _run(self) -> None:
        if sys.platform != "win32":
            if self._ready is not None:
                self._ready.set()
            return

        try:
            import ctypes
            import ctypes.wintypes as wintypes
        except Exception:
            if self._ready is not None:
                self._ready.set()
            return

        try:
            user32 = ctypes.windll.user32
            kernel32 = ctypes.windll.kernel32
            pid = int(kernel32.GetCurrentProcessId())
            known_ok = self._known_ok
            debug_window_events = _env_flag("BOT_DEBUG_WINDOW_EVENTS")
            debug_log_path = Path(os.getenv("TEMP") or ".").resolve() / "binance_window_events.log"
            candidate_titles = {
                str(Path(sys.executable).stem or "").strip().lower(),
                str(Path(sys.argv[0]).stem or "").strip().lower() if sys.argv else "",
                str(os.environ.get("BOT_TASKBAR_DISPLAY_NAME") or "").strip().lower(),
            }
            candidate_titles.discard("")

            SW_HIDE = 0
            GWL_STYLE = -16
            GWL_EXSTYLE = -20
            WS_CHILD = 0x40000000
            WS_VISIBLE = 0x10000000
            EVENT_OBJECT_CREATE = 0x8000
            EVENT_OBJECT_SHOW = 0x8002
            WINEVENT_OUTOFCONTEXT = 0x0000
            get_style = getattr(user32, "GetWindowLongPtrW", None) or user32.GetWindowLongW
            get_exstyle = getattr(user32, "GetWindowLongPtrW", None) or user32.GetWindowLongW
            try:
                user32.EnumWindows.argtypes = [ctypes.c_void_p, wintypes.LPARAM]
                user32.EnumWindows.restype = wintypes.BOOL
            except Exception:
                pass

            def _enum_descendant_pids(root_pid: int) -> set[int]:
                tracked: set[int] = {int(root_pid)}
                if not root_pid:
                    return tracked
                try:
                    TH32CS_SNAPPROCESS = 0x00000002
                    snapshot = kernel32.CreateToolhelp32Snapshot(TH32CS_SNAPPROCESS, 0)
                    if snapshot in (0, ctypes.c_void_p(-1).value):
                        return tracked

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
                        for child_pid in parent_to_children.get(current, []):
                            if child_pid not in tracked:
                                tracked.add(child_pid)
                                queue.append(child_pid)
                except Exception:
                    return tracked
                return tracked

            tracked_lock = threading.Lock()
            tracked_state = {"pids": {int(pid)}, "ts": 0.0}

            def _refresh_descendant_pids(force: bool = False) -> set[int]:
                now = time.monotonic()
                with tracked_lock:
                    last_ts = float(tracked_state["ts"])
                    if not force and (now - last_ts) < 0.1:
                        return set(tracked_state["pids"])
                refreshed = _enum_descendant_pids(int(pid))
                with tracked_lock:
                    tracked_state["pids"] = set(refreshed)
                    tracked_state["ts"] = now
                    return set(refreshed)

            def _pid_is_tracked(pid_value: int) -> bool:
                if not pid_value:
                    return False
                with tracked_lock:
                    if int(pid_value) in tracked_state["pids"]:
                        return True
                return int(pid_value) in _refresh_descendant_pids(force=False)

            def _window_text(hwnd_value: int) -> str:
                try:
                    buf = ctypes.create_unicode_buffer(256)
                    user32.GetWindowTextW(wintypes.HWND(int(hwnd_value)), buf, 256)
                    return str(buf.value or "").strip()
                except Exception:
                    return ""

            def _window_class(hwnd_value: int) -> str:
                try:
                    buf = ctypes.create_unicode_buffer(256)
                    user32.GetClassNameW(wintypes.HWND(int(hwnd_value)), buf, 256)
                    return str(buf.value or "").strip()
                except Exception:
                    return ""

            def _is_tiny_helper_window(hwnd_value: int) -> bool:
                try:
                    rect = wintypes.RECT()
                    if not user32.GetWindowRect(wintypes.HWND(int(hwnd_value)), ctypes.byref(rect)):
                        return False
                    width = int(rect.right - rect.left)
                    height = int(rect.bottom - rect.top)
                    if width <= 0 or height <= 0:
                        return False
                    try:
                        style = int(get_style(wintypes.HWND(int(hwnd_value)), GWL_STYLE))
                    except Exception:
                        style = 0
                    if style & WS_CHILD:
                        return False
                    class_name = _window_class(hwnd_value)
                    title = _window_text(hwnd_value)
                    if class_name == "_q_titlebar" or title == "_q_titlebar":
                        return True
                    if class_name.startswith("QEventDispatcherWin32_") or title.startswith("QEventDispatcherWin32_"):
                        return True
                    lowered_title = title.lower()
                    if class_name.startswith("Qt") and class_name.endswith("QWindowIcon"):
                        if lowered_title in candidate_titles:
                            return height <= 720 and width <= 1800
                    qt_suffixes = (
                        "PowerDummyWindow",
                        "ClipboardView",
                        "ScreenChangeObserverWindow",
                        "ThemeChangeObserverWindow",
                        "QWindowToolSaveBits",
                    )
                    if class_name.startswith("Qt") and any(class_name.endswith(suffix) for suffix in qt_suffixes):
                        return True
                    if title.startswith("Qt") and any(title.endswith(suffix) for suffix in qt_suffixes):
                        return True
                    if class_name in {"ConsoleWindowClass", "PseudoConsoleWindow"}:
                        return True
                    if class_name == "Intermediate D3D Window":
                        return height <= 500 and width <= 4000
                    if class_name.startswith("Chrome_WidgetWin_"):
                        return height <= 400 and width <= 4000
                    try:
                        exstyle = int(get_exstyle(wintypes.HWND(int(hwnd_value)), GWL_EXSTYLE))
                    except Exception:
                        exstyle = 0
                    if width >= 500 and height >= 300 and not (exstyle & 0x00000080):
                        return False
                    return height <= 260 and width <= 3200
                except Exception:
                    return False

            def _hide_window(hwnd_value: int) -> None:
                try:
                    user32.MoveWindow(wintypes.HWND(int(hwnd_value)), -32000, -32000, 1, 1, False)
                except Exception:
                    pass
                try:
                    user32.ShowWindow(wintypes.HWND(int(hwnd_value)), SW_HIDE)
                except Exception:
                    pass

            def _log_window_event(hwnd_value: int, reason: str) -> None:
                if not debug_window_events:
                    return
                try:
                    rect = wintypes.RECT()
                    user32.GetWindowRect(wintypes.HWND(int(hwnd_value)), ctypes.byref(rect))
                    width = int(rect.right - rect.left)
                    height = int(rect.bottom - rect.top)
                    try:
                        style = int(get_style(wintypes.HWND(int(hwnd_value)), GWL_STYLE))
                    except Exception:
                        style = 0
                    try:
                        exstyle = int(get_exstyle(wintypes.HWND(int(hwnd_value)), GWL_EXSTYLE))
                    except Exception:
                        exstyle = 0
                    with open(debug_log_path, "a", encoding="utf-8", errors="ignore") as fh:
                        fh.write(
                            f"{reason} hwnd={int(hwnd_value)} class={_window_class(hwnd_value)!r} "
                            f"title={_window_text(hwnd_value)!r} size={width}x{height} "
                            f"style=0x{style:08X} exstyle=0x{exstyle:08X}\n"
                        )
                except Exception:
                    pass

            def _maybe_hide_window(hwnd_value: int, *, reason: str) -> bool:
                if not hwnd_value or hwnd_value in known_ok:
                    return False
                try:
                    if not _is_tiny_helper_window(hwnd_value):
                        known_ok.add(hwnd_value)
                        return False
                    _hide_window(hwnd_value)
                    _log_window_event(hwnd_value, reason)
                    return True
                except Exception:
                    return False

            WINEVENTPROC = ctypes.WINFUNCTYPE(
                None,
                wintypes.HANDLE,
                wintypes.DWORD,
                wintypes.HWND,
                ctypes.c_long,
                ctypes.c_long,
                wintypes.DWORD,
                wintypes.DWORD,
            )

            def _on_show(_hook, event, hwnd, id_object, _id_child, _tid, _time):  # noqa: ANN001
                if id_object != 0:
                    return
                h = int(hwnd) if hwnd else 0
                if not h or h in known_ok:
                    return
                try:
                    w_pid = wintypes.DWORD()
                    user32.GetWindowThreadProcessId(hwnd, ctypes.byref(w_pid))
                    if not _pid_is_tracked(int(w_pid.value)):
                        return

                    is_create_event = int(event) == EVENT_OBJECT_CREATE
                    _log_window_event(
                        h,
                        reason="winevent-seen-create" if is_create_event else "winevent-seen-show",
                    )
                    if not is_create_event:
                        style = int(get_style(hwnd, GWL_STYLE))
                        if not (style & WS_VISIBLE):
                            return

                    if not _maybe_hide_window(
                        h,
                        reason="winevent-hide-create" if is_create_event else "winevent-hide-show",
                    ):
                        return
                except Exception:
                    pass

            cb = WINEVENTPROC(_on_show)

            EnumWindowsProc = ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)

            def _poll_once() -> None:
                def _enum_cb(hwnd_obj, _lparam):  # noqa: ANN001
                    try:
                        h = int(hwnd_obj) if hwnd_obj else 0
                        if not h or h in known_ok:
                            return True
                        w_pid = wintypes.DWORD()
                        user32.GetWindowThreadProcessId(hwnd_obj, ctypes.byref(w_pid))
                        if not _pid_is_tracked(int(w_pid.value)):
                            return True
                        _maybe_hide_window(h, reason="winevent-hide-poll")
                    except Exception:
                        return True
                    return True

                cb_enum = EnumWindowsProc(_enum_cb)
                try:
                    user32.EnumWindows(cb_enum, 0)
                except Exception:
                    pass

            hook = user32.SetWinEventHook(
                EVENT_OBJECT_CREATE,
                EVENT_OBJECT_SHOW,
                None,
                cb,
                0,
                0,
                WINEVENT_OUTOFCONTEXT,
            )

            if self._ready is not None:
                self._ready.set()

            if not hook:
                return

            deadline = time.monotonic() + 5.0
            next_pid_refresh = time.monotonic()
            next_poll = time.monotonic()
            msg = wintypes.MSG()
            while not self._stop and time.monotonic() < deadline:
                now = time.monotonic()
                if now >= next_pid_refresh:
                    _refresh_descendant_pids(force=True)
                    next_pid_refresh = now + 0.05
                if now >= next_poll:
                    _poll_once()
                    next_poll = now + 0.015
                while user32.PeekMessageW(ctypes.byref(msg), None, 0, 0, 1):
                    if msg.message == 0x0012:
                        user32.UnhookWinEvent(hook)
                        return
                    user32.TranslateMessage(ctypes.byref(msg))
                    user32.DispatchMessageW(ctypes.byref(msg))
                time.sleep(0.001)

            user32.UnhookWinEvent(hook)
        except Exception:
            if self._ready is not None:
                self._ready.set()


def _start_pre_qt_winevent_suppression(*, ready_timeout_s: float = 0.5) -> _PreQtWinEventSuppressor:
    suppressor = _PreQtWinEventSuppressor()
    suppressor.start(ready_timeout_s=ready_timeout_s)
    return suppressor
