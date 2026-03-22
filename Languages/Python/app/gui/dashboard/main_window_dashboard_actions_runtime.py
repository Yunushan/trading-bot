from __future__ import annotations

from PyQt6 import QtWidgets


def _create_dashboard_action_section(self, scroll_layout):
    btn_layout = QtWidgets.QHBoxLayout()
    self.start_btn = QtWidgets.QPushButton("Start")
    self.start_btn.clicked.connect(self.start_strategy)
    btn_layout.addWidget(self.start_btn)
    self.stop_btn = QtWidgets.QPushButton("Stop")
    self.stop_btn.clicked.connect(
        lambda checked=False: self.stop_strategy_async(
            close_positions=not bool(self.cb_stop_without_close.isChecked())
        )
    )
    self.stop_btn.setEnabled(False)
    btn_layout.addWidget(self.stop_btn)
    self.save_btn = QtWidgets.QPushButton("Save Config")
    self.save_btn.clicked.connect(self.save_config)
    btn_layout.addWidget(self.save_btn)
    self.load_btn = QtWidgets.QPushButton("Load Config")
    self.load_btn.clicked.connect(self.load_config)
    btn_layout.addWidget(self.load_btn)
    scroll_layout.addLayout(btn_layout)

    self._runtime_lock_widgets = [
        self.api_key_edit,
        self.api_secret_edit,
        self.mode_combo,
        self.theme_combo,
        self.account_combo,
        self.account_mode_combo,
        self.connector_combo,
        self.leverage_spin,
        self.margin_mode_combo,
        self.position_mode_combo,
        self.assets_mode_combo,
        self.tif_combo,
        self.gtd_minutes_spin,
        self.ind_source_combo,
        self.symbol_list,
        self.refresh_symbols_btn,
        self.interval_list,
        self.custom_interval_edit,
        self.add_interval_btn,
        self.side_combo,
        self.pospct_spin,
        self.loop_combo,
        self.lead_trader_enable_cb,
        self.lead_trader_combo,
        self.cb_live_indicator_values,
        self.cb_add_only,
        self.allow_opposite_checkbox,
        self.cb_stop_without_close,
        self.cb_close_on_exit,
        self.stop_loss_enable_cb,
        self.stop_loss_mode_combo,
        self.stop_loss_usdt_spin,
        self.stop_loss_percent_spin,
        self.stop_loss_scope_combo,
        self.template_combo,
        self.start_btn,
        self.save_btn,
        self.load_btn,
    ] + list(self._indicator_runtime_controls)
    self._set_runtime_controls_enabled(True)


def bind_main_window_dashboard_actions_runtime(MainWindow):
    MainWindow._create_dashboard_action_section = _create_dashboard_action_section
