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
NATIVE_SIGNING_SCENARIO = "Native signing and notarization"
NATIVE_SIGNING_REQUIRED_SINCE = (1, 0, 41)
PRODUCTION_RUN_EVIDENCE_REQUIRED_SINCE = (1, 0, 41)
PRODUCTION_RUN_BINDINGS = (
    ("Candidate CI", "Candidate CI run ID", "Candidate CI run URL"),
    ("CodeQL", "CodeQL run ID", "CodeQL run URL"),
    (
        "Supply chain security",
        "Supply chain security run ID",
        "Supply chain security run URL",
    ),
)
VERSION_TAG_PATTERN = re.compile(
    r"^v(?P<major>\d+)\.(?P<minor>\d+)\.(?P<patch>\d+)(?:[-+][0-9A-Za-z.-]+)?$"
)
REVISION_PATTERN = re.compile(r"^[0-9a-f]{40}$")
EVIDENCE_RUN_ID_PATTERN = re.compile(r"^[1-9][0-9]*$")
EVIDENCE_RUN_URL_PATTERN = re.compile(
    r"^https://github\.com/(?P<repository>[^/\s]+/[^/\s]+)/actions/runs/"
    r"(?P<run_id>[1-9][0-9]*)/?$"
)
EVIDENCE_SCOPES = ("full", "hosted-only")
BASE_METADATA_FIELDS = (
    "Release tag",
    "Source revision",
    "Completed on",
    "Operator",
    "Outcome",
)
PLATFORM_EVIDENCE_FIELDS = (
    "Release platform evidence run ID",
    "Release platform evidence run URL",
    "Release platform evidence scope",
)


def _required_scenarios(tag: str) -> tuple[str, ...]:
    match = VERSION_TAG_PATTERN.fullmatch(tag)
    if not match:
        return REQUIRED_SCENARIOS
    version = tuple(int(match.group(part)) for part in ("major", "minor", "patch"))
    if version >= NATIVE_SIGNING_REQUIRED_SINCE:
        return (*REQUIRED_SCENARIOS, NATIVE_SIGNING_SCENARIO)
    return REQUIRED_SCENARIOS


def _requires_production_run_evidence(tag: str) -> bool:
    match = VERSION_TAG_PATTERN.fullmatch(tag)
    if not match:
        return False
    version = tuple(int(match.group(part)) for part in ("major", "minor", "patch"))
    return version >= PRODUCTION_RUN_EVIDENCE_REQUIRED_SINCE


def _field(text: str, label: str) -> str:
    match = re.search(rf"(?mi)^-\s*{re.escape(label)}:\s*(.+?)\s*$", text)
    return match.group(1).strip() if match else ""


def _duplicate_metadata_issues(text: str, labels: tuple[str, ...]) -> list[str]:
    issues: list[str] = []
    for label in labels:
        matches = re.findall(rf"(?mi)^-\s*{re.escape(label)}:\s*(.+?)\s*$", text)
        if len(matches) > 1:
            issues.append(f"QA note {label} must appear exactly once")
    return issues


def _validate_run_binding(
    text: str,
    *,
    name: str,
    id_label: str,
    url_label: str,
    repository: str = "",
) -> list[str]:
    issues: list[str] = []
    run_id = _field(text, id_label)
    if not EVIDENCE_RUN_ID_PATTERN.fullmatch(run_id):
        issues.append(f"QA note {id_label} must be a positive GitHub Actions run ID")
    run_url = _field(text, url_label)
    url_match = EVIDENCE_RUN_URL_PATTERN.fullmatch(run_url)
    if not url_match:
        issues.append(f"QA note {url_label} must be a GitHub Actions run URL")
        return issues
    if run_id and url_match.group("run_id") != run_id:
        issues.append(f"QA note {url_label} must reference the recorded run ID")
    if repository and url_match.group("repository").casefold() != repository.casefold():
        issues.append(
            f"QA note {name} run URL must reference the current repository {repository}"
        )
    return issues


def validate_release_qa_note(
    note: Path,
    *,
    tag: str,
    source_revision: str = "",
    require_platform_evidence_run: bool = False,
    repository: str = "",
) -> list[str]:
    if not note.is_file():
        return [f"missing release QA note: {note}"]

    text = note.read_text(encoding="utf-8")
    issues: list[str] = []
    if not VERSION_TAG_PATTERN.fullmatch(tag):
        issues.append(f"release tag must use vMAJOR.MINOR.PATCH form: {tag}")
    first_line = text.splitlines()[0].strip() if text.splitlines() else ""
    if first_line != f"# Release QA: {tag}":
        issues.append(f"QA note must start with the release heading for {tag}")

    metadata_fields = list(BASE_METADATA_FIELDS)
    if require_platform_evidence_run:
        metadata_fields.extend(PLATFORM_EVIDENCE_FIELDS)
    if _requires_production_run_evidence(tag):
        for _, id_label, url_label in PRODUCTION_RUN_BINDINGS:
            metadata_fields.extend((id_label, url_label))
    issues.extend(_duplicate_metadata_issues(text, tuple(metadata_fields)))

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
        issues.append(
            "QA note Source revision must be a 40-character lowercase Git commit SHA"
        )
    if source_revision and recorded_revision != source_revision:
        issues.append(
            "QA note Source revision does not match the release source revision"
        )

    if require_platform_evidence_run:
        issues.extend(
            _validate_run_binding(
                text,
                name="Release platform evidence",
                id_label="Release platform evidence run ID",
                url_label="Release platform evidence run URL",
                repository=repository,
            )
        )
        evidence_scope = _field(text, "Release platform evidence scope")
        if evidence_scope not in EVIDENCE_SCOPES:
            issues.append(
                "QA note Release platform evidence scope must be one of: "
                + ", ".join(EVIDENCE_SCOPES)
            )

    if _requires_production_run_evidence(tag):
        for name, id_label, url_label in PRODUCTION_RUN_BINDINGS:
            issues.extend(
                _validate_run_binding(
                    text,
                    name=name,
                    id_label=id_label,
                    url_label=url_label,
                    repository=repository,
                )
            )

    for scenario in _required_scenarios(tag):
        pattern = rf"(?mi)^-\s*\[x\]\s*{re.escape(scenario)}:\s*\S"
        if not re.search(pattern, text):
            issues.append(f"QA note must record a completed {scenario} check")
    return issues


def _release_qa_parent_revision(
    note: Path, release_revision: str
) -> tuple[str, list[str]]:
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
            [
                "git",
                "diff-tree",
                "--no-commit-id",
                "--name-only",
                "-r",
                release_revision,
            ],
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
    parser.add_argument(
        "--note", type=Path, required=True, help="Path to the release QA Markdown note."
    )
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
    output_group.add_argument(
        "--print-platform-evidence-scope",
        action="store_true",
        help="Print the validated release-platform evidence scope from the QA note.",
    )
    output_group.add_argument(
        "--print-production-run-evidence-required",
        action="store_true",
        help="Print true when exact-source CI and security run evidence is required.",
    )
    output_group.add_argument(
        "--print-candidate-ci-run-id",
        action="store_true",
        help="Print the validated candidate CI workflow run ID.",
    )
    output_group.add_argument(
        "--print-codeql-run-id",
        action="store_true",
        help="Print the validated CodeQL workflow run ID.",
    )
    output_group.add_argument(
        "--print-supply-chain-run-id",
        action="store_true",
        help="Print the validated supply-chain workflow run ID.",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = _build_parser()
    args = parser.parse_args(argv)
    revision = os.environ.get("GITHUB_SHA", "") if args.require_current_revision else ""
    repository = os.environ.get("GITHUB_REPOSITORY", "") if args.require_current_revision else ""
    if args.allow_release_qa_commit and not args.require_current_revision:
        parser.error("--allow-release-qa-commit requires --require-current-revision")
    if (
        args.print_source_revision
        or args.print_platform_evidence_run_id
        or args.print_platform_evidence_scope
        or args.print_production_run_evidence_required
        or args.print_candidate_ci_run_id
        or args.print_codeql_run_id
        or args.print_supply_chain_run_id
    ) and not args.require_current_revision:
        parser.error("print options require --require-current-revision")
    if args.require_current_revision and not REVISION_PATTERN.fullmatch(revision):
        print(
            "error: GITHUB_SHA must contain the 40-character release commit SHA",
            file=sys.stderr,
        )
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
            repository=repository,
        )
    )
    if issues:
        for issue in issues:
            print(f"error: {issue}", file=sys.stderr)
        return 1
    if args.print_source_revision:
        print(revision)
    elif args.print_platform_evidence_run_id:
        print(
            _field(
                args.note.read_text(encoding="utf-8"),
                "Release platform evidence run ID",
            )
        )
    elif args.print_platform_evidence_scope:
        print(
            _field(
                args.note.read_text(encoding="utf-8"), "Release platform evidence scope"
            )
        )
    elif args.print_production_run_evidence_required:
        print("true" if _requires_production_run_evidence(args.tag) else "false")
    elif args.print_candidate_ci_run_id:
        print(_field(args.note.read_text(encoding="utf-8"), "Candidate CI run ID"))
    elif args.print_codeql_run_id:
        print(_field(args.note.read_text(encoding="utf-8"), "CodeQL run ID"))
    elif args.print_supply_chain_run_id:
        print(
            _field(
                args.note.read_text(encoding="utf-8"),
                "Supply chain security run ID",
            )
        )
    else:
        print(f"release QA note approved: {args.note}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
