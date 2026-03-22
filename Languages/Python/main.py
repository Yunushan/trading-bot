"""
Trading Bot desktop entrypoint.

This module is intentionally verbose because it is the first execution layer for
the Python app and handles platform quirks before the main GUI is created.

Startup responsibilities, in order:
1. Establish Windows taskbar identity (AppUserModelID + display name).
2. Ensure project paths are importable when launched from direct file execution.
3. Apply safe subprocess defaults to avoid transient console popups on Windows.
4. Sanitize high-risk QtWebEngine CLI arguments.
5. Configure startup suppression safeguards to reduce helper-window flicker.
6. Resolve startup mode (`starter` vs `direct`) and dispatch into `main()`.

Environment-variable behavior is implemented as "opt-in where risky, safe
defaults where possible" so production launches remain stable on Windows 10/11.
"""

import os
import sys
import time
from pathlib import Path

APP_DISPLAY_NAME = str(os.environ.get("BOT_TASKBAR_DISPLAY_NAME") or "Trading Bot").strip() or "Trading Bot"
APP_USER_MODEL_ID = str(os.environ.get("BOT_APP_USER_MODEL_ID") or "com.tradingbot.TradingBot").strip() or "com.tradingbot.TradingBot"
if sys.platform == "win32":
    # These Qt variables improve taskbar grouping consistency when Qt creates
    # helper processes/windows during startup.
    os.environ["QT_WIN_APPID"] = APP_USER_MODEL_ID
    os.environ["QT_QPA_PLATFORM_WINDOWS_USER_MODEL_ID"] = APP_USER_MODEL_ID
    try:
        import ctypes
        ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID(APP_USER_MODEL_ID)
    except Exception:
        pass

# Ensure repo root is importable so shared helpers can be used when launched directly.
# `PROJECT_ROOT` is used by both Python and C++ integration helpers.
# Keep this path stable before importing internal modules so relative imports
# behave the same whether launched from IDE, terminal, or packaged runtime.
PROJECT_ROOT = Path(__file__).resolve().parents[2]
PROJECT_ROOT_STR = str(PROJECT_ROOT)
if PROJECT_ROOT_STR not in sys.path:
    sys.path.insert(0, PROJECT_ROOT_STR)

BINANCE_DIR = Path(__file__).resolve().parent
BINANCE_DIR_STR = str(BINANCE_DIR)
if BINANCE_DIR_STR not in sys.path:
    sys.path.insert(0, BINANCE_DIR_STR)

from app.bootstrap import (
    startup_lifecycle_runtime,
    startup_pre_qt_window_suppression_runtime,
    startup_ui,
    startup_window_suppression_runtime,
)

_configure_startup_window_suppression_defaults = (
    startup_window_suppression_runtime._configure_startup_window_suppression_defaults
)
_install_cbt_startup_window_suppression = (
    startup_window_suppression_runtime._install_cbt_startup_window_suppression
)
_uninstall_cbt_startup_window_suppression = (
    startup_window_suppression_runtime._uninstall_cbt_startup_window_suppression
)
_install_qt_warning_filter = startup_window_suppression_runtime._install_qt_warning_filter
_start_pre_qt_winevent_suppression = (
    startup_pre_qt_window_suppression_runtime._start_pre_qt_winevent_suppression
)


def _normalized_env_path_key(path_value: str) -> str:
    text = str(path_value or "").strip().strip('"').strip("'")
    if not text:
        return ""
    try:
        resolved = Path(text).expanduser().resolve()
        text = str(resolved)
    except Exception:
        pass
    return os.path.normcase(os.path.normpath(text))


def _sanitize_inherited_cpp_qt_env() -> None:
    """Drop C++ Qt runtime hints before Python/PyQt imports run."""
    cpp_exe_dir = str(os.environ.get("TB_CPP_EXE_DIR") or "").strip()
    cpp_launch_path = str(os.environ.get("TB_CPP_LAUNCH_PATH") or "").strip()
    if not cpp_exe_dir and not cpp_launch_path:
        return

    for key in (
        "QT_PLUGIN_PATH",
        "QT_QPA_PLATFORM_PLUGIN_PATH",
        "QML_IMPORT_PATH",
        "QML2_IMPORT_PATH",
        "QT_CONF_PATH",
        "QT_QPA_FONTDIR",
        "QT_QPA_PLATFORMTHEME",
        "QTWEBENGINEPROCESS_PATH",
        "QTWEBENGINE_RESOURCES_PATH",
        "QTWEBENGINE_LOCALES_PATH",
    ):
        os.environ.pop(key, None)

    blocked: set[str] = set()
    cpp_dir_key = _normalized_env_path_key(cpp_exe_dir)
    if cpp_dir_key:
        blocked.add(cpp_dir_key)
        blocked.add(_normalized_env_path_key(str(Path(cpp_exe_dir) / "platforms")))
        blocked.add(_normalized_env_path_key(str(Path(cpp_exe_dir) / "styles")))
        blocked.add(_normalized_env_path_key(str(Path(cpp_exe_dir) / "imageformats")))
    for token in str(cpp_launch_path or "").split(os.pathsep):
        key = _normalized_env_path_key(token)
        if key:
            blocked.add(key)

    path_tokens = str(os.environ.get("PATH", "") or "").split(os.pathsep)
    filtered_tokens: list[str] = []
    seen: set[str] = set()
    prefix = f"{cpp_dir_key}{os.sep}" if cpp_dir_key else ""
    for raw_token in path_tokens:
        token = str(raw_token or "").strip()
        if not token:
            continue
        key = _normalized_env_path_key(token)
        if not key:
            continue
        if key in blocked or (prefix and key.startswith(prefix)):
            continue
        if key in seen:
            continue
        seen.add(key)
        filtered_tokens.append(token)
    if filtered_tokens:
        os.environ["PATH"] = os.pathsep.join(filtered_tokens)

    os.environ["TB_CPP_QT_ENV_SANITIZED"] = "1"


_sanitize_inherited_cpp_qt_env()


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


def _install_startup_window_suppression() -> None:
    return startup_window_suppression_runtime._install_startup_window_suppression()


def _uninstall_startup_window_suppression() -> None:
    return startup_window_suppression_runtime._uninstall_startup_window_suppression()






_apply_qt_icon = startup_ui._apply_qt_icon
_bind_background_process_exit = startup_lifecycle_runtime._bind_background_process_exit
_close_native_startup_cover = startup_lifecycle_runtime._close_native_startup_cover
_format_shortcut_args = startup_ui._format_shortcut_args
_install_background_restore_guard = startup_lifecycle_runtime._install_background_restore_guard
_install_startup_input_unblocker = startup_lifecycle_runtime._install_startup_input_unblocker
_make_splash_widget_class = startup_ui._make_splash_widget_class
_resolve_taskbar_icon_path = startup_ui._resolve_taskbar_icon_path
_schedule_icon_enforcer = startup_ui._schedule_icon_enforcer
_set_native_window_icon = startup_ui._set_native_window_icon
_show_native_startup_cover = startup_ui._show_native_startup_cover
_SplashScreen = startup_ui._SplashScreen






def main() -> int:
    _configure_startup_window_suppression_defaults()
    native_startup_cover = None
    if sys.platform == "win32":
        try:
            native_startup_cover = _show_native_startup_cover()
        except Exception:
            native_startup_cover = None
        if native_startup_cover is not None:
            _boot_log("native startup cover shown")
    if _env_flag("BOT_ENABLE_CBT_STARTUP_WINDOW_SUPPRESS"):
        _install_cbt_startup_window_suppression()
    if _env_flag("BOT_DISABLE_STARTUP_WINDOW_HOOKS"):
        _boot_log("startup window hooks disabled")
    else:
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
        f"{os.environ.get('BOT_STARTUP_MASK_MODE', '')!r} "
        "BOT_NATIVE_STARTUP_COVER_ENABLED="
        f"{os.environ.get('BOT_NATIVE_STARTUP_COVER_ENABLED', '')!r}"
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

    # --- Suppress transient startup windows via WinEvent hook on dedicated thread ---
    # Qt/QtWebEngine create small helper windows during init that flash briefly.
    # We install a WinEvent hook (EVENT_OBJECT_SHOW) on a DEDICATED background thread
    # with its own Win32 message loop BEFORE QApplication is created, because Qt may
    # flash tiny helper windows during app initialization. A threading.Event ensures
    # the hook is active before we proceed.
    pre_qt_window_suppressor = _start_pre_qt_winevent_suppression(ready_timeout_s=0.5)
    if sys.platform == "win32":
        _boot_log("transient window suppression hook ready")
    app = QApplication(sys.argv)
    app.setApplicationName(APP_DISPLAY_NAME)
    app.setApplicationDisplayName(APP_DISPLAY_NAME)
    app._exiting = False  # type: ignore[attr-defined]
    _bind_background_process_exit(
        app,
        uninstall_startup_window_suppression=_uninstall_startup_window_suppression,
        uninstall_cbt_startup_window_suppression=_uninstall_cbt_startup_window_suppression,
    )
    try:
        QtGui.QGuiApplication.setDesktopFileName(APP_USER_MODEL_ID)
    except Exception:
        pass
    if sys.platform == "win32":
        try:
            app.setQuitOnLastWindowClosed(False)
        except Exception:
            pass

    startup_masks: list[QWidget] = []
    startup_mask_hide_ms = 0
    startup_mask_mode = ""
    if sys.platform == "win32" and _env_flag("BOT_STARTUP_MASK_ENABLED"):
        try:
            startup_mask_hide_ms = int(os.environ.get("BOT_STARTUP_MASK_HIDE_MS") or 500)
        except Exception:
            startup_mask_hide_ms = 500
        startup_mask_mode = str(os.environ.get("BOT_STARTUP_MASK_MODE") or "snapshot").strip().lower()
        startup_mask_scope = str(os.environ.get("BOT_STARTUP_MASK_SCOPE") or "all").strip().lower()
        startup_mask_hide_ms = max(100, min(startup_mask_hide_ms, 5000))
        try:
            screens: list = []
            all_screens = list(QtGui.QGuiApplication.screens() or [])
            if startup_mask_scope in {"primary", "main"}:
                primary = QtGui.QGuiApplication.primaryScreen()
                if primary is not None:
                    screens = [primary]
            elif startup_mask_scope in {"cursor", "active"}:
                try:
                    cursor_pos = QtGui.QCursor.pos()
                except Exception:
                    cursor_pos = None
                chosen = QtGui.QGuiApplication.screenAt(cursor_pos) if cursor_pos is not None else None
                if chosen is not None:
                    screens = [chosen]
            if not screens:
                screens = all_screens
            if not screens:
                primary = QtGui.QGuiApplication.primaryScreen()
                if primary is not None:
                    screens = [primary]
            snapshot_count = 0
            for screen in screens:
                mask = QWidget(
                    None,
                    QtCore.Qt.WindowType.SplashScreen
                    | QtCore.Qt.WindowType.FramelessWindowHint
                    | QtCore.Qt.WindowType.WindowStaysOnTopHint
                    | QtCore.Qt.WindowType.NoDropShadowWindowHint,
                )
                mask.setAttribute(QtCore.Qt.WidgetAttribute.WA_ShowWithoutActivating, True)
                mask.setAttribute(QtCore.Qt.WidgetAttribute.WA_TransparentForMouseEvents, True)
                try:
                    mask.setWindowTitle("")
                except Exception:
                    pass
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
                    pre_qt_window_suppressor.add_known_ok_hwnd(int(mask.winId()))
                except Exception:
                    pass
                startup_masks.append(mask)
            try:
                app.processEvents(QtCore.QEventLoop.ProcessEventsFlag.AllEvents, 50)
            except Exception:
                pass
            mask_mode_effective = "snapshot" if snapshot_count == len(startup_masks) and startup_masks else "solid"
            _boot_log(
                f"startup masks shown count={len(startup_masks)} mode={mask_mode_effective} scope={startup_mask_scope or 'all'}"
            )
        except Exception:
            startup_masks = []

    # --- Show loading splash screen ---
    global _SplashWidget
    _SplashWidget = _make_splash_widget_class(QWidget, QtCore, QtGui)
    splash = None
    splash_host_widget = startup_masks[0] if startup_masks else None
    if not _env_flag("BOT_DISABLE_SPLASH"):
        try:
            splash = _SplashScreen(app, QtCore, QtGui, QWidget, host_widget=splash_host_widget)
            _boot_log("splash screen shown")
            # Whitelist splash HWND so the hook doesn't hide it
            if splash._widget is not None and splash_host_widget is None:
                try:
                    pre_qt_window_suppressor.add_known_ok_hwnd(int(splash._widget.winId()))
                except Exception:
                    pass
            if splash._widget is not None and startup_masks:
                try:
                    splash._widget.raise_()
                except Exception:
                    pass
                try:
                    app.processEvents(QtCore.QEventLoop.ProcessEventsFlag.AllEvents, 25)
                except Exception:
                    pass
        except Exception:
            splash = None

    if splash is not None or startup_masks:
        native_startup_cover = _close_native_startup_cover(native_startup_cover, boot_log=_boot_log)

    if splash is not None:
        try:
            splash.set_status("Loading modulesâ€¦")
        except Exception:
            pass

    startup_overlay_raise_timer = None
    startup_main_window_shown = False
    startup_user_switched_away = False

    def _startup_app_is_active() -> bool:
        try:
            state = app.applicationState()
        except Exception:
            return True
        return state == QtCore.Qt.ApplicationState.ApplicationActive

    def _stop_startup_overlay_raise_timer() -> None:
        nonlocal startup_overlay_raise_timer
        if startup_overlay_raise_timer is None:
            return
        try:
            startup_overlay_raise_timer.stop()
        except Exception:
            pass
        try:
            startup_overlay_raise_timer.deleteLater()
        except Exception:
            pass
        startup_overlay_raise_timer = None

    def _release_startup_overlays(*, reason: str = "", mark_user_switched: bool = False) -> None:
        nonlocal splash, startup_masks, startup_user_switched_away
        if mark_user_switched:
            startup_user_switched_away = True
        _stop_startup_overlay_raise_timer()
        if splash is not None:
            try:
                splash.close()
            except Exception:
                pass
            splash = None
        if startup_masks:
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
        if reason:
            _boot_log(f"startup overlays released ({reason})")

    def _raise_startup_overlays() -> None:
        if startup_main_window_shown and not _startup_app_is_active():
            _release_startup_overlays(reason="app-inactive", mark_user_switched=True)
            return
        for mask in list(startup_masks):
            try:
                mask.raise_()
            except Exception:
                pass
        if splash is not None and getattr(splash, "_widget", None) is not None:
            try:
                splash._widget.raise_()
            except Exception:
                pass

    if sys.platform == "win32" and startup_masks:
        try:
            startup_overlay_raise_timer = QtCore.QTimer(app)
            startup_overlay_raise_timer.setInterval(15)
            startup_overlay_raise_timer.timeout.connect(_raise_startup_overlays)
            startup_overlay_raise_timer.start()
            _raise_startup_overlays()
        except Exception:
            startup_overlay_raise_timer = None

    # --- Deferred heavy imports (after splash is visible) ---
    # Import Qt-heavy GUI modules on the main thread. Importing MainWindow from
    # a worker thread can deadlock/stall on Windows + PyQt startup, leaving the
    # main thread stuck polling join() until the user interrupts the process.
    try:
        app.processEvents(QtCore.QEventLoop.ProcessEventsFlag.AllEvents, 50)
    except Exception:
        pass
    from app.gui.shared.app_icon import find_primary_icon_file, load_app_icon  # noqa: E402
    from app.gui.main_window import MainWindow  # noqa: E402

    if splash is not None:
        try:
            splash.set_status("Loading iconsâ€¦")
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
            splash.set_status("Initializing interfaceâ€¦")
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
    startup_reveal_armed = bool(sys.platform == "win32" and startup_reveal_ms > 0)

    def _show_main_window(*, activate: bool) -> None:
        nonlocal native_startup_cover, startup_main_window_shown
        show_without_activating = not activate
        if show_without_activating:
            try:
                win.setAttribute(QtCore.Qt.WidgetAttribute.WA_ShowWithoutActivating, True)
            except Exception:
                pass
        try:
            if sys.platform == "win32":
                try:
                    win.setWindowState(win.windowState() | QtCore.Qt.WindowState.WindowMaximized)
                except Exception:
                    pass
                try:
                    win.showMaximized()
                except Exception:
                    win.show()
            else:
                win.show()
        finally:
            if show_without_activating:
                try:
                    QtCore.QTimer.singleShot(
                        0,
                        lambda: win.setAttribute(QtCore.Qt.WidgetAttribute.WA_ShowWithoutActivating, False),
                    )
                except Exception:
                    pass
        startup_main_window_shown = True
        _boot_log("MainWindow shown")
        native_startup_cover = _close_native_startup_cover(native_startup_cover, boot_log=_boot_log)

    if not startup_reveal_armed:
        _show_main_window(activate=True)
    else:
        _boot_log("MainWindow show deferred for startup reveal")
    try:
        main_hwnd = int(win.winId())
    except Exception:
        main_hwnd = 0
    if main_hwnd:
        pre_qt_window_suppressor.add_known_ok_hwnd(main_hwnd)
    mask_unmask_deadline = time.monotonic() + 4.0
    startup_transition_deadline = time.monotonic() + 4.0
    startup_transition_done = False

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

    def _finish_startup_transition() -> None:
        nonlocal splash, startup_transition_done
        if startup_transition_done:
            return
        if not _main_window_ready_for_unmask() and time.monotonic() < startup_transition_deadline:
            QtCore.QTimer.singleShot(60, _finish_startup_transition)
            return
        startup_transition_done = True
        _stop_startup_overlay_raise_timer()
        pre_qt_window_suppressor.stop()
        if splash is not None:
            try:
                splash.close()
                _boot_log("splash screen closed")
            except Exception:
                pass
            splash = None
        _try_hide_startup_mask()

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
            activate_now = (not startup_user_switched_away) and _startup_app_is_active()
            try:
                if not win.isVisible():
                    _show_main_window(activate=activate_now)
            except Exception:
                pass
            try:
                if activate_now:
                    win.raise_()
                    win.activateWindow()
            except Exception:
                pass
            _finish_startup_transition()

        QtCore.QTimer.singleShot(startup_reveal_ms, _reveal_main_window)
        if startup_masks:
            QtCore.QTimer.singleShot(max(startup_mask_hide_ms, startup_reveal_ms + 300), _try_hide_startup_mask)
    elif startup_masks:
        QtCore.QTimer.singleShot(startup_mask_hide_ms or 1300, _try_hide_startup_mask)
        QtCore.QTimer.singleShot(0, _finish_startup_transition)
    else:
        QtCore.QTimer.singleShot(0, _finish_startup_transition)
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
                            win.showMaximized()
                            win.raise_()
                            win.activateWindow()
                    except Exception:
                        pass

                timer.timeout.connect(_tv_watchdog)
                timer.start()
                app._tradingview_app_watchdog = timer  # type: ignore[attr-defined]
            except Exception:
                pass
    _install_background_restore_guard(app, win, QtCore, QWidget)
    _install_startup_input_unblocker(
        app,
        QtCore,
        uninstall_startup_window_suppression=_uninstall_startup_window_suppression,
        uninstall_cbt_startup_window_suppression=_uninstall_cbt_startup_window_suppression,
    )
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
    exit_code = int(app.exec())
    try:
        _uninstall_startup_window_suppression()
    except Exception:
        pass
    try:
        _uninstall_cbt_startup_window_suppression()
    except Exception:
        pass
    if sys.platform == "win32":
        try:
            sys.stdout.flush()
        except Exception:
            pass
        try:
            sys.stderr.flush()
        except Exception:
            pass
        os._exit(exit_code)
    return exit_code


if __name__ == "__main__":
    raise SystemExit(_run_entrypoint())
