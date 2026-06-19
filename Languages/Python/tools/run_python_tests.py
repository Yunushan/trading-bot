"""Run the full Python test suite with dependency preflight."""

from __future__ import annotations

import argparse
import importlib.util
import os
import shutil
import subprocess
import sys
import unittest
from pathlib import Path


sys.dont_write_bytecode = True

PYTHON_ROOT = Path(__file__).resolve().parents[1]
REPO_ROOT = PYTHON_ROOT.parents[1]

if str(PYTHON_ROOT) not in sys.path:
    sys.path.insert(0, str(PYTHON_ROOT))


PYTHON_TEST_DEPENDENCIES = ("PyQt6", "fastapi", "httpx", "requests", "uvicorn")
PYTEST_TEST_DEPENDENCIES = ("pytest",)


def _read_declared_python_version() -> str:
    try:
        return (REPO_ROOT / ".python-version").read_text(encoding="utf-8").strip()
    except OSError:
        return "3.14"


def _declared_python_command() -> str:
    expected = _read_declared_python_version() or "3.14"
    if sys.platform == "win32":
        return f"py -{expected}" if shutil.which("py") else "python"
    return f"python{expected}"


def python_test_dependency_install_hint() -> str:
    selected_python = _declared_python_command()
    return (
        "Install them from the repository root with the declared-runtime bootstrap: "
        f'python tools/bootstrap_local_dev.py --python-command "{selected_python}" --skip-client-deps\n'
        "Or install the full Python test surface directly with: "
        f'{selected_python} -m pip install -e "Languages/Python[desktop,service,dev]"'
    )


def _dependency_names_for_runner(runner: str) -> tuple[str, ...]:
    names = list(PYTHON_TEST_DEPENDENCIES)
    if runner == "pytest":
        names.extend(PYTEST_TEST_DEPENDENCIES)
    return tuple(dict.fromkeys(names))


def missing_python_test_dependencies(runner: str = "pytest") -> list[str]:
    return [
        name
        for name in _dependency_names_for_runner(runner)
        if importlib.util.find_spec(name) is None
    ]


def check_dependencies(runner: str = "pytest") -> int:
    missing = missing_python_test_dependencies(runner)
    if not missing:
        return 0
    print(
        "[FAIL] full Python tests require optional desktop/service/dev dependencies: "
        + ", ".join(sorted(missing)),
        file=sys.stderr,
    )
    print(python_test_dependency_install_hint(), file=sys.stderr)
    return 1


def build_unittest_suite() -> unittest.TestSuite:
    return unittest.defaultTestLoader.discover(
        start_dir=str(PYTHON_ROOT / "tests"),
        top_level_dir=str(PYTHON_ROOT),
    )


def run_unittest_suite(*, failfast: bool, verbose: bool) -> int:
    runner = unittest.TextTestRunner(
        stream=sys.stdout,
        verbosity=2 if verbose else 1,
        failfast=failfast,
    )
    result = runner.run(build_unittest_suite())
    return 0 if result.wasSuccessful() else 1


def run_pytest_suite() -> int:
    env = os.environ.copy()
    env["PYTHONDONTWRITEBYTECODE"] = "1"
    result = subprocess.run(
        [sys.executable, "-m", "pytest"],
        cwd=PYTHON_ROOT,
        check=False,
        env=env,
    )
    return int(result.returncode)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--runner",
        choices=("unittest", "pytest"),
        default="pytest",
        help="test runner to invoke after dependency preflight",
    )
    parser.add_argument("--check-deps", action="store_true", help="only verify test dependencies")
    parser.add_argument("-f", "--failfast", action="store_true", help="stop after the first failed unittest test")
    parser.add_argument("-v", "--verbose", action="store_true", help="show verbose unittest output")
    args = parser.parse_args(argv)

    dependency_status = check_dependencies(str(args.runner))
    if dependency_status or args.check_deps:
        return dependency_status

    if args.runner == "pytest":
        return run_pytest_suite()
    return run_unittest_suite(failfast=bool(args.failfast), verbose=bool(args.verbose))


if __name__ == "__main__":
    raise SystemExit(main())
