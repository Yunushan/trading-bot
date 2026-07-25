from __future__ import annotations

import logging
import math
import time


_LOGGER = logging.getLogger(__name__)


def _safe_log(self, message: str, *, level: int = logging.WARNING) -> bool:
    callback = getattr(self, "log", None)
    if callable(callback):
        try:
            callback(message)
            return True
        except Exception:
            _LOGGER.exception("Position close log callback failed while reporting: %s", message)
            return False
    _LOGGER.log(level, message)
    return False


def _pause_for_close_uncertainty(self, message: str, *, reconciliation_required: bool) -> None:
    if reconciliation_required:
        self._ledger_reconciliation_required = True
    cls = type(self)
    pause_event = getattr(cls, "_GLOBAL_PAUSE", None)
    if pause_event is None:
        cls._GLOBAL_PAUSE_FALLBACK = True
    else:
        try:
            pause_event.set()
        except Exception:
            cls._GLOBAL_PAUSE_FALLBACK = True
            _LOGGER.exception("Global pause event failed after close-state uncertainty")
    _safe_log(self, f"{message}; trading paused pending reconciliation.")


def _finite_float(value: object, *, default: float = 0.0) -> float:
    """Return a finite float, refusing malformed exchange and ledger values."""
    try:
        number = float(value)
    except (TypeError, ValueError, OverflowError):
        return default
    return number if math.isfinite(number) else default


def _apply_entire_account_stop_loss(self, *, ctx: dict[str, object]) -> bool:
    cw = ctx.get("cw") if isinstance(ctx, dict) else self.config
    if not isinstance(cw, dict):
        cw = self.config
    account_type = str(ctx.get("account_type") or "").upper()
    if account_type != "FUTURES" or not bool(ctx.get("is_entire_account")):
        return False

    total_unrealized = 0.0
    try:
        total_unrealized = _finite_float(self.binance.get_total_unrealized_pnl())
    except Exception as exc:
        _pause_for_close_uncertainty(
            self,
            f"Entire-account stop-loss PnL snapshot failed: {exc}",
            reconciliation_required=False,
        )
        return False

    triggered = False
    reason = None
    apply_usdt_limit = bool(ctx.get("apply_usdt_limit"))
    apply_percent_limit = bool(ctx.get("apply_percent_limit"))
    stop_usdt_limit_value = ctx.get("stop_usdt_limit")
    stop_percent_limit_value = ctx.get("stop_percent_limit")
    try:
        if isinstance(stop_usdt_limit_value, (int, float, str)):
            stop_usdt_limit = _finite_float(stop_usdt_limit_value, default=float("nan"))
        else:
            stop_usdt_limit = float("nan")
    except Exception:
        stop_usdt_limit = float("nan")
    try:
        if isinstance(stop_percent_limit_value, (int, float, str)):
            stop_percent_limit = _finite_float(stop_percent_limit_value, default=float("nan"))
        else:
            stop_percent_limit = float("nan")
    except Exception:
        stop_percent_limit = float("nan")

    if apply_usdt_limit and math.isfinite(stop_usdt_limit) and total_unrealized <= -stop_usdt_limit:
        triggered = True
        reason = f"entire-account-usdt-limit ({total_unrealized:.2f})"
    if not triggered and apply_percent_limit and math.isfinite(stop_percent_limit):
        total_wallet = 0.0
        try:
            total_wallet = _finite_float(self.binance.get_total_wallet_balance())
        except Exception as exc:
            _pause_for_close_uncertainty(
                self,
                f"Entire-account stop-loss wallet snapshot failed: {exc}",
                reconciliation_required=False,
            )
            return False
        if total_wallet > 0.0 and total_unrealized < 0.0:
            loss_pct = (abs(total_unrealized) / total_wallet) * 100.0
            if loss_pct >= stop_percent_limit:
                triggered = True
                reason = f"entire-account-percent-limit ({loss_pct:.2f}%)"

    if not triggered:
        return False

    _safe_log(
        self,
        f"{cw['symbol']}@{cw.get('interval')} entire account stop-loss triggered: {reason}.",
    )
    self._trigger_emergency_close(cw["symbol"], cw.get("interval"), reason or "entire_account_stop")
    return True


def _execute_close_with_fallback(
    self,
    symbol: str,
    close_side: str,
    qty: float,
    preferred_ps: str | None,
) -> tuple[bool, dict | None]:
    """Close a leg without ever falling back across an explicit hedge side."""
    normalized_preferred = str(preferred_ps or "").upper() or None
    if normalized_preferred in {"LONG", "SHORT"}:
        # An explicit hedge side identifies the owned leg. Retrying another side or
        # a one-way order after a mismatch could close an unrelated position.
        attempts: list[str | None] = [normalized_preferred]
    else:
        attempts = []
        hedge_ps = "SHORT" if close_side.upper() == "BUY" else "LONG"
        attempts.append(hedge_ps)
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
            if res.get("reconciliation_required"):
                warnings = res.get("warnings")
                warning_text = "; ".join(str(item) for item in warnings) if isinstance(warnings, list) else ""
                _pause_for_close_uncertainty(
                    self,
                    f"Confirmed {symbol} close requires reconciliation"
                    + (f": {warning_text}" if warning_text else "."),
                    reconciliation_required=True,
                )
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
    qty_recorded = max(0.0, _finite_float(entry.get("qty")))
    if qty_recorded <= 0.0:
        return 0.0
    qty_to_close = qty_recorded
    if qty_limit is not None:
        qty_cap = max(0.0, _finite_float(qty_limit))
        if qty_cap <= 0.0:
            return 0.0
        qty_to_close = min(qty_to_close, qty_cap)
    try:
        actual_qty = self._current_futures_position_qty(symbol, side_label, position_side)
    except Exception as exc:
        _pause_for_close_uncertainty(
            self,
            f"{symbol}@{interval} ({side_label}) live quantity query failed: {exc}",
            reconciliation_required=False,
        )
        return 0.0
    if actual_qty is not None:
        actual_qty = _finite_float(actual_qty, default=-1.0)
        if actual_qty < 0.0:
            _safe_log(
                self,
                f"{symbol}@{interval} ({side_label}) close refused: live quantity snapshot was not finite.",
            )
            return 0.0
        eps = max(1e-9, actual_qty * 1e-6)
        if actual_qty <= eps:
            _safe_log(
                self,
                f"{symbol}@{interval} ({side_label}) live qty snapshot is flat; "
                "attempting verified close to avoid stale-snapshot misses.",
                level=logging.INFO,
            )
        elif qty_to_close - actual_qty > eps:
            _safe_log(
                self,
                f"Adjusting close size for {symbol}@{interval} ({side_label}) "
                f"from {qty_to_close:.10f} to live {actual_qty:.10f}.",
                level=logging.INFO,
            )
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
        _safe_log(self, f"Per-trade stop-loss close error for {symbol}@{interval} ({side_label}): {exc}")
        return 0.0
    if not ok_close:
        _safe_log(self, f"Per-trade stop-loss close failed for {symbol}@{interval} ({side_label}): {res}")
        return 0.0
    closed_qty = qty_to_close
    if isinstance(res, dict):
        sent_qty = _finite_float(
            res.get("sent_qty")
            or res.get("executed_qty")
            or res.get("executedQty")
            or res.get("origQty")
            or 0.0
        )
        if sent_qty > 0.0:
            closed_qty = min(qty_to_close, sent_qty)
    if closed_qty <= 0.0:
        closed_qty = qty_to_close
    latency_s = max(0.0, time.time() - start_ts)
    try:
        payload = self._build_close_event_payload(
            symbol,
            interval,
            side_label,
            closed_qty,
            res,
            leg_info_override=entry,
        )
    except Exception as exc:
        payload = {"qty": closed_qty}
        _pause_for_close_uncertainty(
            self,
            f"Confirmed {symbol}@{interval} ({side_label}) close metadata failed: {exc}",
            reconciliation_required=True,
        )
    reason_text = (
        str(reason).strip()
        if isinstance(reason, str) and str(reason).strip()
        else "per_trade_stop_loss"
    )
    payload["reason"] = reason_text
    side_norm = "BUY" if str(side_label).upper() in ("BUY", "LONG", "L") else "SELL"
    remaining_qty = qty_recorded - closed_qty
    eps_remaining = max(1e-9, qty_recorded * 1e-6)
    fully_closed = remaining_qty <= eps_remaining or not entry.get("ledger_id")
    payload["remaining_qty"] = max(0.0, remaining_qty)
    payload["fully_closed"] = fully_closed
    try:
        if fully_closed:
            self._remove_leg_entry(leg_key, entry.get("ledger_id"))
            self._mark_guard_closed(symbol, interval, side_norm, entry=entry)
        else:
            self._decrement_leg_entry_qty(
                leg_key,
                entry.get("ledger_id"),
                qty_recorded,
                remaining_qty,
            )
        if fully_closed:
            self._mark_indicator_reentry_signal_block(symbol, interval, entry, side_label)
            for indicator_key in self._extract_indicator_keys(entry):
                self._record_indicator_close(symbol, interval, indicator_key, side_label, closed_qty)
    except Exception as exc:
        _pause_for_close_uncertainty(
            self,
            f"Confirmed {symbol}@{interval} ({side_label}) close could not reconcile local state: {exc}",
            reconciliation_required=True,
        )
    try:
        self._notify_interval_closed(
            symbol,
            interval,
            side_label,
            **payload,
            latency_seconds=latency_s,
            latency_ms=latency_s * 1000.0,
        )
    except Exception as exc:
        _safe_log(self, f"Confirmed {symbol}@{interval} ({side_label}) close notification failed: {exc}")
    if queue_flip and fully_closed:
        try:
            self._queue_flip_on_close(interval, side_label, entry, payload)
        except Exception as exc:
            _safe_log(self, f"Confirmed {symbol}@{interval} ({side_label}) close flip queue failed: {exc}")
    try:
        self._log_latency_metric(symbol, interval, f"stop-loss {side_label.lower()} leg", latency_s)
    except Exception as exc:
        _safe_log(self, f"Confirmed {symbol}@{interval} ({side_label}) close latency metric failed: {exc}")
    pct_display = max(price_pct, margin_pct)
    _safe_log(
        self,
        f"Per-trade stop-loss closed {side_label} for {symbol}@{interval} "
        f"(qty {closed_qty:.10f}, loss {loss_usdt:.4f} USDT / {pct_display:.2f}%).",
        level=logging.INFO,
    )
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
    last_price = _finite_float(last_price, default=-1.0)
    if last_price <= 0.0:
        _safe_log(self, "Per-trade stop-loss evaluation skipped: market price was not a positive finite value.")
        return False
    symbol, interval, _ = leg_key
    desired_position_side = None
    if dual_side:
        desired_position_side = "LONG" if side_label.upper() == "BUY" else "SHORT"
    close_side = "SELL" if side_label.upper() == "BUY" else "BUY"
    triggered_any = False
    for entry in list(entries):
        qty = max(0.0, _finite_float(entry.get("qty")))
        entry_price = max(0.0, _finite_float(entry.get("entry_price")))
        if qty <= 0.0 or entry_price <= 0.0:
            continue
        if side_label.upper() == "BUY":
            loss_usdt = max(0.0, (entry_price - last_price) * qty)
        else:
            loss_usdt = max(0.0, (last_price - entry_price) * qty)
        if not math.isfinite(loss_usdt):
            continue
        denom = entry_price * qty
        price_pct = (loss_usdt / denom * 100.0) if denom > 0.0 else 0.0
        leverage_val = max(0.0, _finite_float(entry.get("leverage")))
        margin_entry = max(0.0, _finite_float(entry.get("margin_usdt")))
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
