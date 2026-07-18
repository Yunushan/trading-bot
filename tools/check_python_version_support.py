#!/usr/bin/env python3
"""Validate declared and CI-checked Python support for 3.10 through 3.14."""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path


SUPPORTED_PYTHON_VERSIONS = ("3.10", "3.11", "3.12", "3.13", "3.14")
DEFAULT_PYTHON_VERSION = "3.14"
PYTHON_REQUIRES = ">=3.10,<3.15"
DOCKER_PYTHON_IMAGE = "python:3.14-slim@sha256:cea0e6040540fb2b965b6e7fb5ffa00871e632eef63719f0ea54bca189ce14a6"
WINDOWS_BOOTSTRAP_PYTHON_VERSION = "3.14.5"


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[1]


def _read(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def _quoted_value(text: str, key: str) -> str:
    match = re.search(rf"(?m)^\s*{re.escape(key)}\s*=\s*[\"']([^\"']+)[\"']", text)
    return match.group(1).strip() if match else ""


def _current_minor() -> str:
    return f"{sys.version_info.major}.{sys.version_info.minor}"


def _check_pyproject(root: Path) -> list[str]:
    text = _read(root / "Languages" / "Python" / "pyproject.toml")
    issues: list[str] = []
    requires_python = _quoted_value(text, "requires-python")
    if requires_python != PYTHON_REQUIRES:
        issues.append(f"requires-python must be {PYTHON_REQUIRES!r}; found {requires_python!r}")

    for version in SUPPORTED_PYTHON_VERSIONS:
        classifier = f'"Programming Language :: Python :: {version}"'
        if classifier not in text:
            issues.append(f"missing pyproject classifier for Python {version}")

    if _quoted_value(text, "target-version") != "py310":
        issues.append("ruff target-version must remain py310 for lowest-supported Python compatibility")
    if _quoted_value(text, "python_version") != "3.10":
        issues.append("mypy python_version must remain 3.10 for lowest-supported Python compatibility")
    if '"tomli>=2,<3; python_version < \'3.11\'"' not in text:
        issues.append("dev dependencies must include tomli for Python 3.10 metadata/test tooling")
    return issues


def _check_default_version(root: Path) -> list[str]:
    actual = _read(root / ".python-version").strip()
    if actual != DEFAULT_PYTHON_VERSION:
        return [f".python-version must stay pinned to {DEFAULT_PYTHON_VERSION}; found {actual!r}"]
    return []


def _check_deployment_versions(root: Path) -> list[str]:
    issues: list[str] = []
    dockerfile = _read(root / "docker" / "backend.Dockerfile")
    if f"FROM {DOCKER_PYTHON_IMAGE}" not in dockerfile:
        issues.append(f"docker backend must use the pinned base image {DOCKER_PYTHON_IMAGE!r}")

    launcher = _read(root / "Languages" / "Python" / "Trading-Bot-Python.bat")
    expected_installer = (
        f"https://www.python.org/ftp/python/{WINDOWS_BOOTSTRAP_PYTHON_VERSION}/"
        f"python-{WINDOWS_BOOTSTRAP_PYTHON_VERSION}-amd64.exe"
    )
    if expected_installer not in launcher:
        issues.append(
            "Windows launcher must bootstrap Python "
            f"{WINDOWS_BOOTSTRAP_PYTHON_VERSION} from python.org"
        )
    return issues


def _check_ci_matrix(root: Path) -> list[str]:
    workflow = _read(root / ".github" / "workflows" / "ci.yml")
    issues: list[str] = []
    required_fragments = (
        "python-version-compatibility:",
        "Python 3.10-3.14 Compatibility",
        "python tools/check_python_version_support.py --current",
        'python -m pip install -e "./Languages/Python[service,dev]"',
    )
    for fragment in required_fragments:
        if fragment not in workflow:
            issues.append(f"ci.yml missing compatibility fragment: {fragment}")
    for version in SUPPORTED_PYTHON_VERSIONS:
        if f'"{version}"' not in workflow:
            issues.append(f"ci.yml compatibility matrix missing Python {version}")
    return issues


def run_checks(*, check_current: bool = False) -> dict[str, object]:
    root = _repo_root()
    issues: list[str] = []
    issues.extend(_check_default_version(root))
    issues.extend(_check_deployment_versions(root))
    issues.extend(_check_pyproject(root))
    issues.extend(_check_ci_matrix(root))
    current = _current_minor()
    if check_current and current not in SUPPORTED_PYTHON_VERSIONS:
        issues.append(
            f"current interpreter {current} is outside supported range "
            f"{SUPPORTED_PYTHON_VERSIONS[0]}-{SUPPORTED_PYTHON_VERSIONS[-1]}"
        )
    return {
        "ok": not issues,
        "supported_versions": list(SUPPORTED_PYTHON_VERSIONS),
        "default_version": DEFAULT_PYTHON_VERSION,
        "requires_python": PYTHON_REQUIRES,
        "current_version": current,
        "issues": issues,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--current", action="store_true", help="Also require the active interpreter to be supported.")
    parser.add_argument("--json", action="store_true", help="Print JSON report.")
    args = parser.parse_args(argv)

    report = run_checks(check_current=args.current)
    if args.json:
        print(json.dumps(report, indent=2, sort_keys=True))
    elif report["ok"]:
        print(
            "Python support matrix OK: "
            f"{SUPPORTED_PYTHON_VERSIONS[0]}-{SUPPORTED_PYTHON_VERSIONS[-1]} "
            f"(default {DEFAULT_PYTHON_VERSION})"
        )
    else:
        for issue in report["issues"]:
            print(f"[FAIL] {issue}", file=sys.stderr)
    return 0 if report["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
