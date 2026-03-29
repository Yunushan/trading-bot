from __future__ import annotations


def _get_hwnd_pid(api, hwnd_obj) -> int:  # noqa: ANN001
    try:
        out_pid = api.wintypes.DWORD()
        api.user32.GetWindowThreadProcessId(hwnd_obj, api.ctypes.byref(out_pid))
        return int(out_pid.value)
    except Exception:
        return 0


def _log_window(api, hwnd_obj, reason: str) -> None:  # noqa: ANN001
    if not api.debug_window_events:
        return
    try:
        class_buf = api.ctypes.create_unicode_buffer(256)
        api.user32.GetClassNameW(hwnd_obj, class_buf, 256)
        try:
            vis = int(bool(api.user32.IsWindowVisible(hwnd_obj)))
        except Exception:
            vis = 0
        try:
            get_style = getattr(api.user32, "GetWindowLongPtrW", None) or api.user32.GetWindowLongW
            style_val = int(get_style(hwnd_obj, -16))
        except Exception:
            style_val = 0
        try:
            get_exstyle = getattr(api.user32, "GetWindowLongPtrW", None) or api.user32.GetWindowLongW
            exstyle_val = int(get_exstyle(hwnd_obj, -20))
        except Exception:
            exstyle_val = 0
        rect = api.wintypes.RECT()
        api.user32.GetWindowRect(hwnd_obj, api.ctypes.byref(rect))
        width = int(rect.right - rect.left)
        height = int(rect.bottom - rect.top)
        pid_val = _get_hwnd_pid(api, hwnd_obj)
        with open(api.debug_log_path, "a", encoding="utf-8", errors="ignore") as fh:
            fh.write(
                f"{reason} hwnd={int(hwnd_obj)} pid={pid_val} "
                f"class={class_buf.value!r} size={width}x{height} "
                f"vis={vis} style=0x{style_val:08X} exstyle=0x{exstyle_val:08X}\n"
            )
    except Exception:
        return


def _is_transient_startup_window(api, hwnd_obj) -> bool:  # noqa: ANN001
    try:
        rect = api.wintypes.RECT()
        if not api.user32.GetWindowRect(hwnd_obj, api.ctypes.byref(rect)):
            return False
        width = int(rect.right - rect.left)
        height = int(rect.bottom - rect.top)
        if width <= 0 or height <= 0:
            return False

        class_buf = api.ctypes.create_unicode_buffer(256)
        api.user32.GetClassNameW(hwnd_obj, class_buf, 256)
        class_name = (class_buf.value or "").strip()
        title_buf = api.ctypes.create_unicode_buffer(256)
        api.user32.GetWindowTextW(hwnd_obj, title_buf, 256)
        title = (title_buf.value or "").strip()

        try:
            GWL_STYLE = -16
            WS_CHILD = 0x40000000
            get_style = getattr(api.user32, "GetWindowLongPtrW", None) or api.user32.GetWindowLongW
            style = int(get_style(hwnd_obj, GWL_STYLE))
            if style & WS_CHILD:
                return False
        except Exception:
            pass

        if class_name.startswith("Qt") and any(
            class_name.endswith(suffix)
            for suffix in (
                "PowerDummyWindow",
                "ClipboardView",
                "ScreenChangeObserverWindow",
                "ThemeChangeObserverWindow",
            )
        ):
            return True
        if class_name.startswith("QEventDispatcherWin32_"):
            return True
        if title.startswith("QEventDispatcherWin32_"):
            return True
        if class_name in {"ConsoleWindowClass", "PseudoConsoleWindow"}:
            return True
        if class_name.startswith("_q_"):
            return height <= 260 and width <= 3200
        if title.startswith("_q_"):
            return height <= 260 and width <= 3200
        if class_name == "Intermediate D3D Window":
            return height <= 500 and width <= 4000
        if class_name.startswith("Chrome_WidgetWin_"):
            return height <= 400 and width <= 4000
        if title.startswith("Qt") and any(
            title.endswith(suffix)
            for suffix in (
                "PowerDummyWindow",
                "ClipboardView",
                "ScreenChangeObserverWindow",
                "ThemeChangeObserverWindow",
            )
        ):
            return True
        if width >= 500 and height >= 300:
            return False

        return height <= 800 and width <= 4000
    except Exception:
        return False


def _hide_hwnd(api, hwnd_obj) -> None:  # noqa: ANN001
    try:
        SWP_NOSIZE = 0x0001
        SWP_NOZORDER = 0x0004
        SWP_NOACTIVATE = 0x0010
        SWP_HIDEWINDOW = 0x0080
        SWP_ASYNCWINDOWPOS = 0x4000
        api.user32.SetWindowPos(
            hwnd_obj,
            0,
            -32000,
            -32000,
            0,
            0,
            SWP_NOSIZE | SWP_NOZORDER | SWP_NOACTIVATE | SWP_HIDEWINDOW | SWP_ASYNCWINDOWPOS,
        )
    except Exception:
        pass
    try:
        if getattr(api.user32, "ShowWindowAsync", None):
            api.user32.ShowWindowAsync(hwnd_obj, api.SW_HIDE)
        else:
            api.user32.ShowWindow(hwnd_obj, api.SW_HIDE)
    except Exception:
        pass
