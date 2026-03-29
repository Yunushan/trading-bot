from __future__ import annotations


def _close_interval_side_entries(
    self,
    *,
    symbol: str,
    interval_norm: str,
    interval_tokens: set[str],
    interval_has_filter: bool,
    interval_norm_guard: tuple[str, ...] | None,
    opp: str,
    dual: bool,
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

    for leg_key in list(self._leg_ledger.keys()):
        if limit_remaining is not None and limit_remaining <= limit_tol:
            break
        leg_sym, leg_interval, leg_side = leg_key
        if str(leg_sym or "").upper() != symbol:
            continue
        leg_interval_norm = str(leg_interval or "").strip()
        if indicator_filter_norm and interval_norm and leg_interval_norm != interval_norm:
            continue
        leg_tokens = self._tokenize_interval_label(leg_interval_norm)
        if interval_has_filter and leg_tokens.isdisjoint(interval_tokens):
            continue
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
                entry_sig_tokens = self._normalize_signature_tokens_no_slots(
                    entry.get("trigger_signature") or entry.get("trigger_indicators")
                )
                if indicator_filter_norm not in (entry_sig_tokens or ()):
                    continue
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
            close_side = "SELL" if leg_side_norm == "BUY" else "BUY"
            position_side = None
            if dual:
                position_side = "LONG" if leg_side_norm == "BUY" else "SHORT"
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
