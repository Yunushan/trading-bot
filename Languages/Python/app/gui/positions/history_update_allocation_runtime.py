from __future__ import annotations


def _normalize_allocation_triggers(alloc_entries: list[dict], resolve_trigger_indicators_safe) -> None:
    for entry in alloc_entries:
        if not isinstance(entry, dict):
            continue
        normalized_triggers = resolve_trigger_indicators_safe(
            entry.get("trigger_indicators"),
            entry.get("trigger_desc"),
        )
        if normalized_triggers:
            entry["trigger_indicators"] = normalized_triggers
        elif entry.get("trigger_indicators"):
            entry.pop("trigger_indicators", None)


def update_closed_allocations(
    rec: dict,
    alloc_entries: list[dict],
    *,
    close_status: str,
    close_fmt: str,
    qty_reported,
    margin_reported,
    pnl_reported,
    close_price_reported,
    entry_price_reported,
    leverage_reported,
    resolve_trigger_indicators_safe,
) -> list[dict]:
    if not alloc_entries:
        return []

    _normalize_allocation_triggers(alloc_entries, resolve_trigger_indicators_safe)
    base_data = rec.get("data", {}) or {}
    base_qty = float(base_data.get("qty") or 0.0)
    base_margin = float(base_data.get("margin_usdt") or 0.0)
    base_pnl = float(base_data.get("pnl_value") or 0.0)
    base_size = float(base_data.get("size_usdt") or 0.0)
    total_qty = 0.0
    for entry in alloc_entries:
        try:
            total_qty += abs(float(entry.get("qty") or 0.0))
        except Exception:
            continue
    if total_qty <= 0 and base_qty > 0:
        total_qty = base_qty
    count_entries = len([entry for entry in alloc_entries if isinstance(entry, dict)])
    for entry in alloc_entries:
        if not isinstance(entry, dict):
            continue
        entry["status"] = close_status
        entry["close_time"] = close_fmt
        try:
            qty_val = abs(float(entry.get("qty") or 0.0))
        except Exception:
            qty_val = 0.0
        ratio = (
            (qty_val / total_qty)
            if total_qty > 0
            else (1.0 / count_entries if count_entries else 0.0)
        )
        if ratio <= 0 and count_entries:
            ratio = 1.0 / count_entries
        if float(entry.get("margin_usdt") or 0.0) <= 0 and base_margin > 0:
            entry["margin_usdt"] = base_margin * ratio
        if float(entry.get("notional") or 0.0) <= 0 and base_size > 0:
            entry["notional"] = base_size * ratio
        if entry.get("pnl_value") is None:
            if base_pnl and base_qty > 0 and qty_val > 0:
                entry["pnl_value"] = base_pnl * (qty_val / base_qty)
            elif base_pnl and ratio > 0:
                entry["pnl_value"] = base_pnl * ratio
            else:
                entry["pnl_value"] = base_pnl
    qty_dist_sum = 0.0
    try:
        qty_dist_sum = sum(
            abs(float(entry.get("qty") or 0.0))
            for entry in alloc_entries
            if isinstance(entry, dict)
        )
    except Exception:
        qty_dist_sum = 0.0
    if qty_dist_sum <= 0.0 and qty_reported is not None and qty_reported > 0:
        qty_dist_sum = qty_reported
    entries_count = len([entry for entry in alloc_entries if isinstance(entry, dict)])
    for entry in alloc_entries:
        if not isinstance(entry, dict):
            continue
        share = 0.0
        try:
            if qty_dist_sum and qty_dist_sum > 0:
                share = abs(float(entry.get("qty") or 0.0)) / qty_dist_sum
        except Exception:
            share = 0.0
        if share <= 0.0 and entries_count:
            share = 1.0 / entries_count
        if qty_reported is not None and qty_reported > 0 and share > 0:
            entry["qty"] = qty_reported * share
        if margin_reported is not None and margin_reported > 0 and share > 0:
            entry["margin_usdt"] = margin_reported * share
        if pnl_reported is not None and share > 0:
            entry["pnl_value"] = pnl_reported * share
        if close_price_reported is not None and close_price_reported > 0:
            entry["close_price"] = close_price_reported
        if entry_price_reported is not None and entry_price_reported > 0:
            entry.setdefault("entry_price", entry_price_reported)
        if leverage_reported:
            entry["leverage"] = leverage_reported
    return alloc_entries
