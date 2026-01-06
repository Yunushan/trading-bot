import os
import sys
import time
from pathlib import Path

# Ensure repo root is importable so shared helpers can be used when launched directly.
PROJECT_ROOT = Path(__file__).resolve().parents[4]
PROJECT_ROOT_STR = str(PROJECT_ROOT)
if PROJECT_ROOT_STR not in sys.path:
    sys.path.insert(0, PROJECT_ROOT_STR)

BINANCE_DIR = Path(__file__).resolve().parent
BINANCE_DIR_STR = str(BINANCE_DIR)
if BINANCE_DIR_STR not in sys.path:
    sys.path.insert(0, BINANCE_DIR_STR)


def _env_flag(name: str) -> bool:
    return str(os.environ.get(name, "")).strip().lower() in {"1", "true", "yes", "on"}


def _suppress_subprocess_console_windows() -> None:
    """Hide transient console windows from subprocess calls on Windows."""
    if sys.platform != "win32" or _env_flag("BOT_ALLOW_SUBPROCESS_CONSOLE"):
        return
    try:
        import subprocess
    except Exception:
        return
    if getattr(subprocess, "_bot_no_console_patch", False):
        return
    try:
        create_no_window = getattr(subprocess, "CREATE_NO_WINDOW", 0x08000000)
        startf_use_show = getattr(subprocess, "STARTF_USESHOWWINDOW", 0x00000001)
        sw_hide = 0
        original_popen = subprocess.Popen
        original_run = subprocess.run

        if isinstance(original_popen, type):
            class _NoConsolePopen(original_popen):  # type: ignore[misc, valid-type]
                def __init__(self, *args, **kwargs):
                    if "creationflags" not in kwargs:
                        kwargs["creationflags"] = create_no_window
                    if "startupinfo" not in kwargs:
                        si = subprocess.STARTUPINFO()
                        si.dwFlags |= startf_use_show
                        si.wShowWindow = sw_hide
                        kwargs["startupinfo"] = si
                    super().__init__(*args, **kwargs)

            subprocess.Popen = _NoConsolePopen  # type: ignore[assignment]
        else:
            def _patched_popen(*args, **kwargs):
                if "creationflags" not in kwargs:
                    kwargs["creationflags"] = create_no_window
                if "startupinfo" not in kwargs:
                    si = subprocess.STARTUPINFO()
                    si.dwFlags |= startf_use_show
                    si.wShowWindow = sw_hide
                    kwargs["startupinfo"] = si
                return original_popen(*args, **kwargs)

            subprocess.Popen = _patched_popen  # type: ignore[assignment]

        def _patched_run(*args, **kwargs):
            if "creationflags" not in kwargs:
                kwargs["creationflags"] = create_no_window
            if "startupinfo" not in kwargs:
                si = subprocess.STARTUPINFO()
                si.dwFlags |= startf_use_show
                si.wShowWindow = sw_hide
                kwargs["startupinfo"] = si
            return original_run(*args, **kwargs)

        subprocess.run = _patched_run  # type: ignore[assignment]
        subprocess._bot_no_console_patch = True  # type: ignore[attr-defined]
    except Exception:
        return


# Windows: optionally force software rendering (can reduce GPU probe/helper windows, but may be slower).
if sys.platform == "win32" and _env_flag("BOT_FORCE_SOFTWARE_OPENGL"):
    os.environ.setdefault("QT_OPENGL", "software")
    os.environ.setdefault("QSG_RHI_BACKEND", "software")
    os.environ.setdefault("QT_QUICK_BACKEND", "software")

_suppress_subprocess_console_windows()


# --- Windows startup transient window suppression --------------------------------
# Qt can briefly create tiny helper windows during startup (notably `_q_titlebar`).
# If they show even briefly, it looks like rapid flickering.
_STARTUP_WINDOW_HOOK = None
_STARTUP_WINDOW_PROC = None
_STARTUP_WINDOW_POLL_STOP = None
_STARTUP_WINDOW_POLL_THREAD = None
_CBT_STARTUP_WINDOW_HOOKS: dict[int, int] = {}
_CBT_STARTUP_WINDOW_PROC = None
_CBT_STARTUP_WINDOW_SCAN_STOP = None
_CBT_STARTUP_WINDOW_SCAN_THREAD = None
_CBT_STARTUP_WINDOW_LOCK = None


def _install_cbt_startup_window_suppression() -> None:
    """Best-effort: clear WS_VISIBLE at create-time for tiny helper windows (Windows only)."""
    global _CBT_STARTUP_WINDOW_PROC, _CBT_STARTUP_WINDOW_SCAN_STOP, _CBT_STARTUP_WINDOW_SCAN_THREAD, _CBT_STARTUP_WINDOW_LOCK
    if sys.platform != "win32" or _CBT_STARTUP_WINDOW_PROC is not None:
        return
    # Disabled by default because CBT hooks can be fragile with complex Qt startups.
    # Use BOT_ENABLE_CBT_STARTUP_WINDOW_SUPPRESS=1 to opt in.
    if not _env_flag("BOT_ENABLE_CBT_STARTUP_WINDOW_SUPPRESS"):
        return
    if _env_flag("BOT_NO_STARTUP_WINDOW_SUPPRESS") or _env_flag("BOT_NO_CBT_STARTUP_WINDOW_SUPPRESS"):
        return

    try:  # pragma: no cover - Windows only
        import ctypes
        import ctypes.wintypes as wintypes
        import threading
        import time
    except Exception:
        return

    user32 = ctypes.windll.user32
    kernel32 = ctypes.windll.kernel32

    debug_window_events = _env_flag("BOT_DEBUG_WINDOW_EVENTS")
    debug_log_path = Path(os.getenv("TEMP") or ".").resolve() / "gate_window_events.log"

    WH_CBT = 5
    HCBT_CREATEWND = 3
    WS_CHILD = 0x40000000
    WS_VISIBLE = 0x10000000
    WS_EX_TOOLWINDOW = 0x00000080
    WS_EX_APPWINDOW = 0x00040000
    WS_EX_NOACTIVATE = 0x08000000

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
    except Exception:
        pass

    _QT_INTERNAL_WINDOW_SUFFIXES = (
        "PowerDummyWindow",
        "ClipboardView",
        "ScreenChangeObserverWindow",
        "ThemeChangeObserverWindow",
    )

    def _read_cs_string(value) -> str:  # noqa: ANN001
        if value is None:
            return ""
        if isinstance(value, str):
            text = (value or "").strip()
            # Sometimes lpszClass/lpszName is an atom and ctypes can expose it as a single
            # control character; treat that as "no usable string".
            if len(text) == 1 and ord(text) < 32:
                return ""
            return text
        addr = None
        if isinstance(value, int):
            addr = int(value)
        else:
            try:
                addr = int(ctypes.cast(value, ctypes.c_void_p).value or 0)
            except Exception:
                addr = 0
        if not addr:
            return ""
        # MAKEINTATOM uses values < 0x10000.
        if addr < 0x10000:
            return ""
        try:
            return str(ctypes.wstring_at(addr) or "").strip()
        except Exception:
            return ""

    def _read_hwnd_class(hwnd_val: int) -> str:
        try:
            buf = ctypes.create_unicode_buffer(256)
            user32.GetClassNameW(wintypes.HWND(int(hwnd_val)), buf, 256)
            return str(buf.value or "").strip()
        except Exception:
            return ""

    def _looks_like_qt_internal_helper_window(*, class_name: str, title: str) -> bool:
        name = str(class_name or "").strip()
        if name.startswith("Qt") and any(name.endswith(suffix) for suffix in _QT_INTERNAL_WINDOW_SUFFIXES):
            return True
        ttl = str(title or "").strip()
        # Titles often omit the version digits (e.g., "QtPowerDummyWindow").
        if ttl.startswith("Qt") and any(ttl.endswith(suffix) for suffix in _QT_INTERNAL_WINDOW_SUFFIXES):
            return True
        return False

    def _cbt_proc(n_code, w_param, l_param):  # noqa: ANN001
        try:
            if int(n_code) != HCBT_CREATEWND:
                return user32.CallNextHookEx(0, n_code, w_param, l_param)
            hwnd_val = int(w_param)
            if not hwnd_val:
                return user32.CallNextHookEx(0, n_code, w_param, l_param)
            lp_val = int(l_param)
            if not lp_val or lp_val < 0x10000:
                return user32.CallNextHookEx(0, n_code, w_param, l_param)
            cbt = ctypes.cast(lp_val, ctypes.POINTER(CBT_CREATEWND)).contents
            if not cbt.lpcs:
                return user32.CallNextHookEx(0, n_code, w_param, l_param)
            cs = cbt.lpcs.contents
            width = int(cs.cx)
            height = int(cs.cy)
            if width <= 0 or height <= 0:
                return user32.CallNextHookEx(0, n_code, w_param, l_param)
            cs_class = _read_cs_string(cs.lpszClass)
            cs_title = _read_cs_string(cs.lpszName)
            style = int(cs.style) & 0xFFFFFFFF
            if style & WS_CHILD:
                return user32.CallNextHookEx(0, n_code, w_param, l_param)
            # Some Qt 6.10+ internal helper windows can appear full-size briefly on Windows 11.
            # Hide them at create-time to avoid visible flashes before the main UI shows.
            class_name = cs_class or _read_hwnd_class(hwnd_val)
            if class_name.startswith("QEventDispatcherWin32_Internal_Widget"):
                return user32.CallNextHookEx(0, n_code, w_param, l_param)
            if _looks_like_qt_internal_helper_window(class_name=class_name, title=cs_title):
                cs.style = int(style & ~WS_VISIBLE)
                ex_style = int(cs.dwExStyle) & 0xFFFFFFFF
                cs.dwExStyle = int((ex_style | WS_EX_TOOLWINDOW | WS_EX_NOACTIVATE) & ~WS_EX_APPWINDOW)
                cs.x = -32000
                cs.y = -32000
                if debug_window_events:
                    try:
                        with open(debug_log_path, "a", encoding="utf-8", errors="ignore") as fh:
                            fh.write(
                                f"cbt-hide-qt-helper hwnd={hwnd_val} size={width}x{height} class={class_name!r} title={cs_title!r} "
                                f"style=0x{style:08X} exstyle=0x{ex_style:08X}\n"
                            )
                    except Exception:
                        pass
                return user32.CallNextHookEx(0, n_code, w_param, l_param)
            # Never touch anything that looks like the actual app window.
            if width >= 500 and height >= 300:
                return user32.CallNextHookEx(0, n_code, w_param, l_param)
            # Target only tiny top-level helpers that can flash (titlebar-sized).
            if height <= 120 and width <= 4000:
                cs.style = int(style & ~WS_VISIBLE)
                ex_style = int(cs.dwExStyle) & 0xFFFFFFFF
                cs.dwExStyle = int((ex_style | WS_EX_TOOLWINDOW | WS_EX_NOACTIVATE) & ~WS_EX_APPWINDOW)
                cs.x = -32000
                cs.y = -32000
                if debug_window_events:
                    try:
                        with open(debug_log_path, "a", encoding="utf-8", errors="ignore") as fh:
                            fh.write(
                                f"cbt-hide hwnd={hwnd_val} size={width}x{height} class={class_name!r} title={cs_title!r} "
                                f"style=0x{style:08X} exstyle=0x{ex_style:08X}\n"
                            )
                    except Exception:
                        pass
        except Exception:
            pass
        return user32.CallNextHookEx(0, n_code, w_param, l_param)

    _CBT_STARTUP_WINDOW_PROC = CBTProc(_cbt_proc)

    if _CBT_STARTUP_WINDOW_LOCK is None:
        _CBT_STARTUP_WINDOW_LOCK = threading.Lock()

    try:
        user32.PostThreadMessageW.argtypes = [wintypes.DWORD, wintypes.UINT, wintypes.WPARAM, wintypes.LPARAM]
        user32.PostThreadMessageW.restype = wintypes.BOOL
    except Exception:
        pass

    def _thread_has_message_queue(thread_id: int) -> bool:
        if not thread_id:
            return False
        try:
            # WM_NULL = 0. Fails if the target thread has no message queue.
            return bool(user32.PostThreadMessageW(int(thread_id), 0, 0, 0))
        except Exception:
            return False

    def _install_hook_for_thread(thread_id: int) -> None:
        if not thread_id:
            return
        if _CBT_STARTUP_WINDOW_PROC is None or _CBT_STARTUP_WINDOW_LOCK is None:
            return
        with _CBT_STARTUP_WINDOW_LOCK:
            if thread_id in _CBT_STARTUP_WINDOW_HOOKS:
                return
            hook = user32.SetWindowsHookExW(WH_CBT, _CBT_STARTUP_WINDOW_PROC, 0, int(thread_id))
            if hook:
                _CBT_STARTUP_WINDOW_HOOKS[int(thread_id)] = int(hook)
            if debug_window_events:
                try:
                    with open(debug_log_path, "a", encoding="utf-8", errors="ignore") as fh:
                        fh.write(f"cbt-hook-install tid={int(thread_id)} hook={int(hook) if hook else 0}\n")
                except Exception:
                    pass

    # Ensure the current thread has a message queue, then install the hook immediately.
    try:
        msg = wintypes.MSG()
        user32.PeekMessageW(ctypes.byref(msg), 0, 0, 0, 0)
    except Exception:
        pass
    try:
        current_tid = int(kernel32.GetCurrentThreadId())
    except Exception:
        current_tid = 0
    _install_hook_for_thread(current_tid)

    def _enumerate_thread_ids(pid: int) -> set[int]:
        thread_ids: set[int] = set()
        if not pid:
            return thread_ids
        try:
            TH32CS_SNAPTHREAD = 0x00000004
            snapshot = kernel32.CreateToolhelp32Snapshot(TH32CS_SNAPTHREAD, 0)
            if snapshot in (0, ctypes.c_void_p(-1).value):
                return thread_ids

            class THREADENTRY32(ctypes.Structure):
                _fields_ = [
                    ("dwSize", wintypes.DWORD),
                    ("cntUsage", wintypes.DWORD),
                    ("th32ThreadID", wintypes.DWORD),
                    ("th32OwnerProcessID", wintypes.DWORD),
                    ("tpBasePri", wintypes.LONG),
                    ("tpDeltaPri", wintypes.LONG),
                    ("dwFlags", wintypes.DWORD),
                ]

            entry = THREADENTRY32()
            entry.dwSize = ctypes.sizeof(entry)
            try:
                if not kernel32.Thread32First(snapshot, ctypes.byref(entry)):
                    return thread_ids
                while True:
                    if int(entry.th32OwnerProcessID) == int(pid):
                        thread_ids.add(int(entry.th32ThreadID))
                    if not kernel32.Thread32Next(snapshot, ctypes.byref(entry)):
                        break
            finally:
                try:
                    kernel32.CloseHandle(snapshot)
                except Exception:
                    pass
        except Exception:
            return thread_ids
        return thread_ids

    try:
        scan_ms = int(os.environ.get("BOT_CBT_THREAD_HOOK_SCAN_MS") or 1500)
    except Exception:
        scan_ms = 1500
    scan_ms = max(200, min(8000, scan_ms))
    try:
        interval_ms = int(os.environ.get("BOT_CBT_THREAD_HOOK_SCAN_INTERVAL_MS") or 50)
    except Exception:
        interval_ms = 50
    interval_ms = max(20, min(250, interval_ms))

    try:
        pid_val = int(kernel32.GetCurrentProcessId())
    except Exception:
        pid_val = 0

    stop_event = threading.Event()
    _CBT_STARTUP_WINDOW_SCAN_STOP = stop_event

    def _scan_loop() -> None:
        deadline = time.monotonic() + (scan_ms / 1000.0)
        while time.monotonic() < deadline and not stop_event.is_set():
            for tid in _enumerate_thread_ids(pid_val):
                _install_hook_for_thread(tid)
            time.sleep(interval_ms / 1000.0)

    thread = threading.Thread(target=_scan_loop, name="cbt-hook-scan", daemon=True)
    _CBT_STARTUP_WINDOW_SCAN_THREAD = thread
    thread.start()


def _uninstall_cbt_startup_window_suppression() -> None:
    global _CBT_STARTUP_WINDOW_PROC, _CBT_STARTUP_WINDOW_SCAN_STOP, _CBT_STARTUP_WINDOW_SCAN_THREAD, _CBT_STARTUP_WINDOW_LOCK
    if sys.platform != "win32" or _CBT_STARTUP_WINDOW_PROC is None:
        return
    try:
        stop_event = _CBT_STARTUP_WINDOW_SCAN_STOP
        if stop_event is not None:
            stop_event.set()
    except Exception:
        pass
    try:
        thread = _CBT_STARTUP_WINDOW_SCAN_THREAD
        if thread is not None and getattr(thread, "is_alive", lambda: False)():
            try:
                thread.join(timeout=0.5)
            except Exception:
                pass
    except Exception:
        pass
    try:  # pragma: no cover - Windows only
        import ctypes

        user32 = ctypes.windll.user32
        hooks = list(_CBT_STARTUP_WINDOW_HOOKS.values())
        if _CBT_STARTUP_WINDOW_LOCK is not None:
            try:
                with _CBT_STARTUP_WINDOW_LOCK:
                    _CBT_STARTUP_WINDOW_HOOKS.clear()
            except Exception:
                pass
        for hook in hooks:
            try:
                user32.UnhookWindowsHookEx(hook)
            except Exception:
                pass
    except Exception:
        pass
    _CBT_STARTUP_WINDOW_HOOKS.clear()
    _CBT_STARTUP_WINDOW_PROC = None
    _CBT_STARTUP_WINDOW_SCAN_STOP = None
    _CBT_STARTUP_WINDOW_SCAN_THREAD = None
    _CBT_STARTUP_WINDOW_LOCK = None


def _install_startup_window_suppression() -> None:
    global _STARTUP_WINDOW_HOOK, _STARTUP_WINDOW_PROC, _STARTUP_WINDOW_POLL_STOP, _STARTUP_WINDOW_POLL_THREAD
    if sys.platform != "win32" or _STARTUP_WINDOW_HOOK is not None:
        return
    if _env_flag("BOT_NO_STARTUP_WINDOW_SUPPRESS") or _env_flag("BOT_NO_WINEVENT_STARTUP_WINDOW_SUPPRESS"):
        return

    try:  # pragma: no cover - Windows only
        import ctypes
        import ctypes.wintypes as wintypes
        import threading
        import time
    except Exception:
        return

    user32 = ctypes.windll.user32
    kernel32 = ctypes.windll.kernel32
    pid = int(kernel32.GetCurrentProcessId())

    debug_window_events = _env_flag("BOT_DEBUG_WINDOW_EVENTS")
    debug_log_path = Path(os.getenv("TEMP") or ".").resolve() / "gate_window_events.log"

    EVENT_OBJECT_CREATE = 0x8000
    EVENT_OBJECT_SHOW = 0x8002
    WINEVENT_OUTOFCONTEXT = 0x0000
    OBJID_WINDOW = 0
    SW_HIDE = 0

    try:
        user32.ShowWindowAsync.argtypes = [wintypes.HWND, ctypes.c_int]
        user32.ShowWindowAsync.restype = wintypes.BOOL
    except Exception:
        pass

    try:
        user32.SetWinEventHook.argtypes = [
            wintypes.DWORD,
            wintypes.DWORD,
            wintypes.HMODULE,
            ctypes.c_void_p,
            wintypes.DWORD,
            wintypes.DWORD,
            wintypes.DWORD,
        ]
        user32.SetWinEventHook.restype = wintypes.HANDLE
        user32.UnhookWinEvent.argtypes = [wintypes.HANDLE]
        user32.UnhookWinEvent.restype = wintypes.BOOL
    except Exception:
        pass

    def _get_hwnd_pid(hwnd_obj) -> int:  # noqa: ANN001
        try:
            out_pid = wintypes.DWORD()
            user32.GetWindowThreadProcessId(hwnd_obj, ctypes.byref(out_pid))
            return int(out_pid.value)
        except Exception:
            return 0

    def _log_window(hwnd_obj, reason: str) -> None:  # noqa: ANN001
        if not debug_window_events:
            return
        try:
            class_buf = ctypes.create_unicode_buffer(256)
            user32.GetClassNameW(hwnd_obj, class_buf, 256)
            try:
                vis = int(bool(user32.IsWindowVisible(hwnd_obj)))
            except Exception:
                vis = 0
            try:
                get_style = getattr(user32, "GetWindowLongPtrW", None) or user32.GetWindowLongW
                style_val = int(get_style(hwnd_obj, -16))
            except Exception:
                style_val = 0
            try:
                get_exstyle = getattr(user32, "GetWindowLongPtrW", None) or user32.GetWindowLongW
                exstyle_val = int(get_exstyle(hwnd_obj, -20))
            except Exception:
                exstyle_val = 0
            rect = wintypes.RECT()
            user32.GetWindowRect(hwnd_obj, ctypes.byref(rect))
            width = int(rect.right - rect.left)
            height = int(rect.bottom - rect.top)
            pid_val = _get_hwnd_pid(hwnd_obj)
            with open(debug_log_path, "a", encoding="utf-8", errors="ignore") as fh:
                fh.write(
                    f"{reason} hwnd={int(hwnd_obj)} pid={pid_val} "
                    f"class={class_buf.value!r} size={width}x{height} "
                    f"vis={vis} style=0x{style_val:08X} exstyle=0x{exstyle_val:08X}\n"
                )
        except Exception:
            return

    def _is_transient_startup_window(hwnd_obj) -> bool:  # noqa: ANN001
        try:
            rect = wintypes.RECT()
            if not user32.GetWindowRect(hwnd_obj, ctypes.byref(rect)):
                return False
            width = int(rect.right - rect.left)
            height = int(rect.bottom - rect.top)
            if width <= 0 or height <= 0:
                return False

            class_buf = ctypes.create_unicode_buffer(256)
            user32.GetClassNameW(hwnd_obj, class_buf, 256)
            class_name = (class_buf.value or "").strip()

            # Skip child windows early.
            try:
                GWL_STYLE = -16
                WS_CHILD = 0x40000000
                get_style = getattr(user32, "GetWindowLongPtrW", None) or user32.GetWindowLongW
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
            if class_name in {"ConsoleWindowClass", "PseudoConsoleWindow"}:
                return True
            if class_name.startswith("_q_"):
                return height <= 260 and width <= 3200
            if class_name == "Intermediate D3D Window":
                return height <= 500 and width <= 4000
            if class_name.startswith("Chrome_WidgetWin_"):
                return height <= 400 and width <= 4000
            if width >= 500 and height >= 300:
                return False

            # Generic tiny top-level surfaces that can flash briefly.
            return height <= 80 and width <= 4000
        except Exception:
            return False

    def _hide_hwnd(hwnd_obj) -> None:  # noqa: ANN001
        try:
            SWP_NOSIZE = 0x0001
            SWP_NOZORDER = 0x0004
            SWP_NOACTIVATE = 0x0010
            SWP_HIDEWINDOW = 0x0080
            SWP_ASYNCWINDOWPOS = 0x4000
            user32.SetWindowPos(
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
            if getattr(user32, "ShowWindowAsync", None):
                user32.ShowWindowAsync(hwnd_obj, SW_HIDE)
            else:
                user32.ShowWindow(hwnd_obj, SW_HIDE)
        except Exception:
            pass

    WinEventProc = ctypes.WINFUNCTYPE(
        None,
        wintypes.HANDLE,
        wintypes.DWORD,
        wintypes.HWND,
        wintypes.LONG,
        wintypes.LONG,
        wintypes.DWORD,
        wintypes.DWORD,
    )

    def _win_event_proc(_hook, event, hwnd_obj, id_object, _id_child, _thread, _time):  # noqa: ANN001
        try:
            if id_object != OBJID_WINDOW or not hwnd_obj:
                return
            # Extra guard: only touch windows belonging to this process.
            if _get_hwnd_pid(hwnd_obj) != pid:
                return
            try:
                if not user32.IsWindowVisible(hwnd_obj):
                    return
            except Exception:
                return
            if not _is_transient_startup_window(hwnd_obj):
                return
            reason = "hide-startup-create" if int(event) == EVENT_OBJECT_CREATE else "hide-startup-show"
            _log_window(hwnd_obj, reason)
            _hide_hwnd(hwnd_obj)
        except Exception:
            return

    _STARTUP_WINDOW_PROC = WinEventProc(_win_event_proc)
    hook = user32.SetWinEventHook(
        EVENT_OBJECT_CREATE,
        EVENT_OBJECT_SHOW,
        0,
        _STARTUP_WINDOW_PROC,
        pid,
        0,
        WINEVENT_OUTOFCONTEXT,
    )
    _STARTUP_WINDOW_HOOK = hook if hook else None
    if _STARTUP_WINDOW_HOOK is None:
        _STARTUP_WINDOW_PROC = None

    # Fallback: during the first couple seconds, poll our top-level windows and hide
    # any transient startup helpers. This helps when a window is shown too briefly
    # for WinEvent to catch before the user perceives a flash.
    try:
        poll_ms = int(os.environ.get("BOT_STARTUP_WINDOW_POLL_MS") or 1500)
    except Exception:
        poll_ms = 1500
    try:
        interval_ms = int(os.environ.get("BOT_STARTUP_WINDOW_POLL_INTERVAL_MS") or 30)
    except Exception:
        interval_ms = 30
    poll_ms = max(200, min(poll_ms, 3000))
    interval_ms = max(20, min(interval_ms, 200))
    try:
        fast_ms = int(os.environ.get("BOT_STARTUP_WINDOW_POLL_FAST_MS") or 800)
    except Exception:
        fast_ms = 800
    fast_ms = max(0, min(fast_ms, poll_ms))
    try:
        fast_interval_ms = int(os.environ.get("BOT_STARTUP_WINDOW_POLL_FAST_INTERVAL_MS") or 10)
    except Exception:
        fast_interval_ms = 10
    fast_interval_ms = max(5, min(fast_interval_ms, interval_ms))

    stop_event = threading.Event()
    _STARTUP_WINDOW_POLL_STOP = stop_event

    EnumWindowsProc = ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)
    try:
        user32.EnumWindows.argtypes = [EnumWindowsProc, wintypes.LPARAM]
        user32.EnumWindows.restype = wintypes.BOOL
    except Exception:
        pass

    def _poll_once() -> None:
        def _enum_cb(hwnd_obj, _lparam):  # noqa: ANN001
            try:
                if _get_hwnd_pid(hwnd_obj) != pid:
                    return True
                try:
                    if not user32.IsWindowVisible(hwnd_obj):
                        return True
                except Exception:
                    return True
                if _is_transient_startup_window(hwnd_obj):
                    _hide_hwnd(hwnd_obj)
            except Exception:
                return True
            return True

        cb = EnumWindowsProc(_enum_cb)
        try:
            user32.EnumWindows(cb, 0)
        except Exception:
            pass

    def _poll_loop() -> None:
        start = time.monotonic()
        deadline = start + (max(200, poll_ms) / 1000.0)
        fast_deadline = start + (max(0, fast_ms) / 1000.0)
        while time.monotonic() < deadline and not stop_event.is_set():
            _poll_once()
            now = time.monotonic()
            sleep_s = (fast_interval_ms if now < fast_deadline else interval_ms) / 1000.0
            time.sleep(max(0.002, sleep_s))

    thread = threading.Thread(target=_poll_loop, name="startup-window-poll", daemon=True)
    _STARTUP_WINDOW_POLL_THREAD = thread
    thread.start()


def _uninstall_startup_window_suppression() -> None:
    global _STARTUP_WINDOW_HOOK, _STARTUP_WINDOW_PROC, _STARTUP_WINDOW_POLL_STOP, _STARTUP_WINDOW_POLL_THREAD
    if sys.platform != "win32" or _STARTUP_WINDOW_HOOK is None:
        return
    try:
        stop_event = _STARTUP_WINDOW_POLL_STOP
        if stop_event is not None:
            stop_event.set()
    except Exception:
        pass
    try:
        thread = _STARTUP_WINDOW_POLL_THREAD
        if thread is not None and getattr(thread, "is_alive", lambda: False)():
            try:
                thread.join(timeout=0.5)
            except Exception:
                pass
    except Exception:
        pass
    try:  # pragma: no cover - Windows only
        import ctypes
        ctypes.windll.user32.UnhookWinEvent(_STARTUP_WINDOW_HOOK)
    except Exception:
        pass
    _STARTUP_WINDOW_HOOK = None
    _STARTUP_WINDOW_PROC = None
    _STARTUP_WINDOW_POLL_STOP = None
    _STARTUP_WINDOW_POLL_THREAD = None


_install_cbt_startup_window_suppression()
_install_startup_window_suppression()

# Version banner / environment setup must run before importing PyQt modules
from app import preamble  # noqa: E402,F401

from PyQt6 import QtCore, QtGui  # noqa: E402
from PyQt6.QtWidgets import QApplication  # noqa: E402

from app.gui.app_icon import find_primary_icon_file, load_app_icon  # noqa: E402
from app.gui.main_window import MainWindow  # noqa: E402
from windows_taskbar import (  # noqa: E402
    apply_taskbar_metadata,
    build_relaunch_command,
    ensure_app_user_model_id,
    ensure_taskbar_visible,
)

APP_USER_MODEL_ID = "Gate.TradingBot"
_previous_qt_message_handler = None


def _install_qt_warning_filter() -> None:
    """Suppress nuisance Qt warnings we cannot control."""
    target = "setHighDpiScaleFactorRoundingPolicy"

    def handler(mode, context, message):  # noqa: ANN001
        if target in message:
            return
        if _previous_qt_message_handler is not None:
            _previous_qt_message_handler(mode, context, message)

    handler.__name__ = "qt_warning_filter"
    global _previous_qt_message_handler
    _previous_qt_message_handler = QtCore.qInstallMessageHandler(handler)


def main() -> int:
    _install_qt_warning_filter()

    disable_taskbar = _env_flag("BOT_DISABLE_TASKBAR")
    if sys.platform == "win32" and not disable_taskbar:
        ensure_app_user_model_id(APP_USER_MODEL_ID)

    QtCore.QCoreApplication.setAttribute(QtCore.Qt.ApplicationAttribute.AA_DontShowIconsInMenus, False)
    if sys.platform == "win32":
        try:
            QtCore.QCoreApplication.setAttribute(
                QtCore.Qt.ApplicationAttribute.AA_DontCreateNativeWidgetSiblings, True
            )
        except Exception:
            pass
        if _env_flag("BOT_FORCE_SOFTWARE_OPENGL"):
            try:
                QtCore.QCoreApplication.setAttribute(QtCore.Qt.ApplicationAttribute.AA_UseSoftwareOpenGL, True)
            except Exception:
                pass

    app = QApplication(sys.argv)
    app.setApplicationName("Gate Trading Bot")
    app.setApplicationDisplayName("Gate Trading Bot")
    app._exiting = False  # type: ignore[attr-defined]
    if sys.platform == "win32":
        try:
            app.setQuitOnLastWindowClosed(False)
        except Exception:
            pass

    icon = QtGui.QIcon()
    try:
        icon = load_app_icon()
    except Exception:
        icon = QtGui.QIcon()
    if not icon.isNull():
        try:
            app.setWindowIcon(icon)
            QtGui.QGuiApplication.setWindowIcon(icon)
        except Exception:
            pass

    win = MainWindow()
    try:
        win.setAttribute(QtCore.Qt.WidgetAttribute.WA_DeleteOnClose, False)
    except Exception:
        pass
    if not icon.isNull():
        try:
            win.setWindowIcon(icon)
        except Exception:
            pass

    if sys.platform == "win32" and not disable_taskbar:
        icon_path = find_primary_icon_file()
        relaunch_cmd = build_relaunch_command()

        def _apply_taskbar(attempts: int = 12) -> None:
            if attempts <= 0:
                return
            try:
                win.winId()
            except Exception:
                pass
            success = apply_taskbar_metadata(
                win,
                app_id=APP_USER_MODEL_ID,
                display_name="Gate Trading Bot",
                icon_path=icon_path,
                relaunch_command=relaunch_cmd,
            )
            try:
                ensure_taskbar_visible(win)
            except Exception:
                pass
            if not success and attempts > 1:
                QtCore.QTimer.singleShot(250, lambda: _apply_taskbar(attempts - 1))

        QtCore.QTimer.singleShot(0, _apply_taskbar)

    win.showMaximized()
    try:
        win.winId()
    except Exception:
        pass
    if sys.platform == "win32":
        try:
            watchdog_flag = str(os.environ.get("BOT_TRADINGVIEW_APP_WATCHDOG", "1")).strip().lower()
        except Exception:
            watchdog_flag = "1"
        if watchdog_flag not in {"0", "false", "no", "off"}:
            try:
                timer = QtCore.QTimer(app)
                timer.setInterval(200)

                def _tv_watchdog():  # noqa: N802
                    try:
                        if getattr(app, "_exiting", False):  # type: ignore[attr-defined]
                            return
                    except Exception:
                        pass
                    try:
                        guard_active = bool(
                            getattr(win, "_tv_close_guard_active", False)
                            or getattr(win, "_tv_visibility_watchdog_active", False)
                        )
                    except Exception:
                        guard_active = False
                    if not guard_active:
                        return
                    try:
                        if not win.isVisible() or win.windowState() & QtCore.Qt.WindowState.WindowMinimized:
                            win.showNormal()
                            win.raise_()
                            win.activateWindow()
                    except Exception:
                        pass

                timer.timeout.connect(_tv_watchdog)
                timer.start()
                app._tradingview_app_watchdog = timer  # type: ignore[attr-defined]
            except Exception:
                pass
    try:
        def _restore_main_window():  # noqa: N802
            try:
                if getattr(app, "_exiting", False):  # type: ignore[attr-defined]
                    return
            except Exception:
                pass
            try:
                if win is None or win.isVisible():
                    return
            except Exception:
                return
            try:
                win.showNormal()
                win.raise_()
                win.activateWindow()
            except Exception:
                pass

        app.lastWindowClosed.connect(_restore_main_window)
    except Exception:
        pass
    class _StartupInputUnblocker(QtCore.QObject):
        def __init__(self, app_instance: QApplication):
            super().__init__(app_instance)
            self._app = app_instance
            self._armed = True

        def eventFilter(self, obj, event):  # noqa: N802
            if not self._armed:
                return False
            try:
                ev_type = event.type()
            except Exception:
                return False
            if ev_type in {
                QtCore.QEvent.Type.MouseButtonPress,
                QtCore.QEvent.Type.MouseButtonRelease,
                QtCore.QEvent.Type.MouseButtonDblClick,
                QtCore.QEvent.Type.KeyPress,
                QtCore.QEvent.Type.Wheel,
                QtCore.QEvent.Type.TouchBegin,
            }:
                self._armed = False
                try:
                    _uninstall_startup_window_suppression()
                except Exception:
                    pass
                try:
                    _uninstall_cbt_startup_window_suppression()
                except Exception:
                    pass
                try:
                    self._app.removeEventFilter(self)
                except Exception:
                    pass
            return False

    try:
        app._startup_input_unblocker = _StartupInputUnblocker(app)
        app.installEventFilter(app._startup_input_unblocker)
    except Exception:
        pass
    if not icon.isNull():
        QtCore.QTimer.singleShot(0, lambda: win.setWindowIcon(icon))
    if sys.platform == "win32" and not disable_taskbar:
        try:
            controller_ms = int(os.environ.get("BOT_TASKBAR_ENSURE_MS") or 30000)
        except Exception:
            controller_ms = 30000
        try:
            interval_ms = int(os.environ.get("BOT_TASKBAR_ENSURE_INTERVAL_MS") or 250)
        except Exception:
            interval_ms = 250
        controller_ms = max(1000, min(controller_ms, 30000))
        interval_ms = max(100, min(interval_ms, 2000))
        start_ts = time.monotonic()

        def _tick_taskbar() -> None:
            try:
                ensure_taskbar_visible(win)
            except Exception:
                pass
            try:
                apply_taskbar_metadata(
                    win,
                    app_id=APP_USER_MODEL_ID,
                    display_name="Gate Trading Bot",
                    icon_path=icon_path,
                    relaunch_command=relaunch_cmd,
                )
            except Exception:
                pass
            if (time.monotonic() - start_ts) * 1000.0 < controller_ms:
                QtCore.QTimer.singleShot(interval_ms, _tick_taskbar)

        QtCore.QTimer.singleShot(0, _tick_taskbar)

    ready_signal = os.environ.get("BOT_STARTER_READY_FILE")
    if ready_signal:
        try:
            ready_path = Path(str(ready_signal)).expanduser()
            try:
                ready_path.parent.mkdir(parents=True, exist_ok=True)
            except Exception:
                pass
            try:
                ready_path.write_text(str(os.getpid()), encoding="utf-8", errors="ignore")
            except Exception:
                ready_path.touch(exist_ok=True)
        except Exception:
            pass

    try:
        suppress_ms = int(os.environ.get("BOT_STARTUP_WINDOW_SUPPRESS_DURATION_MS") or 8000)
    except Exception:
        suppress_ms = 8000
    QtCore.QTimer.singleShot(max(800, suppress_ms), _uninstall_startup_window_suppression)

    try:
        cbt_ms = int(os.environ.get("BOT_CBT_STARTUP_WINDOW_SUPPRESS_DURATION_MS") or 2500)
    except Exception:
        cbt_ms = 2500
    QtCore.QTimer.singleShot(max(250, min(8000, cbt_ms)), _uninstall_cbt_startup_window_suppression)

    try:
        auto_exit_ms = int(os.environ.get("BOT_AUTO_EXIT_MS") or 0)
    except Exception:
        auto_exit_ms = 0
    allow_auto_exit = str(os.environ.get("BOT_ALLOW_AUTO_EXIT", "")).strip().lower() in {"1", "true", "yes", "on"}
    if auto_exit_ms > 0 and allow_auto_exit:
        QtCore.QTimer.singleShot(auto_exit_ms, app.quit)

    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())
