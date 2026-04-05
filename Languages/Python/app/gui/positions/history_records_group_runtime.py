from __future__ import annotations

from datetime import datetime
from typing import cast

from ..runtime.window import runtime as main_window_runtime
from .record_build_helpers import _allocation_sort_key


def _qty_key(entry: dict) -> float:
    try:
        return abs(float((entry.get("data") or {}).get("qty") or 0.0))
    except Exception:
        return 0.0


def _record_size_sort_metric(entry: dict) -> float:
    data = entry.get("data") or {}
    try:
        return float(data.get("qty") or data.get("margin_usdt") or 0.0)
    except Exception:
        return 0.0


def _clean_interval_label(value: object) -> str:
    try:
        text = str(value or "").strip()
    except Exception:
        return ""
    return text if text and text not in {"-"} else ""


def _interval_sort_key(label: str) -> tuple[object, ...]:
    return cast(tuple[object, ...], main_window_runtime._mw_interval_sort_key(label))


def _record_interval_sort_key(entry: dict) -> tuple[object, ...]:
    data = entry.get("data") or {}
    label = _clean_interval_label(entry.get("entry_tf"))
    if not label:
        label = _clean_interval_label(data.get("interval_display")) or _clean_interval_label(data.get("interval"))
    return _interval_sort_key(label)


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
    allocations = entry.get("allocations") or []
    if isinstance(allocations, dict):
        allocations = list(allocations.values())

    tokens: list[str] = []
    for candidate in (
        entry.get("_aggregate_key"),
        data.get("_aggregate_key"),
        entry.get("close_event_id"),
        data.get("close_event_id"),
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

    if isinstance(allocations, list):
        for alloc in sorted(
            (payload for payload in allocations if isinstance(payload, dict)),
            key=_allocation_sort_key,
        ):
            tokens.append("|".join(_allocation_sort_key(alloc)))
    return tuple(tokens)


def _record_stable_sort_key(self, entry: dict) -> tuple[object, ...]:
    return (
        _record_interval_sort_key(entry),
        _record_open_time_sort_key(self, entry),
        _record_identity_key(entry),
    )


def _group_sort_key(group_key: tuple[str, str, str, tuple[str, ...]]) -> tuple[object, ...]:
    sym, side, interval_key, indicators = group_key
    return (
        sym,
        side,
        _interval_sort_key(str(interval_key or "")),
        indicators,
    )


def _close_time_key(self, entry: dict) -> datetime:
    data = entry.get("data") or {}
    close_val = data.get("close_time") or entry.get("close_time") or ""
    dt = None
    try:
        dt = self._parse_any_datetime(close_val)
    except Exception:
        dt = None
    if dt is None:
        try:
            dt = datetime.min.replace(tzinfo=datetime.now().astimezone().tzinfo)
        except Exception:
            dt = datetime.min
    return dt


def _aggregate_key(entry: dict) -> str:
    data = entry.get("data") or {}
    for candidate in (
        entry.get("_aggregate_key"),
        data.get("_aggregate_key"),
        entry.get("close_event_id"),
        data.get("close_event_id"),
        entry.get("trade_id"),
        data.get("trade_id"),
        entry.get("client_order_id"),
        data.get("client_order_id"),
        entry.get("order_id"),
        data.get("order_id"),
        entry.get("ledger_id"),
        data.get("ledger_id"),
    ):
        text = str(candidate or "").strip()
        if text:
            return text
    return ""


def _merge_interval_labels(primary: dict, candidate: dict) -> None:
    labels: list[str] = []
    for rec in (primary, candidate):
        if not isinstance(rec, dict):
            continue
        value = rec.get("entry_tf")
        if isinstance(value, str) and value.strip():
            labels.extend([part.strip() for part in value.split(",") if part.strip()])
        data = rec.get("data") or {}
        if isinstance(data, dict):
            value = data.get("interval_display")
            if isinstance(value, str) and value.strip():
                labels.extend([part.strip() for part in value.split(",") if part.strip()])
    merged_labels = sorted(
        dict.fromkeys(label for label in labels if label),
        key=_interval_sort_key,
    )
    merged = ", ".join(merged_labels)
    if merged:
        primary["entry_tf"] = merged
        data = dict(primary.get("data") or {})
        data["interval_display"] = merged
        primary["data"] = data


def _close_key(entry: dict) -> str:
    data = entry.get("data") or {}
    aggregate = _aggregate_key(entry)
    close_event_id = str(entry.get("close_event_id") or data.get("close_event_id") or "").strip()
    ledger = str(entry.get("ledger_id") or data.get("ledger_id") or "").strip()
    close_time = entry.get("close_time") or data.get("close_time") or ""
    symbol_key = str(entry.get("symbol") or data.get("symbol") or "").strip().upper()
    side_key = str(entry.get("side_key") or data.get("side_key") or "").strip().upper()
    try:
        qty_key = f"{float(data.get('qty') or 0.0):.8f}"
    except Exception:
        qty_key = "0.0"
    if aggregate:
        return aggregate
    if close_event_id:
        return close_event_id
    if ledger:
        return ledger
    return f"{symbol_key}|{side_key}|{close_time}|{qty_key}"


def group_history_records(self, raw_records: list[dict], closed_record_states: set[str]) -> list[dict]:
    grouped: dict[tuple[str, str, str, tuple[str, ...]], dict[str, list[dict]]] = {}
    dedupe_tracker: dict[tuple[str, str, str, tuple[str, ...]], set[tuple]] = {}
    for entry in raw_records:
        try:
            symbol_key = str(entry.get("symbol") or "").strip().upper()
            side_key = str(entry.get("side_key") or "").strip().upper()
            interval_key = str(entry.get("entry_tf") or "").strip().lower()
            indicators_tuple = tuple(
                sorted(
                    str(ind or "").strip().lower()
                    for ind in (entry.get("indicators") or [])
                    if str(ind or "").strip()
                )
            )
            status_key = str(entry.get("status") or "").strip().lower() or "active"
            group_key = (symbol_key, side_key, interval_key, indicators_tuple)
            bucket = grouped.setdefault(group_key, {})
            status_bucket = bucket.setdefault(status_key, [])
            aggregate_key = _aggregate_key(entry)

            data = entry.get("data") or {}
            dedupe_key = (
                status_key,
                str(entry.get("open_time") or data.get("open_time") or "").strip(),
                str(entry.get("close_time") or data.get("close_time") or "").strip(),
                round(float(data.get("qty") or 0.0), 10),
                str(aggregate_key or "").strip(),
            )
            seen = dedupe_tracker.setdefault(group_key, set())
            if dedupe_key in seen:
                continue
            seen.add(dedupe_key)

            if aggregate_key and any(existing.get("_aggregate_key") == aggregate_key for existing in status_bucket):
                continue
            status_bucket.append(entry)
        except Exception:
            continue

    records = []
    for group_key in sorted(grouped, key=_group_sort_key):
        _sym, _side, _interval, _indicators = group_key
        status_map = grouped.get(group_key)
        if not isinstance(status_map, dict):
            continue
        active_entries = list(status_map.get("active") or status_map.get("open") or [])
        if active_entries:
            active_entries.sort(key=lambda entry: _record_stable_sort_key(self, entry))
            named_active: list[dict] = []
            unnamed_active: list[dict] = []
            seen_active_keys: set[str] = set()
            for entry in active_entries:
                active_key = _aggregate_key(entry)
                if active_key:
                    if active_key in seen_active_keys:
                        continue
                    seen_active_keys.add(active_key)
                    named_active.append(entry)
                else:
                    unnamed_active.append(entry)
            if named_active:
                records.extend(named_active)
            if unnamed_active and not named_active:
                records.append(max(unnamed_active, key=_qty_key))
            elif unnamed_active:
                records.append(max(unnamed_active, key=_qty_key))
        closed_entries = list(status_map.get("closed") or [])
        closed_entries.sort(key=lambda entry: _close_time_key(self, entry), reverse=True)
        records.extend(closed_entries)
        for status_name in sorted(status_map):
            if status_name in {"active", "open", "closed"}:
                continue
            entries = list(status_map.get(status_name) or [])
            entries.sort(key=lambda entry: _record_stable_sort_key(self, entry))
            records.extend(entries)

    indexed_records = list(enumerate(records))
    indexed_records.sort(
        key=lambda pair: (
            str(pair[1].get("symbol") or ""),
            str(pair[1].get("side_key") or ""),
            _record_interval_sort_key(pair[1]),
            -_record_size_sort_metric(pair[1]),
            pair[0],
        )
    )
    records = [entry for _, entry in indexed_records]

    deduped: list[dict] = []
    seen_closed: dict[str, dict] = {}
    for entry in records:
        data = entry.get("data") or {}
        status_flag = str(entry.get("status") or data.get("status") or "").strip().lower()
        is_closed = status_flag in closed_record_states
        if is_closed:
            key = _close_key(entry)
            existing = seen_closed.get(key)
            if existing:
                _merge_interval_labels(existing, entry)
                continue
            seen_closed[key] = entry
        deduped.append(entry)
    return deduped
