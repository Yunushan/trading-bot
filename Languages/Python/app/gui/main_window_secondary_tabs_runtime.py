from __future__ import annotations


def _initialize_secondary_tabs(self):
    self._create_positions_tab()
    self._create_backtest_tab()

    liquidation_tab = self._init_liquidation_heatmap_tab()
    if liquidation_tab is not None:
        self.liquidation_tab = liquidation_tab
        self.tabs.addTab(liquidation_tab, "Liquidation Heatmap")

    code_tab = self._init_code_language_tab()
    if code_tab is not None:
        self.code_tab = code_tab
        self.tabs.addTab(code_tab, "Code Languages")


def bind_main_window_secondary_tabs_runtime(MainWindow):
    MainWindow._initialize_secondary_tabs = _initialize_secondary_tabs
