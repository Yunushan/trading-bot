from __future__ import annotations

from typing import Any, cast

from PyQt6 import QtWidgets

from app.integrations.exchanges.binance import normalize_margin_ratio

from . import table_render_state_runtime


def _resolve_raw_position(rec: dict, data: dict):
    raw_position = data.get("raw_position")
    if isinstance(raw_position, dict):
        return raw_position
    fallback = rec.get("raw_position")
    return fallback if isinstance(fallback, dict) else None


def _resolve_leverage_value(data: dict, rec: dict, raw_position: dict | None) -> int:
    for candidate in (
        data.get("leverage"),
        rec.get("leverage"),
        (raw_position or {}).get("leverage"),
    ):
        try:
            if candidate is None:
                continue
            leverage_val = int(round(float(candidate)))
            if leverage_val > 0:
                return leverage_val
        except Exception:
            continue
    return 0


def _resolve_contract_display(
    *,
    side_key: str,
    acct_is_futures,
    data: dict,
    raw_position: dict | None,
) -> str:
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
    if not contract_label:
        return ""
    if contract_label.upper().startswith("PERP"):
        return "Perp"
    return contract_label.title()


def _resolve_symbol_display(sym: str, contract_display: str, leverage_val: int) -> str:
    info_parts: list[str] = []
    if contract_display:
        info_parts.append(contract_display)
    if leverage_val > 0:
        info_parts.append(f"{leverage_val}x")
    if not info_parts:
        return sym
    return f"{sym}\n{'    '.join(info_parts)}"


def _resolve_liquidation_price(data: dict, rec: dict, raw_position: dict | None) -> float:
    for candidate in (
        data.get("liquidation_price"),
        data.get("liquidationPrice"),
        data.get("liq_price"),
        data.get("liqPrice"),
        rec.get("liquidation_price"),
        rec.get("liquidationPrice"),
        (raw_position or {}).get("liquidationPrice"),
        (raw_position or {}).get("liqPrice"),
    ):
        try:
            if candidate is None or candidate == "":
                continue
            value = float(candidate)
            if value > 0.0:
                return value
        except Exception:
            continue
    return 0.0


def _make_numeric_item(text: str, value: float):
    item_cls = cast(Any, table_render_state_runtime._NUMERIC_ITEM_CLS)
    return item_cls(text, value)


def _resolve_aggregate_key_entry(rec: dict):
    aggregate_key = str(rec.get("_aggregate_key") or rec.get("close_event_id") or rec.get("ledger_id") or "")
    if not aggregate_key:
        return None
    indicator_signature = tuple(
        table_render_state_runtime._normalize_indicator_values(rec.get("indicators"))
    )
    interval_signature = str(rec.get("entry_tf") or "").strip().lower()
    if indicator_signature:
        return (aggregate_key, interval_signature, indicator_signature)
    return (aggregate_key, interval_signature)


def _resolve_close_target_identity(rec: dict) -> dict[str, str] | None:
    sources: list[dict] = []
    allocations = rec.get("allocations") or []
    if isinstance(allocations, dict):
        allocations = list(allocations.values())
    if isinstance(allocations, list):
        for entry in allocations:
            if isinstance(entry, dict):
                sources.append(entry)
                break
    data = rec.get("data")
    if isinstance(data, dict):
        sources.append(data)
    sources.append(rec)

    target_identity: dict[str, str] = {}
    for field_name in (
        "_aggregate_key",
        "aggregate_key",
        "trade_id",
        "client_order_id",
        "order_id",
        "event_uid",
        "context_key",
        "slot_id",
        "open_time",
    ):
        for source in sources:
            value = str(source.get(field_name) or "").strip()
            if value:
                target_identity[field_name] = value
                break
    return target_identity or None


def _merge_indicator_sources(
    rec: dict,
    *,
    interval: str,
    view_mode: str,
    is_closed_like: bool,
) -> tuple[list[str], list[str], dict[str, list[str]]]:
    source_entries = rec.get("_aggregated_entries") or [rec]
    indicators_list: list[str] = []
    indicator_values_entries: list[str] = []
    interval_map: dict[str, list[str]] = {}
    for entry in source_entries:
        entry_inds = table_render_state_runtime._collect_record_indicator_keys(
            entry,
            include_inactive_allocs=is_closed_like,
            include_allocation_scope=view_mode != "per_trade",
        )
        for token in entry_inds:
            if token and token not in indicators_list:
                indicators_list.append(token)
        cached_values = entry.get("_indicator_value_entries")
        cached_map = entry.get("_indicator_interval_map")
        interval_hint_entry = (
            entry.get("entry_tf")
            or (entry.get("data") or {}).get("interval_display")
            or interval
        )
        if cached_values is None or cached_map is None:
            cached_values, cached_map = table_render_state_runtime._collect_indicator_value_strings(
                entry,
                interval_hint_entry,
            )
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
    indicators_list = table_render_state_runtime._canonicalize_indicator_keys(indicators_list)
    indicator_values_entries = table_render_state_runtime._canonicalize_indicator_entries(
        indicator_values_entries
    )
    interval_map = table_render_state_runtime._canonicalize_indicator_interval_map(interval_map)
    rec["_indicator_value_entries"] = indicator_values_entries
    rec["_indicator_interval_map"] = interval_map
    active_indicator_keys_ordered = list((interval_map or {}).keys())
    display_list = list(indicators_list or [])
    if active_indicator_keys_ordered:
        display_lookup = {str(entry).strip().lower() for entry in display_list if str(entry).strip()}
        filtered = [
            indicator_key
            for indicator_key in active_indicator_keys_ordered
            if indicator_key.lower() in display_lookup
        ]
        display_list = filtered if filtered else list(active_indicator_keys_ordered)
    return display_list, indicator_values_entries, interval_map


def _restrict_live_indicator_scope(
    indicators_list: list[str],
    filtered_indicator_values: list[str],
) -> tuple[list[str], dict[str, list[str]]]:
    label_map = {
        table_render_state_runtime._indicator_short_label(key).strip().lower(): key
        for key in indicators_list
    }
    restricted_keys: list[str] = []
    restricted_map: dict[str, list[str]] = {}
    for entry in filtered_indicator_values:
        label_part, interval_part = table_render_state_runtime._indicator_entry_signature(entry)
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
    return restricted_keys, restricted_map


def _resolve_live_values_entries(
    self,
    *,
    rec: dict,
    sym: str,
    interval: str,
    indicators_list: list[str],
    interval_map: dict[str, list[str]],
    filtered_indicator_values: list[str],
    strict_interval_values: bool,
    is_closed_like: bool,
    live_value_cache: dict,
):
    live_values_entries = rec.get("_current_indicator_values")
    if live_values_entries is None:
        if is_closed_like:
            live_values_entries = []
        else:
            live_indicator_keys = indicators_list
            live_interval_map = interval_map
            if strict_interval_values and filtered_indicator_values:
                restricted_keys, restricted_map = _restrict_live_indicator_scope(
                    indicators_list,
                    filtered_indicator_values,
                )
                if restricted_keys:
                    live_indicator_keys = restricted_keys
                    live_interval_map = restricted_map
            live_values_entries = table_render_state_runtime._collect_current_indicator_live_strings(
                self,
                sym,
                live_indicator_keys,
                live_value_cache,
                live_interval_map,
                interval,
            )
            rec["_current_indicator_values"] = live_values_entries
    if live_values_entries:
        live_values_entries = table_render_state_runtime._dedupe_indicator_entries_normalized(
            live_values_entries
        )
        live_values_entries = table_render_state_runtime._canonicalize_indicator_entries(
            live_values_entries
        )
        rec["_current_indicator_values"] = live_values_entries
    return live_values_entries


def populate_positions_table(
    self,
    *,
    display_records: list[dict],
    view_mode: str,
    acct_is_futures,
    live_value_cache: dict,
) -> dict:
    total_pnl = 0.0
    total_margin = 0.0
    pnl_has_value = False
    aggregated_keys: set[tuple] = set()
    strict_interval_values = view_mode == "per_trade"
    for rec in display_records:
        try:
            data = rec.get("data", {}) or {}
            sym = str(rec.get("symbol") or data.get("symbol") or "").strip().upper() or "-"
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
            is_closed_like = status_lower in table_render_state_runtime._CLOSED_RECORD_STATES
            close_time = rec.get("close_time") if is_closed_like else "-"
            stop_loss_text = "Yes" if bool(rec.get("stop_loss_enabled")) else "No"

            aggregate_key_entry = _resolve_aggregate_key_entry(rec)
            aggregate_primary = bool(rec.get("_aggregate_is_primary", True))
            should_aggregate = True
            if aggregate_key_entry:
                if aggregate_primary:
                    if aggregate_key_entry in aggregated_keys:
                        should_aggregate = False
                    else:
                        aggregated_keys.add(aggregate_key_entry)
                else:
                    should_aggregate = False

            raw_position = _resolve_raw_position(rec, data)
            leverage_val = _resolve_leverage_value(data, rec, raw_position)
            contract_display = _resolve_contract_display(
                side_key=side_key,
                acct_is_futures=acct_is_futures,
                data=data,
                raw_position=raw_position,
            )
            self.pos_table.setItem(
                row,
                0,
                QtWidgets.QTableWidgetItem(
                    _resolve_symbol_display(sym, contract_display, leverage_val)
                ),
            )

            self.pos_table.setItem(
                row,
                1,
                _make_numeric_item(f"{size_usdt:.8f}", size_usdt),
            )
            self.pos_table.setItem(
                row,
                2,
                _make_numeric_item(
                    f"{mark:.8f}" if mark else "-",
                    mark,
                ),
            )
            self.pos_table.setItem(
                row,
                3,
                _make_numeric_item(
                    f"{mr:.2f}%" if mr > 0 else "-",
                    mr,
                ),
            )

            liq_price = _resolve_liquidation_price(data, rec, raw_position)
            self.pos_table.setItem(
                row,
                4,
                _make_numeric_item(
                    f"{liq_price:.6f}" if liq_price > 0 else "-",
                    liq_price,
                ),
            )
            self.pos_table.setItem(
                row,
                5,
                _make_numeric_item(
                    f"{margin_usdt:.2f} USDT" if margin_usdt else "-",
                    margin_usdt,
                ),
            )
            if margin_usdt > 0.0 and should_aggregate:
                total_margin += margin_usdt
            self.pos_table.setItem(
                row,
                6,
                _make_numeric_item(f"{qty_show:.6f}", qty_show),
            )
            self.pos_table.setItem(
                row,
                7,
                _make_numeric_item(str(pnl_roi or "-"), pnl_value),
            )

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
            indicators_list, indicator_values_entries, interval_map = _merge_indicator_sources(
                rec,
                interval=interval,
                view_mode=view_mode,
                is_closed_like=is_closed_like,
            )
            self.pos_table.setItem(
                row,
                9,
                QtWidgets.QTableWidgetItem(
                    table_render_state_runtime._format_indicator_list(indicators_list)
                    if indicators_list
                    else "-"
                ),
            )

            filtered_indicator_values = table_render_state_runtime._filter_indicator_entries(
                indicator_values_entries,
                interval,
                include_non_matching=not strict_interval_values,
            )
            if filtered_indicator_values:
                filtered_indicator_values = list(dict.fromkeys(filtered_indicator_values))
                filtered_indicator_values = table_render_state_runtime._canonicalize_indicator_entries(
                    filtered_indicator_values
                )
            self.pos_table.setItem(
                row,
                table_render_state_runtime.POS_TRIGGERED_VALUE_COLUMN,
                QtWidgets.QTableWidgetItem(
                    "\n".join(filtered_indicator_values) if filtered_indicator_values else "-"
                ),
            )

            live_values_entries = _resolve_live_values_entries(
                self,
                rec=rec,
                sym=sym,
                interval=interval,
                indicators_list=indicators_list,
                interval_map=interval_map,
                filtered_indicator_values=filtered_indicator_values,
                strict_interval_values=strict_interval_values,
                is_closed_like=is_closed_like,
                live_value_cache=live_value_cache,
            )
            self.pos_table.setItem(
                row,
                table_render_state_runtime.POS_CURRENT_VALUE_COLUMN,
                QtWidgets.QTableWidgetItem(
                    "\n".join(live_values_entries) if live_values_entries else "-"
                ),
            )
            self.pos_table.setItem(row, 12, QtWidgets.QTableWidgetItem(side_text))
            self.pos_table.setItem(row, 13, QtWidgets.QTableWidgetItem(str(open_time or "-")))
            self.pos_table.setItem(row, 14, QtWidgets.QTableWidgetItem(str(close_time or "-")))
            self.pos_table.setItem(
                row,
                table_render_state_runtime.POS_STOP_LOSS_COLUMN,
                QtWidgets.QTableWidgetItem(stop_loss_text),
            )
            self.pos_table.setItem(
                row,
                table_render_state_runtime.POS_STATUS_COLUMN,
                QtWidgets.QTableWidgetItem(status_txt),
            )
            btn_interval = interval if interval != "-" else None
            btn = self._make_close_btn(
                sym,
                side_key,
                btn_interval,
                qty_show,
                _resolve_close_target_identity(rec),
            )
            if status_lower != "active":
                btn.setEnabled(False)
            self.pos_table.setCellWidget(
                row,
                table_render_state_runtime.POS_CLOSE_COLUMN,
                btn,
            )
        except Exception:
            pass
    return {
        "pnl_has_value": pnl_has_value,
        "summary_margin": total_margin if total_margin > 0.0 else None,
        "total_pnl": total_pnl,
    }
