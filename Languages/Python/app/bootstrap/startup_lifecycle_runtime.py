from __future__ import annotations

import os
import threading
import time

from .startup_ui_shared import _boot_log


def _record_startup_lifecycle_exception(
    context: str,
    exc: BaseException,
    *,
    boot_log=None,
) -> None:
    message = str(exc).replace("\n", " ")
    logger = boot_log if callable(boot_log) else _boot_log
    try:
        logger(f"startup lifecycle suppressed exception context={context} error={type(exc).__name__}: {message}")
    except Exception:
        return


def _visible_top_level_windows_snapshot(app) -> list:
    try:
        widgets = list(app.topLevelWidgets())
    except Exception:
        widgets = []
    visible: list = []
    for widget in widgets:
        if widget is None:
            continue
        try:
            if not widget.isWindow():
                continue
        except Exception as exc:
            _record_startup_lifecycle_exception("visible_window_is_window_check", exc)
        try:
            if not widget.isVisible():
                continue
        except Exception:
            continue
        visible.append(widget)
    return visible


def _close_native_startup_cover(native_startup_cover, *, boot_log=None):
    cover = native_startup_cover
    if cover is None:
        return None
    try:
        cover.close()
        if callable(boot_log):
            boot_log("native startup cover hidden")
    except Exception as exc:
        _record_startup_lifecycle_exception("close_native_startup_cover", exc, boot_log=boot_log)
    return None


def _arm_background_process_exit(
    app,
    *,
    uninstall_startup_window_suppression,
    uninstall_cbt_startup_window_suppression,
    delay_s: float = 1.5,
    watchdog_s: float = 8.0,
) -> None:
    delay_s = max(0.5, min(float(delay_s), 5.0))
    watchdog_s = max(delay_s + 0.5, min(float(watchdog_s), 20.0))

    lock = getattr(app, "_bot_hard_exit_lock", None)
    if lock is None:
        lock = threading.Lock()
        try:
            setattr(app, "_bot_hard_exit_lock", lock)
        except Exception as exc:
            _record_startup_lifecycle_exception("arm_background_exit_store_lock", exc)

    state = getattr(app, "_bot_hard_exit_state", None)
    if not isinstance(state, dict):
        state = {"armed": False}
        try:
            setattr(app, "_bot_hard_exit_state", state)
        except Exception as exc:
            _record_startup_lifecycle_exception("arm_background_exit_store_state", exc)

    with lock:
        if state["armed"]:
            return
        state["armed"] = True

    def _worker() -> None:
        invisible_since = 0.0
        deadline = time.monotonic() + watchdog_s
        try:
            while time.monotonic() < deadline:
                try:
                    visible = bool(_visible_top_level_windows_snapshot(app))
                except Exception:
                    visible = False
                if visible:
                    invisible_since = 0.0
                else:
                    now = time.monotonic()
                    if invisible_since <= 0.0:
                        invisible_since = now
                    elif (now - invisible_since) >= delay_s:
                        try:
                            uninstall_startup_window_suppression()
                        except Exception as exc:
                            _record_startup_lifecycle_exception("background_exit_uninstall_startup_suppression", exc)
                        try:
                            uninstall_cbt_startup_window_suppression()
                        except Exception as exc:
                            _record_startup_lifecycle_exception("background_exit_uninstall_cbt_suppression", exc)
                        os._exit(0)
                time.sleep(0.1)
        finally:
            with lock:
                state["armed"] = False

    threading.Thread(target=_worker, name="bot-hard-exit", daemon=True).start()


def _bind_background_process_exit(
    app,
    *,
    uninstall_startup_window_suppression,
    uninstall_cbt_startup_window_suppression,
) -> None:
    def _arm(delay_s: float = 1.5, watchdog_s: float = 8.0) -> None:
        _arm_background_process_exit(
            app,
            uninstall_startup_window_suppression=uninstall_startup_window_suppression,
            uninstall_cbt_startup_window_suppression=uninstall_cbt_startup_window_suppression,
            delay_s=delay_s,
            watchdog_s=watchdog_s,
        )

    setattr(app, "_bot_arm_hard_exit", _arm)  # type: ignore[attr-defined]


def _install_background_restore_guard(app, win, QtCore, QWidget) -> None:
    try:
        def _terminate_background_app() -> None:
            try:
                if getattr(app, "_exiting", False):  # type: ignore[attr-defined]
                    arm_hard_exit = getattr(app, "_bot_arm_hard_exit", None)
                    if callable(arm_hard_exit):
                        arm_hard_exit()
                    return
            except Exception as exc:
                _record_startup_lifecycle_exception("terminate_background_check_exiting", exc)
            try:
                setattr(app, "_exiting", True)  # type: ignore[attr-defined]
            except Exception as exc:
                _record_startup_lifecycle_exception("terminate_background_set_exiting", exc)
            try:
                arm_hard_exit = getattr(app, "_bot_arm_hard_exit", None)
                if callable(arm_hard_exit):
                    arm_hard_exit()
            except Exception as exc:
                _record_startup_lifecycle_exception("terminate_background_arm_hard_exit", exc)
            try:
                if win is not None:
                    win._cpp_window_hidden_for_cpp_handoff = False
                    win._force_close = True
            except Exception as exc:
                _record_startup_lifecycle_exception("terminate_background_window_flags", exc)
            try:
                if win is not None:
                    QWidget.close(win)
                    return
            except Exception as exc:
                _record_startup_lifecycle_exception("terminate_background_qwidget_close", exc)
            try:
                app.quit()
            except Exception as exc:
                _record_startup_lifecycle_exception("terminate_background_app_quit", exc)

        def _ensure_not_left_running_in_background() -> None:
            try:
                if getattr(app, "_exiting", False):  # type: ignore[attr-defined]
                    return
            except Exception as exc:
                _record_startup_lifecycle_exception("background_guard_check_exiting", exc)
            try:
                if _visible_top_level_windows_snapshot(app):
                    return
            except Exception as exc:
                _record_startup_lifecycle_exception("background_guard_visible_snapshot", exc)
            try:
                if bool(getattr(win, "_cpp_launch_handoff_active", False)):
                    QtCore.QTimer.singleShot(250, _ensure_not_left_running_in_background)
                    return
            except Exception as exc:
                _record_startup_lifecycle_exception("background_guard_cpp_handoff_check", exc)
            _terminate_background_app()

        def _restore_main_window() -> None:
            try:
                if getattr(app, "_exiting", False):  # type: ignore[attr-defined]
                    return
            except Exception as exc:
                _record_startup_lifecycle_exception("restore_main_window_check_exiting", exc)
            try:
                hidden_for_handoff = bool(getattr(win, "_cpp_window_hidden_for_cpp_handoff", False))
            except Exception:
                hidden_for_handoff = False
            if hidden_for_handoff:
                QtCore.QTimer.singleShot(300, _ensure_not_left_running_in_background)
                return
            try:
                if win is None or win.isVisible():
                    return
            except Exception:
                QtCore.QTimer.singleShot(300, _ensure_not_left_running_in_background)
                return
            try:
                win.showMaximized()
                win.raise_()
                win.activateWindow()
            except Exception as exc:
                _record_startup_lifecycle_exception("restore_main_window_show", exc)
            QtCore.QTimer.singleShot(300, _ensure_not_left_running_in_background)

        app.lastWindowClosed.connect(_restore_main_window)
    except Exception as exc:
        _record_startup_lifecycle_exception("install_background_restore_guard", exc)


def _install_startup_input_unblocker(
    app,
    QtCore,
    *,
    uninstall_startup_window_suppression,
    uninstall_cbt_startup_window_suppression,
) -> None:
    class _StartupInputUnblocker(QtCore.QObject):
        def __init__(self, app_instance):
            super().__init__(app_instance)
            self._app = app_instance
            self._armed = True

        def eventFilter(self, obj, event):  # noqa: ANN001,N802
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
                    uninstall_startup_window_suppression()
                except Exception as exc:
                    _record_startup_lifecycle_exception("startup_input_unblocker_uninstall_startup_suppression", exc)
                try:
                    uninstall_cbt_startup_window_suppression()
                except Exception as exc:
                    _record_startup_lifecycle_exception("startup_input_unblocker_uninstall_cbt_suppression", exc)
                try:
                    self._app.removeEventFilter(self)
                except Exception as exc:
                    _record_startup_lifecycle_exception("startup_input_unblocker_remove_filter", exc)
            return False

    try:
        app._startup_input_unblocker = _StartupInputUnblocker(app)
        app.installEventFilter(app._startup_input_unblocker)
    except Exception as exc:
        _record_startup_lifecycle_exception("install_startup_input_unblocker", exc)
