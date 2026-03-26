from __future__ import annotations

import time

from . import strategy_cycle_risk_runtime

def run_once(self):
    ctx = self._build_cycle_context()
    if not ctx:
        return
    cw = ctx["cw"]
    now_ts = float(ctx["now_ts"])
    allow_opposite_enabled = bool(ctx["allow_opposite_enabled"])
    stop_enabled = bool(ctx["stop_enabled"])
    apply_usdt_limit = bool(ctx["apply_usdt_limit"])
    apply_percent_limit = bool(ctx["apply_percent_limit"])
    stop_usdt_limit = float(ctx["stop_usdt_limit"])
    stop_percent_limit = float(ctx["stop_percent_limit"])
    scope = str(ctx["scope"])
    account_type = str(ctx["account_type"])
    is_cumulative = bool(ctx["is_cumulative"])
    if self._apply_entire_account_stop_loss(ctx=ctx):
        return
    market_state = self._fetch_cycle_market_state(ctx=ctx)
    if not market_state:
        return
    df = market_state["df"]
    ind = market_state["ind"]
    signal = market_state["signal"]
    signal_timestamp = market_state["signal_timestamp"]
    trigger_desc = market_state["trigger_desc"]
    trigger_price = market_state["trigger_price"]
    trigger_sources = market_state["trigger_sources"]
    trigger_actions = market_state["trigger_actions"]
    trigger_segments = list(market_state.get("trigger_segments") or [])
    current_bar_marker = market_state["current_bar_marker"]
    last_rsi = market_state["last_rsi"]

    # Open-state via internal ledger (per symbol, interval, side)
    key_short = (cw['symbol'], cw.get('interval'), 'SELL')
    key_long  = (cw['symbol'], cw.get('interval'), 'BUY')
    short_open = bool(self._leg_ledger.get(key_short, {}).get('qty', 0) > 0)
    long_open  = bool(self._leg_ledger.get(key_long,  {}).get('qty', 0) > 0)

    dual_side = False
    desired_ps_long_guard = None
    desired_ps_short_guard = None
    if account_type == "FUTURES":
        try:
            dual_side = bool(self.binance.get_futures_dual_side())
        except Exception:
            dual_side = False
        desired_ps_long_guard = "LONG" if dual_side else None
        desired_ps_short_guard = "SHORT" if dual_side else None
    # In one-way mode, allow a new order to reduce/flip an opposite leg instead of skipping.
    hedge_overlap_allowed = bool(ctx["hedge_overlap_allowed"])

    risk_state = strategy_cycle_risk_runtime._apply_cycle_risk_management(
        self,
        ctx=ctx,
        cw=cw,
        df=df,
        account_type=account_type,
        allow_opposite_enabled=allow_opposite_enabled,
        dual_side=dual_side,
        desired_ps_long_guard=desired_ps_long_guard,
        desired_ps_short_guard=desired_ps_short_guard,
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
        last_rsi=last_rsi,
    )
    last_price = risk_state["last_price"]
    positions_cache = risk_state["positions_cache"]
    _load_positions_cache = risk_state["load_positions_cache"]
    long_open = bool(risk_state["long_open"])
    short_open = bool(risk_state["short_open"])
    indicator_order_requests, qty_tol_indicator = self._collect_indicator_order_requests(
        cw=cw,
        trigger_actions=trigger_actions,
        dual_side=dual_side,
        account_type=account_type,
        allow_opposite_enabled=allow_opposite_enabled,
        hedge_overlap_allowed=hedge_overlap_allowed,
        now_ts=now_ts,
    )
    indicator_order_requests = self._merge_flip_requests_into_indicator_orders(
        cw=cw,
        indicator_order_requests=indicator_order_requests,
        qty_tol_indicator=qty_tol_indicator,
    )
    market_state["last_price"] = last_price
    self._log_cycle_signal_summary(ctx=ctx, market_state=market_state)
    orders_to_execute, positions_cache, stop_requested = self._prepare_signal_orders(
        cw=cw,
        indicator_order_requests=indicator_order_requests,
        signal=signal,
        signal_timestamp=signal_timestamp,
        trigger_sources=trigger_sources,
        trigger_desc=trigger_desc,
        trigger_actions=trigger_actions,
        trigger_segments=trigger_segments,
        dual_side=dual_side,
        positions_cache=positions_cache,
        load_positions_cache=_load_positions_cache,
    )
    if stop_requested:
        return

    order_batch_total = len(orders_to_execute)
    order_batch_state = {"counter": 0, "total": order_batch_total}
    positions_cache_holder = {"value": positions_cache}

    for order in orders_to_execute:
        order_ts = order.get("timestamp")
        ts_float = None
        try:
            if order_ts is not None:
                ts_float = float(order_ts)
        except Exception:
            ts_float = None
        self._execute_signal_order(
            cw=cw,
            order_side=order.get("side"),
            indicator_labels=list(order.get("labels") or []),
            order_signature=tuple(order.get("signature") or ()),
            origin_timestamp=ts_float,
            flip_from_side=order.get("flip_from"),
            flip_qty=order.get("flip_qty"),
            flip_qty_target=order.get("flip_qty_target"),
            order_trigger_desc=order.get("trigger_desc"),
            order_trigger_actions=order.get("trigger_actions"),
            trigger_desc=trigger_desc,
            trigger_sources=trigger_sources,
            last_price=last_price,
            current_bar_marker=current_bar_marker,
            positions_cache_holder=positions_cache_holder,
            order_batch_state=order_batch_state,
        )

