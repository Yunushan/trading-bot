from __future__ import annotations

import copy
import math
import time

from ..transport.helpers import (
    _as_futures_account_dict,
    _as_futures_balance_entries,
    _auth_error_hint_for,
)


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


def get_spot_position_cost(self, symbol: str, *, max_age: float = 10.0) -> dict | None:
    """
    Approximate spot position cost basis from recent trades.
    Returns {'qty': net_qty, 'cost': cost_usdt} or None if no position.
    """
    sym = (symbol or "").upper()
    if not sym.endswith("USDT"):
        return None
    cache = getattr(self, "_spot_cost_cache", {})
    cache_ts = getattr(self, "_spot_cost_cache_ts", {})
    try:
        ts = cache_ts.get(sym, 0.0)
        if cache and sym in cache and (time.time() - ts) <= max_age:
            return cache.get(sym)
    except Exception:
        pass

    trades = []
    try:
        trades = self.client.get_my_trades(symbol=sym, limit=1000) or []
    except Exception:
        trades = self._http_signed_spot_list("/v3/myTrades", {"symbol": sym, "limit": 1000}) or []
    net_qty = 0.0
    cost = 0.0
    for trade in trades or []:
        try:
            qty = float(trade.get("qty") or trade.get("executedQty") or 0.0)
            px = float(trade.get("price") or 0.0)
            quote_qty = float(trade.get("quoteQty") or (px * qty) or 0.0)
            is_buyer = bool(trade.get("isBuyer"))
            if is_buyer:
                net_qty += qty
                cost += quote_qty
            else:
                net_qty -= qty
                cost -= quote_qty
        except Exception:
            continue
    if net_qty <= 0.0 or cost <= 0.0:
        result = None
    else:
        result = {"qty": net_qty, "cost": cost}
    try:
        cache.setdefault(sym, result)
        cache_ts[sym] = time.time()
        self._spot_cost_cache = cache
        self._spot_cost_cache_ts = cache_ts
    except Exception:
        pass
    return result


def get_spot_balance(self, asset="USDT") -> float:
    info = self._spot_account_dict(force_refresh=True)
    try:
        for balance in info.get("balances", []):
            if balance.get("asset") == asset:
                return float(balance.get("free", 0.0))
    except Exception:
        return 0.0
    return 0.0


def get_balances(self) -> list[dict]:
    """Return normalized balance objects for the active account type."""
    account_kind = str(getattr(self, "account_type", "") or "").upper()
    rows: list[dict] = []
    if account_kind.startswith("FUT"):
        try:
            balances = self._get_futures_account_balance_cached() or []
            for entry in balances:
                asset = entry.get("asset")
                if not asset:
                    continue
                free = float(entry.get("availableBalance") or entry.get("balance") or entry.get("walletBalance") or 0.0)
                total = float(entry.get("walletBalance") or entry.get("balance") or entry.get("crossWalletBalance") or free)
                locked = max(0.0, total - free)
                rows.append({
                    "asset": asset,
                    "free": free,
                    "locked": locked,
                    "total": total,
                })
        except Exception:
            rows = []
    else:
        info = self._spot_account_dict(force_refresh=True)
        try:
            for balance in info.get("balances", []):
                asset = balance.get("asset")
                if not asset:
                    continue
                free = float(balance.get("free", 0.0))
                locked = float(balance.get("locked", 0.0))
                total = free + locked
                if total <= 0.0:
                    continue
                rows.append({
                    "asset": asset,
                    "free": free,
                    "locked": locked,
                    "total": total,
                })
        except Exception:
            rows = []
    return rows


def list_spot_non_usdt_balances(self):
    """Return list of dicts with non-zero free balances for assets (excluding USDT)."""
    out = []
    info = self._spot_account_dict(force_refresh=True)
    try:
        for balance in info.get("balances", []):
            asset = balance.get("asset")
            if not asset or asset == "USDT":
                continue
            free = float(balance.get("free", 0.0))
            if free > 0:
                out.append({"asset": asset, "free": free})
    except Exception:
        pass
    return out


def get_futures_balance_usdt(self, *, force_refresh: bool = False) -> float:
    """Return the withdrawable/available balance for the primary futures asset."""
    preferred_assets = ("USDT", "BUSD", "USD")
    entries = self._get_futures_account_balance_cached(force_refresh=force_refresh) or []
    if not entries and not force_refresh:
        entries = self._get_futures_account_balance_cached(force_refresh=True) or []
    for balance in entries:
        if not isinstance(balance, dict):
            continue
        asset = str(balance.get("asset") or "").upper()
        if asset not in preferred_assets:
            continue
        for key in ("availableBalance", "crossWalletBalance", "balance", "walletBalance"):
            val = balance.get(key)
            if val is not None:
                try:
                    return float(val)
                except Exception:
                    continue
    acct_dict = self._get_futures_account_cached(force_refresh=force_refresh)
    if isinstance(acct_dict, dict):
        for key in ("availableBalance", "maxWithdrawAmount", "totalWalletBalance", "totalMarginBalance"):
            val = acct_dict.get(key)
            if val is not None:
                try:
                    return float(val)
                except Exception:
                    continue
    if not force_refresh:
        acct_dict = self._get_futures_account_cached(force_refresh=True)
        if isinstance(acct_dict, dict):
            for key in ("availableBalance", "maxWithdrawAmount", "totalWalletBalance", "totalMarginBalance"):
                val = acct_dict.get(key)
                if val is not None:
                    try:
                        return float(val)
                    except Exception:
                        continue
    return 0.0


def get_futures_balance_snapshot(self, *, force_refresh: bool = False) -> dict:
    """
    Fetch a single snapshot of key futures balances with minimal API calls.
    """
    preferred_assets = ("USDT", "BUSD", "USD")
    asset = "USDT"
    available: float | None = None
    wallet: float | None = None
    acct_dict: dict | None = None

    if self.api_key and self.api_secret:
        try:
            self._sync_futures_time_offset(force=False)
        except Exception:
            pass

    entries = self._get_futures_account_balance_cached(force_refresh=force_refresh) or []
    chosen_row = None
    try:
        candidates: dict[str, dict] = {}
        for row in entries:
            if not isinstance(row, dict):
                continue
            code = str(row.get("asset") or "").upper()
            if code in preferred_assets and code not in candidates:
                candidates[code] = row
        for code in preferred_assets:
            if code in candidates:
                asset = code
                chosen_row = candidates[code]
                break
    except Exception:
        chosen_row = None

    if isinstance(chosen_row, dict) and chosen_row:
        def _pick_float(keys: tuple[str, ...]) -> float | None:
            for key in keys:
                val = chosen_row.get(key)
                if val is None or val == "":
                    continue
                try:
                    parsed = float(val)
                except Exception:
                    continue
                if math.isfinite(parsed):
                    return parsed
            return None

        available = _pick_float(("availableBalance", "maxWithdrawAmount", "crossWalletBalance"))
        wallet = _pick_float(("walletBalance", "marginBalance", "balance", "crossWalletBalance"))

    if available is None or wallet is None:
        acct_dict = self._get_futures_account_cached(force_refresh=force_refresh) or {}
        if isinstance(acct_dict, dict):
            if available is None:
                for key in ("availableBalance", "maxWithdrawAmount"):
                    val = acct_dict.get(key)
                    if val is None:
                        continue
                    try:
                        parsed = float(val)
                    except Exception:
                        continue
                    if math.isfinite(parsed):
                        available = parsed
                        break
            if wallet is None:
                for key in (
                    "totalWalletBalance",
                    "totalMarginBalance",
                    "totalCrossWalletBalance",
                    "totalCrossBalance",
                ):
                    val = acct_dict.get(key)
                    if val is None:
                        continue
                    try:
                        parsed = float(val)
                    except Exception:
                        continue
                    if math.isfinite(parsed):
                        wallet = parsed
                        break

            if available is None or wallet is None:
                assets_list = acct_dict.get("assets")
                if isinstance(assets_list, list) and assets_list:
                    try:
                        assets_map: dict[str, dict] = {}
                        for asset_row in assets_list:
                            if not isinstance(asset_row, dict):
                                continue
                            code = str(asset_row.get("asset") or "").upper()
                            if code in preferred_assets and code not in assets_map:
                                assets_map[code] = asset_row
                        chosen_asset = None
                        for code in preferred_assets:
                            if code in assets_map:
                                asset = code
                                chosen_asset = assets_map[code]
                                break
                        if isinstance(chosen_asset, dict) and chosen_asset:
                            if available is None:
                                for key in ("availableBalance", "maxWithdrawAmount", "crossWalletBalance"):
                                    val = chosen_asset.get(key)
                                    if val is None:
                                        continue
                                    try:
                                        parsed = float(val)
                                    except Exception:
                                        continue
                                    if math.isfinite(parsed):
                                        available = parsed
                                        break
                            if wallet is None:
                                for key in ("walletBalance", "marginBalance", "balance", "crossWalletBalance"):
                                    val = chosen_asset.get(key)
                                    if val is None:
                                        continue
                                    try:
                                        parsed = float(val)
                                    except Exception:
                                        continue
                                    if math.isfinite(parsed):
                                        wallet = parsed
                                        break
                    except Exception:
                        pass

    if (
        self.api_key
        and self.api_secret
        and available is None
        and wallet is None
        and isinstance(chosen_row, dict)
        and chosen_row
    ):
        err = getattr(self, "_last_futures_http_error", None)
        if isinstance(err, dict):
            msg = str(err.get("message") or "unknown error")
            code = err.get("code")
            status = err.get("status_code")
            path = err.get("path")
            base_url = err.get("base")
            suffix = ""
            if code is not None:
                suffix += f" code={code}"
            if status is not None:
                suffix += f" http={status}"
            if path:
                suffix += f" path={path}"
            if base_url:
                suffix += f" base={base_url}"
            hint = _auth_error_hint_for(self.mode, self.account_type, code)
            if hint:
                suffix += f" | hint: {hint}"
            try:
                if _is_testnet_mode(self.mode) and str(getattr(self, "account_type", "") or "").upper().startswith("FUT"):
                    scope = self._diagnose_testnet_key_scope()
                    if scope == "spot":
                        suffix += " | hint2: These keys appear to be Spot Testnet keys; Futures Testnet uses different API keys."
            except Exception:
                pass
            try:
                extra_hint = self._testnet_auth_hint(code)
                if extra_hint:
                    suffix += f" | hint3: {extra_hint}"
            except Exception:
                pass
            raise RuntimeError(f"Futures balance fetch failed: {msg}{suffix}")
        raise RuntimeError("Futures balance fetch failed: unrecognized balance response format")

    if self.api_key and self.api_secret and not entries and (not acct_dict) and available is None and wallet is None:
        err = getattr(self, "_last_futures_http_error", None)
        if isinstance(err, dict):
            msg = str(err.get("message") or "unknown error")
            code = err.get("code")
            status = err.get("status_code")
            path = err.get("path")
            base_url = err.get("base")
            suffix = ""
            if code is not None:
                suffix += f" code={code}"
            if status is not None:
                suffix += f" http={status}"
            if path:
                suffix += f" path={path}"
            if base_url:
                suffix += f" base={base_url}"
            hint = _auth_error_hint_for(self.mode, self.account_type, code)
            if hint:
                suffix += f" | hint: {hint}"
            try:
                if _is_testnet_mode(self.mode) and str(getattr(self, "account_type", "") or "").upper().startswith("FUT"):
                    scope = self._diagnose_testnet_key_scope()
                    if scope == "spot":
                        suffix += " | hint2: These keys appear to be Spot Testnet keys; Futures Testnet uses different API keys."
            except Exception:
                pass
            try:
                extra_hint = self._testnet_auth_hint(code)
                if extra_hint:
                    suffix += f" | hint3: {extra_hint}"
            except Exception:
                pass
            raise RuntimeError(f"Futures balance fetch failed: {msg}{suffix}")
        raise RuntimeError("Futures balance fetch failed: empty response")

    available_val = float(available or 0.0)
    wallet_val = float(wallet or 0.0)
    total_val = max(available_val, wallet_val)
    return {"asset": asset, "available": available_val, "wallet": wallet_val, "total": total_val}


def get_futures_available_balance(self, *, force_refresh: bool = False) -> float:
    val = self.get_futures_balance_usdt(force_refresh=force_refresh)
    if val:
        return val
    val = self.get_futures_balance_usdt(force_refresh=True)
    if val:
        return val
    try:
        for row in self.get_balances():
            if (row.get("asset") or "").upper() == "USDT":
                free = row.get("free")
                if free is not None:
                    return float(free)
    except Exception:
        pass
    return 0.0


def get_futures_wallet_balance(self, *, force_refresh: bool = False) -> float:
    """Return the total wallet balance (including used margin) for the futures account."""
    preferred_assets = ("USDT", "BUSD", "USD")
    best_val: float | None = None
    entries_cached = self._get_futures_account_balance_cached(force_refresh=force_refresh) or []
    if not entries_cached and not force_refresh:
        entries_cached = self._get_futures_account_balance_cached(force_refresh=True) or []
    for entry in entries_cached:
        if not isinstance(entry, dict):
            continue
        asset = str(entry.get("asset") or "").upper()
        if asset not in preferred_assets:
            continue
        for key in ("walletBalance", "marginBalance", "balance", "crossWalletBalance"):
            val = entry.get(key)
            if val is None:
                continue
            try:
                parsed = float(val)
            except Exception:
                continue
            if parsed < 0.0 and best_val is None:
                best_val = parsed
            elif parsed >= 0.0:
                best_val = parsed if best_val is None else max(best_val, parsed)
        if best_val is not None:
            break
    if best_val is not None:
        return best_val
    acct_dict = self._get_futures_account_cached(force_refresh=force_refresh)
    if isinstance(acct_dict, dict):
        for key in (
            "totalWalletBalance",
            "totalMarginBalance",
            "totalCrossWalletBalance",
            "totalCrossBalance",
        ):
            val = acct_dict.get(key)
            if val is None:
                continue
            try:
                return float(val)
            except Exception:
                continue
    if not force_refresh:
        acct_dict = self._get_futures_account_cached(force_refresh=True)
        if isinstance(acct_dict, dict):
            for key in (
                "totalWalletBalance",
                "totalMarginBalance",
                "totalCrossWalletBalance",
                "totalCrossBalance",
            ):
                val = acct_dict.get(key)
                if val is None:
                    continue
                try:
                    return float(val)
                except Exception:
                    continue
    return 0.0


def get_total_usdt_value(self, *, force_refresh: bool = False) -> float:
    """Aggregate view of USDT value across futures and spot with graceful fallbacks."""
    candidates: list[float] = []

    def _push(label: str, value) -> None:
        try:
            val = float(value or 0.0)
        except Exception:
            return
        if math.isfinite(val):
            candidates.append(val)

    if self.account_type == "FUTURES":
        _push("futures_wallet", self.get_futures_wallet_balance(force_refresh=force_refresh))
        _push("futures_available", self.get_futures_balance_usdt(force_refresh=force_refresh))
        _push("futures_available_balance", self.get_futures_available_balance())
    try:
        _push("spot_usdt", self.get_spot_balance("USDT"))
    except Exception:
        pass
    if not candidates and not force_refresh:
        return self.get_total_usdt_value(force_refresh=True)
    if not candidates:
        return 0.0
    return max(candidates)


def get_total_unrealized_pnl(self) -> float:
    try:
        positions = self.list_open_futures_positions() or []
        total = 0.0
        for pos in positions:
            try:
                total += float(pos.get("unRealizedProfit") or 0.0)
            except Exception:
                continue
        return float(total)
    except Exception:
        acct_dict = self._get_futures_account_cached()
        if isinstance(acct_dict, dict):
            val = acct_dict.get("totalUnrealizedProfit")
            if val is None:
                val = acct_dict.get("totalCrossUnPnl")
            if val is not None:
                try:
                    return float(val)
                except Exception:
                    pass
    return 0.0


def get_total_wallet_balance(self) -> float:
    acct_dict = self._get_futures_account_cached()
    if isinstance(acct_dict, dict):
        for key in (
            "totalWalletBalance",
            "totalMarginBalance",
            "totalInitialMargin",
            "totalCrossWalletBalance",
            "totalCrossBalance",
        ):
            val = acct_dict.get(key)
            if val is not None:
                try:
                    return float(val)
                except Exception:
                    continue
    try:
        return float(self.get_total_usdt_value())
    except Exception:
        return 0.0


def bind_binance_account_data(wrapper_cls):
    wrapper_cls._invalidate_futures_account_cache = _invalidate_futures_account_cache
    wrapper_cls._fallback_futures_account = _fallback_futures_account
    wrapper_cls._fallback_futures_balance = _fallback_futures_balance
    wrapper_cls._try_alt_futures_prefix_on_auth_error = _try_alt_futures_prefix_on_auth_error
    wrapper_cls._get_futures_account_cached = _get_futures_account_cached
    wrapper_cls._get_futures_account_balance_cached = _get_futures_account_balance_cached
    wrapper_cls._spot_account_dict = _spot_account_dict
    wrapper_cls.get_spot_position_cost = get_spot_position_cost
    wrapper_cls.get_spot_balance = get_spot_balance
    wrapper_cls.get_balances = get_balances
    wrapper_cls.list_spot_non_usdt_balances = list_spot_non_usdt_balances
    wrapper_cls.get_futures_balance_usdt = get_futures_balance_usdt
    wrapper_cls.futures_get_usdt_balance = get_futures_balance_usdt
    wrapper_cls.get_futures_balance_snapshot = get_futures_balance_snapshot
    wrapper_cls.get_futures_available_balance = get_futures_available_balance
    wrapper_cls.get_futures_wallet_balance = get_futures_wallet_balance
    wrapper_cls.get_total_usdt_value = get_total_usdt_value
    wrapper_cls.get_total_unrealized_pnl = get_total_unrealized_pnl
    wrapper_cls.get_total_wallet_balance = get_total_wallet_balance
