#!/usr/bin/env python3
"""Validate GitHub Actions run metadata bound to a release source revision."""

from __future__ import annotations

import argparse
import json
import re
import sys
from collections.abc import Mapping
from pathlib import Path
from typing import Any


REVISION_PATTERN = re.compile(r"^[0-9a-f]{40}$")
REPOSITORY_PATTERN = re.compile(r"^[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+$")
MAX_METADATA_BYTES = 4 * 1024 * 1024


def _workflow_file(value: object) -> str:
    """Return the workflow path without GitHub's optional ``@ref`` suffix."""

    path = str(value or "").strip()
    return path.split("@", 1)[0]


def validate_workflow_run(
    payload: Mapping[str, Any],
    *,
    expected_run_id: int,
    expected_repository: str,
    expected_head_sha: str,
    expected_workflow_path: str,
) -> list[str]:
    """Return fail-closed issues for one fetched Actions workflow run."""

    issues: list[str] = []
    if payload.get("id") != expected_run_id:
        issues.append(
            f"workflow run id {payload.get('id')!r} does not match expected {expected_run_id}"
        )

    repository = payload.get("repository")
    actual_repository = (
        str(repository.get("full_name") or "").strip()
        if isinstance(repository, Mapping)
        else ""
    )
    if actual_repository.casefold() != expected_repository.casefold():
        issues.append(
            f"workflow run repository {actual_repository!r} does not match expected "
            f"{expected_repository!r}"
        )

    actual_head_sha = str(payload.get("head_sha") or "").strip()
    if actual_head_sha != expected_head_sha:
        issues.append(
            f"workflow run head SHA {actual_head_sha!r} does not match release source "
            f"{expected_head_sha!r}"
        )

    actual_workflow_path = _workflow_file(payload.get("path"))
    if actual_workflow_path != expected_workflow_path:
        issues.append(
            f"workflow run path {actual_workflow_path!r} does not match expected "
            f"{expected_workflow_path!r}"
        )

    status = str(payload.get("status") or "").strip().lower()
    if status != "completed":
        issues.append(f"workflow run status must be 'completed', found {status!r}")
    conclusion = str(payload.get("conclusion") or "").strip().lower()
    if conclusion != "success":
        issues.append(f"workflow run conclusion must be 'success', found {conclusion!r}")
    return issues


def _decode_metadata(raw: str, *, source: str) -> Mapping[str, Any]:
    if len(raw.encode("utf-8")) > MAX_METADATA_BYTES:
        raise ValueError(
            f"workflow run metadata exceeds {MAX_METADATA_BYTES} bytes: {source}"
        )
    try:
        payload = json.loads(raw)
    except json.JSONDecodeError as error:
        raise ValueError(f"could not read workflow run metadata {source}: {error}") from error
    if not isinstance(payload, Mapping):
        raise ValueError("workflow run metadata must be a JSON object")
    return payload


def _read_metadata(source: str) -> Mapping[str, Any]:
    if source == "-":
        return _decode_metadata(sys.stdin.read(MAX_METADATA_BYTES + 1), source="stdin")
    path = Path(source)
    try:
        size = path.stat().st_size
    except OSError as error:
        raise ValueError(f"could not inspect workflow run metadata {path}: {error}") from error
    if size > MAX_METADATA_BYTES:
        raise ValueError(
            f"workflow run metadata exceeds {MAX_METADATA_BYTES} bytes: {path}"
        )
    try:
        raw = path.read_text(encoding="utf-8")
    except (OSError, UnicodeError) as error:
        raise ValueError(f"could not read workflow run metadata {path}: {error}") from error
    return _decode_metadata(raw, source=str(path))


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "metadata",
        help="GitHub workflow run JSON metadata path, or - to read standard input.",
    )
    parser.add_argument("--expected-run-id", type=int, required=True)
    parser.add_argument("--expected-repository", required=True)
    parser.add_argument("--expected-head-sha", required=True)
    parser.add_argument("--expected-workflow-path", required=True)
    parser.add_argument("--json", action="store_true")
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = _build_parser()
    args = parser.parse_args(argv)
    if args.expected_run_id <= 0:
        parser.error("--expected-run-id must be positive")
    if not REPOSITORY_PATTERN.fullmatch(args.expected_repository):
        parser.error("--expected-repository must use owner/name form")
    if not REVISION_PATTERN.fullmatch(args.expected_head_sha):
        parser.error("--expected-head-sha must be a lowercase 40-character commit SHA")
    if not args.expected_workflow_path.startswith(".github/workflows/"):
        parser.error("--expected-workflow-path must be under .github/workflows/")

    issues: list[str] = []
    try:
        payload = _read_metadata(args.metadata)
    except ValueError as error:
        payload = {}
        issues.append(str(error))
    if not issues:
        issues.extend(
            validate_workflow_run(
                payload,
                expected_run_id=args.expected_run_id,
                expected_repository=args.expected_repository,
                expected_head_sha=args.expected_head_sha,
                expected_workflow_path=args.expected_workflow_path,
            )
        )

    report = {
        "ok": not issues,
        "metadata": str(args.metadata),
        "expected_run_id": args.expected_run_id,
        "expected_repository": args.expected_repository,
        "expected_head_sha": args.expected_head_sha,
        "expected_workflow_path": args.expected_workflow_path,
        "issues": issues,
    }
    if args.json:
        print(json.dumps(report, indent=2, sort_keys=True))
    elif issues:
        print("release workflow run: rejected")
        for issue in issues:
            print(f"- {issue}")
    else:
        print(
            "release workflow run: approved "
            f"({args.expected_workflow_path}, run {args.expected_run_id})"
        )
    return 1 if issues else 0


if __name__ == "__main__":
    raise SystemExit(main())
