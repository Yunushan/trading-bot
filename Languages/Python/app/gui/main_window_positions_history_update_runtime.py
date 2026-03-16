from __future__ import annotations

import copy
import time

_CLOSED_HISTORY_MAX = None
_RESOLVE_TRIGGER_INDICATORS = None


def configure_main_window_positions_history_update_runtime(
    *,
    closed_history_max_fn=None,
    resolve_trigger_indicators=None,
) -> None:
    global _CLOSED_HISTORY_MAX
    global _RESOLVE_TRIGGER_INDICATORS

    _CLOSED_HISTORY_MAX = closed_history_max_fn
    _RESOLVE_TRIGGER_INDICATORS = resolve_trigger_indicators


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


def _resolve_trigger_indicators_safe(raw, desc: str | None = None) -> list[str]:
    func = _RESOLVE_TRIGGER_INDICATORS
    if not callable(func):
        return []
    try:
        return list(func(raw, desc))
    except Exception:
        return []


def _mw_update_position_history(self, positions_map: dict):
    try:
        if not hasattr(self, "_open_position_records"):
            self._open_position_records = {}
        if not hasattr(self, "_closed_position_records"):
            self._closed_position_records = []
        missing_counts = getattr(self, "_position_missing_counts", {})
        if not isinstance(missing_counts, dict):
            missing_counts = {}
        prev_records = getattr(self, "_open_position_records", {}) or {}
        candidates: list[tuple[str, str]] = []
        pending_close_map = getattr(self, "_pending_close_times", {})
        closed_history_max = _closed_history_max(self)
        try:
            missing_grace_seconds = float(
                self.config.get("positions_missing_grace_seconds", 30) or 0.0
            )
        except Exception:
            missing_grace_seconds = 0.0
        missing_grace_seconds = max(0.0, missing_grace_seconds)
        for key, prev in prev_records.items():
            if key in positions_map:
                missing_counts.pop(key, None)
                continue
            count = missing_counts.get(key, 0) + 1
            missing_counts[key] = count
            try:
                threshold = int(self.config.get("positions_missing_threshold", 2) or 2)
            except Exception:
                threshold = 2
            threshold = max(1, threshold)
            try:
                if isinstance(pending_close_map, dict) and key in pending_close_map:
                    threshold = 1
            except Exception:
                try:
                    threshold = int(self.config.get("positions_missing_threshold", 2) or 2)
                except Exception:
                    threshold = 2
            if count >= threshold:
                if missing_grace_seconds > 0 and not (
                    isinstance(pending_close_map, dict) and key in pending_close_map
                ):
                    open_val = None
                    if isinstance(prev, dict):
                        open_val = prev.get("open_time")
                        if not open_val:
                            open_val = (prev.get("data") or {}).get("open_time")
                        if not open_val:
                            open_val = (prev.get("data") or {}).get("update_time")
                    dt_obj = self._parse_any_datetime(open_val)
                    if dt_obj is not None:
                        try:
                            age_seconds = time.time() - dt_obj.timestamp()
                        except Exception:
                            age_seconds = None
                        if age_seconds is not None and 0 <= age_seconds < missing_grace_seconds:
                            continue
                candidates.append(key)

        def _resolve_live_keys() -> set[tuple[str, str]] | None:
            if not candidates:
                return set()
            try:
                bw = getattr(self, "shared_binance", None)
                if bw is None:
                    api_key = ""
                    api_secret = ""
                    try:
                        api_key = (self.api_key_edit.text() or "").strip()
                        api_secret = (self.api_secret_edit.text() or "").strip()
                    except Exception:
                        pass
                    if api_key and api_secret:
                        try:
                            bw = self._create_binance_wrapper(
                                api_key=api_key,
                                api_secret=api_secret,
                                mode=self.mode_combo.currentText(),
                                account_type=self.account_combo.currentText(),
                                default_leverage=int(self.leverage_spin.value() or 1),
                                default_margin_mode=self.margin_mode_combo.currentText() or "Isolated",
                            )
                            self.shared_binance = bw
                        except Exception:
                            bw = None
                if bw is None:
                    return None
                live = set()
                try:
                    acct_text = self.account_combo.currentText()
                except Exception:
                    acct_text = str(self.config.get("account_type") or "")
                acct_upper = str(acct_text or "").upper()
                acct_is_futures = acct_upper.startswith("FUT")
                acct_is_spot = acct_upper.startswith("SPOT")

                need_futures = acct_is_futures and any(side in ("L", "S") for _, side in candidates)
                need_spot = acct_is_spot and any(side in ("L", "S", "SPOT") for _, side in candidates)
                if need_futures:
                    try:
                        for pos in bw.list_open_futures_positions() or []:
                            sym = str(pos.get("symbol") or "").strip().upper()
                            if not sym:
                                continue
                            amt = float(pos.get("positionAmt") or 0.0)
                            if abs(amt) <= 0.0:
                                continue
                            side_key = "L" if amt > 0 else "S"
                            live.add((sym, side_key))
                    except Exception:
                        return None
                if need_spot:
                    try:
                        balances = bw.get_balances() or []
                        for bal in balances:
                            asset = bal.get("asset")
                            free = float(bal.get("free") or 0.0)
                            locked = float(bal.get("locked") or 0.0)
                            total = free + locked
                            if not asset or total <= 0:
                                continue
                            sym = f"{asset}USDT"
                            sym_upper = sym.strip().upper()
                            live.add((sym_upper, "SPOT"))
                            live.add((sym_upper, "L"))
                    except Exception:
                        pass
                return live
            except Exception:
                return None

        live_keys = _resolve_live_keys() if candidates else set()
        allow_missing_autoclose = bool(self.config.get("positions_missing_autoclose", True))

        def _lookup_force_liquidation(
            symbol: str,
            side_key: str,
            update_hint_ms: int | None = None,
        ) -> dict | None:
            try:
                bw = getattr(self, "shared_binance", None)
                if bw is None or not hasattr(bw, "get_recent_force_orders"):
                    return None
                params: dict[str, object] = {"symbol": symbol, "limit": 20}
                if update_hint_ms:
                    try:
                        params["start_time"] = max(0, int(update_hint_ms) - 900_000)
                    except Exception:
                        pass
                orders = bw.get_recent_force_orders(**params) or []
                if not orders:
                    return None
                expected_side = "SELL" if side_key == "L" else "BUY"
                now_ms = int(time.time() * 1000)
                for order in reversed(orders):
                    if not isinstance(order, dict):
                        continue
                    order_side = str(order.get("side") or "").upper()
                    if order_side != expected_side:
                        continue
                    try:
                        order_time = int(float(order.get("updateTime") or order.get("time") or 0))
                    except Exception:
                        order_time = 0
                    if order_time and abs(now_ms - order_time) > 900_000:
                        continue
                    qty_val = 0.0
                    for qty_key in ("executedQty", "origQty"):
                        val = order.get(qty_key)
                        if val in (None, "", 0, 0.0):
                            continue
                        try:
                            qty_val = abs(float(val))
                        except Exception:
                            qty_val = 0.0
                        if qty_val > 0:
                            break
                    if qty_val <= 0.0:
                        continue
                    price_val = 0.0
                    for price_key in ("avgPrice", "price"):
                        val = order.get(price_key)
                        if val in (None, "", 0, 0.0):
                            continue
                        try:
                            price_val = float(val)
                        except Exception:
                            price_val = 0.0
                        if price_val > 0.0:
                            break
                    if price_val <= 0.0:
                        continue
                    return {
                        "close_price": price_val,
                        "qty": qty_val,
                        "time": order_time or now_ms,
                        "raw": order,
                    }
            except Exception:
                return None
            return None

        confirmed_closed: list[tuple[str, str]] = []
        for key in candidates:
            if live_keys is None or key in live_keys:
                if key in prev_records:
                    positions_map.setdefault(key, prev_records[key])
                missing_counts[key] = 0
            else:
                if allow_missing_autoclose:
                    confirmed_closed.append(key)
                else:
                    prev_records.pop(key, None)
                    missing_counts.pop(key, None)

        if confirmed_closed:
            from datetime import datetime as _dt

            close_time_map = getattr(self, "_pending_close_times", {})
            for key in confirmed_closed:
                rec = prev_records.get(key)
                if not rec:
                    continue
                sym, side_key = key
                snap = copy.deepcopy(rec)
                data_prev = dict(rec.get("data") or {})
                close_status = "Closed"
                qty_reported = None
                margin_reported = None
                pnl_reported = None
                roi_reported = None
                close_price_reported = None
                entry_price_reported = None
                leverage_reported = None
                close_fmt = None
                close_raw = close_time_map.pop(key, None) if isinstance(close_time_map, dict) else None
                if close_raw:
                    dt_obj = self._parse_any_datetime(close_raw)
                    if dt_obj:
                        close_fmt = self._format_display_time(dt_obj)
                if close_fmt is None:
                    close_fmt = self._format_display_time(_dt.now().astimezone())
                if "stop_loss_enabled" not in snap:
                    snap["stop_loss_enabled"] = bool(rec.get("stop_loss_enabled"))
                try:
                    alloc_entries = copy.deepcopy(getattr(self, "_entry_allocations", {}).get(key, [])) or []
                except Exception:
                    alloc_entries = []
                entry_price_val = 0.0
                margin_prev = float(data_prev.get("margin_usdt") or 0.0)
                size_prev = float(data_prev.get("size_usdt") or 0.0)
                leverage_prev = data_prev.get("leverage")
                if isinstance(leverage_prev, (int, float)) and leverage_prev > 0:
                    leverage_reported = int(float(leverage_prev))
                else:
                    leverage_reported = None
                if alloc_entries:
                    num = 0.0
                    den = 0.0
                    for entry in alloc_entries:
                        if not isinstance(entry, dict):
                            continue
                        try:
                            qty_val = abs(float(entry.get("qty") or 0.0))
                            price_val = float(entry.get("entry_price") or data_prev.get("entry_price") or 0.0)
                        except Exception:
                            qty_val = 0.0
                            price_val = 0.0
                        if qty_val > 0 and price_val > 0:
                            num += price_val * qty_val
                            den += qty_val
                        try:
                            margin_prev = max(margin_prev, float(entry.get("margin_usdt") or 0.0))
                        except Exception:
                            pass
                        try:
                            size_prev = max(
                                size_prev,
                                float(
                                    entry.get("notional")
                                    or entry.get("size_usdt")
                                    or size_prev
                                    or 0.0
                                ),
                            )
                        except Exception:
                            pass
                    if den > 0:
                        entry_price_val = num / den
                if entry_price_val <= 0:
                    try:
                        entry_price_val = float(data_prev.get("entry_price") or 0.0)
                    except Exception:
                        entry_price_val = 0.0
                update_hint = None
                try:
                    update_hint = int(float(data_prev.get("update_time") or 0))
                except Exception:
                    update_hint = None
                liquidation_meta = None
                if side_key in ("L", "S"):
                    liquidation_meta = _lookup_force_liquidation(sym, side_key, update_hint)
                if liquidation_meta:
                    close_status = "Liquidated"
                    snap["close_reason"] = "Liquidation"
                    liquidation_time = liquidation_meta.get("time")
                    if liquidation_time:
                        try:
                            close_fmt = self._format_display_time(
                                _dt.fromtimestamp(int(liquidation_time) / 1000.0).astimezone()
                            )
                        except Exception:
                            pass
                    close_price_reported = float(liquidation_meta.get("close_price") or 0.0)
                    qty_reported = float(liquidation_meta.get("qty") or 0.0)
                    if entry_price_val > 0:
                        entry_price_reported = entry_price_val
                    side_mult = 1.0 if side_key == "L" else -1.0
                    if entry_price_reported and qty_reported:
                        pnl_calc = (
                            (close_price_reported - entry_price_reported)
                            * qty_reported
                            * side_mult
                        )
                        pnl_reported = pnl_calc
                    if margin_prev <= 0.0 and size_prev > 0.0 and leverage_prev:
                        try:
                            lev_val = float(leverage_prev)
                            if lev_val > 0:
                                margin_prev = size_prev / lev_val
                        except Exception:
                            pass
                    if margin_prev > 0.0:
                        margin_reported = margin_prev
                    if pnl_reported is not None and margin_reported:
                        try:
                            roi_reported = (pnl_reported / margin_reported) * 100.0
                        except Exception:
                            roi_reported = None
                snap["status"] = close_status
                snap["close_time"] = close_fmt
                snap_data = snap.setdefault("data", {})
                if not snap_data and data_prev:
                    snap_data.update(data_prev)
                if qty_reported is None:
                    try:
                        qty_prev = float(data_prev.get("qty") or 0.0)
                        if abs(qty_prev) > 0.0:
                            qty_reported = abs(qty_prev)
                    except Exception:
                        qty_reported = None
                if margin_reported is None:
                    try:
                        margin_val_prev = float(data_prev.get("margin_usdt") or 0.0)
                        if margin_val_prev > 0.0:
                            margin_reported = margin_val_prev
                    except Exception:
                        margin_reported = None
                if pnl_reported is None:
                    try:
                        pnl_prev = float(data_prev.get("pnl_value") or 0.0)
                        pnl_reported = pnl_prev
                    except Exception:
                        pnl_reported = None
                if roi_reported is None:
                    try:
                        roi_prev = float(data_prev.get("roi_percent") or 0.0)
                        roi_reported = roi_prev if roi_prev != 0.0 else None
                    except Exception:
                        roi_reported = None
                if close_price_reported is None:
                    try:
                        close_price_prev = float(data_prev.get("close_price") or 0.0)
                        if close_price_prev > 0.0:
                            close_price_reported = close_price_prev
                    except Exception:
                        close_price_reported = None
                if entry_price_reported is None and entry_price_val > 0:
                    entry_price_reported = entry_price_val
                if leverage_reported is None and leverage_prev:
                    try:
                        lev_int = int(float(leverage_prev))
                        if lev_int > 0:
                            leverage_reported = lev_int
                    except Exception:
                        leverage_reported = None
                if qty_reported is not None and qty_reported > 0:
                    snap_data["qty"] = qty_reported
                if margin_reported is not None and margin_reported > 0:
                    snap_data["margin_usdt"] = margin_reported
                if pnl_reported is not None:
                    snap_data["pnl_value"] = pnl_reported
                    if margin_reported and margin_reported > 0:
                        roi_calc = (
                            roi_reported
                            if roi_reported is not None
                            else (pnl_reported / margin_reported) * 100.0
                        )
                        roi_reported = roi_calc
                        snap_data["roi_percent"] = roi_calc
                        snap_data["pnl_roi"] = f"{pnl_reported:+.2f} USDT ({roi_calc:+.2f}%)"
                    else:
                        snap_data["pnl_roi"] = f"{pnl_reported:+.2f} USDT"
                if roi_reported is not None and "roi_percent" not in snap_data:
                    snap_data["roi_percent"] = roi_reported
                if close_price_reported is not None and close_price_reported > 0:
                    snap_data["close_price"] = close_price_reported
                if entry_price_reported is not None and entry_price_reported > 0:
                    snap_data.setdefault("entry_price", entry_price_reported)
                if leverage_reported:
                    snap_data["leverage"] = leverage_reported
                if alloc_entries:
                    for entry in alloc_entries:
                        if isinstance(entry, dict):
                            normalized_triggers = _resolve_trigger_indicators_safe(
                                entry.get("trigger_indicators"),
                                entry.get("trigger_desc"),
                            )
                            if normalized_triggers:
                                entry["trigger_indicators"] = normalized_triggers
                            elif entry.get("trigger_indicators"):
                                entry.pop("trigger_indicators", None)
                    base_data = rec.get("data", {}) or {}
                    base_qty = float(base_data.get("qty") or 0.0)
                    base_margin = float(base_data.get("margin_usdt") or 0.0)
                    base_pnl = float(base_data.get("pnl_value") or 0.0)
                    base_size = float(base_data.get("size_usdt") or 0.0)
                    total_qty = 0.0
                    for entry in alloc_entries:
                        try:
                            total_qty += abs(float(entry.get("qty") or 0.0))
                        except Exception:
                            continue
                    if total_qty <= 0 and base_qty > 0:
                        total_qty = base_qty
                    count_entries = len([entry for entry in alloc_entries if isinstance(entry, dict)])
                    for entry in alloc_entries:
                        if not isinstance(entry, dict):
                            continue
                        entry["status"] = close_status
                        entry["close_time"] = close_fmt
                        try:
                            qty_val = abs(float(entry.get("qty") or 0.0))
                        except Exception:
                            qty_val = 0.0
                        ratio = (
                            (qty_val / total_qty)
                            if total_qty > 0
                            else (1.0 / count_entries if count_entries else 0.0)
                        )
                        if ratio <= 0 and count_entries:
                            ratio = 1.0 / count_entries
                        if float(entry.get("margin_usdt") or 0.0) <= 0 and base_margin > 0:
                            entry["margin_usdt"] = base_margin * ratio
                        if float(entry.get("notional") or 0.0) <= 0 and base_size > 0:
                            entry["notional"] = base_size * ratio
                        if entry.get("pnl_value") is None:
                            if base_pnl and base_qty > 0 and qty_val > 0:
                                entry["pnl_value"] = base_pnl * (qty_val / base_qty)
                            elif base_pnl and ratio > 0:
                                entry["pnl_value"] = base_pnl * ratio
                            else:
                                entry["pnl_value"] = base_pnl
                    qty_dist_sum = 0.0
                    try:
                        qty_dist_sum = sum(
                            abs(float(entry.get("qty") or 0.0))
                            for entry in alloc_entries
                            if isinstance(entry, dict)
                        )
                    except Exception:
                        qty_dist_sum = 0.0
                    if qty_dist_sum <= 0.0 and qty_reported is not None and qty_reported > 0:
                        qty_dist_sum = qty_reported
                    entries_count = len([entry for entry in alloc_entries if isinstance(entry, dict)])
                    for entry in alloc_entries:
                        if not isinstance(entry, dict):
                            continue
                        share = 0.0
                        try:
                            if qty_dist_sum and qty_dist_sum > 0:
                                share = abs(float(entry.get("qty") or 0.0)) / qty_dist_sum
                        except Exception:
                            share = 0.0
                        if share <= 0.0 and entries_count:
                            share = 1.0 / entries_count
                        if qty_reported is not None and qty_reported > 0 and share > 0:
                            entry["qty"] = qty_reported * share
                        if margin_reported is not None and margin_reported > 0 and share > 0:
                            entry["margin_usdt"] = margin_reported * share
                        if pnl_reported is not None and share > 0:
                            entry["pnl_value"] = pnl_reported * share
                        if close_price_reported is not None and close_price_reported > 0:
                            entry["close_price"] = close_price_reported
                        if entry_price_reported is not None and entry_price_reported > 0:
                            entry.setdefault("entry_price", entry_price_reported)
                        if leverage_reported:
                            entry["leverage"] = leverage_reported
                else:
                    alloc_entries = []
                if alloc_entries:
                    snap["allocations"] = alloc_entries
                self._closed_position_records.insert(0, snap)
                try:
                    registry = getattr(self, "_closed_trade_registry", None)
                    if registry is None:
                        registry = {}
                        self._closed_trade_registry = registry
                    registry_key = snap.get("ledger_id") or f"auto:{sym}:{side_key}:{close_fmt}"

                    def _safe_float_report(value):
                        try:
                            return float(value) if value is not None else None
                        except Exception:
                            return None

                    registry[registry_key] = {
                        "pnl_value": _safe_float_report(pnl_reported),
                        "margin_usdt": _safe_float_report(margin_reported),
                        "roi_percent": _safe_float_report(roi_reported),
                    }
                    if len(registry) > closed_history_max:
                        excess = len(registry) - closed_history_max
                        if excess > 0:
                            for old_key in list(registry.keys())[:excess]:
                                registry.pop(old_key, None)
                    try:
                        self._update_global_pnl_display(*self._compute_global_pnl_totals())
                    except Exception:
                        pass
                except Exception:
                    pass
                missing_counts.pop(key, None)
                try:
                    getattr(self, "_entry_allocations", {}).pop(key, None)
                except Exception:
                    pass
            if len(self._closed_position_records) > closed_history_max:
                self._closed_position_records = self._closed_position_records[:closed_history_max]

        self._open_position_records = positions_map
        self._position_missing_counts = missing_counts
    except Exception:
        pass
