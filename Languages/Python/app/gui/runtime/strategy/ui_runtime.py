from __future__ import annotations

from . import ui_controls_runtime, ui_dashboard_runtime, ui_shared_runtime

_register_runtime_active_exemption = ui_shared_runtime._register_runtime_active_exemption
_loop_choice_value = ui_shared_runtime._loop_choice_value
_set_loop_combo_value = ui_shared_runtime._set_loop_combo_value
_normalize_loop_override = ui_shared_runtime._normalize_loop_override

_on_dashboard_template_changed = ui_dashboard_runtime._on_dashboard_template_changed

_on_runtime_loop_changed = ui_controls_runtime._on_runtime_loop_changed
_on_allow_opposite_changed = ui_controls_runtime._on_allow_opposite_changed
_on_backtest_loop_changed = ui_controls_runtime._on_backtest_loop_changed
_on_runtime_account_mode_changed = ui_controls_runtime._on_runtime_account_mode_changed
_on_backtest_account_mode_changed = ui_controls_runtime._on_backtest_account_mode_changed
_apply_runtime_account_mode_constraints = ui_controls_runtime._apply_runtime_account_mode_constraints
_apply_backtest_account_mode_constraints = ui_controls_runtime._apply_backtest_account_mode_constraints
_enforce_portfolio_margin_constraints = ui_controls_runtime._enforce_portfolio_margin_constraints
_on_lead_trader_toggled = ui_controls_runtime._on_lead_trader_toggled
_on_lead_trader_option_changed = ui_controls_runtime._on_lead_trader_option_changed
_apply_lead_trader_state = ui_controls_runtime._apply_lead_trader_state


def bind_main_window_strategy_ui_runtime(
    main_window_cls,
    *,
    account_mode_options=None,
    stop_loss_scope_options=None,
) -> None:
    ui_shared_runtime.configure_main_window_strategy_ui_shared_runtime(
        account_mode_options=account_mode_options,
        stop_loss_scope_options=stop_loss_scope_options,
    )

    main_window_cls._register_runtime_active_exemption = _register_runtime_active_exemption
    main_window_cls._loop_choice_value = _loop_choice_value
    main_window_cls._set_loop_combo_value = _set_loop_combo_value
    main_window_cls._on_dashboard_template_changed = _on_dashboard_template_changed
    main_window_cls._on_runtime_loop_changed = _on_runtime_loop_changed
    main_window_cls._on_allow_opposite_changed = _on_allow_opposite_changed
    main_window_cls._on_backtest_loop_changed = _on_backtest_loop_changed
    main_window_cls._on_runtime_account_mode_changed = _on_runtime_account_mode_changed
    main_window_cls._on_backtest_account_mode_changed = _on_backtest_account_mode_changed
    main_window_cls._apply_runtime_account_mode_constraints = _apply_runtime_account_mode_constraints
    main_window_cls._apply_backtest_account_mode_constraints = _apply_backtest_account_mode_constraints
    main_window_cls._enforce_portfolio_margin_constraints = _enforce_portfolio_margin_constraints
    main_window_cls._on_lead_trader_toggled = _on_lead_trader_toggled
    main_window_cls._on_lead_trader_option_changed = _on_lead_trader_option_changed
    main_window_cls._apply_lead_trader_state = _apply_lead_trader_state
    main_window_cls._normalize_loop_override = staticmethod(_normalize_loop_override)
