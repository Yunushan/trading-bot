from __future__ import annotations

import os
import sys
from pathlib import Path

from . import windows_taskbar_shared_runtime as shared


def ensure_start_menu_shortcut(
    *,
    app_id: str,
    display_name: str,
    shortcut_name: str | None = None,
    target_path: str | Path,
    arguments: str | None = None,
    icon_path: str | Path | None = None,
    working_dir: str | Path | None = None,
    relaunch_command: str | None = None,
) -> Path | None:
    """Create/update a Start Menu shortcut so Windows can resolve app name + icon."""
    if sys.platform != "win32":
        return None
    name = str(display_name or "").strip() or "Trading Bot"
    appdata = os.environ.get("APPDATA")
    if not appdata:
        return None
    start_menu = Path(appdata) / "Microsoft" / "Windows" / "Start Menu" / "Programs"
    try:
        start_menu.mkdir(parents=True, exist_ok=True)
    except Exception:
        return None
    shortcut_file_name = str(shortcut_name or name).strip() or name
    shortcut_path = start_menu / f"{shortcut_file_name}.lnk"
    if not shared.co_initialize_once():
        return None
    relaunch_cmd = relaunch_command or None
    link_ptr = shared.ctypes.c_void_p()
    hr = shared._ole32.CoCreateInstance(
        shared.ctypes.byref(shared.CLSID_ShellLink),
        None,
        shared.CLSCTX_INPROC_SERVER,
        shared.ctypes.byref(shared.IID_IShellLinkW),
        shared.ctypes.byref(link_ptr),
    )
    if hr != 0 or not link_ptr:
        return None
    shell_link = shared.ctypes.cast(link_ptr, shared.ctypes.POINTER(shared.IShellLinkW))
    try:
        set_path = shell_link.contents.lpVtbl.contents.SetPath
        set_path(shell_link, str(Path(target_path).resolve()))
        if arguments:
            shell_link.contents.lpVtbl.contents.SetArguments(shell_link, str(arguments))
        if working_dir:
            shell_link.contents.lpVtbl.contents.SetWorkingDirectory(shell_link, str(Path(working_dir).resolve()))
        if icon_path:
            shell_link.contents.lpVtbl.contents.SetIconLocation(
                shell_link,
                str(Path(icon_path).resolve()),
                0,
            )
        shell_link.contents.lpVtbl.contents.SetDescription(shell_link, name)

        store_ptr = shared.ctypes.c_void_p()
        hr_store = shell_link.contents.lpVtbl.contents.QueryInterface(
            shell_link,
            shared.ctypes.byref(shared.IID_IPropertyStore),
            shared.ctypes.byref(store_ptr),
        )
        if hr_store == 0 and store_ptr:
            store = shared.ctypes.cast(store_ptr, shared.ctypes.POINTER(shared.IPropertyStore))
            try:
                if app_id:
                    shared.set_prop_string(store, shared.PKEY_AppUserModel_ID, app_id)
                if name:
                    shared.set_prop_string(store, shared.PKEY_RelaunchDisplayNameResource, name)
                if icon_path:
                    icon_str = f"{Path(icon_path).resolve()},0"
                    shared.set_prop_string(store, shared.PKEY_RelaunchIconResource, icon_str)
                if relaunch_cmd:
                    shared.set_prop_string(store, shared.PKEY_RelaunchCommand, relaunch_cmd)
                commit = store.contents.lpVtbl.contents.Commit
                commit(store)
            except Exception:
                pass
            finally:
                release = store.contents.lpVtbl.contents.Release
                release(store)

        persist_ptr = shared.ctypes.c_void_p()
        hr_persist = shell_link.contents.lpVtbl.contents.QueryInterface(
            shell_link,
            shared.ctypes.byref(shared.IID_IPersistFile),
            shared.ctypes.byref(persist_ptr),
        )
        if hr_persist == 0 and persist_ptr:
            persist = shared.ctypes.cast(persist_ptr, shared.ctypes.POINTER(shared.IPersistFile))
            try:
                persist.contents.lpVtbl.contents.Save(persist, str(shortcut_path), True)
            finally:
                persist.contents.lpVtbl.contents.Release(persist)
    finally:
        shell_link.contents.lpVtbl.contents.Release(shell_link)
    try:
        _apply_shortcut_property_store(
            shortcut_path,
            app_id=app_id,
            display_name=name,
            icon_path=icon_path,
            relaunch_command=relaunch_cmd,
        )
    except Exception:
        pass
    return shortcut_path


def _apply_shortcut_property_store(
    shortcut_path: Path | str,
    *,
    app_id: str,
    display_name: str | None,
    icon_path: str | Path | None,
    relaunch_command: str | None = None,
) -> bool:
    if sys.platform != "win32":
        return False
    if not shared.co_initialize_once():
        return False
    link_path = Path(shortcut_path).resolve()
    if not link_path.exists():
        return False
    store_ptr = shared.ctypes.POINTER(shared.IPropertyStore)()
    hr = shared._shell32.SHGetPropertyStoreFromParsingName(
        str(link_path),
        None,
        0x00000002,
        shared.ctypes.byref(shared.IID_IPropertyStore),
        shared.ctypes.byref(store_ptr),
    )
    if hr != 0 or not store_ptr:
        return False
    store = store_ptr
    try:
        if app_id:
            shared.set_prop_string(store, shared.PKEY_AppUserModel_ID, app_id)
        if display_name:
            shared.set_prop_string(store, shared.PKEY_RelaunchDisplayNameResource, display_name)
        if icon_path:
            icon_str = f"{Path(icon_path).resolve()},0"
            shared.set_prop_string(store, shared.PKEY_RelaunchIconResource, icon_str)
        if relaunch_command:
            shared.set_prop_string(store, shared.PKEY_RelaunchCommand, relaunch_command)
        commit = store.contents.lpVtbl.contents.Commit
        commit(store)
    except Exception:
        return False
    finally:
        release = store.contents.lpVtbl.contents.Release
        release(store)
    return True


__all__ = ["_apply_shortcut_property_store", "ensure_start_menu_shortcut"]
