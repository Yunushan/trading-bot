from __future__ import annotations

import io
import importlib.util
import json
import os
import sys
import unittest
from urllib.error import HTTPError, URLError
from http.client import RemoteDisconnected
from pathlib import Path
from unittest import mock


REPO_ROOT = Path(__file__).resolve().parents[3]
PROBE_PATH = REPO_ROOT / "tools" / "run_service_capacity_probe.py"
PROBE_SPEC = importlib.util.spec_from_file_location("run_service_capacity_probe", PROBE_PATH)
assert PROBE_SPEC and PROBE_SPEC.loader
probe = importlib.util.module_from_spec(PROBE_SPEC)
sys.modules["run_service_capacity_probe"] = probe
PROBE_SPEC.loader.exec_module(probe)


class ServiceCapacityProbeTests(unittest.TestCase):
    def test_request_reports_safe_failure_code_and_phase(self) -> None:
        cases = (
            (TimeoutError("password=secret"), "timeout", 0),
            (URLError(TimeoutError("secret")), "timeout", 0),
            (ConnectionRefusedError("secret"), "connection_error", 0),
            (URLError(ConnectionResetError("secret")), "connection_error", 0),
            (RemoteDisconnected("secret"), "connection_error", 0),
            (HTTPError("https://secret.invalid", 503, "secret", {}, None), "http_error", 503),
            (URLError("password=secret"), "transport_error", 0),
        )
        for error, code, status in cases:
            with self.subTest(code=code, exception=type(error).__name__):
                opener = mock.Mock()
                opener.open.side_effect = error
                with mock.patch.object(probe, "_thread_opener", return_value=opener):
                    result = probe._request("http://127.0.0.1:18000", "/livez", token="secret", timeout_seconds=5)
                self.assertEqual(code, result["failure_code"])
                self.assertEqual("headers", result["failure_phase"])
                self.assertEqual(status, result["status_code"])
                self.assertEqual({"opener", "headers"}, set(result["phase_latency_ms"]))
                self.assertNotIn("secret", json.dumps(result))

    def test_body_timeout_is_distinct_from_connection_or_header_failure(self) -> None:
        response = mock.MagicMock(status=200)
        response.__enter__.return_value = response
        response.read.side_effect = TimeoutError("secret")
        opener = mock.Mock()
        opener.open.return_value = response
        with mock.patch.object(probe, "_thread_opener", return_value=opener):
            result = probe._request("http://127.0.0.1:18000", "/livez", token="secret", timeout_seconds=5)
        self.assertEqual("timeout", result["failure_code"])
        self.assertEqual("body", result["failure_phase"])
        self.assertEqual(200, result["status_code"])
        self.assertTrue(result["error"])
        self.assertEqual({"opener", "headers", "body"}, set(result["phase_latency_ms"]))

    def test_opener_failure_is_measured_without_reporting_secret_details(self) -> None:
        with mock.patch.object(probe, "_thread_opener", side_effect=OSError("proxy password=secret")):
            result = probe._request("http://127.0.0.1:18000", "/livez", token="secret", timeout_seconds=5)
        self.assertEqual("opener", result["failure_phase"])
        self.assertEqual("transport_error", result["failure_code"])
        self.assertNotIn("secret", json.dumps(result))
        self.assertEqual({"opener"}, set(result["phase_latency_ms"]))

    def test_response_size_and_decode_failures_are_not_reported_as_success(self) -> None:
        cases = (
            (b"x" * (probe.MAX_RESPONSE_BYTES + 1), False, "response_too_large", "body"),
            (b"not-json", True, "invalid_response", "decode"),
        )
        for body, parse, code, phase in cases:
            with self.subTest(code=code):
                response = mock.MagicMock(status=200)
                response.__enter__.return_value = response
                response.read.return_value = body
                opener = mock.Mock()
                opener.open.return_value = response
                with mock.patch.object(probe, "_thread_opener", return_value=opener):
                    result = probe._request(
                        "http://127.0.0.1:18000", "/livez", token="secret", timeout_seconds=5, parse_json=parse
                    )
                self.assertEqual(code, result["failure_code"])
                self.assertEqual(phase, result["failure_phase"])
                self.assertTrue(result["error"])
                response.read.assert_called_once_with(probe.MAX_RESPONSE_BYTES + 1)

    def test_diagnostic_projection_drops_unrecognized_keys_and_unsafe_values(self) -> None:
        report = {
            "failure_counts": {"timeout": 2, "password=operator-secret": 1, "http_error": True},
            "failure_stage_counts": {"headers": 2, "password=operator-secret": 3},
            "status_code_counts": {"0": 2, "200": 8, "password=operator-secret": 1, "503": -1},
            "request_phase_latency_ms": {
                "headers": {"count": 10, "p95": 100.0, "max": 120.0, "private_payload": "operator-secret"},
                "body": {"count": 10, "p95": float("nan"), "max": float("inf")},
                "password=operator-secret": {"count": 10},
            },
        }
        for projection in (probe._cli_report, probe._artifact_report):
            with self.subTest(projection=projection.__name__):
                result = projection(report)
                self.assertEqual({"timeout": 2}, result["failure_counts"])
                self.assertEqual({"headers": 2}, result["failure_stage_counts"])
                self.assertEqual({"0": 2, "200": 8}, result["status_code_counts"])
                self.assertEqual(
                    {"headers": {"count": 10, "p95": 100.0, "max": 120.0}}, result["request_phase_latency_ms"]
                )
                self.assertNotIn("operator-secret", json.dumps(result, allow_nan=False))

    def test_failed_requests_remain_failed_and_preflight_is_not_counted(self) -> None:
        calls = []

        def request(_base, endpoint, **kwargs):
            calls.append(endpoint)
            if kwargs.get("parse_json"):
                payload = {"read_only": True, "service_api": {"read_only": True, "mutation_routes_enabled": False}}
                return {"status_code": 200, "payload": payload}
            failure = {
                "/livez": (200, "", "", 10.0),
                "/readyz": (503, "http_error", "headers", 20.0),
                "/api/v1/runtime": (0, "timeout", "headers", 5000.0),
                "/api/v1/status": (200, "timeout", "body", 5000.0),
            }[endpoint]
            status, code, phase, latency = failure
            return {
                "endpoint": endpoint,
                "status_code": status,
                "error": code,
                "failure_code": code,
                "failure_phase": phase,
                "latency_ms": latency,
                "phase_latency_ms": {phase or "body": latency},
            }

        with (
            mock.patch.dict(os.environ, {probe.DEFAULT_API_TOKEN_ENV: "secret"}),
            mock.patch.object(probe, "_request", side_effect=request),
        ):
            report = probe.run_capacity_probe(base_url="http://127.0.0.1:18000", request_count=4, concurrency=2)

        self.assertFalse(report["ok"])
        self.assertEqual(6, len(calls))
        self.assertEqual(4, report["request_count"])
        self.assertEqual(3, report["error_count"])
        self.assertEqual(0.75, report["error_rate"])
        self.assertEqual({"200": 2, "503": 1, "0": 1}, report["status_code_counts"])
        self.assertEqual({"http_error": 1, "timeout": 2}, report["failure_counts"])
        self.assertEqual({"headers": 2, "body": 1}, report["failure_stage_counts"])
        self.assertEqual(2, report["request_phase_latency_ms"]["headers"]["count"])
        self.assertEqual(5000.0, report["request_phase_latency_ms"]["headers"]["max"])
        self.assertEqual(0.0, report["thresholds"]["max_error_rate"])
        self.assertEqual(500.0, report["thresholds"]["max_p95_ms"])
        self.assertEqual(5.0, report["request_timeout_seconds"])

    def test_local_capacity_probe_uses_a_real_read_only_child_process(self) -> None:
        report = probe.run_capacity_probe(
            request_count=60,
            concurrency=6,
            max_error_rate=0.0,
            max_p95_ms=2000.0,
            minimum_throughput_rps=1.0,
        )

        self.assertTrue(report["ok"], report["issues"])
        self.assertEqual("child-process", report["process_boundary"])
        self.assertEqual("local-canonical-service-process", report["environment"])
        self.assertEqual(60, report["request_count"])
        self.assertEqual(["GET"], report["methods"])
        self.assertTrue(report["read_only"])
        self.assertFalse(report["order_submission_attempted"])
        self.assertFalse(report["promotion_eligible"])
        self.assertTrue(all(item["status"] == "pass" for item in report["suite_results"]))
        self.assertEqual({}, report["failure_counts"])
        self.assertEqual({}, report["failure_stage_counts"])
        self.assertEqual({"200": 60}, report["status_code_counts"])
        self.assertEqual(5.0, report["request_timeout_seconds"])
        for phase in ("opener", "headers", "body"):
            self.assertEqual(60, report["request_phase_latency_ms"][phase]["count"])
            self.assertGreaterEqual(report["request_phase_latency_ms"][phase]["max"], 0.0)

    def test_remote_plain_http_is_restricted_to_loopback(self) -> None:
        with self.assertRaisesRegex(ValueError, "only on loopback"):
            probe._normalize_base_url("http://service.example.test")
        normalized, scheme = probe._normalize_base_url("http://127.0.0.1:8000/")
        self.assertEqual("http://127.0.0.1:8000", normalized)
        self.assertEqual("http", scheme)

    def test_remote_probe_requires_a_token_without_disclosing_it(self) -> None:
        credential_name = "MISSING_CAPACITY_PROBE_TOKEN"
        with mock.patch.dict(os.environ, {}, clear=True):
            report = probe.run_capacity_probe(
                base_url="https://service.example.test",
                api_token_env=credential_name,
                request_count=1,
            )

        self.assertFalse(report["ok"])
        rendered = str(report)
        self.assertIn("configured API token environment variable", report["issues"][0])
        self.assertNotIn(credential_name, rendered)
        self.assertNotIn("Authorization", rendered)

    def test_cli_report_is_an_explicit_non_secret_projection(self) -> None:
        rendered = json.dumps(
            probe._cli_report(
                {
                    "ok": False,
                    "status": "fail",
                    "issues": ["probe failed: password=operator-secret"],
                    "token": "service-token",
                    "api_secret": "exchange-secret",
                    "deployed_commit": "not-a-commit",
                }
            )
        )

        self.assertNotIn("operator-secret", rendered)
        self.assertNotIn("service-token", rendered)
        self.assertNotIn("exchange-secret", rendered)
        self.assertNotIn("password", rendered)
        self.assertEqual(["probe_failed"], probe._cli_report({"issues": ["arbitrary"]})["issue_codes"])
        self.assertTrue(probe._cli_report({})["secrets_redacted"])

    def test_local_start_failure_suppresses_child_service_output(self) -> None:
        child = mock.Mock(returncode=1)
        output = io.StringIO("password=child-secret")
        with (
            mock.patch.object(probe, "_free_loopback_port", return_value=18001),
            mock.patch.object(probe.tempfile, "TemporaryFile", return_value=output),
            mock.patch.object(probe.subprocess, "Popen", return_value=child),
            mock.patch.object(
                probe,
                "_wait_until_ready",
                side_effect=RuntimeError("service did not become ready"),
            ),
        ):
            with self.assertRaisesRegex(RuntimeError, "diagnostics are suppressed") as raised:
                probe._start_local_service()

        self.assertNotIn("child-secret", str(raised.exception))

    def test_artifact_report_redacts_issue_text(self) -> None:
        rendered = json.dumps(
            probe._artifact_report(
                {
                    "issues": ["probe failed: password=operator-secret"],
                    "deployed_commit": "not-a-commit",
                }
            )
        )

        self.assertNotIn("operator-secret", rendered)
        self.assertNotIn("password", rendered)
        self.assertEqual(["probe_failed"], probe._artifact_report({"issues": ["arbitrary"]})["issues"])

    def test_non_finite_thresholds_fail_before_starting_a_target(self) -> None:
        for field, value in (
            ("request_timeout_seconds", float("nan")),
            ("max_error_rate", float("inf")),
            ("max_p95_ms", float("-inf")),
            ("minimum_throughput_rps", float("nan")),
        ):
            with self.subTest(field=field):
                report = probe.run_capacity_probe(**{field: value})
                self.assertFalse(report["ok"])
                self.assertIn("must be a finite number", report["issues"][0])

    def test_authoritative_verifiers_run_the_capacity_probe(self) -> None:
        verify_all = (REPO_ROOT / "tools" / "verify_all.py").read_text(encoding="utf-8")
        ci_workflow = (REPO_ROOT / ".github" / "workflows" / "ci.yml").read_text(encoding="utf-8")

        for verifier in (verify_all, ci_workflow):
            self.assertIn("tools/run_service_capacity_probe.py", verifier)
        self.assertIn("--base-url http://127.0.0.1:18000", ci_workflow)
        self.assertIn("--env BOT_SERVICE_API_READ_ONLY=1", ci_workflow)


if __name__ == "__main__":
    unittest.main()
