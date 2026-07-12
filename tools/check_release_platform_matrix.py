#!/usr/bin/env python3
"""Validate the release platform/browser test matrix and optional evidence."""

from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[1]
PYTHON_ROOT = REPO_ROOT / "Languages" / "Python"
if str(PYTHON_ROOT) not in sys.path:
    sys.path.insert(0, str(PYTHON_ROOT))

from app.native_parity import native_python_source_contract_hash  # noqa: E402


REQUIRED_PLATFORM_GROUPS: tuple[tuple[str, tuple[str, ...], tuple[str, ...]], ...] = (
    ("windows", ("11",), ("x64",)),
    ("macos", ("15",), ("arm64",)),
    ("ubuntu", ("24.04",), ("x64",)),
)

REQUIRED_BROWSERS = ("chrome", "firefox", "edge")
DEFAULT_MATRIX_PATH = Path("docs/release-platform-test-matrix.json")
PROMOTION_SOURCE_TREE_IGNORED_PATHS = (
    "artifacts/rust-native-runtime-evidence",
    "artifacts/native-source-sync",
    "release-platform-evidence",
)
REQUIRED_SUITE_RESULT_NAMES: dict[str, tuple[str, ...]] = {
    "platform-probe": ("platform-probe",),
    "python-service-contract": ("python-service-contract",),
    "desktop-release-smoke": ("desktop-release-smoke",),
    "native-build-smoke": ("native-build-smoke", "rust-workspace-check"),
    "mobile-client-contract": ("mobile-client-contract",),
    "browser-contract": ("browser-contract",),
}
TARGET_EVIDENCE_STRING_FIELDS = (
    "target_id",
    "status",
    "commit",
    "python_source_contract_hash",
)
TARGET_EVIDENCE_BOOL_FIELDS = (
    "source_tree_clean",
    "runtime_ready_claimed",
    "secrets_redacted",
)
NATIVE_SOURCE_SYNC_AUDIT_ARTIFACT = "native-source-sync-audit"
NATIVE_SOURCE_SYNC_AUDIT_PATH = "artifacts/native-source-sync/native-source-sync-audit.json"
NATIVE_SOURCE_SYNC_SOURCE = "Languages/Python/app/native_parity.py"


def _slug(value: str) -> str:
    return re.sub(r"[^a-z0-9]+", "_", str(value).strip().lower()).strip("_")


def _target_id(family: str, version: str, arch: str) -> str:
    return f"{_slug(family)}-{_slug(version)}-{_slug(arch)}"


def _load_json(path: Path) -> dict[str, Any]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise ValueError(f"{path} is not valid JSON: {exc}") from exc
    except OSError as exc:
        raise ValueError(f"Unable to read {path}: {exc}") from exc
    if not isinstance(payload, dict):
        raise ValueError(f"{path} must contain a JSON object")
    return payload


def _list_of_strings(value: Any, *, field: str) -> list[str]:
    if not isinstance(value, list) or not value:
        raise ValueError(f"{field} must be a non-empty list")
    result = [str(item).strip() for item in value if str(item).strip()]
    if len(result) != len(value):
        raise ValueError(f"{field} must contain only non-empty strings")
    return result


def _runner_labels(group: dict[str, Any], *, version: str, arch: str, target_id: str) -> list[str]:
    label_map = group.get("runner_label_map")
    map_key = f"{version}:{arch}"
    if isinstance(label_map, dict) and map_key in label_map:
        return _list_of_strings(label_map[map_key], field=f"runner_label_map[{map_key}]")
    template = _list_of_strings(group.get("runner_labels_template"), field="runner_labels_template")
    return [
        item.format(
            version=version,
            version_slug=_slug(version),
            arch=_slug(arch),
            target_id=target_id,
        )
        for item in template
    ]


def _expand_platform_targets(matrix: dict[str, Any]) -> list[dict[str, Any]]:
    groups = matrix.get("target_groups")
    if not isinstance(groups, list) or not groups:
        raise ValueError("target_groups must be a non-empty list")

    targets: list[dict[str, Any]] = []
    for group_index, group in enumerate(groups):
        if not isinstance(group, dict):
            raise ValueError(f"target_groups[{group_index}] must be an object")
        family = str(group.get("family") or "").strip().lower()
        if not family:
            raise ValueError(f"target_groups[{group_index}].family is required")
        versions = _list_of_strings(group.get("versions"), field=f"{family}.versions")
        architectures = _list_of_strings(group.get("architectures"), field=f"{family}.architectures")
        suites = _list_of_strings(group.get("test_suites"), field=f"{family}.test_suites")
        runner_kind = str(group.get("runner_kind") or "").strip()
        if not runner_kind:
            raise ValueError(f"{family}.runner_kind is required")
        if group.get("evidence_required") is not True:
            raise ValueError(f"{family}.evidence_required must be true")

        for version in versions:
            for arch in architectures:
                target_id = _target_id(family, version, arch)
                targets.append(
                    {
                        "id": target_id,
                        "kind": "platform",
                        "family": family,
                        "version": version,
                        "architecture": arch,
                        "runner_kind": runner_kind,
                        "runner_labels": _runner_labels(group, version=version, arch=arch, target_id=target_id),
                        "test_suites": suites,
                        "evidence_required": True,
                    }
                )
    return targets


def _expand_browser_targets(matrix: dict[str, Any]) -> list[dict[str, Any]]:
    groups = matrix.get("browser_groups")
    if not isinstance(groups, list) or not groups:
        raise ValueError("browser_groups must be a non-empty list")

    targets: list[dict[str, Any]] = []
    for group_index, group in enumerate(groups):
        if not isinstance(group, dict):
            raise ValueError(f"browser_groups[{group_index}] must be an object")
        browser = str(group.get("browser") or "").strip().lower()
        if not browser:
            raise ValueError(f"browser_groups[{group_index}].browser is required")
        hosts = _list_of_strings(group.get("hosts"), field=f"{browser}.hosts")
        suites = _list_of_strings(group.get("test_suites"), field=f"{browser}.test_suites")
        runner_kind = str(group.get("runner_kind") or "").strip()
        if not runner_kind:
            raise ValueError(f"{browser}.runner_kind is required")
        if group.get("evidence_required") is not True:
            raise ValueError(f"{browser}.evidence_required must be true")
        template = _list_of_strings(group.get("runner_labels_template"), field=f"{browser}.runner_labels_template")
        runner_kind_map = group.get("runner_kind_map")
        if runner_kind_map is not None:
            if not isinstance(runner_kind_map, dict):
                raise ValueError(f"{browser}.runner_kind_map must be an object when provided")
            unknown_hosts = sorted(set(runner_kind_map) - set(hosts))
            if unknown_hosts:
                raise ValueError(f"{browser}.runner_kind_map has unknown hosts: {', '.join(unknown_hosts)}")
            invalid_hosts = sorted(
                host for host, mapped_kind in runner_kind_map.items() if not str(mapped_kind or "").strip()
            )
            if invalid_hosts:
                raise ValueError(f"{browser}.runner_kind_map has empty kinds: {', '.join(invalid_hosts)}")
        for host in hosts:
            host_slug = _slug(host)
            target_id = f"browser-{_slug(browser)}-{host_slug}"
            label_map = group.get("runner_label_map")
            if isinstance(label_map, dict) and host in label_map:
                runner_labels = _list_of_strings(label_map[host], field=f"{browser}.runner_label_map[{host}]")
            else:
                runner_labels = [
                    item.format(browser=_slug(browser), host=host_slug, target_id=target_id) for item in template
                ]
            runner_kind_for_host = (
                str(runner_kind_map.get(host) or "").strip()
                if isinstance(runner_kind_map, dict)
                else ""
            )
            targets.append(
                {
                    "id": target_id,
                    "kind": "browser",
                    "browser": browser,
                    "host": host,
                    "runner_kind": runner_kind_for_host or runner_kind,
                    "runner_labels": runner_labels,
                    "test_suites": suites,
                    "evidence_required": True,
                }
            )
    return targets


def _required_platform_ids() -> set[str]:
    ids: set[str] = set()
    for family, versions, architectures in REQUIRED_PLATFORM_GROUPS:
        for version in versions:
            for arch in architectures:
                ids.add(_target_id(family, version, arch))
    return ids


def _validate_matrix(matrix: dict[str, Any]) -> tuple[list[dict[str, Any]], list[dict[str, Any]], list[str]]:
    issues: list[str] = []
    if matrix.get("schema_version") != 1:
        issues.append("schema_version must be 1")
    policy = matrix.get("policy")
    if not isinstance(policy, dict):
        issues.append("policy must be an object")
    elif policy.get("no_assumed_passes") is not True:
        issues.append("policy.no_assumed_passes must be true")

    try:
        platform_targets = _expand_platform_targets(matrix)
        browser_targets = _expand_browser_targets(matrix)
    except ValueError as exc:
        return [], [], [str(exc)]

    all_ids = [target["id"] for target in platform_targets + browser_targets]
    duplicates = sorted({target_id for target_id in all_ids if all_ids.count(target_id) > 1})
    if duplicates:
        issues.append(f"duplicate target ids: {', '.join(duplicates)}")

    platform_ids = {target["id"] for target in platform_targets}
    missing_platforms = sorted(_required_platform_ids() - platform_ids)
    if missing_platforms:
        issues.append(f"missing required platform targets: {', '.join(missing_platforms)}")

    browsers = {str(target.get("browser") or "") for target in browser_targets}
    missing_browsers = sorted(set(REQUIRED_BROWSERS) - browsers)
    if missing_browsers:
        issues.append(f"missing required browser groups: {', '.join(missing_browsers)}")

    for target in platform_targets + browser_targets:
        labels = target.get("runner_labels")
        suites = target.get("test_suites")
        if not isinstance(labels, list) or not labels:
            issues.append(f"{target['id']} has no runner labels")
        if not isinstance(suites, list) or not suites:
            issues.append(f"{target['id']} has no test suites")
        if target.get("evidence_required") is not True:
            issues.append(f"{target['id']} must require real evidence")

    return platform_targets, browser_targets, issues


def _read_evidence(path: Path) -> dict[str, Any]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError) as exc:
        return {"ok": False, "error": str(exc)}
    if not isinstance(payload, dict):
        return {"ok": False, "error": "evidence JSON must be an object"}
    return payload


def _repo_root() -> Path:
    return REPO_ROOT


def _current_git_commit() -> str | None:
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
        return None
    commit = output.stdout.strip()
    return commit or None


def _source_tree_status_command(*, untracked_files: str) -> list[str]:
    command = ["git", "status", "--porcelain", f"--untracked-files={untracked_files}", "--", "."]
    command.extend(f":(exclude){path}" for path in PROMOTION_SOURCE_TREE_IGNORED_PATHS)
    return command


def _paths_from_porcelain(output: str, *, untracked_only: bool) -> list[str]:
    paths: list[str] = []
    for line in output.splitlines():
        if not line.strip():
            continue
        if untracked_only and not line.startswith("?? "):
            continue
        path = line[3:] if len(line) > 3 else line.strip()
        if " -> " in path:
            path = path.split(" -> ", 1)[-1]
        path = path.strip().strip('"')
        if path:
            paths.append(path)
    return paths


def _current_source_tree_dirty_paths() -> list[str] | None:
    try:
        output = subprocess.run(
            _source_tree_status_command(untracked_files="no"),
            cwd=_repo_root(),
            check=True,
            capture_output=True,
            text=True,
            timeout=10,
        )
    except (OSError, subprocess.SubprocessError):
        return None
    return _paths_from_porcelain(output.stdout, untracked_only=False)


def _current_source_tree_untracked_paths() -> list[str] | None:
    try:
        output = subprocess.run(
            _source_tree_status_command(untracked_files="all"),
            cwd=_repo_root(),
            check=True,
            capture_output=True,
            text=True,
            timeout=10,
        )
    except (OSError, subprocess.SubprocessError):
        return None
    return _paths_from_porcelain(output.stdout, untracked_only=True)


def _current_source_tree_clean() -> bool | None:
    dirty_paths = _current_source_tree_dirty_paths()
    untracked_paths = _current_source_tree_untracked_paths()
    if dirty_paths is None or untracked_paths is None:
        return None
    return not dirty_paths and not untracked_paths


def _source_binding_context(
    *,
    require_current_commit: bool,
    require_clean_source: bool,
) -> dict[str, Any]:
    context: dict[str, Any] = {
        "require_current_commit": bool(require_current_commit),
        "require_clean_source": bool(require_clean_source),
        "current_commit": None,
        "current_python_source_contract_hash": None,
        "current_source_tree_clean": None,
        "current_source_tree_dirty_paths": [],
        "current_source_tree_untracked_paths": [],
        "issues": [],
    }
    if not require_current_commit and not require_clean_source:
        return context

    context["current_python_source_contract_hash"] = native_python_source_contract_hash()
    if require_current_commit:
        current_commit = _current_git_commit()
        context["current_commit"] = current_commit
        if not current_commit:
            context["issues"].append("current git commit could not be determined for platform evidence validation")

    if require_clean_source:
        current_source_tree_clean = _current_source_tree_clean()
        context["current_source_tree_clean"] = current_source_tree_clean
        if current_source_tree_clean is None:
            context["issues"].append("current source tree cleanliness could not be determined for platform evidence validation")
        elif not current_source_tree_clean:
            dirty_paths = _current_source_tree_dirty_paths() or []
            untracked_paths = _current_source_tree_untracked_paths() or []
            context["current_source_tree_dirty_paths"] = dirty_paths
            context["current_source_tree_untracked_paths"] = untracked_paths
            if dirty_paths:
                visible = ", ".join(dirty_paths[:10])
                suffix = "" if len(dirty_paths) <= 10 else ", ..."
                context["issues"].append(
                    "current tracked source tree must be clean for platform evidence validation; "
                    f"dirty paths: {visible}{suffix}"
                )
            if untracked_paths:
                visible = ", ".join(untracked_paths[:10])
                suffix = "" if len(untracked_paths) <= 10 else ", ..."
                context["issues"].append(
                    "current promotion source tree must not contain untracked source/tool files for platform evidence validation; "
                    f"untracked paths: {visible}{suffix}"
                )
            if not dirty_paths and not untracked_paths:
                context["issues"].append("current promotion source tree must be clean for platform evidence validation")
    return context


def _target_source_binding_issues(payload: dict[str, Any], path: Path, context: dict[str, Any]) -> list[str]:
    if not context.get("require_current_commit") and not context.get("require_clean_source"):
        return []

    issues: list[str] = []
    current_commit = context.get("current_commit")
    current_contract_hash = str(context.get("current_python_source_contract_hash") or "")
    if context.get("require_current_commit") and current_commit:
        if str(payload.get("commit") or "").strip() != current_commit:
            issues.append(f"{path} commit must match current git commit {current_commit}")
    if context.get("require_clean_source") and payload.get("source_tree_clean") is not True:
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


def _target_evidence_type_issues(payload: dict[str, Any], path: Path) -> list[str]:
    issues: list[str] = []
    for field in TARGET_EVIDENCE_STRING_FIELDS:
        if field in payload and not isinstance(payload.get(field), str):
            issues.append(f"{path} {field} must be a string")
    for field in TARGET_EVIDENCE_BOOL_FIELDS:
        if field in payload and not isinstance(payload.get(field), bool):
            issues.append(f"{path} {field} must be boolean")
    return issues


def _target_evidence_issues(
    target: dict[str, Any],
    evidence_dir: Path,
    *,
    source_binding_context: dict[str, Any] | None = None,
) -> list[str]:
    issues: list[str] = []
    target_id = str(target["id"])
    path = evidence_dir / f"{target_id}.json"
    if not path.is_file():
        return [f"missing evidence for {target_id}: {path}"]
    payload = _read_evidence(path)
    issues.extend(_target_evidence_type_issues(payload, path))
    if payload.get("target_id") != target_id:
        issues.append(f"{path} target_id does not match {target_id}")
    if payload.get("status") != "passed":
        issues.append(f"{path} status must be passed")
    suites = payload.get("suite_results")
    if not isinstance(suites, list) or not suites:
        issues.append(f"{path} must contain non-empty suite_results")
    else:
        if any(not isinstance(item, dict) or item.get("status") != "passed" for item in suites):
            issues.append(f"{path} has a non-passing suite result")

        observed_suite_names = {
            str(item.get("name") or "").strip()
            for item in suites
            if isinstance(item, dict) and str(item.get("name") or "").strip()
        }
        for suite_name in target.get("test_suites", []):
            suite_key = str(suite_name)
            accepted_names = REQUIRED_SUITE_RESULT_NAMES.get(suite_key, (suite_key,))
            if not any(name in observed_suite_names for name in accepted_names):
                issues.append(f"{path} missing required suite result for {suite_key}")

        if target.get("kind") == "platform" and "platform-probe" in target.get("test_suites", []):
            platform_probe = next(
                (item for item in suites if isinstance(item, dict) and item.get("name") == "platform-probe"),
                None,
            )
            if not isinstance(platform_probe, dict):
                issues.append(f"{path} must contain a platform-probe suite result")
            else:
                target_match = platform_probe.get("target_match")
                if not isinstance(target_match, dict) or target_match.get("matched") is not True:
                    issues.append(f"{path} platform-probe target_match.matched must be true")
    if source_binding_context is not None:
        issues.extend(_target_source_binding_issues(payload, path, source_binding_context))
    return issues


def _evidence_issues(
    targets: list[dict[str, Any]],
    evidence_dir: Path,
    *,
    source_binding_context: dict[str, Any] | None = None,
) -> list[str]:
    issues: list[str] = list(source_binding_context.get("issues", []) if source_binding_context else [])
    for target in targets:
        issues.extend(
            _target_evidence_issues(
                target,
                evidence_dir,
                source_binding_context=source_binding_context,
            )
        )
    return issues


def _filter_targets(targets: list[dict[str, Any]], *, target_filter: str) -> list[dict[str, Any]]:
    needle = target_filter.strip().lower()
    if not needle:
        return targets
    return [target for target in targets if needle in str(target["id"]).lower()]


def _emit_matrix(targets: list[dict[str, Any]]) -> str:
    include = []
    for target in targets:
        target_id = str(target["id"])
        include.append(
            {
                "target_id": target_id,
                "kind": target["kind"],
                "runner_kind": target["runner_kind"],
                "runner_labels_json": json.dumps(target["runner_labels"], separators=(",", ":")),
                "test_suites": ",".join(str(item) for item in target["test_suites"]),
            }
        )
    return json.dumps({"include": include}, separators=(",", ":"))


def _override_runner_labels(
    targets: list[dict[str, Any]], *, runner_labels_json: str
) -> tuple[list[dict[str, Any]], list[str]]:
    """Apply a focused-dispatch runner override without changing matrix policy."""

    value = runner_labels_json.strip()
    if not value:
        return targets, []
    if len(targets) != 1:
        return [], ["--runner-labels-json requires a target filter that resolves exactly one target"]
    try:
        labels = json.loads(value)
    except json.JSONDecodeError as exc:
        return [], [f"--runner-labels-json must be valid JSON: {exc}"]
    try:
        normalized = _list_of_strings(labels, field="runner_labels_json")
    except ValueError as exc:
        return [], [str(exc)]
    target = dict(targets[0])
    target["runner_labels"] = normalized
    return [target], []


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--matrix", default=str(DEFAULT_MATRIX_PATH), help="Path to release platform test matrix JSON.")
    parser.add_argument("--schema-only", action="store_true", help="Validate only the matrix schema/coverage contract.")
    parser.add_argument("--require-evidence", action="store_true", help="Require passed evidence JSON for every target.")
    parser.add_argument(
        "--require-current-commit",
        action="store_true",
        help="With --require-evidence, require target evidence commit to match the current git commit.",
    )
    parser.add_argument(
        "--require-clean-source",
        action="store_true",
        help="With --require-evidence, require clean promotion source state and source-clean target evidence.",
    )
    parser.add_argument("--evidence-dir", default="release-platform-evidence", help="Directory containing target evidence JSON files.")
    parser.add_argument("--emit-github-matrix", action="store_true", help="Print a GitHub Actions matrix JSON object.")
    parser.add_argument("--target-filter", default="", help="Only emit or validate targets whose id contains this text.")
    parser.add_argument(
        "--runner-labels-json",
        default="",
        help="Override runner labels for one focused emitted target; accepts a JSON string array.",
    )
    parser.add_argument("--json", action="store_true", help="Print validation report as JSON.")
    args = parser.parse_args(argv)

    matrix_path = Path(args.matrix)
    try:
        matrix = _load_json(matrix_path)
    except ValueError as exc:
        if args.json:
            print(json.dumps({"ok": False, "issues": [str(exc)]}, indent=2))
        else:
            print(str(exc), file=sys.stderr)
        return 1

    platform_targets, browser_targets, issues = _validate_matrix(matrix)
    targets = platform_targets + browser_targets
    filtered_targets = _filter_targets(targets, target_filter=args.target_filter)
    target_filter_active = bool(str(args.target_filter).strip())
    if target_filter_active and not filtered_targets:
        issues.append(f"target-filter matched no targets: {args.target_filter}")
    filtered_targets, override_issues = _override_runner_labels(
        filtered_targets,
        runner_labels_json=str(args.runner_labels_json),
    )
    issues.extend(override_issues)

    source_binding_context = _source_binding_context(
        require_current_commit=bool(args.require_current_commit),
        require_clean_source=bool(args.require_clean_source),
    )
    if (args.require_current_commit or args.require_clean_source) and not args.require_evidence:
        issues.append("--require-current-commit and --require-clean-source require --require-evidence")

    if args.require_evidence:
        issues.extend(
            _evidence_issues(
                filtered_targets,
                Path(args.evidence_dir),
                source_binding_context=source_binding_context,
            )
        )

    if args.emit_github_matrix:
        if issues:
            print(json.dumps({"include": []}, separators=(",", ":")))
            return 1
        print(_emit_matrix(filtered_targets))
        return 0

    report = {
        "ok": not issues,
        "platform_target_count": len(platform_targets),
        "browser_target_count": len(browser_targets),
        "target_count": len(filtered_targets) if target_filter_active else len(targets),
        "total_target_count": len(targets),
        "target_filter": str(args.target_filter).strip(),
        "issues": issues,
        "evidence_required": bool(args.require_evidence),
        "require_current_commit": bool(args.require_current_commit),
        "require_clean_source": bool(args.require_clean_source),
        "current_commit": source_binding_context.get("current_commit"),
        "current_python_source_contract_hash": source_binding_context.get("current_python_source_contract_hash"),
        "current_source_tree_clean": source_binding_context.get("current_source_tree_clean"),
        "current_source_tree_dirty_paths": source_binding_context.get("current_source_tree_dirty_paths"),
        "current_source_tree_untracked_paths": source_binding_context.get("current_source_tree_untracked_paths"),
    }
    if args.json:
        print(json.dumps(report, indent=2, sort_keys=True))
    else:
        print(
            f"release platform matrix: {report['target_count']} targets "
            f"({report['platform_target_count']} platform, {report['browser_target_count']} browser)"
        )
        if issues:
            print("issues:")
            for issue in issues:
                print(f"- {issue}")
    return 0 if not issues else 1


if __name__ == "__main__":
    raise SystemExit(main())
