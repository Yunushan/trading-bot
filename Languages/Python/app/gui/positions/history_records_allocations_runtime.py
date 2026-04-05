from __future__ import annotations

import copy

from .record_build_helpers import _allocation_sort_key


def _allocation_identity(entry: dict) -> tuple[str, ...] | None:
    identity_fields = (
        "trade_id",
        "client_order_id",
        "order_id",
        "slot_id",
        "context_key",
        "open_time",
        "close_time",
    )
    tokens = tuple(
        str(entry.get(field_name) or "").strip()
        for field_name in identity_fields
    )
    if any(tokens):
        return tokens
    return None


def _collect_allocations(rec: dict) -> list[dict]:
    allocs = rec.get("allocations") or []
    if isinstance(allocs, dict):
        allocs = list(allocs.values())
    if not isinstance(allocs, list):
        return []
    out: list[dict] = []
    for payload in allocs:
        if not isinstance(payload, dict):
            continue
        entry = copy.deepcopy(payload)
        interval = entry.get("interval")
        if interval is None and entry.get("interval_display"):
            interval = entry.get("interval_display")
        entry["interval"] = interval
        triggers_any = entry.get("trigger_indicators")
        if isinstance(triggers_any, dict):
            merged = []
            for value in triggers_any.values():
                if isinstance(value, (list, tuple, set)):
                    merged.extend([str(v).strip() for v in value if str(v).strip()])
                elif isinstance(value, str) and value.strip():
                    merged.append(value.strip())
            entry["trigger_indicators"] = merged or None
        out.append(entry)
    unique: list[dict] = []
    seen: dict[tuple, dict] = {}
    for entry in out:
        indicators_tuple = tuple(
            sorted(
                str(v).strip().lower()
                for v in (entry.get("trigger_indicators") or [])
                if str(v).strip()
            )
        )
        key = (
            str(entry.get("ledger_id") or ""),
            str(entry.get("interval") or "").strip().lower(),
            indicators_tuple,
            _allocation_identity(entry),
        )
        existing = seen.get(key)
        if existing:
            try:
                existing["margin_usdt"] = max(
                    float(existing.get("margin_usdt") or 0.0),
                    float(entry.get("margin_usdt") or 0.0),
                )
                existing["qty"] = max(
                    float(existing.get("qty") or 0.0),
                    float(entry.get("qty") or 0.0),
                )
                existing["notional"] = max(
                    float(existing.get("notional") or 0.0),
                    float(entry.get("notional") or 0.0),
                )
            except Exception:
                pass
            continue
        if indicators_tuple:
            entry["trigger_indicators"] = list(indicators_tuple)
        seen[key] = entry
        unique.append(entry)
    unique.sort(key=_allocation_sort_key)
    return unique
