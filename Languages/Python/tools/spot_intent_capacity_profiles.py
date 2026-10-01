"""Canonical disposable OPO histories and an in-memory, GET-only venue boundary."""
from __future__ import annotations

import copy
import hashlib
import json
from collections.abc import Mapping
from typing import Any

from app.integrations.exchanges.binance.orders import order_intent_runtime as runtime
from app.integrations.exchanges.binance.orders.spot_opo_exit_retry_runtime import (
    archive_spot_opo_no_effect_attempt,
    build_spot_opo_no_effect_proof,
    spot_opo_cancel_client_id,
    used_spot_client_order_ids,
)
from app.integrations.exchanges.binance.orders.spot_opo_runtime import (
    validate_spot_opo_cancel_replace_request,
    validate_spot_opo_request_payload,
    validate_spot_opo_residual_stop_request,
)

FIXED_TIME = "2026-01-01T00:00:00+00:00"
MAX_RECORDS = 100_000
MAX_ACTIVE_STOPS = 128
MAX_HISTORY_ENTRIES = 350_000
SYMBOLS = ("BTCUSDT", "ETHUSDT", "SOLUSDT", "ADAUSDT")


def validate_opo_counts(count: int, original_stops: int, residual_stops: int,
                        attempt_depth: int, residual_depth: int) -> None:
    values = (count, original_stops, residual_stops, attempt_depth, residual_depth)
    if (any(type(value) is not int for value in values)
            or not 1 <= count <= MAX_RECORDS
            or min(original_stops, residual_stops, attempt_depth, residual_depth) < 0
            or not 1 <= original_stops + residual_stops <= min(count, MAX_ACTIVE_STOPS)
            or max(attempt_depth, residual_depth) > 100
            or count * attempt_depth + residual_stops * residual_depth > MAX_HISTORY_ENTRIES):
        raise ValueError("OPO workload exceeds bounded records, active stops or history entries.")


def request_for(index: int) -> dict[str, str]:
    return dict(validate_spot_opo_request_payload({
        "symbol": SYMBOLS[index % len(SYMBOLS)], "listClientOrderId": f"syn-list-{index:08d}",
        "workingClientOrderId": f"syn-buy-{index:08d}", "pendingClientOrderId": f"syn-stop-{index:08d}",
        "workingType": "LIMIT", "workingSide": "BUY", "workingPrice": "100.00",
        "workingQuantity": "0.1000", "workingTimeInForce": "FOK", "pendingType": "STOP_LOSS",
        "pendingSide": "SELL", "pendingStopPrice": "95.00", "newOrderRespType": "FULL",
    }))


def _exit_attempt(record: dict[str, Any], index: int, generation: int) -> dict[str, Any]:
    request = record["request"]
    exit_id = f"syn-exit-{index:08d}-{generation:03d}"
    exit_request = validate_spot_opo_cancel_replace_request({
        "symbol": request["symbol"], "side": "SELL", "type": "MARKET",
        "cancelReplaceMode": "STOP_ON_FAILURE", "cancelOrderId": record["pending_order_id"],
        "cancelOrigClientOrderId": request["pendingClientOrderId"], "cancelRestrictions": "ONLY_NEW",
        "cancelNewClientOrderId": spot_opo_cancel_client_id(exit_id),
        "quantity": "0.0999", "newClientOrderId": exit_id,
        "newOrderRespType": "FULL",
    })
    result = {
        **record, "strategy_exit_state": "no_effect", "cancel_state": "rejected",
        "cancel_submitted_at": FIXED_TIME, "strategy_exit_started_at": FIXED_TIME,
        "strategy_exit_response_at": FIXED_TIME, "strategy_exit_request": exit_request,
        "strategy_exit_request_signature": runtime._request_signature(exit_request),
        "strategy_exit_client_order_id": exit_request["newClientOrderId"],
        "strategy_exit_quantity": "0.0999", "strategy_exit_pre_order_quantity": "0.0999",
        "strategy_exit_pre_order_signature": hashlib.sha256(f"baseline-{index}".encode()).hexdigest(),
        "strategy_exit_outcome": "cancel_failed", "strategy_exit_cancel_confirmed": False,
        "strategy_exit_new_order_accepted": False, "strategy_exit_requires_exact_reconciliation": True,
        "strategy_exit_requires_stop_rearm": False,
    }
    result["strategy_exit_no_effect_proof"] = build_spot_opo_no_effect_proof(result, verified_at=FIXED_TIME)
    return result


def _active_original(index: int, attempt_depth: int) -> dict[str, Any]:
    request = request_for(index)
    list_id = 10_000 + index * 4
    record = {
        "client_order_id": request["listClientOrderId"], "market": "spot", "symbol": request["symbol"],
        "source": "synthetic-capacity-benchmark", "side": "BUY", "type": "OPO", "quantity": "0.1000",
        "state": "accepted", "created_at": FIXED_TIME, "updated_at": FIXED_TIME, "request": request,
        "entry_reconciled": True, "protection_state": "active", "exchange_order_list_id": list_id,
        "list_status": "EXEC_STARTED", "working_order_id": list_id + 1, "pending_order_id": list_id + 2,
        "working_status": "FILLED", "pending_status": "NEW", "working_executed_qty": "0.1000",
        "pending_executed_qty": "0", "pending_original_qty": "0.0999",
        "entry_portfolio_quantity": "0.0999", "entry_recovery_signature": "a" * 64,
    }
    if attempt_depth:
        current = _exit_attempt(record, index, attempt_depth)
        current["strategy_exit_history"] = [
            archive_spot_opo_no_effect_attempt(_exit_attempt(record, index, generation))
            for generation in range(attempt_depth)
        ]
        return current
    return record


def _active_residual(index: int, attempt_depth: int, residual_depth: int) -> dict[str, Any]:
    record = _active_original(index, attempt_depth)
    record = _exit_attempt(record, index, attempt_depth)
    record.pop("strategy_exit_no_effect_proof")
    record.update({
        "protection_state": "cancelled", "list_status": "ALL_DONE", "pending_status": "CANCELED",
        "pending_observed_client_order_id": record["strategy_exit_request"]["cancelNewClientOrderId"],
        "cancel_state": "confirmed", "cancel_confirmed_at": FIXED_TIME,
        "strategy_exit_state": "stop_cancelled", "strategy_exit_outcome": "stop_canceled_exit_rejected",
        "strategy_exit_cancel_confirmed": True, "strategy_exit_requires_stop_rearm": True,
        "residual_rearm_quantity": "0.0999", "residual_rearm_signature": "b" * 64,
        "residual_rearm_no_fill": True, "strategy_exit_fill_signature": "c" * 64,
        "strategy_exit_fill_quantity": "0", "strategy_exit_fill_trade_ids": [],
        "strategy_exit_fill_time_ms": 1_767_225_600_000,
    })
    def residual_request(generation: int) -> dict[str, str]:
        return dict(validate_spot_opo_residual_stop_request({
            "symbol": record["symbol"], "side": "SELL", "type": "STOP_LOSS", "quantity": "0.0999",
            "stopPrice": "95.00", "newClientOrderId": f"syn-rearm-{index:08d}-{generation:03d}",
            "newOrderRespType": "FULL",
        }))
    request = residual_request(residual_depth)
    record.update({
        "residual_stop_state": "active", "residual_stop_request": request,
        "residual_stop_request_signature": runtime._request_signature(request),
        "residual_stop_pre_order_quantity": "0.0999", "residual_stop_pre_order_signature": "b" * 64,
        "residual_stop_started_at": FIXED_TIME, "residual_stop_order_id": 1_000_000 + index * 101 + residual_depth,
        "residual_stop_status": "NEW", "residual_stop_executed_qty": "0",
        "residual_stop_observed_at": FIXED_TIME, "residual_stop_query_verified": True,
        "residual_stop_history": [{
            "request": (prior := residual_request(generation)), "request_signature": runtime._request_signature(prior),
            "pre_order_signature": "b" * 64, "pre_order_quantity": "0.0999", "started_at": FIXED_TIME,
            "state": "recovered", "order_id": 1_000_000 + index * 101 + generation, "status": "CANCELED",
            "executed_qty": "0", "observed_at": FIXED_TIME, "recovery_signature": "b" * 64,
            "recovery_quantity": "0", "trade_ids": [],
        } for generation in range(residual_depth)],
    })
    return record


def synthetic_opo_records(count: int, *, original_stops: int, residual_stops: int,
                          attempt_depth: int, residual_depth: int) -> tuple[dict[str, Any], dict[str, Any]]:
    validate_opo_counts(count, original_stops, residual_stops, attempt_depth, residual_depth)
    records = {}
    active_count = original_stops + residual_stops
    for index in range(count):
        record = _active_original(index, attempt_depth)
        if index < original_stops:
            pass
        elif index < active_count:
            record = _active_residual(index, attempt_depth, residual_depth)
        elif index % 5 == 0:
            record = _active_original(index, 0)
            record.update(state="rejected", entry_reconciled=False, protection_state="none", list_status="ALL_DONE",
                          working_status="EXPIRED", pending_status="CANCELED", working_executed_qty="0",
                          pending_original_qty="0")
            for field in ("entry_portfolio_quantity", "entry_recovery_signature"):
                record.pop(field)
        else:
            record.update(protection_state="triggered", list_status="ALL_DONE", pending_status="FILLED",
                          pending_executed_qty="0.0999", exit_reconciled=True, exit_portfolio_quantity="0.0999",
                          exit_recovery_signature="d" * 64, exit_order_id=record["pending_order_id"])
        records[record["client_order_id"]] = record
    metadata = {
        "opo_record_count": count, "active_original_stop_count": original_stops,
        "active_residual_stop_count": residual_stops, "active_stop_count": active_count,
        "terminal_recovered_stop_count": sum(record.get("exit_reconciled") is True for record in records.values()),
        "terminal_no_fill_count": sum(record["state"] == "rejected" for record in records.values()),
        "attempt_history_depth": attempt_depth, "residual_history_depth": residual_depth,
        "archived_exit_attempt_count": sum(len(record.get("strategy_exit_history", [])) for record in records.values()),
        "archived_residual_stop_count": sum(len(record.get("residual_stop_history", [])) for record in records.values()),
        "current_cancel_alias_count": sum("strategy_exit_request" in record for record in records.values()),
        "archived_cancel_alias_count": sum(len(record.get("strategy_exit_history", [])) for record in records.values()),
        "globally_used_client_id_count": len(used_spot_client_order_ids(records)),
        "symbols": sorted({record["symbol"] for record in records.values()}),
        "expected_gets_per_refresh": {"get_order_list": original_stops, "get_order": 2 * original_stops + residual_stops},
    }
    return records, metadata


def immutable_history_digest(intents: Mapping[str, Any], *, mutable_client_ids: set[str]) -> str:
    """Keep all history/identity/quantities; omit only the measured observation clocks."""
    digest = hashlib.sha256()
    mutable_fields = {"updated_at", "last_reconciliation_at", "residual_stop_observed_at"}
    for client_id, record in sorted(intents.items()):
        stable = dict(record)
        if client_id in mutable_client_ids:
            for field in mutable_fields:
                stable.pop(field, None)
            if "strategy_exit_no_effect_proof" in stable:
                proof = dict(stable["strategy_exit_no_effect_proof"])
                proof.pop("verified_at", None)
                stable["strategy_exit_no_effect_proof"] = proof
        digest.update(json.dumps([client_id, stable], sort_keys=True, separators=(",", ":"), allow_nan=False).encode())
        digest.update(b"\n")
    return digest.hexdigest()


class SyntheticOpoVenue:
    """Exact immutable GET replies; no API secret, HTTP client or order operation."""
    def __init__(self, records: Mapping[str, Any]):
        self.calls = {"get_order_list": 0, "get_order": 0}
        self.lists: dict[str, Any] = {}
        self.orders: dict[str, Any] = {}
        for record in runtime._active_spot_protection_records(records).values():
            request = record["request"]
            if record.get("residual_stop_state") == "active":
                residual = record["residual_stop_request"]
                self.orders[residual["newClientOrderId"]] = {
                    "symbol": record["symbol"], "clientOrderId": residual["newClientOrderId"], "side": "SELL",
                    "type": "STOP_LOSS", "orderListId": -1, "orderId": record["residual_stop_order_id"],
                    "status": "NEW", "origQty": residual["quantity"], "executedQty": "0", "stopPrice": residual["stopPrice"],
                }
                continue
            self.lists[record["client_order_id"]] = {
                "symbol": record["symbol"], "orderListId": record["exchange_order_list_id"], "contingencyType": "OTO",
                "listStatusType": "EXEC_STARTED", "listOrderStatus": "EXECUTING", "listClientOrderId": record["client_order_id"],
                "orders": [{"symbol": record["symbol"], "orderId": record[f"{prefix}_order_id"],
                            "clientOrderId": request[f"{prefix}ClientOrderId"]} for prefix in ("working", "pending")],
            }
            for prefix, order_type, side in (("working", "LIMIT", "BUY"), ("pending", "STOP_LOSS", "SELL")):
                client_id = request[f"{prefix}ClientOrderId"]
                self.orders[client_id] = {
                    "symbol": record["symbol"], "orderId": record[f"{prefix}_order_id"],
                    "orderListId": record["exchange_order_list_id"], "clientOrderId": client_id,
                    "type": order_type, "side": side, "status": record[f"{prefix}_status"],
                    "origQty": request["workingQuantity"] if prefix == "working" else record["pending_original_qty"],
                    "executedQty": record[f"{prefix}_executed_qty"], "timeInForce": "FOK",
                    "stopPrice": request["pendingStopPrice"],
                }

    def get_order_list(self, *, origClientOrderId: str) -> dict[str, Any]:
        self.calls["get_order_list"] += 1
        return copy.deepcopy(self.lists[origClientOrderId])

    def get_order(self, *, symbol: str, origClientOrderId: str) -> dict[str, Any]:
        self.calls["get_order"] += 1
        response = self.orders[origClientOrderId]
        if response["symbol"] != symbol:
            raise AssertionError("Synthetic query changed its exact symbol.")
        return copy.deepcopy(response)
