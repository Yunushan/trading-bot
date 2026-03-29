from __future__ import annotations

from PyQt6 import QtCore, QtWidgets


def build_main_window_tabs_ui(self, *, current_max_closed_history: int) -> int:
    root_layout = QtWidgets.QVBoxLayout(self)
    self.tabs = QtWidgets.QTabWidget()
    self.tabs.currentChanged.connect(self._on_tab_changed)
    self.tabs.tabBarClicked.connect(self._on_tab_bar_clicked)
    try:
        self._store_previous_main_window_event_filter()
        self.tabs.tabBar().installEventFilter(self)
    except Exception:
        pass
    root_layout.addWidget(self.tabs)

    tab1 = QtWidgets.QWidget()
    tab1_layout = QtWidgets.QVBoxLayout(tab1)
    tab1_layout.setContentsMargins(0, 0, 0, 0)
    tab1_layout.setSpacing(0)

    self.dashboard_scroll = QtWidgets.QScrollArea()
    self.dashboard_scroll.setWidgetResizable(True)
    self.dashboard_scroll.setHorizontalScrollBarPolicy(QtCore.Qt.ScrollBarPolicy.ScrollBarAsNeeded)
    self.dashboard_scroll.setVerticalScrollBarPolicy(QtCore.Qt.ScrollBarPolicy.ScrollBarAsNeeded)
    tab1_layout.addWidget(self.dashboard_scroll)

    scroll_contents = QtWidgets.QWidget()
    scroll_layout = QtWidgets.QVBoxLayout(scroll_contents)
    scroll_layout.setContentsMargins(10, 10, 10, 10)
    scroll_layout.setSpacing(10)
    self.dashboard_scroll.setWidget(scroll_contents)

    self._create_dashboard_header_section(scroll_layout)
    runtime_override_group = self._create_dashboard_markets_section(scroll_layout)
    self._create_dashboard_strategy_controls_section(scroll_layout)
    self._create_dashboard_indicator_section(scroll_layout)

    scroll_layout.addWidget(runtime_override_group)
    self._create_dashboard_action_section(scroll_layout)
    self._create_dashboard_log_section(scroll_layout)

    self.tabs.addTab(tab1, "Dashboard")
    self._initialize_dashboard_chart_section()
    updated_max_closed_history = self._initialize_dashboard_runtime_state(
        current_max_closed_history=current_max_closed_history,
        gui_max_closed_history=current_max_closed_history,
    )

    self._initialize_secondary_tabs()
    self._finalize_init_ui()
    return updated_max_closed_history
