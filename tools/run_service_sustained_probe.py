#!/usr/bin/env python3
"""Run a bounded read-only service API probe and optionally write evidence."""

from __future__ import annotations

import argparse
from dataclasses import dataclass
import json
import math
import os
import platform
import re
import sys
import tempfile
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from urllib.error import HTTPError
from urllib.parse import urlsplit, urlunsplit
from urllib.request import HTTPRedirectHandler, Request, build_opener


REPO_ROOT = Path(__file__).resolve().parents[1]
PYTHON_ROOT = REPO_ROOT / "Languages" / "Python"
if str(PYTHON_ROOT) not in sys.path:
    sys.path.insert(0, str(PYTHON_ROOT))

from app.service.api import create_service_api_app  # noqa: E402
from app.service.runtime import TradingBotService  # noqa: E402

if __package__:
    from .check_operational_readiness import (  # noqa: E402
        DEFAULT_POLICY_PATH,
        _current_commit,
        _source_tree_clean,
        load_policy,
        policy_sha256,
        validate_policy,
    )
else:
    from check_operational_readiness import (  # noqa: E402
        DEFAULT_POLICY_PATH,
        _current_commit,
        _source_tree_clean,
        load_policy,
        policy_sha256,
        validate_policy,
    )


DEFAULT_EVIDENCE_ID = "service-api-sustained-runtime"
API_TOKEN = "operational-readiness-probe-token"
OPERATIONAL_FRESHNESS_TIMESTAMP_FIELDS = {
    "exchange_connector": "generated_at",
    "execution": "heartbeat_at",
    "account": "generated_at",
    "portfolio": "generated_at",
}
MAX_FUTURE_CLOCK_SKEW_SECONDS = 5.0
DEFAULT_API_TOKEN_ENV = "BOT_SERVICE_API_TOKEN"


@dataclass(frozen=True, slots=True)
class _RemoteResponse:
    status_code: int
    body: bytes

    def json(self) -> object:
        return json.loads(self.body.decode("utf-8"))


class _NoRedirectHandler(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):  # noqa: ANN001, ANN201
        return None


class _RemoteReadOnlyClient:
    def __init__(self, base_url: str, *, timeout_seconds: float) -> None:
        self._base_url = base_url.rstrip("/")
        self._timeout_seconds = timeout_seconds
        self._opener = build_opener(_NoRedirectHandler)

    def __enter__(self) -> _RemoteReadOnlyClient:
        return self

    def __exit__(self, _exc_type, _exc, _traceback) -> None:
        return None

    def get(self, endpoint: str, *, headers: dict[str, str]) -> _RemoteResponse:
        request = Request(
            f"{self._base_url}{endpoint}",
            headers={**headers, "Accept": "application/json"},
            method="GET",
        )
        try:
            with self._opener.open(request, timeout=self._timeout_seconds) as response:  # noqa: S310
                return _RemoteResponse(
                    status_code=int(response.status), body=response.read()
                )
        except HTTPError as exc:
            return _RemoteResponse(status_code=int(exc.code), body=exc.read())


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _percentile(values: list[float], percentile: float) -> float:
    if not values:
        return 0.0
    ordered = sorted(values)
    position = (len(ordered) - 1) * percentile
    lower = int(position)
    upper = min(lower + 1, len(ordered) - 1)
    fraction = position - lower
    return ordered[lower] + (ordered[upper] - ordered[lower]) * fraction


def _parse_timestamp(value: object) -> datetime | None:
    raw = str(value or "").strip().replace("Z", "+00:00")
    if not raw:
        return None
    try:
        parsed = datetime.fromisoformat(raw)
    except ValueError:
        return None
    if parsed.tzinfo is None:
        return None
    return parsed.astimezone(timezone.utc)


def _finite_non_negative_float(value: object) -> float | None:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    number = float(value)
    return number if math.isfinite(number) and number >= 0 else None


def _operational_snapshot_freshness_samples(
    payload: object,
    *,
    observed_at: datetime | None = None,
) -> tuple[list[float], list[str]]:
    now = (observed_at or datetime.now(timezone.utc)).astimezone(timezone.utc)
    if not isinstance(payload, dict):
        return [], ["operational preflight payload must be an object"]
    freshness = payload.get("freshness")
    if not isinstance(freshness, dict):
        return [], ["operational preflight freshness must be an object"]

    ages: list[float] = []
    issues: list[str] = []
    for component, timestamp_field in OPERATIONAL_FRESHNESS_TIMESTAMP_FIELDS.items():
        item = freshness.get(component)
        if not isinstance(item, dict):
            issues.append(f"{component} freshness sample is missing")
            continue
        reported_age = _finite_non_negative_float(item.get("age_seconds"))
        timestamp = _parse_timestamp(item.get(timestamp_field))
        stale = item.get("stale")
        if reported_age is None:
            issues.append(f"{component} freshness age is missing or invalid")
            continue
        if timestamp is None:
            issues.append(f"{component} freshness timestamp is missing or invalid")
            continue
        clock_age = (now - timestamp).total_seconds()
        if clock_age < -MAX_FUTURE_CLOCK_SKEW_SECONDS:
            issues.append(f"{component} freshness timestamp is in the future")
            continue
        if not isinstance(stale, bool):
            issues.append(f"{component} freshness stale flag is missing or invalid")
            continue
        ages.append(max(reported_age, max(0.0, clock_age)))
        if stale:
            issues.append(f"{component} freshness sample is stale")
    return ages, issues


def _normalize_base_url(value: str) -> tuple[str, bool]:
    parsed = urlsplit(str(value or "").strip())
    if parsed.scheme not in {"http", "https"} or not parsed.hostname:
        raise ValueError(
            "Probe base URL must use http:// or https:// and include a host"
        )
    if parsed.username or parsed.password:
        raise ValueError("Probe base URL must not contain credentials")
    if parsed.query or parsed.fragment or parsed.path not in {"", "/"}:
        raise ValueError(
            "Probe base URL must be an origin without a path, query, or fragment"
        )
    normalized = urlunsplit((parsed.scheme, parsed.netloc, "", "", ""))
    return normalized, parsed.scheme == "https"


def _payload_build_commit(payload: object) -> str:
    if not isinstance(payload, dict):
        return ""
    candidate = str(payload.get("build_commit") or "").strip().lower()
    return candidate if re.fullmatch(r"[0-9a-f]{7,64}", candidate) else ""


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


def _resolve_output_path(policy: dict[str, Any], output: Path) -> Path:
    policy_flags = (
        policy.get("policy") if isinstance(policy.get("policy"), dict) else {}
    )
    evidence_root = REPO_ROOT / str(
        policy_flags.get("evidence_artifact_dir") or "artifacts/operational-readiness"
    )
    evidence_root = evidence_root.resolve()
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


def run_probe(
    *,
    profile_name: str = "quick",
    policy_path: Path = DEFAULT_POLICY_PATH,
    cycles: int | None = None,
    minimum_duration_seconds: float | None = None,
    minimum_requests: int | None = None,
    cycle_interval_seconds: float | None = None,
    max_error_rate: float | None = None,
    max_p95_ms: float | None = None,
    base_url: str | None = None,
    api_token_env: str = DEFAULT_API_TOKEN_ENV,
    request_timeout_seconds: float = 10.0,
) -> dict[str, Any]:
    resolved_policy_path = (
        policy_path if policy_path.is_absolute() else REPO_ROOT / policy_path
    )
    policy = load_policy(resolved_policy_path)
    policy_issues = validate_policy(policy)
    if policy_issues:
        return {
            "ok": False,
            "status": "fail",
            "profile": profile_name,
            "promotion_eligible": False,
            "issues": policy_issues,
        }
    profiles = policy["probe_profiles"]
    if profile_name not in profiles:
        return {
            "ok": False,
            "status": "fail",
            "profile": profile_name,
            "promotion_eligible": False,
            "issues": [f"Unknown probe profile: {profile_name}"],
        }
    profile = profiles[profile_name]
    endpoints = [str(endpoint) for endpoint in profile["endpoints"]]
    configured_cycles = int(profile["cycles"])
    configured_duration = float(profile["minimum_duration_seconds"])
    configured_requests = int(profile["minimum_requests"])
    actual_cycles = configured_cycles if cycles is None else max(1, int(cycles))
    required_duration = (
        configured_duration
        if minimum_duration_seconds is None
        else max(0.0, float(minimum_duration_seconds))
    )
    required_requests = (
        configured_requests
        if minimum_requests is None
        else max(1, int(minimum_requests))
    )
    cycle_interval = (
        float(profile["cycle_interval_seconds"])
        if cycle_interval_seconds is None
        else max(0.0, float(cycle_interval_seconds))
    )
    allowed_error_rate = (
        float(profile["max_error_rate"])
        if max_error_rate is None
        else max(0.0, min(1.0, float(max_error_rate)))
    )
    allowed_p95_ms = (
        float(profile["max_p95_ms"])
        if max_p95_ms is None
        else max(0.001, float(max_p95_ms))
    )
    timeout_seconds = max(0.1, float(request_timeout_seconds))

    normalized_base_url = ""
    transport_https = False
    if base_url:
        normalized_base_url, transport_https = _normalize_base_url(base_url)
    if profile_name == "sustained" and not normalized_base_url:
        return {
            "ok": False,
            "status": "fail",
            "profile": profile_name,
            "promotion_eligible": False,
            "issues": [
                "The sustained production probe requires --base-url for a deployed service"
            ],
        }

    if normalized_base_url:
        token = str(os.environ.get(api_token_env) or "").strip()
        headers = {"Authorization": f"Bearer {token}"} if token else {}
        client_context: Any = _RemoteReadOnlyClient(
            normalized_base_url,
            timeout_seconds=timeout_seconds,
        )
        transport = "external-https" if transport_https else "external-http"
    else:
        try:
            from fastapi.testclient import TestClient
        except Exception as exc:
            return {
                "ok": False,
                "status": "fail",
                "profile": profile_name,
                "promotion_eligible": False,
                "issues": [f"FastAPI TestClient is unavailable: {type(exc).__name__}"],
            }
        service = TradingBotService()
        probe_timestamp = _now_iso()
        service.set_exchange_connector_snapshot(
            {"health": "ok", "state": "ready", "generated_at": probe_timestamp},
            source="operational-readiness-probe",
        )
        service.set_execution_snapshot(
            state="idle",
            heartbeat_at=probe_timestamp,
            source="operational-readiness-probe",
        )
        service.set_account_snapshot(
            total_balance=0.0,
            available_balance=0.0,
            source="operational-readiness-probe",
        )
        service.set_portfolio_snapshot(source="operational-readiness-probe")
        app = create_service_api_app(
            service=service,
            api_token=API_TOKEN,
            host_context="operational-readiness-probe",
            host_owner="verification-process",
            enable_local_executor=False,
        )
        headers = {"Authorization": f"Bearer {API_TOKEN}"}
        client_context = TestClient(app)
        transport = "fastapi-testclient-in-process"
    latencies: list[float] = []
    endpoint_latencies: dict[str, list[float]] = {
        endpoint: [] for endpoint in endpoints
    }
    endpoint_counts: dict[str, int] = {endpoint: 0 for endpoint in endpoints}
    endpoint_errors: dict[str, int] = {endpoint: 0 for endpoint in endpoints}
    failures: list[dict[str, object]] = []
    snapshot_ages: list[float] = []
    snapshot_freshness_issues: list[str] = []
    snapshot_freshness_issue_count = 0
    observed_deployment_commits: set[str] = set()
    request_count = 0
    completed_cycles = 0
    started = time.perf_counter()

    with client_context as client:
        while True:
            for endpoint in endpoints:
                request_started = time.perf_counter()
                status_code = 0
                error = ""
                payload: object = None
                try:
                    response = client.get(endpoint, headers=headers)
                    status_code = int(response.status_code)
                    if status_code == 200:
                        payload = response.json()
                    else:
                        error = f"HTTP {status_code}"
                except Exception as exc:
                    error = f"{type(exc).__name__}: request failed"
                elapsed_ms = (time.perf_counter() - request_started) * 1000
                latencies.append(elapsed_ms)
                endpoint_latencies[endpoint].append(elapsed_ms)
                endpoint_counts[endpoint] += 1
                request_count += 1
                if error:
                    endpoint_errors[endpoint] += 1
                    if len(failures) < 20:
                        failures.append(
                            {
                                "endpoint": endpoint,
                                "status_code": status_code,
                                "error": error,
                            }
                        )
                if endpoint.endswith("/operational-preflight") and isinstance(
                    payload, dict
                ):
                    ages, freshness_issues = _operational_snapshot_freshness_samples(
                        payload
                    )
                    snapshot_ages.extend(ages)
                    snapshot_freshness_issue_count += len(freshness_issues)
                    remaining_issue_slots = max(0, 20 - len(snapshot_freshness_issues))
                    snapshot_freshness_issues.extend(
                        freshness_issues[:remaining_issue_slots]
                    )
                observed_commit = _payload_build_commit(payload)
                if observed_commit:
                    observed_deployment_commits.add(observed_commit)
            completed_cycles += 1
            elapsed = time.perf_counter() - started
            minimums_met = (
                completed_cycles >= actual_cycles
                and request_count >= required_requests
                and elapsed >= required_duration
            )
            if minimums_met:
                break
            if cycle_interval > 0:
                time.sleep(cycle_interval)

    duration = time.perf_counter() - started
    error_count = sum(endpoint_errors.values())
    error_rate = error_count / request_count if request_count else 1.0
    snapshot_expected_count = sum(
        endpoint_counts[endpoint]
        for endpoint in endpoints
        if endpoint.endswith("/runtime/operational-preflight")
    ) * len(OPERATIONAL_FRESHNESS_TIMESTAMP_FIELDS)
    snapshot_sample_count = len(snapshot_ages)
    snapshot_samples_complete = bool(
        snapshot_expected_count > 0 and snapshot_sample_count == snapshot_expected_count
    )
    snapshot_max_age = max(snapshot_ages) if snapshot_ages else None
    freshness_targets = [
        float(objective["target"])
        for objective in policy.get("service_level_objectives", [])
        if isinstance(objective, dict)
        and objective.get("metric") == "operational_snapshot_age_seconds"
        and objective.get("comparison") == "lte"
    ]
    snapshot_max_age_limit = min(freshness_targets) if freshness_targets else None
    snapshot_freshness_pass = bool(
        snapshot_samples_complete
        and snapshot_freshness_issue_count == 0
        and snapshot_max_age is not None
        and snapshot_max_age_limit is not None
        and snapshot_max_age <= snapshot_max_age_limit
    )
    latency_summary = {
        "p50": round(_percentile(latencies, 0.50), 3),
        "p95": round(_percentile(latencies, 0.95), 3),
        "p99": round(_percentile(latencies, 0.99), 3),
        "max": round(max(latencies, default=0.0), 3),
    }
    endpoint_results: list[dict[str, object]] = []
    for endpoint in endpoints:
        values = endpoint_latencies[endpoint]
        errors = endpoint_errors[endpoint]
        endpoint_results.append(
            {
                "endpoint": endpoint,
                "method": "GET",
                "request_count": endpoint_counts[endpoint],
                "error_count": errors,
                "error_rate": errors / endpoint_counts[endpoint]
                if endpoint_counts[endpoint]
                else 1.0,
                "latency_ms": {
                    "p50": round(_percentile(values, 0.50), 3),
                    "p95": round(_percentile(values, 0.95), 3),
                    "p99": round(_percentile(values, 0.99), 3),
                    "max": round(max(values, default=0.0), 3),
                },
                "status": "pass" if errors == 0 else "fail",
            }
        )

    minimums_met = (
        completed_cycles >= actual_cycles
        and request_count >= required_requests
        and duration >= required_duration
    )
    thresholds_pass = (
        error_rate <= allowed_error_rate
        and latency_summary["p95"] <= allowed_p95_ms
        and snapshot_freshness_pass
    )
    endpoints_pass = all(result["status"] == "pass" for result in endpoint_results)
    current_commit = _current_commit(REPO_ROOT)
    deployed_commit = (
        next(iter(observed_deployment_commits))
        if len(observed_deployment_commits) == 1
        else ""
    )
    deployment_identity_matches = bool(
        normalized_base_url
        and current_commit
        and deployed_commit == current_commit
        and len(observed_deployment_commits) == 1
    )
    production_transport_pass = bool(normalized_base_url and transport_https)
    production_probe_prerequisites_pass = bool(
        production_transport_pass and deployment_identity_matches
    )
    ok = bool(minimums_met and thresholds_pass and endpoints_pass)
    if profile_name == "sustained":
        ok = bool(ok and production_probe_prerequisites_pass)
    configured_promotion_minimums_met = (
        profile_name == "sustained"
        and duration >= configured_duration
        and request_count >= configured_requests
        and allowed_error_rate <= float(profile["max_error_rate"])
        and allowed_p95_ms <= float(profile["max_p95_ms"])
    )
    source_tree_clean = _source_tree_clean(REPO_ROOT)
    promotion_eligible = bool(
        ok
        and profile.get("promotion_eligible") is True
        and configured_promotion_minimums_met
        and production_probe_prerequisites_pass
        and source_tree_clean is True
    )
    suite_results = endpoint_results + [
        {
            "name": "probe-minimums",
            "status": "pass" if minimums_met else "fail",
            "required_cycles": actual_cycles,
            "required_duration_seconds": required_duration,
            "required_requests": required_requests,
        },
        {
            "name": "probe-error-budget",
            "status": "pass" if error_rate <= allowed_error_rate else "fail",
            "actual_error_rate": error_rate,
            "maximum_error_rate": allowed_error_rate,
        },
        {
            "name": "probe-latency-budget",
            "status": "pass" if latency_summary["p95"] <= allowed_p95_ms else "fail",
            "actual_p95_ms": latency_summary["p95"],
            "maximum_p95_ms": allowed_p95_ms,
        },
        {
            "name": "operational-snapshot-freshness",
            "status": "pass" if snapshot_freshness_pass else "fail",
            "sample_count": snapshot_sample_count,
            "expected_count": snapshot_expected_count,
            "issue_count": snapshot_freshness_issue_count,
            "maximum_age_seconds": (
                round(snapshot_max_age, 3) if snapshot_max_age is not None else None
            ),
            "allowed_maximum_age_seconds": snapshot_max_age_limit,
        },
    ]
    if profile_name == "sustained":
        suite_results.extend(
            [
                {
                    "name": "production-probe-transport",
                    "status": "pass" if production_transport_pass else "fail",
                    "transport": transport,
                },
                {
                    "name": "deployed-commit-identity",
                    "status": "pass" if deployment_identity_matches else "fail",
                    "expected_commit": current_commit,
                    "observed_commit": deployed_commit,
                },
            ]
        )
    issues: list[str] = []
    if not minimums_met:
        issues.append("probe minimum duration/request/cycle requirements were not met")
    if error_rate > allowed_error_rate:
        issues.append(f"error rate {error_rate:.6f} exceeded {allowed_error_rate:.6f}")
    if latency_summary["p95"] > allowed_p95_ms:
        issues.append(
            f"p95 latency {latency_summary['p95']:.3f}ms exceeded {allowed_p95_ms:.3f}ms"
        )
    if not snapshot_samples_complete:
        issues.append(
            "operational preflight freshness samples were missing or malformed "
            f"({snapshot_sample_count}/{snapshot_expected_count} valid)"
        )
    elif snapshot_freshness_issue_count:
        issues.append(
            "operational preflight reported invalid or stale component freshness "
            f"({snapshot_freshness_issue_count} issue(s))"
        )
    elif not snapshot_freshness_pass:
        issues.append(
            "operational snapshot freshness exceeded the policy limit "
            f"({snapshot_max_age:.3f}s > {snapshot_max_age_limit:.3f}s)"
        )
    if failures:
        issues.append(f"{error_count} read-only service requests failed")
    if profile_name == "sustained" and not production_transport_pass:
        issues.append(
            "production promotion probes require a deployed HTTPS service endpoint"
        )
    if profile_name == "sustained" and not deployment_identity_matches:
        issues.append(
            "deployed service build_commit must match the current repository commit"
        )
    return {
        "ok": ok,
        "evidence_id": DEFAULT_EVIDENCE_ID,
        "status": "pass" if ok else "fail",
        "evidence_scope": (
            f"deployed-{profile_name}-service-api-probe"
            if normalized_base_url
            else f"local-{profile_name}-service-api-probe"
        ),
        "profile": profile_name,
        "generated_at": _now_iso(),
        "commit": current_commit,
        "deployed_commit": deployed_commit,
        "source_tree_clean": source_tree_clean,
        "policy_sha256": policy_sha256(policy),
        "secrets_redacted": True,
        "read_only": True,
        "order_submission_attempted": False,
        "runtime_ready_claimed": False,
        "production_slo_proven": False,
        "promotion_eligible": promotion_eligible,
        "configured_promotion_minimums_met": configured_promotion_minimums_met,
        "production_probe_prerequisites_pass": production_probe_prerequisites_pass,
        "environment": {
            "python": platform.python_version(),
            "platform": platform.platform(),
            "transport": transport,
        },
        "duration_seconds": round(duration, 3),
        "completed_cycles": completed_cycles,
        "request_count": request_count,
        "error_count": error_count,
        "error_rate": error_rate,
        "latency_ms": latency_summary,
        "operational_snapshot_sample_count": snapshot_sample_count,
        "operational_snapshot_expected_count": snapshot_expected_count,
        "operational_snapshot_issue_count": snapshot_freshness_issue_count,
        "operational_snapshot_issues": snapshot_freshness_issues,
        "operational_snapshot_max_age_seconds": (
            round(snapshot_max_age, 3) if snapshot_max_age is not None else None
        ),
        "thresholds": {
            "max_error_rate": allowed_error_rate,
            "max_p95_ms": allowed_p95_ms,
            "minimum_duration_seconds": required_duration,
            "minimum_requests": required_requests,
        },
        "failures": failures,
        "suite_results": suite_results,
        "issues": issues,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--profile", choices=("quick", "sustained"), default="quick")
    parser.add_argument("--policy", type=Path, default=DEFAULT_POLICY_PATH)
    parser.add_argument("--cycles", type=int)
    parser.add_argument("--minimum-duration-seconds", type=float)
    parser.add_argument("--minimum-requests", type=int)
    parser.add_argument("--cycle-interval-seconds", type=float)
    parser.add_argument("--max-error-rate", type=float)
    parser.add_argument("--max-p95-ms", type=float)
    parser.add_argument("--base-url")
    parser.add_argument("--api-token-env", default=DEFAULT_API_TOKEN_ENV)
    parser.add_argument("--request-timeout-seconds", type=float, default=10.0)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args(argv)
    try:
        report = run_probe(
            profile_name=args.profile,
            policy_path=args.policy,
            cycles=args.cycles,
            minimum_duration_seconds=args.minimum_duration_seconds,
            minimum_requests=args.minimum_requests,
            cycle_interval_seconds=args.cycle_interval_seconds,
            max_error_rate=args.max_error_rate,
            max_p95_ms=args.max_p95_ms,
            base_url=args.base_url,
            api_token_env=args.api_token_env,
            request_timeout_seconds=args.request_timeout_seconds,
        )
        if args.output:
            policy_path = (
                args.policy if args.policy.is_absolute() else REPO_ROOT / args.policy
            )
            output_path = _resolve_output_path(load_policy(policy_path), args.output)
            _atomic_write_json(output_path, report)
            report["output_path"] = str(output_path)
    except (OSError, ValueError) as exc:
        report = {
            "ok": False,
            "status": "fail",
            "profile": args.profile,
            "promotion_eligible": False,
            "issues": [str(exc)],
        }
    if args.json:
        print(json.dumps(report, indent=2, sort_keys=True))
    else:
        print(
            f"Service {args.profile} probe: {report.get('status', 'fail')}; "
            f"requests={report.get('request_count', 0)}, "
            f"errors={report.get('error_count', 0)}, "
            f"p95={report.get('latency_ms', {}).get('p95', 0)}ms"
        )
        for issue in report.get("issues", []):
            print(f"- {issue}", file=sys.stderr)
    return 0 if report.get("ok") is True else 1


if __name__ == "__main__":
    raise SystemExit(main())
