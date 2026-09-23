"""Single-host Spot owner gate; this is not exchange-side fencing."""

from __future__ import annotations

import json
import os
import stat
import threading
import weakref
from collections.abc import Iterator, Mapping
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path

from app.security.redaction import redact_text
from app.settings.live_safety import LiveTradingSafetyError

from .order_intent_store import _ensure_parent, _try_lock, _unlock, write_ledger


_SESSIONS_LOCK = threading.RLock()
_SESSIONS: dict[Path, SpotExecutionOwner] = {}
_MARKER_VERSION = 1
_OWNER_STATES = {"armed", "active", "recovery_required"}
RECONCILIATION_ACK = "I_HAVE_STOPPED_EXECUTORS_AND_RECONCILED_EXCHANGE_STATE"


def owner_lock_path(ledger_path: Path) -> Path:
    return ledger_path.with_name(".spot-execution-owner.lock")


def owner_marker_path(ledger_path: Path) -> Path:
    return ledger_path.with_name("spot-execution-owner.json")


def _lock_file(path: Path) -> int:
    try:
        _ensure_parent(path)
        if path.is_symlink():
            raise LiveTradingSafetyError("Spot execution owner lock must not be a symbolic link.")
        fd = os.open(path, os.O_RDWR | os.O_CREAT | getattr(os, "O_NOFOLLOW", 0), 0o600)
        try:
            if not stat.S_ISREG(os.fstat(fd).st_mode):
                raise LiveTradingSafetyError("Spot execution owner lock must be a regular file.")
            _try_lock(fd)
        except BaseException:
            os.close(fd)
            raise
        return fd
    except LiveTradingSafetyError:
        raise
    except OSError as exc:
        raise LiveTradingSafetyError(
            f"Spot execution owner is unavailable; submission is blocked: {redact_text(exc)}"
        ) from exc


def _read_marker(path: Path, *, uid: int, environment: str, store_id: str) -> dict[str, object]:
    if path.is_symlink():
        raise LiveTradingSafetyError("Spot execution owner state must not be a symbolic link.")
    def unique_fields(pairs):
        result = {}
        for key, value in pairs:
            if key in result:
                raise ValueError("duplicate owner field")
            result[key] = value
        return result

    try:
        marker = json.loads(path.read_text(encoding="utf-8"), object_pairs_hook=unique_fields)
    except (OSError, ValueError) as exc:
        raise LiveTradingSafetyError("Spot execution owner state is missing or unreadable; submission is blocked.") from exc
    if (
        not isinstance(marker, dict)
        or set(marker) != {
            "format_version", "account_uid", "environment", "store_id", "state", "generation",
            "updated_at", "reconciliation_reference",
        }
        or type(marker["format_version"]) is not int
        or marker["format_version"] != _MARKER_VERSION
        or type(marker["account_uid"]) is not int
        or marker["account_uid"] != uid
        or marker["environment"] != environment
        or marker["store_id"] != store_id
        or not isinstance(marker["state"], str)
        or marker["state"] not in _OWNER_STATES
        or type(marker["generation"]) is not int
        or marker["generation"] < 0
        or not isinstance(marker["updated_at"], str)
        or not isinstance(marker.get("reconciliation_reference"), str)
        or not marker["reconciliation_reference"].strip()
    ):
        raise LiveTradingSafetyError("Spot execution owner state does not match this account ledger.")
    return marker


def _write_marker(path: Path, marker: Mapping[str, object], *, state: str, increment: bool = False) -> None:
    updated = dict(marker)
    updated["state"] = state
    updated["updated_at"] = datetime.now(timezone.utc).isoformat()
    if increment:
        updated["generation"] = int(updated["generation"]) + 1
    try:
        write_ledger(path, updated)
    except (OSError, TypeError, ValueError) as exc:
        raise LiveTradingSafetyError(
            f"Spot execution owner state could not be persisted: {redact_text(exc)}"
        ) from exc


@contextmanager
def owner_administration_lock(ledger_path: Path) -> Iterator[None]:
    """Serialize offline provisioning/rearming against an active owner."""
    path = owner_lock_path(ledger_path)
    with _SESSIONS_LOCK:
        if path in _SESSIONS:
            raise LiveTradingSafetyError("Spot execution owner is active; stop it before administration.")
        fd = _lock_file(path)
    try:
        yield
    finally:
        try:
            _unlock(fd)
        finally:
            os.close(fd)


def provision_owner_marker(ledger_path: Path, *, uid: int, environment: str, store_id: str) -> None:
    with owner_administration_lock(ledger_path):
        provision_owner_marker_locked(ledger_path, uid=uid, environment=environment, store_id=store_id)


def provision_owner_marker_locked(ledger_path: Path, *, uid: int, environment: str, store_id: str) -> None:
    """Caller must hold owner_administration_lock for the full state transition."""
    path = owner_marker_path(ledger_path)
    if path.exists() or path.is_symlink():
        raise LiveTradingSafetyError("Spot execution owner state already exists; it will not be overwritten.")
    marker = {
        "format_version": _MARKER_VERSION,
        "account_uid": uid,
        "environment": environment,
        "store_id": store_id,
        "state": "armed",
        "generation": 0,
        "updated_at": datetime.now(timezone.utc).isoformat(),
        "reconciliation_reference": "initial-provisioning-attestation",
    }
    _write_marker(path, marker, state="armed")


def rearm_owner_marker(
    ledger_path: Path, *, uid: int, environment: str, store_id: str,
    acknowledgement: str, reconciliation_reference: str,
) -> None:
    with owner_administration_lock(ledger_path):
        rearm_owner_marker_locked(
            ledger_path, uid=uid, environment=environment, store_id=store_id,
            acknowledgement=acknowledgement, reconciliation_reference=reconciliation_reference,
        )


def rearm_owner_marker_locked(
    ledger_path: Path, *, uid: int, environment: str, store_id: str,
    acknowledgement: str, reconciliation_reference: str,
) -> None:
    """Caller must hold owner_administration_lock for the full state transition."""
    if acknowledgement != RECONCILIATION_ACK:
        raise LiveTradingSafetyError("Rearm requires the operator exchange-reconciliation acknowledgement.")
    if (
        not isinstance(reconciliation_reference, str)
        or not reconciliation_reference.strip()
        or len(reconciliation_reference) > 160
        or any(character in reconciliation_reference for character in "\r\n\0")
    ):
        raise LiveTradingSafetyError("Rearm requires a short reconciliation evidence reference.")
    path = owner_marker_path(ledger_path)
    marker = _read_marker(path, uid=uid, environment=environment, store_id=store_id)
    if marker["state"] == "armed":
        raise LiveTradingSafetyError("Spot execution owner is already armed.")
    marker["reconciliation_reference"] = reconciliation_reference.strip()
    _write_marker(path, marker, state="armed")


class SpotExecutionOwner:
    """Retain one OS lock for the whole local execution session."""

    def __init__(
        self, ledger_path: Path, *, uid: int, environment: str, store_id: str,
        credential_fingerprint: str, fd: int, owner_wrapper: object,
    ) -> None:
        self.ledger_path = ledger_path
        self.lock_path = owner_lock_path(ledger_path)
        self.marker_path = owner_marker_path(ledger_path)
        self.uid = uid
        self.environment = environment
        self.store_id = store_id
        self.credential_fingerprint = credential_fingerprint
        self.pid = os.getpid()
        self.fd: int | None = fd
        self._file_stat = os.fstat(fd)
        self._submission_lock = threading.RLock()
        self._owner_ref = weakref.ref(owner_wrapper)
        self._finalizer = weakref.finalize(owner_wrapper, self.close)
        self.generation: int | None = None

    def assert_held(
        self, *, uid: int, environment: str, credential_fingerprint: str, owner_wrapper: object,
    ) -> None:
        if (
            self.fd is None or self.pid != os.getpid() or self.uid != uid
            or self.environment != environment
            or self.credential_fingerprint != credential_fingerprint
            or _SESSIONS.get(self.lock_path) is not self
            or self._owner_ref() is not owner_wrapper
        ):
            raise LiveTradingSafetyError("Spot execution owner is lost or its credential changed; submission is blocked.")
        try:
            held = os.fstat(self.fd)
            current = os.stat(self.lock_path, follow_symlinks=False)
        except OSError as exc:
            raise LiveTradingSafetyError("Spot execution owner lock cannot be verified; submission is blocked.") from exc
        if (
            not stat.S_ISREG(current.st_mode)
            or (held.st_dev, held.st_ino) != (current.st_dev, current.st_ino)
            or (held.st_dev, held.st_ino) != (self._file_stat.st_dev, self._file_stat.st_ino)
        ):
            raise LiveTradingSafetyError("Spot execution owner lock was replaced; submission is blocked.")
        marker = _read_marker(
            self.marker_path, uid=self.uid, environment=self.environment, store_id=self.store_id,
        )
        if marker["state"] != "active" or marker["generation"] != self.generation:
            raise LiveTradingSafetyError("Spot execution owner state changed; submission is blocked.")

    @contextmanager
    def submission(
        self, *, uid: int, environment: str, credential_fingerprint: str, owner_wrapper: object,
    ) -> Iterator[None]:
        with self._submission_lock:
            self.assert_held(
                uid=uid, environment=environment, credential_fingerprint=credential_fingerprint,
                owner_wrapper=owner_wrapper,
            )
            yield

    def close(self) -> None:
        with self._submission_lock, _SESSIONS_LOCK:
            if self.fd is None:
                return
            fd, self.fd = self.fd, None
            self._finalizer.detach()
            try:
                marker = _read_marker(
                    self.marker_path, uid=self.uid, environment=self.environment, store_id=self.store_id,
                )
                if marker["state"] == "active":
                    _write_marker(self.marker_path, marker, state="recovery_required")
            finally:
                _SESSIONS.pop(self.lock_path, None)
                _unlock(fd)
                os.close(fd)


def claim_execution_owner(
    ledger_path: Path, *, uid: int, environment: str, store_id: str,
    credential_fingerprint: str, owner_wrapper: object,
) -> SpotExecutionOwner:
    path = owner_lock_path(ledger_path)
    with _SESSIONS_LOCK:
        existing = _SESSIONS.get(path)
        if existing is not None:
            existing.assert_held(
                uid=uid, environment=environment, credential_fingerprint=credential_fingerprint,
                owner_wrapper=owner_wrapper,
            )
            if existing.store_id != store_id:
                raise LiveTradingSafetyError("Spot account ledger changed while its execution owner was active.")
            return existing
        fd = _lock_file(path)
        owner = SpotExecutionOwner(
            ledger_path, uid=uid, environment=environment, store_id=store_id,
            credential_fingerprint=credential_fingerprint, fd=fd, owner_wrapper=owner_wrapper,
        )
        try:
            marker = _read_marker(owner.marker_path, uid=uid, environment=environment, store_id=store_id)
            if marker["state"] != "armed":
                raise LiveTradingSafetyError(
                    "Spot execution owner needs exchange reconciliation and operator rearm before reacquisition."
                )
            _write_marker(owner.marker_path, marker, state="active", increment=True)
            owner.generation = int(marker["generation"]) + 1
        except BaseException:
            _unlock(fd)
            os.close(fd)
            owner.fd = None
            raise
        _SESSIONS[path] = owner
        return owner
