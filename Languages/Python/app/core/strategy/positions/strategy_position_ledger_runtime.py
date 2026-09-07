from __future__ import annotations

import logging
import math
import time


_LOGGER = logging.getLogger(__name__)


def _mark_ledger_reconciliation_required(self, operation: str, exc: Exception) -> None:
    self._ledger_reconciliation_required = True
    _LOGGER.error(
        "Position ledger auxiliary synchronization failed during %s: %s",
        operation,
        exc,
        exc_info=(type(exc), exc, exc.__traceback__),
    )
    cls = type(self)
    pause_event = getattr(cls, "_GLOBAL_PAUSE", None)
    if pause_event is None:
        cls._GLOBAL_PAUSE_FALLBACK = True
        return
    try:
        pause_event.set()
    except Exception:
        cls._GLOBAL_PAUSE_FALLBACK = True
        _LOGGER.exception("Global pause event failed after position ledger synchronization error")


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
    except Exception as exc:
        _mark_ledger_reconciliation_required(self, "append signature count", exc)
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
    except Exception as exc:
        indicator_keys = None
        _mark_ledger_reconciliation_required(self, "append indicator/trade-book index", exc)
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
    except Exception as exc:
        _mark_ledger_reconciliation_required(self, "append indicator last-action state", exc)
    try:
        if indicator_keys:
            self._resolve_indicator_conflicts(leg_key, indicator_keys, entry)
    except Exception as exc:
        _mark_ledger_reconciliation_required(self, "append indicator conflict resolution", exc)


def _remove_leg_entry(
    self,
    leg_key,
    ledger_id: str | None = None,
    *,
    indicator_key: str | None = None,
) -> None:
    current_entries = self._leg_entries(leg_key)
    leg = self._leg_ledger.get(leg_key)
    if not isinstance(leg, dict):
        if ledger_id is None and indicator_key is None:
            self._leg_ledger.pop(leg_key, None)
            self._last_order_time.pop(leg_key, None)
        return

    # Select before mutating any index; entries without IDs still have ownership.
    removed_entries = []
    entries = []
    try:
        indicator_norm = None
        if indicator_key is not None:
            indicator_norm = self._canonical_indicator_token(indicator_key) or str(indicator_key).strip().lower()
        for entry in current_entries:
            matches = ledger_id is None or entry.get("ledger_id") == ledger_id
            if matches and indicator_norm is not None:
                matches = indicator_norm in self._extract_indicator_keys(entry)
            (removed_entries if matches else entries).append(entry)
    except Exception as exc:
        _mark_ledger_reconciliation_required(self, "select removal ownership", exc)
        raise
    if not removed_entries and current_entries:
        return

    if entries:
        leg["entries"] = entries
        try:
            self._update_leg_snapshot(leg_key, leg)
        except Exception as exc:
            _mark_ledger_reconciliation_required(self, "remove-entry leg snapshot", exc)
            raise
    else:
        self._leg_ledger.pop(leg_key, None)
        self._last_order_time.pop(leg_key, None)

    for entry in removed_entries:
        try:
            signature_labels = entry.get("trigger_signature") or entry.get("trigger_indicators")
            self._bump_symbol_signature_open(leg_key[0], leg_key[1], leg_key[2], signature_labels, -1)
        except Exception as exc:
            _mark_ledger_reconciliation_required(self, "remove-entry signature count", exc)
        try:
            indicator_keys = self._extract_indicator_keys(entry)
        except Exception as exc:
            indicator_keys = []
            _mark_ledger_reconciliation_required(self, "remove-entry indicator ownership", exc)
        ledger_token = entry.get("ledger_id")
        if ledger_token:
            for owned_indicator in indicator_keys:
                try:
                    self._indicator_unregister_entry(leg_key[0], leg_key[1], owned_indicator, leg_key[2], ledger_token)
                except Exception as exc:
                    _mark_ledger_reconciliation_required(self, "remove-entry indicator index", exc)
                try:
                    self._trade_book_remove_entry(leg_key[0], leg_key[1], owned_indicator, leg_key[2], ledger_token)
                except Exception as exc:
                    _mark_ledger_reconciliation_required(self, "remove-entry trade-book index", exc)
        try:
            ledger = entry.get("ledger_id")
            if ledger:
                self._ledger_index.pop(ledger, None)
        except Exception as exc:
            _mark_ledger_reconciliation_required(self, "remove-entry ledger index", exc)


def _decrement_leg_entry_qty(
    self,
    leg_key: tuple[str, str, str],
    ledger_id: str,
    previous_qty: float,
    remaining_qty: float,
) -> None:
    try:
        if not isinstance(ledger_id, str) or not ledger_id.strip():
            raise ValueError("Partial close requires an explicit ledger ID")
        for value in (previous_qty, remaining_qty):
            if value is None or isinstance(value, bool) or value == "":
                raise ValueError("Partial close quantities must be explicit numbers")
        previous_qty = _ledger_nonnegative_number(previous_qty, "previous quantity")
        remaining_qty = _ledger_nonnegative_number(remaining_qty, "remaining quantity")
        if previous_qty <= 0.0 or remaining_qty > previous_qty:
            raise ValueError("Partial close quantity bounds are invalid")
        leg = self._leg_ledger.get(leg_key)
        if not isinstance(leg, dict) or not isinstance(leg.get("entries"), list):
            raise ValueError("Partial close ledger is missing")
        entries = leg["entries"]
        matches = [(idx, entry) for idx, entry in enumerate(entries) if entry.get("ledger_id") == ledger_id]
        if len(matches) != 1:
            raise ValueError("Partial close ledger identity is missing or duplicated")
        idx, entry = matches[0]
        if _ledger_nonnegative_number(entry.get("qty"), "recorded quantity") != previous_qty:
            raise ValueError("Partial close was based on a stale ledger quantity")
        ratio = remaining_qty / previous_qty
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
            if field in new_entry:
                new_entry[field] = _ledger_nonnegative_number(new_entry[field], field) * ratio
        _ledger_nonnegative_number(new_entry.get("entry_price"), "entry price")
        _ledger_nonnegative_number(new_entry.get("timestamp"), "timestamp")
        indicator_keys = self._extract_indicator_keys(new_entry)
    except Exception as exc:
        _mark_ledger_reconciliation_required(self, "validate partial close", exc)
        raise

    # Keep the confirmed primary quantity even if an auxiliary index fails.
    replacement = list(entries)
    replacement[idx] = new_entry
    leg["entries"] = replacement
    errors = []
    try:
        self._update_leg_snapshot(leg_key, leg)
    except Exception as exc:
        errors.append(exc)
        _mark_ledger_reconciliation_required(self, "partial-close snapshot", exc)
    for indicator_key in indicator_keys:
        try:
            if remaining_qty > 0.0:
                self._trade_book_add_entry(
                    leg_key[0], leg_key[1], indicator_key, leg_key[2], ledger_id, remaining_qty, new_entry,
                )
            else:
                self._trade_book_remove_entry(leg_key[0], leg_key[1], indicator_key, leg_key[2], ledger_id)
        except Exception as exc:
            errors.append(exc)
            _mark_ledger_reconciliation_required(self, "partial-close owner record", exc)
    if errors:
        raise RuntimeError("Partial close requires ledger reconciliation") from errors[0]


def _ledger_nonnegative_number(value: object, field: str) -> float:
    number = float(value or 0.0)
    if not math.isfinite(number) or number < 0.0:
        raise ValueError(f"{field} must be finite and nonnegative")
    return number


def _sync_leg_entry_totals(self, leg_key, actual_qty: float) -> None:
    leg = self._leg_ledger.get(leg_key)
    if not isinstance(leg, dict):
        return
    try:
        if actual_qty is None or isinstance(actual_qty, bool) or actual_qty == "":
            raise ValueError("Exchange position quantity must be an explicit number")
        actual_qty = _ledger_nonnegative_number(actual_qty, "exchange position quantity")
        entries = self._leg_entries(leg_key)
        if not entries:
            raise ValueError("Cannot attribute exchange position quantity without tracked entries")
        quantities = [_ledger_nonnegative_number(entry.get("qty"), "recorded quantity") for entry in entries]
        recorded_qty = math.fsum(quantities)
        staged = []
        for entry, quantity in zip(entries, quantities):
            updated = dict(entry)
            updated["qty"] = actual_qty * (quantity / recorded_qty) if recorded_qty > 0.0 else actual_qty / len(entries)
            margin = _ledger_nonnegative_number(entry.get("margin_usdt"), "recorded margin")
            if recorded_qty > 0.0 and margin > 0.0:
                margin *= actual_qty / recorded_qty
            updated["margin_usdt"] = _ledger_nonnegative_number(margin, "reconciled margin")
            updated["entry_price"] = _ledger_nonnegative_number(entry.get("entry_price"), "entry price")
            _ledger_nonnegative_number(entry.get("timestamp"), "entry timestamp")
            staged.append((updated, self._extract_indicator_keys(updated)))
        # Validate the complete replacement before publishing any of its quantities.
        _ledger_nonnegative_number(math.fsum(entry["qty"] for entry, _ in staged), "total quantity")
        _ledger_nonnegative_number(
            math.fsum(entry["qty"] * entry["entry_price"] for entry, _ in staged), "total notional"
        )
        _ledger_nonnegative_number(math.fsum(entry["margin_usdt"] for entry, _ in staged), "total margin")
        leg["entries"] = [entry for entry, _ in staged]
        self._update_leg_snapshot(leg_key, leg)
        for entry, indicator_keys in staged:
            for indicator_key in indicator_keys:
                if entry["qty"] > 0.0:
                    self._trade_book_add_entry(
                        leg_key[0],
                        leg_key[1],
                        indicator_key,
                        leg_key[2],
                        entry.get("ledger_id"),
                        entry["qty"],
                        entry,
                    )
                else:
                    self._trade_book_remove_entry(
                        leg_key[0], leg_key[1], indicator_key, leg_key[2], entry.get("ledger_id")
                    )
    except Exception as exc:
        _mark_ledger_reconciliation_required(self, "synchronize entry quantities", exc)
        raise
