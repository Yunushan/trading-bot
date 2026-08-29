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
PYINSTALLER_REQUIREMENT = "pyinstaller==6.22.0"
PYQT6_PACKAGE_NAMES = (
    "PyQt6",
    "PyQt6-Qt6",
    "PyQt6-WebEngine",
    "PyQt6-WebEngine-Qt6",
)

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
    "Programming Language :: Python :: 3.15",
}

WINDOWS_ARM64_ALLOWLIST = {
    "aiohttp": "aiohttp>=3.14.3,<4",
}

DEV_DEPENDENCY_NAMES = {
    "httpx2",
    "mypy",
    "pre-commit",
    "pytest",
    "pytest-cov",
    "ruff",
    "tomli",
    "types-requests",
}

SECURITY_DEPENDENCIES = {
    "pip-audit": "pip-audit==2.10.1",
    "truststore": "truststore==0.10.4",
}

PYTHON_VERSION_RUNTIME_PINS = {
    "numpy": {
        "numpy==2.2.6; python_version < '3.11'",
        "numpy==2.4.4; python_version >= '3.11' and python_version < '3.15'",
        "numpy==2.5.2; python_version >= '3.15'",
    },
    "pandas": {
        "pandas==2.3.2; python_version < '3.11'",
        "pandas==3.0.2; python_version >= '3.11' and python_version < '3.15'",
        "pandas==3.0.5; python_version >= '3.15'",
    },
}

PYTHON_315_FALLBACK_DEPENDENCIES = {
    "binance-sdk-derivatives-trading-usds-futures": "binance-sdk-derivatives-trading-usds-futures==17.1.0; python_version < '3.15'",
    "binance-sdk-derivatives-trading-coin-futures": "binance-sdk-derivatives-trading-coin-futures==13.0.0; python_version < '3.15'",
    "binance-sdk-spot": "binance-sdk-spot==11.1.0; python_version < '3.15'",
}

PACKAGING_INSTALL_SURFACES = (
    PYTHON_ROOT / "tools" / "build_exe.ps1",
    PYTHON_ROOT / "tools" / "build_binary.sh",
    REPO_ROOT / ".github" / "workflows" / "release-windows.yml",
    REPO_ROOT / ".github" / "workflows" / "release-linux-macos.yml",
    REPO_ROOT / ".github" / "workflows" / "release-freebsd.yml",
)


def _load_pyproject() -> dict[str, Any]:
    return tomllib.loads(PYPROJECT_PATH.read_text(encoding="utf-8"))


def _pyqt6_contract(pyproject: dict[str, Any]) -> tuple[str, str, str]:
    tool = pyproject.get("tool") if isinstance(pyproject.get("tool"), dict) else {}
    trading_bot = tool.get("trading-bot") if isinstance(tool.get("trading-bot"), dict) else {}
    contract = trading_bot.get("pyqt6") if isinstance(trading_bot.get("pyqt6"), dict) else {}
    return (
        str(contract.get("minimum_version") or "").strip(),
        str(contract.get("maximum_version_exclusive") or "").strip(),
        str(contract.get("future_target_version") or "").strip(),
    )


def _release_version_tuple(value: str) -> tuple[int, int, int] | None:
    match = re.fullmatch(r"\s*(\d+)\.(\d+)(?:\.(\d+))?(?:[-+].*)?\s*", str(value or ""))
    if not match:
        return None
    return int(match.group(1)), int(match.group(2)), int(match.group(3) or 0)


def _pyqt6_dependency_specs(pyproject: dict[str, Any]) -> dict[str, str]:
    minimum, maximum, _future = _pyqt6_contract(pyproject)
    if _release_version_tuple(minimum) is None or _release_version_tuple(maximum) is None:
        return {}
    return {
        name.lower().replace("_", "-"): f"{name}>={minimum},<{maximum}"
        for name in PYQT6_PACKAGE_NAMES
    }


def _check_pyqt6_contract(pyproject: dict[str, Any]) -> list[str]:
    minimum, maximum, future = _pyqt6_contract(pyproject)
    minimum_tuple = _release_version_tuple(minimum)
    maximum_tuple = _release_version_tuple(maximum)
    future_tuple = _release_version_tuple(future)
    errors: list[str] = []
    if minimum_tuple is None:
        errors.append("PyQt6 contract minimum_version must be a semantic version")
    if maximum_tuple is None:
        errors.append("PyQt6 contract maximum_version_exclusive must be a semantic version")
    if future_tuple is None:
        errors.append("PyQt6 contract future_target_version must be a semantic version")
    if minimum_tuple and maximum_tuple and minimum_tuple >= maximum_tuple:
        errors.append("PyQt6 contract minimum_version must be lower than maximum_version_exclusive")
    if minimum_tuple and maximum_tuple and future_tuple and not (minimum_tuple <= future_tuple < maximum_tuple):
        errors.append("PyQt6 contract future_target_version must be inside the supported version range")
    return errors


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
    if requires_python != ">=3.10,<3.16":
        errors.append(f"project.requires-python is {requires_python!r}; expected '>=3.10,<3.16'")

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


def _check_pyqt6_group(
    group_name: str,
    requirements: list[str],
    expected_specs: dict[str, str],
) -> list[str]:
    errors: list[str] = []
    by_name = {_dependency_name(requirement): requirement for requirement in requirements}
    for name, expected in expected_specs.items():
        actual = by_name.get(name)
        if actual != expected:
            errors.append(
                f"{group_name} dependency {name!r} must use the reviewed PyQt6 range "
                f"{expected!r}; found {actual!r}"
            )
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


def _check_python_315_fallback_dependencies(requirements: list[str]) -> list[str]:
    errors: list[str] = []
    by_name: dict[str, set[str]] = {}
    for requirement in requirements:
        by_name.setdefault(_dependency_name(requirement), set()).add(requirement)
    for name, expected in PYTHON_315_FALLBACK_DEPENDENCIES.items():
        actual = by_name.get(name, set())
        if actual != {expected}:
            errors.append(
                f"Python 3.15 must omit upstream-incompatible SDK {name!r} via the guarded marker: "
                f"expected {[expected]!r}; found {sorted(actual)!r}"
            )
    return errors


def _check_windows_arm64_group(
    requirements: list[str], pyqt6_specs: dict[str, str]
) -> list[str]:
    errors: list[str] = []
    by_name = {_dependency_name(requirement): requirement for requirement in requirements}
    for name, expected in pyqt6_specs.items():
        actual = by_name.get(name)
        if actual != expected:
            errors.append(
                f"windows-arm64 dependency {name!r} must use the reviewed PyQt6 range "
                f"{expected!r}; found {actual!r}"
            )
    for requirement in requirements:
        name = _dependency_name(requirement)
        if name in pyqt6_specs:
            continue
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
    errors.extend(_check_python_315_fallback_dependencies(runtime_dependencies))
    errors.extend(_check_pyqt6_contract(pyproject))
    pyqt6_specs = _pyqt6_dependency_specs(pyproject)
    desktop_dependencies = list(optional.get("desktop") or [])
    errors.extend(_check_pyqt6_group("desktop", desktop_dependencies, pyqt6_specs))
    errors.extend(
        _check_exact_group(
            "desktop",
            [requirement for requirement in desktop_dependencies if _dependency_name(requirement) not in pyqt6_specs],
        )
    )
    errors.extend(_check_exact_group("service", list(optional.get("service") or [])))
    errors.extend(_check_windows_arm64_group(list(optional.get("windows-arm64") or []), pyqt6_specs))
    errors.extend(_check_dev_group(list(optional.get("dev") or [])))
    security_dependencies = list(optional.get("security") or [])
    actual_security = {_dependency_name(requirement): requirement for requirement in security_dependencies}
    for name, expected in SECURITY_DEPENDENCIES.items():
        if actual_security.get(name) != expected:
            errors.append(f"security dependency {name!r} must be pinned as {expected!r}")
    for name in sorted(set(actual_security) - set(SECURITY_DEPENDENCIES)):
        errors.append(f"security dependencies include unreviewed tool: {name}")
    return errors


def _check_ci_install_surface() -> list[str]:
    workflow = (REPO_ROOT / ".github" / "workflows" / "ci.yml").read_text(encoding="utf-8")
    errors: list[str] = []
    expected_install = 'python -m pip install -e "./Languages/Python[desktop,service,dev]"'
    if expected_install not in workflow:
        errors.append(f"ci.yml must install the canonical editable dev surface: {expected_install}")
    expected_pyqt_check = "python tools/check_pyqt6_compatibility.py --json"
    if expected_pyqt_check not in workflow:
        errors.append(f"ci.yml must run the PyQt6 compatibility gate: {expected_pyqt_check}")
    return errors


def _check_packaging_toolchain() -> list[str]:
    errors: list[str] = []
    requirements_path = PYTHON_ROOT / "requirements.packaging.txt"
    if not requirements_path.is_file():
        errors.append("requirements.packaging.txt is missing")
    else:
        requirements = _non_comment_lines(requirements_path)
        if requirements != [PYINSTALLER_REQUIREMENT]:
            errors.append(
                "requirements.packaging.txt must contain only "
                f"{PYINSTALLER_REQUIREMENT!r}; found {requirements!r}"
            )

    for path in PACKAGING_INSTALL_SURFACES:
        try:
            text = path.read_text(encoding="utf-8")
        except OSError as exc:
            errors.append(f"packaging install surface {path.relative_to(REPO_ROOT)} is unreadable: {exc}")
            continue
        if "requirements.packaging.txt" not in text:
            errors.append(
                f"packaging install surface {path.relative_to(REPO_ROOT)} must install requirements.packaging.txt"
            )
        if re.search(r"pip\s+install(?:\s+--upgrade)?\s+pyinstaller(?:\s|$)", text, flags=re.IGNORECASE):
            errors.append(f"packaging install surface {path.relative_to(REPO_ROOT)} installs unpinned PyInstaller")
    return errors


def run_checks() -> list[str]:
    pyproject = _load_pyproject()
    project = pyproject.get("project") or {}
    errors: list[str] = []
    errors.extend(_check_python_support(project))
    errors.extend(_check_requirement_shims())
    errors.extend(_check_dependency_groups(pyproject))
    errors.extend(_check_ci_install_surface())
    errors.extend(_check_packaging_toolchain())
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
    print("[PASS] runtime, desktop, service, and Windows ARM64 dependencies use reviewed release pins/ranges")
    print("[PASS] dev dependencies use reviewed bounded ranges")
    print(f"[PASS] packaging toolchain uses {PYINSTALLER_REQUIREMENT}")
    print("[PASS] CI installs the canonical editable dependency surface")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
