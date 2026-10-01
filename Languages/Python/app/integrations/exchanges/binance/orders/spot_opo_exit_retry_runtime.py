"""Pure evidence contracts for retrying an original OPO cancellation with no effect."""

from __future__ import annotations

import hashlib
import json
import re
from collections.abc import Mapping
from datetime import datetime
from decimal import Decimal, InvalidOperation

from app.settings.live_safety import LiveTradingSafetyError

from .spot_opo_runtime import validate_spot_opo_cancel_replace_request, validate_spot_opo_request_payload


EXIT_RETRY_HISTORY_LIMIT = 100
_ATTEMPT_FIELDS = {
    "strategy_exit_state", "strategy_exit_client_order_id", "strategy_exit_quantity",
    "strategy_exit_request", "strategy_exit_request_signature", "strategy_exit_pre_order_signature",
    "strategy_exit_pre_order_quantity", "strategy_exit_started_at", "strategy_exit_outcome",
    "strategy_exit_cancel_confirmed", "strategy_exit_new_order_accepted",
    "strategy_exit_requires_exact_reconciliation", "strategy_exit_requires_stop_rearm",
    "strategy_exit_response_at", "strategy_exit_no_effect_proof",
    "cancel_state", "cancel_submitted_at",
}
_OPTIONAL_ATTEMPT_FIELDS = {"strategy_exit_last_error", "strategy_exit_last_observed_at"}


def _signature(request: Mapping[str, object]) -> str:
    encoded = json.dumps(dict(request), sort_keys=True, separators=(",", ":"), ensure_ascii=True)
    return hashlib.sha256(encoded.encode("ascii")).hexdigest()


def _amount(value: object) -> Decimal:
    if isinstance(value, bool):
        raise LiveTradingSafetyError("Linked exit no-effect quantity is invalid.")
    try:
        amount = Decimal(str(value))
    except (InvalidOperation, ValueError):
        raise LiveTradingSafetyError("Linked exit no-effect quantity is invalid.") from None
    if not amount.is_finite() or amount < 0:
        raise LiveTradingSafetyError("Linked exit no-effect quantity is invalid.")
    return amount


def _time(value: object) -> bool:
    if not isinstance(value, str) or not value:
        return False
    try:
        return datetime.fromisoformat(value).utcoffset() is not None
    except ValueError:
        return False


def validate_spot_opo_no_effect_proof(
    intent: Mapping[str, object], proof: object,
) -> dict[str, object]:
    request = validate_spot_opo_request_payload(intent.get("request"))
    exit_request = validate_spot_opo_cancel_replace_request(intent.get("strategy_exit_request"))
    fields = {
        "request_signature", "verified_at", "exchange_order_list_id", "working_order_id", "pending_order_id",
        "list_status", "working_status", "working_executed_qty", "pending_status",
        "pending_executed_qty", "pending_original_qty",
    }
    if not isinstance(proof, Mapping) or set(proof) != fields:
        raise LiveTradingSafetyError("Linked exit retry requires exact no-effect proof.")
    entry_quantity = _amount(intent.get("entry_portfolio_quantity"))
    if (
        proof.get("request_signature") != _signature(exit_request)
        or intent.get("strategy_exit_request_signature") != _signature(exit_request)
        or intent.get("strategy_exit_state") != "no_effect"
        or intent.get("strategy_exit_outcome") != "cancel_failed"
        or intent.get("strategy_exit_cancel_confirmed") is not False
        or intent.get("strategy_exit_new_order_accepted") is not False
        or intent.get("strategy_exit_requires_exact_reconciliation") is not True
        or intent.get("strategy_exit_requires_stop_rearm") is not False
        or intent.get("cancel_state") != "rejected"
        or not _time(proof.get("verified_at"))
        or proof.get("list_status") != "EXEC_STARTED"
        or proof.get("working_status") != "FILLED"
        or proof.get("pending_status") != "NEW"
        or entry_quantity <= 0
        or _amount(proof.get("working_executed_qty")) != Decimal(request["workingQuantity"])
        or _amount(proof.get("pending_original_qty")) != entry_quantity
        or _amount(proof.get("pending_executed_qty")) != 0
        or exit_request["symbol"] != request["symbol"]
        or exit_request["cancelOrderId"] != intent.get("pending_order_id")
        or exit_request["cancelOrigClientOrderId"] != request["pendingClientOrderId"]
        or _amount(exit_request["quantity"]) != entry_quantity
    ):
        raise LiveTradingSafetyError("Linked exit retry no-effect proof conflicts with its exact request or stop.")
    for field, minimum in (("exchange_order_list_id", 0), ("working_order_id", 1), ("pending_order_id", 1)):
        value = proof.get(field)
        if type(value) is not int or value < minimum or value != intent.get(field):
            raise LiveTradingSafetyError("Linked exit retry no-effect proof changed its durable order identity.")
    return dict(proof)


def build_spot_opo_no_effect_proof(
    intent: Mapping[str, object], *, verified_at: str,
) -> dict[str, object]:
    proof = {name: intent.get(name) for name in (
        "exchange_order_list_id", "working_order_id", "pending_order_id", "list_status",
        "working_status", "working_executed_qty", "pending_status", "pending_executed_qty", "pending_original_qty",
    )}
    proof.update(request_signature=intent.get("strategy_exit_request_signature"), verified_at=verified_at)
    return validate_spot_opo_no_effect_proof(intent, proof)


def validate_spot_opo_exit_retry_history(intent: Mapping[str, object]) -> list[dict[str, object]]:
    history = intent.get("strategy_exit_history", [])
    if not isinstance(history, list) or len(history) > EXIT_RETRY_HISTORY_LIMIT:
        raise LiveTradingSafetyError("Linked exit retry history is invalid or exceeds its limit.")
    original = validate_spot_opo_request_payload(intent.get("request"))
    used_ids = {original[name] for name in ("listClientOrderId", "workingClientOrderId", "pendingClientOrderId")}
    current_id = intent.get("strategy_exit_client_order_id")
    if isinstance(current_id, str):
        used_ids.add(current_id)
    current_request = intent.get("strategy_exit_request")
    if isinstance(current_request, Mapping) and isinstance(current_request.get("cancelNewClientOrderId"), str):
        used_ids.add(str(current_request["cancelNewClientOrderId"]))
    normalized = []
    for prior in history:
        if (
            not isinstance(prior, Mapping)
            or not _ATTEMPT_FIELDS <= set(prior)
            or set(prior) - _ATTEMPT_FIELDS - _OPTIONAL_ATTEMPT_FIELDS
        ):
            raise LiveTradingSafetyError("Linked exit retry history contains incomplete or recursive evidence.")
        combined = {**intent, **prior}
        request = validate_spot_opo_cancel_replace_request(prior.get("strategy_exit_request"))
        client_id = request["newClientOrderId"]
        alias = request.get("cancelNewClientOrderId")
        baseline_signature = prior.get("strategy_exit_pre_order_signature")
        if (
            client_id in used_ids
            or (alias is not None and (alias in used_ids or alias != spot_opo_cancel_client_id(str(client_id))))
            or prior.get("strategy_exit_client_order_id") != client_id
            or prior.get("strategy_exit_quantity") != request["quantity"]
            or _amount(prior.get("strategy_exit_pre_order_quantity")) != _amount(request["quantity"])
            or not isinstance(baseline_signature, str)
            or re.fullmatch(r"[0-9a-f]{64}", baseline_signature) is None
            or baseline_signature != intent.get("strategy_exit_pre_order_signature")
            or not _time(prior.get("strategy_exit_started_at"))
            or not _time(prior.get("strategy_exit_response_at"))
            or prior.get("cancel_submitted_at") != prior.get("strategy_exit_started_at")
            or any(
                not isinstance(prior[name], str) or not prior[name]
                for name in _OPTIONAL_ATTEMPT_FIELDS if name in prior
            )
        ):
            raise LiveTradingSafetyError("Linked exit retry history conflicts with its request or unchanged baseline.")
        validate_spot_opo_no_effect_proof(combined, prior.get("strategy_exit_no_effect_proof"))
        used_ids.add(client_id)
        if isinstance(alias, str):
            used_ids.add(alias)
        normalized.append(dict(prior))
    return normalized


def archive_spot_opo_no_effect_attempt(intent: Mapping[str, object]) -> dict[str, object]:
    validate_spot_opo_no_effect_proof(intent, intent.get("strategy_exit_no_effect_proof"))
    prior = {
        name: value for name, value in intent.items()
        if (name.startswith("strategy_exit_") and name != "strategy_exit_history")
        or name in {"cancel_state", "cancel_submitted_at"}
    }
    # Validate the snapshot without inventing a current generation ID.
    candidate = {**intent, "strategy_exit_client_order_id": None, "strategy_exit_request": None,
                 "strategy_exit_history": [prior]}
    validate_spot_opo_exit_retry_history(candidate)
    return prior


def used_spot_client_order_ids(intents: Mapping[str, object]) -> set[str]:
    used: set[str] = set()
    for record in intents.values():
        if not isinstance(record, Mapping) or record.get("market") != "spot":
            continue
        client_id = record.get("client_order_id")
        if isinstance(client_id, str):
            used.add(client_id)
        request = record.get("request")
        if isinstance(request, Mapping):
            used.update(
                value for name in ("listClientOrderId", "workingClientOrderId", "pendingClientOrderId")
                if isinstance((value := request.get(name)), str)
            )
        client_id = record.get("strategy_exit_client_order_id")
        if isinstance(client_id, str):
            used.add(client_id)
        request = record.get("strategy_exit_request")
        if isinstance(request, Mapping) and isinstance(request.get("cancelNewClientOrderId"), str):
            used.add(str(request["cancelNewClientOrderId"]))
        alias = record.get("pending_observed_client_order_id")
        if isinstance(alias, str):
            used.add(alias)
        request = record.get("residual_stop_request")
        if isinstance(request, Mapping) and isinstance(request.get("newClientOrderId"), str):
            used.add(str(request["newClientOrderId"]))
        for history_name in ("strategy_exit_history", "residual_stop_history"):
            history = record.get(history_name, [])
            if not isinstance(history, list) or any(not isinstance(prior, Mapping) for prior in history):
                raise LiveTradingSafetyError("Spot client ID history is malformed.")
            for prior in history:
                if history_name == "strategy_exit_history":
                    client_id = prior.get("strategy_exit_client_order_id")
                    request = prior.get("strategy_exit_request")
                    if isinstance(request, Mapping) and isinstance(request.get("cancelNewClientOrderId"), str):
                        used.add(str(request["cancelNewClientOrderId"]))
                else:
                    request = prior.get("request")
                    client_id = request.get("newClientOrderId") if isinstance(request, Mapping) else None
                if isinstance(client_id, str):
                    used.add(client_id)
    return used


def spot_opo_cancel_client_id(exit_client_id: str) -> str:
    """Return a stable, separately reserved cancellation alias for one new attempt."""
    return "cx" + hashlib.sha256(exit_client_id.encode("utf-8")).hexdigest()[:32]
