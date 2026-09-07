"""Durable, local order-intent ledger for restart-safe exchange submissions."""

from __future__ import annotations

import hashlib
import json
import re
from collections.abc import Mapping
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation
from pathlib import Path
from uuid import UUID

from app.settings.live_safety import LiveTradingSafetyError
from app.settings.execution_mode import execution_environment
from app.security.redaction import redact_text
from trading_core.orders import is_exchange_risk_reducing_order, order_execution_from_response

from .order_intent_store import ledger_transaction, write_ledger


_INTENT_FORMAT_VERSION = 2
_BLOCKING_STATES = {"pending", "submitted", "unknown", "accepted"}
_UNRESOLVED_STATES = {"pending", "submitted", "unknown"}
_ORDER_STATUSES = {"NEW", "PARTIALLY_FILLED", "FILLED", "CANCELED", "REJECTED", "EXPIRED", "EXPIRED_IN_MATCH"}
_SPOT_PENDING_STATUSES = {"PENDING_NEW", "PENDING_CANCEL"}


def _requires_execution_confirmation(record: Mapping[str, object]) -> bool:
    return bool(record.get("requires_close_confirmation")) or (
        record.get("market") == "futures" and record.get("type") == "MARKET"
    )


def _is_unresolved(record: Mapping[str, object]) -> bool:
    if record.get("state") in _UNRESOLVED_STATES:
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


def _intent_path(self) -> Path:
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
    if (not isinstance(payload, dict)
            or type(payload.get("format_version")) is not int
            or payload["format_version"] not in (1, _INTENT_FORMAT_VERSION)
            or not isinstance(payload.get("intents"), dict)):
        raise LiveTradingSafetyError("Order intent ledger is malformed; reconcile it before submitting orders.")
    for key, record in payload["intents"].items():
        if (not isinstance(key, str) or not key.strip()
                or not isinstance(record, dict) or record.get("client_order_id") != key
                or not isinstance(record.get("state"), str)
                or ("requires_close_confirmation" in record and type(record["requires_close_confirmation"]) is not bool)
                or record.get("state") not in _BLOCKING_STATES | {"rejected"}):
            raise LiveTradingSafetyError("Order intent ledger contains an invalid record; reconcile it before submitting orders.")
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
    return {
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


def _begin_order_intent(self, params: Mapping[str, object], *, market: str, source: str) -> dict[str, object]:
    record = _intent_record(params, market=market, source=source)
    path = _intent_path(self)
    with ledger_transaction(path):
        ledger = _read_ledger(path, expected_binding=_intent_binding(self))
        intents = ledger["intents"]
        if not isinstance(intents, dict):
            raise LiveTradingSafetyError("Order intent ledger is malformed; reconcile it before submitting orders.")
        existing = intents.get(record["client_order_id"])
        if isinstance(existing, Mapping) and str(existing.get("state") or "") in _BLOCKING_STATES:
            raise LiveTradingSafetyError(
                f"Client order ID {record['client_order_id']} already has state "
                f"{existing.get('state')}; reconcile it before retrying."
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
    return record


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


def _get_order_intent_record(self, client_order_id: str) -> dict[str, object] | None:
    path = _intent_path(self)
    with ledger_transaction(path):
        ledger = _read_ledger(path, expected_binding=_intent_binding(self))
        intents = ledger.get("intents")
        record = intents.get(client_order_id) if isinstance(intents, dict) else None
        return dict(record) if isinstance(record, Mapping) else None


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


def _validate_reconciliation_response(record: Mapping[str, object], result: object) -> tuple[str, str, str]:
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
        resolved_state, exchange_status, exchange_order_id = _validate_reconciliation_response(record, result)
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
                    "executedQty", "origQty", "avgPrice", "cumQuote", "updateTime",
                ) if key in result}
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
    return {
        "client_order_id": client_order_id,
        "state": str(updated["state"]),
        "reconciled": True,
        "exchange_status": exchange_status,
        "exchange_order_id": exchange_order_id,
        **({"order_response": execution_response} if execution_response else {}),
    }


def reconcile_unresolved_order_intents(self, *, limit: int = 25) -> list[dict[str, object]]:
    limit = max(1, min(100, int(limit)))
    status = get_order_intent_status(self)
    client_order_ids = status.get("unresolved_client_order_ids")
    if not isinstance(client_order_ids, list):
        return []
    return [reconcile_order_intent(self, client_order_id) for client_order_id in client_order_ids[:limit]]


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
    return {
        "path": str(path),
        "format_version": _INTENT_FORMAT_VERSION,
        "storage_ready": True,
        "intent_count": len(records),
        "unresolved_count": len(unresolved),
        "unresolved_client_order_ids": [str(record.get("client_order_id") or "") for record in unresolved],
    }


def bind_binance_order_intent_runtime(wrapper_cls) -> None:
    wrapper_cls._begin_order_intent = _begin_order_intent
    wrapper_cls._mark_order_intent_submitted = _mark_order_intent_submitted
    wrapper_cls._mark_order_intent_accepted = _mark_order_intent_accepted
    wrapper_cls._mark_order_intent_unknown = _mark_order_intent_unknown
    wrapper_cls._query_order_intent_exchange = _query_order_intent_exchange
    wrapper_cls.reconcile_order_intent = reconcile_order_intent
    wrapper_cls.reconcile_unresolved_order_intents = reconcile_unresolved_order_intents
    wrapper_cls.get_order_intent_status = get_order_intent_status
