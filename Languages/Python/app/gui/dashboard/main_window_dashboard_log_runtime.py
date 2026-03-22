from __future__ import annotations

from PyQt6 import QtCore, QtWidgets


def _create_dashboard_log_section(self, scroll_layout):
    self.log_tab_widget = QtWidgets.QTabWidget()
    try:
        self.log_tab_widget.setDocumentMode(True)
    except Exception:
        pass

    self.log_all_edit = QtWidgets.QPlainTextEdit()
    self.log_all_edit.setReadOnly(True)
    self.log_all_edit.setMinimumHeight(220)
    try:
        self.log_all_edit.setSizePolicy(
            QtWidgets.QSizePolicy.Policy.Expanding,
            QtWidgets.QSizePolicy.Policy.Preferred,
        )
    except Exception:
        pass
    try:
        self.log_all_edit.document().setMaximumBlockCount(1000)
    except Exception:
        pass
    self.log_tab_widget.addTab(self.log_all_edit, "All Logs")

    self.log_triggers_edit = QtWidgets.QPlainTextEdit()
    self.log_triggers_edit.setReadOnly(True)
    self.log_triggers_edit.setMinimumHeight(220)
    try:
        self.log_triggers_edit.setSizePolicy(
            QtWidgets.QSizePolicy.Policy.Expanding,
            QtWidgets.QSizePolicy.Policy.Preferred,
        )
    except Exception:
        pass
    try:
        self.log_triggers_edit.document().setMaximumBlockCount(1000)
    except Exception:
        pass
    self.log_tab_widget.addTab(self.log_triggers_edit, "Position Trigger Logs")

    self.waiting_pos_table = QtWidgets.QTableWidget(0, 6)
    self.waiting_pos_table.setHorizontalHeaderLabels(
        [
            "Symbol",
            "Interval",
            "Side",
            "Context",
            "State",
            "Age (s)",
        ]
    )
    self.waiting_pos_table.setEditTriggers(
        QtWidgets.QAbstractItemView.EditTrigger.NoEditTriggers
    )
    self.waiting_pos_table.setSelectionMode(
        QtWidgets.QAbstractItemView.SelectionMode.NoSelection
    )
    self.waiting_pos_table.setFocusPolicy(QtCore.Qt.FocusPolicy.NoFocus)
    try:
        self.waiting_pos_table.setPlaceholderText("No waiting positions")
    except Exception:
        pass
    header_waiting = self.waiting_pos_table.horizontalHeader()
    try:
        header_waiting.setStretchLastSection(True)
        header_waiting.setSectionResizeMode(QtWidgets.QHeaderView.ResizeMode.Stretch)
    except Exception:
        pass
    try:
        self.waiting_pos_table.verticalHeader().setVisible(False)
    except Exception:
        pass
    self.log_tab_widget.addTab(self.waiting_pos_table, "Waiting Positions (Queue)")

    self._waiting_positions_history = []
    self._waiting_positions_last_snapshot = {}
    try:
        self._waiting_positions_history_max = int(
            self.config.get("waiting_positions_history_max", 500) or 500
        )
    except Exception:
        self._waiting_positions_history_max = 500
    try:
        self.log_tab_widget.setCurrentIndex(0)
    except Exception:
        pass
    self.log_edit = self.log_all_edit
    scroll_layout.addWidget(self.log_tab_widget)

    self.waiting_positions_timer = QtCore.QTimer(self)
    self.waiting_positions_timer.setInterval(1000)
    self.waiting_positions_timer.timeout.connect(self._refresh_waiting_positions_tab)
    self.waiting_positions_timer.start()
    self._refresh_waiting_positions_tab()


def bind_main_window_dashboard_log_runtime(MainWindow):
    MainWindow._create_dashboard_log_section = _create_dashboard_log_section
