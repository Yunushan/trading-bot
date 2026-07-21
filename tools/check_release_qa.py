#!/usr/bin/env python3
"""Validate the human QA record required before publishing a tagged release."""

from __future__ import annotations

import argparse
import os
import re
import subprocess
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
EVIDENCE_RUN_ID_PATTERN = re.compile(r"^[1-9][0-9]*$")


def _field(text: str, label: str) -> str:
    match = re.search(rf"(?mi)^-\s*{re.escape(label)}:\s*(.+?)\s*$", text)
    return match.group(1).strip() if match else ""


def validate_release_qa_note(
    note: Path,
    *,
    tag: str,
    source_revision: str = "",
    require_platform_evidence_run: bool = False,
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

    if require_platform_evidence_run:
        evidence_run_id = _field(text, "Release platform evidence run ID")
        if not EVIDENCE_RUN_ID_PATTERN.fullmatch(evidence_run_id):
            issues.append("QA note Release platform evidence run ID must be a positive GitHub Actions run ID")

    for scenario in REQUIRED_SCENARIOS:
        pattern = rf"(?mi)^-\s*\[x\]\s*{re.escape(scenario)}:\s*\S"
        if not re.search(pattern, text):
            issues.append(f"QA note must record a completed {scenario} check")
    return issues


def _release_qa_parent_revision(note: Path, release_revision: str) -> tuple[str, list[str]]:
    """Return the tested parent revision for a metadata-only tagged QA commit."""

    try:
        repository = Path(
            subprocess.run(
                ["git", "rev-parse", "--show-toplevel"],
                check=True,
                capture_output=True,
                text=True,
            ).stdout.strip()
        ).resolve()
        relative_note = note.resolve().relative_to(repository).as_posix()
        parent = subprocess.run(
            ["git", "rev-parse", f"{release_revision}^"],
            check=True,
            capture_output=True,
            text=True,
        ).stdout.strip()
        changed_files = subprocess.run(
            ["git", "diff-tree", "--no-commit-id", "--name-only", "-r", release_revision],
            check=True,
            capture_output=True,
            text=True,
        ).stdout.splitlines()
    except (OSError, subprocess.CalledProcessError) as error:
        return "", [f"could not inspect tagged release QA commit: {error}"]

    if changed_files != [relative_note]:
        return "", [
            "a release QA metadata commit must change only its versioned QA note "
            f"({relative_note}); found: {', '.join(changed_files) or '<none>'}"
        ]
    return parent, []


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
    parser.add_argument(
        "--allow-release-qa-commit",
        action="store_true",
        help=(
            "Allow a tag to target a metadata-only QA commit whose note records its "
            "immediately preceding tested product revision."
        ),
    )
    parser.add_argument(
        "--require-platform-evidence-run",
        action="store_true",
        help="Require the QA note to name the GitHub Actions run containing current release-platform evidence.",
    )
    output_group = parser.add_mutually_exclusive_group()
    output_group.add_argument(
        "--print-source-revision",
        action="store_true",
        help="Print the validated product source revision used by the release QA note.",
    )
    output_group.add_argument(
        "--print-platform-evidence-run-id",
        action="store_true",
        help="Print the validated release-platform evidence workflow run ID from the QA note.",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = _build_parser()
    args = parser.parse_args(argv)
    revision = os.environ.get("GITHUB_SHA", "") if args.require_current_revision else ""
    if args.allow_release_qa_commit and not args.require_current_revision:
        parser.error("--allow-release-qa-commit requires --require-current-revision")
    if (args.print_source_revision or args.print_platform_evidence_run_id) and not args.require_current_revision:
        parser.error("print options require --require-current-revision")
    if args.require_current_revision and not REVISION_PATTERN.fullmatch(revision):
        print("error: GITHUB_SHA must contain the 40-character release commit SHA", file=sys.stderr)
        return 2
    issues: list[str] = []
    if args.allow_release_qa_commit:
        revision, metadata_issues = _release_qa_parent_revision(args.note, revision)
        issues.extend(metadata_issues)
    issues.extend(
        validate_release_qa_note(
            args.note,
            tag=args.tag,
            source_revision=revision,
            require_platform_evidence_run=args.require_platform_evidence_run,
        )
    )
    if issues:
        for issue in issues:
            print(f"error: {issue}", file=sys.stderr)
        return 1
    if args.print_source_revision:
        print(revision)
    elif args.print_platform_evidence_run_id:
        print(_field(args.note.read_text(encoding="utf-8"), "Release platform evidence run ID"))
    else:
        print(f"release QA note approved: {args.note}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
