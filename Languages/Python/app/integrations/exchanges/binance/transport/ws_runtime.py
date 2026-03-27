from __future__ import annotations

import time

import requests

from .helpers import _env_flag

try:
    from binance.streams import ThreadedWebsocketManager as _TWM
except Exception:
    _TWM = None


def _is_testnet_mode(mode: str | None) -> bool:
    text = str(mode or "").lower()
    return any(tag in text for tag in ("demo", "test", "sandbox"))


def _use_live_futures_data_for_indicators(self) -> bool:
    try:
        default_live = _is_testnet_mode(self.mode)
        return _env_flag("BINANCE_INDICATOR_LIVE_DATA", default_live)
    except Exception:
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
    except Exception:
        pass
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
    except Exception:
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
        except Exception:
            pass
        self._ws_twm = _TWM(
            api_key=self.api_key or "",
            api_secret=self.api_secret or "",
            futures=True,
            testnet=ws_testnet,
        )
        self._ws_twm.start()
    except Exception as exc:
        try:
            self._log(f"WebSocket manager init failed; disabling fast indicators ({exc})", lvl="warn")
        except Exception:
            pass
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
        row = {
            "open_time": open_time,
            "open": float(k.get("o") or 0.0),
            "high": float(k.get("h") or 0.0),
            "low": float(k.get("l") or 0.0),
            "close": float(k.get("c") or 0.0),
            "volume": float(k.get("v") or 0.0),
            "closed": bool(k.get("x") or False),
            "event_time": int(msg.get("E") or 0),
        }
        key = (sym, interval)
        with self._ws_lock:
            self._ws_kline_cache[key] = row
    except Exception:
        pass


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
    except Exception:
        try:
            self._log(f"WebSocket subscribe failed for {sym}@{interval}; continuing without WS.", lvl="warn")
        except Exception:
            pass


def _ws_latest_candle(self, symbol: str, interval: str):
    if not self._ws_enabled:
        return None
    sym = (symbol or "").upper()
    key = (sym, interval)
    with self._ws_lock:
        return self._ws_kline_cache.get(key)


def bind_binance_ws_runtime(wrapper_cls) -> None:
    wrapper_cls._use_live_futures_data_for_indicators = _use_live_futures_data_for_indicators
    wrapper_cls._live_futures_symbol_set = _live_futures_symbol_set
    wrapper_cls._symbol_available_on_live_futures = _symbol_available_on_live_futures
    wrapper_cls._ensure_ws_manager = _ensure_ws_manager
    wrapper_cls._ws_kline_handler = _ws_kline_handler
    wrapper_cls._ensure_ws_stream = _ensure_ws_stream
    wrapper_cls._ws_latest_candle = _ws_latest_candle
