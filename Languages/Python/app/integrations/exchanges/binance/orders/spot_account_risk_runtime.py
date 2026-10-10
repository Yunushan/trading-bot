"""Owned risk history diagnostics; no mutation, policy or order permission.

The protected provider is deliberately unavailable. Tests may replace that
private seam with isolated storage. A successful diagnostic does not establish
authentic balances, account-wide exclusion or a working native protected store.
The returned storage receipt's issuing scope is revoked before return.
"""
from __future__ import annotations

from copy import deepcopy
import json
import os
import sqlite3
import stat
import sys
import threading
from pathlib import Path
import time
from typing import Any, Callable

from app.gui.shared import allocation_persistence as allocations
from app.settings.live_safety import LiveTradingSafetyError

from . import order_intent_runtime as intents
from . import order_intent_store as locks
from . import spot_account_risk_store as risk_store
from . import spot_inventory_checkpoint as inventory
from . import spot_indexed_intent_selective as indexed
from .spot_execution_owner import SpotExecutionOwner, owner_lock_path, owner_marker_path
from .spot_indexed_intent_bridge import FullIndexedLedgerPayload, IndexedReadAuthority
from .spot_inventory_checkpoint_runtime import _assert_pin, _pin_authority
from .spot_inventory_namespace import make_namespace
from .spot_inventory_namespace_runtime import _verified_uid

_PROCESS_ID = os.getpid()
_RISK_BASENAME = "account_risk.json"


def _fail() -> LiveTradingSafetyError:
    return LiveTradingSafetyError("Owned Spot risk diagnostic authority is unavailable or changed.")


def _protected_provider() -> risk_store.ProtectedPort:
    """No native adapter, credential lookup, fallback or automatic reseed."""
    raise LiveTradingSafetyError("The owned Spot risk protected provider is not implemented.")


def _paths(wrapper: Any) -> tuple[Path, Path, Path]:
    """Use the signed cache without invoking a virtual UID resolver or GET."""
    if _PROCESS_ID != os.getpid():
        raise _fail()
    uid = _verified_uid(wrapper)
    owner = getattr(wrapper, "_spot_execution_owner", None)
    if not isinstance(owner, SpotExecutionOwner) or owner.pid != os.getpid():
        raise _fail()  # An administration token never substitutes for this owner.
    path = Path.home().resolve()
    for component in (".trading-bot", "account-state", "binance", "spot", "live", f"uid-{uid}"):
        path /= component
        try:
            if not stat.S_ISDIR(path.lstat().st_mode):
                raise _fail()
        except OSError as exc:
            raise _fail() from exc
    intent_path = locks._logical_lock_path(path / "order_intents.json")
    allocation_path = locks._logical_lock_path(allocations.get_position_allocations_path(
        Path(__file__).resolve().parents[4] / "gui" / "window_shell.py"))
    risk_path = locks._logical_lock_path(path / _RISK_BASENAME)
    if (intent_path.is_symlink() or risk_path.is_symlink()
            or owner.ledger_path != intent_path or owner.lock_path != owner_lock_path(intent_path)
            or owner.marker_path != owner_marker_path(intent_path)):
        raise _fail()
    return intent_path, allocation_path, risk_path


def _complete_data(ledger: dict[str, object]) -> str:
    return json.dumps(dict(ledger), sort_keys=True, separators=(",", ":"), allow_nan=False)


def _ledger_source(ledger: dict[str, object], path: Path) -> object:
    if isinstance(ledger, locks.LegacyLedgerWritePayload):
        receipt = ledger.legacy_source
        if receipt[0] != path or locks.ledger_file_identity(path) != receipt[1]:
            raise _fail()
        raw = path.read_bytes()
        if locks.ledger_file_identity(path) != receipt[1]:
            raise _fail()
        return receipt, raw
    if isinstance(ledger, FullIndexedLedgerPayload):
        authority = ledger.indexed_authority
        if authority.snapshot.receipt.logical_path != path:
            raise _fail()
        return authority
    raise _fail()  # Plain copied data cannot replace the original read authority.



def _native_indexed_guard(
    owner: SpotExecutionOwner, wrapper: Any, path: Path, binding: dict[str, str],
    deadline: float, assert_pin: Callable[[], None],
) -> tuple[Callable[[], None], Callable[[object], None]] | None:
    """Retain the actual native session between two complete SQL validations.

    This proves unchanged storage under the existing Windows share exclusion;
    it is not a physical database SHA, permission or a portable cache shortcut.
    The session is selected BEFORE the initial full SQL validation. Nothing is
    opened, refreshed, sealed or adopted when the original session is missing.
    """
    assert_pin()
    if sys.platform != "win32":
        return None
    with indexed._session_registry():
        session = indexed._SESSIONS.get(path)
        if path in indexed._INVALIDATIONS:
            raise _fail()  # Any invalidation key refuses BEFORE connection access.
    if session is None:
        return None
    if (not isinstance(session, indexed.IndexedIntentSession) or session._owner is not owner
            or session._pid != os.getpid() or session._closed or session._pending is not None
            or session._wrapper() is not wrapper):
        raise _fail()  # Refuse a foreign/inactive registry BEFORE any connection access.
    if not session._native_guard:
        return None
    connection = session._connection
    token = locks._ACTIVE_LEDGER_TRANSACTION.get()
    if token is None:
        raise _fail()
    token_paths = token.held_paths
    owner_thread = threading.current_thread()
    origin_pid = os.getpid()
    references = tuple((name, getattr(session, name)) for name in (
        "_owner", "_wrapper", "_connection", "_receipt", "_change", "_manifest", "_migration",
        "_backup", "_rules", "_record_receipts", "_commit_sequences", "_active", "_unresolved", "_reserved"))
    scalars = (session._pid, session._generation, session._data_version, session._metadata,
               session._wrapper_context, session._invalidation)
    scalar_types = tuple(type(value) for value in scalars)
    manifest, migration, backup, change = session._manifest, session._migration, session._backup, session._change
    database_path = session._receipt.path
    records = dict(session._record_receipts)
    sequences = dict(session._commit_sequences)
    active, unresolved, reserved = set(session._active), set(session._unresolved), set(session._reserved)
    changes = connection.total_changes
    transaction = connection.in_transaction
    version = indexed.full._sql(connection, deadline, "PRAGMA data_version").fetchone()[0]
    databases = tuple(indexed.full._sql(connection, deadline, "PRAGMA database_list").fetchall())
    if (transaction or type(version) is not int or version != session._data_version
            or len(databases) not in (1, 2) or databases[0][:2] != (0, "main")
            or (len(databases) == 2 and databases[1] != (1, "temp", ""))
            or locks._logical_lock_path(Path(databases[0][2])) != session._receipt.path):
        raise _fail()
    # Existing integrity/schema checks may create an empty TEMP pager. Preserve
    # its exact row while rejecting every object that could shadow main tables.
    if len(databases) == 2 and indexed.full._sql(connection, deadline,
            "SELECT name,type,tbl_name,sql FROM sqlite_temp_master ORDER BY name").fetchall():
        raise _fail()

    def fields() -> None:
        # This registry/field check performs no native or owner callback.
        with indexed._session_registry():
            registered = indexed._SESSIONS.get(path)
            invalidated = path in indexed._INVALIDATIONS
        current_scalars = (session._pid, session._generation, session._data_version, session._metadata,
                           session._wrapper_context, session._invalidation)
        if (locks._ACTIVE_LEDGER_TRANSACTION.get() is not token or token.active is not True
                or token.owner_thread is not owner_thread or token.owner_pid != origin_pid
                or token.held_paths is not token_paths or type(token.deadline) is not float
                or token.deadline != deadline or time.monotonic() >= deadline
                or invalidated or registered is not session or session._closed or session._pending is not None
                or session._native_guard is not True or session._owner is not owner
                or any(getattr(session, name) is not value for name, value in references)
                or session._wrapper() is not wrapper
                or current_scalars != scalars or tuple(type(value) for value in current_scalars) != scalar_types
                or session._record_receipts != records or session._commit_sequences != sequences
                or session._active != active or session._unresolved != unresolved or session._reserved != reserved):
            raise _fail()

    def connection_proof() -> None:
        fields()
        current_version = indexed.full._sql(connection, deadline, "PRAGMA data_version").fetchone()[0]
        current_databases = tuple(indexed.full._sql(connection, deadline, "PRAGMA database_list").fetchall())
        if (connection.total_changes != changes or connection.in_transaction is not transaction
                or type(current_version) is not int or current_version != version or current_databases != databases):
            raise _fail()
        if len(databases) == 2 and indexed.full._sql(connection, deadline,
                "SELECT name,type,tbl_name,sql FROM sqlite_temp_master ORDER BY name").fetchall():
            raise _fail()
        fields()

    def guard() -> None:
        assert_pin()
        fields()
        connection_proof()
        # The original full SQL snapshot binds schema/header/projections/history.
        # Retain its actual owner and native physical consistency; do not reopen
        # a redundant validation transaction or adopt any refreshed session.
        session._owner_authority(deadline)
        fields()
        session._guard()
        fields()
        assert_pin()
        # Reject changes made by the LAST actual native/owner callback.
        fields()
        connection_proof()
        # Recheck the retained PHYSICAL source artifacts after the last explicit
        # native/owner/SQL callback. Never reseal or adopt new provenance.
        manifest.assert_current(path)
        migration.assert_current(path)
        backup.assert_current(manifest, path)
        for suffix in ("-wal", "-shm", "-journal"):
            try:
                database_path.with_name(database_path.name + suffix).lstat()
            except FileNotFoundError:
                continue
            raise _fail()
        change.assert_current()
        # These properties and registry/field checks have no later SQL, native
        # metadata or owner callback. Preserve the original lifetime/deadline.
        if connection.total_changes != changes or connection.in_transaction is not transaction:
            raise _fail()
        fields()

    def bind(authority: object) -> None:
        if (not isinstance(authority, IndexedReadAuthority)
                or authority.manifest != session._manifest or authority.migration != session._migration
                or authority.source_backup != session._backup or authority.snapshot.receipt != session._receipt
                or authority.original_binding() != binding
                or not indexed._matches_compact(session, authority.snapshot)):
            raise _fail()
        guard()

    guard()
    return guard, bind


def read_owned_spot_risk_store(wrapper: Any) -> risk_store.RiskReadReceipt:
    """Fully replay diagnostics under the caller's three original local locks.

    No account lookup, owner claim, lock expansion, new deadline, bootstrap,
    append, pending recovery, reset or submission is performed. The internal
    provider must exist before any protected inventory read is attempted.
    """
    paths = _paths(wrapper)
    intent_path, allocation_path, risk_path = paths
    transaction = locks._ACTIVE_LEDGER_TRANSACTION.get()
    deadline = locks.current_ledger_deadline(*paths)
    if type(deadline) is not float or time.monotonic() >= deadline:
        raise _fail()
    owner = wrapper._spot_execution_owner
    submission_lock = owner._submission_lock
    namespace = make_namespace(_verified_uid(wrapper), owner.store_id)
    pin = _pin_authority(wrapper, intent_path, namespace)
    original_context = wrapper._verified_spot_account_context
    original_mode = (wrapper.mode, wrapper.account_type)
    original_owner = (owner.ledger_path, owner.lock_path, owner.marker_path, owner.uid,
                      owner.environment, owner.store_id, owner.credential_fingerprint, owner.pid, owner.fd)

    def assert_pin() -> None:
        if (owner._submission_lock is not submission_lock
                or locks._ACTIVE_LEDGER_TRANSACTION.get() is not transaction
                or locks.current_ledger_deadline(*paths) != deadline or time.monotonic() >= deadline
                or _paths(wrapper) != paths or (wrapper.mode, wrapper.account_type) != original_mode
                or wrapper._verified_spot_account_context is not original_context
                or (owner.ledger_path, owner.lock_path, owner.marker_path, owner.uid,
                    owner.environment, owner.store_id, owner.credential_fingerprint, owner.pid, owner.fd)
                != original_owner or make_namespace(_verified_uid(wrapper), owner.store_id) != namespace):
            raise _fail()
        _assert_pin(wrapper, intent_path, namespace, pin)
        if (owner._submission_lock is not submission_lock
                or locks._ACTIVE_LEDGER_TRANSACTION.get() is not transaction
                or locks.current_ledger_deadline(*paths) != deadline or time.monotonic() >= deadline):
            raise _fail()

    assert_pin()
    # The actual owner's mutex is nonblocking while storage is held. Waiting
    # would invert the existing owner-before-storage lock ordering.
    if not submission_lock.acquire(blocking=False):
        raise _fail()
    try:
        assert_pin()
        protected = _protected_provider()  # Default refusal BEFORE inventory's credential adapter.
        assert_pin()
        native = _native_indexed_guard(owner, wrapper, intent_path, pin.binding, deadline, assert_pin)
        ledger = intents._read_ledger(intent_path, expected_binding=pin.binding)
        if ledger.get("binding") != pin.binding or ledger.get("store_id") != namespace["store_id"]:
            raise _fail()
        original_data = _complete_data(ledger)
        original_source = _ledger_source(ledger, intent_path)
        if native is not None:
            native[1](original_source)
        observed_inventory: Any = None

        def full_original_guard() -> None:
            assert_pin()
            current = intents._read_ledger(intent_path, expected_binding=pin.binding)
            if (_complete_data(current) != original_data
                    or _ledger_source(current, intent_path) != original_source):
                raise _fail()
            if observed_inventory is not None and allocations._read_receipt(allocation_path) != observed_inventory:
                raise _fail()
            assert_pin()  # Complete history work must not outlive the original deadline.

        def original_guard() -> None:
            assert_pin()  # Reject lost caller authority BEFORE inventory filesystem I/O.
            if native is None:
                full_original_guard()
            else:
                if observed_inventory is not None and allocations._read_receipt(allocation_path) != observed_inventory:
                    raise _fail()
                native[0]()

        original_guard()
        observed_inventory = allocations._read_receipt(allocation_path)
        with inventory._checkpoint_authority(assert_pin):
            original_checkpoint = inventory._get(allocation_path, deadline)
            snapshot = allocations.guard_position_allocation_snapshot(
                allocation_path, observed_inventory, expected_namespace=namespace)
            if (not isinstance(snapshot, dict)
                    or inventory._get(allocation_path, deadline) != original_checkpoint):
                raise _fail()
        original_guard()

        def complete_guard() -> None:
            original_guard()
            with inventory._checkpoint_authority(assert_pin):
                current = allocations.guard_position_allocation_snapshot(
                    allocation_path, observed_inventory, expected_namespace=namespace)
                if current != snapshot or inventory._get(allocation_path, deadline) != original_checkpoint:
                    raise _fail()
            original_guard()

        identity = {"version": 1, "exchange": "binance", "market": "spot", "environment": "live",
                    "account_uid": namespace["account_uid"], "ledger_store_id": namespace["store_id"]}
        with risk_store._storage_scope(risk_path, protected=protected, guard=complete_guard, deadline=deadline):
            receipt = risk_store.read_risk_store(risk_path, deepcopy(identity))
            complete_guard()
        full_original_guard()  # Genuine full SQL/history proof AFTER the entire risk scope.
        complete_guard()  # Recheck protected inventory and native provenance after that SQL proof.
        return receipt  # Existing store scope is expired; diagnostic data only.
    except LiveTradingSafetyError:
        raise
    except (OSError, ValueError, sqlite3.Error) as exc:
        raise _fail() from exc
    finally:
        submission_lock.release()
