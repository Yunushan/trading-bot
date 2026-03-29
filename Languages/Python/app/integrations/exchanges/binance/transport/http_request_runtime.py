from __future__ import annotations

import hashlib
import hmac
import time
import urllib.parse

import requests

from .helpers import (
    _http_debug_enabled,
    _http_slow_seconds,
    _is_binance_error_payload,
    _requests_timeout,
)


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


def _http_signed_futures_request(
    self,
    method: str,
    path: str,
    params: dict | None = None,
    *,
    timeout: tuple[float, float] | None = None,
    prefix: str | None = None,
):
    base = self._futures_base(prefix=prefix).rstrip("/")
    url = f"{base}/{path.lstrip('/')}"
    if not self.api_key or not self.api_secret:
        return {}
    timeout_pair = timeout or _requests_timeout()
    http_method = (method or "GET").strip().upper()
    for attempt in range(2):
        t0 = time.perf_counter()
        try:
            payload = dict(params or {})
            if "timestamp" not in payload:
                payload["timestamp"] = self._futures_timestamp_ms()
            if "recvWindow" not in payload:
                payload["recvWindow"] = int(getattr(self, "recv_window", 5000) or 5000)
            query = urllib.parse.urlencode(payload, doseq=True)
            sig = hmac.new((self.api_secret or "").encode(), query.encode(), hashlib.sha256).hexdigest()
            full_url = f"{url}?{query}&signature={sig}"
            resp = requests.request(
                http_method,
                full_url,
                headers={"X-MBX-APIKEY": self.api_key},
                timeout=timeout_pair,
            )
            if resp.status_code == 200:
                data = resp.json()
                if isinstance(data, dict) and _is_binance_error_payload(data):
                    err_code = None
                    try:
                        raw_code = data.get("code")
                        if raw_code is not None:
                            err_code = int(raw_code)
                    except Exception:
                        err_code = None
                    err_msg = str(data.get("msg") or data.get("message") or data)
                    if attempt == 0 and (err_code == -1021 or ("timestamp" in err_msg.lower())):
                        self._sync_futures_time_offset(force=True)
                        continue
                    self._record_futures_http_error(path, status_code=resp.status_code, code=err_code, message=err_msg)
                    return {}

                self._clear_futures_http_error()
                if _http_debug_enabled():
                    dt = time.perf_counter() - t0
                    if dt >= _http_slow_seconds():
                        try:
                            self._log(f"Futures REST {path} took {dt:.2f}s", lvl="warn")
                        except Exception:
                            pass
                return data if isinstance(data, (dict, list)) else {}

            err_code = None
            err_msg = None
            try:
                err = resp.json()
                if isinstance(err, dict):
                    raw_code = err.get("code")
                    if raw_code is not None:
                        try:
                            err_code = int(raw_code)
                        except Exception:
                            err_code = None
                    err_msg = str(err.get("msg") or err)
                else:
                    err_msg = str(err)
            except Exception:
                err_msg = (resp.text or "").strip() or f"http_status:{resp.status_code}"

            if attempt == 0 and (err_code == -1021 or ("timestamp" in (err_msg or "").lower())):
                self._sync_futures_time_offset(force=True)
                continue

            self._record_futures_http_error(path, status_code=resp.status_code, code=err_code, message=err_msg)
            return {}
        except requests.exceptions.RequestException as exc:
            self._record_futures_http_error(path, message=str(exc))
            return {}
        except Exception as exc:
            self._record_futures_http_error(path, message=str(exc))
            return {}


def _http_signed_futures(
    self,
    path: str,
    params: dict | None = None,
    *,
    timeout: tuple[float, float] | None = None,
    prefix: str | None = None,
) -> dict:
    base = self._futures_base(prefix=prefix).rstrip("/")
    url = f"{base}/{path.lstrip('/')}"
    if not self.api_key or not self.api_secret:
        return {}
    timeout_pair = timeout or _requests_timeout()
    for attempt in range(2):
        t0 = time.perf_counter()
        try:
            payload = dict(params or {})
            if "timestamp" not in payload:
                payload["timestamp"] = self._futures_timestamp_ms()
            if "recvWindow" not in payload:
                payload["recvWindow"] = int(getattr(self, "recv_window", 5000) or 5000)
            query = urllib.parse.urlencode(payload, doseq=True)
            sig = hmac.new((self.api_secret or "").encode(), query.encode(), hashlib.sha256).hexdigest()
            full_url = f"{url}?{query}&signature={sig}"
            resp = requests.get(full_url, headers={"X-MBX-APIKEY": self.api_key}, timeout=timeout_pair)
            if resp.status_code == 200:
                data = resp.json()
                if isinstance(data, dict) and _is_binance_error_payload(data):
                    err_code = None
                    try:
                        raw_code = data.get("code")
                        if raw_code is not None:
                            err_code = int(raw_code)
                    except Exception:
                        err_code = None
                    err_msg = str(data.get("msg") or data.get("message") or data)
                    if attempt == 0 and (err_code == -1021 or ("timestamp" in err_msg.lower())):
                        self._sync_futures_time_offset(force=True)
                        continue
                    self._record_futures_http_error(path, status_code=resp.status_code, code=err_code, message=err_msg)
                    return {}

                self._clear_futures_http_error()
                if _http_debug_enabled():
                    dt = time.perf_counter() - t0
                    if dt >= _http_slow_seconds():
                        try:
                            self._log(f"Futures REST {path} took {dt:.2f}s", lvl="warn")
                        except Exception:
                            pass
                return data if isinstance(data, dict) else {}

            err_code = None
            err_msg = None
            try:
                err = resp.json()
                if isinstance(err, dict):
                    raw_code = err.get("code")
                    if raw_code is not None:
                        try:
                            err_code = int(raw_code)
                        except Exception:
                            err_code = None
                    err_msg = str(err.get("msg") or err)
                else:
                    err_msg = str(err)
            except Exception:
                err_msg = (resp.text or "").strip() or f"http_status:{resp.status_code}"

            if attempt == 0 and (err_code == -1021 or ("timestamp" in (err_msg or "").lower())):
                self._sync_futures_time_offset(force=True)
                continue

            self._record_futures_http_error(path, status_code=resp.status_code, code=err_code, message=err_msg)
            return {}
        except requests.exceptions.RequestException as exc:
            self._record_futures_http_error(path, message=str(exc))
            return {}
        except Exception as exc:
            self._record_futures_http_error(path, message=str(exc))
            return {}


def _http_signed_futures_list(
    self,
    path: str,
    params: dict | None = None,
    *,
    timeout: tuple[float, float] | None = None,
    prefix: str | None = None,
) -> list:
    base = self._futures_base(prefix=prefix).rstrip("/")
    url = f"{base}/{path.lstrip('/')}"
    if not self.api_key or not self.api_secret:
        return []
    timeout_pair = timeout or _requests_timeout()
    for attempt in range(2):
        t0 = time.perf_counter()
        try:
            payload = dict(params or {})
            if "timestamp" not in payload:
                payload["timestamp"] = self._futures_timestamp_ms()
            if "recvWindow" not in payload:
                payload["recvWindow"] = int(getattr(self, "recv_window", 5000) or 5000)
            query = urllib.parse.urlencode(payload, doseq=True)
            sig = hmac.new((self.api_secret or "").encode(), query.encode(), hashlib.sha256).hexdigest()
            full_url = f"{url}?{query}&signature={sig}"
            resp = requests.get(full_url, headers={"X-MBX-APIKEY": self.api_key}, timeout=timeout_pair)
            if resp.status_code == 200:
                data = resp.json()
                if isinstance(data, dict) and _is_binance_error_payload(data):
                    err_code = None
                    try:
                        raw_code = data.get("code")
                        if raw_code is not None:
                            err_code = int(raw_code)
                    except Exception:
                        err_code = None
                    err_msg = str(data.get("msg") or data.get("message") or data)
                    if attempt == 0 and (err_code == -1021 or ("timestamp" in err_msg.lower())):
                        self._sync_futures_time_offset(force=True)
                        continue
                    self._record_futures_http_error(path, status_code=resp.status_code, code=err_code, message=err_msg)
                    return []

                self._clear_futures_http_error()
                if _http_debug_enabled():
                    dt = time.perf_counter() - t0
                    if dt >= _http_slow_seconds():
                        try:
                            self._log(f"Futures REST {path} took {dt:.2f}s", lvl="warn")
                        except Exception:
                            pass
                return data if isinstance(data, list) else []

            err_code = None
            err_msg = None
            try:
                err = resp.json()
                if isinstance(err, dict):
                    raw_code = err.get("code")
                    if raw_code is not None:
                        try:
                            err_code = int(raw_code)
                        except Exception:
                            err_code = None
                    err_msg = str(err.get("msg") or err)
                else:
                    err_msg = str(err)
            except Exception:
                err_msg = (resp.text or "").strip() or f"http_status:{resp.status_code}"

            if attempt == 0 and (err_code == -1021 or ("timestamp" in (err_msg or "").lower())):
                self._sync_futures_time_offset(force=True)
                continue

            self._record_futures_http_error(path, status_code=resp.status_code, code=err_code, message=err_msg)
            return []
        except requests.exceptions.RequestException as exc:
            self._record_futures_http_error(path, message=str(exc))
            return []
        except Exception as exc:
            self._record_futures_http_error(path, message=str(exc))
            return []
