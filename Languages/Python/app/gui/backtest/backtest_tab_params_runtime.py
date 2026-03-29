from __future__ import annotations

import copy

from PyQt6 import QtCore, QtWidgets

from . import backtest_tab_context_runtime as tab_context_runtime


def build_backtest_params_group(self):
    param_group = QtWidgets.QGroupBox("Backtest Parameters")
    param_group.setMinimumWidth(320)
    param_group.setMaximumWidth(820)
    param_group.setSizePolicy(
        QtWidgets.QSizePolicy.Policy.Expanding,
        QtWidgets.QSizePolicy.Policy.Expanding,
    )
    param_form = QtWidgets.QFormLayout(param_group)
    param_form.setFieldGrowthPolicy(QtWidgets.QFormLayout.FieldGrowthPolicy.AllNonFixedFieldsGrow)
    param_form.setLabelAlignment(QtCore.Qt.AlignmentFlag.AlignRight | QtCore.Qt.AlignmentFlag.AlignVCenter)

    self.backtest_start_edit = QtWidgets.QDateTimeEdit()
    self.backtest_start_edit.setCalendarPopup(True)
    self.backtest_start_edit.setDisplayFormat("dd.MM.yyyy HH:mm:ss")
    self.backtest_end_edit = QtWidgets.QDateTimeEdit()
    self.backtest_end_edit.setCalendarPopup(True)
    self.backtest_end_edit.setDisplayFormat("dd.MM.yyyy HH:mm:ss")
    self.backtest_start_edit.dateTimeChanged.connect(self._backtest_dates_changed)
    self.backtest_end_edit.dateTimeChanged.connect(self._backtest_dates_changed)
    param_form.addRow("Start Date/Time:", self.backtest_start_edit)
    param_form.addRow("End Date/Time:", self.backtest_end_edit)

    self.backtest_logic_combo = QtWidgets.QComboBox()
    self.backtest_logic_combo.addItems(["AND", "OR", "SEPARATE"])
    self.backtest_logic_combo.currentTextChanged.connect(
        lambda v: self._update_backtest_config("logic", v)
    )
    param_form.addRow("Signal Logic:", self.backtest_logic_combo)

    self.backtest_mdd_combo = QtWidgets.QComboBox()
    for key in tab_context_runtime._MDD_LOGIC_OPTIONS:
        label = tab_context_runtime._MDD_LOGIC_LABELS.get(key, key.replace("_", " ").title())
        self.backtest_mdd_combo.addItem(label, key)
    self.backtest_mdd_combo.currentIndexChanged.connect(self._on_backtest_mdd_logic_changed)
    param_form.addRow("MDD Logic:", self.backtest_mdd_combo)

    self.backtest_capital_spin = QtWidgets.QDoubleSpinBox()
    self.backtest_capital_spin.setDecimals(2)
    self.backtest_capital_spin.setRange(1.0, 1_000_000_000.0)
    self.backtest_capital_spin.setSuffix(" USDT")
    self.backtest_capital_spin.valueChanged.connect(
        lambda v: self._update_backtest_config("capital", float(v))
    )
    param_form.addRow("Margin Capital:", self.backtest_capital_spin)

    self.backtest_pospct_spin = QtWidgets.QDoubleSpinBox()
    self.backtest_pospct_spin.setDecimals(2)
    self.backtest_pospct_spin.setRange(0.01, 100.0)
    self.backtest_pospct_spin.setSuffix(" %")
    self.backtest_pospct_spin.valueChanged.connect(
        lambda v: self._update_backtest_config("position_pct", float(v))
    )
    param_form.addRow("Position % of Balance:", self.backtest_pospct_spin)

    self.backtest_loop_combo = QtWidgets.QComboBox()
    for label, value in tab_context_runtime._DASHBOARD_LOOP_CHOICES:
        self.backtest_loop_combo.addItem(label, value)
    loop_default = self._normalize_loop_override(self.backtest_config.get("loop_interval_override")) or ""
    if loop_default and self.backtest_loop_combo.findData(loop_default) < 0:
        self.backtest_loop_combo.addItem(loop_default, loop_default)
    idx_backtest_loop = self.backtest_loop_combo.findData(loop_default)
    if idx_backtest_loop < 0:
        idx_backtest_loop = 0
    self.backtest_loop_combo.setCurrentIndex(idx_backtest_loop)
    self.backtest_loop_combo.currentIndexChanged.connect(self._on_backtest_loop_changed)
    self.backtest_config["loop_interval_override"] = loop_default
    self.config.setdefault("backtest", {})["loop_interval_override"] = loop_default
    param_form.addRow("Loop Interval Override:", self.backtest_loop_combo)

    backtest_stop_cfg = tab_context_runtime._normalize_stop_loss_dict(self.backtest_config.get("stop_loss"))
    self.backtest_config["stop_loss"] = backtest_stop_cfg
    self.config.setdefault("backtest", {})["stop_loss"] = copy.deepcopy(backtest_stop_cfg)

    stop_loss_row = QtWidgets.QWidget()
    stop_loss_layout = QtWidgets.QHBoxLayout(stop_loss_row)
    stop_loss_layout.setContentsMargins(0, 0, 0, 0)
    stop_loss_layout.setSpacing(6)

    self.backtest_stop_loss_enable_cb = QtWidgets.QCheckBox("Enable")
    self.backtest_stop_loss_enable_cb.setChecked(backtest_stop_cfg.get("enabled", False))
    stop_loss_layout.addWidget(self.backtest_stop_loss_enable_cb)

    self.backtest_stop_loss_mode_combo = QtWidgets.QComboBox()
    for mode_key in tab_context_runtime._STOP_LOSS_MODE_ORDER:
        self.backtest_stop_loss_mode_combo.addItem(
            tab_context_runtime._STOP_LOSS_MODE_LABELS.get(mode_key, mode_key.title()),
            mode_key,
        )
    mode_idx = self.backtest_stop_loss_mode_combo.findData(backtest_stop_cfg.get("mode"))
    if mode_idx < 0:
        mode_idx = 0
    self.backtest_stop_loss_mode_combo.setCurrentIndex(mode_idx)
    stop_loss_layout.addWidget(self.backtest_stop_loss_mode_combo)

    stop_loss_layout.addWidget(QtWidgets.QLabel("Scope:"))
    self.backtest_stop_loss_scope_combo = QtWidgets.QComboBox()
    for scope_key in tab_context_runtime._STOP_LOSS_SCOPE_OPTIONS:
        self.backtest_stop_loss_scope_combo.addItem(
            tab_context_runtime._STOP_LOSS_SCOPE_LABELS.get(scope_key, scope_key.replace("_", " ").title()),
            scope_key,
        )
    scope_idx = self.backtest_stop_loss_scope_combo.findData(backtest_stop_cfg.get("scope"))
    if scope_idx < 0:
        scope_idx = 0
    self.backtest_stop_loss_scope_combo.setCurrentIndex(scope_idx)
    stop_loss_layout.addWidget(self.backtest_stop_loss_scope_combo)

    self.backtest_stop_loss_usdt_spin = QtWidgets.QDoubleSpinBox()
    self.backtest_stop_loss_usdt_spin.setRange(0.0, 1_000_000_000.0)
    self.backtest_stop_loss_usdt_spin.setDecimals(2)
    self.backtest_stop_loss_usdt_spin.setSingleStep(1.0)
    self.backtest_stop_loss_usdt_spin.setSuffix(" USDT")
    self.backtest_stop_loss_usdt_spin.setValue(float(backtest_stop_cfg.get("usdt", 0.0)))
    stop_loss_layout.addWidget(self.backtest_stop_loss_usdt_spin)

    self.backtest_stop_loss_percent_spin = QtWidgets.QDoubleSpinBox()
    self.backtest_stop_loss_percent_spin.setRange(0.0, 100.0)
    self.backtest_stop_loss_percent_spin.setDecimals(2)
    self.backtest_stop_loss_percent_spin.setSingleStep(0.5)
    self.backtest_stop_loss_percent_spin.setSuffix(" %")
    self.backtest_stop_loss_percent_spin.setValue(float(backtest_stop_cfg.get("percent", 0.0)))
    stop_loss_layout.addWidget(self.backtest_stop_loss_percent_spin)

    stop_loss_layout.addStretch()
    param_form.addRow("Stop Loss:", stop_loss_row)

    self.backtest_stop_loss_enable_cb.toggled.connect(self._on_backtest_stop_loss_enabled)
    self.backtest_stop_loss_mode_combo.currentIndexChanged.connect(
        self._on_backtest_stop_loss_mode_changed
    )
    self.backtest_stop_loss_scope_combo.currentTextChanged.connect(
        lambda _: self._on_backtest_stop_loss_scope_changed()
    )
    self.backtest_stop_loss_usdt_spin.valueChanged.connect(
        lambda v: self._on_backtest_stop_loss_value_changed("usdt", v)
    )
    self.backtest_stop_loss_percent_spin.valueChanged.connect(
        lambda v: self._on_backtest_stop_loss_value_changed("percent", v)
    )
    self._update_backtest_stop_loss_widgets()

    self.backtest_side_combo = QtWidgets.QComboBox()
    self.backtest_side_combo.addItems(
        [
            tab_context_runtime._SIDE_LABELS["BUY"],
            tab_context_runtime._SIDE_LABELS["SELL"],
            tab_context_runtime._SIDE_LABELS["BOTH"],
        ]
    )
    self.backtest_side_combo.currentTextChanged.connect(
        lambda v: self._update_backtest_config("side", v)
    )
    param_form.addRow("Side:", self.backtest_side_combo)

    self.backtest_margin_mode_combo = QtWidgets.QComboBox()
    self.backtest_margin_mode_combo.addItems(["Isolated", "Cross"])
    self.backtest_margin_mode_combo.currentTextChanged.connect(
        lambda v: self._update_backtest_config("margin_mode", v)
    )
    param_form.addRow("Margin Mode (Futures):", self.backtest_margin_mode_combo)

    self.backtest_position_mode_combo = QtWidgets.QComboBox()
    self.backtest_position_mode_combo.addItems(["Hedge", "One-way"])
    self.backtest_position_mode_combo.currentTextChanged.connect(
        lambda v: self._update_backtest_config("position_mode", v)
    )
    param_form.addRow("Position Mode:", self.backtest_position_mode_combo)

    self.backtest_assets_mode_combo = QtWidgets.QComboBox()
    self.backtest_assets_mode_combo.addItem("Single-Asset Mode", "Single-Asset")
    self.backtest_assets_mode_combo.addItem("Multi-Assets Mode", "Multi-Assets")
    assets_mode_cfg_bt = self._normalize_assets_mode(
        self.backtest_config.get("assets_mode", "Single-Asset")
    )
    idx_assets_bt = self.backtest_assets_mode_combo.findData(assets_mode_cfg_bt)
    if idx_assets_bt < 0:
        idx_assets_bt = 0
    with QtCore.QSignalBlocker(self.backtest_assets_mode_combo):
        self.backtest_assets_mode_combo.setCurrentIndex(idx_assets_bt)
    self.backtest_assets_mode_combo.currentIndexChanged.connect(
        lambda idx: self._update_backtest_config(
            "assets_mode",
            self._normalize_assets_mode(self.backtest_assets_mode_combo.itemData(idx)),
        )
    )
    param_form.addRow("Assets Mode:", self.backtest_assets_mode_combo)

    self.backtest_account_mode_combo = QtWidgets.QComboBox()
    for mode in tab_context_runtime._ACCOUNT_MODE_OPTIONS:
        self.backtest_account_mode_combo.addItem(mode, mode)
    account_mode_cfg_bt = self._normalize_account_mode(
        self.backtest_config.get("account_mode", tab_context_runtime._ACCOUNT_MODE_OPTIONS[0])
    )
    idx_account_mode_bt = self.backtest_account_mode_combo.findData(account_mode_cfg_bt)
    if idx_account_mode_bt < 0:
        idx_account_mode_bt = 0
    with QtCore.QSignalBlocker(self.backtest_account_mode_combo):
        self.backtest_account_mode_combo.setCurrentIndex(idx_account_mode_bt)
    self.backtest_account_mode_combo.currentIndexChanged.connect(
        self._on_backtest_account_mode_changed
    )
    self.backtest_config["account_mode"] = account_mode_cfg_bt
    self.config.setdefault("backtest", {})["account_mode"] = account_mode_cfg_bt
    self._apply_backtest_account_mode_constraints(account_mode_cfg_bt)
    param_form.addRow("Account Mode:", self.backtest_account_mode_combo)

    self.backtest_connector_combo = QtWidgets.QComboBox()
    self._refresh_backtest_connector_options(force_default=False)
    self.backtest_connector_combo.currentIndexChanged.connect(self._on_backtest_connector_changed)
    param_form.addRow("Connector:", self.backtest_connector_combo)

    self.backtest_leverage_spin = QtWidgets.QSpinBox()
    self.backtest_leverage_spin.setRange(1, 150)
    self.backtest_leverage_spin.valueChanged.connect(
        lambda v: self._update_backtest_config("leverage", int(v))
    )
    param_form.addRow("Leverage (Futures):", self.backtest_leverage_spin)

    template_row = QtWidgets.QWidget()
    template_layout = QtWidgets.QHBoxLayout(template_row)
    template_layout.setContentsMargins(0, 0, 0, 0)
    template_layout.setSpacing(6)

    self.backtest_template_enable_cb = QtWidgets.QCheckBox("Enable")
    template_layout.addWidget(self.backtest_template_enable_cb)

    self.backtest_template_combo = QtWidgets.QComboBox()
    for key, definition in tab_context_runtime._BACKTEST_TEMPLATE_DEFINITIONS.items():
        label = definition.get("label", key.replace("_", " ").title())
        self.backtest_template_combo.addItem(label, key)
    template_layout.addWidget(self.backtest_template_combo, stretch=1)
    param_form.addRow("Template:", template_row)

    scan_header = QtWidgets.QWidget()
    scan_header_layout = QtWidgets.QHBoxLayout(scan_header)
    scan_header_layout.setContentsMargins(0, 0, 0, 0)
    scan_header_layout.setSpacing(8)
    scan_title = QtWidgets.QLabel("Max MDD Scanner")
    scan_title.setStyleSheet("font-weight: 600;")
    scan_header_layout.addWidget(scan_title)
    scan_divider = QtWidgets.QFrame()
    scan_divider.setFrameShape(QtWidgets.QFrame.Shape.HLine)
    scan_divider.setFrameShadow(QtWidgets.QFrame.Shadow.Sunken)
    scan_header_layout.addWidget(scan_divider, stretch=1)
    param_form.addRow(scan_header)

    scan_row = QtWidgets.QWidget()
    scan_layout = QtWidgets.QHBoxLayout(scan_row)
    scan_layout.setContentsMargins(0, 0, 0, 0)
    scan_layout.setSpacing(6)
    scan_layout.addWidget(QtWidgets.QLabel("Top N:"))
    self.backtest_scan_top_spin = QtWidgets.QSpinBox()
    self.backtest_scan_top_spin.setRange(1, max(1, int(tab_context_runtime._SYMBOL_FETCH_TOP_N)))
    scan_top_default = int(
        self.backtest_config.get("scan_top_n", tab_context_runtime._SYMBOL_FETCH_TOP_N)
        or tab_context_runtime._SYMBOL_FETCH_TOP_N
    )
    if scan_top_default < 1:
        scan_top_default = 1
    if scan_top_default > tab_context_runtime._SYMBOL_FETCH_TOP_N:
        scan_top_default = tab_context_runtime._SYMBOL_FETCH_TOP_N
    self.backtest_scan_top_spin.setValue(scan_top_default)
    self.backtest_scan_top_spin.valueChanged.connect(
        lambda v: self._update_backtest_config("scan_top_n", int(v))
    )
    scan_layout.addWidget(self.backtest_scan_top_spin)
    scan_layout.addWidget(QtWidgets.QLabel("Max MDD %:"))
    self.backtest_scan_mdd_spin = QtWidgets.QDoubleSpinBox()
    self.backtest_scan_mdd_spin.setRange(0.0, 100.0)
    self.backtest_scan_mdd_spin.setDecimals(2)
    self.backtest_scan_mdd_spin.setSingleStep(0.5)
    scan_mdd_default = float(self.backtest_config.get("scan_mdd_limit", 10.0) or 10.0)
    if scan_mdd_default < 0.0:
        scan_mdd_default = 0.0
    self.backtest_scan_mdd_spin.setValue(scan_mdd_default)
    self.backtest_scan_mdd_spin.valueChanged.connect(
        lambda v: self._update_backtest_config("scan_mdd_limit", float(v))
    )
    scan_layout.addWidget(self.backtest_scan_mdd_spin)
    self.backtest_scan_btn = QtWidgets.QPushButton("Scan Symbols")
    self.backtest_scan_btn.clicked.connect(self._run_backtest_scan)
    scan_layout.addWidget(self.backtest_scan_btn)
    scan_layout.addStretch()
    param_form.addRow("Max MDD Scanner:", scan_row)

    self.backtest_template_enable_cb.toggled.connect(self._on_backtest_template_enabled)
    self.backtest_template_combo.currentIndexChanged.connect(self._on_backtest_template_selected)

    self._backtest_futures_widgets = [
        self.backtest_margin_mode_combo,
        param_form.labelForField(self.backtest_margin_mode_combo),
        self.backtest_position_mode_combo,
        param_form.labelForField(self.backtest_position_mode_combo),
        self.backtest_assets_mode_combo,
        param_form.labelForField(self.backtest_assets_mode_combo),
        self.backtest_account_mode_combo,
        param_form.labelForField(self.backtest_account_mode_combo),
        self.backtest_leverage_spin,
        param_form.labelForField(self.backtest_leverage_spin),
    ]

    self._set_backtest_mdd_selection(
        self.backtest_config.get("mdd_logic", tab_context_runtime._MDD_LOGIC_DEFAULT)
    )
    template_cfg_bt = self.backtest_config.get(
        "template",
        copy.deepcopy(tab_context_runtime._BACKTEST_TEMPLATE_DEFAULT),
    )
    selected_template = self._select_backtest_template(
        template_cfg_bt.get("name"),
        update_config=False,
    )
    template_enabled = bool(template_cfg_bt.get("enabled", False))
    with QtCore.QSignalBlocker(self.backtest_template_enable_cb):
        self.backtest_template_enable_cb.setChecked(template_enabled)
    combo = getattr(self, "backtest_template_combo", None)
    if combo is not None:
        combo.setEnabled(template_enabled and combo.count() > 0)
    template_cfg_bt["name"] = selected_template
    self.backtest_config["template"] = template_cfg_bt
    self.config.setdefault("backtest", {})["template"] = copy.deepcopy(template_cfg_bt)
    self._backtest_template_pending_apply = selected_template if template_enabled else None
    return param_group


__all__ = ["build_backtest_params_group"]
