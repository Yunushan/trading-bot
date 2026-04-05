from __future__ import annotations

import copy

from PyQt6 import QtCore

from .actions_context_runtime import get_save_position_allocations


def _identity_token(value) -> str:
    return str(value or "").strip()


def _close_target_identity(payload: dict | None) -> dict[str, str]:
    if not isinstance(payload, dict):
        return {}
    normalized: dict[str, str] = {}
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
        value = _identity_token(payload.get(field_name))
        if value:
            normalized[field_name] = value
    return normalized


def _normalize_interval_value(self, value) -> str | None:
    if value is None:
        return None
    try:
        canon = self._canonicalize_interval(value)
    except Exception:
        canon = None
    if canon:
        text = str(canon).strip()
        return text or None
    text = str(value).strip()
    return text or None


def _coerce_qty_value(value) -> float | None:
    try:
        qty_value = abs(float(value or 0.0))
    except Exception:
        return None
    if qty_value <= 0.0:
        return None
    return qty_value


def _entry_matches_target_identity(entry: dict, target_identity: dict[str, str]) -> bool:
    if not isinstance(entry, dict) or not target_identity:
        return False

    fills_meta = entry.get("fills_meta")
    fills_order_id = ""
    if isinstance(fills_meta, dict):
        fills_order_id = _identity_token(fills_meta.get("order_id"))

    entry_values = {
        "trade_id": _identity_token(entry.get("trade_id")),
        "client_order_id": _identity_token(entry.get("client_order_id")),
        "order_id": _identity_token(entry.get("order_id")) or fills_order_id,
        "event_uid": _identity_token(entry.get("event_uid")),
        "context_key": _identity_token(entry.get("context_key")),
        "slot_id": _identity_token(entry.get("slot_id")),
        "open_time": _identity_token(entry.get("open_time")),
    }

    for key_name in ("trade_id", "client_order_id", "order_id", "event_uid"):
        target_value = target_identity.get(key_name)
        if target_value and entry_values.get(key_name) == target_value:
            return True

    target_slot = target_identity.get("slot_id")
    if target_slot and entry_values.get("slot_id") == target_slot:
        target_context = target_identity.get("context_key")
        entry_context = entry_values.get("context_key")
        if target_context and entry_context and entry_context != target_context:
            return False
        return True

    target_context = target_identity.get("context_key")
    if target_context and entry_values.get("context_key") == target_context:
        target_open_time = target_identity.get("open_time")
        entry_open_time = entry_values.get("open_time")
        if target_open_time and entry_open_time and entry_open_time != target_open_time:
            return False
        return True

    target_open_time = target_identity.get("open_time")
    if target_open_time and entry_values.get("open_time") == target_open_time:
        return True

    return False


def _allocation_is_active(entry: dict) -> bool:
    if not isinstance(entry, dict):
        return False
    status_flag = str(entry.get("status") or "").strip().lower()
    if status_flag in {"closed", "error"}:
        try:
            qty_val = abs(float(entry.get("qty") or 0.0))
        except Exception:
            qty_val = 0.0
        return qty_val > 0.0
    return True


def sync_local_position_tracking_from_allocations(
    self,
    symbol: str,
    side_key: str,
    allocations: list[dict],
) -> None:
    sym_upper = str(symbol or "").strip().upper()
    side_norm = str(side_key or "").strip().upper()
    if not sym_upper or side_norm not in ("L", "S"):
        return

    entry_intervals = getattr(self, "_entry_intervals", None)
    if not isinstance(entry_intervals, dict):
        entry_intervals = {}
        self._entry_intervals = entry_intervals
    side_map = entry_intervals.setdefault(sym_upper, {"L": set(), "S": set()})
    if not isinstance(side_map, dict):
        side_map = {"L": set(), "S": set()}
        entry_intervals[sym_upper] = side_map
    bucket = side_map.setdefault(side_norm, set())
    if not isinstance(bucket, set):
        bucket = set()
        side_map[side_norm] = bucket
    bucket.clear()

    entry_times_by_iv = getattr(self, "_entry_times_by_iv", None)
    if not isinstance(entry_times_by_iv, dict):
        entry_times_by_iv = {}
        self._entry_times_by_iv = entry_times_by_iv
    for iv_key in list(entry_times_by_iv.keys()):
        try:
            sym_key, side_key_iv, _ = iv_key
        except Exception:
            continue
        if str(sym_key or "").strip().upper() == sym_upper and str(side_key_iv or "").strip().upper() == side_norm:
            entry_times_by_iv.pop(iv_key, None)

    entry_times = getattr(self, "_entry_times", None)
    if not isinstance(entry_times, dict):
        entry_times = {}
        self._entry_times = entry_times

    earliest_overall_epoch: float | None = None
    earliest_overall_raw = None
    earliest_by_interval: dict[str, tuple[float, object]] = {}

    for entry in allocations or []:
        if not _allocation_is_active(entry):
            continue
        interval_value = _normalize_interval_value(
            self,
            entry.get("interval_display") or entry.get("interval"),
        )
        if interval_value:
            bucket.add(interval_value)

        open_time_raw = entry.get("open_time")
        dt_value = None
        if open_time_raw:
            try:
                dt_value = self._parse_any_datetime(open_time_raw)
            except Exception:
                dt_value = None
        if dt_value is None:
            continue
        try:
            epoch_value = float(dt_value.timestamp())
        except Exception:
            continue
        if earliest_overall_epoch is None or epoch_value < earliest_overall_epoch:
            earliest_overall_epoch = epoch_value
            earliest_overall_raw = open_time_raw
        if interval_value:
            previous = earliest_by_interval.get(interval_value)
            if previous is None or epoch_value < previous[0]:
                earliest_by_interval[interval_value] = (epoch_value, open_time_raw)

    if earliest_overall_raw is not None:
        entry_times[(sym_upper, side_norm)] = earliest_overall_raw
    else:
        entry_times.pop((sym_upper, side_norm), None)

    for interval_value, (_epoch_value, raw_value) in earliest_by_interval.items():
        entry_times_by_iv[(sym_upper, side_norm, interval_value)] = raw_value

    if not bucket:
        side_map[side_norm] = set()
        if not side_map.get("L") and not side_map.get("S"):
            entry_intervals.pop(sym_upper, None)


def reduce_local_position_allocation_state(
    self,
    symbol: str,
    side_key: str,
    *,
    interval: str | None = None,
    qty: float | None = None,
    target_identity: dict | None = None,
) -> bool:
    try:
        from app.gui.trade.signal_close_allocations_runtime import _consume_closed_entries
    except Exception:
        return False

    try:
        sym_upper = str(symbol or "").strip().upper()
        side_norm = str(side_key or "").strip().upper()
        if not sym_upper or side_norm not in ("L", "S"):
            return False
        key = (sym_upper, side_norm)

        alloc_map = getattr(self, "_entry_allocations", None)
        if not isinstance(alloc_map, dict):
            return False
        entries = alloc_map.get(key)
        if isinstance(entries, dict):
            entries = list(entries.values())
        if not isinstance(entries, list) or not entries:
            return False

        target_payload = _close_target_identity(target_identity)
        normalized_interval = _normalize_interval_value(self, interval)
        qty_value = _coerce_qty_value(qty)
        qty_tol = 1e-9

        def _matches_interval(entry: dict) -> bool:
            if not normalized_interval:
                return True
            entry_interval = _normalize_interval_value(
                self,
                entry.get("interval_display") or entry.get("interval"),
            )
            return bool(entry_interval and entry_interval == normalized_interval)

        closed_snapshots: list[dict] = []
        survivors: list[dict] = list(entries)
        matched = False
        if target_payload:
            closed_snapshots, survivors, _qty_remaining, matched = _consume_closed_entries(
                entries,
                qty_remaining=qty_value,
                qty_tol=qty_tol,
                close_time_fmt=None,
                matcher=lambda entry: _entry_matches_target_identity(entry, target_payload),
            )

        if not matched:
            closed_snapshots, survivors, _qty_remaining, matched = _consume_closed_entries(
                entries,
                qty_remaining=qty_value,
                qty_tol=qty_tol,
                close_time_fmt=None,
                matcher=_matches_interval,
            )

        if not matched:
            return False

        survivor_entries = [copy.deepcopy(entry) for entry in survivors if isinstance(entry, dict)]
        if survivor_entries:
            alloc_map[key] = survivor_entries
        else:
            alloc_map.pop(key, None)

        open_records = getattr(self, "_open_position_records", None)
        if isinstance(open_records, dict):
            record = open_records.get(key)
            if survivor_entries:
                if isinstance(record, dict):
                    record["allocations"] = copy.deepcopy(survivor_entries)
            else:
                open_records.pop(key, None)

        sync_local_position_tracking_from_allocations(self, sym_upper, side_norm, survivor_entries)

        saver = get_save_position_allocations()
        if callable(saver):
            try:
                mode_value = self.mode_combo.currentText() if hasattr(self, "mode_combo") else None
                saver(
                    getattr(self, "_entry_allocations", {}),
                    getattr(self, "_open_position_records", {}),
                    mode=mode_value,
                )
            except Exception:
                pass
        return bool(closed_snapshots or survivor_entries != entries)
    except Exception:
        return False


def clear_local_position_state(
    self,
    symbol: str,
    side_key: str,
    *,
    interval: str | None = None,
    reason: str | None = None,
) -> bool:
    """Remove a stale local position/allocations snapshot for a single futures side."""
    try:
        sym_upper = str(symbol or "").strip().upper()
        side_norm = str(side_key or "").strip().upper()
        if not sym_upper or side_norm not in ("L", "S"):
            return False
        key = (sym_upper, side_norm)
        changed = False

        try:
            changed = bool(self._snapshot_closed_position(sym_upper, side_norm)) or changed
        except Exception:
            pass

        try:
            open_records = getattr(self, "_open_position_records", None)
            if isinstance(open_records, dict) and key in open_records:
                open_records.pop(key, None)
                changed = True
        except Exception:
            pass

        try:
            alloc_map = getattr(self, "_entry_allocations", None)
            if isinstance(alloc_map, dict) and key in alloc_map:
                alloc_map.pop(key, None)
                changed = True
        except Exception:
            pass

        try:
            pending_close = getattr(self, "_pending_close_times", None)
            if isinstance(pending_close, dict):
                pending_close.pop(key, None)
        except Exception:
            pass

        try:
            missing_counts = getattr(self, "_position_missing_counts", None)
            if isinstance(missing_counts, dict):
                missing_counts.pop(key, None)
        except Exception:
            pass

        try:
            entry_times = getattr(self, "_entry_times", None)
            if isinstance(entry_times, dict):
                entry_times.pop(key, None)
        except Exception:
            pass

        intervals_to_close: list[str] = []
        try:
            entry_intervals = getattr(self, "_entry_intervals", None)
            if isinstance(entry_intervals, dict):
                side_map = entry_intervals.get(sym_upper)
                if isinstance(side_map, dict):
                    bucket = side_map.get(side_norm)
                    if isinstance(bucket, set):
                        intervals_to_close.extend([str(iv).strip() for iv in bucket if str(iv).strip()])
        except Exception:
            pass
        if interval:
            iv = str(interval).strip()
            if iv and iv not in intervals_to_close:
                intervals_to_close.append(iv)
        if intervals_to_close and hasattr(self, "_track_interval_close"):
            for iv in intervals_to_close:
                try:
                    self._track_interval_close(sym_upper, side_norm, iv)
                except Exception:
                    continue

        try:
            iv_times = getattr(self, "_entry_times_by_iv", None)
            if isinstance(iv_times, dict):
                for iv_key in list(iv_times.keys()):
                    try:
                        sym_key, side_key_key, _iv = iv_key
                    except Exception:
                        continue
                    if str(sym_key or "").strip().upper() == sym_upper and str(side_key_key or "").strip().upper() == side_norm:
                        iv_times.pop(iv_key, None)
        except Exception:
            pass

        try:
            guard_obj = getattr(self, "guard", None)
            if guard_obj and hasattr(guard_obj, "mark_closed"):
                guard_side = "BUY" if side_norm == "L" else "SELL"
                if hasattr(guard_obj, "clear_symbol_side"):
                    clear_intervals = intervals_to_close if intervals_to_close else None
                    guard_obj.clear_symbol_side(sym_upper, guard_side, intervals=clear_intervals)
                elif intervals_to_close:
                    for tracked_interval in intervals_to_close:
                        guard_obj.mark_closed(sym_upper, tracked_interval, guard_side)
                else:
                    guard_obj.mark_closed(sym_upper, interval, guard_side)
        except Exception:
            pass

        if changed:
            saver = get_save_position_allocations()
            if callable(saver):
                try:
                    mode_value = self.mode_combo.currentText() if hasattr(self, "mode_combo") else None
                    saver(
                        getattr(self, "_entry_allocations", {}),
                        getattr(self, "_open_position_records", {}),
                        mode=mode_value,
                    )
                except Exception:
                    pass
            try:
                self._update_global_pnl_display(*self._compute_global_pnl_totals())
            except Exception:
                pass
            try:
                self._render_positions_table()
            except Exception:
                pass
            if reason:
                try:
                    self.log(f"{sym_upper} {side_norm}: cleared stale local position ({reason}).")
                except Exception:
                    pass
        return changed
    except Exception:
        return False


def sync_chart_to_active_positions(self):
    try:
        if not getattr(self, "chart_enabled", False):
            return
        open_records = getattr(self, "_open_position_records", {}) or {}
        if not open_records:
            return
        active_syms = []
        for rec in open_records.values():
            try:
                if str(rec.get("status", "Active")).upper() != "ACTIVE":
                    continue
                sym = str(rec.get("symbol") or "").strip().upper()
                if sym:
                    active_syms.append(sym)
            except Exception:
                continue
        if not active_syms:
            return
        target_sym = active_syms[0]
        market_combo = getattr(self, "chart_market_combo", None)
        if market_combo is None:
            return
        current_market = self._normalize_chart_market(market_combo.currentText())
        if current_market != "Futures":
            try:
                idx = market_combo.findText("Futures", QtCore.Qt.MatchFlag.MatchFixedString)
                if idx >= 0:
                    market_combo.setCurrentIndex(idx)
                else:
                    market_combo.addItem("Futures")
                    market_combo.setCurrentIndex(market_combo.count() - 1)
            except Exception:
                try:
                    market_combo.setCurrentText("Futures")
                except Exception:
                    pass
            return
        display_sym = self._futures_display_symbol(target_sym)
        cache = self.chart_symbol_cache.setdefault("Futures", [])
        if target_sym not in cache:
            cache.append(target_sym)
        alias_map = getattr(self, "_chart_symbol_alias_map", None)
        if not isinstance(alias_map, dict):
            alias_map = {}
            self._chart_symbol_alias_map = alias_map
        futures_alias = alias_map.setdefault("Futures", {})
        futures_alias[display_sym] = target_sym
        self._update_chart_symbol_options(cache)
        changed = self._set_chart_symbol(display_sym, ensure_option=True, from_follow=True)
        if changed or self._chart_needs_render or self._is_chart_visible():
            self.load_chart(auto=True)
    except Exception:
        pass
