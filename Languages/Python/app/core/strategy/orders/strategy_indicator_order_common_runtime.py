from __future__ import annotations

import math

from .strategy_order_error_logging import pause_for_order_uncertainty


def _indicator_exchange_qty(self, symbol: str, side_label: str, desired_ps: str | None) -> float:
    try:
        raw_quantity = self._current_futures_position_qty(symbol, side_label, desired_ps)
    except Exception as exc:
        pause_for_order_uncertainty(
            self,
            f"{symbol} exchange position quantity lookup failed: {exc}",
            reconciliation_required=False,
        )
        raise RuntimeError("exchange position quantity lookup failed") from exc
    if raw_quantity is None:
        pause_for_order_uncertainty(
            self,
            f"{symbol} exchange position quantity is unavailable",
            reconciliation_required=False,
        )
        raise RuntimeError("exchange position quantity is unavailable")
    try:
        quantity = float(raw_quantity)
    except (TypeError, ValueError, OverflowError) as exc:
        pause_for_order_uncertainty(
            self,
            f"{symbol} exchange position quantity is invalid: {exc}",
            reconciliation_required=False,
        )
        raise RuntimeError("exchange position quantity is invalid") from exc
    if not math.isfinite(quantity) or quantity < 0.0:
        pause_for_order_uncertainty(
            self,
            f"{symbol} exchange position quantity must be finite and nonnegative",
            reconciliation_required=False,
        )
        raise RuntimeError("exchange position quantity must be finite and nonnegative")
    return quantity


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
        except Exception as exc:
            pause_for_order_uncertainty(
                self,
                f"{symbol}@{interval_current or 'default'} stale indicator tracking purge failed: {exc}",
                reconciliation_required=True,
            )
            return tracked_qty
        return 0.0
    return tracked_qty


__all__ = ["_indicator_exchange_qty", "_purge_indicator_side_if_exchange_flat"]
