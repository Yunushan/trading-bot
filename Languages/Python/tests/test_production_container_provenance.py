from __future__ import annotations

import copy
import importlib.util
import json
import subprocess
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import patch


ROOT = Path(__file__).resolve().parents[3]
VERIFY_PATH = ROOT / "tools" / "verify_production_container_provenance.py"
SCAN_PATH = ROOT / "tools" / "write_container_scan_attestation.py"


def _import(path: Path, name: str):
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


verify = _import(VERIFY_PATH, "verify_production_container_provenance")
scan = _import(SCAN_PATH, "write_container_scan_attestation")

REPO = "Yunushan/trading-bot"
COMMIT = "a" * 40
DIGEST = "sha256:" + "b" * 64
IMAGE_NAME = "ghcr.io/yunushan/trading-bot/service"
IMAGE = IMAGE_NAME + "@" + DIGEST
TAG = "v1.2.3"
NOW = datetime(2026, 9, 23, 12, tzinfo=timezone.utc)
RUN = f"https://github.com/{REPO}/actions/runs/123/attempts/1"


def _entry(kind: str, predicate: dict, *, run: str = RUN, at: datetime = NOW) -> dict:
    return {
        "verificationResult": {
            "signature": {
                "certificate": {
                    "issuer": "https://token.actions.githubusercontent.com",
                    "buildSignerURI": f"https://github.com/{REPO}/{verify.PUBLISH_WORKFLOW}@refs/tags/{TAG}",
                    "sourceRepositoryURI": f"https://github.com/{REPO}",
                    "sourceRepositoryDigest": COMMIT,
                    "sourceRepositoryRef": f"refs/tags/{TAG}",
                    "runnerEnvironment": "github-hosted",
                    "buildTrigger": "workflow_dispatch",
                    "runInvocationURI": run,
                }
            },
            "verifiedTimestamps": [{"type": "Tlog", "timestamp": at.isoformat()}],
            "statement": {
                "subject": [{"name": IMAGE_NAME, "digest": {"sha256": DIGEST[7:]}}],
                "predicateType": kind,
                "predicate": predicate,
            },
        }
    }


def _evidence() -> dict:
    return {
        "build": [_entry(verify.BUILD_TYPE, {"buildDefinition": {}})],
        "sbom": [_entry(verify.SBOM_TYPE, {"spdxVersion": "SPDX-2.3", "packages": [{"name": "python"}]})],
        "scan": [_entry(f"https://github.com/{REPO}/attestations/container-scan/v1", {
            "schema_version": 1,
            "result": "pass",
            "policy": "tools/check_container_vulnerability_policy.py",
            "severity_threshold": "HIGH,CRITICAL",
            "source_commit": COMMIT,
            "release_tag": TAG,
            "image_name": IMAGE_NAME,
            "image_digest": DIGEST,
            "image_id": "sha256:" + "c" * 64,
            "trivy_report_sha256": "d" * 64,
            "sbom_sha256": "e" * 64,
        })],
    }


class ProductionContainerProvenanceTests(unittest.TestCase):
    def evaluate(self, evidence: dict) -> dict:
        return verify.evaluate_verified_attestations(
            evidence, image=IMAGE, repository=REPO, commit=COMMIT, release_tag=TAG, now=NOW,
        )

    def test_f06_correctly_labeled_but_unattested_image_is_rejected(self) -> None:
        # The old workflow accepted a digest and a self-declared revision label.
        # Neither supplies a signed build or scan statement.
        for missing in ("build", "sbom", "scan"):
            with self.subTest(missing=missing):
                evidence = _evidence()
                evidence[missing] = []
                with self.assertRaisesRegex(ValueError, "missing verified"):
                    self.evaluate(evidence)

    def test_fresh_same_run_exact_digest_bundle_passes(self) -> None:
        report = self.evaluate(_evidence())
        self.assertTrue(report["ok"])
        self.assertEqual(IMAGE, report["image"])
        self.assertEqual(RUN, report["publisher_run"])

    def test_wrong_source_digest_workflow_issuer_ref_or_subject_fails(self) -> None:
        mutations = [
            ("signature", "certificate", "sourceRepositoryDigest", "f" * 40),
            ("signature", "certificate", "buildSignerURI", "https://github.com/attacker/build.yml"),
            ("signature", "certificate", "issuer", "https://attacker.invalid"),
            ("signature", "certificate", "sourceRepositoryRef", "refs/heads/main"),
            ("signature", "certificate", "runnerEnvironment", "self-hosted"),
            ("statement", "subject", 0, {"name": IMAGE_NAME, "digest": {"sha256": "f" * 64}}),
        ]
        for *path, value in mutations:
            with self.subTest(path=path):
                evidence = _evidence()
                target = evidence["build"][0]["verificationResult"]
                for key in path[:-1]:
                    target = target[key]
                target[path[-1]] = value
                with self.assertRaises(ValueError):
                    self.evaluate(evidence)

    def test_stale_future_missing_and_mixed_run_evidence_fails(self) -> None:
        for replacement in (NOW - timedelta(days=8), NOW + timedelta(minutes=6)):
            with self.subTest(timestamp=replacement):
                evidence = _evidence()
                evidence["scan"][0]["verificationResult"]["verifiedTimestamps"][0]["timestamp"] = replacement.isoformat()
                with self.assertRaises(ValueError):
                    self.evaluate(evidence)
        evidence = _evidence()
        evidence["scan"][0]["verificationResult"]["verifiedTimestamps"] = []
        with self.assertRaises(ValueError):
            self.evaluate(evidence)
        evidence = _evidence()
        evidence["scan"][0]["verificationResult"]["signature"]["certificate"]["runInvocationURI"] = f"https://github.com/{REPO}/actions/runs/124/attempts/1"
        with self.assertRaises(ValueError):
            self.evaluate(evidence)

    def test_failed_scan_wrong_digest_missing_sbom_or_wrong_policy_fails(self) -> None:
        changes = [
            ("result", "fail"),
            ("image_digest", "sha256:" + "f" * 64),
            ("source_commit", "f" * 40),
            ("policy", "tools/allow_everything.py"),
            ("trivy_report_sha256", ""),
        ]
        for field, value in changes:
            with self.subTest(field=field):
                evidence = _evidence()
                evidence["scan"][0]["verificationResult"]["statement"]["predicate"][field] = value
                with self.assertRaises(ValueError):
                    self.evaluate(evidence)
        evidence = _evidence()
        evidence["sbom"][0]["verificationResult"]["statement"]["predicate"]["packages"] = []
        with self.assertRaises(ValueError):
            self.evaluate(evidence)

    def test_verified_cli_is_the_required_entry_point(self) -> None:
        evidence = _evidence()
        calls = []

        def fake_run(argv, **kwargs):
            calls.append(argv)
            kind = argv[argv.index("--predicate-type") + 1]
            entry_name = {verify.BUILD_TYPE: "build", verify.SBOM_TYPE: "sbom"}.get(kind, "scan")
            return subprocess.CompletedProcess(argv, 0, json.dumps(evidence[entry_name]), "")

        with patch.object(verify.subprocess, "run", side_effect=fake_run):
            result = verify.verify_with_gh(IMAGE, REPO, COMMIT, TAG)
        self.assertTrue(result["ok"])
        self.assertEqual(3, len(calls))
        for argv in calls:
            self.assertIn(f"oci://{IMAGE}", argv)
            self.assertIn("--signer-workflow", argv)
            self.assertIn("--source-digest", argv)
            self.assertIn("--source-ref", argv)
            self.assertIn("--deny-self-hosted-runners", argv)

    def test_cli_verification_failure_never_accepts_json(self) -> None:
        fake = subprocess.CompletedProcess([], 1, json.dumps(_evidence()["build"]), "untrusted")
        with patch.object(verify.subprocess, "run", return_value=fake):
            with self.assertRaisesRegex(ValueError, "verification.*failed"):
                verify.verify_with_gh(IMAGE, REPO, COMMIT, TAG)

    def test_failed_live_verification_writes_no_success_artifact(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / "proof.json"
            with patch.object(verify, "verify_with_gh", side_effect=ValueError("unattested")):
                status = verify.main([
                    "--image", IMAGE, "--repository", REPO, "--commit", COMMIT,
                    "--release-tag", TAG, "--output", str(output),
                ])
            self.assertEqual(1, status)
            self.assertFalse(output.exists())

    def test_deployment_verifies_before_kubernetes_credentials_or_apply(self) -> None:
        workflow = (ROOT / ".github/workflows/deploy-production-readonly.yml").read_text(encoding="utf-8")
        verifier = workflow.index("Verify trusted exact-digest build, SBOM, and scan provenance")
        credentials = workflow.index("Configure Kubernetes credentials")
        mutation = workflow.index("Apply and wait for rollout")
        self.assertLess(verifier, credentials)
        self.assertLess(credentials, mutation)
        self.assertIn("--repository \"${GITHUB_REPOSITORY}\"", workflow)
        self.assertIn("--release-tag \"${RELEASE_TAG}\"", workflow)

    def test_publisher_scans_and_attests_one_published_digest(self) -> None:
        workflow = (ROOT / ".github/workflows/publish-production-readonly-image.yml").read_text(encoding="utf-8")
        self.assertLess(workflow.index("Build and publish candidate once"), workflow.index("Scan published image ID"))
        self.assertLess(workflow.index("Enforce exact-image scan policy"), workflow.index("Attest exact-digest build provenance"))
        self.assertIn('image_ref="${image_name}@${digest}"', workflow)
        self.assertIn('docker pull "${image_ref}"', workflow)
        self.assertIn('grep -Fx -- "${image_ref}"', workflow)
        self.assertIn("image_id=\"$(docker image inspect --format '{{.Id}}' \"${image_ref}\")\"", workflow)
        self.assertIn("--image-id-file container-image-id.txt", workflow)
        self.assertIn("subject-digest: ${{ steps.publish.outputs.image_digest }}", workflow)
        self.assertEqual(3, workflow.count("subject-digest: ${{ steps.publish.outputs.image_digest }}"))
        self.assertIn("image-ref: ${{ steps.publish.outputs.image_id }}", workflow)


class ScanPredicateTests(unittest.TestCase):
    def test_only_clean_inventory_and_sbom_yield_pass_predicate(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            image_id = "sha256:" + "c" * 64
            (root / "id").write_text(image_id, encoding="utf-8")
            (root / "runtime").write_text(json.dumps({"ok": True, "image_id": image_id, "packages": {"msgpack": ["1.2.1"]}}), encoding="utf-8")
            report = {
                "SchemaVersion": 2, "ArtifactType": "container_image",
                "Metadata": {"ImageID": image_id, "OS": {"Family": "wolfi"}},
                "Results": [
                    {"Target": "image", "Class": "os-pkgs", "Type": "wolfi", "Packages": [{"Name": "python", "Version": "3.14"}]},
                    {"Target": "python", "Class": "lang-pkgs", "Type": "python-pkg", "Packages": [{"Name": "msgpack", "Version": "1.2.1"}], "Vulnerabilities": []},
                ],
            }
            (root / "report").write_text(json.dumps(report), encoding="utf-8")
            (root / "sbom").write_text(json.dumps({"spdxVersion": "SPDX-2.3", "packages": [{"name": "python"}]}), encoding="utf-8")
            args = dict(image=IMAGE, commit=COMMIT, release_tag=TAG, report=root / "report", runtime=root / "runtime", image_id_file=root / "id", sbom=root / "sbom")
            predicate = scan.make_predicate(**args)
            self.assertEqual("pass", predicate["result"])
            self.assertEqual(DIGEST, predicate["image_digest"])
            vulnerable = copy.deepcopy(report)
            vulnerable["Results"][1]["Vulnerabilities"] = [{"Severity": "HIGH", "PkgName": "msgpack", "InstalledVersion": "1.2.1", "VulnerabilityID": "CVE-1"}]
            (root / "report").write_text(json.dumps(vulnerable), encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "HIGH or CRITICAL"):
                scan.make_predicate(**args)
            wrong_image = copy.deepcopy(report)
            wrong_image["Metadata"]["ImageID"] = "sha256:" + "f" * 64
            (root / "report").write_text(json.dumps(wrong_image), encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "built image ID"):
                scan.make_predicate(**args)
            (root / "report").write_text(json.dumps(report), encoding="utf-8")
            (root / "sbom").write_text(json.dumps({"spdxVersion": "SPDX-2.3", "packages": []}), encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "SBOM"):
                scan.make_predicate(**args)


if __name__ == "__main__":
    unittest.main()
