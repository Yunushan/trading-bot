from __future__ import annotations

import copy
import time

_MAX_CLOSED_HISTORY = 200
_RESOLVE_TRIGGER_INDICATORS = None
_SAVE_POSITION_ALLOCATIONS = None
_NORMALIZE_TRIGGER_ACTIONS_MAP = None


def _resolve_trigger_indicators_safe(raw, desc: str | None = None) -> list[str]:
    func = _RESOLVE_TRIGGER_INDICATORS
    if not callable(func):
        return []
    try:
        return list(func(raw, desc))
    except Exception:
        return []


def _normalize_trigger_actions_map_safe(raw) -> dict:
    func = _NORMALIZE_TRIGGER_ACTIONS_MAP
    if not callable(func):
        return {}
    try:
        normalized = func(raw) or {}
    except Exception:
        return {}
    return dict(normalized) if isinstance(normalized, dict) else {}


def _save_position_allocations_safe(
    entry_allocations,
    open_position_records,
    *,
    mode=None,
) -> None:
    func = _SAVE_POSITION_ALLOCATIONS
    if not callable(func):
        return
    try:
        func(entry_allocations, open_position_records, mode=mode)
    except Exception:
        pass


def bind_main_window_trade_runtime(
    main_window_cls,
    *,
    resolve_trigger_indicators=None,
    save_position_allocations=None,
    normalize_trigger_actions_map=None,
    max_closed_history: int = 200,
) -> None:
    global _MAX_CLOSED_HISTORY
    global _RESOLVE_TRIGGER_INDICATORS
    global _SAVE_POSITION_ALLOCATIONS
    global _NORMALIZE_TRIGGER_ACTIONS_MAP

    _MAX_CLOSED_HISTORY = max(1, int(max_closed_history))
    _RESOLVE_TRIGGER_INDICATORS = resolve_trigger_indicators
    _SAVE_POSITION_ALLOCATIONS = save_position_allocations
    _NORMALIZE_TRIGGER_ACTIONS_MAP = normalize_trigger_actions_map

    main_window_cls.log = _mw_log
    main_window_cls._trade_mux = _mw_trade_mux
    main_window_cls._on_trade_signal = _mw_on_trade_signal


def _mw_log(self, msg: str):
    try:
        self.log_signal.emit(str(msg))
    except Exception:
        pass


def _mw_trade_mux(self, evt: dict):
    try:
        guard = getattr(self, "guard", None)
        hook = getattr(guard, "trade_hook", None)
        if callable(hook):
            hook(evt)
    except Exception:
        pass
    try:
        self.trade_signal.emit(evt)
    except Exception:
        pass


def _mw_on_trade_signal(self, order_info: dict):
    try:
        connector_name = self._connector_label_text(self._runtime_connector_backend(suppress_refresh=True))
    except Exception:
        connector_name = "Unknown"
    info_with_connector = dict(order_info or {})
    info_with_connector.setdefault("connector", connector_name)
    self.log(f"TRADE UPDATE [{connector_name}]: {info_with_connector}")
    sym = order_info.get("symbol")
    interval = order_info.get("interval")
    side = order_info.get("side")
    position_side = order_info.get("position_side") or side
    event_type = str(order_info.get("event") or "").lower()
    status = str(order_info.get("status") or "").lower()
    ok_flag = order_info.get("ok")
    side_for_key = position_side or side
    side_key = "L" if str(side_for_key).upper() in ("BUY", "LONG") else "S"
    sym_upper = str(sym or "").strip().upper()

    alloc_map = getattr(self, "_entry_allocations", None)
    if alloc_map is None:
        self._entry_allocations = {}
        alloc_map = self._entry_allocations
    pending_close = getattr(self, "_pending_close_times", None)
    if pending_close is None:
        self._pending_close_times = {}
        pending_close = self._pending_close_times

    def _norm_interval(value):
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

    def _sync_open_position_snapshot(
        symbol_key: str,
        side_key_local: str,
        alloc_entries: list | None,
        trade_snapshot: dict | None,
        interval_label: str | None,
        normalized_interval: str | None,
        open_time_fmt: str | None,
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
            normalized_triggers = _resolve_trigger_indicators_safe(
                trade_snapshot.get("trigger_indicators"),
                trigger_desc,
            )
            if normalized_triggers:
                base_data["trigger_indicators"] = normalized_triggers
            normalized_actions = _normalize_trigger_actions_map_safe(
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

    if event_type == "close_interval":
        try:
            if hasattr(self, "_track_interval_close"):
                self._track_interval_close(sym, side_key, interval)
        except Exception:
            pass
        norm_iv = _norm_interval(interval)
        close_time_val_evt = order_info.get("time")
        dt_close_evt = self._parse_any_datetime(close_time_val_evt) if close_time_val_evt else None
        close_time_fmt_evt = self._format_display_time(dt_close_evt) if dt_close_evt else close_time_val_evt
        ledger_id_evt = str(order_info.get("ledger_id") or "").strip()

        def _safe_float_event(value):
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

        qty_reported_evt = _safe_float_event(order_info.get("qty") or order_info.get("executed_qty"))
        if qty_reported_evt is not None:
            qty_reported_evt = abs(qty_reported_evt)
        qty_remaining_evt = qty_reported_evt
        qty_tol_evt = 1e-9

        def _scale_fields(payload: dict, ratio: float) -> None:
            for fld in ("margin_usdt", "margin_balance", "notional", "size_usdt"):
                try:
                    val = float(payload.get(fld) or 0.0)
                except Exception:
                    val = 0.0
                if val > 0.0:
                    payload[fld] = max(0.0, val * ratio)

        def _entry_interval_matches(entry_payload: dict) -> bool:
            entry_iv = _norm_interval(entry_payload.get("interval") or entry_payload.get("interval_display"))
            return norm_iv is None or entry_iv == norm_iv

        def _build_closed_snapshot(entry_payload: dict, qty_closed: float | None = None) -> dict:
            snapshot = copy.deepcopy(entry_payload)
            try:
                entry_qty_val = abs(float(entry_payload.get("qty") or 0.0))
            except Exception:
                entry_qty_val = 0.0
            if qty_closed is not None and entry_qty_val > qty_tol_evt:
                qty_use = max(0.0, min(entry_qty_val, float(qty_closed)))
                ratio_use = qty_use / entry_qty_val if entry_qty_val > 0.0 else 1.0
                snapshot["qty"] = qty_use
                _scale_fields(snapshot, ratio_use)
            if close_time_fmt_evt:
                snapshot["close_time"] = close_time_fmt_evt
            elif not snapshot.get("close_time"):
                snapshot["close_time"] = entry_payload.get("close_time")
            snapshot["status"] = "Closed"
            return snapshot

        closed_snapshots: list[dict] = []
        entries = alloc_map.get((sym_upper, side_key), [])
        if isinstance(entries, dict):
            entries = list(entries.values())
        survivors: list[dict] = []
        matched_by_ledger = False
        if isinstance(entries, list):
            for entry in entries:
                if not isinstance(entry, dict):
                    continue
                entry_ledger = str(entry.get("ledger_id") or "").strip()
                if ledger_id_evt:
                    target_match = bool(entry_ledger and entry_ledger == ledger_id_evt)
                    if target_match:
                        matched_by_ledger = True
                else:
                    target_match = _entry_interval_matches(entry)
                if not target_match:
                    survivors.append(entry)
                    continue
                try:
                    entry_qty = abs(float(entry.get("qty") or 0.0))
                except Exception:
                    entry_qty = 0.0
                if qty_remaining_evt is None:
                    closed_snapshots.append(_build_closed_snapshot(entry))
                    continue
                if qty_remaining_evt <= qty_tol_evt:
                    survivors.append(entry)
                    continue
                qty_used = qty_remaining_evt
                if entry_qty > qty_tol_evt:
                    qty_used = min(entry_qty, qty_remaining_evt)
                if entry_qty > qty_tol_evt and (entry_qty - qty_used) > qty_tol_evt:
                    closed_snapshots.append(_build_closed_snapshot(entry, qty_used))
                    survivor_entry = copy.deepcopy(entry)
                    survivor_qty = max(0.0, entry_qty - qty_used)
                    survivor_entry["qty"] = survivor_qty
                    ratio_remaining = survivor_qty / entry_qty if entry_qty > 0.0 else 1.0
                    _scale_fields(survivor_entry, ratio_remaining)
                    survivors.append(survivor_entry)
                else:
                    closed_snapshots.append(
                        _build_closed_snapshot(entry, qty_used if entry_qty > qty_tol_evt else None)
                    )
                qty_remaining_evt = max(0.0, qty_remaining_evt - max(0.0, qty_used))
        if ledger_id_evt and not matched_by_ledger and isinstance(entries, list):
            closed_snapshots = []
            survivors = []
            qty_remaining_evt = qty_reported_evt
            for entry in entries:
                if not isinstance(entry, dict):
                    continue
                if not _entry_interval_matches(entry):
                    survivors.append(entry)
                    continue
                try:
                    entry_qty = abs(float(entry.get("qty") or 0.0))
                except Exception:
                    entry_qty = 0.0
                if qty_remaining_evt is None:
                    closed_snapshots.append(_build_closed_snapshot(entry))
                    continue
                if qty_remaining_evt <= qty_tol_evt:
                    survivors.append(entry)
                    continue
                qty_used = qty_remaining_evt
                if entry_qty > qty_tol_evt:
                    qty_used = min(entry_qty, qty_remaining_evt)
                if entry_qty > qty_tol_evt and (entry_qty - qty_used) > qty_tol_evt:
                    closed_snapshots.append(_build_closed_snapshot(entry, qty_used))
                    survivor_entry = copy.deepcopy(entry)
                    survivor_qty = max(0.0, entry_qty - qty_used)
                    survivor_entry["qty"] = survivor_qty
                    ratio_remaining = survivor_qty / entry_qty if entry_qty > 0.0 else 1.0
                    _scale_fields(survivor_entry, ratio_remaining)
                    survivors.append(survivor_entry)
                else:
                    closed_snapshots.append(
                        _build_closed_snapshot(entry, qty_used if entry_qty > qty_tol_evt else None)
                    )
                qty_remaining_evt = max(0.0, qty_remaining_evt - max(0.0, qty_used))
        if survivors:
            alloc_map[(sym_upper, side_key)] = survivors
            entries = survivors
        else:
            alloc_map.pop((sym_upper, side_key), None)
            entries = []
        if not closed_snapshots and survivors:
            try:
                seed = copy.deepcopy(survivors[0]) if survivors else {}
            except Exception:
                seed = survivors[0] if survivors else {}
            try:
                seed_interval = seed.get("interval_display") or seed.get("interval") or interval
                seed_norm_iv = _norm_interval(seed_interval) or norm_iv
                seed_open_time = seed.get("open_time")
                _sync_open_position_snapshot(
                    sym_upper,
                    side_key,
                    survivors,
                    seed if isinstance(seed, dict) else None,
                    seed_interval,
                    seed_norm_iv,
                    seed_open_time,
                )
            except Exception:
                pass
            try:
                pending_close.pop((sym_upper, side_key), None)
            except Exception:
                pass
            try:
                _mode = self.mode_combo.currentText() if hasattr(self, "mode_combo") else None
                _save_position_allocations_safe(
                    getattr(self, "_entry_allocations", {}),
                    getattr(self, "_open_position_records", {}),
                    mode=_mode,
                )
            except Exception:
                pass
            self.update_balance_label()
            self.refresh_positions(symbols=[sym] if sym else None)
            return

        try:
            _mode = self.mode_combo.currentText() if hasattr(self, "mode_combo") else None
            _save_position_allocations_safe(
                getattr(self, "_entry_allocations", {}),
                getattr(self, "_open_position_records", {}),
                mode=_mode,
            )
        except Exception:
            pass

        if sym_upper:
            from datetime import datetime as _dt

            close_time_val = order_info.get("time")
            dt_obj = self._parse_any_datetime(close_time_val)
            if dt_obj is None:
                dt_obj = _dt.now().astimezone()
            close_time_fmt = self._format_display_time(dt_obj)
            if close_time_val:
                pending_close[(sym_upper, side_key)] = close_time_fmt
            alloc_entries_snapshot = []
            if closed_snapshots:
                alloc_entries_snapshot = closed_snapshots
                for entry_snap in alloc_entries_snapshot:
                    if not entry_snap.get("close_time"):
                        entry_snap["close_time"] = close_time_fmt
            ledger_id = order_info.get("ledger_id")

            def _safe_float_event(value):
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

            qty_reported = _safe_float_event(order_info.get("qty") or order_info.get("executed_qty"))
            if qty_reported is not None:
                qty_reported = abs(qty_reported)
            close_price_reported = _safe_float_event(
                order_info.get("close_price")
                or order_info.get("avg_price")
                or order_info.get("price")
                or order_info.get("mark_price")
            )
            entry_price_reported = _safe_float_event(order_info.get("entry_price"))
            pnl_reported = _safe_float_event(order_info.get("pnl_value"))
            margin_reported = _safe_float_event(order_info.get("margin_usdt"))
            roi_reported = _safe_float_event(order_info.get("roi_percent"))
            leverage_reported = None
            lev_tmp = _safe_float_event(order_info.get("leverage"))
            if lev_tmp is not None and lev_tmp > 0:
                try:
                    leverage_reported = int(round(lev_tmp))
                except Exception:
                    leverage_reported = None
            processed = getattr(self, "_processed_close_events", None)
            if processed is None:
                processed = set()
                self._processed_close_events = processed
            unique_key = order_info.get("event_id")
            if not unique_key:
                identifier = ledger_id or sym_upper or ""
                qty_token = f"{qty_reported:.8f}" if qty_reported is not None else "0"
                unique_key = f"{identifier}|{close_time_fmt}|{qty_token}|{side_key}"
            if unique_key in processed:
                return
            processed.add(unique_key)
            open_records = getattr(self, "_open_position_records", {}) or {}
            base_record = copy.deepcopy(open_records.get((sym_upper, side_key)))
            if not base_record:
                base_record = {
                    "symbol": sym_upper,
                    "side_key": side_key,
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
                base_qty_curr = float(base_data_snap.get("qty") or 0.0)
                base_margin_curr = float(base_data_snap.get("margin_usdt") or 0.0)
                base_pnl_curr = float(base_data_snap.get("pnl_value") or 0.0)
                base_notional_curr = float(base_data_snap.get("size_usdt") or 0.0)
                alloc_count = len(alloc_entries_snapshot)
                for entry_snap in alloc_entries_snapshot:
                    try:
                        qty_val = abs(float(entry_snap.get("qty") or 0.0))
                    except Exception:
                        qty_val = 0.0
                    qty_total += qty_val
                    margin_val = entry_snap.get("margin_usdt")
                    if (margin_val is None or float(margin_val or 0.0) == 0.0) and base_margin_curr > 0:
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
                        "pnl_value": _safe_float_event(base_data_snap.get("pnl_value")),
                        "margin_usdt": _safe_float_event(base_data_snap.get("margin_usdt")),
                        "roi_percent": _safe_float_event(base_data_snap.get("roi_percent")),
                    }
                    if len(registry) > _MAX_CLOSED_HISTORY:
                        excess = len(registry) - _MAX_CLOSED_HISTORY
                        if excess > 0:
                            for old_key in list(registry.keys())[:excess]:
                                registry.pop(old_key, None)
                try:
                    self._update_global_pnl_display(*self._compute_global_pnl_totals())
                except Exception:
                    pass
            except Exception:
                pass
        try:
            pending_close.pop((sym_upper, side_key), None)
        except Exception:
            pass
        if sym:
            self.traded_symbols.add(sym)
        if sym_upper:
            if survivors:
                try:
                    seed = copy.deepcopy(survivors[0]) if survivors else {}
                except Exception:
                    seed = survivors[0] if survivors else {}
                try:
                    seed_interval = seed.get("interval_display") or seed.get("interval") or interval
                    seed_norm_iv = _norm_interval(seed_interval) or norm_iv
                    seed_open_time = seed.get("open_time")
                    _sync_open_position_snapshot(
                        sym_upper,
                        side_key,
                        survivors,
                        seed if isinstance(seed, dict) else None,
                        seed_interval,
                        seed_norm_iv,
                        seed_open_time,
                    )
                except Exception:
                    pass
            else:
                try:
                    getattr(self, "_open_position_records", {}).pop((sym_upper, side_key), None)
                except Exception:
                    pass
                try:
                    getattr(self, "_position_missing_counts", {}).pop((sym_upper, side_key), None)
                except Exception:
                    pass
        try:
            guard_obj = getattr(self, "guard", None)
            if guard_obj and hasattr(guard_obj, "mark_closed") and sym_upper:
                side_norm = "BUY" if side_key == "L" else "SELL"
                guard_obj.mark_closed(sym_upper, interval, side_norm)
        except Exception:
            pass
        self.update_balance_label()
        self.refresh_positions(symbols=[sym] if sym else None)
        return

    is_success = (status != "error") and (ok_flag is None or ok_flag is True)
    if sym and interval and side_for_key:
        trigger_desc_raw = str(order_info.get("trigger_desc") or "").strip()
        trigger_inds_raw = _resolve_trigger_indicators_safe(
            order_info.get("trigger_indicators"),
            trigger_desc_raw or None,
        )
        fills_meta_raw = order_info.get("fills_meta") or {}
        has_order_identity = bool(
            order_info.get("order_id")
            or order_info.get("client_order_id")
            or order_info.get("clientOrderId")
            or (fills_meta_raw.get("order_id") if isinstance(fills_meta_raw, dict) else None)
        )
        has_trigger_context = bool(trigger_desc_raw or trigger_inds_raw)
        if is_success and status in {"placed", "new"} and (not has_trigger_context) and (not has_order_identity):
            if sym:
                self.traded_symbols.add(sym)
            self.update_balance_label()
            self.refresh_positions(symbols=[sym] if sym else None)
            return
        side_key_local = "L" if str(side_for_key).upper() in ("BUY", "LONG") else "S"
        if is_success and status not in {"error", "failed"}:
            registry = getattr(self, "_processed_open_events", None)
            if not isinstance(registry, dict):
                from collections import deque

                registry = {"order": deque(), "set": set()}
                self._processed_open_events = registry
            queue = registry.setdefault("order", None)
            if queue is None:
                from collections import deque

                queue = registry["order"] = deque()
            registry_set = registry.setdefault("set", set())
            now_ts = time.time()
            while queue and ((now_ts - queue[0][1]) > 600.0 or len(queue) > 400):
                old_key, _ = queue.popleft()
                registry_set.discard(old_key)
            qty_token = ""
            qty_source = order_info.get("executed_qty")
            if qty_source is None:
                qty_source = order_info.get("qty")
            if qty_source is not None:
                try:
                    qty_token = f"{abs(float(qty_source)):.8f}"
                except Exception:
                    qty_token = str(qty_source)
            fills_meta = order_info.get("fills_meta") or {}
            order_id_token = fills_meta.get("order_id") or order_info.get("order_id") or ""
            if order_id_token is None:
                order_id_token = ""
            else:
                order_id_token = str(order_id_token)
            client_order_token = order_info.get("client_order_id") or order_info.get("clientOrderId") or ""
            if client_order_token is None:
                client_order_token = ""
            else:
                client_order_token = str(client_order_token)
            event_uid_token = (
                order_info.get("event_uid") or order_info.get("event_id") or order_info.get("ledger_id") or ""
            )
            if event_uid_token is None:
                event_uid_token = ""
            else:
                event_uid_token = str(event_uid_token).strip()
            interval_token = _norm_interval(interval) or str(interval)
            status_token = str(order_info.get("status") or "").lower()
            time_token = str(order_info.get("time") or "")
            unique_parts = [
                sym_upper,
                side_key_local,
                interval_token,
                str(order_id_token),
                event_uid_token,
                qty_token,
                status_token,
            ]
            if not order_id_token and not event_uid_token:
                unique_parts.append(time_token)
                trigger_sig_token = str(order_info.get("trigger_desc") or "").strip()
                if trigger_sig_token:
                    unique_parts.append(trigger_sig_token)
            unique_key = "|".join(unique_parts)
            if unique_key and unique_key in registry_set:
                return
            if unique_key:
                registry_set.add(unique_key)
                queue.append((unique_key, now_ts))
        if getattr(self, "_is_stopping_engines", False) and status.lower() not in {"closed", "error"}:
            is_success = False
        if is_success:
            tstr = order_info.get("time")
            if not tstr:
                from datetime import datetime

                tstr = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            try:
                if hasattr(self, "_track_interval_open"):
                    self._track_interval_open(sym, side_key_local, interval, tstr)
            except Exception:
                pass

            norm_iv = _norm_interval(interval) or "-"
            try:
                qty_val = abs(float(order_info.get("executed_qty") or order_info.get("qty") or 0.0))
            except Exception:
                qty_val = 0.0
            try:
                price_val = float(order_info.get("avg_price") or order_info.get("price") or 0.0)
            except Exception:
                price_val = 0.0
            try:
                leverage_val = int(float(order_info.get("leverage") or 0.0))
            except Exception:
                leverage_val = 0
            if leverage_val <= 0 and getattr(self, "leverage_spin", None):
                try:
                    leverage_val = int(self.leverage_spin.value())
                except Exception:
                    leverage_val = 0
            entry_price_val = price_val if price_val > 0 else float(order_info.get("price") or 0.0)
            if entry_price_val <= 0:
                entry_price_val = price_val
            if entry_price_val <= 0:
                try:
                    entry_price_val = float(order_info.get("mark_price") or 0.0)
                except Exception:
                    entry_price_val = 0.0
            notional_val = entry_price_val * qty_val if entry_price_val > 0 and qty_val > 0 else 0.0
            if leverage_val > 0 and notional_val > 0:
                margin_val = notional_val / leverage_val
            else:
                margin_val = notional_val
            open_time_val = order_info.get("time") or tstr
            if open_time_val:
                dt_obj = self._parse_any_datetime(open_time_val)
                open_time_fmt = self._format_display_time(dt_obj) if dt_obj else open_time_val
            else:
                open_time_fmt = None
            trigger_inds = _resolve_trigger_indicators_safe(
                order_info.get("trigger_indicators"),
                order_info.get("trigger_desc"),
            )
            trigger_actions = _normalize_trigger_actions_map_safe(order_info.get("trigger_actions"))
            trade_entry = {
                "interval": norm_iv,
                "interval_display": interval,
                "qty": qty_val,
                "entry_price": entry_price_val if entry_price_val > 0 else None,
                "leverage": leverage_val if leverage_val > 0 else None,
                "margin_usdt": margin_val,
                "margin_balance": margin_val,
                "notional": notional_val,
                "symbol": sym_upper,
                "side_key": side_key_local,
                "open_time": open_time_fmt,
                "status": "Active",
                "pnl_value": None,
                "trigger_indicators": list(trigger_inds) if trigger_inds else [],
                "trigger_desc": order_info.get("trigger_desc"),
                "trigger_actions": trigger_actions,
            }
            if order_id_token:
                trade_entry["order_id"] = order_id_token
            if client_order_token:
                trade_entry["client_order_id"] = client_order_token
            order_identifier = client_order_token or order_id_token
            alloc_list = alloc_map.get((sym_upper, side_key_local))
            if isinstance(alloc_list, dict):
                alloc_list = list(alloc_list.values())
            if not isinstance(alloc_list, list):
                alloc_list = []
            existing_entry = None
            if alloc_list:
                for entry in alloc_list:
                    if not isinstance(entry, dict):
                        continue
                    if client_order_token and entry.get("client_order_id") == client_order_token:
                        existing_entry = entry
                        break
                    if order_id_token and str(entry.get("order_id") or "") == order_id_token:
                        existing_entry = entry
                        break
                    if order_identifier and entry.get("trade_id") == order_identifier:
                        existing_entry = entry
                        break
                    if (
                        not order_identifier
                        and entry.get("interval") == norm_iv
                        and list(entry.get("trigger_indicators") or [])
                        == list(trade_entry.get("trigger_indicators") or [])
                        and entry.get("open_time") == open_time_fmt
                    ):
                        existing_entry = entry
                        break
            if existing_entry:
                for key, value in trade_entry.items():
                    if value is None:
                        continue
                    if isinstance(value, (list, tuple, set)) and not value:
                        continue
                    if key == "trade_id" and not order_identifier:
                        continue
                    existing_entry[key] = value
                if order_identifier:
                    existing_entry["trade_id"] = order_identifier
            else:
                if not order_identifier:
                    try:
                        import time as _time

                        seq_len = len(alloc_list)
                        order_identifier = f"{sym_upper}-{side_key_local}-{int(_time.time()*1000)}-{seq_len + 1}"
                    except Exception:
                        order_identifier = f"{sym_upper}-{side_key_local}-{len(alloc_list) + 1}"
                trade_entry["trade_id"] = order_identifier
                alloc_list.append(trade_entry)
                existing_entry = trade_entry
            alloc_map[(sym_upper, side_key_local)] = alloc_list
            pending_close.pop((sym_upper, side_key_local), None)

            try:
                _mode = self.mode_combo.currentText() if hasattr(self, "mode_combo") else None
                _save_position_allocations_safe(
                    getattr(self, "_entry_allocations", {}),
                    getattr(self, "_open_position_records", {}),
                    mode=_mode,
                )
            except Exception:
                pass

            snapshot_entry = existing_entry or trade_entry
            _sync_open_position_snapshot(
                sym_upper,
                side_key_local,
                alloc_list,
                snapshot_entry,
                interval,
                norm_iv,
                open_time_fmt,
            )
        else:
            try:
                if hasattr(self, "_track_interval_close"):
                    self._track_interval_close(sym, side_key_local, interval)
            except Exception:
                pass
    if sym:
        self.traded_symbols.add(sym)
    self.update_balance_label()
    self.refresh_positions(symbols=[sym] if sym else None)
