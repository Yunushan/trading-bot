from __future__ import annotations

import sys

from PyQt6 import QtCore, QtWidgets

try:
    from PyQt6.QtCharts import QChartView
except Exception:
    QChartView = None

from . import chart_embed
from .chart_embed import (
    _binance_unavailable_reason,
    _lightweight_unavailable_reason,
    _native_chart_host_prewarm_enabled,
    _tradingview_unavailable_reason,
    _webengine_charts_allowed,
)
from .chart_widgets import InteractiveChartView, SimpleCandlestickWidget

_CHART_MARKET_OPTIONS = ()
_CHART_INTERVAL_OPTIONS = ()
_DISABLE_TRADINGVIEW = False
_DISABLE_CHARTS = False
_QT_CHARTS_AVAILABLE = False


def _create_chart_tab(self):
    tab = QtWidgets.QWidget()
    self.chart_tab = tab
    layout = QtWidgets.QVBoxLayout(tab)
    layout.setContentsMargins(10, 10, 10, 10)
    layout.setSpacing(8)

    controls_layout = QtWidgets.QHBoxLayout()
    layout.addLayout(controls_layout)

    controls_layout.addWidget(QtWidgets.QLabel("Market:"))
    self.chart_market_combo = QtWidgets.QComboBox()
    for opt in _CHART_MARKET_OPTIONS:
        self.chart_market_combo.addItem(opt)
    controls_layout.addWidget(self.chart_market_combo)

    controls_layout.addWidget(QtWidgets.QLabel("Symbol:"))
    self.chart_symbol_combo = QtWidgets.QComboBox()
    self.chart_symbol_combo.setEditable(False)
    self.chart_symbol_combo.setSizeAdjustPolicy(QtWidgets.QComboBox.SizeAdjustPolicy.AdjustToContents)
    controls_layout.addWidget(self.chart_symbol_combo)

    controls_layout.addWidget(QtWidgets.QLabel("Interval:"))
    self.chart_interval_combo = QtWidgets.QComboBox()
    self.chart_interval_combo.setEditable(False)
    self.chart_interval_combo.setSizeAdjustPolicy(QtWidgets.QComboBox.SizeAdjustPolicy.AdjustToContents)
    for iv in _CHART_INTERVAL_OPTIONS:
        self.chart_interval_combo.addItem(iv)
    controls_layout.addWidget(self.chart_interval_combo)

    controls_layout.addWidget(QtWidgets.QLabel("View:"))
    self.chart_view_mode_combo = QtWidgets.QComboBox()
    self.chart_view_mode_combo.setSizeAdjustPolicy(QtWidgets.QComboBox.SizeAdjustPolicy.AdjustToContents)
    controls_layout.addWidget(self.chart_view_mode_combo)

    controls_layout.addStretch()
    chart_status_widget = QtWidgets.QWidget()
    chart_status_layout = QtWidgets.QHBoxLayout(chart_status_widget)
    chart_status_layout.setContentsMargins(0, 0, 0, 0)
    chart_status_layout.setSpacing(8)
    self.pnl_active_label_chart = QtWidgets.QLabel()
    self.pnl_closed_label_chart = QtWidgets.QLabel()
    self.bot_status_label_chart = QtWidgets.QLabel()
    self.bot_time_label_chart = QtWidgets.QLabel("Bot Active Time: --")
    for lbl in (self.pnl_active_label_chart, self.pnl_closed_label_chart):
        lbl.setAlignment(QtCore.Qt.AlignmentFlag.AlignLeft | QtCore.Qt.AlignmentFlag.AlignVCenter)
        chart_status_layout.addWidget(lbl)
    chart_status_layout.addStretch()
    for lbl in (self.bot_status_label_chart, self.bot_time_label_chart):
        lbl.setAlignment(QtCore.Qt.AlignmentFlag.AlignRight | QtCore.Qt.AlignmentFlag.AlignVCenter)
        chart_status_layout.addWidget(lbl)
    self._register_pnl_summary_labels(self.pnl_active_label_chart, self.pnl_closed_label_chart)
    controls_layout.addWidget(chart_status_widget)

    self._chart_view_widgets = {}
    self.chart_view_stack = QtWidgets.QStackedWidget()
    layout.addWidget(self.chart_view_stack, stretch=1)
    if _native_chart_host_prewarm_enabled():
        for widget in (tab, self.chart_view_stack):
            try:
                widget.setAttribute(QtCore.Qt.WidgetAttribute.WA_NativeWindow, True)
            except Exception:
                pass
            try:
                widget.winId()
            except Exception:
                pass
    try:
        self._chart_switch_overlay = QtWidgets.QLabel(self.chart_view_stack)
        self._chart_switch_overlay.setVisible(False)
        self._chart_switch_overlay.setAlignment(QtCore.Qt.AlignmentFlag.AlignCenter)
        self._chart_switch_overlay.setScaledContents(True)
        self._chart_switch_overlay.setStyleSheet(
            "background-color: #0b0e11; color: #94a3b8; font-size: 15px;"
        )
        self._chart_switch_overlay.setAttribute(
            QtCore.Qt.WidgetAttribute.WA_TransparentForMouseEvents, True
        )
        self._update_chart_overlay_geometry()
        if not self._chart_view_stack_event_filter_installed:
            self.chart_view_stack.installEventFilter(self)
            self._chart_view_stack_event_filter_installed = True
    except Exception:
        self._chart_switch_overlay = None

    self.chart_tradingview = None
    self._chart_view_tradingview_available = (
        (getattr(chart_embed, "_TRADINGVIEW_IMPORT_ERROR", None) is None)
        and (not _DISABLE_TRADINGVIEW)
        and (not _DISABLE_CHARTS)
        and _webengine_charts_allowed()
    )
    self.chart_binance = None
    self.chart_lightweight = None
    self._chart_view_binance_available = (
        (getattr(chart_embed, "_BINANCE_IMPORT_ERROR", None) is None)
        and (not _DISABLE_CHARTS)
        and _webengine_charts_allowed()
    )
    self._chart_view_lightweight_available = (
        (getattr(chart_embed, "_LIGHTWEIGHT_IMPORT_ERROR", None) is None)
        and (not _DISABLE_CHARTS)
        and _webengine_charts_allowed()
    )

    self.chart_original_view = None
    if _QT_CHARTS_AVAILABLE and QChartView is not None:
        view = InteractiveChartView()
        try:
            view.setMinimumHeight(300)
        except Exception:
            pass
        self.chart_original_view = view
    else:
        self.chart_original_view = SimpleCandlestickWidget()
    if self.chart_original_view is not None:
        self._chart_view_widgets["legacy"] = self.chart_original_view
        self.chart_view_stack.addWidget(self.chart_original_view)

    self.chart_view_mode_combo.clear()
    tv_label = "TradingView"
    if self._chart_view_tradingview_available:
        self.chart_view_mode_combo.addItem(tv_label, "tradingview")
    else:
        self.chart_view_mode_combo.addItem(tv_label, "tradingview")
        try:
            idx = self.chart_view_mode_combo.findData("tradingview")
            if idx >= 0:
                model = self.chart_view_mode_combo.model()
                model.setData(model.index(idx, 0), QtCore.Qt.ItemDataRole.EnabledRole, False)
                model.setData(
                    model.index(idx, 0),
                    _tradingview_unavailable_reason(),
                    QtCore.Qt.ItemDataRole.ToolTipRole,
                )
        except Exception:
            pass
    self.chart_view_mode_combo.addItem("Original", "original")
    if not self._chart_view_binance_available:
        try:
            idx = self.chart_view_mode_combo.findData("original")
            if idx >= 0:
                model = self.chart_view_mode_combo.model()
                model.setData(model.index(idx, 0), QtCore.Qt.ItemDataRole.EnabledRole, False)
                model.setData(
                    model.index(idx, 0),
                    _binance_unavailable_reason(),
                    QtCore.Qt.ItemDataRole.ToolTipRole,
                )
        except Exception:
            pass
    self.chart_view_mode_combo.addItem("TradingView Lightweight", "lightweight")
    if not self._chart_view_lightweight_available:
        try:
            idx = self.chart_view_mode_combo.findData("lightweight")
            if idx >= 0:
                model = self.chart_view_mode_combo.model()
                model.setData(model.index(idx, 0), QtCore.Qt.ItemDataRole.EnabledRole, False)
                model.setData(
                    model.index(idx, 0),
                    _lightweight_unavailable_reason(),
                    QtCore.Qt.ItemDataRole.ToolTipRole,
                )
        except Exception:
            pass

    requested_mode = str(self.chart_config.get("view_mode") or "").strip().lower()
    if requested_mode not in {"tradingview", "original", "lightweight"}:
        requested_mode = "tradingview" if self._chart_view_tradingview_available else "original"
    if requested_mode == "tradingview" and not self._chart_view_tradingview_available:
        requested_mode = "original"
    if requested_mode == "lightweight" and not self._chart_view_lightweight_available:
        requested_mode = "original"
    self.chart_config["view_mode"] = requested_mode

    self._pending_tradingview_mode = False
    if self._chart_view_tradingview_available and sys.platform != "win32":
        try:
            self._ensure_tradingview_widget()
        except Exception:
            pass
    try:
        idx = self.chart_view_mode_combo.findData(requested_mode)
        if idx >= 0:
            blocker = QtCore.QSignalBlocker(self.chart_view_mode_combo)
            self.chart_view_mode_combo.setCurrentIndex(idx)
            del blocker
    except Exception:
        pass

    allow_tradingview_init = sys.platform != "win32"
    self._apply_chart_view_mode(requested_mode, initial=True, allow_tradingview_init=allow_tradingview_init)
    self.chart_view_mode_combo.currentIndexChanged.connect(self._on_chart_view_mode_changed)

    self.chart_symbol_combo.currentTextChanged.connect(self._on_chart_controls_changed)
    self.chart_interval_combo.currentTextChanged.connect(self._on_chart_controls_changed)
    self.chart_market_combo.currentTextChanged.connect(self._on_chart_market_changed)

    self._restore_chart_controls_from_config()
    self._on_chart_market_changed(self.chart_market_combo.currentText())
    self._update_bot_status()
    self._load_chart_symbols_async("Futures")
    self._load_chart_symbols_async("Spot")

    if not getattr(self, "_chart_theme_signal_installed", False):
        try:
            self.theme_combo.currentTextChanged.connect(self._on_chart_theme_changed)
            self._chart_theme_signal_installed = True
        except Exception:
            pass

    self._schedule_tradingview_prewarm()

    return tab


def bind_main_window_chart_tab(
    MainWindow,
    *,
    chart_market_options,
    chart_interval_options,
    disable_tradingview,
    disable_charts,
    qt_charts_available,
):
    global _CHART_MARKET_OPTIONS
    global _CHART_INTERVAL_OPTIONS
    global _DISABLE_TRADINGVIEW
    global _DISABLE_CHARTS
    global _QT_CHARTS_AVAILABLE

    _CHART_MARKET_OPTIONS = tuple(chart_market_options)
    _CHART_INTERVAL_OPTIONS = tuple(chart_interval_options)
    _DISABLE_TRADINGVIEW = bool(disable_tradingview)
    _DISABLE_CHARTS = bool(disable_charts)
    _QT_CHARTS_AVAILABLE = bool(qt_charts_available)

    MainWindow._create_chart_tab = _create_chart_tab
