from __future__ import annotations

import math
import time
from collections import deque

import pandas as pd
from PyQt6 import QtCore

from app.binance_wrapper import BinanceWrapper
from app.indicators import (
    ema as ema_indicator,
    rsi as rsi_indicator,
    sma as sma_indicator,
    stoch_rsi as stoch_rsi_indicator,
    williams_r as williams_r_indicator,
)
from app.workers import CallWorker


def sanitize_interval_hint(interval_hint: str | None) -> str:
    if not interval_hint:
        return ""
    try:
        primary = str(interval_hint).split(",")[0].strip()
    except Exception:
        primary = str(interval_hint or "").strip()
    return primary


def calc_indicator_value_from_df(df, indicator_key: str, indicator_cfg: dict, *, use_live_values: bool = True) -> float | None:
    if df is None or df.empty:
        return None
    key = str(indicator_key or "").strip().lower()
    if not key:
        return None
    try:
        close = pd.to_numeric(df["close"], errors="coerce")
    except Exception:
        return None
    close = close.dropna()
    if close.empty:
        return None
    cfg = indicator_cfg or {}

    def _pick(series) -> float | None:
        try:
            s = series.dropna()
        except Exception:
            s = series
        if s is None or len(s) == 0:
            return None
        if use_live_values:
            return float(s.iloc[-1])
        return float(s.iloc[-2]) if len(s) >= 2 else float(s.iloc[-1])

    try:
        if key == "rsi":
            length = int(cfg.get("length") or cfg.get("period") or 14)
            series = rsi_indicator(close, length=length).dropna()
            return _pick(series)
        if key == "stoch_rsi":
            length = int(cfg.get("length") or cfg.get("rsi_length") or 14)
            smooth_k = int(cfg.get("smooth_k") or 3)
            smooth_d = int(cfg.get("smooth_d") or 3)
            k_series, _ = stoch_rsi_indicator(close, length=length, smooth_k=smooth_k, smooth_d=smooth_d)
            return _pick(k_series)
        if key == "willr":
            length = int(cfg.get("length") or 14)
            high = pd.to_numeric(df["high"], errors="coerce")
            low = pd.to_numeric(df["low"], errors="coerce")
            price_frame = pd.DataFrame({"high": high, "low": low, "close": close})
            wr_series = williams_r_indicator(price_frame, length=length).dropna()
            return _pick(wr_series)
        if key == "ma":
            length = int(cfg.get("length") or 20)
            kind = str(cfg.get("type") or "SMA").upper()
            if kind == "EMA":
                series = ema_indicator(close, length).dropna()
            else:
                series = sma_indicator(close, length).dropna()
            return _pick(series)
        if key == "ema":
            length = int(cfg.get("length") or 20)
            series = ema_indicator(close, length).dropna()
            return _pick(series)
    except Exception:
        return None
    return None


def ensure_shared_wrapper(window, *, normalize_connector_backend) -> BinanceWrapper | None:
    bw = getattr(window, "shared_binance", None)
    if not hasattr(window, "_create_binance_wrapper"):
        return None
    try:
        api_key = window.api_key_edit.text().strip()
        api_secret = window.api_secret_edit.text().strip()
        mode = window.mode_combo.currentText()
        account = window.account_combo.currentText()
        backend_raw = None
        try:
            combo = getattr(window, "connector_combo", None)
            if combo is not None:
                backend_raw = combo.currentData()
                if backend_raw is None:
                    backend_raw = combo.currentText()
        except Exception:
            backend_raw = None
        backend = normalize_connector_backend(backend_raw)
        if bw is not None:
            try:
                bw_key = str(getattr(bw, "api_key", "") or "")
                bw_secret = str(getattr(bw, "api_secret", "") or "")
                bw_mode = str(getattr(bw, "mode", "") or "")
                bw_acct = str(getattr(bw, "account_type", "") or "")
                bw_backend = str(getattr(bw, "_connector_backend", "") or "")
                if (
                    bw_key == api_key
                    and bw_secret == api_secret
                    and bw_mode == mode
                    and bw_acct.upper() == str(account or "").strip().upper()
                    and bw_backend == backend
                ):
                    return bw
            except Exception:
                pass
        bw = window._create_binance_wrapper(
            api_key=api_key,
            api_secret=api_secret,
            mode=mode,
            account_type=account,
            connector_backend=backend,
        )
        window.shared_binance = bw
        return bw
    except Exception:
        return None


def snapshot_live_indicator_context(window, *, snapshot_auth_state) -> dict:
    try:
        auth = snapshot_auth_state(window)
    except Exception:
        auth = {}
    try:
        backend = window._runtime_connector_backend(suppress_refresh=True)
    except Exception:
        backend = None
    try:
        indicator_source = str(window.ind_source_combo.currentText() or "").strip()
    except Exception:
        indicator_source = ""
    return {
        "auth": auth,
        "connector_backend": backend,
        "indicator_source": indicator_source,
    }


def get_live_indicator_wrapper(window, context: dict, *, normalize_connector_backend) -> BinanceWrapper | None:
    try:
        auth = context.get("auth") or {}
    except Exception:
        auth = {}
    try:
        backend = normalize_connector_backend(context.get("connector_backend"))
    except Exception:
        backend = None
    api_key = str(auth.get("api_key") or "")
    api_secret = str(auth.get("api_secret") or "")
    mode = str(auth.get("mode") or "Live")
    account_type = str(auth.get("account_type") or "Futures")
    signature = (api_key, api_secret, mode, account_type, str(backend or ""))
    wrapper = getattr(window, "_live_indicator_wrapper", None)
    if wrapper is None or signature != getattr(window, "_live_indicator_wrapper_signature", None):
        try:
            wrapper = BinanceWrapper(
                api_key,
                api_secret,
                mode=mode,
                account_type=account_type,
                connector_backend=backend,
                default_leverage=int(auth.get("default_leverage", 1) or 1),
                default_margin_mode=str(auth.get("default_margin_mode") or "Isolated"),
            )
        except Exception:
            wrapper = None
        window._live_indicator_wrapper = wrapper
        window._live_indicator_wrapper_signature = signature
    indicator_source = context.get("indicator_source") or ""
    if wrapper is not None and indicator_source:
        try:
            wrapper.indicator_source = indicator_source
        except Exception:
            pass
    return wrapper


def start_live_indicator_refresh_worker(
    window,
    entry: dict,
    *,
    get_live_indicator_wrapper,
    normalize_connector_backend,
    calc_indicator_value_from_df,
    process_live_indicator_refresh_queue,
) -> None:
    cache_key = entry.get("cache_key")
    symbol = entry.get("symbol")
    interval = entry.get("interval")
    indicator_keys = sorted({str(k).strip().lower() for k in (entry.get("indicator_keys") or []) if str(k).strip()})
    if not cache_key or not symbol or not interval or not indicator_keys:
        return
    indicators_cfg = entry.get("indicators_cfg") or {}
    use_live_values = bool(entry.get("use_live_values", True))
    context = entry.get("context") or {}
    indicator_source = context.get("indicator_source") or ""

    cache = getattr(window, "_live_indicator_cache", None)
    if not isinstance(cache, dict):
        cache = {}
        window._live_indicator_cache = cache
    cache_entry = cache.get(cache_key)
    if cache_entry is None:
        cache_entry = {"df": None, "values": {}, "error": False, "df_ts": 0.0, "error_ts": 0.0}
        cache[cache_key] = cache_entry
    cache_entry["refreshing"] = True

    wrapper = get_live_indicator_wrapper(window, context)
    auth = context.get("auth") or {}
    backend = normalize_connector_backend(context.get("connector_backend"))

    def _do():
        bw = wrapper
        if bw is None:
            bw = BinanceWrapper(
                str(auth.get("api_key") or ""),
                str(auth.get("api_secret") or ""),
                mode=str(auth.get("mode") or "Live"),
                account_type=str(auth.get("account_type") or "Futures"),
                connector_backend=backend,
                default_leverage=int(auth.get("default_leverage", 1) or 1),
                default_margin_mode=str(auth.get("default_margin_mode") or "Isolated"),
            )
        if indicator_source:
            try:
                bw.indicator_source = indicator_source
            except Exception:
                pass
        frame = bw.get_klines(symbol, interval, limit=200)
        if frame is None or getattr(frame, "empty", True):
            raise RuntimeError("no_kline_data")
        values = {}
        for key in indicator_keys:
            values[key] = calc_indicator_value_from_df(
                frame,
                key,
                indicators_cfg.get(key, {}),
                use_live_values=use_live_values,
            )
        return {"df": frame, "values": values}

    worker = CallWorker(_do, parent=window)

    def _done(res, err, key=cache_key):
        try:
            cache_local = getattr(window, "_live_indicator_cache", None)
        except Exception:
            cache_local = None
        if not isinstance(cache_local, dict):
            cache_local = {}
            try:
                window._live_indicator_cache = cache_local
            except Exception:
                pass
        cache_entry_local = cache_local.get(key) or {}
        cache_entry_local["refreshing"] = False
        now_ts = time.monotonic()
        if err or not isinstance(res, dict):
            cache_entry_local["error"] = True
            cache_entry_local["error_ts"] = now_ts
        else:
            cache_entry_local["error"] = False
            cache_entry_local["error_ts"] = 0.0
            cache_entry_local["df"] = res.get("df")
            cache_entry_local["df_ts"] = now_ts
            values_cache = cache_entry_local.setdefault("values", {})
            values_cache.update(res.get("values") or {})
            cache_entry_local["use_live_values"] = use_live_values
            if indicator_source:
                cache_entry_local["indicator_source"] = indicator_source
            cache_entry_local.pop("pending_keys", None)
        cache_local[key] = cache_entry_local
        try:
            inflight = getattr(window, "_live_indicator_refresh_inflight", None)
            if isinstance(inflight, set):
                inflight.discard(key)
        except Exception:
            pass
        try:
            active = int(getattr(window, "_live_indicator_refresh_active", 0) or 0)
            if active > 0:
                active -= 1
            window._live_indicator_refresh_active = active
        except Exception:
            pass
        try:
            QtCore.QTimer.singleShot(0, lambda w=window: process_live_indicator_refresh_queue(w))
        except Exception:
            pass

    worker.done.connect(_done)
    workers = getattr(window, "_live_indicator_refresh_workers", None)
    if not isinstance(workers, list):
        workers = []
        window._live_indicator_refresh_workers = workers
    workers.append(worker)
    worker.finished.connect(lambda: workers.remove(worker) if worker in workers else None)
    worker.start()


def process_live_indicator_refresh_queue(window, *, start_live_indicator_refresh_worker) -> None:
    try:
        window._live_indicator_refresh_scheduled = False
    except Exception:
        pass
    queue = getattr(window, "_live_indicator_refresh_queue", None)
    if not queue:
        return
    inflight = getattr(window, "_live_indicator_refresh_inflight", None)
    if not isinstance(inflight, set):
        inflight = set()
        window._live_indicator_refresh_inflight = inflight
    active = int(getattr(window, "_live_indicator_refresh_active", 0) or 0)
    limit = int(getattr(window, "_live_indicator_refresh_limit", 2) or 2)
    while queue and active < limit:
        entry = queue.popleft()
        cache_key = entry.get("cache_key")
        if not cache_key or cache_key in inflight:
            continue
        inflight.add(cache_key)
        active += 1
        window._live_indicator_refresh_active = active
        start_live_indicator_refresh_worker(window, entry)


def queue_live_indicator_refresh(
    window,
    cache: dict,
    cache_key: tuple,
    symbol: str,
    interval: str,
    indicator_keys: set[str],
    indicators_cfg: dict,
    use_live_values: bool,
    indicator_source: str,
    *,
    snapshot_live_indicator_context,
    process_live_indicator_refresh_queue,
) -> None:
    if not cache_key or not symbol or not interval or not indicator_keys:
        return
    inflight = getattr(window, "_live_indicator_refresh_inflight", None)
    if not isinstance(inflight, set):
        inflight = set()
        window._live_indicator_refresh_inflight = inflight
    queue = getattr(window, "_live_indicator_refresh_queue", None)
    if queue is None:
        queue = deque()
        window._live_indicator_refresh_queue = queue
    cache_entry = cache.get(cache_key)
    if cache_entry is None:
        cache_entry = {"df": None, "values": {}, "error": False, "df_ts": 0.0, "error_ts": 0.0}
        cache[cache_key] = cache_entry
    pending = cache_entry.setdefault("pending_keys", set())
    pending.update(indicator_keys)
    if cache_key in inflight:
        return
    for existing in queue:
        if existing.get("cache_key") == cache_key:
            existing.setdefault("indicator_keys", set()).update(indicator_keys)
            return
    context = snapshot_live_indicator_context(window)
    if indicator_source and not context.get("indicator_source"):
        context["indicator_source"] = indicator_source
    entry = {
        "cache_key": cache_key,
        "symbol": symbol,
        "interval": interval,
        "indicator_keys": set(indicator_keys),
        "indicators_cfg": indicators_cfg,
        "use_live_values": use_live_values,
        "context": context,
    }
    queue.append(entry)
    if not getattr(window, "_live_indicator_refresh_scheduled", False):
        window._live_indicator_refresh_scheduled = True
        QtCore.QTimer.singleShot(0, lambda w=window: process_live_indicator_refresh_queue(w))


def collect_current_indicator_live_strings(
    window,
    symbol,
    indicator_keys,
    cache,
    interval_map: dict[str, list[str]] | None = None,
    default_interval_hint: str | None = None,
    *,
    sanitize_interval_hint,
    canonicalize_indicator_key,
    normalize_indicator_token,
    indicator_short_label,
    dedupe_indicator_entries_normalized,
    queue_live_indicator_refresh,
) -> list[str]:
    raw_keys = [str(k).strip() for k in (indicator_keys or []) if str(k).strip()]
    keys: list[str] = []
    seen_keys: set[str] = set()
    for key in raw_keys:
        key_norm = canonicalize_indicator_key(key) or key.lower()
        if not key_norm or key_norm in seen_keys:
            continue
        seen_keys.add(key_norm)
        keys.append(key_norm)
    if not symbol or not keys:
        return []
    default_interval = sanitize_interval_hint(default_interval_hint) or "1m"
    symbol_norm = str(symbol).strip().upper()
    try:
        indicators_cfg = (window.config or {}).get("indicators", {}) or {}
    except Exception:
        indicators_cfg = {}
    try:
        use_live_values = bool((window.config or {}).get("indicator_use_live_values", False))
    except Exception:
        use_live_values = True
    try:
        indicator_source = str(window.ind_source_combo.currentText() or "").strip()
    except Exception:
        indicator_source = ""
    buy_thresholds = {
        "stoch_rsi": float((indicators_cfg.get("stoch_rsi", {}).get("buy_value") or 20.0)),
        "willr": float((indicators_cfg.get("willr", {}).get("buy_value") or -80.0)),
        "rsi": float((indicators_cfg.get("rsi", {}).get("buy_value") or 30.0)),
    }
    sell_thresholds = {
        "stoch_rsi": float((indicators_cfg.get("stoch_rsi", {}).get("sell_value") or 80.0)),
        "willr": float((indicators_cfg.get("willr", {}).get("sell_value") or -20.0)),
        "rsi": float((indicators_cfg.get("rsi", {}).get("sell_value") or 70.0)),
    }
    ttl = float(getattr(window, "_live_indicator_cache_ttl", 8.0) or 8.0)
    now_ts = time.monotonic()
    entries: list[str] = []
    refresh_requests: dict[tuple, dict] = {}
    for key in keys:
        intervals: list[str] = []
        if isinstance(interval_map, dict):
            intervals = interval_map.get(key) or interval_map.get(key.lower()) or []
        if not intervals:
            intervals = [default_interval]
        normalized_intervals: list[str] = []
        seen_intervals: set[str] = set()
        for interval_label in intervals:
            interval_clean = (str(interval_label or "").strip() or default_interval).lower()
            interval_key = normalize_indicator_token(interval_clean) or interval_clean
            if interval_key in seen_intervals:
                continue
            seen_intervals.add(interval_key)
            normalized_intervals.append(interval_clean)
        if not normalized_intervals:
            normalized_intervals = [default_interval]
        for interval_clean in normalized_intervals:
            cache_key = (symbol_norm, interval_clean)
            cache_entry = cache.get(cache_key)
            if cache_entry is None:
                cache_entry = {"df": None, "values": {}, "error": False, "df_ts": 0.0, "error_ts": 0.0}
                cache[cache_key] = cache_entry
            frame = cache_entry.get("df")
            try:
                frame_ts = float(cache_entry.get("df_ts") or 0.0)
            except Exception:
                frame_ts = 0.0
            needs_refresh = frame is None or (now_ts - frame_ts) >= ttl
            cached_mode = cache_entry.get("use_live_values")
            if cached_mode is None or cached_mode != use_live_values:
                needs_refresh = True
            cached_source = str(cache_entry.get("indicator_source") or "")
            if indicator_source and cached_source != indicator_source:
                needs_refresh = True
            try:
                error_ts = float(cache_entry.get("error_ts") or 0.0)
            except Exception:
                error_ts = 0.0
            recently_failed = bool(cache_entry.get("error")) and (now_ts - error_ts) < ttl
            if needs_refresh and not recently_failed and not cache_entry.get("refreshing"):
                req = refresh_requests.setdefault(
                    cache_key,
                    {"symbol": symbol_norm, "interval": interval_clean, "keys": set()},
                )
                req["keys"].add(key)
            values_cache = cache_entry.setdefault("values", {})
            value = values_cache.get(key)
            if value is None:
                values_cache[key] = None
                value = None
            label = indicator_short_label(key)
            interval_tag = f"@{interval_clean.upper()}" if interval_clean else ""
            if value is None or not isinstance(value, (int, float)) or not math.isfinite(value):
                value_text = "--"
                action = ""
            else:
                value_text = f"{value:.2f}"
                action = ""
                buy = buy_thresholds.get(key)
                sell = sell_thresholds.get(key)
                if key == "stoch_rsi":
                    if buy is not None and value <= buy:
                        action = "-Buy"
                    elif sell is not None and value >= sell:
                        action = "-Sell"
                elif key == "willr":
                    if buy is not None and value <= buy:
                        action = "-Buy"
                    elif sell is not None and value >= sell:
                        action = "-Sell"
                elif key == "rsi":
                    if buy is not None and value <= buy:
                        action = "-Buy"
                    elif sell is not None and value >= sell:
                        action = "-Sell"
            entries.append(f"{label}{interval_tag} {value_text}{action}".strip())
    if entries:
        entries = dedupe_indicator_entries_normalized(entries)
    if refresh_requests:
        for cache_key, req in refresh_requests.items():
            queue_live_indicator_refresh(
                window,
                cache,
                cache_key,
                req.get("symbol") or symbol_norm,
                req.get("interval") or default_interval,
                req.get("keys") or set(),
                indicators_cfg,
                use_live_values,
                indicator_source,
            )
    return entries
