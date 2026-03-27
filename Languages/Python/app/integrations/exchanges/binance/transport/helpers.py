from __future__ import annotations

import os
import threading
import time
from collections import deque
from typing import Any


def _coerce_interval_seconds(interval: str | None) -> float:
    try:
        iv = (interval or "").strip().lower()
        if not iv:
            return 60.0
        unit = iv[-1]
        value_part = iv[:-1] if unit.isalpha() else iv
        value = float(value_part or 0.0)
        if unit == "s":
            return max(value, 1.0)
        if unit == "m":
            return max(value * 60.0, 1.0)
        if unit == "h":
            return max(value * 3600.0, 1.0)
        if unit == "d":
            return max(value * 86400.0, 1.0)
        if unit == "w":
            return max(value * 7 * 86400.0, 1.0)
        return max(float(iv), 1.0)
    except Exception:
        return 60.0


def normalize_margin_ratio(value):
    """Convert Binance margin ratio payloads to percentage values."""
    try:
        if value is None:
            return 0.0
        if isinstance(value, str):
            txt = value.strip()
            if not txt:
                return 0.0
            if txt.endswith('%'):
                txt = txt[:-1]
            value = float(txt)
        else:
            value = float(value)
    except Exception:
        return 0.0
    if value <= 0.0:
        return 0.0
    return value * 100.0 if value <= 1.0 else value


def _coerce_int(value):
    try:
        if isinstance(value, str):
            value = value.strip()
            if not value:
                return 0
        if value is None:
            return 0
        return int(float(value))
    except Exception:
        return 0


def _maybe_float(value: Any) -> float | None:
    if value is None:
        return None
    try:
        return float(value)
    except Exception:
        return None


def _maybe_int(value: Any) -> int | None:
    if value is None:
        return None
    try:
        return int(value)
    except Exception:
        try:
            return int(float(value))
        except Exception:
            return None


def _env_flag(name: str, default: bool = False) -> bool:
    """
    Read a boolean-ish environment variable. Accepts 1/true/yes/on/live (case-insensitive).
    """
    val = os.getenv(name)
    if val is None or val == "":
        return bool(default)
    return str(val).strip().lower() in {"1", "true", "yes", "on", "live"}


def _env_float(name: str, default: float) -> float:
    """Read a float-ish environment variable with a safe fallback."""
    parsed = _maybe_float(os.getenv(name))
    return float(default) if parsed is None else float(parsed)


def _requests_timeout() -> tuple[float, float]:
    """
    Build a (connect, read) timeout tuple for requests/urllib3.

    Why tuple timeouts?
    - A single large timeout can make stalled connects/reads take minutes.
    - Separating connect vs read keeps the UI responsive while still allowing
      slower responses when needed.

    Environment variables:
    - BINANCE_HTTP_CONNECT_TIMEOUT (default: 5)
    - BINANCE_HTTP_READ_TIMEOUT    (default: BINANCE_HTTP_TIMEOUT or 20)
    - BINANCE_HTTP_TIMEOUT         (legacy read timeout; default: 20)
    """
    connect_timeout = _env_float("BINANCE_HTTP_CONNECT_TIMEOUT", 5.0)
    read_timeout = _env_float("BINANCE_HTTP_READ_TIMEOUT", _env_float("BINANCE_HTTP_TIMEOUT", 20.0))
    try:
        connect_timeout = float(connect_timeout)
    except Exception:
        connect_timeout = 5.0
    try:
        read_timeout = float(read_timeout)
    except Exception:
        read_timeout = 20.0
    connect_timeout = max(0.5, min(connect_timeout, 30.0))
    read_timeout = max(1.0, min(read_timeout, 60.0))
    return (connect_timeout, read_timeout)


def _auth_error_hint_for(mode: str | None, account_type: str | None, code: int | None) -> str | None:
    try:
        c = int(code) if code is not None else None
    except Exception:
        c = None
    if c not in {-2014, -2015}:
        return None
    mode_text = str(mode or "").lower()
    acct = str(account_type or "").upper()
    is_testnet = any(tag in mode_text for tag in ("demo", "test", "sandbox"))
    if acct.startswith("FUT") and is_testnet:
        return (
            "Use Binance FUTURES TESTNET keys from testnet.binancefuture.com "
            "(spot/live keys won't work). In the key settings, enable Futures/Reading permissions. "
            "If you enabled IP restriction, disable it or whitelist your current public IP (VPN changes it)."
        )
    if is_testnet:
        return "Testnet requires testnet API keys (live keys won't work)."
    if acct.startswith("FUT"):
        return "Ensure your API key has Futures permissions enabled and IP whitelist allows your current IP."
    return "Ensure your API key permissions and IP whitelist allow this request."


def _http_timeout_seconds() -> float:
    _, read_timeout = _requests_timeout()
    return float(read_timeout)


def _http_debug_enabled() -> bool:
    return _env_flag("BINANCE_DEBUG_HTTP", False) or _env_flag("BINANCE_DEBUG_HTTP_TIMING", False)


def _http_slow_seconds() -> float:
    try:
        return max(0.0, float(_env_float("BINANCE_DEBUG_HTTP_SLOW_SECONDS", 2.0)))
    except Exception:
        return 2.0


def _is_binance_error_payload(obj: Any) -> bool:
    """
    Detect Binance-style error payloads like {"code": -2015, "msg": "..."} that some
    connectors may surface as plain dicts instead of raising exceptions.
    """
    if not isinstance(obj, dict):
        return False
    if "code" not in obj:
        return False
    msg = obj.get("msg", obj.get("message"))
    if msg is None:
        return False
    try:
        code = int(obj.get("code"))
    except Exception:
        return False
    if code == 0:
        return False
    return True


def _as_futures_balance_entries(data: Any):
    if isinstance(data, dict):
        if _is_binance_error_payload(data):
            return []
        for key in ("balances", "accountBalance", "data"):
            entries = data.get(key)
            if entries is not None:
                return entries
        return []
    return data or []


def _as_futures_account_dict(data: Any) -> dict:
    if isinstance(data, dict):
        if _is_binance_error_payload(data):
            return {}
        return data
    if isinstance(data, list) and data:
        first = data[0]
        if isinstance(first, dict):
            if _is_binance_error_payload(first):
                return {}
            return first
    return {}


class _SimpleRateLimiter:
    def __init__(self, max_per_minute: float = 600.0, min_interval: float = 0.25, safety_margin: float = 0.85):
        self.window = 60.0
        self.capacity = max(1.0, float(max_per_minute) * float(safety_margin))
        self.min_interval = max(0.0, float(min_interval))
        self._events = deque()
        self._window_weight = 0.0
        self._lock = threading.Lock()
        self._last_request = 0.0
        self._pause_until = 0.0

    def acquire(self, weight: float = 1.0) -> None:
        weight = max(float(weight), 0.0)
        if weight == 0.0:
            return
        sleep_for = 0.0
        while True:
            with self._lock:
                now = time.time()
                while self._events and (now - self._events[0][0]) >= self.window:
                    _, old_weight = self._events.popleft()
                    self._window_weight = max(0.0, self._window_weight - old_weight)
                wait_interval = 0.0
                if self._last_request:
                    elapsed = now - self._last_request
                    if elapsed < self.min_interval:
                        wait_interval = self.min_interval - elapsed
                wait_capacity = 0.0
                projected = self._window_weight + weight
                if projected > self.capacity:
                    earliest = self._events[0][0] if self._events else now
                    wait_capacity = max(0.0, self.window - (now - earliest))
                pause_remaining = max(0.0, self._pause_until - now)
                sleep_for = max(wait_interval, wait_capacity, pause_remaining)
                if sleep_for <= 0.0:
                    self._events.append((now, weight))
                    self._window_weight = min(self.capacity, self._window_weight + weight)
                    self._last_request = now
                    return
            time.sleep(min(sleep_for, 1.0))

    def pause_for(self, seconds: float) -> None:
        seconds = float(seconds or 0.0)
        if seconds <= 0.0:
            return
        with self._lock:
            until = time.time() + seconds
            if until > self._pause_until:
                self._pause_until = until
