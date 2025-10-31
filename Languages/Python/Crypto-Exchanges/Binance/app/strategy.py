
import time, copy, traceback, math, threading, os
from datetime import datetime, timezone

import pandas as pd
from .config import STOP_LOSS_MODE_ORDER, STOP_LOSS_SCOPE_OPTIONS, normalize_stop_loss_dict
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


class StrategyEngine:
    _RUN_GATE = threading.BoundedSemaphore(_MAX_PARALLEL_RUNS)
    _MAX_ACTIVE = _MAX_PARALLEL_RUNS
    _ORDER_THROTTLE_LOCK = threading.Lock()
    _ORDER_LAST_TS = 0.0
    _ORDER_MIN_SPACING = 0.35  # seconds between order submissions by default
    _BAR_GUARD_LOCK = threading.Lock()
    _BAR_GLOBAL_SIGNATURES: dict[tuple[str, str, str], dict[str, object]] = {}

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
        self.config["stop_loss"] = normalize_stop_loss_dict(self.config.get("stop_loss"))
        self.binance = binance_wrapper
        self.log = log_callback
        self.trade_cb = trade_callback
        self.loop_override = loop_interval_override
        self._leg_ledger = {}
        self._last_order_time = {}  # (symbol, interval, side)->{'qty': float, 'timestamp': float}
        self._last_bar_key = set()  # prevent multi entries within same bar per (symbol, interval, side)
        self._bar_order_tracker: dict[tuple[str, str, str], dict[str, object]] = {}
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

    def _update_leg_snapshot(self, leg_key, leg: dict | None) -> None:
        if not isinstance(leg, dict):
            self._leg_ledger.pop(leg_key, None)
            return
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

    def _remove_leg_entry(self, leg_key, ledger_id: str | None = None) -> None:
        if ledger_id is None:
            self._leg_ledger.pop(leg_key, None)
            self._last_order_time.pop(leg_key, None)
            return
        leg = self._leg_ledger.get(leg_key)
        if not isinstance(leg, dict):
            return
        entries = [entry for entry in self._leg_entries(leg_key) if entry.get("ledger_id") != ledger_id]
        if not entries:
            self._leg_ledger.pop(leg_key, None)
            self._last_order_time.pop(leg_key, None)
            return
        leg["entries"] = entries
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
    ) -> bool:
        symbol, interval, _ = leg_key
        qty = max(0.0, float(entry.get("qty") or 0.0))
        if qty <= 0.0:
            return False
        start_ts = time.time()
        try:
            res = self.binance.close_futures_leg_exact(
                symbol,
                qty,
                side=close_side,
                position_side=position_side,
            )
        except Exception as exc:
            try:
                self.log(f"Per-trade stop-loss close error for {symbol}@{interval} ({side_label}): {exc}")
            except Exception:
                pass
            return False
        if not (isinstance(res, dict) and res.get("ok")):
            try:
                self.log(f"Per-trade stop-loss close failed for {symbol}@{interval} ({side_label}): {res}")
            except Exception:
                pass
            return False
        latency_s = max(0.0, time.time() - start_ts)
        payload = self._build_close_event_payload(
            symbol,
            interval,
            side_label,
            qty,
            res,
            leg_info_override=entry,
        )
        self._remove_leg_entry(leg_key, entry.get("ledger_id"))
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
                f"(loss {loss_usdt:.4f} USDT / {pct_display:.2f}%)."
            )
        except Exception:
            pass
        return True

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
    ) -> bool:
        """Ensure no net exposure in the opposite direction before opening a new leg."""
        try:
            positions = self.binance.list_open_futures_positions(max_age=0.0, force_refresh=True) or []
        except Exception as e:
            self.log(f"{symbol}@{interval} read positions failed: {e}")
            return False
        desired = (next_side or '').upper()
        if desired not in ('BUY', 'SELL'):
            return True
        try:
            dual = bool(self.binance.get_futures_dual_side())
        except Exception:
            dual = False
        opp = 'SELL' if desired == 'BUY' else 'BUY'
        opp_key = (symbol, interval, opp)

        if dual:
            entries_all = self._leg_entries(opp_key)
            if trigger_signature:
                sig_sorted = tuple(sorted(trigger_signature))
                entries = [
                    entry
                    for entry in entries_all
                    if tuple(sorted(entry.get("trigger_signature") or [])) == sig_sorted
                ]
            else:
                entries = list(entries_all)
            if not entries:
                entry = self._leg_ledger.get(opp_key) if hasattr(self, '_leg_ledger') else None
                if isinstance(entry, dict) and entry.get("qty", 0.0):
                    entries = [entry]
            if not entries:
                return True
            pos_side = 'SHORT' if opp == 'SELL' else 'LONG'
            for entry in list(entries):
                qty_to_close = max(0.0, float(entry.get('qty') or 0.0))
                if qty_to_close <= 0.0:
                    self._remove_leg_entry(opp_key, entry.get("ledger_id"))
                    continue
                reduce_only_missing = False
                res = None
                try:
                    res = self.binance.close_futures_leg_exact(symbol, qty_to_close, side=desired, position_side=pos_side)
                except Exception as exc:
                    msg = str(exc)
                    if "-2022" in msg or "ReduceOnly" in msg or "reduceonly" in msg.lower():
                        reduce_only_missing = True
                    else:
                        self.log(f"{symbol}@{interval} close-opposite exception: {exc}")
                        return False
                if isinstance(res, dict) and not res.get('ok', True):
                    err_msg = str(res.get('error') or "")
                    if "-2022" in err_msg or "reduceonly" in err_msg.lower():
                        reduce_only_missing = True
                    else:
                        self.log(f"{symbol}@{interval} close-opposite failed: {res}")
                        return False
                if reduce_only_missing:
                    try:
                        self.binance.close_futures_position(symbol)
                    except Exception as exc:
                        self.log(f"{symbol}@{interval} close-opposite reduceOnly fallback failed: {exc}")
                        return False
                else:
                    payload = self._build_close_event_payload(symbol, interval, opp, qty_to_close, res, leg_info_override=entry)
                    self._notify_interval_closed(symbol, interval, opp, **payload)
                try:
                    if hasattr(self.guard, "mark_closed"):
                        self.guard.mark_closed(symbol, interval, opp)
                except Exception:
                    pass
                self._remove_leg_entry(opp_key, entry.get("ledger_id"))
            return True

        closed_any = False
        for p in positions:
            try:
                if str(p.get('symbol') or '').upper() != symbol:
                    continue
                amt = float(p.get('positionAmt') or 0.0)
                if desired == 'BUY' and amt < 0:
                    qty = abs(amt)
                    res = self.binance.close_futures_leg_exact(symbol, qty, side='BUY', position_side=None)
                    if not (isinstance(res, dict) and res.get('ok')):
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
                elif desired == 'SELL' and amt > 0:
                    qty = abs(amt)
                    res = self.binance.close_futures_leg_exact(symbol, qty, side='SELL', position_side=None)
                    if not (isinstance(res, dict) and res.get('ok')):
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
                    self._leg_ledger.pop(key, None)
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
                r = float(ind['rsi'].iloc[-2])
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
                srsi_series = ind['stoch_rsi_k'].dropna()
                if not srsi_series.empty:
                    srsi_val = float(srsi_series.iloc[-2])
                    trigger_desc.append(f"StochRSI %K={srsi_val:.2f}")
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
        if willr_enabled and 'willr' in ind and not ind['willr'].dropna().empty:
            try:
                wr = float(ind['willr'].iloc[-2])
                if math.isfinite(wr):
                    trigger_desc.append(f"Williams %R={wr:.2f}")
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
                    if buy_allowed and buy_lower <= wr <= buy_upper:
                        trigger_actions["willr"] = "buy"
                        trigger_desc.append(f"Williams %R in [{buy_lower:.2f}, {buy_upper:.2f}] -> BUY")
                        trigger_sources.append("willr")
                        if signal is None:
                            signal = 'BUY'
                    elif sell_allowed and sell_lower <= wr <= sell_upper:
                        trigger_actions["willr"] = "sell"
                        trigger_desc.append(f"Williams %R in [{sell_lower:.2f}, {sell_upper:.2f}] -> SELL")
                        trigger_sources.append("willr")
                        if signal is None:
                            signal = 'SELL'
                else:
                    trigger_desc.append("Williams %R=NaN/inf skipped")
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
            last_rsi = float(rsi_series.iloc[-2]) if rsi_series is not None and len(rsi_series.dropna()) else None
        except Exception:
            last_rsi = None

        # Open-state via internal ledger (per symbol, interval, side)
        key_short = (cw['symbol'], cw.get('interval'), 'SELL')
        key_long  = (cw['symbol'], cw.get('interval'), 'BUY')
        short_open = bool(self._leg_ledger.get(key_short, {}).get('qty', 0) > 0)
        long_open  = bool(self._leg_ledger.get(key_long,  {}).get('qty', 0) > 0)

        # Exit thresholds
        try:
            rsi_cfg = cw.get('indicators',{}).get('rsi',{})
            exit_up = float(rsi_cfg.get('sell_value', 70))
            exit_dn = float(rsi_cfg.get('buy_value', 30))
        except Exception:
            exit_up, exit_dn = 70.0, 30.0

        if last_rsi is not None:
            # Close LONG when RSI >= sell threshold (e.g., 70)
            if long_open and last_rsi >= exit_up:
                try:
                    leg = self._leg_ledger.get(key_long)
                    qty = float(leg.get('qty', 0)) if leg else 0.0
                    if qty > 0:
                        desired_ps = ('LONG' if self.binance.get_futures_dual_side() else None)
                        res = self.binance.close_futures_leg_exact(cw['symbol'], qty, side='SELL', position_side=desired_ps)
                        if isinstance(res, dict) and res.get('ok'):
                            payload = self._build_close_event_payload(cw['symbol'], cw.get('interval'), 'BUY', qty, res)
                            self._leg_ledger.pop(key_long, None)
                            try:
                                if hasattr(self.guard, 'mark_closed'): self.guard.mark_closed(cw['symbol'], cw.get('interval'), 'BUY')
                            except Exception:
                                pass
                            self._notify_interval_closed(cw['symbol'], cw.get('interval'), 'BUY', **payload)
                            self.log(f"Closed LONG for {cw['symbol']}@{cw.get('interval')} (RSI >= {exit_up}).")
                except Exception:
                    pass
            # Close SHORT when RSI <= buy threshold (e.g., 30)
            if short_open and last_rsi <= exit_dn:
                try:
                    leg = self._leg_ledger.get(key_short)
                    qty = float(leg.get('qty', 0)) if leg else 0.0
                    if qty > 0:
                        desired_ps = ('SHORT' if self.binance.get_futures_dual_side() else None)
                        res = self.binance.close_futures_leg_exact(cw['symbol'], qty, side='BUY', position_side=desired_ps)
                        if isinstance(res, dict) and res.get('ok'):
                            payload = self._build_close_event_payload(cw['symbol'], cw.get('interval'), 'SELL', qty, res)
                            self._leg_ledger.pop(key_short, None)
                            try:
                                if hasattr(self.guard, 'mark_closed'): self.guard.mark_closed(cw['symbol'], cw.get('interval'), 'SELL')
                            except Exception:
                                pass
                            self._notify_interval_closed(cw['symbol'], cw.get('interval'), 'SELL', **payload)
                            self.log(f"Closed SHORT for {cw['symbol']}@{cw.get('interval')} (RSI <= {exit_dn}).")
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

        dual_side = False
        if account_type == "FUTURES":
            try:
                dual_side = bool(self.binance.get_futures_dual_side())
            except Exception:
                dual_side = False
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
                                self._leg_ledger.pop(leg_key, None)
                                self._last_order_time.pop(leg_key, None)
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
                                self._leg_ledger.pop(key_long, None)
                                self._last_order_time.pop(key_long, None)
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
                                self._leg_ledger.pop(key_short, None)
                                self._last_order_time.pop(key_short, None)
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

        indicator_orders_map: dict[str, set[str]] = {}
        if trigger_actions:
            desired_ps_long = "LONG" if dual_side else None
            desired_ps_short = "SHORT" if dual_side else None
            for indicator_name, indicator_action in trigger_actions.items():
                indicator_label = str(indicator_name or "").strip()
                if not indicator_label:
                    continue
                action_norm = str(indicator_action or "").strip().lower()
                long_entries = [
                    entry
                    for entry in self._leg_entries(key_long)
                    if indicator_label.lower() in [
                        str(t).strip().lower()
                        for t in (entry.get("trigger_indicators") or [])
                    ]
                ]
                short_entries = [
                    entry
                    for entry in self._leg_entries(key_short)
                    if indicator_label.lower() in [
                        str(t).strip().lower()
                        for t in (entry.get("trigger_indicators") or [])
                    ]
                ]
                if action_norm == "buy":
                    for entry in list(short_entries):
                        self._close_leg_entry(
                            cw,
                            key_short,
                            entry,
                            "SELL",
                            "BUY",
                            desired_ps_short,
                            loss_usdt=0.0,
                            price_pct=0.0,
                            margin_pct=0.0,
                        )
                    long_entries = [
                        entry
                        for entry in self._leg_entries(key_long)
                        if indicator_label.lower()
                        in [
                            str(t).strip().lower()
                            for t in (entry.get("trigger_indicators") or [])
                        ]
                    ]
                    if not long_entries:
                        indicator_orders_map.setdefault("BUY", set()).add(indicator_label)
                elif action_norm == "sell":
                    for entry in list(long_entries):
                        self._close_leg_entry(
                            cw,
                            key_long,
                            entry,
                            "BUY",
                            "SELL",
                            desired_ps_long,
                            loss_usdt=0.0,
                            price_pct=0.0,
                            margin_pct=0.0,
                        )
                    short_entries = [
                        entry
                        for entry in self._leg_entries(key_short)
                        if indicator_label.lower()
                        in [
                            str(t).strip().lower()
                            for t in (entry.get("trigger_indicators") or [])
                        ]
                    ]
                    if not short_entries:
                        indicator_orders_map.setdefault("SELL", set()).add(indicator_label)

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
        indicator_orders: list[tuple[str, list[str]]] = []
        if indicator_orders_map:
            for side_value, label_set in indicator_orders_map.items():
                ordered_labels = sorted({lbl for lbl in label_set if str(lbl or "").strip()})
                indicator_orders.append((side_value, ordered_labels))
        if indicator_orders:
            order_ts = signal_timestamp or time.time()
            for side_value, labels in indicator_orders:
                label_list = [
                    str(lbl).strip()
                    for lbl in (labels or [])
                    if str(lbl or "").strip()
                ]
                signature = tuple(sorted(label_list)) if label_list else base_signature
                orders_to_execute.append(
                    {
                        "side": str(side_value or "").upper(),
                        "labels": label_list,
                        "signature": signature,
                        "timestamp": order_ts,
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
        for order in orders_to_execute:
            side_upper = str(order.get("side") or "").upper()
            if side_upper not in ("BUY", "SELL"):
                continue
            key_dup = (cw['symbol'], cw.get('interval'), side_upper)
            leg_dup = self._leg_ledger.get(key_dup)
            signature = tuple(order.get("signature") or ())
            allow_order = True
            if leg_dup:
                entries_dup = self._leg_entries(key_dup)
                duplicate_active = False
                active_signatures: set[tuple[str, ...]] = set()
                if entries_dup:
                    for entry in entries_dup:
                        entry_sig = tuple(sorted(entry.get("trigger_signature") or []))
                        entry_qty = max(0.0, float(entry.get("qty") or 0.0))
                        if entry_qty > 0.0:
                            active_signatures.add(entry_sig)
                        if entry_qty > 0.0 and (not signature or entry_sig == signature):
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
                                    self._leg_ledger.pop(key_dup, None)
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
                        "signature": signature,
                        "timestamp": order.get("timestamp"),
                    }
                )
        
        orders_to_execute = filtered_orders
        if not cw.get('trade_on_signal', True):
            orders_to_execute = []

        def _execute_signal_order(order_side: str, indicator_labels: list[str], order_signature: tuple[str, ...], origin_timestamp: float | None) -> None:
            nonlocal positions_cache
            side = str(order_side or "").upper()
            if side not in ("BUY", "SELL"):
                return
            trigger_labels = list(dict.fromkeys(indicator_labels or base_trigger_labels))
            if not trigger_labels:
                trigger_labels = [side.lower()]
            signature = tuple(order_signature or tuple(sorted(trigger_labels)))
            interval_key = str(cw.get("interval") or "").strip() or "default"
            context_key = f"{interval_key}:{side}:{'|'.join(signature) if signature else side}"
            bar_sig_key = (cw["symbol"], interval_key, side)
            sig_sorted = tuple(sorted(signature)) if signature else (side.lower(),)
            if current_bar_marker is not None:
                with StrategyEngine._BAR_GUARD_LOCK:
                    global_tracker = StrategyEngine._BAR_GLOBAL_SIGNATURES.get(bar_sig_key)
                    if not global_tracker or global_tracker.get("bar") != current_bar_marker:
                        global_tracker = {"bar": current_bar_marker, "signatures": set()}
                        StrategyEngine._BAR_GLOBAL_SIGNATURES[bar_sig_key] = global_tracker
                    global_sig_set = global_tracker.setdefault("signatures", set())
                    if "__ANY__" in global_sig_set or sig_sorted in global_sig_set:
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
                if "__ANY__" in sig_set or sig_sorted in sig_set:
                    try:
                        self.log(
                            f"{cw['symbol']}@{interval_key} duplicate {side} suppressed (order already placed this bar)."
                        )
                    except Exception:
                        pass
                    return
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
                        return
                    try:
                        available_total = float(self.binance.get_futures_balance_usdt())
                    except Exception:
                        available_total = 0.0
                    wallet_total = available_total
                    if wallet_total <= 0.0:
                        wallet_total = free_usdt
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
                    equity_estimate = 0.0
                    if (available_total or 0.0) > 0.0 or ledger_margin_total > 0.0:
                        equity_estimate = max(0.0, float(available_total or 0.0)) + ledger_margin_total
                    if equity_estimate > 0.0:
                        wallet_total = equity_estimate
                    equity_cap = max(0.0, float(free_usdt or 0.0)) + ledger_margin_total
                    if equity_cap > 0.0:
                        wallet_total = min(wallet_total, equity_cap)
                    if wallet_total <= 0.0:
                        wallet_total = max(float(equity_estimate or 0.0), float(free_usdt or 0.0))
                    if wallet_total <= 0.0:
                        try:
                            wallet_total = float(self.binance.get_total_wallet_balance())
                        except Exception:
                            wallet_total = 0.0
                    target_margin = wallet_total * pct
                    if target_margin <= 0.0:
                        self.log(f"{cw['symbol']}@{cw.get('interval')} capital guard: zero target margin for {pct*100:.2f}% allocation.")
                        return
                    if available_total <= 0.0:
                        available_total = free_usdt
                    if available_total <= 0.0:
                        self.log(f"{cw['symbol']}@{cw.get('interval')} capital guard: no available USDT to allocate.")
                        return
                    if available_total < target_margin * 0.95:
                        self.log(
                            f"{cw['symbol']}@{cw.get('interval')} capital guard: requested {target_margin:.2f} USDT "
                            f"({pct*100:.2f}%) but only {available_total:.2f} USDT available."
                        )
                        return
                    lev = max(1, int(cw.get('leverage', 1)))
                    qty_target = (target_margin * lev) / price
                    adj_qty, adj_err = self.binance.adjust_qty_to_filters_futures(cw['symbol'], qty_target, price)
                    if adj_err:
                        self.log(f"{cw['symbol']}@{cw.get('interval')} sizing blocked: {adj_err}.")
                        return
                    if adj_qty <= 0.0:
                        self.log(f"{cw['symbol']}@{cw.get('interval')} sizing blocked: quantity <= 0 after filter adjustment.")
                        return
                    margin_est = (adj_qty * price) / max(lev, 1)
                    margin_tolerance = float(self.config.get("margin_over_target_tolerance", 0.05))
                    if margin_tolerance > 1.0:
                        margin_tolerance = margin_tolerance / 100.0
                    max_margin = target_margin * (1.0 + max(0.0, margin_tolerance))
                    if margin_est > max_margin + 1e-9:
                        self.log(
                            f"{cw['symbol']}@{cw.get('interval')} sizing blocked: adjusted margin {margin_est:.4f} "
                            f"exceeds target {target_margin:.4f} by more than {margin_tolerance*100:.2f}%."
                        )
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
                                return
                    except Exception:
                        pass

                    if not self._close_opposite_position(cw['symbol'], cw.get('interval'), side, signature):
                        return

                    if callable(self.can_open_cb):
                        if not self.can_open_cb(cw['symbol'], cw.get('interval'), side, context_key):
                            self.log(f"{cw['symbol']}@{cw.get('interval')} Duplicate guard: {side} already open - skipping.")
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
                                if amt_existing < -tol:
                                    self.log(f"{cw['symbol']}@{cw.get('interval')} guard: short still open on exchange; skipping long entry.")
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
                                            return
                                        long_active = False
                            elif side == 'SELL':
                                if amt_existing > tol:
                                    self.log(f"{cw['symbol']}@{cw.get('interval')} guard: long still open on exchange; skipping short entry.")
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
                                            return
                                        short_active = False
                    except Exception as ex_chk:
                        self.log(f"{cw['symbol']}@{cw.get('interval')} guard check warning: {ex_chk}")
                        return
                    order_res = {}
                    guard_side = side
                    order_success = False
                    guard_obj = getattr(self, "guard", None)
                    if guard_obj and hasattr(guard_obj, "begin_open"):
                        try:
                            if not guard_obj.begin_open(cw['symbol'], cw.get('interval'), guard_side, context=context_key):
                                self.log(f"{cw['symbol']}@{cw.get('interval')} guard blocked {guard_side} entry (pending or opposite side active).")
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
                            order_attempts += 1
                            StrategyEngine._reserve_order_slot(self._order_rate_min_spacing)
                            try:
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
                                    tracker.setdefault("signatures", set()).update({sig_sorted, "__ANY__"})
                                    with StrategyEngine._BAR_GUARD_LOCK:
                                        global_tracker = StrategyEngine._BAR_GLOBAL_SIGNATURES.setdefault(
                                            bar_sig_key,
                                            {"bar": current_bar_marker, "signatures": set()},
                                        )
                                        if global_tracker.get("bar") != current_bar_marker:
                                            global_tracker["bar"] = current_bar_marker
                                            global_tracker["signatures"] = set()
                                        global_tracker.setdefault("signatures", set()).update({sig_sorted, "__ANY__"})
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
                                if entry_fee_usdt:
                                    entry_payload['fees_usdt'] = float(entry_fee_usdt)
                                    entry_payload['entry_fee_usdt'] = float(entry_fee_usdt)
                                if entry_net_realized:
                                    entry_payload['entry_realized_usdt'] = float(entry_net_realized)
                                self._append_leg_entry(key, entry_payload)
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
