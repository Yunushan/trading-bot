from __future__ import annotations

import os
import subprocess
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


def resolve_relaunch_executable(script_path: Path | str | None = None) -> Path | None:
    """Return the preferred Windows GUI host executable for relaunch/shortcuts."""
    if sys.platform != "win32":
        return None
    raw_candidates: list[Path] = []
    for raw_path in (sys.executable, getattr(sys, "_base_executable", None)):
        text = str(raw_path or "").strip()
        if not text:
            continue
        try:
            candidate = Path(text).resolve()
        except Exception:
            candidate = Path(text)
        if candidate not in raw_candidates:
            raw_candidates.append(candidate)
    if not raw_candidates:
        return None
    if getattr(sys, "frozen", False):
        for candidate in raw_candidates:
            if candidate.exists():
                return candidate
        return raw_candidates[0]

    preferred: list[Path] = []
    fallback: list[Path] = []
    for exe in raw_candidates:
        name = str(exe.name or "").strip().lower()
        if name in {"pythonw.exe", "pyw.exe"}:
            preferred.append(exe)
            continue
        gui_candidates: list[Path] = []
        if name == "python.exe":
            gui_candidates.append(exe.with_name("pythonw.exe"))
        elif name == "py.exe":
            gui_candidates.append(exe.with_name("pyw.exe"))
            gui_candidates.append(exe.with_name("pythonw.exe"))
        elif name.startswith("python") and name.endswith(".exe"):
            gui_candidates.append(exe.with_name("pythonw.exe"))
        for candidate in gui_candidates:
            try:
                resolved = candidate.resolve()
            except Exception:
                resolved = candidate
            if resolved not in preferred:
                preferred.append(resolved)
        if exe not in fallback:
            fallback.append(exe)

    for candidate in preferred + fallback:
        if candidate.exists():
            return candidate
    return (preferred + fallback)[0]


def resolve_relaunch_arguments(script_path: Path | str | None = None) -> list[str] | None:
    """Return preferred launch arguments for source and packaged Windows relaunches."""
    if sys.platform != "win32":
        return None
    if script_path is None:
        try:
            script = Path(sys.argv[0]).resolve()
        except Exception:
            script = None
    else:
        script = Path(script_path).resolve()
    if script is None:
        return None
    if not getattr(sys, "frozen", False):
        try:
            if (
                script.name.lower() == "main.py"
                and script.parent.name.lower() == "python"
                and script.parent.parent.name.lower() == "languages"
            ):
                return ["-m", "app.desktop.bootstrap.main"]
        except Exception:
            pass
    return [str(script)]


def build_relaunch_command(script_path: Path | str | None = None) -> str | None:
    """Return a relaunch command string suitable for PKEY_AppUserModel_RelaunchCommand."""
    if sys.platform != "win32":
        return None
    exe = resolve_relaunch_executable(script_path)
    args = resolve_relaunch_arguments(script_path)
    if exe is None or not exe.exists() or not args:
        return None
    try:
        return subprocess.list2cmdline([str(exe), *args])
    except Exception:
        joined_args = " ".join(f'"{arg}"' for arg in args)
        return f'"{exe}" {joined_args}'.strip()


__all__ = [
    "apply_taskbar_metadata",
    "build_relaunch_command",
    "ensure_app_user_model_id",
    "ensure_taskbar_visible",
    "resolve_relaunch_arguments",
    "resolve_relaunch_executable",
]
