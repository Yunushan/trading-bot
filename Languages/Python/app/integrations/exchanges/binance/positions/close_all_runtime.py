from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor, as_completed
from decimal import Decimal, InvalidOperation, getcontext
import math
import time
from collections.abc import Mapping
from typing import Any, Dict, List

from app.security.redaction import redact_text

getcontext().prec = 28


def _cancel_response_accepted(response: object) -> bool:
    if not isinstance(response, Mapping) or not response:
        return False
    success = response.get("success", response.get("ok"))
    if isinstance(success, str):
        success = success.strip().lower() in {"true", "1", "yes", "ok"}
    if success is False or response.get("error"):
        return False
    code = response.get("code")
    if code is not None:
        try:
            return int(code) in {0, 200}
        except (TypeError, ValueError):
            return False
    return success is True or str(response.get("status") or "").upper() in {"OK", "SUCCESS", "ACCEPTED"}


def _record_close_all_exception(binance, context: str, exc: BaseException) -> None:
    message = redact_text(exc).replace("\n", " ")
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


def _cancel_all(binance, sym: str) -> bool:
    """Cancel a symbol's open orders before closing its position.

    A close submitted while an entry order remains open can recreate exposure
    immediately after the close fills.  Report whether cancellation was
    actually confirmed so callers can fail closed instead of treating a
    best-effort cancellation as a safety boundary.
    """
    try:
        response = binance.client.futures_cancel_all_open_orders(symbol=sym)
        if not _cancel_response_accepted(response):
            raise RuntimeError("exchange did not acknowledge bulk cancellation")
        return True
    except Exception as exc:
        _record_close_all_exception(binance, f"cancel_all_open_orders_bulk:{sym}", exc)
    # fallback: cancel one by one
    try:
        open_orders = binance.client.futures_get_open_orders(symbol=sym)
        if not isinstance(open_orders, (list, tuple)):
            _record_close_all_exception(binance, f"cancel_all_open_orders_invalid_snapshot:{sym}", RuntimeError("invalid response"))
            return False
        cancelled = True
        for o in open_orders:
            try:
                order_id = o.get("orderId") if isinstance(o, dict) else None
                if order_id in (None, ""):
                    raise RuntimeError("open order has no orderId")
                response = binance.client.futures_cancel_order(symbol=sym, orderId=order_id)
                if not _cancel_response_accepted(response):
                    raise RuntimeError("exchange did not acknowledge order cancellation")
            except Exception as exc:
                cancelled = False
                _record_close_all_exception(binance, f"cancel_open_order:{sym}", exc)
        return cancelled
    except Exception as exc:
        _record_close_all_exception(binance, f"cancel_all_open_orders_list:{sym}", exc)
        return False


def _close_order_response_accepted(response: object) -> bool:
    """Return whether an emergency-close order has a traceable exchange ID."""
    if not isinstance(response, Mapping) or not response:
        return False
    payload = response.get("data") if isinstance(response.get("data"), Mapping) else response
    if not isinstance(payload, Mapping) or not payload:
        return False
    success = payload.get("success", payload.get("ok"))
    if isinstance(success, str):
        success = success.strip().lower() in {"true", "1", "yes", "ok"}
    if success is False or payload.get("error"):
        return False
    code = payload.get("code")
    if code is not None:
        try:
            if int(code) not in {0, 200}:
                return False
        except (TypeError, ValueError):
            return False
    status = str(payload.get("status") or "").upper()
    if status in {"REJECTED", "EXPIRED", "CANCELED"}:
        return False
    return any(
        payload.get(key) not in (None, "")
        for key in ("orderId", "order_id", "id", "clientOrderId", "client_order_id", "clientOrderID")
    )


def _submit_futures_order(binance, params: dict) -> dict:
    """Place a futures order using wrapper fallback path when available."""
    submit = getattr(binance, "_futures_create_order_with_fallback", None)
    if callable(submit):
        order, _via = submit(dict(params))
        if not _close_order_response_accepted(order):
            raise RuntimeError("close order response was not explicitly acknowledged by the exchange")
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
    if not _close_order_response_accepted(order):
        raise RuntimeError("close order response was not explicitly acknowledged by the exchange")
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
        "newOrderRespType": "RESULT",
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
            "error": redact_text(exc),
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
    def validated_rows(value):
        if not isinstance(value, (list, tuple)):
            raise ValueError("position snapshot must be a list")
        rows = []
        for row in value:
            if not isinstance(row, Mapping):
                raise ValueError("position snapshot contains an invalid row")
            symbol = row.get("symbol")
            amount = row.get("positionAmt")
            if not isinstance(symbol, str) or not symbol.strip() or isinstance(amount, bool):
                raise ValueError("position snapshot is missing a valid symbol or quantity")
            try:
                decimal_amount = Decimal(str(amount))
                numeric_amount = float(decimal_amount)
            except (InvalidOperation, TypeError, ValueError, OverflowError) as exc:
                raise ValueError("position snapshot has an invalid quantity") from exc
            if not math.isfinite(numeric_amount) or (decimal_amount != 0 and numeric_amount == 0):
                raise ValueError("position snapshot has a nonfinite or unrepresentable quantity")
            if _normalize_position_side(row.get("positionSide")) not in {"BOTH", "LONG", "SHORT"}:
                raise ValueError("position snapshot has an invalid position side")
            rows.append({**row, "symbol": symbol.strip().upper(), "positionAmt": numeric_amount})
        return rows

    try:
        infos = validated_rows(binance.client.futures_position_information())
    except Exception:
        try:
            acct = binance.client.futures_account()
            infos = validated_rows(acct.get("positions") if isinstance(acct, Mapping) else None)
        except Exception as exc:
            _record_close_all_exception(binance, "position_snapshot_unavailable", exc)
            return [], False
    out: List[Dict[str, Any]] = []
    for p in infos:
        amt = p["positionAmt"]
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
    return out, True


def _position_scope(row: Mapping) -> dict[str, str]:
    position_side = _normalize_position_side(row.get("positionSide"))
    amount = float(row.get("positionAmt") or 0.0)
    side_key = ("L" if position_side == "LONG" else "S" if position_side == "SHORT"
                else "L" if amount > 0 else "S" if amount < 0 else "")
    return {"symbol": str(row.get("symbol") or "").strip().upper(),
            "positionSide": position_side, "side_key": side_key}


def _unverified_close_results(results: list[dict]) -> list[dict]:
    return [{**result, "ok": False, "position_closed": False,
             "error": "close verification unavailable; local exposure must be reconciled"}
            for result in results or [{}]]


def _finalize_close_results(binance, results: list[dict]) -> list[dict]:
    remaining, snapshot_ok = _gather_positions(binance)
    if not snapshot_ok:
        return _unverified_close_results(results)
    open_keys = {(_position_scope(row)["symbol"], _position_scope(row)["side_key"]): row for row in remaining}
    latest = {}
    for result in results:
        key = (str(result.get("symbol") or "").upper(), result.get("side_key", ""))
        latest[key] = dict(result)
    for key, row in open_keys.items():
        result = latest.setdefault(key, _position_scope(row))
        if result.get("ok", True):
            result.update(error="position remained open after close attempts", method="verification")
        result.update(ok=False, position_closed=False, remaining_qty=abs(row["positionAmt"]))
    for key, result in latest.items():
        if key in open_keys:
            continue
        if key[0] and key[1] in {"L", "S"} and not result.get("skipped"):
            # Flatness confirms the position state, not the fate of an unresolved order.
            # The durable intent ledger is never cleared by this account observation.
            if not result.get("ok"):
                result["reconciled"] = True
            result.update(ok=True, position_closed=True, remaining_qty=0.0)
        else:
            result["position_closed"] = False
    return list(latest.values())


def _is_testnet_wrapper(binance) -> bool:
    from app.settings.execution_mode import is_live_trading_mode

    return not is_live_trading_mode(getattr(binance, "mode", None))


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
        positions, snapshot_ok = _gather_positions(binance)
        if not snapshot_ok:
            return _unverified_close_results(results)
        cancel_failures: set[str] = set()
        for sym in sorted({str(p.get("symbol") or "").upper() for p in positions} - {""}):
            if not _cancel_all(binance, sym):
                cancel_failures.add(sym)
        if positions and max_workers is None:
            max_workers = min(6, max(1, len(positions)))

        def _attempt_close_position(p):
            sym = p.get("symbol")
            pos_side = _normalize_position_side(p.get("positionSide"))
            scope = _position_scope(p)
            normalized_sym = str(sym or "").upper()
            if normalized_sym in cancel_failures:
                return {
                    **scope,
                    "ok": False,
                    "symbol": sym,
                    "positionSide": pos_side,
                    "error": "open-order cancellation was not confirmed; close blocked to prevent re-opening exposure",
                    "method": "cancel-verification",
                }
            try:
                amt = float(p.get("positionAmt") or 0.0)
            except Exception:
                amt = 0.0
            if abs(amt) <= 0:
                return {
                    **scope,
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
                        **scope,
                        "ok": False,
                        "symbol": sym,
                        "positionSide": pos_side,
                        "error": "position quantity cannot be safely represented by exchange lot-size filters",
                        "positionAmt": amt,
                        "method": method,
                    }
                od = _submit_futures_order(binance, params)
                return {
                    **scope,
                    "ok": True,
                    "symbol": sym,
                    "positionSide": pos_side,
                    "info": od,
                    "method": method,
                }
            except Exception as e:
                return {
                    **scope,
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
            side = str(res.get("side_key") or "")
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
        results = _finalize_close_results(binance, results)
        results.extend(_cleanup_zero_qty_negative_margin_positions(binance, dual))
        return results

    # Up to 3 passes: handle partial fills and positions that change while the
    # close is in flight. Binance requires symbol-scoped cancel-all requests.
    canceled_symbols: set[str] = set()
    for _ in range(3):
        positions, snapshot_ok = _gather_positions(binance)
        if not snapshot_ok:
            return _unverified_close_results(results)
        if not positions:
            break
        for p in positions:
            sym = p.get("symbol")
            pos_side = _normalize_position_side(p.get("positionSide"))
            scope = _position_scope(p)
            try:
                amt = float(p.get("positionAmt") or 0.0)
                if abs(amt) <= 0:
                    continue
                if sym not in canceled_symbols:
                    if not _cancel_all(binance, sym):
                        results.append(
                            {
                                **scope,
                                "ok": False,
                                "symbol": sym,
                                "positionSide": pos_side,
                                "error": "open-order cancellation was not confirmed; close blocked to prevent re-opening exposure",
                                "method": "cancel-verification",
                            }
                        )
                        continue
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
                            **scope,
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
                            **scope,
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
                            **scope,
                            "ok": False,
                            "symbol": sym,
                            "positionSide": pos_side,
                            "error": str(e),
                            "params": params,
                            "method": method,
                        }
                    )
            except Exception as e:
                results.append({**scope, "ok": False, "error": str(e)})

    results = _finalize_close_results(binance, results)
    results.extend(_cleanup_zero_qty_negative_margin_positions(binance, dual))
    return results
