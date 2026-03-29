from __future__ import annotations

from .strategy_cycle_risk_rsi_runtime import apply_rsi_exit_management
from .strategy_cycle_risk_stop_runtime import apply_futures_cycle_risk_management


def _apply_cycle_risk_management(
    self,
    *,
    ctx,
    cw,
    df,
    account_type: str,
    allow_opposite_enabled: bool,
    dual_side: bool,
    desired_ps_long_guard: str | None,
    desired_ps_short_guard: str | None,
    key_long,
    key_short,
    long_open: bool,
    short_open: bool,
    stop_enabled: bool,
    apply_usdt_limit: bool,
    apply_percent_limit: bool,
    stop_usdt_limit: float,
    stop_percent_limit: float,
    scope: str,
    is_cumulative: bool,
    last_rsi,
):
    try:
        rsi_cfg = cw.get("indicators", {}).get("rsi", {})
        exit_up = float(rsi_cfg.get("sell_value", 70))
        exit_dn = float(rsi_cfg.get("buy_value", 30))
    except Exception:
        exit_up, exit_dn = 70.0, 30.0

    long_open, short_open = apply_rsi_exit_management(
        self,
        cw=cw,
        account_type=account_type,
        allow_opposite_enabled=allow_opposite_enabled,
        desired_ps_long_guard=desired_ps_long_guard,
        desired_ps_short_guard=desired_ps_short_guard,
        key_long=key_long,
        key_short=key_short,
        long_open=long_open,
        short_open=short_open,
        last_rsi=last_rsi,
        exit_up=exit_up,
        exit_dn=exit_dn,
    )

    return apply_futures_cycle_risk_management(
        self,
        cw=cw,
        df=df,
        account_type=account_type,
        dual_side=dual_side,
        key_long=key_long,
        key_short=key_short,
        long_open=long_open,
        short_open=short_open,
        stop_enabled=stop_enabled,
        apply_usdt_limit=apply_usdt_limit,
        apply_percent_limit=apply_percent_limit,
        stop_usdt_limit=stop_usdt_limit,
        stop_percent_limit=stop_percent_limit,
        scope=scope,
        is_cumulative=is_cumulative,
    )


__all__ = ["_apply_cycle_risk_management"]
