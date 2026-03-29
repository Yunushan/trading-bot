from __future__ import annotations

import copy
import time

from ..transport.helpers import _coerce_int


def get_futures_dual_side(self) -> bool:
    """
    Returns True if dual-side (hedge) mode is enabled on Futures; False if one-way.
    Tries multiple client methods; normalizes string/array responses.
    """
    try:
        cached = self._futures_dual_side_cache
        ts = self._futures_dual_side_cache_ts
    except Exception:
        cached = None
        ts = 0.0
    if cached is not None and (time.time() - ts) < 300.0:
        return bool(cached)
    methods = [
        "futures_get_position_mode",
        "futures_get_position_side_dual",
        "futures_position_side_dual",
    ]
    for method_name in methods:
        try:
            fn = getattr(self.client, method_name, None)
            if not fn:
                continue
            res = fn()
            val = None
            if isinstance(res, dict):
                val = res.get("dualSidePosition")
            elif isinstance(res, (list, tuple)) and res:
                first = res[0]
                if isinstance(first, dict) and "dualSidePosition" in first:
                    val = first["dualSidePosition"]
                else:
                    val = first
            else:
                val = res
            if isinstance(val, str):
                val = val.strip().lower() in ("true", "1", "yes", "y")
            result = bool(val)
            self._futures_dual_side_cache = result
            self._futures_dual_side_cache_ts = time.time()
            return result
        except Exception:
            continue
    self._futures_dual_side_cache = False
    self._futures_dual_side_cache_ts = time.time()
    return False


def list_open_futures_positions(self, *, max_age: float = 1.5, force_refresh: bool = False):
    if force_refresh and bool(getattr(self, "_fast_order_mode", False)):
        try:
            fast_ttl = float(getattr(self, "_fast_positions_cache_ttl", 0.0) or 0.0)
        except Exception:
            fast_ttl = 0.0
        if fast_ttl > 0.0:
            max_age = max(float(max_age or 0.0), fast_ttl)
            force_refresh = False
    if not force_refresh:
        cached = self._get_cached_futures_positions(max_age)
        if cached is not None:
            return cached
    infos = None
    risk_infos = None
    try:
        risk_method = getattr(self.client, "futures_position_risk", None)
        if callable(risk_method):
            risk_infos = risk_method()
            infos = risk_infos
        else:
            infos = self.client.futures_position_information()
    except Exception:
        try:
            infos = self.client.futures_position_information()
        except Exception:
            infos = None
    risk_lookup = {}
    if risk_infos is None and infos is not None:
        risk_infos = infos
    if isinstance(risk_infos, list):
        for risk in risk_infos:
            try:
                sym = str(risk.get("symbol") or "").upper()
                if not sym:
                    continue
                side = str(risk.get("positionSide") or "BOTH").upper()
                risk_lookup[(sym, side)] = risk
                if side != "BOTH" and (sym, "BOTH") not in risk_lookup:
                    risk_lookup[(sym, "BOTH")] = risk
            except Exception:
                continue
    out = []
    if not infos:
        try:
            acc = self._get_futures_account_cached(force_refresh=True) or {}
            for pos in acc.get("positions", []):
                amt = float(pos.get("positionAmt") or 0.0)
                if abs(amt) <= 0.0:
                    continue
                row = {
                    "symbol": pos.get("symbol"),
                    "positionAmt": amt,
                    "notional": float(pos.get("notional") or 0.0) if isinstance(pos, dict) else 0.0,
                    "initialMargin": float(pos.get("initialMargin") or 0.0) if isinstance(pos, dict) else 0.0,
                    "positionInitialMargin": float(pos.get("positionInitialMargin") or pos.get("initialMargin") or 0.0) if isinstance(pos, dict) else 0.0,
                    "openOrderMargin": float(pos.get("openOrderInitialMargin") or 0.0) if isinstance(pos, dict) else 0.0,
                    "isolatedWallet": float(pos.get("isolatedWallet") or 0.0) if isinstance(pos, dict) else 0.0,
                    "isolatedMargin": float(pos.get("isolatedMargin") or 0.0) if isinstance(pos, dict) else 0.0,
                    "maintMargin": float(pos.get("maintMargin") or pos.get("maintenanceMargin") or 0.0) if isinstance(pos, dict) else 0.0,
                    "maintMarginRate": float(pos.get("maintMarginRate") or pos.get("maintenanceMarginRate") or 0.0) if isinstance(pos, dict) else 0.0,
                    "marginRatio": float(pos.get("marginRatio") or 0.0),
                    "marginBalance": float(pos.get("marginBalance") or 0.0) if isinstance(pos, dict) else 0.0,
                    "walletBalance": float(pos.get("walletBalance") or pos.get("marginBalance") or 0.0) if isinstance(pos, dict) else 0.0,
                    "entryPrice": float(pos.get("entryPrice") or 0.0),
                    "markPrice": float(pos.get("markPrice") or 0.0),
                    "marginType": pos.get("marginType"),
                    "leverage": int(float(pos.get("leverage") or 0)),
                    "unRealizedProfit": float(pos.get("unRealizedProfit") or 0.0),
                    "liquidationPrice": float(pos.get("liquidationPrice") or 0.0),
                    "positionSide": (pos.get("positionSide") or pos.get("positionside")),
                    "updateTime": _coerce_int(pos.get("updateTime") or pos.get("update_time")),
                }
                out.append(row)
        except Exception:
            pass
    else:
        for pos in infos or []:
            try:
                amt = float(pos.get("positionAmt") or 0.0)
                if abs(amt) <= 0.0:
                    continue
                row = {
                    "symbol": pos.get("symbol"),
                    "positionAmt": amt,
                    "notional": float(pos.get("notional") or 0.0) if isinstance(pos, dict) else 0.0,
                    "initialMargin": float(pos.get("initialMargin") or 0.0) if isinstance(pos, dict) else 0.0,
                    "positionInitialMargin": float(pos.get("positionInitialMargin") or pos.get("initialMargin") or 0.0) if isinstance(pos, dict) else 0.0,
                    "openOrderMargin": float(pos.get("openOrderInitialMargin") or 0.0) if isinstance(pos, dict) else 0.0,
                    "isolatedWallet": float(pos.get("isolatedWallet") or 0.0) if isinstance(pos, dict) else 0.0,
                    "isolatedMargin": float(pos.get("isolatedMargin") or 0.0) if isinstance(pos, dict) else 0.0,
                    "maintMargin": float(pos.get("maintMargin") or pos.get("maintenanceMargin") or 0.0) if isinstance(pos, dict) else 0.0,
                    "maintMarginRate": float(pos.get("maintMarginRate") or pos.get("maintenanceMarginRate") or 0.0) if isinstance(pos, dict) else 0.0,
                    "marginRatio": float(pos.get("marginRatio") or 0.0),
                    "marginBalance": float(pos.get("marginBalance") or 0.0) if isinstance(pos, dict) else 0.0,
                    "walletBalance": float(pos.get("walletBalance") or pos.get("marginBalance") or 0.0) if isinstance(pos, dict) else 0.0,
                    "entryPrice": float(pos.get("entryPrice") or 0.0),
                    "markPrice": float(pos.get("markPrice") or 0.0),
                    "marginType": pos.get("marginType"),
                    "leverage": int(float(pos.get("leverage") or 0)),
                    "unRealizedProfit": float(pos.get("unRealizedProfit") or 0.0),
                    "liquidationPrice": float(pos.get("liquidationPrice") or 0.0),
                    "positionSide": (pos.get("positionSide") or pos.get("positionside")),
                    "updateTime": _coerce_int(pos.get("updateTime") or pos.get("update_time")),
                }
                out.append(row)
            except Exception:
                continue
    if risk_lookup:
        for row in out:
            try:
                sym = str(row.get("symbol") or "").upper()
                side = str(row.get("positionSide") or row.get("positionside") or "BOTH").upper()
                risk = risk_lookup.get((sym, side)) or risk_lookup.get((sym, "BOTH"))
                if not isinstance(risk, dict):
                    continue
                risk_ratio_raw = risk.get("marginRatio")
                if risk_ratio_raw is not None:
                    try:
                        row["marginRatioRaw"] = float(risk_ratio_raw)
                        row["marginRatio"] = float(risk_ratio_raw)
                    except Exception:
                        pass

                def _safe_update(target_key, source_keys):
                    for src in source_keys:
                        if src not in risk:
                            continue
                        val = risk.get(src)
                        if val in (None, "", 0, 0.0):
                            continue
                        try:
                            row[target_key] = float(val)
                        except Exception:
                            row[target_key] = val
                        return

                _safe_update("marginRatio", ["marginRatio"])
                _safe_update("isolatedWallet", ["isolatedWallet"])
                _safe_update("isolatedMargin", ["isolatedMargin"])
                _safe_update("marginBalance", ["marginBalance", "isolatedWallet"])
                _safe_update("initialMargin", ["initialMargin", "isolatedMargin"])
                _safe_update("positionInitialMargin", ["positionInitialMargin", "initialMargin"])
                _safe_update("openOrderMargin", ["openOrderInitialMargin", "openOrderMargin"])
                _safe_update("walletBalance", ["walletBalance", "marginBalance"])
                _safe_update("notional", ["notional"])
                _safe_update("unRealizedProfit", ["unRealizedProfit"])
                _safe_update("entryPrice", ["entryPrice"])
                _safe_update("markPrice", ["markPrice"])
                _safe_update("leverage", ["leverage"])
                try:
                    maint_margin = float(row.get("maintMargin") or 0.0)
                except Exception:
                    maint_margin = 0.0
                try:
                    open_order_margin = float(row.get("openOrderMargin") or 0.0)
                except Exception:
                    open_order_margin = 0.0
                try:
                    wallet_balance = float(row.get("walletBalance") or row.get("marginBalance") or 0.0)
                except Exception:
                    wallet_balance = 0.0
                try:
                    unreal = float(row.get("unRealizedProfit") or 0.0)
                except Exception:
                    unreal = 0.0
                loss_component = abs(unreal) if unreal < 0 else 0.0
                calc_ratio = ((maint_margin + open_order_margin + loss_component) / wallet_balance) * 100.0 if wallet_balance > 0.0 else 0.0
                row["marginRatioCalc"] = calc_ratio
                if float(row.get("marginRatio") or 0.0) <= 0.0 and calc_ratio > 0.0:
                    row["marginRatio"] = calc_ratio
            except Exception:
                continue
    snapshot = copy.deepcopy(out)
    self._store_futures_positions_cache(snapshot)
    return copy.deepcopy(snapshot)


def get_net_futures_position_amt(self, symbol: str) -> float:
    """
    Return the net position quantity for a symbol (positive long, negative short, 0 if flat).
    """
    try:
        infos = self.client.futures_position_information()
    except Exception:
        try:
            infos = self.client.futures_position_risk()
        except Exception:
            infos = None
    if not infos:
        return 0.0
    symbol_upper = str(symbol or "").strip().upper()
    for entry in infos:
        try:
            if str(entry.get("symbol", "")).upper() != symbol_upper:
                continue
            amt = float(entry.get("positionAmt") or entry.get("positionAmt", 0.0) or 0.0)
            return amt
        except Exception:
            continue
    return 0.0
