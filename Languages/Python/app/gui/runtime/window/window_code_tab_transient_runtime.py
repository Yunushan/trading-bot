from __future__ import annotations

import os
import sys
import time
from pathlib import Path

from PyQt6 import QtCore, QtWidgets


def start_windows_transient_window_suppression(
    self,
    *,
    active_attr: str,
    timer_attr: str,
    enabled_env: str,
    default_enabled: bool = False,
    duration_env: str,
    default_duration_ms: int,
    interval_env: str,
    default_interval_ms: int,
    debug_env: str,
    debug_log_name: str,
    fallback_height_limit: int = 120,
) -> None:
    if sys.platform != "win32":
        return
    default_flag = "1" if default_enabled else "0"
    flag = str(os.environ.get(enabled_env, default_flag)).strip().lower()
    if flag in {"0", "false", "no", "off"}:
        return
    if getattr(self, active_attr, False):
        return
    try:
        import ctypes
        import ctypes.wintypes as wintypes
    except Exception:
        return
    setattr(self, active_attr, True)

    user32 = ctypes.windll.user32
    kernel32 = ctypes.windll.kernel32
    try:
        pid = int(kernel32.GetCurrentProcessId())
    except Exception:
        pid = 0
    known_hwnds: set[int] = set()
    for hwnd_value in (
        getattr(self, "effectiveWinId", lambda: 0)(),
        getattr(self, "winId", lambda: 0)(),
    ):
        try:
            hwnd_int = int(hwnd_value)
        except Exception:
            hwnd_int = 0
        if hwnd_int:
            known_hwnds.add(hwnd_int)
    candidate_titles = {
        str(Path(sys.executable).stem or "").strip().lower(),
        str(Path(sys.argv[0]).stem or "").strip().lower() if sys.argv else "",
        str(os.environ.get("BOT_TASKBAR_DISPLAY_NAME") or "").strip().lower(),
    }
    try:
        app = QtWidgets.QApplication.instance()
    except Exception:
        app = None
    if app is not None:
        for accessor in ("applicationName", "applicationDisplayName"):
            try:
                value = str(getattr(app, accessor)() or "").strip().lower()
            except Exception:
                value = ""
            if value:
                candidate_titles.add(value)
    candidate_titles.discard("")

    TH32CS_SNAPPROCESS = 0x00000002
    SW_HIDE = 0
    debug_windows = str(os.environ.get(debug_env, "")).strip().lower() in {
        "1",
        "true",
        "yes",
        "on",
    }
    debug_log_path = Path(os.getenv("TEMP") or ".").resolve() / debug_log_name

    def _get_hwnd_pid(hwnd_obj):  # noqa: ANN001
        try:
            out_pid = wintypes.DWORD()
            user32.GetWindowThreadProcessId(hwnd_obj, ctypes.byref(out_pid))
            return int(out_pid.value)
        except Exception:
            return 0

    def _class_name(hwnd_obj):  # noqa: ANN001
        try:
            buf = ctypes.create_unicode_buffer(256)
            user32.GetClassNameW(hwnd_obj, buf, 256)
            return str(buf.value or "").strip()
        except Exception:
            return ""

    def _window_title(hwnd_obj):  # noqa: ANN001
        try:
            buf = ctypes.create_unicode_buffer(256)
            user32.GetWindowTextW(hwnd_obj, buf, 256)
            return str(buf.value or "").strip()
        except Exception:
            return ""

    def _is_transient(hwnd_obj, class_name: str | None = None, title: str | None = None):  # noqa: ANN001
        try:
            rect = wintypes.RECT()
            if not user32.GetWindowRect(hwnd_obj, ctypes.byref(rect)):
                return False
            width = int(rect.right - rect.left)
            height = int(rect.bottom - rect.top)
            if width <= 0 or height <= 0:
                return False
            class_name = class_name or _class_name(hwnd_obj)
            title = title or _window_title(hwnd_obj)
            try:
                GWL_STYLE = -16
                WS_CHILD = 0x40000000
                get_style = getattr(user32, "GetWindowLongPtrW", None) or user32.GetWindowLongW
                style = int(get_style(hwnd_obj, GWL_STYLE))
                if style & WS_CHILD:
                    return False
            except Exception:
                pass
            if title and "leave site" in title.lower():
                return True
            if class_name in {"ConsoleWindowClass", "PseudoConsoleWindow"}:
                return height <= 500 and width <= 4000
            if class_name.startswith("Qt") and class_name.endswith(
                (
                    "PowerDummyWindow",
                    "ClipboardView",
                    "ScreenChangeObserverWindow",
                    "ThemeChangeObserverWindow",
                )
            ):
                return True
            if class_name.startswith("_q_"):
                return height <= 260 and width <= 4000
            if class_name.startswith("Qt") and class_name.endswith("QWindowIcon"):
                lowered_title = title.lower()
                if lowered_title in candidate_titles:
                    return height <= 720 and width <= 1800
            if class_name == "Intermediate D3D Window":
                return height <= 500 and width <= 4000
            if class_name.startswith("Chrome_WidgetWin_"):
                return height <= 500 and width <= 4000
            if width >= 500 and height >= 300:
                return False
            return height <= fallback_height_limit and width <= 4000
        except Exception:
            return False

    def _hide(hwnd_obj):  # noqa: ANN001
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

    def _window_size(hwnd_obj):  # noqa: ANN001
        try:
            rect = wintypes.RECT()
            if not user32.GetWindowRect(hwnd_obj, ctypes.byref(rect)):
                return None, None
            return int(rect.right - rect.left), int(rect.bottom - rect.top)
        except Exception:
            return None, None

    def _log_window(hwnd_obj, reason: str, pid_val: int, class_name: str, title: str) -> None:  # noqa: ANN001
        if not debug_windows:
            return
        try:
            width, height = _window_size(hwnd_obj)
            with open(debug_log_path, "a", encoding="utf-8", errors="ignore") as fh:
                fh.write(
                    f"{reason} hwnd={int(hwnd_obj)} pid={pid_val} class={class_name!r} "
                    f"title={title!r} size={width}x{height}\n"
                )
        except Exception:
            return

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
            ("szExeFile", ctypes.c_wchar * 260),
        ]

    def _snapshot_processes():
        entries = []
        try:
            kernel32.CreateToolhelp32Snapshot.argtypes = [wintypes.DWORD, wintypes.DWORD]
            kernel32.CreateToolhelp32Snapshot.restype = wintypes.HANDLE
            kernel32.Process32FirstW.argtypes = [wintypes.HANDLE, ctypes.POINTER(PROCESSENTRY32)]
            kernel32.Process32FirstW.restype = wintypes.BOOL
            kernel32.Process32NextW.argtypes = [wintypes.HANDLE, ctypes.POINTER(PROCESSENTRY32)]
            kernel32.Process32NextW.restype = wintypes.BOOL
            kernel32.CloseHandle.argtypes = [wintypes.HANDLE]
            kernel32.CloseHandle.restype = wintypes.BOOL
        except Exception:
            pass
        try:
            snapshot = kernel32.CreateToolhelp32Snapshot(TH32CS_SNAPPROCESS, 0)
        except Exception:
            snapshot = 0
        if snapshot in (0, ctypes.c_void_p(-1).value):
            return entries

        try:
            entry = PROCESSENTRY32()
            entry.dwSize = ctypes.sizeof(entry)
            if not kernel32.Process32FirstW(snapshot, ctypes.byref(entry)):
                return entries
            while True:
                entries.append(
                    (
                        int(entry.th32ProcessID),
                        int(entry.th32ParentProcessID),
                        str(entry.szExeFile or "").strip(),
                    )
                )
                if not kernel32.Process32NextW(snapshot, ctypes.byref(entry)):
                    break
        finally:
            try:
                kernel32.CloseHandle(snapshot)
            except Exception:
                pass
        return entries

    def _collect_related_pids(root_pid: int):
        entries = _snapshot_processes()
        if not entries:
            return {root_pid} if root_pid else set(), set()
        children = {}
        exe_map = {}
        for proc_pid, parent_pid, exe in entries:
            exe_map[proc_pid] = exe
            children.setdefault(parent_pid, []).append(proc_pid)
        tree = set()
        stack = [root_pid] if root_pid else []
        while stack:
            cur = stack.pop()
            if cur in tree:
                continue
            tree.add(cur)
            stack.extend(children.get(cur, []))
        qt_roots = {
            proc_pid
            for proc_pid in tree
            if "qtwebengineprocess" in (exe_map.get(proc_pid, "") or "").lower()
        }
        qt_tree = set()
        for root in qt_roots:
            stack = [root]
            while stack:
                cur = stack.pop()
                if cur in qt_tree:
                    continue
                qt_tree.add(cur)
                stack.extend(children.get(cur, []))
        return tree if tree else ({root_pid} if root_pid else set()), qt_tree

    pid_cache = {"ts": 0.0, "pids": {pid} if pid else set(), "qt_pids": set()}

    def _get_pid_sets():
        now = time.monotonic()
        if now - pid_cache["ts"] < 0.25:
            return pid_cache["pids"], pid_cache["qt_pids"]
        tree, qt_tree = _collect_related_pids(pid)
        pid_cache["ts"] = now
        pid_cache["pids"] = tree
        pid_cache["qt_pids"] = qt_tree
        return tree, qt_tree

    EnumWindowsProc = ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)

    def _poll_once():
        allowed_pids, qt_pids = _get_pid_sets()

        def _enum_cb(hwnd_obj, _lparam):  # noqa: ANN001
            try:
                pid_val = _get_hwnd_pid(hwnd_obj)
                if allowed_pids and pid_val not in allowed_pids:
                    return True
                try:
                    hwnd_int = int(hwnd_obj)
                except Exception:
                    hwnd_int = 0
                if hwnd_int and hwnd_int in known_hwnds:
                    return True
                try:
                    if not user32.IsWindowVisible(hwnd_obj):
                        return True
                except Exception:
                    return True
                class_name = _class_name(hwnd_obj)
                title = _window_title(hwnd_obj)
                if pid_val in qt_pids or pid_val == pid:
                    if _is_transient(hwnd_obj, class_name=class_name, title=title):
                        reason = "hide-qtwebengine" if pid_val in qt_pids else "hide-current-process"
                        _log_window(hwnd_obj, reason, pid_val, class_name, title)
                        _hide(hwnd_obj)
                    return True
            except Exception:
                return True
            return True

        cb = EnumWindowsProc(_enum_cb)
        try:
            user32.EnumWindows(cb, 0)
        except Exception:
            pass

    try:
        duration_ms = int(os.environ.get(duration_env) or default_duration_ms)
    except Exception:
        duration_ms = default_duration_ms
    duration_ms = max(300, min(duration_ms, 5000))
    try:
        interval_ms = int(os.environ.get(interval_env) or default_interval_ms)
    except Exception:
        interval_ms = default_interval_ms
    interval_ms = max(5, min(interval_ms, 120))

    timer = QtCore.QTimer(self)
    timer.setInterval(interval_ms)
    start_ts = time.monotonic()

    def _tick():
        if (time.monotonic() - start_ts) * 1000.0 >= duration_ms:
            try:
                timer.stop()
            except Exception:
                pass
            try:
                timer.deleteLater()
            except Exception:
                pass
            setattr(self, timer_attr, None)
            setattr(self, active_attr, False)
            return
        _poll_once()

    timer.timeout.connect(_tick)
    timer.start()
    setattr(self, timer_attr, timer)
    _tick()
