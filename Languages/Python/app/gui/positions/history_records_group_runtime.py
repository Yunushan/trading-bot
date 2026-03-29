from __future__ import annotations

from datetime import datetime


def _qty_key(entry: dict) -> float:
    try:
        return abs(float((entry.get("data") or {}).get("qty") or 0.0))
    except Exception:
        return 0.0


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
    merged = ", ".join(dict.fromkeys(labels))
    if merged:
        primary["entry_tf"] = merged
        data = dict(primary.get("data") or {})
        data["interval_display"] = merged
        primary["data"] = data


def _close_key(entry: dict) -> str:
    data = entry.get("data") or {}
    aggregate = str(entry.get("_aggregate_key") or data.get("_aggregate_key") or "").strip()
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
            aggregate_key = entry.get("_aggregate_key")

            data = entry.get("data") or {}
            dedupe_key = (
                status_key,
                str(entry.get("open_time") or data.get("open_time") or "").strip(),
                str(entry.get("close_time") or data.get("close_time") or "").strip(),
                round(float(data.get("qty") or 0.0), 10),
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
    for (_sym, _side, _interval, _indicators), status_map in grouped.items():
        if not isinstance(status_map, dict):
            continue
        active_entries = status_map.get("active") or status_map.get("open") or []
        if active_entries:
            chosen_active = max(active_entries, key=_qty_key)
            records.append(chosen_active)
        closed_entries = (status_map.get("closed") or [])[:]
        closed_entries.sort(key=lambda entry: _close_time_key(self, entry), reverse=True)
        records.extend(closed_entries)
        for status_name, entries in status_map.items():
            if status_name in {"active", "open", "closed"}:
                continue
            records.extend(entries or [])

    records.sort(
        key=lambda item: (
            str(item.get("symbol") or ""),
            str(item.get("side_key") or ""),
            str(item.get("entry_tf") or ""),
            -float(item.get("data", {}).get("qty") or item.get("data", {}).get("margin_usdt") or 0.0),
        )
    )

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
