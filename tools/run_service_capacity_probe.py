#!/usr/bin/env python3
"""Run a bounded concurrent GET-only Service API capacity regression probe."""

from __future__ import annotations

import argparse
import concurrent.futures
from http.client import HTTPException
import ipaddress
import json
import math
import os
import platform
import re
import socket
import subprocess
import sys
import tempfile
import threading
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import urlsplit, urlunsplit
from urllib.request import HTTPRedirectHandler, Request, build_opener


REPO_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_ENDPOINTS = (
    "/livez",
    "/readyz",
    "/api/v1/runtime",
    "/api/v1/status",
    "/api/v1/metrics",
)
LOCAL_API_TOKEN = "capacity-regression-probe-token-0123456789"
DEFAULT_API_TOKEN_ENV = "BOT_SERVICE_API_TOKEN"
MAX_RESPONSE_BYTES = 2 * 1024 * 1024
ENV_NAME_PATTERN = re.compile(r"[A-Z][A-Z0-9_]{0,127}")
COMMIT_PATTERN = re.compile(r"[0-9a-f]{40}")
CLI_SAFE_KEYS = (
    "ok",
    "status",
    "generated_at",
    "profile",
    "evidence_scope",
    "promotion_eligible",
    "environment",
    "process_boundary",
    "platform",
    "python_version",
    "deployed_commit",
    "read_only",
    "secrets_redacted",
    "order_submission_attempted",
    "methods",
    "concurrency",
    "request_count",
    "error_count",
    "error_rate",
    "duration_seconds",
    "throughput_requests_per_second",
    "latency_ms",
    "thresholds",
    "suite_results",
)


class _NoRedirectHandler(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):  # noqa: ANN001, ANN201
        return None


_THREAD_LOCAL = threading.local()


def _thread_opener():
    opener = getattr(_THREAD_LOCAL, "opener", None)
    if opener is None:
        opener = build_opener(_NoRedirectHandler)
        _THREAD_LOCAL.opener = opener
    return opener


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


def _bounded_float(
    value: object,
    *,
    label: str,
    minimum: float,
    maximum: float | None = None,
) -> float:
    try:
        parsed = float(value)
    except (TypeError, ValueError, OverflowError) as exc:
        raise ValueError(f"{label} must be a finite number") from exc
    if not math.isfinite(parsed):
        raise ValueError(f"{label} must be a finite number")
    if maximum is not None:
        parsed = min(maximum, parsed)
    return max(minimum, parsed)


def _is_loopback_hostname(hostname: str) -> bool:
    normalized = str(hostname or "").strip().lower().rstrip(".")
    if normalized == "localhost":
        return True
    try:
        return ipaddress.ip_address(normalized).is_loopback
    except ValueError:
        return False


def _normalize_base_url(value: str) -> tuple[str, str]:
    parsed = urlsplit(str(value or "").strip())
    if parsed.scheme not in {"http", "https"} or not parsed.hostname:
        raise ValueError("--base-url must be an http:// or https:// origin")
    if parsed.username or parsed.password:
        raise ValueError("--base-url must not contain credentials")
    if parsed.path not in {"", "/"} or parsed.query or parsed.fragment:
        raise ValueError("--base-url must not contain a path, query, or fragment")
    if parsed.scheme == "http" and not _is_loopback_hostname(parsed.hostname):
        raise ValueError(
            "Plain HTTP capacity probes are allowed only on loopback; use HTTPS remotely"
        )
    return urlunsplit((parsed.scheme, parsed.netloc, "", "", "")), parsed.scheme


def _free_loopback_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])


def _request(
    base_url: str,
    endpoint: str,
    *,
    token: str,
    timeout_seconds: float,
    parse_json: bool = False,
) -> dict[str, Any]:
    started = time.perf_counter()
    status_code = 0
    error = ""
    payload: object = None
    request = Request(
        f"{base_url}{endpoint}",
        headers={
            "Accept": "application/json",
            "Authorization": f"Bearer {token}",
            "User-Agent": "trading-bot-capacity-regression/1",
        },
        method="GET",
    )
    try:
        with _thread_opener().open(request, timeout=timeout_seconds) as response:  # noqa: S310
            status_code = int(response.status)
            body = response.read(MAX_RESPONSE_BYTES + 1)
            if len(body) > MAX_RESPONSE_BYTES:
                error = "response exceeded the bounded probe limit"
            elif parse_json and status_code == 200:
                payload = json.loads(body.decode("utf-8"))
    except HTTPError as exc:
        status_code = int(exc.code)
        error = f"HTTP {status_code}"
    except (HTTPException, OSError, URLError, ValueError) as exc:
        error = f"{type(exc).__name__}: request failed"
    if status_code != 200 and not error:
        error = f"HTTP {status_code}"
    return {
        "endpoint": endpoint,
        "method": "GET",
        "status_code": status_code,
        "latency_ms": (time.perf_counter() - started) * 1000,
        "error": error,
        "payload": payload,
    }


def _wait_until_ready(
    process: subprocess.Popen[str],
    base_url: str,
    *,
    token: str,
    timeout_seconds: float = 30.0,
) -> None:
    deadline = time.monotonic() + timeout_seconds
    while time.monotonic() < deadline:
        if process.poll() is not None:
            raise RuntimeError(
                f"canonical service process exited with code {process.returncode}"
            )
        result = _request(base_url, "/readyz", token=token, timeout_seconds=1.0)
        if result["status_code"] == 200 and not result["error"]:
            return
        time.sleep(0.1)
    raise RuntimeError(
        "canonical service process did not become ready within 30 seconds"
    )


def _start_local_service() -> tuple[subprocess.Popen[str], Any, str]:
    port = _free_loopback_port()
    base_url = f"http://127.0.0.1:{port}"
    environment = os.environ.copy()
    for name in (
        "BOT_SERVICE_API_ALLOW_UNAUTHENTICATED_WRITES",
        "BOT_SERVICE_API_TLS_CERTFILE",
        "BOT_SERVICE_API_TLS_KEYFILE",
        "BOT_SERVICE_API_TRUST_LOOPBACK_PROXY",
        "BOT_SERVICE_API_TRUST_PROXY_TLS",
    ):
        environment.pop(name, None)
    environment.update(
        {
            "BOT_SERVICE_API_TOKEN": LOCAL_API_TOKEN,
            "BOT_SERVICE_API_READ_ONLY": "1",
            "PYTHONDONTWRITEBYTECODE": "1",
        }
    )
    output = tempfile.TemporaryFile(mode="w+", encoding="utf-8")
    creationflags = subprocess.CREATE_NO_WINDOW if sys.platform == "win32" else 0
    process = subprocess.Popen(
        [
            sys.executable,
            "apps/service-api/main.py",
            "--serve",
            "--host",
            "127.0.0.1",
            "--port",
            str(port),
        ],
        cwd=REPO_ROOT,
        env=environment,
        stdin=subprocess.DEVNULL,
        stdout=output,
        stderr=subprocess.STDOUT,
        text=True,
        creationflags=creationflags,
    )
    try:
        _wait_until_ready(process, base_url, token=LOCAL_API_TOKEN)
    except RuntimeError as exc:
        process.terminate()
        try:
            process.wait(timeout=5)
        except subprocess.TimeoutExpired:
            process.kill()
            process.wait(timeout=5)
        output.seek(0)
        logs = output.read(4000).strip()
        output.close()
        suffix = f" Service output: {logs}" if logs else ""
        raise RuntimeError(
            f"Unable to start local capacity target: {exc}.{suffix}"
        ) from exc
    return process, output, base_url


def _stop_local_service(process: subprocess.Popen[str], output: Any) -> None:
    if process.poll() is None:
        process.terminate()
        try:
            process.wait(timeout=10)
        except subprocess.TimeoutExpired:
            process.kill()
            process.wait(timeout=5)
    output.close()


def _safe_deployed_commit(value: object) -> str:
    candidate = str(value or "").strip().lower()
    return candidate if COMMIT_PATTERN.fullmatch(candidate) else ""


def _safe_issue_codes(value: object) -> list[str]:
    """Expose failure classes to logs without copying arbitrary issue text."""
    if not isinstance(value, list):
        return []
    codes: list[str] = []
    for issue in value:
        normalized = str(issue or "").strip().lower()
        if normalized.startswith("error rate "):
            code = "error_rate_threshold"
        elif normalized.startswith("p95 latency "):
            code = "p95_latency_threshold"
        elif normalized.startswith("throughput "):
            code = "throughput_threshold"
        elif "api token environment variable is required" in normalized:
            code = "missing_api_token"
        elif "finite number" in normalized:
            code = "invalid_numeric_parameter"
        elif "only on loopback" in normalized:
            code = "unsafe_http_origin"
        elif "read-only service api mode" in normalized:
            code = "read_only_preflight_failed"
        elif normalized:
            code = "probe_failed"
        else:
            continue
        if code not in codes:
            codes.append(code)
    return codes


def _cli_report(report: dict[str, Any]) -> dict[str, Any]:
    """Return an explicit, non-secret projection for stdout and CI logs."""
    safe: dict[str, Any] = {}
    for key in CLI_SAFE_KEYS:
        if key not in report:
            continue
        value = report[key]
        safe[key] = _safe_deployed_commit(value) if key == "deployed_commit" else value
    safe["issue_codes"] = _safe_issue_codes(report.get("issues"))
    safe["secrets_redacted"] = True
    return safe


def run_capacity_probe(
    *,
    base_url: str | None = None,
    api_token_env: str = DEFAULT_API_TOKEN_ENV,
    request_count: int = 600,
    concurrency: int = 16,
    request_timeout_seconds: float = 5.0,
    max_error_rate: float = 0.0,
    max_p95_ms: float = 500.0,
    minimum_throughput_rps: float = 10.0,
) -> dict[str, Any]:
    try:
        bounded_requests = max(1, min(100_000, int(request_count)))
        bounded_concurrency = max(1, min(128, int(concurrency)))
        timeout_seconds = _bounded_float(
            request_timeout_seconds,
            label="--request-timeout-seconds",
            minimum=0.1,
            maximum=30.0,
        )
        allowed_error_rate = _bounded_float(
            max_error_rate,
            label="--max-error-rate",
            minimum=0.0,
            maximum=1.0,
        )
        allowed_p95_ms = _bounded_float(
            max_p95_ms,
            label="--max-p95-ms",
            minimum=0.001,
        )
        required_throughput = _bounded_float(
            minimum_throughput_rps,
            label="--minimum-throughput-rps",
            minimum=0.001,
        )
    except (TypeError, ValueError, OverflowError) as exc:
        return {
            "ok": False,
            "status": "fail",
            "promotion_eligible": False,
            "issues": [str(exc)],
        }
    if not ENV_NAME_PATTERN.fullmatch(str(api_token_env or "")):
        return {
            "ok": False,
            "status": "fail",
            "promotion_eligible": False,
            "issues": [
                "--api-token-env must be a conventional uppercase environment variable name"
            ],
        }

    process: subprocess.Popen[str] | None = None
    process_output: Any = None
    if base_url:
        try:
            normalized_base_url, scheme = _normalize_base_url(base_url)
        except ValueError as exc:
            return {
                "ok": False,
                "status": "fail",
                "promotion_eligible": False,
                "issues": [str(exc)],
            }
        token = str(os.environ.get(api_token_env) or "").strip()
        if not token:
            return {
                "ok": False,
                "status": "fail",
                "promotion_eligible": False,
                "issues": [
                    "The configured API token environment variable is required "
                    "for a remote capacity probe"
                ],
            }
        environment = "external-https" if scheme == "https" else "loopback-http"
        process_boundary = "external-service"
    else:
        try:
            process, process_output, normalized_base_url = _start_local_service()
        except RuntimeError as exc:
            return {
                "ok": False,
                "status": "fail",
                "promotion_eligible": False,
                "issues": [str(exc)],
            }
        token = LOCAL_API_TOKEN
        environment = "local-canonical-service-process"
        process_boundary = "child-process"

    try:
        health = _request(
            normalized_base_url,
            "/health",
            token=token,
            timeout_seconds=timeout_seconds,
            parse_json=True,
        )
        readiness = _request(
            normalized_base_url,
            "/readyz",
            token=token,
            timeout_seconds=timeout_seconds,
            parse_json=True,
        )
        health_payload = (
            health.get("payload") if isinstance(health.get("payload"), dict) else {}
        )
        service_api = (
            health_payload.get("service_api")
            if isinstance(health_payload, dict)
            else {}
        )
        service_api = service_api if isinstance(service_api, dict) else {}
        readiness_payload = (
            readiness.get("payload")
            if isinstance(readiness.get("payload"), dict)
            else {}
        )
        readiness_payload = (
            readiness_payload if isinstance(readiness_payload, dict) else {}
        )
        preflight_ok = bool(
            health["status_code"] == 200
            and readiness["status_code"] == 200
            and service_api.get("read_only") is True
            and service_api.get("mutation_routes_enabled") is False
            and readiness_payload.get("read_only") is True
        )
        if not preflight_ok:
            return {
                "ok": False,
                "status": "fail",
                "promotion_eligible": False,
                "read_only": False,
                "order_submission_attempted": False,
                "issues": [
                    "capacity target must report the fail-closed read-only Service API mode"
                ],
            }

        started = time.perf_counter()

        def execute(index: int) -> dict[str, Any]:
            endpoint = DEFAULT_ENDPOINTS[index % len(DEFAULT_ENDPOINTS)]
            return _request(
                normalized_base_url,
                endpoint,
                token=token,
                timeout_seconds=timeout_seconds,
            )

        with concurrent.futures.ThreadPoolExecutor(
            max_workers=bounded_concurrency
        ) as executor:
            results = list(executor.map(execute, range(bounded_requests)))
        duration_seconds = max(time.perf_counter() - started, sys.float_info.epsilon)
    finally:
        if process is not None:
            _stop_local_service(process, process_output)

    latencies = [float(item["latency_ms"]) for item in results]
    error_count = sum(1 for item in results if item["error"])
    error_rate = error_count / len(results) if results else 1.0
    throughput = len(results) / duration_seconds
    latency = {
        "p50": round(_percentile(latencies, 0.50), 3),
        "p95": round(_percentile(latencies, 0.95), 3),
        "p99": round(_percentile(latencies, 0.99), 3),
        "max": round(max(latencies, default=0.0), 3),
    }
    endpoint_results = []
    for endpoint in DEFAULT_ENDPOINTS:
        rows = [item for item in results if item["endpoint"] == endpoint]
        row_latencies = [float(item["latency_ms"]) for item in rows]
        row_errors = sum(1 for item in rows if item["error"])
        endpoint_results.append(
            {
                "endpoint": endpoint,
                "method": "GET",
                "request_count": len(rows),
                "error_count": row_errors,
                "latency_p95_ms": round(_percentile(row_latencies, 0.95), 3),
                "status": "pass" if row_errors == 0 else "fail",
            }
        )
    issues: list[str] = []
    if error_rate > allowed_error_rate:
        issues.append(f"error rate {error_rate:.6f} exceeded {allowed_error_rate:.6f}")
    if latency["p95"] > allowed_p95_ms:
        issues.append(
            f"p95 latency {latency['p95']:.3f}ms exceeded {allowed_p95_ms:.3f}ms"
        )
    if throughput < required_throughput:
        issues.append(
            f"throughput {throughput:.3f} requests/s was below {required_throughput:.3f}"
        )
    passed = not issues
    deployed_commit = str(readiness_payload.get("build_commit") or "").strip().lower()
    return {
        "ok": passed,
        "status": "pass" if passed else "fail",
        "generated_at": _now_iso(),
        "profile": "bounded-capacity-regression",
        "evidence_scope": "non-promotional-capacity-regression",
        "promotion_eligible": False,
        "environment": environment,
        "process_boundary": process_boundary,
        "platform": platform.platform(),
        "python_version": platform.python_version(),
        "deployed_commit": deployed_commit,
        "read_only": True,
        "secrets_redacted": True,
        "order_submission_attempted": False,
        "methods": ["GET"],
        "concurrency": bounded_concurrency,
        "request_count": len(results),
        "error_count": error_count,
        "error_rate": error_rate,
        "duration_seconds": round(duration_seconds, 6),
        "throughput_requests_per_second": round(throughput, 3),
        "latency_ms": latency,
        "thresholds": {
            "max_error_rate": allowed_error_rate,
            "max_p95_ms": allowed_p95_ms,
            "minimum_throughput_requests_per_second": required_throughput,
        },
        "suite_results": endpoint_results,
        "issues": issues,
    }


def _write_json(path: Path, payload: dict[str, Any]) -> None:
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
    parser.add_argument("--base-url")
    parser.add_argument("--api-token-env", default=DEFAULT_API_TOKEN_ENV)
    parser.add_argument("--requests", type=int, default=600)
    parser.add_argument("--concurrency", type=int, default=16)
    parser.add_argument("--request-timeout-seconds", type=float, default=5.0)
    parser.add_argument("--max-error-rate", type=float, default=0.0)
    parser.add_argument("--max-p95-ms", type=float, default=500.0)
    parser.add_argument("--minimum-throughput-rps", type=float, default=10.0)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args(argv)
    report = run_capacity_probe(
        base_url=args.base_url,
        api_token_env=args.api_token_env,
        request_count=args.requests,
        concurrency=args.concurrency,
        request_timeout_seconds=args.request_timeout_seconds,
        max_error_rate=args.max_error_rate,
        max_p95_ms=args.max_p95_ms,
        minimum_throughput_rps=args.minimum_throughput_rps,
    )
    if args.output:
        _write_json(args.output, report)
    cli_report = _cli_report(report)
    if args.json:
        print(json.dumps(cli_report, indent=2, sort_keys=True, allow_nan=False))
    else:
        print(
            "Service capacity regression: "
            f"{cli_report.get('status', 'fail')} requests={cli_report.get('request_count', 0)} "
            f"rps={cli_report.get('throughput_requests_per_second', 0)} "
            f"p95={cli_report.get('latency_ms', {}).get('p95', 0)}ms"
        )
        for issue_code in cli_report.get("issue_codes", []):
            print(f"- issue_code={issue_code}")
    return 0 if report.get("ok") else 1


if __name__ == "__main__":
    raise SystemExit(main())
