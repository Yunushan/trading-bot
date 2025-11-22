
from __future__ import annotations
from typing import List, Dict, Any
import math
from decimal import Decimal, ROUND_DOWN, getcontext

getcontext().prec = 28

def _floor_to_step(qty: float, step: float) -> float:
    if step <= 0:
        return qty
    return math.floor(qty / step) * step

def _get_lot_limits(binance, sym: str) -> tuple[float, float, float]:
    try:
        f = binance.get_symbol_filters(sym)
        lot = f.get("LOT_SIZE") or {}
        step = float(lot.get("stepSize") or 0.0)
        min_qty = float(lot.get("minQty") or 0.0)
        max_qty = float(lot.get("maxQty") or 0.0)
        return step, min_qty, max_qty
    except Exception:
        return 0.0, 0.0, 0.0

def _quantize_qty(qty_raw: float, step: float, min_qty: float, max_qty: float) -> float:
    qty = float(qty_raw)
    if max_qty > 0 and qty > max_qty:
        qty = max_qty
    try:
        if step > 0:
            dec_qty = Decimal(str(qty))
            dec_step = Decimal(str(step))
            qty = float((dec_qty // dec_step) * dec_step)
    except Exception:
        qty = _floor_to_step(qty, step)
    if qty <= 0.0 and qty_raw > 0.0:
        qty = qty_raw
    if qty < min_qty and min_qty > 0:
        qty = min_qty
    if max_qty > 0 and qty > max_qty:
        qty = max_qty
    return max(qty, 0.0)

def _cancel_all(binance, sym: str):
    try:
        binance.client.futures_cancel_all_open_orders(symbol=sym)
        return
    except Exception:
        pass
    # fallback: cancel one by one
    try:
        for o in binance.client.futures_get_open_orders(symbol=sym):
            try:
                binance.client.futures_cancel_order(symbol=sym, orderId=o.get('orderId'))
            except Exception:
                pass
    except Exception:
        pass

def _gather_positions(binance) -> List[Dict[str, Any]]:
    # Try position info first
    infos = None
    try:
        infos = binance.client.futures_position_information()
    except Exception:
        try:
            acct = binance.client.futures_account() or {}
            infos = acct.get('positions', [])
        except Exception:
            infos = []
    out: List[Dict[str, Any]] = []
    for p in infos or []:
        try:
            amt = float(p.get('positionAmt') or 0.0)
        except Exception:
            amt = 0.0
        if abs(amt) <= 0.0:
            continue
        out.append({
            'symbol': (p.get('symbol') or '').upper(),
            'positionAmt': amt,
            'positionSide': (p.get('positionSide') or '').upper(),
        })
    return out

def close_all_futures_positions(binance) -> List[Dict[str, Any]]:
    results: List[Dict[str, Any]] = []
    # detect hedge mode
    def _coerce_dual_flag(value) -> bool:
        if isinstance(value, bool):
            return value
        if isinstance(value, str):
            return value.strip().lower() in {"true", "1", "yes", "y", "on"}
        try:
            return bool(int(value))
        except Exception:
            return bool(value)

    dual = False
    try:
        mode_info = binance.client.futures_get_position_mode() or {}
        dual = _coerce_dual_flag(mode_info.get("dualSidePosition", False))
    except Exception:
        try:
            dual = bool(binance.get_futures_dual_side())
        except Exception:
            dual = False

    # up to 3 passes: handle partial fills / changes
    for _ in range(3):
        positions = _gather_positions(binance)
        if not positions:
            break
        for p in positions:
            sym = p.get('symbol')
            try:
                amt = float(p.get('positionAmt') or 0.0)
                if abs(amt) <= 0:
                    continue
                side = 'SELL' if amt > 0 else 'BUY'
                qty_raw = abs(amt)
                step, min_qty, max_qty = _get_lot_limits(binance, sym)
                qty_float = _quantize_qty(qty_raw, step, min_qty, max_qty)
                qty_str = f"{qty_float:.8f}"
                # First attempt a closePosition order to bypass filter edge cases.
                close_params = dict(symbol=sym, side=side, type='MARKET', closePosition=True)
                if dual:
                    close_params['positionSide'] = ('LONG' if amt > 0 else 'SHORT')
                try:
                    od = binance.client.futures_create_order(**close_params)
                    results.append({'ok': True, 'symbol': sym, 'info': od, 'method': 'closePosition'})
                    continue
                except Exception as e:
                    err_msg = str(e)
                _cancel_all(binance, sym)
                params = dict(symbol=sym, side=side, type='MARKET')
                if dual:
                    params['positionSide'] = ('LONG' if amt > 0 else 'SHORT')
                    params['quantity'] = str(qty_str)
                else:
                    params['reduceOnly'] = True
                    params['quantity'] = str(qty_str)
                try:
                    od = binance.client.futures_create_order(**params)
                    results.append({'ok': True, 'symbol': sym, 'info': od})
                    continue
                except Exception as e:
                    err_msg = str(e)
                    if (not dual) and ("-2022" in err_msg or "ReduceOnly" in err_msg):
                        fallback_params = dict(symbol=sym, side=side, type='MARKET', closePosition=True)
                        try:
                            od = binance.client.futures_create_order(**fallback_params)
                            results.append({'ok': True, 'symbol': sym, 'info': od, 'method': 'closePosition'})
                            continue
                        except Exception as e2:
                            err_msg = f"{err_msg} | fallback error: {e2}"
                            results.append({'ok': False, 'symbol': sym, 'error': err_msg, 'params': fallback_params})
                    else:
                        results.append({'ok': False, 'symbol': sym, 'error': err_msg, 'params': params})
            except Exception as e:
                results.append({'ok': False, 'symbol': sym, 'error': str(e)})
    return results
