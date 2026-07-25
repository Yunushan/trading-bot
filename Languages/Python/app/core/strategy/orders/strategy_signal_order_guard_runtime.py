from __future__ import annotations

import logging
import math
import time


_LOGGER = logging.getLogger(__name__)


def _safe_log(self, message: str, *, level: int = logging.WARNING) -> bool:
    callback = getattr(self, "log", None)
    if callable(callback):
        try:
            callback(message)
            return True
        except Exception:
            _LOGGER.exception("Signal order guard log callback failed while reporting: %s", message)
            return False
    _LOGGER.log(level, message)
    return False


def _guard_timestamp(value: object, *, fallback: float) -> tuple[float, bool]:
    try:
        timestamp = float(value or 0.0)
    except (TypeError, ValueError, OverflowError):
        return fallback, False
    if not math.isfinite(timestamp) or timestamp < 0.0:
        return fallback, False
    return timestamp, True


def _compute_signal_order_guard_window(self, interval_value, signature_guard_key) -> float:
    try:
        interval_seconds = float(self._interval_to_seconds(str(interval_value or "1m")))
    except Exception:
        interval_seconds = 60.0
        _LOGGER.debug("Unable to parse signal order guard interval; using 60 seconds", exc_info=True)
    fast_context = False
    try:
        fast_context = any(str(part or "").startswith("slot") for part in signature_guard_key)
    except Exception:
        fast_context = False
        _LOGGER.debug("Unable to inspect signal order guard signature", exc_info=True)
    guard_window_base = max(8.0, min(45.0, interval_seconds * 1.5))
    if fast_context:
        return min(
            guard_window_base,
            max(2.0, min(6.0, interval_seconds * 0.12)),
        )
    return guard_window_base


def _reset_stale_signal_order_guard(self, *, symbol: str, interval_key: str, side: str, guard_window: float) -> None:
    try:
        qty_tol_guard = 1e-9
        live_qty_sym = 0.0
        live_qty_unknown = False
        sym_upper = str(symbol or "").upper()
        for (sym_l, _iv_l, _side_l), leg_state in list(self._leg_ledger.items()):
            if str(sym_l or "").upper() != sym_upper:
                continue
            try:
                leg_qty = float(leg_state.get("qty") or 0.0)
                if not math.isfinite(leg_qty) or leg_qty < 0.0:
                    raise ValueError("non-finite or negative ledger quantity")
                live_qty_sym = max(live_qty_sym, leg_qty)
            except (AttributeError, TypeError, ValueError, OverflowError):
                live_qty_unknown = True
                _LOGGER.warning(
                    "Signal order guard retained stale state because %s ledger quantity is invalid",
                    sym_upper,
                    exc_info=True,
                )
        guard_key_symbol = (symbol, interval_key, side)
        state = type(self)._SYMBOL_ORDER_STATE.get(guard_key_symbol)
        if isinstance(state, dict):
            now = time.time()
            last_ts_guard, last_ts_valid = _guard_timestamp(state.get("last"), fallback=now)
            age_candidates = []
            state_age_unknown = not last_ts_valid and state.get("last") not in (None, "", 0, 0.0)
            if last_ts_guard > 0.0:
                age_candidates.append(last_ts_guard)
            for bucket_name in ("pending_map", "signatures"):
                bucket = state.get(bucket_name)
                if not isinstance(bucket, dict):
                    continue
                for ts in bucket.values():
                    ts_value, ts_valid = _guard_timestamp(ts, fallback=now)
                    if not ts_valid:
                        state_age_unknown = True
                    if ts_value > 0.0:
                        age_candidates.append(ts_value)
            age = (now - max(age_candidates)) if age_candidates else float("inf")
            if not live_qty_unknown and not state_age_unknown and live_qty_sym <= qty_tol_guard and age > guard_window * 2.0:
                state["pending_map"] = {}
                state["signatures"] = {}
                state["last"] = 0.0
                type(self)._SYMBOL_ORDER_STATE[guard_key_symbol] = state
                _safe_log(
                    self,
                    f"{symbol}@{interval_key} symbol guard reset after {age:.1f}s stale and no live qty.",
                    level=logging.INFO,
                )
            elif live_qty_unknown or state_age_unknown:
                _safe_log(
                    self,
                    f"{symbol}@{interval_key} symbol guard retained because stale-state safety could not be proven.",
                )
    except Exception as exc:
        _safe_log(
            self,
            f"{symbol}@{interval_key} symbol guard stale-state check failed; retaining guard state: {exc}",
        )


def _prepare_signal_order_guard(
    self,
    *,
    cw,
    side: str,
    interval_norm: str,
    interval_key: str,
    trigger_labels,
    signature,
    sig_sorted,
    signature_guard_key,
    signature_label: str,
    indicator_key_hint,
    indicator_tokens_for_order,
    current_bar_marker,
    bar_sig_key,
    flip_active: bool,
) -> dict[str, object]:
    indicator_guard_override = flip_active
    guard_override_used = False
    indicator_opposite_side = "SELL" if side == "BUY" else "BUY"
    indicator_tokens_for_guard = list(indicator_tokens_for_order or [])
    if indicator_key_hint:
        hint_norm = self._canonical_indicator_token(indicator_key_hint) or indicator_key_hint
        if hint_norm and hint_norm not in indicator_tokens_for_guard:
            indicator_tokens_for_guard.append(hint_norm)
    if indicator_tokens_for_guard and not indicator_guard_override:
        try:
            indicator_guard_override = any(
                self._indicator_has_open(
                    cw["symbol"],
                    interval_norm,
                    token,
                    indicator_opposite_side,
                )
                for token in indicator_tokens_for_guard
            )
        except Exception:
            indicator_guard_override = False
            _safe_log(
                self,
                f"{cw['symbol']}@{interval_key} indicator exposure check failed; guard override disabled.",
            )

    active_check_signature = signature if signature else tuple(sorted(trigger_labels or []))
    if self._symbol_signature_active(cw["symbol"], side, active_check_signature, cw.get("interval")):
        _safe_log(
            self,
            f"{cw['symbol']}@{interval_key} duplicate {side} suppressed (signature {signature_label} still open).",
            level=logging.INFO,
        )
        return {
            "aborted": True,
            "indicator_tokens_for_guard": indicator_tokens_for_guard,
            "guard_key_symbol": (cw["symbol"], interval_key, side),
            "guard_window": 0.0,
            "guard_claimed": False,
        }

    guard_window = self._compute_signal_order_guard_window(cw.get("interval"), signature_guard_key)
    self._reset_stale_signal_order_guard(
        symbol=cw["symbol"],
        interval_key=interval_key,
        side=side,
        guard_window=guard_window,
    )

    if current_bar_marker is not None:
        with type(self)._BAR_GUARD_LOCK:
            global_tracker = type(self)._BAR_GLOBAL_SIGNATURES.get(bar_sig_key)
            if not global_tracker or global_tracker.get("bar") != current_bar_marker:
                global_tracker = {"bar": current_bar_marker, "signatures": set()}
                type(self)._BAR_GLOBAL_SIGNATURES[bar_sig_key] = global_tracker
            global_sig_set = global_tracker.setdefault("signatures", set())
            if sig_sorted in global_sig_set and not flip_active:
                _safe_log(
                    self,
                    f"{cw['symbol']}@{interval_key} global duplicate {side} suppressed "
                    f"(order already placed this bar).",
                    level=logging.INFO,
                )
                return {
                    "aborted": True,
                    "indicator_tokens_for_guard": indicator_tokens_for_guard,
                    "guard_key_symbol": (cw["symbol"], interval_key, side),
                    "guard_window": guard_window,
                    "guard_claimed": False,
                }
        tracker = self._bar_order_tracker.get(bar_sig_key)
        if not tracker or tracker.get("bar") != current_bar_marker:
            tracker = {"bar": current_bar_marker, "signatures": set()}
            self._bar_order_tracker[bar_sig_key] = tracker
        sig_set = tracker.setdefault("signatures", set())
        if sig_sorted in sig_set and not flip_active:
            if self.stopped():
                return {
                    "aborted": True,
                    "indicator_tokens_for_guard": indicator_tokens_for_guard,
                    "guard_key_symbol": (cw["symbol"], interval_key, side),
                    "guard_window": guard_window,
                    "guard_claimed": False,
                }
            _safe_log(
                self,
                f"{cw['symbol']}@{interval_key} duplicate {side} suppressed (order already placed this bar).",
                level=logging.INFO,
            )
            return {
                "aborted": True,
                "indicator_tokens_for_guard": indicator_tokens_for_guard,
                "guard_key_symbol": (cw["symbol"], interval_key, side),
                "guard_window": guard_window,
                "guard_claimed": False,
            }
        # Keep current behavior: mark early so later duplicates on the same bar are suppressed.
        global_sig_set.add(sig_sorted)
        sig_set.add(sig_sorted)

    guard_key_symbol = (cw["symbol"], interval_key, side)
    now_guard = time.time()
    guard_claimed = False

    with type(self)._SYMBOL_GUARD_LOCK:
        entry_guard = type(self)._SYMBOL_ORDER_STATE.get(guard_key_symbol)
        if not isinstance(entry_guard, dict):
            entry_guard = {}
        last_ts, last_ts_valid = _guard_timestamp(entry_guard.get("last"), fallback=now_guard)
        if not last_ts_valid and entry_guard.get("last") not in (None, "", 0, 0.0):
            _safe_log(
                self,
                f"{cw['symbol']}@{interval_key} invalid last-order timestamp retained as active guard state.",
            )
        signatures_state = entry_guard.get("signatures")
        if not isinstance(signatures_state, dict):
            signatures_state = {}
        pending_map = entry_guard.get("pending_map")
        if not isinstance(pending_map, dict):
            pending_map = {}
        expired = []
        for sig, ts in list(signatures_state.items()):
            ts_value, ts_valid = _guard_timestamp(ts, fallback=now_guard)
            if not ts_valid:
                _safe_log(
                    self,
                    f"{cw['symbol']}@{interval_key} invalid signature timestamp retained fail-closed.",
                )
                continue
            if now_guard - ts_value > guard_window:
                expired.append(sig)
        for sig in expired:
            signatures_state.pop(sig, None)
        pending_expired = []
        for sig, ts in list(pending_map.items()):
            ts_value, ts_valid = _guard_timestamp(ts, fallback=now_guard)
            if not ts_valid:
                _safe_log(
                    self,
                    f"{cw['symbol']}@{interval_key} invalid pending-order timestamp retained fail-closed.",
                )
                continue
            if now_guard - ts_value > guard_window * 1.5:
                pending_expired.append(sig)
        for sig in pending_expired:
            pending_map.pop(sig, None)
        entry_guard["signatures"] = signatures_state
        entry_guard["pending_map"] = pending_map
        if signature_guard_key in pending_map:
            if not indicator_guard_override:
                _safe_log(
                    self,
                    f"{cw['symbol']}@{interval_key} symbol-level guard suppressed {side} entry "
                    f"(previous order still pending for {signature_label}).",
                    level=logging.INFO,
                )
                return {
                    "aborted": True,
                    "indicator_tokens_for_guard": indicator_tokens_for_guard,
                    "guard_key_symbol": guard_key_symbol,
                    "guard_window": guard_window,
                    "guard_claimed": False,
                }
            guard_override_used = True
        elapsed_since_last = now_guard - last_ts if last_ts > 0.0 else float("inf")
        if signature_guard_key in signatures_state:
            if elapsed_since_last < guard_window:
                if not indicator_guard_override:
                    remaining = guard_window - elapsed_since_last
                    _safe_log(
                        self,
                        f"{cw['symbol']}@{interval_key} symbol-level guard suppressed {side} entry "
                        f"(trigger {signature_label} still within guard window, wait {remaining:.1f}s).",
                        level=logging.INFO,
                    )
                    return {
                        "aborted": True,
                        "indicator_tokens_for_guard": indicator_tokens_for_guard,
                        "guard_key_symbol": guard_key_symbol,
                        "guard_window": guard_window,
                        "guard_claimed": False,
                    }
                guard_override_used = True
            signatures_state.pop(signature_guard_key, None)
        elif not signatures_state and elapsed_since_last < guard_window:
            if not indicator_guard_override:
                remaining = guard_window - elapsed_since_last
                _safe_log(
                    self,
                    f"{cw['symbol']}@{interval_key} symbol-level guard suppressed {side} entry "
                    f"(last order {elapsed_since_last:.1f}s ago, wait {remaining:.1f}s).",
                    level=logging.INFO,
                )
                return {
                    "aborted": True,
                    "indicator_tokens_for_guard": indicator_tokens_for_guard,
                    "guard_key_symbol": guard_key_symbol,
                    "guard_window": guard_window,
                    "guard_claimed": False,
                }
            guard_override_used = True
        entry_guard["window"] = guard_window
        entry_guard["last"] = last_ts
        entry_guard["signatures"] = signatures_state
        pending_map[signature_guard_key] = now_guard
        entry_guard["pending_map"] = pending_map
        type(self)._SYMBOL_ORDER_STATE[guard_key_symbol] = entry_guard
        guard_claimed = True

    if guard_override_used:
        indicator_label = str(indicator_key_hint or signature_label).upper()
        _safe_log(
            self,
            f"{cw['symbol']}@{interval_key} guard override: forcing {side} for indicator {indicator_label} "
            f"to flip opposite exposure.",
            level=logging.INFO,
        )

    return {
        "aborted": False,
        "indicator_tokens_for_guard": indicator_tokens_for_guard,
        "guard_key_symbol": guard_key_symbol,
        "guard_window": guard_window,
        "guard_claimed": guard_claimed,
    }


def bind_strategy_signal_order_guard_runtime(strategy_cls) -> None:
    strategy_cls._compute_signal_order_guard_window = _compute_signal_order_guard_window
    strategy_cls._reset_stale_signal_order_guard = _reset_stale_signal_order_guard
    strategy_cls._prepare_signal_order_guard = _prepare_signal_order_guard
