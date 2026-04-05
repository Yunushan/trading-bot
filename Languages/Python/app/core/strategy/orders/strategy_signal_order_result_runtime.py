from __future__ import annotations

from datetime import datetime
import time


def _float_or(value, default=0.0):
    try:
        return float(value)
    except Exception:
        return default


def _abort_signal_order_guard(self, guard_key_symbol, signature_guard_key) -> None:
    with type(self)._SYMBOL_GUARD_LOCK:
        entry_guard = type(self)._SYMBOL_ORDER_STATE.get(guard_key_symbol)
        if isinstance(entry_guard, dict):
            pending_map = entry_guard.get("pending_map")
            if not isinstance(pending_map, dict):
                pending_map = {}
            pending_map.pop(signature_guard_key, None)
            entry_guard["pending_map"] = pending_map
            type(self)._SYMBOL_ORDER_STATE[guard_key_symbol] = entry_guard


def _handle_futures_signal_order_result(
    self,
    *,
    cw,
    side: str,
    order_res,
    trigger_labels,
    trigger_desc_for_order: str | None,
    order_event_uid: str,
    trigger_actions_for_order,
    current_bar_marker,
    bar_sig_key,
    sig_sorted,
    guard_claimed: bool,
    guard_key_symbol,
    signature_guard_key,
    guard_window: float,
    signature,
    context_key: str,
    slot_key_tuple,
    price: float,
    qty_est: float,
    lev,
) -> tuple[bool, object]:
    try:
        qty_emit = float(order_res.get("computed", {}).get("qty") or 0.0)
        if qty_emit <= 0:
            qty_emit = float(order_res.get("info", {}).get("origQty") or 0.0)
        info_meta_quick = order_res.get("info") or {}
        computed_meta_quick = order_res.get("computed") or {}
        fills_meta_quick = order_res.get("fills") or {}
        order_id_quick = None
        client_order_id_quick = None
        if isinstance(info_meta_quick, dict):
            order_id_quick = (
                info_meta_quick.get("orderId")
                or info_meta_quick.get("order_id")
                or info_meta_quick.get("orderID")
            )
            client_order_id_quick = (
                info_meta_quick.get("clientOrderId")
                or info_meta_quick.get("client_order_id")
                or info_meta_quick.get("clientOrderID")
            )
        if isinstance(computed_meta_quick, dict):
            order_id_quick = order_id_quick or computed_meta_quick.get("order_id") or computed_meta_quick.get("orderId")
            client_order_id_quick = client_order_id_quick or computed_meta_quick.get("client_order_id") or computed_meta_quick.get("clientOrderId")
        try:
            avg_price_quick = float(
                info_meta_quick.get("avgPrice")
                or computed_meta_quick.get("px")
                or cw.get("price")
                or 0.0
            )
        except Exception:
            avg_price_quick = float(cw.get("price") or 0.0)
        leverage_quick = None
        try:
            leverage_quick = float(
                info_meta_quick.get("leverage")
                or computed_meta_quick.get("lev")
                or cw.get("leverage")
                or 0.0
            )
        except Exception:
            leverage_quick = None
        if self.trade_cb:
            event_payload = {
                "symbol": cw["symbol"],
                "interval": cw.get("interval"),
                "side": side,
                "qty": qty_emit,
                "executed_qty": qty_emit,
                "price": cw.get("price"),
                "avg_price": avg_price_quick if avg_price_quick > 0.0 else cw.get("price"),
                "leverage": leverage_quick,
                "trigger_indicators": list(trigger_labels or []),
                "trigger_signature": list(signature or ()),
                "trigger_desc": str(trigger_desc_for_order or ""),
                "context_key": context_key,
                "event_uid": order_event_uid,
                "time": datetime.now().astimezone().strftime("%Y-%m-%d %H:%M:%S"),
                "status": "placed",
                "ok": bool(order_res.get("ok", True)),
            }
            if slot_key_tuple:
                try:
                    event_payload["slot_id"] = "|".join(slot_key_tuple)
                except Exception:
                    pass
            if trigger_actions_for_order:
                event_payload["trigger_actions"] = dict(trigger_actions_for_order)
            if order_id_quick is not None:
                event_payload["order_id"] = order_id_quick
            if client_order_id_quick is not None:
                event_payload["client_order_id"] = client_order_id_quick
            if fills_meta_quick:
                event_payload["fills_meta"] = {
                    "order_id": fills_meta_quick.get("order_id"),
                    "trade_count": fills_meta_quick.get("trade_count"),
                }
                commission_quick = fills_meta_quick.get("commission_usdt")
                if commission_quick is not None:
                    try:
                        event_payload["commission_usdt"] = float(commission_quick)
                    except Exception:
                        event_payload["commission_usdt"] = commission_quick
                realized_quick = fills_meta_quick.get("net_realized")
                if realized_quick is not None:
                    try:
                        event_payload["net_realized_usdt"] = float(realized_quick)
                    except Exception:
                        event_payload["net_realized_usdt"] = realized_quick
            self.trade_cb(event_payload)
    except Exception:
        pass

    order_ok = True
    qty_display = order_res.get("executedQty") or order_res.get("origQty") or qty_est
    try:
        try:
            if (not order_res.get("ok")) and callable(self.trade_cb):
                self.trade_cb(
                    {
                        "symbol": cw["symbol"],
                        "interval": cw.get("interval"),
                        "side": side,
                        "qty": float(order_res.get("computed", {}).get("qty") or 0.0),
                        "price": cw.get("price"),
                        "time": datetime.now().astimezone().strftime("%Y-%m-%d %H:%M:%S"),
                        "status": "error",
                        "ok": False,
                    }
                )
        except Exception:
            pass

        try:
            order_ok = bool(order_res.get("ok", True))
        except Exception:
            order_ok = True

        if order_ok:
            if current_bar_marker is not None:
                tracker = self._bar_order_tracker.setdefault(
                    bar_sig_key,
                    {"bar": current_bar_marker, "signatures": set()},
                )
                if tracker.get("bar") != current_bar_marker:
                    tracker["bar"] = current_bar_marker
                    tracker["signatures"] = set()
                tracker.setdefault("signatures", set()).add(sig_sorted)
                with type(self)._BAR_GUARD_LOCK:
                    global_tracker = type(self)._BAR_GLOBAL_SIGNATURES.setdefault(
                        bar_sig_key,
                        {"bar": current_bar_marker, "signatures": set()},
                    )
                    if global_tracker.get("bar") != current_bar_marker:
                        global_tracker["bar"] = current_bar_marker
                        global_tracker["signatures"] = set()
                    global_tracker.setdefault("signatures", set()).add(sig_sorted)
            success_ts = time.time()
            with type(self)._SYMBOL_GUARD_LOCK:
                entry_guard = type(self)._SYMBOL_ORDER_STATE.get(
                    guard_key_symbol,
                    {} if guard_claimed else None,
                )
                if isinstance(entry_guard, dict):
                    signatures_state = entry_guard.get("signatures")
                    if not isinstance(signatures_state, dict):
                        signatures_state = {}
                    signatures_state[signature_guard_key] = success_ts
                    entry_guard["signatures"] = signatures_state
                    pending_map = entry_guard.get("pending_map")
                    if not isinstance(pending_map, dict):
                        pending_map = {}
                    pending_map.pop(signature_guard_key, None)
                    entry_guard["pending_map"] = pending_map
                    entry_guard["last"] = success_ts
                    entry_guard["window"] = guard_window
                    type(self)._SYMBOL_ORDER_STATE[guard_key_symbol] = entry_guard
        else:
            failure_ts = time.time()
            with type(self)._SYMBOL_GUARD_LOCK:
                entry_guard = type(self)._SYMBOL_ORDER_STATE.get(guard_key_symbol)
                if isinstance(entry_guard, dict):
                    pending_map = entry_guard.get("pending_map")
                    if not isinstance(pending_map, dict):
                        pending_map = {}
                    pending_map.pop(signature_guard_key, None)
                    entry_guard["pending_map"] = pending_map
                    entry_guard["last"] = max(float(entry_guard.get("last") or 0.0), failure_ts)
                    type(self)._SYMBOL_ORDER_STATE[guard_key_symbol] = entry_guard

        key = (cw["symbol"], cw.get("interval"), side)
        if order_ok:
            qty = float(order_res.get("info", {}).get("origQty") or order_res.get("computed", {}).get("qty") or 0)
            exec_qty = self._order_field(order_res, "executedQty", "cumQty", "cumQuantity")
            if exec_qty is not None:
                try:
                    exec_qty_val = float(exec_qty)
                except Exception:
                    exec_qty_val = 0.0
                if exec_qty_val > 0.0:
                    qty = exec_qty_val
            if qty > 0:
                fills_info = order_res.get("fills") or {}
                entry_price_est = price
                try:
                    avg_px = (order_res.get("info", {}) or {}).get("avgPrice")
                    if avg_px:
                        entry_price_est = float(avg_px)
                    else:
                        computed_px = (order_res.get("computed", {}) or {}).get("px")
                        if computed_px:
                            entry_price_est = float(computed_px)
                except Exception:
                    entry_price_est = price
                qty_from_fills = _float_or(fills_info.get("filled_qty"))
                if qty_from_fills > 0:
                    qty = qty_from_fills
                avg_from_fills = _float_or(fills_info.get("avg_price"))
                if avg_from_fills > 0:
                    entry_price_est = avg_from_fills

                try:
                    leverage_val = int(order_res.get("info", {}).get("leverage") or 0)
                except Exception:
                    leverage_val = 0
                if leverage_val <= 0:
                    try:
                        leverage_val = int(order_res.get("computed", {}).get("lev") or 0)
                    except Exception:
                        leverage_val = 0
                if leverage_val <= 0:
                    try:
                        leverage_val = int(cw.get("leverage") or 0)
                    except Exception:
                        leverage_val = 0
                if leverage_val <= 0:
                    try:
                        leverage_val = int(self.config.get("leverage") or 0)
                    except Exception:
                        leverage_val = 0
                try:
                    margin_est = (entry_price_est * qty) / leverage_val if leverage_val > 0 else entry_price_est * qty
                except Exception:
                    margin_est = 0.0
                if margin_est <= 0.0:
                    margin_est = (price * qty) / max(leverage_val, 1)

                entry_fee_usdt = _float_or(fills_info.get("commission_usdt"))
                entry_net_realized = _float_or(fills_info.get("net_realized"))

                signature_list = list(signature or tuple(sorted(trigger_labels)))
                ledger_id = f"{key[0]}-{key[1]}-{key[2]}-{int(time.time()*1000)}"
                entry_payload = {
                    "qty": float(qty),
                    "timestamp": time.time(),
                    "entry_price": float(entry_price_est or price),
                    "leverage": leverage_val,
                    "margin_usdt": float(margin_est or 0.0),
                    "ledger_id": ledger_id,
                    "trigger_signature": signature_list,
                    "trigger_indicators": list(trigger_labels),
                    "trigger_desc": trigger_desc_for_order,
                    "context_key": context_key,
                    "event_uid": order_event_uid,
                }
                if trigger_actions_for_order:
                    entry_payload["trigger_actions"] = dict(trigger_actions_for_order)
                if slot_key_tuple:
                    try:
                        entry_payload["slot_id"] = "|".join(slot_key_tuple)
                    except Exception:
                        pass
                try:
                    sig_tokens = type(self)._normalize_signature_tokens_no_slots(signature_list)
                    if sig_tokens:
                        entry_payload["indicator_keys"] = list(sig_tokens)
                except Exception:
                    pass
                if entry_fee_usdt:
                    entry_payload["fees_usdt"] = float(entry_fee_usdt)
                    entry_payload["entry_fee_usdt"] = float(entry_fee_usdt)
                if entry_net_realized:
                    entry_payload["entry_realized_usdt"] = float(entry_net_realized)
                self._append_leg_entry(key, entry_payload)
                try:
                    qty_logged = _float_or(entry_payload.get("qty"))
                    price_logged = _float_or(entry_payload.get("entry_price") or price)
                    size_logged = qty_logged * price_logged if price_logged > 0.0 else 0.0
                    margin_logged = _float_or(entry_payload.get("margin_usdt") or margin_est)
                    indicator_label = (
                        trigger_desc_for_order.upper()
                        if isinstance(trigger_desc_for_order, str) and trigger_desc_for_order.strip()
                        else "-"
                    )
                    self.log(
                        f"{cw['symbol']}@{cw['interval']} OPEN {side}: qty={qty_logged:.6f}, "
                        f"size?{size_logged:.2f} USDT, margin?{margin_logged:.2f} USDT "
                        f"(context={indicator_label})."
                    )
                except Exception:
                    pass
    except Exception:
        pass

    return order_ok, qty_display


def _emit_signal_order_info(
    self,
    *,
    cw,
    side: str,
    order_res,
    price: float,
    qty_display,
    trigger_labels,
    trigger_desc_for_order: str | None,
    trigger_signature,
    context_key: str | None,
    order_event_uid: str,
    trigger_actions_for_order,
    origin_timestamp: float | None,
    slot_key_tuple=None,
    leverage_used=None,
) -> None:
    try:
        avg_price = float((order_res.get("info", {}) or {}).get("avgPrice") or 0.0)
    except Exception:
        avg_price = 0.0
    fills_info = order_res.get("fills") or {}
    if fills_info:
        try:
            avg_from_fills = float(fills_info.get("avg_price") or 0.0)
            if avg_from_fills > 0.0:
                avg_price = avg_from_fills
        except Exception:
            pass
    try:
        executed_qty = float(
            (order_res.get("info", {}) or {}).get("executedQty")
            or (order_res.get("info", {}) or {}).get("origQty")
            or (order_res.get("computed", {}) or {}).get("qty")
            or qty_display
            or 0.0
        )
    except Exception:
        try:
            executed_qty = float(qty_display or 0.0)
        except Exception:
            executed_qty = 0.0
    if fills_info:
        try:
            fill_qty = float(fills_info.get("filled_qty") or 0.0)
            if fill_qty > 0.0:
                executed_qty = fill_qty
        except Exception:
            pass
    qty_numeric = executed_qty if executed_qty else float(qty_display or 0.0)
    leverage_normalized = None
    if leverage_used is not None:
        try:
            leverage_normalized = int(leverage_used)
        except Exception:
            leverage_normalized = leverage_used
    order_info = {
        "symbol": cw["symbol"],
        "interval": cw["interval"],
        "side": side,
        "qty": qty_numeric,
        "executed_qty": qty_numeric,
        "price": price,
        "avg_price": avg_price if avg_price > 0 else price,
        "leverage": leverage_normalized,
        "trigger_indicators": trigger_labels,
        "trigger_signature": list(trigger_signature or ()),
        "trigger_desc": trigger_desc_for_order,
        "event_uid": order_event_uid,
        "time": datetime.now().astimezone().strftime("%Y-%m-%d %H:%M:%S"),
        "status": "placed",
        "ok": bool(order_res.get("ok", True)),
    }
    if context_key:
        order_info["context_key"] = context_key
    if slot_key_tuple:
        try:
            order_info["slot_id"] = "|".join(slot_key_tuple)
        except Exception:
            pass
    if trigger_actions_for_order:
        order_info["trigger_actions"] = dict(trigger_actions_for_order)
    info_meta = order_res.get("info") or {}
    computed_meta = order_res.get("computed") or {}
    order_id_value = None
    client_order_id_value = None
    if isinstance(info_meta, dict):
        order_id_value = info_meta.get("orderId") or info_meta.get("order_id") or info_meta.get("orderID")
        client_order_id_value = info_meta.get("clientOrderId") or info_meta.get("client_order_id") or info_meta.get("clientOrderID")
    if isinstance(computed_meta, dict):
        order_id_value = order_id_value or computed_meta.get("order_id") or computed_meta.get("orderId")
        client_order_id_value = client_order_id_value or computed_meta.get("client_order_id") or computed_meta.get("clientOrderId")
    if order_id_value is not None:
        order_info["order_id"] = order_id_value
    if client_order_id_value is not None:
        order_info["client_order_id"] = client_order_id_value
    if fills_info:
        commission_val = fills_info.get("commission_usdt")
        net_realized_val = fills_info.get("net_realized")
        if commission_val is not None:
            try:
                order_info["commission_usdt"] = float(commission_val)
            except Exception:
                order_info["commission_usdt"] = commission_val
        if net_realized_val is not None:
            try:
                order_info["net_realized_usdt"] = float(net_realized_val)
            except Exception:
                order_info["net_realized_usdt"] = net_realized_val
        order_info["fills_meta"] = {
            "order_id": fills_info.get("order_id"),
            "trade_count": fills_info.get("trade_count"),
        }
    if self.trade_cb:
        self.trade_cb(order_info)
    order_ok = True
    if isinstance(order_res, dict):
        order_ok = bool(order_res.get("ok", True))
    if origin_timestamp is not None and order_ok:
        latency = max(0.0, time.time() - float(origin_timestamp))
        self._log_latency_metric(cw["symbol"], cw["interval"], side, latency)
    self.log(f"{cw['symbol']}@{cw['interval']} Order placed: {order_res}")


def bind_strategy_signal_order_result_runtime(strategy_cls) -> None:
    strategy_cls._abort_signal_order_guard = _abort_signal_order_guard
    strategy_cls._handle_futures_signal_order_result = _handle_futures_signal_order_result
    strategy_cls._emit_signal_order_info = _emit_signal_order_info
