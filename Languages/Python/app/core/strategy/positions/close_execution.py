from __future__ import annotations

import time


def _apply_entire_account_stop_loss(self, *, ctx: dict[str, object]) -> bool:
    cw = ctx.get("cw") if isinstance(ctx, dict) else self.config
    if not isinstance(cw, dict):
        cw = self.config
    account_type = str(ctx.get("account_type") or "").upper()
    if account_type != "FUTURES" or not bool(ctx.get("is_entire_account")):
        return False

    total_unrealized = 0.0
    try:
        total_unrealized = float(self.binance.get_total_unrealized_pnl())
    except Exception:
        total_unrealized = 0.0

    triggered = False
    reason = None
    apply_usdt_limit = bool(ctx.get("apply_usdt_limit"))
    apply_percent_limit = bool(ctx.get("apply_percent_limit"))
    try:
        stop_usdt_limit = float(ctx.get("stop_usdt_limit") or 0.0)
    except Exception:
        stop_usdt_limit = 0.0
    try:
        stop_percent_limit = float(ctx.get("stop_percent_limit") or 0.0)
    except Exception:
        stop_percent_limit = 0.0

    if apply_usdt_limit and total_unrealized <= -stop_usdt_limit:
        triggered = True
        reason = f"entire-account-usdt-limit ({total_unrealized:.2f})"
    if not triggered and apply_percent_limit:
        total_wallet = 0.0
        try:
            total_wallet = float(self.binance.get_total_wallet_balance())
        except Exception:
            total_wallet = 0.0
        if total_wallet > 0.0 and total_unrealized < 0.0:
            loss_pct = (abs(total_unrealized) / total_wallet) * 100.0
            if loss_pct >= stop_percent_limit:
                triggered = True
                reason = f"entire-account-percent-limit ({loss_pct:.2f}%)"

    if not triggered:
        return False

    try:
        self.log(f"{cw['symbol']}@{cw.get('interval')} entire account stop-loss triggered: {reason}.")
    except Exception:
        pass
    self._trigger_emergency_close(cw["symbol"], cw.get("interval"), reason or "entire_account_stop")
    return True


def _execute_close_with_fallback(
    self,
    symbol: str,
    close_side: str,
    qty: float,
    preferred_ps: str | None,
) -> tuple[bool, dict | None]:
    """Close a leg, trying the preferred position side before hedge/None fallbacks."""
    attempts: list[str | None] = []
    normalized_preferred = str(preferred_ps or "").upper() or None
    if normalized_preferred:
        attempts.append(normalized_preferred)
    hedge_ps = "SHORT" if close_side.upper() == "BUY" else "LONG"
    if hedge_ps not in attempts:
        attempts.append(hedge_ps)
    if None not in attempts:
        attempts.append(None)
    last_res = None
    tried: set[str | None] = set()
    for ps in attempts:
        if ps in tried:
            continue
        tried.add(ps)
        try:
            res = self.binance.close_futures_leg_exact(
                symbol,
                qty,
                side=close_side,
                position_side=ps,
            )
        except Exception as exc:
            res = {"ok": False, "error": str(exc)}
        last_res = res
        if isinstance(res, dict) and res.get("ok"):
            return True, res
        if isinstance(res, dict):
            message = str(res.get("error") or res)
        else:
            message = str(res)
        if "position side does not match" in message.lower():
            continue
    return False, last_res


def _close_leg_entry(
    self,
    cw: dict,
    leg_key: tuple[str, str, str],
    entry: dict,
    side_label: str,
    close_side: str,
    position_side: str | None,
    *,
    loss_usdt: float,
    price_pct: float,
    margin_pct: float,
    qty_limit: float | None = None,
    queue_flip: bool = True,
    reason: str | None = None,
) -> float:
    symbol, interval, _ = leg_key
    qty_recorded = max(0.0, float(entry.get("qty") or 0.0))
    if qty_recorded <= 0.0:
        return 0.0
    qty_to_close = qty_recorded
    if qty_limit is not None:
        try:
            qty_cap = max(0.0, float(qty_limit))
        except Exception:
            qty_cap = 0.0
        if qty_cap <= 0.0:
            return 0.0
        qty_to_close = min(qty_to_close, qty_cap)
    actual_qty = self._current_futures_position_qty(symbol, side_label, position_side)
    if actual_qty is not None:
        eps = max(1e-9, actual_qty * 1e-6)
        if actual_qty <= eps:
            try:
                self.log(
                    f"{symbol}@{interval} ({side_label}) live qty snapshot is flat; attempting verified close to avoid stale-snapshot misses."
                )
            except Exception:
                pass
        elif qty_to_close - actual_qty > eps:
            try:
                self.log(
                    f"Adjusting close size for {symbol}@{interval} ({side_label}) "
                    f"from {qty_to_close:.10f} to live {actual_qty:.10f}."
                )
            except Exception:
                pass
            qty_to_close = actual_qty
    if qty_to_close <= 0.0:
        return 0.0
    start_ts = time.time()
    try:
        ok_close, res = self._execute_close_with_fallback(
            symbol,
            close_side,
            qty_to_close,
            position_side,
        )
    except Exception as exc:
        try:
            self.log(f"Per-trade stop-loss close error for {symbol}@{interval} ({side_label}): {exc}")
        except Exception:
            pass
        return 0.0
    if not ok_close:
        try:
            self.log(f"Per-trade stop-loss close failed for {symbol}@{interval} ({side_label}): {res}")
        except Exception:
            pass
        return 0.0
    closed_qty = qty_to_close
    if isinstance(res, dict):
        try:
            sent_qty = float(
                res.get("sent_qty")
                or res.get("executed_qty")
                or res.get("executedQty")
                or res.get("origQty")
                or 0.0
            )
        except Exception:
            sent_qty = 0.0
        if sent_qty > 0.0:
            closed_qty = min(qty_to_close, sent_qty)
    if closed_qty <= 0.0:
        closed_qty = qty_to_close
    latency_s = max(0.0, time.time() - start_ts)
    payload = self._build_close_event_payload(
        symbol,
        interval,
        side_label,
        closed_qty,
        res,
        leg_info_override=entry,
    )
    if isinstance(reason, str) and reason.strip():
        payload["reason"] = reason.strip()
    remaining_qty = qty_recorded - closed_qty
    eps_remaining = max(1e-9, qty_recorded * 1e-6)
    fully_closed = remaining_qty <= eps_remaining or not entry.get("ledger_id")
    if fully_closed:
        self._remove_leg_entry(leg_key, entry.get("ledger_id"))
    else:
        self._decrement_leg_entry_qty(
            leg_key,
            entry.get("ledger_id"),
            qty_recorded,
            remaining_qty,
        )
    side_norm = "BUY" if str(side_label).upper() in ("BUY", "LONG", "L") else "SELL"
    self._mark_guard_closed(symbol, interval, side_norm)
    if fully_closed:
        self._mark_indicator_reentry_signal_block(symbol, interval, entry, side_label)
        try:
            for indicator_key in self._extract_indicator_keys(entry):
                self._record_indicator_close(symbol, interval, indicator_key, side_label, closed_qty)
        except Exception:
            pass
    self._notify_interval_closed(
        symbol,
        interval,
        side_label,
        **payload,
        latency_seconds=latency_s,
        latency_ms=latency_s * 1000.0,
        reason=(str(reason).strip() if isinstance(reason, str) and str(reason).strip() else "per_trade_stop_loss"),
    )
    if queue_flip and fully_closed:
        try:
            self._queue_flip_on_close(interval, side_label, entry, payload)
        except Exception:
            pass
    self._log_latency_metric(symbol, interval, f"stop-loss {side_label.lower()} leg", latency_s)
    try:
        pct_display = max(price_pct, margin_pct)
        self.log(
            f"Per-trade stop-loss closed {side_label} for {symbol}@{interval} "
            f"(qty {closed_qty:.10f}, loss {loss_usdt:.4f} USDT / {pct_display:.2f}%)."
        )
    except Exception:
        pass
    return closed_qty


def _evaluate_per_trade_stop(
    self,
    cw: dict,
    leg_key: tuple[str, str, str],
    entries: list[dict],
    *,
    side_label: str,
    last_price: float | None,
    apply_usdt_limit: bool,
    apply_percent_limit: bool,
    stop_usdt_limit: float,
    stop_percent_limit: float,
    dual_side: bool,
) -> bool:
    if last_price is None:
        return False
    symbol, interval, _ = leg_key
    desired_position_side = None
    if dual_side:
        desired_position_side = "LONG" if side_label.upper() == "BUY" else "SHORT"
    close_side = "SELL" if side_label.upper() == "BUY" else "BUY"
    triggered_any = False
    for entry in list(entries):
        qty = max(0.0, float(entry.get("qty") or 0.0))
        entry_price = max(0.0, float(entry.get("entry_price") or 0.0))
        if qty <= 0.0 or entry_price <= 0.0:
            continue
        if side_label.upper() == "BUY":
            loss_usdt = max(0.0, (entry_price - last_price) * qty)
        else:
            loss_usdt = max(0.0, (last_price - entry_price) * qty)
        denom = entry_price * qty
        price_pct = (loss_usdt / denom * 100.0) if denom > 0.0 else 0.0
        leverage_val = float(entry.get("leverage") or 0.0)
        margin_entry = float(entry.get("margin_usdt") or 0.0)
        if margin_entry <= 0.0:
            if leverage_val > 0.0:
                margin_entry = denom / leverage_val if leverage_val != 0.0 else denom
            else:
                margin_entry = denom
        margin_pct = (loss_usdt / margin_entry * 100.0) if margin_entry > 0.0 else 0.0
        effective_pct = max(price_pct, margin_pct)
        triggered = False
        if apply_usdt_limit and loss_usdt >= stop_usdt_limit:
            triggered = True
        if not triggered and apply_percent_limit and effective_pct >= stop_percent_limit:
            triggered = True
        if triggered:
            if self._close_leg_entry(
                cw,
                leg_key,
                entry,
                side_label.upper(),
                close_side,
                desired_position_side,
                loss_usdt=loss_usdt,
                price_pct=price_pct,
                margin_pct=margin_pct,
                reason="per_trade_stop_loss",
            ):
                triggered_any = True
    if triggered_any:
        leg = self._leg_ledger.get(leg_key)
        if isinstance(leg, dict):
            self._update_leg_snapshot(leg_key, leg)
    else:
        leg = self._leg_ledger.get(leg_key)
        if isinstance(leg, dict):
            leg["timestamp"] = time.time()
    return triggered_any
