"""
Trading Bot desktop bootstrap implementation.

This module holds the real desktop startup flow. The public launcher remains
``apps/desktop-pyqt/main.py`` while ``Languages/Python/main.py`` remains as the
compatibility launcher so end-user commands, IDE run configurations, shortcuts,
and relaunch metadata stay stable.

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
import importlib
import subprocess
import sys
from pathlib import Path
from types import SimpleNamespace

APP_DISPLAY_NAME = str(os.environ.get("BOT_TASKBAR_DISPLAY_NAME") or "Trading Bot").strip() or "Trading Bot"
_DEFAULT_APP_USER_MODEL_ID = "com.tradingbot.TradingBot"
if sys.platform == "win32" and not getattr(sys, "frozen", False):
    _DEFAULT_APP_USER_MODEL_ID = "com.tradingbot.TradingBot.PythonSource"
APP_USER_MODEL_ID = str(os.environ.get("BOT_APP_USER_MODEL_ID") or _DEFAULT_APP_USER_MODEL_ID).strip() or _DEFAULT_APP_USER_MODEL_ID
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
_THIS_FILE = Path(__file__).resolve()
PROJECT_ROOT = _THIS_FILE.parents[5]
PROJECT_ROOT_STR = str(PROJECT_ROOT)
if PROJECT_ROOT_STR not in sys.path:
    sys.path.insert(0, PROJECT_ROOT_STR)

PYTHON_WORKSPACE_DIR = PROJECT_ROOT / "Languages" / "Python"
PYTHON_WORKSPACE_DIR_STR = str(PYTHON_WORKSPACE_DIR)
if PYTHON_WORKSPACE_DIR_STR not in sys.path:
    sys.path.insert(0, PYTHON_WORKSPACE_DIR_STR)

PUBLIC_ENTRYPOINT_PATH = (PYTHON_WORKSPACE_DIR / "main.py").resolve()
_SplashWidget = None


def _load_internal_module(name: str):
    return importlib.import_module(name)


_windows_taskbar_metadata_runtime = _load_internal_module(
    "app.platform.windows_taskbar_metadata_runtime"
)
resolve_relaunch_arguments = _windows_taskbar_metadata_runtime.resolve_relaunch_arguments
resolve_relaunch_executable = _windows_taskbar_metadata_runtime.resolve_relaunch_executable


def _maybe_relaunch_via_pythonw() -> None:
    if sys.platform != "win32" or getattr(sys, "frozen", False):
        return
    if str(os.environ.get("BOT_DISABLE_PYTHONW_RELAUNCH") or "").strip().lower() in {"1", "true", "yes", "on"}:
        return
    if str(os.environ.get("BOT_PYTHONW_RELAUNCHED") or "").strip().lower() in {"1", "true", "yes", "on"}:
        return
    try:
        if sys.gettrace() is not None:
            return
    except Exception:
        pass
    try:
        current_exe = Path(sys.executable).resolve()
    except Exception:
        return
    gui_host = resolve_relaunch_executable(PUBLIC_ENTRYPOINT_PATH)
    gui_args = resolve_relaunch_arguments(PUBLIC_ENTRYPOINT_PATH)
    if gui_host is None:
        return
    if not gui_args:
        return
    try:
        gui_host = gui_host.resolve()
    except Exception:
        pass
    if gui_host == current_exe:
        return
    env = os.environ.copy()
    env["BOT_PYTHONW_RELAUNCHED"] = "1"
    args = [str(gui_host), *gui_args, *sys.argv[1:]]
    shortcut_path = None
    try:
        from app.bootstrap.startup_icon_runtime import _resolve_taskbar_icon_path
        from app.platform.windows_taskbar import build_relaunch_command, ensure_start_menu_shortcut

        shortcut_name = f"{APP_DISPLAY_NAME} Python Source"
        shortcut_path = ensure_start_menu_shortcut(
            app_id=APP_USER_MODEL_ID,
            display_name=APP_DISPLAY_NAME,
            shortcut_name=shortcut_name,
            target_path=gui_host,
            arguments=subprocess.list2cmdline(gui_args),
            icon_path=_resolve_taskbar_icon_path(),
            working_dir=PYTHON_WORKSPACE_DIR,
            relaunch_command=build_relaunch_command(PUBLIC_ENTRYPOINT_PATH),
        )
    except Exception:
        shortcut_path = None
    if shortcut_path is not None:
        try:
            os.startfile(str(shortcut_path))
            raise SystemExit(0)
        except Exception:
            pass
    try:
        subprocess.Popen(
            args,
            cwd=str(PYTHON_WORKSPACE_DIR),
            env=env,
            close_fds=True,
        )
    except Exception:
        return
    raise SystemExit(0)


_maybe_relaunch_via_pythonw()


def _load_startup_runtime_modules() -> SimpleNamespace:
    return SimpleNamespace(
        startup_app_runtime=_load_internal_module("app.bootstrap.startup_app_runtime"),
        startup_cover_runtime=_load_internal_module("app.bootstrap.startup_cover_runtime"),
        startup_icon_runtime=_load_internal_module("app.bootstrap.startup_icon_runtime"),
        startup_lifecycle_runtime=_load_internal_module("app.bootstrap.startup_lifecycle_runtime"),
        startup_post_window_runtime=_load_internal_module("app.bootstrap.startup_post_window_runtime"),
        startup_presentation_runtime=_load_internal_module("app.bootstrap.startup_presentation_runtime"),
        startup_pre_qt_window_suppression_runtime=_load_internal_module(
            "app.bootstrap.startup_pre_qt_window_suppression_runtime"
        ),
        startup_splash_ui=_load_internal_module("app.bootstrap.startup_splash_ui"),
        startup_window_suppression_runtime=_load_internal_module(
            "app.bootstrap.startup_window_suppression_runtime"
        ),
    )


_startup_modules = _load_startup_runtime_modules()
startup_app_runtime = _startup_modules.startup_app_runtime
startup_cover_runtime = _startup_modules.startup_cover_runtime
startup_icon_runtime = _startup_modules.startup_icon_runtime
startup_lifecycle_runtime = _startup_modules.startup_lifecycle_runtime
startup_post_window_runtime = _startup_modules.startup_post_window_runtime
startup_presentation_runtime = _startup_modules.startup_presentation_runtime
startup_pre_qt_window_suppression_runtime = (
    _startup_modules.startup_pre_qt_window_suppression_runtime
)
startup_splash_ui = _startup_modules.startup_splash_ui
startup_window_suppression_runtime = _startup_modules.startup_window_suppression_runtime

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

            setattr(subprocess, "Popen", _NoConsolePopen)
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

            setattr(subprocess, "Popen", _patched_popen)

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
    startup_window_suppression_runtime._install_startup_window_suppression()


def _uninstall_startup_window_suppression() -> None:
    startup_window_suppression_runtime._uninstall_startup_window_suppression()






_apply_qt_icon = startup_icon_runtime._apply_qt_icon
_bind_background_process_exit = startup_lifecycle_runtime._bind_background_process_exit
_close_native_startup_cover = startup_lifecycle_runtime._close_native_startup_cover
_create_qt_application = startup_app_runtime._create_qt_application
_format_shortcut_args = startup_icon_runtime._format_shortcut_args
_install_background_restore_guard = startup_lifecycle_runtime._install_background_restore_guard
_install_startup_input_unblocker = startup_lifecycle_runtime._install_startup_input_unblocker
_load_application_icon = startup_app_runtime._load_application_icon
_make_splash_widget_class = startup_splash_ui._make_splash_widget_class
_resolve_taskbar_icon_path = startup_icon_runtime._resolve_taskbar_icon_path
_schedule_icon_enforcer = startup_icon_runtime._schedule_icon_enforcer
_set_native_window_icon = startup_icon_runtime._set_native_window_icon
_show_native_startup_cover = startup_cover_runtime._show_native_startup_cover
_SplashScreen = startup_splash_ui._SplashScreen
_configure_post_window_runtime = startup_post_window_runtime._configure_post_window_runtime
_ensure_taskbar_identity = startup_post_window_runtime._ensure_taskbar_identity
_StartupPresentationController = startup_presentation_runtime._StartupPresentationController






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
    from app.bootstrap import runtime_env  # noqa: E402,F401
    _boot_log("runtime env loaded")

    from PyQt6 import QtCore, QtGui  # noqa: E402
    from PyQt6.QtWidgets import QApplication, QLabel, QWidget  # noqa: E402

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
    _ensure_taskbar_identity(
        disable_taskbar=disable_taskbar,
        app_user_model_id=APP_USER_MODEL_ID,
    )

    # --- Suppress transient startup windows via WinEvent hook on dedicated thread ---
    # Qt/QtWebEngine create small helper windows during init that flash briefly.
    # We install a WinEvent hook (EVENT_OBJECT_SHOW) on a DEDICATED background thread
    # with its own Win32 message loop BEFORE QApplication is created, because Qt may
    # flash tiny helper windows during app initialization. A threading.Event ensures
    # the hook is active before we proceed.
    pre_qt_window_suppressor = _start_pre_qt_winevent_suppression(ready_timeout_s=0.5)
    if sys.platform == "win32":
        _boot_log("transient window suppression hook ready")
    app = _create_qt_application(
        QApplication=QApplication,
        QtCore=QtCore,
        QtGui=QtGui,
        env_flag=_env_flag,
        app_display_name=APP_DISPLAY_NAME,
        app_user_model_id=APP_USER_MODEL_ID,
        bind_background_process_exit=_bind_background_process_exit,
        uninstall_startup_window_suppression=_uninstall_startup_window_suppression,
        uninstall_cbt_startup_window_suppression=_uninstall_cbt_startup_window_suppression,
    )
    global _SplashWidget
    _SplashWidget = _make_splash_widget_class(QWidget, QtCore, QtGui)
    startup_presentation = _StartupPresentationController(
        app=app,
        QtCore=QtCore,
        QtGui=QtGui,
        QLabel=QLabel,
        QWidget=QWidget,
        env_flag=_env_flag,
        boot_log=_boot_log,
        pre_qt_window_suppressor=pre_qt_window_suppressor,
        splash_screen_cls=_SplashScreen,
        close_native_startup_cover=_close_native_startup_cover,
        native_startup_cover=native_startup_cover,
    )
    startup_presentation.set_status("Loading modulesâ€¦")

    # --- Deferred heavy imports (after splash is visible) ---
    # Import Qt-heavy GUI modules on the main thread. Importing MainWindow from
    # a worker thread can deadlock/stall on Windows + PyQt startup, leaving the
    # main thread stuck polling join() until the user interrupts the process.
    try:
        app.processEvents(QtCore.QEventLoop.ProcessEventsFlag.AllEvents, 50)
    except Exception:
        pass
    from app.gui.window_shell import MainWindow  # noqa: E402

    startup_presentation.set_status("Loading iconsâ€¦")
    icon, disable_app_icon = _load_application_icon(
        QtGui=QtGui,
        app=app,
        env_flag=_env_flag,
        force_app_icon=force_app_icon,
    )

    startup_presentation.set_status("Initializing interfaceâ€¦")

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
    if sys.platform == "win32":
        try:
            win.winId()
        except Exception:
            pass
        if force_app_icon or not disable_app_icon or _env_flag("BOT_ENABLE_DELAYED_QT_ICON"):
            try:
                _apply_qt_icon(app, win)
            except Exception:
                pass
        if force_app_icon or _env_flag("BOT_ENABLE_NATIVE_ICON"):
            try:
                _set_native_window_icon(win)
            except Exception:
                pass
        if not disable_taskbar:
            try:
                from app.platform.windows_taskbar import apply_taskbar_metadata, build_relaunch_command

                apply_taskbar_metadata(
                    win,
                    app_id=APP_USER_MODEL_ID,
                    display_name=APP_DISPLAY_NAME,
                    icon_path=_resolve_taskbar_icon_path(),
                    relaunch_command=build_relaunch_command(PUBLIC_ENTRYPOINT_PATH),
                )
            except Exception:
                pass
    startup_presentation.attach_main_window(win)
    _configure_post_window_runtime(
        app=app,
        win=win,
        QtCore=QtCore,
        QWidget=QWidget,
        env_flag=_env_flag,
        script_path=PUBLIC_ENTRYPOINT_PATH,
        app_display_name=APP_DISPLAY_NAME,
        app_user_model_id=APP_USER_MODEL_ID,
        force_app_icon=force_app_icon,
        disable_app_icon=disable_app_icon,
        disable_taskbar=disable_taskbar,
        resolve_taskbar_icon_path=_resolve_taskbar_icon_path,
        format_shortcut_args=_format_shortcut_args,
        set_native_window_icon=_set_native_window_icon,
        apply_qt_icon=_apply_qt_icon,
        schedule_icon_enforcer=_schedule_icon_enforcer,
        install_background_restore_guard=_install_background_restore_guard,
        install_startup_input_unblocker=_install_startup_input_unblocker,
        uninstall_startup_window_suppression=_uninstall_startup_window_suppression,
        uninstall_cbt_startup_window_suppression=_uninstall_cbt_startup_window_suppression,
    )
    _boot_log("ready file handled")

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
