"""Run the focused service API test suite."""

from __future__ import annotations

import argparse
import importlib.util
import shutil
import sys
import unittest
from pathlib import Path


PYTHON_ROOT = Path(__file__).resolve().parents[1]
REPO_ROOT = PYTHON_ROOT.parents[1]

if str(PYTHON_ROOT) not in sys.path:
    sys.path.insert(0, str(PYTHON_ROOT))

from tools.service_test_manifest import (  # noqa: E402
    SERVICE_TEST_MODULES,
    docs_table_errors,
    module_list_errors,
    render_markdown_section,
)


SERVICE_TEST_DEPENDENCIES = ("fastapi", "httpx")


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


def service_dependency_install_hint() -> str:
    selected_python = _declared_python_command()
    return (
        "Install them from the repository root with the declared-runtime bootstrap: "
        f'python tools/bootstrap_local_dev.py --python-command "{selected_python}" --skip-client-deps\n'
        "Or install the focused service test surface directly with: "
        f'{selected_python} -m pip install -e "Languages/Python[service,dev]"'
    )


def missing_service_test_dependencies() -> list[str]:
    return [name for name in SERVICE_TEST_DEPENDENCIES if importlib.util.find_spec(name) is None]


def check_dependencies() -> int:
    missing = missing_service_test_dependencies()
    if not missing:
        return 0
    print(
        "[FAIL] focused service tests require optional service/dev dependencies: "
        + ", ".join(sorted(missing)),
        file=sys.stderr,
    )
    print(service_dependency_install_hint(), file=sys.stderr)
    return 1


def build_suite() -> unittest.TestSuite:
    return unittest.defaultTestLoader.loadTestsFromNames(SERVICE_TEST_MODULES)


def check_module_list() -> int:
    errors = module_list_errors(PYTHON_ROOT)
    if errors:
        for error in errors:
            print(f"[FAIL] {error}", file=sys.stderr)
        return 1
    print("[PASS] focused service test module list matches test_service_*.py files")
    return 0


def check_docs() -> int:
    errors = docs_table_errors(REPO_ROOT)
    if errors:
        for error in errors:
            print(f"[FAIL] {error}", file=sys.stderr)
        return 1
    print("[PASS] focused service test docs match tools/service_test_manifest.py")
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--list", action="store_true", help="print the focused service modules without running them")
    mode.add_argument(
        "--check-list",
        action="store_true",
        help="verify every test_service_*.py file is listed or intentionally excluded",
    )
    mode.add_argument(
        "--check-docs",
        action="store_true",
        help="verify focused service test map docs match the central manifest",
    )
    mode.add_argument("--print-markdown", action="store_true", help="print the generated focused service test map")
    parser.add_argument("-f", "--failfast", action="store_true", help="stop after the first failed test")
    parser.add_argument("-v", "--verbose", action="store_true", help="show verbose unittest output")
    args = parser.parse_args(argv)

    if args.list:
        for module_name in SERVICE_TEST_MODULES:
            print(module_name)
        return 0

    if args.check_list:
        return check_module_list()

    if args.check_docs:
        return check_docs()

    if args.print_markdown:
        print(render_markdown_section())
        return 0

    dependency_status = check_dependencies()
    if dependency_status:
        return dependency_status

    runner = unittest.TextTestRunner(
        stream=sys.stdout,
        verbosity=2 if args.verbose else 1,
        failfast=args.failfast,
    )
    result = runner.run(build_suite())
    return 0 if result.wasSuccessful() else 1


if __name__ == "__main__":
    raise SystemExit(main())
