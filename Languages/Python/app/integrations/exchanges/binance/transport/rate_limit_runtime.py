from __future__ import annotations

import re
import time
import types

from .helpers import _SimpleRateLimiter


def _estimate_request_weight(path: str | None) -> float:
    if not path:
        return 1.0
    lower = str(path).lower()
    if "exchangeinfo" in lower:
        return 10.0
    if "balance" in lower or "account" in lower:
        return 5.0
    if "position" in lower:
        return 5.0
    if "klines" in lower:
        return 4.0
    if "ticker" in lower:
        return 1.0 if "price" in lower else 2.0
    if "margin" in lower or "leverage" in lower or "order" in lower:
        return 1.0
    return 2.0


def _throttle_request(self, path: str | None) -> None:
    limiter = getattr(self, "_request_limiter", None)
    if limiter is None:
        return
    try:
        weight = self._estimate_request_weight(path)
    except Exception:
        weight = 1.0
    try:
        limiter.acquire(weight)
    except Exception:
        pass


def _environment_tag(mode_value: str | None) -> str:
    text = str(mode_value or "").lower()
    return "testnet" if any(tag in text for tag in ("test", "demo")) else "live"


def _account_tag(account_value: str | None) -> str:
    text = str(account_value or "").upper()
    return "spot" if text.startswith("SPOT") else "futures"


def _limiter_settings_for(cls, env_tag: str, acct_tag: str) -> dict:
    if env_tag == "testnet":
        return {"max_per_minute": 180.0, "min_interval": 0.65, "safety_margin": 0.8}
    if acct_tag == "spot":
        return {"max_per_minute": 900.0, "min_interval": 0.25, "safety_margin": 0.85}
    return {"max_per_minute": 1100.0, "min_interval": 0.2, "safety_margin": 0.9}


def _acquire_rate_limiter(cls, key: str, settings: dict) -> _SimpleRateLimiter:
    with cls._limiter_lock:
        limiter = cls._limiter_pool.get(key)
        if limiter is None:
            limiter = _SimpleRateLimiter(
                max_per_minute=settings.get("max_per_minute", 600.0),
                min_interval=settings.get("min_interval", 0.25),
                safety_margin=settings.get("safety_margin", 0.85),
            )
            cls._limiter_pool[key] = limiter
        return limiter


def _ban_key(self) -> str:
    try:
        return getattr(self, "_limiter_key", None) or "global"
    except Exception:
        return "global"


def _install_request_throttler(self) -> None:
    client = getattr(self, "client", None)
    if not client or getattr(client, "_bw_throttled", False):
        return
    try:
        original = client._request
    except AttributeError:
        return

    def throttled(_self, method, path, signed=False, force_params=False, **kwargs):
        self._throttle_request(path)
        return original(method, path, signed=signed, force_params=force_params, **kwargs)

    try:
        client._request = types.MethodType(throttled, client)
        client._bw_throttled = True
    except Exception as exc:
        self._log(f"Failed to attach rate limiter: {exc}", lvl="warn")


def _register_ban_until(self, until_epoch: float | None) -> None:
    if not until_epoch or until_epoch != until_epoch:
        return
    key = self._ban_key()
    with self._ban_state_lock:
        current = self._ban_until_epoch.get(key, 0.0)
        if until_epoch > current:
            self._ban_until_epoch[key] = until_epoch


def _seconds_until_unban(self) -> float:
    key = self._ban_key()
    with self._ban_state_lock:
        until = self._ban_until_epoch.get(key, 0.0)
    remaining = until - time.time()
    return remaining if remaining > 0 else 0.0


def _extract_ban_until(message: str | None) -> float | None:
    if not message:
        return None
    match = re.search(r"banned until (\d+)", message)
    if match:
        raw = float(match.group(1))
        if raw > 1e12:
            return raw / 1000.0
        if raw > 1e5:
            return raw
    match = re.search(r"(?:after|wait)\s+(\d+)(?:ms| milliseconds)", message)
    if match:
        return time.time() + max(float(match.group(1)) / 1000.0, 0.0)
    match = re.search(r"(?:after|wait)\s+(\d+)(?:s| seconds)", message)
    if match:
        return time.time() + max(float(match.group(1)), 0.0)
    return None


def _handle_potential_ban(self, exc) -> float | None:
    try:
        code = getattr(exc, "code", None)
        status = getattr(exc, "status_code", None)
        msg = str(exc)
    except Exception:
        code, status, msg = None, None, ""
    triggered = False
    msg_lower = msg.lower() if isinstance(msg, str) else ""
    if code in (-1003, 429) or status in (418, 429):
        triggered = True
    elif msg_lower:
        if "banned until" in msg_lower or "too many requests" in msg_lower or "too frequent" in msg_lower or "frequency" in msg_lower:
            triggered = True
    if not triggered:
        return None
    until = self._extract_ban_until(msg)
    if until is None:
        retry_after = None
        try:
            response = getattr(exc, "response", None)
            if response is not None:
                retry_after = response.headers.get("Retry-After") or response.headers.get("retry-after")
        except Exception:
            retry_after = None
        if retry_after:
            try:
                until = time.time() + float(retry_after)
            except Exception:
                until = None
    if until is None:
        until = time.time() + 8.0
    self._register_ban_until(until)
    remaining = max(0.0, until - time.time())
    try:
        limiter = getattr(self, "_request_limiter", None)
        if limiter is not None:
            limiter.pause_for(remaining + 3.0)
    except Exception:
        pass
    return until


def bind_binance_rate_limit_runtime(wrapper_cls) -> None:
    wrapper_cls._estimate_request_weight = staticmethod(_estimate_request_weight)
    wrapper_cls._throttle_request = _throttle_request
    wrapper_cls._environment_tag = staticmethod(_environment_tag)
    wrapper_cls._account_tag = staticmethod(_account_tag)
    wrapper_cls._limiter_settings_for = classmethod(_limiter_settings_for)
    wrapper_cls._acquire_rate_limiter = classmethod(_acquire_rate_limiter)
    wrapper_cls._ban_key = _ban_key
    wrapper_cls._install_request_throttler = _install_request_throttler
    wrapper_cls._register_ban_until = _register_ban_until
    wrapper_cls._seconds_until_unban = _seconds_until_unban
    wrapper_cls._extract_ban_until = staticmethod(_extract_ban_until)
    wrapper_cls._handle_potential_ban = _handle_potential_ban
