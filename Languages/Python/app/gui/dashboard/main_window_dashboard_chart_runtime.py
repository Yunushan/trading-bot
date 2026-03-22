from __future__ import annotations

_QT_CHARTS_AVAILABLE = False


def _initialize_dashboard_chart_section(self):
    if self.chart_enabled:
        chart_tab = self._create_chart_tab()
        self.tabs.addTab(chart_tab, "Chart")
        try:
            self._runtime_lock_widgets.extend(
                [
                    self.chart_market_combo,
                    self.chart_symbol_combo,
                    self.chart_interval_combo,
                    self.chart_view_mode_combo,
                ]
            )
            for widget in (
                self.chart_market_combo,
                self.chart_symbol_combo,
                self.chart_interval_combo,
                self.chart_view_mode_combo,
            ):
                self._register_runtime_active_exemption(widget)
        except Exception:
            pass
        if self.chart_auto_follow:
            self._apply_dashboard_selection_to_chart(load=False)
        elif _QT_CHARTS_AVAILABLE:
            try:
                self.load_chart(auto=True)
            except Exception:
                pass
    else:
        self.chart_tab = None
        self.chart_view = None
        self.chart_view_stack = None
        self.chart_tradingview = None
        self.chart_binance = None
        self.chart_lightweight = None
        self.chart_original_view = None


def bind_main_window_dashboard_chart_runtime(
    MainWindow,
    *,
    qt_charts_available,
):
    global _QT_CHARTS_AVAILABLE

    _QT_CHARTS_AVAILABLE = bool(qt_charts_available)

    MainWindow._initialize_dashboard_chart_section = _initialize_dashboard_chart_section
