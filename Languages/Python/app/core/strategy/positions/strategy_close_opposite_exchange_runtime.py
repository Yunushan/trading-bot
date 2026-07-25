from __future__ import annotations

from .close_execution import _pause_for_close_uncertainty, _safe_log
from .strategy_close_opposite_common_runtime import _goal_met, _reduce_goal


def _close_symbol_level_positions(self, state: dict[str, object]) -> bool:
    symbol = str(state["symbol"])
    interval = str(state["interval"])
    desired = str(state["desired"])
    dual = bool(state["dual"])
    qty_goal = state.get("qty_goal")

    for pos in state["positions"]:
        try:
            if str(pos.get("symbol") or "").upper() != symbol:
                continue
            amt = float(pos.get("positionAmt") or 0.0)
            position_side_flag = None
            if dual:
                pos_side = str(pos.get("positionSide") or pos.get("positionside") or "").upper()
                if pos_side in {"LONG", "SHORT"}:
                    position_side_flag = pos_side
                else:
                    position_side_flag = "LONG" if amt > 0 else "SHORT"
            if desired == "BUY" and amt < 0:
                qty = abs(amt)
                if qty_goal is not None:
                    if _goal_met(state):
                        break
                    qty = min(qty, float(state["qty_goal"]))
                success, res = self._execute_close_with_fallback(
                    symbol,
                    "BUY",
                    qty,
                    position_side_flag if dual else None,
                )
                if not success:
                    _safe_log(self, f"{symbol}@{interval} close-short failed: {res}")
                    return False
                try:
                    payload = self._build_close_event_payload(symbol, interval, "SELL", qty, res)
                    self._notify_interval_closed(symbol, interval, "SELL", **payload)
                    self._mark_guard_closed(symbol, interval, "SELL")
                    self._purge_indicator_tracking(symbol, interval, None, "SELL")
                except Exception as exc:
                    _pause_for_close_uncertainty(
                        self,
                        f"{symbol}@{interval} confirmed short close could not update local state: {exc}",
                        reconciliation_required=True,
                    )
                    return False
                state["closed_any"] = True
                _reduce_goal(state, qty)
                if _goal_met(state):
                    break
            elif desired == "SELL" and amt > 0:
                qty = abs(amt)
                if qty_goal is not None:
                    if _goal_met(state):
                        break
                    qty = min(qty, float(state["qty_goal"]))
                success, res = self._execute_close_with_fallback(
                    symbol,
                    "SELL",
                    qty,
                    position_side_flag if dual else None,
                )
                if not success:
                    _safe_log(self, f"{symbol}@{interval} close-long failed: {res}")
                    return False
                try:
                    payload = self._build_close_event_payload(symbol, interval, "BUY", qty, res)
                    self._notify_interval_closed(symbol, interval, "BUY", **payload)
                    self._mark_guard_closed(symbol, interval, "BUY")
                    self._purge_indicator_tracking(symbol, interval, None, "BUY")
                except Exception as exc:
                    _pause_for_close_uncertainty(
                        self,
                        f"{symbol}@{interval} confirmed long close could not update local state: {exc}",
                        reconciliation_required=True,
                    )
                    return False
                state["closed_any"] = True
                _reduce_goal(state, qty)
                if _goal_met(state):
                    break
        except Exception as exc:
            _pause_for_close_uncertainty(
                self,
                f"{symbol}@{interval} close-opposite execution failed: {exc}",
                reconciliation_required=True,
            )
            return False
    return True
