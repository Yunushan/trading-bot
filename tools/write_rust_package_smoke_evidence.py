#!/usr/bin/env python3
"""Run packaged Rust binaries and write source-bound smoke evidence."""

from __future__ import annotations

import argparse
import hashlib
import json
import platform
import subprocess
import sys
import time
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[1]
PYTHON_ROOT = REPO_ROOT / "Languages" / "Python"
if str(PYTHON_ROOT) not in sys.path:
    sys.path.insert(0, str(PYTHON_ROOT))

try:
    from audit_native_source_sync import audit_native_source_sync
except ModuleNotFoundError:  # pragma: no cover - exercised when imported as tools.*
    from tools.audit_native_source_sync import audit_native_source_sync

from app.native_parity import (  # noqa: E402
    RUST_STANDALONE_RUNTIME_READY,
    native_python_source_contract_hash,
)


EVIDENCE_SCHEMA = "trading-bot.rust-package-smoke.v1"
SMOKE_MARKERS = {
    "rust_cli": "Trading Bot Rust packaged smoke passed",
    "tauri_desktop": "Trading Bot Tauri packaged smoke passed",
}


class EvidenceError(RuntimeError):
    """Raised when packaged-binary evidence cannot be trusted."""


def _repo_path(path: Path) -> Path:
    return path if path.is_absolute() else REPO_ROOT / path


def _normalize_architecture(value: str) -> str:
    normalized = value.strip().lower().replace("-", "_")
    if normalized in {"amd64", "x86_64", "x64"}:
        return "x64"
    if normalized in {"aarch64", "arm64"}:
        return "arm64"
    if normalized in {"i386", "i686", "x86"}:
        return "x86"
    return normalized or "unknown"


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as file:
        for chunk in iter(lambda: file.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _current_git_commit() -> str:
    try:
        completed = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            cwd=REPO_ROOT,
            check=True,
            capture_output=True,
            text=True,
            timeout=10,
        )
    except (OSError, subprocess.SubprocessError):
        return "unknown-local-commit"
    return completed.stdout.strip() or "unknown-local-commit"


def _source_tree_clean() -> bool:
    try:
        completed = subprocess.run(
            [
                "git",
                "status",
                "--porcelain",
                "--untracked-files=all",
                "--",
                ".",
                ":(exclude)release",
            ],
            cwd=REPO_ROOT,
            check=True,
            capture_output=True,
            text=True,
            timeout=10,
        )
    except (OSError, subprocess.SubprocessError):
        return False
    return not completed.stdout.strip()


def _source_sync_evidence(contract_hash: str) -> dict[str, Any]:
    audit = audit_native_source_sync()
    surface = audit.get("surface_contract")
    surface_ok = isinstance(surface, dict) and surface.get("ok") is True
    audit_hash = str(audit.get("contract_hash") or "").strip().lower()
    issues = [str(issue) for issue in audit.get("issues", []) if str(issue).strip()]
    if not surface_ok:
        issues.append("native source-sync surface contract did not pass")
    if audit_hash != contract_hash.lower():
        issues.append(
            "native source-sync contract hash does not match the current Python source contract"
        )
    if audit.get("ok") is not True or issues:
        detail = "; ".join(issues) or "native source-sync audit failed"
        raise EvidenceError(detail)
    return {
        "status": "passed",
        "python_source_of_truth": "Languages/Python/app/native_parity.py",
        "contract_hash": audit_hash,
        "surface_contract_ok": surface_ok,
        "generated_artifact_count": len(audit.get("generated", []) or []),
        "consumer_surface_count": len(audit.get("consumers", []) or []),
    }


def _tail(value: str, limit: int = 4000) -> str:
    return value[-limit:]


def _run_packaged_smoke(
    *,
    role: str,
    binary: Path,
    contract_hash: str,
    runtime_ready: bool,
    timeout: float,
) -> dict[str, Any]:
    binary = _repo_path(binary).resolve()
    if role not in SMOKE_MARKERS:
        raise EvidenceError(f"unknown packaged Rust binary role: {role}")
    if not binary.is_file():
        raise EvidenceError(f"{role} executable does not exist: {binary}")

    command = [str(binary), "--smoke"]
    try:
        completed = subprocess.run(
            command,
            cwd=REPO_ROOT,
            capture_output=True,
            text=True,
            timeout=timeout,
        )
    except subprocess.TimeoutExpired as exc:
        raise EvidenceError(
            f"{role} smoke timed out after {timeout:g} seconds"
        ) from exc
    except OSError as exc:
        raise EvidenceError(f"{role} smoke could not start: {exc}") from exc

    stdout = completed.stdout or ""
    stderr = completed.stderr or ""
    if completed.returncode != 0:
        raise EvidenceError(
            f"{role} smoke exited with {completed.returncode}: {_tail(stderr or stdout).strip()}"
        )
    if stderr.strip():
        raise EvidenceError(f"{role} smoke wrote to stderr: {_tail(stderr).strip()}")

    required_markers = [SMOKE_MARKERS[role], f"contract {contract_hash}"]
    required_markers.append(
        "native trading ready" if runtime_ready else "native trading disabled"
    )
    missing_markers = [marker for marker in required_markers if marker not in stdout]
    if missing_markers:
        raise EvidenceError(
            f"{role} smoke output is missing marker(s): {', '.join(missing_markers)}"
        )

    return {
        "role": role,
        "status": "passed",
        "path": str(binary),
        "size_bytes": binary.stat().st_size,
        "sha256": _sha256_file(binary),
        "command": command,
        "exit_code": completed.returncode,
        "stdout_tail": _tail(stdout).strip(),
        "stderr_empty": True,
        "required_markers": required_markers,
    }


def build_evidence(
    *,
    rust_cli: Path,
    tauri_desktop: Path,
    source_revision: str,
    system: str,
    architecture: str,
    timeout: float,
    require_clean_source: bool,
) -> dict[str, Any]:
    contract_hash = native_python_source_contract_hash().lower()
    if len(contract_hash) != 64 or any(
        character not in "0123456789abcdef" for character in contract_hash
    ):
        raise EvidenceError(
            "current Python source contract hash is not a SHA-256 value"
        )

    source_clean = _source_tree_clean()
    if require_clean_source and not source_clean:
        raise EvidenceError(
            "source tree must be clean before release package evidence is written"
        )

    revision = source_revision.strip() or _current_git_commit()
    if not revision:
        raise EvidenceError("source revision must not be empty")

    source_sync = _source_sync_evidence(contract_hash)
    runtime_ready = bool(RUST_STANDALONE_RUNTIME_READY)
    binaries = [
        _run_packaged_smoke(
            role="rust_cli",
            binary=rust_cli,
            contract_hash=contract_hash,
            runtime_ready=runtime_ready,
            timeout=timeout,
        ),
        _run_packaged_smoke(
            role="tauri_desktop",
            binary=tauri_desktop,
            contract_hash=contract_hash,
            runtime_ready=runtime_ready,
            timeout=timeout,
        ),
    ]

    normalized_system = system.strip().lower() or platform.system().lower() or "unknown"
    normalized_architecture = _normalize_architecture(
        architecture or platform.machine()
    )
    return {
        "schema": EVIDENCE_SCHEMA,
        "evidence_id": f"rust-package-smoke-{normalized_system}-{normalized_architecture}",
        "status": "passed",
        "evidence_scope": "packaged_binary",
        "generated_at": f"unix:{int(time.time())}",
        "commit": revision,
        "source_revision": revision,
        "source_tree_clean": source_clean,
        "python_source_contract_hash": contract_hash,
        "native_source_sync": source_sync,
        "runtime_ready_claimed": runtime_ready,
        "platform": {
            "system": normalized_system,
            "architecture": normalized_architecture,
        },
        "secrets_redacted": True,
        "binaries": binaries,
        "suite_results": [
            {"name": f"{binary['role']}_packaged_smoke", "status": "passed"}
            for binary in binaries
        ],
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--rust-cli", required=True, help="Path to the packaged Rust CLI executable."
    )
    parser.add_argument(
        "--tauri-desktop",
        required=True,
        help="Path to the packaged Tauri desktop executable.",
    )
    parser.add_argument("--output", required=True, help="JSON evidence destination.")
    parser.add_argument(
        "--source-revision", default="", help="Source commit used for the binaries."
    )
    parser.add_argument(
        "--platform", default=platform.system(), help="Expected release platform."
    )
    parser.add_argument(
        "--architecture",
        default=platform.machine(),
        help="Expected release architecture.",
    )
    parser.add_argument(
        "--timeout", type=float, default=60.0, help="Per-binary smoke timeout."
    )
    parser.add_argument(
        "--require-clean-source",
        action="store_true",
        help="Refuse evidence when tracked or untracked source files are dirty.",
    )
    parser.add_argument("--json", action="store_true", help="Print the result as JSON.")
    args = parser.parse_args(argv)

    output_path = _repo_path(Path(args.output))
    try:
        evidence = build_evidence(
            rust_cli=Path(args.rust_cli),
            tauri_desktop=Path(args.tauri_desktop),
            source_revision=str(args.source_revision),
            system=str(args.platform),
            architecture=str(args.architecture),
            timeout=max(0.1, float(args.timeout)),
            require_clean_source=bool(args.require_clean_source),
        )
    except EvidenceError as exc:
        result = {"ok": False, "artifact": None, "issues": [str(exc)]}
        if args.json:
            print(json.dumps(result, indent=2, sort_keys=True))
        else:
            print(f"Rust package smoke evidence failed: {exc}", file=sys.stderr)
        return 1

    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(
        json.dumps(evidence, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    result = {"ok": True, "artifact": str(output_path), "issues": []}
    if args.json:
        print(json.dumps(result, indent=2, sort_keys=True))
    else:
        print(f"Rust package smoke evidence written to {output_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
