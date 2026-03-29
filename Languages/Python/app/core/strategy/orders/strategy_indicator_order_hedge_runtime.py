from __future__ import annotations

from .strategy_indicator_order_common_runtime import (
    _indicator_exchange_qty,
    _purge_indicator_side_if_exchange_flat,
)


def _build_hedge_indicator_order_request(
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
    reason_signal: str,
) -> tuple[bool, dict[str, object] | None]:
    symbol = cw["symbol"]
    target_side = str(target_side or "").upper()
    if target_side not in {"BUY", "SELL"}:
        return False, None
    opposite_side = "SELL" if target_side == "BUY" else "BUY"

    close_qty = self._indicator_open_qty(
        symbol,
        interval_current,
        indicator_key,
        opposite_side,
        interval_aliases=indicator_interval_tokens,
        strict_interval=True,
    )
    if close_qty <= qty_tol_indicator:
        fallback_live_qty = self._indicator_trade_book_qty(
            symbol,
            interval_current,
            indicator_key,
            opposite_side,
        )
        if fallback_live_qty > qty_tol_indicator:
            close_qty = fallback_live_qty
    if close_qty <= qty_tol_indicator:
        protect_other = False
        try:
            protect_other = self._symbol_side_has_other_positions(
                symbol, interval_current, indicator_key, opposite_side
            )
        except Exception:
            protect_other = False
        if not protect_other:
            exch_qty = _indicator_exchange_qty(
                self,
                symbol,
                opposite_side,
                desired_ps_opposite,
            )
            if exch_qty > qty_tol_indicator:
                close_qty = exch_qty
    if close_qty <= qty_tol_indicator:
        return False, None

    closed_opposite, closed_qty = self._close_indicator_positions(
        cw,
        interval_current,
        indicator_key,
        opposite_side,
        desired_ps_opposite,
        signature_hint=(indicator_key,),
        ignore_hold=True,
        interval_aliases=indicator_interval_tokens,
        qty_limit=close_qty,
        strict_interval=True,
        allow_hedge_close=True,
        reason=reason_signal,
    )
    if closed_opposite <= 0:
        if not self._close_opposite_position(
            symbol,
            interval_current,
            target_side,
            trigger_signature=(indicator_key,),
            indicator_key=(indicator_key,),
            target_qty=close_qty,
        ):
            return True, None
        closed_opposite = 1
        closed_qty = max(closed_qty, close_qty)

    remaining_after_close = self._indicator_open_qty(
        symbol,
        interval_current,
        indicator_key,
        opposite_side,
        interval_aliases=indicator_interval_tokens,
        strict_interval=True,
    )
    remaining_after_close = _purge_indicator_side_if_exchange_flat(
        self,
        symbol=symbol,
        interval_current=interval_current,
        indicator_key=indicator_key,
        side_label=opposite_side,
        desired_ps=desired_ps_opposite,
        tracked_qty=remaining_after_close,
    )
    if remaining_after_close > qty_tol_indicator:
        try:
            self.log(
                f"{symbol}@{interval_current or 'default'} {indicator_key} {target_side} deferred: "
                f"{remaining_after_close:.10f} {opposite_side.lower()} qty still open."
            )
        except Exception:
            pass
        return True, None

    flip_from_side = opposite_side if closed_qty > 0.0 else None
    if closed_opposite > 0 and flip_from_side is None:
        flip_from_side = opposite_side
    flip_qty = closed_qty if closed_qty > 0.0 else 0.0
    return True, {
        "side": target_side,
        "labels": [indicator_label],
        "signature": (indicator_key,),
        "indicator_key": indicator_key,
        "flip_from": flip_from_side,
        "flip_qty": flip_qty,
        "flip_qty_target": flip_qty,
    }


__all__ = ["_build_hedge_indicator_order_request"]
