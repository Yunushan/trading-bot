#!/usr/bin/env python3
"""Validate the human QA record required before publishing a tagged release."""

from __future__ import annotations

import argparse
import os
import re
import sys
from datetime import date
from pathlib import Path


REQUIRED_SCENARIOS = (
    "Desktop visual flow",
    "Service API flow",
    "LLM/local-model flow",
    "Release package",
)
REVISION_PATTERN = re.compile(r"^[0-9a-f]{40}$")


def _field(text: str, label: str) -> str:
    match = re.search(rf"(?mi)^-\s*{re.escape(label)}:\s*(.+?)\s*$", text)
    return match.group(1).strip() if match else ""


def validate_release_qa_note(
    note: Path,
    *,
    tag: str,
    source_revision: str = "",
) -> list[str]:
    if not note.is_file():
        return [f"missing release QA note: {note}"]

    text = note.read_text(encoding="utf-8")
    issues: list[str] = []
    if f"# Release QA: {tag}" not in text:
        issues.append(f"QA note must start with the release heading for {tag}")
    if _field(text, "Release tag") != tag:
        issues.append(f"QA note Release tag must equal {tag}")

    completed_on = _field(text, "Completed on")
    try:
        if date.fromisoformat(completed_on) > date.today():
            issues.append("QA note Completed on date cannot be in the future")
    except ValueError:
        issues.append("QA note Completed on must use ISO date format YYYY-MM-DD")

    if not _field(text, "Operator"):
        issues.append("QA note Operator is required")
    if _field(text, "Outcome").lower() != "approved":
        issues.append("QA note Outcome must be approved")

    recorded_revision = _field(text, "Source revision")
    if not REVISION_PATTERN.fullmatch(recorded_revision):
        issues.append("QA note Source revision must be a 40-character lowercase Git commit SHA")
    if source_revision and recorded_revision != source_revision:
        issues.append("QA note Source revision does not match the release source revision")

    for scenario in REQUIRED_SCENARIOS:
        pattern = rf"(?mi)^-\s*\[x\]\s*{re.escape(scenario)}:\s*\S"
        if not re.search(pattern, text):
            issues.append(f"QA note must record a completed {scenario} check")
    return issues


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Validate the versioned manual QA record required before release publication.",
    )
    parser.add_argument("--tag", required=True, help="Release tag, for example v1.2.3.")
    parser.add_argument("--note", type=Path, required=True, help="Path to the release QA Markdown note.")
    parser.add_argument(
        "--require-current-revision",
        action="store_true",
        help="Require Source revision to match the GitHub Actions GITHUB_SHA environment variable.",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    args = _build_parser().parse_args(argv)
    revision = os.environ.get("GITHUB_SHA", "") if args.require_current_revision else ""
    if args.require_current_revision and not REVISION_PATTERN.fullmatch(revision):
        print("error: GITHUB_SHA must contain the 40-character release commit SHA", file=sys.stderr)
        return 2
    issues = validate_release_qa_note(args.note, tag=args.tag, source_revision=revision)
    if issues:
        for issue in issues:
            print(f"error: {issue}", file=sys.stderr)
        return 1
    print(f"release QA note approved: {args.note}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
