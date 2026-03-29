from __future__ import annotations

import time

try:
    from ....integrations.exchanges.binance import normalize_margin_ratio
except ImportError:  # pragma: no cover - standalone execution fallback
    from binance_wrapper import normalize_margin_ratio


def _apply_long_futures_stop(
    self,
    *,
    cw,
    dual_side: bool,
    key_long,
    qty_long: float,
    entry_price_long: float,
    pos_long,
    pos_long_qty_total: float,
    apply_usdt_limit: bool,
    apply_percent_limit: bool,
    stop_usdt_limit: float,
    stop_percent_limit: float,
    last_price: float,
) -> None:
    if qty_long <= 0.0 or entry_price_long <= 0.0:
        return
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
    if not triggered_long:
        return
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


def _apply_short_futures_stop(
    self,
    *,
    cw,
    dual_side: bool,
    key_short,
    qty_short: float,
    entry_price_short: float,
    pos_short,
    pos_short_qty_total: float,
    apply_usdt_limit: bool,
    apply_percent_limit: bool,
    stop_usdt_limit: float,
    stop_percent_limit: float,
    last_price: float,
) -> None:
    if qty_short <= 0.0 or entry_price_short <= 0.0:
        return
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
    if not triggered_short:
        return
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


def apply_directional_futures_stop_management(
    self,
    *,
    cw,
    dual_side: bool,
    key_long,
    key_short,
    qty_long: float,
    qty_short: float,
    entry_price_long: float,
    entry_price_short: float,
    pos_long,
    pos_short,
    pos_long_qty_total: float,
    pos_short_qty_total: float,
    apply_usdt_limit: bool,
    apply_percent_limit: bool,
    stop_usdt_limit: float,
    stop_percent_limit: float,
    last_price: float,
) -> None:
    _apply_long_futures_stop(
        self,
        cw=cw,
        dual_side=dual_side,
        key_long=key_long,
        qty_long=qty_long,
        entry_price_long=entry_price_long,
        pos_long=pos_long,
        pos_long_qty_total=pos_long_qty_total,
        apply_usdt_limit=apply_usdt_limit,
        apply_percent_limit=apply_percent_limit,
        stop_usdt_limit=stop_usdt_limit,
        stop_percent_limit=stop_percent_limit,
        last_price=last_price,
    )
    _apply_short_futures_stop(
        self,
        cw=cw,
        dual_side=dual_side,
        key_short=key_short,
        qty_short=qty_short,
        entry_price_short=entry_price_short,
        pos_short=pos_short,
        pos_short_qty_total=pos_short_qty_total,
        apply_usdt_limit=apply_usdt_limit,
        apply_percent_limit=apply_percent_limit,
        stop_usdt_limit=stop_usdt_limit,
        stop_percent_limit=stop_percent_limit,
        last_price=last_price,
    )


__all__ = ["apply_directional_futures_stop_management"]
