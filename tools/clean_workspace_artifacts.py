from __future__ import annotations

import argparse
import json
import os
import shutil
import stat
import subprocess
import sys
from pathlib import Path

# Cleanup must not recreate the bytecode directories it is removing.
sys.dont_write_bytecode = True

from audit_workspace_hygiene import is_noisy_ignored_path  # noqa: E402
from check_rust_native_runtime_evidence import (  # noqa: E402
    REQUIRED_REQUIREMENTS,
    _current_git_commit,
    native_python_source_contract_hash,
)
from check_operational_readiness import (  # noqa: E402
    DEFAULT_POLICY_PATH as OPERATIONAL_READINESS_POLICY_PATH,
    _current_commit as _current_operational_readiness_commit,
    _source_tree_clean as _current_operational_readiness_source_tree_clean,
    load_policy as _load_operational_readiness_policy,
    policy_sha256 as _operational_readiness_policy_sha256,
)


EXPLICIT_GENERATED_ARTIFACT_GLOBS = (
    "artifacts/native-source-sync/*.json",
    # `gh run download` stores Rust runtime bundles below this generated root;
    # the importer expects canonical evidence files directly in the parent.
    "artifacts/rust-native-runtime-evidence/downloads",
    "artifacts/rust-native-runtime-evidence/rust-native-runtime-evidence-plan.md",
    "artifacts/rust-native-runtime-evidence-plan.md",
    # `gh run download --pattern release-platform-evidence-*` nests each
    # artifact below this generated root.  The canonical evidence importer
    # expects flattened JSON files, so the downloader directories are always
    # disposable generated workspace state.
    "release-platform-evidence/release-platform-evidence-*",
)
STALE_RUNTIME_EVIDENCE_GLOBS = (
    "artifacts/rust-native-runtime-evidence/*.json",
)
STALE_RELEASE_PLATFORM_EVIDENCE_GLOBS = (
    "release-platform-evidence/*.json",
)
STALE_OPERATIONAL_READINESS_EVIDENCE_GLOBS = (
    "artifacts/operational-readiness/*.json",
)


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[1]


def _git_lines(*args: str) -> list[str]:
    result = subprocess.run(
        ["git", *args],
        cwd=_repo_root(),
        check=True,
        capture_output=True,
        text=True,
    )
    return [line.strip() for line in result.stdout.splitlines() if line.strip()]


def _ignored_paths() -> list[str]:
    rows = _git_lines("status", "--ignored", "--short")
    return [row[3:] for row in rows if row.startswith("!! ")]


def _is_noisy_artifact(path: str) -> bool:
    return is_noisy_ignored_path(path)


def _normalize_repo_path(path: str) -> str:
    return path.replace("\\", "/").strip()


def _explicit_generated_artifacts(root: Path) -> list[str]:
    paths: list[str] = []
    for pattern in EXPLICIT_GENERATED_ARTIFACT_GLOBS:
        for target in root.glob(pattern):
            if not target.exists():
                continue
            try:
                relative = target.relative_to(root)
            except ValueError:
                continue
            path = relative.as_posix()
            paths.append(path)
    return sorted(paths)


def _current_runtime_evidence_binding() -> tuple[str, str]:
    try:
        current_commit = _current_git_commit() or ""
        current_hash = native_python_source_contract_hash()
    except (OSError, RuntimeError, ValueError, subprocess.SubprocessError):
        return "", ""
    return current_commit.strip(), current_hash.strip().lower()


def _json_payload(path: Path) -> dict[str, object] | None:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    return payload if isinstance(payload, dict) else None


def _stale_runtime_evidence_artifacts(root: Path) -> list[str]:
    current_commit, current_hash = _current_runtime_evidence_binding()
    if not current_commit or not current_hash:
        return []

    paths: list[str] = []
    for pattern in STALE_RUNTIME_EVIDENCE_GLOBS:
        for target in root.glob(pattern):
            if not target.is_file():
                continue
            payload = _json_payload(target)
            if payload is None:
                continue
            evidence_id = str(payload.get("evidence_id") or "").strip()
            if evidence_id not in REQUIRED_REQUIREMENTS:
                continue
            artifact_commit = str(payload.get("commit") or "").strip()
            artifact_hash = str(payload.get("python_source_contract_hash") or "").strip().lower()
            if artifact_commit == current_commit and artifact_hash == current_hash:
                continue
            try:
                paths.append(target.relative_to(root).as_posix())
            except ValueError:
                continue
    return sorted(paths)


def _stale_release_platform_evidence_artifacts(root: Path) -> list[str]:
    current_commit, current_hash = _current_runtime_evidence_binding()
    if not current_commit or not current_hash:
        return []

    paths: list[str] = []
    for pattern in STALE_RELEASE_PLATFORM_EVIDENCE_GLOBS:
        for target in root.glob(pattern):
            if not target.is_file():
                continue
            payload = _json_payload(target)
            if payload is None:
                continue
            artifact_commit = str(payload.get("commit") or "").strip()
            artifact_hash = str(payload.get("python_source_contract_hash") or "").strip().lower()
            native_source_sync = payload.get("native_source_sync")
            native_hash = ""
            if isinstance(native_source_sync, dict):
                native_hash = str(native_source_sync.get("contract_hash") or "").strip().lower()
            source_bound_to_current = (
                artifact_commit == current_commit
                and artifact_hash == current_hash
                and native_hash == current_hash
                and payload.get("source_tree_clean") is True
                and payload.get("runtime_ready_claimed") is False
            )
            if source_bound_to_current:
                continue
            try:
                paths.append(target.relative_to(root).as_posix())
            except ValueError:
                continue
    return sorted(paths)


def _operational_readiness_required_filenames(root: Path) -> set[str]:
    policy_path = OPERATIONAL_READINESS_POLICY_PATH
    if not policy_path.is_absolute():
        policy_path = root / policy_path
    try:
        policy = _load_operational_readiness_policy(policy_path)
    except ValueError:
        return set()

    requirements = policy.get("required_evidence")
    if not isinstance(requirements, list):
        return set()
    return {
        str(item.get("filename") or "").strip()
        for item in requirements
        if isinstance(item, dict)
        and item.get("required_for_production") is True
        and str(item.get("filename") or "").strip()
    }


def _current_operational_readiness_binding(root: Path) -> tuple[str, str, bool | None]:
    policy_path = OPERATIONAL_READINESS_POLICY_PATH
    if not policy_path.is_absolute():
        policy_path = root / policy_path
    try:
        policy = _load_operational_readiness_policy(policy_path)
        return (
            _current_operational_readiness_commit(root).strip(),
            _operational_readiness_policy_sha256(policy).strip().lower(),
            _current_operational_readiness_source_tree_clean(root),
        )
    except (OSError, RuntimeError, ValueError, subprocess.SubprocessError):
        return "", "", None


def _stale_operational_readiness_evidence_artifacts(root: Path) -> list[str]:
    required_filenames = _operational_readiness_required_filenames(root)
    current_commit, current_hash, current_source_clean = _current_operational_readiness_binding(root)
    if not required_filenames or not current_commit or not current_hash:
        return []

    paths: list[str] = []
    for pattern in STALE_OPERATIONAL_READINESS_EVIDENCE_GLOBS:
        for target in root.glob(pattern):
            if not target.is_file() or target.name not in required_filenames:
                continue
            payload = _json_payload(target)
            source_bound_to_current = bool(
                isinstance(payload, dict)
                and payload.get("status") == "pass"
                and payload.get("promotion_eligible") is True
                and payload.get("source_tree_clean") is True
                and str(payload.get("commit") or "").strip() == current_commit
                and str(payload.get("policy_sha256") or "").strip().lower() == current_hash
                and current_source_clean is True
            )
            if source_bound_to_current:
                continue
            try:
                paths.append(target.relative_to(root).as_posix())
            except ValueError:
                continue
    return sorted(paths)


def _cleanup_plan(root: Path, *, include_stale_runtime_evidence: bool = False) -> list[str]:
    planned: list[str] = []
    seen: set[str] = set()
    explicit_artifacts = list(_explicit_generated_artifacts(root))
    explicit_artifact_set = set(explicit_artifacts)
    stale_runtime_artifacts: list[str] = []
    if include_stale_runtime_evidence:
        stale_runtime_artifacts = _stale_runtime_evidence_artifacts(root)
        stale_runtime_artifacts.extend(_stale_release_platform_evidence_artifacts(root))
        stale_runtime_artifacts.extend(_stale_operational_readiness_evidence_artifacts(root))
        explicit_artifacts.extend(stale_runtime_artifacts)
    stale_runtime_artifact_set = set(stale_runtime_artifacts)
    for path in [*_ignored_paths(), *explicit_artifacts]:
        normalized = _normalize_repo_path(path)
        if normalized in seen:
            continue
        if (
            normalized not in explicit_artifact_set
            and normalized not in stale_runtime_artifact_set
            and not _is_noisy_artifact(normalized)
        ):
            continue
        seen.add(normalized)
        planned.append(normalized)
    return planned


def _is_inside_repo(path: Path, root: Path) -> bool:
    try:
        path.resolve().relative_to(root.resolve())
    except ValueError:
        return False
    return True


def _make_writable_and_retry(function, path: str, _exc_info) -> None:
    try:
        os.chmod(path, stat.S_IWRITE | stat.S_IREAD)
    except FileNotFoundError:
        return
    try:
        function(path)
    except FileNotFoundError:
        return


def clean_workspace_artifacts(*, apply: bool = False, include_stale_runtime_evidence: bool = False) -> dict[str, object]:
    root = _repo_root()
    planned = _cleanup_plan(root, include_stale_runtime_evidence=include_stale_runtime_evidence)
    removed: list[str] = []
    skipped: list[dict[str, str]] = []

    if not apply:
        return {
            "applied": False,
            "include_stale_runtime_evidence": bool(include_stale_runtime_evidence),
            "include_stale_promotion_evidence": bool(include_stale_runtime_evidence),
            "planned_count": len(planned),
            "planned": planned,
            "removed_count": 0,
            "removed": removed,
            "skipped": skipped,
        }

    for path in planned:
        target = root / path
        if not _is_inside_repo(target, root):
            skipped.append({"path": path, "reason": "outside repository"})
            continue
        if not target.exists():
            skipped.append({"path": path, "reason": "does not exist"})
            continue
        try:
            if target.is_dir() and not target.is_symlink():
                shutil.rmtree(target, onerror=_make_writable_and_retry)
            else:
                os.chmod(target, stat.S_IWRITE | stat.S_IREAD)
                target.unlink()
        except FileNotFoundError:
            skipped.append({"path": path, "reason": "already removed"})
            continue
        removed.append(path)

    return {
        "applied": True,
        "include_stale_runtime_evidence": bool(include_stale_runtime_evidence),
        "include_stale_promotion_evidence": bool(include_stale_runtime_evidence),
        "planned_count": len(planned),
        "planned": planned,
        "removed_count": len(removed),
        "removed": removed,
        "skipped": skipped,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Safely remove ignored generated artifacts reported by the workspace hygiene audit."
    )
    parser.add_argument("--apply", action="store_true", help="Delete the planned ignored generated artifacts.")
    parser.add_argument(
        "--stale-runtime-evidence",
        "--stale-promotion-evidence",
        action="store_true",
        dest="stale_runtime_evidence",
        help=(
            "Also delete ignored Rust and operational-readiness promotion evidence JSON that "
            "does not match the current source binding."
        ),
    )
    parser.add_argument("--json", action="store_true", help="Print the cleanup plan/result as JSON.")
    args = parser.parse_args(argv)

    summary = clean_workspace_artifacts(
        apply=args.apply,
        include_stale_runtime_evidence=args.stale_runtime_evidence,
    )
    if args.json:
        print(json.dumps(summary, indent=2, sort_keys=True))
        return 0

    action = "Removed" if args.apply else "Would remove"
    print(f"{action} {summary['planned_count']} ignored generated artifact(s):")
    for path in summary["planned"]:
        print(f"  - {path}")
    if not args.apply:
        print("Run with --apply to delete these paths.")
    if summary["skipped"]:
        print("Skipped:")
        for item in summary["skipped"]:
            print(f"  - {item['path']}: {item['reason']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
