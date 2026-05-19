from __future__ import annotations

import importlib.util
import io
import unittest
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path
from unittest import mock


PYTHON_ROOT = Path(__file__).resolve().parents[1]
RUNNER_SCRIPT = PYTHON_ROOT / "tools" / "run_python_tests.py"

RUNNER_SPEC = importlib.util.spec_from_file_location("run_python_tests", RUNNER_SCRIPT)
assert RUNNER_SPEC is not None
assert RUNNER_SPEC.loader is not None
run_python_tests = importlib.util.module_from_spec(RUNNER_SPEC)
RUNNER_SPEC.loader.exec_module(run_python_tests)


def _run_runner(*args: str) -> tuple[int, str, str]:
    stdout = io.StringIO()
    stderr = io.StringIO()
    with redirect_stdout(stdout), redirect_stderr(stderr):
        returncode = run_python_tests.main(list(args))
    return returncode, stdout.getvalue(), stderr.getvalue()


class PythonTestRunnerTests(unittest.TestCase):
    def test_python_test_runner_preflights_full_test_dependencies(self):
        def fake_find_spec(name: str):
            return None if name in {"PyQt6", "httpx"} else object()

        with mock.patch("importlib.util.find_spec", side_effect=fake_find_spec):
            missing = run_python_tests.missing_python_test_dependencies()

        self.assertEqual(["PyQt6", "httpx"], missing)

    def test_python_test_runner_pytest_mode_preflights_pytest(self):
        def fake_find_spec(name: str):
            return None if name == "pytest" else object()

        with mock.patch("importlib.util.find_spec", side_effect=fake_find_spec):
            missing = run_python_tests.missing_python_test_dependencies("pytest")

        self.assertEqual(["pytest"], missing)

    def test_python_test_runner_dependency_check_prints_full_install_command(self):
        with (
            mock.patch.object(run_python_tests, "missing_python_test_dependencies", return_value=["PyQt6", "httpx"]),
            mock.patch("sys.stderr") as stderr,
        ):
            self.assertEqual(1, run_python_tests.check_dependencies())

        writes = "".join(str(call.args[0]) for call in stderr.write.call_args_list if call.args)
        self.assertIn("PyQt6", writes)
        self.assertIn("httpx", writes)
        self.assertIn("python tools/bootstrap_local_dev.py --python-command", writes)
        self.assertIn('Languages/Python[desktop,service,dev]', writes)

    def test_python_test_runner_check_deps_mode_does_not_run_suite(self):
        with (
            mock.patch.object(run_python_tests, "check_dependencies", return_value=0) as check_dependencies,
            mock.patch.object(run_python_tests, "run_unittest_suite") as run_unittest_suite,
        ):
            returncode, stdout, stderr = _run_runner("--check-deps")

        self.assertEqual(0, returncode, f"stdout={stdout}\nstderr={stderr}")
        check_dependencies.assert_called_once_with("unittest")
        run_unittest_suite.assert_not_called()

    def test_python_test_runner_pytest_mode_invokes_pytest_after_preflight(self):
        with (
            mock.patch.object(run_python_tests, "check_dependencies", return_value=0),
            mock.patch.object(run_python_tests, "run_pytest_suite", return_value=0) as run_pytest_suite,
        ):
            returncode, stdout, stderr = _run_runner("--runner", "pytest")

        self.assertEqual(0, returncode, f"stdout={stdout}\nstderr={stderr}")
        run_pytest_suite.assert_called_once_with()


if __name__ == "__main__":
    unittest.main()
