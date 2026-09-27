"""Exact, idempotent recovery of terminal Binance Spot market BUY fills."""

from __future__ import annotations

import hashlib
import json
import time
from collections.abc import Mapping, Sequence
from datetime import datetime
from decimal import Decimal, InvalidOperation
from pathlib import Path

from app.settings.live_safety import LiveTradingSafetyError

from .order_intent_store import ledger_transaction, write_ledger


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
    """Validate exact order/trade agreement and calculate commission-aware inventory."""
    symbol = intent.get("symbol")
    client_order_id = intent.get("client_order_id")
    order_id = _positive_id(order_response.get("orderId"), "order ID")
    if (
        intent.get("market") != "spot"
        or intent.get("type") != "MARKET"
        or intent.get("side") != "BUY"
        or not isinstance(symbol, str)
        or order_response.get("symbol") != symbol
        or order_response.get("clientOrderId") != client_order_id
        or order_response.get("status") not in _TERMINAL_STATUSES
        or (intent.get("exchange_order_id") and str(intent["exchange_order_id"]) != str(order_id))
    ):
        raise LiveTradingSafetyError("Spot fill recovery requires the exact terminal BUY market intent.")
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
            or trade.get("isBuyer") is not True
        ):
            raise LiveTradingSafetyError("Binance Spot trade row does not belong to the requested BUY order.")
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
    net_qty = expected_qty - base_fee
    net_quote_cost = expected_quote + quote_fee
    if net_qty <= 0 or net_quote_cost <= 0:
        raise LiveTradingSafetyError("Spot BUY commissions leave no positive recoverable inventory.")

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
    signature = hashlib.sha256(
        json.dumps(signature_payload, sort_keys=True, separators=(",", ":")).encode("utf-8")
    ).hexdigest()
    return {
        "symbol": symbol,
        "client_order_id": client_order_id,
        "order_id": order_id,
        "trade_ids": sorted(trade_ids),
        "trade_count": len(trade_ids),
        "gross_qty": _canonical_amount(expected_qty),
        "net_qty": _canonical_amount(net_qty),
        "gross_quote_qty": _canonical_amount(expected_quote),
        "net_quote_cost": _canonical_amount(net_quote_cost),
        "average_cost": _canonical_amount(net_quote_cost / net_qty),
        "commissions": commission_rows,
        "base_asset": base_asset,
        "quote_asset": quote_asset,
        "fill_time_ms": latest_time,
        "signature": signature,
    }


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
    symbol = fill.get("symbol")
    client_order_id = fill.get("client_order_id")
    signature = fill.get("signature")
    if (
        not isinstance(symbol, str) or not symbol.isascii() or not symbol.isalnum()
        or symbol != symbol.upper()
        or not isinstance(client_order_id, str) or not client_order_id
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

    if path.is_symlink():
        raise LiveTradingSafetyError("Desktop allocation state must not be a symbolic link.")
    with ledger_transaction(path):
        if path.exists():
            try:
                data = json.loads(path.read_text(encoding="utf-8"), object_pairs_hook=_unique_json_object)
            except Exception as exc:
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
            if isinstance(previous_recovery, Mapping) and previous_recovery.get("signature") != signature:
                raise LiveTradingSafetyError("Recovered Spot fill conflicts with its prior portfolio proof.")
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
        record["allocations"] = [dict(row) for row in target_entries if isinstance(row, dict)]
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
