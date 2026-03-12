from __future__ import annotations

import copy
from datetime import datetime


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
        primary = max(
            bucket,
            key=lambda r: float((r.get("data") or {}).get("qty") or (r.get("data") or {}).get("margin_usdt") or 0.0),
        )
        clone = copy.deepcopy(primary)
        open_time_candidates: list[datetime] = []

        def _clean_interval_label(value: object) -> str:
            try:
                text = str(value or "").strip()
            except Exception:
                return ""
            return text if text and text not in {"-"} else ""

        intervals: list[str] = []
        total_qty = 0.0
        total_margin = 0.0
        total_pnl = 0.0
        leverage_values: set[int] = set()

        def _collect_leverage(value: object) -> None:
            try:
                if value is None or value == "":
                    return
                lev_val = int(float(value))
                if lev_val > 0:
                    leverage_values.add(lev_val)
            except Exception:
                return

        for entry in bucket:
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
            for ts_key in ("open_time",):
                ts_val = entry.get(ts_key) or data.get(ts_key)
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
        if intervals:
            clone["entry_tf"] = ", ".join(intervals)
            clone.setdefault("data", {}).setdefault("interval_display", intervals[0])
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
                if intervals:
                    clone["entry_tf"] = ", ".join(intervals)
                    clone.setdefault("data", {}).setdefault("interval_display", intervals[0])
        agg_data = dict(clone.get("data") or {})
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
                agg_data.setdefault("open_time", open_fmt)
            except Exception:
                pass
        clone["data"] = agg_data
        clone["_aggregated_entries"] = bucket
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
    aggregated.sort(
        key=lambda item: (item.get("symbol"), item.get("side_key"), item.get("entry_tf") or "", item.get("status") or "")
    )
    return aggregated


def _update_positions_pnl_summary(self, total_pnl: float | None, total_margin: float | None) -> None:
    label = getattr(self, "positions_pnl_label", None)
    if label is None:
        return
    if total_pnl is None:
        label.setText("Total PNL: --")
        return
    text = f"Total PNL: {total_pnl:+.2f} USDT"
    if total_margin is not None and total_margin > 0.0:
        try:
            roi = (total_pnl / total_margin) * 100.0
        except Exception:
            roi = 0.0
        text += f" ({roi:+.2f}%)"
    label.setText(text)


def bind_main_window_positions(main_window_cls) -> None:
    main_window_cls._update_positions_pnl_summary = _update_positions_pnl_summary
