#!/usr/bin/env python3
"""Create a scan-pass predicate only after validating the exact image's reports."""

from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import re
import sys
from pathlib import Path


POLICY_PATH = Path(__file__).with_name("check_container_vulnerability_policy.py")
POLICY_SPEC = importlib.util.spec_from_file_location("check_container_vulnerability_policy", POLICY_PATH)
assert POLICY_SPEC and POLICY_SPEC.loader
policy = importlib.util.module_from_spec(POLICY_SPEC)
POLICY_SPEC.loader.exec_module(policy)


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def make_predicate(
    *, image: str, commit: str, release_tag: str, report: Path,
    runtime: Path, image_id_file: Path, sbom: Path,
) -> dict[str, object]:
    match = re.fullmatch(r"(ghcr\.io/[a-z0-9_.-]+/[a-z0-9_.-]+/service)@(sha256:[0-9a-f]{64})", image)
    if match is None:
        raise ValueError("image must be an immutable GHCR service digest")
    if re.fullmatch(r"[0-9a-f]{40}", commit) is None:
        raise ValueError("commit must be a full lowercase SHA")
    if re.fullmatch(r"v[0-9]+\.[0-9]+\.[0-9]+", release_tag) is None:
        raise ValueError("release tag must be a semantic version")
    _, active = policy.evaluate(report, runtime, image_id_file)
    if active:
        raise ValueError("HIGH or CRITICAL container vulnerabilities remain")
    sbom_payload = json.loads(sbom.read_text(encoding="utf-8"))
    if not isinstance(sbom_payload, dict) or sbom_payload.get("spdxVersion") != "SPDX-2.3" or not isinstance(sbom_payload.get("packages"), list) or not sbom_payload["packages"]:
        raise ValueError("SBOM must contain a non-empty SPDX 2.3 package inventory")
    image_id = image_id_file.read_text(encoding="utf-8-sig").strip()
    return {
        "schema_version": 1,
        "result": "pass",
        "policy": "tools/check_container_vulnerability_policy.py",
        "severity_threshold": "HIGH,CRITICAL",
        "source_commit": commit,
        "release_tag": release_tag,
        "image_name": match.group(1),
        "image_digest": match.group(2),
        "image_id": image_id,
        "trivy_report_sha256": _sha256(report),
        "sbom_sha256": _sha256(sbom),
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--image", required=True)
    parser.add_argument("--commit", required=True)
    parser.add_argument("--release-tag", required=True)
    parser.add_argument("--report", type=Path, required=True)
    parser.add_argument("--runtime", type=Path, required=True)
    parser.add_argument("--image-id-file", type=Path, required=True)
    parser.add_argument("--sbom", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args(argv)
    try:
        predicate = make_predicate(
            image=args.image, commit=args.commit, release_tag=args.release_tag,
            report=args.report, runtime=args.runtime, image_id_file=args.image_id_file,
            sbom=args.sbom,
        )
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(json.dumps(predicate, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    except (OSError, json.JSONDecodeError, ValueError) as exc:
        print(f"Container scan predicate refused: {exc}", file=sys.stderr)
        return 1
    print("Exact-digest container scan predicate created.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
