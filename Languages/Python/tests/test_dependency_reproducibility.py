from __future__ import annotations

import os
import subprocess
import sys
import unittest
from pathlib import Path


PYTHON_ROOT = Path(__file__).resolve().parents[1]
CHECK_SCRIPT = PYTHON_ROOT / "tools" / "check_dependency_metadata.py"


def _clean_subprocess_env() -> dict[str, str]:
    env = dict(os.environ)
    for key in list(env):
        if key.startswith("COV_CORE_") or key in {"COVERAGE_PROCESS_START", "PYTEST_CURRENT_TEST"}:
            env.pop(key, None)
    return env


class DependencyReproducibilityTests(unittest.TestCase):
    def test_dependency_metadata_check_passes(self):
        result = subprocess.run(
            [
                sys.executable,
                str(CHECK_SCRIPT),
            ],
            cwd=PYTHON_ROOT,
            env=_clean_subprocess_env(),
            text=True,
            capture_output=True,
            timeout=20,
            check=False,
        )

        self.assertEqual(0, result.returncode, f"stdout={result.stdout}\nstderr={result.stderr}")
        self.assertIn("requirements.txt -> .[desktop]", result.stdout)
        self.assertIn("requirements.service.txt -> .[service]", result.stdout)
        self.assertIn("dependencies are release-pinned", result.stdout)
        self.assertIn("canonical editable dependency surface", result.stdout)


if __name__ == "__main__":
    unittest.main()
