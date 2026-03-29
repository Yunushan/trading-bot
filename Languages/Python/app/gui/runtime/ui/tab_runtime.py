from __future__ import annotations

import os
import sys
import time

from PyQt6 import QtCore, QtWidgets

from ...chart.chart_embed import _chart_safe_mode_enabled, _webengine_charts_allowed

_CPP_CODE_LANGUAGE_KEY = ""
_LAZY_SECONDARY_TAB_PROPERTY = "_bot_lazy_secondary_tab_key"


def _code_tab_visibility_auto_prepare_cpp_enabled() -> bool:
    default_flag = "0" if sys.platform == "win32" else "1"
    raw_value = str(os.environ.get("BOT_CODE_TAB_AUTO_PREPARE_CPP", default_flag) or default_flag).strip().lower()
    return raw_value not in {"0", "false", "no", "off"}


def _code_tab_open_auto_refresh_versions_enabled() -> bool:
    raw_value = str(os.environ.get("BOT_CODE_TAB_AUTO_OPEN_CHECK_VERSIONS", "1") or "1").strip().lower()
    return raw_value not in {"0", "false", "no", "off"}


def _mark_recent_code_tab_switch(self) -> None:
    try:
        duration_ms = int(os.environ.get("BOT_CODE_TO_CHART_COOLDOWN_MS") or 1100)
    except Exception:
        duration_ms = 1100
    duration_ms = max(0, min(duration_ms, 5000))
    try:
        self._recent_code_tab_switch_until = time.monotonic() + (duration_ms / 1000.0)
    except Exception:
        self._recent_code_tab_switch_until = 0.0


def _recent_code_tab_switch_active(self) -> bool:
    try:
        until = float(getattr(self, "_recent_code_tab_switch_until", 0.0) or 0.0)
    except Exception:
        until = 0.0
    if not until:
        return False
    try:
        now = time.monotonic()
    except Exception:
        now = 0.0
    if now >= until:
        try:
            self._recent_code_tab_switch_until = 0.0
        except Exception:
            pass
        return False
    return True


def _cancel_code_tab_auto_refresh_versions(self) -> None:
    try:
        token = int(getattr(self, "_code_tab_auto_refresh_versions_token", 0) or 0) + 1
    except Exception:
        token = 1
    self._code_tab_auto_refresh_versions_token = token
    self._code_tab_auto_refresh_versions_pending = False


def _schedule_code_tab_auto_refresh_versions(self) -> None:
    if not _code_tab_open_auto_refresh_versions_enabled():
        return
    try:
        tabs = getattr(self, "tabs", None)
        code_tab = getattr(self, "code_tab", None)
        if tabs is None or code_tab is None or tabs.currentWidget() is not code_tab:
            return
    except Exception:
        return
    if getattr(self, "_dep_version_refresh_inflight", False):
        return
    if getattr(self, "_dep_version_auto_refresh_done", False):
        return
    if getattr(self, "_code_tab_auto_refresh_versions_pending", False):
        return
    try:
        delay_ms = int(os.environ.get("BOT_CODE_TAB_AUTO_OPEN_CHECK_VERSIONS_DELAY_MS") or 650)
    except Exception:
        delay_ms = 650
    delay_ms = max(100, min(delay_ms, 5000))
    try:
        token = int(getattr(self, "_code_tab_auto_refresh_versions_token", 0) or 0) + 1
    except Exception:
        token = 1
    self._code_tab_auto_refresh_versions_token = token
    self._code_tab_auto_refresh_versions_pending = True

    def _run() -> None:
        current_token = getattr(self, "_code_tab_auto_refresh_versions_token", None)
        self._code_tab_auto_refresh_versions_pending = False
        if current_token != token:
            return
        try:
            tabs = getattr(self, "tabs", None)
            code_tab = getattr(self, "code_tab", None)
            if tabs is None or code_tab is None or tabs.currentWidget() is not code_tab:
                return
        except Exception:
            return
        if getattr(self, "_dep_version_refresh_inflight", False):
            return
        try:
            self._dep_version_auto_refresh_done = True
        except Exception:
            pass
        try:
            self._refresh_dependency_versions()
        except Exception:
            try:
                self._dep_version_auto_refresh_done = False
            except Exception:
                pass

    QtCore.QTimer.singleShot(delay_ms, _run)


def _maybe_start_code_tab_window_suppression(self, index: int) -> None:
    try:
        tabs = getattr(self, "tabs", None)
        if tabs is None or index < 0:
            return
        widget = tabs.widget(index)
    except Exception:
        return
    try:
        lazy_secondary_key = str(widget.property(_LAZY_SECONDARY_TAB_PROPERTY) or "").strip().lower()
    except Exception:
        lazy_secondary_key = ""
    if lazy_secondary_key == "code" or widget is getattr(self, "code_tab", None):
        _mark_recent_code_tab_switch(self)
        try:
            self._start_code_tab_window_suppression()
        except Exception:
            pass


def _on_tab_bar_clicked(self, index: int) -> None:
    return _maybe_start_code_tab_window_suppression(self, index)


def _tab_bar_event_target_index(self, obj, event) -> int:  # noqa: ANN001
    try:
        tabs = getattr(self, "tabs", None)
        tab_bar = tabs.tabBar() if tabs is not None else None
    except Exception:
        tab_bar = None
    if tab_bar is None or obj is not tab_bar or event is None:
        return -1
    try:
        position = event.position()
        point = position.toPoint() if position is not None else None
    except Exception:
        point = None
    if point is None:
        try:
            point = event.pos()
        except Exception:
            point = None
    if point is None:
        return -1
    try:
        return int(tab_bar.tabAt(point))
    except Exception:
        return -1


def _event_filter(self, obj, event):  # noqa: ANN001, N802
    try:
        if event is not None and event.type() in {
            QtCore.QEvent.Type.MouseButtonPress,
            QtCore.QEvent.Type.MouseButtonDblClick,
        }:
            index = self._tab_bar_event_target_index(obj, event)
            if index >= 0:
                _maybe_start_code_tab_window_suppression(self, index)
    except Exception:
        pass
    previous_event_filter = getattr(self, "_previous_main_window_event_filter", None)
    if callable(previous_event_filter):
        try:
            return previous_event_filter(obj, event)
        except TypeError:
            pass
        except Exception:
            pass
    return QtWidgets.QWidget.eventFilter(self, obj, event)


def _on_tab_changed(self, index: int):
    _maybe_start_code_tab_window_suppression(self, index)
    try:
        widget = self.tabs.widget(index)
    except Exception:
        return
    try:
        if widget is getattr(self, "code_tab", None):
            self._start_dependency_usage_auto_poll()
            _schedule_code_tab_auto_refresh_versions(self)
            if (
                str(self.config.get("code_language") or "") == _CPP_CODE_LANGUAGE_KEY
                and _code_tab_visibility_auto_prepare_cpp_enabled()
            ):
                self._maybe_auto_prepare_cpp_environment(
                    resolved_targets=getattr(self, "_dep_version_targets", None),
                    reason="code-tab-visible",
                )
        else:
            self._stop_dependency_usage_auto_poll()
    except Exception:
        pass
    try:
        lazy_secondary_key = str(widget.property(_LAZY_SECONDARY_TAB_PROPERTY) or "").strip().lower()
    except Exception:
        lazy_secondary_key = ""
    if lazy_secondary_key != "code" and widget is not getattr(self, "code_tab", None):
        _cancel_code_tab_auto_refresh_versions(self)
        try:
            self._stop_code_tab_window_suppression()
        except Exception:
            pass
    if lazy_secondary_key:
        if lazy_secondary_key == "code":
            try:
                self._start_code_tab_window_suppression()
            except Exception:
                pass
        delay_ms = 0
        only_if_current = False
        try:
            if lazy_secondary_key == "code":
                delay_ms = int(self._lazy_secondary_tab_load_delay_ms(lazy_secondary_key))
                only_if_current = True
        except Exception:
            delay_ms = 0
            only_if_current = False
        try:
            QtCore.QTimer.singleShot(
                max(0, int(delay_ms)),
                lambda key=lazy_secondary_key, window=self, current_only=only_if_current: (
                    window._load_lazy_secondary_tab(key, only_if_current=current_only)
                ),
            )
        except Exception:
            pass
        return
    if widget is getattr(self, "chart_tab", None):
        try:
            combo_mode = self.chart_view_mode_combo.currentData()
        except Exception:
            combo_mode = None
        if not combo_mode:
            try:
                combo_mode = self.chart_view_mode_combo.currentText()
            except Exception:
                combo_mode = ""
        combo_mode = str(combo_mode or "").strip().lower()
        try:
            env_disable = str(os.environ.get("BOT_DISABLE_WEBENGINE_CHARTS", "")).strip()
            env_safe = str(os.environ.get("BOT_SAFE_CHART_TAB", "")).strip()
            tv_flag = str(os.environ.get("BOT_TRADINGVIEW_WINDOW_SUPPRESS", "")).strip()
            self._chart_debug_log(
                f"chart_tab_selected mode={combo_mode} webengine_allowed={int(_webengine_charts_allowed())} "
                f"safe_mode={int(_chart_safe_mode_enabled())} disable_env={env_disable!r} "
                f"safe_env={env_safe!r} tv_suppress={tv_flag!r}"
            )
        except Exception:
            pass
        if _recent_code_tab_switch_active(self):
            try:
                self._chart_debug_log("chart_tab_deferred_after_code_switch=1")
            except Exception:
                pass
            legacy = self._chart_view_widgets.get("legacy")
            if legacy is not None:
                try:
                    self.chart_view = legacy
                    idx = self.chart_view_stack.indexOf(legacy)
                    if idx >= 0:
                        self.chart_view_stack.setCurrentIndex(idx)
                except Exception:
                    pass
            try:
                if self._chart_pending_initial_load or self._chart_needs_render:
                    self.load_chart(auto=True)
                self._chart_pending_initial_load = False
            except Exception:
                pass
            if not getattr(self, "_chart_tab_resume_after_code_timer_active", False):
                self._chart_tab_resume_after_code_timer_active = True

                def _resume_chart_tab() -> None:
                    self._chart_tab_resume_after_code_timer_active = False
                    try:
                        tabs = getattr(self, "tabs", None)
                        chart_tab = getattr(self, "chart_tab", None)
                        if tabs is None or chart_tab is None or tabs.currentWidget() is not chart_tab:
                            return
                    except Exception:
                        return
                    try:
                        self._on_tab_changed(self.tabs.currentIndex())
                    except Exception:
                        pass

                try:
                    delay_ms = int(os.environ.get("BOT_CODE_TO_CHART_RESUME_MS") or 950)
                except Exception:
                    delay_ms = 950
                delay_ms = max(100, min(delay_ms, 5000))
                QtCore.QTimer.singleShot(delay_ms, _resume_chart_tab)
            return
        if _chart_safe_mode_enabled() and combo_mode in {"tradingview", "original", "lightweight"}:
            try:
                self._chart_debug_log("chart_tab_safe_mode_redirect=1")
            except Exception:
                pass
            if combo_mode == "tradingview":
                opened = False
                try:
                    opened = self._open_tradingview_external()
                except Exception:
                    opened = False
                if opened:
                    self._show_chart_status(
                        "TradingView opened in your browser. Set BOT_SAFE_CHART_TAB=0 to embed.",
                        color="#94a3b8",
                    )
                else:
                    self._show_chart_status(
                        "TradingView embed disabled. Set BOT_SAFE_CHART_TAB=0 to embed.",
                        color="#f59e0b",
                    )
            else:
                self._show_chart_status(
                    "Web charts disabled for stability. Set BOT_SAFE_CHART_TAB=0 to enable.",
                    color="#f59e0b",
                )
            legacy = self._chart_view_widgets.get("legacy")
            if legacy is not None:
                try:
                    self.chart_view = legacy
                    idx = self.chart_view_stack.indexOf(legacy)
                    if idx >= 0:
                        self.chart_view_stack.setCurrentIndex(idx)
                except Exception:
                    pass
            if self._chart_needs_render or self._chart_pending_initial_load:
                self.load_chart(auto=True)
            self._chart_pending_initial_load = False
            return
        if self._pending_tradingview_mode:
            allow_tradingview_init = sys.platform != "win32"
            if not allow_tradingview_init:
                allow_flag = str(os.environ.get("BOT_ALLOW_TRADINGVIEW_WINDOWS", "")).strip().lower()
                allow_tradingview_init = allow_flag in {"1", "true", "yes", "on"}
            self._apply_chart_view_mode("tradingview", allow_tradingview_init=allow_tradingview_init)
        pending_web = getattr(self, "_pending_webengine_mode", None)
        if pending_web:
            self._pending_webengine_mode = None
            self._apply_chart_view_mode(str(pending_web), allow_tradingview_init=True)
        if getattr(self, "_pending_tradingview_switch", False):
            self._on_tradingview_ready()
        if self._chart_pending_initial_load:
            self.load_chart(auto=True)
        elif self.chart_auto_follow:
            self._apply_dashboard_selection_to_chart(load=True)
        elif self._chart_needs_render:
            self.load_chart(auto=True)
        self._chart_pending_initial_load = False
    elif widget is getattr(self, "liquidation_tab", None):
        pass
    elif widget is getattr(self, "code_tab", None):
        pass


def bind_main_window_tab_runtime(MainWindow, *, cpp_code_language_key):
    global _CPP_CODE_LANGUAGE_KEY
    _CPP_CODE_LANGUAGE_KEY = str(cpp_code_language_key)
    previous_event_filter = getattr(MainWindow, "eventFilter", None)
    if callable(previous_event_filter):
        def _store_previous_event_filter(self) -> None:
            if getattr(self, "_previous_main_window_event_filter", None) is not None:
                return
            try:
                self._previous_main_window_event_filter = previous_event_filter.__get__(self, MainWindow)
            except Exception:
                self._previous_main_window_event_filter = None
    else:
        def _store_previous_event_filter(self) -> None:
            self._previous_main_window_event_filter = None

    MainWindow._store_previous_main_window_event_filter = _store_previous_event_filter
    MainWindow._tab_bar_event_target_index = _tab_bar_event_target_index
    MainWindow._on_tab_changed = _on_tab_changed
    MainWindow._on_tab_bar_clicked = _on_tab_bar_clicked
    MainWindow.eventFilter = _event_filter
