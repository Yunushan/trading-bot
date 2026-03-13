from __future__ import annotations

from PyQt6 import QtCore, QtWidgets

_coerce_bool = lambda value, default=False: default  # type: ignore
_POS_CLOSE_COLUMN = 0
_PositionsWorkerCls = None


def _create_positions_tab(self):
    tab2 = QtWidgets.QWidget()
    tab2_layout = QtWidgets.QVBoxLayout(tab2)

    ctrl_layout = QtWidgets.QHBoxLayout()
    self.refresh_pos_btn = QtWidgets.QPushButton("Refresh Positions")
    self.refresh_pos_btn.clicked.connect(self.refresh_positions)
    ctrl_layout.addWidget(self.refresh_pos_btn)
    self.close_all_btn = QtWidgets.QPushButton("Market Close ALL Positions")
    self.close_all_btn.clicked.connect(self.close_all_positions_async)
    ctrl_layout.addWidget(self.close_all_btn)
    ctrl_layout.addWidget(QtWidgets.QLabel("Positions View:"))
    self.positions_view_combo = QtWidgets.QComboBox()
    self.positions_view_combo.addItems(["Cumulative View", "Per Trade View"])
    self.positions_view_combo.setCurrentIndex(0)
    self.positions_view_combo.currentIndexChanged.connect(self._on_positions_view_changed)
    ctrl_layout.addWidget(self.positions_view_combo)
    self.positions_auto_resize_checkbox = QtWidgets.QCheckBox("Auto Row Height")
    self.positions_auto_resize_checkbox.setToolTip("Resize rows to fit multi-line indicator values.")
    self.positions_auto_resize_checkbox.setChecked(
        _coerce_bool(self.config.get("positions_auto_resize_rows", True), True)
    )
    self.positions_auto_resize_checkbox.stateChanged.connect(self._on_positions_auto_resize_changed)
    ctrl_layout.addWidget(self.positions_auto_resize_checkbox)
    self.positions_auto_resize_columns_checkbox = QtWidgets.QCheckBox("Auto Column Width")
    self.positions_auto_resize_columns_checkbox.setToolTip("Resize columns to fit full indicator text.")
    self.positions_auto_resize_columns_checkbox.setChecked(
        _coerce_bool(self.config.get("positions_auto_resize_columns", True), True)
    )
    self.positions_auto_resize_columns_checkbox.stateChanged.connect(
        self._on_positions_auto_resize_columns_changed
    )
    ctrl_layout.addWidget(self.positions_auto_resize_columns_checkbox)
    ctrl_layout.addStretch()
    tab2_layout.addLayout(ctrl_layout)

    tab2_status_widget = QtWidgets.QWidget()
    tab2_status_widget.setSizePolicy(
        QtWidgets.QSizePolicy.Policy.Expanding,
        QtWidgets.QSizePolicy.Policy.Fixed,
    )
    tab2_status_layout = QtWidgets.QHBoxLayout(tab2_status_widget)
    tab2_status_layout.setContentsMargins(0, 0, 0, 0)
    tab2_status_layout.setSpacing(12)
    self.pnl_active_label_tab2 = QtWidgets.QLabel()
    self.pnl_closed_label_tab2 = QtWidgets.QLabel()
    self.positions_total_balance_label = QtWidgets.QLabel("Total Balance: --")
    self.positions_available_balance_label = QtWidgets.QLabel("Available Balance: --")
    self.bot_status_label_tab2 = QtWidgets.QLabel()
    self.bot_time_label_tab2 = QtWidgets.QLabel("Bot Active Time: --")
    for lbl in (
        self.pnl_active_label_tab2,
        self.pnl_closed_label_tab2,
        self.positions_total_balance_label,
        self.positions_available_balance_label,
    ):
        lbl.setAlignment(QtCore.Qt.AlignmentFlag.AlignLeft | QtCore.Qt.AlignmentFlag.AlignVCenter)
        lbl.setSizePolicy(
            QtWidgets.QSizePolicy.Policy.Expanding,
            QtWidgets.QSizePolicy.Policy.Preferred,
        )
        tab2_status_layout.addWidget(lbl)
    tab2_status_layout.addStretch()
    for lbl in (self.bot_status_label_tab2, self.bot_time_label_tab2):
        lbl.setAlignment(QtCore.Qt.AlignmentFlag.AlignRight | QtCore.Qt.AlignmentFlag.AlignVCenter)
        lbl.setSizePolicy(
            QtWidgets.QSizePolicy.Policy.Minimum,
            QtWidgets.QSizePolicy.Policy.Preferred,
        )
        tab2_status_layout.addWidget(lbl)
    self._register_pnl_summary_labels(self.pnl_active_label_tab2, self.pnl_closed_label_tab2)
    self._update_positions_balance_labels(None, None)
    tab2_layout.addWidget(tab2_status_widget)
    self._sync_runtime_state()

    self.pos_table = QtWidgets.QTableWidget(0, _POS_CLOSE_COLUMN + 1, tab2)
    self.pos_table.setHorizontalHeaderLabels(
        [
            "Symbol",
            "Size (USDT)",
            "Last Price (USDT)",
            "Margin Ratio",
            "Liq Price (USDT)",
            "Margin (USDT)",
            "Quantity (Qty)",
            "PNL (ROI%)",
            "Interval",
            "Indicator",
            "Triggered Indicator Value",
            "Current Indicator Value",
            "Side",
            "Open Time",
            "Close Time",
            "Stop-Loss",
            "Status",
            "Close",
        ]
    )
    pos_header = self.pos_table.horizontalHeader()
    pos_header.setStretchLastSection(True)
    try:
        pos_header.setSectionsMovable(True)
    except Exception:
        pass
    self.pos_table.setSelectionBehavior(QtWidgets.QAbstractItemView.SelectionBehavior.SelectRows)
    try:
        self.pos_table.setEditTriggers(QtWidgets.QAbstractItemView.EditTrigger.NoEditTriggers)
    except Exception:
        self.pos_table.setEditTriggers(QtWidgets.QAbstractItemView.NoEditTriggers)
    self.pos_table.setSortingEnabled(True)
    self.pos_table.setWordWrap(True)
    try:
        self.pos_table.setTextElideMode(QtCore.Qt.TextElideMode.ElideNone)
    except Exception:
        pass
    try:
        self.pos_table.verticalHeader().setDefaultSectionSize(44)
    except Exception:
        pass
    tab2_layout.addWidget(self.pos_table)

    pos_btn_layout = QtWidgets.QHBoxLayout()
    self.pos_clear_selected_btn = QtWidgets.QPushButton("Clear Selected")
    self.pos_clear_selected_btn.clicked.connect(self._clear_positions_selected)
    pos_btn_layout.addWidget(self.pos_clear_selected_btn)
    self.pos_clear_all_btn = QtWidgets.QPushButton("Clear All")
    self.pos_clear_all_btn.clicked.connect(self._clear_positions_all)
    pos_btn_layout.addWidget(self.pos_clear_all_btn)
    pos_btn_layout.addStretch()
    tab2_layout.addLayout(pos_btn_layout)

    self.tabs.addTab(tab2, "Positions")

    self._pos_thread = QtCore.QThread(self)
    self._pos_worker = _PositionsWorkerCls(
        self.api_key_edit.text().strip(),
        self.api_secret_edit.text().strip(),
        self.mode_combo.currentText(),
        self.account_combo.currentText(),
        connector_backend=self._runtime_connector_backend(suppress_refresh=True),
    )
    self.req_pos_start.connect(self._pos_worker.start_with_interval)
    self.req_pos_stop.connect(self._pos_worker.stop_timer)
    self.req_pos_set_interval.connect(self._pos_worker.set_interval)
    self._pos_worker.moveToThread(self._pos_thread)
    self._pos_worker.positions_ready.connect(self._on_positions_ready)
    self._pos_worker.error.connect(lambda e: self.log(f"Positions worker: {e}"))
    try:
        self._reconfigure_positions_worker()
    except Exception:
        pass

    self._pos_thread.start()
    try:
        self._apply_positions_refresh_settings()
    except Exception:
        pass


def bind_main_window_positions_tab(
    MainWindow,
    *,
    coerce_bool,
    pos_close_column,
    positions_worker_cls,
):
    global _coerce_bool
    global _POS_CLOSE_COLUMN
    global _PositionsWorkerCls

    _coerce_bool = coerce_bool
    _POS_CLOSE_COLUMN = int(pos_close_column)
    _PositionsWorkerCls = positions_worker_cls

    MainWindow._create_positions_tab = _create_positions_tab
