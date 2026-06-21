#!/usr/bin/env python3
"""Generate and validate deterministic Rust native runtime recovery evidence."""

from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import tempfile
from pathlib import Path
from typing import Any

try:
    from check_rust_native_runtime_evidence import DEFAULT_MANIFEST_PATH, validate
except ModuleNotFoundError:  # pragma: no cover - exercised when imported as tools.*
    from tools.check_rust_native_runtime_evidence import DEFAULT_MANIFEST_PATH, validate


RECOVERY_EVIDENCE_IDS = {
    "rust-native-live-stream-recovery",
    "rust-native-order-guard-recovery",
}
RECOVERY_EVIDENCE_FILENAMES = tuple(f"{evidence_id}.json" for evidence_id in sorted(RECOVERY_EVIDENCE_IDS))


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[1]


def _rust_workspace() -> Path:
    return _repo_root() / "experiments" / "rust-shells"


def _tail(text: str, max_chars: int = 4000) -> str:
    text = text.strip()
    if len(text) <= max_chars:
        return text
    return text[-max_chars:]


def _repo_relative(path: Path, *, root: Path) -> str:
    try:
        return path.resolve().relative_to(root.resolve()).as_posix()
    except ValueError:
        return ""


def _tracked_git_files(paths: list[str], *, root: Path) -> list[str]:
    if not paths:
        return []
    try:
        result = subprocess.run(
            ["git", "ls-files", "--", *paths],
            cwd=root,
            capture_output=True,
            text=True,
            check=False,
        )
    except OSError:
        return []
    if result.returncode != 0:
        return []
    return [line.strip().replace("\\", "/") for line in result.stdout.splitlines() if line.strip()]


def _tracked_recovery_evidence_targets(
    evidence_dir: Path,
    *,
    root: Path | None = None,
    tracked_files: list[str] | None = None,
) -> list[str]:
    root = root or _repo_root()
    target_paths = [evidence_dir / filename for filename in RECOVERY_EVIDENCE_FILENAMES]
    relative_targets = [relative for path in target_paths if (relative := _repo_relative(path, root=root))]
    if tracked_files is None:
        tracked_files = _tracked_git_files(relative_targets, root=root)
    tracked = {path.replace("\\", "/") for path in tracked_files}
    return [relative for relative in relative_targets if relative in tracked]


def _source_control_generation_guard(evidence_dir: Path) -> dict[str, Any]:
    tracked_targets = _tracked_recovery_evidence_targets(evidence_dir)
    issues = []
    if tracked_targets:
        joined = ", ".join(tracked_targets)
        issues.append(
            "refusing to write local Rust recovery evidence over tracked generated evidence "
            f"artifact path(s): {joined}. Commit the removal of generated evidence artifacts "
            "first, then regenerate/import evidence from a clean candidate source commit."
        )
    return {
        "ok": not issues,
        "tracked_generated_evidence_targets": tracked_targets,
        "issues": issues,
    }


def local_recovery_generation_guard(evidence_dir: Path) -> dict[str, Any]:
    if not evidence_dir.is_absolute():
        evidence_dir = (_repo_root() / evidence_dir).resolve()
    return _source_control_generation_guard(evidence_dir)


def _run_recovery_evidence_command(evidence_dir: Path, *, timeout: int) -> dict[str, Any]:
    cargo = shutil.which("cargo")
    if not cargo:
        return {
            "ok": False,
            "returncode": None,
            "command": "cargo run -p trading-bot-rust -- --write-local-recovery-evidence",
            "stdout_tail": "",
            "stderr_tail": "cargo was not found on PATH",
        }

    command = [cargo, "run", "-p", "trading-bot-rust", "--", "--write-local-recovery-evidence"]
    env = os.environ.copy()
    env["RUST_NATIVE_RUNTIME_EVIDENCE_DIR"] = str(evidence_dir)
    try:
        result = subprocess.run(
            command,
            cwd=_rust_workspace(),
            env=env,
            capture_output=True,
            text=True,
            timeout=timeout,
            check=False,
        )
    except subprocess.TimeoutExpired as exc:
        return {
            "ok": False,
            "returncode": None,
            "command": " ".join(command),
            "stdout_tail": _tail(exc.stdout or ""),
            "stderr_tail": _tail((exc.stderr or "") + f"\nTimed out after {timeout} seconds."),
        }
    return {
        "ok": result.returncode == 0,
        "returncode": result.returncode,
        "command": " ".join(command),
        "stdout_tail": _tail(result.stdout),
        "stderr_tail": _tail(result.stderr),
    }


def check_local_recovery_evidence(
    *,
    manifest_path: Path,
    evidence_dir: Path,
    validate_only: bool,
    timeout: int,
) -> dict[str, Any]:
    if not evidence_dir.is_absolute():
        evidence_dir = (_repo_root() / evidence_dir).resolve()
    command_result = {
        "ok": True,
        "returncode": 0,
        "command": "validate-only",
        "stdout_tail": "",
        "stderr_tail": "",
    }
    if not validate_only:
        source_control_guard = local_recovery_generation_guard(evidence_dir)
        if not source_control_guard["ok"]:
            return {
                "ok": False,
                "evidence_dir": str(evidence_dir),
                "validate_only": validate_only,
                "recovery_evidence_ids": sorted(RECOVERY_EVIDENCE_IDS),
                "command": {
                    "ok": False,
                    "returncode": None,
                    "command": "blocked-before-run",
                    "stdout_tail": "",
                    "stderr_tail": "",
                },
                "source_control_guard": source_control_guard,
                "validation": {},
                "issues": list(source_control_guard["issues"]),
            }
        evidence_dir.mkdir(parents=True, exist_ok=True)
        command_result = _run_recovery_evidence_command(evidence_dir, timeout=timeout)
    else:
        source_control_guard = {"ok": True, "tracked_generated_evidence_targets": [], "issues": []}

    validation = validate(
        manifest_path,
        require_evidence=True,
        evidence_dir_override=evidence_dir,
        requirement_ids=RECOVERY_EVIDENCE_IDS,
    )
    issues = []
    if not command_result["ok"]:
        issues.append("local recovery evidence command failed")
    issues.extend(str(issue) for issue in validation.get("issues", []))
    return {
        "ok": not issues,
        "evidence_dir": str(evidence_dir),
        "validate_only": validate_only,
        "recovery_evidence_ids": sorted(RECOVERY_EVIDENCE_IDS),
        "command": command_result,
        "source_control_guard": source_control_guard,
        "validation": validation,
        "issues": issues,
    }


def _run_with_managed_evidence_dir(args: argparse.Namespace) -> dict[str, Any]:
    manifest_path = Path(args.manifest)
    if args.evidence_dir:
        return check_local_recovery_evidence(
            manifest_path=manifest_path,
            evidence_dir=Path(args.evidence_dir),
            validate_only=bool(args.validate_only),
            timeout=int(args.timeout),
        )
    if args.validate_only:
        default_dir = _repo_root() / "artifacts" / "rust-native-runtime-evidence"
        return check_local_recovery_evidence(
            manifest_path=manifest_path,
            evidence_dir=default_dir,
            validate_only=True,
            timeout=int(args.timeout),
        )
    with tempfile.TemporaryDirectory(prefix="trading-bot-rust-recovery-") as temp_dir:
        return check_local_recovery_evidence(
            manifest_path=manifest_path,
            evidence_dir=Path(temp_dir),
            validate_only=False,
            timeout=int(args.timeout),
        )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest", default=str(DEFAULT_MANIFEST_PATH), help="Rust runtime evidence manifest path.")
    parser.add_argument("--evidence-dir", help="Directory to write or validate recovery evidence artifacts.")
    parser.add_argument("--validate-only", action="store_true", help="Validate existing recovery evidence without running cargo.")
    parser.add_argument("--timeout", type=int, default=240, help="Maximum seconds for the Rust recovery evidence command.")
    parser.add_argument("--json", action="store_true", help="Print machine-readable JSON.")
    args = parser.parse_args(argv)

    result = _run_with_managed_evidence_dir(args)
    if args.json:
        print(json.dumps(result, indent=2, sort_keys=True))
    elif result["ok"]:
        print(f"Rust native local recovery evidence ok: {result['evidence_dir']}")
    else:
        print("Rust native local recovery evidence failed:")
        for issue in result["issues"]:
            print(f"- {issue}")
    return 0 if result["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
