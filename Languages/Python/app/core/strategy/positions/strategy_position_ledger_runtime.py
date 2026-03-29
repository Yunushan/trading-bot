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
