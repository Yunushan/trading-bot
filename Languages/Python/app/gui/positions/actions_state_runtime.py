from __future__ import annotations

import copy
import math

from PyQt6 import QtCore

from app.security.redaction import redact_text

from .actions_context_runtime import get_save_position_allocations


def _identity_token(value) -> str:
    return str(value or "").strip()


def _record_positions_action_exception(self, context: str, exc: BaseException) -> None:
    message = redact_text(exc).replace("\n", " ")
    entry = f"positions action suppressed exception context={context} error={type(exc).__name__}: {message}"
    try:
        logger = getattr(self, "_chart_debug_log", None)
    except Exception:
        logger = None
    if callable(logger):
        try:
            logger(entry)
            return
        except Exception:
            logger = None
    try:
        logger = getattr(self, "log", None)
    except Exception:
        logger = None
    if callable(logger):
        try:
            logger(entry)
        except Exception:
            return


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
    if isinstance(value, bool):
        return None
    try:
        qty_value = float(value or 0.0)
    except Exception:
        return None
    if not math.isfinite(qty_value) or qty_value <= 0.0:
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

    strong_keys = [key for key in ("trade_id", "client_order_id", "order_id", "event_uid") if target_identity.get(key)]
    if strong_keys:
        return all(entry_values.get(key) == target_identity[key] for key in strong_keys)

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
    return str(entry.get("status") or "Active").strip().lower() == "active"


def _allocation_reconciliation_pending(self, symbol: str, side_key: str) -> bool:
    pending = getattr(self, "_pending_allocation_reconciliations", None)
    return bool(isinstance(pending, dict) and pending.get((symbol, side_key)))


def _retain_pending_allocation_reconciliation(
    self,
    symbol: str,
    side_key: str,
    *,
    operation: str,
    interval: str | None = None,
    qty: float | None = None,
    target_identity: dict | None = None,
    reason: str | None = None,
    venue_result: dict | None = None,
) -> None:
    """Retain a local reconciliation fence without publishing account payloads."""
    pending = getattr(self, "_pending_allocation_reconciliations", None)
    if not isinstance(pending, dict):
        pending = {}
        self._pending_allocation_reconciliations = pending
    key = (symbol, side_key)
    operations = pending.setdefault(key, [])
    payload = {
        "operation": operation,
        "interval": interval,
        "qty": qty,
        "target_identity": copy.deepcopy(target_identity or {}),
        "reason": reason,
    }
    # The helper and its callback describe the same failed publication. Attach
    # the confirmed venue receipt to that item, retaining distinct later events.
    match = next((item for item in reversed(operations) if all(
        item.get(field) == payload[field] for field in ("operation", "interval", "qty", "target_identity")
    ) and (venue_result is None or item.get("venue_result") is None or item.get("venue_result") == venue_result)), None)
    if match is None:
        match = payload
        operations.append(match)
    if isinstance(venue_result, dict):
        match["venue_result"] = copy.deepcopy(venue_result)


def _publish_position_allocation_snapshot(
    self, allocations: dict, records: dict, *, context: str, event_receipt: dict | None = None,
) -> bool:
    saver = get_save_position_allocations()
    if not callable(saver):
        return False
    try:
        mode = self.mode_combo.currentText() if hasattr(self, "mode_combo") else None
        options = {"mode": mode, "session": getattr(self, "_allocation_snapshot_session", None)}
        if event_receipt is not None:
            options["event_receipt"] = event_receipt
        return saver(allocations, records, **options) is True
    except (AttributeError, OSError, RuntimeError, TypeError, ValueError) as exc:
        _record_positions_action_exception(self, context, exc)
        return False


def _release_closed_allocation_intervals(self, symbol: str, side_key: str, intervals: list[str]) -> None:
    for interval in intervals:
        try:
            if hasattr(self, "_track_interval_close"):
                self._track_interval_close(symbol, side_key, interval)
        except (AttributeError, OSError, RuntimeError, TypeError, ValueError) as exc:
            _record_positions_action_exception(self, "publish_track_interval_close", exc)
    try:
        guard = getattr(self, "guard", None)
        guard_side = "BUY" if side_key == "L" else "SELL"
        if guard and hasattr(guard, "clear_symbol_side"):
            guard.clear_symbol_side(symbol, guard_side, intervals=intervals or None)
        elif guard and hasattr(guard, "mark_closed"):
            for interval in intervals:
                guard.mark_closed(symbol, interval, guard_side)
    except (AttributeError, OSError, RuntimeError, TypeError, ValueError) as exc:
        _record_positions_action_exception(self, "publish_guard_state", exc)


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
    close_result: dict | None = None,
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
        if _allocation_reconciliation_pending(self, sym_upper, side_norm):
            return False

        event_receipt = None
        if close_result is not None:
            receipt_classified = False
            try:
                from trading_core.orders import confirmed_close_quantity

                from app.gui.trade.signal_common_runtime import _trade_event_receipt

                confirmed_qty = confirmed_close_quantity(close_result, qty)
                if confirmed_qty <= 0 or confirmed_qty != _coerce_qty_value(qty):
                    raise ValueError("Manual close quantity does not match its confirmed receipt")
                info = close_result.get("info")
                if not isinstance(info, dict):
                    raise ValueError("Manual close receipt has no exact order identity")
                event_receipt = _trade_event_receipt(
                    {"qty": confirmed_qty, "client_order_id": info.get("clientOrderId"),
                     "order_id": info.get("orderId")},
                    {"sym_upper": sym_upper, "side_key": side_norm}, "SELL",
                )
                session = getattr(self, "_allocation_snapshot_session", None)
                checker = getattr(session, "has_trade_event_receipt", None)
                if callable(checker) and checker(event_receipt) is True:
                    receipt_classified = True
                    return True
                receipt_classified = True
            except (AttributeError, ImportError, OSError, RuntimeError, TypeError, ValueError) as exc:
                _record_positions_action_exception(self, "manual_close_receipt", exc)
                return False
            finally:
                if not receipt_classified:
                    _retain_pending_allocation_reconciliation(
                        self, sym_upper, side_norm, operation="reduce", interval=_normalize_interval_value(self, interval),
                        qty=_coerce_qty_value(qty), target_identity=_close_target_identity(target_identity),
                        reason="confirmed close receipt requires reconciliation", venue_result=close_result,
                    )

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
        if qty is not None and qty_value is None:
            return False
        qty_tol = 1e-9

        def _matches_interval(entry: dict) -> bool:
            if not _allocation_is_active(entry):
                return False
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
            targets = [entry for entry in entries if isinstance(entry, dict) and _allocation_is_active(entry)
                       and _entry_matches_target_identity(entry, target_payload)]
            if len(targets) != 1:
                return False
            available_qty = _coerce_qty_value(targets[0].get("qty"))
            if qty_value is not None and (available_qty is None or qty_value > available_qty + qty_tol):
                return False
            closed_snapshots, survivors, _qty_remaining, matched = _consume_closed_entries(
                entries,
                qty_remaining=qty_value,
                qty_tol=qty_tol,
                close_time_fmt=None,
                matcher=lambda entry: entry is targets[0],
            )

        if not target_payload:
            if qty_value is not None:
                interval_entries = [entry for entry in entries if isinstance(entry, dict) and _matches_interval(entry)]
                available_values = [_coerce_qty_value(entry.get("qty")) for entry in interval_entries]
                if any(value is None for value in available_values):
                    return False
                available_qty = sum(value for value in available_values if value is not None)
                if qty_value > available_qty + qty_tol:
                    return False
            closed_snapshots, survivors, _qty_remaining, matched = _consume_closed_entries(
                entries,
                qty_remaining=qty_value,
                qty_tol=qty_tol,
                close_time_fmt=None,
                matcher=_matches_interval,
            )

        if not matched or (qty_value is not None and _qty_remaining > qty_tol):
            return False

        survivor_entries = [copy.deepcopy(entry) for entry in survivors if isinstance(entry, dict)]
        active_survivors = [entry for entry in survivor_entries if _allocation_is_active(entry)]
        candidate_allocations = copy.deepcopy(alloc_map)
        open_records = getattr(self, "_open_position_records", None)
        candidate_records = copy.deepcopy(open_records) if isinstance(open_records, dict) else {}
        if survivor_entries:
            candidate_allocations[key] = survivor_entries
        else:
            candidate_allocations.pop(key, None)

        record = candidate_records.get(key)
        if active_survivors:
            if not isinstance(record, dict):
                seed = active_survivors[0]
                record = {"symbol": sym_upper, "side_key": side_norm, "status": "Active",
                          "entry_tf": seed.get("interval_display") or seed.get("interval") or "-",
                          "open_time": seed.get("open_time") or "-", "close_time": "-", "data": {}}
                candidate_records[key] = record
            record["allocations"] = copy.deepcopy(active_survivors)
            data = copy.deepcopy(record.get("data")) if isinstance(record.get("data"), dict) else {}
            data["qty"] = sum(abs(float(entry.get("qty") or 0.0)) for entry in active_survivors)
            if data["qty"] > 0:
                weighted_cost = sum(abs(float(entry.get("qty") or 0.0)) * float(entry.get("entry_price") or 0.0)
                                    for entry in active_survivors)
                data["entry_price"] = weighted_cost / data["qty"]
            for field_name in ("margin_usdt", "margin_balance", "notional", "size_usdt"):
                if any(field_name in entry for entry in active_survivors):
                    data[field_name] = sum(float(entry.get(field_name) or 0.0) for entry in active_survivors)
            if any("notional" in entry or "size_usdt" in entry for entry in active_survivors):
                data["size_usdt"] = sum(float(entry.get("size_usdt") or entry.get("notional") or 0.0)
                                        for entry in active_survivors)
            record["data"] = data
        else:
            candidate_records.pop(key, None)

        published = False
        try:
            published = _publish_position_allocation_snapshot(
                self, candidate_allocations, candidate_records, context="reduce_allocation_save",
                event_receipt=event_receipt,
            )
        finally:
            if not published:
                _retain_pending_allocation_reconciliation(
                    self, sym_upper, side_norm, operation="reduce", interval=normalized_interval,
                    qty=qty_value, target_identity=target_payload, reason="allocation publication failed",
                    venue_result=close_result,
                )
        if not published:
            return False

        self._entry_allocations = candidate_allocations
        self._open_position_records = candidate_records

        previous_intervals = {_normalize_interval_value(self, entry.get("interval_display") or entry.get("interval"))
                              for entry in entries if isinstance(entry, dict) and _allocation_is_active(entry)}
        survivor_intervals = {_normalize_interval_value(self, entry.get("interval_display") or entry.get("interval"))
                              for entry in active_survivors}
        removed_intervals = sorted(iv for iv in previous_intervals - survivor_intervals if iv)
        if removed_intervals or not active_survivors:
            _release_closed_allocation_intervals(self, sym_upper, side_norm, removed_intervals)

        sync_local_position_tracking_from_allocations(self, sym_upper, side_norm, active_survivors)
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
        if _allocation_reconciliation_pending(self, sym_upper, side_norm):
            return False
        alloc_map = getattr(self, "_entry_allocations", None)
        open_records = getattr(self, "_open_position_records", None)
        candidate_allocations = copy.deepcopy(alloc_map) if isinstance(alloc_map, dict) else {}
        candidate_records = copy.deepcopy(open_records) if isinstance(open_records, dict) else {}
        changed = key in candidate_allocations or key in candidate_records
        if not changed:
            return False
        candidate_allocations.pop(key, None)
        candidate_records.pop(key, None)

        published = False
        try:
            published = _publish_position_allocation_snapshot(
                self, candidate_allocations, candidate_records, context="clear_save_allocations",
            )
        finally:
            if not published:
                _retain_pending_allocation_reconciliation(
                    self, sym_upper, side_norm, operation="clear", interval=interval, reason=reason,
                )
        if not published:
            return False

        # History/UI callbacks use the old record only after storage succeeds.
        # The storage lock has been released before any guard or ledger callback.
        try:
            self._snapshot_closed_position(sym_upper, side_norm)
        except Exception as exc:
            _record_positions_action_exception(self, "clear_snapshot_closed_position", exc)
        self._entry_allocations = candidate_allocations
        self._open_position_records = candidate_records

        try:
            pending_close = getattr(self, "_pending_close_times", None)
            if isinstance(pending_close, dict):
                pending_close.pop(key, None)
        except Exception as exc:
            _record_positions_action_exception(self, "clear_pending_close_times", exc)

        try:
            missing_counts = getattr(self, "_position_missing_counts", None)
            if isinstance(missing_counts, dict):
                missing_counts.pop(key, None)
        except Exception as exc:
            _record_positions_action_exception(self, "clear_position_missing_counts", exc)

        try:
            entry_times = getattr(self, "_entry_times", None)
            if isinstance(entry_times, dict):
                entry_times.pop(key, None)
        except Exception as exc:
            _record_positions_action_exception(self, "clear_entry_times", exc)

        intervals_to_close: list[str] = []
        try:
            entry_intervals = getattr(self, "_entry_intervals", None)
            if isinstance(entry_intervals, dict):
                side_map = entry_intervals.get(sym_upper)
                if isinstance(side_map, dict):
                    bucket = side_map.get(side_norm)
                    if isinstance(bucket, set):
                        intervals_to_close.extend([str(iv).strip() for iv in bucket if str(iv).strip()])
        except Exception as exc:
            _record_positions_action_exception(self, "clear_collect_intervals", exc)
        if interval:
            iv = str(interval).strip()
            if iv and iv not in intervals_to_close:
                intervals_to_close.append(iv)
        _release_closed_allocation_intervals(self, sym_upper, side_norm, intervals_to_close)
        sync_local_position_tracking_from_allocations(self, sym_upper, side_norm, [])

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
        except Exception as exc:
            _record_positions_action_exception(self, "clear_entry_times_by_interval", exc)

        if changed:
            try:
                self._update_global_pnl_display(*self._compute_global_pnl_totals())
            except Exception as exc:
                _record_positions_action_exception(self, "clear_update_global_pnl_display", exc)
            try:
                self._render_positions_table()
            except Exception as exc:
                _record_positions_action_exception(self, "clear_render_positions_table", exc)
            if reason:
                try:
                    self.log(f"{sym_upper} {side_norm}: cleared stale local position ({reason}).")
                except Exception as exc:
                    _record_positions_action_exception(self, "clear_reason_log", exc)
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
                except Exception as exc:
                    _record_positions_action_exception(self, "sync_chart_market_set_current_text", exc)
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
    except Exception as exc:
        _record_positions_action_exception(self, "sync_chart_to_active_positions", exc)
