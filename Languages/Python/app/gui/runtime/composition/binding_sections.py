from __future__ import annotations

from types import SimpleNamespace


def _bind_window_and_chart_core(main_window_cls, g, modules: SimpleNamespace) -> None:
    window = modules.runtime.window
    account = modules.runtime.account
    chart = modules.chart
    ui = modules.runtime.ui

    window.main_window_runtime.bind_main_window_runtime(
        main_window_cls,
        strategy_engine_cls=g["StrategyEngine"],
        numeric_item_cls=g["_NumericItem"],
        waiting_position_late_threshold=g["WAITING_POSITION_LATE_THRESHOLD"],
    )
    account.main_window_account_runtime.bind_main_window_account_runtime(
        main_window_cls,
        connector_options=g["CONNECTOR_OPTIONS"],
        default_connector_backend=g["DEFAULT_CONNECTOR_BACKEND"],
        futures_connector_keys=g["FUTURES_CONNECTOR_KEYS"],
        spot_connector_keys=g["SPOT_CONNECTOR_KEYS"],
        side_labels=g["SIDE_LABELS"],
        normalize_connector_backend=g["_normalize_connector_backend"],
        recommended_connector_for_key=g["_recommended_connector_for_key"],
        refresh_dependency_usage_labels=g["_refresh_dependency_usage_labels"],
    )
    chart.main_window_chart_view_runtime.bind_main_window_chart_view_runtime(
        main_window_cls,
        chart_interval_options=g["CHART_INTERVAL_OPTIONS"],
        chart_market_options=g["CHART_MARKET_OPTIONS"],
    )
    chart.main_window_chart_host_runtime.bind_main_window_chart_host_runtime(main_window_cls)
    chart.main_window_chart_tab.bind_main_window_chart_tab(
        main_window_cls,
        chart_market_options=g["CHART_MARKET_OPTIONS"],
        chart_interval_options=g["CHART_INTERVAL_OPTIONS"],
        disable_tradingview=g["_DISABLE_TRADINGVIEW"],
        disable_charts=g["_DISABLE_CHARTS"],
        qt_charts_available=g["QT_CHARTS_AVAILABLE"],
    )
    ui.main_window_tab_runtime.bind_main_window_tab_runtime(
        main_window_cls,
        cpp_code_language_key=g["CPP_CODE_LANGUAGE_KEY"],
    )


def _bind_dashboard_runtime(main_window_cls, g, modules: SimpleNamespace) -> None:
    dashboard = modules.dashboard

    dashboard.main_window_dashboard_log_runtime.bind_main_window_dashboard_log_runtime(main_window_cls)
    dashboard.main_window_dashboard_markets_runtime.bind_main_window_dashboard_markets_runtime(
        main_window_cls,
        starter_crypto_exchanges=g["STARTER_CRYPTO_EXCHANGES"],
        exchange_paths=g["EXCHANGE_PATHS"],
        chart_interval_options=g["CHART_INTERVAL_OPTIONS"],
        binance_supported_intervals=g["BINANCE_SUPPORTED_INTERVALS"],
    )
    dashboard.main_window_dashboard_state_runtime.bind_main_window_dashboard_state_runtime(
        main_window_cls,
        load_position_allocations=g["_load_position_allocations"],
    )
    dashboard.main_window_dashboard_strategy_runtime.bind_main_window_dashboard_strategy_runtime(
        main_window_cls,
        side_labels=g["SIDE_LABELS"],
        dashboard_loop_choices=g["DASHBOARD_LOOP_CHOICES"],
        lead_trader_options=g["LEAD_TRADER_OPTIONS"],
        stop_loss_mode_order=g["STOP_LOSS_MODE_ORDER"],
        stop_loss_mode_labels=g["STOP_LOSS_MODE_LABELS"],
        stop_loss_scope_options=g["STOP_LOSS_SCOPE_OPTIONS"],
        stop_loss_scope_labels=g["STOP_LOSS_SCOPE_LABELS"],
        coerce_bool=g["coerce_bool"],
        normalize_stop_loss_dict=g["normalize_stop_loss_dict"],
    )
    dashboard.main_window_dashboard_indicator_runtime.bind_main_window_dashboard_indicator_runtime(
        main_window_cls,
        indicator_display_names=g["INDICATOR_DISPLAY_NAMES"],
        param_dialog_cls=g["ParamDialog"],
    )
    dashboard.main_window_dashboard_actions_runtime.bind_main_window_dashboard_actions_runtime(main_window_cls)
    dashboard.main_window_dashboard_chart_runtime.bind_main_window_dashboard_chart_runtime(
        main_window_cls,
        qt_charts_available=g["QT_CHARTS_AVAILABLE"],
    )
    dashboard.main_window_dashboard_header_runtime.bind_main_window_dashboard_header_runtime(
        main_window_cls,
        account_mode_options=g["ACCOUNT_MODE_OPTIONS"],
        connector_options=g["CONNECTOR_OPTIONS"],
        futures_connector_keys=g["FUTURES_CONNECTOR_KEYS"],
        spot_connector_keys=g["SPOT_CONNECTOR_KEYS"],
    )


def _bind_bootstrap_backtest_and_chart_runtime(main_window_cls, g, modules: SimpleNamespace) -> None:
    window = modules.runtime.window
    ui = modules.runtime.ui
    positions = modules.positions
    backtest = modules.backtest
    chart = modules.chart

    window.main_window_bootstrap_runtime.bind_main_window_bootstrap_runtime(
        main_window_cls,
        app_state_path=g["APP_STATE_PATH"],
        legacy_app_state_path=g["LEGACY_APP_STATE_PATH"],
        load_app_state_file=g["_load_app_state_file"],
        normalize_connector_backend=g["_normalize_connector_backend"],
        default_connector_backend=g["DEFAULT_CONNECTOR_BACKEND"],
        chart_market_options=g["CHART_MARKET_OPTIONS"],
        disable_tradingview=g["_DISABLE_TRADINGVIEW"],
        disable_charts=g["_DISABLE_CHARTS"],
        enable_chart_tab=g["ENABLE_CHART_TAB"],
        tradingview_supported=g["_tradingview_supported"],
    )
    window.main_window_init_finalize_runtime.bind_main_window_init_finalize_runtime(main_window_cls)
    ui.main_window_secondary_tabs_runtime.bind_main_window_secondary_tabs_runtime(main_window_cls)
    positions.main_window_positions_tab.bind_main_window_positions_tab(
        main_window_cls,
        coerce_bool=g["coerce_bool"],
        pos_close_column=g["POS_CLOSE_COLUMN"],
        positions_worker_cls=g["_PositionsWorker"],
    )
    backtest.main_window_backtest_tab.bind_main_window_backtest_tab(
        main_window_cls,
        mdd_logic_options=g["MDD_LOGIC_OPTIONS"],
        mdd_logic_labels=g["MDD_LOGIC_LABELS"],
        mdd_logic_default=g["MDD_LOGIC_DEFAULT"],
        dashboard_loop_choices=g["DASHBOARD_LOOP_CHOICES"],
        stop_loss_mode_order=g["STOP_LOSS_MODE_ORDER"],
        stop_loss_scope_options=g["STOP_LOSS_SCOPE_OPTIONS"],
        stop_loss_mode_labels=g["STOP_LOSS_MODE_LABELS"],
        stop_loss_scope_labels=g["STOP_LOSS_SCOPE_LABELS"],
        side_labels=g["SIDE_LABELS"],
        account_mode_options=g["ACCOUNT_MODE_OPTIONS"],
        backtest_template_definitions=g["BACKTEST_TEMPLATE_DEFINITIONS"],
        backtest_template_default=g["BACKTEST_TEMPLATE_DEFAULT"],
        indicator_display_names=g["INDICATOR_DISPLAY_NAMES"],
        symbol_fetch_top_n=g["_SYMBOL_FETCH_TOP_N"],
        normalize_stop_loss_dict=g["normalize_stop_loss_dict"],
    )
    backtest.main_window_backtest_state_runtime.bind_main_window_backtest_state_runtime(
        main_window_cls,
        backtest_interval_order=g["BACKTEST_INTERVAL_ORDER"],
        side_labels=g["SIDE_LABELS"],
        symbol_fetch_top_n=g["_SYMBOL_FETCH_TOP_N"],
    )
    backtest.main_window_backtest_template_runtime.bind_main_window_backtest_template_runtime(
        main_window_cls,
        mdd_logic_options=g["MDD_LOGIC_OPTIONS"],
        mdd_logic_default=g["MDD_LOGIC_DEFAULT"],
        backtest_template_definitions=g["BACKTEST_TEMPLATE_DEFINITIONS"],
        backtest_template_default=g["BACKTEST_TEMPLATE_DEFAULT"],
        indicator_display_names=g["INDICATOR_DISPLAY_NAMES"],
        side_labels=g["SIDE_LABELS"],
        normalize_connector_backend=g["_normalize_connector_backend"],
        param_dialog_cls=g["ParamDialog"],
    )
    backtest.main_window_backtest_execution_runtime.bind_main_window_backtest_execution_runtime(
        main_window_cls,
        dbg_backtest_run=g["_DBG_BACKTEST_RUN"],
        symbol_fetch_top_n=g["_SYMBOL_FETCH_TOP_N"],
        normalize_stop_loss_dict=g["normalize_stop_loss_dict"],
        backtest_worker_cls=g["_BacktestWorker"],
    )
    chart.main_window_chart_selection_runtime.bind_main_window_chart_selection_runtime(
        main_window_cls,
        default_chart_symbols=g["DEFAULT_CHART_SYMBOLS"],
        symbol_fetch_top_n=g["_SYMBOL_FETCH_TOP_N"],
        tradingview_symbol_prefix=g["TRADINGVIEW_SYMBOL_PREFIX"],
        tradingview_interval_map=g["TRADINGVIEW_INTERVAL_MAP"],
    )
    chart.main_window_chart_display_runtime.bind_main_window_chart_display_runtime(main_window_cls)


def _bind_runtime_control_and_service_helpers(main_window_cls, g, modules: SimpleNamespace) -> None:
    account = modules.runtime.account
    service = modules.runtime.service
    strategy = modules.runtime.strategy
    ui = modules.runtime.ui

    strategy.main_window_control_runtime.bind_main_window_control_runtime(
        main_window_cls,
        strategy_engine_cls=g["StrategyEngine"],
        make_engine_key=g["_make_engine_key"],
        coerce_bool=g["coerce_bool"],
        normalize_stop_loss_dict=g["normalize_stop_loss_dict"],
        format_indicator_list=g["_format_indicator_list"],
        symbol_fetch_top_n=g["_SYMBOL_FETCH_TOP_N"],
    )
    account.main_window_balance_runtime.bind_main_window_balance_runtime(
        main_window_cls,
        normalize_connector_backend=g["_normalize_connector_backend"],
    )
    service.main_window_session_runtime.bind_main_window_session_runtime(
        main_window_cls,
        default_connector_backend=g["DEFAULT_CONNECTOR_BACKEND"],
        normalize_connector_backend=g["_normalize_connector_backend"],
        save_app_state_file=g["_save_app_state_file"],
    )
    strategy.main_window_strategy_ui_runtime.bind_main_window_strategy_ui_runtime(
        main_window_cls,
        account_mode_options=g["ACCOUNT_MODE_OPTIONS"],
        stop_loss_scope_options=g["STOP_LOSS_SCOPE_OPTIONS"],
    )
    service.main_window_service_api_runtime.bind_main_window_service_api_runtime(
        main_window_cls,
        save_app_state_file=g["_save_app_state_file"],
    )
    ui.main_window_ui_misc_runtime.bind_main_window_ui_misc_runtime(main_window_cls)
    strategy.main_window_override_runtime.bind_main_window_override_runtime(
        main_window_cls,
        format_indicator_list=g["_format_indicator_list"],
        normalize_connector_backend=g["_normalize_connector_backend"],
        normalize_indicator_values=g["_normalize_indicator_values"],
        normalize_stop_loss_dict=g["normalize_stop_loss_dict"],
    )
    service.main_window_status_runtime.bind_main_window_status_runtime(main_window_cls)
    strategy.main_window_stop_loss_runtime.bind_main_window_stop_loss_runtime(
        main_window_cls,
        normalize_stop_loss_dict=g["normalize_stop_loss_dict"],
        stop_loss_mode_order=g["STOP_LOSS_MODE_ORDER"],
        stop_loss_scope_options=g["STOP_LOSS_SCOPE_OPTIONS"],
    )
    strategy.main_window_strategy_controls_runtime.bind_main_window_strategy_controls_runtime(
        main_window_cls,
        side_labels=g["SIDE_LABELS"],
        normalize_stop_loss_dict=g["normalize_stop_loss_dict"],
        normalize_connector_backend=g["_normalize_connector_backend"],
    )
    strategy.main_window_indicator_runtime.bind_main_window_indicator_runtime(
        canonicalize_indicator_key=g["_canonicalize_indicator_key"],
        normalize_connector_backend=g["_normalize_connector_backend"],
        normalize_indicator_token=g["_normalize_indicator_token"],
        normalize_indicator_values=g["_normalize_indicator_values"],
        resolve_trigger_indicators=g["_resolve_trigger_indicators"],
    )
    strategy.main_window_strategy_context_runtime.bind_main_window_strategy_context_runtime(
        main_window_cls,
        side_label_lookup=g["SIDE_LABEL_LOOKUP"],
        binance_interval_lower=g["BINANCE_INTERVAL_LOWER"],
    )


def _bind_trade_positions_and_tail_runtime(main_window_cls, g, modules: SimpleNamespace) -> None:
    account = modules.runtime.account
    strategy = modules.runtime.strategy
    ui = modules.runtime.ui
    trade = modules.trade
    positions = modules.positions
    backtest = modules.backtest
    shared = modules.shared
    code = modules.code
    desktop = modules.desktop

    trade.main_window_trade_runtime.bind_main_window_trade_runtime(
        main_window_cls,
        resolve_trigger_indicators=g["_resolve_trigger_indicators"],
        save_position_allocations=g["_save_position_allocations"],
        normalize_trigger_actions_map=strategy.main_window_indicator_runtime._normalize_trigger_actions_map,
        max_closed_history=g["MAX_CLOSED_HISTORY"],
    )
    positions.main_window_positions.bind_main_window_positions(
        main_window_cls,
        resolve_trigger_indicators=g["_resolve_trigger_indicators"],
        max_closed_history=g["MAX_CLOSED_HISTORY"],
        stop_strategy_sync=strategy.main_window_control_runtime._stop_strategy_sync,
        pos_status_column=g["POS_STATUS_COLUMN"],
        save_position_allocations=g["_save_position_allocations"],
        normalize_indicator_values=g["_normalize_indicator_values"],
        derive_margin_snapshot=account.main_window_margin_runtime._derive_margin_snapshot,
        coerce_bool=g["coerce_bool"],
        format_indicator_list=g["_format_indicator_list"],
        collect_record_indicator_keys=strategy.main_window_indicator_runtime._collect_record_indicator_keys,
        collect_indicator_value_strings=strategy.main_window_indicator_runtime._collect_indicator_value_strings,
        collect_current_indicator_live_strings=strategy.main_window_indicator_runtime._collect_current_indicator_live_strings,
        dedupe_indicator_entries_normalized=strategy.main_window_indicator_runtime._dedupe_indicator_entries_normalized,
        numeric_item_cls=g["_NumericItem"],
        pos_triggered_value_column=g["POS_TRIGGERED_VALUE_COLUMN"],
        pos_current_value_column=g["POS_CURRENT_VALUE_COLUMN"],
        pos_stop_loss_column=g["POS_STOP_LOSS_COLUMN"],
        pos_close_column=g["POS_CLOSE_COLUMN"],
    )
    backtest.main_window_backtest_results_runtime.bind_main_window_backtest_results_runtime(
        main_window_cls,
        mdd_logic_labels=g["MDD_LOGIC_LABELS"],
        normalize_loop_override=main_window_cls._normalize_loop_override,
    )
    backtest.main_window_backtest_bridge_runtime.bind_main_window_backtest_bridge_runtime(
        main_window_cls,
        dbg_backtest_dashboard=g["_DBG_BACKTEST_DASHBOARD"],
        normalize_indicator_values=g["_normalize_indicator_values"],
        normalize_stop_loss_dict=g["normalize_stop_loss_dict"],
    )
    shared.main_window_config.bind_main_window_config(
        main_window_cls,
        normalize_stop_loss_dict=g["normalize_stop_loss_dict"],
        qt_charts_available=g["QT_CHARTS_AVAILABLE"],
        tradingview_supported=g["_tradingview_supported"],
        language_paths=g["LANGUAGE_PATHS"],
        exchange_paths=g["EXCHANGE_PATHS"],
        forex_broker_paths=g["FOREX_BROKER_PATHS"],
        lead_trader_options=g["LEAD_TRADER_OPTIONS"],
    )
    code.main_window_code_runtime.bind_main_window_code_runtime(main_window_cls)
    code.main_window_code.bind_main_window_code(
        main_window_cls,
        lazy_web_embed_cls=g["_LazyWebEmbed"],
        starter_card_cls=g["_StarterCard"],
        resolve_dependency_targets_for_config=g["_resolve_dependency_targets_for_config"],
        launch_cpp_from_code_tab=code.main_window_code_runtime._launch_cpp_from_code_tab,
        launch_rust_from_code_tab=code.main_window_code_runtime._launch_rust_from_code_tab,
        refresh_code_language_card_release_labels=code.main_window_code_runtime._refresh_code_language_card_release_labels,
        refresh_dependency_usage_labels=g["_refresh_dependency_usage_labels"],
        base_project_path=g["_BASE_PROJECT_PATH"],
    )
    ui.main_window_theme_runtime.bind_main_window_theme_runtime(main_window_cls)
    desktop.desktop_service_bridge.bind_main_window_desktop_service_bridge(
        main_window_cls,
        desktop_service_client_factory=desktop.create_desktop_service_client,
    )
