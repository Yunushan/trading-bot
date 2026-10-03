"""Exact, idempotent recovery of terminal Binance Spot market BUY fills."""

from __future__ import annotations

import hashlib
import json
import re
import time
from collections.abc import Mapping, Sequence
from contextlib import nullcontext
from datetime import datetime
from decimal import Decimal, InvalidOperation
from pathlib import Path

from app.settings.live_safety import LiveTradingSafetyError

from .spot_opo_runtime import validate_spot_opo_strategy_exit_order

from .order_intent_store import ledger_transaction, write_ledger
from .spot_opo_runtime import validate_spot_opo_request_payload
from .spot_exchange_errors import SPOT_LOCAL_STATE_ERRORS
from .spot_allocation_generation_runtime import build_spot_buy_allocation_row, validate_spot_buy_replay


_TRADE_PAGE_SIZE = 1000
_MAX_TRADE_PAGES = 100
_TERMINAL_STATUSES = {"FILLED", "CANCELED", "EXPIRED", "EXPIRED_IN_MATCH", "REJECTED"}


def _amount(value: object, field: str, *, positive: bool = False) -> Decimal:
    if not isinstance(value, str) or not value or len(value) > 80:
        raise LiveTradingSafetyError(f"Binance Spot fill {field} is invalid.")
    try:
        parsed = Decimal(value)
    except (InvalidOperation, ValueError):
        raise LiveTradingSafetyError(f"Binance Spot fill {field} is invalid.") from None
    if not parsed.is_finite() or parsed < 0 or (positive and parsed <= 0):
        raise LiveTradingSafetyError(f"Binance Spot fill {field} is invalid.")
    return parsed


def _canonical_amount(value: Decimal) -> str:
    text = format(value.normalize(), "f")
    return "0" if text in {"", "-0"} else text


def _positive_id(value: object, field: str) -> int:
    if type(value) is int and value > 0:
        return value
    if isinstance(value, str) and value.isascii() and value.isdigit() and int(value) > 0:
        return int(value)
    raise LiveTradingSafetyError(f"Binance Spot fill {field} is invalid.")


def summarize_primary_spot_buy(
    order_response: Mapping[str, object],
    *,
    symbol: str,
    client_order_id: str,
    base_asset: str,
    quote_asset: str,
) -> dict[str, object]:
    """Validate Binance's FULL primary acknowledgement and summarize its fills."""
    order_id = _positive_id(order_response.get("orderId"), "order ID")
    if (
        order_response.get("symbol") != symbol
        or order_response.get("clientOrderId") != client_order_id
        or order_response.get("side") != "BUY"
        or order_response.get("type") != "MARKET"
        or order_response.get("status") != "FILLED"
    ):
        raise LiveTradingSafetyError("Spot fill evidence does not identify the exact terminal BUY order.")
    if (
        not isinstance(base_asset, str) or not base_asset.isascii() or not base_asset.isalnum()
        or base_asset != base_asset.upper()
        or not isinstance(quote_asset, str) or not quote_asset.isascii() or not quote_asset.isalnum()
        or quote_asset != quote_asset.upper() or base_asset == quote_asset
    ):
        raise LiveTradingSafetyError("Binance Spot symbol assets are invalid.")
    if quote_asset != "USDT":
        raise LiveTradingSafetyError("Spot portfolio recovery currently requires a USDT-quoted symbol.")
    raw_fills = order_response.get("fills")
    if not isinstance(raw_fills, list) or not raw_fills or len(raw_fills) > _TRADE_PAGE_SIZE:
        raise LiveTradingSafetyError("Binance Spot primary acknowledgement has no complete fill list.")
    expected_qty = _amount(order_response.get("executedQty"), "executed quantity", positive=True)
    expected_quote = _amount(order_response.get("cummulativeQuoteQty"), "cumulative quote quantity", positive=True)
    quantity = Decimal(0)
    quote_quantity = Decimal(0)
    commissions: dict[str, Decimal] = {}
    trade_ids: list[int] = []
    normalized_trades: list[dict[str, object]] = []
    for fill in raw_fills:
        if not isinstance(fill, Mapping):
            raise LiveTradingSafetyError("Binance Spot primary fill row is malformed.")
        trade_id = _positive_id(fill.get("tradeId"), "trade ID")
        if trade_id in trade_ids:
            raise LiveTradingSafetyError("Binance Spot primary fill list contains a duplicate trade ID.")
        trade_ids.append(trade_id)
        price = _amount(fill.get("price"), "price", positive=True)
        qty = _amount(fill.get("qty"), "quantity", positive=True)
        fee = _amount(fill.get("commission"), "commission")
        fee_asset = fill.get("commissionAsset")
        if (
            not isinstance(fee_asset, str) or not fee_asset.isascii() or not fee_asset.isalnum()
            or fee_asset != fee_asset.upper()
        ):
            raise LiveTradingSafetyError("Binance Spot primary fill commission asset is invalid.")
        if fee:
            commissions[fee_asset] = commissions.get(fee_asset, Decimal(0)) + fee
        quantity += qty
        quote_quantity += price * qty
        normalized_trades.append({
            "id": trade_id,
            "price": _canonical_amount(price),
            "qty": _canonical_amount(qty),
            "commission": _canonical_amount(fee),
            "commissionAsset": fee_asset,
        })
    if quantity != expected_qty or quote_quantity != expected_quote:
        raise LiveTradingSafetyError("Binance Spot primary fill totals do not match the order response.")
    if any(asset not in {base_asset, quote_asset} and amount > 0 for asset, amount in commissions.items()):
        raise LiveTradingSafetyError("A third-asset Spot commission requires valuation before portfolio recovery.")
    net_qty = expected_qty - commissions.get(base_asset, Decimal(0))
    net_quote_cost = expected_quote + commissions.get(quote_asset, Decimal(0))
    if net_qty <= 0 or net_quote_cost <= 0:
        raise LiveTradingSafetyError("Spot BUY commissions leave no positive recoverable inventory.")
    trade_ids.sort()
    normalized_trades.sort(key=lambda row: int(row["id"]))
    signature_payload = {
        "symbol": symbol,
        "client_order_id": client_order_id,
        "order_id": order_id,
        "base_asset": base_asset,
        "quote_asset": quote_asset,
        "trades": normalized_trades,
    }
    signature = hashlib.sha256(
        json.dumps(signature_payload, sort_keys=True, separators=(",", ":")).encode("utf-8")
    ).hexdigest()
    fill_time_ms = order_response.get("updateTime") or order_response.get("transactTime") or order_response.get("time")
    if type(fill_time_ms) is not int or fill_time_ms <= 0:
        raise LiveTradingSafetyError("Binance Spot primary fill time is invalid.")
    return {
        "symbol": symbol,
        "client_order_id": client_order_id,
        "order_id": order_id,
        "trade_ids": trade_ids,
        "trade_count": len(trade_ids),
        "gross_qty": _canonical_amount(expected_qty),
        "net_qty": _canonical_amount(net_qty),
        "gross_quote_qty": _canonical_amount(expected_quote),
        "net_quote_cost": _canonical_amount(net_quote_cost),
        "average_cost": _canonical_amount(net_quote_cost / net_qty),
        "commissions": [
            {"asset": asset, "amount": _canonical_amount(amount)}
            for asset, amount in sorted(commissions.items())
        ],
        "base_asset": base_asset,
        "quote_asset": quote_asset,
        "fill_time_ms": fill_time_ms,
        "signature": signature,
    }


def collect_spot_order_trades(transport, *, symbol: str, order_id: int) -> list[dict[str, object]]:
    """Read every user trade for one exact order, failing on stalled pagination."""
    trades: list[dict[str, object]] = []
    from_id: int | None = None
    for _page_number in range(_MAX_TRADE_PAGES):
        page = transport.get_my_trades(
            symbol=symbol, order_id=order_id, from_id=from_id, limit=_TRADE_PAGE_SIZE,
        )
        if not isinstance(page, list) or len(page) > _TRADE_PAGE_SIZE:
            raise LiveTradingSafetyError("Binance Spot trade history page is invalid.")
        if not page:
            return trades
        page_ids = [_positive_id(row.get("id"), "trade ID") for row in page if isinstance(row, Mapping)]
        if len(page_ids) != len(page) or page_ids != sorted(set(page_ids)):
            raise LiveTradingSafetyError("Binance Spot trade history page has invalid or duplicate trade IDs.")
        if from_id is not None and page_ids[0] < from_id:
            raise LiveTradingSafetyError("Binance Spot trade history pagination regressed.")
        trades.extend(dict(row) for row in page if isinstance(row, Mapping))
        if len(page) < _TRADE_PAGE_SIZE:
            return trades
        next_from_id = page_ids[-1] + 1
        if from_id is not None and next_from_id <= from_id:
            raise LiveTradingSafetyError("Binance Spot trade history pagination did not advance.")
        from_id = next_from_id
    raise LiveTradingSafetyError("Binance Spot order has too many fills for bounded recovery.")


def summarize_spot_market_fill(
    intent: Mapping[str, object],
    order_response: Mapping[str, object],
    trades: Sequence[Mapping[str, object]],
    *,
    base_asset: str,
    quote_asset: str,
) -> dict[str, object]:
    """Validate exact Spot market order/trade agreement and portfolio impact."""
    symbol = intent.get("symbol")
    client_order_id = intent.get("client_order_id")
    exchange_client_order_id = intent.get("exchange_client_order_id", client_order_id)
    side = intent.get("side")
    order_type = intent.get("type")
    order_id = _positive_id(order_response.get("orderId"), "order ID")
    if (
        intent.get("market") != "spot"
        or order_type not in {"MARKET", "LIMIT", "STOP_LOSS"}
        or (order_type == "LIMIT" and side != "BUY")
        or (order_type == "STOP_LOSS" and side != "SELL")
        or side not in {"BUY", "SELL"}
        or not isinstance(symbol, str)
        or not isinstance(client_order_id, str) or not client_order_id
        or not isinstance(exchange_client_order_id, str) or not exchange_client_order_id
        or order_response.get("symbol") != symbol
        or order_response.get("clientOrderId") != exchange_client_order_id
        or order_response.get("side") != side
        or order_response.get("type") != order_type
        or order_response.get("status") not in _TERMINAL_STATUSES
        or (intent.get("exchange_order_id") and str(intent["exchange_order_id"]) != str(order_id))
    ):
        raise LiveTradingSafetyError("Spot fill recovery requires the exact terminal order intent.")
    if (
        not isinstance(base_asset, str) or not base_asset.isascii() or not base_asset.isalnum()
        or base_asset != base_asset.upper()
        or not isinstance(quote_asset, str) or not quote_asset.isascii() or not quote_asset.isalnum()
        or quote_asset != quote_asset.upper() or base_asset == quote_asset
    ):
        raise LiveTradingSafetyError("Binance Spot symbol assets are invalid.")
    if quote_asset != "USDT":
        raise LiveTradingSafetyError("Spot portfolio recovery currently requires a USDT-quoted symbol.")

    expected_qty = _amount(order_response.get("executedQty"), "executed quantity")
    expected_quote = _amount(order_response.get("cummulativeQuoteQty"), "cumulative quote quantity")
    if expected_qty <= 0 or not trades:
        raise LiveTradingSafetyError("A positive Spot fill with trade rows is required for recovery.")

    trade_ids: list[int] = []
    quantity = Decimal(0)
    quote_quantity = Decimal(0)
    commissions: dict[str, Decimal] = {}
    latest_time = 0
    normalized_trades: list[dict[str, object]] = []
    for trade in trades:
        if (
            not isinstance(trade, Mapping)
            or trade.get("symbol") != symbol
            or _positive_id(trade.get("orderId"), "trade order ID") != order_id
            or type(trade.get("isBuyer")) is not bool
            or trade.get("isBuyer") is not (side == "BUY")
        ):
            raise LiveTradingSafetyError("Binance Spot trade row does not belong to the requested market order.")
        trade_id = _positive_id(trade.get("id"), "trade ID")
        if trade_id in trade_ids:
            raise LiveTradingSafetyError("Binance Spot order fill contains a duplicate trade ID.")
        trade_ids.append(trade_id)
        price = _amount(trade.get("price"), "price", positive=True)
        qty = _amount(trade.get("qty"), "quantity", positive=True)
        quote_qty = _amount(trade.get("quoteQty"), "quote quantity", positive=True)
        fee = _amount(trade.get("commission"), "commission")
        fee_asset = trade.get("commissionAsset")
        if (
            not isinstance(fee_asset, str) or not fee_asset.isascii() or not fee_asset.isalnum()
            or fee_asset != fee_asset.upper()
        ):
            raise LiveTradingSafetyError("Binance Spot trade commission asset is invalid.")
        if fee:
            commissions[fee_asset] = commissions.get(fee_asset, Decimal(0)) + fee
        trade_time = trade.get("time")
        if type(trade_time) is not int or trade_time <= 0:
            raise LiveTradingSafetyError("Binance Spot trade time is invalid.")
        latest_time = max(latest_time, trade_time)
        quantity += qty
        quote_quantity += quote_qty
        normalized_trades.append({
            "id": trade_id,
            "price": _canonical_amount(price),
            "qty": _canonical_amount(qty),
            "quoteQty": format(quote_qty, "f"),
            "commission": _canonical_amount(fee),
            "commissionAsset": fee_asset,
            "time": trade_time,
        })

    if quantity != expected_qty or quote_quantity != expected_quote:
        raise LiveTradingSafetyError("Binance Spot order totals do not match its complete trade history.")
    if any(asset not in {base_asset, quote_asset} and amount > 0 for asset, amount in commissions.items()):
        raise LiveTradingSafetyError("A third-asset Spot commission requires valuation before portfolio recovery.")

    base_fee = commissions.get(base_asset, Decimal(0))
    quote_fee = commissions.get(quote_asset, Decimal(0))
    if side == "BUY":
        portfolio_qty = expected_qty - base_fee
        net_quote = expected_quote + quote_fee
        if portfolio_qty <= 0 or net_quote <= 0:
            raise LiveTradingSafetyError("Spot BUY commissions leave no positive recoverable inventory.")
    else:
        # A base-asset fee consumes additional owned inventory on a SELL. A
        # quote-asset fee reduces proceeds. Third-asset fees remain unsupported.
        portfolio_qty = expected_qty + base_fee
        net_quote = expected_quote - quote_fee
        if portfolio_qty <= 0 or net_quote <= 0:
            raise LiveTradingSafetyError("Spot SELL commissions leave no positive recoverable inventory.")

    commission_rows = [
        {"asset": asset, "amount": _canonical_amount(amount)}
        for asset, amount in sorted(commissions.items())
    ]
    signature_trades = [
        {
            "id": int(row["id"]),
            "price": str(row["price"]),
            "qty": str(row["qty"]),
            "commission": str(row["commission"]),
            "commissionAsset": str(row["commissionAsset"]),
        }
        for row in sorted(normalized_trades, key=lambda item: int(item["id"]))
    ]
    signature_payload = {
        "symbol": symbol,
        "client_order_id": client_order_id,
        "order_id": order_id,
        "base_asset": base_asset,
        "quote_asset": quote_asset,
        "trades": signature_trades,
    }
    if exchange_client_order_id != client_order_id:
        signature_payload["exchange_client_order_id"] = exchange_client_order_id
    if side == "SELL":
        signature_payload["side"] = side
    signature = hashlib.sha256(
        json.dumps(signature_payload, sort_keys=True, separators=(",", ":")).encode("utf-8")
    ).hexdigest()
    result = {
        "symbol": symbol,
        "client_order_id": client_order_id,
        "exchange_client_order_id": exchange_client_order_id,
        "side": side,
        "order_id": order_id,
        "trade_ids": sorted(trade_ids),
        "trade_count": len(trade_ids),
        "gross_qty": _canonical_amount(expected_qty),
        # For BUY this is received base inventory. For SELL it is consumed
        # base inventory, including any base-asset commission.
        "net_qty": _canonical_amount(portfolio_qty),
        "portfolio_qty": _canonical_amount(portfolio_qty),
        "base_fee_qty": _canonical_amount(base_fee),
        "quote_fee_qty": _canonical_amount(quote_fee),
        "gross_quote_qty": _canonical_amount(expected_quote),
        "net_quote_cost": _canonical_amount(net_quote) if side == "BUY" else "0",
        "net_quote_proceeds": _canonical_amount(net_quote) if side == "SELL" else "0",
        "average_cost": _canonical_amount(net_quote / portfolio_qty) if side == "BUY" else "0",
        "average_price": _canonical_amount(net_quote / portfolio_qty) if side == "SELL" else "0",
        "commissions": commission_rows,
        "base_asset": base_asset,
        "quote_asset": quote_asset,
        "fill_time_ms": latest_time,
        "signature": signature,
    }
    return result


def summarize_spot_opo_buy_fill(
    intent: Mapping[str, object],
    order_response: Mapping[str, object],
    trades: Sequence[Mapping[str, object]],
    *,
    base_asset: str,
    quote_asset: str,
) -> dict[str, object]:
    """Summarize an exact filled OPO working BUY child for portfolio import."""
    request = validate_spot_opo_request_payload(intent.get("request"))
    if (
        intent.get("market") != "spot"
        or intent.get("type") != "OPO"
        or intent.get("side") != "BUY"
        or intent.get("client_order_id") != request["listClientOrderId"]
        or intent.get("symbol") != request["symbol"]
        or intent.get("state") not in {"accepted", "unknown"}
        or intent.get("protection_state") not in {"active", "triggered", "lost", "unverified"}
        or intent.get("working_status") != "FILLED"
        or intent.get("list_status") not in {"EXEC_STARTED", "ALL_DONE"}
    ):
        raise LiveTradingSafetyError("Spot OPO BUY recovery requires an exact filled working child.")
    try:
        expected_quantity = Decimal(request["workingQuantity"])
        working_id = _positive_id(intent.get("working_order_id"), "OPO working order ID")
        list_id = intent.get("exchange_order_list_id")
        response_quantity = _amount(order_response.get("origQty"), "OPO working order quantity", positive=True)
        executed_quantity = _amount(order_response.get("executedQty"), "OPO working executed quantity", positive=True)
        reconciled_quantity = _amount(intent.get("working_executed_qty"), "reconciled OPO working quantity", positive=True)
        response_order_id = _positive_id(order_response.get("orderId"), "OPO working order ID")
    except (InvalidOperation, ValueError):
        raise LiveTradingSafetyError("Spot OPO working order quantities are invalid.") from None
    if (
        type(list_id) is not int
        or list_id < 0
        or order_response.get("orderListId") != list_id
        or response_order_id != working_id
        or order_response.get("clientOrderId") != request["workingClientOrderId"]
        or order_response.get("symbol") != request["symbol"]
        or order_response.get("side") != "BUY"
        or order_response.get("type") != "LIMIT"
        or order_response.get("timeInForce") != "FOK"
        or order_response.get("status") != "FILLED"
        or response_quantity != expected_quantity
        or executed_quantity != expected_quantity
        or reconciled_quantity != expected_quantity
    ):
        raise LiveTradingSafetyError("Spot OPO working order query conflicts with its reconciled list fill.")
    normalized_intent = {
        "market": "spot",
        "type": "LIMIT",
        "side": "BUY",
        "symbol": request["symbol"],
        "client_order_id": request["listClientOrderId"],
        "exchange_client_order_id": request["workingClientOrderId"],
        "exchange_order_id": working_id,
    }
    fill = summarize_spot_market_fill(
        normalized_intent,
        order_response,
        trades,
        base_asset=base_asset,
        quote_asset=quote_asset,
    )
    fill["pending_order_qty"] = intent.get("pending_original_qty")
    return fill


def summarize_spot_opo_stop_sell_fill(
    intent: Mapping[str, object],
    order_response: Mapping[str, object],
    trades: Sequence[Mapping[str, object]],
    *,
    base_asset: str,
    quote_asset: str,
) -> dict[str, object]:
    """Summarize a fully filled OPO stop only against its linked BUY allocation."""
    request = validate_spot_opo_request_payload(intent.get("request"))
    if (
        intent.get("market") != "spot"
        or intent.get("type") != "OPO"
        or intent.get("side") != "BUY"
        or intent.get("client_order_id") != request["listClientOrderId"]
        or intent.get("symbol") != request["symbol"]
        or intent.get("state") not in {"accepted", "unknown"}
        or intent.get("protection_state") != "triggered"
        or intent.get("list_status") != "ALL_DONE"
        or intent.get("working_status") != "FILLED"
        or intent.get("pending_status") != "FILLED"
        or intent.get("entry_reconciled") is not True
    ):
        raise LiveTradingSafetyError("OPO stop recovery requires a triggered stop and durable entry proof.")
    try:
        list_id = intent.get("exchange_order_list_id")
        stop_order_id = _positive_id(intent.get("pending_order_id"), "OPO stop order ID")
        stop_original = _amount(intent.get("pending_original_qty"), "OPO stop quantity", positive=True)
        stop_executed = _amount(intent.get("pending_executed_qty"), "OPO stop executed quantity", positive=True)
        entry_quantity = _amount(intent.get("entry_portfolio_quantity"), "OPO entry quantity", positive=True)
        entry_signature = intent.get("entry_recovery_signature")
        request_stop_price = Decimal(request["pendingStopPrice"])
        observed_stop_price = _amount(order_response.get("stopPrice"), "OPO stop price", positive=True)
        response_original = _amount(order_response.get("origQty"), "OPO stop order quantity", positive=True)
        response_executed = _amount(order_response.get("executedQty"), "OPO stop executed quantity", positive=True)
        response_order_id = _positive_id(order_response.get("orderId"), "OPO stop order ID")
    except (InvalidOperation, ValueError):
        raise LiveTradingSafetyError("Spot OPO stop quantities or identity are invalid.") from None
    if (
        type(list_id) is not int or list_id < 0
        or not isinstance(entry_signature, str) or re.fullmatch(r"[0-9a-f]{64}", entry_signature) is None
        or response_order_id != stop_order_id
        or order_response.get("orderListId") != list_id
        or order_response.get("clientOrderId") != request["pendingClientOrderId"]
        or order_response.get("symbol") != request["symbol"]
        or order_response.get("side") != "SELL"
        or order_response.get("type") != "STOP_LOSS"
        or order_response.get("status") != "FILLED"
        or observed_stop_price != request_stop_price
        or response_original != stop_original
        or response_executed != stop_executed
        or stop_original != entry_quantity
        or stop_executed != stop_original
    ):
        raise LiveTradingSafetyError("Spot OPO stop order query conflicts with its exact linked entry proof.")
    normalized_intent = {
        "market": "spot",
        "type": "STOP_LOSS",
        "side": "SELL",
        "symbol": request["symbol"],
        "client_order_id": request["listClientOrderId"],
        "exchange_client_order_id": request["pendingClientOrderId"],
        "exchange_order_id": stop_order_id,
    }
    fill = summarize_spot_market_fill(
        normalized_intent,
        order_response,
        trades,
        base_asset=base_asset,
        quote_asset=quote_asset,
    )
    if Decimal(str(fill["portfolio_qty"])) != entry_quantity:
        raise LiveTradingSafetyError(
            "OPO stop SELL consumed quantity differs from its recovered BUY allocation; manual reconciliation is required."
        )
    fill.update({
        "type": "STOP_LOSS",
        "opo_list_client_order_id": request["listClientOrderId"],
        "opo_pending_client_order_id": request["pendingClientOrderId"],
        "opo_order_list_id": list_id,
        "entry_recovery_signature": entry_signature,
        "entry_portfolio_quantity": _canonical_amount(entry_quantity),
        "entry_working_client_order_id": request["workingClientOrderId"],
        "entry_working_order_id": _positive_id(intent.get("working_order_id"), "OPO working order ID"),
    })
    return fill


def summarize_spot_opo_strategy_sell_fill(
    intent: Mapping[str, object],
    order_response: Mapping[str, object],
    trades: Sequence[Mapping[str, object]],
    *,
    base_asset: str,
    quote_asset: str,
) -> dict[str, object]:
    """Bind terminal cancel-replace SELL trades to one recovered OPO entry."""
    request = intent.get("strategy_exit_request")
    order_evidence = validate_spot_opo_strategy_exit_order(order_response, request)
    try:
        entry_quantity = _amount(intent.get("entry_portfolio_quantity"), "OPO entry quantity", positive=True)
        pre_order_quantity = _amount(
            intent.get("strategy_exit_pre_order_quantity"), "OPO SELL baseline quantity", positive=True,
        )
    except (InvalidOperation, ValueError):
        raise LiveTradingSafetyError("Linked OPO strategy SELL is missing its durable entry baseline.") from None
    if (
        intent.get("type") != "OPO"
        or intent.get("market") != "spot"
        or intent.get("entry_reconciled") is not True
        or intent.get("strategy_exit_state") not in {"sell_accepted", "unknown"}
        or intent.get("strategy_exit_new_order_accepted") is not True
        or intent.get("strategy_exit_cancel_confirmed") is not True
        or intent.get("cancel_state") != "confirmed"
        or intent.get("protection_state") != "cancelled"
        or not order_evidence["terminal"]
        or order_evidence["order_id"] != intent.get("strategy_exit_order_id")
        or order_evidence["status"] != intent.get("strategy_exit_status")
        or order_evidence["executed_quantity"] != str(intent.get("strategy_exit_executed_qty"))
        or pre_order_quantity != entry_quantity
        or not isinstance(intent.get("strategy_exit_pre_order_signature"), str)
        or re.fullmatch(r"[0-9a-f]{64}", str(intent.get("strategy_exit_pre_order_signature"))) is None
    ):
        raise LiveTradingSafetyError("Linked OPO strategy SELL is not an exact terminal recovered exit.")
    normalized_intent = {
        "market": "spot",
        "type": "MARKET",
        "side": "SELL",
        "symbol": intent.get("symbol"),
        "client_order_id": intent.get("strategy_exit_client_order_id"),
        "exchange_client_order_id": intent.get("strategy_exit_client_order_id"),
        "exchange_order_id": order_evidence["order_id"],
    }
    fill = summarize_spot_market_fill(
        normalized_intent,
        order_response,
        trades,
        base_asset=base_asset,
        quote_asset=quote_asset,
    )
    fill.update({
        "type": "MARKET",
        "opo_list_client_order_id": intent.get("client_order_id"),
        "opo_entry_portfolio_quantity": format(entry_quantity, "f"),
        "pre_order_portfolio_signature": intent.get("strategy_exit_pre_order_signature"),
        "pre_order_portfolio_qty": format(pre_order_quantity, "f"),
    })
    return fill


def summarize_spot_opo_residual_stop_sell_fill(
    intent: Mapping[str, object],
    order_response: Mapping[str, object],
    trades: Sequence[Mapping[str, object]],
    *,
    base_asset: str,
    quote_asset: str,
) -> dict[str, object]:
    """Bind a standalone residual STOP_LOSS fill to the exact OPO remainder."""
    from .spot_opo_runtime import (
        validate_spot_opo_residual_stop_order,
        validate_spot_opo_residual_stop_request,
    )

    request = validate_spot_opo_residual_stop_request(intent.get("residual_stop_request"))
    try:
        pre_order_quantity = _amount(
            intent.get("residual_stop_pre_order_quantity"), "residual stop baseline quantity", positive=True,
        )
        order_id = _positive_id(intent.get("residual_stop_order_id"), "residual stop order ID")
        evidence = validate_spot_opo_residual_stop_order(order_response, request)
        entry_quantity = _amount(intent.get("entry_portfolio_quantity"), "OPO entry quantity", positive=True)
    except (InvalidOperation, ValueError):
        raise LiveTradingSafetyError("Residual OPO stop is missing its durable exact request or baseline.") from None
    if (
        intent.get("type") != "OPO"
        or intent.get("market") != "spot"
        or intent.get("state") != "accepted"
        or intent.get("entry_reconciled") is not True
        or intent.get("cancel_state") != "confirmed"
        or intent.get("protection_state") != "cancelled"
        or intent.get("residual_stop_state") not in {"active", "triggered", "unknown"}
        or intent.get("residual_stop_query_verified") is not True
        or intent.get("residual_stop_order_id") != evidence["order_id"]
        or intent.get("residual_stop_status") != evidence["status"]
        or str(intent.get("residual_stop_executed_qty")) != str(evidence["executed_quantity"])
        or request["symbol"] != intent.get("symbol")
        or Decimal(request["quantity"]) != pre_order_quantity
        # A rejected linked SELL leaves the full entry allocation to re-arm.
        or pre_order_quantity > entry_quantity
        or not evidence["terminal"]
        or not isinstance(intent.get("residual_stop_pre_order_signature"), str)
        or re.fullmatch(r"[0-9a-f]{64}", str(intent.get("residual_stop_pre_order_signature"))) is None
    ):
        raise LiveTradingSafetyError("Residual OPO stop SELL is not one exact terminal protected remainder.")

    normalized_intent = {
        "market": "spot",
        "type": "STOP_LOSS",
        "side": "SELL",
        "symbol": request["symbol"],
        "client_order_id": request["newClientOrderId"],
        "exchange_client_order_id": request["newClientOrderId"],
        "exchange_order_id": order_id,
    }
    fill = summarize_spot_market_fill(
        normalized_intent,
        order_response,
        trades,
        base_asset=base_asset,
        quote_asset=quote_asset,
    )
    fill.update({
        "type": "STOP_LOSS",
        "opo_list_client_order_id": intent.get("client_order_id"),
        "residual_stop_client_order_id": request["newClientOrderId"],
        "residual_stop_pre_order_signature": intent.get("residual_stop_pre_order_signature"),
        "residual_stop_pre_order_quantity": format(pre_order_quantity, "f"),
        "opo_entry_portfolio_quantity": format(entry_quantity, "f"),
    })
    return fill


def _display_time(timestamp_ms: int) -> str:
    return datetime.fromtimestamp(timestamp_ms / 1000).astimezone().strftime("%Y-%m-%d %H:%M:%S")


def _unique_json_object(pairs: list[tuple[str, object]]) -> dict[str, object]:
    value: dict[str, object] = {}
    for key, item in pairs:
        if key in value:
            raise ValueError("duplicate allocation field")
        value[key] = item
    return value


def persist_spot_buy_allocation(path: Path, fill: Mapping[str, object]) -> bool:
    """Atomically insert or repair one recovered BUY allocation by exact order identity."""
    return _persist_spot_buy_allocation(path, fill)


def _persist_spot_buy_allocation_unlocked(path: Path, fill: Mapping[str, object]) -> bool:
    """Publish only while the caller holds this allocation's storage lock."""
    return _persist_spot_buy_allocation(path, fill, unlocked=True)


def _persist_spot_buy_allocation(path: Path, fill: Mapping[str, object], *, unlocked: bool = False) -> bool:
    symbol = fill.get("symbol")
    client_order_id = fill.get("client_order_id")
    exchange_client_order_id = fill.get("exchange_client_order_id", client_order_id)
    signature = fill.get("signature")
    if (
        not isinstance(symbol, str) or not symbol.isascii() or not symbol.isalnum()
        or symbol != symbol.upper()
        or not isinstance(client_order_id, str) or not client_order_id
        or not isinstance(exchange_client_order_id, str) or not exchange_client_order_id
        or len(exchange_client_order_id) > 36 or not exchange_client_order_id.isascii()
        or any(character not in "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789._:/-" for character in exchange_client_order_id)
        or not isinstance(signature, str) or len(signature) != 64
    ):
        raise LiveTradingSafetyError("Recovered Spot allocation identity is invalid.")
    try:
        net_qty = Decimal(str(fill.get("net_qty")))
        net_quote_cost = Decimal(str(fill.get("net_quote_cost")))
        average_cost = Decimal(str(fill.get("average_cost")))
        fill_time_ms = int(fill.get("fill_time_ms"))
    except (InvalidOperation, ValueError, TypeError):
        raise LiveTradingSafetyError("Recovered Spot allocation amounts are invalid.") from None
    if (
        not net_qty.is_finite() or net_qty <= 0 or not net_quote_cost.is_finite()
        or net_quote_cost <= 0 or not average_cost.is_finite() or average_cost <= 0
        or fill_time_ms <= 0 or net_quote_cost / net_qty != average_cost
    ):
        raise LiveTradingSafetyError("Recovered Spot allocation amounts are invalid.")

    recovery_metadata = {
        "version": 1,
        "signature": signature,
        "exchange_client_order_id": exchange_client_order_id,
        "order_id": fill.get("order_id"),
        "trade_ids": list(fill.get("trade_ids") or []),
        "trade_count": fill.get("trade_count"),
        "gross_qty": str(fill.get("gross_qty")),
        "net_qty": _canonical_amount(net_qty),
        "gross_quote_qty": str(fill.get("gross_quote_qty")),
        "net_quote_cost": _canonical_amount(net_quote_cost),
        "commissions": list(fill.get("commissions") or []),
        "base_asset": fill.get("base_asset"),
        "quote_asset": fill.get("quote_asset"),
        "fill_time_ms": fill_time_ms,
    }
    pending_order_qty = fill.get("pending_order_qty")
    if pending_order_qty is not None:
        try:
            parsed_pending_qty = Decimal(str(pending_order_qty))
        except (InvalidOperation, ValueError):
            raise LiveTradingSafetyError("Recovered Spot linked stop quantity is invalid.") from None
        if not parsed_pending_qty.is_finite() or parsed_pending_qty <= 0:
            raise LiveTradingSafetyError("Recovered Spot linked stop quantity is invalid.")
        recovery_metadata["pending_order_qty"] = _canonical_amount(parsed_pending_qty)
    key = f"{symbol}:L"
    entry = {
        "interval": "RECOVERY",
        "interval_display": "Recovered Spot fill",
        "qty": float(net_qty),
        "entry_price": float(average_cost),
        "leverage": 1,
        "margin_usdt": float(net_quote_cost),
        "margin_balance": float(net_quote_cost),
        "notional": float(net_quote_cost),
        "symbol": symbol,
        "side_key": "L",
        "open_time": _display_time(fill_time_ms),
        "status": "Active",
        "pnl_value": None,
        "trigger_indicators": [],
        "trigger_signature": [],
        "trigger_desc": "Recovered exact Binance Spot fill",
        "trigger_actions": {},
        "order_id": str(fill.get("order_id")),
        "client_order_id": client_order_id,
        "trade_id": client_order_id,
        "spot_fill_recovery": recovery_metadata,
    }

    entry = build_spot_buy_allocation_row(fill)
    if path.is_symlink():
        raise LiveTradingSafetyError("Desktop allocation state must not be a symbolic link.")
    with nullcontext() if unlocked else ledger_transaction(path):
        if path.exists():
            try:
                data = json.loads(path.read_text(encoding="utf-8"), object_pairs_hook=_unique_json_object)
            except SPOT_LOCAL_STATE_ERRORS as exc:
                raise LiveTradingSafetyError("Desktop allocation state is unreadable; Spot recovery is blocked.") from exc
            if (
                not isinstance(data, dict)
                or type(data.get("version")) is not int
                or data.get("version") != 1
                or data.get("mode") != "Live"
                or not isinstance(data.get("entry_allocations"), dict)
                or not isinstance(data.get("open_position_records"), dict)
            ):
                raise LiveTradingSafetyError("Desktop allocation state is not a valid Live portfolio snapshot.")
        else:
            data = {
                "version": 1,
                "mode": "Live",
                "timestamp": time.time(),
                "entry_allocations": {},
                "open_position_records": {},
            }

        allocations = data["entry_allocations"]
        records = data["open_position_records"]
        matches: list[tuple[str, dict[str, object]]] = []
        for stored_key, stored_entries in allocations.items():
            if not isinstance(stored_key, str) or not isinstance(stored_entries, list):
                raise LiveTradingSafetyError("Desktop allocation state contains an invalid allocation list.")
            for stored_entry in stored_entries:
                if not isinstance(stored_entry, dict):
                    raise LiveTradingSafetyError("Desktop allocation state contains an invalid entry.")
                if stored_entry.get("client_order_id") == client_order_id:
                    matches.append((stored_key, stored_entry))
        if len(matches) > 1 or (matches and matches[0][0] != key):
            raise LiveTradingSafetyError("Spot fill identity conflicts with existing desktop portfolio entries.")

        target_entries = allocations.setdefault(key, [])
        if not isinstance(target_entries, list):
            raise LiveTradingSafetyError("Desktop Spot allocation list is invalid.")
        if matches:
            existing = matches[0][1]
            previous_recovery = existing.get("spot_fill_recovery")
            if isinstance(previous_recovery, Mapping):
                if previous_recovery.get("signature") != signature:
                    raise LiveTradingSafetyError("Recovered Spot fill conflicts with its prior portfolio proof.")
                validate_spot_buy_replay(existing, fill)
                # The acquisition is already durable. Consumption is never undone by BUY replay.
                return True
            if ("spot_fill_recovery" in existing or existing.get("spot_sell_recoveries")
                or "spot_opo_stop_recovery" in existing or str(existing.get("status") or "").lower() != "active"):
                raise LiveTradingSafetyError("Spot acquisition replay has unprovable prior consumption.")
            for field in (
                "qty", "entry_price", "leverage", "margin_usdt", "margin_balance", "notional",
                "symbol", "side_key", "status", "order_id", "client_order_id", "trade_id",
                "spot_fill_recovery",
            ):
                existing[field] = entry[field]
        else:
            target_entries.append(entry)

        record = records.get(key)
        if record is None:
            record = {
                "symbol": symbol,
                "side_key": "L",
                "entry_tf": "Recovered Spot fill",
                "open_time": entry["open_time"],
                "close_time": "-",
                "status": "Active",
                "data": {},
                "indicators": [],
                "stop_loss_enabled": False,
            }
            records[key] = record
        if (
            not isinstance(record, dict)
            or not isinstance(record.get("status", "Active"), str)
            or record.get("status", "Active").lower() != "active"
        ):
            raise LiveTradingSafetyError("Desktop Spot position snapshot conflicts with recovered inventory.")
        record["status"] = "Active"
        record["allocations"] = [dict(row) for row in target_entries
                                 if isinstance(row, dict) and str(row.get("status") or "").lower() == "active"]
        record_data = record.get("data")
        if not isinstance(record_data, dict):
            raise LiveTradingSafetyError("Desktop Spot position snapshot is malformed.")
        total_qty = Decimal(0)
        total_cost = Decimal(0)
        for allocation in target_entries:
            if not isinstance(allocation, Mapping) or str(allocation.get("status") or "").lower() != "active":
                continue
            try:
                allocation_qty = Decimal(str(allocation.get("qty")))
                allocation_price = Decimal(str(allocation.get("entry_price")))
            except (InvalidOperation, ValueError):
                raise LiveTradingSafetyError("Desktop Spot allocation quantities are invalid.") from None
            if (
                not allocation_qty.is_finite() or allocation_qty <= 0
                or not allocation_price.is_finite() or allocation_price <= 0
            ):
                raise LiveTradingSafetyError("Desktop Spot allocation quantities are invalid.")
            total_qty += allocation_qty
            total_cost += allocation_qty * allocation_price
        if total_qty <= 0 or total_cost <= 0:
            raise LiveTradingSafetyError("Desktop Spot allocation snapshot has no positive inventory.")
        total_average = total_cost / total_qty
        record_data.update({
            "symbol": symbol,
            "side_key": "L",
            "interval": "RECOVERY",
            "interval_display": "Recovered Spot fill",
            "qty": float(total_qty),
            "entry_price": float(total_average),
            "margin_usdt": float(total_cost),
            "size_usdt": float(total_cost),
        })
        data["timestamp"] = time.time()
        write_ledger(path, data)
    return True


def _stored_decimal(value: object, field: str, *, positive: bool = False) -> Decimal:
    try:
        parsed = Decimal(str(value))
    except (InvalidOperation, ValueError, TypeError):
        raise LiveTradingSafetyError(f"Desktop Spot allocation {field} is invalid.") from None
    if not parsed.is_finite() or parsed < 0 or (positive and parsed <= 0):
        raise LiveTradingSafetyError(f"Desktop Spot allocation {field} is invalid.")
    return parsed


def _load_live_allocation_snapshot(path: Path) -> dict[str, object]:
    if path.is_symlink() or not path.is_file():
        raise LiveTradingSafetyError("A durable Live allocation snapshot is required for Spot SELL recovery.")
    try:
        data = json.loads(path.read_text(encoding="utf-8"), object_pairs_hook=_unique_json_object)
    except SPOT_LOCAL_STATE_ERRORS as exc:
        raise LiveTradingSafetyError("Desktop allocation state is unreadable; Spot recovery is blocked.") from exc
    if (
        not isinstance(data, dict)
        or type(data.get("version")) is not int
        or data.get("version") != 1
        or data.get("mode") != "Live"
        or not isinstance(data.get("entry_allocations"), dict)
        or not isinstance(data.get("open_position_records"), dict)
    ):
        raise LiveTradingSafetyError("Desktop allocation state is not a valid Live portfolio snapshot.")
    return data


def spot_live_allocation_baseline(path: Path, *, symbol: str) -> dict[str, str] | None:
    """Fingerprint a coherent local Live position before a Spot market SELL."""
    if not isinstance(symbol, str) or not symbol.isascii() or not symbol.isalnum() or symbol != symbol.upper():
        raise LiveTradingSafetyError("Spot SELL baseline symbol is invalid.")
    if path.is_symlink():
        raise LiveTradingSafetyError("Desktop allocation state must not be a symbolic link.")
    if not path.exists():
        return None
    data = _load_live_allocation_snapshot(path)
    allocations = data["entry_allocations"]
    records = data["open_position_records"]
    assert isinstance(allocations, dict) and isinstance(records, dict)
    key = f"{symbol}:L"
    raw_entries = allocations.get(key)
    if not isinstance(raw_entries, list):
        return None
    _existing_sell_recovery_proofs(allocations, signature="0" * 64)
    for stored_key, stored_rows in allocations.items():
        if not isinstance(stored_key, str) or not isinstance(stored_rows, list):
            raise LiveTradingSafetyError("Desktop allocation state contains an invalid allocation list.")
        if stored_key == key:
            continue
        for stored_row in stored_rows:
            if not isinstance(stored_row, dict):
                raise LiveTradingSafetyError("Desktop allocation state contains an invalid entry.")
            if stored_row.get("symbol") == symbol:
                stored_status = stored_row.get("status")
                if not isinstance(stored_status, str) or stored_status.lower() not in {"active", "closed"}:
                    raise LiveTradingSafetyError("Desktop Spot allocation status is invalid.")
                if stored_status.lower() == "active":
                    raise LiveTradingSafetyError("Active Spot inventory exists outside its canonical allocation key.")

    active_entries: list[dict[str, object]] = []
    active_ids: set[str] = set()
    for row in raw_entries:
        if not isinstance(row, dict) or row.get("symbol") != symbol or row.get("side_key") != "L":
            raise LiveTradingSafetyError("Desktop Spot allocation identity conflicts with its baseline.")
        status = row.get("status")
        if not isinstance(status, str) or status.lower() not in {"active", "closed"}:
            raise LiveTradingSafetyError("Desktop Spot allocation status is invalid.")
        if status.lower() != "active":
            continue
        client_order_id = row.get("client_order_id")
        if not isinstance(client_order_id, str) or not client_order_id or client_order_id in active_ids:
            raise LiveTradingSafetyError("Desktop Spot allocation identity is missing or duplicated.")
        active_ids.add(client_order_id)
        qty = _stored_decimal(row.get("qty"), "quantity", positive=True)
        entry_price = _stored_decimal(row.get("entry_price"), "entry price", positive=True)
        proofs = row.get("spot_sell_recoveries", [])
        if not isinstance(proofs, list):
            raise LiveTradingSafetyError("Desktop Spot SELL recovery evidence is malformed.")
        active_entries.append({
            "client_order_id": client_order_id,
            "qty": _canonical_amount(qty),
            "entry_price": _canonical_amount(entry_price),
            "sell_recovery_signatures": [
                {
                    "signature": proof.get("signature"),
                    "consumed_qty": proof.get("consumed_qty"),
                }
                for proof in proofs if isinstance(proof, Mapping)
            ],
        })
    if not active_entries:
        return None

    record = records.get(key)
    if (
        not isinstance(record, dict)
        or record.get("symbol") != symbol
        or record.get("side_key") != "L"
        or not isinstance(record.get("status", "Active"), str)
        or record.get("status", "Active").lower() != "active"
    ):
        raise LiveTradingSafetyError("Desktop Spot position snapshot conflicts with its allocations.")
    record_data = record.get("data")
    snapshot_entries = record.get("allocations")
    if not isinstance(record_data, dict) or not isinstance(snapshot_entries, list):
        raise LiveTradingSafetyError("Desktop Spot position snapshot is malformed.")
    snapshot_active: dict[str, Decimal] = {}
    for row in snapshot_entries:
        if not isinstance(row, dict):
            raise LiveTradingSafetyError("Desktop Spot position allocation snapshot is malformed.")
        snapshot_status = row.get("status")
        if not isinstance(snapshot_status, str) or snapshot_status.lower() not in {"active", "closed"}:
            raise LiveTradingSafetyError("Desktop Spot position allocation status is invalid.")
        if snapshot_status.lower() != "active":
            continue
        row_id = row.get("client_order_id")
        if not isinstance(row_id, str) or row_id in snapshot_active:
            raise LiveTradingSafetyError("Desktop Spot position allocation identity is invalid.")
        snapshot_active[row_id] = _stored_decimal(row.get("qty"), "snapshot quantity", positive=True)
    main_active = {
        str(row["client_order_id"]): Decimal(str(row["qty"]))
        for row in active_entries
    }
    if snapshot_active != main_active:
        raise LiveTradingSafetyError("Desktop Spot position snapshot does not match its allocations.")
    total_qty = sum(main_active.values(), Decimal(0))
    if _stored_decimal(record_data.get("qty"), "snapshot total quantity", positive=True) != total_qty:
        raise LiveTradingSafetyError("Desktop Spot position quantity does not match its allocations.")
    signature = hashlib.sha256(
        json.dumps(
            {"symbol": symbol, "active_allocations": active_entries, "total_qty": _canonical_amount(total_qty)},
            sort_keys=True, separators=(",", ":"),
        ).encode("utf-8")
    ).hexdigest()
    return {"signature": signature, "quantity": _canonical_amount(total_qty)}


def spot_opo_allocation_baseline(
    path: Path, *, symbol: str, list_client_order_id: str, expected_quantity: object,
) -> dict[str, str]:
    """Require one coherent Spot allocation belonging only to the exact OPO list."""
    with ledger_transaction(path):
        return spot_opo_allocation_baseline_unlocked(
            path, symbol=symbol, list_client_order_id=list_client_order_id, expected_quantity=expected_quantity,
        )


def spot_opo_allocation_baseline_unlocked(
    path: Path, *, symbol: str, list_client_order_id: str, expected_quantity: object,
) -> dict[str, str]:
    """Validate an OPO baseline while the caller holds this allocation's transaction."""
    baseline = spot_live_allocation_baseline(path, symbol=symbol)
    if baseline is None:
        raise LiveTradingSafetyError("A recovered Live Spot allocation is required before linked exit.")
    try:
        expected = _stored_decimal(expected_quantity, "OPO entry quantity", positive=True)
        observed = Decimal(baseline["quantity"])
    except (InvalidOperation, KeyError):
        raise LiveTradingSafetyError("Recovered OPO allocation quantity is invalid.") from None
    if observed != expected:
        raise LiveTradingSafetyError("Linked OPO must be the only active allocation for its Spot symbol.")
    data = _load_live_allocation_snapshot(path)
    allocations = data["entry_allocations"]
    assert isinstance(allocations, dict)
    raw_entries = allocations.get(f"{symbol}:L")
    if not isinstance(raw_entries, list):
        raise LiveTradingSafetyError("Recovered OPO allocation is missing from the Live Spot portfolio.")
    active = [
        row for row in raw_entries
        if isinstance(row, dict) and str(row.get("status") or "").lower() == "active"
    ]
    if (
        len(active) != 1
        or active[0].get("client_order_id") != list_client_order_id
        or active[0].get("symbol") != symbol
        or active[0].get("side_key") != "L"
        or _stored_decimal(active[0].get("qty"), "OPO allocation quantity", positive=True) != expected
    ):
        raise LiveTradingSafetyError("The exact OPO allocation is not the sole active Spot inventory.")
    return baseline

def _existing_sell_recovery_proofs(
    allocations: Mapping[str, object], *, signature: str,
) -> list[tuple[dict[str, object], dict[str, object]]]:
    matches: list[tuple[dict[str, object], dict[str, object]]] = []
    for rows in allocations.values():
        if not isinstance(rows, list):
            raise LiveTradingSafetyError("Desktop allocation state contains an invalid allocation list.")
        for row in rows:
            if not isinstance(row, dict):
                raise LiveTradingSafetyError("Desktop allocation state contains an invalid entry.")
            proofs = row.get("spot_sell_recoveries", [])
            if not isinstance(proofs, list):
                raise LiveTradingSafetyError("Desktop Spot SELL recovery evidence is malformed.")
            seen: set[str] = set()
            for proof in proofs:
                if not isinstance(proof, dict):
                    raise LiveTradingSafetyError("Desktop Spot SELL recovery evidence is malformed.")
                proof_signature = proof.get("signature")
                if not isinstance(proof_signature, str) or re.fullmatch(r"[0-9a-f]{64}", proof_signature) is None:
                    raise LiveTradingSafetyError("Desktop Spot SELL recovery evidence is malformed.")
                proof_trade_ids = proof.get("trade_ids")
                if (
                    type(proof.get("version")) is not int or proof["version"] != 1
                    or not isinstance(proof.get("client_order_id"), str)
                    or not proof.get("client_order_id")
                    or type(proof.get("order_id")) is not int
                    or proof["order_id"] <= 0
                    or not isinstance(proof_trade_ids, list)
                    or not proof_trade_ids
                    or any(type(item) is not int or item <= 0 for item in proof_trade_ids)
                    or len(proof_trade_ids) != len(set(proof_trade_ids))
                    or type(proof.get("fill_time_ms")) is not int
                    or proof["fill_time_ms"] <= 0
                    or row.get("side_key") != "L"
                ):
                    raise LiveTradingSafetyError("Desktop Spot SELL recovery evidence is malformed.")
                consumed_qty = _stored_decimal(proof.get("consumed_qty"), "SELL proof quantity", positive=True)
                gross_qty = _stored_decimal(proof.get("gross_qty"), "SELL proof gross quantity", positive=True)
                portfolio_qty = _stored_decimal(proof.get("portfolio_qty"), "SELL proof portfolio quantity", positive=True)
                base_fee_qty = _stored_decimal(proof.get("base_fee_qty"), "SELL proof base commission")
                gross_quote_qty = _stored_decimal(proof.get("gross_quote_qty"), "SELL proof gross proceeds", positive=True)
                quote_fee_qty = _stored_decimal(proof.get("quote_fee_qty"), "SELL proof quote commission")
                total_net_proceeds = _stored_decimal(
                    proof.get("total_net_quote_proceeds"), "SELL proof net proceeds", positive=True,
                )
                baseline_signature = proof.get("pre_order_portfolio_signature")
                if (
                    not isinstance(baseline_signature, str)
                    or re.fullmatch(r"[0-9a-f]{64}", baseline_signature) is None
                ):
                    raise LiveTradingSafetyError("Desktop Spot SELL recovery evidence is malformed.")
                _stored_decimal(proof.get("pre_order_portfolio_qty"), "SELL proof baseline quantity", positive=True)
                _stored_decimal(proof.get("net_quote_proceeds"), "SELL proof proceeds", positive=True)
                _stored_decimal(proof.get("cost_basis"), "SELL proof cost basis", positive=True)
                if (
                    portfolio_qty != gross_qty + base_fee_qty
                    or total_net_proceeds != gross_quote_qty - quote_fee_qty
                    or consumed_qty > portfolio_qty
                ):
                    raise LiveTradingSafetyError("Desktop Spot SELL recovery evidence is inconsistent.")
                if proof_signature in seen:
                    raise LiveTradingSafetyError("Desktop Spot SELL recovery evidence contains a duplicate proof.")
                seen.add(proof_signature)
                if proof_signature == signature:
                    matches.append((row, proof))
    return matches


def _update_spot_position_snapshot(
    record: dict[str, object], *, symbol: str, active_entries: list[dict[str, object]],
) -> None:
    record_data = record.get("data")
    if not isinstance(record_data, dict):
        raise LiveTradingSafetyError("Desktop Spot position snapshot is malformed.")
    total_qty = Decimal(0)
    total_cost = Decimal(0)
    for allocation in active_entries:
        qty = _stored_decimal(allocation.get("qty"), "quantity", positive=True)
        price = _stored_decimal(allocation.get("entry_price"), "entry price", positive=True)
        total_qty += qty
        total_cost += qty * price
    if total_qty <= 0 or total_cost <= 0:
        raise LiveTradingSafetyError("Desktop Spot allocation snapshot has no positive inventory.")
    record["status"] = "Active"
    record["allocations"] = [dict(row) for row in active_entries]
    record_data.update({
        "symbol": symbol,
        "side_key": "L",
        "interval": "RECOVERY",
        "interval_display": "Recovered Spot fill",
        "qty": float(total_qty),
        "entry_price": float(total_cost / total_qty),
        "margin_usdt": float(total_cost),
        "size_usdt": float(total_cost),
    })


def persist_spot_sell_allocation(path: Path, fill: Mapping[str, object]) -> bool:
    """Atomically consume owned Live Spot allocations using exact SELL fill evidence."""
    symbol = fill.get("symbol")
    client_order_id = fill.get("client_order_id")
    signature = fill.get("signature")
    pre_order_signature = fill.get("pre_order_portfolio_signature")
    if (
        not isinstance(symbol, str) or not symbol.isascii() or not symbol.isalnum()
        or symbol != symbol.upper()
        or not isinstance(client_order_id, str) or not client_order_id
        or not isinstance(signature, str) or re.fullmatch(r"[0-9a-f]{64}", signature) is None
        or fill.get("side") != "SELL"
    ):
        raise LiveTradingSafetyError("Recovered Spot SELL allocation identity is invalid.")
    if (
        not isinstance(pre_order_signature, str)
        or re.fullmatch(r"[0-9a-f]{64}", pre_order_signature) is None
    ):
        raise LiveTradingSafetyError("Recovered Spot SELL requires a valid pre-order portfolio baseline.")
    try:
        consumed_qty = Decimal(str(fill.get("portfolio_qty", fill.get("net_qty"))))
        gross_qty = Decimal(str(fill.get("gross_qty")))
        gross_quote_qty = Decimal(str(fill.get("gross_quote_qty")))
        base_fee_qty = Decimal(str(fill.get("base_fee_qty")))
        quote_fee_qty = Decimal(str(fill.get("quote_fee_qty")))
        net_proceeds = Decimal(str(fill.get("net_quote_proceeds")))
        pre_order_qty = Decimal(str(fill.get("pre_order_portfolio_qty")))
        fill_time_ms = int(fill.get("fill_time_ms"))
    except (InvalidOperation, ValueError, TypeError):
        raise LiveTradingSafetyError("Recovered Spot SELL allocation amounts are invalid.") from None
    trade_ids = fill.get("trade_ids")
    order_id = fill.get("order_id")
    base_asset = fill.get("base_asset")
    quote_asset = fill.get("quote_asset")
    commission_rows = fill.get("commissions")
    if (
        not consumed_qty.is_finite() or consumed_qty <= 0
        or not gross_qty.is_finite() or gross_qty <= 0
        or not gross_quote_qty.is_finite() or gross_quote_qty <= 0
        or not base_fee_qty.is_finite() or base_fee_qty < 0
        or not quote_fee_qty.is_finite() or quote_fee_qty < 0
        or consumed_qty != gross_qty + base_fee_qty
        or net_proceeds != gross_quote_qty - quote_fee_qty
        or not net_proceeds.is_finite() or net_proceeds <= 0
        or not pre_order_qty.is_finite() or pre_order_qty <= 0
        or fill_time_ms <= 0
        or not isinstance(trade_ids, list) or not trade_ids
        or any(type(item) is not int or item <= 0 for item in trade_ids)
        or len(trade_ids) != len(set(trade_ids))
        or type(order_id) is not int or order_id <= 0
        or not isinstance(base_asset, str) or not base_asset.isascii() or not base_asset.isalnum()
        or base_asset != base_asset.upper()
        or not isinstance(quote_asset, str) or quote_asset != "USDT"
        or not isinstance(commission_rows, list)
    ):
        raise LiveTradingSafetyError("Recovered Spot SELL allocation amounts are invalid.")
    commission_totals: dict[str, Decimal] = {}
    for commission in commission_rows:
        if not isinstance(commission, Mapping):
            raise LiveTradingSafetyError("Recovered Spot SELL commission evidence is invalid.")
        asset = commission.get("asset")
        amount = commission.get("amount")
        if not isinstance(asset, str) or not asset.isascii() or not asset.isalnum() or asset != asset.upper():
            raise LiveTradingSafetyError("Recovered Spot SELL commission evidence is invalid.")
        parsed_amount = _stored_decimal(amount, "commission")
        if parsed_amount:
            commission_totals[asset] = commission_totals.get(asset, Decimal(0)) + parsed_amount
    if (
        any(asset not in {base_asset, quote_asset} for asset, amount in commission_totals.items() if amount > 0)
        or commission_totals.get(base_asset, Decimal(0)) != base_fee_qty
        or commission_totals.get(quote_asset, Decimal(0)) != quote_fee_qty
    ):
        raise LiveTradingSafetyError("Recovered Spot SELL commission evidence is inconsistent.")

    key = f"{symbol}:L"
    if path.is_symlink():
        raise LiveTradingSafetyError("Desktop allocation state must not be a symbolic link.")
    with ledger_transaction(path):
        data = _load_live_allocation_snapshot(path)
        allocations = data["entry_allocations"]
        records = data["open_position_records"]
        assert isinstance(allocations, dict) and isinstance(records, dict)

        prior_proofs = _existing_sell_recovery_proofs(allocations, signature=signature)
        if prior_proofs:
            prior_consumed = Decimal(0)
            prior_proceeds = Decimal(0)
            for row, proof in prior_proofs:
                if (
                    proof.get("version") != 1
                    or proof.get("client_order_id") != client_order_id
                    or proof.get("order_id") != order_id
                    or proof.get("trade_ids") != trade_ids
                    or proof.get("gross_qty") != _canonical_amount(gross_qty)
                    or proof.get("portfolio_qty") != _canonical_amount(consumed_qty)
                    or proof.get("base_fee_qty") != _canonical_amount(base_fee_qty)
                    or proof.get("gross_quote_qty") != _canonical_amount(gross_quote_qty)
                    or proof.get("quote_fee_qty") != _canonical_amount(quote_fee_qty)
                    or proof.get("total_net_quote_proceeds") != _canonical_amount(net_proceeds)
                    or proof.get("pre_order_portfolio_signature") != pre_order_signature
                    or proof.get("pre_order_portfolio_qty") != _canonical_amount(pre_order_qty)
                    or proof.get("fill_time_ms") != fill_time_ms
                    or row.get("symbol") != symbol
                    or row.get("side_key") != "L"
                ):
                    raise LiveTradingSafetyError("Recovered Spot SELL fill conflicts with its prior portfolio proof.")
                prior_consumed += _stored_decimal(proof.get("consumed_qty"), "SELL proof quantity", positive=True)
                prior_proceeds += _stored_decimal(proof.get("net_quote_proceeds"), "SELL proof proceeds")
            if prior_consumed != consumed_qty or prior_proceeds != net_proceeds:
                raise LiveTradingSafetyError("Recovered Spot SELL fill conflicts with its prior portfolio proof.")
            return True

        baseline = spot_live_allocation_baseline(path, symbol=symbol)
        if (
            baseline is None
            or baseline.get("signature") != pre_order_signature
            or baseline.get("quantity") != _canonical_amount(pre_order_qty)
        ):
            raise LiveTradingSafetyError(
                "Spot SELL portfolio changed after intent creation; manual reconciliation is required."
            )

        raw_entries = allocations.get(key)
        if not isinstance(raw_entries, list):
            raise LiveTradingSafetyError("Owned Spot allocations are missing; SELL recovery is blocked.")
        for stored_key, stored_rows in allocations.items():
            if not isinstance(stored_key, str) or not isinstance(stored_rows, list):
                raise LiveTradingSafetyError("Desktop allocation state contains an invalid allocation list.")
            if stored_key == key:
                continue
            for stored_row in stored_rows:
                if not isinstance(stored_row, dict):
                    raise LiveTradingSafetyError("Desktop allocation state contains an invalid entry.")
                if stored_row.get("symbol") == symbol:
                    stored_status = stored_row.get("status")
                    if not isinstance(stored_status, str) or stored_status.lower() not in {"active", "closed"}:
                        raise LiveTradingSafetyError("Desktop Spot allocation status is invalid.")
                    if stored_status.lower() == "active":
                        raise LiveTradingSafetyError("Active Spot inventory exists outside its canonical allocation key.")
        active_entries: list[dict[str, object]] = []
        seen_buy_ids: set[str] = set()
        for row in raw_entries:
            if not isinstance(row, dict):
                raise LiveTradingSafetyError("Desktop Spot allocation list is malformed.")
            if row.get("symbol") != symbol or row.get("side_key") != "L":
                raise LiveTradingSafetyError("Desktop Spot allocation identity conflicts with the SELL fill.")
            status = row.get("status")
            if not isinstance(status, str) or status.lower() not in {"active", "closed"}:
                raise LiveTradingSafetyError("Desktop Spot allocation status is invalid.")
            if status.lower() != "active":
                continue
            buy_client_order_id = row.get("client_order_id")
            if not isinstance(buy_client_order_id, str) or not buy_client_order_id or buy_client_order_id in seen_buy_ids:
                raise LiveTradingSafetyError("Desktop Spot allocation identity is missing or duplicated.")
            seen_buy_ids.add(buy_client_order_id)
            _stored_decimal(row.get("qty"), "quantity", positive=True)
            _stored_decimal(row.get("entry_price"), "entry price", positive=True)
            active_entries.append(row)

        active_total = sum(
            (_stored_decimal(row.get("qty"), "quantity", positive=True) for row in active_entries),
            Decimal(0),
        )
        if not active_entries or consumed_qty > active_total:
            raise LiveTradingSafetyError("Spot SELL fill exceeds durable owned allocation inventory.")

        record = records.get(key)
        if (
            not isinstance(record, dict)
            or record.get("symbol") != symbol
            or record.get("side_key") != "L"
            or not isinstance(record.get("status", "Active"), str)
            or record.get("status", "Active").lower() != "active"
        ):
            raise LiveTradingSafetyError("Desktop Spot position snapshot conflicts with owned allocations.")
        record_data = record.get("data")
        snapshot_entries = record.get("allocations")
        if not isinstance(record_data, dict) or not isinstance(snapshot_entries, list):
            raise LiveTradingSafetyError("Desktop Spot position snapshot is malformed.")
        snapshot_active: dict[str, Decimal] = {}
        for row in snapshot_entries:
            if not isinstance(row, dict):
                raise LiveTradingSafetyError("Desktop Spot position allocation snapshot is malformed.")
            snapshot_status = row.get("status")
            if not isinstance(snapshot_status, str) or snapshot_status.lower() not in {"active", "closed"}:
                raise LiveTradingSafetyError("Desktop Spot position allocation status is invalid.")
            if snapshot_status.lower() != "active":
                continue
            row_id = row.get("client_order_id")
            if not isinstance(row_id, str) or row_id in snapshot_active:
                raise LiveTradingSafetyError("Desktop Spot position allocation identity is invalid.")
            snapshot_active[row_id] = _stored_decimal(row.get("qty"), "snapshot quantity", positive=True)
        main_active = {
            str(row["client_order_id"]): _stored_decimal(row.get("qty"), "quantity", positive=True)
            for row in active_entries
        }
        if snapshot_active != main_active:
            raise LiveTradingSafetyError("Desktop Spot position snapshot does not match owned allocations.")
        snapshot_qty = _stored_decimal(record_data.get("qty"), "snapshot total quantity", positive=True)
        if snapshot_qty != active_total:
            raise LiveTradingSafetyError("Desktop Spot position quantity does not match owned allocations.")

        remaining_to_consume = consumed_qty
        allocated_proceeds = Decimal(0)
        affected: list[tuple[dict[str, object], Decimal, Decimal]] = []
        for index, row in enumerate(active_entries):
            if remaining_to_consume <= 0:
                break
            row_qty = _stored_decimal(row.get("qty"), "quantity", positive=True)
            consumed_here = min(row_qty, remaining_to_consume)
            row_price = _stored_decimal(row.get("entry_price"), "entry price", positive=True)
            if index == len(active_entries) - 1 or consumed_here == remaining_to_consume:
                proceeds_here = net_proceeds - allocated_proceeds
            else:
                proceeds_here = net_proceeds * consumed_here / consumed_qty
                allocated_proceeds += proceeds_here
            affected.append((row, consumed_here, proceeds_here))
            remaining_to_consume -= consumed_here
        if remaining_to_consume != 0 or not affected:
            raise LiveTradingSafetyError("Spot SELL fill exceeds durable owned allocation inventory.")

        close_time = _display_time(fill_time_ms)
        for row, consumed_here, proceeds_here in affected:
            row_qty = _stored_decimal(row.get("qty"), "quantity", positive=True)
            row_price = _stored_decimal(row.get("entry_price"), "entry price", positive=True)
            remaining_qty = row_qty - consumed_here
            cost_basis = row_price * consumed_here
            proof = {
                "version": 1,
                "signature": signature,
                "client_order_id": client_order_id,
                "order_id": order_id,
                "trade_ids": list(trade_ids),
                "consumed_qty": _canonical_amount(consumed_here),
                "gross_qty": _canonical_amount(gross_qty),
                "portfolio_qty": _canonical_amount(consumed_qty),
                "base_fee_qty": _canonical_amount(base_fee_qty),
                "gross_quote_qty": _canonical_amount(gross_quote_qty),
                "quote_fee_qty": _canonical_amount(quote_fee_qty),
                "total_net_quote_proceeds": _canonical_amount(net_proceeds),
                "pre_order_portfolio_signature": pre_order_signature,
                "pre_order_portfolio_qty": _canonical_amount(pre_order_qty),
                "net_quote_proceeds": _canonical_amount(proceeds_here),
                "cost_basis": _canonical_amount(cost_basis),
                "fill_time_ms": fill_time_ms,
            }
            proofs = row.setdefault("spot_sell_recoveries", [])
            if not isinstance(proofs, list):
                raise LiveTradingSafetyError("Desktop Spot SELL recovery evidence is malformed.")
            proofs.append(proof)
            if remaining_qty <= 0:
                row["qty"] = float(consumed_here)
                row["status"] = "Closed"
                row["close_time"] = close_time
                row["pnl_value"] = float(sum((
                    Decimal(str(previous.get("net_quote_proceeds") or "0"))
                    - Decimal(str(previous.get("cost_basis") or "0"))
                    for previous in proofs if isinstance(previous, Mapping)
                ), Decimal(0)))
                continue
            ratio = remaining_qty / row_qty
            row["qty"] = float(remaining_qty)
            for field in ("margin_usdt", "margin_balance", "notional", "size_usdt"):
                if field in row and row[field] not in (None, ""):
                    row[field] = float(_stored_decimal(row[field], field) * ratio)

        active_after = [
            row for row in raw_entries
            if isinstance(row, dict) and str(row.get("status") or "").lower() == "active"
        ]
        if active_after:
            _update_spot_position_snapshot(record, symbol=symbol, active_entries=active_after)
        else:
            records.pop(key, None)
        data["timestamp"] = time.time()
        write_ledger(path, data)
    return True


def has_durable_spot_opo_strategy_sell(
    path: Path, intent: Mapping[str, object], *, signature: str, consumed_quantity: object,
) -> bool:
    """Find the exact linked SELL proof on its OPO allocation after restart."""
    list_client_id = intent.get("client_order_id")
    exit_client_id = intent.get("strategy_exit_client_order_id")
    if (
        not isinstance(list_client_id, str) or not list_client_id
        or not isinstance(exit_client_id, str) or not exit_client_id
        or not isinstance(signature, str) or re.fullmatch(r"[0-9a-f]{64}", signature) is None
    ):
        return False
    try:
        expected = _stored_decimal(consumed_quantity, "linked SELL quantity", positive=True)
        with ledger_transaction(path):
            data = _load_live_allocation_snapshot(path)
    except (LiveTradingSafetyError, InvalidOperation):
        return False
    allocations = data["entry_allocations"]
    assert isinstance(allocations, dict)
    matches = [
        row for rows in allocations.values() if isinstance(rows, list)
        for row in rows if isinstance(row, dict) and row.get("client_order_id") == list_client_id
    ]
    if len(matches) != 1:
        return False
    row = matches[0]
    proofs = row.get("spot_sell_recoveries")
    if not isinstance(proofs, list):
        return False
    exact = [
        proof for proof in proofs
        if isinstance(proof, Mapping)
        and proof.get("signature") == signature
        and proof.get("client_order_id") == exit_client_id
        and proof.get("order_id") == intent.get("strategy_exit_order_id")
    ]
    if len(exact) != 1:
        return False
    proof = exact[0]
    try:
        return (
            _stored_decimal(proof.get("consumed_qty"), "linked SELL proof quantity", positive=True) == expected
            and _stored_decimal(proof.get("portfolio_qty"), "linked SELL portfolio quantity", positive=True) == expected
            and proof.get("trade_ids") == intent.get("strategy_exit_trade_ids")
            and proof.get("pre_order_portfolio_signature") == intent.get("strategy_exit_pre_order_signature")
            and _stored_decimal(
                proof.get("pre_order_portfolio_qty"), "linked SELL baseline quantity", positive=True,
            ) == _stored_decimal(
                intent.get("strategy_exit_pre_order_quantity"), "linked SELL baseline quantity", positive=True,
            )
            and str(row.get("status") or "").lower() == "closed"
        )
    except (LiveTradingSafetyError, InvalidOperation):
        return False


def persist_spot_opo_strategy_sell_allocation(path: Path, fill: Mapping[str, object]) -> bool:
    """Apply linked SELL trades only to the sole allocation owned by that OPO."""
    list_client_id = fill.get("opo_list_client_order_id")
    entry_quantity = fill.get("opo_entry_portfolio_quantity")
    signature = fill.get("signature")
    if (
        not isinstance(list_client_id, str) or not list_client_id
        or not isinstance(signature, str) or re.fullmatch(r"[0-9a-f]{64}", signature) is None
        or fill.get("side") != "SELL"
        or fill.get("type") != "MARKET"
    ):
        raise LiveTradingSafetyError("Recovered OPO strategy SELL identity is invalid.")
    try:
        expected = _stored_decimal(entry_quantity, "OPO entry quantity", positive=True)
        consumed = _stored_decimal(fill.get("portfolio_qty"), "linked SELL consumed quantity", positive=True)
        baseline_quantity = _stored_decimal(
            fill.get("pre_order_portfolio_qty"), "linked SELL baseline quantity", positive=True,
        )
    except (InvalidOperation, TypeError):
        raise LiveTradingSafetyError("Recovered OPO strategy SELL quantities are invalid.") from None
    if consumed > expected or baseline_quantity != expected:
        raise LiveTradingSafetyError("Linked OPO strategy SELL exceeds its exact recovered allocation.")

    existing = _load_live_allocation_snapshot(path)
    allocations = existing["entry_allocations"]
    assert isinstance(allocations, dict)
    existing_proofs = _existing_sell_recovery_proofs(allocations, signature=signature)
    if existing_proofs:
        if len(existing_proofs) != 1 or existing_proofs[0][0].get("client_order_id") != list_client_id:
            raise LiveTradingSafetyError("Linked OPO strategy SELL proof belongs to another allocation.")
        # The generic persister validates all execution fields and makes this
        # path idempotent before checking a now-consumed portfolio baseline.
        return persist_spot_sell_allocation(path, fill)

    baseline = spot_opo_allocation_baseline(
        path,
        symbol=str(fill.get("symbol") or ""),
        list_client_order_id=list_client_id,
        expected_quantity=expected,
    )
    if (
        baseline.get("signature") != fill.get("pre_order_portfolio_signature")
        or baseline.get("quantity") != _canonical_amount(baseline_quantity)
    ):
        raise LiveTradingSafetyError("Spot portfolio changed after the linked SELL intent was recorded.")
    return persist_spot_sell_allocation(path, fill)


def has_durable_spot_opo_strategy_sell_recovery(
    path: Path,
    intent: Mapping[str, object],
    *,
    signature: str,
    consumed_quantity: object,
    remaining_quantity: object,
    trade_ids: list[int],
) -> bool:
    """Prove the exact terminal linked SELL left one known OPO remainder."""
    list_client_id = intent.get("client_order_id")
    exit_client_id = intent.get("strategy_exit_client_order_id")
    if (
        not isinstance(list_client_id, str) or not list_client_id
        or not isinstance(exit_client_id, str) or not exit_client_id
        or not isinstance(signature, str) or re.fullmatch(r"[0-9a-f]{64}", signature) is None
        or not isinstance(trade_ids, list) or not trade_ids
    ):
        return False
    try:
        consumed = _stored_decimal(consumed_quantity, "linked SELL quantity", positive=True)
        remaining = _stored_decimal(remaining_quantity, "remaining OPO quantity", positive=True)
        with ledger_transaction(path):
            data = _load_live_allocation_snapshot(path)
    except (LiveTradingSafetyError, InvalidOperation):
        return False
    allocations = data["entry_allocations"]
    records = data["open_position_records"]
    assert isinstance(allocations, dict) and isinstance(records, dict)
    matches = [
        row for rows in allocations.values() if isinstance(rows, list)
        for row in rows if isinstance(row, dict) and row.get("client_order_id") == list_client_id
    ]
    if len(matches) != 1:
        return False
    row = matches[0]
    proofs = row.get("spot_sell_recoveries")
    if not isinstance(proofs, list):
        return False
    exact = [
        proof for proof in proofs
        if isinstance(proof, Mapping)
        and proof.get("signature") == signature
        and proof.get("client_order_id") == exit_client_id
        and proof.get("order_id") == intent.get("strategy_exit_order_id")
    ]
    try:
        if (
            len(exact) != 1
            or _stored_decimal(exact[0].get("consumed_qty"), "linked SELL proof quantity", positive=True) != consumed
            or _stored_decimal(exact[0].get("portfolio_qty"), "linked SELL proof portfolio quantity", positive=True) != consumed
            or exact[0].get("trade_ids") != trade_ids
            or exact[0].get("pre_order_portfolio_signature") != intent.get("strategy_exit_pre_order_signature")
            or _stored_decimal(
                exact[0].get("pre_order_portfolio_qty"), "linked SELL baseline quantity", positive=True,
            ) != _stored_decimal(
                intent.get("strategy_exit_pre_order_quantity"), "linked SELL baseline quantity", positive=True,
            )
            or str(row.get("status") or "").lower() != "active"
            or row.get("symbol") != intent.get("symbol")
            or row.get("side_key") != "L"
            or _stored_decimal(row.get("qty"), "remaining OPO quantity", positive=True) != remaining
        ):
            return False
        key = f"{intent.get('symbol')}:L"
        active = [
            item for item in allocations.get(key, [])
            if isinstance(item, Mapping) and str(item.get("status") or "").lower() == "active"
        ]
        if len(active) != 1 or active[0].get("client_order_id") != list_client_id:
            return False
        baseline = spot_live_allocation_baseline(path, symbol=str(intent.get("symbol") or ""))
        return baseline is not None and baseline.get("quantity") == _canonical_amount(remaining)
    except (LiveTradingSafetyError, InvalidOperation, TypeError):
        return False


def persist_spot_opo_residual_stop_allocation(path: Path, fill: Mapping[str, object]) -> bool:
    """Apply a re-armed STOP_LOSS SELL only to the sole exact OPO residual."""
    list_client_id = fill.get("opo_list_client_order_id")
    residual_client_id = fill.get("residual_stop_client_order_id")
    signature = fill.get("signature")
    if (
        not isinstance(list_client_id, str) or not list_client_id
        or not isinstance(residual_client_id, str) or not residual_client_id
        or not isinstance(signature, str) or re.fullmatch(r"[0-9a-f]{64}", signature) is None
        or fill.get("side") != "SELL"
        or fill.get("type") != "STOP_LOSS"
    ):
        raise LiveTradingSafetyError("Recovered OPO residual stop identity is invalid.")
    try:
        residual_quantity = _stored_decimal(
            fill.get("residual_stop_pre_order_quantity"), "residual stop baseline quantity", positive=True,
        )
        entry_quantity = _stored_decimal(fill.get("opo_entry_portfolio_quantity"), "OPO entry quantity", positive=True)
        consumed_quantity = _stored_decimal(fill.get("portfolio_qty"), "residual stop consumed quantity", positive=True)
    except (InvalidOperation, TypeError):
        raise LiveTradingSafetyError("Recovered OPO residual stop quantities are invalid.") from None
    # A zero-fill linked SELL can require protection of the entire entry.
    if residual_quantity > entry_quantity or consumed_quantity > residual_quantity:
        raise LiveTradingSafetyError("Recovered residual stop SELL exceeds its exact OPO remainder.")

    normalized = dict(fill)
    normalized.update({
        "client_order_id": residual_client_id,
        "pre_order_portfolio_signature": fill.get("residual_stop_pre_order_signature"),
        "pre_order_portfolio_qty": _canonical_amount(residual_quantity),
    })

    existing = _load_live_allocation_snapshot(path)
    allocations = existing["entry_allocations"]
    assert isinstance(allocations, dict)
    prior = _existing_sell_recovery_proofs(allocations, signature=signature)
    if prior:
        if len(prior) != 1 or prior[0][1].get("client_order_id") != residual_client_id:
            raise LiveTradingSafetyError("Residual OPO stop proof belongs to another allocation or order.")
        return persist_spot_sell_allocation(path, normalized)

    baseline = spot_opo_allocation_baseline(
        path,
        symbol=str(fill.get("symbol") or ""),
        list_client_order_id=list_client_id,
        expected_quantity=residual_quantity,
    )
    if (
        baseline.get("signature") != fill.get("residual_stop_pre_order_signature")
        or baseline.get("quantity") != _canonical_amount(residual_quantity)
    ):
        raise LiveTradingSafetyError("Spot portfolio changed after residual-stop intent creation.")
    return persist_spot_sell_allocation(path, normalized)


def has_durable_spot_opo_residual_stop_allocation(
    path: Path,
    intent: Mapping[str, object],
    *,
    signature: str,
    consumed_quantity: object,
    remaining_quantity: object,
    trade_ids: list[int],
) -> bool:
    """Prove a residual-stop fill affected only its exact OPO allocation."""
    list_client_id = intent.get("client_order_id")
    stop_request = intent.get("residual_stop_request")
    if (
        not isinstance(list_client_id, str) or not list_client_id
        or not isinstance(stop_request, Mapping)
        or not isinstance(signature, str) or re.fullmatch(r"[0-9a-f]{64}", signature) is None
        or not isinstance(trade_ids, list) or not trade_ids
    ):
        return False
    try:
        residual_id = str(stop_request.get("newClientOrderId") or "")
        consumed = _stored_decimal(consumed_quantity, "residual stop consumed quantity", positive=True)
        remaining = _stored_decimal(remaining_quantity, "remaining OPO quantity")
        with ledger_transaction(path):
            data = _load_live_allocation_snapshot(path)
    except (LiveTradingSafetyError, InvalidOperation):
        return False
    allocations = data["entry_allocations"]
    records = data["open_position_records"]
    assert isinstance(allocations, dict) and isinstance(records, dict)
    matches = [
        (key, row) for key, rows in allocations.items() if isinstance(rows, list)
        for row in rows if isinstance(row, dict) and row.get("client_order_id") == list_client_id
    ]
    if len(matches) != 1 or matches[0][0] != f"{intent.get('symbol')}:L":
        return False
    key, row = matches[0]
    proofs = row.get("spot_sell_recoveries")
    if not isinstance(proofs, list):
        return False
    exact = [
        proof for proof in proofs
        if isinstance(proof, Mapping)
        and proof.get("signature") == signature
        and proof.get("client_order_id") == residual_id
        and proof.get("order_id") == intent.get("residual_stop_order_id")
    ]
    try:
        if (
            len(exact) != 1
            or _stored_decimal(exact[0].get("consumed_qty"), "residual stop proof quantity", positive=True) != consumed
            or _stored_decimal(exact[0].get("portfolio_qty"), "residual stop portfolio quantity", positive=True) != consumed
            or exact[0].get("trade_ids") != trade_ids
            or exact[0].get("pre_order_portfolio_signature") != intent.get("residual_stop_pre_order_signature")
            or _stored_decimal(
                exact[0].get("pre_order_portfolio_qty"), "residual stop baseline quantity", positive=True,
            ) != _stored_decimal(
                intent.get("residual_stop_pre_order_quantity"), "residual stop baseline quantity", positive=True,
            )
        ):
            return False
        status = str(row.get("status") or "").lower()
        if remaining == 0:
            return status == "closed" and key not in records
        if (
            status != "active"
            or _stored_decimal(row.get("qty"), "remaining OPO quantity", positive=True) != remaining
        ):
            return False
        active = [
            item for item in allocations.get(key, [])
            if isinstance(item, Mapping) and str(item.get("status") or "").lower() == "active"
        ]
        if len(active) != 1 or active[0].get("client_order_id") != list_client_id:
            return False
        baseline = spot_live_allocation_baseline(path, symbol=str(intent.get("symbol") or ""))
        return baseline is not None and Decimal(baseline["quantity"]) == remaining
    except (LiveTradingSafetyError, InvalidOperation, TypeError):
        return False


def persist_spot_opo_stop_sell_allocation(path: Path, fill: Mapping[str, object]) -> bool:
    """Close only the BUY allocation proved by one fully filled linked OPO stop."""
    symbol = fill.get("symbol")
    list_client_order_id = fill.get("opo_list_client_order_id")
    pending_client_order_id = fill.get("opo_pending_client_order_id")
    entry_signature = fill.get("entry_recovery_signature")
    signature = fill.get("signature")
    try:
        list_id = fill.get("opo_order_list_id")
        stop_order_id = fill.get("order_id")
        entry_quantity = Decimal(str(fill.get("entry_portfolio_quantity")))
        consumed_qty = Decimal(str(fill.get("portfolio_qty")))
        gross_qty = Decimal(str(fill.get("gross_qty")))
        base_fee_qty = Decimal(str(fill.get("base_fee_qty")))
        gross_quote_qty = Decimal(str(fill.get("gross_quote_qty")))
        quote_fee_qty = Decimal(str(fill.get("quote_fee_qty")))
        net_proceeds = Decimal(str(fill.get("net_quote_proceeds")))
        fill_time_ms = int(fill.get("fill_time_ms"))
    except (InvalidOperation, TypeError, ValueError):
        raise LiveTradingSafetyError("Recovered OPO stop SELL amounts are invalid.") from None
    trade_ids = fill.get("trade_ids")
    base_asset = fill.get("base_asset")
    commission_rows = fill.get("commissions")
    if (
        not isinstance(symbol, str) or not symbol.isascii() or not symbol.isalnum() or symbol != symbol.upper()
        or not isinstance(list_client_order_id, str) or not list_client_order_id
        or not isinstance(pending_client_order_id, str) or not pending_client_order_id
        or not isinstance(entry_signature, str) or re.fullmatch(r"[0-9a-f]{64}", entry_signature) is None
        or not isinstance(signature, str) or re.fullmatch(r"[0-9a-f]{64}", signature) is None
        or type(list_id) is not int or list_id < 0
        or type(stop_order_id) is not int or stop_order_id <= 0
        or not entry_quantity.is_finite() or entry_quantity <= 0
        or not consumed_qty.is_finite() or consumed_qty != entry_quantity
        or not gross_qty.is_finite() or gross_qty != entry_quantity
        or not base_fee_qty.is_finite() or base_fee_qty < 0
        or consumed_qty != gross_qty + base_fee_qty
        or not gross_quote_qty.is_finite() or gross_quote_qty <= 0
        or not quote_fee_qty.is_finite() or quote_fee_qty < 0
        or not net_proceeds.is_finite() or net_proceeds != gross_quote_qty - quote_fee_qty or net_proceeds <= 0
        or fill_time_ms <= 0
        or not isinstance(trade_ids, list) or not trade_ids
        or any(type(item) is not int or item <= 0 for item in trade_ids)
        or len(trade_ids) != len(set(trade_ids))
        or not isinstance(base_asset, str) or not base_asset.isascii() or not base_asset.isalnum()
        or base_asset != base_asset.upper()
        or not isinstance(commission_rows, list)
        or fill.get("side") != "SELL"
        or fill.get("type") != "STOP_LOSS"
        or fill.get("quote_asset") != "USDT"
    ):
        raise LiveTradingSafetyError("Recovered OPO stop SELL identity or quantities are invalid.")

    commission_totals: dict[str, Decimal] = {}
    for commission in commission_rows:
        if not isinstance(commission, Mapping):
            raise LiveTradingSafetyError("Recovered OPO stop SELL commission evidence is invalid.")
        asset = commission.get("asset")
        if not isinstance(asset, str) or not asset.isascii() or not asset.isalnum() or asset != asset.upper():
            raise LiveTradingSafetyError("Recovered OPO stop SELL commission evidence is invalid.")
        amount = _stored_decimal(commission.get("amount"), "commission")
        if amount:
            commission_totals[asset] = commission_totals.get(asset, Decimal(0)) + amount
    if (
        any(asset not in {base_asset, "USDT"} for asset, amount in commission_totals.items() if amount > 0)
        or commission_totals.get(base_asset, Decimal(0)) != base_fee_qty
        or commission_totals.get("USDT", Decimal(0)) != quote_fee_qty
    ):
        raise LiveTradingSafetyError("Recovered OPO stop SELL commission evidence is inconsistent.")

    key = f"{symbol}:L"
    if path.is_symlink():
        raise LiveTradingSafetyError("Desktop allocation state must not be a symbolic link.")
    with ledger_transaction(path):
        data = _load_live_allocation_snapshot(path)
        allocations = data["entry_allocations"]
        records = data["open_position_records"]
        assert isinstance(allocations, dict) and isinstance(records, dict)
        matches: list[tuple[str, dict[str, object]]] = []
        for stored_key, rows in allocations.items():
            if not isinstance(stored_key, str) or not isinstance(rows, list):
                raise LiveTradingSafetyError("Desktop allocation state contains an invalid allocation list.")
            for row in rows:
                if not isinstance(row, dict):
                    raise LiveTradingSafetyError("Desktop allocation state contains an invalid entry.")
                if row.get("client_order_id") == list_client_order_id:
                    matches.append((stored_key, row))
        if len(matches) != 1 or matches[0][0] != key:
            raise LiveTradingSafetyError("Linked OPO BUY allocation is missing or duplicated.")
        row = matches[0][1]

        prior = row.get("spot_opo_stop_recovery")
        if prior is not None:
            if (
                not isinstance(prior, Mapping)
                or prior.get("signature") != signature
                or prior.get("entry_recovery_signature") != entry_signature
                or prior.get("pending_client_order_id") != pending_client_order_id
                or prior.get("order_list_id") != list_id
                or prior.get("order_id") != stop_order_id
                or prior.get("entry_quantity") != _canonical_amount(entry_quantity)
                or prior.get("consumed_qty") != _canonical_amount(consumed_qty)
                or prior.get("trade_ids") != trade_ids
                or prior.get("fill_time_ms") != fill_time_ms
                or str(row.get("status") or "").lower() != "closed"
            ):
                raise LiveTradingSafetyError("OPO stop SELL conflicts with its prior durable allocation proof.")
            return True

        if str(row.get("status") or "").lower() != "active":
            raise LiveTradingSafetyError("Linked OPO BUY allocation is not active; manual reconciliation is required.")
        entry_recovery = row.get("spot_fill_recovery")
        row_qty = _stored_decimal(row.get("qty"), "quantity", positive=True)
        entry_price = _stored_decimal(row.get("entry_price"), "entry price", positive=True)
        if (
            row.get("symbol") != symbol
            or row.get("side_key") != "L"
            or row_qty != entry_quantity
            or not isinstance(entry_recovery, Mapping)
            or entry_recovery.get("signature") != entry_signature
            or entry_recovery.get("exchange_client_order_id") != fill.get("entry_working_client_order_id")
            or str(entry_recovery.get("order_id")) != str(fill.get("entry_working_order_id"))
            or _stored_decimal(entry_recovery.get("pending_order_qty"), "linked stop quantity", positive=True)
            != entry_quantity
        ):
            raise LiveTradingSafetyError("Linked OPO BUY allocation does not match the recovered stop SELL.")
        if row.get("spot_sell_recoveries"):
            raise LiveTradingSafetyError("Linked OPO allocation has other SELL history; manual reconciliation is required.")

        raw_entries = allocations.get(key)
        if not isinstance(raw_entries, list):
            raise LiveTradingSafetyError("Desktop Spot allocation list is missing.")
        for stored_key, stored_rows in allocations.items():
            if stored_key == key:
                continue
            for stored_row in stored_rows:
                if stored_row.get("symbol") == symbol and str(stored_row.get("status") or "").lower() == "active":
                    raise LiveTradingSafetyError("Active Spot inventory exists outside its canonical allocation key.")
        active_entries: list[dict[str, object]] = []
        active_ids: set[str] = set()
        for allocation in raw_entries:
            if not isinstance(allocation, dict) or allocation.get("symbol") != symbol or allocation.get("side_key") != "L":
                raise LiveTradingSafetyError("Desktop Spot allocation identity conflicts with the OPO stop SELL.")
            status = str(allocation.get("status") or "").lower()
            if status not in {"active", "closed"}:
                raise LiveTradingSafetyError("Desktop Spot allocation status is invalid.")
            if status == "active":
                allocation_id = allocation.get("client_order_id")
                if not isinstance(allocation_id, str) or allocation_id in active_ids:
                    raise LiveTradingSafetyError("Desktop Spot allocation identity is missing or duplicated.")
                active_ids.add(allocation_id)
                _stored_decimal(allocation.get("qty"), "quantity", positive=True)
                _stored_decimal(allocation.get("entry_price"), "entry price", positive=True)
                active_entries.append(allocation)
        if row not in active_entries:
            raise LiveTradingSafetyError("Linked OPO BUY allocation is not present in active inventory.")

        record = records.get(key)
        if (
            not isinstance(record, dict)
            or record.get("symbol") != symbol
            or record.get("side_key") != "L"
            or str(record.get("status", "Active")).lower() != "active"
        ):
            raise LiveTradingSafetyError("Desktop Spot position snapshot conflicts with owned allocations.")
        record_data = record.get("data")
        snapshot_rows = record.get("allocations")
        if not isinstance(record_data, dict) or not isinstance(snapshot_rows, list):
            raise LiveTradingSafetyError("Desktop Spot position snapshot is malformed.")
        main_active = {
            str(item["client_order_id"]): _stored_decimal(item.get("qty"), "quantity", positive=True)
            for item in active_entries
        }
        snapshot_active: dict[str, Decimal] = {}
        for snapshot in snapshot_rows:
            if not isinstance(snapshot, dict):
                raise LiveTradingSafetyError("Desktop Spot position allocation snapshot is malformed.")
            snapshot_status = str(snapshot.get("status") or "").lower()
            if snapshot_status not in {"active", "closed"}:
                raise LiveTradingSafetyError("Desktop Spot position allocation status is invalid.")
            if snapshot_status == "active":
                snapshot_id = snapshot.get("client_order_id")
                if not isinstance(snapshot_id, str) or snapshot_id in snapshot_active:
                    raise LiveTradingSafetyError("Desktop Spot position allocation identity is invalid.")
                snapshot_active[snapshot_id] = _stored_decimal(snapshot.get("qty"), "snapshot quantity", positive=True)
        active_total = sum(main_active.values(), Decimal(0))
        if (
            snapshot_active != main_active
            or _stored_decimal(record_data.get("qty"), "snapshot total quantity", positive=True) != active_total
        ):
            raise LiveTradingSafetyError("Desktop Spot position snapshot does not match its allocations.")

        cost_basis = row_qty * entry_price
        proof = {
            "version": 1,
            "signature": signature,
            "client_order_id": list_client_order_id,
            "pending_client_order_id": pending_client_order_id,
            "order_list_id": list_id,
            "order_id": stop_order_id,
            "trade_ids": list(trade_ids),
            "entry_recovery_signature": entry_signature,
            "entry_quantity": _canonical_amount(entry_quantity),
            "consumed_qty": _canonical_amount(consumed_qty),
            "gross_qty": _canonical_amount(gross_qty),
            "base_fee_qty": _canonical_amount(base_fee_qty),
            "gross_quote_qty": _canonical_amount(gross_quote_qty),
            "quote_fee_qty": _canonical_amount(quote_fee_qty),
            "net_quote_proceeds": _canonical_amount(net_proceeds),
            "cost_basis": _canonical_amount(cost_basis),
            "fill_time_ms": fill_time_ms,
        }
        row["spot_opo_stop_recovery"] = proof
        row["status"] = "Closed"
        row["close_time"] = _display_time(fill_time_ms)
        row["pnl_value"] = float(net_proceeds - cost_basis)
        active_after = [allocation for allocation in active_entries if allocation is not row]
        if active_after:
            _update_spot_position_snapshot(record, symbol=symbol, active_entries=active_after)
        else:
            records.pop(key, None)
        data["timestamp"] = time.time()
        write_ledger(path, data)
    return True


def has_durable_spot_opo_stop_exit(
    record: Mapping[str, object], *, signature: str, portfolio_quantity: object,
) -> bool:
    """Check that one OPO allocation durably records the exact linked stop exit."""
    try:
        if re.fullmatch(r"[0-9a-f]{64}", signature) is None:
            return False
        from app.gui.shared.allocation_persistence import get_position_allocations_path

        app_root = Path(__file__).resolve().parents[4]
        path = get_position_allocations_path(app_root / "gui" / "window_shell.py")
        if path.is_symlink() or not path.is_file():
            return False
        data = json.loads(path.read_text(encoding="utf-8"), object_pairs_hook=_unique_json_object)
        allocations = data.get("entry_allocations") if isinstance(data, dict) else None
        if data.get("version") != 1 or data.get("mode") != "Live" or not isinstance(allocations, dict):
            return False
        request = validate_spot_opo_request_payload(record.get("request"))
        expected_qty = Decimal(str(portfolio_quantity))
        if not expected_qty.is_finite() or expected_qty <= 0:
            return False
        matches = []
        for rows in allocations.values():
            if not isinstance(rows, list):
                return False
            for row in rows:
                if not isinstance(row, dict):
                    return False
                if row.get("client_order_id") == request["listClientOrderId"]:
                    matches.append(row)
        if len(matches) != 1:
            return False
        row = matches[0]
        proof = row.get("spot_opo_stop_recovery")
        entry_proof = row.get("spot_fill_recovery")
        return (
            row.get("symbol") == request["symbol"]
            and row.get("side_key") == "L"
            and str(row.get("status") or "").lower() == "closed"
            and isinstance(proof, Mapping)
            and proof.get("signature") == signature
            and proof.get("client_order_id") == request["listClientOrderId"]
            and proof.get("pending_client_order_id") == request["pendingClientOrderId"]
            and proof.get("order_list_id") == record.get("exchange_order_list_id")
            and proof.get("order_id") == record.get("pending_order_id")
            and proof.get("entry_recovery_signature") == record.get("entry_recovery_signature")
            and _stored_decimal(proof.get("entry_quantity"), "OPO exit entry quantity", positive=True) == expected_qty
            and _stored_decimal(proof.get("consumed_qty"), "OPO exit consumed quantity", positive=True) == expected_qty
            and isinstance(entry_proof, Mapping)
            and entry_proof.get("signature") == record.get("entry_recovery_signature")
            and entry_proof.get("exchange_client_order_id") == request["workingClientOrderId"]
            and str(entry_proof.get("order_id")) == str(record.get("working_order_id"))
            and _stored_decimal(entry_proof.get("pending_order_qty"), "linked stop quantity", positive=True) == expected_qty
        )
    except Exception:
        return False
