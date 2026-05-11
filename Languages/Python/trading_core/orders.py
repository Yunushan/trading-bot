from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True, slots=True)
class OrderSubmitIntent:
    market: str
    symbol: str
    side: str
    order_type: str
    quantity: float | None = None
    price: float | None = None
    close_position: bool = False
    reduce_only: bool = False


def _bool_param(value: object) -> bool:
    return str(value or "").strip().lower() in {"1", "true", "yes", "on"}


def _float_param(value: object) -> float | None:
    try:
        if value in (None, ""):
            return None
        return float(value)
    except Exception:
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
        close_position=_bool_param(payload.get("closePosition") or payload.get("close_position")),
        reduce_only=_bool_param(payload.get("reduceOnly") or payload.get("reduce_only")),
    )


def validate_order_submit_intent(intent: OrderSubmitIntent) -> tuple[str, ...]:
    errors: list[str] = []
    if not intent.symbol:
        errors.append("order symbol is required")
    if intent.side not in {"BUY", "SELL"}:
        errors.append("order side must be BUY or SELL")
    if not intent.order_type:
        errors.append("order type is required")
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
