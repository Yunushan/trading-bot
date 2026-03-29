from __future__ import annotations

import time

import requests

from .helpers import _requests_timeout
from .http_base_runtime import _is_testnet_mode


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
