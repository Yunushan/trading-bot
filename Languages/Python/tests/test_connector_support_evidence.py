from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch


REPO_ROOT = Path(__file__).resolve().parents[3]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from tools import check_connector_support_matrix as connector_matrix  # noqa: E402
from tools import check_generated_evidence_source_control as evidence_guard  # noqa: E402


class ConnectorSupportEvidenceTests(unittest.TestCase):
    def _target(self) -> dict[str, object]:
        return {
            "id": "connector-example-example",
            "group": "example",
            "venue": "Example",
            "backend": "example-rest",
            "status": "order-routing-supported-evidence-required",
            "capabilities_required": ["market-data", "account-snapshot", "order-routing"],
            "capabilities_gated": ["official-live-evidence"],
            "evidence_required": True,
        }

    def _artifact(self, target: dict[str, object], matrix_sha256: str) -> dict[str, object]:
        capabilities = list(target["capabilities_required"])
        return {
            "schema_version": 1,
            "evidence_id": target["id"],
            "target_id": target["id"],
            "group": target["group"],
            "venue": target["venue"],
            "backend": target["backend"],
            "status": "passed",
            "passed": True,
            "generated_at": "2026-08-23T16:00:00+00:00",
            "commit": "current-commit",
            "source_tree_clean": True,
            "matrix_sha256": matrix_sha256,
            "target_contract_sha256": connector_matrix._target_contract_sha256(target),
            "evidence_scope": "testnet",
            "command": "python external_connector_harness.py --target connector-example-example",
            "environment": {"credentials_present": True, "secrets_in_artifact": False},
            "capabilities_tested": capabilities,
            "suite_results": [{"name": capability, "status": "passed"} for capability in capabilities],
            "order_lifecycle": {
                "mode": "testnet",
                "submission_attempted": True,
                "acknowledged": True,
                "cleanup_confirmed": True,
                "order_identifier_redacted": True,
                "production_funds_at_risk": False,
            },
            "secrets_redacted": True,
            "secrets_in_artifact": False,
            "runtime_ready_claimed": False,
        }

    def _validate(self, artifact: dict[str, object]) -> list[str]:
        target = self._target()
        with tempfile.TemporaryDirectory() as temp_dir:
            evidence_dir = Path(temp_dir)
            (evidence_dir / f"{target['id']}.json").write_text(json.dumps(artifact), encoding="utf-8")
            with patch.object(connector_matrix, "_current_git_commit", return_value="current-commit"):
                return connector_matrix._validate_evidence(
                    [target],
                    evidence_dir,
                    matrix_sha256="matrix-sha",
                    require_current_commit=True,
                    require_clean_source=True,
                )

    def test_strict_connector_evidence_accepts_source_bound_order_lifecycle(self):
        target = self._target()
        self.assertEqual([], self._validate(self._artifact(target, "matrix-sha")))

    def test_strict_connector_evidence_rejects_stale_weak_or_unsafe_proof(self):
        target = self._target()
        artifact = self._artifact(target, "matrix-sha")
        artifact["commit"] = "stale-commit"
        artifact["target_contract_sha256"] = "0" * 64
        artifact["capabilities_tested"] = ["market-data"]
        artifact["suite_results"] = [{"name": "market-data", "status": "passed"}]
        artifact["order_lifecycle"] = {
            **artifact["order_lifecycle"],
            "acknowledged": False,
            "production_funds_at_risk": True,
        }
        artifact["environment"] = {"api_token": "not-redacted"}

        issues = self._validate(artifact)

        self.assertTrue(any("commit must match current git commit" in issue for issue in issues))
        self.assertTrue(any("target_contract_sha256" in issue for issue in issues))
        self.assertTrue(any("capabilities_tested must exactly match" in issue for issue in issues))
        self.assertTrue(any("suite_results must include account-snapshot" in issue for issue in issues))
        self.assertTrue(any("order_lifecycle.acknowledged must be true" in issue for issue in issues))
        self.assertTrue(any("production_funds_at_risk must be false" in issue for issue in issues))
        self.assertTrue(any("unredacted secret field: api_token" in issue for issue in issues))

    def test_connector_and_operational_evidence_are_generated_not_source(self):
        self.assertTrue(evidence_guard._matches_generated_evidence_artifact("connector-support-evidence/a.json"))
        self.assertTrue(
            evidence_guard._matches_generated_evidence_artifact(
                "artifacts/operational-readiness/service-config-backup-restore.json"
            )
        )


if __name__ == "__main__":
    unittest.main()
