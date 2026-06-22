#!/usr/bin/env python3
"""Import validated Rust native runtime and release-platform evidence artifacts."""

from __future__ import annotations

import argparse
import hashlib
import json
import shutil
import tempfile
import zipfile
from dataclasses import dataclass
from pathlib import Path
from typing import Any

try:
    from check_generated_evidence_source_control import generated_evidence_write_guard
    from check_release_platform_matrix import DEFAULT_MATRIX_PATH, _load_json, _target_evidence_issues, _validate_matrix
    import check_rust_native_runtime_evidence as runtime_evidence
except ModuleNotFoundError:  # pragma: no cover - exercised when imported as tools.*
    from tools.check_generated_evidence_source_control import generated_evidence_write_guard
    from tools.check_release_platform_matrix import DEFAULT_MATRIX_PATH, _load_json, _target_evidence_issues, _validate_matrix
    from tools import check_rust_native_runtime_evidence as runtime_evidence


DEFAULT_RUNTIME_EVIDENCE_DIR = Path("artifacts/rust-native-runtime-evidence")
DEFAULT_PLATFORM_EVIDENCE_DIR = Path("release-platform-evidence")
DEFAULT_MANIFEST_PATH = runtime_evidence.DEFAULT_MANIFEST_PATH
REQUIRED_REQUIREMENTS = runtime_evidence.REQUIRED_REQUIREMENTS


@dataclass(frozen=True)
class JsonCandidate:
    source: str
    name: str
    payload: dict[str, Any]


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[1]


def _repo_path(path: Path) -> Path:
    return path if path.is_absolute() else _repo_root() / path


def _load_json_bytes(source: str, data: bytes) -> dict[str, Any] | None:
    try:
        payload = json.loads(data.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError):
        return None
    return payload if isinstance(payload, dict) else None


def _iter_json_candidates(paths: list[Path]) -> tuple[list[JsonCandidate], list[str]]:
    candidates: list[JsonCandidate] = []
    issues: list[str] = []
    optional_canonical_dirs = {
        _repo_path(DEFAULT_RUNTIME_EVIDENCE_DIR).resolve(),
        _repo_path(DEFAULT_PLATFORM_EVIDENCE_DIR).resolve(),
    }
    for raw_path in paths:
        path = _repo_path(raw_path)
        if path.is_dir():
            for file_path in sorted(path.rglob("*.json")):
                payload = _load_json_bytes(str(file_path), file_path.read_bytes())
                if payload is None:
                    issues.append(f"{file_path} is not a UTF-8 JSON object")
                    continue
                candidates.append(JsonCandidate(source=str(file_path), name=file_path.name, payload=payload))
        elif path.is_file() and path.suffix.lower() == ".zip":
            try:
                with zipfile.ZipFile(path) as archive:
                    for member in sorted(archive.namelist()):
                        if member.endswith("/") or not member.lower().endswith(".json"):
                            continue
                        payload = _load_json_bytes(f"{path}!{member}", archive.read(member))
                        if payload is None:
                            issues.append(f"{path}!{member} is not a UTF-8 JSON object")
                            continue
                        candidates.append(JsonCandidate(source=f"{path}!{member}", name=Path(member).name, payload=payload))
            except zipfile.BadZipFile:
                issues.append(f"{path} is not a valid ZIP archive")
        elif path.is_file() and path.suffix.lower() == ".json":
            payload = _load_json_bytes(str(path), path.read_bytes())
            if payload is None:
                issues.append(f"{path} is not a UTF-8 JSON object")
                continue
            candidates.append(JsonCandidate(source=str(path), name=path.name, payload=payload))
        elif path.resolve() in optional_canonical_dirs:
            continue
        else:
            issues.append(f"unsupported artifact path: {path}")
    return candidates, issues


def _load_release_targets(matrix_path: Path) -> tuple[dict[str, dict[str, Any]], list[str]]:
    try:
        matrix = _load_json(_repo_path(matrix_path))
    except ValueError as exc:
        return {}, [str(exc)]
    platform_targets, browser_targets, issues = _validate_matrix(matrix)
    return {str(target["id"]): target for target in platform_targets + browser_targets}, issues


def _validate_runtime_candidate(
    candidate: JsonCandidate,
    manifest_path: Path,
    *,
    require_current_commit: bool,
    require_clean_source: bool,
) -> list[str]:
    evidence_id = str(candidate.payload.get("evidence_id") or "").strip()
    if evidence_id not in REQUIRED_REQUIREMENTS:
        return [f"{candidate.source} has unknown runtime evidence_id: {evidence_id or '<missing>'}"]
    if candidate.name != f"{evidence_id}.json":
        return [f"{candidate.source} filename must be {evidence_id}.json"]
    with tempfile.TemporaryDirectory() as temp_dir:
        temp_path = Path(temp_dir) / candidate.name
        temp_path.write_text(json.dumps(candidate.payload), encoding="utf-8")
        result = runtime_evidence.validate(
            manifest_path,
            require_evidence=True,
            require_current_commit=require_current_commit,
            require_clean_source=require_clean_source,
            evidence_dir_override=Path(temp_dir),
            requirement_ids={evidence_id},
        )
    return [str(issue) for issue in result.get("issues", [])]


def _validate_platform_source_binding(
    candidate: JsonCandidate,
    *,
    require_current_commit: bool,
    require_clean_source: bool,
) -> list[str]:
    if not require_current_commit and not require_clean_source:
        return []

    issues: list[str] = []
    current_contract_hash = runtime_evidence.native_python_source_contract_hash()
    if require_current_commit:
        current_commit = runtime_evidence._current_git_commit()
        if not current_commit:
            issues.append(f"{candidate.source} current git commit could not be determined")
        elif str(candidate.payload.get("commit") or "").strip() != current_commit:
            issues.append(f"{candidate.source} commit must match current git commit {current_commit}")

    if require_clean_source:
        current_source_tree_clean = runtime_evidence._current_source_tree_clean()
        if current_source_tree_clean is None:
            issues.append(f"{candidate.source} current source tree cleanliness could not be determined")
        elif not current_source_tree_clean:
            issues.append(f"{candidate.source} current source tree must be clean for promotion evidence import")
        if candidate.payload.get("source_tree_clean") is not True:
            issues.append(f"{candidate.source} source_tree_clean must be true for release promotion evidence")

    if str(candidate.payload.get("python_source_contract_hash") or "").strip().lower() != current_contract_hash:
        issues.append(f"{candidate.source} python_source_contract_hash must match current Python source contract")
    if candidate.payload.get("runtime_ready_claimed") is not False:
        issues.append(f"{candidate.source} runtime_ready_claimed must be false")
    if candidate.payload.get("secrets_redacted") is not True:
        issues.append(f"{candidate.source} secrets_redacted must be true")
    return issues


def _validate_platform_candidate(
    candidate: JsonCandidate,
    target: dict[str, Any],
    *,
    require_current_commit: bool,
    require_clean_source: bool,
) -> list[str]:
    target_id = str(target["id"])
    if candidate.name != f"{target_id}.json":
        return [f"{candidate.source} filename must be {target_id}.json"]
    with tempfile.TemporaryDirectory() as temp_dir:
        temp_path = Path(temp_dir) / candidate.name
        temp_path.write_text(json.dumps(candidate.payload), encoding="utf-8")
        issues = _target_evidence_issues(target, Path(temp_dir))
    issues.extend(
        _validate_platform_source_binding(
            candidate,
            require_current_commit=require_current_commit,
            require_clean_source=require_clean_source,
        )
    )
    return issues


def _candidate_destination(
    candidate: JsonCandidate,
    *,
    runtime_evidence_dir: Path,
    platform_evidence_dir: Path,
    platform_targets: dict[str, dict[str, Any]],
    manifest_path: Path,
    require_current_commit: bool,
    require_clean_source: bool,
) -> tuple[str, Path, list[str]] | None:
    evidence_id = str(candidate.payload.get("evidence_id") or "").strip()
    if evidence_id in REQUIRED_REQUIREMENTS:
        issues = _validate_runtime_candidate(
            candidate,
            manifest_path,
            require_current_commit=require_current_commit,
            require_clean_source=require_clean_source,
        )
        return "runtime", runtime_evidence_dir / candidate.name, issues

    target_id = str(candidate.payload.get("target_id") or Path(candidate.name).stem).strip()
    target = platform_targets.get(target_id)
    if target is not None:
        issues = _validate_platform_candidate(
            candidate,
            target,
            require_current_commit=require_current_commit,
            require_clean_source=require_clean_source,
        )
        return "release_platform", platform_evidence_dir / candidate.name, issues

    return None


def _same_json_file(path: Path, payload: dict[str, Any]) -> bool:
    try:
        existing = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return False
    return existing == payload


def _payload_sha256(payload: dict[str, Any]) -> str:
    data = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(data).hexdigest()


def _existing_json_sha256(path: Path) -> str:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return hashlib.sha256(path.read_bytes()).hexdigest()
    return _payload_sha256(payload) if isinstance(payload, dict) else hashlib.sha256(path.read_bytes()).hexdigest()


def import_evidence_artifacts(
    paths: list[Path],
    *,
    runtime_evidence_dir: Path = DEFAULT_RUNTIME_EVIDENCE_DIR,
    platform_evidence_dir: Path = DEFAULT_PLATFORM_EVIDENCE_DIR,
    matrix_path: Path = DEFAULT_MATRIX_PATH,
    manifest_path: Path = DEFAULT_MANIFEST_PATH,
    apply: bool = False,
    overwrite: bool = False,
    require_current_commit: bool = False,
    require_clean_source: bool = False,
    required_runtime_ids: set[str] | None = None,
) -> dict[str, Any]:
    runtime_evidence_dir = _repo_path(runtime_evidence_dir)
    platform_evidence_dir = _repo_path(platform_evidence_dir)
    manifest_path = _repo_path(manifest_path)
    required_runtime_ids = set(required_runtime_ids or set())
    unknown_required_ids = sorted(required_runtime_ids - set(REQUIRED_REQUIREMENTS))
    if unknown_required_ids:
        issues = [f"unknown required runtime evidence id: {evidence_id}" for evidence_id in unknown_required_ids]
    else:
        issues = []
    candidates, candidate_issues = _iter_json_candidates(paths)
    issues.extend(candidate_issues)
    platform_targets, target_issues = _load_release_targets(matrix_path)
    issues.extend(target_issues)

    planned: list[dict[str, Any]] = []
    skipped_existing: list[dict[str, Any]] = []
    ignored: list[str] = []
    valid_runtime_ids: set[str] = set()
    seen_destinations: set[Path] = set()
    for candidate in candidates:
        resolved = _candidate_destination(
            candidate,
            runtime_evidence_dir=runtime_evidence_dir,
            platform_evidence_dir=platform_evidence_dir,
            platform_targets=platform_targets,
            manifest_path=manifest_path,
            require_current_commit=require_current_commit,
            require_clean_source=require_clean_source,
        )
        if resolved is None:
            ignored.append(candidate.source)
            continue
        kind, destination, validation_issues = resolved
        if validation_issues:
            issues.extend(f"{candidate.source}: {issue}" for issue in validation_issues)
            continue
        if kind == "runtime":
            valid_runtime_ids.add(str(candidate.payload.get("evidence_id") or "").strip())
        if destination in seen_destinations:
            issues.append(f"duplicate destination candidate skipped: {destination}")
            continue
        seen_destinations.add(destination)
        if destination.exists() and not overwrite:
            if _same_json_file(destination, candidate.payload):
                skipped_existing.append(
                    {
                        "action": "skip_existing_identical",
                        "kind": kind,
                        "source": candidate.source,
                        "destination": str(destination),
                        "existing_sha256": _existing_json_sha256(destination),
                        "incoming_sha256": _payload_sha256(candidate.payload),
                    }
                )
                continue
            issues.append(f"destination already exists; pass --overwrite to replace: {destination}")
            continue
        destination_exists = destination.exists()
        planned.append(
            {
                "action": "overwrite" if destination_exists else "copy",
                "kind": kind,
                "source": candidate.source,
                "destination": str(destination),
                "incoming_sha256": _payload_sha256(candidate.payload),
                **(
                    {
                        "existing_sha256": _existing_json_sha256(destination),
                        "replaces_identical_json": _same_json_file(destination, candidate.payload),
                    }
                    if destination_exists
                    else {}
                ),
            }
        )

    missing_required_runtime_ids = sorted(required_runtime_ids - valid_runtime_ids)
    for evidence_id in missing_required_runtime_ids:
        issues.append(f"missing required runtime evidence artifact in scanned inputs: {evidence_id}")

    source_control_write_guard = generated_evidence_write_guard(
        [Path(row["destination"]) for row in planned],
        root=_repo_root(),
    )
    if apply and not source_control_write_guard["ok"]:
        issues.extend(str(issue) for issue in source_control_write_guard["issues"])

    copied: list[dict[str, Any]] = []
    if apply and not issues:
        by_source = {candidate.source: candidate for candidate in candidates}
        for row in planned:
            destination = Path(row["destination"])
            destination.parent.mkdir(parents=True, exist_ok=True)
            candidate = by_source[row["source"]]
            with tempfile.NamedTemporaryFile("w", encoding="utf-8", delete=False, dir=destination.parent) as temp_file:
                json.dump(candidate.payload, temp_file, indent=2, sort_keys=True)
                temp_file.write("\n")
                temp_name = temp_file.name
            shutil.move(temp_name, destination)
            copied.append(row)

    overwritten = [row for row in copied if row.get("action") == "overwrite"]
    planned_overwrites = [row for row in planned if row.get("action") == "overwrite"]
    return {
        "ok": not issues,
        "applied": bool(apply),
        "require_current_commit": bool(require_current_commit),
        "require_clean_source": bool(require_clean_source),
        "required_runtime_ids": sorted(required_runtime_ids),
        "valid_runtime_ids": sorted(valid_runtime_ids),
        "candidate_count": len(candidates),
        "planned_count": len(planned),
        "copied_count": len(copied),
        "overwrite_count": len(overwritten) if apply else len(planned_overwrites),
        "skipped_existing_count": len(skipped_existing),
        "planned": planned,
        "copied": copied,
        "overwritten": overwritten if apply else planned_overwrites,
        "skipped_existing": skipped_existing,
        "ignored": ignored,
        "source_control_write_guard": source_control_write_guard,
        "issues": issues,
        "runtime_evidence_dir": str(runtime_evidence_dir),
        "platform_evidence_dir": str(platform_evidence_dir),
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("paths", nargs="+", help="Artifact ZIP, JSON file, or directory paths to scan.")
    parser.add_argument("--apply", action="store_true", help="Copy validated evidence into canonical directories.")
    parser.add_argument("--overwrite", action="store_true", help="Replace existing destination evidence files.")
    parser.add_argument(
        "--require-current-commit",
        action="store_true",
        help="Reject runtime evidence artifacts whose commit does not match the current git commit.",
    )
    parser.add_argument(
        "--require-clean-source",
        action="store_true",
        help="Require a clean tracked source tree and runtime artifacts generated with source_tree_clean: true.",
    )
    parser.add_argument("--runtime-evidence-dir", default=str(DEFAULT_RUNTIME_EVIDENCE_DIR))
    parser.add_argument("--platform-evidence-dir", default=str(DEFAULT_PLATFORM_EVIDENCE_DIR))
    parser.add_argument("--matrix", default=str(DEFAULT_MATRIX_PATH))
    parser.add_argument("--manifest", default=str(DEFAULT_MANIFEST_PATH))
    parser.add_argument(
        "--require-runtime-id",
        action="append",
        choices=sorted(REQUIRED_REQUIREMENTS),
        default=[],
        help="Require a specific runtime evidence id to be present and valid in the scanned artifact inputs.",
    )
    parser.add_argument("--json", action="store_true", help="Print machine-readable JSON.")
    args = parser.parse_args(argv)
    result = import_evidence_artifacts(
        [Path(path) for path in args.paths],
        runtime_evidence_dir=Path(args.runtime_evidence_dir),
        platform_evidence_dir=Path(args.platform_evidence_dir),
        matrix_path=Path(args.matrix),
        manifest_path=Path(args.manifest),
        apply=bool(args.apply),
        overwrite=bool(args.overwrite),
        require_current_commit=bool(args.require_current_commit),
        require_clean_source=bool(args.require_clean_source),
        required_runtime_ids=set(args.require_runtime_id or []),
    )
    if args.json:
        print(json.dumps(result, indent=2, sort_keys=True))
    else:
        action = "copied" if result["applied"] else "planned"
        print(f"Rust native evidence import {action}: {result['copied_count'] or result['planned_count']} file(s)")
        for issue in result["issues"]:
            print(f"- {issue}")
    return 0 if result["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
