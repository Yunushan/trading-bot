from __future__ import annotations

import math
import time

from .close_execution import _pause_for_close_uncertainty, _safe_log
from .strategy_close_opposite_common_runtime import _goal_met, _reduce_goal, _refresh_positions_snapshot


def _indicator_scope_is_already_flat(self, state: dict[str, object]) -> bool:
    indicator_tokens = state["indicator_tokens"]
    if not indicator_tokens:
        return False
    symbol = str(state["symbol"])
    interval_norm = str(state["interval_norm"])
    interval_tokens = state["interval_tokens"]
    opp = str(state["opp"])
    qty_goal = state.get("qty_goal")
    qty_tol = float(state["qty_tol"])

    try:
        live_opp_qty = self._indicator_open_qty(
            symbol,
            interval_norm,
            indicator_tokens[0],
            opp,
            interval_aliases=interval_tokens,
            strict_interval=True,
        )
    except Exception as exc:
        _pause_for_close_uncertainty(
            self,
            f"{symbol}@{interval_norm or 'default'} indicator open-quantity lookup failed: {exc}",
            reconciliation_required=False,
        )
        return False
    if live_opp_qty <= qty_tol:
        try:
            live_opp_qty = self._indicator_trade_book_qty(symbol, interval_norm, indicator_tokens[0], opp)
        except Exception as exc:
            _pause_for_close_uncertainty(
                self,
                f"{symbol}@{interval_norm or 'default'} indicator trade-book quantity lookup failed: {exc}",
                reconciliation_required=False,
            )
            return False
    if live_opp_qty <= qty_tol:
        try:
            live_opp_qty = max(0.0, float(self._current_futures_position_qty(symbol, opp, None) or 0.0))
        except Exception as exc:
            _pause_for_close_uncertainty(
                self,
                f"{symbol}@{interval_norm or 'default'} exchange position quantity lookup failed: {exc}",
                reconciliation_required=False,
            )
            return False
    try:
        qty_goal_flat = qty_goal is None or (
            math.isfinite(float(qty_goal)) and float(qty_goal) <= qty_tol
        )
    except (TypeError, ValueError, OverflowError):
        _pause_for_close_uncertainty(
            self,
            f"{symbol}@{interval_norm or 'default'} close quantity goal is invalid",
            reconciliation_required=False,
        )
        return False
    return (qty_goal is None and live_opp_qty <= qty_tol) or (
        qty_goal is not None and qty_goal_flat and live_opp_qty <= qty_tol
    )


def _close_indicator_scope(
    self,
    state: dict[str, object],
    indicator_position_side: str | None,
) -> bool | None:
    symbol = str(state["symbol"])
    interval_norm = str(state["interval_norm"])
    interval = str(state["interval"])
    indicator_tokens = state["indicator_tokens"]
    opp = str(state["opp"])
    desired = str(state["desired"])

    if indicator_tokens:
        cw_stub = {"symbol": symbol, "interval": interval_norm}
        state["indicator_target_cleared"] = True
        for indicator_hint in indicator_tokens:
            closed_count = 0
            closed_qty_total = 0.0
            try:
                closed_count, closed_qty_total = self._close_indicator_positions(
                    cw_stub,
                    interval_norm,
                    indicator_hint,
                    opp,
                    indicator_position_side,
                    signature_hint=state["signature_hint_tokens"],
                    ignore_hold=True,
                    qty_limit=state.get("qty_goal"),
                    strict_interval=True,
                    allow_hedge_close=True,
                )
            except Exception as exc:
                _pause_for_close_uncertainty(
                    self,
                    f"{symbol}@{interval} indicator-close {indicator_hint} failed: {exc}",
                    reconciliation_required=False,
                )
            if closed_count:
                state["closed_any"] = True
                _reduce_goal(state, closed_qty_total)
                ctx_interval = interval_norm or "default"
                _safe_log(
                    self,
                    f"{symbol}@{ctx_interval} flip {indicator_hint}: closed {closed_count} "
                    f"{opp} leg(s) before opening {desired}.",
                )
                refreshed = _refresh_positions_snapshot(self, symbol, interval)
                if refreshed is None:
                    return False
                state["positions"] = refreshed
                if _goal_met(state):
                    return True
            try:
                indicator_clear = not self._indicator_has_open(symbol, interval_norm, indicator_hint, opp)
            except Exception as exc:
                indicator_clear = False
                _pause_for_close_uncertainty(
                    self,
                    f"{symbol}@{interval_norm or 'default'} indicator residual-state lookup failed: {exc}",
                    reconciliation_required=False,
                )
            state["indicator_target_cleared"] = bool(state["indicator_target_cleared"]) and indicator_clear
            if _goal_met(state):
                return True

    if indicator_tokens:
        if state["indicator_target_cleared"]:
            return True if state.get("qty_goal") is None else _goal_met(state)
        return False
    if state["signature_hint_tokens"] and not state["indicator_target_cleared"]:
        return False
    if state["allow_opposite_requested"]:
        return True
    return None


def _resolve_indicator_residuals(
    self,
    state: dict[str, object],
    indicator_position_side: str | None,
) -> bool | None:
    indicator_tokens = state["indicator_tokens"]
    if not indicator_tokens or state["indicator_target_cleared"]:
        if indicator_tokens:
            return True if state.get("qty_goal") is None else _goal_met(state)
        return None

    symbol = str(state["symbol"])
    interval_norm = str(state["interval_norm"])
    opp = str(state["opp"])
    interval_tokens = state["interval_tokens"]

    if not self._strategy_coerce_bool(self.config.get("allow_close_ignoring_hold"), False):
        now_hold_ts = time.time()
        hold_ready_any = False
        hold_candidate_seen = False
        remaining_values: list[float] = []
        for indicator_hint in indicator_tokens:
            for leg_key, entry in self._iter_indicator_entries(symbol, interval_norm, indicator_hint, opp):
                try:
                    ts_val = float(entry.get("timestamp") or 0.0)
                    if not math.isfinite(ts_val) or ts_val <= 0.0:
                        raise ValueError("entry timestamp is not positive and finite")
                except (TypeError, ValueError, OverflowError) as exc:
                    _pause_for_close_uncertainty(
                        self,
                        f"{symbol}@{interval_norm or 'default'} indicator hold timestamp is invalid: {exc}",
                        reconciliation_required=True,
                    )
                    return False
                if ts_val <= 0.0:
                    continue
                hold_candidate_seen = True
                interval_seconds_entry = self._interval_seconds_value(leg_key[1] or interval_norm)
                effective_hold = max(
                    max(0.0, float(getattr(self, "_indicator_min_hold_seconds", 0.0) or 0.0)),
                    max(0, int(getattr(self, "_indicator_min_hold_bars", 0) or 0)) * interval_seconds_entry,
                )
                if effective_hold <= 0.0:
                    hold_ready_any = True
                    break
                age = max(0.0, now_hold_ts - ts_val)
                if age >= effective_hold:
                    hold_ready_any = True
                    break
                remaining_values.append(max(0.0, effective_hold - age))
            if hold_ready_any:
                break
        if hold_candidate_seen and not hold_ready_any:
            wait_s = min(remaining_values) if remaining_values else 0.0
            indicator_label = ", ".join(indicator_tokens)
            _safe_log(
                self,
                f"{symbol}@{interval_norm or 'default'} flip blocked by hold guard for {indicator_label} "
                f"{opp} leg (wait ~{wait_s:.1f}s).",
            )
            return False
    indicator_label = ", ".join(indicator_tokens)
    indicator_primary = indicator_tokens[0] if indicator_tokens else None
    protect_other_legs = False
    try:
        protect_other_legs = self._symbol_side_has_other_positions(
            symbol,
            interval_norm,
            indicator_primary,
            opp,
        )
    except Exception as exc:
        _pause_for_close_uncertainty(
            self,
            f"{symbol}@{interval_norm or 'default'} other-position ownership lookup failed: {exc}",
            reconciliation_required=False,
        )
        return False
    if protect_other_legs:
        _safe_log(
            self,
            f"{symbol}@{interval_norm or 'default'} flip blocked: other {opp} legs "
            f"are active on this symbol ({indicator_label}).",
        )
        return False
    residual_qty = 0.0
    for indicator_hint in indicator_tokens:
        try:
            qty_val = self._indicator_live_qty_total(
                symbol,
                interval_norm,
                indicator_hint,
                opp,
                interval_aliases=interval_tokens,
                strict_interval=True,
                use_exchange_fallback=True,
            )
        except Exception as exc:
            _pause_for_close_uncertainty(
                self,
                f"{symbol}@{interval_norm or 'default'} indicator live quantity lookup failed: {exc}",
                reconciliation_required=False,
            )
            return False
        residual_qty = max(residual_qty, qty_val)
    residual_tol = max(1e-9, residual_qty * 1e-6)
    if residual_qty <= residual_tol:
        try:
            for indicator_hint in indicator_tokens:
                self._purge_indicator_tracking(symbol, interval_norm, indicator_hint, opp)
        except Exception as exc:
            _pause_for_close_uncertainty(
                self,
                f"{symbol}@{interval_norm or 'default'} flat indicator tracking purge failed: {exc}",
                reconciliation_required=True,
            )
            return False
        state["indicator_target_cleared"] = True
        if state.get("qty_goal") is None:
            return True
        return _goal_met(state)
    qty_hint = residual_qty
    qty_goal = state.get("qty_goal")
    if qty_goal is not None and float(qty_goal) > 0.0:
        qty_hint = min(qty_hint, float(qty_goal))
    if qty_hint > 0.0:
        close_side = "SELL" if opp.upper() in {"BUY", "LONG"} else "BUY"
        try:
            success, close_res = self._execute_close_with_fallback(
                symbol,
                close_side,
                qty_hint,
                indicator_position_side,
            )
        except Exception as exc:
            _pause_for_close_uncertainty(
                self,
                f"{symbol}@{interval_norm or 'default'} residual {indicator_label} close failed: {exc}",
                reconciliation_required=False,
            )
            return False
        if success:
            state["closed_any"] = True
            _reduce_goal(state, qty_hint)
            cleanup_ok = True
            try:
                self._mark_guard_closed(symbol, interval_norm, opp)
                self._purge_indicator_tracking(symbol, interval_norm, indicator_primary or indicator_tokens[0], opp)
            except Exception as exc:
                cleanup_ok = False
                _pause_for_close_uncertainty(
                    self,
                    f"Confirmed {symbol}@{interval_norm or 'default'} residual close cleanup failed: {exc}",
                    reconciliation_required=True,
                )
            refreshed = _refresh_positions_snapshot(self, symbol, str(state["interval"]))
            if refreshed is None:
                return False
            state["positions"] = refreshed
            state["indicator_target_cleared"] = cleanup_ok
            if not cleanup_ok:
                return False
            if _goal_met(state):
                return True
        else:
            _safe_log(
                self,
                f"{symbol}@{interval_norm or 'default'} flip blocked: residual {indicator_label} {opp} leg "
                f"could not be closed ({close_res}).",
            )
            return False
    else:
        _safe_log(
            self,
            f"{symbol}@{interval_norm or 'default'} flip skipped: no {indicator_label} {opp} leg to close.",
        )
        state["indicator_target_cleared"] = True
        if state.get("qty_goal") is None:
            return True
        return _goal_met(state)
    return None
