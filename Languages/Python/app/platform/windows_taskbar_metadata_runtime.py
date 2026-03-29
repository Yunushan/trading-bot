from __future__ import annotations

import os
import sys
from pathlib import Path

from . import windows_taskbar_shared_runtime as shared


def ensure_app_user_model_id(app_id: str) -> None:
    """Assign a stable AppUserModelID on Windows."""
    if sys.platform != "win32" or not app_id:
        return
    try:  # pragma: no cover - Windows only
        shared.ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID(str(app_id))
    except Exception:
        pass


def apply_taskbar_metadata(
    window,
    *,
    app_id: str,
    display_name: str | None = None,
    icon_path: str | os.PathLike[str] | None = None,
    relaunch_command: str | None = None,
) -> bool:
    """Assign relaunch metadata so the Windows taskbar shows the correct label and icon."""
    if sys.platform != "win32":
        return False
    hwnd = shared.get_hwnd(window)
    if hwnd == 0:
        return False
    ensure_app_user_model_id(app_id)
    if not shared.co_initialize_once():
        return False
    if shared._SetWindowAppUserModelID and app_id:
        try:
            shared._SetWindowAppUserModelID(shared.wintypes.HWND(hwnd), shared.ctypes.c_wchar_p(app_id))
        except Exception:
            pass
    store_ptr = shared.ctypes.POINTER(shared.IPropertyStore)()
    hr = shared._shell32.SHGetPropertyStoreForWindow(
        hwnd,
        shared.ctypes.byref(shared.IID_IPropertyStore),
        shared.ctypes.byref(store_ptr),
    )
    if hr != 0 or not store_ptr:
        return False
    store = store_ptr
    try:
        if app_id:
            shared.set_prop_string(store, shared.PKEY_AppUserModel_ID, app_id)
        if relaunch_command:
            shared.set_prop_string(store, shared.PKEY_RelaunchCommand, relaunch_command)
        if display_name:
            shared.set_prop_string(store, shared.PKEY_RelaunchDisplayNameResource, display_name)
        if icon_path:
            icon_str = f"{Path(icon_path).resolve()},0"
            shared.set_prop_string(store, shared.PKEY_RelaunchIconResource, icon_str)
        commit = store.contents.lpVtbl.contents.Commit
        commit(store)
    except Exception:
        pass
    finally:
        release = store.contents.lpVtbl.contents.Release
        release(store)
    return True


def ensure_taskbar_visible(window) -> bool:
    """Force a window to show in the Windows taskbar (clears WS_EX_TOOLWINDOW)."""
    if sys.platform != "win32":
        return False
    hwnd = shared.get_hwnd(window)
    if hwnd == 0:
        return False
    try:  # pragma: no cover - Windows only
        user32 = shared.ctypes.windll.user32
        GWL_EXSTYLE = -20
        WS_EX_TOOLWINDOW = 0x00000080
        WS_EX_APPWINDOW = 0x00040000
        get_exstyle = getattr(user32, "GetWindowLongPtrW", None) or user32.GetWindowLongW
        set_exstyle = getattr(user32, "SetWindowLongPtrW", None) or user32.SetWindowLongW
        ex_style = int(get_exstyle(hwnd, GWL_EXSTYLE))
        new_ex_style = int((ex_style | WS_EX_APPWINDOW) & ~WS_EX_TOOLWINDOW)
        if new_ex_style != ex_style:
            set_exstyle(hwnd, GWL_EXSTYLE, new_ex_style)
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
        try:
            if not user32.IsWindowVisible(hwnd):
                SW_SHOWNOACTIVATE = 4
                if getattr(user32, "ShowWindowAsync", None):
                    user32.ShowWindowAsync(hwnd, SW_SHOWNOACTIVATE)
                else:
                    user32.ShowWindow(hwnd, SW_SHOWNOACTIVATE)
        except Exception:
            pass
    except Exception:
        return False
    return True


def build_relaunch_command(script_path: Path | str | None = None) -> str | None:
    """Return a relaunch command string suitable for PKEY_AppUserModel_RelaunchCommand."""
    if sys.platform != "win32":
        return None
    exe = Path(sys.executable).resolve()
    if script_path is None:
        try:
            script = Path(sys.argv[0]).resolve()
        except Exception:
            script = None
    else:
        script = Path(script_path).resolve()
    if not exe.exists() or script is None:
        return None
    return f'"{exe}" "{script}"'


__all__ = [
    "apply_taskbar_metadata",
    "build_relaunch_command",
    "ensure_app_user_model_id",
    "ensure_taskbar_visible",
]
