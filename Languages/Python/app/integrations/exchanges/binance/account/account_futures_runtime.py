from __future__ import annotations

import math

from ..transport.helpers import _auth_error_hint_for
from .account_cache_runtime import _is_testnet_mode


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
    """Fetch a single snapshot of key futures balances with minimal API calls."""
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

    def _push(value) -> None:
        try:
            val = float(value or 0.0)
        except Exception:
            return
        if math.isfinite(val):
            candidates.append(val)

    if self.account_type == "FUTURES":
        _push(self.get_futures_wallet_balance(force_refresh=force_refresh))
        _push(self.get_futures_balance_usdt(force_refresh=force_refresh))
        _push(self.get_futures_available_balance())
    try:
        _push(self.get_spot_balance("USDT"))
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
