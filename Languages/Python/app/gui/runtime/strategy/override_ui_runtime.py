from __future__ import annotations

from PyQt6 import QtCore, QtWidgets


def _create_override_group(self, kind: str, symbol_list, interval_list) -> QtWidgets.QGroupBox:
    group = QtWidgets.QGroupBox("Symbol / Interval Overrides")
    layout = QtWidgets.QVBoxLayout(group)
    columns = ["Symbol", "Interval"]
    show_indicators = kind in ("runtime", "backtest")
    if show_indicators:
        columns.append("Indicators")
    include_loop = kind in ("runtime", "backtest")
    include_leverage = kind in ("runtime", "backtest")
    if include_loop:
        columns.append("Loop")
    if include_leverage:
        columns.append("Leverage")
    columns.append("Connector")
    columns.append("Strategy Controls")
    columns.append("Stop-Loss")
    table = QtWidgets.QTableWidget(0, len(columns))
    table.setHorizontalHeaderLabels(columns)
    column_map = {name: idx for idx, name in enumerate(columns)}
    header = table.horizontalHeader()
    header.setStretchLastSection(False)
    try:
        header.setSectionResizeMode(QtWidgets.QHeaderView.ResizeMode.ResizeToContents)
    except Exception:
        pass
    try:
        header.setSectionsMovable(True)
    except Exception:
        pass
    table.setHorizontalScrollBarPolicy(QtCore.Qt.ScrollBarPolicy.ScrollBarAsNeeded)
    table.setSizeAdjustPolicy(QtWidgets.QAbstractScrollArea.SizeAdjustPolicy.AdjustIgnored)
    table.setHorizontalScrollMode(QtWidgets.QAbstractItemView.ScrollMode.ScrollPerPixel)
    table.setMinimumHeight(180)
    try:
        table.verticalHeader().setDefaultSectionSize(28)
    except Exception:
        pass
    try:
        table.setEditTriggers(QtWidgets.QAbstractItemView.EditTrigger.NoEditTriggers)
    except Exception:
        table.setEditTriggers(QtWidgets.QAbstractItemView.NoEditTriggers)
    table.setSelectionBehavior(QtWidgets.QTableWidget.SelectionBehavior.SelectRows)
    table.setSelectionMode(QtWidgets.QAbstractItemView.SelectionMode.MultiSelection)
    table.setSortingEnabled(True)
    layout.addWidget(table)

    btn_layout = QtWidgets.QHBoxLayout()
    add_btn = QtWidgets.QPushButton("Add Selected")
    add_btn.clicked.connect(lambda _, k=kind: self._add_selected_symbol_interval_pairs(k))
    btn_layout.addWidget(add_btn)
    remove_btn = QtWidgets.QPushButton("Remove Selected")
    remove_btn.clicked.connect(lambda _, k=kind: self._remove_selected_symbol_interval_pairs(k))
    btn_layout.addWidget(remove_btn)
    clear_btn = QtWidgets.QPushButton("Clear All")
    clear_btn.clicked.connect(lambda _, k=kind: self._clear_symbol_interval_pairs(k))
    btn_layout.addWidget(clear_btn)
    btn_layout.addStretch()
    layout.addLayout(btn_layout)
    config_key = "runtime_symbol_interval_pairs" if kind == "runtime" else "backtest_symbol_interval_pairs"
    self.override_contexts[kind] = {
        "table": table,
        "symbol_list": symbol_list,
        "interval_list": interval_list,
        "config_key": config_key,
        "add_btn": add_btn,
        "remove_btn": remove_btn,
        "clear_btn": clear_btn,
        "column_map": column_map,
    }
    if kind == "runtime":
        self.pair_add_btn = add_btn
        self.pair_remove_btn = remove_btn
        self.pair_clear_btn = clear_btn
    lock_widgets = getattr(self, "_runtime_lock_widgets", None)
    if isinstance(lock_widgets, list):
        for widget in (table, add_btn, remove_btn, clear_btn):
            if widget and widget not in lock_widgets:
                lock_widgets.append(widget)
    self._refresh_symbol_interval_pairs(kind)
    return group
