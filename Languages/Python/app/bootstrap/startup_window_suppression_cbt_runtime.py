from __future__ import annotations

import os
import sys
from pathlib import Path

from .startup_window_suppression_shared_runtime import _env_flag

_CBT_STARTUP_WINDOW_HOOKS: dict[int, int] = {}
_CBT_STARTUP_WINDOW_PROC = None
_CBT_STARTUP_WINDOW_SCAN_STOP = None
_CBT_STARTUP_WINDOW_SCAN_THREAD = None
_CBT_STARTUP_WINDOW_LOCK = None
_CBT_STARTUP_HELPER_COVERS: dict[tuple[int, int, int, int], dict[str, object]] = {}
_CBT_STARTUP_HELPER_COVER_LOCK = None
_CBT_STARTUP_HELPER_COVER_STOP = None
_CBT_STARTUP_HELPER_COVER_THREAD = None


def _install_cbt_startup_window_suppression() -> None:
    """Best-effort: clear WS_VISIBLE at create-time for tiny helper windows (Windows only)."""
    global _CBT_STARTUP_WINDOW_PROC, _CBT_STARTUP_WINDOW_SCAN_STOP, _CBT_STARTUP_WINDOW_SCAN_THREAD, _CBT_STARTUP_WINDOW_LOCK
    global _CBT_STARTUP_HELPER_COVER_LOCK, _CBT_STARTUP_HELPER_COVER_STOP, _CBT_STARTUP_HELPER_COVER_THREAD
    if sys.platform != "win32" or _CBT_STARTUP_WINDOW_PROC is not None:
        return
    if not _env_flag("BOT_ENABLE_CBT_STARTUP_WINDOW_SUPPRESS"):
        return
    if _env_flag("BOT_NO_STARTUP_WINDOW_SUPPRESS") or _env_flag("BOT_NO_CBT_STARTUP_WINDOW_SUPPRESS"):
        return

    try:  # pragma: no cover - Windows only
        import ctypes
        import ctypes.wintypes as wintypes
        import threading
        import time
    except Exception:
        return

    user32 = ctypes.windll.user32
    kernel32 = ctypes.windll.kernel32
    gdi32 = ctypes.windll.gdi32

    debug_window_events = _env_flag("BOT_DEBUG_WINDOW_EVENTS")
    debug_log_path = Path(os.getenv("TEMP") or ".").resolve() / "binance_window_events.log"

    WH_CBT = 5
    HCBT_CREATEWND = 3
    WS_CHILD = 0x40000000
    WS_VISIBLE = 0x10000000
    WS_EX_TOOLWINDOW = 0x00000080
    WS_EX_APPWINDOW = 0x00040000
    WS_EX_NOACTIVATE = 0x08000000
    WS_EX_TOPMOST = 0x00000008
    WS_EX_LAYERED = 0x00080000
    WS_EX_TRANSPARENT = 0x00000020
    WS_POPUP = 0x80000000
    SS_BITMAP = 0x0000000E
    HWND_TOPMOST = -1
    SW_HIDE = 0
    SW_SHOWNOACTIVATE = 4
    SWP_NOSIZE = 0x0001
    SWP_NOZORDER = 0x0004
    SWP_NOACTIVATE = 0x0010
    SWP_SHOWWINDOW = 0x0040
    SWP_HIDEWINDOW = 0x0080
    SWP_ASYNCWINDOWPOS = 0x4000
    STM_SETIMAGE = 0x0172
    IMAGE_BITMAP = 0
    SRCCOPY = 0x00CC0020
    CAPTUREBLT = 0x40000000
    _HELPER_COVER_TITLE = "__BOT_STARTUP_HELPER_COVER__"

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

    user32.SetWindowsHookExW.argtypes = [ctypes.c_int, ctypes.c_void_p, wintypes.HINSTANCE, wintypes.DWORD]
    user32.SetWindowsHookExW.restype = wintypes.HHOOK
    user32.UnhookWindowsHookEx.argtypes = [wintypes.HHOOK]
    user32.UnhookWindowsHookEx.restype = wintypes.BOOL
    user32.CallNextHookEx.argtypes = [wintypes.HHOOK, ctypes.c_int, wintypes.WPARAM, wintypes.LPARAM]
    user32.CallNextHookEx.restype = LRESULT
    try:
        user32.GetClassNameW.argtypes = [wintypes.HWND, wintypes.LPWSTR, ctypes.c_int]
        user32.GetClassNameW.restype = ctypes.c_int
        user32.GetWindowTextW.argtypes = [wintypes.HWND, wintypes.LPWSTR, ctypes.c_int]
        user32.GetWindowTextW.restype = ctypes.c_int
        user32.CreateWindowExW.argtypes = [
            wintypes.DWORD,
            wintypes.LPCWSTR,
            wintypes.LPCWSTR,
            wintypes.DWORD,
            ctypes.c_int,
            ctypes.c_int,
            ctypes.c_int,
            ctypes.c_int,
            wintypes.HWND,
            wintypes.HMENU,
            wintypes.HINSTANCE,
            wintypes.LPVOID,
        ]
        user32.CreateWindowExW.restype = wintypes.HWND
        user32.SendMessageW.argtypes = [wintypes.HWND, wintypes.UINT, wintypes.WPARAM, wintypes.LPARAM]
        user32.SendMessageW.restype = wintypes.LRESULT
        user32.SetWindowPos.argtypes = [
            wintypes.HWND,
            wintypes.HWND,
            ctypes.c_int,
            ctypes.c_int,
            ctypes.c_int,
            ctypes.c_int,
            wintypes.UINT,
        ]
        user32.SetWindowPos.restype = wintypes.BOOL
        user32.GetDC.argtypes = [wintypes.HWND]
        user32.GetDC.restype = wintypes.HDC
        user32.ReleaseDC.argtypes = [wintypes.HWND, wintypes.HDC]
        user32.ReleaseDC.restype = ctypes.c_int
        gdi32.CreateCompatibleDC.argtypes = [wintypes.HDC]
        gdi32.CreateCompatibleDC.restype = wintypes.HDC
        gdi32.CreateCompatibleBitmap.argtypes = [wintypes.HDC, ctypes.c_int, ctypes.c_int]
        gdi32.CreateCompatibleBitmap.restype = wintypes.HBITMAP
        gdi32.SelectObject.argtypes = [wintypes.HDC, wintypes.HGDIOBJ]
        gdi32.SelectObject.restype = wintypes.HGDIOBJ
        gdi32.BitBlt.argtypes = [
            wintypes.HDC,
            ctypes.c_int,
            ctypes.c_int,
            ctypes.c_int,
            ctypes.c_int,
            wintypes.HDC,
            ctypes.c_int,
            ctypes.c_int,
            wintypes.DWORD,
        ]
        gdi32.BitBlt.restype = wintypes.BOOL
        gdi32.DeleteDC.argtypes = [wintypes.HDC]
        gdi32.DeleteDC.restype = wintypes.BOOL
        gdi32.DeleteObject.argtypes = [wintypes.HGDIOBJ]
        gdi32.DeleteObject.restype = wintypes.BOOL
    except Exception:
        pass

    _QT_INTERNAL_WINDOW_SUFFIXES = (
        "PowerDummyWindow",
        "ClipboardView",
        "ScreenChangeObserverWindow",
        "ThemeChangeObserverWindow",
        "QWindowToolSaveBits",
    )

    def _read_cs_string(value) -> str:  # noqa: ANN001
        if value is None:
            return ""
        if isinstance(value, str):
            text = (value or "").strip()
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
        if not addr:
            return ""
        if addr < 0x10000:
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

    def _looks_like_qt_internal_helper_window(*, class_name: str, title: str) -> bool:
        name = str(class_name or "").strip()
        if name == "_q_titlebar":
            return True
        if name.startswith("QEventDispatcherWin32_"):
            return True
        if name.startswith("Qt") and any(name.endswith(suffix) for suffix in _QT_INTERNAL_WINDOW_SUFFIXES):
            return True
        ttl = str(title or "").strip()
        if ttl == "_q_titlebar":
            return True
        if ttl.startswith("QEventDispatcherWin32_"):
            return True
        if ttl.startswith("Qt") and any(ttl.endswith(suffix) for suffix in _QT_INTERNAL_WINDOW_SUFFIXES):
            return True
        return False

    if _CBT_STARTUP_HELPER_COVER_LOCK is None:
        _CBT_STARTUP_HELPER_COVER_LOCK = threading.Lock()

    def _set_helper_cover_visible(key: tuple[int, int, int, int], info: dict[str, object], visible: bool) -> None:
        hwnd = int(info.get("hwnd") or 0)
        if not hwnd:
            return
        left, top, width, height = key
        if visible:
            try:
                user32.SetWindowPos(
                    wintypes.HWND(hwnd),
                    wintypes.HWND(HWND_TOPMOST),
                    left,
                    top,
                    width,
                    height,
                    SWP_NOACTIVATE | SWP_SHOWWINDOW,
                )
                if getattr(user32, "ShowWindowAsync", None):
                    user32.ShowWindowAsync(wintypes.HWND(hwnd), SW_SHOWNOACTIVATE)
                else:
                    user32.ShowWindow(wintypes.HWND(hwnd), SW_SHOWNOACTIVATE)
                info["hidden"] = False
                return
            except Exception:
                pass
        try:
            user32.SetWindowPos(
                wintypes.HWND(hwnd),
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
                user32.ShowWindowAsync(wintypes.HWND(hwnd), SW_HIDE)
            else:
                user32.ShowWindow(wintypes.HWND(hwnd), SW_HIDE)
        except Exception:
            pass
        info["hidden"] = True

    def _cleanup_expired_helper_covers(*, force: bool = False) -> None:
        lock = _CBT_STARTUP_HELPER_COVER_LOCK
        if lock is None:
            return
        try:
            now = time.monotonic()
        except Exception:
            now = 0.0
        with lock:
            items = list(_CBT_STARTUP_HELPER_COVERS.items())
        for key, info in items:
            try:
                expires_at = float(info.get("expires_at") or 0.0)
            except Exception:
                expires_at = 0.0
            if not force and expires_at > now:
                continue
            if bool(info.get("hidden")) and not force:
                continue
            _set_helper_cover_visible(key, info, False)

    def _ensure_helper_cover_cleanup_thread() -> None:
        global _CBT_STARTUP_HELPER_COVER_STOP, _CBT_STARTUP_HELPER_COVER_THREAD
        if _CBT_STARTUP_HELPER_COVER_THREAD is not None:
            return
        stop_event = threading.Event()
        _CBT_STARTUP_HELPER_COVER_STOP = stop_event

        def _cover_cleanup_loop() -> None:
            while not stop_event.wait(0.03):
                _cleanup_expired_helper_covers(force=False)

        thread = threading.Thread(target=_cover_cleanup_loop, name="cbt-helper-cover-cleanup", daemon=True)
        _CBT_STARTUP_HELPER_COVER_THREAD = thread
        thread.start()

    def _create_helper_cover(left: int, top: int, width: int, height: int) -> tuple[int, int]:
        screen_dc = None
        mem_dc = None
        bitmap = 0
        old_obj = 0
        hwnd = 0
        try:
            screen_dc = user32.GetDC(0)
            if not screen_dc:
                return 0, 0
            mem_dc = gdi32.CreateCompatibleDC(screen_dc)
            if not mem_dc:
                return 0, 0
            bitmap = int(gdi32.CreateCompatibleBitmap(screen_dc, width, height) or 0)
            if not bitmap:
                return 0, 0
            old_obj = int(gdi32.SelectObject(mem_dc, bitmap) or 0)
            if not gdi32.BitBlt(mem_dc, 0, 0, width, height, screen_dc, left, top, SRCCOPY | CAPTUREBLT):
                return 0, 0
            hwnd = int(
                user32.CreateWindowExW(
                    WS_EX_TOPMOST | WS_EX_TOOLWINDOW | WS_EX_NOACTIVATE | WS_EX_LAYERED | WS_EX_TRANSPARENT,
                    "Static",
                    _HELPER_COVER_TITLE,
                    WS_POPUP | SS_BITMAP,
                    left,
                    top,
                    width,
                    height,
                    0,
                    0,
                    0,
                    None,
                )
                or 0
            )
            if not hwnd:
                return 0, 0
            user32.SendMessageW(wintypes.HWND(hwnd), STM_SETIMAGE, IMAGE_BITMAP, bitmap)
            user32.SetWindowPos(
                wintypes.HWND(hwnd),
                wintypes.HWND(HWND_TOPMOST),
                left,
                top,
                width,
                height,
                SWP_NOACTIVATE | SWP_SHOWWINDOW,
            )
            return hwnd, bitmap
        except Exception:
            return 0, 0
        finally:
            try:
                if mem_dc:
                    if old_obj:
                        gdi32.SelectObject(mem_dc, old_obj)
                    gdi32.DeleteDC(mem_dc)
            except Exception:
                pass
            try:
                if screen_dc:
                    user32.ReleaseDC(0, screen_dc)
            except Exception:
                pass

    def _show_helper_cover(left: int, top: int, width: int, height: int, *, duration_ms: int = 900) -> None:
        if width <= 0 or height <= 0:
            return
        if width > 6000 or height > 160:
            return
        if abs(int(left)) > 50000 or abs(int(top)) > 50000:
            return
        if left <= -32000 or top <= -32000:
            return
        key = (int(left), int(top), int(width), int(height))
        try:
            expires_at = time.monotonic() + (max(120, min(duration_ms, 5000)) / 1000.0)
        except Exception:
            expires_at = 0.0
        lock = _CBT_STARTUP_HELPER_COVER_LOCK
        if lock is None:
            return
        with lock:
            existing = _CBT_STARTUP_HELPER_COVERS.get(key)
            if existing is not None:
                existing["expires_at"] = max(float(existing.get("expires_at") or 0.0), expires_at)
                if bool(existing.get("hidden")):
                    _set_helper_cover_visible(key, existing, True)
                return
        hwnd, bitmap = _create_helper_cover(left, top, width, height)
        if not hwnd:
            return
        with lock:
            existing = _CBT_STARTUP_HELPER_COVERS.get(key)
            if existing is None:
                _CBT_STARTUP_HELPER_COVERS[key] = {
                    "hwnd": int(hwnd),
                    "hbitmap": int(bitmap),
                    "expires_at": float(expires_at),
                    "hidden": False,
                }
            else:
                existing["expires_at"] = max(float(existing.get("expires_at") or 0.0), expires_at)
                if bool(existing.get("hidden")):
                    _set_helper_cover_visible(key, existing, True)
        _ensure_helper_cover_cleanup_thread()
        if debug_window_events:
            try:
                with open(debug_log_path, "a", encoding="utf-8", errors="ignore") as fh:
                    fh.write(f"cbt-cover-show rect={left},{top},{width},{height} hwnd={hwnd}\n")
            except Exception:
                pass

    def _cbt_proc(n_code, w_param, l_param):  # noqa: ANN001
        try:
            if int(n_code) != HCBT_CREATEWND:
                return user32.CallNextHookEx(0, n_code, w_param, l_param)
            hwnd_val = int(w_param)
            if not hwnd_val:
                return user32.CallNextHookEx(0, n_code, w_param, l_param)
            lp_val = int(l_param)
            if not lp_val or lp_val < 0x10000:
                return user32.CallNextHookEx(0, n_code, w_param, l_param)
            cbt = ctypes.cast(lp_val, ctypes.POINTER(CBT_CREATEWND)).contents
            if not cbt.lpcs:
                return user32.CallNextHookEx(0, n_code, w_param, l_param)
            cs = cbt.lpcs.contents
            width = int(cs.cx)
            height = int(cs.cy)
            if width <= 0 or height <= 0:
                return user32.CallNextHookEx(0, n_code, w_param, l_param)
            cs_class = _read_cs_string(cs.lpszClass)
            cs_title = _read_cs_string(cs.lpszName)
            if cs_title == _HELPER_COVER_TITLE:
                return user32.CallNextHookEx(0, n_code, w_param, l_param)
            style = int(cs.style) & 0xFFFFFFFF
            if style & WS_CHILD:
                return user32.CallNextHookEx(0, n_code, w_param, l_param)
            class_name = cs_class or _read_hwnd_class(hwnd_val)
            title_text = cs_title or _read_hwnd_title(hwnd_val)
            if _looks_like_qt_internal_helper_window(class_name=class_name, title=title_text):
                orig_x = int(cs.x)
                orig_y = int(cs.y)
                is_q_titlebar_helper = class_name == "_q_titlebar" or title_text == "_q_titlebar"
                if is_q_titlebar_helper:
                    _show_helper_cover(orig_x, orig_y, width, height)
                cs.style = int(style & ~WS_VISIBLE)
                ex_style = int(cs.dwExStyle) & 0xFFFFFFFF
                cs.dwExStyle = int((ex_style | WS_EX_TOOLWINDOW | WS_EX_NOACTIVATE) & ~WS_EX_APPWINDOW)
                cs.x = -32000
                cs.y = -32000
                cs.cx = 1
                cs.cy = 1
                if debug_window_events:
                    try:
                        with open(debug_log_path, "a", encoding="utf-8", errors="ignore") as fh:
                            reason = "cbt-hide-qt-titlebar-helper" if is_q_titlebar_helper else "cbt-hide-qt-helper"
                            fh.write(
                                f"{reason} hwnd={hwnd_val} pos={orig_x},{orig_y} size={width}x{height} class={class_name!r} title={title_text!r} "
                                f"style=0x{style:08X} exstyle=0x{ex_style:08X}\n"
                            )
                    except Exception:
                        pass
                return user32.CallNextHookEx(0, n_code, w_param, l_param)
            if width >= 360 and height >= 220:
                return user32.CallNextHookEx(0, n_code, w_param, l_param)
            is_tiny_strip = height <= 120 and width <= 4000
            is_tiny_popup = width <= 320 and height <= 320
            if is_tiny_strip or is_tiny_popup:
                cs.style = int(style & ~WS_VISIBLE)
                ex_style = int(cs.dwExStyle) & 0xFFFFFFFF
                cs.dwExStyle = int((ex_style | WS_EX_TOOLWINDOW | WS_EX_NOACTIVATE) & ~WS_EX_APPWINDOW)
                cs.x = -32000
                cs.y = -32000
                cs.cx = 1
                cs.cy = 1
                if debug_window_events:
                    try:
                        with open(debug_log_path, "a", encoding="utf-8", errors="ignore") as fh:
                            fh.write(
                                f"cbt-hide hwnd={hwnd_val} size={width}x{height} class={class_name!r} title={cs_title!r} "
                                f"style=0x{style:08X} exstyle=0x{ex_style:08X}\n"
                            )
                    except Exception:
                        pass
        except Exception:
            pass
        return user32.CallNextHookEx(0, n_code, w_param, l_param)

    _CBT_STARTUP_WINDOW_PROC = CBTProc(_cbt_proc)

    if _CBT_STARTUP_WINDOW_LOCK is None:
        _CBT_STARTUP_WINDOW_LOCK = threading.Lock()

    try:
        user32.PostThreadMessageW.argtypes = [wintypes.DWORD, wintypes.UINT, wintypes.WPARAM, wintypes.LPARAM]
        user32.PostThreadMessageW.restype = wintypes.BOOL
    except Exception:
        pass

    def _install_hook_for_thread(thread_id: int) -> None:
        if not thread_id:
            return
        if _CBT_STARTUP_WINDOW_PROC is None or _CBT_STARTUP_WINDOW_LOCK is None:
            return
        with _CBT_STARTUP_WINDOW_LOCK:
            if thread_id in _CBT_STARTUP_WINDOW_HOOKS:
                return
            hook = user32.SetWindowsHookExW(WH_CBT, _CBT_STARTUP_WINDOW_PROC, 0, int(thread_id))
            if hook:
                _CBT_STARTUP_WINDOW_HOOKS[int(thread_id)] = int(hook)
            if debug_window_events:
                try:
                    with open(debug_log_path, "a", encoding="utf-8", errors="ignore") as fh:
                        fh.write(f"cbt-hook-install tid={int(thread_id)} hook={int(hook) if hook else 0}\n")
                except Exception:
                    pass

    try:
        msg = wintypes.MSG()
        user32.PeekMessageW(ctypes.byref(msg), 0, 0, 0, 0)
    except Exception:
        pass
    try:
        current_tid = int(kernel32.GetCurrentThreadId())
    except Exception:
        current_tid = 0
    _install_hook_for_thread(current_tid)

    def _enumerate_thread_ids(pid: int) -> set[int]:
        thread_ids: set[int] = set()
        if not pid:
            return thread_ids
        try:
            TH32CS_SNAPTHREAD = 0x00000004
            snapshot = kernel32.CreateToolhelp32Snapshot(TH32CS_SNAPTHREAD, 0)
            if snapshot in (0, ctypes.c_void_p(-1).value):
                return thread_ids

            class THREADENTRY32(ctypes.Structure):
                _fields_ = [
                    ("dwSize", wintypes.DWORD),
                    ("cntUsage", wintypes.DWORD),
                    ("th32ThreadID", wintypes.DWORD),
                    ("th32OwnerProcessID", wintypes.DWORD),
                    ("tpBasePri", wintypes.LONG),
                    ("tpDeltaPri", wintypes.LONG),
                    ("dwFlags", wintypes.DWORD),
                ]

            entry = THREADENTRY32()
            entry.dwSize = ctypes.sizeof(entry)
            try:
                if not kernel32.Thread32First(snapshot, ctypes.byref(entry)):
                    return thread_ids
                while True:
                    if int(entry.th32OwnerProcessID) == int(pid):
                        thread_ids.add(int(entry.th32ThreadID))
                    if not kernel32.Thread32Next(snapshot, ctypes.byref(entry)):
                        break
            finally:
                try:
                    kernel32.CloseHandle(snapshot)
                except Exception:
                    pass
        except Exception:
            return thread_ids
        return thread_ids

    try:
        scan_ms = int(os.environ.get("BOT_CBT_THREAD_HOOK_SCAN_MS") or 0)
    except Exception:
        scan_ms = 0
    scan_ms = max(0, min(30000, scan_ms))
    try:
        interval_ms = int(os.environ.get("BOT_CBT_THREAD_HOOK_SCAN_INTERVAL_MS") or 50)
    except Exception:
        interval_ms = 50
    interval_ms = max(20, min(250, interval_ms))

    try:
        pid_val = int(kernel32.GetCurrentProcessId())
    except Exception:
        pid_val = 0

    if scan_ms <= 0:
        return

    stop_event = threading.Event()
    _CBT_STARTUP_WINDOW_SCAN_STOP = stop_event

    def _scan_loop() -> None:
        deadline = time.monotonic() + (scan_ms / 1000.0)
        while time.monotonic() < deadline and not stop_event.is_set():
            for tid in _enumerate_thread_ids(pid_val):
                _install_hook_for_thread(tid)
            time.sleep(interval_ms / 1000.0)

    thread = threading.Thread(target=_scan_loop, name="cbt-hook-scan", daemon=True)
    _CBT_STARTUP_WINDOW_SCAN_THREAD = thread
    thread.start()


def _uninstall_cbt_startup_window_suppression() -> None:
    global _CBT_STARTUP_WINDOW_PROC, _CBT_STARTUP_WINDOW_SCAN_STOP, _CBT_STARTUP_WINDOW_SCAN_THREAD, _CBT_STARTUP_WINDOW_LOCK
    global _CBT_STARTUP_HELPER_COVER_LOCK, _CBT_STARTUP_HELPER_COVER_STOP, _CBT_STARTUP_HELPER_COVER_THREAD
    if sys.platform != "win32" or _CBT_STARTUP_WINDOW_PROC is None:
        return
    try:
        stop_event = _CBT_STARTUP_WINDOW_SCAN_STOP
        if stop_event is not None:
            stop_event.set()
    except Exception:
        pass
    try:
        thread = _CBT_STARTUP_WINDOW_SCAN_THREAD
        if thread is not None and getattr(thread, "is_alive", lambda: False)():
            try:
                thread.join(timeout=0.5)
            except Exception:
                pass
    except Exception:
        pass
    try:
        stop_event = _CBT_STARTUP_HELPER_COVER_STOP
        if stop_event is not None:
            stop_event.set()
    except Exception:
        pass
    try:
        thread = _CBT_STARTUP_HELPER_COVER_THREAD
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
        hooks = list(_CBT_STARTUP_WINDOW_HOOKS.values())
        if _CBT_STARTUP_WINDOW_LOCK is not None:
            try:
                with _CBT_STARTUP_WINDOW_LOCK:
                    _CBT_STARTUP_WINDOW_HOOKS.clear()
            except Exception:
                pass
        for hook in hooks:
            try:
                user32.UnhookWindowsHookEx(hook)
            except Exception:
                pass
        helper_covers = list(_CBT_STARTUP_HELPER_COVERS.items())
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
    _CBT_STARTUP_WINDOW_HOOKS.clear()
    _CBT_STARTUP_HELPER_COVERS.clear()
    _CBT_STARTUP_WINDOW_PROC = None
    _CBT_STARTUP_WINDOW_SCAN_STOP = None
    _CBT_STARTUP_WINDOW_SCAN_THREAD = None
    _CBT_STARTUP_WINDOW_LOCK = None
    _CBT_STARTUP_HELPER_COVER_LOCK = None
    _CBT_STARTUP_HELPER_COVER_STOP = None
    _CBT_STARTUP_HELPER_COVER_THREAD = None
