from __future__ import annotations


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
    px = float(price if price is not None else (self.get_last_price(sym) or 0.0))
    if px <= 0:
        return {"ok": False, "error": "No price available"}
    qty = float(quantity or 0.0)
    if side.upper() == "BUY" and use_quote:
        qamt = float(quote_amount or 0.0)
        if qamt <= 0:
            return {"ok": False, "error": "quote_amount<=0"}
        qty = qamt / px
    filters = self.get_spot_symbol_filters(sym)
    step = float(filters.get("stepSize", 0.0) or 0.0)
    min_qty = float(filters.get("minQty", 0.0) or 0.0)
    min_notional = float(filters.get("minNotional", 0.0) or 0.0)
    if step > 0:
        qty = self._floor_to_step(qty, step)
    if min_qty > 0 and qty < min_qty:
        qty = min_qty
        if step > 0:
            qty = self._floor_to_step(qty, step)
    if min_notional > 0 and (qty * px) < min_notional:
        needed = min_notional / px
        qty = needed
        if step > 0:
            qty = self._floor_to_step(qty, step)
    try:
        res = self.client.create_order(symbol=sym, side=side.upper(), type="MARKET", quantity=str(qty))
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
    if qty <= 0:
        return 0.0, "qty<=0"
    try:
        filters = self.get_spot_symbol_filters(symbol)
    except Exception as exc:
        return 0.0, f"filters_error:{exc}"

    step = filters["stepSize"] or 0.0
    min_qty = filters["minQty"] or 0.0
    min_notional = filters["minNotional"] or 0.0

    adj = qty
    if step > 0:
        adj = self._floor_to_step(adj, step)

    if min_qty > 0 and adj < min_qty:
        adj = min_qty
    if min_notional > 0 and (est_price or 0) > 0:
        needed = min_notional / float(est_price)
        if adj < needed:
            adj = needed
        adj = min_qty
        if step > 0:
            adj = self._floor_to_step(adj, step)

    if est_price and min_notional > 0:
        notional = adj * est_price
        if notional < min_notional:
            needed_qty = (min_notional / est_price) if est_price > 0 else adj
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
    step = float(filters.get("stepSize", 0.0) or 0.0)
    min_qty = float(filters.get("minQty", 0.0) or 0.0)
    min_notional = float(filters.get("minNotional", 0.0) or 0.0)

    adj = float(qty or 0.0)
    if step > 0:
        adj = self._floor_to_step(adj, step)
    if min_qty > 0 and adj < min_qty:
        adj = min_qty
    if min_notional > 0 and (price or 0) > 0:
        need = float(min_notional) / float(price)
        if step > 0:
            need = self._ceil_to_step(need, step)
        if adj < need:
            adj = need
    if adj <= 0:
        return 0.0, "adj<=0"
    return float(adj), None


def bind_binance_order_sizing_runtime(wrapper_cls) -> None:
    wrapper_cls.required_percent_for_symbol = required_percent_for_symbol
    wrapper_cls.place_spot_market_order = place_spot_market_order
    wrapper_cls._ceil_to_step = _ceil_to_step
    wrapper_cls._floor_to_step = staticmethod(_floor_to_step)
    wrapper_cls.floor_to_decimals = staticmethod(floor_to_decimals)
    wrapper_cls.ceil_to_decimals = staticmethod(ceil_to_decimals)
    wrapper_cls.adjust_qty_to_filters_spot = adjust_qty_to_filters_spot
    wrapper_cls.adjust_qty_to_filters_futures = adjust_qty_to_filters_futures
