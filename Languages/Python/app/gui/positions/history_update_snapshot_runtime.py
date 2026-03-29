from __future__ import annotations

import copy

from .history_update_allocation_runtime import update_closed_allocations


def build_closed_position_snapshot(
    self,
    key: tuple[str, str],
    rec: dict,
    close_time_map,
    *,
    resolve_trigger_indicators_safe,
    lookup_force_liquidation,
) -> dict:
    from datetime import datetime as _dt

    sym, side_key = key
    snap = copy.deepcopy(rec)
    data_prev = dict(rec.get("data") or {})
    close_status = "Closed"
    qty_reported = None
    margin_reported = None
    pnl_reported = None
    roi_reported = None
    close_price_reported = None
    entry_price_reported = None
    leverage_reported = None
    close_fmt = None
    close_raw = close_time_map.pop(key, None) if isinstance(close_time_map, dict) else None
    if close_raw:
        dt_obj = self._parse_any_datetime(close_raw)
        if dt_obj:
            close_fmt = self._format_display_time(dt_obj)
    if close_fmt is None:
        close_fmt = self._format_display_time(_dt.now().astimezone())
    if "stop_loss_enabled" not in snap:
        snap["stop_loss_enabled"] = bool(rec.get("stop_loss_enabled"))
    try:
        alloc_entries = copy.deepcopy(getattr(self, "_entry_allocations", {}).get(key, [])) or []
    except Exception:
        alloc_entries = []
    entry_price_val = 0.0
    margin_prev = float(data_prev.get("margin_usdt") or 0.0)
    size_prev = float(data_prev.get("size_usdt") or 0.0)
    leverage_prev = data_prev.get("leverage")
    if isinstance(leverage_prev, (int, float)) and leverage_prev > 0:
        leverage_reported = int(float(leverage_prev))
    else:
        leverage_reported = None
    if alloc_entries:
        num = 0.0
        den = 0.0
        for entry in alloc_entries:
            if not isinstance(entry, dict):
                continue
            try:
                qty_val = abs(float(entry.get("qty") or 0.0))
                price_val = float(entry.get("entry_price") or data_prev.get("entry_price") or 0.0)
            except Exception:
                qty_val = 0.0
                price_val = 0.0
            if qty_val > 0 and price_val > 0:
                num += price_val * qty_val
                den += qty_val
            try:
                margin_prev = max(margin_prev, float(entry.get("margin_usdt") or 0.0))
            except Exception:
                pass
            try:
                size_prev = max(
                    size_prev,
                    float(
                        entry.get("notional")
                        or entry.get("size_usdt")
                        or size_prev
                        or 0.0
                    ),
                )
            except Exception:
                pass
        if den > 0:
            entry_price_val = num / den
    if entry_price_val <= 0:
        try:
            entry_price_val = float(data_prev.get("entry_price") or 0.0)
        except Exception:
            entry_price_val = 0.0
    update_hint = None
    try:
        update_hint = int(float(data_prev.get("update_time") or 0))
    except Exception:
        update_hint = None
    liquidation_meta = None
    if side_key in ("L", "S"):
        liquidation_meta = lookup_force_liquidation(self, sym, side_key, update_hint)
    if liquidation_meta:
        close_status = "Liquidated"
        snap["close_reason"] = "Liquidation"
        liquidation_time = liquidation_meta.get("time")
        if liquidation_time:
            try:
                close_fmt = self._format_display_time(
                    _dt.fromtimestamp(int(liquidation_time) / 1000.0).astimezone()
                )
            except Exception:
                pass
        close_price_reported = float(liquidation_meta.get("close_price") or 0.0)
        qty_reported = float(liquidation_meta.get("qty") or 0.0)
        if entry_price_val > 0:
            entry_price_reported = entry_price_val
        side_mult = 1.0 if side_key == "L" else -1.0
        if entry_price_reported and qty_reported:
            pnl_reported = (
                (close_price_reported - entry_price_reported)
                * qty_reported
                * side_mult
            )
        if margin_prev <= 0.0 and size_prev > 0.0 and leverage_prev:
            try:
                lev_val = float(leverage_prev)
                if lev_val > 0:
                    margin_prev = size_prev / lev_val
            except Exception:
                pass
        if margin_prev > 0.0:
            margin_reported = margin_prev
        if pnl_reported is not None and margin_reported:
            try:
                roi_reported = (pnl_reported / margin_reported) * 100.0
            except Exception:
                roi_reported = None
    snap["status"] = close_status
    snap["close_time"] = close_fmt
    snap_data = snap.setdefault("data", {})
    if not snap_data and data_prev:
        snap_data.update(data_prev)
    if qty_reported is None:
        try:
            qty_prev = float(data_prev.get("qty") or 0.0)
            if abs(qty_prev) > 0.0:
                qty_reported = abs(qty_prev)
        except Exception:
            qty_reported = None
    if margin_reported is None:
        try:
            margin_val_prev = float(data_prev.get("margin_usdt") or 0.0)
            if margin_val_prev > 0.0:
                margin_reported = margin_val_prev
        except Exception:
            margin_reported = None
    if pnl_reported is None:
        try:
            pnl_prev = float(data_prev.get("pnl_value") or 0.0)
            pnl_reported = pnl_prev
        except Exception:
            pnl_reported = None
    if roi_reported is None:
        try:
            roi_prev = float(data_prev.get("roi_percent") or 0.0)
            roi_reported = roi_prev if roi_prev != 0.0 else None
        except Exception:
            roi_reported = None
    if close_price_reported is None:
        try:
            close_price_prev = float(data_prev.get("close_price") or 0.0)
            if close_price_prev > 0.0:
                close_price_reported = close_price_prev
        except Exception:
            close_price_reported = None
    if entry_price_reported is None and entry_price_val > 0:
        entry_price_reported = entry_price_val
    if leverage_reported is None and leverage_prev:
        try:
            lev_int = int(float(leverage_prev))
            if lev_int > 0:
                leverage_reported = lev_int
        except Exception:
            leverage_reported = None
    if qty_reported is not None and qty_reported > 0:
        snap_data["qty"] = qty_reported
    if margin_reported is not None and margin_reported > 0:
        snap_data["margin_usdt"] = margin_reported
    if pnl_reported is not None:
        snap_data["pnl_value"] = pnl_reported
        if margin_reported and margin_reported > 0:
            roi_calc = (
                roi_reported
                if roi_reported is not None
                else (pnl_reported / margin_reported) * 100.0
            )
            roi_reported = roi_calc
            snap_data["roi_percent"] = roi_calc
            snap_data["pnl_roi"] = f"{pnl_reported:+.2f} USDT ({roi_calc:+.2f}%)"
        else:
            snap_data["pnl_roi"] = f"{pnl_reported:+.2f} USDT"
    if roi_reported is not None and "roi_percent" not in snap_data:
        snap_data["roi_percent"] = roi_reported
    if close_price_reported is not None and close_price_reported > 0:
        snap_data["close_price"] = close_price_reported
    if entry_price_reported is not None and entry_price_reported > 0:
        snap_data.setdefault("entry_price", entry_price_reported)
    if leverage_reported:
        snap_data["leverage"] = leverage_reported

    alloc_entries = update_closed_allocations(
        rec,
        alloc_entries,
        close_status=close_status,
        close_fmt=close_fmt,
        qty_reported=qty_reported,
        margin_reported=margin_reported,
        pnl_reported=pnl_reported,
        close_price_reported=close_price_reported,
        entry_price_reported=entry_price_reported,
        leverage_reported=leverage_reported,
        resolve_trigger_indicators_safe=resolve_trigger_indicators_safe,
    )
    if alloc_entries:
        snap["allocations"] = alloc_entries

    return {
        "snap": snap,
        "sym": sym,
        "side_key": side_key,
        "close_fmt": close_fmt,
        "pnl_reported": pnl_reported,
        "margin_reported": margin_reported,
        "roi_reported": roi_reported,
    }
