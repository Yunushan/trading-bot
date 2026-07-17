from __future__ import annotations

from PyQt6 import QtCore, QtWidgets

from app.gui.runtime.ui import design_layout_runtime


def build_main_window_tabs_ui(self, *, current_max_closed_history: int) -> int:
    root_layout = QtWidgets.QVBoxLayout(self)
    self.workspace_root_layout = root_layout
    body_layout = design_layout_runtime.build_workspace_shell(self, root_layout)
    self.tabs = QtWidgets.QTabWidget()
    self.tabs.currentChanged.connect(self._on_tab_changed)
    self.tabs.currentChanged.connect(lambda index: design_layout_runtime.update_workspace_page(self, index))
    self.tabs.tabBarClicked.connect(self._on_tab_bar_clicked)
    try:
        self._store_previous_main_window_event_filter()
        self.tabs.tabBar().installEventFilter(self)
    except Exception:
        pass
    body_layout.addWidget(self.tabs, 1)

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
    self.dashboard_scroll_contents = scroll_contents
    self.dashboard_scroll_layout = scroll_layout
    scroll_layout.setContentsMargins(10, 10, 10, 10)
    scroll_layout.setSpacing(10)
    self._classic_dashboard_layout_margins = (10, 10, 10, 10)
    self._classic_dashboard_layout_spacing = 10
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
    design_layout_runtime.sync_workspace_navigation(self)
    self._finalize_init_ui()
    return updated_max_closed_history
