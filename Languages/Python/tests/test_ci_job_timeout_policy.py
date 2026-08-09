from __future__ import annotations

import re
from pathlib import Path
import unittest


REPO_ROOT = Path(__file__).resolve().parents[3]
WORKFLOW_ROOT = REPO_ROOT / ".github" / "workflows"
JOB_HEADER = re.compile(r"^  ([A-Za-z0-9_-]+):\s*$")
TIMEOUT = re.compile(r"^    timeout-minutes:\s*(\d+)\s*$", re.MULTILINE)


def _job_blocks(workflow: str) -> dict[str, str]:
    lines = workflow.splitlines()
    try:
        jobs_index = next(index for index, line in enumerate(lines) if line.strip() == "jobs:")
    except StopIteration:
        return {}

    blocks: dict[str, list[str]] = {}
    current_name: str | None = None
    for line in lines[jobs_index + 1 :]:
        match = JOB_HEADER.fullmatch(line)
        if match:
            current_name = match.group(1)
            blocks[current_name] = [line]
        elif current_name is not None:
            blocks[current_name].append(line)
    return {name: "\n".join(lines) for name, lines in blocks.items()}


class CiJobTimeoutPolicyTests(unittest.TestCase):
    def test_every_workflow_job_has_one_bounded_timeout(self):
        workflow_files = sorted(WORKFLOW_ROOT.glob("*.yml"))
        self.assertTrue(workflow_files)

        violations: list[str] = []
        for workflow_file in workflow_files:
            blocks = _job_blocks(workflow_file.read_text(encoding="utf-8"))
            for job_name, block in blocks.items():
                values = [int(value) for value in TIMEOUT.findall(block)]
                if len(values) != 1:
                    violations.append(f"{workflow_file.name}:{job_name} must declare exactly one timeout-minutes")
                    continue
                if not 1 <= values[0] <= 360:
                    violations.append(
                        f"{workflow_file.name}:{job_name} timeout-minutes={values[0]} is outside the 1..360 minute policy"
                    )

        self.assertFalse(violations, "\n".join(violations))


if __name__ == "__main__":
    unittest.main()
