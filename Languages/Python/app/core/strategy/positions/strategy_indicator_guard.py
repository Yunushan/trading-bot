from __future__ import annotations

import time


def _side_token(side: str | None) -> str:
    return "BUY" if str(side or "").upper() in {"BUY", "LONG"} else "SELL"


def _indicator_hold_ready(
    self,
    entry_ts: float | int | None,
    symbol: str,
    interval: str | None,
    indicator_key: str | None,
    side_label: str,
    interval_seconds: float,
    now_ts: float | None = None,
    *,
    ignore_hold: bool = False,
) -> bool:
    if ignore_hold and self._strategy_coerce_bool(self.config.get("allow_close_ignoring_hold"), False):
        return True
    base_hold = max(0.0, getattr(self, "_indicator_min_hold_seconds", 0.0))
    try:
        interval_seconds = max(1.0, float(interval_seconds or 0.0))
    except Exception:
        interval_seconds = 60.0
    bars_hold = max(0, getattr(self, "_indicator_min_hold_bars", 0))
    effective_hold = max(base_hold, interval_seconds * bars_hold)
    if effective_hold <= 0.0:
        return True
    try:
        ts_val = float(entry_ts or 0.0)
    except Exception:
        ts_val = 0.0
    if ts_val <= 0.0:
        return True
    if now_ts is None:
        now_ts = time.time()
    age = max(0.0, now_ts - ts_val)
    if age >= effective_hold:
        return True
    remaining = max(0.0, effective_hold - age)
    try:
        indicator_label = str(indicator_key or "").upper() or "<indicator>"
        self.log(
            f"{str(symbol or '').upper()}@{interval or 'default'} hold guard: waiting {remaining:.1f}s "
            f"before flipping {indicator_label} {side_label}."
        )
    except Exception:
        pass
    return False


def _indicator_signal_confirmation_ready(
    self,
    symbol: str,
    interval: str | None,
    indicator_key: str,
    action: str,
    interval_seconds: float,
    signal_ts: float | None,
) -> bool:
    confirm_req = max(1, getattr(self, "_indicator_flip_confirm_bars", 1))
    if confirm_req <= 1:
        return True
    action_norm = str(action or "").strip().lower()
    if action_norm not in {"buy", "sell"}:
        return True
    sym_norm = str(symbol or "").upper()
    interval_norm = str(interval or "").strip().lower() or "default"
    indicator_norm = self._canonical_indicator_token(indicator_key) or ""
    if not indicator_norm:
        return True
    key = (sym_norm, interval_norm, indicator_norm)
    tracker = self._indicator_signal_tracker.get(key)
    now_ts = signal_ts or time.time()
    reset_window = max(1.0, float(interval_seconds or 0.0)) * max(confirm_req + 1, 2)
    if tracker:
        try:
            last_ts = float(tracker.get("ts") or 0.0)
        except Exception:
            last_ts = 0.0
        if last_ts and now_ts - last_ts > reset_window:
            tracker = None
    if tracker and tracker.get("direction") == action_norm:
        count = int(tracker.get("count", 0)) + 1
    else:
        count = 1
    tracker = {"direction": action_norm, "count": count, "ts": now_ts}
    self._indicator_signal_tracker[key] = tracker
    if count >= confirm_req:
        return True
    try:
        self.log(
            f"{symbol}@{interval or 'default'} {indicator_key} {action_norm.upper()} "
            f"confirmation {count}/{confirm_req} – waiting additional bar(s)."
        )
    except Exception:
        pass
    return False


def _indicator_entry_matches_close(
    self,
    entry: dict,
    indicator_lookup_key: str,
    *,
    allow_multi_override: bool = False,
) -> bool:
    tokens = self._extract_indicator_keys(entry)
    if not tokens:
        return False
    if indicator_lookup_key not in tokens:
        return False
    allow_multi = self._strategy_coerce_bool(self.config.get("allow_multi_indicator_close"), False)
    if len(tokens) > 1 and not (allow_multi or allow_multi_override):
        return False
    return True


def _record_reentry_block(self, symbol: str, interval: str | None, side: str) -> None:
    base_window = max(0.0, getattr(self, "_indicator_reentry_cooldown_seconds", 0.0))
    bars_window = max(0, getattr(self, "_indicator_reentry_cooldown_bars", 0))
    interval_seconds = self._interval_seconds_value(interval)
    window_seconds = max(base_window, bars_window * interval_seconds)
    if window_seconds <= 0.0:
        return
    sym_norm = (symbol or "").upper()
    interval_norm = (str(interval or "").strip().lower()) or "default"
    side_norm = _side_token(side)
    self._reentry_blocks[(sym_norm, interval_norm, side_norm)] = time.time() + window_seconds


def _mark_indicator_reentry_signal_block(
    self,
    symbol: str,
    interval: str | None,
    entry: dict | None,
    side_label: str,
) -> None:
    if not self._indicator_reentry_requires_reset:
        return
    indicator_keys = self._extract_indicator_keys(entry)
    if not indicator_keys:
        return
    sym_norm = (symbol or "").upper()
    interval_norm = (str(interval or "").strip().lower()) or "default"
    side_norm = _side_token(side_label)
    for indicator_key in indicator_keys:
        indicator_norm = self._canonical_indicator_token(indicator_key) or str(indicator_key or "").strip().lower()
        if not indicator_norm:
            continue
        self._indicator_reentry_signal_blocks[(sym_norm, interval_norm, indicator_norm)] = side_norm


def _record_indicator_close(
    self,
    symbol: str,
    interval: str | None,
    indicator_key: str | None,
    side_label: str,
    qty: float | None = None,
    *,
    ts: float | None = None,
) -> None:
    indicator_norm = self._canonical_indicator_token(indicator_key) or str(indicator_key or "").strip().lower()
    if not indicator_norm:
        return
    sym_norm = (symbol or "").upper()
    interval_norm = (str(interval or "").strip().lower()) or "default"
    side_norm = _side_token(side_label)
    payload: dict[str, float] = {"ts": float(ts if ts is not None else time.time())}
    if qty is not None:
        try:
            payload["qty"] = max(0.0, float(qty))
        except Exception:
            payload["qty"] = 0.0
    self._indicator_recent_closes[(sym_norm, interval_norm, indicator_norm, side_norm)] = payload


def _recent_indicator_close(
    self,
    symbol: str,
    interval: str | None,
    indicator_key: str | None,
    side_label: str,
    *,
    max_age_seconds: float | None = None,
) -> dict | None:
    indicator_norm = self._canonical_indicator_token(indicator_key) or str(indicator_key or "").strip().lower()
    if not indicator_norm:
        return None
    sym_norm = (symbol or "").upper()
    interval_norm = (str(interval or "").strip().lower()) or "default"
    side_norm = _side_token(side_label)
    key = (sym_norm, interval_norm, indicator_norm, side_norm)
    info = self._indicator_recent_closes.get(key)
    if not isinstance(info, dict):
        return None
    if max_age_seconds is None:
        interval_seconds = self._interval_seconds_value(interval)
        max_age_seconds = max(5.0, min(interval_seconds * 1.5, 600.0))
    try:
        max_age_seconds = max(0.0, float(max_age_seconds))
    except Exception:
        max_age_seconds = 0.0
    try:
        ts_val = float(info.get("ts") or 0.0)
    except Exception:
        ts_val = 0.0
    if max_age_seconds <= 0.0:
        return info
    if ts_val <= 0.0:
        self._indicator_recent_closes.pop(key, None)
        return None
    if time.time() - ts_val > max_age_seconds:
        self._indicator_recent_closes.pop(key, None)
        return None
    return info


def _refresh_indicator_reentry_signal_blocks(
    self,
    symbol: str,
    interval: str | None,
    action_side_map: dict[str, str] | None,
) -> None:
    if not self._indicator_reentry_requires_reset:
        return
    sym_norm = (symbol or "").upper()
    interval_norm = (str(interval or "").strip().lower()) or "default"
    normalized_actions: dict[str, str] = {}
    for key, side in (action_side_map or {}).items():
        indicator_norm = self._canonical_indicator_token(key) or str(key or "").strip().lower()
        side_norm = str(side or "").upper()
        if not indicator_norm or side_norm not in {"BUY", "SELL"}:
            continue
        normalized_actions[indicator_norm] = side_norm
    for block_key in list(self._indicator_reentry_signal_blocks.keys()):
        sym_k, iv_k, ind_k = block_key
        if sym_k != sym_norm or iv_k != interval_norm:
            continue
        block_side = self._indicator_reentry_signal_blocks.get(block_key)
        current_side = normalized_actions.get(ind_k)
        if current_side != block_side:
            self._indicator_reentry_signal_blocks.pop(block_key, None)


def _reentry_block_remaining(
    self,
    symbol: str,
    interval: str | None,
    side: str,
    *,
    now_ts: float | None = None,
) -> float:
    key = (
        (symbol or "").upper(),
        (str(interval or "").strip().lower()) or "default",
        _side_token(side),
    )
    block_until = self._reentry_blocks.get(key)
    if not block_until:
        return 0.0
    if now_ts is None:
        now_ts = time.time()
    remaining = block_until - now_ts
    if remaining <= 0.0:
        self._reentry_blocks.pop(key, None)
        return 0.0
    return remaining


def _mark_guard_closed(self, symbol: str, interval: str | None, side: str) -> None:
    side_norm = _side_token(side)
    self._record_reentry_block(symbol, interval, side_norm)
    guard_obj = getattr(self, "guard", None)
    if not guard_obj or not hasattr(guard_obj, "mark_closed"):
        return
    try:
        guard_obj.mark_closed(symbol, interval, side_norm)
    except Exception:
        pass


def _guard_mark_leg_closed(self, leg_key: tuple[str, str, str]) -> None:
    try:
        symbol, interval, side = leg_key
        side_norm = _side_token(side)
        self._mark_guard_closed(symbol, interval, side_norm)
    except Exception:
        pass


def _enter_close_guard(self, symbol: str, side: str, label: str | None = None) -> bool:
    sym = (symbol or "").upper()
    side_norm = _side_token(side)
    if not sym or side_norm not in {"BUY", "SELL"}:
        return True
    allow_opposite = self._strategy_coerce_bool(self.config.get("allow_opposite_positions"), True)
    key = (sym, side_norm)
    opposite = "SELL" if side_norm == "BUY" else "BUY"
    opposite_key = (sym, opposite)
    with self._close_guard_lock:
        existing = self._close_inflight.get(key)
        if existing:
            existing["depth"] = int(existing.get("depth") or 0) + 1
            return True
        if (not allow_opposite) and opposite_key in self._close_inflight:
            return False
        self._close_inflight[key] = {"side": side_norm, "label": label or "", "depth": 1}
        return True


def _exit_close_guard(self, symbol: str, side: str) -> None:
    sym = (symbol or "").upper()
    side_norm = _side_token(side)
    if not sym or side_norm not in {"BUY", "SELL"}:
        return
    key = (sym, side_norm)
    with self._close_guard_lock:
        entry = self._close_inflight.get(key)
        if not entry:
            return
        depth = int(entry.get("depth") or 1) - 1
        if depth <= 0:
            self._close_inflight.pop(key, None)
        else:
            entry["depth"] = depth


def _describe_close_guard(self, symbol: str) -> dict | None:
    sym = (symbol or "").upper()
    if not sym:
        return None
    with self._close_guard_lock:
        entries = [entry for (sym_key, _), entry in self._close_inflight.items() if sym_key == sym]
        if not entries:
            return None
        entry = entries[0]
        return {
            "side": str(entry.get("side") or ""),
            "label": str(entry.get("label") or ""),
        }


def _indicator_cooldown_remaining(
    self,
    symbol: str,
    interval: str | None,
    indicator_key: str | None,
    next_side: str,
    interval_seconds: float,
    now_ts: float | None = None,
) -> float:
    try:
        interval_seconds = max(1.0, float(interval_seconds or 0.0))
    except Exception:
        interval_seconds = 60.0
    cooldown_window = max(
        float(getattr(self, "_indicator_flip_cooldown_seconds", 0.0)),
        float(max(0, getattr(self, "_indicator_flip_cooldown_bars", 0))) * interval_seconds,
    )
    if cooldown_window <= 0.0:
        return 0.0
    sym_norm = str(symbol or "").upper()
    interval_norm = str(interval or "").strip().lower() or "default"
    indicator_norm = self._canonical_indicator_token(indicator_key) or ""
    if not indicator_norm:
        return 0.0
    last = self._indicator_last_action.get((sym_norm, interval_norm, indicator_norm))
    if not isinstance(last, dict):
        return 0.0
    last_side = str(last.get("side") or "").upper()
    if last_side == str(next_side or "").upper():
        return 0.0
    try:
        last_ts = float(last.get("ts") or 0.0)
    except Exception:
        last_ts = 0.0
    if last_ts <= 0.0:
        return 0.0
    if now_ts is None:
        now_ts = time.time()
    elapsed = max(0.0, float(now_ts) - last_ts)
    remaining = cooldown_window - elapsed
    return max(0.0, remaining)


def bind_strategy_indicator_guard(strategy_cls, *, coerce_bool_fn) -> None:
    strategy_cls._strategy_coerce_bool = staticmethod(coerce_bool_fn)
    strategy_cls._indicator_hold_ready = _indicator_hold_ready
    strategy_cls._indicator_signal_confirmation_ready = _indicator_signal_confirmation_ready
    strategy_cls._indicator_entry_matches_close = _indicator_entry_matches_close
    strategy_cls._record_reentry_block = _record_reentry_block
    strategy_cls._mark_indicator_reentry_signal_block = _mark_indicator_reentry_signal_block
    strategy_cls._record_indicator_close = _record_indicator_close
    strategy_cls._recent_indicator_close = _recent_indicator_close
    strategy_cls._refresh_indicator_reentry_signal_blocks = _refresh_indicator_reentry_signal_blocks
    strategy_cls._reentry_block_remaining = _reentry_block_remaining
    strategy_cls._mark_guard_closed = _mark_guard_closed
    strategy_cls._guard_mark_leg_closed = _guard_mark_leg_closed
    strategy_cls._enter_close_guard = _enter_close_guard
    strategy_cls._exit_close_guard = _exit_close_guard
    strategy_cls._describe_close_guard = _describe_close_guard
    strategy_cls._indicator_cooldown_remaining = _indicator_cooldown_remaining
