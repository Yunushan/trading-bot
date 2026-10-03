"""Conserved acquisition receipts and canonical append-only Spot BUY generations."""
from __future__ import annotations

from collections.abc import Mapping
from copy import deepcopy
from dataclasses import dataclass, field
from datetime import datetime
from decimal import Decimal, InvalidOperation
import hashlib
from pathlib import Path
import re

from app.settings.live_safety import LiveTradingSafetyError


def _amount(value: object, name: str, *, positive: bool = False) -> Decimal:
    if isinstance(value, bool):
        raise LiveTradingSafetyError(f"Spot generation {name} is invalid.")
    try:
        result = Decimal(str(value))
    except (InvalidOperation, ValueError, TypeError):
        raise LiveTradingSafetyError(f"Spot generation {name} is invalid.") from None
    if not result.is_finite() or result < 0 or (positive and result <= 0):
        raise LiveTradingSafetyError(f"Spot generation {name} is invalid.")
    return result


def _identity(value: object, name: str) -> str:
    if not isinstance(value, str) or not value or len(value) > 128 or not value.isascii():
        raise LiveTradingSafetyError(f"Spot generation {name} is invalid.")
    return value


def _text(value: Decimal) -> str:
    return format(value.normalize(), "f")


@dataclass(frozen=True)
class SpotBuyGenerationReceipt:
    symbol: str
    client_order_id: str
    exchange_client_order_id: str
    order_id: int
    signature: str
    acquisition_qty: Decimal
    remaining_qty: Decimal
    terminal: bool


@dataclass(frozen=True)
class SpotBuyAdmissionReceipt:
    allocation_path: Path
    mode: str
    raw: bytes | None = field(repr=False)
    identity: tuple[int, int, int, int] | None
    generation: int
    target_key: tuple[str, str]
    client_order_ids: tuple[str, ...]

    @property
    def snapshot_signature(self) -> str:
        return hashlib.sha256(self.raw or b"").hexdigest()


@dataclass(frozen=True)
class SpotBuyPublicationContext:
    allocation_path: Path
    intent_path: Path
    expected_binding: dict = field(repr=False)
    expected_intent: dict = field(repr=False)
    fill: dict = field(repr=False)
    entry_source_receipt: SpotBuyAdmissionReceipt = field(repr=False)
    expected_store_id: str
    namespace: dict = field(repr=False)


def spot_buy_target(params: Mapping) -> tuple[tuple[str, str], tuple[str, ...]]:
    symbol = params.get("symbol")
    opo = "listClientOrderId" in params
    if (
        not isinstance(symbol, str) or not symbol or not symbol.isascii() or not symbol.isalnum()
        or symbol != symbol.upper()
        or (not opo and params.get("side") != "BUY")
    ):
        raise LiveTradingSafetyError("Spot BUY admission target is invalid.")
    names = ("listClientOrderId", "workingClientOrderId", "pendingClientOrderId") if opo else ("newClientOrderId",)
    identities = tuple(_identity(params.get(name), name) for name in names)
    if len(set(identities)) != len(identities):
        raise LiveTradingSafetyError("Spot BUY admission identities are duplicated.")
    return (symbol, "L"), identities


spot_buy_admission_identity = spot_buy_target


def canonical_spot_buy_metadata(fill: Mapping) -> dict:
    if "version" in fill and (type(fill["version"]) is not int or fill["version"] != 1):
        raise LiveTradingSafetyError("Spot acquisition proof version is invalid.")
    symbol = _identity(fill.get("symbol"), "symbol")
    client = _identity(fill.get("client_order_id"), "client ID")
    exchange_client = _identity(fill.get("exchange_client_order_id", client), "exchange client ID")
    signature = fill.get("signature")
    order_id = fill.get("order_id")
    if (
        not symbol.isalnum() or symbol != symbol.upper()
        or not isinstance(signature, str) or re.fullmatch(r"[0-9a-f]{64}", signature) is None
        or type(order_id) is not int or order_id <= 0
        or type(fill.get("fill_time_ms")) is not int or fill["fill_time_ms"] <= 0
    ):
        raise LiveTradingSafetyError("Spot acquisition proof identity is invalid.")
    qty = _amount(fill.get("net_qty"), "acquisition quantity", positive=True)
    gross = _amount(fill.get("gross_qty"), "gross quantity", positive=True)
    quote = _amount(fill.get("net_quote_cost"), "acquisition cost", positive=True)
    gross_quote = _amount(fill.get("gross_quote_qty"), "gross cost", positive=True)
    trades = fill.get("trade_ids")
    commissions = fill.get("commissions")
    base, quote_asset = fill.get("base_asset"), fill.get("quote_asset")
    if (
        not isinstance(trades, list) or not trades or len(trades) != len(set(trades))
        or any(type(item) is not int or item <= 0 for item in trades)
        or type(fill.get("trade_count")) is not int or fill["trade_count"] != len(trades)
        or not isinstance(commissions, list) or not isinstance(base, str) or not base.isalnum()
        or base != base.upper() or quote_asset != "USDT" or base == quote_asset
    ):
        raise LiveTradingSafetyError("Spot acquisition trade/fee proof is invalid.")
    fees: dict[str, Decimal] = {}
    for commission in commissions:
        if not isinstance(commission, Mapping) or commission.get("asset") not in {base, quote_asset}:
            raise LiveTradingSafetyError("Spot acquisition commission is invalid.")
        asset = str(commission["asset"])
        if asset in fees:
            raise LiveTradingSafetyError("Spot acquisition commission is duplicated.")
        fees[asset] = _amount(commission.get("amount"), "commission")
    if qty != gross - fees.get(base, Decimal(0)) or quote != gross_quote + fees.get(quote_asset, Decimal(0)):
        raise LiveTradingSafetyError("Spot acquisition quantities/cost do not conserve fees.")
    if "average_cost" in fill and _amount(fill["average_cost"], "average cost", positive=True) != quote / qty:
        raise LiveTradingSafetyError("Spot acquisition average cost is invalid.")
    result = {"version": 1, "signature": signature, "exchange_client_order_id": exchange_client,
              "order_id": order_id, "trade_ids": list(trades), "trade_count": len(trades),
              "gross_qty": _text(gross), "net_qty": _text(qty), "gross_quote_qty": _text(gross_quote),
              "net_quote_cost": _text(quote), "commissions": deepcopy(commissions),
              "base_asset": base, "quote_asset": quote_asset, "fill_time_ms": fill["fill_time_ms"]}
    if "pending_order_qty" in fill:
        pending = _amount(fill["pending_order_qty"], "linked stop quantity", positive=True)
        result["pending_order_qty"] = _text(pending)
    return result


def build_spot_buy_allocation_row(fill: Mapping, annotations: Mapping | None = None) -> dict:
    metadata = canonical_spot_buy_metadata(fill)
    qty = _amount(metadata["net_qty"], "acquisition quantity", positive=True)
    cost = _amount(metadata["net_quote_cost"], "acquisition cost", positive=True)
    row = {
        "interval": "RECOVERY", "interval_display": "Recovered Spot fill", "qty": float(qty),
        "entry_price": float(cost / qty), "leverage": 1, "margin_usdt": float(cost),
        "margin_balance": float(cost), "notional": float(cost), "symbol": fill["symbol"], "side_key": "L",
        "open_time": datetime.fromtimestamp(metadata["fill_time_ms"] / 1000).strftime("%Y-%m-%d %H:%M:%S"),
        "status": "Active", "pnl_value": None, "trigger_indicators": [], "trigger_signature": [],
        "trigger_desc": "Recovered exact Binance Spot fill", "trigger_actions": {},
        "order_id": str(metadata["order_id"]), "client_order_id": fill["client_order_id"],
        "trade_id": fill["client_order_id"], "spot_fill_recovery": metadata,
    }
    # Only presentation/strategy annotations may accompany an authoritative acquisition.
    for name in ("interval", "interval_display", "context_key", "slot_id", "event_uid",
                 "trigger_indicators", "trigger_signature", "trigger_desc", "trigger_actions"):
        if annotations is not None and name in annotations:
            row[name] = deepcopy(annotations[name])
    return row


def validate_spot_entry_snapshot(snapshot: Mapping | None, symbol: str, new_ids: tuple[str, ...]) -> None:
    if snapshot is None:
        return
    allocations, records = snapshot.get("entry_allocations"), snapshot.get("open_position_records")
    if snapshot.get("mode") != "Live" or not isinstance(allocations, Mapping) or not isinstance(records, Mapping):
        raise LiveTradingSafetyError("Spot admission requires a valid Live allocation snapshot.")
    rows = allocations.get(f"{symbol}:L", [])
    if not isinstance(rows, list):
        raise LiveTradingSafetyError("Spot admission allocation history is invalid.")
    for values in allocations.values():
        if not isinstance(values, list):
            raise LiveTradingSafetyError("Spot admission allocation list is invalid.")
        for row in values:
            if not isinstance(row, Mapping):
                raise LiveTradingSafetyError("Spot admission allocation row is invalid.")
            proof = row.get("spot_fill_recovery")
            used = {row.get("client_order_id"), row.get("trade_id")}
            if isinstance(proof, Mapping):
                used.add(proof.get("exchange_client_order_id"))
            if any(token in used for token in new_ids):
                raise LiveTradingSafetyError("Spot admission acquisition identity was already used.")
    active = []
    for row in rows:
        if row.get("symbol") != symbol or row.get("side_key") != "L":
            raise LiveTradingSafetyError("Spot admission allocation target conflicts with history.")
        status = str(row.get("status") or "").lower()
        if status not in {"active", "closed"}:
            raise LiveTradingSafetyError("Spot admission allocation status is invalid.")
        if any(name in row for name in ("spot_fill_recovery", "spot_sell_recoveries", "spot_opo_stop_recovery")):
            spot_buy_generation_receipt(row)
        if status == "active":
            active.append(row)
    record = records.get(f"{symbol}:L")
    if not active:
        if record is not None:
            raise LiveTradingSafetyError("Spot admission has a position without current inventory.")
        return
    if not isinstance(record, Mapping) or not isinstance(record.get("data"), Mapping):
        raise LiveTradingSafetyError("Spot admission current position is missing.")
    snapshot_rows = record.get("allocations")
    if not isinstance(snapshot_rows, list) or [row for row in snapshot_rows if str(row.get("status") or "").lower() == "active"] != active:
        raise LiveTradingSafetyError("Spot admission position allocations are incoherent.")
    total = sum((_amount(row.get("qty"), "active quantity", positive=True) for row in active), Decimal(0))
    if _amount(record["data"].get("qty"), "position quantity", positive=True) != Decimal(str(float(total))):
        raise LiveTradingSafetyError("Spot admission position quantity is incoherent.")


def spot_buy_generation_receipt(row: Mapping) -> SpotBuyGenerationReceipt:
    proof = row.get("spot_fill_recovery")
    if not isinstance(proof, Mapping) or ("version" in proof and (type(proof["version"]) is not int or proof["version"] != 1)):
        raise LiveTradingSafetyError("Spot generation has no immutable acquisition proof.")
    if any(name in proof and proof[name] != row.get(name) for name in ("symbol", "client_order_id")):
        raise LiveTradingSafetyError("Spot generation acquisition identity conflicts with its row.")
    fill = {**proof, "symbol": row.get("symbol"), "client_order_id": row.get("client_order_id")}
    metadata = canonical_spot_buy_metadata(fill)
    qty = _amount(metadata["net_qty"], "acquisition quantity", positive=True)
    if (
        row.get("side_key") != "L" or str(row.get("order_id")) != str(metadata["order_id"])
        or _amount(row.get("entry_price"), "acquisition price", positive=True)
        != Decimal(str(float(_amount(metadata["net_quote_cost"], "acquisition cost") / qty)))
    ):
        raise LiveTradingSafetyError("Spot generation row identity conflicts with its acquisition.")
    consumed = Decimal(0)
    sell_proofs = row.get("spot_sell_recoveries", [])
    if sell_proofs:
        # Reuse the existing authoritative SELL schema and arithmetic validator.
        from .spot_fill_recovery_runtime import _existing_sell_recovery_proofs
        _existing_sell_recovery_proofs({"owned:L": [dict(row)]}, signature="0" * 64)
        seen_orders, seen_clients = set(), set()
        previous_time = metadata["fill_time_ms"]
        for sell in sell_proofs:
            if sell["fill_time_ms"] < previous_time or sell["order_id"] in seen_orders or sell["client_order_id"] in seen_clients:
                raise LiveTradingSafetyError("Spot consumption order history is invalid.")
            previous_time = sell["fill_time_ms"]
            seen_orders.add(sell["order_id"])
            seen_clients.add(sell["client_order_id"])
            amount = _amount(sell["consumed_qty"], "consumed quantity", positive=True)
            if (
                amount > qty - consumed
                or _amount(sell["pre_order_portfolio_qty"], "consumption baseline", positive=True) < qty - consumed
                or _amount(sell["cost_basis"], "consumption cost", positive=True)
                != amount * _amount(row["entry_price"], "acquisition price", positive=True)
            ):
                raise LiveTradingSafetyError("Spot consumption chain does not conserve acquisition.")
            consumed += amount
    elif not isinstance(sell_proofs, list):
        raise LiveTradingSafetyError("Spot consumption history is malformed.")
    stop = row.get("spot_opo_stop_recovery")
    if stop is not None:
        stop_trades = stop.get("trade_ids") if isinstance(stop, Mapping) else None
        if (
            sell_proofs or not isinstance(stop, Mapping) or type(stop.get("version")) is not int or stop.get("version") != 1
            or stop.get("entry_recovery_signature") != metadata["signature"]
            or stop.get("client_order_id") != row.get("client_order_id")
            or not isinstance(stop.get("signature"), str) or re.fullmatch(r"[0-9a-f]{64}", stop["signature"]) is None
            or type(stop.get("fill_time_ms")) is not int or stop["fill_time_ms"] < metadata["fill_time_ms"]
            or not isinstance(stop.get("pending_client_order_id"), str) or not stop["pending_client_order_id"]
            or type(stop.get("order_list_id")) is not int or stop["order_list_id"] <= 0
            or type(stop.get("order_id")) is not int or stop["order_id"] <= 0
            or not isinstance(stop_trades, list) or not stop_trades
            or any(type(item) is not int or item <= 0 for item in stop_trades)
            or len(set(stop_trades)) != len(stop_trades)
            or _amount(stop.get("entry_quantity"), "stop acquisition quantity", positive=True) != qty
            or _amount(stop.get("gross_qty"), "stop gross quantity", positive=True)
            + _amount(stop.get("base_fee_qty"), "stop base fee")
            != _amount(stop.get("consumed_qty"), "stop consumed quantity", positive=True)
            or _amount(stop.get("gross_quote_qty"), "stop gross proceeds", positive=True)
            - _amount(stop.get("quote_fee_qty"), "stop quote fee")
            != _amount(stop.get("net_quote_proceeds"), "stop proceeds", positive=True)
        ):
            raise LiveTradingSafetyError("Spot stop consumption proof is invalid.")
        consumed = _amount(stop["consumed_qty"], "stop consumed quantity", positive=True)
    remaining = qty - consumed
    terminal = str(row.get("status") or "").lower() == "closed"
    if remaining < 0 or (terminal and remaining != 0) or (not terminal and (
        str(row.get("status") or "").lower() != "active" or remaining <= 0
        or _amount(row.get("qty"), "current remainder", positive=True) != Decimal(str(float(remaining)))
    )):
        raise LiveTradingSafetyError("Spot generation status/remainder does not conserve acquisition.")
    return SpotBuyGenerationReceipt(str(row["symbol"]), str(row["client_order_id"]),
                                    str(metadata["exchange_client_order_id"]), int(metadata["order_id"]),
                                    str(metadata["signature"]), qty, remaining, terminal)


def validate_spot_buy_replay(row: Mapping, fill: Mapping) -> SpotBuyGenerationReceipt:
    receipt = spot_buy_generation_receipt(row)
    expected = canonical_spot_buy_metadata(fill)
    previous = canonical_spot_buy_metadata({**row["spot_fill_recovery"],
                                            "symbol": row.get("symbol"), "client_order_id": row.get("client_order_id")})
    if receipt.client_order_id != fill.get("client_order_id") or receipt.symbol != fill.get("symbol") or previous != expected:
        raise LiveTradingSafetyError("Spot BUY replay conflicts with its immutable acquisition proof.")
    return receipt


def validate_spot_buy_publication(context: SpotBuyPublicationContext, observed_intent: Mapping) -> None:
    from .spot_inventory_namespace import validate_namespace
    namespace = validate_namespace(context.namespace)
    if namespace["store_id"] != context.expected_store_id:
        raise LiveTradingSafetyError("Spot BUY publication inventory store changed.")
    fill, intent = context.fill, context.expected_intent
    metadata = canonical_spot_buy_metadata(fill)
    if observed_intent != intent or intent.get("state") != "accepted" or intent.get("market") != "spot" or intent.get("side") != "BUY":
        raise LiveTradingSafetyError("Spot BUY publication has no unchanged accepted intent.")
    if intent.get("symbol") != fill.get("symbol") or intent.get("client_order_id") != fill.get("client_order_id"):
        raise LiveTradingSafetyError("Spot BUY publication intent identity conflicts with acquisition.")
    if intent.get("type") == "OPO":
        raise LiveTradingSafetyError("Desktop OPO publication requires dedicated exact trade recovery.")
    elif (
        intent.get("type") != "MARKET" or intent.get("exchange_status") != "FILLED"
        or str(intent.get("exchange_order_id")) != str(metadata["order_id"])
        or metadata["exchange_client_order_id"] != intent.get("client_order_id")
        or intent.get("primary_fill_signature") != metadata["signature"]
        or _amount(intent.get("portfolio_qty"), "accepted net quantity", positive=True) != _amount(metadata["net_qty"], "net acquisition", positive=True)
        or intent.get("primary_fill_receipt") != metadata
        or _amount(intent.get("executed_qty"), "executed quantity", positive=True) != _amount(metadata["gross_qty"], "gross acquisition", positive=True)
    ):
        raise LiveTradingSafetyError("Spot primary acquisition does not match its accepted fill.")
