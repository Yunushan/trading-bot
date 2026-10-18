"""Publish one desktop portfolio only against that window's loaded snapshot."""
from __future__ import annotations

import copy
import json
import os
import stat
import threading
import time
from contextlib import AbstractContextManager, contextmanager, nullcontext
from dataclasses import dataclass, field
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Any, cast
from collections.abc import Mapping

from app.integrations.exchanges.binance.orders.spot_allocation_generation_runtime import (
    SpotBuyAdmissionReceipt, SpotBuyPublicationContext, build_spot_buy_allocation_row,
    spot_buy_target, validate_spot_buy_publication, validate_spot_entry_snapshot,
)

from app.integrations.exchanges.binance.orders.order_intent_store import (
    ledger_transaction,
    ledger_transactions,
    write_ledger,
)
from app.settings.live_safety import LiveTradingSafetyError
from .trade_callback_origin import TradeCallbackOrigin, _matches_original_context
from app.integrations.exchanges.binance.orders.spot_inventory_namespace import (
    ACCOUNT_NAMESPACE_KEY, is_strictly_empty_live_snapshot, make_namespace,
    require_namespace, validate_namespace,
)

_ALLOCATIONS_FILE_NAME = ".trading_bot_allocations.json"
_ALLOCATIONS_DIR_NAME = "data"
_ALLOCATION_STATE_ERRORS = (
    LiveTradingSafetyError, OSError, ValueError, TypeError, KeyError,
    AttributeError, OverflowError, RecursionError, InvalidOperation,
)


@dataclass
class AllocationSnapshotLoadTicket:
    """Correlate a returned two-map load with its exact accepted window receipt."""

    _completion: tuple[Path, str | None, int] | None = field(default=None, repr=False)


@dataclass
class AllocationSnapshotSession:
    """A receipt belongs to one window, never to a module or a fresh save read."""

    state: str = "unloaded"
    last_error: str | None = None
    _path: Path | None = field(default=None, repr=False)
    _mode: str | None = field(default=None, repr=False)
    _bytes: bytes | None = field(default=None, repr=False)
    _identity: tuple[int, int, int, int] | None = field(default=None, repr=False)
    _snapshot: dict | None = field(default=None, repr=False)
    _generation: int = field(default=0, repr=False)
    _mutex: threading.RLock = field(default_factory=threading.RLock, repr=False)

    @property
    def ready(self) -> bool:
        with self._mutex:
            return self.state in {"absent", "loaded"}

    def invalidate(self, reason: str = "mode_changed") -> None:
        """Fence publication without turning old maps into a newly loaded receipt."""
        with self._mutex:
            self.state, self.last_error = "blocked", reason
            self._generation += 1

    def _capture(self):
        with self._mutex:
            return (
                self._path, self._mode, self._bytes, self._identity,
                copy.deepcopy(self._snapshot), self._generation, self.ready,
            )

    def _begin_load(self) -> int:
        with self._mutex:
            self.state = "loading"
            self._generation += 1
            return self._generation

    @contextmanager
    def loaded_handoff(self, ticket: AllocationSnapshotLoadTicket):
        """Keep receipt replacement/invalidation out of the two-map assignment gap."""
        with self._mutex:
            accepted = self.state in {"absent_pending", "loaded_pending"} and (
                ticket._completion == (self._path, self._mode, self._generation)
            )
            completed = False
            try:
                yield accepted
                completed = True
            finally:
                if accepted:
                    if completed:
                        self.state = "absent" if self._snapshot is None else "loaded"
                        self._generation += 1
                    else:
                        self.invalidate("allocation map handoff failed")

    def _accept(
        self, path: Path, mode: str | None, observed, snapshot: dict | None, *, pending_handoff: bool = False,
    ) -> None:
        with self._mutex:
            self._path, self._mode = path, mode
            self._bytes, self._identity = observed
            self._snapshot = copy.deepcopy(snapshot)
            self.state = "absent" if snapshot is None else "loaded"
            if pending_handoff:
                self.state += "_pending"
            self.last_error = None
            self._generation += 1

    def has_trade_event_receipt(self, descriptor: dict) -> bool:
        """Inspect committed evidence only; a conflicting replay is an error."""
        _validate_event_receipt(descriptor)
        captured = self._capture()
        if self.state != "loaded" or captured[0] is None:
            return False
        with ledger_transaction(captured[0]), self._mutex:
            assert_loaded_allocation_checkpoint(self)
            receipts = (self._snapshot or {}).get("gui_trade_event_receipts", [])
            matches = [receipt for receipt in receipts if receipt["event_id"] == descriptor["event_id"]]
            if matches and matches != [descriptor]:
                raise ValueError("GUI trade event conflicts with committed receipt")
            return self.state == "loaded" and matches == [descriptor]

    def capture_spot_buy_admission(self, params: Mapping) -> SpotBuyAdmissionReceipt:
        """Capture actual loaded authority; never reload to authorize old window maps."""
        target, identities = spot_buy_target(params)
        captured = self._capture()
        if not captured[6] or captured[0] is None or captured[1] != "Live":
            raise LiveTradingSafetyError("Spot entry requires a loaded Live allocation receipt.")
        validate_spot_entry_snapshot(captured[4], target[0], identities)
        receipt = SpotBuyAdmissionReceipt(captured[0], captured[1], captured[2], captured[3],
                                          captured[5], target, identities)
        if not self.check_spot_buy_admission(receipt, params):
            raise LiveTradingSafetyError("Spot entry allocation authority changed during capture.")
        return receipt

    def matches_loaded_maps(self, allocations: dict, records: dict) -> bool:
        """Compare complete window maps with actual loaded authority, without storage I/O."""
        if not isinstance(allocations, dict) or not isinstance(records, dict):
            return False
        try:
            with self._mutex:
                if not self.ready:
                    return False
                expected = self._snapshot or {"entry_allocations": {}, "open_position_records": {}}
                expected_allocations = expected["entry_allocations"]
                expected_records = expected["open_position_records"]
                if not isinstance(expected_allocations, dict) or not isinstance(expected_records, dict):
                    return False
                current_allocations = {
                    _serialize_allocation_key(key): copy.deepcopy(list(rows.values()) if isinstance(rows, dict) else rows)
                    for key, rows in allocations.items()
                }
                current_records = {_serialize_allocation_key(key): copy.deepcopy(record) for key, record in records.items()}
                return current_allocations == expected_allocations and current_records == expected_records
        except (ValueError, TypeError, KeyError, AttributeError, RecursionError):
            return False

    def check_spot_buy_admission(self, receipt: SpotBuyAdmissionReceipt, params: Mapping) -> bool:
        """Pure source check; caller compares real storage under its transaction."""
        if not isinstance(receipt, SpotBuyAdmissionReceipt):
            return False
        target, identities = spot_buy_target(params)
        with self._mutex:
            return self.ready and (
                self._path, self._mode, self._bytes, self._identity, self._generation, target, identities
            ) == (
                receipt.allocation_path, receipt.mode, receipt.raw, receipt.identity,
                receipt.generation, receipt.target_key, receipt.client_order_ids,
            )


def _get_allocations_file_path(this_file: Path) -> Path:
    # Path resolution is not permission to migrate or publish state.
    return this_file.absolute().parents[2] / _ALLOCATIONS_DIR_NAME / _ALLOCATIONS_FILE_NAME


def get_position_allocations_path(this_file: Path) -> Path:
    """Return the canonical path without reading, creating or migrating state."""
    return _get_allocations_file_path(this_file)


def initialize_spot_allocation_namespace(window, wrapper) -> bool:
    """Bind an empty source, then actually reload both maps before entry capture."""
    from .trade_callback_origin import owned_live_spot_wrapper
    from app.integrations.exchanges.binance.orders.order_intent_runtime import _intent_path
    from app.integrations.exchanges.binance.orders.spot_execution_owner import SpotExecutionOwner
    from app.integrations.exchanges.binance.orders.spot_inventory_checkpoint_runtime import bootstrap_owned_inventory_checkpoint

    session = getattr(window, "_allocation_snapshot_session", None)
    if not isinstance(session, AllocationSnapshotSession) or not owned_live_spot_wrapper(wrapper):
        raise LiveTradingSafetyError("Spot inventory namespace requires the current loaded account.")
    owner = getattr(wrapper, "_spot_execution_owner", None)
    if not isinstance(owner, SpotExecutionOwner):
        raise LiveTradingSafetyError("Spot inventory namespace requires held execution ownership.")
    uid = wrapper._resolve_spot_account_uid()
    owner.assert_held(uid=uid, environment=owner.environment,
                      credential_fingerprint=owner.credential_fingerprint, owner_wrapper=wrapper)
    expected = make_namespace(uid, owner.store_id)
    app_root = Path(__file__).resolve().parents[2]
    this_file = app_root / "gui" / "window_shell.py"
    path, intent_path = get_position_allocations_path(this_file), _intent_path(wrapper)
    captured = session._capture()
    maps = (getattr(window, "_entry_allocations", None), getattr(window, "_open_position_records", None))
    if not all(isinstance(value, dict) for value in maps):
        raise LiveTradingSafetyError("Spot inventory namespace actual maps are unavailable.")
    original_maps = cast(tuple[dict, dict], maps)
    context = (wrapper.api_key, wrapper.api_secret, wrapper.mode, wrapper.account_type, wrapper.client,
               getattr(window, "_account_observation_generation", 0))

    def assert_original(*, ready: bool = True) -> None:
        bound_wrapper = cast(Any, wrapper)
        bound_owner = cast(SpotExecutionOwner, owner)
        bound_session = cast(AllocationSnapshotSession, session)
        if (getattr(window, "shared_binance", None) is not wrapper
                or getattr(window, "_allocation_snapshot_session", None) is not session
                or getattr(wrapper, "_spot_execution_owner", None) is not owner
                or getattr(wrapper, "_spot_execution_revoked", False)
                or window.mode_combo.currentText() != "Live"
                or (bound_wrapper.api_key, bound_wrapper.api_secret, bound_wrapper.mode, bound_wrapper.account_type, bound_wrapper.client,
                    getattr(window, "_account_observation_generation", 0)) != context
                or getattr(window, "_entry_allocations", None) is not maps[0]
                or getattr(window, "_open_position_records", None) is not maps[1]
                or bound_owner.ledger_path != intent_path):
            raise LiveTradingSafetyError("Spot inventory namespace account or maps changed.")
        bound_owner.assert_held(uid=uid, environment=bound_owner.environment,
                                credential_fingerprint=bound_owner.credential_fingerprint, owner_wrapper=wrapper)
        if ready and (bound_session._capture() != captured or not bound_session.matches_loaded_maps(*original_maps)):
            raise LiveTradingSafetyError("Spot inventory namespace loaded source changed.")

    if not captured[6] or captured[0] != path or captured[1] != "Live":
        raise LiveTradingSafetyError("Spot inventory namespace has no loaded canonical Live source.")
    with ledger_transactions(intent_path, path), session._mutex:
        assert_original()
        observed = _read_receipt(path)
        guard_position_allocation_snapshot(path, observed)
        if observed != (captured[2], captured[3]):
            raise LiveTradingSafetyError("Spot inventory namespace source changed after loading.")
        previous = captured[4]
        if previous is not None and ACCOUNT_NAMESPACE_KEY in previous:
            require_namespace(previous, expected)
            return False
        if not is_strictly_empty_live_snapshot(previous):
            raise LiveTradingSafetyError("Unscoped Spot inventory requires explicit reconciliation.")
        data = copy.deepcopy(previous) if previous is not None else {
            "version": 1, "mode": "Live", "entry_allocations": {}, "open_position_records": {},
        }
        data[ACCOUNT_NAMESPACE_KEY] = expected
        session.invalidate("Spot inventory namespace initialization requires an actual reload")
        if bootstrap_owned_inventory_checkpoint(wrapper, allocation_path=path) is not True:
            raise LiveTradingSafetyError("Spot inventory protected bootstrap was not committed.")
        committed = _read_receipt(path)
        guard_position_allocation_snapshot(path, committed, expected_namespace=expected)
    # This loader obtains a new receipt and returns both actual maps. It never
    # adopts old maps into a freshened session or calls a window/venue callback.
    assert_original(ready=False)
    ticket = AllocationSnapshotLoadTicket()
    loaded_maps = load_position_allocations(this_file=this_file, mode="Live", session=session, load_ticket=ticket)
    with ledger_transactions(intent_path, path), session._mutex:
        assert_original(ready=False)
        reloaded = _read_receipt(path)
        guard_position_allocation_snapshot(path, reloaded, expected_namespace=expected)
        if reloaded != committed:
            session.invalidate("Spot inventory namespace changed during reload")
            raise LiveTradingSafetyError("Spot inventory namespace changed during reload.")
        current = session._capture()
        if (current[0:4] != (path, "Live", committed[0], committed[1])
                or current[4] != data):
            session.invalidate("Spot inventory namespace reload did not retain its source")
            raise LiveTradingSafetyError("Spot inventory namespace reload lost its exact source.")
        require_namespace(current[4], expected)
        with session.loaded_handoff(ticket) as accepted:
            if not accepted:
                raise LiveTradingSafetyError("Spot inventory namespace map handoff was not accepted.")
            window._entry_allocations, window._open_position_records = loaded_maps
    return True


def non_spot_desktop_exposure_allowed(window, wrapper) -> bool:
    """Inspect current storage before non-Spot exposure can reuse a Spot portfolio."""
    from .trade_callback_origin import owned_live_spot_wrapper
    if owned_live_spot_wrapper(wrapper):
        return True  # Actual account namespace is checked by entry capture/handoff.
    path = get_position_allocations_path(Path(__file__).resolve().parents[2] / "gui" / "window_shell.py")
    try:
        with ledger_transaction(path):
            observed = _read_receipt(path)
            snapshot = guard_position_allocation_snapshot(path, observed)
            if snapshot is None:
                return True
            return ACCOUNT_NAMESPACE_KEY not in snapshot and not (
                snapshot["mode"] == "Live" and any(is_recovery_owned_allocation(row)
                    for rows in snapshot["entry_allocations"].values() for row in rows)
            )
    except _ALLOCATION_STATE_ERRORS:
        return False


def is_recovery_owned_allocation(row: object) -> bool:
    """Malformed proof fields also fence ordinary GUI mutation and cleanup."""
    return isinstance(row, dict) and (
        "spot_fill_recovery" in row or "spot_sell_recoveries" in row or "spot_opo_stop_recovery" in row
    )


def _check_path(path: Path) -> None:
    for target in (path, path.parent, path.parent.parent):
        if target.is_symlink():
            raise ValueError("allocation state must not use symbolic links")


def _file_identity(info) -> tuple[int, int, int, int]:
    return info.st_dev, info.st_ino, info.st_mtime_ns, info.st_size


def _read_receipt(path: Path):
    _check_path(path)
    try:
        fd = os.open(path, os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0))
    except FileNotFoundError:
        return None, None
    with os.fdopen(fd, "rb") as handle:
        observed_stat = os.fstat(handle.fileno())
        if not stat.S_ISREG(observed_stat.st_mode):
            raise ValueError("allocation state must be a regular file")
        raw = handle.read()
        after = os.fstat(handle.fileno())
    _check_path(path)
    current = path.stat()
    if _file_identity(observed_stat) != _file_identity(after) or _file_identity(after) != _file_identity(current):
        raise ValueError("allocation state changed while reading")
    return raw, _file_identity(current)


def _unique_object(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("duplicate allocation field")
        result[key] = value
    return result


def _deserialize_allocation_key(key_str: str) -> tuple[str, str]:
    if not isinstance(key_str, str):
        raise ValueError("invalid allocation key")
    parts = key_str.rsplit(":", 1)
    if len(parts) != 2 or not parts[0] or parts[1] not in {"L", "S"}:
        raise ValueError("invalid allocation key")
    return parts[0], parts[1]


def _serialize_allocation_key(key: tuple) -> str:
    if not isinstance(key, tuple) or len(key) != 2 or any(not isinstance(v, str) for v in key):
        raise ValueError("invalid allocation key")
    serialized = f"{key[0]}:{key[1]}"
    if _deserialize_allocation_key(serialized) != key:
        raise ValueError("ambiguous allocation key")
    return serialized


def _validate_event_receipt(descriptor: dict) -> None:
    if (
        not isinstance(descriptor, dict)
        or type(descriptor.get("version")) is not int or descriptor["version"] != 1
    ):
        raise ValueError("invalid GUI trade event receipt")
    allowed = {"version", "event_id", "kind", "symbol", "side_key", "quantity", "order_id", "client_order_id"}
    if set(descriptor) - allowed or descriptor.get("kind") not in {"BUY", "SELL"}:
        raise ValueError("invalid GUI trade event receipt")
    if descriptor.get("side_key") not in {"L", "S"}:
        raise ValueError("invalid GUI trade event receipt")
    for name, bound in (("event_id", 128), ("symbol", 32), ("order_id", 128), ("client_order_id", 128)):
        value = descriptor.get(name)
        if name in {"event_id", "symbol"} or value is not None:
            if not isinstance(value, str) or not value or len(value) > bound or not value.isascii():
                raise ValueError("invalid GUI trade event receipt identity")
            if any(c not in "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789._:/-" for c in value):
                raise ValueError("invalid GUI trade event receipt identity")
    quantity = descriptor.get("quantity")
    try:
        if not isinstance(quantity, str) or not quantity or len(quantity) > 80:
            raise ValueError("invalid GUI trade event quantity")
        parsed = Decimal(quantity)
        if not parsed.is_finite() or parsed <= 0:
            raise ValueError("invalid GUI trade event quantity")
    except InvalidOperation as exc:
        raise ValueError("invalid GUI trade event quantity") from exc


def _validate_snapshot(data: dict, mode: str | None) -> None:
    if (
        not isinstance(data, dict) or type(data.get("version")) is not int or data["version"] != 1
        or not isinstance(data.get("mode"), str) or not data["mode"]
        or not isinstance(data.get("entry_allocations"), dict)
        or not isinstance(data.get("open_position_records"), dict)
    ):
        raise ValueError("malformed allocation snapshot")
    if mode is not None and data["mode"] != mode:
        raise ValueError("allocation snapshot mode mismatch")
    if ACCOUNT_NAMESPACE_KEY in data:
        validate_namespace(data[ACCOUNT_NAMESPACE_KEY])
        if data["mode"] != "Live":
            raise ValueError("Spot inventory namespace requires Live mode")
    # Check all fields, including extensions, without silently dropping any field.
    json.dumps(data, allow_nan=False)
    _validate_json_keys(data)
    for key, entries in data["entry_allocations"].items():
        _deserialize_allocation_key(key)
        if not isinstance(entries, list) or any(not isinstance(row, dict) for row in entries):
            raise ValueError("invalid allocation list")
        for row in entries:
            if "data" in row and not isinstance(row["data"], dict):
                raise ValueError("invalid allocation data")
            if "spot_fill_recovery" in row and not isinstance(row["spot_fill_recovery"], dict):
                raise ValueError("invalid recovered BUY proof")
            if "spot_sell_recoveries" in row and (
                not isinstance(row["spot_sell_recoveries"], list)
                or any(not isinstance(proof, dict) for proof in row["spot_sell_recoveries"])
            ):
                raise ValueError("invalid recovered SELL proof")
    for key, record in data["open_position_records"].items():
        _deserialize_allocation_key(key)
        if (
            not isinstance(record, dict) or not isinstance(record.get("data"), dict)
            or not isinstance(record.get("allocations"), list)
            or any(not isinstance(row, dict) for row in record["allocations"])
        ):
            raise ValueError("invalid open position record")
    receipts = data.get("gui_trade_event_receipts", [])
    if not isinstance(receipts, list):
        raise ValueError("invalid GUI trade event registry")
    seen = set()
    for receipt in receipts:
        _validate_event_receipt(receipt)
        token = receipt["event_id"]
        if token in seen:
            raise ValueError("duplicate GUI trade event identity")
        seen.add(token)


def _validate_json_keys(value: object) -> None:
    if isinstance(value, dict):
        if any(not isinstance(key, str) for key in value):
            raise ValueError("allocation JSON fields must have string keys")
        for child in value.values():
            _validate_json_keys(child)
    elif isinstance(value, (tuple, list)):
        for child in value:
            _validate_json_keys(child)


def _decode(raw: bytes, mode: str | None) -> dict:
    data = json.loads(raw.decode("utf-8"), object_pairs_hook=_unique_object)
    if not isinstance(data, dict):
        raise ValueError("malformed allocation snapshot")
    _validate_snapshot(data, mode)
    return data


def guard_position_allocation_snapshot(path: Path, observed, *, expected_namespace=None) -> dict | None:
    """Verify the actual locked path slot before any missing or mode decision."""
    from app.integrations.exchanges.binance.orders.spot_inventory_checkpoint import verify_inventory_checkpoint
    raw = observed[0]
    snapshot = None
    if raw is not None:
        try:
            snapshot = json.loads(raw.decode("utf-8"), object_pairs_hook=_unique_object)
        except (ValueError, UnicodeError):
            # The checkpoint verifier inspects the Windows slot first and then
            # rejects these malformed original bytes; never substitute a receipt.
            pass
    verified = verify_inventory_checkpoint(path, raw, snapshot, expected_namespace)
    if expected_namespace is not None and verified is not True:
        raise LiveTradingSafetyError("Scoped Spot inventory requires its stable protected checkpoint.")
    if snapshot is not None:
        _validate_snapshot(snapshot, None)
    return snapshot


def assert_loaded_allocation_checkpoint(session: AllocationSnapshotSession, *, expected_namespace=None):
    """Compare storage to the original receipt without adopting fresh window maps."""
    captured = session._capture()
    if not captured[6] or captured[0] is None:
        raise LiveTradingSafetyError("Desktop inventory has no current loaded receipt.")
    observed = _read_receipt(captured[0])
    actual_snapshot = guard_position_allocation_snapshot(captured[0], observed, expected_namespace=expected_namespace)
    if (observed != (captured[2], captured[3]) or actual_snapshot != captured[4]
            or session._capture() != captured):
        raise LiveTradingSafetyError("Desktop inventory changed after its original load.")
    return captured


def _write_snapshot(file_path: Path, payload: dict) -> None:
    _check_path(file_path)
    if ACCOUNT_NAMESPACE_KEY in payload:
        from app.integrations.exchanges.binance.orders.spot_inventory_checkpoint_runtime import write_owned_inventory_checkpoint
        write_owned_inventory_checkpoint(file_path, payload)
    else:
        guard_position_allocation_snapshot(file_path, _read_receipt(file_path))
        write_ledger(file_path, payload)


def _protect_owned_rows(previous: dict, candidate: dict, *, position_transition_key: str | None = None) -> None:
    candidate_identities: dict[tuple[str, str, str], list[tuple[str, dict]]] = {}
    for candidate_key, rows in candidate["entry_allocations"].items():
        for row in rows:
            for field_name in ("client_order_id", "order_id", "trade_id"):
                identity = row.get(field_name)
                if identity is not None and str(identity):
                    scope = str(row.get("symbol", "")) if field_name == "order_id" else ""
                    candidate_identities.setdefault((field_name, str(identity), scope), []).append((candidate_key, row))
            buy_proof = row.get("spot_fill_recovery")
            if isinstance(buy_proof, dict) and isinstance(buy_proof.get("signature"), str):
                candidate_identities.setdefault(("BUY proof", buy_proof["signature"], ""), []).append((candidate_key, row))
    for key, rows in previous["entry_allocations"].items():
        protected = [row for row in rows if is_recovery_owned_allocation(row)]
        if not protected:
            continue
        for row in protected:
            identity = row.get("client_order_id")
            if not isinstance(identity, str) or not identity:
                raise ValueError("recovery-owned allocation identity is invalid")
            for field_name in ("client_order_id", "order_id", "trade_id"):
                token = row.get(field_name)
                if token is not None and str(token):
                    scope = str(row.get("symbol", "")) if field_name == "order_id" else ""
                    matches = candidate_identities.get((field_name, str(token), scope), [])
                    if matches != [(key, row)]:
                        raise ValueError("recovery-owned allocation cannot be changed, removed or duplicated by the GUI")
            buy_proof = row.get("spot_fill_recovery")
            if isinstance(buy_proof, dict) and isinstance(buy_proof.get("signature"), str):
                if candidate_identities.get(("BUY proof", buy_proof["signature"], ""), []) != [(key, row)]:
                    raise ValueError("recovery-owned BUY proof cannot be copied to another GUI allocation")
        previous_record = previous["open_position_records"].get(key)
        if key == position_transition_key:
            # Only the strict canonical transition validator can authorize this position update.
            continue
        if previous_record is not None:
            new_record = candidate["open_position_records"].get(key)
            if not isinstance(new_record, dict):
                raise ValueError("recovery-owned position record cannot be removed by the GUI")
            for name in ("symbol", "side_key", "status", "allocations"):
                if new_record.get(name) != previous_record.get(name):
                    raise ValueError("recovery-owned position inventory cannot be changed by the GUI")
            for name in ("symbol", "side_key", "qty", "entry_price", "margin_usdt", "size_usdt"):
                if new_record["data"].get(name) != previous_record["data"].get(name):
                    raise ValueError("recovery-owned position amounts cannot be changed by the GUI")
        elif key in candidate["open_position_records"]:
            raise ValueError("closed recovery-owned inventory cannot be reactivated by the GUI")


def _validate_owned_spot_buy_candidate(context, captured, file_path, previous, candidate, event_receipt) -> Mapping:
    if not isinstance(context, SpotBuyPublicationContext) or captured is None or previous is None and captured[2] is not None:
        raise ValueError("owned Spot BUY publication context is invalid")
    require_namespace(previous, context.namespace)
    require_namespace(candidate, context.namespace)
    source = context.entry_source_receipt
    if not isinstance(source, SpotBuyAdmissionReceipt) or (
        context.allocation_path, source.allocation_path, source.mode, source.raw, source.identity, source.generation
    ) != (file_path, captured[0], captured[1], captured[2], captured[3], captured[5]):
        raise ValueError("owned Spot BUY publication source differs from the loaded receipt")
    # Both storage paths are already held; never nest the process-global transaction.
    from app.integrations.exchanges.binance.orders.order_intent_runtime import _read_ledger
    ledger = _read_ledger(context.intent_path, expected_binding=context.expected_binding)
    if ledger.get("store_id") != context.expected_store_id:
        raise ValueError("owned Spot BUY publication intent store identity changed")
    intents = ledger.get("intents")
    observed_intent = intents.get(context.expected_intent.get("client_order_id")) if isinstance(intents, dict) else None
    if not isinstance(observed_intent, Mapping):
        raise ValueError("owned Spot BUY accepted intent is missing")
    validate_spot_buy_publication(context, observed_intent)
    from app.integrations.exchanges.binance.orders.spot_buy_publication_runtime import desktop_source_descriptor
    if observed_intent.get("desktop_entry_source") != desktop_source_descriptor(source):
        raise ValueError("owned Spot BUY accepted intent does not bind its original desktop source")
    fill = context.fill
    key = f"{fill['symbol']}:L"
    if source.target_key != (fill["symbol"], "L") or fill["client_order_id"] not in source.client_order_ids:
        raise ValueError("owned Spot BUY generation differs from pre-submit target")
    if (
        not isinstance(event_receipt, dict) or event_receipt.get("kind") != "BUY"
        or event_receipt.get("symbol") != fill["symbol"] or event_receipt.get("side_key") != "L"
        or event_receipt.get("client_order_id") != fill["client_order_id"]
        or event_receipt.get("order_id") != str(fill["order_id"])
        or Decimal(event_receipt["quantity"]) != Decimal(str(fill["net_qty"]))
    ):
        raise ValueError("owned Spot BUY publication lacks its exact GUI event receipt")
    baseline = previous or {"entry_allocations": {}, "open_position_records": {}}
    validate_spot_entry_snapshot(previous, fill["symbol"], source.client_order_ids)
    old_rows = baseline["entry_allocations"].get(key, [])
    new_rows = candidate["entry_allocations"].get(key)
    if not isinstance(new_rows, list) or len(new_rows) != len(old_rows) + 1 or new_rows[:-1] != old_rows:
        raise ValueError("owned Spot BUY must append one generation without changing history")
    if new_rows[-1] != build_spot_buy_allocation_row(fill, new_rows[-1]):
        raise ValueError("owned Spot BUY candidate differs from canonical acquisition")
    for map_name in ("entry_allocations", "open_position_records"):
        before_other = {stored_key: value for stored_key, value in baseline[map_name].items() if stored_key != key}
        after_other = {stored_key: value for stored_key, value in candidate[map_name].items() if stored_key != key}
        if before_other != after_other:
            raise ValueError("owned Spot BUY cannot alter another allocation key")
    active = [row for row in new_rows if str(row.get("status") or "").lower() == "active"]
    record = candidate["open_position_records"].get(key)
    if (
        not isinstance(record, dict) or record.get("symbol") != fill["symbol"] or record.get("side_key") != "L"
        or str(record.get("status") or "").lower() != "active" or record.get("allocations") != active
    ):
        raise ValueError("owned Spot BUY position does not contain only current active inventory")
    amounts = record.get("data")
    quantity = sum(float(row["qty"]) for row in active)
    margin = sum(float(row.get("margin_usdt") or 0) for row in active)
    notional = sum(float(row.get("notional") or 0) for row in active)
    average = sum(float(row["qty"]) * float(row["entry_price"]) for row in active) / quantity
    if not isinstance(amounts, dict) or any(amounts.get(name) != expected for name, expected in (
        ("symbol", fill["symbol"]), ("side_key", "L"), ("qty", quantity),
        ("entry_price", average), ("margin_usdt", margin), ("size_usdt", notional),
    )):
        raise ValueError("owned Spot BUY position financial fields are incoherent")
    _protect_owned_rows(baseline, candidate, position_transition_key=key)
    return observed_intent


def _assert_gui_publication_origin(context: SpotBuyPublicationContext, session) -> TradeCallbackOrigin:
    origin = context.origin
    if (not isinstance(origin, TradeCallbackOrigin) or origin.session is not session
            or origin.admission_receipt != context.entry_source_receipt
            or not _matches_original_context(origin.window, origin)):
        raise LiveTradingSafetyError("Desktop BUY publication lost its original account and window.")
    return origin


def save_position_allocations(
    entry_allocations: dict, open_position_records: dict, *, this_file: Path,
    mode: str | None = None, session: AllocationSnapshotSession | None = None,
    event_receipt: dict | None = None,
    owned_spot_buy: SpotBuyPublicationContext | None = None,
) -> bool:
    completed = False
    failure_reason = "allocation publication failed"
    try:
        file_path = _get_allocations_file_path(this_file)
        _check_path(file_path)
        captured = session._capture() if session is not None else None
        owned_spot_buy = copy.deepcopy(owned_spot_buy)
        if session is not None and (
            captured is None or not captured[6] or captured[0] != file_path or captured[1] != mode
        ):
            raise ValueError("allocation publication has no matching loaded receipt")
        allocations = {}
        for key, entries in entry_allocations.items():
            if isinstance(entries, dict):
                entries = list(entries.values())
            if not isinstance(entries, list) or any(not isinstance(row, dict) for row in entries):
                raise ValueError("invalid candidate allocation list")
            allocations[_serialize_allocation_key(key)] = copy.deepcopy(entries)
        records = {_serialize_allocation_key(key): copy.deepcopy(record) for key, record in open_position_records.items()}
        previous = captured[4] if captured is not None else None
        saved_mode = mode or (previous["mode"] if previous is not None else "unknown")
        data: dict = copy.deepcopy(previous) if previous is not None else {"version": 1}
        data.update({"mode": saved_mode, "timestamp": time.time(), "entry_allocations": allocations, "open_position_records": records})
        if owned_spot_buy is None and (
            ACCOUNT_NAMESPACE_KEY in data or previous is not None and ACCOUNT_NAMESPACE_KEY in previous
        ):
            raise ValueError("Bound Spot inventory publication requires its owned account authority")
        if owned_spot_buy is None and saved_mode == "Live":
            old_allocations = (previous or {}).get("entry_allocations", {})
            if any(is_recovery_owned_allocation(row) and row not in old_allocations.get(key, [])
                   for key, rows in allocations.items() for row in rows):
                raise ValueError("New Spot acquisition proof requires owned publication authority")
        duplicate_event = False
        if event_receipt is not None:
            _validate_event_receipt(event_receipt)
            receipts = data.setdefault("gui_trade_event_receipts", [])
            matches = [receipt for receipt in receipts if receipt["event_id"] == event_receipt["event_id"]]
            if matches and matches != [event_receipt]:
                raise ValueError("GUI trade event conflicts with committed receipt")
            if matches:
                duplicate_event = True
                if previous is None or any(
                    data[name] != previous[name] for name in ("entry_allocations", "open_position_records")
                ):
                    raise ValueError("committed GUI trade event cannot apply another mutation")
            if not matches:
                receipts.append(copy.deepcopy(event_receipt))
        _validate_snapshot(data, mode)
        if previous is not None and owned_spot_buy is None:
            _protect_owned_rows(previous, data)
        transaction = (ledger_transactions(file_path, owned_spot_buy.intent_path)
                       if isinstance(owned_spot_buy, SpotBuyPublicationContext) else ledger_transaction(file_path))
        with transaction:
            # Lock ordering: the process/file transaction precedes the brief per-window mutex.
            # Capture never holds this mutex while acquiring a storage transaction.
            with session._mutex if session is not None else nullcontext():
                observed = _read_receipt(file_path)
                guard_position_allocation_snapshot(file_path, observed,
                    expected_namespace=owned_spot_buy.namespace if owned_spot_buy is not None else None)
                if session is None:
                    # Independent bootstrap compatibility; existing state needs an actual receipt.
                    if observed != (None, None) or (file_path.parent.parent / _ALLOCATIONS_FILE_NAME).exists():
                        raise ValueError("existing allocation state requires a loaded receipt")
                elif captured is None or (
                    session._generation != captured[5] or not session.ready
                    or observed != (captured[2], captured[3])
                ):
                    raise ValueError("allocation state changed after this window loaded it")
                publication: AbstractContextManager = nullcontext()
                if owned_spot_buy is not None:
                    actual_record = _validate_owned_spot_buy_candidate(owned_spot_buy, captured, file_path, previous, data, event_receipt)
                    origin = _assert_gui_publication_origin(owned_spot_buy, session)
                    from app.integrations.exchanges.binance.orders.spot_inventory_checkpoint_runtime import owned_inventory_publication
                    publication = owned_inventory_publication(origin.wrapper,
                        allocation_path=file_path, expected_record=actual_record, fill=owned_spot_buy.fill)
                committed = committed_data = None
                with publication:
                    if owned_spot_buy is not None:
                        _assert_gui_publication_origin(owned_spot_buy, session)
                        if _read_receipt(file_path) != observed:
                            raise ValueError("owned allocation source changed during publication admission")
                    if not duplicate_event:
                        _write_snapshot(file_path, data)
                        committed = _read_receipt(file_path)
                        if committed[0] is None:
                            raise ValueError("published allocation state is missing")
                        committed_data = guard_position_allocation_snapshot(file_path, committed)
                        if committed_data is None:
                            raise ValueError("published allocation snapshot is missing")
                        _validate_snapshot(committed_data, mode)
                    if owned_spot_buy is not None:
                        _assert_gui_publication_origin(owned_spot_buy, session)
                if session is not None and committed is not None:
                    session._accept(file_path, mode, committed, committed_data)
        completed = True
        return True
    except _ALLOCATION_STATE_ERRORS as exc:
        failure_reason = str(exc) if isinstance(exc, ValueError) else failure_reason
        return False
    finally:
        if session is not None and not completed:
            # Retain the old receipt, fence admission, and require explicit two-map reload.
            # Never freshen the receipt before retrying old in-memory maps.
            session.invalidate(failure_reason)


def load_position_allocations(
    *, this_file: Path, mode: str | None = None, session: AllocationSnapshotSession | None = None,
    load_ticket: AllocationSnapshotLoadTicket | None = None,
) -> tuple[dict, dict]:
    generation = session._begin_load() if session is not None else None
    completed = False
    failure_reason = "allocation load failed"
    if load_ticket is not None:
        load_ticket._completion = None
    try:
        path = _get_allocations_file_path(this_file)
        legacy = path.parent.parent / _ALLOCATIONS_FILE_NAME
        _check_path(path)
        _check_path(legacy)
        # Lock both paths throughout migration and load; path lookup never moves files.
        with ledger_transactions(path, legacy):
            observed = _read_receipt(path)
            data = guard_position_allocation_snapshot(path, observed)
            if observed == (None, None):
                legacy_observed = _read_receipt(legacy)
                legacy_data = guard_position_allocation_snapshot(legacy, legacy_observed)
                if legacy_data is not None:
                    _validate_snapshot(legacy_data, mode)
                    _write_snapshot(path, legacy_data)
                    if _read_receipt(legacy) != legacy_observed:
                        raise ValueError("legacy allocation source changed during migration")
                    guard_position_allocation_snapshot(legacy, legacy_observed)
                    legacy.unlink()
                    observed = _read_receipt(path)
                    data = guard_position_allocation_snapshot(path, observed)
            if observed[0] is None:
                if session is not None:
                    with session._mutex:
                        if session._generation != generation:
                            return {}, {}
                        session._accept(path, mode, observed, None, pending_handoff=load_ticket is not None)
                        if load_ticket is not None:
                            load_ticket._completion = (path, mode, session._generation)
                completed = True
                return {}, {}
            if data is None:
                raise ValueError("loaded allocation snapshot is missing")
            _validate_snapshot(data, mode)
            allocations = {_deserialize_allocation_key(key): copy.deepcopy(rows) for key, rows in data["entry_allocations"].items()}
            records = {_deserialize_allocation_key(key): copy.deepcopy(record) for key, record in data["open_position_records"].items()}
            if session is not None:
                with session._mutex:
                    if session._generation != generation:
                        return {}, {}
                    session._accept(path, mode, observed, data, pending_handoff=load_ticket is not None)
                    if load_ticket is not None:
                        load_ticket._completion = (path, mode, session._generation)
            completed = True
            return allocations, records
    except _ALLOCATION_STATE_ERRORS as exc:
        failure_reason = str(exc) if isinstance(exc, ValueError) else failure_reason
        return {}, {}
    finally:
        if session is not None and not completed:
            with session._mutex:
                if session._generation == generation:
                    session.invalidate(failure_reason)
