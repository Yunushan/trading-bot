from __future__ import annotations

import time


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
        if live_qty <= qty_tol and (known_preferred or known_fallback):
            return {"ok": True, "skipped": True, "symbol": sym, "reason": "position already flat"}
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
        else:
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

        def _fresh_symbol_rows() -> tuple[list, bool, str | None]:
            snapshot_error: str | None = None
            fresh_rows = []
            known = False
            try:
                fresh_rows = self.list_open_futures_positions(max_age=0.0, force_refresh=True) or []
                known = True
            except Exception as exc:
                snapshot_error = str(exc)
            if not fresh_rows:
                try:
                    raw_rows = self.client.futures_position_information(symbol=sym) or []
                    known = True
                    fresh_rows = []
                    for raw in raw_rows:
                        try:
                            if str(raw.get("symbol") or "").upper() != sym:
                                continue
                            fresh_rows.append(
                                {
                                    "symbol": sym,
                                    "positionAmt": float(raw.get("positionAmt") or 0.0),
                                    "positionSide": str(
                                        raw.get("positionSide") or raw.get("positionside") or "BOTH"
                                    ).upper(),
                                }
                            )
                        except Exception:
                            continue
                except Exception as exc:
                    if not known:
                        snapshot_error = str(exc)
            return fresh_rows, known, snapshot_error

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

        remaining = []
        verification_known = False
        verification_error: str | None = None
        if closed > 0 or failed > 0:
            for attempt in range(3):
                fresh_rows, verification_known, verification_error = _fresh_symbol_rows()
                remaining = []
                for fresh in fresh_rows:
                    try:
                        if str(fresh.get("symbol") or "").upper() != sym:
                            continue
                        if abs(float(fresh.get("positionAmt") or 0.0)) > 1e-12:
                            remaining.append(fresh)
                    except Exception:
                        continue
                if verification_known and not remaining:
                    break
                if attempt < 2:
                    time.sleep(0.1)
            if not verification_known:
                errors.append(f"close verification unavailable: {verification_error or 'unknown error'}")
            elif remaining:
                remaining_labels = [
                    f"{str(row.get('positionSide') or 'BOTH').upper()}={row.get('positionAmt')}"
                    for row in remaining
                ]
                errors.append(f"position remained open after close: {', '.join(remaining_labels)}")
        if closed <= 0 and failed <= 0:
            return {
                "ok": False,
                "closed": 0,
                "failed": 0,
                "errors": ["no open positions found from close snapshot"],
                "symbol": sym,
            }
        return {
            "ok": failed == 0 and verification_known and not remaining,
            "closed": closed,
            "failed": failed,
            "errors": errors,
            "remaining": len(remaining),
        }
    except Exception as exc:
        return {"ok": False, "error": str(exc)}


def cancel_all_open_futures_orders(self) -> dict:
    results: dict = {"ok": True, "canceled_symbols": 0, "errors": []}
    try:
        orders = []
        try:
            orders = self.client.futures_get_open_orders() or []
        except Exception as exc:
            results["ok"] = False
            results["errors"].append(f"open order snapshot: {exc}")
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
            except Exception as exc:
                results["errors"].append(f"position snapshot: {exc}")
        for sym in sorted(symbols):
            try:
                self.client.futures_cancel_all_open_orders(symbol=sym)
                results["canceled_symbols"] += 1
            except Exception as exc:
                results["ok"] = False
                results["errors"].append(f"{sym}: {exc}")
        if results["ok"]:
            results["errors"] = []
    except Exception as exc:
        return {"ok": False, "error": str(exc)}
    return results


def close_all_futures_positions(self):
    """Delegate to the single canonical, reconciled close-all implementation."""
    try:
        from .close_all_runtime import close_all_futures_positions as _close_all_futures_positions

        delegated = _close_all_futures_positions(self)
        if isinstance(delegated, list):
            return delegated
        return [{"ok": False, "error": "canonical close-all runtime returned an invalid response"}]
    except Exception as exc:
        try:
            logger = getattr(self, "_log", None)
            if callable(logger):
                logger(f"Canonical close-all runtime failed: {exc}", lvl="error")
        except Exception:
            return [{"ok": False, "error": f"canonical close-all runtime failed: {exc}"}]
        return [{"ok": False, "error": f"canonical close-all runtime failed: {exc}"}]
