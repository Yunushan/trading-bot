from __future__ import annotations

import time

try:
    from ...integrations.exchanges.binance import normalize_margin_ratio
except ImportError:  # pragma: no cover - standalone execution fallback
    from binance_wrapper import normalize_margin_ratio

def _apply_cycle_risk_management(
    self,
    *,
    ctx,
    cw,
    df,
    account_type: str,
    allow_opposite_enabled: bool,
    dual_side: bool,
    desired_ps_long_guard: str | None,
    desired_ps_short_guard: str | None,
    key_long,
    key_short,
    long_open: bool,
    short_open: bool,
    stop_enabled: bool,
    apply_usdt_limit: bool,
    apply_percent_limit: bool,
    stop_usdt_limit: float,
    stop_percent_limit: float,
    scope: str,
    is_cumulative: bool,
    last_rsi,
):
    # Exit thresholds
    try:
        rsi_cfg = cw.get('indicators',{}).get('rsi',{})
        exit_up = float(rsi_cfg.get('sell_value', 70))
        exit_dn = float(rsi_cfg.get('buy_value', 30))
    except Exception:
        exit_up, exit_dn = 70.0, 30.0

    if account_type == "FUTURES" and last_rsi is not None and not allow_opposite_enabled:
        interval_current = cw.get('interval')
        try:
            if last_rsi >= exit_up and self._indicator_has_open(cw['symbol'], interval_current, 'rsi', 'BUY'):
                try:
                    closed_long, _ = self._close_indicator_positions(
                        cw,
                        interval_current,
                        'rsi',
                        'BUY',
                        desired_ps_long_guard,
                        ignore_hold=True,
                        strict_interval=True,
                        reason="rsi_exit",
                    )
                except Exception:
                    closed_long = 0
                if closed_long:
                    long_open = bool(self._leg_ledger.get(key_long, {}).get('qty', 0) > 0)
                    try:
                        plural = "entry" if closed_long == 1 else "entries"
                        self.log(
                            f"Closed {closed_long} RSI LONG {plural} for {cw['symbol']}@{cw.get('interval')} (RSI >= {exit_up})."
                        )
                    except Exception:
                        pass
            if last_rsi <= exit_dn and self._indicator_has_open(cw['symbol'], interval_current, 'rsi', 'SELL'):
                try:
                    closed_short, _ = self._close_indicator_positions(
                        cw,
                        interval_current,
                        'rsi',
                        'SELL',
                        desired_ps_short_guard,
                        ignore_hold=True,
                        strict_interval=True,
                        reason="rsi_exit",
                    )
                except Exception:
                    closed_short = 0
                if closed_short:
                    short_open = bool(self._leg_ledger.get(key_short, {}).get('qty', 0) > 0)
                    try:
                        plural = "entry" if closed_short == 1 else "entries"
                        self.log(
                            f"Closed {closed_short} RSI SHORT {plural} for {cw['symbol']}@{cw.get('interval')} (RSI <= {exit_dn})."
                        )
                    except Exception:
                        pass
        except Exception:
            pass

    last_price = None
    try:
        live_price = float(self.binance.get_last_price(cw['symbol']) or 0.0)
        if live_price > 0.0:
            last_price = live_price
    except Exception:
        last_price = None
    if last_price is None and not df.empty:
        try:
            last_price = float(df['close'].iloc[-1])
        except Exception:
            last_price = None
    positions_cache = None
    positions_cache_ok = False

    def _load_positions_cache():
        nonlocal positions_cache, positions_cache_ok
        if positions_cache is None:
            try:
                positions_cache = self.binance.list_open_futures_positions() or []
                positions_cache_ok = True
            except Exception:
                positions_cache = []
                positions_cache_ok = False
        return positions_cache or []

    if account_type == "FUTURES":
        try:
            _load_positions_cache()
            if positions_cache_ok:
                self._purge_flat_futures_legs(
                    cw["symbol"],
                    positions_cache,
                    dual_side=dual_side,
                )
        except Exception:
            pass

    if stop_enabled and last_price is not None and account_type == "FUTURES":
        def _ensure_entry_price(leg_key, expect_long: bool):
            leg = self._leg_ledger.get(leg_key, {}) or {}
            qty_val = float(leg.get("qty") or 0.0)
            entry_px = float(leg.get("entry_price") or 0.0)
            matched_pos = None
            cache = _load_positions_cache()
            for pos in cache:
                try:
                    if str(pos.get("symbol") or "").upper() != cw["symbol"]:
                        continue
                    amt = float(pos.get("positionAmt") or 0.0)
                    if dual_side:
                        pos_side = str(pos.get("positionSide") or "").upper()
                        if expect_long and pos_side != "LONG":
                            continue
                        if (not expect_long) and pos_side != "SHORT":
                            continue
                        qty_candidate = abs(amt)
                    else:
                        if expect_long and amt <= 0.0:
                            continue
                        if (not expect_long) and amt >= 0.0:
                            continue
                        qty_candidate = abs(amt)
                    if qty_candidate <= 0.0:
                        continue
                    matched_pos = pos
                    if entry_px <= 0.0:
                        try:
                            entry_px = float(pos.get("entryPrice") or entry_px)
                        except Exception:
                            pass
                    break
                except Exception:
                    continue
            if matched_pos and entry_px > 0.0:
                leg["entry_price"] = entry_px
                self._leg_ledger[leg_key] = leg
            return leg, qty_val, entry_px, matched_pos

        leg_long, qty_long, entry_price_long, pos_long = _ensure_entry_price(key_long, True)
        leg_short, qty_short, entry_price_short, pos_short = _ensure_entry_price(key_short, False)
        pos_long_qty_total = 0.0
        pos_short_qty_total = 0.0

        if qty_long <= 0.0 and pos_long:
            try:
                qty_long = max(0.0, float(pos_long.get("positionAmt") or 0.0))
            except Exception:
                qty_long = 0.0
            if qty_long > 0.0:
                self._sync_leg_entry_totals(key_long, qty_long)
        if pos_long:
            try:
                amt_val = float(pos_long.get("positionAmt") or 0.0)
                pos_long_qty_total = abs(amt_val)
            except Exception:
                pos_long_qty_total = 0.0
        if qty_short <= 0.0 and pos_short:
            try:
                qty_short = abs(float(pos_short.get("positionAmt") or 0.0))
            except Exception:
                qty_short = 0.0
            if qty_short > 0.0:
                self._sync_leg_entry_totals(key_short, qty_short)
        if pos_short:
            try:
                amt_val = float(pos_short.get("positionAmt") or 0.0)
                pos_short_qty_total = abs(amt_val)
            except Exception:
                pos_short_qty_total = 0.0

        entries_long = self._leg_entries(key_long)
        entries_short = self._leg_entries(key_short)

        if scope == "per_trade":
            if entries_long:
                self._evaluate_per_trade_stop(
                    cw,
                    key_long,
                    entries_long,
                    side_label="BUY",
                    last_price=last_price,
                    apply_usdt_limit=apply_usdt_limit,
                    apply_percent_limit=apply_percent_limit,
                    stop_usdt_limit=stop_usdt_limit,
                    stop_percent_limit=stop_percent_limit,
                    dual_side=dual_side,
                )
            if entries_short:
                self._evaluate_per_trade_stop(
                    cw,
                    key_short,
                    entries_short,
                    side_label="SELL",
                    last_price=last_price,
                    apply_usdt_limit=apply_usdt_limit,
                    apply_percent_limit=apply_percent_limit,
                    stop_usdt_limit=stop_usdt_limit,
                    stop_percent_limit=stop_percent_limit,
                    dual_side=dual_side,
                )
            leg_long = self._leg_ledger.get(key_long, {}) or {}
            leg_short = self._leg_ledger.get(key_short, {}) or {}
            qty_long = float(leg_long.get("qty") or 0.0)
            qty_short = float(leg_short.get("qty") or 0.0)
            entry_price_long = float(leg_long.get("entry_price") or 0.0)
            entry_price_short = float(leg_short.get("entry_price") or 0.0)
        elif is_cumulative:
            cache = _load_positions_cache()
            totals = {
                "LONG": {"qty": 0.0, "loss": 0.0, "margin": 0.0},
                "SHORT": {"qty": 0.0, "loss": 0.0, "margin": 0.0},
            }
            for pos in cache:
                try:
                    if str(pos.get("symbol") or "").upper() != cw["symbol"]:
                        continue
                    pos_side = str(pos.get("positionSide") or "").upper()
                    amt = float(pos.get("positionAmt") or 0.0)
                    entry_px = float(pos.get("entryPrice") or 0.0)
                    if entry_px <= 0.0:
                        continue
                    if dual_side:
                        if pos_side == "LONG":
                            qty_pos = max(0.0, float(pos.get("positionAmt") or 0.0))
                            side_key = "LONG"
                        elif pos_side == "SHORT":
                            qty_pos = max(0.0, abs(float(pos.get("positionAmt") or 0.0)))
                            side_key = "SHORT"
                        else:
                            continue
                    else:
                        if amt > 0.0:
                            qty_pos = amt
                            side_key = "LONG"
                        elif amt < 0.0:
                            qty_pos = abs(amt)
                            side_key = "SHORT"
                        else:
                            continue
                    if qty_pos <= 0.0:
                        continue
                    margin_val = float(pos.get("isolatedWallet") or 0.0)
                    if margin_val <= 0.0:
                        margin_val = float(pos.get("initialMargin") or 0.0)
                    if margin_val <= 0.0:
                        notional_val = abs(float(pos.get("notional") or 0.0))
                        lev = float(pos.get("leverage") or 1.0) or 1.0
                        if lev > 0.0:
                            margin_val = notional_val / lev
                    if side_key == "LONG":
                        loss_val = max(0.0, (entry_px - last_price) * qty_pos)
                    else:
                        loss_val = max(0.0, (last_price - entry_px) * qty_pos)
                    totals[side_key]["qty"] += qty_pos
                    totals[side_key]["loss"] += loss_val
                    totals[side_key]["margin"] += max(0.0, margin_val)
                except Exception:
                    continue
            cumulative_triggered = False
            for side_key in ("LONG", "SHORT"):
                data = totals[side_key]
                if data["qty"] <= 0.0:
                    continue
                triggered = False
                if apply_usdt_limit and data["loss"] >= stop_usdt_limit:
                    triggered = True
                if (
                    not triggered
                    and apply_percent_limit
                    and data["margin"] > 0.0
                    and (data["loss"] / data["margin"] * 100.0) >= stop_percent_limit
                ):
                    triggered = True
                if not triggered:
                    continue
                cumulative_triggered = True
                close_side = "SELL" if side_key == "LONG" else "BUY"
                position_side = side_key if dual_side else None
                start_ts = time.time()
                try:
                    res = self.binance.close_futures_leg_exact(
                        cw["symbol"], data["qty"], side=close_side, position_side=position_side
                    )
                except Exception as exc:
                    try:
                        self.log(f"Cumulative stop-loss close error for {cw['symbol']} ({side_key}): {exc}")
                    except Exception:
                        pass
                    continue
                if isinstance(res, dict) and res.get("ok"):
                    latency_s = max(0.0, time.time() - start_ts)
                    target_side_label = "BUY" if side_key == "LONG" else "SELL"
                    payload = self._build_close_event_payload(
                        cw["symbol"], cw.get("interval"), target_side_label, data["qty"], res
                    )
                    try:
                        payload["reason"] = "cumulative_stop_loss"
                    except Exception:
                        pass
                    for leg_key in list(self._leg_ledger.keys()):
                        if leg_key[0] == cw["symbol"] and leg_key[2] == target_side_label:
                            try:
                                for entry in self._leg_entries(leg_key):
                                    try:
                                        self._mark_indicator_reentry_signal_block(
                                            cw["symbol"],
                                            cw.get("interval"),
                                            entry,
                                            target_side_label,
                                        )
                                    except Exception:
                                        pass
                                    try:
                                        for indicator_key in self._extract_indicator_keys(entry):
                                            self._record_indicator_close(
                                                cw["symbol"],
                                                cw.get("interval"),
                                                indicator_key,
                                                target_side_label,
                                                entry.get("qty"),
                                            )
                                    except Exception:
                                        pass
                                    try:
                                        self._queue_flip_on_close(
                                            cw.get("interval"),
                                            target_side_label,
                                            entry,
                                            payload,
                                        )
                                    except Exception:
                                        pass
                            except Exception:
                                pass
                            self._remove_leg_entry(leg_key, None)
                    self._mark_guard_closed(cw["symbol"], cw.get("interval"), target_side_label)
                    self._notify_interval_closed(
                        cw["symbol"],
                        cw.get("interval"),
                        target_side_label,
                        **payload,
                        latency_seconds=latency_s,
                        latency_ms=latency_s * 1000.0,
                        reason="cumulative_stop_loss",
                    )
                    try:
                        margin_val = data["margin"] or 0.0
                        pct_loss = (data["loss"] / margin_val * 100.0) if margin_val > 0.0 else 0.0
                        self._log_latency_metric(
                            cw["symbol"],
                            cw.get("interval"),
                            f"cumulative stop-loss {target_side_label}",
                            latency_s,
                        )
                        self.log(
                            f"Cumulative stop-loss closed {target_side_label} for {cw['symbol']}@{cw.get('interval')} "
                            f"(loss {data['loss']:.4f} USDT / {pct_loss:.2f}%)."
                        )
                    except Exception:
                        pass
                else:
                    try:
                        self.log(
                            f"Cumulative stop-loss close failed for {cw['symbol']} ({side_key}): {res}"
                        )
                    except Exception:
                        pass
            if cumulative_triggered:
                position_open = False
                units = 0.0
                position_margin = 0.0
                direction = ""
                long_open = False
                short_open = False
        else:
            if qty_long > 0.0 and entry_price_long > 0.0:
                loss_usdt_long = max(0.0, (entry_price_long - last_price) * qty_long)
                denom_long = entry_price_long * qty_long
                loss_pct_long = (loss_usdt_long / denom_long * 100.0) if denom_long > 0 else 0.0
                margin_long, margin_balance_long, mm_long, unrealized_loss_long = self._compute_position_margin_fields(
                    pos_long,
                    qty_hint=qty_long,
                    entry_price_hint=entry_price_long,
                )
                ratio_long = normalize_margin_ratio((pos_long or {}).get("marginRatio"))
                if ratio_long <= 0.0 and mm_long > 0.0 and margin_balance_long > 0.0:
                    ratio_long = ((mm_long + unrealized_loss_long) / margin_balance_long) * 100.0
                if margin_long > 0.0:
                    try:
                        margin_share = margin_long
                        if pos_long_qty_total > 0.0 and qty_long > 0.0:
                            share = min(1.0, qty_long / pos_long_qty_total)
                            margin_share = max(margin_long * share, 1e-12)
                        margin_pct = (loss_usdt_long / margin_share) * 100.0
                        if margin_pct > loss_pct_long:
                            loss_pct_long = margin_pct
                    except Exception:
                        pass
                triggered_long = False
                if apply_usdt_limit and loss_usdt_long >= stop_usdt_limit:
                    triggered_long = True
                if not triggered_long and apply_percent_limit and loss_pct_long >= stop_percent_limit:
                    triggered_long = True
                if not triggered_long and apply_percent_limit and ratio_long >= stop_percent_limit:
                    triggered_long = True
                    if ratio_long > loss_pct_long:
                        loss_pct_long = ratio_long
                if triggered_long:
                    desired_ps = "LONG" if dual_side else None
                    try:
                        start_ts = time.time()
                        res = self.binance.close_futures_leg_exact(
                            cw["symbol"], qty_long, side="SELL", position_side=desired_ps
                        )
                        if isinstance(res, dict) and res.get("ok"):
                            latency_s = max(0.0, time.time() - start_ts)
                            payload = self._build_close_event_payload(
                                cw["symbol"], cw.get("interval"), "BUY", qty_long, res
                            )
                            try:
                                payload["reason"] = "stop_loss_long"
                            except Exception:
                                pass
                            try:
                                for entry in self._leg_entries(key_long):
                                    self._mark_indicator_reentry_signal_block(
                                        cw["symbol"],
                                        cw.get("interval"),
                                        entry,
                                        "BUY",
                                    )
                                    try:
                                        for indicator_key in self._extract_indicator_keys(entry):
                                            self._record_indicator_close(
                                                cw["symbol"],
                                                cw.get("interval"),
                                                indicator_key,
                                                "BUY",
                                                entry.get("qty"),
                                            )
                                    except Exception:
                                        pass
                                    self._queue_flip_on_close(
                                        cw.get("interval"),
                                        "BUY",
                                        entry,
                                        payload,
                                    )
                            except Exception:
                                pass
                            self._remove_leg_entry(key_long, None)
                            long_open = False
                            self._mark_guard_closed(cw["symbol"], cw.get("interval"), "BUY")
                            self._log_latency_metric(
                                cw["symbol"],
                                cw.get("interval"),
                                "stop-loss BUY leg",
                                latency_s,
                            )
                            self._notify_interval_closed(
                                cw["symbol"],
                                cw.get("interval"),
                                "BUY",
                                **payload,
                                latency_seconds=latency_s,
                                latency_ms=latency_s * 1000.0,
                                reason="stop_loss_long",
                            )
                            try:
                                self.log(
                                    f"Stop-loss closed BUY for {cw['symbol']}@{cw.get('interval')} "
                                    f"(loss {loss_usdt_long:.4f} USDT / {loss_pct_long:.2f}%)."
                                )
                            except Exception:
                                pass
                        else:
                            try:
                                self.log(
                                    f"Stop-loss close failed for {cw['symbol']}@{cw.get('interval')} (BUY): {res}"
                                )
                            except Exception:
                                pass
                    except Exception as exc:
                        try:
                            self.log(
                                f"Stop-loss close error for {cw['symbol']}@{cw.get('interval')} (BUY): {exc}"
                            )
                        except Exception:
                            pass
            if qty_short > 0.0 and entry_price_short > 0.0:
                loss_usdt_short = max(0.0, (last_price - entry_price_short) * qty_short)
                denom_short = entry_price_short * qty_short
                loss_pct_short = (loss_usdt_short / denom_short * 100.0) if denom_short > 0 else 0.0
                margin_short, margin_balance_short, mm_short, unrealized_loss_short_val = self._compute_position_margin_fields(
                    pos_short,
                    qty_hint=qty_short,
                    entry_price_hint=entry_price_short,
                )
                ratio_short = normalize_margin_ratio((pos_short or {}).get("marginRatio"))
                if ratio_short <= 0.0 and mm_short > 0.0 and margin_balance_short > 0.0:
                    ratio_short = ((mm_short + unrealized_loss_short_val) / margin_balance_short) * 100.0
                if margin_short > 0.0:
                    try:
                        margin_share = margin_short
                        if pos_short_qty_total > 0.0 and qty_short > 0.0:
                            share = min(1.0, qty_short / pos_short_qty_total)
                            margin_share = max(margin_short * share, 1e-12)
                        margin_pct = (loss_usdt_short / margin_share) * 100.0
                        if margin_pct > loss_pct_short:
                            loss_pct_short = margin_pct
                    except Exception:
                        pass
                triggered_short = False
                if apply_usdt_limit and loss_usdt_short >= stop_usdt_limit:
                    triggered_short = True
                if not triggered_short and apply_percent_limit and loss_pct_short >= stop_percent_limit:
                    triggered_short = True
                if not triggered_short and apply_percent_limit and ratio_short >= stop_percent_limit:
                    triggered_short = True
                    if ratio_short > loss_pct_short:
                        loss_pct_short = ratio_short
                if triggered_short:
                    desired_ps = "SHORT" if dual_side else None
                    try:
                        start_ts = time.time()
                        res = self.binance.close_futures_leg_exact(
                            cw["symbol"], qty_short, side="BUY", position_side=desired_ps
                        )
                        if isinstance(res, dict) and res.get("ok"):
                            latency_s = max(0.0, time.time() - start_ts)
                            payload = self._build_close_event_payload(
                                cw["symbol"], cw.get("interval"), "SELL", qty_short, res
                            )
                            try:
                                payload["reason"] = "stop_loss_short"
                            except Exception:
                                pass
                            try:
                                for entry in self._leg_entries(key_short):
                                    self._mark_indicator_reentry_signal_block(
                                        cw["symbol"],
                                        cw.get("interval"),
                                        entry,
                                        "SELL",
                                    )
                                    try:
                                        for indicator_key in self._extract_indicator_keys(entry):
                                            self._record_indicator_close(
                                                cw["symbol"],
                                                cw.get("interval"),
                                                indicator_key,
                                                "SELL",
                                                entry.get("qty"),
                                            )
                                    except Exception:
                                        pass
                                    self._queue_flip_on_close(
                                        cw.get("interval"),
                                        "SELL",
                                        entry,
                                        payload,
                                    )
                            except Exception:
                                pass
                            self._remove_leg_entry(key_short, None)
                            short_open = False
                            self._mark_guard_closed(cw["symbol"], cw.get("interval"), "SELL")
                            self._log_latency_metric(
                                cw["symbol"],
                                cw.get("interval"),
                                "stop-loss SELL leg",
                                latency_s,
                            )
                            self._notify_interval_closed(
                                cw["symbol"],
                                cw.get("interval"),
                                "SELL",
                                **payload,
                                latency_seconds=latency_s,
                                latency_ms=latency_s * 1000.0,
                                reason="stop_loss_short",
                            )
                            try:
                                self.log(
                                    f"Stop-loss closed SELL for {cw['symbol']}@{cw.get('interval')} "
                                    f"(loss {loss_usdt_short:.4f} USDT / {loss_pct_short:.2f}%)."
                                )
                            except Exception:
                                pass
                        else:
                            try:
                                self.log(
                                    f"Stop-loss close failed for {cw['symbol']}@{cw.get('interval')} (SELL): {res}"
                                )
                            except Exception:
                                pass
                    except Exception as exc:
                        try:
                                self.log(
                                    f"Stop-loss close error for {cw['symbol']}@{cw.get('interval')} (SELL): {exc}"
                                )
                        except Exception:
                            pass
        leg_long_state = self._leg_ledger.get(key_long, {}) or {}
        leg_short_state = self._leg_ledger.get(key_short, {}) or {}
        qty_long = float(leg_long_state.get("qty") or 0.0)
        qty_short = float(leg_short_state.get("qty") or 0.0)
        entry_price_long = float(leg_long_state.get("entry_price") or 0.0)
        entry_price_short = float(leg_short_state.get("entry_price") or 0.0)
        long_open = qty_long > 0.0
        short_open = qty_short > 0.0


    return {
        "last_price": last_price,
        "positions_cache": positions_cache,
        "load_positions_cache": _load_positions_cache,
        "long_open": long_open,
        "short_open": short_open,
    }

