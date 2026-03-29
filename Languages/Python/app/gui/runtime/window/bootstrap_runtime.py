from __future__ import annotations

from . import portfolio_runtime as main_window_portfolio_runtime, state_init_runtime as main_window_state_init_runtime

_initialize_main_window_state = main_window_state_init_runtime._initialize_main_window_state
_resolve_app_state_load_path = main_window_state_init_runtime._resolve_app_state_load_path
_initialize_config_state = main_window_state_init_runtime._initialize_config_state
_initialize_chart_state = main_window_state_init_runtime._initialize_chart_state
_initialize_backtest_state = main_window_state_init_runtime._initialize_backtest_state
_initialize_runtime_state = main_window_state_init_runtime._initialize_runtime_state

_update_positions_balance_labels = main_window_portfolio_runtime._update_positions_balance_labels
_compute_global_pnl_totals = main_window_portfolio_runtime._compute_global_pnl_totals


def bind_main_window_bootstrap_runtime(
    main_window_cls,
    *,
    app_state_path,
    legacy_app_state_path=None,
    load_app_state_file,
    normalize_connector_backend,
    default_connector_backend,
    chart_market_options,
    disable_tradingview,
    disable_charts,
    enable_chart_tab,
    tradingview_supported,
) -> None:
    main_window_state_init_runtime.configure_main_window_state_init_runtime(
        app_state_path=app_state_path,
        legacy_app_state_path=legacy_app_state_path,
        load_app_state_file=load_app_state_file,
        normalize_connector_backend=normalize_connector_backend,
        default_connector_backend=default_connector_backend,
        chart_market_options=chart_market_options,
        disable_tradingview=disable_tradingview,
        disable_charts=disable_charts,
        enable_chart_tab=enable_chart_tab,
        tradingview_supported=tradingview_supported,
    )

    main_window_cls._initialize_main_window_state = _initialize_main_window_state
    main_window_cls._update_positions_balance_labels = _update_positions_balance_labels
    main_window_cls._compute_global_pnl_totals = _compute_global_pnl_totals
