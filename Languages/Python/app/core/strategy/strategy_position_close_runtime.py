from __future__ import annotations

from collections.abc import Iterable
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
        message = ""
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
    side_norm = 'BUY' if str(side_label).upper() in ('BUY', 'LONG', 'L') else 'SELL'
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
        # ensure ledger snapshot reflects any removals
        leg = self._leg_ledger.get(leg_key)
        if isinstance(leg, dict):
            self._update_leg_snapshot(leg_key, leg)
    else:
        # ensure we keep consistent timestamps even if no trigger
        leg = self._leg_ledger.get(leg_key)
        if isinstance(leg, dict):
            leg["timestamp"] = time.time()
    return triggered_any



def _close_indicator_positions(
    self,
    cw: dict,
    interval: str,
    indicator_key: str,
    side_label: str,
    position_side: str | None,
    signature_hint: tuple[str, ...] | None = None,
    *,
    ignore_hold: bool = False,
    interval_aliases: Iterable[str] | None = None,
    qty_limit: float | None = None,
    strict_interval: bool = False,
    allow_hedge_close: bool = False,
    reason: str | None = None,
) -> tuple[int, float]:
    symbol = cw["symbol"]
    interval_text = str(interval or "").strip()
    indicator_norm = self._canonical_indicator_token(indicator_key) or str(indicator_key or "").strip().lower()
    if not indicator_norm:
        indicator_norm = str(indicator_key or "").strip().lower()
    indicator_lookup_key = indicator_norm or indicator_key
    hedge_scope_only = self._strategy_coerce_bool(self.config.get("allow_opposite_positions"), True)

    if hedge_scope_only:
        # In hedge mode, we must close only the quantity associated with the specific
        # indicator and interval that triggered the close signal.
        qty_for_indicator = self._indicator_open_qty(
            symbol,
            interval_text,
            indicator_lookup_key,
            side_label,
            strict_interval=True,
        )
        # Fallback: include trade-book and live exchange qty for this slot to avoid skipping closes.
        try:
            book_qty = self._indicator_trade_book_qty(symbol, interval_text, indicator_lookup_key, side_label)
        except Exception:
            book_qty = 0.0
        try:
            exch_qty = 0.0
            desired_ps_local = None
            if position_side:
                desired_ps_local = position_side
            elif self._strategy_coerce_bool(self.binance.get_futures_dual_side(), False):
                desired_ps_local = "LONG" if side_label.upper() in {"BUY", "LONG"} else "SHORT"
            exch_qty = max(
                0.0,
                float(
                    self._current_futures_position_qty(
                        symbol,
                        side_label,
                        desired_ps_local,
                    )
                    or 0.0
                ),
            )
        except Exception:
            exch_qty = 0.0
        qty_for_indicator = max(qty_for_indicator or 0.0, book_qty or 0.0, exch_qty or 0.0)
        qty_tol = 1e-9
        if qty_for_indicator <= qty_tol:
            return 0, 0.0

        if qty_limit is None:
            qty_limit = qty_for_indicator
        else:
            qty_limit = min(qty_limit, qty_for_indicator)

    if hedge_scope_only and not allow_hedge_close:
        return 0, 0.0
    if (
        not signature_hint
        and self._strategy_coerce_bool(self.config.get("require_indicator_flip_signal"), True)
        and self._strategy_coerce_bool(self.config.get("strict_indicator_flip_enforcement"), True)
        and not self._strategy_coerce_bool(self.config.get("allow_indicator_close_without_signal"), False)
    ):
        return 0, 0.0
    interval_tokens = self._tokenize_interval_label(interval_text)
    if not strict_interval and interval_aliases:
        for alias in interval_aliases:
            norm = self._normalize_interval_token(alias)
            if norm:
                interval_tokens.add(norm)
    if self._strategy_coerce_bool(self.config.get("allow_opposite_positions"), True):
        interval_tokens = self._tokenize_interval_label(interval_text)
        interval_aliases = None
        strict_interval = True
    interval_has_filter = interval_tokens != {"-"}
    ledger_entries = [
        entry
        for entry in self._trade_book_entries(symbol, interval, indicator_lookup_key, side_label)
        if self._indicator_entry_matches_close(
            entry,
            indicator_lookup_key,
            allow_multi_override=allow_hedge_close,
        )
    ]
    ledger_ids = [entry.get("ledger_id") for entry in ledger_entries if entry.get("ledger_id")]
    ledger_ids = [lid for lid in ledger_ids if lid]
    if not ledger_ids:
        ledger_ids = self._indicator_get_ledger_ids(symbol, interval, indicator_lookup_key, side_label)
    indicator_scope_found = bool(ledger_ids)
    if allow_hedge_close:
        indicator_scope_found = True
    if (not ledger_ids) and signature_hint:
        signature_hint = tuple(
            str(token or "").strip().lower() for token in signature_hint if str(token or "").strip()
        )
        if signature_hint:
            extra_ids: list[str] = []
            for _, entry in self._iter_indicator_entries(symbol, interval, indicator_key, side_label):
                sig_tuple = self._normalize_signature_tokens_no_slots(
                    entry.get("trigger_signature") or entry.get("trigger_indicators")
                )
                if signature_hint:
                    hint_norm = tuple(
                        str(token or "").strip().lower()
                        for token in signature_hint
                        if str(token or "").strip()
                    )
                    if hint_norm:
                        sig_set = set(sig_tuple or ())
                        if not set(hint_norm).issubset(sig_set):
                            continue
                ledger = entry.get("ledger_id")
                if ledger and ledger not in ledger_ids and ledger not in extra_ids:
                    extra_ids.append(ledger)
            if extra_ids:
                ledger_ids.extend(extra_ids)
    close_side = "SELL" if str(side_label).upper() in {"BUY", "LONG"} else "BUY"
    side_norm = "BUY" if str(side_label).upper() in {"BUY", "LONG"} else "SELL"
    guard_label = f"{indicator_lookup_key}@{interval_text or 'default'}"
    if not self._enter_close_guard(symbol, side_norm, guard_label):
        try:
            blocking = self._describe_close_guard(symbol) or {}
            self.log(
                f"{symbol}@{interval_text or 'default'} close skipped: {guard_label} blocked by active "
                f"{blocking.get('side') or 'side'} close {blocking.get('label') or ''}".strip()
            )
        except Exception:
            pass
        return 0, 0.0
    if strict_interval and interval_has_filter and not indicator_scope_found and not allow_hedge_close:
        self._exit_close_guard(symbol, side_norm)
        return 0, 0.0
    closed_count = 0
    total_qty_closed = 0.0
    limit_remaining = None
    limit_tol = 1e-9
    if qty_limit is not None:
        try:
            limit_remaining = max(0.0, float(qty_limit))
        except Exception:
            limit_remaining = 0.0
    hedge_scope_only = self._strategy_coerce_bool(self.config.get("allow_opposite_positions"), True)
    for ledger_id in list(ledger_ids):
        if limit_remaining is not None and limit_remaining <= limit_tol:
            break
        leg_key = self._ledger_index.get(ledger_id)
        if not leg_key:
            continue
        entries = self._leg_entries(leg_key)
        target_entry = None
        for entry in entries:
            if entry.get("ledger_id") == ledger_id:
                target_entry = entry
                break
        if not target_entry:
            continue
        try:
            if hedge_scope_only:
                leg_iv_tokens = self._tokenize_interval_label(leg_key[1])
                if interval_tokens != {"-"} and leg_iv_tokens != interval_tokens:
                    continue
            elif strict_interval and interval_has_filter:
                leg_iv_tokens = self._tokenize_interval_label(leg_key[1])
                if leg_iv_tokens != interval_tokens:
                    continue
            interval_seconds_entry = self._interval_seconds_value(leg_key[1])
            if not self._indicator_hold_ready(
                target_entry.get("timestamp"),
                symbol,
                leg_key[1],
                indicator_key,
                side_label,
                interval_seconds_entry,
                now_ts=None,
                ignore_hold=ignore_hold,
            ):
                continue
            cw_clone = dict(cw)
            cw_clone["interval"] = leg_key[1]
            qty_request = limit_remaining if limit_remaining is not None else None
            closed_qty = self._close_leg_entry(
                cw_clone,
                leg_key,
                target_entry,
                side_norm,
                close_side,
                position_side,
                loss_usdt=0.0,
                price_pct=0.0,
                margin_pct=0.0,
                qty_limit=qty_request,
                reason=reason,
            )
            if closed_qty > 0.0:
                closed_count += 1
                total_qty_closed += closed_qty
                if limit_remaining is not None:
                    limit_remaining = max(0.0, limit_remaining - closed_qty)
                self._mark_guard_closed(symbol, leg_key[1], close_side)
        except Exception:
            continue
        if limit_remaining is not None and limit_remaining <= limit_tol:
            break
    if closed_count <= 0:
        if hedge_scope_only and not allow_hedge_close:
            self._exit_close_guard(symbol, side_norm)
            return 0, 0.0
        targeted_entries: list[tuple[tuple[str, str, str], dict]] = []
        for leg_key, _ in list(self._leg_ledger.items()):
            leg_sym, leg_interval, leg_side = leg_key
            if str(leg_sym or "").upper() != symbol:
                continue
            leg_interval_norm = str(leg_interval or "").strip()
            leg_interval_tokens = self._tokenize_interval_label(leg_interval_norm)
            if interval_tokens != {"-"} and leg_interval_tokens.isdisjoint(interval_tokens):
                continue
            if strict_interval and interval_has_filter and leg_interval_tokens != interval_tokens:
                continue
            leg_side_norm = str(leg_side or "").upper()
            if leg_side_norm in {"LONG", "SHORT"}:
                leg_side_norm = "BUY" if leg_side_norm == "LONG" else "SELL"
            if leg_side_norm != side_norm:
                continue
            entries = self._leg_entries(leg_key)
            if not entries:
                continue
            for entry in entries:
                if not self._indicator_entry_matches_close(
                    entry,
                    indicator_lookup_key,
                    allow_multi_override=allow_hedge_close,
                ):
                    continue
                targeted_entries.append((leg_key, entry))
        if targeted_entries:
            indicator_scope_found = True
            for leg_key, entry in targeted_entries:
                if limit_remaining is not None and limit_remaining <= limit_tol:
                    break
                try:
                    if hedge_scope_only:
                        leg_iv_tokens = self._tokenize_interval_label(leg_key[1])
                        if interval_tokens != {"-"} and leg_iv_tokens != interval_tokens:
                            continue
                    interval_seconds_entry = self._interval_seconds_value(leg_key[1])
                    if not self._indicator_hold_ready(
                        entry.get("timestamp"),
                        symbol,
                        leg_key[1],
                        indicator_key,
                        side_label,
                        interval_seconds_entry,
                        now_ts=None,
                        ignore_hold=ignore_hold,
                    ):
                        continue
                    cw_clone = dict(cw)
                    cw_clone["interval"] = leg_key[1]
                    qty_request = limit_remaining if limit_remaining is not None else None
                    closed_qty = self._close_leg_entry(
                        cw_clone,
                        leg_key,
                        entry,
                        side_norm,
                        "SELL" if side_norm == "BUY" else "BUY",
                        position_side,
                        loss_usdt=0.0,
                        price_pct=0.0,
                        margin_pct=0.0,
                        qty_limit=qty_request,
                        reason=reason,
                    )
                    if closed_qty > 0.0:
                        closed_count += 1
                        total_qty_closed += closed_qty
                        if limit_remaining is not None:
                            limit_remaining = max(0.0, limit_remaining - closed_qty)
                except Exception:
                    continue
            if closed_count > 0:
                self._exit_close_guard(symbol, side_norm)
                return closed_count, total_qty_closed

    if closed_count <= 0 and not indicator_scope_found:
        self._exit_close_guard(symbol, side_norm)
        return closed_count, total_qty_closed

    if closed_count <= 0:
        fallback_entries: list[tuple[tuple[str, str, str], str | None, float]] = []
        fallback_qty_target = 0.0
        for leg_key, _ in list(self._leg_ledger.items()):
            leg_sym, leg_interval, leg_side = leg_key
            if str(leg_sym or "").upper() != symbol:
                continue
            leg_interval_norm = str(leg_interval or "").strip()
            leg_tokens = self._tokenize_interval_label(leg_interval_norm)
            if interval_has_filter and leg_tokens.isdisjoint(interval_tokens):
                continue
            if hedge_scope_only and interval_has_filter and leg_tokens != interval_tokens:
                continue
            if strict_interval and interval_has_filter and leg_tokens != interval_tokens:
                continue
            leg_side_norm = "BUY" if str(leg_side or "").upper() in {"BUY", "LONG"} else "SELL"
            if leg_side_norm != side_norm:
                continue
            entries = self._leg_entries(leg_key)
            if not entries:
                continue
            for entry in entries:
                if not self._indicator_entry_matches_close(
                    entry,
                    indicator_lookup_key,
                    allow_multi_override=allow_hedge_close,
                ):
                    continue
                interval_seconds_entry = self._interval_seconds_value(leg_key[1] or "1m")
                if not self._indicator_hold_ready(
                    entry.get("timestamp"),
                    leg_sym,
                    leg_key[1],
                    indicator_key,
                    side_norm,
                    interval_seconds_entry,
                    now_ts=None,
                    ignore_hold=ignore_hold,
                ):
                    continue
                try:
                    qty_val = max(0.0, float(entry.get("qty") or 0.0))
                    fallback_qty_target += qty_val
                except Exception:
                    continue
                fallback_entries.append((leg_key, entry.get("ledger_id"), qty_val))
        indicator_scope_found = indicator_scope_found or bool(fallback_entries)
        if hedge_scope_only and not indicator_scope_found:
            self._exit_close_guard(symbol, side_norm)
            return closed_count, total_qty_closed
        live_qty = 0.0
        try:
            live_qty = max(
                0.0,
                float(self._current_futures_position_qty(symbol, side_norm, position_side)),
            )
        except Exception:
            live_qty = 0.0
        qty_limit_hint = None
        if qty_limit is not None:
            try:
                qty_limit_hint = max(0.0, float(qty_limit))
            except Exception:
                qty_limit_hint = 0.0
        fallback_qty_goal = fallback_qty_target
        if fallback_qty_goal <= 0.0:
            fallback_qty_goal = qty_limit_hint or 0.0
        qty_to_close = min(live_qty, fallback_qty_goal) if fallback_qty_goal > 0.0 else 0.0
        if limit_remaining is not None:
            qty_to_close = min(qty_to_close, limit_remaining)
        if qty_to_close > 0.0:
            close_side = "SELL" if side_norm == "BUY" else "BUY"
            qty_remaining = qty_to_close
            tol = max(1e-9, qty_to_close * 1e-6)
            if fallback_entries:
                for leg_key, ledger_token, entry_qty in fallback_entries:
                    if qty_remaining <= tol:
                        break
                    if not ledger_token:
                        continue
                    entry_match = None
                    for entry in self._leg_entries(leg_key):
                        if entry.get("ledger_id") == ledger_token:
                            entry_match = entry
                            break
                    if not entry_match:
                        continue
                    cw_clone = dict(cw)
                    cw_clone["interval"] = leg_key[1]
                    request_qty = min(entry_qty, qty_remaining)
                    closed_qty_entry = self._close_leg_entry(
                        cw_clone,
                        leg_key,
                        entry_match,
                        side_norm,
                        close_side,
                        position_side,
                        loss_usdt=0.0,
                        price_pct=0.0,
                        margin_pct=0.0,
                        qty_limit=request_qty,
                        reason=reason,
                    )
                    if closed_qty_entry > 0.0:
                        closed_count += 1
                        total_qty_closed += closed_qty_entry
                        qty_remaining = max(0.0, qty_remaining - closed_qty_entry)
                        if limit_remaining is not None:
                            limit_remaining = max(0.0, limit_remaining - closed_qty_entry)
                if qty_remaining > tol:
                    try:
                        self.log(
                            f"{symbol}@{interval_text or 'default'} fallback close incomplete for {indicator_key}: "
                            f"residual {qty_remaining:.10f} {side_norm} still open."
                        )
                    except Exception:
                        pass
            else:
                success, res = self._execute_close_with_fallback(
                    symbol,
                    close_side,
                    qty_remaining,
                    position_side,
                )
                if success:
                    payload = self._build_close_event_payload(
                        symbol,
                        interval_text or cw.get("interval") or "default",
                        side_norm,
                        qty_remaining,
                        res,
                    )
                    if isinstance(reason, str) and reason.strip():
                        payload["reason"] = reason.strip()
                    try:
                        self._notify_interval_closed(
                            symbol,
                            interval_text or cw.get("interval") or "default",
                            side_norm,
                            **payload,
                        )
                    except Exception:
                        pass
                    try:
                        self._mark_guard_closed(symbol, interval_text or cw.get("interval"), side_norm)
                    except Exception:
                        pass
                    try:
                        if indicator_lookup_key:
                            self._purge_indicator_tracking(
                                symbol,
                                interval_text or cw.get("interval"),
                                indicator_lookup_key,
                                side_norm,
                            )
                    except Exception:
                        pass
                    closed_count += 1
                    total_qty_closed += qty_remaining
                    if limit_remaining is not None:
                        limit_remaining = max(0.0, limit_remaining - qty_remaining)
                else:
                    try:
                        self.log(
                            f"{symbol}@{interval_text or 'default'} fallback close failed for indicator {indicator_key}: {res}"
                        )
                    except Exception:
                        pass
    self._exit_close_guard(symbol, side_norm)
    return closed_count, total_qty_closed


def bind_strategy_position_close_runtime(strategy_cls) -> None:
    strategy_cls._apply_entire_account_stop_loss = _apply_entire_account_stop_loss
    strategy_cls._close_indicator_positions = _close_indicator_positions
    strategy_cls._execute_close_with_fallback = _execute_close_with_fallback
    strategy_cls._close_leg_entry = _close_leg_entry
    strategy_cls._evaluate_per_trade_stop = _evaluate_per_trade_stop
