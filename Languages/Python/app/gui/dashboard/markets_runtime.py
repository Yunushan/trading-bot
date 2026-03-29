from __future__ import annotations

from PyQt6 import QtCore, QtGui, QtWidgets

_STARTER_CRYPTO_EXCHANGES = ()
_EXCHANGE_PATHS = {}
_CHART_INTERVAL_OPTIONS = ()
_BINANCE_SUPPORTED_INTERVALS = set()


def _create_dashboard_markets_section(self, scroll_layout):
    exchange_group = QtWidgets.QGroupBox("Exchange")
    exchange_layout = QtWidgets.QVBoxLayout(exchange_group)
    exchange_layout.setContentsMargins(12, 10, 12, 10)
    exchange_layout.setSpacing(6)
    exchange_label = QtWidgets.QLabel("Select exchange")
    exchange_layout.addWidget(exchange_label)
    self.exchange_combo = QtWidgets.QComboBox()
    exchange_layout.addWidget(self.exchange_combo)
    exchange_options = [
        opt for opt in _STARTER_CRYPTO_EXCHANGES if opt["key"] in _EXCHANGE_PATHS
    ]
    enabled_exchanges = []
    for opt in exchange_options:
        item_text = opt["title"]
        badge = opt.get("badge")
        if badge:
            item_text = f"{item_text} ({badge})"
        self.exchange_combo.addItem(item_text, opt["key"])
        idx = self.exchange_combo.count() - 1
        if opt.get("disabled", False):
            item = self.exchange_combo.model().item(idx)
            if item is not None:
                item.setFlags(item.flags() & ~QtCore.Qt.ItemFlag.ItemIsEnabled)
                item.setForeground(QtGui.QColor("#6b7280"))
        else:
            enabled_exchanges.append(opt["key"])
    selected_exchange = self.config.get("selected_exchange")
    if selected_exchange not in enabled_exchanges:
        selected_exchange = enabled_exchanges[0] if enabled_exchanges else None
        if selected_exchange:
            self.config["selected_exchange"] = selected_exchange
    if selected_exchange:
        idx = self.exchange_combo.findData(selected_exchange)
        if idx >= 0:
            with QtCore.QSignalBlocker(self.exchange_combo):
                self.exchange_combo.setCurrentIndex(idx)
    self.exchange_combo.currentIndexChanged.connect(
        lambda _=None: self._on_exchange_selection_changed(self.exchange_combo.currentData())
    )
    scroll_layout.addWidget(exchange_group)

    sym_group = QtWidgets.QGroupBox("Markets & Intervals")
    sgrid = QtWidgets.QGridLayout(sym_group)

    sgrid.addWidget(QtWidgets.QLabel("Symbols (select 1 or more):"), 0, 0)
    self.symbol_list = QtWidgets.QListWidget()
    self.symbol_list.setSelectionMode(QtWidgets.QAbstractItemView.SelectionMode.MultiSelection)
    self.symbol_list.setMinimumHeight(260)
    self.symbol_list.itemSelectionChanged.connect(self._reconfigure_positions_worker)
    self.symbol_list.itemSelectionChanged.connect(self._on_dashboard_selection_for_chart)
    sgrid.addWidget(self.symbol_list, 1, 0, 4, 2)

    self.refresh_symbols_btn = QtWidgets.QPushButton("Refresh Symbols")
    self.refresh_symbols_btn.clicked.connect(self.refresh_symbols)
    sgrid.addWidget(self.refresh_symbols_btn, 5, 0, 1, 2)

    sgrid.addWidget(QtWidgets.QLabel("Intervals (select 1 or more):"), 0, 2)
    self.interval_list = QtWidgets.QListWidget()
    self.interval_list.setSelectionMode(QtWidgets.QAbstractItemView.SelectionMode.MultiSelection)
    self.interval_list.setMinimumHeight(260)
    for interval in _CHART_INTERVAL_OPTIONS:
        self.interval_list.addItem(QtWidgets.QListWidgetItem(interval))
    self.interval_list.itemSelectionChanged.connect(self._on_dashboard_selection_for_chart)
    sgrid.addWidget(self.interval_list, 1, 2, 3, 2)

    self.custom_interval_edit = QtWidgets.QLineEdit()
    self.custom_interval_edit.setPlaceholderText("e.g., 45s or 7m or 90m, comma-separated")
    self.add_interval_btn = QtWidgets.QPushButton("Add Custom Interval(s)")

    def _add_custom_intervals():
        txt = self.custom_interval_edit.text().strip()
        if not txt:
            return
        parts = [p.strip() for p in txt.split(",") if p.strip()]
        existing = {
            self.interval_list.item(i).text()
            for i in range(self.interval_list.count())
        }
        source = (
            (self.ind_source_combo.currentText() or "").strip().lower()
            if hasattr(self, "ind_source_combo")
            else ""
        )
        is_binance_source = "binance" in source
        for part in parts:
            norm = part.strip()
            key = norm.lower()
            if is_binance_source and key not in _BINANCE_SUPPORTED_INTERVALS:
                self.log(f"Skipping unsupported Binance interval '{norm}'.")
                continue
            if norm not in existing:
                self.interval_list.addItem(QtWidgets.QListWidgetItem(norm))
                existing.add(norm)
        self.custom_interval_edit.clear()

    self.add_interval_btn.clicked.connect(_add_custom_intervals)
    sgrid.addWidget(self.custom_interval_edit, 4, 2)
    sgrid.addWidget(self.add_interval_btn, 4, 3)
    scroll_layout.addWidget(sym_group)

    return self._create_override_group("runtime", self.symbol_list, self.interval_list)


def bind_main_window_dashboard_markets_runtime(
    MainWindow,
    *,
    starter_crypto_exchanges,
    exchange_paths,
    chart_interval_options,
    binance_supported_intervals,
):
    global _STARTER_CRYPTO_EXCHANGES
    global _EXCHANGE_PATHS
    global _CHART_INTERVAL_OPTIONS
    global _BINANCE_SUPPORTED_INTERVALS

    _STARTER_CRYPTO_EXCHANGES = tuple(starter_crypto_exchanges)
    _EXCHANGE_PATHS = dict(exchange_paths)
    _CHART_INTERVAL_OPTIONS = tuple(chart_interval_options)
    _BINANCE_SUPPORTED_INTERVALS = set(binance_supported_intervals)

    MainWindow._create_dashboard_markets_section = _create_dashboard_markets_section
