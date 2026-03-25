from __future__ import annotations

from collections.abc import Iterable


def _prepare_signal_order_slot_state(
    self,
    *,
    cw,
    side: str,
    lev: int,
    signature,
    trigger_labels,
    context_key: str,
    indicator_key_hint,
    indicator_tokens_for_order,
    flip_active: bool,
    abort_guard,
) -> dict[str, object]:
    def _abort() -> dict[str, object]:
        abort_guard()
        return {"aborted": True}

    sig_tuple_base = tuple(
        sorted(
            str(part or "").strip().lower()
            for part in (signature or ())
            if str(part or "").strip()
        )
    )
    indicator_key_for_order = self._canonical_indicator_token(indicator_key_hint) or indicator_key_hint
    if not indicator_key_for_order and len(sig_tuple_base) == 1:
        indicator_key_for_order = sig_tuple_base[0]
    if not indicator_key_for_order and trigger_labels:
        labels_norm = [
            self._canonical_indicator_token(lbl) or str(lbl or "").strip().lower()
            for lbl in trigger_labels
            if str(lbl or "").strip()
        ]
        if len(labels_norm) == 1:
            indicator_key_for_order = labels_norm[0]
    if indicator_key_for_order:
        indicator_key_norm = self._canonical_indicator_token(indicator_key_for_order) or indicator_key_for_order
        if indicator_key_norm and indicator_key_norm not in indicator_tokens_for_order:
            indicator_tokens_for_order.append(indicator_key_norm)

    slot_interval_norm = str(cw.get("interval") or "").strip().lower()
    slot_key_tuple = self._trade_book_key(cw["symbol"], slot_interval_norm, indicator_key_for_order, side)
    qty_tol_slot = 1e-9
    if indicator_key_for_order:
        slot_live_qty = self._indicator_open_qty(
            cw["symbol"],
            slot_interval_norm,
            indicator_key_for_order,
            side,
            strict_interval=True,
        )
        if slot_live_qty > qty_tol_slot:
            self.log(
                f"{cw['symbol']}@{cw.get('interval')} {indicator_key_for_order} {side} slot already active; skipping new entry."
            )
            return _abort()
        slot_book_qty = self._indicator_trade_book_qty(
            cw["symbol"],
            slot_interval_norm,
            indicator_key_for_order,
            side,
        )
        if slot_book_qty > qty_tol_slot:
            self.log(
                f"{cw['symbol']}@{cw.get('interval')} {indicator_key_for_order} {side} slot already pending ({slot_book_qty:.10f}); skipping duplicate open."
            )
            return _abort()

    entries_side_all: list[tuple[tuple[str, str, str], dict]] = []
    try:
        for (leg_sym, leg_iv, leg_side), _ in list(self._leg_ledger.items()):
            if str(leg_sym or "").upper() != str(cw["symbol"]).upper():
                continue
            leg_side_norm = str(leg_side or "").upper()
            if leg_side_norm in {"LONG", "SHORT"}:
                leg_side_norm = "BUY" if leg_side_norm == "LONG" else "SELL"
            if leg_side_norm != side:
                continue
            leg_entries = self._leg_entries((leg_sym, leg_iv, leg_side))
            for entry in leg_entries:
                entries_side_all.append(((leg_sym, leg_iv, leg_side), entry))
    except Exception:
        entries_side_all = list(entries_side_all)

    def _normalized_signature(entry_dict: dict) -> tuple[str, ...]:
        raw_sig = entry_dict.get("trigger_signature") or entry_dict.get("trigger_indicators")
        if isinstance(raw_sig, Iterable) and not isinstance(raw_sig, (str, bytes)):
            parts: list[str] = []
            for part in raw_sig:
                text = str(part or "").strip().lower()
                if text:
                    parts.append(text)
            parts.sort()
            return tuple(parts)
        return tuple()

    def _slot_token_from_entry(entry_dict: dict, leg_interval: str | None) -> str:
        iv_key = str(
            entry_dict.get("interval") or entry_dict.get("interval_display") or leg_interval or ""
        ).strip().lower()
        indicator_ids = self._extract_indicator_keys(entry_dict)
        if indicator_ids:
            base = f"ind:{indicator_ids[0]}"
        else:
            sig_norm = _normalized_signature(entry_dict)
            if sig_norm:
                base = "sig:" + "|".join(sig_norm)
            else:
                ledger_id = entry_dict.get("ledger_id")
                if ledger_id:
                    base = f"id:{ledger_id}"
                else:
                    base = f"side:{side}"
        if iv_key:
            return f"{base}@{iv_key}"
        return base

    target_interval_tokens = self._tokenize_interval_label(cw.get("interval"))
    indicator_entries_all: list[tuple[tuple[str, str, str], dict]] = []
    if indicator_key_for_order:
        for leg_key, entry in entries_side_all:
            leg_iv_tokens = self._tokenize_interval_label(leg_key[1])
            if leg_iv_tokens != target_interval_tokens:
                continue
            keys_for_entry = self._extract_indicator_keys(entry)
            try:
                qty_val_slot = max(0.0, float(entry.get("qty") or 0.0))
            except Exception:
                qty_val_slot = 0.0
            if qty_val_slot <= qty_tol_slot:
                continue
            if indicator_key_for_order in keys_for_entry:
                indicator_entries_all.append((leg_key, entry))
    elif sig_tuple_base:
        for leg_key, entry in entries_side_all:
            leg_iv_tokens = self._tokenize_interval_label(leg_key[1])
            if leg_iv_tokens != target_interval_tokens:
                continue
            try:
                qty_val_slot = max(0.0, float(entry.get("qty") or 0.0))
            except Exception:
                qty_val_slot = 0.0
            if qty_val_slot <= qty_tol_slot:
                continue
            if _normalized_signature(entry) == sig_tuple_base:
                indicator_entries_all.append((leg_key, entry))
    else:
        for leg_key, entry in entries_side_all:
            leg_iv_tokens = self._tokenize_interval_label(leg_key[1])
            if leg_iv_tokens != target_interval_tokens:
                continue
            try:
                qty_val_slot = max(0.0, float(entry.get("qty") or 0.0))
            except Exception:
                qty_val_slot = 0.0
            if qty_val_slot > qty_tol_slot:
                indicator_entries_all.append((leg_key, entry))

    active_slot_tokens_all: set[str] = set()
    for leg_key, entry in indicator_entries_all:
        active_slot_tokens_all.add(_slot_token_from_entry(entry, leg_key[1]))

    existing_margin_indicator_total = sum(
        self._entry_margin_value(entry, lev)
        for _, entry in indicator_entries_all
    )

    slot_token_base = (
        f"ind:{indicator_key_for_order}"
        if indicator_key_for_order
        else (
            "sig:" + "|".join(sig_tuple_base)
            if sig_tuple_base
            else f"side:{side}"
        )
    )
    order_iv_key = str(cw.get("interval") or "").strip().lower()
    slot_token_for_order = f"{slot_token_base}@{order_iv_key}" if order_iv_key else slot_token_base
    slot_label = (
        indicator_key_for_order.upper()
        if indicator_key_for_order
        else ("|".join(sig_tuple_base) if sig_tuple_base else "current slot")
    )
    slot_count_existing = len(indicator_entries_all)
    if slot_count_existing > 0:
        if flip_active:
            try:
                desired_ps_check = None
                if self.binance.get_futures_dual_side():
                    desired_ps_check = "LONG" if side == "BUY" else "SHORT"
                exch_qty = max(
                    0.0,
                    float(self._current_futures_position_qty(cw["symbol"], side, desired_ps_check) or 0.0),
                )
            except Exception:
                exch_qty = 0.0
            if exch_qty <= qty_tol_slot:
                try:
                    if indicator_key_for_order:
                        self._purge_indicator_tracking(
                            cw["symbol"], order_iv_key, indicator_key_for_order, side
                        )
                except Exception:
                    pass
                active_slot_tokens_all = set()
                existing_margin_indicator_total = 0.0
                slot_count_existing = 0
            else:
                self.log(
                    f"{cw['symbol']}@{cw.get('interval')} {slot_label} {side} slot blocked: "
                    f"exchange still open ({exch_qty:.10f})."
                )
                return _abort()
        if slot_count_existing > 0:
            self.log(
                f"{cw['symbol']}@{cw.get('interval')} {slot_label} {side} slot already open; blocking additional entries."
            )
            return _abort()

    slot_suffix = "slot0"
    if signature:
        signature = tuple(list(signature) + [slot_suffix])
    else:
        signature = (slot_suffix,)
    if isinstance(trigger_labels, (list, tuple)):
        try:
            trigger_labels = [str(lbl).strip() for lbl in trigger_labels if str(lbl).strip()]
        except Exception:
            trigger_labels = []
    elif isinstance(trigger_labels, str) and trigger_labels.strip():
        trigger_labels = [trigger_labels.strip()]
    else:
        trigger_labels = []
    context_key = f"{context_key}|slot0"

    return {
        "aborted": False,
        "signature": signature,
        "trigger_labels": trigger_labels,
        "context_key": context_key,
        "indicator_tokens_for_order": indicator_tokens_for_order,
        "entries_side_all": entries_side_all,
        "existing_margin_indicator_total": existing_margin_indicator_total,
        "active_slot_tokens_all": active_slot_tokens_all,
        "slot_label": slot_label,
        "slot_token_for_order": slot_token_for_order,
        "slot_key_tuple": slot_key_tuple,
    }


def bind_strategy_signal_order_slot_runtime(strategy_cls) -> None:
    strategy_cls._prepare_signal_order_slot_state = _prepare_signal_order_slot_state
