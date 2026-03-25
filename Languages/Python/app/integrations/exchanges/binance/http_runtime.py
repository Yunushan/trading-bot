from __future__ import annotations

import hashlib
import hmac
import time
import urllib.parse

import requests

from .transport_helpers import (
    _http_debug_enabled,
    _http_slow_seconds,
    _is_binance_error_payload,
    _requests_timeout,
)


def _is_testnet_mode(mode: str | None) -> bool:
    text = str(mode or "").lower()
    return any(tag in text for tag in ("demo", "test", "sandbox"))


def _spot_base(self) -> str:
    return "https://testnet.binance.vision/api" if _is_testnet_mode(self.mode) else "https://api.binance.com/api"


def _normalize_futures_prefix(self, prefix: str | None) -> str | None:
    text = str(prefix or "").strip().lower()
    if not text:
        return None
    if not text.startswith("/"):
        text = f"/{text}"
    if text in {"/fapi", "/dapi"}:
        return text
    return None


def _futures_api_prefix(self) -> str:
    override = self._normalize_futures_prefix(getattr(self, "_futures_api_prefix_override", None))
    if override:
        return override
    client = getattr(self, "client", None)
    for attr in ("_api_prefix", "api_prefix", "API_PREFIX"):
        try:
            candidate = self._normalize_futures_prefix(getattr(client, attr, None))
        except Exception:
            candidate = None
        if candidate:
            return candidate
    backend = str(getattr(self, "_connector_backend", "") or "").lower()
    if "coin" in backend and "future" in backend:
        return "/dapi"
    return "/fapi"


def _alternate_futures_prefix(self, prefix: str | None = None) -> str | None:
    current = self._normalize_futures_prefix(prefix) or self._futures_api_prefix()
    if current == "/fapi":
        return "/dapi"
    if current == "/dapi":
        return "/fapi"
    return None


def _futures_base(self, prefix: str | None = None) -> str:
    api_prefix = self._normalize_futures_prefix(prefix) or self._futures_api_prefix()
    if _is_testnet_mode(self.mode):
        host = "https://testnet.binancefuture.com"
    else:
        host = "https://dapi.binance.com" if api_prefix == "/dapi" else "https://fapi.binance.com"
    base = host.rstrip("/")
    if base.endswith(api_prefix):
        return base
    return f"{base}{api_prefix}"


def _futures_base_live(self, prefix: str | None = None) -> str:
    api_prefix = self._normalize_futures_prefix(prefix) or self._futures_api_prefix()
    host = "https://dapi.binance.com" if api_prefix == "/dapi" else "https://fapi.binance.com"
    return f"{host}{api_prefix}"


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


def _record_futures_http_error(
    self,
    path: str | None,
    *,
    status_code: int | None = None,
    code: int | None = None,
    message: str | None = None,
) -> None:
    try:
        base_url = None
        try:
            base_url = str(self._futures_base() or "")
        except Exception:
            base_url = None
        self._last_futures_http_error = {
            "ts": time.time(),
            "path": str(path or ""),
            "base": base_url,
            "status_code": int(status_code) if status_code is not None else None,
            "code": int(code) if code is not None else None,
            "message": str(message or ""),
        }
    except Exception:
        pass


def _clear_futures_http_error(self) -> None:
    try:
        self._last_futures_http_error = None
    except Exception:
        pass


def _diagnose_testnet_key_scope(self) -> str | None:
    try:
        if not _is_testnet_mode(self.mode) or not (self.api_key and self.api_secret):
            return None
    except Exception:
        return None
    try:
        now = time.time()
        ts = float(getattr(self, "_testnet_key_scope_ts", 0.0) or 0.0)
        cached = getattr(self, "_testnet_key_scope", None)
        if cached and ts and (now - ts) < 600.0:
            return str(cached)
    except Exception:
        pass
    scope = None
    try:
        acct = self._http_signed_spot("/v3/account", timeout=_requests_timeout()) or {}
        if isinstance(acct, dict) and "balances" in acct:
            scope = "spot"
    except Exception:
        scope = None
    try:
        self._testnet_key_scope = scope
        self._testnet_key_scope_ts = time.time() if scope else 0.0
    except Exception:
        pass
    return scope


def _probe_testnet_key_acceptance(self) -> dict | None:
    try:
        if not _is_testnet_mode(self.mode) or not self.api_key:
            return None
    except Exception:
        return None
    try:
        now = time.time()
        ts = float(getattr(self, "_testnet_key_probe_ts", 0.0) or 0.0)
        cached = getattr(self, "_testnet_key_probe", None)
        if isinstance(cached, dict) and ts and (now - ts) < 600.0:
            return dict(cached)
    except Exception:
        cached = None

    def _probe(method: str, url: str) -> tuple[bool, int | None, int | None, str | None]:
        try:
            resp = requests.request(
                method,
                url,
                headers={"X-MBX-APIKEY": self.api_key},
                timeout=_requests_timeout(),
            )
            if resp.status_code == 200:
                return True, 200, None, None
            code = None
            msg = None
            try:
                payload = resp.json()
                if isinstance(payload, dict):
                    raw = payload.get("code")
                    if raw is not None:
                        try:
                            code = int(raw)
                        except Exception:
                            code = None
                    msg = str(payload.get("msg") or payload.get("message") or payload)
                else:
                    msg = str(payload)
            except Exception:
                msg = (resp.text or "").strip() or f"http_status:{resp.status_code}"
            return False, int(resp.status_code), code, msg
        except Exception as exc:
            return False, None, None, str(exc)

    spot_ok = False
    futures_ok = False
    spot_http = spot_code = None
    futures_http = futures_code = None
    spot_msg = futures_msg = None
    try:
        spot_url = f"{self._spot_base().rstrip('/')}/v3/userDataStream"
        spot_ok, spot_http, spot_code, spot_msg = _probe("POST", spot_url)
    except Exception:
        pass
    try:
        fut_url = f"{self._futures_base().rstrip('/')}/v1/listenKey"
        futures_ok, futures_http, futures_code, futures_msg = _probe("POST", fut_url)
    except Exception:
        pass

    result = {
        "spot_ok": bool(spot_ok),
        "spot_http": spot_http,
        "spot_code": spot_code,
        "spot_msg": spot_msg,
        "futures_ok": bool(futures_ok),
        "futures_http": futures_http,
        "futures_code": futures_code,
        "futures_msg": futures_msg,
    }
    try:
        self._testnet_key_probe = dict(result)
        self._testnet_key_probe_ts = time.time()
    except Exception:
        pass
    return dict(result)


def _testnet_auth_hint(self, code: int | None) -> str | None:
    try:
        c = int(code) if code is not None else None
    except Exception:
        c = None
    if c not in (-2014, -2015):
        return None
    if not _is_testnet_mode(self.mode):
        return None
    try:
        probe = self._probe_testnet_key_acceptance()
    except Exception:
        probe = None
    if not isinstance(probe, dict):
        return None
    spot_ok = bool(probe.get("spot_ok"))
    futures_ok = bool(probe.get("futures_ok"))
    try:
        spot_http = probe.get("spot_http")
        spot_code = probe.get("spot_code")
        futures_http = probe.get("futures_http")
        futures_code = probe.get("futures_code")
        probe_summary = (
            f"probe spot_ok={spot_ok} http={spot_http} code={spot_code} | "
            f"futures_ok={futures_ok} http={futures_http} code={futures_code}"
        )
    except Exception:
        probe_summary = None
    if probe_summary:
        probe_summary = f"{probe_summary}. "
    else:
        probe_summary = ""
    if spot_ok and not futures_ok:
        fut_http = probe.get("futures_http")
        fut_code = probe.get("futures_code")
        if fut_http == 401 and fut_code in (-2014, -2015):
            return (
                f"{probe_summary}"
                "These keys are accepted on Spot Testnet but rejected on Futures Testnet; "
                "use FUTURES Testnet keys from testnet.binancefuture.com."
            )
        if fut_http in (408, 504) or fut_code in (-1007,):
            return (
                f"{probe_summary}"
                "Spot Testnet accepts this API key, but the Futures Testnet probe timed out/unreachable; "
                "if you are running Futures Testnet, ensure you use FUTURES Testnet keys (and check network/DNS)."
            )
        return (
            f"{probe_summary}"
            "Spot Testnet accepts this API key, but the Futures Testnet probe failed; "
            "if you are running Futures Testnet, ensure you use FUTURES Testnet keys from testnet.binancefuture.com "
            "and check permissions/IP whitelist."
        )
    if futures_ok and not spot_ok:
        return (
            f"{probe_summary}"
            "API key is accepted by Futures Testnet; check Futures/Reading permissions and IP whitelist (VPN changes it)."
        )
    if not spot_ok and not futures_ok:
        return (
            f"{probe_summary}"
            "API key is rejected by both Spot/Futures Testnet; likely wrong key type/environment or IP restriction/permissions."
        )
    return None


def _sync_futures_time_offset(self, *, force: bool = False) -> None:
    now = time.time()
    last = float(getattr(self, "_futures_time_offset_ts", 0.0) or 0.0)
    if not force and last and (now - last) < 1800.0:
        return
    try:
        base = self._futures_base().rstrip("/")
        url = f"{base}/v1/time"
        resp = requests.get(url, timeout=_requests_timeout())
        if resp.status_code != 200:
            return
        data = resp.json() or {}
        server_time = int(float(data.get("serverTime") or 0))
        if server_time <= 0:
            return
        local_ms = int(time.time() * 1000)
        offset_ms = int(server_time - local_ms)
        self._futures_time_offset_ms = offset_ms
        self._futures_time_offset_ts = now
        try:
            client = getattr(self, "client", None)
            if client is not None and hasattr(client, "timestamp_offset"):
                setattr(client, "timestamp_offset", offset_ms)
        except Exception:
            pass
        try:
            fb = getattr(self, "_fallback_py_client", None)
            if fb is not None and hasattr(fb, "timestamp_offset"):
                setattr(fb, "timestamp_offset", offset_ms)
        except Exception:
            pass
    except Exception:
        return


def _futures_timestamp_ms(self) -> int:
    try:
        if not float(getattr(self, "_futures_time_offset_ts", 0.0) or 0.0):
            self._sync_futures_time_offset(force=False)
    except Exception:
        pass
    try:
        offset = int(getattr(self, "_futures_time_offset_ms", 0) or 0)
    except Exception:
        offset = 0
    return int(time.time() * 1000 + offset)


def _futures_call(self, method_name: str, allow_recv=True, **kwargs):
    try:
        api_prefix = self._futures_api_prefix()
        self._throttle_request(f"{api_prefix}/{method_name}")
    except Exception:
        pass
    method = getattr(self.client, method_name)
    if allow_recv:
        try:
            return method(recvWindow=self.recv_window, **kwargs)
        except TypeError:
            pass
    return method(**kwargs)


def futures_api_ok(self) -> tuple[bool, str | None]:
    try:
        _ = self._futures_call("futures_account_balance", allow_recv=True)
        return True, None
    except Exception as exc:
        return False, str(exc)


def spot_api_ok(self) -> tuple[bool, str | None]:
    try:
        _ = self.client.get_account()
        return True, None
    except Exception as exc:
        return False, str(exc)


def bind_binance_http_runtime(wrapper_cls) -> None:
    wrapper_cls._spot_base = _spot_base
    wrapper_cls._normalize_futures_prefix = _normalize_futures_prefix
    wrapper_cls._futures_api_prefix = _futures_api_prefix
    wrapper_cls._alternate_futures_prefix = _alternate_futures_prefix
    wrapper_cls._futures_base = _futures_base
    wrapper_cls._futures_base_live = _futures_base_live
    wrapper_cls._http_signed_spot = _http_signed_spot
    wrapper_cls._http_signed_spot_list = _http_signed_spot_list
    wrapper_cls._http_signed_futures_request = _http_signed_futures_request
    wrapper_cls._http_signed_futures = _http_signed_futures
    wrapper_cls._http_signed_futures_list = _http_signed_futures_list
    wrapper_cls._record_futures_http_error = _record_futures_http_error
    wrapper_cls._clear_futures_http_error = _clear_futures_http_error
    wrapper_cls._diagnose_testnet_key_scope = _diagnose_testnet_key_scope
    wrapper_cls._probe_testnet_key_acceptance = _probe_testnet_key_acceptance
    wrapper_cls._testnet_auth_hint = _testnet_auth_hint
    wrapper_cls._sync_futures_time_offset = _sync_futures_time_offset
    wrapper_cls._futures_timestamp_ms = _futures_timestamp_ms
    wrapper_cls._futures_call = _futures_call
    wrapper_cls.futures_api_ok = futures_api_ok
    wrapper_cls.spot_api_ok = spot_api_ok
