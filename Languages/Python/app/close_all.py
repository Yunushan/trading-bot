
from __future__ import annotations
from typing import List, Dict, Any
from concurrent.futures import ThreadPoolExecutor, as_completed
import math
import time
from decimal import Decimal, ROUND_DOWN, getcontext

getcontext().prec = 28

def _floor_to_step(qty: float, step: float) -> float:
    if step <= 0:
        return qty
    return math.floor(qty / step) * step

def _get_lot_limits(binance, sym: str) -> tuple[float, float, float]:
    try:
        fut_filters = getattr(binance, "get_futures_symbol_filters", None)
        if callable(fut_filters):
            f = fut_filters(sym) or {}
            step = float(f.get("stepSize") or 0.0)
            min_qty = float(f.get("minQty") or 0.0)
            max_qty = float(f.get("maxQty") or 0.0)
            if step > 0.0 or min_qty > 0.0 or max_qty > 0.0:
                return step, min_qty, max_qty
    except Exception:
        pass
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

def _submit_futures_order(binance, params: dict) -> dict:
    """Place a futures order using wrapper fallback path when available."""
    try:
        submit = getattr(binance, "_futures_create_order_with_fallback", None)
        if callable(submit):
            order, _via = submit(dict(params))
            try:
                invalidate = getattr(binance, "_invalidate_futures_positions_cache", None)
                if callable(invalidate):
                    invalidate()
            except Exception:
                pass
            return order or {}
    except Exception:
        pass
    order = binance.client.futures_create_order(**params)
    try:
        invalidate = getattr(binance, "_invalidate_futures_positions_cache", None)
        if callable(invalidate):
            invalidate()
    except Exception:
        pass
    return order or {}

def _normalize_position_side(value: str | None) -> str:
    side = str(value or "").strip().upper()
    return side if side else "BOTH"

def _derive_close_directive(amt: float, pos_side: str | None, dual: bool) -> tuple[str, str | None, float]:
    """Return (order_side, position_side, qty_abs) for closing the given position row."""
    qty_raw = abs(float(amt or 0.0))
    ps_norm = _normalize_position_side(pos_side)
    if dual:
        if ps_norm == "LONG":
            return "SELL", "LONG", qty_raw
        if ps_norm == "SHORT":
            return "BUY", "SHORT", qty_raw
    if float(amt or 0.0) < 0.0:
        return "BUY", ("SHORT" if dual else None), qty_raw
    return "SELL", ("LONG" if dual else None), qty_raw

def _is_unknown_execution_error(err: object) -> bool:
    if err is None:
        return False
    try:
        code = getattr(err, "code", None)
    except Exception:
        code = None
    if code in (-1007,):
        return True
    text = str(err)
    lower = text.lower()
    if "-1007" in lower:
        return True
    if "execution status unknown" in lower or "send status unknown" in lower:
        return True
    if "timeout waiting for response" in lower:
        return True
    return False

def _gather_positions(binance) -> tuple[List[Dict[str, Any]], bool]:
    # Try position info first
    infos = None
    ok = False
    try:
        infos = binance.client.futures_position_information()
        ok = True
    except Exception:
        try:
            acct = binance.client.futures_account() or {}
            infos = acct.get('positions', [])
            ok = True
        except Exception:
            infos = []
            ok = False
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
            'positionSide': _normalize_position_side(p.get('positionSide')),
        })
    return out, ok

def _is_testnet_wrapper(binance) -> bool:
    try:
        text = str(getattr(binance, "mode", "") or "").lower()
    except Exception:
        text = ""
    return any(tag in text for tag in ("demo", "test", "sandbox"))

def close_all_futures_positions(binance, *, fast: bool = False, max_workers: int | None = None) -> List[Dict[str, Any]]:
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

    if fast:
        use_close_position = not _is_testnet_wrapper(binance)
        try:
            try:
                binance.client.futures_cancel_all_open_orders()
            except Exception:
                pass
        except Exception:
            pass
        positions, _ = _gather_positions(binance)
        if not positions:
            return results
        if max_workers is None:
            max_workers = min(6, max(1, len(positions)))

        def _attempt_close_position(p):
            sym = p.get('symbol')
            pos_side = _normalize_position_side(p.get('positionSide'))
            try:
                amt = float(p.get('positionAmt') or 0.0)
            except Exception:
                amt = 0.0
            if abs(amt) <= 0:
                return {
                    'ok': True,
                    'symbol': sym,
                    'positionSide': pos_side,
                    'skipped': True,
                    'reason': 'zero-qty',
                }
            side, target_ps, qty_raw = _derive_close_directive(amt, pos_side, dual)
            if use_close_position:
                close_params = dict(symbol=sym, side=side, type='MARKET', closePosition=True)
                if dual and target_ps in ("LONG", "SHORT"):
                    close_params['positionSide'] = target_ps
                try:
                    od = _submit_futures_order(binance, close_params)
                    return {'ok': True, 'symbol': sym, 'positionSide': pos_side, 'info': od, 'method': 'closePosition'}
                except Exception as e:
                    return {
                        'ok': False,
                        'symbol': sym,
                        'positionSide': pos_side,
                        'error': str(e),
                        'positionAmt': amt,
                    }
            try:
                step, min_qty, max_qty = _get_lot_limits(binance, sym)
                qty_float = _quantize_qty(qty_raw, step, min_qty, max_qty)
                if qty_float <= 0.0:
                    return {
                        'ok': True,
                        'symbol': sym,
                        'positionSide': pos_side,
                        'skipped': True,
                        'reason': 'zero-qty',
                    }
                qty_str = f"{qty_float:.8f}"
                params = dict(symbol=sym, side=side, type='MARKET')
                if dual and target_ps in ("LONG", "SHORT"):
                    params['positionSide'] = target_ps
                    params['quantity'] = str(qty_str)
                else:
                    params['reduceOnly'] = True
                    params['quantity'] = str(qty_str)
                od = _submit_futures_order(binance, params)
                return {'ok': True, 'symbol': sym, 'positionSide': pos_side, 'info': od, 'method': 'reduceOnly'}
            except Exception as e:
                return {
                    'ok': False,
                    'symbol': sym,
                    'positionSide': pos_side,
                    'error': str(e),
                    'positionAmt': amt,
                }

        with ThreadPoolExecutor(max_workers=max_workers) as executor:
            futures = [executor.submit(_attempt_close_position, p) for p in positions]
            for future in as_completed(futures):
                try:
                    results.append(future.result())
                except Exception as e:
                    results.append({'ok': False, 'symbol': '?', 'error': str(e)})

        failures = [r for r in results if not r.get('ok')]
        if failures and use_close_position:
            for r in failures:
                sym = r.get('symbol') or ''
                amt = float(r.get('positionAmt') or 0.0)
                if not sym or abs(amt) <= 0.0:
                    continue
                try:
                    side, target_ps, qty_raw = _derive_close_directive(amt, r.get('positionSide'), dual)
                    step, min_qty, max_qty = _get_lot_limits(binance, sym)
                    qty_float = _quantize_qty(qty_raw, step, min_qty, max_qty)
                    qty_str = f"{qty_float:.8f}"
                    params = dict(symbol=sym, side=side, type='MARKET')
                    if dual and target_ps in ("LONG", "SHORT"):
                        params['positionSide'] = target_ps
                        params['quantity'] = str(qty_str)
                    else:
                        params['reduceOnly'] = True
                        params['quantity'] = str(qty_str)
                    try:
                        od = _submit_futures_order(binance, params)
                        results.append({'ok': True, 'symbol': sym, 'positionSide': r.get('positionSide'), 'info': od})
                    except Exception as e:
                        results.append({
                            'ok': False,
                            'symbol': sym,
                            'positionSide': r.get('positionSide'),
                            'error': str(e),
                            'params': params,
                        })
                except Exception as e:
                    results.append({
                        'ok': False,
                        'symbol': sym,
                        'positionSide': r.get('positionSide'),
                        'error': str(e),
                    })
        failures = [r for r in results if not r.get('ok')]
        if failures:
            result_index: dict[tuple[str, str], int] = {}
            def _result_key(res: dict) -> tuple[str, str] | None:
                sym = str(res.get('symbol') or '').upper()
                if not sym:
                    return None
                side = _normalize_position_side(res.get('positionSide'))
                return (sym, side)

            for idx, res in enumerate(results):
                key = _result_key(res)
                if key is not None:
                    result_index[key] = idx

            def _upsert_result(res: dict) -> None:
                key = _result_key(res)
                if key is None:
                    results.append(res)
                    return
                idx = result_index.get(key)
                if idx is None:
                    result_index[key] = len(results)
                    results.append(res)
                else:
                    results[idx] = res

            if any(_is_unknown_execution_error(r.get('error')) for r in failures):
                time.sleep(0.35)
            for _ in range(2):
                remaining, remaining_ok = _gather_positions(binance)
                if not remaining_ok or not remaining:
                    break
                for p in remaining:
                    _upsert_result(_attempt_close_position(p))
                if any(
                    _is_unknown_execution_error(r.get('error'))
                    for r in results
                    if not r.get('ok')
                ):
                    time.sleep(0.35)
            remaining, remaining_ok = _gather_positions(binance)
            if remaining_ok:
                open_symbols = {str(p.get('symbol') or '').upper() for p in remaining}
                for r in results:
                    if r.get('ok'):
                        continue
                    if not _is_unknown_execution_error(r.get('error')):
                        continue
                    sym = str(r.get('symbol') or '').upper()
                    if sym and sym not in open_symbols:
                        r['ok'] = True
                        r['reconciled'] = True
        return results

    # up to 3 passes: handle partial fills / changes
    for _ in range(3):
        positions, _ = _gather_positions(binance)
        if not positions:
            break
        for p in positions:
            sym = p.get('symbol')
            pos_side = _normalize_position_side(p.get('positionSide'))
            try:
                amt = float(p.get('positionAmt') or 0.0)
                if abs(amt) <= 0:
                    continue
                side, target_ps, qty_raw = _derive_close_directive(amt, pos_side, dual)
                step, min_qty, max_qty = _get_lot_limits(binance, sym)
                qty_float = _quantize_qty(qty_raw, step, min_qty, max_qty)
                qty_str = f"{qty_float:.8f}"
                # First attempt a closePosition order to bypass filter edge cases.
                close_params = dict(symbol=sym, side=side, type='MARKET', closePosition=True)
                if dual and target_ps in ("LONG", "SHORT"):
                    close_params['positionSide'] = target_ps
                try:
                    od = _submit_futures_order(binance, close_params)
                    results.append({
                        'ok': True,
                        'symbol': sym,
                        'positionSide': pos_side,
                        'info': od,
                        'method': 'closePosition',
                    })
                    continue
                except Exception as e:
                    err_msg = str(e)
                _cancel_all(binance, sym)
                params = dict(symbol=sym, side=side, type='MARKET')
                if dual and target_ps in ("LONG", "SHORT"):
                    params['positionSide'] = target_ps
                    params['quantity'] = str(qty_str)
                else:
                    params['reduceOnly'] = True
                    params['quantity'] = str(qty_str)
                try:
                    od = _submit_futures_order(binance, params)
                    results.append({'ok': True, 'symbol': sym, 'positionSide': pos_side, 'info': od})
                    continue
                except Exception as e:
                    err_msg = str(e)
                    if (not dual) and ("-2022" in err_msg or "ReduceOnly" in err_msg):
                        fallback_params = dict(symbol=sym, side=side, type='MARKET', closePosition=True)
                        try:
                            od = _submit_futures_order(binance, fallback_params)
                            results.append({
                                'ok': True,
                                'symbol': sym,
                                'positionSide': pos_side,
                                'info': od,
                                'method': 'closePosition',
                            })
                            continue
                        except Exception as e2:
                            err_msg = f"{err_msg} | fallback error: {e2}"
                            results.append({
                                'ok': False,
                                'symbol': sym,
                                'positionSide': pos_side,
                                'error': err_msg,
                                'params': fallback_params,
                            })
                    else:
                        results.append({
                            'ok': False,
                            'symbol': sym,
                            'positionSide': pos_side,
                            'error': err_msg,
                            'params': params,
                        })
            except Exception as e:
                results.append({'ok': False, 'symbol': sym, 'positionSide': pos_side, 'error': str(e)})
    return results
