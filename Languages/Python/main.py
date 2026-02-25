import os
import shutil
import sys
import time
from pathlib import Path

APP_DISPLAY_NAME = str(os.environ.get("BOT_TASKBAR_DISPLAY_NAME") or "Trading Bot").strip() or "Trading Bot"
APP_USER_MODEL_ID = str(os.environ.get("BOT_APP_USER_MODEL_ID") or "com.tradingbot.TradingBot").strip() or "com.tradingbot.TradingBot"
if sys.platform == "win32":
    os.environ["QT_WIN_APPID"] = APP_USER_MODEL_ID
    os.environ["QT_QPA_PLATFORM_WINDOWS_USER_MODEL_ID"] = APP_USER_MODEL_ID
    try:
        import ctypes
        ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID(APP_USER_MODEL_ID)
    except Exception:
        pass

# Ensure repo root is importable so shared helpers can be used when launched directly.
PROJECT_ROOT = Path(__file__).resolve().parents[2]
PROJECT_ROOT_STR = str(PROJECT_ROOT)
if PROJECT_ROOT_STR not in sys.path:
    sys.path.insert(0, PROJECT_ROOT_STR)

BINANCE_DIR = Path(__file__).resolve().parent
BINANCE_DIR_STR = str(BINANCE_DIR)
if BINANCE_DIR_STR not in sys.path:
    sys.path.insert(0, BINANCE_DIR_STR)


def _env_flag(name: str) -> bool:
    return str(os.environ.get(name, "")).strip().lower() in {"1", "true", "yes", "on"}


def _boot_log(message: str) -> None:
    if not _env_flag("BOT_BOOT_LOG"):
        return
    try:
        print(f"[boot] {message}", flush=True)
    except Exception:
        pass


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

def _sanitize_webengine_cli_args() -> None:
    """Drop risky Chromium args that can destabilize QtWebEngine/main window behavior."""
    if sys.platform != "win32":
        return
    try:
        argv = list(sys.argv or [])
    except Exception:
        return
    if len(argv) <= 1:
        return
    filtered = [argv[0]]
    changed = False
    for arg in argv[1:]:
        text = str(arg or "").strip()
        lower = text.lower()
        if lower in {"--single-process", "--in-process-gpu"}:
            changed = True
            continue
        if lower.startswith("--window-position="):
            changed = True
            continue
        filtered.append(arg)
    if changed:
        try:
            sys.argv[:] = filtered
        except Exception:
            pass

_sanitize_webengine_cli_args()


def _parse_entry_mode(argv: list[str]) -> str:
    """
    Select startup mode for this script.

    Modes:
    - "starter": open main UI and focus the Code Languages tab first
    - "direct": open main UI normally (dashboard-first, default)
    """
    env_mode = str(os.environ.get("BOT_MAIN_MODE", "")).strip().lower()
    if env_mode in {"starter", "direct"}:
        return env_mode

    lowered = {str(arg).strip().lower() for arg in argv}
    if "--direct" in lowered or "--mode=direct" in lowered:
        return "direct"
    if "--starter" in lowered or "--mode=starter" in lowered:
        return "starter"

    if _env_flag("BOT_DIRECT_MAIN"):
        return "direct"
    if _env_flag("BOT_STARTER_SHOW_UI"):
        return "starter"

    # Default startup should land on Dashboard.
    return "direct"


def _run_entrypoint(argv: list[str] | None = None) -> int:
    args = list(sys.argv[1:] if argv is None else argv)
    mode = _parse_entry_mode(args)
    if mode == "starter":
        os.environ["BOT_OPEN_CODE_TAB"] = "1"
    else:
        os.environ["BOT_OPEN_CODE_TAB"] = "0"
    return int(main())


def _configure_startup_window_suppression_defaults() -> None:
    """Set safe Windows startup suppression defaults unless user already configured them."""
    if sys.platform != "win32":
        return
    # Stability-first default: do not run WinEvent/CBT startup hooks unless explicitly
    # forced. This prevents occasional post-startup UI hangs on some systems.
    # Instead, use a full-screen startup mask to hide transient Qt windows.
    # The mask is made Win32-level click-through (WS_EX_TRANSPARENT) so it does not
    # block mouse input on Windows 11.
    if not _env_flag("BOT_FORCE_STARTUP_WINDOW_HOOKS"):
        # Both WinEvent and CBT hooks can cause UI hangs on some Windows 11 systems.
        # Use polling-based suppression instead (handled in main()).
        os.environ["BOT_DISABLE_STARTUP_WINDOW_HOOKS"] = "1"
        os.environ["BOT_ENABLE_CBT_STARTUP_WINDOW_SUPPRESS"] = "0"
        os.environ.setdefault("BOT_STARTUP_MASK_ENABLED", "0")
        os.environ.setdefault("BOT_STARTUP_REVEAL_DELAY_MS", "0")
        return
    if _env_flag("BOT_DISABLE_STARTUP_WINDOW_HOOKS"):
        return
    if _env_flag("BOT_NO_STARTUP_WINDOW_SUPPRESS"):
        return

    # Keep suppression short and process-scoped by default. Aggressive global hooks can
    # cause UI stalls on some Windows systems.
    os.environ.setdefault("BOT_STARTUP_WINDOW_SUPPRESS_DURATION_MS", "2500")
    os.environ.setdefault("BOT_STARTUP_WINDOW_POLL_MS", "2500")
    os.environ.setdefault("BOT_STARTUP_WINDOW_POLL_INTERVAL_MS", "20")
    os.environ.setdefault("BOT_STARTUP_WINDOW_POLL_FAST_MS", "900")
    os.environ.setdefault("BOT_STARTUP_WINDOW_POLL_FAST_INTERVAL_MS", "8")
    os.environ.setdefault("BOT_STARTUP_WINDOW_SUPPRESS_GLOBAL_HOOK", "0")
    os.environ.setdefault("BOT_TASKBAR_METADATA_DELAY_MS", "1200")
    os.environ.setdefault("BOT_TASKBAR_ENSURE_MS", "0")
    os.environ.setdefault("BOT_TASKBAR_ENSURE_START_DELAY_MS", "1200")
    os.environ.setdefault("BOT_PRIME_NATIVE_CHART_HOST", "0")
    os.environ.setdefault("BOT_STARTUP_REVEAL_DELAY_MS", "400")
    os.environ.setdefault("BOT_STARTUP_WINDOW_HOOK_AUTO_UNINSTALL_MS", "900")

    if _env_flag("BOT_NO_CBT_STARTUP_WINDOW_SUPPRESS"):
        return

    # Keep CBT disabled by default; WinEvent+poll suppression handles most flickers
    # with lower risk of UI stalls.
    os.environ.setdefault("BOT_ENABLE_CBT_STARTUP_WINDOW_SUPPRESS", "0")
    os.environ.setdefault("BOT_CBT_STARTUP_WINDOW_SUPPRESS_DURATION_MS", "2500")
    os.environ.setdefault("BOT_CBT_THREAD_HOOK_SCAN_MS", "0")
    os.environ.setdefault("BOT_CBT_THREAD_HOOK_SCAN_INTERVAL_MS", "80")


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
    # Enabled by default for the main/UI thread; multi-thread scan remains opt-in.
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
    debug_log_path = Path(os.getenv("TEMP") or ".").resolve() / "binance_window_events.log"

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

    def _read_hwnd_title(hwnd_val: int) -> str:
        try:
            buf = ctypes.create_unicode_buffer(256)
            user32.GetWindowTextW(wintypes.HWND(int(hwnd_val)), buf, 256)
            return str(buf.value or "").strip()
        except Exception:
            return ""

    def _looks_like_qt_internal_helper_window(*, class_name: str, title: str) -> bool:
        name = str(class_name or "").strip()
        if name.startswith("QEventDispatcherWin32_"):
            return True
        if name.startswith("Qt") and any(name.endswith(suffix) for suffix in _QT_INTERNAL_WINDOW_SUFFIXES):
            return True
        ttl = str(title or "").strip()
        # Titles often omit the version digits (e.g., "QtPowerDummyWindow").
        if ttl.startswith("QEventDispatcherWin32_"):
            return True
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
            title_text = cs_title or _read_hwnd_title(hwnd_val)
            if class_name.startswith("QEventDispatcherWin32_Internal_Widget"):
                return user32.CallNextHookEx(0, n_code, w_param, l_param)
            if _looks_like_qt_internal_helper_window(class_name=class_name, title=title_text):
                cs.style = int(style & ~WS_VISIBLE)
                ex_style = int(cs.dwExStyle) & 0xFFFFFFFF
                cs.dwExStyle = int((ex_style | WS_EX_TOOLWINDOW | WS_EX_NOACTIVATE) & ~WS_EX_APPWINDOW)
                cs.x = -32000
                cs.y = -32000
                if debug_window_events:
                    try:
                        with open(debug_log_path, "a", encoding="utf-8", errors="ignore") as fh:
                            fh.write(
                                f"cbt-hide-qt-helper hwnd={hwnd_val} size={width}x{height} class={class_name!r} title={title_text!r} "
                                f"style=0x{style:08X} exstyle=0x{ex_style:08X}\n"
                            )
                    except Exception:
                        pass
                return user32.CallNextHookEx(0, n_code, w_param, l_param)
            # Never touch anything that looks like the actual app window.
            if width >= 500 and height >= 300:
                return user32.CallNextHookEx(0, n_code, w_param, l_param)
            # Target only tiny top-level helpers that can flash (titlebar-sized).
            if height <= 800 and width <= 4000:
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
        if not _thread_has_message_queue(int(thread_id)):
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
        scan_ms = int(os.environ.get("BOT_CBT_THREAD_HOOK_SCAN_MS") or 0)
    except Exception:
        scan_ms = 0
    scan_ms = max(0, min(30000, scan_ms))
    try:
        interval_ms = int(os.environ.get("BOT_CBT_THREAD_HOOK_SCAN_INTERVAL_MS") or 50)
    except Exception:
        interval_ms = 50
    interval_ms = max(20, min(250, interval_ms))

    try:
        pid_val = int(kernel32.GetCurrentProcessId())
    except Exception:
        pid_val = 0

    if scan_ms <= 0:
        return

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
    if sys.platform != "win32":
        return
    if _STARTUP_WINDOW_HOOK is not None or _STARTUP_WINDOW_POLL_THREAD is not None:
        return
    if _env_flag("BOT_NO_STARTUP_WINDOW_SUPPRESS"):
        return
    disable_winevent_hook = _env_flag("BOT_NO_WINEVENT_STARTUP_WINDOW_SUPPRESS")

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
    debug_log_path = Path(os.getenv("TEMP") or ".").resolve() / "binance_window_events.log"

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

    try:
        user32.EnumWindows.argtypes = [ctypes.c_void_p, wintypes.LPARAM]
        user32.EnumWindows.restype = wintypes.BOOL
    except Exception:
        pass

    def _get_hwnd_pid(hwnd_obj) -> int:  # noqa: ANN001
        try:
            out_pid = wintypes.DWORD()
            user32.GetWindowThreadProcessId(hwnd_obj, ctypes.byref(out_pid))
            return int(out_pid.value)
        except Exception:
            return 0

    def _enum_descendant_pids(root_pid: int) -> set[int]:
        pids: set[int] = {int(root_pid)}
        if not root_pid:
            return pids
        try:
            TH32CS_SNAPPROCESS = 0x00000002
            snapshot = kernel32.CreateToolhelp32Snapshot(TH32CS_SNAPPROCESS, 0)
            if snapshot in (0, ctypes.c_void_p(-1).value):
                return pids

            class PROCESSENTRY32(ctypes.Structure):
                _fields_ = [
                    ("dwSize", wintypes.DWORD),
                    ("cntUsage", wintypes.DWORD),
                    ("th32ProcessID", wintypes.DWORD),
                    ("th32DefaultHeapID", ctypes.c_void_p),
                    ("th32ModuleID", wintypes.DWORD),
                    ("cntThreads", wintypes.DWORD),
                    ("th32ParentProcessID", wintypes.DWORD),
                    ("pcPriClassBase", wintypes.LONG),
                    ("dwFlags", wintypes.DWORD),
                    ("szExeFile", wintypes.WCHAR * 260),
                ]

            parent_to_children: dict[int, list[int]] = {}
            entry = PROCESSENTRY32()
            entry.dwSize = ctypes.sizeof(entry)
            try:
                if kernel32.Process32FirstW(snapshot, ctypes.byref(entry)):
                    while True:
                        child_pid = int(entry.th32ProcessID)
                        parent_pid = int(entry.th32ParentProcessID)
                        parent_to_children.setdefault(parent_pid, []).append(child_pid)
                        if not kernel32.Process32NextW(snapshot, ctypes.byref(entry)):
                            break
            finally:
                try:
                    kernel32.CloseHandle(snapshot)
                except Exception:
                    pass

            queue = [int(root_pid)]
            while queue:
                current = queue.pop()
                for child in parent_to_children.get(current, []):
                    if child not in pids:
                        pids.add(child)
                        queue.append(child)
        except Exception:
            return pids
        return pids

    tracked_lock = threading.Lock()
    tracked_pids: set[int] = {int(pid)}
    tracked_state = {"ts": 0.0}

    def _refresh_descendant_pids(force: bool = False) -> set[int]:
        now = time.monotonic()
        with tracked_lock:
            last_ts = float(tracked_state["ts"])
            if not force and (now - last_ts) < 0.2:
                return set(tracked_pids)
        refreshed = _enum_descendant_pids(pid)
        with tracked_lock:
            tracked_pids.clear()
            tracked_pids.update(refreshed)
            tracked_state["ts"] = now
            return set(tracked_pids)

    def _pid_is_tracked(pid_val: int) -> bool:
        if not pid_val:
            return False
        with tracked_lock:
            if pid_val in tracked_pids:
                return True
        return pid_val in _refresh_descendant_pids(force=False)

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
            title_buf = ctypes.create_unicode_buffer(256)
            user32.GetWindowTextW(hwnd_obj, title_buf, 256)
            title = (title_buf.value or "").strip()

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
            if class_name.startswith("QEventDispatcherWin32_Internal_Widget"):
                return False
            if class_name.startswith("QEventDispatcherWin32_"):
                return True
            if title.startswith("QEventDispatcherWin32_Internal_Widget"):
                return False
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

            # Generic tiny top-level surfaces that can flash briefly.
            return height <= 800 and width <= 4000
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
            is_create_event = int(event) == EVENT_OBJECT_CREATE
            hwnd_pid = _get_hwnd_pid(hwnd_obj)
            if not _pid_is_tracked(hwnd_pid):
                return
            if not is_create_event:
                try:
                    if not user32.IsWindowVisible(hwnd_obj):
                        return
                except Exception:
                    return
            if not _is_transient_startup_window(hwnd_obj):
                return
            reason = "hide-startup-create" if is_create_event else "hide-startup-show"
            _log_window(hwnd_obj, reason)
            _hide_hwnd(hwnd_obj)
        except Exception:
            return

    _refresh_descendant_pids(force=True)

    _STARTUP_WINDOW_PROC = WinEventProc(_win_event_proc)
    hook = 0
    if not disable_winevent_hook:
        use_global_hook = str(os.environ.get("BOT_STARTUP_WINDOW_SUPPRESS_GLOBAL_HOOK", "")).strip().lower() not in {
            "0",
            "false",
            "no",
            "off",
        }
        hook_pid = 0 if use_global_hook else pid
        hook = user32.SetWinEventHook(
            EVENT_OBJECT_CREATE,
            EVENT_OBJECT_SHOW,
            0,
            _STARTUP_WINDOW_PROC,
            hook_pid,
            0,
            WINEVENT_OUTOFCONTEXT,
        )
    _STARTUP_WINDOW_HOOK = hook if hook else None
    if _STARTUP_WINDOW_HOOK is None:
        _STARTUP_WINDOW_PROC = None

    # Fallback: poll top-level windows and hide transient helpers in this process tree.
    try:
        suppress_ms = int(os.environ.get("BOT_STARTUP_WINDOW_SUPPRESS_DURATION_MS") or 8000)
    except Exception:
        suppress_ms = 8000
    suppress_ms = max(500, min(suppress_ms, 30000))
    try:
        poll_ms = int(os.environ.get("BOT_STARTUP_WINDOW_POLL_MS") or suppress_ms)
    except Exception:
        poll_ms = suppress_ms
    try:
        interval_ms = int(os.environ.get("BOT_STARTUP_WINDOW_POLL_INTERVAL_MS") or 30)
    except Exception:
        interval_ms = 30
    poll_ms = max(200, min(poll_ms, suppress_ms))
    interval_ms = max(20, min(interval_ms, 200))
    try:
        fast_ms = int(os.environ.get("BOT_STARTUP_WINDOW_POLL_FAST_MS") or 1200)
    except Exception:
        fast_ms = 1200
    fast_ms = max(0, min(fast_ms, poll_ms))
    try:
        fast_interval_ms = int(os.environ.get("BOT_STARTUP_WINDOW_POLL_FAST_INTERVAL_MS") or 10)
    except Exception:
        fast_interval_ms = 10
    fast_interval_ms = max(5, min(fast_interval_ms, interval_ms))

    stop_event = threading.Event()
    _STARTUP_WINDOW_POLL_STOP = stop_event

    EnumWindowsProc = ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)

    def _poll_once() -> None:
        def _enum_cb(hwnd_obj, _lparam):  # noqa: ANN001
            try:
                hwnd_pid = _get_hwnd_pid(hwnd_obj)
                if not _pid_is_tracked(hwnd_pid):
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
        next_pid_refresh = start
        while time.monotonic() < deadline and not stop_event.is_set():
            now = time.monotonic()
            if now >= next_pid_refresh:
                _refresh_descendant_pids(force=True)
                next_pid_refresh = now + 0.05
            _poll_once()
            sleep_s = (fast_interval_ms if now < fast_deadline else interval_ms) / 1000.0
            time.sleep(max(0.002, sleep_s))

    thread = threading.Thread(target=_poll_loop, name="startup-window-poll", daemon=True)
    _STARTUP_WINDOW_POLL_THREAD = thread
    thread.start()


def _uninstall_startup_window_suppression() -> None:
    global _STARTUP_WINDOW_HOOK, _STARTUP_WINDOW_PROC, _STARTUP_WINDOW_POLL_STOP, _STARTUP_WINDOW_POLL_THREAD
    if sys.platform != "win32":
        return
    if _STARTUP_WINDOW_HOOK is None and _STARTUP_WINDOW_POLL_STOP is None and _STARTUP_WINDOW_POLL_THREAD is None:
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
    if _STARTUP_WINDOW_HOOK is not None:
        try:  # pragma: no cover - Windows only
            import ctypes
            ctypes.windll.user32.UnhookWinEvent(_STARTUP_WINDOW_HOOK)
        except Exception:
            pass
    _STARTUP_WINDOW_HOOK = None
    _STARTUP_WINDOW_PROC = None
    _STARTUP_WINDOW_POLL_STOP = None
    _STARTUP_WINDOW_POLL_THREAD = None






_previous_qt_message_handler = None
_native_icon_handles: list[int] = []


def _install_qt_warning_filter() -> None:
    """Suppress nuisance Qt warnings we cannot control."""
    from PyQt6 import QtCore
    target = "setHighDpiScaleFactorRoundingPolicy"

    def handler(mode, context, message):  # noqa: ANN001
        if target in message:
            return
        if _previous_qt_message_handler is not None:
            _previous_qt_message_handler(mode, context, message)

    handler.__name__ = "qt_warning_filter"
    global _previous_qt_message_handler
    _previous_qt_message_handler = QtCore.qInstallMessageHandler(handler)


def _resolve_native_icon_path() -> Path | None:
    from app.gui.app_icon import find_primary_icon_file
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
    # Prefer a stable cached icon path first (safe for pinned taskbar entries).
    native_icon = _resolve_native_icon_path()
    persisted = _persist_icon_for_taskbar(native_icon)
    if persisted and persisted.is_file():
        return persisted
    if getattr(sys, "frozen", False):
        try:
            exe_icon = Path(sys.executable).resolve()
        except Exception:
            exe_icon = None
        if exe_icon is not None and exe_icon.is_file():
            # In bundled mode, prefer the executable icon resource so pinned
            # taskbar entries don't depend on transient _MEIPASS paths.
            return exe_icon
    icon_path = _resolve_native_icon_path()
    if icon_path and icon_path.is_file():
        return icon_path
    from app.gui.app_icon import find_primary_icon_file
    primary = find_primary_icon_file()
    if primary and primary.is_file():
        if primary.suffix.lower() == ".ico":
            return primary
        ico_path = primary.with_suffix(".ico")
        if ico_path.is_file():
            return ico_path
        return primary
    repo_icon = Path(__file__).resolve().parents[2] / "assets" / "crypto_forex_logo.ico"
    return repo_icon if repo_icon.is_file() else None


def _resolve_splash_logo_pixmap(QtGui):  # noqa: N803
    """Best-effort splash logo resolver that works in source and frozen builds."""
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

    root_assets = Path(__file__).resolve().parents[2] / "assets"
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
        import subprocess
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
        cx_small = int(user32.GetSystemMetrics(49))  # SM_CXSMICON
        cy_small = int(user32.GetSystemMetrics(50))  # SM_CYSMICON
        cx_big = int(user32.GetSystemMetrics(11))  # SM_CXICON
        cy_big = int(user32.GetSystemMetrics(12))  # SM_CYICON
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
    from app.gui.app_icon import load_app_icon, find_primary_icon_file
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
    """Lightweight loading screen shown during startup.

    Uses raw QWidget + QPainter to avoid importing heavy modules early.
    Made Win32-level click-through so it never blocks mouse input.
    """

    def __init__(self, app, QtCore, QtGui, QWidget):  # noqa: N803
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
            screen = QtGui.QGuiApplication.primaryScreen()
            screen_geo = screen.geometry() if screen else QtCore.QRect(0, 0, 1920, 1080)

            splash_w, splash_h = 420, 320

            splash = _SplashWidget(
                None,
                QtCore.Qt.WindowType.FramelessWindowHint
                | QtCore.Qt.WindowType.WindowStaysOnTopHint
                | QtCore.Qt.WindowType.Tool
                | QtCore.Qt.WindowType.WindowDoesNotAcceptFocus
                | QtCore.Qt.WindowType.NoDropShadowWindowHint,
            )
            splash.setAttribute(QtCore.Qt.WidgetAttribute.WA_TranslucentBackground, True)
            splash.setAttribute(QtCore.Qt.WidgetAttribute.WA_ShowWithoutActivating, True)
            splash.setAttribute(QtCore.Qt.WidgetAttribute.WA_TransparentForMouseEvents, True)
            splash.setFixedSize(splash_w, splash_h)

            x = screen_geo.x() + (screen_geo.width() - splash_w) // 2
            y = screen_geo.y() + (screen_geo.height() - splash_h) // 2
            splash.move(x, y)

            splash._splash_ref = self  # back-reference for paint
            self._widget = splash
            splash.show()
            app.processEvents(QtCore.QEventLoop.ProcessEventsFlag.AllEvents, 30)

            # Win32 click-through
            if sys.platform == "win32":
                try:
                    import ctypes
                    import ctypes.wintypes as wintypes
                    _u32 = ctypes.windll.user32
                    _hwnd = wintypes.HWND(int(splash.winId()))
                    GWL_EXSTYLE = -20
                    WS_EX_LAYERED = 0x00080000
                    WS_EX_TRANSPARENT = 0x00000020
                    _get = getattr(_u32, "GetWindowLongPtrW", None) or _u32.GetWindowLongW
                    _set = getattr(_u32, "SetWindowLongPtrW", None) or _u32.SetWindowLongW
                    _ex = int(_get(_hwnd, GWL_EXSTYLE))
                    _set(_hwnd, GWL_EXSTYLE, _ex | WS_EX_LAYERED | WS_EX_TRANSPARENT)
                except Exception:
                    pass

            # Spinner animation timer
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
    """Minimal widget subclass placeholder — replaced at runtime below."""
    pass


def _make_splash_widget_class(QWidget, QtCore, QtGui):  # noqa: N803
    """Create the splash widget class at call-time so Qt imports are available."""

    class SplashWidget(QWidget):
        def paintEvent(self, event):  # noqa: N802
            splash_ref = getattr(self, "_splash_ref", None)
            if splash_ref is None:
                return
            try:
                painter = QtGui.QPainter(self)
                painter.setRenderHint(QtGui.QPainter.RenderHint.Antialiasing, True)

                w, h = self.width(), self.height()

                # --- Background panel with rounded corners ---
                panel_rect = QtCore.QRectF(0, 0, w, h)
                panel_path = QtGui.QPainterPath()
                panel_path.addRoundedRect(panel_rect, 24, 24)
                painter.setClipPath(panel_path)

                # Dark gradient background
                bg_grad = QtGui.QLinearGradient(0, 0, 0, h)
                bg_grad.setColorAt(0.0, QtGui.QColor(16, 22, 32, 245))
                bg_grad.setColorAt(1.0, QtGui.QColor(10, 14, 22, 250))
                painter.fillRect(self.rect(), bg_grad)

                # Subtle border glow
                painter.setClipping(False)
                border_pen = QtGui.QPen(QtGui.QColor(56, 189, 248, 80))
                border_pen.setWidthF(1.5)
                painter.setPen(border_pen)
                painter.setBrush(QtCore.Qt.BrushStyle.NoBrush)
                painter.drawRoundedRect(QtCore.QRectF(0.75, 0.75, w - 1.5, h - 1.5), 24, 24)

                # --- Top accent line gradient ---
                accent_rect = QtCore.QRectF(40, 0, w - 80, 3)
                accent_grad = QtGui.QLinearGradient(40, 0, w - 40, 0)
                accent_grad.setColorAt(0.0, QtGui.QColor(56, 189, 248, 0))
                accent_grad.setColorAt(0.3, QtGui.QColor(56, 189, 248, 180))
                accent_grad.setColorAt(0.5, QtGui.QColor(52, 211, 153, 200))
                accent_grad.setColorAt(0.7, QtGui.QColor(56, 189, 248, 180))
                accent_grad.setColorAt(1.0, QtGui.QColor(56, 189, 248, 0))
                painter.setPen(QtCore.Qt.PenStyle.NoPen)
                painter.setBrush(accent_grad)
                painter.drawRoundedRect(accent_rect, 1.5, 1.5)

                cy = 40  # current y position for layout

                # --- App logo ---
                logo = splash_ref._logo_pixmap
                if logo is not None and not logo.isNull():
                    logo_size = 72
                    scaled = logo.scaled(
                        logo_size, logo_size,
                        QtCore.Qt.AspectRatioMode.KeepAspectRatio,
                        QtCore.Qt.TransformationMode.SmoothTransformation,
                    )
                    lx = (w - scaled.width()) // 2
                    painter.drawPixmap(lx, cy, scaled)
                    cy += logo_size + 16
                else:
                    cy += 20

                # --- App name ---
                title_font = QtGui.QFont("Segoe UI", 18, QtGui.QFont.Weight.Bold)
                painter.setFont(title_font)
                painter.setPen(QtGui.QColor(230, 237, 243))
                title_rect = QtCore.QRectF(0, cy, w, 30)
                painter.drawText(title_rect, QtCore.Qt.AlignmentFlag.AlignHCenter | QtCore.Qt.AlignmentFlag.AlignTop, APP_DISPLAY_NAME)
                cy += 36

                # --- Status text ---
                status_font = QtGui.QFont("Segoe UI", 11)
                painter.setFont(status_font)
                painter.setPen(QtGui.QColor(148, 163, 184))
                status_rect = QtCore.QRectF(0, cy, w, 22)
                painter.drawText(status_rect, QtCore.Qt.AlignmentFlag.AlignHCenter | QtCore.Qt.AlignmentFlag.AlignTop, splash_ref._status_text)
                cy += 34

                # --- Spinner ring ---
                spinner_size = 44
                sx = (w - spinner_size) // 2
                spinner_rect = QtCore.QRectF(sx, cy, spinner_size, spinner_size)

                # Track ring (dim) — use QPainterPath for smooth AA
                track_pen = QtGui.QPen(QtGui.QColor(148, 163, 184, 40))
                track_pen.setWidthF(3.0)
                track_pen.setCapStyle(QtCore.Qt.PenCapStyle.RoundCap)
                painter.setPen(track_pen)
                painter.setBrush(QtCore.Qt.BrushStyle.NoBrush)
                painter.drawEllipse(spinner_rect)

                # Active arc (bright) — QPainterPath for smooth curves
                arc_path = QtGui.QPainterPath()
                arc_path.arcMoveTo(spinner_rect, splash_ref._spinner_angle)
                arc_path.arcTo(spinner_rect, splash_ref._spinner_angle, 100)
                arc_pen = QtGui.QPen(QtGui.QColor(56, 189, 248))
                arc_pen.setWidthF(3.0)
                arc_pen.setCapStyle(QtCore.Qt.PenCapStyle.RoundCap)
                painter.setPen(arc_pen)
                painter.drawPath(arc_path)

                # Second smaller arc for visual depth
                arc_path2 = QtGui.QPainterPath()
                angle2 = (splash_ref._spinner_angle + 180) % 360
                arc_path2.arcMoveTo(spinner_rect, angle2)
                arc_path2.arcTo(spinner_rect, angle2, 60)
                arc_pen2 = QtGui.QPen(QtGui.QColor(52, 211, 153, 180))
                arc_pen2.setWidthF(3.0)
                arc_pen2.setCapStyle(QtCore.Qt.PenCapStyle.RoundCap)
                painter.setPen(arc_pen2)
                painter.drawPath(arc_path2)

            except Exception:
                pass
            finally:
                try:
                    painter.end()
                except Exception:
                    pass

    return SplashWidget


def main() -> int:
    _configure_startup_window_suppression_defaults()
    if _env_flag("BOT_DISABLE_STARTUP_WINDOW_HOOKS"):
        _boot_log("startup window hooks disabled")
    else:
        _install_cbt_startup_window_suppression()
        _install_startup_window_suppression()

    # Version banner / environment setup must run before importing PyQt modules
    from app import preamble  # noqa: E402,F401
    _boot_log("preamble loaded")

    from PyQt6 import QtCore, QtGui  # noqa: E402
    from PyQt6.QtWidgets import QApplication, QLabel, QWidget  # noqa: E402

    # Heavy imports (MainWindow, app_icon) are deferred to after the splash screen
    # is shown, so the user sees loading feedback immediately.
    from app.platform.windows_taskbar import (  # noqa: E402
        apply_taskbar_metadata,
        build_relaunch_command,
        ensure_app_user_model_id,
        ensure_start_menu_shortcut,
        ensure_taskbar_visible,
    )

    _install_qt_warning_filter()
    _boot_log(
        "env BOT_NO_STARTUP_WINDOW_SUPPRESS="
        f"{os.environ.get('BOT_NO_STARTUP_WINDOW_SUPPRESS', '')!r} "
        "BOT_NO_CBT_STARTUP_WINDOW_SUPPRESS="
        f"{os.environ.get('BOT_NO_CBT_STARTUP_WINDOW_SUPPRESS', '')!r} "
        "BOT_ENABLE_CBT_STARTUP_WINDOW_SUPPRESS="
        f"{os.environ.get('BOT_ENABLE_CBT_STARTUP_WINDOW_SUPPRESS', '')!r} "
        "BOT_DISABLE_STARTUP_WINDOW_HOOKS="
        f"{os.environ.get('BOT_DISABLE_STARTUP_WINDOW_HOOKS', '')!r} "
        "BOT_STARTUP_MASK_ENABLED="
        f"{os.environ.get('BOT_STARTUP_MASK_ENABLED', '')!r} "
        "BOT_STARTUP_MASK_MODE="
        f"{os.environ.get('BOT_STARTUP_MASK_MODE', '')!r}"
    )

    force_app_icon = _env_flag("BOT_FORCE_APP_ICON")
    force_taskbar = _env_flag("BOT_FORCE_TASKBAR_ICON")
    disable_taskbar = _env_flag("BOT_DISABLE_TASKBAR") and not force_taskbar
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
    app.setApplicationName(APP_DISPLAY_NAME)
    app.setApplicationDisplayName(APP_DISPLAY_NAME)
    app._exiting = False  # type: ignore[attr-defined]
    try:
        QtGui.QGuiApplication.setDesktopFileName(APP_USER_MODEL_ID)
    except Exception:
        pass
    if sys.platform == "win32":
        try:
            app.setQuitOnLastWindowClosed(False)
        except Exception:
            pass
    # --- Suppress transient startup windows via WinEvent hook on dedicated thread ---
    # Qt/QtWebEngine create small helper windows during init that flash briefly.
    # We install a WinEvent hook (EVENT_OBJECT_SHOW) on a DEDICATED background thread
    # with its own Win32 message loop BEFORE creating any Qt windows (including the
    # splash screen). A threading.Event ensures the hook is active before we proceed.
    _suppress_stop = False
    _suppress_thread_id = 0
    _suppress_known_ok: set[int] = set()  # whitelisted HWNDs (splash, main window)
    _hook_ready = None  # threading.Event set when hook is installed

    def _suppress_via_winevent():
        nonlocal _suppress_thread_id
        if sys.platform != "win32":
            if _hook_ready is not None:
                _hook_ready.set()
            return
        try:
            import ctypes
            import ctypes.wintypes as wintypes

            user32 = ctypes.windll.user32
            kernel32 = ctypes.windll.kernel32

            _suppress_thread_id = kernel32.GetCurrentThreadId()
            pid = kernel32.GetCurrentProcessId()

            SW_HIDE = 0
            GWL_STYLE = -16
            WS_VISIBLE = 0x10000000
            EVENT_OBJECT_SHOW = 0x8002
            WINEVENT_OUTOFCONTEXT = 0x0000
            _get_style = getattr(user32, "GetWindowLongPtrW", None) or user32.GetWindowLongW

            # WinEvent callback — fires instantly when any window becomes visible
            WINEVENTPROC = ctypes.WINFUNCTYPE(
                None,
                wintypes.HANDLE, wintypes.DWORD, wintypes.HWND,
                ctypes.c_long, ctypes.c_long, wintypes.DWORD, wintypes.DWORD,
            )

            def _on_show(_hook, _event, hwnd, id_object, _id_child, _tid, _time):
                if id_object != 0:  # OBJID_WINDOW = 0
                    return
                h = int(hwnd) if hwnd else 0
                if not h or h in _suppress_known_ok:
                    return
                try:
                    w_pid = wintypes.DWORD()
                    user32.GetWindowThreadProcessId(hwnd, ctypes.byref(w_pid))
                    if w_pid.value != pid:
                        return

                    style = int(_get_style(hwnd, GWL_STYLE))
                    if not (style & WS_VISIBLE):
                        return

                    rect = wintypes.RECT()
                    user32.GetWindowRect(hwnd, ctypes.byref(rect))
                    w = rect.right - rect.left
                    h_val = rect.bottom - rect.top
                    if w > 400 and h_val > 300:
                        _suppress_known_ok.add(h)
                        return

                    # Move off-screen instantly (MoveWindow is immediate, doesn't
                    # need the target thread to process messages like ShowWindow does)
                    user32.MoveWindow(hwnd, -32000, -32000, 1, 1, False)
                    user32.ShowWindow(hwnd, SW_HIDE)
                except Exception:
                    pass

            cb = WINEVENTPROC(_on_show)

            hook = user32.SetWinEventHook(
                EVENT_OBJECT_SHOW, EVENT_OBJECT_SHOW,
                None, cb, pid, 0, WINEVENT_OUTOFCONTEXT,
            )

            # Signal main thread that hook is installed
            if _hook_ready is not None:
                _hook_ready.set()

            if not hook:
                return

            import time
            deadline = time.monotonic() + 5.0
            msg = wintypes.MSG()
            while not _suppress_stop and time.monotonic() < deadline:
                while user32.PeekMessageW(ctypes.byref(msg), None, 0, 0, 1):
                    if msg.message == 0x0012:  # WM_QUIT
                        user32.UnhookWinEvent(hook)
                        return
                    user32.TranslateMessage(ctypes.byref(msg))
                    user32.DispatchMessageW(ctypes.byref(msg))
                time.sleep(0.001)

            user32.UnhookWinEvent(hook)
        except Exception:
            if _hook_ready is not None:
                _hook_ready.set()

    # Start hook thread and wait for it to be ready BEFORE creating any Qt windows
    if sys.platform == "win32":
        import threading as _th
        _hook_ready = _th.Event()
        _suppress_thread = _th.Thread(target=_suppress_via_winevent, daemon=True)
        _suppress_thread.start()
        _hook_ready.wait(timeout=0.5)  # wait up to 500ms for hook to be installed
        _boot_log("transient window suppression hook ready")

    # --- Show loading splash screen ---
    global _SplashWidget
    _SplashWidget = _make_splash_widget_class(QWidget, QtCore, QtGui)
    splash = None
    if not _env_flag("BOT_DISABLE_SPLASH"):
        try:
            splash = _SplashScreen(app, QtCore, QtGui, QWidget)
            _boot_log("splash screen shown")
            # Whitelist splash HWND so the hook doesn't hide it
            if splash._widget is not None:
                try:
                    _suppress_known_ok.add(int(splash._widget.winId()))
                except Exception:
                    pass
        except Exception:
            splash = None

    startup_masks: list[QWidget] = []
    startup_mask_hide_ms = 0
    startup_mask_mode = ""
    if sys.platform == "win32" and _env_flag("BOT_STARTUP_MASK_ENABLED"):
        try:
            startup_mask_hide_ms = int(os.environ.get("BOT_STARTUP_MASK_HIDE_MS") or 500)
        except Exception:
            startup_mask_hide_ms = 500
        startup_mask_mode = str(os.environ.get("BOT_STARTUP_MASK_MODE") or "snapshot").strip().lower()
        startup_mask_hide_ms = max(100, min(startup_mask_hide_ms, 5000))
        try:
            screens = list(QtGui.QGuiApplication.screens() or [])
            if not screens:
                primary = QtGui.QGuiApplication.primaryScreen()
                if primary is not None:
                    screens = [primary]
            snapshot_count = 0
            for screen in screens:
                mask = QWidget(
                    None,
                    QtCore.Qt.WindowType.FramelessWindowHint
                    | QtCore.Qt.WindowType.Tool
                    | QtCore.Qt.WindowType.WindowStaysOnTopHint
                    | QtCore.Qt.WindowType.WindowDoesNotAcceptFocus
                    | QtCore.Qt.WindowType.NoDropShadowWindowHint,
                )
                mask.setAttribute(QtCore.Qt.WidgetAttribute.WA_ShowWithoutActivating, True)
                mask.setAttribute(QtCore.Qt.WidgetAttribute.WA_TransparentForMouseEvents, True)
                mask.setGeometry(screen.geometry())
                mask_is_snapshot = False
                if startup_mask_mode == "snapshot":
                    try:
                        pixmap = screen.grabWindow(0)
                    except Exception:
                        pixmap = QtGui.QPixmap()
                    if pixmap is not None and not pixmap.isNull():
                        snapshot = QLabel(mask)
                        snapshot.setScaledContents(True)
                        snapshot.setPixmap(pixmap)
                        snapshot.setGeometry(mask.rect())
                        snapshot.show()
                        mask_is_snapshot = True
                        snapshot_count += 1
                if not mask_is_snapshot:
                    mask.setStyleSheet("background-color: #0d1117;")
                mask.show()
                try:
                    mask.raise_()
                except Exception:
                    pass
                # Make the mask truly click-through at the Win32 level.
                # Qt's WA_TransparentForMouseEvents only affects Qt's internal routing;
                # on Windows 11 the OS still considers topmost windows as capturing input.
                # WS_EX_TRANSPARENT | WS_EX_LAYERED tells Windows to pass all mouse
                # events through to whatever is behind the mask.
                try:
                    import ctypes
                    import ctypes.wintypes as wintypes
                    _user32 = ctypes.windll.user32
                    _hwnd = wintypes.HWND(int(mask.winId()))
                    GWL_EXSTYLE = -20
                    WS_EX_LAYERED = 0x00080000
                    WS_EX_TRANSPARENT = 0x00000020
                    _get = getattr(_user32, "GetWindowLongPtrW", None) or _user32.GetWindowLongW
                    _set = getattr(_user32, "SetWindowLongPtrW", None) or _user32.SetWindowLongW
                    _ex = int(_get(_hwnd, GWL_EXSTYLE))
                    _set(_hwnd, GWL_EXSTYLE, _ex | WS_EX_LAYERED | WS_EX_TRANSPARENT)
                except Exception:
                    pass
                # Whitelist mask HWND so WinEvent hook doesn't hide it
                try:
                    _suppress_known_ok.add(int(mask.winId()))
                except Exception:
                    pass
                startup_masks.append(mask)
            try:
                app.processEvents(QtCore.QEventLoop.ProcessEventsFlag.AllEvents, 50)
            except Exception:
                pass
            mask_mode_effective = "snapshot" if snapshot_count == len(startup_masks) and startup_masks else "solid"
            _boot_log(f"startup masks shown count={len(startup_masks)} mode={mask_mode_effective}")
        except Exception:
            startup_masks = []

    if splash is not None:
        try:
            splash.set_status("Loading modules…")
        except Exception:
            pass

    # --- Deferred heavy imports (after splash is visible) ---
    # Run imports in a background thread so the Qt event loop stays alive
    # and the splash spinner keeps animating during the ~2-3s import time.
    _import_result: dict = {}
    _import_done = False

    def _bg_import():
        nonlocal _import_done
        try:
            from app.gui.app_icon import find_primary_icon_file as _fpi, load_app_icon as _lai  # noqa: E402
            from app.gui.main_window import MainWindow as _MW  # noqa: E402
            _import_result["find_primary_icon_file"] = _fpi
            _import_result["load_app_icon"] = _lai
            _import_result["MainWindow"] = _MW
        except Exception as exc:
            _import_result["error"] = exc
        _import_done = True

    import threading
    _import_thread = threading.Thread(target=_bg_import, daemon=True)
    _import_thread.start()
    while not _import_done:
        try:
            app.processEvents(QtCore.QEventLoop.ProcessEventsFlag.AllEvents, 50)
        except Exception:
            pass
        _import_thread.join(0.05)

    if "error" in _import_result:
        raise _import_result["error"]
    find_primary_icon_file = _import_result["find_primary_icon_file"]
    load_app_icon = _import_result["load_app_icon"]
    MainWindow = _import_result["MainWindow"]

    if splash is not None:
        try:
            splash.set_status("Loading icons…")
        except Exception:
            pass

    icon = QtGui.QIcon()
    disable_app_icon = _env_flag("BOT_DISABLE_APP_ICON") and not force_app_icon
    if not disable_app_icon:
        try:
            icon = load_app_icon()
        except Exception:
            icon = QtGui.QIcon()
    if (force_app_icon or not disable_app_icon) and icon.isNull():
        try:
            fallback_path = find_primary_icon_file()
        except Exception:
            fallback_path = None
        if fallback_path and fallback_path.is_file():
            try:
                icon = QtGui.QIcon(str(fallback_path))
            except Exception:
                icon = QtGui.QIcon()
        if not icon.isNull():
            try:
                app.setWindowIcon(icon)
                QtGui.QGuiApplication.setWindowIcon(icon)
            except Exception:
                pass

    if splash is not None:
        try:
            splash.set_status("Initializing interface…")
        except Exception:
            pass

    win = MainWindow()
    _boot_log("MainWindow created")
    try:
        win.setAttribute(QtCore.Qt.WidgetAttribute.WA_DeleteOnClose, False)
    except Exception:
        pass
    if not icon.isNull():
        try:
            win.setWindowIcon(icon)
        except Exception:
            pass
    apply_native_icon_after_show = sys.platform == "win32" and (force_app_icon or _env_flag("BOT_ENABLE_NATIVE_ICON"))
    force_taskbar_visibility = _env_flag("BOT_FORCE_TASKBAR_VISIBILITY")

    if sys.platform == "win32" and not disable_taskbar:
        icon_path = _resolve_taskbar_icon_path()
        relaunch_cmd = build_relaunch_command(Path(__file__))
        if not _env_flag("BOT_DISABLE_START_MENU_SHORTCUT"):
            try:
                ensure_start_menu_shortcut(
                    app_id=APP_USER_MODEL_ID,
                    display_name=APP_DISPLAY_NAME,
                    target_path=sys.executable,
                    arguments=_format_shortcut_args(Path(__file__)),
                    icon_path=icon_path,
                    working_dir=Path(__file__).resolve().parent,
                    relaunch_command=relaunch_cmd,
                )
            except Exception:
                pass
        try:
            taskbar_delay = int(os.environ.get("BOT_TASKBAR_METADATA_DELAY_MS") or 0)
        except Exception:
            taskbar_delay = 0
        taskbar_delay = max(0, min(taskbar_delay, 5000))

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
                display_name=APP_DISPLAY_NAME,
                icon_path=icon_path,
                relaunch_command=relaunch_cmd,
            )
            if force_taskbar_visibility:
                try:
                    ensure_taskbar_visible(win)
                except Exception:
                    pass
            if not success and attempts > 1:
                QtCore.QTimer.singleShot(250, lambda: _apply_taskbar(attempts - 1))

        QtCore.QTimer.singleShot(taskbar_delay, _apply_taskbar)

    try:
        startup_reveal_ms = int(os.environ.get("BOT_STARTUP_REVEAL_DELAY_MS") or 0)
    except Exception:
        startup_reveal_ms = 0
    startup_reveal_ms = max(0, min(startup_reveal_ms, 5000))
    startup_reveal_armed = False
    if sys.platform == "win32" and startup_reveal_ms > 0:
        try:
            win.setWindowOpacity(0.0)
            startup_reveal_armed = True
        except Exception:
            startup_reveal_armed = False

    if sys.platform == "win32":
        try:
            win.setWindowState(win.windowState() | QtCore.Qt.WindowState.WindowMaximized)
        except Exception:
            pass
        win.show()
    else:
        win.showMaximized()
    _boot_log("MainWindow shown")
    _suppress_stop = True  # stop transient window suppression thread
    if splash is not None:
        try:
            splash.close()
            _boot_log("splash screen closed")
        except Exception:
            pass
        splash = None
    try:
        win.winId()
    except Exception:
        pass
    mask_unmask_deadline = time.monotonic() + 4.0

    def _main_window_ready_for_unmask() -> bool:
        try:
            if not win.isVisible():
                return False
        except Exception:
            return False
        try:
            if win.windowState() & QtCore.Qt.WindowState.WindowMinimized:
                return False
        except Exception:
            pass
        try:
            handle = win.windowHandle()
        except Exception:
            handle = None
        if handle is not None:
            try:
                if hasattr(handle, "isExposed") and not handle.isExposed():
                    return False
            except Exception:
                pass
        return True

    def _try_hide_startup_mask() -> None:
        nonlocal startup_masks
        if not startup_masks:
            return
        if not _main_window_ready_for_unmask() and time.monotonic() < mask_unmask_deadline:
            QtCore.QTimer.singleShot(80, _try_hide_startup_mask)
            return
        for mask in list(startup_masks):
            try:
                mask.hide()
            except Exception:
                pass
            try:
                mask.deleteLater()
            except Exception:
                pass
        startup_masks = []
        _boot_log("startup masks hidden")

    if startup_reveal_armed:

        def _reveal_main_window() -> None:
            try:
                win.setWindowOpacity(1.0)
            except Exception:
                pass
            try:
                if not win.isVisible():
                    if sys.platform == "win32":
                        win.show()
                    else:
                        win.showMaximized()
            except Exception:
                pass
            try:
                win.raise_()
                win.activateWindow()
            except Exception:
                pass
            _try_hide_startup_mask()

        QtCore.QTimer.singleShot(startup_reveal_ms, _reveal_main_window)
        if startup_masks:
            QtCore.QTimer.singleShot(max(startup_mask_hide_ms, startup_reveal_ms + 300), _try_hide_startup_mask)
    elif startup_masks:
        QtCore.QTimer.singleShot(startup_mask_hide_ms or 1300, _try_hide_startup_mask)
    # Safety valve: startup window hooks help suppress flashes during creation, but
    # keeping them active too long can make some Windows setups feel unresponsive.
    if sys.platform == "win32":
        try:
            hook_auto_uninstall_ms = int(os.environ.get("BOT_STARTUP_WINDOW_HOOK_AUTO_UNINSTALL_MS") or 900)
        except Exception:
            hook_auto_uninstall_ms = 900
        hook_auto_uninstall_ms = max(0, min(hook_auto_uninstall_ms, 5000))
        if hook_auto_uninstall_ms > 0:
            QtCore.QTimer.singleShot(hook_auto_uninstall_ms, _uninstall_startup_window_suppression)
            QtCore.QTimer.singleShot(hook_auto_uninstall_ms, _uninstall_cbt_startup_window_suppression)
    if apply_native_icon_after_show:
        QtCore.QTimer.singleShot(0, lambda: _set_native_window_icon(win))
    if sys.platform == "win32" and force_app_icon:
        QtCore.QTimer.singleShot(0, lambda: _apply_qt_icon(app, win))
    if sys.platform == "win32":
        if disable_app_icon:
            if force_app_icon or _env_flag("BOT_ENABLE_NATIVE_ICON"):
                try:
                    native_delay = int(os.environ.get("BOT_NATIVE_ICON_DELAY_MS") or 0)
                except Exception:
                    native_delay = 0
                if native_delay > 0:
                    QtCore.QTimer.singleShot(native_delay, lambda: _set_native_window_icon(win))
                else:
                    _set_native_window_icon(win)
            if force_app_icon or _env_flag("BOT_ENABLE_DELAYED_QT_ICON"):
                try:
                    delayed_ms = int(os.environ.get("BOT_DELAYED_APP_ICON_MS") or 800)
                except Exception:
                    delayed_ms = 800
                delayed_ms = max(0, min(delayed_ms, 5000))
                QtCore.QTimer.singleShot(delayed_ms, lambda: _apply_qt_icon(app, win))
        _schedule_icon_enforcer(app, win)
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
                            or getattr(win, "_webengine_close_guard_active", False)
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
        def __init__(self, app_instance):
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
    if sys.platform == "win32" and not disable_taskbar:
        try:
            controller_ms_raw = int(os.environ.get("BOT_TASKBAR_ENSURE_MS") or 0)
        except Exception:
            controller_ms_raw = 0
        try:
            interval_ms = int(os.environ.get("BOT_TASKBAR_ENSURE_INTERVAL_MS") or 250)
        except Exception:
            interval_ms = 250
        try:
            start_delay_ms = int(os.environ.get("BOT_TASKBAR_ENSURE_START_DELAY_MS") or 1200)
        except Exception:
            start_delay_ms = 1200
        if controller_ms_raw > 0:
            controller_ms = max(1000, min(controller_ms_raw, 30000))
            interval_ms = max(100, min(interval_ms, 2000))
            start_delay_ms = max(0, min(start_delay_ms, 5000))
            start_ts = time.monotonic()

            def _tick_taskbar() -> None:
                if force_taskbar_visibility:
                    try:
                        ensure_taskbar_visible(win)
                    except Exception:
                        pass
                try:
                    apply_taskbar_metadata(
                        win,
                        app_id=APP_USER_MODEL_ID,
                        display_name=APP_DISPLAY_NAME,
                        icon_path=icon_path,
                        relaunch_command=relaunch_cmd,
                    )
                except Exception:
                    pass
                if (time.monotonic() - start_ts) * 1000.0 < controller_ms:
                    QtCore.QTimer.singleShot(interval_ms, _tick_taskbar)

            QtCore.QTimer.singleShot(start_delay_ms, _tick_taskbar)

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
    _boot_log("ready file handled")

    try:
        suppress_ms = int(os.environ.get("BOT_STARTUP_WINDOW_SUPPRESS_DURATION_MS") or 8000)
    except Exception:
        suppress_ms = 8000
    QtCore.QTimer.singleShot(max(800, suppress_ms), _uninstall_startup_window_suppression)

    try:
        cbt_ms = int(os.environ.get("BOT_CBT_STARTUP_WINDOW_SUPPRESS_DURATION_MS") or 2500)
    except Exception:
        cbt_ms = 2500
    QtCore.QTimer.singleShot(max(250, min(30000, cbt_ms)), _uninstall_cbt_startup_window_suppression)

    try:
        auto_exit_ms = int(os.environ.get("BOT_AUTO_EXIT_MS") or 0)
    except Exception:
        auto_exit_ms = 0
    allow_auto_exit = str(os.environ.get("BOT_ALLOW_AUTO_EXIT", "")).strip().lower() in {"1", "true", "yes", "on"}
    if auto_exit_ms > 0 and allow_auto_exit:
        QtCore.QTimer.singleShot(auto_exit_ms, app.quit)

    _boot_log("entering event loop")
    return app.exec()


if __name__ == "__main__":
    raise SystemExit(_run_entrypoint())
