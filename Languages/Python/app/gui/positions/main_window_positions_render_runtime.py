from __future__ import annotations

import time

from PyQt6 import QtCore, QtWidgets

from ...binance_wrapper import normalize_margin_ratio

_CLOSED_RECORD_STATES: set[str] = set()
_NUMERIC_ITEM_CLS = QtWidgets.QTableWidgetItem
_COLLECT_CURRENT_INDICATOR_LIVE_STRINGS = None
_COLLECT_INDICATOR_VALUE_STRINGS = None
_COLLECT_RECORD_INDICATOR_KEYS = None
_COERCE_BOOL = None
_DEDUPE_INDICATOR_ENTRIES_NORMALIZED = None
_FILTER_INDICATOR_ENTRIES_FOR_INTERVAL = None
_FORMAT_INDICATOR_LIST = None
_INDICATOR_ENTRY_SIGNATURE = None
_INDICATOR_SHORT_LABEL = None
_NORMALIZE_INDICATOR_VALUES = None
_POSITIONS_RECORDS_CUMULATIVE = None
POS_TRIGGERED_VALUE_COLUMN = 10
POS_CURRENT_VALUE_COLUMN = 11
POS_STOP_LOSS_COLUMN = 15
POS_STATUS_COLUMN = 16
POS_CLOSE_COLUMN = 17


def configure_main_window_positions_render_runtime(
    *,
    closed_record_states=None,
    numeric_item_cls=None,
    collect_current_indicator_live_strings=None,
    collect_indicator_value_strings=None,
    collect_record_indicator_keys=None,
    coerce_bool_fn=None,
    dedupe_indicator_entries_normalized=None,
    filter_indicator_entries_for_interval=None,
    format_indicator_list=None,
    indicator_entry_signature=None,
    indicator_short_label=None,
    normalize_indicator_values=None,
    positions_records_cumulative_fn=None,
    pos_triggered_value_column: int = 10,
    pos_current_value_column: int = 11,
    pos_stop_loss_column: int = 15,
    pos_status_column: int = 16,
    pos_close_column: int = 17,
) -> None:
    global _CLOSED_RECORD_STATES
    global _NUMERIC_ITEM_CLS
    global _COLLECT_CURRENT_INDICATOR_LIVE_STRINGS
    global _COLLECT_INDICATOR_VALUE_STRINGS
    global _COLLECT_RECORD_INDICATOR_KEYS
    global _COERCE_BOOL
    global _DEDUPE_INDICATOR_ENTRIES_NORMALIZED
    global _FILTER_INDICATOR_ENTRIES_FOR_INTERVAL
    global _FORMAT_INDICATOR_LIST
    global _INDICATOR_ENTRY_SIGNATURE
    global _INDICATOR_SHORT_LABEL
    global _NORMALIZE_INDICATOR_VALUES
    global _POSITIONS_RECORDS_CUMULATIVE
    global POS_TRIGGERED_VALUE_COLUMN
    global POS_CURRENT_VALUE_COLUMN
    global POS_STOP_LOSS_COLUMN
    global POS_STATUS_COLUMN
    global POS_CLOSE_COLUMN

    _CLOSED_RECORD_STATES = set(closed_record_states or ())
    if numeric_item_cls is not None:
        _NUMERIC_ITEM_CLS = numeric_item_cls
    _COLLECT_CURRENT_INDICATOR_LIVE_STRINGS = collect_current_indicator_live_strings
    _COLLECT_INDICATOR_VALUE_STRINGS = collect_indicator_value_strings
    _COLLECT_RECORD_INDICATOR_KEYS = collect_record_indicator_keys
    _COERCE_BOOL = coerce_bool_fn
    _DEDUPE_INDICATOR_ENTRIES_NORMALIZED = dedupe_indicator_entries_normalized
    _FILTER_INDICATOR_ENTRIES_FOR_INTERVAL = filter_indicator_entries_for_interval
    _FORMAT_INDICATOR_LIST = format_indicator_list
    _INDICATOR_ENTRY_SIGNATURE = indicator_entry_signature
    _INDICATOR_SHORT_LABEL = indicator_short_label
    _NORMALIZE_INDICATOR_VALUES = normalize_indicator_values
    _POSITIONS_RECORDS_CUMULATIVE = positions_records_cumulative_fn
    POS_TRIGGERED_VALUE_COLUMN = int(pos_triggered_value_column)
    POS_CURRENT_VALUE_COLUMN = int(pos_current_value_column)
    POS_STOP_LOSS_COLUMN = int(pos_stop_loss_column)
    POS_STATUS_COLUMN = int(pos_status_column)
    POS_CLOSE_COLUMN = int(pos_close_column)


def _coerce_bool(value, default=False):
    func = _COERCE_BOOL
    if not callable(func):
        return bool(default)
    try:
        return func(value, default)
    except Exception:
        return bool(default)


def _format_indicator_list(keys) -> str:
    func = _FORMAT_INDICATOR_LIST
    if not callable(func):
        try:
            return ", ".join(str(key).strip() for key in (keys or []) if str(key).strip())
        except Exception:
            return ""
    try:
        return str(func(keys))
    except Exception:
        return ""


def _collect_record_indicator_keys(
    rec: dict,
    *,
    include_inactive_allocs: bool = False,
    include_allocation_scope: bool = True,
) -> list[str]:
    func = _COLLECT_RECORD_INDICATOR_KEYS
    if not callable(func):
        return []
    try:
        return list(
            func(
                rec,
                include_inactive_allocs=include_inactive_allocs,
                include_allocation_scope=include_allocation_scope,
            )
        )
    except Exception:
        return []


def _collect_indicator_value_strings(
    rec: dict,
    interval_hint: str | None = None,
) -> tuple[list[str], dict[str, list[str]]]:
    func = _COLLECT_INDICATOR_VALUE_STRINGS
    if not callable(func):
        return ([], {})
    try:
        values, interval_map = func(rec, interval_hint)
        return list(values or []), dict(interval_map or {})
    except Exception:
        return ([], {})


def _collect_current_indicator_live_strings(
    window,
    symbol,
    indicator_keys,
    cache,
    interval_map: dict[str, list[str]] | None = None,
    default_interval_hint: str | None = None,
):
    func = _COLLECT_CURRENT_INDICATOR_LIVE_STRINGS
    if not callable(func):
        return []
    try:
        return list(
            func(
                window,
                symbol,
                indicator_keys,
                cache,
                interval_map,
                default_interval_hint,
            )
            or []
        )
    except Exception:
        return []


def _dedupe_indicator_entries_normalized(entries: list[str] | None) -> list[str]:
    func = _DEDUPE_INDICATOR_ENTRIES_NORMALIZED
    if not callable(func):
        return list(entries or [])
    try:
        return list(func(entries) or [])
    except Exception:
        return list(entries or [])


def _filter_indicator_entries(
    entries: list[str] | None,
    interval_hint: str | None,
    *,
    include_non_matching: bool = True,
) -> list[str]:
    func = _FILTER_INDICATOR_ENTRIES_FOR_INTERVAL
    if not callable(func):
        return list(entries or [])
    try:
        return list(
            func(
                entries,
                interval_hint,
                include_non_matching=include_non_matching,
            )
            or []
        )
    except Exception:
        return list(entries or [])


def _indicator_entry_signature(entry: str) -> tuple[str, str]:
    func = _INDICATOR_ENTRY_SIGNATURE
    if not callable(func):
        text = str(entry or "").strip().lower()
        return (text, "")
    try:
        label_part, interval_part = func(entry)
        return str(label_part or ""), str(interval_part or "")
    except Exception:
        text = str(entry or "").strip().lower()
        return (text, "")


def _indicator_short_label(key) -> str:
    func = _INDICATOR_SHORT_LABEL
    if not callable(func):
        return str(key or "")
    try:
        return str(func(key) or "")
    except Exception:
        return str(key or "")


def _normalize_indicator_values(raw) -> list[str]:
    func = _NORMALIZE_INDICATOR_VALUES
    if not callable(func):
        return []
    try:
        return list(func(raw))
    except Exception:
        return []


def _positions_records_cumulative(self, entries: list[dict], closed_entries: list[dict] | None = None) -> list[dict]:
    func = _POSITIONS_RECORDS_CUMULATIVE
    if not callable(func):
        return list(entries or [])
    try:
        return list(func(self, entries, closed_entries) or [])
    except Exception:
        return list(entries or [])


def _mw_render_positions_table(self):
    try:
        table = self.pos_table
        updates_prev = None
        signals_prev = None
        try:
            updates_prev = table.updatesEnabled()
            table.setUpdatesEnabled(False)
        except Exception:
            pass
        try:
            if hasattr(table, "blockSignals"):
                signals_prev = table.blockSignals(True)
        except Exception:
            pass
        open_records = getattr(self, "_open_position_records", {}) or {}
        closed_records = getattr(self, "_closed_position_records", []) or []
        view_mode = getattr(self, "_positions_view_mode", "cumulative")
        try:
            vbar = self.pos_table.verticalScrollBar()
            vbar_val = vbar.value()
        except Exception:
            vbar = None
            vbar_val = None
        try:
            hbar = self.pos_table.horizontalScrollBar()
            hbar_val = hbar.value()
        except Exception:
            hbar = None
            hbar_val = None
        prev_snapshot = getattr(self, "_last_positions_table_snapshot", None)
        if view_mode == "per_trade":
            display_records = self._positions_records_per_trade(open_records, closed_records)
        else:
            display_records = _positions_records_cumulative(
                self,
                sorted(
                    open_records.values(),
                    key=lambda d: (d["symbol"], d.get("side_key"), d.get("entry_tf")),
                ),
                closed_records,
            )
        display_records = [rec for rec in (display_records or []) if isinstance(rec, dict)]
        snapshot_digest: list[tuple] = []
        acct_type = str(getattr(self, "_positions_account_type", "") or "").upper()
        acct_is_futures = getattr(self, "_positions_account_is_futures", None)
        if acct_is_futures is None:
            acct_is_futures = "FUT" in acct_type
        live_value_cache = getattr(self, "_live_indicator_cache", None)
        if not isinstance(live_value_cache, dict):
            live_value_cache = {}
            self._live_indicator_cache = live_value_cache
        now_ts = time.monotonic()
        ttl = float(getattr(self, "_live_indicator_cache_ttl", 8.0) or 8.0)
        cleanup_interval = max(ttl * 3.0, 30.0)
        last_cleanup = float(getattr(self, "_live_indicator_cache_last_cleanup", 0.0) or 0.0)
        if now_ts - last_cleanup >= cleanup_interval:
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
        for rec in display_records:
            data = rec.get("data") or {}
            status_flag = str(rec.get("status") or data.get("status") or "").strip().lower()
            record_is_closed = status_flag in _CLOSED_RECORD_STATES
            indicators_list = tuple(
                _collect_record_indicator_keys(
                    rec,
                    include_inactive_allocs=record_is_closed,
                    include_allocation_scope=view_mode != "per_trade",
                )
            )
            interval_hint = rec.get("entry_tf") or data.get("interval_display") or data.get("interval") or "-"
            indicator_value_entries, interval_map = _collect_indicator_value_strings(rec, interval_hint)
            rec["_indicator_value_entries"] = indicator_value_entries
            rec["_indicator_interval_map"] = interval_map
            sym_digest = str(rec.get("symbol") or data.get("symbol") or "").strip().upper()
            if record_is_closed:
                current_live_entries = list(rec.get("_current_indicator_values") or [])
            else:
                current_live_entries = _collect_current_indicator_live_strings(
                    self,
                    sym_digest,
                    indicators_list,
                    live_value_cache,
                    interval_map,
                    interval_hint,
                )
            if view_mode == "per_trade":
                filtered_values = _filter_indicator_entries(
                    indicator_value_entries,
                    interval_hint,
                    include_non_matching=False,
                )
                if filtered_values:
                    allowed = {_indicator_entry_signature(entry) for entry in filtered_values}
                    current_live_entries = [
                        entry
                        for entry in (current_live_entries or [])
                        if _indicator_entry_signature(entry) in allowed
                    ]
            if current_live_entries:
                current_live_entries = _dedupe_indicator_entries_normalized(current_live_entries)
            rec["_current_indicator_values"] = current_live_entries
            indicator_snapshot = tuple(indicator_value_entries or [])
            interval_snapshot = tuple((key, tuple(values)) for key, values in (interval_map or {}).items())
            current_live_tuple = tuple(current_live_entries or [])
            snapshot_digest.append(
                (
                    str(rec.get("symbol") or "").upper(),
                    str(rec.get("side_key") or "").upper(),
                    str(rec.get("entry_tf") or ""),
                    indicators_list,
                    indicator_snapshot,
                    interval_snapshot,
                    current_live_tuple,
                    float(data.get("qty") or 0.0),
                    float(data.get("margin_usdt") or 0.0),
                    float(data.get("pnl_value") or 0.0),
                    str(rec.get("status") or ""),
                )
            )
        snapshot_key = (view_mode, tuple(snapshot_digest))
        if prev_snapshot == snapshot_key and view_mode == "per_trade":
            totals = getattr(self, "_last_positions_table_totals", None)
            if isinstance(totals, tuple) and len(totals) == 2:
                self._update_positions_pnl_summary(*totals)
                self._update_global_pnl_display(*self._compute_global_pnl_totals())
            return
        header = self.pos_table.horizontalHeader()
        try:
            sort_column = header.sortIndicatorSection()
            sort_order = header.sortIndicatorOrder()
            if sort_column is None or sort_column < 0:
                sort_column = 0
                sort_order = QtCore.Qt.SortOrder.AscendingOrder
        except Exception:
            sort_column = 0
            sort_order = QtCore.Qt.SortOrder.AscendingOrder
        self.pos_table.setSortingEnabled(False)
        self.pos_table.setRowCount(0)
        total_pnl = 0.0
        total_margin = 0.0
        pnl_has_value = False
        aggregated_keys: set[tuple[str, tuple[str, ...]] | str] = set()
        for rec in display_records:
            try:
                data = rec.get("data", {}) or {}
                sym = str(rec.get("symbol") or data.get("symbol") or "").strip().upper()
                if not sym:
                    sym = "-"
                side_key = str(rec.get("side_key") or data.get("side_key") or "").upper()
                interval = rec.get("entry_tf") or data.get("interval_display") or "-"
                row = self.pos_table.rowCount()
                self.pos_table.insertRow(row)

                qty_show = float(data.get("qty") or 0.0)
                mark = float(data.get("mark") or 0.0)
                size_usdt = float(data.get("size_usdt") or (qty_show * mark))
                mr = normalize_margin_ratio(data.get("margin_ratio"))
                margin_usdt = float(data.get("margin_usdt") or 0.0)
                pnl_roi = data.get("pnl_roi")
                pnl_raw_value = data.get("pnl_value")
                try:
                    pnl_value = float(pnl_raw_value or 0.0)
                except Exception:
                    pnl_value = 0.0
                side_text = "Long" if side_key == "L" else ("Short" if side_key == "S" else "Spot")
                open_time = data.get("open_time") or rec.get("open_time") or "-"
                status_txt = rec.get("status", "Active")
                status_lower = str(status_txt).strip().lower()
                is_closed_like = status_lower in _CLOSED_RECORD_STATES
                close_time = rec.get("close_time") if is_closed_like else "-"
                stop_loss_enabled = bool(rec.get("stop_loss_enabled"))
                stop_loss_text = "Yes" if stop_loss_enabled else "No"

                aggregate_key = str(rec.get("_aggregate_key") or rec.get("ledger_id") or "")
                aggregate_primary = bool(rec.get("_aggregate_is_primary", True))
                should_aggregate = True
                if aggregate_key:
                    indicator_signature = tuple(_normalize_indicator_values(rec.get("indicators")))
                    interval_signature = str(rec.get("entry_tf") or "").strip().lower()
                    if indicator_signature:
                        key_entry = (aggregate_key, interval_signature, indicator_signature)
                    else:
                        key_entry = (aggregate_key, interval_signature)
                    if aggregate_primary:
                        if key_entry in aggregated_keys:
                            should_aggregate = False
                        else:
                            aggregated_keys.add(key_entry)
                    else:
                        should_aggregate = False

                raw_position = data.get("raw_position")
                if not isinstance(raw_position, dict):
                    raw_position = rec.get("raw_position") if isinstance(rec.get("raw_position"), dict) else None
                leverage_val = 0
                leverage_candidates = [
                    data.get("leverage"),
                    rec.get("leverage"),
                    (raw_position or {}).get("leverage"),
                ]
                for candidate in leverage_candidates:
                    try:
                        if candidate is None:
                            continue
                        val = int(round(float(candidate)))
                        if val > 0:
                            leverage_val = val
                            break
                    except Exception:
                        continue
                contract_label_raw = (
                    data.get("contract_type")
                    or data.get("contractType")
                    or data.get("instrument_type")
                    or data.get("instrumentType")
                    or (raw_position or {}).get("contractType")
                    or (raw_position or {}).get("contract_type")
                    or ""
                )
                contract_label = str(contract_label_raw).strip()
                if not contract_label:
                    if side_key in ("L", "S") and acct_is_futures:
                        contract_label = "Perp"
                    elif side_key == "SPOT":
                        contract_label = "Spot"
                elif side_key == "SPOT":
                    contract_label = "Spot"
                contract_display = ""
                if contract_label:
                    if contract_label.upper().startswith("PERP"):
                        contract_display = "Perp"
                    else:
                        contract_display = contract_label.title()
                info_parts: list[str] = []
                if contract_display:
                    info_parts.append(contract_display)
                if leverage_val > 0:
                    info_parts.append(f"{leverage_val}x")
                if info_parts:
                    sym_display = f"{sym}\n{'    '.join(info_parts)}"
                else:
                    sym_display = sym
                self.pos_table.setItem(row, 0, QtWidgets.QTableWidgetItem(sym_display))

                size_item = _NUMERIC_ITEM_CLS(f"{size_usdt:.8f}", size_usdt)
                self.pos_table.setItem(row, 1, size_item)

                mark_item = _NUMERIC_ITEM_CLS(f"{mark:.8f}" if mark else "-", mark)
                self.pos_table.setItem(row, 2, mark_item)

                mr_display = f"{mr:.2f}%" if mr > 0 else "-"
                mr_item = _NUMERIC_ITEM_CLS(mr_display, mr)
                self.pos_table.setItem(row, 3, mr_item)

                liq_price = 0.0
                liq_candidates = [
                    data.get("liquidation_price"),
                    data.get("liquidationPrice"),
                    data.get("liq_price"),
                    data.get("liqPrice"),
                    rec.get("liquidation_price"),
                    rec.get("liquidationPrice"),
                    (raw_position or {}).get("liquidationPrice"),
                    (raw_position or {}).get("liqPrice"),
                ]
                for candidate in liq_candidates:
                    try:
                        if candidate is None or candidate == "":
                            continue
                        value = float(candidate)
                        if value > 0.0:
                            liq_price = value
                            break
                    except Exception:
                        continue
                liq_text = f"{liq_price:.6f}" if liq_price > 0 else "-"
                liq_item = _NUMERIC_ITEM_CLS(liq_text if liq_price > 0 else "-", liq_price)
                self.pos_table.setItem(row, 4, liq_item)

                margin_item = _NUMERIC_ITEM_CLS(f"{margin_usdt:.2f} USDT" if margin_usdt else "-", margin_usdt)
                self.pos_table.setItem(row, 5, margin_item)
                if margin_usdt > 0.0 and should_aggregate:
                    total_margin += margin_usdt

                qty_margin_item = _NUMERIC_ITEM_CLS(f"{qty_show:.6f}", qty_show)
                self.pos_table.setItem(row, 6, qty_margin_item)

                pnl_item = _NUMERIC_ITEM_CLS(str(pnl_roi or "-"), pnl_value)
                self.pos_table.setItem(row, 7, pnl_item)
                added_to_total = False
                if pnl_raw_value is not None and should_aggregate:
                    total_pnl += pnl_value
                    pnl_has_value = True
                    added_to_total = True
                pnl_valid = (pnl_raw_value is not None) or (abs(pnl_value) > 0.0)
                if not pnl_valid and status_lower == "closed":
                    pnl_valid = True
                if status_lower == "closed" and not added_to_total and pnl_valid and should_aggregate:
                    total_pnl += pnl_value
                    pnl_has_value = True

                self.pos_table.setItem(row, 8, QtWidgets.QTableWidgetItem(interval or "-"))
                source_entries = rec.get("_aggregated_entries") or [rec]
                indicators_list: list[str] = []
                indicator_values_entries: list[str] = []
                interval_map: dict[str, list[str]] = {}
                for entry in source_entries:
                    entry_inds = _collect_record_indicator_keys(
                        entry,
                        include_inactive_allocs=is_closed_like,
                        include_allocation_scope=view_mode != "per_trade",
                    )
                    for token in entry_inds:
                        if token and token not in indicators_list:
                            indicators_list.append(token)
                    cached_values = entry.get("_indicator_value_entries")
                    cached_map = entry.get("_indicator_interval_map")
                    interval_hint_entry = entry.get("entry_tf") or (entry.get("data") or {}).get("interval_display") or interval
                    if cached_values is None or cached_map is None:
                        cached_values, cached_map = _collect_indicator_value_strings(entry, interval_hint_entry)
                        entry["_indicator_value_entries"] = cached_values
                        entry["_indicator_interval_map"] = cached_map
                    for value_entry in cached_values or []:
                        if value_entry not in indicator_values_entries:
                            indicator_values_entries.append(value_entry)
                    for key, slots in (cached_map or {}).items():
                        bucket = interval_map.setdefault(key, [])
                        for slot in slots:
                            if slot not in bucket:
                                bucket.append(slot)
                rec["_indicator_value_entries"] = indicator_values_entries
                rec["_indicator_interval_map"] = interval_map
                active_indicator_keys_ordered = list((interval_map or {}).keys())
                display_list: list[str] = list(indicators_list or [])
                if active_indicator_keys_ordered:
                    filtered = [ind for ind in display_list if ind.lower() in active_indicator_keys_ordered]
                    display_list = filtered if filtered else active_indicator_keys_ordered
                indicators_list = display_list
                indicators_display = _format_indicator_list(display_list) if display_list else "-"
                self.pos_table.setItem(row, 9, QtWidgets.QTableWidgetItem(indicators_display))
                interval_for_display = interval
                strict_interval_values = getattr(self, "_positions_view_mode", "cumulative") == "per_trade"
                filtered_indicator_values = _filter_indicator_entries(
                    indicator_values_entries,
                    interval_for_display,
                    include_non_matching=not strict_interval_values,
                )
                if filtered_indicator_values:
                    filtered_indicator_values = list(dict.fromkeys(filtered_indicator_values))
                indicator_values_display = "\n".join(filtered_indicator_values) if filtered_indicator_values else "-"
                self.pos_table.setItem(
                    row,
                    POS_TRIGGERED_VALUE_COLUMN,
                    QtWidgets.QTableWidgetItem(indicator_values_display),
                )
                live_values_entries = rec.get("_current_indicator_values")
                if live_values_entries is None:
                    if not is_closed_like:
                        live_indicator_keys = indicators_list
                        live_interval_map = interval_map
                        if strict_interval_values and filtered_indicator_values:
                            label_map = {
                                _indicator_short_label(key).strip().lower(): key
                                for key in indicators_list
                            }
                            restricted_keys: list[str] = []
                            restricted_map: dict[str, list[str]] = {}
                            for entry in filtered_indicator_values:
                                label_part, interval_part = _indicator_entry_signature(entry)
                                mapped_key = label_map.get(label_part)
                                if not mapped_key:
                                    continue
                                if mapped_key not in restricted_keys:
                                    restricted_keys.append(mapped_key)
                                if interval_part:
                                    slots = restricted_map.setdefault(mapped_key.lower(), [])
                                    interval_clean = interval_part.strip().upper()
                                    if interval_clean and interval_clean not in slots:
                                        slots.append(interval_clean)
                            if restricted_keys:
                                live_indicator_keys = restricted_keys
                                live_interval_map = restricted_map
                        live_values_entries = _collect_current_indicator_live_strings(
                            self,
                            sym,
                            live_indicator_keys,
                            live_value_cache,
                            live_interval_map,
                            interval,
                        )
                        rec["_current_indicator_values"] = live_values_entries
                    else:
                        live_values_entries = []
                if live_values_entries:
                    live_values_entries = _dedupe_indicator_entries_normalized(live_values_entries)
                    rec["_current_indicator_values"] = live_values_entries
                current_values_display = "\n".join(live_values_entries) if live_values_entries else "-"
                self.pos_table.setItem(
                    row,
                    POS_CURRENT_VALUE_COLUMN,
                    QtWidgets.QTableWidgetItem(current_values_display),
                )
                self.pos_table.setItem(row, 12, QtWidgets.QTableWidgetItem(side_text))
                self.pos_table.setItem(row, 13, QtWidgets.QTableWidgetItem(str(open_time or "-")))
                self.pos_table.setItem(row, 14, QtWidgets.QTableWidgetItem(str(close_time or "-")))
                self.pos_table.setItem(row, POS_STOP_LOSS_COLUMN, QtWidgets.QTableWidgetItem(stop_loss_text))
                self.pos_table.setItem(row, POS_STATUS_COLUMN, QtWidgets.QTableWidgetItem(status_txt))
                btn_interval = interval if interval != "-" else None
                btn = self._make_close_btn(sym, side_key, btn_interval, qty_show)
                if str(status_txt).strip().lower() != "active":
                    btn.setEnabled(False)
                self.pos_table.setCellWidget(row, POS_CLOSE_COLUMN, btn)
            except Exception:
                pass
        try:
            if _coerce_bool(self.config.get("positions_auto_resize_rows", True), True):
                self.pos_table.resizeRowsToContents()
        except Exception:
            pass
        try:
            if _coerce_bool(self.config.get("positions_auto_resize_columns", True), True):
                self.pos_table.resizeColumnsToContents()
        except Exception:
            pass
        summary_margin = total_margin if total_margin > 0.0 else None
        self._update_positions_pnl_summary(total_pnl if pnl_has_value else None, summary_margin)
        self._update_global_pnl_display(*self._compute_global_pnl_totals())
        try:
            if (
                getattr(self, "chart_enabled", False)
                and getattr(self, "chart_auto_follow", False)
                and not getattr(self, "_chart_manual_override", False)
                and self._is_chart_visible()
            ):
                self._sync_chart_to_active_positions()
        except Exception:
            pass
    except Exception as exc:
        try:
            self.log(f"Positions table update failed: {exc}")
        except Exception:
            pass
    finally:
        def _restore_scrollbar(bar, value):
            try:
                if bar is None or value is None:
                    return
                value_clamped = max(bar.minimum(), min(value, bar.maximum()))
                bar.setValue(value_clamped)
            except Exception:
                pass

        try:
            self.pos_table.setSortingEnabled(True)
            if sort_column is not None and sort_column >= 0:
                self.pos_table.sortItems(sort_column, sort_order)
        except Exception:
            pass
        try:
            if vbar is not None and vbar_val is not None:
                QtCore.QTimer.singleShot(0, lambda: _restore_scrollbar(vbar, vbar_val))
        except Exception:
            pass
        try:
            if hbar is not None and hbar_val is not None:
                QtCore.QTimer.singleShot(0, lambda: _restore_scrollbar(hbar, hbar_val))
        except Exception:
            pass
        try:
            self._last_positions_table_snapshot = snapshot_key
            self._last_positions_table_totals = (total_pnl if pnl_has_value else None, summary_margin)
        except Exception:
            pass
        try:
            if hasattr(self.pos_table, "blockSignals"):
                self.pos_table.blockSignals(signals_prev if signals_prev is not None else False)
        except Exception:
            pass
        try:
            if updates_prev is not None:
                self.pos_table.setUpdatesEnabled(updates_prev)
        except Exception:
            pass
