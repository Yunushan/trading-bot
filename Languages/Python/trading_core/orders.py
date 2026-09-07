from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
import math
from typing import Any


@dataclass(frozen=True, slots=True)
class OrderSubmitIntent:
    market: str
    symbol: str
    side: str
    order_type: str
    quantity: float | None = None
    price: float | None = None
    position_side: str = ""
    close_position: bool = False
    reduce_only: bool = False


@dataclass(frozen=True, slots=True)
class OrderExecution:
    executed_qty: float
    status: str
    complete: bool


def _execution_quantity(value: object) -> Decimal:
    if isinstance(value, bool) or value is None:
        raise ValueError("Execution quantity must be an explicit finite nonnegative number")
    try:
        number = Decimal(str(value))
    except (ValueError, InvalidOperation) as exc:
        raise ValueError("Execution quantity must be numeric") from exc
    if not number.is_finite() or number < 0 or not math.isfinite(float(number)) or (number != 0 and float(number) == 0):
        raise ValueError("Execution quantity must be finite and nonnegative")
    return number


def order_execution_from_response(
    response: object, submitted_qty: object, *, expected_params: Mapping[str, Any] | None = None,
) -> OrderExecution:
    """Read exchange-confirmed execution, never requested or submitted quantity."""
    if not isinstance(response, Mapping):
        raise ValueError("Order execution response must be an object")
    if expected_params is not None:
        for response_key, request_key in (("clientOrderId", "newClientOrderId"), ("symbol", "symbol"), ("side", "side")):
            expected = expected_params.get(request_key)
            if not expected or response.get(response_key) != expected:
                raise ValueError("Order execution does not identify the submitted order")
        if "positionSide" in response and response["positionSide"] != expected_params.get("positionSide", "BOTH"):
            raise ValueError("Order execution does not identify the submitted position side")
    submitted = _execution_quantity(submitted_qty)
    executed = _execution_quantity(response.get("executedQty"))
    status = response.get("status")
    if not isinstance(status, str) or status not in {
        "NEW", "PARTIALLY_FILLED", "FILLED", "CANCELED", "EXPIRED", "EXPIRED_IN_MATCH", "REJECTED",
    }:
        raise ValueError("Order execution status is missing or unsupported")
    if submitted <= 0 or executed > submitted:
        raise ValueError("Executed quantity exceeds the submitted order")
    if "origQty" in response and _execution_quantity(response["origQty"]) != submitted:
        raise ValueError("Order response quantity does not match the submitted order")
    if status in {"NEW", "REJECTED"} and executed != 0:
        raise ValueError("Unfilled order status conflicts with executed quantity")
    if status == "FILLED" and executed != submitted:
        raise ValueError("Filled order response does not confirm the submitted quantity")
    return OrderExecution(float(executed), str(status), status == "FILLED")


def confirmed_close_quantity(response: object, requested_qty: object) -> float:
    """Consume the close wrapper's explicit execution-confirmation contract."""
    if not isinstance(response, Mapping) or response.get("execution_confirmed") is not True:
        return 0.0
    executed = _execution_quantity(response.get("executed_qty"))
    if executed > _execution_quantity(requested_qty):
        raise ValueError("Confirmed close exceeds the requested quantity")
    return float(executed)


def _bool_param(value: object) -> bool:
    return str(value or "").strip().lower() in {"1", "true", "yes", "on"}


def _float_param(value: object) -> float | None:
    try:
        if value in (None, ""):
            return None
        return float(str(value).strip())
    except (TypeError, ValueError):
        return None


def order_submit_intent_from_params(market: str, params: Mapping[str, Any] | None) -> OrderSubmitIntent:
    payload = params if isinstance(params, Mapping) else {}
    return OrderSubmitIntent(
        market=str(market or "").strip().lower(),
        symbol=str(payload.get("symbol") or "").strip().upper(),
        side=str(payload.get("side") or "").strip().upper(),
        order_type=str(payload.get("type") or "").strip().upper(),
        quantity=_float_param(payload.get("quantity")),
        price=_float_param(payload.get("price")),
        position_side=str(payload.get("positionSide") or payload.get("position_side") or "").strip().upper(),
        close_position=_bool_param(payload.get("closePosition") or payload.get("close_position")),
        reduce_only=_bool_param(payload.get("reduceOnly") or payload.get("reduce_only")),
    )


def is_exchange_risk_reducing_order(market: str, params: Mapping[str, Any] | None) -> bool:
    """Classify exchange-enforced futures exits, not caller intent or UI aliases.

    This only controls the entry budget; normal validation and reconciliation
    remain required. Spot sells and unsupported conditional orders are not exempt.
    """
    if market != "futures" or not isinstance(params, Mapping):
        return False
    if params.get("type") not in ("LIMIT", "MARKET") or params.get("side") not in ("BUY", "SELL"):
        return False
    if "closePosition" in params:
        return False
    position_side = params.get("positionSide", "BOTH")
    if position_side == "BOTH":
        reduce_only = params.get("reduceOnly")
        return reduce_only is True or reduce_only == "true"
    # Binance hedge mode forbids reduceOnly; the closing side cannot open the
    # opposite position because positionSide binds the request to one hedge leg.
    return "reduceOnly" not in params and (params.get("side"), position_side) in (
        ("SELL", "LONG"), ("BUY", "SHORT"),
    )


def validate_order_submit_intent(intent: OrderSubmitIntent) -> tuple[str, ...]:
    errors: list[str] = []
    if intent.market not in {"futures", "spot"}:
        errors.append("order market must be futures or spot")
    if not intent.symbol:
        errors.append("order symbol is required")
    if intent.side not in {"BUY", "SELL"}:
        errors.append("order side must be BUY or SELL")
    if not intent.order_type:
        errors.append("order type is required")
    elif intent.order_type not in {"LIMIT", "MARKET"}:
        errors.append("order type must be LIMIT or MARKET")
    if intent.position_side and intent.position_side not in {"BOTH", "LONG", "SHORT"}:
        errors.append("positionSide must be BOTH, LONG, or SHORT")
    if intent.position_side and intent.market != "futures":
        errors.append("positionSide is only supported for futures")
    if intent.close_position and intent.market != "futures":
        errors.append("closePosition orders are only supported for futures")
    if intent.reduce_only and intent.market != "futures":
        errors.append("reduceOnly orders are only supported for futures")
    if intent.close_position and intent.reduce_only:
        errors.append("closePosition and reduceOnly cannot be used together")
    qty_required = intent.market != "futures" or not intent.close_position
    if qty_required and (intent.quantity is None or intent.quantity <= 0.0):
        errors.append("order quantity must be > 0")
    if intent.order_type == "LIMIT" and (intent.price is None or intent.price <= 0.0):
        errors.append("limit order price must be > 0")
    return tuple(errors)
