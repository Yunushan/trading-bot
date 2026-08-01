#!/usr/bin/env python3
"""Require release-tag and distributable metadata versions to agree."""

from __future__ import annotations

import argparse
import json
import re
import sys
import tomllib
from pathlib import Path


VERSION_TAG_PATTERN = re.compile(r"^v(?P<version>\d+\.\d+\.\d+(?:[-+][0-9A-Za-z.-]+)?)$")
RUST_MANIFESTS = (
    "experiments/rust-shells/Cargo.toml",
    "experiments/rust-shells/crates/core/Cargo.toml",
    "experiments/rust-shells/crates/contracts/Cargo.toml",
    "experiments/rust-shells/apps/tauri-desktop/Cargo.toml",
)
PYTHON_PROJECT = "Languages/Python/pyproject.toml"
TAURI_CONFIG = "experiments/rust-shells/apps/tauri-desktop/tauri.conf.json"


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[1]


def _read_toml_version(path: Path, section: str) -> str:
    try:
        payload = tomllib.loads(path.read_text(encoding="utf-8"))
    except (OSError, tomllib.TOMLDecodeError) as error:
        raise ValueError(f"could not read {path}: {error}") from error
    value = payload.get(section, {}).get("version") if isinstance(payload.get(section), dict) else None
    if not isinstance(value, str) or not value:
        raise ValueError(f"{path} has no [{section}] version")
    return value


def collect_release_versions(root: Path) -> dict[str, str]:
    versions = {PYTHON_PROJECT: _read_toml_version(root / PYTHON_PROJECT, "project")}
    for manifest in RUST_MANIFESTS:
        versions[manifest] = _read_toml_version(root / manifest, "package")
    config_path = root / TAURI_CONFIG
    try:
        config = json.loads(config_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise ValueError(f"could not read {config_path}: {error}") from error
    tauri_version = config.get("version") if isinstance(config, dict) else None
    if not isinstance(tauri_version, str) or not tauri_version:
        raise ValueError(f"{config_path} has no version")
    versions[TAURI_CONFIG] = tauri_version
    return versions


def validate_release_version(tag: str, root: Path | None = None) -> tuple[str, dict[str, str], list[str]]:
    match = VERSION_TAG_PATTERN.fullmatch(tag)
    if not match:
        return "", {}, [f"release tag must use vMAJOR.MINOR.PATCH form: {tag}"]
    expected = match.group("version")
    try:
        versions = collect_release_versions(root or _repo_root())
    except ValueError as error:
        return expected, {}, [str(error)]
    issues = [f"{path} version {version!r} does not match release version {expected!r}" for path, version in versions.items() if version != expected]
    return expected, versions, issues


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Validate release tag/package metadata version alignment.")
    parser.add_argument("--tag", required=True, help="Release tag, for example v1.2.3.")
    parser.add_argument("--json", action="store_true", help="Print the resolved versions as JSON.")
    args = parser.parse_args(argv)

    expected, versions, issues = validate_release_version(args.tag)
    if args.json:
        print(json.dumps({"tag": args.tag, "expected_version": expected, "versions": versions, "issues": issues}, indent=2, sort_keys=True))
    elif issues:
        for issue in issues:
            print(f"error: {issue}", file=sys.stderr)
    else:
        print(f"release metadata versions match {expected}")
    return 1 if issues else 0


if __name__ == "__main__":
    raise SystemExit(main())
