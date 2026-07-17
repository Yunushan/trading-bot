"""Durable, local order-intent ledger for restart-safe exchange submissions."""

from __future__ import annotations

import json
import os
import threading
from collections.abc import Mapping
from datetime import datetime, timezone
from pathlib import Path

from app.settings.live_safety import LiveTradingSafetyError


_INTENT_LOCK = threading.Lock()
_INTENT_FORMAT_VERSION = 1
_BLOCKING_STATES = {"pending", "submitted", "unknown", "accepted"}
_UNRESOLVED_STATES = {"pending", "submitted", "unknown"}
_REJECTED_STATES = {"REJECTED", "CANCELED", "CANCELLED", "EXPIRED"}


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _intent_path(self) -> Path:
    audit_path = getattr(self, "_order_audit_log_path", None)
    if audit_path:
        path = Path(audit_path).expanduser()
        return path.with_name(f"{path.stem}.intents.json")
    return Path.home() / ".trading-bot" / "order_intents.json"


def _read_ledger(path: Path) -> dict[str, object]:
    if not path.is_file():
        return {"format_version": _INTENT_FORMAT_VERSION, "intents": {}}
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except Exception as exc:
        raise LiveTradingSafetyError(f"Order intent ledger cannot be read: {exc}") from exc
    if not isinstance(payload, dict) or not isinstance(payload.get("intents"), dict):
        raise LiveTradingSafetyError("Order intent ledger is malformed; reconcile it before submitting orders.")
    return payload


def _write_ledger(path: Path, payload: Mapping[str, object]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp_path = path.with_name(f".{path.name}.tmp")
    tmp_path.write_text(json.dumps(payload, sort_keys=True, indent=2) + "\n", encoding="utf-8")
    tmp_path.replace(path)
    try:
        os.chmod(path, 0o600)
    except OSError:
        pass


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
        "type": str(params.get("type") or "").upper(),
        "quantity": str(params.get("quantity") or ""),
        "state": "pending",
        "created_at": _now(),
        "updated_at": _now(),
    }


def _begin_order_intent(self, params: Mapping[str, object], *, market: str, source: str) -> dict[str, object]:
    record = _intent_record(params, market=market, source=source)
    path = _intent_path(self)
    with _INTENT_LOCK:
        ledger = _read_ledger(path)
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
            if isinstance(intent, Mapping) and str(intent.get("state") or "") in _UNRESOLVED_STATES
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
    with _INTENT_LOCK:
        ledger = _read_ledger(path)
        intents = ledger["intents"]
        if not isinstance(intents, dict):
            raise LiveTradingSafetyError("Order intent ledger is malformed; reconcile it before submitting orders.")
        record = intents.get(client_order_id)
        if not isinstance(record, dict):
            return
        record["state"] = state
        record["updated_at"] = _now()
        record.update({key: value for key, value in updates.items() if value not in (None, "")})
        _write_ledger(path, ledger)


def _mark_order_intent_submitted(self, params: Mapping[str, object], *, via: str) -> None:
    _update_order_intent(self, params, state="submitted", last_via=str(via), submitted_at=_now())


def _mark_order_intent_accepted(self, params: Mapping[str, object], *, via: str, result: object) -> None:
    order_id = ""
    if isinstance(result, Mapping):
        for key in ("orderId", "order_id", "id", "clientOrderId", "client_order_id"):
            if result.get(key) not in (None, ""):
                order_id = str(result[key])
                break
    _update_order_intent(
        self,
        params,
        state="accepted",
        last_via=str(via),
        exchange_order_id=order_id,
        accepted_at=_now(),
    )


def _mark_order_intent_unknown(self, params: Mapping[str, object], *, error: object) -> None:
    _update_order_intent(self, params, state="unknown", last_error=str(error or ""), uncertain_at=_now())


def _get_order_intent_record(self, client_order_id: str) -> dict[str, object] | None:
    path = _intent_path(self)
    with _INTENT_LOCK:
        ledger = _read_ledger(path)
        intents = ledger.get("intents")
        record = intents.get(client_order_id) if isinstance(intents, dict) else None
        return dict(record) if isinstance(record, Mapping) else None


def _update_order_intent_by_id(self, client_order_id: str, *, state: str, **updates: object) -> dict[str, object] | None:
    path = _intent_path(self)
    with _INTENT_LOCK:
        ledger = _read_ledger(path)
        intents = ledger.get("intents")
        if not isinstance(intents, dict):
            raise LiveTradingSafetyError("Order intent ledger is malformed; reconcile it before submitting orders.")
        record = intents.get(client_order_id)
        if not isinstance(record, dict):
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
    for key in ("orderId", "order_id", "id", "clientOrderId", "client_order_id"):
        value = result.get(key)
        if value not in (None, ""):
            return str(value)
    return ""


def reconcile_order_intent(self, client_order_id: str) -> dict[str, object]:
    """Reconcile one unresolved order intent against the exchange.

    A failed query, malformed response, or a not-found response preserves the
    safety block. Only an explicit exchange order state can resolve an intent.
    """
    client_order_id = str(client_order_id or "").strip()
    if not client_order_id:
        raise LiveTradingSafetyError("Client order ID is required for reconciliation.")
    record = _get_order_intent_record(self, client_order_id)
    if record is None:
        raise LiveTradingSafetyError(f"Order intent {client_order_id} was not found in the local ledger.")
    current_state = str(record.get("state") or "").lower()
    if current_state not in _UNRESOLVED_STATES:
        return {"client_order_id": client_order_id, "state": current_state, "reconciled": False}
    try:
        query = getattr(self, "_query_order_intent_exchange", None)
        if not callable(query):
            raise LiveTradingSafetyError("Order intent reconciliation transport is unavailable.")
        result = query(record)
    except Exception as exc:
        updated = _update_order_intent_by_id(
            self,
            client_order_id,
            state=current_state,
            last_reconciliation_error=str(exc),
            last_reconciliation_at=_now(),
        )
        return {
            "client_order_id": client_order_id,
            "state": str((updated or record).get("state") or current_state),
            "reconciled": False,
            "error": str(exc),
        }
    if not isinstance(result, Mapping):
        updated = _update_order_intent_by_id(
            self,
            client_order_id,
            state=current_state,
            last_reconciliation_error="Exchange returned an invalid order response.",
            last_reconciliation_at=_now(),
        )
        return {
            "client_order_id": client_order_id,
            "state": str((updated or record).get("state") or current_state),
            "reconciled": False,
            "error": "Exchange returned an invalid order response.",
        }
    exchange_status = str(result.get("status") or "").strip().upper()
    exchange_order_id = _exchange_order_id(result)
    if not exchange_status and not exchange_order_id:
        updated = _update_order_intent_by_id(
            self,
            client_order_id,
            state=current_state,
            last_reconciliation_error="Exchange did not confirm the order.",
            last_reconciliation_at=_now(),
        )
        return {
            "client_order_id": client_order_id,
            "state": str((updated or record).get("state") or current_state),
            "reconciled": False,
            "error": "Exchange did not confirm the order.",
        }
    resolved_state = "rejected" if exchange_status in _REJECTED_STATES else "accepted"
    updated = _update_order_intent_by_id(
        self,
        client_order_id,
        state=resolved_state,
        exchange_order_id=exchange_order_id,
        exchange_status=exchange_status,
        reconciled_at=_now(),
    )
    return {
        "client_order_id": client_order_id,
        "state": str((updated or record).get("state") or resolved_state),
        "reconciled": True,
        "exchange_status": exchange_status,
        "exchange_order_id": exchange_order_id,
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
    with _INTENT_LOCK:
        ledger = _read_ledger(path)
    intents = ledger.get("intents")
    records = list(intents.values()) if isinstance(intents, dict) else []
    unresolved = [
        record
        for record in records
        if isinstance(record, Mapping) and str(record.get("state") or "") in _UNRESOLVED_STATES
    ]
    return {
        "path": str(path),
        "format_version": _INTENT_FORMAT_VERSION,
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
