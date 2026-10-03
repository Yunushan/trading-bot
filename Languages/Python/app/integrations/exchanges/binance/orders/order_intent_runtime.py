"""Durable, local order-intent ledger for restart-safe exchange submissions."""

from __future__ import annotations

import hashlib
import json
import re
from collections.abc import Mapping
from contextlib import contextmanager
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import cast
from uuid import UUID

from app.settings.live_safety import LiveTradingSafetyError, is_live_trading_mode
from app.settings.execution_mode import execution_environment
from app.security.redaction import redact_text
from trading_core.orders import is_exchange_risk_reducing_order, order_execution_from_response

from .order_intent_store import ledger_transaction, ledger_transactions, write_ledger
from .spot_execution_owner import SpotExecutionOwner, claim_execution_owner
from .spot_buy_publication_runtime import (
    capture_desktop_entry, desktop_entry_for_submission, desktop_entry_transaction,
    desktop_source_descriptor, remember_desktop_entry, validate_desktop_source_descriptor, assert_desktop_entry_ledger,
    _capture_spot_buy_publication, _get_spot_buy_submission_origin,
)
from .spot_opo_runtime import (
    build_spot_opo_cancel_replace_request,
    validate_spot_opo_cancel_replace_request,
    validate_spot_opo_cancel_replace_response,
    validate_spot_opo_request_payload,
    validate_spot_opo_acknowledgement,
    validate_spot_opo_residual_stop_order,
    validate_spot_opo_residual_stop_request,
    validate_spot_opo_strategy_exit_order,
)
from .spot_exchange_errors import SPOT_EXCHANGE_ERRORS, SPOT_LOCAL_STATE_ERRORS
from .spot_opo_exit_retry_runtime import (
    EXIT_RETRY_HISTORY_LIMIT,
    archive_spot_opo_no_effect_attempt,
    build_spot_opo_no_effect_proof,
    spot_opo_cancel_client_id,
    used_spot_client_order_ids,
    validate_spot_opo_exit_retry_history,
    validate_spot_opo_no_effect_proof,
)
from .spot_opo_exit_recovery_runtime import build_spot_opo_exit_query_proof, validate_spot_opo_exit_query_proof


_INTENT_FORMAT_VERSION = 2
_BLOCKING_STATES = {"pending", "submitted", "unknown", "accepted"}
_UNRESOLVED_STATES = {"pending", "submitted", "unknown"}
_ORDER_STATUSES = {"NEW", "PARTIALLY_FILLED", "FILLED", "CANCELED", "REJECTED", "EXPIRED", "EXPIRED_IN_MATCH"}
_SPOT_PENDING_STATUSES = {"PENDING_NEW", "PENDING_CANCEL"}
_OPO_CANCEL_STATES = {"submitted", "unknown", "confirmed", "rejected"}
_OPO_STRATEGY_EXIT_STATES = {
    "submitted", "unknown", "cancel_failed", "stop_cancelled", "sell_accepted", "no_effect", "completed",
}
_OPO_RESIDUAL_STOP_STATES = {"rearm_required", "submitted", "unknown", "acknowledged", "active", "triggered", "completed"}


def _requires_execution_confirmation(record: Mapping[str, object]) -> bool:
    return bool(record.get("requires_close_confirmation")) or (
        record.get("market") in {"spot", "futures"} and record.get("type") == "MARKET"
    )


def _is_unresolved(record: Mapping[str, object]) -> bool:
    if record.get("state") in _UNRESOLVED_STATES:
        return True
    if record.get("market") == "spot" and record.get("type") == "OPO":
        if record.get("state") == "rejected" and record.get("protection_state") == "none":
            return False
        if record.get("strategy_exit_state") == "completed":
            return False
        if record.get("residual_stop_state") == "completed":
            return False
        if record.get("residual_stop_state") == "active":
            try:
                request = validate_spot_opo_residual_stop_request(record.get("residual_stop_request"))
                residual_order_id = record.get("residual_stop_order_id")
                return not (
                    record.get("state") == "accepted"
                    and record.get("cancel_state") == "confirmed"
                    and record.get("protection_state") == "cancelled"
                    and record.get("residual_stop_status") == "NEW"
                    and record.get("residual_stop_query_verified") is True
                    and Decimal(str(record.get("residual_stop_executed_qty"))) == 0
                    and type(residual_order_id) is int
                    and residual_order_id > 0
                    and record.get("residual_stop_request_signature") == _request_signature(request)
                )
            except (LiveTradingSafetyError, InvalidOperation, TypeError):
                return True
        if record.get("strategy_exit_state") not in (None, "no_effect"):
            return True
        if record.get("state") == "accepted" and record.get("protection_state") == "triggered":
            return record.get("entry_reconciled") is not True or record.get("exit_reconciled") is not True
        if record.get("cancel_state") in {"submitted", "unknown"}:
            return True
        if record.get("state") == "accepted" and record.get("protection_state") == "active":
            return record.get("entry_reconciled") is not True
        return True
    if (
        record.get("state") == "accepted"
        and record.get("market") == "spot"
        and record.get("type") == "MARKET"
    ):
        try:
            executed = Decimal(str(record.get("executed_qty") or "0"))
        except (InvalidOperation, ValueError):
            return True
        if not executed.is_finite() or executed < 0:
            return True
        if executed > 0 and record.get("portfolio_reconciled") is not True:
            return True
    if record.get("state") == "accepted" and _requires_execution_confirmation(record):
        # Older ledgers accepted market ACKs without recording execution proof.
        try:
            execution = order_execution_from_response(
                {"status": record.get("exchange_status"), "executedQty": record.get("executed_qty")},
                record.get("quantity"),
            )
        except (TypeError, ValueError):
            return True
        return execution.status in {"NEW", "PARTIALLY_FILLED"}
    return False


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _request_signature(request: Mapping[str, object]) -> str:
    serialized = json.dumps(dict(request), sort_keys=True, separators=(",", ":"), ensure_ascii=True)
    return hashlib.sha256(serialized.encode("ascii")).hexdigest()


def _decimal_text(value: Decimal) -> str:
    rendered = format(value, "f")
    if "." in rendered:
        rendered = rendered.rstrip("0").rstrip(".")
    return rendered or "0"


def _legacy_intent_path(self) -> Path:
    audit_path = getattr(self, "_order_audit_log_path", None)
    if audit_path:
        path = Path(audit_path).expanduser()
        path = path.with_name(f"{path.stem}.intents.json")
    else:
        path = Path.home() / ".trading-bot" / "order_intents.json"
    path = path.parent.resolve() / path.name
    if path.is_symlink():
        raise LiveTradingSafetyError("Order intent ledger must not be a symbolic link; submission is blocked.")
    return path


def _spot_owner_scope(self) -> bool:
    return bool(getattr(self, "_enforce_spot_execution_owner", False)) and is_live_trading_mode(
        getattr(self, "mode", None)
    ) and str(
        getattr(self, "account_type", "") or ""
    ).strip().upper() == "SPOT"


def _resolve_spot_account_uid(self) -> int:
    """Use a fresh signed Spot account response once per immutable wrapper context."""
    initial = getattr(self, "_spot_owner_initial_context", None)
    if initial is not None and (
        initial[:4] != (
            getattr(self, "api_key", None), getattr(self, "api_secret", None),
            getattr(self, "mode", None), getattr(self, "account_type", None),
        ) or initial[4] is not getattr(self, "client", None)
    ):
        raise LiveTradingSafetyError("Spot execution wrapper context changed after construction.")
    if getattr(self, "_spot_execution_revoked", False):
        raise LiveTradingSafetyError("Spot execution owner was revoked after an account configuration change.")
    if str(getattr(self, "account_type", "") or "").strip().upper() != "SPOT":
        raise LiveTradingSafetyError("Spot execution owner account type changed after wrapper construction.")
    key = getattr(self, "api_key", None)
    secret = getattr(self, "api_secret", None)
    client = getattr(self, "client", None)
    if not isinstance(key, str) or not key.strip() or not isinstance(secret, str) or not secret.strip():
        raise LiveTradingSafetyError("Spot execution owner requires signed account credentials.")
    environment = execution_environment(getattr(self, "mode", None))
    context = getattr(self, "_verified_spot_account_context", None)
    if context is not None:
        if context[:3] != (key, secret, environment) or context[3] is not client:
            raise LiveTradingSafetyError("Spot execution credentials or client changed after account verification.")
        uid_value = context[4]
        if type(uid_value) is not int or uid_value <= 0:
            raise LiveTradingSafetyError("Cached Spot account UID is invalid.")
        return cast(int, uid_value)
    request = getattr(self, "_http_signed_spot", None)
    if not callable(request):
        raise LiveTradingSafetyError("Signed Spot account identity endpoint is unavailable.")
    try:
        response = request("/v3/account")
    except Exception as exc:
        raise LiveTradingSafetyError(f"Spot account identity could not be verified: {redact_text(exc)}") from exc
    uid = response.get("uid") if isinstance(response, Mapping) else None
    if type(uid) is not int or uid <= 0 or response.get("accountType") != "SPOT":
        raise LiveTradingSafetyError("Signed Spot account identity is missing or invalid.")
    self._verified_spot_account_context = (key, secret, environment, client, uid)
    return uid


def _spot_account_uid(self) -> int:
    resolver = getattr(self, "_resolve_spot_account_uid", None)
    if callable(resolver):
        uid_value = resolver()
        if type(uid_value) is not int or uid_value <= 0:
            raise LiveTradingSafetyError("Signed Spot account UID is invalid.")
        return cast(int, uid_value)
    # The offline administration command supplies an expected UID to choose
    # the storage path. The trading wrapper always takes the signed branch.
    uid = getattr(self, "_operator_spot_account_uid", None)
    if type(uid) is not int or uid <= 0:
        raise LiveTradingSafetyError("Spot account UID is required for offline storage administration.")
    return uid


def _intent_path(self) -> Path:
    if not _spot_owner_scope(self):
        return _legacy_intent_path(self)
    environment = execution_environment(getattr(self, "mode", None))
    uid = _spot_account_uid(self)
    home = Path.home().resolve()
    path = home
    for component in (".trading-bot", "account-state", "binance", "spot", environment, f"uid-{uid}"):
        path = path / component
        if path.is_symlink() or (path.exists() and not path.is_dir()):
            raise LiveTradingSafetyError("Spot account state root is not a local directory; submission is blocked.")
    path = path / "order_intents.json"
    if path.is_symlink():
        raise LiveTradingSafetyError("Order intent ledger must not be a symbolic link; submission is blocked.")
    return path


def _intent_binding(self) -> dict[str, str]:
    key = getattr(self, "api_key", None)
    if not isinstance(key, str) or not key.strip():
        raise LiveTradingSafetyError("Order intent storage requires a credential identity.")
    try:
        environment = execution_environment(getattr(self, "mode", None))
    except ValueError as exc:
        raise LiveTradingSafetyError("Order intent storage requires a known execution environment.") from exc
    return {
        "exchange": "binance",
        "environment": environment,
        "credential_fingerprint": hashlib.sha256(b"binance-order-intents-v1\0" + key.strip().encode()).hexdigest(),
    }


def _ensure_spot_execution_owner(self) -> SpotExecutionOwner:
    if not _spot_owner_scope(self):
        raise LiveTradingSafetyError("Spot execution owner requires a Spot trading wrapper.")
    uid = _spot_account_uid(self)
    path = _intent_path(self)
    binding = _intent_binding(self)
    with ledger_transaction(path):
        ledger = _read_ledger(path, expected_binding=binding)
    owner = claim_execution_owner(
        path, uid=uid, environment=binding["environment"],
        store_id=str(ledger["store_id"]), credential_fingerprint=binding["credential_fingerprint"],
        owner_wrapper=self,
    )
    self._spot_execution_owner = owner
    return owner


@contextmanager
def _spot_execution_submission(self):
    if not _spot_owner_scope(self):
        raise LiveTradingSafetyError("Spot execution owner scope changed before order submission.")
    owner = getattr(self, "_spot_execution_owner", None)
    if not isinstance(owner, SpotExecutionOwner):
        raise LiveTradingSafetyError("Spot execution owner was not acquired before order submission.")
    uid = _spot_account_uid(self)
    binding = _intent_binding(self)
    with owner.submission(
        uid=uid, environment=binding["environment"],
        credential_fingerprint=binding["credential_fingerprint"],
        owner_wrapper=self,
    ):
        yield


def _revoke_spot_execution_owner(self) -> None:
    self._spot_execution_revoked = True
    owner = getattr(self, "_spot_execution_owner", None)
    if isinstance(owner, SpotExecutionOwner):
        owner.close()


def _read_ledger(
    path: Path, *, expected_binding: Mapping[str, str] | None = None, allow_legacy: bool = False,
) -> dict[str, object]:
    def unique_object(pairs):
        result = {}
        for key, value in pairs:
            if key in result:
                raise ValueError("Duplicate ledger field")
            result[key] = value
        return result

    try:
        payload = json.loads(path.read_text(encoding="utf-8"), object_pairs_hook=unique_object)
    except FileNotFoundError as exc:
        raise LiveTradingSafetyError(
            "Order intent ledger is missing; submission is blocked. Restore and reconcile existing history, "
            "or explicitly provision a first-use store with trading-bot-order-store."
        ) from exc
    except Exception as exc:
        raise LiveTradingSafetyError(f"Order intent ledger cannot be read: {redact_text(exc)}") from exc
    return validate_order_intent_ledger(payload, expected_binding=expected_binding, allow_legacy=allow_legacy)


def validate_order_intent_ledger(
    payload: object, *, expected_binding: Mapping[str, str] | None = None, allow_legacy: bool = False,
) -> dict[str, object]:
    """Validate a complete decoded ledger without filesystem or venue access.

    Supply every record: current and archived cancellation-ID ownership is a
    cross-record invariant and cannot be established from an isolated row.
    """
    if (not isinstance(payload, dict)
            or type(payload.get("format_version")) is not int
            or payload["format_version"] not in (1, _INTENT_FORMAT_VERSION)
            or not isinstance(payload.get("intents"), dict)):
        raise LiveTradingSafetyError("Order intent ledger is malformed; reconcile it before submitting orders.")
    for key, record in payload["intents"].items():
        validate_order_intent_record(key, record)
    _validate_spot_opo_cancel_alias_ownership(payload["intents"])
    return validate_order_intent_metadata(
        payload, expected_binding=expected_binding, allow_legacy=allow_legacy,
    )


def validate_order_intent_record(key: object, record: object) -> None:
    """Validate one complete record using the authoritative local rules.

    This does not prove cross-record alias or historical client-ID ownership.
    """
    if (not isinstance(key, str) or not key.strip()
            or not isinstance(record, dict) or record.get("client_order_id") != key
            or not isinstance(record.get("state"), str)
            or ("requires_close_confirmation" in record and type(record["requires_close_confirmation"]) is not bool)
            or record.get("state") not in _BLOCKING_STATES | {"rejected"}):
        raise LiveTradingSafetyError("Order intent ledger contains an invalid record; reconcile it before submitting orders.")
    validate_desktop_source_descriptor(record)
    if "primary_fill_receipt" in record:
        from .spot_allocation_generation_runtime import canonical_spot_buy_metadata
        proof = record["primary_fill_receipt"]
        if not isinstance(proof, Mapping):
            raise LiveTradingSafetyError("Spot primary acquisition receipt is malformed.")
        canonical = canonical_spot_buy_metadata({
            **proof, "symbol": record.get("symbol"), "client_order_id": record.get("client_order_id"),
        })
        if (canonical != proof or record.get("market") != "spot" or record.get("type") != "MARKET"
            or record.get("side") != "BUY" or record.get("exchange_status") != "FILLED"
            or proof["exchange_client_order_id"] != record.get("client_order_id")
            or str(proof["order_id"]) != str(record.get("exchange_order_id"))
            or proof["signature"] != record.get("primary_fill_signature")
            or Decimal(proof["gross_qty"]) != _finite_nonnegative_decimal(record.get("executed_qty"))
            or Decimal(proof["net_qty"]) != _finite_nonnegative_decimal(record.get("portfolio_qty"))):
            raise LiveTradingSafetyError("Spot primary acquisition receipt conflicts with its intent.")
    if "portfolio_reconciled" in record and type(record["portfolio_reconciled"]) is not bool:
        raise LiveTradingSafetyError("Order intent ledger contains an invalid portfolio recovery marker.")
    if record.get("type") == "OPO":
        request = record.get("request")
        try:
            normalized_request = validate_spot_opo_request_payload(request)
        except LiveTradingSafetyError as exc:
            raise LiveTradingSafetyError("Order intent ledger contains an invalid Spot OPO request.") from exc
        list_status = record.get("list_status")
        working_status = record.get("working_status")
        pending_status = record.get("pending_status")
        list_id = record.get("exchange_order_list_id")
        working_id = record.get("working_order_id")
        pending_id = record.get("pending_order_id")
        working_executed_raw = record.get("working_executed_qty")
        pending_executed_raw = record.get("pending_executed_qty")
        pending_original_raw = record.get("pending_original_qty")
        snapshot_fields = (
            list_status, working_status, pending_status, list_id, working_id, pending_id,
            working_executed_raw, pending_executed_raw,
        )
        has_snapshot = any(value is not None for value in snapshot_fields)
        if (
            record.get("market") != "spot"
            or record.get("side") != "BUY"
            or normalized_request["symbol"] != record.get("symbol")
            or normalized_request["listClientOrderId"] != key
            or record.get("client_order_id") != key
            or type(record.get("entry_reconciled")) is not bool
            or record.get("protection_state") not in {"unverified", "active", "triggered", "cancelled", "closed", "lost", "none"}
            or (list_status is not None and list_status not in {"EXEC_STARTED", "ALL_DONE"})
            or (working_status is not None and working_status not in _ORDER_STATUSES)
            or (pending_status is not None and pending_status not in _ORDER_STATUSES | _SPOT_PENDING_STATUSES)
            or (list_id is not None and (type(list_id) is not int or list_id < 0))
            or (working_id is not None and (type(working_id) is not int or working_id <= 0))
            or (pending_id is not None and (type(pending_id) is not int or pending_id <= 0))
        ):
            raise LiveTradingSafetyError("Order intent ledger contains an invalid Spot OPO state.")
        protection_state = record.get("protection_state")
        intent_state = record.get("state")
        cancel_state = record.get("cancel_state")
        if cancel_state is not None and cancel_state not in _OPO_CANCEL_STATES:
            raise LiveTradingSafetyError("Order intent ledger contains an invalid Spot OPO cancellation state.")
        if cancel_state is not None and (
            record.get("entry_reconciled") is not True
            or not isinstance(record.get("cancel_submitted_at"), str)
            or not record.get("cancel_submitted_at")
        ):
            raise LiveTradingSafetyError("Spot OPO cancellation is missing its durable recovered-entry intent.")
        if ("cancel_submitted_at" in record) != (cancel_state is not None):
            raise LiveTradingSafetyError("Spot OPO cancellation ledger fields are incomplete.")
        if cancel_state == "confirmed" and (
            not isinstance(record.get("cancel_confirmed_at"), str)
            or not record.get("cancel_confirmed_at")
        ):
            raise LiveTradingSafetyError("Confirmed Spot OPO cancellation is missing its verification time.")
        if cancel_state != "confirmed" and "cancel_confirmed_at" in record:
            raise LiveTradingSafetyError("Unconfirmed Spot OPO cancellation has a false confirmation time.")
        if cancel_state == "confirmed" and protection_state not in {"cancelled", "closed"}:
            raise LiveTradingSafetyError("Confirmed Spot OPO cancellation lacks exact canceled-order evidence.")
        if protection_state == "cancelled" and cancel_state != "confirmed":
            raise LiveTradingSafetyError("Canceled Spot OPO protection lacks a confirmed cancellation intent.")
        strategy_exit_state = record.get("strategy_exit_state")
        has_strategy_exit_fields = any(
            isinstance(name, str) and name.startswith("strategy_exit_") for name in record
        )
        if strategy_exit_state is None:
            if has_strategy_exit_fields or "pending_observed_client_order_id" in record:
                raise LiveTradingSafetyError("Spot OPO strategy exit is missing its durable state.")
        else:
            try:
                strategy_request = validate_spot_opo_cancel_replace_request(
                    record.get("strategy_exit_request"),
                )
            except LiveTradingSafetyError as exc:
                raise LiveTradingSafetyError("Order intent ledger contains an invalid linked Spot SELL request.") from exc
            strategy_quantity = _finite_nonnegative_decimal(record.get("strategy_exit_quantity"))
            strategy_baseline_quantity = _finite_nonnegative_decimal(
                record.get("strategy_exit_pre_order_quantity"),
            )
            if (
                strategy_exit_state not in _OPO_STRATEGY_EXIT_STATES
                or not has_strategy_exit_fields
                or record.get("entry_reconciled") is not True
                or intent_state not in {"accepted", "unknown"}
                or not isinstance(record.get("strategy_exit_client_order_id"), str)
                or record.get("strategy_exit_client_order_id") != strategy_request["newClientOrderId"]
                or record.get("strategy_exit_quantity") != strategy_request["quantity"]
                or strategy_quantity is None or strategy_quantity <= 0
                or not isinstance(record.get("strategy_exit_started_at"), str)
                or not record.get("strategy_exit_started_at")
                or not isinstance(record.get("strategy_exit_request_signature"), str)
                or record.get("strategy_exit_request_signature") != _request_signature(strategy_request)
                or not isinstance(record.get("strategy_exit_pre_order_signature"), str)
                or re.fullmatch(r"[0-9a-f]{64}", record.get("strategy_exit_pre_order_signature", "")) is None
                or strategy_baseline_quantity is None
                or strategy_baseline_quantity != strategy_quantity
                or strategy_quantity != _finite_nonnegative_decimal(record.get("entry_portfolio_quantity"))
                or strategy_request["symbol"] != record.get("symbol")
                or strategy_request["cancelOrderId"] != pending_id
                or strategy_request["cancelOrigClientOrderId"] != normalized_request["pendingClientOrderId"]
                or strategy_quantity != _finite_nonnegative_decimal(pending_original_raw)
                or cancel_state not in {"submitted", "unknown", "confirmed", "rejected"}
                or not isinstance(record.get("cancel_submitted_at"), str)
                or not record.get("cancel_submitted_at")
            ):
                raise LiveTradingSafetyError("Order intent ledger contains an invalid linked Spot SELL intent.")
            outcome = record.get("strategy_exit_outcome")
            alias = strategy_request.get("cancelNewClientOrderId")
            if alias is not None and alias != spot_opo_cancel_client_id(str(strategy_request["newClientOrderId"])):
                raise LiveTradingSafetyError("Linked Spot SELL cancellation alias conflicts with its durable attempt.")
            if "pending_observed_client_order_id" in record:
                observed_alias = record["pending_observed_client_order_id"]
                if (
                    not isinstance(observed_alias, str)
                    or re.fullmatch(r"[A-Za-z0-9._:/-]{1,36}", observed_alias) is None
                    or pending_status != "CANCELED" or _finite_nonnegative_decimal(pending_executed_raw) != 0
                    or cancel_state != "confirmed" or protection_state not in {"cancelled", "closed"}
                    or (alias is not None and observed_alias != alias)
                    or observed_alias in {key, normalized_request["workingClientOrderId"], strategy_request["newClientOrderId"]}
                ):
                    raise LiveTradingSafetyError("Canceled OPO child alias lacks exact terminal cancellation evidence.")
            response_fields = {
                "strategy_exit_cancel_confirmed", "strategy_exit_new_order_accepted",
                "strategy_exit_requires_exact_reconciliation", "strategy_exit_requires_stop_rearm",
                "strategy_exit_response_at", "strategy_exit_order_id", "strategy_exit_status",
                "strategy_exit_executed_qty", "strategy_exit_order_observed_at",
            }
            has_response_fields = any(name in record for name in response_fields)
            if outcome is not None:
                if (
                    not isinstance(record.get("strategy_exit_response_at"), str)
                    or not record.get("strategy_exit_response_at")
                ):
                    raise LiveTradingSafetyError("Spot OPO linked SELL response is missing its durable time.")
                expected_outcomes = {
                    "cancel_failed": (False, False, False),
                    "stop_canceled_exit_rejected": (True, False, True),
                }
                if outcome == "exit_sell_accepted":
                    order_id = record.get("strategy_exit_order_id")
                    exit_status = record.get("strategy_exit_status")
                    try:
                        exit_executed = _finite_nonnegative_decimal(record.get("strategy_exit_executed_qty"))
                    except (InvalidOperation, ValueError):
                        exit_executed = None
                    if (
                        record.get("strategy_exit_cancel_confirmed") is not True
                        or record.get("strategy_exit_new_order_accepted") is not True
                        or record.get("strategy_exit_requires_exact_reconciliation") is not True
                        or type(order_id) is not int or order_id <= 0
                        or exit_status not in {"NEW", "PARTIALLY_FILLED", "FILLED", "CANCELED", "EXPIRED", "EXPIRED_IN_MATCH"}
                        or exit_executed is None or exit_executed > strategy_quantity
                        or record.get("strategy_exit_requires_stop_rearm") is not (exit_status != "FILLED")
                        or (exit_status == "FILLED" and exit_executed != strategy_quantity)
                        or (exit_status == "NEW" and exit_executed != 0)
                        or (exit_status == "PARTIALLY_FILLED" and not 0 < exit_executed < strategy_quantity)
                        or (exit_status in {"CANCELED", "EXPIRED", "EXPIRED_IN_MATCH"} and exit_executed >= strategy_quantity)
                    ):
                        raise LiveTradingSafetyError("Order intent ledger contains invalid linked Spot SELL evidence.")
                else:
                    flags = expected_outcomes.get(outcome)
                    if (
                        flags is None
                        or record.get("strategy_exit_cancel_confirmed") is not flags[0]
                        or record.get("strategy_exit_new_order_accepted") is not flags[1]
                        or record.get("strategy_exit_requires_exact_reconciliation") is not True
                        or record.get("strategy_exit_requires_stop_rearm") is not flags[2]
                    ):
                        raise LiveTradingSafetyError("Order intent ledger contains invalid linked Spot SELL outcome.")
            elif has_response_fields:
                raise LiveTradingSafetyError("Spot OPO linked SELL response fields have no classified outcome.")
            if strategy_exit_state == "no_effect" and not (
                outcome == "cancel_failed"
                and cancel_state == "rejected"
            ):
                raise LiveTradingSafetyError("Spot OPO strategy exit was cleared without proof the stop remained active.")
            if strategy_exit_state == "cancel_failed" and outcome != "cancel_failed":
                raise LiveTradingSafetyError("Spot OPO cancel failure state lacks exact response evidence.")
            if strategy_exit_state == "stop_cancelled" and outcome != "stop_canceled_exit_rejected":
                raise LiveTradingSafetyError("Spot OPO lost-stop state lacks exact cancel-replace evidence.")
            if strategy_exit_state == "sell_accepted" and outcome != "exit_sell_accepted":
                raise LiveTradingSafetyError("Spot OPO strategy SELL state lacks exact response evidence.")
            completion_fields = {
                "strategy_exit_portfolio_reconciled", "strategy_exit_portfolio_signature",
                "strategy_exit_portfolio_quantity", "strategy_exit_trade_ids", "strategy_exit_fill_time_ms",
            }
            if strategy_exit_state == "completed":
                exit_trade_ids = record.get("strategy_exit_trade_ids")
                completion_quantity = _finite_nonnegative_decimal(record.get("strategy_exit_portfolio_quantity"))
                if (
                    outcome != "exit_sell_accepted"
                    or record.get("protection_state") != "closed"
                    or cancel_state != "confirmed"
                    or record.get("strategy_exit_cancel_confirmed") is not True
                    or record.get("strategy_exit_new_order_accepted") is not True
                    or record.get("strategy_exit_requires_stop_rearm") is not False
                    or record.get("strategy_exit_status") != "FILLED"
                    or record.get("strategy_exit_executed_qty") != record.get("strategy_exit_quantity")
                    or not isinstance(record.get("strategy_exit_order_observed_at"), str)
                    or not record.get("strategy_exit_order_observed_at")
                    or record.get("strategy_exit_portfolio_reconciled") is not True
                    or not isinstance(record.get("strategy_exit_portfolio_signature"), str)
                    or re.fullmatch(r"[0-9a-f]{64}", record.get("strategy_exit_portfolio_signature", "")) is None
                    or completion_quantity is None
                    or completion_quantity != strategy_quantity
                    or type(record.get("strategy_exit_fill_time_ms")) is not int
                    or record["strategy_exit_fill_time_ms"] <= 0
                    or not isinstance(exit_trade_ids, list)
                    or not exit_trade_ids
                    or any(type(item) is not int or item <= 0 for item in exit_trade_ids)
                    or len(exit_trade_ids) != len(set(exit_trade_ids))
                ):
                    raise LiveTradingSafetyError("Completed Spot OPO strategy SELL is missing exact portfolio proof.")
            elif any(field in record for field in completion_fields - {"strategy_exit_fill_time_ms"}) or (
                "strategy_exit_fill_time_ms" in record
                and record.get("residual_stop_state") not in _OPO_RESIDUAL_STOP_STATES
            ):
                raise LiveTradingSafetyError("Spot OPO SELL portfolio proof has no completed state.")
            if strategy_exit_state in {"submitted", "unknown"} and outcome is not None:
                raise LiveTradingSafetyError("Spot OPO uncertain SELL state contains a classified outcome.")
            if strategy_exit_state == "submitted" and cancel_state != "submitted":
                raise LiveTradingSafetyError("Spot OPO submitted SELL state contains a conflicting cancel marker.")
            if strategy_exit_state == "unknown" and cancel_state not in {"unknown", "confirmed"}:
                raise LiveTradingSafetyError("Spot OPO unknown SELL state lacks an uncertain cancellation marker.")
            if strategy_exit_state == "unknown" and cancel_state == "confirmed" and protection_state != "cancelled":
                raise LiveTradingSafetyError("Unknown linked SELL has no exact canceled-stop evidence.")
        validate_spot_opo_exit_retry_history(record)
        validate_spot_opo_exit_query_proof(record)
        if "strategy_exit_no_effect_proof" in record:
            validate_spot_opo_no_effect_proof(record, record["strategy_exit_no_effect_proof"])
        residual_stop_state = record.get("residual_stop_state")
        residual_fields = {
            name for name in record
            if isinstance(name, str) and name.startswith("residual_stop_")
        }
        if residual_stop_state is None:
            if residual_fields:
                raise LiveTradingSafetyError("Spot OPO residual protection is missing its durable state.")
        else:
            try:
                residual_quantity = _finite_nonnegative_decimal(record.get("residual_rearm_quantity"))
            except (InvalidOperation, ValueError):
                residual_quantity = None
            residual_signature = record.get("residual_rearm_signature")
            if (
                residual_stop_state not in _OPO_RESIDUAL_STOP_STATES
                or not residual_fields
                or intent_state != "accepted"
                or record.get("entry_reconciled") is not True
                or cancel_state != "confirmed"
                or protection_state not in {"cancelled", "closed"}
                or strategy_exit_state not in {"sell_accepted", "stop_cancelled"}
                or residual_quantity is None
                or not residual_quantity.is_finite()
                or residual_quantity <= 0
                or not isinstance(residual_signature, str)
                or re.fullmatch(r"[0-9a-f]{64}", residual_signature) is None
            ):
                raise LiveTradingSafetyError("Order intent ledger contains an invalid OPO residual-stop state.")
            history = record.get("residual_stop_history", [])
            if not isinstance(history, list) or len(history) > 100:
                raise LiveTradingSafetyError("Order intent ledger contains invalid residual-stop history.")
            seen_residual_ids: set[str] = set()
            for prior in history:
                if not isinstance(prior, Mapping) or prior.get("state") not in {"recovered", "completed"}:
                    raise LiveTradingSafetyError("Order intent ledger contains an unfinished prior residual stop.")
                try:
                    prior_request = validate_spot_opo_residual_stop_request(prior.get("request"))
                except LiveTradingSafetyError as exc:
                    raise LiveTradingSafetyError("Order intent ledger contains an invalid prior residual stop.") from exc
                prior_id = prior_request["newClientOrderId"]
                prior_order_id = prior.get("order_id")
                prior_status = prior.get("status")
                prior_executed = _finite_nonnegative_decimal(prior.get("executed_qty"))
                if (
                    prior_id in seen_residual_ids
                    or prior_request["symbol"] != record.get("symbol")
                    or prior_request["stopPrice"] != normalized_request["pendingStopPrice"]
                    or prior_request["quantity"] != prior.get("pre_order_quantity")
                    or not isinstance(prior.get("pre_order_signature"), str)
                    or re.fullmatch(r"[0-9a-f]{64}", str(prior.get("pre_order_signature"))) is None
                    or not isinstance(prior.get("request_signature"), str)
                    or prior.get("request_signature") != _request_signature(prior_request)
                    or type(prior_order_id) is not int or prior_order_id <= 0
                    or prior_status not in {"FILLED", "CANCELED", "EXPIRED", "EXPIRED_IN_MATCH"}
                    or prior_executed is None
                    or not isinstance(prior.get("observed_at"), str) or not prior.get("observed_at")
                    or not isinstance(prior.get("recovery_signature"), str)
                    or re.fullmatch(r"[0-9a-f]{64}", str(prior.get("recovery_signature"))) is None
                    or type(prior.get("trade_ids")) is not list
                ):
                    raise LiveTradingSafetyError("Order intent ledger contains invalid residual-stop history evidence.")
                seen_residual_ids.add(prior_id)
            current_request_value = record.get("residual_stop_request")
            if residual_stop_state == "rearm_required":
                if current_request_value is not None:
                    try:
                        current_request = validate_spot_opo_residual_stop_request(current_request_value)
                    except LiveTradingSafetyError as exc:
                        raise LiveTradingSafetyError("Order intent ledger contains an invalid completed residual stop.") from exc
                    prior_quantity = _finite_nonnegative_decimal(record.get("residual_stop_pre_order_quantity"))
                    recovered_quantity = _finite_nonnegative_decimal(record.get("residual_stop_recovery_quantity"))
                    executed_quantity = _finite_nonnegative_decimal(record.get("residual_stop_executed_qty"))
                    recovery_trade_ids = record.get("residual_stop_recovery_trade_ids")
                    recovery_fill_time = record.get("residual_stop_recovery_fill_time_ms")
                    try:
                        validate_spot_opo_residual_stop_order({
                            "symbol": record.get("symbol"),
                            "clientOrderId": current_request["newClientOrderId"],
                            "side": "SELL", "type": "STOP_LOSS", "orderListId": -1,
                            "orderId": record.get("residual_stop_order_id"),
                            "status": record.get("residual_stop_status"),
                            "origQty": current_request["quantity"],
                            "executedQty": record.get("residual_stop_executed_qty"),
                            "stopPrice": current_request["stopPrice"],
                        }, current_request)
                    except LiveTradingSafetyError as exc:
                        raise LiveTradingSafetyError("Residual stop rearm contains invalid prior order evidence.") from exc
                    if (
                        current_request["newClientOrderId"] in seen_residual_ids
                        or current_request["symbol"] != record.get("symbol")
                        or current_request["stopPrice"] != normalized_request["pendingStopPrice"]
                        or current_request["quantity"] != record.get("residual_stop_pre_order_quantity")
                        or record.get("residual_stop_request_signature") != _request_signature(current_request)
                        or not isinstance(record.get("residual_stop_pre_order_signature"), str)
                        or re.fullmatch(r"[0-9a-f]{64}", str(record.get("residual_stop_pre_order_signature"))) is None
                        or not isinstance(record.get("residual_stop_started_at"), str)
                        or not record.get("residual_stop_started_at")
                        or record.get("residual_stop_status") not in {"CANCELED", "EXPIRED", "EXPIRED_IN_MATCH"}
                        or prior_quantity is None or recovered_quantity is None
                        or prior_quantity != recovered_quantity + residual_quantity
                        or executed_quantity is None
                        or recovered_quantity < executed_quantity
                        or ((recovered_quantity == 0) != (executed_quantity == 0))
                        or not isinstance(recovery_trade_ids, list)
                        or (recovered_quantity == 0 and (
                            recovery_trade_ids or record.get("residual_stop_pre_order_signature") != residual_signature
                        ))
                        or (recovered_quantity > 0 and (
                            not recovery_trade_ids
                            or any(type(item) is not int or item <= 0 for item in recovery_trade_ids)
                            or len(recovery_trade_ids) != len(set(recovery_trade_ids))
                            or type(recovery_fill_time) is not int or recovery_fill_time <= 0
                        ))
                        or record.get("residual_stop_terminal_state") != "recovered"
                        or type(record.get("residual_stop_order_id")) is not int
                        or not isinstance(record.get("residual_stop_observed_at"), str)
                        or not record.get("residual_stop_observed_at")
                        or record.get("residual_stop_query_verified") is not True
                        or record.get("residual_stop_recovered") is not True
                        or not isinstance(record.get("residual_stop_recovery_signature"), str)
                        or re.fullmatch(r"[0-9a-f]{64}", str(record.get("residual_stop_recovery_signature"))) is None
                        or _finite_nonnegative_decimal(record.get("residual_stop_recovery_quantity")) is None
                    ):
                        raise LiveTradingSafetyError("Residual stop rearm is missing exact prior fill recovery proof.")
            else:
                try:
                    current_request = validate_spot_opo_residual_stop_request(current_request_value)
                except LiveTradingSafetyError as exc:
                    raise LiveTradingSafetyError("Order intent ledger contains an invalid residual-stop request.") from exc
                current_id = current_request["newClientOrderId"]
                current_order_id = record.get("residual_stop_order_id")
                current_status = record.get("residual_stop_status")
                if (
                    current_id in seen_residual_ids
                    or current_request["symbol"] != record.get("symbol")
                    or current_request["stopPrice"] != normalized_request["pendingStopPrice"]
                    or current_request["quantity"] != record.get("residual_stop_pre_order_quantity")
                    or record.get("residual_stop_pre_order_quantity") != format(residual_quantity, "f")
                    or record.get("residual_stop_pre_order_signature") != residual_signature
                    or not isinstance(record.get("residual_stop_request_signature"), str)
                    or record.get("residual_stop_request_signature") != _request_signature(current_request)
                    or not isinstance(record.get("residual_stop_started_at"), str)
                    or not record.get("residual_stop_started_at")
                ):
                    raise LiveTradingSafetyError("Order intent ledger residual-stop request conflicts with its allocation baseline.")
                if residual_stop_state in {"submitted", "unknown"}:
                    if any(key in record for key in (
                        "residual_stop_order_id", "residual_stop_status", "residual_stop_executed_qty",
                        "residual_stop_observed_at", "residual_stop_query_verified",
                    )):
                        raise LiveTradingSafetyError("Unconfirmed residual stop contains false exchange response evidence.")
                else:
                    try:
                        current_evidence = validate_spot_opo_residual_stop_order({
                            "symbol": record.get("symbol"),
                            "clientOrderId": current_id,
                            "side": "SELL",
                            "type": "STOP_LOSS",
                            "orderListId": -1,
                            "orderId": current_order_id,
                            "status": current_status,
                            "origQty": current_request["quantity"],
                            "executedQty": record.get("residual_stop_executed_qty"),
                            "stopPrice": current_request["stopPrice"],
                        }, current_request)
                    except LiveTradingSafetyError as exc:
                        raise LiveTradingSafetyError("Order intent ledger contains invalid residual-stop order evidence.") from exc
                    if (
                        type(current_order_id) is not int or current_order_id <= 0
                        or not isinstance(record.get("residual_stop_observed_at"), str)
                        or not record.get("residual_stop_observed_at")
                        or type(record.get("residual_stop_query_verified")) is not bool
                        or (
                            residual_stop_state == "acknowledged"
                            and record.get("residual_stop_query_verified") is not False
                        )
                        or (
                            residual_stop_state in {"active", "triggered", "completed"}
                            and record.get("residual_stop_query_verified") is not True
                        )
                        or (residual_stop_state == "active" and (
                            current_evidence["status"] != "NEW" or current_evidence["executed_quantity"] != "0"
                        ))
                        or (residual_stop_state == "triggered" and current_evidence["status"] == "NEW")
                        or (residual_stop_state == "completed" and (
                            current_evidence["status"] != "FILLED"
                            or record.get("residual_stop_recovered") is not True
                            or not isinstance(record.get("residual_stop_recovery_signature"), str)
                            or re.fullmatch(r"[0-9a-f]{64}", str(record.get("residual_stop_recovery_signature"))) is None
                        ))
                    ):
                        raise LiveTradingSafetyError("Order intent ledger residual stop does not match its durable state.")
            if residual_stop_state == "completed" and protection_state != "closed":
                raise LiveTradingSafetyError("Completed residual stop has not closed the OPO protection record.")
            if residual_stop_state in _OPO_RESIDUAL_STOP_STATES:
                no_fill_required = record.get("residual_rearm_no_fill")
                if type(no_fill_required) is not bool:
                    raise LiveTradingSafetyError("Residual re-arm requirement is missing its recovery classification.")
                fill_signature = record.get("strategy_exit_fill_signature")
                fill_quantity = _finite_nonnegative_decimal(record.get("strategy_exit_fill_quantity"))
                fill_trade_ids = record.get("strategy_exit_fill_trade_ids")
                fill_time = record.get("strategy_exit_fill_time_ms")
                if (
                    not isinstance(fill_signature, str)
                    or re.fullmatch(r"[0-9a-f]{64}", fill_signature) is None
                    or fill_quantity is None
                    or not isinstance(fill_trade_ids, list)
                    or type(fill_time) is not int or fill_time <= 0
                    or (no_fill_required and (fill_quantity != 0 or fill_trade_ids))
                    or (not no_fill_required and (
                        fill_quantity <= 0 or not fill_trade_ids
                        or any(type(item) is not int or item <= 0 for item in fill_trade_ids)
                        or len(fill_trade_ids) != len(set(fill_trade_ids))
                    ))
                ):
                    raise LiveTradingSafetyError("Residual re-arm requirement lacks terminal SELL recovery proof.")
        if (
            (intent_state == "rejected" and protection_state != "none")
            or (intent_state == "accepted" and protection_state == "none")
            or (intent_state in {"pending", "submitted"} and protection_state != "unverified")
            or (intent_state == "unknown" and protection_state == "none")
        ):
            raise LiveTradingSafetyError("Order intent ledger contains an invalid Spot OPO state transition.")
        if record.get("state") in {"accepted", "rejected"} and (
            list_status is None or working_status is None or pending_status is None
            or list_id is None or working_id is None or pending_id is None
            or working_executed_raw is None or pending_executed_raw is None
        ):
            raise LiveTradingSafetyError("Order intent ledger is missing exact Spot OPO exchange evidence.")
        if has_snapshot and any(value is None for value in snapshot_fields):
            raise LiveTradingSafetyError("Order intent ledger contains incomplete Spot OPO exchange evidence.")
        if has_snapshot:
            working_executed = _finite_nonnegative_decimal(working_executed_raw)
            pending_executed = _finite_nonnegative_decimal(pending_executed_raw)
            pending_original = (
                _finite_nonnegative_decimal(pending_original_raw)
                if pending_original_raw is not None else None
            )
            if (
                working_executed is None or pending_executed is None
                or (pending_original_raw is not None and pending_original is None)
            ):
                raise LiveTradingSafetyError("Order intent ledger contains invalid Spot OPO execution quantities.")
            requested_quantity = Decimal(normalized_request["workingQuantity"])
            if protection_state == "active" and not (
                record.get("state") == "accepted"
                and list_status == "EXEC_STARTED"
                and working_status == "FILLED"
                and working_executed == requested_quantity
                and pending_status == "NEW"
                and pending_executed == 0
                and pending_original is not None and pending_original > 0
            ):
                raise LiveTradingSafetyError("Order intent ledger has an unproven active Spot OPO stop.")
            if protection_state == "triggered" and not (
                record.get("state") in {"accepted", "unknown"}
                and list_status == "ALL_DONE"
                and working_status == "FILLED"
                and working_executed == requested_quantity
                and pending_status == "FILLED"
                and pending_original is not None and pending_original > 0
                and pending_executed == pending_original
            ):
                raise LiveTradingSafetyError("Order intent ledger has an unproven triggered Spot OPO stop.")
            if protection_state == "cancelled" and not (
                record.get("state") == "accepted"
                and record.get("entry_reconciled") is True
                and cancel_state == "confirmed"
                and list_status == "ALL_DONE"
                and working_status == "FILLED"
                and working_executed == requested_quantity
                and pending_status == "CANCELED"
                and pending_executed == 0
                and pending_original is not None and pending_original > 0
            ):
                raise LiveTradingSafetyError("Order intent ledger has an unproven canceled Spot OPO stop.")
            if protection_state == "none" and not (
                record.get("state") == "rejected"
                and list_status == "ALL_DONE"
                and working_status in {"CANCELED", "EXPIRED", "EXPIRED_IN_MATCH", "REJECTED"}
                and working_executed == 0
                and pending_status in {"PENDING_NEW", "CANCELED", "EXPIRED", "REJECTED"}
                and pending_executed == 0
            ):
                raise LiveTradingSafetyError("Order intent ledger has an unproven no-fill Spot OPO result.")
            if protection_state == "lost" and not (
                record.get("state") in {"accepted", "unknown"}
                and (working_executed > 0 or pending_executed > 0)
            ):
                raise LiveTradingSafetyError("Order intent ledger has an unproven lost Spot OPO protection state.")
            if protection_state == "unverified" and record.get("state") == "rejected":
                raise LiveTradingSafetyError("Rejected Spot OPO intent must have verified no-fill evidence.")
        if record.get("entry_reconciled") is True:
            try:
                entry_quantity = Decimal(str(record.get("entry_portfolio_quantity") or "NaN"))
            except (InvalidOperation, ValueError):
                entry_quantity = Decimal("NaN")
            if (
                not entry_quantity.is_finite() or entry_quantity <= 0
                or entry_quantity > Decimal(normalized_request["workingQuantity"])
                or record.get("pending_original_qty") is None
                or Decimal(str(record.get("pending_original_qty"))) != entry_quantity
                or not isinstance(record.get("entry_recovery_signature"), str)
                or re.fullmatch(r"[0-9a-f]{64}", record["entry_recovery_signature"]) is None
                or record.get("protection_state") not in {"active", "triggered", "cancelled", "closed", "lost", "unverified"}
            ):
                raise LiveTradingSafetyError("Order intent ledger contains an invalid Spot OPO entry proof.")
        if "exit_reconciled" in record and type(record["exit_reconciled"]) is not bool:
            raise LiveTradingSafetyError("Order intent ledger contains an invalid Spot OPO exit marker.")
        if record.get("exit_reconciled") is True:
            try:
                exit_quantity = Decimal(str(record.get("exit_portfolio_quantity") or "NaN"))
            except (InvalidOperation, ValueError):
                exit_quantity = Decimal("NaN")
            if (
                intent_state != "accepted"
                or protection_state != "triggered"
                or record.get("entry_reconciled") is not True
                or not exit_quantity.is_finite() or exit_quantity <= 0
                or exit_quantity != Decimal(str(record.get("entry_portfolio_quantity")))
                or not isinstance(record.get("exit_recovery_signature"), str)
                or re.fullmatch(r"[0-9a-f]{64}", record["exit_recovery_signature"]) is None
                or record.get("exit_order_id") != pending_id
            ):
                raise LiveTradingSafetyError("Order intent ledger contains an invalid Spot OPO exit proof.")
    if "portfolio_pre_order_signature" in record or "portfolio_pre_order_qty" in record:
        try:
            baseline_qty = Decimal(str(record.get("portfolio_pre_order_qty") or "NaN"))
        except (InvalidOperation, ValueError):
            baseline_qty = Decimal("NaN")
        if (
            record.get("market") != "spot"
            or record.get("type") != "MARKET"
            or record.get("side") != "SELL"
            or not baseline_qty.is_finite() or baseline_qty <= 0
            or not isinstance(record.get("portfolio_pre_order_signature"), str)
            or re.fullmatch(r"[0-9a-f]{64}", record["portfolio_pre_order_signature"]) is None
        ):
            raise LiveTradingSafetyError("Order intent ledger contains an invalid Spot SELL baseline.")
    if record.get("portfolio_reconciled") is True and (
        record.get("market") != "spot"
        or record.get("type") != "MARKET"
        or record.get("side") not in {"BUY", "SELL"}
        or record.get("exchange_status") not in _ORDER_STATUSES
        or record.get("exchange_status") in {"NEW", "PARTIALLY_FILLED"}
    ):
        raise LiveTradingSafetyError("Order intent ledger contains an invalid portfolio recovery marker.")
    if record.get("portfolio_reconciled") is True:
        try:
            portfolio_qty = Decimal(str(record.get("portfolio_qty") or "NaN"))
            executed_qty = Decimal(str(record.get("executed_qty") or "NaN"))
        except (InvalidOperation, ValueError):
            portfolio_qty = Decimal("NaN")
            executed_qty = Decimal("NaN")
        if (
            not portfolio_qty.is_finite() or portfolio_qty <= 0
            or not executed_qty.is_finite() or executed_qty <= 0
            or (record.get("side") == "BUY" and portfolio_qty > executed_qty)
            or (record.get("side") == "SELL" and portfolio_qty < executed_qty)
            or not isinstance(record.get("portfolio_recovery_signature"), str)
            or re.fullmatch(r"[0-9a-f]{64}", record["portfolio_recovery_signature"]) is None
        ):
            raise LiveTradingSafetyError("Order intent ledger contains an invalid portfolio recovery proof.")


def validate_order_intent_metadata(
    payload: object, *, expected_binding: Mapping[str, str] | None = None, allow_legacy: bool = False,
) -> dict[str, object]:
    """Validate actual ledger header fields without an intents placeholder.

    Local records and global ownership must be validated separately. Unknown
    header fields retain the complete JSON validator's existing behavior.
    """
    if (not isinstance(payload, dict)
            or type(payload.get("format_version")) is not int
            or payload["format_version"] not in (1, _INTENT_FORMAT_VERSION)):
        raise LiveTradingSafetyError("Order intent ledger is malformed; reconcile it before submitting orders.")
    if payload["format_version"] == 1:
        if allow_legacy:
            return payload
        raise LiveTradingSafetyError("Legacy order intent ledger requires explicit migration; submission is blocked.")
    binding = payload.get("binding")
    try:
        store_id = payload.get("store_id")
        if not isinstance(store_id, str) or str(UUID(store_id)) != store_id:
            raise ValueError("invalid store ID")
        created = datetime.fromisoformat(str(payload.get("created_at") or "").replace("Z", "+00:00"))
        if created.tzinfo is None:
            raise ValueError("missing timezone")
    except (ValueError, TypeError, AttributeError) as exc:
        raise LiveTradingSafetyError("Order intent ledger has invalid provisioning metadata.") from exc
    if (not isinstance(binding, dict)
            or set(binding) != {"exchange", "environment", "credential_fingerprint"}
            or binding.get("exchange") != "binance"
            or binding.get("environment") not in ("live", "testnet")
            or not isinstance(binding.get("credential_fingerprint"), str)
            or re.fullmatch(r"[0-9a-f]{64}", binding["credential_fingerprint"]) is None):
        raise LiveTradingSafetyError("Order intent ledger has invalid credential/environment binding.")
    rotation_history = payload.get("credential_rotation_history", [])
    if not isinstance(rotation_history, list):
        raise LiveTradingSafetyError("Order intent ledger has invalid credential rotation history.")
    previous_rotation_fingerprint = None
    for rotation in rotation_history:
        if (
            not isinstance(rotation, dict)
            or set(rotation) != {"previous_fingerprint", "new_fingerprint", "rotated_at", "reconciliation_reference"}
            or not isinstance(rotation.get("previous_fingerprint"), str)
            or re.fullmatch(r"[0-9a-f]{64}", rotation["previous_fingerprint"]) is None
            or not isinstance(rotation.get("new_fingerprint"), str)
            or re.fullmatch(r"[0-9a-f]{64}", rotation["new_fingerprint"]) is None
            or rotation["previous_fingerprint"] == rotation["new_fingerprint"]
            or not isinstance(rotation.get("rotated_at"), str)
            or not isinstance(rotation.get("reconciliation_reference"), str)
        ):
            raise LiveTradingSafetyError("Order intent ledger has invalid credential rotation history.")
        try:
            rotated_at = datetime.fromisoformat(rotation["rotated_at"].replace("Z", "+00:00"))
            if rotated_at.tzinfo is None:
                raise ValueError("missing timezone")
        except (ValueError, TypeError) as exc:
            raise LiveTradingSafetyError("Order intent ledger has invalid credential rotation history.") from exc
        reference = rotation["reconciliation_reference"]
        if (
            not isinstance(reference, str)
            or not reference.strip()
            or len(reference) > 160
            or any(character in reference for character in "\r\n\0")
            or (previous_rotation_fingerprint is not None and rotation["previous_fingerprint"] != previous_rotation_fingerprint)
        ):
            raise LiveTradingSafetyError("Order intent ledger has invalid credential rotation history.")
        previous_rotation_fingerprint = rotation["new_fingerprint"]
    if rotation_history and previous_rotation_fingerprint != binding["credential_fingerprint"]:
        raise LiveTradingSafetyError("Order intent ledger credential rotation history does not match its binding.")
    if expected_binding is not None and binding != expected_binding:
        raise LiveTradingSafetyError("Order intent ledger belongs to different credentials or environment; submission is blocked.")
    return payload


def _write_ledger(path: Path, payload: Mapping[str, object]) -> None:
    write_ledger(path, payload)


def _client_order_id(params: Mapping[str, object]) -> str:
    value = str(params.get("newClientOrderId") or "").strip()
    if not value:
        raise LiveTradingSafetyError("Client order ID is required before submitting an exchange order.")
    return value


def _intent_record(params: Mapping[str, object], *, market: str, source: str) -> dict[str, object]:
    record = {
        "client_order_id": _client_order_id(params),
        "market": str(market),
        "source": str(source),
        "symbol": str(params.get("symbol") or "").upper(),
        "side": str(params.get("side") or "").upper(),
        "position_side": str(params.get("positionSide") or "BOTH").upper(),
        "type": str(params.get("type") or "").upper(),
        "quantity": str(params.get("quantity") or ""),
        "requires_close_confirmation": (
            params.get("type") == "MARKET" and is_exchange_risk_reducing_order(market, params)
        ),
        "state": "pending",
        "created_at": _now(),
        "updated_at": _now(),
    }
    if market == "spot" and str(params.get("type") or "").upper() == "MARKET":
        record["portfolio_reconciled"] = False
    return record


def _has_active_spot_protection(record: Mapping[str, object]) -> bool:
    return (
        record.get("market") == "spot"
        and record.get("type") == "OPO"
        and record.get("strategy_exit_state") != "completed"
        and record.get("residual_stop_state") != "completed"
        and (
            record.get("protection_state") == "active"
            or record.get("residual_stop_state") == "active"
        )
    )


def _active_spot_protection_records(intents: Mapping[str, object]) -> dict[str, dict[str, object]]:
    return {
        client_order_id: dict(record)
        for client_order_id, record in intents.items()
        if isinstance(record, Mapping) and _has_active_spot_protection(record)
    }


def _raise_for_duplicate_intent(intents: Mapping[str, object], client_order_id: str) -> None:
    existing = intents.get(client_order_id)
    if isinstance(existing, Mapping) and str(existing.get("state") or "") in _BLOCKING_STATES:
        raise LiveTradingSafetyError(
            f"Client order ID {client_order_id} already has state "
            f"{existing.get('state')}; reconcile it before retrying."
        )


def _assert_unused_spot_client_ids(intents: Mapping[str, object], client_order_ids: tuple[str, ...]) -> None:
    used_ids = used_spot_client_order_ids(intents)
    if any(client_id in used_ids for client_id in client_order_ids):
        raise LiveTradingSafetyError("Spot client order ID was already used in this ledger.")


def _raise_for_unresolved_intents(
    intents: Mapping[str, object], *, exclude_client_order_id: str | None = None,
) -> None:
    unresolved_ids = [
        client_order_id for client_order_id, record in intents.items()
        if client_order_id != exclude_client_order_id and isinstance(record, Mapping) and _is_unresolved(record)
    ]
    if unresolved_ids:
        raise LiveTradingSafetyError(
            "Unresolved exchange order intent(s) block new live submissions; "
            f"reconcile {', '.join(unresolved_ids[:3])} before continuing."
        )


def _refresh_spot_active_protection(
    self, *, exclude_client_order_id: str | None = None,
    reject_existing_client_order_id: str | None = None,
    reject_spot_client_order_ids: tuple[str, ...] = (),
) -> tuple[str, dict[str, dict[str, object]]]:
    """Obtain exact applied proof for every active stop before one new BUY boundary."""
    path = _intent_path(self)
    with ledger_transaction(path):
        ledger = _read_ledger(path, expected_binding=_intent_binding(self))
        intents = ledger["intents"]
        if not isinstance(intents, dict):
            raise LiveTradingSafetyError("Order intent ledger is malformed; new Spot exposure is blocked.")
        if reject_existing_client_order_id is not None:
            _raise_for_duplicate_intent(intents, reject_existing_client_order_id)
        _raise_for_unresolved_intents(intents, exclude_client_order_id=exclude_client_order_id)
        if reject_spot_client_order_ids:
            _assert_unused_spot_client_ids(intents, reject_spot_client_order_ids)
        active_records = _active_spot_protection_records(intents)
        store_id = str(ledger["store_id"])
    refreshed: dict[str, dict[str, object]] = {}
    # No monitoring limit or cached timestamp can authorize new exposure.
    for client_order_id in active_records:
        applied_records: list[dict[str, object]] = []
        observation = _reconcile_spot_opo_intent(
            self, client_order_id, force=True, applied_records=applied_records,
        )
        if (
            observation.get("error")
            or observation.get("reconciled") is not True
            or len(applied_records) != 1
            or not _has_active_spot_protection(applied_records[0])
            or _is_unresolved(applied_records[0])
        ):
            raise LiveTradingSafetyError(
                "Fresh exact Spot protection could not be verified; new exposure is blocked. "
                f"Reconcile {client_order_id} before continuing."
            )
        refreshed[client_order_id] = applied_records[0]
    return store_id, refreshed


def _assert_fresh_spot_protection(
    ledger: Mapping[str, object], proof: tuple[str, dict[str, dict[str, object]]],
    *, exclude_client_order_id: str | None = None,
) -> None:
    intents = ledger.get("intents")
    if not isinstance(intents, dict):
        raise LiveTradingSafetyError("Order intent ledger is malformed; new Spot exposure is blocked.")
    _raise_for_unresolved_intents(intents, exclude_client_order_id=exclude_client_order_id)
    if str(ledger.get("store_id")) != proof[0] or _active_spot_protection_records(intents) != proof[1]:
        raise LiveTradingSafetyError(
            "Spot protection changed after its exact refresh; new exposure is blocked. Query it again."
        )


def _submit_spot_buy_intent(self, record: Mapping[str, object], *, via: str) -> None:
    client_order_id = str(record["client_order_id"])
    protection_proof = _refresh_spot_active_protection(self, exclude_client_order_id=client_order_id)
    path = _intent_path(self)
    desktop_source = desktop_entry_for_submission(self, record)
    desktop_params = record["request"] if record.get("type") == "OPO" else {
        "symbol": record["symbol"], "side": "BUY", "newClientOrderId": client_order_id,
    }
    with desktop_entry_transaction(self, path, desktop_params, desktop_source):
        ledger = _read_ledger(path, expected_binding=_intent_binding(self))
        assert_desktop_entry_ledger(desktop_source, ledger)
        intents = ledger["intents"]
        if not isinstance(intents, dict):
            raise LiveTradingSafetyError("Order intent ledger is malformed; Spot BUY submission is blocked.")
        current = intents.get(client_order_id)
        if not isinstance(current, dict) or current != record:
            raise LiveTradingSafetyError("Spot BUY intent changed before submission; reconcile it first.")
        _assert_fresh_spot_protection(
            ledger, protection_proof, exclude_client_order_id=client_order_id,
        )
        current.update(state="submitted", updated_at=_now(), last_via=str(via), submitted_at=_now())
        _write_ledger(path, ledger)


def _begin_order_intent(self, params: Mapping[str, object], *, market: str, source: str) -> dict[str, object]:
    if market == "spot" and getattr(self, "_enforce_spot_execution_owner", False) and (
        is_live_trading_mode(getattr(self, "mode", None))
        or getattr(self, "_spot_owner_initial_live", False)
    ):
        if not _spot_owner_scope(self):
            raise LiveTradingSafetyError("Spot execution owner requires a Spot account wrapper.")
        _ensure_spot_execution_owner(self)
    record = _intent_record(params, market=market, source=source)
    protection_proof = (
        _refresh_spot_active_protection(
            self, reject_existing_client_order_id=str(record["client_order_id"]),
            reject_spot_client_order_ids=(str(record["client_order_id"]),),
        )
        if market == "spot" and record.get("side") == "BUY" else None
    )
    path = _intent_path(self)
    if (
        market == "spot"
        and record.get("type") == "MARKET"
        and record.get("side") == "SELL"
        and is_live_trading_mode(getattr(self, "mode", None))
    ):
        try:
            from app.gui.shared.allocation_persistence import get_position_allocations_path
            from .spot_fill_recovery_runtime import spot_live_allocation_baseline

            app_root = Path(__file__).resolve().parents[4]
            allocation_path = get_position_allocations_path(app_root / "gui" / "window_shell.py")
            baseline = spot_live_allocation_baseline(allocation_path, symbol=str(record["symbol"]))
        except (ImportError, OSError, LiveTradingSafetyError):
            baseline = None
        if baseline is not None:
            record["portfolio_pre_order_signature"] = baseline["signature"]
            record["portfolio_pre_order_qty"] = baseline["quantity"]
    desktop_source = capture_desktop_entry(self, params) if market == "spot" and record.get("side") == "BUY" else None
    if desktop_source is not None:
        record["desktop_entry_source"] = desktop_source_descriptor(desktop_source[1])
    with desktop_entry_transaction(self, path, params, desktop_source):
        ledger = _read_ledger(path, expected_binding=_intent_binding(self))
        assert_desktop_entry_ledger(desktop_source, ledger)
        intents = ledger["intents"]
        if not isinstance(intents, dict):
            raise LiveTradingSafetyError("Order intent ledger is malformed; reconcile it before submitting orders.")
        _raise_for_duplicate_intent(intents, str(record["client_order_id"]))
        if market == "spot":
            _assert_unused_spot_client_ids(intents, (str(record["client_order_id"]),))
        if protection_proof is not None:
            _assert_fresh_spot_protection(ledger, protection_proof)
        if market == "spot" and record.get("type") == "MARKET" and record.get("side") == "SELL":
            protected_opo_exists = any(
                isinstance(intent, Mapping)
                and intent.get("market") == "spot"
                and intent.get("type") == "OPO"
                and intent.get("symbol") == record.get("symbol")
                and intent.get("state") == "accepted"
                and intent.get("entry_reconciled") is True
                and (
                    intent.get("protection_state") == "active"
                    or intent.get("residual_stop_state") == "active"
                )
                for intent in intents.values()
            )
            if protected_opo_exists:
                raise LiveTradingSafetyError(
                    "Spot market SELL is blocked while an OPO stop reserves inventory for this symbol, including a re-armed residual stop."
                )
        unresolved_ids = [
            str(intent.get("client_order_id") or client_order_id)
            for client_order_id, intent in intents.items()
            if isinstance(intent, Mapping) and _is_unresolved(intent)
        ]
        if unresolved_ids:
            raise LiveTradingSafetyError(
                "Unresolved exchange order intent(s) block new live submissions; "
                f"reconcile {', '.join(unresolved_ids[:3])} before continuing."
            )
        intents[record["client_order_id"]] = record
        _write_ledger(path, ledger)
        remember_desktop_entry(self, record, desktop_source, ledger)
    return record


def _begin_spot_opo_intent(
    self, params: Mapping[str, object], *, source: str,
) -> dict[str, object]:
    request = validate_spot_opo_request_payload(params)
    if not isinstance(source, str) or not source.strip() or len(source) > 120:
        raise LiveTradingSafetyError("Spot OPO intent source is invalid.")
    if is_live_trading_mode(getattr(self, "mode", None)):
        if not _spot_owner_scope(self):
            raise LiveTradingSafetyError("Live Spot OPO requires the single-owner execution boundary.")
        _ensure_spot_execution_owner(self)
    now = _now()
    record: dict[str, object] = {
        "client_order_id": request["listClientOrderId"],
        "market": "spot",
        "source": source.strip(),
        "symbol": request["symbol"],
        "side": "BUY",
        "type": "OPO",
        "quantity": request["workingQuantity"],
        "state": "pending",
        "created_at": now,
        "updated_at": now,
        "request": request,
        "entry_reconciled": False,
        "protection_state": "unverified",
    }
    client_ids = tuple(request[name] for name in ("listClientOrderId", "workingClientOrderId", "pendingClientOrderId"))
    protection_proof = _refresh_spot_active_protection(
        self, reject_existing_client_order_id=request["listClientOrderId"], reject_spot_client_order_ids=client_ids,
    )
    path = _intent_path(self)
    desktop_source = capture_desktop_entry(self, request)
    if desktop_source is not None:
        record["desktop_entry_source"] = desktop_source_descriptor(desktop_source[1])
    with desktop_entry_transaction(self, path, request, desktop_source):
        ledger = _read_ledger(path, expected_binding=_intent_binding(self))
        assert_desktop_entry_ledger(desktop_source, ledger)
        intents = ledger["intents"]
        if not isinstance(intents, dict):
            raise LiveTradingSafetyError("Order intent ledger is malformed; reconcile it before submitting orders.")
        _raise_for_duplicate_intent(intents, str(record["client_order_id"]))
        _assert_unused_spot_client_ids(intents, client_ids)
        _assert_fresh_spot_protection(ledger, protection_proof)
        unresolved_ids = [
            str(intent.get("client_order_id") or client_order_id)
            for client_order_id, intent in intents.items()
            if isinstance(intent, Mapping) and _is_unresolved(intent)
        ]
        if unresolved_ids:
            raise LiveTradingSafetyError(
                "Unresolved exchange order intent(s) block new live submissions; "
                f"reconcile {', '.join(unresolved_ids[:3])} before continuing."
            )
        intents[record["client_order_id"]] = record
        _write_ledger(path, ledger)
        remember_desktop_entry(self, record, desktop_source, ledger)
    return record


def _mark_spot_opo_submitted(self, list_client_order_id: str, *, via: str) -> None:
    record = _get_order_intent_record(self, str(list_client_order_id))
    if record is None or record.get("type") != "OPO":
        raise LiveTradingSafetyError("Spot OPO intent is missing; submission is blocked.")
    if record.get("state") != "pending":
        raise LiveTradingSafetyError("Spot OPO intent is not in a submittable state.")
    _submit_spot_buy_intent(self, record, via=via)


def _mark_spot_opo_unknown(self, list_client_order_id: str, *, error: object) -> None:
    record = _get_order_intent_record(self, str(list_client_order_id))
    if record is None or record.get("type") != "OPO":
        raise LiveTradingSafetyError("Spot OPO intent is missing; its outcome cannot be recorded.")
    if record.get("state") not in {"pending", "submitted", "unknown"}:
        raise LiveTradingSafetyError("Resolved Spot OPO intent cannot be marked as an uncertain submission.")
    updated = _update_order_intent_by_id(
        self, str(list_client_order_id), state="unknown", expected_record=record,
        protection_state="unverified", last_error=redact_text(error), uncertain_at=_now(),
    )
    if updated is None:
        raise LiveTradingSafetyError("Spot OPO intent changed while recording an uncertain submission.")


def _mark_spot_opo_accepted(
    self, params: Mapping[str, object], *, via: str, result: object,
) -> dict[str, object]:
    request = validate_spot_opo_request_payload(params)
    list_client_order_id = request["listClientOrderId"]
    record = _get_order_intent_record(self, list_client_order_id)
    if record is None or record.get("type") != "OPO" or record.get("request") != request:
        raise LiveTradingSafetyError("Spot OPO acknowledgement does not match a durable request intent.")
    if record.get("state") != "submitted":
        raise LiveTradingSafetyError("Spot OPO acknowledgement requires a durably submitted intent.")
    try:
        evidence = validate_spot_opo_acknowledgement(result, request)
    except LiveTradingSafetyError as exc:
        _update_order_intent_by_id(
            self, list_client_order_id, state="unknown", expected_record=record,
            protection_state="unverified", last_error=redact_text(exc), uncertain_at=_now(),
        )
        raise LiveTradingSafetyError("Spot OPO acknowledgement conflicts with its intent; reconciliation required.") from exc
    updated = _update_order_intent_by_id(
        self,
        list_client_order_id,
        state="accepted",
        expected_record=record,
        protection_state="unverified",
        exchange_order_list_id=evidence["order_list_id"],
        list_status=evidence["list_status"],
        working_order_id=evidence["working_order_id"],
        working_status=evidence["working_status"],
        working_executed_qty=evidence["working_executed_qty"],
        pending_order_id=evidence["pending_order_id"],
        pending_status=evidence["pending_status"],
        pending_executed_qty=evidence["pending_executed_qty"],
        last_via=str(via),
        accepted_at=_now(),
    )
    if updated is None:
        raise LiveTradingSafetyError("Spot OPO intent changed while recording acceptance; reconcile it first.")
    return updated


def _check_spot_opo_strategy_exit_client_id(
    self, list_client_order_id: str, *, new_order_client_id: str,
) -> None:
    """Reject a previously used exit ID before any refresh rewrites the ledger."""
    path = _intent_path(self)
    with ledger_transaction(path):
        ledger = _read_ledger(path, expected_binding=_intent_binding(self))
        intents = ledger["intents"]
        if not isinstance(intents, dict):
            raise LiveTradingSafetyError("Order intent ledger is malformed; linked SELL is blocked.")
        record = intents.get(list_client_order_id)
        if not isinstance(record, Mapping):
            raise LiveTradingSafetyError("Linked Spot SELL requires one exact OPO list intent.")
        alias = spot_opo_cancel_client_id(new_order_client_id)
        _assert_unused_spot_client_ids(intents, (new_order_client_id, alias))
        build_spot_opo_cancel_replace_request(
            record, new_order_client_id=new_order_client_id, cancel_new_client_order_id=alias,
        )


def _begin_spot_opo_strategy_exit(
    self, list_client_order_id: str, *, new_order_client_id: str,
    pre_order_portfolio_signature: str, pre_order_portfolio_quantity: object,
    allocation_path: Path | None = None, expected_record: Mapping[str, object] | None = None,
) -> dict[str, object]:
    """Persist one original-stop SELL attempt after exact protection and allocation proof."""
    list_client_order_id = str(list_client_order_id or "").strip()
    record = _get_order_intent_record(self, list_client_order_id) if list_client_order_id else None
    if record is None or record.get("type") != "OPO":
        raise LiveTradingSafetyError("Linked Spot SELL requires one exact OPO list intent.")
    if expected_record is not None and record != expected_record:
        raise LiveTradingSafetyError("Spot OPO changed after linked SELL preflight.")
    if is_live_trading_mode(getattr(self, "mode", None)):
        if not _spot_owner_scope(self):
            raise LiveTradingSafetyError("Live linked Spot SELL requires the single-owner execution boundary.")
        _ensure_spot_execution_owner(self)
    retry = record.get("strategy_exit_state") == "no_effect" and record.get("cancel_state") == "rejected"
    if (
        record.get("state") != "accepted"
        or record.get("protection_state") != "active"
        or record.get("entry_reconciled") is not True
        or record.get("residual_stop_state") is not None
        or (not retry and (record.get("cancel_state") is not None or record.get("strategy_exit_state") is not None))
    ):
        raise LiveTradingSafetyError("Linked Spot SELL requires one active recovered stop with no prior exit attempt.")
    alias = spot_opo_cancel_client_id(new_order_client_id)
    request = build_spot_opo_cancel_replace_request(
        record, new_order_client_id=new_order_client_id, cancel_new_client_order_id=alias,
    )
    _check_spot_opo_strategy_exit_client_id(self, list_client_order_id, new_order_client_id=new_order_client_id)
    history = validate_spot_opo_exit_retry_history(record)
    if retry and len(history) >= EXIT_RETRY_HISTORY_LIMIT:
        raise LiveTradingSafetyError("Linked exit retry history limit reached; manual reconciliation is required.")
    try:
        baseline_quantity = Decimal(str(pre_order_portfolio_quantity))
        expected_quantity = Decimal(str(request["quantity"]))
    except (InvalidOperation, ValueError, TypeError):
        raise LiveTradingSafetyError("Linked Spot SELL requires an exact pre-order allocation baseline.") from None
    if (
        not isinstance(pre_order_portfolio_signature, str)
        or re.fullmatch(r"[0-9a-f]{64}", pre_order_portfolio_signature) is None
        or not baseline_quantity.is_finite() or baseline_quantity <= 0
        or baseline_quantity != expected_quantity
        or (
            retry and (
                pre_order_portfolio_signature != record.get("strategy_exit_pre_order_signature")
                or baseline_quantity != _finite_nonnegative_decimal(record.get("strategy_exit_pre_order_quantity"))
            )
        )
    ):
        raise LiveTradingSafetyError("Linked Spot SELL requires the unchanged sole exact OPO allocation baseline.")
    applied_records: list[dict[str, object]] = []
    observation = _reconcile_spot_opo_intent(
        self, list_client_order_id, force=True, applied_records=applied_records, expected_record=record,
    )
    if (
        observation.get("error") or len(applied_records) != 1
        or observation.get("protection_state") != "active"
        or observation.get("reconciled") is not True
        or _is_unresolved(applied_records[0])
    ):
        raise LiveTradingSafetyError("Linked Spot SELL requires fresh exact active-stop proof.")
    record = applied_records[0]
    if build_spot_opo_cancel_replace_request(
        record, new_order_client_id=new_order_client_id, cancel_new_client_order_id=alias,
    ) != request:
        raise LiveTradingSafetyError("Linked Spot SELL request changed during exact stop refresh.")
    if allocation_path is None:
        from app.gui.shared.allocation_persistence import get_position_allocations_path

        app_root = Path(__file__).resolve().parents[4]
        allocation_path = get_position_allocations_path(app_root / "gui" / "window_shell.py")
    from .spot_fill_recovery_runtime import spot_opo_allocation_baseline_unlocked

    submitted_at = _now()
    path = _intent_path(self)
    with ledger_transactions(path, allocation_path):
        ledger = _read_ledger(path, expected_binding=_intent_binding(self))
        intents = ledger.get("intents")
        if not isinstance(intents, dict):
            raise LiveTradingSafetyError("Order intent ledger is malformed; linked SELL is blocked.")
        current = intents.get(list_client_order_id)
        if not isinstance(current, dict) or current != record:
            raise LiveTradingSafetyError("Spot OPO changed before the linked SELL intent was persisted.")
        _assert_unused_spot_client_ids(intents, (new_order_client_id, alias))
        baseline = spot_opo_allocation_baseline_unlocked(
            allocation_path, symbol=str(record["symbol"]), list_client_order_id=list_client_order_id,
            expected_quantity=baseline_quantity,
        )
        if baseline["signature"] != pre_order_portfolio_signature or Decimal(baseline["quantity"]) != baseline_quantity:
            raise LiveTradingSafetyError("Live Spot allocation changed before linked SELL submission.")
        if retry:
            history.append(archive_spot_opo_no_effect_attempt(current))
        for name in list(current):
            if name.startswith("strategy_exit_"):
                del current[name]
        current.update({
            "updated_at": submitted_at,
            "cancel_state": "submitted",
            "cancel_submitted_at": submitted_at,
            "strategy_exit_state": "submitted",
            "strategy_exit_client_order_id": request["newClientOrderId"],
            "strategy_exit_quantity": request["quantity"],
            "strategy_exit_request": request,
            "strategy_exit_request_signature": _request_signature(request),
            "strategy_exit_pre_order_signature": pre_order_portfolio_signature,
            "strategy_exit_pre_order_quantity": format(baseline_quantity, "f"),
            "strategy_exit_started_at": submitted_at,
            "strategy_exit_history": history,
        })
        _write_ledger(path, ledger)
        updated = dict(current)
    return updated


def _mark_spot_opo_strategy_exit_unknown(
    self, list_client_order_id: str, *, error: object, expected_record: Mapping[str, object] | None = None,
) -> dict[str, object]:
    """Keep an interrupted cancel-replace attempt unresolved across restart."""
    list_client_order_id = str(list_client_order_id or "").strip()
    record = _get_order_intent_record(self, list_client_order_id) if list_client_order_id else None
    if (
        record is not None
        and ((expected_record is not None and record != expected_record)
             or (record.get("strategy_exit_history") and expected_record is None))
    ):
        raise LiveTradingSafetyError("Linked Spot SELL attempt changed; the late failure was not applied.")
    if (
        record is None or record.get("type") != "OPO"
        or record.get("strategy_exit_state") not in {"submitted", "unknown"}
        or record.get("strategy_exit_outcome") is not None
    ):
        raise LiveTradingSafetyError("Only an unclassified linked Spot SELL attempt can be marked unknown.")
    updated = _update_order_intent_by_id(
        self,
        list_client_order_id,
        state="unknown",
        expected_record=record,
        cancel_state="unknown",
        protection_state="unverified",
        strategy_exit_state="unknown",
        strategy_exit_last_error=redact_text(error)[:500] or "Cancel-replace outcome is uncertain.",
        strategy_exit_last_observed_at=_now(),
    )
    if updated is None:
        raise LiveTradingSafetyError("Spot OPO changed while preserving the uncertain linked SELL attempt.")
    return updated


def _mark_spot_opo_strategy_exit_response(
    self, list_client_order_id: str, *, response: object, expected_record: Mapping[str, object] | None = None,
) -> dict[str, object]:
    """Persist a validated cancel-replace outcome while keeping recovery unresolved."""
    list_client_order_id = str(list_client_order_id or "").strip()
    record = _get_order_intent_record(self, list_client_order_id) if list_client_order_id else None
    if (
        record is not None
        and ((expected_record is not None and record != expected_record)
             or (record.get("strategy_exit_history") and expected_record is None))
    ):
        raise LiveTradingSafetyError("Linked Spot SELL attempt changed; the late response was not applied.")
    if (
        record is None or record.get("type") != "OPO"
        or record.get("strategy_exit_state") not in {"submitted", "unknown"}
    ):
        raise LiveTradingSafetyError("Linked Spot SELL response has no unresolved durable intent.")
    request = validate_spot_opo_cancel_replace_request(record.get("strategy_exit_request"))
    try:
        evidence = validate_spot_opo_cancel_replace_response(response, request)
    except LiveTradingSafetyError as exc:
        updated = _update_order_intent_by_id(
            self,
            list_client_order_id,
            state="accepted",
            expected_record=record,
            cancel_state="unknown",
            protection_state="unverified",
            strategy_exit_state="unknown",
            strategy_exit_last_error=redact_text(exc)[:500],
            strategy_exit_last_observed_at=_now(),
        )
        if updated is None:
            raise LiveTradingSafetyError("Spot OPO changed while preserving an invalid SELL response; reconcile it.") from exc
        raise LiveTradingSafetyError("Linked Spot SELL response is unverified; exact reconciliation is required.") from exc

    outcome = str(evidence["outcome"])
    next_state = {
        "cancel_failed": "cancel_failed",
        "stop_canceled_exit_rejected": "stop_cancelled",
        "exit_sell_accepted": "sell_accepted",
    }[outcome]
    stop_already_confirmed = (
        record.get("cancel_state") == "confirmed"
        and record.get("protection_state") == "cancelled"
    )
    updates: dict[str, object] = {
        "strategy_exit_state": next_state,
        "strategy_exit_outcome": outcome,
        "strategy_exit_cancel_confirmed": evidence["cancel_confirmed"],
        "strategy_exit_new_order_accepted": evidence["new_order_accepted"],
        "strategy_exit_requires_exact_reconciliation": evidence["requires_exact_reconciliation"],
        "strategy_exit_requires_stop_rearm": evidence["requires_stop_rearm"],
        "strategy_exit_response_at": _now(),
        "cancel_state": "confirmed" if stop_already_confirmed else "unknown",
        "protection_state": "cancelled" if stop_already_confirmed else "unverified",
    }
    if evidence.get("new_order_id") is not None:
        updates.update({
            "strategy_exit_order_id": evidence["new_order_id"],
            "strategy_exit_status": evidence["new_order_status"],
            "strategy_exit_executed_qty": evidence["executed_qty"],
        })
    updated = _update_order_intent_by_id(
        self,
        list_client_order_id,
        state="accepted",
        expected_record=record,
        **updates,
    )
    if updated is None:
        raise LiveTradingSafetyError("Spot OPO changed while persisting the linked SELL outcome; reconcile it.")
    return {
        "client_order_id": list_client_order_id,
        **evidence,
        "strategy_exit_state": next_state,
        "portfolio_recovery_required": evidence["new_order_accepted"],
    }


def reconcile_spot_opo_strategy_exit(
    self, list_client_order_id: str, *, allocation_path: Path,
    expected_record: Mapping[str, object] | None = None, initial_order_response: object | None = None,
) -> dict[str, object]:
    """Classify a lost original-stop replacement reply using GETs only.

    Exact acceptance remains an inventory obligation until complete trade and
    fee-aware allocation recovery. No negative lookup permits another POST.
    """
    list_id = str(list_client_order_id or "").strip()
    record = _get_order_intent_record(self, list_id)
    if expected_record is not None and record != expected_record:
        raise LiveTradingSafetyError("Spot OPO changed before lost linked SELL recovery.")
    if (
        record is None or record.get("type") != "OPO" or record.get("market") != "spot"
        or record.get("entry_reconciled") is not True or record.get("residual_stop_state") is not None
        or record.get("strategy_exit_state") not in {"submitted", "unknown"}
        or record.get("strategy_exit_outcome") is not None
        or record.get("cancel_state") not in {"submitted", "unknown", "confirmed"}
    ):
        raise LiveTradingSafetyError("Lost linked SELL recovery requires one exact unresolved original-stop attempt.")
    request = validate_spot_opo_cancel_replace_request(record["strategy_exit_request"])
    first = (
        validate_spot_opo_strategy_exit_order(initial_order_response, request)
        if initial_order_response is not None else None
    )
    list_response, working, pending = _query_spot_opo_observation(self, record)
    if (
        list_response["listStatusType"] != "ALL_DONE" or list_response.get("listOrderStatus") != "ALL_DONE"
        or working["status"] != "FILLED"
        or Decimal(str(working["executedQty"])) != Decimal(str(record["quantity"]))
        or pending["status"] != "CANCELED" or Decimal(str(pending["executedQty"])) != 0
        or Decimal(str(pending["origQty"])) != Decimal(str(request["quantity"]))
    ):
        raise LiveTradingSafetyError("Lost linked SELL recovery lacks exact unexecuted canceled-stop proof.")
    getter = getattr(getattr(self, "client", None), "get_order", None)
    if not callable(getter):
        raise LiveTradingSafetyError("Exact lost linked SELL query transport is unavailable.")
    order = getter(symbol=request["symbol"], origClientOrderId=request["newClientOrderId"])
    evidence = validate_spot_opo_strategy_exit_order(order, request)
    if (
        evidence["order_id"] in {working["orderId"], pending["orderId"]}
        or (first is not None and (
            first["order_id"] != evidence["order_id"]
            or Decimal(str(evidence["executed_quantity"])) < Decimal(str(first["executed_quantity"]))
            or (first["terminal"] and first["status"] != evidence["status"])
        ))
    ):
        raise LiveTradingSafetyError("Lost linked SELL query changed identity or regressed execution/status.")
    from .spot_fill_recovery_runtime import spot_opo_allocation_baseline_unlocked

    observed_at = _now()
    path = _intent_path(self)
    with ledger_transactions(path, allocation_path):
        ledger = _read_ledger(path, expected_binding=_intent_binding(self))
        intents = ledger.get("intents")
        if not isinstance(intents, dict):
            raise LiveTradingSafetyError("Spot OPO intent ledger is malformed; lost linked SELL recovery is blocked.")
        current = intents.get(list_id)
        if not isinstance(current, dict) or current != record:
            raise LiveTradingSafetyError("Spot OPO changed during lost linked SELL recovery; late queries were not applied.")
        baseline = spot_opo_allocation_baseline_unlocked(
            allocation_path, symbol=str(request["symbol"]), list_client_order_id=list_id,
            expected_quantity=record["strategy_exit_pre_order_quantity"],
        )
        if (
            baseline["signature"] != record["strategy_exit_pre_order_signature"]
            or Decimal(baseline["quantity"]) != Decimal(str(request["quantity"]))
        ):
            raise LiveTradingSafetyError("Live Spot allocation changed before lost linked SELL classification.")
        pending_alias = str(pending["clientOrderId"])
        _assert_spot_opo_cancel_alias(intents, list_id, record, pending_alias)
        candidate = {
            **current, "state": "accepted", "updated_at": observed_at,
            "exchange_order_list_id": list_response["orderListId"], "list_status": "ALL_DONE",
            "working_order_id": working["orderId"], "working_status": "FILLED",
            "working_executed_qty": format(Decimal(str(working["executedQty"])), "f"),
            "pending_order_id": pending["orderId"], "pending_status": "CANCELED",
            "pending_original_qty": format(Decimal(str(pending["origQty"])), "f"),
            "pending_executed_qty": "0", "pending_observed_client_order_id": pending_alias,
            "protection_state": "cancelled", "cancel_state": "confirmed", "cancel_confirmed_at": observed_at,
            "last_reconciliation_at": observed_at,
            "strategy_exit_state": "sell_accepted", "strategy_exit_outcome": "exit_sell_accepted",
            "strategy_exit_outcome_source": "exact_query", "strategy_exit_cancel_confirmed": True,
            "strategy_exit_new_order_accepted": True, "strategy_exit_requires_exact_reconciliation": True,
            "strategy_exit_requires_stop_rearm": evidence["status"] != "FILLED",
            "strategy_exit_response_at": observed_at, "strategy_exit_order_id": evidence["order_id"],
            "strategy_exit_status": evidence["status"], "strategy_exit_executed_qty": evidence["executed_quantity"],
            "strategy_exit_order_observed_at": observed_at,
        }
        candidate["strategy_exit_query_proof"] = build_spot_opo_exit_query_proof(candidate, evidence, observed_at=observed_at)
        validate_spot_opo_exit_query_proof(candidate)
        intents[list_id] = candidate
        _write_ledger(path, ledger)
    return {"client_order_id": list_id, **evidence, "strategy_exit_state": "sell_accepted",
            "portfolio_recovery_required": True, "exchange_orders_placed": False}


def _mark_spot_opo_strategy_exit_order_observed(
    self, list_client_order_id: str, *, order_response: object,
    expected_record: Mapping[str, object] | None = None,
) -> dict[str, object]:
    """Persist an exact replacement-order query without resolving inventory."""
    list_client_order_id = str(list_client_order_id or "").strip()
    record = _get_order_intent_record(self, list_client_order_id) if list_client_order_id else None
    if record is not None and (
        (expected_record is not None and record != expected_record)
        or (expected_record is None and (record.get("strategy_exit_history") or record.get("strategy_exit_query_proof")))
    ):
        raise LiveTradingSafetyError("Linked SELL observation changed attempt; the late query was not applied.")
    if (
        record is None or record.get("type") != "OPO"
        or record.get("strategy_exit_state") != "sell_accepted"
        or record.get("strategy_exit_outcome") != "exit_sell_accepted"
        or record.get("protection_state") != "cancelled"
        or record.get("cancel_state") != "confirmed"
    ):
        raise LiveTradingSafetyError("Exact linked SELL query requires a confirmed canceled OPO stop.")
    try:
        request = validate_spot_opo_cancel_replace_request(record.get("strategy_exit_request"))
        evidence = validate_spot_opo_strategy_exit_order(order_response, request)
        previous_quantity = Decimal(str(record.get("strategy_exit_executed_qty")))
        observed_quantity = Decimal(str(evidence["executed_quantity"]))
    except (LiveTradingSafetyError, InvalidOperation, ValueError):
        raise LiveTradingSafetyError("Exact linked SELL query conflicts with the durable exit intent.") from None
    if (
        evidence["order_id"] != record.get("strategy_exit_order_id") or observed_quantity < previous_quantity
        or (record.get("strategy_exit_status") in {"FILLED", "CANCELED", "EXPIRED", "EXPIRED_IN_MATCH"}
            and evidence["status"] != record.get("strategy_exit_status"))
    ):
        raise LiveTradingSafetyError("Linked SELL execution regressed or changed order identity.")
    observed_at = _now()
    updated = _update_order_intent_by_id(
        self,
        list_client_order_id,
        state="accepted",
        expected_record=record,
        strategy_exit_order_id=evidence["order_id"],
        strategy_exit_status=evidence["status"],
        strategy_exit_executed_qty=evidence["executed_quantity"],
        strategy_exit_order_observed_at=observed_at,
        strategy_exit_requires_stop_rearm=evidence["status"] != "FILLED",
    )
    if updated is None:
        raise LiveTradingSafetyError("Spot OPO changed while recording its exact replacement SELL query.")
    return {"client_order_id": list_client_order_id, **evidence, "order_observed_at": observed_at}


def _mark_spot_opo_strategy_exit_reconciled(
    self, list_client_order_id: str, *, allocation_path: Path,
    portfolio_signature: str, portfolio_quantity: object,
    trade_ids: list[int], fill_time_ms: int,
) -> dict[str, object]:
    """Resolve a linked OPO only after its full SELL and exact local allocation proof."""
    list_client_order_id = str(list_client_order_id or "").strip()
    record = _get_order_intent_record(self, list_client_order_id) if list_client_order_id else None
    if (
        record is None or record.get("type") != "OPO"
        or record.get("strategy_exit_state") != "sell_accepted"
        or record.get("strategy_exit_status") != "FILLED"
        or record.get("strategy_exit_order_observed_at") is None
        or record.get("protection_state") != "cancelled"
        or record.get("cancel_state") != "confirmed"
        or record.get("entry_reconciled") is not True
    ):
        raise LiveTradingSafetyError("OPO strategy SELL recovery requires a fully filled exact replacement order.")
    try:
        quantity = Decimal(str(portfolio_quantity))
        expected = Decimal(str(record.get("entry_portfolio_quantity")))
    except (InvalidOperation, ValueError, TypeError):
        raise LiveTradingSafetyError("Linked OPO strategy SELL recovery quantity is invalid.") from None
    if (
        not isinstance(portfolio_signature, str)
        or re.fullmatch(r"[0-9a-f]{64}", portfolio_signature) is None
        or not quantity.is_finite() or quantity <= 0 or quantity != expected
        or type(fill_time_ms) is not int or fill_time_ms <= 0
        or not isinstance(trade_ids, list) or not trade_ids
        or any(type(item) is not int or item <= 0 for item in trade_ids)
        or len(trade_ids) != len(set(trade_ids))
        or str(record.get("strategy_exit_executed_qty")) != str(record.get("strategy_exit_quantity"))
    ):
        raise LiveTradingSafetyError("Linked OPO strategy SELL did not close its exact recovered inventory.")
    from .spot_fill_recovery_runtime import has_durable_spot_opo_strategy_sell

    candidate = dict(record)
    candidate["strategy_exit_trade_ids"] = list(trade_ids)
    if not has_durable_spot_opo_strategy_sell(
        allocation_path,
        candidate,
        signature=portfolio_signature,
        consumed_quantity=quantity,
    ):
        raise LiveTradingSafetyError("Matching durable OPO strategy SELL allocation proof was not found.")
    updated = _update_order_intent_by_id(
        self,
        list_client_order_id,
        state="accepted",
        expected_record=record,
        protection_state="closed",
        strategy_exit_state="completed",
        strategy_exit_portfolio_reconciled=True,
        strategy_exit_portfolio_signature=portfolio_signature,
        strategy_exit_portfolio_quantity=format(quantity, "f"),
        strategy_exit_trade_ids=list(trade_ids),
        strategy_exit_fill_time_ms=fill_time_ms,
        strategy_exit_reconciled_at=_now(),
    )
    if updated is None:
        raise LiveTradingSafetyError("Spot OPO changed while committing its full strategy SELL recovery proof.")
    return {"client_order_id": list_client_order_id, "portfolio_reconciled": True, "already_reconciled": False}


def _mark_spot_opo_strategy_exit_residual_required(
    self,
    list_client_order_id: str,
    *,
    allocation_path: Path,
    portfolio_signature: str,
    portfolio_quantity: object,
    no_fill: bool = False,
    no_trades_confirmed: bool = False,
    fill_signature: str | None = None,
    consumed_quantity: object | None = None,
    trade_ids: list[int] | None = None,
    fill_time_ms: int | None = None,
) -> dict[str, object]:
    """Persist exact terminal SELL recovery and the remaining allocation to protect."""
    from .spot_fill_recovery_runtime import (
        has_durable_spot_opo_strategy_sell_recovery,
        spot_opo_allocation_baseline,
    )

    list_client_order_id = str(list_client_order_id or "").strip()
    record = _get_order_intent_record(self, list_client_order_id) if list_client_order_id else None
    if (
        record is None or record.get("type") != "OPO"
        or record.get("state") != "accepted"
        or record.get("entry_reconciled") is not True
        or record.get("cancel_state") != "confirmed"
        or record.get("protection_state") != "cancelled"
        or record.get("residual_stop_state") not in {None, "rearm_required"}
        or record.get("strategy_exit_state") not in {"sell_accepted", "stop_cancelled"}
    ):
        raise LiveTradingSafetyError("Residual protection requires one confirmed canceled OPO stop and terminal linked SELL.")
    try:
        residual_quantity = Decimal(str(portfolio_quantity))
        entry_quantity = Decimal(str(record.get("entry_portfolio_quantity")))
        pre_order_quantity = Decimal(str(record.get("strategy_exit_pre_order_quantity")))
    except (InvalidOperation, ValueError, TypeError):
        raise LiveTradingSafetyError("Residual OPO allocation quantity is invalid.") from None
    if (
        not isinstance(portfolio_signature, str)
        or re.fullmatch(r"[0-9a-f]{64}", portfolio_signature) is None
        or not residual_quantity.is_finite() or residual_quantity <= 0
        or not entry_quantity.is_finite()
        or (residual_quantity > entry_quantity if no_fill else residual_quantity >= entry_quantity)
        or not pre_order_quantity.is_finite() or pre_order_quantity != entry_quantity
    ):
        raise LiveTradingSafetyError("Residual OPO allocation must be positive, smaller than entry, and exactly recovered.")
    if no_fill:
        rejected_before_order = (
            record.get("strategy_exit_state") == "stop_cancelled"
            and record.get("strategy_exit_outcome") == "stop_canceled_exit_rejected"
            and record.get("strategy_exit_new_order_accepted") is False
        )
        terminal_zero_fill = (
            record.get("strategy_exit_state") == "sell_accepted"
            and record.get("strategy_exit_outcome") == "exit_sell_accepted"
            and record.get("strategy_exit_status") in {"CANCELED", "EXPIRED", "EXPIRED_IN_MATCH"}
            and Decimal(str(record.get("strategy_exit_executed_qty") or "NaN")) == 0
            and no_trades_confirmed is True
        )
        if (
            not (rejected_before_order or terminal_zero_fill)
            or portfolio_signature != record.get("strategy_exit_pre_order_signature")
            or residual_quantity != entry_quantity
        ):
            raise LiveTradingSafetyError("No-fill protection recovery conflicts with the exact cancel-replace result.")
        no_fill_evidence = {
            "request": record.get("strategy_exit_request"),
            "order_id": record.get("strategy_exit_order_id") if terminal_zero_fill else None,
            "status": record.get("strategy_exit_status") if terminal_zero_fill else "REJECTED",
            "outcome": record.get("strategy_exit_outcome"),
            "trade_ids": [],
        }
        fill_signature = hashlib.sha256(
            json.dumps(no_fill_evidence, sort_keys=True, separators=(",", ":")).encode("utf-8")
        ).hexdigest()
    else:
        try:
            consumed = Decimal(str(consumed_quantity))
        except (InvalidOperation, ValueError, TypeError):
            raise LiveTradingSafetyError("Recovered linked SELL consumed quantity is invalid.") from None
        if (
            record.get("strategy_exit_state") != "sell_accepted"
            or record.get("strategy_exit_outcome") != "exit_sell_accepted"
            or record.get("strategy_exit_status") not in {"FILLED", "CANCELED", "EXPIRED", "EXPIRED_IN_MATCH"}
            or not consumed.is_finite() or consumed <= 0
            or consumed + residual_quantity != entry_quantity
            or type(fill_time_ms) is not int or fill_time_ms <= 0
            or not isinstance(trade_ids, list) or not trade_ids
            or any(type(item) is not int or item <= 0 for item in trade_ids)
            or len(trade_ids) != len(set(trade_ids))
            or not isinstance(fill_signature, str)
            or re.fullmatch(r"[0-9a-f]{64}", fill_signature) is None
            or not has_durable_spot_opo_strategy_sell_recovery(
                allocation_path,
                record,
                signature=fill_signature,
                consumed_quantity=consumed,
                remaining_quantity=residual_quantity,
                trade_ids=trade_ids,
            )
        ):
            raise LiveTradingSafetyError("Partial linked SELL is missing exact durable trade and allocation proof.")
    baseline = spot_opo_allocation_baseline(
        allocation_path,
        symbol=str(record.get("symbol") or ""),
        list_client_order_id=list_client_order_id,
        expected_quantity=residual_quantity,
    )
    if (
        baseline.get("signature") != portfolio_signature
        or baseline.get("quantity") != _decimal_text(residual_quantity)
    ):
        raise LiveTradingSafetyError("Current Live Spot allocation differs from the residual protection baseline.")
    updates: dict[str, object] = {
        "residual_stop_state": "rearm_required",
        "residual_rearm_signature": portfolio_signature,
        "residual_rearm_quantity": _decimal_text(residual_quantity),
        "residual_rearm_required_at": _now(),
        "residual_rearm_no_fill": no_fill,
    }
    if not no_fill:
        updates.update({
            "strategy_exit_fill_signature": fill_signature,
            "strategy_exit_fill_quantity": format(consumed, "f"),
            "strategy_exit_fill_trade_ids": list(trade_ids or []),
            "strategy_exit_fill_time_ms": fill_time_ms,
        })
    else:
        updates.update({
            "strategy_exit_fill_signature": fill_signature,
            "strategy_exit_fill_quantity": "0",
            "strategy_exit_fill_trade_ids": [],
            "strategy_exit_fill_time_ms": int(datetime.now(timezone.utc).timestamp() * 1000),
            "strategy_exit_fill_no_fill": True,
        })
    updated = _update_order_intent_by_id(
        self, list_client_order_id, state="accepted", expected_record=record, **updates,
    )
    if updated is None:
        raise LiveTradingSafetyError("Spot OPO changed while persisting its residual protection requirement.")
    return {
        "client_order_id": list_client_order_id,
        "residual_rearm_required": True,
        "portfolio_signature": portfolio_signature,
        "portfolio_quantity": format(residual_quantity, "f"),
    }


def _begin_spot_opo_residual_stop(
    self,
    list_client_order_id: str,
    *,
    allocation_path: Path,
    request: object,
    pre_order_portfolio_signature: str,
    pre_order_portfolio_quantity: object,
) -> dict[str, object]:
    """Durably record a unique re-arm request before its single signed POST."""
    list_client_order_id = str(list_client_order_id or "").strip()
    record = _get_order_intent_record(self, list_client_order_id) if list_client_order_id else None
    if (
        record is None or record.get("type") != "OPO"
        or record.get("state") != "accepted"
        or record.get("entry_reconciled") is not True
        or record.get("cancel_state") != "confirmed"
        or record.get("protection_state") != "cancelled"
        or record.get("residual_stop_state") != "rearm_required"
    ):
        raise LiveTradingSafetyError("Residual stop submission requires an exact re-arm-required OPO allocation.")
    normalized = validate_spot_opo_residual_stop_request(request)
    original = validate_spot_opo_request_payload(record.get("request"))
    try:
        quantity = Decimal(str(pre_order_portfolio_quantity))
        expected = Decimal(str(record.get("residual_rearm_quantity")))
    except (InvalidOperation, ValueError, TypeError):
        raise LiveTradingSafetyError("Residual stop submission requires an exact current allocation baseline.") from None
    if (
        normalized["symbol"] != record.get("symbol")
        or normalized["stopPrice"] != original["pendingStopPrice"]
        or Decimal(normalized["quantity"]) != quantity
        or quantity != expected
        or not isinstance(pre_order_portfolio_signature, str)
        or pre_order_portfolio_signature != record.get("residual_rearm_signature")
        or re.fullmatch(r"[0-9a-f]{64}", pre_order_portfolio_signature) is None
    ):
        raise LiveTradingSafetyError("Residual stop request does not exactly cover the recovered OPO remainder.")
    from .spot_fill_recovery_runtime import spot_opo_allocation_baseline

    baseline = spot_opo_allocation_baseline(
        allocation_path,
        symbol=str(record.get("symbol") or ""),
        list_client_order_id=list_client_order_id,
        expected_quantity=quantity,
    )
    if (
        baseline.get("signature") != pre_order_portfolio_signature
        or Decimal(str(baseline.get("quantity"))) != quantity
    ):
        raise LiveTradingSafetyError("Live Spot allocation changed before residual-stop submission.")
    path = _intent_path(self)
    started_at = _now()
    with ledger_transaction(path):
        ledger = _read_ledger(path, expected_binding=_intent_binding(self))
        intents = ledger.get("intents")
        if not isinstance(intents, dict):
            raise LiveTradingSafetyError("Order intent ledger is malformed; residual protection is blocked.")
        current = intents.get(list_client_order_id)
        if not isinstance(current, dict) or current != record:
            raise LiveTradingSafetyError("Spot OPO changed before residual-stop intent persistence.")
        used_ids = used_spot_client_order_ids(intents)
        if normalized["newClientOrderId"] in used_ids:
            raise LiveTradingSafetyError("Residual stop client order ID was already used in this Spot ledger.")
        history = list(current.get("residual_stop_history", []))
        if current.get("residual_stop_request") is not None:
            prior = {
                "request": current.get("residual_stop_request"),
                "request_signature": current.get("residual_stop_request_signature"),
                "pre_order_signature": current.get("residual_stop_pre_order_signature"),
                "pre_order_quantity": current.get("residual_stop_pre_order_quantity"),
                "started_at": current.get("residual_stop_started_at"),
                "state": current.get("residual_stop_terminal_state"),
                "order_id": current.get("residual_stop_order_id"),
                "status": current.get("residual_stop_status"),
                "executed_qty": current.get("residual_stop_executed_qty"),
                "observed_at": current.get("residual_stop_observed_at"),
                "recovery_signature": current.get("residual_stop_recovery_signature"),
                "recovery_quantity": current.get("residual_stop_recovery_quantity"),
                "trade_ids": current.get("residual_stop_recovery_trade_ids", []),
            }
            if prior["state"] not in {"recovered", "completed"}:
                raise LiveTradingSafetyError("Prior residual stop has not been exactly recovered; new order is blocked.")
            if len(history) >= 100:
                raise LiveTradingSafetyError("Residual stop recovery history limit reached; manual reconciliation is required.")
            history.append(prior)
        for field in (
            "residual_stop_order_id", "residual_stop_status", "residual_stop_executed_qty",
            "residual_stop_observed_at", "residual_stop_query_verified",
            "residual_stop_terminal_state", "residual_stop_recovered",
            "residual_stop_recovery_signature", "residual_stop_recovery_quantity",
            "residual_stop_recovery_trade_ids", "residual_stop_recovery_fill_time_ms",
            "residual_stop_last_error", "residual_stop_last_observed_at", "residual_stop_reconciled_at",
        ):
            current.pop(field, None)
        current.update({
            "updated_at": started_at,
            "residual_stop_state": "submitted",
            "residual_stop_request": normalized,
            "residual_stop_request_signature": _request_signature(normalized),
            "residual_stop_pre_order_signature": pre_order_portfolio_signature,
            "residual_stop_pre_order_quantity": _decimal_text(quantity),
            "residual_stop_started_at": started_at,
            "residual_stop_history": history,
        })
        _write_ledger(path, ledger)
        return dict(current)


def _mark_spot_opo_residual_stop_unknown(
    self, list_client_order_id: str, *, error: object,
) -> dict[str, object]:
    list_client_order_id = str(list_client_order_id or "").strip()
    record = _get_order_intent_record(self, list_client_order_id) if list_client_order_id else None
    if record is None or record.get("residual_stop_state") not in {"submitted", "unknown"}:
        raise LiveTradingSafetyError("Only an unclassified residual STOP_LOSS submission can be marked uncertain.")
    updated = _update_order_intent_by_id(
        self,
        list_client_order_id,
        state="accepted",
        expected_record=record,
        residual_stop_state="unknown",
        residual_stop_last_error=redact_text(error)[:500] or "Residual stop submission result is uncertain.",
        residual_stop_last_observed_at=_now(),
    )
    if updated is None:
        raise LiveTradingSafetyError("Spot OPO changed while preserving the uncertain residual-stop submission.")
    return updated


def _mark_spot_opo_residual_stop_order_observed(
    self, list_client_order_id: str, *, order_response: object, exact_query: bool = False,
    expected_record: Mapping[str, object] | None = None,
    applied_records: list[dict[str, object]] | None = None,
) -> dict[str, object]:
    list_client_order_id = str(list_client_order_id or "").strip()
    record = _get_order_intent_record(self, list_client_order_id) if list_client_order_id else None
    if expected_record is not None and record != expected_record:
        raise LiveTradingSafetyError("Spot OPO changed while querying its residual stop; the late result was not applied.")
    if record is None or record.get("residual_stop_state") not in {
        "submitted", "unknown", "acknowledged", "active", "triggered",
    }:
        raise LiveTradingSafetyError("Residual stop query has no durable outstanding OPO intent.")
    try:
        request = validate_spot_opo_residual_stop_request(record.get("residual_stop_request"))
        evidence = validate_spot_opo_residual_stop_order(order_response, request)
        previous_order_id = record.get("residual_stop_order_id")
        previous_executed = Decimal(str(record.get("residual_stop_executed_qty") or "0"))
        previous_status = record.get("residual_stop_status")
    except (LiveTradingSafetyError, InvalidOperation, ValueError):
        raise LiveTradingSafetyError("Exact residual stop query conflicts with its durable request.") from None
    if (
        (previous_order_id is not None and previous_order_id != evidence["order_id"])
        or Decimal(str(evidence["executed_quantity"])) < previous_executed
        or (
            previous_status in {"FILLED", "CANCELED", "EXPIRED", "EXPIRED_IN_MATCH"}
            and evidence["status"] != previous_status
        )
    ):
        raise LiveTradingSafetyError("Residual stop query changed identity or regressed execution or terminal status.")
    observed_at = _now()
    next_state = (
        ("active" if evidence["status"] == "NEW" else "triggered")
        if exact_query is True else "acknowledged"
    )
    updated = _update_order_intent_by_id(
        self,
        list_client_order_id,
        state="accepted",
        expected_record=record,
        residual_stop_state=next_state,
        residual_stop_order_id=evidence["order_id"],
        residual_stop_status=evidence["status"],
        residual_stop_executed_qty=evidence["executed_quantity"],
        residual_stop_observed_at=observed_at,
        residual_stop_query_verified=exact_query is True,
    )
    if updated is None:
        raise LiveTradingSafetyError("Spot OPO changed while recording the exact residual stop query.")
    if applied_records is not None and exact_query is True:
        applied_records.append(updated)
    return {"client_order_id": list_client_order_id, **evidence, "observed_at": observed_at}


def _mark_spot_opo_residual_stop_reconciled(
    self,
    list_client_order_id: str,
    *,
    allocation_path: Path,
    fill_signature: str,
    consumed_quantity: object,
    remaining_quantity: object,
    trade_ids: list[int],
    fill_time_ms: int,
) -> dict[str, object]:
    """Commit exact trades after a re-armed STOP_LOSS fills or terminates partially."""
    from .spot_fill_recovery_runtime import (
        has_durable_spot_opo_residual_stop_allocation,
        spot_opo_allocation_baseline,
    )

    list_client_order_id = str(list_client_order_id or "").strip()
    record = _get_order_intent_record(self, list_client_order_id) if list_client_order_id else None
    if (
        record is None or record.get("type") != "OPO"
        or record.get("residual_stop_state") != "triggered"
        or record.get("residual_stop_query_verified") is not True
        or record.get("entry_reconciled") is not True
        or record.get("cancel_state") != "confirmed"
        or record.get("protection_state") != "cancelled"
    ):
        raise LiveTradingSafetyError("Residual stop fill recovery requires one exact triggered OPO stop.")
    request = validate_spot_opo_residual_stop_request(record.get("residual_stop_request"))
    try:
        consumed = Decimal(str(consumed_quantity))
        remaining = Decimal(str(remaining_quantity))
        stop_quantity = Decimal(str(record.get("residual_stop_pre_order_quantity")))
        requested = Decimal(request["quantity"])
    except (InvalidOperation, ValueError, TypeError, AttributeError):
        raise LiveTradingSafetyError("Residual stop fill quantities are invalid.") from None
    if (
        not isinstance(fill_signature, str)
        or re.fullmatch(r"[0-9a-f]{64}", fill_signature) is None
        or not consumed.is_finite() or consumed <= 0 or consumed > stop_quantity
        or not remaining.is_finite() or remaining < 0
        or consumed + remaining != stop_quantity
        or requested != stop_quantity
        or type(fill_time_ms) is not int or fill_time_ms <= 0
        or not isinstance(trade_ids, list) or not trade_ids
        or any(type(item) is not int or item <= 0 for item in trade_ids)
        or len(trade_ids) != len(set(trade_ids))
        or (record.get("residual_stop_status") == "FILLED" and remaining != 0)
        or not has_durable_spot_opo_residual_stop_allocation(
            allocation_path,
            record,
            signature=fill_signature,
            consumed_quantity=consumed,
            remaining_quantity=remaining,
            trade_ids=trade_ids,
        )
    ):
        raise LiveTradingSafetyError("Residual stop trades do not match the exact OPO inventory proof.")
    if remaining > 0:
        baseline = spot_opo_allocation_baseline(
            allocation_path,
            symbol=str(record.get("symbol") or ""),
            list_client_order_id=list_client_order_id,
            expected_quantity=remaining,
        )
        state = "rearm_required"
        protection_state = "cancelled"
        residual_signature = baseline["signature"]
        residual_quantity = baseline["quantity"]
        terminal_state = "recovered"
    else:
        state = "completed"
        protection_state = "closed"
        residual_signature = str(record.get("residual_stop_pre_order_signature") or "")
        residual_quantity = str(record.get("residual_stop_pre_order_quantity") or "")
        terminal_state = "completed"
    updated = _update_order_intent_by_id(
        self,
        list_client_order_id,
        state="accepted",
        expected_record=record,
        protection_state=protection_state,
        residual_stop_state=state,
        residual_rearm_signature=residual_signature,
        residual_rearm_quantity=residual_quantity,
        residual_stop_terminal_state=terminal_state,
        residual_stop_recovered=True,
        residual_stop_recovery_signature=fill_signature,
        residual_stop_recovery_quantity=_decimal_text(consumed),
        residual_stop_recovery_trade_ids=list(trade_ids),
        residual_stop_recovery_fill_time_ms=fill_time_ms,
        residual_stop_reconciled_at=_now(),
    )
    if updated is None:
        raise LiveTradingSafetyError("Spot OPO changed while committing residual-stop recovery proof.")
    return {
        "client_order_id": list_client_order_id,
        "portfolio_reconciled": True,
        "residual_quantity": residual_quantity,
        "residual_rearm_required": remaining > 0,
        "completed": remaining == 0,
    }


def _mark_spot_opo_residual_stop_no_fill(
    self,
    list_client_order_id: str,
    *,
    allocation_path: Path,
    no_trades_confirmed: bool,
) -> dict[str, object]:
    """Record a terminal zero-fill stop and preserve the unchanged remainder for re-arm."""
    from .spot_fill_recovery_runtime import spot_opo_allocation_baseline

    list_client_order_id = str(list_client_order_id or "").strip()
    record = _get_order_intent_record(self, list_client_order_id) if list_client_order_id else None
    if (
        record is None or record.get("type") != "OPO"
        or record.get("residual_stop_state") != "triggered"
        or record.get("residual_stop_status") not in {"CANCELED", "EXPIRED", "EXPIRED_IN_MATCH"}
        or record.get("residual_stop_query_verified") is not True
        or no_trades_confirmed is not True
    ):
        raise LiveTradingSafetyError("Zero-fill residual recovery requires an exact terminal order and empty trade history.")
    try:
        quantity = Decimal(str(record.get("residual_stop_pre_order_quantity")))
        executed = Decimal(str(record.get("residual_stop_executed_qty") or "NaN"))
    except (InvalidOperation, ValueError, TypeError):
        raise LiveTradingSafetyError("Zero-fill residual order quantity is invalid.") from None
    if executed != 0:
        raise LiveTradingSafetyError("Zero-fill residual recovery requires an exact zero execution quantity.")
    baseline = spot_opo_allocation_baseline(
        allocation_path,
        symbol=str(record.get("symbol") or ""),
        list_client_order_id=list_client_order_id,
        expected_quantity=quantity,
    )
    if (
        baseline.get("signature") != record.get("residual_stop_pre_order_signature")
        or Decimal(str(baseline.get("quantity"))) != quantity
    ):
        raise LiveTradingSafetyError("OPO allocation changed during zero-fill residual stop recovery.")
    proof_payload = {
        "request": record.get("residual_stop_request"),
        "order_id": record.get("residual_stop_order_id"),
        "status": record.get("residual_stop_status"),
        "executed_qty": "0",
        "trade_ids": [],
    }
    proof_signature = hashlib.sha256(
        json.dumps(proof_payload, sort_keys=True, separators=(",", ":")).encode("utf-8")
    ).hexdigest()
    updated = _update_order_intent_by_id(
        self,
        list_client_order_id,
        state="accepted",
        expected_record=record,
        residual_stop_state="rearm_required",
        residual_stop_terminal_state="recovered",
        residual_stop_recovered=True,
        residual_stop_recovery_signature=proof_signature,
        residual_stop_recovery_quantity="0",
        residual_stop_recovery_trade_ids=[],
        residual_stop_reconciled_at=_now(),
        residual_rearm_signature=baseline["signature"],
        residual_rearm_quantity=baseline["quantity"],
    )
    if updated is None:
        raise LiveTradingSafetyError("Spot OPO changed while persisting zero-fill residual recovery.")
    return {
        "client_order_id": list_client_order_id,
        "portfolio_reconciled": True,
        "residual_quantity": baseline["quantity"],
        "residual_rearm_required": True,
        "no_fill": True,
    }


def _update_order_intent(self, params: Mapping[str, object], *, state: str, **updates: object) -> None:
    client_order_id = _client_order_id(params)
    path = _intent_path(self)
    with ledger_transaction(path):
        ledger = _read_ledger(path, expected_binding=_intent_binding(self))
        intents = ledger["intents"]
        if not isinstance(intents, dict):
            raise LiveTradingSafetyError("Order intent ledger is malformed; reconcile it before submitting orders.")
        record = intents.get(client_order_id)
        if not isinstance(record, dict):
            raise LiveTradingSafetyError("Order intent record is missing; submission is blocked pending reconciliation.")
        record["state"] = state
        record["updated_at"] = _now()
        record.update({key: value for key, value in updates.items() if value not in (None, "")})
        _write_ledger(path, ledger)


def _mark_order_intent_submitted(self, params: Mapping[str, object], *, via: str) -> None:
    client_order_id = _client_order_id(params)
    record = _get_order_intent_record(self, client_order_id)
    if record is not None and record.get("market") == "spot" and record.get("side") == "BUY":
        if record.get("state") != "pending":
            raise LiveTradingSafetyError("Spot BUY intent is not in a submittable state.")
        _submit_spot_buy_intent(self, record, via=via)
        return
    _update_order_intent(self, params, state="submitted", last_via=str(via), submitted_at=_now())


def _mark_order_intent_accepted(self, params: Mapping[str, object], *, via: str, result: object) -> None:
    client_order_id = _client_order_id(params)
    record = _get_order_intent_record(self, client_order_id)
    if record is None:
        raise LiveTradingSafetyError("Order intent record is missing; confirmation is blocked.")
    execution_updates: dict[str, object] = {}
    try:
        state, status, order_id = _validate_reconciliation_response(record, result)
        if _requires_execution_confirmation(record):
            assert isinstance(result, Mapping)
            execution_updates["executed_qty"] = str(result["executedQty"])
            if record.get("market") == "spot" and record.get("side") == "BUY" and status == "FILLED":
                try:
                    base_asset, quote_asset = self.get_base_quote_assets(str(record["symbol"]))
                    from .spot_fill_recovery_runtime import summarize_primary_spot_buy

                    primary_fill = summarize_primary_spot_buy(
                        result,
                        symbol=str(record["symbol"]),
                        client_order_id=str(record["client_order_id"]),
                        base_asset=base_asset,
                        quote_asset=quote_asset,
                    )
                    execution_updates["portfolio_qty"] = str(primary_fill["net_qty"])
                    execution_updates["primary_fill_signature"] = str(primary_fill["signature"])
                    from .spot_allocation_generation_runtime import canonical_spot_buy_metadata
                    execution_updates["primary_fill_receipt"] = canonical_spot_buy_metadata(primary_fill)
                except Exception:
                    # Without a complete commission-aware fill proof, the
                    # accepted Spot market order remains unresolved.
                    pass
            if record.get("market") == "spot" and status in {
                "CANCELED", "EXPIRED", "EXPIRED_IN_MATCH", "REJECTED",
            }:
                raise LiveTradingSafetyError("Spot market acknowledgement is terminal; reconciliation is required.")
        elif state != "accepted" or status in {"CANCELED", "EXPIRED", "EXPIRED_IN_MATCH"}:
            raise LiveTradingSafetyError("Order response does not confirm an accepted submission.")
    except (TypeError, ValueError, LiveTradingSafetyError) as exc:
        _update_order_intent_by_id(
            self, client_order_id, state="unknown", expected_record=record,
            last_error=redact_text(exc), uncertain_at=_now(),
        )
        raise LiveTradingSafetyError("Order response conflicts with its persisted intent; reconciliation required.") from exc
    updated = _update_order_intent_by_id(
        self, client_order_id, state=state, expected_record=record,
        last_via=str(via), exchange_order_id=order_id, exchange_status=status,
        accepted_at=_now(), **execution_updates,
    )
    if updated is None:
        raise LiveTradingSafetyError("Order intent changed during confirmation; reconciliation required.")


def _mark_order_intent_unknown(self, params: Mapping[str, object], *, error: object) -> None:
    _update_order_intent(self, params, state="unknown", last_error=str(error or ""), uncertain_at=_now())


def _has_durable_spot_buy_allocation(
    record: Mapping[str, object], *, portfolio_signature: str, portfolio_quantity: object,
) -> bool:
    try:
        if re.fullmatch(r"[0-9a-f]{64}", portfolio_signature) is None:
            return False
        from app.gui.shared.allocation_persistence import get_position_allocations_path

        app_root = Path(__file__).resolve().parents[4]
        path = get_position_allocations_path(app_root / "gui" / "window_shell.py")
        if path.is_symlink() or not path.is_file():
            return False

        def unique_object(pairs):
            value = {}
            for key, item in pairs:
                if key in value:
                    raise ValueError("duplicate allocation field")
                value[key] = item
            return value

        data = json.loads(path.read_text(encoding="utf-8"), object_pairs_hook=unique_object)
        if (
            not isinstance(data, dict)
            or data.get("version") != 1
            or data.get("mode") != "Live"
            or not isinstance(data.get("entry_allocations"), dict)
        ):
            return False
        matches = []
        for entries in data["entry_allocations"].values():
            if not isinstance(entries, list):
                return False
            for entry in entries:
                if not isinstance(entry, dict):
                    return False
                if entry.get("client_order_id") == record.get("client_order_id"):
                    matches.append(entry)
        if len(matches) != 1:
            return False
        entry = matches[0]
        fill_evidence = entry.get("spot_fill_recovery")
        if not isinstance(fill_evidence, Mapping):
            return False
        from .spot_allocation_generation_runtime import spot_buy_generation_receipt
        acquisition = spot_buy_generation_receipt(entry)
        if "primary_fill_receipt" in record:
            from .spot_allocation_generation_runtime import canonical_spot_buy_metadata
            original = canonical_spot_buy_metadata({
                **fill_evidence, "symbol": entry.get("symbol"), "client_order_id": entry.get("client_order_id"),
            })
            if original != record["primary_fill_receipt"]:
                return False
        expected_quantity = Decimal(str(portfolio_quantity or record.get("portfolio_qty") or "NaN"))
        if record.get("type") == "OPO":
            request = validate_spot_opo_request_payload(record.get("request"))
            expected_exchange_client_id = request["workingClientOrderId"]
            expected_order_id = record.get("working_order_id")
            expected_pending_quantity = _finite_nonnegative_decimal(record.get("pending_original_qty"))
        else:
            expected_exchange_client_id = str(record.get("client_order_id") or "")
            expected_order_id = record.get("exchange_order_id")
            expected_pending_quantity = None
        return (
            entry.get("symbol") == record.get("symbol")
            and entry.get("side_key") == "L"
            and acquisition.client_order_id == record.get("client_order_id")
            and isinstance(fill_evidence, Mapping)
            and fill_evidence.get("signature") == portfolio_signature
            and fill_evidence.get("exchange_client_order_id", entry.get("client_order_id"))
            == expected_exchange_client_id
            and str(entry.get("order_id") or "") == str(expected_order_id or "")
            and (
                expected_pending_quantity is None
                or _finite_nonnegative_decimal(fill_evidence.get("pending_order_qty")) == expected_pending_quantity
            )
            and acquisition.signature == portfolio_signature
            and acquisition.exchange_client_order_id == expected_exchange_client_id
            and str(acquisition.order_id) == str(expected_order_id)
            and expected_quantity.is_finite()
            and acquisition.acquisition_qty == expected_quantity
        )
    except SPOT_LOCAL_STATE_ERRORS:
        return False


def _has_durable_spot_sell_allocation(
    record: Mapping[str, object], *, portfolio_signature: str, portfolio_quantity: object,
) -> bool:
    try:
        if re.fullmatch(r"[0-9a-f]{64}", portfolio_signature) is None:
            return False
        from app.gui.shared.allocation_persistence import get_position_allocations_path

        app_root = Path(__file__).resolve().parents[4]
        path = get_position_allocations_path(app_root / "gui" / "window_shell.py")
        if path.is_symlink() or not path.is_file():
            return False

        def unique_object(pairs):
            value = {}
            for key, item in pairs:
                if key in value:
                    raise ValueError("duplicate allocation field")
                value[key] = item
            return value

        data = json.loads(path.read_text(encoding="utf-8"), object_pairs_hook=unique_object)
        allocations = data.get("entry_allocations") if isinstance(data, dict) else None
        if data.get("version") != 1 or data.get("mode") != "Live" or not isinstance(allocations, dict):
            return False
        expected_quantity = Decimal(str(portfolio_quantity or record.get("portfolio_qty") or "NaN"))
        executed_quantity = Decimal(str(record.get("executed_qty") or "NaN"))
        baseline_quantity = Decimal(str(record.get("portfolio_pre_order_qty") or "NaN"))
        baseline_signature = record.get("portfolio_pre_order_signature")
        if (
            not expected_quantity.is_finite() or expected_quantity <= 0
            or not executed_quantity.is_finite() or executed_quantity <= 0
            or not baseline_quantity.is_finite() or baseline_quantity <= 0
            or not isinstance(baseline_signature, str)
            or re.fullmatch(r"[0-9a-f]{64}", baseline_signature) is None
        ):
            return False
        matched_quantity = Decimal(0)
        matched_proceeds = Decimal(0)
        total_net_proceeds: Decimal | None = None
        matched_rows = 0
        for rows in allocations.values():
            if not isinstance(rows, list):
                return False
            for row in rows:
                if not isinstance(row, dict):
                    return False
                proofs = row.get("spot_sell_recoveries", [])
                if not isinstance(proofs, list):
                    return False
                for proof in proofs:
                    if not isinstance(proof, Mapping):
                        return False
                    if (
                        proof.get("client_order_id") != record.get("client_order_id")
                        or proof.get("signature") != portfolio_signature
                    ):
                        continue
                    if (
                        type(proof.get("version")) is not int
                        or proof.get("version") != 1
                        or row.get("symbol") != record.get("symbol")
                        or row.get("side_key") != "L"
                        or proof.get("pre_order_portfolio_signature") != baseline_signature
                        or type(proof.get("order_id")) is not int
                        or proof["order_id"] <= 0
                        or str(proof.get("order_id")) != str(record.get("exchange_order_id"))
                        or not isinstance(proof.get("trade_ids"), list)
                        or not proof.get("trade_ids")
                        or any(type(item) is not int or item <= 0 for item in proof["trade_ids"])
                        or type(proof.get("fill_time_ms")) is not int
                        or proof["fill_time_ms"] <= 0
                    ):
                        return False
                    quantity = Decimal(str(proof.get("consumed_qty") or "NaN"))
                    gross_quantity = Decimal(str(proof.get("gross_qty") or "NaN"))
                    portfolio_quantity = Decimal(str(proof.get("portfolio_qty") or "NaN"))
                    proof_baseline_quantity = Decimal(str(proof.get("pre_order_portfolio_qty") or "NaN"))
                    base_fee_quantity = Decimal(str(proof.get("base_fee_qty") or "NaN"))
                    gross_quote_quantity = Decimal(str(proof.get("gross_quote_qty") or "NaN"))
                    quote_fee_quantity = Decimal(str(proof.get("quote_fee_qty") or "NaN"))
                    row_proceeds = Decimal(str(proof.get("net_quote_proceeds") or "NaN"))
                    proof_total_proceeds = Decimal(str(proof.get("total_net_quote_proceeds") or "NaN"))
                    if (
                        not quantity.is_finite() or quantity <= 0
                        or not gross_quantity.is_finite() or gross_quantity != executed_quantity
                        or not portfolio_quantity.is_finite()
                        or not proof_baseline_quantity.is_finite()
                        or proof_baseline_quantity != baseline_quantity
                        or not base_fee_quantity.is_finite() or base_fee_quantity < 0
                        or portfolio_quantity != gross_quantity + base_fee_quantity
                        or not gross_quote_quantity.is_finite() or gross_quote_quantity <= 0
                        or not quote_fee_quantity.is_finite() or quote_fee_quantity < 0
                        or not row_proceeds.is_finite() or row_proceeds <= 0
                        or not proof_total_proceeds.is_finite() or proof_total_proceeds <= 0
                        or proof_total_proceeds != gross_quote_quantity - quote_fee_quantity
                        or (total_net_proceeds is not None and total_net_proceeds != proof_total_proceeds)
                    ):
                        return False
                    matched_quantity += quantity
                    matched_proceeds += row_proceeds
                    total_net_proceeds = proof_total_proceeds
                    matched_rows += 1
        return (
            matched_rows > 0
            and matched_quantity == expected_quantity
            and total_net_proceeds is not None
            and matched_proceeds == total_net_proceeds
        )
    except SPOT_LOCAL_STATE_ERRORS:
        return False


def _commit_spot_buy_acquisition_receipt(
    self, record: Mapping[str, object], *, portfolio_signature: str, portfolio_quantity: Decimal, opo: bool = False,
) -> dict[str, object]:
    """Confirm acquisition history under both locks; never treat it as inventory."""
    from app.gui.shared.allocation_persistence import get_position_allocations_path
    app_root = Path(__file__).resolve().parents[4]
    allocation_path = get_position_allocations_path(app_root / "gui" / "window_shell.py")
    path = _intent_path(self)
    flag = "entry_reconciled" if opo else "portfolio_reconciled"
    signature_field = "entry_recovery_signature" if opo else "portfolio_recovery_signature"
    quantity_field = "entry_portfolio_quantity" if opo else "portfolio_qty"
    with ledger_transactions(path, allocation_path):
        ledger = _read_ledger(path, expected_binding=_intent_binding(self))
        intents = ledger["intents"]
        current = intents.get(str(record["client_order_id"])) if isinstance(intents, dict) else None
        if not isinstance(current, dict) or current != record:
            raise LiveTradingSafetyError("Spot BUY intent changed during acquisition confirmation.")
        if not _has_durable_spot_buy_allocation(
            current, portfolio_signature=portfolio_signature, portfolio_quantity=portfolio_quantity,
        ):
            raise LiveTradingSafetyError("Matching durable Spot BUY acquisition history is no longer present.")
        already = current.get(flag) is True
        if already:
            if current.get(signature_field) != portfolio_signature or Decimal(str(current.get(quantity_field))) != portfolio_quantity:
                raise LiveTradingSafetyError("Spot BUY acquisition receipt conflicts with its intent.")
        else:
            current.update({
                "state": "accepted", flag: True, quantity_field: format(portfolio_quantity, "f"),
                signature_field: portfolio_signature,
                "entry_reconciled_at" if opo else "portfolio_reconciled_at": _now(), "updated_at": _now(),
            })
            _write_ledger(path, ledger)
    return {"client_order_id": str(record["client_order_id"]), flag: True, "already_reconciled": already}


def _mark_order_intent_portfolio_reconciled(
    self, client_order_id: str, *, portfolio_signature: str, portfolio_quantity: object = None,
) -> dict[str, object]:
    client_order_id = str(client_order_id or "").strip()
    record = _get_order_intent_record(self, client_order_id) if client_order_id else None
    if record is None:
        raise LiveTradingSafetyError("Spot portfolio recovery intent was not found.")
    if (
        record.get("market") != "spot"
        or record.get("type") != "MARKET"
        or record.get("side") not in {"BUY", "SELL"}
        or record.get("exchange_status") not in _ORDER_STATUSES - {"NEW", "PARTIALLY_FILLED"}
    ):
        raise LiveTradingSafetyError("Only a terminal Spot market BUY or SELL can be marked portfolio-reconciled.")
    if record.get("portfolio_reconciled") is True:
        if (
            record.get("portfolio_recovery_signature") != portfolio_signature
            or str(record.get("portfolio_qty")) != str(portfolio_quantity or record.get("portfolio_qty"))
        ):
            raise LiveTradingSafetyError("Spot portfolio recovery proof conflicts with the stored intent.")
        if record.get("side") == "BUY":
            return _commit_spot_buy_acquisition_receipt(
                self, record, portfolio_signature=portfolio_signature,
                portfolio_quantity=Decimal(str(portfolio_quantity or record.get("portfolio_qty"))),
            )
        return {"client_order_id": client_order_id, "portfolio_reconciled": True, "already_reconciled": True}
    try:
        expected_quantity = Decimal(str(portfolio_quantity or record.get("portfolio_qty") or "NaN"))
        executed_quantity = Decimal(str(record.get("executed_qty") or "NaN"))
    except (InvalidOperation, ValueError):
        expected_quantity = Decimal("NaN")
        executed_quantity = Decimal("NaN")
    if (
        not expected_quantity.is_finite() or expected_quantity <= 0
        or not executed_quantity.is_finite() or executed_quantity <= 0
        or (record.get("side") == "BUY" and expected_quantity > executed_quantity)
        or (record.get("side") == "SELL" and expected_quantity < executed_quantity)
    ):
        raise LiveTradingSafetyError("Spot portfolio recovery quantity is invalid.")
    if (
        record.get("side") == "BUY"
        and record.get("primary_fill_signature")
        and record["primary_fill_signature"] != portfolio_signature
    ):
        raise LiveTradingSafetyError("Spot portfolio recovery proof conflicts with the primary fill evidence.")
    if record.get("side") == "BUY":
        return _commit_spot_buy_acquisition_receipt(
            self, record, portfolio_signature=portfolio_signature, portfolio_quantity=expected_quantity,
        )
    has_durable_proof = (
        _has_durable_spot_buy_allocation(
            record, portfolio_signature=portfolio_signature, portfolio_quantity=expected_quantity,
        )
        if record.get("side") == "BUY"
        else _has_durable_spot_sell_allocation(
            record, portfolio_signature=portfolio_signature, portfolio_quantity=expected_quantity,
        )
    )
    if not has_durable_proof:
        raise LiveTradingSafetyError("A matching durable Live Spot portfolio recovery proof was not found.")
    updated = _update_order_intent_by_id(
        self,
        client_order_id,
        state="accepted",
        expected_record=record,
        portfolio_reconciled=True,
        portfolio_qty=format(expected_quantity, "f"),
        portfolio_recovery_signature=portfolio_signature,
        portfolio_reconciled_at=_now(),
    )
    if updated is None:
        raise LiveTradingSafetyError("Spot order intent changed during portfolio recovery; reconciliation is required.")
    return {"client_order_id": client_order_id, "portfolio_reconciled": True, "already_reconciled": False}


def _mark_spot_opo_entry_reconciled(
    self, list_client_order_id: str, *, portfolio_signature: str, portfolio_quantity: object,
) -> dict[str, object]:
    list_client_order_id = str(list_client_order_id or "").strip()
    record = _get_order_intent_record(self, list_client_order_id) if list_client_order_id else None
    if record is None or record.get("type") != "OPO":
        raise LiveTradingSafetyError("Spot OPO entry recovery intent was not found.")
    if (
        record.get("market") != "spot"
        or record.get("side") != "BUY"
        or record.get("state") not in {"accepted", "unknown"}
        or (record.get("protection_state") not in {"active", "triggered", "lost", "unverified"}
            and not (record.get("protection_state") == "closed" and record.get("entry_reconciled") is True))
        or record.get("list_status") not in {"EXEC_STARTED", "ALL_DONE"}
        or record.get("working_status") != "FILLED"
    ):
        raise LiveTradingSafetyError("OPO entry recovery requires an exact filled working BUY child.")
    try:
        request = validate_spot_opo_request_payload(record.get("request"))
        expected_quantity = Decimal(str(portfolio_quantity))
        working_quantity = Decimal(request["workingQuantity"])
        pending_quantity = Decimal(str(record.get("pending_original_qty") or "NaN"))
    except (InvalidOperation, ValueError):
        raise LiveTradingSafetyError("Spot OPO entry recovery quantity is invalid.") from None
    if (
        not expected_quantity.is_finite() or expected_quantity <= 0
        or expected_quantity > working_quantity
        or not pending_quantity.is_finite() or pending_quantity <= 0
        or pending_quantity != expected_quantity
        or not isinstance(portfolio_signature, str)
        or re.fullmatch(r"[0-9a-f]{64}", portfolio_signature) is None
    ):
        raise LiveTradingSafetyError(
            "Spot OPO stop quantity does not exactly cover the recovered BUY inventory; manual reconciliation is required."
        )
    return _commit_spot_buy_acquisition_receipt(
        self, record, portfolio_signature=portfolio_signature, portfolio_quantity=expected_quantity, opo=True,
    )


def _mark_spot_opo_exit_reconciled(
    self, list_client_order_id: str, *, portfolio_signature: str, portfolio_quantity: object,
) -> dict[str, object]:
    list_client_order_id = str(list_client_order_id or "").strip()
    record = _get_order_intent_record(self, list_client_order_id) if list_client_order_id else None
    if record is None or record.get("type") != "OPO":
        raise LiveTradingSafetyError("Spot OPO stop exit recovery intent was not found.")
    if (
        record.get("market") != "spot"
        or record.get("side") != "BUY"
        or record.get("state") not in {"accepted", "unknown"}
        or record.get("protection_state") != "triggered"
        or record.get("list_status") != "ALL_DONE"
        or record.get("working_status") != "FILLED"
        or record.get("pending_status") != "FILLED"
        or record.get("entry_reconciled") is not True
        or record.get("strategy_exit_state") not in (None, "no_effect")
    ):
        raise LiveTradingSafetyError("OPO stop exit recovery requires a triggered stop with durable entry proof.")
    try:
        request = validate_spot_opo_request_payload(record.get("request"))
        expected_quantity = Decimal(str(portfolio_quantity))
        entry_quantity = Decimal(str(record.get("entry_portfolio_quantity") or "NaN"))
        pending_quantity = Decimal(str(record.get("pending_original_qty") or "NaN"))
    except (InvalidOperation, ValueError):
        raise LiveTradingSafetyError("Spot OPO stop exit recovery quantity is invalid.") from None
    if (
        not expected_quantity.is_finite() or expected_quantity <= 0
        or not entry_quantity.is_finite() or entry_quantity <= 0
        or not pending_quantity.is_finite() or pending_quantity <= 0
        or expected_quantity != entry_quantity or pending_quantity != entry_quantity
        or not isinstance(portfolio_signature, str)
        or re.fullmatch(r"[0-9a-f]{64}", portfolio_signature) is None
        or record.get("pending_order_id") is None
        or request["listClientOrderId"] != list_client_order_id
    ):
        raise LiveTradingSafetyError("OPO stop exit quantity does not exactly close its recovered BUY allocation.")
    from .spot_fill_recovery_runtime import has_durable_spot_opo_stop_exit

    if not has_durable_spot_opo_stop_exit(
        record, signature=portfolio_signature, portfolio_quantity=expected_quantity,
    ):
        raise LiveTradingSafetyError("A matching durable OPO stop SELL allocation proof was not found.")
    if record.get("exit_reconciled") is True:
        if (
            record.get("exit_recovery_signature") != portfolio_signature
            or str(record.get("exit_portfolio_quantity")) != format(expected_quantity, "f")
            or record.get("exit_order_id") != record.get("pending_order_id")
        ):
            raise LiveTradingSafetyError("Spot OPO stop exit proof conflicts with the stored intent.")
        return {"client_order_id": list_client_order_id, "exit_reconciled": True, "already_reconciled": True}
    updated = _update_order_intent_by_id(
        self,
        list_client_order_id,
        state="accepted",
        expected_record=record,
        exit_reconciled=True,
        exit_portfolio_quantity=format(expected_quantity, "f"),
        exit_recovery_signature=portfolio_signature,
        exit_order_id=record["pending_order_id"],
        exit_reconciled_at=_now(),
    )
    if updated is None:
        raise LiveTradingSafetyError("Spot OPO intent changed during stop exit recovery; reconciliation is required.")
    return {"client_order_id": list_client_order_id, "exit_reconciled": True, "already_reconciled": False}


def _get_order_intent_record(self, client_order_id: str) -> dict[str, object] | None:
    path = _intent_path(self)
    with ledger_transaction(path):
        ledger = _read_ledger(path, expected_binding=_intent_binding(self))
        intents = ledger.get("intents")
        record = intents.get(client_order_id) if isinstance(intents, dict) else None
        return dict(record) if isinstance(record, Mapping) else None


def _assert_spot_opo_cancel_alias(
    intents: Mapping[str, object], list_id: str, record: Mapping[str, object], alias: str,
    *, owners: Mapping[str, set[str]] | None = None,
) -> None:
    """Reserve a queried cancellation alias without waiving archived ID collisions."""
    request = validate_spot_opo_cancel_replace_request(record.get("strategy_exit_request"))
    prior_alias = record.get("pending_observed_client_order_id")
    if prior_alias is not None and prior_alias != alias:
        raise LiveTradingSafetyError("Canceled OPO client identity changed from its durable observation.")
    if owners is None:
        others = {key: value for key, value in intents.items() if key != list_id}
        _assert_unused_spot_client_ids(others, (alias,))
    elif owners.get(alias, set()) - {list_id}:
        raise LiveTradingSafetyError("Canceled OPO alias conflicts with another durable Spot intent.")
    own = dict(record)
    own.pop("pending_observed_client_order_id", None)
    if alias not in {request["cancelOrigClientOrderId"], request.get("cancelNewClientOrderId")}:
        if alias in used_spot_client_order_ids({list_id: own}):
            raise LiveTradingSafetyError("Canceled OPO alias conflicts with a current or archived attempt ID.")


def _validate_spot_opo_cancel_alias_ownership(intents: Mapping[str, object]) -> None:
    """Check cross-intent cancellation aliases with one linear ownership index."""
    records = {
        key: value for key, value in intents.items()
        if isinstance(value, Mapping) and isinstance(value.get("pending_observed_client_order_id"), str)
    }
    if not records:
        return
    owners: dict[str, set[str]] = {}
    for key, record in intents.items():
        for client_id in used_spot_client_order_ids({key: record}):
            owners.setdefault(client_id, set()).add(key)
    validate_order_intent_global_ownership(records, owners=owners)


def validate_order_intent_global_ownership(
    alias_records: Mapping[str, Mapping[str, object]], *, owners: Mapping[str, set[str]],
) -> None:
    """Validate aliases against a caller-proved complete ownership projection.

    The caller must supply every alias-bearing record and every owner of every
    current or historical client ID, with local records already validated. This
    helper does not establish projection completeness or snapshot consistency.
    """
    for key, record in alias_records.items():
        _assert_spot_opo_cancel_alias(
            alias_records, key, record, str(record["pending_observed_client_order_id"]), owners=owners,
        )


def _update_order_intent_by_id(
    self, client_order_id: str, *, state: str,
    expected_record: Mapping[str, object] | None = None, **updates: object,
) -> dict[str, object] | None:
    path = _intent_path(self)
    with ledger_transaction(path):
        ledger = _read_ledger(path, expected_binding=_intent_binding(self))
        intents = ledger.get("intents")
        if not isinstance(intents, dict):
            raise LiveTradingSafetyError("Order intent ledger is malformed; reconcile it before submitting orders.")
        record = intents.get(client_order_id)
        if not isinstance(record, dict):
            raise LiveTradingSafetyError("Order intent record is missing; reconciliation cannot update it.")
        # The exchange query runs outside the file lock; never overwrite a newer observation.
        if expected_record is not None and record != expected_record:
            return None
        alias = updates.get("pending_observed_client_order_id")
        if isinstance(alias, str):
            _assert_spot_opo_cancel_alias(intents, client_order_id, record, alias)
        record["state"] = state
        record["updated_at"] = _now()
        record.update({key: value for key, value in updates.items() if value not in (None, "")})
        _write_ledger(path, ledger)
        return dict(record)


def _query_order_intent_exchange(self, record: Mapping[str, object]) -> object:
    """Return an exchange response for one persisted client order ID.

    No missing-order response is treated as proof that the request did not reach
    Binance. That ambiguity must remain blocked until an affirmative response
    or a deliberate operator reconciliation is available.
    """
    symbol = str(record.get("symbol") or "").strip().upper()
    client_order_id = str(record.get("client_order_id") or "").strip()
    market = str(record.get("market") or "").strip().lower()
    if not symbol or not client_order_id:
        raise LiveTradingSafetyError("Order intent is missing its symbol or client order ID.")
    if market == "futures":
        request = getattr(self, "_http_signed_futures_request", None)
        prefix = getattr(self, "_futures_api_prefix", None)
        if not callable(request) or not callable(prefix):
            raise LiveTradingSafetyError("Futures order reconciliation transport is unavailable.")
        return request(
            "GET",
            "/v1/order",
            {"symbol": symbol, "origClientOrderId": client_order_id},
            prefix=prefix(),
        )
    if market == "spot":
        client = getattr(self, "client", None)
        getter = getattr(client, "get_order", None)
        if not callable(getter):
            raise LiveTradingSafetyError("Spot order reconciliation transport is unavailable.")
        return getter(symbol=symbol, origClientOrderId=client_order_id)
    raise LiveTradingSafetyError(f"Order intent has unsupported market {market!r}.")


def _exchange_order_id(result: Mapping[str, object]) -> str:
    value = result.get("orderId")
    if type(value) is int and value > 0:
        return str(value)
    if isinstance(value, str) and value.isascii() and value.isdigit() and int(value) > 0:
        return value
    return ""


def _finite_nonnegative_decimal(value: object) -> Decimal | None:
    if not isinstance(value, str):
        return None
    try:
        amount = Decimal(value)
    except (InvalidOperation, ValueError):
        return None
    return amount if amount.is_finite() and amount >= 0 else None


def _validate_reconciliation_response(
    record: Mapping[str, object], result: object, *, require_portfolio_reconciliation: bool = False,
) -> tuple[str, str, str]:
    if (not isinstance(result, Mapping) or "code" in result or result.get("error") is not None
            or ("success" in result and result["success"] is not True)):
        raise LiveTradingSafetyError("Exchange returned an invalid order response.")
    status = result.get("status")
    if not isinstance(status, str) or not status.strip():
        raise LiveTradingSafetyError("Exchange did not provide an explicit order status.")
    status = status.strip().upper()
    market = record.get("market")
    allowed = _ORDER_STATUSES | (_SPOT_PENDING_STATUSES if market == "spot" else set())
    if market not in ("spot", "futures") or status not in allowed:
        raise LiveTradingSafetyError("Exchange returned an unsupported order status or market.")
    if result.get("clientOrderId") != record.get("client_order_id"):
        raise LiveTradingSafetyError("Exchange response does not identify the requested client order.")
    symbol = result.get("symbol")
    if not isinstance(symbol, str) or symbol.strip().upper() != record.get("symbol"):
        raise LiveTradingSafetyError("Exchange response does not identify the requested symbol.")
    order_id = _exchange_order_id(result)
    if not order_id:
        raise LiveTradingSafetyError("Exchange response is missing a valid exchange order ID.")
    previous_id = record.get("exchange_order_id")
    if previous_id and str(previous_id) != order_id:
        raise LiveTradingSafetyError("Exchange order ID changed during reconciliation.")
    primary_receipt = record.get("primary_fill_receipt")
    if "primary_fill_receipt" in record:
        # A terminal primary acquisition cannot become a different execution
        # merely because an exact-ID GET returned contradictory order fields.
        if (not isinstance(primary_receipt, Mapping)
                or status != "FILLED" or result.get("side") != "BUY" or result.get("type") != "MARKET"
                or result.get("clientOrderId") != primary_receipt.get("exchange_client_order_id")
                or order_id != str(primary_receipt.get("order_id"))):
            raise LiveTradingSafetyError("Exchange response conflicts with the retained terminal Spot acquisition.")
        gross_quantity = _finite_nonnegative_decimal(result.get("executedQty"))
        retained_quantity = _finite_nonnegative_decimal(primary_receipt.get("gross_qty"))
        if gross_quantity is None or retained_quantity is None or gross_quantity != retained_quantity:
            raise LiveTradingSafetyError("Exchange execution changed from the retained Spot acquisition.")
        if ("cummulativeQuoteQty" in result
                and _finite_nonnegative_decimal(result["cummulativeQuoteQty"])
                != _finite_nonnegative_decimal(primary_receipt.get("gross_quote_qty"))):
            raise LiveTradingSafetyError("Exchange quote total changed from the retained Spot acquisition.")
        # GET creation/update timestamps do not replace the primary acquisition time.
    if _requires_execution_confirmation(record):
        expected_params = {
            "newClientOrderId": record.get("client_order_id"), "symbol": record.get("symbol"),
            "side": record.get("side"), "positionSide": record.get("position_side", "BOTH"),
        }
        execution = order_execution_from_response(result, record.get("quantity"), expected_params=expected_params)
        if expected_params["positionSide"] in {"LONG", "SHORT"} and result.get("positionSide") != expected_params["positionSide"]:
            raise LiveTradingSafetyError("Exchange response does not identify the requested hedge leg.")
        previous_qty = record.get("executed_qty")
        if previous_qty is not None and Decimal(str(result["executedQty"])) < Decimal(str(previous_qty)):
            raise LiveTradingSafetyError("Order execution quantity regressed during reconciliation.")
        if execution.status in {"NEW", "PARTIALLY_FILLED"}:
            return "unknown", status, order_id
        if (require_portfolio_reconciliation and market == "spot" and record.get("type") == "MARKET"
                and execution.executed_qty > 0):
            # An exact order query proves exchange execution, not that the
            # desktop portfolio recorded the fill before a crash. Keep every
            # positive Spot market fill unresolved until inventory recovery exists.
            return "unknown", status, order_id
    if status == "REJECTED":
        executed = result.get("executedQty")
        try:
            quantity = Decimal(executed) if isinstance(executed, str) else Decimal("NaN")
        except InvalidOperation:
            quantity = Decimal("NaN")
        if not quantity.is_finite() or quantity != 0:
            raise LiveTradingSafetyError("Rejected order response does not confirm zero execution.")
        return "rejected", status, order_id
    # Canceled/expired orders may have fills. Retain their ID as a submitted intent.
    return "accepted", status, order_id


def _query_spot_opo_observation(
    self, record: Mapping[str, object],
) -> tuple[dict[str, object], dict[str, object], dict[str, object]]:
    request_value = record.get("request")
    request = validate_spot_opo_request_payload(request_value)
    client = getattr(self, "client", None)
    list_getter = getattr(client, "get_order_list", None)
    order_getter = getattr(client, "get_order", None)
    if not callable(list_getter) or not callable(order_getter):
        raise LiveTradingSafetyError("Spot OPO list reconciliation transport is unavailable.")
    response = list_getter(origClientOrderId=request["listClientOrderId"])
    if (
        not isinstance(response, Mapping)
        or "code" in response
        or response.get("error") is not None
        or response.get("symbol") != request["symbol"]
        or response.get("listClientOrderId") != request["listClientOrderId"]
        or response.get("contingencyType") != "OTO"
        or type(response.get("orderListId")) is not int
        or response["orderListId"] < 0
        or response.get("listStatusType") not in {"EXEC_STARTED", "ALL_DONE"}
        or ("listOrderStatus" in response and response.get("listOrderStatus") != (
            "EXECUTING" if response.get("listStatusType") == "EXEC_STARTED" else "ALL_DONE"
        ))
    ):
        raise LiveTradingSafetyError("Binance Spot OPO list response conflicts with its durable intent.")
    list_id = cast(int, response["orderListId"])
    orders = response.get("orders")
    if not isinstance(orders, list) or len(orders) != 2:
        raise LiveTradingSafetyError("Binance Spot OPO list response must identify exactly two child orders.")
    expected_ids = {
        request["workingClientOrderId"],
        request["pendingClientOrderId"],
    }
    exit_request_value = record.get("strategy_exit_request")
    exit_request = (
        validate_spot_opo_cancel_replace_request(exit_request_value)
        if isinstance(exit_request_value, Mapping) else None
    )
    cancellation_lookup = (
        exit_request is not None and response["listStatusType"] == "ALL_DONE"
        and record.get("strategy_exit_state") not in {"cancel_failed", "no_effect"}
        and exit_request["cancelOrderId"] == record.get("pending_order_id")
    )
    if cancellation_lookup and response.get("listOrderStatus") != "ALL_DONE":
        raise LiveTradingSafetyError("Canceled OPO list lacks exact terminal order-list status.")
    list_orders: dict[str, dict[str, object]] = {}
    for row in orders:
        row_key = row.get("clientOrderId") if isinstance(row, Mapping) else None
        if (
            cancellation_lookup and isinstance(row, Mapping)
            and row.get("orderId") == record.get("pending_order_id")
        ):
            row_key = request["pendingClientOrderId"]
        if (
            not isinstance(row, Mapping)
            or row.get("symbol") != request["symbol"]
            or row_key not in expected_ids
            or row_key in list_orders
            or not isinstance(row.get("clientOrderId"), str)
            or re.fullmatch(r"[A-Za-z0-9._:/-]{1,36}", str(row.get("clientOrderId"))) is None
            or type(row.get("orderId")) is not int
            or row["orderId"] <= 0
        ):
            raise LiveTradingSafetyError("Binance Spot OPO list child identity is invalid.")
        list_orders[str(row_key)] = dict(row)
    if set(list_orders) != expected_ids:
        raise LiveTradingSafetyError("Binance Spot OPO list response omitted an expected child order.")

    child_responses: dict[str, dict[str, object]] = {}
    for child_id, expected_type, expected_side in (
        (request["workingClientOrderId"], "LIMIT", "BUY"),
        (request["pendingClientOrderId"], "STOP_LOSS", "SELL"),
    ):
        exact_pending = cancellation_lookup and child_id == request["pendingClientOrderId"]
        child = (
            order_getter(symbol=request["symbol"], orderId=record["pending_order_id"])
            if exact_pending else order_getter(symbol=request["symbol"], origClientOrderId=child_id)
        )
        observed_alias = child.get("clientOrderId") if isinstance(child, Mapping) else None
        valid_identity = observed_alias == child_id
        if exact_pending and isinstance(child, Mapping) and child.get("status") == "CANCELED":
            list_client_id = list_orders[child_id]["clientOrderId"]
            expected_alias = exit_request.get("cancelNewClientOrderId") if exit_request is not None else None
            prior_alias = record.get("pending_observed_client_order_id")
            valid_identity = (
                isinstance(observed_alias, str)
                and re.fullmatch(r"[A-Za-z0-9._:/-]{1,36}", observed_alias) is not None
                and observed_alias not in {request["listClientOrderId"], request["workingClientOrderId"],
                                          exit_request.get("newClientOrderId") if exit_request is not None else None}
                and (expected_alias is None or observed_alias == expected_alias)
                and (prior_alias is None or observed_alias == prior_alias)
                and list_client_id in {child_id, observed_alias}
            )
        if (
            not isinstance(child, Mapping)
            or "code" in child
            or child.get("error") is not None
            or child.get("symbol") != request["symbol"]
            or not valid_identity
            or type(child.get("orderId")) is not int
            or child.get("orderId") != list_orders[child_id]["orderId"]
            or type(child.get("orderListId")) is not int
            or child.get("orderListId") != list_id
            or child.get("type") != expected_type
            or child.get("side") != expected_side
            or not isinstance(child.get("status"), str)
            or child.get("status") not in _ORDER_STATUSES | _SPOT_PENDING_STATUSES
        ):
            raise LiveTradingSafetyError("Binance Spot OPO child query conflicts with its list identity.")
        child_responses[child_id] = dict(child)

    working = child_responses[request["workingClientOrderId"]]
    pending = child_responses[request["pendingClientOrderId"]]
    working_executed = _finite_nonnegative_decimal(working.get("executedQty"))
    working_original = _finite_nonnegative_decimal(working.get("origQty"))
    pending_executed = _finite_nonnegative_decimal(pending.get("executedQty"))
    pending_original = _finite_nonnegative_decimal(pending.get("origQty"))
    if (
        working.get("timeInForce") != "FOK"
        or working_executed is None
        or working_original is None
        or pending_executed is None
        or pending_original is None
    ):
        raise LiveTradingSafetyError("Binance Spot OPO child execution fields are missing or invalid.")
    try:
        requested_quantity = Decimal(request["workingQuantity"])
        requested_stop_price = Decimal(request["pendingStopPrice"])
        observed_stop_price = Decimal(str(pending.get("stopPrice")))
    except (InvalidOperation, ValueError):
        raise LiveTradingSafetyError("Binance Spot OPO stop or working quantity is invalid.") from None
    if (
        not observed_stop_price.is_finite()
        or observed_stop_price != requested_stop_price
        or working_original != requested_quantity
    ):
        raise LiveTradingSafetyError("Binance Spot OPO child price or quantity differs from the request.")
    if (
        record.get("exchange_order_list_id") is not None
        and record["exchange_order_list_id"] != list_id
    ):
        raise LiveTradingSafetyError("Binance Spot OPO list ID changed from its durable observation.")
    if record.get("list_status") == "ALL_DONE" and response["listStatusType"] != "ALL_DONE":
        raise LiveTradingSafetyError("Binance Spot OPO terminal list status regressed.")
    for prefix, child, executed, original in (
        ("working", working, working_executed, working_original),
        ("pending", pending, pending_executed, pending_original),
    ):
        prior_order_id = record.get(f"{prefix}_order_id")
        prior_status = record.get(f"{prefix}_status")
        prior_executed = _finite_nonnegative_decimal(record.get(f"{prefix}_executed_qty"))
        if prior_order_id is not None and child["orderId"] != prior_order_id:
            raise LiveTradingSafetyError("Binance Spot OPO child order ID changed from its durable observation.")
        if (
            prior_status in _ORDER_STATUSES - {"NEW", "PARTIALLY_FILLED"}
            and child["status"] != prior_status
        ):
            raise LiveTradingSafetyError("Binance Spot OPO terminal child status changed.")
        if prior_executed is not None and executed < prior_executed:
            raise LiveTradingSafetyError("Binance Spot OPO child executed quantity decreased.")
        if (
            executed > original
            or (child["status"] in {"NEW", "PENDING_NEW"} and executed != 0)
            or (child["status"] == "NEW" and original <= 0)
            or (child["status"] == "FILLED" and (original <= 0 or executed != original))
        ):
            raise LiveTradingSafetyError("Binance Spot OPO child status conflicts with its execution quantities.")
    prior_pending_original = _finite_nonnegative_decimal(record.get("pending_original_qty"))
    if (
        (prior_pending_original is not None and prior_pending_original > 0 and pending_original != prior_pending_original)
        or (
            record.get("entry_reconciled") is True
            and pending_original != _finite_nonnegative_decimal(record.get("entry_portfolio_quantity"))
        )
    ):
        raise LiveTradingSafetyError("Binance Spot OPO stop quantity changed from its durable entry observation.")
    return dict(response), working, pending


def _reconcile_spot_opo_residual_stop(
    self, record: Mapping[str, object], *, applied_records: list[dict[str, object]] | None = None,
) -> dict[str, object]:
    """Refresh the current standalone stop; exact order proof never implies portfolio recovery."""
    list_client_order_id = str(record["client_order_id"])
    try:
        request = validate_spot_opo_residual_stop_request(record.get("residual_stop_request"))
        getter = getattr(getattr(self, "client", None), "get_order", None)
        if not callable(getter):
            raise LiveTradingSafetyError("Residual STOP_LOSS query transport is unavailable.")
        response = getter(symbol=request["symbol"], origClientOrderId=request["newClientOrderId"])
        observed = _mark_spot_opo_residual_stop_order_observed(
            self, list_client_order_id, order_response=response, exact_query=True,
            expected_record=record, applied_records=applied_records,
        )
    except SPOT_EXCHANGE_ERRORS as exc:
        error = redact_text(exc)[:500] or "Residual STOP_LOSS reconciliation failed."
        # Keep the last order ID and execution quantity for monotonic checks.
        # An old NEW observation is no longer verified after a failed refresh.
        updates: dict[str, object] = {
            "residual_stop_last_error": error, "residual_stop_last_observed_at": _now(),
        }
        if record.get("residual_stop_state") in {"active", "acknowledged"}:
            updates.update(residual_stop_state="acknowledged", residual_stop_query_verified=False)
        updated = _update_order_intent_by_id(
            self, list_client_order_id, state="accepted", expected_record=record, **updates,
        )
        if updated is None:
            updated = _get_order_intent_record(self, list_client_order_id)
            error = "Spot OPO changed during residual-stop refresh; the late result was not applied."
        return {
            "client_order_id": list_client_order_id, "state": "accepted", "reconciled": False,
            "protection_state": record.get("protection_state"), "error": error,
            "residual_stop_state": (updated or record).get("residual_stop_state"),
        }
    return {
        "client_order_id": list_client_order_id, "state": "accepted",
        "reconciled": observed["status"] == "NEW",
        "protection_state": record.get("protection_state"),
        "residual_stop_state": "active" if observed["status"] == "NEW" else "triggered",
        "residual_stop_status": observed["status"],
    }


def _reconcile_spot_opo_intent(
    self, list_client_order_id: str, *, force: bool = False,
    applied_records: list[dict[str, object]] | None = None,
    expected_record: Mapping[str, object] | None = None,
) -> dict[str, object]:
    """Reconcile an OPO list and both child orders without treating protection as inventory proof."""
    list_client_order_id = str(list_client_order_id or "").strip()
    if not list_client_order_id:
        raise LiveTradingSafetyError("Order-list client ID is required for Spot OPO reconciliation.")
    record = _get_order_intent_record(self, list_client_order_id)
    if record is None or record.get("type") != "OPO":
        raise LiveTradingSafetyError(f"Spot OPO intent {list_client_order_id} was not found in the local ledger.")
    if expected_record is not None and record != expected_record:
        raise LiveTradingSafetyError("Spot OPO changed before its exact linked-stop refresh.")
    if record.get("residual_stop_state") in {"submitted", "unknown", "acknowledged", "active", "triggered"}:
        return _reconcile_spot_opo_residual_stop(self, record, applied_records=applied_records)
    if record.get("residual_stop_state") == "completed":
        return {
            "client_order_id": list_client_order_id, "state": "accepted", "reconciled": True,
            "protection_state": "closed", "residual_stop_state": "completed",
        }
    if record.get("state") == "accepted" and record.get("strategy_exit_state") == "completed":
        return {
            "client_order_id": list_client_order_id,
            "state": "accepted",
            "reconciled": True,
            "protection_state": "closed",
            "strategy_exit_reconciled": True,
        }
    if record.get("state") == "accepted" and record.get("protection_state") == "triggered" and record.get("exit_reconciled") is True:
        return {
            "client_order_id": list_client_order_id,
            "state": "accepted",
            "reconciled": True,
            "protection_state": "triggered",
            "exit_reconciled": True,
        }
    if not _is_unresolved(record) and not force:
        return {
            "client_order_id": list_client_order_id,
            "state": str(record.get("state") or ""),
            "reconciled": False,
            "protection_state": record.get("protection_state"),
        }
    try:
        list_response, working, pending = _query_spot_opo_observation(self, record)
        working_status = str(working["status"])
        pending_status = str(pending["status"])
        working_executed = Decimal(str(working["executedQty"]))
        pending_executed = Decimal(str(pending["executedQty"]))
        pending_original = Decimal(str(pending["origQty"]))
        list_status = str(list_response["listStatusType"])
        if (
            working_status == "FILLED"
            and working_executed == Decimal(str(record["quantity"]))
            and pending_status == "NEW"
            and list_status == "EXEC_STARTED"
        ):
            state, protection_state = "accepted", "active"
        elif (
            working_status == "FILLED"
            and working_executed == Decimal(str(record["quantity"]))
            and pending_status == "PENDING_NEW"
            and list_status == "EXEC_STARTED"
        ):
            state, protection_state = "accepted", "unverified"
        elif (
            working_status == "FILLED"
            and working_executed == Decimal(str(record["quantity"]))
            and pending_status == "FILLED"
            and pending_original > 0
            and pending_executed == pending_original
            and list_status == "ALL_DONE"
        ):
            state, protection_state = "accepted", "triggered"
        elif (
            record.get("cancel_state") in {"submitted", "unknown", "confirmed"}
            and record.get("entry_reconciled") is True
            and working_status == "FILLED"
            and working_executed == Decimal(str(record["quantity"]))
            and pending_status == "CANCELED"
            and pending_executed == 0
            and list_status == "ALL_DONE"
        ):
            state, protection_state = "accepted", "cancelled"
        elif (
            working_status in {"CANCELED", "EXPIRED", "EXPIRED_IN_MATCH", "REJECTED"}
            and working_executed == 0
            and pending_status in {"PENDING_NEW", "CANCELED", "EXPIRED", "REJECTED"}
            and pending_executed == 0
            and list_status == "ALL_DONE"
        ):
            state, protection_state = "rejected", "none"
        elif working_executed > 0:
            state, protection_state = "unknown", "lost"
        else:
            state, protection_state = "unknown", "unverified"
        updates = {
            "exchange_order_list_id": list_response["orderListId"],
            "list_status": list_status,
            "working_order_id": working["orderId"],
            "working_status": working_status,
            "pending_order_id": pending["orderId"],
            "pending_status": pending_status,
            "working_executed_qty": format(working_executed, "f"),
            "pending_executed_qty": format(pending_executed, "f"),
            "pending_original_qty": format(pending_original, "f"),
            "protection_state": protection_state,
            "last_reconciliation_at": _now(),
        }
        if (
            protection_state in {"active", "triggered"}
            and record.get("strategy_exit_state") == "cancel_failed"
            and record.get("strategy_exit_outcome") == "cancel_failed"
            and record.get("strategy_exit_new_order_accepted") is False
        ):
            updates["cancel_state"] = "rejected"
            updates["strategy_exit_state"] = "no_effect"
        if (
            protection_state == "active"
            and record.get("strategy_exit_state") in {"cancel_failed", "no_effect"}
            and record.get("strategy_exit_outcome") == "cancel_failed"
            and record.get("strategy_exit_new_order_accepted") is False
        ):
            candidate = {**record, **updates, "state": state, "cancel_state": "rejected", "strategy_exit_state": "no_effect"}
            updates["strategy_exit_no_effect_proof"] = build_spot_opo_no_effect_proof(
                candidate, verified_at=str(updates["last_reconciliation_at"]),
            )
        if (
            protection_state == "cancelled"
            and record.get("strategy_exit_state") == "submitted"
            and record.get("strategy_exit_outcome") is None
        ):
            updates["strategy_exit_state"] = "unknown"
        if protection_state == "cancelled":
            updates["cancel_state"] = "confirmed"
            updates["cancel_confirmed_at"] = _now()
            if isinstance(record.get("strategy_exit_request"), Mapping):
                updates["pending_observed_client_order_id"] = pending["clientOrderId"]
    except SPOT_EXCHANGE_ERRORS as exc:
        error = redact_text(exc) or "Spot OPO reconciliation failed."
        prior_protection_state = record.get("protection_state")
        confirmed_cancel = prior_protection_state == "cancelled" and record.get("cancel_state") == "confirmed"
        protection_state = (
            "cancelled" if confirmed_cancel else
            prior_protection_state if prior_protection_state in {"lost", "triggered"} else "unverified"
        )
        # A confirmed canceled stop remains an unresolved inventory obligation.
        # Preserve its valid durable proof when a later query fails or regresses.
        updated = _update_order_intent_by_id(
            self, list_client_order_id, state="accepted" if confirmed_cancel else "unknown", expected_record=record,
            protection_state=protection_state, last_reconciliation_error=error,
            last_reconciliation_at=_now(),
        )
        if updated is None:
            return {
                "client_order_id": list_client_order_id,
                "state": "unknown",
                "reconciled": False,
                "error": "Spot OPO intent changed during reconciliation; the late result was not applied.",
            }
        return {
            "client_order_id": list_client_order_id,
            "state": str(updated["state"]),
            "reconciled": False,
            "protection_state": updated.get("protection_state"),
            "error": error,
        }
    updated = _update_order_intent_by_id(
        self, list_client_order_id, state=state, expected_record=record, **updates,
    )
    if updated is None:
        return {
            "client_order_id": list_client_order_id,
            "state": str((_get_order_intent_record(self, list_client_order_id) or {}).get("state") or "unknown"),
            "reconciled": False,
            "error": "Spot OPO intent changed during reconciliation; the late result was not applied.",
        }
    if applied_records is not None:
        applied_records.append(updated)
    return {
        "client_order_id": list_client_order_id,
        "state": str(updated["state"]),
        "reconciled": not _is_unresolved(updated),
        "protection_state": updated.get("protection_state"),
        "list_status": updated.get("list_status"),
        "working_status": updated.get("working_status"),
        "pending_status": updated.get("pending_status"),
        "exchange_order_list_id": updated.get("exchange_order_list_id"),
    }


def reconcile_spot_opo_intent(
    self, list_client_order_id: str, *, force: bool = False,
) -> dict[str, object]:
    return _reconcile_spot_opo_intent(self, list_client_order_id, force=force)


def cancel_spot_opo_intent(self, list_client_order_id: str) -> dict[str, object]:
    """Cancel one recovered OPO stop and confirm the exact list and child state.

    Cancellation deliberately leaves the OPO unresolved after the stop is
    removed. This operation never submits a strategy SELL or rearms protection.
    """
    list_client_order_id = str(list_client_order_id or "").strip()
    record = _get_order_intent_record(self, list_client_order_id) if list_client_order_id else None
    if record is None or record.get("type") != "OPO":
        raise LiveTradingSafetyError("Spot OPO cancellation requires one exact list intent.")
    if record.get("strategy_exit_state") is not None:
        raise LiveTradingSafetyError("Spot OPO cancellation is blocked after a linked SELL attempt; reconcile it first.")
    if record.get("entry_reconciled") is not True:
        raise LiveTradingSafetyError("Spot OPO cancellation requires recovered BUY inventory.")
    client = getattr(self, "client", None)
    observation = reconcile_spot_opo_intent(self, list_client_order_id, force=True)
    record = _get_order_intent_record(self, list_client_order_id)
    if record is None or observation.get("error"):
        raise LiveTradingSafetyError("Spot OPO state is unverified; cancellation was not attempted.")
    if record.get("protection_state") == "triggered":
        return {
            "client_order_id": list_client_order_id,
            "cancel_confirmed": False,
            "protection_state": "triggered",
            "requires_stop_fill_recovery": True,
        }
    if (
        record.get("state") == "accepted"
        and record.get("protection_state") == "cancelled"
        and record.get("cancel_state") == "confirmed"
    ):
        return {
            "client_order_id": list_client_order_id,
            "cancel_confirmed": True,
            "protection_state": "cancelled",
            "already_cancelled": True,
            "requires_manual_reconciliation": True,
        }
    if record.get("protection_state") != "active" or record.get("state") != "accepted":
        raise LiveTradingSafetyError("Only an exactly active recovered Spot OPO can be canceled by this action.")
    cancel_order_list = getattr(client, "cancel_order_list", None)
    if not callable(cancel_order_list):
        raise LiveTradingSafetyError("Exact Binance Spot OPO cancellation transport is unavailable.")

    updated = _update_order_intent_by_id(
        self,
        list_client_order_id,
        state="accepted",
        expected_record=record,
        cancel_state="submitted",
        cancel_submitted_at=_now(),
    )
    if updated is None:
        raise LiveTradingSafetyError("Spot OPO changed before cancellation; query it again before proceeding.")

    cancellation_error = ""
    try:
        request = validate_spot_opo_request_payload(updated.get("request"))
        cancel_order_list(
            symbol=request["symbol"],
            listClientOrderId=request["listClientOrderId"],
        )
    except SPOT_EXCHANGE_ERRORS as exc:
        cancellation_error = redact_text(exc) or "Binance Spot OPO cancellation result is uncertain."

    result = reconcile_spot_opo_intent(self, list_client_order_id, force=True)
    refreshed = _get_order_intent_record(self, list_client_order_id)
    if refreshed is None:
        raise LiveTradingSafetyError("Spot OPO intent disappeared after cancellation; manual reconciliation is required.")
    if refreshed.get("protection_state") == "cancelled" and refreshed.get("cancel_state") == "confirmed":
        return {
            "client_order_id": list_client_order_id,
            "cancel_confirmed": True,
            "protection_state": "cancelled",
            "already_cancelled": False,
            "requires_manual_reconciliation": True,
        }
    if refreshed.get("protection_state") == "triggered":
        return {
            "client_order_id": list_client_order_id,
            "cancel_confirmed": False,
            "protection_state": "triggered",
            "requires_stop_fill_recovery": True,
        }
    if not cancellation_error:
        cancellation_error = "The exact OPO query did not confirm a canceled pending stop."
    safe_cancel_error = redact_text(cancellation_error)[:500]
    _update_order_intent_by_id(
        self,
        list_client_order_id,
        state="accepted" if refreshed.get("state") == "accepted" else "unknown",
        expected_record=refreshed,
        cancel_state="unknown",
        last_cancel_error=safe_cancel_error,
    )
    return {
        "client_order_id": list_client_order_id,
        "cancel_confirmed": False,
        "protection_state": refreshed.get("protection_state"),
        "error": safe_cancel_error,
        "requires_manual_reconciliation": True,
        "reconciled": result.get("reconciled") is True,
    }


def reconcile_order_intent(self, client_order_id: str, *, include_execution: bool = False) -> dict[str, object]:
    """Reconcile one unresolved order intent against the exchange.

    A failed query, malformed response, or a not-found response preserves the
    safety block. Only a known state for the exact requested order can resolve it.
    """
    client_order_id = str(client_order_id or "").strip()
    if not client_order_id:
        raise LiveTradingSafetyError("Client order ID is required for reconciliation.")
    record = _get_order_intent_record(self, client_order_id)
    if record is None:
        raise LiveTradingSafetyError(f"Order intent {client_order_id} was not found in the local ledger.")
    if record.get("market") == "spot" and record.get("type") == "OPO":
        return reconcile_spot_opo_intent(self, client_order_id, force=_has_active_spot_protection(record))
    current_state = str(record.get("state") or "").lower()
    if not _is_unresolved(record):
        return {"client_order_id": client_order_id, "state": current_state, "reconciled": False}
    error = ""
    exchange_status = ""
    exchange_order_id = ""
    updates: dict[str, object]
    execution_response: dict[str, object] = {}
    try:
        query = getattr(self, "_query_order_intent_exchange", None)
        if not callable(query):
            raise LiveTradingSafetyError("Order intent reconciliation transport is unavailable.")
        result = query(record)
        resolved_state, exchange_status, exchange_order_id = _validate_reconciliation_response(
            record, result, require_portfolio_reconciliation=True,
        )
    except Exception as exc:
        error = redact_text(exc) or "Exchange order reconciliation failed."
        resolved_state = "unknown" if current_state == "accepted" else current_state
        updates = {"last_reconciliation_error": error, "last_reconciliation_at": _now()}
    else:
        updates = {
            "exchange_order_id": exchange_order_id,
            "exchange_status": exchange_status,
            "reconciled_at": _now(),
        }
        if _requires_execution_confirmation(record) and isinstance(result, Mapping):
            updates["executed_qty"] = str(result["executedQty"])
            if include_execution:
                execution_response = {key: result[key] for key in (
                    "clientOrderId", "symbol", "side", "positionSide", "orderId", "status",
                    "type", "price", "origQty", "executedQty", "cummulativeQuoteQty",
                    "avgPrice", "cumQuote", "time", "updateTime",
                ) if key in result}
                # Binance Spot order responses report cumulative quote under
                # `cummulativeQuoteQty`; preserve it and derive a gross average
                # only when both exchange quantities are finite and usable.
                executed = _finite_nonnegative_decimal(result.get("executedQty"))
                quote = _finite_nonnegative_decimal(result.get("cummulativeQuoteQty"))
                if executed is not None and executed > 0 and quote is not None:
                    gross_average = format(quote / executed, "f")
                    if "." in gross_average:
                        gross_average = gross_average.rstrip("0").rstrip(".")
                    execution_response["gross_average_price"] = gross_average
    updated = _update_order_intent_by_id(
        self, client_order_id, state=resolved_state, expected_record=record, **updates,
    )
    if updated is None:
        current = _get_order_intent_record(self, client_order_id)
        if current is None:
            raise LiveTradingSafetyError("Order intent disappeared during reconciliation.")
        return {
            "client_order_id": client_order_id,
            "state": str(current["state"]),
            "reconciled": False,
            "error": "Order intent changed during reconciliation; the late result was not applied.",
        }
    if error:
        return {"client_order_id": client_order_id, "state": str(updated["state"]), "reconciled": False, "error": error}
    response_market = str(record.get("market") or "").lower()
    response_type = str(record.get("type") or "").upper()
    reported_executed_qty = _finite_nonnegative_decimal(execution_response.get("executedQty"))
    has_spot_execution = (
        response_market == "spot"
        and response_type == "MARKET"
        and execution_response
        and reported_executed_qty is not None
        and reported_executed_qty > 0
    )
    return {
        "client_order_id": client_order_id,
        "state": str(updated["state"]),
        "reconciled": True,
        "exchange_status": exchange_status,
        "exchange_order_id": exchange_order_id,
        **({"portfolio_reconciliation_required": True} if has_spot_execution else {}),
        **({"order_response": execution_response} if execution_response else {}),
    }


def reconcile_unresolved_order_intents(
    self, *, limit: int = 25, include_execution: bool = False,
) -> list[dict[str, object]]:
    limit = max(1, min(100, int(limit)))
    path = _intent_path(self)
    with ledger_transaction(path):
        ledger = _read_ledger(path, expected_binding=_intent_binding(self))
        intents = ledger["intents"]
        if not isinstance(intents, dict):
            raise LiveTradingSafetyError("Order intent ledger is malformed; reconciliation is blocked.")
        client_order_ids = [
            client_order_id for client_order_id, record in intents.items()
            if isinstance(record, Mapping) and _is_unresolved(record)
        ]
        client_order_ids.extend(
            client_order_id for client_order_id in _active_spot_protection_records(intents)
            if client_order_id not in client_order_ids
        )
    return [
        reconcile_order_intent(self, client_order_id, include_execution=include_execution)
        for client_order_id in client_order_ids[:limit]
    ]


def get_order_intent_status(self) -> dict[str, object]:
    path = _intent_path(self)
    with ledger_transaction(path):
        ledger = _read_ledger(path, expected_binding=_intent_binding(self))
    intents = ledger.get("intents")
    records = list(intents.values()) if isinstance(intents, dict) else []
    unresolved = [
        record
        for record in records
        if isinstance(record, Mapping) and _is_unresolved(record)
    ]
    spot_opo_client_order_ids = [
        str(record.get("client_order_id") or "")
        for record in records
        if (
            isinstance(record, Mapping)
            and record.get("market") == "spot"
            and record.get("type") == "OPO"
            and not (record.get("state") == "rejected" and record.get("protection_state") == "none")
            and not (record.get("protection_state") == "triggered" and record.get("exit_reconciled") is True)
        )
    ]
    return {
        "path": str(path),
        "format_version": _INTENT_FORMAT_VERSION,
        "storage_ready": True,
        "intent_count": len(records),
        "unresolved_count": len(unresolved),
        "unresolved_client_order_ids": [str(record.get("client_order_id") or "") for record in unresolved],
        "spot_opo_client_order_ids": spot_opo_client_order_ids,
    }


def get_spot_open_order_reconciliation_status(
    self, exchange_open_orders: object,
) -> dict[str, int]:
    """Compare account-wide Binance open orders with this UID ledger without mutating it."""
    open_statuses = {"NEW", "PARTIALLY_FILLED", "PENDING_NEW", "PENDING_CANCEL"}
    allowed_statuses = _ORDER_STATUSES | _SPOT_PENDING_STATUSES
    if not isinstance(exchange_open_orders, list) or len(exchange_open_orders) > 10_000:
        raise LiveTradingSafetyError("Binance Spot open orders response is missing or too large.")

    def valid_symbol(value: object) -> bool:
        return (
            isinstance(value, str) and bool(value) and value.isascii()
            and value.isalnum() and value == value.upper()
        )

    def valid_client_order_id(value: object) -> bool:
        return (
            isinstance(value, str) and bool(value) and len(value) <= 36 and value.isascii()
            and all(character.isalnum() or character in "._:/-" for character in value)
        )

    exchange_orders: dict[tuple[str, str], dict[str, object]] = {}
    for value in exchange_open_orders:
        if not isinstance(value, Mapping) or "code" in value:
            raise LiveTradingSafetyError("Binance Spot open orders response is malformed.")
        symbol = value.get("symbol")
        client_order_id = value.get("clientOrderId")
        status = value.get("status")
        order_id = _exchange_order_id(value)
        if (
            not valid_symbol(symbol) or not valid_client_order_id(client_order_id)
            or not isinstance(status, str) or status.strip().upper() not in open_statuses
            or not order_id
        ):
            raise LiveTradingSafetyError("Binance Spot open orders response contains an invalid order identity.")
        key = (cast(str, symbol), cast(str, client_order_id))
        if key in exchange_orders:
            raise LiveTradingSafetyError("Binance Spot open orders response contains a duplicate order.")
        exchange_orders[key] = dict(value)

    path = _intent_path(self)
    with ledger_transaction(path):
        ledger = _read_ledger(path, expected_binding=_intent_binding(self))
    intents = ledger.get("intents")
    if not isinstance(intents, dict):
        raise LiveTradingSafetyError("Order intent ledger is malformed; reconcile it before submitting orders.")

    local_orders: dict[tuple[str, str], Mapping[str, object]] = {}
    expected_open: set[tuple[str, str]] = set()
    local_status_conflicts = 0
    for client_order_id, record in intents.items():
        if (
            not isinstance(client_order_id, str)
            or not valid_client_order_id(client_order_id)
            or not isinstance(record, Mapping)
            or record.get("market") != "spot"
        ):
            raise LiveTradingSafetyError("Live Spot order ledger contains an invalid market record.")
        symbol = record.get("symbol")
        if not valid_symbol(symbol) or client_order_id != record.get("client_order_id"):
            raise LiveTradingSafetyError("Live Spot order ledger contains an invalid order identity.")
        if record.get("type") == "OPO":
            request_value = record.get("request")
            request = validate_spot_opo_request_payload(request_value)
            if record.get("state") == "rejected" and record.get("protection_state") == "none":
                continue
            pending_client_id = request["pendingClientOrderId"]
            protection_cancelled = (
                record.get("state") == "accepted"
                and record.get("protection_state") in {"cancelled", "closed"}
                and record.get("cancel_state") == "confirmed"
            )
            if not protection_cancelled:
                if not valid_client_order_id(pending_client_id):
                    raise LiveTradingSafetyError("Live Spot OPO child order ID is invalid.")
                key = (cast(str, symbol), pending_client_id)
                if key in local_orders:
                    raise LiveTradingSafetyError("Live Spot order ledger contains a duplicate child order identity.")
                local_orders[key] = record
                if record.get("pending_status") in open_statuses:
                    expected_open.add(key)
            is_active = (
                record.get("state") == "accepted"
                and record.get("protection_state") == "active"
                and record.get("pending_status") == "NEW"
            )
            is_triggered = (
                record.get("state") == "accepted"
                and record.get("protection_state") == "triggered"
                and record.get("pending_status") == "FILLED"
            )
            if not (protection_cancelled or is_triggered or is_active):
                local_status_conflicts += 1
            elif is_active and record.get("cancel_state") in {"submitted", "unknown"}:
                local_status_conflicts += 1

            exit_state = record.get("strategy_exit_state")
            exit_client_id = record.get("strategy_exit_client_order_id")
            if (
                isinstance(exit_client_id, str)
                and exit_state in {"submitted", "unknown", "sell_accepted"}
            ):
                exit_key = (cast(str, symbol), exit_client_id)
                if exit_key in local_orders:
                    raise LiveTradingSafetyError("Live Spot order ledger contains a duplicate linked SELL identity.")
                exit_record = dict(record)
                exit_record.update({
                    "client_order_id": exit_client_id,
                    "side": "SELL",
                    "type": "MARKET",
                    "exchange_order_id": record.get("strategy_exit_order_id"),
                    "exchange_status": record.get("strategy_exit_status"),
                })
                local_orders[exit_key] = exit_record
                if record.get("strategy_exit_status") in open_statuses:
                    expected_open.add(exit_key)
            residual_state = record.get("residual_stop_state")
            residual_request_value = record.get("residual_stop_request")
            if residual_state in {"submitted", "unknown", "acknowledged", "active", "triggered"}:
                try:
                    residual_request = validate_spot_opo_residual_stop_request(residual_request_value)
                except LiveTradingSafetyError:
                    local_status_conflicts += 1
                    continue
                residual_id = residual_request["newClientOrderId"]
                residual_key = (cast(str, symbol), residual_id)
                if residual_key in local_orders:
                    raise LiveTradingSafetyError("Live Spot ledger contains a duplicate residual stop identity.")
                residual_record = dict(record)
                residual_record.update({
                    "client_order_id": residual_id,
                    "type": "STOP_LOSS",
                    "side": "SELL",
                    "exchange_order_id": record.get("residual_stop_order_id"),
                    "exchange_status": record.get("residual_stop_status"),
                })
                local_orders[residual_key] = residual_record
                if record.get("residual_stop_status") in open_statuses:
                    expected_open.add(residual_key)
                if residual_state in {"submitted", "unknown", "acknowledged"}:
                    local_status_conflicts += 1
            continue
        key = (cast(str, symbol), client_order_id)
        if key in local_orders:
            raise LiveTradingSafetyError("Live Spot order ledger contains a duplicate order identity.")
        local_orders[key] = record
        raw_status = record.get("exchange_status")
        state = record.get("state")
        if raw_status in (None, ""):
            if state == "accepted":
                local_status_conflicts += 1
            continue
        if not isinstance(raw_status, str) or raw_status.strip().upper() not in allowed_statuses:
            raise LiveTradingSafetyError("Live Spot order ledger contains an invalid exchange status.")
        if raw_status.strip().upper() in open_statuses:
            if state == "rejected":
                local_status_conflicts += 1
            else:
                expected_open.add(key)

    unmatched_exchange_open_orders = 0
    for key, exchange_order in exchange_orders.items():
        local_record = local_orders.get(key)
        if local_record is None:
            unmatched_exchange_open_orders += 1
            continue
        is_opo = local_record.get("type") == "OPO"
        local_status = local_record.get("pending_status") if is_opo else local_record.get("exchange_status")
        if (
            local_record.get("state") == "rejected"
            or not isinstance(local_status, str)
            or local_status.strip().upper() not in open_statuses
        ):
            local_status_conflicts += 1
            continue
        local_order_id = local_record.get("pending_order_id") if is_opo else local_record.get("exchange_order_id")
        exchange_order_id = _exchange_order_id(exchange_order)
        if local_order_id and str(local_order_id) != exchange_order_id:
            local_status_conflicts += 1

    local_open_orders_missing_from_exchange = sum(
        1 for key in expected_open if key not in exchange_orders
    )
    return {
        "exchange_open_order_count": len(exchange_orders),
        "matched_open_order_count": len(exchange_orders) - unmatched_exchange_open_orders,
        "unmatched_exchange_open_order_count": unmatched_exchange_open_orders,
        "local_open_orders_missing_from_exchange_count": local_open_orders_missing_from_exchange,
        "local_open_order_status_conflict_count": local_status_conflicts,
    }


def bind_binance_order_intent_runtime(wrapper_cls) -> None:
    wrapper_cls._resolve_spot_account_uid = _resolve_spot_account_uid
    wrapper_cls._ensure_spot_execution_owner = _ensure_spot_execution_owner
    wrapper_cls._spot_execution_submission = _spot_execution_submission
    wrapper_cls._revoke_spot_execution_owner = _revoke_spot_execution_owner
    wrapper_cls._get_order_intent_record = _get_order_intent_record
    wrapper_cls._capture_spot_buy_publication = _capture_spot_buy_publication
    wrapper_cls._get_spot_buy_submission_origin = _get_spot_buy_submission_origin
    wrapper_cls._begin_order_intent = _begin_order_intent
    wrapper_cls._begin_spot_opo_intent = _begin_spot_opo_intent
    wrapper_cls._mark_order_intent_submitted = _mark_order_intent_submitted
    wrapper_cls._mark_order_intent_accepted = _mark_order_intent_accepted
    wrapper_cls._mark_order_intent_unknown = _mark_order_intent_unknown
    wrapper_cls._mark_spot_opo_submitted = _mark_spot_opo_submitted
    wrapper_cls._mark_spot_opo_accepted = _mark_spot_opo_accepted
    wrapper_cls._mark_spot_opo_unknown = _mark_spot_opo_unknown
    wrapper_cls._check_spot_opo_strategy_exit_client_id = _check_spot_opo_strategy_exit_client_id
    wrapper_cls._begin_spot_opo_strategy_exit = _begin_spot_opo_strategy_exit
    wrapper_cls._mark_spot_opo_strategy_exit_unknown = _mark_spot_opo_strategy_exit_unknown
    wrapper_cls._mark_spot_opo_strategy_exit_response = _mark_spot_opo_strategy_exit_response
    wrapper_cls.reconcile_spot_opo_strategy_exit = reconcile_spot_opo_strategy_exit
    wrapper_cls._mark_spot_opo_strategy_exit_order_observed = _mark_spot_opo_strategy_exit_order_observed
    wrapper_cls._mark_spot_opo_strategy_exit_reconciled = _mark_spot_opo_strategy_exit_reconciled
    wrapper_cls._mark_spot_opo_strategy_exit_residual_required = _mark_spot_opo_strategy_exit_residual_required
    wrapper_cls._begin_spot_opo_residual_stop = _begin_spot_opo_residual_stop
    wrapper_cls._mark_spot_opo_residual_stop_unknown = _mark_spot_opo_residual_stop_unknown
    wrapper_cls._mark_spot_opo_residual_stop_order_observed = _mark_spot_opo_residual_stop_order_observed
    wrapper_cls._mark_spot_opo_residual_stop_reconciled = _mark_spot_opo_residual_stop_reconciled
    wrapper_cls._mark_spot_opo_residual_stop_no_fill = _mark_spot_opo_residual_stop_no_fill
    wrapper_cls._mark_order_intent_portfolio_reconciled = _mark_order_intent_portfolio_reconciled
    wrapper_cls._mark_spot_opo_entry_reconciled = _mark_spot_opo_entry_reconciled
    wrapper_cls._mark_spot_opo_exit_reconciled = _mark_spot_opo_exit_reconciled
    wrapper_cls.cancel_spot_opo_intent = cancel_spot_opo_intent
    wrapper_cls._query_order_intent_exchange = _query_order_intent_exchange
    wrapper_cls.reconcile_order_intent = reconcile_order_intent
    wrapper_cls.reconcile_spot_opo_intent = reconcile_spot_opo_intent
    wrapper_cls.reconcile_unresolved_order_intents = reconcile_unresolved_order_intents
    wrapper_cls.get_order_intent_status = get_order_intent_status
