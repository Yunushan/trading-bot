from __future__ import annotations

import copy
import time

from ..transport.helpers import _as_futures_account_dict, _as_futures_balance_entries


def _is_testnet_mode(mode: str | None) -> bool:
    text = str(mode or "").lower()
    return any(tag in text for tag in ("demo", "test", "sandbox"))


def _invalidate_futures_account_cache(self) -> None:
    with self._futures_account_cache_lock:
        self._futures_account_cache = None
        self._futures_account_cache_ts = 0.0
        self._futures_account_balance_cache = None
        self._futures_account_balance_cache_ts = 0.0


def _fallback_futures_account(self) -> dict:
    try:
        if hasattr(self.client, "futures_account"):
            return self._futures_call("futures_account", allow_recv=True) or {}
    except Exception as exc:
        self._record_futures_http_error("/v2/account", message=str(exc))
    return {}


def _fallback_futures_balance(self) -> list:
    try:
        if hasattr(self.client, "futures_account_balance"):
            data = self._futures_call("futures_account_balance", allow_recv=True) or []
            return list(_as_futures_balance_entries(data))
    except Exception as exc:
        self._record_futures_http_error("/v2/balance", message=str(exc))
    return []


def _try_alt_futures_prefix_on_auth_error(self, path: str, *, list_mode: bool = False):
    if not _is_testnet_mode(self.mode):
        return None
    err = getattr(self, "_last_futures_http_error", None)
    if not isinstance(err, dict):
        return None
    if str(err.get("path") or "") != str(path):
        return None
    code = err.get("code")
    if code not in (-2014, -2015):
        return None
    alt_prefix = self._alternate_futures_prefix()
    if not alt_prefix:
        return None
    try:
        current_override = getattr(self, "_futures_api_prefix_override", None)
    except Exception:
        current_override = None
    if current_override == alt_prefix:
        return None
    err_snapshot = dict(err)
    alt_path = str(path)
    tail = alt_path.rsplit("/", 1)[-1]
    if tail in {"account", "balance"}:
        if alt_prefix == "/dapi" and alt_path.startswith(("/v2/", "/v3/")):
            alt_path = f"/v1/{tail}"
        elif alt_prefix == "/fapi" and alt_path.startswith("/v1/"):
            alt_path = f"/v2/{tail}"
    if list_mode:
        data = self._http_signed_futures_list(alt_path, prefix=alt_prefix)
    else:
        data = self._http_signed_futures(alt_path, prefix=alt_prefix)
    if data:
        self._futures_api_prefix_override = alt_prefix
        return data
    try:
        self._last_futures_http_error = err_snapshot
    except Exception:
        pass
    return None


def _get_futures_account_cached(self, max_age: float = 2.5, *, force_refresh: bool = False) -> dict:
    now = time.time()
    if not force_refresh:
        with self._futures_account_cache_lock:
            if (
                self._futures_account_cache is not None
                and (now - self._futures_account_cache_ts) < max(0.0, float(max_age or 0.0))
            ):
                return copy.deepcopy(self._futures_account_cache)
    acct_dict = {}
    try:
        if not self.api_key or not self.api_secret:
            acct_dict = {}
        else:
            api_prefix = self._futures_api_prefix()
            acct_path = "/v1/account" if api_prefix == "/dapi" else "/v2/account"
            acct = self._http_signed_futures(acct_path)
            acct_dict = _as_futures_account_dict(acct)
            if not acct_dict:
                alt = self._try_alt_futures_prefix_on_auth_error(acct_path)
                if alt:
                    acct_dict = _as_futures_account_dict(alt)
            if not acct_dict and api_prefix != "/dapi":
                acct = self._http_signed_futures("/v3/account")
                acct_dict = _as_futures_account_dict(acct)
                if not acct_dict:
                    alt = self._try_alt_futures_prefix_on_auth_error("/v3/account")
                    if alt:
                        acct_dict = _as_futures_account_dict(alt)
            if not acct_dict:
                acct_dict = _as_futures_account_dict(self._fallback_futures_account())
    except Exception:
        acct_dict = {}
    with self._futures_account_cache_lock:
        if acct_dict:
            self._futures_account_cache = copy.deepcopy(acct_dict)
            self._futures_account_cache_ts = time.time()
        elif force_refresh:
            self._futures_account_cache = None
            self._futures_account_cache_ts = 0.0
    return copy.deepcopy(acct_dict) if acct_dict else {}


def _get_futures_account_balance_cached(self, max_age: float = 2.5, *, force_refresh: bool = False) -> list:
    now = time.time()
    if not force_refresh:
        with self._futures_account_cache_lock:
            if (
                self._futures_account_balance_cache is not None
                and (now - self._futures_account_balance_cache_ts) < max(0.0, float(max_age or 0.0))
            ):
                return copy.deepcopy(self._futures_account_balance_cache)
    entries: list = []
    try:
        if not self.api_key or not self.api_secret:
            entries = []
        else:
            api_prefix = self._futures_api_prefix()
            balance_path = "/v1/balance" if api_prefix == "/dapi" else "/v2/balance"
            bals = self._http_signed_futures_list(balance_path)
            entries = list(_as_futures_balance_entries(bals))
            if not entries:
                alt = self._try_alt_futures_prefix_on_auth_error(balance_path, list_mode=True)
                if alt is not None:
                    entries = list(_as_futures_balance_entries(alt))
            if not entries and api_prefix != "/dapi":
                bals = self._http_signed_futures_list("/v3/balance")
                entries = list(_as_futures_balance_entries(bals))
                if not entries:
                    alt = self._try_alt_futures_prefix_on_auth_error("/v3/balance", list_mode=True)
                    if alt is not None:
                        entries = list(_as_futures_balance_entries(alt))
            if not entries:
                entries = self._fallback_futures_balance()
    except Exception:
        entries = []
    with self._futures_account_cache_lock:
        if entries:
            self._futures_account_balance_cache = copy.deepcopy(entries)
            self._futures_account_balance_cache_ts = time.time()
        elif force_refresh:
            self._futures_account_balance_cache = None
            self._futures_account_balance_cache_ts = 0.0
    return copy.deepcopy(entries)


def _spot_account_dict(self, *, force_refresh: bool = False) -> dict:
    if not force_refresh:
        try:
            cache = getattr(self, "_spot_acct_cache", None)
            ts = getattr(self, "_spot_acct_cache_ts", 0.0)
            if cache and (time.time() - ts) <= 2.0:
                return cache
        except Exception:
            pass
    data = self._http_signed_spot("/v3/account")
    if not data:
        try:
            data = self.client.get_account()
        except Exception:
            data = {}
    if isinstance(data, dict):
        self._spot_acct_cache = data
        self._spot_acct_cache_ts = time.time()
    return data or {}
