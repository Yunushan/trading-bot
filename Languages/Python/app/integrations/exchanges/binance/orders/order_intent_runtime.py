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

from .order_intent_store import ledger_transaction, write_ledger
from .spot_execution_owner import SpotExecutionOwner, claim_execution_owner


_INTENT_FORMAT_VERSION = 2
_BLOCKING_STATES = {"pending", "submitted", "unknown", "accepted"}
_UNRESOLVED_STATES = {"pending", "submitted", "unknown"}
_ORDER_STATUSES = {"NEW", "PARTIALLY_FILLED", "FILLED", "CANCELED", "REJECTED", "EXPIRED", "EXPIRED_IN_MATCH"}
_SPOT_PENDING_STATUSES = {"PENDING_NEW", "PENDING_CANCEL"}


def _requires_execution_confirmation(record: Mapping[str, object]) -> bool:
    return bool(record.get("requires_close_confirmation")) or (
        record.get("market") in {"spot", "futures"} and record.get("type") == "MARKET"
    )


def _is_unresolved(record: Mapping[str, object]) -> bool:
    if record.get("state") in _UNRESOLVED_STATES:
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
        if "portfolio_reconciled" in record and type(record["portfolio_reconciled"]) is not bool:
            raise LiveTradingSafetyError("Order intent ledger contains an invalid portfolio recovery marker.")
        if record.get("portfolio_reconciled") is True and (
            record.get("market") != "spot"
            or record.get("type") != "MARKET"
            or record.get("side") != "BUY"
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
                or portfolio_qty > executed_qty
                or not isinstance(record.get("portfolio_recovery_signature"), str)
                or re.fullmatch(r"[0-9a-f]{64}", record["portfolio_recovery_signature"]) is None
            ):
                raise LiveTradingSafetyError("Order intent ledger contains an invalid portfolio recovery proof.")
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


def _begin_order_intent(self, params: Mapping[str, object], *, market: str, source: str) -> dict[str, object]:
    if market == "spot" and getattr(self, "_enforce_spot_execution_owner", False) and (
        is_live_trading_mode(getattr(self, "mode", None))
        or getattr(self, "_spot_owner_initial_live", False)
    ):
        if not _spot_owner_scope(self):
            raise LiveTradingSafetyError("Spot execution owner requires a Spot account wrapper.")
        _ensure_spot_execution_owner(self)
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
        quantity = Decimal(str(entry.get("qty") or "NaN"))
        expected_quantity = Decimal(str(portfolio_quantity or record.get("portfolio_qty") or "NaN"))
        return (
            entry.get("symbol") == record.get("symbol")
            and entry.get("side_key") == "L"
            and str(entry.get("status") or "").lower() == "active"
            and isinstance(fill_evidence, Mapping)
            and fill_evidence.get("signature") == portfolio_signature
            and quantity.is_finite()
            and expected_quantity.is_finite()
            and quantity == expected_quantity
        )
    except Exception:
        return False


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
        or record.get("side") != "BUY"
        or record.get("exchange_status") not in _ORDER_STATUSES - {"NEW", "PARTIALLY_FILLED"}
    ):
        raise LiveTradingSafetyError("Only a terminal Spot market BUY can be marked portfolio-reconciled.")
    if record.get("portfolio_reconciled") is True:
        if (
            record.get("portfolio_recovery_signature") != portfolio_signature
            or str(record.get("portfolio_qty")) != str(portfolio_quantity or record.get("portfolio_qty"))
        ):
            raise LiveTradingSafetyError("Spot portfolio recovery proof conflicts with the stored intent.")
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
        or expected_quantity > executed_quantity
    ):
        raise LiveTradingSafetyError("Spot portfolio recovery quantity is invalid.")
    if record.get("primary_fill_signature") and record["primary_fill_signature"] != portfolio_signature:
        raise LiveTradingSafetyError("Spot portfolio recovery proof conflicts with the primary fill evidence.")
    if not _has_durable_spot_buy_allocation(
        record, portfolio_signature=portfolio_signature, portfolio_quantity=expected_quantity,
    ):
        raise LiveTradingSafetyError("A matching durable Live Spot BUY allocation was not found.")
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
    status = get_order_intent_status(self)
    client_order_ids = status.get("unresolved_client_order_ids")
    if not isinstance(client_order_ids, list):
        return []
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
    return {
        "path": str(path),
        "format_version": _INTENT_FORMAT_VERSION,
        "storage_ready": True,
        "intent_count": len(records),
        "unresolved_count": len(unresolved),
        "unresolved_client_order_ids": [str(record.get("client_order_id") or "") for record in unresolved],
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
        local_status = local_record.get("exchange_status")
        if (
            local_record.get("state") == "rejected"
            or not isinstance(local_status, str)
            or local_status.strip().upper() not in open_statuses
        ):
            local_status_conflicts += 1
            continue
        local_order_id = local_record.get("exchange_order_id")
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
    wrapper_cls._begin_order_intent = _begin_order_intent
    wrapper_cls._mark_order_intent_submitted = _mark_order_intent_submitted
    wrapper_cls._mark_order_intent_accepted = _mark_order_intent_accepted
    wrapper_cls._mark_order_intent_unknown = _mark_order_intent_unknown
    wrapper_cls._mark_order_intent_portfolio_reconciled = _mark_order_intent_portfolio_reconciled
    wrapper_cls._query_order_intent_exchange = _query_order_intent_exchange
    wrapper_cls.reconcile_order_intent = reconcile_order_intent
    wrapper_cls.reconcile_unresolved_order_intents = reconcile_unresolved_order_intents
    wrapper_cls.get_order_intent_status = get_order_intent_status
