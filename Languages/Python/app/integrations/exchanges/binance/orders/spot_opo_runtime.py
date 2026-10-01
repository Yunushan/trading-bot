"""Pure request and acknowledgement contracts for protected Binance Spot entries."""

from __future__ import annotations

from collections.abc import Mapping
from decimal import Decimal, InvalidOperation

from app.settings.live_safety import LiveTradingSafetyError


_CLIENT_ID_ALLOWED = frozenset("abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789._:/-")
_WORKING_STATUSES = frozenset({"FILLED"})
_PENDING_STATUSES = frozenset({"PENDING_NEW", "NEW", "FILLED"})
_LIST_STATUSES = frozenset({"EXEC_STARTED", "ALL_DONE"})
_CANCEL_REPLACE_SELL_STATUSES = frozenset({
    "NEW", "PARTIALLY_FILLED", "FILLED", "CANCELED", "EXPIRED", "EXPIRED_IN_MATCH",
})
_TERMINAL_SELL_STATUSES = frozenset({"FILLED", "CANCELED", "EXPIRED", "EXPIRED_IN_MATCH"})


def _decimal(value: object, name: str) -> Decimal:
    if isinstance(value, bool) or value is None:
        raise LiveTradingSafetyError(f"Spot OPO {name} must be a finite positive amount.")
    try:
        parsed = Decimal(str(value))
    except (InvalidOperation, ValueError):
        raise LiveTradingSafetyError(f"Spot OPO {name} must be a finite positive amount.") from None
    if not parsed.is_finite() or parsed <= 0:
        raise LiveTradingSafetyError(f"Spot OPO {name} must be a finite positive amount.")
    return parsed


def _nonnegative_decimal(value: object, name: str) -> Decimal:
    if isinstance(value, bool) or value is None:
        raise LiveTradingSafetyError(f"Spot OPO {name} must be a finite non-negative amount.")
    try:
        parsed = Decimal(str(value))
    except (InvalidOperation, ValueError):
        raise LiveTradingSafetyError(f"Spot OPO {name} must be a finite non-negative amount.") from None
    if not parsed.is_finite() or parsed < 0:
        raise LiveTradingSafetyError(f"Spot OPO {name} must be a finite non-negative amount.")
    return parsed


def _client_id(value: object, name: str) -> str:
    if (
        not isinstance(value, str)
        or not value
        or len(value) > 36
        or any(character not in _CLIENT_ID_ALLOWED for character in value)
    ):
        raise LiveTradingSafetyError(f"Spot OPO {name} is invalid.")
    return value


def _is_step_multiple(value: Decimal, step: Decimal) -> bool:
    return step == 0 or value % step == 0


def validate_spot_opo_request_payload(request: object) -> dict[str, str]:
    """Validate the fixed OPO request shape before durable intent or transport use."""
    required = {
        "symbol", "listClientOrderId", "workingClientOrderId", "pendingClientOrderId",
        "workingType", "workingSide", "workingPrice", "workingQuantity", "workingTimeInForce",
        "pendingType", "pendingSide", "pendingStopPrice", "newOrderRespType",
    }
    if not isinstance(request, Mapping) or set(request) != required:
        raise LiveTradingSafetyError("Spot OPO request parameters do not match the supported request contract.")
    if (
        not isinstance(request.get("symbol"), str)
        or not request["symbol"]
        or not request["symbol"].isascii()
        or not request["symbol"].isalnum()
        or request["symbol"] != request["symbol"].upper()
        or request.get("workingType") != "LIMIT"
        or request.get("workingSide") != "BUY"
        or request.get("workingTimeInForce") != "FOK"
        or request.get("pendingType") != "STOP_LOSS"
        or request.get("pendingSide") != "SELL"
        or request.get("newOrderRespType") != "FULL"
    ):
        raise LiveTradingSafetyError("Spot OPO request type, side, or time-in-force is unsupported.")
    list_id = _client_id(request.get("listClientOrderId"), "list client order ID")
    working_id = _client_id(request.get("workingClientOrderId"), "working client order ID")
    pending_id = _client_id(request.get("pendingClientOrderId"), "pending client order ID")
    if len({list_id, working_id, pending_id}) != 3:
        raise LiveTradingSafetyError("Spot OPO list and child order IDs must be distinct.")
    working_price = _decimal(request.get("workingPrice"), "working price")
    _decimal(request.get("workingQuantity"), "working quantity")
    stop_price = _decimal(request.get("pendingStopPrice"), "pending stop price")
    if stop_price >= working_price:
        raise LiveTradingSafetyError("Spot OPO stop price must be below the LIMIT BUY price.")
    return {str(key): str(value) for key, value in request.items()}


def build_spot_opo_request(
    *,
    symbol: str,
    symbol_info: Mapping[str, object],
    working_price: object,
    working_quantity: object,
    pending_stop_price: object,
    list_client_order_id: str,
    working_client_order_id: str,
    pending_client_order_id: str,
) -> dict[str, str]:
    """Build a FOK LIMIT BUY paired with an OPO-managed STOP_LOSS SELL.

    FOK is required because Binance only activates the pending OPO leg after
    the working order is fully filled. A partial working fill must not create
    a local position with no exchange-resident stop.
    """
    if (
        not isinstance(symbol, str)
        or not symbol
        or not symbol.isascii()
        or not symbol.isalnum()
        or symbol != symbol.upper()
        or symbol_info.get("symbol") != symbol
        or symbol_info.get("status") != "TRADING"
        or symbol_info.get("quoteAsset") != "USDT"
        or symbol_info.get("isSpotTradingAllowed") is not True
        or symbol_info.get("otoAllowed") is not True
        or symbol_info.get("opoAllowed") is not True
    ):
        raise LiveTradingSafetyError("Spot symbol is not verified as eligible for USDT OPO trading.")

    price = _decimal(working_price, "working price")
    quantity = _decimal(working_quantity, "working quantity")
    stop_price = _decimal(pending_stop_price, "pending stop price")
    if stop_price >= price:
        raise LiveTradingSafetyError("Spot OPO stop price must be below the LIMIT BUY price.")

    filters = symbol_info.get("filters")
    if not isinstance(filters, list):
        raise LiveTradingSafetyError("Spot OPO symbol filters are missing.")
    by_type: dict[str, Mapping[str, object]] = {}
    for row in filters:
        if not isinstance(row, Mapping) or not isinstance(row.get("filterType"), str):
            raise LiveTradingSafetyError("Spot OPO symbol filters are malformed.")
        kind = str(row["filterType"])
        if kind in by_type:
            raise LiveTradingSafetyError("Spot OPO symbol filters contain a duplicate rule.")
        by_type[kind] = row

    lot = by_type.get("LOT_SIZE")
    price_filter = by_type.get("PRICE_FILTER")
    if not isinstance(lot, Mapping) or not isinstance(price_filter, Mapping):
        raise LiveTradingSafetyError("Spot OPO requires LOT_SIZE and PRICE_FILTER metadata.")
    step = _decimal(lot.get("stepSize"), "quantity step")
    min_qty = _decimal(lot.get("minQty"), "minimum quantity")
    max_qty = _decimal(lot.get("maxQty"), "maximum quantity")
    tick = _decimal(price_filter.get("tickSize"), "price tick")
    min_price = _nonnegative_decimal(price_filter.get("minPrice"), "minimum price")
    max_price = _decimal(price_filter.get("maxPrice"), "maximum price")
    if (
        quantity < min_qty
        or quantity > max_qty
        or price < min_price
        or price > max_price
        or stop_price < min_price
        or stop_price > max_price
        or not _is_step_multiple(quantity, step)
        or not _is_step_multiple(price, tick)
        or not _is_step_multiple(stop_price, tick)
    ):
        raise LiveTradingSafetyError("Spot OPO price or quantity violates the symbol tick/lot filters.")

    notionals = []
    for kind in ("MIN_NOTIONAL", "NOTIONAL"):
        rule = by_type.get(kind)
        if rule is not None:
            raw = rule.get("minNotional")
            if raw is None:
                raw = rule.get("notional")
            notionals.append(_nonnegative_decimal(raw, "minimum notional"))
    min_notional = max(notionals, default=Decimal(0))
    if min_notional and price * quantity < min_notional:
        raise LiveTradingSafetyError("Spot OPO working order is below the symbol minimum notional.")

    identifiers = (
        _client_id(list_client_order_id, "list client order ID"),
        _client_id(working_client_order_id, "working client order ID"),
        _client_id(pending_client_order_id, "pending client order ID"),
    )
    if len(set(identifiers)) != 3:
        raise LiveTradingSafetyError("Spot OPO list and child order IDs must be distinct.")

    return validate_spot_opo_request_payload({
        "symbol": symbol,
        "listClientOrderId": identifiers[0],
        "workingClientOrderId": identifiers[1],
        "pendingClientOrderId": identifiers[2],
        "workingType": "LIMIT",
        "workingSide": "BUY",
        "workingPrice": format(price, "f"),
        "workingQuantity": format(quantity, "f"),
        "workingTimeInForce": "FOK",
        "pendingType": "STOP_LOSS",
        "pendingSide": "SELL",
        "pendingStopPrice": format(stop_price, "f"),
        "newOrderRespType": "FULL",
    })


def validate_spot_opo_acknowledgement(
    response: object,
    request: Mapping[str, str],
) -> dict[str, object]:
    """Validate that a full OPO acknowledgement identifies both expected legs."""
    request = validate_spot_opo_request_payload(request)
    if not isinstance(response, Mapping):
        raise LiveTradingSafetyError("Binance Spot OPO acknowledgement is missing or malformed.")
    symbol = request.get("symbol")
    list_client_id = request.get("listClientOrderId")
    working_client_id = request.get("workingClientOrderId")
    pending_client_id = request.get("pendingClientOrderId")
    list_id = response.get("orderListId")
    list_status = response.get("listStatusType")
    if (
        response.get("symbol") != symbol
        or response.get("listClientOrderId") != list_client_id
        or response.get("contingencyType") != "OTO"
        or type(list_id) is not int
        or list_id < 0
        or list_status not in _LIST_STATUSES
    ):
        raise LiveTradingSafetyError("Binance Spot OPO acknowledgement conflicts with its persisted request.")

    orders = response.get("orders")
    reports = response.get("orderReports")
    if not isinstance(orders, list) or len(orders) != 2 or not isinstance(reports, list) or len(reports) != 2:
        raise LiveTradingSafetyError("Binance Spot OPO acknowledgement must identify exactly two child orders.")

    expected_ids = {working_client_id, pending_client_id}
    if (
        not isinstance(symbol, str)
        or not isinstance(list_client_id, str)
        or not isinstance(working_client_id, str)
        or not isinstance(pending_client_id, str)
        or len(expected_ids) != 2
        or list_client_id in expected_ids
    ):
        raise LiveTradingSafetyError("Spot OPO acknowledgement request identities are invalid.")
    order_rows: dict[str, Mapping[str, object]] = {}
    for row in orders:
        if (
            not isinstance(row, Mapping)
            or row.get("symbol") != symbol
            or row.get("clientOrderId") not in expected_ids
            or row.get("clientOrderId") in order_rows
        ):
            raise LiveTradingSafetyError("Binance Spot OPO child order identity is invalid.")
        child_id = row.get("orderId")
        if type(child_id) is not int or child_id <= 0:
            raise LiveTradingSafetyError("Binance Spot OPO child order ID is invalid.")
        order_rows[str(row["clientOrderId"])] = row
    if set(order_rows) != expected_ids:
        raise LiveTradingSafetyError("Binance Spot OPO acknowledgement is missing an expected child order.")

    report_rows: dict[str, Mapping[str, object]] = {}
    for row in reports:
        if (
            not isinstance(row, Mapping)
            or row.get("symbol") != symbol
            or row.get("orderListId") != list_id
            or row.get("clientOrderId") not in expected_ids
            or row.get("clientOrderId") in report_rows
            or row.get("orderId") != order_rows.get(str(row.get("clientOrderId")), {}).get("orderId")
        ):
            raise LiveTradingSafetyError("Binance Spot OPO child report conflicts with its order identity.")
        report_rows[str(row["clientOrderId"])] = row
    if set(report_rows) != expected_ids:
        raise LiveTradingSafetyError("Binance Spot OPO acknowledgement is missing a child order report.")

    working = report_rows[str(working_client_id)]
    pending = report_rows[str(pending_client_id)]
    working_executed = _decimal(working.get("executedQty"), "filled working quantity")
    working_original = _decimal(working.get("origQty"), "working order quantity")
    pending_executed = _nonnegative_decimal(pending.get("executedQty"), "pending executed quantity")
    if (
        working.get("type") != "LIMIT"
        or working.get("side") != "BUY"
        or working.get("timeInForce") != "FOK"
        or working.get("status") not in _WORKING_STATUSES
        or working_executed != working_original
        or working_original != _decimal(request.get("workingQuantity"), "requested working quantity")
        or pending.get("type") != "STOP_LOSS"
        or pending.get("side") != "SELL"
        or pending.get("status") not in _PENDING_STATUSES
        or (pending.get("status") in {"PENDING_NEW", "NEW"} and pending_executed != 0)
        or (pending.get("status") == "FILLED" and pending_executed <= 0)
        or _decimal(pending.get("stopPrice"), "acknowledged stop price")
        != _decimal(request.get("pendingStopPrice"), "requested stop price")
    ):
        raise LiveTradingSafetyError("Binance Spot OPO child order types or states conflict with the request.")

    return {
        "order_list_id": list_id,
        "list_client_order_id": list_client_id,
        "list_status": list_status,
        "working_order_id": working["orderId"],
        "working_status": working["status"],
        "working_executed_qty": format(working_executed, "f"),
        "pending_order_id": pending["orderId"],
        "pending_status": pending["status"],
        "pending_executed_qty": format(pending_executed, "f"),
    }


def build_spot_opo_cancel_replace_request(
    intent: object,
    *,
    new_order_client_id: str,
    cancel_new_client_order_id: str | None = None,
) -> dict[str, object]:
    """Build a full-position strategy SELL that replaces one active OPO stop.

    This only prepares the exchange request. The caller must persist a linked
    exit intent first and must handle cancel-success/new-order-failure by
    reconciling and restoring protection before allowing another submission.
    """
    if not isinstance(intent, Mapping):
        raise LiveTradingSafetyError("A recovered Spot OPO intent is required for strategy exit.")
    request = validate_spot_opo_request_payload(intent.get("request"))
    try:
        order_id = intent.get("pending_order_id")
        entry_quantity = _decimal(intent.get("entry_portfolio_quantity"), "recovered entry quantity")
        pending_quantity = _decimal(intent.get("pending_original_qty"), "active stop quantity")
        pending_executed = _nonnegative_decimal(intent.get("pending_executed_qty"), "active stop execution")
    except LiveTradingSafetyError:
        raise LiveTradingSafetyError("Spot OPO strategy exit requires exact recovered entry and stop quantities.") from None
    exit_client_id = _client_id(new_order_client_id, "strategy exit client order ID")
    if (
        intent.get("market") != "spot"
        or intent.get("type") != "OPO"
        or intent.get("state") != "accepted"
        or intent.get("symbol") != request["symbol"]
        or intent.get("protection_state") != "active"
        or intent.get("entry_reconciled") is not True
        or (
            intent.get("cancel_state") is not None
            and not (intent.get("cancel_state") == "rejected" and intent.get("strategy_exit_state") == "no_effect")
        )
        or intent.get("strategy_exit_state") not in (None, "no_effect")
        or intent.get("residual_stop_state") is not None
        or intent.get("list_status") != "EXEC_STARTED"
        or intent.get("working_status") != "FILLED"
        or intent.get("pending_status") != "NEW"
        or type(order_id) is not int or order_id <= 0
        or entry_quantity != pending_quantity
        or pending_executed != 0
        or exit_client_id in {
            request["listClientOrderId"],
            request["workingClientOrderId"],
            request["pendingClientOrderId"],
        }
    ):
        raise LiveTradingSafetyError("Spot OPO strategy exit requires one exact active, fully recovered stop.")
    from .spot_opo_exit_retry_runtime import validate_spot_opo_no_effect_proof

    if intent.get("strategy_exit_state") == "no_effect":
        validate_spot_opo_no_effect_proof(intent, intent.get("strategy_exit_no_effect_proof"))
    used_exit_ids = {intent.get("strategy_exit_client_order_id")}
    used_exit_ids.update(
        prior.get("strategy_exit_client_order_id") for prior in intent.get("strategy_exit_history", [])
        if isinstance(prior, Mapping)
    )
    if exit_client_id in used_exit_ids:
        raise LiveTradingSafetyError("Linked Spot SELL client order ID was already used in this ledger.")
    payload: dict[str, object] = {
        "symbol": request["symbol"],
        "side": "SELL",
        "type": "MARKET",
        "cancelReplaceMode": "STOP_ON_FAILURE",
        "cancelOrderId": order_id,
        "cancelOrigClientOrderId": request["pendingClientOrderId"],
        "cancelRestrictions": "ONLY_NEW",
        "quantity": format(pending_quantity, "f"),
        "newClientOrderId": exit_client_id,
        "newOrderRespType": "FULL",
    }
    if cancel_new_client_order_id is not None:
        payload["cancelNewClientOrderId"] = cancel_new_client_order_id
    return validate_spot_opo_cancel_replace_request(payload)


def validate_spot_opo_cancel_replace_request(request: object) -> dict[str, object]:
    """Validate the fixed, full-quantity OPO-stop replacement request."""
    required = {
        "symbol", "side", "type", "cancelReplaceMode", "cancelOrderId",
        "cancelOrigClientOrderId", "cancelRestrictions", "quantity",
        "newClientOrderId", "newOrderRespType",
    }
    if not isinstance(request, Mapping) or set(request) not in (required, required | {"cancelNewClientOrderId"}):
        raise LiveTradingSafetyError("Spot OPO strategy-exit request does not match the supported contract.")
    symbol = request.get("symbol")
    if (
        not isinstance(symbol, str)
        or not symbol or not symbol.isascii() or not symbol.isalnum() or symbol != symbol.upper()
        or request.get("side") != "SELL"
        or request.get("type") != "MARKET"
        or request.get("cancelReplaceMode") != "STOP_ON_FAILURE"
        or request.get("cancelRestrictions") != "ONLY_NEW"
        or request.get("newOrderRespType") != "FULL"
    ):
        raise LiveTradingSafetyError("Spot OPO strategy-exit request mode or order type is unsupported.")
    cancel_order_id = request.get("cancelOrderId")
    if type(cancel_order_id) is not int or cancel_order_id <= 0:
        raise LiveTradingSafetyError("Spot OPO strategy-exit child order ID is invalid.")
    cancel_client_id = _client_id(request.get("cancelOrigClientOrderId"), "linked stop client order ID")
    exit_client_id = _client_id(request.get("newClientOrderId"), "strategy exit client order ID")
    if cancel_client_id == exit_client_id:
        raise LiveTradingSafetyError("Spot OPO stop and strategy exit client IDs must be distinct.")
    quantity = _decimal(request.get("quantity"), "strategy exit quantity")
    normalized: dict[str, object] = {
        "symbol": symbol,
        "side": "SELL",
        "type": "MARKET",
        "cancelReplaceMode": "STOP_ON_FAILURE",
        "cancelOrderId": cancel_order_id,
        "cancelOrigClientOrderId": cancel_client_id,
        "cancelRestrictions": "ONLY_NEW",
        "quantity": format(quantity, "f"),
        "newClientOrderId": exit_client_id,
        "newOrderRespType": "FULL",
    }
    if "cancelNewClientOrderId" in request:
        alias = _client_id(request["cancelNewClientOrderId"], "canceled stop client order ID")
        if alias in {cancel_client_id, exit_client_id}:
            raise LiveTradingSafetyError("Canceled stop and exit client IDs must be distinct.")
        normalized["cancelNewClientOrderId"] = alias
    return normalized


def validate_spot_opo_cancel_replace_response(
    response: object,
    request: object,
) -> dict[str, object]:
    """Classify exact Binance cancel-replace outcomes without resolving inventory.

    Every outcome still needs exact OPO/order queries and fee-aware portfolio
    recovery. A canceled stop with a rejected replacement also requires re-arm.
    """
    normalized_request = validate_spot_opo_cancel_replace_request(request)
    if not isinstance(response, Mapping):
        raise LiveTradingSafetyError("Binance cancel-replace response is missing or malformed.")
    payload = response.get("data") if isinstance(response.get("data"), Mapping) else response
    if not isinstance(payload, Mapping):
        raise LiveTradingSafetyError("Binance cancel-replace response is missing its result data.")
    cancel_result = payload.get("cancelResult")
    new_result = payload.get("newOrderResult")
    cancel_response = payload.get("cancelResponse")
    new_response = payload.get("newOrderResponse")
    if cancel_result == "FAILURE" and new_result == "NOT_ATTEMPTED":
        if (
            not isinstance(cancel_response, Mapping)
            or type(cancel_response.get("code")) is not int
            or new_response is not None
        ):
            raise LiveTradingSafetyError("Binance cancel-replace failure response conflicts with STOP_ON_FAILURE.")
        return {
            "outcome": "cancel_failed",
            "cancel_confirmed": False,
            "new_order_accepted": False,
            "requires_exact_reconciliation": True,
            "requires_stop_rearm": False,
        }
    if cancel_result != "SUCCESS" or not isinstance(cancel_response, Mapping):
        raise LiveTradingSafetyError("Binance cancel-replace response does not prove the linked stop outcome.")

    try:
        canceled_order_id = cancel_response.get("orderId")
        canceled_executed = _nonnegative_decimal(cancel_response.get("executedQty"), "canceled stop execution")
    except LiveTradingSafetyError:
        raise LiveTradingSafetyError("Binance cancel-replace response has invalid canceled-stop quantities.") from None
    if (
        cancel_response.get("symbol") != normalized_request["symbol"]
        or cancel_response.get("origClientOrderId") != normalized_request["cancelOrigClientOrderId"]
        or canceled_order_id != normalized_request["cancelOrderId"]
        or cancel_response.get("side") != "SELL"
        or cancel_response.get("status") != "CANCELED"
        or canceled_executed != 0
        or ("clientOrderId" in cancel_response and "cancelNewClientOrderId" in normalized_request
            and cancel_response["clientOrderId"] != normalized_request["cancelNewClientOrderId"])
    ):
        raise LiveTradingSafetyError("Binance cancel-replace canceled a different or executed stop order.")

    if new_result == "FAILURE":
        if not isinstance(new_response, Mapping) or type(new_response.get("code")) is not int:
            raise LiveTradingSafetyError("Binance cancel-replace new-order failure is missing exact error evidence.")
        return {
            "outcome": "stop_canceled_exit_rejected",
            "cancel_confirmed": True,
            "new_order_accepted": False,
            "requires_exact_reconciliation": True,
            "requires_stop_rearm": True,
        }
    if new_result != "SUCCESS" or not isinstance(new_response, Mapping):
        raise LiveTradingSafetyError("Binance cancel-replace response does not prove the replacement SELL outcome.")
    try:
        original_quantity = _decimal(new_response.get("origQty"), "replacement SELL quantity")
        executed_quantity = _nonnegative_decimal(new_response.get("executedQty"), "replacement SELL execution")
    except LiveTradingSafetyError:
        raise LiveTradingSafetyError("Binance cancel-replace replacement quantities are invalid.") from None
    order_id = new_response.get("orderId")
    status = new_response.get("status")
    if (
        new_response.get("symbol") != normalized_request["symbol"]
        or new_response.get("clientOrderId") != normalized_request["newClientOrderId"]
        or new_response.get("side") != "SELL"
        or new_response.get("type") != "MARKET"
        or type(order_id) is not int or order_id <= 0
        or status not in _CANCEL_REPLACE_SELL_STATUSES
        or original_quantity != _decimal(normalized_request["quantity"], "requested exit quantity")
        or executed_quantity > original_quantity
        or (status == "FILLED" and executed_quantity != original_quantity)
        or (status in {"NEW", "CANCELED", "EXPIRED", "EXPIRED_IN_MATCH"} and executed_quantity >= original_quantity)
        or (status == "NEW" and executed_quantity != 0)
        or (status == "PARTIALLY_FILLED" and not 0 < executed_quantity < original_quantity)
    ):
        raise LiveTradingSafetyError("Binance cancel-replace replacement SELL conflicts with its exact request.")
    full_execution = status == "FILLED" and executed_quantity == original_quantity
    return {
        "outcome": "exit_sell_accepted",
        "cancel_confirmed": True,
        "new_order_accepted": True,
        "new_order_id": order_id,
        "new_order_status": status,
        "executed_qty": format(executed_quantity, "f"),
        "requires_exact_reconciliation": True,
        "requires_stop_rearm": not full_execution,
    }


def validate_spot_opo_strategy_exit_order(
    response: object, request: object,
) -> dict[str, object]:
    """Validate an exact query of the individual SELL created by cancel-replace."""
    normalized_request = validate_spot_opo_cancel_replace_request(request)
    if (
        not isinstance(response, Mapping)
        or "code" in response
        or response.get("error") is not None
        or response.get("symbol") != normalized_request["symbol"]
        or response.get("clientOrderId") != normalized_request["newClientOrderId"]
        or response.get("side") != "SELL"
        or response.get("type") != "MARKET"
        or response.get("orderListId") != -1
        or type(response.get("orderId")) is not int
        or response["orderId"] <= 0
        or response.get("status") not in _CANCEL_REPLACE_SELL_STATUSES
    ):
        raise LiveTradingSafetyError("Binance linked Spot SELL query conflicts with its exact durable intent.")
    original = _decimal(response.get("origQty"), "linked SELL original quantity")
    executed = _nonnegative_decimal(response.get("executedQty"), "linked SELL executed quantity")
    requested = _decimal(normalized_request["quantity"], "linked SELL requested quantity")
    status = str(response["status"])
    if (
        original != requested
        or executed > requested
        or (status == "NEW" and executed != 0)
        or (status == "PARTIALLY_FILLED" and not 0 < executed < requested)
        or (status == "FILLED" and executed != requested)
        or (status in {"CANCELED", "EXPIRED", "EXPIRED_IN_MATCH"} and executed >= requested)
    ):
        raise LiveTradingSafetyError("Binance linked Spot SELL quantity or status conflicts with its durable intent.")
    return {
        "order_id": response["orderId"],
        "status": status,
        "original_quantity": format(original, "f"),
        "executed_quantity": format(executed, "f"),
        "terminal": status in _TERMINAL_SELL_STATUSES,
    }


def validate_spot_opo_residual_stop_request(request: object) -> dict[str, str]:
    """Validate one standalone STOP_LOSS SELL for the exact OPO residual."""
    required = {
        "symbol", "side", "type", "quantity", "stopPrice", "newClientOrderId", "newOrderRespType",
    }
    if not isinstance(request, Mapping) or set(request) != required:
        raise LiveTradingSafetyError("Spot residual-stop request does not match the supported contract.")
    symbol = request.get("symbol")
    if (
        not isinstance(symbol, str) or not symbol or not symbol.isascii()
        or not symbol.isalnum() or symbol != symbol.upper()
        or request.get("side") != "SELL"
        or request.get("type") != "STOP_LOSS"
        or request.get("newOrderRespType") != "FULL"
    ):
        raise LiveTradingSafetyError("Spot residual-stop request type or side is unsupported.")
    quantity = _decimal(request.get("quantity"), "residual stop quantity")
    stop_price = _decimal(request.get("stopPrice"), "residual stop price")
    client_id = _client_id(request.get("newClientOrderId"), "residual stop client order ID")
    return {
        "symbol": symbol,
        "side": "SELL",
        "type": "STOP_LOSS",
        "quantity": format(quantity, "f"),
        "stopPrice": format(stop_price, "f"),
        "newClientOrderId": client_id,
        "newOrderRespType": "FULL",
    }


def build_spot_opo_residual_stop_request(
    intent: object,
    *,
    symbol_info: Mapping[str, object],
    quantity: object,
    last_price: object,
    average_price: object | None,
    average_price_mins: object | None,
    new_client_order_id: str,
) -> dict[str, str]:
    """Build a filtered standalone stop for one recovered residual OPO allocation.

    The old linked OPO stop must already be exactly canceled. Quantity is the
    current fee-aware desktop allocation after terminal linked SELL recovery.
    """
    if not isinstance(intent, Mapping):
        raise LiveTradingSafetyError("A recovered Spot OPO is required for residual protection.")
    original = validate_spot_opo_request_payload(intent.get("request"))
    if (
        intent.get("market") != "spot"
        or intent.get("type") != "OPO"
        or intent.get("state") != "accepted"
        or intent.get("symbol") != original["symbol"]
        or intent.get("entry_reconciled") is not True
        or intent.get("cancel_state") != "confirmed"
        or intent.get("protection_state") != "cancelled"
        or intent.get("residual_stop_state") != "rearm_required"
        or symbol_info.get("symbol") != original["symbol"]
        or symbol_info.get("status") != "TRADING"
        or symbol_info.get("isSpotTradingAllowed") is not True
    ):
        raise LiveTradingSafetyError("Residual protection requires one exactly canceled, recovered OPO and a trading symbol.")
    stop_price = _decimal(original["pendingStopPrice"], "original stop price")
    residual_quantity = _decimal(quantity, "residual allocation quantity")
    entry_quantity = _decimal(intent.get("entry_portfolio_quantity"), "OPO entry quantity")
    current = _decimal(last_price, "last traded price")
    if residual_quantity > entry_quantity:
        raise LiveTradingSafetyError("Residual stop quantity exceeds the recovered OPO entry allocation.")
    if current <= stop_price:
        raise LiveTradingSafetyError("Original stop price is at or above the current market; immediate-trigger race must be reconciled.")

    filters = symbol_info.get("filters")
    if not isinstance(filters, list):
        raise LiveTradingSafetyError("Spot residual-stop symbol filters are missing.")
    by_type: dict[str, Mapping[str, object]] = {}
    for row in filters:
        if not isinstance(row, Mapping) or not isinstance(row.get("filterType"), str):
            raise LiveTradingSafetyError("Spot residual-stop symbol filters are malformed.")
        kind = str(row["filterType"])
        if kind in by_type:
            raise LiveTradingSafetyError("Spot residual-stop symbol filters contain a duplicate rule.")
        by_type[kind] = row

    price_filter = by_type.get("PRICE_FILTER")
    lot_filter = by_type.get("LOT_SIZE")
    market_lot_filter = by_type.get("MARKET_LOT_SIZE")
    if not isinstance(price_filter, Mapping) or not isinstance(lot_filter, Mapping) or not isinstance(market_lot_filter, Mapping):
        raise LiveTradingSafetyError("Spot residual stop requires PRICE_FILTER, LOT_SIZE and MARKET_LOT_SIZE metadata.")
    min_price = _nonnegative_decimal(price_filter.get("minPrice"), "minimum stop price")
    max_price = _nonnegative_decimal(price_filter.get("maxPrice"), "maximum stop price")
    tick = _nonnegative_decimal(price_filter.get("tickSize"), "stop price tick")
    if (
        (min_price > 0 and stop_price < min_price)
        or (max_price > 0 and stop_price > max_price)
        or (tick > 0 and not _is_step_multiple(stop_price, tick))
    ):
        raise LiveTradingSafetyError("Original OPO stop price violates the current Spot PRICE_FILTER.")

    def check_quantity_filter(rule: Mapping[str, object], label: str) -> None:
        minimum = _nonnegative_decimal(rule.get("minQty"), f"{label} minimum quantity")
        maximum = _nonnegative_decimal(rule.get("maxQty"), f"{label} maximum quantity")
        step = _nonnegative_decimal(rule.get("stepSize"), f"{label} quantity step")
        if (
            (minimum > 0 and residual_quantity < minimum)
            or (maximum > 0 and residual_quantity > maximum)
            or (step > 0 and not _is_step_multiple(residual_quantity, step))
        ):
            raise LiveTradingSafetyError(f"Spot residual stop quantity violates the current {label} filter.")

    check_quantity_filter(lot_filter, "LOT_SIZE")
    check_quantity_filter(market_lot_filter, "MARKET_LOT_SIZE")

    avg_price_value: Decimal | None = None
    if average_price is not None:
        avg_price_value = _decimal(average_price, "average market price")
    if average_price_mins is not None and (type(average_price_mins) is not int or average_price_mins < 0):
        raise LiveTradingSafetyError("Spot average-price window is invalid.")
    for kind in ("MIN_NOTIONAL", "NOTIONAL"):
        rule = by_type.get(kind)
        if rule is None:
            continue
        if kind == "MIN_NOTIONAL":
            apply_min = rule.get("applyToMarket")
            apply_max = False
            min_raw = rule.get("minNotional")
            max_raw = None
        else:
            apply_min = rule.get("applyMinToMarket")
            apply_max = rule.get("applyMaxToMarket")
            min_raw = rule.get("minNotional")
            max_raw = rule.get("maxNotional")
        if type(apply_min) is not bool or type(apply_max) is not bool:
            raise LiveTradingSafetyError(f"Spot {kind} market-application flags are missing or invalid.")
        if not apply_min and not apply_max:
            continue
        filter_minutes = rule.get("avgPriceMins")
        if type(filter_minutes) is not int or filter_minutes < 0:
            raise LiveTradingSafetyError(f"Spot {kind} average-price window is missing or invalid.")
        if filter_minutes == 0:
            reference_price = current
        elif filter_minutes == average_price_mins and avg_price_value is not None:
            reference_price = avg_price_value
        else:
            raise LiveTradingSafetyError(f"Spot {kind} market notional reference price cannot be verified exactly.")
        notional = residual_quantity * reference_price
        if apply_min:
            minimum_notional = _nonnegative_decimal(min_raw, f"{kind} minimum notional")
            if minimum_notional > 0 and notional < minimum_notional:
                raise LiveTradingSafetyError(f"Spot residual stop is below the current {kind} minimum notional.")
        if apply_max:
            maximum_notional = _nonnegative_decimal(max_raw, f"{kind} maximum notional")
            if maximum_notional > 0 and notional > maximum_notional:
                raise LiveTradingSafetyError(f"Spot residual stop exceeds the current {kind} maximum notional.")

    return validate_spot_opo_residual_stop_request({
        "symbol": original["symbol"],
        "side": "SELL",
        "type": "STOP_LOSS",
        "quantity": format(residual_quantity, "f"),
        "stopPrice": format(stop_price, "f"),
        "newClientOrderId": new_client_order_id,
        "newOrderRespType": "FULL",
    })


def validate_spot_opo_residual_stop_order(
    response: object, request: object,
) -> dict[str, object]:
    """Validate the exact REST acknowledgement or query for the re-armed stop."""
    normalized = validate_spot_opo_residual_stop_request(request)
    if (
        not isinstance(response, Mapping)
        or "code" in response
        or response.get("symbol") != normalized["symbol"]
        or response.get("clientOrderId") != normalized["newClientOrderId"]
        or response.get("side") != "SELL"
        or response.get("type") != "STOP_LOSS"
        or response.get("orderListId") != -1
        or type(response.get("orderId")) is not int
        or response["orderId"] <= 0
        or response.get("status") not in _CANCEL_REPLACE_SELL_STATUSES
    ):
        raise LiveTradingSafetyError("Binance residual STOP_LOSS order conflicts with its exact durable request.")
    original = _decimal(response.get("origQty"), "residual stop original quantity")
    executed = _nonnegative_decimal(response.get("executedQty"), "residual stop executed quantity")
    requested = _decimal(normalized["quantity"], "residual stop requested quantity")
    stop_price = _decimal(response.get("stopPrice"), "residual stop acknowledged price")
    status = str(response["status"])
    if (
        original != requested
        or stop_price != _decimal(normalized["stopPrice"], "residual stop requested price")
        or executed > requested
        or (status == "NEW" and executed != 0)
        or (status == "PARTIALLY_FILLED" and not 0 < executed < requested)
        or (status == "FILLED" and executed != requested)
        or (status in {"CANCELED", "EXPIRED", "EXPIRED_IN_MATCH"} and executed >= requested)
    ):
        raise LiveTradingSafetyError("Binance residual STOP_LOSS quantity or state conflicts with its request.")
    return {
        "order_id": response["orderId"],
        "status": status,
        "original_quantity": format(original, "f"),
        "executed_quantity": format(executed, "f"),
        "terminal": status in _TERMINAL_SELL_STATUSES,
        "active": status in {"NEW", "PARTIALLY_FILLED"},
    }
