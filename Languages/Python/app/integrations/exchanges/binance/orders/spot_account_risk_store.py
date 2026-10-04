"""INERT PROPOSAL: conditional storage/replay receipts, never trading authority.

ProtectedPort and private lifetime guards are supplied claims, not authentication,
account-wide exclusion, approved policy, reset authorization or permission. The
unconfigured default fences. No real credential adapter or runtime caller exists.
The portable file publisher is synthetic draft I/O, not qualified native durability.
A future adapter must supply genuine UID exclusion and original held-lock deadline.
Whole protected-store restoration/deletion or same-user compromise is not solved.
"""
from __future__ import annotations

from contextlib import contextmanager
from contextvars import ContextVar
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from fractions import Fraction
import hashlib
import json
import math
import os
from pathlib import Path
import re
import stat
import tempfile
import threading
import time
from typing import Callable, Iterator, NoReturn, Protocol, cast
from uuid import UUID, uuid4
from weakref import WeakKeyDictionary

from . import spot_account_risk_contract as risk


class RiskStoreError(ValueError):
    """Storage is fenced; the caller receives no permission from this error."""


class ProtectedPort(Protocol):
    """Conditional external anchor. Implementations must not silently reseed."""

    def read(self, slot: str) -> bytes | None: ...

    def write(self, slot: str, value: bytes) -> None: ...


@dataclass
class _Scope:
    path: Path
    port: ProtectedPort
    guard: Callable[[], None]
    deadline: float
    pid: int
    thread: int
    active: bool = True


@dataclass(frozen=True)
class _Attribution:
    scope: _Scope
    path: Path
    port: ProtectedPort
    guard: Callable[[], None]
    deadline: float
    pid: int
    thread: int


_CONTEXT: ContextVar[_Scope | None] = ContextVar("inert_risk_storage_scope", default=None)
_LOCAL = threading.local()
_IMPORT_PID = os.getpid()


@dataclass(frozen=True, eq=False)
class RiskReadReceipt:
    """Original storage receipt, not genuine account or submission authority."""

    path: Path
    raw: bytes
    file_identity: tuple[int, int, int, int]
    protected_raw: bytes
    state: risk.State
    risk_store_id: str
    revision: int
    chain_head: str


_ISSUED: WeakKeyDictionary[RiskReadReceipt, _Scope] = WeakKeyDictionary()


def _fail(message: str) -> NoReturn:
    raise RiskStoreError(message)


def _sha(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def _encode(value: object) -> bytes:
    try:
        return (json.dumps(value, sort_keys=True, indent=2, allow_nan=False) + "\n").encode("utf-8")
    except (TypeError, ValueError, OverflowError, RecursionError) as exc:
        raise RiskStoreError("Invalid canonical storage JSON") from exc


def _decode(raw: bytes) -> dict:
    try:
        value = risk.decode_contract(raw)
    except (ValueError, RecursionError) as exc:
        raise RiskStoreError("Invalid strict storage JSON") from exc
    if _encode(value) != raw:
        _fail("Noncanonical storage bytes")
    return cast(dict, value)


def _fields(value: object, names: set[str]) -> dict:
    if type(value) is not dict or set(value) != names:
        _fail("Missing, unknown or non-object storage fields")
    return value


def _positive(value: object) -> int:
    if type(value) is not int or not 0 < value <= 2**63 - 1:
        _fail("Invalid storage revision")
    return value


def _hash(value: object) -> str:
    if type(value) is not str or not re.fullmatch(r"[0-9a-f]{64}", value):
        _fail("Invalid canonical digest")
    return value


def _reference(value: object) -> str:
    if (type(value) is not str or not 0 < len(value) <= 128 or value.strip() != value
            or any(not 32 <= ord(char) <= 126 for char in value)):
        _fail("Invalid explicit operation/reference")
    return value


def _uuid(value: object) -> str:
    if type(value) is not str:
        _fail("Invalid risk store UUID")
    try:
        if str(UUID(value)) != value:
            _fail("Noncanonical risk store UUID")
    except ValueError as exc:
        raise RiskStoreError("Invalid risk store UUID") from exc
    return value


def _path(path: Path) -> Path:
    # Preserve basename; resolve parent aliases consistently. Final symlinks reject.
    path = Path(path)
    return Path(os.path.normcase(str(path.parent.resolve(strict=True) / path.name)))


@contextmanager
def _storage_scope(path: Path, *, protected: ProtectedPort,
                   guard: Callable[[], None], deadline: float) -> Iterator[None]:
    """Private supplied precondition, not a genuine UID or lock authority issuer."""
    if os.getpid() != _IMPORT_PID or _CONTEXT.get() is not None or getattr(_LOCAL, "expected", None) is not None:
        _fail("Inherited or nested storage scope")
    if (not callable(guard) or not callable(getattr(protected, "read", None))
            or not callable(getattr(protected, "write", None))
            or type(deadline) is not float or not math.isfinite(deadline) or deadline <= time.monotonic()):
        _fail("Explicit protected port, lifetime guard and original deadline required")
    guard()
    scope = _Scope(_path(path), protected, guard, deadline, os.getpid(), threading.get_ident())
    token = _CONTEXT.set(scope)
    _LOCAL.expected = scope
    _LOCAL.origin = _Attribution(scope, scope.path, protected, guard, deadline, scope.pid, scope.thread)
    try:
        _guard(scope.path)
        yield
        _guard(scope.path)
    finally:
        scope.active = False
        _CONTEXT.reset(token)
        _LOCAL.expected = None
        _LOCAL.origin = None


def _guard(path: Path) -> _Scope:
    scope = _CONTEXT.get()
    origin = cast(_Attribution, getattr(_LOCAL, "origin", None))

    def current() -> bool:
        return (scope is not None and type(origin) is _Attribution
                and _CONTEXT.get() is scope and getattr(_LOCAL, "expected", None) is scope
                and getattr(_LOCAL, "origin", None) is origin and origin.scope is scope
                and scope.active is True and os.getpid() == _IMPORT_PID
                and type(scope.pid) is int and scope.pid == origin.pid == os.getpid()
                and type(scope.thread) is int and scope.thread == origin.thread == threading.get_ident()
                and scope.path is origin.path and origin.path == _path(path)
                and scope.port is origin.port and scope.guard is origin.guard
                and type(scope.deadline) is float and scope.deadline == origin.deadline
                and time.monotonic() < origin.deadline)

    if not current():
        _fail("Missing, lost, changed, foreign or expired original storage scope")
    origin.guard()
    if not current():
        _fail("Original path/port/guard/deadline/lifetime changed during callback")
    return cast(_Scope, scope)


@contextmanager
def _errors() -> Iterator[None]:
    try:
        yield
    except (RiskStoreError, KeyboardInterrupt, SystemExit):
        raise
    except (OSError, risk.ContractError) as exc:
        raise RiskStoreError("Risk store storage/replay failed") from exc


def _cleanup(action: Callable[[], None], primary: BaseException | None) -> None:
    try:
        action()
    except BaseException as cleanup:
        if cleanup is primary:
            raise
        if isinstance(primary, (KeyboardInterrupt, SystemExit)):
            previous = primary.__cause__
            if previous is not None and previous is not cleanup:
                # Retain earlier cleanup diagnostics without repeated-reference cycles.
                chain: list[BaseException] = []
                current: BaseException | None = cleanup
                while current is not None and all(current is not error for error in chain):
                    chain.append(current)
                    current = current.__cause__
                prior_chain: list[BaseException] = []
                current = previous
                while current is not None and all(current is not error for error in prior_chain):
                    prior_chain.append(current)
                    current = current.__cause__
                if all(previous is not error for error in chain) and not any(left is right for left in chain for right in prior_chain):
                    chain[-1].__cause__ = previous
            raise primary from cleanup
        raise cleanup from primary


def _identity(value: os.stat_result) -> tuple[int, int, int, int]:
    if (not stat.S_ISREG(value.st_mode) or value.st_nlink != 1
            or getattr(value, "st_file_attributes", 0) & 0x400):
        _fail("Unique regular non-reparse file required")
    return value.st_dev, value.st_ino, value.st_size, value.st_mtime_ns


def _read(path: Path, scope_path: Path) -> tuple[bytes, tuple[int, int, int, int]] | None:
    _guard(scope_path)
    try:
        before = _identity(path.lstat())
    except FileNotFoundError:
        _guard(scope_path)
        return None
    fd = os.open(path, os.O_RDONLY | getattr(os, "O_BINARY", 0) | getattr(os, "O_NOFOLLOW", 0))
    primary = None
    try:
        opened = _identity(os.fstat(fd))
        chunks = []
        while True:
            _guard(scope_path)
            chunk = os.read(fd, 1024 * 1024)
            if not chunk:
                break
            chunks.append(chunk)
        raw = b"".join(chunks)
        after = _identity(os.fstat(fd))
        if before != opened or opened != after or after != _identity(path.lstat()) or len(raw) != after[2]:
            _fail("Risk file changed during exact read")
        _guard(scope_path)
        return raw, after
    except BaseException as exc:
        primary = exc
        raise
    finally:
        _cleanup(lambda: os.close(fd), primary)


def _same_source(path: Path, expected: tuple[bytes, tuple[int, int, int, int]] | None) -> None:
    if _read(path, path) != expected:
        _fail("Original risk source changed")


def _slot(identity: dict) -> str:
    parsed = risk.parse_identity(identity)
    # Deliberately excludes source path, store, credentials and owner generation.
    return "inert-risk-v1-" + _sha(f"binance/spot/live/uid-{parsed.account_uid}".encode("ascii"))


def _get(path: Path, identity: dict) -> bytes | None:
    scope = _guard(path)
    value = scope.port.read(_slot(identity))
    _guard(path)
    if value is not None and (type(value) is not bytes or not 0 < len(value) < 2560):
        _fail("Invalid protected risk value")
    return value


def _put(path: Path, identity: dict, expected: bytes | None, value: bytes) -> None:
    if len(value) >= 2560 or _get(path, identity) != expected:
        _fail("Protected original value changed")
    scope = _guard(path)
    scope.port.write(_slot(identity), value)
    _guard(path)
    if _get(path, identity) != value:
        _fail("Protected write readback did not match")


def _provenance(raw: object, identity: dict) -> dict:
    value = _fields(raw, {"version", "basis", "identity", "reference", "record_digest", "request_digest", "evidence_digest"})
    if (_positive(value["version"]) != 1 or type(value["basis"]) is not str
            or value["basis"] != "unverified_supplied_claim" or _encode(value["identity"]) != _encode(identity)):
        _fail("Unsupported or changed supplied provenance identity/basis")
    risk.parse_identity(value["identity"])
    _reference(value["reference"])
    for key in ("record_digest", "request_digest", "evidence_digest"):
        _hash(value[key])
    return _decode(_encode(value))


def _projection(state: risk.State) -> dict:
    def fraction(value: object) -> list[int]:
        if type(value) is not Fraction:
            _fail("Unsupported materialized state type")
        return [value.numerator, value.denominator]
    raw = json.dumps(asdict(state), default=fraction, sort_keys=True, allow_nan=False)
    return cast(dict, risk.decode_contract(raw.encode("utf-8")))


def _event_raw(event: risk.Event) -> dict:
    if (type(event) is not risk.Event or type(event.at) is not int or not 0 <= event.at <= 2**63 - 1
            or type(event.payload) is not str):
        _fail("Exact parsed event/scalar types required")
    try:
        at = datetime.fromtimestamp(event.at, timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    except (OSError, OverflowError, ValueError) as exc:
        raise RiskStoreError("Unsupported exact event time") from exc
    try:
        payload = risk.decode_contract(event.payload.encode("utf-8"))
    except (ValueError, RecursionError) as exc:
        raise RiskStoreError("Invalid exact event payload") from exc
    value = {"event_id": event.event_id, "expected_head": event.expected_head,
             "at": at,
             "kind": event.kind, "data": payload}
    if risk.parse_event(value) != event:
        _fail("Noncanonical event")
    return value


def _replay(raw: bytes, identity: dict) -> tuple[dict, risk.State]:
    value = _fields(_decode(raw), {"version", "risk_store_id", "identity", "opening", "opening_provenance", "entries", "head", "projection"})
    if _positive(value["version"]) != 1 or _encode(value["identity"]) != _encode(identity):
        _fail("Risk snapshot identity/version changed")
    risk.parse_identity(value["identity"])
    store_id = _uuid(value["risk_store_id"])
    opening = value["opening"]
    state = risk.opening_state(opening)
    if _encode(opening["identity"]) != _encode(identity):
        _fail("Opening account/store identity changed")
    proof = _provenance(value["opening_provenance"], identity)
    chain = _sha(_encode({"risk_store_id": store_id, "opening": opening, "provenance": proof}))
    if type(value["entries"]) is not list:
        _fail("Complete ordered event history required")
    seen = set()
    for revision, row in enumerate(value["entries"], 2):
        row = _fields(row, {"event", "provenance", "previous_chain_head", "chain_head", "state_head"})
        event = risk.parse_event(row["event"])
        if event.event_id in seen or row["previous_chain_head"] != chain:
            _fail("Historical event identity/chain changed")
        proof = _provenance(row["provenance"], identity)
        state = risk.apply_event(state, event)
        candidate = {"revision": revision, "previous_chain_head": chain, "event": row["event"],
                     "provenance": proof, "state_head": state.head}
        chain = _sha(_encode(candidate))
        if _hash(row["chain_head"]) != chain or _hash(row["state_head"]) != state.head:
            _fail("Historical revision commitment changed")
        seen.add(event.event_id)
    expected_head = {"revision": len(value["entries"]) + 1, "chain_head": chain, "state_head": state.head}
    if _encode(value["head"]) != _encode(expected_head) or _encode(value["projection"]) != _encode(_projection(state)):
        _fail("Head/projection differs from complete history replay")
    return value, state


def _head(raw: bytes, value: dict) -> dict:
    return dict(value["head"], digest=_sha(raw))


def _parse_head(raw: object) -> dict:
    value = _fields(raw, {"revision", "digest", "chain_head", "state_head"})
    _positive(value["revision"])
    for key in ("digest", "chain_head", "state_head"):
        _hash(value[key])
    return value


def _base(path: Path, value: dict, identity: dict) -> dict:
    return {"version": 1, "identity": identity, "path_digest": _sha(str(path).encode("utf-8")),
            "risk_store_id": value["risk_store_id"], "opening_digest": _sha(_encode(value["opening"])),
            "opening_provenance_digest": _sha(_encode(value["opening_provenance"])),
            "policy_digest": _sha(_encode(value["opening"]["policy"]))}


def _anchor(raw: bytes, path: Path, identity: dict) -> dict:
    value = _decode(raw)
    names = {"version", "state", "identity", "path_digest", "risk_store_id", "opening_digest", "opening_provenance_digest", "policy_digest"}
    if value.get("state") == "stable" and type(value.get("state")) is str:
        names |= {"head"}
    elif value.get("state") == "pending" and type(value.get("state")) is str:
        names |= {"previous", "target", "operation_digest"}
    else:
        _fail("Invalid protected risk state")
    _fields(value, names)
    if (_positive(value["version"]) != 1 or _encode(value["identity"]) != _encode(identity)
            or _hash(value["path_digest"]) != _sha(str(path).encode("utf-8"))):
        _fail("Protected account/original path changed")
    risk.parse_identity(value["identity"])
    _uuid(value["risk_store_id"])
    for key in ("opening_digest", "opening_provenance_digest", "policy_digest"):
        _hash(value[key])
    if value["state"] == "stable":
        _parse_head(value["head"])
    else:
        target = _parse_head(value["target"])
        _hash(value["operation_digest"])
        previous = value["previous"]
        if previous is None:
            if target["revision"] != 1:
                _fail("Invalid bootstrap target")
        elif _parse_head(previous)["revision"] + 1 != target["revision"]:
            _fail("Invalid consecutive pending revision")
    return value


def _matches_anchor(path: Path, value: dict, raw: bytes, anchor: dict, identity: dict) -> None:
    for name, expected in _base(path, value, identity).items():
        if _encode(anchor[name]) != _encode(expected):
            _fail("Protected immutable risk basis changed")
    expected = anchor["head"] if anchor["state"] == "stable" else anchor["target"]
    if _encode(expected) != _encode(_head(raw, value)):
        _fail("Source differs from latest protected risk head")


def _issue(path: Path, source: tuple[bytes, tuple[int, int, int, int]], protected: bytes, value: dict, state: risk.State) -> RiskReadReceipt:
    receipt = RiskReadReceipt(path, source[0], source[1], protected, state, value["risk_store_id"], value["head"]["revision"], value["head"]["chain_head"])
    _ISSUED[receipt] = _guard(path)
    return receipt


def read_risk_store(path: Path, identity: dict) -> RiskReadReceipt:
    """Read and fully replay under supplied scope; never grant order authority."""
    with _errors():
        path = _guard(path).path
        protected = _get(path, identity)  # Slot first, before missing source branch.
        if protected is None:
            _fail("Missing protected risk authority; no automatic reseed")
        anchor = _anchor(protected, path, identity)
        if anchor["state"] != "stable":
            _fail("Prepared risk transition requires exact forward recovery")
        if any(entry.name.startswith(path.name + ".risk-pending.") for entry in path.parent.iterdir()):
            _fail("Stable leftover journal requires separate review; no adoption or deletion")
        source = _read(path, path)
        if source is None:
            _fail("Protected risk source missing")
        value, state = _replay(source[0], identity)
        _matches_anchor(path, value, source[0], anchor, identity)
        _same_source(path, source)
        if _get(path, identity) != protected:
            _fail("Protected risk authority changed during read")
        return _issue(path, source, protected, value, state)


def _journal(path: Path, operation: str) -> Path:
    return path.with_name(path.name + ".risk-pending." + operation + ".json")


def _write_exact(path: Path, raw: bytes, scope_path: Path, *, exclusive: bool,
                 before_replace: Callable[[], None] | None = None) -> None:
    _guard(scope_path)
    if exclusive:
        fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_BINARY", 0), 0o600)
        temp = None
    else:
        fd, name = tempfile.mkstemp(prefix=path.name + ".write-", dir=path.parent)
        temp = Path(name)
    written_identity: tuple[int, int, int, int] | None = None
    primary = None
    try:
        offset = 0
        while offset < len(raw):
            _guard(scope_path)
            count = os.write(fd, raw[offset:])
            if count <= 0:
                _fail("Short risk storage write")
            offset += count
        _guard(scope_path)
        os.fsync(fd)
        _guard(scope_path)
        if temp is not None:
            written_identity = _identity(os.fstat(fd))
    except BaseException as exc:
        primary = exc
        raise
    finally:
        try:
            _cleanup(lambda: os.close(fd), primary)
        except BaseException as exc:
            primary = exc
            raise
        finally:
            if temp is not None and primary is not None:
                _cleanup(lambda: temp.unlink(missing_ok=True), primary)
    if temp is not None:
        primary = None
        try:
            _guard(scope_path)
            if before_replace is None:
                _fail("Original source/protected CAS callback required before replacement")
            before_replace()
            _guard(scope_path)
            if _read(temp, scope_path) != (raw, written_identity):
                _fail("Prepared temporary candidate bytes/identity changed")
            os.replace(temp, path)
            _guard(scope_path)
        except BaseException as exc:
            primary = exc
            raise
        finally:
            _cleanup(lambda: temp.unlink(missing_ok=True), primary)


def _finish(path: Path, identity: dict, pending_raw: bytes, pending: dict) -> RiskReadReceipt:
    journal = _journal(path, pending["operation_digest"])
    target = _read(journal, path)
    if target is None:
        _fail("Exact prepared target journal missing")
    value, state = _replay(target[0], identity)
    _matches_anchor(path, value, target[0], pending, identity)
    source = _read(path, path)
    if source is None:
        old_matches = pending["previous"] is None
    else:
        old_matches = pending["previous"] is not None and _sha(source[0]) == pending["previous"]["digest"]
    if source is None or source[0] != target[0]:
        if not old_matches:
            _fail("Current risk source is neither exact old nor exact target")
        if _get(path, identity) != pending_raw:
            _fail("Prepared risk authority changed")
        _same_source(path, source)
        def before_replace() -> None:
            if _read(journal, path) != target or _get(path, identity) != pending_raw:
                _fail("Original prepared journal/protected authority changed before replacement")
            _same_source(path, source)
            _guard(path)
        _write_exact(path, target[0], path, exclusive=False, before_replace=before_replace)
    current = _read(path, path)
    if current is None or current[0] != target[0]:
        _fail("Prepared target publication not exact")
    # Journal must still be original; compare under risk source scope.
    if _read(journal, path) != target:
        _fail("Prepared journal changed")
    stable = _encode(dict(_base(path, value, identity), state="stable", head=_head(target[0], value)))
    _same_source(path, current)
    _put(path, identity, pending_raw, stable)
    _guard(path)
    if _read(journal, path) != target:
        _fail("Stable journal cleanup identity changed")
    _guard(path)
    journal.unlink()
    _guard(path)
    _same_source(path, current)
    if _get(path, identity) != stable:
        _fail("Stable risk authority changed after publication")
    return _issue(path, current, stable, value, state)


def _prepare(path: Path, identity: dict, old: tuple[bytes, tuple[int, int, int, int]] | None,
             protected: bytes | None, value: dict, operation_id: str) -> RiskReadReceipt:
    raw = _encode(value)
    value, _ = _replay(raw, identity)
    operation = _sha(_reference(operation_id).encode("ascii"))
    journal = _journal(path, operation)
    _write_exact(journal, raw, path, exclusive=True)
    journal_readback = _read(journal, path)
    if journal_readback is None or journal_readback[0] != raw:
        _fail("Prepared journal readback failed")
    _same_source(path, old)
    previous = None if old is None else _head(old[0], _decode(old[0]))
    pending = dict(_base(path, value, identity), state="pending", previous=previous,
                   target=_head(raw, value), operation_digest=operation)
    pending_raw = _encode(pending)
    _anchor(pending_raw, path, identity)
    _put(path, identity, protected, pending_raw)
    return _finish(path, identity, pending_raw, pending)


def bootstrap_risk_store(path: Path, opening: dict, provenance: dict, *, operation_id: str) -> RiskReadReceipt:
    """Explicit absent synthetic foundation; supplied opening is not authority."""
    with _errors():
        path = _guard(path).path
        state = risk.opening_state(opening)
        identity = _decode(_encode(opening))["identity"]
        if _get(path, identity) is not None or _read(path, path) is not None:
            _fail("Existing protected/source state cannot be reseeded")
        if any(entry.name.startswith(path.name + ".risk-pending.") for entry in path.parent.iterdir()):
            _fail("Unprotected orphan journal cannot bootstrap authority")
        proof = _provenance(provenance, identity)
        store_id = str(uuid4())
        chain = _sha(_encode({"risk_store_id": store_id, "opening": opening, "provenance": proof}))
        value = {"version": 1, "risk_store_id": store_id, "identity": identity, "opening": opening,
                 "opening_provenance": proof, "entries": [], "projection": _projection(state),
                 "head": {"revision": 1, "chain_head": chain, "state_head": state.head}}
        return _prepare(path, identity, None, None, value, operation_id)


def append_risk_event(path: Path, expected: RiskReadReceipt, event: risk.Event,
                      provenance: dict) -> RiskReadReceipt:
    """Append exactly one event/provenance; no financial authority is issued."""
    with _errors():
        path = _guard(path).path
        if (type(expected) is not RiskReadReceipt or expected not in _ISSUED
                or _ISSUED[expected] is not _guard(path) or expected.path != path):
            _fail("Original issued read receipt for this path required")
        identity = risk.decode_contract(expected.state.opening_payload.encode("utf-8"))["identity"]
        current = read_risk_store(path, identity)
        if (current.raw != expected.raw or current.file_identity != expected.file_identity
                or current.protected_raw != expected.protected_raw):
            _fail("Stale original risk source/authority receipt")
        value, state = _replay(expected.raw, identity)
        event_raw, proof = _event_raw(event), _provenance(provenance, identity)
        for row in value["entries"]:
            if row["event"]["event_id"] == event.event_id:
                if _encode(row["event"]) != _encode(event_raw) or _encode(row["provenance"]) != _encode(proof):
                    _fail("Changed duplicate event or provenance")
                _guard(path)
                return expected
        result = risk.apply_event(state, event)
        candidate = {"revision": current.revision + 1, "previous_chain_head": current.chain_head,
                     "event": event_raw, "provenance": proof, "state_head": result.head}
        chain = _sha(_encode(candidate))
        value["entries"].append({"event": event_raw, "provenance": proof, "previous_chain_head": current.chain_head,
                                 "chain_head": chain, "state_head": result.head})
        value["head"] = {"revision": current.revision + 1, "chain_head": chain, "state_head": result.head}
        value["projection"] = _projection(result)
        return _prepare(path, identity, (expected.raw, expected.file_identity), expected.protected_raw, value, event.event_id)


def recover_risk_store(path: Path, identity: dict, *, operation_id: str) -> RiskReadReceipt | None:
    """Forward-only exact prepared target. Stable matching source returns None."""
    with _errors():
        path = _guard(path).path
        protected = _get(path, identity)
        if protected is None:
            _fail("Missing protected risk authority; recovery cannot reseed")
        anchor = _anchor(protected, path, identity)
        if anchor["state"] == "stable":
            read_risk_store(path, identity)
            return None
        if anchor["operation_digest"] != _sha(_reference(operation_id).encode("ascii")):
            _fail("Prepared operation does not match")
        return _finish(path, identity, protected, anchor)
