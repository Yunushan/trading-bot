from __future__ import annotations

from .strategy_cycle_risk_stop_context_runtime import (
    build_futures_stop_state,
    ensure_futures_leg_entry_price,
    purge_flat_futures_cycle_legs,
)
from .strategy_cycle_risk_stop_cumulative_runtime import apply_cumulative_futures_stop_management
from .strategy_cycle_risk_stop_directional_runtime import apply_directional_futures_stop_management


def apply_futures_cycle_risk_management(
    self,
    *,
    cw,
    df,
    account_type: str,
    dual_side: bool,
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
):
    state = build_futures_stop_state(self, cw=cw, df=df)
    last_price = state.get("last_price")
    load_positions_cache = state.get("load_positions_cache")

    if account_type == "FUTURES":
        purge_flat_futures_cycle_legs(self, cw=cw, dual_side=dual_side, state=state)

    if stop_enabled and last_price is not None and account_type == "FUTURES":
        leg_long, qty_long, entry_price_long, pos_long = ensure_futures_leg_entry_price(
            self,
            cw=cw,
            leg_key=key_long,
            expect_long=True,
            dual_side=dual_side,
            state=state,
        )
        leg_short, qty_short, entry_price_short, pos_short = ensure_futures_leg_entry_price(
            self,
            cw=cw,
            leg_key=key_short,
            expect_long=False,
            dual_side=dual_side,
            state=state,
        )
        pos_long_qty_total = 0.0
        pos_short_qty_total = 0.0

        if qty_long <= 0.0 and pos_long:
            try:
                qty_long = max(0.0, float(pos_long.get("positionAmt") or 0.0))
            except Exception:
                qty_long = 0.0
            if qty_long > 0.0:
                self._sync_leg_entry_totals(key_long, qty_long)
        if pos_long:
            try:
                amt_val = float(pos_long.get("positionAmt") or 0.0)
                pos_long_qty_total = abs(amt_val)
            except Exception:
                pos_long_qty_total = 0.0
        if qty_short <= 0.0 and pos_short:
            try:
                qty_short = abs(float(pos_short.get("positionAmt") or 0.0))
            except Exception:
                qty_short = 0.0
            if qty_short > 0.0:
                self._sync_leg_entry_totals(key_short, qty_short)
        if pos_short:
            try:
                amt_val = float(pos_short.get("positionAmt") or 0.0)
                pos_short_qty_total = abs(amt_val)
            except Exception:
                pos_short_qty_total = 0.0

        entries_long = self._leg_entries(key_long)
        entries_short = self._leg_entries(key_short)

        if scope == "per_trade":
            if entries_long:
                self._evaluate_per_trade_stop(
                    cw,
                    key_long,
                    entries_long,
                    side_label="BUY",
                    last_price=last_price,
                    apply_usdt_limit=apply_usdt_limit,
                    apply_percent_limit=apply_percent_limit,
                    stop_usdt_limit=stop_usdt_limit,
                    stop_percent_limit=stop_percent_limit,
                    dual_side=dual_side,
                )
            if entries_short:
                self._evaluate_per_trade_stop(
                    cw,
                    key_short,
                    entries_short,
                    side_label="SELL",
                    last_price=last_price,
                    apply_usdt_limit=apply_usdt_limit,
                    apply_percent_limit=apply_percent_limit,
                    stop_usdt_limit=stop_usdt_limit,
                    stop_percent_limit=stop_percent_limit,
                    dual_side=dual_side,
                )
            leg_long = self._leg_ledger.get(key_long, {}) or {}
            leg_short = self._leg_ledger.get(key_short, {}) or {}
            qty_long = float(leg_long.get("qty") or 0.0)
            qty_short = float(leg_short.get("qty") or 0.0)
            entry_price_long = float(leg_long.get("entry_price") or 0.0)
            entry_price_short = float(leg_short.get("entry_price") or 0.0)
        elif is_cumulative:
            cumulative_triggered = apply_cumulative_futures_stop_management(
                self,
                cw=cw,
                last_price=last_price,
                dual_side=dual_side,
                apply_usdt_limit=apply_usdt_limit,
                apply_percent_limit=apply_percent_limit,
                stop_usdt_limit=stop_usdt_limit,
                stop_percent_limit=stop_percent_limit,
                state=state,
            )
            if cumulative_triggered:
                long_open = False
                short_open = False
        else:
            apply_directional_futures_stop_management(
                self,
                cw=cw,
                dual_side=dual_side,
                key_long=key_long,
                key_short=key_short,
                qty_long=qty_long,
                qty_short=qty_short,
                entry_price_long=entry_price_long,
                entry_price_short=entry_price_short,
                pos_long=pos_long,
                pos_short=pos_short,
                pos_long_qty_total=pos_long_qty_total,
                pos_short_qty_total=pos_short_qty_total,
                apply_usdt_limit=apply_usdt_limit,
                apply_percent_limit=apply_percent_limit,
                stop_usdt_limit=stop_usdt_limit,
                stop_percent_limit=stop_percent_limit,
                last_price=last_price,
            )
        leg_long_state = self._leg_ledger.get(key_long, {}) or {}
        leg_short_state = self._leg_ledger.get(key_short, {}) or {}
        qty_long = float(leg_long_state.get("qty") or 0.0)
        qty_short = float(leg_short_state.get("qty") or 0.0)
        long_open = qty_long > 0.0
        short_open = qty_short > 0.0

    return {
        "last_price": last_price,
        "positions_cache": state.get("positions_cache"),
        "load_positions_cache": load_positions_cache,
        "long_open": long_open,
        "short_open": short_open,
    }


__all__ = ["apply_futures_cycle_risk_management"]
