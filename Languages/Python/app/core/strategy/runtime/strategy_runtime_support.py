from __future__ import annotations

from datetime import datetime
import time


def _notify_interval_closed(self, symbol: str, interval: str, position_side: str, **extra):
    if not self.trade_cb:
        return
    try:
        info = {
            "symbol": symbol,
            "interval": interval,
            "side": position_side,
            "position_side": position_side,
            "event": "close_interval",
            "status": "closed",
            "ok": True,
            "time": datetime.now().astimezone().strftime("%Y-%m-%d %H:%M:%S"),
        }
        if extra:
            info.update({k: v for k, v in extra.items() if v is not None})

        def _safe_float(value):
            try:
                if value is None:
                    return 0.0
                return float(value)
            except Exception:
                return 0.0

        log_parts: list[str] = []
        qty_val = _safe_float(info.get("qty"))
        if qty_val > 0.0:
            log_parts.append(f"qty={qty_val:.6f}")
        ref_price = _safe_float(info.get("close_price") or info.get("entry_price"))
        if qty_val > 0.0 and ref_price > 0.0:
            log_parts.append(f"size~{qty_val * ref_price:.2f} USDT")
        margin_val = _safe_float(info.get("margin_usdt"))
        if margin_val > 0.0:
            log_parts.append(f"margin~{margin_val:.2f} USDT")
        if log_parts:
            indicator_label = "-"
            trigger_desc = info.get("trigger_desc")
            if isinstance(trigger_desc, str) and trigger_desc.strip():
                indicator_label = trigger_desc.strip().upper()
            else:
                trig_sig = info.get("trigger_signature") or info.get("trigger_indicators")
                if isinstance(trig_sig, (list, tuple)):
                    normalized = [str(part).strip() for part in trig_sig if str(part).strip()]
                    if normalized:
                        indicator_label = "|".join(normalized).upper()
            reason_text = ""
            reason_val = info.get("reason")
            if isinstance(reason_val, str) and reason_val.strip():
                reason_text = f" [{reason_val.replace('_', ' ').strip()}]"
            interval_display = interval or info.get("interval") or "default"
            self.log(
                f"{symbol}@{interval_display} CLOSE {position_side}: "
                f"{', '.join(log_parts)} (context={indicator_label}){reason_text}."
            )
        self.trade_cb(info)
    except Exception:
        pass


def _queue_flip_on_close(
    self,
    interval: str | None,
    closed_side: str,
    entry: dict | None,
    payload: dict | None = None,
) -> None:
    if not self._strategy_coerce_bool(self.config.get("auto_flip_on_close"), False):
        return
    if not bool(self.config.get("trade_on_signal", True)):
        return
    if self.stopped():
        return
    indicator_keys = self._extract_indicator_keys(entry)
    if not indicator_keys:
        return
    interval_raw = str(interval or "").strip()
    interval_tokens = [
        token
        for token in self._tokenize_interval_label(interval_raw)
        if token and token != "-"
    ]
    if not interval_tokens:
        interval_tokens = [interval_raw.lower() or "default"]
    interval_key = ",".join(sorted(interval_tokens))
    closed_norm = "BUY" if str(closed_side or "").upper() in {"BUY", "LONG"} else "SELL"
    open_side = "SELL" if closed_norm == "BUY" else "BUY"
    qty = 0.0
    if isinstance(payload, dict):
        try:
            qty = float(payload.get("qty") or 0.0)
        except Exception:
            qty = 0.0
    if qty <= 0.0 and isinstance(entry, dict):
        try:
            qty = float(entry.get("qty") or 0.0)
        except Exception:
            qty = 0.0
    event_id = payload.get("event_id") if isinstance(payload, dict) else None
    now_ts = time.time()
    with self._flip_on_close_lock:
        for indicator_key in indicator_keys:
            indicator_cfg = (self.config.get("indicators") or {}).get(indicator_key, {})
            if indicator_cfg and not bool(indicator_cfg.get("enabled", True)):
                continue
            key = (interval_key, indicator_key, open_side)
            existing = self._flip_on_close_requests.get(key)
            if existing and event_id and existing.get("event_id") == event_id:
                continue
            self._flip_on_close_requests[key] = {
                "interval": interval_key,
                "interval_tokens": list(interval_tokens),
                "indicator_key": indicator_key,
                "side": open_side,
                "flip_from": closed_norm,
                "qty": qty,
                "event_id": event_id,
                "ts": now_ts,
            }
            try:
                qty_display = f"{qty:.10f}" if isinstance(qty, (int, float)) else str(qty)
                symbol_label = str(self.config.get("symbol") or "").upper()
                if not symbol_label:
                    symbols = self.config.get("symbols") or []
                    symbol_label = str(symbols[0] if symbols else "").upper()
                symbol_label = symbol_label or "SYMBOL"
                reason_val = ""
                if isinstance(payload, dict):
                    reason_val = str(payload.get("reason") or "").strip()
                if not reason_val and isinstance(entry, dict):
                    reason_val = str(entry.get("reason") or "").strip()
                if not reason_val:
                    reason_val = "unspecified"
                self.log(
                    f"{symbol_label}@{interval_key} flip-on-close queued: "
                    f"{indicator_key} {closed_norm}->{open_side} qty={qty_display} reason={reason_val}."
                )
            except Exception:
                pass


def _drain_flip_on_close_requests(self, interval: str | None) -> list[dict[str, object]]:
    if not self._strategy_coerce_bool(self.config.get("auto_flip_on_close"), False):
        return []
    interval_norm = str(interval or "").strip().lower() or "default"
    ttl = max(5.0, self._interval_seconds_value(interval) * 2.0)
    now_ts = time.time()
    drained: list[dict[str, object]] = []
    with self._flip_on_close_lock:
        for key, req in list(self._flip_on_close_requests.items()):
            req_tokens = req.get("interval_tokens")
            if isinstance(req_tokens, (list, tuple, set)):
                normalized_tokens = {
                    str(token or "").strip().lower()
                    for token in req_tokens
                    if str(token or "").strip()
                }
                if interval_norm not in normalized_tokens:
                    continue
            else:
                if str(req.get("interval") or "") != interval_norm:
                    continue
            try:
                age = now_ts - float(req.get("ts") or 0.0)
            except Exception:
                age = now_ts
            if age > ttl:
                self._flip_on_close_requests.pop(key, None)
                continue
            drained.append(req)
            self._flip_on_close_requests.pop(key, None)
    return drained


def _log_latency_metric(self, symbol: str, interval: str, label: str, latency_seconds: float) -> None:
    try:
        latency_seconds = max(0.0, float(latency_seconds))
    except Exception:
        latency_seconds = 0.0
    try:
        self.log(
            f"{symbol}@{interval} {label} signal->order latency: "
            f"{latency_seconds * 1000.0:.0f} ms ({latency_seconds:.3f}s)."
        )
    except Exception:
        pass


def _order_field(order_res, *names):
    """Extract the first available field from order response dictionaries."""
    if not isinstance(order_res, dict):
        return None
    sources = [order_res]
    info = order_res.get("info")
    if isinstance(info, dict):
        sources.append(info)
    computed = order_res.get("computed")
    if isinstance(computed, dict):
        sources.append(computed)
    for source in sources:
        for name in names:
            if name in source and source[name] is not None:
                return source[name]
    return None


def _build_close_event_payload(
    self,
    symbol: str,
    interval: str,
    side_label: str,
    qty_hint: float,
    order_res: dict | None,
    *,
    leg_info_override: dict | None = None,
) -> dict:
    """Prepare metadata describing a closed leg so the UI can compute realized PnL."""

    def _safe_float(value):
        try:
            return float(value)
        except Exception:
            return 0.0

    def _maybe_float(value):
        try:
            if value is None:
                return None
            if isinstance(value, str) and not value.strip():
                return None
            return float(value)
        except Exception:
            return None

    qty_val = _safe_float(self._order_field(order_res or {}, "executedQty", "cumQty", "cumQuantity", "origQty"))
    if qty_val <= 0.0:
        qty_val = abs(_safe_float(qty_hint))

    price_val = _safe_float(
        self._order_field(order_res or {}, "avgPrice", "price", "stopPrice", "markPrice", "px")
    )

    leg_key = (symbol, interval, side_label.upper())
    if isinstance(leg_info_override, dict):
        leg_info = leg_info_override
    else:
        leg_info = self._leg_ledger.get(leg_key, {}) or {}

    entry_price = _safe_float(leg_info.get("entry_price"))
    leverage = int(_safe_float(leg_info.get("leverage")))
    if leverage <= 0:
        try:
            leverage = int(self.config.get("leverage") or 0)
        except Exception:
            leverage = 0
    margin_usdt = _safe_float(leg_info.get("margin_usdt"))
    if margin_usdt <= 0.0 and entry_price > 0.0 and qty_val > 0.0:
        margin_usdt = (entry_price * qty_val) / leverage if leverage > 0 else entry_price * qty_val

    pnl_value = None
    if entry_price > 0.0 and price_val > 0.0 and qty_val > 0.0:
        direction = 1.0 if side_label.upper() in ("BUY", "LONG") else -1.0
        pnl_value = (price_val - entry_price) * qty_val * direction

    roi_percent = None
    if pnl_value is not None and margin_usdt > 0.0:
        roi_percent = (pnl_value / margin_usdt) * 100.0

    payload: dict[str, float] = {}
    if qty_val > 0.0:
        payload["qty"] = abs(qty_val)
    if price_val > 0.0:
        payload["close_price"] = price_val
    if entry_price > 0.0:
        payload["entry_price"] = entry_price
    if pnl_value is not None:
        payload["pnl_value"] = pnl_value
    if margin_usdt > 0.0:
        payload["margin_usdt"] = margin_usdt
    if leverage > 0:
        payload["leverage"] = leverage
    if roi_percent is not None:
        payload["roi_percent"] = roi_percent
    ledger_id = leg_info.get("ledger_id") if isinstance(leg_info, dict) else None
    if ledger_id:
        payload["ledger_id"] = ledger_id

    fills_info = order_res.get("fills") if isinstance(order_res, dict) else None
    entry_fee_value = None
    if isinstance(leg_info, dict):
        entry_fee_value = _maybe_float(leg_info.get("fees_usdt") or leg_info.get("entry_fee_usdt"))
    close_fee_value = _maybe_float(fills_info.get("commission_usdt")) if isinstance(fills_info, dict) else None
    net_realized_value = _maybe_float(fills_info.get("net_realized")) if isinstance(fills_info, dict) else None
    realized_raw_value = _maybe_float(fills_info.get("realized_pnl")) if isinstance(fills_info, dict) else None

    if entry_fee_value not in (None, 0.0):
        payload["entry_fee_usdt"] = entry_fee_value
    if close_fee_value not in (None, 0.0):
        payload["close_fee_usdt"] = close_fee_value
    if realized_raw_value not in (None, 0.0):
        payload["realized_pnl_usdt"] = realized_raw_value

    if net_realized_value is not None:
        pnl_adj = net_realized_value - (entry_fee_value or 0.0)
        payload["pnl_value"] = pnl_adj
    elif "pnl_value" in payload:
        total_fee = (entry_fee_value or 0.0) + (close_fee_value or 0.0)
        if total_fee:
            pnl_adj = float(payload["pnl_value"]) - total_fee
            payload["pnl_value"] = pnl_adj

    if "pnl_value" in payload and margin_usdt > 0.0:
        payload["roi_percent"] = (float(payload["pnl_value"]) / margin_usdt) * 100.0

    if isinstance(fills_info, dict) and fills_info:
        payload.setdefault("fills_meta", {})
        payload["fills_meta"].update(
            {
                "trade_count": fills_info.get("trade_count"),
                "order_id": fills_info.get("order_id"),
            }
        )

    payload["event_id"] = f"{ledger_id or symbol}-{int(time.time() * 1000)}"
    return payload


def _leg_entries(self, leg_key) -> list[dict]:
    leg = self._leg_ledger.get(leg_key)
    if not isinstance(leg, dict):
        return []
    entries = leg.get("entries")
    if not isinstance(entries, list):
        return []
    filtered = []
    for entry in entries:
        if isinstance(entry, dict):
            filtered.append(entry)
    return filtered


def _indicator_prev_live_signal_values(self, series) -> tuple[float, float, float]:
    """
    Returns (prev_closed, live, selected_signal) for a pandas Series.
    selected_signal respects indicator_use_live_values.
    """
    if series is None:
        raise ValueError("indicator series missing")
    try:
        data = series.dropna()
    except Exception:
        data = series
    if data is None or len(data) == 0:
        raise ValueError("indicator series empty")
    live_val = float(data.iloc[-1])
    prev_val = float(data.iloc[-2]) if len(data) >= 2 else live_val
    signal_val = live_val if self._indicator_use_live_values else prev_val
    return prev_val, live_val, signal_val


def _interval_seconds_value(interval_value: str | None) -> float:
    try:
        text = str(interval_value or "1m")
        if text.endswith("s"):
            return float(int(text[:-1]))
        if text.endswith("m"):
            return float(int(text[:-1]) * 60)
        if text.endswith("h"):
            return float(int(text[:-1]) * 3600)
        if text.endswith("d"):
            return float(int(text[:-1]) * 86400)
    except Exception:
        pass
    return 60.0


def _interval_seconds(self, interval: str) -> int:
    try:
        if interval.endswith("s"):
            return int(interval[:-1])
        if interval.endswith("m"):
            return int(interval[:-1]) * 60
        if interval.endswith("h"):
            return int(interval[:-1]) * 3600
        if interval.endswith("d"):
            return int(interval[:-1]) * 86400
        if interval.endswith("w"):
            return int(interval[:-1]) * 7 * 86400
        return int(interval)
    except Exception:
        return 60


def bind_strategy_runtime_support(strategy_cls) -> None:
    strategy_cls._notify_interval_closed = _notify_interval_closed
    strategy_cls._queue_flip_on_close = _queue_flip_on_close
    strategy_cls._drain_flip_on_close_requests = _drain_flip_on_close_requests
    strategy_cls._log_latency_metric = _log_latency_metric
    strategy_cls._order_field = staticmethod(_order_field)
    strategy_cls._build_close_event_payload = _build_close_event_payload
    strategy_cls._leg_entries = _leg_entries
    strategy_cls._indicator_prev_live_signal_values = _indicator_prev_live_signal_values
    strategy_cls._interval_seconds_value = staticmethod(_interval_seconds_value)
    strategy_cls._interval_seconds = _interval_seconds
