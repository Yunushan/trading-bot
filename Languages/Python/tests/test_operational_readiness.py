from __future__ import annotations

import json
import sys
import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path


PYTHON_ROOT = Path(__file__).resolve().parents[1]
REPO_ROOT = PYTHON_ROOT.parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from tools import check_operational_readiness as readiness  # noqa: E402
from tools import run_incident_audit_continuity_drill as audit_continuity  # noqa: E402
from tools import run_operational_recovery_drill as recovery  # noqa: E402
from tools import run_service_sustained_probe as service_probe  # noqa: E402


POLICY_PATH = REPO_ROOT / "docs" / "operational-readiness-policy.json"


class OperationalReadinessTests(unittest.TestCase):
    def test_checked_in_policy_is_valid_and_has_no_assumed_passes(self):
        policy = readiness.load_policy(POLICY_PATH)

        self.assertEqual([], readiness.validate_policy(policy))
        self.assertTrue(policy["policy"]["no_assumed_passes"])
        self.assertTrue(policy["policy"]["production_promotion_requires_all_evidence"])
        self.assertFalse(policy["probe_profiles"]["quick"]["promotion_eligible"])
        self.assertTrue(policy["probe_profiles"]["sustained"]["promotion_eligible"])

    def test_schema_audit_passes_without_claiming_promotion_readiness(self):
        report = readiness.audit_operational_readiness(REPO_ROOT)

        self.assertTrue(report["ok"])
        self.assertTrue(report["schema_ok"])
        self.assertFalse(report["promotion_ready"])
        self.assertEqual(4, report["service_level_objective_count"])
        self.assertEqual(3, report["recovery_objective_count"])
        self.assertEqual(4, report["required_evidence_count"])

    def test_invalid_policy_is_rejected(self):
        policy = readiness.load_policy(POLICY_PATH)
        policy["policy"]["no_assumed_passes"] = False
        policy["probe_profiles"]["quick"]["promotion_eligible"] = True

        issues = readiness.validate_policy(policy)

        self.assertIn("policy.no_assumed_passes must be true", issues)
        self.assertIn("probe_profiles.quick.promotion_eligible must be false", issues)

    def test_missing_promotion_evidence_is_reported_explicitly(self):
        with tempfile.TemporaryDirectory() as temporary_directory:
            report = readiness.audit_operational_readiness(
                REPO_ROOT,
                evidence_dir=Path(temporary_directory),
                require_evidence=True,
            )

        self.assertFalse(report["ok"])
        self.assertFalse(report["promotion_ready"])
        self.assertEqual(4, len(report["evidence"]))
        self.assertTrue(all(not item["ok"] for item in report["evidence"]))
        self.assertTrue(all("missing evidence artifact" in item["issues"][0] for item in report["evidence"]))

    def test_complete_current_policy_evidence_can_be_validated_without_assumptions(self):
        policy = readiness.load_policy(POLICY_PATH)
        policy_hash = readiness.policy_sha256(policy)
        generated_at = datetime.now(timezone.utc).isoformat()
        with tempfile.TemporaryDirectory() as temporary_directory:
            evidence_dir = Path(temporary_directory)
            for requirement in policy["required_evidence"]:
                payload: dict[str, object] = {
                    "evidence_id": requirement["id"],
                    "status": "pass",
                    "generated_at": generated_at,
                    "commit": "test-commit",
                    "source_tree_clean": True,
                    "policy_sha256": policy_hash,
                    "secrets_redacted": True,
                    "read_only": True,
                    "order_submission_attempted": False,
                    "promotion_eligible": True,
                    "suite_results": [{"name": "test", "status": "pass"}],
                }
                for field in requirement["required_fields"]:
                    payload.setdefault(field, 0)
                if requirement["id"] == "service-api-sustained-runtime":
                    sustained = policy["probe_profiles"]["sustained"]
                    payload.update(
                        {
                            "duration_seconds": sustained["minimum_duration_seconds"],
                            "request_count": sustained["minimum_requests"],
                            "error_rate": 0.0,
                            "latency_ms": {"p95": 1.0},
                            "operational_snapshot_max_age_seconds": 1.0,
                            "deployed_commit": "test-commit",
                            "evidence_scope": "deployed-sustained-service-api-probe",
                            "environment": {"transport": "external-https"},
                        }
                    )
                elif requirement["id"] == "production-service-slo-window":
                    payload.update(
                        {
                            "window_start": "2026-06-01T00:00:00+00:00",
                            "window_end": "2026-07-01T00:00:00+00:00",
                            "successful_request_ratio": 1.0,
                            "failed_request_ratio": 0.0,
                            "read_latency_p95_ms": 1.0,
                            "operational_snapshot_age_seconds": 1.0,
                        }
                    )
                else:
                    payload.update(
                        {
                            "recovery_time_seconds": 0.0,
                            "recovery_point_seconds": 0.0,
                        }
                    )
                (evidence_dir / requirement["filename"]).write_text(
                    json.dumps(payload),
                    encoding="utf-8",
                )

            report = readiness.audit_operational_readiness(
                REPO_ROOT,
                evidence_dir=evidence_dir,
                require_evidence=True,
            )

        self.assertTrue(report["ok"])
        self.assertTrue(report["promotion_ready"])

    def test_quick_service_probe_is_read_only_and_not_promotion_evidence(self):
        policy = readiness.load_policy(POLICY_PATH)
        endpoint_count = len(policy["probe_profiles"]["quick"]["endpoints"])

        report = service_probe.run_probe(
            profile_name="quick",
            cycles=1,
            minimum_requests=endpoint_count,
        )

        self.assertTrue(report["ok"], report["issues"])
        self.assertEqual(endpoint_count, report["request_count"])
        self.assertEqual(0, report["error_count"])
        self.assertTrue(report["read_only"])
        self.assertFalse(report["order_submission_attempted"])
        self.assertFalse(report["promotion_eligible"])
        self.assertFalse(report["production_slo_proven"])

    def test_sustained_probe_requires_a_deployed_service_origin(self):
        report = service_probe.run_probe(
            profile_name="sustained",
            cycles=1,
            minimum_duration_seconds=0,
            minimum_requests=1,
        )

        self.assertFalse(report["ok"])
        self.assertFalse(report["promotion_eligible"])
        self.assertIn("requires --base-url", report["issues"][0])

    def test_probe_base_url_rejects_credentials_and_non_origin_paths(self):
        for value in (
            "https://user:secret@example.test",
            "https://example.test/api/v1",
            "file:///tmp/service.sock",
        ):
            with self.subTest(value=value):
                with self.assertRaises(ValueError):
                    service_probe._normalize_base_url(value)

    def test_config_backup_restore_and_service_restart_drill_passes(self):
        report = recovery.run_recovery_drill()

        self.assertTrue(report["ok"], report["issues"])
        self.assertTrue(report["secrets_redacted"])
        self.assertTrue(report["read_only"])
        self.assertFalse(report["order_submission_attempted"])
        self.assertLessEqual(report["recovery_time_seconds"], report["thresholds"]["rto_seconds"])
        self.assertLessEqual(report["recovery_point_seconds"], report["thresholds"]["rpo_seconds"])
        serialized = json.dumps(report)
        self.assertNotIn("exchange-secret", serialized)
        self.assertNotIn("llm-secret", serialized)

    def test_incident_audit_continuity_drill_recovers_rotated_redacted_logs(self):
        report = audit_continuity.run_continuity_drill()

        self.assertTrue(report["ok"], report.get("issues"))
        self.assertEqual("incident-audit-continuity", report["evidence_id"])
        self.assertTrue(report["read_only"])
        self.assertTrue(report["secrets_redacted"])
        self.assertFalse(report["order_submission_attempted"])
        self.assertGreaterEqual(len(report["suite_results"]), 9)

    def test_evidence_output_cannot_escape_configured_directory(self):
        policy = readiness.load_policy(POLICY_PATH)

        with self.assertRaisesRegex(ValueError, "must stay inside"):
            service_probe._resolve_output_path(policy, Path("..") / "outside.json")

    def test_short_production_window_cannot_satisfy_rolling_slo(self):
        policy = readiness.load_policy(POLICY_PATH)
        requirement = next(
            item
            for item in policy["required_evidence"]
            if item["id"] == "production-service-slo-window"
        )
        payload = {
            "window_start": "2026-07-01T00:00:00+00:00",
            "window_end": "2026-07-02T00:00:00+00:00",
            "successful_request_ratio": 1.0,
            "failed_request_ratio": 0.0,
            "read_latency_p95_ms": 1.0,
            "operational_snapshot_age_seconds": 1.0,
        }

        issues = readiness._validate_evidence_metrics(
            requirement,
            payload,
            policy=policy,
            path=Path("production-service-slo-window.json"),
        )

        self.assertTrue(any("at least 30 days" in issue for issue in issues))

    def test_authoritative_verifiers_run_operational_readiness_gates(self):
        verify_all = (REPO_ROOT / "tools" / "verify_all.py").read_text(encoding="utf-8")
        ci_workflow = (REPO_ROOT / ".github" / "workflows" / "ci.yml").read_text(encoding="utf-8")

        for script in (
            "tools/check_operational_readiness.py",
            "tools/run_service_sustained_probe.py",
            "tools/run_operational_recovery_drill.py",
        ):
            self.assertIn(script, verify_all)
            self.assertIn(script, ci_workflow)


if __name__ == "__main__":
    unittest.main()
