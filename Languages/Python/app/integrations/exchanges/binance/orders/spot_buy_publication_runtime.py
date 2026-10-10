"""Bind desktop BUY admission and publication to the original loaded source."""
from __future__ import annotations

import copy
import re
from collections.abc import Mapping
from contextlib import contextmanager

from app.settings.live_safety import LiveTradingSafetyError
from .order_intent_store import ledger_transaction, ledger_transactions


def desktop_source_descriptor(receipt):
    from .spot_allocation_generation_runtime import SpotBuyAdmissionReceipt
    if not isinstance(receipt, SpotBuyAdmissionReceipt):
        raise LiveTradingSafetyError("Desktop BUY source receipt is unavailable.")
    return {
        "version": 1, "allocation_path": str(receipt.allocation_path),
        "mode": receipt.mode, "snapshot_signature": receipt.snapshot_signature,
        "absent": receipt.raw is None, "generation": receipt.generation,
        "target_key": list(receipt.target_key), "client_order_ids": list(receipt.client_order_ids),
    }


def validate_desktop_source_descriptor(record: Mapping):
    descriptor = record.get("desktop_entry_source")
    if descriptor is None:
        return
    if not isinstance(descriptor, dict) or set(descriptor) != {
        "version", "allocation_path", "mode", "snapshot_signature", "absent",
        "generation", "target_key", "client_order_ids",
    }:
        raise LiveTradingSafetyError("Desktop BUY source descriptor is malformed.")
    from pathlib import Path
    from .spot_allocation_generation_runtime import spot_buy_admission_identity
    request = record.get("request") if record.get("type") == "OPO" else {
        "symbol": record.get("symbol"), "side": record.get("side"),
        "newClientOrderId": record.get("client_order_id"),
    }
    if not isinstance(request, Mapping):
        raise LiveTradingSafetyError("Desktop BUY source request is malformed.")
    key, ids = spot_buy_admission_identity(request)
    if (record.get("market") != "spot" or record.get("side") != "BUY"
        or type(descriptor["version"]) is not int or descriptor["version"] != 1
        or not isinstance(descriptor["allocation_path"], str)
        or not Path(descriptor["allocation_path"]).is_absolute()
        or descriptor["mode"] != "Live"
        or not isinstance(descriptor["snapshot_signature"], str)
        or re.fullmatch(r"[0-9a-f]{64}", descriptor["snapshot_signature"]) is None
        or type(descriptor["absent"]) is not bool
        or type(descriptor["generation"]) is not int or descriptor["generation"] < 0
        or descriptor["target_key"] != list(key) or descriptor["client_order_ids"] != list(ids)):
        raise LiveTradingSafetyError("Desktop BUY source descriptor conflicts with its intent.")


def capture_desktop_entry(self, params):
    capture = getattr(self, "_desktop_spot_entry_capture", None)
    if capture is None:
        return None
    if "listClientOrderId" in params:
        raise LiveTradingSafetyError(
            "Desktop OPO entry requires the dedicated exact-fill recovery workflow; automatic publication is unavailable."
        )
    check = getattr(self, "_desktop_spot_entry_check", None)
    if not callable(capture) or not callable(check):
        raise LiveTradingSafetyError("Desktop BUY admission boundary is unavailable.")
    origin = capture(params)
    receipt = getattr(origin, "admission_receipt", origin)
    desktop_source_descriptor(receipt)
    if check(origin, params) is not True:
        raise LiveTradingSafetyError("Desktop BUY origin requires reconciliation.")
    return origin, receipt


@contextmanager
def desktop_entry_transaction(self, intent_path, params, source):
    if source is None:
        from .order_intent_runtime import _spot_owner_scope
        if _spot_owner_scope(self) and (params.get("side") == "BUY" or "listClientOrderId" in params):
            from pathlib import Path
            from app.gui.shared.allocation_persistence import (
                _read_receipt, get_position_allocations_path, guard_position_allocation_snapshot,
            )
            from .spot_inventory_checkpoint_runtime import _owned_lifetime, _pin_authority, _assert_pin
            from .spot_inventory_checkpoint import _checkpoint_authority
            from .spot_inventory_namespace_runtime import namespace_for_owner
            namespace = namespace_for_owner(self)
            app_root = Path(__file__).resolve().parents[4]
            allocation_path = get_position_allocations_path(app_root / "gui" / "window_shell.py")
            with _owned_lifetime(self, intent_path), ledger_transactions(intent_path, allocation_path):
                pin = _pin_authority(self, intent_path, namespace)
                with _checkpoint_authority(lambda: _assert_pin(self, intent_path, namespace, pin)):
                    guard_position_allocation_snapshot(
                        allocation_path, _read_receipt(allocation_path), expected_namespace=namespace,
                    )
                    yield
                    guard_position_allocation_snapshot(
                        allocation_path, _read_receipt(allocation_path), expected_namespace=namespace,
                    )
        else:
            with ledger_transaction(intent_path):
                yield
        return
    origin, receipt = source
    check = getattr(self, "_desktop_spot_entry_check", None)
    if not callable(check) or check(origin, params) is not True:
        raise LiveTradingSafetyError("Desktop BUY source changed before submission.")
    from app.gui.shared.allocation_persistence import _read_receipt, guard_position_allocation_snapshot
    from .spot_inventory_namespace_runtime import namespace_for_owner
    from .spot_inventory_checkpoint_runtime import _owned_lifetime, _pin_authority, _assert_pin
    from .spot_inventory_checkpoint import _checkpoint_authority
    from app.gui.shared.trade_callback_origin import TradeCallbackOrigin, _matches_original_context, _window_maps_match_snapshot
    namespace = namespace_for_owner(self)
    with _owned_lifetime(self, intent_path), ledger_transactions(intent_path, receipt.allocation_path):
        pin = _pin_authority(self, intent_path, namespace)

        def assert_origin():
            _assert_pin(self, intent_path, namespace, pin)
            if not isinstance(origin, TradeCallbackOrigin) or origin.wrapper is not self or origin.admission_receipt != receipt:
                raise LiveTradingSafetyError("Desktop BUY lacks its original account receipt.")
            with origin.session._mutex:
                if (not _matches_original_context(origin.window, origin)
                        or not _window_maps_match_snapshot(origin.window, origin.session)
                        or origin.session.check_spot_buy_admission(receipt, params) is not True):
                    raise LiveTradingSafetyError("Desktop BUY original window changed during admission.")

        with _checkpoint_authority(assert_origin):
            observed = _read_receipt(receipt.allocation_path)
            guard_position_allocation_snapshot(receipt.allocation_path, observed, expected_namespace=namespace)
            if observed != (receipt.raw, receipt.identity):
                raise LiveTradingSafetyError("Desktop allocation changed before BUY submission.")
            handoff = origin.admission_handoff
            # Only the owned pure authority check runs under these locks. No callback,
            # account GET, refresh or portfolio marker may run in this handoff.
            with handoff(params):
                yield
                guard_position_allocation_snapshot(
                    receipt.allocation_path, _read_receipt(receipt.allocation_path), expected_namespace=namespace,
                )


def assert_desktop_entry_ledger(source, ledger):
    if source is None:
        return
    origin, _receipt = source
    binding = ledger.get("binding")
    if (ledger.get("store_id") != getattr(origin, "store_id", None)
        or not isinstance(binding, Mapping)
        or binding.get("environment") != getattr(origin, "environment", None)
        or binding.get("credential_fingerprint") != getattr(getattr(origin, "owner", None), "credential_fingerprint", None)):
        raise LiveTradingSafetyError("Desktop BUY ledger changed from its original execution store.")


def remember_desktop_entry(self, record, source, ledger):
    if source is None:
        return
    origin, receipt = source
    origins = getattr(self, "_desktop_spot_entry_origins", None)
    if not isinstance(origins, dict):
        origins = {}
        self._desktop_spot_entry_origins = origins
    origins[str(record["client_order_id"])] = {
        "origin": origin, "receipt": receipt, "binding": copy.deepcopy(ledger["binding"]),
        "store_id": ledger["store_id"],
        "params": copy.deepcopy(record["request"] if record.get("type") == "OPO" else {
            "symbol": record["symbol"], "side": "BUY", "newClientOrderId": record["client_order_id"],
        }),
    }


def desktop_entry_for_submission(self, record):
    descriptor = record.get("desktop_entry_source")
    if descriptor is None:
        if getattr(self, "_desktop_spot_entry_capture", None) is not None:
            raise LiveTradingSafetyError("Desktop BUY intent lacks its original source receipt.")
        return None
    validate_desktop_source_descriptor(record)
    origins = getattr(self, "_desktop_spot_entry_origins", {})
    saved = origins.get(str(record["client_order_id"])) if isinstance(origins, dict) else None
    if not isinstance(saved, dict) or desktop_source_descriptor(saved["receipt"]) != descriptor:
        raise LiveTradingSafetyError("Desktop BUY submission lost its original source; reconcile without resubmission.")
    return saved["origin"], saved["receipt"]


def _get_spot_buy_submission_origin(self, client_order_id):
    origins = getattr(self, "_desktop_spot_entry_origins", {})
    saved = origins.get(str(client_order_id)) if isinstance(origins, dict) else None
    return saved.get("origin") if isinstance(saved, dict) else None


def _capture_spot_buy_publication(self, fill):
    from .order_intent_runtime import _intent_path, _intent_binding, _read_ledger
    from .spot_allocation_generation_runtime import SpotBuyPublicationContext, validate_spot_buy_publication
    if not isinstance(fill, Mapping):
        raise LiveTradingSafetyError("Desktop BUY fill evidence is unavailable.")
    client_id = str(fill.get("client_order_id") or "")
    origins = getattr(self, "_desktop_spot_entry_origins", {})
    saved = origins.get(client_id) if isinstance(origins, dict) else None
    if not isinstance(saved, dict):
        raise LiveTradingSafetyError("Desktop BUY publication lost its submission origin.")
    from .spot_inventory_namespace_runtime import namespace_for_owner
    namespace = namespace_for_owner(self)
    origin = saved["origin"]
    if namespace["account_uid"] != origin.uid or namespace["store_id"] != saved["store_id"]:
        raise LiveTradingSafetyError("Desktop BUY publication account namespace changed.")
    path = _intent_path(self)
    receipt = saved["receipt"]
    with desktop_entry_transaction(self, path, saved["params"], (saved["origin"], receipt)):
        ledger = _read_ledger(path, expected_binding=_intent_binding(self))
        intents = ledger["intents"]
        record = intents.get(client_id) if isinstance(intents, dict) else None
        if (ledger["store_id"] != saved["store_id"] or ledger["binding"] != saved["binding"]
            or not isinstance(record, dict) or record.get("desktop_entry_source") != desktop_source_descriptor(receipt)):
            raise LiveTradingSafetyError("Desktop BUY publication no longer matches its bound intent.")
        context = SpotBuyPublicationContext(
            allocation_path=receipt.allocation_path, intent_path=path,
            expected_binding=copy.deepcopy(saved["binding"]), expected_intent=copy.deepcopy(record),
            expected_store_id=str(saved["store_id"]), namespace=namespace,
            fill=copy.deepcopy(dict(fill)), entry_source_receipt=receipt, origin=origin,
        )
        validate_spot_buy_publication(context, record)
    return context
