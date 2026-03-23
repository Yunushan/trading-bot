from __future__ import annotations

import os
import sys
import time
from pathlib import Path


def _ensure_taskbar_identity(*, disable_taskbar: bool, app_user_model_id: str) -> None:
    if sys.platform != "win32" or disable_taskbar:
        return
    from app.platform.windows_taskbar import ensure_app_user_model_id

    ensure_app_user_model_id(app_user_model_id)


def _install_tradingview_app_watchdog(*, app, win, QtCore) -> None:
    if sys.platform != "win32":
        return
    try:
        watchdog_flag = str(os.environ.get("BOT_TRADINGVIEW_APP_WATCHDOG", "1")).strip().lower()
    except Exception:
        watchdog_flag = "1"
    if watchdog_flag in {"0", "false", "no", "off"}:
        return
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


def _write_ready_file() -> None:
    ready_signal = os.environ.get("BOT_STARTER_READY_FILE")
    if not ready_signal:
        return
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


def _schedule_startup_cleanup_timers(
    *,
    QtCore,
    uninstall_startup_window_suppression,
    uninstall_cbt_startup_window_suppression,
) -> None:
    if sys.platform == "win32":
        try:
            hook_auto_uninstall_ms = int(os.environ.get("BOT_STARTUP_WINDOW_HOOK_AUTO_UNINSTALL_MS") or 900)
        except Exception:
            hook_auto_uninstall_ms = 900
        hook_auto_uninstall_ms = max(0, min(hook_auto_uninstall_ms, 5000))
        if hook_auto_uninstall_ms > 0:
            QtCore.QTimer.singleShot(hook_auto_uninstall_ms, uninstall_startup_window_suppression)
            QtCore.QTimer.singleShot(hook_auto_uninstall_ms, uninstall_cbt_startup_window_suppression)

    try:
        suppress_ms = int(os.environ.get("BOT_STARTUP_WINDOW_SUPPRESS_DURATION_MS") or 8000)
    except Exception:
        suppress_ms = 8000
    QtCore.QTimer.singleShot(max(800, suppress_ms), uninstall_startup_window_suppression)

    try:
        cbt_ms = int(os.environ.get("BOT_CBT_STARTUP_WINDOW_SUPPRESS_DURATION_MS") or 2500)
    except Exception:
        cbt_ms = 2500
    QtCore.QTimer.singleShot(max(250, min(30000, cbt_ms)), uninstall_cbt_startup_window_suppression)


def _schedule_auto_exit(*, app, QtCore) -> None:
    try:
        auto_exit_ms = int(os.environ.get("BOT_AUTO_EXIT_MS") or 0)
    except Exception:
        auto_exit_ms = 0
    allow_auto_exit = str(os.environ.get("BOT_ALLOW_AUTO_EXIT", "")).strip().lower() in {"1", "true", "yes", "on"}
    if auto_exit_ms > 0 and allow_auto_exit:
        QtCore.QTimer.singleShot(auto_exit_ms, app.quit)


def _configure_post_window_runtime(
    *,
    app,
    win,
    QtCore,
    QWidget,
    env_flag,
    script_path: Path,
    app_display_name: str,
    app_user_model_id: str,
    force_app_icon: bool,
    disable_app_icon: bool,
    disable_taskbar: bool,
    resolve_taskbar_icon_path,
    format_shortcut_args,
    set_native_window_icon,
    apply_qt_icon,
    schedule_icon_enforcer,
    install_background_restore_guard,
    install_startup_input_unblocker,
    uninstall_startup_window_suppression,
    uninstall_cbt_startup_window_suppression,
) -> None:
    force_taskbar_visibility = env_flag("BOT_FORCE_TASKBAR_VISIBILITY")
    icon_path = None
    relaunch_cmd = None
    apply_taskbar_metadata = None
    ensure_taskbar_visible = None

    if sys.platform == "win32" and not disable_taskbar:
        from app.platform.windows_taskbar import (
            apply_taskbar_metadata as _apply_taskbar_metadata,
            build_relaunch_command,
            ensure_start_menu_shortcut,
            ensure_taskbar_visible as _ensure_taskbar_visible,
        )

        apply_taskbar_metadata = _apply_taskbar_metadata
        ensure_taskbar_visible = _ensure_taskbar_visible
        icon_path = resolve_taskbar_icon_path()
        relaunch_cmd = build_relaunch_command(script_path)
        if not env_flag("BOT_DISABLE_START_MENU_SHORTCUT"):
            try:
                ensure_start_menu_shortcut(
                    app_id=app_user_model_id,
                    display_name=app_display_name,
                    target_path=sys.executable,
                    arguments=format_shortcut_args(script_path),
                    icon_path=icon_path,
                    working_dir=script_path.resolve().parent,
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
                app_id=app_user_model_id,
                display_name=app_display_name,
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

    apply_native_icon_after_show = sys.platform == "win32" and (force_app_icon or env_flag("BOT_ENABLE_NATIVE_ICON"))
    if apply_native_icon_after_show:
        QtCore.QTimer.singleShot(0, lambda: set_native_window_icon(win))
    if sys.platform == "win32" and force_app_icon:
        QtCore.QTimer.singleShot(0, lambda: apply_qt_icon(app, win))
    if sys.platform == "win32":
        if disable_app_icon:
            if force_app_icon or env_flag("BOT_ENABLE_NATIVE_ICON"):
                try:
                    native_delay = int(os.environ.get("BOT_NATIVE_ICON_DELAY_MS") or 0)
                except Exception:
                    native_delay = 0
                if native_delay > 0:
                    QtCore.QTimer.singleShot(native_delay, lambda: set_native_window_icon(win))
                else:
                    set_native_window_icon(win)
            if force_app_icon or env_flag("BOT_ENABLE_DELAYED_QT_ICON"):
                try:
                    delayed_ms = int(os.environ.get("BOT_DELAYED_APP_ICON_MS") or 800)
                except Exception:
                    delayed_ms = 800
                delayed_ms = max(0, min(delayed_ms, 5000))
                QtCore.QTimer.singleShot(delayed_ms, lambda: apply_qt_icon(app, win))
        schedule_icon_enforcer(app, win)

    _install_tradingview_app_watchdog(app=app, win=win, QtCore=QtCore)
    install_background_restore_guard(app, win, QtCore, QWidget)
    install_startup_input_unblocker(
        app,
        QtCore,
        uninstall_startup_window_suppression=uninstall_startup_window_suppression,
        uninstall_cbt_startup_window_suppression=uninstall_cbt_startup_window_suppression,
    )

    if (
        sys.platform == "win32"
        and not disable_taskbar
        and apply_taskbar_metadata is not None
        and ensure_taskbar_visible is not None
    ):
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
                        app_id=app_user_model_id,
                        display_name=app_display_name,
                        icon_path=icon_path,
                        relaunch_command=relaunch_cmd,
                    )
                except Exception:
                    pass
                if (time.monotonic() - start_ts) * 1000.0 < controller_ms:
                    QtCore.QTimer.singleShot(interval_ms, _tick_taskbar)

            QtCore.QTimer.singleShot(start_delay_ms, _tick_taskbar)

    _write_ready_file()
    _schedule_startup_cleanup_timers(
        QtCore=QtCore,
        uninstall_startup_window_suppression=uninstall_startup_window_suppression,
        uninstall_cbt_startup_window_suppression=uninstall_cbt_startup_window_suppression,
    )
    _schedule_auto_exit(app=app, QtCore=QtCore)
