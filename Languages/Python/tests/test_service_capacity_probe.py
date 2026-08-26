from __future__ import annotations

import importlib.util
import sys
import unittest
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[3]
PROBE_PATH = REPO_ROOT / "tools" / "run_service_capacity_probe.py"
PROBE_SPEC = importlib.util.spec_from_file_location("run_service_capacity_probe", PROBE_PATH)
assert PROBE_SPEC and PROBE_SPEC.loader
probe = importlib.util.module_from_spec(PROBE_SPEC)
sys.modules["run_service_capacity_probe"] = probe
PROBE_SPEC.loader.exec_module(probe)


class ServiceCapacityProbeTests(unittest.TestCase):
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

    def test_remote_plain_http_is_restricted_to_loopback(self) -> None:
        with self.assertRaisesRegex(ValueError, "only on loopback"):
            probe._normalize_base_url("http://service.example.test")
        normalized, scheme = probe._normalize_base_url("http://127.0.0.1:8000/")
        self.assertEqual("http://127.0.0.1:8000", normalized)
        self.assertEqual("http", scheme)

    def test_remote_probe_requires_a_token_without_disclosing_it(self) -> None:
        report = probe.run_capacity_probe(
            base_url="https://service.example.test",
            api_token_env="MISSING_CAPACITY_PROBE_TOKEN",
            request_count=1,
        )

        self.assertFalse(report["ok"])
        self.assertIn("MISSING_CAPACITY_PROBE_TOKEN", report["issues"][0])
        self.assertNotIn("Authorization", str(report))

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
