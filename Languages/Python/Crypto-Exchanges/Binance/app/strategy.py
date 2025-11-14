
import time, copy, traceback, math, threading, os, re
from collections.abc import Iterable
from datetime import datetime, timezone

import pandas as pd
from .config import (
    STOP_LOSS_MODE_ORDER,
    STOP_LOSS_SCOPE_OPTIONS,
    normalize_stop_loss_dict,
    INDICATOR_DISPLAY_NAMES,
    coerce_bool,
)
from .binance_wrapper import NetworkConnectivityError, normalize_margin_ratio
from .indicators import (
    sma,
    ema,
    bollinger_bands,
    rsi as rsi_fallback,
    macd as macd_fallback,
    stoch_rsi as stoch_rsi_fallback,
    williams_r as williams_r_fallback,
    parabolic_sar as psar_fallback,
    ultimate_oscillator as uo_fallback,
    dmi as dmi_fallback,
    adx as adx_fallback,
    supertrend as supertrend_fallback,
    stochastic as stochastic_fallback,
)
from .preamble import PANDAS_TA_AVAILABLE, PANDAS_VERSION, PANDAS_TA_VERSION

def _interval_to_seconds(iv:str)->int:
    try:
        if iv.endswith('m'): return int(iv[:-1])*60
        if iv.endswith('s'): return int(iv[:-1])
        if iv.endswith('h'): return int(iv[:-1])*3600
        if iv.endswith('d'): return int(iv[:-1])*86400
    except Exception:
        pass
    return 60


_CPU_COUNT = os.cpu_count() or 4


def _default_parallel_limit(cpu_count: int) -> int:
    """Heuristic to balance strategy loop concurrency with available CPU cores.

    Too many concurrent loops on low core-count hosts starves the Qt GUI thread,
    so we keep the limit tight for <=4 cores and scale gently afterwards.
    """
    cpu = max(1, int(cpu_count))
    if cpu == 1:
        return 1
    if cpu == 2:
        return 2
    if cpu <= 4:
        return cpu
    if cpu <= 8:
        return int(round(cpu * 1.25))
    return min(16, int(round(cpu * 1.5)))


_MAX_PARALLEL_RUNS = max(1, min(16, _default_parallel_limit(_CPU_COUNT)))


def _normalize_indicator_alias(token: str | None) -> str:
    return str(token or "").strip().lower()


def _strip_indicator_label(alias: str) -> str:
    text = alias.replace("(", " ").replace(")", " ")
    text = text.replace("%", " % ")
    while "  " in text:
        text = text.replace("  ", " ")
    return text.strip()


def _build_indicator_alias_map() -> dict[str, str]:
    alias_map: dict[str, str] = {}

    def _register(alias: str | None, canonical: str | None) -> None:
        alias_norm = _normalize_indicator_alias(alias)
        canonical_norm = _normalize_indicator_alias(canonical)
        if alias_norm and canonical_norm and alias_norm not in alias_map:
            alias_map[alias_norm] = canonical_norm

    indicators = INDICATOR_DISPLAY_NAMES or {}
    for key, label in indicators.items():
        _register(key, key)
        _register(label, key)
        if isinstance(label, str):
            _register(_strip_indicator_label(label), key)
            _register(_strip_indicator_label(label).replace(" ", ""), key)
            if "(" in label and ")" in label:
                inner = label[label.find("(") + 1 : label.rfind(")")]
                _register(inner, key)
                _register(inner.replace(" ", ""), key)
    return alias_map


_INDICATOR_ALIAS_MAP = _build_indicator_alias_map()


def _canonical_indicator_token(token: str | None) -> str | None:
    text = _normalize_indicator_alias(token)
    if not text:
        return None
    mapped = _INDICATOR_ALIAS_MAP.get(text)
    if mapped:
        return mapped
    compact = text.replace(" ", "")
    mapped = _INDICATOR_ALIAS_MAP.get(compact)
    if mapped:
        return mapped
    stripped = _strip_indicator_label(text)
    mapped = _INDICATOR_ALIAS_MAP.get(stripped)
    if mapped:
        return mapped
    compact_stripped = stripped.replace(" ", "")
    mapped = _INDICATOR_ALIAS_MAP.get(compact_stripped)
    if mapped:
        return mapped
    return text


class StrategyEngine:
    _RUN_GATE = threading.BoundedSemaphore(_MAX_PARALLEL_RUNS)
    _MAX_ACTIVE = _MAX_PARALLEL_RUNS
    _ORDER_THROTTLE_LOCK = threading.Lock()
    _ORDER_LAST_TS = 0.0
    _ORDER_MIN_SPACING = 0.35  # seconds between order submissions by default
    _BAR_GUARD_LOCK = threading.Lock()
    _BAR_GLOBAL_SIGNATURES: dict[tuple[str, str, str], dict[str, object]] = {}
    _SYMBOL_GUARD_LOCK = threading.Lock()
    _SYMBOL_ORDER_STATE: dict[tuple[str, str], dict[str, object]] = {}

    @classmethod
    def concurrent_limit(cls, job_count: int | None = None) -> int:
        limit = cls._MAX_ACTIVE
        if job_count is not None:
            try:
                limit = min(limit, max(1, int(job_count)))
            except Exception:
                pass
        return limit

    @classmethod
    def _reserve_order_slot(cls, min_spacing: float | None = None) -> None:
        """Global rate limiter so we don't spam the exchange with concurrent orders."""
        spacing = float(min_spacing) if min_spacing is not None else cls._ORDER_MIN_SPACING
        if not math.isfinite(spacing) or spacing <= 0.0:
            spacing = cls._ORDER_MIN_SPACING
        spacing = max(cls._ORDER_MIN_SPACING, spacing)
        while True:
            with cls._ORDER_THROTTLE_LOCK:
                now = time.time()
                wait = (cls._ORDER_LAST_TS + spacing) - now
                if wait <= 0.0:
                    cls._ORDER_LAST_TS = now
                    return
            time.sleep(min(max(wait, 0.01), 0.5))

    @classmethod
    def _release_order_slot(cls) -> None:
        with cls._ORDER_THROTTLE_LOCK:
            cls._ORDER_LAST_TS = max(cls._ORDER_LAST_TS, time.time())

    def __init__(self, binance_wrapper, config, log_callback, trade_callback=None, loop_interval_override=None, can_open_callback=None):
        self.config = copy.deepcopy(config)
        self.config.setdefault("indicator_flip_cooldown_bars", 1)
        self.config.setdefault("indicator_flip_cooldown_seconds", 0.0)
        self.config.setdefault("indicator_use_live_values", True)
        self.config.setdefault("indicator_min_position_hold_seconds", 0.0)
        self.config["stop_loss"] = normalize_stop_loss_dict(self.config.get("stop_loss"))
        self.binance = binance_wrapper
        self.log = log_callback
        self.trade_cb = trade_callback
        self.loop_override = loop_interval_override
        self._leg_ledger = {}
        self._last_order_time = {}  # (symbol, interval, side)->{'qty': float, 'timestamp': float}
        self._last_bar_key = set()  # prevent multi entries within same bar per (symbol, interval, side)
        self._bar_order_tracker: dict[tuple[str, str, str], dict[str, object]] = {}
        self._symbol_signature_open: dict[tuple[str, str, tuple[str, ...]], int] = {}
        self._symbol_signature_lock = threading.Lock()
        self._indicator_state: dict[tuple[str, str, str], dict[str, set[str]]] = {}
        self._indicator_state_lock = threading.Lock()
        self._trade_book_lock = threading.RLock()
        self._trade_book: dict[tuple[str, str, str, str], dict[str, dict[str, float]]] = {}
        self._ledger_index: dict[str, tuple[str, str, str]] = {}
        self.can_open_cb = can_open_callback
        self._stop = False
        key = f"{str(self.config.get('symbol') or '').upper()}@{str(self.config.get('interval') or '').lower()}"
        h = abs(hash(key)) if key.strip('@') else 0
        self._phase_seed = (h % 997) / 997.0 if key.strip('@') else 0.0
        self._phase_offset = self._phase_seed * 25.0
        self._thread = None
        self._offline_backoff = 0.0
        self._last_network_log = 0.0
        self._emergency_close_triggered = False
        self._stop_time = 0.0
        try:
            spacing = float(self.config.get("order_rate_min_spacing", StrategyEngine._ORDER_MIN_SPACING))
        except Exception:
            spacing = StrategyEngine._ORDER_MIN_SPACING
        self._order_rate_min_spacing = max(0.05, min(spacing, 5.0))
        try:
            retry_backoff = float(self.config.get("order_rate_retry_backoff", 0.75))
        except Exception:
            retry_backoff = 0.75
        self._order_rate_retry_backoff = max(0.1, min(retry_backoff, 5.0))
        self._indicator_use_live_values = bool(self.config.get("indicator_use_live_values", True))
        try:
            self._indicator_min_hold_seconds = max(
                0.0, float(self.config.get("indicator_min_position_hold_seconds") or 0.0)
            )
        except Exception:
            self._indicator_min_hold_seconds = 0.0
        try:
            self._indicator_flip_cooldown_seconds = max(
                0.0, float(self.config.get("indicator_flip_cooldown_seconds") or 0.0)
            )
        except Exception:
            self._indicator_flip_cooldown_seconds = 0.0
        try:
            self._indicator_flip_cooldown_bars = max(
                0, int(self.config.get("indicator_flip_cooldown_bars") or 0)
            )
        except Exception:
            self._indicator_flip_cooldown_bars = 0
        try:
            self._indicator_min_hold_bars = max(
                0, int(self.config.get("indicator_min_position_hold_bars") or 0)
            )
        except Exception:
            self._indicator_min_hold_bars = 0
        try:
            self._indicator_flip_confirm_bars = max(
                1, int(self.config.get("indicator_flip_confirmation_bars") or 1)
            )
        except Exception:
            self._indicator_flip_confirm_bars = 1
        self._indicator_last_action: dict[tuple[str, str, str], dict[str, float]] = {}
        self._indicator_signal_tracker: dict[tuple[str, str, str], dict[str, float | int | str]] = {}

    def _notify_interval_closed(self, symbol: str, interval: str, position_side: str, **extra):
        if not self.trade_cb:
            return
        try:
            info = {
                'symbol': symbol,
                'interval': interval,
                'side': position_side,
                'position_side': position_side,
                'event': 'close_interval',
                'status': 'closed',
                'ok': True,
                'time': datetime.now().astimezone().strftime('%Y-%m-%d %H:%M:%S')
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
                log_parts.append(f"size≈{qty_val * ref_price:.2f} USDT")
            margin_val = _safe_float(info.get("margin_usdt"))
            if margin_val > 0.0:
                log_parts.append(f"margin≈{margin_val:.2f} USDT")
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

    def _log_latency_metric(self, symbol: str, interval: str, label: str, latency_seconds: float) -> None:
        try:
            latency_seconds = max(0.0, float(latency_seconds))
        except Exception:
            latency_seconds = 0.0
        try:
            self.log(
                f"{symbol}@{interval} {label} signal→order latency: "
                f"{latency_seconds * 1000.0:.0f} ms ({latency_seconds:.3f}s)."
            )
        except Exception:
            pass

    @staticmethod
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
        import time as _time  # local import to avoid circular references in tests

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
            payload["fills_meta"].update({
                "trade_count": fills_info.get("trade_count"),
                "order_id": fills_info.get("order_id"),
            })

        payload["event_id"] = f"{ledger_id or symbol}-{int(_time.time() * 1000)}"
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

    @staticmethod
    def _normalize_signature_tuple(signature: Iterable[str] | None) -> tuple[str, ...] | None:
        parts: list[str] = []
        for label in signature or []:
            text = str(label or "").strip().lower()
            if not text:
                continue
            if text.startswith("slot"):
                parts.append(text)
            else:
                parts.append(_canonical_indicator_token(text) or text)
        if not parts:
            return None
        parts.sort()
        return tuple(parts)

    @staticmethod
    def _normalize_signature_tokens_no_slots(signature: Iterable[str] | None) -> tuple[str, ...]:
        normalized = StrategyEngine._normalize_signature_tuple(signature) or ()
        filtered: list[str] = []
        for token in normalized:
            token_norm = str(token or "").strip().lower()
            if not token_norm or token_norm.startswith("slot"):
                continue
            canon = _canonical_indicator_token(token_norm) or token_norm
            filtered.append(canon)
        return tuple(filtered)

    @staticmethod
    def _normalize_indicator_token_list(tokens: Iterable[str] | str | None) -> list[str]:
        if tokens is None:
            return []
        if isinstance(tokens, str):
            iterable = [tokens]
        else:
            iterable = list(tokens)
        normalized = StrategyEngine._normalize_signature_tokens_no_slots(iterable)
        return list(dict.fromkeys(normalized))

    def _indicator_state_entry(self, symbol: str, interval: str, indicator_key: str) -> dict[str, set[str]]:
        sym = str(symbol or "").upper()
        iv = str(interval or "").strip().lower()
        ind = _canonical_indicator_token(indicator_key) or ""
        key = (sym, iv, ind)
        with self._indicator_state_lock:
            state = self._indicator_state.get(key)
            if not isinstance(state, dict):
                state = {"BUY": set(), "SELL": set()}
                self._indicator_state[key] = state
            else:
                state.setdefault("BUY", set())
                state.setdefault("SELL", set())
            return state

    def _trade_book_key(
        self,
        symbol: str,
        interval: str | None,
        indicator_key: str | None,
        side: str,
    ) -> tuple[str, str, str, str] | None:
        indicator_norm = _canonical_indicator_token(indicator_key) or ""
        if not indicator_norm:
            return None
        sym_norm = str(symbol or "").upper()
        interval_norm = str(interval or "").strip().lower() or "default"
        side_norm = "BUY" if str(side or "").upper() in {"BUY", "LONG"} else "SELL"
        return (sym_norm, interval_norm, indicator_norm, side_norm)

    def _trade_book_add_entry(
        self,
        symbol: str,
        interval: str | None,
        indicator_key: str,
        side: str,
        ledger_id: str | None,
        qty: float | None,
        entry: dict,
    ) -> None:
        if not ledger_id:
            return
        key = self._trade_book_key(symbol, interval, indicator_key, side)
        if not key:
            return
        try:
            qty_val = max(0.0, float(qty or 0.0))
        except Exception:
            qty_val = 0.0
        if qty_val <= 0.0:
            return
        meta = {
            "ledger_id": ledger_id,
            "qty": qty_val,
            "timestamp": float(entry.get("timestamp") or time.time()),
        }
        try:
            meta["entry_price"] = float(entry.get("entry_price") or 0.0)
        except Exception:
            pass
        try:
            meta["margin_usdt"] = float(entry.get("margin_usdt") or 0.0)
        except Exception:
            pass
        with self._trade_book_lock:
            bucket = self._trade_book.setdefault(key, {})
            bucket[ledger_id] = meta

    def _trade_book_remove_entry(
        self,
        symbol: str,
        interval: str | None,
        indicator_key: str,
        side: str,
        ledger_id: str | None,
    ) -> None:
        if not ledger_id:
            return
        key = self._trade_book_key(symbol, interval, indicator_key, side)
        if not key:
            return
        with self._trade_book_lock:
            bucket = self._trade_book.get(key)
            if not bucket:
                return
            bucket.pop(ledger_id, None)
            if not bucket:
                self._trade_book.pop(key, None)

    def _trade_book_update_qty(
        self,
        symbol: str,
        interval: str | None,
        indicator_key: str,
        side: str,
        ledger_id: str | None,
        qty: float,
    ) -> None:
        if not ledger_id:
            return
        key = self._trade_book_key(symbol, interval, indicator_key, side)
        if not key:
            return
        with self._trade_book_lock:
            bucket = self._trade_book.get(key)
            if not bucket:
                return
            meta = bucket.get(ledger_id)
            if isinstance(meta, dict):
                try:
                    meta["qty"] = max(0.0, float(qty or 0.0))
                except Exception:
                    meta["qty"] = 0.0

    def _trade_book_entries(
        self,
        symbol: str,
        interval: str | None,
        indicator_key: str | None,
        side: str,
    ) -> list[dict]:
        key = self._trade_book_key(symbol, interval, indicator_key, side)
        if not key:
            return []
        with self._trade_book_lock:
            bucket = self._trade_book.get(key)
            if not bucket:
                return []
            entries: list[dict] = []
            for ledger_id, meta in bucket.items():
                if not ledger_id:
                    continue
                record = dict(meta or {})
                record.setdefault("ledger_id", ledger_id)
                entries.append(record)
        entries.sort(key=lambda rec: float(rec.get("timestamp") or 0.0))
        return entries

    def _trade_book_total_qty(
        self,
        symbol: str,
        interval: str | None,
        indicator_key: str,
        side: str,
    ) -> float | None:
        key = self._trade_book_key(symbol, interval, indicator_key, side)
        if not key:
            return None
        with self._trade_book_lock:
            bucket = self._trade_book.get(key)
            if not bucket:
                return None
            total = 0.0
            for meta in bucket.values():
                try:
                    total += max(0.0, float(meta.get("qty") or 0.0))
                except Exception:
                    continue
            return total

    def _indicator_trade_book_qty(
        self,
        symbol: str,
        interval: str | None,
        indicator_key: str,
        side: str,
    ) -> float:
        key = _canonical_indicator_token(indicator_key) or indicator_key
        if not key:
            return 0.0
        entries = self._trade_book_entries(symbol, interval, key, side)
        total = 0.0
        for meta in entries:
            try:
                total += max(0.0, float(meta.get("qty") or 0.0))
            except Exception:
                continue
        return total

    def _trade_book_has_entries(
        self,
        symbol: str,
        interval: str | None,
        indicator_key: str,
        side: str,
    ) -> bool:
        key = self._trade_book_key(symbol, interval, indicator_key, side)
        if not key:
            return False
        with self._trade_book_lock:
            bucket = self._trade_book.get(key)
            if not bucket:
                return False
            for meta in bucket.values():
                try:
                    if max(0.0, float(meta.get("qty") or 0.0)) > 0.0:
                        return True
                except Exception:
                    continue
        return False

    def _indicator_has_open(self, symbol: str, interval: str, indicator_key: str, side: str) -> bool:
        side_norm = "BUY" if str(side or "").upper() in {"BUY", "LONG"} else "SELL"
        sym = str(symbol or "").upper()
        iv = str(interval or "").strip().lower()
        indicator_norm = _canonical_indicator_token(indicator_key) or ""
        key = (sym, iv, indicator_norm)
        if self._trade_book_has_entries(symbol, interval, indicator_norm, side):
            return True
        state = None
        with self._indicator_state_lock:
            raw = self._indicator_state.get(key)
            if isinstance(raw, dict):
                state = raw
                ids = state.get(side_norm)
                if ids:
                    return True
        return bool(self._iter_indicator_entries(symbol, interval, indicator_key, side))

    def _indicator_get_ledger_ids(self, symbol: str, interval: str, indicator_key: str, side: str) -> list[str]:
        side_norm = "BUY" if str(side or "").upper() in {"BUY", "LONG"} else "SELL"
        sym = str(symbol or "").upper()
        iv = str(interval or "").strip().lower()
        indicator_norm = _canonical_indicator_token(indicator_key) or ""
        key = (sym, iv, indicator_norm)
        ids: set[str] | None = None
        with self._indicator_state_lock:
            state = self._indicator_state.get(key)
            if isinstance(state, dict):
                ids = state.get(side_norm)
        collected: list[str] = []
        if ids:
            collected.extend(list(ids))
        for _, entry in self._iter_indicator_entries(symbol, interval, indicator_key, side):
            ledger = entry.get("ledger_id")
            if ledger and ledger not in collected:
                collected.append(ledger)
        return collected

    def _iter_indicator_entries(
        self,
        symbol: str,
        interval: str,
        indicator_key: str,
        side: str,
    ) -> list[tuple[tuple[str, str, str], dict]]:
        sym_norm = str(symbol or "").upper()
        target_tokens = self._tokenize_interval_label(interval)
        indicator_norm = _canonical_indicator_token(indicator_key) or ""
        side_norm = "BUY" if str(side or "").upper() in {"BUY", "LONG"} else "SELL"
        if not indicator_norm:
            return []
        matches: list[tuple[tuple[str, str, str], dict]] = []
        for (leg_sym, leg_iv, leg_side), _ in list(self._leg_ledger.items()):
            try:
                if str(leg_sym or "").upper() != sym_norm:
                    continue
                leg_tokens = self._tokenize_interval_label(leg_iv)
                if target_tokens != {'-'} and leg_tokens.isdisjoint(target_tokens):
                    continue
                leg_side_norm = "BUY" if str(leg_side or "").upper() in {"BUY", "LONG"} else "SELL"
                if leg_side_norm != side_norm:
                    continue
                entries = self._leg_entries((leg_sym, leg_iv, leg_side))
                if not entries:
                    continue
                for entry in entries:
                    try:
                        qty_val = max(0.0, float(entry.get("qty") or 0.0))
                    except Exception:
                        qty_val = 0.0
                    if qty_val <= 0.0:
                        continue
                    sig_tuple = self._normalize_signature_tuple(
                        entry.get("trigger_signature") or entry.get("trigger_indicators")
                    )
                    if not sig_tuple:
                        continue
                    if indicator_norm in sig_tuple:
                        matches.append(((leg_sym, leg_iv, leg_side), entry))
            except Exception:
                continue
        return matches

    def _indicator_open_qty(
        self,
        symbol: str,
        interval: str,
        indicator_key: str,
        side: str,
        interval_aliases: Iterable[str] | None = None,
    ) -> float:
        target_tokens = self._tokenize_interval_label(interval)
        if interval_aliases:
            for alias in interval_aliases:
                norm = self._normalize_interval_token(alias)
                if norm:
                    target_tokens.add(norm)
        indicator_norm = _canonical_indicator_token(indicator_key) or indicator_key
        indicator_lookup_key = indicator_norm or indicator_key
        qty_from_book = self._trade_book_total_qty(symbol, interval, indicator_lookup_key, side)
        if qty_from_book is not None:
            return qty_from_book
        total = 0.0
        try:
            for (leg_sym, leg_iv, leg_side), entry in self._iter_indicator_entries(symbol, interval, indicator_lookup_key, side):
                leg_tokens = self._tokenize_interval_label(leg_iv)
                if target_tokens and target_tokens != {'-'} and leg_tokens.isdisjoint(target_tokens):
                    continue
                try:
                    total += max(0.0, float(entry.get("qty") or 0.0))
                except Exception:
                    continue
        except Exception:
            return 0.0
        return total

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

    @staticmethod
    def _interval_seconds_value(interval_value: str | None) -> float:
        try:
            return float(_interval_to_seconds(str(interval_value or "1m")))
        except Exception:
            return 60.0

    def _indicator_hold_ready(
        self,
        entry_ts: float | int | None,
        symbol: str,
        interval: str | None,
        indicator_key: str | None,
        side_label: str,
        interval_seconds: float,
        now_ts: float | None = None,
        *,
        ignore_hold: bool = False,
    ) -> bool:
        if ignore_hold:
            return True
        base_hold = max(0.0, getattr(self, "_indicator_min_hold_seconds", 0.0))
        try:
            interval_seconds = max(1.0, float(interval_seconds or 0.0))
        except Exception:
            interval_seconds = 60.0
        bars_hold = max(0, getattr(self, "_indicator_min_hold_bars", 0))
        effective_hold = max(base_hold, interval_seconds * bars_hold)
        if effective_hold <= 0.0:
            return True
        try:
            ts_val = float(entry_ts or 0.0)
        except Exception:
            ts_val = 0.0
        if ts_val <= 0.0:
            return True
        if now_ts is None:
            now_ts = time.time()
        age = max(0.0, now_ts - ts_val)
        if age >= effective_hold:
            return True
        remaining = max(0.0, effective_hold - age)
        try:
            indicator_label = str(indicator_key or "").upper() or "<indicator>"
            self.log(
                f"{str(symbol or '').upper()}@{interval or 'default'} hold guard: waiting {remaining:.1f}s "
                f"before flipping {indicator_label} {side_label}."
            )
        except Exception:
            pass
        return False

    def _indicator_signal_confirmation_ready(
        self,
        symbol: str,
        interval: str | None,
        indicator_key: str,
        action: str,
        interval_seconds: float,
        signal_ts: float | None,
    ) -> bool:
        confirm_req = max(1, getattr(self, "_indicator_flip_confirm_bars", 1))
        if confirm_req <= 1:
            return True
        action_norm = str(action or "").strip().lower()
        if action_norm not in {"buy", "sell"}:
            return True
        sym_norm = str(symbol or "").upper()
        interval_norm = str(interval or "").strip().lower() or "default"
        indicator_norm = _canonical_indicator_token(indicator_key) or ""
        if not indicator_norm:
            return True
        key = (sym_norm, interval_norm, indicator_norm)
        tracker = self._indicator_signal_tracker.get(key)
        now_ts = signal_ts or time.time()
        reset_window = max(1.0, float(interval_seconds or 0.0)) * max(confirm_req + 1, 2)
        if tracker:
            try:
                last_ts = float(tracker.get("ts") or 0.0)
            except Exception:
                last_ts = 0.0
            if last_ts and now_ts - last_ts > reset_window:
                tracker = None
        if tracker and tracker.get("direction") == action_norm:
            count = int(tracker.get("count", 0)) + 1
        else:
            count = 1
        tracker = {"direction": action_norm, "count": count, "ts": now_ts}
        self._indicator_signal_tracker[key] = tracker
        if count >= confirm_req:
            return True
        try:
            self.log(
                f"{symbol}@{interval or 'default'} {indicator_key} {action_norm.upper()} "
                f"confirmation {count}/{confirm_req} – waiting additional bar(s)."
            )
        except Exception:
            pass
        return False

    def _guard_mark_leg_closed(self, leg_key: tuple[str, str, str]) -> None:
        guard_obj = getattr(self, "guard", None)
        if not guard_obj or not hasattr(guard_obj, "mark_closed"):
            return
        try:
            symbol, interval, side = leg_key
            side_norm = "BUY" if str(side or "").upper() in {"BUY", "LONG"} else "SELL"
            guard_obj.mark_closed(symbol, interval, side_norm)
        except Exception:
            pass

    def _indicator_cooldown_remaining(
        self,
        symbol: str,
        interval: str | None,
        indicator_key: str | None,
        next_side: str,
        interval_seconds: float,
        now_ts: float | None = None,
    ) -> float:
        """Return remaining cooldown time before the indicator can flip sides."""
        try:
            interval_seconds = max(1.0, float(interval_seconds or 0.0))
        except Exception:
            interval_seconds = 60.0
        cooldown_window = max(
            float(getattr(self, "_indicator_flip_cooldown_seconds", 0.0)),
            float(max(0, getattr(self, "_indicator_flip_cooldown_bars", 0))) * interval_seconds,
        )
        if cooldown_window <= 0.0:
            return 0.0
        sym_norm = str(symbol or "").upper()
        interval_norm = str(interval or "").strip().lower() or "default"
        indicator_norm = _canonical_indicator_token(indicator_key) or ""
        if not indicator_norm:
            return 0.0
        last = self._indicator_last_action.get((sym_norm, interval_norm, indicator_norm))
        if not isinstance(last, dict):
            return 0.0
        last_side = str(last.get("side") or "").upper()
        if last_side == str(next_side or "").upper():
            return 0.0
        try:
            last_ts = float(last.get("ts") or 0.0)
        except Exception:
            last_ts = 0.0
        if last_ts <= 0.0:
            return 0.0
        if now_ts is None:
            now_ts = time.time()
        elapsed = max(0.0, float(now_ts) - last_ts)
        remaining = cooldown_window - elapsed
        return max(0.0, remaining)

    def _indicator_register_entry(
        self,
        symbol: str,
        interval: str,
        indicator_key: str,
        side: str,
        ledger_id: str | None,
    ) -> None:
        if not ledger_id:
            return
        side_norm = "BUY" if str(side or "").upper() in {"BUY", "LONG"} else "SELL"
        state = self._indicator_state_entry(symbol, interval, indicator_key)
        with self._indicator_state_lock:
            state.setdefault(side_norm, set()).add(ledger_id)


    def _indicator_unregister_entry(
        self,
        symbol: str,
        interval: str,
        indicator_key: str,
        side: str,
        ledger_id: str | None,
    ) -> None:
        if not ledger_id:
            return
        side_norm = "BUY" if str(side or "").upper() in {"BUY", "LONG"} else "SELL"
        state = self._indicator_state_entry(symbol, interval, indicator_key)
        with self._indicator_state_lock:
            ids = state.get(side_norm)
            if isinstance(ids, set):
                ids.discard(ledger_id)

    def _indicator_token_from_signature(
        self,
        signature: Iterable[str] | None,
        fallback_labels: Iterable[str] | None = None,
    ) -> str | None:
        """
        Extract the canonical indicator token from a tuple/list of signature labels.
        Slot markers (e.g. slot0) are ignored so we can match the logical indicator.
        """
        sig_tuple = self._normalize_signature_tuple(signature)
        if not sig_tuple and fallback_labels:
            sig_tuple = self._normalize_signature_tuple(fallback_labels)
        if not sig_tuple:
            return None
        for token in sig_tuple:
            token_norm = str(token or "").strip().lower()
            if token_norm and not token_norm.startswith("slot"):
                return _canonical_indicator_token(token_norm) or token_norm
        fallback = sig_tuple[0] if sig_tuple else None
        return _canonical_indicator_token(fallback) or (fallback if isinstance(fallback, str) else None)

    def _extract_indicator_keys(self, entry: dict | None) -> list[str]:
        if not isinstance(entry, dict):
            return []
        key_override = entry.get("indicator_keys")
        if isinstance(key_override, (list, tuple)):
            normalized = []
            for token in key_override:
                canon = _canonical_indicator_token(token)
                if canon:
                    normalized.append(canon)
            if normalized:
                return list(dict.fromkeys(normalized))
        sig = entry.get("trigger_signature") or entry.get("trigger_indicators")
        sig_tuple = self._normalize_signature_tuple(sig if isinstance(sig, Iterable) else [])
        if not sig_tuple:
            return []
        keys: list[str] = []
        seen: set[str] = set()
        for token in sig_tuple:
            token_str = str(token or "").strip().lower()
            if token_str and not token_str.startswith("slot"):
                canon = _canonical_indicator_token(token_str) or token_str
                if canon not in seen:
                    keys.append(canon)
                    seen.add(canon)
        if not keys and sig_tuple:
            fallback = _canonical_indicator_token(sig_tuple[0]) or str(sig_tuple[0]).strip().lower()
            if fallback:
                keys.append(fallback)
        return keys

    def _extract_indicator_key(self, entry: dict) -> str | None:
        keys = self._extract_indicator_keys(entry)
        return keys[0] if keys else None

    @staticmethod
    def _normalize_interval_token(value: str | None) -> str | None:
        token = str(value or "").strip().lower()
        if not token:
            return None
        token = token.replace(" ", "")
        replacements = {
            "minutes": "m",
            "minute": "m",
            "mins": "m",
            "min": "m",
            "seconds": "s",
            "second": "s",
            "secs": "s",
            "sec": "s",
            "hours": "h",
            "hour": "h",
            "hrs": "h",
            "hr": "h",
            "days": "d",
            "day": "d",
        }
        for src, dst in replacements.items():
            if token.endswith(src):
                token = token[: -len(src)] + dst
                break
        return token or None

    @staticmethod
    def _extract_interval_tokens_from_labels(labels: Iterable[str] | None) -> set[str]:
        tokens: set[str] = set()
        if not labels:
            return tokens
        pattern = re.compile(r"@([0-9]+[smhd])", re.IGNORECASE)
        for label in labels:
            if not isinstance(label, str):
                continue
            for match in pattern.finditer(label):
                norm = StrategyEngine._normalize_interval_token(match.group(1))
                if norm:
                    tokens.add(norm)
        return tokens

    @classmethod
    def _tokenize_interval_label(cls, interval_value: str | None) -> set[str]:
        tokens: set[str] = set()
        if interval_value is None:
            return {'-'}
        for part in str(interval_value).split(','):
            norm = cls._normalize_interval_token(part)
            if norm:
                tokens.add(norm)
        if not tokens:
            tokens.add('-')
        return tokens

    def _bump_symbol_signature_open(
        self,
        symbol: str,
        interval: str | None,
        side: str,
        signature: Iterable[str] | None,
        delta: int,
    ) -> None:
        sig_tuple = self._normalize_signature_tuple(signature)
        if sig_tuple is None:
            return
        key = (str(symbol or "").upper(), str(side or "").upper(), sig_tuple)
        with self._symbol_signature_lock:
            current = self._symbol_signature_open.get(key, 0) + int(delta)
            if current <= 0:
                self._symbol_signature_open.pop(key, None)
            else:
                self._symbol_signature_open[key] = current

    def _symbol_signature_active(
        self,
        symbol: str,
        side: str,
        signature: Iterable[str] | None,
        interval: str | None = None,
    ) -> bool:
        sig_tuple = self._normalize_signature_tuple(signature)
        if sig_tuple is None:
            return False
        if len(sig_tuple) == 1:
            return False
        key = (str(symbol or "").upper(), str(side or "").upper(), sig_tuple)
        with self._symbol_signature_lock:
            return self._symbol_signature_open.get(key, 0) > 0

    def _close_indicator_positions(
        self,
        cw: dict,
        interval: str,
        indicator_key: str,
        side_label: str,
        position_side: str | None,
        signature_hint: tuple[str, ...] | None = None,
        *,
        ignore_hold: bool = False,
        interval_aliases: Iterable[str] | None = None,
        qty_limit: float | None = None,
    ) -> tuple[int, float]:
        symbol = cw["symbol"]
        interval_text = str(interval or "").strip()
        indicator_norm = _canonical_indicator_token(indicator_key) or str(indicator_key or "").strip().lower()
        if not indicator_norm:
            indicator_norm = str(indicator_key or "").strip().lower()
        indicator_lookup_key = indicator_norm or indicator_key
        interval_tokens = self._tokenize_interval_label(interval_text)
        if interval_aliases:
            for alias in interval_aliases:
                norm = self._normalize_interval_token(alias)
                if norm:
                    interval_tokens.add(norm)
        interval_lower = interval_text.lower()
        interval_has_filter = interval_tokens != {"-"}
        ledger_entries = self._trade_book_entries(symbol, interval, indicator_lookup_key, side_label)
        ledger_ids = [entry.get("ledger_id") for entry in ledger_entries if entry.get("ledger_id")]
        ledger_ids = [lid for lid in ledger_ids if lid]
        if not ledger_ids:
            ledger_ids = self._indicator_get_ledger_ids(symbol, interval, indicator_lookup_key, side_label)
        if (not ledger_ids) and signature_hint:
            signature_hint = tuple(
                str(token or "").strip().lower() for token in signature_hint if str(token or "").strip()
            )
            if signature_hint:
                extra_ids: list[str] = []
                for _, entry in self._iter_indicator_entries(symbol, interval, indicator_key, side_label):
                    sig_tuple = StrategyEngine._normalize_signature_tokens_no_slots(
                        entry.get("trigger_signature") or entry.get("trigger_indicators")
                    )
                    if signature_hint:
                        hint_norm = tuple(
                            str(token or "").strip().lower()
                            for token in signature_hint
                            if str(token or "").strip()
                        )
                        if hint_norm:
                            sig_set = set(sig_tuple or ())
                            if not set(hint_norm).issubset(sig_set):
                                continue
                    ledger = entry.get("ledger_id")
                    if ledger and ledger not in ledger_ids and ledger not in extra_ids:
                        extra_ids.append(ledger)
                if extra_ids:
                    ledger_ids.extend(extra_ids)
        close_side = "SELL" if str(side_label).upper() in {"BUY", "LONG"} else "BUY"
        side_norm = "BUY" if str(side_label).upper() in {"BUY", "LONG"} else "SELL"
        closed_count = 0
        total_qty_closed = 0.0
        limit_remaining = None
        limit_tol = 1e-9
        if qty_limit is not None:
            try:
                limit_remaining = max(0.0, float(qty_limit))
            except Exception:
                limit_remaining = 0.0
        for ledger_id in list(ledger_ids):
            if limit_remaining is not None and limit_remaining <= limit_tol:
                break
            leg_key = self._ledger_index.get(ledger_id)
            if not leg_key:
                continue
            entries = self._leg_entries(leg_key)
            target_entry = None
            for entry in entries:
                if entry.get("ledger_id") == ledger_id:
                    target_entry = entry
                    break
            if not target_entry:
                continue
            try:
                qty_snapshot = max(0.0, float(target_entry.get("qty") or 0.0))
            except Exception:
                qty_snapshot = 0.0
            try:
                interval_seconds_entry = self._interval_seconds_value(leg_key[1])
                if not self._indicator_hold_ready(
                    target_entry.get("timestamp"),
                    symbol,
                    leg_key[1],
                    indicator_key,
                    side_label,
                    interval_seconds_entry,
                    now_ts=None,
                    ignore_hold=ignore_hold,
                ):
                    continue
                cw_clone = dict(cw)
                cw_clone["interval"] = leg_key[1]
                qty_request = limit_remaining if limit_remaining is not None else None
                closed_qty = self._close_leg_entry(
                    cw_clone,
                    leg_key,
                    target_entry,
                    side_norm,
                    close_side,
                    position_side,
                    loss_usdt=0.0,
                    price_pct=0.0,
                    margin_pct=0.0,
                    qty_limit=qty_request,
                )
                if closed_qty > 0.0:
                    closed_count += 1
                    total_qty_closed += closed_qty
                    if limit_remaining is not None:
                        limit_remaining = max(0.0, limit_remaining - closed_qty)
            except Exception:
                continue
            if limit_remaining is not None and limit_remaining <= limit_tol:
                break
        if closed_count <= 0:
            targeted_entries: list[tuple[tuple[str, str, str], dict]] = []
            for leg_key, leg_state in list(self._leg_ledger.items()):
                leg_sym, leg_interval, leg_side = leg_key
                if str(leg_sym or "").upper() != symbol:
                    continue
                leg_interval_norm = str(leg_interval or "").strip()
                leg_interval_tokens = self._tokenize_interval_label(leg_interval_norm)
                if interval_tokens != {'-'} and leg_interval_tokens.isdisjoint(interval_tokens):
                    continue
                leg_side_norm = str(leg_side or "").upper()
                if leg_side_norm in {"LONG", "SHORT"}:
                    leg_side_norm = "BUY" if leg_side_norm == "LONG" else "SELL"
                if leg_side_norm != side_norm:
                    continue
                entries = self._leg_entries(leg_key)
                if not entries:
                    continue
                for entry in entries:
                    keys_for_entry = self._extract_indicator_keys(entry)
                    if indicator_lookup_key not in keys_for_entry:
                        continue
                    targeted_entries.append((leg_key, entry))
            if targeted_entries:
                for leg_key, entry in targeted_entries:
                    if limit_remaining is not None and limit_remaining <= limit_tol:
                        break
                    try:
                        qty_snapshot = max(0.0, float(entry.get("qty") or 0.0))
                    except Exception:
                        qty_snapshot = 0.0
                    try:
                        try:
                            interval_seconds_entry = float(_interval_to_seconds(str(leg_key[1] or "1m")))
                        except Exception:
                            interval_seconds_entry = 60.0
                        if not self._indicator_hold_ready(
                            entry.get("timestamp"),
                            symbol,
                            leg_key[1],
                            indicator_key,
                            side_label,
                            interval_seconds_entry,
                            now_ts=None,
                            ignore_hold=ignore_hold,
                        ):
                            continue
                        cw_clone = dict(cw)
                        cw_clone["interval"] = leg_key[1]
                        qty_request = limit_remaining if limit_remaining is not None else None
                        closed_qty = self._close_leg_entry(
                            cw_clone,
                            leg_key,
                            entry,
                            side_norm,
                            "SELL" if side_norm == "BUY" else "BUY",
                            position_side,
                            loss_usdt=0.0,
                            price_pct=0.0,
                            margin_pct=0.0,
                            qty_limit=qty_request,
                        )
                        if closed_qty > 0.0:
                            closed_count += 1
                            total_qty_closed += closed_qty
                            if limit_remaining is not None:
                                limit_remaining = max(0.0, limit_remaining - closed_qty)
                    except Exception:
                        continue
                if closed_count > 0:
                    return closed_count, total_qty_closed

        if closed_count <= 0:
            fallback_entries: list[tuple[tuple[str, str, str], str | None, float]] = []
            fallback_qty_target = 0.0
            for leg_key, leg_state in list(self._leg_ledger.items()):
                leg_sym, leg_interval, leg_side = leg_key
                if str(leg_sym or "").upper() != symbol:
                    continue
                leg_interval_norm = str(leg_interval or "").strip()
                leg_tokens = self._tokenize_interval_label(leg_interval_norm)
                if interval_has_filter and leg_tokens.isdisjoint(interval_tokens):
                    continue
                leg_side_norm = "BUY" if str(leg_side or "").upper() in {"BUY", "LONG"} else "SELL"
                if leg_side_norm != side_norm:
                    continue
                entries = self._leg_entries(leg_key)
                if not entries:
                    continue
                for entry in entries:
                    keys_for_entry = self._extract_indicator_keys(entry)
                    if indicator_lookup_key not in keys_for_entry:
                        continue
                    try:
                        interval_seconds_entry = float(_interval_to_seconds(str(leg_key[1] or "1m")))
                    except Exception:
                        interval_seconds_entry = 60.0
                    if not self._indicator_hold_ready(
                        entry.get("timestamp"),
                        leg_sym,
                        leg_key[1],
                        indicator_key,
                        side_norm,
                        interval_seconds_entry,
                        now_ts=None,
                        ignore_hold=ignore_hold,
                    ):
                        continue
                    try:
                        qty_val = max(0.0, float(entry.get("qty") or 0.0))
                        fallback_qty_target += qty_val
                    except Exception:
                        continue
                    fallback_entries.append((leg_key, entry.get("ledger_id"), qty_val))
            live_qty = 0.0
            try:
                live_qty = max(
                    0.0,
                    float(self._current_futures_position_qty(symbol, side_norm, position_side)),
                )
            except Exception:
                live_qty = 0.0
            qty_limit_hint = None
            if qty_limit is not None:
                try:
                    qty_limit_hint = max(0.0, float(qty_limit))
                except Exception:
                    qty_limit_hint = 0.0
            fallback_qty_goal = fallback_qty_target
            if fallback_qty_goal <= 0.0:
                fallback_qty_goal = qty_limit_hint or 0.0
            qty_to_close = min(live_qty, fallback_qty_goal) if fallback_qty_goal > 0.0 else 0.0
            if limit_remaining is not None:
                qty_to_close = min(qty_to_close, limit_remaining)
            if fallback_entries and qty_to_close > 0.0:
                close_side = "SELL" if side_norm == "BUY" else "BUY"
                try:
                    res = self.binance.close_futures_leg_exact(
                        symbol,
                        qty_to_close,
                        side=close_side,
                        position_side=position_side,
                    )
                except Exception as exc:
                    res = {"ok": False, "error": str(exc)}
                if isinstance(res, dict) and res.get("ok"):
                    try:
                        executed_qty_val = float(
                            self._order_field(res, "executedQty", "cumQty", "cumQuantity", "origQty") or 0.0
                        )
                    except Exception:
                        executed_qty_val = 0.0
                    if executed_qty_val <= 0.0 and isinstance(res.get("fills"), dict):
                        try:
                            executed_qty_val = float(res["fills"].get("filled_qty") or 0.0)
                        except Exception:
                            executed_qty_val = 0.0
                    qty_recorded = executed_qty_val if executed_qty_val > 0.0 else qty_to_close
                    total_qty_closed += qty_recorded
                    if limit_remaining is not None:
                        limit_remaining = max(0.0, limit_remaining - qty_recorded)
                    entries_removed = 0
                    partial_updates = 0
                    affected_leg_keys: set[tuple[str, str, str]] = set()
                    qty_remaining = qty_recorded
                    tol = max(1e-9, qty_recorded * 1e-6)
                    for leg_key, ledger_token, entry_qty in fallback_entries:
                        if qty_remaining <= tol:
                            break
                        affected_leg_keys.add(leg_key)
                        consume = min(entry_qty, qty_remaining)
                        if ledger_token:
                            if entry_qty <= tol or consume >= entry_qty - tol:
                                self._remove_leg_entry(leg_key, ledger_token)
                                entries_removed += 1
                            else:
                                self._decrement_leg_entry_qty(leg_key, ledger_token, entry_qty, entry_qty - consume)
                                partial_updates += 1
                            qty_remaining = max(0.0, qty_remaining - consume)
                        else:
                            try:
                                self.log(
                                    f"{symbol}@{interval_text or 'default'} fallback removal missing ledger id for "
                                    f"{leg_key[0]}@{leg_key[1]} {indicator_key}; purging leg."
                                )
                            except Exception:
                                pass
                            self._remove_leg_entry(leg_key, None)
                            entries_removed += 1
                            qty_remaining = max(0.0, qty_remaining - entry_qty)
                    if qty_remaining > tol:
                        try:
                            self.log(
                                f"{symbol}@{interval_text or 'default'} fallback close executed {qty_recorded:.10f} "
                                f"but only reconciled {qty_recorded - qty_remaining:.10f}; residual {qty_remaining:.10f} "
                                f"will be flushed on next sync."
                            )
                        except Exception:
                            pass
                    for leg_key in affected_leg_keys:
                        if not self._leg_entries(leg_key):
                            self._guard_mark_leg_closed(leg_key)
                    closed_count = max(1, entries_removed + partial_updates)
                    try:
                        note_parts: list[str] = []
                        if entries_removed:
                            label = "entry" if entries_removed == 1 else "entries"
                            note_parts.append(f"{entries_removed} {label}")
                        if partial_updates:
                            label = "entry" if partial_updates == 1 else "entries"
                            note_parts.append(f"{partial_updates} {label} (partial)")
                        entry_note = ", ".join(note_parts) if note_parts else "entries"
                        self.log(
                            f"{symbol}@{interval_text or 'default'} fallback closed {qty_recorded:.10f} "
                            f"{side_norm} {entry_note} for indicator {indicator_key}."
                        )
                    except Exception:
                        pass
        return closed_count, total_qty_closed


    def _update_leg_snapshot(self, leg_key, leg: dict | None) -> None:
        if not isinstance(leg, dict):
            self._leg_ledger.pop(leg_key, None)
            return
        entries_param = leg.get("entries") if isinstance(leg, dict) else None
        if isinstance(entries_param, list):
            provided_entries = [entry for entry in entries_param if isinstance(entry, dict)]
            entries = provided_entries if provided_entries else self._leg_entries(leg_key)
        else:
            entries = self._leg_entries(leg_key)
        total_qty = 0.0
        weighted_notional = 0.0
        total_margin = 0.0
        last_entry: dict | None = None
        for entry in entries:
            qty = max(0.0, float(entry.get("qty") or 0.0))
            price = max(0.0, float(entry.get("entry_price") or 0.0))
            margin = max(0.0, float(entry.get("margin_usdt") or 0.0))
            total_qty += qty
            weighted_notional += qty * price
            total_margin += margin
            last_entry = entry
        if total_qty > 0.0:
            leg["qty"] = total_qty
            leg["entry_price"] = weighted_notional / total_qty if weighted_notional > 0.0 else leg.get("entry_price", 0.0)
        else:
            leg["qty"] = 0.0
            leg["entry_price"] = 0.0
        leg["margin_usdt"] = total_margin
        if last_entry:
            if "ledger_id" in last_entry:
                leg["ledger_id"] = last_entry.get("ledger_id")
            if last_entry.get("leverage") is not None:
                leg["leverage"] = last_entry.get("leverage")
        leg["entries"] = entries
        leg["timestamp"] = time.time()
        self._leg_ledger[leg_key] = leg

    def _append_leg_entry(self, leg_key, entry: dict) -> None:
        leg = self._leg_ledger.get(leg_key, {})
        entries = self._leg_entries(leg_key)
        entries.append(entry)
        leg["entries"] = entries
        self._update_leg_snapshot(leg_key, leg)
        self._last_order_time[leg_key] = time.time()
        try:
            signature_labels = entry.get("trigger_signature") or entry.get("trigger_indicators")
            self._bump_symbol_signature_open(leg_key[0], leg_key[1], leg_key[2], signature_labels, +1)
        except Exception:
            pass
        indicator_keys: list[str] | None = None
        try:
            ledger_id = entry.get("ledger_id")
            if ledger_id:
                self._ledger_index[ledger_id] = leg_key
            indicator_keys = self._extract_indicator_keys(entry)
            if ledger_id and indicator_keys:
                for indicator_key in indicator_keys:
                    self._indicator_register_entry(leg_key[0], leg_key[1], indicator_key, leg_key[2], ledger_id)
                    self._trade_book_add_entry(
                        leg_key[0],
                        leg_key[1],
                        indicator_key,
                        leg_key[2],
                        ledger_id,
                        entry.get("qty"),
                        entry,
                    )
        except Exception:
            indicator_keys = None
        try:
            if indicator_keys:
                interval_norm = str(leg_key[1] or "").strip().lower() or "default"
                sym_norm = str(leg_key[0] or "").upper()
                side_norm = "BUY" if str(leg_key[2] or "").upper() in {"BUY", "LONG"} else "SELL"
                now_ts = time.time()
                for indicator_key in indicator_keys:
                    ind_norm = _canonical_indicator_token(indicator_key) or ""
                    if not ind_norm:
                        continue
                    self._indicator_last_action[(sym_norm, interval_norm, ind_norm)] = {
                        "side": side_norm,
                        "ts": now_ts,
                    }
        except Exception:
            pass
        try:
            if indicator_keys:
                self._resolve_indicator_conflicts(leg_key, indicator_keys, entry)
        except Exception:
            pass

    def _resolve_indicator_conflicts(
        self,
        leg_key: tuple[str, str, str],
        indicator_keys: list[str],
        current_entry: dict,
    ) -> None:
        if not indicator_keys:
            return
        symbol, interval, side_raw = leg_key
        side_norm = "BUY" if str(side_raw or "").upper() in {"BUY", "LONG"} else "SELL"
        opposite_side = "SELL" if side_norm == "BUY" else "BUY"
        cw_stub = {"symbol": symbol, "interval": interval}
        account_type = str(self.config.get("account_type") or getattr(self.binance, "account_type", "") or "").upper()
        dual_side = False
        if account_type == "FUTURES":
            try:
                dual_side = bool(self.binance.get_futures_dual_side())
            except Exception:
                dual_side = False
        desired_ps_opposite = None
        desired_ps_current = None
        if dual_side:
            desired_ps_opposite = "LONG" if opposite_side == "BUY" else "SHORT"
            desired_ps_current = "LONG" if side_norm == "BUY" else "SHORT"
        conflict_found = False
        for indicator_key in indicator_keys:
            conflicts = self._iter_indicator_entries(symbol, interval, indicator_key, opposite_side)
            if not conflicts:
                continue
            conflict_found = True
            try:
                self.log(
                    f"{symbol}@{interval or 'default'} conflict: {indicator_key} has active {opposite_side} leg while opening {side_norm}. "
                    "Forcing additional close."
                )
            except Exception:
                pass
            for conflict_leg_key, conflict_entry in conflicts:
                try:
                    self._close_leg_entry(
                        cw_stub,
                        conflict_leg_key,
                        conflict_entry,
                        opposite_side,
                        "SELL" if opposite_side == "BUY" else "BUY",
                        desired_ps_opposite,
                        loss_usdt=0.0,
                        price_pct=0.0,
                        margin_pct=0.0,
                    )
                except Exception:
                    continue
        if conflict_found:
            # After forcing opposite closes, re-check. If still conflicting, drop the newly opened leg.
            for indicator_key in indicator_keys:
                residual = self._iter_indicator_entries(symbol, interval, indicator_key, opposite_side)
                if residual:
                    try:
                        self.log(
                            f"{symbol}@{interval or 'default'} conflict persists for {indicator_key}; "
                            f"closing newly opened {side_norm} leg to avoid overlap."
                        )
                    except Exception:
                        pass
                    self._close_leg_entry(
                        cw_stub,
                        leg_key,
                        current_entry,
                        side_norm,
                        "SELL" if side_norm == "BUY" else "BUY",
                        desired_ps_current,
                        loss_usdt=0.0,
                        price_pct=0.0,
                        margin_pct=0.0,
                    )
                    break

    def _remove_leg_entry(self, leg_key, ledger_id: str | None = None) -> None:
        current_entries = self._leg_entries(leg_key)
        if ledger_id is None:
            for entry in current_entries:
                try:
                    signature_labels = entry.get("trigger_signature") or entry.get("trigger_indicators")
                    self._bump_symbol_signature_open(leg_key[0], leg_key[1], leg_key[2], signature_labels, -1)
                except Exception:
                    pass
                try:
                    ledger = entry.get("ledger_id")
                    indicator_keys = self._extract_indicator_keys(entry)
                    if ledger and indicator_keys:
                        for indicator_key in indicator_keys:
                            self._indicator_unregister_entry(leg_key[0], leg_key[1], indicator_key, leg_key[2], ledger)
                            self._trade_book_remove_entry(leg_key[0], leg_key[1], indicator_key, leg_key[2], ledger)
                        self._ledger_index.pop(ledger, None)
                except Exception:
                    pass
            self._leg_ledger.pop(leg_key, None)
            self._last_order_time.pop(leg_key, None)
            return
        leg = self._leg_ledger.get(leg_key)
        if not isinstance(leg, dict):
            return
        removed_entries = [entry for entry in current_entries if entry.get("ledger_id") == ledger_id]
        entries = [entry for entry in current_entries if entry.get("ledger_id") != ledger_id]
        if not entries:
            for entry in removed_entries:
                try:
                    signature_labels = entry.get("trigger_signature") or entry.get("trigger_indicators")
                    self._bump_symbol_signature_open(leg_key[0], leg_key[1], leg_key[2], signature_labels, -1)
                except Exception:
                    pass
                try:
                    indicator_keys = self._extract_indicator_keys(entry)
                    ledger_token = entry.get("ledger_id")
                    if ledger_token and indicator_keys:
                        for indicator_key in indicator_keys:
                            self._indicator_unregister_entry(
                                leg_key[0], leg_key[1], indicator_key, leg_key[2], ledger_token
                            )
                            self._trade_book_remove_entry(
                                leg_key[0], leg_key[1], indicator_key, leg_key[2], ledger_token
                            )
                except Exception:
                    pass
            try:
                for entry in removed_entries:
                    ledger = entry.get("ledger_id")
                    if ledger:
                        self._ledger_index.pop(ledger, None)
            except Exception:
                pass
            self._leg_ledger.pop(leg_key, None)
            self._last_order_time.pop(leg_key, None)
            return
        leg["entries"] = entries
        self._update_leg_snapshot(leg_key, leg)
        for entry in removed_entries:
            try:
                signature_labels = entry.get("trigger_signature") or entry.get("trigger_indicators")
                self._bump_symbol_signature_open(leg_key[0], leg_key[1], leg_key[2], signature_labels, -1)
            except Exception:
                pass
            try:
                indicator_keys = self._extract_indicator_keys(entry)
                ledger_token = entry.get("ledger_id")
                if ledger_token and indicator_keys:
                    for indicator_key in indicator_keys:
                        self._indicator_unregister_entry(
                            leg_key[0], leg_key[1], indicator_key, leg_key[2], ledger_token
                        )
                        self._trade_book_remove_entry(
                            leg_key[0], leg_key[1], indicator_key, leg_key[2], ledger_token
                        )
            except Exception:
                pass
            try:
                ledger = entry.get("ledger_id")
                if ledger:
                    self._ledger_index.pop(ledger, None)
            except Exception:
                pass

    def _decrement_leg_entry_qty(
        self,
        leg_key: tuple[str, str, str],
        ledger_id: str,
        previous_qty: float,
        remaining_qty: float,
    ) -> None:
        leg = self._leg_ledger.get(leg_key)
        if not isinstance(leg, dict):
            return
        entries = leg.get("entries")
        if not isinstance(entries, list):
            return
        ratio = 0.0
        try:
            if previous_qty > 0.0:
                ratio = max(0.0, remaining_qty / previous_qty)
        except Exception:
            ratio = 0.0
        updated = False
        for idx, entry in enumerate(entries):
            if entry.get("ledger_id") != ledger_id:
                continue
            new_entry = dict(entry)
            new_entry["qty"] = remaining_qty
            for field in (
                "margin_usdt",
                "margin",
                "size_usdt",
                "notional",
                "margin_balance",
                "maint_margin",
                "position_size",
            ):
                value = new_entry.get(field)
                if isinstance(value, (int, float)):
                    new_entry[field] = max(0.0, float(value) * ratio)
            entries[idx] = new_entry
            leg["entries"] = entries
            indicator_keys = self._extract_indicator_keys(new_entry)
            if ledger_id and indicator_keys:
                for indicator_key in indicator_keys:
                    self._trade_book_update_qty(
                        leg_key[0],
                        leg_key[1],
                        indicator_key,
                        leg_key[2],
                        ledger_id,
                        remaining_qty,
                    )
            updated = True
            break
        if updated:
            self._update_leg_snapshot(leg_key, leg)

    def _sync_leg_entry_totals(self, leg_key, actual_qty: float) -> None:
        leg = self._leg_ledger.get(leg_key)
        if not isinstance(leg, dict):
            return
        entries = self._leg_entries(leg_key)
        if not entries:
            leg["qty"] = max(0.0, float(actual_qty))
            self._update_leg_snapshot(leg_key, leg)
            return
        recorded_qty = sum(max(0.0, float(entry.get("qty") or 0.0)) for entry in entries)
        if recorded_qty <= 0.0:
            per_entry_qty = max(0.0, float(actual_qty)) / len(entries) if entries else 0.0
            for entry in entries:
                entry["qty"] = per_entry_qty
        else:
            scale = max(0.0, float(actual_qty)) / recorded_qty if recorded_qty > 0.0 else 0.0
            for entry in entries:
                qty = max(0.0, float(entry.get("qty") or 0.0)) * scale
                entry["qty"] = qty
                margin = max(0.0, float(entry.get("margin_usdt") or 0.0))
                entry["margin_usdt"] = margin * scale if margin > 0.0 else margin
        leg["entries"] = entries
        self._update_leg_snapshot(leg_key, leg)

    @staticmethod
    def _entry_margin_value(entry: dict | None, leverage_fallback: float | int = 1) -> float:
        if not isinstance(entry, dict):
            return 0.0
        try:
            margin_val = float(entry.get("margin_usdt") or 0.0)
        except Exception:
            margin_val = 0.0
        if margin_val > 0.0:
            return max(0.0, margin_val)
        try:
            qty = max(0.0, float(entry.get("qty") or 0.0))
        except Exception:
            qty = 0.0
        try:
            price = max(0.0, float(entry.get("entry_price") or 0.0))
        except Exception:
            price = 0.0
        try:
            lev_val = float(entry.get("leverage") or leverage_fallback or 1.0)
        except Exception:
            lev_val = float(leverage_fallback or 1.0)
        lev_val = max(1.0, lev_val)
        if qty > 0.0 and price > 0.0:
            try:
                return (price * qty) / lev_val
            except Exception:
                return 0.0
        return 0.0

    def _current_futures_position_qty(
        self,
        symbol: str,
        side_label: str,
        position_side: str | None,
        positions: list[dict] | None = None,
    ) -> float | None:
        rows: list[dict] | None
        if positions is None:
            try:
                rows = self.binance.list_open_futures_positions(max_age=0.0, force_refresh=True) or []
            except Exception:
                return None
        else:
            rows = positions
        sym_norm = str(symbol or "").upper()
        side_norm = "BUY" if str(side_label or "").upper() in {"BUY", "LONG"} else "SELL"
        desired_pos_side = str(position_side or "").upper() if position_side else None
        best_qty = 0.0
        for pos in rows or []:
            try:
                if str(pos.get("symbol") or "").upper() != sym_norm:
                    continue
                amt = float(pos.get("positionAmt") or 0.0)
                pos_side_val = str(pos.get("positionSide") or "").upper()
                if desired_pos_side:
                    if pos_side_val and pos_side_val not in ("BOTH", desired_pos_side):
                        if not (
                            desired_pos_side == "LONG" and pos_side_val == "BOTH" and amt > 0.0
                        ) and not (
                            desired_pos_side == "SHORT" and pos_side_val == "BOTH" and amt < 0.0
                        ):
                            continue
                if desired_pos_side:
                    qty_val = abs(amt)
                else:
                    if side_norm == "BUY":
                        if amt <= 0.0:
                            continue
                        qty_val = amt
                    else:
                        if amt >= 0.0:
                            continue
                        qty_val = abs(amt)
                if qty_val > best_qty:
                    best_qty = qty_val
            except Exception:
                continue
        return best_qty if best_qty > 0.0 else 0.0

    def _purge_flat_futures_legs(
        self,
        symbol: str,
        positions: list[dict] | None,
        *,
        dual_side: bool,
    ) -> None:
        sym_norm = str(symbol or "").upper()
        if not sym_norm:
            return
        for leg_key, leg in list(self._leg_ledger.items()):
            leg_sym, leg_interval, leg_side = leg_key
            if str(leg_sym or "").upper() != sym_norm:
                continue
            try:
                qty_recorded = max(0.0, float((leg or {}).get("qty") or 0.0))
            except Exception:
                qty_recorded = 0.0
            if qty_recorded <= 0.0:
                continue
            leg_side_norm = "BUY" if str(leg_side or "").upper() in {"BUY", "LONG"} else "SELL"
            desired_pos_side = None
            if dual_side:
                desired_pos_side = "LONG" if leg_side_norm == "BUY" else "SHORT"
            live_qty = self._current_futures_position_qty(
                sym_norm,
                leg_side_norm,
                desired_pos_side,
                positions,
            )
            if live_qty is None:
                continue
            eps = max(1e-8, abs(live_qty) * 1e-6)
            if live_qty <= eps:
                self._remove_leg_entry(leg_key, None)
                self._guard_mark_leg_closed(leg_key)
                try:
                    self.log(
                        f"Purged stale {leg_side_norm} leg for {sym_norm}@{leg_interval} after liquidation/manual close."
                    )
                except Exception:
                    pass

    def _close_leg_entry(
        self,
        cw: dict,
        leg_key: tuple[str, str, str],
        entry: dict,
        side_label: str,
        close_side: str,
        position_side: str | None,
        *,
        loss_usdt: float,
        price_pct: float,
        margin_pct: float,
        qty_limit: float | None = None,
    ) -> float:
        symbol, interval, _ = leg_key
        qty_recorded = max(0.0, float(entry.get("qty") or 0.0))
        if qty_recorded <= 0.0:
            return 0.0
        qty_to_close = qty_recorded
        if qty_limit is not None:
            try:
                qty_cap = max(0.0, float(qty_limit))
            except Exception:
                qty_cap = 0.0
            if qty_cap <= 0.0:
                return 0.0
            qty_to_close = min(qty_to_close, qty_cap)
        actual_qty = self._current_futures_position_qty(symbol, side_label, position_side)
        if actual_qty is not None:
            eps = max(1e-9, actual_qty * 1e-6)
            if actual_qty <= eps:
                self._remove_leg_entry(leg_key, entry.get("ledger_id"))
                try:
                    self.log(
                        f"Skip close for {symbol}@{interval} ({side_label}): position already flat on exchange."
                    )
                except Exception:
                    pass
                return 0.0
            if qty_to_close - actual_qty > eps:
                try:
                    self.log(
                        f"Adjusting close size for {symbol}@{interval} ({side_label}) "
                        f"from {qty_to_close:.10f} to live {actual_qty:.10f}."
                    )
                except Exception:
                    pass
                qty_to_close = actual_qty
        start_ts = time.time()
        try:
            res = self.binance.close_futures_leg_exact(
                symbol,
                qty_to_close,
                side=close_side,
                position_side=position_side,
            )
        except Exception as exc:
            try:
                self.log(f"Per-trade stop-loss close error for {symbol}@{interval} ({side_label}): {exc}")
            except Exception:
                pass
            return 0.0
        if not (isinstance(res, dict) and res.get("ok")):
            try:
                self.log(f"Per-trade stop-loss close failed for {symbol}@{interval} ({side_label}): {res}")
            except Exception:
                pass
            return 0.0
        latency_s = max(0.0, time.time() - start_ts)
        payload = self._build_close_event_payload(
            symbol,
            interval,
            side_label,
            qty_to_close,
            res,
            leg_info_override=entry,
        )
        remaining_qty = qty_recorded - qty_to_close
        eps_remaining = max(1e-9, qty_recorded * 1e-6)
        if remaining_qty <= eps_remaining or not entry.get("ledger_id"):
            self._remove_leg_entry(leg_key, entry.get("ledger_id"))
        else:
            self._decrement_leg_entry_qty(
                leg_key,
                entry.get("ledger_id"),
                qty_recorded,
                remaining_qty,
            )
        try:
            if hasattr(self.guard, "mark_closed"):
                side_norm = 'BUY' if str(side_label).upper() in ('BUY', 'LONG', 'L') else 'SELL'
                self.guard.mark_closed(symbol, interval, side_norm)
        except Exception:
            pass
        self._notify_interval_closed(
            symbol,
            interval,
            side_label,
            **payload,
            latency_seconds=latency_s,
            latency_ms=latency_s * 1000.0,
            reason="per_trade_stop_loss",
        )
        self._log_latency_metric(symbol, interval, f"stop-loss {side_label.lower()} leg", latency_s)
        try:
            pct_display = max(price_pct, margin_pct)
            self.log(
                f"Per-trade stop-loss closed {side_label} for {symbol}@{interval} "
                f"(qty {qty_to_close:.10f}, loss {loss_usdt:.4f} USDT / {pct_display:.2f}%)."
            )
        except Exception:
            pass
        return qty_to_close

    def _evaluate_per_trade_stop(
        self,
        cw: dict,
        leg_key: tuple[str, str, str],
        entries: list[dict],
        *,
        side_label: str,
        last_price: float | None,
        apply_usdt_limit: bool,
        apply_percent_limit: bool,
        stop_usdt_limit: float,
        stop_percent_limit: float,
        dual_side: bool,
    ) -> bool:
        if last_price is None:
            return False
        symbol, interval, _ = leg_key
        desired_position_side = None
        if dual_side:
            desired_position_side = "LONG" if side_label.upper() == "BUY" else "SHORT"
        close_side = "SELL" if side_label.upper() == "BUY" else "BUY"
        triggered_any = False
        for entry in list(entries):
            qty = max(0.0, float(entry.get("qty") or 0.0))
            entry_price = max(0.0, float(entry.get("entry_price") or 0.0))
            if qty <= 0.0 or entry_price <= 0.0:
                continue
            if side_label.upper() == "BUY":
                loss_usdt = max(0.0, (entry_price - last_price) * qty)
            else:
                loss_usdt = max(0.0, (last_price - entry_price) * qty)
            denom = entry_price * qty
            price_pct = (loss_usdt / denom * 100.0) if denom > 0.0 else 0.0
            leverage_val = float(entry.get("leverage") or 0.0)
            margin_entry = float(entry.get("margin_usdt") or 0.0)
            if margin_entry <= 0.0:
                if leverage_val > 0.0:
                    margin_entry = denom / leverage_val if leverage_val != 0.0 else denom
                else:
                    margin_entry = denom
            margin_pct = (loss_usdt / margin_entry * 100.0) if margin_entry > 0.0 else 0.0
            effective_pct = max(price_pct, margin_pct)
            triggered = False
            if apply_usdt_limit and loss_usdt >= stop_usdt_limit:
                triggered = True
            if not triggered and apply_percent_limit and effective_pct >= stop_percent_limit:
                triggered = True
            if triggered:
                if self._close_leg_entry(
                    cw,
                    leg_key,
                    entry,
                    side_label.upper(),
                    close_side,
                    desired_position_side,
                    loss_usdt=loss_usdt,
                    price_pct=price_pct,
                    margin_pct=margin_pct,
                ):
                    triggered_any = True
        if triggered_any:
            # ensure ledger snapshot reflects any removals
            leg = self._leg_ledger.get(leg_key)
            if isinstance(leg, dict):
                self._update_leg_snapshot(leg_key, leg)
        else:
            # ensure we keep consistent timestamps even if no trigger
            leg = self._leg_ledger.get(leg_key)
            if isinstance(leg, dict):
                leg["timestamp"] = time.time()
        return triggered_any

    @staticmethod
    def _compute_position_margin_fields(
        position: dict | None,
        *,
        qty_hint: float = 0.0,
        entry_price_hint: float = 0.0,
    ) -> tuple[float, float, float, float]:
        """Derive margin, balance, maintenance margin, and unrealized loss for a futures leg."""
        if not isinstance(position, dict):
            return 0.0, 0.0, 0.0, 0.0
        try:
            margin = float(
                position.get("isolatedMargin")
                or position.get("isolatedWallet")
                or position.get("initialMargin")
                or 0.0
            )
        except Exception:
            margin = 0.0
        try:
            leverage = float(position.get("leverage") or 0.0)
        except Exception:
            leverage = 0.0
        try:
            entry_price = float(position.get("entryPrice") or 0.0)
        except Exception:
            entry_price = 0.0
        if entry_price <= 0.0:
            entry_price = max(0.0, float(entry_price_hint or 0.0))
        try:
            notional_val = abs(float(position.get("notional") or 0.0))
        except Exception:
            notional_val = 0.0
        if notional_val <= 0.0 and entry_price > 0.0 and qty_hint > 0.0:
            notional_val = entry_price * qty_hint
        if margin <= 0.0:
            if leverage > 0.0 and notional_val > 0.0:
                margin = notional_val / leverage
            elif notional_val > 0.0:
                margin = notional_val
        if margin <= 0.0 and entry_price > 0.0 and qty_hint > 0.0:
            if leverage > 0.0:
                margin = (entry_price * qty_hint) / leverage
            else:
                margin = entry_price * qty_hint
        margin = max(margin, 0.0)
        try:
            margin_balance = float(position.get("marginBalance") or 0.0)
        except Exception:
            margin_balance = 0.0
        try:
            iso_wallet = float(position.get("isolatedWallet") or 0.0)
        except Exception:
            iso_wallet = 0.0
        if margin_balance <= 0.0 and iso_wallet > 0.0:
            margin_balance = iso_wallet
        try:
            unrealized_profit = float(position.get("unRealizedProfit") or 0.0)
        except Exception:
            unrealized_profit = 0.0
        if margin_balance <= 0.0 and margin > 0.0:
            margin_balance = margin + unrealized_profit
        if margin_balance <= 0.0 and margin > 0.0:
            margin_balance = margin
        margin_balance = max(margin_balance, 0.0)
        try:
            maint_margin = float(position.get("maintMargin") or position.get("maintenanceMargin") or 0.0)
        except Exception:
            maint_margin = 0.0
        try:
            maint_margin_rate = float(
                position.get("maintMarginRate")
                or position.get("maintenanceMarginRate")
                or position.get("maintMarginRatio")
                or position.get("maintenanceMarginRatio")
                or 0.0
            )
        except Exception:
            maint_margin_rate = 0.0
        if maint_margin <= 0.0 and maint_margin_rate > 0.0 and notional_val > 0.0:
            maint_margin = notional_val * maint_margin_rate
        if margin_balance > 0.0 and maint_margin > margin_balance:
            maint_margin = margin_balance
        unrealized_loss = max(0.0, -unrealized_profit)
        return margin, margin_balance, maint_margin, unrealized_loss

    def stop(self):
        self._stop = True
        try:
            self._stop_time = float(time.time())
        except Exception:
            self._stop_time = 0.0

    def stopped(self):
        return self._stop

    def is_alive(self):
        try:
            thread = getattr(self, '_thread', None)
            return bool(thread) and bool(getattr(thread, 'is_alive', lambda: False)())
        except Exception:
            return False

    def join(self, timeout=None):
        try:
            thread = getattr(self, '_thread', None)
            if thread and thread.is_alive():
                thread.join(timeout)
        except Exception:
            pass

    def _close_opposite_position(
        self,
        symbol: str,
        interval: str,
        next_side: str,
        trigger_signature: tuple[str, ...] | None = None,
        indicator_key: Iterable[str] | str | None = None,
        target_qty: float | None = None,
    ) -> bool:
        """Ensure no conflicting exposure remains before opening a new leg."""
        interval_norm = str(interval or "").strip()
        interval_tokens = self._tokenize_interval_label(interval_norm)
        interval_norm_lower = interval_norm.lower()
        interval_has_filter = interval_tokens != {"-"}
        indicator_tokens = StrategyEngine._normalize_indicator_token_list(indicator_key)
        if not indicator_tokens:
            indicator_tokens = StrategyEngine._normalize_indicator_token_list(
                self._indicator_token_from_signature(trigger_signature)
            )
        signature_hint_tokens = StrategyEngine._normalize_signature_tokens_no_slots(trigger_signature)

        try:
            positions = self.binance.list_open_futures_positions(max_age=0.0, force_refresh=True) or []
        except Exception as e:
            self.log(f"{symbol}@{interval} read positions failed: {e}")
            return False

        def _refresh_positions_snapshot() -> list[dict] | None:
            try:
                return self.binance.list_open_futures_positions(max_age=0.0, force_refresh=True) or []
            except Exception as refresh_exc:
                try:
                    self.log(f"{symbol}@{interval} close-opposite refresh failed: {refresh_exc}")
                except Exception:
                    pass
                return None

        desired = (next_side or '').upper()
        if desired not in ('BUY', 'SELL'):
            return True
        try:
            dual = bool(self.binance.get_futures_dual_side())
        except Exception:
            dual = False

        def _execute_close_with_fallback(close_side: str, qty: float, preferred_ps: str | None):
            attempts: list[str | None] = []
            normalized_preferred = str(preferred_ps or "").upper() or None
            if normalized_preferred:
                attempts.append(normalized_preferred)
            hedge_ps = 'SHORT' if close_side.upper() == 'BUY' else 'LONG'
            if hedge_ps not in attempts:
                attempts.append(hedge_ps)
            if None not in attempts:
                attempts.append(None)
            last_res = None
            tried: set[str | None] = set()
            for ps in attempts:
                if ps in tried:
                    continue
                tried.add(ps)
                try:
                    res = self.binance.close_futures_leg_exact(
                        symbol,
                        qty,
                        side=close_side,
                        position_side=ps,
                    )
                except Exception as exc:
                    res = {'ok': False, 'error': str(exc)}
                last_res = res
                if isinstance(res, dict) and res.get('ok'):
                    return True, res
                message = ""
                if isinstance(res, dict):
                    message = str(res.get('error') or res)
                else:
                    message = str(res)
                if "position side does not match" in message.lower():
                    continue
            return False, last_res

        opp = 'SELL' if desired == 'BUY' else 'BUY'
        closed_any = False
        indicator_target_cleared = False
        try:
            qty_goal = float(target_qty) if target_qty is not None else None
        except Exception:
            qty_goal = None
        qty_tol = 1e-9

        def _reduce_goal(delta: float) -> None:
            nonlocal qty_goal
            if qty_goal is None:
                return
            qty_goal = max(0.0, qty_goal - max(0.0, delta))

        def _goal_met() -> bool:
            return qty_goal is not None and qty_goal <= qty_tol

        if _goal_met():
            return True

        def _close_interval_side_entries(
            indicator_filter: str | None,
            signature_filter: tuple[str, ...] | None,
            qty_limit: float | None,
        ) -> tuple[int, bool, float]:
            """Close ledger-tracked entries for this symbol/interval/opposite side."""
            closed_entries = 0
            failed = False
            qty_closed = 0.0
            indicator_filter_norm = _canonical_indicator_token(indicator_filter) or ""
            signature_filter = (
                tuple(str(token or "").strip().lower() for token in (signature_filter or ()) if str(token or "").strip())
                or None
            )
            limit_remaining = None
            limit_tol = 1e-9
            if qty_limit is not None:
                try:
                    limit_remaining = max(0.0, float(qty_limit))
                except Exception:
                    limit_remaining = 0.0
            for leg_key in list(self._leg_ledger.keys()):
                if limit_remaining is not None and limit_remaining <= limit_tol:
                    break
                leg_sym, leg_interval, leg_side = leg_key
                if str(leg_sym or "").upper() != symbol:
                    continue
                leg_interval_norm = str(leg_interval or "").strip()
                leg_tokens = self._tokenize_interval_label(leg_interval_norm)
                if interval_has_filter and leg_tokens.isdisjoint(interval_tokens):
                    continue
                leg_side_norm = str(leg_side or "").upper()
                if leg_side_norm in {"LONG", "SHORT"}:
                    leg_side_norm = "BUY" if leg_side_norm == "LONG" else "SELL"
                if leg_side_norm != opp:
                    continue
                entries = list(self._leg_entries(leg_key))
                if not entries:
                    continue
                interval_for_entry = leg_interval if leg_interval is not None else interval_norm or "default"
                cw_ctx = {"symbol": leg_sym, "interval": interval_for_entry}
                for entry in entries:
                    entry_keys = self._extract_indicator_keys(entry)
                    if indicator_filter_norm:
                        matches_filter = any(
                            (_canonical_indicator_token(key) or str(key or "").strip().lower()) == indicator_filter_norm
                            for key in entry_keys
                        )
                        if not matches_filter:
                            continue
                    if signature_filter:
                        entry_sig = StrategyEngine._normalize_signature_tokens_no_slots(
                            entry.get("trigger_signature") or entry.get("trigger_indicators")
                        )
                        if tuple(entry_sig or ()) != signature_filter:
                            continue
                    indicator_hold_key = indicator_filter_norm or (entry_keys[0] if entry_keys else None)
                    if indicator_hold_key:
                        try:
                            interval_seconds_entry = float(_interval_to_seconds(str(interval_for_entry or "1m")))
                        except Exception:
                            interval_seconds_entry = 60.0
                        if not self._indicator_hold_ready(
                            entry.get("timestamp"),
                            leg_sym,
                            interval_for_entry,
                            indicator_hold_key,
                            leg_side_norm,
                            interval_seconds_entry,
                        ):
                            continue
                    close_side = 'SELL' if leg_side_norm == 'BUY' else 'BUY'
                    position_side = None
                    if dual:
                        position_side = 'LONG' if leg_side_norm == 'BUY' else 'SHORT'
                    try:
                        qty_request = limit_remaining if limit_remaining is not None else None
                        closed_qty = self._close_leg_entry(
                            cw_ctx,
                            leg_key,
                            entry,
                            leg_side_norm,
                            close_side,
                            position_side,
                            loss_usdt=0.0,
                            price_pct=0.0,
                            margin_pct=0.0,
                            qty_limit=qty_request,
                        )
                        if closed_qty > 0.0:
                            closed_entries += 1
                            qty_closed += closed_qty
                            if limit_remaining is not None:
                                limit_remaining = max(0.0, limit_remaining - closed_qty)
                        else:
                            failed = True
                            break
                    except Exception as entry_exc:
                        try:
                            self.log(
                                f"{symbol}@{interval_norm or leg_interval} close-opposite ledger entry failed: {entry_exc}"
                            )
                        except Exception:
                            pass
                        failed = True
                        break
                if failed:
                    break
            return closed_entries, failed, qty_closed

        indicator_position_side = None
        if dual:
            indicator_position_side = 'LONG' if opp == 'BUY' else 'SHORT'
        if indicator_tokens:
            cw_stub = {"symbol": symbol, "interval": interval_norm}
            indicator_target_cleared = True
            for indicator_hint in indicator_tokens:
                closed_count = 0
                closed_qty_total = 0.0
                try:
                    closed_count, closed_qty_total = self._close_indicator_positions(
                        cw_stub,
                        interval_norm,
                        indicator_hint,
                        opp,
                        indicator_position_side,
                        signature_hint=signature_hint_tokens,
                        ignore_hold=True,
                        qty_limit=qty_goal,
                    )
                except Exception as exc:
                    try:
                        self.log(f"{symbol}@{interval} indicator-close {indicator_hint} failed: {exc}")
                    except Exception:
                        pass
                if closed_count:
                    closed_any = True
                    _reduce_goal(closed_qty_total)
                    try:
                        ctx_interval = interval_norm or "default"
                        self.log(
                            f"{symbol}@{ctx_interval} flip {indicator_hint}: closed {closed_count} {opp} leg(s) before opening {next_side}."
                        )
                    except Exception:
                        pass
                    refreshed = _refresh_positions_snapshot()
                    if refreshed is None:
                        return False
                    positions = refreshed
                    if _goal_met():
                        return True
                try:
                    indicator_clear = not self._indicator_has_open(symbol, interval_norm, indicator_hint, opp)
                except Exception:
                    indicator_clear = False
                indicator_target_cleared = indicator_target_cleared and indicator_clear
                if _goal_met():
                    return True

        def _has_opposite_live(pos_iterable) -> bool:
            tol = 1e-9
            for pos in pos_iterable:
                if str(pos.get('symbol') or '').upper() != symbol:
                    continue
                pos_side = str(pos.get('positionSide') or pos.get('positionside') or 'BOTH').upper()
                amt_val = float(pos.get('positionAmt') or 0.0)
                if opp == 'BUY':
                    if (pos_side == 'LONG' and amt_val > tol) or (pos_side in {'BOTH', ''} and amt_val > tol):
                        return True
                else:
                    if (pos_side == 'SHORT' and amt_val < -tol) or (pos_side in {'BOTH', ''} and amt_val < -tol):
                        return True
            return False

        if dual and indicator_tokens and indicator_target_cleared:
            if qty_goal is not None:
                if _goal_met():
                    return True
            else:
                return True

        ledger_closed = 0
        ledger_failed = False
        ledger_qty_closed = 0.0
        if indicator_tokens:
            for indicator_hint in indicator_tokens:
                closed, failed, qty = _close_interval_side_entries(indicator_hint, signature_hint_tokens, qty_goal)
                ledger_closed += closed
                ledger_qty_closed += qty
                if failed:
                    ledger_failed = True
                    break
        else:
            ledger_closed, ledger_failed, ledger_qty_closed = _close_interval_side_entries(
                None, signature_hint_tokens, qty_goal
            )
        if ledger_failed:
            try:
                self.log(
                    f"{symbol}@{interval_norm or 'default'} flip aborted: failed to close existing {opp} ledger entries."
                )
            except Exception:
                pass
            return False
        if ledger_closed:
            closed_any = True
            _reduce_goal(ledger_qty_closed)
            refreshed = _refresh_positions_snapshot()
            if refreshed is None:
                return False
            positions = refreshed
            if _goal_met():
                return True
        if dual:
            if qty_goal is not None:
                if _goal_met():
                    return True
            elif indicator_tokens and indicator_target_cleared:
                return True
            elif not _has_opposite_live(positions):
                return True
        elif _goal_met():
            return True

        def _execute_close_with_fallback(close_side: str, qty: float, preferred_ps: str | None):
            attempts: list[str | None] = []
            normalized = str(preferred_ps or "").upper() or None
            if normalized:
                attempts.append(normalized)
            hedge_ps = 'SHORT' if close_side.upper() == 'BUY' else 'LONG'
            if hedge_ps not in attempts:
                attempts.append(hedge_ps)
            if None not in attempts:
                attempts.append(None)
            last_res = None
            tried: set[str | None] = set()
            for ps in attempts:
                if ps in tried:
                    continue
                tried.add(ps)
                try:
                    res = self.binance.close_futures_leg_exact(
                        symbol,
                        qty,
                        side=close_side,
                        position_side=ps,
                    )
                except Exception as exc:
                    res = {'ok': False, 'error': str(exc)}
                last_res = res
                if isinstance(res, dict) and res.get('ok'):
                    return True, res
                message = ""
                if isinstance(res, dict):
                    message = str(res.get('error') or res)
                else:
                    message = str(res)
                if "position side does not match" in message.lower():
                    continue
            return False, last_res

        if indicator_tokens and not indicator_target_cleared:
            try:
                residual_qty = max(
                    0.0,
                    float(
                        self._current_futures_position_qty(
                            symbol,
                            opp,
                            indicator_position_side,
                            positions,
                        )
                        or 0.0
                    ),
                )
            except Exception:
                residual_qty = 0.0
            qty_hint = qty_goal if qty_goal is not None and qty_goal > 0.0 else residual_qty
            if qty_hint > 0.0:
                success, close_res = _execute_close_with_fallback(opp, qty_hint, indicator_position_side)
                if success:
                    closed_any = True
                    _reduce_goal(qty_hint)
                    refreshed = _refresh_positions_snapshot()
                    if refreshed is None:
                        return False
                    positions = refreshed
                    indicator_target_cleared = True
                    ledger_closed = 1
                    ledger_qty_closed = qty_hint
                    if _goal_met():
                        return True
                else:
                    try:
                        indicator_label = ", ".join(indicator_tokens)
                        self.log(
                            f"{symbol}@{interval_norm or 'default'} flip blocked: residual {indicator_label} {opp} leg "
                            f"could not be closed ({close_res})."
                        )
                    except Exception:
                        pass
                    return False
            else:
                try:
                    indicator_label = ", ".join(indicator_tokens)
                    self.log(f"{symbol}@{interval_norm or 'default'} flip skipped: no {indicator_label} {opp} leg to close.")
                except Exception:
                    pass
                return False

        opp_key = (symbol, interval, opp)
        for p in positions:
            try:
                if str(p.get('symbol') or '').upper() != symbol:
                    continue
                amt = float(p.get('positionAmt') or 0.0)
                position_side_flag = None
                if dual:
                    pos_side = str(p.get('positionSide') or p.get('positionside') or '').upper()
                    if pos_side in {'LONG', 'SHORT'}:
                        position_side_flag = pos_side
                    else:
                        position_side_flag = 'LONG' if amt > 0 else 'SHORT'
                if desired == 'BUY' and amt < 0:
                    qty = abs(amt)
                    if qty_goal is not None:
                        if _goal_met():
                            break
                        qty = min(qty, qty_goal)
                    success, res = _execute_close_with_fallback(
                        'BUY',
                        qty,
                        position_side_flag if dual else None,
                    )
                    if not success:
                        self.log(f"{symbol}@{interval} close-short failed: {res}")
                        return False
                    payload = self._build_close_event_payload(symbol, interval, 'SELL', qty, res)
                    self._notify_interval_closed(symbol, interval, 'SELL', **payload)
                    try:
                        if hasattr(self.guard, "mark_closed"):
                            self.guard.mark_closed(symbol, interval, 'SELL')
                    except Exception:
                        pass
                    closed_any = True
                    _reduce_goal(qty)
                    if _goal_met():
                        break
                elif desired == 'SELL' and amt > 0:
                    qty = abs(amt)
                    if qty_goal is not None:
                        if _goal_met():
                            break
                        qty = min(qty, qty_goal)
                    success, res = _execute_close_with_fallback(
                        'SELL',
                        qty,
                        position_side_flag if dual else None,
                    )
                    if not success:
                        self.log(f"{symbol}@{interval} close-long failed: {res}")
                        return False
                    payload = self._build_close_event_payload(symbol, interval, 'BUY', qty, res)
                    self._notify_interval_closed(symbol, interval, 'BUY', **payload)
                    try:
                        if hasattr(self.guard, "mark_closed"):
                            self.guard.mark_closed(symbol, interval, 'BUY')
                    except Exception:
                        pass
                    closed_any = True
                    _reduce_goal(qty)
                    if _goal_met():
                        break
            except Exception as exc:
                self.log(f"{symbol}@{interval} close-opposite exception: {exc}")
                return False
        if closed_any:
            try:
                import time as _t
                for _ in range(6):
                    positions_refresh = self.binance.list_open_futures_positions(max_age=0.0, force_refresh=True) or []
                    still_opposite = False
                    for pos in positions_refresh:
                        if str(pos.get('symbol') or '').upper() != symbol:
                            continue
                        amt_chk = float(pos.get('positionAmt') or 0.0)
                        if (opp == 'SELL' and amt_chk < 0) or (opp == 'BUY' and amt_chk > 0):
                            still_opposite = True
                            break
                    if not still_opposite:
                        break
                    _t.sleep(0.15)
            except Exception:
                pass
            for key in list(self._leg_ledger.keys()):
                if key[0] == symbol and key[2] == opp:
                    self._remove_leg_entry(key, None)
                    self._guard_mark_leg_closed(key)
        return True
    # ---- indicator computation (uses pandas_ta when available)
    def compute_indicators(self, df):
        cfg = self.config['indicators']
        ind = {}
        if df.empty:
            return ind
        try:
            import pandas_ta as ta  # optional
            has_accessor = hasattr(df['close'], 'ta')
        except Exception:
            ta = None
            has_accessor = False

        # MA
        ma_cfg = cfg.get('ma', {})
        if ma_cfg.get('enabled'):
            if has_accessor and cfg['ma'].get('type','SMA').upper()=='SMA':
                ind['ma'] = df['close'].ta.sma(length=int(cfg['ma']['length']))
            elif has_accessor:
                ind['ma'] = df['close'].ta.ema(length=int(cfg['ma']['length']))
            else:
                if cfg['ma'].get('type','SMA').upper()=='SMA':
                    ind['ma'] = sma(df['close'], int(cfg['ma']['length']))
                else:
                    ind['ma'] = ema(df['close'], int(cfg['ma']['length']))

        ema_cfg = cfg.get('ema', {})
        if ema_cfg.get('enabled'):
            length = int(ema_cfg.get('length') or 20)
            if has_accessor:
                try:
                    ind['ema'] = df['close'].ta.ema(length=length)
                except Exception:
                    ind['ema'] = ema(df['close'], length)
            else:
                ind['ema'] = ema(df['close'], length)

        # BB
        bb_cfg = cfg.get('bb', {})
        if bb_cfg.get('enabled'):
            if has_accessor:
                try:
                    bb = df['close'].ta.bbands(length=int(cfg['bb']['length']), std=float(cfg['bb']['std']))
                    ind['bb_upper'] = bb.iloc[:,0]; ind['bb_mid'] = bb.iloc[:,1]; ind['bb_lower'] = bb.iloc[:,2]
                except Exception:
                    upper, mid, lower = bollinger_bands(df, int(cfg['bb']['length']), float(cfg['bb']['std']))
                    ind['bb_upper'], ind['bb_mid'], ind['bb_lower'] = upper, mid, lower
            else:
                upper, mid, lower = bollinger_bands(df, int(cfg['bb']['length']), float(cfg['bb']['std']))
                ind['bb_upper'], ind['bb_mid'], ind['bb_lower'] = upper, mid, lower

        # RSI
        if cfg.get('rsi', {}).get('enabled'):
            if has_accessor:
                ind['rsi'] = df['close'].ta.rsi(length=int(cfg['rsi']['length']))
            else:
                ind['rsi'] = rsi_fallback(df['close'], length=int(cfg['rsi']['length']))

        # Stochastic RSI
        stoch_rsi_cfg = cfg.get('stoch_rsi', {})
        if stoch_rsi_cfg.get('enabled'):
            length = int(stoch_rsi_cfg.get('length') or 14)
            smooth_k = int(stoch_rsi_cfg.get('smooth_k') or 3)
            smooth_d = int(stoch_rsi_cfg.get('smooth_d') or 3)
            k_series = None
            d_series = None
            if has_accessor:
                try:
                    srsi_df = df['close'].ta.stochrsi(length=length, rsi_length=length, k=smooth_k, d=smooth_d)
                    cols = list(srsi_df.columns) if srsi_df is not None else []
                    if cols:
                        k_series = srsi_df[cols[0]]
                        if len(cols) > 1:
                            d_series = srsi_df[cols[1]]
                except Exception:
                    k_series = None
                    d_series = None
            if k_series is None or d_series is None:
                k_series, d_series = stoch_rsi_fallback(df['close'], length=length, smooth_k=smooth_k, smooth_d=smooth_d)
            ind['stoch_rsi'] = k_series
            ind['stoch_rsi_k'] = k_series
            ind['stoch_rsi_d'] = d_series

        # Williams %R
        if cfg.get('willr', {}).get('enabled'):
            try:
                length = int(cfg['willr'].get('length') or 14)
            except Exception:
                length = 14
            length = max(1, length)
            if has_accessor:
                try:
                    ind['willr'] = df.ta.willr(length=length)
                except Exception:
                    ind['willr'] = williams_r_fallback(df, length=length)
            else:
                ind['willr'] = williams_r_fallback(df, length=length)

        # MACD (kept for completeness)
        if cfg.get('macd', {}).get('enabled'):
            if has_accessor:
                macd_df = df['close'].ta.macd(fast=int(cfg['macd']['fast']), slow=int(cfg['macd']['slow']), signal=int(cfg['macd']['signal']))
                ind['macd_line'] = macd_df.iloc[:,0]; ind['macd_signal'] = macd_df.iloc[:,1]
            else:
                macdl, macds, _ = macd_fallback(df['close'], int(cfg['macd']['fast']), int(cfg['macd']['slow']), int(cfg['macd']['signal']))
                ind['macd_line'], ind['macd_signal'] = macdl, macds

        if cfg.get('uo', {}).get('enabled'):
            short = int(cfg['uo'].get('short') or 7)
            medium = int(cfg['uo'].get('medium') or 14)
            long = int(cfg['uo'].get('long') or 28)
            ind['uo'] = uo_fallback(df, short=short, medium=medium, long=long)

        if cfg.get('adx', {}).get('enabled'):
            length = int(cfg['adx'].get('length') or 14)
            if has_accessor:
                try:
                    adx_df = df.ta.adx(length=length)
                    adx_cols = [c for c in adx_df.columns if 'ADX' in c.upper()]
                    ind['adx'] = adx_df[adx_cols[0]] if adx_cols else adx_fallback(df, length=length)
                except Exception:
                    ind['adx'] = adx_fallback(df, length=length)
            else:
                ind['adx'] = adx_fallback(df, length=length)

        if cfg.get('dmi', {}).get('enabled'):
            length = int(cfg['dmi'].get('length') or 14)
            plus_series = minus_series = None
            if has_accessor:
                try:
                    dmi_df = df.ta.dmi(length=length)
                    cols = list(dmi_df.columns)
                    if len(cols) >= 2:
                        plus_series = dmi_df[cols[0]]
                        minus_series = dmi_df[cols[1]]
                except Exception:
                    plus_series = minus_series = None
            if plus_series is None or minus_series is None:
                plus_series, minus_series, _ = dmi_fallback(df, length=length)
            ind['dmi_plus'] = plus_series
            ind['dmi_minus'] = minus_series
            ind['dmi'] = (plus_series - minus_series)

        if cfg.get('supertrend', {}).get('enabled'):
            atr_period = int(cfg['supertrend'].get('atr_period') or 10)
            multiplier = float(cfg['supertrend'].get('multiplier') or 3.0)
            ind['supertrend'] = supertrend_fallback(df, atr_period=atr_period, multiplier=multiplier)

        if cfg.get('stochastic', {}).get('enabled'):
            length = int(cfg['stochastic'].get('length') or 14)
            smooth_k = int(cfg['stochastic'].get('smooth_k') or 3)
            smooth_d = int(cfg['stochastic'].get('smooth_d') or 3)
            k_series = None
            d_series = None
            if has_accessor:
                try:
                    stoch_df = df.ta.stoch(k=length, d=smooth_d, smooth_k=smooth_k)
                    cols = list(stoch_df.columns)
                    if cols:
                        k_series = stoch_df[cols[0]]
                        if len(cols) > 1:
                            d_series = stoch_df[cols[1]]
                except Exception:
                    k_series = None
                    d_series = None
            if k_series is None or d_series is None:
                k_series, d_series = stochastic_fallback(df, length=length, smooth_k=smooth_k, smooth_d=smooth_d)
            ind['stochastic'] = k_series
            ind['stochastic_k'] = k_series
            ind['stochastic_d'] = d_series

        return ind

    def _interval_seconds(self, interval: str) -> int:
        try:
            if interval.endswith('s'): return int(interval[:-1])
            if interval.endswith('m'): return int(interval[:-1]) * 60
            if interval.endswith('h'): return int(interval[:-1]) * 3600
            if interval.endswith('d'): return int(interval[:-1]) * 86400
            if interval.endswith('w'): return int(interval[:-1]) * 7 * 86400
            return int(interval)
        except Exception:
            return 60

    def generate_signal(self, df, ind):
        cfg = self.config
        if df.empty or len(df) < 2:
            return None, "no data", None, [], {}

        last_close = float(df['close'].iloc[-1])
        prev_close = float(df['close'].iloc[-2])

        signal = None
        trigger_desc = []
        trigger_sources: list[str] = []
        trigger_actions: dict[str, str] = {}

        # --- RSI thresholds as primary triggers ---
        rsi_cfg = cfg['indicators'].get('rsi', {})
        rsi_enabled = bool(rsi_cfg.get('enabled', False))
        if rsi_enabled and 'rsi' in ind and not ind['rsi'].dropna().empty:
            try:
                _, _, r = self._indicator_prev_live_signal_values(ind['rsi'])
                if math.isfinite(r):
                    trigger_desc.append(f"RSI={r:.2f}")
                    buy_th = float(rsi_cfg.get('buy_value', 30) or 30)
                    sell_th = float(rsi_cfg.get('sell_value', 70) or 70)
                    buy_allowed = cfg['side'] in ('BUY', 'BOTH')
                    sell_allowed = cfg['side'] in ('SELL', 'BOTH')
                    if buy_allowed and r <= buy_th:
                        trigger_actions["rsi"] = "buy"
                        trigger_desc.append(f"RSI <= {buy_th:.2f} -> BUY")
                        trigger_sources.append("rsi")
                        if signal is None:
                            signal = 'BUY'
                    elif sell_allowed and r >= sell_th:
                        trigger_actions["rsi"] = "sell"
                        trigger_desc.append(f"RSI >= {sell_th:.2f} -> SELL")
                        trigger_sources.append("rsi")
                        if signal is None:
                            signal = 'SELL'
                else:
                    trigger_desc.append("RSI=NaN/inf skipped")
            except Exception as e:
                trigger_desc.append(f"RSI error:{e!r}")

        # --- Stochastic RSI thresholds ---
        stoch_rsi_cfg = cfg['indicators'].get('stoch_rsi', {})
        stoch_rsi_enabled = bool(stoch_rsi_cfg.get('enabled', False))
        if stoch_rsi_enabled and 'stoch_rsi_k' in ind and ind['stoch_rsi_k'] is not None:
            try:
                prev_srsi, live_srsi, srsi_val = self._indicator_prev_live_signal_values(ind['stoch_rsi_k'])
                trigger_desc.append(f"StochRSI %K={srsi_val:.2f} (prev={prev_srsi:.2f}, live={live_srsi:.2f})")
                buy_th = stoch_rsi_cfg.get('buy_value')
                sell_th = stoch_rsi_cfg.get('sell_value')
                buy_limit = float(buy_th if buy_th is not None else 20.0)
                sell_limit = float(sell_th if sell_th is not None else 80.0)
                buy_allowed = cfg['side'] in ('BUY', 'BOTH')
                sell_allowed = cfg['side'] in ('SELL', 'BOTH')
                if buy_allowed and srsi_val <= buy_limit:
                    trigger_actions["stoch_rsi"] = "buy"
                    trigger_desc.append(f"StochRSI %K <= {buy_limit:.2f} -> BUY")
                    trigger_sources.append("stoch_rsi")
                    if signal is None:
                        signal = 'BUY'
                elif sell_allowed and srsi_val >= sell_limit:
                    trigger_actions["stoch_rsi"] = "sell"
                    trigger_desc.append(f"StochRSI %K >= {sell_limit:.2f} -> SELL")
                    trigger_sources.append("stoch_rsi")
                    if signal is None:
                        signal = 'SELL'
            except Exception as e:
                trigger_desc.append(f"StochRSI error:{e!r}")

        # --- Williams %R thresholds ---
        willr_cfg = cfg['indicators'].get('willr', {})
        willr_enabled = bool(willr_cfg.get('enabled', False))
        if willr_enabled and 'willr' in ind:
            try:
                prev_wr, live_wr, wr_signal = self._indicator_prev_live_signal_values(ind['willr'])
                trigger_desc.append(f"Williams %R(prev={prev_wr:.2f}, live={live_wr:.2f}) -> using {wr_signal:.2f}")
                buy_val = willr_cfg.get('buy_value')
                sell_val = willr_cfg.get('sell_value')
                buy_th = float(buy_val if buy_val is not None else -80.0)
                sell_th = float(sell_val if sell_val is not None else -20.0)
                buy_upper = max(-100.0, min(0.0, buy_th))
                buy_lower = -100.0
                sell_lower = max(-100.0, min(0.0, sell_th))
                sell_upper = 0.0
                buy_allowed = cfg['side'] in ('BUY', 'BOTH')
                sell_allowed = cfg['side'] in ('SELL', 'BOTH')
                if buy_allowed and buy_lower <= wr_signal <= buy_upper:
                    trigger_actions["willr"] = "buy"
                    trigger_desc.append(f"Williams %R in [{buy_lower:.2f}, {buy_upper:.2f}] -> BUY")
                    trigger_sources.append("willr")
                    if signal is None:
                        signal = 'BUY'
                elif sell_allowed and sell_lower <= wr_signal <= sell_upper:
                    trigger_actions["willr"] = "sell"
                    trigger_desc.append(f"Williams %R in [{sell_lower:.2f}, {sell_upper:.2f}] -> SELL")
                    trigger_sources.append("willr")
                    if signal is None:
                        signal = 'SELL'
            except Exception as e:
                trigger_desc.append(f"Williams %R error:{e!r}")

        # --- MA crossover (optional alternative trigger) ---
        ma_cfg = cfg['indicators'].get('ma', {})
        ma_enabled = bool(ma_cfg.get('enabled', False))
        if ma_enabled and 'ma' in ind:
            ma = ind['ma']
            ma_valid = len(ma.dropna()) >= 2
            if ma_valid:
                last_ma = float(ma.iloc[-1]); prev_ma = float(ma.iloc[-2])
                trigger_desc.append(f"MA_prev={prev_ma:.8f},MA_last={last_ma:.8f}")
                buy_allowed = cfg['side'] in ('BUY', 'BOTH')
                sell_allowed = cfg['side'] in ('SELL', 'BOTH')
                if buy_allowed and prev_close < prev_ma and last_close > last_ma:
                    trigger_actions["ma"] = "buy"
                    trigger_desc.append("MA crossover -> BUY")
                    trigger_sources.append("ma")
                    if signal is None:
                        signal = 'BUY'
                elif sell_allowed and prev_close > prev_ma and last_close < last_ma:
                    trigger_actions["ma"] = "sell"
                    trigger_desc.append("MA crossover -> SELL")
                    trigger_sources.append("ma")
                    if signal is None:
                        signal = 'SELL'

        # --- BB context (informational)
        if cfg['indicators'].get('bb', {}).get('enabled', False) and 'bb_upper' in ind and not ind['bb_upper'].isnull().all():
            try:
                bu = float(ind['bb_upper'].iloc[-1]); bm = float(ind['bb_mid'].iloc[-1]); bl = float(ind['bb_lower'].iloc[-1])
                trigger_desc.append(f"BB_up={bu:.8f},BB_mid={bm:.8f},BB_low={bl:.8f}")
            except Exception:
                pass

        if not trigger_desc:
            trigger_desc = ["No triggers evaluated"]

        trigger_price = last_close if signal else None
        trigger_sources = list(dict.fromkeys(trigger_sources))
        return signal, " | ".join(trigger_desc), trigger_price, trigger_sources, trigger_actions

    def run_once(self):
        cw = self.config
        if self.stopped():
            return
        stop_cfg = normalize_stop_loss_dict(cw.get("stop_loss"))
        stop_mode = str(stop_cfg.get("mode") or "usdt").lower()
        if stop_mode not in STOP_LOSS_MODE_ORDER:
            stop_mode = STOP_LOSS_MODE_ORDER[0]
        stop_usdt_limit = max(0.0, float(stop_cfg.get("usdt", 0.0) or 0.0))
        stop_percent_limit = max(0.0, float(stop_cfg.get("percent", 0.0) or 0.0))
        scope = str(stop_cfg.get("scope") or "per_trade").lower()
        if scope not in STOP_LOSS_SCOPE_OPTIONS:
            scope = STOP_LOSS_SCOPE_OPTIONS[0]
        stop_enabled = bool(stop_cfg.get("enabled", False))
        apply_usdt_limit = stop_enabled and stop_mode in ("usdt", "both") and stop_usdt_limit > 0.0
        apply_percent_limit = stop_enabled and stop_mode in ("percent", "both") and stop_percent_limit > 0.0
        stop_enabled = apply_usdt_limit or apply_percent_limit
        account_type = str((self.config.get("account_type") or self.binance.account_type)).upper()
        is_cumulative = stop_enabled and scope == "cumulative"
        is_entire_account = stop_enabled and scope == "entire_account"
        if is_entire_account and account_type == "FUTURES":
            total_unrealized = 0.0
            try:
                total_unrealized = float(self.binance.get_total_unrealized_pnl())
            except Exception:
                total_unrealized = 0.0
            triggered = False
            reason = None
            if apply_usdt_limit and total_unrealized <= -stop_usdt_limit:
                triggered = True
                reason = f"entire-account-usdt-limit ({total_unrealized:.2f})"
            if not triggered and apply_percent_limit:
                total_wallet = 0.0
                try:
                    total_wallet = float(self.binance.get_total_wallet_balance())
                except Exception:
                    total_wallet = 0.0
                if total_wallet > 0.0 and total_unrealized < 0.0:
                    loss_pct = (abs(total_unrealized) / total_wallet) * 100.0
                    if loss_pct >= stop_percent_limit:
                        triggered = True
                        reason = f"entire-account-percent-limit ({loss_pct:.2f}%)"
            if triggered:
                try:
                    self.log(f"{cw['symbol']}@{cw.get('interval')} entire account stop-loss triggered: {reason}.")
                except Exception:
                    pass
                self._trigger_emergency_close(cw['symbol'], cw.get('interval'), reason or "entire_account_stop")
                return
        elif is_entire_account:
            stop_enabled = False
        df = self.binance.get_klines(cw['symbol'], cw['interval'], limit=cw.get('lookback', 200))
        ind = self.compute_indicators(df)
        signal, trigger_desc, trigger_price, trigger_sources, trigger_actions = self.generate_signal(df, ind)
        signal_timestamp = time.time() if signal else None
        try:
            current_bar_marker = int(df.index[-1].value) if not df.empty else None
        except Exception:
            current_bar_marker = None
        
        # --- RSI guard-close (interval-scoped) ---
        try:
            rsi_series = ind.get('rsi') or ind.get('RSI') or None
            if rsi_series is not None:
                _, _, last_rsi = self._indicator_prev_live_signal_values(rsi_series)
            else:
                last_rsi = None
        except Exception:
            last_rsi = None

        # Open-state via internal ledger (per symbol, interval, side)
        key_short = (cw['symbol'], cw.get('interval'), 'SELL')
        key_long  = (cw['symbol'], cw.get('interval'), 'BUY')
        short_open = bool(self._leg_ledger.get(key_short, {}).get('qty', 0) > 0)
        long_open  = bool(self._leg_ledger.get(key_long,  {}).get('qty', 0) > 0)

        dual_side = False
        desired_ps_long_guard = None
        desired_ps_short_guard = None
        if account_type == "FUTURES":
            try:
                dual_side = bool(self.binance.get_futures_dual_side())
            except Exception:
                dual_side = False
            desired_ps_long_guard = "LONG" if dual_side else None
            desired_ps_short_guard = "SHORT" if dual_side else None
        allow_opposite_enabled = coerce_bool(self.config.get("allow_opposite_positions"), True)
        hedge_overlap_allowed = bool(dual_side and allow_opposite_enabled)

        # Exit thresholds
        try:
            rsi_cfg = cw.get('indicators',{}).get('rsi',{})
            exit_up = float(rsi_cfg.get('sell_value', 70))
            exit_dn = float(rsi_cfg.get('buy_value', 30))
        except Exception:
            exit_up, exit_dn = 70.0, 30.0

        if account_type == "FUTURES" and last_rsi is not None:
            interval_current = cw.get('interval')
            try:
                if last_rsi >= exit_up and self._indicator_has_open(cw['symbol'], interval_current, 'rsi', 'BUY'):
                    try:
                        closed_long, _ = self._close_indicator_positions(
                            cw,
                            interval_current,
                            'rsi',
                            'BUY',
                            desired_ps_long_guard,
                            ignore_hold=True,
                        )
                    except Exception:
                        closed_long = 0
                    if closed_long:
                        long_open = bool(self._leg_ledger.get(key_long, {}).get('qty', 0) > 0)
                        try:
                            plural = "entry" if closed_long == 1 else "entries"
                            self.log(
                                f"Closed {closed_long} RSI LONG {plural} for {cw['symbol']}@{cw.get('interval')} (RSI >= {exit_up})."
                            )
                        except Exception:
                            pass
                if last_rsi <= exit_dn and self._indicator_has_open(cw['symbol'], interval_current, 'rsi', 'SELL'):
                    try:
                        closed_short, _ = self._close_indicator_positions(
                            cw,
                            interval_current,
                            'rsi',
                            'SELL',
                            desired_ps_short_guard,
                            ignore_hold=True,
                        )
                    except Exception:
                        closed_short = 0
                    if closed_short:
                        short_open = bool(self._leg_ledger.get(key_short, {}).get('qty', 0) > 0)
                        try:
                            plural = "entry" if closed_short == 1 else "entries"
                            self.log(
                                f"Closed {closed_short} RSI SHORT {plural} for {cw['symbol']}@{cw.get('interval')} (RSI <= {exit_dn})."
                            )
                        except Exception:
                            pass
            except Exception:
                pass

        last_price = None
        try:
            live_price = float(self.binance.get_last_price(cw['symbol']) or 0.0)
            if live_price > 0.0:
                last_price = live_price
        except Exception:
            last_price = None
        if last_price is None and not df.empty:
            try:
                last_price = float(df['close'].iloc[-1])
            except Exception:
                last_price = None
        positions_cache = None

        def _load_positions_cache():
            nonlocal positions_cache
            if positions_cache is None:
                try:
                    positions_cache = self.binance.list_open_futures_positions() or []
                except Exception:
                    positions_cache = []
            return positions_cache or []

        if stop_enabled and last_price is not None and account_type == "FUTURES":
            def _ensure_entry_price(leg_key, expect_long: bool):
                leg = self._leg_ledger.get(leg_key, {}) or {}
                qty_val = float(leg.get("qty") or 0.0)
                entry_px = float(leg.get("entry_price") or 0.0)
                matched_pos = None
                cache = _load_positions_cache()
                for pos in cache:
                    try:
                        if str(pos.get("symbol") or "").upper() != cw["symbol"]:
                            continue
                        amt = float(pos.get("positionAmt") or 0.0)
                        if dual_side:
                            pos_side = str(pos.get("positionSide") or "").upper()
                            if expect_long and pos_side != "LONG":
                                continue
                            if (not expect_long) and pos_side != "SHORT":
                                continue
                            qty_candidate = abs(amt)
                        else:
                            if expect_long and amt <= 0.0:
                                continue
                            if (not expect_long) and amt >= 0.0:
                                continue
                            qty_candidate = abs(amt)
                        if qty_candidate <= 0.0:
                            continue
                        matched_pos = pos
                        if entry_px <= 0.0:
                            try:
                                entry_px = float(pos.get("entryPrice") or entry_px)
                            except Exception:
                                pass
                        break
                    except Exception:
                        continue
                if matched_pos and entry_px > 0.0:
                    leg["entry_price"] = entry_px
                    self._leg_ledger[leg_key] = leg
                return leg, qty_val, entry_px, matched_pos

            leg_long, qty_long, entry_price_long, pos_long = _ensure_entry_price(key_long, True)
            leg_short, qty_short, entry_price_short, pos_short = _ensure_entry_price(key_short, False)
            pos_long_qty_total = 0.0
            pos_short_qty_total = 0.0

            if qty_long <= 0.0 and pos_long:
                try:
                    qty_long = max(0.0, float(pos_long.get("positionAmt") or 0.0))
                except Exception:
                    qty_long = 0.0
                if qty_long > 0.0:
                    self._sync_leg_entry_totals(key_long, qty_long)
            if pos_long:
                try:
                    amt_val = float(pos_long.get("positionAmt") or 0.0)
                    pos_long_qty_total = abs(amt_val)
                except Exception:
                    pos_long_qty_total = 0.0
            if qty_short <= 0.0 and pos_short:
                try:
                    qty_short = abs(float(pos_short.get("positionAmt") or 0.0))
                except Exception:
                    qty_short = 0.0
                if qty_short > 0.0:
                    self._sync_leg_entry_totals(key_short, qty_short)
            if pos_short:
                try:
                    amt_val = float(pos_short.get("positionAmt") or 0.0)
                    pos_short_qty_total = abs(amt_val)
                except Exception:
                    pos_short_qty_total = 0.0

            entries_long = self._leg_entries(key_long)
            entries_short = self._leg_entries(key_short)

            if scope == "per_trade":
                if entries_long:
                    self._evaluate_per_trade_stop(
                        cw,
                        key_long,
                        entries_long,
                        side_label="BUY",
                        last_price=last_price,
                        apply_usdt_limit=apply_usdt_limit,
                        apply_percent_limit=apply_percent_limit,
                        stop_usdt_limit=stop_usdt_limit,
                        stop_percent_limit=stop_percent_limit,
                        dual_side=dual_side,
                    )
                if entries_short:
                    self._evaluate_per_trade_stop(
                        cw,
                        key_short,
                        entries_short,
                        side_label="SELL",
                        last_price=last_price,
                        apply_usdt_limit=apply_usdt_limit,
                        apply_percent_limit=apply_percent_limit,
                        stop_usdt_limit=stop_usdt_limit,
                        stop_percent_limit=stop_percent_limit,
                        dual_side=dual_side,
                    )
                leg_long = self._leg_ledger.get(key_long, {}) or {}
                leg_short = self._leg_ledger.get(key_short, {}) or {}
                qty_long = float(leg_long.get("qty") or 0.0)
                qty_short = float(leg_short.get("qty") or 0.0)
                entry_price_long = float(leg_long.get("entry_price") or 0.0)
                entry_price_short = float(leg_short.get("entry_price") or 0.0)
            elif is_cumulative:
                cache = _load_positions_cache()
                totals = {
                    "LONG": {"qty": 0.0, "loss": 0.0, "margin": 0.0},
                    "SHORT": {"qty": 0.0, "loss": 0.0, "margin": 0.0},
                }
                for pos in cache:
                    try:
                        if str(pos.get("symbol") or "").upper() != cw["symbol"]:
                            continue
                        pos_side = str(pos.get("positionSide") or "").upper()
                        amt = float(pos.get("positionAmt") or 0.0)
                        entry_px = float(pos.get("entryPrice") or 0.0)
                        if entry_px <= 0.0:
                            continue
                        if dual_side:
                            if pos_side == "LONG":
                                qty_pos = max(0.0, float(pos.get("positionAmt") or 0.0))
                                side_key = "LONG"
                            elif pos_side == "SHORT":
                                qty_pos = max(0.0, abs(float(pos.get("positionAmt") or 0.0)))
                                side_key = "SHORT"
                            else:
                                continue
                        else:
                            if amt > 0.0:
                                qty_pos = amt
                                side_key = "LONG"
                            elif amt < 0.0:
                                qty_pos = abs(amt)
                                side_key = "SHORT"
                            else:
                                continue
                        if qty_pos <= 0.0:
                            continue
                        margin_val = float(pos.get("isolatedWallet") or 0.0)
                        if margin_val <= 0.0:
                            margin_val = float(pos.get("initialMargin") or 0.0)
                        if margin_val <= 0.0:
                            notional_val = abs(float(pos.get("notional") or 0.0))
                            lev = float(pos.get("leverage") or 1.0) or 1.0
                            if lev > 0.0:
                                margin_val = notional_val / lev
                        if side_key == "LONG":
                            loss_val = max(0.0, (entry_px - last_price) * qty_pos)
                        else:
                            loss_val = max(0.0, (last_price - entry_px) * qty_pos)
                        totals[side_key]["qty"] += qty_pos
                        totals[side_key]["loss"] += loss_val
                        totals[side_key]["margin"] += max(0.0, margin_val)
                    except Exception:
                        continue
                cumulative_triggered = False
                for side_key in ("LONG", "SHORT"):
                    data = totals[side_key]
                    if data["qty"] <= 0.0:
                        continue
                    triggered = False
                    if apply_usdt_limit and data["loss"] >= stop_usdt_limit:
                        triggered = True
                    if (
                        not triggered
                        and apply_percent_limit
                        and data["margin"] > 0.0
                        and (data["loss"] / data["margin"] * 100.0) >= stop_percent_limit
                    ):
                        triggered = True
                    if not triggered:
                        continue
                    cumulative_triggered = True
                    close_side = "SELL" if side_key == "LONG" else "BUY"
                    position_side = side_key if dual_side else None
                    start_ts = time.time()
                    try:
                        res = self.binance.close_futures_leg_exact(
                            cw["symbol"], data["qty"], side=close_side, position_side=position_side
                        )
                    except Exception as exc:
                        try:
                            self.log(f"Cumulative stop-loss close error for {cw['symbol']} ({side_key}): {exc}")
                        except Exception:
                            pass
                        continue
                    if isinstance(res, dict) and res.get("ok"):
                        latency_s = max(0.0, time.time() - start_ts)
                        target_side_label = "BUY" if side_key == "LONG" else "SELL"
                        payload = self._build_close_event_payload(
                            cw["symbol"], cw.get("interval"), target_side_label, data["qty"], res
                        )
                        for leg_key in list(self._leg_ledger.keys()):
                            if leg_key[0] == cw["symbol"] and leg_key[2] == target_side_label:
                                self._remove_leg_entry(leg_key, None)
                        try:
                            if hasattr(self.guard, "mark_closed"):
                                self.guard.mark_closed(cw["symbol"], cw.get("interval"), target_side_label)
                        except Exception:
                            pass
                        self._notify_interval_closed(
                            cw["symbol"],
                            cw.get("interval"),
                            target_side_label,
                            **payload,
                            latency_seconds=latency_s,
                            latency_ms=latency_s * 1000.0,
                            reason="cumulative_stop_loss",
                        )
                        try:
                            margin_val = data["margin"] or 0.0
                            pct_loss = (data["loss"] / margin_val * 100.0) if margin_val > 0.0 else 0.0
                            self._log_latency_metric(
                                cw["symbol"],
                                cw.get("interval"),
                                f"cumulative stop-loss {target_side_label}",
                                latency_s,
                            )
                            self.log(
                                f"Cumulative stop-loss closed {target_side_label} for {cw['symbol']}@{cw.get('interval')} "
                                f"(loss {data['loss']:.4f} USDT / {pct_loss:.2f}%)."
                            )
                        except Exception:
                            pass
                    else:
                        try:
                            self.log(
                                f"Cumulative stop-loss close failed for {cw['symbol']} ({side_key}): {res}"
                            )
                        except Exception:
                            pass
                if cumulative_triggered:
                    position_open = False
                    units = 0.0
                    position_margin = 0.0
                    direction = ""
                    long_open = False
                    short_open = False
            else:
                if qty_long > 0.0 and entry_price_long > 0.0:
                    loss_usdt_long = max(0.0, (entry_price_long - last_price) * qty_long)
                    denom_long = entry_price_long * qty_long
                    loss_pct_long = (loss_usdt_long / denom_long * 100.0) if denom_long > 0 else 0.0
                    margin_long, margin_balance_long, mm_long, unrealized_loss_long = self._compute_position_margin_fields(
                        pos_long,
                        qty_hint=qty_long,
                        entry_price_hint=entry_price_long,
                    )
                    ratio_long = normalize_margin_ratio((pos_long or {}).get("marginRatio"))
                    if ratio_long <= 0.0 and mm_long > 0.0 and margin_balance_long > 0.0:
                        ratio_long = ((mm_long + unrealized_loss_long) / margin_balance_long) * 100.0
                    if margin_long > 0.0:
                        try:
                            margin_share = margin_long
                            if pos_long_qty_total > 0.0 and qty_long > 0.0:
                                share = min(1.0, qty_long / pos_long_qty_total)
                                margin_share = max(margin_long * share, 1e-12)
                            margin_pct = (loss_usdt_long / margin_share) * 100.0
                            if margin_pct > loss_pct_long:
                                loss_pct_long = margin_pct
                        except Exception:
                            pass
                    triggered_long = False
                    if apply_usdt_limit and loss_usdt_long >= stop_usdt_limit:
                        triggered_long = True
                    if not triggered_long and apply_percent_limit and loss_pct_long >= stop_percent_limit:
                        triggered_long = True
                    if not triggered_long and apply_percent_limit and ratio_long >= stop_percent_limit:
                        triggered_long = True
                        if ratio_long > loss_pct_long:
                            loss_pct_long = ratio_long
                    if triggered_long:
                        desired_ps = "LONG" if dual_side else None
                        try:
                            start_ts = time.time()
                            res = self.binance.close_futures_leg_exact(
                                cw["symbol"], qty_long, side="SELL", position_side=desired_ps
                            )
                            if isinstance(res, dict) and res.get("ok"):
                                latency_s = max(0.0, time.time() - start_ts)
                                payload = self._build_close_event_payload(
                                    cw["symbol"], cw.get("interval"), "BUY", qty_long, res
                                )
                                self._remove_leg_entry(key_long, None)
                                long_open = False
                                try:
                                    if hasattr(self.guard, "mark_closed"):
                                        self.guard.mark_closed(cw["symbol"], cw.get("interval"), "BUY")
                                except Exception:
                                    pass
                                self._log_latency_metric(
                                    cw["symbol"],
                                    cw.get("interval"),
                                    "stop-loss BUY leg",
                                    latency_s,
                                )
                                self._notify_interval_closed(
                                    cw["symbol"],
                                    cw.get("interval"),
                                    "BUY",
                                    **payload,
                                    latency_seconds=latency_s,
                                    latency_ms=latency_s * 1000.0,
                                    reason="stop_loss_long",
                                )
                                try:
                                    self.log(
                                        f"Stop-loss closed BUY for {cw['symbol']}@{cw.get('interval')} "
                                        f"(loss {loss_usdt_long:.4f} USDT / {loss_pct_long:.2f}%)."
                                    )
                                except Exception:
                                    pass
                            else:
                                try:
                                    self.log(
                                        f"Stop-loss close failed for {cw['symbol']}@{cw.get('interval')} (BUY): {res}"
                                    )
                                except Exception:
                                    pass
                        except Exception as exc:
                            try:
                                self.log(
                                    f"Stop-loss close error for {cw['symbol']}@{cw.get('interval')} (BUY): {exc}"
                                )
                            except Exception:
                                pass
                if qty_short > 0.0 and entry_price_short > 0.0:
                    loss_usdt_short = max(0.0, (last_price - entry_price_short) * qty_short)
                    denom_short = entry_price_short * qty_short
                    loss_pct_short = (loss_usdt_short / denom_short * 100.0) if denom_short > 0 else 0.0
                    margin_short, margin_balance_short, mm_short, unrealized_loss_short_val = self._compute_position_margin_fields(
                        pos_short,
                        qty_hint=qty_short,
                        entry_price_hint=entry_price_short,
                    )
                    ratio_short = normalize_margin_ratio((pos_short or {}).get("marginRatio"))
                    if ratio_short <= 0.0 and mm_short > 0.0 and margin_balance_short > 0.0:
                        ratio_short = ((mm_short + unrealized_loss_short_val) / margin_balance_short) * 100.0
                    if margin_short > 0.0:
                        try:
                            margin_share = margin_short
                            if pos_short_qty_total > 0.0 and qty_short > 0.0:
                                share = min(1.0, qty_short / pos_short_qty_total)
                                margin_share = max(margin_short * share, 1e-12)
                            margin_pct = (loss_usdt_short / margin_share) * 100.0
                            if margin_pct > loss_pct_short:
                                loss_pct_short = margin_pct
                        except Exception:
                            pass
                    triggered_short = False
                    if apply_usdt_limit and loss_usdt_short >= stop_usdt_limit:
                        triggered_short = True
                    if not triggered_short and apply_percent_limit and loss_pct_short >= stop_percent_limit:
                        triggered_short = True
                    if not triggered_short and apply_percent_limit and ratio_short >= stop_percent_limit:
                        triggered_short = True
                        if ratio_short > loss_pct_short:
                            loss_pct_short = ratio_short
                    if triggered_short:
                        desired_ps = "SHORT" if dual_side else None
                        try:
                            start_ts = time.time()
                            res = self.binance.close_futures_leg_exact(
                                cw["symbol"], qty_short, side="BUY", position_side=desired_ps
                            )
                            if isinstance(res, dict) and res.get("ok"):
                                latency_s = max(0.0, time.time() - start_ts)
                                payload = self._build_close_event_payload(
                                    cw["symbol"], cw.get("interval"), "SELL", qty_short, res
                                )
                                self._remove_leg_entry(key_short, None)
                                short_open = False
                                try:
                                    if hasattr(self.guard, "mark_closed"):
                                        self.guard.mark_closed(cw["symbol"], cw.get("interval"), "SELL")
                                except Exception:
                                    pass
                                self._log_latency_metric(
                                    cw["symbol"],
                                    cw.get("interval"),
                                    "stop-loss SELL leg",
                                    latency_s,
                                )
                                self._notify_interval_closed(
                                    cw["symbol"],
                                    cw.get("interval"),
                                    "SELL",
                                    **payload,
                                    latency_seconds=latency_s,
                                    latency_ms=latency_s * 1000.0,
                                    reason="stop_loss_short",
                                )
                                try:
                                    self.log(
                                        f"Stop-loss closed SELL for {cw['symbol']}@{cw.get('interval')} "
                                        f"(loss {loss_usdt_short:.4f} USDT / {loss_pct_short:.2f}%)."
                                    )
                                except Exception:
                                    pass
                            else:
                                try:
                                    self.log(
                                        f"Stop-loss close failed for {cw['symbol']}@{cw.get('interval')} (SELL): {res}"
                                    )
                                except Exception:
                                    pass
                        except Exception as exc:
                            try:
                                    self.log(
                                        f"Stop-loss close error for {cw['symbol']}@{cw.get('interval')} (SELL): {exc}"
                                    )
                            except Exception:
                                pass
            leg_long_state = self._leg_ledger.get(key_long, {}) or {}
            leg_short_state = self._leg_ledger.get(key_short, {}) or {}
            qty_long = float(leg_long_state.get("qty") or 0.0)
            qty_short = float(leg_short_state.get("qty") or 0.0)
            entry_price_long = float(leg_long_state.get("entry_price") or 0.0)
            entry_price_short = float(leg_short_state.get("entry_price") or 0.0)
            long_open = qty_long > 0.0
            short_open = qty_short > 0.0

        indicator_order_requests: list[dict[str, object]] = []
        if trigger_actions:
            desired_ps_long = "LONG" if dual_side else None
            desired_ps_short = "SHORT" if dual_side else None
            now_indicator_ts = time.time()
            for indicator_name, indicator_action in trigger_actions.items():
                indicator_label = str(indicator_name or "").strip()
                if not indicator_label:
                    continue
                indicator_key = indicator_label.lower()
                if not indicator_key:
                    continue
                action_norm = str(indicator_action or "").strip().lower()
                interval_current = cw.get("interval")
                try:
                    interval_seconds_est = float(_interval_to_seconds(str(interval_current or "1m")))
                except Exception:
                    interval_seconds_est = 60.0
                indicator_interval_tokens: set[str] = set(self._tokenize_interval_label(interval_current))
                label_interval_tokens = StrategyEngine._extract_interval_tokens_from_labels([indicator_label])
                if label_interval_tokens:
                    indicator_interval_tokens.update(label_interval_tokens)
                if action_norm not in {"buy", "sell"}:
                    continue
                if not self._indicator_signal_confirmation_ready(
                    cw["symbol"],
                    interval_current,
                    indicator_key,
                    action_norm,
                    interval_seconds_est,
                    now_indicator_ts,
                ):
                    continue
                action_side_label = "BUY" if action_norm == "buy" else "SELL"
                cooldown_remaining = self._indicator_cooldown_remaining(
                    cw["symbol"],
                    interval_current,
                    indicator_key,
                    action_side_label,
                    interval_seconds_est,
                    now_indicator_ts,
                )
                if cooldown_remaining > 0.0:
                    try:
                        self.log(
                            f"{cw['symbol']}@{interval_current or 'default'} {indicator_key} "
                            f"{action_side_label} suppressed: cooldown {cooldown_remaining:.1f}s remaining."
                        )
                    except Exception:
                        pass
                    continue
                if action_norm == "buy":
                    remaining_indicator_qty = self._indicator_open_qty(
                        cw["symbol"],
                        interval_current,
                        indicator_key,
                        "SELL",
                        interval_aliases=indicator_interval_tokens,
                    )
                    closed_short = 0
                    closed_short_qty = 0.0
                    try:
                        needs_close_short = self._indicator_has_open(
                            cw["symbol"], interval_current, indicator_key, "SELL"
                        )
                    except Exception:
                        needs_close_short = False
                    if remaining_indicator_qty <= 0.0 and needs_close_short:
                        fallback_live_qty = self._indicator_trade_book_qty(
                            cw["symbol"],
                            interval_current,
                            indicator_key,
                            "SELL",
                        )
                        if fallback_live_qty <= 0.0:
                            try:
                                fallback_live_qty = max(
                                    0.0,
                                    float(
                                        self._current_futures_position_qty(
                                            cw["symbol"], "SELL", desired_ps_short
                                        )
                                        or 0.0
                                    ),
                                )
                            except Exception:
                                fallback_live_qty = 0.0
                        remaining_indicator_qty = fallback_live_qty
                    if remaining_indicator_qty > 0.0 or needs_close_short:
                        qty_cap = remaining_indicator_qty if remaining_indicator_qty > 0.0 else None
                        closed_short, closed_short_qty = self._close_indicator_positions(
                            cw,
                            interval_current,
                            indicator_key,
                            "SELL",
                            desired_ps_short,
                            signature_hint=(indicator_key,),
                            ignore_hold=True,
                            interval_aliases=indicator_interval_tokens,
                            qty_limit=qty_cap,
                        )
                        if closed_short <= 0:
                            try:
                                still_open = self._indicator_has_open(
                                    cw["symbol"], interval_current, indicator_key, "SELL"
                                )
                            except Exception:
                                still_open = False
                            if still_open:
                                target_qty_hint = qty_cap
                                if (target_qty_hint is None or target_qty_hint <= 0.0) and remaining_indicator_qty > 0.0:
                                    target_qty_hint = remaining_indicator_qty
                                if not self._close_opposite_position(
                                    cw["symbol"],
                                    interval_current,
                                    "BUY",
                                    trigger_signature=(indicator_key,),
                                    indicator_key=(indicator_key,),
                                    target_qty=target_qty_hint,
                                ):
                                    continue
                                closed_short = 1
                    if closed_short <= 0:
                        fallback_qty = self._indicator_trade_book_qty(
                            cw["symbol"],
                            interval_current,
                            indicator_key,
                            "SELL",
                        )
                        if fallback_qty <= 0.0:
                            try:
                                fallback_qty = max(
                                    0.0,
                                    float(
                                        self._current_futures_position_qty(
                                            cw["symbol"], "SELL", desired_ps_short
                                        )
                                        or 0.0
                                    ),
                                )
                            except Exception:
                                fallback_qty = 0.0
                        if fallback_qty > 0.0:
                            retry_count, retry_qty = self._close_indicator_positions(
                                cw,
                                interval_current,
                                indicator_key,
                                "SELL",
                                desired_ps_short,
                                signature_hint=(indicator_key,),
                                ignore_hold=True,
                                interval_aliases=indicator_interval_tokens,
                                qty_limit=fallback_qty,
                            )
                            closed_short = retry_count
                            closed_short_qty = retry_qty
                        if closed_short <= 0:
                            try:
                                self.log(
                                    f"{cw['symbol']}@{interval_current or 'default'} {indicator_key} BUY skipped:"
                                    " short leg still live on exchange."
                                )
                            except Exception:
                                pass
                            continue
                    flip_from_side = None
                    flip_qty = 0.0
                    flip_qty_target = 0.0
                    remaining_indicator_qty = self._indicator_open_qty(
                        cw["symbol"],
                        interval_current,
                        indicator_key,
                        "SELL",
                        interval_aliases=indicator_interval_tokens,
                    )
                    if closed_short > 0 and closed_short_qty > 0.0:
                        flip_from_side = "SELL"
                        flip_qty = closed_short_qty
                        flip_qty_target = closed_short_qty
                        try:
                            self.log(
                                f"{cw['symbol']}@{interval_current} {indicator_key} flip SELL→BUY "
                                f"(closed {flip_qty:.10f})."
                            )
                        except Exception:
                            pass
                    elif remaining_indicator_qty > 0.0:
                        try:
                            self.log(
                                f"{cw['symbol']}@{interval_current or 'default'} {indicator_key} BUY deferred: "
                                f"{remaining_indicator_qty:.10f} short qty still open."
                            )
                        except Exception:
                            pass
                        continue
                    else:
                        live_short_residual = 0.0
                        try:
                            live_short_residual = max(
                                0.0,
                                float(self._current_futures_position_qty(cw["symbol"], "SELL", desired_ps_short)),
                            )
                        except Exception:
                            live_short_residual = 0.0
                        tol_live = max(1e-9, live_short_residual * 1e-6)
                        if live_short_residual > tol_live:
                            try:
                                self.log(
                                    f"{cw['symbol']}@{interval_current or 'default'} {indicator_key} BUY forcing close of residual short "
                                    f"({live_short_residual:.10f})."
                                )
                            except Exception:
                                pass
                            if not self._close_opposite_position(
                                cw["symbol"],
                                interval_current,
                                "BUY",
                                trigger_signature=(indicator_key,),
                                indicator_key=(indicator_key,),
                                target_qty=live_short_residual,
                            ):
                                continue
                            flip_from_side = "SELL"
                            flip_qty = live_short_residual
                            flip_qty_target = live_short_residual
                        elif self._indicator_has_open(cw["symbol"], interval_current, indicator_key, "SELL"):
                            try:
                                self.log(
                                    f"Skip BUY for {cw['symbol']}@{interval_current} ({indicator_key}): short leg still syncing (waiting for ledger)."
                                )
                            except Exception:
                                pass
                            continue
                    if self._indicator_has_open(cw["symbol"], interval_current, indicator_key, "BUY"):
                        continue
                    indicator_order_requests.append(
                        {
                            "side": "BUY",
                            "labels": [indicator_label],
                            "signature": (indicator_key,),
                            "indicator_key": indicator_key,
                            "flip_from": flip_from_side,
                            "flip_qty": flip_qty,
                            "flip_qty_target": flip_qty_target,
                        }
                    )
                elif action_norm == "sell":
                    # Close existing longs for this indicator on this interval.
                    remaining_long_qty = self._indicator_open_qty(
                        cw["symbol"],
                        interval_current,
                        indicator_key,
                        "BUY",
                        interval_aliases=indicator_interval_tokens,
                    )
                    closed_long = 0
                    closed_long_qty = 0.0
                    try:
                        needs_close_long = self._indicator_has_open(
                            cw["symbol"], interval_current, indicator_key, "BUY"
                        )
                    except Exception:
                        needs_close_long = False
                    if remaining_long_qty <= 0.0 and needs_close_long:
                        fallback_live_qty = self._indicator_trade_book_qty(
                            cw["symbol"],
                            interval_current,
                            indicator_key,
                            "BUY",
                        )
                        if fallback_live_qty <= 0.0:
                            try:
                                fallback_live_qty = max(
                                    0.0,
                                    float(
                                        self._current_futures_position_qty(
                                            cw["symbol"], "BUY", desired_ps_long
                                        )
                                        or 0.0
                                    ),
                                )
                            except Exception:
                                fallback_live_qty = 0.0
                        remaining_long_qty = fallback_live_qty
                        if remaining_long_qty > 0.0 or needs_close_long:
                            qty_cap = remaining_long_qty if remaining_long_qty > 0.0 else None
                            closed_long, closed_long_qty = self._close_indicator_positions(
                                cw,
                                interval_current,
                            indicator_key,
                            "BUY",
                            desired_ps_long,
                            signature_hint=(indicator_key,),
                            ignore_hold=True,
                            interval_aliases=indicator_interval_tokens,
                            qty_limit=qty_cap,
                        )
                            if closed_long <= 0:
                                try:
                                    still_open = self._indicator_has_open(
                                        cw["symbol"], interval_current, indicator_key, "BUY"
                                    )
                                except Exception:
                                    still_open = False
                                if still_open:
                                    target_qty_hint = qty_cap
                                    if (target_qty_hint is None or target_qty_hint <= 0.0) and remaining_long_qty > 0.0:
                                        target_qty_hint = remaining_long_qty
                                    if not self._close_opposite_position(
                                        cw["symbol"],
                                        interval_current,
                                        "SELL",
                                        trigger_signature=(indicator_key,),
                                        indicator_key=(indicator_key,),
                                        target_qty=target_qty_hint,
                                    ):
                                        continue
                                    closed_long = 1
                    if closed_long <= 0:
                        fallback_qty = self._indicator_trade_book_qty(
                            cw["symbol"],
                            interval_current,
                            indicator_key,
                            "BUY",
                        )
                        if fallback_qty <= 0.0:
                            try:
                                fallback_qty = max(
                                    0.0,
                                    float(
                                        self._current_futures_position_qty(
                                            cw["symbol"], "BUY", desired_ps_long
                                        )
                                        or 0.0
                                    ),
                                )
                            except Exception:
                                fallback_qty = 0.0
                        if fallback_qty > 0.0:
                            retry_count, retry_qty = self._close_indicator_positions(
                                cw,
                                interval_current,
                                indicator_key,
                                "BUY",
                                desired_ps_long,
                                signature_hint=(indicator_key,),
                                ignore_hold=True,
                                interval_aliases=indicator_interval_tokens,
                                qty_limit=fallback_qty,
                            )
                            closed_long = retry_count
                            closed_long_qty = retry_qty
                        if closed_long <= 0:
                            try:
                                self.log(
                                    f"{cw['symbol']}@{interval_current or 'default'} {indicator_key} SELL skipped:"
                                    " long leg still live on exchange."
                                )
                            except Exception:
                                pass
                            continue
                    flip_from_side = None
                    flip_qty = 0.0
                    flip_qty_target = 0.0
                    remaining_indicator_qty = self._indicator_open_qty(
                        cw["symbol"],
                        interval_current,
                        indicator_key,
                        "BUY",
                        interval_aliases=indicator_interval_tokens,
                    )
                    if closed_long > 0 and closed_long_qty > 0.0:
                        flip_from_side = "BUY"
                        flip_qty = closed_long_qty
                        flip_qty_target = closed_long_qty
                        try:
                            self.log(
                                f"{cw['symbol']}@{interval_current} {indicator_key} flip BUY→SELL "
                                f"(closed {flip_qty:.10f})."
                            )
                        except Exception:
                            pass
                    elif remaining_indicator_qty > 0.0:
                        try:
                            self.log(
                                f"{cw['symbol']}@{interval_current or 'default'} {indicator_key} SELL deferred: "
                                f"{remaining_indicator_qty:.10f} long qty still open."
                            )
                        except Exception:
                            pass
                        continue
                    else:
                        live_long_residual = 0.0
                        try:
                            live_long_residual = max(
                                0.0,
                                float(self._current_futures_position_qty(cw["symbol"], "BUY", desired_ps_long)),
                            )
                        except Exception:
                            live_long_residual = 0.0
                        tol_live = max(1e-9, live_long_residual * 1e-6)
                        if live_long_residual > tol_live:
                            try:
                                self.log(
                                    f"{cw['symbol']}@{interval_current or 'default'} {indicator_key} SELL forcing close of residual long "
                                    f"({live_long_residual:.10f})."
                                )
                            except Exception:
                                pass
                            if not self._close_opposite_position(
                                cw["symbol"],
                                interval_current,
                                "SELL",
                                trigger_signature=(indicator_key,),
                                indicator_key=(indicator_key,),
                                target_qty=live_long_residual,
                            ):
                                continue
                            flip_from_side = "BUY"
                            flip_qty = live_long_residual
                            flip_qty_target = live_long_residual
                        elif self._indicator_has_open(cw["symbol"], interval_current, indicator_key, "BUY"):
                            try:
                                self.log(
                                    f"Skip SELL for {cw['symbol']}@{interval_current} ({indicator_key}): long leg still syncing (waiting for ledger)."
                                )
                            except Exception:
                                pass
                            continue
                    if self._indicator_has_open(cw["symbol"], interval_current, indicator_key, "SELL"):
                        continue
                    indicator_order_requests.append(
                        {
                            "side": "SELL",
                            "labels": [indicator_label],
                            "signature": (indicator_key,),
                            "indicator_key": indicator_key,
                            "flip_from": flip_from_side,
                            "flip_qty": flip_qty,
                            "flip_qty_target": flip_qty_target,
                        }
                    )
            if not indicator_order_requests:
                for indicator_name, indicator_action in trigger_actions.items():
                    indicator_label = str(indicator_name or "").strip()
                    if not indicator_label:
                        continue
                    indicator_key = indicator_label.lower()
                    interval_current = cw.get("interval")
                    action_norm = str(indicator_action or "").strip().lower()
                    try:
                        interval_seconds_est = float(_interval_to_seconds(str(interval_current or "1m")))
                    except Exception:
                        interval_seconds_est = 60.0
                    if action_norm not in {"buy", "sell"}:
                        continue
                    if not self._indicator_signal_confirmation_ready(
                        cw["symbol"],
                        interval_current,
                        indicator_key,
                        action_norm,
                        interval_seconds_est,
                        now_indicator_ts,
                    ):
                        continue
                    if action_norm == "buy":
                        if not hedge_overlap_allowed:
                            live_short_qty = 0.0
                            try:
                                live_short_qty = max(
                                    0.0,
                                    float(self._current_futures_position_qty(cw["symbol"], "SELL", desired_ps_short)),
                                )
                            except Exception:
                                live_short_qty = 0.0
                            if live_short_qty > 0.0:
                                try:
                                    self.log(
                                        f"{cw['symbol']}@{interval_current or 'default'} {indicator_key} BUY skipped:"
                                        f" short leg still live on exchange ({live_short_qty:.10f})."
                                    )
                                except Exception:
                                    pass
                                continue
                        indicator_order_requests.append(
                            {
                                "side": "BUY",
                                "labels": [indicator_label],
                                "signature": (indicator_key,),
                                "indicator_key": indicator_key,
                            }
                        )
                    else:
                        if not hedge_overlap_allowed:
                            live_long_qty = 0.0
                            try:
                                live_long_qty = max(
                                    0.0,
                                    float(self._current_futures_position_qty(cw["symbol"], "BUY", desired_ps_long)),
                                )
                            except Exception:
                                live_long_qty = 0.0
                            if live_long_qty > 0.0:
                                try:
                                    self.log(
                                        f"{cw['symbol']}@{interval_current or 'default'} {indicator_key} SELL skipped:"
                                        f" long leg still live on exchange ({live_long_qty:.10f})."
                                    )
                                except Exception:
                                    pass
                                continue
                        indicator_order_requests.append(
                            {
                                "side": "SELL",
                                "labels": [indicator_label],
                                "signature": (indicator_key,),
                                "indicator_key": indicator_key,
                            }
                        )
        thresholds = []
        try:
            if cw['indicators']['ma']['enabled'] and 'ma' in ind and not ind['ma'].isnull().all(): 
                thresholds.append(f"MA={float(ind['ma'].iloc[-1]):.8f}")
        except Exception: 
            pass

        ts = datetime.now().astimezone().strftime("%Y-%m-%d %H:%M:%S")
        parts = [f"{ts}", f"{cw['symbol']}@{cw['interval']}",
                 f"Price={last_price:.8f}" if last_price is not None else "Price=None",
                 f"Signal={signal if signal else 'None'}"]
        if trigger_price is not None: parts.append(f"TriggerPrice={trigger_price:.8f}")
        if thresholds: parts.append("Thresholds:" + ",".join(thresholds))
        parts.append("Details:" + trigger_desc)
        self.log(" | ".join(parts))

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
                if self._symbol_signature_active(cw["symbol"], side_value, signature, cw.get("interval")):
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
                    }
                )
        elif signal:
            orders_to_execute.append(
                {
                    "side": str(signal).upper(),
                    "labels": base_trigger_labels,
                    "signature": base_signature,
                    "timestamp": signal_timestamp,
                }
            )

        filtered_orders: list[dict[str, object]] = []
        if self.stopped():
            return
        for order in orders_to_execute:
            if self.stopped():
                return
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
            key_dup = (cw['symbol'], cw.get('interval'), side_upper)
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
            indicator_key_for_order = _canonical_indicator_token(order.get("indicator_key")) or None
            if not indicator_key_for_order:
                if len(sig_tuple_base) == 1:
                    indicator_key_for_order = sig_tuple_base[0]
                elif len(trigger_labels_raw) == 1:
                    indicator_key_for_order = _canonical_indicator_token(trigger_labels_raw[0]) or trigger_labels_raw[0].lower()
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
                        existing_qty = float(leg_dup.get('qty') or 0.0)
                    except Exception:
                        existing_qty = 0.0
                    signature_tracked_elsewhere = bool(active_signatures) and bool(signature) and signature not in active_signatures
                    if existing_qty > 0.0 and not signature_tracked_elsewhere:
                        side_is_long = side_upper == "BUY"

                        def _is_position_active(entries: list[dict] | None) -> bool:
                            for pos in entries or []:
                                try:
                                    if str(pos.get("symbol") or "").upper() != cw["symbol"]:
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

                        cache = _load_positions_cache()
                        position_active = _is_position_active(cache)
                        if not position_active:
                            try:
                                fresh_cache = self.binance.list_open_futures_positions(max_age=0.0, force_refresh=True) or []
                                if fresh_cache:
                                    positions_cache = fresh_cache  # capture latest snapshot
                                position_active = _is_position_active(fresh_cache)
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
                                interval_seconds = float(_interval_to_seconds(str(cw.get('interval') or '1m')))
                            except Exception:
                                interval_seconds = 60.0
                            guard_window = max(12.0, max(5.0, interval_seconds) * 1.2)
                            if elapsed < guard_window:
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
                    }
                )

        orders_to_execute = filtered_orders
        if not cw.get('trade_on_signal', True):
            orders_to_execute = []

        order_batch_total = len(orders_to_execute)
        order_batch_counter = 0

        def _execute_signal_order(
            order_side: str,
            indicator_labels: list[str],
            order_signature: tuple[str, ...],
            origin_timestamp: float | None,
            flip_from_side: str | None = None,
            flip_qty: float | int | None = None,
            flip_qty_target: float | int | None = None,
        ) -> None:
            nonlocal positions_cache, order_batch_counter, order_batch_total
            side = str(order_side or "").upper()
            if side not in ("BUY", "SELL"):
                return
            flip_from_norm = str(flip_from_side or "").upper()
            try:
                flip_qty_val = float(flip_qty or 0.0)
            except Exception:
                flip_qty_val = 0.0
            try:
                flip_qty_target_val = float(
                    flip_qty_target if flip_qty_target is not None else (flip_qty or 0.0)
                )
            except Exception:
                flip_qty_target_val = 0.0
            flip_active = flip_from_norm in ("BUY", "SELL") and flip_from_norm != side
            flip_qty_override = 0.0
            if flip_active:
                if flip_qty_target_val > 0.0:
                    flip_qty_override = flip_qty_target_val
                if flip_qty_val > 0.0:
                    try:
                        self.log(
                            f"{cw['symbol']}@{interval_norm or 'default'} flip {flip_from_norm}→{side} "
                            f"request (qty {flip_qty_val:.10f})."
                        )
                    except Exception:
                        pass
            current_batch_index = order_batch_counter
            order_batch_counter += 1
            trigger_labels = list(dict.fromkeys(indicator_labels or base_trigger_labels))
            if not trigger_labels:
                trigger_labels = [side.lower()]
            signature = tuple(order_signature or tuple(sorted(trigger_labels)))
            interval_norm = str(cw.get("interval") or "").strip()
            interval_key = interval_norm or "default"
            context_key = f"{interval_key}:{side}:{'|'.join(signature) if signature else side}"
            bar_sig_key = (cw["symbol"], interval_key, side)
            sig_sorted = tuple(sorted(signature)) if signature else (side.lower(),)
            signature_guard_key = sig_sorted if sig_sorted else (side.lower(),)
            signature_label = (
                "|".join(str(part) for part in signature_guard_key)
                if signature_guard_key
                else side.lower()
            )

            indicator_tokens_for_order = StrategyEngine._normalize_indicator_token_list(signature)
            if not indicator_tokens_for_order:
                indicator_tokens_for_order = StrategyEngine._normalize_indicator_token_list(trigger_labels)
            indicator_key_hint = self._indicator_token_from_signature(signature, trigger_labels)
            indicator_guard_override = flip_active
            guard_override_used = False
            indicator_opposite_side = 'SELL' if side == 'BUY' else 'BUY'
            indicator_tokens_for_guard = list(indicator_tokens_for_order)
            if indicator_key_hint:
                hint_norm = _canonical_indicator_token(indicator_key_hint) or indicator_key_hint
                if hint_norm and hint_norm not in indicator_tokens_for_guard:
                    indicator_tokens_for_guard.append(hint_norm)
            if indicator_tokens_for_guard and not indicator_guard_override:
                try:
                    indicator_guard_override = any(
                        self._indicator_has_open(
                            cw["symbol"],
                            interval_norm,
                            token,
                            indicator_opposite_side,
                        )
                        for token in indicator_tokens_for_guard
                    )
                except Exception:
                    indicator_guard_override = False

            active_check_signature = signature if signature else tuple(sorted(trigger_labels))
            if self._symbol_signature_active(cw["symbol"], side, active_check_signature, cw.get("interval")):
                try:
                    self.log(
                        f"{cw['symbol']}@{interval_key} duplicate {side} suppressed (signature {signature_label} still open)."
                    )
                except Exception:
                    pass
                return
            try:
                interval_seconds = float(_interval_to_seconds(str(cw.get("interval") or "1m")))
            except Exception:
                interval_seconds = 60.0
            fast_context = False
            try:
                fast_context = any(str(part or "").startswith("slot") for part in signature_guard_key)
            except Exception:
                fast_context = False
            guard_window_base = max(8.0, min(45.0, interval_seconds * 1.5))
            if fast_context:
                guard_window = min(
                    guard_window_base,
                    max(2.0, min(6.0, interval_seconds * 0.12)),
                )
            else:
                guard_window = guard_window_base
            if current_bar_marker is not None:
                with StrategyEngine._BAR_GUARD_LOCK:
                    global_tracker = StrategyEngine._BAR_GLOBAL_SIGNATURES.get(bar_sig_key)
                    if not global_tracker or global_tracker.get("bar") != current_bar_marker:
                        global_tracker = {"bar": current_bar_marker, "signatures": set()}
                        StrategyEngine._BAR_GLOBAL_SIGNATURES[bar_sig_key] = global_tracker
                    global_sig_set = global_tracker.setdefault("signatures", set())
                    if sig_sorted in global_sig_set:
                        try:
                            self.log(
                                f"{cw['symbol']}@{interval_key} global duplicate {side} suppressed (order already placed this bar)."
                            )
                        except Exception:
                            pass
                        return
                tracker = self._bar_order_tracker.get(bar_sig_key)
                if not tracker or tracker.get("bar") != current_bar_marker:
                    tracker = {"bar": current_bar_marker, "signatures": set()}
                    self._bar_order_tracker[bar_sig_key] = tracker
                sig_set = tracker.setdefault("signatures", set())
                if sig_sorted in sig_set:
                    if self.stopped():
                        return
                    try:
                        self.log(
                            f"{cw['symbol']}@{interval_key} duplicate {side} suppressed (order already placed this bar)."
                        )
                    except Exception:
                        pass
                    return
            guard_key_symbol = (cw["symbol"], side)
            now_guard = time.time()
            guard_claimed = False

            def _guard_abort():
                nonlocal guard_claimed
                if guard_claimed:
                    with StrategyEngine._SYMBOL_GUARD_LOCK:
                        entry_guard_abort = StrategyEngine._SYMBOL_ORDER_STATE.get(guard_key_symbol)
                        if isinstance(entry_guard_abort, dict):
                            pending_map_abort = entry_guard_abort.get("pending_map")
                            if not isinstance(pending_map_abort, dict):
                                pending_map_abort = {}
                            pending_map_abort.pop(signature_guard_key, None)
                            entry_guard_abort["pending_map"] = pending_map_abort
                            StrategyEngine._SYMBOL_ORDER_STATE[guard_key_symbol] = entry_guard_abort
                    guard_claimed = False
                return
            with StrategyEngine._SYMBOL_GUARD_LOCK:
                entry_guard = StrategyEngine._SYMBOL_ORDER_STATE.get(guard_key_symbol)
                if not isinstance(entry_guard, dict):
                    entry_guard = {}
                last_ts = float(entry_guard.get("last") or 0.0)
                signatures_state = entry_guard.get("signatures")
                if not isinstance(signatures_state, dict):
                    signatures_state = {}
                pending_map = entry_guard.get("pending_map")
                if not isinstance(pending_map, dict):
                    pending_map = {}
                # prune expired signature reservations
                try:
                    expired = [
                        sig
                        for sig, ts in list(signatures_state.items())
                        if now_guard - float(ts or 0.0) > guard_window
                    ]
                except Exception:
                    expired = []
                for sig in expired:
                    signatures_state.pop(sig, None)
                pending_expired = [
                    sig
                    for sig, ts in list(pending_map.items())
                    if now_guard - float(ts or 0.0) > guard_window * 1.5
                ]
                for sig in pending_expired:
                    pending_map.pop(sig, None)
                entry_guard["signatures"] = signatures_state
                entry_guard["pending_map"] = pending_map
                if signature_guard_key in pending_map:
                    if not indicator_guard_override:
                        try:
                            self.log(
                                f"{cw['symbol']}@{interval_key} symbol-level guard suppressed {side} entry "
                                f"(previous order still pending for {signature_label})."
                            )
                        except Exception:
                            pass
                        _guard_abort()
                        return
                    guard_override_used = True
                elapsed_since_last = now_guard - last_ts if last_ts > 0.0 else float("inf")
                if signature_guard_key in signatures_state:
                    if elapsed_since_last < guard_window:
                        if not indicator_guard_override:
                            try:
                                remaining = guard_window - elapsed_since_last
                                self.log(
                                    f"{cw['symbol']}@{interval_key} symbol-level guard suppressed {side} entry "
                                    f"(trigger {signature_label} still within guard window, wait {remaining:.1f}s)."
                                )
                            except Exception:
                                pass
                            _guard_abort()
                            return
                        guard_override_used = True
                    signatures_state.pop(signature_guard_key, None)
                elif not signatures_state and elapsed_since_last < guard_window:
                    if not indicator_guard_override:
                        try:
                            remaining = guard_window - elapsed_since_last
                            self.log(
                                f"{cw['symbol']}@{interval_key} symbol-level guard suppressed {side} entry "
                                f"(last order {elapsed_since_last:.1f}s ago, wait {remaining:.1f}s)."
                            )
                        except Exception:
                            pass
                        _guard_abort()
                        return
                    guard_override_used = True
                entry_guard["window"] = guard_window
                entry_guard["last"] = last_ts
                entry_guard["signatures"] = signatures_state
                pending_map[signature_guard_key] = now_guard
                entry_guard["pending_map"] = pending_map
                StrategyEngine._SYMBOL_ORDER_STATE[guard_key_symbol] = entry_guard
                guard_claimed = True
            if guard_override_used:
                try:
                    indicator_label = (indicator_key_hint or signature_label).upper()
                    self.log(
                        f"{cw['symbol']}@{interval_key} guard override: forcing {side} for indicator {indicator_label} "
                        f"to flip opposite exposure."
                    )
                except Exception:
                    pass
            try:
                account_type = str((self.config.get('account_type') or self.binance.account_type)).upper()
                usdt_bal = self.binance.get_total_usdt_value()
                pct_raw = float(cw.get('position_pct', 100.0))
                pct_units_raw = str(
                    cw.get('position_pct_units')
                    or cw.get('_position_pct_units')
                    or ""
                ).strip().lower()
                if pct_units_raw in {"percent", "%", "perc"}:
                    pct = pct_raw / 100.0
                elif pct_units_raw in {"fraction", "decimal", "ratio"}:
                    pct = pct_raw
                else:
                    pct = pct_raw / 100.0 if pct_raw > 1.0 else pct_raw
                pct = max(0.0001, min(1.0, pct))
                free_usdt = max(float(usdt_bal or 0.0), 0.0)
                price = last_price or 0.0

                if account_type == "FUTURES":
                    if price <= 0.0:
                        self.log(f"{cw['symbol']}@{cw.get('interval')} skipped: no market price available for sizing.")
                        _guard_abort()
                        return
                    try:
                        available_total = float(self.binance.get_futures_balance_usdt())
                    except Exception:
                        available_total = 0.0
                    try:
                        wallet_total = float(self.binance.get_total_wallet_balance())
                    except Exception:
                        wallet_total = 0.0
                    available_total = max(0.0, available_total)
                    wallet_total = max(0.0, wallet_total)
                    if wallet_total <= 0.0:
                        wallet_total = max(available_total, free_usdt)
                    ledger_margin_total = 0.0
                    try:
                        for leg_state in self._leg_ledger.values():
                            if not isinstance(leg_state, dict):
                                continue
                            margin_val = float(leg_state.get("margin_usdt") or 0.0)
                            if margin_val > 0.0:
                                ledger_margin_total += margin_val
                    except Exception:
                        ledger_margin_total = 0.0
                    equity_estimate = max(wallet_total, available_total + ledger_margin_total)
                    equity_estimate = max(equity_estimate, free_usdt + ledger_margin_total)
                    if equity_estimate <= 0.0:
                        equity_estimate = max(wallet_total, available_total, free_usdt, ledger_margin_total)
                    wallet_total = max(0.0, equity_estimate)
                    margin_tolerance = float(self.config.get("margin_over_target_tolerance", 0.05))
                    if margin_tolerance > 1.0:
                        margin_tolerance = margin_tolerance / 100.0
                    margin_tolerance = max(0.0, margin_tolerance)

                    try:
                        lev_raw = cw.get('leverage', self.config.get('leverage', 1))
                        lev = int(lev_raw)
                    except Exception:
                        lev = int(self.config.get('leverage', 1))
                    if lev <= 0:
                        lev = 1

                    per_indicator_margin_target = wallet_total * pct
                    if per_indicator_margin_target <= 0.0:
                        self.log(
                            f"{cw['symbol']}@{cw.get('interval')} sizing blocked: computed margin target <= 0 "
                            f"for {pct*100:.2f}% allocation."
                        )
                        _guard_abort()
                        return
                    per_indicator_notional_target = per_indicator_margin_target * float(lev)

                    sig_tuple_base = tuple(
                        sorted(
                            str(part or "").strip().lower()
                            for part in (signature or ())
                            if str(part or "").strip()
                        )
                    )
                    indicator_key_for_order = _canonical_indicator_token(indicator_key_hint) or indicator_key_hint
                    if not indicator_key_for_order and len(sig_tuple_base) == 1:
                        indicator_key_for_order = sig_tuple_base[0]
                    if not indicator_key_for_order and trigger_labels:
                        labels_norm = [
                            _canonical_indicator_token(lbl) or str(lbl or "").strip().lower()
                            for lbl in trigger_labels
                            if str(lbl or "").strip()
                        ]
                        if len(labels_norm) == 1:
                            indicator_key_for_order = labels_norm[0]
                    if indicator_key_for_order:
                        indicator_key_norm = _canonical_indicator_token(indicator_key_for_order) or indicator_key_for_order
                        if indicator_key_norm and indicator_key_norm not in indicator_tokens_for_order:
                            indicator_tokens_for_order.append(indicator_key_norm)

                    key_current_leg = (cw["symbol"], cw.get("interval"), side)
                    entries_side_all: list[tuple[tuple[str, str, str], dict]] = []
                    try:
                        for (leg_sym, leg_iv, leg_side), _ in list(self._leg_ledger.items()):
                            if str(leg_sym or "").upper() != str(cw["symbol"]).upper():
                                continue
                            leg_side_norm = str(leg_side or "").upper()
                            if leg_side_norm in {"LONG", "SHORT"}:
                                leg_side_norm = "BUY" if leg_side_norm == "LONG" else "SELL"
                            if leg_side_norm != side:
                                continue
                            leg_entries = self._leg_entries((leg_sym, leg_iv, leg_side))
                            for entry in leg_entries:
                                entries_side_all.append(((leg_sym, leg_iv, leg_side), entry))
                    except Exception:
                        entries_side_all = list(entries_side_all)

                    def _normalized_signature(entry_dict: dict) -> tuple[str, ...]:
                        raw_sig = entry_dict.get("trigger_signature") or entry_dict.get("trigger_indicators")
                        if isinstance(raw_sig, Iterable) and not isinstance(raw_sig, (str, bytes)):
                            parts: list[str] = []
                            for part in raw_sig:
                                text = str(part or "").strip().lower()
                                if text:
                                    parts.append(text)
                            parts.sort()
                            return tuple(parts)
                        return tuple()

                    def _slot_token_from_entry(entry_dict: dict) -> str:
                        iv_key = str(entry_dict.get("interval") or entry_dict.get("interval_display") or "").strip().lower()
                        indicator_ids = self._extract_indicator_keys(entry_dict)
                        if indicator_ids:
                            base = f"ind:{indicator_ids[0]}"
                        else:
                            sig_norm = _normalized_signature(entry_dict)
                            if sig_norm:
                                base = "sig:" + "|".join(sig_norm)
                            else:
                                ledger_id = entry_dict.get("ledger_id")
                                if ledger_id:
                                    base = f"id:{ledger_id}"
                                else:
                                    base = f"side:{side}"
                        if iv_key:
                            return f"{base}@{iv_key}"
                        return base

                    active_slot_tokens_all: set[str] = set()
                    for _, entry in entries_side_all:
                        active_slot_tokens_all.add(_slot_token_from_entry(entry))
                    if indicator_key_for_order:
                        indicator_entries_all = []
                        for leg_key, entry in entries_side_all:
                            keys_for_entry = self._extract_indicator_keys(entry)
                            if indicator_key_for_order in keys_for_entry:
                                indicator_entries_all.append((leg_key, entry))
                    elif sig_tuple_base:
                        indicator_entries_all = [
                            (leg_key, entry)
                            for leg_key, entry in entries_side_all
                            if _normalized_signature(entry) == sig_tuple_base
                        ]
                    else:
                        indicator_entries_all = entries_side_all[:]

                    existing_margin_indicator_total = sum(
                        self._entry_margin_value(entry, lev) for _, entry in indicator_entries_all
                    )

                    slot_token_base = (
                        f"ind:{indicator_key_for_order}"
                        if indicator_key_for_order
                        else (
                            "sig:" + "|".join(sig_tuple_base)
                            if sig_tuple_base
                            else f"side:{side}"
                        )
                    )
                    order_iv_key = str(cw.get('interval') or '').strip().lower()
                    slot_token_for_order = f"{slot_token_base}@{order_iv_key}" if order_iv_key else slot_token_base
                    slot_label = (
                        indicator_key_for_order.upper()
                        if indicator_key_for_order
                        else ("|".join(sig_tuple_base) if sig_tuple_base else "current slot")
                    )
                    slot_count_existing = len(indicator_entries_all)
                    slot_suffix = f"slot{slot_count_existing}"
                    if signature:
                        signature = tuple(list(signature) + [slot_suffix])
                    else:
                        signature = (slot_suffix,)
                    if isinstance(trigger_labels, (list, tuple)):
                        try:
                            base_labels = [str(lbl).strip() for lbl in trigger_labels if str(lbl).strip()]
                        except Exception:
                            base_labels = []
                    elif isinstance(trigger_labels, str) and trigger_labels.strip():
                        base_labels = [trigger_labels.strip()]
                    else:
                        base_labels = []
                    trigger_labels = base_labels
                    sig_tuple_for_order = tuple(
                        sorted(
                            str(part or "").strip().lower()
                            for part in (signature or ())
                            if str(part or "").strip()
                        )
                    )
                    desired_slots_after = slot_count_existing + 1
                    context_key = f"{context_key}|slot{slot_count_existing}"
                    max_indicator_margin = per_indicator_margin_target * desired_slots_after * (1.0 + margin_tolerance)
                    if existing_margin_indicator_total >= max_indicator_margin - 1e-9:
                        self.log(
                            f"{cw['symbol']}@{cw.get('interval')} capital guard: existing {side} margin for {slot_label} "
                            f"{existing_margin_indicator_total:.4f} USDT already >= cap {max_indicator_margin:.4f} USDT "
                            f"({pct*100:.2f}% margin target → {per_indicator_notional_target:.4f} USDT notional @ {lev}x)."
                        )
                        _guard_abort()
                        return

                    desired_total_margin = per_indicator_margin_target * desired_slots_after
                    target_margin = max(0.0, desired_total_margin - existing_margin_indicator_total)
                    if flip_qty_override > 0.0:
                        flip_margin = (flip_qty_override * price) / float(lev)
                        if flip_margin > target_margin:
                            target_margin = flip_margin
                    if target_margin <= 0.0:
                        self.log(
                            f"{cw['symbol']}@{cw.get('interval')} capital guard: {slot_label} exposure already meets "
                            f"the {pct*100:.2f}% margin allocation target."
                        )
                        _guard_abort()
                        return

                    if available_total <= 0.0:
                        available_total = free_usdt
                    if available_total <= 0.0:
                        self.log(f"{cw['symbol']}@{cw.get('interval')} capital guard: no available USDT to allocate.")
                        _guard_abort()
                        return
                    if available_total < target_margin * 0.95:
                        self.log(
                            f"{cw['symbol']}@{cw.get('interval')} capital guard: requested {target_margin:.4f} USDT "
                            f"({pct*100:.2f}% margin target) but only {available_total:.4f} USDT available."
                        )
                        _guard_abort()
                        return

                    existing_margin_same_side = sum(
                        self._entry_margin_value(entry, lev) for _, entry in entries_side_all
                    )

                    if flip_qty_override > 0.0:
                        qty_target = flip_qty_override
                    else:
                        qty_target = (target_margin * lev) / price
                    adj_qty, adj_err = self.binance.adjust_qty_to_filters_futures(cw['symbol'], qty_target, price)
                    if adj_err:
                        self.log(f"{cw['symbol']}@{cw.get('interval')} sizing blocked: {adj_err}.")
                        _guard_abort()
                        return
                    if adj_qty <= 0.0:
                        self.log(f"{cw['symbol']}@{cw.get('interval')} sizing blocked: quantity <= 0 after filter adjustment.")
                        _guard_abort()
                        return

                    margin_est = (adj_qty * price) / float(lev)
                    if existing_margin_indicator_total + margin_est > max_indicator_margin + 1e-6:
                        self.log(
                            f"{cw['symbol']}@{cw.get('interval')} capital guard: adding {margin_est:.4f} USDT to {slot_label} "
                            f"would exceed cap {max_indicator_margin:.4f} USDT "
                            f"({pct*100:.2f}% margin target → {per_indicator_notional_target:.4f} USDT notional @ {lev}x)."
                        )
                        _guard_abort()
                        return

                    expected_slots_after = len(active_slot_tokens_all)
                    if slot_token_for_order not in active_slot_tokens_all:
                        expected_slots_after += 1
                    expected_slots_after = max(1, expected_slots_after)
                    expected_slots_after = max(expected_slots_after, desired_slots_after)
                    max_side_margin = per_indicator_margin_target * expected_slots_after * (1.0 + margin_tolerance)
                    projected_total_margin = existing_margin_same_side + margin_est
                    if projected_total_margin > max_side_margin + 1e-6:
                        self.log(
                            f"{cw['symbol']}@{cw.get('interval')} capital guard: projected total {side} margin {projected_total_margin:.4f} USDT "
                            f"exceeds cap {max_side_margin:.4f} USDT for {expected_slots_after} slot(s) at "
                            f"{pct*100:.2f}% margin each."
                        )
                        _guard_abort()
                        return

                    min_required_margin = 0.0
                    try:
                        f_filters = self.binance.get_futures_symbol_filters(cw['symbol']) or {}
                        min_notional_filter = float(f_filters.get('minNotional') or 0.0)
                        if min_notional_filter > 0.0:
                            min_required_margin = max(min_required_margin, min_notional_filter / float(lev))
                        min_qty_filter = float(f_filters.get('minQty') or 0.0)
                        if min_qty_filter > 0.0 and price > 0.0:
                            min_required_margin = max(min_required_margin, (min_qty_filter * price) / float(lev))
                    except Exception:
                        min_required_margin = max(min_required_margin, 0.0)
                    if min_required_margin > 0.0 and min_required_margin > max_indicator_margin + 1e-9:
                        self.log(
                            f"{cw['symbol']}@{cw.get('interval')} sizing blocked: minimum contract margin {min_required_margin:.4f} "
                            f"exceeds cap {max_indicator_margin:.4f} USDT for {slot_label} "
                            f"({pct*100:.2f}% margin target)."
                        )
                        _guard_abort()
                        return

                    qty_est = adj_qty
                    reduce_only = False
                    if bool(self.config.get('add_only', False)):
                        dual = self.binance.get_futures_dual_side()
                        if not dual:
                            try:
                                net_amt = float(self.binance.get_net_futures_position_amt(cw['symbol']))
                            except Exception:
                                net_amt = 0.0
                            if (net_amt > 0 and side == 'SELL'):
                                qty_est = min(qty_est, abs(net_amt)); reduce_only = True
                            elif (net_amt < 0 and side == 'BUY'):
                                qty_est = min(qty_est, abs(net_amt)); reduce_only = True
                            if qty_est <= 0:
                                self.log(f"{cw['symbol']}@{cw['interval']} Opposite open blocked (one-way add-only). net={net_amt}")
                                _guard_abort()
                                return

                    desired_ps = None
                    if self.binance.get_futures_dual_side():
                        desired_ps = 'LONG' if side == 'BUY' else 'SHORT'

                    try:
                        key_bar = (cw['symbol'], cw.get('interval'), side)
                        now_ts = time.time()
                        secs = _interval_to_seconds(str(cw.get('interval') or '1m'))
                        last_ts = self._last_order_time.get(key_bar, 0)
                        if now_ts - last_ts < max(5, secs * 0.9):
                            existing_entries = self._leg_entries(key_bar)
                            if any(tuple(sorted(entry.get("trigger_signature") or [])) == signature for entry in existing_entries):
                                _guard_abort()
                                return
                    except Exception:
                        pass

                    target_flip_qty = flip_qty_override if flip_qty_override > 0.0 else None
                    if not self._close_opposite_position(
                        cw['symbol'],
                        cw.get('interval'),
                        side,
                        signature,
                        indicator_tokens_for_order,
                        target_qty=target_flip_qty,
                    ):
                        _guard_abort()
                        return

                    if callable(self.can_open_cb):
                        if not self.can_open_cb(cw['symbol'], cw.get('interval'), side, context_key):
                            self.log(f"{cw['symbol']}@{cw.get('interval')} Duplicate guard: {side} already open - skipping.")
                            _guard_abort()
                            return
                    # Final sanity check with exchange before opening the new side
                    try:
                        backend_key = str(getattr(self.binance, "_connector_backend", "") or "").lower()
                        guard_duplicates = backend_key == "binance-sdk-derivatives-trading-usds-futures"
                        tol = 1e-8
                        dual_mode = bool(self.binance.get_futures_dual_side())
                        existing_positions = self.binance.list_open_futures_positions(max_age=0.0, force_refresh=True) or []
                        for pos in existing_positions:
                            if str(pos.get('symbol') or '').upper() != cw['symbol'].upper():
                                continue
                            try:
                                amt_existing = float(pos.get('positionAmt') or 0.0)
                            except Exception:
                                amt_existing = 0.0
                            pos_side = str(pos.get('positionSide') or pos.get('positionside') or 'BOTH').upper()
                            if side == 'BUY':
                                if amt_existing < -tol and (not dual_mode or pos_side in {'BOTH', ''}):
                                    self.log(f"{cw['symbol']}@{cw.get('interval')} guard: short still open on exchange; skipping long entry.")
                                    _guard_abort()
                                    return
                                if guard_duplicates:
                                    long_active = False
                                    if dual_mode:
                                        if pos_side == 'LONG':
                                            long_active = abs(amt_existing) > tol
                                        elif pos_side == 'BOTH':
                                            long_active = amt_existing > tol
                                    else:
                                        long_active = amt_existing > tol
                                    if long_active:
                                        entries_dup = self._leg_entries(key_bar)
                                        sig_sorted = signature if signature else ()
                                        if any(tuple(sorted(entry.get("trigger_signature") or [])) == sig_sorted for entry in entries_dup):
                                            self.log(f"{cw['symbol']}@{cw.get('interval')} guard: long already active on exchange; skipping duplicate long entry.")
                                            _guard_abort()
                                            return
                                        long_active = False
                            elif side == 'SELL':
                                if amt_existing > tol and (not dual_mode or pos_side in {'BOTH', ''}):
                                    self.log(f"{cw['symbol']}@{cw.get('interval')} guard: long still open on exchange; skipping short entry.")
                                    _guard_abort()
                                    return
                                if guard_duplicates:
                                    short_active = False
                                    if dual_mode:
                                        if pos_side == 'SHORT':
                                            short_active = abs(amt_existing) > tol
                                        elif pos_side == 'BOTH':
                                            short_active = amt_existing < -tol
                                    else:
                                        short_active = amt_existing < -tol
                                    if short_active:
                                        entries_dup = self._leg_entries(key_dup)
                                        sig_sorted = signature if signature else ()
                                        if any(tuple(sorted(entry.get("trigger_signature") or [])) == sig_sorted for entry in entries_dup):
                                            self.log(f"{cw['symbol']}@{cw.get('interval')} guard: short already active on exchange; skipping duplicate short entry.")
                                            _guard_abort()
                                            return
                                        short_active = False
                    except Exception as ex_chk:
                        self.log(f"{cw['symbol']}@{cw.get('interval')} guard check warning: {ex_chk}")
                        _guard_abort()
                        return
                    order_res = {}
                    guard_side = side
                    order_success = False
                    guard_obj = getattr(self, "guard", None)
                    if guard_obj and hasattr(guard_obj, "begin_open"):
                        try:
                            if not guard_obj.begin_open(cw['symbol'], cw.get('interval'), guard_side, context=context_key):
                                self.log(f"{cw['symbol']}@{cw.get('interval')} guard blocked {guard_side} entry (pending or opposite side active).")
                                _guard_abort()
                                return
                        except Exception:
                            pass
                    try:
                        order_attempts = 0
                        order_success = False
                        price_for_order = last_price if (last_price is not None and last_price > 0.0) else cw.get('price')
                        backoff_base = self._order_rate_retry_backoff
                        rate_limit_tokens = ("too frequent", "-1003", "frequency", "rate limit", "request too many", "too many requests")
                        while True:
                            if self.stopped():
                                order_res = {'ok': False, 'symbol': cw['symbol'], 'error': 'stop_requested'}
                                order_success = False
                                break
                            order_attempts += 1
                            spacing_to_use = self._order_rate_min_spacing
                            if order_batch_total > 1 and current_batch_index > 0 and order_attempts == 1:
                                spacing_to_use = min(
                                    spacing_to_use,
                                    max(0.1, spacing_to_use * 0.35),
                                )
                            try:
                                StrategyEngine._reserve_order_slot(spacing_to_use)
                                if self.stopped():
                                    order_res = {'ok': False, 'symbol': cw['symbol'], 'error': 'stop_requested'}
                                else:
                                    order_res = self.binance.place_futures_market_order(
                                        cw['symbol'],
                                        side,
                                        percent_balance=None,
                                        leverage=lev,
                                        reduce_only=(False if self.binance.get_futures_dual_side() else reduce_only),
                                        position_side=desired_ps,
                                        price=price_for_order,
                                        quantity=qty_est,
                                        strict=True,
                                        timeInForce=self.config.get('tif', 'GTC'),
                                        gtd_minutes=int(self.config.get('gtd_minutes', 30)),
                                        interval=cw.get('interval'),
                                        max_auto_bump_percent=float(self.config.get('max_auto_bump_percent', 5.0)),
                                        auto_bump_percent_multiplier=float(self.config.get('auto_bump_percent_multiplier', 10.0)),
                                    )
                            except Exception as exc_order:
                                order_res = {'ok': False, 'symbol': cw['symbol'], 'error': str(exc_order)}
                            finally:
                                StrategyEngine._release_order_slot()
                            order_success = bool(order_res.get('ok', True))
                            if self.stopped():
                                order_success = False
                                break
                            if order_success:
                                break
                            err_text = str(order_res.get('error') or '').lower()
                            if order_attempts < 3 and any(token in err_text for token in rate_limit_tokens):
                                wait_time = min(5.0, backoff_base * order_attempts)
                                time.sleep(wait_time)
                                continue
                            break
                    finally:
                        if guard_obj and hasattr(guard_obj, "end_open"):
                            try:
                                guard_obj.end_open(cw['symbol'], cw.get('interval'), guard_side, order_success, context=context_key)
                            except Exception:
                                pass
                    if self.stopped():
                        return
                    try:
                        qty_emit = float(order_res.get('computed',{}).get('qty') or 0.0)
                        if qty_emit <= 0:
                            qty_emit = float(order_res.get('info',{}).get('origQty') or 0.0)
                        if self.trade_cb:
                            self.trade_cb({
                                'symbol': cw['symbol'],
                                'interval': cw.get('interval'),
                                'side': side,
                                'qty': qty_emit,
                                'price': cw.get('price'),
                                'time': datetime.now().astimezone().strftime('%Y-%m-%d %H:%M:%S'),
                                'status': 'placed',
                                'ok': bool(order_res.get('ok', True))
                            })
                    except Exception:
                        pass
                    try:
                        try:
                            if (not order_res.get('ok')) and callable(self.trade_cb):
                                self.trade_cb({
                                    'symbol': cw['symbol'],
                                    'interval': cw.get('interval'),
                                    'side': side,
                                    'qty': float(order_res.get('computed',{}).get('qty') or 0.0),
                                    'price': cw.get('price'),
                                    'time': datetime.now().astimezone().strftime("%Y-%m-%d %H:%M:%S"),
                                    'status': 'error',
                                    'ok': False
                                })
                        except Exception:
                            pass
                            if order_res.get('ok'):
                                if current_bar_marker is not None:
                                    tracker = self._bar_order_tracker.setdefault(
                                        bar_sig_key,
                                        {"bar": current_bar_marker, "signatures": set()},
                                    )
                                    if tracker.get("bar") != current_bar_marker:
                                        tracker["bar"] = current_bar_marker
                                        tracker["signatures"] = set()
                                    tracker.setdefault("signatures", set()).add(sig_sorted)
                                    with StrategyEngine._BAR_GUARD_LOCK:
                                        global_tracker = StrategyEngine._BAR_GLOBAL_SIGNATURES.setdefault(
                                            bar_sig_key,
                                            {"bar": current_bar_marker, "signatures": set()},
                                        )
                                        if global_tracker.get("bar") != current_bar_marker:
                                            global_tracker["bar"] = current_bar_marker
                                            global_tracker["signatures"] = set()
                                        global_tracker.setdefault("signatures", set()).add(sig_sorted)
                                success_ts = time.time()
                                if guard_claimed:
                                    with StrategyEngine._SYMBOL_GUARD_LOCK:
                                        entry_guard = StrategyEngine._SYMBOL_ORDER_STATE.get(guard_key_symbol, {})
                                        if isinstance(entry_guard, dict):
                                            signatures_state = entry_guard.get("signatures")
                                            if not isinstance(signatures_state, dict):
                                                signatures_state = {}
                                            signatures_state[signature_guard_key] = success_ts
                                            entry_guard["signatures"] = signatures_state
                                            pending_map = entry_guard.get("pending_map")
                                            if not isinstance(pending_map, dict):
                                                pending_map = {}
                                            pending_map.pop(signature_guard_key, None)
                                            entry_guard["pending_map"] = pending_map
                                            entry_guard["last"] = success_ts
                                            entry_guard["window"] = guard_window
                                            StrategyEngine._SYMBOL_ORDER_STATE[guard_key_symbol] = entry_guard
                                else:
                                    with StrategyEngine._SYMBOL_GUARD_LOCK:
                                        entry_guard = StrategyEngine._SYMBOL_ORDER_STATE.get(guard_key_symbol)
                                        if isinstance(entry_guard, dict):
                                            signatures_state = entry_guard.get("signatures")
                                            if not isinstance(signatures_state, dict):
                                                signatures_state = {}
                                            signatures_state[signature_guard_key] = success_ts
                                            entry_guard["signatures"] = signatures_state
                                            pending_map = entry_guard.get("pending_map")
                                            if not isinstance(pending_map, dict):
                                                pending_map = {}
                                            pending_map.pop(signature_guard_key, None)
                                            entry_guard["pending_map"] = pending_map
                                            entry_guard["last"] = success_ts
                                            entry_guard["window"] = guard_window
                                            StrategyEngine._SYMBOL_ORDER_STATE[guard_key_symbol] = entry_guard
                            else:
                                failure_ts = time.time()
                                with StrategyEngine._SYMBOL_GUARD_LOCK:
                                    entry_guard = StrategyEngine._SYMBOL_ORDER_STATE.get(guard_key_symbol)
                                    if isinstance(entry_guard, dict):
                                        pending_map = entry_guard.get("pending_map")
                                        if not isinstance(pending_map, dict):
                                            pending_map = {}
                                        pending_map.pop(signature_guard_key, None)
                                        entry_guard["pending_map"] = pending_map
                                        entry_guard["last"] = max(float(entry_guard.get("last") or 0.0), failure_ts)
                                        StrategyEngine._SYMBOL_ORDER_STATE[guard_key_symbol] = entry_guard
                                key = (cw['symbol'], cw.get('interval'), side)
                            qty = float(order_res.get('info',{}).get('origQty') or order_res.get('computed',{}).get('qty') or 0)
                            exec_qty = self._order_field(order_res, 'executedQty', 'cumQty', 'cumQuantity')
                            if exec_qty is not None:
                                try:
                                    exec_qty_val = float(exec_qty)
                                except Exception:
                                    exec_qty_val = 0.0
                                if exec_qty_val > 0.0:
                                    qty = exec_qty_val
                            if qty > 0:
                                fills_info = order_res.get('fills') or {}

                                def _float_or(value, default=0.0):
                                    try:
                                        return float(value)
                                    except Exception:
                                        return default

                                entry_price_est = price
                                try:
                                    avg_px = (order_res.get('info', {}) or {}).get('avgPrice')
                                    if avg_px:
                                        entry_price_est = float(avg_px)
                                    else:
                                        computed_px = (order_res.get('computed', {}) or {}).get('px')
                                        if computed_px:
                                            entry_price_est = float(computed_px)
                                except Exception:
                                    entry_price_est = price
                                qty_from_fills = _float_or(fills_info.get('filled_qty'))
                                if qty_from_fills > 0:
                                    qty = qty_from_fills
                                avg_from_fills = _float_or(fills_info.get('avg_price'))
                                if avg_from_fills > 0:
                                    entry_price_est = avg_from_fills

                                try:
                                    leverage_val = int(order_res.get('info', {}).get('leverage') or 0)
                                except Exception:
                                    leverage_val = 0
                                if leverage_val <= 0:
                                    try:
                                        leverage_val = int(order_res.get('computed', {}).get('lev') or 0)
                                    except Exception:
                                        leverage_val = 0
                                if leverage_val <= 0:
                                    try:
                                        leverage_val = int(cw.get('leverage') or 0)
                                    except Exception:
                                        leverage_val = 0
                                if leverage_val <= 0:
                                    try:
                                        leverage_val = int(self.config.get('leverage') or 0)
                                    except Exception:
                                        leverage_val = 0
                                try:
                                    margin_est = (entry_price_est * qty) / leverage_val if leverage_val > 0 else entry_price_est * qty
                                except Exception:
                                    margin_est = 0.0
                                if margin_est <= 0.0:
                                    margin_est = (price * qty) / max(leverage_val, 1)

                                entry_fee_usdt = _float_or(fills_info.get('commission_usdt'))
                                entry_net_realized = _float_or(fills_info.get('net_realized'))

                                signature_list = list(signature or tuple(sorted(trigger_labels)))
                                ledger_id = f"{key[0]}-{key[1]}-{key[2]}-{int(time.time()*1000)}"
                                entry_payload = {
                                    'qty': float(qty),
                                    'timestamp': time.time(),
                                    'entry_price': float(entry_price_est or price),
                                    'leverage': leverage_val,
                                    'margin_usdt': float(margin_est or 0.0),
                                    'ledger_id': ledger_id,
                                    'trigger_signature': signature_list,
                                    'trigger_indicators': list(trigger_labels),
                                    'trigger_desc': trigger_desc,
                                }
                                try:
                                    sig_tokens = StrategyEngine._normalize_signature_tokens_no_slots(signature_list)
                                    if sig_tokens:
                                        entry_payload['indicator_keys'] = list(sig_tokens)
                                except Exception:
                                    pass
                                if entry_fee_usdt:
                                    entry_payload['fees_usdt'] = float(entry_fee_usdt)
                                    entry_payload['entry_fee_usdt'] = float(entry_fee_usdt)
                                if entry_net_realized:
                                    entry_payload['entry_realized_usdt'] = float(entry_net_realized)
                                self._append_leg_entry(key, entry_payload)
                                try:
                                    qty_logged = float(entry_payload.get('qty') or 0.0)
                                    price_logged = float(entry_payload.get('entry_price') or price or 0.0)
                                    size_logged = qty_logged * price_logged if price_logged > 0.0 else 0.0
                                    margin_logged = float(entry_payload.get('margin_usdt') or margin_est or 0.0)
                                    indicator_label = (
                                        trigger_desc.upper()
                                        if isinstance(trigger_desc, str) and trigger_desc.strip()
                                        else "-"
                                    )
                                    self.log(
                                        f"{cw['symbol']}@{cw['interval']} OPEN {side}: qty={qty_logged:.6f}, "
                                        f"size≈{size_logged:.2f} USDT, margin≈{margin_logged:.2f} USDT "
                                        f"(context={indicator_label})."
                                    )
                                except Exception:
                                    pass
                    except Exception:
                        pass
                    qty_display = order_res.get('executedQty') or order_res.get('origQty') or qty_est

                else:
                    filters = self.binance.get_spot_symbol_filters(cw['symbol'])
                    min_notional = float(filters.get('minNotional', 0.0) or 0.0)
                    price = float(last_price or 0.0)
                    if side == 'BUY':
                        total_usdt = float(self.binance.get_spot_balance('USDT') or 0.0)
                        use_usdt = total_usdt * pct
                        if min_notional > 0 and use_usdt < min_notional:
                            if total_usdt >= min_notional:
                                use_usdt = min_notional
                        order_res = self.binance.place_spot_market_order(
                            cw['symbol'], 'BUY', quantity=0.0, price=price, use_quote=True, quote_amount=use_usdt
                        )
                        qty_display = order_res.get('executedQty') or order_res.get('origQty')
                    else:
                        base_asset, _ = self.binance.get_base_quote_assets(cw['symbol'])
                        base_free = float(self.binance.get_spot_balance(base_asset) or 0.0)
                        if base_free <= 0:
                            self.log(f"Skip SELL for {cw['symbol']}: no {base_asset} balance. Spot cannot open shorts with USDT. Switch Account Type to FUTURES to short.")
                            return
                        est_notional = base_free * (price or 0.0) * pct
                        if min_notional > 0 and est_notional < min_notional:
                            self.log(f"Skip SELL for {cw['symbol']}: position value {est_notional:.8f} < minNotional {min_notional:.8f}.")
                            return
                        qty_to_sell = base_free * pct
                        order_res = self.binance.place_spot_market_order(
                            cw['symbol'], 'SELL', quantity=qty_to_sell, price=price, use_quote=False
                        )
                        qty_display = order_res.get('executedQty') or order_res.get('origQty') or qty_to_sell

                try:
                    avg_price = float((order_res.get('info', {}) or {}).get('avgPrice') or 0.0)
                except Exception:
                    avg_price = 0.0
                fills_info = order_res.get('fills') or {}
                if fills_info:
                    try:
                        avg_from_fills = float(fills_info.get('avg_price') or 0.0)
                        if avg_from_fills > 0.0:
                            avg_price = avg_from_fills
                    except Exception:
                        pass
                try:
                    executed_qty = float(
                        (order_res.get('info', {}) or {}).get('executedQty')
                        or (order_res.get('info', {}) or {}).get('origQty')
                        or (order_res.get('computed', {}) or {}).get('qty')
                        or qty_display
                        or 0.0
                    )
                except Exception:
                    try:
                        executed_qty = float(qty_display or 0.0)
                    except Exception:
                        executed_qty = 0.0
                if fills_info:
                    try:
                        fill_qty = float(fills_info.get('filled_qty') or 0.0)
                        if fill_qty > 0.0:
                            executed_qty = fill_qty
                    except Exception:
                        pass
                qty_numeric = executed_qty if executed_qty else float(qty_display or 0.0)
                leverage_used = None
                if 'lev' in locals():
                    try:
                        leverage_used = int(lev)
                    except Exception:
                        leverage_used = lev
                order_info = {
                    "symbol": cw['symbol'],
                    "interval": cw['interval'],
                    "side": side,
                    "qty": qty_numeric,
                    "executed_qty": qty_numeric,
                    "price": price,
                    "avg_price": avg_price if avg_price > 0 else price,
                    "leverage": leverage_used,
                    "trigger_indicators": trigger_labels,
                    "trigger_desc": trigger_desc,
                    "time": datetime.now().astimezone().strftime("%Y-%m-%d %H:%M:%S"),
                    "status": "placed",
                }
                info_meta = order_res.get("info") or {}
                computed_meta = order_res.get("computed") or {}
                order_id_value = None
                client_order_id_value = None
                if isinstance(info_meta, dict):
                    order_id_value = info_meta.get("orderId") or info_meta.get("order_id") or info_meta.get("orderID")
                    client_order_id_value = info_meta.get("clientOrderId") or info_meta.get("client_order_id") or info_meta.get("clientOrderID")
                if isinstance(computed_meta, dict):
                    order_id_value = order_id_value or computed_meta.get("order_id") or computed_meta.get("orderId")
                    client_order_id_value = client_order_id_value or computed_meta.get("client_order_id") or computed_meta.get("clientOrderId")
                if order_id_value is not None:
                    order_info["order_id"] = order_id_value
                if client_order_id_value is not None:
                    order_info["client_order_id"] = client_order_id_value
                if fills_info:
                    commission_val = fills_info.get("commission_usdt")
                    net_realized_val = fills_info.get("net_realized")
                    if commission_val is not None:
                        try:
                            order_info["commission_usdt"] = float(commission_val)
                        except Exception:
                            order_info["commission_usdt"] = commission_val
                    if net_realized_val is not None:
                        try:
                            order_info["net_realized_usdt"] = float(net_realized_val)
                        except Exception:
                            order_info["net_realized_usdt"] = net_realized_val
                    order_info["fills_meta"] = {
                        "order_id": fills_info.get("order_id"),
                        "trade_count": fills_info.get("trade_count"),
                    }
                if self.trade_cb:
                    self.trade_cb(order_info)
                order_ok = True
                if isinstance(order_res, dict):
                    order_ok = bool(order_res.get('ok', True))
                if origin_timestamp is not None and order_ok:
                    latency = max(0.0, time.time() - float(origin_timestamp))
                    self.log(
                        f"{cw['symbol']}@{cw['interval']} signal→order latency: {latency*1000:.0f} ms ({latency:.3f}s)."
                    )
                self.log(f"{cw['symbol']}@{cw['interval']} Order placed: {order_res}")
            except Exception as e:
                self.log(f"{cw['symbol']}@{cw['interval']} Order failed: {e}")
                if guard_claimed:
                    with StrategyEngine._SYMBOL_GUARD_LOCK:
                        entry_guard = StrategyEngine._SYMBOL_ORDER_STATE.get(guard_key_symbol)
                        if isinstance(entry_guard, dict):
                            pending_map = entry_guard.get("pending_map")
                            if not isinstance(pending_map, dict):
                                pending_map = {}
                            pending_map.pop(signature_guard_key, None)
                            entry_guard["pending_map"] = pending_map
                            StrategyEngine._SYMBOL_ORDER_STATE[guard_key_symbol] = entry_guard

        for order in orders_to_execute:
            order_ts = order.get("timestamp")
            ts_float = None
            try:
                if order_ts is not None:
                    ts_float = float(order_ts)
            except Exception:
                ts_float = None
            _execute_signal_order(
                order.get("side"),
                list(order.get("labels") or []),
                tuple(order.get("signature") or ()),
                ts_float,
                order.get("flip_from"),
                order.get("flip_qty"),
                order.get("flip_qty_target"),
            )

    def _trigger_emergency_close(self, sym: str, interval: str, reason: str):
        if self._emergency_close_triggered:
            return
        self._emergency_close_triggered = True
        try:
            self.log(f"{sym}@{interval} connectivity lost ({reason}); scheduling emergency close of all positions.")
        except Exception:
            pass
        try:
            closer = getattr(self.binance, "trigger_emergency_close_all", None)
            if callable(closer):
                closer(reason=f"{sym}@{interval}: {reason}", source="strategy")
            else:
                from .close_all import close_all_futures_positions as _close_all_fut
                def _do_close():
                    try:
                        _close_all_fut(self.binance)
                    except Exception:
                        pass
                threading.Thread(target=_do_close, name=f"EmergencyClose-{sym}@{interval}", daemon=True).start()
        except Exception as exc:
            try:
                self.log(f"{sym}@{interval} emergency close scheduling failed: {exc}")
            except Exception:
                pass
        finally:
            try:
                self.stop()
            except Exception:
                self._stop = True

    def _handle_network_outage(self, sym: str, interval: str, exc: Exception) -> float:
        prev = getattr(self, "_offline_backoff", 0.0) or 0.0
        backoff = 5.0 if prev <= 0.0 else min(90.0, max(prev * 1.5, 5.0))
        self._offline_backoff = backoff
        now = time.time()
        reason_txt = str(exc)
        if reason_txt.startswith("network_offline"):
            parts = reason_txt.split(":", 2)
            if len(parts) >= 2:
                reason_txt = parts[-1] or "network_offline"
        emergency_requested = False
        shared = getattr(self, "binance", None)
        if shared is not None:
            emergency_requested = bool(getattr(shared, "_network_emergency_dispatched", False))
        if (now - getattr(self, "_last_network_log", 0.0)) >= 8.0:
            self._last_network_log = now
            try:
                note = "emergency close queued" if emergency_requested else "monitoring"
                self.log(f"{sym}@{interval} network offline ({reason_txt}); {note}; retrying in {backoff:.0f}s.")
            except Exception:
                pass
        if emergency_requested:
            self._trigger_emergency_close(sym, interval, reason_txt)
        return backoff

    def run_loop(self):
        sym = self.config.get('symbol', '(unknown)')
        interval = self.config.get('interval', '(unknown)')
        self.log(f"Loop start for {sym} @ {interval}.")
        if self.loop_override:
            interval_seconds = max(1, int(self._interval_seconds(self.loop_override)))
        else:
            interval_seconds = max(1, int(self._interval_seconds(self.config['interval'])))
        phase_span = max(2.0, min(interval_seconds * 0.35, 10.0))
        phase = self._phase_seed * phase_span
        if phase > 0:
            waited = 0.0
            while waited < phase and not self.stopped():
                chunk = min(0.5, phase - waited)
                time.sleep(chunk)
                waited += chunk
        while not self.stopped():
            loop_started = time.time()
            got_gate = False
            sleep_override = None
            try:
                if self.stopped():
                    break
                got_gate = StrategyEngine._RUN_GATE.acquire(timeout=0.25)
                if not got_gate:
                    continue
                self.run_once()
                self._offline_backoff = 0.0
                self._last_network_log = 0.0
            except NetworkConnectivityError as e:
                sleep_override = self._handle_network_outage(sym, interval, e)
            except Exception as e:
                self.log(f"Error in {sym}@{interval} loop: {repr(e)}")
                try:
                    self.log(traceback.format_exc())
                except Exception:
                    pass
            finally:
                if got_gate:
                    try:
                        StrategyEngine._RUN_GATE.release()
                    except Exception:
                        pass
            loop_elapsed = max(0.0, time.time() - loop_started)
            if sleep_override is None:
                sleep_remaining = max(0.0, interval_seconds - loop_elapsed)
                if interval_seconds > 1 and sleep_remaining > 0.0:
                    jitter = self._phase_seed * min(0.75, max(0.1, interval_seconds * 0.05))
                    sleep_remaining = max(0.0, sleep_remaining + jitter)
            else:
                sleep_remaining = float(max(0.0, sleep_override))
            while sleep_remaining > 0 and not self.stopped():
                chunk = min(0.5, sleep_remaining)
                time.sleep(chunk)
                sleep_remaining -= chunk
        self.log(f"Loop stopped for {sym} @ {interval}.")

    def set_guard(self, guard):
        """Attach/replace risk guard (hedge gate)."""
        self.guard = guard
        return self

    def start(self):
        """Start the strategy loop in a daemon thread."""
        t = threading.Thread(
            target=self.run_loop,
            name=f"StrategyLoop-{self.config.get('symbol','?')}@{self.config.get('interval','?')} ",
            daemon=True,
        )
        t.start()
        self._thread = t
        return t
