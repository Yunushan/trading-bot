#!/usr/bin/env python3
"""Validate Rust native runtime evidence workflow contracts.

This is a lightweight structural check, not a replacement for actionlint.
It keeps the evidence/promotion workflows aligned with the promotion model
without requiring a YAML dependency in local verification.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any


WORKFLOWS = {
    "ci_rust_native_gate": ".github/workflows/ci.yml",
    "live_smoke": ".github/workflows/rust-native-live-smoke.yml",
    "release_platform_real_tests": ".github/workflows/release-platform-real-tests.yml",
    "release_evidence": ".github/workflows/rust-native-release-evidence.yml",
    "promotion_audit": ".github/workflows/rust-native-promotion-audit.yml",
}
SOURCE_SYNC_AUDIT_COMMAND = (
    "python tools/audit_native_source_sync.py --json "
    "--output artifacts/native-source-sync/native-source-sync-audit.json"
)
SOURCE_SYNC_AUDIT_FRAGMENTS = (
    "Audit native source sync",
    "mkdir -p artifacts/native-source-sync",
    SOURCE_SYNC_AUDIT_COMMAND,
    "Upload native source sync audit",
    "name: native-source-sync-audit",
    "path: artifacts/native-source-sync/native-source-sync-audit.json",
    "if-no-files-found: warn",
)


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[1]


def _read(root: Path, relative: str) -> str:
    return (root / relative).read_text(encoding="utf-8")


def _missing_fragments(text: str, fragments: tuple[str, ...]) -> list[str]:
    return [fragment for fragment in fragments if fragment not in text]


def _ordered(text: str, fragments: tuple[str, ...]) -> list[str]:
    issues: list[str] = []
    cursor = -1
    for fragment in fragments:
        index = text.find(fragment, cursor + 1)
        if index == -1:
            issues.append(f"missing ordered fragment: {fragment}")
            continue
        if index <= cursor:
            issues.append(f"fragment appears out of order: {fragment}")
        cursor = index
    return issues


def _workflow_result(name: str, path: str, issues: list[str]) -> dict[str, Any]:
    return {
        "name": name,
        "path": path,
        "ok": not issues,
        "issues": issues,
    }


def _check_live_smoke(root: Path) -> dict[str, Any]:
    path = WORKFLOWS["live_smoke"]
    text = _read(root, path)
    issues = _missing_fragments(
        text,
        (
            "workflow_dispatch:",
            "contents: read",
            "uses: actions/setup-python@v6",
            'python-version: "3.14"',
            "BINANCE_API_KEY: ${{ secrets.BINANCE_API_KEY }}",
            "BINANCE_API_SECRET: ${{ secrets.BINANCE_API_SECRET }}",
            'TRADING_BOT_RUST_LIVE_SMOKE: "1"',
            "RUST_NATIVE_RUNTIME_EVIDENCE_DIR: ${{ github.workspace }}/${{ inputs.evidence_dir }}",
            "Validate signed smoke inputs",
            "symbol input is required for Rust native live smoke evidence.",
            "interval input is required for Rust native live smoke evidence.",
            "evidence_dir input is required for Rust native live smoke evidence.",
            *SOURCE_SYNC_AUDIT_FRAGMENTS,
            "Validate Rust native live-smoke preflight",
            "python tools/check_rust_native_live_smoke_preflight.py --json --timeout 180",
            "cargo run -p trading-bot-rust -- --native-live-smoke-preflight",
            "cargo run -p trading-bot-rust -- --native-live-smoke",
            "python tools/check_rust_native_runtime_evidence.py",
            "--require-evidence",
            "--require-current-commit",
            "--require-clean-source",
            "--only rust-native-live-market-data-smoke",
            "--only rust-native-live-account-read-smoke",
            "Write post-smoke Rust native runtime evidence plan",
            "if: ${{ always() }}",
            'mkdir -p "${RUST_NATIVE_RUNTIME_EVIDENCE_DIR}"',
            "--write-evidence-plan",
            "name: rust-native-live-smoke-evidence",
            "rust-native-live-market-data-smoke.json",
            "rust-native-live-account-read-smoke.json",
            "if-no-files-found: error",
            "name: rust-native-live-smoke-evidence-plan",
            "if-no-files-found: warn",
        ),
    )
    issues.extend(
        _ordered(
            text,
            (
                "Set up Python",
                "Validate signed smoke inputs",
                "Audit native source sync",
                "Upload native source sync audit",
                "Validate Rust native live-smoke preflight",
                "Run guarded signed account-read smoke",
                "Validate signed account-read smoke evidence",
                "Write post-smoke Rust native runtime evidence plan",
                "Upload signed account-read smoke evidence",
                "Upload post-smoke Rust native runtime evidence plan",
            ),
        )
    )
    return _workflow_result("live_smoke", path, issues)


def _check_ci_rust_native_gate(root: Path) -> dict[str, Any]:
    path = WORKFLOWS["ci_rust_native_gate"]
    text = _read(root, path)
    issues = _missing_fragments(
        text,
        (
            *SOURCE_SYNC_AUDIT_FRAGMENTS,
            "Check Rust native runtime evidence contract",
            "python tools/check_rust_native_runtime_evidence.py --schema-only",
            "Check Rust native evidence workflow contracts",
            "python tools/check_rust_native_evidence_workflows.py --json",
            "Audit Rust native evidence importer",
            "python tools/import_rust_native_evidence_artifacts.py",
            "artifacts/rust-native-runtime-evidence",
            "release-platform-evidence",
            "artifacts/native-source-sync",
            "--require-current-commit",
            "--require-clean-source",
            "--require-native-source-sync-audit",
            "Audit Rust native runtime promotion readiness",
            "python tools/audit_rust_native_runtime_readiness.py",
            "--write-evidence-plan artifacts/rust-native-runtime-evidence-plan.md",
            "Upload Rust native runtime evidence plan",
            "rust-native-runtime-evidence-plan",
            "Validate Rust native local recovery evidence",
            "python3 tools/check_rust_native_local_recovery_evidence.py --json",
            "Validate Rust native live-smoke preflight",
            "python3 tools/check_rust_native_live_smoke_preflight.py --json",
            "generated evidence source-control guard",
            "python tools/check_generated_evidence_source_control.py --json",
        ),
    )
    issues.extend(
        _ordered(
            text,
            (
                "Audit native source sync",
                "Upload native source sync audit",
                "Check Rust native runtime evidence contract",
                "Check Rust native evidence workflow contracts",
                "Audit Rust native evidence importer",
                "Audit Rust native runtime promotion readiness",
                "Upload Rust native runtime evidence plan",
            ),
        )
    )
    importer_start = text.find("Audit Rust native evidence importer")
    readiness_start = text.find("Audit Rust native runtime promotion readiness")
    if importer_start == -1 or readiness_start == -1 or readiness_start <= importer_start:
        issues.append("CI Rust native importer audit must run before promotion readiness audit")
    else:
        importer_section = text[importer_start:readiness_start]
        for fragment in (
            "artifacts/native-source-sync",
            "--require-current-commit",
            "--require-clean-source",
            "--require-native-source-sync-audit",
        ):
            if fragment not in importer_section:
                issues.append(f"CI Rust native importer audit must use {fragment}")
    return _workflow_result("ci_rust_native_gate", path, issues)


def _check_release_platform_real_tests(root: Path) -> dict[str, Any]:
    path = WORKFLOWS["release_platform_real_tests"]
    text = _read(root, path)
    issues = _missing_fragments(
        text,
        (
            "workflow_dispatch:",
            "target_id:",
            "runner_labels_json:",
            "require_all_evidence:",
            "desktop_smoke_command:",
            "browser_test_command:",
            "contents: read",
            "python tools/check_release_platform_matrix.py --schema-only",
            *SOURCE_SYNC_AUDIT_FRAGMENTS,
            "python tools/run_release_platform_probe.py",
            "--target-id \"${{ inputs.target_id }}\"",
            "--require-native-source-sync",
            "--output \"release-platform-evidence/${{ inputs.target_id }}.json\"",
            "Validate target evidence",
            "python tools/check_release_platform_matrix.py",
            "--require-evidence",
            "--require-current-commit",
            "--require-clean-source",
            "--target-filter \"${{ inputs.target_id }}\"",
            "name: release-platform-evidence-${{ inputs.target_id }}",
            "if-no-files-found: error",
            "Full Evidence Gate",
            "pattern: release-platform-evidence-*",
            "merge-multiple: true",
            "Require passed evidence for every target",
        ),
    )
    issues.extend(
        _ordered(
            text,
            (
                "Validate matrix contract",
                "Audit native source sync",
                "Upload native source sync audit",
                "Run real target probe",
                "Validate target evidence",
                "Upload target evidence",
                "Require passed evidence for every target",
            ),
        )
    )
    issues.extend(
        _ordered(
            text,
            (
                "python tools/run_release_platform_probe.py",
                "--target-id \"${{ inputs.target_id }}\"",
                "--require-clean-source",
                "--require-native-source-sync",
                "--output \"release-platform-evidence/${{ inputs.target_id }}.json\"",
            ),
        )
    )
    for fragment in ("--require-current-commit", "--require-clean-source"):
        if text.count(fragment) < 2:
            issues.append(f"release platform workflow must use {fragment} for target and full evidence validation")
    if text.count("--require-native-source-sync") < 1:
        issues.append("release platform workflow must use --require-native-source-sync for target evidence collection")
    return _workflow_result("release_platform_real_tests", path, issues)


def _check_release_evidence(root: Path) -> dict[str, Any]:
    path = WORKFLOWS["release_evidence"]
    text = _read(root, path)
    issues = _missing_fragments(
        text,
        (
            "workflow_dispatch:",
            "actions: read",
            "contents: read",
            "uses: actions/setup-python@v6",
            'python-version: "3.14"',
            "platform_evidence_run_id",
            "platform_evidence_artifact_pattern",
            "GH_TOKEN: ${{ github.token }}",
            "GITHUB_TOKEN: ${{ github.token }}",
            "RUST_NATIVE_RUNTIME_EVIDENCE_DIR: ${{ github.workspace }}/${{ inputs.evidence_dir }}",
            "Validate release evidence inputs",
            "tag input is required for Rust native release evidence.",
            "platform_evidence_artifact_pattern input is required for Rust native release evidence.",
            "platform_evidence_run_id must be a numeric GitHub Actions run id.",
            "evidence_dir input is required for Rust native release evidence.",
            *SOURCE_SYNC_AUDIT_FRAGMENTS,
            "gh run download",
            "release-platform-evidence",
            "python tools/write_rust_native_release_evidence.py",
            "--preflight",
            "--platform-evidence-dir release-platform-evidence",
            "--output-dir \"${RUST_NATIVE_RUNTIME_EVIDENCE_DIR}\"",
            "python tools/check_rust_native_runtime_evidence.py",
            "--require-evidence",
            "--require-current-commit",
            "--require-clean-source",
            "--only rust-native-release-platform-evidence",
            "Write post-release Rust native runtime evidence plan",
            "if: ${{ always() }}",
            'mkdir -p "${RUST_NATIVE_RUNTIME_EVIDENCE_DIR}"',
            "--write-evidence-plan",
            "name: rust-native-release-platform-evidence",
            "rust-native-release-platform-evidence.json",
            "if-no-files-found: error",
            "name: rust-native-release-platform-evidence-plan",
            "if-no-files-found: warn",
        ),
    )
    issues.extend(
        _ordered(
            text,
            (
                "Set up Python",
                "Validate release evidence inputs",
                "Audit native source sync",
                "Upload native source sync audit",
                "Collect release platform evidence",
                "Preflight Rust native release evidence inputs",
                "Write Rust native release evidence",
                "Validate Rust native release evidence",
                "Write post-release Rust native runtime evidence plan",
                "Upload Rust native release evidence",
                "Upload post-release Rust native runtime evidence plan",
            ),
        )
    )
    return _workflow_result("release_evidence", path, issues)


def _check_promotion_audit(root: Path) -> dict[str, Any]:
    path = WORKFLOWS["promotion_audit"]
    text = _read(root, path)
    issues = _missing_fragments(
        text,
        (
            "workflow_dispatch:",
            "live_smoke_run_id",
            "release_evidence_run_id",
            "actions: read",
            "contents: read",
            "GH_TOKEN: ${{ github.token }}",
            "GITHUB_TOKEN: ${{ github.token }}",
            "LIVE_SMOKE_RUN_ID: ${{ inputs.live_smoke_run_id }}",
            "RELEASE_EVIDENCE_RUN_ID: ${{ inputs.release_evidence_run_id }}",
            "RUST_NATIVE_RUNTIME_EVIDENCE_DIR: ${{ github.workspace }}/${{ inputs.evidence_dir }}",
            "Validate promotion audit inputs",
            "live_smoke_run_id must be a numeric GitHub Actions run id.",
            "release_evidence_run_id must be a numeric GitHub Actions run id.",
            "evidence_dir input is required for Rust native promotion audit.",
            *SOURCE_SYNC_AUDIT_FRAGMENTS,
            'download_dir="${RUST_NATIVE_RUNTIME_EVIDENCE_DIR}/downloads"',
            "--name rust-native-live-smoke-evidence",
            "--name rust-native-release-platform-evidence",
            "python tools/import_rust_native_evidence_artifacts.py",
            '"${RUST_NATIVE_RUNTIME_EVIDENCE_DIR}/downloads"',
            "artifacts/native-source-sync",
            "--apply",
            "--overwrite",
            "--require-current-commit",
            "--require-clean-source",
            "--require-native-source-sync-audit",
            "--require-runtime-id rust-native-live-market-data-smoke",
            "--require-runtime-id rust-native-live-account-read-smoke",
            "--require-runtime-id rust-native-release-platform-evidence",
            "--runtime-evidence-dir \"${RUST_NATIVE_RUNTIME_EVIDENCE_DIR}\"",
            "python tools/check_rust_native_local_recovery_evidence.py",
            "--evidence-dir \"${RUST_NATIVE_RUNTIME_EVIDENCE_DIR}\"",
            "--require-clean-source",
            "--require-native-source-sync",
            "python tools/check_rust_native_runtime_evidence.py",
            "--require-evidence",
            "python tools/audit_rust_native_runtime_readiness.py",
            "--require-ready",
            "Write final Rust native runtime evidence plan",
            "if: ${{ always() }}",
            "--write-evidence-plan",
            "name: rust-native-promotion-evidence-plan",
            "name: rust-native-runtime-promotion-evidence",
            "rust-native-live-market-data-smoke.json",
            "rust-native-live-account-read-smoke.json",
            "rust-native-live-stream-recovery.json",
            "rust-native-order-guard-recovery.json",
            "rust-native-release-platform-evidence.json",
            "native-source-sync-audit.json",
            "if-no-files-found: warn",
        ),
    )
    issues.extend(
        _ordered(
            text,
            (
                "Validate promotion audit inputs",
                "Audit native source sync",
                "Upload native source sync audit",
                "Download external Rust native evidence artifacts",
                "Import external Rust native evidence artifacts",
                "Generate deterministic local recovery evidence for checked commit",
                "Validate complete current-commit runtime evidence",
                "Run strict Rust native runtime promotion readiness audit",
                "Write final Rust native runtime evidence plan",
                "Upload final Rust native runtime evidence plan",
                "Upload normalized Rust native runtime promotion evidence",
            ),
        )
    )
    if "artifacts/rust-native-runtime-evidence/downloads" not in text and (
        '"${RUST_NATIVE_RUNTIME_EVIDENCE_DIR}/downloads"' not in text
    ):
        issues.append("promotion workflow must download artifacts under the ignored runtime evidence directory")
    return _workflow_result("promotion_audit", path, issues)


def check_workflows(root: Path | None = None) -> dict[str, Any]:
    root = root or _repo_root()
    workflow_results = [
        _check_ci_rust_native_gate(root),
        _check_live_smoke(root),
        _check_release_platform_real_tests(root),
        _check_release_evidence(root),
        _check_promotion_audit(root),
    ]
    issues = [
        f"{workflow['path']}: {issue}"
        for workflow in workflow_results
        for issue in workflow["issues"]
    ]
    return {
        "ok": not issues,
        "workflow_count": len(workflow_results),
        "workflows": workflow_results,
        "issues": issues,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--json", action="store_true", help="Print machine-readable JSON.")
    args = parser.parse_args(argv)
    result = check_workflows()
    if args.json:
        print(json.dumps(result, indent=2, sort_keys=True))
    elif result["ok"]:
        print(f"Rust native evidence workflow contracts ok: {result['workflow_count']} workflows")
    else:
        print("Rust native evidence workflow contracts failed")
        for issue in result["issues"]:
            print(f"- {issue}")
    return 0 if result["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
