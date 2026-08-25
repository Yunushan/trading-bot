from __future__ import annotations

import json
import sys
import unittest
from pathlib import Path


PYTHON_ROOT = Path(__file__).resolve().parents[1]
REPO_ROOT = PYTHON_ROOT.parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from tools import check_release_runner_availability as runner_check  # noqa: E402


def _target(target_id: str, labels: list[str], *, runner_kind: str = "self-hosted-windows-11") -> dict[str, object]:
    return {
        "target_id": target_id,
        "runner_kind": runner_kind,
        "runner_labels_json": json.dumps(labels),
    }


class ReleaseRunnerAvailabilityTests(unittest.TestCase):
    def test_matrix_parser_rejects_malformed_target_labels(self):
        with self.assertRaisesRegex(ValueError, "runner_labels_json"):
            runner_check.parse_target_matrix(json.dumps({"include": [_target("windows-11-x64", [])]}))

    def test_available_runner_must_be_online_and_not_busy(self):
        target = _target("windows-11-x64", ["self-hosted", "windows", "x64"])
        runners = [
            {
                "name": "offline-runner",
                "status": "offline",
                "busy": False,
                "labels": [{"name": label} for label in ["self-hosted", "windows", "x64"]],
            },
            {
                "name": "busy-runner",
                "status": "online",
                "busy": True,
                "labels": [{"name": label} for label in ["self-hosted", "windows", "x64"]],
            },
        ]

        issues = runner_check.availability_issues([target], runners)

        self.assertEqual(1, len(issues))
        self.assertIn("matching runners but none are ready", issues[0])

    def test_hosted_targets_are_ignored_by_self_hosted_preflight(self):
        target = _target("ubuntu-24_04-x64", ["ubuntu-24.04", "x64"], runner_kind="github-hosted")

        self.assertEqual([], runner_check.availability_issues([target], []))

    def test_all_required_labels_must_be_on_one_ready_runner(self):
        target = _target("windows-11-x64", ["self-hosted", "windows", "x64", "tb-release-platform"])
        runners = [
            {
                "name": "partial-runner",
                "status": "online",
                "busy": False,
                "labels": [{"name": label} for label in ["self-hosted", "windows", "x64"]],
            }
        ]

        issues = runner_check.availability_issues([target], runners)

        self.assertEqual(1, len(issues))
        self.assertIn("no runner advertising all required labels", issues[0])

