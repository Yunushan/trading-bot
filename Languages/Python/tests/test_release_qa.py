from __future__ import annotations

import importlib.util
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
- Release platform evidence run ID: 123456789

- [x] Desktop visual flow: Passed with expected controls and error states.
- [x] Service API flow: Passed health, authentication, and unavailable-service checks.
- [x] LLM/local-model flow: Passed disabled, missing-token, and unavailable-model checks.
- [x] Release package: Passed clean start, provenance, SBOM, and uninstall checks.
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
            note.write_text(_approved_note().replace("- Outcome: approved", "- Outcome: pending").replace("- [x] Release package", "- [ ] Release package"), encoding="utf-8")
            issues = checker.validate_release_qa_note(note, tag="v1.2.3", source_revision=REVISION)
        self.assertIn("QA note Outcome must be approved", issues)
        self.assertIn("QA note must record a completed Release package check", issues)

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

    def test_release_qa_commit_mode_requires_a_current_revision(self):
        checker = _load_checker()
        with mock.patch.dict(os.environ, {}, clear=True):
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
                self.assertIn("docs/release-qa/${{ github.ref_name }}.md", workflow)
                self.assertIn("--require-current-revision", workflow)
                self.assertIn("--allow-release-qa-commit", workflow)
                self.assertIn("--require-platform-evidence-run", workflow)
                self.assertIn("fetch-depth: 2", workflow)

    def test_tagged_release_publishers_validate_downloaded_platform_evidence(self):
        for workflow_name in RELEASE_WORKFLOWS:
            with self.subTest(workflow=workflow_name):
                workflow = (REPO_ROOT / ".github" / "workflows" / workflow_name).read_text(encoding="utf-8")
                self.assertIn("./.github/actions/verify-release-platform-evidence", workflow)

        action = (
            REPO_ROOT / ".github" / "actions" / "verify-release-platform-evidence" / "action.yml"
        ).read_text(encoding="utf-8")
        self.assertIn("actions/download-artifact@37930b1c2abaa49bbe596cd826c3c89aef350131", action)
        self.assertIn("--require-evidence", action)
        self.assertIn("--require-current-commit", action)
        self.assertIn("--require-clean-source", action)
        self.assertIn("--require-platform-evidence-run", action)

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


if __name__ == "__main__":
    unittest.main()
