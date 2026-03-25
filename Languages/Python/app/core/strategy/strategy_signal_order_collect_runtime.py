from __future__ import annotations

import time


def _indicator_exchange_qty(self, symbol: str, side_label: str, desired_ps: str | None) -> float:
    try:
        return max(
            0.0,
            float(self._current_futures_position_qty(symbol, side_label, desired_ps) or 0.0),
        )
    except Exception:
        return 0.0


def _purge_indicator_side_if_exchange_flat(
    self,
    *,
    symbol: str,
    interval_current,
    indicator_key: str,
    side_label: str,
    desired_ps: str | None,
    tracked_qty: float,
) -> float:
    if tracked_qty <= 0.0:
        return tracked_qty
    exch_qty = _indicator_exchange_qty(self, symbol, side_label, desired_ps)
    tol_live = max(1e-9, exch_qty * 1e-6)
    if exch_qty <= tol_live:
        try:
            self._purge_indicator_tracking(symbol, interval_current, indicator_key, side_label)
        except Exception:
            pass
        return 0.0
    return tracked_qty


def _build_directional_indicator_order_request(
    self,
    *,
    cw,
    interval_current,
    indicator_key: str,
    indicator_label: str,
    target_side: str,
    desired_ps_target: str | None,
    desired_ps_opposite: str | None,
    indicator_interval_tokens: set[str],
    qty_tol_indicator: float,
    reason_signal: str,
    recent_close,
    now_indicator_ts: float,
) -> dict[str, object] | None:
    symbol = cw["symbol"]
    target_side = str(target_side or "").upper()
    if target_side not in {"BUY", "SELL"}:
        return None
    opposite_side = "SELL" if target_side == "BUY" else "BUY"
    remaining_opposite_qty = self._indicator_open_qty(
        symbol,
        interval_current,
        indicator_key,
        opposite_side,
        interval_aliases=indicator_interval_tokens,
        strict_interval=True,
    )
    if remaining_opposite_qty <= qty_tol_indicator:
        fallback_live_qty = self._indicator_trade_book_qty(
            symbol,
            interval_current,
            indicator_key,
            opposite_side,
        )
        if fallback_live_qty <= qty_tol_indicator:
            fallback_live_qty = _indicator_exchange_qty(
                self,
                symbol,
                opposite_side,
                desired_ps_opposite,
            )
        if fallback_live_qty > qty_tol_indicator:
            remaining_opposite_qty = fallback_live_qty

    closed_opposite = 0
    closed_opposite_qty = 0.0
    qty_cap = remaining_opposite_qty if remaining_opposite_qty > qty_tol_indicator else None
    if remaining_opposite_qty > qty_tol_indicator:
        closed_opposite, closed_opposite_qty = self._close_indicator_positions(
            cw,
            interval_current,
            indicator_key,
            opposite_side,
            desired_ps_opposite,
            signature_hint=(indicator_key,),
            ignore_hold=True,
            interval_aliases=indicator_interval_tokens,
            qty_limit=qty_cap,
            strict_interval=True,
            allow_hedge_close=True,
            reason=reason_signal,
        )
        if closed_opposite <= 0:
            try:
                still_open = self._indicator_has_open(
                    symbol, interval_current, indicator_key, opposite_side
                )
            except Exception:
                still_open = False
            if still_open:
                target_qty_hint = qty_cap
                if (target_qty_hint is None or target_qty_hint <= 0.0) and remaining_opposite_qty > 0.0:
                    target_qty_hint = remaining_opposite_qty
                if not self._close_opposite_position(
                    symbol,
                    interval_current,
                    target_side,
                    trigger_signature=(indicator_key,),
                    indicator_key=(indicator_key,),
                    target_qty=target_qty_hint,
                ):
                    return None
                closed_opposite = 1

    if closed_opposite <= 0:
        fallback_qty = self._indicator_trade_book_qty(
            symbol,
            interval_current,
            indicator_key,
            opposite_side,
        )
        if fallback_qty <= 0.0:
            fallback_qty = _indicator_exchange_qty(
                self,
                symbol,
                opposite_side,
                desired_ps_opposite,
            )
        if fallback_qty > 0.0:
            retry_count, retry_qty = self._close_indicator_positions(
                cw,
                interval_current,
                indicator_key,
                opposite_side,
                desired_ps_opposite,
                signature_hint=(indicator_key,),
                ignore_hold=True,
                interval_aliases=indicator_interval_tokens,
                qty_limit=fallback_qty,
                strict_interval=True,
                allow_hedge_close=True,
                reason=reason_signal,
            )
            closed_opposite = retry_count
            closed_opposite_qty = retry_qty

    if closed_opposite <= 0:
        remaining_opposite_qty = self._indicator_open_qty(
            symbol,
            interval_current,
            indicator_key,
            opposite_side,
            interval_aliases=indicator_interval_tokens,
            strict_interval=True,
        )
        remaining_opposite_qty = _purge_indicator_side_if_exchange_flat(
            self,
            symbol=symbol,
            interval_current=interval_current,
            indicator_key=indicator_key,
            side_label=opposite_side,
            desired_ps=desired_ps_opposite,
            tracked_qty=remaining_opposite_qty,
        )
        if remaining_opposite_qty > qty_tol_indicator:
            try:
                self.log(
                    f"{symbol}@{interval_current or 'default'} {indicator_key} {target_side} skipped: "
                    f"{opposite_side.lower()} leg still live on exchange."
                )
            except Exception:
                pass
            return None

    flip_from_side = None
    flip_qty = 0.0
    flip_qty_target = 0.0
    remaining_opposite_qty = self._indicator_open_qty(
        symbol,
        interval_current,
        indicator_key,
        opposite_side,
        interval_aliases=indicator_interval_tokens,
        strict_interval=True,
    )
    if closed_opposite > 0 and closed_opposite_qty > 0.0:
        flip_from_side = opposite_side
        flip_qty = closed_opposite_qty
        flip_qty_target = closed_opposite_qty
        try:
            self.log(
                f"{symbol}@{interval_current} {indicator_key} flip {opposite_side}→{target_side} "
                f"(closed {flip_qty:.10f})."
            )
        except Exception:
            pass
    elif remaining_opposite_qty > 0.0:
        try:
            self.log(
                f"{symbol}@{interval_current or 'default'} {indicator_key} {target_side} deferred: "
                f"{remaining_opposite_qty:.10f} {opposite_side.lower()} qty still open."
            )
        except Exception:
            pass
        return None
    else:
        protect_opposite_residual = self._symbol_side_has_other_positions(
            symbol,
            interval_current,
            indicator_key,
            opposite_side,
        )
        live_opposite_residual = _indicator_exchange_qty(
            self,
            symbol,
            opposite_side,
            desired_ps_opposite,
        )
        tol_live = max(1e-9, live_opposite_residual * 1e-6)
        if protect_opposite_residual and live_opposite_residual > tol_live:
            try:
                self.log(
                    f"{symbol}@{interval_current or 'default'} {indicator_key} {target_side} skipping residual "
                    f"{opposite_side.lower()} close (other {opposite_side} legs still active)."
                )
            except Exception:
                pass
        elif live_opposite_residual > tol_live:
            try:
                self.log(
                    f"{symbol}@{interval_current or 'default'} {indicator_key} {target_side} forcing close of residual "
                    f"{opposite_side.lower()} ({live_opposite_residual:.10f})."
                )
            except Exception:
                pass
            if not self._close_opposite_position(
                symbol,
                interval_current,
                target_side,
                trigger_signature=(indicator_key,),
                indicator_key=(indicator_key,),
                target_qty=live_opposite_residual,
            ):
                return None
            flip_from_side = opposite_side
            flip_qty = live_opposite_residual
            flip_qty_target = live_opposite_residual
        else:
            current_opposite_qty = self._indicator_open_qty(
                symbol,
                interval_current,
                indicator_key,
                opposite_side,
                interval_aliases=indicator_interval_tokens,
                strict_interval=True,
            )
            current_opposite_qty = _purge_indicator_side_if_exchange_flat(
                self,
                symbol=symbol,
                interval_current=interval_current,
                indicator_key=indicator_key,
                side_label=opposite_side,
                desired_ps=desired_ps_opposite,
                tracked_qty=current_opposite_qty,
            )
            if current_opposite_qty > qty_tol_indicator and closed_opposite_qty <= 0.0 and flip_qty <= 0.0:
                return None

    if closed_opposite > 0 and flip_from_side is None:
        flip_from_side = opposite_side
    if flip_from_side is None and recent_close:
        flip_from_side = opposite_side
        try:
            if flip_qty <= 0.0:
                flip_qty = float(recent_close.get("qty") or 0.0)
            if flip_qty_target <= 0.0 and flip_qty > 0.0:
                flip_qty_target = flip_qty
        except Exception:
            pass

    current_target_qty = self._indicator_open_qty(
        symbol,
        interval_current,
        indicator_key,
        target_side,
        interval_aliases=indicator_interval_tokens,
        strict_interval=True,
    )
    current_target_qty = _purge_indicator_side_if_exchange_flat(
        self,
        symbol=symbol,
        interval_current=interval_current,
        indicator_key=indicator_key,
        side_label=target_side,
        desired_ps=desired_ps_target,
        tracked_qty=current_target_qty,
    )
    if current_target_qty > qty_tol_indicator:
        return None

    bypass_reentry_guard = bool(
        flip_from_side
        or closed_opposite > 0
        or closed_opposite_qty > 0.0
        or flip_qty > 0.0
    )
    if not bypass_reentry_guard:
        reentry_remaining = self._reentry_block_remaining(
            symbol,
            interval_current,
            target_side,
            now_ts=now_indicator_ts,
        )
        if reentry_remaining > 0.0:
            try:
                self.log(
                    f"{symbol}@{interval_current or 'default'} {indicator_key} {target_side} suppressed by "
                    f"re-entry guard ({reentry_remaining:.1f}s)."
                )
            except Exception:
                pass
            return None

    return {
        "side": target_side,
        "labels": [indicator_label],
        "signature": (indicator_key,),
        "indicator_key": indicator_key,
        "flip_from": flip_from_side,
        "flip_qty": flip_qty,
        "flip_qty_target": flip_qty_target,
    }


def _build_fallback_indicator_order_request(
    self,
    *,
    cw,
    interval_current,
    indicator_key: str,
    indicator_label: str,
    target_side: str,
    desired_ps_opposite: str | None,
    indicator_interval_tokens: set[str],
    qty_tol_indicator: float,
    hedge_overlap_allowed: bool,
    now_indicator_ts: float,
) -> dict[str, object] | None:
    symbol = cw["symbol"]
    target_side = str(target_side or "").upper()
    if target_side not in {"BUY", "SELL"}:
        return None
    opposite_side = "SELL" if target_side == "BUY" else "BUY"
    opp_live_qty = 0.0
    try:
        opp_live_qty = self._indicator_live_qty_total(
            symbol,
            interval_current,
            indicator_key,
            opposite_side,
            interval_aliases=indicator_interval_tokens,
            strict_interval=True,
            use_exchange_fallback=False,
        )
    except Exception:
        opp_live_qty = 0.0
    if opp_live_qty <= qty_tol_indicator:
        try:
            account_type = str((self.config.get("account_type") or self.binance.account_type)).upper()
        except Exception:
            account_type = ""
        if account_type == "FUTURES":
            protect_other = False
            try:
                protect_other = self._symbol_side_has_other_positions(
                    symbol, interval_current, indicator_key, opposite_side
                )
            except Exception:
                protect_other = False
            if not protect_other:
                desired_ps_check = None
                try:
                    if self.binance.get_futures_dual_side():
                        desired_ps_check = desired_ps_opposite
                except Exception:
                    desired_ps_check = None
                exch_qty = _indicator_exchange_qty(
                    self,
                    symbol,
                    opposite_side,
                    desired_ps_check,
                )
                if exch_qty > qty_tol_indicator:
                    opp_live_qty = exch_qty
    if opp_live_qty > qty_tol_indicator:
        try:
            self.log(
                f"{symbol}@{interval_current or 'default'} {indicator_key} "
                f"{target_side} skipped: opposite {opposite_side} still open "
                f"({opp_live_qty:.10f})."
            )
            self.log(
                f"{symbol}@{interval_current or 'default'} {indicator_key} "
                f"guard=opp_open skip {target_side}."
            )
        except Exception:
            pass
        return None
    if not hedge_overlap_allowed:
        live_opposite_qty = _indicator_exchange_qty(
            self,
            symbol,
            opposite_side,
            desired_ps_opposite,
        )
        if live_opposite_qty > 0.0:
            try:
                self.log(
                    f"{symbol}@{interval_current or 'default'} {indicator_key} {target_side} skipped:"
                    f" {opposite_side.lower()} leg still live on exchange ({live_opposite_qty:.10f})."
                )
            except Exception:
                pass
            return None
    reentry_remaining = self._reentry_block_remaining(
        symbol,
        interval_current,
        target_side,
        now_ts=now_indicator_ts,
    )
    if reentry_remaining > 0.0:
        try:
            self.log(
                f"{symbol}@{interval_current or 'default'} {indicator_key} {target_side} suppressed by "
                f"re-entry guard ({reentry_remaining:.1f}s)."
            )
        except Exception:
            pass
        return None
    return {
        "side": target_side,
        "labels": [indicator_label],
        "signature": (indicator_key,),
        "indicator_key": indicator_key,
    }


def _build_hedge_indicator_order_request(
    self,
    *,
    cw,
    interval_current,
    indicator_key: str,
    indicator_label: str,
    target_side: str,
    desired_ps_opposite: str | None,
    indicator_interval_tokens: set[str],
    qty_tol_indicator: float,
    reason_signal: str,
) -> tuple[bool, dict[str, object] | None]:
    symbol = cw["symbol"]
    target_side = str(target_side or "").upper()
    if target_side not in {"BUY", "SELL"}:
        return False, None
    opposite_side = "SELL" if target_side == "BUY" else "BUY"

    close_qty = self._indicator_open_qty(
        symbol,
        interval_current,
        indicator_key,
        opposite_side,
        interval_aliases=indicator_interval_tokens,
        strict_interval=True,
    )
    if close_qty <= qty_tol_indicator:
        fallback_live_qty = self._indicator_trade_book_qty(
            symbol,
            interval_current,
            indicator_key,
            opposite_side,
        )
        if fallback_live_qty > qty_tol_indicator:
            close_qty = fallback_live_qty
    if close_qty <= qty_tol_indicator:
        protect_other = False
        try:
            protect_other = self._symbol_side_has_other_positions(
                symbol, interval_current, indicator_key, opposite_side
            )
        except Exception:
            protect_other = False
        if not protect_other:
            exch_qty = _indicator_exchange_qty(
                self,
                symbol,
                opposite_side,
                desired_ps_opposite,
            )
            if exch_qty > qty_tol_indicator:
                close_qty = exch_qty
    if close_qty <= qty_tol_indicator:
        return False, None

    closed_opposite, closed_qty = self._close_indicator_positions(
        cw,
        interval_current,
        indicator_key,
        opposite_side,
        desired_ps_opposite,
        signature_hint=(indicator_key,),
        ignore_hold=True,
        interval_aliases=indicator_interval_tokens,
        qty_limit=close_qty,
        strict_interval=True,
        allow_hedge_close=True,
        reason=reason_signal,
    )
    if closed_opposite <= 0:
        if not self._close_opposite_position(
            symbol,
            interval_current,
            target_side,
            trigger_signature=(indicator_key,),
            indicator_key=(indicator_key,),
            target_qty=close_qty,
        ):
            return True, None
        closed_opposite = 1
        closed_qty = max(closed_qty, close_qty)

    remaining_after_close = self._indicator_open_qty(
        symbol,
        interval_current,
        indicator_key,
        opposite_side,
        interval_aliases=indicator_interval_tokens,
        strict_interval=True,
    )
    remaining_after_close = _purge_indicator_side_if_exchange_flat(
        self,
        symbol=symbol,
        interval_current=interval_current,
        indicator_key=indicator_key,
        side_label=opposite_side,
        desired_ps=desired_ps_opposite,
        tracked_qty=remaining_after_close,
    )
    if remaining_after_close > qty_tol_indicator:
        try:
            self.log(
                f"{symbol}@{interval_current or 'default'} {indicator_key} {target_side} deferred: "
                f"{remaining_after_close:.10f} {opposite_side.lower()} qty still open."
            )
        except Exception:
            pass
        return True, None

    flip_from_side = opposite_side if closed_qty > 0.0 else None
    if closed_opposite > 0 and flip_from_side is None:
        flip_from_side = opposite_side
    flip_qty = closed_qty if closed_qty > 0.0 else 0.0
    return True, {
        "side": target_side,
        "labels": [indicator_label],
        "signature": (indicator_key,),
        "indicator_key": indicator_key,
        "flip_from": flip_from_side,
        "flip_qty": flip_qty,
        "flip_qty_target": flip_qty,
    }


def _prepare_indicator_signal_request_context(
    self,
    *,
    cw,
    indicator_label: str,
    indicator_action,
    account_type: str,
    dual_side: bool,
    qty_tol_indicator: float,
    now_ts: float,
    now_indicator_ts: float,
) -> dict[str, object] | None:
    strategy_type = type(self)
    indicator_key = indicator_label.lower()
    if not indicator_key:
        return None
    action_norm = str(indicator_action or "").strip().lower()
    interval_current = cw.get("interval")
    try:
        interval_seconds_est = float(self._interval_to_seconds(str(interval_current or "1m")))
    except Exception:
        interval_seconds_est = 60.0
    indicator_interval_tokens: set[str] = set(self._tokenize_interval_label(interval_current))
    label_interval_tokens = strategy_type._extract_interval_tokens_from_labels([indicator_label])
    if label_interval_tokens:
        indicator_interval_tokens.update(label_interval_tokens)
    if action_norm not in {"buy", "sell"}:
        return None
    action_side_label = "BUY" if action_norm == "buy" else "SELL"
    opp_side_label = "SELL" if action_side_label == "BUY" else "BUY"
    reason_signal = f"{indicator_key}_{action_norm}_signal"
    recent_close = None
    try:
        recent_close_window = max(5.0, min(interval_seconds_est * 1.5, 600.0))
        recent_close = self._recent_indicator_close(
            cw["symbol"],
            interval_current,
            indicator_key,
            opp_side_label,
            max_age_seconds=recent_close_window,
        )
    except Exception:
        recent_close = None
    same_side_live = self._indicator_live_qty_total(
        cw["symbol"],
        interval_current,
        indicator_key,
        action_side_label,
        interval_aliases=indicator_interval_tokens,
        strict_interval=True,
        use_exchange_fallback=False,
    )
    opp_side_live = self._indicator_live_qty_total(
        cw["symbol"],
        interval_current,
        indicator_key,
        opp_side_label,
        interval_aliases=indicator_interval_tokens,
        strict_interval=True,
        use_exchange_fallback=False,
    )
    if self._indicator_reentry_requires_reset:
        indicator_norm = self._canonical_indicator_token(indicator_key) or indicator_key
        block_key = (
            str(cw["symbol"] or "").upper(),
            str(interval_current or "").strip().lower() or "default",
            indicator_norm,
        )
        block_side = self._indicator_reentry_signal_blocks.get(block_key)
        if block_side == action_side_label and opp_side_live <= qty_tol_indicator:
            try:
                self.log(
                    f"{cw['symbol']}@{interval_current or 'default'} {indicator_norm} {action_side_label} "
                    "blocked: signal has not reset since last close."
                )
            except Exception:
                pass
            return None
    if same_side_live > qty_tol_indicator and opp_side_live <= qty_tol_indicator:
        stale_cleared = False
        if account_type == "FUTURES":
            try:
                desired_ps_check = None
                if dual_side:
                    desired_ps_check = "LONG" if action_side_label == "BUY" else "SHORT"
                exch_qty = _indicator_exchange_qty(
                    self,
                    cw["symbol"],
                    action_side_label,
                    desired_ps_check,
                )
                tol_live = max(1e-9, exch_qty * 1e-6)
                if exch_qty <= tol_live:
                    self._purge_indicator_tracking(
                        cw["symbol"],
                        interval_current,
                        indicator_key,
                        action_side_label,
                    )
                    same_side_live = 0.0
                    stale_cleared = True
                    try:
                        self.log(
                            f"{cw['symbol']}@{interval_current or 'default'} {indicator_key} "
                            f"{action_side_label} stale guard cleared (no live position)."
                        )
                    except Exception:
                        pass
            except Exception:
                stale_cleared = False
        if not stale_cleared:
            return None
    if not self._indicator_signal_confirmation_ready(
        cw["symbol"],
        interval_current,
        indicator_key,
        action_norm,
        interval_seconds_est,
        now_indicator_ts,
    ):
        return None
    cooldown_remaining = self._indicator_cooldown_remaining(
        cw["symbol"],
        interval_current,
        indicator_key,
        action_side_label,
        interval_seconds_est,
        now_indicator_ts,
    )
    if cooldown_remaining > 0.0:
        allow_flip_cooldown_bypass = False
        if opp_side_live > qty_tol_indicator:
            allow_flip_cooldown_bypass = True
        else:
            try:
                opp_live_exch = self._indicator_live_qty_total(
                    cw["symbol"],
                    interval_current,
                    indicator_key,
                    opp_side_label,
                    interval_aliases=indicator_interval_tokens,
                    strict_interval=True,
                    use_exchange_fallback=True,
                )
                if opp_live_exch > qty_tol_indicator:
                    allow_flip_cooldown_bypass = True
            except Exception:
                allow_flip_cooldown_bypass = False
        if not allow_flip_cooldown_bypass and recent_close:
            allow_flip_cooldown_bypass = True
        if not allow_flip_cooldown_bypass:
            try:
                self.log(
                    f"{cw['symbol']}@{interval_current or 'default'} {indicator_key} "
                    f"{action_side_label} suppressed: cooldown {cooldown_remaining:.1f}s remaining."
                )
            except Exception:
                pass
            return None
    reentry_block = self._reentry_block_remaining(
        cw["symbol"], interval_current, action_side_label, now_ts=now_ts
    )
    if reentry_block > 0.0:
        try:
            self.log(
                f"{cw['symbol']}@{interval_current} {action_side_label} re-entry guard: waiting {reentry_block:.1f}s."
            )
        except Exception:
            pass
        return None
    return {
        "indicator_key": indicator_key,
        "action_norm": action_norm,
        "interval_current": interval_current,
        "indicator_interval_tokens": indicator_interval_tokens,
        "action_side_label": action_side_label,
        "opp_side_label": opp_side_label,
        "reason_signal": reason_signal,
        "recent_close": recent_close,
    }


def _prepare_fallback_indicator_request_context(
    self,
    *,
    cw,
    indicator_label: str,
    indicator_action,
    now_indicator_ts: float,
) -> dict[str, object] | None:
    strategy_type = type(self)
    indicator_key = indicator_label.lower()
    if not indicator_key:
        return None
    interval_current = cw.get("interval")
    action_norm = str(indicator_action or "").strip().lower()
    try:
        interval_seconds_est = float(self._interval_to_seconds(str(interval_current or "1m")))
    except Exception:
        interval_seconds_est = 60.0
    if action_norm not in {"buy", "sell"}:
        return None
    if not self._indicator_signal_confirmation_ready(
        cw["symbol"],
        interval_current,
        indicator_key,
        action_norm,
        interval_seconds_est,
        now_indicator_ts,
    ):
        return None
    action_side_label = "BUY" if action_norm == "buy" else "SELL"
    indicator_interval_tokens = set(self._tokenize_interval_label(interval_current))
    label_interval_tokens = strategy_type._extract_interval_tokens_from_labels([indicator_label])
    if label_interval_tokens:
        indicator_interval_tokens.update(label_interval_tokens)
    return {
        "indicator_key": indicator_key,
        "interval_current": interval_current,
        "action_side_label": action_side_label,
        "indicator_interval_tokens": indicator_interval_tokens,
    }


def _collect_indicator_order_requests(
    self,
    *,
    cw,
    trigger_actions,
    dual_side: bool,
    account_type: str,
    allow_opposite_enabled: bool,
    hedge_overlap_allowed: bool,
    now_ts: float,
) -> tuple[list[dict[str, object]], float]:
    indicator_order_requests: list[dict[str, object]] = []
    qty_tol_indicator = 1e-9
    try:
        tol_cfg = float(cw.get("indicator_qty_tolerance") or cw.get("qty_tolerance") or 0.0)
        if tol_cfg > 0.0:
            qty_tol_indicator = max(qty_tol_indicator, tol_cfg)
    except Exception:
        pass
    interval_current = cw.get("interval")
    action_side_map: dict[str, str] = {}
    for indicator_name, indicator_action in (trigger_actions or {}).items():
        indicator_norm = self._canonical_indicator_token(indicator_name) or str(
            indicator_name or ""
        ).strip().lower()
        action_norm = str(indicator_action or "").strip().lower()
        if indicator_norm and action_norm in {"buy", "sell"}:
            action_side_map[indicator_norm] = "BUY" if action_norm == "buy" else "SELL"
    self._refresh_indicator_reentry_signal_blocks(
        cw["symbol"],
        interval_current,
        action_side_map,
    )
    if trigger_actions:
        desired_ps_long = "LONG" if dual_side else None
        desired_ps_short = "SHORT" if dual_side else None
        now_indicator_ts = time.time()
        for indicator_name, indicator_action in trigger_actions.items():
            indicator_label = str(indicator_name or "").strip()
            if not indicator_label:
                continue
            request_ctx = _prepare_indicator_signal_request_context(
                self,
                cw=cw,
                indicator_label=indicator_label,
                indicator_action=indicator_action,
                account_type=account_type,
                dual_side=dual_side,
                qty_tol_indicator=qty_tol_indicator,
                now_ts=now_ts,
                now_indicator_ts=now_indicator_ts,
            )
            if not request_ctx:
                continue
            indicator_key = str(request_ctx["indicator_key"])
            action_side_label = str(request_ctx["action_side_label"])
            interval_current = request_ctx["interval_current"]
            indicator_interval_tokens = set(request_ctx["indicator_interval_tokens"] or ())
            reason_signal = str(request_ctx["reason_signal"])
            recent_close = request_ctx.get("recent_close")

            if allow_opposite_enabled:
                hedge_handled, hedge_request = _build_hedge_indicator_order_request(
                    self,
                    cw=cw,
                    interval_current=interval_current,
                    indicator_key=indicator_key,
                    indicator_label=indicator_label,
                    target_side=action_side_label,
                    desired_ps_opposite=desired_ps_short if action_side_label == "BUY" else desired_ps_long,
                    indicator_interval_tokens=indicator_interval_tokens,
                    qty_tol_indicator=qty_tol_indicator,
                    reason_signal=reason_signal,
                )
                if hedge_handled:
                    if hedge_request is not None:
                        indicator_order_requests.append(hedge_request)
                    continue

            directional_request = _build_directional_indicator_order_request(
                self,
                cw=cw,
                interval_current=interval_current,
                indicator_key=indicator_key,
                indicator_label=indicator_label,
                target_side=action_side_label,
                desired_ps_target=desired_ps_long if action_side_label == "BUY" else desired_ps_short,
                desired_ps_opposite=desired_ps_short if action_side_label == "BUY" else desired_ps_long,
                indicator_interval_tokens=indicator_interval_tokens,
                qty_tol_indicator=qty_tol_indicator,
                reason_signal=reason_signal,
                recent_close=recent_close,
                now_indicator_ts=now_indicator_ts,
            )
            if directional_request is not None:
                indicator_order_requests.append(directional_request)
        if not indicator_order_requests:
            for indicator_name, indicator_action in trigger_actions.items():
                indicator_label = str(indicator_name or "").strip()
                if not indicator_label:
                    continue
                fallback_ctx = _prepare_fallback_indicator_request_context(
                    self,
                    cw=cw,
                    indicator_label=indicator_label,
                    indicator_action=indicator_action,
                    now_indicator_ts=now_indicator_ts,
                )
                if not fallback_ctx:
                    continue
                indicator_key = str(fallback_ctx["indicator_key"])
                interval_current = fallback_ctx["interval_current"]
                action_side_label = str(fallback_ctx["action_side_label"])
                indicator_interval_tokens = set(fallback_ctx["indicator_interval_tokens"] or ())
                fallback_request = _build_fallback_indicator_order_request(
                    self,
                    cw=cw,
                    interval_current=interval_current,
                    indicator_key=indicator_key,
                    indicator_label=indicator_label,
                    target_side=action_side_label,
                    desired_ps_opposite=desired_ps_short if action_side_label == "BUY" else desired_ps_long,
                    indicator_interval_tokens=indicator_interval_tokens,
                    qty_tol_indicator=qty_tol_indicator,
                    hedge_overlap_allowed=hedge_overlap_allowed,
                    now_indicator_ts=now_indicator_ts,
                )
                if fallback_request is not None:
                    indicator_order_requests.append(fallback_request)
    return indicator_order_requests, qty_tol_indicator


def bind_strategy_signal_order_collect_runtime(strategy_cls) -> None:
    strategy_cls._collect_indicator_order_requests = _collect_indicator_order_requests
