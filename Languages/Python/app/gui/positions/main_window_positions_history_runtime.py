from __future__ import annotations

import copy
from datetime import datetime

from ...binance_wrapper import normalize_margin_ratio
from . import main_window_positions_history_update_runtime

_CLOSED_HISTORY_MAX = None
_CLOSED_RECORD_STATES: set[str] = set()
_NORMALIZE_INDICATOR_VALUES = None
_DERIVE_MARGIN_SNAPSHOT = None
_RESOLVE_TRIGGER_INDICATORS = None


def configure_main_window_positions_history_runtime(
    *,
    closed_history_max_fn=None,
    closed_record_states=None,
    normalize_indicator_values=None,
    derive_margin_snapshot=None,
    resolve_trigger_indicators=None,
) -> None:
    global _CLOSED_HISTORY_MAX
    global _CLOSED_RECORD_STATES
    global _NORMALIZE_INDICATOR_VALUES
    global _DERIVE_MARGIN_SNAPSHOT
    global _RESOLVE_TRIGGER_INDICATORS

    _CLOSED_HISTORY_MAX = closed_history_max_fn
    _CLOSED_RECORD_STATES = set(closed_record_states or ())
    _NORMALIZE_INDICATOR_VALUES = normalize_indicator_values
    _DERIVE_MARGIN_SNAPSHOT = derive_margin_snapshot
    _RESOLVE_TRIGGER_INDICATORS = resolve_trigger_indicators
    main_window_positions_history_update_runtime.configure_main_window_positions_history_update_runtime(
        closed_history_max_fn=closed_history_max_fn,
        resolve_trigger_indicators=resolve_trigger_indicators,
    )


def _closed_history_max(self) -> int:
    func = _CLOSED_HISTORY_MAX
    if callable(func):
        try:
            return int(func(self))
        except Exception:
            pass
    try:
        cfg_val = int(self.config.get("positions_closed_history_max", 500) or 500)
    except Exception:
        cfg_val = 500
    return max(200, cfg_val)


def _normalize_indicator_values(raw) -> list[str]:
    func = _NORMALIZE_INDICATOR_VALUES
    if not callable(func):
        return []
    try:
        return list(func(raw))
    except Exception:
        return []


def _derive_margin_snapshot(
    position: dict | None,
    qty_hint: float = 0.0,
    entry_price_hint: float = 0.0,
) -> tuple[float, float, float, float]:
    func = _DERIVE_MARGIN_SNAPSHOT
    if not callable(func):
        return (0.0, 0.0, 0.0, 0.0)
    try:
        return func(position, qty_hint=qty_hint, entry_price_hint=entry_price_hint)
    except Exception:
        return (0.0, 0.0, 0.0, 0.0)


def _resolve_trigger_indicators_safe(raw, desc: str | None = None) -> list[str]:
    func = _RESOLVE_TRIGGER_INDICATORS
    if not callable(func):
        return []
    try:
        return list(func(raw, desc))
    except Exception:
        return []


def _mw_positions_records_per_trade(self, open_records: dict, closed_records: list) -> list:
    raw_records: list[dict] = []
    metadata = getattr(self, "_engine_indicator_map", {}) or {}
    meta_map: dict[tuple[str, str], list[dict]] = {}
    for meta in metadata.values():
        if not isinstance(meta, dict):
            continue
        sym = str(meta.get("symbol") or "").strip().upper()
        if not sym:
            continue
        interval = str(meta.get("interval") or "").strip()
        side_cfg = str(meta.get("side") or "BOTH").upper()
        stop_enabled = bool(meta.get("stop_loss_enabled"))
        indicators = list(meta.get("indicators") or [])
        sides = []
        if side_cfg == "BUY":
            sides = ["L"]
        elif side_cfg == "SELL":
            sides = ["S"]
        else:
            sides = ["L", "S"]
        for side in sides:
            meta_map.setdefault((sym, side), []).append(
                {
                    "interval": interval,
                    "indicators": indicators,
                    "stop_loss_enabled": stop_enabled,
                }
            )

    def _normalize_interval(value):
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

    def _collect_allocations(rec: dict) -> list[dict]:
        allocs = rec.get("allocations") or []
        if isinstance(allocs, dict):
            allocs = list(allocs.values())
        if not isinstance(allocs, list):
            return []
        out: list[dict] = []
        for payload in allocs:
            if not isinstance(payload, dict):
                continue
            entry = copy.deepcopy(payload)
            interval = entry.get("interval")
            if interval is None and entry.get("interval_display"):
                interval = entry.get("interval_display")
            entry["interval"] = interval
            triggers_any = entry.get("trigger_indicators")
            if isinstance(triggers_any, dict):
                merged = []
                for value in triggers_any.values():
                    if isinstance(value, (list, tuple, set)):
                        merged.extend([str(v).strip() for v in value if str(v).strip()])
                    elif isinstance(value, str) and value.strip():
                        merged.append(value.strip())
                entry["trigger_indicators"] = merged or None
            out.append(entry)
        unique: list[dict] = []
        seen: dict[tuple, dict] = {}
        for entry in out:
            indicators_tuple = tuple(
                sorted(
                    str(v).strip().lower()
                    for v in (entry.get("trigger_indicators") or [])
                    if str(v).strip()
                )
            )
            key = (
                str(entry.get("ledger_id") or ""),
                str(entry.get("interval") or "").strip().lower(),
                indicators_tuple,
            )
            existing = seen.get(key)
            if existing:
                try:
                    existing["margin_usdt"] = max(
                        float(existing.get("margin_usdt") or 0.0),
                        float(entry.get("margin_usdt") or 0.0),
                    )
                    existing["qty"] = max(
                        float(existing.get("qty") or 0.0),
                        float(entry.get("qty") or 0.0),
                    )
                    existing["notional"] = max(
                        float(existing.get("notional") or 0.0),
                        float(entry.get("notional") or 0.0),
                    )
                except Exception:
                    pass
                continue
            if indicators_tuple:
                entry["trigger_indicators"] = list(indicators_tuple)
            seen[key] = entry
            unique.append(entry)
        return unique

    def _compute_trade_data(base_data: dict, allocation: dict | None, side_key: str, status: str) -> dict:
        data = dict(base_data)
        base_qty = float(base_data.get("qty") or 0.0)
        base_margin = float(base_data.get("margin_usdt") or 0.0)
        base_pnl = float(base_data.get("pnl_value") or 0.0)
        base_roi = float(base_data.get("roi_percent") or 0.0)
        base_size = float(base_data.get("size_usdt") or 0.0)
        mark = float(base_data.get("mark") or 0.0)
        entry_price = float(base_data.get("entry_price") or 0.0)
        leverage = int(base_data.get("leverage") or 0) if base_data.get("leverage") else 0
        base_margin_ratio = normalize_margin_ratio(base_data.get("margin_ratio"))
        base_margin_balance = float(base_data.get("margin_balance") or 0.0)
        base_maint_margin = float(base_data.get("maint_margin") or 0.0)

        qty = base_qty
        margin = base_margin
        notional = base_size
        status_lower = str(status or "").strip().lower()
        pnl = base_pnl
        margin_ratio = 0.0
        margin_balance_val = 0.0
        maint_margin_val = 0.0
        base_liq_price = None

        def _extract_liq_value(candidate):
            try:
                if candidate is None or candidate == "":
                    return None
                value = float(candidate)
                return value if value > 0.0 else None
            except Exception:
                return None

        for cand in (
            base_data.get("liquidation_price"),
            base_data.get("liquidationPrice"),
            base_data.get("liq_price"),
            base_data.get("liqPrice"),
        ):
            found = _extract_liq_value(cand)
            if found:
                base_liq_price = found
                break
        if not base_liq_price:
            raw_base = base_data.get("raw_position") if isinstance(base_data.get("raw_position"), dict) else None
            if raw_base:
                for cand in (raw_base.get("liquidationPrice"), raw_base.get("liqPrice")):
                    found = _extract_liq_value(cand)
                    if found:
                        base_liq_price = found
                        break

        if allocation:
            try:
                qty = abs(float(allocation.get("qty") or 0.0))
            except Exception:
                qty = max(base_qty, 0.0)
            try:
                entry_price_alloc = float(allocation.get("entry_price") or 0.0)
                if entry_price_alloc > 0:
                    entry_price = entry_price_alloc
            except Exception:
                pass
            try:
                leverage_alloc = int(allocation.get("leverage") or 0)
                if leverage_alloc:
                    leverage = leverage_alloc
            except Exception:
                pass
            try:
                margin = float(allocation.get("margin_usdt") or 0.0)
            except Exception:
                margin = 0.0
            try:
                notional = float(allocation.get("notional") or 0.0)
            except Exception:
                notional = 0.0
            if base_liq_price is None:
                for cand in (
                    allocation.get("liquidation_price"),
                    allocation.get("liquidationPrice"),
                    allocation.get("liq_price"),
                    allocation.get("liqPrice"),
                ):
                    found = _extract_liq_value(cand)
                    if found:
                        base_liq_price = found
                        break
            alloc_pnl = allocation.get("pnl_value")
            if alloc_pnl is not None:
                try:
                    pnl = float(alloc_pnl)
                except Exception:
                    pnl = base_pnl
            if allocation.get("status"):
                status_lower = str(allocation.get("status")).strip().lower()
        allocation_data = allocation if isinstance(allocation, dict) else {}
        margin_ratio = normalize_margin_ratio(allocation_data.get("margin_ratio"))
        try:
            margin_balance_val = float(allocation_data.get("margin_balance") or 0.0)
        except Exception:
            margin_balance_val = 0.0
        try:
            maint_margin_val = float(allocation_data.get("maint_margin") or 0.0)
        except Exception:
            maint_margin_val = 0.0

        qty = max(qty, 0.0)
        if notional <= 0:
            if entry_price > 0 and qty > 0:
                notional = entry_price * qty
            elif mark > 0 and qty > 0:
                notional = mark * qty
            elif base_size > 0 and base_qty > 0:
                notional = base_size * (qty / base_qty)
            else:
                notional = 0.0

        if margin <= 0:
            if leverage and leverage > 0 and entry_price > 0 and qty > 0:
                margin = (entry_price * qty) / leverage
            elif base_margin > 0 and base_qty > 0:
                margin = base_margin * (qty / base_qty)
            else:
                margin = 0.0
        margin = max(margin, 0.0)

        if status_lower == "active":
            if allocation is None or allocation.get("pnl_value") is None:
                direction = 1.0 if side_key == "L" else -1.0 if side_key == "S" else 0.0
                if direction != 0.0 and entry_price > 0 and mark > 0 and qty > 0:
                    pnl = direction * (mark - entry_price) * qty
                elif base_pnl and base_qty > 0:
                    pnl = base_pnl * (qty / base_qty)
        else:
            if allocation is None or allocation.get("pnl_value") is None:
                if base_pnl and base_qty > 0:
                    pnl = base_pnl * (qty / base_qty)
                else:
                    pnl = base_pnl

        roi_percent = (pnl / margin * 100.0) if margin > 0 else base_roi
        pnl_roi = f"{pnl:+.2f} USDT ({roi_percent:+.2f}%)" if margin > 0 else f"{pnl:+.2f} USDT"

        raw_position = base_data.get("raw_position") if isinstance(base_data.get("raw_position"), dict) else None
        if margin_ratio <= 0.0:
            margin_ratio = base_margin_ratio
        if margin_balance_val <= 0.0:
            margin_balance_val = base_margin_balance
        if maint_margin_val <= 0.0:
            maint_margin_val = base_maint_margin
        if margin_ratio <= 0.0 and raw_position is not None:
            snap_margin, snap_balance, snap_maint, snap_unreal_loss = _derive_margin_snapshot(
                raw_position,
                qty_hint=qty if qty > 0 else base_qty,
                entry_price_hint=entry_price if entry_price > 0 else base_data.get("entry_price") or 0.0,
            )
            if margin <= 0.0 and snap_margin > 0.0:
                margin = snap_margin
            if margin_balance_val <= 0.0 and snap_balance > 0.0:
                margin_balance_val = snap_balance
            if maint_margin_val <= 0.0 and snap_maint > 0.0:
                maint_margin_val = snap_maint
            if margin_ratio <= 0.0 and snap_balance > 0.0 and snap_maint > 0.0:
                margin_ratio = ((snap_maint + snap_unreal_loss) / snap_balance) * 100.0
        if margin_balance_val <= 0.0:
            margin_balance_val = margin + max(pnl, 0.0)
        margin_balance_val = max(margin_balance_val, 0.0)
        if margin_ratio <= 0.0 and margin_balance_val > 0 and maint_margin_val > 0.0:
            unrealized_loss = max(0.0, -pnl) if status_lower == "active" else 0.0
            margin_ratio = ((maint_margin_val + unrealized_loss) / margin_balance_val) * 100.0

        data.update(
            {
                "qty": qty,
                "margin_usdt": margin,
                "pnl_value": pnl,
                "roi_percent": roi_percent,
                "pnl_roi": pnl_roi,
                "size_usdt": max(notional, 0.0),
                "margin_balance": max(margin_balance_val, 0.0),
                "maint_margin": max(0.0, maint_margin_val),
                "margin_ratio": max(margin_ratio, 0.0),
            }
        )
        trigger_inds = []
        if allocation and isinstance(allocation.get("trigger_indicators"), (list, tuple, set)):
            trigger_inds = [
                str(ind).strip()
                for ind in allocation.get("trigger_indicators")
                if str(ind).strip()
            ]
        elif isinstance(base_data.get("trigger_indicators"), (list, tuple, set)):
            trigger_inds = [
                str(ind).strip()
                for ind in base_data.get("trigger_indicators")
                if str(ind).strip()
            ]
        if trigger_inds:
            trigger_inds = list(dict.fromkeys(trigger_inds))
            data["trigger_indicators"] = trigger_inds
        if entry_price > 0:
            data["entry_price"] = entry_price
        if leverage:
            data["leverage"] = leverage
        if base_liq_price:
            data["liquidation_price"] = base_liq_price
        if allocation and isinstance(allocation, dict) and allocation.get("trigger_desc"):
            data["trigger_desc"] = allocation.get("trigger_desc")
        elif base_data.get("trigger_desc") and not data.get("trigger_desc"):
            data["trigger_desc"] = base_data.get("trigger_desc")
        return data

    def _emit_entries(base_rec: dict, sym: str, side_key: str, meta_items: list[dict | None]) -> None:
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
            alloc_data = _compute_trade_data(base_data, allocation, side_key, alloc_status)
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
            normalized_inds = _normalize_indicator_values(
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
            indicator_values = _normalize_indicator_values(indicator_source)
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
                norm_iv = _normalize_interval(interval_label)
                matching_meta = None
                if norm_iv is not None:
                    for meta in meta_items:
                        if isinstance(meta, dict) and _normalize_interval(meta.get("interval")) == norm_iv:
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

    for (sym, side_key), rec in open_records.items():
        meta_items = meta_map.get((sym, side_key)) or [None]
        _emit_entries(rec, sym, side_key, meta_items)

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
        _emit_entries(rec, sym, side_key, meta_items)

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

    def _qty_key(entry: dict) -> float:
        try:
            return abs(float((entry.get("data") or {}).get("qty") or 0.0))
        except Exception:
            return 0.0

    def _close_time_key(entry: dict) -> datetime:
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

    records = []
    for (_sym, _side, _interval, _indicators), status_map in grouped.items():
        if not isinstance(status_map, dict):
            continue
        active_entries = status_map.get("active") or status_map.get("open") or []
        if active_entries:
            chosen_active = max(active_entries, key=_qty_key)
            records.append(chosen_active)
        closed_entries = (status_map.get("closed") or [])[:]
        closed_entries.sort(key=_close_time_key, reverse=True)
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

    deduped: list[dict] = []
    seen_closed: dict[str, dict] = {}
    for entry in records:
        data = entry.get("data") or {}
        status_flag = str(entry.get("status") or data.get("status") or "").strip().lower()
        is_closed = status_flag in _CLOSED_RECORD_STATES
        if is_closed:
            key = _close_key(entry)
            existing = seen_closed.get(key)
            if existing:
                _merge_interval_labels(existing, entry)
                continue
            seen_closed[key] = entry
        deduped.append(entry)
    records = deduped

    for entry in records:
        entry["_aggregated_entries"] = [entry]
    return records


def _mw_update_position_history(self, positions_map: dict):
    return main_window_positions_history_update_runtime._mw_update_position_history(
        self,
        positions_map,
    )
