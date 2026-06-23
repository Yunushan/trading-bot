from __future__ import annotations

import importlib.util
import json
import sys
import unittest
from contextlib import redirect_stderr, redirect_stdout
from io import StringIO
from pathlib import Path
from unittest import mock


PYTHON_ROOT = Path(__file__).resolve().parents[1]
SMOKE_SCRIPT = PYTHON_ROOT / "tools" / "manual_smoke.py"

if str(PYTHON_ROOT) not in sys.path:
    sys.path.insert(0, str(PYTHON_ROOT))


def _load_manual_smoke_module():
    spec = importlib.util.spec_from_file_location("manual_smoke", SMOKE_SCRIPT)
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def _run_manual_smoke_with_mocked_healthcheck(*args: str) -> tuple[int, str, str]:
    module = _load_manual_smoke_module()
    stdout = StringIO()
    stderr = StringIO()
    with (
        mock.patch.object(module, "_check_service_healthcheck", return_value="service launcher --healthcheck returned ok"),
        redirect_stdout(stdout),
        redirect_stderr(stderr),
    ):
        returncode = module.main(list(args))
    return returncode, stdout.getvalue(), stderr.getvalue()


class ManualSmokeScriptTests(unittest.TestCase):
    def test_manual_smoke_default_timeout_covers_slow_service_startup(self):
        module = _load_manual_smoke_module()

        self.assertGreaterEqual(module.DEFAULT_TIMEOUT_SECONDS, 60.0)
        self.assertEqual(module.DEFAULT_TIMEOUT_SECONDS, module._build_parser().get_default("timeout"))

    def test_manual_smoke_cli_runs_non_http_checks_as_json(self):
        returncode, stdout, stderr = _run_manual_smoke_with_mocked_healthcheck("--skip-http", "--json")

        self.assertEqual(0, returncode, f"stdout={stdout}\nstderr={stderr}")
        payload = json.loads(stdout)
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
