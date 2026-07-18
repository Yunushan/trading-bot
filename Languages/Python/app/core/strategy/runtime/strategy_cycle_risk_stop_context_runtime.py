from __future__ import annotations

import math


def _finite_positive(value: object) -> float:
    try:
        number = float(value)
    except (TypeError, ValueError, OverflowError):
        return 0.0
    return number if math.isfinite(number) and number > 0.0 else 0.0


def _reconciled_close_qty(result: object, requested_qty: float) -> float:
    if not math.isfinite(requested_qty) or requested_qty <= 0.0:
        return 0.0
    if isinstance(result, dict):
        for field in ("sent_qty", "executed_qty", "executedQty", "origQty"):
            try:
                quantity = float(result.get(field) or 0.0)
            except (TypeError, ValueError, OverflowError):
                continue
            if math.isfinite(quantity) and quantity > 0.0:
                return min(requested_qty, quantity)
    return requested_qty


def build_futures_stop_state(self, *, cw, df):
    last_price = None
    try:
        live_price = _finite_positive(self.binance.get_last_price(cw["symbol"]))
        if live_price > 0.0:
            last_price = live_price
    except Exception:
        last_price = None
    if last_price is None and not df.empty:
        try:
            close_price = _finite_positive(df["close"].iloc[-1])
            last_price = close_price if close_price > 0.0 else None
        except Exception:
            last_price = None

    state = {
        "last_price": last_price,
        "positions_cache": None,
        "positions_cache_ok": False,
    }

    def load_positions_cache():
        if state["positions_cache"] is None:
            try:
                state["positions_cache"] = self.binance.list_open_futures_positions() or []
                state["positions_cache_ok"] = True
            except Exception:
                state["positions_cache"] = []
                state["positions_cache_ok"] = False
        return state["positions_cache"] or []

    state["load_positions_cache"] = load_positions_cache
    return state


def purge_flat_futures_cycle_legs(self, *, cw, dual_side: bool, state) -> None:
    try:
        load_positions_cache = state.get("load_positions_cache")
        if callable(load_positions_cache):
            load_positions_cache()
        if state.get("positions_cache_ok"):
            self._purge_flat_futures_legs(
                cw["symbol"],
                state.get("positions_cache") or [],
                dual_side=dual_side,
            )
    except Exception:
        pass


def ensure_futures_leg_entry_price(
    self,
    *,
    cw,
    leg_key,
    expect_long: bool,
    dual_side: bool,
    state,
):
    leg = self._leg_ledger.get(leg_key, {}) or {}
    qty_val = _finite_positive(leg.get("qty"))
    entry_px = _finite_positive(leg.get("entry_price"))
    matched_pos = None
    load_positions_cache = state.get("load_positions_cache")
    cache = load_positions_cache() if callable(load_positions_cache) else []
    for pos in cache:
        try:
            if str(pos.get("symbol") or "").upper() != cw["symbol"]:
                continue
            amt = float(pos.get("positionAmt") or 0.0)
            if not math.isfinite(amt):
                continue
            if dual_side:
                pos_side = str(pos.get("positionSide") or "").upper()
                if expect_long and pos_side != "LONG":
                    continue
                if (not expect_long) and pos_side != "SHORT":
                    continue
                qty_candidate = abs(amt)
            else:
                if expect_long and amt <= 0.0:
                    continue
                if (not expect_long) and amt >= 0.0:
                    continue
                qty_candidate = abs(amt)
            if qty_candidate <= 0.0:
                continue
            matched_pos = pos
            if entry_px <= 0.0:
                try:
                    entry_px = _finite_positive(pos.get("entryPrice"))
                except Exception:
                    pass
            break
        except Exception:
            continue
    if matched_pos and entry_px > 0.0:
        leg["entry_price"] = entry_px
        self._leg_ledger[leg_key] = leg
    return leg, qty_val, entry_px, matched_pos


__all__ = [
    "build_futures_stop_state",
    "ensure_futures_leg_entry_price",
    "purge_flat_futures_cycle_legs",
]
