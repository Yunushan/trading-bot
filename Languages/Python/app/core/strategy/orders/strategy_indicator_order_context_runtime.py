from __future__ import annotations

from . import strategy_indicator_order_build_runtime


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
                exch_qty = strategy_indicator_order_build_runtime._indicator_exchange_qty(
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
