from __future__ import annotations

import copy
import importlib.util
import sys
import tempfile
import unittest
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[3]
CHECKER_PATH = REPO_ROOT / "tools" / "check_production_deployment.py"
RENDERER_PATH = REPO_ROOT / "tools" / "render_production_deployment.py"

CHECKER_SPEC = importlib.util.spec_from_file_location("check_production_deployment", CHECKER_PATH)
assert CHECKER_SPEC and CHECKER_SPEC.loader
checker = importlib.util.module_from_spec(CHECKER_SPEC)
CHECKER_SPEC.loader.exec_module(checker)
sys.modules["check_production_deployment"] = checker

RENDERER_SPEC = importlib.util.spec_from_file_location("render_production_deployment", RENDERER_PATH)
assert RENDERER_SPEC and RENDERER_SPEC.loader
renderer = importlib.util.module_from_spec(RENDERER_SPEC)
RENDERER_SPEC.loader.exec_module(renderer)


class ProductionDeploymentTests(unittest.TestCase):
    def test_checked_in_template_passes_the_fail_closed_contract(self) -> None:
        report = checker.audit_manifest(REPO_ROOT / checker.DEFAULT_MANIFEST_PATH)

        self.assertTrue(report["ok"], report["issues"])
        self.assertEqual("stateless-read-only-service-api", report["declared_scope"])
        self.assertFalse(report["trading_execution_ha_claimed"])
        self.assertTrue(all(report["checks"].values()))

    def test_renderer_binds_image_digest_and_commit_without_embedding_a_secret(self) -> None:
        image = f"registry.example.com/trading-bot/service@sha256:{'a' * 64}"
        commit = "b" * 40
        payload = renderer.render_manifest(image=image, build_commit=commit)
        report = checker.validate_manifest(payload, require_rendered=True)

        self.assertTrue(report["ok"], report["issues"])
        rendered_text = str(payload)
        self.assertIn(image, rendered_text)
        self.assertIn(commit, rendered_text)
        self.assertNotIn(checker.IMAGE_SENTINEL, rendered_text)
        self.assertNotIn(checker.COMMIT_SENTINEL, rendered_text)
        self.assertNotIn("'kind': 'Secret'", rendered_text)

        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / "deployment.json"
            renderer.write_manifest(output, payload)
            reloaded = checker.load_manifest(output)
        self.assertEqual(payload, reloaded)

    def test_renderer_rejects_mutable_images_and_placeholder_commits(self) -> None:
        with self.assertRaisesRegex(ValueError, "immutable image reference"):
            renderer.render_manifest(image="registry.example.com/service:latest", build_commit="b" * 40)
        with self.assertRaisesRegex(ValueError, "non-placeholder"):
            renderer.render_manifest(
                image=f"registry.example.com/service@sha256:{'a' * 64}",
                build_commit=checker.COMMIT_SENTINEL,
            )

    def test_checker_rejects_replica_and_read_only_regressions(self) -> None:
        payload = copy.deepcopy(checker.load_manifest(REPO_ROOT / checker.DEFAULT_MANIFEST_PATH))
        deployment = next(item for item in payload["items"] if item["kind"] == "Deployment")
        deployment["spec"]["replicas"] = 1
        environment = deployment["spec"]["template"]["spec"]["containers"][0]["env"]
        next(item for item in environment if item["name"] == "BOT_SERVICE_API_READ_ONLY")["value"] = "0"

        report = checker.validate_manifest(payload)

        self.assertFalse(report["ok"])
        self.assertFalse(report["checks"]["three_replicas"])
        self.assertFalse(report["checks"]["api_read_only"])

    def test_checker_rejects_unreviewed_resources_and_broken_workload_wiring(self) -> None:
        payload = copy.deepcopy(checker.load_manifest(REPO_ROOT / checker.DEFAULT_MANIFEST_PATH))
        payload["items"].append(
            {
                "apiVersion": "v1",
                "kind": "ConfigMap",
                "metadata": {"name": "unreviewed", "namespace": checker.NAMESPACE},
            }
        )
        deployment = next(item for item in payload["items"] if item["kind"] == "Deployment")
        deployment["spec"]["template"]["spec"]["initContainers"] = [
            {"name": "unexpected", "image": "example.invalid/unreviewed:latest"}
        ]
        service = next(item for item in payload["items"] if item["kind"] == "Service")
        service["spec"]["selector"] = {"app.kubernetes.io/name": "wrong-workload"}

        report = checker.validate_manifest(payload)

        self.assertFalse(report["ok"])
        self.assertFalse(report["checks"]["exact_resource_set"])
        self.assertFalse(report["checks"]["no_auxiliary_containers"])
        self.assertFalse(report["checks"]["cluster_only_service"])

    def test_checker_requires_the_reviewed_group_read_secret_projection(self) -> None:
        payload = copy.deepcopy(checker.load_manifest(REPO_ROOT / checker.DEFAULT_MANIFEST_PATH))
        deployment = next(item for item in payload["items"] if item["kind"] == "Deployment")
        pod_spec = deployment["spec"]["template"]["spec"]
        token_volume = next(item for item in pod_spec["volumes"] if item["name"] == "service-api-token")
        token_volume["secret"]["defaultMode"] = 420

        report = checker.validate_manifest(payload)

        self.assertFalse(report["ok"])
        self.assertFalse(report["checks"]["secret_mount"])

    def test_checker_rejects_resource_identity_and_duplicate_environment_bypasses(self) -> None:
        payload = copy.deepcopy(checker.load_manifest(REPO_ROOT / checker.DEFAULT_MANIFEST_PATH))
        namespace = next(item for item in payload["items"] if item["kind"] == "Namespace")
        namespace["metadata"]["name"] = checker.WORKLOAD_NAME
        deployment = next(item for item in payload["items"] if item["kind"] == "Deployment")
        environment = deployment["spec"]["template"]["spec"]["containers"][0]["env"]
        environment.insert(0, {"name": "BOT_SERVICE_API_READ_ONLY", "value": "0"})

        report = checker.validate_manifest(payload)

        self.assertFalse(report["ok"])
        self.assertFalse(report["checks"]["resource_identity"])
        self.assertFalse(report["checks"]["environment_allowlist"])

    def test_checker_rejects_probe_hpa_and_network_policy_drift(self) -> None:
        payload = copy.deepcopy(checker.load_manifest(REPO_ROOT / checker.DEFAULT_MANIFEST_PATH))
        deployment = next(item for item in payload["items"] if item["kind"] == "Deployment")
        container = deployment["spec"]["template"]["spec"]["containers"][0]
        container["readinessProbe"]["failureThreshold"] = 30
        hpa = next(item for item in payload["items"] if item["kind"] == "HorizontalPodAutoscaler")
        hpa["spec"]["metrics"][0]["resource"]["target"]["averageUtilization"] = 99
        network_policy = next(item for item in payload["items"] if item["kind"] == "NetworkPolicy")
        network_policy["spec"]["ingress"].append({})

        report = checker.validate_manifest(payload)

        self.assertFalse(report["ok"])
        self.assertFalse(report["checks"]["health_probes"])
        self.assertFalse(report["checks"]["bounded_autoscaling"])
        self.assertFalse(report["checks"]["default_deny_network"])

    def test_authoritative_verifiers_run_the_deployment_contract(self) -> None:
        verify_all = (REPO_ROOT / "tools" / "verify_all.py").read_text(encoding="utf-8")
        ci_workflow = (REPO_ROOT / ".github" / "workflows" / "ci.yml").read_text(encoding="utf-8")

        for verifier in (verify_all, ci_workflow):
            self.assertIn("tools/check_production_deployment.py", verifier)
        self.assertIn("tools/render_production_deployment.py", ci_workflow)
        self.assertIn("--require-rendered", ci_workflow)


if __name__ == "__main__":
    unittest.main()
