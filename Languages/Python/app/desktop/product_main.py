"""
Canonical importable desktop product entrypoint.
"""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

WORKSPACE_DIR = Path(__file__).resolve().parents[2]
LEGACY_ENTRYPOINT_PATH = WORKSPACE_DIR / "main.py"
LAUNCH_CONTEXT_PATH = LEGACY_ENTRYPOINT_PATH if LEGACY_ENTRYPOINT_PATH.is_file() else Path(__file__).resolve()


def _env_flag(name: str) -> bool:
    return str(os.environ.get(name, "")).strip().lower() in {"1", "true", "yes", "on"}


def _boot_log(message: str) -> None:
    if not _env_flag("BOT_BOOT_LOG"):
        return
    try:
        print(f"[desktop-product] {message}", flush=True)
    except Exception:
        pass


def _maybe_launch_via_shell_shortcut() -> None:
    if sys.platform != "win32" or getattr(sys, "frozen", False):
        _boot_log("skip shell shortcut: unsupported platform or frozen")
        return
    if _env_flag("BOT_DISABLE_PUBLIC_SHELL_SHORTCUT_LAUNCH"):
        _boot_log("skip shell shortcut: disabled by env")
        return
    try:
        if sys.gettrace() is not None:
            _boot_log("skip shell shortcut: debugger detected")
            return
    except Exception:
        pass
    try:
        from app.bootstrap.startup_icon_runtime import _resolve_taskbar_icon_path
        from app.platform.windows_taskbar import build_relaunch_command, ensure_start_menu_shortcut
        from app.platform.windows_taskbar_metadata_runtime import resolve_relaunch_executable
    except Exception:
        _boot_log("skip shell shortcut: failed to import taskbar helpers")
        return

    try:
        current_exe = Path(sys.executable).resolve()
    except Exception:
        return
    gui_host = resolve_relaunch_executable(LAUNCH_CONTEXT_PATH)
    if gui_host is None or not gui_host.exists():
        _boot_log(f"skip shell shortcut: gui host missing {gui_host}")
        return
    if current_exe == gui_host:
        _boot_log("skip shell shortcut: already running under gui host")
        return
    gui_args = ["-m", "app.desktop.bootstrap.main", *sys.argv[1:]]
    try:
        shortcut_path = ensure_start_menu_shortcut(
            app_id="com.tradingbot.TradingBot.PythonSource",
            display_name="Trading Bot",
            shortcut_name="Trading Bot Python Source",
            target_path=gui_host,
            arguments=subprocess.list2cmdline(gui_args),
            icon_path=_resolve_taskbar_icon_path(),
            working_dir=WORKSPACE_DIR,
            relaunch_command=build_relaunch_command(LAUNCH_CONTEXT_PATH),
        )
        _boot_log(f"shell shortcut prepared at {shortcut_path}")
    except Exception as exc:
        _boot_log(f"shell shortcut prepare failed: {exc!r}")
        shortcut_path = None
    if shortcut_path is None:
        return
    try:
        legacy_shortcut = shortcut_path.with_name("Trading Bot.lnk")
        if legacy_shortcut != shortcut_path and legacy_shortcut.exists():
            legacy_shortcut.unlink()
            _boot_log(f"removed legacy shortcut {legacy_shortcut}")
    except Exception as exc:
        _boot_log(f"legacy shortcut cleanup failed: {exc!r}")
    try:
        os.startfile(str(shortcut_path))  # noqa: S606 - shortcut was created for the resolved GUI host.
        _boot_log(f"shell shortcut launched via {shortcut_path}")
    except Exception as exc:
        _boot_log(f"shell shortcut launch failed: {exc!r}")
        return
    raise SystemExit(0)


def _run_packaged_smoke() -> int:
    """Import the packaged desktop/runtime surface without creating a window."""
    from PyQt6 import QtCore, QtWidgets

    from app.entrypoint_contract import DESKTOP_ENTRYPOINT_CONTRACT
    from app.gui.window_shell import MainWindow
    from app.service.runtime import TradingBotService

    if DESKTOP_ENTRYPOINT_CONTRACT.canonical_module != __name__:
        raise RuntimeError("Desktop entrypoint contract does not target this module.")
    if not issubclass(MainWindow, QtWidgets.QWidget):
        raise RuntimeError("Packaged MainWindow is not a Qt widget.")

    service = TradingBotService()
    descriptor = service.describe_runtime().to_dict()
    if descriptor.get("desktop_entrypoint") != DESKTOP_ENTRYPOINT_CONTRACT.canonical_repo_path:
        raise RuntimeError("Service runtime reports a different desktop entrypoint.")
    if not isinstance(service.get_status().to_dict(), dict):
        raise RuntimeError("Service runtime status is unavailable.")

    # Windowed PyInstaller builds intentionally have no stdout stream.
    stdout = getattr(sys, "stdout", None)
    if stdout is not None:
        stdout.write(
            "Trading Bot Python packaged smoke passed "
            f"(PyQt {QtCore.PYQT_VERSION_STR}, Qt {QtCore.QT_VERSION_STR}).\n"
        )
        stdout.flush()
    return 0


def _configure_window_smoke_environment() -> None:
    """Keep the window smoke deterministic and isolated from external services."""
    defaults = {
        "BOT_DISABLE_PUBLIC_SHELL_SHORTCUT_LAUNCH": "1",
        "BOT_DISABLE_PYTHONW_RELAUNCH": "1",
        "BOT_DISABLE_STARTUP_WINDOW_HOOKS": "1",
        "BOT_DISABLE_TASKBAR": "1",
        "BOT_DISABLE_SPLASH": "1",
        "BOT_PREWARM_WEBENGINE": "0",
        "BOT_DISABLE_WEBENGINE_CHARTS": "1",
        "BOT_DISABLE_CHARTS": "1",
        "BOT_DISABLE_TRADINGVIEW": "1",
        "BOT_ENABLE_DESKTOP_SERVICE_API": "0",
        "BOT_OPEN_CODE_TAB": "0",
    }
    for name, value in defaults.items():
        os.environ.setdefault(name, value)


def _run_window_smoke() -> int:
    """Construct the real Qt window surface and process a short event-loop turn."""
    _configure_window_smoke_environment()

    from PyQt6 import QtCore, QtWidgets

    from app.gui.window_shell import MainWindow

    app = QtWidgets.QApplication.instance()
    if app is None:
        app = QtWidgets.QApplication([sys.argv[0] if sys.argv else "trading-bot-desktop-smoke"])
    app.setQuitOnLastWindowClosed(False)

    window = None
    try:
        window = MainWindow()
        if not isinstance(window, QtWidgets.QWidget):
            raise RuntimeError("Window smoke created a non-Qt MainWindow.")
        tabs = getattr(window, "tabs", None)
        tab_count = int(tabs.count()) if tabs is not None else 0
        if tab_count <= 0:
            raise RuntimeError("Window smoke created a MainWindow without any tabs.")

        window.hide()
        QtCore.QTimer.singleShot(300, app.quit)
        app.exec()
        app.processEvents(QtCore.QEventLoop.ProcessEventsFlag.AllEvents, 100)

        stdout = getattr(sys, "stdout", None)
        if stdout is not None:
            stdout.write(
                "Trading Bot Python window smoke passed "
                f"(PyQt {QtCore.PYQT_VERSION_STR}, Qt {QtCore.QT_VERSION_STR}, tabs={tab_count}).\n"
            )
            stdout.flush()
        return 0
    finally:
        if window is not None:
            try:
                window.hide()
            except Exception:
                pass
            try:
                window._force_close = True
            except Exception:
                pass
            try:
                window.deleteLater()
            except Exception:
                pass
        try:
            app.processEvents(QtCore.QEventLoop.ProcessEventsFlag.AllEvents, 100)
        except Exception:
            pass
        try:
            app.quit()
        except Exception:
            pass


def _headless_service_requested(args: list[str]) -> bool:
    return any(
        str(arg or "").strip().lower() in {"--headless-service", "--desktop-service"}
        for arg in args
    )


def _run_headless_service() -> int:
    """Run the real desktop-owned Python runtime without presenting a window."""
    os.environ["BOT_ENABLE_DESKTOP_SERVICE_API"] = "1"
    os.environ.setdefault("BOT_DISABLE_PUBLIC_SHELL_SHORTCUT_LAUNCH", "1")
    os.environ.setdefault("BOT_DISABLE_PYTHONW_RELAUNCH", "1")
    os.environ.setdefault("BOT_DISABLE_STARTUP_WINDOW_HOOKS", "1")
    os.environ.setdefault("BOT_DISABLE_TASKBAR", "1")
    os.environ.setdefault("BOT_DISABLE_SPLASH", "1")
    from app.desktop.bootstrap import _run_headless_service as run_headless_service

    return int(run_headless_service())


def main(argv: list[str] | None = None) -> int:
    args = list(sys.argv[1:] if argv is None else argv)
    if "--smoke-window" in {str(arg).strip().lower() for arg in args}:
        return _run_window_smoke()
    if "--smoke" in {str(arg).strip().lower() for arg in args}:
        return _run_packaged_smoke()
    if _headless_service_requested(args):
        return _run_headless_service()

    _maybe_launch_via_shell_shortcut()
    from app.desktop.bootstrap import _run_entrypoint

    return int(_run_entrypoint())


if __name__ == "__main__":
    raise SystemExit(main())
