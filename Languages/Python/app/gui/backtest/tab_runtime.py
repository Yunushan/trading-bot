from __future__ import annotations

from PyQt6 import QtCore, QtWidgets

from . import (
    backtest_tab_context_runtime,
    backtest_tab_indicator_runtime,
    backtest_tab_market_runtime,
    backtest_tab_output_runtime,
    backtest_tab_params_runtime,
)


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
    top_layout.addWidget(backtest_tab_market_runtime.build_backtest_market_group(self), 3)
    top_layout.addWidget(backtest_tab_params_runtime.build_backtest_params_group(self), 5)
    top_layout.addWidget(backtest_tab_indicator_runtime.build_backtest_indicator_group(self), stretch=3)

    pending_template = getattr(self, "_backtest_template_pending_apply", None)
    if pending_template:
        self._apply_backtest_template(pending_template)
    self._backtest_template_pending_apply = None

    tab3_content_layout.addLayout(top_layout)
    tab3_content_layout.addWidget(backtest_tab_output_runtime.build_backtest_output_group(self))

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
    backtest_tab_context_runtime.configure_backtest_tab_context(
        mdd_logic_options=mdd_logic_options,
        mdd_logic_labels=mdd_logic_labels,
        mdd_logic_default=mdd_logic_default,
        dashboard_loop_choices=dashboard_loop_choices,
        stop_loss_mode_order=stop_loss_mode_order,
        stop_loss_scope_options=stop_loss_scope_options,
        stop_loss_mode_labels=stop_loss_mode_labels,
        stop_loss_scope_labels=stop_loss_scope_labels,
        side_labels=side_labels,
        account_mode_options=account_mode_options,
        backtest_template_definitions=backtest_template_definitions,
        backtest_template_default=backtest_template_default,
        indicator_display_names=indicator_display_names,
        symbol_fetch_top_n=symbol_fetch_top_n,
        normalize_stop_loss_dict=normalize_stop_loss_dict,
    )
    MainWindow._create_backtest_tab = _create_backtest_tab


__all__ = [
    "_create_backtest_tab",
    "bind_main_window_backtest_tab",
]
