from __future__ import annotations

from .close_execution import _safe_log


def _resolve_indicator_conflicts(
    self,
    leg_key: tuple[str, str, str],
    indicator_keys: list[str],
    current_entry: dict,
) -> None:
    if not indicator_keys:
        return
    if not self._strategy_coerce_bool(self.config.get("allow_indicator_close_without_signal"), False):
        # Respect strict flip enforcement: do not auto-close opposite legs unless an explicit flip signal exists.
        return
    symbol, interval, side_raw = leg_key
    side_norm = "BUY" if str(side_raw or "").upper() in {"BUY", "LONG"} else "SELL"
    opposite_side = "SELL" if side_norm == "BUY" else "BUY"
    cw_stub = {"symbol": symbol, "interval": interval}
    account_type = str(self.config.get("account_type") or getattr(self.binance, "account_type", "") or "").upper()
    dual_side = False
    if account_type == "FUTURES":
        try:
            dual_side = bool(self.binance.get_futures_dual_side())
        except Exception as exc:
            raise RuntimeError("indicator conflict resolution could not verify position mode") from exc
    desired_ps_opposite = None
    desired_ps_current = None
    if dual_side:
        desired_ps_opposite = "LONG" if opposite_side == "BUY" else "SHORT"
        desired_ps_current = "LONG" if side_norm == "BUY" else "SHORT"
    conflict_found = False
    for indicator_key in indicator_keys:
        conflicts = self._iter_indicator_entries(symbol, interval, indicator_key, opposite_side)
        if not conflicts:
            continue
        conflict_found = True
        _safe_log(
            self,
            f"{symbol}@{interval or 'default'} conflict: {indicator_key} has active {opposite_side} "
            f"leg while opening {side_norm}. Forcing additional close.",
        )
        for conflict_leg_key, conflict_entry in conflicts:
            close_error: Exception | None = None
            try:
                self._close_leg_entry(
                    cw_stub,
                    conflict_leg_key,
                    conflict_entry,
                    opposite_side,
                    "SELL" if opposite_side == "BUY" else "BUY",
                    desired_ps_opposite,
                    loss_usdt=0.0,
                    price_pct=0.0,
                    margin_pct=0.0,
                    queue_flip=False,
                )
            except Exception as exc:
                close_error = exc
            if close_error is not None:
                _safe_log(
                    self,
                    f"{symbol}@{interval or 'default'} failed to close conflicting "
                    f"{opposite_side} leg: {close_error}",
                )
                continue
    if conflict_found:
        # After forcing opposite closes, re-check. If still conflicting, drop the newly opened leg.
        for indicator_key in indicator_keys:
            residual = self._iter_indicator_entries(symbol, interval, indicator_key, opposite_side)
            if residual:
                _safe_log(
                    self,
                    f"{symbol}@{interval or 'default'} conflict persists for {indicator_key}; "
                    f"closing newly opened {side_norm} leg to avoid overlap.",
                )
                self._close_leg_entry(
                    cw_stub,
                    leg_key,
                    current_entry,
                    side_norm,
                    "SELL" if side_norm == "BUY" else "BUY",
                    desired_ps_current,
                    loss_usdt=0.0,
                    price_pct=0.0,
                    margin_pct=0.0,
                    queue_flip=False,
                )
                break
