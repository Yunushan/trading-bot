from __future__ import annotations

import io
import importlib.util
import sys
import unittest
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path
from unittest import mock


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

RUNNER_SPEC = importlib.util.spec_from_file_location("run_service_tests", RUNNER_SCRIPT)
assert RUNNER_SPEC is not None
assert RUNNER_SPEC.loader is not None
run_service_tests = importlib.util.module_from_spec(RUNNER_SPEC)
RUNNER_SPEC.loader.exec_module(run_service_tests)


def _run_runner(*args: str) -> tuple[int, str, str]:
    stdout = io.StringIO()
    stderr = io.StringIO()
    with redirect_stdout(stdout), redirect_stderr(stderr):
        returncode = run_service_tests.main(list(args))
    return returncode, stdout.getvalue(), stderr.getvalue()


class ServiceTestRunnerTests(unittest.TestCase):
    def test_service_test_runner_lists_focused_modules(self):
        returncode, stdout, stderr = _run_runner("--list")

        self.assertEqual(0, returncode, f"stdout={stdout}\nstderr={stderr}")
        self.assertEqual(list(SERVICE_TEST_MODULES), stdout.splitlines())
        self.assertNotIn("tests.test_service_api_smoke", stdout)

    def test_service_test_runner_checks_module_list_drift(self):
        returncode, stdout, stderr = _run_runner("--check-list")

        self.assertEqual(0, returncode, f"stdout={stdout}\nstderr={stderr}")
        self.assertIn("[PASS] focused service test module list matches", stdout)

    def test_service_test_runner_checks_docs_against_manifest(self):
        returncode, stdout, stderr = _run_runner("--check-docs")

        self.assertEqual(0, returncode, f"stdout={stdout}\nstderr={stderr}")
        self.assertIn("[PASS] focused service test docs match", stdout)

    def test_service_test_runner_prints_manifest_markdown(self):
        returncode, stdout, stderr = _run_runner("--print-markdown")

        self.assertEqual(0, returncode, f"stdout={stdout}\nstderr={stderr}")
        self.assertEqual(render_markdown_section(), stdout.strip())

    def test_service_test_runner_has_explicit_exclusion_for_its_meta_test(self):
        self.assertEqual(("tests.test_service_test_runner",), INTENTIONALLY_EXCLUDED_SERVICE_TEST_MODULES)
        self.assertEqual([], module_list_errors(PYTHON_ROOT))
        self.assertEqual([], docs_table_errors(PYTHON_ROOT.parents[1]))
        self.assertIn("tests.test_service_schema_contracts", discover_service_test_modules(PYTHON_ROOT))

    def test_service_test_runner_preflights_testclient_dependencies(self):
        def fake_find_spec(name: str):
            return None if name == "httpx" else object()

        with mock.patch("importlib.util.find_spec", side_effect=fake_find_spec):
            self.assertEqual(["httpx"], run_service_tests.missing_service_test_dependencies())

    def test_service_test_runner_dependency_check_prints_install_command(self):
        with (
            mock.patch.object(run_service_tests, "missing_service_test_dependencies", return_value=["httpx"]),
            mock.patch("sys.stderr") as stderr,
        ):
            self.assertEqual(1, run_service_tests.check_dependencies())

        writes = "".join(str(call.args[0]) for call in stderr.write.call_args_list if call.args)
        self.assertIn("httpx", writes)
        self.assertIn("python tools/bootstrap_local_dev.py --python-command", writes)
        self.assertIn('Languages/Python[service,dev]', writes)


if __name__ == "__main__":
    unittest.main()
