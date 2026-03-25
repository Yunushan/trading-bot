from __future__ import annotations

import time


def _update_leg_snapshot(self, leg_key, leg: dict | None) -> None:
    if not isinstance(leg, dict):
        self._leg_ledger.pop(leg_key, None)
        return
    entries_param = leg.get("entries") if isinstance(leg, dict) else None
    if isinstance(entries_param, list):
        provided_entries = [entry for entry in entries_param if isinstance(entry, dict)]
        entries = provided_entries if provided_entries else self._leg_entries(leg_key)
    else:
        entries = self._leg_entries(leg_key)
    total_qty = 0.0
    weighted_notional = 0.0
    total_margin = 0.0
    last_entry: dict | None = None
    for entry in entries:
        qty = max(0.0, float(entry.get("qty") or 0.0))
        price = max(0.0, float(entry.get("entry_price") or 0.0))
        margin = max(0.0, float(entry.get("margin_usdt") or 0.0))
        total_qty += qty
        weighted_notional += qty * price
        total_margin += margin
        last_entry = entry
    if total_qty > 0.0:
        leg["qty"] = total_qty
        leg["entry_price"] = weighted_notional / total_qty if weighted_notional > 0.0 else leg.get("entry_price", 0.0)
    else:
        leg["qty"] = 0.0
        leg["entry_price"] = 0.0
    leg["margin_usdt"] = total_margin
    if last_entry:
        if "ledger_id" in last_entry:
            leg["ledger_id"] = last_entry.get("ledger_id")
        if last_entry.get("leverage") is not None:
            leg["leverage"] = last_entry.get("leverage")
    leg["entries"] = entries
    leg["timestamp"] = time.time()
    self._leg_ledger[leg_key] = leg

def _append_leg_entry(self, leg_key, entry: dict) -> None:
    leg = self._leg_ledger.get(leg_key, {})
    entries = self._leg_entries(leg_key)
    entries.append(entry)
    leg["entries"] = entries
    self._update_leg_snapshot(leg_key, leg)
    self._last_order_time[leg_key] = time.time()
    try:
        signature_labels = entry.get("trigger_signature") or entry.get("trigger_indicators")
        self._bump_symbol_signature_open(leg_key[0], leg_key[1], leg_key[2], signature_labels, +1)
    except Exception:
        pass
    indicator_keys: list[str] | None = None
    try:
        ledger_id = entry.get("ledger_id")
        if ledger_id:
            self._ledger_index[ledger_id] = leg_key
        indicator_keys = self._extract_indicator_keys(entry)
        if ledger_id and indicator_keys:
            for indicator_key in indicator_keys:
                self._indicator_register_entry(leg_key[0], leg_key[1], indicator_key, leg_key[2], ledger_id)
                self._trade_book_add_entry(
                    leg_key[0],
                    leg_key[1],
                    indicator_key,
                    leg_key[2],
                    ledger_id,
                    entry.get("qty"),
                    entry,
                )
    except Exception:
        indicator_keys = None
    try:
        if indicator_keys:
            interval_norm = str(leg_key[1] or "").strip().lower() or "default"
            sym_norm = str(leg_key[0] or "").upper()
            side_norm = "BUY" if str(leg_key[2] or "").upper() in {"BUY", "LONG"} else "SELL"
            now_ts = time.time()
            for indicator_key in indicator_keys:
                ind_norm = self._canonical_indicator_token(indicator_key) or ""
                if not ind_norm:
                    continue
                self._indicator_last_action[(sym_norm, interval_norm, ind_norm)] = {
                    "side": side_norm,
                    "ts": now_ts,
                }
    except Exception:
        pass
    try:
        if indicator_keys:
            self._resolve_indicator_conflicts(leg_key, indicator_keys, entry)
    except Exception:
        pass

def _resolve_indicator_conflicts(
    self,
    leg_key: tuple[str, str, str],
    indicator_keys: list[str],
    current_entry: dict,
) -> None:
    if not indicator_keys:
        return
    if not self._strategy_coerce_bool(self.config.get("allow_indicator_close_without_signal"), False):
        # Respect strict flip enforcement: do not auto-close opposite legs unless an explicit flip signal exists.
        return
    symbol, interval, side_raw = leg_key
    side_norm = "BUY" if str(side_raw or "").upper() in {"BUY", "LONG"} else "SELL"
    opposite_side = "SELL" if side_norm == "BUY" else "BUY"
    cw_stub = {"symbol": symbol, "interval": interval}
    account_type = str(self.config.get("account_type") or getattr(self.binance, "account_type", "") or "").upper()
    dual_side = False
    if account_type == "FUTURES":
        try:
            dual_side = bool(self.binance.get_futures_dual_side())
        except Exception:
            dual_side = False
    desired_ps_opposite = None
    desired_ps_current = None
    if dual_side:
        desired_ps_opposite = "LONG" if opposite_side == "BUY" else "SHORT"
        desired_ps_current = "LONG" if side_norm == "BUY" else "SHORT"
    conflict_found = False
    for indicator_key in indicator_keys:
        conflicts = self._iter_indicator_entries(symbol, interval, indicator_key, opposite_side)
        if not conflicts:
            continue
        conflict_found = True
        try:
            self.log(
                f"{symbol}@{interval or 'default'} conflict: {indicator_key} has active {opposite_side} leg while opening {side_norm}. "
                "Forcing additional close."
            )
        except Exception:
            pass
        for conflict_leg_key, conflict_entry in conflicts:
            try:
                self._close_leg_entry(
                    cw_stub,
                    conflict_leg_key,
                    conflict_entry,
                    opposite_side,
                    "SELL" if opposite_side == "BUY" else "BUY",
                    desired_ps_opposite,
                    loss_usdt=0.0,
                    price_pct=0.0,
                    margin_pct=0.0,
                    queue_flip=False,
                )
            except Exception:
                continue
    if conflict_found:
        # After forcing opposite closes, re-check. If still conflicting, drop the newly opened leg.
        for indicator_key in indicator_keys:
            residual = self._iter_indicator_entries(symbol, interval, indicator_key, opposite_side)
            if residual:
                try:
                    self.log(
                        f"{symbol}@{interval or 'default'} conflict persists for {indicator_key}; "
                        f"closing newly opened {side_norm} leg to avoid overlap."
                    )
                except Exception:
                    pass
                self._close_leg_entry(
                    cw_stub,
                    leg_key,
                    current_entry,
                    side_norm,
                    "SELL" if side_norm == "BUY" else "BUY",
                    desired_ps_current,
                    loss_usdt=0.0,
                    price_pct=0.0,
                    margin_pct=0.0,
                    queue_flip=False,
                )
                break

def _remove_leg_entry(self, leg_key, ledger_id: str | None = None) -> None:
    current_entries = self._leg_entries(leg_key)
    if ledger_id is None:
        for entry in current_entries:
            try:
                signature_labels = entry.get("trigger_signature") or entry.get("trigger_indicators")
                self._bump_symbol_signature_open(leg_key[0], leg_key[1], leg_key[2], signature_labels, -1)
            except Exception:
                pass
            try:
                ledger = entry.get("ledger_id")
                indicator_keys = self._extract_indicator_keys(entry)
                if ledger and indicator_keys:
                    for indicator_key in indicator_keys:
                        self._indicator_unregister_entry(leg_key[0], leg_key[1], indicator_key, leg_key[2], ledger)
                        self._trade_book_remove_entry(leg_key[0], leg_key[1], indicator_key, leg_key[2], ledger)
                    self._ledger_index.pop(ledger, None)
            except Exception:
                pass
        self._leg_ledger.pop(leg_key, None)
        self._last_order_time.pop(leg_key, None)
        return
    leg = self._leg_ledger.get(leg_key)
    if not isinstance(leg, dict):
        return
    removed_entries = [entry for entry in current_entries if entry.get("ledger_id") == ledger_id]
    entries = [entry for entry in current_entries if entry.get("ledger_id") != ledger_id]
    if not entries:
        for entry in removed_entries:
            try:
                signature_labels = entry.get("trigger_signature") or entry.get("trigger_indicators")
                self._bump_symbol_signature_open(leg_key[0], leg_key[1], leg_key[2], signature_labels, -1)
            except Exception:
                pass
            try:
                indicator_keys = self._extract_indicator_keys(entry)
                ledger_token = entry.get("ledger_id")
                if ledger_token and indicator_keys:
                    for indicator_key in indicator_keys:
                        self._indicator_unregister_entry(
                            leg_key[0], leg_key[1], indicator_key, leg_key[2], ledger_token
                        )
                        self._trade_book_remove_entry(
                            leg_key[0], leg_key[1], indicator_key, leg_key[2], ledger_token
                        )
            except Exception:
                pass
        try:
            for entry in removed_entries:
                ledger = entry.get("ledger_id")
                if ledger:
                    self._ledger_index.pop(ledger, None)
        except Exception:
            pass
        self._leg_ledger.pop(leg_key, None)
        self._last_order_time.pop(leg_key, None)
        return
    leg["entries"] = entries
    self._update_leg_snapshot(leg_key, leg)
    for entry in removed_entries:
        try:
            signature_labels = entry.get("trigger_signature") or entry.get("trigger_indicators")
            self._bump_symbol_signature_open(leg_key[0], leg_key[1], leg_key[2], signature_labels, -1)
        except Exception:
            pass
        try:
            indicator_keys = self._extract_indicator_keys(entry)
            ledger_token = entry.get("ledger_id")
            if ledger_token and indicator_keys:
                for indicator_key in indicator_keys:
                    self._indicator_unregister_entry(
                        leg_key[0], leg_key[1], indicator_key, leg_key[2], ledger_token
                    )
                    self._trade_book_remove_entry(
                        leg_key[0], leg_key[1], indicator_key, leg_key[2], ledger_token
                    )
        except Exception:
            pass
        try:
            ledger = entry.get("ledger_id")
            if ledger:
                self._ledger_index.pop(ledger, None)
        except Exception:
            pass

def _decrement_leg_entry_qty(
    self,
    leg_key: tuple[str, str, str],
    ledger_id: str,
    previous_qty: float,
    remaining_qty: float,
) -> None:
    leg = self._leg_ledger.get(leg_key)
    if not isinstance(leg, dict):
        return
    entries = leg.get("entries")
    if not isinstance(entries, list):
        return
    ratio = 0.0
    try:
        if previous_qty > 0.0:
            ratio = max(0.0, remaining_qty / previous_qty)
    except Exception:
        ratio = 0.0
    updated = False
    for idx, entry in enumerate(entries):
        if entry.get("ledger_id") != ledger_id:
            continue
        new_entry = dict(entry)
        new_entry["qty"] = remaining_qty
        for field in (
            "margin_usdt",
            "margin",
            "size_usdt",
            "notional",
            "margin_balance",
            "maint_margin",
            "position_size",
        ):
            value = new_entry.get(field)
            if isinstance(value, (int, float)):
                new_entry[field] = max(0.0, float(value) * ratio)
        entries[idx] = new_entry
        leg["entries"] = entries
        indicator_keys = self._extract_indicator_keys(new_entry)
        if ledger_id and indicator_keys:
            for indicator_key in indicator_keys:
                self._trade_book_update_qty(
                    leg_key[0],
                    leg_key[1],
                    indicator_key,
                    leg_key[2],
                    ledger_id,
                    remaining_qty,
                )
        updated = True
        break
    if updated:
        self._update_leg_snapshot(leg_key, leg)

def _sync_leg_entry_totals(self, leg_key, actual_qty: float) -> None:
    leg = self._leg_ledger.get(leg_key)
    if not isinstance(leg, dict):
        return
    entries = self._leg_entries(leg_key)
    if not entries:
        leg["qty"] = max(0.0, float(actual_qty))
        self._update_leg_snapshot(leg_key, leg)
        return
    recorded_qty = sum(max(0.0, float(entry.get("qty") or 0.0)) for entry in entries)
    if recorded_qty <= 0.0:
        per_entry_qty = max(0.0, float(actual_qty)) / len(entries) if entries else 0.0
        for entry in entries:
            entry["qty"] = per_entry_qty
    else:
        scale = max(0.0, float(actual_qty)) / recorded_qty if recorded_qty > 0.0 else 0.0
        for entry in entries:
            qty = max(0.0, float(entry.get("qty") or 0.0)) * scale
            entry["qty"] = qty
            margin = max(0.0, float(entry.get("margin_usdt") or 0.0))
            entry["margin_usdt"] = margin * scale if margin > 0.0 else margin
    leg["entries"] = entries
    self._update_leg_snapshot(leg_key, leg)

@staticmethod
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
                # Prefer explicit positionSide labels when available because some connectors
                # report SHORT amounts as positive values in hedge mode.
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
    # Demo/testnet position snapshots can lag right after opening.
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


@staticmethod
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



def bind_strategy_position_state(strategy_cls) -> None:
    strategy_cls._update_leg_snapshot = _update_leg_snapshot
    strategy_cls._append_leg_entry = _append_leg_entry
    strategy_cls._resolve_indicator_conflicts = _resolve_indicator_conflicts
    strategy_cls._remove_leg_entry = _remove_leg_entry
    strategy_cls._decrement_leg_entry_qty = _decrement_leg_entry_qty
    strategy_cls._sync_leg_entry_totals = _sync_leg_entry_totals
    strategy_cls._entry_margin_value = staticmethod(_entry_margin_value)
    strategy_cls._current_futures_position_qty = _current_futures_position_qty
    strategy_cls._purge_flat_futures_legs = _purge_flat_futures_legs
    strategy_cls._compute_position_margin_fields = staticmethod(_compute_position_margin_fields)
