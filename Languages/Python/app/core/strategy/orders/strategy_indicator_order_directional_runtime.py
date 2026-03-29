from __future__ import annotations

from .strategy_indicator_order_common_runtime import (
    _indicator_exchange_qty,
    _purge_indicator_side_if_exchange_flat,
)


def _build_directional_indicator_order_request(
    self,
    *,
    cw,
    interval_current,
    indicator_key: str,
    indicator_label: str,
    target_side: str,
    desired_ps_target: str | None,
    desired_ps_opposite: str | None,
    indicator_interval_tokens: set[str],
    qty_tol_indicator: float,
    reason_signal: str,
    recent_close,
    now_indicator_ts: float,
) -> dict[str, object] | None:
    symbol = cw["symbol"]
    target_side = str(target_side or "").upper()
    if target_side not in {"BUY", "SELL"}:
        return None
    opposite_side = "SELL" if target_side == "BUY" else "BUY"
    remaining_opposite_qty = self._indicator_open_qty(
        symbol,
        interval_current,
        indicator_key,
        opposite_side,
        interval_aliases=indicator_interval_tokens,
        strict_interval=True,
    )
    if remaining_opposite_qty <= qty_tol_indicator:
        fallback_live_qty = self._indicator_trade_book_qty(
            symbol,
            interval_current,
            indicator_key,
            opposite_side,
        )
        if fallback_live_qty <= qty_tol_indicator:
            fallback_live_qty = _indicator_exchange_qty(
                self,
                symbol,
                opposite_side,
                desired_ps_opposite,
            )
        if fallback_live_qty > qty_tol_indicator:
            remaining_opposite_qty = fallback_live_qty

    closed_opposite = 0
    closed_opposite_qty = 0.0
    qty_cap = remaining_opposite_qty if remaining_opposite_qty > qty_tol_indicator else None
    if remaining_opposite_qty > qty_tol_indicator:
        closed_opposite, closed_opposite_qty = self._close_indicator_positions(
            cw,
            interval_current,
            indicator_key,
            opposite_side,
            desired_ps_opposite,
            signature_hint=(indicator_key,),
            ignore_hold=True,
            interval_aliases=indicator_interval_tokens,
            qty_limit=qty_cap,
            strict_interval=True,
            allow_hedge_close=True,
            reason=reason_signal,
        )
        if closed_opposite <= 0:
            try:
                still_open = self._indicator_has_open(
                    symbol, interval_current, indicator_key, opposite_side
                )
            except Exception:
                still_open = False
            if still_open:
                target_qty_hint = qty_cap
                if (target_qty_hint is None or target_qty_hint <= 0.0) and remaining_opposite_qty > 0.0:
                    target_qty_hint = remaining_opposite_qty
                if not self._close_opposite_position(
                    symbol,
                    interval_current,
                    target_side,
                    trigger_signature=(indicator_key,),
                    indicator_key=(indicator_key,),
                    target_qty=target_qty_hint,
                ):
                    return None
                closed_opposite = 1

    if closed_opposite <= 0:
        fallback_qty = self._indicator_trade_book_qty(
            symbol,
            interval_current,
            indicator_key,
            opposite_side,
        )
        if fallback_qty <= 0.0:
            fallback_qty = _indicator_exchange_qty(
                self,
                symbol,
                opposite_side,
                desired_ps_opposite,
            )
        if fallback_qty > 0.0:
            retry_count, retry_qty = self._close_indicator_positions(
                cw,
                interval_current,
                indicator_key,
                opposite_side,
                desired_ps_opposite,
                signature_hint=(indicator_key,),
                ignore_hold=True,
                interval_aliases=indicator_interval_tokens,
                qty_limit=fallback_qty,
                strict_interval=True,
                allow_hedge_close=True,
                reason=reason_signal,
            )
            closed_opposite = retry_count
            closed_opposite_qty = retry_qty

    if closed_opposite <= 0:
        remaining_opposite_qty = self._indicator_open_qty(
            symbol,
            interval_current,
            indicator_key,
            opposite_side,
            interval_aliases=indicator_interval_tokens,
            strict_interval=True,
        )
        remaining_opposite_qty = _purge_indicator_side_if_exchange_flat(
            self,
            symbol=symbol,
            interval_current=interval_current,
            indicator_key=indicator_key,
            side_label=opposite_side,
            desired_ps=desired_ps_opposite,
            tracked_qty=remaining_opposite_qty,
        )
        if remaining_opposite_qty > qty_tol_indicator:
            try:
                self.log(
                    f"{symbol}@{interval_current or 'default'} {indicator_key} {target_side} skipped: "
                    f"{opposite_side.lower()} leg still live on exchange."
                )
            except Exception:
                pass
            return None

    flip_from_side = None
    flip_qty = 0.0
    flip_qty_target = 0.0
    remaining_opposite_qty = self._indicator_open_qty(
        symbol,
        interval_current,
        indicator_key,
        opposite_side,
        interval_aliases=indicator_interval_tokens,
        strict_interval=True,
    )
    if closed_opposite > 0 and closed_opposite_qty > 0.0:
        flip_from_side = opposite_side
        flip_qty = closed_opposite_qty
        flip_qty_target = closed_opposite_qty
        try:
            self.log(
                f"{symbol}@{interval_current} {indicator_key} flip {opposite_side}→{target_side} "
                f"(closed {flip_qty:.10f})."
            )
        except Exception:
            pass
    elif remaining_opposite_qty > 0.0:
        try:
            self.log(
                f"{symbol}@{interval_current or 'default'} {indicator_key} {target_side} deferred: "
                f"{remaining_opposite_qty:.10f} {opposite_side.lower()} qty still open."
            )
        except Exception:
            pass
        return None
    else:
        protect_opposite_residual = self._symbol_side_has_other_positions(
            symbol,
            interval_current,
            indicator_key,
            opposite_side,
        )
        live_opposite_residual = _indicator_exchange_qty(
            self,
            symbol,
            opposite_side,
            desired_ps_opposite,
        )
        tol_live = max(1e-9, live_opposite_residual * 1e-6)
        if protect_opposite_residual and live_opposite_residual > tol_live:
            try:
                self.log(
                    f"{symbol}@{interval_current or 'default'} {indicator_key} {target_side} skipping residual "
                    f"{opposite_side.lower()} close (other {opposite_side} legs still active)."
                )
            except Exception:
                pass
        elif live_opposite_residual > tol_live:
            try:
                self.log(
                    f"{symbol}@{interval_current or 'default'} {indicator_key} {target_side} forcing close of residual "
                    f"{opposite_side.lower()} ({live_opposite_residual:.10f})."
                )
            except Exception:
                pass
            if not self._close_opposite_position(
                symbol,
                interval_current,
                target_side,
                trigger_signature=(indicator_key,),
                indicator_key=(indicator_key,),
                target_qty=live_opposite_residual,
            ):
                return None
            flip_from_side = opposite_side
            flip_qty = live_opposite_residual
            flip_qty_target = live_opposite_residual
        else:
            current_opposite_qty = self._indicator_open_qty(
                symbol,
                interval_current,
                indicator_key,
                opposite_side,
                interval_aliases=indicator_interval_tokens,
                strict_interval=True,
            )
            current_opposite_qty = _purge_indicator_side_if_exchange_flat(
                self,
                symbol=symbol,
                interval_current=interval_current,
                indicator_key=indicator_key,
                side_label=opposite_side,
                desired_ps=desired_ps_opposite,
                tracked_qty=current_opposite_qty,
            )
            if current_opposite_qty > qty_tol_indicator and closed_opposite_qty <= 0.0 and flip_qty <= 0.0:
                return None

    if closed_opposite > 0 and flip_from_side is None:
        flip_from_side = opposite_side
    if flip_from_side is None and recent_close:
        flip_from_side = opposite_side
        try:
            if flip_qty <= 0.0:
                flip_qty = float(recent_close.get("qty") or 0.0)
            if flip_qty_target <= 0.0 and flip_qty > 0.0:
                flip_qty_target = flip_qty
        except Exception:
            pass

    current_target_qty = self._indicator_open_qty(
        symbol,
        interval_current,
        indicator_key,
        target_side,
        interval_aliases=indicator_interval_tokens,
        strict_interval=True,
    )
    current_target_qty = _purge_indicator_side_if_exchange_flat(
        self,
        symbol=symbol,
        interval_current=interval_current,
        indicator_key=indicator_key,
        side_label=target_side,
        desired_ps=desired_ps_target,
        tracked_qty=current_target_qty,
    )
    if current_target_qty > qty_tol_indicator:
        return None

    bypass_reentry_guard = bool(
        flip_from_side
        or closed_opposite > 0
        or closed_opposite_qty > 0.0
        or flip_qty > 0.0
    )
    if not bypass_reentry_guard:
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
        "flip_from": flip_from_side,
        "flip_qty": flip_qty,
        "flip_qty_target": flip_qty_target,
    }


__all__ = ["_build_directional_indicator_order_request"]
