from __future__ import annotations

from datetime import datetime, timezone
import time

import pandas as pd
import requests
from binance.exceptions import BinanceAPIException

from ..clients.connector_clients import CcxtConnectorError, OfficialConnectorError
from ..transport.helpers import _coerce_interval_seconds

FUTURES_NATIVE_INTERVALS = {
    "1m",
    "3m",
    "5m",
    "15m",
    "30m",
    "1h",
    "2h",
    "4h",
    "6h",
    "8h",
    "12h",
    "1d",
    "3d",
    "1w",
    "1M",
}

SPOT_NATIVE_INTERVALS = {
    "1m",
    "3m",
    "5m",
    "15m",
    "30m",
    "1h",
    "2h",
    "4h",
    "6h",
    "8h",
    "12h",
    "1d",
    "3d",
    "1w",
    "1M",
}


def _fetch_futures_klines_rest(self, params: dict, *, live: bool = False):
    """
    Fetch klines directly from REST. When live=True, always hit production futures
    (fapi) even if the bot is running in testnet mode.
    """
    payload = dict(params or {})
    if "symbol" in payload:
        payload["symbol"] = str(payload["symbol"]).upper()
    base = self._futures_base_live() if live else self._futures_base()
    url = f"{base.rstrip('/')}/v1/klines"
    resp = requests.get(url, params=payload, timeout=10)
    resp.raise_for_status()
    return resp.json()


def get_klines(self, symbol, interval, limit=500):
    source = (getattr(self, "indicator_source", "") or "").strip().lower()
    acct = str(getattr(self, "account_type", "") or "").upper()
    if source in ("binance spot", "binance_spot", "spot"):
        native_intervals = SPOT_NATIVE_INTERVALS
    else:
        native_intervals = FUTURES_NATIVE_INTERVALS
    binance_source = source in ("", "binance futures", "binance_futures", "futures", "binance spot", "binance_spot", "spot")
    interval_key = str(interval or "").strip()
    custom_interval_requested = binance_source and interval_key not in native_intervals
    cache_key = (source or "binance", str(symbol or "").upper(), str(interval or ""), int(limit or 0))
    interval_seconds = _coerce_interval_seconds(interval)
    ttl = max(1.0, min(interval_seconds * 0.9, 3600.0))
    cached_df = None
    now = time.time()

    with self._kline_cache_lock:
        entry = self._kline_cache.get(cache_key)
        if entry:
            age = now - entry["ts"]
            if age < ttl:
                return entry["df"].copy(deep=True)
            cached_df = entry["df"].copy(deep=True)

    ban_remaining = self._seconds_until_unban()
    if ban_remaining > 0.0:
        if cached_df is not None:
            if (now - getattr(self, "_last_ban_log", 0.0)) > 15.0:
                eta = datetime.fromtimestamp(time.time() + ban_remaining).strftime("%H:%M:%S")
                self._last_ban_log = now
                self._log(f"REST ban active (~{ban_remaining:.0f}s). Serving cached klines for {symbol}@{interval} until {eta}.", lvl="warn")
            return cached_df
        raise RuntimeError(f"binance_rest_banned:{ban_remaining:.0f}s")

    if custom_interval_requested:
        end_dt = pd.Timestamp.utcnow()
        if end_dt.tzinfo is not None:
            end_dt = end_dt.tz_localize(None)
        span_seconds = _coerce_interval_seconds(interval_key or interval) * max(int(limit or 1), 1)
        start_dt = end_dt - pd.Timedelta(seconds=span_seconds * 2)
        fetch_limit = max(int(limit or 1) * 2, int(limit or 1))
        df_custom = self.get_klines_range(symbol, interval_key or interval, start_dt, end_dt, fetch_limit)
        if df_custom is None or df_custom.empty:
            if cached_df is not None:
                return cached_df
            raise RuntimeError(f"No kline data returned for interval '{interval}'")
        trimmed = df_custom.tail(int(limit or 1)).copy()
        with self._kline_cache_lock:
            self._kline_cache[cache_key] = {"df": trimmed.copy(deep=True), "ts": time.time()}
        return trimmed

    raw = None
    max_retries = 5
    attempt = 0
    while attempt < max_retries:
        attempt += 1
        try:
            params = {"symbol": symbol, "interval": interval, "limit": limit}
            client = self.client
            method = None
            use_live_fut = source in ("", "binance futures", "binance_futures", "futures") and self._use_live_futures_data_for_indicators()
            if use_live_fut:
                self._ensure_ws_stream(symbol, interval)
                if not self._symbol_available_on_live_futures(symbol):
                    try:
                        self._log(f"{symbol} not on live futures; falling back to testnet data for indicators.", lvl="warn")
                    except Exception:
                        pass
                    method = getattr(client, "futures_klines", None) or getattr(client, "get_klines", None)
                else:
                    try:
                        raw = self._fetch_futures_klines_rest(params, live=True)
                    except Exception as exc:
                        try:
                            self._log(f"Live futures klines fetch failed for {symbol}@{interval}: {exc}; falling back to testnet", lvl="warn")
                        except Exception:
                            pass
                        raw = None
                    if not raw:
                        try:
                            self._log(f"Live futures klines empty for {symbol}@{interval}; falling back to testnet", lvl="warn")
                        except Exception:
                            pass
                        method = getattr(client, "futures_klines", None) or getattr(client, "get_klines", None)
            elif source in ("", "binance futures", "binance_futures", "futures"):
                method = getattr(client, "futures_klines", None)
                if method is None:
                    method = getattr(client, "get_klines", None)
            elif source in ("binance spot", "binance_spot", "spot"):
                method = getattr(client, "get_klines", None) or getattr(client, "klines", None)
            elif source == "bybit":
                bybit_interval = self._bybit_interval(interval)
                url = "https://api.bybit.com/v5/market/kline"
                bybit_params = {"category": "linear", "symbol": symbol, "interval": bybit_interval, "limit": limit}
                resp = requests.get(url, params=bybit_params, timeout=10)
                resp.raise_for_status()
                payload = resp.json() or {}
                data = (payload.get("result", {}) or {}).get("list", []) or []
                data = sorted(data, key=lambda item: int(item[0]))
                raw = [[int(item[0]), item[1], item[2], item[3], item[4], item[5], 0, 0, 0, 0, 0, 0] for item in data]
            elif source in ("tradingview", "trading view"):
                raise NotImplementedError("TradingView data source is not implemented in this build.")
            else:
                if acct == "FUTURES":
                    method = getattr(client, "futures_klines", None)
                    if method is None:
                        method = getattr(client, "get_klines", None)
                else:
                    method = getattr(client, "get_klines", None) or getattr(client, "klines", None)
            if raw is None and method is not None:
                raw = method(**params)
            elif raw is None and source not in ("bybit", "tradingview", "trading view"):
                raise AttributeError("Connector does not provide a klines method")
            break
        except (BinanceAPIException, OfficialConnectorError, CcxtConnectorError) as exc:
            ban_until = self._handle_potential_ban(exc)
            if cached_df is not None and ban_until:
                if (time.time() - getattr(self, "_last_ban_log", 0.0)) > 15.0:
                    when = datetime.fromtimestamp(ban_until).strftime("%H:%M:%S")
                    self._last_ban_log = time.time()
                    self._log(f"Binance REST rate limit hit; serving cached klines for {symbol}@{interval} until {when}.", lvl="warn")
                return cached_df
            if ban_until:
                delay = max(1.0, ban_until - time.time())
                if (time.time() - getattr(self, "_last_ban_log", 0.0)) > 15.0:
                    when = datetime.fromtimestamp(ban_until).strftime("%H:%M:%S")
                    self._last_ban_log = time.time()
                    self._log(f"Binance REST rate limiter activated; retrying {symbol}@{interval} after {when}.", lvl="warn")
                time.sleep(min(delay, 5.0))
                continue
            if attempt >= max_retries:
                raise
            time.sleep(min(0.5 * attempt, 2.0))
        except requests.exceptions.RequestException as exc:
            context = f"fetching {symbol}@{interval}"
            self._handle_network_offline(context, exc)
            error_cls = getattr(self, "_network_connectivity_error_cls", RuntimeError)
            raise error_cls(f"network_offline:{symbol}@{interval}") from exc

    if raw is None:
        raise RuntimeError("kline_fetch_failed: no data returned")

    cols = ["open_time", "open", "high", "low", "close", "volume", "close_time", "qav", "num_trades", "taker_base", "taker_quote", "ignore"]
    df = pd.DataFrame(raw, columns=cols)
    df["open_time"] = pd.to_datetime(df["open_time"], unit="ms")
    df.set_index("open_time", inplace=True)
    for column in ["open", "high", "low", "close", "volume"]:
        df[column] = pd.to_numeric(df[column], errors="coerce")
    trimmed = df[["open", "high", "low", "close", "volume"]].copy(deep=True)
    ws_row = self._ws_latest_candle(symbol, interval) if use_live_fut else None
    if ws_row:
        try:
            ts = pd.to_datetime(ws_row["open_time"], unit="ms")
            patch = pd.DataFrame(
                [[ws_row["open"], ws_row["high"], ws_row["low"], ws_row["close"], ws_row["volume"]]],
                index=[ts],
                columns=["open", "high", "low", "close", "volume"],
            )
            trimmed.loc[ts] = patch.iloc[0]
            trimmed = trimmed.sort_index()
        except Exception:
            pass
    with self._kline_cache_lock:
        self._kline_cache[cache_key] = {"df": trimmed.copy(deep=True), "ts": time.time()}
    self._last_network_error_log = 0.0
    self._handle_network_recovered()
    return trimmed


def _klines_raw_to_df(raw):
    cols = ["open_time", "open", "high", "low", "close", "volume", "close_time", "qav", "num_trades", "taker_base", "taker_quote", "ignore"]
    if not raw:
        return pd.DataFrame(columns=["open", "high", "low", "close", "volume"]).astype(float)
    df = pd.DataFrame(raw, columns=cols)
    df["open_time"] = pd.to_datetime(df["open_time"], unit="ms")
    df.set_index("open_time", inplace=True)
    for column in ["open", "high", "low", "close", "volume"]:
        df[column] = pd.to_numeric(df[column], errors="coerce")
    return df[["open", "high", "low", "close", "volume"]].copy(deep=True)


def _interval_seconds_to_freq(seconds: float) -> str:
    seconds = float(seconds or 0.0)
    if seconds <= 0.0:
        raise ValueError("Interval must be positive")
    if seconds % 86400 == 0:
        return f"{int(seconds // 86400)}D"
    if seconds % 3600 == 0:
        return f"{int(seconds // 3600)}h"
    if seconds % 60 == 0:
        return f"{int(seconds // 60)}min"
    return f"{int(seconds)}S"


def _get_klines_range_native(self, symbol: str, interval: str, start_dt, end_dt, limit: int, acct: str, source: str):
    start_ts = pd.Timestamp(start_dt)
    end_ts = pd.Timestamp(end_dt)
    if start_ts.tzinfo is None:
        start_utc = start_ts.tz_localize("UTC")
    else:
        start_utc = start_ts.tz_convert("UTC")
    if end_ts.tzinfo is None:
        end_utc = end_ts.tz_localize("UTC")
    else:
        end_utc = end_ts.tz_convert("UTC")
    start_filter = start_utc.tz_localize(None)
    end_filter = end_utc.tz_localize(None)
    start_ms = int(start_utc.timestamp() * 1000)
    end_ms = int(end_utc.timestamp() * 1000)
    interval_ms = max(int(_coerce_interval_seconds(interval) * 1000), 1)
    all_frames = []
    current = start_ms
    max_limit = 1500 if acct.startswith("FUT") else 1000
    limit = max(1, int(limit or max_limit))
    limit = min(limit, max_limit)
    guard = 0
    max_network_retries = 4
    while current < end_ms and guard < 10000:
        guard += 1
        raw = None
        last_error = None
        for attempt in range(max_network_retries):
            try:
                params = {
                    "symbol": symbol,
                    "interval": interval,
                    "startTime": current,
                    "endTime": end_ms,
                    "limit": limit,
                }
                client = self.client
                use_live_fut = (acct == "FUTURES" or source in ("binance futures", "binance_futures", "futures", "")) and self._use_live_futures_data_for_indicators()
                if use_live_fut:
                    self._ensure_ws_stream(symbol, interval)
                    if not self._symbol_available_on_live_futures(symbol):
                        try:
                            self._log(f"{symbol} not on live futures; falling back to testnet data for indicators.", lvl="warn")
                        except Exception:
                            pass
                        method = getattr(client, "futures_klines", None) or getattr(client, "get_klines", None)
                        if method is None:
                            raise AttributeError("Connector does not provide a klines method")
                        raw = method(**params)
                    else:
                        try:
                            raw = self._fetch_futures_klines_rest(params, live=True)
                        except Exception as exc:
                            try:
                                self._log(f"Live futures klines range failed for {symbol}@{interval}: {exc}; falling back to testnet", lvl="warn")
                            except Exception:
                                pass
                            raw = None
                        if not raw:
                            method = getattr(client, "futures_klines", None) or getattr(client, "get_klines", None)
                            if method is None:
                                raise AttributeError("Connector does not provide a klines method")
                            raw = method(**params)
                else:
                    if acct == "FUTURES" or source in ("binance futures", "binance_futures", "futures", ""):
                        method = getattr(client, "futures_klines", None)
                        if method is None:
                            method = getattr(client, "get_klines", None)
                    else:
                        method = getattr(client, "get_klines", None) or getattr(client, "klines", None)
                    if method is None:
                        raise AttributeError("Connector does not provide a klines method")
                    raw = method(**params)
                break
            except (BinanceAPIException, OfficialConnectorError, CcxtConnectorError) as exc:
                ban_until = self._handle_potential_ban(exc)
                if ban_until:
                    delay = max(1.0, ban_until - time.time())
                    if (time.time() - getattr(self, "_last_ban_log", 0.0)) > 15.0:
                        when = datetime.fromtimestamp(ban_until).strftime("%H:%M:%S")
                        self._last_ban_log = time.time()
                        try:
                            self._log(f"Rate limit hit while fetching {symbol}@{interval}; retrying after {when}.", lvl="warn")
                        except Exception:
                            pass
                    time.sleep(min(delay, 5.0))
                    continue
                last_error = exc
                break
            except requests.exceptions.RequestException as req_err:
                last_error = req_err
                sleep_for = min(1.5 * (attempt + 1), 6.0)
                time.sleep(sleep_for)
            except Exception as exc:
                last_error = exc
                break

        if raw is None:
            if last_error is not None:
                if isinstance(last_error, requests.exceptions.RequestException):
                    guard -= 1
                    now = time.time()
                    if (now - getattr(self, "_last_network_log", 0.0)) > 10.0:
                        self._last_network_log = now
                        try:
                            self._log(f"Network hiccup while fetching {symbol}@{interval}; retrying...", lvl="warn")
                        except Exception:
                            pass
                    continue
                raise RuntimeError(f"network_error:{last_error}") from last_error
            break

        if not raw:
            break

        frame = self._klines_raw_to_df(raw)
        if use_live_fut:
            ws_row = self._ws_latest_candle(symbol, interval)
            if ws_row:
                try:
                    ts = pd.to_datetime(ws_row["open_time"], unit="ms")
                    patch = pd.DataFrame(
                        [[ws_row["open"], ws_row["high"], ws_row["low"], ws_row["close"], ws_row["volume"]]],
                        index=[ts],
                        columns=["open", "high", "low", "close", "volume"],
                    )
                    frame.loc[ts] = patch.iloc[0]
                    frame = frame.sort_index()
                except Exception:
                    pass
        all_frames.append(frame)

        last_open = int(raw[-1][0])
        next_open = last_open + interval_ms
        if next_open <= current:
            break
        current = next_open

    if not all_frames:
        return self._klines_raw_to_df([])

    full = pd.concat(all_frames).sort_index()
    full = full[~full.index.duplicated(keep="first")]
    return full.loc[start_filter:end_filter].copy()


def _get_klines_range_custom(self, symbol: str, interval: str, start_dt, end_dt, limit: int, acct: str, source: str):
    interval_seconds = _coerce_interval_seconds(interval)
    if interval_seconds < 60:
        raise NotImplementedError(f"Custom interval '{interval}' below 1 minute is not supported.")
    if interval_seconds < 3600:
        base_interval = "1m"
    elif interval_seconds < 86400:
        base_interval = "1h"
    else:
        base_interval = "1d"
    base_seconds = _coerce_interval_seconds(base_interval)
    if interval_seconds % base_seconds != 0:
        raise NotImplementedError(f"Custom interval '{interval}' is not a multiple of {base_interval}.")
    factor = int(interval_seconds / base_seconds)
    base_limit = max(int(limit or 1000) * factor, factor)
    fetch_end = end_dt + pd.Timedelta(seconds=base_seconds * factor)
    base_df = self._get_klines_range_native(symbol, base_interval, start_dt, fetch_end, base_limit, acct, source)
    if base_df.empty:
        return base_df
    freq = self._interval_seconds_to_freq(interval_seconds)
    agg = base_df.resample(freq, label="left", closed="left").agg({
        "open": "first",
        "high": "max",
        "low": "min",
        "close": "last",
        "volume": "sum",
    })
    agg = agg.dropna()
    return agg.loc[start_dt:end_dt].copy()


def get_klines_range(self, symbol, interval, start_time, end_time, limit=1000):
    """
    Fetch historical klines between start_time and end_time (inclusive) and return a DataFrame.
    start_time/end_time may be datetime, int milliseconds, or string accepted by pandas.to_datetime.
    """
    try:
        if isinstance(start_time, str):
            start_dt = pd.to_datetime(start_time)
        elif isinstance(start_time, datetime):
            start_dt = start_time
        else:
            start_dt = pd.to_datetime(int(start_time), unit="ms")
    except Exception as exc:
        raise ValueError(f"Invalid start_time: {start_time}") from exc
    if isinstance(start_dt, pd.Timestamp) and start_dt.tzinfo is not None:
        start_dt = start_dt.tz_localize(None)
    elif getattr(start_dt, "tzinfo", None) is not None:
        start_dt = start_dt.astimezone(timezone.utc).replace(tzinfo=None)

    try:
        if isinstance(end_time, str):
            end_dt = pd.to_datetime(end_time)
        elif isinstance(end_time, datetime):
            end_dt = end_time
        else:
            end_dt = pd.to_datetime(int(end_time), unit="ms")
    except Exception as exc:
        raise ValueError(f"Invalid end_time: {end_time}") from exc
    if isinstance(end_dt, pd.Timestamp) and end_dt.tzinfo is not None:
        end_dt = end_dt.tz_localize(None)
    elif getattr(end_dt, "tzinfo", None) is not None:
        end_dt = end_dt.astimezone(timezone.utc).replace(tzinfo=None)

    if end_dt <= start_dt:
        raise ValueError("end_time must be greater than start_time")

    source = (getattr(self, "indicator_source", "") or "").strip().lower()
    acct = str(getattr(self, "account_type", "") or "").upper()
    if source not in ("", "binance futures", "binance_futures", "futures", "binance spot", "binance_spot", "spot"):
        raise NotImplementedError(f"Historical klines not supported for source '{source}' in backtester.")

    native_intervals = FUTURES_NATIVE_INTERVALS if acct.startswith("FUT") else SPOT_NATIVE_INTERVALS
    if interval in native_intervals:
        df = self._get_klines_range_native(symbol, interval, start_dt, end_dt, limit, acct, source)
    else:
        df = self._get_klines_range_custom(symbol, interval, start_dt, end_dt, limit, acct, source)

    if df.empty:
        raise RuntimeError("No kline data returned for requested range.")
    return df


def bind_binance_market_data(wrapper_cls, *, network_error_cls):
    wrapper_cls._fetch_futures_klines_rest = _fetch_futures_klines_rest
    wrapper_cls.get_klines = get_klines
    wrapper_cls._klines_raw_to_df = staticmethod(_klines_raw_to_df)
    wrapper_cls._interval_seconds_to_freq = staticmethod(_interval_seconds_to_freq)
    wrapper_cls._get_klines_range_native = _get_klines_range_native
    wrapper_cls._get_klines_range_custom = _get_klines_range_custom
    wrapper_cls.get_klines_range = get_klines_range
    wrapper_cls._network_connectivity_error_cls = network_error_cls
