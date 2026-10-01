"""Pure proof of a lost original-stop cancel-replace acknowledgement from exact queries."""

from __future__ import annotations

import hashlib
import json
import re
from collections.abc import Mapping
from datetime import datetime
from decimal import Decimal, InvalidOperation

from app.settings.live_safety import LiveTradingSafetyError

from .spot_opo_runtime import validate_spot_opo_cancel_replace_request, validate_spot_opo_request_payload


_PROOF_FIELDS = {
    "version", "request_signature", "pre_order_signature", "pre_order_quantity", "observed_at",
    "exchange_order_list_id", "working_order_id", "pending_order_id", "pending_client_order_id",
    "list_status", "working_status", "working_executed_quantity", "pending_status",
    "pending_original_quantity", "pending_executed_quantity", "order_id", "status",
    "original_quantity", "executed_quantity",
}
_TERMINAL = {"FILLED", "CANCELED", "EXPIRED", "EXPIRED_IN_MATCH"}


def _amount(value: object) -> Decimal:
    try:
        amount = Decimal(str(value))
    except (InvalidOperation, ValueError, TypeError):
        raise LiveTradingSafetyError("Lost linked SELL recovery quantity is invalid.") from None
    if not amount.is_finite() or amount < 0:
        raise LiveTradingSafetyError("Lost linked SELL recovery quantity is invalid.")
    return amount


def _time(value: object) -> bool:
    if not isinstance(value, str):
        return False
    try:
        parsed = datetime.fromisoformat(value)
        return parsed.tzinfo is not None and parsed.timestamp() > 0
    except (ValueError, OverflowError, OSError):
        return False


def validate_spot_opo_exit_query_proof(intent: Mapping[str, object]) -> None:
    """Bind immutable query classification to its request, stop and allocation baseline."""
    source = intent.get("strategy_exit_outcome_source")
    proof = intent.get("strategy_exit_query_proof")
    if source is None and proof is None:
        return  # Legacy response classifications retain their original format.
    if source != "exact_query" or not isinstance(proof, Mapping) or set(proof) != _PROOF_FIELDS:
        raise LiveTradingSafetyError("Linked SELL query classification proof is missing or malformed.")
    request = validate_spot_opo_cancel_replace_request(intent.get("strategy_exit_request"))
    original = validate_spot_opo_request_payload(intent.get("request"))
    signature = hashlib.sha256(json.dumps(request, sort_keys=True, separators=(",", ":")).encode("utf-8")).hexdigest()
    quantity = _amount(request["quantity"])
    executed = _amount(proof["executed_quantity"])
    status = proof["status"]
    current_executed = _amount(intent.get("strategy_exit_executed_qty"))
    if (
        type(proof["version"]) is not int or proof["version"] != 1
        or proof["request_signature"] != signature or signature != intent.get("strategy_exit_request_signature")
        or proof["pre_order_signature"] != intent.get("strategy_exit_pre_order_signature")
        or not isinstance(proof["pre_order_signature"], str)
        or re.fullmatch(r"[0-9a-f]{64}", proof["pre_order_signature"]) is None
        or _amount(proof["pre_order_quantity"]) != quantity or quantity <= 0
        or quantity != _amount(intent.get("entry_portfolio_quantity"))
        or quantity != _amount(intent.get("strategy_exit_pre_order_quantity"))
        or not _time(proof["observed_at"])
        or proof["observed_at"] != intent.get("strategy_exit_response_at")
        or any(type(proof[name]) is not int for name in ("exchange_order_list_id", "working_order_id", "pending_order_id", "order_id"))
        or proof["exchange_order_list_id"] != intent.get("exchange_order_list_id")
        or proof["working_order_id"] != intent.get("working_order_id")
        or proof["pending_order_id"] != intent.get("pending_order_id")
        or proof["pending_order_id"] != request["cancelOrderId"]
        or proof["order_id"] != intent.get("strategy_exit_order_id")
        or proof["order_id"] in {proof["working_order_id"], proof["pending_order_id"]}
        or proof["list_status"] != "ALL_DONE" or intent.get("list_status") != "ALL_DONE"
        or proof["working_status"] != "FILLED" or intent.get("working_status") != "FILLED"
        or _amount(proof["working_executed_quantity"]) != _amount(original["workingQuantity"])
        or proof["pending_status"] != "CANCELED" or intent.get("pending_status") != "CANCELED"
        or _amount(proof["pending_original_quantity"]) != quantity
        or _amount(proof["pending_executed_quantity"]) != 0
        or proof["pending_client_order_id"] != intent.get("pending_observed_client_order_id")
        or intent.get("strategy_exit_outcome") != "exit_sell_accepted"
        or intent.get("strategy_exit_state") not in {"sell_accepted", "completed"}
        or intent.get("strategy_exit_cancel_confirmed") is not True
        or intent.get("strategy_exit_new_order_accepted") is not True
        or intent.get("cancel_state") != "confirmed"
        or status not in _TERMINAL | {"NEW", "PARTIALLY_FILLED"}
        or _amount(proof["original_quantity"]) != quantity or executed > quantity
        or (status == "NEW" and executed != 0)
        or (status == "PARTIALLY_FILLED" and not 0 < executed < quantity)
        or (status == "FILLED" and executed != quantity)
        or (status in _TERMINAL - {"FILLED"} and executed >= quantity)
        or current_executed < executed
        or (status in _TERMINAL and intent.get("strategy_exit_status") != status)
    ):
        raise LiveTradingSafetyError("Linked SELL query classification conflicts with its durable request or exact proof.")


def build_spot_opo_exit_query_proof(
    intent: Mapping[str, object], evidence: Mapping[str, object], *, observed_at: str,
) -> dict[str, object]:
    """Snapshot already validated exact list, child and replacement observations."""
    return {
        "version": 1,
        "request_signature": intent["strategy_exit_request_signature"],
        "pre_order_signature": intent["strategy_exit_pre_order_signature"],
        "pre_order_quantity": intent["strategy_exit_pre_order_quantity"],
        "observed_at": observed_at,
        "exchange_order_list_id": intent["exchange_order_list_id"],
        "working_order_id": intent["working_order_id"], "pending_order_id": intent["pending_order_id"],
        "pending_client_order_id": intent["pending_observed_client_order_id"],
        "list_status": intent["list_status"], "working_status": intent["working_status"],
        "working_executed_quantity": intent["working_executed_qty"],
        "pending_status": intent["pending_status"], "pending_original_quantity": intent["pending_original_qty"],
        "pending_executed_quantity": intent["pending_executed_qty"],
        "order_id": evidence["order_id"], "status": evidence["status"],
        "original_quantity": evidence["original_quantity"], "executed_quantity": evidence["executed_quantity"],
    }
