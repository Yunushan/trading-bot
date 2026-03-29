from __future__ import annotations

import os
import sys
import threading
import time

from .startup_ui_shared import _env_flag


class _NativeStartupCover:
    def __init__(self, hwnd: int = 0, hbitmap: int = 0):
        self.hwnd = int(hwnd or 0)
        self.hbitmap = int(hbitmap or 0)
        self._stop_event = threading.Event()
        self._raise_thread = None
        if self.hwnd:
            thread = threading.Thread(target=self._raise_loop, name="bot-native-startup-cover", daemon=True)
            self._raise_thread = thread
            thread.start()

    def _raise_loop(self) -> None:
        if sys.platform != "win32":
            return
        try:
            import ctypes
            import ctypes.wintypes as wintypes

            user32 = ctypes.windll.user32
            HWND_TOPMOST = -1
            SWP_NOMOVE = 0x0002
            SWP_NOSIZE = 0x0001
            SWP_NOACTIVATE = 0x0010
            SWP_SHOWWINDOW = 0x0040
        except Exception:
            return
        deadline = time.monotonic() + 8.0
        while not self._stop_event.is_set() and time.monotonic() < deadline:
            hwnd = int(self.hwnd or 0)
            if not hwnd:
                return
            try:
                user32.SetWindowPos(
                    wintypes.HWND(hwnd),
                    wintypes.HWND(HWND_TOPMOST),
                    0,
                    0,
                    0,
                    0,
                    SWP_NOMOVE | SWP_NOSIZE | SWP_NOACTIVATE | SWP_SHOWWINDOW,
                )
            except Exception:
                pass
            self._stop_event.wait(0.015)

    def close(self) -> None:
        if sys.platform != "win32":
            return
        try:
            import ctypes
        except Exception:
            return
        hwnd = int(self.hwnd or 0)
        hbitmap = int(self.hbitmap or 0)
        self.hwnd = 0
        self.hbitmap = 0
        try:
            self._stop_event.set()
        except Exception:
            pass
        try:
            thread = self._raise_thread
            if thread is not None and thread.is_alive():
                thread.join(timeout=0.2)
        except Exception:
            pass
        self._raise_thread = None
        try:
            if hwnd:
                ctypes.windll.user32.DestroyWindow(ctypes.c_void_p(hwnd))
        except Exception:
            pass
        try:
            if hbitmap:
                ctypes.windll.gdi32.DeleteObject(ctypes.c_void_p(hbitmap))
        except Exception:
            pass


def _show_native_startup_cover() -> _NativeStartupCover | None:
    if sys.platform != "win32":
        return None
    if not _env_flag("BOT_STARTUP_MASK_ENABLED"):
        return None
    if not _env_flag("BOT_NATIVE_STARTUP_COVER_ENABLED"):
        return None
    startup_mask_mode = str(os.environ.get("BOT_STARTUP_MASK_MODE") or "snapshot").strip().lower()
    if startup_mask_mode not in {"", "snapshot", "screen"}:
        return None
    try:
        import ctypes
        import ctypes.wintypes as wintypes
    except Exception:
        return None
    user32 = ctypes.windll.user32
    gdi32 = ctypes.windll.gdi32
    MONITOR_DEFAULTTOPRIMARY = 1
    WS_EX_TOPMOST = 0x00000008
    WS_EX_TOOLWINDOW = 0x00000080
    WS_EX_NOACTIVATE = 0x08000000
    WS_POPUP = 0x80000000
    SS_BITMAP = 0x0000000E
    HWND_TOPMOST = -1
    SWP_NOACTIVATE = 0x0010
    SWP_SHOWWINDOW = 0x0040
    STM_SETIMAGE = 0x0172
    IMAGE_BITMAP = 0
    SRCCOPY = 0x00CC0020
    CAPTUREBLT = 0x40000000

    class POINT(ctypes.Structure):
        _fields_ = [("x", wintypes.LONG), ("y", wintypes.LONG)]

    class RECT(ctypes.Structure):
        _fields_ = [("left", wintypes.LONG), ("top", wintypes.LONG), ("right", wintypes.LONG), ("bottom", wintypes.LONG)]

    class MONITORINFO(ctypes.Structure):
        _fields_ = [("cbSize", wintypes.DWORD), ("rcMonitor", RECT), ("rcWork", RECT), ("dwFlags", wintypes.DWORD)]

    try:
        user32.MonitorFromPoint.argtypes = [POINT, wintypes.DWORD]
        user32.MonitorFromPoint.restype = wintypes.HMONITOR
        user32.GetMonitorInfoW.argtypes = [wintypes.HMONITOR, ctypes.POINTER(MONITORINFO)]
        user32.GetMonitorInfoW.restype = wintypes.BOOL
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
        user32.UpdateWindow.argtypes = [wintypes.HWND]
        user32.UpdateWindow.restype = wintypes.BOOL
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
    try:
        monitor = user32.MonitorFromPoint(POINT(0, 0), MONITOR_DEFAULTTOPRIMARY)
        if not monitor:
            return None
        mi = MONITORINFO()
        mi.cbSize = ctypes.sizeof(mi)
        if not user32.GetMonitorInfoW(monitor, ctypes.byref(mi)):
            return None
        left = int(mi.rcMonitor.left)
        top = int(mi.rcMonitor.top)
        width = int(mi.rcMonitor.right - mi.rcMonitor.left)
        height = int(mi.rcMonitor.bottom - mi.rcMonitor.top)
        if width <= 0 or height <= 0:
            return None
    except Exception:
        return None
    screen_dc = None
    mem_dc = None
    bitmap = 0
    old_obj = 0
    hwnd = 0
    try:
        screen_dc = user32.GetDC(0)
        if not screen_dc:
            return None
        mem_dc = gdi32.CreateCompatibleDC(screen_dc)
        if not mem_dc:
            return None
        bitmap = int(gdi32.CreateCompatibleBitmap(screen_dc, width, height) or 0)
        if not bitmap:
            return None
        old_obj = int(gdi32.SelectObject(mem_dc, bitmap) or 0)
        if not gdi32.BitBlt(mem_dc, 0, 0, width, height, screen_dc, left, top, SRCCOPY | CAPTUREBLT):
            return None
        hwnd = int(
            user32.CreateWindowExW(
                WS_EX_TOPMOST | WS_EX_TOOLWINDOW | WS_EX_NOACTIVATE,
                "Static",
                None,
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
            return None
        user32.SendMessageW(hwnd, STM_SETIMAGE, IMAGE_BITMAP, bitmap)
        user32.SetWindowPos(hwnd, HWND_TOPMOST, left, top, width, height, SWP_NOACTIVATE | SWP_SHOWWINDOW)
        user32.UpdateWindow(hwnd)
        return _NativeStartupCover(hwnd=hwnd, hbitmap=bitmap)
    except Exception:
        if hwnd:
            try:
                user32.DestroyWindow(hwnd)
            except Exception:
                pass
        if bitmap:
            try:
                gdi32.DeleteObject(bitmap)
            except Exception:
                pass
        return None
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
