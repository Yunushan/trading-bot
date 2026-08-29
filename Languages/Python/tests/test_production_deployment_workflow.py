import unittest
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[3]


class ProductionDeploymentWorkflowTests(unittest.TestCase):
    def setUp(self) -> None:
        self.workflow = (
            REPO_ROOT / ".github" / "workflows" / "deploy-production-readonly.yml"
        ).read_text(encoding="utf-8")
        self.dockerfile = (REPO_ROOT / "docker" / "backend.Dockerfile").read_text(
            encoding="utf-8"
        )

    def test_deployment_is_manual_protected_tag_only_and_stable_release_bound(self):
        self.assertIn("workflow_dispatch:", self.workflow)
        self.assertIn("environment:", self.workflow)
        self.assertIn("name: production", self.workflow)
        self.assertIn("RELEASE_REF_TYPE: ${{ github.ref_type }}", self.workflow)
        self.assertIn("RELEASE_REF_PROTECTED: ${{ github.ref_protected }}", self.workflow)
        self.assertIn("DEPLOY_CONFIRMATION: ${{ inputs.confirmation }}", self.workflow)
        self.assertIn("DEPLOY_READONLY_PRODUCTION", self.workflow)
        self.assertIn("Only a published stable release may be deployed.", self.workflow)

    def test_deployment_binds_image_to_commit_and_validates_kubernetes_rollout(self):
        self.assertIn("render_production_deployment.py", self.workflow)
        self.assertIn("--require-rendered", self.workflow)
        self.assertIn("docker pull", self.workflow)
        self.assertIn("org.opencontainers.image.revision", self.workflow)
        self.assertIn("PRODUCTION_KUBECONFIG_B64", self.workflow)
        self.assertIn("--dry-run=server", self.workflow)
        self.assertIn("kubectl apply", self.workflow)
        self.assertIn("rollout status", self.workflow)
        self.assertIn("run_service_sustained_probe.py", self.workflow)
        self.assertIn("--profile quick", self.workflow)

    def test_deployment_never_places_service_token_in_command_arguments(self):
        self.assertIn("BOT_SERVICE_API_TOKEN: ${{ secrets.BOT_SERVICE_API_TOKEN }}", self.workflow)
        self.assertIn("--api-token-env BOT_SERVICE_API_TOKEN", self.workflow)
        self.assertNotIn("--api-token ", self.workflow)
        self.assertNotIn("kubectl get secret", self.workflow)

    def test_container_records_source_revision_label(self):
        self.assertIn("ARG BUILD_COMMIT=unknown", self.dockerfile)
        self.assertIn('LABEL org.opencontainers.image.revision="${BUILD_COMMIT}"', self.dockerfile)

    def test_ci_container_builds_bind_revision_label_to_checked_out_commit(self):
        ci_workflow = (REPO_ROOT / ".github" / "workflows" / "ci.yml").read_text(
            encoding="utf-8"
        )
        supply_chain_workflow = (
            REPO_ROOT / ".github" / "workflows" / "supply-chain-security.yml"
        ).read_text(encoding="utf-8")
        for workflow in (ci_workflow, supply_chain_workflow):
            self.assertIn('--build-arg BUILD_COMMIT="$GITHUB_SHA"', workflow)
            self.assertIn("org.opencontainers.image.revision", workflow)
            self.assertIn('!= "$GITHUB_SHA"', workflow)
