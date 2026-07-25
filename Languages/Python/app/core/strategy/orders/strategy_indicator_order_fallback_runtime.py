from __future__ import annotations

from .strategy_indicator_order_common_runtime import _indicator_exchange_qty
from .strategy_order_error_logging import pause_for_order_uncertainty, safe_strategy_log


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
    except Exception as exc:
        pause_for_order_uncertainty(
            self,
            f"{symbol}@{interval_current or 'default'} fallback ownership lookup failed: {exc}",
            reconciliation_required=True,
        )
        return None
    if opp_live_qty <= qty_tol_indicator:
        try:
            account_type = str((self.config.get("account_type") or self.binance.account_type)).upper()
        except Exception as exc:
            pause_for_order_uncertainty(
                self,
                f"{symbol}@{interval_current or 'default'} account type lookup failed: {exc}",
                reconciliation_required=False,
            )
            return None
        if account_type == "FUTURES":
            protect_other = False
            try:
                protect_other = self._symbol_side_has_other_positions(
                    symbol, interval_current, indicator_key, opposite_side
                )
            except Exception as exc:
                pause_for_order_uncertainty(
                    self,
                    f"{symbol}@{interval_current or 'default'} other-position ownership lookup failed: {exc}",
                    reconciliation_required=True,
                )
                return None
            if not protect_other:
                desired_ps_check = None
                try:
                    if self.binance.get_futures_dual_side():
                        desired_ps_check = desired_ps_opposite
                except Exception as exc:
                    pause_for_order_uncertainty(
                        self,
                        f"{symbol}@{interval_current or 'default'} position mode lookup failed: {exc}",
                        reconciliation_required=False,
                    )
                    return None
                exch_qty = _indicator_exchange_qty(
                    self,
                    symbol,
                    opposite_side,
                    desired_ps_check,
                )
                if exch_qty > qty_tol_indicator:
                    opp_live_qty = exch_qty
    if opp_live_qty > qty_tol_indicator:
        safe_strategy_log(
            self,
            f"{symbol}@{interval_current or 'default'} {indicator_key} "
            f"{target_side} skipped: opposite {opposite_side} still open ({opp_live_qty:.10f}).",
            level="warning",
        )
        safe_strategy_log(
            self,
            f"{symbol}@{interval_current or 'default'} {indicator_key} guard=opp_open skip {target_side}.",
            level="warning",
        )
        return None
    if not hedge_overlap_allowed:
        live_opposite_qty = _indicator_exchange_qty(
            self,
            symbol,
            opposite_side,
            desired_ps_opposite,
        )
        if live_opposite_qty > 0.0:
            safe_strategy_log(
                self,
                f"{symbol}@{interval_current or 'default'} {indicator_key} {target_side} skipped:"
                f" {opposite_side.lower()} leg still live on exchange ({live_opposite_qty:.10f}).",
                level="warning",
            )
            return None
    reentry_remaining = self._reentry_block_remaining(
        symbol,
        interval_current,
        target_side,
        now_ts=now_indicator_ts,
    )
    if reentry_remaining > 0.0:
        safe_strategy_log(
            self,
            f"{symbol}@{interval_current or 'default'} {indicator_key} {target_side} suppressed by "
            f"re-entry guard ({reentry_remaining:.1f}s).",
            level="warning",
        )
        return None
    return {
        "side": target_side,
        "labels": [indicator_label],
        "signature": (indicator_key,),
        "indicator_key": indicator_key,
    }


__all__ = ["_build_fallback_indicator_order_request"]
