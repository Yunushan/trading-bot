"""Qualify a synthetic, bounded scrypt candidate; never accepts credentials.

This probe does not migrate ledgers, select production latency budgets, or
certify credential storage. It exercises three RFC 7914 section 12 vectors
and one fixed candidate profile before any production binding integration.
The fourth RFC vector needs about 1 GiB and is outside this probe's bound.

References:
https://www.rfc-editor.org/rfc/rfc7914.html#section-12
https://cheatsheetseries.owasp.org/cheatsheets/Password_Storage_Cheat_Sheet.html#scrypt
https://docs.python.org/3/library/hashlib.html#hashlib.scrypt
"""
from __future__ import annotations

import sys

_ATTEMPTS = {"network": 0, "process": 0, "native_bridge": 0, "registry": 0}


def _audit_barrier(event: str, _arguments: tuple[object, ...]) -> None:
    category = None
    if event.startswith("socket."):
        category = "network"
    elif event == "subprocess.Popen" or event in {"os.system", "os.exec", "os.spawn", "os.posix_spawn"}:
        category = "process"
    elif event.startswith("ctypes."):
        category = "native_bridge"
    elif event.startswith("winreg."):
        category = "registry"
    if category is not None:
        _ATTEMPTS[category] += 1
        raise RuntimeError("Synthetic KDF qualification forbids this runtime operation.")


# Install before importing the cryptographic backend. Frozen bootloader and
# interpreter startup precede this Python hook; they require external isolation.
sys.addaudithook(_audit_barrier)

import hashlib  # noqa: E402
import json  # noqa: E402
import ssl  # noqa: E402
import time  # noqa: E402


class QualificationError(RuntimeError):
    """A fixed synthetic cryptographic or barrier control did not pass."""


_MAXMEM = 192 * 1024 * 1024
_PROFILE = {"n": 131072, "r": 8, "p": 1, "dklen": 32, "maxmem": _MAXMEM}
_VECTORS = (
    (b"", b"", 16, 1, 1,
     "77d6576238657b203b19ca42c18a0497f16b4844e3074ae8dfdffa3fede21442"
     "fcd0069ded0948f8326a753a0fc81f17e8d3e0fb2e0d3628cf35e20c38d18906"),
    (b"password", b"NaCl", 1024, 8, 16,
     "fdbabe1c9d3472007856e7190d01e9fe7c6ad7cbc8237830e77376634b373162"
     "2eaf30d92e22a3886ff109279d9830dac727afb94a83ee6d8360cbdfa2cc0640"),
    (b"pleaseletmein", b"SodiumChloride", 16384, 8, 1,
     "7023bdcb3afd7348461c06cd81fd38ebfda8fbba904f8e3ea9b543f6545da1f2"
     "d5432955613f0fcf62d49705242a9af9e61e85dc0d651e40dfcf017b45575887"),
)


def _require(condition: bool, message: str) -> None:
    if not condition:
        raise QualificationError(message)


def _barrier_controls() -> dict[str, int]:
    before = dict(_ATTEMPTS)
    for event in ("socket.connect", "subprocess.Popen", "ctypes.dlopen", "winreg.OpenKey"):
        try:
            # Emit synthetic audit events, without loading a bridge, opening a
            # registry key, creating a process or contacting an endpoint.
            sys.audit(event)
        except RuntimeError:
            continue
        raise QualificationError("Runtime audit barrier control failed.")
    counts = {key: _ATTEMPTS[key] - before[key] for key in _ATTEMPTS}
    _require(all(value == 1 for value in counts.values()), "Runtime audit barrier control counts differ.")
    return counts


def qualify() -> dict[str, object]:
    initial_attempts = dict(_ATTEMPTS)
    _require(all(value == 0 for value in initial_attempts.values()), "Backend import attempted a forbidden operation.")
    controls = _barrier_controls()
    before = dict(_ATTEMPTS)
    vectors = []
    for sample, salt, n, r, p, expected in _VECTORS:
        _require(len(expected) == 128, "RFC fixture encoding is invalid.")
        started = time.perf_counter()
        derived = hashlib.scrypt(sample, salt=salt, n=n, r=r, p=p, dklen=64, maxmem=_MAXMEM)
        _require(derived.hex() == expected, "RFC 7914 scrypt test vector differs.")
        vectors.append({"n": n, "r": r, "p": p, "dklen": 64,
                        "elapsed_seconds": time.perf_counter() - started})

    sample = b"production-readiness-synthetic-only"
    salt = bytes(range(32))
    repetitions = []
    result = None
    for _ in range(3):
        started = time.perf_counter()
        current = hashlib.scrypt(sample, salt=salt, **_PROFILE)
        _require(len(current) == 32, "Candidate derived length differs.")
        if result is not None:
            _require(current == result, "Candidate derivation is not repeatable.")
        result = current
        repetitions.append(time.perf_counter() - started)

    variants = ((sample + b"-other", salt),
                (sample, bytes([salt[0] ^ 1]) + salt[1:]),
                (sample, salt[:-1] + bytes([salt[-1] ^ 1])))
    variant_results = [hashlib.scrypt(item, salt=variant_salt, **_PROFILE)
                       for item, variant_salt in variants]
    _require(len(set([result, *variant_results])) == 4, "Synthetic key/salt distinction control failed.")
    try:
        hashlib.scrypt(sample, salt=salt, n=131072, r=8, p=1, dklen=32, maxmem=1024 * 1024)
    except ValueError:
        memory_rejection = True
    else:
        raise QualificationError("Backend accepted a candidate with an insufficient memory cap.")

    if result is None:
        raise QualificationError("Candidate produced no result.")
    attempts = {key: _ATTEMPTS[key] - before[key] for key in _ATTEMPTS}
    _require(all(value == 0 for value in attempts.values()), "Derivation attempted a forbidden runtime operation.")
    return {
        "schema_version": 1,
        "purpose": "synthetic candidate backend qualification; no ledger or credential operation",
        "python": sys.version.split()[0], "openssl": ssl.OPENSSL_VERSION,
        "platform": sys.platform, "frozen": bool(getattr(sys, "frozen", False)),
        "candidate_profile": dict(_PROFILE), "candidate_sample_hex": result.hex(),
        "candidate_repetition_seconds": repetitions,
        "rfc_vectors_completed": vectors,
        "rfc_n1048576_vector": "not run; outside this probe's memory bound",
        "synthetic_distinction_controls": 3, "insufficient_maxmem_rejected": memory_rejection,
        "audit_barrier_synthetic_controls": controls, "backend_import_attempts": initial_attempts,
        "derivation_forbidden_attempts": attempts, "ok": True,
        "production_binding_migrated": False, "production_capacity_approved": False,
    }


def main() -> int:
    if len(sys.argv) != 1:
        print("This synthetic probe accepts no arguments or credential input.", file=sys.stderr)
        return 2
    try:
        report = qualify()
    except QualificationError as exc:
        print(json.dumps({"ok": False, "error": str(exc)}, sort_keys=True))
        return 1
    print(json.dumps(report, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
