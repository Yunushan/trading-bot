from __future__ import annotations

from datetime import datetime
import threading
import time
import traceback

try:
    from ...integrations.exchanges.binance import NetworkConnectivityError
    from ...config import (
        STOP_LOSS_MODE_ORDER,
        STOP_LOSS_SCOPE_OPTIONS,
        coerce_bool,
        normalize_stop_loss_dict,
    )
except ImportError:  # pragma: no cover - standalone execution fallback
    from binance_wrapper import NetworkConnectivityError
    from config import (
        STOP_LOSS_MODE_ORDER,
        STOP_LOSS_SCOPE_OPTIONS,
        coerce_bool,
        normalize_stop_loss_dict,
    )


def stop(self):
    self._stop = True
    try:
        self._stop_time = float(time.time())
    except Exception:
        self._stop_time = 0.0


def stopped(self):
    cls = type(self)
    try:
        if cls._GLOBAL_SHUTDOWN.is_set():
            return True
    except Exception:
        pass
    try:
        if cls._GLOBAL_PAUSE.is_set():
            return True
    except Exception:
        pass
    return self._stop


def request_shutdown(cls) -> None:
    try:
        cls._GLOBAL_SHUTDOWN.set()
    except Exception:
        pass


def pause_trading(cls) -> None:
    try:
        cls._GLOBAL_PAUSE.set()
    except Exception:
        pass


def resume_trading(cls) -> None:
    try:
        if not cls._GLOBAL_SHUTDOWN.is_set():
            cls._GLOBAL_PAUSE.clear()
    except Exception:
        pass


def stop_blocking(self, timeout: float | None = 3.0):
    """Signal stop and wait briefly for the thread to exit without hanging the UI."""
    try:
        self.stop()
    except Exception:
        pass
    thread = getattr(self, "_thread", None)
    if thread is not None:
        try:
            thread.join(timeout=timeout if timeout is not None else 0.0)
        except Exception:
            pass


def is_alive(self):
    try:
        thread = getattr(self, "_thread", None)
        return bool(thread) and bool(getattr(thread, "is_alive", lambda: False)())
    except Exception:
        return False


def join(self, timeout=None):
    try:
        thread = getattr(self, "_thread", None)
        if thread and thread.is_alive():
            thread.join(timeout)
    except Exception:
        pass


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
            try:
                from ...close_all import close_all_futures_positions as close_all_futures_positions
            except ImportError:  # pragma: no cover - standalone execution fallback
                from close_all import close_all_futures_positions as close_all_futures_positions

            def _do_close():
                try:
                    close_all_futures_positions(self.binance)
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


def _build_cycle_context(self) -> dict[str, object] | None:
    cw = self.config
    if self.stopped():
        return None
    now_ts = time.time()
    allow_opposite_enabled = coerce_bool(self.config.get("allow_opposite_positions"), True)
    if allow_opposite_enabled and coerce_bool(self.config.get("hedge_preserve_opposites"), False):
        allow_opposite_enabled = False  # keep both sides; do not auto-close opposite legs in hedge stacking
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
    return {
        "cw": cw,
        "now_ts": now_ts,
        "allow_opposite_enabled": allow_opposite_enabled,
        "hedge_overlap_allowed": bool(allow_opposite_enabled),
        "stop_cfg": stop_cfg,
        "stop_mode": stop_mode,
        "stop_usdt_limit": stop_usdt_limit,
        "stop_percent_limit": stop_percent_limit,
        "scope": scope,
        "stop_enabled": stop_enabled,
        "apply_usdt_limit": apply_usdt_limit,
        "apply_percent_limit": apply_percent_limit,
        "account_type": account_type,
        "is_cumulative": is_cumulative,
        "is_entire_account": is_entire_account,
    }


def _fetch_cycle_market_state(self, *, ctx: dict[str, object]) -> dict[str, object] | None:
    cw = ctx.get("cw") if isinstance(ctx, dict) else self.config
    if not isinstance(cw, dict):
        cw = self.config

    try:
        self._reconcile_liquidations(cw["symbol"])
    except Exception:
        pass
    if self.stopped():
        return None

    df = self.binance.get_klines(cw["symbol"], cw["interval"], limit=cw.get("lookback", 200))
    if self.stopped():
        return None

    ind = self.compute_indicators(df)
    if self.stopped():
        return None

    signal, trigger_desc, trigger_price, trigger_sources, trigger_actions = self.generate_signal(df, ind)
    signal_timestamp = time.time() if signal else None
    try:
        current_bar_marker = int(df.index[-1].value) if not df.empty else None
    except Exception:
        current_bar_marker = None

    try:
        rsi_series = ind.get("rsi") or ind.get("RSI") or None
        if rsi_series is not None:
            _, _, last_rsi = self._indicator_prev_live_signal_values(rsi_series)
        else:
            last_rsi = None
    except Exception:
        last_rsi = None

    trigger_segments = [
        segment.strip()
        for segment in str(trigger_desc or "").split("|")
        if str(segment).strip()
    ]

    return {
        "df": df,
        "ind": ind,
        "signal": signal,
        "signal_timestamp": signal_timestamp,
        "trigger_desc": trigger_desc,
        "trigger_price": trigger_price,
        "trigger_sources": trigger_sources,
        "trigger_actions": trigger_actions,
        "trigger_segments": trigger_segments,
        "current_bar_marker": current_bar_marker,
        "last_rsi": last_rsi,
        "last_price": None,
    }


def _log_cycle_signal_summary(self, *, ctx: dict[str, object], market_state: dict[str, object]) -> None:
    cw = ctx.get("cw") if isinstance(ctx, dict) else self.config
    if not isinstance(cw, dict):
        cw = self.config
    ind = market_state.get("ind") if isinstance(market_state, dict) else {}
    if not isinstance(ind, dict):
        ind = {}
    last_price = market_state.get("last_price")
    signal = market_state.get("signal")
    trigger_price = market_state.get("trigger_price")
    trigger_desc = str(market_state.get("trigger_desc") or "")

    thresholds = []
    try:
        if cw["indicators"]["ma"]["enabled"] and "ma" in ind and not ind["ma"].isnull().all():
            thresholds.append(f"MA={float(ind['ma'].iloc[-1]):.8f}")
    except Exception:
        pass

    ts = datetime.now().astimezone().strftime("%Y-%m-%d %H:%M:%S")
    parts = [
        f"{ts}",
        f"{cw['symbol']}@{cw['interval']}",
        f"Price={last_price:.8f}" if last_price is not None else "Price=None",
        f"Signal={signal if signal else 'None'}",
    ]
    if trigger_price is not None:
        parts.append(f"TriggerPrice={trigger_price:.8f}")
    if thresholds:
        parts.append("Thresholds:" + ",".join(thresholds))
    parts.append("Details:" + trigger_desc)
    self.log(" | ".join(parts))


def run_loop(self):
    cls = type(self)
    sym = self.config.get("symbol", "(unknown)")
    interval = self.config.get("interval", "(unknown)")
    self.log(f"Loop start for {sym} @ {interval}.")
    if self.loop_override:
        interval_seconds = max(1, int(self._interval_seconds(self.loop_override)))
    else:
        interval_seconds = max(1, int(self._interval_seconds(self.config["interval"])))
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
            got_gate = cls._RUN_GATE.acquire(timeout=0.25)
            if not got_gate:
                continue
            self.run_once()
            self._offline_backoff = 0.0
            self._last_network_log = 0.0
        except NetworkConnectivityError as exc:
            sleep_override = self._handle_network_outage(sym, interval, exc)
        except Exception as exc:
            self.log(f"Error in {sym}@{interval} loop: {repr(exc)}")
            try:
                self.log(traceback.format_exc())
            except Exception:
                pass
        finally:
            if got_gate:
                try:
                    cls._RUN_GATE.release()
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
    """Attach or replace the risk guard."""
    self.guard = guard
    return self


def start(self):
    """Start the strategy loop in a daemon thread."""
    thread = threading.Thread(
        target=self.run_loop,
        name=f"StrategyLoop-{self.config.get('symbol', '?')}@{self.config.get('interval', '?')} ",
        daemon=True,
    )
    thread.start()
    self._thread = thread
    return thread


def bind_strategy_runtime(strategy_cls) -> None:
    strategy_cls.stop = stop
    strategy_cls.stopped = stopped
    strategy_cls.request_shutdown = classmethod(request_shutdown)
    strategy_cls.pause_trading = classmethod(pause_trading)
    strategy_cls.resume_trading = classmethod(resume_trading)
    strategy_cls.stop_blocking = stop_blocking
    strategy_cls.is_alive = is_alive
    strategy_cls.join = join
    strategy_cls._trigger_emergency_close = _trigger_emergency_close
    strategy_cls._handle_network_outage = _handle_network_outage
    strategy_cls._build_cycle_context = _build_cycle_context
    strategy_cls._fetch_cycle_market_state = _fetch_cycle_market_state
    strategy_cls._log_cycle_signal_summary = _log_cycle_signal_summary
    strategy_cls.run_loop = run_loop
    strategy_cls.set_guard = set_guard
    strategy_cls.start = start
