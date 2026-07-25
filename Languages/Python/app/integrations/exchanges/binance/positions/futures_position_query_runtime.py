from __future__ import annotations

import copy
import math
import time

from ..runtime_diagnostics import report_runtime_fallback
from ..transport.helpers import _coerce_int

POSITION_EPSILON = 1e-10


def _finite_float(value) -> float | None:
    try:
        parsed = float(value)
    except (TypeError, ValueError, OverflowError):
        return None
    return parsed if math.isfinite(parsed) else None


def _position_number(position: dict, *keys: str) -> float:
    for key in keys:
        parsed = _finite_float(position.get(key))
        if parsed is not None:
            return parsed
    return 0.0


def _normalize_open_position(position) -> dict | None:
    if not isinstance(position, dict):
        raise ValueError("position row must be an object")
    symbol = str(position.get("symbol") or "").strip().upper()
    if not symbol:
        raise ValueError("position row is missing symbol")
    amount = _finite_float(position.get("positionAmt"))
    if amount is None:
        raise ValueError(f"{symbol} positionAmt must be finite")
    if abs(amount) <= POSITION_EPSILON:
        return None
    leverage = _position_number(position, "leverage")
    return {
        "symbol": symbol,
        "positionAmt": amount,
        "notional": _position_number(position, "notional"),
        "initialMargin": _position_number(position, "initialMargin"),
        "positionInitialMargin": _position_number(position, "positionInitialMargin", "initialMargin"),
        "openOrderMargin": _position_number(position, "openOrderInitialMargin", "openOrderMargin"),
        "isolatedWallet": _position_number(position, "isolatedWallet"),
        "isolatedMargin": _position_number(position, "isolatedMargin"),
        "maintMargin": _position_number(position, "maintMargin", "maintenanceMargin"),
        "maintMarginRate": _position_number(position, "maintMarginRate", "maintenanceMarginRate"),
        "marginRatio": _position_number(position, "marginRatio"),
        "marginBalance": _position_number(position, "marginBalance"),
        "walletBalance": _position_number(position, "walletBalance", "marginBalance"),
        "entryPrice": _position_number(position, "entryPrice"),
        "markPrice": _position_number(position, "markPrice"),
        "marginType": position.get("marginType"),
        "leverage": int(leverage),
        "unRealizedProfit": _position_number(position, "unRealizedProfit"),
        "liquidationPrice": _position_number(position, "liquidationPrice"),
        "positionSide": position.get("positionSide") or position.get("positionside"),
        "updateTime": _coerce_int(position.get("updateTime") or position.get("update_time")),
    }


def _normalize_position_snapshot(self, positions: object, source: str) -> tuple[list[dict], bool]:
    if not isinstance(positions, (list, tuple)):
        report_runtime_fallback(self, f"{source} returned an invalid position snapshot")
        return [], False
    normalized: list[dict] = []
    valid = True
    for index, position in enumerate(positions):
        try:
            row = _normalize_open_position(position)
        except (TypeError, ValueError, OverflowError) as exc:
            valid = False
            report_runtime_fallback(self, f"{source} position row {index} is malformed", exc)
            continue
        if row is not None:
            normalized.append(row)
    return normalized, valid


def _coerce_dual_side_value(value: object) -> bool | None:
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        normalized = value.strip().lower()
        if normalized in {"true", "1", "yes", "y"}:
            return True
        if normalized in {"false", "0", "no", "n"}:
            return False
        return None
    if isinstance(value, (int, float)) and value in {0, 1}:
        return bool(value)
    return None


def get_futures_dual_side(self) -> bool:
    """
    Returns True if dual-side (hedge) mode is enabled on Futures; False if one-way.
    Tries multiple client methods; normalizes string/array responses.
    """
    try:
        cached = self._futures_dual_side_cache
        ts = self._futures_dual_side_cache_ts
    except Exception as exc:
        report_runtime_fallback(self, "Futures position-mode cache is unavailable", exc)
        cached = None
        ts = 0.0
    if cached is not None and (time.time() - ts) < 300.0:
        return bool(cached)
    methods = [
        "futures_get_position_mode",
        "futures_get_position_side_dual",
        "futures_position_side_dual",
    ]
    attempted = False
    failures: list[str] = []
    for method_name in methods:
        try:
            fn = getattr(self.client, method_name, None)
            if not fn:
                continue
            attempted = True
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
            result = _coerce_dual_side_value(val)
            if result is None:
                raise ValueError("position-mode response did not contain a valid dualSidePosition value")
            self._futures_dual_side_cache = result
            self._futures_dual_side_cache_ts = time.time()
            return result
        except Exception as exc:
            failures.append(f"{method_name}: {type(exc).__name__}")
            report_runtime_fallback(self, f"Futures position-mode query via {method_name} failed", exc)
            continue
    reason = "; ".join(failures) if attempted else "no supported position-mode endpoint"
    raise RuntimeError(f"futures position mode unavailable ({reason})")


def list_open_futures_positions(self, *, max_age: float = 1.5, force_refresh: bool = False) -> list[dict] | None:
    if force_refresh and bool(getattr(self, "_fast_order_mode", False)):
        try:
            fast_ttl = float(getattr(self, "_fast_positions_cache_ttl", 0.0) or 0.0)
        except Exception as exc:
            report_runtime_fallback(self, "Fast position-cache TTL is invalid", exc)
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
    risk_method = getattr(self.client, "futures_position_risk", None)
    if callable(risk_method):
        try:
            risk_infos = risk_method()
            infos = risk_infos
        except Exception as exc:
            report_runtime_fallback(self, "Primary futures position snapshot failed", exc)
        if not isinstance(risk_infos, (list, tuple)) or not risk_infos:
            try:
                infos = self.client.futures_position_information()
            except Exception as fallback_exc:
                report_runtime_fallback(self, "Fallback futures position snapshot failed", fallback_exc)
                infos = risk_infos if isinstance(risk_infos, (list, tuple)) else None
    else:
        try:
            infos = self.client.futures_position_information()
        except Exception as exc:
            report_runtime_fallback(self, "Futures position snapshot failed", exc)
            infos = None
    risk_lookup = {}
    if infos is not None and not isinstance(infos, (list, tuple)):
        report_runtime_fallback(self, "Futures position endpoint returned a non-list snapshot")
        infos = None
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
            except Exception as exc:
                report_runtime_fallback(self, "Malformed futures risk row ignored", exc)
                continue
    out: list[dict] = []
    primary_snapshot_available = False
    if infos is not None:
        out, primary_snapshot_available = _normalize_position_snapshot(self, infos, "Futures position endpoint")
    account_snapshot_available = False
    if not primary_snapshot_available or not out:
        try:
            acc = self._get_futures_account_cached(force_refresh=True) or {}
            raw_positions = acc.get("positions") if isinstance(acc, dict) else None
            account_rows, account_snapshot_available = _normalize_position_snapshot(
                self,
                raw_positions,
                "Futures account endpoint",
            )
            if account_snapshot_available and (not primary_snapshot_available or not out):
                out = account_rows
        except Exception as exc:
            report_runtime_fallback(self, "Futures account position fallback failed", exc)
            account_snapshot_available = False
    if not primary_snapshot_available and not account_snapshot_available:
        return None
    if risk_lookup:
        for row in out:
            try:
                sym = str(row.get("symbol") or "").upper()
                side = str(row.get("positionSide") or row.get("positionside") or "BOTH").upper()
                risk = risk_lookup.get((sym, side)) or risk_lookup.get((sym, "BOTH"))
                if not isinstance(risk, dict):
                    continue
                risk_ratio_raw = _finite_float(risk.get("marginRatio"))
                if risk_ratio_raw is not None:
                    row["marginRatioRaw"] = risk_ratio_raw
                    row["marginRatio"] = risk_ratio_raw

                def _safe_update(target_key, source_keys):
                    for src in source_keys:
                        if src not in risk:
                            continue
                        val = risk.get(src)
                        if val in (None, "", 0, 0.0):
                            continue
                        parsed = _finite_float(val)
                        if parsed is not None:
                            row[target_key] = parsed
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
                maint_margin = _finite_float(row.get("maintMargin")) or 0.0
                open_order_margin = _finite_float(row.get("openOrderMargin")) or 0.0
                wallet_balance = _finite_float(row.get("walletBalance")) or _finite_float(row.get("marginBalance")) or 0.0
                unreal = _finite_float(row.get("unRealizedProfit")) or 0.0
                loss_component = abs(unreal) if unreal < 0 else 0.0
                calc_ratio = ((maint_margin + open_order_margin + loss_component) / wallet_balance) * 100.0 if wallet_balance > 0.0 else 0.0
                row["marginRatioCalc"] = calc_ratio
                if (_finite_float(row.get("marginRatio")) or 0.0) <= 0.0 and calc_ratio > 0.0:
                    row["marginRatio"] = calc_ratio
            except Exception as exc:
                report_runtime_fallback(self, "Futures position risk enrichment failed", exc)
                continue
    snapshot = copy.deepcopy(out)
    self._store_futures_positions_cache(snapshot)
    return copy.deepcopy(snapshot)


def get_net_futures_position_amt(self, symbol: str) -> float | None:
    """
    Return the net position quantity for a symbol (positive long, negative short, 0 if flat).
    """
    try:
        infos = list_open_futures_positions(self, max_age=0.0, force_refresh=True)
    except Exception as exc:
        report_runtime_fallback(self, "Net futures position snapshot failed", exc)
        return None
    if infos is None:
        return None
    symbol_upper = str(symbol or "").strip().upper()
    net_amount = 0.0
    for entry in infos:
        try:
            if str(entry.get("symbol", "")).upper() != symbol_upper:
                continue
            amount = _finite_float(entry.get("positionAmt"))
            if amount is None:
                raise ValueError("normalized position amount is not finite")
            if abs(amount) > POSITION_EPSILON:
                net_amount += amount
        except Exception as exc:
            report_runtime_fallback(self, "Net futures position row is malformed", exc)
            return None
    if not symbol_upper:
        report_runtime_fallback(self, "Net futures position query used an empty symbol")
        return None
    if not math.isfinite(net_amount):
        report_runtime_fallback(self, f"Net futures position for {symbol_upper} is not finite")
        return None
    return net_amount if abs(net_amount) > POSITION_EPSILON else 0.0
