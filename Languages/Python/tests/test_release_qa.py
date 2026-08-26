from __future__ import annotations

import importlib.util
from contextlib import redirect_stderr
from io import StringIO
import os
import tempfile
import unittest
from unittest import mock
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[3]
CHECKER_PATH = REPO_ROOT / "tools" / "check_release_qa.py"
REVISION = "a" * 40
RELEASE_WORKFLOWS = (
    "release-windows.yml",
    "release-linux-macos.yml",
    "release-freebsd.yml",
)


def _load_checker():
    spec = importlib.util.spec_from_file_location("check_release_qa", CHECKER_PATH)
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _approved_note(tag: str = "v1.2.3") -> str:
    return f"""# Release QA: {tag}

- Release tag: {tag}
- Source revision: {REVISION}
- Completed on: 2026-07-18
- Operator: Release engineering
- Outcome: approved
- Candidate CI run ID: 123456780
- Candidate CI run URL: https://github.com/example/trading-bot/actions/runs/123456780
- CodeQL run ID: 123456781
- CodeQL run URL: https://github.com/example/trading-bot/actions/runs/123456781
- Supply chain security run ID: 123456782
- Supply chain security run URL: https://github.com/example/trading-bot/actions/runs/123456782
- Release platform evidence run ID: 123456789
- Release platform evidence run URL: https://github.com/example/trading-bot/actions/runs/123456789
- Release platform evidence scope: full

- [x] Desktop visual flow: Passed with expected controls and error states.
- [x] Service API flow: Passed health, authentication, and unavailable-service checks.
- [x] LLM/local-model flow: Passed disabled, missing-token, and unavailable-model checks.
- [x] Release package: Passed clean start, provenance, SBOM, and uninstall checks.
- [x] Native signing and notarization: Protected credentials and fail-closed trust gates were reviewed.
"""


class ReleaseQaTests(unittest.TestCase):
    def test_accepts_complete_approved_note_for_current_revision(self):
        checker = _load_checker()
        with tempfile.TemporaryDirectory() as temp_dir:
            note = Path(temp_dir) / "v1.2.3.md"
            note.write_text(_approved_note(), encoding="utf-8")
            self.assertEqual([], checker.validate_release_qa_note(note, tag="v1.2.3", source_revision=REVISION))

    def test_rejects_incomplete_or_unapproved_note(self):
        checker = _load_checker()
        with tempfile.TemporaryDirectory() as temp_dir:
            note = Path(temp_dir) / "v1.2.3.md"
            note.write_text(
                _approved_note()
                .replace("- Outcome: approved", "- Outcome: pending")
                .replace("- [x] Release package", "- [ ] Release package"),
                encoding="utf-8",
            )
            issues = checker.validate_release_qa_note(note, tag="v1.2.3", source_revision=REVISION)
        self.assertIn("QA note Outcome must be approved", issues)
        self.assertIn("QA note must record a completed Release package check", issues)

    def test_rejects_non_semantic_release_tag_and_displaced_heading(self):
        checker = _load_checker()
        tag = "vnot-a-version"
        note_text = "Unexpected preface\n" + _approved_note(tag)
        with tempfile.TemporaryDirectory() as temp_dir:
            note = Path(temp_dir) / f"{tag}.md"
            note.write_text(note_text, encoding="utf-8")
            issues = checker.validate_release_qa_note(
                note,
                tag=tag,
                source_revision=REVISION,
            )
        self.assertIn(
            f"release tag must use vMAJOR.MINOR.PATCH form: {tag}",
            issues,
        )
        self.assertIn(
            f"QA note must start with the release heading for {tag}",
            issues,
        )

    def test_rejects_ambiguous_duplicate_release_metadata(self):
        checker = _load_checker()
        note_text = _approved_note().replace(
            "- Outcome: approved\n",
            "- Outcome: approved\n- Outcome: approved\n",
        )
        note_text += "- CodeQL run ID: 123456781\n"
        with tempfile.TemporaryDirectory() as temp_dir:
            note = Path(temp_dir) / "v1.2.3.md"
            note.write_text(note_text, encoding="utf-8")
            issues = checker.validate_release_qa_note(
                note,
                tag="v1.2.3",
                source_revision=REVISION,
            )
        self.assertIn("QA note Outcome must appear exactly once", issues)
        self.assertIn("QA note CodeQL run ID must appear exactly once", issues)

    def test_v1_0_40_does_not_retroactively_require_native_signing(self):
        checker = _load_checker()
        note_text = _approved_note("v1.0.40").replace(
            "- [x] Native signing and notarization: Protected credentials and fail-closed trust gates were reviewed.\n",
            "",
        )
        for line in (
            "- Candidate CI run ID: 123456780\n",
            "- Candidate CI run URL: https://github.com/example/trading-bot/actions/runs/123456780\n",
            "- CodeQL run ID: 123456781\n",
            "- CodeQL run URL: https://github.com/example/trading-bot/actions/runs/123456781\n",
            "- Supply chain security run ID: 123456782\n",
            "- Supply chain security run URL: https://github.com/example/trading-bot/actions/runs/123456782\n",
        ):
            note_text = note_text.replace(line, "")
        with tempfile.TemporaryDirectory() as temp_dir:
            note = Path(temp_dir) / "v1.0.40.md"
            note.write_text(note_text, encoding="utf-8")
            issues = checker.validate_release_qa_note(
                note,
                tag="v1.0.40",
                source_revision=REVISION,
            )
        self.assertEqual([], issues)

    def test_v1_0_41_requires_native_signing_and_notarization_review(self):
        checker = _load_checker()
        note_text = _approved_note("v1.0.41").replace(
            "- [x] Native signing and notarization: Protected credentials and fail-closed trust gates were reviewed.\n",
            "",
        )
        with tempfile.TemporaryDirectory() as temp_dir:
            note = Path(temp_dir) / "v1.0.41.md"
            note.write_text(note_text, encoding="utf-8")
            issues = checker.validate_release_qa_note(
                note,
                tag="v1.0.41",
                source_revision=REVISION,
            )
        self.assertIn(
            "QA note must record a completed Native signing and notarization check",
            issues,
        )

    def test_v1_0_41_requires_exact_source_ci_and_security_run_bindings(self):
        checker = _load_checker()
        note_text = _approved_note("v1.0.41").replace(
            "- CodeQL run ID: 123456781\n",
            "",
        )
        with tempfile.TemporaryDirectory() as temp_dir:
            note = Path(temp_dir) / "v1.0.41.md"
            note.write_text(note_text, encoding="utf-8")
            issues = checker.validate_release_qa_note(
                note,
                tag="v1.0.41",
                source_revision=REVISION,
            )
        self.assertIn(
            "QA note CodeQL run ID must be a positive GitHub Actions run ID",
            issues,
        )

    def test_release_run_urls_must_match_ids_and_current_repository(self):
        checker = _load_checker()
        note_text = _approved_note().replace(
            "actions/runs/123456781",
            "actions/runs/987654321",
        )
        with tempfile.TemporaryDirectory() as temp_dir:
            note = Path(temp_dir) / "v1.2.3.md"
            note.write_text(note_text, encoding="utf-8")
            issues = checker.validate_release_qa_note(
                note,
                tag="v1.2.3",
                source_revision=REVISION,
                repository="current/trading-bot",
            )
        self.assertIn(
            "QA note CodeQL run URL must reference the recorded run ID",
            issues,
        )
        self.assertTrue(
            any("must reference the current repository current/trading-bot" in issue for issue in issues)
        )

    def test_requires_a_positive_platform_evidence_run_id_when_requested(self):
        checker = _load_checker()
        with tempfile.TemporaryDirectory() as temp_dir:
            note = Path(temp_dir) / "v1.2.3.md"
            note.write_text(
                _approved_note().replace("- Release platform evidence run ID: 123456789\n", ""),
                encoding="utf-8",
            )
            issues = checker.validate_release_qa_note(
                note,
                tag="v1.2.3",
                source_revision=REVISION,
                require_platform_evidence_run=True,
            )
        self.assertIn("QA note Release platform evidence run ID must be a positive GitHub Actions run ID", issues)

    def test_requires_a_known_platform_evidence_scope_when_requested(self):
        checker = _load_checker()
        with tempfile.TemporaryDirectory() as temp_dir:
            note = Path(temp_dir) / "v1.2.3.md"
            note.write_text(
                _approved_note().replace(
                    "- Release platform evidence scope: full", "- Release platform evidence scope: partial"
                ),
                encoding="utf-8",
            )
            issues = checker.validate_release_qa_note(
                note,
                tag="v1.2.3",
                source_revision=REVISION,
                require_platform_evidence_run=True,
            )
        self.assertIn("QA note Release platform evidence scope must be one of: full, hosted-only", issues)

    def test_requires_platform_evidence_url_to_match_run_id(self):
        checker = _load_checker()
        with tempfile.TemporaryDirectory() as temp_dir:
            note = Path(temp_dir) / "v1.2.3.md"
            note.write_text(
                _approved_note().replace(
                    "actions/runs/123456789",
                    "actions/runs/987654321",
                ),
                encoding="utf-8",
            )
            issues = checker.validate_release_qa_note(
                note,
                tag="v1.2.3",
                source_revision=REVISION,
                require_platform_evidence_run=True,
            )
        self.assertIn(
            "QA note Release platform evidence run URL must reference the recorded run ID",
            issues,
        )

    def test_requires_platform_evidence_url_when_requested(self):
        checker = _load_checker()
        with tempfile.TemporaryDirectory() as temp_dir:
            note = Path(temp_dir) / "v1.2.3.md"
            note.write_text(
                _approved_note().replace(
                    "- Release platform evidence run URL: https://github.com/example/trading-bot/actions/runs/123456789\n",
                    "",
                ),
                encoding="utf-8",
            )
            issues = checker.validate_release_qa_note(
                note,
                tag="v1.2.3",
                source_revision=REVISION,
                require_platform_evidence_run=True,
            )
        self.assertIn(
            "QA note Release platform evidence run URL must be a GitHub Actions run URL",
            issues,
        )

    def test_release_qa_commit_mode_requires_a_current_revision(self):
        checker = _load_checker()
        with mock.patch.dict(os.environ, {}, clear=True):
            with redirect_stderr(StringIO()):
                with self.assertRaises(SystemExit) as error:
                    checker.main(
                        [
                            "--tag",
                            "v1.2.3",
                            "--note",
                            "docs/release-qa/v1.2.3.md",
                            "--allow-release-qa-commit",
                        ]
                    )
        self.assertEqual(2, error.exception.code)

    def test_tagged_release_workflows_require_versioned_qa_note(self):
        for workflow_name in RELEASE_WORKFLOWS:
            with self.subTest(workflow=workflow_name):
                workflow = (REPO_ROOT / ".github" / "workflows" / workflow_name).read_text(encoding="utf-8")
                self.assertIn("Validate tagged release QA sign-off", workflow)
                self.assertIn("if: github.ref_type == 'tag'", workflow)
                self.assertIn("tools/check_release_qa.py", workflow)
                self.assertIn("tools/check_release_version.py", workflow)
                self.assertIn("docs/release-qa/${{ github.ref_name }}.md", workflow)
                self.assertIn("--require-current-revision", workflow)
                self.assertIn("--allow-release-qa-commit", workflow)
                self.assertIn("--require-platform-evidence-run", workflow)
                self.assertIn("RELEASE_TAG: ${{ github.ref_name }}", workflow)
                self.assertIn("RELEASE_QA_NOTE: docs/release-qa/${{ github.ref_name }}.md", workflow)
                self.assertNotIn('--tag "${{ github.ref_name }}"', workflow)
                self.assertNotIn('--note "docs/release-qa/${{ github.ref_name }}.md"', workflow)
                self.assertIn("fetch-depth: 0", workflow)

    def test_tagged_release_workflows_trigger_on_version_tags(self):
        for workflow_name in RELEASE_WORKFLOWS:
            with self.subTest(workflow=workflow_name):
                workflow = (REPO_ROOT / ".github" / "workflows" / workflow_name).read_text(encoding="utf-8")
                self.assertRegex(workflow, r'(?ms)^\s*push:\s*\n\s*tags:\s*\n\s*- "v\*"')

    def test_workflow_lint_uses_actionlint_compatible_go_toolchain(self):
        workflow = (REPO_ROOT / ".github" / "workflows" / "ci.yml").read_text(encoding="utf-8")

        self.assertIn('go-version: "1.25"', workflow)
        self.assertIn(
            "go install github.com/rhysd/actionlint/cmd/actionlint@v1.7.12",
            workflow,
        )

    def test_tagged_release_publishers_validate_downloaded_platform_evidence(self):
        for workflow_name in RELEASE_WORKFLOWS:
            with self.subTest(workflow=workflow_name):
                workflow = (REPO_ROOT / ".github" / "workflows" / workflow_name).read_text(encoding="utf-8")
                self.assertIn("./.github/actions/verify-release-platform-evidence", workflow)

        action = (REPO_ROOT / ".github" / "actions" / "verify-release-platform-evidence" / "action.yml").read_text(
            encoding="utf-8"
        )
        self.assertIn("actions/download-artifact@37930b1c2abaa49bbe596cd826c3c89aef350131", action)
        self.assertIn("--require-evidence", action)
        self.assertIn("--require-current-commit", action)
        self.assertIn("--require-clean-source", action)
        self.assertIn("--require-platform-evidence-run", action)
        self.assertIn("--print-platform-evidence-scope", action)
        self.assertIn("--print-production-run-evidence-required", action)
        self.assertIn("--print-candidate-ci-run-id", action)
        self.assertIn("--print-codeql-run-id", action)
        self.assertIn("--print-supply-chain-run-id", action)
        self.assertIn("--exclude-self-hosted", action)
        self.assertIn("outputs:", action)
        self.assertIn("value: ${{ steps.release_qa.outputs.source_revision }}", action)
        self.assertIn("value: ${{ steps.release_qa.outputs.evidence_run_id }}", action)
        self.assertIn("value: ${{ steps.release_qa.outputs.evidence_scope }}", action)
        self.assertIn("Verify exact-source CI and security workflow runs", action)
        self.assertIn("tools/check_release_workflow_run.py", action)
        self.assertIn(".github/workflows/ci.yml", action)
        self.assertIn(".github/workflows/codeql.yml", action)
        self.assertIn(".github/workflows/supply-chain-security.yml", action)
        self.assertIn("Require stable release source on the default branch", action)
        self.assertIn("steps.release_qa.outputs.evidence_scope == 'full'", action)
        self.assertIn("github.event.repository.default_branch", action)
        self.assertIn("git merge-base --is-ancestor", action)
        self.assertIn("Require protected release tag for stable publication", action)
        self.assertIn("RELEASE_REF_PROTECTED: ${{ github.ref_protected }}", action)
        self.assertIn('[[ "${RELEASE_REF_PROTECTED}" != "true" ]]', action)
        self.assertIn("RELEASE_TAG: ${{ inputs.tag }}", action)
        self.assertIn("RELEASE_QA_NOTE: ${{ inputs.note }}", action)
        self.assertIn('--tag "${RELEASE_TAG}"', action)
        self.assertIn('--note "${RELEASE_QA_NOTE}"', action)
        self.assertNotIn('--tag "${{ inputs.tag }}"', action)
        self.assertNotIn('--note "${{ inputs.note }}"', action)
        self.assertNotIn('--evidence-dir "${{ inputs.evidence_dir }}"', action)

    def test_platform_publishers_create_only_prerelease_candidates(self):
        for workflow_name in RELEASE_WORKFLOWS:
            with self.subTest(workflow=workflow_name):
                workflow = (REPO_ROOT / ".github" / "workflows" / workflow_name).read_text(encoding="utf-8")
                _, publish_section = workflow.split("\n  publish-release:", 1)
                self.assertIn("id: release_platform_evidence", publish_section)
                self.assertIn("prerelease: true", publish_section)
                self.assertIn("make_latest: false", publish_section)
                self.assertNotIn("make_latest: true", publish_section)
                self.assertIn("queue: max", publish_section)
                self.assertIn("tools/check_release_publication_state.py", publish_section)
                state_index = publish_section.index("tools/check_release_publication_state.py")
                upload_index = publish_section.index("uses: softprops/action-gh-release@")
                self.assertLess(state_index, upload_index)

        release_guide = (REPO_ROOT / "docs" / "RELEASES.md").read_text(encoding="utf-8")
        self.assertIn("publishers always create or update a non-latest", release_guide)
        self.assertIn("A `hosted-only` candidate must remain", release_guide)
        self.assertIn("`Finalize Stable Release`", release_guide)

    def test_stable_release_finalizer_is_aggregate_and_fail_closed(self):
        finalizer = (REPO_ROOT / ".github" / "workflows" / "finalize-release.yml").read_text(
            encoding="utf-8"
        )
        self.assertIn('"on":\n  workflow_dispatch:', finalizer)
        self.assertIn("actions: read\n      contents: write", finalizer)
        self.assertIn("environment: production", finalizer)
        self.assertIn("group: release-publish-${{ github.ref_name }}", finalizer)
        self.assertIn("cancel-in-progress: false", finalizer)
        self.assertIn("queue: max", finalizer)
        self.assertIn("RELEASE_REF_TYPE: ${{ github.ref_type }}", finalizer)
        self.assertIn("uses: ./.github/actions/verify-release-platform-evidence", finalizer)
        self.assertIn("Only full release-platform evidence may become stable/latest", finalizer)
        self.assertIn("tools/check_release_assets.py", finalizer)
        self.assertIn("--require-prerelease-candidate", finalizer)
        self.assertIn("tools/check_release_workflow_run_set.py", finalizer)
        self.assertIn(".github/workflows/release-windows.yml", finalizer)
        self.assertIn(".github/workflows/release-linux-macos.yml", finalizer)
        self.assertIn("tools/check_release_candidate_manifests.py", finalizer)
        self.assertIn("release-manifest-*.json", finalizer)
        self.assertIn("--expected-source-revision", finalizer)
        self.assertIn("RELEASE_BUILD_REVISION: ${{ github.sha }}", finalizer)
        self.assertIn("name: Restore tagged release checkout", finalizer)
        self.assertIn("prerelease: false", finalizer)
        self.assertIn("make_latest: true", finalizer)
        self.assertLess(
            finalizer.index("--require-prerelease-candidate"),
            finalizer.index("name: Promote complete candidate to stable latest release"),
        )

    def test_actionlint_queue_compatibility_exception_is_release_scoped(self):
        config = (REPO_ROOT / ".github" / "actionlint.yaml").read_text(encoding="utf-8")
        self.assertIn(".github/workflows/*release*.yml:", config)
        self.assertIn('unexpected key "queue" for "concurrency" section', config)
        self.assertNotIn(".github/workflows/**/*.yml", config)

    def test_release_publishers_restore_tagged_checkout_after_platform_evidence(self):
        for workflow_name in RELEASE_WORKFLOWS:
            with self.subTest(workflow=workflow_name):
                workflow = (REPO_ROOT / ".github" / "workflows" / workflow_name).read_text(encoding="utf-8")
                _, publish_section = workflow.split("\n  publish-release:", 1)
                evidence_index = publish_section.index("uses: ./.github/actions/verify-release-platform-evidence")
                restore_index = publish_section.index("name: Restore tagged release checkout")
                self.assertLess(evidence_index, restore_index)

    def test_split_release_workflows_use_job_scoped_permissions(self):
        for workflow_name in ("release-windows.yml", "release-linux-macos.yml"):
            with self.subTest(workflow=workflow_name):
                workflow = (REPO_ROOT / ".github" / "workflows" / workflow_name).read_text(encoding="utf-8")
                self.assertIn("permissions:\n  contents: read", workflow)
                self.assertRegex(
                    workflow,
                    r"(?ms)^  build:\n    permissions:\n      contents: read\n      id-token: write\n      attestations: write",
                )
                self.assertRegex(
                    workflow,
                    r"(?ms)^  publish-release:\n    permissions:\n      actions: read\n      contents: write",
                )

        freebsd = (REPO_ROOT / ".github" / "workflows" / "release-freebsd.yml").read_text(encoding="utf-8")
        self.assertIn("permissions:\n  contents: read\n  actions: read", freebsd)
        self.assertIn(
            "github.event_name == 'workflow_dispatch' && github.event.inputs.run_freebsd == 'true'",
            freebsd,
        )
        self.assertIn(
            "if: startsWith(github.ref, 'refs/tags/') && needs.build.result == 'success'",
            freebsd,
        )
        self.assertRegex(
            freebsd,
            r"(?ms)^  build:\n    permissions:\n      contents: read\n      actions: read",
        )
        self.assertRegex(
            freebsd,
            r"(?ms)^  publish-release:\n    permissions:\n      actions: read\n      contents: write\n      id-token: write\n      attestations: write",
        )
        build_section, publish_section = freebsd.split("\n  publish-release:", 1)
        self.assertNotIn("id-token: write", build_section)
        self.assertNotIn("attestations: write", build_section)
        self.assertIn("actions/attest@1e69f48acb82d1966a394da916b4c1698aa569d6", publish_section)

    def test_release_publishers_use_protected_serialized_environment(self):
        for workflow_name in RELEASE_WORKFLOWS:
            with self.subTest(workflow=workflow_name):
                workflow = (REPO_ROOT / ".github" / "workflows" / workflow_name).read_text(encoding="utf-8")
                _, publish_section = workflow.split("\n  publish-release:", 1)
                self.assertIn("environment: production", publish_section)
                self.assertRegex(
                    publish_section,
                    r"(?ms)concurrency:\n      group: release-publish-\$\{\{ github\.ref_name \}\}\n"
                    r"      cancel-in-progress: false",
                )
                self.assertIn("queue: max", publish_section)

    def test_freebsd_release_publisher_provisions_pinned_python(self):
        workflow = (REPO_ROOT / ".github" / "workflows" / "release-freebsd.yml").read_text(encoding="utf-8")
        _, publish_section = workflow.split("\n  publish-release:", 1)
        self.assertIn(
            "uses: actions/setup-python@5fda3b95a4ea91299a34e894583c3862153e4b97 # v7.0.0",
            publish_section,
        )
        self.assertIn('python-version: "3.14"', publish_section)

    def test_release_publishers_verify_downloaded_manifests_and_sboms(self):
        expected_counts = {
            "release-linux-macos.yml": "six",
            "release-windows.yml": "two",
        }
        for workflow_name, count_word in expected_counts.items():
            with self.subTest(workflow=workflow_name):
                workflow = (REPO_ROOT / ".github" / "workflows" / workflow_name).read_text(encoding="utf-8")
                _, publish_section = workflow.split("\n  publish-release:", 1)
                self.assertIn(
                    "uses: actions/setup-python@5fda3b95a4ea91299a34e894583c3862153e4b97 # v7.0.0",
                    publish_section,
                )
                self.assertIn('python-version: "3.14"', publish_section)
                self.assertIn("Verify downloaded release assets", publish_section)
                self.assertIn(f"Expected {count_word} ", publish_section)
                self.assertIn("release-manifest-*.json", publish_section)
                self.assertIn("release-sbom-*.spdx.json", publish_section)
                self.assertIn("--require-current-revision", publish_section)
                self.assertNotIn("mapfile", publish_section)
                self.assertIn(
                    'manifest_count="$(count_regular_files release/release-manifest-*.json)"',
                    publish_section,
                )
                self.assertIn(
                    'sbom_count="$(count_regular_files release/release-sbom-*.spdx.json)"',
                    publish_section,
                )
                self.assertIn("count_regular_files() {", publish_section)
                self.assertIn("for manifest in release/release-manifest-*.json; do", publish_section)
                self.assertNotIn("find release -maxdepth", publish_section)

    def test_native_release_packaging_uses_portable_file_enumeration(self):
        for workflow_name in ("release-freebsd.yml", "release-linux-macos.yml"):
            with self.subTest(workflow=workflow_name):
                workflow = (REPO_ROOT / ".github" / "workflows" / workflow_name).read_text(encoding="utf-8")
                build_section, _ = workflow.split("\n  publish-release:", 1)
                self.assertNotIn("find release -maxdepth", workflow)
                self.assertIn("for artifact in release/*; do", build_section)
                self.assertIn('[[ -f "${artifact}" ]] || continue', build_section)
                self.assertIn('artifacts+=("${artifact}")', build_section)

    def test_codeowners_protect_governance_and_runtime_surfaces(self):
        owners = (REPO_ROOT / ".github" / "CODEOWNERS").read_text(encoding="utf-8")

        self.assertIn("* @Yunushan", owners)
        for path in ("/.github/", "/docs/", "/tools/", "/SECURITY.md", "/experiments/"):
            with self.subTest(path=path):
                self.assertIn(f"{path} @Yunushan", owners)

    def test_operational_readiness_evidence_workflow_is_manual_and_fail_closed(self):
        workflow = (REPO_ROOT / ".github" / "workflows" / "operational-readiness-evidence.yml").read_text(
            encoding="utf-8"
        )

        self.assertIn("workflow_dispatch:", workflow)
        self.assertIn("service_base_url:", workflow)
        self.assertIn("required: true", workflow)
        self.assertRegex(
            workflow,
            r"(?ms)slo_telemetry_run_id:\n\s+description: .*\n\s+required: true",
        )
        self.assertRegex(workflow, r"(?ms)  collect:\n.*?\n    environment: production\n")
        self.assertIn("EXPECTED_SERVICE_BASE_URL: ${{ vars.PRODUCTION_SERVICE_API_ORIGIN }}", workflow)
        self.assertIn("group: operational-readiness-evidence", workflow)
        self.assertIn("id: validate_inputs", workflow)
        self.assertIn("service_base_url must exactly match the configured production service origin.", workflow)
        self.assertIn(
            'SLO_TELEMETRY_ARTIFACT}" =~ ^[A-Za-z0-9][A-Za-z0-9._-]*$',
            workflow,
        )
        self.assertIn(
            'SERVICE_BASE_URL}" =~ ^https://[^/?#]+$',
            workflow,
        )
        self.assertIn("permissions:\n  actions: read\n  contents: read", workflow)
        self.assertIn("actions/checkout@3d3c42e5aac5ba805825da76410c181273ba90b1", workflow)
        self.assertIn("actions/setup-python@5fda3b95a4ea91299a34e894583c3862153e4b97", workflow)
        self.assertIn("actions/upload-artifact@043fb46d1a93c77aae656e7c1c64a875d1fc6a0a", workflow)
        self.assertIn("--require-evidence", workflow)
        self.assertIn("--require-current-commit", workflow)
        self.assertIn("--require-clean-source", workflow)
        self.assertIn("if-no-files-found: warn", workflow)
        self.assertIn("if: ${{ steps.validate_inputs.outcome == 'success' }}", workflow)
        self.assertIn("GH_TOKEN: ${{ github.token }}", workflow)
        self.assertIn('gh run view "${SLO_TELEMETRY_RUN_ID}"', workflow)
        self.assertIn(
            "--json databaseId,status,conclusion,headSha,workflowName,event",
            workflow,
        )
        self.assertIn('status != "completed" or conclusion != "success"', workflow)
        self.assertIn("headSha must match the current promotion commit", workflow)
        self.assertIn("telemetry Actions run metadata is incomplete", workflow)
        self.assertNotIn("inputs.slo_telemetry_run_id != ''", workflow)

        runbook = (REPO_ROOT / "docs" / "OPERATOR_RUNBOOK.md").read_text(encoding="utf-8")
        self.assertIn("protected GitHub `production` environment variable", runbook)
        self.assertIn("BOT_SERVICE_API_TOKEN` secret in the same protected environment", runbook)
        self.assertIn("service_base_url` input must exactly match", runbook)
        self.assertIn("telemetry run ID is required at dispatch time", runbook)
        self.assertIn("referenced Actions run completed", runbook)
        self.assertIn("headSha` is the exact current promotion commit", runbook)
        self.assertIn("artifact from another revision is rejected", runbook)

        job_env = workflow.split("    env:\n", 1)[1].split("    steps:\n", 1)[0]
        self.assertNotIn("BOT_SERVICE_API_TOKEN", job_env)
        self.assertNotIn("GH_TOKEN", job_env)
        self.assertNotIn("GITHUB_TOKEN", job_env)
        self.assertIn(
            "        env:\n          BOT_SERVICE_API_TOKEN: ${{ secrets.BOT_SERVICE_API_TOKEN }}",
            workflow,
        )
        self.assertIn(
            "        env:\n          GH_TOKEN: ${{ github.token }}\n          GITHUB_TOKEN: ${{ github.token }}",
            workflow,
        )
        self.assertNotIn("contents: write", workflow)
        self.assertNotIn("id-token: write", workflow)
        self.assertNotIn("attestations: write", workflow)

    def test_rust_live_smoke_limits_signed_credentials_to_smoke_step(self):
        workflow = (REPO_ROOT / ".github" / "workflows" / "rust-native-live-smoke.yml").read_text(encoding="utf-8")

        signed_job = workflow.split("  public-market-data-smoke:", 1)[0]
        self.assertIn("    environment: production\n", signed_job)
        job_env = signed_job.split("    env:\n", 1)[1].split("    steps:\n", 1)[0]
        self.assertNotIn("BINANCE_API_KEY", job_env)
        self.assertNotIn("BINANCE_API_SECRET", job_env)
        self.assertIn(
            "        env:\n"
            "          BINANCE_API_KEY: ${{ secrets.BINANCE_API_KEY }}\n"
            "          BINANCE_API_SECRET: ${{ secrets.BINANCE_API_SECRET }}",
            signed_job,
        )
        self.assertIn("protected production environment secrets are required", signed_job)
        self.assertEqual(1, signed_job.count("secrets.BINANCE_API_KEY"))
        self.assertEqual(1, signed_job.count("secrets.BINANCE_API_SECRET"))
        self.assertIn("RUST_NATIVE_RUNTIME_EVIDENCE_INPUT: ${{ inputs.evidence_dir }}", workflow)
        self.assertEqual(
            2,
            workflow.count("^artifacts/rust-native-runtime-evidence(/[A-Za-z0-9._-]+)*$"),
        )

    def test_rust_release_evidence_validates_paths_and_shell_inputs(self):
        workflow = (REPO_ROOT / ".github" / "workflows" / "rust-native-release-evidence.yml").read_text(
            encoding="utf-8"
        )

        self.assertIn("RUST_NATIVE_RUNTIME_EVIDENCE_INPUT: ${{ inputs.evidence_dir }}", workflow)
        self.assertIn("MISSING_LIMIT: ${{ inputs.missing_limit }}", workflow)
        self.assertIn("^artifacts/rust-native-runtime-evidence(/[A-Za-z0-9._-]+)*$", workflow)
        self.assertIn('[[ ! "${MISSING_LIMIT}" =~ ^[0-9]+$ ]]', workflow)
        self.assertIn('--missing-limit "${MISSING_LIMIT}"', workflow)
        self.assertNotIn('--missing-limit "${{ inputs.missing_limit }}"', workflow)

        job = workflow.split("  release-platform-evidence:\n", 1)[1]
        self.assertIn("    environment: production\n", job)
        job_env = job.split("    env:\n", 1)[1].split("    steps:\n", 1)[0]
        self.assertNotIn("GH_TOKEN", job_env)
        self.assertNotIn("GITHUB_TOKEN", job_env)
        self.assertIn(
            "        env:\n          GH_TOKEN: ${{ github.token }}\n          GITHUB_TOKEN: ${{ github.token }}",
            workflow,
        )

    def test_rust_promotion_audit_limits_evidence_path_and_token_scope(self):
        workflow = (REPO_ROOT / ".github" / "workflows" / "rust-native-promotion-audit.yml").read_text(encoding="utf-8")

        self.assertIn("RUST_NATIVE_RUNTIME_EVIDENCE_INPUT: ${{ inputs.evidence_dir }}", workflow)
        self.assertIn("^artifacts/rust-native-runtime-evidence(/[A-Za-z0-9._-]+)*$", workflow)
        job = workflow.split("  promotion-audit:\n", 1)[1]
        self.assertIn("    environment: production\n", job)
        job_env = job.split("    env:\n", 1)[1].split("    steps:\n", 1)[0]
        self.assertNotIn("GH_TOKEN", job_env)
        self.assertNotIn("GITHUB_TOKEN", job_env)
        self.assertIn(
            "        env:\n          GH_TOKEN: ${{ github.token }}\n          GITHUB_TOKEN: ${{ github.token }}",
            workflow,
        )

    def test_loc_snapshot_workflow_cannot_mutate_main(self):
        workflow = (REPO_ROOT / ".github" / "workflows" / "update-loc-snapshot.yml").read_text(encoding="utf-8")
        self.assertIn("pull_request:", workflow)
        self.assertIn("permissions:\n  contents: read", workflow)
        self.assertIn("tools/update_loc_snapshot.py --readme README.md --check", workflow)
        self.assertNotIn("contents: write", workflow)
        self.assertNotIn("git push", workflow)


if __name__ == "__main__":
    unittest.main()
