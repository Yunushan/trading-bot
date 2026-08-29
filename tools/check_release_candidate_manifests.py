#!/usr/bin/env python3
"""Validate source-bound release manifests against GitHub release asset metadata."""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import check_release_assets


MAX_RELEASE_METADATA_BYTES = 8 * 1024 * 1024
MAX_MANIFEST_BYTES = 4 * 1024 * 1024
REVISION_PATTERN = re.compile(r"^[0-9a-f]{40}$")
SHA256_PATTERN = re.compile(r"^[0-9a-f]{64}$")


@dataclass(frozen=True)
class LoadedManifest:
    name: str
    payload: Mapping[str, Any]
    size_bytes: int
    sha256: str


def _decode_object(raw: bytes, *, source: str, limit: int) -> Mapping[str, Any]:
    if len(raw) > limit:
        raise ValueError(f"JSON input exceeds {limit} bytes: {source}")
    try:
        payload = json.loads(raw.decode("utf-8"))
    except (UnicodeError, json.JSONDecodeError) as error:
        raise ValueError(f"could not read JSON {source}: {error}") from error
    if not isinstance(payload, Mapping):
        raise ValueError(f"JSON input must be an object: {source}")
    return payload


def _read_release_metadata(source: str) -> Mapping[str, Any]:
    if source == "-":
        raw = sys.stdin.buffer.read(MAX_RELEASE_METADATA_BYTES + 1)
        return _decode_object(raw, source="stdin", limit=MAX_RELEASE_METADATA_BYTES)
    path = Path(source)
    try:
        raw = path.read_bytes()
    except OSError as error:
        raise ValueError(f"could not read release metadata {path}: {error}") from error
    return _decode_object(raw, source=str(path), limit=MAX_RELEASE_METADATA_BYTES)


def load_manifests(directory: Path) -> dict[str, LoadedManifest]:
    try:
        candidates = sorted(directory.glob("release-manifest-*.json"))
    except OSError as error:
        raise ValueError(f"could not inspect manifest directory {directory}: {error}") from error
    manifests: dict[str, LoadedManifest] = {}
    for path in candidates:
        if path.is_symlink() or not path.is_file():
            raise ValueError(f"release manifest must be a regular non-symlink file: {path}")
        try:
            raw = path.read_bytes()
        except OSError as error:
            raise ValueError(f"could not read release manifest {path}: {error}") from error
        payload = _decode_object(raw, source=str(path), limit=MAX_MANIFEST_BYTES)
        manifests[path.name] = LoadedManifest(
            name=path.name,
            payload=payload,
            size_bytes=len(raw),
            sha256=hashlib.sha256(raw).hexdigest(),
        )
    return manifests


def _release_rows(payload: Mapping[str, Any]) -> tuple[dict[str, list[Mapping[str, Any]]], list[str]]:
    rows = payload.get("assets")
    if not isinstance(rows, list):
        return {}, ["release metadata does not contain an asset list"]
    by_name: dict[str, list[Mapping[str, Any]]] = {}
    for row in rows:
        if not isinstance(row, Mapping):
            continue
        name = str(row.get("name") or "").strip()
        if name:
            by_name.setdefault(name, []).append(row)
    return by_name, []


def _verify_release_row(
    rows_by_name: dict[str, list[Mapping[str, Any]]],
    *,
    name: str,
    size_bytes: int,
    sha256: str,
) -> list[str]:
    rows = rows_by_name.get(name, [])
    if len(rows) != 1:
        return [f"manifest artifact {name!r} must map to exactly one release asset"]
    row = rows[0]
    issues: list[str] = []
    if str(row.get("state") or "").strip().lower() != "uploaded":
        issues.append(f"manifest artifact {name!r} is not fully uploaded")
    actual_size = row.get("size")
    if (
        isinstance(actual_size, bool)
        or not isinstance(actual_size, int)
        or actual_size != size_bytes
    ):
        issues.append(f"manifest artifact {name!r} size does not match release metadata")
    if str(row.get("digest") or "").strip() != f"sha256:{sha256}":
        issues.append(f"manifest artifact {name!r} digest does not match release metadata")
    return issues


def validate_candidate_manifests(
    release_payload: Mapping[str, Any],
    manifests: Mapping[str, LoadedManifest],
    *,
    tag: str,
    expected_source_revision: str,
) -> list[str]:
    """Return all aggregate manifest/source/release-metadata binding defects."""

    _, expected_assets = check_release_assets._build_expected_assets(tag)
    required_names = {asset.name for asset in expected_assets if asset.required}
    required_manifest_names = {
        name for name in required_names if name.startswith("release-manifest-")
    }
    required_manifest_covered_names = {
        name
        for name in required_names
        if not name.startswith("release-manifest-")
        and not name.startswith("release-sbom-")
    }

    issues: list[str] = []
    missing_manifests = sorted(required_manifest_names - set(manifests))
    if missing_manifests:
        issues.append(
            "missing required release manifests: " + ", ".join(missing_manifests)
        )

    rows_by_name, row_issues = _release_rows(release_payload)
    issues.extend(row_issues)
    if row_issues:
        return issues

    covered_names: set[str] = set()
    for manifest_name, loaded in sorted(manifests.items()):
        issues.extend(
            _verify_release_row(
                rows_by_name,
                name=manifest_name,
                size_bytes=loaded.size_bytes,
                sha256=loaded.sha256,
            )
        )
        payload = loaded.payload
        if payload.get("schema_version") != 1:
            issues.append(f"{manifest_name} has an unsupported schema version")
        if payload.get("source_revision") != expected_source_revision:
            issues.append(f"{manifest_name} source revision does not match the tested source")
        artifacts = payload.get("artifacts")
        if not isinstance(artifacts, list) or not artifacts:
            issues.append(f"{manifest_name} must contain at least one artifact")
            continue

        local_names: set[str] = set()
        for index, row in enumerate(artifacts):
            if not isinstance(row, Mapping):
                issues.append(f"{manifest_name} artifacts[{index}] must be an object")
                continue
            name = row.get("name")
            digest = row.get("sha256")
            size = row.get("size_bytes")
            if (
                not isinstance(name, str)
                or not name
                or "/" in name
                or "\\" in name
                or Path(name).name != name
                or name in local_names
            ):
                issues.append(
                    f"{manifest_name} artifacts[{index}] has an unsafe or duplicate name"
                )
                continue
            local_names.add(name)
            if name in covered_names:
                issues.append(f"release artifact {name!r} appears in multiple manifests")
            covered_names.add(name)
            if not isinstance(digest, str) or not SHA256_PATTERN.fullmatch(digest):
                issues.append(f"{manifest_name} artifact {name!r} has an invalid SHA-256")
                continue
            if isinstance(size, bool) or not isinstance(size, int) or size < 0:
                issues.append(f"{manifest_name} artifact {name!r} has an invalid size")
                continue
            issues.extend(
                _verify_release_row(
                    rows_by_name,
                    name=name,
                    size_bytes=size,
                    sha256=digest,
                )
            )

    uncovered = sorted(required_manifest_covered_names - covered_names)
    if uncovered:
        issues.append(
            "required release assets are not source-bound by a manifest: "
            + ", ".join(uncovered)
        )
    return issues


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("release_metadata", help="Release JSON path, or - for stdin.")
    parser.add_argument("--manifest-dir", type=Path, required=True)
    parser.add_argument("--tag", required=True)
    parser.add_argument("--expected-source-revision", required=True)
    parser.add_argument("--json", action="store_true")
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = _build_parser()
    args = parser.parse_args(argv)
    if not REVISION_PATTERN.fullmatch(args.expected_source_revision):
        parser.error("--expected-source-revision must be a lowercase 40-character commit SHA")

    issues: list[str] = []
    try:
        release_payload = _read_release_metadata(args.release_metadata)
        manifests = load_manifests(args.manifest_dir)
    except ValueError as error:
        release_payload = {}
        manifests = {}
        issues.append(str(error))
    if not issues:
        issues.extend(
            validate_candidate_manifests(
                release_payload,
                manifests,
                tag=args.tag,
                expected_source_revision=args.expected_source_revision,
            )
        )

    report = {
        "ok": not issues,
        "tag": args.tag,
        "expected_source_revision": args.expected_source_revision,
        "manifest_count": len(manifests),
        "issues": issues,
    }
    if args.json:
        print(json.dumps(report, indent=2, sort_keys=True))
    elif issues:
        print("release candidate manifests: rejected")
        for issue in issues:
            print(f"- {issue}")
    else:
        print(
            "release candidate manifests: approved "
            f"({len(manifests)} manifests, source {args.expected_source_revision})"
        )
    return 1 if issues else 0


if __name__ == "__main__":
    raise SystemExit(main())
