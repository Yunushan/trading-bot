from __future__ import annotations

import time


def apply_cumulative_futures_stop_management(
    self,
    *,
    cw,
    last_price: float,
    dual_side: bool,
    apply_usdt_limit: bool,
    apply_percent_limit: bool,
    stop_usdt_limit: float,
    stop_percent_limit: float,
    state,
) -> bool:
    load_positions_cache = state.get("load_positions_cache")
    cache = load_positions_cache() if callable(load_positions_cache) else []
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
    return cumulative_triggered


__all__ = ["apply_cumulative_futures_stop_management"]
