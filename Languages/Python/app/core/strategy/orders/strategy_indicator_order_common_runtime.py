from __future__ import annotations


def _indicator_exchange_qty(self, symbol: str, side_label: str, desired_ps: str | None) -> float:
    try:
        return max(
            0.0,
            float(self._current_futures_position_qty(symbol, side_label, desired_ps) or 0.0),
        )
    except Exception:
        return 0.0


def _purge_indicator_side_if_exchange_flat(
    self,
    *,
    symbol: str,
    interval_current,
    indicator_key: str,
    side_label: str,
    desired_ps: str | None,
    tracked_qty: float,
) -> float:
    if tracked_qty <= 0.0:
        return tracked_qty
    exch_qty = _indicator_exchange_qty(self, symbol, side_label, desired_ps)
    tol_live = max(1e-9, exch_qty * 1e-6)
    if exch_qty <= tol_live:
        try:
            self._purge_indicator_tracking(symbol, interval_current, indicator_key, side_label)
        except Exception:
            pass
        return 0.0
    return tracked_qty


__all__ = ["_indicator_exchange_qty", "_purge_indicator_side_if_exchange_flat"]
