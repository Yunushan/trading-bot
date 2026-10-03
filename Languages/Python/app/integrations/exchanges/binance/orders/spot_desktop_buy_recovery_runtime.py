"""Explicit local desktop recovery from a durable terminal Spot BUY receipt."""
from __future__ import annotations

from collections.abc import Callable, Mapping
from contextlib import AbstractContextManager
from copy import deepcopy
from dataclasses import dataclass, field
from decimal import Decimal
import hashlib
import json
from pathlib import Path
from typing import Any, cast

from app.gui.shared import allocation_persistence as allocations
from app.security.redaction import redact_text
from app.settings.live_safety import LiveTradingSafetyError
from app.settings.execution_mode import execution_environment

from . import order_intent_runtime as intents
from .order_intent_store import ledger_transaction, ledger_transactions
from .spot_allocation_generation_runtime import canonical_spot_buy_metadata, validate_spot_entry_snapshot
from .spot_buy_publication_runtime import validate_desktop_source_descriptor
from .spot_execution_owner import (
    _read_marker, mark_owner_recovery_required_locked, owner_administration_lock, owner_marker_path,
)
from .spot_fill_recovery_runtime import (
    _persist_spot_buy_allocation_unlocked, _stored_decimal, _update_spot_position_snapshot,
)
from .spot_exchange_errors import SPOT_LOCAL_STATE_ERRORS


@dataclass(frozen=True, repr=False)
class SpotDesktopBuyRecoveryAuthority:
    wrapper: Any = field(repr=False)
    account_uid: int
    environment: str
    intent_path: Path
    binding: dict = field(repr=False)
    store_id: str
    allocation_path: Path
    _wrapper_context: tuple = field(repr=False)


@dataclass(frozen=True)
class SpotDesktopBuyRecoveryWorkItem:
    authority: SpotDesktopBuyRecoveryAuthority = field(repr=False)
    client_order_id: str
    symbol: str
    order_id: int
    exchange_status: str
    expected_record: dict = field(repr=False)
    _record_signature: str = field(repr=False)


@dataclass(frozen=True)
class SpotDesktopBuyRecoveryDiscovery:
    authority: SpotDesktopBuyRecoveryAuthority = field(repr=False)
    items: tuple[SpotDesktopBuyRecoveryWorkItem, ...]
    unresolved_count: int
    unsupported_count: int


@dataclass(frozen=True, repr=False)
class SpotDesktopBuyRecoveryLoadedReceipt:
    session: allocations.AllocationSnapshotSession
    allocation_path: Path
    raw: bytes | None
    identity: tuple[int, int, int, int] | None
    generation: int
    snapshot: dict | None
    _allocations: dict
    _records: dict


def _signature(record: Mapping) -> str:
    return hashlib.sha256(json.dumps(dict(record), sort_keys=True, separators=(",", ":"),
                                     allow_nan=False).encode("utf-8")).hexdigest()


def _canonical_path() -> Path:
    app_root = Path(__file__).resolve().parents[4]
    return cast(Path, allocations.get_position_allocations_path(app_root / "gui" / "window_shell.py"))


def _wrapper_context(wrapper) -> tuple:
    return (wrapper.api_key, wrapper.api_secret, wrapper.mode, wrapper.account_type, wrapper.client)


def _signed_selected_uid(wrapper) -> int:
    if (not intents._spot_owner_scope(wrapper) or execution_environment(wrapper.mode) != "live"
            or getattr(wrapper, "_spot_execution_revoked", False)):
        raise LiveTradingSafetyError("Desktop BUY recovery requires the current Live Spot account wrapper.")
    uid = wrapper._resolve_spot_account_uid()
    if type(uid) is not int or uid <= 0:
        raise LiveTradingSafetyError("Desktop BUY recovery signed account UID is invalid.")
    response = wrapper._http_signed_spot("/v3/account")
    if (not isinstance(response, Mapping) or "code" in response or response.get("accountType") != "SPOT"
            or type(response.get("uid")) is not int or response["uid"] != uid):
        raise LiveTradingSafetyError("Desktop BUY recovery signed account identity changed.")
    return int(uid)


def _assert_authority(wrapper, authority: SpotDesktopBuyRecoveryAuthority) -> None:
    if (not isinstance(authority, SpotDesktopBuyRecoveryAuthority) or wrapper is not authority.wrapper
            or _wrapper_context(wrapper) != authority._wrapper_context
            or getattr(wrapper, "_spot_execution_revoked", False)
            or not intents._spot_owner_scope(wrapper)
            or intents._intent_path(wrapper) != authority.intent_path
            or intents._intent_binding(wrapper) != authority.binding
            or authority.allocation_path != _canonical_path()):
        raise LiveTradingSafetyError("Desktop BUY recovery account or storage context changed.")


def _primary_fill(record: Mapping) -> dict:
    proof = record.get("primary_fill_receipt")
    if (record.get("market") != "spot" or record.get("type") != "MARKET" or record.get("side") != "BUY"
            or record.get("state") != "accepted" or record.get("portfolio_reconciled") is True
            or record.get("exchange_status") != "FILLED"
            or not isinstance(proof, Mapping)):
        raise LiveTradingSafetyError("Desktop recovery requires an unmarked accepted terminal primary Spot MARKET BUY receipt.")
    fill = {**deepcopy(dict(proof)), "symbol": record["symbol"], "client_order_id": record["client_order_id"],
            "portfolio_qty": proof["net_qty"],
            "average_cost": format(Decimal(proof["net_quote_cost"]) / Decimal(proof["net_qty"]), "f")}
    if (canonical_spot_buy_metadata(fill) != proof or proof["signature"] != record.get("primary_fill_signature")
            or proof["exchange_client_order_id"] != record.get("client_order_id")
            or str(proof["order_id"]) != str(record.get("exchange_order_id"))
            or Decimal(proof["gross_qty"]) != Decimal(str(record.get("executed_qty")))
            or Decimal(proof["net_qty"]) != Decimal(str(record.get("portfolio_qty")))):
        raise LiveTradingSafetyError("Desktop BUY recovery primary receipt conflicts with its durable intent.")
    return fill


def discover_spot_desktop_buy_recoveries(wrapper, *, allocation_path: Path) -> SpotDesktopBuyRecoveryDiscovery:
    """Read work only from the freshly verified selected account, without arming it."""
    if allocation_path != _canonical_path():
        raise LiveTradingSafetyError("Desktop BUY recovery requires the canonical allocation path.")
    uid = _signed_selected_uid(wrapper)
    path, binding = intents._intent_path(wrapper), intents._intent_binding(wrapper)
    with owner_administration_lock(path), ledger_transaction(path):
        ledger = intents._read_ledger(path, expected_binding=binding)
        _read_marker(owner_marker_path(path), uid=uid, environment=binding["environment"], store_id=str(ledger["store_id"]))
        authority = SpotDesktopBuyRecoveryAuthority(
            wrapper, uid, binding["environment"], path, deepcopy(binding), str(ledger["store_id"]),
            allocation_path, _wrapper_context(wrapper),
        )
        records = ledger["intents"]
        if not isinstance(records, dict):
            raise LiveTradingSafetyError("Desktop BUY recovery intent store is malformed.")
        items = []
        unresolved = 0
        for record in records.values():
            if not intents._is_unresolved(record):
                continue
            unresolved += 1
            if (record.get("market") != "spot" or record.get("type") != "MARKET"
                    or record.get("side") != "BUY" or record.get("state") != "accepted"
                    or record.get("portfolio_reconciled") is True or "primary_fill_receipt" not in record):
                continue
            fill = _primary_fill(record)
            expected = deepcopy(record)
            items.append(SpotDesktopBuyRecoveryWorkItem(
                authority, str(record["client_order_id"]), str(record["symbol"]), int(fill["order_id"]),
                str(record["exchange_status"]), expected, _signature(expected),
            ))
        _assert_authority(wrapper, authority)
    return SpotDesktopBuyRecoveryDiscovery(authority, tuple(items), unresolved, unresolved - len(items))


def capture_spot_desktop_buy_recovery_source(
    session: allocations.AllocationSnapshotSession, entry_allocations: dict, open_position_records: dict,
    *, allocation_path: Path,
) -> SpotDesktopBuyRecoveryLoadedReceipt:
    """Capture a newly loaded session and its complete actual maps; never load to bless stale maps."""
    if not isinstance(session, allocations.AllocationSnapshotSession) or allocation_path != _canonical_path():
        raise LiveTradingSafetyError("Desktop BUY recovery loaded allocation source is unavailable.")
    with session._mutex:
        captured = session._capture()
        if (not captured[6] or captured[0] != allocation_path or captured[1] != "Live"
                or not session.matches_loaded_maps(entry_allocations, open_position_records)):
            raise LiveTradingSafetyError("Desktop BUY recovery maps differ from their loaded Live source.")
        return SpotDesktopBuyRecoveryLoadedReceipt(
            session, allocation_path, captured[2], captured[3], captured[5], captured[4],
            entry_allocations, open_position_records,
        )


def _assert_source(source: SpotDesktopBuyRecoveryLoadedReceipt, allocation_path: Path) -> None:
    if not isinstance(source, SpotDesktopBuyRecoveryLoadedReceipt) or source.allocation_path != allocation_path:
        raise LiveTradingSafetyError("Desktop BUY recovery source receipt changed.")
    current = source.session._capture()
    if (current != (allocation_path, "Live", source.raw, source.identity, source.snapshot, source.generation, True)
            or not source.session.matches_loaded_maps(source._allocations, source._records)
            or allocations._read_receipt(allocation_path) != (source.raw, source.identity)):
        raise LiveTradingSafetyError("Desktop BUY recovery loaded source changed before publication.")


def _validate_current_snapshot(snapshot: Mapping | None, symbol: str) -> None:
    """Validate the current target projection independently of historical acquisition proof."""
    validate_spot_entry_snapshot(snapshot, symbol, ())
    if snapshot is None:
        return
    key = f"{symbol}:L"
    for stored_key, rows in snapshot["entry_allocations"].items():
        if stored_key != key and any(row.get("symbol") == symbol and str(row.get("status")).lower() == "active"
                                     for row in rows):
            raise LiveTradingSafetyError("Desktop BUY recovery active inventory exists outside its canonical target.")
    active = [deepcopy(row) for row in snapshot["entry_allocations"].get(key, [])
              if str(row.get("status") or "").lower() == "active"]
    if not active:
        return
    record = snapshot["open_position_records"][key]
    data = record["data"]
    if (record.get("symbol") != symbol or record.get("side_key") != "L"
            or not isinstance(record.get("status"), str) or record["status"].lower() != "active"
            or data.get("symbol") != symbol or data.get("side_key") != "L"
            or ("status" in data and (not isinstance(data["status"], str) or data["status"].lower() != "active"))):
        raise LiveTradingSafetyError("Desktop BUY recovery current position identity/status is incoherent.")
    expected = deepcopy(dict(record))
    _update_spot_position_snapshot(expected, symbol=symbol, active_entries=active)
    if record["allocations"] != expected["allocations"]:
        raise LiveTradingSafetyError("Desktop BUY recovery current allocation view is incoherent.")
    for name in ("qty", "entry_price", "margin_usdt", "size_usdt"):
        if (_stored_decimal(data.get(name), f"current position {name}", positive=True)
                != _stored_decimal(expected["data"][name], f"derived position {name}", positive=True)):
            raise LiveTradingSafetyError(f"Desktop BUY recovery current position {name} is incoherent.")


def _already_present(record: dict, source: SpotDesktopBuyRecoveryLoadedReceipt, fill: dict) -> bool:
    _validate_current_snapshot(source.snapshot, str(record["symbol"]))
    rows = [row for group in (source.snapshot or {}).get("entry_allocations", {}).values() for row in group
            if row.get("client_order_id") == record["client_order_id"]]
    if not rows:
        validate_desktop_source_descriptor(record)
        descriptor = record.get("desktop_entry_source")
        if (not isinstance(descriptor, Mapping) or descriptor["allocation_path"] != str(source.allocation_path)
                or descriptor["mode"] != "Live" or descriptor["absent"] != (source.raw is None)
                or descriptor["snapshot_signature"] != hashlib.sha256(source.raw or b"").hexdigest()):
            raise LiveTradingSafetyError("Missing desktop BUY acquisition no longer matches its original source baseline.")
        return False
    if len(rows) != 1 or not intents._has_durable_spot_buy_allocation(
        record, portfolio_signature=str(fill["signature"]), portfolio_quantity=Decimal(fill["net_qty"]),
    ):
        raise LiveTradingSafetyError("Existing desktop BUY acquisition has conflicting or unconserved evidence.")
    return True


def _mark_exact_acquisition(wrapper, authority: SpotDesktopBuyRecoveryAuthority, record: dict, fill: dict) -> dict:
    """Commit only this work item's account/store/record and exact retained acquisition."""
    quantity = Decimal(fill["net_qty"])
    signature = str(fill["signature"])
    with ledger_transactions(authority.intent_path, authority.allocation_path):
        _assert_authority(wrapper, authority)
        ledger = intents._read_ledger(authority.intent_path, expected_binding=authority.binding)
        records = ledger["intents"]
        current = records.get(record["client_order_id"]) if isinstance(records, dict) else None
        if ledger["store_id"] != authority.store_id or not isinstance(current, dict) or current != record:
            raise LiveTradingSafetyError("Desktop BUY recovery store or work item changed during acquisition confirmation.")
        marker = _read_marker(owner_marker_path(authority.intent_path), uid=authority.account_uid,
                              environment=authority.environment, store_id=authority.store_id)
        if marker["state"] != "recovery_required":
            raise LiveTradingSafetyError("Desktop BUY recovery owner state changed during acquisition confirmation.")
        raw, _identity = allocations._read_receipt(authority.allocation_path)
        snapshot = allocations._decode(raw, "Live") if raw is not None else None
        _validate_current_snapshot(snapshot, str(record["symbol"]))
        if not intents._has_durable_spot_buy_allocation(
            current, portfolio_signature=signature, portfolio_quantity=quantity,
        ):
            raise LiveTradingSafetyError("Desktop BUY recovery exact acquisition is no longer durable.")
        already = current.get("portfolio_reconciled") is True
        if already:
            if (current.get("portfolio_recovery_signature") != signature
                    or Decimal(str(current.get("portfolio_qty"))) != quantity):
                raise LiveTradingSafetyError("Desktop BUY acquisition receipt conflicts with its intent.")
        else:
            current.update({"state": "accepted", "portfolio_reconciled": True,
                            "portfolio_qty": format(quantity, "f"), "portfolio_recovery_signature": signature,
                            "portfolio_reconciled_at": intents._now(), "updated_at": intents._now()})
            intents._write_ledger(authority.intent_path, ledger)
    return {"portfolio_reconciled": True, "already_reconciled": already}


def recover_spot_desktop_buy(
    wrapper, item: SpotDesktopBuyRecoveryWorkItem, *, allocation_path: Path,
    expected_loaded_receipt: SpotDesktopBuyRecoveryLoadedReceipt,
    publication_handoff: Callable[[], AbstractContextManager],
) -> dict:
    """Recover local inventory once, then mark exact acquisition; never POST, rearm or clear GUI fences."""
    if not isinstance(item, SpotDesktopBuyRecoveryWorkItem) or not callable(publication_handoff):
        raise LiveTradingSafetyError("Desktop BUY recovery work item or publication handoff is unavailable.")
    authority = item.authority
    _assert_authority(wrapper, authority)
    if allocation_path != authority.allocation_path or _signed_selected_uid(wrapper) != authority.account_uid:
        raise LiveTradingSafetyError("Desktop BUY recovery selected account changed.")
    record = deepcopy(item.expected_record)
    if (_signature(record) != item._record_signature or record.get("client_order_id") != item.client_order_id
            or record.get("symbol") != item.symbol or str(record.get("exchange_order_id")) != str(item.order_id)):
        raise LiveTradingSafetyError("Desktop BUY recovery work item changed from its durable receipt.")
    fill = _primary_fill(record)
    source = expected_loaded_receipt
    if not isinstance(source, SpotDesktopBuyRecoveryLoadedReceipt):
        raise LiveTradingSafetyError("Desktop BUY recovery source receipt is unavailable.")
    with owner_administration_lock(authority.intent_path):
        marker = _read_marker(owner_marker_path(authority.intent_path), uid=authority.account_uid,
                              environment=authority.environment, store_id=authority.store_id)
        with ledger_transactions(authority.intent_path, allocation_path), source.session._mutex, publication_handoff():
            _assert_authority(wrapper, authority)
            ledger = intents._read_ledger(authority.intent_path, expected_binding=authority.binding)
            records = ledger["intents"]
            if (ledger["store_id"] != authority.store_id or not isinstance(records, dict)
                    or records.get(item.client_order_id) != record):
                raise LiveTradingSafetyError("Desktop BUY recovery intent or store changed before publication.")
            _assert_source(source, allocation_path)
            already_present = _already_present(record, source, fill)
            if marker["state"] != "recovery_required":
                mark_owner_recovery_required_locked(
                    authority.intent_path, uid=authority.account_uid, environment=authority.environment,
                    store_id=authority.store_id, reconciliation_reference=f"desktop-buy-{item.client_order_id}",
                )
            source.session.invalidate("desktop BUY recovery requires a fresh allocation reload")
            if _persist_spot_buy_allocation_unlocked(allocation_path, fill) is not True:
                raise LiveTradingSafetyError("Desktop BUY recovery allocation publication did not complete.")
            if not intents._has_durable_spot_buy_allocation(
                record, portfolio_signature=str(fill["signature"]), portfolio_quantity=Decimal(fill["net_qty"]),
            ):
                raise LiveTradingSafetyError("Desktop BUY recovery has no exact durable acquisition after publication.")
            committed = allocations._read_receipt(allocation_path)
            committed_generation = source.session._generation
        result = {
            "client_order_id": item.client_order_id, "account_uid": authority.account_uid,
            "environment": authority.environment, "store_id": authority.store_id,
            "allocation_published": True, "already_present": already_present, "portfolio_reconciled": False,
            "already_reconciled": False, "recovery_required": True,
            "allocation_receipt": committed, "session_generation": committed_generation,
        }
        try:
            _assert_authority(wrapper, authority)
            marked = _mark_exact_acquisition(wrapper, authority, record, fill)
            _assert_authority(wrapper, authority)
        except SPOT_LOCAL_STATE_ERRORS as exc:
            result["error"] = redact_text(exc) or "Desktop BUY acquisition confirmation did not complete."
            return result
        result.update(portfolio_reconciled=marked["portfolio_reconciled"],
                      already_reconciled=marked["already_reconciled"])
        return result
