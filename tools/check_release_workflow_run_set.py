#!/usr/bin/env python3
"""Require a successful exact-source packaging workflow run in an Actions run list."""

from __future__ import annotations

import argparse
import json
import sys
from collections.abc import Mapping
from pathlib import Path
from typing import Any

import check_release_workflow_run


MAX_METADATA_BYTES = 8 * 1024 * 1024
ALLOWED_RELEASE_EVENTS = {"push", "workflow_dispatch"}


def validate_workflow_run_set(
    payload: Mapping[str, Any],
    *,
    expected_repository: str,
    expected_head_sha: str,
    expected_workflow_path: str,
) -> tuple[list[int], list[str]]:
    """Return approved run IDs and fail-closed aggregate issues."""

    rows = payload.get("workflow_runs")
    if not isinstance(rows, list):
        return [], ["workflow run list metadata must contain workflow_runs"]

    approved: list[int] = []
    rejected_details: list[str] = []
    for index, row in enumerate(rows):
        if not isinstance(row, Mapping):
            rejected_details.append(f"workflow_runs[{index}] is not an object")
            continue
        run_id = row.get("id")
        if isinstance(run_id, bool) or not isinstance(run_id, int) or run_id <= 0:
            rejected_details.append(f"workflow_runs[{index}] has no positive run id")
            continue
        issues = check_release_workflow_run.validate_workflow_run(
            row,
            expected_run_id=run_id,
            expected_repository=expected_repository,
            expected_head_sha=expected_head_sha,
            expected_workflow_path=expected_workflow_path,
        )
        event = str(row.get("event") or "").strip()
        if event not in ALLOWED_RELEASE_EVENTS:
            issues.append(
                f"workflow run event {event!r} must be push or workflow_dispatch"
            )
        if issues:
            if len(rejected_details) < 10:
                rejected_details.append(f"run {run_id}: {'; '.join(issues)}")
            continue
        approved.append(run_id)

    if approved:
        return sorted(set(approved)), []
    issues = [
        "no completed successful exact-source packaging workflow run was found "
        f"for {expected_workflow_path}"
    ]
    issues.extend(rejected_details)
    return [], issues


def _read_payload(source: str) -> Mapping[str, Any]:
    if source == "-":
        raw = sys.stdin.buffer.read(MAX_METADATA_BYTES + 1)
        label = "stdin"
    else:
        path = Path(source)
        try:
            raw = path.read_bytes()
        except OSError as error:
            raise ValueError(f"could not read workflow run list {path}: {error}") from error
        label = str(path)
    if len(raw) > MAX_METADATA_BYTES:
        raise ValueError(f"workflow run list exceeds {MAX_METADATA_BYTES} bytes: {label}")
    try:
        payload = json.loads(raw.decode("utf-8"))
    except (UnicodeError, json.JSONDecodeError) as error:
        raise ValueError(f"could not decode workflow run list {label}: {error}") from error
    if not isinstance(payload, Mapping):
        raise ValueError("workflow run list metadata must be a JSON object")
    return payload


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("metadata", help="Workflow run list JSON path, or - for stdin.")
    parser.add_argument("--expected-repository", required=True)
    parser.add_argument("--expected-head-sha", required=True)
    parser.add_argument("--expected-workflow-path", required=True)
    parser.add_argument("--json", action="store_true")
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = _build_parser()
    args = parser.parse_args(argv)
    if not check_release_workflow_run.REPOSITORY_PATTERN.fullmatch(
        args.expected_repository
    ):
        parser.error("--expected-repository must use owner/name form")
    if not check_release_workflow_run.REVISION_PATTERN.fullmatch(args.expected_head_sha):
        parser.error("--expected-head-sha must be a lowercase 40-character commit SHA")
    if not args.expected_workflow_path.startswith(".github/workflows/"):
        parser.error("--expected-workflow-path must be under .github/workflows/")

    issues: list[str] = []
    approved: list[int] = []
    try:
        payload = _read_payload(args.metadata)
    except ValueError as error:
        payload = {}
        issues.append(str(error))
    if not issues:
        approved, issues = validate_workflow_run_set(
            payload,
            expected_repository=args.expected_repository,
            expected_head_sha=args.expected_head_sha,
            expected_workflow_path=args.expected_workflow_path,
        )

    report = {
        "ok": not issues,
        "expected_repository": args.expected_repository,
        "expected_head_sha": args.expected_head_sha,
        "expected_workflow_path": args.expected_workflow_path,
        "approved_run_ids": approved,
        "issues": issues,
    }
    if args.json:
        print(json.dumps(report, indent=2, sort_keys=True))
    elif issues:
        print("release packaging workflow runs: rejected")
        for issue in issues:
            print(f"- {issue}")
    else:
        print(
            "release packaging workflow runs: approved "
            f"({args.expected_workflow_path}, runs {approved})"
        )
    return 1 if issues else 0


if __name__ == "__main__":
    raise SystemExit(main())
