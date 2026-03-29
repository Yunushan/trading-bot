from __future__ import annotations

_QT_INTERNAL_WINDOW_SUFFIXES = (
    "PowerDummyWindow",
    "ClipboardView",
    "ScreenChangeObserverWindow",
    "ThemeChangeObserverWindow",
    "QWindowToolSaveBits",
)


def _read_cs_string(api, value) -> str:  # noqa: ANN001
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
            addr = int(api.ctypes.cast(value, api.ctypes.c_void_p).value or 0)
        except Exception:
            addr = 0
    if not addr:
        return ""
    if addr < 0x10000:
        return ""
    try:
        return str(api.ctypes.wstring_at(addr) or "").strip()
    except Exception:
        return ""


def _read_hwnd_class(api, hwnd_val: int) -> str:
    try:
        buf = api.ctypes.create_unicode_buffer(256)
        api.user32.GetClassNameW(api.wintypes.HWND(int(hwnd_val)), buf, 256)
        return str(buf.value or "").strip()
    except Exception:
        return ""


def _read_hwnd_title(api, hwnd_val: int) -> str:
    try:
        buf = api.ctypes.create_unicode_buffer(256)
        api.user32.GetWindowTextW(api.wintypes.HWND(int(hwnd_val)), buf, 256)
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
