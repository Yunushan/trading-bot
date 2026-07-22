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
    from rust_command import run_cargo_with_secure_wsl_fallback
except ModuleNotFoundError:  # pragma: no cover - exercised by package imports
    from tools.rust_command import run_cargo_with_secure_wsl_fallback

try:
    from audit_native_source_sync import audit_native_source_sync
    from check_generated_evidence_source_control import generated_evidence_write_guard
    from check_rust_native_runtime_evidence import (
        DEFAULT_MANIFEST_PATH,
        PROMOTION_SOURCE_TREE_IGNORED_PATHS,
        _current_source_tree_clean,
        _current_source_tree_dirty_paths,
        _current_source_tree_untracked_paths,
        validate,
    )
except ModuleNotFoundError:  # pragma: no cover - exercised when imported as tools.*
    from tools.audit_native_source_sync import audit_native_source_sync
    from tools.check_generated_evidence_source_control import generated_evidence_write_guard
    from tools.check_rust_native_runtime_evidence import (
        DEFAULT_MANIFEST_PATH,
        PROMOTION_SOURCE_TREE_IGNORED_PATHS,
        _current_source_tree_clean,
        _current_source_tree_dirty_paths,
        _current_source_tree_untracked_paths,
        validate,
    )


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
    root = _repo_root()
    target_paths = [evidence_dir / filename for filename in RECOVERY_EVIDENCE_FILENAMES]
    write_guard = generated_evidence_write_guard(
        target_paths,
        root=root,
        require_generated_destinations=True,
    )
    tracked_targets = list(write_guard.get("tracked_generated_evidence_write_targets") or [])
    return {
        "ok": bool(write_guard.get("ok")),
        "generated_evidence_write_targets": list(write_guard.get("generated_evidence_write_targets") or []),
        "non_generated_in_repo_write_targets": list(write_guard.get("non_generated_in_repo_write_targets") or []),
        "tracked_generated_evidence_targets": tracked_targets,
        "issues": [str(issue) for issue in write_guard.get("issues", [])],
    }


def local_recovery_generation_guard(evidence_dir: Path) -> dict[str, Any]:
    if not evidence_dir.is_absolute():
        evidence_dir = (_repo_root() / evidence_dir).resolve()
    return _source_control_generation_guard(evidence_dir)


def _promotion_source_guard() -> dict[str, Any]:
    source_tree_clean = _current_source_tree_clean()
    dirty_paths = _current_source_tree_dirty_paths() or []
    untracked_paths = _current_source_tree_untracked_paths() or []
    issues: list[str] = []
    if source_tree_clean is None:
        issues.append("could not check current source tree cleanliness before local recovery promotion evidence")
    elif not source_tree_clean:
        issues.append(
            "source tree must be clean before generating Rust native deterministic local recovery promotion evidence"
        )
        if dirty_paths:
            visible = ", ".join(dirty_paths[:10])
            suffix = "" if len(dirty_paths) <= 10 else ", ..."
            issues.append(f"dirty paths: {visible}{suffix}")
        if untracked_paths:
            visible = ", ".join(untracked_paths[:10])
            suffix = "" if len(untracked_paths) <= 10 else ", ..."
            issues.append(f"untracked paths: {visible}{suffix}")
    return {
        "ok": not issues,
        "source_tree_clean": source_tree_clean,
        "dirty_paths": dirty_paths,
        "untracked_paths": untracked_paths,
        "ignored_paths": list(PROMOTION_SOURCE_TREE_IGNORED_PATHS),
        "issues": issues,
    }


def _native_source_sync_not_required() -> dict[str, Any]:
    return {
        "required": False,
        "ok": True,
        "audit_command": "python tools/audit_native_source_sync.py --json",
        "contract_hash": "",
        "surface_contract_ok": None,
        "generated_artifact_count": 0,
        "consumer_surface_count": 0,
        "issues": [],
    }


def _native_source_sync_guard() -> dict[str, Any]:
    try:
        audit = audit_native_source_sync()
    except (OSError, UnicodeDecodeError) as exc:  # pragma: no cover - defensive CLI boundary
        return {
            "required": True,
            "ok": False,
            "audit_command": "python tools/audit_native_source_sync.py --json",
            "contract_hash": "",
            "surface_contract_ok": False,
            "generated_artifact_count": 0,
            "consumer_surface_count": 0,
            "issues": [f"native source sync audit failed before local recovery evidence generation: {exc}"],
        }

    surface_contract = audit.get("surface_contract")
    surface_contract_ok = bool(isinstance(surface_contract, dict) and surface_contract.get("ok") is True)
    issues = [str(issue) for issue in audit.get("issues", [])]
    if audit.get("ok") is not True and not issues:
        issues.append("native source sync audit failed before local recovery evidence generation")
    if not isinstance(surface_contract, dict):
        issues.append("native source sync audit must include surface_contract before local recovery evidence generation")
    elif surface_contract.get("ok") is not True:
        issues.extend(
            f"native source sync surface contract issue before local recovery evidence generation: {issue}"
            for issue in surface_contract.get("issues", [])
        )

    return {
        "required": True,
        "ok": not issues,
        "audit_command": "python tools/audit_native_source_sync.py --json",
        "contract_hash": str(audit.get("contract_hash") or ""),
        "surface_contract_ok": surface_contract_ok,
        "generated_artifact_count": len(audit.get("generated", []) or []),
        "consumer_surface_count": len(audit.get("consumers", []) or []),
        "issues": issues,
    }


def _run_recovery_evidence_command(evidence_dir: Path, *, timeout: int) -> dict[str, Any]:
    cargo = shutil.which("cargo")
    if not cargo:
        return {
            "ok": False,
            "returncode": None,
            "command": "cargo run --locked -p trading-bot-rust -- --write-local-recovery-evidence",
            "stdout_tail": "",
            "stderr_tail": "cargo was not found on PATH",
        }

    command = [cargo, "run", "--locked", "-p", "trading-bot-rust", "--", "--write-local-recovery-evidence"]
    env = os.environ.copy()
    env["RUST_NATIVE_RUNTIME_EVIDENCE_DIR"] = str(evidence_dir)
    try:
        result, execution_environment = run_cargo_with_secure_wsl_fallback(
            command,
            cwd=_rust_workspace(),
            env=env,
            timeout=timeout,
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
        "execution_environment": execution_environment,
        "stdout_tail": _tail(result.stdout),
        "stderr_tail": _tail(result.stderr),
    }


def check_local_recovery_evidence(
    *,
    manifest_path: Path,
    evidence_dir: Path,
    validate_only: bool,
    timeout: int,
    require_clean_source: bool = False,
    require_native_source_sync: bool = False,
) -> dict[str, Any]:
    if not evidence_dir.is_absolute():
        evidence_dir = (_repo_root() / evidence_dir).resolve()
    promotion_source_guard = _promotion_source_guard() if require_clean_source else {
        "ok": True,
        "source_tree_clean": None,
        "dirty_paths": [],
        "untracked_paths": [],
        "ignored_paths": list(PROMOTION_SOURCE_TREE_IGNORED_PATHS),
        "issues": [],
    }
    native_source_sync_guard = (
        _native_source_sync_guard() if require_native_source_sync else _native_source_sync_not_required()
    )
    pre_run_issues: list[str] = []
    if require_clean_source and not promotion_source_guard["ok"]:
        pre_run_issues.extend(str(issue) for issue in promotion_source_guard["issues"])
    if require_native_source_sync and not native_source_sync_guard["ok"]:
        pre_run_issues.extend(str(issue) for issue in native_source_sync_guard["issues"])
    if pre_run_issues:
        return {
            "ok": False,
            "evidence_dir": str(evidence_dir),
            "validate_only": validate_only,
            "require_clean_source": require_clean_source,
            "require_native_source_sync": require_native_source_sync,
            "recovery_evidence_ids": sorted(RECOVERY_EVIDENCE_IDS),
            "command": {
                "ok": False,
                "returncode": None,
                "command": "blocked-before-run",
                "stdout_tail": "",
                "stderr_tail": "",
            },
            "source_control_guard": {},
            "promotion_source_guard": promotion_source_guard,
            "native_source_sync_guard": native_source_sync_guard,
            "validation": {},
            "issues": pre_run_issues,
        }
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
                "require_clean_source": require_clean_source,
                "require_native_source_sync": require_native_source_sync,
                "recovery_evidence_ids": sorted(RECOVERY_EVIDENCE_IDS),
                "command": {
                    "ok": False,
                    "returncode": None,
                    "command": "blocked-before-run",
                    "stdout_tail": "",
                    "stderr_tail": "",
                },
                "source_control_guard": source_control_guard,
                "promotion_source_guard": promotion_source_guard,
                "native_source_sync_guard": native_source_sync_guard,
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
        require_current_commit=require_clean_source,
        require_clean_source=require_clean_source,
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
        "require_clean_source": require_clean_source,
        "require_native_source_sync": require_native_source_sync,
        "recovery_evidence_ids": sorted(RECOVERY_EVIDENCE_IDS),
        "command": command_result,
        "source_control_guard": source_control_guard,
        "promotion_source_guard": promotion_source_guard,
        "native_source_sync_guard": native_source_sync_guard,
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
            require_clean_source=bool(args.require_clean_source),
            require_native_source_sync=bool(args.require_native_source_sync),
        )
    if args.validate_only:
        default_dir = _repo_root() / "artifacts" / "rust-native-runtime-evidence"
        return check_local_recovery_evidence(
            manifest_path=manifest_path,
            evidence_dir=default_dir,
            validate_only=True,
            timeout=int(args.timeout),
            require_clean_source=bool(args.require_clean_source),
            require_native_source_sync=bool(args.require_native_source_sync),
        )
    with tempfile.TemporaryDirectory(prefix="trading-bot-rust-recovery-") as temp_dir:
        return check_local_recovery_evidence(
            manifest_path=manifest_path,
            evidence_dir=Path(temp_dir),
            validate_only=False,
            timeout=int(args.timeout),
            require_clean_source=bool(args.require_clean_source),
            require_native_source_sync=bool(args.require_native_source_sync),
        )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest", default=str(DEFAULT_MANIFEST_PATH), help="Rust runtime evidence manifest path.")
    parser.add_argument("--evidence-dir", help="Directory to write or validate recovery evidence artifacts.")
    parser.add_argument("--validate-only", action="store_true", help="Validate existing recovery evidence without running cargo.")
    parser.add_argument(
        "--require-clean-source",
        action="store_true",
        help="Require the current checkout and generated artifacts to satisfy promotion clean-source rules.",
    )
    parser.add_argument(
        "--require-native-source-sync",
        action="store_true",
        help="Require the current Python-owned C++/Rust/Tauri native source-sync audit before local recovery evidence.",
    )
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
