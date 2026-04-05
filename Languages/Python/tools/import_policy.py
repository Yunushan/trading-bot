"""
Canonical import and compatibility-wrapper policy for the Python workspace.

This registry keeps the current migration boundary explicit while compatibility
modules remain in the tree. New production code should import canonical modules
only; the legacy wrappers stay in place solely to avoid breaking older callers
during the staged cleanup.
"""

from __future__ import annotations

from typing import Final


CANONICAL_IMPORT_GUIDANCE: Final[dict[str, str]] = {
    "bootstrap/runtime metadata": "app.bootstrap.runtime_env",
    "GUI worker helpers": "app.gui.runtime.background_workers or app.gui.runtime.strategy_workers",
    "Binance futures close-all helpers": "app.integrations.exchanges.binance.positions.close_all_runtime",
    "backtest domain helpers": "trading_core.backtest",
    "indicator helpers": "trading_core.indicators",
    "position guard helpers": "trading_core.positions",
    "strategy engine": "trading_core.strategy",
    "flat Binance adapter": "app.integrations.exchanges.binance",
    "legacy main window wrapper": "app.gui.window_shell",
    "chart GUI wrappers": "app.gui.chart.* short runtime module names",
    "backtest GUI wrappers": "app.gui.backtest.* short runtime module names",
    "dashboard GUI wrappers": "app.gui.dashboard.* short runtime module names",
    "positions GUI wrappers": "app.gui.positions.* short runtime module names",
    "strategy GUI wrappers": "app.gui.runtime.strategy.* short runtime module names",
}

DEPRECATED_COMPAT_IMPORTS: Final[dict[str, str]] = {
    "app.backtester": "trading_core.backtest",
    "app.binance_wrapper": "app.integrations.exchanges.binance",
    "app.close_all": "app.integrations.exchanges.binance.positions.close_all_runtime",
    "app.gui.main_window": "app.gui.window_shell",
    "app.indicators": "trading_core.indicators",
    "app.position_guard": "trading_core.positions",
    "app.preamble": "app.bootstrap.runtime_env",
    "app.strategy": "trading_core.strategy",
    "app.strategy_cycle_runtime": "app.core.strategy.runtime.strategy_cycle_runtime",
    "app.strategy_indicator_compute": "app.core.strategy.runtime.strategy_indicator_compute",
    "app.strategy_indicator_guard": "app.core.strategy.positions.strategy_indicator_guard",
    "app.strategy_indicator_tracking": "app.core.strategy.runtime.strategy_indicator_tracking",
    "app.strategy_position_close_runtime": "app.core.strategy.positions.strategy_position_close_runtime",
    "app.strategy_position_flip_runtime": "app.core.strategy.positions.strategy_position_flip_runtime",
    "app.strategy_position_state": "app.core.strategy.positions.strategy_position_state",
    "app.strategy_runtime": "app.core.strategy.runtime.strategy_runtime",
    "app.strategy_runtime_support": "app.core.strategy.runtime.strategy_runtime_support",
    "app.strategy_signal_generation": "app.core.strategy.runtime.strategy_signal_generation",
    "app.strategy_signal_orders_runtime": "app.core.strategy.orders.strategy_signal_orders_runtime",
    "app.strategy_signal_order_collect_runtime": "app.core.strategy.orders.strategy_signal_order_collect_runtime",
    "app.strategy_signal_order_execute_runtime": "app.core.strategy.orders.strategy_signal_order_execute_runtime",
    "app.strategy_signal_order_guard_runtime": "app.core.strategy.orders.strategy_signal_order_guard_runtime",
    "app.strategy_signal_order_margin_runtime": "app.core.strategy.orders.strategy_signal_order_margin_runtime",
    "app.strategy_signal_order_position_gate_runtime": "app.core.strategy.orders.strategy_signal_order_position_gate_runtime",
    "app.strategy_signal_order_prepare_runtime": "app.core.strategy.orders.strategy_signal_order_prepare_runtime",
    "app.strategy_signal_order_result_runtime": "app.core.strategy.orders.strategy_signal_order_result_runtime",
    "app.strategy_signal_order_sizing_runtime": "app.core.strategy.orders.strategy_signal_order_sizing_runtime",
    "app.strategy_signal_order_slot_runtime": "app.core.strategy.orders.strategy_signal_order_slot_runtime",
    "app.strategy_signal_order_submit_runtime": "app.core.strategy.orders.strategy_signal_order_submit_runtime",
    "app.strategy_trade_book": "app.core.strategy.positions.strategy_trade_book",
    "app.workers": "app.gui.runtime.background_workers or app.gui.runtime.strategy_workers",
}

DEPRECATED_COMPAT_PREFIXES: Final[dict[str, str]] = {
    "app.gui.backtest.main_window_backtest_": (
        "app.gui.backtest.{bridge_runtime,execution_runtime,results_runtime,state_runtime,tab_runtime,"
        "template_runtime,worker_runtime}"
    ),
    "app.gui.chart.main_window_chart_": (
        "app.gui.chart.{display_runtime,host_runtime,selection_runtime,tab_runtime,view_runtime}"
    ),
    "app.gui.code.main_window_": "app.gui.code.{runtime,tab_runtime}",
    "app.gui.dashboard.main_window_dashboard_": (
        "app.gui.dashboard.{actions_runtime,chart_runtime,header_runtime,indicator_runtime,log_runtime,"
        "markets_runtime,state_runtime,strategy_runtime}"
    ),
    "app.gui.positions.main_window_positions": (
        "app.gui.positions.{positions_runtime,actions_runtime,history_runtime,history_records_runtime,"
        "history_update_runtime,record_build_runtime,render_runtime,tab_runtime,table_render_runtime,"
        "tracking_runtime,worker_runtime}"
    ),
    "app.gui.runtime.account.main_window_": "app.gui.runtime.account.{account_runtime,balance_runtime,margin_runtime}",
    "app.gui.runtime.composition.main_window_": "app.gui.runtime.composition.{bindings_runtime,module_state_runtime}",
    "app.gui.runtime.service.main_window_": "app.gui.runtime.service.{service_api_runtime,session_runtime,status_runtime}",
    "app.gui.runtime.strategy.main_window_": (
        "app.gui.runtime.strategy.{context_runtime,control_runtime,controls_runtime,indicator_runtime,"
        "override_runtime,start_runtime,stop_loss_runtime,stop_runtime,ui_runtime}"
    ),
    "app.gui.runtime.ui.main_window_": "app.gui.runtime.ui.{secondary_tabs_runtime,tab_runtime,theme_runtime,theme_styles,ui_misc_runtime}",
    "app.gui.runtime.window.main_window_": (
        "app.gui.runtime.window.{bootstrap_runtime,init_finalize_runtime,init_ui_runtime,log_runtime,"
        "portfolio_runtime,positions_runtime,runtime,startup_runtime,state_init_runtime,window_events_runtime}"
    ),
    "app.gui.shared.main_window_": "app.gui.shared.{config_runtime,helper_runtime,ui_support,web_embed}",
    "app.gui.trade.main_window_": "app.gui.trade.{trade_runtime,signal_runtime,signal_open_runtime}",
}

POLICY_SCAN_ROOTS: Final[tuple[str, ...]] = (
    "main.py",
    "app",
    "tools",
)


def replacement_for_legacy_import(target: str) -> str | None:
    if target in DEPRECATED_COMPAT_IMPORTS:
        return DEPRECATED_COMPAT_IMPORTS[target]
    for name, replacement in DEPRECATED_COMPAT_IMPORTS.items():
        if target.startswith(f"{name}."):
            return replacement
    for prefix, replacement in DEPRECATED_COMPAT_PREFIXES.items():
        if target.startswith(prefix):
            return replacement
    return None


def is_deprecated_import(target: str) -> bool:
    return replacement_for_legacy_import(target) is not None
