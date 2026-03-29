from __future__ import annotations

from .binding_modules import _load_binding_modules
from .binding_sections import (
    _bind_bootstrap_backtest_and_chart_runtime,
    _bind_dashboard_runtime,
    _bind_runtime_control_and_service_helpers,
    _bind_trade_positions_and_tail_runtime,
    _bind_window_and_chart_core,
)


def bind_main_window_class(main_window_cls, *, module_globals) -> None:
    modules = _load_binding_modules()
    g = module_globals

    _bind_window_and_chart_core(main_window_cls, g, modules)
    _bind_dashboard_runtime(main_window_cls, g, modules)
    _bind_bootstrap_backtest_and_chart_runtime(main_window_cls, g, modules)
    _bind_runtime_control_and_service_helpers(main_window_cls, g, modules)
    _bind_trade_positions_and_tail_runtime(main_window_cls, g, modules)
