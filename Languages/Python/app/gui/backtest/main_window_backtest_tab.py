from __future__ import annotations

import copy

from PyQt6 import QtCore, QtWidgets

_MDD_LOGIC_OPTIONS = ()
_MDD_LOGIC_LABELS = {}
_MDD_LOGIC_DEFAULT = "overall"
_DASHBOARD_LOOP_CHOICES = ()
_STOP_LOSS_MODE_ORDER = ()
_STOP_LOSS_SCOPE_OPTIONS = ()
_STOP_LOSS_MODE_LABELS = {}
_STOP_LOSS_SCOPE_LABELS = {}
_SIDE_LABELS = {}
_ACCOUNT_MODE_OPTIONS = ()
_BACKTEST_TEMPLATE_DEFINITIONS = {}
_BACKTEST_TEMPLATE_DEFAULT = {}
_INDICATOR_DISPLAY_NAMES = {}
_SYMBOL_FETCH_TOP_N = 200
_normalize_stop_loss_dict = lambda value: value  # type: ignore


def _create_backtest_tab(self, *, add_to_tabs: bool = True):
    tab3 = QtWidgets.QWidget()
    tab3_layout = QtWidgets.QVBoxLayout(tab3)
    tab3_scroll_area = QtWidgets.QScrollArea(tab3)
    tab3_scroll_area.setWidgetResizable(True)
    tab3_scroll_area.setHorizontalScrollBarPolicy(QtCore.Qt.ScrollBarPolicy.ScrollBarAsNeeded)
    tab3_layout.addWidget(tab3_scroll_area)
    tab3_scroll_widget = QtWidgets.QWidget()
    tab3_scroll_area.setWidget(tab3_scroll_widget)
    tab3_content_layout = QtWidgets.QVBoxLayout(tab3_scroll_widget)
    tab3_content_layout.setContentsMargins(12, 12, 12, 12)
    tab3_content_layout.setSpacing(16)

    top_layout = QtWidgets.QHBoxLayout()
    top_layout.setSpacing(16)

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
            self.backtest_interval_list.item(i).text()
            for i in range(self.backtest_interval_list.count())
        }
        new_items = []
        for part in parts:
            norm = part.strip()
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

    top_layout.addWidget(market_group, 3)

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
    for key in _MDD_LOGIC_OPTIONS:
        label = _MDD_LOGIC_LABELS.get(key, key.replace("_", " ").title())
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
    for label, value in _DASHBOARD_LOOP_CHOICES:
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

    backtest_stop_cfg = _normalize_stop_loss_dict(self.backtest_config.get("stop_loss"))
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
    for mode_key in _STOP_LOSS_MODE_ORDER:
        self.backtest_stop_loss_mode_combo.addItem(
            _STOP_LOSS_MODE_LABELS.get(mode_key, mode_key.title()),
            mode_key,
        )
    mode_idx = self.backtest_stop_loss_mode_combo.findData(backtest_stop_cfg.get("mode"))
    if mode_idx < 0:
        mode_idx = 0
    self.backtest_stop_loss_mode_combo.setCurrentIndex(mode_idx)
    stop_loss_layout.addWidget(self.backtest_stop_loss_mode_combo)

    stop_loss_layout.addWidget(QtWidgets.QLabel("Scope:"))
    self.backtest_stop_loss_scope_combo = QtWidgets.QComboBox()
    for scope_key in _STOP_LOSS_SCOPE_OPTIONS:
        self.backtest_stop_loss_scope_combo.addItem(
            _STOP_LOSS_SCOPE_LABELS.get(scope_key, scope_key.replace("_", " ").title()),
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
        [_SIDE_LABELS["BUY"], _SIDE_LABELS["SELL"], _SIDE_LABELS["BOTH"]]
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
    for mode in _ACCOUNT_MODE_OPTIONS:
        self.backtest_account_mode_combo.addItem(mode, mode)
    account_mode_cfg_bt = self._normalize_account_mode(
        self.backtest_config.get("account_mode", _ACCOUNT_MODE_OPTIONS[0])
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
    for key, definition in _BACKTEST_TEMPLATE_DEFINITIONS.items():
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
    self.backtest_scan_top_spin.setRange(1, max(1, int(_SYMBOL_FETCH_TOP_N)))
    scan_top_default = int(
        self.backtest_config.get("scan_top_n", _SYMBOL_FETCH_TOP_N) or _SYMBOL_FETCH_TOP_N
    )
    if scan_top_default < 1:
        scan_top_default = 1
    if scan_top_default > _SYMBOL_FETCH_TOP_N:
        scan_top_default = _SYMBOL_FETCH_TOP_N
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
        self.backtest_config.get("mdd_logic", _MDD_LOGIC_DEFAULT)
    )
    template_cfg_bt = self.backtest_config.get(
        "template",
        copy.deepcopy(_BACKTEST_TEMPLATE_DEFAULT),
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

    top_layout.addWidget(param_group, 5)

    indicator_group = QtWidgets.QGroupBox("Indicators")
    indicator_group.setMinimumWidth(220)
    indicator_group.setMaximumWidth(340)
    indicator_group.setSizePolicy(
        QtWidgets.QSizePolicy.Policy.Preferred,
        QtWidgets.QSizePolicy.Policy.Expanding,
    )
    ind_layout = QtWidgets.QGridLayout(indicator_group)
    self.backtest_indicator_widgets.clear()
    row = 0
    for key, params in self.backtest_config.get("indicators", {}).items():
        label = _INDICATOR_DISPLAY_NAMES.get(key, key)
        cb = QtWidgets.QCheckBox(label)
        cb.setProperty("indicator_key", key)
        cb.setChecked(bool(params.get("enabled", False)))
        cb.toggled.connect(lambda checked, _key=key: self._backtest_toggle_indicator(_key, checked))
        btn = QtWidgets.QPushButton("Buy-Sell Values")
        btn.clicked.connect(lambda _=False, _key=key: self._open_backtest_params(_key))
        ind_layout.addWidget(cb, row, 0)
        ind_layout.addWidget(btn, row, 1)
        self.backtest_indicator_widgets[key] = (cb, btn)
        row += 1
    top_layout.addWidget(indicator_group, stretch=3)

    pending_template = getattr(self, "_backtest_template_pending_apply", None)
    if pending_template:
        self._apply_backtest_template(pending_template)
    self._backtest_template_pending_apply = None

    tab3_content_layout.addLayout(top_layout)

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
    tab3_content_layout.addWidget(output_group)

    if add_to_tabs:
        self.backtest_tab = tab3
        self.tabs.addTab(tab3, "Backtest")
    return tab3


def bind_main_window_backtest_tab(
    MainWindow,
    *,
    mdd_logic_options,
    mdd_logic_labels,
    mdd_logic_default,
    dashboard_loop_choices,
    stop_loss_mode_order,
    stop_loss_scope_options,
    stop_loss_mode_labels,
    stop_loss_scope_labels,
    side_labels,
    account_mode_options,
    backtest_template_definitions,
    backtest_template_default,
    indicator_display_names,
    symbol_fetch_top_n,
    normalize_stop_loss_dict,
):
    global _MDD_LOGIC_OPTIONS
    global _MDD_LOGIC_LABELS
    global _MDD_LOGIC_DEFAULT
    global _DASHBOARD_LOOP_CHOICES
    global _STOP_LOSS_MODE_ORDER
    global _STOP_LOSS_SCOPE_OPTIONS
    global _STOP_LOSS_MODE_LABELS
    global _STOP_LOSS_SCOPE_LABELS
    global _SIDE_LABELS
    global _ACCOUNT_MODE_OPTIONS
    global _BACKTEST_TEMPLATE_DEFINITIONS
    global _BACKTEST_TEMPLATE_DEFAULT
    global _INDICATOR_DISPLAY_NAMES
    global _SYMBOL_FETCH_TOP_N
    global _normalize_stop_loss_dict

    _MDD_LOGIC_OPTIONS = tuple(mdd_logic_options)
    _MDD_LOGIC_LABELS = dict(mdd_logic_labels)
    _MDD_LOGIC_DEFAULT = str(mdd_logic_default)
    _DASHBOARD_LOOP_CHOICES = tuple(dashboard_loop_choices)
    _STOP_LOSS_MODE_ORDER = tuple(stop_loss_mode_order)
    _STOP_LOSS_SCOPE_OPTIONS = tuple(stop_loss_scope_options)
    _STOP_LOSS_MODE_LABELS = dict(stop_loss_mode_labels)
    _STOP_LOSS_SCOPE_LABELS = dict(stop_loss_scope_labels)
    _SIDE_LABELS = dict(side_labels)
    _ACCOUNT_MODE_OPTIONS = tuple(account_mode_options)
    _BACKTEST_TEMPLATE_DEFINITIONS = dict(backtest_template_definitions)
    _BACKTEST_TEMPLATE_DEFAULT = dict(backtest_template_default)
    _INDICATOR_DISPLAY_NAMES = dict(indicator_display_names)
    _SYMBOL_FETCH_TOP_N = int(symbol_fetch_top_n)
    _normalize_stop_loss_dict = normalize_stop_loss_dict

    MainWindow._create_backtest_tab = _create_backtest_tab
