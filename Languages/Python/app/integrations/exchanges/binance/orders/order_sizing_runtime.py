from __future__ import annotations

import math
from collections.abc import Mapping

from .order_audit_runtime import audit_order_method
from .order_fallback_runtime import _ensure_binance_client_order_id
from ..transport.helpers import _is_binance_error_payload


def _finite_float(value: object) -> float | None:
    try:
        candidate = float(value)
    except (TypeError, ValueError):
        return None
    return candidate if math.isfinite(candidate) else None


def _validated_spot_order_response(response: object) -> dict:
    """Return a verified spot-order acknowledgement or raise a rejection.

    A transport call returning without an exception is not sufficient evidence
    that Binance accepted an order.  In particular, wrappers may surface empty
    or error payloads as normal return values.  Do not mark the local intent as
    accepted until the response is an identifiable accepted order.
    """
    if response is None:
        raise RuntimeError("spot order rejected: empty response")
    if not isinstance(response, Mapping):
        raise RuntimeError("spot order rejected: malformed response")
    payload = dict(response)
    if not payload:
        raise RuntimeError("spot order rejected: empty response")
    error = payload.get("error")
    if isinstance(error, Mapping) and _is_binance_error_payload(dict(error)):
        code = error.get("code")
        message = error.get("msg") or error.get("message") or "order rejected"
        raise RuntimeError(f"spot order rejected (code={code}): {message}")
    if _is_binance_error_payload(payload):
        code = payload.get("code")
        message = payload.get("msg") or payload.get("message") or "order rejected"
        raise RuntimeError(f"spot order rejected (code={code}): {message}")
    success = payload.get("success")
    if isinstance(success, str):
        success = success.strip().lower() in {"true", "1", "yes"}
    if success is False:
        message = payload.get("msg") or payload.get("message") or "order rejected"
        raise RuntimeError(f"spot order rejected: {message}")
    nested = payload.get("data")
    if isinstance(nested, Mapping) and nested:
        payload = dict(nested)
    status = str(payload.get("status") or "").upper()
    if status in {"REJECTED", "EXPIRED", "CANCELED"}:
        message = payload.get("msg") or payload.get("message") or status.lower()
        raise RuntimeError(f"spot order rejected (status={status}): {message}")
    if not any(payload.get(key) for key in ("orderId", "order_id", "id")):
        raise RuntimeError("spot order rejected: response has no order identifier")
    return payload


def required_percent_for_symbol(self, symbol: str, leverage: int | float | None = None) -> float:
    try:
        sym = (symbol or "").upper()
        lev = float(
            leverage
            if leverage is not None
            else getattr(self, "futures_leverage", getattr(self, "_default_leverage", 5)) or 5
        )
        px = float(self.get_last_price(sym) or 0.0)
        filters = self.get_futures_symbol_filters(sym) or {}
        step = float(filters.get("stepSize") or 0.0) or 0.001
        min_qty = float(filters.get("minQty") or 0.0) or step
        min_notional = float(filters.get("minNotional") or 0.0) or 5.0
        need_qty = max(min_qty, (float(min_notional) / px) if px > 0 else 0.0)
        if step > 0 and need_qty > 0:
            k = int(need_qty / step)
            if abs(need_qty - k * step) > 1e-12:
                need_qty = (k + 1) * step
        if px <= 0 or lev <= 0 or need_qty <= 0:
            return 0.0
        margin_needed = (need_qty * px) / lev
        bal = float(self.futures_get_usdt_balance() or 0.0)
        if bal <= 0:
            return 0.0
        return (margin_needed / bal) * 100.0
    except Exception:
        return 0.0


def place_spot_market_order(
    self,
    symbol: str,
    side: str,
    quantity: float = 0.0,
    price: float | None = None,
    use_quote: bool = False,
    quote_amount: float | None = None,
    **kwargs,
):
    sym = symbol.upper()
    if self.account_type != "SPOT":
        return {"ok": False, "error": "account_type != SPOT"}
    side_up = str(side or "").strip().upper()
    if side_up not in {"BUY", "SELL"}:
        return {"ok": False, "error": f"Unsupported spot order side: {side!r}"}
    px = _finite_float(price if price is not None else (self.get_last_price(sym) or 0.0))
    if px is None or px <= 0:
        return {"ok": False, "error": "No price available"}
    qty = _finite_float(quantity) if quantity is not None else 0.0
    if qty is None:
        return {"ok": False, "error": "quantity must be a finite number"}
    if side_up == "BUY" and use_quote:
        qamt = _finite_float(quote_amount) if quote_amount is not None else 0.0
        if qamt is None or qamt <= 0:
            return {"ok": False, "error": "quote_amount<=0"}
        qty = qamt / px
    intent_started = False
    mark_unknown = None
    try:
        filters = self.get_spot_symbol_filters(sym) or {}
    except Exception as exc:
        return {
            "ok": False,
            "error": f"spot symbol filters unavailable for {sym}: {exc}",
            "computed": {
                "qty": qty,
                "price": px,
                "filters": {},
            },
        }
    if not isinstance(filters, Mapping):
        return {
            "ok": False,
            "error": f"spot symbol filters invalid for {sym}",
            "computed": {
                "qty": qty,
                "price": px,
                "filters": {},
            },
        }
    filter_values: dict[str, float] = {}
    for filter_key in ("stepSize", "minQty", "minNotional"):
        raw_value = filters.get(filter_key, 0.0)
        parsed_value = 0.0 if raw_value in (None, "") else _finite_float(raw_value)
        if parsed_value is None or parsed_value < 0.0:
            return {"ok": False, "error": f"spot symbol filter {filter_key} must be a finite non-negative number"}
        filter_values[filter_key] = parsed_value
    step = filter_values["stepSize"]
    min_qty = filter_values["minQty"]
    min_notional = filter_values["minNotional"]
    if step > 0:
        qty = self._floor_to_step(qty, step)
    if min_qty > 0 and qty < min_qty:
        qty = min_qty
        if step > 0:
            qty = self._floor_to_step(qty, step)
    if min_notional > 0 and (qty * px) < min_notional:
        needed = min_notional / px
        if step > 0:
            needed = self._ceil_to_step(needed, step)
        qty = max(needed, min_qty)
    params = _ensure_binance_client_order_id(
        dict(symbol=sym, side=side_up, type="MARKET", quantity=str(qty))
    )
    try:
        guard = getattr(self, "_guard_live_order_submit", None)
        if callable(guard):
            guard(market="spot", params=params, source="place_spot_market_order")
        begin_intent = getattr(self, "_begin_order_intent", None)
        mark_submitted = getattr(self, "_mark_order_intent_submitted", None)
        mark_accepted = getattr(self, "_mark_order_intent_accepted", None)
        mark_unknown = getattr(self, "_mark_order_intent_unknown", None)
        if callable(begin_intent):
            begin_intent(params, market="spot", source="place_spot_market_order")
            intent_started = True
        if callable(mark_submitted):
            mark_submitted(params, via="primary")
        res = _validated_spot_order_response(self.client.create_order(**params))
        if callable(mark_accepted) and intent_started:
            mark_accepted(params, via="primary", result=res)
        return {
            "ok": True,
            "info": res,
            "computed": {
                "qty": qty,
                "price": px,
                "filters": {"step": step, "minQty": min_qty, "minNotional": min_notional},
            },
        }
    except Exception as exc:
        if intent_started and callable(mark_unknown):
            mark_unknown(params, error=exc)
        return {
            "ok": False,
            "error": str(exc),
            "computed": {
                "qty": qty,
                "price": px,
                "filters": {"step": step, "minQty": min_qty, "minNotional": min_notional},
            },
        }


def _ceil_to_step(self, value: float, step: float) -> float:
    try:
        if step <= 0:
            return float(value)
        import math

        return math.ceil(float(value) / float(step)) * float(step)
    except Exception:
        return float(value)


def _floor_to_step(value: float, step: float) -> float:
    from decimal import Decimal, ROUND_DOWN

    if step <= 0:
        return float(value)
    d_val = Decimal(str(value))
    d_step = Decimal(str(step))
    units = (d_val / d_step).to_integral_value(rounding=ROUND_DOWN)
    snapped = units * d_step
    return float(snapped)


def floor_to_decimals(value: float, decimals: int) -> float:
    from decimal import Decimal, ROUND_DOWN

    if decimals < 0:
        return float(value)
    q = Decimal("1").scaleb(-decimals)
    return float(Decimal(str(value)).quantize(q, rounding=ROUND_DOWN))


def ceil_to_decimals(value: float, decimals: int) -> float:
    from decimal import Decimal, ROUND_UP

    if decimals < 0:
        return float(value)
    q = Decimal("1").scaleb(-decimals)
    return float(Decimal(str(value)).quantize(q, rounding=ROUND_UP))


def adjust_qty_to_filters_spot(self, symbol: str, qty: float, est_price: float):
    normalized_qty = _finite_float(qty)
    normalized_price = _finite_float(est_price)
    if normalized_qty is None:
        return 0.0, "qty must be a finite number"
    if normalized_price is None:
        return 0.0, "price must be a finite number"
    if normalized_qty <= 0:
        return 0.0, "qty<=0"
    try:
        filters = self.get_spot_symbol_filters(symbol)
    except Exception as exc:
        return 0.0, f"filters_error:{exc}"

    if not isinstance(filters, Mapping):
        return 0.0, "filters_error: invalid response"
    filter_values: dict[str, float] = {}
    for filter_key in ("stepSize", "minQty", "minNotional"):
        raw_value = filters.get(filter_key, 0.0)
        parsed_value = 0.0 if raw_value in (None, "") else _finite_float(raw_value)
        if parsed_value is None or parsed_value < 0.0:
            return 0.0, f"filters_error: {filter_key} must be a finite non-negative number"
        filter_values[filter_key] = parsed_value
    step = filter_values["stepSize"]
    min_qty = filter_values["minQty"]
    min_notional = filter_values["minNotional"]

    adj = normalized_qty
    if step > 0:
        adj = self._floor_to_step(adj, step)

    if min_qty > 0 and adj < min_qty:
        adj = min_qty
    if min_notional > 0 and normalized_price > 0:
        needed = min_notional / normalized_price
        if step > 0:
            needed = self._ceil_to_step(needed, step)
        if min_qty > 0:
            needed = max(needed, min_qty)
        if adj < needed:
            adj = needed

    if normalized_price > 0 and min_notional > 0:
        notional = adj * normalized_price
        if notional < min_notional:
            needed_qty = min_notional / normalized_price
            if step > 0:
                needed_qty = self._floor_to_step(needed_qty + step, step)
            if needed_qty < min_qty:
                needed_qty = min_qty
                if step > 0:
                    needed_qty = self._floor_to_step(needed_qty, step)
            adj = needed_qty
            if adj * est_price < min_notional:
                return 0.0, f"below_minNotional({adj*est_price:.8f}<{min_notional:.8f})"

    if adj <= 0:
        return 0.0, "adj<=0"
    return float(adj), None


def adjust_qty_to_filters_futures(self, symbol: str, qty: float, price: float | None = None):
    try:
        filters = self.get_futures_symbol_filters(symbol)
    except Exception as exc:
        return 0.0, f"filters_error:{exc}"
    if not isinstance(filters, Mapping):
        return 0.0, "filters_error: invalid response"
    normalized_qty = _finite_float(qty)
    normalized_price = 0.0 if price is None else _finite_float(price)
    if normalized_qty is None:
        return 0.0, "qty must be a finite number"
    if normalized_price is None:
        return 0.0, "price must be a finite number"
    filter_values: dict[str, float] = {}
    for filter_key in ("stepSize", "minQty", "minNotional"):
        raw_value = filters.get(filter_key, 0.0)
        parsed_value = 0.0 if raw_value in (None, "") else _finite_float(raw_value)
        if parsed_value is None or parsed_value < 0.0:
            return 0.0, f"filters_error: {filter_key} must be a finite non-negative number"
        filter_values[filter_key] = parsed_value
    step = filter_values["stepSize"]
    min_qty = filter_values["minQty"]
    min_notional = filter_values["minNotional"]

    adj = normalized_qty
    if step > 0:
        adj = self._floor_to_step(adj, step)
    if min_qty > 0 and adj < min_qty:
        adj = min_qty
    if min_notional > 0 and normalized_price > 0:
        need = min_notional / normalized_price
        if step > 0:
            need = self._ceil_to_step(need, step)
        if adj < need:
            adj = need
    if adj <= 0:
        return 0.0, "adj<=0"
    return float(adj), None


def bind_binance_order_sizing_runtime(wrapper_cls) -> None:
    wrapper_cls.required_percent_for_symbol = required_percent_for_symbol
    wrapper_cls.place_spot_market_order = audit_order_method(place_spot_market_order, market="spot")
    wrapper_cls._ceil_to_step = _ceil_to_step
    wrapper_cls._floor_to_step = staticmethod(_floor_to_step)
    wrapper_cls.floor_to_decimals = staticmethod(floor_to_decimals)
    wrapper_cls.ceil_to_decimals = staticmethod(ceil_to_decimals)
    wrapper_cls.adjust_qty_to_filters_spot = adjust_qty_to_filters_spot
    wrapper_cls.adjust_qty_to_filters_futures = adjust_qty_to_filters_futures
