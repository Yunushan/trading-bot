from __future__ import annotations

import importlib.util
import json
import sys
import tempfile
import unittest
from contextlib import redirect_stdout
from io import StringIO
from pathlib import Path
from unittest import mock


REPO_ROOT = Path(__file__).resolve().parents[3]
CHECKER_PATH = REPO_ROOT / "tools" / "check_release_workflow_run.py"
RUN_ID = 123456789
REVISION = "a" * 40
REPOSITORY = "example/trading-bot"
WORKFLOW_PATH = ".github/workflows/ci.yml"


def _load_checker():
    spec = importlib.util.spec_from_file_location(
        "check_release_workflow_run", CHECKER_PATH
    )
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _run_payload() -> dict[str, object]:
    return {
        "id": RUN_ID,
        "head_sha": REVISION,
        "path": f"{WORKFLOW_PATH}@codex/release-candidate",
        "status": "completed",
        "conclusion": "success",
        "repository": {"full_name": REPOSITORY},
    }


class ReleaseWorkflowRunTests(unittest.TestCase):
    def test_accepts_successful_exact_source_run(self):
        checker = _load_checker()
        self.assertEqual(
            [],
            checker.validate_workflow_run(
                _run_payload(),
                expected_run_id=RUN_ID,
                expected_repository=REPOSITORY,
                expected_head_sha=REVISION,
                expected_workflow_path=WORKFLOW_PATH,
            ),
        )

    def test_rejects_every_release_binding_mismatch(self):
        checker = _load_checker()
        mutations = {
            "run id": ("id", RUN_ID + 1),
            "head SHA": ("head_sha", "b" * 40),
            "workflow path": ("path", ".github/workflows/codeql.yml@main"),
            "status": ("status", "in_progress"),
            "conclusion": ("conclusion", "failure"),
        }
        for label, (field, value) in mutations.items():
            with self.subTest(label=label):
                payload = _run_payload()
                payload[field] = value
                issues = checker.validate_workflow_run(
                    payload,
                    expected_run_id=RUN_ID,
                    expected_repository=REPOSITORY,
                    expected_head_sha=REVISION,
                    expected_workflow_path=WORKFLOW_PATH,
                )
                self.assertTrue(issues)

        payload = _run_payload()
        payload["repository"] = {"full_name": "other/trading-bot"}
        issues = checker.validate_workflow_run(
            payload,
            expected_run_id=RUN_ID,
            expected_repository=REPOSITORY,
            expected_head_sha=REVISION,
            expected_workflow_path=WORKFLOW_PATH,
        )
        self.assertTrue(any("repository" in issue for issue in issues))

    def test_cli_emits_machine_readable_approval(self):
        checker = _load_checker()
        with tempfile.TemporaryDirectory() as temp_dir:
            metadata = Path(temp_dir) / "run.json"
            metadata.write_text(json.dumps(_run_payload()), encoding="utf-8")
            stdout = StringIO()
            with redirect_stdout(stdout):
                result = checker.main(
                    [
                        str(metadata),
                        "--expected-run-id",
                        str(RUN_ID),
                        "--expected-repository",
                        REPOSITORY,
                        "--expected-head-sha",
                        REVISION,
                        "--expected-workflow-path",
                        WORKFLOW_PATH,
                        "--json",
                    ]
                )
        self.assertEqual(0, result)
        self.assertTrue(json.loads(stdout.getvalue())["ok"])

    def test_cli_fails_closed_for_invalid_metadata(self):
        checker = _load_checker()
        with tempfile.TemporaryDirectory() as temp_dir:
            metadata = Path(temp_dir) / "run.json"
            metadata.write_text("[]", encoding="utf-8")
            with redirect_stdout(StringIO()):
                result = checker.main(
                    [
                        str(metadata),
                        "--expected-run-id",
                        str(RUN_ID),
                        "--expected-repository",
                        REPOSITORY,
                        "--expected-head-sha",
                        REVISION,
                        "--expected-workflow-path",
                        WORKFLOW_PATH,
                    ]
                )
        self.assertEqual(1, result)

    def test_cli_accepts_metadata_from_standard_input(self):
        checker = _load_checker()
        stdin = StringIO(json.dumps(_run_payload()))
        with mock.patch.object(sys, "stdin", stdin), redirect_stdout(StringIO()):
            result = checker.main(
                [
                    "-",
                    "--expected-run-id",
                    str(RUN_ID),
                    "--expected-repository",
                    REPOSITORY,
                    "--expected-head-sha",
                    REVISION,
                    "--expected-workflow-path",
                    WORKFLOW_PATH,
                ]
            )
        self.assertEqual(0, result)


if __name__ == "__main__":
    unittest.main()
