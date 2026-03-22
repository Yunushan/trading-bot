from __future__ import annotations

import os
import sys

from PyQt6 import QtCore

from ..chart.chart_embed import _chart_safe_mode_enabled, _webengine_charts_allowed

_CPP_CODE_LANGUAGE_KEY = ""


def _on_tab_changed(self, index: int):
    try:
        widget = self.tabs.widget(index)
    except Exception:
        return
    try:
        if widget is getattr(self, "code_tab", None):
            self._start_dependency_usage_auto_poll()
            if str(self.config.get("code_language") or "") == _CPP_CODE_LANGUAGE_KEY:
                self._maybe_auto_prepare_cpp_environment(
                    resolved_targets=getattr(self, "_dep_version_targets", None),
                    reason="code-tab-visible",
                )
        else:
            self._stop_dependency_usage_auto_poll()
    except Exception:
        pass
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
        if not getattr(self, "_dep_version_auto_refresh_done", False):
            self._dep_version_auto_refresh_done = True
            QtCore.QTimer.singleShot(100, self._refresh_dependency_versions)


def bind_main_window_tab_runtime(MainWindow, *, cpp_code_language_key):
    global _CPP_CODE_LANGUAGE_KEY
    _CPP_CODE_LANGUAGE_KEY = str(cpp_code_language_key)
    MainWindow._on_tab_changed = _on_tab_changed
