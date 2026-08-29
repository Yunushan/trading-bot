#!/usr/bin/env python3
"""Validate fail-closed native signing/notarization release workflow contracts."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit


REPO_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_POLICY_PATH = Path("docs/release-signing-policy.json")
REQUIRED_POLICY_FLAGS = (
    "tagged_windows_assets_require_authenticode",
    "tagged_macos_assets_require_developer_id",
    "tagged_macos_assets_require_notarization",
    "macos_app_ticket_must_be_stapled",
    "signatures_precede_digest_manifest_sbom_and_attestation",
    "publication_requires_hash_bound_signing_evidence",
    "workflow_dispatch_builds_are_non_publishable",
    "missing_credentials_fail_closed",
    "secrets_are_step_scoped",
)
WINDOWS_SECRETS = {
    "WINDOWS_CODESIGN_PFX_B64",
    "WINDOWS_CODESIGN_PFX_PASSWORD",
}
MACOS_SECRETS = {
    "MACOS_CODESIGN_P12_B64",
    "MACOS_CODESIGN_P12_PASSWORD",
    "MACOS_CODESIGN_IDENTITY",
    "APPLE_NOTARY_KEY_B64",
    "APPLE_NOTARY_KEY_ID",
    "APPLE_NOTARY_ISSUER_ID",
}
WINDOWS_TIMESTAMP_HOST = "timestamp.digicert.com"


def _load_json(path: Path) -> dict[str, Any]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ValueError(
            f"Unable to load release signing policy {path}: {exc}"
        ) from exc
    if not isinstance(payload, dict):
        raise ValueError("release signing policy must contain a JSON object")
    return payload


def _contains_in_order(text: str, markers: tuple[str, ...]) -> bool:
    cursor = -1
    for marker in markers:
        cursor = text.find(marker, cursor + 1)
        if cursor < 0:
            return False
    return True


def _is_exact_timestamp_url(value: object) -> bool:
    """Validate the timestamp endpoint by parsed URL components, not substrings."""
    try:
        parsed = urlsplit(str(value or "").strip())
        hostname = parsed.hostname
        port = parsed.port
    except ValueError:
        return False
    return (
        parsed.scheme.lower() == "http"
        and hostname == WINDOWS_TIMESTAMP_HOST
        and parsed.username is None
        and parsed.password is None
        and port is None
        and parsed.path == ""
        and not parsed.query
        and not parsed.fragment
    )


def audit_policy(
    root: Path | None = None, *, policy_path: Path | None = None
) -> dict[str, Any]:
    repo_root = (root or REPO_ROOT).resolve()
    resolved_policy = policy_path or (repo_root / DEFAULT_POLICY_PATH)
    policy = _load_json(resolved_policy)
    checks: dict[str, bool] = {}
    issues: list[str] = []

    def check(name: str, condition: object, message: str) -> None:
        passed = bool(condition)
        checks[name] = passed
        if not passed:
            issues.append(message)

    check(
        "schema_version", policy.get("schema_version") == 1, "schema_version must be 1"
    )
    check(
        "enforcement_version",
        policy.get("enforcement_since") == "v1.0.41",
        "enforcement_since must be v1.0.41",
    )
    policy_flags = (
        policy.get("policy") if isinstance(policy.get("policy"), dict) else {}
    )
    for flag in REQUIRED_POLICY_FLAGS:
        check(
            f"policy_{flag}",
            policy_flags.get(flag) is True,
            f"policy.{flag} must be true",
        )

    windows_policy = (
        policy.get("windows") if isinstance(policy.get("windows"), dict) else {}
    )
    macos_policy = policy.get("macos") if isinstance(policy.get("macos"), dict) else {}
    check(
        "windows_targets",
        windows_policy.get("targets") == ["windows-x64", "windows-arm64"],
        "Windows signing targets must be x64 and ARM64",
    )
    check(
        "windows_crypto",
        windows_policy.get("method") == "authenticode"
        and windows_policy.get("digest_algorithm") == "sha256"
        and windows_policy.get("timestamp_protocol") == "rfc3161"
        and _is_exact_timestamp_url(windows_policy.get("timestamp_url")),
        "Windows policy must require SHA-256 Authenticode with RFC 3161 timestamping",
    )
    check(
        "windows_secrets",
        set(windows_policy.get("required_secret_names") or []) == WINDOWS_SECRETS,
        "Windows policy must declare only the reviewed signing secret names",
    )
    check(
        "macos_targets",
        macos_policy.get("targets")
        == ["macos-14-arm64", "macos-15-intel", "macos-15-arm64", "macos-26-arm64"],
        "macOS signing targets must match the release matrix",
    )
    check(
        "macos_crypto",
        macos_policy.get("method") == "developer-id-application"
        and macos_policy.get("hardened_runtime") is True
        and macos_policy.get("secure_timestamp") is True
        and macos_policy.get("notarization_tool") == "notarytool",
        "macOS policy must require Developer ID, Hardened Runtime, timestamps, and notarytool",
    )
    check(
        "macos_secrets",
        set(macos_policy.get("required_secret_names") or []) == MACOS_SECRETS,
        "macOS policy must declare only the reviewed signing/notarization secret names",
    )

    windows_workflow = (repo_root / ".github/workflows/release-windows.yml").read_text(
        encoding="utf-8"
    )
    macos_workflow = (
        repo_root / ".github/workflows/release-linux-macos.yml"
    ).read_text(encoding="utf-8")
    check(
        "windows_tag_gate",
        "Authenticode-sign required Windows release binaries" in windows_workflow
        and "if: github.ref_type == 'tag'" in windows_workflow
        and "tools/Sign-WindowsReleaseBinaries.ps1" in windows_workflow,
        "Windows tagged builds must invoke the Authenticode signer",
    )
    check(
        "windows_secret_scope",
        all(
            f"{name}: ${{{{ secrets.{name} }}}}" in windows_workflow
            for name in WINDOWS_SECRETS
        )
        and "secrets." not in windows_workflow.split("    steps:", 1)[0],
        "Windows signing credentials must be referenced only by a step",
    )
    check(
        "windows_order",
        _contains_in_order(
            windows_workflow,
            (
                "Package release assets",
                "Authenticode-sign required Windows release binaries",
                "Smoke packaged native binaries",
                "Write and verify artifact digest manifest",
                "Generate SPDX SBOM for release assets",
                "Attest release asset provenance",
            ),
        ),
        "Windows signing must precede smoke, digest, SBOM, and attestation",
    )
    check(
        "windows_publish_gate",
        windows_workflow.count("release-signing-windows-*.json") >= 3
        and "--require-complete-platform-set windows" in windows_workflow
        and _contains_in_order(
            windows_workflow.split("  publish-release:", 1)[1],
            (
                "Download built assets",
                "check_release_signing_evidence.py",
                "Publish GitHub release",
            ),
        ),
        "Windows publication must verify two downloaded signing evidence files",
    )

    macos_tag_condition = "if: runner.os == 'macOS' && github.ref_type == 'tag'"
    check(
        "macos_tag_gates",
        macos_workflow.count(macos_tag_condition) >= 3
        and "tools/sign_macos_release.sh" in macos_workflow
        and macos_workflow.count("tools/notarize_macos_release.sh") >= 2,
        "macOS tagged builds must sign, notarize/staple the app, and notarize archives",
    )
    check(
        "macos_secret_scope",
        all(
            f"{name}: ${{{{ secrets.{name} }}}}" in macos_workflow
            for name in MACOS_SECRETS
        )
        and "secrets." not in macos_workflow.split("    steps:", 1)[0],
        "macOS signing credentials must be referenced only by signing/notarization steps",
    )
    check(
        "macos_order",
        _contains_in_order(
            macos_workflow,
            (
                "Deploy macOS Qt frameworks",
                "Developer ID-sign required macOS release binaries",
                "Notarize and staple the macOS C++ app bundle",
                "Smoke packaged native binaries",
                "Package release assets",
                "Notarize final macOS release archives",
                "Write and verify artifact digest manifest",
                "Generate SPDX SBOM for release assets",
                "Attest release asset provenance",
            ),
        ),
        "macOS signing/notarization must precede digest, SBOM, and attestation",
    )
    check(
        "macos_publish_gate",
        macos_workflow.count("release-signing-macos-*.json") >= 2
        and 'if [[ "$signing_count" -ne 4 ]]' in macos_workflow
        and "--require-complete-platform-set macos" in macos_workflow
        and _contains_in_order(
            macos_workflow.split("  publish-release:", 1)[1],
            (
                "Download built assets",
                "check_release_signing_evidence.py",
                "Publish GitHub release assets",
            ),
        ),
        "macOS publication must verify four downloaded signing evidence files",
    )

    windows_script = (repo_root / "tools/Sign-WindowsReleaseBinaries.ps1").read_text(
        encoding="utf-8"
    )
    macos_sign_script = (repo_root / "tools/sign_macos_release.sh").read_text(
        encoding="utf-8"
    )
    macos_notary_script = (repo_root / "tools/notarize_macos_release.sh").read_text(
        encoding="utf-8"
    )
    check(
        "windows_script_hardening",
        all(
            marker in windows_script
            for marker in (
                "/fd",
                "SHA256",
                "/tr",
                "/td",
                '"verify", "/pa", "/all"',
                "Get-AuthenticodeSignature",
                "finally",
            )
        ),
        "Windows signer must use SHA-256, RFC 3161, platform verification, and cleanup",
    )
    check(
        "macos_script_hardening",
        all(
            marker in macos_sign_script
            for marker in (
                "-sign-for-notarization=",
                "--options runtime",
                "--timestamp",
                "--verify --deep --strict",
                "get-task-allow",
                "delete-keychain",
            )
        ),
        "macOS signer must use Qt nested signing, Hardened Runtime, timestamps, strict verification, and cleanup",
    )
    check(
        "notary_script_hardening",
        all(
            marker in macos_notary_script
            for marker in (
                "notarytool submit",
                "--wait",
                "notarytool log",
                "stapler staple",
                "stapler validate",
                "APPLE_NOTARY_KEY_B64",
            )
        ),
        "macOS notarizer must wait, inspect logs, staple/validate, and use API-key credentials",
    )
    evidence_writer = (repo_root / "tools/write_release_signing_evidence.py").read_text(
        encoding="utf-8"
    )
    evidence_checker = (
        repo_root / "tools/check_release_signing_evidence.py"
    ).read_text(encoding="utf-8")
    check(
        "hash_bound_evidence",
        "archive_sha256" in evidence_writer
        and "secrets_redacted" in evidence_writer
        and "signed artifact hash mismatch" in evidence_checker
        and "signed {family} binary hash is not present" in evidence_checker
        and "duplicate signing evidence targets" in evidence_checker
        and "source_revision must match the current Git revision" in evidence_checker,
        "signing evidence must be secret-free, hash-bound, and commit-bound",
    )

    release_assets = (repo_root / "tools/check_release_assets.py").read_text(
        encoding="utf-8"
    )
    release_qa = (repo_root / "tools/check_release_qa.py").read_text(encoding="utf-8")
    qa_template = (repo_root / "docs/release-qa/TEMPLATE.md").read_text(
        encoding="utf-8"
    )
    release_docs = (repo_root / "docs/RELEASES.md").read_text(encoding="utf-8")
    check(
        "release_asset_gate",
        "NATIVE_SIGNING_REQUIRED_SINCE = (1, 0, 41)" in release_assets
        and "release-signing-{release_id}.json" in release_assets,
        "release asset verifier must require native signing evidence from v1.0.41",
    )
    check(
        "qa_and_runbook",
        "Native signing and notarization" in release_qa
        and "Native signing and notarization" in qa_template
        and "WINDOWS_CODESIGN_PFX_B64" in release_docs
        and "APPLE_NOTARY_KEY_B64" in release_docs,
        "release QA and release guide must document the native trust gate and credential names",
    )

    verify_all = (repo_root / "tools/verify_all.py").read_text(encoding="utf-8")
    ci_workflow = (repo_root / ".github/workflows/ci.yml").read_text(encoding="utf-8")
    check(
        "authoritative_verifiers",
        "tools/check_release_signing_policy.py" in verify_all
        and "tools/check_release_signing_policy.py" in ci_workflow,
        "local verification and CI must run the release signing policy checker",
    )
    return {
        "ok": not issues,
        "policy": str(resolved_policy),
        "enforcement_since": policy.get("enforcement_since"),
        "checks": checks,
        "issues": issues,
        "external_credentials_configured": None,
        "external_signing_evidence_collected": False,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--policy", type=Path, default=REPO_ROOT / DEFAULT_POLICY_PATH)
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args(argv)
    try:
        report = audit_policy(policy_path=args.policy)
    except ValueError as exc:
        report = {"ok": False, "issues": [str(exc)]}
    if args.json:
        print(json.dumps(report, indent=2, sort_keys=True))
    else:
        print(f"Release signing policy: {'passed' if report.get('ok') else 'failed'}")
        for issue in report.get("issues", []):
            print(f"- {issue}")
    return 0 if report.get("ok") else 1


if __name__ == "__main__":
    raise SystemExit(main())
