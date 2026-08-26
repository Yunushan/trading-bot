#!/usr/bin/env python3
"""Verify native release signing evidence and its exact asset hashes."""

from __future__ import annotations

import argparse
from collections import Counter
import hashlib
import json
import re
import stat
import subprocess
from datetime import datetime
from pathlib import Path, PurePosixPath
from typing import Any
import zipfile


COMMIT_PATTERN = re.compile(r"[0-9a-f]{40}")
SHA256_PATTERN = re.compile(r"[0-9a-f]{64}")
SECRET_KEY_FRAGMENTS = (
    "password",
    "private_key",
    "private-key",
    "pfx",
    "p12",
    "base64",
    "api_token",
    "authorization",
)
TARGET_IDS = {
    "windows": ("windows-x64", "windows-arm64"),
    "macos": ("macos-14-arm64", "macos-15-intel", "macos-15-arm64", "macos-26-arm64"),
}
MAX_ZIP_MEMBER_BYTES = 2 * 1024 * 1024 * 1024
MAX_ZIP_TOTAL_BYTES = 4 * 1024 * 1024 * 1024


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _current_revision(repo_root: Path) -> str:
    result = subprocess.run(
        ["git", "rev-parse", "HEAD"],
        cwd=repo_root,
        capture_output=True,
        text=True,
        check=False,
        timeout=15,
    )
    return result.stdout.strip().lower() if result.returncode == 0 else ""


def _asset_patterns(
    platform_name: str, target_id: str
) -> tuple[tuple[str, re.Pattern[str]], ...]:
    escaped_target = re.escape(target_id)
    extension = "exe" if platform_name == "windows" else "zip"
    return (
        ("python", re.compile(rf"Trading-Bot-Python-{escaped_target}-.+\.{extension}")),
        ("rust", re.compile(rf"Trading-Bot-Rust-{escaped_target}-.+\.{extension}")),
        (
            "tauri",
            re.compile(rf"Trading-Bot-Rust-tauri-{escaped_target}-.+\.{extension}"),
        ),
        ("cpp", re.compile(rf"Trading-Bot-C\+\+-{escaped_target}-.+\.zip")),
    )


def _zip_member_hashes(path: Path) -> Counter[str]:
    hashes: Counter[str] = Counter()
    seen_names: set[str] = set()
    total_size = 0
    try:
        with zipfile.ZipFile(path) as archive:
            for member in archive.infolist():
                normalized_name = member.filename.replace("\\", "/")
                member_path = PurePosixPath(normalized_name)
                if (
                    member_path.is_absolute()
                    or ".." in member_path.parts
                    or normalized_name in seen_names
                ):
                    raise ValueError(
                        f"unsafe or duplicate ZIP member: {member.filename}"
                    )
                seen_names.add(normalized_name)
                if member.is_dir():
                    continue
                unix_mode = (member.external_attr >> 16) & 0xFFFF
                if unix_mode and stat.S_ISLNK(unix_mode):
                    raise ValueError(
                        f"ZIP member must not be a symbolic link: {member.filename}"
                    )
                if member.file_size > MAX_ZIP_MEMBER_BYTES:
                    raise ValueError(
                        f"ZIP member exceeds the 2 GiB verification limit: {member.filename}"
                    )
                total_size += member.file_size
                if total_size > MAX_ZIP_TOTAL_BYTES:
                    raise ValueError("ZIP contents exceed the 4 GiB verification limit")
                digest = hashlib.sha256()
                with archive.open(member) as handle:
                    for chunk in iter(lambda: handle.read(1024 * 1024), b""):
                        digest.update(chunk)
                hashes[digest.hexdigest()] += 1
    except (OSError, zipfile.BadZipFile, RuntimeError) as exc:
        raise ValueError(f"unable to inspect ZIP archive: {exc}") from exc
    return hashes


def _secret_issues(value: object, *, path: str = "evidence") -> list[str]:
    issues: list[str] = []
    if isinstance(value, dict):
        for key, item in value.items():
            normalized_key = str(key).lower()
            if any(fragment in normalized_key for fragment in SECRET_KEY_FRAGMENTS):
                issues.append(f"{path}.{key} is a forbidden secret-bearing field")
            issues.extend(_secret_issues(item, path=f"{path}.{key}"))
    elif isinstance(value, list):
        for index, item in enumerate(value):
            issues.extend(_secret_issues(item, path=f"{path}[{index}]"))
    elif (
        isinstance(value, str) and "-----BEGIN" in value and "PRIVATE KEY-----" in value
    ):
        issues.append(f"{path} contains private-key material")
    return issues


def validate_evidence(
    payload: dict[str, Any],
    *,
    evidence_path: Path,
    asset_dir: Path,
    expected_revision: str = "",
) -> list[str]:
    issues: list[str] = _secret_issues(payload)
    if payload.get("schema_version") != 1:
        issues.append("schema_version must be 1")
    if payload.get("status") != "pass":
        issues.append("status must be pass")
    if payload.get("secrets_redacted") is not True:
        issues.append("secrets_redacted must be true")
    platform_name = str(payload.get("platform") or "").strip().lower()
    target_id = str(payload.get("target_id") or "").strip().lower()
    platform_valid = platform_name in TARGET_IDS
    if not platform_valid:
        issues.append("platform must be windows or macos")
    elif target_id not in TARGET_IDS[platform_name]:
        issues.append(
            "target_id must be an exact release signing target for the platform"
        )
    elif evidence_path.name != f"release-signing-{target_id}.json":
        issues.append("evidence filename must match target_id")
    revision = str(payload.get("source_revision") or "").strip().lower()
    if not COMMIT_PATTERN.fullmatch(revision):
        issues.append("source_revision must be a full lowercase Git commit")
    if expected_revision and revision != expected_revision:
        issues.append("source_revision must match the current Git revision")
    generated_at = str(payload.get("generated_at") or "").strip()
    try:
        timestamp = datetime.fromisoformat(generated_at.replace("Z", "+00:00"))
    except ValueError:
        timestamp = None
    if timestamp is None or timestamp.tzinfo is None:
        issues.append("generated_at must be a timezone-aware ISO timestamp")

    signing = payload.get("signing") if isinstance(payload.get("signing"), dict) else {}
    expected_method = (
        "authenticode" if platform_name == "windows" else "developer-id-application"
    )
    if signing.get("method") != expected_method:
        issues.append(f"signing.method must be {expected_method}")
    if signing.get("digest_algorithm") != "sha256":
        issues.append("signing.digest_algorithm must be sha256")
    if signing.get("secure_timestamp") is not True:
        issues.append("signing.secure_timestamp must be true")
    if signing.get("verification") != "valid":
        issues.append("signing.verification must be valid")
    if platform_name == "macos" and signing.get("hardened_runtime") is not True:
        issues.append("macOS signing must enable hardened runtime")

    signature_targets = payload.get("signature_targets")
    signature_rows: dict[str, dict[str, Any]] = {}
    if not isinstance(signature_targets, list) or len(signature_targets) != 4:
        issues.append("signature_targets must contain exactly four entries")
    else:
        for index, item in enumerate(signature_targets):
            if not isinstance(item, dict):
                issues.append(f"signature_targets[{index}] must be an object")
                continue
            name = str(item.get("name") or "")
            if not name or Path(name).name != name:
                issues.append(f"signature_targets[{index}].name must be a basename")
            elif name in signature_rows:
                issues.append(f"duplicate signature target name: {name}")
            else:
                signature_rows[name] = item
            if item.get("verification") != "valid":
                issues.append(f"signature_targets[{index}].verification must be valid")
            if not SHA256_PATTERN.fullmatch(str(item.get("sha256") or "")):
                issues.append(
                    f"signature_targets[{index}].sha256 must be lowercase SHA-256"
                )

    assets = payload.get("artifacts")
    artifact_names: list[str] = []
    artifact_digests: dict[str, str] = {}
    artifact_paths: dict[str, Path] = {}
    if not isinstance(assets, list) or len(assets) != 4:
        issues.append("artifacts must contain exactly four entries")
    else:
        for index, item in enumerate(assets):
            if not isinstance(item, dict):
                issues.append(f"artifacts[{index}] must be an object")
                continue
            name = str(item.get("name") or "")
            digest = str(item.get("sha256") or "")
            if Path(name).name != name or not name:
                issues.append(f"artifacts[{index}].name must be a basename")
                continue
            if name in artifact_names:
                issues.append(f"duplicate artifact name: {name}")
                continue
            artifact_names.append(name)
            if not SHA256_PATTERN.fullmatch(digest):
                issues.append(f"artifacts[{index}].sha256 must be lowercase SHA-256")
                continue
            artifact_path = asset_dir / name
            artifact_digests[name] = digest
            if not artifact_path.is_file() or artifact_path.is_symlink():
                issues.append(f"signed artifact is missing: {artifact_path}")
            else:
                artifact_paths[name] = artifact_path
                if _sha256(artifact_path) != digest:
                    issues.append(f"signed artifact hash mismatch: {name}")

    family_assets: dict[str, str] = {}
    if (
        platform_valid
        and target_id in TARGET_IDS.get(platform_name, ())
        and artifact_names
    ):
        for family, pattern in _asset_patterns(platform_name, target_id):
            matches = [name for name in artifact_names if pattern.fullmatch(name)]
            if len(matches) != 1:
                issues.append(
                    f"{platform_name} evidence must bind exactly one {family} asset for {target_id}"
                )
            else:
                family_assets[family] = matches[0]

    if platform_name == "windows" and len(family_assets) == 4:
        expected_signature_names = {
            family_assets["python"],
            family_assets["rust"],
            family_assets["tauri"],
            "Trading-Bot-C++.exe",
        }
        family_signature_names = {
            "python": family_assets["python"],
            "rust": family_assets["rust"],
            "tauri": family_assets["tauri"],
            "cpp": "Trading-Bot-C++.exe",
        }
    elif platform_name == "macos" and len(family_assets) == 4:
        expected_signature_names = {
            "Trading-Bot-Python",
            "trading-bot-rust",
            "trading-bot-tauri-desktop",
            "Trading-Bot-C++",
        }
        family_signature_names = {
            "python": "Trading-Bot-Python",
            "rust": "trading-bot-rust",
            "tauri": "trading-bot-tauri-desktop",
            "cpp": "Trading-Bot-C++",
        }
    else:
        expected_signature_names = set()
        family_signature_names = {}

    if expected_signature_names and set(signature_rows) != expected_signature_names:
        issues.append(
            f"{platform_name} evidence must name exactly the four required signed binaries"
        )

    zip_hash_cache: dict[str, Counter[str]] = {}
    for family, signature_name in family_signature_names.items():
        asset_name = family_assets[family]
        signature_row = signature_rows.get(signature_name)
        artifact_path = artifact_paths.get(asset_name)
        if signature_row is None or artifact_path is None:
            continue
        signature_digest = str(signature_row.get("sha256") or "")
        if not SHA256_PATTERN.fullmatch(signature_digest):
            continue
        if artifact_path.suffix.lower() == ".zip":
            try:
                member_hashes = zip_hash_cache.setdefault(
                    asset_name,
                    _zip_member_hashes(artifact_path),
                )
            except ValueError as exc:
                issues.append(f"unable to bind signed binary to {asset_name}: {exc}")
                continue
            if member_hashes[signature_digest] < 1:
                issues.append(
                    f"signed {family} binary hash is not present in {asset_name}"
                )
        elif artifact_digests.get(asset_name) != signature_digest:
            issues.append(f"signed {family} binary hash does not match {asset_name}")

    notarization = (
        payload.get("notarization")
        if isinstance(payload.get("notarization"), dict)
        else {}
    )
    submissions = notarization.get("submissions")
    if platform_name == "macos":
        if (
            notarization.get("required") is not True
            or notarization.get("tool") != "notarytool"
        ):
            issues.append("macOS evidence must require notarytool notarization")
        if notarization.get("all_submissions_accepted") is not True:
            issues.append("all macOS notarization submissions must be accepted")
        if notarization.get("cplusplus_app_stapled") is not True:
            issues.append("the macOS C++ app notarization ticket must be stapled")
        if not isinstance(submissions, list) or len(submissions) != 4:
            issues.append(
                "macOS evidence must contain exactly the app and three standalone archive submissions"
            )
        else:
            submission_ids: set[str] = set()
            submitted_archives: dict[str, str] = {}
            for index, item in enumerate(submissions):
                if not isinstance(item, dict) or item.get("status") != "Accepted":
                    issues.append(f"notarization.submissions[{index}] must be Accepted")
                    continue
                if item.get("error_count") != 0:
                    issues.append(
                        f"notarization.submissions[{index}] must contain zero errors"
                    )
                warning_count = item.get("warning_count")
                if (
                    not isinstance(warning_count, int)
                    or isinstance(warning_count, bool)
                    or warning_count < 0
                ):
                    issues.append(
                        f"notarization.submissions[{index}].warning_count must be non-negative"
                    )
                submission_id = str(item.get("id") or "")
                if not re.fullmatch(r"[0-9a-f-]{16,64}", submission_id):
                    issues.append(f"notarization.submissions[{index}].id is invalid")
                elif submission_id in submission_ids:
                    issues.append(
                        f"duplicate notarization submission id: {submission_id}"
                    )
                else:
                    submission_ids.add(submission_id)
                archive_name = str(item.get("archive") or "")
                archive_digest = str(item.get("archive_sha256") or "")
                if not archive_name or Path(archive_name).name != archive_name:
                    issues.append(
                        f"notarization.submissions[{index}].archive must be a basename"
                    )
                elif archive_name in submitted_archives:
                    issues.append(f"duplicate notarized archive: {archive_name}")
                else:
                    submitted_archives[archive_name] = archive_digest
                if not SHA256_PATTERN.fullmatch(archive_digest):
                    issues.append(
                        f"notarization.submissions[{index}].archive_sha256 is invalid"
                    )
            expected_standalone = {
                family_assets[family]: artifact_digests.get(family_assets[family], "")
                for family in ("python", "rust", "tauri")
                if family in family_assets
            }
            for archive_name, artifact_digest in expected_standalone.items():
                if submitted_archives.get(archive_name) != artifact_digest:
                    issues.append(
                        f"notarization must bind the exact published archive: {archive_name}"
                    )
            app_archive = f".notary-cpp-{target_id}.zip"
            if app_archive not in submitted_archives:
                issues.append(
                    "notarization must include the pre-package C++ app archive"
                )
    else:
        if (
            notarization.get("required") is not False
            or notarization.get("tool") != "not-applicable"
            or notarization.get("all_submissions_accepted") is not False
            or notarization.get("cplusplus_app_stapled") is not False
            or submissions != []
        ):
            issues.append("Windows evidence must not claim Apple notarization")
    if issues:
        return [f"{evidence_path}: {issue}" for issue in issues]
    return []


def audit_paths(
    paths: list[Path],
    *,
    asset_dir: Path,
    expected_revision: str = "",
    required_platform: str = "",
) -> dict[str, Any]:
    issues: list[str] = []
    reports = []
    observed_target_ids: list[str] = []
    for path in paths:
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            issues.append(f"{path}: unable to load evidence: {exc}")
            continue
        if not isinstance(payload, dict):
            issues.append(f"{path}: evidence must contain a JSON object")
            continue
        evidence_issues = validate_evidence(
            payload,
            evidence_path=path,
            asset_dir=asset_dir,
            expected_revision=expected_revision,
        )
        issues.extend(evidence_issues)
        observed_target_ids.append(str(payload.get("target_id") or "").strip().lower())
        reports.append(
            {
                "path": str(path),
                "platform": payload.get("platform"),
                "target_id": payload.get("target_id"),
                "ok": not evidence_issues,
            }
        )
    duplicate_targets = sorted(
        target_id
        for target_id, count in Counter(observed_target_ids).items()
        if target_id and count > 1
    )
    if duplicate_targets:
        issues.append(
            f"duplicate signing evidence targets: {', '.join(duplicate_targets)}"
        )
    if required_platform:
        expected_targets = set(TARGET_IDS[required_platform])
        observed_targets = set(observed_target_ids)
        if observed_targets != expected_targets or len(observed_target_ids) != len(
            expected_targets
        ):
            issues.append(
                f"{required_platform} signing evidence target set must be exactly: "
                + ", ".join(TARGET_IDS[required_platform])
            )
    return {"ok": not issues, "evidence": reports, "issues": issues}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("evidence", type=Path, nargs="+")
    parser.add_argument("--asset-dir", type=Path, default=Path("release"))
    parser.add_argument("--require-current-revision", action="store_true")
    parser.add_argument(
        "--require-complete-platform-set",
        choices=("windows", "macos"),
        default="",
        help="Require the exact complete signing target set for one publication workflow.",
    )
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args(argv)
    expected_revision = (
        _current_revision(Path.cwd()) if args.require_current_revision else ""
    )
    if args.require_current_revision and not COMMIT_PATTERN.fullmatch(
        expected_revision
    ):
        report = {
            "ok": False,
            "evidence": [],
            "issues": ["Unable to resolve current Git revision"],
        }
    else:
        report = audit_paths(
            args.evidence,
            asset_dir=args.asset_dir,
            expected_revision=expected_revision,
            required_platform=args.require_complete_platform_set,
        )
    if args.json:
        print(json.dumps(report, indent=2, sort_keys=True))
    else:
        print(f"Release signing evidence: {'passed' if report['ok'] else 'failed'}")
        for issue in report["issues"]:
            print(f"- {issue}")
    return 0 if report["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
