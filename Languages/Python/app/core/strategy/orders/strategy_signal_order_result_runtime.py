from __future__ import annotations

from datetime import datetime
import logging
import math
import time

from app.security.redaction import redact_value


_LOGGER = logging.getLogger(__name__)


def _float_or(value, default=0.0):
    try:
        number = float(value)
    except (TypeError, ValueError, OverflowError):
        return default
    return number if math.isfinite(number) else default


def _int_or(value, default=0):
    try:
        return int(value)
    except (TypeError, ValueError, OverflowError):
        return default


def _safe_log(self, message: str, *, level: int = logging.WARNING) -> bool:
    callback = getattr(self, "log", None)
    if callable(callback):
        try:
            callback(message)
            return True
        except Exception:
            _LOGGER.exception("Signal order result log callback failed while reporting: %s", message)
            return False
    _LOGGER.log(level, message)
    return False


def _safe_trade_callback(self, payload: dict[str, object], *, context: str) -> bool:
    callback = getattr(self, "trade_cb", None)
    if callback is None:
        return True
    if not callable(callback):
        _LOGGER.error("Signal order %s callback is not callable", context)
        return False
    try:
        callback(payload)
        return True
    except Exception:
        _LOGGER.exception("Signal order %s callback failed", context)
        return False


def _slot_identifier(slot_key_tuple) -> str | None:
    if not slot_key_tuple:
        return None
    return "|".join(str(part) for part in slot_key_tuple)


def _pause_after_result_reconciliation_failure(self, message: str) -> None:
    cls = type(self)
    try:
        cls._GLOBAL_PAUSE.set()
    except Exception:
        cls._GLOBAL_PAUSE_FALLBACK = True
        _LOGGER.exception("%s; global pause event could not be set", message)
    _safe_log(self, f"{message}; trading paused pending account reconciliation.")


def _finalize_signal_order_guard(
    self,
    *,
    order_ok: bool,
    guard_claimed: bool,
    guard_key_symbol,
    signature_guard_key,
    guard_window: float,
) -> None:
    outcome_ts = time.time()
    with type(self)._SYMBOL_GUARD_LOCK:
        entry_guard = type(self)._SYMBOL_ORDER_STATE.get(
            guard_key_symbol,
            {} if order_ok or guard_claimed else None,
        )
        if not isinstance(entry_guard, dict):
            return
        pending_map = entry_guard.get("pending_map")
        if not isinstance(pending_map, dict):
            pending_map = {}
        pending_map.pop(signature_guard_key, None)
        entry_guard["pending_map"] = pending_map
        if order_ok:
            signatures_state = entry_guard.get("signatures")
            if not isinstance(signatures_state, dict):
                signatures_state = {}
            signatures_state[signature_guard_key] = outcome_ts
            entry_guard["signatures"] = signatures_state
            entry_guard["last"] = outcome_ts
            entry_guard["window"] = guard_window
        else:
            entry_guard["last"] = max(_float_or(entry_guard.get("last")), outcome_ts)
        type(self)._SYMBOL_ORDER_STATE[guard_key_symbol] = entry_guard


def _record_order_bar_signature(
    self,
    *,
    current_bar_marker,
    bar_sig_key,
    sig_sorted,
) -> None:
    if current_bar_marker is None:
        return
    tracker = self._bar_order_tracker.get(bar_sig_key)
    if not isinstance(tracker, dict) or tracker.get("bar") != current_bar_marker:
        tracker = {"bar": current_bar_marker, "signatures": set()}
        self._bar_order_tracker[bar_sig_key] = tracker
    signatures = tracker.get("signatures")
    if not isinstance(signatures, set):
        signatures = set()
        tracker["signatures"] = signatures
    signatures.add(sig_sorted)
    with type(self)._BAR_GUARD_LOCK:
        global_tracker = type(self)._BAR_GLOBAL_SIGNATURES.get(bar_sig_key)
        if not isinstance(global_tracker, dict) or global_tracker.get("bar") != current_bar_marker:
            global_tracker = {"bar": current_bar_marker, "signatures": set()}
            type(self)._BAR_GLOBAL_SIGNATURES[bar_sig_key] = global_tracker
        global_signatures = global_tracker.get("signatures")
        if not isinstance(global_signatures, set):
            global_signatures = set()
            global_tracker["signatures"] = global_signatures
        global_signatures.add(sig_sorted)


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
    if not isinstance(order_res, dict):
        _safe_log(self, f"Invalid futures order result for {cw.get('symbol')} {side}; expected an object.")
        try:
            _finalize_signal_order_guard(
                self,
                order_ok=False,
                guard_claimed=guard_claimed,
                guard_key_symbol=guard_key_symbol,
                signature_guard_key=signature_guard_key,
                guard_window=guard_window,
            )
        except Exception:
            _LOGGER.exception("Failed to finalize guard for malformed futures order result")
        return False, qty_est

    order_ok = bool(order_res.get("ok", True))
    qty_display = order_res.get("executedQty") or order_res.get("origQty") or qty_est
    info_meta = order_res.get("info") if isinstance(order_res.get("info"), dict) else {}
    computed_meta = order_res.get("computed") if isinstance(order_res.get("computed"), dict) else {}
    fills_meta = order_res.get("fills") if isinstance(order_res.get("fills"), dict) else {}

    qty_emit = _float_or(computed_meta.get("qty"))
    if qty_emit <= 0.0:
        qty_emit = _float_or(info_meta.get("executedQty") or info_meta.get("origQty"))
    order_id = info_meta.get("orderId") or info_meta.get("order_id") or info_meta.get("orderID")
    client_order_id = (
        info_meta.get("clientOrderId")
        or info_meta.get("client_order_id")
        or info_meta.get("clientOrderID")
    )
    order_id = order_id or computed_meta.get("order_id") or computed_meta.get("orderId")
    client_order_id = (
        client_order_id or computed_meta.get("client_order_id") or computed_meta.get("clientOrderId")
    )
    avg_price = _float_or(info_meta.get("avgPrice") or computed_meta.get("px") or cw.get("price"))
    leverage_quick = _float_or(
        info_meta.get("leverage") or computed_meta.get("lev") or cw.get("leverage"),
        None,
    )
    event_payload: dict[str, object] = {
        "symbol": cw["symbol"],
        "interval": cw.get("interval"),
        "side": side,
        "qty": qty_emit,
        "executed_qty": qty_emit,
        "price": cw.get("price"),
        "avg_price": avg_price if avg_price > 0.0 else cw.get("price"),
        "leverage": leverage_quick,
        "trigger_indicators": list(trigger_labels or []),
        "trigger_signature": list(signature or ()),
        "trigger_desc": str(trigger_desc_for_order or ""),
        "context_key": context_key,
        "event_uid": order_event_uid,
        "time": datetime.now().astimezone().strftime("%Y-%m-%d %H:%M:%S"),
        "status": "placed",
        "ok": order_ok,
    }
    slot_id = _slot_identifier(slot_key_tuple)
    if slot_id:
        event_payload["slot_id"] = slot_id
    if trigger_actions_for_order:
        event_payload["trigger_actions"] = dict(trigger_actions_for_order)
    if order_id is not None:
        event_payload["order_id"] = order_id
    if client_order_id is not None:
        event_payload["client_order_id"] = client_order_id
    if fills_meta:
        event_payload["fills_meta"] = {
            "order_id": fills_meta.get("order_id"),
            "trade_count": fills_meta.get("trade_count"),
        }
        if fills_meta.get("commission_usdt") is not None:
            event_payload["commission_usdt"] = _float_or(
                fills_meta.get("commission_usdt"),
                fills_meta.get("commission_usdt"),
            )
        if fills_meta.get("net_realized") is not None:
            event_payload["net_realized_usdt"] = _float_or(
                fills_meta.get("net_realized"),
                fills_meta.get("net_realized"),
            )
    _safe_trade_callback(self, event_payload, context="placed-event")

    if not order_ok:
        _safe_trade_callback(
            self,
            {
                "symbol": cw["symbol"],
                "interval": cw.get("interval"),
                "side": side,
                "qty": _float_or(computed_meta.get("qty")),
                "price": cw.get("price"),
                "time": datetime.now().astimezone().strftime("%Y-%m-%d %H:%M:%S"),
                "status": "error",
                "ok": False,
            },
            context="error-event",
        )

    try:
        _finalize_signal_order_guard(
            self,
            order_ok=order_ok,
            guard_claimed=guard_claimed,
            guard_key_symbol=guard_key_symbol,
            signature_guard_key=signature_guard_key,
            guard_window=guard_window,
        )
    except Exception as exc:
        _safe_log(self, f"Failed to finalize {cw['symbol']} {side} order guard: {exc}")
        if order_ok:
            _pause_after_result_reconciliation_failure(
                self,
                f"Successful {cw['symbol']} {side} order guard state is uncertain",
            )

    if not order_ok:
        return False, qty_display

    try:
        _record_order_bar_signature(
            self,
            current_bar_marker=current_bar_marker,
            bar_sig_key=bar_sig_key,
            sig_sorted=sig_sorted,
        )
    except Exception as exc:
        _safe_log(self, f"Failed to record {cw['symbol']} {side} bar signature: {exc}")

    key = (cw["symbol"], cw.get("interval"), side)
    try:
        qty = _float_or(info_meta.get("origQty") or computed_meta.get("qty"))
        exec_qty = self._order_field(order_res, "executedQty", "cumQty", "cumQuantity")
        exec_qty_value = _float_or(exec_qty)
        if exec_qty_value > 0.0:
            qty = exec_qty_value
        qty_from_fills = _float_or(fills_meta.get("filled_qty"))
        if qty_from_fills > 0.0:
            qty = qty_from_fills
        if qty <= 0.0:
            _pause_after_result_reconciliation_failure(
                self,
                f"Successful {cw['symbol']} {side} order has no positive executed quantity",
            )
            return True, qty_display

        entry_price_est = _float_or(info_meta.get("avgPrice") or computed_meta.get("px"), price)
        avg_from_fills = _float_or(fills_meta.get("avg_price"))
        if avg_from_fills > 0.0:
            entry_price_est = avg_from_fills
        if entry_price_est <= 0.0:
            entry_price_est = price

        leverage_val = _int_or(info_meta.get("leverage"))
        if leverage_val <= 0:
            leverage_val = _int_or(computed_meta.get("lev"))
        if leverage_val <= 0:
            leverage_val = _int_or(cw.get("leverage"))
        if leverage_val <= 0:
            leverage_val = _int_or(self.config.get("leverage"))
        margin_est = (entry_price_est * qty) / leverage_val if leverage_val > 0 else entry_price_est * qty
        if not math.isfinite(margin_est) or margin_est <= 0.0:
            margin_est = (price * qty) / max(leverage_val, 1)

        entry_fee_usdt = _float_or(fills_meta.get("commission_usdt"))
        entry_net_realized = _float_or(fills_meta.get("net_realized"))
        signature_list = list(signature or tuple(sorted(trigger_labels or [])))
        ledger_id = f"{key[0]}-{key[1]}-{key[2]}-{int(time.time() * 1000)}"
        entry_payload: dict[str, object] = {
            "qty": qty,
            "timestamp": time.time(),
            "entry_price": entry_price_est,
            "leverage": leverage_val,
            "margin_usdt": margin_est,
            "ledger_id": ledger_id,
            "trigger_signature": signature_list,
            "trigger_indicators": list(trigger_labels or []),
            "trigger_desc": trigger_desc_for_order,
            "context_key": context_key,
            "event_uid": order_event_uid,
        }
        if trigger_actions_for_order:
            entry_payload["trigger_actions"] = dict(trigger_actions_for_order)
        if slot_id:
            entry_payload["slot_id"] = slot_id
        try:
            sig_tokens = type(self)._normalize_signature_tokens_no_slots(signature_list)
        except Exception as exc:
            sig_tokens = ()
            _safe_log(self, f"Failed to normalize {cw['symbol']} {side} indicator signature: {exc}")
        if sig_tokens:
            entry_payload["indicator_keys"] = list(sig_tokens)
        if entry_fee_usdt:
            entry_payload["fees_usdt"] = entry_fee_usdt
            entry_payload["entry_fee_usdt"] = entry_fee_usdt
        if entry_net_realized:
            entry_payload["entry_realized_usdt"] = entry_net_realized

        self._append_leg_entry(key, entry_payload)
        qty_logged = _float_or(entry_payload.get("qty"))
        price_logged = _float_or(entry_payload.get("entry_price") or price)
        size_logged = qty_logged * price_logged if price_logged > 0.0 else 0.0
        margin_logged = _float_or(entry_payload.get("margin_usdt") or margin_est)
        indicator_label = (
            trigger_desc_for_order.upper()
            if isinstance(trigger_desc_for_order, str) and trigger_desc_for_order.strip()
            else "-"
        )
        _safe_log(
            self,
            f"{cw['symbol']}@{cw['interval']} OPEN {side}: qty={qty_logged:.6f}, "
            f"size?{size_logged:.2f} USDT, margin?{margin_logged:.2f} USDT "
            f"(context={indicator_label}).",
            level=logging.INFO,
        )
    except Exception as exc:
        _pause_after_result_reconciliation_failure(
            self,
            f"Successful {cw['symbol']} {side} order could not be recorded locally: {exc}",
        )

    return True, qty_display


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
    if not isinstance(order_res, dict):
        _safe_log(self, f"Cannot emit {cw.get('symbol')} {side} order info from malformed result.")
        return
    info_meta = order_res.get("info") if isinstance(order_res.get("info"), dict) else {}
    computed_meta = order_res.get("computed") if isinstance(order_res.get("computed"), dict) else {}
    fills_info = order_res.get("fills") if isinstance(order_res.get("fills"), dict) else {}
    avg_price = _float_or(info_meta.get("avgPrice"))
    if fills_info:
        avg_from_fills = _float_or(fills_info.get("avg_price"))
        if avg_from_fills > 0.0:
            avg_price = avg_from_fills
    executed_qty = _float_or(
        info_meta.get("executedQty")
        or info_meta.get("origQty")
        or computed_meta.get("qty")
        or qty_display
    )
    if fills_info:
        fill_qty = _float_or(fills_info.get("filled_qty"))
        if fill_qty > 0.0:
            executed_qty = fill_qty
    qty_numeric = executed_qty if executed_qty else _float_or(qty_display)
    leverage_normalized = None
    if leverage_used is not None:
        leverage_normalized = _int_or(leverage_used, leverage_used)
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
    slot_id = _slot_identifier(slot_key_tuple)
    if slot_id:
        order_info["slot_id"] = slot_id
    if trigger_actions_for_order:
        order_info["trigger_actions"] = dict(trigger_actions_for_order)
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
            order_info["commission_usdt"] = _float_or(commission_val, commission_val)
        if net_realized_val is not None:
            order_info["net_realized_usdt"] = _float_or(net_realized_val, net_realized_val)
        order_info["fills_meta"] = {
            "order_id": fills_info.get("order_id"),
            "trade_count": fills_info.get("trade_count"),
        }
    _safe_trade_callback(self, order_info, context="order-info")
    order_ok = True
    if isinstance(order_res, dict):
        order_ok = bool(order_res.get("ok", True))
    if origin_timestamp is not None and order_ok:
        origin_value = _float_or(origin_timestamp, None)
        if origin_value is None:
            _safe_log(self, f"Invalid {cw['symbol']} {side} order origin timestamp; latency omitted.")
        else:
            latency = max(0.0, time.time() - origin_value)
            try:
                self._log_latency_metric(cw["symbol"], cw["interval"], side, latency)
            except Exception as exc:
                _safe_log(self, f"Failed to record {cw['symbol']} {side} order latency: {exc}")
    try:
        redacted_result = redact_value(order_res)
    except Exception:
        redacted_result = "<order result unavailable>"
        _LOGGER.exception("Failed to redact signal order result")
    _safe_log(
        self,
        f"{cw['symbol']}@{cw['interval']} Order placed: {redacted_result}",
        level=logging.INFO,
    )


def bind_strategy_signal_order_result_runtime(strategy_cls) -> None:
    strategy_cls._abort_signal_order_guard = _abort_signal_order_guard
    strategy_cls._handle_futures_signal_order_result = _handle_futures_signal_order_result
    strategy_cls._emit_signal_order_info = _emit_signal_order_info
