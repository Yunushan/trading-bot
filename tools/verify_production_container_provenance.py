#!/usr/bin/env python3
"""Fail closed unless a production image has same-run build, SBOM, and scan attestations.

The GitHub CLI performs cryptographic verification. This module evaluates its
verified JSON output; JSON supplied directly to this module is not proof.
"""

from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any


BUILD_TYPE = "https://slsa.dev/provenance/v1"
SBOM_TYPE = "https://spdx.dev/Document/v2.3"
MAX_AGE = timedelta(days=7)
MAX_CLOCK_SKEW = timedelta(minutes=5)
PUBLISH_WORKFLOW = ".github/workflows/publish-production-readonly-image.yml"


def _object(value: Any, label: str) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise ValueError(f"{label} must be an object")
    return value


def _text(value: Any, label: str) -> str:
    if not isinstance(value, str) or not value:
        raise ValueError(f"{label} must be non-empty text")
    return value


def _timestamp(value: Any) -> datetime:
    raw = _text(value, "verified timestamp")
    try:
        parsed = datetime.fromisoformat(raw.replace("Z", "+00:00"))
    except ValueError as exc:
        raise ValueError("verified timestamp is not ISO 8601") from exc
    if parsed.tzinfo is None:
        raise ValueError("verified timestamp needs a timezone")
    return parsed.astimezone(timezone.utc)


def _context(image: str, repository: str, commit: str, release_tag: str) -> tuple[str, str]:
    if re.fullmatch(r"[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+", repository) is None:
        raise ValueError("repository must be owner/name")
    if re.fullmatch(r"[0-9a-f]{40}", commit) is None:
        raise ValueError("commit must be a full lowercase Git SHA")
    if re.fullmatch(r"v[0-9]+\.[0-9]+\.[0-9]+", release_tag) is None:
        raise ValueError("release tag must be a semantic version")
    image_name = f"ghcr.io/{repository.lower()}/service"
    if re.fullmatch(re.escape(image_name) + r"@sha256:[0-9a-f]{64}", image) is None:
        raise ValueError(f"image must be the approved immutable {image_name} digest")
    return image_name, image.rsplit("@", 1)[1]


def _verified_entries(
    payload: Any, *, predicate_type: str, image_name: str, digest: str,
    repository: str, commit: str, release_tag: str, now: datetime,
) -> list[dict[str, Any]]:
    if not isinstance(payload, list) or not payload:
        raise ValueError(f"missing verified {predicate_type} attestation")
    expected_ref = f"refs/tags/{release_tag}"
    workflow_uri = f"https://github.com/{repository}/{PUBLISH_WORKFLOW}@{expected_ref}"
    repo_uri = f"https://github.com/{repository}"
    run_pattern = re.compile(
        re.escape(repo_uri) + r"/actions/runs/[1-9][0-9]*/attempts/[1-9][0-9]*\Z"
    )
    accepted: list[dict[str, Any]] = []
    for item in payload:
        try:
            result = _object(_object(item, "verified entry").get("verificationResult"), "verification result")
            statement = _object(result.get("statement"), "statement")
            cert = _object(_object(result.get("signature"), "signature").get("certificate"), "certificate")
            subjects = statement.get("subject")
            if statement.get("predicateType") != predicate_type or not isinstance(subjects, list) or len(subjects) != 1:
                continue
            subject = _object(subjects[0], "subject")
            if subject.get("name") != image_name or _object(subject.get("digest"), "digest").get("sha256") != digest.removeprefix("sha256:"):
                continue
            if (
                cert.get("issuer") != "https://token.actions.githubusercontent.com"
                or cert.get("buildSignerURI") != workflow_uri
                or cert.get("sourceRepositoryURI") != repo_uri
                or cert.get("sourceRepositoryDigest") != commit
                or cert.get("sourceRepositoryRef") != expected_ref
                or cert.get("runnerEnvironment") != "github-hosted"
                or cert.get("buildTrigger") != "workflow_dispatch"
            ):
                continue
            run = cert.get("runInvocationURI")
            if not isinstance(run, str) or run_pattern.fullmatch(run) is None:
                continue
            timestamps = result.get("verifiedTimestamps")
            if not isinstance(timestamps, list) or not timestamps:
                continue
            valid_times = [
                _timestamp(_object(item, "verified timestamp").get("timestamp"))
                for item in timestamps
            ]
            fresh_times = [at for at in valid_times if now - MAX_AGE <= at <= now + MAX_CLOCK_SKEW]
            if not fresh_times:
                continue
            accepted.append({"run": run, "timestamp": max(fresh_times), "predicate": statement.get("predicate")})
        except ValueError:
            continue
    return accepted


def evaluate_verified_attestations(
    evidence: dict[str, Any], *, image: str, repository: str, commit: str,
    release_tag: str, now: datetime | None = None,
) -> dict[str, Any]:
    """Evaluate only output from successful ``gh attestation verify`` calls."""
    image_name, digest = _context(image, repository, commit, release_tag)
    current = now or datetime.now(timezone.utc)
    if current.tzinfo is None:
        raise ValueError("current time needs a timezone")
    current = current.astimezone(timezone.utc)
    types = {
        "build": BUILD_TYPE,
        "sbom": SBOM_TYPE,
        "scan": f"https://github.com/{repository}/attestations/container-scan/v1",
    }
    found = {
        name: _verified_entries(
            evidence.get(name), predicate_type=kind, image_name=image_name, digest=digest,
            repository=repository, commit=commit, release_tag=release_tag, now=current,
        )
        for name, kind in types.items()
    }
    for build in found["build"]:
        for sbom in found["sbom"]:
            if sbom["run"] != build["run"]:
                continue
            sbom_data = sbom["predicate"]
            if not isinstance(sbom_data, dict) or sbom_data.get("spdxVersion") != "SPDX-2.3" or not isinstance(sbom_data.get("packages"), list) or not sbom_data["packages"]:
                continue
            for scan in found["scan"]:
                if scan["run"] != build["run"]:
                    continue
                predicate = scan["predicate"]
                if not isinstance(predicate, dict):
                    continue
                if (
                    type(predicate.get("schema_version")) is not int
                    or predicate["schema_version"] != 1
                    or predicate.get("result") != "pass"
                    or predicate.get("policy") != "tools/check_container_vulnerability_policy.py"
                    or predicate.get("source_commit") != commit
                    or predicate.get("release_tag") != release_tag
                    or predicate.get("image_digest") != digest
                    or predicate.get("image_name") != image_name
                    or predicate.get("severity_threshold") != "HIGH,CRITICAL"
                    or re.fullmatch(r"sha256:[0-9a-f]{64}", str(predicate.get("image_id"))) is None
                    or re.fullmatch(r"[0-9a-f]{64}", str(predicate.get("trivy_report_sha256"))) is None
                    or re.fullmatch(r"[0-9a-f]{64}", str(predicate.get("sbom_sha256"))) is None
                ):
                    continue
                return {
                    "ok": True,
                    "image": image,
                    "commit": commit,
                    "release_tag": release_tag,
                    "publisher_run": build["run"],
                    "build_attested_at": build["timestamp"].isoformat(),
                    "sbom_attested_at": sbom["timestamp"].isoformat(),
                    "scan_attested_at": scan["timestamp"].isoformat(),
                    "scan_report_sha256": predicate["trivy_report_sha256"],
                    "sbom_sha256": predicate["sbom_sha256"],
                }
    raise ValueError("no fresh same-run build, SBOM, and passing scan attestations for this digest")


def verify_with_gh(image: str, repository: str, commit: str, release_tag: str) -> dict[str, Any]:
    _context(image, repository, commit, release_tag)
    signer = f"{repository}/{PUBLISH_WORKFLOW}"
    shared = [
        "gh", "attestation", "verify", f"oci://{image}", "--repo", repository,
        "--signer-workflow", signer, "--source-digest", commit,
        "--source-ref", f"refs/tags/{release_tag}", "--deny-self-hosted-runners",
        "--format", "json", "--limit", "100",
    ]
    predicates = {
        "build": BUILD_TYPE,
        "sbom": SBOM_TYPE,
        "scan": f"https://github.com/{repository}/attestations/container-scan/v1",
    }
    evidence: dict[str, Any] = {}
    for name, predicate in predicates.items():
        completed = subprocess.run(
            [*shared, "--predicate-type", predicate], capture_output=True, text=True,
            check=False, timeout=60,
        )
        if completed.returncode != 0:
            raise ValueError(f"GitHub verification of {name} attestation failed: {completed.stderr.strip()}")
        try:
            evidence[name] = json.loads(completed.stdout)
        except json.JSONDecodeError as exc:
            raise ValueError(f"GitHub verification returned invalid {name} JSON") from exc
    return evaluate_verified_attestations(
        evidence, image=image, repository=repository, commit=commit, release_tag=release_tag,
    )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--image", required=True)
    parser.add_argument("--repository", required=True)
    parser.add_argument("--commit", required=True)
    parser.add_argument("--release-tag", required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args(argv)
    try:
        result = verify_with_gh(args.image, args.repository, args.commit, args.release_tag)
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    except (OSError, subprocess.TimeoutExpired, ValueError) as exc:
        print(f"Production image provenance verification failed closed: {exc}", file=sys.stderr)
        return 1
    print(json.dumps(result, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
