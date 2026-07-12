#!/usr/bin/env python3
"""Write Rust native runtime release/platform evidence from real release inputs."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import platform
import re
import subprocess
import sys
import time
from pathlib import Path
from typing import Any

try:
    from audit_native_source_sync import audit_native_source_sync
    from check_generated_evidence_source_control import generated_evidence_write_guard
    from release_browser_contract_commands import browser_contract_command_text
    from release_browser_contract_commands import browser_host_from_observed_platform
    from release_browser_contract_commands import builtin_browser_contract_targets_for_host
    from release_browser_contract_commands import has_builtin_browser_contract_command
    from check_release_assets import _build_expected_assets, _fetch_release, _resolve_default_repo
    from check_release_platform_matrix import DEFAULT_MATRIX_PATH, PROMOTION_SOURCE_TREE_IGNORED_PATHS
    from check_release_platform_matrix import REQUIRED_SUITE_RESULT_NAMES
    from check_release_platform_matrix import _evidence_issues, _load_json, _read_evidence
    from check_release_platform_matrix import _target_evidence_issues, _validate_matrix
except ModuleNotFoundError:  # pragma: no cover - exercised when imported as tools.*
    from tools.audit_native_source_sync import audit_native_source_sync
    from tools.check_generated_evidence_source_control import generated_evidence_write_guard
    from tools.release_browser_contract_commands import browser_contract_command_text
    from tools.release_browser_contract_commands import browser_host_from_observed_platform
    from tools.release_browser_contract_commands import builtin_browser_contract_targets_for_host
    from tools.release_browser_contract_commands import has_builtin_browser_contract_command
    from tools.check_release_assets import _build_expected_assets, _fetch_release, _resolve_default_repo
    from tools.check_release_platform_matrix import DEFAULT_MATRIX_PATH, PROMOTION_SOURCE_TREE_IGNORED_PATHS
    from tools.check_release_platform_matrix import REQUIRED_SUITE_RESULT_NAMES
    from tools.check_release_platform_matrix import _evidence_issues, _load_json, _read_evidence
    from tools.check_release_platform_matrix import _target_evidence_issues, _validate_matrix


DEFAULT_OUTPUT_DIR = Path("artifacts/rust-native-runtime-evidence")
EVIDENCE_ID = "rust-native-release-platform-evidence"
REPO_ROOT = Path(__file__).resolve().parents[1]
NATIVE_SOURCE_SYNC_AUDIT_ARTIFACT = "native-source-sync-audit"
NATIVE_SOURCE_SYNC_AUDIT_PATH = "artifacts/native-source-sync/native-source-sync-audit.json"
NATIVE_SOURCE_SYNC_SOURCE = "Languages/Python/app/native_parity.py"
DIRTY_SOURCE_RELEASE_EVIDENCE_ISSUE = (
    "source tree must be clean before writing Rust native release-platform evidence"
)
FAILED_SOURCE_SYNC_RELEASE_EVIDENCE_ISSUE = (
    "native source sync audit must pass before writing Rust native release-platform evidence"
)
PYTHON_ROOT = REPO_ROOT / "Languages" / "Python"
if str(PYTHON_ROOT) not in sys.path:
    sys.path.insert(0, str(PYTHON_ROOT))

from app.native_parity import native_python_source_contract_hash  # noqa: E402


def _repo_root() -> Path:
    return REPO_ROOT


def _repo_path(path: Path) -> Path:
    return path if path.is_absolute() else _repo_root() / path


def _current_git_commit() -> str:
    try:
        output = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            cwd=_repo_root(),
            check=True,
            capture_output=True,
            text=True,
            timeout=10,
        )
    except (OSError, subprocess.SubprocessError):
        return "unknown-local-commit"
    return output.stdout.strip() or "unknown-local-commit"


def _source_tree_status_command(untracked_files: str) -> list[str]:
    command = ["git", "status", "--porcelain", f"--untracked-files={untracked_files}", "--", "."]
    command.extend(f":(exclude){path}" for path in PROMOTION_SOURCE_TREE_IGNORED_PATHS)
    return command


def _source_tree_status_clean(untracked_files: str) -> bool:
    try:
        output = subprocess.run(
            _source_tree_status_command(untracked_files),
            cwd=_repo_root(),
            check=True,
            capture_output=True,
            text=True,
            timeout=10,
        )
    except (OSError, subprocess.SubprocessError):
        return False
    return not output.stdout.strip()


def _source_tree_clean() -> bool:
    return _source_tree_status_clean("no") and _source_tree_status_clean("all")


def _native_source_sync_binding() -> dict[str, Any]:
    return {
        "required": True,
        "audit_artifact": "native-source-sync-audit",
        "audit_path": "artifacts/native-source-sync/native-source-sync-audit.json",
        "python_source_of_truth": "Languages/Python/app/native_parity.py",
        "contract_hash": native_python_source_contract_hash(),
        "surface_contract_required": True,
    }


def _native_source_sync_guard() -> dict[str, Any]:
    audit = audit_native_source_sync()
    surface_contract = audit.get("surface_contract")
    surface_contract_ok = isinstance(surface_contract, dict) and surface_contract.get("ok") is True
    surface_contract_issues = (
        [str(issue) for issue in surface_contract.get("issues", []) if str(issue).strip()]
        if isinstance(surface_contract, dict)
        else ["native source sync surface_contract is missing"]
    )
    audit_issues = [str(issue) for issue in audit.get("issues", []) if str(issue).strip()]
    issues = [*audit_issues]
    if not surface_contract_ok:
        issues.extend(surface_contract_issues)
    return {
        "ok": bool(audit.get("ok")) and surface_contract_ok,
        "audit_artifact": "native-source-sync-audit",
        "audit_path": "artifacts/native-source-sync/native-source-sync-audit.json",
        "python_source_of_truth": "Languages/Python/app/native_parity.py",
        "contract_hash": audit.get("contract_hash"),
        "surface_contract_ok": surface_contract_ok,
        "generated_artifact_count": len(audit.get("generated", []) or []),
        "consumer_surface_count": len(audit.get("consumers", []) or []),
        "issues": issues,
    }


def _current_unix_timestamp_label() -> str:
    return f"unix:{int(time.time())}"


def _os_release() -> dict[str, str]:
    os_release = Path("/etc/os-release")
    if not os_release.is_file():
        return {}
    parsed: dict[str, str] = {}
    try:
        lines = os_release.read_text(encoding="utf-8", errors="replace").splitlines()
    except OSError:
        return {}
    for line in lines:
        if not line or line.lstrip().startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        parsed[key.strip()] = value.strip().strip('"')
    return parsed


def _normalize_architecture(value: str) -> str:
    normalized = value.strip().lower().replace("-", "_")
    if normalized in {"amd64", "x86_64", "x64"}:
        return "x64"
    if normalized in {"arm64", "aarch64"}:
        return "arm64"
    if normalized in {"x86", "i386", "i686"}:
        return "x86"
    if normalized.startswith("armv7") or normalized.startswith("armv6"):
        return "arm32"
    return normalized


def _observed_platform() -> dict[str, Any]:
    os_release = _os_release()
    return {
        "system": platform.system(),
        "release": platform.release(),
        "normalized_architecture": _normalize_architecture(platform.machine()),
        "os_release_id": os_release.get("ID", ""),
        "os_release_version_id": os_release.get("VERSION_ID", ""),
        "macos_version": platform.mac_ver()[0],
    }


def _local_browser_batch_plan(browser_targets: list[dict[str, Any]]) -> dict[str, Any]:
    host = browser_host_from_observed_platform(_observed_platform())
    targets = builtin_browser_contract_targets_for_host(browser_targets, host)
    target_ids = [str(target["id"]) for target in targets]
    validation_commands = [
        (
            "python tools/check_release_platform_matrix.py --require-evidence "
            "--require-current-commit --require-clean-source "
            f"--evidence-dir release-platform-evidence --target-filter {target_id}"
        )
        for target_id in target_ids
    ]
    return {
        "host": host,
        "target_count": len(target_ids),
        "target_ids": target_ids,
        "list_command": "python tools/run_release_platform_probe.py --list-local-browser-targets",
        "batch_command": (
            "python tools/run_release_platform_probe.py "
            "--local-browser-targets --require-clean-source --require-native-source-sync "
            "--output-dir release-platform-evidence"
        ),
        "validation_commands": validation_commands,
        "partial_evidence_only": True,
        "remaining_matrix_targets_still_required": True,
    }


def _release_asset_names(payload: dict[str, Any]) -> set[str]:
    rows = payload.get("assets")
    if not isinstance(rows, list):
        raise ValueError("GitHub release payload does not contain an asset list")
    return {
        str(row.get("name") or "").strip()
        for row in rows
        if isinstance(row, dict) and str(row.get("name") or "").strip()
    }


def _rust_release_artifacts(tag: str, present_names: set[str]) -> tuple[list[dict[str, Any]], list[str]]:
    _, expected_assets = _build_expected_assets(tag)
    rust_assets = [asset for asset in expected_assets if asset.name.startswith("Trading-Bot-Rust-")]
    missing = sorted(asset.name for asset in rust_assets if asset.required and asset.name not in present_names)
    artifacts = [
        {
            "name": asset.name,
            "group": asset.group,
            "required": asset.required,
            "status": "passed",
        }
        for asset in rust_assets
        if asset.name in present_names
    ]
    return artifacts, missing


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as file:
        for chunk in iter(lambda: file.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _release_suite_results(target: dict[str, Any], payload: dict[str, Any]) -> list[dict[str, Any]]:
    suites = payload.get("suite_results")
    if not isinstance(suites, list):
        return []
    expected_suites = [str(item) for item in target.get("test_suites", [])]
    accepted_names = {
        name
        for suite in expected_suites
        for name in REQUIRED_SUITE_RESULT_NAMES.get(suite, (suite,))
    }
    results: list[dict[str, Any]] = []
    for item in suites:
        if not isinstance(item, dict):
            continue
        name = str(item.get("name") or "").strip()
        if not name or name not in accepted_names:
            continue
        result: dict[str, Any] = {
            "name": name,
            "status": str(item.get("status") or "").strip(),
        }
        target_match = item.get("target_match")
        if isinstance(target_match, dict):
            result["target_match"] = {
                "matched": target_match.get("matched") is True,
                "issues": [str(issue) for issue in target_match.get("issues", []) if str(issue).strip()],
            }
        results.append(result)
    return results


def _platform_results(platform_targets: list[dict[str, Any]], browser_targets: list[dict[str, Any]], evidence_dir: Path) -> list[dict[str, Any]]:
    results: list[dict[str, Any]] = []
    for target in platform_targets + browser_targets:
        target_id = str(target["id"])
        evidence_file = f"{target_id}.json"
        evidence_path = evidence_dir / evidence_file
        payload = _read_evidence(evidence_path)
        suite_results = _release_suite_results(target, payload)
        results.append(
            {
                "target_id": target_id,
                "kind": target["kind"],
                "runner_kind": target["runner_kind"],
                "status": "passed",
                "evidence_file": evidence_file,
                "evidence_sha256": _sha256_file(evidence_path),
                "expected_suite_count": len(target.get("test_suites", [])),
                "test_suites": [str(item) for item in target.get("test_suites", [])],
                "suite_count": len(suite_results),
                "suite_results": suite_results,
            }
        )
    return results


def _target_source_binding_issues(payload: dict[str, Any], path: Path) -> list[str]:
    issues: list[str] = []
    current_commit = _current_git_commit()
    current_contract_hash = native_python_source_contract_hash().lower()
    if str(payload.get("commit") or "").strip() != current_commit:
        issues.append(f"{path} commit must match current git commit {current_commit}")
    if payload.get("source_tree_clean") is not True:
        issues.append(f"{path} source_tree_clean must be true for release promotion evidence")
    if str(payload.get("python_source_contract_hash") or "").strip().lower() != current_contract_hash:
        issues.append(f"{path} python_source_contract_hash must match current Python source contract")
    native_source_sync = payload.get("native_source_sync")
    if not isinstance(native_source_sync, dict) or not native_source_sync:
        issues.append(f"{path} native_source_sync must be a non-empty object")
    else:
        if native_source_sync.get("required") is not True:
            issues.append(f"{path} native_source_sync.required must be true")
        if str(native_source_sync.get("audit_artifact") or "").strip() != NATIVE_SOURCE_SYNC_AUDIT_ARTIFACT:
            issues.append(f"{path} native_source_sync.audit_artifact must be {NATIVE_SOURCE_SYNC_AUDIT_ARTIFACT}")
        if str(native_source_sync.get("audit_path") or "").strip().replace("\\", "/") != NATIVE_SOURCE_SYNC_AUDIT_PATH:
            issues.append(f"{path} native_source_sync.audit_path must be {NATIVE_SOURCE_SYNC_AUDIT_PATH}")
        if str(native_source_sync.get("python_source_of_truth") or "").strip().replace("\\", "/") != NATIVE_SOURCE_SYNC_SOURCE:
            issues.append(f"{path} native_source_sync.python_source_of_truth must be {NATIVE_SOURCE_SYNC_SOURCE}")
        binding_hash = str(native_source_sync.get("contract_hash") or "").strip().lower()
        if not re.fullmatch(r"[0-9a-f]{64}", binding_hash):
            issues.append(f"{path} native_source_sync.contract_hash must be a SHA-256 hex digest")
        elif binding_hash != current_contract_hash:
            issues.append(f"{path} native_source_sync.contract_hash must match current Python source contract")
        if native_source_sync.get("surface_contract_required") is not True:
            issues.append(f"{path} native_source_sync.surface_contract_required must be true")
    if payload.get("runtime_ready_claimed") is not False:
        issues.append(f"{path} runtime_ready_claimed must be false")
    if payload.get("secrets_redacted") is not True:
        issues.append(f"{path} secrets_redacted must be true")
    return issues


def _release_platform_source_binding_issues(
    targets: list[dict[str, Any]], evidence_dir: Path
) -> list[str]:
    issues: list[str] = []
    for target in targets:
        target_id = str(target["id"])
        path = evidence_dir / f"{target_id}.json"
        if not path.is_file():
            continue
        payload = _read_evidence(path)
        issues.extend(_target_source_binding_issues(payload, path))
    return issues


def _limit_list(values: list[Any], limit: int) -> list[Any]:
    if limit <= 0:
        return values
    return values[:limit]


def _required_workflow_inputs(target: dict[str, Any]) -> list[str]:
    suites = {str(item) for item in target.get("test_suites", [])}
    inputs: list[str] = []
    if (target.get("kind") == "browser" or "browser-contract" in suites) and not has_builtin_browser_contract_command(target):
        inputs.append("browser_test_command")
    return inputs


def _workflow_dispatch_example(target: dict[str, Any]) -> str:
    target_id = str(target.get("id") or "")
    runner_labels = target.get("runner_labels")
    runner_labels_json = json.dumps(runner_labels if isinstance(runner_labels, list) else [], separators=(",", ":"))
    args = [
        "gh workflow run release-platform-real-tests.yml",
        f"-f target_id={target_id}",
        f"-f runner_labels_json='{runner_labels_json}'",
    ]
    if "desktop_smoke_command" in _required_workflow_inputs(target):
        args.append("-f desktop_smoke_command='<real release desktop smoke command>'")
    if "browser_test_command" in _required_workflow_inputs(target):
        args.append(f"-f browser_test_command='{browser_contract_command_text(target)}'")
    return " ".join(args)


def _target_plan(target: dict[str, Any]) -> dict[str, Any]:
    target_id = str(target.get("id") or "")
    runner_labels = target.get("runner_labels")
    runner_labels_list = runner_labels if isinstance(runner_labels, list) else []
    plan = {
        "target_id": target_id,
        "kind": str(target.get("kind") or ""),
        "runner_kind": str(target.get("runner_kind") or ""),
        "runner_labels": runner_labels_list,
        "runner_labels_json": json.dumps(runner_labels_list, separators=(",", ":")),
        "test_suites": [str(item) for item in target.get("test_suites", [])],
        "required_workflow_inputs": _required_workflow_inputs(target),
        "probe_command": (
            "python tools/run_release_platform_probe.py "
            f"--target-id {target_id} --require-clean-source --require-native-source-sync "
            f"--output release-platform-evidence/{target_id}.json"
        ),
        "target_validation_command": (
            "python tools/check_release_platform_matrix.py --require-evidence "
            "--require-current-commit --require-clean-source "
            f"--evidence-dir release-platform-evidence --target-filter {target_id}"
        ),
        "workflow_dispatch_example": _workflow_dispatch_example(target),
    }
    if target.get("kind") == "browser" or "browser-contract" in set(plan["test_suites"]):
        plan["browser_contract_command"] = browser_contract_command_text(target)
        plan["browser_contract_command_builtin"] = has_builtin_browser_contract_command(target)
    return plan


def _workflow_dispatch_batch_plan(targets: list[dict[str, Any]], *, limit: int) -> dict[str, Any]:
    def _workflow_inputs_for_plan(plan: dict[str, Any]) -> dict[str, Any]:
        inputs: dict[str, Any] = {
            "target_id": str(plan.get("target_id") or ""),
            "runner_labels_json": str(plan.get("runner_labels_json") or "[]"),
        }
        required_inputs = set(str(item) for item in plan.get("required_workflow_inputs") or [])
        if "desktop_smoke_command" in required_inputs:
            inputs["desktop_smoke_command"] = "<real release desktop smoke command>"
        if "browser_test_command" in required_inputs:
            inputs["browser_test_command"] = str(plan.get("browser_contract_command") or "")
        return inputs

    target_plans = [_target_plan(target) for target in targets]
    limited_plans = _limit_list(target_plans, limit)
    workflow_dispatch_inputs = [_workflow_inputs_for_plan(plan) for plan in limited_plans]
    manual_input_targets = [
        {
            "target_id": str(plan.get("target_id") or ""),
            "required_workflow_inputs": list(plan.get("required_workflow_inputs") or []),
            "workflow_dispatch_inputs": {
                key: value
                for key, value in _workflow_inputs_for_plan(plan).items()
                if key not in {"target_id", "runner_labels_json"}
            },
            "workflow_dispatch_example": str(plan.get("workflow_dispatch_example") or ""),
        }
        for plan in target_plans
        if plan.get("required_workflow_inputs")
    ]
    limited_manual_input_targets = _limit_list(manual_input_targets, limit)
    return {
        "workflow": "release-platform-real-tests.yml",
        "target_count": len(target_plans),
        "target_ids": [str(plan.get("target_id") or "") for plan in target_plans],
        "command_limit": limit,
        "command_count": len(limited_plans),
        "command_target_ids": [str(plan.get("target_id") or "") for plan in limited_plans],
        "commands": [str(plan.get("workflow_dispatch_example") or "") for plan in limited_plans],
        "workflow_dispatch_inputs": workflow_dispatch_inputs,
        "commands_truncated": limit > 0 and len(target_plans) > limit,
        "manual_input_target_count": len(manual_input_targets),
        "manual_input_targets": limited_manual_input_targets,
        "manual_input_targets_truncated": limit > 0 and len(manual_input_targets) > limit,
        "complete_matrix_dispatch": {
            "workflow": "release-platform-real-tests.yml",
            "workflow_dispatch_inputs": {
                "target_id": "all",
                "runner_labels_json": "",
                "require_all_evidence": True,
            },
            "command": (
                "gh workflow run release-platform-real-tests.yml "
                "-f target_id=all -f require_all_evidence=true"
            ),
            "description": (
                "Preferred promotion collection: run every checked-in release target in one "
                "GitHub Actions workflow so the full evidence gate validates the combined artifacts."
            ),
        },
        "artifact_name_pattern": "release-platform-evidence-<target_id>",
        "validation_command": (
            "python tools/check_release_platform_matrix.py --require-evidence "
            "--require-current-commit --require-clean-source --evidence-dir release-platform-evidence"
        ),
        "aggregate_write_command": (
            "python tools/write_rust_native_release_evidence.py --tag <tag> "
            "--platform-evidence-dir release-platform-evidence"
        ),
    }


def preflight_release_evidence_inputs(
    *,
    tag: str,
    owner: str,
    repo: str,
    matrix_path: Path,
    platform_evidence_dir: Path,
    output_dir: Path,
    missing_limit: int = 25,
) -> dict[str, Any]:
    """Inspect local release evidence inputs without network access or writes."""

    matrix_path = _repo_path(matrix_path)
    platform_evidence_dir = _repo_path(platform_evidence_dir)
    output_dir = _repo_path(output_dir)
    output_write_guard = generated_evidence_write_guard(
        [output_dir / f"{EVIDENCE_ID}.json"],
        root=_repo_root(),
        require_generated_destinations=True,
    )
    version, expected_assets = _build_expected_assets(tag)
    required_rust_assets = sorted(
        asset.name
        for asset in expected_assets
        if asset.required and asset.name.startswith("Trading-Bot-Rust-")
    )
    optional_rust_assets = sorted(
        asset.name
        for asset in expected_assets
        if not asset.required and asset.name.startswith("Trading-Bot-Rust-")
    )
    issues: list[str] = []
    source_tree_clean = _source_tree_clean()
    if not source_tree_clean:
        issues.append(DIRTY_SOURCE_RELEASE_EVIDENCE_ISSUE)
    native_source_sync_guard = _native_source_sync_guard()
    if not native_source_sync_guard["ok"]:
        issues.append(FAILED_SOURCE_SYNC_RELEASE_EVIDENCE_ISSUE)
        issues.extend(str(issue) for issue in native_source_sync_guard["issues"])
    platform_targets: list[dict[str, Any]] = []
    browser_targets: list[dict[str, Any]] = []
    try:
        matrix = _load_json(matrix_path)
        platform_targets, browser_targets, matrix_issues = _validate_matrix(matrix)
        issues.extend(matrix_issues)
    except ValueError as exc:
        issues.append(str(exc))

    targets_by_id = {str(target["id"]): target for target in platform_targets + browser_targets}
    target_ids = list(targets_by_id)
    evidence_dir_exists = platform_evidence_dir.is_dir()
    present_evidence = sorted(
        path.stem
        for path in platform_evidence_dir.glob("*.json")
        if platform_evidence_dir.is_dir() and path.is_file()
    )
    present_evidence_set = set(present_evidence)
    missing_evidence = sorted(target_id for target_id in target_ids if target_id not in present_evidence_set)
    passed_evidence: list[str] = []
    invalid_evidence: list[dict[str, Any]] = []
    for target_id in target_ids:
        if target_id not in present_evidence_set:
            continue
        target_issues = _target_evidence_issues(targets_by_id[target_id], platform_evidence_dir)
        if not target_issues:
            payload = _read_evidence(platform_evidence_dir / f"{target_id}.json")
            target_issues.extend(
                _target_source_binding_issues(payload, platform_evidence_dir / f"{target_id}.json")
            )
        if target_issues:
            invalid_evidence.append(
                {
                    "target_id": target_id,
                    "path": str(platform_evidence_dir / f"{target_id}.json"),
                    "issues": target_issues,
                }
            )
        else:
            passed_evidence.append(target_id)
    unknown_evidence = sorted(target_id for target_id in present_evidence if target_id not in set(target_ids))
    if target_ids and missing_evidence:
        issues.append(
            f"missing release platform evidence for {len(missing_evidence)} of {len(target_ids)} target(s)"
        )
    if invalid_evidence:
        issues.append(f"invalid release platform evidence for {len(invalid_evidence)} target(s)")
    if not output_write_guard["ok"]:
        issues.extend(str(issue) for issue in output_write_guard["issues"])

    missing_targets = [targets_by_id[target_id] for target_id in missing_evidence if target_id in targets_by_id]
    missing_evidence_plan = [_target_plan(target) for target in _limit_list(missing_targets, missing_limit)]
    workflow_dispatch_batch_plan = _workflow_dispatch_batch_plan(missing_targets, limit=missing_limit)
    local_browser_batch_plan = _local_browser_batch_plan(browser_targets)
    github_token_present = bool(
        str(os.environ.get("GITHUB_TOKEN") or "").strip()
        or str(os.environ.get("GH_TOKEN") or "").strip()
    )
    can_attempt_write = not issues
    return {
        "ok": can_attempt_write,
        "mode": "rust_native_release_evidence_preflight",
        "network_access_attempted": False,
        "artifact_write_attempted": False,
        "secrets_redacted": True,
        "release_asset_presence_verified": False,
        "release_asset_presence_requires_network": True,
        "github_token_present": github_token_present,
        "tag": tag,
        "asset_version": version,
        "owner": owner,
        "repo": repo,
        "matrix_path": str(matrix_path),
        "platform_evidence_dir": str(platform_evidence_dir),
        "platform_evidence_dir_exists": evidence_dir_exists,
        "source_tree_clean": source_tree_clean,
        "python_source_contract_hash": native_python_source_contract_hash(),
        "native_source_sync": _native_source_sync_binding(),
        "native_source_sync_guard": native_source_sync_guard,
        "release_evidence_target_count": len(target_ids),
        "platform_target_count": len(platform_targets),
        "browser_target_count": len(browser_targets),
        "required_rust_release_assets": required_rust_assets,
        "optional_rust_release_assets": optional_rust_assets,
        "present_platform_evidence_count": len(present_evidence),
        "passed_platform_evidence_count": len(passed_evidence),
        "invalid_platform_evidence_count": len(invalid_evidence),
        "invalid_platform_evidence": _limit_list(invalid_evidence, missing_limit),
        "unknown_platform_evidence_count": len(unknown_evidence),
        "unknown_platform_evidence": _limit_list(unknown_evidence, missing_limit),
        "missing_platform_evidence_count": len(missing_evidence),
        "missing_platform_evidence_limit": missing_limit,
        "missing_platform_evidence_all": missing_evidence,
        "missing_platform_evidence": _limit_list(missing_evidence, missing_limit),
        "missing_platform_evidence_plan": missing_evidence_plan,
        "missing_platform_evidence_truncated": missing_limit > 0 and len(missing_evidence) > missing_limit,
        "workflow_dispatch_batch_plan": workflow_dispatch_batch_plan,
        "local_browser_batch_plan": local_browser_batch_plan,
        "expected_output_path": str(output_dir / f"{EVIDENCE_ID}.json"),
        "source_control_write_guard": output_write_guard,
        "preflight_command": (
            "python tools/write_rust_native_release_evidence.py --tag <tag> "
            "--platform-evidence-dir release-platform-evidence --preflight --json"
        ),
        "write_command": (
            "python tools/write_rust_native_release_evidence.py --tag <tag> "
            "--platform-evidence-dir release-platform-evidence"
        ),
        "issues": issues,
    }


def build_release_evidence(
    *,
    tag: str,
    owner: str,
    repo: str,
    timeout: float,
    matrix_path: Path,
    platform_evidence_dir: Path,
) -> tuple[dict[str, Any] | None, list[str]]:
    issues: list[str] = []
    matrix_path = _repo_path(matrix_path)
    platform_evidence_dir = _repo_path(platform_evidence_dir)
    if not _source_tree_clean():
        return None, [DIRTY_SOURCE_RELEASE_EVIDENCE_ISSUE]
    native_source_sync_guard = _native_source_sync_guard()
    if not native_source_sync_guard["ok"]:
        return None, [
            FAILED_SOURCE_SYNC_RELEASE_EVIDENCE_ISSUE,
            *[str(issue) for issue in native_source_sync_guard["issues"]],
        ]
    token = (
        str(os.environ.get("GITHUB_TOKEN") or "").strip()
        or str(os.environ.get("GH_TOKEN") or "").strip()
        or None
    )
    try:
        release_payload = _fetch_release(tag, owner=owner, repo=repo, timeout=timeout, token=token)
        release_asset_names = _release_asset_names(release_payload)
    except (RuntimeError, ValueError) as exc:
        return None, [f"release asset check failed: {exc}"]

    release_artifacts, missing_rust_assets = _rust_release_artifacts(tag, release_asset_names)
    if missing_rust_assets:
        issues.append(f"missing required Rust release assets: {', '.join(missing_rust_assets)}")
    if not release_artifacts:
        issues.append("no Rust release artifacts were present on the GitHub release")

    try:
        matrix = _load_json(matrix_path)
    except ValueError as exc:
        return None, [str(exc)]
    platform_targets, browser_targets, matrix_issues = _validate_matrix(matrix)
    issues.extend(matrix_issues)
    if not matrix_issues:
        issues.extend(_evidence_issues(platform_targets + browser_targets, platform_evidence_dir))
        if not issues:
            issues.extend(
                _release_platform_source_binding_issues(
                    platform_targets + browser_targets,
                    platform_evidence_dir,
                )
            )
    if issues:
        return None, issues

    platform_results = _platform_results(platform_targets, browser_targets, platform_evidence_dir)
    command = " ".join(sys.argv)
    artifact = {
        "evidence_id": EVIDENCE_ID,
        "status": "passed",
        "evidence_scope": "release_platform",
        "generated_at": _current_unix_timestamp_label(),
        "commit": _current_git_commit(),
        "source_tree_clean": _source_tree_clean(),
        "python_source_contract_hash": native_python_source_contract_hash(),
        "native_source_sync": _native_source_sync_binding(),
        "command": command,
        "environment": {
            "tag": tag,
            "owner": owner,
            "repo": repo,
            "matrix": str(matrix_path),
            "platform_evidence_dir": str(platform_evidence_dir),
        },
        "secrets_redacted": True,
        "runtime_ready_claimed": False,
        "release_artifacts": release_artifacts,
        "platform_results": platform_results,
        "suite_results": [
            {
                "name": "required_rust_release_assets_present",
                "status": "passed",
                "observed_count": len(release_artifacts),
            },
            {
                "name": "release_platform_matrix_evidence_present",
                "status": "passed",
                "observed_count": len(platform_results),
            },
        ],
    }
    return artifact, []


def main(argv: list[str] | None = None) -> int:
    default_owner, default_repo = _resolve_default_repo()
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--tag", required=True, help="GitHub release tag to validate, for example v1.0.30.")
    parser.add_argument("--owner", default=default_owner, help=f"GitHub owner (default: {default_owner}).")
    parser.add_argument("--repo", default=default_repo, help=f"GitHub repo (default: {default_repo}).")
    parser.add_argument("--timeout", type=float, default=15.0, help="GitHub API timeout in seconds.")
    parser.add_argument("--matrix", default=str(DEFAULT_MATRIX_PATH), help="Release platform matrix JSON path.")
    parser.add_argument(
        "--platform-evidence-dir",
        default="release-platform-evidence",
        help="Directory containing per-target release platform evidence JSON files.",
    )
    parser.add_argument(
        "--output-dir",
        default=str(DEFAULT_OUTPUT_DIR),
        help="Directory where rust-native-release-platform-evidence.json will be written.",
    )
    parser.add_argument(
        "--preflight",
        action="store_true",
        help="Inspect local release evidence inputs without contacting GitHub or writing artifacts.",
    )
    parser.add_argument(
        "--missing-limit",
        type=int,
        default=25,
        help="Maximum missing release-platform targets to include in preflight JSON. Use 0 for all.",
    )
    parser.add_argument("--json", action="store_true", help="Print machine-readable JSON.")
    args = parser.parse_args(argv)

    if args.preflight:
        result = preflight_release_evidence_inputs(
            tag=str(args.tag).strip(),
            owner=str(args.owner).strip(),
            repo=str(args.repo).strip(),
            matrix_path=Path(args.matrix),
            platform_evidence_dir=Path(args.platform_evidence_dir),
            output_dir=Path(args.output_dir),
            missing_limit=max(0, int(args.missing_limit)),
        )
        if args.json:
            print(json.dumps(result, indent=2, sort_keys=True))
        else:
            state = "ok" if result["ok"] else "blocked"
            print(f"Rust native release evidence preflight: {state}")
            for issue in result["issues"]:
                print(f"- {issue}")
            print("No network request or artifact write was attempted.")
        return 0 if result["ok"] else 1

    artifact, issues = build_release_evidence(
        tag=str(args.tag).strip(),
        owner=str(args.owner).strip(),
        repo=str(args.repo).strip(),
        timeout=float(args.timeout),
        matrix_path=Path(args.matrix),
        platform_evidence_dir=Path(args.platform_evidence_dir),
    )
    if issues or artifact is None:
        result = {"ok": False, "issues": issues, "artifact": None}
        if args.json:
            print(json.dumps(result, indent=2, sort_keys=True))
        else:
            print("Rust native release evidence was not written:")
            for issue in issues:
                print(f"- {issue}")
        return 1

    output_dir = _repo_path(Path(args.output_dir))
    output_path = output_dir / f"{EVIDENCE_ID}.json"
    source_control_write_guard = generated_evidence_write_guard(
        [output_path],
        root=_repo_root(),
        require_generated_destinations=True,
    )
    if not source_control_write_guard["ok"]:
        result = {
            "ok": False,
            "issues": [str(issue) for issue in source_control_write_guard["issues"]],
            "artifact": None,
            "source_control_write_guard": source_control_write_guard,
        }
        if args.json:
            print(json.dumps(result, indent=2, sort_keys=True))
        else:
            print("Rust native release evidence was not written:")
            for issue in result["issues"]:
                print(f"- {issue}")
        return 1

    output_dir.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(artifact, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    result = {
        "ok": True,
        "artifact": str(output_path),
        "source_control_write_guard": source_control_write_guard,
        "issues": [],
    }
    if args.json:
        print(json.dumps(result, indent=2, sort_keys=True))
    else:
        print(f"Rust native release evidence written to {output_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
