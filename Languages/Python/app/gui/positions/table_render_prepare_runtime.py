from __future__ import annotations

import time

from . import table_render_state_runtime


def _resolve_display_records(self, open_records: dict, closed_records: list[dict], view_mode: str) -> list[dict]:
    if view_mode == "per_trade":
        records = self._positions_records_per_trade(open_records, closed_records)
    else:
        records = table_render_state_runtime._positions_records_cumulative(
            self,
            sorted(
                open_records.values(),
                key=lambda d: (d["symbol"], d.get("side_key"), d.get("entry_tf")),
            ),
            closed_records,
        )
    return [rec for rec in (records or []) if isinstance(rec, dict)]


def _resolve_account_is_futures(self):
    acct_type = str(getattr(self, "_positions_account_type", "") or "").upper()
    acct_is_futures = getattr(self, "_positions_account_is_futures", None)
    if acct_is_futures is None:
        acct_is_futures = "FUT" in acct_type
    return acct_is_futures


def _resolve_live_value_cache(self) -> dict:
    live_value_cache = getattr(self, "_live_indicator_cache", None)
    if not isinstance(live_value_cache, dict):
        live_value_cache = {}
        self._live_indicator_cache = live_value_cache
    return live_value_cache


def _cleanup_live_value_cache(self, live_value_cache: dict) -> None:
    now_ts = time.monotonic()
    ttl = float(getattr(self, "_live_indicator_cache_ttl", 8.0) or 8.0)
    cleanup_interval = max(ttl * 3.0, 30.0)
    last_cleanup = float(getattr(self, "_live_indicator_cache_last_cleanup", 0.0) or 0.0)
    if now_ts - last_cleanup < cleanup_interval:
        return
    cutoff = now_ts - max(ttl * 6.0, 60.0)
    stale_keys: list[tuple[str, str]] = []
    for key, entry in list(live_value_cache.items()):
        try:
            entry_ts = float(entry.get("df_ts") or entry.get("ts") or 0.0)
        except Exception:
            entry_ts = 0.0
        if entry_ts and entry_ts < cutoff:
            stale_keys.append(key)
    for key in stale_keys:
        live_value_cache.pop(key, None)
    self._live_indicator_cache_last_cleanup = now_ts


def _prepare_record_snapshot(
    self,
    rec: dict,
    *,
    view_mode: str,
    live_value_cache: dict,
) -> tuple:
    data = rec.get("data") or {}
    status_flag = str(rec.get("status") or data.get("status") or "").strip().lower()
    record_is_closed = status_flag in table_render_state_runtime._CLOSED_RECORD_STATES
    indicators_list = tuple(
        table_render_state_runtime._collect_record_indicator_keys(
            rec,
            include_inactive_allocs=record_is_closed,
            include_allocation_scope=view_mode != "per_trade",
        )
    )
    interval_hint = rec.get("entry_tf") or data.get("interval_display") or data.get("interval") or "-"
    indicator_value_entries, interval_map = table_render_state_runtime._collect_indicator_value_strings(
        rec,
        interval_hint,
    )
    rec["_indicator_value_entries"] = indicator_value_entries
    rec["_indicator_interval_map"] = interval_map
    sym_digest = str(rec.get("symbol") or data.get("symbol") or "").strip().upper()
    if record_is_closed:
        current_live_entries = list(rec.get("_current_indicator_values") or [])
    else:
        current_live_entries = table_render_state_runtime._collect_current_indicator_live_strings(
            self,
            sym_digest,
            indicators_list,
            live_value_cache,
            interval_map,
            interval_hint,
        )
    if view_mode == "per_trade":
        filtered_values = table_render_state_runtime._filter_indicator_entries(
            indicator_value_entries,
            interval_hint,
            include_non_matching=False,
        )
        if filtered_values:
            allowed = {
                table_render_state_runtime._indicator_entry_signature(entry)
                for entry in filtered_values
            }
            current_live_entries = [
                entry
                for entry in (current_live_entries or [])
                if table_render_state_runtime._indicator_entry_signature(entry) in allowed
            ]
    if current_live_entries:
        current_live_entries = table_render_state_runtime._dedupe_indicator_entries_normalized(
            current_live_entries
        )
    rec["_current_indicator_values"] = current_live_entries
    return (
        str(rec.get("symbol") or "").upper(),
        str(rec.get("side_key") or "").upper(),
        str(rec.get("entry_tf") or ""),
        indicators_list,
        tuple(indicator_value_entries or []),
        tuple((key, tuple(values)) for key, values in (interval_map or {}).items()),
        tuple(current_live_entries or []),
        float(data.get("qty") or 0.0),
        float(data.get("margin_usdt") or 0.0),
        float(data.get("pnl_value") or 0.0),
        str(rec.get("status") or ""),
    )


def prepare_positions_table_render(self) -> dict:
    open_records = getattr(self, "_open_position_records", {}) or {}
    closed_records = getattr(self, "_closed_position_records", []) or []
    view_mode = getattr(self, "_positions_view_mode", "cumulative")
    prev_snapshot = getattr(self, "_last_positions_table_snapshot", None)
    display_records = _resolve_display_records(self, open_records, closed_records, view_mode)
    acct_is_futures = _resolve_account_is_futures(self)
    live_value_cache = _resolve_live_value_cache(self)
    _cleanup_live_value_cache(self, live_value_cache)
    snapshot_digest = [
        _prepare_record_snapshot(
            self,
            rec,
            view_mode=view_mode,
            live_value_cache=live_value_cache,
        )
        for rec in display_records
    ]
    return {
        "acct_is_futures": acct_is_futures,
        "display_records": display_records,
        "live_value_cache": live_value_cache,
        "prev_snapshot": prev_snapshot,
        "snapshot_key": (view_mode, tuple(snapshot_digest)),
        "view_mode": view_mode,
    }
