from __future__ import annotations

import os
import sys
from pathlib import Path

from PyQt6 import QtCore, QtWidgets


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
