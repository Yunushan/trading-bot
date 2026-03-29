from __future__ import annotations

from .strategy_indicator_order_common_runtime import _indicator_exchange_qty


def _build_fallback_indicator_order_request(
    self,
    *,
    cw,
    interval_current,
    indicator_key: str,
    indicator_label: str,
    target_side: str,
    desired_ps_opposite: str | None,
    indicator_interval_tokens: set[str],
    qty_tol_indicator: float,
    hedge_overlap_allowed: bool,
    now_indicator_ts: float,
) -> dict[str, object] | None:
    symbol = cw["symbol"]
    target_side = str(target_side or "").upper()
    if target_side not in {"BUY", "SELL"}:
        return None
    opposite_side = "SELL" if target_side == "BUY" else "BUY"
    opp_live_qty = 0.0
    try:
        opp_live_qty = self._indicator_live_qty_total(
            symbol,
            interval_current,
            indicator_key,
            opposite_side,
            interval_aliases=indicator_interval_tokens,
            strict_interval=True,
            use_exchange_fallback=False,
        )
    except Exception:
        opp_live_qty = 0.0
    if opp_live_qty <= qty_tol_indicator:
        try:
            account_type = str((self.config.get("account_type") or self.binance.account_type)).upper()
        except Exception:
            account_type = ""
        if account_type == "FUTURES":
            protect_other = False
            try:
                protect_other = self._symbol_side_has_other_positions(
                    symbol, interval_current, indicator_key, opposite_side
                )
            except Exception:
                protect_other = False
            if not protect_other:
                desired_ps_check = None
                try:
                    if self.binance.get_futures_dual_side():
                        desired_ps_check = desired_ps_opposite
                except Exception:
                    desired_ps_check = None
                exch_qty = _indicator_exchange_qty(
                    self,
                    symbol,
                    opposite_side,
                    desired_ps_check,
                )
                if exch_qty > qty_tol_indicator:
                    opp_live_qty = exch_qty
    if opp_live_qty > qty_tol_indicator:
        try:
            self.log(
                f"{symbol}@{interval_current or 'default'} {indicator_key} "
                f"{target_side} skipped: opposite {opposite_side} still open "
                f"({opp_live_qty:.10f})."
            )
            self.log(
                f"{symbol}@{interval_current or 'default'} {indicator_key} "
                f"guard=opp_open skip {target_side}."
            )
        except Exception:
            pass
        return None
    if not hedge_overlap_allowed:
        live_opposite_qty = _indicator_exchange_qty(
            self,
            symbol,
            opposite_side,
            desired_ps_opposite,
        )
        if live_opposite_qty > 0.0:
            try:
                self.log(
                    f"{symbol}@{interval_current or 'default'} {indicator_key} {target_side} skipped:"
                    f" {opposite_side.lower()} leg still live on exchange ({live_opposite_qty:.10f})."
                )
            except Exception:
                pass
            return None
    reentry_remaining = self._reentry_block_remaining(
        symbol,
        interval_current,
        target_side,
        now_ts=now_indicator_ts,
    )
    if reentry_remaining > 0.0:
        try:
            self.log(
                f"{symbol}@{interval_current or 'default'} {indicator_key} {target_side} suppressed by "
                f"re-entry guard ({reentry_remaining:.1f}s)."
            )
        except Exception:
            pass
        return None
    return {
        "side": target_side,
        "labels": [indicator_label],
        "signature": (indicator_key,),
        "indicator_key": indicator_key,
    }


__all__ = ["_build_fallback_indicator_order_request"]
