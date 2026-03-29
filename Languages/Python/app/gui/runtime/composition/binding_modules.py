from __future__ import annotations

from types import SimpleNamespace


def _load_binding_modules() -> SimpleNamespace:
    from app.desktop import create_desktop_service_client
    from app.desktop import service_bridge as desktop_service_bridge
    from app.gui.backtest import (
        bridge_runtime as main_window_backtest_bridge_runtime,
        execution_runtime as main_window_backtest_execution_runtime,
        results_runtime as main_window_backtest_results_runtime,
        state_runtime as main_window_backtest_state_runtime,
        tab_runtime as main_window_backtest_tab,
        template_runtime as main_window_backtest_template_runtime,
    )
    from app.gui.chart import (
        display_runtime as main_window_chart_display_runtime,
        host_runtime as main_window_chart_host_runtime,
        selection_runtime as main_window_chart_selection_runtime,
        tab_runtime as main_window_chart_tab,
        view_runtime as main_window_chart_view_runtime,
    )
    from app.gui.code import runtime as main_window_code_runtime, tab_runtime as main_window_code
    from app.gui.dashboard import (
        actions_runtime as main_window_dashboard_actions_runtime,
        chart_runtime as main_window_dashboard_chart_runtime,
        header_runtime as main_window_dashboard_header_runtime,
        indicator_runtime as main_window_dashboard_indicator_runtime,
        log_runtime as main_window_dashboard_log_runtime,
        markets_runtime as main_window_dashboard_markets_runtime,
        state_runtime as main_window_dashboard_state_runtime,
        strategy_runtime as main_window_dashboard_strategy_runtime,
    )
    from app.gui.positions import positions_runtime as main_window_positions, tab_runtime as main_window_positions_tab
    from app.gui.runtime.account import (
        account_runtime as main_window_account_runtime,
        balance_runtime as main_window_balance_runtime,
        margin_runtime as main_window_margin_runtime,
    )
    from app.gui.runtime.service import (
        service_api_runtime as main_window_service_api_runtime,
        session_runtime as main_window_session_runtime,
        status_runtime as main_window_status_runtime,
    )
    from app.gui.runtime.strategy import (
        context_runtime,
        control_runtime,
        controls_runtime,
        indicator_runtime,
        override_runtime,
        stop_loss_runtime,
        ui_runtime,
    )
    from app.gui.runtime.ui import (
        secondary_tabs_runtime as main_window_secondary_tabs_runtime,
        tab_runtime as main_window_tab_runtime,
        theme_runtime as main_window_theme_runtime,
        ui_misc_runtime as main_window_ui_misc_runtime,
    )
    from app.gui.runtime.window import (
        bootstrap_runtime as main_window_bootstrap_runtime,
        init_finalize_runtime as main_window_init_finalize_runtime,
        runtime as main_window_runtime,
    )
    from app.gui.shared import config_runtime as main_window_config
    from app.gui.trade import trade_runtime as main_window_trade_runtime

    return SimpleNamespace(
        desktop=SimpleNamespace(
            create_desktop_service_client=create_desktop_service_client,
            desktop_service_bridge=desktop_service_bridge,
        ),
        backtest=SimpleNamespace(
            main_window_backtest_bridge_runtime=main_window_backtest_bridge_runtime,
            main_window_backtest_execution_runtime=main_window_backtest_execution_runtime,
            main_window_backtest_results_runtime=main_window_backtest_results_runtime,
            main_window_backtest_state_runtime=main_window_backtest_state_runtime,
            main_window_backtest_tab=main_window_backtest_tab,
            main_window_backtest_template_runtime=main_window_backtest_template_runtime,
        ),
        chart=SimpleNamespace(
            main_window_chart_display_runtime=main_window_chart_display_runtime,
            main_window_chart_host_runtime=main_window_chart_host_runtime,
            main_window_chart_selection_runtime=main_window_chart_selection_runtime,
            main_window_chart_tab=main_window_chart_tab,
            main_window_chart_view_runtime=main_window_chart_view_runtime,
        ),
        code=SimpleNamespace(
            main_window_code=main_window_code,
            main_window_code_runtime=main_window_code_runtime,
        ),
        dashboard=SimpleNamespace(
            main_window_dashboard_actions_runtime=main_window_dashboard_actions_runtime,
            main_window_dashboard_chart_runtime=main_window_dashboard_chart_runtime,
            main_window_dashboard_header_runtime=main_window_dashboard_header_runtime,
            main_window_dashboard_indicator_runtime=main_window_dashboard_indicator_runtime,
            main_window_dashboard_log_runtime=main_window_dashboard_log_runtime,
            main_window_dashboard_markets_runtime=main_window_dashboard_markets_runtime,
            main_window_dashboard_state_runtime=main_window_dashboard_state_runtime,
            main_window_dashboard_strategy_runtime=main_window_dashboard_strategy_runtime,
        ),
        positions=SimpleNamespace(
            main_window_positions=main_window_positions,
            main_window_positions_tab=main_window_positions_tab,
        ),
        runtime=SimpleNamespace(
            account=SimpleNamespace(
                main_window_account_runtime=main_window_account_runtime,
                main_window_balance_runtime=main_window_balance_runtime,
                main_window_margin_runtime=main_window_margin_runtime,
            ),
            service=SimpleNamespace(
                main_window_service_api_runtime=main_window_service_api_runtime,
                main_window_session_runtime=main_window_session_runtime,
                main_window_status_runtime=main_window_status_runtime,
            ),
            strategy=SimpleNamespace(
                main_window_control_runtime=control_runtime,
                main_window_indicator_runtime=indicator_runtime,
                main_window_override_runtime=override_runtime,
                main_window_stop_loss_runtime=stop_loss_runtime,
                main_window_strategy_context_runtime=context_runtime,
                main_window_strategy_controls_runtime=controls_runtime,
                main_window_strategy_ui_runtime=ui_runtime,
            ),
            ui=SimpleNamespace(
                main_window_secondary_tabs_runtime=main_window_secondary_tabs_runtime,
                main_window_tab_runtime=main_window_tab_runtime,
                main_window_theme_runtime=main_window_theme_runtime,
                main_window_ui_misc_runtime=main_window_ui_misc_runtime,
            ),
            window=SimpleNamespace(
                main_window_bootstrap_runtime=main_window_bootstrap_runtime,
                main_window_init_finalize_runtime=main_window_init_finalize_runtime,
                main_window_runtime=main_window_runtime,
            ),
        ),
        shared=SimpleNamespace(main_window_config=main_window_config),
        trade=SimpleNamespace(main_window_trade_runtime=main_window_trade_runtime),
    )
