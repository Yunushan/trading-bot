from __future__ import annotations

from PyQt6 import QtWidgets

from .backtest_state_context_runtime import normalize_backtest_interval_value


def build_backtest_market_group(self):
    market_group = QtWidgets.QGroupBox("Markets")
    market_group.setMinimumWidth(220)
    market_group.setMaximumWidth(620)
    market_group.setSizePolicy(
        QtWidgets.QSizePolicy.Policy.Preferred,
        QtWidgets.QSizePolicy.Policy.Expanding,
    )
    market_layout = QtWidgets.QGridLayout(market_group)

    market_layout.addWidget(QtWidgets.QLabel("Symbol Source:"), 0, 0)
    self.backtest_symbol_source_combo = QtWidgets.QComboBox()
    self.backtest_symbol_source_combo.addItems(["Futures", "Spot"])
    self.backtest_symbol_source_combo.currentTextChanged.connect(self._backtest_symbol_source_changed)
    market_layout.addWidget(self.backtest_symbol_source_combo, 0, 1)
    self.backtest_refresh_symbols_btn = QtWidgets.QPushButton("Refresh")
    self.backtest_refresh_symbols_btn.clicked.connect(self._refresh_backtest_symbols)
    market_layout.addWidget(self.backtest_refresh_symbols_btn, 0, 2)

    market_layout.addWidget(QtWidgets.QLabel("Symbols (select 1 or more):"), 1, 0, 1, 3)
    self.backtest_symbol_list = QtWidgets.QListWidget()
    self.backtest_symbol_list.setSelectionMode(QtWidgets.QAbstractItemView.SelectionMode.MultiSelection)
    size_policy_symbols = QtWidgets.QSizePolicy(
        QtWidgets.QSizePolicy.Policy.Preferred,
        QtWidgets.QSizePolicy.Policy.Expanding,
    )
    size_policy_symbols.setHorizontalStretch(0)
    size_policy_symbols.setVerticalStretch(1)
    self.backtest_symbol_list.setSizePolicy(size_policy_symbols)
    self.backtest_symbol_list.setMinimumWidth(140)
    self.backtest_symbol_list.setMaximumWidth(260)
    self.backtest_symbol_list.itemSelectionChanged.connect(self._backtest_store_symbols)
    market_layout.addWidget(self.backtest_symbol_list, 2, 0, 4, 3)

    market_layout.addWidget(QtWidgets.QLabel("Intervals (select 1 or more):"), 1, 3)
    self.backtest_interval_list = QtWidgets.QListWidget()
    self.backtest_interval_list.setSelectionMode(QtWidgets.QAbstractItemView.SelectionMode.MultiSelection)
    size_policy_intervals = QtWidgets.QSizePolicy(
        QtWidgets.QSizePolicy.Policy.Preferred,
        QtWidgets.QSizePolicy.Policy.Expanding,
    )
    size_policy_intervals.setHorizontalStretch(0)
    size_policy_intervals.setVerticalStretch(1)
    self.backtest_interval_list.setSizePolicy(size_policy_intervals)
    self.backtest_interval_list.setMinimumWidth(120)
    self.backtest_interval_list.setMaximumWidth(240)
    self.backtest_interval_list.itemSelectionChanged.connect(self._backtest_store_intervals)
    market_layout.addWidget(self.backtest_interval_list, 2, 3, 4, 2)

    self.backtest_custom_interval_edit = QtWidgets.QLineEdit()
    self.backtest_custom_interval_edit.setPlaceholderText("e.g., 45s or 7m or 90m, comma-separated")
    self.backtest_custom_interval_edit.setMaximumWidth(240)
    market_layout.addWidget(self.backtest_custom_interval_edit, 6, 3)
    self.backtest_add_interval_btn = QtWidgets.QPushButton("Add Custom Interval(s)")
    market_layout.addWidget(self.backtest_add_interval_btn, 6, 4)

    def _add_backtest_custom_intervals():
        text = self.backtest_custom_interval_edit.text().strip()
        if not text:
            return
        parts = [p.strip() for p in text.split(",") if p.strip()]
        if not parts:
            self.backtest_custom_interval_edit.clear()
            return
        existing = {
            normalize_backtest_interval_value(self.backtest_interval_list.item(i).text())
            for i in range(self.backtest_interval_list.count())
            if self.backtest_interval_list.item(i) is not None
        }
        new_items = []
        for part in parts:
            norm = normalize_backtest_interval_value(part)
            if not norm or norm in existing:
                continue
            item = QtWidgets.QListWidgetItem(norm)
            self.backtest_interval_list.addItem(item)
            item.setSelected(True)
            existing.add(norm)
            new_items.append(item)
        self.backtest_custom_interval_edit.clear()
        if new_items:
            self._backtest_store_intervals()

    self.backtest_add_interval_btn.clicked.connect(_add_backtest_custom_intervals)

    pair_group = self._create_override_group("backtest", self.backtest_symbol_list, self.backtest_interval_list)
    market_layout.addWidget(pair_group, 7, 0, 1, 5)

    market_layout.setColumnStretch(0, 2)
    market_layout.setColumnStretch(1, 1)
    market_layout.setColumnStretch(2, 1)
    market_layout.setColumnStretch(3, 1)
    market_layout.setColumnStretch(4, 1)
    return market_group


__all__ = ["build_backtest_market_group"]
