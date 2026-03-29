from __future__ import annotations

import time


def _refresh_positions_snapshot(self, symbol: str, interval: str) -> list[dict] | None:
    try:
        return self.binance.list_open_futures_positions(max_age=0.0, force_refresh=True) or []
    except Exception as refresh_exc:
        try:
            self.log(f"{symbol}@{interval} close-opposite refresh failed: {refresh_exc}")
        except Exception:
            pass
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
    try:
        self.log(
            f"{symbol}@{interval_norm or 'default'} {indicator_label} blocked: Binance Futures account is in one-way mode. "
            "Enable hedge (dual-side) mode to run opposite signals or disable 'allow opposite positions'."
        )
    except Exception:
        pass


def _reduce_goal(state: dict[str, object], delta: float) -> None:
    qty_goal = state.get("qty_goal")
    if qty_goal is None:
        return
    state["qty_goal"] = max(0.0, float(qty_goal) - max(0.0, delta))


def _goal_met(state: dict[str, object]) -> bool:
    qty_goal = state.get("qty_goal")
    qty_tol = float(state.get("qty_tol") or 0.0)
    return qty_goal is not None and float(qty_goal) <= qty_tol


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
        try:
            import time as _t

            for _ in range(6):
                positions_refresh = self.binance.list_open_futures_positions(max_age=0.0, force_refresh=True) or []
                still_opposite = False
                for pos in positions_refresh:
                    if str(pos.get("symbol") or "").upper() != symbol:
                        continue
                    amt_chk = float(pos.get("positionAmt") or 0.0)
                    if (opp == "SELL" and amt_chk < 0) or (opp == "BUY" and amt_chk > 0):
                        still_opposite = True
                        break
                if not still_opposite:
                    break
                _t.sleep(0.15)
        except Exception:
            pass
        for key in list(self._leg_ledger.keys()):
            if key[0] == symbol and key[2] == opp:
                self._remove_leg_entry(key, None)
                self._guard_mark_leg_closed(key)
    try:
        positions_latest = self.binance.list_open_futures_positions(max_age=0.0, force_refresh=True) or []
        live_qty_latest = 0.0
        for pos in positions_latest:
            if str(pos.get("symbol") or "").upper() != symbol:
                continue
            try:
                live_qty_latest = max(live_qty_latest, abs(float(pos.get("positionAmt") or 0.0)))
            except Exception:
                continue
        if live_qty_latest <= qty_tol:
            for key in list(self._leg_ledger.keys()):
                if key[0] != symbol:
                    continue
                self._remove_leg_entry(key, None)
                self._guard_mark_leg_closed(key)
    except Exception:
        pass
