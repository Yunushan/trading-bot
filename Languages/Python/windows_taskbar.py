from __future__ import annotations

import os
import sys
from pathlib import Path

_SetWindowAppUserModelID = None

if sys.platform == "win32":
    import ctypes
    from ctypes import wintypes

    _shell32 = ctypes.windll.shell32
    _ole32 = ctypes.windll.ole32

    HRESULT = ctypes.HRESULT
    LPVOID = ctypes.c_void_p
    ULONG = ctypes.c_ulong
    VT_LPWSTR = 31

    class GUID(ctypes.Structure):
        _fields_ = [
            ("Data1", wintypes.DWORD),
            ("Data2", wintypes.WORD),
            ("Data3", wintypes.WORD),
            ("Data4", ctypes.c_ubyte * 8),
        ]

        def __init__(self, d1: int, d2: int, d3: int, *rest: int) -> None:
            super().__init__()
            self.Data1 = d1
            self.Data2 = d2
            self.Data3 = d3
            if len(rest) != 8:
                raise ValueError("GUID requires 8 bytes for Data4")
            self.Data4[:] = rest

    class PROPERTYKEY(ctypes.Structure):
        _fields_ = [
            ("fmtid", GUID),
            ("pid", wintypes.DWORD),
        ]

    class _PROPVARIANT_VALUE(ctypes.Union):
        _fields_ = [
            ("pwszVal", wintypes.LPWSTR),
            ("ulVal", wintypes.ULONG),
            ("boolVal", ctypes.c_short),
        ]

    class PROPVARIANT(ctypes.Structure):
        _anonymous_ = ("value",)
        _fields_ = [
            ("vt", wintypes.USHORT),
            ("wReserved1", wintypes.USHORT),
            ("wReserved2", wintypes.USHORT),
            ("wReserved3", wintypes.USHORT),
            ("value", _PROPVARIANT_VALUE),
        ]

    QueryInterfaceType = ctypes.WINFUNCTYPE(
        HRESULT, ctypes.c_void_p, ctypes.POINTER(GUID), ctypes.POINTER(LPVOID)
    )
    AddRefType = ctypes.WINFUNCTYPE(ULONG, ctypes.c_void_p)
    ReleaseType = ctypes.WINFUNCTYPE(ULONG, ctypes.c_void_p)
    GetCountType = ctypes.WINFUNCTYPE(HRESULT, ctypes.c_void_p, ctypes.POINTER(wintypes.DWORD))
    GetAtType = ctypes.WINFUNCTYPE(HRESULT, ctypes.c_void_p, wintypes.DWORD, ctypes.POINTER(PROPERTYKEY))
    GetValueType = ctypes.WINFUNCTYPE(HRESULT, ctypes.c_void_p, ctypes.POINTER(PROPERTYKEY), ctypes.POINTER(PROPVARIANT))
    SetValueType = ctypes.WINFUNCTYPE(HRESULT, ctypes.c_void_p, ctypes.POINTER(PROPERTYKEY), ctypes.POINTER(PROPVARIANT))
    CommitType = ctypes.WINFUNCTYPE(HRESULT, ctypes.c_void_p)

    class IPropertyStoreVtbl(ctypes.Structure):
        _fields_ = [
            ("QueryInterface", QueryInterfaceType),
            ("AddRef", AddRefType),
            ("Release", ReleaseType),
            ("GetCount", GetCountType),
            ("GetAt", GetAtType),
            ("GetValue", GetValueType),
            ("SetValue", SetValueType),
            ("Commit", CommitType),
        ]

    class IPropertyStore(ctypes.Structure):
        _fields_ = [("lpVtbl", ctypes.POINTER(IPropertyStoreVtbl))]

    IID_IPropertyStore = GUID(
        0x886D8EEB,
        0x8CF2,
        0x4446,
        0x8D,
        0x02,
        0xCD,
        0xBA,
        0x1D,
        0xBD,
        0xCF,
        0x99,
    )

    FMTID_AppUserModel = GUID(
        0x9F4C2855,
        0x9F79,
        0x4B39,
        0xA8,
        0xD0,
        0xE1,
        0xD4,
        0x2D,
        0xE1,
        0xD5,
        0xF3,
    )

    PKEY_RelaunchCommand = PROPERTYKEY(FMTID_AppUserModel, 2)
    PKEY_RelaunchIconResource = PROPERTYKEY(FMTID_AppUserModel, 3)
    PKEY_RelaunchDisplayNameResource = PROPERTYKEY(FMTID_AppUserModel, 4)
    PKEY_AppUserModel_ID = PROPERTYKEY(FMTID_AppUserModel, 5)

    _shell32.SHGetPropertyStoreForWindow.restype = HRESULT
    _shell32.SHGetPropertyStoreForWindow.argtypes = [
        wintypes.HWND,
        ctypes.POINTER(GUID),
        ctypes.POINTER(ctypes.POINTER(IPropertyStore)),
    ]
    _SetWindowAppUserModelID = getattr(_shell32, "SetWindowAppUserModelID", None)
    if _SetWindowAppUserModelID:
        _SetWindowAppUserModelID.restype = HRESULT
        _SetWindowAppUserModelID.argtypes = [wintypes.HWND, ctypes.c_wchar_p]
    else:
        _SetWindowAppUserModelID = None

    _PropVariantClear = _ole32.PropVariantClear
    _PropVariantClear.argtypes = [ctypes.POINTER(PROPVARIANT)]

    _COM_INITIALISED = False


def ensure_app_user_model_id(app_id: str) -> None:
    """Assign a stable AppUserModelID on Windows."""
    if sys.platform != "win32":
        return
    if not app_id:
        return
    try:  # pragma: no cover - Windows only
        ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID(str(app_id))
    except Exception:
        pass


def _co_initialize_once() -> bool:
    if sys.platform != "win32":
        return False
    global _COM_INITIALISED
    if _COM_INITIALISED:
        return True
    try:  # pragma: no cover - Windows only
        hr = int(_ole32.CoInitialize(None))
    except Exception:
        return False
    # S_OK (0) or S_FALSE (1) both signal success.
    # RPC_E_CHANGED_MODE (0x80010106) means COM is already initialised with a different
    # concurrency model (often by Qt); treat it as usable to avoid intermittent failures.
    if hr not in (0, 1) and (hr & 0xFFFFFFFF) != 0x80010106:  # RPC_E_CHANGED_MODE
        return False
    _COM_INITIALISED = True
    return True


def _get_hwnd(window) -> int:
    if sys.platform != "win32" or window is None:
        return 0
    try:
        win_id = None
        if hasattr(window, "effectiveWinId"):
            try:
                win_id = window.effectiveWinId()
            except Exception:
                win_id = None
        if win_id is None and hasattr(window, "winId"):
            try:
                win_id = window.winId()
            except Exception:
                win_id = None
        if win_id is None and hasattr(window, "windowHandle"):
            handle = window.windowHandle()
            if handle is not None:
                try:
                    win_id = handle.winId()
                except Exception:
                    win_id = None
        return int(win_id) if win_id is not None else 0
    except Exception:
        return 0


def _propvariant_from_string(value: str) -> PROPVARIANT:
    buffer = value or ""
    encoded = ctypes.create_unicode_buffer(buffer)
    size = ctypes.sizeof(encoded)
    mem = _ole32.CoTaskMemAlloc(size)
    if not mem:
        raise MemoryError("CoTaskMemAlloc failed")
    ctypes.memmove(mem, ctypes.addressof(encoded), size)
    var = PROPVARIANT()
    var.vt = VT_LPWSTR
    var.value.pwszVal = ctypes.cast(mem, wintypes.LPWSTR)
    return var


def _set_prop_string(store: ctypes.POINTER(IPropertyStore), key: PROPERTYKEY, value: str) -> None:
    if not value:
        return
    prop = _propvariant_from_string(value)
    try:
        set_value = store.contents.lpVtbl.contents.SetValue
        hr = set_value(store, ctypes.byref(key), ctypes.byref(prop))
        if hr != 0:
            raise OSError(f"SetValue failed with HRESULT 0x{hr:08X}")
    finally:
        _PropVariantClear(ctypes.byref(prop))


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
    hwnd = _get_hwnd(window)
    if hwnd == 0:
        return False
    ensure_app_user_model_id(app_id)
    if not _co_initialize_once():
        return False
    if _SetWindowAppUserModelID and app_id:
        try:
            _SetWindowAppUserModelID(wintypes.HWND(hwnd), ctypes.c_wchar_p(app_id))
        except Exception:
            pass
    store_ptr = ctypes.POINTER(IPropertyStore)()
    hr = _shell32.SHGetPropertyStoreForWindow(hwnd, ctypes.byref(IID_IPropertyStore), ctypes.byref(store_ptr))
    if hr != 0 or not store_ptr:
        return False
    store = store_ptr
    try:
        if app_id:
            _set_prop_string(store, PKEY_AppUserModel_ID, app_id)
        if relaunch_command:
            _set_prop_string(store, PKEY_RelaunchCommand, relaunch_command)
        if display_name:
            _set_prop_string(store, PKEY_RelaunchDisplayNameResource, display_name)
        if icon_path:
            icon_str = f"{Path(icon_path).resolve()},0"
            _set_prop_string(store, PKEY_RelaunchIconResource, icon_str)
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
    hwnd = _get_hwnd(window)
    if hwnd == 0:
        return False
    try:  # pragma: no cover - Windows only
        user32 = ctypes.windll.user32
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
