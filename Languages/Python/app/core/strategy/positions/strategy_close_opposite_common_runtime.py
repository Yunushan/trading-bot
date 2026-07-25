from __future__ import annotations

import math
import time

from .close_execution import _pause_for_close_uncertainty, _safe_log


def _finite_state_float(value: object, *, default: float) -> float:
    try:
        number = float(value)
    except (TypeError, ValueError, OverflowError):
        return default
    return number if math.isfinite(number) else default


def _refresh_positions_snapshot(self, symbol: str, interval: str) -> list[dict] | None:
    try:
        positions = self.binance.list_open_futures_positions(max_age=0.0, force_refresh=True)
        if not isinstance(positions, (list, tuple)):
            raise RuntimeError("futures position snapshot unavailable")
        return list(positions)
    except Exception as refresh_exc:
        _pause_for_close_uncertainty(
            self,
            f"{symbol}@{interval} close-opposite refresh failed: {refresh_exc}",
            reconciliation_required=False,
        )
        return None


def _warn_oneway_overlap(
    self,
    warn_key: tuple[str, str, str],
    symbol: str,
    interval_norm: str,
    indicator_tokens: tuple[str, ...] | list[str],
    opp: str,
) -> None:
    warned = getattr(self, "_oneway_overlap_warned", set())
    if warn_key in warned:
        return
    warned.add(warn_key)
    self._oneway_overlap_warned = warned
    indicator_label = ", ".join(indicator_tokens) or opp
    _safe_log(
        self,
        f"{symbol}@{interval_norm or 'default'} {indicator_label} blocked: "
        "Binance Futures account is in one-way mode. Enable hedge (dual-side) mode to run "
        "opposite signals or disable 'allow opposite positions'.",
    )


def _reduce_goal(state: dict[str, object], delta: float) -> None:
    qty_goal = state.get("qty_goal")
    if qty_goal is None:
        return
    goal_value = _finite_state_float(qty_goal, default=0.0)
    delta_value = _finite_state_float(delta, default=0.0)
    state["qty_goal"] = max(0.0, goal_value - max(0.0, delta_value))


def _goal_met(state: dict[str, object]) -> bool:
    qty_goal = state.get("qty_goal")
    qty_tol = max(0.0, _finite_state_float(state.get("qty_tol"), default=0.0))
    goal_value = _finite_state_float(qty_goal, default=float("inf"))
    return qty_goal is not None and goal_value <= qty_tol


def _has_opposite_live(pos_iterable, symbol: str, opp: str) -> bool:
    tol = 1e-9
    for pos in pos_iterable:
        if str(pos.get("symbol") or "").upper() != symbol:
            continue
        pos_side = str(pos.get("positionSide") or pos.get("positionside") or "BOTH").upper()
        amt_val = float(pos.get("positionAmt") or 0.0)
        if opp == "BUY":
            if (pos_side == "LONG" and amt_val > tol) or (pos_side in {"BOTH", ""} and amt_val > tol):
                return True
        else:
            if (pos_side == "SHORT" and amt_val < -tol) or (pos_side in {"BOTH", ""} and amt_val < -tol):
                return True
    return False


def _finalize_close_cleanup(self, symbol: str, opp: str, qty_tol: float, closed_any: bool) -> None:
    if closed_any:
        opposite_flat_verified = False
        try:
            for _ in range(6):
                positions_refresh = self.binance.list_open_futures_positions(max_age=0.0, force_refresh=True)
                if not isinstance(positions_refresh, (list, tuple)):
                    raise RuntimeError("futures position snapshot unavailable during close cleanup")
                still_opposite = False
                for pos in positions_refresh:
                    if str(pos.get("symbol") or "").upper() != symbol:
                        continue
                    amt_chk = _finite_state_float(pos.get("positionAmt"), default=float("nan"))
                    if not math.isfinite(amt_chk):
                        raise RuntimeError("non-finite position amount during close cleanup")
                    if (opp == "SELL" and amt_chk < 0) or (opp == "BUY" and amt_chk > 0):
                        still_opposite = True
                        break
                if not still_opposite:
                    opposite_flat_verified = True
                    break
                time.sleep(0.15)
        except Exception as exc:
            _pause_for_close_uncertainty(
                self,
                f"{symbol} close-opposite cleanup snapshot failed: {exc}",
                reconciliation_required=True,
            )
            return
        if not opposite_flat_verified:
            _pause_for_close_uncertainty(
                self,
                f"{symbol} close-opposite cleanup retained ledger because exposure is still open",
                reconciliation_required=True,
            )
            return
        for key in list(self._leg_ledger.keys()):
            if key[0] == symbol and key[2] == opp:
                try:
                    self._remove_leg_entry(key, None)
                    self._guard_mark_leg_closed(key)
                except Exception as exc:
                    _pause_for_close_uncertainty(
                        self,
                        f"{symbol} close-opposite ledger cleanup failed: {exc}",
                        reconciliation_required=True,
                    )
                    return
    try:
        positions_latest = self.binance.list_open_futures_positions(max_age=0.0, force_refresh=True)
        if not isinstance(positions_latest, (list, tuple)):
            raise RuntimeError("latest futures position snapshot unavailable")
        live_qty_latest = 0.0
        for pos in positions_latest:
            if str(pos.get("symbol") or "").upper() != symbol:
                continue
            amount = _finite_state_float(pos.get("positionAmt"), default=float("nan"))
            if not math.isfinite(amount):
                raise RuntimeError("non-finite latest position amount")
            live_qty_latest = max(live_qty_latest, abs(amount))
        if live_qty_latest <= qty_tol:
            for key in list(self._leg_ledger.keys()):
                if key[0] != symbol:
                    continue
                try:
                    self._remove_leg_entry(key, None)
                    self._guard_mark_leg_closed(key)
                except Exception as exc:
                    _pause_for_close_uncertainty(
                        self,
                        f"{symbol} final ledger cleanup failed: {exc}",
                        reconciliation_required=True,
                    )
                    return
    except Exception as exc:
        _pause_for_close_uncertainty(
            self,
            f"{symbol} final close-opposite snapshot failed: {exc}",
            reconciliation_required=True,
        )
