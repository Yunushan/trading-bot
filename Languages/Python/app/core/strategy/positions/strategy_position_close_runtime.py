from __future__ import annotations

from collections.abc import Iterable

from .close_execution import (
    _apply_entire_account_stop_loss,
    _close_leg_entry,
    _evaluate_per_trade_stop,
    _execute_close_with_fallback,
)


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
