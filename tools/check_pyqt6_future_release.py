#!/usr/bin/env python3
"""Check whether a complete, installable PyQt6 future family is published."""

from __future__ import annotations

import argparse
import json
import platform
import re
import ssl
import sys
from collections.abc import Callable
from typing import Any
from urllib.request import Request, urlopen


PYQT6_PACKAGE_NAMES = (
    "PyQt6",
    "PyQt6-Qt6",
    "PyQt6-WebEngine",
    "PyQt6-WebEngine-Qt6",
)
PYQT6_SIP_PACKAGE_NAME = "PyQt6-sip"
PYQT6_WHEEL_PACKAGE_NAMES = (*PYQT6_PACKAGE_NAMES, PYQT6_SIP_PACKAGE_NAME)
PYQT6_SIP_MINIMUM_VERSION = (13, 8, 0)
PYQT6_SIP_MAXIMUM_VERSION = (14, 0, 0)
PLATFORM_WHEEL_MARKERS = {
    "ubuntu-24.04": ("manylinux", "linux_", "any"),
    "ubuntu-24.04-arm": ("manylinux", "linux_", "any"),
    "windows-2025": ("win_amd64",),
    "windows-11-arm": ("win_arm64",),
    "macos-14": ("macosx_", "any"),
    "macos-15": ("macosx_", "any"),
    "macos-15-intel": ("macosx_", "any"),
    "macos-26": ("macosx_", "any"),
}
PLATFORM_MACHINE_FAMILIES = {
    "ubuntu-24.04": "x64",
    "ubuntu-24.04-arm": "arm64",
    "windows-2025": "x64",
    "windows-11-arm": "arm64",
    "macos-14": "arm64",
    "macos-15": "arm64",
    "macos-15-intel": "x64",
    "macos-26": "arm64",
}
_STABLE_VERSION_RE = re.compile(r"^(\d+)\.(\d+)\.(\d+)$")
_PYTHON_VERSION_RE = re.compile(r"^(\d+)\.(\d+)$")


def stable_version(value: object) -> tuple[int, int, int] | None:
    match = _STABLE_VERSION_RE.fullmatch(str(value or ""))
    if match is None:
        return None
    return tuple(int(part) for part in match.groups())  # type: ignore[return-value]


def stable_series(value: object) -> tuple[int, int] | None:
    parsed = stable_version(value)
    return parsed[:2] if parsed is not None else None


def sip_version_compatible(value: object) -> bool:
    parsed = stable_version(value)
    return parsed is not None and PYQT6_SIP_MINIMUM_VERSION <= parsed < PYQT6_SIP_MAXIMUM_VERSION


def parse_python_version(value: object) -> tuple[int, int] | None:
    match = _PYTHON_VERSION_RE.fullmatch(str(value or "").strip())
    if match is None:
        return None
    return int(match.group(1)), int(match.group(2))


def runner_wheel_architectures(platform_name: str, machine_name: str | None = None) -> tuple[str, ...]:
    """Return normalized architectures after binding the runner label to its host."""

    machine = str(machine_name or platform.machine()).strip().lower()
    expected_family = PLATFORM_MACHINE_FAMILIES.get(platform_name)
    if expected_family is None:
        raise ValueError(f"Unsupported PyQt6 compatibility runner {platform_name!r}")
    machine_family = (
        "x64"
        if machine in {"amd64", "x86_64", "x64"}
        else "arm64"
        if machine in {"arm64", "aarch64", "arm64e"}
        else None
    )
    if machine_family != expected_family:
        raise ValueError(
            f"Runner {platform_name!r} reports architecture {machine!r}; "
            f"expected {expected_family}"
        )
    if expected_family == "x64":
        return ("x86_64", "amd64", "universal2") if platform_name.startswith("macos-") else ("x86_64", "amd64")
    return ("arm64", "aarch64", "universal2") if platform_name.startswith("macos-") else ("arm64", "aarch64")


def _wheel_python_compatible(
    python_tag: str,
    abi_tag: str,
    python_version: tuple[int, int] | None = None,
) -> bool:
    major, minor = python_version or sys.version_info[:2]
    current_code = major * 100 + minor
    for tag in python_tag.split("."):
        if tag in {f"py{major}", f"py{major}{minor}"}:
            return True
        match = re.fullmatch(r"cp(\d+)", tag)
        if match is None:
            continue
        tag_code = int(match.group(1))
        if tag_code == current_code and abi_tag in {f"cp{current_code}", "abi3"}:
            return True
        if tag_code <= current_code and abi_tag == "abi3":
            return True
    return False


def _wheel_platform_compatible(
    platform_tag: str,
    wheel_markers: tuple[str, ...],
    wheel_architectures: tuple[str, ...] | None,
) -> bool:
    if platform_tag == "any":
        return "any" in wheel_markers
    if not any(platform_tag.startswith(marker) for marker in wheel_markers):
        return False
    if wheel_architectures is None:
        return True
    return any(platform_tag.endswith(f"_{architecture}") for architecture in wheel_architectures)


def has_installable_wheel(
    files: object,
    wheel_markers: tuple[str, ...],
    wheel_architectures: tuple[str, ...] | None = None,
    python_version: tuple[int, int] | None = None,
) -> bool:
    """Return whether PyPI metadata has a non-yanked wheel for this runner."""

    if not isinstance(files, list):
        return False
    for file_info in files:
        if not isinstance(file_info, dict):
            continue
        filename = str(file_info.get("filename") or "").lower()
        if file_info.get("packagetype") != "bdist_wheel":
            continue
        if not filename.endswith(".whl") or file_info.get("yanked", False):
            continue
        wheel_parts = filename[:-4].split("-")
        if len(wheel_parts) < 5:
            continue
        python_tag, abi_tag, platform_part = wheel_parts[-3:]
        if not _wheel_python_compatible(python_tag, abi_tag, python_version):
            continue
        if any(
            _wheel_platform_compatible(platform_tag, wheel_markers, wheel_architectures)
            for platform_tag in platform_part.split(".")
        ):
            return True
    return False


def package_has_installable_release(
    package_name: str,
    releases: object,
    target: str,
    target_series: tuple[int, int],
    wheel_markers: tuple[str, ...],
    wheel_architectures: tuple[str, ...] | None = None,
    python_version: tuple[int, int] | None = None,
) -> bool:
    if not isinstance(releases, dict):
        return False
    if package_name == PYQT6_SIP_PACKAGE_NAME:
        return any(
            sip_version_compatible(version)
            and has_installable_wheel(files, wheel_markers, wheel_architectures, python_version)
            for version, files in releases.items()
        )
    if package_name == "PyQt6":
        return has_installable_wheel(
            releases.get(target, []), wheel_markers, wheel_architectures, python_version
        )
    return any(
        stable_series(version) == target_series
        and has_installable_wheel(files, wheel_markers, wheel_architectures, python_version)
        for version, files in releases.items()
    )


def package_has_published_release(
    package_name: str,
    releases: object,
    target: str,
    target_series: tuple[int, int],
) -> bool:
    """Return whether PyPI exposes the requested release metadata at all."""

    if not isinstance(releases, dict):
        return False
    if package_name == PYQT6_SIP_PACKAGE_NAME:
        return any(sip_version_compatible(version) for version in releases)
    if package_name == "PyQt6":
        return target in releases
    return any(stable_series(version) == target_series for version in releases)


def _fetch_package_json(package_name: str) -> dict[str, Any]:
    request = Request(
        f"https://pypi.org/pypi/{package_name}/json",
        headers={"User-Agent": "trading-bot-pyqt6-future-compatibility"},
    )
    with urlopen(  # noqa: S310 - fixed HTTPS PyPI endpoint
        request,
        timeout=20,
        context=_pypi_ssl_context(),
    ) as response:
        payload = json.load(response)
    if not isinstance(payload, dict):
        raise RuntimeError(f"PyPI returned an invalid metadata document for {package_name}")
    return payload


def _pypi_ssl_context() -> ssl.SSLContext:
    """Use the host trust store, falling back to the bundled public CA set."""

    try:
        import truststore
    except ImportError:
        try:
            import certifi
        except ImportError:
            return ssl.create_default_context()
        return ssl.create_default_context(cafile=certifi.where())
    else:
        return truststore.SSLContext(ssl.PROTOCOL_TLS_CLIENT)


def check_family_details(
    target: str,
    platform_name: str,
    metadata_loader: Callable[[str], dict[str, Any]] = _fetch_package_json,
    *,
    architecture: str | None = None,
    python_version: tuple[int, int] | None = None,
) -> tuple[dict[str, bool], dict[str, bool], tuple[int, int]]:
    """Return wheel availability, publication metadata, and the target series."""

    target_release = stable_version(target)
    if target_release is None:
        raise ValueError(f"Invalid PyQt6 target version {target!r}; use MAJOR.MINOR.PATCH")
    wheel_markers = PLATFORM_WHEEL_MARKERS.get(platform_name)
    if wheel_markers is None:
        raise ValueError(f"Unsupported PyQt6 compatibility runner {platform_name!r}")

    target_series = target_release[:2]
    wheel_architectures = runner_wheel_architectures(platform_name, architecture)
    package_status: dict[str, bool] = {}
    package_published: dict[str, bool] = {}
    for package_name in PYQT6_WHEEL_PACKAGE_NAMES:
        payload = metadata_loader(package_name)
        releases = payload.get("releases") if isinstance(payload, dict) else None
        package_published[package_name] = package_has_published_release(
            package_name,
            releases,
            target,
            target_series,
        )
        package_status[package_name] = package_has_installable_release(
            package_name,
            releases,
            target,
            target_series,
            wheel_markers,
            wheel_architectures,
            python_version,
        )
    return package_status, package_published, target_series


def check_family(
    target: str,
    platform_name: str,
    metadata_loader: Callable[[str], dict[str, Any]] = _fetch_package_json,
    *,
    architecture: str | None = None,
    python_version: tuple[int, int] | None = None,
) -> tuple[dict[str, bool], tuple[int, int]]:
    """Return whether every PyQt6 family member has a compatible wheel."""

    package_status, _package_published, target_series = check_family_details(
        target,
        platform_name,
        metadata_loader,
        architecture=architecture,
        python_version=python_version,
    )
    return package_status, target_series


def _write_github_output(
    path: str,
    available: bool,
    *,
    published: bool | None = None,
    complete: bool | None = None,
) -> None:
    with open(path, "a", encoding="utf-8") as output:
        output.write(f"available={'true' if available else 'false'}\n")
        if published is not None:
            output.write(f"published={'true' if published else 'false'}\n")
        if complete is not None:
            output.write(f"complete={'true' if complete else 'false'}\n")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--target", required=True, help="stable PyQt6 release to check")
    parser.add_argument("--platform", required=True, help="GitHub Actions runner identifier")
    parser.add_argument(
        "--architecture",
        help="target runner architecture (defaults to the current host; e.g. x86_64 or arm64)",
    )
    parser.add_argument(
        "--python-version",
        help="Python version used for wheel-tag compatibility (defaults to the current interpreter; e.g. 3.14)",
    )
    parser.add_argument(
        "--fail-on-partial-publication",
        action="store_true",
        help="fail when release metadata exists but the complete requested wheel family is unavailable",
    )
    parser.add_argument(
        "--github-output",
        help="GITHUB_OUTPUT path to receive available/published/complete booleans",
    )
    args = parser.parse_args(argv)

    target = args.target.strip()
    platform_name = args.platform.strip()
    try:
        python_version = None
        if args.python_version:
            python_version = parse_python_version(args.python_version)
            if python_version is None:
                raise ValueError(
                    f"Invalid Python version {args.python_version!r}; use MAJOR.MINOR"
                )
        package_status, package_published, target_series = check_family_details(
            target,
            platform_name,
            architecture=args.architecture,
            python_version=python_version,
        )
    except (OSError, ValueError, RuntimeError) as exc:
        print(f"[FAIL] {exc}", file=sys.stderr)
        return 1

    available = all(package_status.values())
    published = any(package_published.get(package_name, False) for package_name in PYQT6_PACKAGE_NAMES)
    complete = all(package_published.get(package_name, False) for package_name in PYQT6_PACKAGE_NAMES)
    if args.github_output:
        _write_github_output(
            args.github_output,
            available,
            published=published,
            complete=complete,
        )
    status_text = ", ".join(
        f"{package_name}={'compatible' if is_available else 'missing compatible wheel'}"
        for package_name, is_available in package_status.items()
    )
    publication_text = ", ".join(
        f"{package_name}={'published' if is_available else 'not yet published'}"
        for package_name, is_available in package_published.items()
    )
    print(
        f"PyQt6 {target_series[0]}.{target_series[1]} family wheel status for "
        f"{platform_name}: {status_text}. Publication metadata: {publication_text}."
    )
    if args.fail_on_partial_publication and published and (not complete or not available):
        missing = ", ".join(
            package_name
            for package_name, is_available in package_status.items()
            if not is_available
        )
        print(
            f"[FAIL] PyQt6 {target} is published but incomplete for {platform_name}"
            f" and Python {args.python_version or f'{sys.version_info.major}.{sys.version_info.minor}'}"
            f"; missing compatible wheels: {missing or 'none'}.",
            file=sys.stderr,
        )
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
