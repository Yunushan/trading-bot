from __future__ import annotations

import copy

from .history_records_allocations_runtime import _collect_allocations
from .history_records_meta_runtime import _normalize_interval
from .history_records_trade_data_runtime import _compute_trade_data


def _emit_entries(
    self,
    raw_records: list[dict],
    base_rec: dict,
    sym: str,
    side_key: str,
    meta_items: list[dict | None],
    *,
    normalize_indicator_values,
    derive_margin_snapshot,
) -> None:
    allocations = _collect_allocations(base_rec)
    base_data = dict(base_rec.get("data") or {})
    status_text = str(base_rec.get("status") or "Active")
    stop_loss_flag = bool(base_rec.get("stop_loss_enabled"))
    default_open = base_rec.get("open_time") or "-"
    default_close = base_rec.get("close_time") or "-"
    meta_items = meta_items or [None]

    def _interval_from_meta(meta: dict | None, fallback: str | None = None) -> str:
        if isinstance(meta, dict):
            label = meta.get("interval") or meta.get("interval_display")
            if label:
                return str(label)
        if fallback:
            return str(fallback)
        return "-"

    def _build_entry(allocation: dict | None, interval_hint: str | None, meta: dict | None = None) -> None:
        entry = copy.deepcopy(base_rec)
        interval_label = interval_hint or entry.get("entry_tf") or "-"
        entry["entry_tf"] = interval_label or "-"
        if isinstance(allocation, dict):
            try:
                entry["allocations"] = [copy.deepcopy(allocation)]
            except Exception:
                entry["allocations"] = [dict(allocation)]
        else:
            entry["allocations"] = []
        alloc_status = str((allocation or {}).get("status") or status_text)
        entry["status"] = alloc_status
        if isinstance(meta, dict) and meta.get("stop_loss_enabled") is not None:
            entry["stop_loss_enabled"] = bool(meta.get("stop_loss_enabled"))
        else:
            entry["stop_loss_enabled"] = bool(
                (allocation or {}).get("stop_loss_enabled", stop_loss_flag)
            )
        alloc_data = _compute_trade_data(
            base_data,
            allocation,
            side_key,
            alloc_status,
            derive_margin_snapshot=derive_margin_snapshot,
        )
        entry["data"] = alloc_data
        entry["leverage"] = alloc_data.get("leverage")
        entry["liquidation_price"] = alloc_data.get("liquidation_price")
        indicators = allocation.get("trigger_indicators") if isinstance(allocation, dict) else None
        if isinstance(indicators, (list, tuple, set)):
            entry["indicators"] = list(
                dict.fromkeys(str(t).strip() for t in indicators if str(t).strip())
            )
        elif isinstance(meta, dict):
            meta_inds = meta.get("indicators")
            if meta_inds:
                entry["indicators"] = list(meta_inds)
        trig_inds = alloc_data.get("trigger_indicators")
        if trig_inds:
            entry["indicators"] = list(dict.fromkeys(trig_inds))
        open_hint = None
        close_hint = None
        if isinstance(allocation, dict):
            open_hint = allocation.get("open_time")
            close_hint = allocation.get("close_time")
        entry["open_time"] = open_hint or default_open
        entry["close_time"] = close_hint or default_close
        entry["stop_loss_enabled"] = bool(entry.get("stop_loss_enabled"))
        normalized_inds = normalize_indicator_values(
            entry.get("indicators") or alloc_data.get("trigger_indicators")
        )
        if normalized_inds:
            entry["indicators"] = normalized_inds
            alloc_data["trigger_indicators"] = normalized_inds
        else:
            entry.pop("indicators", None)
            alloc_data.pop("trigger_indicators", None)

        aggregate_key = None
        if isinstance(allocation, dict):
            aggregate_key = (
                allocation.get("trade_id")
                or allocation.get("client_order_id")
                or allocation.get("order_id")
                or allocation.get("ledger_id")
            )
        if not aggregate_key:
            aggregate_key = (
                entry.get("trade_id")
                or entry.get("client_order_id")
                or entry.get("order_id")
                or entry.get("ledger_id")
                or base_rec.get("ledger_id")
            )
        if not aggregate_key:
            aggregate_key = f"{sym}|{side_key}|{interval_label}|{entry.get('open_time')}"

        indicator_source = (
            alloc_data.get("trigger_indicators")
            or entry.get("indicators")
            or base_data.get("trigger_indicators")
        )
        indicator_values = normalize_indicator_values(indicator_source)
        if indicator_values:
            for indicator_name in indicator_values:
                clone = copy.deepcopy(entry)
                clone_indicators = [indicator_name]
                clone["indicators"] = clone_indicators
                clone_data = dict(clone.get("data") or {})
                clone_data["trigger_indicators"] = clone_indicators
                clone["data"] = clone_data
                clone_allocs: list[dict] = []
                for alloc_payload in clone.get("allocations") or []:
                    if not isinstance(alloc_payload, dict):
                        continue
                    alloc_clone = dict(alloc_payload)
                    alloc_clone["trigger_indicators"] = clone_indicators
                    clone_allocs.append(alloc_clone)
                clone["allocations"] = clone_allocs
                clone["_aggregate_key"] = f"{aggregate_key}|{indicator_name.lower()}"
                clone["_aggregate_is_primary"] = True
                raw_records.append(clone)
            return
        entry["indicators"] = []
        entry_data = dict(entry.get("data") or {})
        entry_data["trigger_indicators"] = []
        entry["data"] = entry_data
        entry["_aggregate_key"] = aggregate_key
        entry["_aggregate_is_primary"] = True
        raw_records.append(entry)

    if allocations:
        for alloc in allocations:
            interval_label = alloc.get("interval_display") or alloc.get("interval")
            norm_iv = _normalize_interval(self, interval_label)
            matching_meta = None
            if norm_iv is not None:
                for meta in meta_items:
                    if isinstance(meta, dict) and _normalize_interval(self, meta.get("interval")) == norm_iv:
                        matching_meta = meta
                        break
            if matching_meta is None:
                for meta in meta_items:
                    if meta is None:
                        matching_meta = None
                        break
            _build_entry(alloc, interval_label or norm_iv, matching_meta)
    else:
        fallback_intervals: list[str] = []
        for meta in meta_items:
            if isinstance(meta, dict) and meta.get("interval"):
                fallback_intervals.append(_interval_from_meta(meta))
        if not fallback_intervals:
            entry_tf = base_rec.get("entry_tf")
            if isinstance(entry_tf, str) and entry_tf.strip():
                fallback_intervals = [
                    part.strip()
                    for part in entry_tf.split(",")
                    if part.strip()
                ]
        if not fallback_intervals:
            fallback_intervals = ["-"]
        for idx, interval_label in enumerate(fallback_intervals):
            meta = None
            if idx < len(meta_items) and isinstance(meta_items[idx], dict):
                meta = meta_items[idx]
            _build_entry(None, interval_label, meta)


def build_raw_history_records(
    self,
    open_records: dict,
    closed_records: list,
    meta_map: dict[tuple[str, str], list[dict]],
    *,
    normalize_indicator_values,
    derive_margin_snapshot,
) -> list[dict]:
    raw_records: list[dict] = []
    for (sym, side_key), rec in open_records.items():
        meta_items = meta_map.get((sym, side_key)) or [None]
        _emit_entries(
            self,
            raw_records,
            rec,
            sym,
            side_key,
            meta_items,
            normalize_indicator_values=normalize_indicator_values,
            derive_margin_snapshot=derive_margin_snapshot,
        )

    for rec in closed_records:
        sym = str(rec.get("symbol") or "").strip().upper()
        side_key = str(rec.get("side_key") or "").strip().upper()
        entry_tf = rec.get("entry_tf")
        meta_items: list[dict | None] = []
        if isinstance(entry_tf, str) and entry_tf.strip():
            parts = [part.strip() for part in entry_tf.split(",") if part.strip()]
            if parts:
                meta_items = [{"interval": part} for part in parts]
        if not meta_items:
            meta_items = [None]
        _emit_entries(
            self,
            raw_records,
            rec,
            sym,
            side_key,
            meta_items,
            normalize_indicator_values=normalize_indicator_values,
            derive_margin_snapshot=derive_margin_snapshot,
        )
    return raw_records
