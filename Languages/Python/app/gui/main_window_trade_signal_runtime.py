from __future__ import annotations

import copy
from datetime import datetime

from app.gui import main_window_trade_signal_open_runtime


def _connector_name(self) -> str:
    try:
        return self._connector_label_text(self._runtime_connector_backend(suppress_refresh=True))
    except Exception:
        return "Unknown"


def _side_key(side_value) -> str:
    return "L" if str(side_value).upper() in ("BUY", "LONG") else "S"


def _ensure_trade_maps(self):
    alloc_map = getattr(self, "_entry_allocations", None)
    if alloc_map is None:
        self._entry_allocations = {}
        alloc_map = self._entry_allocations

    pending_close = getattr(self, "_pending_close_times", None)
    if pending_close is None:
        self._pending_close_times = {}
        pending_close = self._pending_close_times
    return alloc_map, pending_close


def _normalize_interval(self, value):
    try:
        canon = self._canonicalize_interval(value)
    except Exception:
        canon = None
    if canon:
        return canon
    if isinstance(value, str):
        lowered = value.strip().lower()
        return lowered or None
    return None


def _safe_float(value):
    try:
        if value is None:
            return None
        if isinstance(value, str):
            stripped = value.strip()
            if not stripped:
                return None
            return float(stripped)
        return float(value)
    except Exception:
        return None


def _persist_trade_allocations(self, save_position_allocations) -> None:
    try:
        mode = self.mode_combo.currentText() if hasattr(self, "mode_combo") else None
        save_position_allocations(
            getattr(self, "_entry_allocations", {}),
            getattr(self, "_open_position_records", {}),
            mode=mode,
        )
    except Exception:
        pass


def _refresh_trade_views(self, sym, *, mark_traded: bool = True) -> None:
    if mark_traded and sym:
        self.traded_symbols.add(sym)
    self.update_balance_label()
    self.refresh_positions(symbols=[sym] if sym else None)


def _sync_open_position_snapshot(
    self,
    symbol_key: str,
    side_key_local: str,
    alloc_entries: list | None,
    trade_snapshot: dict | None,
    interval_label: str | None,
    normalized_interval: str | None,
    open_time_fmt: str | None,
    *,
    resolve_trigger_indicators,
    normalize_trigger_actions_map,
) -> None:
    if not symbol_key or side_key_local not in ("L", "S"):
        return

    open_records = getattr(self, "_open_position_records", None)
    if not isinstance(open_records, dict):
        open_records = {}
        self._open_position_records = open_records

    record = open_records.get((symbol_key, side_key_local))
    if not isinstance(record, dict):
        record = {
            "symbol": symbol_key,
            "side_key": side_key_local,
            "entry_tf": interval_label or normalized_interval or "-",
            "open_time": open_time_fmt
            or (trade_snapshot.get("open_time") if isinstance(trade_snapshot, dict) else "-"),
            "close_time": "-",
            "status": "Active",
            "data": {},
            "indicators": [],
            "stop_loss_enabled": False,
        }
        open_records[(symbol_key, side_key_local)] = record

    record["status"] = "Active"
    if interval_label:
        record["entry_tf"] = interval_label
    elif normalized_interval and not record.get("entry_tf"):
        record["entry_tf"] = normalized_interval
    if open_time_fmt:
        record["open_time"] = open_time_fmt
    record["allocations"] = copy.deepcopy(alloc_entries or [])

    base_data = dict(record.get("data") or {})
    base_data.setdefault("symbol", symbol_key)
    base_data.setdefault("side_key", side_key_local)
    if interval_label:
        base_data.setdefault("interval_display", interval_label)
    if normalized_interval:
        base_data.setdefault("interval", normalized_interval)

    if isinstance(trade_snapshot, dict):
        trigger_desc = trade_snapshot.get("trigger_desc")
        if trigger_desc:
            base_data["trigger_desc"] = trigger_desc
        normalized_triggers = resolve_trigger_indicators(
            trade_snapshot.get("trigger_indicators"),
            trigger_desc,
        )
        if normalized_triggers:
            base_data["trigger_indicators"] = normalized_triggers
        normalized_actions = normalize_trigger_actions_map(
            trade_snapshot.get("trigger_actions")
        )
        if normalized_actions:
            base_data["trigger_actions"] = normalized_actions

        value_mappings = (
            ("qty", "qty"),
            ("margin_usdt", "margin_usdt"),
            ("pnl_value", "pnl_value"),
            ("entry_price", "entry_price"),
            ("leverage", "leverage"),
            ("notional", "size_usdt"),
            ("size_usdt", "size_usdt"),
        )
        for src_key, dest_key in value_mappings:
            value = trade_snapshot.get(src_key)
            if value is None or value == "":
                continue
            if isinstance(value, str):
                try:
                    value_num = float(value)
                except Exception:
                    value_num = value
            else:
                value_num = value
            if dest_key == "leverage":
                try:
                    value_num = int(value_num)
                except Exception:
                    pass
            if dest_key not in base_data or base_data.get(dest_key) in (None, "", 0):
                base_data[dest_key] = value_num

    record["data"] = base_data


def _scale_fields(payload: dict, ratio: float) -> None:
    for field_name in ("margin_usdt", "margin_balance", "notional", "size_usdt"):
        try:
            value = float(payload.get(field_name) or 0.0)
        except Exception:
            value = 0.0
        if value > 0.0:
            payload[field_name] = max(0.0, value * ratio)


def _build_closed_snapshot(
    entry_payload: dict,
    *,
    close_time_fmt: str | None,
    qty_tol: float,
    qty_closed: float | None = None,
) -> dict:
    snapshot = copy.deepcopy(entry_payload)
    try:
        entry_qty_val = abs(float(entry_payload.get("qty") or 0.0))
    except Exception:
        entry_qty_val = 0.0
    if qty_closed is not None and entry_qty_val > qty_tol:
        qty_use = max(0.0, min(entry_qty_val, float(qty_closed)))
        ratio_use = qty_use / entry_qty_val if entry_qty_val > 0.0 else 1.0
        snapshot["qty"] = qty_use
        _scale_fields(snapshot, ratio_use)
    if close_time_fmt:
        snapshot["close_time"] = close_time_fmt
    elif not snapshot.get("close_time"):
        snapshot["close_time"] = entry_payload.get("close_time")
    snapshot["status"] = "Closed"
    return snapshot


def _consume_closed_entries(
    entries: list,
    *,
    qty_remaining,
    qty_tol: float,
    close_time_fmt: str | None,
    matcher,
):
    closed_snapshots: list[dict] = []
    survivors: list[dict] = []
    matched = False

    for entry in entries:
        if not isinstance(entry, dict):
            continue

        target_match = bool(matcher(entry))
        if target_match:
            matched = True
        if not target_match:
            survivors.append(entry)
            continue

        try:
            entry_qty = abs(float(entry.get("qty") or 0.0))
        except Exception:
            entry_qty = 0.0

        if qty_remaining is None:
            closed_snapshots.append(
                _build_closed_snapshot(
                    entry,
                    close_time_fmt=close_time_fmt,
                    qty_tol=qty_tol,
                )
            )
            continue

        if qty_remaining <= qty_tol:
            survivors.append(entry)
            continue

        qty_used = qty_remaining
        if entry_qty > qty_tol:
            qty_used = min(entry_qty, qty_remaining)

        if entry_qty > qty_tol and (entry_qty - qty_used) > qty_tol:
            closed_snapshots.append(
                _build_closed_snapshot(
                    entry,
                    close_time_fmt=close_time_fmt,
                    qty_tol=qty_tol,
                    qty_closed=qty_used,
                )
            )
            survivor_entry = copy.deepcopy(entry)
            survivor_qty = max(0.0, entry_qty - qty_used)
            survivor_entry["qty"] = survivor_qty
            ratio_remaining = survivor_qty / entry_qty if entry_qty > 0.0 else 1.0
            _scale_fields(survivor_entry, ratio_remaining)
            survivors.append(survivor_entry)
        else:
            closed_snapshots.append(
                _build_closed_snapshot(
                    entry,
                    close_time_fmt=close_time_fmt,
                    qty_tol=qty_tol,
                    qty_closed=qty_used if entry_qty > qty_tol else None,
                )
            )

        qty_remaining = max(0.0, qty_remaining - max(0.0, qty_used))

    return closed_snapshots, survivors, qty_remaining, matched


def _restore_survivor_snapshot(
    self,
    ctx: dict,
    survivors: list[dict],
    *,
    interval,
    normalized_interval,
    pending_close,
    save_position_allocations,
    resolve_trigger_indicators,
    normalize_trigger_actions_map,
) -> None:
    try:
        seed = copy.deepcopy(survivors[0]) if survivors else {}
    except Exception:
        seed = survivors[0] if survivors else {}

    try:
        seed_interval = seed.get("interval_display") or seed.get("interval") or interval
        seed_norm_iv = _normalize_interval(self, seed_interval) or normalized_interval
        seed_open_time = seed.get("open_time")
        _sync_open_position_snapshot(
            self,
            ctx["sym_upper"],
            ctx["side_key"],
            survivors,
            seed if isinstance(seed, dict) else None,
            seed_interval,
            seed_norm_iv,
            seed_open_time,
            resolve_trigger_indicators=resolve_trigger_indicators,
            normalize_trigger_actions_map=normalize_trigger_actions_map,
        )
    except Exception:
        pass

    try:
        pending_close.pop((ctx["sym_upper"], ctx["side_key"]), None)
    except Exception:
        pass

    _persist_trade_allocations(self, save_position_allocations)
    _refresh_trade_views(self, ctx["sym"], mark_traded=False)


def _record_closed_position(
    self,
    order_info: dict,
    ctx: dict,
    *,
    closed_snapshots: list[dict],
    max_closed_history: int,
) -> bool:
    close_time_val = order_info.get("time")
    dt_obj = self._parse_any_datetime(close_time_val)
    if dt_obj is None:
        dt_obj = datetime.now().astimezone()
    close_time_fmt = self._format_display_time(dt_obj)

    alloc_entries_snapshot = list(closed_snapshots or [])
    for entry_snap in alloc_entries_snapshot:
        if not entry_snap.get("close_time"):
            entry_snap["close_time"] = close_time_fmt

    ledger_id = order_info.get("ledger_id")
    qty_reported = _safe_float(order_info.get("qty") or order_info.get("executed_qty"))
    if qty_reported is not None:
        qty_reported = abs(qty_reported)

    close_price_reported = _safe_float(
        order_info.get("close_price")
        or order_info.get("avg_price")
        or order_info.get("price")
        or order_info.get("mark_price")
    )
    entry_price_reported = _safe_float(order_info.get("entry_price"))
    pnl_reported = _safe_float(order_info.get("pnl_value"))
    margin_reported = _safe_float(order_info.get("margin_usdt"))
    roi_reported = _safe_float(order_info.get("roi_percent"))

    leverage_reported = None
    leverage_value = _safe_float(order_info.get("leverage"))
    if leverage_value is not None and leverage_value > 0:
        try:
            leverage_reported = int(round(leverage_value))
        except Exception:
            leverage_reported = None

    processed = getattr(self, "_processed_close_events", None)
    if processed is None:
        processed = set()
        self._processed_close_events = processed

    unique_key = order_info.get("event_id")
    if not unique_key:
        identifier = ledger_id or ctx["sym_upper"] or ""
        qty_token = f"{qty_reported:.8f}" if qty_reported is not None else "0"
        unique_key = f"{identifier}|{close_time_fmt}|{qty_token}|{ctx['side_key']}"
    if unique_key in processed:
        return False
    processed.add(unique_key)

    open_records = getattr(self, "_open_position_records", {}) or {}
    base_record = copy.deepcopy(open_records.get((ctx["sym_upper"], ctx["side_key"])))
    if not base_record:
        base_record = {
            "symbol": ctx["sym_upper"],
            "side_key": ctx["side_key"],
            "entry_tf": "-",
            "open_time": "-",
            "close_time": close_time_fmt,
            "status": "Closed",
            "data": {},
            "indicators": [],
            "stop_loss_enabled": False,
        }
    else:
        base_record["status"] = "Closed"
        base_record["close_time"] = close_time_fmt
    if ledger_id:
        base_record["ledger_id"] = ledger_id

    base_data_snap = dict(base_record.get("data") or {})
    if alloc_entries_snapshot:
        qty_total = 0.0
        margin_total = 0.0
        pnl_total = 0.0
        pnl_has_value = False
        notional_total = 0.0
        trigger_list = []
        try:
            base_qty_curr = float(base_data_snap.get("qty") or 0.0)
        except Exception:
            base_qty_curr = 0.0
        try:
            base_margin_curr = float(base_data_snap.get("margin_usdt") or 0.0)
        except Exception:
            base_margin_curr = 0.0
        try:
            base_pnl_curr = float(base_data_snap.get("pnl_value") or 0.0)
        except Exception:
            base_pnl_curr = 0.0
        try:
            base_notional_curr = float(base_data_snap.get("size_usdt") or 0.0)
        except Exception:
            base_notional_curr = 0.0
        alloc_count = len(alloc_entries_snapshot)

        for entry_snap in alloc_entries_snapshot:
            try:
                qty_val = abs(float(entry_snap.get("qty") or 0.0))
            except Exception:
                qty_val = 0.0
            qty_total += qty_val

            margin_val = entry_snap.get("margin_usdt")
            try:
                margin_missing = margin_val is None or float(margin_val or 0.0) == 0.0
            except Exception:
                margin_missing = margin_val is None
            if margin_missing and base_margin_curr > 0:
                share = (
                    (qty_val / base_qty_curr)
                    if base_qty_curr > 0
                    else (1.0 / alloc_count if alloc_count else 0.0)
                )
                entry_snap["margin_usdt"] = base_margin_curr * share if share else base_margin_curr
            try:
                margin_total += max(float(entry_snap.get("margin_usdt") or 0.0), 0.0)
            except Exception:
                pass

            pnl_val = entry_snap.get("pnl_value")
            if pnl_val is not None:
                try:
                    pnl_total += float(pnl_val)
                    pnl_has_value = True
                except Exception:
                    pass
            elif base_pnl_curr:
                share = (
                    (qty_val / base_qty_curr)
                    if base_qty_curr > 0
                    else (1.0 / alloc_count if alloc_count else 0.0)
                )
                approx_pnl = base_pnl_curr * share if share else base_pnl_curr
                entry_snap["pnl_value"] = approx_pnl
                pnl_total += approx_pnl
                pnl_has_value = True

            try:
                notional_total += max(float(entry_snap.get("notional") or 0.0), 0.0)
            except Exception:
                pass
            if entry_snap.get("notional") in (None, 0.0) and base_notional_curr > 0:
                share = (
                    (qty_val / base_qty_curr)
                    if base_qty_curr > 0
                    else (1.0 / alloc_count if alloc_count else 0.0)
                )
                entry_snap["notional"] = base_notional_curr * share if share else base_notional_curr

            trig = entry_snap.get("trigger_indicators")
            if isinstance(trig, (list, tuple, set)):
                trigger_list.extend([str(t).strip() for t in trig if str(t).strip()])
            if close_price_reported is not None and close_price_reported > 0:
                entry_snap["close_price"] = close_price_reported
            if entry_price_reported is not None and entry_price_reported > 0:
                entry_snap.setdefault("entry_price", entry_price_reported)
            if leverage_reported:
                entry_snap["leverage"] = leverage_reported

        if qty_reported is not None and qty_reported > 0:
            qty_total = qty_reported
        if margin_reported is not None and margin_reported > 0:
            margin_total = margin_reported
        if pnl_reported is not None:
            pnl_total = pnl_reported
            pnl_has_value = True
        if qty_total > 0:
            base_data_snap["qty"] = qty_total
        if margin_total > 0:
            base_data_snap["margin_usdt"] = margin_total
        if pnl_has_value:
            base_data_snap["pnl_value"] = pnl_total
        if notional_total > 0:
            base_data_snap["size_usdt"] = notional_total
        if margin_total > 0 and pnl_has_value:
            roi_percent = (pnl_total / margin_total) * 100.0 if margin_total else 0.0
            base_data_snap["roi_percent"] = roi_percent
            base_data_snap["pnl_roi"] = f"{pnl_total:+.2f} USDT ({roi_percent:+.2f}%)"
        if (
            pnl_reported is not None
            and roi_reported is not None
            and margin_reported is not None
            and margin_reported > 0
        ):
            base_data_snap["roi_percent"] = roi_reported
            base_data_snap["pnl_roi"] = f"{pnl_reported:+.2f} USDT ({roi_reported:+.2f}%)"
        if trigger_list:
            trigger_list = list(dict.fromkeys(trigger_list))
            base_record["indicators"] = trigger_list
            base_data_snap["trigger_indicators"] = trigger_list

    if qty_reported is not None and qty_reported > 0:
        base_data_snap["qty"] = qty_reported
    if margin_reported is not None and margin_reported > 0:
        base_data_snap["margin_usdt"] = margin_reported
    if pnl_reported is not None:
        base_data_snap["pnl_value"] = pnl_reported
        if margin_reported and margin_reported > 0:
            roi_val = roi_reported if roi_reported is not None else (pnl_reported / margin_reported) * 100.0
            base_data_snap["roi_percent"] = roi_val
            base_data_snap["pnl_roi"] = f"{pnl_reported:+.2f} USDT ({roi_val:+.2f}%)"
        else:
            base_data_snap["pnl_roi"] = f"{pnl_reported:+.2f} USDT"
    if close_price_reported is not None and close_price_reported > 0:
        base_data_snap["close_price"] = close_price_reported
    if entry_price_reported is not None and entry_price_reported > 0:
        base_data_snap.setdefault("entry_price", entry_price_reported)
    if leverage_reported:
        base_data_snap["leverage"] = leverage_reported

    base_record["data"] = base_data_snap
    base_record["allocations"] = alloc_entries_snapshot

    try:
        closed_records = getattr(self, "_closed_position_records", [])
        if ledger_id:
            replaced = False
            for idx, rec in enumerate(closed_records):
                if isinstance(rec, dict) and rec.get("ledger_id") == ledger_id:
                    closed_records[idx] = base_record
                    replaced = True
                    break
            if not replaced:
                closed_records.insert(0, base_record)
        else:
            closed_records.insert(0, base_record)
        self._closed_position_records = closed_records
    except Exception:
        pass

    try:
        registry = getattr(self, "_closed_trade_registry", None)
        if registry is None:
            registry = {}
            self._closed_trade_registry = registry
        registry_key = ledger_id or unique_key
        if registry_key:
            registry[registry_key] = {
                "pnl_value": _safe_float(base_data_snap.get("pnl_value")),
                "margin_usdt": _safe_float(base_data_snap.get("margin_usdt")),
                "roi_percent": _safe_float(base_data_snap.get("roi_percent")),
            }
            if len(registry) > max_closed_history:
                excess = len(registry) - max_closed_history
                if excess > 0:
                    for old_key in list(registry.keys())[:excess]:
                        registry.pop(old_key, None)
        try:
            self._update_global_pnl_display(*self._compute_global_pnl_totals())
        except Exception:
            pass
    except Exception:
        pass

    return True


def _handle_close_interval_event(
    self,
    order_info: dict,
    ctx: dict,
    *,
    alloc_map,
    pending_close,
    max_closed_history: int,
    resolve_trigger_indicators,
    normalize_trigger_actions_map,
    save_position_allocations,
) -> None:
    try:
        if hasattr(self, "_track_interval_close"):
            self._track_interval_close(ctx["sym"], ctx["side_key"], ctx["interval"])
    except Exception:
        pass

    normalized_interval = _normalize_interval(self, ctx["interval"])
    close_time_val_evt = order_info.get("time")
    dt_close_evt = self._parse_any_datetime(close_time_val_evt) if close_time_val_evt else None
    close_time_fmt_evt = self._format_display_time(dt_close_evt) if dt_close_evt else close_time_val_evt
    ledger_id_evt = str(order_info.get("ledger_id") or "").strip()

    qty_reported_evt = _safe_float(order_info.get("qty") or order_info.get("executed_qty"))
    if qty_reported_evt is not None:
        qty_reported_evt = abs(qty_reported_evt)
    qty_tol_evt = 1e-9

    entries = alloc_map.get((ctx["sym_upper"], ctx["side_key"]), [])
    if isinstance(entries, dict):
        entries = list(entries.values())

    closed_snapshots: list[dict] = []
    survivors: list[dict] = []
    matched_by_ledger = False
    if isinstance(entries, list):
        closed_snapshots, survivors, _, matched_by_ledger = _consume_closed_entries(
            entries,
            qty_remaining=qty_reported_evt,
            qty_tol=qty_tol_evt,
            close_time_fmt=close_time_fmt_evt,
            matcher=lambda entry: (
                bool(str(entry.get("ledger_id") or "").strip())
                and str(entry.get("ledger_id") or "").strip() == ledger_id_evt
            )
            if ledger_id_evt
            else (
                normalized_interval is None
                or _normalize_interval(
                    self,
                    entry.get("interval") or entry.get("interval_display"),
                )
                == normalized_interval
            ),
        )

    if ledger_id_evt and not matched_by_ledger and isinstance(entries, list):
        closed_snapshots, survivors, _, _ = _consume_closed_entries(
            entries,
            qty_remaining=qty_reported_evt,
            qty_tol=qty_tol_evt,
            close_time_fmt=close_time_fmt_evt,
            matcher=lambda entry: (
                normalized_interval is None
                or _normalize_interval(
                    self,
                    entry.get("interval") or entry.get("interval_display"),
                )
                == normalized_interval
            ),
        )

    if survivors:
        alloc_map[(ctx["sym_upper"], ctx["side_key"])] = survivors
    else:
        alloc_map.pop((ctx["sym_upper"], ctx["side_key"]), None)

    if not closed_snapshots and survivors:
        _restore_survivor_snapshot(
            self,
            ctx,
            survivors,
            interval=ctx["interval"],
            normalized_interval=normalized_interval,
            pending_close=pending_close,
            save_position_allocations=save_position_allocations,
            resolve_trigger_indicators=resolve_trigger_indicators,
            normalize_trigger_actions_map=normalize_trigger_actions_map,
        )
        return

    _persist_trade_allocations(self, save_position_allocations)

    if ctx["sym_upper"]:
        recorded = _record_closed_position(
            self,
            order_info,
            ctx,
            closed_snapshots=closed_snapshots,
            max_closed_history=max_closed_history,
        )
        if not recorded:
            return

    try:
        pending_close.pop((ctx["sym_upper"], ctx["side_key"]), None)
    except Exception:
        pass

    if ctx["sym_upper"]:
        if survivors:
            try:
                seed = copy.deepcopy(survivors[0]) if survivors else {}
            except Exception:
                seed = survivors[0] if survivors else {}
            try:
                seed_interval = seed.get("interval_display") or seed.get("interval") or ctx["interval"]
                seed_norm_iv = _normalize_interval(self, seed_interval) or normalized_interval
                seed_open_time = seed.get("open_time")
                _sync_open_position_snapshot(
                    self,
                    ctx["sym_upper"],
                    ctx["side_key"],
                    survivors,
                    seed if isinstance(seed, dict) else None,
                    seed_interval,
                    seed_norm_iv,
                    seed_open_time,
                    resolve_trigger_indicators=resolve_trigger_indicators,
                    normalize_trigger_actions_map=normalize_trigger_actions_map,
                )
            except Exception:
                pass
        else:
            try:
                getattr(self, "_open_position_records", {}).pop((ctx["sym_upper"], ctx["side_key"]), None)
            except Exception:
                pass
            try:
                getattr(self, "_position_missing_counts", {}).pop((ctx["sym_upper"], ctx["side_key"]), None)
            except Exception:
                pass

    try:
        guard_obj = getattr(self, "guard", None)
        if guard_obj and hasattr(guard_obj, "mark_closed") and ctx["sym_upper"]:
            side_norm = "BUY" if ctx["side_key"] == "L" else "SELL"
            guard_obj.mark_closed(ctx["sym_upper"], ctx["interval"], side_norm)
    except Exception:
        pass

    _refresh_trade_views(self, ctx["sym"])




def handle_trade_signal(
    self,
    order_info: dict,
    *,
    max_closed_history: int,
    resolve_trigger_indicators,
    normalize_trigger_actions_map,
    save_position_allocations,
) -> None:
    connector_name = _connector_name(self)
    info_with_connector = dict(order_info or {})
    info_with_connector.setdefault("connector", connector_name)
    self.log(f"TRADE UPDATE [{connector_name}]: {info_with_connector}")

    sym = order_info.get("symbol")
    side = order_info.get("side")
    position_side = order_info.get("position_side") or side
    side_for_key = position_side or side
    ctx = {
        "sym": sym,
        "interval": order_info.get("interval"),
        "side_for_key": side_for_key,
        "side_key": _side_key(side_for_key),
        "sym_upper": str(sym or "").strip().upper(),
        "event_type": str(order_info.get("event") or "").lower(),
        "status": str(order_info.get("status") or "").lower(),
        "ok_flag": order_info.get("ok"),
    }

    alloc_map, pending_close = _ensure_trade_maps(self)

    if ctx["event_type"] == "close_interval":
        _handle_close_interval_event(
            self,
            order_info,
            ctx,
            alloc_map=alloc_map,
            pending_close=pending_close,
            max_closed_history=max_closed_history,
            resolve_trigger_indicators=resolve_trigger_indicators,
            normalize_trigger_actions_map=normalize_trigger_actions_map,
            save_position_allocations=save_position_allocations,
        )
        return

    main_window_trade_signal_open_runtime.handle_non_close_trade_signal(
        self,
        order_info,
        ctx,
        alloc_map=alloc_map,
        pending_close=pending_close,
        resolve_trigger_indicators=resolve_trigger_indicators,
        normalize_trigger_actions_map=normalize_trigger_actions_map,
        save_position_allocations=save_position_allocations,
        normalize_interval=_normalize_interval,
        side_key_from_value=_side_key,
        refresh_trade_views=_refresh_trade_views,
        persist_trade_allocations=_persist_trade_allocations,
        sync_open_position_snapshot=_sync_open_position_snapshot,
    )
