from __future__ import annotations

import os
import shutil
import subprocess
import sys
import threading
import time
from pathlib import Path

APP_DISPLAY_NAME = str(os.environ.get("BOT_TASKBAR_DISPLAY_NAME") or "Trading Bot").strip() or "Trading Bot"
_native_icon_handles: list[int] = []
_PROJECT_ROOT = Path(__file__).resolve().parents[4]


def _env_flag(name: str) -> bool:
    return str(os.environ.get(name, "")).strip().lower() in {"1", "true", "yes", "on"}


def _boot_log(message: str) -> None:
    if not _env_flag("BOT_BOOT_LOG"):
        return
    try:
        print(f"[boot] {message}", flush=True)
    except Exception:
        pass


def _resolve_native_icon_path() -> Path | None:
    from app.gui.shared.app_icon import find_primary_icon_file

    path = find_primary_icon_file()
    if path is None:
        return None
    if path.suffix.lower() == ".ico":
        return path
    fallback = path.with_suffix(".ico")
    return fallback if fallback.is_file() else None


def _stable_icon_cache_path() -> Path | None:
    base = str(os.environ.get("LOCALAPPDATA") or os.environ.get("APPDATA") or "").strip()
    if not base:
        return None
    try:
        cache_dir = Path(base).resolve() / "TradingBot" / "assets"
        cache_dir.mkdir(parents=True, exist_ok=True)
        return cache_dir / "crypto_forex_logo.ico"
    except Exception:
        return None


def _persist_icon_for_taskbar(icon_path: Path | None) -> Path | None:
    if icon_path is None or not icon_path.is_file():
        return None
    if icon_path.suffix.lower() != ".ico":
        ico_path = icon_path.with_suffix(".ico")
        if not ico_path.is_file():
            return None
        icon_path = ico_path
    target = _stable_icon_cache_path()
    if target is None:
        return None
    try:
        src = icon_path.resolve()
        if target.exists():
            try:
                if target.resolve() == src:
                    return target
            except Exception:
                pass
        shutil.copy2(src, target)
        return target
    except Exception:
        return None


def _resolve_taskbar_icon_path() -> Path | None:
    env_icon = os.environ.get("BOT_TASKBAR_ICON") or os.environ.get("BINANCE_BOT_ICON")
    if env_icon:
        env_path = Path(env_icon).expanduser()
        if env_path.is_file():
            if env_path.suffix.lower() == ".ico":
                return env_path
            ico_path = env_path.with_suffix(".ico")
            if ico_path.is_file():
                return ico_path
            return env_path
    if getattr(sys, "frozen", False):
        try:
            exe_icon = Path(sys.executable).resolve()
        except Exception:
            exe_icon = None
        if exe_icon is not None and exe_icon.is_file():
            return exe_icon
    native_icon = _resolve_native_icon_path()
    persisted = _persist_icon_for_taskbar(native_icon)
    if persisted and persisted.is_file():
        return persisted
    icon_path = _resolve_native_icon_path()
    if icon_path and icon_path.is_file():
        return icon_path
    from app.gui.shared.app_icon import find_primary_icon_file

    primary = find_primary_icon_file()
    if primary and primary.is_file():
        if primary.suffix.lower() == ".ico":
            return primary
        ico_path = primary.with_suffix(".ico")
        if ico_path.is_file():
            return ico_path
        return primary
    repo_icon = _PROJECT_ROOT / "assets" / "crypto_forex_logo.ico"
    return repo_icon if repo_icon.is_file() else None


def _resolve_splash_logo_pixmap(QtGui):  # noqa: N803
    candidates: list[Path] = []
    env_logo = str(os.environ.get("BOT_SPLASH_LOGO") or os.environ.get("BINANCE_BOT_SPLASH") or "").strip()
    if env_logo:
        candidates.append(Path(env_logo).expanduser())

    meipass = getattr(sys, "_MEIPASS", None)
    if meipass:
        meipass_path = Path(meipass)
        candidates.extend(
            [
                meipass_path / "assets" / "crypto_forex_logo.png",
                meipass_path / "assets" / "crypto_forex_logo.ico",
                meipass_path / "crypto_forex_logo.png",
                meipass_path / "crypto_forex_logo.ico",
            ]
        )

    try:
        exe_dir = Path(sys.executable).resolve().parent
    except Exception:
        exe_dir = None
    if exe_dir is not None:
        candidates.extend(
            [
                exe_dir / "assets" / "crypto_forex_logo.png",
                exe_dir / "assets" / "crypto_forex_logo.ico",
                exe_dir / "crypto_forex_logo.png",
                exe_dir / "crypto_forex_logo.ico",
            ]
        )

    root_assets = _PROJECT_ROOT / "assets"
    candidates.extend(
        [
            root_assets / "crypto_forex_logo.png",
            root_assets / "crypto_forex_logo.ico",
        ]
    )

    seen: set[Path] = set()
    for candidate in candidates:
        if candidate in seen:
            continue
        seen.add(candidate)
        if not candidate.is_file():
            continue
        try:
            pixmap = QtGui.QPixmap(str(candidate))
            if pixmap is not None and not pixmap.isNull():
                return pixmap
        except Exception:
            pass
        try:
            icon = QtGui.QIcon(str(candidate))
            if icon is not None and not icon.isNull():
                pixmap = icon.pixmap(96, 96)
                if pixmap is not None and not pixmap.isNull():
                    return pixmap
        except Exception:
            pass
    return None


def _format_shortcut_args(script_path: Path) -> str:
    try:
        return subprocess.list2cmdline([str(script_path.resolve())])
    except Exception:
        return f"\"{script_path.resolve()}\""


def _get_hwnd(window) -> int:  # noqa: ANN001
    try:
        if hasattr(window, "effectiveWinId"):
            try:
                win_id = window.effectiveWinId()
                if win_id:
                    return int(win_id)
            except Exception:
                pass
        try:
            win_id = window.winId()
            if win_id:
                return int(win_id)
        except Exception:
            pass
        try:
            handle = window.windowHandle()
        except Exception:
            handle = None
        if handle is not None:
            try:
                win_id = handle.winId()
                if win_id:
                    return int(win_id)
            except Exception:
                pass
    except Exception:
        return 0
    return 0


def _set_native_window_icon(window) -> bool:  # noqa: ANN001
    if sys.platform != "win32":
        return False
    icon_path = _resolve_native_icon_path()
    if icon_path is None:
        taskbar_icon = _resolve_taskbar_icon_path()
        if taskbar_icon is not None and str(taskbar_icon).lower().endswith(".ico"):
            icon_path = taskbar_icon
    if icon_path is None or not icon_path.is_file():
        return False
    try:
        import ctypes
        import ctypes.wintypes as wintypes
    except Exception:
        return False
    hwnd = _get_hwnd(window)
    if not hwnd:
        return False
    user32 = ctypes.windll.user32
    try:
        user32.GetWindowLongPtrW.argtypes = [wintypes.HWND, ctypes.c_int]
        user32.GetWindowLongPtrW.restype = ctypes.c_longlong
        user32.SetWindowLongPtrW.argtypes = [wintypes.HWND, ctypes.c_int, ctypes.c_longlong]
        user32.SetWindowLongPtrW.restype = ctypes.c_longlong
    except Exception:
        pass
    try:
        user32.GetWindowLongW.argtypes = [wintypes.HWND, ctypes.c_int]
        user32.GetWindowLongW.restype = ctypes.c_long
        user32.SetWindowLongW.argtypes = [wintypes.HWND, ctypes.c_int, ctypes.c_long]
        user32.SetWindowLongW.restype = ctypes.c_long
    except Exception:
        pass
    try:
        get_style = getattr(user32, "GetWindowLongPtrW", None) or user32.GetWindowLongW
        set_style = getattr(user32, "SetWindowLongPtrW", None) or user32.SetWindowLongW
        style = int(get_style(hwnd, -16))
        exstyle = int(get_style(hwnd, -20))
        WS_SYSMENU = 0x00080000
        WS_EX_TOOLWINDOW = 0x00000080
        WS_EX_APPWINDOW = 0x00040000
        if not (style & WS_SYSMENU):
            set_style(hwnd, -16, int(style | WS_SYSMENU))
        new_exstyle = int((exstyle | WS_EX_APPWINDOW) & ~WS_EX_TOOLWINDOW)
        if new_exstyle != exstyle:
            set_style(hwnd, -20, new_exstyle)
        try:
            SWP_NOSIZE = 0x0001
            SWP_NOMOVE = 0x0002
            SWP_NOZORDER = 0x0004
            SWP_NOACTIVATE = 0x0010
            SWP_FRAMECHANGED = 0x0020
            user32.SetWindowPos(
                hwnd,
                0,
                0,
                0,
                0,
                0,
                SWP_NOSIZE | SWP_NOMOVE | SWP_NOZORDER | SWP_NOACTIVATE | SWP_FRAMECHANGED,
            )
        except Exception:
            pass
    except Exception:
        pass
    IMAGE_ICON = 1
    LR_LOADFROMFILE = 0x00000010
    LR_DEFAULTSIZE = 0x00000040
    try:
        user32.GetSystemMetrics.argtypes = [ctypes.c_int]
        user32.GetSystemMetrics.restype = ctypes.c_int
        user32.LoadImageW.argtypes = [
            wintypes.HINSTANCE,
            wintypes.LPCWSTR,
            wintypes.UINT,
            ctypes.c_int,
            ctypes.c_int,
            wintypes.UINT,
        ]
        user32.LoadImageW.restype = wintypes.HICON
    except Exception:
        pass
    try:
        cx_small = int(user32.GetSystemMetrics(49))
        cy_small = int(user32.GetSystemMetrics(50))
        cx_big = int(user32.GetSystemMetrics(11))
        cy_big = int(user32.GetSystemMetrics(12))
    except Exception:
        cx_small = cy_small = cx_big = cy_big = 0
    hicon_small = user32.LoadImageW(0, str(icon_path), IMAGE_ICON, cx_small, cy_small, LR_LOADFROMFILE)
    hicon_big = user32.LoadImageW(0, str(icon_path), IMAGE_ICON, cx_big, cy_big, LR_LOADFROMFILE)
    if not hicon_small and not hicon_big:
        hicon_big = user32.LoadImageW(0, str(icon_path), IMAGE_ICON, 0, 0, LR_LOADFROMFILE | LR_DEFAULTSIZE)
    if not hicon_small and not hicon_big:
        return False
    WM_SETICON = 0x0080
    ICON_SMALL = 0
    ICON_BIG = 1
    try:
        user32.SendMessageW.argtypes = [
            wintypes.HWND,
            wintypes.UINT,
            wintypes.WPARAM,
            wintypes.LPARAM,
        ]
        user32.SendMessageW.restype = wintypes.LRESULT
    except Exception:
        pass
    applied = False
    if hicon_small:
        user32.SendMessageW(hwnd, WM_SETICON, ICON_SMALL, hicon_small)
        _native_icon_handles.append(int(hicon_small))
        applied = True
    if hicon_big:
        user32.SendMessageW(hwnd, WM_SETICON, ICON_BIG, hicon_big)
        _native_icon_handles.append(int(hicon_big))
        applied = True
    try:
        user32.SetClassLongPtrW.argtypes = [wintypes.HWND, ctypes.c_int, ctypes.c_void_p]
        user32.SetClassLongPtrW.restype = ctypes.c_void_p
    except Exception:
        pass
    try:
        user32.SetClassLongW.argtypes = [wintypes.HWND, ctypes.c_int, ctypes.c_long]
        user32.SetClassLongW.restype = ctypes.c_long
    except Exception:
        pass
    if applied:
        try:
            set_class = getattr(user32, "SetClassLongPtrW", None) or user32.SetClassLongW
            GCLP_HICON = -14
            GCLP_HICONSM = -34
            if hicon_big:
                set_class(hwnd, GCLP_HICON, hicon_big)
            if hicon_small:
                set_class(hwnd, GCLP_HICONSM, hicon_small)
        except Exception:
            pass
    return applied


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
        user32.CreateWindowExW.argtypes = [wintypes.DWORD, wintypes.LPCWSTR, wintypes.LPCWSTR, wintypes.DWORD, ctypes.c_int, ctypes.c_int, ctypes.c_int, ctypes.c_int, wintypes.HWND, wintypes.HMENU, wintypes.HINSTANCE, wintypes.LPVOID]
        user32.CreateWindowExW.restype = wintypes.HWND
        user32.SendMessageW.argtypes = [wintypes.HWND, wintypes.UINT, wintypes.WPARAM, wintypes.LPARAM]
        user32.SendMessageW.restype = wintypes.LRESULT
        user32.SetWindowPos.argtypes = [wintypes.HWND, wintypes.HWND, ctypes.c_int, ctypes.c_int, ctypes.c_int, ctypes.c_int, wintypes.UINT]
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
        gdi32.BitBlt.argtypes = [wintypes.HDC, ctypes.c_int, ctypes.c_int, ctypes.c_int, ctypes.c_int, wintypes.HDC, ctypes.c_int, ctypes.c_int, wintypes.DWORD]
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
        hwnd = int(user32.CreateWindowExW(WS_EX_TOPMOST | WS_EX_TOOLWINDOW | WS_EX_NOACTIVATE, "Static", None, WS_POPUP | SS_BITMAP, left, top, width, height, 0, 0, 0, None) or 0)
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


def _apply_qt_icon(app, window) -> bool:
    from PyQt6 import QtGui
    from app.gui.shared.app_icon import find_primary_icon_file, load_app_icon

    icon = QtGui.QIcon()
    try:
        icon = load_app_icon()
    except Exception:
        icon = QtGui.QIcon()
    if icon.isNull():
        try:
            fallback_path = find_primary_icon_file()
        except Exception:
            fallback_path = None
        if fallback_path and fallback_path.is_file():
            try:
                icon = QtGui.QIcon(str(fallback_path))
            except Exception:
                icon = QtGui.QIcon()
        if icon.isNull() and fallback_path is not None:
            png_path = fallback_path.with_suffix(".png")
            if png_path.is_file():
                try:
                    pixmap = QtGui.QPixmap(str(png_path))
                    if not pixmap.isNull():
                        icon = QtGui.QIcon(pixmap)
                except Exception:
                    pass
    if icon.isNull():
        return False
    try:
        app.setWindowIcon(icon)
        QtGui.QGuiApplication.setWindowIcon(icon)
    except Exception:
        pass
    try:
        window.setWindowIcon(icon)
    except Exception:
        pass
    try:
        handle = window.windowHandle()
    except Exception:
        handle = None
    if handle is not None:
        try:
            handle.setIcon(icon)
        except Exception:
            pass
    return True


def _schedule_icon_enforcer(app, window) -> None:  # noqa: ANN001
    if sys.platform != "win32":
        return
    from PyQt6 import QtCore

    force_icon = _env_flag("BOT_FORCE_APP_ICON")
    if not (force_icon or _env_flag("BOT_ENABLE_NATIVE_ICON") or _env_flag("BOT_ENABLE_DELAYED_QT_ICON")):
        return
    try:
        attempts = int(os.environ.get("BOT_ICON_ENFORCE_ATTEMPTS") or 6)
    except Exception:
        attempts = 6
    try:
        interval_ms = int(os.environ.get("BOT_ICON_ENFORCE_INTERVAL_MS") or 500)
    except Exception:
        interval_ms = 500
    attempts = max(1, min(attempts, 20))
    interval_ms = max(100, min(interval_ms, 2000))
    state = {"remaining": attempts}

    def _attempt() -> None:
        if state["remaining"] <= 0:
            return
        state["remaining"] -= 1
        native_ok = False
        qt_ok = False
        if force_icon or _env_flag("BOT_ENABLE_NATIVE_ICON"):
            native_ok = _set_native_window_icon(window)
        if force_icon or _env_flag("BOT_ENABLE_DELAYED_QT_ICON"):
            qt_ok = _apply_qt_icon(app, window)
        if _env_flag("BOT_BOOT_LOG"):
            _boot_log(f"icon enforce attempt native={native_ok} qt={qt_ok}")
        if state["remaining"] > 0:
            QtCore.QTimer.singleShot(interval_ms, _attempt)

    QtCore.QTimer.singleShot(0, _attempt)


class _SplashScreen:
    def __init__(self, app, QtCore, QtGui, QWidget, *, host_widget=None):  # noqa: N803
        self._app = app
        self._QtCore = QtCore
        self._QtGui = QtGui
        self._widget = None
        self._spinner_angle = 0
        self._status_text = "Loading…"
        self._logo_pixmap = None
        self._timer = None
        try:
            self._logo_pixmap = _resolve_splash_logo_pixmap(QtGui)
            if self._logo_pixmap is not None and self._logo_pixmap.isNull():
                self._logo_pixmap = None
        except Exception:
            self._logo_pixmap = None
        try:
            splash_w, splash_h = 420, 320
            splash_topmost = str(os.environ.get("BOT_STARTUP_SPLASH_TOPMOST", "") or "").strip().lower() in {
                "1",
                "true",
                "yes",
                "on",
            }
            if host_widget is not None:
                try:
                    host_rect = host_widget.rect()
                except Exception:
                    host_rect = QtCore.QRect(0, 0, 1920, 1080)
                splash = _SplashWidget(host_widget)
            else:
                screen = QtGui.QGuiApplication.primaryScreen()
                screen_geo = screen.geometry() if screen else QtCore.QRect(0, 0, 1920, 1080)
                splash_flags = (
                    QtCore.Qt.WindowType.SplashScreen
                    | QtCore.Qt.WindowType.FramelessWindowHint
                    | QtCore.Qt.WindowType.NoDropShadowWindowHint
                )
                if splash_topmost:
                    splash_flags |= QtCore.Qt.WindowType.WindowStaysOnTopHint
                splash = _SplashWidget(None, splash_flags)
            splash.setAttribute(QtCore.Qt.WidgetAttribute.WA_ShowWithoutActivating, True)
            splash.setAttribute(QtCore.Qt.WidgetAttribute.WA_TransparentForMouseEvents, True)
            try:
                splash.setWindowTitle("")
            except Exception:
                pass
            splash.setFixedSize(splash_w, splash_h)
            try:
                rounded_path = QtGui.QPainterPath()
                rounded_path.addRoundedRect(QtCore.QRectF(0, 0, splash_w, splash_h), 24, 24)
                splash.setMask(QtGui.QRegion(rounded_path.toFillPolygon().toPolygon()))
            except Exception:
                pass
            if host_widget is not None:
                x = (host_widget.rect().width() - splash_w) // 2
                y = (host_widget.rect().height() - splash_h) // 2
                splash.move(max(0, x), max(0, y))
            else:
                x = screen_geo.x() + (screen_geo.width() - splash_w) // 2
                y = screen_geo.y() + (screen_geo.height() - splash_h) // 2
                splash.move(x, y)
            splash._splash_ref = self
            self._widget = splash
            splash.show()
            try:
                splash.raise_()
            except Exception:
                pass
            app.processEvents(QtCore.QEventLoop.ProcessEventsFlag.AllEvents, 30)
            if sys.platform == "win32" and host_widget is None:
                try:
                    import ctypes
                    import ctypes.wintypes as wintypes
                    user32 = ctypes.windll.user32
                    hwnd = wintypes.HWND(int(splash.winId()))
                    GWL_EXSTYLE = -20
                    WS_EX_LAYERED = 0x00080000
                    WS_EX_TRANSPARENT = 0x00000020
                    get_style = getattr(user32, "GetWindowLongPtrW", None) or user32.GetWindowLongW
                    set_style = getattr(user32, "SetWindowLongPtrW", None) or user32.SetWindowLongW
                    exstyle = int(get_style(hwnd, GWL_EXSTYLE))
                    set_style(hwnd, GWL_EXSTYLE, exstyle | WS_EX_LAYERED | WS_EX_TRANSPARENT)
                except Exception:
                    pass
            timer = QtCore.QTimer()
            timer.setInterval(40)
            timer.timeout.connect(self._tick)
            timer.start()
            self._timer = timer
        except Exception:
            self._widget = None

    def _tick(self) -> None:
        self._spinner_angle = (self._spinner_angle + 8) % 360
        if self._widget is not None:
            try:
                self._widget.update()
            except Exception:
                pass

    def set_status(self, text: str) -> None:
        self._status_text = text
        if self._widget is not None:
            try:
                self._widget.update()
                self._app.processEvents(self._QtCore.QEventLoop.ProcessEventsFlag.AllEvents, 20)
            except Exception:
                pass

    def close(self) -> None:
        if self._timer is not None:
            try:
                self._timer.stop()
            except Exception:
                pass
            self._timer = None
        if self._widget is not None:
            try:
                self._widget.hide()
                self._widget.deleteLater()
            except Exception:
                pass
            self._widget = None


class _SplashWidget:
    pass


def _make_splash_widget_class(QWidget, QtCore, QtGui):  # noqa: N803
    class SplashWidget(QWidget):
        def paintEvent(self, event):  # noqa: N802
            splash_ref = getattr(self, "_splash_ref", None)
            if splash_ref is None:
                return
            try:
                painter = QtGui.QPainter(self)
                painter.setRenderHint(QtGui.QPainter.RenderHint.Antialiasing, True)
                w, h = self.width(), self.height()
                panel_rect = QtCore.QRectF(0, 0, w, h)
                panel_path = QtGui.QPainterPath()
                panel_path.addRoundedRect(panel_rect, 24, 24)
                painter.fillPath(panel_path, QtGui.QColor(16, 20, 27, 235))
                border_pen = QtGui.QPen(QtGui.QColor(255, 255, 255, 22))
                border_pen.setWidthF(1.0)
                painter.setPen(border_pen)
                painter.drawPath(panel_path)
                title = APP_DISPLAY_NAME
                subtitle = splash_ref._status_text or "Loading…"
                y = 34
                if splash_ref._logo_pixmap is not None:
                    logo = splash_ref._logo_pixmap.scaled(84, 84, QtCore.Qt.AspectRatioMode.KeepAspectRatio, QtCore.Qt.TransformationMode.SmoothTransformation)
                    logo_x = (w - logo.width()) // 2
                    painter.drawPixmap(logo_x, y, logo)
                    y += logo.height() + 20
                painter.setPen(QtGui.QColor("#f8fafc"))
                title_font = QtGui.QFont("Segoe UI", 18)
                title_font.setWeight(QtGui.QFont.Weight.DemiBold)
                painter.setFont(title_font)
                painter.drawText(QtCore.QRectF(24, y, w - 48, 32), int(QtCore.Qt.AlignmentFlag.AlignHCenter | QtCore.Qt.AlignmentFlag.AlignVCenter), title)
                y += 40
                painter.setPen(QtGui.QColor("#94a3b8"))
                body_font = QtGui.QFont("Segoe UI", 10)
                painter.setFont(body_font)
                painter.drawText(QtCore.QRectF(24, y, w - 48, 24), int(QtCore.Qt.AlignmentFlag.AlignHCenter | QtCore.Qt.AlignmentFlag.AlignVCenter), subtitle)
                spinner_y = h - 74
                spinner_x = w // 2
                radius = 14
                for i in range(12):
                    alpha = int(25 + (230 * ((i + 1) / 12.0)))
                    color = QtGui.QColor(59, 130, 246, alpha)
                    painter.setPen(QtCore.Qt.PenStyle.NoPen)
                    painter.setBrush(color)
                    angle = math.radians((splash_ref._spinner_angle + i * 30) % 360)
                    dx = math.cos(angle) * radius
                    dy = math.sin(angle) * radius
                    painter.drawEllipse(QtCore.QPointF(spinner_x + dx, spinner_y + dy), 3.0, 3.0)
            except Exception:
                pass

    import math
    return SplashWidget
