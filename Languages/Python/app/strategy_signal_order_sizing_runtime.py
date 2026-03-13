from __future__ import annotations

try:
    from . import strategy_signal_order_margin_runtime
    from . import strategy_signal_order_position_gate_runtime
    from . import strategy_signal_order_slot_runtime
except ImportError:  # pragma: no cover - standalone execution fallback
    import strategy_signal_order_margin_runtime
    import strategy_signal_order_position_gate_runtime
    import strategy_signal_order_slot_runtime


def _resolve_signal_order_account_state(self, *, cw, last_price) -> dict[str, object]:
    account_type = str((self.config.get("account_type") or self.binance.account_type)).upper()
    futures_balance_snap = None
    if account_type == "FUTURES" and hasattr(self.binance, "get_futures_balance_snapshot"):
        try:
            futures_balance_snap = self.binance.get_futures_balance_snapshot(force_refresh=True) or {}
        except Exception:
            futures_balance_snap = None
    if isinstance(futures_balance_snap, dict) and futures_balance_snap:
        try:
            usdt_bal = float(futures_balance_snap.get("total") or futures_balance_snap.get("wallet") or 0.0)
        except Exception:
            usdt_bal = 0.0
    else:
        usdt_bal = self.binance.get_total_usdt_value()
    pct_raw = float(cw.get("position_pct", 100.0))
    pct_units_raw = str(
        cw.get("position_pct_units")
        or cw.get("_position_pct_units")
        or ""
    ).strip().lower()
    if pct_units_raw in {"percent", "%", "perc"}:
        pct = pct_raw / 100.0
    elif pct_units_raw in {"fraction", "decimal", "ratio"}:
        pct = pct_raw
    else:
        pct = pct_raw / 100.0 if pct_raw > 1.0 else pct_raw
    pct = max(0.0001, min(1.0, pct))
    free_usdt = max(float(usdt_bal or 0.0), 0.0)
    price = last_price or 0.0
    return {
        "account_type": account_type,
        "futures_balance_snap": futures_balance_snap,
        "free_usdt": free_usdt,
        "pct": pct,
        "price": price,
    }


def _prepare_futures_signal_order_state(
    self,
    *,
    cw,
    side: str,
    interval_norm: str,
    signature,
    trigger_labels,
    context_key: str,
    indicator_key_hint,
    indicator_tokens_for_order,
    indicator_tokens_for_guard,
    flip_active: bool,
    flip_close_qty: float,
    qty_tol_slot_guard: float,
    free_usdt: float,
    price: float,
    pct: float,
    futures_balance_snap,
    abort_guard,
) -> dict[str, object]:
    def _abort() -> dict[str, object]:
        abort_guard()
        return {"aborted": True}

    if price <= 0.0:
        self.log(f"{cw['symbol']}@{cw.get('interval')} skipped: no market price available for sizing.")
        return _abort()

    try:
        lev_raw = cw.get("leverage", self.config.get("leverage", 1))
        lev = int(lev_raw)
    except Exception:
        lev = int(self.config.get("leverage", 1))
    if lev <= 0:
        lev = 1

    slot_state = self._prepare_signal_order_slot_state(
        cw=cw,
        side=side,
        lev=lev,
        signature=signature,
        trigger_labels=trigger_labels,
        context_key=context_key,
        indicator_key_hint=indicator_key_hint,
        indicator_tokens_for_order=indicator_tokens_for_order,
        flip_active=flip_active,
        abort_guard=abort_guard,
    )
    if slot_state.get("aborted"):
        return slot_state

    signature = tuple(slot_state.get("signature") or signature)
    trigger_labels = list(slot_state.get("trigger_labels") or trigger_labels)
    context_key = str(slot_state.get("context_key") or context_key)
    indicator_tokens_for_order = list(slot_state.get("indicator_tokens_for_order") or indicator_tokens_for_order)
    entries_side_all = list(slot_state.get("entries_side_all") or [])
    active_slot_tokens_all = set(slot_state.get("active_slot_tokens_all") or set())
    try:
        existing_margin_indicator_total = float(slot_state.get("existing_margin_indicator_total") or 0.0)
    except Exception:
        existing_margin_indicator_total = 0.0
    slot_label = str(slot_state.get("slot_label") or "current slot")
    slot_token_for_order = str(slot_state.get("slot_token_for_order") or f"side:{side}")
    slot_key_tuple = slot_state.get("slot_key_tuple")

    margin_state = self._prepare_signal_order_margin_state(
        cw=cw,
        side=side,
        pct=pct,
        free_usdt=free_usdt,
        price=price,
        futures_balance_snap=futures_balance_snap,
        flip_close_qty=flip_close_qty,
        entries_side_all=entries_side_all,
        active_slot_tokens_all=active_slot_tokens_all,
        existing_margin_indicator_total=existing_margin_indicator_total,
        slot_label=slot_label,
        slot_token_for_order=slot_token_for_order,
        lev=lev,
        abort_guard=abort_guard,
    )
    if margin_state.get("aborted"):
        return margin_state

    try:
        lev = int(margin_state.get("lev") or lev)
    except Exception:
        pass
    try:
        qty_est = float(margin_state.get("qty_est") or 0.0)
    except Exception:
        qty_est = 0.0
    reduce_only = bool(margin_state.get("reduce_only"))
    desired_ps = margin_state.get("desired_ps")

    position_gate_state = self._prepare_signal_order_position_gate(
        cw=cw,
        side=side,
        interval_norm=interval_norm,
        signature=signature,
        indicator_key_hint=indicator_key_hint,
        indicator_tokens_for_order=indicator_tokens_for_order,
        indicator_tokens_for_guard=indicator_tokens_for_guard,
        flip_close_qty=flip_close_qty,
        qty_tol_slot_guard=qty_tol_slot_guard,
        abort_guard=abort_guard,
    )
    if position_gate_state.get("aborted"):
        return position_gate_state
    key_bar = position_gate_state.get("key_bar") or (cw["symbol"], cw.get("interval"), side)
    key_dup = position_gate_state.get("key_dup") or key_bar

    return {
        "aborted": False,
        "context_key": context_key,
        "key_bar": key_bar,
        "key_dup": key_dup,
        "lev": lev,
        "qty_est": qty_est,
        "reduce_only": reduce_only,
        "desired_ps": desired_ps,
        "signature": signature,
        "slot_key_tuple": slot_key_tuple,
        "trigger_labels": trigger_labels,
    }


def bind_strategy_signal_order_sizing_runtime(strategy_cls) -> None:
    strategy_signal_order_margin_runtime.bind_strategy_signal_order_margin_runtime(strategy_cls)
    strategy_signal_order_position_gate_runtime.bind_strategy_signal_order_position_gate_runtime(strategy_cls)
    strategy_signal_order_slot_runtime.bind_strategy_signal_order_slot_runtime(strategy_cls)
    strategy_cls._resolve_signal_order_account_state = _resolve_signal_order_account_state
    strategy_cls._prepare_futures_signal_order_state = _prepare_futures_signal_order_state
