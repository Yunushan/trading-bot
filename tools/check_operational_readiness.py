#!/usr/bin/env python3
"""Validate operational SLO/DR policy and optional promotion evidence."""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import re
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


REPO_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_POLICY_PATH = Path("docs/operational-readiness-policy.json")
REQUIRED_POLICY_FLAGS = (
    "no_assumed_passes",
    "production_promotion_requires_current_commit",
    "production_promotion_requires_clean_source",
    "production_promotion_requires_all_evidence",
    "read_only_service_probe",
    "order_submission_forbidden",
    "secrets_must_be_redacted",
)
REQUIRED_EVIDENCE_FIELDS = (
    "evidence_id",
    "status",
    "generated_at",
    "commit",
    "source_tree_clean",
    "policy_sha256",
    "secrets_redacted",
    "read_only",
    "order_submission_attempted",
    "promotion_eligible",
    "suite_results",
)
SAFE_TELEMETRY_SOURCE_PATTERN = re.compile(r"[A-Za-z0-9][A-Za-z0-9._:/-]{0,255}")
SHA256_PATTERN = re.compile(r"[0-9a-f]{64}")
COMMIT_SHA_PATTERN = re.compile(r"[0-9a-f]{40}")
RATIO_TOLERANCE = 1e-12


def _reject_non_finite_json_constant(value: str) -> None:
    raise ValueError(f"non-finite JSON number is not allowed: {value}")


def load_policy(path: Path) -> dict[str, Any]:
    try:
        payload = json.loads(
            path.read_text(encoding="utf-8"),
            parse_constant=_reject_non_finite_json_constant,
        )
    except (json.JSONDecodeError, ValueError) as exc:
        raise ValueError(f"{path} is not valid JSON: {exc}") from exc
    except OSError as exc:
        raise ValueError(f"Unable to read {path}: {exc}") from exc
    if not isinstance(payload, dict):
        raise ValueError(f"{path} must contain a JSON object")
    return payload


def policy_sha256(policy: dict[str, Any]) -> str:
    canonical = json.dumps(
        policy,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    ).encode("utf-8")
    return hashlib.sha256(canonical).hexdigest()


def _nonempty_string(value: object) -> bool:
    return isinstance(value, str) and bool(value.strip())


def _number(
    value: object, *, minimum: float | None = None, maximum: float | None = None
) -> bool:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return False
    number = float(value)
    if not math.isfinite(number):
        return False
    if minimum is not None and number < minimum:
        return False
    if maximum is not None and number > maximum:
        return False
    return True


def _non_negative_integer(value: object) -> int | None:
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        return None
    return value


def _unique_ids(items: object, *, field: str, issues: list[str]) -> set[str]:
    if not isinstance(items, list) or not items:
        issues.append(f"{field} must be a non-empty list")
        return set()
    ids: list[str] = []
    for index, item in enumerate(items):
        if not isinstance(item, dict):
            issues.append(f"{field}[{index}] must be an object")
            continue
        item_id = str(item.get("id") or "").strip()
        if not item_id:
            issues.append(f"{field}[{index}].id is required")
            continue
        ids.append(item_id)
    duplicates = sorted({item_id for item_id in ids if ids.count(item_id) > 1})
    if duplicates:
        issues.append(f"{field} has duplicate ids: {', '.join(duplicates)}")
    return set(ids)


def validate_policy(policy: dict[str, Any]) -> list[str]:
    issues: list[str] = []
    if policy.get("schema_version") != 1:
        issues.append("schema_version must be 1")

    policy_flags = policy.get("policy")
    if not isinstance(policy_flags, dict):
        issues.append("policy must be an object")
        policy_flags = {}
    for flag in REQUIRED_POLICY_FLAGS:
        if policy_flags.get(flag) is not True:
            issues.append(f"policy.{flag} must be true")
    evidence_dir = policy_flags.get("evidence_artifact_dir")
    if not _nonempty_string(evidence_dir):
        issues.append("policy.evidence_artifact_dir must be a non-empty relative path")
    elif Path(str(evidence_dir)).is_absolute() or ".." in Path(str(evidence_dir)).parts:
        issues.append("policy.evidence_artifact_dir must stay inside the repository")

    slos = policy.get("service_level_objectives")
    _unique_ids(slos, field="service_level_objectives", issues=issues)
    if isinstance(slos, list):
        for index, slo in enumerate(slos):
            if not isinstance(slo, dict):
                continue
            prefix = f"service_level_objectives[{index}]"
            for field in ("metric", "window", "owner", "evidence_id"):
                if not _nonempty_string(slo.get(field)):
                    issues.append(f"{prefix}.{field} is required")
            if slo.get("comparison") not in {"gte", "lte"}:
                issues.append(f"{prefix}.comparison must be gte or lte")
            if not _number(slo.get("target"), minimum=0):
                issues.append(f"{prefix}.target must be a non-negative number")

    recovery = policy.get("recovery_objectives")
    _unique_ids(recovery, field="recovery_objectives", issues=issues)
    if isinstance(recovery, list):
        for index, objective in enumerate(recovery):
            if not isinstance(objective, dict):
                continue
            prefix = f"recovery_objectives[{index}]"
            for field in ("asset", "owner", "evidence_id"):
                if not _nonempty_string(objective.get(field)):
                    issues.append(f"{prefix}.{field} is required")
            for field in ("rto_seconds", "rpo_seconds"):
                if not _number(objective.get(field), minimum=0):
                    issues.append(f"{prefix}.{field} must be a non-negative number")

    profiles = policy.get("probe_profiles")
    if not isinstance(profiles, dict):
        issues.append("probe_profiles must be an object")
        profiles = {}
    for profile_name in ("quick", "sustained"):
        profile = profiles.get(profile_name)
        if not isinstance(profile, dict):
            issues.append(f"probe_profiles.{profile_name} must be an object")
            continue
        if profile.get("promotion_eligible") is not (profile_name == "sustained"):
            issues.append(
                f"probe_profiles.{profile_name}.promotion_eligible must be "
                f"{str(profile_name == 'sustained').lower()}"
            )
        for field in ("cycles", "minimum_requests"):
            if not _number(profile.get(field), minimum=1):
                issues.append(
                    f"probe_profiles.{profile_name}.{field} must be at least 1"
                )
        for field in ("minimum_duration_seconds", "cycle_interval_seconds"):
            if not _number(profile.get(field), minimum=0):
                issues.append(
                    f"probe_profiles.{profile_name}.{field} must be non-negative"
                )
        if not _number(profile.get("max_error_rate"), minimum=0, maximum=1):
            issues.append(
                f"probe_profiles.{profile_name}.max_error_rate must be between 0 and 1"
            )
        if not _number(profile.get("max_p95_ms"), minimum=0.001):
            issues.append(f"probe_profiles.{profile_name}.max_p95_ms must be positive")
        endpoints = profile.get("endpoints")
        if not isinstance(endpoints, list) or not endpoints:
            issues.append(
                f"probe_profiles.{profile_name}.endpoints must be a non-empty list"
            )
        elif any(
            not _nonempty_string(endpoint) or not str(endpoint).startswith("/")
            for endpoint in endpoints
        ):
            issues.append(
                f"probe_profiles.{profile_name}.endpoints must contain absolute URL paths"
            )

    evidence = policy.get("required_evidence")
    evidence_ids = _unique_ids(evidence, field="required_evidence", issues=issues)
    if isinstance(evidence, list):
        filenames: list[str] = []
        for index, requirement in enumerate(evidence):
            if not isinstance(requirement, dict):
                continue
            prefix = f"required_evidence[{index}]"
            for field in ("kind", "filename"):
                if not _nonempty_string(requirement.get(field)):
                    issues.append(f"{prefix}.{field} is required")
            filename = str(requirement.get("filename") or "")
            if filename:
                filenames.append(filename)
                if Path(filename).name != filename or not filename.endswith(".json"):
                    issues.append(
                        f"{prefix}.filename must be a JSON filename without directories"
                    )
            if requirement.get("required_for_production") is not True:
                issues.append(f"{prefix}.required_for_production must be true")
            if not _number(requirement.get("maximum_age_hours"), minimum=1):
                issues.append(f"{prefix}.maximum_age_hours must be at least 1")
            required_fields = requirement.get("required_fields")
            if not isinstance(required_fields, list) or not required_fields:
                issues.append(f"{prefix}.required_fields must be a non-empty list")
            else:
                missing_fields = sorted(
                    set(REQUIRED_EVIDENCE_FIELDS)
                    - {str(item) for item in required_fields}
                )
                if missing_fields:
                    issues.append(
                        f"{prefix}.required_fields is missing: {', '.join(missing_fields)}"
                    )
        duplicate_filenames = sorted(
            {name for name in filenames if filenames.count(name) > 1}
        )
        if duplicate_filenames:
            issues.append(
                f"required_evidence has duplicate filenames: {', '.join(duplicate_filenames)}"
            )

    referenced_evidence: set[str] = set()
    for collection_name in ("service_level_objectives", "recovery_objectives"):
        collection = policy.get(collection_name)
        if isinstance(collection, list):
            referenced_evidence.update(
                str(item.get("evidence_id") or "").strip()
                for item in collection
                if isinstance(item, dict)
            )
    unknown = sorted(
        item for item in referenced_evidence if item and item not in evidence_ids
    )
    if unknown:
        issues.append(
            f"objectives reference unknown evidence ids: {', '.join(unknown)}"
        )
    return issues


def _current_commit(root: Path) -> str:
    try:
        return subprocess.check_output(
            ["git", "rev-parse", "HEAD"],
            cwd=root,
            text=True,
            stderr=subprocess.DEVNULL,
        ).strip()
    except (OSError, subprocess.CalledProcessError):
        return ""


def _source_tree_clean(root: Path) -> bool | None:
    try:
        completed = subprocess.run(
            ["git", "status", "--porcelain", "--untracked-files=all"],
            cwd=root,
            text=True,
            capture_output=True,
            check=False,
        )
    except OSError:
        return None
    if completed.returncode != 0:
        return None
    ignored_prefixes = (
        "artifacts/operational-readiness/",
        "artifacts/native-source-sync/",
        "artifacts/rust-native-runtime-evidence/",
        "release-platform-evidence/",
    )
    dirty_paths: list[str] = []
    for line in completed.stdout.splitlines():
        path = line[3:].strip().replace("\\", "/")
        if " -> " in path:
            path = path.split(" -> ", 1)[1]
        if not any(path.startswith(prefix) for prefix in ignored_prefixes):
            dirty_paths.append(path)
    return not dirty_paths


def _parse_timestamp(value: object) -> datetime | None:
    if not _nonempty_string(value):
        return None
    raw = str(value).strip().replace("Z", "+00:00")
    try:
        parsed = datetime.fromisoformat(raw)
    except ValueError:
        return None
    if parsed.tzinfo is None:
        return None
    return parsed.astimezone(timezone.utc)


def _metric_threshold_issue(
    *,
    path: Path,
    metric: str,
    value: object,
    comparison: str,
    target: object,
) -> str | None:
    if not _number(value, minimum=0) or not _number(target, minimum=0):
        return f"{path} {metric} must be a non-negative number"
    actual = float(value)
    threshold = float(target)
    if comparison == "gte" and actual < threshold:
        return f"{path} {metric} {actual:.6f} is below required {threshold:.6f}"
    if comparison == "lte" and actual > threshold:
        return f"{path} {metric} {actual:.6f} exceeds allowed {threshold:.6f}"
    return None


def _validate_evidence_metrics(
    requirement: dict[str, Any],
    payload: dict[str, Any],
    *,
    policy: dict[str, Any],
    path: Path,
) -> list[str]:
    issues: list[str] = []
    evidence_id = str(requirement.get("id") or "")
    if evidence_id == "service-api-sustained-runtime":
        profiles = policy.get("probe_profiles")
        sustained = profiles.get("sustained") if isinstance(profiles, dict) else None
        if not isinstance(sustained, dict):
            return ["probe_profiles.sustained is unavailable for evidence validation"]
        checks = (
            (
                "duration_seconds",
                payload.get("duration_seconds"),
                "gte",
                sustained.get("minimum_duration_seconds"),
            ),
            (
                "request_count",
                payload.get("request_count"),
                "gte",
                sustained.get("minimum_requests"),
            ),
            (
                "error_rate",
                payload.get("error_rate"),
                "lte",
                sustained.get("max_error_rate"),
            ),
        )
        for metric, value, comparison, target in checks:
            issue = _metric_threshold_issue(
                path=path,
                metric=metric,
                value=value,
                comparison=comparison,
                target=target,
            )
            if issue:
                issues.append(issue)
        latency = payload.get("latency_ms")
        p95 = latency.get("p95") if isinstance(latency, dict) else None
        issue = _metric_threshold_issue(
            path=path,
            metric="latency_ms.p95",
            value=p95,
            comparison="lte",
            target=sustained.get("max_p95_ms"),
        )
        if issue:
            issues.append(issue)
        freshness_targets = [
            objective.get("target")
            for objective in policy.get("service_level_objectives", [])
            if isinstance(objective, dict)
            and objective.get("metric") == "operational_snapshot_age_seconds"
            and objective.get("comparison") == "lte"
        ]
        if freshness_targets:
            issue = _metric_threshold_issue(
                path=path,
                metric="operational_snapshot_max_age_seconds",
                value=payload.get("operational_snapshot_max_age_seconds"),
                comparison="lte",
                target=min(float(value) for value in freshness_targets),
            )
            if issue:
                issues.append(issue)
        sample_count = _non_negative_integer(
            payload.get("operational_snapshot_sample_count")
        )
        expected_count = _non_negative_integer(
            payload.get("operational_snapshot_expected_count")
        )
        if sample_count is None or sample_count <= 0:
            issues.append(
                f"{path} operational_snapshot_sample_count must be a positive integer"
            )
        if expected_count is None or expected_count <= 0:
            issues.append(
                f"{path} operational_snapshot_expected_count must be a positive integer"
            )
        if (
            sample_count is not None
            and expected_count is not None
            and sample_count != expected_count
        ):
            issues.append(
                f"{path} operational snapshot sample count must equal the expected count"
            )
        deployed_commit = str(payload.get("deployed_commit") or "").strip()
        evidence_commit = str(payload.get("commit") or "").strip()
        if not deployed_commit or deployed_commit != evidence_commit:
            issues.append(f"{path} deployed_commit must match the evidence commit")
        if payload.get("evidence_scope") != "deployed-sustained-service-api-probe":
            issues.append(
                f"{path} must come from a deployed sustained service API probe"
            )
        environment = payload.get("environment")
        if (
            not isinstance(environment, dict)
            or environment.get("transport") != "external-https"
        ):
            issues.append(f"{path} production probe transport must be external-https")

    if evidence_id == "production-service-slo-window":
        window_start = _parse_timestamp(payload.get("window_start"))
        window_end = _parse_timestamp(payload.get("window_end"))
        if window_start is None or window_end is None:
            issues.append(
                f"{path} window_start and window_end must be timezone-aware ISO-8601 timestamps"
            )
        elif window_end <= window_start:
            issues.append(f"{path} window_end must be after window_start")
        else:
            if (window_end - window_start).total_seconds() < 30 * 24 * 60 * 60:
                issues.append(
                    f"{path} production SLO evidence must cover at least 30 days"
                )
            maximum_age = float(requirement.get("maximum_age_hours") or 0)
            window_age_hours = (
                datetime.now(timezone.utc) - window_end
            ).total_seconds() / 3600
            if window_age_hours < -0.1:
                issues.append(f"{path} production SLO window cannot end in the future")
            elif maximum_age and window_age_hours > maximum_age:
                issues.append(
                    f"{path} production SLO window is stale "
                    f"({window_age_hours:.1f}h > {maximum_age:.1f}h)"
                )

        telemetry_source = payload.get("telemetry_source")
        if (
            not isinstance(telemetry_source, str)
            or SAFE_TELEMETRY_SOURCE_PATTERN.fullmatch(telemetry_source.strip()) is None
        ):
            issues.append(
                f"{path} telemetry_source must be a credential-free identifier"
            )
        telemetry_hash = payload.get("telemetry_input_sha256")
        if (
            not isinstance(telemetry_hash, str)
            or SHA256_PATTERN.fullmatch(telemetry_hash) is None
        ):
            issues.append(
                f"{path} telemetry_input_sha256 must be a lowercase SHA-256 digest"
            )
        deployed_commit = str(payload.get("deployed_commit") or "").strip().lower()
        evidence_commit = str(payload.get("commit") or "").strip().lower()
        if COMMIT_SHA_PATTERN.fullmatch(deployed_commit) is None:
            issues.append(
                f"{path} deployed_commit must be a full 40-character SHA"
            )
        elif deployed_commit != evidence_commit:
            issues.append(f"{path} deployed_commit must match the evidence commit")

        eligible = _non_negative_integer(payload.get("eligible_request_count"))
        successful = _non_negative_integer(payload.get("successful_request_count"))
        failed = _non_negative_integer(payload.get("failed_request_count"))
        for field, value in (
            ("eligible_request_count", eligible),
            ("successful_request_count", successful),
            ("failed_request_count", failed),
        ):
            if value is None:
                issues.append(f"{path} {field} must be a non-negative integer")
        if eligible == 0:
            issues.append(f"{path} eligible_request_count must be greater than zero")
        if (
            None not in (eligible, successful, failed)
            and successful + failed != eligible
        ):
            issues.append(
                f"{path} successful_request_count + failed_request_count must equal "
                "eligible_request_count"
            )

        successful_ratio = payload.get("successful_request_ratio")
        failed_ratio = payload.get("failed_request_ratio")
        if not _number(successful_ratio, minimum=0, maximum=1):
            issues.append(f"{path} successful_request_ratio must be between 0 and 1")
        if not _number(failed_ratio, minimum=0, maximum=1):
            issues.append(f"{path} failed_request_ratio must be between 0 and 1")
        if _number(successful_ratio, minimum=0, maximum=1) and _number(
            failed_ratio,
            minimum=0,
            maximum=1,
        ):
            ratio_sum = float(successful_ratio) + float(failed_ratio)
            if abs(ratio_sum - 1.0) > RATIO_TOLERANCE:
                issues.append(
                    f"{path} successful and failed request ratios must sum to 1"
                )
            if eligible and successful is not None:
                expected = successful / eligible
                if abs(float(successful_ratio) - expected) > RATIO_TOLERANCE:
                    issues.append(
                        f"{path} successful_request_ratio does not match request counts"
                    )
            if eligible and failed is not None:
                expected = failed / eligible
                if abs(float(failed_ratio) - expected) > RATIO_TOLERANCE:
                    issues.append(
                        f"{path} failed_request_ratio does not match request counts"
                    )
        objectives = policy.get("service_level_objectives")
        if isinstance(objectives, list):
            for objective in objectives:
                if (
                    not isinstance(objective, dict)
                    or objective.get("evidence_id") != evidence_id
                ):
                    continue
                metric = str(objective.get("metric") or "")
                issue = _metric_threshold_issue(
                    path=path,
                    metric=metric,
                    value=payload.get(metric),
                    comparison=str(objective.get("comparison") or ""),
                    target=objective.get("target"),
                )
                if issue:
                    issues.append(issue)

    recovery_objectives = policy.get("recovery_objectives")
    matching_recovery = (
        [
            objective
            for objective in recovery_objectives
            if isinstance(objective, dict)
            and objective.get("evidence_id") == evidence_id
        ]
        if isinstance(recovery_objectives, list)
        else []
    )
    if matching_recovery:
        rto_target = min(
            float(objective["rto_seconds"]) for objective in matching_recovery
        )
        rpo_target = min(
            float(objective["rpo_seconds"]) for objective in matching_recovery
        )
        for metric, target in (
            ("recovery_time_seconds", rto_target),
            ("recovery_point_seconds", rpo_target),
        ):
            issue = _metric_threshold_issue(
                path=path,
                metric=metric,
                value=payload.get(metric),
                comparison="lte",
                target=target,
            )
            if issue:
                issues.append(issue)
    if evidence_id == "service-config-backup-restore":
        objectives_by_id = {
            str(objective.get("id") or ""): objective
            for objective in matching_recovery
            if isinstance(objective, dict)
        }
        for metric, objective_id in (
            ("config_recovery_time_seconds", "service-config-recovery"),
            ("service_recovery_time_seconds", "service-process-recovery"),
        ):
            objective = objectives_by_id.get(objective_id)
            target = (
                objective.get("rto_seconds") if isinstance(objective, dict) else None
            )
            issue = _metric_threshold_issue(
                path=path,
                metric=metric,
                value=payload.get(metric),
                comparison="lte",
                target=target,
            )
            if issue:
                issues.append(issue)
        suite_results = payload.get("suite_results")
        result_by_name = (
            {
                str(item.get("name") or ""): item
                for item in suite_results
                if isinstance(item, dict)
            }
            if isinstance(suite_results, list)
            else {}
        )
        for required_name in (
            "config-backup-secret-redaction",
            "config-restore-round-trip",
            "synthetic-credential-cleanup",
            "canonical-service-process-restart",
        ):
            result = result_by_name.get(required_name)
            if not isinstance(result, dict) or result.get("status") != "pass":
                issues.append(
                    f"{path} must include a passing {required_name} suite result"
                )
        process_result = result_by_name.get("canonical-service-process-restart")
        if (
            not isinstance(process_result, dict)
            or process_result.get("process_boundary") != "child-process"
        ):
            issues.append(
                f"{path} service restart must be proven across a child-process boundary"
            )
    return issues


def _validate_evidence(
    requirement: dict[str, Any],
    *,
    policy: dict[str, Any],
    path: Path,
    expected_policy_hash: str,
    expected_commit: str,
    require_current_commit: bool,
    require_clean_source: bool,
) -> list[str]:
    issues: list[str] = []
    if not path.is_file():
        return [f"missing evidence artifact: {path}"]
    try:
        payload = load_policy(path)
    except ValueError as exc:
        return [str(exc)]

    required_fields = {str(field) for field in requirement.get("required_fields", [])}
    missing = sorted(field for field in required_fields if field not in payload)
    if missing:
        issues.append(f"{path} is missing fields: {', '.join(missing)}")
    evidence_id = str(requirement.get("id") or "")
    if payload.get("evidence_id") != evidence_id:
        issues.append(f"{path} evidence_id must be {evidence_id}")
    if payload.get("status") != "pass":
        issues.append(f"{path} status must be pass")
    if payload.get("policy_sha256") != expected_policy_hash:
        issues.append(f"{path} policy_sha256 does not match the current policy")
    if payload.get("secrets_redacted") is not True:
        issues.append(f"{path} secrets_redacted must be true")
    if payload.get("read_only") is not True:
        issues.append(f"{path} read_only must be true")
    if payload.get("order_submission_attempted") is not False:
        issues.append(f"{path} order_submission_attempted must be false")
    if payload.get("promotion_eligible") is not True:
        issues.append(f"{path} promotion_eligible must be true")
    if not isinstance(payload.get("source_tree_clean"), bool):
        issues.append(f"{path} source_tree_clean must be boolean")
    if require_clean_source and payload.get("source_tree_clean") is not True:
        issues.append(f"{path} source_tree_clean must be true for production promotion")
    commit = str(payload.get("commit") or "").strip()
    if not commit:
        issues.append(f"{path} commit is required")
    elif require_current_commit and commit != expected_commit:
        issues.append(f"{path} commit must match current git commit {expected_commit}")

    generated_at = _parse_timestamp(payload.get("generated_at"))
    if generated_at is None:
        issues.append(f"{path} generated_at must be an ISO-8601 timestamp")
    else:
        maximum_age = float(requirement.get("maximum_age_hours") or 0)
        age_hours = (datetime.now(timezone.utc) - generated_at).total_seconds() / 3600
        if age_hours < -0.1:
            issues.append(f"{path} generated_at cannot be in the future")
        elif maximum_age and age_hours > maximum_age:
            issues.append(
                f"{path} evidence is stale ({age_hours:.1f}h > {maximum_age:.1f}h)"
            )

    suite_results = payload.get("suite_results")
    if not isinstance(suite_results, list) or not suite_results:
        issues.append(f"{path} suite_results must be a non-empty list")
    elif any(
        not isinstance(item, dict) or item.get("status") != "pass"
        for item in suite_results
    ):
        issues.append(f"{path} every suite result must have status pass")
    issues.extend(
        _validate_evidence_metrics(requirement, payload, policy=policy, path=path)
    )
    return issues


def audit_operational_readiness(
    root: Path,
    *,
    policy_path: Path = DEFAULT_POLICY_PATH,
    evidence_dir: Path | None = None,
    require_evidence: bool = False,
    require_current_commit: bool = False,
    require_clean_source: bool = False,
) -> dict[str, Any]:
    resolved_policy_path = (
        policy_path if policy_path.is_absolute() else root / policy_path
    )
    try:
        policy = load_policy(resolved_policy_path)
    except ValueError as exc:
        return {
            "ok": False,
            "schema_ok": False,
            "promotion_ready": False,
            "issues": [str(exc)],
        }

    issues = validate_policy(policy)
    schema_ok = not issues
    policy_hash = policy_sha256(policy)
    policy_flags = (
        policy.get("policy") if isinstance(policy.get("policy"), dict) else {}
    )
    configured_dir = Path(
        str(
            policy_flags.get("evidence_artifact_dir")
            or "artifacts/operational-readiness"
        )
    )
    resolved_evidence_dir = evidence_dir or configured_dir
    if not resolved_evidence_dir.is_absolute():
        resolved_evidence_dir = root / resolved_evidence_dir

    commit = _current_commit(root) if require_current_commit else ""
    current_clean = _source_tree_clean(root) if require_clean_source else None
    if require_current_commit and not commit:
        issues.append("unable to determine current git commit")
    if require_clean_source and current_clean is not True:
        issues.append(
            "current tracked source tree must be clean for production promotion evidence"
        )

    evidence_results: list[dict[str, Any]] = []
    requirements = policy.get("required_evidence")
    if require_evidence and isinstance(requirements, list):
        for requirement in requirements:
            if (
                not isinstance(requirement, dict)
                or requirement.get("required_for_production") is not True
            ):
                continue
            path = resolved_evidence_dir / str(requirement.get("filename") or "")
            evidence_issues = _validate_evidence(
                requirement,
                policy=policy,
                path=path,
                expected_policy_hash=policy_hash,
                expected_commit=commit,
                require_current_commit=require_current_commit,
                require_clean_source=require_clean_source,
            )
            evidence_results.append(
                {
                    "id": str(requirement.get("id") or ""),
                    "path": str(path),
                    "ok": not evidence_issues,
                    "issues": evidence_issues,
                }
            )
            issues.extend(evidence_issues)

    promotion_ready = bool(
        schema_ok and require_evidence and evidence_results and not issues
    )
    return {
        "ok": not issues,
        "schema_ok": schema_ok,
        "promotion_ready": promotion_ready,
        "require_evidence": bool(require_evidence),
        "require_current_commit": bool(require_current_commit),
        "require_clean_source": bool(require_clean_source),
        "current_commit": commit or None,
        "current_source_tree_clean": current_clean,
        "policy_path": str(resolved_policy_path),
        "policy_sha256": policy_hash,
        "evidence_dir": str(resolved_evidence_dir),
        "service_level_objective_count": len(
            policy.get("service_level_objectives") or []
        ),
        "recovery_objective_count": len(policy.get("recovery_objectives") or []),
        "required_evidence_count": len(policy.get("required_evidence") or []),
        "evidence": evidence_results,
        "issues": issues,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--policy", type=Path, default=DEFAULT_POLICY_PATH)
    parser.add_argument("--evidence-dir", type=Path)
    parser.add_argument("--schema-only", action="store_true")
    parser.add_argument("--require-evidence", action="store_true")
    parser.add_argument("--require-current-commit", action="store_true")
    parser.add_argument("--require-clean-source", action="store_true")
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args(argv)
    require_evidence = bool(args.require_evidence and not args.schema_only)
    report = audit_operational_readiness(
        REPO_ROOT,
        policy_path=args.policy,
        evidence_dir=args.evidence_dir,
        require_evidence=require_evidence,
        require_current_commit=bool(args.require_current_commit),
        require_clean_source=bool(args.require_clean_source),
    )
    if args.json:
        print(json.dumps(report, indent=2, sort_keys=True))
    else:
        print(
            "Operational readiness policy: "
            f"{'ok' if report['schema_ok'] else 'failed'}; "
            f"SLOs={report.get('service_level_objective_count', 0)}, "
            f"recovery objectives={report.get('recovery_objective_count', 0)}, "
            f"required evidence={report.get('required_evidence_count', 0)}"
        )
        if require_evidence:
            print(
                f"Production promotion evidence: {'ready' if report['promotion_ready'] else 'not ready'}"
            )
        for issue in report["issues"]:
            print(f"- {issue}", file=sys.stderr)
    return 0 if report["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
