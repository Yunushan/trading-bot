"""Publish one desktop portfolio only against that window's loaded snapshot."""
from __future__ import annotations

import copy
import json
import os
import stat
import threading
import time
from contextlib import contextmanager, nullcontext
from dataclasses import dataclass, field
from decimal import Decimal, InvalidOperation
from pathlib import Path

from app.integrations.exchanges.binance.orders.order_intent_store import (
    ledger_transaction,
    ledger_transactions,
    write_ledger,
)
from app.settings.live_safety import LiveTradingSafetyError

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
        with self._mutex:
            receipts = (self._snapshot or {}).get("gui_trade_event_receipts", [])
            matches = [receipt for receipt in receipts if receipt["event_id"] == descriptor["event_id"]]
            if matches and matches != [descriptor]:
                raise ValueError("GUI trade event conflicts with committed receipt")
            return self.state == "loaded" and matches == [descriptor]


def _get_allocations_file_path(this_file: Path) -> Path:
    # Path resolution is not permission to migrate or publish state.
    return this_file.absolute().parents[2] / _ALLOCATIONS_DIR_NAME / _ALLOCATIONS_FILE_NAME


def get_position_allocations_path(this_file: Path) -> Path:
    """Return the canonical path without reading, creating or migrating state."""
    return _get_allocations_file_path(this_file)


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


def _write_snapshot(file_path: Path, payload: dict) -> None:
    _check_path(file_path)
    write_ledger(file_path, payload)


def _protect_owned_rows(previous: dict, candidate: dict) -> None:
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


def save_position_allocations(
    entry_allocations: dict, open_position_records: dict, *, this_file: Path,
    mode: str | None = None, session: AllocationSnapshotSession | None = None,
    event_receipt: dict | None = None,
) -> bool:
    completed = False
    failure_reason = "allocation publication failed"
    try:
        file_path = _get_allocations_file_path(this_file)
        _check_path(file_path)
        captured = session._capture() if session is not None else None
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
        if previous is not None:
            _protect_owned_rows(previous, data)
        with ledger_transaction(file_path):
            # Lock ordering: the process/file transaction precedes the brief per-window mutex.
            # Capture never holds this mutex while acquiring a storage transaction.
            with session._mutex if session is not None else nullcontext():
                observed = _read_receipt(file_path)
                if session is None:
                    # Independent bootstrap compatibility; existing state needs an actual receipt.
                    if observed != (None, None) or (file_path.parent.parent / _ALLOCATIONS_FILE_NAME).exists():
                        raise ValueError("existing allocation state requires a loaded receipt")
                elif captured is None or (
                    session._generation != captured[5] or not session.ready
                    or observed != (captured[2], captured[3])
                ):
                    raise ValueError("allocation state changed after this window loaded it")
                if not duplicate_event:
                    _write_snapshot(file_path, data)
                    committed = _read_receipt(file_path)
                    if committed[0] is None:
                        raise ValueError("published allocation state is missing")
                    committed_data = _decode(committed[0], mode)
                    if session is not None:
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
            if observed == (None, None):
                legacy_observed = _read_receipt(legacy)
                if legacy_observed[0] is not None:
                    data = _decode(legacy_observed[0], mode)
                    _write_snapshot(path, data)
                    legacy.unlink()
                    observed = _read_receipt(path)
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
            data = _decode(observed[0], mode)
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
