from __future__ import annotations

import re
import time

def _segment_matches_indicator_context(self, indicator_key: str | None, segment: str) -> bool:
    key_norm = self._canonical_indicator_token(indicator_key) or str(indicator_key or "").strip().lower()
    if not key_norm:
        return False
    seg_low = str(segment or "").lower()
    if not seg_low:
        return False
    seg_token = re.sub(r"[^a-z0-9]", "", seg_low)
    if key_norm == "stoch_rsi":
        return "stochrsi" in seg_token or "stochasticrsi" in seg_token
    if key_norm == "rsi":
        return (
            "rsi" in seg_token
            and "stochrsi" not in seg_token
            and "stochasticrsi" not in seg_token
        )
    if key_norm == "willr":
        return ("williams" in seg_low) or ("%r" in seg_low)
    if key_norm == "ma":
        return "ma_" in seg_low or "ma crossover" in seg_low or seg_low.startswith("ma")
    token = key_norm.replace("_", "")
    return token in seg_token if token else False


def _build_trigger_desc_for_order(
    self,
    indicator_key: str | None,
    side_value: str | None,
    trigger_segments: list[str] | None,
    trigger_desc: str | None,
) -> str:
    side_upper = str(side_value or "").upper()
    action_suffix = f"-> {side_upper}" if side_upper in {"BUY", "SELL"} else ""
    indicator_norm = self._canonical_indicator_token(indicator_key) or str(indicator_key or "").strip().lower()
    if not indicator_norm or not trigger_segments:
        return str(trigger_desc or "")
    matched_segments = [
        segment
        for segment in trigger_segments
        if self._segment_matches_indicator_context(indicator_norm, segment)
    ]
    if not matched_segments:
        return str(trigger_desc or "")
    selected: list[str] = []
    value_segment = next((seg for seg in matched_segments if "->" not in seg), None)
    if value_segment:
        selected.append(value_segment)
    action_segment = None
    for seg in matched_segments:
        if "->" not in seg:
            continue
        if action_suffix and action_suffix in seg.upper():
            action_segment = seg
            break
        if action_segment is None:
            action_segment = seg
    if action_segment:
        selected.append(action_segment)
    if action_suffix and not action_segment:
        selected.append(f"{indicator_norm.upper()} {action_suffix}")
    selected = list(dict.fromkeys(selected))
    return " | ".join(selected) if selected else str(trigger_desc or "")


def _normalize_order_trigger_actions(
    self,
    raw_actions,
    indicator_key: str | None,
    side_value: str | None,
) -> dict[str, str]:
    normalized: dict[str, str] = {}
    if isinstance(raw_actions, dict):
        for raw_key, raw_action in raw_actions.items():
            key_norm = self._canonical_indicator_token(raw_key) or str(raw_key or "").strip().lower()
            action_norm = str(raw_action or "").strip().lower()
            if key_norm and action_norm in {"buy", "sell"}:
                normalized[key_norm] = action_norm
    indicator_norm = self._canonical_indicator_token(indicator_key) or str(indicator_key or "").strip().lower()
    if indicator_norm and indicator_norm not in normalized:
        side_norm = str(side_value or "").upper()
        if side_norm in {"BUY", "SELL"}:
            normalized[indicator_norm] = side_norm.lower()
    return normalized


def _build_signal_order_candidates(
    self,
    *,
    cw,
    indicator_order_requests,
    signal,
    signal_timestamp,
    trigger_sources,
    trigger_desc,
    trigger_actions,
    trigger_segments,
) -> list[dict[str, object]]:
    base_trigger_labels = list(dict.fromkeys(trigger_sources or []))
    base_signature = tuple(sorted(base_trigger_labels))
    orders_to_execute: list[dict[str, object]] = []
    if indicator_order_requests:
        order_ts = signal_timestamp or time.time()
        seen_signatures: set[tuple[str, ...]] = set()
        for request in indicator_order_requests:
            side_value = str(request.get("side") or "").upper()
            if side_value not in ("BUY", "SELL"):
                continue
            raw_labels = [
                str(lbl).strip()
                for lbl in (request.get("labels") or [])
                if str(lbl or "").strip()
            ]
            label_list = raw_labels or [side_value.lower()]
            signature_parts = tuple(
                str(part).strip().lower()
                for part in (request.get("signature") or ())
                if str(part or "").strip()
            )
            signature = signature_parts or tuple(sorted(lbl.lower() for lbl in label_list))
            indicator_key_request = self._canonical_indicator_token(request.get("indicator_key")) or None
            if not indicator_key_request:
                if signature:
                    indicator_key_request = self._canonical_indicator_token(signature[0]) or signature[0]
                elif label_list:
                    indicator_key_request = (
                        self._canonical_indicator_token(label_list[0]) or str(label_list[0]).strip().lower()
                    )
            request_trigger_actions = self._normalize_order_trigger_actions(
                request.get("trigger_actions"),
                indicator_key_request,
                side_value,
            )
            request_trigger_desc = str(request.get("trigger_desc") or "").strip()
            if not request_trigger_desc:
                request_trigger_desc = self._build_trigger_desc_for_order(
                    indicator_key_request,
                    side_value,
                    trigger_segments,
                    trigger_desc,
                )
            if not request_trigger_desc:
                request_trigger_desc = str(trigger_desc or "")
            if self._symbol_signature_active(cw["symbol"], side_value, signature, cw.get("interval")):
                try:
                    self.log(f"{cw['symbol']}@{cw.get('interval')} {side_value} skipped: signature active on this bar.")
                except Exception:
                    pass
                continue
            if signature in seen_signatures:
                continue
            seen_signatures.add(signature)
            orders_to_execute.append(
                {
                    "side": side_value,
                    "labels": label_list,
                    "signature": signature,
                    "timestamp": request.get("timestamp") or order_ts,
                    "indicator_key": request.get("indicator_key"),
                    "flip_from": request.get("flip_from"),
                    "flip_qty": request.get("flip_qty"),
                    "flip_qty_target": request.get("flip_qty_target"),
                    "trigger_desc": request_trigger_desc,
                    "trigger_actions": request_trigger_actions,
                }
            )
    elif signal:
        fallback_trigger_actions = self._normalize_order_trigger_actions(
            trigger_actions,
            None,
            str(signal).upper(),
        )
        orders_to_execute.append(
            {
                "side": str(signal).upper(),
                "labels": base_trigger_labels,
                "signature": base_signature,
                "timestamp": signal_timestamp,
                "trigger_desc": str(trigger_desc or ""),
                "trigger_actions": fallback_trigger_actions,
            }
        )
    return orders_to_execute


def _is_futures_position_active_for_order(
    self,
    symbol: str,
    side: str,
    dual_side: bool,
    entries: list[dict] | None,
) -> bool:
    symbol_norm = str(symbol or "").upper()
    side_is_long = str(side or "").upper() == "BUY"
    for pos in entries or []:
        try:
            if str(pos.get("symbol") or "").upper() != symbol_norm:
                continue
            amt = float(pos.get("positionAmt") or 0.0)
            if dual_side:
                pos_side = str(pos.get("positionSide") or "").upper()
                if side_is_long and pos_side == "LONG" and amt > 1e-9:
                    return True
                if (not side_is_long) and pos_side == "SHORT" and abs(amt) > 1e-9:
                    return True
            else:
                if side_is_long and amt > 1e-9:
                    return True
                if (not side_is_long) and amt < -1e-9:
                    return True
        except Exception:
            continue
    return False


def _filter_signal_order_candidates(
    self,
    *,
    cw,
    orders_to_execute,
    dual_side: bool,
    positions_cache=None,
    load_positions_cache=None,
) -> tuple[list[dict[str, object]], list[dict] | None, bool]:
    filtered_orders: list[dict[str, object]] = []
    positions_cache_snapshot = positions_cache
    if self.stopped():
        return filtered_orders, positions_cache_snapshot, True
    for order in orders_to_execute:
        if self.stopped():
            return filtered_orders, positions_cache_snapshot, True
        stop_cutoff = 0.0
        try:
            stop_cutoff = float(getattr(self, "_stop_time", 0.0) or 0.0)
        except Exception:
            stop_cutoff = 0.0
        if stop_cutoff > 0.0:
            try:
                order_ts = float(order.get("timestamp") or 0.0)
            except Exception:
                order_ts = 0.0
            if order_ts > 0.0 and order_ts <= stop_cutoff:
                continue
        side_upper = str(order.get("side") or "").upper()
        if side_upper not in ("BUY", "SELL"):
            continue
        key_dup = (cw["symbol"], cw.get("interval"), side_upper)
        leg_dup = self._leg_ledger.get(key_dup)
        signature = tuple(order.get("signature") or ())
        trigger_labels_raw = [
            str(lbl or "").strip()
            for lbl in (order.get("labels") or [])
            if str(lbl or "").strip()
        ]
        sig_tuple_base = tuple(
            sorted(
                str(part or "").strip().lower()
                for part in signature
                if str(part or "").strip()
            )
        )
        indicator_key_for_order = self._canonical_indicator_token(order.get("indicator_key")) or None
        if not indicator_key_for_order:
            if len(sig_tuple_base) == 1:
                indicator_key_for_order = sig_tuple_base[0]
            elif len(trigger_labels_raw) == 1:
                indicator_key_for_order = (
                    self._canonical_indicator_token(trigger_labels_raw[0]) or trigger_labels_raw[0].lower()
                )
        flip_from_norm = str(order.get("flip_from") or "").upper()
        flip_active = flip_from_norm in ("BUY", "SELL") and flip_from_norm != side_upper
        allow_order = True
        if leg_dup:
            entries_dup = self._leg_entries(key_dup)
            duplicate_active = False
            active_signatures: set[tuple[str, ...]] = set()
            allow_same_signature = bool(indicator_key_for_order or sig_tuple_base)
            if entries_dup:
                for entry in entries_dup:
                    entry_sig = tuple(sorted(entry.get("trigger_signature") or []))
                    entry_qty = max(0.0, float(entry.get("qty") or 0.0))
                    if entry_qty > 0.0:
                        active_signatures.add(entry_sig)
                    if entry_qty > 0.0 and (not signature or entry_sig == signature):
                        if not allow_same_signature:
                            duplicate_active = True
                            self.log(
                                f"{cw['symbol']}@{cw.get('interval')} duplicate {side_upper} open prevented (active entry for trigger {entry_sig or ('<none>',)})."
                            )
                            break
            if duplicate_active:
                allow_order = False
            else:
                try:
                    existing_qty = float(leg_dup.get("qty") or 0.0)
                except Exception:
                    existing_qty = 0.0
                signature_tracked_elsewhere = (
                    bool(active_signatures) and bool(signature) and signature not in active_signatures
                )
                if existing_qty > 0.0 and not signature_tracked_elsewhere:
                    cache = []
                    if callable(load_positions_cache):
                        try:
                            cache = load_positions_cache() or []
                        except Exception:
                            cache = []
                    elif isinstance(positions_cache_snapshot, list):
                        cache = positions_cache_snapshot
                    position_active = self._is_futures_position_active_for_order(
                        cw["symbol"],
                        side_upper,
                        dual_side,
                        cache,
                    )
                    if not position_active:
                        try:
                            fresh_cache = self.binance.list_open_futures_positions(
                                max_age=0.0,
                                force_refresh=True,
                            ) or []
                            if fresh_cache:
                                positions_cache_snapshot = fresh_cache
                            position_active = self._is_futures_position_active_for_order(
                                cw["symbol"],
                                side_upper,
                                dual_side,
                                fresh_cache,
                            )
                        except Exception:
                            position_active = False
                    if position_active:
                        self.log(
                            f"{cw['symbol']}@{cw.get('interval')} duplicate {side_upper} open prevented (position still active)."
                        )
                        allow_order = False
                    else:
                        elapsed = time.time() - float(leg_dup.get("timestamp") or 0.0)
                        try:
                            interval_seconds = float(self._interval_to_seconds(str(cw.get("interval") or "1m")))
                        except Exception:
                            interval_seconds = 60.0
                        guard_window = max(12.0, max(5.0, interval_seconds) * 1.2)
                        if elapsed < guard_window:
                            if flip_active:
                                try:
                                    self._remove_leg_entry(key_dup, None)
                                    self._guard_mark_leg_closed(key_dup)
                                except Exception:
                                    pass
                                try:
                                    self._last_order_time.pop(key_dup, None)
                                except Exception:
                                    pass
                            else:
                                self.log(
                                    f"{cw['symbol']}@{cw.get('interval')} pending fill guard: suppressing duplicate {side_upper} open (last attempt {elapsed:.1f}s ago)."
                                )
                                allow_order = False
                        else:
                            try:
                                self._remove_leg_entry(key_dup, None)
                                self._guard_mark_leg_closed(key_dup)
                            except Exception:
                                pass
                            try:
                                self._last_order_time.pop(key_dup, None)
                            except Exception:
                                pass
        if allow_order:
            filtered_orders.append(
                {
                    "side": side_upper,
                    "labels": list(order.get("labels") or []),
                    "indicator_key": indicator_key_for_order,
                    "base_signature": sig_tuple_base,
                    "signature": signature,
                    "timestamp": order.get("timestamp"),
                    "flip_from": order.get("flip_from"),
                    "flip_qty": order.get("flip_qty"),
                    "flip_qty_target": order.get("flip_qty_target"),
                    "trigger_desc": order.get("trigger_desc"),
                    "trigger_actions": order.get("trigger_actions"),
                }
            )
    return filtered_orders, positions_cache_snapshot, False


def _prepare_signal_orders(
    self,
    *,
    cw,
    indicator_order_requests,
    signal,
    signal_timestamp,
    trigger_sources,
    trigger_desc,
    trigger_actions,
    trigger_segments,
    dual_side: bool,
    positions_cache=None,
    load_positions_cache=None,
) -> tuple[list[dict[str, object]], list[dict] | None, bool]:
    orders_to_execute = self._build_signal_order_candidates(
        cw=cw,
        indicator_order_requests=indicator_order_requests,
        signal=signal,
        signal_timestamp=signal_timestamp,
        trigger_sources=trigger_sources,
        trigger_desc=trigger_desc,
        trigger_actions=trigger_actions,
        trigger_segments=trigger_segments,
    )
    initial_orders_count = len(orders_to_execute)
    orders_to_execute, positions_cache_snapshot, aborted = self._filter_signal_order_candidates(
        cw=cw,
        orders_to_execute=orders_to_execute,
        dual_side=dual_side,
        positions_cache=positions_cache,
        load_positions_cache=load_positions_cache,
    )
    if aborted:
        return orders_to_execute, positions_cache_snapshot, True
    if not cw.get("trade_on_signal", True):
        orders_to_execute = []
    if initial_orders_count > 0 and not orders_to_execute:
        try:
            self.log(
                f"{cw['symbol']}@{cw.get('interval')} order candidates={initial_orders_count} but all were filtered (guards/duplicates)."
            )
        except Exception:
            pass
    return orders_to_execute, positions_cache_snapshot, False


def bind_strategy_signal_order_prepare_runtime(strategy_cls) -> None:
    strategy_cls._segment_matches_indicator_context = _segment_matches_indicator_context
    strategy_cls._build_trigger_desc_for_order = _build_trigger_desc_for_order
    strategy_cls._normalize_order_trigger_actions = _normalize_order_trigger_actions
    strategy_cls._build_signal_order_candidates = _build_signal_order_candidates
    strategy_cls._is_futures_position_active_for_order = _is_futures_position_active_for_order
    strategy_cls._filter_signal_order_candidates = _filter_signal_order_candidates
    strategy_cls._prepare_signal_orders = _prepare_signal_orders
