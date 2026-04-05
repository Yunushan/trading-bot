from __future__ import annotations

import copy
from datetime import datetime

from ..runtime.window import runtime as main_window_runtime
from .record_build_helpers import _allocation_sort_key


def _clean_interval_label(value: object) -> str:
    try:
        text = str(value or "").strip()
    except Exception:
        return ""
    return text if text and text not in {"-"} else ""


def _record_primary_metric(entry: dict) -> float:
    data = entry.get("data") or {}
    try:
        return float(data.get("qty") or data.get("margin_usdt") or 0.0)
    except Exception:
        return 0.0


def _record_open_time_sort_key(self, entry: dict) -> tuple[float, str]:
    data = entry.get("data") or {}
    raw_value = entry.get("open_time") or data.get("open_time") or ""
    try:
        dt_obj = self._parse_any_datetime(raw_value)
    except Exception:
        dt_obj = None
    if dt_obj is None:
        return (float("inf"), str(raw_value or ""))
    try:
        return (float(dt_obj.timestamp()), str(raw_value or ""))
    except Exception:
        return (float("inf"), str(raw_value or ""))


def _record_identity_key(entry: dict) -> tuple[str, ...]:
    data = entry.get("data") or {}
    tokens: list[str] = []
    for candidate in (
        entry.get("_aggregate_key"),
        data.get("_aggregate_key"),
        entry.get("trade_id"),
        data.get("trade_id"),
        entry.get("client_order_id"),
        data.get("client_order_id"),
        entry.get("order_id"),
        data.get("order_id"),
        entry.get("event_uid"),
        data.get("event_uid"),
        entry.get("context_key"),
        data.get("context_key"),
        entry.get("slot_id"),
        data.get("slot_id"),
        entry.get("ledger_id"),
        data.get("ledger_id"),
        entry.get("open_time"),
        data.get("open_time"),
    ):
        text = str(candidate or "").strip()
        if text:
            tokens.append(text)
    allocations = entry.get("allocations") or []
    if isinstance(allocations, dict):
        allocations = list(allocations.values())
    if isinstance(allocations, list):
        for alloc in sorted(
            (payload for payload in allocations if isinstance(payload, dict)),
            key=_allocation_sort_key,
        ):
            tokens.append("|".join(_allocation_sort_key(alloc)))
    return tuple(tokens)


def _record_stable_sort_key(self, entry: dict) -> tuple[object, ...]:
    data = entry.get("data") or {}
    interval_label = _clean_interval_label(entry.get("entry_tf"))
    if not interval_label:
        interval_label = _clean_interval_label(data.get("interval_display")) or _clean_interval_label(
            data.get("interval")
        )
    return (
        main_window_runtime._mw_interval_sort_key(interval_label),
        _record_open_time_sort_key(self, entry),
        _record_identity_key(entry),
    )


def _canonical_interval_labels(labels: list[str]) -> list[str]:
    ordered = [
        label
        for label in dict.fromkeys(label for label in labels if label)
    ]
    return sorted(ordered, key=main_window_runtime._mw_interval_sort_key)


def _summary_row_sort_key(self, item: dict) -> tuple[object, ...]:
    interval_label = _clean_interval_label(item.get("entry_tf"))
    if interval_label and "," in interval_label:
        interval_label = interval_label.split(",")[0].strip()
    if not interval_label:
        interval_label = _clean_interval_label((item.get("data") or {}).get("interval_display"))
    return (
        str(item.get("symbol") or "").strip().upper(),
        str(item.get("side_key") or "").strip().upper(),
        main_window_runtime._mw_interval_sort_key(interval_label),
        str(item.get("status") or ""),
        _record_open_time_sort_key(self, item),
        _record_identity_key(item),
    )


def _mw_positions_records_cumulative(self, entries: list[dict], closed_entries: list[dict] | None = None) -> list[dict]:
    grouped: dict[tuple[str, str], list[dict]] = {}
    for rec in entries or []:
        if not isinstance(rec, dict):
            continue
        sym = str(rec.get("symbol") or "").strip().upper()
        if not sym:
            continue
        side_key = str(rec.get("side_key") or "").strip().upper()
        if not side_key:
            continue
        grouped.setdefault((sym, side_key), []).append(rec)
    aggregated: list[dict] = []
    for (_sym, _side_key), bucket in grouped.items():
        if not bucket:
            continue
        bucket_sorted = sorted(bucket, key=lambda entry: _record_stable_sort_key(self, entry))
        primary = max(bucket_sorted, key=_record_primary_metric)
        clone = copy.deepcopy(primary)
        clone_allocations = clone.get("allocations") or []
        if isinstance(clone_allocations, dict):
            clone_allocations = list(clone_allocations.values())
        if isinstance(clone_allocations, list):
            clone["allocations"] = [
                copy.deepcopy(entry)
                for entry in sorted(
                    (payload for payload in clone_allocations if isinstance(payload, dict)),
                    key=_allocation_sort_key,
                )
            ]
        open_time_candidates: list[datetime] = []

        intervals: list[str] = []
        total_qty = 0.0
        total_margin = 0.0
        total_pnl = 0.0
        leverage_values: set[int] = set()

        def _collect_leverage(value: object) -> None:
            try:
                if value is None or value == "":
                    return
                if not isinstance(value, (int, float, str, bytes, bytearray)):
                    return
                lev_val = int(float(value))
                if lev_val > 0:
                    leverage_values.add(lev_val)
            except Exception:
                return

        for entry in bucket_sorted:
            label = _clean_interval_label(entry.get("entry_tf")) or _clean_interval_label(
                (entry.get("data") or {}).get("interval_display")
            )
            if label and label not in intervals:
                intervals.append(label)
            data = entry.get("data") or {}
            _collect_leverage(data.get("leverage"))
            _collect_leverage(entry.get("leverage"))
            raw_entry = data.get("raw_position")
            if not isinstance(raw_entry, dict):
                raw_entry = entry.get("raw_position") if isinstance(entry.get("raw_position"), dict) else None
            if isinstance(raw_entry, dict):
                _collect_leverage(raw_entry.get("leverage"))
            allocations = entry.get("allocations") or []
            if isinstance(allocations, dict):
                allocations = list(allocations.values())
            if isinstance(allocations, list):
                for alloc in allocations:
                    if not isinstance(alloc, dict):
                        continue
                    _collect_leverage(alloc.get("leverage"))
            ts_val = entry.get("open_time") or data.get("open_time")
            dt_obj = self._parse_any_datetime(ts_val) if hasattr(self, "_parse_any_datetime") else None
            if dt_obj:
                open_time_candidates.append(dt_obj)
            try:
                total_qty += max(0.0, float(data.get("qty") or 0.0))
            except Exception:
                pass
            try:
                total_margin += max(0.0, float(data.get("margin_usdt") or 0.0))
            except Exception:
                pass
            try:
                total_pnl += float(data.get("pnl_value") or 0.0)
            except Exception:
                pass
        intervals = _canonical_interval_labels(intervals)
        if intervals:
            clone["entry_tf"] = ", ".join(intervals)
        else:
            allocations = clone.get("allocations") or []
            if isinstance(allocations, list):
                for alloc in allocations:
                    if not isinstance(alloc, dict):
                        continue
                    label = _clean_interval_label(alloc.get("interval_display")) or _clean_interval_label(
                        alloc.get("interval")
                    )
                    if label and label not in intervals:
                        intervals.append(label)
                intervals = _canonical_interval_labels(intervals)
                if intervals:
                    clone["entry_tf"] = ", ".join(intervals)
        agg_data = dict(clone.get("data") or {})
        if intervals:
            agg_data["interval_display"] = intervals[0]
            agg_data["interval"] = intervals[0]
        if total_qty > 0.0:
            agg_data["qty"] = total_qty
        if total_margin > 0.0:
            agg_data["margin_usdt"] = total_margin
        if total_pnl or total_pnl == 0.0:
            agg_data["pnl_value"] = total_pnl
        if total_margin > 0.0:
            try:
                agg_data["roi_percent"] = (total_pnl / total_margin) * 100.0
            except Exception:
                pass
        leverage_final = None
        if leverage_values:
            leverage_final = max(leverage_values)
        try:
            existing_lev = agg_data.get("leverage")
            if existing_lev is not None:
                existing_lev = int(float(existing_lev))
            if existing_lev and existing_lev > 0:
                leverage_final = existing_lev
        except Exception:
            pass
        if leverage_final:
            agg_data["leverage"] = leverage_final
            clone["leverage"] = leverage_final
        if open_time_candidates:
            try:
                earliest = min(open_time_candidates)
                open_fmt = (
                    self._format_display_time(earliest)
                    if hasattr(self, "_format_display_time")
                    else earliest.isoformat()
                )
                clone["open_time"] = open_fmt
                agg_data["open_time"] = open_fmt
            except Exception:
                pass
        clone["data"] = agg_data
        clone["_aggregated_entries"] = bucket_sorted
        aggregated.append(clone)
    closed_entries = list(closed_entries or [])

    def _close_dt(entry: dict):
        try:
            dt_val = entry.get("close_time") or (entry.get("data") or {}).get("close_time")
            return self._parse_any_datetime(dt_val)
        except Exception:
            return None

    closed_entries.sort(key=lambda e: (_close_dt(e) or datetime.min), reverse=True)
    aggregated.extend(closed_entries)
    aggregated.sort(key=lambda item: _summary_row_sort_key(self, item))
    return aggregated


__all__ = ["_mw_positions_records_cumulative"]
