from __future__ import annotations

from collections.abc import Iterable
import time


def _close_opposite_position(
    self,
    symbol: str,
    interval: str,
    next_side: str,
    trigger_signature: tuple[str, ...] | None = None,
    indicator_key: Iterable[str] | str | None = None,
    target_qty: float | None = None,
) -> bool:
    """Ensure no conflicting exposure remains before opening a new leg."""
    interval_norm = str(interval or "").strip()
    interval_tokens = self._tokenize_interval_label(interval_norm)
    interval_norm_lower = interval_norm.lower()
    interval_has_filter = interval_tokens != {"-"}
    indicator_tokens = self._normalize_indicator_token_list(indicator_key)
    if not indicator_tokens:
        indicator_tokens = self._normalize_indicator_token_list(
            self._indicator_token_from_signature(trigger_signature)
        )
    signature_hint_tokens = self._normalize_signature_tokens_no_slots(trigger_signature)
    allow_opposite_requested = self._strategy_coerce_bool(self.config.get("allow_opposite_positions"), True)
    interval_norm_guard = None
    if allow_opposite_requested:
        if indicator_tokens and not signature_hint_tokens:
            # Enforce per-indicator scoping when hedge stacking; use indicator tokens as the signature guard.
            signature_hint_tokens = tuple(indicator_tokens)
        if interval_tokens:
            # Never allow a different interval to close when hedge stacking; require exact interval tokens.
            interval_norm_guard = tuple(sorted(interval_tokens))

    try:
        positions = self.binance.list_open_futures_positions(max_age=0.0, force_refresh=True) or []
    except Exception as e:
        self.log(f"{symbol}@{interval} read positions failed: {e}")
        return False

    def _refresh_positions_snapshot() -> list[dict] | None:
        try:
            return self.binance.list_open_futures_positions(max_age=0.0, force_refresh=True) or []
        except Exception as refresh_exc:
            try:
                self.log(f"{symbol}@{interval} close-opposite refresh failed: {refresh_exc}")
            except Exception:
                pass
            return None

    desired = (next_side or '').upper()
    if desired not in ('BUY', 'SELL'):
        return True
    try:
        dual = bool(self.binance.get_futures_dual_side())
    except Exception:
        dual = False

    opp = 'SELL' if desired == 'BUY' else 'BUY'
    warn_key = (str(symbol or "").upper(), interval_norm_lower or "default", opp)
    warn_oneway_needed = bool(indicator_tokens and allow_opposite_requested and not dual)
    allow_hedge_scope_only = bool(allow_opposite_requested)
    strict_flip_guard = self._strategy_coerce_bool(self.config.get("strict_indicator_flip_enforcement"), True)
    # Safety: in dual-side hedge accounts, never issue a broad symbol close without indicator/sig context.
    if dual and not indicator_tokens and not signature_hint_tokens:
        try:
            self.log(
                f"{symbol}@{interval_norm or 'default'} close-opposite skipped (hedge scope missing)."
            )
        except Exception:
            pass
        return True

    # Hedge isolation: only close opposite legs when we have an explicit indicator+signature scope.
    if allow_opposite_requested:
        if not indicator_tokens or not signature_hint_tokens:
            try:
                self.log(
                    f"{symbol}@{interval_norm or 'default'} close-opposite skipped (hedge isolation, missing indicator/signature)."
                )
            except Exception:
                pass
            return True
    # In strict mode, never close indicator-scoped exposure without an explicit opposite signature.
    if strict_flip_guard and indicator_tokens and not signature_hint_tokens:
        try:
            self.log(
                f"{symbol}@{interval_norm or 'default'} close-opposite skipped: missing opposite signature for "
                f"{', '.join(indicator_tokens)}."
            )
        except Exception:
            pass
        return True

    # When hedge stacking is allowed and we cannot identify an indicator scope,
    # avoid broad symbol-level closes that could flatten unrelated strategies.
    if allow_opposite_requested and (not indicator_tokens or not signature_hint_tokens or not interval_norm):
        try:
            self.log(
                f"{symbol}@{interval_norm or 'default'} close-opposite skipped: "
                f"hedge stacking enabled and no indicator scope available."
            )
        except Exception:
            pass
        return True
    # Extra isolation: in hedge/stacking mode, require both interval and indicator signature guards.
    if allow_opposite_requested and indicator_tokens:
        if not interval_tokens or interval_norm_guard is None or not signature_hint_tokens:
            try:
                self.log(
                    f"{symbol}@{interval_norm or 'default'} close-opposite skipped: "
                    f"hedge isolation guard (missing interval/signature guard)."
                )
            except Exception:
                pass
            return True
    # Extra guard: never let a different interval close when hedge stacking.
    if allow_opposite_requested and interval_norm_guard:
        other_iv = self._tokenize_interval_label(interval_norm)
        if set(interval_norm_guard) != other_iv:
            try:
                self.log(
                    f"{symbol}@{interval_norm or 'default'} close-opposite blocked: "
                    f"interval mismatch (guard {interval_norm_guard}, got {sorted(other_iv)})."
                )
            except Exception:
                pass
            return True

    def _warn_oneway_overlap() -> None:
        warned = getattr(self, "_oneway_overlap_warned", set())
        if warn_key in warned:
            return
        warned.add(warn_key)
        self._oneway_overlap_warned = warned
        indicator_label = ", ".join(indicator_tokens) or opp
        try:
            self.log(
                f"{symbol}@{interval_norm or 'default'} {indicator_label} blocked: Binance Futures account is in one-way mode. "
                "Enable hedge (dual-side) mode to run opposite signals or disable 'allow opposite positions'."
            )
        except Exception:
            pass
    closed_any = False
    indicator_target_cleared = False
    try:
        qty_goal = float(target_qty) if target_qty is not None else None
    except Exception:
        qty_goal = None
    qty_tol = 1e-9

    # Indicator-scoped early exit: if no opposite exposure exists (ledger, trade book, or exchange),
    # do nothing so we never flatten unrelated legs.
    if indicator_tokens:
        try:
            live_opp_qty = self._indicator_open_qty(
                symbol,
                interval_norm,
                indicator_tokens[0],
                opp,
                interval_aliases=interval_tokens,
                strict_interval=True,
            )
        except Exception:
            live_opp_qty = 0.0
        if live_opp_qty <= qty_tol:
            try:
                live_opp_qty = self._indicator_trade_book_qty(symbol, interval_norm, indicator_tokens[0], opp)
            except Exception:
                pass
        # Even in hedge mode, fall back to live exchange exposure so explicit counter-signals
        # can flip the position when ledger/trade book tracking is missing.
        if live_opp_qty <= qty_tol:
            try:
                live_opp_qty = max(
                    0.0,
                    float(self._current_futures_position_qty(symbol, opp, None) or 0.0),
                )
            except Exception:
                live_opp_qty = 0.0
        if (qty_goal is None and live_opp_qty <= qty_tol) or (qty_goal is not None and qty_goal <= qty_tol and live_opp_qty <= qty_tol):
            return True

    def _reduce_goal(delta: float) -> None:
        nonlocal qty_goal
        if qty_goal is None:
            return
        qty_goal = max(0.0, qty_goal - max(0.0, delta))

    def _goal_met() -> bool:
        return qty_goal is not None and qty_goal <= qty_tol

    if _goal_met():
        return True

    def _close_interval_side_entries(
                indicator_filter: str | None,
                signature_filter: tuple[str, ...] | None,
                qty_limit: float | None,
            ) -> tuple[int, bool, float]:
        """Close ledger-tracked entries for this symbol/interval/opposite side."""
        closed_entries = 0
        failed = False
        qty_closed = 0.0
        indicator_filter_norm = self._canonical_indicator_token(indicator_filter) or ""
        signature_filter = (
            tuple(str(token or "").strip().lower() for token in (signature_filter or ()) if str(token or "").strip())
            or None
        )
        limit_remaining = None
        limit_tol = 1e-9
        if qty_limit is not None:
            try:
                limit_remaining = max(0.0, float(qty_limit))
            except Exception:
                limit_remaining = 0.0
        # Only touch ledger entries that match symbol, interval, side, and indicator scope.
        for leg_key in list(self._leg_ledger.keys()):
            if limit_remaining is not None and limit_remaining <= limit_tol:
                break
            leg_sym, leg_interval, leg_side = leg_key
            if str(leg_sym or "").upper() != symbol:
                continue
            leg_interval_norm = str(leg_interval or "").strip()
            # When an indicator/interval scope is provided, require exact interval text match to avoid
            # closing other timeframes (e.g., 3m) when acting on a 1m signal.
            if indicator_filter_norm and interval_norm and leg_interval_norm != interval_norm:
                continue
            leg_tokens = self._tokenize_interval_label(leg_interval_norm)
            if interval_has_filter and leg_tokens.isdisjoint(interval_tokens):
                continue
            # Hedge/stacking: require exact interval match if a guard is present.
            if interval_norm_guard and leg_tokens != set(interval_norm_guard):
                continue
            leg_side_norm = str(leg_side or "").upper()
            if leg_side_norm in {"LONG", "SHORT"}:
                leg_side_norm = "BUY" if leg_side_norm == "LONG" else "SELL"
            if leg_side_norm != opp:
                continue
            entries = list(self._leg_entries(leg_key))
            if not entries:
                continue
            interval_for_entry = leg_interval if leg_interval is not None else interval_norm or "default"
            cw_ctx = {"symbol": leg_sym, "interval": interval_for_entry}
            for entry in entries:
                entry_keys = self._extract_indicator_keys(entry)
                if indicator_filter_norm:
                    matches_filter = any(
                        (self._canonical_indicator_token(key) or str(key or "").strip().lower()) == indicator_filter_norm
                        for key in entry_keys
                    )
                    if not matches_filter:
                        continue
                    # Require explicit trigger signature to include the indicator filter.
                    entry_sig_tokens = self._normalize_signature_tokens_no_slots(
                        entry.get("trigger_signature") or entry.get("trigger_indicators")
                    )
                    if indicator_filter_norm not in (entry_sig_tokens or ()):
                        continue
                    # Require the stored indicator list to include the filter as well.
                    entry_inds = [
                        self._canonical_indicator_token(key) or str(key or "").strip().lower() for key in entry_keys
                    ]
                    if entry_inds and indicator_filter_norm not in entry_inds:
                        continue
                if signature_filter:
                    entry_sig = self._normalize_signature_tokens_no_slots(
                        entry.get("trigger_signature") or entry.get("trigger_indicators")
                    )
                    if tuple(entry_sig or ()) != signature_filter:
                        continue
                try:
                    key_guard = (
                        leg_sym,
                        leg_interval_norm,
                        indicator_filter_norm or tuple(entry_keys) or None,
                        leg_side_norm,
                    )
                    already = getattr(self, "_close_leg_guard", set())
                    if key_guard in already:
                        continue
                except Exception:
                    key_guard = None
                indicator_hold_key = indicator_filter_norm or (entry_keys[0] if entry_keys else None)
                if indicator_hold_key:
                    try:
                        interval_seconds_entry = float(_interval_to_seconds(str(interval_for_entry or "1m")))
                    except Exception:
                        interval_seconds_entry = 60.0
                    if not self._indicator_hold_ready(
                        entry.get("timestamp"),
                        leg_sym,
                        interval_for_entry,
                        indicator_hold_key,
                        leg_side_norm,
                        interval_seconds_entry,
                    ):
                        continue
                close_side = 'SELL' if leg_side_norm == 'BUY' else 'BUY'
                position_side = None
                if dual:
                    position_side = 'LONG' if leg_side_norm == 'BUY' else 'SHORT'
                try:
                    qty_request = limit_remaining if limit_remaining is not None else None
                    closed_qty = self._close_leg_entry(
                        cw_ctx,
                        leg_key,
                        entry,
                        leg_side_norm,
                        close_side,
                        position_side,
                        loss_usdt=0.0,
                        price_pct=0.0,
                        margin_pct=0.0,
                        qty_limit=qty_request,
                        queue_flip=bool(indicator_filter_norm),
                    )
                    if closed_qty > 0.0:
                        closed_entries += 1
                        qty_closed += closed_qty
                        if limit_remaining is not None:
                            limit_remaining = max(0.0, limit_remaining - closed_qty)
                        if key_guard is not None:
                            try:
                                already = getattr(self, "_close_leg_guard", set())
                                already.add(key_guard)
                                self._close_leg_guard = already
                            except Exception:
                                pass
                    else:
                        failed = True
                        break
                except Exception as entry_exc:
                    try:
                        self.log(
                            f"{symbol}@{interval_norm or leg_interval} close-opposite ledger entry failed: {entry_exc}"
                        )
                    except Exception:
                        pass
                    failed = True
                    break
            if failed:
                break
            if indicator_filter_norm and limit_remaining is not None and limit_remaining <= limit_tol:
                break
        return closed_entries, failed, qty_closed

    indicator_position_side = None
    if dual:
        indicator_position_side = 'LONG' if opp == 'BUY' else 'SHORT'
    if indicator_tokens:
        cw_stub = {"symbol": symbol, "interval": interval_norm}
        indicator_target_cleared = True
        for indicator_hint in indicator_tokens:
            closed_count = 0
            closed_qty_total = 0.0
            try:
                closed_count, closed_qty_total = self._close_indicator_positions(
                    cw_stub,
                    interval_norm,
                    indicator_hint,
                    opp,
                    indicator_position_side,
                    signature_hint=signature_hint_tokens,
                    ignore_hold=True,
                    qty_limit=qty_goal,
                    strict_interval=True,
                    allow_hedge_close=True,
                )
            except Exception as exc:
                try:
                    self.log(f"{symbol}@{interval} indicator-close {indicator_hint} failed: {exc}")
                except Exception:
                    pass
            if closed_count:
                closed_any = True
                _reduce_goal(closed_qty_total)
                try:
                    ctx_interval = interval_norm or "default"
                    self.log(
                        f"{symbol}@{ctx_interval} flip {indicator_hint}: closed {closed_count} {opp} leg(s) before opening {next_side}."
                    )
                except Exception:
                    pass
                refreshed = _refresh_positions_snapshot()
                if refreshed is None:
                    return False
                positions = refreshed
                if _goal_met():
                    return True
            try:
                indicator_clear = not self._indicator_has_open(symbol, interval_norm, indicator_hint, opp)
            except Exception:
                indicator_clear = False
            indicator_target_cleared = indicator_target_cleared and indicator_clear
            if _goal_met():
                return True

    # Indicator safety: when handling a per-indicator flip, never proceed to symbol-level closes.
    # Only if indicator_target_cleared and a specific qty_goal was requested do we consider the flip done.
    if indicator_tokens:
        if indicator_target_cleared:
            return True if qty_goal is None else _goal_met()
        # If the indicator target is not cleared, abort to avoid touching other indicator legs.
        return False
    # Guard: when a specific indicator scope was requested but not cleared, never escalate to symbol-level closes.
    if signature_hint_tokens and not indicator_target_cleared:
        return False
    # Final guard: in hedge/stacking mode never perform symbol-level closes here; only indicator-scoped flips are allowed.
    if allow_opposite_requested:
        return True

    def _has_opposite_live(pos_iterable) -> bool:
        tol = 1e-9
        for pos in pos_iterable:
            if str(pos.get('symbol') or '').upper() != symbol:
                continue
            pos_side = str(pos.get('positionSide') or pos.get('positionside') or 'BOTH').upper()
            amt_val = float(pos.get('positionAmt') or 0.0)
            if opp == 'BUY':
                if (pos_side == 'LONG' and amt_val > tol) or (pos_side in {'BOTH', ''} and amt_val > tol):
                    return True
            else:
                if (pos_side == 'SHORT' and amt_val < -tol) or (pos_side in {'BOTH', ''} and amt_val < -tol):
                    return True
        return False

    if warn_oneway_needed and not allow_opposite_requested:
        try:
            if _has_opposite_live(positions):
                _warn_oneway_overlap()
                return False
        except Exception:
            _warn_oneway_overlap()
            return False

    if dual and indicator_tokens and indicator_target_cleared:
        if qty_goal is not None:
            if _goal_met():
                return True
        else:
            return True

    ledger_closed = 0
    ledger_failed = False
    ledger_qty_closed = 0.0
    if indicator_tokens:
        for indicator_hint in indicator_tokens:
            closed, failed, qty = _close_interval_side_entries(indicator_hint, signature_hint_tokens, qty_goal)
            ledger_closed += closed
            ledger_qty_closed += qty
            if failed:
                ledger_failed = True
                break
    else:
        ledger_closed, ledger_failed, ledger_qty_closed = _close_interval_side_entries(
            None, signature_hint_tokens, qty_goal
        )
    if ledger_failed:
        try:
            self.log(
                f"{symbol}@{interval_norm or 'default'} flip aborted: failed to close existing {opp} ledger entries."
            )
        except Exception:
            pass
        return False
    if ledger_closed:
        closed_any = True
        _reduce_goal(ledger_qty_closed)
        refreshed = _refresh_positions_snapshot()
        if refreshed is None:
            return False
        positions = refreshed
        if _goal_met():
            return True
    if dual:
        if qty_goal is not None:
            if _goal_met():
                return True
        elif indicator_tokens and indicator_target_cleared:
            return True
        elif not _has_opposite_live(positions):
            return True
    elif _goal_met():
        return True

    if indicator_tokens and not indicator_target_cleared:
        if not self._strategy_coerce_bool(self.config.get("allow_close_ignoring_hold"), False):
            now_hold_ts = time.time()
            hold_ready_any = False
            hold_candidate_seen = False
            remaining_values: list[float] = []
            for indicator_hint in indicator_tokens:
                for leg_key, entry in self._iter_indicator_entries(symbol, interval_norm, indicator_hint, opp):
                    try:
                        ts_val = float(entry.get("timestamp") or 0.0)
                    except Exception:
                        ts_val = 0.0
                    if ts_val <= 0.0:
                        continue
                    hold_candidate_seen = True
                    interval_seconds_entry = self._interval_seconds_value(leg_key[1] or interval_norm)
                    effective_hold = max(
                        max(0.0, float(getattr(self, "_indicator_min_hold_seconds", 0.0) or 0.0)),
                        max(0, int(getattr(self, "_indicator_min_hold_bars", 0) or 0)) * interval_seconds_entry,
                    )
                    if effective_hold <= 0.0:
                        hold_ready_any = True
                        break
                    age = max(0.0, now_hold_ts - ts_val)
                    if age >= effective_hold:
                        hold_ready_any = True
                        break
                    remaining_values.append(max(0.0, effective_hold - age))
                if hold_ready_any:
                    break
            if hold_candidate_seen and not hold_ready_any:
                try:
                    wait_s = min(remaining_values) if remaining_values else 0.0
                    indicator_label = ", ".join(indicator_tokens)
                    self.log(
                        f"{symbol}@{interval_norm or 'default'} flip blocked by hold guard for {indicator_label} "
                        f"{opp} leg (wait ~{wait_s:.1f}s)."
                    )
                except Exception:
                    pass
                return False
        indicator_label = ", ".join(indicator_tokens)
        indicator_primary = indicator_tokens[0] if indicator_tokens else None
        protect_other_legs = False
        try:
            protect_other_legs = self._symbol_side_has_other_positions(
                symbol,
                interval_norm,
                indicator_primary,
                opp,
            )
        except Exception:
            protect_other_legs = False
        if protect_other_legs:
            try:
                self.log(
                    f"{symbol}@{interval_norm or 'default'} flip blocked: other {opp} legs "
                    f"are active on this symbol ({indicator_label})."
                )
            except Exception:
                pass
            return False
        residual_qty = 0.0
        for indicator_hint in indicator_tokens:
            try:
                qty_val = self._indicator_live_qty_total(
                    symbol,
                    interval_norm,
                    indicator_hint,
                    opp,
                    interval_aliases=interval_tokens,
                    strict_interval=True,
                    use_exchange_fallback=True,
                )
            except Exception:
                qty_val = 0.0
            residual_qty = max(residual_qty, qty_val)
        residual_tol = max(1e-9, residual_qty * 1e-6)
        if residual_qty <= residual_tol:
            # Reconcile stale indicator tracking instead of hard-blocking the flip.
            try:
                for indicator_hint in indicator_tokens:
                    self._purge_indicator_tracking(symbol, interval_norm, indicator_hint, opp)
            except Exception:
                pass
            indicator_target_cleared = True
            if qty_goal is None:
                return True
            return _goal_met()
        qty_hint = residual_qty
        if qty_goal is not None and qty_goal > 0.0:
            qty_hint = min(qty_hint, qty_goal)
        if qty_hint > 0.0:
            success, close_res = self._execute_close_with_fallback(
                symbol,
                opp,
                qty_hint,
                indicator_position_side,
            )
            if success:
                closed_any = True
                _reduce_goal(qty_hint)
                try:
                    self._mark_guard_closed(symbol, interval_norm, opp)
                    # Also clear any stale indicator tracking so future entries aren't suppressed.
                    self._purge_indicator_tracking(symbol, interval_norm, indicator_primary or indicator_tokens[0], opp)
                except Exception:
                    pass
                refreshed = _refresh_positions_snapshot()
                if refreshed is None:
                    return False
                positions = refreshed
                indicator_target_cleared = True
                ledger_closed = 1
                ledger_qty_closed = qty_hint
                if _goal_met():
                    return True
            else:
                try:
                    indicator_label = ", ".join(indicator_tokens)
                    self.log(
                        f"{symbol}@{interval_norm or 'default'} flip blocked: residual {indicator_label} {opp} leg "
                        f"could not be closed ({close_res})."
                    )
                except Exception:
                    pass
                return False
        else:
            try:
                indicator_label = ", ".join(indicator_tokens)
                self.log(f"{symbol}@{interval_norm or 'default'} flip skipped: no {indicator_label} {opp} leg to close.")
            except Exception:
                pass
            indicator_target_cleared = True
            if qty_goal is None:
                return True
            return _goal_met()

    # If an indicator was provided, stop here. We never want to close unrelated symbol-side
    # exposure beyond the indicator/interval scope.
    if indicator_tokens:
        return True if qty_goal is None else _goal_met()

    opp_key = (symbol, interval, opp)
    for p in positions:
        try:
            if str(p.get('symbol') or '').upper() != symbol:
                continue
            amt = float(p.get('positionAmt') or 0.0)
            position_side_flag = None
            if dual:
                pos_side = str(p.get('positionSide') or p.get('positionside') or '').upper()
                if pos_side in {'LONG', 'SHORT'}:
                    position_side_flag = pos_side
                else:
                    position_side_flag = 'LONG' if amt > 0 else 'SHORT'
            if desired == 'BUY' and amt < 0:
                qty = abs(amt)
                if qty_goal is not None:
                    if _goal_met():
                        break
                    qty = min(qty, qty_goal)
                success, res = self._execute_close_with_fallback(
                    symbol,
                    'BUY',
                    qty,
                    position_side_flag if dual else None,
                )
                if not success:
                    self.log(f"{symbol}@{interval} close-short failed: {res}")
                    return False
                payload = self._build_close_event_payload(symbol, interval, 'SELL', qty, res)
                self._notify_interval_closed(symbol, interval, 'SELL', **payload)
                try:
                    self._mark_guard_closed(symbol, interval, 'SELL')
                    self._purge_indicator_tracking(symbol, interval, indicator_tokens[0] if indicator_tokens else None, 'SELL')
                except Exception:
                    pass
                closed_any = True
                _reduce_goal(qty)
                if _goal_met():
                    break
            elif desired == 'SELL' and amt > 0:
                qty = abs(amt)
                if qty_goal is not None:
                    if _goal_met():
                        break
                    qty = min(qty, qty_goal)
                success, res = self._execute_close_with_fallback(
                    symbol,
                    'SELL',
                    qty,
                    position_side_flag if dual else None,
                )
                if not success:
                    self.log(f"{symbol}@{interval} close-long failed: {res}")
                    return False
                payload = self._build_close_event_payload(symbol, interval, 'BUY', qty, res)
                self._notify_interval_closed(symbol, interval, 'BUY', **payload)
                try:
                    self._mark_guard_closed(symbol, interval, 'BUY')
                    self._purge_indicator_tracking(symbol, interval, indicator_tokens[0] if indicator_tokens else None, 'BUY')
                except Exception:
                    pass
                closed_any = True
                _reduce_goal(qty)
                if _goal_met():
                    break
        except Exception as exc:
            self.log(f"{symbol}@{interval} close-opposite exception: {exc}")
            return False
    if closed_any:
        try:
            import time as _t
            for _ in range(6):
                positions_refresh = self.binance.list_open_futures_positions(max_age=0.0, force_refresh=True) or []
                still_opposite = False
                for pos in positions_refresh:
                    if str(pos.get('symbol') or '').upper() != symbol:
                        continue
                    amt_chk = float(pos.get('positionAmt') or 0.0)
                    if (opp == 'SELL' and amt_chk < 0) or (opp == 'BUY' and amt_chk > 0):
                        still_opposite = True
                        break
                if not still_opposite:
                    break
                _t.sleep(0.15)
        except Exception:
            pass
        for key in list(self._leg_ledger.keys()):
            if key[0] == symbol and key[2] == opp:
                self._remove_leg_entry(key, None)
                self._guard_mark_leg_closed(key)
    # Reconcile state if the exchange shows no open amounts (e.g., liquidations flattened exposure).
    try:
        positions_latest = self.binance.list_open_futures_positions(max_age=0.0, force_refresh=True) or []
        live_qty_latest = 0.0
        for pos in positions_latest:
            if str(pos.get('symbol') or '').upper() != symbol:
                continue
            try:
                live_qty_latest = max(live_qty_latest, abs(float(pos.get('positionAmt') or 0.0)))
            except Exception:
                continue
        if live_qty_latest <= qty_tol:
            for key in list(self._leg_ledger.keys()):
                if key[0] != symbol:
                    continue
                self._remove_leg_entry(key, None)
                self._guard_mark_leg_closed(key)
    except Exception:
        pass
    return True

def _reconcile_liquidations(self, symbol: str) -> None:
    """Clear internal state for a symbol if exchange shows no exposure (e.g., liquidation)."""
    try:
        positions = self.binance.list_open_futures_positions(max_age=0.0, force_refresh=True) or []
    except Exception:
        # Do not mutate miss counters on API failure; treat as inconclusive.
        return
    try:
        dual_mode = bool(self.binance.get_futures_dual_side())
    except Exception:
        dual_mode = False
    tol = 1e-9
    long_active = False
    short_active = False
    for pos in positions:
        if str(pos.get("symbol") or "").upper() != str(symbol or "").upper():
            continue
        try:
            amt_val = float(pos.get("positionAmt") or 0.0)
        except Exception:
            amt_val = 0.0
        pos_side = str(pos.get("positionSide") or pos.get("positionside") or "BOTH").upper()
        if dual_mode:
            if pos_side == "LONG" and amt_val > tol:
                long_active = True
            elif pos_side == "SHORT" and amt_val < -tol:
                short_active = True
            elif pos_side in {"BOTH", ""}:
                if amt_val > tol:
                    long_active = True
                elif amt_val < -tol:
                    short_active = True
        else:
            if amt_val > tol:
                long_active = True
            elif amt_val < -tol:
                short_active = True
    # Debounce: require two consecutive "no exposure" reads before purging local state.
    sym_norm = str(symbol or "").upper()
    if long_active or short_active:
        self._reconcile_miss_counts[sym_norm] = 0
        return
    miss_count = self._reconcile_miss_counts.get(sym_norm, 0) + 1
    self._reconcile_miss_counts[sym_norm] = miss_count
    if miss_count <= 1:
        # First miss: wait for a confirming read before clearing.
        return
    self._reconcile_miss_counts[sym_norm] = 0
    for key in list(self._leg_ledger.keys()):
        leg_sym, _, leg_side = key
        if str(leg_sym or "").upper() != str(symbol or "").upper():
            continue
        leg_side_norm = str(leg_side or "").upper()
        side_is_long = leg_side_norm in {"BUY", "LONG"}
        side_is_short = leg_side_norm in {"SELL", "SHORT"}
        clear_side = (side_is_long and not long_active) or (side_is_short and not short_active)
        if not clear_side:
            continue
        entries = self._leg_entries(key) or []
        for entry in entries:
            try:
                self._mark_indicator_reentry_signal_block(
                    symbol,
                    key[1],
                    entry,
                    leg_side_norm,
                )
            except Exception:
                pass
            try:
                for indicator_key in self._extract_indicator_keys(entry):
                    self._record_indicator_close(symbol, key[1], indicator_key, leg_side_norm, entry.get("qty"))
            except Exception:
                pass
            try:
                self._queue_flip_on_close(key[1], leg_side_norm, entry, None)
            except Exception:
                pass
        for entry in entries:
            for ind in self._extract_indicator_keys(entry):
                try:
                    self._purge_indicator_tracking(symbol, key[1], ind, leg_side_norm)
                except Exception:
                    pass
        self._remove_leg_entry(key, None)
        self._guard_mark_leg_closed(key)
# ---- indicator computation (uses pandas_ta when available)


def bind_strategy_position_flip_runtime(strategy_cls) -> None:
    strategy_cls._close_opposite_position = _close_opposite_position
