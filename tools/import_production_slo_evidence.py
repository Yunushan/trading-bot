#!/usr/bin/env python3
"""Convert a raw production telemetry export into canonical SLO evidence."""

from __future__ import annotations

import argparse
from datetime import datetime, timedelta, timezone
import hashlib
import json
import math
import os
from pathlib import Path
import re
import tempfile
from typing import Any


REPO_ROOT = Path(__file__).resolve().parents[1]

if __package__:
    from .check_operational_readiness import (
        DEFAULT_POLICY_PATH,
        SAFE_TELEMETRY_SOURCE_PATTERN,
        SHA256_PATTERN,
        _current_commit,
        _source_tree_clean,
        load_policy,
        policy_sha256,
        validate_policy,
    )
else:
    from check_operational_readiness import (
        DEFAULT_POLICY_PATH,
        SAFE_TELEMETRY_SOURCE_PATTERN,
        SHA256_PATTERN,
        _current_commit,
        _source_tree_clean,
        load_policy,
        policy_sha256,
        validate_policy,
    )


EVIDENCE_ID = "production-service-slo-window"
DEFAULT_OUTPUT = Path("production-service-slo-window.json")
TELEMETRY_FIELDS = frozenset(
    {
        "schema_version",
        "telemetry_source",
        "deployed_commit",
        "window_start",
        "window_end",
        "eligible_request_count",
        "successful_request_count",
        "failed_request_count",
        "read_latency_p95_ms",
        "operational_snapshot_age_seconds",
    }
)
COMMIT_SHA_PATTERN = re.compile(r"[0-9a-f]{40}")


def _now_utc() -> datetime:
    return datetime.now(timezone.utc)


def _parse_timestamp(value: object) -> datetime | None:
    if not isinstance(value, str) or not value.strip():
        return None
    raw = value.strip().replace("Z", "+00:00")
    try:
        parsed = datetime.fromisoformat(raw)
    except ValueError:
        return None
    if parsed.tzinfo is None:
        return None
    return parsed.astimezone(timezone.utc)


def _non_negative_int(value: object) -> int | None:
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        return None
    return value


def _non_negative_float(value: object) -> float | None:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    number = float(value)
    return number if math.isfinite(number) and number >= 0 else None


def _reject_non_finite_json_constant(value: str) -> None:
    raise ValueError(f"non-finite JSON number is not allowed: {value}")


def _requirement(policy: dict[str, Any]) -> dict[str, Any]:
    requirements = policy.get("required_evidence")
    if isinstance(requirements, list):
        for requirement in requirements:
            if isinstance(requirement, dict) and requirement.get("id") == EVIDENCE_ID:
                return requirement
    raise ValueError(f"Operational readiness policy does not define {EVIDENCE_ID}")


def _objective_results(
    policy: dict[str, Any], metrics: dict[str, float]
) -> list[dict[str, object]]:
    results: list[dict[str, object]] = []
    objectives = policy.get("service_level_objectives")
    if not isinstance(objectives, list):
        return results
    for objective in objectives:
        if (
            not isinstance(objective, dict)
            or objective.get("evidence_id") != EVIDENCE_ID
        ):
            continue
        metric = str(objective.get("metric") or "")
        comparison = str(objective.get("comparison") or "")
        target = float(objective.get("target") or 0)
        actual = metrics.get(metric)
        passed = actual is not None and (
            (comparison == "gte" and actual >= target)
            or (comparison == "lte" and actual <= target)
        )
        results.append(
            {
                "name": f"slo:{objective.get('id')}",
                "status": "pass" if passed else "fail",
                "metric": metric,
                "comparison": comparison,
                "target": target,
                "actual": actual,
            }
        )
    return results


def build_evidence(
    telemetry: dict[str, Any],
    *,
    policy: dict[str, Any],
    current_commit: str,
    source_tree_clean: bool,
    telemetry_input_sha256: str,
    generated_at: datetime | None = None,
) -> dict[str, Any]:
    raw_now = generated_at or _now_utc()
    if raw_now.tzinfo is None:
        raise ValueError("generated_at must be timezone-aware")
    now = raw_now.astimezone(timezone.utc)
    requirement = _requirement(policy)
    contract_issues: list[str] = []
    count_issues: list[str] = []
    window_issues: list[str] = []
    candidate_issues: list[str] = []

    telemetry_fields = set(telemetry)
    missing = sorted(TELEMETRY_FIELDS - telemetry_fields)
    unexpected = sorted(telemetry_fields - TELEMETRY_FIELDS)
    if missing:
        contract_issues.append(
            f"telemetry export is missing fields: {', '.join(missing)}"
        )
    if unexpected:
        contract_issues.append(
            f"telemetry export has unsupported fields: {', '.join(unexpected)}"
        )
    if telemetry.get("schema_version") != 1:
        contract_issues.append("telemetry schema_version must be 1")
    telemetry_source = str(telemetry.get("telemetry_source") or "").strip()
    if SAFE_TELEMETRY_SOURCE_PATTERN.fullmatch(telemetry_source) is None:
        contract_issues.append("telemetry_source must be a credential-free identifier")
    if SHA256_PATTERN.fullmatch(telemetry_input_sha256) is None:
        contract_issues.append("telemetry input SHA-256 is invalid")
    deployed_commit = str(telemetry.get("deployed_commit") or "").strip().lower()

    eligible = _non_negative_int(telemetry.get("eligible_request_count"))
    successful = _non_negative_int(telemetry.get("successful_request_count"))
    failed = _non_negative_int(telemetry.get("failed_request_count"))
    for field, value in (
        ("eligible_request_count", eligible),
        ("successful_request_count", successful),
        ("failed_request_count", failed),
    ):
        if value is None:
            count_issues.append(f"{field} must be a non-negative integer")
    if eligible == 0:
        count_issues.append("eligible_request_count must be greater than zero")
    if None not in (eligible, successful, failed) and successful + failed != eligible:
        count_issues.append(
            "successful_request_count + failed_request_count must equal eligible_request_count"
        )

    successful_ratio = (
        successful / eligible if eligible and successful is not None else 0.0
    )
    failed_ratio = failed / eligible if eligible and failed is not None else 1.0
    latency_p95 = _non_negative_float(telemetry.get("read_latency_p95_ms"))
    snapshot_age = _non_negative_float(
        telemetry.get("operational_snapshot_age_seconds")
    )
    if latency_p95 is None:
        contract_issues.append("read_latency_p95_ms must be a non-negative number")
    if snapshot_age is None:
        contract_issues.append(
            "operational_snapshot_age_seconds must be a non-negative number"
        )

    window_start = _parse_timestamp(telemetry.get("window_start"))
    window_end = _parse_timestamp(telemetry.get("window_end"))
    if window_start is None or window_end is None:
        window_issues.append(
            "window_start and window_end must be timezone-aware ISO-8601 timestamps"
        )
    elif window_end <= window_start:
        window_issues.append("window_end must be after window_start")
    else:
        if window_end - window_start < timedelta(days=30):
            window_issues.append("production telemetry must cover at least 30 days")
        age_hours = (now - window_end).total_seconds() / 3600
        maximum_age_hours = float(requirement.get("maximum_age_hours") or 0)
        if age_hours < -0.1:
            window_issues.append("production telemetry window cannot end in the future")
        elif maximum_age_hours and age_hours > maximum_age_hours:
            window_issues.append(
                f"production telemetry window is stale ({age_hours:.1f}h > {maximum_age_hours:.1f}h)"
            )

    if COMMIT_SHA_PATTERN.fullmatch(current_commit) is None:
        candidate_issues.append("current git commit must be a full 40-character SHA")
    elif COMMIT_SHA_PATTERN.fullmatch(deployed_commit) is None:
        candidate_issues.append(
            "telemetry deployed_commit must be a full 40-character SHA"
        )
    elif deployed_commit != current_commit.lower():
        candidate_issues.append(
            f"telemetry deployed_commit must match current git commit {current_commit}"
        )
    if source_tree_clean is not True:
        candidate_issues.append(
            "tracked source tree must be clean before production evidence is written"
        )

    metrics = {
        "successful_request_ratio": successful_ratio,
        "failed_request_ratio": failed_ratio,
        "read_latency_p95_ms": latency_p95 if latency_p95 is not None else -1.0,
        "operational_snapshot_age_seconds": snapshot_age
        if snapshot_age is not None
        else -1.0,
    }
    objective_results = _objective_results(policy, metrics)
    objective_issues = [
        f"{result['metric']} did not satisfy the production objective"
        for result in objective_results
        if result["status"] != "pass"
    ]
    issues = (
        contract_issues
        + count_issues
        + window_issues
        + candidate_issues
        + objective_issues
    )
    suite_results: list[dict[str, object]] = [
        {
            "name": "telemetry-contract",
            "status": "pass" if not contract_issues else "fail",
        },
        {
            "name": "request-accounting",
            "status": "pass" if not count_issues else "fail",
        },
        {
            "name": "telemetry-window",
            "status": "pass" if not window_issues else "fail",
        },
        {
            "name": "candidate-source",
            "status": "pass" if not candidate_issues else "fail",
        },
        *objective_results,
    ]
    promotion_eligible = not issues
    return {
        "ok": promotion_eligible,
        "evidence_id": EVIDENCE_ID,
        "status": "pass" if promotion_eligible else "fail",
        "generated_at": now.isoformat(),
        "commit": current_commit,
        "source_tree_clean": source_tree_clean,
        "policy_sha256": policy_sha256(policy),
        "secrets_redacted": True,
        "read_only": True,
        "order_submission_attempted": False,
        "promotion_eligible": promotion_eligible,
        "telemetry_source": telemetry_source,
        "deployed_commit": deployed_commit,
        "telemetry_input_sha256": telemetry_input_sha256,
        "window_start": str(telemetry.get("window_start") or ""),
        "window_end": str(telemetry.get("window_end") or ""),
        "eligible_request_count": eligible if eligible is not None else -1,
        "successful_request_count": successful if successful is not None else -1,
        "failed_request_count": failed if failed is not None else -1,
        **metrics,
        "suite_results": suite_results,
        "issues": issues,
    }


def _resolve_output_path(policy: dict[str, Any], output: Path) -> Path:
    flags = policy.get("policy") if isinstance(policy.get("policy"), dict) else {}
    evidence_root = (
        REPO_ROOT
        / str(flags.get("evidence_artifact_dir") or "artifacts/operational-readiness")
    ).resolve()
    try:
        evidence_root.relative_to(REPO_ROOT.resolve())
    except ValueError as exc:
        raise ValueError(
            "Configured evidence directory must stay inside the repository"
        ) from exc
    if output.is_absolute():
        candidate = output
    else:
        try:
            repo_relative_evidence_root = evidence_root.relative_to(REPO_ROOT.resolve())
            output.relative_to(repo_relative_evidence_root)
        except ValueError:
            # Bare filenames are resolved inside the configured evidence root.
            candidate = evidence_root / output
        else:
            # CI workflows commonly pass a repository-relative artifact path.
            candidate = REPO_ROOT / output
    candidate = candidate.resolve()
    try:
        candidate.relative_to(evidence_root)
    except ValueError as exc:
        raise ValueError(f"Evidence output must stay inside {evidence_root}") from exc
    return candidate


def _atomic_write_json(path: Path, payload: dict[str, Any]) -> None:
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


def import_evidence(
    input_path: Path,
    *,
    policy_path: Path = DEFAULT_POLICY_PATH,
) -> dict[str, Any]:
    resolved_policy_path = (
        policy_path if policy_path.is_absolute() else REPO_ROOT / policy_path
    )
    policy = load_policy(resolved_policy_path)
    policy_issues = validate_policy(policy)
    if policy_issues:
        return {"ok": False, "status": "fail", "issues": policy_issues}
    raw = input_path.read_bytes()
    try:
        telemetry = json.loads(
            raw.decode("utf-8"),
            parse_constant=_reject_non_finite_json_constant,
        )
    except (UnicodeError, json.JSONDecodeError, ValueError) as exc:
        raise ValueError(f"{input_path} is not valid UTF-8 JSON: {exc}") from exc
    if not isinstance(telemetry, dict):
        raise ValueError(f"{input_path} must contain a JSON object")
    return build_evidence(
        telemetry,
        policy=policy,
        current_commit=_current_commit(REPO_ROOT),
        source_tree_clean=_source_tree_clean(REPO_ROOT),
        telemetry_input_sha256=hashlib.sha256(raw).hexdigest(),
    )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", type=Path, required=True)
    parser.add_argument("--policy", type=Path, default=DEFAULT_POLICY_PATH)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args(argv)
    try:
        report = import_evidence(args.input, policy_path=args.policy)
        if report.get("ok") is True:
            policy_path = (
                args.policy if args.policy.is_absolute() else REPO_ROOT / args.policy
            )
            output_path = _resolve_output_path(load_policy(policy_path), args.output)
            _atomic_write_json(output_path, report)
            report["output_path"] = str(output_path)
    except (OSError, ValueError) as exc:
        report = {"ok": False, "status": "fail", "issues": [str(exc)]}
    if args.json:
        print(json.dumps(report, indent=2, sort_keys=True))
    else:
        print(f"Production SLO evidence import: {report.get('status', 'fail')}")
        for issue in report.get("issues", []):
            print(f"- {issue}")
    return 0 if report.get("ok") is True else 1


if __name__ == "__main__":
    raise SystemExit(main())
