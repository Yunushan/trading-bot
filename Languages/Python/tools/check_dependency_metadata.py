from __future__ import annotations

import re
from pathlib import Path
from typing import Any

try:
    import tomllib
except ModuleNotFoundError:  # pragma: no cover - exercised on Python 3.10
    import tomli as tomllib  # type: ignore[import-not-found]


PYTHON_ROOT = Path(__file__).resolve().parents[1]
REPO_ROOT = PYTHON_ROOT.parents[1]
PYPROJECT_PATH = PYTHON_ROOT / "pyproject.toml"

EXPECTED_REQUIREMENT_SHIMS = {
    "requirements.backend.txt": ".",
    "requirements.service.txt": ".[service]",
    "requirements.txt": ".[desktop]",
    "requirements.windows-arm64.txt": ".[windows-arm64]",
}

SUPPORTED_PYTHON_CLASSIFIERS = {
    "Programming Language :: Python :: 3.10",
    "Programming Language :: Python :: 3.11",
    "Programming Language :: Python :: 3.12",
    "Programming Language :: Python :: 3.13",
    "Programming Language :: Python :: 3.14",
}

WINDOWS_ARM64_ALLOWLIST = {
    "aiohttp": "aiohttp>=3.9,<4",
}

DEV_DEPENDENCY_NAMES = {
    "httpx",
    "mypy",
    "pre-commit",
    "pytest",
    "pytest-cov",
    "ruff",
    "tomli",
    "types-requests",
}

PYTHON_VERSION_RUNTIME_PINS = {
    "numpy": {
        "numpy==2.2.6; python_version < '3.11'",
        "numpy==2.4.4; python_version >= '3.11'",
    },
    "pandas": {
        "pandas==2.3.2; python_version < '3.11'",
        "pandas==3.0.2; python_version >= '3.11'",
    },
}


def _load_pyproject() -> dict[str, Any]:
    return tomllib.loads(PYPROJECT_PATH.read_text(encoding="utf-8"))


def _strip_marker(requirement: str) -> str:
    return str(requirement or "").split(";", 1)[0].strip()


def _dependency_name(requirement: str) -> str:
    requirement_part = _strip_marker(requirement)
    name = re.split(r"\s*(?:===|==|~=|!=|<=|>=|<|>|@)\s*", requirement_part, maxsplit=1)[0].strip()
    if "[" in name:
        name = name.split("[", 1)[0].strip()
    return name.lower().replace("_", "-")


def _is_exact_pin(requirement: str) -> bool:
    requirement_part = _strip_marker(requirement)
    return "==" in requirement_part and "===" not in requirement_part


def _is_bounded_range(requirement: str) -> bool:
    requirement_part = _strip_marker(requirement).replace(" ", "")
    return ">=" in requirement_part and ",<" in requirement_part


def _non_comment_lines(path: Path) -> list[str]:
    lines: list[str] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        stripped = line.strip()
        if stripped and not stripped.startswith("#"):
            lines.append(stripped)
    return lines


def _check_python_support(project: dict[str, Any]) -> list[str]:
    errors: list[str] = []
    requires_python = str(project.get("requires-python") or "")
    if requires_python != ">=3.10,<3.15":
        errors.append(f"project.requires-python is {requires_python!r}; expected '>=3.10,<3.15'")

    classifiers = set(project.get("classifiers") or [])
    missing = sorted(SUPPORTED_PYTHON_CLASSIFIERS - classifiers)
    if missing:
        errors.append(f"missing Python classifiers: {', '.join(missing)}")
    return errors


def _check_requirement_shims() -> list[str]:
    errors: list[str] = []
    for filename, expected in EXPECTED_REQUIREMENT_SHIMS.items():
        path = PYTHON_ROOT / filename
        if not path.is_file():
            errors.append(f"{filename} is missing")
            continue
        actual_lines = _non_comment_lines(path)
        if actual_lines != [expected]:
            errors.append(f"{filename} must contain only {expected!r}; found {actual_lines!r}")
    return errors


def _check_exact_group(group_name: str, requirements: list[str]) -> list[str]:
    errors: list[str] = []
    for requirement in requirements:
        if not _is_exact_pin(requirement):
            errors.append(f"{group_name} dependency {requirement!r} must use an exact == pin")
    return errors


def _check_runtime_python_version_pins(requirements: list[str]) -> list[str]:
    errors: list[str] = []
    by_name: dict[str, set[str]] = {}
    for requirement in requirements:
        by_name.setdefault(_dependency_name(requirement), set()).add(requirement)
    for name, expected in PYTHON_VERSION_RUNTIME_PINS.items():
        actual = by_name.get(name, set())
        if actual != expected:
            errors.append(
                f"runtime dependency {name!r} must stay split for Python 3.10 compatibility: "
                f"expected {sorted(expected)!r}; found {sorted(actual)!r}"
            )
    return errors


def _check_windows_arm64_group(requirements: list[str]) -> list[str]:
    errors: list[str] = []
    for requirement in requirements:
        name = _dependency_name(requirement)
        allowed = WINDOWS_ARM64_ALLOWLIST.get(name)
        if allowed is not None:
            if requirement != allowed:
                errors.append(f"windows-arm64 dependency {name!r} must stay {allowed!r}; found {requirement!r}")
            continue
        if not _is_exact_pin(requirement):
            errors.append(f"windows-arm64 dependency {requirement!r} must use an exact == pin")
    return errors


def _check_dev_group(requirements: list[str]) -> list[str]:
    errors: list[str] = []
    names = {_dependency_name(requirement) for requirement in requirements}
    missing = sorted(DEV_DEPENDENCY_NAMES - names)
    unknown = sorted(names - DEV_DEPENDENCY_NAMES)
    if missing:
        errors.append(f"dev dependencies missing expected tools: {', '.join(missing)}")
    if unknown:
        errors.append(f"dev dependencies include unreviewed tools: {', '.join(unknown)}")
    for requirement in requirements:
        if not _is_bounded_range(requirement):
            errors.append(f"dev dependency {requirement!r} must use a bounded >=,< range")
    return errors


def _check_dependency_groups(pyproject: dict[str, Any]) -> list[str]:
    project = pyproject.get("project") or {}
    optional = project.get("optional-dependencies") or {}
    errors: list[str] = []
    runtime_dependencies = list(project.get("dependencies") or [])
    errors.extend(_check_exact_group("runtime", runtime_dependencies))
    errors.extend(_check_runtime_python_version_pins(runtime_dependencies))
    errors.extend(_check_exact_group("desktop", list(optional.get("desktop") or [])))
    errors.extend(_check_exact_group("service", list(optional.get("service") or [])))
    errors.extend(_check_windows_arm64_group(list(optional.get("windows-arm64") or [])))
    errors.extend(_check_dev_group(list(optional.get("dev") or [])))
    return errors


def _check_ci_install_surface() -> list[str]:
    workflow = (REPO_ROOT / ".github" / "workflows" / "ci.yml").read_text(encoding="utf-8")
    expected = 'python -m pip install -e "./Languages/Python[desktop,service,dev]"'
    if expected not in workflow:
        return [f"ci.yml must install the canonical editable dev surface: {expected}"]
    return []


def run_checks() -> list[str]:
    pyproject = _load_pyproject()
    project = pyproject.get("project") or {}
    errors: list[str] = []
    errors.extend(_check_python_support(project))
    errors.extend(_check_requirement_shims())
    errors.extend(_check_dependency_groups(pyproject))
    errors.extend(_check_ci_install_surface())
    return errors


def main() -> int:
    errors = run_checks()
    if errors:
        for error in errors:
            print(f"[FAIL] {error}")
        return 1

    print("[PASS] Python version support metadata is consistent")
    for filename, expected in EXPECTED_REQUIREMENT_SHIMS.items():
        print(f"[PASS] {filename} -> {expected}")
    print("[PASS] runtime, desktop, service, and Windows ARM64 dependencies are release-pinned")
    print("[PASS] dev dependencies use reviewed bounded ranges")
    print("[PASS] CI installs the canonical editable dependency surface")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
