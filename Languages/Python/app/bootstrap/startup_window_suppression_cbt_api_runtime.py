from __future__ import annotations

import os
from pathlib import Path
from types import SimpleNamespace

from .startup_window_suppression_shared_runtime import _env_flag


def build_cbt_api():
    try:  # pragma: no cover - Windows only
        import ctypes
        import ctypes.wintypes as wintypes
        import threading
        import time
    except Exception:
        return None, None, None

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
    HELPER_COVER_TITLE = "__BOT_STARTUP_HELPER_COVER__"

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

    api = SimpleNamespace(
        ctypes=ctypes,
        wintypes=wintypes,
        user32=user32,
        kernel32=kernel32,
        gdi32=gdi32,
        threading=threading,
        time=time,
        debug_window_events=debug_window_events,
        debug_log_path=debug_log_path,
        WH_CBT=WH_CBT,
        HCBT_CREATEWND=HCBT_CREATEWND,
        WS_CHILD=WS_CHILD,
        WS_VISIBLE=WS_VISIBLE,
        WS_EX_TOOLWINDOW=WS_EX_TOOLWINDOW,
        WS_EX_APPWINDOW=WS_EX_APPWINDOW,
        WS_EX_NOACTIVATE=WS_EX_NOACTIVATE,
        WS_EX_TOPMOST=WS_EX_TOPMOST,
        WS_EX_LAYERED=WS_EX_LAYERED,
        WS_EX_TRANSPARENT=WS_EX_TRANSPARENT,
        WS_POPUP=WS_POPUP,
        SS_BITMAP=SS_BITMAP,
        HWND_TOPMOST=HWND_TOPMOST,
        SW_HIDE=SW_HIDE,
        SW_SHOWNOACTIVATE=SW_SHOWNOACTIVATE,
        SWP_NOSIZE=SWP_NOSIZE,
        SWP_NOZORDER=SWP_NOZORDER,
        SWP_NOACTIVATE=SWP_NOACTIVATE,
        SWP_SHOWWINDOW=SWP_SHOWWINDOW,
        SWP_HIDEWINDOW=SWP_HIDEWINDOW,
        SWP_ASYNCWINDOWPOS=SWP_ASYNCWINDOWPOS,
        STM_SETIMAGE=STM_SETIMAGE,
        IMAGE_BITMAP=IMAGE_BITMAP,
        SRCCOPY=SRCCOPY,
        CAPTUREBLT=CAPTUREBLT,
        HELPER_COVER_TITLE=HELPER_COVER_TITLE,
    )
    return api, CBTProc, CBT_CREATEWND
