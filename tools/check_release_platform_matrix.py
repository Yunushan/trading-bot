#!/usr/bin/env python3
"""Validate the release platform/browser test matrix and optional evidence."""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path
from typing import Any


REQUIRED_PLATFORM_GROUPS: tuple[tuple[str, tuple[str, ...], tuple[str, ...]], ...] = (
    ("windows", ("xp", "vista", "7", "8", "8.1", "10", "11"), ("x86", "x64", "arm32", "arm64")),
    ("macos", ("14", "15", "26"), ("x64", "arm64")),
    ("rhel", ("7", "8", "9", "10"), ("x64", "arm64")),
    ("ubuntu", ("20.04", "22.04", "24.04", "26.04"), ("x64", "arm64")),
    ("freebsd", ("release",), ("x64", "arm64")),
    ("openbsd", ("release",), ("x64", "arm64")),
    ("netbsd", ("release",), ("x64", "arm64")),
    ("android", ("14", "15", "16"), ("x86_64-emulator", "arm64-device")),
    ("ios", ("15", "16", "18", "26"), ("simulator-arm64", "device-arm64")),
)

REQUIRED_BROWSERS = ("chrome", "firefox", "internet-explorer", "edge")
DEFAULT_MATRIX_PATH = Path("docs/release-platform-test-matrix.json")


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
        for host in hosts:
            host_slug = _slug(host)
            target_id = f"browser-{_slug(browser)}-{host_slug}"
            runner_labels = [item.format(browser=_slug(browser), host=host_slug, target_id=target_id) for item in template]
            targets.append(
                {
                    "id": target_id,
                    "kind": "browser",
                    "browser": browser,
                    "host": host,
                    "runner_kind": runner_kind,
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


def _evidence_issues(targets: list[dict[str, Any]], evidence_dir: Path) -> list[str]:
    issues: list[str] = []
    for target in targets:
        target_id = str(target["id"])
        path = evidence_dir / f"{target_id}.json"
        if not path.is_file():
            issues.append(f"missing evidence for {target_id}: {path}")
            continue
        payload = _read_evidence(path)
        if payload.get("target_id") != target_id:
            issues.append(f"{path} target_id does not match {target_id}")
        if payload.get("status") != "passed":
            issues.append(f"{path} status must be passed")
        suites = payload.get("suite_results")
        if not isinstance(suites, list) or not suites:
            issues.append(f"{path} must contain non-empty suite_results")
        elif any(not isinstance(item, dict) or item.get("status") != "passed" for item in suites):
            issues.append(f"{path} has a non-passing suite result")
    return issues


def _emit_matrix(targets: list[dict[str, Any]], *, target_filter: str) -> str:
    needle = target_filter.strip().lower()
    include = []
    for target in targets:
        target_id = str(target["id"])
        if needle and needle not in target_id.lower():
            continue
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


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--matrix", default=str(DEFAULT_MATRIX_PATH), help="Path to release platform test matrix JSON.")
    parser.add_argument("--schema-only", action="store_true", help="Validate only the matrix schema/coverage contract.")
    parser.add_argument("--require-evidence", action="store_true", help="Require passed evidence JSON for every target.")
    parser.add_argument("--evidence-dir", default="release-platform-evidence", help="Directory containing target evidence JSON files.")
    parser.add_argument("--emit-github-matrix", action="store_true", help="Print a GitHub Actions matrix JSON object.")
    parser.add_argument("--target-filter", default="", help="Only emit targets whose id contains this text.")
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

    if args.require_evidence:
        issues.extend(_evidence_issues(targets, Path(args.evidence_dir)))

    if args.emit_github_matrix:
        if issues:
            print(json.dumps({"include": []}, separators=(",", ":")))
            return 1
        print(_emit_matrix(targets, target_filter=args.target_filter))
        return 0

    report = {
        "ok": not issues,
        "platform_target_count": len(platform_targets),
        "browser_target_count": len(browser_targets),
        "target_count": len(targets),
        "issues": issues,
        "evidence_required": bool(args.require_evidence),
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
