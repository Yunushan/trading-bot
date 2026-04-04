"""
Public desktop launcher.

This file intentionally stays at the workspace root so existing IDE
configurations, user shortcuts, README instructions, and relaunch metadata keep
working while the desktop bootstrap implementation lives under ``app.desktop``.
"""

import os
import subprocess
import sys
from pathlib import Path


def _env_flag(name: str) -> bool:
    return str(os.environ.get(name, "")).strip().lower() in {"1", "true", "yes", "on"}


def _boot_log(message: str) -> None:
    if not _env_flag("BOT_BOOT_LOG"):
        return
    try:
        print(f"[public-main] {message}", flush=True)
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
        from app.platform.windows_taskbar_metadata_runtime import resolve_relaunch_executable
        from app.platform.windows_taskbar import build_relaunch_command, ensure_start_menu_shortcut
    except Exception:
        _boot_log("skip shell shortcut: failed to import taskbar helpers")
        return

    workspace_dir = Path(__file__).resolve().parent
    try:
        current_exe = Path(sys.executable).resolve()
    except Exception:
        return
    gui_host = resolve_relaunch_executable(workspace_dir / "main.py")
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
            working_dir=workspace_dir,
            relaunch_command=build_relaunch_command(workspace_dir / "main.py"),
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
        os.startfile(str(shortcut_path))
        _boot_log(f"shell shortcut launched via {shortcut_path}")
    except Exception as exc:
        _boot_log(f"shell shortcut launch failed: {exc!r}")
        return
    raise SystemExit(0)


_maybe_launch_via_shell_shortcut()

from app.desktop.bootstrap import _run_entrypoint


if __name__ == "__main__":
    raise SystemExit(_run_entrypoint())
