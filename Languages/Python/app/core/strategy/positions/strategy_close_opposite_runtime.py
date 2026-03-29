from __future__ import annotations

from collections.abc import Iterable

from .strategy_close_opposite_common_runtime import (
    _finalize_close_cleanup,
    _goal_met,
    _has_opposite_live,
    _reduce_goal,
    _refresh_positions_snapshot,
    _warn_oneway_overlap,
)
from .strategy_close_opposite_exchange_runtime import _close_symbol_level_positions
from .strategy_close_opposite_indicator_runtime import (
    _close_indicator_scope,
    _indicator_scope_is_already_flat,
    _resolve_indicator_residuals,
)
from .strategy_close_opposite_ledger_runtime import _close_interval_side_entries


def _close_opposite_position(
    self,
    symbol: str,
    interval: str,
    next_side: str,
    trigger_signature: tuple[str, ...] | None = None,
    indicator_key: Iterable[str] | str | None = None,
    target_qty: float | None = None,
) -> bool:
    """Ensure no conflicting exposure remains before opening a new leg."""
    interval_norm = str(interval or "").strip()
    interval_tokens = self._tokenize_interval_label(interval_norm)
    interval_norm_lower = interval_norm.lower()
    interval_has_filter = interval_tokens != {"-"}
    indicator_tokens = self._normalize_indicator_token_list(indicator_key)
    if not indicator_tokens:
        indicator_tokens = self._normalize_indicator_token_list(
            self._indicator_token_from_signature(trigger_signature)
        )
    signature_hint_tokens = self._normalize_signature_tokens_no_slots(trigger_signature)
    allow_opposite_requested = self._strategy_coerce_bool(self.config.get("allow_opposite_positions"), True)
    interval_norm_guard = None
    if allow_opposite_requested:
        if indicator_tokens and not signature_hint_tokens:
            signature_hint_tokens = tuple(indicator_tokens)
        if interval_tokens:
            interval_norm_guard = tuple(sorted(interval_tokens))

    try:
        positions = self.binance.list_open_futures_positions(max_age=0.0, force_refresh=True) or []
    except Exception as e:
        self.log(f"{symbol}@{interval} read positions failed: {e}")
        return False

    desired = (next_side or "").upper()
    if desired not in ("BUY", "SELL"):
        return True
    try:
        dual = bool(self.binance.get_futures_dual_side())
    except Exception:
        dual = False

    opp = "SELL" if desired == "BUY" else "BUY"
    warn_key = (str(symbol or "").upper(), interval_norm_lower or "default", opp)
    warn_oneway_needed = bool(indicator_tokens and allow_opposite_requested and not dual)
    strict_flip_guard = self._strategy_coerce_bool(self.config.get("strict_indicator_flip_enforcement"), True)

    if dual and not indicator_tokens and not signature_hint_tokens:
        try:
            self.log(
                f"{symbol}@{interval_norm or 'default'} close-opposite skipped (hedge scope missing)."
            )
        except Exception:
            pass
        return True

    if allow_opposite_requested:
        if not indicator_tokens or not signature_hint_tokens:
            try:
                self.log(
                    f"{symbol}@{interval_norm or 'default'} close-opposite skipped (hedge isolation, missing indicator/signature)."
                )
            except Exception:
                pass
            return True
    if strict_flip_guard and indicator_tokens and not signature_hint_tokens:
        try:
            self.log(
                f"{symbol}@{interval_norm or 'default'} close-opposite skipped: missing opposite signature for "
                f"{', '.join(indicator_tokens)}."
            )
        except Exception:
            pass
        return True

    if allow_opposite_requested and (not indicator_tokens or not signature_hint_tokens or not interval_norm):
        try:
            self.log(
                f"{symbol}@{interval_norm or 'default'} close-opposite skipped: "
                f"hedge stacking enabled and no indicator scope available."
            )
        except Exception:
            pass
        return True
    if allow_opposite_requested and indicator_tokens:
        if not interval_tokens or interval_norm_guard is None or not signature_hint_tokens:
            try:
                self.log(
                    f"{symbol}@{interval_norm or 'default'} close-opposite skipped: "
                    f"hedge isolation guard (missing interval/signature guard)."
                )
            except Exception:
                pass
            return True
    if allow_opposite_requested and interval_norm_guard:
        other_iv = self._tokenize_interval_label(interval_norm)
        if set(interval_norm_guard) != other_iv:
            try:
                self.log(
                    f"{symbol}@{interval_norm or 'default'} close-opposite blocked: "
                    f"interval mismatch (guard {interval_norm_guard}, got {sorted(other_iv)})."
                )
            except Exception:
                pass
            return True

    try:
        qty_goal = float(target_qty) if target_qty is not None else None
    except Exception:
        qty_goal = None

    state: dict[str, object] = {
        "symbol": str(symbol or "").upper(),
        "interval": str(interval or ""),
        "interval_norm": interval_norm,
        "interval_tokens": interval_tokens,
        "interval_has_filter": interval_has_filter,
        "interval_norm_guard": interval_norm_guard,
        "indicator_tokens": tuple(indicator_tokens),
        "signature_hint_tokens": signature_hint_tokens,
        "allow_opposite_requested": allow_opposite_requested,
        "positions": positions,
        "desired": desired,
        "opp": opp,
        "dual": dual,
        "qty_goal": qty_goal,
        "qty_tol": 1e-9,
        "closed_any": False,
        "indicator_target_cleared": False,
    }

    if indicator_tokens and _indicator_scope_is_already_flat(self, state):
        return True
    if _goal_met(state):
        return True

    indicator_position_side = None
    if dual:
        indicator_position_side = "LONG" if opp == "BUY" else "SHORT"

    indicator_result = _close_indicator_scope(self, state, indicator_position_side)
    if indicator_result is not None:
        return indicator_result

    if warn_oneway_needed and not allow_opposite_requested:
        try:
            if _has_opposite_live(state["positions"], state["symbol"], opp):
                _warn_oneway_overlap(self, warn_key, state["symbol"], interval_norm, indicator_tokens, opp)
                return False
        except Exception:
            _warn_oneway_overlap(self, warn_key, state["symbol"], interval_norm, indicator_tokens, opp)
            return False

    ledger_closed = 0
    ledger_failed = False
    ledger_qty_closed = 0.0
    if indicator_tokens:
        for indicator_hint in indicator_tokens:
            closed, failed, qty = _close_interval_side_entries(
                self,
                symbol=state["symbol"],
                interval_norm=interval_norm,
                interval_tokens=interval_tokens,
                interval_has_filter=interval_has_filter,
                interval_norm_guard=interval_norm_guard,
                opp=opp,
                dual=dual,
                indicator_filter=indicator_hint,
                signature_filter=signature_hint_tokens,
                qty_limit=state.get("qty_goal"),
            )
            ledger_closed += closed
            ledger_qty_closed += qty
            if failed:
                ledger_failed = True
                break
    else:
        ledger_closed, ledger_failed, ledger_qty_closed = _close_interval_side_entries(
            self,
            symbol=state["symbol"],
            interval_norm=interval_norm,
            interval_tokens=interval_tokens,
            interval_has_filter=interval_has_filter,
            interval_norm_guard=interval_norm_guard,
            opp=opp,
            dual=dual,
            indicator_filter=None,
            signature_filter=signature_hint_tokens,
            qty_limit=state.get("qty_goal"),
        )
    if ledger_failed:
        try:
            self.log(
                f"{state['symbol']}@{interval_norm or 'default'} flip aborted: failed to close existing {opp} ledger entries."
            )
        except Exception:
            pass
        return False
    if ledger_closed:
        state["closed_any"] = True
        _reduce_goal(state, ledger_qty_closed)
        refreshed = _refresh_positions_snapshot(self, state["symbol"], state["interval"])
        if refreshed is None:
            return False
        state["positions"] = refreshed
        if _goal_met(state):
            return True
    if dual:
        if state.get("qty_goal") is not None:
            if _goal_met(state):
                return True
        elif indicator_tokens and state["indicator_target_cleared"]:
            return True
        elif not _has_opposite_live(state["positions"], state["symbol"], opp):
            return True
    elif _goal_met(state):
        return True

    residual_result = _resolve_indicator_residuals(self, state, indicator_position_side)
    if residual_result is not None:
        return residual_result

    if indicator_tokens:
        return True if state.get("qty_goal") is None else _goal_met(state)

    if not _close_symbol_level_positions(self, state):
        return False
    _finalize_close_cleanup(self, state["symbol"], opp, float(state["qty_tol"]), bool(state["closed_any"]))
    return True
