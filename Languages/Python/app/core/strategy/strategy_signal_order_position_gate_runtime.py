from __future__ import annotations

import time


def _prepare_signal_order_position_gate(
    self,
    *,
    cw,
    side: str,
    interval_norm: str,
    signature,
    indicator_key_hint,
    indicator_tokens_for_order,
    indicator_tokens_for_guard,
    flip_close_qty: float,
    qty_tol_slot_guard: float,
    abort_guard,
) -> dict[str, object]:
    def _abort() -> dict[str, object]:
        abort_guard()
        return {"aborted": True}

    key_bar = (cw["symbol"], cw.get("interval"), side)
    key_dup = key_bar
    try:
        now_ts = time.time()
        secs = self._interval_to_seconds(str(cw.get("interval") or "1m"))
        last_ts = self._last_order_time.get(key_bar, 0)
        if now_ts - last_ts < max(5, secs * 0.9):
            existing_entries = self._leg_entries(key_bar)
            if any(tuple(sorted(entry.get("trigger_signature") or [])) == signature for entry in existing_entries):
                return _abort()
        guard_stale_secs = max(30.0, secs * 3.0)
        if now_ts - last_ts > guard_stale_secs:
            self._last_order_time.pop(key_bar, None)
            self._leg_ledger.pop(key_bar, None)
    except Exception:
        pass

    target_flip_qty = flip_close_qty if flip_close_qty > 0.0 else None
    if not self._close_opposite_position(
        cw["symbol"],
        cw.get("interval"),
        side,
        signature,
        indicator_tokens_for_order,
        target_qty=target_flip_qty,
    ):
        return _abort()

    if indicator_tokens_for_guard:
        opp_side_guard = "SELL" if side == "BUY" else "BUY"
        indicator_interval_tokens = set(self._tokenize_interval_label(interval_norm))
        remaining_opp_qty = 0.0
        for token in indicator_tokens_for_guard:
            try:
                qty_val = self._indicator_live_qty_total(
                    cw["symbol"],
                    interval_norm,
                    token,
                    opp_side_guard,
                    interval_aliases=indicator_interval_tokens,
                    strict_interval=True,
                    use_exchange_fallback=False,
                )
            except Exception:
                qty_val = 0.0
            if qty_val > remaining_opp_qty:
                remaining_opp_qty = qty_val
        if remaining_opp_qty <= qty_tol_slot_guard:
            try:
                account_type_check = str(
                    (self.config.get("account_type") or self.binance.account_type)
                ).upper()
            except Exception:
                account_type_check = ""
            if account_type_check == "FUTURES":
                protect_other = False
                for token in indicator_tokens_for_guard:
                    try:
                        if self._symbol_side_has_other_positions(
                            cw["symbol"], interval_norm, token, opp_side_guard
                        ):
                            protect_other = True
                            break
                    except Exception:
                        continue
                if not protect_other:
                    try:
                        desired_ps_check = None
                        if self.binance.get_futures_dual_side():
                            desired_ps_check = "LONG" if opp_side_guard == "BUY" else "SHORT"
                        exch_qty = max(
                            0.0,
                            float(
                                self._current_futures_position_qty(
                                    cw["symbol"], opp_side_guard, desired_ps_check
                                )
                                or 0.0
                            ),
                        )
                    except Exception:
                        exch_qty = 0.0
                    if exch_qty > qty_tol_slot_guard:
                        remaining_opp_qty = exch_qty
        if remaining_opp_qty > qty_tol_slot_guard:
            try:
                indicator_label_guard = (
                    indicator_key_hint
                    or (indicator_tokens_for_guard[0] if indicator_tokens_for_guard else "indicator")
                ).upper()
                self.log(
                    f"{cw['symbol']}@{interval_norm or 'default'} {indicator_label_guard} {side} blocked: "
                    f"opposite {opp_side_guard} still open ({remaining_opp_qty:.10f})."
                )
                self.log(
                    f"{cw['symbol']}@{interval_norm or 'default'} {indicator_label_guard} "
                    f"guard=opp_open block {side}."
                )
            except Exception:
                pass
            return _abort()

    return {
        "aborted": False,
        "key_bar": key_bar,
        "key_dup": key_dup,
    }


def bind_strategy_signal_order_position_gate_runtime(strategy_cls) -> None:
    strategy_cls._prepare_signal_order_position_gate = _prepare_signal_order_position_gate
