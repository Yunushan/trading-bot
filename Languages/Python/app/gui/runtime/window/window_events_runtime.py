from __future__ import annotations

import os
import sys
import time
from datetime import datetime
from pathlib import Path

from PyQt6 import QtCore, QtWidgets

from . import window_webengine_guard_runtime


def request_strategy_shutdown(strategy_engine_cls=None) -> None:
    if strategy_engine_cls is None:
        return
    try:
        strategy_engine_cls.request_shutdown()
    except Exception:
        pass


def teardown_positions_thread(self):
    try:
        if getattr(self, "_pos_worker", None) is not None:
            try:
                self.req_pos_stop.emit()
            except Exception:
                pass
        if getattr(self, "_pos_thread", None) is not None:
            try:
                self._pos_thread.quit()
                self._pos_thread.wait(2000)
            except Exception:
                pass
        self._pos_worker = None
        self._pos_thread = None
    except Exception:
        pass


def log_window_event(self, name: str, event=None) -> None:
    try:
        visible = int(bool(self.isVisible()))
    except Exception:
        visible = -1
    try:
        minimized = int(bool(self.windowState() & QtCore.Qt.WindowState.WindowMinimized))
    except Exception:
        minimized = -1
    try:
        spontaneous = int(bool(event.spontaneous())) if event is not None else -1
    except Exception:
        spontaneous = -1
    try:
        now = time.monotonic()
    except Exception:
        now = 0.0
    try:
        we_active = int(bool(getattr(self, "_webengine_close_guard_active", False)))
    except Exception:
        we_active = -1
    try:
        we_until = float(getattr(self, "_webengine_close_guard_until", 0.0) or 0.0)
    except Exception:
        we_until = 0.0
    try:
        we_rem_ms = int(max(0.0, (we_until - now) * 1000.0)) if we_until else 0
    except Exception:
        we_rem_ms = -1
    msg = (
        f"window_event {name} visible={visible} minimized={minimized} spontaneous={spontaneous} "
        f"we_guard={we_active} we_rem_ms={we_rem_ms}"
    )
    try:
        logger = getattr(self, "_chart_debug_log", None)
        if callable(logger):
            logger(msg)
            return
    except Exception:
        pass
    try:
        path = Path(os.getenv("TEMP") or ".").resolve() / "binance_chart_debug.log"
        with open(path, "a", encoding="utf-8", errors="ignore") as fh:
            fh.write(f"[{datetime.now().astimezone().strftime('%Y-%m-%d %H:%M:%S %z')}] {msg}\n")
    except Exception:
        pass


def allow_guard_bypass(self) -> bool:
    try:
        if (
            bool(getattr(self, "_force_close", False))
            or bool(getattr(self, "_close_in_progress", False))
            or bool(getattr(self, "_cpp_launch_handoff_active", False))
            or bool(getattr(self, "_rust_launch_handoff_active", False))
        ):
            return True
    except Exception:
        pass
    try:
        app = QtWidgets.QApplication.instance()
    except Exception:
        app = None
    try:
        if app is not None and bool(getattr(app, "_exiting", False)):
            return True
    except Exception:
        pass
    return False


def mark_user_close_command(self) -> None:
    try:
        self._last_user_close_command_ts = time.monotonic()
    except Exception:
        self._last_user_close_command_ts = 0.0


def is_recent_user_close_command(self) -> bool:
    try:
        last_ts = float(getattr(self, "_last_user_close_command_ts", 0.0) or 0.0)
    except Exception:
        last_ts = 0.0
    if last_ts <= 0.0:
        return False
    try:
        ttl_ms = int(os.environ.get("BOT_USER_CLOSE_BYPASS_MS") or 1800)
    except Exception:
        ttl_ms = 1800
    ttl_ms = max(300, min(ttl_ms, 10000))
    try:
        return (time.monotonic() - last_ts) * 1000.0 <= ttl_ms
    except Exception:
        return False


def event_is_spontaneous(event) -> bool:  # noqa: ANN001
    try:
        return bool(event is not None and event.spontaneous())
    except Exception:
        return False


def active_spontaneous_close_block_until(self) -> float:
    try:
        now = time.monotonic()
    except Exception:
        now = 0.0
    try:
        until = float(getattr(self, "_spontaneous_close_block_until", 0.0) or 0.0)
    except Exception:
        until = 0.0
    if until and now >= until:
        try:
            self._spontaneous_close_block_until = 0.0
        except Exception:
            pass
        return 0.0
    return until


def extend_spontaneous_close_block(self, duration_ms: int = 5000) -> float:
    try:
        now = time.monotonic()
    except Exception:
        now = 0.0
    duration_ms = max(300, min(int(duration_ms), 15000))
    try:
        previous = float(getattr(self, "_spontaneous_close_block_until", 0.0) or 0.0)
    except Exception:
        previous = 0.0
    until = max(previous, now + (duration_ms / 1000.0))
    try:
        self._spontaneous_close_block_until = until
    except Exception:
        pass
    return until


def active_close_protection_until(self) -> float:
    try:
        now = time.monotonic()
    except Exception:
        now = 0.0

    try:
        tv_active = bool(getattr(self, "_tv_close_guard_active", False))
    except Exception:
        tv_active = False
    try:
        tv_until = float(getattr(self, "_tv_close_guard_until", 0.0) or 0.0)
    except Exception:
        tv_until = 0.0
    if tv_active and tv_until and now >= tv_until:
        try:
            self._tv_close_guard_active = False
        except Exception:
            pass
        tv_active = False
        tv_until = 0.0

    try:
        we_active = bool(getattr(self, "_webengine_close_guard_active", False))
    except Exception:
        we_active = False
    try:
        we_until = float(getattr(self, "_webengine_close_guard_until", 0.0) or 0.0)
    except Exception:
        we_until = 0.0
    if we_active and we_until and now >= we_until:
        try:
            self._webengine_close_guard_active = False
        except Exception:
            pass
        we_active = False
        we_until = 0.0

    active_until = 0.0
    if tv_active and tv_until > active_until:
        active_until = tv_until
    if we_active and we_until > active_until:
        active_until = we_until
    return active_until


def restore_window_after_guard(self) -> None:
    return window_webengine_guard_runtime.restore_window_after_guard(self)


def should_block_spontaneous_close(self, event) -> bool:  # noqa: ANN001
    if allow_guard_bypass(self):
        return False
    if is_recent_user_close_command(self):
        return False
    if not event_is_spontaneous(event):
        return False
    try:
        now = time.monotonic()
    except Exception:
        now = 0.0
    guard_until = active_close_protection_until(self)
    if guard_until and now < guard_until:
        remaining_ms = int(max(0.0, (guard_until - now) * 1000.0))
        extend_spontaneous_close_block(self, max(5000, remaining_ms + 2500))
        return True
    block_until = active_spontaneous_close_block_until(self)
    return bool(block_until and now < block_until)


def should_block_programmatic_hide(self) -> bool:
    if allow_guard_bypass(self):
        return False
    try:
        now = time.monotonic()
    except Exception:
        now = 0.0
    guard_until = active_close_protection_until(self)
    return bool(guard_until and now < guard_until and not is_recent_user_close_command(self))


def set_visible(self, visible):  # noqa: N802, ANN001
    make_visible = bool(visible)
    if not make_visible and should_block_programmatic_hide(self):
        try:
            logger = getattr(self, "_chart_debug_log", None)
            if callable(logger):
                logger("window_event setVisible_blocked visible=0 reason=webengine_guard")
        except Exception:
            pass
        restore_window_after_guard(self)
        return
    try:
        super(type(self), self).setVisible(visible)
    except Exception:
        pass


def hide_window(self):  # noqa: ANN001
    if should_block_programmatic_hide(self):
        try:
            logger = getattr(self, "_chart_debug_log", None)
            if callable(logger):
                logger("window_event hide_blocked reason=webengine_guard")
        except Exception:
            pass
        restore_window_after_guard(self)
        return
    try:
        super(type(self), self).hide()
    except Exception:
        pass


def native_event(self, eventType, message):  # noqa: N802, ANN001
    if sys.platform == "win32":
        detect_flag = str(os.environ.get("BOT_ENABLE_NATIVE_CLOSE_DETECT", "")).strip().lower()
        if detect_flag not in {"1", "true", "yes", "on"}:
            try:
                return super(type(self), self).nativeEvent(eventType, message)
            except Exception:
                return False, 0
        try:
            et = ""
            try:
                et = bytes(eventType).decode("utf-8", "ignore").strip().lower()
            except Exception:
                try:
                    et = str(eventType).strip().lower()
                except Exception:
                    et = ""
            if et not in {"windows_generic_msg", "windows_dispatcher_msg"}:
                raise RuntimeError("unsupported native event type")
            import ctypes
            import ctypes.wintypes as wintypes

            wm_syscommand = 0x0112
            sc_close = 0xF060
            msg_ptr = int(message)
            if msg_ptr and msg_ptr > 0x10000:
                msg_obj = ctypes.cast(msg_ptr, ctypes.POINTER(wintypes.MSG)).contents
                if int(msg_obj.message) == wm_syscommand:
                    cmd = int(msg_obj.wParam) & 0xFFF0
                    if cmd == sc_close:
                        mark_user_close_command(self)
        except Exception:
            pass
    try:
        return super(type(self), self).nativeEvent(eventType, message)
    except Exception:
        return False, 0


def close_event(self, event, *, strategy_engine_cls=None):
    try:
        log_window_event(self, "closeEvent", event=event)
    except Exception:
        pass
    close_guard = getattr(self, "_close_in_progress", False)
    if close_guard:
        event.ignore()
        return
    if getattr(self, "_force_close", False):
        self._force_close = False
        request_strategy_shutdown(strategy_engine_cls)
        try:
            teardown_positions_thread(self)
        except Exception:
            pass
        try:
            shutdown_service_host = getattr(self, "_shutdown_desktop_service_api_host", None)
            if callable(shutdown_service_host):
                shutdown_service_host()
        except Exception:
            pass
        try:
            self._mark_session_inactive()
        except Exception:
            pass
        try:
            super(type(self), self).closeEvent(event)
        except Exception:
            try:
                event.accept()
            except Exception:
                pass
        try:
            app = QtWidgets.QApplication.instance()
            if app is not None:
                setattr(app, "_exiting", True)
                arm_hard_exit = getattr(app, "_bot_arm_hard_exit", None)
                if callable(arm_hard_exit):
                    arm_hard_exit()
                app.quit()
        except Exception:
            pass
        return
    if should_block_spontaneous_close(self, event):
        try:
            logger = getattr(self, "_chart_debug_log", None)
            if callable(logger):
                logger("window_event closeEvent_blocked reason=spontaneous_guard")
        except Exception:
            pass
        try:
            event.ignore()
        except Exception:
            pass
        restore_window_after_guard(self)
        return
    if not allow_guard_bypass(self):
        try:
            now = time.monotonic()
        except Exception:
            now = 0.0
        guard_until = active_close_protection_until(self)
        if guard_until and now < guard_until:
            if is_recent_user_close_command(self):
                try:
                    self._last_user_close_command_ts = 0.0
                except Exception:
                    pass
                try:
                    self._webengine_close_guard_active = False
                    self._tv_close_guard_active = False
                except Exception:
                    pass
            else:
                event.ignore()
                restore_window_after_guard(self)
                return

    request_strategy_shutdown(strategy_engine_cls)
    try:
        app = QtWidgets.QApplication.instance()
        if app is not None:
            setattr(app, "_exiting", True)
            arm_hard_exit = getattr(app, "_bot_arm_hard_exit", None)
            if callable(arm_hard_exit):
                arm_hard_exit()
    except Exception:
        pass

    close_on_exit_enabled = bool(getattr(self, "cb_close_on_exit", None) and self.cb_close_on_exit.isChecked())
    if close_on_exit_enabled:
        event.ignore()
        self._begin_close_on_exit_sequence()
        return

    try:
        self.stop_strategy_async(close_positions=close_on_exit_enabled, blocking=True)
    except Exception:
        pass
    try:
        teardown_positions_thread(self)
    except Exception:
        pass
    try:
        shutdown_service_host = getattr(self, "_shutdown_desktop_service_api_host", None)
        if callable(shutdown_service_host):
            shutdown_service_host()
    except Exception:
        pass
    try:
        self._mark_session_inactive()
    except Exception:
        pass
    try:
        super(type(self), self).closeEvent(event)
    except Exception:
        try:
            event.accept()
        except Exception:
            pass
    try:
        if event.isAccepted():
            app = QtWidgets.QApplication.instance()
            if app is not None:
                arm_hard_exit = getattr(app, "_bot_arm_hard_exit", None)
                if callable(arm_hard_exit):
                    arm_hard_exit()
                app.quit()
    except Exception:
        pass


def hide_event(self, event):  # noqa: N802
    try:
        log_window_event(self, "hideEvent", event=event)
    except Exception:
        pass
    if should_block_spontaneous_close(self, event):
        try:
            logger = getattr(self, "_chart_debug_log", None)
            if callable(logger):
                logger("window_event hideEvent_blocked reason=spontaneous_guard")
        except Exception:
            pass
        try:
            event.ignore()
        except Exception:
            pass
        restore_window_after_guard(self)
        return
    if not allow_guard_bypass(self):
        try:
            now = time.monotonic()
        except Exception:
            now = 0.0
        guard_until = active_close_protection_until(self)
        if guard_until and now < guard_until:
            if not is_recent_user_close_command(self):
                try:
                    event.ignore()
                except Exception:
                    pass
                restore_window_after_guard(self)
                return
    try:
        super(type(self), self).hideEvent(event)
    except Exception:
        try:
            event.accept()
        except Exception:
            pass
