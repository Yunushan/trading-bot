from __future__ import annotations

from PyQt6 import QtCore, QtWidgets


def build_backtest_output_group(self):
    output_group = QtWidgets.QGroupBox("Backtest Output")
    output_group_layout = QtWidgets.QVBoxLayout(output_group)
    output_group_layout.setContentsMargins(12, 12, 12, 12)
    output_group_layout.setSpacing(12)

    controls_layout = QtWidgets.QHBoxLayout()
    self.backtest_run_btn = QtWidgets.QPushButton("Run Backtest")
    self.backtest_run_btn.clicked.connect(self._run_backtest)
    controls_layout.addWidget(self.backtest_run_btn)
    self.backtest_stop_btn = QtWidgets.QPushButton("Stop")
    self.backtest_stop_btn.setEnabled(False)
    self.backtest_stop_btn.clicked.connect(self._stop_backtest)
    controls_layout.addWidget(self.backtest_stop_btn)
    self.backtest_status_label = QtWidgets.QLabel()
    controls_layout.addWidget(self.backtest_status_label)
    self.backtest_add_to_dashboard_btn = QtWidgets.QPushButton("Add Selected to Dashboard")
    self.backtest_add_to_dashboard_btn.clicked.connect(self._backtest_add_selected_to_dashboard)
    controls_layout.addWidget(self.backtest_add_to_dashboard_btn)
    self.backtest_add_all_to_dashboard_btn = QtWidgets.QPushButton("Add All to Dashboard")
    self.backtest_add_all_to_dashboard_btn.clicked.connect(self._backtest_add_all_to_dashboard)
    controls_layout.addWidget(self.backtest_add_all_to_dashboard_btn)
    controls_layout.addStretch()

    tab3_status_widget = QtWidgets.QWidget()
    tab3_status_layout = QtWidgets.QHBoxLayout(tab3_status_widget)
    tab3_status_layout.setContentsMargins(0, 0, 0, 0)
    tab3_status_layout.setSpacing(8)
    self.pnl_active_label_tab3 = QtWidgets.QLabel()
    self.pnl_closed_label_tab3 = QtWidgets.QLabel()
    self.bot_status_label_tab3 = QtWidgets.QLabel()
    self.bot_time_label_tab3 = QtWidgets.QLabel("Bot Active Time: --")
    for lbl in (self.pnl_active_label_tab3, self.pnl_closed_label_tab3):
        lbl.setAlignment(QtCore.Qt.AlignmentFlag.AlignLeft | QtCore.Qt.AlignmentFlag.AlignVCenter)
        tab3_status_layout.addWidget(lbl)
    tab3_status_layout.addStretch()
    for lbl in (self.bot_status_label_tab3, self.bot_time_label_tab3):
        lbl.setAlignment(QtCore.Qt.AlignmentFlag.AlignRight | QtCore.Qt.AlignmentFlag.AlignVCenter)
        tab3_status_layout.addWidget(lbl)
    self._register_pnl_summary_labels(self.pnl_active_label_tab3, self.pnl_closed_label_tab3)
    controls_layout.addWidget(tab3_status_widget)
    output_group_layout.addLayout(controls_layout)
    self._update_bot_status()
    try:
        for widget in (
            self.backtest_run_btn,
            self.backtest_stop_btn,
            self.backtest_scan_btn,
            self.backtest_add_to_dashboard_btn,
            self.backtest_add_all_to_dashboard_btn,
        ):
            if widget and widget not in self._runtime_lock_widgets:
                self._runtime_lock_widgets.append(widget)
            if widget in (
                self.backtest_run_btn,
                self.backtest_stop_btn,
                self.backtest_scan_btn,
            ):
                self._register_runtime_active_exemption(widget)
    except Exception:
        pass

    self.backtest_results_table = QtWidgets.QTableWidget(0, 21)
    self.backtest_results_table.setHorizontalHeaderLabels(
        [
            "Symbol",
            "Interval",
            "Logic",
            "Indicators",
            "Trades",
            "Loop Interval",
            "Start Date",
            "End Date",
            "Position % Of Balance",
            "Stop-Loss Options",
            "Margin Mode (Futures)",
            "Position Mode",
            "Assets Mode",
            "Account Mode",
            "Leverage (Futures)",
            "ROI (USDT)",
            "ROI (%)",
            "Max Drawdown During Position (USDT)",
            "Max Drawdown During Position (%)",
            "Max Drawdown Results (USDT)",
            "Max Drawdown Results (%)",
        ]
    )
    header = self.backtest_results_table.horizontalHeader()
    header.setStretchLastSection(False)
    try:
        header.setSectionsMovable(True)
    except Exception:
        pass
    try:
        header.setSectionResizeMode(QtWidgets.QHeaderView.ResizeMode.Interactive)
    except Exception:
        try:
            header.setSectionResizeMode(QtWidgets.QHeaderView.Interactive)
        except Exception:
            pass
    try:
        font_metrics = header.fontMetrics()
        style = header.style()
        opt = QtWidgets.QStyleOptionHeader()
        opt.initFrom(header)
        base_padding = style.pixelMetric(QtWidgets.QStyle.PixelMetric.PM_HeaderMargin, opt, header)
        arrow_padding = style.pixelMetric(QtWidgets.QStyle.PixelMetric.PM_HeaderMarkSize, opt, header)
    except Exception:
        font_metrics = None
        base_padding = 12
        arrow_padding = 12
    if font_metrics is None:
        font_metrics = self.fontMetrics()
    total_padding = (base_padding or 12) * 2 + (arrow_padding or 12)
    for col in range(self.backtest_results_table.columnCount()):
        try:
            header_item = self.backtest_results_table.horizontalHeaderItem(col)
            text = header_item.text() if header_item is not None else ""
            text_width = font_metrics.horizontalAdvance(text) if font_metrics is not None else 0
            target_width = max(text_width + total_padding, 80)
            header.resizeSection(col, target_width)
        except Exception:
            continue
    self.backtest_results_table.setSortingEnabled(True)
    try:
        self.backtest_results_table.setEditTriggers(
            QtWidgets.QAbstractItemView.EditTrigger.NoEditTriggers
        )
    except Exception:
        self.backtest_results_table.setEditTriggers(QtWidgets.QAbstractItemView.NoEditTriggers)
    self.backtest_results_table.setHorizontalScrollBarPolicy(
        QtCore.Qt.ScrollBarPolicy.ScrollBarAsNeeded
    )
    self.backtest_results_table.setVerticalScrollBarPolicy(
        QtCore.Qt.ScrollBarPolicy.ScrollBarAsNeeded
    )
    self.backtest_results_table.setSizeAdjustPolicy(
        QtWidgets.QAbstractScrollArea.SizeAdjustPolicy.AdjustIgnored
    )
    self.backtest_results_table.setHorizontalScrollMode(
        QtWidgets.QAbstractItemView.ScrollMode.ScrollPerPixel
    )
    self.backtest_results_table.setVerticalScrollMode(
        QtWidgets.QAbstractItemView.ScrollMode.ScrollPerPixel
    )
    self.backtest_results_table.setSelectionBehavior(
        QtWidgets.QAbstractItemView.SelectionBehavior.SelectRows
    )
    self.backtest_results_table.setSelectionMode(
        QtWidgets.QAbstractItemView.SelectionMode.MultiSelection
    )
    self.backtest_results_table.setMinimumHeight(420)
    output_group_layout.addWidget(self.backtest_results_table, 1)
    return output_group


__all__ = ["build_backtest_output_group"]
