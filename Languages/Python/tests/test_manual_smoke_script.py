from __future__ import annotations

import json
import os
import subprocess
import sys
import unittest
from pathlib import Path


PYTHON_ROOT = Path(__file__).resolve().parents[1]
SMOKE_SCRIPT = PYTHON_ROOT / "tools" / "manual_smoke.py"


class ManualSmokeScriptTests(unittest.TestCase):
    def test_manual_smoke_cli_runs_non_http_checks_as_json(self):
        env = dict(os.environ)
        for key in list(env):
            if key.startswith("COV_CORE_") or key in {"COVERAGE_PROCESS_START", "PYTEST_CURRENT_TEST"}:
                env.pop(key, None)
        result = subprocess.run(
            [
                sys.executable,
                str(SMOKE_SCRIPT),
                "--skip-http",
                "--json",
            ],
            cwd=PYTHON_ROOT,
            env=env,
            text=True,
            capture_output=True,
            timeout=60,
            check=False,
        )

        self.assertEqual(0, result.returncode, f"stdout={result.stdout}\nstderr={result.stderr}")
        payload = json.loads(result.stdout)
        self.assertTrue(payload["ok"])
        steps = {step["name"]: step for step in payload["steps"]}
        self.assertIn("desktop import", steps)
        self.assertIn("service launcher healthcheck", steps)
        self.assertIn("fake exchange order path", steps)
        self.assertTrue(steps["desktop import"]["ok"])
        self.assertTrue(steps["service launcher healthcheck"]["ok"])
        self.assertTrue(steps["fake exchange order path"]["ok"])


if __name__ == "__main__":
    unittest.main()
