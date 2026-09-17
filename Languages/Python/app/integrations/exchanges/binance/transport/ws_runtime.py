from __future__ import annotations

import math
import time

import requests

from ..runtime_diagnostics import report_runtime_fallback
from .helpers import _coerce_interval_seconds, _env_flag


_WS_PUBLIC_CANDLE_FIELDS = (
    "open_time",
    "open",
    "high",
    "low",
    "close",
    "volume",
    "closed",
    "event_time",
)

try:
    from binance.streams import ThreadedWebsocketManager as _TWM
except Exception:
    _TWM = None


def _is_testnet_mode(mode: str | None) -> bool:
    from app.settings.execution_mode import is_testnet_trading_mode

    return is_testnet_trading_mode(mode)


def _use_live_futures_data_for_indicators(self) -> bool:
    try:
        default_live = _is_testnet_mode(self.mode)
        return _env_flag("BINANCE_INDICATOR_LIVE_DATA", default_live)
    except Exception as exc:
        report_runtime_fallback(self, "Live-indicator source configuration failed", exc)
        return False


def _live_futures_symbol_set(self) -> set:
    now = time.time()
    if self._live_fut_symbols_cache and (now - self._live_fut_symbols_ts) < 900:
        return self._live_fut_symbols_cache
    try:
        url = f"{self._futures_base_live().rstrip('/')}/v1/exchangeInfo"
        data = requests.get(url, timeout=10).json() or {}
        symbols = {str(s.get("symbol") or "").upper() for s in data.get("symbols", []) if s.get("status") == "TRADING"}
        if symbols:
            self._live_fut_symbols_cache = symbols
            self._live_fut_symbols_ts = now
            return symbols
    except Exception as exc:
        report_runtime_fallback(self, "Live futures symbol catalog refresh failed", exc)
    return self._live_fut_symbols_cache or set()


def _symbol_available_on_live_futures(self, symbol: str) -> bool:
    try:
        sym = (symbol or "").upper()
        if not sym:
            return False
        live_symbols = self._live_futures_symbol_set()
        if not live_symbols and _is_testnet_mode(self.mode):
            return True
        return sym in live_symbols
    except Exception as exc:
        report_runtime_fallback(self, f"Live futures symbol lookup failed for {symbol}", exc)
        return False


def _ensure_ws_manager(self):
    if not self._ws_enabled or _TWM is None:
        return
    if self._ws_twm is not None:
        return
    try:
        ws_testnet = _is_testnet_mode(self.mode)
        try:
            if ws_testnet and self._use_live_futures_data_for_indicators():
                ws_testnet = False
        except Exception as exc:
            report_runtime_fallback(self, "WebSocket live-data override failed", exc)
        self._ws_twm = _TWM(
            api_key=self.api_key or "",
            api_secret=self.api_secret or "",
            futures=True,
            testnet=ws_testnet,
        )
        self._ws_twm.start()
    except Exception as exc:
        report_runtime_fallback(self, "WebSocket manager init failed; disabling fast indicators", exc)
        self._ws_twm = None
        self._ws_enabled = False


def _ws_kline_handler(self, msg):
    try:
        if not isinstance(msg, dict):
            return
        k = msg.get("k") or msg.get("data", {}).get("k")
        if not k:
            return
        sym = str(k.get("s") or "").upper()
        interval = str(k.get("i") or "")
        if not sym or not interval:
            return
        open_time = int(k.get("t") or 0)
        event_time = int(msg.get("E") or 0)
        if open_time <= 0 or event_time <= 0:
            return
        try:
            open_value = float(k.get("o"))
            high_value = float(k.get("h"))
            low_value = float(k.get("l"))
            close_value = float(k.get("c"))
            volume_value = float(k.get("v"))
        except (TypeError, ValueError, OverflowError):
            return
        if not all(math.isfinite(value) for value in (open_value, high_value, low_value, close_value, volume_value)):
            return
        if (
            min(open_value, high_value, low_value, close_value) <= 0.0
            or volume_value < 0.0
            or high_value < max(open_value, close_value, low_value)
            or low_value > min(open_value, close_value, high_value)
        ):
            return
        row = {
            "open_time": open_time,
            "open": open_value,
            "high": high_value,
            "low": low_value,
            "close": close_value,
            "volume": volume_value,
            "closed": bool(k.get("x") or False),
            "event_time": event_time,
            "receipt_time_ms": int(time.time() * 1000),
            "sequence_ok": True,
        }
        key = (sym, interval)
        with self._ws_lock:
            previous = self._ws_kline_cache.get(key)
            if isinstance(previous, dict):
                previous_event = int(previous.get("event_time") or 0)
                previous_open = int(previous.get("open_time") or 0)
                if event_time <= previous_event or open_time < previous_open:
                    rejections = getattr(self, "_ws_kline_rejections", None)
                    if not isinstance(rejections, dict):
                        rejections = {}
                        setattr(self, "_ws_kline_rejections", rejections)
                    rejections[key] = {
                        "reason": "replayed or out-of-order websocket candle",
                        "event_time": event_time,
                        "open_time": open_time,
                        "rejected_at_ms": row["receipt_time_ms"],
                    }
                    return
                try:
                    interval_ms = int(_coerce_interval_seconds(interval) * 1000)
                except (TypeError, ValueError, OverflowError):
                    interval_ms = 0
                if interval_ms > 0 and open_time - previous_open > interval_ms + 1_000:
                    row["sequence_ok"] = False
            self._ws_kline_cache[key] = row
    except Exception as exc:
        report_runtime_fallback(self, "WebSocket kline payload was malformed", exc)


def _ensure_ws_stream(self, symbol: str, interval: str):
    if not self._ws_enabled or _TWM is None:
        return
    self._ensure_ws_manager()
    if self._ws_twm is None:
        return
    sym = (symbol or "").upper()
    key = (sym, interval)
    with self._ws_lock:
        if key in self._ws_streams:
            return
    try:
        stream_id = self._ws_twm.start_kline_futures_socket(
            callback=self._ws_kline_handler,
            symbol=sym,
            interval=interval,
        )
        with self._ws_lock:
            self._ws_streams[key] = stream_id
    except Exception as exc:
        report_runtime_fallback(self, f"WebSocket subscribe failed for {sym}@{interval}; continuing without WS", exc)


def _ws_latest_candle(self, symbol: str, interval: str):
    if not self._ws_enabled:
        return None
    sym = (symbol or "").upper()
    key = (sym, interval)
    with self._ws_lock:
        row = self._ws_kline_cache.get(key)
        if not isinstance(row, dict):
            return None
        return {field: row[field] for field in _WS_PUBLIC_CANDLE_FIELDS if field in row}


def _ws_latest_candle_metadata(self, symbol: str, interval: str):
    """Return the internal candle metadata used by live-data quality checks."""

    if not self._ws_enabled:
        return None
    sym = (symbol or "").upper()
    key = (sym, interval)
    with self._ws_lock:
        row = self._ws_kline_cache.get(key)
        return dict(row) if isinstance(row, dict) else None


def bind_binance_ws_runtime(wrapper_cls) -> None:
    wrapper_cls._use_live_futures_data_for_indicators = _use_live_futures_data_for_indicators
    wrapper_cls._live_futures_symbol_set = _live_futures_symbol_set
    wrapper_cls._symbol_available_on_live_futures = _symbol_available_on_live_futures
    wrapper_cls._ensure_ws_manager = _ensure_ws_manager
    wrapper_cls._ws_kline_handler = _ws_kline_handler
    wrapper_cls._ensure_ws_stream = _ensure_ws_stream
    wrapper_cls._ws_latest_candle = _ws_latest_candle
    wrapper_cls._ws_latest_candle_metadata = _ws_latest_candle_metadata
