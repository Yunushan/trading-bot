from __future__ import annotations

from PyQt6 import QtCore, QtGui, QtWidgets

_SIDE_LABELS = {}
_DASHBOARD_LOOP_CHOICES = ()
_LEAD_TRADER_OPTIONS = ()
_STOP_LOSS_MODE_ORDER = ()
_STOP_LOSS_MODE_LABELS = {}
_STOP_LOSS_SCOPE_OPTIONS = ()
_STOP_LOSS_SCOPE_LABELS = {}
_coerce_bool = lambda value, default=False: default  # type: ignore
_normalize_stop_loss_dict = lambda value: value  # type: ignore


def _create_dashboard_strategy_controls_section(self, scroll_layout):
    strat_group = QtWidgets.QGroupBox("Strategy Controls")
    layout = QtWidgets.QGridLayout(strat_group)

    layout.addWidget(QtWidgets.QLabel("Side:"), 0, 0)
    self.side_combo = QtWidgets.QComboBox()
    self.side_combo.addItems(
        [_SIDE_LABELS["BUY"], _SIDE_LABELS["SELL"], _SIDE_LABELS["BOTH"]]
    )
    current_side = (self.config.get("side", "BOTH") or "BOTH").upper()
    label = _SIDE_LABELS.get(current_side, _SIDE_LABELS["BOTH"])
    if hasattr(QtCore.Qt, "MatchFlag"):
        idx = self.side_combo.findText(label, QtCore.Qt.MatchFlag.MatchFixedString)
    else:
        idx = self.side_combo.findText(label)
    if idx >= 0:
        self.side_combo.setCurrentIndex(idx)
    else:
        self.side_combo.setCurrentIndex(2)
    self.config["side"] = self._resolve_dashboard_side()
    self.side_combo.currentTextChanged.connect(
        lambda _=None: self.config.__setitem__("side", self._resolve_dashboard_side())
    )
    layout.addWidget(self.side_combo, 0, 1)

    layout.addWidget(QtWidgets.QLabel("Position % of Balance:"), 0, 2)
    self.pospct_spin = QtWidgets.QDoubleSpinBox()
    self.pospct_spin.setRange(0.01, 100.0)
    self.pospct_spin.setDecimals(2)
    initial_pct = float(self.config.get("position_pct", 2.0))
    if initial_pct <= 1.0:
        initial_pct *= 100.0
    self.pospct_spin.setValue(initial_pct)
    layout.addWidget(self.pospct_spin, 0, 3)

    layout.addWidget(QtWidgets.QLabel("Loop Interval Override:"), 0, 4)
    self.loop_combo = QtWidgets.QComboBox()
    for label_text, value in _DASHBOARD_LOOP_CHOICES:
        self.loop_combo.addItem(label_text, value)
    initial_loop = self._normalize_loop_override(self.config.get("loop_interval_override"))
    if not initial_loop:
        initial_loop = "1m"
    self.config["loop_interval_override"] = initial_loop
    if initial_loop and self.loop_combo.findData(initial_loop) < 0:
        self.loop_combo.addItem(initial_loop, initial_loop)
    idx_loop = self.loop_combo.findData(initial_loop)
    if idx_loop < 0:
        idx_loop = 0
    self.loop_combo.setCurrentIndex(idx_loop)
    self.loop_combo.currentIndexChanged.connect(self._on_runtime_loop_changed)
    layout.addWidget(self.loop_combo, 0, 5)

    self.lead_trader_enable_cb = QtWidgets.QCheckBox("Enable Lead Trader")
    lead_trader_enabled = bool(self.config.get("lead_trader_enabled", False))
    self.lead_trader_enable_cb.setChecked(lead_trader_enabled)

    self.lead_trader_combo = QtWidgets.QComboBox()
    for label_text, value in _LEAD_TRADER_OPTIONS:
        self.lead_trader_combo.addItem(label_text, value)
    lead_trader_choice = self.config.get("lead_trader_profile") or _LEAD_TRADER_OPTIONS[0][1]
    idx_lead_trader = self.lead_trader_combo.findData(lead_trader_choice)
    if idx_lead_trader < 0:
        idx_lead_trader = 0
    self.lead_trader_combo.setCurrentIndex(idx_lead_trader)
    self.config["lead_trader_profile"] = str(self.lead_trader_combo.itemData(idx_lead_trader))
    self.lead_trader_combo.setMaximumWidth(260)
    try:
        self.lead_trader_combo.setSizePolicy(
            QtWidgets.QSizePolicy.Policy.Fixed,
            QtWidgets.QSizePolicy.Policy.Fixed,
        )
    except Exception:
        pass

    lead_trader_row = QtWidgets.QWidget()
    lead_trader_layout = QtWidgets.QHBoxLayout(lead_trader_row)
    lead_trader_layout.setContentsMargins(0, 0, 0, 0)
    lead_trader_layout.setSpacing(12)
    lead_trader_layout.addWidget(self.lead_trader_enable_cb)
    lead_trader_layout.addWidget(self.lead_trader_combo)
    lead_trader_layout.addStretch(1)
    layout.addWidget(lead_trader_row, 1, 0, 1, 6)

    self.lead_trader_enable_cb.toggled.connect(self._on_lead_trader_toggled)
    self.lead_trader_combo.currentIndexChanged.connect(self._on_lead_trader_option_changed)

    self.cb_live_indicator_values = QtWidgets.QCheckBox(
        "Use live candle values for signals (repaints)"
    )
    live_values_enabled = bool(self.config.get("indicator_use_live_values", False))
    self.config["indicator_use_live_values"] = live_values_enabled
    self.cb_live_indicator_values.setChecked(live_values_enabled)
    self.cb_live_indicator_values.setToolTip(
        "When unchecked, signals use the previous closed candle (no repaint), which matches candle-close backtests "
        "and TradingView values on bar close."
    )
    self.cb_live_indicator_values.stateChanged.connect(
        lambda state: self.config.__setitem__(
            "indicator_use_live_values",
            bool(state == QtCore.Qt.CheckState.Checked),
        )
    )
    layout.addWidget(self.cb_live_indicator_values, 2, 0, 1, 6)

    self.cb_add_only = QtWidgets.QCheckBox("Add-only in current net direction (one-way)")
    self.cb_add_only.setChecked(bool(self.config.get("add_only", False)))
    layout.addWidget(self.cb_add_only, 3, 0, 1, 6)

    self.allow_opposite_checkbox = QtWidgets.QCheckBox(
        "Allow simultaneous long & short positions (hedge stacking)"
    )
    allow_opposite_enabled = _coerce_bool(
        self.config.get("allow_opposite_positions", True),
        True,
    )
    self.config["allow_opposite_positions"] = allow_opposite_enabled
    self.allow_opposite_checkbox.setChecked(allow_opposite_enabled)
    self.allow_opposite_checkbox.setToolTip(
        "When enabled, the bot may keep both long and short positions open at the same time if hedge mode is active. "
        "Leave disabled to force the bot to close the opposite side before opening a new trade."
    )
    self.allow_opposite_checkbox.stateChanged.connect(self._on_allow_opposite_changed)
    layout.addWidget(self.allow_opposite_checkbox, 4, 0, 1, 6)

    self.cb_stop_without_close = QtWidgets.QCheckBox(
        "Stop Bot Without Closing Active Positions"
    )
    stop_without_close = bool(self.config.get("stop_without_close", False))
    self.cb_stop_without_close.setChecked(stop_without_close)
    self.cb_stop_without_close.setToolTip(
        "When checked, the Stop button will halt strategy threads but leave all open positions untouched."
    )
    self.cb_stop_without_close.stateChanged.connect(
        lambda state: self.config.__setitem__(
            "stop_without_close",
            bool(state == QtCore.Qt.CheckState.Checked),
        )
    )
    layout.addWidget(self.cb_stop_without_close, 5, 0, 1, 6)

    self.cb_close_on_exit = QtWidgets.QCheckBox(
        "Market Close All Active Positions On Window Close (Working in progress)"
    )
    self.cb_close_on_exit.setChecked(False)
    self.cb_close_on_exit.setEnabled(False)
    self.cb_close_on_exit.setCheckable(False)
    try:
        self.cb_close_on_exit.setAttribute(
            QtCore.Qt.WidgetAttribute.WA_TransparentForMouseEvents,
            True,
        )
    except Exception:
        pass
    try:
        pal = self.cb_close_on_exit.palette()
        disabled_color = pal.color(
            QtGui.QPalette.ColorGroup.Disabled,
            QtGui.QPalette.ColorRole.Text,
        )
        pal.setColor(QtGui.QPalette.ColorRole.WindowText, disabled_color)
        self.cb_close_on_exit.setPalette(pal)
        pal.setColor(QtGui.QPalette.ColorRole.ButtonText, disabled_color)
        pal.setColor(QtGui.QPalette.ColorRole.Text, disabled_color)
        self.cb_close_on_exit.setPalette(pal)
        self.cb_close_on_exit.setStyleSheet("color: #5a5f70;")
    except Exception:
        pass
    self.cb_close_on_exit.setToolTip("Disabled while improvements are in progress.")
    self.config["close_on_exit"] = False
    self.cb_close_on_exit.stateChanged.connect(self._on_close_on_exit_changed)
    layout.addWidget(self.cb_close_on_exit, 6, 0, 1, 6)

    self._apply_lead_trader_state(lead_trader_enabled)

    stop_cfg = _normalize_stop_loss_dict(self.config.get("stop_loss"))
    self.config["stop_loss"] = stop_cfg

    layout.addWidget(QtWidgets.QLabel("Stop Loss:"), 7, 0)
    self.stop_loss_enable_cb = QtWidgets.QCheckBox("Enable")
    self.stop_loss_enable_cb.setToolTip("Toggle automatic stop-loss handling for live trades.")
    self.stop_loss_enable_cb.setChecked(stop_cfg.get("enabled", False))
    layout.addWidget(self.stop_loss_enable_cb, 7, 1)

    self.stop_loss_mode_combo = QtWidgets.QComboBox()
    for mode_key in _STOP_LOSS_MODE_ORDER:
        self.stop_loss_mode_combo.addItem(
            _STOP_LOSS_MODE_LABELS.get(mode_key, mode_key.title()),
            mode_key,
        )
    mode_idx = self.stop_loss_mode_combo.findData(stop_cfg.get("mode"))
    if mode_idx < 0:
        mode_idx = 0
    self.stop_loss_mode_combo.setCurrentIndex(mode_idx)
    layout.addWidget(self.stop_loss_mode_combo, 7, 2, 1, 2)

    self.stop_loss_usdt_spin = QtWidgets.QDoubleSpinBox()
    self.stop_loss_usdt_spin.setRange(0.0, 1_000_000_000.0)
    self.stop_loss_usdt_spin.setDecimals(2)
    self.stop_loss_usdt_spin.setSingleStep(1.0)
    self.stop_loss_usdt_spin.setSuffix(" USDT")
    self.stop_loss_usdt_spin.setValue(float(stop_cfg.get("usdt", 0.0)))
    layout.addWidget(self.stop_loss_usdt_spin, 7, 4)

    self.stop_loss_percent_spin = QtWidgets.QDoubleSpinBox()
    self.stop_loss_percent_spin.setRange(0.0, 100.0)
    self.stop_loss_percent_spin.setDecimals(2)
    self.stop_loss_percent_spin.setSingleStep(0.5)
    self.stop_loss_percent_spin.setSuffix(" %")
    self.stop_loss_percent_spin.setValue(float(stop_cfg.get("percent", 0.0)))
    layout.addWidget(self.stop_loss_percent_spin, 7, 5)

    self.stop_loss_scope_combo = QtWidgets.QComboBox()
    for scope_key in _STOP_LOSS_SCOPE_OPTIONS:
        label = _STOP_LOSS_SCOPE_LABELS.get(scope_key, scope_key.replace("_", " ").title())
        self.stop_loss_scope_combo.addItem(label, scope_key)
    scope_idx = self.stop_loss_scope_combo.findData(stop_cfg.get("scope"))
    if scope_idx < 0:
        scope_idx = 0
    self.stop_loss_scope_combo.setCurrentIndex(scope_idx)
    layout.addWidget(QtWidgets.QLabel("Stop Loss Scope:"), 8, 0)
    layout.addWidget(self.stop_loss_scope_combo, 8, 1, 1, 2)

    self._dashboard_templates = {
        "top10": {
            "label": "Top 10 %2 per trade 5x Isolated",
            "position_pct": 2.0,
            "leverage": 5,
            "margin_mode": "Isolated",
            "indicators": {
                "rsi": {"enabled": True, "buy_value": 30, "sell_value": 70},
                "stoch_rsi": {"enabled": True, "buy_value": 20, "sell_value": 80},
                "willr": {"enabled": True, "buy_value": -80, "sell_value": -20},
            },
        },
        "top50": {
            "label": "Top 50 %2 per trade 20x",
            "position_pct": 2.0,
            "leverage": 20,
            "margin_mode": "Isolated",
            "indicators": {
                "rsi": {"enabled": True, "buy_value": 30, "sell_value": 70},
                "stoch_rsi": {"enabled": True, "buy_value": 20, "sell_value": 80},
                "willr": {"enabled": True, "buy_value": -80, "sell_value": -20},
            },
        },
        "top100": {
            "label": "Top 100 %1 per trade 5x",
            "position_pct": 1.0,
            "leverage": 5,
            "margin_mode": "Isolated",
            "indicators": {
                "rsi": {"enabled": True, "buy_value": 30, "sell_value": 70},
                "stoch_rsi": {"enabled": True, "buy_value": 20, "sell_value": 80},
                "willr": {"enabled": True, "buy_value": -80, "sell_value": -20},
            },
        },
    }
    layout.addWidget(QtWidgets.QLabel("Template:"), 9, 0)
    self.template_combo = QtWidgets.QComboBox()
    self.template_combo.addItem("No Template", "")
    for key, info in self._dashboard_templates.items():
        self.template_combo.addItem(info["label"], key)
    current_template = str(self.config.get("dashboard_template") or "")
    idx_template = self.template_combo.findData(current_template)
    if idx_template < 0:
        idx_template = 0
    self.template_combo.setCurrentIndex(idx_template)
    self.template_combo.currentIndexChanged.connect(self._on_dashboard_template_changed)
    layout.addWidget(self.template_combo, 9, 1, 1, 3)

    self.stop_loss_enable_cb.toggled.connect(self._on_runtime_stop_loss_enabled)
    self.stop_loss_mode_combo.currentIndexChanged.connect(
        self._on_runtime_stop_loss_mode_changed
    )
    self.stop_loss_usdt_spin.valueChanged.connect(
        lambda v: self._on_runtime_stop_loss_value_changed("usdt", v)
    )
    self.stop_loss_percent_spin.valueChanged.connect(
        lambda v: self._on_runtime_stop_loss_value_changed("percent", v)
    )
    self.stop_loss_scope_combo.currentTextChanged.connect(
        lambda _: self._on_runtime_stop_loss_scope_changed()
    )
    self._update_runtime_stop_loss_widgets()

    scroll_layout.addWidget(strat_group)


def bind_main_window_dashboard_strategy_runtime(
    MainWindow,
    *,
    side_labels,
    dashboard_loop_choices,
    lead_trader_options,
    stop_loss_mode_order,
    stop_loss_mode_labels,
    stop_loss_scope_options,
    stop_loss_scope_labels,
    coerce_bool,
    normalize_stop_loss_dict,
):
    global _SIDE_LABELS
    global _DASHBOARD_LOOP_CHOICES
    global _LEAD_TRADER_OPTIONS
    global _STOP_LOSS_MODE_ORDER
    global _STOP_LOSS_MODE_LABELS
    global _STOP_LOSS_SCOPE_OPTIONS
    global _STOP_LOSS_SCOPE_LABELS
    global _coerce_bool
    global _normalize_stop_loss_dict

    _SIDE_LABELS = dict(side_labels)
    _DASHBOARD_LOOP_CHOICES = tuple(dashboard_loop_choices)
    _LEAD_TRADER_OPTIONS = tuple(lead_trader_options)
    _STOP_LOSS_MODE_ORDER = tuple(stop_loss_mode_order)
    _STOP_LOSS_MODE_LABELS = dict(stop_loss_mode_labels)
    _STOP_LOSS_SCOPE_OPTIONS = tuple(stop_loss_scope_options)
    _STOP_LOSS_SCOPE_LABELS = dict(stop_loss_scope_labels)
    _coerce_bool = coerce_bool
    _normalize_stop_loss_dict = normalize_stop_loss_dict

    MainWindow._create_dashboard_strategy_controls_section = _create_dashboard_strategy_controls_section
