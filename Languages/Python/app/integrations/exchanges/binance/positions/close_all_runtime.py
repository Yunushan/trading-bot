from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor, as_completed
from decimal import Decimal, InvalidOperation, getcontext
import math
import time
from typing import Any, Dict, List

getcontext().prec = 28


def _record_close_all_exception(binance, context: str, exc: BaseException) -> None:
    message = str(exc).replace("\n", " ")
    try:
        logger = getattr(binance, "_log", None)
    except Exception:
        logger = None
    if callable(logger):
        try:
            logger(f"close-all suppressed exception context={context} error={type(exc).__name__}: {message}", lvl="warn")
        except Exception:
            return


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
    except Exception as exc:
        _record_close_all_exception(binance, f"get_futures_lot_limits:{sym}", exc)
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
    # A close path must never increase quantity above the live position. In
    # hedge mode an oversized quantity can create or expose the opposite side.
    if qty < min_qty and min_qty > 0:
        return 0.0
    if max_qty > 0 and qty > max_qty:
        qty = max_qty
    return max(qty, 0.0)


def _cancel_all(binance, sym: str):
    try:
        binance.client.futures_cancel_all_open_orders(symbol=sym)
        return
    except Exception as exc:
        _record_close_all_exception(binance, f"cancel_all_open_orders_bulk:{sym}", exc)
    # fallback: cancel one by one
    try:
        for o in binance.client.futures_get_open_orders(symbol=sym):
            try:
                binance.client.futures_cancel_order(symbol=sym, orderId=o.get("orderId"))
            except Exception as exc:
                _record_close_all_exception(binance, f"cancel_open_order:{sym}", exc)
    except Exception as exc:
        _record_close_all_exception(binance, f"cancel_all_open_orders_list:{sym}", exc)


def _submit_futures_order(binance, params: dict) -> dict:
    """Place a futures order using wrapper fallback path when available."""
    submit = getattr(binance, "_futures_create_order_with_fallback", None)
    if callable(submit):
        order, _via = submit(dict(params))
        try:
            invalidate = getattr(binance, "_invalidate_futures_positions_cache", None)
            if callable(invalidate):
                invalidate()
        except Exception as exc:
            _record_close_all_exception(binance, "submit_futures_order_invalidate_fallback_cache", exc)
        return order or {}
    guard = getattr(binance, "_guard_live_order_submit", None)
    if callable(guard):
        guard(market="futures", params=params, source="close_all_futures_positions")
    order = binance.client.futures_create_order(**params)
    try:
        invalidate = getattr(binance, "_invalidate_futures_positions_cache", None)
        if callable(invalidate):
            invalidate()
    except Exception as exc:
        _record_close_all_exception(binance, "submit_futures_order_invalidate_cache", exc)
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


def _build_market_close_params(
    binance,
    *,
    symbol: str,
    amount: float,
    position_side: str | None,
    dual: bool,
) -> tuple[dict[str, Any], str]:
    """Build an immediate, quantity-based close accepted by Binance USD-M."""
    side, target_ps, qty_raw = _derive_close_directive(amount, position_side, dual)
    step, min_qty, max_qty = _get_lot_limits(binance, symbol)
    qty_float = _quantize_qty(qty_raw, step, min_qty, max_qty)
    if qty_float <= 0.0:
        return {}, "validation"

    params: dict[str, Any] = {
        "symbol": symbol,
        "side": side,
        "type": "MARKET",
        "quantity": f"{qty_float:.8f}",
    }
    if dual and target_ps in ("LONG", "SHORT"):
        params["positionSide"] = target_ps
        return params, "positionSide"
    params["reduceOnly"] = True
    return params, "reduceOnly"


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


def _decimal_from_position(value: Any) -> Decimal:
    try:
        if value in (None, ""):
            return Decimal("0")
        return Decimal(str(value).strip())
    except (InvalidOperation, ValueError, TypeError):
        return Decimal("0")


def _format_decimal_amount(value: Decimal) -> str:
    try:
        if value <= 0:
            return "0"
        return format(value.normalize(), "f")
    except Exception:
        return str(value)


def _zero_qty_negative_isolated_margin_amount(row: Dict[str, Any]) -> Decimal:
    try:
        amt = _decimal_from_position(row.get("positionAmt"))
        if abs(amt) > Decimal("0"):
            return Decimal("0")
    except Exception:
        return Decimal("0")
    for key in ("isolatedWallet", "isolatedMargin", "margin", "positionMargin"):
        value = _decimal_from_position(row.get(key))
        if value < 0:
            return abs(value)
    return Decimal("0")


def _call_position_margin_add(binance, payload: dict) -> dict:
    client = getattr(binance, "client", None)
    unavailable_error: Exception | None = None
    method_names = (
        "futures_change_position_margin",
        "modify_isolated_position_margin",
        "futures_position_margin",
    )
    for name in method_names:
        method = getattr(client, name, None)
        if not callable(method):
            continue
        try:
            response = method(**payload) or {}
        except (AttributeError, NotImplementedError) as exc:
            unavailable_error = exc
            continue
        if not isinstance(response, dict):
            return {"response": response}
        return response

    request_api = getattr(client, "_request_futures_api", None)
    if callable(request_api):
        try:
            response = request_api("post", "positionMargin", signed=True, data=payload) or {}
            if not isinstance(response, dict):
                return {"response": response}
            return response
        except (AttributeError, NotImplementedError) as exc:
            unavailable_error = exc

    signed_request = getattr(binance, "_http_signed_futures_request", None)
    if callable(signed_request):
        try:
            prefix_func = getattr(binance, "_futures_api_prefix", None)
            prefix = prefix_func() if callable(prefix_func) else None
        except Exception:
            prefix = None
        response = signed_request("POST", "/v1/positionMargin", payload, prefix=prefix) or {}
        if response:
            return response if isinstance(response, dict) else {"response": response}
        try:
            last_error = getattr(binance, "_last_futures_http_error", None)
        except Exception:
            last_error = None
        if isinstance(last_error, dict):
            msg = str(last_error.get("message") or "").strip()
            code = last_error.get("code")
            if msg:
                if code is None:
                    raise RuntimeError(f"position margin cleanup rejected: {msg}")
                raise RuntimeError(f"position margin cleanup rejected (code={code}): {msg}")
        return {}

    if unavailable_error is not None:
        raise RuntimeError(
            f"position margin cleanup endpoint is not available for this Binance client: {unavailable_error}"
        ) from unavailable_error
    raise RuntimeError("position margin cleanup endpoint is not available for this Binance client")


def _raise_if_position_margin_error(response: dict) -> None:
    if not isinstance(response, dict):
        return
    if not response:
        raise RuntimeError("position margin cleanup rejected: empty response")
    code = response.get("code")
    if code is None:
        err_obj = response.get("error")
        if isinstance(err_obj, dict):
            code = err_obj.get("code")
            msg = err_obj.get("msg") or err_obj.get("message")
            if code is not None or msg:
                raise RuntimeError(f"position margin cleanup rejected (code={code}): {msg or err_obj}")
        return
    try:
        code_int = int(code)
    except Exception:
        code_int = None
    if code_int is not None and code_int < 0:
        msg = response.get("msg") or response.get("message") or response
        raise RuntimeError(f"position margin cleanup rejected (code={code_int}): {msg}")


def _cleanup_zero_qty_negative_margin_position(binance, row: Dict[str, Any], dual: bool) -> Dict[str, Any]:
    sym = str(row.get("symbol") or "").upper()
    pos_side = _normalize_position_side(row.get("positionSide"))
    amount = _zero_qty_negative_isolated_margin_amount(row)
    if not sym or amount <= 0:
        return {
            "ok": True,
            "symbol": sym or "?",
            "positionSide": pos_side,
            "skipped": True,
            "reason": "zero-qty-no-negative-isolated-margin",
        }
    amount_str = _format_decimal_amount(amount)
    payload = {
        "symbol": sym,
        "amount": amount_str,
        "type": 1,
    }
    if dual and pos_side in ("LONG", "SHORT"):
        payload["positionSide"] = pos_side
    elif pos_side and pos_side != "BOTH":
        payload["positionSide"] = pos_side
    try:
        info = _call_position_margin_add(binance, payload)
        _raise_if_position_margin_error(info)
        try:
            invalidate = getattr(binance, "_invalidate_futures_positions_cache", None)
            if callable(invalidate):
                invalidate()
        except Exception as exc:
            _record_close_all_exception(binance, "cleanup_negative_margin_invalidate_cache", exc)
        return {
            "ok": True,
            "symbol": sym,
            "positionSide": pos_side,
            "amount": amount_str,
            "info": info,
            "method": "positionMargin",
            "reason": "zero-qty-negative-isolated-margin",
        }
    except Exception as exc:
        return {
            "ok": False,
            "symbol": sym,
            "positionSide": pos_side,
            "amount": amount_str,
            "error": str(exc),
            "method": "positionMargin",
            "reason": "zero-qty-negative-isolated-margin",
        }


def _cleanup_zero_qty_negative_margin_positions(binance, dual: bool) -> List[Dict[str, Any]]:
    if not _is_testnet_wrapper(binance):
        return []
    positions, ok = _gather_positions(binance, include_zero_qty_residuals=True)
    if not ok:
        return []
    results: List[Dict[str, Any]] = []
    for row in positions:
        if not row.get("zeroQtyNegativeMargin"):
            continue
        results.append(_cleanup_zero_qty_negative_margin_position(binance, row, dual))
    return results


def _gather_positions(binance, *, include_zero_qty_residuals: bool = False) -> tuple[List[Dict[str, Any]], bool]:
    # Try position info first
    infos = None
    ok = False
    try:
        infos = binance.client.futures_position_information()
        ok = True
    except Exception:
        try:
            acct = binance.client.futures_account() or {}
            infos = acct.get("positions", [])
            ok = True
        except Exception:
            infos = []
            ok = False
    out: List[Dict[str, Any]] = []
    for p in infos or []:
        try:
            amt = float(p.get("positionAmt") or 0.0)
        except Exception:
            amt = 0.0
        if abs(amt) <= 0.0:
            residual_amount = (
                _zero_qty_negative_isolated_margin_amount(p)
                if include_zero_qty_residuals and isinstance(p, dict)
                else Decimal("0")
            )
            if residual_amount <= 0:
                continue
            out.append(
                {
                    "symbol": (p.get("symbol") or "").upper(),
                    "positionAmt": 0.0,
                    "positionSide": _normalize_position_side(p.get("positionSide")),
                    "zeroQtyNegativeMargin": True,
                    "negativeMarginAmount": _format_decimal_amount(residual_amount),
                    "isolatedWallet": p.get("isolatedWallet"),
                    "isolatedMargin": p.get("isolatedMargin"),
                    "margin": p.get("margin"),
                    "positionMargin": p.get("positionMargin"),
                }
            )
            continue
        out.append(
            {
                "symbol": (p.get("symbol") or "").upper(),
                "positionAmt": amt,
                "positionSide": _normalize_position_side(p.get("positionSide")),
            }
        )
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
        positions, _ = _gather_positions(binance)
        for sym in sorted({str(p.get("symbol") or "").upper() for p in positions} - {""}):
            _cancel_all(binance, sym)
        if positions and max_workers is None:
            max_workers = min(6, max(1, len(positions)))

        def _attempt_close_position(p):
            sym = p.get("symbol")
            pos_side = _normalize_position_side(p.get("positionSide"))
            try:
                amt = float(p.get("positionAmt") or 0.0)
            except Exception:
                amt = 0.0
            if abs(amt) <= 0:
                return {
                    "ok": True,
                    "symbol": sym,
                    "positionSide": pos_side,
                    "skipped": True,
                    "reason": "zero-qty",
                }
            try:
                params, method = _build_market_close_params(
                    binance,
                    symbol=sym,
                    amount=amt,
                    position_side=pos_side,
                    dual=dual,
                )
                if not params:
                    return {
                        "ok": False,
                        "symbol": sym,
                        "positionSide": pos_side,
                        "error": "position quantity cannot be safely represented by exchange lot-size filters",
                        "positionAmt": amt,
                        "method": method,
                    }
                od = _submit_futures_order(binance, params)
                return {
                    "ok": True,
                    "symbol": sym,
                    "positionSide": pos_side,
                    "info": od,
                    "method": method,
                }
            except Exception as e:
                return {
                    "ok": False,
                    "symbol": sym,
                    "positionSide": pos_side,
                    "error": str(e),
                    "positionAmt": amt,
                }

        if positions:
            with ThreadPoolExecutor(max_workers=max_workers) as executor:
                futures = [executor.submit(_attempt_close_position, p) for p in positions]
                for future in as_completed(futures):
                    try:
                        results.append(future.result())
                    except Exception as e:
                        results.append({"ok": False, "symbol": "?", "error": str(e)})

        result_index: dict[tuple[str, str], int] = {}

        def _result_key(res: dict) -> tuple[str, str] | None:
            sym = str(res.get("symbol") or "").upper()
            if not sym:
                return None
            side = _normalize_position_side(res.get("positionSide"))
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

        failures = [r for r in results if not r.get("ok")]
        if results:
            if any(_is_unknown_execution_error(r.get("error")) for r in failures):
                time.sleep(0.35)
            for _ in range(2):
                remaining, remaining_ok = _gather_positions(binance)
                if not remaining_ok or not remaining:
                    break
                for p in remaining:
                    _upsert_result(_attempt_close_position(p))
                if any(
                    _is_unknown_execution_error(r.get("error"))
                    for r in results
                    if not r.get("ok")
                ):
                    time.sleep(0.35)
            remaining, remaining_ok = _gather_positions(binance)
            if remaining_ok:
                open_symbols = {str(p.get("symbol") or "").upper() for p in remaining}
                for r in results:
                    if r.get("ok"):
                        continue
                    if not _is_unknown_execution_error(r.get("error")):
                        continue
                    sym = str(r.get("symbol") or "").upper()
                    if sym and sym not in open_symbols:
                        r["ok"] = True
                        r["reconciled"] = True
                for p in remaining:
                    key = _result_key(
                        {
                            "symbol": p.get("symbol"),
                            "positionSide": p.get("positionSide"),
                        }
                    )
                    if key is None:
                        continue
                    idx = result_index.get(key)
                    stale = {
                        "ok": False,
                        "symbol": key[0],
                        "positionSide": key[1],
                        "error": "position remained open after close attempts",
                        "positionAmt": p.get("positionAmt"),
                        "method": "verification",
                    }
                    if idx is None or results[idx].get("ok"):
                        _upsert_result(stale)
        results.extend(_cleanup_zero_qty_negative_margin_positions(binance, dual))
        return results

    # Up to 3 passes: handle partial fills and positions that change while the
    # close is in flight. Binance requires symbol-scoped cancel-all requests.
    canceled_symbols: set[str] = set()
    for _ in range(3):
        positions, _ = _gather_positions(binance)
        if not positions:
            break
        for p in positions:
            sym = p.get("symbol")
            pos_side = _normalize_position_side(p.get("positionSide"))
            try:
                amt = float(p.get("positionAmt") or 0.0)
                if abs(amt) <= 0:
                    continue
                if sym not in canceled_symbols:
                    _cancel_all(binance, sym)
                    canceled_symbols.add(sym)
                params, method = _build_market_close_params(
                    binance,
                    symbol=sym,
                    amount=amt,
                    position_side=pos_side,
                    dual=dual,
                )
                if not params:
                    results.append(
                        {
                            "ok": False,
                            "symbol": sym,
                            "positionSide": pos_side,
                            "error": "position quantity cannot be safely represented by exchange lot-size filters",
                            "positionAmt": amt,
                            "method": method,
                        }
                    )
                    continue
                try:
                    od = _submit_futures_order(binance, params)
                    results.append(
                        {
                            "ok": True,
                            "symbol": sym,
                            "positionSide": pos_side,
                            "info": od,
                            "method": method,
                        }
                    )
                    continue
                except Exception as e:
                    results.append(
                        {
                            "ok": False,
                            "symbol": sym,
                            "positionSide": pos_side,
                            "error": str(e),
                            "params": params,
                            "method": method,
                        }
                    )
            except Exception as e:
                results.append({"ok": False, "symbol": sym, "positionSide": pos_side, "error": str(e)})

    remaining, remaining_ok = _gather_positions(binance)
    if remaining_ok:
        remaining_by_key = {
            (
                str(p.get("symbol") or "").upper(),
                _normalize_position_side(p.get("positionSide")),
            ): p
            for p in remaining
            if str(p.get("symbol") or "").strip()
        }
        latest_by_key: dict[tuple[str, str], Dict[str, Any]] = {}
        result_order: list[tuple[str, str]] = []
        for result in results:
            key = (
                str(result.get("symbol") or "").upper(),
                _normalize_position_side(result.get("positionSide")),
            )
            if not key[0]:
                continue
            if key not in latest_by_key:
                result_order.append(key)
            latest_by_key[key] = result
        for key, position in remaining_by_key.items():
            if key not in latest_by_key:
                result_order.append(key)
            latest_by_key[key] = {
                "ok": False,
                "symbol": key[0],
                "positionSide": key[1],
                "error": "position remained open after close attempts",
                "positionAmt": position.get("positionAmt"),
                "method": "verification",
            }
        for key, result in latest_by_key.items():
            if key not in remaining_by_key and not result.get("ok"):
                result["ok"] = True
                result["reconciled"] = True
        results = [latest_by_key[key] for key in result_order]
    results.extend(_cleanup_zero_qty_negative_margin_positions(binance, dual))
    return results
