from __future__ import annotations

import copy
import time
from decimal import ROUND_DOWN, Decimal


def _get_cached_futures_positions(self, max_age: float) -> list | None:
    if max_age is None or max_age <= 0:
        return None
    with self._positions_cache_lock:
        data = self._positions_cache
        ts = self._positions_cache_ts
    if data is None:
        return None
    if (time.time() - ts) > max_age:
        return None
    return copy.deepcopy(data)


def _store_futures_positions_cache(self, entries: list | None) -> None:
    with self._positions_cache_lock:
        self._positions_cache = copy.deepcopy(entries) if entries is not None else None
        self._positions_cache_ts = time.time() if entries is not None else 0.0


def _invalidate_futures_positions_cache(self) -> None:
    with self._positions_cache_lock:
        self._positions_cache = None
        self._positions_cache_ts = 0.0
    self._invalidate_futures_account_cache()


def _format_quantity_for_order(value: float, step: float | None = None) -> str:
    try:
        if value is None:
            return "0"
        quant = Decimal(str(value))
        if step and float(step) > 0:
            step_dec = Decimal(str(step))
            quant = quant.quantize(step_dec, rounding=ROUND_DOWN)
        quant = quant.normalize()
        text_value = format(quant, "f")
        text_value = text_value.rstrip("0").rstrip(".") if "." in text_value else text_value
        return text_value if text_value else "0"
    except Exception:
        try:
            return f"{float(value):.8f}".rstrip("0").rstrip(".")
        except Exception:
            return "0"
