from __future__ import annotations

from . import display_load_runtime, display_payload_runtime, display_render_runtime

QT_CHARTS_AVAILABLE = display_render_runtime.QT_CHARTS_AVAILABLE
QChart = display_render_runtime.QChart
QChartView = display_render_runtime.QChartView
QCandlestickSeries = display_render_runtime.QCandlestickSeries
QCandlestickSet = display_render_runtime.QCandlestickSet
QDateTimeAxis = display_render_runtime.QDateTimeAxis
QValueAxis = display_render_runtime.QValueAxis

_show_chart_status = display_render_runtime._show_chart_status
_render_candlestick_chart = display_render_runtime._render_candlestick_chart
_build_lightweight_payload = display_payload_runtime._build_lightweight_payload
_on_chart_theme_changed = display_load_runtime._on_chart_theme_changed
_on_dashboard_selection_for_chart = display_load_runtime._on_dashboard_selection_for_chart
_is_chart_visible = display_load_runtime._is_chart_visible
load_chart = display_load_runtime.load_chart


def bind_main_window_chart_display_runtime(MainWindow):
    MainWindow._show_chart_status = _show_chart_status
    MainWindow._render_candlestick_chart = _render_candlestick_chart
    MainWindow._build_lightweight_payload = _build_lightweight_payload
    MainWindow._on_chart_theme_changed = _on_chart_theme_changed
    MainWindow._on_dashboard_selection_for_chart = _on_dashboard_selection_for_chart
    MainWindow._is_chart_visible = _is_chart_visible
    MainWindow.load_chart = load_chart


__all__ = [
    "QChart",
    "QChartView",
    "QCandlestickSeries",
    "QCandlestickSet",
    "QDateTimeAxis",
    "QT_CHARTS_AVAILABLE",
    "QValueAxis",
    "_build_lightweight_payload",
    "_is_chart_visible",
    "_on_chart_theme_changed",
    "_on_dashboard_selection_for_chart",
    "_render_candlestick_chart",
    "_show_chart_status",
    "bind_main_window_chart_display_runtime",
    "load_chart",
]
