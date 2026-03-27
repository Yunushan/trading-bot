from __future__ import annotations


def _prepare_signal_order_margin_state(
    self,
    *,
    cw,
    side: str,
    pct: float,
    free_usdt: float,
    price: float,
    futures_balance_snap,
    flip_close_qty: float,
    entries_side_all,
    active_slot_tokens_all,
    existing_margin_indicator_total: float,
    slot_label: str,
    slot_token_for_order: str,
    lev: int,
    abort_guard,
) -> dict[str, object]:
    def _abort() -> dict[str, object]:
        abort_guard()
        return {"aborted": True}

    try:
        if isinstance(futures_balance_snap, dict) and futures_balance_snap:
            available_total = float(futures_balance_snap.get("available") or 0.0)
        else:
            available_total = float(self.binance.get_futures_balance_usdt())
    except Exception:
        available_total = 0.0
    try:
        if isinstance(futures_balance_snap, dict) and futures_balance_snap:
            wallet_total = float(futures_balance_snap.get("wallet") or 0.0)
        else:
            wallet_total = float(self.binance.get_total_wallet_balance())
    except Exception:
        wallet_total = 0.0
    available_total = max(0.0, available_total)
    wallet_total = max(0.0, wallet_total)
    if wallet_total <= 0.0:
        wallet_total = max(available_total, free_usdt)
    ledger_margin_total = 0.0
    try:
        for leg_state in self._leg_ledger.values():
            if not isinstance(leg_state, dict):
                continue
            margin_val = float(leg_state.get("margin_usdt") or 0.0)
            if margin_val > 0.0:
                ledger_margin_total += margin_val
    except Exception:
        ledger_margin_total = 0.0
    equity_estimate = max(wallet_total, available_total + ledger_margin_total)
    equity_estimate = max(equity_estimate, free_usdt + ledger_margin_total)
    if equity_estimate <= 0.0:
        equity_estimate = max(wallet_total, available_total, free_usdt, ledger_margin_total)
    wallet_total = max(0.0, equity_estimate)

    margin_tolerance = float(self.config.get("margin_over_target_tolerance", 0.05))
    if margin_tolerance > 1.0:
        margin_tolerance = margin_tolerance / 100.0
    margin_tolerance = max(0.0, margin_tolerance)
    margin_filter_slippage = float(self.config.get("margin_filter_slippage", 0.1))
    if margin_filter_slippage > 1.0:
        margin_filter_slippage = margin_filter_slippage / 100.0
    margin_filter_slippage = max(0.0, margin_filter_slippage)

    filter_headroom = 0.0
    try:
        f_filters = self.binance.get_futures_symbol_filters(cw["symbol"]) or {}
        min_notional_filter = float(f_filters.get("minNotional") or 0.0)
        min_qty_filter = float(f_filters.get("minQty") or 0.0)
        min_qty_margin = (min_qty_filter * price) / float(lev) if price > 0.0 else 0.0
        min_notional_margin = min_notional_filter / float(lev) if min_notional_filter > 0.0 else 0.0
        filter_margin_floor = max(min_qty_margin, min_notional_margin)
        if filter_margin_floor > 0.0:
            filter_headroom = max(filter_margin_floor * 0.25, 0.0)
    except Exception:
        filter_headroom = 0.0

    per_indicator_margin_target = wallet_total * pct
    if per_indicator_margin_target <= 0.0:
        self.log(
            f"{cw['symbol']}@{cw.get('interval')} sizing blocked: computed margin target <= 0 "
            f"for {pct*100:.2f}% allocation."
        )
        return _abort()
    per_indicator_notional_target = per_indicator_margin_target * float(lev)

    desired_slots_after = 1
    max_indicator_margin = (
        per_indicator_margin_target * desired_slots_after * (1.0 + margin_tolerance)
        + filter_headroom
    )
    if existing_margin_indicator_total >= max_indicator_margin - 1e-9:
        self.log(
            f"{cw['symbol']}@{cw.get('interval')} capital guard: existing {side} margin for {slot_label} "
            f"{existing_margin_indicator_total:.4f} USDT already >= cap {max_indicator_margin:.4f} USDT "
            f"({pct*100:.2f}% margin target → {per_indicator_notional_target:.4f} USDT notional @ {lev}x)."
        )
        return _abort()

    qty_override_from_flip = None
    if flip_close_qty > 0.0:
        try:
            qty_override_from_flip = max(0.0, float(flip_close_qty))
        except Exception:
            qty_override_from_flip = None
    if qty_override_from_flip is not None and qty_override_from_flip > 0.0:
        target_margin = (qty_override_from_flip * price) / float(lev)
        desired_total_margin = target_margin + existing_margin_indicator_total
    else:
        desired_total_margin = per_indicator_margin_target * desired_slots_after
        target_margin = max(0.0, desired_total_margin - existing_margin_indicator_total)
    if target_margin <= 0.0:
        self.log(
            f"{cw['symbol']}@{cw.get('interval')} capital guard: {slot_label} exposure already meets "
            f"the {pct*100:.2f}% margin allocation target."
        )
        return _abort()

    if available_total <= 0.0:
        available_total = free_usdt
    if available_total <= 0.0:
        self.log(f"{cw['symbol']}@{cw.get('interval')} capital guard: no available USDT to allocate.")
        return _abort()
    if available_total < target_margin * 0.95:
        self.log(
            f"{cw['symbol']}@{cw.get('interval')} capital guard: requested {target_margin:.4f} USDT "
            f"({pct*100:.2f}% margin target) but only {available_total:.4f} USDT available."
        )
        return _abort()

    existing_margin_same_side = sum(
        self._entry_margin_value(entry, lev) for _, entry in entries_side_all
    )

    filters_for_symbol: dict | None = None
    filter_min_margin = 0.0
    try:
        filters_for_symbol = self.binance.get_futures_symbol_filters(cw["symbol"]) or {}
        step_sz = float(filters_for_symbol.get("stepSize") or 0.0)
        min_qty_filter = float(filters_for_symbol.get("minQty") or 0.0)
        min_notional_filter = float(filters_for_symbol.get("minNotional") or 0.0)
        if price > 0.0 and lev > 0:
            qty_floor = max(min_qty_filter, 0.0)
            if min_notional_filter > 0.0:
                qty_needed = min_notional_filter / float(price)
                if step_sz > 0.0:
                    qty_needed = self.binance._ceil_to_step(qty_needed, step_sz)
                qty_floor = max(qty_floor, qty_needed)
            if qty_floor > 0.0:
                filter_min_margin = (qty_floor * price) / float(lev)
    except Exception:
        filters_for_symbol = None
        filter_min_margin = 0.0

    if qty_override_from_flip is not None and qty_override_from_flip > 0.0:
        qty_target = qty_override_from_flip
    else:
        qty_target = (target_margin * lev) / price
    adj_qty, adj_err = self.binance.adjust_qty_to_filters_futures(cw["symbol"], qty_target, price)
    if adj_err:
        self.log(f"{cw['symbol']}@{cw.get('interval')} sizing blocked: {adj_err}.")
        return _abort()
    if adj_qty <= 0.0:
        self.log(f"{cw['symbol']}@{cw.get('interval')} sizing blocked: quantity <= 0 after filter adjustment.")
        return _abort()

    margin_est = (adj_qty * price) / float(lev)
    indicator_soft_cap = max_indicator_margin * (1.0 + margin_filter_slippage)
    if filter_min_margin > max_indicator_margin:
        indicator_soft_cap = max(indicator_soft_cap, filter_min_margin * (1.0 + margin_filter_slippage))
    if existing_margin_indicator_total + margin_est > indicator_soft_cap + 1e-6:
        self.log(
            f"{cw['symbol']}@{cw.get('interval')} capital guard: adding {margin_est:.4f} USDT to {slot_label} "
            f"would exceed cap {max_indicator_margin:.4f} USDT (soft cap {indicator_soft_cap:.4f}) "
            f"({pct*100:.2f}% margin target → {per_indicator_notional_target:.4f} USDT notional @ {lev}x)."
        )
        return _abort()

    expected_slots_after = len(active_slot_tokens_all)
    if slot_token_for_order not in active_slot_tokens_all:
        expected_slots_after += 1
    expected_slots_after = max(1, expected_slots_after)
    expected_slots_after = max(expected_slots_after, desired_slots_after)
    max_side_margin = (
        per_indicator_margin_target * expected_slots_after * (1.0 + margin_tolerance)
        + filter_headroom
    )
    projected_total_margin = existing_margin_same_side + margin_est
    side_soft_cap = max_side_margin * (1.0 + margin_filter_slippage)
    if filter_min_margin > max_side_margin:
        side_soft_cap = max(side_soft_cap, filter_min_margin * (1.0 + margin_filter_slippage))
    if projected_total_margin > side_soft_cap + 1e-6:
        self.log(
            f"{cw['symbol']}@{cw.get('interval')} capital guard: projected total {side} margin {projected_total_margin:.4f} USDT "
            f"exceeds cap {max_side_margin:.4f} USDT (soft cap {side_soft_cap:.4f}) for {expected_slots_after} slot(s) at "
            f"{pct*100:.2f}% margin each."
        )
        return _abort()

    min_required_margin = 0.0
    try:
        f_filters = filters_for_symbol or self.binance.get_futures_symbol_filters(cw["symbol"]) or {}
        min_notional_filter = float(f_filters.get("minNotional") or 0.0)
        if min_notional_filter > 0.0:
            min_required_margin = max(min_required_margin, min_notional_filter / float(lev))
        min_qty_filter = float(f_filters.get("minQty") or 0.0)
        if min_qty_filter > 0.0 and price > 0.0:
            min_required_margin = max(min_required_margin, (min_qty_filter * price) / float(lev))
    except Exception:
        min_required_margin = max(min_required_margin, 0.0)
    if min_required_margin > 0.0 and min_required_margin > indicator_soft_cap + 1e-9:
        self.log(
            f"{cw['symbol']}@{cw.get('interval')} sizing blocked: minimum contract margin {min_required_margin:.4f} "
            f"exceeds cap {max_indicator_margin:.4f} USDT (soft cap {indicator_soft_cap:.4f}) for {slot_label} "
            f"({pct*100:.2f}% margin target). Skipping trade to avoid oversizing."
        )
        return _abort()

    qty_est = adj_qty
    reduce_only = False
    if bool(self.config.get("add_only", False)):
        dual = self.binance.get_futures_dual_side()
        if not dual:
            try:
                net_amt = float(self.binance.get_net_futures_position_amt(cw["symbol"]))
            except Exception:
                net_amt = 0.0
            if net_amt > 0 and side == "SELL":
                qty_est = min(qty_est, abs(net_amt))
                reduce_only = True
            elif net_amt < 0 and side == "BUY":
                qty_est = min(qty_est, abs(net_amt))
                reduce_only = True
            if qty_est <= 0:
                self.log(f"{cw['symbol']}@{cw['interval']} Opposite open blocked (one-way add-only). net={net_amt}")
                return _abort()

    desired_ps = None
    if self.binance.get_futures_dual_side():
        desired_ps = "LONG" if side == "BUY" else "SHORT"

    return {
        "aborted": False,
        "lev": lev,
        "qty_est": qty_est,
        "reduce_only": reduce_only,
        "desired_ps": desired_ps,
    }


def bind_strategy_signal_order_margin_runtime(strategy_cls) -> None:
    strategy_cls._prepare_signal_order_margin_state = _prepare_signal_order_margin_state
