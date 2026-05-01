from __future__ import annotations

import os
import subprocess
import sys
import unittest
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[3]
RELEASE_SMOKE_SCRIPT = REPO_ROOT / "tools" / "release_smoke.py"


def _clean_subprocess_env() -> dict[str, str]:
    env = dict(os.environ)
    for key in list(env):
        if key.startswith("COV_CORE_") or key in {"COVERAGE_PROCESS_START", "PYTEST_CURRENT_TEST"}:
            env.pop(key, None)
    return env


class ReleaseSmokeScriptTests(unittest.TestCase):
    def test_release_smoke_dry_run_lists_fast_preflight_without_full_tests(self):
        result = subprocess.run(
            [
                sys.executable,
                str(RELEASE_SMOKE_SCRIPT),
                "--dry-run",
                "--skip-full-tests",
                "--manual-smoke-mode",
                "fast",
            ],
            cwd=REPO_ROOT,
            env=_clean_subprocess_env(),
            text=True,
            capture_output=True,
            timeout=20,
            check=False,
        )

        self.assertEqual(0, result.returncode, f"stdout={result.stdout}\nstderr={result.stderr}")
        self.assertIn("compile Python sources", result.stdout)
        self.assertIn("Languages/Python/tools", result.stdout)
        self.assertIn("python -m ruff check", result.stdout)
        self.assertIn("check Python dependency metadata", result.stdout)
        self.assertIn("Languages/Python/tools/check_dependency_metadata.py", result.stdout)
        self.assertIn("python -m mypy", result.stdout)
        self.assertIn("manual desktop/service smoke", result.stdout)
        self.assertIn("--skip-http", result.stdout)
        self.assertNotIn("python -m pytest", result.stdout)

    def test_release_smoke_dry_run_can_skip_manual_smoke(self):
        result = subprocess.run(
            [
                sys.executable,
                str(RELEASE_SMOKE_SCRIPT),
                "--dry-run",
                "--skip-full-tests",
                "--manual-smoke-mode",
                "skip",
            ],
            cwd=REPO_ROOT,
            env=_clean_subprocess_env(),
            text=True,
            capture_output=True,
            timeout=20,
            check=False,
        )

        self.assertEqual(0, result.returncode, f"stdout={result.stdout}\nstderr={result.stderr}")
        self.assertNotIn("manual desktop/service smoke", result.stdout)
        self.assertNotIn("manual_smoke.py", result.stdout)


if __name__ == "__main__":
    unittest.main()
