from __future__ import annotations

import os
import sys
import time

from PyQt6 import QtCore, QtWidgets


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
    try:
        delay_ms = int(os.environ.get("BOT_PREWARM_TRADINGVIEW_DELAY_MS") or 1200)
    except Exception:
        delay_ms = 1200
    delay_ms = max(100, min(delay_ms, 10000))
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
    try:
        delay_ms = int(os.environ.get("BOT_PREWARM_WEBENGINE_DELAY_MS") or 1800)
    except Exception:
        delay_ms = 1800
    delay_ms = max(250, min(delay_ms, 15000))
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
        except Exception:
            pass
        try:
            if not self.isVisible() or self.windowState() & QtCore.Qt.WindowState.WindowMinimized:
                QtCore.QTimer.singleShot(1200, self._maybe_run_deferred_webengine_prewarm)
                return
        except Exception:
            pass
    self._webengine_runtime_prewarm_scheduled = False
    try:
        self._prewarm_webengine_runtime()
    except Exception:
        pass


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
    except Exception:
        pass
    try:
        from PyQt6.QtWebEngineWidgets import QWebEngineView
    except Exception:
        return
    try:
        view = QWebEngineView(self)
        view.setObjectName("botWebEnginePrewarm")
        try:
            view.setAttribute(QtCore.Qt.WidgetAttribute.WA_DontShowOnScreen, True)
        except Exception:
            pass
        try:
            view.resize(1, 1)
            view.move(-32000, -32000)
            view.hide()
        except Exception:
            pass
        try:
            view.load(QtCore.QUrl("about:blank"))
        except Exception:
            pass
        self._webengine_runtime_prewarm_view = view
        self._webengine_runtime_prewarmed = True
        try:
            self._chart_debug_log("webengine_prewarm init=1")
        except Exception:
            pass
    except Exception:
        return

    try:
        hold_ms = int(os.environ.get("BOT_PREWARM_WEBENGINE_HOLD_MS") or 2200)
    except Exception:
        hold_ms = 2200
    hold_ms = max(500, min(hold_ms, 10000))

    def _cleanup():
        view_obj = getattr(self, "_webengine_runtime_prewarm_view", None)
        self._webengine_runtime_prewarm_view = None
        if view_obj is not None:
            try:
                view_obj.deleteLater()
            except Exception:
                pass

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
    try:
        duration_ms = int(os.environ.get("BOT_TRADINGVIEW_VISIBILITY_GUARD_MS") or 2500)
    except Exception:
        duration_ms = 2500
    duration_ms = max(500, min(duration_ms, 8000))
    try:
        interval_ms = int(os.environ.get("BOT_TRADINGVIEW_VISIBILITY_GUARD_INTERVAL_MS") or 50)
    except Exception:
        interval_ms = 50
    interval_ms = max(20, min(interval_ms, 200))

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
        except Exception:
            pass

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
    try:
        interval_ms = int(os.environ.get("BOT_TRADINGVIEW_VISIBILITY_WATCHDOG_INTERVAL_MS") or 200)
    except Exception:
        interval_ms = 200
    interval_ms = max(50, min(interval_ms, 1000))
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
        except Exception:
            pass

    timer.timeout.connect(_tick)
    timer.start()
    _tick()


def start_tradingview_close_guard(self) -> None:
    if sys.platform != "win32":
        return
    try:
        duration_ms = int(os.environ.get("BOT_TRADINGVIEW_CLOSE_GUARD_MS") or 2500)
    except Exception:
        duration_ms = 2500
    duration_ms = max(500, min(duration_ms, 8000))
    try:
        self._tv_close_guard_until = time.monotonic() + (duration_ms / 1000.0)
    except Exception:
        self._tv_close_guard_until = 0.0
    self._tv_close_guard_active = True


def start_webengine_close_guard(self, *, webengine_charts_allowed) -> None:
    if sys.platform != "win32":
        return
    if not webengine_charts_allowed():
        return
    try:
        duration_ms = int(os.environ.get("BOT_WEBENGINE_CLOSE_GUARD_MS") or 3500)
    except Exception:
        duration_ms = 3500
    duration_ms = max(800, min(duration_ms, 15000))
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
    self._start_webengine_visibility_watchdog()
    try:
        self._chart_debug_log(
            f"webengine_close_guard start duration_ms={duration_ms} until={self._webengine_close_guard_until:.3f}"
        )
    except Exception:
        pass


def start_webengine_visibility_watchdog(self, *, allow_guard_bypass, restore_window_after_guard) -> None:
    if sys.platform != "win32":
        return
    if getattr(self, "_webengine_visibility_watchdog_active", False):
        return
    try:
        interval_ms = int(os.environ.get("BOT_WEBENGINE_CLOSE_GUARD_WATCHDOG_INTERVAL_MS") or 120)
    except Exception:
        interval_ms = 120
    interval_ms = max(30, min(interval_ms, 1000))
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
            except Exception:
                pass
            self._stop_webengine_visibility_watchdog()
            return
        if not getattr(self, "_webengine_close_guard_active", False):
            self._stop_webengine_visibility_watchdog()
            return
        try:
            if not self.isVisible() or self.windowState() & QtCore.Qt.WindowState.WindowMinimized:
                restore_window_after_guard(self)
        except Exception:
            pass

    timer.timeout.connect(_tick)
    timer.start()
    _tick()


def stop_webengine_visibility_watchdog(self) -> None:
    timer = getattr(self, "_webengine_visibility_watchdog_timer", None)
    if timer is not None:
        try:
            timer.stop()
        except Exception:
            pass
        try:
            timer.deleteLater()
        except Exception:
            pass
    self._webengine_visibility_watchdog_timer = None
    self._webengine_visibility_watchdog_active = False


def stop_tradingview_visibility_guard(self) -> None:
    timer = getattr(self, "_tv_visibility_guard_timer", None)
    if timer is not None:
        try:
            timer.stop()
        except Exception:
            pass
        try:
            timer.deleteLater()
        except Exception:
            pass
    self._tv_visibility_guard_timer = None
    self._tv_visibility_guard_active = False


def stop_tradingview_visibility_watchdog(self) -> None:
    timer = getattr(self, "_tv_visibility_watchdog_timer", None)
    if timer is not None:
        try:
            timer.stop()
        except Exception:
            pass
        try:
            timer.deleteLater()
        except Exception:
            pass
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
            except Exception:
                pass
        elif not visible:
            try:
                self.showMaximized()
            except Exception:
                pass
        try:
            self.raise_()
            self.activateWindow()
        except Exception:
            pass

    _restore_once()
    try:
        # WebEngine can minimize the host window a little after the initial
        # hide/minimize event, so keep restoring for a short grace period.
        for delay_ms in (40, 140, 320, 700, 1400, 2400):
            QtCore.QTimer.singleShot(delay_ms, _restore_once)
    except Exception:
        pass
