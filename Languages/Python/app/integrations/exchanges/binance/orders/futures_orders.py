from __future__ import annotations

import logging
import math
from collections.abc import Mapping

from app.settings.live_safety import is_live_trading_mode
from app.settings.risk import coerce_bool

from .order_audit_runtime import audit_order_method

LOGGER = logging.getLogger(__name__)


def _finite_float(value: object) -> float | None:
    try:
        candidate = float(value)
    except (TypeError, ValueError):
        return None
    return candidate if math.isfinite(candidate) else None


def _normalize_futures_order_side(value: object) -> str | None:
    side = str(value or "").strip().upper()
    if side in {"BUY", "LONG", "L"}:
        return "BUY"
    if side in {"SELL", "SHORT", "S"}:
        return "SELL"
    return None


def _normalize_futures_leverage(value: object) -> int | None:
    candidate = _finite_float(value)
    if candidate is None or candidate <= 0.0 or not candidate.is_integer():
        return None
    return int(candidate)


def _validated_futures_order_filters(
    wrapper,
    symbol: str,
    *,
    allow_step_size_alias: bool = False,
) -> tuple[float, float, float]:
    filters = wrapper.get_futures_symbol_filters(symbol) or {}
    if not isinstance(filters, Mapping):
        raise ValueError("invalid futures symbol filter response")

    def parse_filter(key: str, raw_value: object, default: float) -> float:
        parsed = _finite_float(raw_value)
        if raw_value in (None, "") or parsed == 0.0:
            return default
        if parsed is None or parsed < 0.0:
            raise ValueError(f"{key} must be a finite non-negative number")
        return parsed

    raw_step = filters.get("stepSize")
    if allow_step_size_alias and raw_step in (None, "", 0, 0.0):
        raw_step = filters.get("step_size")
    step = parse_filter("stepSize", raw_step, 0.001)
    min_qty = parse_filter("minQty", filters.get("minQty"), step)
    min_notional = parse_filter("minNotional", filters.get("minNotional"), 5.0)
    return step, min_qty, min_notional


def place_futures_market_order(
    self,
    symbol: str,
    side: str,
    percent_balance: float | None = None,
    price: float | None = None,
    position_side: str | None = None,
    quantity: float | None = None,
    **kwargs,
):
    """Futures MARKET order with robust sizing and clear returns."""
    assert self.account_type == "FUTURES", "Futures order called while account_type != FUTURES"

    sym = (symbol or "").upper()
    side_up = _normalize_futures_order_side(side)
    if side_up is None:
        return {"ok": False, "symbol": sym, "error": f"Unsupported futures order side: {side!r}"}
    requested_leverage = kwargs.get("leverage")
    leverage_input = requested_leverage if requested_leverage is not None else getattr(self, "_futures_leverage", 1) or 1
    lev = _normalize_futures_leverage(leverage_input)
    if lev is None:
        return {"ok": False, "symbol": sym, "error": f"Bad leverage: {leverage_input!r}"}
    fast_mode = bool(getattr(self, "_fast_order_mode", False))
    self._ensure_margin_and_leverage_or_block(
        sym,
        kwargs.get("margin_mode") or getattr(self, "_default_margin_mode", "ISOLATED"),
        lev,
    )

    def _floor_to_step_local(val: float, step: float) -> float:
        try:
            if step <= 0:
                return float(val)
            q = int(round(float(val) / float(step)))
            return float(q * float(step))
        except Exception:
            return float(val)

    def _ceil_to_step_local(val: float, step: float) -> float:
        try:
            if step <= 0:
                return float(val)
            q = int(-(-float(val) // float(step)))
            return float(q * float(step))
        except Exception:
            return float(val)

    px = _finite_float(price if price is not None else (self.get_last_price(sym) or 0.0))
    if px is None or px <= 0:
        return {"ok": False, "error": "No price available", "computed": {}}

    try:
        step, min_qty, min_notional = _validated_futures_order_filters(self, sym)
    except Exception as exc:
        return {"ok": False, "symbol": sym, "error": f"futures symbol filters unavailable: {exc}"}

    mode = "percent"
    pct = _finite_float(percent_balance) if percent_balance is not None else 0.0
    if pct is None:
        return {"ok": False, "symbol": sym, "error": f"Bad percent balance: {percent_balance!r}"}
    qty = 0.0

    if pct > 0.0:
        bal = float(self.get_futures_available_balance() or 0.0)
        margin_budget = bal * (pct / 100.0)
        try:
            used_usd = 0.0
            positions = None
            if fast_mode:
                try:
                    positions = self._get_cached_futures_positions(max_age=8.0)
                except Exception:
                    positions = None
            if positions is None:
                positions = self.list_open_futures_positions()
            if not isinstance(positions, (list, tuple)):
                raise RuntimeError("futures position snapshot unavailable")
            for pos in positions:
                if (pos or {}).get("symbol", "").upper() == sym:
                    used_usd += float(
                        pos.get("isolatedWallet")
                        or pos.get("initialMargin")
                        or (abs(pos.get("notional") or 0.0) / max(lev, 1))
                    )
            margin_budget = max(margin_budget - used_usd, 0.0)
        except Exception as exc:
            if is_live_trading_mode(getattr(self, "mode", "")):
                return {
                    "ok": False,
                    "symbol": sym,
                    "error": "unable to verify current futures exposure; live order blocked",
                    "computed": {
                        "px": px,
                        "pct_used": pct,
                        "lev": lev,
                        "avail": bal,
                        "margin_budget": margin_budget,
                    },
                    "mode": "percent(exposure-unverified)",
                }
            try:
                self._log(
                    f"Futures exposure lookup failed; sizing from available balance only: {type(exc).__name__}: {exc}",
                    lvl="warn",
                )
            except Exception:
                # Sizing remains available in demo mode even when the optional
                # diagnostic sink is unavailable.
                LOGGER.debug("Could not record demo exposure lookup diagnostic", exc_info=True)

        qty = _floor_to_step_local((margin_budget * lev) / px, step)
        need_qty = max(min_qty, _ceil_to_step_local(min_notional / px, step))
        if qty < need_qty:
            req_pct = self.required_percent_for_symbol(sym, lev)
            return {
                "ok": False,
                "symbol": sym,
                "error": f"exchange minimum requires ~{req_pct:.2f}% (> {pct:.2f}%)",
                "computed": {
                    "px": px,
                    "minQty": min_qty,
                    "minNotional": min_notional,
                    "step": step,
                    "pct_used": pct,
                    "need_qty": need_qty,
                    "lev": lev,
                    "avail": bal,
                    "margin_budget": margin_budget,
                },
                "required_percent": req_pct,
                "mode": "percent(strict)",
            }
        mode = "percent"
    elif quantity is not None:
        qty_override = _finite_float(quantity)
        if qty_override is None:
            return {"ok": False, "error": f"Bad quantity override: {quantity!r}"}
        qty = qty_override
        qty = max(min_qty, _floor_to_step_local(qty, step))
        if qty * px < min_notional:
            qty = max(qty, _ceil_to_step_local(min_notional / px, step))
        mode = "quantity"
    else:
        qty = max(min_qty, _ceil_to_step_local(min_notional / px, step))
        mode = "fallback"

    if qty <= 0:
        return {
            "ok": False,
            "error": "qty<=0",
            "computed": {"px": px, "minQty": min_qty, "minNotional": min_notional, "step": step},
            "mode": mode,
        }

    try:
        dual = bool(getattr(self, "_futures_dual_side", False) or self.get_futures_dual_side())
        pos_side = position_side or kwargs.get("positionSide")
        if dual and not pos_side:
            pos_side = "SHORT" if side_up == "SELL" else "LONG"

        qty_str = self._format_quantity_for_order(qty, step)
        params = dict(symbol=sym, side=side_up, type="MARKET", quantity=qty_str)
        if dual and pos_side:
            params["positionSide"] = pos_side

        order, order_via = self._futures_create_order_with_fallback(params)
        fills_summary = {}
        if not fast_mode:
            try:
                fills_summary = self._summarize_futures_order_fills(sym, (order or {}).get("orderId"))
            except Exception:
                fills_summary = {}
        if isinstance(order, dict) and fills_summary:
            try:
                if not float(order.get("avgPrice") or 0.0) and float(fills_summary.get("avg_price") or 0.0):
                    order["avgPrice"] = fills_summary.get("avg_price")
            except Exception:
                pass
        self._invalidate_futures_positions_cache()
        result = {
            "ok": True,
            "info": order,
            "computed": {
                "qty": qty,
                "px": px,
                "step": step,
                "minQty": min_qty,
                "minNotional": min_notional,
                "lev": lev,
            },
            "mode": mode,
        }
        if order_via != "primary":
            result["via"] = order_via
        if fills_summary:
            result["fills"] = fills_summary
        return result
    except Exception as exc:
        return {
            "ok": False,
            "error": str(exc),
            "computed": {
                "qty": qty,
                "px": px,
                "step": step,
                "minQty": min_qty,
                "minNotional": min_notional,
                "lev": lev,
            },
            "mode": mode,
        }


def _floor_to_step(value: float, step: float) -> float:
    try:
        if step and step > 0:
            n = int(float(value) / float(step) + 1e-12)
            return float(n) * float(step)
    except Exception:
        pass
    return float(value or 0.0)


def _place_futures_market_order_STRICT(
    self,
    symbol: str,
    side: str,
    percent_balance: float | None = None,
    price: float | None = None,
    position_side: str | None = None,
    quantity: float | None = None,
    **kwargs,
):
    """Strict futures order sizer that skips instead of auto-bumping."""
    sym = (symbol or "").upper()
    side_up = _normalize_futures_order_side(side)
    if side_up is None:
        return {"ok": False, "symbol": sym, "error": f"Unsupported futures order side: {side!r}", "mode": "strict"}
    requested_leverage = kwargs.get("leverage")
    leverage_input = requested_leverage if requested_leverage is not None else getattr(self, "_default_leverage", 5) or 5
    lev_requested = _normalize_futures_leverage(leverage_input)
    if lev_requested is None:
        return {"ok": False, "symbol": sym, "error": f"Bad leverage: {leverage_input!r}", "mode": "strict"}
    try:
        self._ensure_symbol_margin(
            sym,
            kwargs.get("margin_mode") or getattr(self, "_default_margin_mode", "ISOLATED"),
            lev_requested,
        )
    except Exception as exc:
        self._log(f"BLOCK strict path: {type(exc).__name__}: {exc}", lvl="error")
        return {"ok": False, "error": str(exc), "mode": "strict"}

    ensure_err = None
    try:
        self.ensure_futures_settings(sym, leverage=lev_requested, margin_mode=kwargs.get("margin_mode"))
    except Exception as exc:
        ensure_err = str(exc)
    if ensure_err:
        return {"ok": False, "symbol": sym, "error": ensure_err}

    px = _finite_float(price if price is not None else self.get_last_price(sym) or 0.0)
    if px is None or px <= 0.0:
        return {"ok": False, "symbol": sym, "error": "No price available"}

    try:
        step, min_qty, min_notional = _validated_futures_order_filters(
            self,
            sym,
            allow_step_size_alias=True,
        )
    except Exception as exc:
        return {"ok": False, "symbol": sym, "error": f"futures symbol filters unavailable: {exc}", "mode": "strict"}

    dual = bool(getattr(self, "_futures_dual_side", False) or self.get_futures_dual_side())

    quantity_value = _finite_float(quantity) if quantity is not None else None
    if quantity is not None and quantity_value is None:
        return {"ok": False, "symbol": sym, "error": f"Bad quantity override: {quantity!r}", "mode": "strict"}
    percent_value = _finite_float(percent_balance) if percent_balance is not None else None
    if percent_balance is not None and percent_value is None:
        return {"ok": False, "symbol": sym, "error": f"Bad percent balance: {percent_balance!r}", "mode": "strict"}
    qty = float(quantity_value or 0.0)
    mode = "quantity"
    lev = self.clamp_futures_leverage(sym, lev_requested)
    if qty <= 0 and percent_balance is not None:
        mode = "percent(strict)"
        pct = float(percent_value)
        bal = float(self.get_futures_balance_usdt() or 0.0)
        margin_budget = bal * (pct / 100.0)
        notional_target = margin_budget * max(lev, 1)
        qty_raw = (notional_target / px) if px > 0 else 0.0
        qty = _floor_to_step(qty_raw, step)

        notional = qty * px
        need_notional = max(min_notional, min_qty * px)
        if qty < min_qty or notional < min_notional or notional < need_notional:
            denom = max(bal * max(lev, 1), 1e-12)
            req_pct = (need_notional / denom) * 100.0
            return {
                "ok": False,
                "symbol": sym,
                "error": f"exchange minimum requires ~{req_pct:.2f}% (> {pct:.2f}%)",
                "computed": {
                    "px": px,
                    "step": step,
                    "minQty": min_qty,
                    "minNotional": min_notional,
                    "need_qty": max(min_qty, need_notional / px),
                    "need_notional": need_notional,
                    "lev": lev,
                    "avail": bal,
                    "margin_budget": margin_budget,
                },
                "required_percent": req_pct,
                "mode": mode,
            }

    qty = _floor_to_step(qty, step)
    if qty <= 0:
        return {"ok": False, "symbol": sym, "error": "qty<=0", "computed": {"qty": qty, "px": px, "step": step, "lev": lev}}

    qty_str = self._format_quantity_for_order(qty, step)
    params = dict(symbol=sym, side=side_up, type="MARKET", quantity=qty_str)
    if bool(kwargs.get("reduce_only")):
        params["reduceOnly"] = True
    if dual:
        ps = position_side or kwargs.get("positionSide")
        if not ps:
            ps = "SHORT" if side_up == "SELL" else "LONG"
        params["positionSide"] = ps

    try:
        info, via = self._futures_create_order_with_fallback(params)
        self._invalidate_futures_positions_cache()
        res = {
            "ok": True,
            "info": info,
            "computed": {"qty": qty, "px": px, "step": step, "minQty": min_qty, "minNotional": min_notional, "lev": lev},
            "mode": mode,
        }
        if via and via != "primary":
            res["via"] = via
        return res
    except Exception as exc:
        return {"ok": False, "symbol": sym, "error": str(exc), "computed": {"qty": qty, "px": px, "step": step, "lev": lev}, "mode": mode}


def _place_futures_market_order_FLEX(
    self,
    symbol: str,
    side: str,
    percent_balance: float | None = None,
    price: float | None = None,
    position_side: str | None = None,
    quantity: float | None = None,
    **kwargs,
):
    """Flexible sizer that always tries to place the minimum legal order."""
    sym = (symbol or "").upper()
    side_up = _normalize_futures_order_side(side)
    if side_up is None:
        return {"ok": False, "symbol": sym, "error": f"Unsupported futures order side: {side!r}", "mode": "flex"}
    requested_leverage = kwargs.get("leverage")
    leverage_input = requested_leverage if requested_leverage is not None else getattr(self, "_default_leverage", 5) or 5
    desired_requested = _normalize_futures_leverage(leverage_input)
    if desired_requested is None:
        return {"ok": False, "symbol": sym, "error": f"Bad leverage: {leverage_input!r}", "mode": "flex"}
    pos_side = position_side or kwargs.get("positionSide") or None
    px = _finite_float(price if price is not None else (self.get_last_price(sym) or 0.0))
    if px is None or px <= 0:
        return {"ok": False, "symbol": sym, "error": "No price available"}

    quantity_value = _finite_float(quantity) if quantity is not None else None
    if quantity is not None and quantity_value is None:
        return {"ok": False, "symbol": sym, "error": f"Bad quantity override: {quantity!r}", "mode": "flex"}
    percent_value = _finite_float(percent_balance) if percent_balance is not None else None
    if percent_balance is not None and percent_value is None:
        return {"ok": False, "symbol": sym, "error": f"Bad percent balance: {percent_balance!r}", "mode": "flex"}

    desired_mm = kwargs.get("margin_mode") or getattr(self, "_default_margin_mode", "ISOLATED") or "ISOLATED"
    effective_lev = self.clamp_futures_leverage(sym, desired_requested)
    try:
        self._ensure_margin_and_leverage_or_block(sym, desired_mm, desired_requested)
    except Exception as exc:
        return {"ok": False, "symbol": sym, "error": f"enforce_settings_failed: {exc}", "mode": "flex"}

    try:
        step, min_qty, min_notional = _validated_futures_order_filters(self, sym)
    except Exception as exc:
        return {"ok": False, "symbol": sym, "error": f"futures symbol filters unavailable: {exc}", "mode": "flex"}

    dual = bool(getattr(self, "_futures_dual_side", False) or self.get_futures_dual_side())
    if dual and not pos_side:
        pos_side = "SHORT" if side_up == "SELL" else "LONG"

    def _floor_to_step_local(val: float, step_: float) -> float:
        try:
            if step_ <= 0:
                return float(val)
            import math
            return math.floor(float(val) / float(step_)) * float(step_)
        except Exception:
            return float(val)

    def _ceil_to_step_local(val: float, step_: float) -> float:
        try:
            if step_ <= 0:
                return float(val)
            import math
            return math.ceil(float(val) / float(step_)) * float(step_)
        except Exception:
            return float(val)

    min_qty_by_notional = _ceil_to_step_local(min_notional / px, step)
    min_legal_qty = max(min_qty, min_qty_by_notional)

    lev = max(1, int(effective_lev))
    reduce_only = bool(kwargs.get("reduce_only") or kwargs.get("reduceOnly") or False)

    mode = "quantity" if (quantity_value is not None and quantity_value > 0) else "percent"
    if quantity_value is not None and quantity_value > 0:
        qty = _floor_to_step_local(quantity_value, step)
    else:
        pct = max(float(percent_value or 0.0), 0.0)
        avail = float(self.get_futures_balance_usdt() or 0.0)
        margin_budget = avail * (pct / 100.0)
        target_notional = margin_budget * max(lev, 1)
        qty = _floor_to_step_local((target_notional / px) if px > 0 else 0.0, step)

        if qty < min_legal_qty:
            required_notional = max(min_notional, min_qty * px, min_legal_qty * px)
            required_margin = required_notional / max(lev, 1)
            required_percent = (required_notional / max(avail * max(lev, 1), 1e-12)) * 100.0
            max_auto_bump_percent = float(kwargs.get("max_auto_bump_percent", getattr(self, "_max_auto_bump_percent", 5.0)))
            percent_multiplier = float(
                kwargs.get("auto_bump_percent_multiplier", getattr(self, "_auto_bump_percent_multiplier", 10.0))
            )
            if percent_multiplier <= 0:
                percent_multiplier = 1.0
            self._max_auto_bump_percent = max_auto_bump_percent
            self._auto_bump_percent_multiplier = percent_multiplier
            if max_auto_bump_percent <= 0:
                allowed_percent = float("inf")
            else:
                allowed_percent = max(max_auto_bump_percent, pct * percent_multiplier)
            cushion = 1.01
            within_margin = (required_margin <= avail * cushion) and (not reduce_only)
            percent_ok = (allowed_percent == float("inf")) or (required_percent <= (allowed_percent + 1e-9))
            live_auto_bump_allowed = True
            if is_live_trading_mode(getattr(self, "mode", "")):
                cfg = getattr(self, "_live_safety_config", None)
                cfg = cfg if isinstance(cfg, dict) else {}
                live_auto_bump_allowed = bool(
                    coerce_bool(cfg.get("live_allow_auto_bump_to_min_order"), False)
                    or coerce_bool(kwargs.get("allow_live_auto_bump_to_min_order"), False)
                )
            if within_margin and percent_ok:
                if not live_auto_bump_allowed:
                    return {
                        "ok": False,
                        "symbol": sym,
                        "error": (
                            "live auto-bump to exchange minimum is disabled; increase position percent "
                            "or enable live_allow_auto_bump_to_min_order explicitly"
                        ),
                        "computed": {
                            "px": px,
                            "step": step,
                            "minQty": min_qty,
                            "minNotional": min_notional,
                            "need_qty": _ceil_to_step_local(required_notional / px, step),
                            "need_notional": required_notional,
                            "lev": lev,
                            "avail": avail,
                            "margin_budget": margin_budget,
                            "requested_percent": pct,
                        },
                        "required_percent": required_percent,
                        "mode": "percent(strict)",
                    }
                qty = _ceil_to_step_local(required_notional / px, step)
                mode = "percent(bumped_to_min)"
            else:
                limit_pct = None if (allowed_percent == float("inf") or not within_margin) else allowed_percent
                cap_note = ""
                if limit_pct is not None and not percent_ok:
                    cap_note = f" (cap {limit_pct:.2f}% / requested {pct:.2f}%)"
                return {
                    "ok": False,
                    "symbol": sym,
                    "error": f"insufficient funds for exchange minimum (~{required_percent:.2f}% needed){cap_note}",
                    "computed": {
                        "px": px,
                        "step": step,
                        "minQty": min_qty,
                        "minNotional": min_notional,
                        "need_qty": _ceil_to_step_local(required_notional / px, step),
                        "need_notional": required_notional,
                        "lev": lev,
                        "avail": avail,
                        "margin_budget": margin_budget,
                        "cap_percent": limit_pct,
                        "requested_percent": pct,
                    },
                    "required_percent": required_percent,
                    "mode": "percent(strict)",
                }

    qty = max(qty, min_legal_qty)
    qty = _floor_to_step_local(qty, step)
    if qty <= 0 and not reduce_only:
        return {"ok": False, "symbol": sym, "error": "qty<=0 after sizing"}

    qty_str = self._format_quantity_for_order(qty, step)
    params = dict(symbol=sym, side=side_up, type="MARKET", quantity=qty_str)
    if dual and pos_side:
        params["positionSide"] = pos_side
    if reduce_only and not (dual and pos_side):
        params["reduceOnly"] = True

    try:
        order, via = self._futures_create_order_with_fallback(params)
        self._invalidate_futures_positions_cache()
        res = {
            "ok": True,
            "info": order,
            "computed": {"qty": qty, "px": px, "step": step, "minQty": min_qty, "minNotional": min_notional, "lev": lev},
            "mode": mode,
        }
        if via and via != "primary":
            res["via"] = via
        return res
    except Exception as exc:
        return {"ok": False, "symbol": sym, "error": str(exc), "computed": {"qty": qty, "px": px, "step": step, "lev": lev}, "mode": mode}


def bind_binance_futures_orders(wrapper_cls, *, default_mode: str = "flex"):
    wrapper_cls._place_futures_market_order_BASE = place_futures_market_order
    wrapper_cls._place_futures_market_order_STRICT = _place_futures_market_order_STRICT
    wrapper_cls._place_futures_market_order_FLEX = _place_futures_market_order_FLEX

    mode = str(default_mode or "flex").strip().lower()
    if mode == "base":
        wrapper_cls.place_futures_market_order = audit_order_method(place_futures_market_order, market="futures")
    elif mode == "strict":
        wrapper_cls.place_futures_market_order = audit_order_method(_place_futures_market_order_STRICT, market="futures")
    else:
        wrapper_cls.place_futures_market_order = audit_order_method(_place_futures_market_order_FLEX, market="futures")
