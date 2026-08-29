#!/usr/bin/env python3
"""Validate the reviewed PyQt6 package range and desktop runtime API surface."""

from __future__ import annotations

import argparse
import importlib.metadata as importlib_metadata
import json
import os
import re
import sys
from pathlib import Path
from typing import Any, Callable

try:
    import tomllib
except ModuleNotFoundError:  # pragma: no cover - exercised on Python 3.10
    import tomli as tomllib  # type: ignore[import-not-found]


REPO_ROOT = Path(__file__).resolve().parents[1]
PYPROJECT_PATH = REPO_ROOT / "Languages" / "Python" / "pyproject.toml"
PYQT6_PACKAGE_NAMES = ("PyQt6", "PyQt6-Qt6", "PyQt6-WebEngine")
VersionTuple = tuple[int, int, int]

_VERSION_RE = re.compile(
    r"^\s*(\d+)\.(\d+)(?:\.(\d+))?(?:(?:[A-Za-z][A-Za-z0-9.-]*)|(?:[-+.][A-Za-z0-9.-]*))?\s*$"
)


def parse_release_version(value: object) -> VersionTuple | None:
    """Return the numeric release tuple while accepting normal prerelease suffixes."""

    match = _VERSION_RE.fullmatch(str(value or ""))
    if not match:
        return None
    return int(match.group(1)), int(match.group(2)), int(match.group(3) or 0)


def version_series(value: object) -> tuple[int, int] | None:
    parsed = parse_release_version(value)
    return parsed[:2] if parsed is not None else None


def _load_contract(root: Path = REPO_ROOT) -> dict[str, str]:
    pyproject_path = root / "Languages" / "Python" / "pyproject.toml"
    try:
        pyproject = tomllib.loads(pyproject_path.read_text(encoding="utf-8"))
    except (OSError, tomllib.TOMLDecodeError):
        return {}

    tool = pyproject.get("tool") if isinstance(pyproject.get("tool"), dict) else {}
    trading_bot = tool.get("trading-bot") if isinstance(tool.get("trading-bot"), dict) else {}
    contract = trading_bot.get("pyqt6") if isinstance(trading_bot.get("pyqt6"), dict) else {}
    return {
        key: str(contract.get(key) or "").strip()
        for key in ("minimum_version", "maximum_version_exclusive", "future_target_version")
    }


def _contract_versions(contract: dict[str, str]) -> tuple[VersionTuple | None, VersionTuple | None, VersionTuple | None]:
    return tuple(
        parse_release_version(contract.get(key, ""))
        for key in ("minimum_version", "maximum_version_exclusive", "future_target_version")
    )  # type: ignore[return-value]


def _validate_contract(contract: dict[str, str]) -> list[str]:
    minimum, maximum, future_target = _contract_versions(contract)
    errors: list[str] = []
    if minimum is None:
        errors.append("PyQt6 contract minimum_version is missing or invalid")
    if maximum is None:
        errors.append("PyQt6 contract maximum_version_exclusive is missing or invalid")
    if future_target is None:
        errors.append("PyQt6 contract future_target_version is missing or invalid")
    if minimum is not None and maximum is not None and minimum >= maximum:
        errors.append("PyQt6 contract minimum_version must be lower than maximum_version_exclusive")
    if minimum is not None and maximum is not None and future_target is not None:
        if not minimum <= future_target < maximum:
            errors.append("PyQt6 contract future_target_version must be inside the supported version range")
    return errors


def _validate_package_versions(
    package_versions: dict[str, str | None],
    contract: dict[str, str],
    required_version: str | None = None,
) -> tuple[list[str], dict[str, tuple[int, int]], bool]:
    minimum, maximum, future_target = _contract_versions(contract)
    errors: list[str] = []
    package_series: dict[str, tuple[int, int]] = {}
    parsed_versions: dict[str, VersionTuple] = {}

    for package_name in PYQT6_PACKAGE_NAMES:
        raw_version = package_versions.get(package_name)
        parsed = parse_release_version(raw_version)
        if parsed is None:
            errors.append(f"{package_name} is not installed or has an invalid version: {raw_version!r}")
            continue
        parsed_versions[package_name] = parsed
        package_series[package_name] = parsed[:2]
        if minimum is not None and maximum is not None and not minimum <= parsed < maximum:
            errors.append(
                f"{package_name} {raw_version} is outside the reviewed PyQt6 range "
                f"{contract.get('minimum_version', '')} <= version < {contract.get('maximum_version_exclusive', '')}"
            )

    distinct_series = set(package_series.values())
    if len(distinct_series) > 1:
        formatted = ", ".join(f"{name}={series[0]}.{series[1]}" for name, series in package_series.items())
        errors.append(f"PyQt6 packages must share one major.minor series; found {formatted}")

    required_series = version_series(required_version) if required_version else None
    if required_version and required_series is None:
        errors.append(f"requested PyQt6 version is invalid: {required_version!r}")
    if required_series is not None:
        mismatched = [
            package_name
            for package_name, series in package_series.items()
            if series != required_series
        ]
        if mismatched:
            errors.append(
                f"requested PyQt6 release series {required_series[0]}.{required_series[1]} is not installed for "
                + ", ".join(mismatched)
            )

    future_series = future_target[:2] if future_target is not None else None
    future_target_available = bool(
        future_series is not None
        and len(parsed_versions) == len(PYQT6_PACKAGE_NAMES)
        and all(parsed[:2] == future_series for parsed in parsed_versions.values())
    )
    return errors, package_series, future_target_available


def _installed_package_versions(
    version_provider: Callable[[str], str] = importlib_metadata.version,
) -> dict[str, str | None]:
    versions: dict[str, str | None] = {}
    for package_name in PYQT6_PACKAGE_NAMES:
        try:
            versions[package_name] = version_provider(package_name)
        except importlib_metadata.PackageNotFoundError:
            versions[package_name] = None
        except Exception:
            versions[package_name] = None
    return versions


def _prepare_headless_qt() -> None:
    if sys.platform != "win32" and not os.environ.get("DISPLAY"):
        os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")


def _probe_runtime() -> tuple[dict[str, str | None], dict[str, bool], list[str]]:
    _prepare_headless_qt()
    runtime_versions: dict[str, str | None] = {}
    api_checks = {
        "PyQt6.QtCore": False,
        "PyQt6.QtGui": False,
        "PyQt6.QtWidgets": False,
        "PyQt6.QtWebEngineCore.QWebEnginePage": False,
        "PyQt6.QtWebEngineWidgets.QWebEngineView": False,
    }
    errors: list[str] = []
    try:
        from PyQt6 import QtCore, QtGui, QtWidgets

        runtime_versions["PyQt6"] = str(getattr(QtCore, "PYQT_VERSION_STR", "")) or None
        runtime_versions["Qt6"] = str(getattr(QtCore, "QT_VERSION_STR", "")) or None
        api_checks["PyQt6.QtCore"] = all(
            hasattr(QtCore, name) for name in ("QCoreApplication", "QTimer", "QUrl")
        )
        api_checks["PyQt6.QtGui"] = hasattr(QtGui, "QIcon")
        api_checks["PyQt6.QtWidgets"] = all(
            hasattr(QtWidgets, name) for name in ("QApplication", "QWidget")
        )
    except Exception as exc:
        errors.append(f"PyQt6 core runtime import failed: {exc}")

    try:
        from PyQt6.QtWebEngineCore import QWebEnginePage

        api_checks["PyQt6.QtWebEngineCore.QWebEnginePage"] = QWebEnginePage is not None
    except Exception as exc:
        errors.append(f"PyQt6 WebEngineCore import failed: {exc}")

    try:
        from PyQt6.QtWebEngineWidgets import QWebEngineView

        api_checks["PyQt6.QtWebEngineWidgets.QWebEngineView"] = QWebEngineView is not None
    except Exception as exc:
        errors.append(f"PyQt6 WebEngineWidgets import failed: {exc}")

    for api_name, available in api_checks.items():
        if not available:
            errors.append(f"required PyQt6 API is unavailable: {api_name}")
    return runtime_versions, api_checks, errors


def _validate_runtime_versions(
    package_versions: dict[str, str | None], runtime_versions: dict[str, str | None]
) -> list[str]:
    errors: list[str] = []
    pyqt_series = version_series(package_versions.get("PyQt6"))
    qt_series = version_series(package_versions.get("PyQt6-Qt6"))
    runtime_pyqt_series = version_series(runtime_versions.get("PyQt6"))
    runtime_qt_series = version_series(runtime_versions.get("Qt6"))
    if runtime_pyqt_series is None:
        errors.append("PyQt6 runtime did not report a valid PYQT_VERSION_STR")
    elif pyqt_series is not None and runtime_pyqt_series != pyqt_series:
        errors.append(
            f"PyQt6 runtime series {runtime_pyqt_series[0]}.{runtime_pyqt_series[1]} does not match "
            f"the PyQt6 package series {pyqt_series[0]}.{pyqt_series[1]}"
        )
    if runtime_qt_series is None:
        errors.append("Qt6 runtime did not report a valid QT_VERSION_STR")
    elif qt_series is not None and runtime_qt_series != qt_series:
        errors.append(
            f"Qt6 runtime series {runtime_qt_series[0]}.{runtime_qt_series[1]} does not match "
            f"the PyQt6-Qt6 package series {qt_series[0]}.{qt_series[1]}"
        )
    return errors


def run_checks(
    *,
    root: Path = REPO_ROOT,
    required_version: str | None = None,
    version_provider: Callable[[str], str] = importlib_metadata.version,
    probe_runtime: bool = True,
) -> dict[str, Any]:
    contract = _load_contract(root)
    errors = _validate_contract(contract)
    package_versions = _installed_package_versions(version_provider)
    package_errors, package_series, future_target_available = _validate_package_versions(
        package_versions,
        contract,
        required_version,
    )
    errors.extend(package_errors)

    if probe_runtime:
        runtime_versions, api_checks, runtime_errors = _probe_runtime()
        errors.extend(runtime_errors)
        errors.extend(_validate_runtime_versions(package_versions, runtime_versions))
    else:
        runtime_versions = {}
        api_checks = {}

    report: dict[str, Any] = {
        "ok": not errors,
        "contract": contract,
        "package_versions": package_versions,
        "package_series": {
            name: f"{series[0]}.{series[1]}" for name, series in package_series.items()
        },
        "runtime_versions": runtime_versions,
        "api_checks": api_checks,
        "future_target_available": future_target_available,
        "errors": errors,
    }
    if required_version:
        report["required_version"] = required_version
    return report


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--require-version",
        help="require all PyQt6 distributions and runtimes to use this major.minor release series",
    )
    parser.add_argument("--json", action="store_true", help="print a machine-readable JSON report")
    args = parser.parse_args(argv)

    report = run_checks(required_version=args.require_version)
    if args.json:
        print(json.dumps(report, indent=2, sort_keys=True))
    elif report["ok"]:
        series = report["package_series"].get("PyQt6", "unknown")
        target = report["contract"].get("future_target_version", "unknown")
        print(f"PyQt6 compatibility OK: installed series {series}; future target {target}")
    else:
        for error in report["errors"]:
            print(f"[FAIL] {error}", file=sys.stderr)
    return 0 if report["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
