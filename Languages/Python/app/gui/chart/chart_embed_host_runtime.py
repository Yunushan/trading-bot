from __future__ import annotations

import time

from PyQt6 import QtCore, QtGui

from . import chart_embed_state_runtime as state


def ensure_tradingview_widget(self):
    if state._chart_safe_mode_enabled():
        return None
    if self.chart_tradingview is not None:
        bind_tradingview_ready(self, self.chart_tradingview)
        return self.chart_tradingview
    if not self._chart_view_tradingview_available:
        return None
    widget_class, _available = state._load_tradingview_widget()
    if widget_class is None:
        self._chart_view_tradingview_available = False
        return None
    self._start_webengine_close_guard()
    try:
        parent = getattr(self, "chart_view_stack", None) or self
        widget = widget_class(parent)
    except Exception:
        self.chart_tradingview = None
        self._chart_view_tradingview_available = False
        return None
    self.chart_tradingview = widget
    self._chart_view_widgets["tradingview"] = widget
    self.chart_view_stack.addWidget(widget)
    bind_tradingview_ready(self, widget)
    return widget


def bind_tradingview_ready(self, widget) -> None:
    if widget is None:
        return
    if getattr(self, "_tradingview_ready_connected", False):
        return
    try:
        if hasattr(widget, "ready"):
            widget.ready.connect(self._on_tradingview_ready)
            self._tradingview_ready_connected = True
    except Exception:
        pass


def ensure_binance_widget(self):
    if state._chart_safe_mode_enabled():
        return None
    if self.chart_binance is not None:
        return self.chart_binance
    if not self._chart_view_binance_available:
        return None
    widget_class, available = state._load_binance_widget()
    if widget_class is None or not available:
        self._chart_view_binance_available = False
        return None
    self._start_webengine_close_guard()
    try:
        parent = getattr(self, "chart_view_stack", None) or self
        widget = widget_class(parent)
    except Exception:
        self._chart_view_binance_available = False
        return None
    self.chart_binance = widget
    self._chart_view_widgets["original"] = widget
    try:
        self.chart_view_stack.addWidget(widget)
    except Exception:
        pass
    return widget


def ensure_lightweight_widget(self):
    if state._chart_safe_mode_enabled():
        return None
    if self.chart_lightweight is not None:
        return self.chart_lightweight
    if not self._chart_view_lightweight_available:
        return None
    widget_class, available = state._load_lightweight_widget()
    if widget_class is None or not available:
        self._chart_view_lightweight_available = False
        return None
    self._start_webengine_close_guard()
    try:
        parent = getattr(self, "chart_view_stack", None) or self
        widget = widget_class(parent)
    except Exception:
        self._chart_view_lightweight_available = False
        return None
    self.chart_lightweight = widget
    self._chart_view_widgets["lightweight"] = widget
    try:
        self.chart_view_stack.addWidget(widget)
    except Exception:
        pass
    return widget


def update_chart_overlay_geometry(self) -> None:
    overlay = getattr(self, "_chart_switch_overlay", None)
    stack = getattr(self, "chart_view_stack", None)
    if overlay is None or stack is None:
        return
    try:
        overlay.setGeometry(stack.rect())
    except Exception:
        pass


def show_chart_switch_overlay(self) -> None:
    if getattr(self, "_chart_switch_overlay_active", False):
        return
    overlay = getattr(self, "_chart_switch_overlay", None)
    stack = getattr(self, "chart_view_stack", None)
    if overlay is None or stack is None:
        return
    update_chart_overlay_geometry(self)
    pixmap = None
    try:
        source = stack.currentWidget()
        if source is not None:
            pixmap = source.grab()
    except Exception:
        pixmap = None
    try:
        if pixmap is not None and not pixmap.isNull():
            overlay.setPixmap(pixmap)
            overlay.setText("")
        else:
            overlay.setPixmap(QtGui.QPixmap())
            overlay.setText("Loading TradingView...")
        overlay.setVisible(True)
        overlay.raise_()
        self._chart_switch_overlay_active = True
    except Exception:
        pass


def hide_chart_switch_overlay(self, delay_ms: int = 0) -> None:
    overlay = getattr(self, "_chart_switch_overlay", None)
    if overlay is None or not getattr(self, "_chart_switch_overlay_active", False):
        return

    def _do_hide():
        try:
            overlay.setVisible(False)
            overlay.setPixmap(QtGui.QPixmap())
            overlay.setText("")
        except Exception:
            pass
        self._chart_switch_overlay_active = False

    if delay_ms and delay_ms > 0:
        QtCore.QTimer.singleShot(int(delay_ms), _do_hide)
    else:
        _do_hide()


def prime_tradingview_chart(self, widget) -> None:
    if widget is None:
        return
    try:
        symbol_text = (self.chart_symbol_combo.currentText() or "").strip().upper()
        interval_text = (self.chart_interval_combo.currentText() or "").strip()
    except Exception:
        return
    if not symbol_text or not interval_text:
        return
    interval_code = self._map_chart_interval(interval_text)
    if not interval_code:
        return
    market_text = self._normalize_chart_market(
        self.chart_market_combo.currentText() if hasattr(self, "chart_market_combo") else None
    )
    tv_symbol = self._format_chart_symbol(symbol_text, market_text)
    try:
        theme_name = (self.theme_combo.currentText() or "").strip()
    except Exception:
        theme_name = self.config.get("theme", "Dark")
    theme_code = "light" if str(theme_name or "").lower().startswith("light") else "dark"
    try:
        widget.set_chart(tv_symbol, interval_code, theme=theme_code, timezone="Etc/UTC")
    except Exception:
        return
    try:
        if hasattr(widget, "warmup"):
            widget.warmup()
    except Exception:
        pass


def open_tradingview_external(self) -> bool:
    try:
        symbol_text = (self.chart_symbol_combo.currentText() or "").strip().upper()
        interval_text = (self.chart_interval_combo.currentText() or "").strip()
    except Exception:
        return False
    if not symbol_text or not interval_text:
        return False
    interval_code = self._map_chart_interval(interval_text)
    if not interval_code:
        interval_code = "60"
    market_text = self._normalize_chart_market(
        self.chart_market_combo.currentText() if hasattr(self, "chart_market_combo") else None
    )
    tv_symbol = self._format_chart_symbol(symbol_text, market_text)
    try:
        now = time.monotonic()
    except Exception:
        now = 0.0
    if now and (now - float(getattr(self, "_tradingview_external_last_open_ts", 0.0) or 0.0)) < 1.0:
        return False
    self._tradingview_external_last_open_ts = now
    url = state._build_tradingview_url(tv_symbol, interval_code)
    try:
        return bool(QtGui.QDesktopServices.openUrl(QtCore.QUrl(url)))
    except Exception:
        return False
