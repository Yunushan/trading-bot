#!/usr/bin/env python3
"""Write hash-bound native signing and notarization evidence for release assets."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


COMMIT_PATTERN = re.compile(r"[0-9a-f]{40}")
SHA256_PATTERN = re.compile(r"[0-9a-f]{64}")
TARGET_PATTERN = re.compile(r"(?:windows-(?:x64|arm64)|macos-[a-z0-9._-]+)")
WINDOWS_TARGET_IDS = {"windows-x64", "windows-arm64"}
MACOS_TARGET_IDS = {
    "macos-14-arm64",
    "macos-15-intel",
    "macos-15-arm64",
    "macos-26-arm64",
}


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _regular_file(path: Path, *, label: str) -> Path:
    resolved = path.resolve()
    if not resolved.is_file() or resolved.is_symlink():
        raise ValueError(f"{label} must be a regular, non-symlink file: {path}")
    return resolved


def _load_json(path: Path, *, label: str) -> dict[str, Any]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ValueError(f"Unable to load {label} {path}: {exc}") from exc
    if not isinstance(payload, dict):
        raise ValueError(f"{label} must contain a JSON object: {path}")
    return payload


def _notary_submission(
    receipt_path: Path, log_path: Path, archive_path: Path
) -> dict[str, Any]:
    receipt = _load_json(
        _regular_file(receipt_path, label="notary receipt"), label="notary receipt"
    )
    log = _load_json(_regular_file(log_path, label="notary log"), label="notary log")
    archive = _regular_file(archive_path, label="notarized archive")
    status = str(receipt.get("status") or "").strip()
    submission_id = str(receipt.get("id") or "").strip()
    if status.lower() != "accepted":
        raise ValueError(f"Notary submission for {archive.name} was not Accepted")
    if not re.fullmatch(r"[0-9a-fA-F-]{16,64}", submission_id):
        raise ValueError(f"Notary submission for {archive.name} has an invalid id")
    issues = log.get("issues")
    if issues is None:
        issues = []
    if not isinstance(issues, list):
        raise ValueError(
            f"Notary log for {archive.name} must contain an issues array or null"
        )
    error_count = sum(
        1
        for item in issues
        if isinstance(item, dict)
        and str(item.get("severity") or "").strip().lower() == "error"
    )
    warning_count = sum(
        1
        for item in issues
        if isinstance(item, dict)
        and str(item.get("severity") or "").strip().lower() == "warning"
    )
    if error_count:
        raise ValueError(
            f"Notary log for {archive.name} contains {error_count} error(s)"
        )
    return {
        "archive": archive.name,
        "archive_sha256": _sha256(archive),
        "id": submission_id.lower(),
        "status": "Accepted",
        "error_count": 0,
        "warning_count": warning_count,
    }


def build_evidence(
    *,
    platform_name: str,
    target_id: str,
    source_revision: str,
    assets: list[Path],
    signature_targets: list[Path],
    notary_receipts: list[Path] | None = None,
    notary_logs: list[Path] | None = None,
    notarized_archives: list[Path] | None = None,
    cpp_app_stapled: bool = False,
) -> dict[str, Any]:
    platform_value = str(platform_name or "").strip().lower()
    normalized_target = str(target_id or "").strip().lower()
    revision = str(source_revision or "").strip().lower()
    if platform_value not in {"windows", "macos"}:
        raise ValueError("platform must be windows or macos")
    allowed_targets = (
        WINDOWS_TARGET_IDS if platform_value == "windows" else MACOS_TARGET_IDS
    )
    if (
        not TARGET_PATTERN.fullmatch(normalized_target)
        or normalized_target not in allowed_targets
    ):
        raise ValueError("target id does not match the native signing platform")
    if not COMMIT_PATTERN.fullmatch(revision):
        raise ValueError(
            "source revision must be a full 40-character lowercase Git commit"
        )
    if len(assets) != 4:
        raise ValueError("exactly four signed release assets are required")
    if len(signature_targets) != 4:
        raise ValueError("exactly four native signature targets are required")

    asset_rows = []
    seen_asset_names: set[str] = set()
    for raw_path in assets:
        path = _regular_file(raw_path, label="release asset")
        if path.name in seen_asset_names:
            raise ValueError(f"duplicate release asset name: {path.name}")
        seen_asset_names.add(path.name)
        asset_rows.append({"name": path.name, "sha256": _sha256(path)})

    signature_rows = []
    seen_signature_paths: set[str] = set()
    for raw_path in signature_targets:
        path = _regular_file(raw_path, label="signature target")
        normalized_path = path.as_posix()
        if normalized_path in seen_signature_paths:
            raise ValueError(f"duplicate signature target: {path}")
        seen_signature_paths.add(normalized_path)
        signature_rows.append(
            {
                "name": path.name,
                "sha256": _sha256(path),
                "verification": "valid",
            }
        )

    receipts = list(notary_receipts or [])
    logs = list(notary_logs or [])
    archives = list(notarized_archives or [])
    submissions: list[dict[str, Any]] = []
    if platform_value == "macos":
        if not receipts or len(receipts) != len(logs) or len(logs) != len(archives):
            raise ValueError(
                "macOS evidence requires matching notary receipt, log, and archive lists"
            )
        submissions = [
            _notary_submission(receipt, log, archive)
            for receipt, log, archive in zip(receipts, logs, archives, strict=True)
        ]
        if not cpp_app_stapled:
            raise ValueError("macOS evidence requires a stapled C++ app bundle")
    elif receipts or logs or archives or cpp_app_stapled:
        raise ValueError(
            "Windows Authenticode evidence must not contain Apple notarization inputs"
        )

    return {
        "schema_version": 1,
        "status": "pass",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "platform": platform_value,
        "target_id": normalized_target,
        "source_revision": revision,
        "secrets_redacted": True,
        "artifacts": asset_rows,
        "signature_targets": signature_rows,
        "signing": {
            "method": "authenticode"
            if platform_value == "windows"
            else "developer-id-application",
            "digest_algorithm": "sha256",
            "secure_timestamp": True,
            "hardened_runtime": platform_value == "macos",
            "verification": "valid",
        },
        "notarization": {
            "required": platform_value == "macos",
            "tool": "notarytool" if platform_value == "macos" else "not-applicable",
            "all_submissions_accepted": platform_value == "macos"
            and all(item["status"] == "Accepted" for item in submissions),
            "cplusplus_app_stapled": bool(cpp_app_stapled),
            "submissions": submissions,
        },
    }


def _atomic_write(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary: Path | None = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="w",
            encoding="utf-8",
            dir=path.parent,
            prefix=f".{path.name}.",
            suffix=".tmp",
            delete=False,
        ) as handle:
            temporary = Path(handle.name)
            json.dump(payload, handle, indent=2, sort_keys=True, allow_nan=False)
            handle.write("\n")
            handle.flush()
            os.fsync(handle.fileno())
        temporary.replace(path)
        temporary = None
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--platform", choices=("windows", "macos"), required=True)
    parser.add_argument("--target-id", required=True)
    parser.add_argument("--source-revision", required=True)
    parser.add_argument("--asset", type=Path, action="append", required=True)
    parser.add_argument("--signature-target", type=Path, action="append", required=True)
    parser.add_argument("--notary-receipt", type=Path, action="append", default=[])
    parser.add_argument("--notary-log", type=Path, action="append", default=[])
    parser.add_argument("--notarized-archive", type=Path, action="append", default=[])
    parser.add_argument("--cpp-app-stapled", action="store_true")
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args(argv)
    try:
        evidence = build_evidence(
            platform_name=args.platform,
            target_id=args.target_id,
            source_revision=args.source_revision,
            assets=args.asset,
            signature_targets=args.signature_target,
            notary_receipts=args.notary_receipt,
            notary_logs=args.notary_log,
            notarized_archives=args.notarized_archive,
            cpp_app_stapled=args.cpp_app_stapled,
        )
        _atomic_write(args.output, evidence)
    except (OSError, ValueError) as exc:
        print(f"Release signing evidence failed closed: {exc}")
        return 1
    print(f"Release signing evidence written: {args.output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
