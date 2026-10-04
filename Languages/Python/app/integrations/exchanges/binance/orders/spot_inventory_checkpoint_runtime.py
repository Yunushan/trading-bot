"""Genuine owned authority for protected inventory publication primitives.

The ordinary product callers must still validate the canonical fill/candidate.
This boundary does not make a caller-selected namespace or detached token into
execution authority. It performs no venue request or portfolio marker callback.
"""
from __future__ import annotations

from collections.abc import Iterator, Mapping
from contextlib import contextmanager
from contextvars import ContextVar
from copy import deepcopy
from dataclasses import dataclass, field
import hashlib
import json
import os
from pathlib import Path
import threading

from app.settings.live_safety import LiveTradingSafetyError

from . import spot_inventory_checkpoint as checkpoints
from .order_intent_store import current_ledger_deadline, ledger_transactions
from .spot_inventory_namespace import ACCOUNT_NAMESPACE_KEY, is_strictly_empty_live_snapshot
from .spot_inventory_namespace_runtime import namespace_for_ledger, namespace_for_owner


_PROCESS_ID = os.getpid()


def _fail() -> LiveTradingSafetyError:
    return LiveTradingSafetyError("Protected Spot inventory requires its original owned publication authority.")


def _canonical_paths(wrapper, allocation_path: Path) -> Path:
    from app.gui.shared.allocation_persistence import get_position_allocations_path
    from .order_intent_runtime import _intent_path
    app_root = Path(__file__).resolve().parents[4]
    if _PROCESS_ID != os.getpid() or allocation_path != get_position_allocations_path(app_root / "gui" / "window_shell.py"):
        raise _fail()
    path = _intent_path(wrapper)
    if not isinstance(path, Path):
        raise _fail()
    return path


@contextmanager
def _owned_lifetime(wrapper, intent_path: Path) -> Iterator[None]:
    """Retain real owner exclusion without waiting in an inverted storage order."""
    from .spot_execution_owner import SpotExecutionOwner, assert_owner_administration_held
    if _PROCESS_ID != os.getpid():
        raise _fail()
    owner = getattr(wrapper, "_spot_execution_owner", None)
    if owner is None:
        assert_owner_administration_held(intent_path)
        yield
        assert_owner_administration_held(intent_path)
        return
    if not isinstance(owner, SpotExecutionOwner) or owner.pid != os.getpid():
        raise _fail()
    # Some canonical callers already hold storage locks. Waiting for a submitter
    # that needs those locks would invert the existing owner->storage order.
    lock = owner._submission_lock
    if not lock.acquire(blocking=False):
        raise LiveTradingSafetyError("Spot publication owner is busy; reconciliation is required.")
    try:
        if getattr(wrapper, "_spot_execution_owner", None) is not owner:
            raise _fail()
        namespace_for_owner(wrapper)
        yield
        if getattr(wrapper, "_spot_execution_owner", None) is not owner:
            raise _fail()
        namespace_for_owner(wrapper)
    finally:
        lock.release()


def _read_owned(wrapper, allocation_path: Path):
    from app.gui.shared.allocation_persistence import _decode, _read_receipt
    from .order_intent_runtime import _intent_binding, _read_ledger
    path = _canonical_paths(wrapper, allocation_path)
    current_ledger_deadline(path, allocation_path)
    ledger = _read_ledger(path, expected_binding=_intent_binding(wrapper))
    namespace = namespace_for_ledger(wrapper, ledger)
    if namespace is None:
        raise _fail()
    raw, _identity = _read_receipt(allocation_path)
    snapshot = _decode(raw, "Live") if raw is not None else None
    return path, ledger, namespace, raw, snapshot


@dataclass(frozen=True, repr=False)
class _AuthorityPin:
    owner: object
    administration: object
    generation: int
    binding: dict = field(repr=False)
    context: tuple = field(repr=False)
    client: object = field(repr=False)


def _pin_authority(wrapper, path: Path, namespace: Mapping) -> _AuthorityPin:
    from .order_intent_runtime import _intent_binding
    from .spot_execution_owner import _ADMINISTRATION, _read_marker, owner_marker_path
    owner = getattr(wrapper, "_spot_execution_owner", None)
    administration = _ADMINISTRATION.get() if owner is None else None
    context = getattr(wrapper, "_verified_spot_account_context", None)
    if not isinstance(context, tuple) or len(context) != 5 or context[3] is not getattr(wrapper, "client", None):
        raise _fail()
    generation = (getattr(owner, "generation", None) if owner is not None else
                  _read_marker(owner_marker_path(path), uid=namespace["account_uid"], environment="live",
                               store_id=str(namespace["store_id"]))["generation"])
    if type(generation) is not int or owner is None and administration is None:
        raise _fail()
    return _AuthorityPin(owner, administration, generation, deepcopy(_intent_binding(wrapper)), context,
                         getattr(wrapper, "client", None))


def _assert_pin(wrapper, path: Path, namespace: Mapping, pin: _AuthorityPin) -> None:
    from .order_intent_runtime import _intent_binding
    from .spot_execution_owner import (
        _ADMINISTRATION, _read_marker, owner_marker_path, assert_owner_administration_held, SpotExecutionOwner,
    )
    context = getattr(wrapper, "_verified_spot_account_context", None)
    if (getattr(wrapper, "_spot_execution_owner", None) is not pin.owner
            or getattr(wrapper, "client", None) is not pin.client or not isinstance(context, tuple)
            or len(context) != 5 or context[:3] != pin.context[:3]
            or context[3] is not pin.context[3] or context[4] != pin.context[4]
            or _intent_binding(wrapper) != pin.binding):
        raise _fail()
    if pin.owner is not None:
        if not isinstance(pin.owner, SpotExecutionOwner) or pin.owner.generation != pin.generation:
            raise _fail()
        pin.owner.assert_held(uid=namespace["account_uid"], environment=pin.binding["environment"],
                              credential_fingerprint=pin.binding["credential_fingerprint"], owner_wrapper=wrapper)
    elif (_ADMINISTRATION.get() is not pin.administration
          or _read_marker(owner_marker_path(path), uid=namespace["account_uid"], environment="live",
                          store_id=str(namespace["store_id"]))["generation"] != pin.generation):
        raise _fail()
    if pin.owner is None:
        assert_owner_administration_held(path)


def _assert_history(wrapper, path: Path, allocation_path: Path, namespace: Mapping,
                    pin: _AuthorityPin, record: Mapping | None = None) -> None:
    """Recheck the original complete history at each native publication phase."""
    from .order_intent_runtime import _intent_binding, _read_ledger
    _assert_pin(wrapper, path, namespace, pin)
    current_ledger_deadline(path, allocation_path)
    if _canonical_paths(wrapper, allocation_path) != path:
        raise _fail()
    ledger = _read_ledger(path, expected_binding=_intent_binding(wrapper))
    records = ledger.get("intents")
    if (namespace_for_ledger(wrapper, ledger) != namespace or not isinstance(records, dict)
            or (records != {} if record is None else records.get(record.get("client_order_id")) != record)):
        raise _fail()
    _assert_pin(wrapper, path, namespace, pin)


def _event_operation(namespace: Mapping, record: Mapping, fill: Mapping) -> str:
    client = record.get("client_order_id")
    if (not isinstance(client, str) or not client or fill.get("client_order_id") != client
            or record.get("market") != "spot" or record.get("state") != "accepted"):
        raise _fail()
    value = {"version": 1, "namespace": dict(namespace), "client_order_id": client,
             "kind": record.get("entry_type") or record.get("side"), "fill": deepcopy(dict(fill))}
    encoded = json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _bootstrap_operation(namespace: Mapping) -> str:
    encoded = json.dumps({"version": 1, "kind": "empty-bootstrap", "namespace": dict(namespace)},
                         sort_keys=True, separators=(",", ":"), allow_nan=False).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def bootstrap_owned_inventory_checkpoint(wrapper, *, allocation_path: Path) -> bool:
    """Bind only actual fresh empty history; never adopt existing bound state."""
    path = _canonical_paths(wrapper, allocation_path)
    with _owned_lifetime(wrapper, path), ledger_transactions(path, allocation_path):
        _path, ledger, namespace, raw, snapshot = _read_owned(wrapper, allocation_path)
        if namespace_for_owner(wrapper) != namespace:
            raise _fail()
        pin = _pin_authority(wrapper, path, namespace)
        if checkpoints.verify_inventory_checkpoint(allocation_path, raw, snapshot, expected_namespace=namespace):
            _assert_pin(wrapper, path, namespace, pin)
            return False
        if ledger.get("intents") != {} or not is_strictly_empty_live_snapshot(snapshot):
            raise LiveTradingSafetyError("Protected Spot inventory bootstrap requires complete empty history.")
        candidate = deepcopy(snapshot) if snapshot is not None else {
            "version": 1, "mode": "Live", "entry_allocations": {}, "open_position_records": {},
        }
        candidate[ACCOUNT_NAMESPACE_KEY] = namespace
        with checkpoints._checkpoint_authority(lambda: _assert_history(wrapper, path, allocation_path, namespace, pin)):
            checkpoints._bootstrap_inventory_checkpoint(
                allocation_path, raw, snapshot, candidate, namespace, _bootstrap_operation(namespace),
            )
        _assert_pin(wrapper, path, namespace, pin)
        _read_owned(wrapper, allocation_path)
        return True


def recover_owned_inventory_bootstrap(wrapper, *, allocation_path: Path) -> bool:
    """Explicitly finish the pinned first empty write; do not reconstruct or clear it."""
    path = _canonical_paths(wrapper, allocation_path)
    with _owned_lifetime(wrapper, path), ledger_transactions(path, allocation_path):
        _path, ledger, namespace, _raw, _snapshot = _read_owned(wrapper, allocation_path)
        if namespace_for_owner(wrapper) != namespace or ledger.get("intents") != {}:
            raise _fail()
        pin = _pin_authority(wrapper, path, namespace)
        with checkpoints._checkpoint_authority(lambda: _assert_history(wrapper, path, allocation_path, namespace, pin)):
            result = checkpoints._recover_inventory_checkpoint(allocation_path, namespace, _bootstrap_operation(namespace))
        _assert_pin(wrapper, path, namespace, pin)
        _read_owned(wrapper, allocation_path)
        if type(result) is not bool:
            raise _fail()
        return bool(result)


@dataclass(repr=False)
class _Publication:
    wrapper: object = field(repr=False)
    allocation_path: Path
    intent_path: Path
    namespace: dict = field(repr=False)
    record: dict = field(repr=False)
    operation: str = field(repr=False)
    authority: _AuthorityPin = field(repr=False)
    pid: int
    thread: int
    active: bool = True
    written: bool = False


_ACTIVE: ContextVar[_Publication | None] = ContextVar("spot_protected_inventory_publication", default=None)


def _assert_publication(value: _Publication, allocation_path: Path) -> None:
    if (not value.active or value.pid != os.getpid() or value.thread != threading.get_ident()
            or _ACTIVE.get() is not value or value.allocation_path != allocation_path):
        raise _fail()
    _assert_pin(value.wrapper, value.intent_path, value.namespace, value.authority)
    path, ledger, namespace, _raw, _snapshot = _read_owned(value.wrapper, allocation_path)
    records = ledger.get("intents")
    if (path != value.intent_path or namespace != value.namespace or not isinstance(records, dict)
            or records.get(value.record.get("client_order_id")) != value.record):
        raise _fail()


@contextmanager
def owned_inventory_publication(wrapper, *, allocation_path: Path, expected_record: Mapping, fill: Mapping) -> Iterator[None]:
    """Keep exact original record authority under both locks, including prepared recovery."""
    path = _canonical_paths(wrapper, allocation_path)
    record, original_fill = deepcopy(dict(expected_record)), deepcopy(dict(fill))
    with _owned_lifetime(wrapper, path), ledger_transactions(path, allocation_path):
        _path, ledger, namespace, _raw, _snapshot = _read_owned(wrapper, allocation_path)
        records = ledger.get("intents")
        if not isinstance(records, dict) or records.get(record.get("client_order_id")) != record or _ACTIVE.get() is not None:
            raise _fail()
        operation = _event_operation(namespace, record, original_fill)
        pin = _pin_authority(wrapper, path, namespace)
        with checkpoints._checkpoint_authority(lambda: _assert_history(wrapper, path, allocation_path, namespace, pin, record)):
            checkpoints._recover_inventory_checkpoint(allocation_path, namespace, operation)
            _assert_pin(wrapper, path, namespace, pin)
            _path, _ledger, _namespace, raw, snapshot = _read_owned(wrapper, allocation_path)
            if not checkpoints.verify_inventory_checkpoint(allocation_path, raw, snapshot, expected_namespace=namespace):
                raise _fail()
            value = _Publication(wrapper, allocation_path, path, deepcopy(namespace), record, operation, pin, os.getpid(), threading.get_ident())
            token = _ACTIVE.set(value)
            try:
                _assert_publication(value, allocation_path)
                yield
                _assert_publication(value, allocation_path)
                _path, _ledger, _namespace, raw, snapshot = _read_owned(wrapper, allocation_path)
                if not checkpoints.verify_inventory_checkpoint(allocation_path, raw, snapshot, expected_namespace=namespace):
                    raise _fail()
            finally:
                value.active = False
                _ACTIVE.reset(token)


def write_owned_inventory_checkpoint(allocation_path: Path, candidate: dict) -> None:
    """Advance one prevalidated candidate using the active real owned record."""
    value = _ACTIVE.get()
    if value is None:
        raise _fail()
    _assert_publication(value, allocation_path)
    if value.written:
        raise _fail()
    _path, _ledger, _namespace, raw, snapshot = _read_owned(value.wrapper, allocation_path)
    # A failed native/protected write can have committed; retry needs a new
    # verified context and the protocol's exact prepared recovery.
    value.written = True
    checkpoints._publish_inventory_checkpoint(allocation_path, raw, snapshot, candidate, value.namespace, value.operation)
