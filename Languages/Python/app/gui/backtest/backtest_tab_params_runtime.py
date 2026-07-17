from __future__ import annotations

import copy

from PyQt6 import QtCore, QtWidgets

from app.core.backtest.indicator_selection_runtime import (
    build_backtest_indicator_definitions,
)
from app.core.backtest.indicator_runtime import signal_indicators

from . import backtest_optimizer_runtime
from . import backtest_tab_context_runtime as tab_context_runtime


def _selected_backtest_symbols_for_estimate(self) -> list[str]:
    symbols = [
        str(symbol or "").strip().upper()
        for symbol in (self.backtest_config.get("symbols") or [])
        if str(symbol or "").strip()
    ]
    if symbols:
        return symbols
    symbol_list = getattr(self, "backtest_symbol_list", None)
    if symbol_list is None:
        return []
    try:
        return [
            str(item.text() or "").strip().upper()
            for item in symbol_list.selectedItems()
            if str(item.text() or "").strip()
        ]
    except Exception:
        return []


def _selected_backtest_intervals_for_estimate(self) -> list[str]:
    intervals = [
        str(interval or "").strip()
        for interval in (self.backtest_config.get("intervals") or [])
        if str(interval or "").strip()
    ]
    if intervals:
        return intervals
    interval_list = getattr(self, "backtest_interval_list", None)
    if interval_list is None:
        return []
    try:
        return [
            str(item.text() or "").strip()
            for item in interval_list.selectedItems()
            if str(item.text() or "").strip()
        ]
    except Exception:
        return []


def refresh_backtest_optimizer_estimate(self) -> None:
    label = getattr(self, "backtest_optimizer_estimate_label", None)
    if label is None:
        return
    try:
        indicators = build_backtest_indicator_definitions(
            self.backtest_config.get("indicators", {}) or {}
        )
        signal_keys = [indicator.key for indicator in signal_indicators(indicators)]
        scope_combo = getattr(self, "backtest_scan_scope_combo", None)
        mode_combo = getattr(self, "backtest_optimizer_mode_combo", None)
        scope = (
            scope_combo.currentData()
            if scope_combo is not None
            else self.backtest_config.get("scan_scope", "selected")
        )
        mode = (
            mode_combo.currentData()
            if mode_combo is not None
            else self.backtest_config.get("optimizer_mode", "current")
        )
        try:
            top_n = int(self.backtest_scan_top_spin.value())
        except Exception:
            top_n = int(self.backtest_config.get("scan_top_n", 1) or 1)
        try:
            combo_size = int(self.backtest_optimizer_combo_size_spin.value())
        except Exception:
            combo_size = int(self.backtest_config.get("optimizer_combo_size", 2) or 2)
        logic = str(self.backtest_config.get("logic", "AND") or "AND").upper()
        plan = backtest_optimizer_runtime.estimate_scan_plan(
            symbols_all=getattr(self, "backtest_symbols_all", []) or [],
            selected_symbols=_selected_backtest_symbols_for_estimate(self),
            intervals=_selected_backtest_intervals_for_estimate(self),
            indicator_keys=signal_keys,
            scope=str(scope or ""),
            top_n=top_n,
            mode=str(mode or ""),
            combo_size=combo_size,
            logic=logic,
        )
        try:
            budget_seconds = int(self.backtest_optimizer_max_duration_spin.value()) * 60
        except Exception:
            budget_seconds = int(self.backtest_config.get("optimizer_max_duration_seconds", 14_400) or 14_400)
        label.setText(
            f"{backtest_optimizer_runtime.format_scan_plan_estimate(plan)} "
            f"Execution budget: {backtest_optimizer_runtime.format_optimizer_duration(budget_seconds)}; "
            "completed results are retained when reached."
        )
        if plan.get("over_limit"):
            label.setStyleSheet("color: #ff6b6b; font-weight: 600;")
        elif plan.get("large_warning") or plan.get("interactive_warning"):
            label.setStyleSheet("color: #ffb84d; font-weight: 600;")
        else:
            label.setStyleSheet("color: #9fd0ff;")
        button = getattr(self, "backtest_scan_btn", None)
        scan_worker = getattr(self, "backtest_scan_worker", None)
        backtest_worker = getattr(self, "backtest_worker", None)
        scan_busy = bool(scan_worker is not None and scan_worker.isRunning())
        backtest_busy = bool(backtest_worker is not None and backtest_worker.isRunning())
        if button is not None and not scan_busy and not backtest_busy:
            button.setEnabled(not bool(plan.get("over_limit")))
    except Exception:
        try:
            label.setText("Estimated optimizer runs: unavailable")
            label.setStyleSheet("color: #ffb86b;")
        except Exception:
            pass


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

    self.backtest_fee_bps_spin = QtWidgets.QDoubleSpinBox()
    self.backtest_fee_bps_spin.setDecimals(2)
    self.backtest_fee_bps_spin.setRange(0.0, 1_000.0)
    self.backtest_fee_bps_spin.setSingleStep(0.5)
    self.backtest_fee_bps_spin.setSuffix(" bps / side")
    self.backtest_fee_bps_spin.setToolTip(
        "Estimated trading fee charged at both entry and exit. 100 bps equals 1%."
    )
    self.backtest_fee_bps_spin.valueChanged.connect(
        lambda v: self._update_backtest_config("fee_bps", float(v))
    )
    param_form.addRow("Trading Fee:", self.backtest_fee_bps_spin)

    self.backtest_slippage_bps_spin = QtWidgets.QDoubleSpinBox()
    self.backtest_slippage_bps_spin.setDecimals(2)
    self.backtest_slippage_bps_spin.setRange(0.0, 1_000.0)
    self.backtest_slippage_bps_spin.setSingleStep(0.5)
    self.backtest_slippage_bps_spin.setSuffix(" bps / side")
    self.backtest_slippage_bps_spin.setToolTip(
        "Estimated adverse price movement applied at both entry and exit. 100 bps equals 1%."
    )
    self.backtest_slippage_bps_spin.valueChanged.connect(
        lambda v: self._update_backtest_config("slippage_bps", float(v))
    )
    param_form.addRow("Slippage:", self.backtest_slippage_bps_spin)

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
    scan_title = QtWidgets.QLabel("ROI Optimizer / Max MDD Scanner")
    scan_title.setStyleSheet("font-weight: 600;")
    scan_header_layout.addWidget(scan_title)
    scan_divider = QtWidgets.QFrame()
    scan_divider.setFrameShape(QtWidgets.QFrame.Shape.HLine)
    scan_divider.setFrameShadow(QtWidgets.QFrame.Shadow.Sunken)
    scan_header_layout.addWidget(scan_divider, stretch=1)
    param_form.addRow(scan_header)

    optimizer_row = QtWidgets.QWidget()
    optimizer_layout = QtWidgets.QHBoxLayout(optimizer_row)
    optimizer_layout.setContentsMargins(0, 0, 0, 0)
    optimizer_layout.setSpacing(6)

    optimizer_layout.addWidget(QtWidgets.QLabel("Scope:"))
    self.backtest_scan_scope_combo = QtWidgets.QComboBox()
    for label, value in backtest_optimizer_runtime.SCAN_SCOPE_OPTIONS:
        self.backtest_scan_scope_combo.addItem(label, value)
    scan_scope = backtest_optimizer_runtime.normalize_scan_scope(
        self.backtest_config.get("scan_scope", "selected")
    )
    scope_idx = self.backtest_scan_scope_combo.findData(scan_scope)
    if scope_idx < 0:
        scope_idx = 0
    self.backtest_scan_scope_combo.setCurrentIndex(scope_idx)
    self.backtest_scan_scope_combo.currentIndexChanged.connect(
        lambda idx: self._update_backtest_config(
            "scan_scope",
            self.backtest_scan_scope_combo.itemData(idx),
        )
    )
    optimizer_layout.addWidget(self.backtest_scan_scope_combo)

    optimizer_layout.addWidget(QtWidgets.QLabel("Mode:"))
    self.backtest_optimizer_mode_combo = QtWidgets.QComboBox()
    for label, value in backtest_optimizer_runtime.OPTIMIZER_MODE_OPTIONS:
        self.backtest_optimizer_mode_combo.addItem(label, value)
    optimizer_mode = backtest_optimizer_runtime.normalize_optimizer_mode(
        self.backtest_config.get("optimizer_mode", "current")
    )
    optimizer_mode_idx = self.backtest_optimizer_mode_combo.findData(optimizer_mode)
    if optimizer_mode_idx < 0:
        optimizer_mode_idx = 0
    self.backtest_optimizer_mode_combo.setCurrentIndex(optimizer_mode_idx)
    optimizer_layout.addWidget(self.backtest_optimizer_mode_combo)

    self.backtest_optimizer_combo_size_label = QtWidgets.QLabel("Max Combo:")
    optimizer_layout.addWidget(self.backtest_optimizer_combo_size_label)
    self.backtest_optimizer_combo_size_spin = QtWidgets.QSpinBox()
    self.backtest_optimizer_combo_size_spin.setRange(1, 5)
    optimizer_combo_size = int(self.backtest_config.get("optimizer_combo_size", 2) or 2)
    self.backtest_optimizer_combo_size_spin.setValue(max(1, min(5, optimizer_combo_size)))
    self.backtest_optimizer_combo_size_spin.valueChanged.connect(
        lambda v: self._update_backtest_config("optimizer_combo_size", int(v))
    )
    optimizer_layout.addWidget(self.backtest_optimizer_combo_size_spin)

    def _sync_optimizer_combo_size_enabled(idx: int) -> None:
        mode_value = backtest_optimizer_runtime.normalize_optimizer_mode(
            self.backtest_optimizer_mode_combo.itemData(idx)
        )
        self._update_backtest_config("optimizer_mode", mode_value)
        combo_enabled = mode_value == "combinations"
        self.backtest_optimizer_combo_size_label.setEnabled(combo_enabled)
        self.backtest_optimizer_combo_size_spin.setEnabled(combo_enabled)
        self.backtest_optimizer_combo_size_spin.setToolTip(
            "Used only when Mode is Combinations up to N."
        )

    self.backtest_optimizer_mode_combo.currentIndexChanged.connect(_sync_optimizer_combo_size_enabled)
    _sync_optimizer_combo_size_enabled(self.backtest_optimizer_mode_combo.currentIndex())
    optimizer_layout.addStretch()
    param_form.addRow("Optimizer:", optimizer_row)

    optimizer_metric_row = QtWidgets.QWidget()
    optimizer_metric_layout = QtWidgets.QHBoxLayout(optimizer_metric_row)
    optimizer_metric_layout.setContentsMargins(0, 0, 0, 0)
    optimizer_metric_layout.setSpacing(6)

    optimizer_metric_layout.addWidget(QtWidgets.QLabel("Optimize For:"))
    self.backtest_optimizer_metric_combo = QtWidgets.QComboBox()
    for label, value in backtest_optimizer_runtime.OPTIMIZER_METRIC_OPTIONS:
        self.backtest_optimizer_metric_combo.addItem(label, value)
    optimizer_metric = backtest_optimizer_runtime.normalize_optimizer_metric(
        self.backtest_config.get("optimizer_metric", "roi_percent")
    )
    optimizer_metric_idx = self.backtest_optimizer_metric_combo.findData(optimizer_metric)
    if optimizer_metric_idx < 0:
        optimizer_metric_idx = 0
    self.backtest_optimizer_metric_combo.setCurrentIndex(optimizer_metric_idx)
    self.backtest_optimizer_metric_combo.currentIndexChanged.connect(
        lambda idx: self._update_backtest_config(
            "optimizer_metric",
            self.backtest_optimizer_metric_combo.itemData(idx),
        )
    )
    optimizer_metric_layout.addWidget(self.backtest_optimizer_metric_combo)

    optimizer_metric_layout.addWidget(QtWidgets.QLabel("Min Trades:"))
    self.backtest_optimizer_min_trades_spin = QtWidgets.QSpinBox()
    self.backtest_optimizer_min_trades_spin.setRange(0, 1_000_000)
    optimizer_min_trades = int(self.backtest_config.get("optimizer_min_trades", 1) or 1)
    self.backtest_optimizer_min_trades_spin.setValue(max(0, optimizer_min_trades))
    self.backtest_optimizer_min_trades_spin.valueChanged.connect(
        lambda v: self._update_backtest_config("optimizer_min_trades", int(v))
    )
    optimizer_metric_layout.addWidget(self.backtest_optimizer_min_trades_spin)
    optimizer_metric_layout.addWidget(QtWidgets.QLabel("Max Time:"))
    self.backtest_optimizer_max_duration_spin = QtWidgets.QSpinBox()
    self.backtest_optimizer_max_duration_spin.setRange(1, 10_080)
    self.backtest_optimizer_max_duration_spin.setSuffix(" min")
    duration_seconds = int(self.backtest_config.get("optimizer_max_duration_seconds", 14_400) or 14_400)
    self.backtest_optimizer_max_duration_spin.setValue(max(1, min(10_080, round(duration_seconds / 60))))
    self.backtest_optimizer_max_duration_spin.setToolTip(
        "Applies to optimizer runs. When the budget is reached, completed ranked results remain available."
    )
    self.backtest_optimizer_max_duration_spin.valueChanged.connect(
        lambda v: self._update_backtest_config("optimizer_max_duration_seconds", int(v) * 60)
    )
    optimizer_metric_layout.addWidget(self.backtest_optimizer_max_duration_spin)
    optimizer_metric_layout.addStretch()
    param_form.addRow("Leaderboard:", optimizer_metric_row)

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
    scan_layout.addWidget(QtWidgets.QLabel("Max MDD % (0=off):"))
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
    self.backtest_scan_btn = QtWidgets.QPushButton("Run Optimizer")
    self.backtest_scan_btn.clicked.connect(self._run_backtest_scan)
    scan_layout.addWidget(self.backtest_scan_btn)
    scan_layout.addStretch()
    param_form.addRow("Scanner Limits:", scan_row)

    self.backtest_optimizer_estimate_label = QtWidgets.QLabel()
    self.backtest_optimizer_estimate_label.setWordWrap(True)
    self.backtest_optimizer_estimate_label.setTextInteractionFlags(
        QtCore.Qt.TextInteractionFlag.TextSelectableByMouse
    )
    param_form.addRow("Estimate:", self.backtest_optimizer_estimate_label)

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
    try:
        self._refresh_backtest_optimizer_estimate()
    except Exception:
        refresh_backtest_optimizer_estimate(self)
    return param_group


__all__ = ["build_backtest_params_group", "refresh_backtest_optimizer_estimate"]
