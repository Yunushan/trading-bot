from __future__ import annotations

import os
import shutil
import subprocess
import sys
from pathlib import Path

from .startup_ui_shared import _PROJECT_ROOT, _boot_log, _env_flag, _native_icon_handles


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
    source_launcher_exe = _PROJECT_ROOT / "Trading-Bot-Python.exe"
    if not getattr(sys, "frozen", False) and source_launcher_exe.is_file():
        return source_launcher_exe
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
    if getattr(sys, "frozen", False):
        try:
            exe_icon = Path(sys.executable).resolve()
        except Exception:
            exe_icon = None
        if exe_icon is not None and exe_icon.is_file():
            return exe_icon
    repo_icon = _PROJECT_ROOT / "assets" / "crypto_forex_logo.ico"
    return repo_icon if repo_icon.is_file() else None


def _format_shortcut_args(script_path: Path) -> str:
    try:
        from app.platform.windows_taskbar_metadata_runtime import resolve_relaunch_arguments

        args = resolve_relaunch_arguments(script_path)
    except Exception:
        args = None
    if args:
        try:
            return subprocess.list2cmdline(args)
        except Exception:
            return " ".join(f"\"{arg}\"" for arg in args)
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
