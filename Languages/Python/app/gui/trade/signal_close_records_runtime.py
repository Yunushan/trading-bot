from __future__ import annotations

import copy
from datetime import datetime

from . import signal_common_runtime


def _record_closed_position(
    self,
    order_info: dict,
    ctx: dict,
    *,
    closed_snapshots: list[dict],
    max_closed_history: int,
) -> bool:
    close_time_val = order_info.get("time")
    dt_obj = self._parse_any_datetime(close_time_val)
    if dt_obj is None:
        dt_obj = datetime.now().astimezone()
    close_time_fmt = self._format_display_time(dt_obj)

    alloc_entries_snapshot = list(closed_snapshots or [])
    for entry_snap in alloc_entries_snapshot:
        if not entry_snap.get("close_time"):
            entry_snap["close_time"] = close_time_fmt

    ledger_id = order_info.get("ledger_id")
    qty_reported = signal_common_runtime._safe_float(order_info.get("qty") or order_info.get("executed_qty"))
    if qty_reported is not None:
        qty_reported = abs(qty_reported)

    close_price_reported = signal_common_runtime._safe_float(
        order_info.get("close_price")
        or order_info.get("avg_price")
        or order_info.get("price")
        or order_info.get("mark_price")
    )
    entry_price_reported = signal_common_runtime._safe_float(order_info.get("entry_price"))
    pnl_reported = signal_common_runtime._safe_float(order_info.get("pnl_value"))
    margin_reported = signal_common_runtime._safe_float(order_info.get("margin_usdt"))
    roi_reported = signal_common_runtime._safe_float(order_info.get("roi_percent"))

    leverage_reported = None
    leverage_value = signal_common_runtime._safe_float(order_info.get("leverage"))
    if leverage_value is not None and leverage_value > 0:
        try:
            leverage_reported = int(round(leverage_value))
        except Exception:
            leverage_reported = None

    processed = getattr(self, "_processed_close_events", None)
    if processed is None:
        processed = set()
        self._processed_close_events = processed

    unique_key = order_info.get("event_id")
    if not unique_key:
        identifier = ledger_id or ctx["sym_upper"] or ""
        qty_token = f"{qty_reported:.8f}" if qty_reported is not None else "0"
        unique_key = f"{identifier}|{close_time_fmt}|{qty_token}|{ctx['side_key']}"
    if unique_key in processed:
        return False
    processed.add(unique_key)

    open_records = getattr(self, "_open_position_records", {}) or {}
    base_record = copy.deepcopy(open_records.get((ctx["sym_upper"], ctx["side_key"])))
    if not base_record:
        base_record = {
            "symbol": ctx["sym_upper"],
            "side_key": ctx["side_key"],
            "entry_tf": "-",
            "open_time": "-",
            "close_time": close_time_fmt,
            "status": "Closed",
            "data": {},
            "indicators": [],
            "stop_loss_enabled": False,
        }
    else:
        base_record["status"] = "Closed"
        base_record["close_time"] = close_time_fmt
    if ledger_id:
        base_record["ledger_id"] = ledger_id

    base_data_snap = dict(base_record.get("data") or {})
    if alloc_entries_snapshot:
        qty_total = 0.0
        margin_total = 0.0
        pnl_total = 0.0
        pnl_has_value = False
        notional_total = 0.0
        trigger_list = []
        try:
            base_qty_curr = float(base_data_snap.get("qty") or 0.0)
        except Exception:
            base_qty_curr = 0.0
        try:
            base_margin_curr = float(base_data_snap.get("margin_usdt") or 0.0)
        except Exception:
            base_margin_curr = 0.0
        try:
            base_pnl_curr = float(base_data_snap.get("pnl_value") or 0.0)
        except Exception:
            base_pnl_curr = 0.0
        try:
            base_notional_curr = float(base_data_snap.get("size_usdt") or 0.0)
        except Exception:
            base_notional_curr = 0.0
        alloc_count = len(alloc_entries_snapshot)

        for entry_snap in alloc_entries_snapshot:
            try:
                qty_val = abs(float(entry_snap.get("qty") or 0.0))
            except Exception:
                qty_val = 0.0
            qty_total += qty_val

            margin_val = entry_snap.get("margin_usdt")
            try:
                margin_missing = margin_val is None or float(margin_val or 0.0) == 0.0
            except Exception:
                margin_missing = margin_val is None
            if margin_missing and base_margin_curr > 0:
                share = (
                    (qty_val / base_qty_curr)
                    if base_qty_curr > 0
                    else (1.0 / alloc_count if alloc_count else 0.0)
                )
                entry_snap["margin_usdt"] = base_margin_curr * share if share else base_margin_curr
            try:
                margin_total += max(float(entry_snap.get("margin_usdt") or 0.0), 0.0)
            except Exception:
                pass

            pnl_val = entry_snap.get("pnl_value")
            if pnl_val is not None:
                try:
                    pnl_total += float(pnl_val)
                    pnl_has_value = True
                except Exception:
                    pass
            elif base_pnl_curr:
                share = (
                    (qty_val / base_qty_curr)
                    if base_qty_curr > 0
                    else (1.0 / alloc_count if alloc_count else 0.0)
                )
                approx_pnl = base_pnl_curr * share if share else base_pnl_curr
                entry_snap["pnl_value"] = approx_pnl
                pnl_total += approx_pnl
                pnl_has_value = True

            try:
                notional_total += max(float(entry_snap.get("notional") or 0.0), 0.0)
            except Exception:
                pass
            if entry_snap.get("notional") in (None, 0.0) and base_notional_curr > 0:
                share = (
                    (qty_val / base_qty_curr)
                    if base_qty_curr > 0
                    else (1.0 / alloc_count if alloc_count else 0.0)
                )
                entry_snap["notional"] = base_notional_curr * share if share else base_notional_curr

            trig = entry_snap.get("trigger_indicators")
            if isinstance(trig, (list, tuple, set)):
                trigger_list.extend([str(t).strip() for t in trig if str(t).strip()])
            if close_price_reported is not None and close_price_reported > 0:
                entry_snap["close_price"] = close_price_reported
            if entry_price_reported is not None and entry_price_reported > 0:
                entry_snap.setdefault("entry_price", entry_price_reported)
            if leverage_reported:
                entry_snap["leverage"] = leverage_reported

        if qty_reported is not None and qty_reported > 0:
            qty_total = qty_reported
        if margin_reported is not None and margin_reported > 0:
            margin_total = margin_reported
        if pnl_reported is not None:
            pnl_total = pnl_reported
            pnl_has_value = True
        if qty_total > 0:
            base_data_snap["qty"] = qty_total
        if margin_total > 0:
            base_data_snap["margin_usdt"] = margin_total
        if pnl_has_value:
            base_data_snap["pnl_value"] = pnl_total
        if notional_total > 0:
            base_data_snap["size_usdt"] = notional_total
        if margin_total > 0 and pnl_has_value:
            roi_percent = (pnl_total / margin_total) * 100.0 if margin_total else 0.0
            base_data_snap["roi_percent"] = roi_percent
            base_data_snap["pnl_roi"] = f"{pnl_total:+.2f} USDT ({roi_percent:+.2f}%)"
        if (
            pnl_reported is not None
            and roi_reported is not None
            and margin_reported is not None
            and margin_reported > 0
        ):
            base_data_snap["roi_percent"] = roi_reported
            base_data_snap["pnl_roi"] = f"{pnl_reported:+.2f} USDT ({roi_reported:+.2f}%)"
        if trigger_list:
            trigger_list = list(dict.fromkeys(trigger_list))
            base_record["indicators"] = trigger_list
            base_data_snap["trigger_indicators"] = trigger_list

    if qty_reported is not None and qty_reported > 0:
        base_data_snap["qty"] = qty_reported
    if margin_reported is not None and margin_reported > 0:
        base_data_snap["margin_usdt"] = margin_reported
    if pnl_reported is not None:
        base_data_snap["pnl_value"] = pnl_reported
        if margin_reported and margin_reported > 0:
            roi_val = roi_reported if roi_reported is not None else (pnl_reported / margin_reported) * 100.0
            base_data_snap["roi_percent"] = roi_val
            base_data_snap["pnl_roi"] = f"{pnl_reported:+.2f} USDT ({roi_val:+.2f}%)"
        else:
            base_data_snap["pnl_roi"] = f"{pnl_reported:+.2f} USDT"
    if close_price_reported is not None and close_price_reported > 0:
        base_data_snap["close_price"] = close_price_reported
    if entry_price_reported is not None and entry_price_reported > 0:
        base_data_snap.setdefault("entry_price", entry_price_reported)
    if leverage_reported:
        base_data_snap["leverage"] = leverage_reported

    base_record["data"] = base_data_snap
    base_record["allocations"] = alloc_entries_snapshot

    try:
        closed_records = getattr(self, "_closed_position_records", [])
        if ledger_id:
            replaced = False
            for idx, rec in enumerate(closed_records):
                if isinstance(rec, dict) and rec.get("ledger_id") == ledger_id:
                    closed_records[idx] = base_record
                    replaced = True
                    break
            if not replaced:
                closed_records.insert(0, base_record)
        else:
            closed_records.insert(0, base_record)
        self._closed_position_records = closed_records
    except Exception:
        pass

    try:
        registry = getattr(self, "_closed_trade_registry", None)
        if registry is None:
            registry = {}
            self._closed_trade_registry = registry
        registry_key = ledger_id or unique_key
        if registry_key:
            registry[registry_key] = {
                "pnl_value": signal_common_runtime._safe_float(base_data_snap.get("pnl_value")),
                "margin_usdt": signal_common_runtime._safe_float(base_data_snap.get("margin_usdt")),
                "roi_percent": signal_common_runtime._safe_float(base_data_snap.get("roi_percent")),
            }
            if len(registry) > max_closed_history:
                excess = len(registry) - max_closed_history
                if excess > 0:
                    for old_key in list(registry.keys())[:excess]:
                        registry.pop(old_key, None)
        try:
            self._update_global_pnl_display(*self._compute_global_pnl_totals())
        except Exception:
            pass
    except Exception:
        pass

    return True


__all__ = ["_record_closed_position"]
