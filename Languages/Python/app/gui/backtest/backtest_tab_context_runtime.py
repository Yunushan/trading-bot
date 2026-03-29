from __future__ import annotations

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


def configure_backtest_tab_context(
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
) -> None:
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


__all__ = ["configure_backtest_tab_context"]
