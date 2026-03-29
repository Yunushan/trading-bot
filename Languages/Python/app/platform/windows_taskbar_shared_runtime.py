from __future__ import annotations

import ctypes
import sys
from ctypes import wintypes

_SetWindowAppUserModelID = None
_COM_INITIALISED = False

if sys.platform == "win32":
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
    _shell32.SHGetPropertyStoreFromParsingName.restype = HRESULT
    _shell32.SHGetPropertyStoreFromParsingName.argtypes = [
        wintypes.LPCWSTR,
        ctypes.c_void_p,
        wintypes.DWORD,
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
    _ole32.CoTaskMemAlloc.argtypes = [ctypes.c_size_t]
    _ole32.CoTaskMemAlloc.restype = ctypes.c_void_p

    CLSCTX_INPROC_SERVER = 0x1

    CLSID_ShellLink = GUID(
        0x00021401,
        0x0000,
        0x0000,
        0xC0,
        0x00,
        0x00,
        0x00,
        0x00,
        0x00,
        0x00,
        0x46,
    )
    IID_IShellLinkW = GUID(
        0x000214F9,
        0x0000,
        0x0000,
        0xC0,
        0x00,
        0x00,
        0x00,
        0x00,
        0x00,
        0x00,
        0x46,
    )
    IID_IPersistFile = GUID(
        0x0000010B,
        0x0000,
        0x0000,
        0xC0,
        0x00,
        0x00,
        0x00,
        0x00,
        0x00,
        0x00,
        0x46,
    )

    SetDescriptionType = ctypes.WINFUNCTYPE(HRESULT, ctypes.c_void_p, wintypes.LPCWSTR)
    SetWorkingDirectoryType = ctypes.WINFUNCTYPE(HRESULT, ctypes.c_void_p, wintypes.LPCWSTR)
    SetArgumentsType = ctypes.WINFUNCTYPE(HRESULT, ctypes.c_void_p, wintypes.LPCWSTR)
    SetIconLocationType = ctypes.WINFUNCTYPE(HRESULT, ctypes.c_void_p, wintypes.LPCWSTR, ctypes.c_int)
    SetPathType = ctypes.WINFUNCTYPE(HRESULT, ctypes.c_void_p, wintypes.LPCWSTR)
    SaveFileType = ctypes.WINFUNCTYPE(HRESULT, ctypes.c_void_p, wintypes.LPCWSTR, wintypes.BOOL)

    class IShellLinkWVtbl(ctypes.Structure):
        _fields_ = [
            ("QueryInterface", QueryInterfaceType),
            ("AddRef", AddRefType),
            ("Release", ReleaseType),
            ("GetPath", ctypes.c_void_p),
            ("GetIDList", ctypes.c_void_p),
            ("SetIDList", ctypes.c_void_p),
            ("GetDescription", ctypes.c_void_p),
            ("SetDescription", SetDescriptionType),
            ("GetWorkingDirectory", ctypes.c_void_p),
            ("SetWorkingDirectory", SetWorkingDirectoryType),
            ("GetArguments", ctypes.c_void_p),
            ("SetArguments", SetArgumentsType),
            ("GetHotkey", ctypes.c_void_p),
            ("SetHotkey", ctypes.c_void_p),
            ("GetShowCmd", ctypes.c_void_p),
            ("SetShowCmd", ctypes.c_void_p),
            ("GetIconLocation", ctypes.c_void_p),
            ("SetIconLocation", SetIconLocationType),
            ("SetRelativePath", ctypes.c_void_p),
            ("Resolve", ctypes.c_void_p),
            ("SetPath", SetPathType),
        ]

    class IShellLinkW(ctypes.Structure):
        _fields_ = [("lpVtbl", ctypes.POINTER(IShellLinkWVtbl))]

    class IPersistFileVtbl(ctypes.Structure):
        _fields_ = [
            ("QueryInterface", QueryInterfaceType),
            ("AddRef", AddRefType),
            ("Release", ReleaseType),
            ("GetClassID", ctypes.c_void_p),
            ("IsDirty", ctypes.c_void_p),
            ("Load", ctypes.c_void_p),
            ("Save", SaveFileType),
            ("SaveCompleted", ctypes.c_void_p),
            ("GetCurFile", ctypes.c_void_p),
        ]

    class IPersistFile(ctypes.Structure):
        _fields_ = [("lpVtbl", ctypes.POINTER(IPersistFileVtbl))]

    _ole32.CoCreateInstance.argtypes = [
        ctypes.POINTER(GUID),
        ctypes.c_void_p,
        wintypes.DWORD,
        ctypes.POINTER(GUID),
        ctypes.POINTER(LPVOID),
    ]
    _ole32.CoCreateInstance.restype = HRESULT


def co_initialize_once() -> bool:
    if sys.platform != "win32":
        return False
    global _COM_INITIALISED
    if _COM_INITIALISED:
        return True
    try:  # pragma: no cover - Windows only
        hr = int(_ole32.CoInitialize(None))
    except Exception:
        return False
    if hr not in (0, 1) and (hr & 0xFFFFFFFF) != 0x80010106:
        return False
    _COM_INITIALISED = True
    return True


def get_hwnd(window) -> int:
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


def propvariant_from_string(value: str):
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


def set_prop_string(store, key, value: str) -> None:
    if not value:
        return
    prop = propvariant_from_string(value)
    try:
        set_value = store.contents.lpVtbl.contents.SetValue
        hr = set_value(store, ctypes.byref(key), ctypes.byref(prop))
        if hr != 0:
            raise OSError(f"SetValue failed with HRESULT 0x{hr:08X}")
    finally:
        _PropVariantClear(ctypes.byref(prop))


__all__ = [
    "ctypes",
    "wintypes",
    "co_initialize_once",
    "get_hwnd",
    "set_prop_string",
]
