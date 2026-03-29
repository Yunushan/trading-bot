from __future__ import annotations

import time


def _entry_margin_value(entry: dict | None, leverage_fallback: float | int = 1) -> float:
    if not isinstance(entry, dict):
        return 0.0
    try:
        margin_val = float(entry.get("margin_usdt") or 0.0)
    except Exception:
        margin_val = 0.0
    if margin_val > 0.0:
        return max(0.0, margin_val)
    try:
        qty = max(0.0, float(entry.get("qty") or 0.0))
    except Exception:
        qty = 0.0
    try:
        price = max(0.0, float(entry.get("entry_price") or 0.0))
    except Exception:
        price = 0.0
    try:
        lev_val = float(entry.get("leverage") or leverage_fallback or 1.0)
    except Exception:
        lev_val = float(leverage_fallback or 1.0)
    lev_val = max(1.0, lev_val)
    if qty > 0.0 and price > 0.0:
        try:
            return (price * qty) / lev_val
        except Exception:
            return 0.0
    return 0.0


def _current_futures_position_qty(
    self,
    symbol: str,
    side_label: str,
    position_side: str | None,
    positions: list[dict] | None = None,
) -> float | None:
    sym_norm = str(symbol or "").upper()
    rows: list[dict] | None
    if positions is None:
        try:
            rows = self.binance.list_open_futures_positions(max_age=0.0, force_refresh=True) or []
        except Exception:
            return None
        if not rows:
            try:
                rows = self.binance.client.futures_position_information(symbol=sym_norm) or []
            except Exception:
                rows = []
    else:
        rows = positions
    side_norm = "BUY" if str(side_label or "").upper() in {"BUY", "LONG"} else "SELL"
    desired_pos_side = str(position_side or "").upper() if position_side else None
    best_qty = 0.0
    qty_tol = 1e-6
    for pos in rows or []:
        try:
            if str(pos.get("symbol") or "").upper() != sym_norm:
                continue
            amt = float(pos.get("positionAmt") or 0.0)
            pos_side_val = str(pos.get("positionSide") or "").upper()
            if desired_pos_side:
                if pos_side_val and pos_side_val not in ("BOTH", desired_pos_side):
                    if not (
                        desired_pos_side == "LONG" and pos_side_val == "BOTH" and amt > 0.0
                    ) and not (
                        desired_pos_side == "SHORT" and pos_side_val == "BOTH" and amt < 0.0
                    ):
                        continue
            if desired_pos_side:
                qty_val = abs(amt)
            else:
                if pos_side_val == "LONG":
                    if side_norm != "BUY":
                        continue
                    qty_val = abs(amt)
                elif pos_side_val == "SHORT":
                    if side_norm != "SELL":
                        continue
                    qty_val = abs(amt)
                elif side_norm == "BUY":
                    if amt <= 0.0:
                        continue
                    qty_val = amt
                else:
                    if amt >= 0.0:
                        continue
                    qty_val = abs(amt)
            if qty_val > best_qty:
                best_qty = qty_val
        except Exception:
            continue
    return best_qty if best_qty > qty_tol else 0.0


def _purge_flat_futures_legs(
    self,
    symbol: str,
    positions: list[dict] | None,
    *,
    dual_side: bool,
) -> None:
    sym_norm = str(symbol or "").upper()
    if not sym_norm:
        return
    now_ts = time.time()
    try:
        mode_text = str(getattr(self.binance, "mode", "") or "").lower()
    except Exception:
        mode_text = ""
    try:
        purge_grace_seconds = max(0.0, float(getattr(self, "_flat_purge_grace_seconds", 12.0) or 0.0))
    except Exception:
        purge_grace_seconds = 12.0
    if any(tag in mode_text for tag in ("demo", "test", "paper")):
        purge_grace_seconds = max(purge_grace_seconds, 30.0)
    try:
        miss_threshold = max(1, int(getattr(self, "_flat_purge_miss_threshold", 2) or 1))
    except Exception:
        miss_threshold = 2
    for leg_key, leg in list(self._leg_ledger.items()):
        leg_sym, leg_interval, leg_side = leg_key
        if str(leg_sym or "").upper() != sym_norm:
            continue
        try:
            qty_recorded = max(0.0, float((leg or {}).get("qty") or 0.0))
        except Exception:
            qty_recorded = 0.0
        if qty_recorded <= 0.0:
            self._flat_purge_miss_counts.pop(leg_key, None)
            continue
        leg_side_norm = "BUY" if str(leg_side or "").upper() in {"BUY", "LONG"} else "SELL"
        desired_pos_side = None
        if dual_side:
            desired_pos_side = "LONG" if leg_side_norm == "BUY" else "SHORT"
        live_qty = self._current_futures_position_qty(
            sym_norm,
            leg_side_norm,
            desired_pos_side,
            positions,
        )
        if live_qty is None:
            continue
        eps = max(1e-8, abs(live_qty) * 1e-6)
        if live_qty > eps:
            self._flat_purge_miss_counts.pop(leg_key, None)
            continue
        try:
            entries = self._leg_entries(leg_key)
        except Exception:
            entries = []
        if purge_grace_seconds > 0.0:
            newest_ts = 0.0
            for entry in entries or []:
                try:
                    ts_val = float(entry.get("timestamp") or 0.0)
                except Exception:
                    ts_val = 0.0
                if ts_val > newest_ts:
                    newest_ts = ts_val
            if newest_ts <= 0.0:
                try:
                    newest_ts = float((leg or {}).get("timestamp") or 0.0)
                except Exception:
                    newest_ts = 0.0
            if newest_ts > 0.0 and (now_ts - newest_ts) < purge_grace_seconds:
                continue
        miss_count = int(self._flat_purge_miss_counts.get(leg_key, 0) or 0) + 1
        self._flat_purge_miss_counts[leg_key] = miss_count
        if miss_count < miss_threshold:
            continue
        self._flat_purge_miss_counts.pop(leg_key, None)
        for entry in entries or []:
            try:
                self._mark_indicator_reentry_signal_block(sym_norm, leg_interval, entry, leg_side_norm)
            except Exception:
                pass
            try:
                for indicator_key in self._extract_indicator_keys(entry):
                    self._record_indicator_close(sym_norm, leg_interval, indicator_key, leg_side_norm, entry.get("qty"))
            except Exception:
                pass
            try:
                self._queue_flip_on_close(leg_interval, leg_side_norm, entry, None)
            except Exception:
                pass
        self._remove_leg_entry(leg_key, None)
        self._guard_mark_leg_closed(leg_key)
        try:
            self.log(
                f"Purged stale {leg_side_norm} leg for {sym_norm}@{leg_interval} after liquidation/manual close."
            )
        except Exception:
            pass


def _compute_position_margin_fields(
    position: dict | None,
    *,
    qty_hint: float = 0.0,
    entry_price_hint: float = 0.0,
) -> tuple[float, float, float, float]:
    """Derive margin, balance, maintenance margin, and unrealized loss for a futures leg."""
    if not isinstance(position, dict):
        return 0.0, 0.0, 0.0, 0.0
    try:
        margin = float(
            position.get("isolatedMargin")
            or position.get("isolatedWallet")
            or position.get("initialMargin")
            or 0.0
        )
    except Exception:
        margin = 0.0
    try:
        leverage = float(position.get("leverage") or 0.0)
    except Exception:
        leverage = 0.0
    try:
        entry_price = float(position.get("entryPrice") or 0.0)
    except Exception:
        entry_price = 0.0
    if entry_price <= 0.0:
        entry_price = max(0.0, float(entry_price_hint or 0.0))
    try:
        notional_val = abs(float(position.get("notional") or 0.0))
    except Exception:
        notional_val = 0.0
    if notional_val <= 0.0 and entry_price > 0.0 and qty_hint > 0.0:
        notional_val = entry_price * qty_hint
    if margin <= 0.0:
        if leverage > 0.0 and notional_val > 0.0:
            margin = notional_val / leverage
        elif notional_val > 0.0:
            margin = notional_val
    if margin <= 0.0 and entry_price > 0.0 and qty_hint > 0.0:
        if leverage > 0.0:
            margin = (entry_price * qty_hint) / leverage
        else:
            margin = entry_price * qty_hint
    margin = max(margin, 0.0)
    try:
        margin_balance = float(position.get("marginBalance") or 0.0)
    except Exception:
        margin_balance = 0.0
    try:
        iso_wallet = float(position.get("isolatedWallet") or 0.0)
    except Exception:
        iso_wallet = 0.0
    if margin_balance <= 0.0 and iso_wallet > 0.0:
        margin_balance = iso_wallet
    try:
        unrealized_profit = float(position.get("unRealizedProfit") or 0.0)
    except Exception:
        unrealized_profit = 0.0
    if margin_balance <= 0.0 and margin > 0.0:
        margin_balance = margin + unrealized_profit
    if margin_balance <= 0.0 and margin > 0.0:
        margin_balance = margin
    margin_balance = max(margin_balance, 0.0)
    try:
        maint_margin = float(position.get("maintMargin") or position.get("maintenanceMargin") or 0.0)
    except Exception:
        maint_margin = 0.0
    try:
        maint_margin_rate = float(
            position.get("maintMarginRate")
            or position.get("maintenanceMarginRate")
            or position.get("maintMarginRatio")
            or position.get("maintenanceMarginRatio")
            or 0.0
        )
    except Exception:
        maint_margin_rate = 0.0
    if maint_margin <= 0.0 and maint_margin_rate > 0.0 and notional_val > 0.0:
        maint_margin = notional_val * maint_margin_rate
    if margin_balance > 0.0 and maint_margin > margin_balance:
        maint_margin = margin_balance
    unrealized_loss = max(0.0, -unrealized_profit)
    return margin, margin_balance, maint_margin, unrealized_loss
