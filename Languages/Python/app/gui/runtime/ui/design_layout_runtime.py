from __future__ import annotations

from PyQt6 import QtCore, QtWidgets

from .theme_styles import DESIGN_CLASSIC, DESIGN_WORKSTATION


def _layout_margins(layout) -> tuple[int, int, int, int]:
    margins = layout.contentsMargins()
    return margins.left(), margins.top(), margins.right(), margins.bottom()


def build_workspace_shell(self, root_layout: QtWidgets.QVBoxLayout) -> QtWidgets.QHBoxLayout:
    self._classic_root_layout_margins = _layout_margins(root_layout)
    self._classic_root_layout_spacing = root_layout.spacing()
    self.workspace_header = QtWidgets.QFrame(self)
    self.workspace_header.setObjectName("workspaceHeader")
    header_layout = QtWidgets.QHBoxLayout(self.workspace_header)
    header_layout.setContentsMargins(18, 10, 18, 10)
    header_layout.setSpacing(14)

    title_stack = QtWidgets.QWidget(self.workspace_header)
    title_layout = QtWidgets.QVBoxLayout(title_stack)
    title_layout.setContentsMargins(0, 0, 0, 0)
    title_layout.setSpacing(1)
    title = QtWidgets.QLabel("Trading Workspace", title_stack)
    title.setObjectName("workspaceHeaderTitle")
    self.workspace_page_label = QtWidgets.QLabel("Dashboard", title_stack)
    self.workspace_page_label.setObjectName("workspacePageTitle")
    title_layout.addWidget(title)
    title_layout.addWidget(self.workspace_page_label)
    header_layout.addWidget(title_stack)
    header_layout.addStretch(1)

    self.pnl_active_label_workspace = QtWidgets.QLabel(self.workspace_header)
    self.pnl_active_label_workspace.setProperty("pnlPrefix", "Active PNL")
    self.pnl_active_label_workspace.setObjectName("workspaceKpi")
    self.pnl_closed_label_workspace = QtWidgets.QLabel(self.workspace_header)
    self.pnl_closed_label_workspace.setProperty("pnlPrefix", "Closed PNL")
    self.pnl_closed_label_workspace.setObjectName("workspaceKpi")
    self.bot_status_label_workspace = QtWidgets.QLabel("Bot Status: OFF", self.workspace_header)
    self.bot_status_label_workspace.setObjectName("workspaceKpi")
    self.bot_time_label_workspace = QtWidgets.QLabel("Bot Active Time: --", self.workspace_header)
    self.bot_time_label_workspace.setObjectName("workspaceKpi")
    for label in (
        self.pnl_active_label_workspace,
        self.pnl_closed_label_workspace,
        self.bot_status_label_workspace,
        self.bot_time_label_workspace,
    ):
        label.setAlignment(QtCore.Qt.AlignmentFlag.AlignCenter)
        header_layout.addWidget(label)

    register_pnl = getattr(self, "_register_pnl_summary_labels", None)
    if callable(register_pnl):
        register_pnl(self.pnl_active_label_workspace, self.pnl_closed_label_workspace)

    self.workspace_classic_btn = QtWidgets.QPushButton("Classic Layout", self.workspace_header)
    self.workspace_classic_btn.setObjectName("workspaceClassicButton")
    self.workspace_classic_btn.clicked.connect(lambda: select_design(self, DESIGN_CLASSIC))
    header_layout.addWidget(self.workspace_classic_btn)
    root_layout.addWidget(self.workspace_header)

    self.workspace_body = QtWidgets.QWidget(self)
    self.workspace_body.setObjectName("workspaceBody")
    body_layout = QtWidgets.QHBoxLayout(self.workspace_body)
    body_layout.setContentsMargins(0, 0, 0, 0)
    body_layout.setSpacing(0)

    self.workspace_nav_rail = QtWidgets.QFrame(self.workspace_body)
    self.workspace_nav_rail.setObjectName("workspaceNavigationRail")
    rail_layout = QtWidgets.QVBoxLayout(self.workspace_nav_rail)
    rail_layout.setContentsMargins(10, 14, 10, 10)
    rail_layout.setSpacing(8)
    section_label = QtWidgets.QLabel("OPERATIONS", self.workspace_nav_rail)
    section_label.setObjectName("workspaceNavigationLabel")
    rail_layout.addWidget(section_label)
    self.workspace_navigation = QtWidgets.QListWidget(self.workspace_nav_rail)
    self.workspace_navigation.setObjectName("workspaceNavigation")
    self.workspace_navigation.setSelectionMode(
        QtWidgets.QAbstractItemView.SelectionMode.SingleSelection
    )
    self.workspace_navigation.setHorizontalScrollBarPolicy(
        QtCore.Qt.ScrollBarPolicy.ScrollBarAlwaysOff
    )
    self.workspace_navigation.setUniformItemSizes(True)
    self.workspace_navigation.currentRowChanged.connect(
        lambda row: select_workspace_page(self, row)
    )
    rail_layout.addWidget(self.workspace_navigation, 1)
    body_layout.addWidget(self.workspace_nav_rail)
    root_layout.addWidget(self.workspace_body, 1)
    return body_layout


def select_design(self, design: str) -> None:
    combo = getattr(self, "design_combo", None)
    if combo is not None:
        index = combo.findText(design)
        if index >= 0:
            combo.setCurrentIndex(index)
            return
    apply_design = getattr(self, "apply_design", None)
    if callable(apply_design):
        apply_design(design)


def select_workspace_page(self, row: int) -> None:
    tabs = getattr(self, "tabs", None)
    if tabs is None or row < 0 or row >= tabs.count():
        return
    if tabs.currentIndex() != row:
        tabs.setCurrentIndex(row)


def sync_workspace_navigation(self, current_index: int | None = None) -> None:
    tabs = getattr(self, "tabs", None)
    navigation = getattr(self, "workspace_navigation", None)
    if tabs is None or navigation is None:
        return
    selected_index = tabs.currentIndex() if current_index is None else int(current_index)
    with QtCore.QSignalBlocker(navigation):
        navigation.clear()
        for index in range(tabs.count()):
            item = QtWidgets.QListWidgetItem(tabs.tabText(index))
            item.setData(QtCore.Qt.ItemDataRole.UserRole, index)
            navigation.addItem(item)
        if 0 <= selected_index < navigation.count():
            navigation.setCurrentRow(selected_index)
    update_workspace_page(self, selected_index)


def update_workspace_page(self, index: int) -> None:
    tabs = getattr(self, "tabs", None)
    navigation = getattr(self, "workspace_navigation", None)
    if tabs is None or index < 0 or index >= tabs.count():
        return
    if navigation is not None and navigation.currentRow() != index:
        with QtCore.QSignalBlocker(navigation):
            navigation.setCurrentRow(index)
    page_label = getattr(self, "workspace_page_label", None)
    if page_label is not None:
        page_label.setText(tabs.tabText(index))


def apply_design_layout(self, design: str) -> None:
    workstation = str(design or "").strip().lower() == DESIGN_WORKSTATION.lower()
    header = getattr(self, "workspace_header", None)
    rail = getattr(self, "workspace_nav_rail", None)
    tabs = getattr(self, "tabs", None)
    root_layout = getattr(self, "workspace_root_layout", None)
    dashboard_layout = getattr(self, "dashboard_scroll_layout", None)
    dashboard_status = getattr(self, "dashboard_status_widget", None)

    if header is not None:
        header.setVisible(workstation)
    if rail is not None:
        rail.setVisible(workstation)
        rail.setFixedWidth(210 if workstation else 0)
    if tabs is not None:
        tabs.tabBar().setVisible(not workstation)
        tabs.setDocumentMode(workstation)
        if workstation:
            sync_workspace_navigation(self)
    if root_layout is not None:
        classic_margins = getattr(self, "_classic_root_layout_margins", (11, 11, 11, 11))
        classic_spacing = int(getattr(self, "_classic_root_layout_spacing", 6))
        root_layout.setContentsMargins(*(0, 0, 0, 0) if workstation else classic_margins)
        root_layout.setSpacing(0 if workstation else classic_spacing)
    if dashboard_layout is not None:
        classic_margins = getattr(self, "_classic_dashboard_layout_margins", (10, 10, 10, 10))
        classic_spacing = int(getattr(self, "_classic_dashboard_layout_spacing", 10))
        dashboard_layout.setContentsMargins(*(18, 14, 18, 18) if workstation else classic_margins)
        dashboard_layout.setSpacing(12 if workstation else classic_spacing)
    if dashboard_status is not None:
        dashboard_status.setVisible(not workstation)

    set_property = getattr(self, "setProperty", None)
    if callable(set_property):
        set_property("workstationLayout", workstation)
    for widget in (self, header, rail, tabs, dashboard_status):
        if widget is None:
            continue
        style_getter = getattr(widget, "style", None)
        if callable(style_getter):
            style = style_getter()
            style.unpolish(widget)
            style.polish(widget)
        update = getattr(widget, "update", None)
        if callable(update):
            update()
