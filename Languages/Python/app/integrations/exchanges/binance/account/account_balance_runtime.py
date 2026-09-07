from __future__ import annotations

import math
import time

from ..runtime_diagnostics import report_runtime_fallback


def _finite_float(value: object) -> float | None:
    if isinstance(value, bool) or not isinstance(value, (str, int, float)):
        return None
    try:
        parsed = float(value)
    except (TypeError, ValueError, OverflowError):
        return None
    return parsed if math.isfinite(parsed) else None


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
    except Exception as exc:
        report_runtime_fallback(self, f"{sym} spot cost cache read failed", exc)

    trades = []
    try:
        trades = self.client.get_my_trades(symbol=sym, limit=1000) or []
    except Exception as exc:
        report_runtime_fallback(self, f"{sym} primary spot trade history failed", exc)
        trades = self._http_signed_spot_list("/v3/myTrades", {"symbol": sym, "limit": 1000}) or []
    if not isinstance(trades, (list, tuple)):
        report_runtime_fallback(self, f"{sym} spot trade history returned an invalid snapshot")
        return None
    net_qty = 0.0
    cost = 0.0
    trades_valid = True
    for index, trade in enumerate(trades):
        try:
            if not isinstance(trade, dict):
                raise ValueError("trade row must be an object")
            qty = _finite_float(trade.get("qty") or trade.get("executedQty") or 0.0)
            px = _finite_float(trade.get("price") or 0.0)
            if qty is None or qty < 0.0 or px is None or px < 0.0:
                raise ValueError("trade quantity and price must be finite non-negative values")
            quote_qty = _finite_float(trade.get("quoteQty") or (px * qty) or 0.0)
            if quote_qty is None or quote_qty < 0.0:
                raise ValueError("trade quote quantity must be a finite non-negative value")
            is_buyer = bool(trade.get("isBuyer"))
            if is_buyer:
                net_qty += qty
                cost += quote_qty
            else:
                net_qty -= qty
                cost -= quote_qty
        except Exception as exc:
            trades_valid = False
            report_runtime_fallback(self, f"{sym} spot trade history row {index} is malformed", exc)
            continue
    if not trades_valid or net_qty <= 0.0 or cost <= 0.0:
        result = None
    else:
        result = {"qty": net_qty, "cost": cost}
    try:
        cache.setdefault(sym, result)
        cache_ts[sym] = time.time()
        self._spot_cost_cache = cache
        self._spot_cost_cache_ts = cache_ts
    except Exception as exc:
        report_runtime_fallback(self, f"{sym} spot cost cache write failed", exc)
    return result


def _spot_balance_rows(self) -> list[dict]:
    info = self._spot_account_dict(force_refresh=True)
    if not isinstance(info, dict) or not isinstance(info.get("balances"), list):
        raise RuntimeError("Spot balance snapshot is unavailable or invalid")
    rows = []
    seen = set()
    for balance in info["balances"]:
        if not isinstance(balance, dict):
            raise RuntimeError("Spot balance row is invalid")
        asset = balance.get("asset")
        if not isinstance(asset, str) or not asset.strip() or any(char.isspace() for char in asset.strip()):
            raise RuntimeError("Spot balance asset is invalid")
        asset = asset.strip().upper()
        if asset in seen or asset in {"UNKNOWN", "NONE", "NULL", "-"}:
            raise RuntimeError("Spot balance asset is invalid or duplicated")
        seen.add(asset)
        free, locked = _finite_float(balance.get("free")), _finite_float(balance.get("locked"))
        if free is None or locked is None or free < 0.0 or locked < 0.0 or not math.isfinite(free + locked):
            raise RuntimeError("Spot balance quantities must be finite and non-negative")
        rows.append({"asset": asset, "free": free, "locked": locked, "total": free + locked})
    return rows


def get_spot_balance(self, asset="USDT") -> float:
    for balance in _spot_balance_rows(self):
        if balance["asset"] == str(asset).strip().upper():
            return balance["free"]
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
        except Exception as exc:
            report_runtime_fallback(self, "Futures balance list normalization failed", exc)
            rows = []
    else:
        rows = [row for row in _spot_balance_rows(self) if row["total"] > 0.0]
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
    except Exception as exc:
        report_runtime_fallback(self, "Non-USDT spot balance normalization failed", exc)
    return out
