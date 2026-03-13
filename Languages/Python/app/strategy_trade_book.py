from __future__ import annotations

from collections.abc import Iterable
import time


def _side_token(side: str | None) -> str:
    return "BUY" if str(side or "").upper() in {"BUY", "LONG"} else "SELL"


def _indicator_state_entry(self, symbol: str, interval: str, indicator_key: str) -> dict[str, set[str]]:
    sym = str(symbol or "").upper()
    iv = str(interval or "").strip().lower()
    ind = self._canonical_indicator_token(indicator_key) or ""
    key = (sym, iv, ind)
    with self._indicator_state_lock:
        state = self._indicator_state.get(key)
        if not isinstance(state, dict):
            state = {"BUY": set(), "SELL": set()}
            self._indicator_state[key] = state
        else:
            state.setdefault("BUY", set())
            state.setdefault("SELL", set())
        return state


def _trade_book_key(
    self,
    symbol: str,
    interval: str | None,
    indicator_key: str | None,
    side: str,
) -> tuple[str, str, str, str] | None:
    indicator_norm = self._canonical_indicator_token(indicator_key) or ""
    if not indicator_norm:
        return None
    sym_norm = str(symbol or "").upper()
    interval_norm = str(interval or "").strip().lower() or "default"
    side_norm = _side_token(side)
    return (sym_norm, interval_norm, indicator_norm, side_norm)


def _trade_book_add_entry(
    self,
    symbol: str,
    interval: str | None,
    indicator_key: str,
    side: str,
    ledger_id: str | None,
    qty: float | None,
    entry: dict,
) -> None:
    if not ledger_id:
        return
    key = self._trade_book_key(symbol, interval, indicator_key, side)
    if not key:
        return
    try:
        qty_val = max(0.0, float(qty or 0.0))
    except Exception:
        qty_val = 0.0
    if qty_val <= 0.0:
        return
    meta = {
        "ledger_id": ledger_id,
        "qty": qty_val,
        "timestamp": float(entry.get("timestamp") or time.time()),
    }
    try:
        meta["entry_price"] = float(entry.get("entry_price") or 0.0)
    except Exception:
        pass
    try:
        meta["margin_usdt"] = float(entry.get("margin_usdt") or 0.0)
    except Exception:
        pass
    with self._trade_book_lock:
        bucket = self._trade_book.setdefault(key, {})
        bucket[ledger_id] = meta


def _trade_book_remove_entry(
    self,
    symbol: str,
    interval: str | None,
    indicator_key: str,
    side: str,
    ledger_id: str | None,
) -> None:
    if not ledger_id:
        return
    key = self._trade_book_key(symbol, interval, indicator_key, side)
    if not key:
        return
    with self._trade_book_lock:
        bucket = self._trade_book.get(key)
        if not bucket:
            return
        bucket.pop(ledger_id, None)
        if not bucket:
            self._trade_book.pop(key, None)


def _purge_indicator_tracking(self, symbol: str, interval: str, indicator_key: str | None, side: str) -> None:
    indicator_norm = self._canonical_indicator_token(indicator_key) or str(indicator_key or "").strip().lower()
    interval_norm = str(interval or "").strip().lower() or "default"
    side_norm = _side_token(side)
    sym_norm = str(symbol or "").upper()

    with self._trade_book_lock:
        keys_to_drop = []
        for key in list(self._trade_book.keys()):
            sym_k, iv_k, ind_k, side_k = key
            if sym_k != sym_norm or side_k != side_norm:
                continue
            if iv_k != interval_norm:
                continue
            if indicator_norm and ind_k != indicator_norm:
                continue
            keys_to_drop.append(key)
        for key in keys_to_drop:
            self._trade_book.pop(key, None)

    with self._indicator_state_lock:
        keys_to_drop = []
        for state_key, state in list(self._indicator_state.items()):
            sym_k, iv_k, ind_k = state_key
            if sym_k != sym_norm or iv_k != interval_norm:
                continue
            if indicator_norm and ind_k != indicator_norm:
                continue
            if isinstance(state, dict):
                if side_norm in state:
                    state[side_norm].clear()
                if not any(state.values()):
                    keys_to_drop.append(state_key)
        for key in keys_to_drop:
            self._indicator_state.pop(key, None)

    to_purge = []
    for leg_key in list(self._leg_ledger.keys()):
        leg_sym, leg_interval, leg_side = leg_key
        if str(leg_sym or "").upper() != sym_norm:
            continue
        leg_side_norm = _side_token(leg_side)
        if leg_side_norm != side_norm:
            continue
        leg_interval_norm = str(leg_interval or "").strip().lower() or "default"
        if leg_interval_norm != interval_norm:
            continue
        entries = self._leg_entries(leg_key)
        keep_entries = []
        for entry in entries:
            keys = self._extract_indicator_keys(entry)
            if indicator_norm:
                if indicator_norm in keys:
                    continue
            else:
                continue
            keep_entries.append(entry)
        if not keep_entries:
            to_purge.append(leg_key)
        else:
            self._leg_ledger[leg_key]["entries"] = keep_entries
            self._update_leg_snapshot(leg_key, self._leg_ledger[leg_key])
    for leg_key in to_purge:
        self._leg_ledger.pop(leg_key, None)


def _trade_book_update_qty(
    self,
    symbol: str,
    interval: str | None,
    indicator_key: str,
    side: str,
    ledger_id: str | None,
    qty: float,
) -> None:
    if not ledger_id:
        return
    key = self._trade_book_key(symbol, interval, indicator_key, side)
    if not key:
        return
    with self._trade_book_lock:
        bucket = self._trade_book.get(key)
        if not bucket:
            return
        meta = bucket.get(ledger_id)
        if isinstance(meta, dict):
            try:
                meta["qty"] = max(0.0, float(qty or 0.0))
            except Exception:
                meta["qty"] = 0.0


def _trade_book_entries(
    self,
    symbol: str,
    interval: str | None,
    indicator_key: str | None,
    side: str,
) -> list[dict]:
    key = self._trade_book_key(symbol, interval, indicator_key, side)
    if not key:
        return []
    with self._trade_book_lock:
        bucket = self._trade_book.get(key)
        if not bucket:
            return []
        entries: list[dict] = []
        for ledger_id, meta in bucket.items():
            if not ledger_id:
                continue
            record = dict(meta or {})
            record.setdefault("ledger_id", ledger_id)
            entries.append(record)
    entries.sort(key=lambda rec: float(rec.get("timestamp") or 0.0))
    return entries


def _trade_book_total_qty(
    self,
    symbol: str,
    interval: str | None,
    indicator_key: str,
    side: str,
) -> float | None:
    key = self._trade_book_key(symbol, interval, indicator_key, side)
    if not key:
        return None
    with self._trade_book_lock:
        bucket = self._trade_book.get(key)
        if not bucket:
            return None
        total = 0.0
        for meta in bucket.values():
            try:
                total += max(0.0, float(meta.get("qty") or 0.0))
            except Exception:
                continue
        return total


def _indicator_trade_book_qty(
    self,
    symbol: str,
    interval: str | None,
    indicator_key: str,
    side: str,
) -> float:
    key = self._canonical_indicator_token(indicator_key) or indicator_key
    if not key:
        return 0.0
    entries = self._trade_book_entries(symbol, interval, key, side)
    total = 0.0
    for meta in entries:
        try:
            total += max(0.0, float(meta.get("qty") or 0.0))
        except Exception:
            continue
    return total


def _trade_book_has_entries(
    self,
    symbol: str,
    interval: str | None,
    indicator_key: str,
    side: str,
) -> bool:
    key = self._trade_book_key(symbol, interval, indicator_key, side)
    if not key:
        return False
    with self._trade_book_lock:
        bucket = self._trade_book.get(key)
        if not bucket:
            return False
        for meta in bucket.values():
            try:
                if max(0.0, float(meta.get("qty") or 0.0)) > 0.0:
                    return True
            except Exception:
                continue
    return False


def _indicator_has_open(self, symbol: str, interval: str, indicator_key: str, side: str) -> bool:
    side_norm = _side_token(side)
    sym = str(symbol or "").upper()
    iv = str(interval or "").strip().lower()
    indicator_norm = self._canonical_indicator_token(indicator_key) or ""
    key = (sym, iv, indicator_norm)
    if self._trade_book_has_entries(symbol, interval, indicator_norm, side):
        return True
    with self._indicator_state_lock:
        raw = self._indicator_state.get(key)
        if isinstance(raw, dict):
            ids = raw.get(side_norm)
            if ids:
                return True
    return bool(self._iter_indicator_entries(symbol, interval, indicator_key, side))


def _symbol_side_has_other_positions(
    self,
    symbol: str,
    interval: str | None,
    indicator_key: str | None,
    side: str,
) -> bool:
    sym_norm = str(symbol or "").upper()
    interval_norm = str(interval or "").strip().lower()
    side_norm = _side_token(side)
    indicator_norm = self._canonical_indicator_token(indicator_key) or (
        str(indicator_key or "").strip().lower() if indicator_key else ""
    )
    qty_tol = 1e-9
    for (leg_sym, leg_interval, leg_side), _ in list(self._leg_ledger.items()):
        if str(leg_sym or "").upper() != sym_norm:
            continue
        leg_side_norm = _side_token(leg_side)
        if leg_side_norm != side_norm:
            continue
        entries = self._leg_entries((leg_sym, leg_interval, leg_side))
        if not entries:
            continue
        leg_interval_norm = str(leg_interval or "").strip().lower()
        for entry in entries:
            try:
                qty_val = max(0.0, float(entry.get("qty") or 0.0))
            except Exception:
                qty_val = 0.0
            if qty_val <= qty_tol:
                continue
            entry_keys = self._extract_indicator_keys(entry)
            if indicator_norm and leg_interval_norm == interval_norm and indicator_norm in entry_keys:
                continue
            return True
    interval_norm_key = interval_norm or "default"
    with self._trade_book_lock:
        for (sym_key, interval_key, ind_key, side_key), bucket in self._trade_book.items():
            if sym_key != sym_norm or side_key != side_norm:
                continue
            if indicator_norm and interval_key == interval_norm_key and ind_key == indicator_norm:
                continue
            for meta in (bucket or {}).values():
                try:
                    qty_val = max(0.0, float((meta or {}).get("qty") or 0.0))
                except Exception:
                    qty_val = 0.0
                if qty_val > qty_tol:
                    return True
    return False


def _indicator_get_ledger_ids(self, symbol: str, interval: str, indicator_key: str, side: str) -> list[str]:
    side_norm = _side_token(side)
    sym = str(symbol or "").upper()
    iv = str(interval or "").strip().lower()
    indicator_norm = self._canonical_indicator_token(indicator_key) or ""
    key = (sym, iv, indicator_norm)
    ids: set[str] | None = None
    with self._indicator_state_lock:
        state = self._indicator_state.get(key)
        if isinstance(state, dict):
            ids = state.get(side_norm)
    collected: list[str] = []
    if ids:
        collected.extend(list(ids))
    for _, entry in self._iter_indicator_entries(symbol, interval, indicator_key, side):
        ledger = entry.get("ledger_id")
        if ledger and ledger not in collected:
            collected.append(ledger)
    return collected


def _iter_indicator_entries(
    self,
    symbol: str,
    interval: str,
    indicator_key: str,
    side: str,
) -> list[tuple[tuple[str, str, str], dict]]:
    sym_norm = str(symbol or "").upper()
    target_tokens = self._tokenize_interval_label(interval)
    indicator_norm = self._canonical_indicator_token(indicator_key) or ""
    side_norm = _side_token(side)
    if not indicator_norm:
        return []
    matches: list[tuple[tuple[str, str, str], dict]] = []
    for (leg_sym, leg_iv, leg_side), _ in list(self._leg_ledger.items()):
        try:
            if str(leg_sym or "").upper() != sym_norm:
                continue
            leg_tokens = self._tokenize_interval_label(leg_iv)
            if target_tokens != {"-"} and leg_tokens.isdisjoint(target_tokens):
                continue
            leg_side_norm = _side_token(leg_side)
            if leg_side_norm != side_norm:
                continue
            entries = self._leg_entries((leg_sym, leg_iv, leg_side))
            if not entries:
                continue
            for entry in entries:
                try:
                    qty_val = max(0.0, float(entry.get("qty") or 0.0))
                except Exception:
                    qty_val = 0.0
                if qty_val <= 0.0:
                    continue
                sig_tuple = self._normalize_signature_tuple(
                    entry.get("trigger_signature") or entry.get("trigger_indicators")
                )
                if not sig_tuple:
                    continue
                if indicator_norm in sig_tuple:
                    matches.append(((leg_sym, leg_iv, leg_side), entry))
        except Exception:
            continue
    return matches


def _indicator_open_qty(
    self,
    symbol: str,
    interval: str,
    indicator_key: str,
    side: str,
    interval_aliases: Iterable[str] | None = None,
    *,
    strict_interval: bool = False,
) -> float:
    target_tokens = self._tokenize_interval_label(interval)
    if not strict_interval and interval_aliases:
        for alias in interval_aliases:
            norm = self._normalize_interval_token(alias)
            if norm:
                target_tokens.add(norm)
    indicator_norm = self._canonical_indicator_token(indicator_key) or indicator_key
    indicator_lookup_key = indicator_norm or indicator_key
    qty_from_book = self._trade_book_total_qty(symbol, interval, indicator_lookup_key, side)
    if qty_from_book is not None and qty_from_book > 0.0:
        return qty_from_book
    total = 0.0
    try:
        for (_, leg_iv, _), entry in self._iter_indicator_entries(symbol, interval, indicator_lookup_key, side):
            leg_tokens = self._tokenize_interval_label(leg_iv)
            if target_tokens and target_tokens != {"-"} and leg_tokens.isdisjoint(target_tokens):
                continue
            try:
                total += max(0.0, float(entry.get("qty") or 0.0))
            except Exception:
                continue
    except Exception:
        return 0.0
    if qty_from_book is not None:
        return max(total, qty_from_book)
    return total


def _indicator_live_qty_total(
    self,
    symbol: str,
    interval: str,
    indicator_key: str,
    side: str,
    *,
    interval_aliases: Iterable[str] | None = None,
    strict_interval: bool = True,
    use_exchange_fallback: bool = True,
) -> float:
    qty = self._indicator_open_qty(
        symbol,
        interval,
        indicator_key,
        side,
        interval_aliases=interval_aliases,
        strict_interval=strict_interval,
    )
    if qty > 0.0:
        return qty
    qty = self._indicator_trade_book_qty(symbol, interval, indicator_key, side)
    if qty > 0.0:
        return qty
    if not use_exchange_fallback:
        return 0.0
    try:
        desired_ps = None
        if self.binance.get_futures_dual_side():
            desired_ps = "LONG" if side.upper() == "BUY" else "SHORT"
        qty = max(0.0, float(self._current_futures_position_qty(symbol, side, desired_ps) or 0.0))
    except Exception:
        qty = 0.0
    return qty


def bind_strategy_trade_book(strategy_cls, *, canonical_indicator_fn) -> None:
    strategy_cls._canonical_indicator_token = staticmethod(canonical_indicator_fn)
    strategy_cls._indicator_state_entry = _indicator_state_entry
    strategy_cls._trade_book_key = _trade_book_key
    strategy_cls._trade_book_add_entry = _trade_book_add_entry
    strategy_cls._trade_book_remove_entry = _trade_book_remove_entry
    strategy_cls._purge_indicator_tracking = _purge_indicator_tracking
    strategy_cls._trade_book_update_qty = _trade_book_update_qty
    strategy_cls._trade_book_entries = _trade_book_entries
    strategy_cls._trade_book_total_qty = _trade_book_total_qty
    strategy_cls._indicator_trade_book_qty = _indicator_trade_book_qty
    strategy_cls._trade_book_has_entries = _trade_book_has_entries
    strategy_cls._indicator_has_open = _indicator_has_open
    strategy_cls._symbol_side_has_other_positions = _symbol_side_has_other_positions
    strategy_cls._indicator_get_ledger_ids = _indicator_get_ledger_ids
    strategy_cls._iter_indicator_entries = _iter_indicator_entries
    strategy_cls._indicator_open_qty = _indicator_open_qty
    strategy_cls._indicator_live_qty_total = _indicator_live_qty_total
