#!/usr/bin/env python3
"""Ensure generated runtime/release evidence artifacts are not tracked source."""

from __future__ import annotations

import argparse
import fnmatch
import json
import subprocess
from pathlib import Path


GENERATED_EVIDENCE_PATTERNS = (
    "artifacts/rust-native-runtime-evidence/*.json",
    "artifacts/rust-native-runtime-evidence/*.zip",
    "artifacts/rust-native-runtime-evidence/downloads/*",
    "release-platform-evidence/*.json",
)

EVIDENCE_SCAN_ROOTS = (
    "artifacts/rust-native-runtime-evidence",
    "release-platform-evidence",
)


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[1]


def _repo_relative(path: Path, *, root: Path) -> str:
    try:
        return path.resolve().relative_to(root.resolve()).as_posix()
    except ValueError:
        return ""


def _git_ls_files(root: Path, paths: list[str] | None = None) -> list[str]:
    args = ["git", "ls-files"]
    if paths is None:
        args.extend(["--", *EVIDENCE_SCAN_ROOTS])
    elif paths:
        args.extend(["--", *paths])
    else:
        return []
    result = subprocess.run(
        args,
        cwd=root,
        check=True,
        capture_output=True,
        text=True,
        timeout=10,
    )
    return [line.strip().replace("\\", "/") for line in result.stdout.splitlines() if line.strip()]


def _matches_generated_evidence_artifact(path: str) -> bool:
    normalized = path.replace("\\", "/").strip()
    return any(fnmatch.fnmatchcase(normalized, pattern) for pattern in GENERATED_EVIDENCE_PATTERNS)


def check_generated_evidence_source_control(
    *,
    root: Path | None = None,
    tracked_files: list[str] | None = None,
) -> dict[str, object]:
    root = (root or _repo_root()).resolve()
    tracked = tracked_files if tracked_files is not None else _git_ls_files(root)
    generated = sorted(path.replace("\\", "/") for path in tracked if _matches_generated_evidence_artifact(path))
    existing = [path for path in generated if (root / path).exists()]
    pending_removal = [path for path in generated if path not in set(existing)]
    issues = [
        f"generated evidence artifact is tracked as source: {path}"
        for path in existing
    ]
    return {
        "ok": not issues,
        "generated_evidence_patterns": list(GENERATED_EVIDENCE_PATTERNS),
        "tracked_generated_evidence_count": len(generated),
        "tracked_existing_generated_evidence": existing,
        "tracked_pending_removal_generated_evidence": pending_removal,
        "issues": issues,
    }


def generated_evidence_write_guard(
    destination_paths: list[Path],
    *,
    root: Path | None = None,
    tracked_files: list[str] | None = None,
) -> dict[str, object]:
    root = (root or _repo_root()).resolve()
    generated_destinations = []
    for raw_path in destination_paths:
        path = raw_path if raw_path.is_absolute() else root / raw_path
        relative = _repo_relative(path, root=root)
        if relative and _matches_generated_evidence_artifact(relative):
            generated_destinations.append(relative)

    if tracked_files is None:
        tracked_files = _git_ls_files(root, generated_destinations)
    tracked = {path.replace("\\", "/") for path in tracked_files}
    tracked_targets = [path for path in generated_destinations if path in tracked]
    issues = []
    if tracked_targets:
        joined = ", ".join(tracked_targets)
        issues.append(
            "refusing to write generated evidence artifact over tracked source path(s): "
            f"{joined}. Commit the removal of generated evidence artifacts first, then "
            "regenerate/import evidence from a clean candidate source commit."
        )
    return {
        "ok": not issues,
        "generated_evidence_write_targets": generated_destinations,
        "tracked_generated_evidence_write_targets": tracked_targets,
        "issues": issues,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--json", action="store_true", help="Print machine-readable JSON.")
    args = parser.parse_args(argv)
    result = check_generated_evidence_source_control()
    if args.json:
        print(json.dumps(result, indent=2, sort_keys=True))
    elif result["ok"]:
        print("Generated evidence source-control guard ok")
    else:
        print("Generated evidence source-control guard failed:")
        for issue in result["issues"]:
            print(f"- {issue}")
    return 0 if result["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
