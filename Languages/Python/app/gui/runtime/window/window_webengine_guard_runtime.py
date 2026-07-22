from __future__ import annotations

import os
import sys
import time
from datetime import datetime
from pathlib import Path

from PyQt6 import QtCore, QtWidgets

from ...shared.silent_webengine_page import SilentWebEnginePage


def _record_webengine_guard_exception(self, context: str, exc: BaseException) -> None:
    message = (
        f"webengine_guard suppressed_exception context={context} "
        f"error={type(exc).__name__}: {str(exc).replace(chr(10), ' ')}"
    )
    try:
        logger = getattr(self, "_chart_debug_log", None) if self is not None else None
        if callable(logger):
            logger(message)
            return
    except Exception:
        logger = None
    try:
        path = Path(os.getenv("TEMP") or ".").resolve() / "binance_chart_debug.log"
        with open(path, "a", encoding="utf-8", errors="ignore") as fh:
            fh.write(f"[{datetime.now().astimezone().strftime('%Y-%m-%d %H:%M:%S %z')}] {message}\n")
    except OSError:
        return


def _bounded_env_int(name: str, default: int, minimum: int, maximum: int) -> int:
    try:
        value = int(os.environ.get(name) or default)
    except (TypeError, ValueError):
        value = default
    return max(minimum, min(value, maximum))


def schedule_tradingview_prewarm(self) -> None:
    if getattr(self, "_tradingview_prewarm_scheduled", False) or getattr(self, "_tradingview_prewarmed", False):
        return
    if not getattr(self, "_chart_view_tradingview_available", False):
        return
    if sys.platform != "win32":
        return
    flag = str(os.environ.get("BOT_PREWARM_TRADINGVIEW", "0")).strip().lower()
    if flag in {"0", "false", "no", "off"}:
        return
    delay_ms = _bounded_env_int("BOT_PREWARM_TRADINGVIEW_DELAY_MS", 1200, 100, 10000)
    self._tradingview_prewarm_scheduled = True
    QtCore.QTimer.singleShot(delay_ms, self._prewarm_tradingview)


def schedule_webengine_runtime_prewarm(self) -> None:
    if getattr(self, "_webengine_runtime_prewarm_scheduled", False):
        return
    if getattr(self, "_webengine_runtime_prewarmed", False):
        return
    flag = str(os.environ.get("BOT_PREWARM_WEBENGINE", "0")).strip().lower()
    if flag in {"0", "false", "no", "off"}:
        return
    delay_ms = _bounded_env_int("BOT_PREWARM_WEBENGINE_DELAY_MS", 1800, 250, 15000)
    self._webengine_runtime_prewarm_scheduled = True
    QtCore.QTimer.singleShot(delay_ms, self._maybe_run_deferred_webengine_prewarm)


def maybe_run_deferred_webengine_prewarm(self) -> None:
    if getattr(self, "_webengine_runtime_prewarmed", False):
        self._webengine_runtime_prewarm_scheduled = False
        return
    try:
        app = QtWidgets.QApplication.instance()
    except Exception:
        app = None
    if sys.platform == "win32":
        try:
            if app is not None and app.applicationState() != QtCore.Qt.ApplicationState.ApplicationActive:
                QtCore.QTimer.singleShot(1200, self._maybe_run_deferred_webengine_prewarm)
                return
        except Exception as exc:
            _record_webengine_guard_exception(self, "deferred_prewarm_app_state", exc)
        try:
            if not self.isVisible() or self.windowState() & QtCore.Qt.WindowState.WindowMinimized:
                QtCore.QTimer.singleShot(1200, self._maybe_run_deferred_webengine_prewarm)
                return
        except Exception as exc:
            _record_webengine_guard_exception(self, "deferred_prewarm_window_state", exc)
    self._webengine_runtime_prewarm_scheduled = False
    try:
        self._prewarm_webengine_runtime()
    except Exception as exc:
        _record_webengine_guard_exception(self, "deferred_prewarm_run", exc)


def prewarm_webengine_runtime(
    self,
    *,
    webengine_charts_allowed,
    webengine_embed_unavailable_reason,
    configure_tradingview_webengine_env,
) -> None:
    if getattr(self, "_webengine_runtime_prewarmed", False):
        return
    if sys.platform != "win32":
        return
    if not webengine_charts_allowed():
        return
    flag = str(os.environ.get("BOT_PREWARM_WEBENGINE", "1")).strip().lower()
    if flag in {"0", "false", "no", "off"}:
        return
    if webengine_embed_unavailable_reason():
        return
    try:
        configure_tradingview_webengine_env()
    except Exception as exc:
        _record_webengine_guard_exception(self, "prewarm_configure_env", exc)
    try:
        from PyQt6.QtWebEngineWidgets import QWebEngineView
    except Exception:
        return
    try:
        view = QWebEngineView(self)
        view.setObjectName("botWebEnginePrewarm")
        try:
            if SilentWebEnginePage is not None:
                view.setPage(SilentWebEnginePage(view))
        except Exception as exc:
            _record_webengine_guard_exception(self, "prewarm_set_silent_page", exc)
        try:
            view.setAttribute(QtCore.Qt.WidgetAttribute.WA_DontShowOnScreen, True)
        except Exception as exc:
            _record_webengine_guard_exception(self, "prewarm_hide_attribute", exc)
        try:
            view.resize(1, 1)
            view.move(-32000, -32000)
            view.hide()
        except Exception as exc:
            _record_webengine_guard_exception(self, "prewarm_position_view", exc)
        try:
            view.load(QtCore.QUrl("about:blank"))
        except Exception as exc:
            _record_webengine_guard_exception(self, "prewarm_load_blank", exc)
        self._webengine_runtime_prewarm_view = view
        self._webengine_runtime_prewarmed = True
        try:
            self._chart_debug_log("webengine_prewarm init=1")
        except Exception as exc:
            _record_webengine_guard_exception(self, "prewarm_debug_log", exc)
    except Exception as exc:
        _record_webengine_guard_exception(self, "prewarm_create_view", exc)
        return

    hold_ms = _bounded_env_int("BOT_PREWARM_WEBENGINE_HOLD_MS", 2200, 500, 10000)

    def _cleanup():
        view_obj = getattr(self, "_webengine_runtime_prewarm_view", None)
        self._webengine_runtime_prewarm_view = None
        if view_obj is not None:
            try:
                view_obj.deleteLater()
            except Exception as exc:
                _record_webengine_guard_exception(self, "prewarm_cleanup_view", exc)

    QtCore.QTimer.singleShot(hold_ms, _cleanup)


def prewarm_tradingview(self) -> None:
    self._tradingview_prewarm_scheduled = False
    if getattr(self, "_tradingview_prewarmed", False):
        return
    if not getattr(self, "_chart_view_tradingview_available", False):
        return
    widget = self._ensure_tradingview_widget()
    if widget is None:
        return
    self._tradingview_prewarmed = True
    self._prime_tradingview_chart(widget)


def start_tradingview_visibility_guard(self) -> None:
    if sys.platform != "win32":
        return
    if getattr(self, "_tv_visibility_guard_active", False):
        return
    duration_ms = _bounded_env_int("BOT_TRADINGVIEW_VISIBILITY_GUARD_MS", 2500, 500, 8000)
    interval_ms = _bounded_env_int("BOT_TRADINGVIEW_VISIBILITY_GUARD_INTERVAL_MS", 50, 20, 200)

    timer = QtCore.QTimer(self)
    timer.setInterval(interval_ms)
    start_ts = time.monotonic()
    self._tv_visibility_guard_active = True
    self._tv_visibility_guard_timer = timer

    def _tick():
        if (time.monotonic() - start_ts) * 1000.0 >= duration_ms:
            self._stop_tradingview_visibility_guard()
            return
        try:
            if not self.isVisible():
                self.showMaximized()
                self.raise_()
                self.activateWindow()
            elif self.windowState() & QtCore.Qt.WindowState.WindowMinimized:
                self.showMaximized()
                self.raise_()
                self.activateWindow()
        except Exception as exc:
            _record_webengine_guard_exception(self, "tradingview_visibility_guard_tick", exc)

    timer.timeout.connect(_tick)
    timer.start()
    _tick()


def start_tradingview_visibility_watchdog(self) -> None:
    if sys.platform != "win32":
        return
    if getattr(self, "_tv_visibility_watchdog_active", False):
        return
    flag = str(os.environ.get("BOT_TRADINGVIEW_VISIBILITY_WATCHDOG", "1")).strip().lower()
    if flag in {"0", "false", "no", "off"}:
        return
    interval_ms = _bounded_env_int("BOT_TRADINGVIEW_VISIBILITY_WATCHDOG_INTERVAL_MS", 200, 50, 1000)
    timer = QtCore.QTimer(self)
    timer.setInterval(interval_ms)
    self._tv_visibility_watchdog_active = True
    self._tv_visibility_watchdog_timer = timer

    def _tick():
        try:
            if not self.isVisible() or self.windowState() & QtCore.Qt.WindowState.WindowMinimized:
                self.showMaximized()
                self.raise_()
                self.activateWindow()
        except Exception as exc:
            _record_webengine_guard_exception(self, "tradingview_visibility_watchdog_tick", exc)

    timer.timeout.connect(_tick)
    timer.start()
    _tick()


def start_tradingview_close_guard(self) -> None:
    if sys.platform != "win32":
        return
    duration_ms = _bounded_env_int("BOT_TRADINGVIEW_CLOSE_GUARD_MS", 2500, 500, 8000)
    try:
        self._tv_close_guard_until = time.monotonic() + (duration_ms / 1000.0)
    except Exception:
        self._tv_close_guard_until = 0.0
    self._tv_close_guard_active = True
    try:
        extender = getattr(self, "_extend_spontaneous_close_block", None)
        if callable(extender):
            extender(duration_ms + 2500)
    except Exception as exc:
        _record_webengine_guard_exception(self, "tradingview_close_guard_extend", exc)


def start_webengine_close_guard(self, *, webengine_charts_allowed) -> None:
    if sys.platform != "win32":
        return
    if not webengine_charts_allowed():
        return
    duration_ms = _bounded_env_int("BOT_WEBENGINE_CLOSE_GUARD_MS", 3500, 800, 15000)
    try:
        until = time.monotonic() + (duration_ms / 1000.0)
    except Exception:
        until = 0.0
    try:
        prev_until = float(getattr(self, "_webengine_close_guard_until", 0.0) or 0.0)
    except Exception:
        prev_until = 0.0
    self._webengine_close_guard_until = max(prev_until, until)
    self._webengine_close_guard_active = True
    try:
        extender = getattr(self, "_extend_spontaneous_close_block", None)
        if callable(extender):
            extender(duration_ms + 2500)
    except Exception as exc:
        _record_webengine_guard_exception(self, "webengine_close_guard_extend", exc)
    self._start_webengine_visibility_watchdog()
    try:
        self._chart_debug_log(
            f"webengine_close_guard start duration_ms={duration_ms} until={self._webengine_close_guard_until:.3f}"
        )
    except Exception as exc:
        _record_webengine_guard_exception(self, "webengine_close_guard_debug_log", exc)


def start_webengine_visibility_watchdog(self, *, allow_guard_bypass, restore_window_after_guard) -> None:
    if sys.platform != "win32":
        return
    if getattr(self, "_webengine_visibility_watchdog_active", False):
        return
    interval_ms = _bounded_env_int("BOT_WEBENGINE_CLOSE_GUARD_WATCHDOG_INTERVAL_MS", 120, 30, 1000)
    timer = QtCore.QTimer(self)
    timer.setInterval(interval_ms)
    self._webengine_visibility_watchdog_active = True
    self._webengine_visibility_watchdog_timer = timer

    def _tick():
        if allow_guard_bypass(self):
            self._stop_webengine_visibility_watchdog()
            return
        try:
            now = time.monotonic()
        except Exception:
            now = 0.0
        try:
            until = float(getattr(self, "_webengine_close_guard_until", 0.0) or 0.0)
        except Exception:
            until = 0.0
        if not until or now >= until:
            try:
                self._webengine_close_guard_active = False
            except Exception as exc:
                _record_webengine_guard_exception(self, "webengine_visibility_watchdog_expire", exc)
            self._stop_webengine_visibility_watchdog()
            return
        if not getattr(self, "_webengine_close_guard_active", False):
            self._stop_webengine_visibility_watchdog()
            return
        try:
            if not self.isVisible() or self.windowState() & QtCore.Qt.WindowState.WindowMinimized:
                restore_window_after_guard(self)
        except Exception as exc:
            _record_webengine_guard_exception(self, "webengine_visibility_watchdog_restore", exc)

    timer.timeout.connect(_tick)
    timer.start()
    _tick()


def stop_webengine_visibility_watchdog(self) -> None:
    timer = getattr(self, "_webengine_visibility_watchdog_timer", None)
    if timer is not None:
        try:
            timer.stop()
        except Exception as exc:
            _record_webengine_guard_exception(self, "webengine_watchdog_timer_stop", exc)
        try:
            timer.deleteLater()
        except Exception as exc:
            _record_webengine_guard_exception(self, "webengine_watchdog_timer_delete", exc)
    self._webengine_visibility_watchdog_timer = None
    self._webengine_visibility_watchdog_active = False


def stop_tradingview_visibility_guard(self) -> None:
    timer = getattr(self, "_tv_visibility_guard_timer", None)
    if timer is not None:
        try:
            timer.stop()
        except Exception as exc:
            _record_webengine_guard_exception(self, "tradingview_guard_timer_stop", exc)
        try:
            timer.deleteLater()
        except Exception as exc:
            _record_webengine_guard_exception(self, "tradingview_guard_timer_delete", exc)
    self._tv_visibility_guard_timer = None
    self._tv_visibility_guard_active = False


def stop_tradingview_visibility_watchdog(self) -> None:
    timer = getattr(self, "_tv_visibility_watchdog_timer", None)
    if timer is not None:
        try:
            timer.stop()
        except Exception as exc:
            _record_webengine_guard_exception(self, "tradingview_watchdog_timer_stop", exc)
        try:
            timer.deleteLater()
        except Exception as exc:
            _record_webengine_guard_exception(self, "tradingview_watchdog_timer_delete", exc)
    self._tv_visibility_watchdog_timer = None
    self._tv_visibility_watchdog_active = False


def restore_window_after_guard(self) -> None:
    def _restore_once():
        try:
            state = self.windowState()
        except Exception:
            state = QtCore.Qt.WindowState.WindowNoState
        try:
            visible = bool(self.isVisible())
        except Exception:
            visible = False
        try:
            minimized = bool(state & QtCore.Qt.WindowState.WindowMinimized)
        except Exception:
            minimized = False
        if minimized:
            try:
                self.showMaximized()
            except Exception as exc:
                _record_webengine_guard_exception(self, "restore_minimized_show", exc)
        elif not visible:
            try:
                self.showMaximized()
            except Exception as exc:
                _record_webengine_guard_exception(self, "restore_hidden_show", exc)
        try:
            self.raise_()
            self.activateWindow()
        except Exception as exc:
            _record_webengine_guard_exception(self, "restore_raise_activate", exc)

    _restore_once()
    try:
        # WebEngine can minimize the host window a little after the initial
        # hide/minimize event, so keep restoring for a short grace period.
        for delay_ms in (40, 140, 320, 700, 1400, 2400):
            QtCore.QTimer.singleShot(delay_ms, _restore_once)
    except Exception as exc:
        _record_webengine_guard_exception(self, "restore_schedule_retries", exc)
