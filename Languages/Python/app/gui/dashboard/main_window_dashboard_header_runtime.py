from __future__ import annotations

from PyQt6 import QtCore, QtWidgets

_ACCOUNT_MODE_OPTIONS = ()
_CONNECTOR_OPTIONS = ()
_FUTURES_CONNECTOR_KEYS = ()
_SPOT_CONNECTOR_KEYS = ()


def _create_dashboard_header_section(self, scroll_layout):
    grid = QtWidgets.QGridLayout()

    grid.addWidget(QtWidgets.QLabel("API Key:"), 0, 0)
    self.api_key_edit = QtWidgets.QLineEdit(self.config["api_key"])
    grid.addWidget(self.api_key_edit, 0, 1)

    grid.addWidget(QtWidgets.QLabel("API Secret Key:"), 1, 0)
    self.api_secret_edit = QtWidgets.QLineEdit(self.config["api_secret"])
    self.api_secret_edit.setEchoMode(QtWidgets.QLineEdit.EchoMode.Password)
    grid.addWidget(self.api_secret_edit, 1, 1)
    self.api_key_edit.editingFinished.connect(self._on_api_credentials_changed)
    self.api_secret_edit.editingFinished.connect(self._on_api_credentials_changed)

    grid.addWidget(QtWidgets.QLabel("Mode:"), 0, 2)
    self.mode_combo = QtWidgets.QComboBox()
    mode_options = [
        "Live",
        "Demo",
        "Testnet",
    ]
    self.mode_combo.addItems(mode_options)
    loaded_mode = self.config.get("mode", "Live") or "Live"
    if loaded_mode == "Demo/Testnet":
        loaded_mode = "Demo"
    if loaded_mode == "Futures WebSocket (live market data)":
        loaded_mode = "Live"
    if loaded_mode == "Testnet WebSocket":
        loaded_mode = "Testnet"
    if loaded_mode not in mode_options:
        loaded_mode = "Live"
    self.mode_combo.setCurrentText(loaded_mode)
    grid.addWidget(self.mode_combo, 0, 3)
    self.mode_combo.currentTextChanged.connect(self._on_mode_changed)

    grid.addWidget(QtWidgets.QLabel("Theme:"), 0, 4)
    self.theme_combo = QtWidgets.QComboBox()
    self.theme_combo.addItems(["Light", "Dark", "Blue", "Yellow", "Green", "Red"])
    current_theme = (self.config.get("theme") or "Dark").title()
    if current_theme not in {"Light", "Dark", "Blue", "Yellow", "Green", "Red"}:
        current_theme = "Dark"
    self.theme_combo.setCurrentText(current_theme)
    self.theme_combo.currentTextChanged.connect(self.apply_theme)
    grid.addWidget(self.theme_combo, 0, 5)

    status_widget = QtWidgets.QWidget()
    status_layout = QtWidgets.QHBoxLayout(status_widget)
    status_layout.setContentsMargins(0, 0, 0, 0)
    status_layout.setSpacing(10)
    self.pnl_active_label_tab1 = QtWidgets.QLabel()
    self.pnl_closed_label_tab1 = QtWidgets.QLabel()
    self.bot_status_label_tab1 = QtWidgets.QLabel()
    self.bot_time_label_tab1 = QtWidgets.QLabel("Bot Active Time: --")
    for lbl in (self.pnl_active_label_tab1, self.pnl_closed_label_tab1):
        lbl.setAlignment(QtCore.Qt.AlignmentFlag.AlignLeft | QtCore.Qt.AlignmentFlag.AlignVCenter)
        status_layout.addWidget(lbl)
    status_layout.addStretch()
    for lbl in (self.bot_status_label_tab1, self.bot_time_label_tab1):
        lbl.setAlignment(QtCore.Qt.AlignmentFlag.AlignRight | QtCore.Qt.AlignmentFlag.AlignVCenter)
        status_layout.addWidget(lbl)
    self._register_pnl_summary_labels(self.pnl_active_label_tab1, self.pnl_closed_label_tab1)
    grid.addWidget(status_widget, 0, 6, 1, 4)

    grid.addWidget(QtWidgets.QLabel("Account Type:"), 1, 2)
    self.account_combo = QtWidgets.QComboBox()
    self.account_combo.addItems(["Spot", "Futures"])
    self.account_combo.setCurrentText(self.config.get("account_type", "Futures"))
    grid.addWidget(self.account_combo, 1, 3)
    self.account_combo.currentTextChanged.connect(self._on_account_type_changed)

    grid.addWidget(QtWidgets.QLabel("Account Mode:"), 1, 4)
    self.account_mode_combo = QtWidgets.QComboBox()
    for mode in _ACCOUNT_MODE_OPTIONS:
        self.account_mode_combo.addItem(mode, mode)
    account_mode_cfg = self._normalize_account_mode(
        self.config.get("account_mode", _ACCOUNT_MODE_OPTIONS[0])
    )
    idx_account_mode = self.account_mode_combo.findData(account_mode_cfg)
    if idx_account_mode < 0:
        idx_account_mode = 0
    self.account_mode_combo.setCurrentIndex(idx_account_mode)
    self.account_mode_combo.currentIndexChanged.connect(self._on_runtime_account_mode_changed)
    self.config["account_mode"] = account_mode_cfg
    self._apply_runtime_account_mode_constraints(account_mode_cfg)
    grid.addWidget(self.account_mode_combo, 1, 5)

    grid.addWidget(QtWidgets.QLabel("Connector:"), 1, 6)
    self.connector_combo = QtWidgets.QComboBox()
    current_account_type = self.config.get("account_type", "Futures")
    account_key = (
        "FUTURES"
        if str(current_account_type or "Futures").strip().lower().startswith("fut")
        else "SPOT"
    )
    allowed_backends = (
        _FUTURES_CONNECTOR_KEYS if account_key == "FUTURES" else _SPOT_CONNECTOR_KEYS
    )
    for label, value in _CONNECTOR_OPTIONS:
        if value in allowed_backends:
            self.connector_combo.addItem(label, value)
    runtime_backend = self._ensure_runtime_connector_for_account(
        current_account_type,
        force_default=False,
    )
    idx_connector = self.connector_combo.findData(runtime_backend)
    if idx_connector < 0 and self.connector_combo.count():
        idx_connector = 0
    if self.connector_combo.count():
        self.connector_combo.setCurrentIndex(idx_connector)
    self.connector_combo.currentIndexChanged.connect(self._on_runtime_connector_changed)
    grid.addWidget(self.connector_combo, 1, 7, 1, 3)

    grid.addWidget(QtWidgets.QLabel("Total USDT balance:"), 2, 0)
    self.balance_label = QtWidgets.QLabel("N/A")
    grid.addWidget(self.balance_label, 2, 1)
    self.pos_mode_label = QtWidgets.QLabel("Position Mode: N/A")
    grid.addWidget(self.pos_mode_label, 2, 6, 1, 2)
    self.refresh_balance_btn = QtWidgets.QPushButton("Refresh Balance")
    self.refresh_balance_btn.clicked.connect(lambda: self.update_balance_label())
    grid.addWidget(self.refresh_balance_btn, 2, 2)

    grid.addWidget(QtWidgets.QLabel("Leverage (Futures):"), 2, 3)
    self.leverage_spin = QtWidgets.QSpinBox()
    self.leverage_spin.setRange(1, 150)
    self.leverage_spin.setValue(self.config.get("leverage", 5))
    self.leverage_spin.valueChanged.connect(self.on_leverage_changed)
    grid.addWidget(self.leverage_spin, 2, 4)
    self._update_leverage_enabled()

    grid.addWidget(QtWidgets.QLabel("Margin Mode (Futures):"), 2, 5)
    self.margin_mode_combo = QtWidgets.QComboBox()
    self.margin_mode_combo.addItems(["Cross", "Isolated"])
    self.margin_mode_combo.setCurrentText(self.config.get("margin_mode", "Isolated"))
    grid.addWidget(self.margin_mode_combo, 2, 6)
    self._apply_runtime_account_mode_constraints(
        self.config.get("account_mode", _ACCOUNT_MODE_OPTIONS[0])
    )

    grid.addWidget(QtWidgets.QLabel("Position Mode:"), 2, 7)
    self.position_mode_combo = QtWidgets.QComboBox()
    self.position_mode_combo.addItems(["One-way", "Hedge"])
    self.position_mode_combo.setCurrentText(self.config.get("position_mode", "Hedge"))
    grid.addWidget(self.position_mode_combo, 2, 8)

    grid.addWidget(QtWidgets.QLabel("Assets Mode:"), 2, 9)
    self.assets_mode_combo = QtWidgets.QComboBox()
    self.assets_mode_combo.addItem("Single-Asset Mode", "Single-Asset")
    self.assets_mode_combo.addItem("Multi-Assets Mode", "Multi-Assets")
    assets_mode_cfg = self._normalize_assets_mode(
        self.config.get("assets_mode", "Single-Asset")
    )
    idx_assets = self.assets_mode_combo.findData(assets_mode_cfg)
    if idx_assets < 0:
        idx_assets = 0
    self.assets_mode_combo.setCurrentIndex(idx_assets)
    grid.addWidget(self.assets_mode_combo, 2, 10)

    grid.addWidget(QtWidgets.QLabel("Time-in-Force:"), 3, 2)
    self.tif_combo = QtWidgets.QComboBox()
    self.tif_combo.addItems(["GTC", "IOC", "FOK", "GTD"])
    self.tif_combo.setCurrentText(self.config.get("tif", "GTC"))
    grid.addWidget(self.tif_combo, 3, 3)
    self.gtd_minutes_spin = QtWidgets.QSpinBox()
    self.gtd_minutes_spin.setRange(1, 1440)
    self.gtd_minutes_spin.setValue(self.config.get("gtd_minutes", 30))
    self.gtd_minutes_spin.setSuffix(" min (GTD)")
    self.gtd_minutes_spin.setEnabled(False)
    self.gtd_minutes_spin.setReadOnly(True)
    try:
        self.gtd_minutes_spin.setButtonSymbols(
            QtWidgets.QAbstractSpinBox.ButtonSymbols.NoButtons
        )
    except Exception:
        pass
    grid.addWidget(self.gtd_minutes_spin, 3, 4)

    def _update_gtd_visibility(text: str):
        is_gtd = text == "GTD"
        self.gtd_minutes_spin.setEnabled(is_gtd)
        self.gtd_minutes_spin.setReadOnly(not is_gtd)
        try:
            self.gtd_minutes_spin.setButtonSymbols(
                QtWidgets.QAbstractSpinBox.ButtonSymbols.UpDownArrows
                if is_gtd
                else QtWidgets.QAbstractSpinBox.ButtonSymbols.NoButtons
            )
        except Exception:
            pass

    self.tif_combo.currentTextChanged.connect(_update_gtd_visibility)
    _update_gtd_visibility(self.tif_combo.currentText())

    grid.addWidget(QtWidgets.QLabel("Indicator Source:"), 3, 0)
    self.ind_source_combo = QtWidgets.QComboBox()
    self.ind_source_combo.addItems(
        [
            "Binance spot",
            "Binance futures",
            "TradingView",
            "Bybit",
            "Coinbase",
            "OKX",
            "Gate",
            "Bitget",
            "Mexc",
            "Kucoin",
            "HTX",
            "Kraken",
        ]
    )
    self.ind_source_combo.setCurrentText(
        self.config.get("indicator_source", "Binance futures")
    )
    grid.addWidget(self.ind_source_combo, 3, 1, 1, 2)

    self._on_account_type_changed(self.account_combo.currentText())
    scroll_layout.addLayout(grid)


def bind_main_window_dashboard_header_runtime(
    MainWindow,
    *,
    account_mode_options,
    connector_options,
    futures_connector_keys,
    spot_connector_keys,
):
    global _ACCOUNT_MODE_OPTIONS
    global _CONNECTOR_OPTIONS
    global _FUTURES_CONNECTOR_KEYS
    global _SPOT_CONNECTOR_KEYS

    _ACCOUNT_MODE_OPTIONS = tuple(account_mode_options)
    _CONNECTOR_OPTIONS = tuple(connector_options)
    _FUTURES_CONNECTOR_KEYS = tuple(futures_connector_keys)
    _SPOT_CONNECTOR_KEYS = tuple(spot_connector_keys)

    MainWindow._create_dashboard_header_section = _create_dashboard_header_section
