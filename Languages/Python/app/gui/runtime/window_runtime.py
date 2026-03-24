from __future__ import annotations

import os
import sys
import time
from pathlib import Path

from PyQt6 import QtCore, QtWidgets

from ..shared.silent_webengine_page import SilentWebEnginePage


def start_windows_thread_cbt_window_suppression(
    self,
    *,
    hook_attr: str,
    proc_attr: str,
    timer_attr: str,
    enabled_env: str,
    default_enabled: bool = False,
    duration_env: str,
    default_duration_ms: int,
    debug_env: str,
    debug_log_name: str,
) -> None:
    if sys.platform != "win32":
        return
    default_flag = "1" if default_enabled else "0"
    flag = str(os.environ.get(enabled_env, default_flag)).strip().lower()
    if flag in {"0", "false", "no", "off"}:
        return
    try:
        import ctypes
        import ctypes.wintypes as wintypes
    except Exception:
        return

    try:
        duration_ms = int(os.environ.get(duration_env) or default_duration_ms)
    except Exception:
        duration_ms = default_duration_ms
    duration_ms = max(300, min(duration_ms, 5000))

    user32 = ctypes.windll.user32
    kernel32 = ctypes.windll.kernel32
    debug_windows = str(os.environ.get(debug_env, "")).strip().lower() in {
        "1",
        "true",
        "yes",
        "on",
    }
    debug_log_path = Path(os.getenv("TEMP") or ".").resolve() / debug_log_name

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

    WH_CBT = 5
    HCBT_CREATEWND = 3
    WS_CHILD = 0x40000000
    WS_VISIBLE = 0x10000000
    WS_EX_TOOLWINDOW = 0x00000080
    WS_EX_APPWINDOW = 0x00040000
    WS_EX_NOACTIVATE = 0x08000000
    _QT_INTERNAL_WINDOW_SUFFIXES = (
        "PowerDummyWindow",
        "ClipboardView",
        "ScreenChangeObserverWindow",
        "ThemeChangeObserverWindow",
        "QWindowToolSaveBits",
    )

    LRESULT = ctypes.c_ssize_t
    CBTProc = ctypes.WINFUNCTYPE(LRESULT, ctypes.c_int, wintypes.WPARAM, wintypes.LPARAM)

    class CREATESTRUCTW(ctypes.Structure):
        _fields_ = [
            ("lpCreateParams", wintypes.LPVOID),
            ("hInstance", wintypes.HINSTANCE),
            ("hMenu", wintypes.HMENU),
            ("hwndParent", wintypes.HWND),
            ("cy", ctypes.c_int),
            ("cx", ctypes.c_int),
            ("y", ctypes.c_int),
            ("x", ctypes.c_int),
            ("style", ctypes.c_long),
            ("lpszName", wintypes.LPCWSTR),
            ("lpszClass", wintypes.LPCWSTR),
            ("dwExStyle", wintypes.DWORD),
        ]

    class CBT_CREATEWND(ctypes.Structure):
        _fields_ = [("lpcs", ctypes.POINTER(CREATESTRUCTW)), ("hwndInsertAfter", wintypes.HWND)]

    try:
        user32.SetWindowsHookExW.argtypes = [ctypes.c_int, ctypes.c_void_p, wintypes.HINSTANCE, wintypes.DWORD]
        user32.SetWindowsHookExW.restype = wintypes.HHOOK
        user32.UnhookWindowsHookEx.argtypes = [wintypes.HHOOK]
        user32.UnhookWindowsHookEx.restype = wintypes.BOOL
        user32.CallNextHookEx.argtypes = [wintypes.HHOOK, ctypes.c_int, wintypes.WPARAM, wintypes.LPARAM]
        user32.CallNextHookEx.restype = LRESULT
        user32.GetClassNameW.argtypes = [wintypes.HWND, wintypes.LPWSTR, ctypes.c_int]
        user32.GetClassNameW.restype = ctypes.c_int
        user32.GetWindowTextW.argtypes = [wintypes.HWND, wintypes.LPWSTR, ctypes.c_int]
        user32.GetWindowTextW.restype = ctypes.c_int
    except Exception:
        pass

    def _read_cs_string(value) -> str:  # noqa: ANN001
        if value is None:
            return ""
        if isinstance(value, str):
            text = str(value or "").strip()
            if len(text) == 1 and ord(text) < 32:
                return ""
            return text
        addr = None
        if isinstance(value, int):
            addr = int(value)
        else:
            try:
                addr = int(ctypes.cast(value, ctypes.c_void_p).value or 0)
            except Exception:
                addr = 0
        if not addr or addr < 0x10000:
            return ""
        try:
            return str(ctypes.wstring_at(addr) or "").strip()
        except Exception:
            return ""

    def _read_hwnd_class(hwnd_val: int) -> str:
        try:
            buf = ctypes.create_unicode_buffer(256)
            user32.GetClassNameW(wintypes.HWND(int(hwnd_val)), buf, 256)
            return str(buf.value or "").strip()
        except Exception:
            return ""

    def _read_hwnd_title(hwnd_val: int) -> str:
        try:
            buf = ctypes.create_unicode_buffer(256)
            user32.GetWindowTextW(wintypes.HWND(int(hwnd_val)), buf, 256)
            return str(buf.value or "").strip()
        except Exception:
            return ""

    def _looks_transient(*, class_name: str, title: str, width: int, height: int, style: int) -> bool:
        if width <= 0 or height <= 0:
            return False
        if style & WS_CHILD:
            return False
        name = str(class_name or "").strip()
        ttl = str(title or "").strip()
        lowered_title = ttl.lower()
        if name == "_q_titlebar" or ttl == "_q_titlebar":
            return True
        if name.startswith("QEventDispatcherWin32_") or ttl.startswith("QEventDispatcherWin32_"):
            return True
        if name.startswith("Qt") and any(name.endswith(suffix) for suffix in _QT_INTERNAL_WINDOW_SUFFIXES):
            return True
        if ttl.startswith("Qt") and any(ttl.endswith(suffix) for suffix in _QT_INTERNAL_WINDOW_SUFFIXES):
            return True
        if name in {"ConsoleWindowClass", "PseudoConsoleWindow"}:
            return height <= 500 and width <= 4000
        if name == "Intermediate D3D Window":
            return height <= 500 and width <= 4000
        if name.startswith("Chrome_WidgetWin_"):
            return height <= 500 and width <= 4000
        if name.startswith("Qt") and name.endswith("QWindowIcon") and lowered_title in candidate_titles:
            return height <= 1200 and width <= 2200
        if width >= 500 and height >= 300:
            return False
        return height <= 260 and width <= 4000

    def _log_create(hwnd_val: int, reason: str, class_name: str, title: str, width: int, height: int) -> None:
        if not debug_windows:
            return
        try:
            with open(debug_log_path, "a", encoding="utf-8", errors="ignore") as fh:
                fh.write(
                    f"{reason} hwnd={int(hwnd_val)} class={class_name!r} title={title!r} "
                    f"size={int(width)}x{int(height)}\n"
                )
        except Exception:
            pass

    def _cbt_proc(n_code, w_param, l_param):  # noqa: ANN001
        try:
            if int(n_code) != HCBT_CREATEWND:
                return user32.CallNextHookEx(0, n_code, w_param, l_param)
            hwnd_val = int(w_param or 0)
            if not hwnd_val or hwnd_val in known_hwnds:
                return user32.CallNextHookEx(0, n_code, w_param, l_param)
            lp_val = int(l_param or 0)
            if not lp_val or lp_val < 0x10000:
                return user32.CallNextHookEx(0, n_code, w_param, l_param)
            cbt = ctypes.cast(lp_val, ctypes.POINTER(CBT_CREATEWND)).contents
            if not cbt.lpcs:
                return user32.CallNextHookEx(0, n_code, w_param, l_param)
            cs = cbt.lpcs.contents
            width = int(cs.cx)
            height = int(cs.cy)
            style = int(cs.style) & 0xFFFFFFFF
            class_name = _read_cs_string(cs.lpszClass) or _read_hwnd_class(hwnd_val)
            title = _read_cs_string(cs.lpszName) or _read_hwnd_title(hwnd_val)
            if not _looks_transient(
                class_name=class_name,
                title=title,
                width=width,
                height=height,
                style=style,
            ):
                return user32.CallNextHookEx(0, n_code, w_param, l_param)
            ex_style = int(cs.dwExStyle) & 0xFFFFFFFF
            cs.style = int(style & ~WS_VISIBLE)
            cs.dwExStyle = int((ex_style | WS_EX_TOOLWINDOW | WS_EX_NOACTIVATE) & ~WS_EX_APPWINDOW)
            cs.x = -32000
            cs.y = -32000
            cs.cx = 1
            cs.cy = 1
            _log_create(hwnd_val, "cbt-hide", class_name, title, width, height)
        except Exception:
            pass
        return user32.CallNextHookEx(0, n_code, w_param, l_param)

    hook_value = getattr(self, hook_attr, None)
    timer = getattr(self, timer_attr, None)

    def _stop() -> None:
        current_hook = getattr(self, hook_attr, None)
        if current_hook:
            try:
                user32.UnhookWindowsHookEx(current_hook)
            except Exception:
                pass
        setattr(self, hook_attr, None)
        setattr(self, proc_attr, None)
        current_timer = getattr(self, timer_attr, None)
        if current_timer is not None:
            try:
                current_timer.stop()
            except Exception:
                pass

    if not hook_value:
        try:
            msg = wintypes.MSG()
            user32.PeekMessageW(ctypes.byref(msg), 0, 0, 0, 0)
        except Exception:
            pass
        try:
            thread_id = int(kernel32.GetCurrentThreadId())
        except Exception:
            thread_id = 0
        if not thread_id:
            return
        proc = CBTProc(_cbt_proc)
        try:
            hook_value = user32.SetWindowsHookExW(WH_CBT, proc, 0, int(thread_id))
        except Exception:
            hook_value = 0
        if not hook_value:
            return
        setattr(self, hook_attr, hook_value)
        setattr(self, proc_attr, proc)

    if timer is None:
        try:
            timer = QtCore.QTimer(self)
            timer.setSingleShot(True)
            timer.timeout.connect(_stop)
            setattr(self, timer_attr, timer)
        except Exception:
            _stop()
            return
    try:
        timer.stop()
    except Exception:
        pass
    try:
        timer.start(duration_ms)
    except Exception:
        _stop()


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
        from ...bootstrap.startup_pre_qt_window_suppression_runtime import _PreQtWinEventSuppressor
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


def schedule_tradingview_prewarm(self) -> None:
    if getattr(self, "_tradingview_prewarm_scheduled", False) or getattr(self, "_tradingview_prewarmed", False):
        return
    if not getattr(self, "_chart_view_tradingview_available", False):
        return
    if sys.platform != "win32":
        return
    flag = str(os.environ.get("BOT_PREWARM_TRADINGVIEW", "0")).strip().lower()
    if flag in {"0", "false", "no", "off"}:
        return
    try:
        delay_ms = int(os.environ.get("BOT_PREWARM_TRADINGVIEW_DELAY_MS") or 1200)
    except Exception:
        delay_ms = 1200
    delay_ms = max(100, min(delay_ms, 10000))
    self._tradingview_prewarm_scheduled = True
    QtCore.QTimer.singleShot(delay_ms, self._prewarm_tradingview)


def schedule_webengine_runtime_prewarm(self) -> None:
    if getattr(self, "_webengine_runtime_prewarm_scheduled", False):
        return
    if getattr(self, "_webengine_runtime_prewarmed", False):
        return
    flag = str(os.environ.get("BOT_PREWARM_WEBENGINE", "0")).strip().lower()
    if flag in {"0", "false", "no", "off"}:
        return
    try:
        delay_ms = int(os.environ.get("BOT_PREWARM_WEBENGINE_DELAY_MS") or 1800)
    except Exception:
        delay_ms = 1800
    delay_ms = max(250, min(delay_ms, 15000))
    self._webengine_runtime_prewarm_scheduled = True
    QtCore.QTimer.singleShot(delay_ms, self._maybe_run_deferred_webengine_prewarm)


def maybe_run_deferred_webengine_prewarm(self) -> None:
    if getattr(self, "_webengine_runtime_prewarmed", False):
        self._webengine_runtime_prewarm_scheduled = False
        return
    try:
        app = QtWidgets.QApplication.instance()
    except Exception:
        app = None
    if sys.platform == "win32":
        try:
            if app is not None and app.applicationState() != QtCore.Qt.ApplicationState.ApplicationActive:
                QtCore.QTimer.singleShot(1200, self._maybe_run_deferred_webengine_prewarm)
                return
        except Exception:
            pass
        try:
            if not self.isVisible() or self.windowState() & QtCore.Qt.WindowState.WindowMinimized:
                QtCore.QTimer.singleShot(1200, self._maybe_run_deferred_webengine_prewarm)
                return
        except Exception:
            pass
    self._webengine_runtime_prewarm_scheduled = False
    try:
        self._prewarm_webengine_runtime()
    except Exception:
        pass


def prewarm_webengine_runtime(
    self,
    *,
    webengine_charts_allowed,
    webengine_embed_unavailable_reason,
    configure_tradingview_webengine_env,
) -> None:
    if getattr(self, "_webengine_runtime_prewarmed", False):
        return
    if sys.platform != "win32":
        return
    if not webengine_charts_allowed():
        return
    flag = str(os.environ.get("BOT_PREWARM_WEBENGINE", "1")).strip().lower()
    if flag in {"0", "false", "no", "off"}:
        return
    if webengine_embed_unavailable_reason():
        return
    try:
        configure_tradingview_webengine_env()
    except Exception:
        pass
    try:
        from PyQt6.QtWebEngineWidgets import QWebEngineView
    except Exception:
        return
    try:
        view = QWebEngineView(self)
        view.setObjectName("botWebEnginePrewarm")
        try:
            if SilentWebEnginePage is not None:
                view.setPage(SilentWebEnginePage(view))
        except Exception:
            pass
        try:
            view.setAttribute(QtCore.Qt.WidgetAttribute.WA_DontShowOnScreen, True)
        except Exception:
            pass
        try:
            view.resize(1, 1)
            view.move(-32000, -32000)
            view.hide()
        except Exception:
            pass
        try:
            view.load(QtCore.QUrl("about:blank"))
        except Exception:
            pass
        self._webengine_runtime_prewarm_view = view
        self._webengine_runtime_prewarmed = True
        try:
            self._chart_debug_log("webengine_prewarm init=1")
        except Exception:
            pass
    except Exception:
        return

    try:
        hold_ms = int(os.environ.get("BOT_PREWARM_WEBENGINE_HOLD_MS") or 2200)
    except Exception:
        hold_ms = 2200
    hold_ms = max(500, min(hold_ms, 10000))

    def _cleanup():
        view_obj = getattr(self, "_webengine_runtime_prewarm_view", None)
        self._webengine_runtime_prewarm_view = None
        if view_obj is not None:
            try:
                view_obj.deleteLater()
            except Exception:
                pass

    QtCore.QTimer.singleShot(hold_ms, _cleanup)


def prewarm_tradingview(self) -> None:
    self._tradingview_prewarm_scheduled = False
    if getattr(self, "_tradingview_prewarmed", False):
        return
    if not getattr(self, "_chart_view_tradingview_available", False):
        return
    widget = self._ensure_tradingview_widget()
    if widget is None:
        return
    self._tradingview_prewarmed = True
    self._prime_tradingview_chart(widget)


def start_tradingview_visibility_guard(self) -> None:
    if sys.platform != "win32":
        return
    if getattr(self, "_tv_visibility_guard_active", False):
        return
    try:
        duration_ms = int(os.environ.get("BOT_TRADINGVIEW_VISIBILITY_GUARD_MS") or 2500)
    except Exception:
        duration_ms = 2500
    duration_ms = max(500, min(duration_ms, 8000))
    try:
        interval_ms = int(os.environ.get("BOT_TRADINGVIEW_VISIBILITY_GUARD_INTERVAL_MS") or 50)
    except Exception:
        interval_ms = 50
    interval_ms = max(20, min(interval_ms, 200))

    timer = QtCore.QTimer(self)
    timer.setInterval(interval_ms)
    start_ts = time.monotonic()
    self._tv_visibility_guard_active = True
    self._tv_visibility_guard_timer = timer

    def _tick():
        if (time.monotonic() - start_ts) * 1000.0 >= duration_ms:
            self._stop_tradingview_visibility_guard()
            return
        try:
            if not self.isVisible():
                self.showMaximized()
                self.raise_()
                self.activateWindow()
            elif self.windowState() & QtCore.Qt.WindowState.WindowMinimized:
                self.showMaximized()
                self.raise_()
                self.activateWindow()
        except Exception:
            pass

    timer.timeout.connect(_tick)
    timer.start()
    _tick()


def start_tradingview_visibility_watchdog(self) -> None:
    if sys.platform != "win32":
        return
    if getattr(self, "_tv_visibility_watchdog_active", False):
        return
    flag = str(os.environ.get("BOT_TRADINGVIEW_VISIBILITY_WATCHDOG", "1")).strip().lower()
    if flag in {"0", "false", "no", "off"}:
        return
    try:
        interval_ms = int(os.environ.get("BOT_TRADINGVIEW_VISIBILITY_WATCHDOG_INTERVAL_MS") or 200)
    except Exception:
        interval_ms = 200
    interval_ms = max(50, min(interval_ms, 1000))
    timer = QtCore.QTimer(self)
    timer.setInterval(interval_ms)
    self._tv_visibility_watchdog_active = True
    self._tv_visibility_watchdog_timer = timer

    def _tick():
        try:
            if not self.isVisible() or self.windowState() & QtCore.Qt.WindowState.WindowMinimized:
                self.showMaximized()
                self.raise_()
                self.activateWindow()
        except Exception:
            pass

    timer.timeout.connect(_tick)
    timer.start()
    _tick()


def start_tradingview_close_guard(self) -> None:
    if sys.platform != "win32":
        return
    try:
        duration_ms = int(os.environ.get("BOT_TRADINGVIEW_CLOSE_GUARD_MS") or 2500)
    except Exception:
        duration_ms = 2500
    duration_ms = max(500, min(duration_ms, 8000))
    try:
        self._tv_close_guard_until = time.monotonic() + (duration_ms / 1000.0)
    except Exception:
        self._tv_close_guard_until = 0.0
    self._tv_close_guard_active = True
    try:
        extender = getattr(self, "_extend_spontaneous_close_block", None)
        if callable(extender):
            extender(duration_ms + 2500)
    except Exception:
        pass


def start_webengine_close_guard(self, *, webengine_charts_allowed) -> None:
    if sys.platform != "win32":
        return
    if not webengine_charts_allowed():
        return
    try:
        duration_ms = int(os.environ.get("BOT_WEBENGINE_CLOSE_GUARD_MS") or 3500)
    except Exception:
        duration_ms = 3500
    duration_ms = max(800, min(duration_ms, 15000))
    try:
        until = time.monotonic() + (duration_ms / 1000.0)
    except Exception:
        until = 0.0
    try:
        prev_until = float(getattr(self, "_webengine_close_guard_until", 0.0) or 0.0)
    except Exception:
        prev_until = 0.0
    self._webengine_close_guard_until = max(prev_until, until)
    self._webengine_close_guard_active = True
    try:
        extender = getattr(self, "_extend_spontaneous_close_block", None)
        if callable(extender):
            extender(duration_ms + 2500)
    except Exception:
        pass
    self._start_webengine_visibility_watchdog()
    try:
        self._chart_debug_log(
            f"webengine_close_guard start duration_ms={duration_ms} until={self._webengine_close_guard_until:.3f}"
        )
    except Exception:
        pass


def start_webengine_visibility_watchdog(self, *, allow_guard_bypass, restore_window_after_guard) -> None:
    if sys.platform != "win32":
        return
    if getattr(self, "_webengine_visibility_watchdog_active", False):
        return
    try:
        interval_ms = int(os.environ.get("BOT_WEBENGINE_CLOSE_GUARD_WATCHDOG_INTERVAL_MS") or 120)
    except Exception:
        interval_ms = 120
    interval_ms = max(30, min(interval_ms, 1000))
    timer = QtCore.QTimer(self)
    timer.setInterval(interval_ms)
    self._webengine_visibility_watchdog_active = True
    self._webengine_visibility_watchdog_timer = timer

    def _tick():
        if allow_guard_bypass(self):
            self._stop_webengine_visibility_watchdog()
            return
        try:
            now = time.monotonic()
        except Exception:
            now = 0.0
        try:
            until = float(getattr(self, "_webengine_close_guard_until", 0.0) or 0.0)
        except Exception:
            until = 0.0
        if not until or now >= until:
            try:
                self._webengine_close_guard_active = False
            except Exception:
                pass
            self._stop_webengine_visibility_watchdog()
            return
        if not getattr(self, "_webengine_close_guard_active", False):
            self._stop_webengine_visibility_watchdog()
            return
        try:
            if not self.isVisible() or self.windowState() & QtCore.Qt.WindowState.WindowMinimized:
                restore_window_after_guard(self)
        except Exception:
            pass

    timer.timeout.connect(_tick)
    timer.start()
    _tick()


def stop_webengine_visibility_watchdog(self) -> None:
    timer = getattr(self, "_webengine_visibility_watchdog_timer", None)
    if timer is not None:
        try:
            timer.stop()
        except Exception:
            pass
        try:
            timer.deleteLater()
        except Exception:
            pass
    self._webengine_visibility_watchdog_timer = None
    self._webengine_visibility_watchdog_active = False


def stop_tradingview_visibility_guard(self) -> None:
    timer = getattr(self, "_tv_visibility_guard_timer", None)
    if timer is not None:
        try:
            timer.stop()
        except Exception:
            pass
        try:
            timer.deleteLater()
        except Exception:
            pass
    self._tv_visibility_guard_timer = None
    self._tv_visibility_guard_active = False


def stop_tradingview_visibility_watchdog(self) -> None:
    timer = getattr(self, "_tv_visibility_watchdog_timer", None)
    if timer is not None:
        try:
            timer.stop()
        except Exception:
            pass
        try:
            timer.deleteLater()
        except Exception:
            pass
    self._tv_visibility_watchdog_timer = None
    self._tv_visibility_watchdog_active = False


def restore_window_after_guard(self) -> None:
    def _restore_once():
        try:
            state = self.windowState()
        except Exception:
            state = QtCore.Qt.WindowState.WindowNoState
        try:
            visible = bool(self.isVisible())
        except Exception:
            visible = False
        try:
            minimized = bool(state & QtCore.Qt.WindowState.WindowMinimized)
        except Exception:
            minimized = False
        if minimized:
            try:
                self.showMaximized()
            except Exception:
                pass
        elif not visible:
            try:
                self.showMaximized()
            except Exception:
                pass
        try:
            self.raise_()
            self.activateWindow()
        except Exception:
            pass

    _restore_once()
    try:
        # WebEngine can minimize the host window a little after the initial
        # hide/minimize event, so keep restoring for a short grace period.
        for delay_ms in (40, 140, 320, 700, 1400, 2400):
            QtCore.QTimer.singleShot(delay_ms, _restore_once)
    except Exception:
        pass
