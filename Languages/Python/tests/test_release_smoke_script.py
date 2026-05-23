from __future__ import annotations

import unittest
import importlib.util
import sys
from contextlib import redirect_stderr, redirect_stdout
from io import StringIO
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[3]
RELEASE_SMOKE_SCRIPT = REPO_ROOT / "tools" / "release_smoke.py"


def _load_release_smoke_module():
    spec = importlib.util.spec_from_file_location("release_smoke", RELEASE_SMOKE_SCRIPT)
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def _run_release_smoke(*args: str) -> tuple[int, str, str]:
    module = _load_release_smoke_module()
    stdout = StringIO()
    stderr = StringIO()
    with redirect_stdout(stdout), redirect_stderr(stderr):
        returncode = module.main(list(args))
    return returncode, stdout.getvalue(), stderr.getvalue()


class ReleaseSmokeScriptTests(unittest.TestCase):
    def test_release_smoke_dry_run_lists_fast_preflight_without_full_tests(self):
        returncode, stdout, stderr = _run_release_smoke(
            "--dry-run",
            "--skip-full-tests",
            "--manual-smoke-mode",
            "fast",
        )

        self.assertEqual(0, returncode, f"stdout={stdout}\nstderr={stderr}")
        self.assertIn("check runtime tool versions", stdout)
        self.assertIn("tools/check_local_tool_versions.py --strict", stdout)
        self.assertIn("check client dependency locks", stdout)
        self.assertIn("tools/check_client_dependency_locks.py --json --strict", stdout)
        self.assertIn("compile Python sources", stdout)
        self.assertIn("tools/check_python_sources_compile.py", stdout)
        self.assertNotIn("-m compileall", stdout)
        self.assertIn("python -m ruff check --no-cache", stdout)
        self.assertIn("check Python dependency metadata", stdout)
        self.assertIn("Languages/Python/tools/check_dependency_metadata.py", stdout)
        self.assertIn("python -m mypy --no-incremental --cache-dir", stdout)
        self.assertIn("manual desktop/service smoke", stdout)
        self.assertIn("--skip-http", stdout)
        self.assertNotIn("python -m pytest", stdout)

    def test_release_smoke_full_tests_use_preflight_runner(self):
        returncode, stdout, stderr = _run_release_smoke(
            "--dry-run",
            "--manual-smoke-mode",
            "skip",
        )

        self.assertEqual(0, returncode, f"stdout={stdout}\nstderr={stderr}")
        self.assertIn("run Python test suite", stdout)
        self.assertIn("tools/run_python_tests.py --runner pytest", stdout)
        self.assertNotIn("python -m pytest", stdout)

    def test_release_smoke_dry_run_accepts_selected_python_command(self):
        returncode, stdout, stderr = _run_release_smoke(
            "--dry-run",
            "--skip-full-tests",
            "--manual-smoke-mode",
            "skip",
            "--python-command",
            "python",
        )

        self.assertEqual(0, returncode, f"stdout={stdout}\nstderr={stderr}")
        self.assertIn('python tools/check_local_tool_versions.py --strict --python-command python', stdout)
        self.assertIn("python -m ruff check --no-cache", stdout)
        self.assertIn("python -m mypy --no-incremental --cache-dir", stdout)

    def test_release_smoke_rejects_conflicting_python_options(self):
        returncode, stdout, stderr = _run_release_smoke(
            "--dry-run",
            "--python",
            "python",
            "--python-command",
            "python",
        )

        self.assertEqual(2, returncode)
        self.assertIn("Use either --python or --python-command", stderr)

    def test_release_smoke_dry_run_can_skip_manual_smoke(self):
        returncode, stdout, stderr = _run_release_smoke(
            "--dry-run",
            "--skip-full-tests",
            "--manual-smoke-mode",
            "skip",
        )

        self.assertEqual(0, returncode, f"stdout={stdout}\nstderr={stderr}")
        self.assertNotIn("manual desktop/service smoke", stdout)
        self.assertNotIn("manual_smoke.py", stdout)


if __name__ == "__main__":
    unittest.main()
