from __future__ import annotations

import importlib.util
import sys
import unittest
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[3]
TOOLS_DIR = REPO_ROOT / "tools"
if str(TOOLS_DIR) not in sys.path:
    sys.path.insert(0, str(TOOLS_DIR))

CHECKER_PATH = TOOLS_DIR / "check_release_workflow_run_set.py"
RUN_ID = 123456789
REVISION = "a" * 40
REPOSITORY = "example/trading-bot"
WORKFLOW_PATH = ".github/workflows/release-windows.yml"


def _load_checker():
    spec = importlib.util.spec_from_file_location(
        "check_release_workflow_run_set", CHECKER_PATH
    )
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _run(*, event: str = "push") -> dict[str, object]:
    return {
        "id": RUN_ID,
        "head_sha": REVISION,
        "path": WORKFLOW_PATH,
        "status": "completed",
        "conclusion": "success",
        "event": event,
        "repository": {"full_name": REPOSITORY},
    }


class ReleaseWorkflowRunSetTests(unittest.TestCase):
    def test_accepts_successful_exact_tag_packaging_run(self):
        checker = _load_checker()
        approved, issues = checker.validate_workflow_run_set(
            {"workflow_runs": [_run()]},
            expected_repository=REPOSITORY,
            expected_head_sha=REVISION,
            expected_workflow_path=WORKFLOW_PATH,
        )
        self.assertEqual([RUN_ID], approved)
        self.assertEqual([], issues)

    def test_accepts_workflow_dispatch_for_the_exact_tag(self):
        checker = _load_checker()
        approved, issues = checker.validate_workflow_run_set(
            {"workflow_runs": [_run(event="workflow_dispatch")]},
            expected_repository=REPOSITORY,
            expected_head_sha=REVISION,
            expected_workflow_path=WORKFLOW_PATH,
        )
        self.assertEqual([RUN_ID], approved)
        self.assertEqual([], issues)

    def test_rejects_wrong_source_or_non_release_event(self):
        checker = _load_checker()
        wrong_source = _run()
        wrong_source["head_sha"] = "b" * 40
        approved, issues = checker.validate_workflow_run_set(
            {"workflow_runs": [wrong_source, _run(event="schedule")]},
            expected_repository=REPOSITORY,
            expected_head_sha=REVISION,
            expected_workflow_path=WORKFLOW_PATH,
        )
        self.assertEqual([], approved)
        self.assertTrue(any("no completed successful" in issue for issue in issues))
        self.assertTrue(any("head SHA" in issue for issue in issues))
        self.assertTrue(any("event" in issue for issue in issues))

    def test_rejects_missing_run_list(self):
        checker = _load_checker()
        approved, issues = checker.validate_workflow_run_set(
            {},
            expected_repository=REPOSITORY,
            expected_head_sha=REVISION,
            expected_workflow_path=WORKFLOW_PATH,
        )
        self.assertEqual([], approved)
        self.assertTrue(issues)


if __name__ == "__main__":
    unittest.main()
