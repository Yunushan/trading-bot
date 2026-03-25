from __future__ import annotations

from PyQt6 import QtCore

from . import chart_embed
from . import tradingview_window_suppression_runtime
from ..runtime import main_window_runtime, window_webengine_guard_runtime
from .chart_embed import (
    _configure_tradingview_webengine_env,
    _webengine_charts_allowed,
    _webengine_embed_unavailable_reason,
)


def _ensure_tradingview_widget(self):
    return chart_embed.ensure_tradingview_widget(self)


def _bind_tradingview_ready(self, widget):
    return chart_embed.bind_tradingview_ready(self, widget)


def _ensure_binance_widget(self):
    return chart_embed.ensure_binance_widget(self)


def _ensure_lightweight_widget(self):
    return chart_embed.ensure_lightweight_widget(self)


def _update_chart_overlay_geometry(self):
    return chart_embed.update_chart_overlay_geometry(self)


def _show_chart_switch_overlay(self):
    return chart_embed.show_chart_switch_overlay(self)


def _hide_chart_switch_overlay(self, delay_ms: int = 0):
    return chart_embed.hide_chart_switch_overlay(self, delay_ms=delay_ms)


def _schedule_tradingview_prewarm(self):
    return window_webengine_guard_runtime.schedule_tradingview_prewarm(self)


def _schedule_webengine_runtime_prewarm(self):
    return window_webengine_guard_runtime.schedule_webengine_runtime_prewarm(self)


def _maybe_run_deferred_webengine_prewarm(self):
    return window_webengine_guard_runtime.maybe_run_deferred_webengine_prewarm(self)


def _prewarm_webengine_runtime(self):
    return window_webengine_guard_runtime.prewarm_webengine_runtime(
        self,
        webengine_charts_allowed=_webengine_charts_allowed,
        webengine_embed_unavailable_reason=_webengine_embed_unavailable_reason,
        configure_tradingview_webengine_env=_configure_tradingview_webengine_env,
    )


def _prewarm_tradingview(self):
    return window_webengine_guard_runtime.prewarm_tradingview(self)


def _start_tradingview_visibility_guard(self):
    return window_webengine_guard_runtime.start_tradingview_visibility_guard(self)


def _start_tradingview_visibility_watchdog(self):
    return window_webengine_guard_runtime.start_tradingview_visibility_watchdog(self)


def _start_tradingview_close_guard(self):
    return window_webengine_guard_runtime.start_tradingview_close_guard(self)


def _start_webengine_close_guard(self):
    return window_webengine_guard_runtime.start_webengine_close_guard(
        self,
        webengine_charts_allowed=_webengine_charts_allowed,
    )


def _start_webengine_visibility_watchdog(self):
    return window_webengine_guard_runtime.start_webengine_visibility_watchdog(
        self,
        allow_guard_bypass=main_window_runtime._allow_guard_bypass,
        restore_window_after_guard=main_window_runtime._restore_window_after_guard,
    )


def _stop_webengine_visibility_watchdog(self):
    return window_webengine_guard_runtime.stop_webengine_visibility_watchdog(self)


def _stop_tradingview_visibility_guard(self):
    return window_webengine_guard_runtime.stop_tradingview_visibility_guard(self)


def _stop_tradingview_visibility_watchdog(self):
    return window_webengine_guard_runtime.stop_tradingview_visibility_watchdog(self)


def _start_tradingview_window_suppression(self):
    return tradingview_window_suppression_runtime.start_tradingview_window_suppression(self)


def _prime_tradingview_chart(self, widget):
    return chart_embed.prime_tradingview_chart(self, widget)


def _open_tradingview_external(self) -> bool:
    return chart_embed.open_tradingview_external(self)


def bind_main_window_chart_host_runtime(MainWindow):
    MainWindow._ensure_tradingview_widget = _ensure_tradingview_widget
    MainWindow._bind_tradingview_ready = _bind_tradingview_ready
    MainWindow._ensure_binance_widget = _ensure_binance_widget
    MainWindow._ensure_lightweight_widget = _ensure_lightweight_widget
    MainWindow._update_chart_overlay_geometry = _update_chart_overlay_geometry
    MainWindow._show_chart_switch_overlay = _show_chart_switch_overlay
    MainWindow._hide_chart_switch_overlay = _hide_chart_switch_overlay
    MainWindow._schedule_tradingview_prewarm = _schedule_tradingview_prewarm
    MainWindow._schedule_webengine_runtime_prewarm = _schedule_webengine_runtime_prewarm
    MainWindow._maybe_run_deferred_webengine_prewarm = _maybe_run_deferred_webengine_prewarm
    MainWindow._prewarm_webengine_runtime = _prewarm_webengine_runtime
    MainWindow._prewarm_tradingview = _prewarm_tradingview
    MainWindow._start_tradingview_visibility_guard = _start_tradingview_visibility_guard
    MainWindow._start_tradingview_visibility_watchdog = _start_tradingview_visibility_watchdog
    MainWindow._start_tradingview_close_guard = _start_tradingview_close_guard
    MainWindow._start_webengine_close_guard = _start_webengine_close_guard
    MainWindow._start_webengine_visibility_watchdog = _start_webengine_visibility_watchdog
    MainWindow._stop_webengine_visibility_watchdog = _stop_webengine_visibility_watchdog
    MainWindow._stop_tradingview_visibility_guard = _stop_tradingview_visibility_guard
    MainWindow._stop_tradingview_visibility_watchdog = _stop_tradingview_visibility_watchdog
    MainWindow._start_tradingview_window_suppression = _start_tradingview_window_suppression
    MainWindow._prime_tradingview_chart = _prime_tradingview_chart
    MainWindow._open_tradingview_external = _open_tradingview_external
