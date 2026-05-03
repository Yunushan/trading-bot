from __future__ import annotations

import os
import subprocess
import sys
import unittest
from pathlib import Path


PYTHON_ROOT = Path(__file__).resolve().parents[1]
RUNNER_SCRIPT = PYTHON_ROOT / "tools" / "run_service_tests.py"

if str(PYTHON_ROOT) not in sys.path:
    sys.path.insert(0, str(PYTHON_ROOT))

from tools.service_test_manifest import (  # noqa: E402
    INTENTIONALLY_EXCLUDED_SERVICE_TEST_MODULES,
    SERVICE_TEST_MODULES,
    discover_service_test_modules,
    docs_table_errors,
    module_list_errors,
    render_markdown_section,
)


def _clean_subprocess_env() -> dict[str, str]:
    env = dict(os.environ)
    for key in list(env):
        if key.startswith("COV_CORE_") or key in {"COVERAGE_PROCESS_START", "PYTEST_CURRENT_TEST"}:
            env.pop(key, None)
    return env


class ServiceTestRunnerTests(unittest.TestCase):
    def test_service_test_runner_lists_focused_modules(self):
        result = subprocess.run(
            [
                sys.executable,
                str(RUNNER_SCRIPT),
                "--list",
            ],
            cwd=PYTHON_ROOT,
            env=_clean_subprocess_env(),
            text=True,
            capture_output=True,
            timeout=20,
            check=False,
        )

        self.assertEqual(0, result.returncode, f"stdout={result.stdout}\nstderr={result.stderr}")
        self.assertEqual(list(SERVICE_TEST_MODULES), result.stdout.splitlines())
        self.assertNotIn("tests.test_service_api_smoke", result.stdout)

    def test_service_test_runner_checks_module_list_drift(self):
        result = subprocess.run(
            [
                sys.executable,
                str(RUNNER_SCRIPT),
                "--check-list",
            ],
            cwd=PYTHON_ROOT,
            env=_clean_subprocess_env(),
            text=True,
            capture_output=True,
            timeout=20,
            check=False,
        )

        self.assertEqual(0, result.returncode, f"stdout={result.stdout}\nstderr={result.stderr}")
        self.assertIn("[PASS] focused service test module list matches", result.stdout)

    def test_service_test_runner_checks_docs_against_manifest(self):
        result = subprocess.run(
            [
                sys.executable,
                str(RUNNER_SCRIPT),
                "--check-docs",
            ],
            cwd=PYTHON_ROOT,
            env=_clean_subprocess_env(),
            text=True,
            capture_output=True,
            timeout=20,
            check=False,
        )

        self.assertEqual(0, result.returncode, f"stdout={result.stdout}\nstderr={result.stderr}")
        self.assertIn("[PASS] focused service test docs match", result.stdout)

    def test_service_test_runner_prints_manifest_markdown(self):
        result = subprocess.run(
            [
                sys.executable,
                str(RUNNER_SCRIPT),
                "--print-markdown",
            ],
            cwd=PYTHON_ROOT,
            env=_clean_subprocess_env(),
            text=True,
            capture_output=True,
            timeout=20,
            check=False,
        )

        self.assertEqual(0, result.returncode, f"stdout={result.stdout}\nstderr={result.stderr}")
        self.assertEqual(render_markdown_section(), result.stdout.strip())

    def test_service_test_runner_has_explicit_exclusion_for_its_meta_test(self):
        self.assertEqual(("tests.test_service_test_runner",), INTENTIONALLY_EXCLUDED_SERVICE_TEST_MODULES)
        self.assertEqual([], module_list_errors(PYTHON_ROOT))
        self.assertEqual([], docs_table_errors(PYTHON_ROOT.parents[1]))
        self.assertIn("tests.test_service_schema_contracts", discover_service_test_modules(PYTHON_ROOT))


if __name__ == "__main__":
    unittest.main()
