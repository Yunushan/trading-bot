
from __future__ import annotations
from typing import List, Dict, Any
import math

def _floor_to_step(qty: float, step: float) -> float:
    if step <= 0:
        return qty
    return math.floor(qty / step) * step

def _get_lot_step(binance, sym: str) -> float:
    try:
        f = binance.get_symbol_filters(sym)
        return float((f.get('LOT_SIZE') or {}).get('stepSize') or 0.0)
    except Exception:
        return 0.0

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
    dual = False
    try:
        m = binance.client.futures_get_position_mode() or {}
        dual = bool(m.get('dualSidePosition', False))
    except Exception:
        pass

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
                qty  = abs(amt)
                qty  = _floor_to_step(qty, _get_lot_step(binance, sym))
                if qty <= 0:
                    results.append({'ok': True, 'symbol': sym, 'skipped': True, 'reason': 'zero qty after rounding'})
                    continue
                _cancel_all(binance, sym)
                params = dict(symbol=sym, side=side, type='MARKET', quantity=str(qty))
                if dual:
                    params['positionSide'] = ('LONG' if amt > 0 else 'SHORT')
                try:
                    od = binance.client.futures_create_order(**params)
                    results.append({'ok': True, 'symbol': sym, 'info': od})
                except Exception as e:
                    results.append({'ok': False, 'symbol': sym, 'error': str(e), 'params': params})
            except Exception as e:
                results.append({'ok': False, 'symbol': sym, 'error': str(e)})
    return results
