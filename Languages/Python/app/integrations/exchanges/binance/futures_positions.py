from __future__ import annotations

import copy
import time
from decimal import Decimal, ROUND_DOWN

from .transport_helpers import _coerce_int


def _get_cached_futures_positions(self, max_age: float) -> list | None:
    if max_age is None or max_age <= 0:
        return None
    with self._positions_cache_lock:
        data = self._positions_cache
        ts = self._positions_cache_ts
    if data is None:
        return None
    if (time.time() - ts) > max_age:
        return None
    return copy.deepcopy(data)


def _store_futures_positions_cache(self, entries: list | None) -> None:
    with self._positions_cache_lock:
        self._positions_cache = copy.deepcopy(entries) if entries is not None else None
        self._positions_cache_ts = time.time() if entries is not None else 0.0


def _invalidate_futures_positions_cache(self) -> None:
    with self._positions_cache_lock:
        self._positions_cache = None
        self._positions_cache_ts = 0.0
    self._invalidate_futures_account_cache()


def _format_quantity_for_order(value: float, step: float | None = None) -> str:
    try:
        if value is None:
            return "0"
        quant = Decimal(str(value))
        if step and float(step) > 0:
            step_dec = Decimal(str(step))
            quant = quant.quantize(step_dec, rounding=ROUND_DOWN)
        quant = quant.normalize()
        text_value = format(quant, "f")
        text_value = text_value.rstrip("0").rstrip(".") if "." in text_value else text_value
        return text_value if text_value else "0"
    except Exception:
        try:
            return f"{float(value):.8f}".rstrip("0").rstrip(".")
        except Exception:
            return "0"


def _convert_asset_to_usdt(self, amount: float | str | None, asset: str | None) -> float:
    """Convert a commission amount into USDT using last price when needed."""
    try:
        value = float(amount or 0.0)
    except Exception:
        return 0.0
    if value == 0.0:
        return 0.0
    code = str(asset or "").upper()
    if not code:
        return value
    if code in {"USDT", "BUSD", "USD"}:
        return value
    try:
        px = float(self.get_last_price(f"{code}USDT") or 0.0)
        if px > 0.0:
            return value * px
    except Exception:
        pass
    return value


def _summarize_futures_order_fills(
    self,
    symbol: str,
    order_id: int | str | None,
    *,
    attempts: int = 2,
    delay: float = 0.2,
) -> dict:
    """Fetch fills for an order to expose realized PnL and commission totals."""
    sym = str(symbol or "").upper()
    if not sym or order_id is None:
        return {}
    try:
        oid = int(float(order_id))
    except Exception:
        return {}

    trades: list[dict] = []
    for attempt in range(max(1, attempts) + 1):
        try:
            self._throttle_request("/fapi/v1/userTrades")
            trades = self.client.futures_account_trades(symbol=sym, orderId=oid, limit=100) or []
        except Exception:
            trades = []
        if trades:
            break
        if attempt < attempts:
            try:
                time.sleep(max(0.0, float(delay)))
            except Exception:
                pass
    if not trades:
        return {}

    total_qty = 0.0
    total_quote = 0.0
    realized_pnl = 0.0
    commission_by_asset: dict[str, float] = {}
    for trade in trades:
        try:
            qty = abs(float(trade.get("qty") or 0.0))
        except Exception:
            qty = 0.0
        try:
            price = float(trade.get("price") or 0.0)
        except Exception:
            price = 0.0
        total_qty += qty
        total_quote += qty * price
        try:
            realized_pnl += float(trade.get("realizedPnl") or 0.0)
        except Exception:
            pass
        try:
            commission_val = float(trade.get("commission") or 0.0)
        except Exception:
            commission_val = 0.0
        asset = str(trade.get("commissionAsset") or "").upper() or "USDT"
        commission_by_asset[asset] = commission_by_asset.get(asset, 0.0) + commission_val

    avg_price = (total_quote / total_qty) if total_qty > 0 else 0.0
    commission_usdt = 0.0
    for asset, amount in commission_by_asset.items():
        commission_usdt += self._convert_asset_to_usdt(amount, asset)
    net_realized = realized_pnl - commission_usdt
    return {
        "order_id": oid,
        "filled_qty": total_qty,
        "avg_price": avg_price,
        "realized_pnl": realized_pnl,
        "commission_breakdown": commission_by_asset,
        "commission_usdt": commission_usdt,
        "net_realized": net_realized,
        "trade_count": len(trades),
    }


def get_futures_dual_side(self) -> bool:
    """
    Returns True if dual-side (hedge) mode is enabled on Futures; False if one-way.
    Tries multiple client methods; normalizes string/array responses.
    """
    try:
        cached = self._futures_dual_side_cache
        ts = self._futures_dual_side_cache_ts
    except Exception:
        cached = None
        ts = 0.0
    if cached is not None and (time.time() - ts) < 300.0:
        return bool(cached)
    methods = [
        "futures_get_position_mode",
        "futures_get_position_side_dual",
        "futures_position_side_dual",
    ]
    for method_name in methods:
        try:
            fn = getattr(self.client, method_name, None)
            if not fn:
                continue
            res = fn()
            val = None
            if isinstance(res, dict):
                val = res.get("dualSidePosition")
            elif isinstance(res, (list, tuple)) and res:
                first = res[0]
                if isinstance(first, dict) and "dualSidePosition" in first:
                    val = first["dualSidePosition"]
                else:
                    val = first
            else:
                val = res
            if isinstance(val, str):
                val = val.strip().lower() in ("true", "1", "yes", "y")
            result = bool(val)
            self._futures_dual_side_cache = result
            self._futures_dual_side_cache_ts = time.time()
            return result
        except Exception:
            continue
    self._futures_dual_side_cache = False
    self._futures_dual_side_cache_ts = time.time()
    return False


def close_futures_leg_exact(self, symbol: str, qty: float, side: str, position_side: str | None = None):
    """Close exactly `qty` using reduce-only MARKET on the given `side`."""
    try:
        sym = (symbol or "").upper()
        q = abs(float(qty or 0))
        if q <= 0:
            return {"ok": False, "error": "qty<=0"}
        side_up = str(side or "SELL").upper()
        if side_up in ("L", "LONG"):
            side_up = "BUY"
        elif side_up in ("S", "SHORT"):
            side_up = "SELL"
        if side_up not in ("BUY", "SELL"):
            return {"ok": False, "error": f"invalid side: {side!r}"}
        ps_norm = str(position_side or "").upper().strip() or None
        if ps_norm not in ("LONG", "SHORT"):
            ps_norm = None
        try:
            dual = bool(getattr(self, "_futures_dual_side", False) or self.get_futures_dual_side())
        except Exception:
            dual = bool(ps_norm)
        try:
            filters = self.get_futures_symbol_filters(sym) or {}
            step = float(filters.get("stepSize") or 0.0)
        except Exception:
            step = 0.0
        qty_tol = 1e-12

        def _normalize_row_side(raw_side: object) -> str:
            text = str(raw_side or "").upper().strip()
            if text in ("L", "LONG"):
                return "LONG"
            if text in ("S", "SHORT"):
                return "SHORT"
            return "BOTH" if text in ("", "BOTH") else text

        def _live_closeable_qty(preferred_ps: str | None) -> tuple[float, bool]:
            total = 0.0
            try:
                rows = self.list_open_futures_positions(max_age=0.0, force_refresh=True) or []
            except Exception:
                return 0.0, False
            for row in rows:
                if str(row.get("symbol") or "").upper() != sym:
                    continue
                try:
                    amt = float(row.get("positionAmt") or 0.0)
                except Exception:
                    amt = 0.0
                if abs(amt) <= qty_tol:
                    continue
                row_ps = _normalize_row_side(row.get("positionSide") or row.get("positionside"))
                include = False
                if preferred_ps in ("LONG", "SHORT"):
                    if row_ps == preferred_ps:
                        include = True
                    elif row_ps == "BOTH":
                        if preferred_ps == "LONG" and amt > 0:
                            include = True
                        elif preferred_ps == "SHORT" and amt < 0:
                            include = True
                else:
                    if side_up == "SELL":
                        if row_ps == "LONG":
                            include = True
                        elif row_ps == "BOTH" and amt > 0:
                            include = True
                    else:
                        if row_ps == "SHORT":
                            include = True
                        elif row_ps == "BOTH" and amt < 0:
                            include = True
                    if not include:
                        if side_up == "SELL" and amt > 0:
                            include = True
                        elif side_up == "BUY" and amt < 0:
                            include = True
                if include:
                    total += abs(amt)
            return max(total, 0.0), True

        def _coerce_order_qty(qty_value: float) -> tuple[float, str]:
            try:
                text = self._format_quantity_for_order(qty_value, step)
                q_norm = float(text or 0.0)
                if q_norm > qty_tol:
                    return q_norm, text
            except Exception:
                pass
            try:
                text = self._format_quantity_for_order(qty_value, 0.0)
                q_norm = float(text or 0.0)
                return q_norm, text
            except Exception:
                q_norm = max(0.0, float(qty_value or 0.0))
                return q_norm, f"{q_norm:.8f}"

        live_qty_preferred, known_preferred = _live_closeable_qty(ps_norm)
        live_qty_fallback, known_fallback = _live_closeable_qty(None)
        live_qty = live_qty_preferred if live_qty_preferred > qty_tol else live_qty_fallback
        if live_qty > qty_tol:
            q = min(q, live_qty)
        if q <= qty_tol:
            q = abs(float(qty or 0.0))
        if q <= qty_tol and (known_preferred or known_fallback):
            return {"ok": True, "skipped": True, "symbol": sym, "reason": "position already flat"}

        derived_ps = "LONG" if side_up == "SELL" else "SHORT"
        ps_attempts: list[str | None] = []
        if dual:
            if ps_norm in ("LONG", "SHORT"):
                ps_attempts.append(ps_norm)
            ps_attempts.append(derived_ps)
        ps_attempts.append(None)
        dedup_attempts: list[str | None] = []
        for candidate in ps_attempts:
            if candidate not in dedup_attempts:
                dedup_attempts.append(candidate)

        errors: list[str] = []
        for attempt_idx, ps_try in enumerate(dedup_attempts):
            if ps_try is not None and not dual:
                continue
            qty_cap, _ = _live_closeable_qty(ps_try)
            qty_try = q
            if qty_cap > qty_tol:
                qty_try = min(qty_try, qty_cap)
            if qty_try <= qty_tol:
                continue
            qty_send, qty_str = _coerce_order_qty(qty_try)
            if qty_send <= qty_tol:
                continue
            params = dict(symbol=sym, side=side_up, type="MARKET", quantity=qty_str)
            if ps_try:
                params["positionSide"] = ps_try
            else:
                params["reduceOnly"] = True
            try:
                params.setdefault("newClientOrderId", f"close-{sym}-{int(time.time() * 1000)}-{attempt_idx}")
            except Exception:
                pass
            try:
                info, via = self._futures_create_order_with_fallback(params)
            except Exception as exc:
                errors.append(f"{ps_try or 'reduceOnly'}: {exc}")
                continue
            fills_summary = {}
            try:
                fills_summary = self._summarize_futures_order_fills(sym, (info or {}).get("orderId"))
            except Exception:
                fills_summary = {}
            if isinstance(info, dict) and fills_summary:
                try:
                    if not float(info.get("avgPrice") or 0.0) and float(fills_summary.get("avg_price") or 0.0):
                        info["avgPrice"] = fills_summary.get("avg_price")
                except Exception:
                    pass
            self._invalidate_futures_positions_cache()
            res = {"ok": True, "info": info, "requested_qty": float(qty or 0.0), "sent_qty": qty_send}
            if ps_try:
                res["positionSide"] = ps_try
            if via and via != "primary":
                res["via"] = via
            if fills_summary:
                res["fills"] = fills_summary
            return res
        error_text = "; ".join(errors) if errors else "no close attempt matched open exposure"
        return {
            "ok": False,
            "error": error_text,
            "symbol": sym,
            "requested_qty": float(qty or 0.0),
            "position_side": ps_norm,
            "side": side_up,
        }
    except Exception as exc:
        return {"ok": False, "error": str(exc)}


def close_futures_position(self, symbol: str):
    """Close open futures position(s) for `symbol` using reduce-only MARKET orders."""
    try:
        sym = (symbol or "").upper()
        try:
            filters = self.get_futures_symbol_filters(sym) or {}
            step = float(filters.get("stepSize") or 0.0)
        except Exception:
            step = 0.0
        dual = bool(getattr(self, "_futures_dual_side", False) or self.get_futures_dual_side())
        rows = self.list_open_futures_positions(max_age=0.0, force_refresh=True) or []
        if not rows:
            try:
                raw_rows = self.client.futures_position_information(symbol=sym) or []
            except Exception:
                raw_rows = []
            for raw in raw_rows:
                try:
                    if str(raw.get("symbol") or "").upper() != sym:
                        continue
                    rows.append(
                        {
                            "symbol": str(raw.get("symbol") or "").upper(),
                            "positionAmt": float(raw.get("positionAmt") or 0.0),
                            "positionSide": str(raw.get("positionSide") or raw.get("positionside") or "BOTH").upper(),
                        }
                    )
                except Exception:
                    continue
        closed = 0
        failed = 0
        errors = []

        def _resolve_close(amt_val: float, raw_pos_side: object) -> tuple[str | None, str | None]:
            pos_side = str(raw_pos_side or "").upper().strip()
            if dual and pos_side in ("LONG", "SHORT"):
                return ("SELL" if pos_side == "LONG" else "BUY"), pos_side
            if amt_val > 0:
                return "SELL", ("LONG" if dual else None)
            if amt_val < 0:
                return "BUY", ("SHORT" if dual else None)
            return None, None

        for row in rows:
            if (row.get("symbol") or "").upper() != sym:
                continue
            amt = float(row.get("positionAmt") or 0)
            if abs(amt) < 1e-12:
                continue
            side, target_ps = _resolve_close(amt, row.get("positionSide") or row.get("positionside"))
            if side not in ("BUY", "SELL"):
                continue
            params = dict(symbol=sym, side=side, type="MARKET", quantity=self._format_quantity_for_order(abs(amt), step))
            if dual and target_ps in ("LONG", "SHORT"):
                params["positionSide"] = target_ps
            else:
                params["reduceOnly"] = True
            try:
                self._futures_create_order_with_fallback(params)
                self._invalidate_futures_positions_cache()
                closed += 1
            except Exception as exc:
                failed += 1
                errors.append(str(exc))
        if closed <= 0 and failed <= 0:
            return {
                "ok": False,
                "closed": 0,
                "failed": 0,
                "errors": ["no open positions found from close snapshot"],
                "symbol": sym,
            }
        return {"ok": failed == 0, "closed": closed, "failed": failed, "errors": errors}
    except Exception as exc:
        return {"ok": False, "error": str(exc)}


def cancel_all_open_futures_orders(self) -> dict:
    results: dict = {"ok": True, "canceled_symbols": 0, "errors": []}
    try:
        try:
            self.client.futures_cancel_all_open_orders()
            return results
        except Exception:
            pass
        orders = []
        try:
            orders = self.client.futures_get_open_orders() or []
        except Exception:
            orders = []
        symbols = set()
        for order in orders:
            try:
                sym = str(order.get("symbol") or "").upper()
            except Exception:
                sym = ""
            if sym:
                symbols.add(sym)
        if not symbols:
            try:
                positions = self.list_open_futures_positions(max_age=0.0, force_refresh=True) or []
                for pos in positions:
                    sym = str(pos.get("symbol") or "").upper()
                    if sym:
                        symbols.add(sym)
            except Exception:
                symbols = set()
        for sym in sorted(symbols):
            try:
                self.client.futures_cancel_all_open_orders(symbol=sym)
                results["canceled_symbols"] += 1
            except Exception as exc:
                results["ok"] = False
                results["errors"].append(f"{sym}: {exc}")
    except Exception as exc:
        return {"ok": False, "error": str(exc)}
    return results


def close_all_futures_positions(self):
    try:
        from .close_all import close_all_futures_positions as _close_all_futures_positions

        delegated = _close_all_futures_positions(self)
        return delegated if isinstance(delegated, list) else []
    except Exception:
        pass
    results = []
    try:
        dual = False
        try:
            mode_info = self.client.futures_get_position_mode()
            dual = bool(mode_info.get("dualSidePosition"))
        except Exception:
            pass
        positions = self.list_open_futures_positions(max_age=0.0, force_refresh=True) or []
        if not positions:
            return results
        try:
            for symbol in sorted({p["symbol"] for p in positions}):
                try:
                    self.client.futures_cancel_all_open_orders(symbol=symbol)
                except Exception:
                    pass
        except Exception:
            pass
        for pos in positions:
            try:
                sym = pos["symbol"]
                amt = float(pos.get("positionAmt") or 0.0)
                if abs(amt) <= 0.0:
                    continue
                raw_ps = str(pos.get("positionSide") or pos.get("positionside") or "").upper().strip()
                if dual and raw_ps in ("LONG", "SHORT"):
                    side = "SELL" if raw_ps == "LONG" else "BUY"
                    target_ps = raw_ps
                else:
                    side = "SELL" if amt > 0 else "BUY"
                    target_ps = ("LONG" if amt > 0 else "SHORT") if dual else None
                qty = abs(amt)
                try:
                    filters = self.get_futures_symbol_filters(sym) or {}
                    step = float(filters.get("stepSize") or 0.0)
                except Exception:
                    step = 0.0
                qty_str = self._format_quantity_for_order(qty, step)
                params = dict(symbol=sym, side=side, type="MARKET", quantity=qty_str)
                if dual and target_ps in ("LONG", "SHORT"):
                    params["positionSide"] = target_ps
                else:
                    params["reduceOnly"] = True
                info, via = self._futures_create_order_with_fallback(params)
                self._invalidate_futures_positions_cache()
                row = {"symbol": sym, "ok": True, "info": info}
                if via and via != "primary":
                    row["via"] = via
                results.append(row)
            except Exception as exc:
                results.append({"symbol": pos.get("symbol"), "ok": False, "error": str(exc)})
    except Exception as exc:
        results.append({"ok": False, "error": str(exc)})
    return results


def list_open_futures_positions(self, *, max_age: float = 1.5, force_refresh: bool = False):
    if force_refresh and bool(getattr(self, "_fast_order_mode", False)):
        try:
            fast_ttl = float(getattr(self, "_fast_positions_cache_ttl", 0.0) or 0.0)
        except Exception:
            fast_ttl = 0.0
        if fast_ttl > 0.0:
            max_age = max(float(max_age or 0.0), fast_ttl)
            force_refresh = False
    if not force_refresh:
        cached = self._get_cached_futures_positions(max_age)
        if cached is not None:
            return cached
    infos = None
    risk_infos = None
    try:
        risk_method = getattr(self.client, "futures_position_risk", None)
        if callable(risk_method):
            risk_infos = risk_method()
            infos = risk_infos
        else:
            infos = self.client.futures_position_information()
    except Exception:
        try:
            infos = self.client.futures_position_information()
        except Exception:
            infos = None
    risk_lookup = {}
    if risk_infos is None and infos is not None:
        risk_infos = infos
    if isinstance(risk_infos, list):
        for risk in risk_infos:
            try:
                sym = str(risk.get("symbol") or "").upper()
                if not sym:
                    continue
                side = str(risk.get("positionSide") or "BOTH").upper()
                risk_lookup[(sym, side)] = risk
                if side != "BOTH" and (sym, "BOTH") not in risk_lookup:
                    risk_lookup[(sym, "BOTH")] = risk
            except Exception:
                continue
    out = []
    if not infos:
        try:
            acc = self._get_futures_account_cached(force_refresh=True) or {}
            for pos in acc.get("positions", []):
                amt = float(pos.get("positionAmt") or 0.0)
                if abs(amt) <= 0.0:
                    continue
                row = {
                    "symbol": pos.get("symbol"),
                    "positionAmt": amt,
                    "notional": float(pos.get("notional") or 0.0) if isinstance(pos, dict) else 0.0,
                    "initialMargin": float(pos.get("initialMargin") or 0.0) if isinstance(pos, dict) else 0.0,
                    "positionInitialMargin": float(pos.get("positionInitialMargin") or pos.get("initialMargin") or 0.0) if isinstance(pos, dict) else 0.0,
                    "openOrderMargin": float(pos.get("openOrderInitialMargin") or 0.0) if isinstance(pos, dict) else 0.0,
                    "isolatedWallet": float(pos.get("isolatedWallet") or 0.0) if isinstance(pos, dict) else 0.0,
                    "isolatedMargin": float(pos.get("isolatedMargin") or 0.0) if isinstance(pos, dict) else 0.0,
                    "maintMargin": float(pos.get("maintMargin") or pos.get("maintenanceMargin") or 0.0) if isinstance(pos, dict) else 0.0,
                    "maintMarginRate": float(pos.get("maintMarginRate") or pos.get("maintenanceMarginRate") or 0.0) if isinstance(pos, dict) else 0.0,
                    "marginRatio": float(pos.get("marginRatio") or 0.0),
                    "marginBalance": float(pos.get("marginBalance") or 0.0) if isinstance(pos, dict) else 0.0,
                    "walletBalance": float(pos.get("walletBalance") or pos.get("marginBalance") or 0.0) if isinstance(pos, dict) else 0.0,
                    "entryPrice": float(pos.get("entryPrice") or 0.0),
                    "markPrice": float(pos.get("markPrice") or 0.0),
                    "marginType": pos.get("marginType"),
                    "leverage": int(float(pos.get("leverage") or 0)),
                    "unRealizedProfit": float(pos.get("unRealizedProfit") or 0.0),
                    "liquidationPrice": float(pos.get("liquidationPrice") or 0.0),
                    "positionSide": (pos.get("positionSide") or pos.get("positionside")),
                    "updateTime": _coerce_int(pos.get("updateTime") or pos.get("update_time")),
                }
                out.append(row)
        except Exception:
            pass
    else:
        for pos in infos or []:
            try:
                amt = float(pos.get("positionAmt") or 0.0)
                if abs(amt) <= 0.0:
                    continue
                row = {
                    "symbol": pos.get("symbol"),
                    "positionAmt": amt,
                    "notional": float(pos.get("notional") or 0.0) if isinstance(pos, dict) else 0.0,
                    "initialMargin": float(pos.get("initialMargin") or 0.0) if isinstance(pos, dict) else 0.0,
                    "positionInitialMargin": float(pos.get("positionInitialMargin") or pos.get("initialMargin") or 0.0) if isinstance(pos, dict) else 0.0,
                    "openOrderMargin": float(pos.get("openOrderInitialMargin") or 0.0) if isinstance(pos, dict) else 0.0,
                    "isolatedWallet": float(pos.get("isolatedWallet") or 0.0) if isinstance(pos, dict) else 0.0,
                    "isolatedMargin": float(pos.get("isolatedMargin") or 0.0) if isinstance(pos, dict) else 0.0,
                    "maintMargin": float(pos.get("maintMargin") or pos.get("maintenanceMargin") or 0.0) if isinstance(pos, dict) else 0.0,
                    "maintMarginRate": float(pos.get("maintMarginRate") or pos.get("maintenanceMarginRate") or 0.0) if isinstance(pos, dict) else 0.0,
                    "marginRatio": float(pos.get("marginRatio") or 0.0),
                    "marginBalance": float(pos.get("marginBalance") or 0.0) if isinstance(pos, dict) else 0.0,
                    "walletBalance": float(pos.get("walletBalance") or pos.get("marginBalance") or 0.0) if isinstance(pos, dict) else 0.0,
                    "entryPrice": float(pos.get("entryPrice") or 0.0),
                    "markPrice": float(pos.get("markPrice") or 0.0),
                    "marginType": pos.get("marginType"),
                    "leverage": int(float(pos.get("leverage") or 0)),
                    "unRealizedProfit": float(pos.get("unRealizedProfit") or 0.0),
                    "liquidationPrice": float(pos.get("liquidationPrice") or 0.0),
                    "positionSide": (pos.get("positionSide") or pos.get("positionside")),
                    "updateTime": _coerce_int(pos.get("updateTime") or pos.get("update_time")),
                }
                out.append(row)
            except Exception:
                continue
    if risk_lookup:
        for row in out:
            try:
                sym = str(row.get("symbol") or "").upper()
                side = str(row.get("positionSide") or row.get("positionside") or "BOTH").upper()
                risk = risk_lookup.get((sym, side)) or risk_lookup.get((sym, "BOTH"))
                if not isinstance(risk, dict):
                    continue
                risk_ratio_raw = risk.get("marginRatio")
                if risk_ratio_raw is not None:
                    try:
                        row["marginRatioRaw"] = float(risk_ratio_raw)
                        row["marginRatio"] = float(risk_ratio_raw)
                    except Exception:
                        pass

                def _safe_update(target_key, source_keys):
                    for src in source_keys:
                        if src not in risk:
                            continue
                        val = risk.get(src)
                        if val in (None, "", 0, 0.0):
                            continue
                        try:
                            row[target_key] = float(val)
                        except Exception:
                            row[target_key] = val
                        return

                _safe_update("marginRatio", ["marginRatio"])
                _safe_update("isolatedWallet", ["isolatedWallet"])
                _safe_update("isolatedMargin", ["isolatedMargin"])
                _safe_update("marginBalance", ["marginBalance", "isolatedWallet"])
                _safe_update("initialMargin", ["initialMargin", "isolatedMargin"])
                _safe_update("positionInitialMargin", ["positionInitialMargin", "initialMargin"])
                _safe_update("openOrderMargin", ["openOrderInitialMargin", "openOrderMargin"])
                _safe_update("walletBalance", ["walletBalance", "marginBalance"])
                _safe_update("notional", ["notional"])
                _safe_update("unRealizedProfit", ["unRealizedProfit"])
                _safe_update("entryPrice", ["entryPrice"])
                _safe_update("markPrice", ["markPrice"])
                _safe_update("leverage", ["leverage"])
                try:
                    maint_margin = float(row.get("maintMargin") or 0.0)
                except Exception:
                    maint_margin = 0.0
                try:
                    open_order_margin = float(row.get("openOrderMargin") or 0.0)
                except Exception:
                    open_order_margin = 0.0
                try:
                    wallet_balance = float(row.get("walletBalance") or row.get("marginBalance") or 0.0)
                except Exception:
                    wallet_balance = 0.0
                try:
                    unreal = float(row.get("unRealizedProfit") or 0.0)
                except Exception:
                    unreal = 0.0
                loss_component = abs(unreal) if unreal < 0 else 0.0
                calc_ratio = ((maint_margin + open_order_margin + loss_component) / wallet_balance) * 100.0 if wallet_balance > 0.0 else 0.0
                row["marginRatioCalc"] = calc_ratio
                if float(row.get("marginRatio") or 0.0) <= 0.0 and calc_ratio > 0.0:
                    row["marginRatio"] = calc_ratio
            except Exception:
                continue
    snapshot = copy.deepcopy(out)
    self._store_futures_positions_cache(snapshot)
    return copy.deepcopy(snapshot)


def get_net_futures_position_amt(self, symbol: str) -> float:
    """
    Return the net position quantity for a symbol (positive long, negative short, 0 if flat).
    """
    try:
        infos = self.client.futures_position_information()
    except Exception:
        try:
            infos = self.client.futures_position_risk()
        except Exception:
            infos = None
    if not infos:
        return 0.0
    symbol_upper = str(symbol or "").strip().upper()
    for entry in infos:
        try:
            if str(entry.get("symbol", "")).upper() != symbol_upper:
                continue
            amt = float(entry.get("positionAmt") or entry.get("positionAmt", 0.0) or 0.0)
            return amt
        except Exception:
            continue
    return 0.0


def bind_binance_futures_positions(wrapper_cls):
    wrapper_cls._get_cached_futures_positions = _get_cached_futures_positions
    wrapper_cls._store_futures_positions_cache = _store_futures_positions_cache
    wrapper_cls._invalidate_futures_positions_cache = _invalidate_futures_positions_cache
    wrapper_cls._format_quantity_for_order = staticmethod(_format_quantity_for_order)
    wrapper_cls._convert_asset_to_usdt = _convert_asset_to_usdt
    wrapper_cls._summarize_futures_order_fills = _summarize_futures_order_fills
    wrapper_cls.get_futures_dual_side = get_futures_dual_side
    wrapper_cls.close_futures_leg_exact = close_futures_leg_exact
    wrapper_cls.close_futures_position = close_futures_position
    wrapper_cls.cancel_all_open_futures_orders = cancel_all_open_futures_orders
    wrapper_cls.close_all_futures_positions = close_all_futures_positions
    wrapper_cls.list_open_futures_positions = list_open_futures_positions
    wrapper_cls.get_net_futures_position_amt = get_net_futures_position_amt
