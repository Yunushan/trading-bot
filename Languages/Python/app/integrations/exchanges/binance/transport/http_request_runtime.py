from __future__ import annotations

import hashlib
import hmac
import time
import urllib.parse
from typing import Any

import requests

from .helpers import (
    _http_debug_enabled,
    _http_slow_seconds,
    _is_binance_error_payload,
    _requests_timeout,
)


_FUTURES_HTTP_MAX_ATTEMPTS = 2
_RATE_LIMIT_HTTP_STATUSES = {418, 429}
_RATE_LIMIT_ERROR_CODES = {-1003, 429}
_RETRYABLE_HTTP_STATUSES = {408, 425, 500, 502, 503, 504}
_RETRYABLE_ERROR_CODES = {-1001, -1006, -1007, -1008, -1016}


def _http_signed_spot(
    self,
    path: str,
    params: dict | None = None,
    *,
    timeout: float | tuple[float, float] | None = None,
) -> dict:
    base = self._spot_base().rstrip("/")
    url = f"{base}/{path.lstrip('/')}"
    if not self.api_key or not self.api_secret:
        return {}
    try:
        timeout_val = timeout or _requests_timeout()
        payload = dict(params or {})
        if "timestamp" not in payload:
            payload["timestamp"] = int(time.time() * 1000)
        if "recvWindow" not in payload:
            payload["recvWindow"] = 5000
        query = urllib.parse.urlencode(payload)
        sig = hmac.new((self.api_secret or "").encode(), query.encode(), hashlib.sha256).hexdigest()
        full_params = dict(payload)
        full_params["signature"] = sig
        resp = requests.get(url, params=full_params, headers={"X-MBX-APIKEY": self.api_key}, timeout=timeout_val)
        resp.raise_for_status()
        data = resp.json()
        return data if isinstance(data, dict) else {}
    except Exception:
        return {}


def _http_signed_spot_list(
    self,
    path: str,
    params: dict | None = None,
    *,
    timeout: float | tuple[float, float] | None = None,
) -> list:
    base = self._spot_base().rstrip("/")
    url = f"{base}/{path.lstrip('/')}"
    if not self.api_key or not self.api_secret:
        return []
    try:
        timeout_val = timeout or _requests_timeout()
        payload = dict(params or {})
        if "timestamp" not in payload:
            payload["timestamp"] = int(time.time() * 1000)
        if "recvWindow" not in payload:
            payload["recvWindow"] = 5000
        query = urllib.parse.urlencode(payload)
        sig = hmac.new((self.api_secret or "").encode(), query.encode(), hashlib.sha256).hexdigest()
        full_params = dict(payload)
        full_params["signature"] = sig
        resp = requests.get(url, params=full_params, headers={"X-MBX-APIKEY": self.api_key}, timeout=timeout_val)
        resp.raise_for_status()
        data = resp.json()
        return data if isinstance(data, list) else []
    except Exception:
        return []


def _coerce_error_code(value: Any) -> int | None:
    try:
        if value is None:
            return None
        return int(value)
    except Exception:
        try:
            return int(float(value))
        except Exception:
            return None


def _parse_futures_error_response(resp: Any) -> tuple[int | None, str]:
    try:
        payload = resp.json()
        if isinstance(payload, dict):
            code = _coerce_error_code(payload.get("code"))
            return code, str(payload.get("msg") or payload.get("message") or payload)
        return None, str(payload)
    except Exception:
        try:
            text = (getattr(resp, "text", "") or "").strip()
        except Exception:
            text = ""
        try:
            status_code = int(getattr(resp, "status_code", 0) or 0)
        except Exception:
            status_code = 0
        return None, text or f"http_status:{status_code}"


def _response_retry_after(resp: Any) -> float | None:
    try:
        headers = getattr(resp, "headers", None) or {}
        retry_after = headers.get("Retry-After") or headers.get("retry-after")
        if retry_after in (None, ""):
            return None
        return max(float(retry_after), 0.0)
    except Exception:
        return None


def _is_timestamp_error(code: int | None, message: str | None) -> bool:
    return code == -1021 or "timestamp" in str(message or "").lower()


def _is_rate_limit_error(status_code: int | None, code: int | None, message: str | None) -> bool:
    msg_lower = str(message or "").lower()
    return (
        status_code in _RATE_LIMIT_HTTP_STATUSES
        or code in _RATE_LIMIT_ERROR_CODES
        or "banned until" in msg_lower
        or "too many requests" in msg_lower
        or "too frequent" in msg_lower
        or "rate limit" in msg_lower
    )


def _is_retryable_exchange_error(status_code: int | None, code: int | None, message: str | None) -> bool:
    if _is_rate_limit_error(status_code, code, message):
        return True
    return status_code in _RETRYABLE_HTTP_STATUSES or code in _RETRYABLE_ERROR_CODES


def _is_retryable_request_exception(exc: BaseException) -> bool:
    return isinstance(exc, (requests.exceptions.Timeout, requests.exceptions.ConnectionError))


def _futures_error_category(
    *,
    status_code: int | None = None,
    code: int | None = None,
    message: str | None = None,
    exc: BaseException | None = None,
) -> str:
    if _is_timestamp_error(code, message):
        return "timestamp"
    if _is_rate_limit_error(status_code, code, message):
        return "rate_limited"
    if exc is not None:
        return "network" if _is_retryable_request_exception(exc) else "request"
    if status_code in _RETRYABLE_HTTP_STATUSES or code in _RETRYABLE_ERROR_CODES:
        return "exchange_unavailable"
    if status_code in (401, 403) or code in (-2014, -2015):
        return "auth"
    if status_code is not None:
        return "exchange_http"
    return "unexpected"


def _record_direct_futures_http_error(
    self,
    path: str | None,
    *,
    status_code: int | None = None,
    code: int | None = None,
    message: str | None = None,
    category: str | None = None,
    retryable: bool | None = None,
    attempt: int | None = None,
    max_attempts: int | None = None,
    method: str | None = None,
    retry_after: float | None = None,
    ban_until: float | None = None,
) -> None:
    recorder = getattr(self, "_record_futures_http_error", None)
    if not callable(recorder):
        return
    try:
        recorder(
            path,
            status_code=status_code,
            code=code,
            message=message,
            category=category,
            retryable=retryable,
            attempt=attempt,
            max_attempts=max_attempts,
            method=method,
            retry_after=retry_after,
            ban_until=ban_until,
        )
    except TypeError:
        try:
            recorder(path, status_code=status_code, code=code, message=message)
        except Exception:
            pass
    except Exception:
        pass


def _handle_direct_futures_rate_limit(
    self,
    *,
    status_code: int | None,
    code: int | None,
    message: str | None,
    retry_after: float | None,
) -> float | None:
    handler = getattr(self, "_apply_http_backoff", None)
    if callable(handler):
        try:
            return handler(status_code=status_code, code=code, message=message, retry_after=retry_after)
        except Exception:
            return None
    return None


def _seconds_until_direct_futures_request_allowed(self) -> float:
    checker = getattr(self, "_seconds_until_unban", None)
    if not callable(checker):
        return 0.0
    try:
        return max(float(checker() or 0.0), 0.0)
    except Exception:
        return 0.0


def _throttle_direct_futures_request(self, path: str | None) -> None:
    throttler = getattr(self, "_throttle_request", None)
    if callable(throttler):
        try:
            throttler(path)
        except Exception:
            pass


def _mark_direct_futures_network_offline(self, path: str, exc: Exception) -> None:
    handler = getattr(self, "_handle_network_offline", None)
    if callable(handler):
        try:
            handler(f"Binance futures REST {path}", exc)
        except Exception:
            pass


def _mark_direct_futures_network_recovered(self) -> None:
    handler = getattr(self, "_handle_network_recovered", None)
    if callable(handler):
        try:
            handler()
        except Exception:
            pass


def _sleep_before_futures_retry(attempt: int) -> None:
    try:
        time.sleep(min(0.25 * (attempt + 1), 1.0))
    except Exception:
        pass


def _empty_futures_http_result(response_kind: str) -> dict | list:
    return [] if response_kind == "list" else {}


def _coerce_futures_http_result(data: Any, response_kind: str) -> dict | list:
    if response_kind == "list":
        return data if isinstance(data, list) else []
    if response_kind == "any":
        return data if isinstance(data, (dict, list)) else {}
    return data if isinstance(data, dict) else {}


def _signed_futures_url(self, base_url: str, params: dict | None) -> str:
    payload = dict(params or {})
    if "timestamp" not in payload:
        payload["timestamp"] = self._futures_timestamp_ms()
    if "recvWindow" not in payload:
        payload["recvWindow"] = int(getattr(self, "recv_window", 5000) or 5000)
    query = urllib.parse.urlencode(payload, doseq=True)
    signature = hmac.new((self.api_secret or "").encode(), query.encode(), hashlib.sha256).hexdigest()
    return f"{base_url}?{query}&signature={signature}"


def _http_signed_futures_impl(
    self,
    method: str,
    path: str,
    params: dict | None,
    *,
    timeout: tuple[float, float] | None,
    prefix: str | None,
    response_kind: str,
) -> dict | list:
    base = self._futures_base(prefix=prefix).rstrip("/")
    url = f"{base}/{path.lstrip('/')}"
    if not self.api_key or not self.api_secret:
        return _empty_futures_http_result(response_kind)
    timeout_pair = timeout or _requests_timeout()
    http_method = (method or "GET").strip().upper()
    max_attempts = _FUTURES_HTTP_MAX_ATTEMPTS

    for attempt in range(max_attempts):
        allowed_after = _seconds_until_direct_futures_request_allowed(self)
        if allowed_after > 0.0:
            ban_until = time.time() + allowed_after
            _record_direct_futures_http_error(
                self,
                path,
                message=f"rate limit cooldown active; retry after {allowed_after:.1f}s",
                category="rate_limited",
                retryable=True,
                attempt=attempt + 1,
                max_attempts=max_attempts,
                method=http_method,
                retry_after=allowed_after,
                ban_until=ban_until,
            )
            return _empty_futures_http_result(response_kind)

        _throttle_direct_futures_request(self, path)
        t0 = time.perf_counter()
        try:
            resp = requests.request(
                http_method,
                _signed_futures_url(self, url, params),
                headers={"X-MBX-APIKEY": self.api_key},
                timeout=timeout_pair,
            )
        except requests.exceptions.RequestException as exc:
            _mark_direct_futures_network_offline(self, path, exc)
            retryable = _is_retryable_request_exception(exc)
            if retryable and attempt < max_attempts - 1:
                _sleep_before_futures_retry(attempt)
                continue
            _record_direct_futures_http_error(
                self,
                path,
                message=str(exc),
                category=_futures_error_category(exc=exc),
                retryable=retryable,
                attempt=attempt + 1,
                max_attempts=max_attempts,
                method=http_method,
            )
            return _empty_futures_http_result(response_kind)
        except Exception as exc:
            _record_direct_futures_http_error(
                self,
                path,
                message=str(exc),
                category="unexpected",
                retryable=False,
                attempt=attempt + 1,
                max_attempts=max_attempts,
                method=http_method,
            )
            return _empty_futures_http_result(response_kind)

        try:
            status_code = int(getattr(resp, "status_code", 0) or 0)
        except Exception:
            status_code = 0

        if status_code == 200:
            try:
                data = resp.json()
            except Exception as exc:
                _record_direct_futures_http_error(
                    self,
                    path,
                    status_code=status_code,
                    message=str(exc),
                    category="decode",
                    retryable=False,
                    attempt=attempt + 1,
                    max_attempts=max_attempts,
                    method=http_method,
                )
                return _empty_futures_http_result(response_kind)

            if isinstance(data, dict) and _is_binance_error_payload(data):
                err_code = _coerce_error_code(data.get("code"))
                err_msg = str(data.get("msg") or data.get("message") or data)
                if attempt < max_attempts - 1 and _is_timestamp_error(err_code, err_msg):
                    self._sync_futures_time_offset(force=True)
                    continue
                category = _futures_error_category(status_code=status_code, code=err_code, message=err_msg)
                retryable = _is_retryable_exchange_error(status_code, err_code, err_msg)
                rate_limited = _is_rate_limit_error(status_code, err_code, err_msg)
                ban_until = None
                if rate_limited:
                    ban_until = _handle_direct_futures_rate_limit(
                        self,
                        status_code=status_code,
                        code=err_code,
                        message=err_msg,
                        retry_after=None,
                    )
                elif retryable and attempt < max_attempts - 1:
                    _sleep_before_futures_retry(attempt)
                    continue
                _record_direct_futures_http_error(
                    self,
                    path,
                    status_code=status_code,
                    code=err_code,
                    message=err_msg,
                    category=category,
                    retryable=retryable,
                    attempt=attempt + 1,
                    max_attempts=max_attempts,
                    method=http_method,
                    ban_until=ban_until,
                )
                return _empty_futures_http_result(response_kind)

            self._clear_futures_http_error()
            _mark_direct_futures_network_recovered(self)
            if _http_debug_enabled():
                dt = time.perf_counter() - t0
                if dt >= _http_slow_seconds():
                    try:
                        self._log(f"Futures REST {path} took {dt:.2f}s", lvl="warn")
                    except Exception:
                        pass
            return _coerce_futures_http_result(data, response_kind)

        err_code, err_msg = _parse_futures_error_response(resp)
        if attempt < max_attempts - 1 and _is_timestamp_error(err_code, err_msg):
            self._sync_futures_time_offset(force=True)
            continue

        retry_after = _response_retry_after(resp)
        category = _futures_error_category(status_code=status_code, code=err_code, message=err_msg)
        retryable = _is_retryable_exchange_error(status_code, err_code, err_msg)
        rate_limited = _is_rate_limit_error(status_code, err_code, err_msg)
        ban_until = None
        if rate_limited:
            ban_until = _handle_direct_futures_rate_limit(
                self,
                status_code=status_code,
                code=err_code,
                message=err_msg,
                retry_after=retry_after,
            )
        elif retryable and attempt < max_attempts - 1:
            _sleep_before_futures_retry(attempt)
            continue

        _record_direct_futures_http_error(
            self,
            path,
            status_code=status_code,
            code=err_code,
            message=err_msg,
            category=category,
            retryable=retryable,
            attempt=attempt + 1,
            max_attempts=max_attempts,
            method=http_method,
            retry_after=retry_after,
            ban_until=ban_until,
        )
        return _empty_futures_http_result(response_kind)

    return _empty_futures_http_result(response_kind)


def _http_signed_futures_request(
    self,
    method: str,
    path: str,
    params: dict | None = None,
    *,
    timeout: tuple[float, float] | None = None,
    prefix: str | None = None,
):
    return _http_signed_futures_impl(
        self,
        method,
        path,
        params,
        timeout=timeout,
        prefix=prefix,
        response_kind="any",
    )


def _http_signed_futures(
    self,
    path: str,
    params: dict | None = None,
    *,
    timeout: tuple[float, float] | None = None,
    prefix: str | None = None,
) -> dict:
    result = _http_signed_futures_impl(
        self,
        "GET",
        path,
        params,
        timeout=timeout,
        prefix=prefix,
        response_kind="dict",
    )
    return result if isinstance(result, dict) else {}


def _http_signed_futures_list(
    self,
    path: str,
    params: dict | None = None,
    *,
    timeout: tuple[float, float] | None = None,
    prefix: str | None = None,
) -> list:
    result = _http_signed_futures_impl(
        self,
        "GET",
        path,
        params,
        timeout=timeout,
        prefix=prefix,
        response_kind="list",
    )
    return result if isinstance(result, list) else []
